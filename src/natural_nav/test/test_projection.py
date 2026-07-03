"""
Geometry tests for natural_nav.projection.

Pure numpy — no ROS, no torch, no GPU sim — so the depth-to-3D math that
semantic_detector relies on is actually exercised in CI and on a dev host.
Runs under colcon test and standalone: `python3 -m pytest test/test_projection.py`.
"""

import math
import os
import sys

import numpy as np
import pytest

# Allow standalone runs (no installed package) by putting the package src on path.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from natural_nav.projection import sample_depth, unproject, scale_pixel  # noqa: E402


# A plausible OAK-D-ish intrinsic set for a 640x480 image.
FX = FY = 500.0
CX, CY = 320.0, 240.0


def test_unproject_optical_axis():
    # A pixel at the principal point maps onto the optical axis: x = y = 0.
    x, y, z = unproject(CX, CY, 2.5, FX, FY, CX, CY)
    assert x == pytest.approx(0.0)
    assert y == pytest.approx(0.0)
    assert z == pytest.approx(2.5)


def test_unproject_signs_follow_optical_frame():
    # Optical frame: +x right, +y down. A pixel right-and-below center at
    # depth z gives +x, +y.
    z = 3.0
    x, y, _ = unproject(CX + 100, CY + 50, z, FX, FY, CX, CY)
    assert x == pytest.approx(100 * z / FX)   # 0.6
    assert y == pytest.approx(50 * z / FY)    # 0.3
    assert x > 0 and y > 0


def test_unproject_roundtrip_through_projection():
    # Project a known 3D point to a pixel, then unproject it back.
    px, py, pz = 0.4, -0.25, 2.0
    u = px * FX / pz + CX
    v = py * FY / pz + CY
    x, y, z = unproject(u, v, pz, FX, FY, CX, CY)
    assert (x, y, z) == pytest.approx((px, py, pz))


def test_sample_depth_median_ignores_holes():
    depth = np.full((480, 640), 4.0, dtype=np.float32)
    # Punch NaN / zero holes (edge & reflection artifacts) around the center.
    depth[240, 320] = np.nan
    depth[239, 319] = 0.0
    depth[241, 321] = np.inf
    z = sample_depth(depth, 320, 240, window=5)
    assert z == pytest.approx(4.0)


def test_sample_depth_center_hole_recovered_from_neighbors():
    depth = np.zeros((480, 640), dtype=np.float32)  # mostly invalid
    depth[240, 320] = np.nan                        # dead center is a hole
    depth[238:243, 318:323] = 3.2                   # but the neighborhood is good
    depth[240, 320] = np.nan
    z = sample_depth(depth, 320, 240, window=5)
    assert z == pytest.approx(3.2)


def test_sample_depth_all_invalid_returns_none():
    depth = np.zeros((480, 640), dtype=np.float32)  # everything below min_depth
    assert sample_depth(depth, 320, 240, window=5, min_depth=0.3) is None


def test_sample_depth_respects_range():
    depth = np.full((480, 640), 50.0, dtype=np.float32)  # everything too far
    assert sample_depth(depth, 320, 240, max_depth=8.0) is None


def test_sample_depth_out_of_bounds_returns_none():
    depth = np.full((10, 10), 2.0, dtype=np.float32)
    assert sample_depth(depth, 999, 999) is None


def test_scale_pixel_noop_when_matched():
    assert scale_pixel(320, 240, 640, 480, 640, 480) == (320, 240)


def test_scale_pixel_downscales():
    # RGB 640x480 pixel -> aligned depth at 320x240 halves the coordinates.
    assert scale_pixel(320, 240, 640, 480, 320, 240) == (160, 120)


def test_end_to_end_center_object_at_two_meters():
    # Full detector path in miniature: object centered in the frame at 2 m
    # should unproject to a point straight ahead on the optical axis.
    depth = np.full((480, 640), 2.0, dtype=np.float32)
    u_d, v_d = scale_pixel(CX, CY, 640, 480, 640, 480)
    z = sample_depth(depth, u_d, v_d)
    x, y, zc = unproject(CX, CY, z, FX, FY, CX, CY)
    assert math.hypot(x, y) == pytest.approx(0.0, abs=1e-6)
    assert zc == pytest.approx(2.0)


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
