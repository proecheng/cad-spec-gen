#!/usr/bin/env python3
"""
cad_pipeline.py — Unified CLI for the CAD parametric pipeline.

Chains: build → render → enhance → annotate in correct order,
with error propagation, progress tracking, and --dry-run support.

Usage:
    python cad_pipeline.py build                         # STEP + DXF only
    python cad_pipeline.py build --render                # + Blender renders
    python cad_pipeline.py render --subsystem end_effector
    python cad_pipeline.py enhance --dir cad/output/renders
    python cad_pipeline.py annotate --config render_config.json --lang cn
    python cad_pipeline.py full --subsystem end_effector  # build+render+enhance+annotate
    python cad_pipeline.py status                         # show pipeline status
    python cad_pipeline.py env-check                      # environment validation

Examples:
    # Full pipeline for end_effector:
    python cad_pipeline.py full --subsystem end_effector

    # Dry-run (validate only, no actual builds):
    python cad_pipeline.py full --subsystem end_effector --dry-run

    # Render a single view:
    python cad_pipeline.py render --subsystem end_effector --view V1
"""

import argparse
import glob
import json
import logging
import os
import shutil
import subprocess
import sys
import time

log = logging.getLogger("cad_pipeline")

SKILL_ROOT = os.path.dirname(os.path.abspath(__file__))
CAD_DIR = os.path.join(SKILL_ROOT, "cad")
TOOLS_DIR = os.path.join(SKILL_ROOT, "tools")
DEFAULT_OUTPUT = os.environ.get("CAD_OUTPUT_DIR",
                                os.path.join(CAD_DIR, "output"))


def _find_blender():
    """Locate Blender executable."""
    candidates = [
        os.environ.get("BLENDER_PATH", ""),
        os.path.join(TOOLS_DIR, "blender", "blender.exe"),
        "D:/cad-skill/tools/blender/blender.exe",
    ]
    for c in candidates:
        c = os.path.normpath(c) if c else ""
        if c and os.path.isfile(c):
            return c
    return None


def _find_subsystem(name):
    """Resolve subsystem name to its directory."""
    d = os.path.join(CAD_DIR, name)
    if os.path.isdir(d):
        return d
    # Fuzzy match
    for entry in os.listdir(CAD_DIR):
        if name.lower() in entry.lower() and os.path.isdir(os.path.join(CAD_DIR, entry)):
            return os.path.join(CAD_DIR, entry)
    return None


def _run_subprocess(cmd, label, dry_run=False, timeout=600):
    """Run a subprocess with error capture. Returns (success, elapsed)."""
    if dry_run:
        log.info("  [DRY-RUN] Would run: %s", " ".join(cmd[:6]))
        return True, 0.0

    log.info("  Running: %s", label)
    t0 = time.time()
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
        elapsed = time.time() - t0
        if result.returncode != 0:
            log.error("  FAILED %s (exit %d, %.1fs)", label, result.returncode, elapsed)
            if result.stderr:
                for line in result.stderr.strip().split("\n")[-10:]:
                    log.error("    %s", line)
            return False, elapsed
        log.info("  OK: %s (%.1fs)", label, elapsed)
        return True, elapsed
    except subprocess.TimeoutExpired:
        log.error("  TIMEOUT %s (>%ds)", label, timeout)
        return False, timeout
    except FileNotFoundError as e:
        log.error("  NOT FOUND: %s", e)
        return False, 0.0


# ═════════════════════════════════════════════════════════════════════════════
# Commands
# ═════════════════════════════════════════════════════════════════════════════

def cmd_build(args):
    """Build STEP + DXF for a subsystem."""
    sub_dir = _find_subsystem(args.subsystem)
    if not sub_dir:
        log.error("Subsystem '%s' not found in %s", args.subsystem, CAD_DIR)
        return 1

    build_script = os.path.join(sub_dir, "build_all.py")
    if not os.path.isfile(build_script):
        log.error("No build_all.py found in %s", sub_dir)
        return 1

    cmd = [sys.executable, build_script]
    if args.render:
        cmd.append("--render")
    if args.dry_run:
        cmd.append("--dry-run")
    if args.verbose:
        cmd.append("--verbose")

    ok, elapsed = _run_subprocess(cmd, f"build_all.py ({args.subsystem})",
                                  timeout=1200)
    return 0 if ok else 1


