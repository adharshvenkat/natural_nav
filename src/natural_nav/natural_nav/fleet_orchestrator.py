#!/usr/bin/env python3
"""
Task executor (single robot).

Consumes a task graph (JSON on /natural_nav/task_graph) emitted by the LLM
planner, walks its DAG, and dispatches each ready task to Nav2's NavigateToPose
action.

Task target resolution flow:
  1. Lookup the target label in the live semantic map (built by semantic_detector).
  2. If found, navigate.
  3. If not found, publish a status that triggers an LLM replan (e.g. an
     "explore" task is prepended, then the original target is retried).

The map is consumed via JSON snapshots on /natural_nav/semantic_map.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from std_msgs.msg import String
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose

from natural_nav.semantic_map import SemanticMap


class TaskStatus(str, Enum):
    PENDING = 'pending'
    READY = 'ready'
    DISPATCHED = 'dispatched'
    SUCCEEDED = 'succeeded'
    FAILED = 'failed'
    UNRESOLVABLE = 'unresolvable'  # target not in semantic map


@dataclass
class Task:
    id: str
    type: str
    target: str
    description: str
    depends_on: list[str] = field(default_factory=list)
    priority: int = 3
    status: TaskStatus = TaskStatus.PENDING
    failure_reason: str = ''

    def is_ready(self, all_tasks: dict[str, 'Task']) -> bool:
        if self.status != TaskStatus.PENDING:
            return False
        return all(all_tasks[dep].status == TaskStatus.SUCCEEDED
                   for dep in self.depends_on if dep in all_tasks)


class TaskExecutorNode(Node):
    def __init__(self):
        super().__init__('task_executor')

        self.declare_parameter('nav_action', '/navigate_to_pose')
        nav_action = self.get_parameter('nav_action').value

        self._nav_client = ActionClient(self, NavigateToPose, nav_action)
        self._semantic_map = SemanticMap()
        self._tasks: dict[str, Task] = {}
        self._mission_summary: str = ''
        self._replan_on_failure: bool = True
        self._active_task_id: Optional[str] = None

        self.create_subscription(
            String, '/natural_nav/task_graph', self._on_task_graph, 10)
        self.create_subscription(
            String, '/natural_nav/semantic_map', self._on_semantic_map, 10)

        self._status_pub = self.create_publisher(
            String, '/natural_nav/fleet_status', 10)
        # Re-publish on this topic to ask the planner to replan (with context).
        self._replan_request_pub = self.create_publisher(
            String, '/natural_nav/replan_request', 10)

        self._tick_timer = self.create_timer(0.5, self._tick)
        self.get_logger().info(
            f'Task Executor ready, waiting on Nav2 action {nav_action!r}')

    # subscriptions

    def _on_task_graph(self, msg: String):
        try:
            data = json.loads(msg.data)
        except json.JSONDecodeError as e:
            self.get_logger().error(f'Bad task graph JSON: {e}')
            return

        self._mission_summary = data.get('summary', '')
        self._replan_on_failure = bool(data.get('replan_on_failure', True))
        self._tasks = {}
        for t in data.get('tasks', []):
            task = Task(
                id=t['id'],
                type=t.get('type', 'navigate'),
                target=t.get('target', ''),
                description=t.get('description', ''),
                depends_on=list(t.get('depends_on', [])),
                priority=int(t.get('priority', 3)),
            )
            self._tasks[task.id] = task
        self._active_task_id = None
        self.get_logger().info(
            f'New mission: "{self._mission_summary}" ({len(self._tasks)} tasks)')
        self._publish_status()

    def _on_semantic_map(self, msg: String):
        try:
            data = json.loads(msg.data)
            self._semantic_map.load_dict(data)
        except (json.JSONDecodeError, ValueError) as e:
            self.get_logger().warn(f'Bad semantic map snapshot: {e}')

    # execution loop

    def _tick(self):
        if not self._tasks or self._active_task_id is not None:
            return

        next_task = self._pick_next_task()
        if next_task is None:
            if self._all_done():
                self.get_logger().info(
                    f'Mission complete: "{self._mission_summary}"')
                self._tasks = {}
                self._publish_status()
            return

        self._dispatch(next_task)

    def _pick_next_task(self) -> Optional[Task]:
        ready = [t for t in self._tasks.values() if t.is_ready(self._tasks)]
        if not ready:
            return None
        ready.sort(key=lambda t: (t.priority, t.id))
        return ready[0]

    def _all_done(self) -> bool:
        return all(t.status in (TaskStatus.SUCCEEDED,
                                TaskStatus.FAILED,
                                TaskStatus.UNRESOLVABLE)
                   for t in self._tasks.values())

    def _dispatch(self, task: Task):
        pose = self._resolve_target(task.target)
        if pose is None:
            task.status = TaskStatus.UNRESOLVABLE
            task.failure_reason = f'target {task.target!r} not in semantic map'
            self.get_logger().warn(
                f'Task {task.id}: {task.failure_reason} '
                f'(known labels: {list(self._semantic_map.labels())})')
            self._publish_status()
            if self._replan_on_failure:
                self._request_replan(task)
            return

        if not self._nav_client.wait_for_server(timeout_sec=2.0):
            self.get_logger().error('Nav2 action server not available')
            task.status = TaskStatus.FAILED
            task.failure_reason = 'nav action server unavailable'
            self._publish_status()
            return

        goal = NavigateToPose.Goal()
        goal.pose = self._make_pose_stamped(pose[0], pose[1])
        task.status = TaskStatus.DISPATCHED
        self._active_task_id = task.id
        self.get_logger().info(
            f'Dispatching task {task.id} ({task.type}) -> '
            f'{task.target} at ({pose[0]:.2f}, {pose[1]:.2f})')
        self._publish_status()

        send = self._nav_client.send_goal_async(goal)
        send.add_done_callback(lambda fut: self._on_goal_response(fut, task.id))

    def _resolve_target(self, target: str) -> Optional[tuple[float, float]]:
        exact = self._semantic_map.lookup(target)
        if exact is not None:
            return exact
        fuzzy = self._semantic_map.fuzzy_lookup(target)
        if fuzzy is not None:
            matched, pose = fuzzy
            self.get_logger().info(
                f'Resolved {target!r} via fuzzy match -> {matched!r}')
            return pose
        return None

    def _on_goal_response(self, future, task_id: str):
        goal_handle = future.result()
        task = self._tasks.get(task_id)
        if task is None:
            return
        if not goal_handle.accepted:
            self.get_logger().warn(f'Task {task_id}: goal rejected by Nav2')
            task.status = TaskStatus.FAILED
            task.failure_reason = 'goal rejected'
            self._active_task_id = None
            self._publish_status()
            if self._replan_on_failure:
                self._request_replan(task)
            return
        result_fut = goal_handle.get_result_async()
        result_fut.add_done_callback(
            lambda fut: self._on_goal_result(fut, task_id))

    def _on_goal_result(self, future, task_id: str):
        task = self._tasks.get(task_id)
        if task is None:
            return
        status_code = future.result().status
        # 4 = STATUS_SUCCEEDED in action_msgs/GoalStatus
        if status_code == 4:
            task.status = TaskStatus.SUCCEEDED
            self.get_logger().info(f'Task {task_id}: succeeded')
        else:
            task.status = TaskStatus.FAILED
            task.failure_reason = f'nav goal terminal status {status_code}'
            self.get_logger().warn(f'Task {task_id}: {task.failure_reason}')
            if self._replan_on_failure:
                self._request_replan(task)
        self._active_task_id = None
        self._publish_status()

    def _request_replan(self, failed_task: Task):
        request = {
            'mission_summary': self._mission_summary,
            'failed_task': {
                'id': failed_task.id,
                'type': failed_task.type,
                'target': failed_task.target,
                'description': failed_task.description,
                'reason': failed_task.failure_reason,
            },
            'known_labels': list(self._semantic_map.labels()),
            'remaining_tasks': [
                {'id': t.id, 'type': t.type, 'target': t.target,
                 'description': t.description, 'status': t.status.value}
                for t in self._tasks.values() if t.id != failed_task.id
            ],
        }
        msg = String()
        msg.data = json.dumps(request)
        self._replan_request_pub.publish(msg)
        self.get_logger().info(
            f'Requested replan for task {failed_task.id}: {failed_task.failure_reason}')

    # helpers

    def _publish_status(self):
        snapshot = {
            'mission': self._mission_summary,
            'active_task': self._active_task_id,
            'tasks': [
                {'id': t.id, 'type': t.type, 'target': t.target,
                 'status': t.status.value, 'failure_reason': t.failure_reason}
                for t in self._tasks.values()
            ],
            'known_labels': list(self._semantic_map.labels()),
        }
        msg = String()
        msg.data = json.dumps(snapshot)
        self._status_pub.publish(msg)

    @staticmethod
    def _make_pose_stamped(x: float, y: float, yaw: float = 0.0) -> PoseStamped:
        pose = PoseStamped()
        pose.header.frame_id = 'map'
        pose.pose.position.x = float(x)
        pose.pose.position.y = float(y)
        # quaternion from yaw (z-axis rotation)
        pose.pose.orientation.z = math.sin(yaw / 2.0)
        pose.pose.orientation.w = math.cos(yaw / 2.0)
        return pose


def main(args=None):
    rclpy.init(args=args)
    node = TaskExecutorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
