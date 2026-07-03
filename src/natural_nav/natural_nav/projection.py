"""
Pixel-to-3D projection helpers.

Deliberately free of ROS and torch imports so the geometry — the part most
likely to carry a silent bug — can be unit-tested on a plain Python host
without the GPU sim. semantic_detector imports these; the test suite exercises
them directly.

Conventions follow the standard camera *optical* frame (REP 103): x right,
y down, z forward along the view axis. Depth is metric along z.
"""

from __future__ import annotations

import numpy as np


def sample_depth(
    depth: np.ndarray,
    u: int,
    v: int,
    window: int = 5,
    min_depth: float = 0.3,
    max_depth: float = 8.0,
) -> float | None:
    """Robust metric depth at (u, v).

    A single center pixel is a bad estimator: in sim (and on real depth
    sensors) it is frequently 0/NaN at object edges, thin structures, or
    reflective surfaces, which would silently drop the detection. Instead take
    the median of the finite, in-range depths in a small window centered on
    (u, v).

    (u, v) are pixel coordinates in `depth`'s own resolution. Returns None when
    no valid sample exists in the window.
    """
    h, w = depth.shape[:2]
    if not (0 <= u < w and 0 <= v < h):
        return None

    half = window // 2
    u0, u1 = max(0, u - half), min(w, u + half + 1)
    v0, v1 = max(0, v - half), min(h, v + half + 1)
    patch = depth[v0:v1, u0:u1].astype(np.float32).ravel()

    valid = patch[np.isfinite(patch) & (patch >= min_depth) & (patch <= max_depth)]
    if valid.size == 0:
        return None
    return float(np.median(valid))


def unproject(
    u: float,
    v: float,
    z: float,
    fx: float,
    fy: float,
    cx: float,
    cy: float,
) -> tuple[float, float, float]:
    """Back-project pixel (u, v) at metric depth z to a point in the camera
    optical frame via the pinhole model.

    (u, v) and (cx, cy) must live in the *same* pixel space — i.e. unproject
    with the intrinsics that match the coordinates you pass, not a rescaled
    copy. semantic_detector samples depth in the depth image's resolution but
    unprojects in the camera_info (RGB) resolution, keeping this consistent.
    """
    x = (u - cx) * z / fx
    y = (v - cy) * z / fy
    return (x, y, z)


def scale_pixel(
    u: float,
    v: float,
    src_w: int,
    src_h: int,
    dst_w: int,
    dst_h: int,
) -> tuple[int, int]:
    """Map a pixel from one image resolution to another (e.g. RGB -> depth when
    an aligned depth image is published at a different size). No-op when the
    resolutions already match."""
    if src_w == dst_w and src_h == dst_h:
        return int(round(u)), int(round(v))
    return (
        int(round(u * dst_w / src_w)),
        int(round(v * dst_h / src_h)),
    )
