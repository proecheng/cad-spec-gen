"""Tests for `_resolve_camera_coords()` 球坐标→笛卡尔数学（v2.9.2 Tier 1）。

该函数位于 `cad_pipeline.py:94`，在 enhance / render 阶段把 render_config.json
中的相机条目（`azimuth_deg` / `elevation_deg` / `distance_factor`）就地转换成
`location` / `target` 笛卡尔对。它是**纯数学无 bpy 依赖**，可在标准 Python
进程内单测。

v2.9.2 锁在以下行为上：
- 已知角度 → 已知笛卡尔坐标（0°/90° 轴对齐 case）
- `subsystem.bounding_radius_mm` 缺失时 fallback 到 300
- 已预设 `location` 的相机不应被覆盖（幂等性）
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_azimuth_zero_elevation_zero_puts_camera_on_positive_x():
    """az=0, el=0 → 相机应落在 +X 轴上，距离 = bounding_radius × distance_factor。"""
    from cad_pipeline import _resolve_camera_coords

    rc = {
        "subsystem": {"name": "test", "bounding_radius_mm": 100.0},
        "camera": {
            "V1": {"azimuth_deg": 0, "elevation_deg": 0, "distance_factor": 2.0},
        },
    }
    _resolve_camera_coords(rc)
    cam = rc["camera"]["V1"]
    loc = cam["location"]
    tgt = cam["target"]

    # 预期：dist = 100 × 2.0 = 200；target = [0, 0, 100 × 0.33] = [0, 0, 33]
    # location = [dist × cos(0) × cos(0) + 0, dist × cos(0) × sin(0) + 0, dist × sin(0) + 33]
    #          = [200, 0, 33]
    assert abs(loc[0] - 200.0) < 0.01
    assert abs(loc[1] - 0.0) < 0.01
    assert abs(loc[2] - 33.0) < 0.01
    # target 默认 [0, 0, br × 0.33]
    assert abs(tgt[2] - 33.0) < 0.01


def test_azimuth_90_puts_camera_on_positive_y():
    """az=90°, el=0 → 相机应落在 +Y 轴上（sin(90°)=1, cos(90°)=0）。"""
    from cad_pipeline import _resolve_camera_coords

    rc = {
        "subsystem": {"bounding_radius_mm": 100.0},
        "camera": {
            "V2": {"azimuth_deg": 90, "elevation_deg": 0, "distance_factor": 1.0},
        },
    }
    _resolve_camera_coords(rc)
    loc = rc["camera"]["V2"]["location"]

    # dist = 100; x = dist × cos(0) × cos(90°) = 0
    # y = dist × cos(0) × sin(90°) = 100
    # z = dist × sin(0) + 33 = 33
    assert abs(loc[0] - 0.0) < 0.01
    assert abs(loc[1] - 100.0) < 0.01
    assert abs(loc[2] - 33.0) < 0.01


def test_elevation_90_puts_camera_straight_above():
    """az=*, el=90° → 相机正上方（cos(90°)=0, sin(90°)=1）。"""
    from cad_pipeline import _resolve_camera_coords

    rc = {
        "subsystem": {"bounding_radius_mm": 100.0},
        "camera": {
            "V_top": {"azimuth_deg": 0, "elevation_deg": 90, "distance_factor": 1.0},
        },
    }
    _resolve_camera_coords(rc)
    loc = rc["camera"]["V_top"]["location"]

    # cos(90°) = 0 → x = y = 0；z = dist × sin(90°) + target_z = 100 + 33 = 133
    assert abs(loc[0] - 0.0) < 0.01
    assert abs(loc[1] - 0.0) < 0.01
    assert abs(loc[2] - 133.0) < 0.01


def test_missing_bounding_radius_falls_back_to_default():
    """subsystem.bounding_radius_mm 缺失时应 fallback 到 300（代码硬编码默认值）。"""
    from cad_pipeline import _resolve_camera_coords

    rc = {
        "subsystem": {"name": "no_radius"},  # bounding_radius_mm 缺失
        "camera": {
            "V1": {"azimuth_deg": 0, "elevation_deg": 0, "distance_factor": 1.0},
        },
    }
    _resolve_camera_coords(rc)
    loc = rc["camera"]["V1"]["location"]

    # Fallback br = 300, dist = 300 × 1.0 = 300; loc[0] = 300
    assert abs(loc[0] - 300.0) < 0.01


def test_existing_location_not_overwritten():
    """若相机条目已有 `location`，`_resolve_camera_coords` 不应覆盖它（幂等性）。"""
    from cad_pipeline import _resolve_camera_coords

    rc = {
        "subsystem": {"bounding_radius_mm": 100.0},
        "camera": {
            "V1": {
                "azimuth_deg": 0,
                "elevation_deg": 0,
                "location": [999, 888, 777],
                "target": [1, 2, 3],
            },
        },
    }
    _resolve_camera_coords(rc)
    cam = rc["camera"]["V1"]

    assert cam["location"] == [999, 888, 777]


def test_multiple_cameras_resolved_independently():
    """多相机条目应各自独立解析，不互相污染。"""
    from cad_pipeline import _resolve_camera_coords

    rc = {
        "subsystem": {"bounding_radius_mm": 100.0},
        "camera": {
            "V1": {"azimuth_deg": 0, "elevation_deg": 0, "distance_factor": 1.0},
            "V2": {"azimuth_deg": 90, "elevation_deg": 0, "distance_factor": 1.0},
        },
    }
    _resolve_camera_coords(rc)

    v1 = rc["camera"]["V1"]["location"]
    v2 = rc["camera"]["V2"]["location"]

    assert abs(v1[0] - 100.0) < 0.01  # +X
    assert abs(v1[1] - 0.0) < 0.01
    assert abs(v2[0] - 0.0) < 0.01  # +Y
    assert abs(v2[1] - 100.0) < 0.01
