import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class LLMPlannerNode(Node):
    def __init__(self):
        super().__init__('llm_planner')
        self.sub = self.create_subscription(String, '/natural_nav/command', self._cb, 10)
        self.pub = self.create_publisher(String, '/natural_nav/task_graph', 10)
        self.get_logger().info('LLM Planner stub ready')

    def _cb(self, msg):
        self.get_logger().info(f'Received: {msg.data}')


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
