#!/usr/bin/env python3
"""
LLM Planner node.

Subscribes:
  /natural_nav/command          std_msgs/String   natural-language command
  /natural_nav/semantic_map     std_msgs/String   JSON snapshot of label->pose map
  /natural_nav/replan_request   std_msgs/String   JSON context from executor on failure

Publishes:
  /natural_nav/task_graph       std_msgs/String   JSON task DAG
  /natural_nav/planner_status   std_msgs/String   human-readable status

The system prompt is rebuilt at planning time using the *current* known_labels
from the semantic map so the LLM only emits target labels the executor can
actually resolve.
"""

from __future__ import annotations

import json

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from natural_nav.llm_client import get_client


SYSTEM_PROMPT_TEMPLATE = """You are a task planner for a single mobile robot
in a warehouse. Convert the user's natural-language command into a JSON task
graph the robot's executor can dispatch.

Output ONLY valid JSON (no prose, no markdown fences) matching this schema:

{{
  "summary": "one-line description of the mission",
  "tasks": [
    {{
      "id": "t1",
      "type": "navigate" | "inspect",
      "target": "<label>",
      "depends_on": ["<task id>", ...],
      "priority": 1,
      "description": "human-readable description"
    }}
  ],
  "replan_on_failure": true
}}

CRITICAL: the "target" field MUST be one of the labels the robot has actually
perceived. Use ONLY labels from this list (case-insensitive, exact match
preferred; the executor will fuzzy-match if needed):

{known_labels}

If the command can't be satisfied with any of the known labels, return:
{{ "summary": "no matching target", "tasks": [], "replan_on_failure": false }}

Rules:
- "navigate" = go to the target.
- "inspect" = navigate to the target then loiter to perceive it.
- Chain tasks via depends_on when ordering matters.
- Keep ids short (t1, t2, ...). priority 1 = highest.
{replan_context}
"""


class LLMPlannerNode(Node):
    def __init__(self):
        super().__init__('llm_planner')

        self.declare_parameter('llm_provider', '')
        self.declare_parameter('llm_api_key', '')
        self.declare_parameter('llm_model', '')

        provider = self.get_parameter('llm_provider').value or None
        api_key = self.get_parameter('llm_api_key').value or None
        model = self.get_parameter('llm_model').value or None

        try:
            self._llm = get_client(provider, api_key, model)
        except ValueError as e:
            self.get_logger().error(f'LLM client init failed: {e}')
            raise

        self._known_labels: list[str] = []
        self._pending_replan_context: dict | None = None
        self._last_command: str = ''

        self.create_subscription(
            String, '/natural_nav/command', self._on_command, 10)
        self.create_subscription(
            String, '/natural_nav/semantic_map', self._on_semantic_map, 10)
        self.create_subscription(
            String, '/natural_nav/replan_request', self._on_replan_request, 10)

        self._graph_pub = self.create_publisher(
            String, '/natural_nav/task_graph', 10)
        self._status_pub = self.create_publisher(
            String, '/natural_nav/planner_status', 10)

        self.get_logger().info('LLM Planner ready')

    # ── subscriptions ────────────────────────────────────────────────────────

    def _on_semantic_map(self, msg: String):
        try:
            data = json.loads(msg.data)
            self._known_labels = sorted(data.keys())
        except json.JSONDecodeError:
            pass

    def _on_command(self, msg: String):
        command = msg.data.strip()
        if not command:
            return
        self._last_command = command
        self._pending_replan_context = None
        self.get_logger().info(f'Planning command: "{command}"')
        self._plan(command)

    def _on_replan_request(self, msg: String):
        try:
            ctx = json.loads(msg.data)
        except json.JSONDecodeError as e:
            self.get_logger().warn(f'Bad replan request JSON: {e}')
            return
        if not self._last_command:
            self.get_logger().warn(
                'Replan requested but no prior command, ignoring')
            return
        # Pull the freshest known_labels from the request (executor sends them).
        self._known_labels = sorted(ctx.get('known_labels', self._known_labels))
        self._pending_replan_context = ctx
        self.get_logger().info(
            f'Replanning after failure: '
            f'{ctx.get("failed_task", {}).get("reason", "(no reason)")}')
        self._plan(self._last_command)

    # ── planning ─────────────────────────────────────────────────────────────

    def _plan(self, command: str):
        self._publish_status(f'planning: {command}')

        if not self._known_labels:
            self.get_logger().warn(
                'No known labels in semantic map yet, emitting empty plan. '
                'Drive the robot around to populate the map first.')
            empty = {
                'summary': 'no perceived labels yet, explore first',
                'tasks': [],
                'replan_on_failure': False,
            }
            out = String()
            out.data = json.dumps(empty)
            self._graph_pub.publish(out)
            return

        prompt = self._build_prompt()
        try:
            raw = self._llm.complete(prompt, command)
            task_graph = self._parse_json(raw)
        except Exception as e:
            self.get_logger().error(f'Planning failed: {e}')
            self._publish_status(f'error: {e}')
            return

        out = String()
        out.data = json.dumps(task_graph)
        self._graph_pub.publish(out)
        n = len(task_graph.get('tasks', []))
        self.get_logger().info(
            f'Published task graph: {task_graph.get("summary", "")} ({n} tasks)')
        self._publish_status(
            f'planned {n} tasks: {task_graph.get("summary", "")}')

    def _build_prompt(self) -> str:
        labels = '\n'.join(f'  - {label}' for label in self._known_labels)
        replan_context = ''
        if self._pending_replan_context:
            ctx = self._pending_replan_context
            failed = ctx.get('failed_task', {})
            replan_context = (
                '\nThis is a REPLAN. The previous attempt failed:\n'
                f'  failed task id : {failed.get("id")}\n'
                f'  failed target  : {failed.get("target")}\n'
                f'  reason         : {failed.get("reason")}\n'
                'Avoid that target. Pick a different known label or return an '
                'empty plan if nothing fits.'
            )
        return SYSTEM_PROMPT_TEMPLATE.format(
            known_labels=labels, replan_context=replan_context)

    @staticmethod
    def _parse_json(raw: str) -> dict:
        """Extract JSON from the model response, tolerating ```json fences."""
        raw = raw.strip()
        if raw.startswith('```'):
            raw = raw.split('```', 2)[1]
            if raw.startswith('json'):
                raw = raw[4:]
        return json.loads(raw.strip())

    def _publish_status(self, text: str):
        msg = String()
        msg.data = text
        self._status_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = LLMPlannerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
