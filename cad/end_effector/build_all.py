#!/usr/bin/env python3
"""
Build All — One-click STEP + DXF generation for 末端执行机构.

Auto-generated scaffold by codegen/gen_build.py
Source: D:\cad-skill\cad\end_effector\CAD_SPEC.md
Generated: 2026-03-24 22:51

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
    ("法兰总成", "part_001", "make_part_001", "EE-001.step"),
    ("工位1涂抹模块", "1", "make_1", "EE-002.step"),
    ("工位2 AE检测模块", "2_ae", "make_2_ae", "EE-003.step"),
    ("工位3卷带清洁模块", "3", "make_3", "EE-004.step"),
    ("工位4 UHF模块", "4_uhf", "make_4_uhf", "EE-005.step"),
    ("信号调理模块", "part_006", "make_part_006", "EE-006.step"),
]

_DXF_BUILDS = [
    ("法兰本体", "draw_part_001_01", "draw_part_001_01_sheet"),
    ("PEEK绝缘段", "draw_peek", "draw_peek_sheet"),
    ("ISO 9409适配板", "draw_iso_9409", "draw_iso_9409_sheet"),
    ("涂抹模块壳体", "draw_part_002_01", "draw_part_002_01_sheet"),
    ("弹簧限力机构总成", "draw_part_003_03", "draw_part_003_03_sheet"),
    ("柔性关节", "draw_part_003_04", "draw_part_003_04_sheet"),
    ("清洁模块壳体", "draw_part_004_01", "draw_part_004_01_sheet"),
    ("清洁窗口翻盖", "draw_part_004_12", "draw_part_004_12_sheet"),
    ("UHF安装支架", "draw_uhf", "draw_uhf_sheet"),
    ("壳体", "draw_part_006_01", "draw_part_006_01_sheet"),
    ("安装支架", "draw_part_006_03", "draw_part_006_03_sheet"),
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
        log.info("All %d STEP + %d DXF targets validated", len(_STEP_BUILDS), len(_DXF_BUILDS))
        return

    # Build STEP files
    step_results = []
    for args in _STEP_BUILDS:
        r = _build_step(*args)
        step_results.append(r)

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
    ok_dxf = sum(1 for r in dxf_results if r)
    log.info("=" * 60)
    log.info("  STEP: %d/%d OK", ok_step, len(_STEP_BUILDS))
    log.info("  DXF:  %d/%d OK", ok_dxf, len(_DXF_BUILDS))
    for r in step_results + dxf_results:
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
