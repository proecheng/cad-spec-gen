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


def run_render(output_dir: Path, extra_env: dict[str, str], dry_run: bool = False) -> bool:
    """调用 Blender 渲染 end_effector 全部 5 视图到 output_dir。

    Args:
        output_dir: PNG 输出目录（自动创建）。
        extra_env:  追加/覆写的环境变量 dict（叠加在 os.environ 上）。
        dry_run:    True 时只打印命令不执行，用于调试。

    Returns:
        True 表示渲染成功，False 表示 Blender 返回非零退出码。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    blender = _find_blender()

    cmd = [
        blender, "-b", "-P", str(_RENDER_SCRIPT),
        "--",
        "--all",
        "--glb", str(_GLB_PATH),
        "--output-dir", str(output_dir),
    ]

    env = {**os.environ, **extra_env}

    print(f"\n[render] 命令: {' '.join(cmd)}")
    print(f"[render] 输出目录: {output_dir}")
    for k, v in extra_env.items():
        print(f"[render] env {k}={v!r}")

    if dry_run:
        print("[render] --dry-run 模式，跳过实际渲染")
        return True

    result = subprocess.run(cmd, env=env, cwd=str(_REPO_ROOT))
    if result.returncode != 0:
        print(f"[render] ❌ Blender 退出码 {result.returncode}")
        return False
    print("[render] ✅ 渲染完成")
    return True


def build_baseline(out_root: Path, dry_run: bool = False) -> bool:
    """渲染 baseline 版本：SW_TEXTURES_DIR 置空，不注入 runtime presets。

    Args:
        out_root: artifacts/regression/ 根目录。
        dry_run:  传递给 run_render。

    Returns:
        True 表示渲染成功。
    """
    print("\n=== BASELINE 渲染（平坦材质）===")
    output_dir = out_root / "baseline" / "end_effector"
    extra_env: dict[str, str] = {"SW_TEXTURES_DIR": ""}
    return run_render(output_dir, extra_env, dry_run=dry_run)


def build_enhanced(out_root: Path, dry_run: bool = False) -> tuple[bool, str]:
    """渲染 enhanced 版本：注入 SW 纹理路径 + runtime_materials.json。

    Returns:
        (success: bool, textures_dir: str)  textures_dir 供 F2 断言使用。
    """
    from adapters.solidworks.sw_detect import detect_solidworks
    from adapters.solidworks.sw_texture_backfill import backfill_presets_for_sw
    from render_config import MATERIAL_PRESETS  # 已在 sys.path 中（_EE_DIR）

    print("\n=== ENHANCED 渲染（PBR 纹理）===")

    sw_info = detect_solidworks()
    textures_dir = getattr(sw_info, "textures_dir", "") or ""

    if not sw_info.installed:
        print("[enhanced] ⚠️  SolidWorks 未装机，enhanced 渲染将等同 baseline")
    elif not textures_dir:
        print("[enhanced] ⚠️  textures_dir 为空，纹理回填为 no-op")
    else:
        print(f"[enhanced] SW textures_dir: {textures_dir}")

    runtime_presets = backfill_presets_for_sw(MATERIAL_PRESETS, sw_info)

    enhanced_dir = out_root / "enhanced"
    enhanced_dir.mkdir(parents=True, exist_ok=True)
    json_path = enhanced_dir / "runtime_materials.json"
    json_path.write_text(json.dumps(runtime_presets, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[enhanced] runtime_materials.json → {json_path}")

    output_dir = enhanced_dir / "end_effector"
    extra_env: dict[str, str] = {
        "SW_TEXTURES_DIR": textures_dir,
        "CAD_RUNTIME_MATERIAL_PRESETS_JSON": str(json_path),
    }

    success = run_render(output_dir, extra_env, dry_run=dry_run)
    return success, textures_dir
