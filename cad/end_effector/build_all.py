#!/usr/bin/env python3
"""
Build All — One-click STEP + DXF generation for 末端执行机构.

Auto-generated scaffold by codegen/gen_build.py
Source: D:\Work\cad-spec-gen\cad\end_effector\CAD_SPEC.md
Generated: 2026-04-03 20:15

Usage:
    python cad/end_effector/build_all.py
    python cad/end_effector/build_all.py --render
    python cad/end_effector/build_all.py --dry-run
    python cad/end_effector/build_all.py --render --timestamp
"""

import logging
import os
import subprocess
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cadquery as cq

log = logging.getLogger("build_all")

OUTPUT_DIR = os.environ.get(
    "CAD_OUTPUT_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output")
)


# ── Build step definitions (declarative) ─────────────────────────────────────

_STEP_BUILDS = [
]

_DXF_BUILDS = [
    ("法兰本体", "ee_001_01", "draw_ee_001_01_sheet"),
    ("PEEK绝缘段", "ee_001_02", "draw_ee_001_02_sheet"),
    ("ISO 9409适配板", "ee_001_08", "draw_ee_001_08_sheet"),
    ("涂抹模块壳体", "ee_002_01", "draw_ee_002_01_sheet"),
    ("弹簧限力机构总成", "ee_003_03", "draw_ee_003_03_sheet"),
    ("柔性关节", "ee_003_04", "draw_ee_003_04_sheet"),
    ("清洁模块壳体", "ee_004_01", "draw_ee_004_01_sheet"),
    ("清洁窗口翻盖", "ee_004_12", "draw_ee_004_12_sheet"),
    ("UHF安装支架", "ee_005_02", "draw_ee_005_02_sheet"),
    ("壳体", "ee_006_01", "draw_ee_006_01_sheet"),
    ("安装支架", "ee_006_03", "draw_ee_006_03_sheet"),
]

_STD_STEP_BUILDS = [
    ("[标准件] O型圈", "std_ee_001_03", "make_std_ee_001_03", "GIS-EE-001-03_std.step"),
    ("[标准件] 碟形弹簧垫圈", "std_ee_001_04", "make_std_ee_001_04", "GIS-EE-001-04_std.step"),
    ("[标准件] 伺服电机", "std_ee_001_05", "make_std_ee_001_05", "GIS-EE-001-05_std.step"),
    ("[标准件] 行星减速器", "std_ee_001_06", "make_std_ee_001_06", "GIS-EE-001-06_std.step"),
    ("[标准件] 弹簧销组件", "std_ee_001_07", "make_std_ee_001_07", "GIS-EE-001-07_std.step"),
    ("[标准件] FFC线束总成", "std_ee_001_09", "make_std_ee_001_09", "GIS-EE-001-09_std.step"),
    ("[标准件] ZIF连接器", "std_ee_001_10", "make_std_ee_001_10", "GIS-EE-001-10_std.step"),
    ("[标准件] 储罐", "std_ee_002_02", "make_std_ee_002_02", "GIS-EE-002-02_std.step"),
    ("[标准件] 齿轮泵", "std_ee_002_03", "make_std_ee_002_03", "GIS-EE-002-03_std.step"),
    ("[标准件] LEMO插头", "std_ee_002_05", "make_std_ee_002_05", "GIS-EE-002-05_std.step"),
    ("[标准件] AE传感器", "std_ee_003_01", "make_std_ee_003_01", "GIS-EE-003-01_std.step"),
    ("[标准件] 六轴力传感器", "std_ee_003_02", "make_std_ee_003_02", "GIS-EE-003-02_std.step"),
    ("[标准件] LEMO插头", "std_ee_003_08", "make_std_ee_003_08", "GIS-EE-003-08_std.step"),
    ("[标准件] 微型电机", "std_ee_004_03", "make_std_ee_004_03", "GIS-EE-004-03_std.step"),
    ("[标准件] 齿轮减速组", "std_ee_004_04", "make_std_ee_004_04", "GIS-EE-004-04_std.step"),
    ("[标准件] 恒力弹簧", "std_ee_004_06", "make_std_ee_004_06", "GIS-EE-004-06_std.step"),
    ("[标准件] 溶剂储罐", "std_ee_004_08", "make_std_ee_004_08", "GIS-EE-004-08_std.step"),
    ("[标准件] 微量泵", "std_ee_004_09", "make_std_ee_004_09", "GIS-EE-004-09_std.step"),
    ("[标准件] 微型轴承", "std_ee_004_11", "make_std_ee_004_11", "GIS-EE-004-11_std.step"),
    ("[标准件] LEMO插头", "std_ee_004_13", "make_std_ee_004_13", "GIS-EE-004-13_std.step"),
    ("[标准件] I300-UHF-GT传感器", "std_ee_005_01", "make_std_ee_005_01", "GIS-EE-005-01_std.step"),
    ("[标准件] LEMO插头", "std_ee_005_03", "make_std_ee_005_03", "GIS-EE-005-03_std.step"),
    ("[标准件] LEMO插座", "std_ee_006_04", "make_std_ee_006_04", "GIS-EE-006-04_std.step"),
    ("[标准件] SMA穿壁连接器", "std_ee_006_05", "make_std_ee_006_05", "GIS-EE-006-05_std.step"),
]


