#!/usr/bin/env python3
"""
LLM Planner node: converts a natural language command into a structured
multi-robot task graph (JSON), published on /natural_nav/task_graph.
"""

import json

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from natural_nav.llm_client import get_client


SYSTEM_PROMPT = """You are a task planner for a 2-robot warehouse fleet.

Convert the user's natural language command into a JSON task graph. Output ONLY
valid JSON, no prose, matching this schema:

{
  "summary": "one-line description of the mission",
  "tasks": [
    {
      "id": "t1",
      "type": "navigate" | "inspect" | "deliver" | "alert",
      "target": "<location name>",
      "robot_id": "robot_1" | "robot_2" | "any",
      "depends_on": ["<task id>", ...],
      "priority": 1-5,
      "description": "human-readable description"
    }
  ],
  "replan_on_failure": true
}

Rules:
- Robots: robot_1, robot_2 (identical, full capability). Use "any" unless the
  command requires a specific robot; the orchestrator assigns by availability.
- Locations: shelf_row_1..shelf_row_10, workstation_1..workstation_5,
  charging_dock_1, charging_dock_2, entrance, storage_area.
- "inspect" implies navigate-then-perceive at the target.
- "deliver X to Y" → an inspect/pickup task at X, then a navigate task to Y
  that depends_on the first.
- Assign independent tasks to different robots so they run in parallel.
- Keep ids short (t1, t2, ...). priority 1 = highest.
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

        self._cmd_sub = self.create_subscription(
            String, '/natural_nav/command', self._on_command, 10)
        self._graph_pub = self.create_publisher(
            String, '/natural_nav/task_graph', 10)
        self._status_pub = self.create_publisher(
            String, '/natural_nav/planner_status', 10)

        self.get_logger().info('LLM Planner ready')

    def _on_command(self, msg: String):
        command = msg.data.strip()
        if not command:
            return
        self.get_logger().info(f'Planning command: "{command}"')
        self._publish_status(f'planning: {command}')

        try:
            raw = self._llm.complete(SYSTEM_PROMPT, command)
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
        self._publish_status(f'planned {n} tasks: {task_graph.get("summary", "")}')

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
