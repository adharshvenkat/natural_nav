import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class FleetOrchestratorNode(Node):
    def __init__(self):
        super().__init__('fleet_orchestrator')
        self.sub = self.create_subscription(String, '/natural_nav/task_graph', self._cb, 10)
        self.pub = self.create_publisher(String, '/natural_nav/fleet_status', 10)
        self.get_logger().info('Fleet Orchestrator stub ready')

    def _cb(self, msg):
        self.get_logger().info(f'Received task graph: {msg.data}')


def main(args=None):
    rclpy.init(args=args)
    node = FleetOrchestratorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