def cmd_render(args):
    """Run Blender rendering for a subsystem."""
    blender = _find_blender()
    if not blender:
        log.error("Blender not found. Set BLENDER_PATH env var.")
        return 1

    sub_dir = _find_subsystem(args.subsystem)
    if not sub_dir:
        log.error("Subsystem '%s' not found", args.subsystem)
        return 1

    render_script = os.path.join(sub_dir, "render_3d.py")
    exploded_script = os.path.join(sub_dir, "render_exploded.py")
    config_path = os.path.join(sub_dir, "render_config.json")

    if not os.path.isfile(render_script):
        log.error("No render_3d.py in %s", sub_dir)
        return 1

    failures = 0
    render_args = []
    if os.path.isfile(config_path):
        render_args = ["--config", config_path]

    if args.view:
        # Single view
        if args.view.upper() == "V4" and os.path.isfile(exploded_script):
            cmd = [blender, "-b", "-P", exploded_script, "--"] + render_args
        else:
            cmd = [blender, "-b", "-P", render_script, "--"] + render_args + ["--view", args.view]
        ok, _ = _run_subprocess(cmd, f"render {args.view}", dry_run=args.dry_run, timeout=600)
        if not ok:
            failures += 1
    else:
        # All views
        cmd = [blender, "-b", "-P", render_script, "--"] + render_args + ["--all"]
        ok, _ = _run_subprocess(cmd, "render standard views", dry_run=args.dry_run, timeout=600)
        if not ok:
            failures += 1

        if os.path.isfile(exploded_script):
            cmd = [blender, "-b", "-P", exploded_script, "--"] + render_args
            ok, _ = _run_subprocess(cmd, "render exploded view", dry_run=args.dry_run, timeout=600)
            if not ok:
                failures += 1

    return 1 if failures else 0


def cmd_enhance(args):
    """Run Gemini AI enhancement on rendered PNGs."""
    gemini_script = os.environ.get("GEMINI_GEN_PATH", "D:/imageProduce/gemini_gen.py")
    if not os.path.isfile(gemini_script):
        log.error("gemini_gen.py not found at %s", gemini_script)
        log.error("Set GEMINI_GEN_PATH env var or install gemini_gen.py")
        return 1

    render_dir = args.dir or os.path.join(DEFAULT_OUTPUT, "renders")
    pngs = sorted(glob.glob(os.path.join(render_dir, "V*.png")))
    if not pngs:
        log.error("No V*.png files found in %s", render_dir)
        return 1

    # Load prompt template
    prompt_dir = os.path.join(TOOLS_DIR, "hybrid_render", "prompts")
    failures = 0

    for png in pngs:
        basename = os.path.basename(png).upper()
        if "V4" in basename:
            tmpl_file = os.path.join(prompt_dir, "prompt_exploded.txt")
        elif "V5" in basename:
            tmpl_file = os.path.join(prompt_dir, "prompt_ortho.txt")
        else:
            tmpl_file = os.path.join(prompt_dir, "prompt_enhance.txt")

        if os.path.isfile(tmpl_file):
            with open(tmpl_file, encoding="utf-8") as f:
                prompt = f.read().strip()
        else:
            prompt = ("Keep ALL geometry EXACTLY unchanged. Enhance surface materials "
                      "to photo-realistic quality with proper lighting and reflections.")

        cmd = [sys.executable, gemini_script, prompt, "--image", png]
        ok, _ = _run_subprocess(cmd, f"enhance {os.path.basename(png)}",
                                dry_run=args.dry_run, timeout=180)
        if not ok:
            failures += 1

    return 1 if failures else 0


