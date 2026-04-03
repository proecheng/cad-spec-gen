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

# Force UTF-8 output on Windows to avoid GBK encoding issues
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
import time

from cad_paths import (
    SKILL_ROOT, PROJECT_ROOT, get_blender_path, get_subsystem_dir,
    get_output_dir, get_gemini_script,
)

log = logging.getLogger("cad_pipeline")

CAD_DIR = os.path.join(PROJECT_ROOT, "cad")
TOOLS_DIR = os.path.join(SKILL_ROOT, "tools")
CONFIG_PATH = os.path.join(SKILL_ROOT, "config", "gisbot.json")
PIPELINE_CONFIG_PATH = os.path.join(SKILL_ROOT, "pipeline_config.json")
DEFAULT_OUTPUT = get_output_dir()


def _deploy_tool_modules(sub_dir: str):
    """Copy shared Python tool modules to a subsystem directory.

    These modules are needed at runtime by generated code (ee_*.py, build_all.py):
      - drawing.py        — ezdxf GB/T drawing primitives
      - draw_three_view.py — ThreeViewSheet class
      - cq_to_dxf.py      — CadQuery→DXF HLR projection bridge
      - render_dxf.py      — DXF→PNG batch renderer
    Only copies if source is newer or target is missing (scaffold-safe).
    """
    import shutil
    tool_files = ["drawing.py", "draw_three_view.py", "cq_to_dxf.py", "render_dxf.py"]
    for fname in tool_files:
        src = os.path.join(SKILL_ROOT, fname)
        dst = os.path.join(sub_dir, fname)
        if not os.path.isfile(src):
            continue
        if os.path.isfile(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
            continue  # Target is up-to-date
        shutil.copy2(src, dst)
        log.info("  Deployed: %s → %s", fname, os.path.basename(sub_dir))


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
        doc_base = os.path.join(PROJECT_ROOT, doc_base)

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
        sub_name = getattr(args, "subsystem", None)
        if not sub_name:
            log.warning("No --subsystem specified; cannot locate DESIGN_REVIEW.json")
            return None
        for _ch, info in sub_cfg.items():
            aliases = [info.get("name", "")] + info.get("aliases", [])
            if sub_name in aliases or sub_name == info.get("cad_dir"):
                cad_subdir = info.get("cad_dir", sub_name)
                break
        if not cad_subdir:
            cad_subdir = sub_name
        return os.path.join(output_dir, cad_subdir, "DESIGN_REVIEW.json")
    except (OSError, json.JSONDecodeError):
        sub_name = getattr(args, "subsystem", None)
        if not sub_name:
            return None
        return os.path.join(DEFAULT_OUTPUT, sub_name, "DESIGN_REVIEW.json")


def _show_review_summary(review_json_path):
    """Print review summary and return (critical, warning, auto_fill, auto_fill_items) counts."""
    if not os.path.isfile(review_json_path):
        return 0, 0, 0, []
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
        severity = item.get("verdict", "")
        code = item.get("id", "")
        check = item.get("check", "")
        detail = item.get("detail", "")
        suggestion = item.get("suggestion", "")
        label = f"{code} {check}".strip() if check else code
        msg = detail
        if severity == "CRITICAL":
            log.info("  [CRITICAL] %s: %s", label, msg)
            if suggestion:
                log.info("    建议: %s", suggestion)
        elif severity == "WARNING":
            log.info("  [WARNING]  %s: %s", label, msg)
            if suggestion:
                log.info("    建议: %s", suggestion)
        elif severity == "INFO":
            log.info("  [INFO]     %s: %s", label, msg)
    log.info("=" * 60)
    auto_fill_items = [item.get("id", "") for item in items if item.get("auto_fill") == "是"]
    return c, w, af, auto_fill_items


def _infer_assembly_layers(review_json_path):
    """从 CAD_SPEC.md BOM树推断装配层叠表初稿。"""
    spec_path = review_json_path.replace("DESIGN_REVIEW.json", "CAD_SPEC.md")
    # Try cad/ path too
    if not os.path.isfile(spec_path):
        # output/end_effector/DESIGN_REVIEW.json -> cad/end_effector/CAD_SPEC.md
        spec_path = spec_path.replace(os.sep + "output" + os.sep,
                                      os.sep + "cad" + os.sep)
    if not os.path.isfile(spec_path):
        return None
    lines = open(spec_path, encoding="utf-8", errors="replace").readlines()
    # Find BOM table rows
    in_bom = False
    rows = []
    for line in lines:
        if "## 5." in line and "BOM" in line:
            in_bom = True
            continue
        if in_bom and line.startswith("## "):
            break
        if in_bom and line.startswith("| ") and "---" not in line and "料号" not in line:
            cols = [c.strip().strip("*") for c in line.strip().split("|")[1:-1]]
            if len(cols) >= 2:
                part_no = cols[0].strip()
                name = cols[1].strip()
                rows.append((part_no, name))
    if not rows:
        return None
    # Generate layers table
    result = ["层级|零件名称|固定/运动|连接方式|偏移"]
    current_assembly = None
    for part_no, name in rows:
        if not part_no:
            continue
        # Assembly header (bold, no sub-number)
        if part_no.count("-") <= 2 and not any(c.isdigit() for c in part_no.split("-")[-1:][0] if part_no.split("-")[-1:]):
            pass
        is_assembly = part_no.count("-") == 2  # GIS-EE-001
        is_part = part_no.count("-") == 3       # GIS-EE-001-01
        if is_assembly:
            current_assembly = name
            result.append(f"1|{name}|固定|法兰螺栓|0")
        elif is_part and current_assembly:
            result.append(f"2|{name}|固定|螺栓/粘接|0")
    return "\n".join(result)


MATERIAL_CANDIDATES = {
    "泵": ["铸铁", "球墨铸铁", "不锈钢", "铝合金"],
    "电机": ["铝合金壳体", "不锈钢轴"],
    "阀": ["不锈钢", "铜合金"],
    "传感器": ["铝合金", "不锈钢"],
    "支架": ["铝合金", "不锈钢"],
    "壳体": ["铝合金", "工程塑料"],
    "轴": ["不锈钢", "42CrMo"],
    "弹簧": ["SUS301", "65Mn"],
    "齿轮": ["45#钢", "塑料PA66"],
    "密封": ["FKM", "NBR", "硅橡胶"],
    "线束": ["铜芯"],
    "接头": ["不锈钢", "铜合金"],
}


def _infer_material_candidates(part_name):
    """从零件名称推断材质候选列表。"""
    for keyword, candidates in MATERIAL_CANDIDATES.items():
        if keyword in part_name:
            return candidates
    return ["铝合金", "不锈钢", "工程塑料"]


def _interactive_fill_warnings(review_json_path):
    """逐项引导用户处理所有 WARNING/CRITICAL 项（含自动补全和手动填写）。

    Returns: dict of {item_id: user_input}
    """
    if not os.path.isfile(review_json_path):
        return {}
    with open(review_json_path, encoding="utf-8") as f:
        data = json.load(f)

    all_items = [item for item in data.get("items", [])
                 if item.get("verdict") in ("WARNING", "CRITICAL")]
    info_items = [item for item in data.get("items", [])
                  if item.get("verdict") == "INFO" and item.get("auto_fill") == "是"]
    all_guide = all_items + info_items
    if not all_guide:
        return {}

    supplements = {}
    print(f"\n共 {len(all_guide)} 项需要逐项处理：")
    for item in all_guide:
        item_id = item.get("id", "?")
        check = item.get("check", "") or item.get("id", "")
        detail = item.get("detail", "")
        suggestion = item.get("suggestion", "")
        can_auto = item.get("auto_fill") == "是"
        verdict = item.get("verdict", "")

        print(f"\n{'─'*60}")
        print(f"[{verdict}] {item_id}: {check or detail}")
        if detail and check:
            print(f"  详情: {detail}")
        if suggestion and suggestion != "—":
            print(f"  建议格式: {suggestion}")
        print(f"{'─'*60}")

        if can_auto:
            print("  此项可自动补全。")
            print("  a. 自动补全（使用建议默认值）")
            print("  b. 手动填写")
            print("  s. 跳过")
            try:
                sub = input("  选择 [a/b/s]: ").strip().lower()
            except EOFError:
                log.error("交互式填写需要终端输入，stdin 已关闭。")
                sys.exit(1)
            if sub == "a":
                # Mark as auto-fill
                supplements[item_id] = "__AUTO_FILL__"
                print(f"  [自动补全 {item_id}]")
                continue
            elif sub == "s":
                print(f"  [跳过 {item_id}]")
                continue
            # else fall through to manual input
        else:
            # Check if we can infer a value for this item
            inferred = None
            infer_label = None
            if "M02" in item_id or "装配层叠" in check:
                inferred = _infer_assembly_layers(review_json_path)
                infer_label = "从BOM树推断装配层叠表"
            elif "D5" in item_id or "BOM缺少材质" in check:
                # Extract part names from detail
                parts = [p.strip() for p in detail.replace("缺失:", "").split(",") if p.strip()]
                if parts:
                    cands = _infer_material_candidates(parts[0])
                    inferred = f"{parts[0]} 材质候选: {' / '.join(cands)}"
                    infer_label = f"为 {parts[0]} 推断材质候选"

            if inferred:
                print(f"\n  推断值（{infer_label}）：")
                print(f"  {'─'*56}")
                for ln in inferred.splitlines():
                    print(f"  {ln}")
                print(f"  {'─'*56}")
                # Tell user where to manually edit if they want to change later
                spec_path = review_json_path.replace("DESIGN_REVIEW.json", "CAD_SPEC.md")
                if not os.path.isfile(spec_path):
                    spec_path = review_json_path.replace(
                        os.path.join("output", ""), os.path.join("cad", "")
                    ).replace("DESIGN_REVIEW.json", "CAD_SPEC.md")
                print(f"  ℹ 如需后续修改，请编辑: {spec_path} 的 §10 节")
                print("  i. 采用推断值并写入")
                print("  b. 手动填写（替换推断值）")
                print("  s. 跳过")
                try:
                    sub = input("  选择 [i/b/s]: ").strip().lower()
                except EOFError:
                    log.error("交互式填写需要终端输入，stdin 已关闭。")
                    sys.exit(1)
                if sub == "i":
                    supplements[item_id] = inferred
                    print(f"  [已记录 {item_id}]")
                    continue
                elif sub == "s":
                    print(f"  [跳过 {item_id}]")
                    continue
                # else fall through to manual input
            else:
                print("  此项需要手动填写（不可自动补全）。")
            print("  输入补充内容（多行请按 Enter 换行，空行结束；直接空行跳过）:")

        lines = []
        try:
            while True:
                line = input("  > ").rstrip()
                if line == "" and not lines:
                    print(f"  [跳过 {item_id}]")
                    break
                if line == "" and lines:
                    break
                lines.append(line.encode("utf-8", errors="replace").decode("utf-8"))
        except EOFError:
            log.error("交互式填写需要终端输入，stdin 已关闭。")
            sys.exit(1)

        if lines:
            supplements[item_id] = "\n".join(lines)
            print(f"  [已记录 {item_id}]")

    return supplements


def _save_supplements(supplements, review_json_path):
    """Save user supplements to user_supplements.json next to DESIGN_REVIEW.json."""
    if not supplements:
        return None
    out_path = review_json_path.replace("DESIGN_REVIEW.json", "user_supplements.json")
    existing = {}
    if os.path.isfile(out_path):
        with open(out_path, encoding="utf-8") as f:
            existing = json.load(f)
    existing.update(supplements)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    log.info("补充内容已保存: %s", out_path)
    return out_path


def _prompt_review_choice(critical, warning, auto_fill, auto_fill_items=None):
    """Prompt user to choose next action after design review.

    Returns: "iterate" | "auto_fill" | "proceed" | "abort" | "guided_fill"
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
        print("  1. 逐项引导 — 逐项查看问题，可选自动补全或手动填写")
        print("  2. 跳过 — 按现有数据直接生成 CAD_SPEC.md")
        while True:
            try:
                choice = input("\n请输入选项 [1/2]: ").strip()
            except EOFError:
                log.error(
                    "交互式门控需要终端输入，stdin 已关闭。\n"
                    "请在终端直接运行本命令，或加 --auto-fill 使用非交互模式。"
                )
                sys.exit(1)
            if choice == "1":
                return "guided_fill"
            elif choice == "2":
                return "proceed"
            print("  无效输入，请输入 1 或 2")

    # No issues
    log.info("审查通过，无 CRITICAL/WARNING 问题，自动进入下一步。")
    return "proceed"


def cmd_spec(args):
    """Phase 1: Design review + CAD_SPEC.md generation.

    Modes (in priority order):
      --review-only   Generate DESIGN_REVIEW.md + .json only, no interaction, exit 0.
      --auto-fill     Auto-fill computable defaults + generate CAD_SPEC.md, no interaction.
      --proceed       Skip interaction, generate CAD_SPEC.md with existing data.
      (default)       Interactive: prompt user to iterate / auto-fill / proceed / abort.
    """
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

    # ── Step 2: Read review results ──
    review_json = _resolve_review_json(args)
    critical, warning, auto_fill_count, auto_fill_items = _show_review_summary(review_json)

    # ── Step 2b: Determine mode ──
    review_only = getattr(args, "review_only", False)
    if review_only:
        # Agent mode: just generate review, no spec generation
        log.info("--review-only: 审查报告已生成，等待 Agent 逐项审查。")
        log.info("  DESIGN_REVIEW.json: %s", review_json)
        return 0

    if getattr(args, "auto_fill", False):
        log.info("--auto-fill 已指定，自动补全并生成 CAD_SPEC.md")
        choice = "auto_fill"
    elif getattr(args, "proceed", False):
        log.info("--proceed 已指定，按现有数据生成 CAD_SPEC.md")
        choice = "proceed"
    elif getattr(args, "supplements", None):
        # Agent passed supplements as JSON string → write to file then proceed
        try:
            sup_data = json.loads(args.supplements)
        except json.JSONDecodeError as e:
            log.error("--supplements JSON 解析失败: %s", e)
            return 1
        _save_supplements(sup_data, review_json)
        log.info("--supplements 已写入 user_supplements.json，生成 CAD_SPEC.md")
        choice = "proceed"
    else:
        # Default (no flags): Agent mode — print summary and exit.
        # Agent reads DESIGN_REVIEW.json, discusses with user, then calls
        # spec --supplements '{...}' or spec --auto-fill / --proceed.
        if critical > 0:
            log.error("存在 %d 个 CRITICAL 问题，必须修复后才能继续。", critical)
            log.info("请修正设计文档后重新运行，或使用 --proceed 强制生成。")
            return 1
        if warning > 0:
            log.info("存在 %d 个 WARNING。Agent 请读取 DESIGN_REVIEW.json 逐项处理后"
                     " 调用 spec --supplements '{}' 或 spec --auto-fill。", warning)
        log.info("审查报告: %s", review_json)
        return 0

    # Parse --supplements even when combined with --auto-fill or --proceed
    sup_data = None
    if getattr(args, "supplements", None):
        try:
            sup_data = json.loads(args.supplements)
        except json.JSONDecodeError as e:
            log.error("--supplements JSON 解析失败: %s", e)
            return 1
        _save_supplements(sup_data, review_json)
        log.info("--supplements 已写入 user_supplements.json")

    supplements = None
    guided_auto_fill = False
    if choice == "guided_fill":
        supplements = _interactive_fill_warnings(review_json)
        guided_auto_fill = any(v == "__AUTO_FILL__" for v in supplements.values())
        supplements = {k: v for k, v in supplements.items() if v != "__AUTO_FILL__"}
        choice = "proceed"
    elif sup_data is not None:
        # --supplements path: carry non-AUTO entries to §10, AUTO entries trigger --auto-fill
        supplements = {k: v for k, v in sup_data.items()
                       if v not in ("__AUTO__", "__AUTO_FILL__")}
        guided_auto_fill = any(v in ("__AUTO__", "__AUTO_FILL__") for v in sup_data.values())

    # "auto_fill", "proceed", or post-guided_fill → generate CAD_SPEC.md
    cmd_gen = [sys.executable, spec_gen, design_doc,
               "--config", CONFIG_PATH,
               "--review"]
    if choice == "auto_fill" or guided_auto_fill:
        cmd_gen.append("--auto-fill")
    if force_flag:
        cmd_gen.append("--force")

    log.info("Phase 1b: 生成 CAD_SPEC.md...")
    ok, _ = _run_subprocess(cmd_gen, f"spec-gen ({os.path.basename(design_doc)})",
                            dry_run=args.dry_run, timeout=120)
    if not ok:
        return 1

    # Append user supplements to CAD_SPEC.md if any were collected
    if supplements:
        # CAD_SPEC.md is written to output/<subsystem>/ by cad_spec_gen.py
        output_dir = os.path.join(PROJECT_ROOT, "output", args.subsystem)
        spec_path = os.path.join(output_dir, "CAD_SPEC.md")
        if not os.path.isfile(spec_path):
            # Fallback: cad/<subsystem>/
            sub_dir = get_subsystem_dir(args.subsystem)
            spec_path = os.path.join(sub_dir, "CAD_SPEC.md") if sub_dir else None
        if os.path.isfile(spec_path):
            existing = open(spec_path, encoding="utf-8", errors="replace").read()
            if "## §10 用户补充数据" not in existing:
                with open(spec_path, "a", encoding="utf-8", errors="replace") as _sf:
                    _sf.write("\n\n## §10 用户补充数据 (User Supplements)\n\n")
                    for item_id, content in supplements.items():
                        _sf.write(f"### {item_id}\n\n{content}\n\n")
            else:
                # Overwrite existing §10 section
                import re
                new_section = "\n\n## §10 用户补充数据 (User Supplements)\n\n"
                for item_id, content in supplements.items():
                    new_section += f"### {item_id}\n\n{content}\n\n"
                updated = re.sub(r'\n+## §10 用户补充数据.*$', new_section, existing,
                                 flags=re.DOTALL)
                with open(spec_path, "w", encoding="utf-8", errors="replace") as _sf:
                    _sf.write(updated)
            log.info("用户补充数据已追加到 CAD_SPEC.md (%d 项)", len(supplements))
    return 0


def cmd_codegen(args):
    """Phase 2: Generate CadQuery scaffolds from CAD_SPEC.md."""
    try:
        import jinja2  # noqa: F401
    except ImportError:
        log.error("Jinja2 not installed. Run: pip install Jinja2")
        return 1

    sub_dir = get_subsystem_dir(args.subsystem)
    if not sub_dir:
        log.error("Subsystem '%s' not found in %s", args.subsystem or '(none — use --subsystem)', CAD_DIR)
        return 1

    spec_path = os.path.join(sub_dir, "CAD_SPEC.md")
    if not os.path.isfile(spec_path):
        log.error("CAD_SPEC.md not found in %s. Run 'spec' first.", sub_dir)
        return 1

    mode = "force" if getattr(args, "force", False) else "scaffold"
    failures = 0

    # 2-pre: Deploy shared tool modules to subsystem directory
    _deploy_tool_modules(sub_dir)

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
           spec_path, "--output-dir", sub_dir, "--mode", mode]
    ok, _ = _run_subprocess(cmd, "codegen part scaffolds", dry_run=args.dry_run)
    if not ok:
        failures += 1

    # 2c2: standard part simplified geometry (purchased parts)
    cmd = [sys.executable, os.path.join(SKILL_ROOT, "codegen", "gen_std_parts.py"),
           spec_path, "--output-dir", sub_dir, "--mode", mode]
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
        log.error("Subsystem '%s' not found in %s", args.subsystem or '(none — use --subsystem)', CAD_DIR)
        return 1

    build_script = os.path.join(sub_dir, "build_all.py")
    if not os.path.isfile(build_script):
        log.error("No build_all.py found in %s", sub_dir)
        return 1

    # ── Pre-build orientation gate ────────────────────────────────────────────
    orientation_script = os.path.join(sub_dir, "orientation_check.py")
    if os.path.isfile(orientation_script) and not getattr(args, 'skip_orientation', False):
        log.info("[Phase 3 pre-check] Running orientation_check.py ...")
        ok_orient, _ = _run_subprocess(
            [sys.executable, orientation_script],
            "orientation_check", dry_run=args.dry_run, timeout=120
        )
        if not ok_orient:
            log.error("Orientation check FAILED — aborting build. "
                      "Fix assembly directions then re-run. "
                      "Use --skip-orientation to bypass (not recommended).")
            return 1
        log.info("Orientation check passed.")
    # ─────────────────────────────────────────────────────────────────────────

    cmd = [sys.executable, build_script]
    if args.render:
        cmd.append("--render")
    if args.dry_run:
        cmd.append("--dry-run")
    if args.verbose:
        cmd.append("--verbose")

    ok, elapsed = _run_subprocess(cmd, f"build_all.py ({args.subsystem})",
                                  dry_run=args.dry_run, timeout=1200)
    if not ok:
        return 1

    # ── Post-build: DXF → PNG rendering ──────────────────────────────────────
    render_dxf_script = os.path.join(sub_dir, "render_dxf.py")
    if os.path.isfile(render_dxf_script):
        log.info("[Phase 3 post-build] Rendering DXF → PNG ...")
        ok_dxf, _ = _run_subprocess(
            [sys.executable, render_dxf_script],
            "render_dxf.py (DXF → PNG)", dry_run=args.dry_run, timeout=600
        )
        if not ok_dxf:
            log.warning("DXF → PNG rendering failed (non-fatal, DXF files are still available)")
    else:
        log.info("No render_dxf.py in %s — skipping DXF → PNG", sub_dir)
    # ─────────────────────────────────────────────────────────────────────────

    return 0


def cmd_render(args):
    """Run Blender rendering for a subsystem."""
    blender = get_blender_path()
    if not blender:
        log.error("Blender not found. Set BLENDER_PATH env var.")
        return 1

    sub_dir = get_subsystem_dir(args.subsystem)
    if not sub_dir:
        log.error("Subsystem '%s' not found. Use --subsystem.", args.subsystem or '(none)')
        return 1

    render_script = os.path.join(sub_dir, "render_3d.py")
    exploded_script = os.path.join(sub_dir, "render_exploded.py")
    config_path = os.path.join(sub_dir, "render_config.json")

    if not os.path.isfile(render_script):
        log.error("No render_3d.py in %s", sub_dir)
        return 1

    failures = 0
    _custom_output_dir = getattr(args, "output_dir", None)
    _renders_dir_pre = _custom_output_dir or os.path.join(DEFAULT_OUTPUT, "renders")
    _pre_existing = set(glob.glob(os.path.join(_renders_dir_pre, "V*.png"))) if os.path.isdir(_renders_dir_pre) else set()
    render_args = []
    if os.path.isfile(config_path):
        render_args = ["--config", config_path]
    if _should_timestamp(args):
        render_args.append("--timestamp")
    if _custom_output_dir:
        render_args += ["--output-dir", _custom_output_dir]

    section_script = os.path.join(sub_dir, "render_section.py")

    # P4: Load view-type map from render_config.json (exploded/section/ortho/standard)
    _view_type_map = {}  # view_key -> type string
    if os.path.isfile(config_path):
        try:
            with open(config_path, encoding="utf-8") as _rcf:
                _rc_data = json.load(_rcf)
            for _vk, _vcfg in _rc_data.get("camera", {}).items():
                _view_type_map[_vk.upper()] = _vcfg.get("type", "standard")
        except (OSError, json.JSONDecodeError):
            pass

    def _script_for_view(view_key):
        """Return (script_path, extra_args) based on view type from render_config."""
        vtype = _view_type_map.get(view_key.upper(), "standard")
        if vtype == "exploded" and os.path.isfile(exploded_script):
            return exploded_script, []
        if vtype == "section" and os.path.isfile(section_script):
            return section_script, []
        return render_script, ["--view", view_key]

    if args.view:
        # Single view — dispatch by type from config
        script, extra = _script_for_view(args.view)
        cmd = [blender, "-b", "-P", script, "--"] + render_args + extra
        ok, _ = _run_subprocess(cmd, f"render {args.view}", dry_run=args.dry_run, timeout=1200)
        if not ok:
            failures += 1
    else:
        # All views — run standard first, then any exploded/section scripts present
        cmd = [blender, "-b", "-P", render_script, "--"] + render_args + ["--all"]
        ok, _ = _run_subprocess(cmd, "render standard views", dry_run=args.dry_run, timeout=1200)
        if not ok:
            failures += 1

        if os.path.isfile(exploded_script):
            cmd = [blender, "-b", "-P", exploded_script, "--"] + render_args
            ok, _ = _run_subprocess(cmd, "render exploded view", dry_run=args.dry_run, timeout=600)
            if not ok:
                failures += 1

        if os.path.isfile(section_script):
            cmd = [blender, "-b", "-P", section_script, "--"] + render_args
            ok, _ = _run_subprocess(cmd, "render section view", dry_run=args.dry_run, timeout=600)
            if not ok:
                failures += 1

    if not args.dry_run:
        import time as _time
        _renders_dir = _custom_output_dir or os.path.join(DEFAULT_OUTPUT, "renders")
        _all_now = set(glob.glob(os.path.join(_renders_dir, "V*.png")))
        _new_files = sorted(_all_now - _pre_existing)
        # Deduplicate: when --timestamp is used, both V1_name_TS.png and
        # V1_name.png (latest copy) are new.  Keep only the timestamped one
        # to avoid enhance processing the same image twice.
        if _should_timestamp(args) and len(_new_files) > 1:
            import re as _re
            _ts_files = [f for f in _new_files if _re.search(r'_\d{8}_\d{4}\.png$', f)]
            if _ts_files:
                _new_files = _ts_files
        if _new_files:
            manifest = {
                "subsystem": getattr(args, "subsystem", ""),
                "timestamp": _time.strftime("%Y-%m-%dT%H:%M:%S"),
                "render_dir": _renders_dir,
                "files": _new_files,
                "partial": failures > 0,
            }
            manifest_path = os.path.join(_renders_dir, "render_manifest.json")
            with open(manifest_path, "w", encoding="utf-8") as _mf:
                json.dump(manifest, _mf, indent=2)
            log.info("Manifest written: %s (%d files%s)",
                     manifest_path, len(_new_files),
                     ", partial" if failures > 0 else "")

    return 1 if failures else 0


def cmd_enhance(args):
    """Run AI enhancement on rendered PNGs (Gemini or ComfyUI backend)."""
    from enhance_prompt import build_enhance_prompt, build_labeled_prompt, extract_view_key, view_sort_key

    # Determine backend: CLI arg > pipeline_config.json > default gemini
    _pcfg = _load_pipeline_config()
    backend = getattr(args, "backend", None) or _pcfg.get("enhance", {}).get("backend", "gemini")
    log.info("Enhance backend: %s", backend)
    if getattr(args, "labeled", False) and backend != "gemini":
        log.warning("--labeled is only supported with gemini backend; ignoring")

    if backend == "comfyui":
        # Pre-flight env check — catches CPU-only, missing models, server down
        _check_result = subprocess.run(
            [sys.executable, os.path.join(SKILL_ROOT, "comfyui_env_check.py"), "--quiet"],
            capture_output=True,
        )
        if _check_result.returncode != 0:
            subprocess.run(
                [sys.executable, os.path.join(SKILL_ROOT, "comfyui_env_check.py")],
            )
            log.error("ComfyUI environment check failed. Fix the issues above, then retry.")
            return 1
        from comfyui_enhancer import enhance_image as enhance_with_comfyui
    else:
        backend = "gemini"  # normalise
        gemini_script = get_gemini_script()
        if not gemini_script:
            log.error("gemini_gen.py not found. Set GEMINI_GEN_PATH or check installation.")
            log.error("Set GEMINI_GEN_PATH env var or install gemini_gen.py")
            return 1

    # Load render_config.json (full dict for prompt building) — must come before PNG sorting
    rc = {}
    _sub_name = getattr(args, "subsystem", None)
    # Auto-detect subsystem from manifest when not specified via CLI
    if not _sub_name:
        _manifest_search_dirs = []
        if getattr(args, "dir", None):
            _manifest_search_dirs.append(args.dir)
        _manifest_search_dirs.append(os.path.join(DEFAULT_OUTPUT, "renders"))
        for _mdir in _manifest_search_dirs:
            _manifest_path_check = os.path.join(_mdir, "render_manifest.json")
            if os.path.isfile(_manifest_path_check):
                with open(_manifest_path_check, encoding="utf-8") as _mf_check:
                    _sub_name = json.load(_mf_check).get("subsystem")
                if _sub_name:
                    log.info("Auto-detected subsystem from manifest: %s", _sub_name)
                break
    sub_dir = get_subsystem_dir(_sub_name) if _sub_name else None
    rc_path = os.path.join(sub_dir, "render_config.json") if sub_dir else None
    if rc_path and os.path.isfile(rc_path):
        with open(rc_path, encoding="utf-8") as f:
            rc = json.load(f)

    # P2: Auto-enrich rc with generated prompt data from params.py (in-memory only)
    if sub_dir and os.path.isfile(os.path.join(sub_dir, "params.py")):
        try:
            from prompt_data_builder import generate_prompt_data, merge_into_config
            _generated = generate_prompt_data(sub_dir, rc=rc)
            rc = merge_into_config(rc, _generated)
            log.info("Auto-enriched render_config from params.py")
        except Exception as _e:
            log.warning("prompt_data_builder auto-enrich failed (non-fatal): %s", _e)

    # Fail fast if an explicit subsystem was given but its directory doesn't exist
    if _sub_name and not sub_dir:
        log.error("Subsystem '%s' not found. Run 'cad-init %s' first or check the name.",
                  _sub_name, _sub_name)
        return 1

    render_dir = args.dir or os.path.join(DEFAULT_OUTPUT, "renders")
    manifest_path = os.path.join(render_dir, "render_manifest.json")
    if not os.path.isfile(manifest_path) and args.dir:
        # also check default location as fallback
        _default_manifest = os.path.join(DEFAULT_OUTPUT, "renders", "render_manifest.json")
        if os.path.isfile(_default_manifest):
            manifest_path = _default_manifest
    if os.path.isfile(manifest_path):
        with open(manifest_path, encoding="utf-8") as _mf:
            _manifest = json.load(_mf)
        pngs = sorted([p for p in _manifest.get("files", []) if os.path.isfile(p)],
                     key=lambda p: view_sort_key(p, rc))
        log.info("Using manifest: %d files (subsystem=%s, ts=%s)",
                 len(pngs), _manifest.get("subsystem", "?"), _manifest.get("timestamp", "?"))
    else:
        pngs = sorted([p for p in glob.glob(os.path.join(render_dir, "V*.png"))
                       if "_enhanced" not in os.path.basename(p)],
                      key=lambda p: view_sort_key(p, rc))
    if not pngs:
        log.error("No V*.png files found in %s", render_dir)
        return 1

    # Load model config
    model_arg = []
    pcfg_path = os.path.join(SKILL_ROOT, "pipeline_config.json")
    if os.path.isfile(pcfg_path):
        with open(pcfg_path, encoding="utf-8") as f:
            pcfg = json.load(f)
        enhance_cfg = pcfg.get("enhance", {})
        model_key = getattr(args, "model", None) or enhance_cfg.get("model", "")
        models = enhance_cfg.get("models", {})
        if model_key and model_key not in models:
            log.warning("Model key '%s' not found in pipeline_config.json models dict — using as raw model ID", model_key)
        model_id = models.get(model_key, model_key)  # fall back to raw value if not a key
        if model_id:
            model_arg = ["--model", model_id]

    failures = 0
    v1_done = False
    hero_image = None  # V1 enhanced result for multi-view anchoring

    # ── Multi-view consistency settings from pipeline_config ──
    _enhance_cfg = _pcfg.get("enhance", {})
    _ref_mode = _enhance_cfg.get("reference_mode", "none")
    _seed_from_image = _enhance_cfg.get("seed_from_image", False)
    _temperature = _enhance_cfg.get("temperature")  # None = don't send
    if _ref_mode != "none" or _seed_from_image or _temperature is not None:
        log.info("Enhance consistency: reference=%s, seed=%s, temperature=%s",
                 _ref_mode, _seed_from_image, _temperature)

    def _pixel_seed(image_path):
        """Deterministic seed from pixel content, ignoring file metadata.
        Returns value in INT32 range (0..2^31-1) as required by Gemini API."""
        import hashlib
        from PIL import Image as _SeedImg
        _im = _SeedImg.open(image_path)
        h = int(hashlib.md5(_im.tobytes()).hexdigest()[:8], 16)
        return h & 0x7FFFFFFF  # clamp to signed INT32 max

    def _compress_for_api(src_path, max_res=(1920, 1080), quality=95):
        """Compress image for API send. Returns (tmp_path, size_kb) or (None, 0).

        Gemini accepts up to 20MB per image. Only compress if over 4MB to
        preserve spatial detail (critical for viewpoint preservation).
        """
        import tempfile as _ctf_mod
        from PIL import Image as _CImg
        _src_size = os.path.getsize(src_path)
        if _src_size <= 4 * 1024 * 1024:
            return None, _src_size / 1024  # under 4MB, send original
        _im = _CImg.open(src_path).convert("RGB")
        _im.thumbnail(max_res, _CImg.LANCZOS)
        _tmp = _ctf_mod.NamedTemporaryFile(suffix=".jpg", delete=False)
        _tmp.close()
        _im.save(_tmp.name, "JPEG", quality=quality)
        return _tmp.name, os.path.getsize(_tmp.name) / 1024

    def _parse_gemini_output(stdout_text):
        """Extract saved image path from gemini_gen.py stdout."""
        for line in (stdout_text or "").split("\n"):
            if "图片已保存:" in line:
                return line[line.rfind("图片已保存:") + len("图片已保存:"):].strip()
            if "已保存:" in line:
                return line[line.rfind("已保存:") + len("已保存:"):].strip()
        return None

    for png in pngs:
        new_path = None  # reset each iteration (A5 fix)
        view_key = extract_view_key(png, rc)

        # ── Set reference flag in rc for prompt building (A1 fix) ──
        _use_ref = (_ref_mode == "v1_anchor" and hero_image
                    and view_key != "V1" and backend == "gemini")
        rc["_has_reference"] = _use_ref

        # Build prompt with all placeholders filled
        try:
            prompt = build_enhance_prompt(view_key, rc, is_v1_done=v1_done)
        except FileNotFoundError:
            prompt = ("Keep ALL geometry EXACTLY unchanged. Enhance surface materials "
                      "to photo-realistic quality with proper lighting and reflections.")

        # Compute seed (if enabled)
        _seed = _pixel_seed(png) if _seed_from_image else None

        if args.dry_run:
            log.info("  [DRY-RUN] %s prompt (%d chars):", view_key, len(prompt))
            log.info("  --- prompt start ---")
            for line in prompt.split("\n"):
                log.info("  %s", line)
            log.info("  --- prompt end ---")
            # Check for unfilled placeholders
            import re as _re
            residual = _re.findall(r'\{[a-z_]+\}', prompt)
            if residual:
                log.warning("  UNFILLED placeholders: %s", residual)
            if _seed is not None:
                log.info("  [DRY-RUN] seed: %d", _seed)
            if _use_ref:
                log.info("  [DRY-RUN] reference: (will use V1 enhanced result at runtime)")
            elif _ref_mode == "v1_anchor" and view_key != "V1":
                log.info("  [DRY-RUN] reference: (pending V1 completion)")
            if getattr(args, "labeled", False) and backend == "gemini":
                _lbl_prompt = build_labeled_prompt(view_key, rc, is_v1_done=v1_done)
                if _lbl_prompt != prompt:
                    log.info("  [DRY-RUN] labeled prompt (%d chars, +%d label chars)",
                             len(_lbl_prompt), len(_lbl_prompt) - len(prompt))
            if view_key == "V1":
                v1_done = True
            continue

        # Write prompt to temp file (avoid Windows argv length limit)
        import tempfile
        prompt_file = None
        _compressed_tmp = None
        _ref_compressed_tmp = None  # A6: separate tracking for reference temp file
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8"
            ) as f:
                f.write(prompt)
                prompt_file = f.name

            # ── ComfyUI backend ──────────────────────────────────────────
            if backend == "comfyui":
                log.info("  Running: enhance %s (%s, comfyui)",
                         os.path.basename(png), view_key)
                t0 = time.time()
                try:
                    raw_path = enhance_with_comfyui(png, prompt, _pcfg.get("enhance", {}).get("comfyui", {}), view_key, rc)
                except Exception as _ce:
                    log.error("  ComfyUI enhance failed for %s: %s",
                              os.path.basename(png), _ce)
                    failures += 1
                    continue
                elapsed = time.time() - t0
                log.info("  OK: enhance %s (%.1fs)", os.path.basename(png), elapsed)
                if view_key == "V1":
                    v1_done = True
                if raw_path and os.path.isfile(raw_path):
                    from datetime import datetime as _dt
                    src_stem = os.path.splitext(os.path.basename(png))[0]
                    ts = _dt.now().strftime("%Y%m%d_%H%M")
                    ext = os.path.splitext(raw_path)[1]
                    new_name = f"{src_stem}_{ts}_enhanced{ext}"
                    new_path = os.path.join(os.path.dirname(png), new_name)
                    shutil.copy2(raw_path, new_path)
                    try:
                        os.remove(raw_path)
                    except OSError:
                        pass
                    log.info("  Saved: %s", new_path)
                else:
                    log.warning("  Could not locate ComfyUI output for %s",
                                os.path.basename(png))
                continue  # skip Gemini block

            # ── Gemini backend ───────────────────────────────────────────
            # Compress source image (upgraded: 1280×720, quality 90)
            _img_to_send = png
            try:
                _ctmp, _csz = _compress_for_api(png, (1280, 720), 90)
                if _ctmp:
                    _compressed_tmp = _ctmp
                    _img_to_send = _compressed_tmp
                    log.info("  Compressed %s: %.0fKB → %.0fKB",
                             os.path.basename(png),
                             os.path.getsize(png) / 1024, _csz)
            except Exception as _ce:
                log.warning("  Could not compress image: %s", _ce)

            # Build command with optional reference, seed, temperature
            cmd = [sys.executable, gemini_script,
                   "--prompt-file", prompt_file,
                   "--image", _img_to_send] + model_arg

            ref_args = []
            if _use_ref and hero_image:
                # Compress reference image more aggressively to keep payload small
                try:
                    _rctmp, _rsz = _compress_for_api(hero_image, (1280, 720), 90)
                    _ref_to_send = _rctmp if _rctmp else hero_image
                    if _rctmp:
                        _ref_compressed_tmp = _rctmp
                    ref_args = ["--reference", _ref_to_send]
                    log.info("  Reference: %s (%.0fKB)",
                             os.path.basename(hero_image), _rsz)
                except Exception as _re_err:
                    log.warning("  Could not prepare reference image: %s", _re_err)

            seed_args = []
            if _seed is not None:
                seed_args = ["--seed", str(_seed)]

            temp_args = []
            if _temperature is not None:
                temp_args = ["--temperature", str(_temperature)]

            cmd = cmd + ref_args + seed_args + temp_args

            log.info("  Running: enhance %s (%s, %d chars%s)",
                     os.path.basename(png), view_key, len(prompt),
                     " +ref" if ref_args else "")
            t0 = time.time()
            result = None
            for _attempt in range(3):
                if _attempt > 0:
                    log.info("  Retry %d/2 for %s ...", _attempt, os.path.basename(png))
                    time.sleep(10)
                try:
                    result = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=180,
                        encoding="utf-8", errors="replace",
                    )
                    if result.returncode == 0:
                        break
                except subprocess.TimeoutExpired:
                    log.warning("  TIMEOUT attempt %d for %s", _attempt + 1, os.path.basename(png))
                    result = None

            # ── Fallback: retry without reference if reference mode failed ──
            if (result is None or result.returncode != 0) and ref_args:
                log.warning("  Reference mode failed for %s, retrying without reference...",
                            os.path.basename(png))
                cmd_fallback = [a for a in cmd if a not in ref_args
                                and a != "--reference"]
                try:
                    result = subprocess.run(
                        cmd_fallback, capture_output=True, text=True, timeout=180,
                        encoding="utf-8", errors="replace",
                    )
                except subprocess.TimeoutExpired:
                    result = None

            elapsed = time.time() - t0
            if result is None or result.returncode != 0:
                rc_val = result.returncode if result is not None else -1
                log.error("  FAILED enhance %s (exit %d, %.1fs)",
                          os.path.basename(png), rc_val, elapsed)
                if result is not None and result.stdout:
                    for line in result.stdout.strip().split("\n")[-10:]:
                        log.error("    STDOUT: %s", line)
                if result is not None and result.stderr:
                    for line in result.stderr.strip().split("\n")[-5:]:
                        log.error("    STDERR: %s", line)
                failures += 1
                continue
            log.info("  OK: enhance %s (%.1fs)", os.path.basename(png), elapsed)

            # Mark V1 done for consistency anchor on subsequent views
            if view_key == "V1":
                v1_done = True

            # Rename gemini output: V*_YYYYMMDD_HHMM_enhanced.ext → same dir as source
            gemini_path = _parse_gemini_output(result.stdout)
            if gemini_path and os.path.isfile(gemini_path):
                from datetime import datetime as _dt
                src_stem = os.path.splitext(os.path.basename(png))[0]
                ts = _dt.now().strftime("%Y%m%d_%H%M")
                ext = os.path.splitext(gemini_path)[1]
                new_name = f"{src_stem}_{ts}_enhanced{ext}"
                new_path = os.path.join(os.path.dirname(png), new_name)
                shutil.copy2(gemini_path, new_path)
                try:
                    os.remove(gemini_path)
                except OSError:
                    pass  # copied successfully, removal is best-effort
                log.info("  Saved: %s", new_path)

                # ── Set hero image after V1 succeeds (A5 fix) ──
                if view_key == "V1" and _ref_mode == "v1_anchor":
                    hero_image = new_path
                    log.info("  Hero image set: %s", os.path.basename(new_path))
            else:
                log.warning("  Could not locate gemini output for %s",
                            os.path.basename(png))

        except subprocess.TimeoutExpired:
            log.error("  TIMEOUT enhance %s (>180s)", os.path.basename(png))
            failures += 1
        except FileNotFoundError as e:
            log.error("  NOT FOUND: %s", e)
            failures += 1
        finally:
            if prompt_file and os.path.isfile(prompt_file):
                os.unlink(prompt_file)
            # Note: _compressed_tmp cleanup deferred until after labeled call

        # ── Labeled version (second Gemini call, --labeled only) ────────────
        _has_labels = bool(rc.get("labels", {}).get(view_key))
        if (getattr(args, "labeled", False) and backend == "gemini"
                and not args.dry_run and _has_labels):
            _labeled_prompt_file = None
            # Use compressed image if available, else original PNG
            _labeled_img = _compressed_tmp if (_compressed_tmp and os.path.isfile(_compressed_tmp)) else png
            try:
                labeled_prompt = build_labeled_prompt(view_key, rc, is_v1_done=v1_done)
                import tempfile as _tf2
                with _tf2.NamedTemporaryFile(
                    mode="w", suffix=".txt", delete=False, encoding="utf-8"
                ) as _lf:
                    _lf.write(labeled_prompt)
                    _labeled_prompt_file = _lf.name

                log.info("  Running: labeled enhance %s (%s)", os.path.basename(png), view_key)
                t0_l = time.time()
                _cmd_l = [sys.executable, gemini_script,
                          "--prompt-file", _labeled_prompt_file,
                          "--image", _labeled_img]
                _cmd_l += model_arg
                _res_l = subprocess.run(
                    _cmd_l, capture_output=True, timeout=300,
                    encoding="utf-8", errors="replace"
                )
                elapsed_l = time.time() - t0_l
                if _res_l.returncode == 0:
                    _lbl_path = None
                    for _line in (_res_l.stdout or "").split("\n"):
                        if "图片已保存:" in _line:
                            _lbl_path = _line[_line.rfind("图片已保存:") + len("图片已保存:"):].strip()
                            break
                        if "已保存:" in _line:
                            _lbl_path = _line[_line.rfind("已保存:") + len("已保存:"):].strip()
                            break
                    if _lbl_path and os.path.isfile(_lbl_path):
                        from datetime import datetime as _dt2
                        _src_stem = os.path.splitext(os.path.basename(png))[0]
                        _ts2 = _dt2.now().strftime("%Y%m%d_%H%M")
                        _ext2 = os.path.splitext(_lbl_path)[1]
                        _lbl_name = f"{_src_stem}_{_ts2}_enhanced_labeled_en{_ext2}"
                        _lbl_dest = os.path.join(os.path.dirname(png), _lbl_name)
                        shutil.copy2(_lbl_path, _lbl_dest)
                        try:
                            os.remove(_lbl_path)
                        except OSError:
                            pass
                        log.info("  Labeled: %s (%.1fs)", _lbl_name, elapsed_l)
                    else:
                        log.warning("  Labeled output not found for %s", os.path.basename(png))
                else:
                    log.warning("  Labeled enhance failed for %s (exit %d, %.1fs)",
                                os.path.basename(png), _res_l.returncode, elapsed_l)
            except Exception as _le:
                log.warning("  Labeled enhance error for %s: %s", os.path.basename(png), _le)
            finally:
                if _labeled_prompt_file and os.path.isfile(_labeled_prompt_file):
                    os.unlink(_labeled_prompt_file)

        # Clean up compressed temp images (deferred from first call's finally)
        if _compressed_tmp and os.path.isfile(_compressed_tmp):
            os.unlink(_compressed_tmp)
        if _ref_compressed_tmp and os.path.isfile(_ref_compressed_tmp):
            os.unlink(_ref_compressed_tmp)

    return 1 if failures else 0


def cmd_annotate(args):
    """Add component labels to enhanced images."""
    annotate_script = os.path.join(SKILL_ROOT, "annotate_render.py")
    if not os.path.isfile(annotate_script):
        log.error("annotate_render.py not found at %s", annotate_script)
        return 1

    sub_dir = get_subsystem_dir(args.subsystem)
    # Auto-detect subsystem from manifest if not specified
    if not sub_dir and not args.config:
        _detect_dirs = []
        if getattr(args, "dir", None):
            _detect_dirs.append(args.dir)
        _detect_dirs.append(os.path.join(DEFAULT_OUTPUT, "renders"))
        for _mdir in _detect_dirs:
            _mp = os.path.join(_mdir, "render_manifest.json")
            if os.path.isfile(_mp):
                with open(_mp, encoding="utf-8") as _mf:
                    _sub = json.load(_mf).get("subsystem")
                if _sub:
                    sub_dir = get_subsystem_dir(_sub)
                    if sub_dir:
                        log.info("Auto-detected subsystem from manifest: %s", _sub)
                break
    config_path = args.config
    if not config_path and sub_dir:
        config_path = os.path.join(sub_dir, "render_config.json")
    if not config_path or not os.path.isfile(config_path):
        log.error("No render_config.json found. Use --config or --subsystem.")
        return 1

    img_dir = args.dir or os.path.join(DEFAULT_OUTPUT, "renders")
    _manifest_path = os.path.join(img_dir, "render_manifest.json")
    if not os.path.isfile(_manifest_path) and args.dir:
        _default_manifest = os.path.join(DEFAULT_OUTPUT, "renders", "render_manifest.json")
        if os.path.isfile(_default_manifest):
            _manifest_path = _default_manifest
    _use_manifest = os.path.isfile(_manifest_path)
    if _use_manifest:
        log.info("Annotate using manifest: %s", _manifest_path)
    for lang in (args.lang.split(",") if "," in args.lang else [args.lang]):
        if _use_manifest:
            cmd = [sys.executable, annotate_script,
                   "--manifest", _manifest_path,
                   "--config", config_path,
                   "--lang", lang.strip()]
        else:
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
    if not review_json or not os.path.isfile(review_json):
        return 0  # No review data, continue

    with open(review_json, encoding="utf-8") as f:
        data = json.load(f)

    critical = data.get("critical", 0)
    if critical > 0:
        log.error("DESIGN_REVIEW still has %d CRITICAL issue(s). Cannot continue.", critical)
        return 1

    return 0


def _agent_review_pause(args):
    """Pause pipeline for Agent-driven review. Exit 10 = waiting for Agent."""
    review_json = _resolve_review_json(args)
    if os.path.isfile(review_json):
        log.info("AGENT_REVIEW_JSON=%s", review_json)
        log.info("Agent 审查模式: 请读取上述 JSON，逐项审查后用 --skip-spec 继续。")
    return 10


def cmd_full(args):
    """Full pipeline: spec → codegen → build → render → enhance → annotate."""
    if not args.subsystem:
        log.error("--subsystem is required for 'full' pipeline.")
        return 1
    log.info("=" * 60)
    log.info("  Full pipeline for: %s", args.subsystem)
    log.info("=" * 60)
    t0 = time.time()

    steps = []

    # Phase 1: Spec generation (requires --design-doc or auto-resolve)
    if not args.skip_spec:
        if getattr(args, "agent_review", False):
            # Agent mode: run review-only, output JSON path, exit for Agent processing
            args.review_only = True
            steps.append(("SPEC_REVIEW", lambda: cmd_spec(args)))
            # After review-only, return exit code 10 for Agent to process
            steps.append(("AGENT_WAIT", lambda: _agent_review_pause(args)))
        else:
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
def cmd_init(args):
    """Scaffold a new subsystem directory with template files."""
    sub_name = args.subsystem
    if not sub_name:
        log.error("--subsystem is required for init")
        return 1

    # Determine output dir
    config = _load_config()
    output_dir = config.get("output_dir", "./output")
    if not os.path.isabs(output_dir):
        output_dir = os.path.join(PROJECT_ROOT, output_dir)
    sub_dir = os.path.join(output_dir, sub_name)

    if os.path.exists(sub_dir) and not args.force:
        log.error("Directory already exists: %s  (use --force to overwrite)", sub_dir)
        return 1

    os.makedirs(sub_dir, exist_ok=True)
    log.info("Scaffolding subsystem '%s' → %s", sub_name, sub_dir)

    # ── render_config.json template ──────────────────────────────────────────
    rc_template = {
        "version": 1,
        "subsystem": {
            "name": sub_name,
            "name_cn": args.name_cn or sub_name,
            "part_prefix": (args.prefix or sub_name.upper()),
            "glb_file": f"{sub_name}_assembly.glb",
            "bounding_radius_mm": 300
        },
        "coordinate_system": "Z-axis vertical. Describe your coordinate convention here.",
        "materials": {
            "body": {"preset": "brushed_aluminum", "label": "Main body",
                     "name_cn": "主体", "name_en": "Main Body"},
            "fastener": {"preset": "stainless_304", "label": "Fasteners",
                         "name_cn": "紧固件", "name_en": "Fasteners"}
        },
        "camera": {
            "V1": {
                "name": "V1_front_iso",
                "type": "standard",
                "location": [350, -380, 320],
                "target": [0, 0, 50],
                "lens_mm": 50,
                "description": "Front isometric view"
            },
            "V2": {
                "name": "V2_rear_oblique",
                "type": "standard",
                "location": [-320, 350, 400],
                "target": [0, 0, 50],
                "lens_mm": 50,
                "description": "Rear oblique view"
            },
            "V3": {
                "name": "V3_exploded",
                "type": "exploded",
                "location": [400, -400, 500],
                "target": [0, 0, 0],
                "description": "Exploded view (use render_exploded.py)"
            },
            "V4": {
                "name": "V4_ortho_front",
                "type": "ortho",
                "location": [0, -500, 80],
                "target": [0, 0, 80],
                "ortho": True,
                "ortho_scale": 400,
                "description": "Front orthographic view"
            }
        },
        "components": {
            "body": {
                "name_cn": "主体",
                "name_en": "Main Body"
            }
        },
        "labels": {
            "_doc": "Only visible components per view. Coords at 1920x1080 ref, auto-scaled.",
            "V1": [
                {
                    "component": "body",
                    "anchor": [600, 400],
                    "label": [1600, 200]
                }
            ]
        }
    }

    rc_path = os.path.join(sub_dir, "render_config.json")
    if not os.path.isfile(rc_path) or args.force:
        with open(rc_path, "w", encoding="utf-8") as f:
            json.dump(rc_template, f, indent=2, ensure_ascii=False)
        log.info("  Created: render_config.json")
    else:
        log.info("  Skipped (exists): render_config.json")

    # ── params.py template ───────────────────────────────────────────────────
    params_path = os.path.join(sub_dir, "params.py")
    params_content = f'''#!/usr/bin/env python3
"""
params.py — Single source of truth for {sub_name} dimensions.
Edit this file to change part geometry.
"""

# ── Global dimensions ────────────────────────────────────────────────────────
OVERALL_DIA   = 200  # mm  overall envelope diameter
OVERALL_H     = 100  # mm  overall height

# ── Material identifiers ─────────────────────────────────────────────────────
MATERIAL_BODY    = "7075-T6 aluminum alloy"
MATERIAL_SEALS   = "NBR rubber"

# ── Assembly metadata ────────────────────────────────────────────────────────
PART_PREFIX      = "{args.prefix or sub_name.upper()}"
ASSEMBLY_NAME    = "{sub_name}_assembly"
'''
    if not os.path.isfile(params_path) or args.force:
        with open(params_path, "w", encoding="utf-8") as f:
            f.write(params_content)
        log.info("  Created: params.py")
    else:
        log.info("  Skipped (exists): params.py")

    # ── design doc placeholder ───────────────────────────────────────────────
    doc_base = config.get("doc_dir", "docs/design")
    if not os.path.isabs(doc_base):
        doc_base = os.path.join(PROJECT_ROOT, doc_base)
    os.makedirs(doc_base, exist_ok=True)
    doc_path = os.path.join(doc_base, f"XX-{sub_name}.md")
    doc_content = f"""# {args.name_cn or sub_name} 设计文档

<!-- Replace XX with the chapter number and rename this file -->

## 1. 设计目标

TODO: 描述本子系统的设计目标

## 2. 关键参数

TODO: 列出关键尺寸和参数

## 3. 装配关系

TODO: 描述部件间的装配关系
"""
    if not os.path.isfile(doc_path) or args.force:
        with open(doc_path, "w", encoding="utf-8") as f:
            f.write(doc_content)
        log.info("  Created: %s", doc_path)
    else:
        log.info("  Skipped (exists): %s", doc_path)

    log.info("")
    log.info("Next steps:")
    log.info("  1. Edit %s/params.py with real dimensions", sub_dir)
    log.info("  2. Edit %s with your design requirements", doc_path)
    log.info("  3. Edit %s/render_config.json — update camera views and labels", sub_dir)
    log.info("  4. Run: python cad_pipeline.py full --subsystem %s --design-doc %s",
             sub_name, doc_path)
    return 0


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
    p_spec.add_argument("--subsystem", "-s", default=None)
    p_spec.add_argument("--design-doc", help="Path to design document (NN-*.md)")
    p_spec.add_argument("--auto-fill", action="store_true", help="Auto-fill computable values")
    p_spec.add_argument("--force", action="store_true", help="Force regeneration")
    p_spec.add_argument("--review-only", action="store_true",
                        help="Generate DESIGN_REVIEW only (no interaction, no CAD_SPEC.md). For Agent-driven review.")
    p_spec.add_argument("--proceed", action="store_true",
                        help="Skip interaction, generate CAD_SPEC.md with existing data")
    p_spec.add_argument("--supplements", default=None,
                        help="JSON string of Agent-collected supplements, e.g. '{\"B3\":\"4xM4\",\"D2\":\"__AUTO__\"}'. "
                             "Written to user_supplements.json then spec is generated.")

    # codegen
    p_codegen = sub.add_parser("codegen", help="Generate CadQuery scaffolds from CAD_SPEC.md")
    p_codegen.add_argument("--subsystem", "-s", default=None)
    p_codegen.add_argument("--force", action="store_true", help="Overwrite existing files")

    # build
    p_build = sub.add_parser("build", help="Build STEP + DXF files")
    p_build.add_argument("--subsystem", "-s", default=None)
    p_build.add_argument("--render", action="store_true", help="Also render after build")
    p_build.add_argument("--skip-orientation", dest="skip_orientation", action="store_true",
                         help="Bypass orientation_check.py pre-gate (not recommended)")

    # render
    p_render = sub.add_parser("render", help="Blender Cycles rendering")
    p_render.add_argument("--subsystem", "-s", default=None)
    p_render.add_argument("--view", help="Single view (V1-V5)")
    p_render.add_argument("--timestamp", action="store_true", help="Append timestamp to filenames")
    p_render.add_argument("--output-dir", help="Override output directory for rendered PNGs")

    # enhance
    p_enhance = sub.add_parser("enhance", help="AI enhancement (Gemini or ComfyUI)")
    p_enhance.add_argument("--subsystem", "-s", default=None)
    p_enhance.add_argument("--dir", help="Directory with V*.png files")
    p_enhance.add_argument("--backend", choices=["gemini", "comfyui"],
                           help="Override enhance backend (default: from pipeline_config.json)")
    p_enhance.add_argument("--labeled", action="store_true",
                           help="Also generate English-labeled version via Gemini (gemini backend only)")
    p_enhance.add_argument("--model", default=None,
                           help="Override model key from pipeline_config.json (e.g. nano_banana_2)")

    # annotate
    p_annotate = sub.add_parser("annotate", help="Add component labels")
    p_annotate.add_argument("--subsystem", "-s", default=None)
    p_annotate.add_argument("--config", help="render_config.json path")
    p_annotate.add_argument("--dir", help="Directory with images")
    p_annotate.add_argument("--lang", default="cn,en", help="Languages (default: cn,en)")

    # full
    p_full = sub.add_parser("full", help="Full pipeline: spec→codegen→build→render→enhance→annotate")
    p_full.add_argument("--subsystem", "-s", default=None)
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
    p_full.add_argument("--labeled", action="store_true",
                        help="Generate English-labeled enhanced images (gemini only)")
    p_full.add_argument("--agent-review", action="store_true",
                        help="Agent-driven review: run Phase 1 review-only, output JSON path, exit 10 for Agent to process")

    # init
    p_init = sub.add_parser("init", help="Scaffold a new subsystem directory")
    p_init.add_argument("--subsystem", required=True, help="Subsystem directory name (e.g. my_device)")
    p_init.add_argument("--name-cn", default="", help="Chinese display name (e.g. 末端执行机构)")
    p_init.add_argument("--prefix", default="", help="Part number prefix (e.g. GIS-EE)")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing files")

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
        handlers=[logging.StreamHandler(stream=sys.stderr)],
    )
    # Ensure log handler uses UTF-8 on Windows
    for handler in logging.root.handlers:
        if hasattr(handler, "stream") and hasattr(handler.stream, "reconfigure"):
            handler.stream.reconfigure(encoding="utf-8", errors="replace")

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
        "init": cmd_init,
        "status": cmd_status,
        "env-check": cmd_env_check,
    }

    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
