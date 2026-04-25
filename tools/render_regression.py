#!/usr/bin/env python3
"""端到端渲染回归工具 — 对比 baseline（平坦材质）与 enhanced（PBR 纹理）渲染输出。

用法:
    python tools/render_regression.py
    python tools/render_regression.py --dry-run   # 仅做前置检查，不运行 Blender
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# ── 路径常量 ──────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).parent.parent.resolve()

# render_3d.py 和 render_config.py 都在这里
_EE_DIR = _REPO_ROOT / "cad" / "end_effector"
_RENDER_SCRIPT = _EE_DIR / "render_3d.py"

# render_3d.py 默认读取此 GLB 作为场景输入
_GLB_PATH = _REPO_ROOT / "cad" / "output" / "EE-000_assembly.glb"

# 产物根目录
_OUT_ROOT = _REPO_ROOT / "artifacts" / "regression"

# render_config.MATERIAL_PRESETS 需要从子目录导入
sys.path.insert(0, str(_EE_DIR))
sys.path.insert(0, str(_REPO_ROOT))

VIEW_NAMES = [
    "V1_front_iso",
    "V2_rear_oblique",
    "V3_side_elevation",
    "V4_exploded",
    "V5_ortho_front",
]


def _find_blender() -> str:
    """优先 PATH 中的 blender，fallback D:\\Blender\\blender.exe。

    Returns:
        可用 blender 可执行文件的绝对路径字符串。

    Raises:
        FileNotFoundError: 两处均未找到。
    """
    blender_in_path = shutil.which("blender")
    if blender_in_path:
        return blender_in_path

    fallback = Path(r"D:\Blender\blender.exe")
    if fallback.exists():
        return str(fallback)

    raise FileNotFoundError(
        "找不到 Blender 可执行文件。\n"
        "请将 blender 加入 PATH，或确认 D:\\Blender\\blender.exe 存在。"
    )
