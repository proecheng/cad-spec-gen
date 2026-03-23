#!/usr/bin/env python3
"""
Build All — One-click STEP + DXF generation for the end effector.

Usage:
    python cad/end_effector/build_all.py
    python cad/end_effector/build_all.py --render
    python cad/end_effector/build_all.py --dry-run

Output:
    cad/output/EE-001_flange_al.step      (+ 7 more STEP files)
    cad/output/EE-001-01_flange.dxf       (+ 10 more DXF three-view sheets)
"""

import logging
import os
import subprocess
import sys
import time
import traceback

# Ensure imports work from any CWD
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cadquery as cq

log = logging.getLogger("build_all")

OUTPUT_DIR = os.environ.get(
    "CAD_OUTPUT_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output")
)


# ── Build step definitions (declarative) ─────────────────────────────────────

_STEP_BUILDS = [
    ("flange",       "flange",              "make_flange_al",     "EE-001_flange_al.step"),
    ("peek ring",    "flange",              "make_peek_ring",     "EE-001_flange_peek.step"),
    ("station 1",    "station1_applicator", "make_applicator",    "EE-002_station1_applicator.step"),
    ("station 2",    "station2_ae",         "make_ae_module",     "EE-003_station2_ae.step"),
    ("station 3",    "station3_cleaner",    "make_cleaner",       "EE-004_station3_cleaner.step"),
    ("station 4",    "station4_uhf",        "make_uhf_module",    "EE-005_station4_uhf.step"),
    ("drive",        "drive_assembly",      "make_drive_assembly","EE-006_drive.step"),
]

_DXF_BUILDS = [
    ("flange",         "draw_flange",      "draw_flange_sheet"),
    ("peek ring",      "draw_peek_ring",   "draw_peek_ring_sheet"),
    ("adapter",        "draw_drive",       "draw_adapter_sheet"),
    ("applicator",     "draw_station1",    "draw_applicator_sheet"),
    ("spring limiter", "draw_station2_ae", "draw_spring_limiter_sheet"),
    ("gimbal",         "draw_station2_ae", "draw_gimbal_sheet"),
    ("cleaner body",   "draw_station3",    "draw_cleaner_body_sheet"),
    ("flap",           "draw_station3",    "draw_flap_sheet"),
    ("uhf bracket",    "draw_station4",    "draw_uhf_bracket_sheet"),
    ("sig shell",      "draw_signal_cond", "draw_sig_shell_sheet"),
    ("sig bracket",    "draw_signal_cond", "draw_sig_bracket_sheet"),
]


def _build_step(label, module_name, func_name, filename):
    """Build a single STEP file. Returns path on success, None on failure."""
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
    """Build a single DXF sheet. Returns path on success, None on failure."""
    log.info("Drawing %s...", label)
    try:
        mod = __import__(module_name)
        func = getattr(mod, func_name)
        return func(OUTPUT_DIR)
    except Exception:
        log.error("FAILED drawing %s:\n%s", label, traceback.format_exc())
        return None


