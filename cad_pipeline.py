#!/usr/bin/env python3
"""
cad_pipeline.py — Unified CLI for the CAD parametric pipeline.

Chains: spec → codegen → build → render → enhance → annotate in correct order,
with error propagation, progress tracking, and --dry-run support.

Usage:
    python cad_pipeline.py spec --design-doc docs/design/04-末端执行机构设计.md
    python cad_pipeline.py codegen --subsystem end_effector
    python cad_pipeline.py build                         # STEP + DXF only
    python cad_pipeline.py build --render                # + Blender renders
    python cad_pipeline.py render --subsystem end_effector --timestamp
    python cad_pipeline.py enhance --dir cad/output/renders
    python cad_pipeline.py annotate --config render_config.json --lang cn
    python cad_pipeline.py full --subsystem end_effector  # all 6 phases
    python cad_pipeline.py status                         # show pipeline status
    python cad_pipeline.py env-check                      # environment validation

Examples:
    # Full pipeline for end_effector (spec→codegen→build→render→enhance→annotate):
    python cad_pipeline.py full --subsystem end_effector --design-doc docs/design/04-末端执行机构设计.md

    # Dry-run (validate only, no actual builds):
    python cad_pipeline.py full --subsystem end_effector --dry-run

    # Render a single view with timestamp:
    python cad_pipeline.py render --subsystem end_effector --view V1 --timestamp
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

from cad_paths import (
    SKILL_ROOT, get_blender_path, get_subsystem_dir, get_output_dir,
    get_gemini_script,
)

log = logging.getLogger("cad_pipeline")

CAD_DIR = os.path.join(SKILL_ROOT, "cad")
TOOLS_DIR = os.path.join(SKILL_ROOT, "tools")
CONFIG_PATH = os.path.join(SKILL_ROOT, "config", "gisbot.json")
PIPELINE_CONFIG_PATH = os.path.join(SKILL_ROOT, "pipeline_config.json")
DEFAULT_OUTPUT = get_output_dir()


def _load_pipeline_config():
    """Load pipeline_config.json (render/timestamp/archive settings)."""
    if os.path.isfile(PIPELINE_CONFIG_PATH):
        with open(PIPELINE_CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _should_timestamp(args):
    """Determine if timestamp should be added to output filenames.

    Priority: CLI --timestamp flag > pipeline_config.json timestamp.enabled
    """
    if getattr(args, "timestamp", False):
        return True
    pc = _load_pipeline_config()
    return pc.get("timestamp", {}).get("enabled", False)


def _load_config():
    """Load gisbot.json subsystem config."""
    if os.path.isfile(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _resolve_design_doc(subsystem_name, config=None, doc_dir=None):
    """Find the design doc for a subsystem from config mapping.

    Returns path or None.
    """
    if config is None:
        config = _load_config()
    doc_base = doc_dir or config.get("doc_dir", "docs/design")
    if not os.path.isabs(doc_base):
        doc_base = os.path.join(SKILL_ROOT, doc_base)

    # Find chapter number for this subsystem
    for chapter, info in config.get("subsystems", {}).items():
        cad_dir = info.get("cad_dir", "")
        aliases = info.get("aliases", [])
        if cad_dir == subsystem_name or subsystem_name in aliases:
            # Look for NN-*.md matching this chapter
            pattern = os.path.join(doc_base, f"{chapter}-*.md")
            matches = glob.glob(pattern)
            if matches:
                return matches[0]
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
            encoding="utf-8", errors="replace",
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

def _resolve_review_json(args):
    """Locate DESIGN_REVIEW.json for a subsystem (output_dir/cad_subdir/)."""
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        output_dir = cfg.get("output_dir", "./output")
        sub_cfg = cfg.get("subsystems", {})
        cad_subdir = None
        sub_name = getattr(args, "subsystem", None) or "end_effector"
        for _ch, info in sub_cfg.items():
            aliases = [info.get("name", "")] + info.get("aliases", [])
            if sub_name in aliases or sub_name == info.get("cad_dir"):
                cad_subdir = info.get("cad_dir", sub_name)
                break
        if not cad_subdir:
            cad_subdir = sub_name
        return os.path.join(output_dir, cad_subdir, "DESIGN_REVIEW.json")
    except (OSError, json.JSONDecodeError):
        return os.path.join("./output", getattr(args, "subsystem", "end_effector"),
                            "DESIGN_REVIEW.json")


def _show_review_summary(review_json_path):
    """Print review summary and return (critical, warning, auto_fill) counts."""
    if not os.path.isfile(review_json_path):
        return 0, 0, 0
    with open(review_json_path, encoding="utf-8") as f:
        data = json.load(f)
    c, w, af = data.get("critical", 0), data.get("warning", 0), data.get("auto_fill", 0)
    ok_count = data.get("ok", 0)
    info_count = data.get("info", 0)

    review_md = review_json_path.replace("DESIGN_REVIEW.json", "DESIGN_REVIEW.md")
    log.info("=" * 60)
    log.info("  设计审查结果 (Design Review)")
    log.info("=" * 60)
    log.info("  CRITICAL: %d | WARNING: %d | INFO: %d | OK: %d", c, w, info_count, ok_count)
    if af > 0:
        log.info("  可自动补全: %d 项", af)
    log.info("  详见: %s", review_md)

    # Print review items summary
    items = data.get("items", [])
    for item in items:
        severity = item.get("severity", "")
        code = item.get("code", "")
        msg = item.get("message", "")
        if severity in ("CRITICAL", "WARNING"):
            log.info("  [%s] %s: %s", severity, code, msg[:80])
    log.info("=" * 60)
    return c, w, af


def _prompt_review_choice(critical, warning, auto_fill):
    """Prompt user to choose next action after design review.

    Returns: "iterate" | "auto_fill" | "proceed" | "abort"
    """
    if critical > 0:
        log.error("存在 %d 个 CRITICAL 问题，必须修复后才能继续。", critical)
        print("\n请选择:")
        print("  1. 继续审查 — 逐项讨论问题并修正")
        print("  2. 中止 — 先手动修正设计文档后重新运行")
        while True:
            choice = input("\n请输入选项 [1/2]: ").strip()
            if choice == "1":
                return "iterate"
            elif choice == "2":
                return "abort"
            print("  无效输入，请输入 1 或 2")

    if warning > 0:
        print("\n请选择:")
        print("  1. 继续审查 — 逐项讨论 WARNING 问题")
        if auto_fill > 0:
            print(f"  2. 自动补全 — 自动填入 {auto_fill} 项可计算的默认值，然后生成 CAD_SPEC.md")
        else:
            print("  2. (无可自动补全项)")
        print("  3. 下一步 — 按现有数据直接生成 CAD_SPEC.md")
        valid = {"1", "3"} if auto_fill == 0 else {"1", "2", "3"}
        while True:
            choice = input(f"\n请输入选项 [{'/'.join(sorted(valid))}]: ").strip()
            if choice == "1" and "1" in valid:
                return "iterate"
            elif choice == "2" and "2" in valid:
                return "auto_fill"
            elif choice == "3" and "3" in valid:
                return "proceed"
            print(f"  无效输入，请输入 {'/'.join(sorted(valid))}")

    # No issues
    log.info("审查通过，无 CRITICAL/WARNING 问题，自动进入下一步。")
    return "proceed"


def cmd_spec(args):
    """Phase 1: Design review + CAD_SPEC.md generation (interactive)."""
    design_doc = getattr(args, "design_doc", None)
    if not design_doc:
        design_doc = _resolve_design_doc(args.subsystem)
    if not design_doc or not os.path.isfile(design_doc):
        log.error("Design doc not found. Use --design-doc or ensure docs/design/%s exists",
                  design_doc or "??-*.md")
        return 1

    spec_gen = os.path.join(SKILL_ROOT, "cad_spec_gen.py")
    if not os.path.isfile(spec_gen):
        log.error("cad_spec_gen.py not found at %s", spec_gen)
        return 1

    force_flag = getattr(args, "force", False) or getattr(args, "force_spec", False)

    # ── Step 1: Run review-only first ──
    cmd_review = [sys.executable, spec_gen, design_doc,
                  "--config", CONFIG_PATH,
                  "--review-only"]
    if force_flag:
        cmd_review.append("--force")

    log.info("Phase 1a: 生成设计审查报告...")
    ok, _ = _run_subprocess(cmd_review, f"review ({os.path.basename(design_doc)})",
                            dry_run=args.dry_run, timeout=120)
    if not ok:
        return 1

    if args.dry_run:
        return 0

    # ── Step 2: Read review results and prompt user ──
    review_json = _resolve_review_json(args)
    critical, warning, auto_fill_count = _show_review_summary(review_json)

    # If --auto-fill was pre-set via CLI, skip interactive prompt
    if getattr(args, "auto_fill", False):
        log.info("--auto-fill 已指定，自动补全并生成 CAD_SPEC.md")
        choice = "auto_fill"
    else:
        choice = _prompt_review_choice(critical, warning, auto_fill_count)

    # ── Step 3: Act on user choice ──
    if choice == "abort":
        log.info("用户选择中止。请修正设计文档后重新运行。")
        return 1

    if choice == "iterate":
        log.info("用户选择继续审查。请查看 DESIGN_REVIEW.md 逐项讨论后重新运行。")
        return 2  # Special exit code: review iteration

    # "auto_fill" or "proceed" → generate CAD_SPEC.md
    cmd_gen = [sys.executable, spec_gen, design_doc,
               "--config", CONFIG_PATH,
               "--review"]
    if choice == "auto_fill":
        cmd_gen.append("--auto-fill")
    if force_flag:
        cmd_gen.append("--force")

    log.info("Phase 1b: 生成 CAD_SPEC.md...")
    ok, _ = _run_subprocess(cmd_gen, f"spec-gen ({os.path.basename(design_doc)})",
                            dry_run=args.dry_run, timeout=120)
    return 0 if ok else 1


def cmd_codegen(args):
    """Phase 2: Generate CadQuery scaffolds from CAD_SPEC.md."""
    try:
        import jinja2  # noqa: F401
    except ImportError:
        log.error("Jinja2 not installed. Run: pip install Jinja2")
        return 1

    sub_dir = get_subsystem_dir(args.subsystem)
    if not sub_dir:
        log.error("Subsystem '%s' not found in %s", args.subsystem, CAD_DIR)
        return 1

    spec_path = os.path.join(sub_dir, "CAD_SPEC.md")
    if not os.path.isfile(spec_path):
        log.error("CAD_SPEC.md not found in %s. Run 'spec' first.", sub_dir)
        return 1

    mode = "force" if getattr(args, "force", False) else "scaffold"
    failures = 0

    # 2a: params.py
    cmd = [sys.executable, os.path.join(SKILL_ROOT, "codegen", "gen_params.py"),
           spec_path, "--mode", mode]
    ok, _ = _run_subprocess(cmd, "codegen params.py", dry_run=args.dry_run)
    if not ok:
        failures += 1

    # 2b: build_all.py
    cmd = [sys.executable, os.path.join(SKILL_ROOT, "codegen", "gen_build.py"),
           spec_path, "--mode", mode]
    ok, _ = _run_subprocess(cmd, "codegen build_all.py", dry_run=args.dry_run)
    if not ok:
        failures += 1

    # 2c: part module scaffolds
    cmd = [sys.executable, os.path.join(SKILL_ROOT, "codegen", "gen_parts.py"),
           spec_path, "--output-dir", sub_dir]
    ok, _ = _run_subprocess(cmd, "codegen part scaffolds", dry_run=args.dry_run)
    if not ok:
        failures += 1

    # 2c2: standard part simplified geometry (purchased parts)
    cmd = [sys.executable, os.path.join(SKILL_ROOT, "codegen", "gen_std_parts.py"),
           spec_path, "--output-dir", sub_dir]
    ok, _ = _run_subprocess(cmd, "codegen std parts", dry_run=args.dry_run)
    if not ok:
        failures += 1

    # 2d: assembly.py
    cmd = [sys.executable, os.path.join(SKILL_ROOT, "codegen", "gen_assembly.py"),
           spec_path, "--mode", mode]
    ok, _ = _run_subprocess(cmd, "codegen assembly.py", dry_run=args.dry_run)
    if not ok:
        failures += 1

    return 1 if failures else 0

def cmd_build(args):
    """Build STEP + DXF for a subsystem."""
    sub_dir = get_subsystem_dir(args.subsystem)
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
                                  dry_run=args.dry_run, timeout=1200)
    return 0 if ok else 1


def cmd_render(args):
    """Run Blender rendering for a subsystem."""
    blender = get_blender_path()
    if not blender:
        log.error("Blender not found. Set BLENDER_PATH env var.")
        return 1

    sub_dir = get_subsystem_dir(args.subsystem)
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
    if _should_timestamp(args):
        render_args.append("--timestamp")

    if args.view:
        # Single view
        if args.view.upper() == "V4" and os.path.isfile(exploded_script):
            cmd = [blender, "-b", "-P", exploded_script, "--"] + render_args
        else:
            cmd = [blender, "-b", "-P", render_script, "--"] + render_args + ["--view", args.view]
        ok, _ = _run_subprocess(cmd, f"render {args.view}", dry_run=args.dry_run, timeout=1200)
        if not ok:
            failures += 1
    else:
        # All views
        cmd = [blender, "-b", "-P", render_script, "--"] + render_args + ["--all"]
        ok, _ = _run_subprocess(cmd, "render standard views", dry_run=args.dry_run, timeout=1200)
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
    gemini_script = get_gemini_script()
    if not gemini_script:
        log.error("gemini_gen.py not found at %s", gemini_script)
        log.error("Set GEMINI_GEN_PATH env var or install gemini_gen.py")
        return 1

    render_dir = args.dir or os.path.join(DEFAULT_OUTPUT, "renders")
    pngs = sorted(glob.glob(os.path.join(render_dir, "V*.png")))
    if not pngs:
        log.error("No V*.png files found in %s", render_dir)
        return 1

    # Load render_config.json for standard_parts descriptions
    std_parts_desc = ""
    _sub_name = getattr(args, "subsystem", None)
    sub_dir = get_subsystem_dir(_sub_name) if _sub_name else None
    rc_path = os.path.join(sub_dir, "render_config.json") if sub_dir else None
    if rc_path and os.path.isfile(rc_path):
        with open(rc_path, encoding="utf-8") as f:
            rc = json.load(f)
        std_parts = rc.get("standard_parts", [])
        if std_parts:
            lines = ["\n[Standard Components — enhance simplified shapes to real-world appearance]"]
            for sp in std_parts:
                lines.append(f"- {sp.get('visual_cue', '')}: {sp.get('real_part', '')}")
            std_parts_desc = "\n".join(lines)

    # Load model config
    model_arg = []
    pcfg_path = os.path.join(SKILL_ROOT, "pipeline_config.json")
    if os.path.isfile(pcfg_path):
        with open(pcfg_path, encoding="utf-8") as f:
            pcfg = json.load(f)
        enhance_cfg = pcfg.get("enhance", {})
        model_key = enhance_cfg.get("model", "")
        models = enhance_cfg.get("models", {})
        model_id = models.get(model_key, "")
        if model_id:
            model_arg = ["--model", model_id]

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
            # Fill standard_parts_description (empty string if no data)
            prompt = prompt.replace("{standard_parts_description}", std_parts_desc)
        else:
            prompt = ("Keep ALL geometry EXACTLY unchanged. Enhance surface materials "
                      "to photo-realistic quality with proper lighting and reflections.")

        cmd = [sys.executable, gemini_script, prompt, "--image", png] + model_arg

        if args.dry_run:
            log.info("  [DRY-RUN] Would run: %s", " ".join(cmd[:6]))
            continue

        log.info("  Running: enhance %s", os.path.basename(png))
        t0 = time.time()
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=180,
                encoding="utf-8", errors="replace",
            )
            elapsed = time.time() - t0
            if result.returncode != 0:
                log.error("  FAILED enhance %s (exit %d, %.1fs)",
                          os.path.basename(png), result.returncode, elapsed)
                failures += 1
                continue
            log.info("  OK: enhance %s (%.1fs)", os.path.basename(png), elapsed)

            # Rename gemini output: V*_YYYYMMDD_HHMM_enhanced.ext → same dir as source
            gemini_path = None
            for line in (result.stdout or "").split("\n"):
                if "图片已保存:" in line or "已保存:" in line:
                    # Extract path after last colon (handle Windows drive letters)
                    idx = line.rfind("保存:")
                    if idx >= 0:
                        gemini_path = line[idx + len("保存:"):].strip()
                    break
            if gemini_path and os.path.isfile(gemini_path):
                from datetime import datetime as _dt
                src_stem = os.path.splitext(os.path.basename(png))[0]
                ts = _dt.now().strftime("%Y%m%d_%H%M")
                ext = os.path.splitext(gemini_path)[1]  # .jpg or .png
                new_name = f"{src_stem}_{ts}_enhanced{ext}"
                new_path = os.path.join(os.path.dirname(png), new_name)
                shutil.copy2(gemini_path, new_path)
                os.remove(gemini_path)
                log.info("  Saved: %s", new_path)
            else:
                log.warning("  Could not locate gemini output for %s", os.path.basename(png))

        except subprocess.TimeoutExpired:
            log.error("  TIMEOUT enhance %s (>180s)", os.path.basename(png))
            failures += 1
        except FileNotFoundError as e:
            log.error("  NOT FOUND: %s", e)
            failures += 1

    return 1 if failures else 0


def cmd_annotate(args):
    """Add component labels to enhanced images."""
    annotate_script = os.path.join(SKILL_ROOT, "annotate_render.py")
    if not os.path.isfile(annotate_script):
        log.error("annotate_render.py not found at %s", annotate_script)
        return 1

    sub_dir = get_subsystem_dir(args.subsystem)
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


def _review_checkpoint(args):
    """Check that review passed. Called from cmd_full after cmd_spec already handled interaction."""
    review_json = _resolve_review_json(args)
    if not os.path.isfile(review_json):
        return 0  # No review data, continue

    with open(review_json, encoding="utf-8") as f:
        data = json.load(f)

    critical = data.get("critical", 0)
    if critical > 0:
        log.error("DESIGN_REVIEW still has %d CRITICAL issue(s). Cannot continue.", critical)
        return 1

    return 0


def cmd_full(args):
    """Full pipeline: spec → codegen → build → render → enhance → annotate."""
    log.info("=" * 60)
    log.info("  Full pipeline for: %s", args.subsystem)
    log.info("=" * 60)
    t0 = time.time()

    steps = []

    # Phase 1: Spec generation (requires --design-doc or auto-resolve)
    if not args.skip_spec:
        steps.append(("SPEC", lambda: cmd_spec(args)))
        steps.append(("REVIEW_CHECK", lambda: _review_checkpoint(args)))

    # Phase 2: Code generation
    if not args.skip_codegen:
        steps.append(("CODEGEN", lambda: cmd_codegen(args)))

    # Phase 3: Build
    steps.append(("BUILD", lambda: cmd_build(args)))

    # Phase 4: Render
    steps.append(("RENDER", lambda: cmd_render(args)))

    # Phase 5: Enhance
    if not args.skip_enhance:
        steps.append(("ENHANCE", lambda: cmd_enhance(args)))

    # Phase 6: Annotate
    if not args.skip_annotate:
        steps.append(("ANNOTATE", lambda: cmd_annotate(args)))

    for i, (name, fn) in enumerate(steps, 1):
        log.info("\n[%d/%d] %s", i, len(steps), name)
        rc = fn()
        if rc != 0:
            if rc == 2:
                log.info("管线暂停于 %s — 用户选择继续审查。修正后重新运行。", name)
            else:
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

        icon = {"spec-only": "[ ]", "buildable": "[B]", "built": "[*]", "rendered": "[R]"}
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

    # Jinja2 (codegen templates)
    try:
        import jinja2
        log.info("  Jinja2: %s", jinja2.__version__)
    except ImportError:
        log.error("  Jinja2: NOT INSTALLED (pip install Jinja2) — required by codegen/")

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
    blender = get_blender_path()
    if blender:
        log.info("  Blender: %s", blender)
    else:
        log.error("  Blender: NOT FOUND")

    # Gemini
    gemini = get_gemini_script()
    if gemini:
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
  %(prog)s spec --design-doc docs/design/04-*.md
  %(prog)s codegen --subsystem end_effector
  %(prog)s build --subsystem end_effector
  %(prog)s render --subsystem end_effector --view V1 --timestamp
  %(prog)s full --subsystem end_effector --design-doc docs/design/04-*.md
  %(prog)s status
  %(prog)s env-check
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("-v", "--verbose", action="store_true", help="Debug output")
    parser.add_argument("-q", "--quiet", action="store_true", help="Warnings only")
    parser.add_argument("--dry-run", action="store_true", help="Validate without executing")

    sub = parser.add_subparsers(dest="command", help="Pipeline command")

    # spec
    p_spec = sub.add_parser("spec", help="Design review + CAD_SPEC.md generation")
    p_spec.add_argument("--subsystem", "-s", default="end_effector")
    p_spec.add_argument("--design-doc", help="Path to design document (NN-*.md)")
    p_spec.add_argument("--auto-fill", action="store_true", help="Auto-fill computable values")
    p_spec.add_argument("--force", action="store_true", help="Force regeneration")

    # codegen
    p_codegen = sub.add_parser("codegen", help="Generate CadQuery scaffolds from CAD_SPEC.md")
    p_codegen.add_argument("--subsystem", "-s", default="end_effector")
    p_codegen.add_argument("--force", action="store_true", help="Overwrite existing files")

    # build
    p_build = sub.add_parser("build", help="Build STEP + DXF files")
    p_build.add_argument("--subsystem", "-s", default="end_effector")
    p_build.add_argument("--render", action="store_true", help="Also render after build")

    # render
    p_render = sub.add_parser("render", help="Blender Cycles rendering")
    p_render.add_argument("--subsystem", "-s", default="end_effector")
    p_render.add_argument("--view", help="Single view (V1-V5)")
    p_render.add_argument("--timestamp", action="store_true", help="Append timestamp to filenames")

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
    p_full = sub.add_parser("full", help="Full pipeline: spec→codegen→build→render→enhance→annotate")
    p_full.add_argument("--subsystem", "-s", default="end_effector")
    p_full.add_argument("--design-doc", help="Path to design document (NN-*.md)")
    p_full.add_argument("--auto-fill", action="store_true", help="Auto-fill computable values")
    p_full.add_argument("--force-spec", action="store_true", help="Force spec regeneration")
    p_full.add_argument("--force", action="store_true", help="Force codegen overwrite")
    p_full.add_argument("--render", action="store_true", default=False,
                        help="Pass --render to build_all.py (normally handled by RENDER phase)")
    p_full.add_argument("--view", default=None)
    p_full.add_argument("--dir", default=None)
    p_full.add_argument("--config", default=None)
    p_full.add_argument("--lang", default="cn,en")
    p_full.add_argument("--timestamp", action="store_true", help="Append timestamp to renders")
    p_full.add_argument("--skip-spec", action="store_true", help="Skip spec generation")
    p_full.add_argument("--skip-codegen", action="store_true", help="Skip code generation")
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
        "spec": cmd_spec,
        "codegen": cmd_codegen,
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