def cmd_annotate(args):
    """Add component labels to enhanced images."""
    annotate_script = os.path.join(TOOLS_DIR, "annotate_render.py")
    if not os.path.isfile(annotate_script):
        log.error("annotate_render.py not found at %s", annotate_script)
        return 1

    sub_dir = _find_subsystem(args.subsystem)
    config_path = args.config
    if not config_path and sub_dir:
        config_path = os.path.join(sub_dir, "render_config.json")
    if not config_path or not os.path.isfile(config_path):
        log.error("No render_config.json found. Use --config or --subsystem.")
        return 1

    img_dir = args.dir or os.path.join(DEFAULT_OUTPUT, "renders")
    for lang in (args.lang.split(",") if "," in args.lang else [args.lang]):
        cmd = [sys.executable, annotate_script,
               "--all", "--dir", img_dir,
               "--config", config_path,
               "--lang", lang.strip()]
        ok, _ = _run_subprocess(cmd, f"annotate ({lang})", dry_run=args.dry_run)
        if not ok:
            return 1
    return 0


def cmd_full(args):
    """Full pipeline: build → render → enhance → annotate."""
    log.info("=" * 60)
    log.info("  Full pipeline for: %s", args.subsystem)
    log.info("=" * 60)
    t0 = time.time()

    steps = [
        ("BUILD", lambda: cmd_build(args)),
        ("RENDER", lambda: cmd_render(args)),
    ]
    if not args.skip_enhance:
        steps.append(("ENHANCE", lambda: cmd_enhance(args)))
    if not args.skip_annotate:
        steps.append(("ANNOTATE", lambda: cmd_annotate(args)))

    for i, (name, fn) in enumerate(steps, 1):
        log.info("\n[%d/%d] %s", i, len(steps), name)
        rc = fn()
        if rc != 0:
            log.error("Pipeline stopped at step %s (exit %d)", name, rc)
            return rc

    elapsed = time.time() - t0
    log.info("\n" + "=" * 60)
    log.info("  Full pipeline complete in %.1fs", elapsed)
    log.info("=" * 60)
    return 0


def cmd_status(args):
    """Show pipeline status for all subsystems."""
    log.info("=" * 60)
    log.info("  CAD Pipeline Status")
    log.info("=" * 60)

    for entry in sorted(os.listdir(CAD_DIR)):
        sub_dir = os.path.join(CAD_DIR, entry)
        if not os.path.isdir(sub_dir) or entry.startswith(".") or entry == "output":
            continue

        has_build = os.path.isfile(os.path.join(sub_dir, "build_all.py"))
        has_config = os.path.isfile(os.path.join(sub_dir, "render_config.json"))
        has_spec = os.path.isfile(os.path.join(sub_dir, "CAD_SPEC.md"))

        # Count outputs
        prefix = entry[:2].upper() if len(entry) >= 2 else ""
        steps = glob.glob(os.path.join(DEFAULT_OUTPUT, f"*{prefix}*.step"))
        dxfs = glob.glob(os.path.join(DEFAULT_OUTPUT, f"*{prefix}*.dxf"))
        render_dir = os.path.join(DEFAULT_OUTPUT, "renders")
        pngs = glob.glob(os.path.join(render_dir, "V*.png")) if os.path.isdir(render_dir) else []

        status = "spec-only"
        if has_build:
            status = "buildable"
        if steps:
            status = "built"
        if pngs:
            status = "rendered"

        icon = {"spec-only": "  ", "buildable": "  ", "built": "  ", "rendered": "  "}
        log.info("  %s %-25s [%s] build=%s config=%s STEP=%d DXF=%d PNG=%d",
                 icon.get(status, "?"), entry, status,
                 "Y" if has_build else "-",
                 "Y" if has_config else "-",
                 len(steps), len(dxfs), len(pngs))

    return 0