def build_all(dry_run=False):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    t0 = time.time()
    results = []
    failures = []

    if dry_run:
        log.info("DRY RUN — validating imports only")

    # ═══ 3D STEP models ═══
    for label, mod, func, fname in _STEP_BUILDS:
        if dry_run:
            try:
                __import__(mod)
                log.info("  OK: %s.%s importable", mod, func)
            except ImportError as e:
                log.error("  FAIL: cannot import %s — %s", mod, e)
                failures.append(label)
            continue

        p = _build_step(label, mod, func, fname)
        if p:
            results.append(p)
        else:
            failures.append(label)

    # Full assembly
    if not dry_run:
        log.info("Building full assembly...")
        try:
            from assembly import export_assembly
            p = export_assembly(OUTPUT_DIR)
            results.append(p)
        except Exception:
            log.error("FAILED building assembly:\n%s", traceback.format_exc())
            failures.append("assembly")

    # ═══ GB/T 三视图 DXF engineering drawings ═══
    log.info("Generating GB/T three-view DXF drawings...")
    dxf_files = []
    for label, mod, func in _DXF_BUILDS:
        if dry_run:
            try:
                __import__(mod)
                log.info("  OK: %s.%s importable", mod, func)
            except ImportError as e:
                log.error("  FAIL: cannot import %s — %s", mod, e)
                failures.append(f"dxf:{label}")
            continue

        p = _build_dxf(label, mod, func)
        if p:
            dxf_files.append(p)
        else:
            failures.append(f"dxf:{label}")

    if dry_run:
        if failures:
            log.warning("Dry run found %d import errors", len(failures))
            return 1
        log.info("Dry run OK — all modules importable")
        return 0

    elapsed = time.time() - t0
    log.info("=" * 60)
    log.info("  Build complete in %.1fs", elapsed)
    log.info("  %d STEP + %d DXF generated, %d failures",
             len(results), len(dxf_files), len(failures))
    for r in results:
        size_kb = os.path.getsize(r) / 1024
        log.info("    %-40s %6.1f KB", os.path.basename(r), size_kb)
    for d in dxf_files:
        size_kb = os.path.getsize(d) / 1024
        log.info("    %-40s %6.1f KB", os.path.basename(d), size_kb)
    if failures:
        log.error("  FAILED steps: %s", ", ".join(failures))
    log.info("=" * 60)

    return 1 if failures else 0


def _find_blender():
    """Locate Blender executable via env var or well-known paths."""
    candidates = [
        os.environ.get("BLENDER_PATH", ""),
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "..", "..", "tools", "blender", "blender.exe"),
        "D:/cad-skill/tools/blender/blender.exe",
    ]
    for c in candidates:
        c = os.path.normpath(c) if c else ""
        if c and os.path.isfile(c):
            return c
    return None


def run_blender(script, extra_args, blender_path):
    """Run a Blender script as subprocess with error capture."""
    cmd = [blender_path, "-b", "-P", script, "--"] + extra_args
    log.info("  Running: %s", " ".join(os.path.basename(c) for c in cmd[:5]))
    try:
        result = subprocess.run(
            cmd, check=True, capture_output=True, text=True, timeout=600,
        )
        # Print stdout (Blender output) at debug level
        if result.stdout:
            for line in result.stdout.strip().split("\n")[-5:]:
                log.debug("  blender: %s", line)
        return True
    except subprocess.CalledProcessError as e:
        log.error("Blender script failed (exit code %d): %s", e.returncode, script)
        if e.stderr:
            for line in e.stderr.strip().split("\n")[-10:]:
                log.error("  stderr: %s", line)
        return False
    except subprocess.TimeoutExpired:
        log.error("Blender script timed out (600s): %s", script)
        return False


if __name__ == "__main__":
    # ── Logging setup ──
    level = logging.DEBUG if "--verbose" in sys.argv else logging.INFO
    if "--quiet" in sys.argv:
        level = logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    dry_run = "--dry-run" in sys.argv
    exit_code = build_all(dry_run=dry_run)

    # ═══ Optional: Blender Cycles rendering ═══
    if "--render" in sys.argv and not dry_run:
        blender = _find_blender()
        if not blender:
            log.error("Blender not found. Set BLENDER_PATH or install to tools/blender/")
            sys.exit(1)
        log.info("Blender: %s", blender)

        SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
        render_script = os.path.join(SCRIPT_DIR, "render_3d.py")
        exploded_script = os.path.join(SCRIPT_DIR, "render_exploded.py")
        config_path = os.path.join(SCRIPT_DIR, "render_config.json")

        log.info("=" * 60)
        log.info("  Blender Cycles rendering...")
        log.info("=" * 60)

        # Build render args — use config if it exists
        render_args = ["--all"]
        explode_args = []
        if os.path.isfile(config_path):
            render_args = ["--config", config_path, "--all"]
            explode_args = ["--config", config_path]
            log.info("  Using config: %s", config_path)

        # Standard views (V1, V2, V3, V5)
        ok1 = run_blender(render_script, render_args, blender)
        # Exploded view (V4)
        ok2 = run_blender(exploded_script, explode_args, blender)

        if ok1 and ok2:
            log.info("All renders complete. Check cad/output/renders/")
        else:
            log.error("Some renders failed. Check logs above.")
            exit_code = 1

    sys.exit(exit_code)
