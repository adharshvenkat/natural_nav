import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from sensor_msgs.msg import Image


class SemanticDetectorNode(Node):
    def __init__(self):
        super().__init__('semantic_detector')
        self.sub = self.create_subscription(Image, '/robot_1/camera/image_raw', self._cb, 10)
        self.pub = self.create_publisher(String, '/natural_nav/detections', 10)
        self.get_logger().info('Semantic Detector stub ready')

    def _cb(self, msg):
        self.get_logger().info('Image received')


def main(args=None):
    rclpy.init(args=args)
    node = SemanticDetectorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
