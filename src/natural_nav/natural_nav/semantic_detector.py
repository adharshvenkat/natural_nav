#!/usr/bin/env python3
"""
Semantic detector node.

Runs GroundingDINO on the TB4's OAK-D RGB feed at ~2 Hz with a static
warehouse-relevant prompt list. For each detection:
  - take the bbox center pixel
  - sample depth from the aligned depth image
  - unproject to a 3D point in the camera optical frame using intrinsics
  - transform to the map frame via TF
  - update the in-memory SemanticMap

Publishes a JSON snapshot of the map on /natural_nav/semantic_map at ~1 Hz so
the task executor (and any external watcher) can react.

Depends on:
  /rgbd_camera/image          sensor_msgs/Image  (RGB, ~10 Hz)
  /rgbd_camera/depth_image    sensor_msgs/Image  (float32 metric depth)
  /rgbd_camera/camera_info    sensor_msgs/CameraInfo (intrinsics)
  TF: oakd_rgb_camera_optical_frame -> map  (provided by Nav2 + robot_state_publisher)

Weights:
  ~/.cache/naturalnav/groundingdino/groundingdino_swint_ogc.pth
  Pull via scripts/setup_groundingdino.sh
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import String
from sensor_msgs.msg import Image, CameraInfo
from geometry_msgs.msg import PointStamped
from tf2_ros import Buffer, TransformListener, TransformException
from tf2_geometry_msgs import do_transform_point
from cv_bridge import CvBridge

from natural_nav.semantic_map import SemanticMap
from natural_nav.projection import sample_depth, unproject, scale_pixel


# Default open-vocab prompt for warehouse scenes. GroundingDINO uses ' . '
# as label separator.
DEFAULT_PROMPTS = [
    'shelf', 'pallet', 'box', 'cardboard box',
    'person', 'chair', 'table',
    'forklift', 'door', 'barrel',
]

DEFAULT_WEIGHTS = Path('/root/.cache/naturalnav/groundingdino/groundingdino_swint_ogc.pth')
DEFAULT_CONFIG = Path('/usr/local/lib/python3.12/dist-packages/groundingdino/config/GroundingDINO_SwinT_OGC.py')


@dataclass
class CameraIntrinsics:
    fx: float
    fy: float
    cx: float
    cy: float
    width: int
    height: int


class SemanticDetectorNode(Node):
    def __init__(self):
        super().__init__('semantic_detector')

        # NOTE: use_sim_time is implicitly declared by rclpy. Pass it on the
        # CLI (--ros-args -p use_sim_time:=true) so get_clock() reflects
        # Gazebo's /clock and TF lookups stay in the same timebase.
        self.declare_parameter('image_topic', '/rgbd_camera/image')
        self.declare_parameter('depth_topic', '/rgbd_camera/depth_image')
        self.declare_parameter('camera_info_topic', '/rgbd_camera/camera_info')
        self.declare_parameter('map_frame', 'map')
        self.declare_parameter('detect_period_sec', 0.5)        # ~2 Hz inference
        self.declare_parameter('publish_period_sec', 1.0)       # 1 Hz map snapshot
        self.declare_parameter('box_threshold', 0.30)
        self.declare_parameter('text_threshold', 0.25)
        self.declare_parameter('weights_path', str(DEFAULT_WEIGHTS))
        self.declare_parameter('config_path', str(DEFAULT_CONFIG))
        self.declare_parameter('device', 'cuda')
        self.declare_parameter('prompts', DEFAULT_PROMPTS)
        self.declare_parameter('max_depth_m', 8.0)              # ignore very far hits
        self.declare_parameter('min_depth_m', 0.3)              # too-close hits = junk

        self._image_topic = self.get_parameter('image_topic').value
        self._depth_topic = self.get_parameter('depth_topic').value
        self._info_topic = self.get_parameter('camera_info_topic').value
        self._map_frame = self.get_parameter('map_frame').value
        self._box_thresh = self.get_parameter('box_threshold').value
        self._text_thresh = self.get_parameter('text_threshold').value
        self._device = self.get_parameter('device').value
        self._max_depth = self.get_parameter('max_depth_m').value
        self._min_depth = self.get_parameter('min_depth_m').value
        self._prompts: list[str] = list(self.get_parameter('prompts').value)
        self._caption = ' . '.join(self._prompts) + ' .'

        self._bridge = CvBridge()
        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self)

        self._latest_rgb: np.ndarray | None = None
        self._latest_rgb_header = None
        self._latest_depth: np.ndarray | None = None
        self._intrinsics: CameraIntrinsics | None = None
        self._lock = threading.Lock()

        self._semantic_map = SemanticMap()
        self._inference_lock = threading.Lock()
        self._gdino_model = None

        self.create_subscription(
            Image, self._image_topic, self._on_rgb, qos_profile_sensor_data)
        self.create_subscription(
            Image, self._depth_topic, self._on_depth, qos_profile_sensor_data)
        self.create_subscription(
            CameraInfo, self._info_topic, self._on_camera_info, qos_profile_sensor_data)

        self._map_pub = self.create_publisher(
            String, '/natural_nav/semantic_map', 10)
        self._detections_pub = self.create_publisher(
            String, '/natural_nav/detections', 10)

        self._load_model()

        detect_period = self.get_parameter('detect_period_sec').value
        publish_period = self.get_parameter('publish_period_sec').value
        self.create_timer(detect_period, self._run_inference)
        self.create_timer(publish_period, self._publish_map)

        self.get_logger().info(
            f'Semantic detector ready, prompts={self._prompts}, '
            f'inference={1.0/detect_period:.1f} Hz, '
            f'publish={1.0/publish_period:.1f} Hz')

    # ── model load ──────────────────────────────────────────────────────────

    def _load_model(self):
        from groundingdino.util.inference import load_model
        weights = Path(self.get_parameter('weights_path').value)
        config = Path(self.get_parameter('config_path').value)
        if not weights.exists():
            self.get_logger().error(
                f'GroundingDINO weights not found at {weights}. '
                'Run scripts/setup_groundingdino.sh to download them.')
            raise FileNotFoundError(str(weights))
        if not config.exists():
            self.get_logger().error(f'GroundingDINO config not found at {config}')
            raise FileNotFoundError(str(config))
        self.get_logger().info(
            f'Loading GroundingDINO on {self._device} from {weights.name}...')
        self._gdino_model = load_model(str(config), str(weights), device=self._device)
        self.get_logger().info('GroundingDINO loaded')

    # ── subscriptions ────────────────────────────────────────────────────────

    def _on_rgb(self, msg: Image):
        try:
            arr = self._bridge.imgmsg_to_cv2(msg, desired_encoding='rgb8')
        except Exception as e:
            self.get_logger().warn(f'rgb conversion failed: {e}')
            return
        with self._lock:
            self._latest_rgb = arr
            self._latest_rgb_header = msg.header

    def _on_depth(self, msg: Image):
        try:
            arr = self._bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')
            # Some Gazebo configs publish depth as uint16 mm; we want float meters.
            if arr.dtype == np.uint16:
                arr = arr.astype(np.float32) / 1000.0
            else:
                arr = arr.astype(np.float32)
        except Exception as e:
            self.get_logger().warn(f'depth conversion failed: {e}')
            return
        with self._lock:
            self._latest_depth = arr

    def _on_camera_info(self, msg: CameraInfo):
        with self._lock:
            self._intrinsics = CameraIntrinsics(
                fx=msg.k[0], fy=msg.k[4],
                cx=msg.k[2], cy=msg.k[5],
                width=msg.width, height=msg.height,
            )

    # ── inference + projection ──────────────────────────────────────────────

    def _run_inference(self):
        if not self._inference_lock.acquire(blocking=False):
            return  # previous inference still running
        try:
            with self._lock:
                rgb = self._latest_rgb
                rgb_header = self._latest_rgb_header
                depth = self._latest_depth
                intr = self._intrinsics

            if rgb is None or depth is None or intr is None or rgb_header is None:
                return

            detections = self._detect(rgb)
            if not detections:
                return

            self._project_and_update(detections, depth, intr, rgb_header)
            self._publish_detections(detections, rgb_header)
        finally:
            self._inference_lock.release()

    def _detect(self, rgb: np.ndarray) -> list[dict]:
        """Returns [{label, score, cx, cy, w_px, h_px}] in pixel coords."""
        import torch
        from groundingdino.util.inference import predict
        import groundingdino.datasets.transforms as T
        from PIL import Image as PILImage

        # GroundingDINO's predict() wants a transformed tensor.
        transform = T.Compose([
            T.RandomResize([800], max_size=1333),
            T.ToTensor(),
            T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
        pil = PILImage.fromarray(rgb)
        image_tensor, _ = transform(pil, None)

        with torch.no_grad():
            boxes, logits, phrases = predict(
                model=self._gdino_model,
                image=image_tensor,
                caption=self._caption,
                box_threshold=self._box_thresh,
                text_threshold=self._text_thresh,
                device=self._device,
            )

        h, w = rgb.shape[:2]
        out = []
        for box, score, phrase in zip(boxes, logits, phrases):
            # box is [cx, cy, w, h] normalized to [0, 1]
            cx_n, cy_n, bw_n, bh_n = box.tolist()
            cx = int(cx_n * w)
            cy = int(cy_n * h)
            bw = int(bw_n * w)
            bh = int(bh_n * h)
            label = phrase.strip().lower()
            if not label:
                continue
            out.append({
                'label': label,
                'score': float(score),
                'cx': cx, 'cy': cy,
                'w_px': bw, 'h_px': bh,
            })
        return out

    def _project_and_update(
        self,
        detections: list[dict],
        depth: np.ndarray,
        intr: CameraIntrinsics,
        rgb_header,
    ):
        # TF lookup at "latest available" via Time() (epoch zero). tf2_ros
        # interprets a zero-stamp lookup as "give me the most recent transform"
        # regardless of clock source. This sidesteps sim-time vs wall-time
        # mismatches and the RGB-stamp-vs-buffer-stamp races we hit with the
        # exact-time approach.
        camera_frame = rgb_header.frame_id
        try:
            tf = self._tf_buffer.lookup_transform(
                self._map_frame, camera_frame,
                rclpy.time.Time(),
                timeout=rclpy.duration.Duration(seconds=0.5))
        except TransformException as e:
            self.get_logger().warn(
                f'TF lookup {camera_frame} -> {self._map_frame} failed: {e}')
            return

        depth_h, depth_w = depth.shape[:2]
        for det in detections:
            # Sample depth in the depth image's own resolution: the aligned
            # depth image may be published at a different size than the RGB
            # feed the intrinsics describe.
            u_d, v_d = scale_pixel(
                det['cx'], det['cy'], intr.width, intr.height, depth_w, depth_h)
            z = sample_depth(
                depth, u_d, v_d,
                min_depth=self._min_depth, max_depth=self._max_depth)
            if z is None:
                continue
            # Unproject in the RGB/camera_info pixel space using the matching
            # intrinsics, never the depth-scaled coords with RGB intrinsics.
            x_cam, y_cam, z_cam = unproject(
                det['cx'], det['cy'], z,
                intr.fx, intr.fy, intr.cx, intr.cy)
            point = PointStamped()
            point.header = rgb_header
            point.point.x = x_cam
            point.point.y = y_cam
            point.point.z = z_cam
            try:
                point_map = do_transform_point(point, tf)
            except Exception as e:
                self.get_logger().warn(f'point transform failed: {e}')
                continue
            self._semantic_map.update(
                det['label'], point_map.point.x, point_map.point.y, det['score'])

    # ── publishing ──────────────────────────────────────────────────────────

    def _publish_map(self):
        if len(self._semantic_map) == 0:
            return
        msg = String()
        msg.data = json.dumps(self._semantic_map.to_dict())
        self._map_pub.publish(msg)

    def _publish_detections(self, detections: list[dict], header):
        msg = String()
        msg.data = json.dumps({
            'stamp_sec': header.stamp.sec,
            'detections': detections,
        })
        self._detections_pub.publish(msg)


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


if __name__ == '__main__':
    main()