def _build_step(label, module_name, func_name, filename):
    """Build a single STEP file."""
    log.info("Building %s...", label)
    try:
        mod = __import__(module_name)
        func = getattr(mod, func_name)
        solid = func()
        p = os.path.join(OUTPUT_DIR, filename)
        cq.exporters.export(solid, p)
        return p
    except Exception:
        log.error("FAILED building %s:\n%s", label, traceback.format_exc())
        return None


def _build_dxf(label, module_name, func_name):
    """Build a single DXF sheet."""
    log.info("Drawing %s...", label)
    try:
        mod = __import__(module_name)
        func = getattr(mod, func_name)
        path = func(OUTPUT_DIR)
        return path
    except Exception:
        log.error("FAILED drawing %s:\n%s", label, traceback.format_exc())
        return None


def build_all(render: bool = False, dry_run: bool = False, timestamp: bool = False):
    """Run the full build."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                        datefmt="%H:%M:%S")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if dry_run:
        log.info("DRY RUN — validating imports only")
        for label, mod_name, func_name, _ in _STEP_BUILDS:
            mod = __import__(mod_name)
            assert hasattr(mod, func_name), f"{mod_name}.{func_name} not found"
            log.info("  OK: %s.%s", mod_name, func_name)
        for label, mod_name, func_name, _ in _STD_STEP_BUILDS:
            mod = __import__(mod_name)
            assert hasattr(mod, func_name), f"{mod_name}.{func_name} not found"
            log.info("  OK: %s.%s (std)", mod_name, func_name)
        log.info("All %d STEP + %d STD + %d DXF targets validated",
                 len(_STEP_BUILDS), len(_STD_STEP_BUILDS), len(_DXF_BUILDS))
        return

    # Build STEP files
    step_results = []
    for args in _STEP_BUILDS:
        r = _build_step(*args)
        step_results.append(r)

    # Build standard part STEP files
    std_results = []
    for args in _STD_STEP_BUILDS:
        r = _build_step(*args)
        std_results.append(r)

    # Build DXF files
    dxf_results = []
    for args in _DXF_BUILDS:
        r = _build_dxf(*args)
        dxf_results.append(r)

    # Assembly
    from assembly import export_assembly
    export_assembly(OUTPUT_DIR)

    # Summary
    ok_step = sum(1 for r in step_results if r)
    ok_std = sum(1 for r in std_results if r)
    ok_dxf = sum(1 for r in dxf_results if r)
    log.info("=" * 60)
    log.info("  STEP: %d/%d OK", ok_step, len(_STEP_BUILDS))
    log.info("  STD:  %d/%d OK", ok_std, len(_STD_STEP_BUILDS))
    log.info("  DXF:  %d/%d OK", ok_dxf, len(_DXF_BUILDS))
    for r in step_results + std_results + dxf_results:
        if r:
            size_kb = os.path.getsize(r) / 1024
            log.info("    %-45s %7.1f KB", os.path.basename(r), size_kb)
    log.info("=" * 60)

    # Render
    if render:
        _run_render(timestamp)


def _run_render(timestamp: bool = False):
    """Invoke Blender rendering."""
    import json
    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "pipeline_config.json")
    if os.path.exists(config_path):
        with open(config_path, encoding="utf-8") as f:
            pcfg = json.load(f)
        blender = pcfg.get("blender_path", "blender")
    else:
        blender = "blender"

    script_dir = os.path.dirname(os.path.abspath(__file__))
    render_config = os.path.join(script_dir, "render_config.json")

    ts_args = ["--timestamp"] if timestamp else []

    # Standard views
    cmd = [blender, "-b", "-P", os.path.join(script_dir, "render_3d.py"),
           "--", "--config", render_config, "--all"] + ts_args
    log.info("Rendering standard views...")
    subprocess.run(cmd, check=True)

    # Exploded view
    cmd = [blender, "-b", "-P", os.path.join(script_dir, "render_exploded.py"),
           "--", "--config", render_config] + ts_args
    log.info("Rendering exploded view...")
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Build all STEP + DXF for 末端执行机构")
    parser.add_argument("--render", action="store_true", help="Also run Blender rendering")
    parser.add_argument("--dry-run", action="store_true", help="Validate imports only")
    parser.add_argument("--timestamp", action="store_true", help="Add timestamp to output filenames")
    args = parser.parse_args()
    build_all(render=args.render, dry_run=args.dry_run, timestamp=args.timestamp)