def cmd_env_check(args):
    """Environment validation."""
    check_script = os.path.join(TOOLS_DIR, "hybrid_render", "check_env.py")
    if os.path.isfile(check_script):
        ok, _ = _run_subprocess([sys.executable, check_script], "check_env.py")
        if ok:
            return 0

    # Inline checks
    log.info("=" * 60)
    log.info("  Environment Check")
    log.info("=" * 60)

    # Python
    log.info("  Python: %s", sys.version.split()[0])

    # CadQuery
    try:
        import cadquery
        log.info("  CadQuery: %s", cadquery.__version__)
    except ImportError:
        log.error("  CadQuery: NOT INSTALLED (pip install cadquery)")

    # ezdxf
    try:
        import ezdxf
        log.info("  ezdxf: %s", ezdxf.__version__)
    except ImportError:
        log.error("  ezdxf: NOT INSTALLED (pip install ezdxf)")

    # matplotlib
    try:
        import matplotlib
        log.info("  matplotlib: %s", matplotlib.__version__)
    except ImportError:
        log.error("  matplotlib: NOT INSTALLED (pip install matplotlib)")

    # Pillow
    try:
        from PIL import Image
        import PIL
        log.info("  Pillow: %s", PIL.__version__)
    except ImportError:
        log.error("  Pillow: NOT INSTALLED (pip install Pillow)")

    # Blender
    blender = _find_blender()
    if blender:
        log.info("  Blender: %s", blender)
    else:
        log.error("  Blender: NOT FOUND")

    # Gemini
    gemini = os.environ.get("GEMINI_GEN_PATH", "D:/imageProduce/gemini_gen.py")
    if os.path.isfile(gemini):
        log.info("  Gemini: %s", gemini)
    else:
        log.warning("  Gemini: not found (optional, for AI enhancement)")

    return 0


# ═════════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="CAD Parametric Pipeline — unified CLI",
        epilog="""Examples:
  %(prog)s build --subsystem end_effector
  %(prog)s render --subsystem end_effector --view V1
  %(prog)s full --subsystem end_effector
  %(prog)s status
  %(prog)s env-check
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("-v", "--verbose", action="store_true", help="Debug output")
    parser.add_argument("-q", "--quiet", action="store_true", help="Warnings only")
    parser.add_argument("--dry-run", action="store_true", help="Validate without executing")

    sub = parser.add_subparsers(dest="command", help="Pipeline command")

    # build
    p_build = sub.add_parser("build", help="Build STEP + DXF files")
    p_build.add_argument("--subsystem", "-s", default="end_effector")
    p_build.add_argument("--render", action="store_true", help="Also render after build")

    # render
    p_render = sub.add_parser("render", help="Blender Cycles rendering")
    p_render.add_argument("--subsystem", "-s", default="end_effector")
    p_render.add_argument("--view", help="Single view (V1-V5)")

    # enhance
    p_enhance = sub.add_parser("enhance", help="Gemini AI enhancement")
    p_enhance.add_argument("--dir", help="Directory with V*.png files")

    # annotate
    p_annotate = sub.add_parser("annotate", help="Add component labels")
    p_annotate.add_argument("--subsystem", "-s", default="end_effector")
    p_annotate.add_argument("--config", help="render_config.json path")
    p_annotate.add_argument("--dir", help="Directory with images")
    p_annotate.add_argument("--lang", default="cn,en", help="Languages (default: cn,en)")

    # full
    p_full = sub.add_parser("full", help="Full pipeline: build→render→enhance→annotate")
    p_full.add_argument("--subsystem", "-s", default="end_effector")
    p_full.add_argument("--render", action="store_true", default=True)
    p_full.add_argument("--view", default=None)
    p_full.add_argument("--dir", default=None)
    p_full.add_argument("--config", default=None)
    p_full.add_argument("--lang", default="cn,en")
    p_full.add_argument("--skip-enhance", action="store_true")
    p_full.add_argument("--skip-annotate", action="store_true")

    # status
    sub.add_parser("status", help="Show pipeline status")

    # env-check
    sub.add_parser("env-check", help="Validate environment")

    args = parser.parse_args()

    # Logging
    level = logging.DEBUG if args.verbose else logging.INFO
    if args.quiet:
        level = logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    if not args.command:
        parser.print_help()
        return 0

    dispatch = {
        "build": cmd_build,
        "render": cmd_render,
        "enhance": cmd_enhance,
        "annotate": cmd_annotate,
        "full": cmd_full,
        "status": cmd_status,
        "env-check": cmd_env_check,
    }

    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
