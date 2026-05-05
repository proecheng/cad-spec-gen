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
    python cad_pipeline.py enhance-check --subsystem end_effector --dir cad/output/renders/end_effector/<run_id>
    python cad_pipeline.py annotate --config render_config.json --lang cn
    python cad_pipeline.py full --subsystem end_effector  # all 6 phases
    python cad_pipeline.py model-audit --subsystem end_effector
    python cad_pipeline.py model-import --subsystem end_effector --part-no P-001 --step models/p.step
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
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

# Force UTF-8 output on Windows to avoid GBK encoding issues
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
import time

from cad_paths import (
    SKILL_ROOT,
    PROJECT_ROOT,
    get_blender_path,
    get_subsystem_dir,
    get_output_dir,
    get_gemini_script,
)
from tools.model_context import ModelProjectContext

# A1-3：SW 检测函数。非 Windows / pywin32 缺失均被 sw_detect 内部短路成
# SwInfo(installed=False)，本导入对跨平台无害。top-level 是必需——
# `mock.patch('cad_pipeline.detect_solidworks')` 需要名字存在于本模块命名空间。
from adapters.solidworks.sw_detect import detect_solidworks

log = logging.getLogger("cad_pipeline")

CAD_DIR = os.path.join(PROJECT_ROOT, "cad")
TOOLS_DIR = os.path.join(SKILL_ROOT, "tools")
CONFIG_PATH = os.path.join(SKILL_ROOT, "config", "gisbot.json")
PIPELINE_CONFIG_PATH = os.path.join(SKILL_ROOT, "pipeline_config.json")
DEFAULT_OUTPUT = get_output_dir()


def _deploy_tool_modules(sub_dir: str):
    """Copy shared Python tool modules to a subsystem directory.

    These modules are needed at runtime by generated code (ee_*.py, build_all.py):
      - drawing.py          — ezdxf GB/T drawing primitives
      - draw_three_view.py  — ThreeViewSheet class (imports cad_spec_defaults)
      - cq_to_dxf.py        — CadQuery→DXF HLR projection bridge
      - render_dxf.py       — DXF→PNG batch renderer
      - render_config.py    — render camera / pose helpers
      - cad_spec_defaults.py — surface roughness + part-no helper tables,
                               imported lazily from draw_three_view.save()
    Only copies if source is newer or target is missing (scaffold-safe).
    """
    import shutil

    tool_files = [
        "drawing.py",
        "draw_three_view.py",
        "cq_to_dxf.py",
        "render_dxf.py",
        "render_config.py",
        "cad_spec_defaults.py",
    ]
    for fname in tool_files:
        src = os.path.join(SKILL_ROOT, fname)
        dst = os.path.join(sub_dir, fname)
        if not os.path.isfile(src):
            continue
        if os.path.isfile(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
            continue  # Target is up-to-date
        shutil.copy2(src, dst)
        log.info("  Deployed: %s → %s", fname, os.path.basename(sub_dir))


def _resolve_camera_coords(rc):
    """Ensure all camera entries in rc have location/target fields.

    For spherical entries (azimuth_deg/elevation_deg/distance_factor),
    computes cartesian location/target using standard spherical-to-cartesian
    conversion. Original spherical fields are preserved for consumers that
    prefer them (e.g. enhance_prompt.py reads azimuth_deg directly).

    This function is the single resolve point — downstream consumers can
    safely call cam.get("location") without checking coordinate format.

    Math matches render_config.py camera_to_blender() — pure spherical-to-
    cartesian, no subsystem-specific logic.
    """
    import math as _m

    br = rc.get("subsystem", {}).get("bounding_radius_mm", 0)
    if not br:
        # Auto-derive from §6.4 envelopes if available
        spec_path = os.path.join(
            get_subsystem_dir(rc.get("subsystem", {}).get("name", "")) or "",
            "CAD_SPEC.md",
        )
        if os.path.isfile(spec_path):
            try:
                from codegen.gen_assembly import parse_envelopes

                envs = parse_envelopes(spec_path)
                if envs:
                    br = max(max(e) for e in envs.values()) * 1.5
            except Exception:
                pass
        if not br:
            br = 300  # ultimate fallback
    for cam in rc.get("camera", {}).values():
        if "azimuth_deg" in cam and "location" not in cam:
            az = _m.radians(cam["azimuth_deg"])
            el = _m.radians(cam.get("elevation_deg", 0))
            dist = br * cam.get("distance_factor", 2.5)
            tgt = cam.get("target", [0, 0, br * 0.33])
            cam["location"] = [
                dist * _m.cos(el) * _m.cos(az) + tgt[0],
                dist * _m.cos(el) * _m.sin(az) + tgt[1],
                dist * _m.sin(el) + tgt[2],
            ]
            cam["target"] = list(tgt)


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


def _canonical_subsystem_name(subsystem_name, config=None):
    """Return the canonical cad_dir for a subsystem name or alias."""
    if not subsystem_name:
        return None
    if config is None:
        config = _load_config()
    for _chapter, info in config.get("subsystems", {}).items():
        aliases = [
            info.get("cad_dir", ""),
            info.get("name", ""),
            *info.get("aliases", []),
        ]
        if subsystem_name in aliases:
            return info.get("cad_dir", subsystem_name)
    return subsystem_name


def _infer_subsystem_from_design_doc(design_doc, config=None):
    """Infer canonical subsystem cad_dir from an NN-*.md design document name."""
    if not design_doc:
        return None
    if config is None:
        config = _load_config()
    stem = os.path.splitext(os.path.basename(str(design_doc)))[0]
    m = re.match(r"(\d{2})-", stem)
    if not m:
        return None
    info = config.get("subsystems", {}).get(m.group(1), {})
    return info.get("cad_dir") or None


def _ensure_spec_subsystem(args, design_doc, config=None):
    """Populate args.subsystem for spec mode from explicit alias or design doc."""
    if config is None:
        config = _load_config()
    current = getattr(args, "subsystem", None)
    resolved = (
        _canonical_subsystem_name(current, config)
        if current
        else _infer_subsystem_from_design_doc(design_doc, config)
    )
    if resolved and resolved != current:
        setattr(args, "subsystem", resolved)
        if current:
            log.info("Canonical subsystem: %s → %s", current, resolved)
        else:
            log.info("Auto-detected subsystem from design doc: %s", resolved)
    return resolved


def _build_blender_env():
    """A1-3 + A1 重构 Track A §3.3：构造 Blender subprocess 的环境变量。

    基于父进程 env 的拷贝。若 SW 装了 + textures_dir 有效：
      1. 注入 SW_TEXTURES_DIR（原 A1-3 行为，render_3d.py 的
         _resolve_texture_path 依赖它做相对路径 → 绝对路径解析）
      2. 调 adapters.solidworks.sw_texture_backfill.backfill_presets_for_sw()
         给 MATERIAL_PRESETS 副本合并 SW 纹理字段 → 落盘
         artifacts/{run}/runtime_materials.json → env CAD_RUNTIME_MATERIAL_PRESETS_JSON
         指该路径，让 Blender 子进程 render_3d.py 启动时加载覆盖内置 preset

    SW 未装 / textures_dir 空 / 目录不存在 → 两条都不注入。
    Blender 子进程 env 缺 → MATERIAL_PRESETS 保持纯 PBR（preset 定义层干净）。

    lazy import：非 Windows 平台 detect_solidworks() 立即返 installed=False；
    pywin32 缺失也按"未装"处理，不抛异常。
    """
    env = os.environ.copy()
    try:
        sw = detect_solidworks()
    except Exception as exc:
        # 探测本身抛（非典型：非 Windows / pywin32 缺都已被 detect_solidworks
        # 内部短路）— 不阻塞 render，退回裸父进程 env
        log.debug("SW detection skipped (%s): %s", type(exc).__name__, exc)
        return env

    if not (
        getattr(sw, "installed", False)
        and getattr(sw, "textures_dir", "")
        and os.path.isdir(sw.textures_dir)
    ):
        return env

    # —— (1) SW_TEXTURES_DIR（A1-3 原有）——
    env["SW_TEXTURES_DIR"] = sw.textures_dir
    log.info("SW_TEXTURES_DIR -> %s (injected into Blender env)", sw.textures_dir)

    # —— (2) runtime_materials.json（A1 重构）——
    try:
        import sys as _sys
        _here = os.path.abspath(os.path.dirname(__file__))
        if _here not in _sys.path:
            _sys.path.insert(0, _here)
        import render_config as _rcfg
        from adapters.solidworks.sw_texture_backfill import backfill_presets_for_sw

        backfilled = backfill_presets_for_sw(_rcfg.MATERIAL_PRESETS, sw)

        # 落盘到 artifacts/{run_id}/runtime_materials.json
        # CAD_RUN_ARTIFACTS_DIR 由 pipeline orchestrator 提前 set；缺则写到 tmp
        artifact_dir = os.environ.get("CAD_RUN_ARTIFACTS_DIR")
        if artifact_dir and os.path.isdir(artifact_dir):
            json_path = os.path.join(artifact_dir, "runtime_materials.json")
        else:
            import tempfile
            json_path = os.path.join(tempfile.gettempdir(), "runtime_materials.json")

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(
                {k: dict(v) for k, v in backfilled.items()},
                f, ensure_ascii=False, indent=2,
            )
        env["CAD_RUNTIME_MATERIAL_PRESETS_JSON"] = json_path
        log.info("CAD_RUNTIME_MATERIAL_PRESETS_JSON -> %s", json_path)
    except Exception as exc:
        log.warning("runtime_materials.json 回填失败（preset 将走 v2.11 纯色）：%s", exc)

    return env


def _run_subprocess(cmd, label, dry_run=False, timeout=600, warn_exit_codes=None, env=None):
    """Run a subprocess with error capture. Returns (success, elapsed).

    Parameters
    ----------
    warn_exit_codes : set[int] | None
        Exit codes that should be treated as "completed with warnings" rather
        than as hard failures. A match still returns success=True but logs
        a WARNING-level line with the trailing stderr so the pipeline
        continues. Used by gen_parts.py (exit 2 = scaffolds emitted with
        unfilled TODO markers — valid scaffolds, just not yet hand-finalized).
    env : dict | None
        Optional environment variable mapping passed through to subprocess.run.
        None (default) preserves the historical behavior of inheriting the
        parent process env. Used by Track A §3.3 SW texture bridge (A1) to
        inject SW_TEXTURES_DIR into the Blender subprocess so render_3d.py
        can resolve SolidWorks-installed PBR textures.
    """
    if dry_run:
        log.info("  [DRY-RUN] Would run: %s", " ".join(cmd[:6]))
        return True, 0.0

    warn_codes = set(warn_exit_codes or ())

    log.info("  Running: %s", label)
    t0 = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        elapsed = time.time() - t0
        if result.returncode in warn_codes:
            log.warning(
                "  WARN %s (exit %d, %.1fs) — continuing",
                label,
                result.returncode,
                elapsed,
            )
            # Surface a short stderr tail so the warning is actionable,
            # but do not treat as failure.
            if result.stderr:
                for line in result.stderr.strip().split("\n")[-5:]:
                    log.warning("    %s", line)
            return True, elapsed
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
        cfg = _load_config()
        output_dir = os.path.join(PROJECT_ROOT, "output")
        sub_cfg = cfg.get("subsystems", {})
        cad_subdir = None
        sub_name = _canonical_subsystem_name(
            getattr(args, "subsystem", None),
            cfg,
        )
        if not sub_name:
            sub_name = _infer_subsystem_from_design_doc(
                getattr(args, "design_doc", None),
                cfg,
            )
        if not sub_name:
            log.warning("No --subsystem specified; cannot locate DESIGN_REVIEW.json")
            return None
        for _ch, info in sub_cfg.items():
            aliases = [
                info.get("cad_dir", ""),
                info.get("name", ""),
                *info.get("aliases", []),
            ]
            if sub_name in aliases or sub_name == info.get("cad_dir"):
                cad_subdir = info.get("cad_dir", sub_name)
                break
        if not cad_subdir:
            cad_subdir = sub_name
        return os.path.join(output_dir, cad_subdir, "DESIGN_REVIEW.json")
    except (OSError, json.JSONDecodeError):
        sub_name = getattr(args, "subsystem", None) or _infer_subsystem_from_design_doc(
            getattr(args, "design_doc", None),
        )
        if not sub_name:
            return None
        return os.path.join(DEFAULT_OUTPUT, sub_name, "DESIGN_REVIEW.json")


def _show_review_summary(review_json_path):
    """Print review summary and return (critical, warning, auto_fill, auto_fill_items) counts."""
    if not review_json_path:
        return 0, 0, 0, []
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
    log.info(
        "  CRITICAL: %d | WARNING: %d | INFO: %d | OK: %d", c, w, info_count, ok_count
    )
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
    auto_fill_items = [
        item.get("id", "") for item in items if item.get("auto_fill") == "是"
    ]
    return c, w, af, auto_fill_items


def _infer_assembly_layers(review_json_path):
    """从 CAD_SPEC.md BOM树推断装配层叠表初稿。"""
    spec_path = review_json_path.replace("DESIGN_REVIEW.json", "CAD_SPEC.md")
    # Try cad/ path too
    if not os.path.isfile(spec_path):
        # output/end_effector/DESIGN_REVIEW.json -> cad/end_effector/CAD_SPEC.md
        spec_path = spec_path.replace(
            os.sep + "output" + os.sep, os.sep + "cad" + os.sep
        )
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
        if (
            in_bom
            and line.startswith("| ")
            and "---" not in line
            and "料号" not in line
        ):
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
        if part_no.count("-") <= 2 and not any(
            c.isdigit() for c in part_no.split("-")[-1:][0] if part_no.split("-")[-1:]
        ):
            pass
        is_assembly = part_no.count("-") == 2  # GIS-EE-001
        is_part = part_no.count("-") == 3  # GIS-EE-001-01
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


def _enrich_render_config_materials(sub_dir):
    """Auto-populate component.material from comp_key↔materials fuzzy match.

    Called after codegen to bridge components (with bom_id) to materials
    (with PBR presets). Writes back to render_config.json if changes made.
    """
    rc_path = os.path.join(sub_dir, "render_config.json")
    if not os.path.isfile(rc_path):
        return
    with open(rc_path, encoding="utf-8") as f:
        rc = json.load(f)

    materials = rc.get("materials", {})
    components = rc.get("components", {})
    changed = False

    for comp_key, comp in components.items():
        if comp_key.startswith("_") or "material" in comp:
            continue

        # Priority 1: comp_key exactly matches a materials key
        if comp_key in materials:
            comp["material"] = comp_key
            changed = True
            continue

        # Priority 2: a materials key starts with comp_key (flange → flange_al)
        candidates = [mk for mk in materials if mk.startswith(comp_key)]
        if len(candidates) == 1:
            comp["material"] = candidates[0]
            changed = True
            continue

        # Priority 3: comp_key is a substring of a materials key
        candidates = [mk for mk in materials if comp_key in mk]
        if len(candidates) == 1:
            comp["material"] = candidates[0]
            changed = True

    if changed:
        with open(rc_path, "w", encoding="utf-8") as f:
            json.dump(rc, f, indent=2, ensure_ascii=False)
        log.info(
            "  Enriched render_config.json: %d component→material links",
            sum(
                1
                for c in components.values()
                if not isinstance(c, str) and "material" in c
            ),
        )


# 材质 preset 推断关键词路由（从 BOM material 文本推导 render preset）
_MAT_PRESET = {
    "铝": "brushed_aluminum",
    "Al": "brushed_aluminum",
    "钢": "stainless_304",
    "SUS": "stainless_304",
    "PEEK": "peek_amber",
    "橡胶": "black_rubber",
    "硅橡胶": "black_rubber",
    "塑料": "white_nylon",
    "尼龙": "white_nylon",
    "铜": "copper",
}

_preset_keywords_merged = None
_PART_NO_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b")


def get_material_preset_keywords():
    """返回基础 + SW 扩展的 preset 关键词路由。首次调用时合并，缓存结果。

    无 SW 时返回值与 _MAT_PRESET 内容一致。
    """
    global _preset_keywords_merged
    if _preset_keywords_merged is not None:
        return _preset_keywords_merged
    _preset_keywords_merged = dict(_MAT_PRESET)
    if sys.platform == "win32":
        try:
            from adapters.solidworks.sw_material_bridge import load_sw_material_bundle

            bundle = load_sw_material_bundle()
            if bundle:
                for k, v in bundle.preset_keywords.items():
                    if k not in _preset_keywords_merged:
                        _preset_keywords_merged[k] = v
        except ImportError:
            pass
    return _preset_keywords_merged


def _reset_preset_keywords_cache():
    """测试用：重置缓存。"""
    global _preset_keywords_merged
    _preset_keywords_merged = None


def _infer_render_part_prefix(parts: list[dict]) -> str:
    """Infer a stable BOM prefix from part numbers when the title lacks one."""
    token_lists = []
    for part in parts:
        pno = str(part.get("part_no") or "")
        if pno == "UNKNOWN" or "-" not in pno:
            continue
        token_lists.append(pno.split("-"))
    if not token_lists:
        return ""

    common = []
    for idx in range(min(len(tokens) for tokens in token_lists)):
        token = token_lists[0][idx]
        if any(tokens[idx] != token for tokens in token_lists[1:]):
            break
        if re.fullmatch(r"\d+|[A-Z]?\d+[A-Z]?", token):
            break
        common.append(token)
    return "-".join(common)


def _render_identity_from_spec(sub_dir: str, spec_path: str, parts: list[dict]) -> dict:
    """Derive render_config subsystem identity from CAD_SPEC.md, not references."""
    sub_name = os.path.basename(os.path.normpath(sub_dir))
    name_cn = sub_name
    part_prefix = ""

    try:
        text = open(spec_path, encoding="utf-8", errors="replace").read(1000)
    except OSError:
        text = ""

    m = re.search(
        r"^#\s*CAD Spec\s*[—-]\s*(.+?)(?:\s*\(([A-Za-z0-9_-]+)\))?\s*$",
        text,
        flags=re.MULTILINE,
    )
    if m:
        name_cn = m.group(1).strip() or name_cn
        part_prefix = (m.group(2) or "").strip()

    if not part_prefix:
        part_prefix = _infer_render_part_prefix(parts) or sub_name.upper()

    prefix_short = part_prefix.split("-")[-1] if "-" in part_prefix else part_prefix
    return {
        "name": sub_name,
        "name_cn": name_cn,
        "part_prefix": part_prefix,
        "glb_file": f"{prefix_short}-000_assembly.glb",
    }


def _default_render_config(identity: dict) -> dict:
    """Create a generic render_config.json for spec→codegen projects."""
    return {
        "version": 1,
        "subsystem": {
            **identity,
            "bounding_radius_mm": 300,
        },
        "frame_fill": 0.75,
        "coordinate_system": "Z-axis vertical. Generated from CAD_SPEC.md.",
        "materials": {
            "body": {
                "preset": "brushed_aluminum",
                "label": "Main body",
                "name_cn": "主体",
                "name_en": "Main Body",
            },
            "fastener": {
                "preset": "stainless_304",
                "label": "Fasteners",
                "name_cn": "紧固件",
                "name_en": "Fasteners",
            },
        },
        "camera": {
            "V1": {
                "name": "V1_front_iso",
                "type": "standard",
                "azimuth_deg": 35,
                "elevation_deg": 25,
                "distance_factor": 2.5,
                "description": "Front-left isometric",
            },
            "V2": {
                "name": "V2_rear_oblique",
                "type": "standard",
                "azimuth_deg": 215,
                "elevation_deg": 20,
                "distance_factor": 2.8,
                "description": "Rear-right oblique",
            },
            "V3": {
                "name": "V3_side_elevation",
                "type": "standard",
                "azimuth_deg": 90,
                "elevation_deg": 0,
                "distance_factor": 2.5,
                "description": "Side elevation",
            },
            "V4": {
                "name": "V4_exploded",
                "type": "exploded",
                "azimuth_deg": 35,
                "elevation_deg": 35,
                "distance_factor": 3.5,
                "description": "Exploded view",
            },
            "V5": {
                "name": "V5_ortho_front",
                "type": "ortho",
                "azimuth_deg": 0,
                "elevation_deg": 0,
                "description": "Front orthographic",
            },
        },
        "components": {
            "body": {"name_cn": "主体", "name_en": "Main Body", "material": "body"}
        },
        "labels": {},
    }


def _sync_render_identity(rc: dict, identity: dict) -> bool:
    subsystem_block = rc.setdefault("subsystem", {})
    changed = False
    for key, value in identity.items():
        if value and subsystem_block.get(key) != value:
            subsystem_block[key] = value
            changed = True
    subsystem_block.setdefault("bounding_radius_mm", 300)
    return changed


def _render_component_key(kind: str, part_no: str) -> str:
    """Return a stable render_config component key for a BOM item."""
    suffix = str(part_no or "").rsplit("-", 1)[-1].lower()
    suffix = re.sub(r"[^a-z0-9]+", "_", suffix).strip("_")
    if not suffix:
        suffix = re.sub(r"[^a-z0-9]+", "_", str(part_no).lower()).strip("_")
    return f"{kind}_{suffix or 'unknown'}"


def _clean_render_material_text(value: object) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[*`]+", "", text)
    text = text.replace("<br>", " ").replace("<br/>", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return "" if text in {"", "-", "—", "–", "n/a", "N/A"} else text


def _infer_render_material_preset(material_text: str, default: str = "brushed_aluminum") -> str:
    """Infer a render material preset from a material/model text cell."""
    text = _clean_render_material_text(material_text)
    if not text:
        return default
    text_lower = text.lower()

    # Surface/color cues are more specific than base material words.
    if "黑" in text and ("阳极" in text or "铝" in text):
        return "black_anodized"
    if "蓝" in text and "阳极" in text:
        return "anodized_blue"
    if "绿" in text and "阳极" in text:
        return "anodized_green"
    if "红" in text and "阳极" in text:
        return "anodized_red"
    if "紫" in text and "阳极" in text:
        return "anodized_purple"
    if "45#" in text or "45号" in text or "碳钢" in text:
        return "dark_steel"
    if "gcr15" in text_lower or "轴承钢" in text or "镀铬" in text:
        return "stainless_304"
    if "pu" in text_lower or "聚氨酯" in text or "缓冲垫" in text:
        return "black_rubber"
    if "黑" in text and any(k in text_lower for k in ("橡胶", "塑料", "尼龙", "pla")):
        return "black_rubber"

    for keyword, preset in get_material_preset_keywords().items():
        keyword_text = str(keyword)
        if keyword_text in text or keyword_text.lower() in text_lower:
            return preset
    return default


def _split_markdown_table_row(line: str) -> list[str]:
    return [
        _clean_render_material_text(cell)
        for cell in line.strip().strip("|").split("|")
    ]


def _iter_markdown_table_dicts(section_text: str):
    lines = section_text.splitlines()
    idx = 0
    while idx < len(lines):
        if not lines[idx].lstrip().startswith("|"):
            idx += 1
            continue

        table_lines = []
        while idx < len(lines) and lines[idx].lstrip().startswith("|"):
            table_lines.append(lines[idx])
            idx += 1

        if len(table_lines) < 2:
            continue
        headers = _split_markdown_table_row(table_lines[0])
        for row_line in table_lines[2:]:
            cells = _split_markdown_table_row(row_line)
            if not any(cells):
                continue
            if len(cells) < len(headers):
                cells.extend([""] * (len(headers) - len(cells)))
            yield dict(zip(headers, cells))


def _extract_markdown_section(text: str, heading_pattern: str) -> str:
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if not match or not re.search(heading_pattern, match.group(2)):
            continue
        level = len(match.group(1))
        body = []
        for next_line in lines[idx + 1:]:
            next_match = re.match(r"^(#{1,6})\s+", next_line)
            if next_match and len(next_match.group(1)) <= level:
                break
            body.append(next_line)
        return "\n".join(body)
    return ""


def _extract_part_no_from_text(*values: object) -> str:
    for value in values:
        for match in _PART_NO_RE.findall(str(value or "")):
            if match != "UNKNOWN":
                return match
    return ""


def _collect_render_material_sources(spec_text: str) -> dict[str, dict[str, str]]:
    """Collect part material hints from CAD_SPEC §7 and §2.3 tables."""
    sources: dict[str, dict[str, str]] = {}

    visual_section = _extract_markdown_section(spec_text, r"7\.\s*视觉标识|视觉标识")
    for row in _iter_markdown_table_dicts(visual_section):
        part_no = _extract_part_no_from_text(
            row.get("唯一标签"),
            row.get("零件"),
            *row.values(),
        )
        if not part_no:
            continue
        mat_text = " ".join(
            value for value in (
                row.get("材质", ""),
                row.get("表面颜色", ""),
                row.get("颜色", ""),
            )
            if value
        ).strip()
        if mat_text:
            sources.setdefault(part_no, {})["section7"] = mat_text

    surface_section = _extract_markdown_section(spec_text, r"2\.3\s*表面处理|表面处理")
    for row in _iter_markdown_table_dicts(surface_section):
        part_no = _extract_part_no_from_text(row.get("零件"), *row.values())
        if not part_no:
            continue
        mat_text = " ".join(
            value for value in (
                row.get("material_type", ""),
                row.get("材质", ""),
                row.get("处理方式", ""),
            )
            if value
        ).strip()
        if mat_text:
            sources.setdefault(part_no, {})["section23"] = mat_text

    return sources


def _select_render_material_text(
    part: dict,
    material_sources: dict[str, dict[str, str]],
) -> tuple[str, str]:
    """Return (source, text) using BOM > §7 > §2.3 > name fallback."""
    bom_text = _clean_render_material_text(part.get("material", ""))
    if bom_text:
        return "bom", bom_text
    part_no = part.get("part_no", "")
    sources = material_sources.get(part_no, {})
    if sources.get("section7"):
        return "section7", sources["section7"]
    if sources.get("section23"):
        return "section23", sources["section23"]
    fallback = " ".join(
        value for value in (
            part.get("name_cn", ""),
            part.get("make_buy", ""),
        )
        if value
    ).strip()
    return "fallback", fallback


def _ensure_render_component(
    components: dict,
    materials: dict,
    *,
    comp_key: str,
    part_no: str,
    name_cn: str,
    preset: str,
    material_source: str = "",
    material_text: str = "",
) -> bool:
    """Upsert a render_config component and its material without overwriting user choices."""
    changed = False
    existing_key = None
    for key, value in components.items():
        if isinstance(value, dict) and value.get("bom_id") == part_no:
            existing_key = key
            break

    if existing_key is None:
        base_key = comp_key
        candidate = base_key
        idx = 2
        while (
            candidate in components
            and isinstance(components.get(candidate), dict)
            and components[candidate].get("bom_id") != part_no
        ):
            candidate = f"{base_key}_{idx}"
            idx += 1
        existing_key = candidate
        components[existing_key] = {}
        changed = True

    comp = components[existing_key]
    for key, value in {
        "name_cn": name_cn,
        "name_en": comp.get("name_en", ""),
        "bom_id": part_no,
    }.items():
        if comp.get(key) != value:
            comp[key] = value
            changed = True

    mat_key = comp.get("material") or existing_key
    if comp.get("material") != mat_key:
        comp["material"] = mat_key
        changed = True

    if mat_key not in materials:
        materials[mat_key] = {
            "preset": preset,
            "label": name_cn,
            "name_cn": name_cn,
            "name_en": "",
            "material_source": material_source,
            "material_text": material_text,
        }
        changed = True
    else:
        mat = materials[mat_key]
        auto_generated_default = (
            mat.get("material_source")
            or (
                mat.get("preset") == "brushed_aluminum"
                and not any(k in mat for k in ("overrides", "color", "metallic", "roughness"))
                and mat.get("label", name_cn) == name_cn
            )
        )
        if auto_generated_default:
            for key, value in {
                "preset": preset,
                "label": mat.get("label") or name_cn,
                "name_cn": mat.get("name_cn") or name_cn,
                "name_en": mat.get("name_en", ""),
                "material_source": material_source,
                "material_text": material_text,
            }.items():
                if value and mat.get(key) != value:
                    mat[key] = value
                    changed = True
    return changed


def _render_config_identity_stale(rc: dict, identity: dict) -> bool:
    subsystem_block = rc.get("subsystem", {})
    for key in ("name", "part_prefix", "glb_file"):
        current = subsystem_block.get(key)
        if current and identity.get(key) and current != identity[key]:
            return True
    prefix = str(identity.get("part_prefix") or "")
    if prefix:
        components = rc.get("components", {})
        for comp in components.values():
            if not isinstance(comp, dict):
                continue
            bom_id = str(comp.get("bom_id") or "")
            if bom_id and bom_id != "UNKNOWN" and not bom_id.startswith(prefix):
                return True
    return False


def _gen_render_config_from_bom(sub_dir, spec_path):
    """Auto-generate render_config.json materials+components from BOM.

    Uses CAD_SPEC identity as the source of truth for subsystem/glb fields,
    then fills missing BOM-derived material/component entries.
    """
    rc_path = os.path.join(sub_dir, "render_config.json")
    if not os.path.isfile(spec_path):
        return

    from codegen.gen_build import parse_bom_tree

    parts = parse_bom_tree(spec_path)
    try:
        spec_text = open(spec_path, encoding="utf-8", errors="replace").read()
    except OSError:
        spec_text = ""
    material_sources = _collect_render_material_sources(spec_text)
    identity = _render_identity_from_spec(sub_dir, spec_path, parts)
    if os.path.isfile(rc_path):
        with open(rc_path, encoding="utf-8") as f:
            rc = json.load(f)
        if _render_config_identity_stale(rc, identity):
            rc = _default_render_config(identity)
            changed = True
        else:
            changed = _sync_render_identity(rc, identity)
    else:
        rc = _default_render_config(identity)
        changed = True

    assemblies = [
        p for p in parts
        if p["is_assembly"] and p.get("part_no") != "UNKNOWN"
    ]

    components = rc.setdefault("components", {})
    materials = rc.setdefault("materials", {})

    for assy in assemblies:
        pno = assy["part_no"]
        name_cn = assy["name_cn"]

        # Derive comp_key: use part_no suffix for guaranteed uniqueness
        comp_key = _render_component_key("assy", pno)

        # Check if any existing component already has this bom_id
        existing = None
        for ck, cv in components.items():
            if isinstance(cv, dict) and cv.get("bom_id") == pno:
                existing = ck
                break

        if existing:
            # Already exists — ensure material link AND materials entry
            comp = components[existing]
            mat_key = comp.get("material", existing)
            if mat_key not in materials:
                # Try fuzzy: existing key as prefix of some material
                candidates = [mk for mk in materials if mk.startswith(existing)]
                if len(candidates) == 1:
                    mat_key = candidates[0]
                else:
                    # Create materials entry from BOM child material field
                    children = [
                        p
                        for p in parts
                        if p["part_no"].startswith(pno + "-") and not p["is_assembly"]
                    ]
                    preset = "brushed_aluminum"
                    for child in children:
                        _, child_text = _select_render_material_text(child, material_sources)
                        candidate = _infer_render_material_preset(child_text)
                        if candidate != "brushed_aluminum":
                            preset = candidate
                            break
                    materials[mat_key] = {"preset": preset, "label": name_cn}
                    changed = True
            comp["material"] = mat_key
            changed = True
            continue

        # New component — create both entries with same key
        components[comp_key] = {
            "name_cn": name_cn,
            "name_en": "",
            "bom_id": pno,
            "material": comp_key,
        }

        # Infer preset from first child's material field
        children = [
            p
            for p in parts
            if p["part_no"].startswith(pno + "-") and not p["is_assembly"]
        ]
        preset = "brushed_aluminum"
        for child in children:
            _, child_text = _select_render_material_text(child, material_sources)
            candidate = _infer_render_material_preset(child_text)
            if candidate != "brushed_aluminum":
                preset = candidate
                break

        if comp_key not in materials:
            materials[comp_key] = {
                "preset": preset,
                "label": name_cn,
            }
        changed = True

    ordinary_parts = [
        p for p in parts
        if not p["is_assembly"] and p.get("part_no") != "UNKNOWN"
    ]
    for part in ordinary_parts:
        pno = part["part_no"]
        material_source, material_text = _select_render_material_text(part, material_sources)
        preset = _infer_render_material_preset(material_text)
        changed = _ensure_render_component(
            components,
            materials,
            comp_key=_render_component_key("part", pno),
            part_no=pno,
            name_cn=part.get("name_cn", ""),
            preset=preset,
            material_source=material_source,
            material_text=material_text,
        ) or changed

    # Fill components referenced by labels but missing from components section
    # (e.g. "adapter" is a part-level item used in labels but not an assembly)
    labels = rc.get("labels", {})
    all_parts = {p["part_no"]: p for p in parts if not p["is_assembly"]}
    for view_key, label_list in labels.items():
        if isinstance(label_list, str) or view_key.startswith("_"):
            continue
        for label in label_list:
            comp_ref = label.get("component", "")
            if comp_ref and comp_ref not in components:
                # Try to find a BOM part matching this component name
                # by checking if comp_ref matches a materials key (which
                # was designed to match this component)
                mat_key = comp_ref if comp_ref in materials else None
                # Find BOM part by name keyword
                matched_part = None
                for pno, part in all_parts.items():
                    name_lower = part["name_cn"].lower()
                    if (
                        comp_ref in name_lower
                        or comp_ref.replace("_", "") in name_lower
                    ):
                        matched_part = part
                        break
                if not matched_part:
                    # Try English-like matching (adapter → 适配)
                    _LABEL_CN_MAP = {
                        "adapter": "适配",
                        "motor": "电机",
                        "reducer": "减速",
                        "drive": "驱动",
                    }
                    cn_keyword = _LABEL_CN_MAP.get(comp_ref, "")
                    if cn_keyword:
                        for pno, part in all_parts.items():
                            if cn_keyword in part["name_cn"]:
                                matched_part = part
                                break
                if matched_part:
                    components[comp_ref] = {
                        "name_cn": matched_part["name_cn"],
                        "name_en": "",
                        "bom_id": matched_part["part_no"],
                        "material": mat_key or comp_ref,
                    }
                    # Ensure materials entry exists
                    if comp_ref not in materials and mat_key is None:
                        material_source, mat_text = _select_render_material_text(
                            matched_part,
                            material_sources,
                        )
                        preset = _infer_render_material_preset(mat_text)
                        materials[comp_ref] = {
                            "preset": preset,
                            "label": matched_part["name_cn"],
                            "material_source": material_source,
                            "material_text": mat_text,
                        }
                    changed = True

    if changed:
        with open(rc_path, "w", encoding="utf-8") as f:
            json.dump(rc, f, indent=2, ensure_ascii=False)
        synced = sum(
            1 for comp in components.values()
            if isinstance(comp, dict) and comp.get("bom_id")
        )
        log.info("  BOM→render_config: %d components synced", synced)


def _validate_render_config(rc_path):
    """Validate render_config.json internal consistency.

    Returns list of warning strings (empty = valid).
    """
    import re as _re

    if not os.path.isfile(rc_path):
        return []
    with open(rc_path, encoding="utf-8") as f:
        rc = json.load(f)

    warnings = []
    materials = rc.get("materials", {})
    components = rc.get("components", {})

    for comp_key, comp in components.items():
        if isinstance(comp, str) or comp_key.startswith("_"):
            continue
        # Check material reference exists
        mat_key = comp.get("material", comp_key)
        if mat_key not in materials:
            warnings.append(
                f"component '{comp_key}': material '{mat_key}' not in materials section"
            )
        # Check bom_id format
        bom_id = comp.get("bom_id", "")
        if bom_id and not _re.match(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+$", bom_id):
            warnings.append(
                f"component '{comp_key}': bom_id '{bom_id}' has unexpected format"
            )

    # Check labels reference valid components
    for view_key, label_list in rc.get("labels", {}).items():
        if isinstance(label_list, str) or view_key.startswith("_"):
            continue
        for label in label_list:
            comp_ref = label.get("component", "")
            if comp_ref and comp_ref not in components:
                warnings.append(f"labels.{view_key}: component '{comp_ref}' not found")

    return warnings


def _read_glb_json_chunk(glb_path: str) -> dict:
    """Read the JSON chunk from a binary GLB file."""
    import struct

    with open(glb_path, "rb") as f:
        data = f.read()
    if len(data) < 20:
        raise ValueError("GLB too small")
    magic, _version, _length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF":
        raise ValueError("not a GLB file")

    offset = 12
    while offset + 8 <= len(data):
        chunk_len, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk = data[offset: offset + chunk_len]
        offset += chunk_len
        if chunk_type == 0x4E4F534A:
            return json.loads(chunk.decode("utf-8"))
    raise ValueError("GLB JSON chunk missing")


def _render_bom_match_key(bom_id: str) -> str:
    """Match render_3d.resolve_bom_materials() BOM normalization."""
    return re.sub(r"^[A-Z]+-", "", str(bom_id or "")).lower()


def _simulate_render_material_assignment(rc: dict, mesh_node_names: list[str]) -> list[dict]:
    """Simulate render_3d.assign_materials() without importing Blender."""
    materials = rc.get("materials", {})
    components = rc.get("components", {})
    bom_materials = {}
    for comp_key, comp in components.items():
        if isinstance(comp, str) or str(comp_key).startswith("_"):
            continue
        bom_id = comp.get("bom_id", "")
        mat_key = comp.get("material", comp_key)
        if bom_id and mat_key in materials:
            bom_materials[_render_bom_match_key(bom_id)] = mat_key

    assignments = []
    for node_name in mesh_node_names:
        name_lower = str(node_name or "").lower()
        material = None
        reason = "default_gray"

        for bom_key, mat_key in sorted(bom_materials.items(), key=lambda item: -len(item[0])):
            if bom_key and bom_key in name_lower:
                material = mat_key
                reason = "bom_id"
                break

        if material is None:
            for pattern in materials:
                if pattern and pattern in name_lower:
                    material = pattern
                    reason = "material_pattern"
                    break

        assignments.append({
            "node": node_name,
            "material": material or "PBR_default",
            "reason": reason,
        })
    return assignments


def _validate_render_glb_material_coverage(rc_path: str, glb_path: str) -> list[str]:
    """Validate that GLB mesh nodes can resolve to render_config materials."""
    if not os.path.isfile(rc_path) or not os.path.isfile(glb_path):
        return []

    try:
        with open(rc_path, encoding="utf-8") as f:
            rc = json.load(f)
        glb = _read_glb_json_chunk(glb_path)
    except Exception as exc:
        return [f"GLB material coverage skipped: {type(exc).__name__}: {exc}"]

    mesh_nodes = [
        node.get("name", "")
        for node in glb.get("nodes", [])
        if "mesh" in node
    ]
    if not mesh_nodes:
        return ["GLB material coverage skipped: no mesh nodes found"]

    assignments = _simulate_render_material_assignment(rc, mesh_nodes)
    unmatched = [a["node"] for a in assignments if a["reason"] == "default_gray"]
    if not unmatched:
        return []

    preview = ", ".join(str(name) for name in unmatched[:12])
    suffix = "" if len(unmatched) <= 12 else f", ... (+{len(unmatched) - 12} more)"
    return [
        "GLB material coverage: "
        f"{len(unmatched)}/{len(mesh_nodes)} mesh node(s) would use default gray: "
        f"{preview}{suffix}"
    ]


def _interactive_fill_warnings(review_json_path):
    """逐项引导用户处理所有 WARNING/CRITICAL 项（含自动补全和手动填写）。

    Returns: dict of {item_id: user_input}
    """
    if not os.path.isfile(review_json_path):
        return {}
    with open(review_json_path, encoding="utf-8") as f:
        data = json.load(f)

    all_items = [
        item
        for item in data.get("items", [])
        if item.get("verdict") in ("WARNING", "CRITICAL")
    ]
    info_items = [
        item
        for item in data.get("items", [])
        if item.get("verdict") == "INFO" and item.get("auto_fill") == "是"
    ]
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

        print(f"\n{'─' * 60}")
        print(f"[{verdict}] {item_id}: {check or detail}")
        if detail and check:
            print(f"  详情: {detail}")
        if suggestion and suggestion != "—":
            print(f"  建议格式: {suggestion}")
        print(f"{'─' * 60}")

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
                parts = [
                    p.strip()
                    for p in detail.replace("缺失:", "").split(",")
                    if p.strip()
                ]
                if parts:
                    cands = _infer_material_candidates(parts[0])
                    inferred = f"{parts[0]} 材质候选: {' / '.join(cands)}"
                    infer_label = f"为 {parts[0]} 推断材质候选"

            if inferred:
                print(f"\n  推断值（{infer_label}）：")
                print(f"  {'─' * 56}")
                for ln in inferred.splitlines():
                    print(f"  {ln}")
                print(f"  {'─' * 56}")
                # Tell user where to manually edit if they want to change later
                spec_path = review_json_path.replace(
                    "DESIGN_REVIEW.json", "CAD_SPEC.md"
                )
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
    model_choices = _extract_model_choices(supplements)
    if model_choices:
        _save_model_choices(model_choices, review_json_path)
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


_MODEL_CHOICE_KEYS = {
    "model_choices",
    "geometry_choices",
    "parts_library_choices",
}


def _extract_model_choices(supplements) -> list[dict]:
    """Extract structured model choices from Agent/user supplements."""
    if not isinstance(supplements, dict):
        return []

    choices: list[dict] = []
    for key in _MODEL_CHOICE_KEYS:
        value = supplements.get(key)
        if isinstance(value, list):
            choices.extend(v for v in value if isinstance(v, dict))
        elif isinstance(value, dict):
            if any(_looks_like_step_choice(v) for v in value.values() if isinstance(v, dict)):
                for item_id, choice in value.items():
                    if isinstance(choice, dict):
                        enriched = dict(choice)
                        enriched.setdefault("id", item_id)
                        choices.append(enriched)
            else:
                choices.append(value)

    for item_id, value in supplements.items():
        if item_id in _MODEL_CHOICE_KEYS or not isinstance(value, dict):
            continue
        if _looks_like_step_choice(value):
            enriched = dict(value)
            enriched.setdefault("id", item_id)
            choices.append(enriched)
            continue
        user_choice = value.get("user_choice")
        if isinstance(user_choice, dict) and _looks_like_step_choice(user_choice):
            enriched = dict(user_choice)
            enriched.setdefault("id", item_id)
            enriched.setdefault("part_no", value.get("part_no"))
            enriched.setdefault("name_cn", value.get("name_cn"))
            choices.append(enriched)

    return choices


def _looks_like_step_choice(value: dict) -> bool:
    return any(
        value.get(k)
        for k in ("step_file", "source_path", "selected_path", "path")
    )


def _is_model_choice_supplement(item_id: str, value) -> bool:
    if item_id in _MODEL_CHOICE_KEYS:
        return True
    if not isinstance(value, dict):
        return False
    if _looks_like_step_choice(value):
        return True
    user_choice = value.get("user_choice")
    return isinstance(user_choice, dict) and _looks_like_step_choice(user_choice)


def _save_model_choices(model_choices: list[dict], review_json_path: str) -> str:
    """Persist model choices and apply valid STEP selections to parts_library.yaml."""
    out_path = _model_choices_path(review_json_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    applied = []
    for choice in model_choices:
        applied.append(_apply_model_choice_to_parts_library(choice, review_json_path))

    envelope = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "choices": model_choices,
        "applied": applied,
    }
    tmp_path = out_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(envelope, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, out_path)
    log.info("模型选择已保存: %s", out_path)
    return out_path


def _model_choices_path(review_json_path: str) -> str:
    """Return the authoritative model_choices.json path for a review artifact."""
    ctx = ModelProjectContext.from_review_json(
        review_json_path,
        project_root=PROJECT_ROOT,
    )
    return str(ctx.model_choices_path)


def _apply_model_choice_to_parts_library(
    choice: dict,
    review_json_path: str = "",
) -> dict:
    """Copy a selected STEP file into std_parts and prepend a resolver mapping."""
    from tools.model_import import import_user_step_model

    part_no = (choice.get("part_no") or "").strip()
    source = (
        choice.get("step_file")
        or choice.get("source_path")
        or choice.get("selected_path")
        or choice.get("path")
    )
    if not part_no:
        return {"applied": False, "reason": "missing part_no", "choice": choice}
    if not source:
        return {"applied": False, "reason": "missing step file path", "part_no": part_no}

    return import_user_step_model(
        part_no=part_no,
        name_cn=choice.get("name_cn", ""),
        step=str(source),
        subsystem=_subsystem_from_review_path(review_json_path),
        project_root=PROJECT_ROOT,
        source_search_dirs=[os.path.dirname(os.path.abspath(review_json_path))]
        if review_json_path
        else None,
    )


def _subsystem_from_review_path(review_json_path: str) -> str | None:
    ctx = ModelProjectContext.from_review_json(
        review_json_path,
        project_root=PROJECT_ROOT,
    )
    return ctx.subsystem


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
        log.error(
            "Design doc not found. Use --design-doc or ensure docs/design/%s exists",
            design_doc or "??-*.md",
        )
        return 1
    _ensure_spec_subsystem(args, design_doc)

    spec_gen = os.path.join(SKILL_ROOT, "cad_spec_gen.py")
    if not os.path.isfile(spec_gen):
        log.error("cad_spec_gen.py not found at %s", spec_gen)
        return 1

    force_flag = getattr(args, "force", False) or getattr(args, "force_spec", False)

    # ── Step 1: Run review-only first ──
    _spec_output_dir = os.path.join(PROJECT_ROOT, "output")
    cmd_review = [
        sys.executable,
        spec_gen,
        design_doc,
        "--config",
        CONFIG_PATH,
        "--output-dir",
        _spec_output_dir,
        "--review-only",
    ]
    if force_flag:
        cmd_review.append("--force")

    log.info("Phase 1a: 生成设计审查报告...")
    ok, _ = _run_subprocess(
        cmd_review,
        f"review ({os.path.basename(design_doc)})",
        dry_run=args.dry_run,
        timeout=120,
    )
    if not ok:
        return 1

    if args.dry_run:
        return 0

    # ── Step 2: Read review results ──
    review_json = _resolve_review_json(args)
    critical, warning, auto_fill_count, auto_fill_items = _show_review_summary(
        review_json
    )

    # ── Step 2b: Determine mode ──
    review_only = getattr(args, "review_only", False)
    parsed_supplements = None
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
            parsed_supplements = json.loads(args.supplements)
        except json.JSONDecodeError as e:
            log.error("--supplements JSON 解析失败: %s", e)
            return 1
        _save_supplements(parsed_supplements, review_json)
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
            log.info(
                "存在 %d 个 WARNING。Agent 请读取 DESIGN_REVIEW.json 逐项处理后"
                " 调用 spec --supplements '{}' 或 spec --auto-fill。",
                warning,
            )
        log.info("审查报告: %s", review_json)
        return 0

    # Parse --supplements even when combined with --auto-fill or --proceed
    sup_data = parsed_supplements
    if getattr(args, "supplements", None) and sup_data is None:
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
        supplements = {
            k: v for k, v in sup_data.items()
            if v not in ("__AUTO__", "__AUTO_FILL__")
            and not _is_model_choice_supplement(k, v)
        }
        guided_auto_fill = any(
            v in ("__AUTO__", "__AUTO_FILL__") for v in sup_data.values()
        )

    # "auto_fill", "proceed", or post-guided_fill → generate CAD_SPEC.md
    cmd_gen = [
        sys.executable,
        spec_gen,
        design_doc,
        "--config",
        CONFIG_PATH,
        "--output-dir",
        _spec_output_dir,
        "--review",
    ]
    if choice == "auto_fill" or guided_auto_fill:
        cmd_gen.append("--auto-fill")
    if force_flag:
        cmd_gen.append("--force")

    log.info("Phase 1b: 生成 CAD_SPEC.md...")
    ok, _ = _run_subprocess(
        cmd_gen,
        f"spec-gen ({os.path.basename(design_doc)})",
        dry_run=args.dry_run,
        timeout=120,
    )
    if not ok:
        return 1

    # Deploy spec artifacts from output/ to cad/ so codegen can read them
    _output_sub = os.path.join(PROJECT_ROOT, "output", args.subsystem)
    _out_dir_override = getattr(args, "out_dir", None)
    if _out_dir_override and args.subsystem:
        # --out-dir supplied: redirect all writes away from cad/<subsystem>/
        _cad_sub = os.path.join(_out_dir_override, args.subsystem)
        os.makedirs(_cad_sub, exist_ok=True)
        log.info("  --out-dir: redirecting subsystem output to %s", _cad_sub)
    else:
        _cad_sub = get_subsystem_dir(args.subsystem) if args.subsystem else None
        if not _cad_sub and args.subsystem:
            # Directory doesn't exist yet — create it so deploy can proceed
            _cad_sub = os.path.join(PROJECT_ROOT, "cad", args.subsystem)
            os.makedirs(_cad_sub, exist_ok=True)
            log.info("  Created: %s", _cad_sub)
    if _cad_sub and os.path.isdir(_output_sub):
        for _fname in ("CAD_SPEC.md", "DESIGN_REVIEW.md", "DESIGN_REVIEW.json"):
            _src = os.path.join(_output_sub, _fname)
            if os.path.isfile(_src):
                shutil.copy2(_src, os.path.join(_cad_sub, _fname))
                log.info("  Deployed: %s → %s", _fname, os.path.basename(_cad_sub))

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
                updated = re.sub(
                    r"\n+## §10 用户补充数据.*$", new_section, existing, flags=re.DOTALL
                )
                with open(spec_path, "w", encoding="utf-8", errors="replace") as _sf:
                    _sf.write(updated)
            log.info("用户补充数据已追加到 CAD_SPEC.md (%d 项)", len(supplements))
            # Re-deploy after supplements were appended
            if _cad_sub and os.path.isfile(spec_path):
                shutil.copy2(spec_path, os.path.join(_cad_sub, "CAD_SPEC.md"))
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
        log.error(
            "Subsystem '%s' not found in %s",
            args.subsystem or "(none — use --subsystem)",
            CAD_DIR,
        )
        return 1

    spec_path = os.path.join(sub_dir, "CAD_SPEC.md")
    if not os.path.isfile(spec_path):
        log.error("CAD_SPEC.md not found in %s. Run 'spec' first.", sub_dir)
        return 1

    mode = "force" if getattr(args, "force", False) else "scaffold"
    failures = 0

    # 2-pre: Deploy shared tool modules to subsystem directory
    _deploy_tool_modules(sub_dir)

    # 2-contract: PRODUCT_GRAPH is the instance identity source for assembly
    # layout contracts. Generate it explicitly so codegen stays one-command
    # usable while downstream tools never infer identities from names.
    cmd = [
        sys.executable,
        os.path.join(SKILL_ROOT, "cad_pipeline.py"),
        "product-graph",
        "--subsystem",
        args.subsystem,
    ]
    ok, _ = _run_subprocess(cmd, "codegen PRODUCT_GRAPH.json", dry_run=args.dry_run)
    if not ok:
        failures += 1

    # 2a: params.py
    cmd = [
        sys.executable,
        os.path.join(SKILL_ROOT, "codegen", "gen_params.py"),
        spec_path,
        "--mode",
        mode,
    ]
    ok, _ = _run_subprocess(cmd, "codegen params.py", dry_run=args.dry_run)
    if not ok:
        failures += 1

    # 2b: build_all.py
    cmd = [
        sys.executable,
        os.path.join(SKILL_ROOT, "codegen", "gen_build.py"),
        spec_path,
        "--mode",
        mode,
    ]
    ok, _ = _run_subprocess(cmd, "codegen build_all.py", dry_run=args.dry_run)
    if not ok:
        failures += 1

    # 2c: part module scaffolds.
    # gen_parts.py uses exit 2 as a soft signal that scaffolds were emitted
    # but still have unfilled TODO markers (coordinate-system blocks the
    # designer needs to review). That is NOT a failure for the pipeline —
    # the files are valid Python and Phase 2.5 build can proceed.
    cmd = [
        sys.executable,
        os.path.join(SKILL_ROOT, "codegen", "gen_parts.py"),
        spec_path,
        "--output-dir",
        sub_dir,
        "--mode",
        mode,
    ]
    ok, _ = _run_subprocess(
        cmd,
        "codegen part scaffolds",
        dry_run=args.dry_run,
        warn_exit_codes={2},
    )
    if not ok:
        failures += 1

    # 2c2: standard part simplified geometry (purchased parts)
    cmd = [
        sys.executable,
        os.path.join(SKILL_ROOT, "codegen", "gen_std_parts.py"),
        spec_path,
        "--output-dir",
        sub_dir,
        "--mode",
        mode,
    ]
    ok, _ = _run_subprocess(cmd, "codegen std parts", dry_run=args.dry_run)
    if not ok:
        failures += 1

    # 2d: assembly.py
    cmd = [
        sys.executable,
        os.path.join(SKILL_ROOT, "codegen", "gen_assembly.py"),
        spec_path,
        "--mode",
        mode,
    ]
    if getattr(args, "force_layout", False):
        cmd.append("--force-layout")
    ok, _ = _run_subprocess(cmd, "codegen assembly.py", dry_run=args.dry_run)
    if not ok:
        failures += 1

    # Auto-generate materials+components from BOM (fills gaps only)
    if os.path.isfile(spec_path):
        _gen_render_config_from_bom(sub_dir, spec_path)
    # Enrich component→material links
    _enrich_render_config_materials(sub_dir)

    return 1 if failures else 0


def cmd_build(args):
    """Build STEP + DXF for a subsystem."""
    sub_dir = get_subsystem_dir(args.subsystem)
    if not sub_dir:
        log.error(
            "Subsystem '%s' not found in %s",
            args.subsystem or "(none — use --subsystem)",
            CAD_DIR,
        )
        return 1

    build_script = os.path.join(sub_dir, "build_all.py")
    if not os.path.isfile(build_script):
        log.error("No build_all.py found in %s", sub_dir)
        return 1

    # ── Pre-build orientation gate ────────────────────────────────────────────
    orientation_script = os.path.join(sub_dir, "orientation_check.py")
    if os.path.isfile(orientation_script) and not getattr(
        args, "skip_orientation", False
    ):
        log.info("[Phase 3 pre-check] Running orientation_check.py ...")
        ok_orient, _ = _run_subprocess(
            [sys.executable, orientation_script],
            "orientation_check",
            dry_run=args.dry_run,
            timeout=120,
        )
        if not ok_orient:
            log.error(
                "Orientation check FAILED — aborting build. "
                "Fix assembly directions then re-run. "
                "Use --skip-orientation to bypass (not recommended)."
            )
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

    ok, elapsed = _run_subprocess(
        cmd, f"build_all.py ({args.subsystem})", dry_run=args.dry_run, timeout=1200
    )
    if not ok:
        return 1

    # ── Post-build: GLB consolidation ────────────────────────────────────────
    # CadQuery's exportGLTF emits one mesh node per OCCT face — a 100-face
    # part becomes 100 sibling Mesh nodes in the GLB. The consolidator
    # collapses sibling components by `_<digit>` suffix so each part is a
    # single mesh under its canonical name. Without this, downstream
    # tools that read per-component bbox (3D viewers, label projectors)
    # see only the bbox of the first face. Gracefully no-ops when
    # trimesh isn't installed.
    if not args.dry_run:
        try:
            from codegen.consolidate_glb import consolidate_glb_file
            import glob

            glb_files = glob.glob(os.path.join(DEFAULT_OUTPUT, "*_assembly.glb"))
            for glb_file in glb_files:
                consolidate_glb_file(glb_file, logger=lambda m: log.info(m))
        except ImportError:
            pass  # consolidator module missing — non-fatal

    # ── Post-build: DXF → PNG rendering ──────────────────────────────────────
    render_dxf_script = os.path.join(sub_dir, "render_dxf.py")
    if os.path.isfile(render_dxf_script):
        log.info("[Phase 3 post-build] Rendering DXF → PNG ...")
        ok_dxf, _ = _run_subprocess(
            [sys.executable, render_dxf_script],
            "render_dxf.py (DXF → PNG)",
            dry_run=args.dry_run,
            timeout=600,
        )
        if not ok_dxf:
            log.warning(
                "DXF → PNG rendering failed (non-fatal, DXF files are still available)"
            )
    else:
        log.info("No render_dxf.py in %s — skipping DXF → PNG", sub_dir)
    # ─────────────────────────────────────────────────────────────────────────

    # ── Post-build: Assembly validation (GATE-3.5) ──────────────────────────
    validator_script = os.path.join(SKILL_ROOT, "assembly_validator.py")
    spec_in_sub = os.path.join(sub_dir, "CAD_SPEC.md")
    if os.path.isfile(validator_script) and os.path.isfile(spec_in_sub):
        log.info("[Phase 3 GATE-3.5] Running assembly validation ...")
        ok_val, _ = _run_subprocess(
            [
                sys.executable,
                validator_script,
                sub_dir,
                "--spec",
                spec_in_sub,
                "--output-dir",
                DEFAULT_OUTPUT,
            ],
            "assembly_validator.py",
            dry_run=args.dry_run,
            timeout=120,
        )
        if not ok_val:
            log.warning("Assembly validation failed (non-fatal)")
    # ─────────────────────────────────────────────────────────────────────────

    return 0


def cmd_render(args):
    """Run Blender rendering for a subsystem."""
    from tools.render_qa import write_render_manifest

    blender = get_blender_path()
    if not blender:
        log.error("Blender not found. Set BLENDER_PATH env var.")
        return 1

    sub_dir = get_subsystem_dir(args.subsystem)
    if not sub_dir:
        log.error(
            "Subsystem '%s' not found. Use --subsystem.", args.subsystem or "(none)"
        )
        return 1

    # Deploy Blender render scripts if missing (look in SKILL_ROOT, then reference impl)
    _render_scripts = [
        "render_3d.py",
        "render_exploded.py",
        "render_section.py",
        "render_label_utils.py",
        "render_depth_only.py",
        "render_config.json",
    ]
    for _rs in _render_scripts:
        dst = os.path.join(sub_dir, _rs)
        if os.path.isfile(dst):
            continue
        # Try SKILL_ROOT first, then any existing subsystem as reference
        src = os.path.join(SKILL_ROOT, _rs)
        if not os.path.isfile(src):
            for _d in glob.glob(os.path.join(SKILL_ROOT, "cad", "*")):
                _c = os.path.join(_d, _rs)
                if os.path.isfile(_c):
                    src = _c
                    break
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            log.info(
                "  Deployed render script: %s → %s", _rs, os.path.basename(sub_dir)
            )

    render_script = os.path.join(sub_dir, "render_3d.py")
    exploded_script = os.path.join(sub_dir, "render_exploded.py")
    config_path = os.path.join(sub_dir, "render_config.json")

    # Validate render_config consistency
    rc_path = os.path.join(sub_dir, "render_config.json")
    if os.path.isfile(rc_path):
        warnings = _validate_render_config(rc_path)
        for w in warnings:
            log.warning("  render_config: %s", w)
        try:
            with open(rc_path, encoding="utf-8") as f:
                _rc_for_glb = json.load(f)
            _configured_glb = _rc_for_glb.get("subsystem", {}).get("glb_file", "")
        except Exception:
            _configured_glb = ""
        _glb_for_coverage = os.path.join(DEFAULT_OUTPUT, _configured_glb) if _configured_glb else ""
        for w in _validate_render_glb_material_coverage(rc_path, _glb_for_coverage):
            log.warning("  render_config: %s", w)

    if not os.path.isfile(render_script):
        log.error("No render_3d.py in %s", sub_dir)
        return 1

    failures = 0
    _custom_output_dir = getattr(args, "output_dir", None)
    if _custom_output_dir:
        _custom_output_dir = os.path.abspath(_custom_output_dir)
    _renders_dir_pre = _custom_output_dir or os.path.join(DEFAULT_OUTPUT, "renders")
    _pre_existing = _snapshot_render_pngs(_renders_dir_pre)

    # A1-3：Blender subprocess 环境——注入 SW_TEXTURES_DIR 让 render_3d.py
    # 里 A1-1/A1-2 的 _resolve_texture_path 能查到 SW 的 PBR 贴图目录
    _blender_env = _build_blender_env()
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
        ok, _ = _run_subprocess(
            cmd, f"render {args.view}", dry_run=args.dry_run, timeout=1200,
            env=_blender_env,
        )
        if not ok:
            failures += 1
    else:
        # All views — run standard first, then any exploded/section scripts present
        cmd = [blender, "-b", "-P", render_script, "--"] + render_args + ["--all"]
        ok, _ = _run_subprocess(
            cmd, "render standard views", dry_run=args.dry_run, timeout=1200,
            env=_blender_env,
        )
        if not ok:
            failures += 1

        if os.path.isfile(exploded_script):
            cmd = [blender, "-b", "-P", exploded_script, "--"] + render_args
            ok, _ = _run_subprocess(
                cmd, "render exploded view", dry_run=args.dry_run, timeout=600,
                env=_blender_env,
            )
            if not ok:
                failures += 1

        if os.path.isfile(section_script):
            cmd = [blender, "-b", "-P", section_script, "--"] + render_args
            ok, _ = _run_subprocess(
                cmd, "render section view", dry_run=args.dry_run, timeout=600,
                env=_blender_env,
            )
            if not ok:
                failures += 1

    if not args.dry_run:
        _renders_dir = _custom_output_dir or os.path.join(DEFAULT_OUTPUT, "renders")
        _all_now = _snapshot_render_pngs(_renders_dir)
        _new_files = sorted(
            path
            for path, signature in _all_now.items()
            if path not in _pre_existing or _pre_existing[path] != signature
        )
        # Deduplicate: when --timestamp is used, both V1_name_TS.png and
        # V1_name.png (latest copy) are new.  Keep only the timestamped one
        # to avoid enhance processing the same image twice.
        if _should_timestamp(args) and len(_new_files) > 1:
            import re as _re

            _ts_files = [f for f in _new_files if _re.search(r"_\d{8}_\d{4}\.png$", f)]
            if _ts_files:
                _new_files = _ts_files
        if _new_files:
            _product_graph_path = os.path.join(sub_dir, "PRODUCT_GRAPH.json")
            _product_graph = _load_json_if_present(_product_graph_path)
            _run_id = (
                getattr(args, "run_id", None)
                or (_product_graph or {}).get("run_id")
                or datetime.now(timezone.utc).strftime("run_%Y%m%d_%H%M%S")
            )
            _path_context_hash = (
                getattr(args, "path_context_hash", None)
                or (_product_graph or {}).get("path_context_hash")
            )
            _model_contract_path = _first_existing_path([
                os.path.join(sub_dir, ".cad-spec-gen", "MODEL_CONTRACT.json"),
                os.path.join(DEFAULT_OUTPUT, ".cad-spec-gen", "MODEL_CONTRACT.json"),
            ])
            _assembly_signature_path = _first_existing_path([
                os.path.join(DEFAULT_OUTPUT, "runs", str(_run_id), "ASSEMBLY_SIGNATURE.json"),
                os.path.join(DEFAULT_OUTPUT, "ASSEMBLY_SIGNATURE.json"),
            ])
            _glb_path = _configured_glb_path(config_path)
            _manifest_project_root = _project_root_for_manifest(_renders_dir)
            manifest_path = write_render_manifest(
                _manifest_project_root,
                _renders_dir,
                _new_files,
                subsystem=getattr(args, "subsystem", "") or os.path.basename(sub_dir),
                run_id=str(_run_id),
                path_context_hash=_path_context_hash,
                product_graph=_product_graph_path if os.path.isfile(_product_graph_path) else None,
                model_contract=_model_contract_path,
                assembly_signature=_assembly_signature_path,
                render_config_path=config_path if os.path.isfile(config_path) else None,
                glb_path=_glb_path,
                render_script_path=render_script if os.path.isfile(render_script) else None,
                partial=failures > 0,
            )
            _written_manifest = _load_json_if_present(str(manifest_path)) or {}
            if _written_manifest.get("status") == "blocked":
                failures += 1
                for _reason in (_written_manifest.get("blocking_reasons") or [])[:5]:
                    log.error("render QA blocked: %s %s", _reason.get("code", ""), _reason.get("reasons", ""))
            log.info(
                "Manifest written: %s (%d files%s)",
                manifest_path,
                len(_new_files),
                ", partial" if failures > 0 else "",
            )
        elif failures == 0:
            # silent-failure-hunter: blender -b swallows Python exceptions and
            # returns exit 0, so _run_subprocess cannot see render failures.
            # If every sub-command "succeeded" yet renders/ has zero new PNGs,
            # the run is actually broken — escalate to failure so Phase 5 does
            # not blindly enhance a stale/empty dir.
            log.error(
                "render phase produced 0 new PNGs in %s — "
                "likely a Blender Python crash hidden behind exit 0 "
                "(check GLB path / render_config.json schema)",
                _renders_dir,
            )
            return 1

    return 1 if failures else 0


def _build_enhance_cfg_with_hero(cfg: dict, hero_image: str) -> dict:
    """返回注入了 hero_image 键的 cfg 浅拷贝，不修改原 cfg。"""
    result = dict(cfg)
    result["hero_image"] = hero_image
    return result


def _load_json_if_present(path: str) -> dict | None:
    if not path or not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else None


def _snapshot_render_pngs(render_dir: str) -> dict[str, tuple[int, int, int, str]]:
    if not os.path.isdir(render_dir):
        return {}
    from tools.contract_io import file_sha256

    snapshot = {}
    for path in glob.glob(os.path.join(render_dir, "V*.png")):
        try:
            stat = os.stat(path)
            content_hash = file_sha256(path)
        except OSError:
            continue
        snapshot[path] = (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, content_hash)
    return snapshot


def _first_existing_path(paths: list[str]) -> str | None:
    for path in paths:
        if path and os.path.isfile(path):
            return path
    return None


def _project_root_for_manifest(render_dir: str) -> str:
    render_path = os.path.abspath(render_dir)
    candidates = [os.path.abspath(PROJECT_ROOT), os.path.abspath(os.getcwd())]
    for candidate in candidates:
        try:
            if os.path.commonpath([render_path, candidate]) == candidate:
                return candidate
        except ValueError:
            continue
    return render_path


def _configured_glb_path(config_path: str) -> str | None:
    config = _load_json_if_present(config_path)
    glb_file = (config or {}).get("subsystem", {}).get("glb_file")
    if not glb_file:
        return None
    candidates = [
        glb_file if os.path.isabs(glb_file) else os.path.join(DEFAULT_OUTPUT, glb_file),
        glb_file if os.path.isabs(glb_file) else os.path.join(PROJECT_ROOT, glb_file),
    ]
    return _first_existing_path(candidates)


def cmd_enhance(args):
    """Run AI enhancement on rendered PNGs (Gemini, ComfyUI, fal, or fal_comfy backend)."""
    from tools.render_qa import manifest_blocks_enhance, manifest_image_paths, require_render_manifest

    from enhance_prompt import (
        build_enhance_prompt,
        build_labeled_prompt,
        extract_view_key,
        view_sort_key,
    )

    # Determine backend: CLI arg > pipeline_config.json > default gemini
    _pcfg = _load_pipeline_config()
    backend = getattr(args, "backend", None) or _pcfg.get("enhance", {}).get(
        "backend", "gemini"
    )
    log.info("Enhance backend: %s", backend)
    if getattr(args, "labeled", False) and backend != "gemini":
        log.warning("--labeled is only supported with gemini backend; ignoring")
    _explicit_render_dir = getattr(args, "dir", None)
    if _explicit_render_dir:
        try:
            require_render_manifest(_explicit_render_dir, explicit=True)
        except FileNotFoundError as exc:
            log.error("%s", exc)
            return 1

    # ── Backend-specific init & validation ─────────────────────────────
    # _enhance_fn / _enhance_cfg_key: set for table-driven backends
    # (comfyui, fal, fal_comfy). gemini keeps its own subprocess path.
    _enhance_fn = None
    _enhance_cfg_key = None

    if backend == "comfyui":
        # Pre-flight env check — catches CPU-only, missing models, server down
        _check_result = subprocess.run(
            [
                sys.executable,
                os.path.join(SKILL_ROOT, "comfyui_env_check.py"),
                "--quiet",
            ],
            capture_output=True,
        )
        if _check_result.returncode != 0:
            subprocess.run(
                [sys.executable, os.path.join(SKILL_ROOT, "comfyui_env_check.py")],
            )
            log.error(
                "ComfyUI environment check failed. Fix the issues above, then retry."
            )
            return 1
        from comfyui_enhancer import enhance_image as _comfyui_fn

        _enhance_fn, _enhance_cfg_key = _comfyui_fn, "comfyui"
    elif backend == "engineering":
        # 零 AI 工程后端：Blender PBR PNG → PIL 轻量后处理 → JPG。
        # 无外部依赖（仅 Pillow），用于兜底 / 离线 / 零成本场景。
        from engineering_enhancer import enhance_image as _eng_fn

        _enhance_fn, _enhance_cfg_key = _eng_fn, "engineering"
    elif backend in ("fal", "fal_comfy"):
        # Pre-flight env check for fal_comfy (FAL_KEY, fal-client, depth deps, API, models)
        if backend == "fal_comfy":
            _check_result = subprocess.run(
                [
                    sys.executable,
                    os.path.join(SKILL_ROOT, "fal_comfy_env_check.py"),
                    "--quiet",
                ],
                capture_output=True,
            )
            if _check_result.returncode != 0:
                subprocess.run(
                    [
                        sys.executable,
                        os.path.join(SKILL_ROOT, "fal_comfy_env_check.py"),
                    ],
                )
                log.error(
                    "fal_comfy environment check failed. Fix the issues above, then retry."
                )
                return 1
        else:
            # fal (Flux) backend — lightweight checks only
            if not os.environ.get("FAL_KEY"):
                log.error(
                    "FAL_KEY environment variable not set. Get your key from https://fal.ai/dashboard/keys"
                )
                return 1
            try:
                import fal_client  # noqa — validate import early
            except ImportError:
                log.error("fal-client not installed. Run: pip install fal-client")
                return 1
        if backend == "fal":
            from fal_enhancer import enhance_image as _fal_fn

            _enhance_fn, _enhance_cfg_key = _fal_fn, "fal"
        else:
            from fal_comfy_enhancer import enhance_image as _fal_comfy_fn

            _enhance_fn, _enhance_cfg_key = _fal_comfy_fn, "fal_comfy"
    else:
        backend = "gemini"  # normalise
        gemini_script = get_gemini_script()
        if not gemini_script:
            log.error(
                "gemini_gen.py not found. Set GEMINI_GEN_PATH or check installation."
            )
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
        else:
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
        _resolve_camera_coords(rc)

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
        log.error(
            "Subsystem '%s' not found. Run 'cad-init %s' first or check the name.",
            _sub_name,
            _sub_name,
        )
        return 1

    render_dir = args.dir or os.path.join(DEFAULT_OUTPUT, "renders")
    manifest_path = os.path.join(render_dir, "render_manifest.json")
    if not os.path.isfile(manifest_path) and args.dir:
        log.error("render_manifest.json not found in explicit render dir: %s", render_dir)
        return 1
    if os.path.isfile(manifest_path):
        with open(manifest_path, encoding="utf-8") as _mf:
            _manifest = json.load(_mf)
        _manifest_blocks = manifest_blocks_enhance(_manifest)
        if _manifest_blocks:
            log.error(
                "Render manifest is blocked; refusing enhancement (%d reasons).",
                len(_manifest_blocks),
            )
            for _reason in _manifest_blocks[:5]:
                log.error("  %s: %s", _reason.get("code", "blocked"), _reason.get("message", ""))
            return 1
        pngs = sorted(
            [p for p in manifest_image_paths(_manifest, project_root=PROJECT_ROOT, require_qa_passed=True) if os.path.isfile(p)],
            key=lambda p: view_sort_key(p, rc),
        )
        log.info(
            "Using manifest: %d files (subsystem=%s, ts=%s)",
            len(pngs),
            _manifest.get("subsystem", "?"),
            _manifest.get("timestamp", "?"),
        )
    else:
        pngs = sorted(
            [
                p
                for p in glob.glob(os.path.join(render_dir, "V*.png"))
                if "_enhanced" not in os.path.basename(p)
            ],
            key=lambda p: view_sort_key(p, rc),
        )
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
            log.warning(
                "Model key '%s' not found in pipeline_config.json models dict — using as raw model ID",
                model_key,
            )
        model_id = models.get(
            model_key, model_key
        )  # fall back to raw value if not a key
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
        log.info(
            "Enhance consistency: reference=%s, seed=%s, temperature=%s",
            _ref_mode,
            _seed_from_image,
            _temperature,
        )

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
                return line[line.rfind("图片已保存:") + len("图片已保存:") :].strip()
            if "已保存:" in line:
                return line[line.rfind("已保存:") + len("已保存:") :].strip()
        return None

    def _is_render_acceptable(image_path, config=None):
        """Reject near-blank renders before sending to AI enhance.

        Checks file size and grayscale variance. Thresholds can be overridden
        via render_config.json "enhance_quality_gate" section.
        """
        defaults = {"min_size_kb": 80, "min_variance": 5}
        gate = {**defaults, **(config or {}).get("enhance_quality_gate", {})}
        size_kb = os.path.getsize(image_path) / 1024
        if size_kb < gate["min_size_kb"]:
            return False
        try:
            from PIL import Image, ImageStat

            im = Image.open(image_path).convert("L")
            stat = ImageStat.Stat(im)
            if stat.var[0] < gate["min_variance"]:
                return False
        except Exception:
            pass  # If PIL fails, allow through — don't block on import errors
        return True

    skipped = 0
    for png in pngs:
        new_path = None  # reset each iteration (A5 fix)
        view_key = extract_view_key(png, rc)

        # Quality gate: skip blank/near-empty renders
        if not _is_render_acceptable(png, rc):
            _sz = os.path.getsize(png) / 1024
            log.warning(
                "  SKIP %s: render appears blank (%.0fKB). "
                "Check BUILD output before enhancing.",
                os.path.basename(png),
                _sz,
            )
            skipped += 1
            continue

        # ── Set reference flag in rc for prompt building (A1 fix) ──
        _use_ref = (
            _ref_mode == "v1_anchor"
            and hero_image
            and view_key != "V1"
            and backend == "gemini"
        )
        rc["_has_reference"] = _use_ref

        # Build prompt with all placeholders filled
        try:
            prompt = build_enhance_prompt(view_key, rc, is_v1_done=v1_done)
        except FileNotFoundError:
            prompt = (
                "Keep ALL geometry EXACTLY unchanged. Enhance surface materials "
                "to photo-realistic quality with proper lighting and reflections."
            )

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

            residual = _re.findall(r"\{[a-z_]+\}", prompt)
            if residual:
                log.warning("  UNFILLED placeholders: %s", residual)
            if _seed is not None:
                log.info("  [DRY-RUN] seed: %d", _seed)
            if _use_ref:
                log.info(
                    "  [DRY-RUN] reference: (will use V1 enhanced result at runtime)"
                )
            elif _ref_mode == "v1_anchor" and view_key != "V1":
                log.info("  [DRY-RUN] reference: (pending V1 completion)")
            if getattr(args, "labeled", False) and backend == "gemini":
                _lbl_prompt = build_labeled_prompt(view_key, rc, is_v1_done=v1_done)
                if _lbl_prompt != prompt:
                    log.info(
                        "  [DRY-RUN] labeled prompt (%d chars, +%d label chars)",
                        len(_lbl_prompt),
                        len(_lbl_prompt) - len(prompt),
                    )
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

            # ── Table-driven backend (comfyui / fal / fal_comfy) ────────
            if _enhance_fn is not None:
                log.info(
                    "  Running: enhance %s (%s, %s)",
                    os.path.basename(png),
                    view_key,
                    backend,
                )
                t0 = time.time()
                try:
                    _ecfg = _pcfg.get("enhance", {}).get(_enhance_cfg_key, {})
                    # Track C: v1_anchor を FAL/ComfyUI に拡張
                    if (
                        _ref_mode == "v1_anchor"
                        and hero_image
                        and view_key != "V1"
                        and backend in ("fal", "comfyui", "fal_comfy")
                    ):
                        _ecfg = _build_enhance_cfg_with_hero(_ecfg, hero_image)
                    raw_path = _enhance_fn(png, prompt, _ecfg, view_key, rc)
                except Exception as _be:
                    log.error(
                        "  %s enhance failed for %s: %s",
                        backend,
                        os.path.basename(png),
                        _be,
                    )
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
                    log.warning(
                        "  Could not locate %s output for %s",
                        backend,
                        os.path.basename(png),
                    )
                if view_key == "V1" and _ref_mode == "v1_anchor" and new_path:
                    # Track C: FAL/ComfyUI V1 完了後に hero_image を設定
                    if backend in ("fal", "comfyui", "fal_comfy"):
                        hero_image = new_path
                        log.info("  Hero image set (FAL/ComfyUI): %s", os.path.basename(new_path))
                continue  # skip Gemini block

            # ── Gemini backend ───────────────────────────────────────────
            # Compress source image (upgraded: 1280×720, quality 90)
            _img_to_send = png
            try:
                _ctmp, _csz = _compress_for_api(png, (1280, 720), 90)
                if _ctmp:
                    _compressed_tmp = _ctmp
                    _img_to_send = _compressed_tmp
                    log.info(
                        "  Compressed %s: %.0fKB → %.0fKB",
                        os.path.basename(png),
                        os.path.getsize(png) / 1024,
                        _csz,
                    )
            except Exception as _ce:
                log.warning("  Could not compress image: %s", _ce)

            # Build command with optional reference, seed, temperature
            cmd = [
                sys.executable,
                gemini_script,
                "--prompt-file",
                prompt_file,
                "--image",
                _img_to_send,
            ] + model_arg

            ref_args = []
            if _use_ref and hero_image:
                # Compress reference image more aggressively to keep payload small
                try:
                    _rctmp, _rsz = _compress_for_api(hero_image, (1280, 720), 90)
                    _ref_to_send = _rctmp if _rctmp else hero_image
                    if _rctmp:
                        _ref_compressed_tmp = _rctmp
                    ref_args = ["--reference", _ref_to_send]
                    log.info(
                        "  Reference: %s (%.0fKB)", os.path.basename(hero_image), _rsz
                    )
                except Exception as _re_err:
                    log.warning("  Could not prepare reference image: %s", _re_err)

            seed_args = []
            if _seed is not None:
                seed_args = ["--seed", str(_seed)]

            temp_args = []
            if _temperature is not None:
                temp_args = ["--temperature", str(_temperature)]

            cmd = cmd + ref_args + seed_args + temp_args

            log.info(
                "  Running: enhance %s (%s, %d chars%s)",
                os.path.basename(png),
                view_key,
                len(prompt),
                " +ref" if ref_args else "",
            )
            t0 = time.time()
            result = None
            for _attempt in range(3):
                if _attempt > 0:
                    log.info("  Retry %d/2 for %s ...", _attempt, os.path.basename(png))
                    time.sleep(10)
                try:
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=180,
                        encoding="utf-8",
                        errors="replace",
                    )
                    if result.returncode == 0:
                        break
                except subprocess.TimeoutExpired:
                    log.warning(
                        "  TIMEOUT attempt %d for %s",
                        _attempt + 1,
                        os.path.basename(png),
                    )
                    result = None

            # ── Fallback: retry without reference if reference mode failed ──
            if (result is None or result.returncode != 0) and ref_args:
                log.warning(
                    "  Reference mode failed for %s, retrying without reference...",
                    os.path.basename(png),
                )
                cmd_fallback = [
                    a for a in cmd if a not in ref_args and a != "--reference"
                ]
                try:
                    result = subprocess.run(
                        cmd_fallback,
                        capture_output=True,
                        text=True,
                        timeout=180,
                        encoding="utf-8",
                        errors="replace",
                    )
                except subprocess.TimeoutExpired:
                    result = None

            elapsed = time.time() - t0
            if result is None or result.returncode != 0:
                rc_val = result.returncode if result is not None else -1
                log.error(
                    "  FAILED enhance %s (exit %d, %.1fs)",
                    os.path.basename(png),
                    rc_val,
                    elapsed,
                )
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
                log.warning(
                    "  Could not locate gemini output for %s", os.path.basename(png)
                )

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
        if (
            getattr(args, "labeled", False)
            and backend == "gemini"
            and not args.dry_run
            and _has_labels
        ):
            _labeled_prompt_file = None
            # Use compressed image if available, else original PNG
            _labeled_img = (
                _compressed_tmp
                if (_compressed_tmp and os.path.isfile(_compressed_tmp))
                else png
            )
            try:
                labeled_prompt = build_labeled_prompt(view_key, rc, is_v1_done=v1_done)
                import tempfile as _tf2

                with _tf2.NamedTemporaryFile(
                    mode="w", suffix=".txt", delete=False, encoding="utf-8"
                ) as _lf:
                    _lf.write(labeled_prompt)
                    _labeled_prompt_file = _lf.name

                log.info(
                    "  Running: labeled enhance %s (%s)",
                    os.path.basename(png),
                    view_key,
                )
                t0_l = time.time()
                _cmd_l = [
                    sys.executable,
                    gemini_script,
                    "--prompt-file",
                    _labeled_prompt_file,
                    "--image",
                    _labeled_img,
                ]
                _cmd_l += model_arg
                _res_l = subprocess.run(
                    _cmd_l,
                    capture_output=True,
                    timeout=300,
                    encoding="utf-8",
                    errors="replace",
                )
                elapsed_l = time.time() - t0_l
                if _res_l.returncode == 0:
                    _lbl_path = None
                    for _line in (_res_l.stdout or "").split("\n"):
                        if "图片已保存:" in _line:
                            _lbl_path = _line[
                                _line.rfind("图片已保存:") + len("图片已保存:") :
                            ].strip()
                            break
                        if "已保存:" in _line:
                            _lbl_path = _line[
                                _line.rfind("已保存:") + len("已保存:") :
                            ].strip()
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
                        log.warning(
                            "  Labeled output not found for %s", os.path.basename(png)
                        )
                else:
                    log.warning(
                        "  Labeled enhance failed for %s (exit %d, %.1fs)",
                        os.path.basename(png),
                        _res_l.returncode,
                        elapsed_l,
                    )
            except Exception as _le:
                log.warning(
                    "  Labeled enhance error for %s: %s", os.path.basename(png), _le
                )
            finally:
                if _labeled_prompt_file and os.path.isfile(_labeled_prompt_file):
                    os.unlink(_labeled_prompt_file)

        # Clean up compressed temp images (deferred from first call's finally)
        if _compressed_tmp and os.path.isfile(_compressed_tmp):
            os.unlink(_compressed_tmp)
        if _ref_compressed_tmp and os.path.isfile(_ref_compressed_tmp):
            os.unlink(_ref_compressed_tmp)

    return 1 if failures else 0


def cmd_enhance_check(args):
    """Validate enhanced images against the current render manifest."""
    from pathlib import Path

    from tools.contract_io import load_json_required
    from tools.enhance_consistency import write_enhancement_report
    from tools.path_policy import assert_within_project

    project_root = Path(getattr(args, "project_root", None) or PROJECT_ROOT).resolve()
    render_dir = Path(args.dir)
    if not render_dir.is_absolute():
        render_dir = project_root / render_dir
    render_dir = render_dir.resolve()
    try:
        assert_within_project(render_dir, project_root, "render_dir")
    except ValueError as exc:
        log.error("%s", exc)
        return 1
    if not render_dir.is_dir():
        log.error("Render directory not found: %s", render_dir)
        return 1

    manifest_path = (
        Path(args.manifest)
        if getattr(args, "manifest", None)
        else render_dir / "render_manifest.json"
    )
    if not manifest_path.is_absolute():
        manifest_path = project_root / manifest_path
    manifest_path = manifest_path.resolve()
    output_path = getattr(args, "output", None)

    try:
        assert_within_project(manifest_path, project_root, "render manifest")
        manifest = load_json_required(manifest_path, "render manifest")
        if getattr(args, "subsystem", None):
            manifest_subsystem = manifest.get("subsystem")
            if manifest_subsystem and manifest_subsystem != args.subsystem:
                log.error(
                    "Subsystem mismatch: CLI --subsystem=%s, manifest subsystem=%s",
                    args.subsystem,
                    manifest_subsystem,
                )
                return 1

        manifest_render_dir = (
            manifest.get("render_dir_abs_resolved")
            or manifest.get("render_dir")
            or manifest.get("render_dir_rel_project")
        )
        if manifest_render_dir:
            manifest_render_dir_path = Path(manifest_render_dir)
            if not manifest_render_dir_path.is_absolute():
                manifest_render_dir_path = project_root / manifest_render_dir_path
            if manifest_render_dir_path.resolve() != render_dir:
                log.error(
                    "Render directory mismatch: CLI --dir=%s, manifest render_dir=%s",
                    render_dir,
                    manifest_render_dir_path.resolve(),
                )
                return 1

        report = write_enhancement_report(
            project_root,
            {**manifest, "manifest_path": str(manifest_path)},
            min_similarity=float(args.min_similarity),
            output_path=output_path,
        )
    except (FileNotFoundError, OSError, ValueError) as exc:
        log.error("%s", exc)
        return 1

    log.info(
        "Enhancement acceptance: %s (%s)",
        report["status"],
        report["enhancement_report"],
    )
    return 1 if report["status"] == "blocked" else 0


def cmd_annotate(args):
    """Add component labels to enhanced images."""
    from tools.render_qa import require_render_manifest

    annotate_script = os.path.join(SKILL_ROOT, "annotate_render.py")
    if not os.path.isfile(annotate_script):
        log.error("annotate_render.py not found at %s", annotate_script)
        return 1
    if getattr(args, "dir", None):
        try:
            require_render_manifest(args.dir, explicit=True)
        except FileNotFoundError as exc:
            log.error("%s", exc)
            return 1

    sub_dir = get_subsystem_dir(args.subsystem)
    # Auto-detect subsystem from manifest if not specified
    if not sub_dir and not args.config:
        _detect_dirs = []
        if getattr(args, "dir", None):
            _detect_dirs.append(args.dir)
        else:
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
        log.error("render_manifest.json not found in explicit render dir: %s", img_dir)
        return 1
    _use_manifest = os.path.isfile(_manifest_path)
    if _use_manifest:
        log.info("Annotate using manifest: %s", _manifest_path)
    for lang in args.lang.split(",") if "," in args.lang else [args.lang]:
        if _use_manifest:
            cmd = [
                sys.executable,
                annotate_script,
                "--manifest",
                _manifest_path,
                "--config",
                config_path,
                "--lang",
                lang.strip(),
            ]
        else:
            cmd = [
                sys.executable,
                annotate_script,
                "--all",
                "--dir",
                img_dir,
                "--config",
                config_path,
                "--lang",
                lang.strip(),
            ]
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
        log.error(
            "DESIGN_REVIEW still has %d CRITICAL issue(s). Cannot continue.", critical
        )
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
        pngs = (
            glob.glob(os.path.join(render_dir, "V*.png"))
            if os.path.isdir(render_dir)
            else []
        )

        status = "spec-only"
        if has_build:
            status = "buildable"
        if steps:
            status = "built"
        if pngs:
            status = "rendered"

        icon = {
            "spec-only": "[ ]",
            "buildable": "[B]",
            "built": "[*]",
            "rendered": "[R]",
        }
        log.info(
            "  %s %-25s [%s] build=%s config=%s STEP=%d DXF=%d PNG=%d",
            icon.get(status, "?"),
            entry,
            status,
            "Y" if has_build else "-",
            "Y" if has_config else "-",
            len(steps),
            len(dxfs),
            len(pngs),
        )

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


def cmd_sw_warmup(args):
    """SW Toolbox sldprt → STEP 批量预热（v4 §7）。"""
    from tools.sw_warmup import run_sw_warmup

    return run_sw_warmup(args)


def cmd_sw_toolbox_e2e(args):
    """真实 SW Toolbox 模型库 → STEP → codegen 消费端到端验收。"""
    from tools.sw_toolbox_e2e import run_sw_toolbox_e2e

    return run_sw_toolbox_e2e(args)


def cmd_sw_inspect(args):
    """F-1：SW 环境/索引/材质/warmup 产物诊断。"""
    from tools.sw_inspect import run_sw_inspect

    return run_sw_inspect(args)


def cmd_model_audit(args):
    """只读审计模型库几何质量报告。"""
    from tools.model_audit import run_model_audit

    return run_model_audit(args)


def cmd_model_import(args):
    """导入用户 STEP 并更新模型库映射。"""
    from tools.model_import import run_model_import

    return run_model_import(args)


def cmd_product_graph(args):
    """生成 PRODUCT_GRAPH.json 产品图契约。"""
    from tools.product_graph import write_product_graph

    if not args.subsystem:
        log.error("--subsystem is required")
        return 1
    output = write_product_graph(
        PROJECT_ROOT,
        args.subsystem,
        output=getattr(args, "output", None),
    )
    log.info("PRODUCT_GRAPH.json written: %s", output)
    return 0


def cmd_project_guide(args):
    """生成普通用户/大模型只读项目下一步向导。"""
    from tools.project_guide import (
        command_return_code_for_project_guide,
        write_project_guide,
    )

    if not args.subsystem:
        log.error("--subsystem is required")
        return 1
    report = write_project_guide(
        PROJECT_ROOT,
        args.subsystem,
        design_doc=getattr(args, "design_doc", None),
        artifact_index_path=getattr(args, "artifact_index", None),
        output_path=getattr(args, "output", None),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    log.info("PROJECT_GUIDE: %s", report.get("ordinary_user_message"))
    return command_return_code_for_project_guide(report)


def cmd_photo3d(args):
    """运行照片级 3D 契约门禁。"""
    from tools.photo3d_gate import run_photo3d_gate

    if not args.subsystem:
        log.error("--subsystem is required")
        return 1
    report = run_photo3d_gate(
        PROJECT_ROOT,
        args.subsystem,
        artifact_index_path=getattr(args, "artifact_index", None),
        change_scope_path=getattr(args, "change_scope", None),
        baseline_signature_path=getattr(args, "baseline_signature", None),
        output_path=getattr(args, "output", None),
        config=_load_pipeline_config(),
    )
    status = report.get("status")
    log.info("PHOTO3D_REPORT: %s", report.get("ordinary_user_message"))
    return 0 if status in {"pass", "warning"} else 1


def cmd_photo3d_autopilot(args):
    """运行 Photo3D 门禁并写出普通用户下一步报告。"""
    from tools.photo3d_autopilot import write_photo3d_autopilot_report
    from tools.photo3d_gate import run_photo3d_gate

    if not args.subsystem:
        log.error("--subsystem is required")
        return 1
    report = run_photo3d_gate(
        PROJECT_ROOT,
        args.subsystem,
        artifact_index_path=getattr(args, "artifact_index", None),
        change_scope_path=getattr(args, "change_scope", None),
        baseline_signature_path=getattr(args, "baseline_signature", None),
        output_path=None,
    )
    autopilot_report = write_photo3d_autopilot_report(
        PROJECT_ROOT,
        args.subsystem,
        report,
        artifact_index_path=getattr(args, "artifact_index", None),
        output_path=getattr(args, "output", None),
    )
    log.info("PHOTO3D_AUTOPILOT: %s", autopilot_report.get("ordinary_user_message"))
    return 0 if report.get("status") in {"pass", "warning"} else 1


def cmd_photo3d_action(args):
    """预览或确认执行 Photo3D action plan 中的低风险动作。"""
    from tools.photo3d_action_runner import command_return_code, run_photo3d_action

    if not args.subsystem:
        log.error("--subsystem is required")
        return 1
    report = run_photo3d_action(
        PROJECT_ROOT,
        args.subsystem,
        artifact_index_path=getattr(args, "artifact_index", None),
        autopilot_report_path=getattr(args, "autopilot_report", None),
        action_plan_path=getattr(args, "action_plan", None),
        action_id=getattr(args, "action_id", None),
        confirm=bool(getattr(args, "confirm", False)),
        output_path=getattr(args, "output", None),
    )
    log.info("PHOTO3D_ACTION_RUN: %s", report.get("ordinary_user_message"))
    return command_return_code(report)


def cmd_photo3d_run(args):
    """运行 Photo3D 多轮普通用户向导。"""
    from tools.photo3d_loop import command_return_code_for_loop, run_photo3d_loop

    if not args.subsystem:
        log.error("--subsystem is required")
        return 1
    report = run_photo3d_loop(
        PROJECT_ROOT,
        args.subsystem,
        artifact_index_path=getattr(args, "artifact_index", None),
        max_rounds=int(getattr(args, "max_rounds", 3) or 3),
        confirm_actions=bool(getattr(args, "confirm_actions", False)),
        output_path=getattr(args, "output", None),
    )
    log.info("PHOTO3D_RUN: %s", report.get("ordinary_user_message"))
    return command_return_code_for_loop(report)


def cmd_photo3d_handoff(args):
    """预览或确认执行当前 Photo3D 下一步交接动作。"""
    from tools.photo3d_handoff import command_return_code, run_photo3d_handoff

    if not args.subsystem:
        log.error("--subsystem is required")
        return 1
    try:
        report = run_photo3d_handoff(
            PROJECT_ROOT,
            args.subsystem,
            artifact_index_path=getattr(args, "artifact_index", None),
            source=getattr(args, "source", None),
            confirm=bool(getattr(args, "confirm", False)),
            provider_preset=getattr(args, "provider_preset", None),
            output_path=getattr(args, "output", None),
        )
    except (FileNotFoundError, OSError, ValueError) as exc:
        log.error("PHOTO3D_HANDOFF failed: %s", exc)
        return 1
    log.info("PHOTO3D_HANDOFF: %s", report.get("ordinary_user_message"))
    return command_return_code(report)


def cmd_photo3d_recover(args):
    """执行绑定当前 run_id 的 Photo3D 低风险恢复动作。"""
    from tools.photo3d_recover import run_photo3d_recover

    if not args.subsystem:
        log.error("--subsystem is required")
        return 1
    try:
        report = run_photo3d_recover(
            PROJECT_ROOT,
            args.subsystem,
            getattr(args, "run_id", ""),
            artifact_index_path=getattr(args, "artifact_index", None),
            action=getattr(args, "action", ""),
        )
    except (FileNotFoundError, ValueError) as exc:
        log.error("PHOTO3D_RECOVER failed: %s", exc)
        return 1
    log.info(
        "PHOTO3D_RECOVER %s for %s/%s returned %s",
        report.get("action"),
        report.get("subsystem"),
        report.get("run_id"),
        report.get("returncode"),
    )
    return int(report.get("returncode") or 0)


def cmd_accept_baseline(args):
    """接受当前通过门禁的 Photo3D run 作为后续漂移基准。"""
    from tools.photo3d_baseline import accept_photo3d_baseline

    if not args.subsystem:
        log.error("--subsystem is required")
        return 1
    try:
        accepted = accept_photo3d_baseline(
            PROJECT_ROOT,
            args.subsystem,
            artifact_index_path=getattr(args, "artifact_index", None),
            run_id=getattr(args, "run_id", None),
            report_path=getattr(args, "report", None),
        )
    except (FileNotFoundError, OSError, ValueError) as exc:
        log.error("%s", exc)
        return 1
    log.info("Accepted Photo3D baseline: %s", accepted["run_id"])
    log.info("Baseline signature: %s", accepted["baseline_signature"])
    return 0


def cmd_sw_export_plan(args):
    """生成只读 SolidWorks Toolbox 导出候选计划。"""
    from codegen.gen_build import parse_bom_tree
    from parts_resolver import load_registry
    from tools.sw_export_plan import build_sw_export_plan, write_sw_export_plan

    spec_path = args.spec or os.path.join(
        PROJECT_ROOT, "cad", args.subsystem, "CAD_SPEC.md"
    )
    if not os.path.isfile(spec_path):
        log.error("CAD_SPEC.md 不存在: %s", spec_path)
        return 1
    bom_rows = parse_bom_tree(spec_path)
    registry = load_registry(project_root=PROJECT_ROOT)
    context = ModelProjectContext.for_subsystem(
        args.subsystem,
        project_root=PROJECT_ROOT,
    )
    plan = build_sw_export_plan(bom_rows, registry, context)
    output_path = write_sw_export_plan(plan, context)
    if args.json:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    else:
        print(f"sw_export_plan: {output_path}")
        print(f"candidates: {len(plan.get('candidates', []))}")
    return 0


# ═════════════════════════════════════════════════════════════════════════════
def cmd_init(args):
    """Scaffold a new subsystem directory with template files."""
    sub_name = args.subsystem
    if not sub_name:
        log.error("--subsystem is required for init")
        return 1

    # Subsystem scaffolds live under PROJECT_ROOT/cad/<name>/ — same dir that
    # get_subsystem_dir() resolves for codegen/build/render phases. The historic
    # "output_dir" config key was never read by other phases and caused init
    # artifacts to land in the spec-stage scratch area, breaking codegen lookup.
    sub_dir = os.path.join(PROJECT_ROOT, "cad", sub_name)

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
            "bounding_radius_mm": 300,
        },
        "coordinate_system": "Z-axis vertical. Describe your coordinate convention here.",
        "materials": {
            "body": {
                "preset": "brushed_aluminum",
                "label": "Main body",
                "name_cn": "主体",
                "name_en": "Main Body",
            },
            "fastener": {
                "preset": "stainless_304",
                "label": "Fasteners",
                "name_cn": "紧固件",
                "name_en": "Fasteners",
            },
        },
        "camera": {
            "V1": {
                "name": "V1_front_iso",
                "type": "standard",
                "azimuth_deg": 35,
                "elevation_deg": 25,
                "distance_factor": 2.5,
                "description": "Front-left isometric — main showcase",
            },
            "V2": {
                "name": "V2_rear_oblique",
                "type": "standard",
                "azimuth_deg": 215,
                "elevation_deg": 20,
                "distance_factor": 2.8,
                "description": "Rear-right oblique — back detail",
            },
            "V3": {
                "name": "V3_exploded",
                "type": "exploded",
                "azimuth_deg": 35,
                "elevation_deg": 35,
                "distance_factor": 3.5,
                "description": "Exploded view (render_exploded.py)",
            },
            "V4": {
                "name": "V4_ortho_front",
                "type": "ortho",
                "azimuth_deg": 0,
                "elevation_deg": 0,
                "description": "Front orthographic — auto-scaled to fit model",
            },
        },
        "components": {
            "body": {"name_cn": "主体", "name_en": "Main Body", "material": "body"}
        },
        "labels": {
            "_doc": "Only visible components per view. Coords at 1920x1080 ref, auto-scaled.",
            "V1": [{"component": "body", "anchor": [600, 400], "label": [1600, 200]}],
        },
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
    doc_base = os.path.join(PROJECT_ROOT, "docs", "design")
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
    log.info(
        "  3. Edit %s/render_config.json — update camera views and labels", sub_dir
    )
    log.info(
        "  4. Run: python cad_pipeline.py full --subsystem %s --design-doc %s",
        sub_name,
        doc_path,
    )
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
  %(prog)s model-audit --subsystem end_effector
  %(prog)s model-import --subsystem end_effector --part-no P-001 --step models/p.step
  %(prog)s status
  %(prog)s env-check
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("-v", "--verbose", action="store_true", help="Debug output")
    parser.add_argument("-q", "--quiet", action="store_true", help="Warnings only")
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate without executing"
    )

    sub = parser.add_subparsers(dest="command", help="Pipeline command")

    # spec
    p_spec = sub.add_parser("spec", help="Design review + CAD_SPEC.md generation")
    p_spec.add_argument("--subsystem", "-s", default=None)
    p_spec.add_argument("--design-doc", help="Path to design document (NN-*.md)")
    p_spec.add_argument(
        "--auto-fill", action="store_true", help="Auto-fill computable values"
    )
    p_spec.add_argument("--force", action="store_true", help="Force regeneration")
    p_spec.add_argument(
        "--review-only",
        action="store_true",
        help="Generate DESIGN_REVIEW only (no interaction, no CAD_SPEC.md). For Agent-driven review.",
    )
    p_spec.add_argument(
        "--proceed",
        action="store_true",
        help="Skip interaction, generate CAD_SPEC.md with existing data",
    )
    p_spec.add_argument(
        "--supplements",
        default=None,
        help='JSON string of Agent-collected supplements, e.g. \'{"B3":"4xM4","D2":"__AUTO__"}\'. '
        "Written to user_supplements.json then spec is generated.",
    )
    p_spec.add_argument(
        "--out-dir",
        type=str,
        default=None,
        help="Override subsystem output root (default: cad/<subsystem>/). "
        "Used by tests to redirect writes away from pinned subsystem dirs.",
    )

    # codegen
    p_codegen = sub.add_parser(
        "codegen", help="Generate CadQuery scaffolds from CAD_SPEC.md"
    )
    p_codegen.add_argument("--subsystem", "-s", default=None)
    p_codegen.add_argument(
        "--force", action="store_true", help="Overwrite existing files"
    )
    p_codegen.add_argument(
        "--force-layout",
        action="store_true",
        help="Rebuild assembly_layout.py; plain --force preserves manual layout",
    )

    # build
    p_build = sub.add_parser("build", help="Build STEP + DXF files")
    p_build.add_argument("--subsystem", "-s", default=None)
    p_build.add_argument(
        "--render", action="store_true", help="Also render after build"
    )
    p_build.add_argument(
        "--skip-orientation",
        dest="skip_orientation",
        action="store_true",
        help="Bypass orientation_check.py pre-gate (not recommended)",
    )

    # render
    p_render = sub.add_parser("render", help="Blender Cycles rendering")
    p_render.add_argument("--subsystem", "-s", default=None)
    p_render.add_argument("--view", help="Single view (V1-V5)")
    p_render.add_argument(
        "--timestamp", action="store_true", help="Append timestamp to filenames"
    )
    p_render.add_argument(
        "--output-dir", help="Override output directory for rendered PNGs"
    )

    # enhance
    p_enhance = sub.add_parser(
        "enhance", help="AI enhancement (Gemini, ComfyUI, or fal Cloud ComfyUI)"
    )
    p_enhance.add_argument("--subsystem", "-s", default=None)
    p_enhance.add_argument("--dir", help="Directory with V*.png files")
    p_enhance.add_argument(
        "--backend",
        choices=["gemini", "comfyui", "fal", "fal_comfy", "engineering"],
        help="Override enhance backend (default: from pipeline_config.json). "
        "'engineering' = no AI, Blender PBR direct + post-processing.",
    )
    p_enhance.add_argument(
        "--labeled",
        action="store_true",
        help="Also generate English-labeled version via Gemini (gemini backend only)",
    )
    p_enhance.add_argument(
        "--model",
        default=None,
        help="Override model key from pipeline_config.json (e.g. nano_banana_2)",
    )

    # enhance-check
    p_enhance_check = sub.add_parser(
        "enhance-check",
        help="Validate enhanced image delivery status",
        description=(
            "Enhancement consistency acceptance: reads the explicit render "
            "directory's render_manifest.json, matches each manifest view to an "
            "enhanced image in the same directory, and writes ENHANCEMENT_REPORT.json."
        ),
        epilog=(
            "Typical: python cad_pipeline.py enhance-check --subsystem <name> --dir <render_dir>\n"
            "Status semantics: accepted = every manifest view has a matching "
            "enhanced image and consistency passes; preview = enhanced images exist "
            "but shape/QA consistency needs review; blocked = required views or "
            "inputs are missing. The command does not scan directories for the "
            "newest file and never accepts enhanced images outside --dir.\n"
            "Use --manifest to bind a specific render_manifest.json, --output to "
            "override ENHANCEMENT_REPORT.json, and --min-similarity to adjust the "
            "generic mask-IoU threshold."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_enhance_check.add_argument("--subsystem", "-s", default=None)
    p_enhance_check.add_argument(
        "--dir",
        required=True,
        help="Explicit current render directory; no fallback scanning is performed",
    )
    p_enhance_check.add_argument(
        "--manifest",
        default=None,
        help="Explicit render_manifest.json path (default: --dir/render_manifest.json)",
    )
    p_enhance_check.add_argument(
        "--output",
        default=None,
        help="ENHANCEMENT_REPORT.json output path (default: --dir/ENHANCEMENT_REPORT.json)",
    )
    p_enhance_check.add_argument(
        "--min-similarity",
        type=float,
        default=0.85,
        help="Minimum source/enhanced shape similarity for accepted status",
    )

    # annotate
    p_annotate = sub.add_parser("annotate", help="Add component labels")
    p_annotate.add_argument("--subsystem", "-s", default=None)
    p_annotate.add_argument("--config", help="render_config.json path")
    p_annotate.add_argument("--dir", help="Directory with images")
    p_annotate.add_argument(
        "--lang", default="cn,en", help="Languages (default: cn,en)"
    )

    # full
    p_full = sub.add_parser(
        "full", help="Full pipeline: spec→codegen→build→render→enhance→annotate"
    )
    p_full.add_argument("--subsystem", "-s", default=None)
    p_full.add_argument("--design-doc", help="Path to design document (NN-*.md)")
    p_full.add_argument(
        "--auto-fill", action="store_true", help="Auto-fill computable values"
    )
    p_full.add_argument(
        "--force-spec", action="store_true", help="Force spec regeneration"
    )
    p_full.add_argument("--force", action="store_true", help="Force codegen overwrite")
    p_full.add_argument(
        "--force-layout",
        action="store_true",
        help="Rebuild assembly_layout.py during codegen; plain --force preserves it",
    )
    p_full.add_argument(
        "--render",
        action="store_true",
        default=False,
        help="Pass --render to build_all.py (normally handled by RENDER phase)",
    )
    p_full.add_argument("--view", default=None)
    p_full.add_argument("--dir", default=None)
    p_full.add_argument("--config", default=None)
    p_full.add_argument("--lang", default="cn,en")
    p_full.add_argument(
        "--timestamp", action="store_true", help="Append timestamp to renders"
    )
    p_full.add_argument("--skip-spec", action="store_true", help="Skip spec generation")
    p_full.add_argument(
        "--skip-codegen", action="store_true", help="Skip code generation"
    )
    p_full.add_argument("--skip-enhance", action="store_true")
    p_full.add_argument("--skip-annotate", action="store_true")
    p_full.add_argument(
        "--labeled",
        action="store_true",
        help="Generate English-labeled enhanced images (gemini only)",
    )
    p_full.add_argument(
        "--agent-review",
        action="store_true",
        help="Agent-driven review: run Phase 1 review-only, output JSON path, exit 10 for Agent to process",
    )

    # init
    p_init = sub.add_parser("init", help="Scaffold a new subsystem directory")
    p_init.add_argument(
        "--subsystem", required=True, help="Subsystem directory name (e.g. my_device)"
    )
    p_init.add_argument(
        "--name-cn", default="", help="Chinese display name (e.g. 末端执行机构)"
    )
    p_init.add_argument("--prefix", default="", help="Part number prefix (e.g. GIS-EE)")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing files")

    # status
    sub.add_parser("status", help="Show pipeline status")

    # env-check
    sub.add_parser("env-check", help="Validate environment")

    # sw-warmup（v4 §7）
    p_sw_warmup = sub.add_parser(
        "sw-warmup",
        help="批量预热 SW Toolbox sldprt → STEP 缓存（v4 §7）",
    )
    p_sw_warmup.add_argument(
        "--standard", help="逗号分隔标准，如 GB,ISO,DIN（默认 GB）"
    )
    p_sw_warmup.add_argument("--bom", help="BOM CSV 路径（按行匹配 sldprt）")
    p_sw_warmup.add_argument(
        "--all", action="store_true", help="预热所有 1818 个标准件"
    )
    p_sw_warmup.add_argument("--dry-run", action="store_true", help="只列目标不调 COM")
    p_sw_warmup.add_argument("--overwrite", action="store_true", help="覆盖已有缓存")
    p_sw_warmup.add_argument(
        "--smoke-test",
        action="store_true",
        help="转换单件验收（GB/bearing 第一个件），exit 0=PASS / exit 2=FAIL",
    )

    # sw-toolbox-e2e：真实模型库闭环验收（手动/runner 用）
    p_sw_toolbox_e2e = sub.add_parser(
        "sw-toolbox-e2e",
        help="真实 SW Toolbox 模型库 → STEP → codegen 消费端到端验收",
    )
    p_sw_toolbox_e2e.add_argument(
        "--out-dir",
        default="artifacts/sw-toolbox-e2e",
        help="写入 mini project、geometry_report 和 sw_toolbox_e2e.json 的目录",
    )

    # sw-inspect（F-1 子命令）
    p_sw_inspect = sub.add_parser(
        "sw-inspect",
        help="SolidWorks 环境/索引/材质/产物快速诊断（--deep 启动 COM）",
    )
    p_sw_inspect.add_argument(
        "--deep",
        action="store_true",
        help="启动 win32com Dispatch + LoadAddIn（冷启约 10–20s，纯诊断用）",
    )
    p_sw_inspect.add_argument(
        "--json",
        action="store_true",
        help="输出机读 JSON 而非彩色文本",
    )
    p_sw_inspect.add_argument(
        "--resolve-report",
        metavar="PATH",
        default=None,
        help="展示指定 resolve_report.json 的路由诊断摘要",
    )

    # model-audit：只读模型库质量审计
    p_model_audit = sub.add_parser(
        "model-audit",
        help="只读审计 geometry_report.json 中的模型库几何质量",
    )
    p_model_audit.add_argument("--subsystem", "-s", default=None)
    p_model_audit.add_argument(
        "--report",
        default=None,
        help="显式指定 geometry_report.json；相对路径以 CAD_PROJECT_ROOT 为锚点",
    )
    p_model_audit.add_argument(
        "--json",
        action="store_true",
        help="输出机读 JSON",
    )
    p_model_audit.add_argument(
        "--strict",
        action="store_true",
        help="存在需审查模型或缺失 STEP 路径时返回 exit 1",
    )

    # model-import：导入用户 STEP 到模型库
    p_model_import = sub.add_parser(
        "model-import",
        help="导入用户 STEP，更新 parts_library.yaml 并验证 resolver 消费",
    )
    p_model_import.add_argument("--subsystem", "-s", default=None)
    p_model_import.add_argument("--part-no", required=True, help="BOM part_no")
    p_model_import.add_argument("--name-cn", default="", help="中文零件名")
    p_model_import.add_argument(
        "--step",
        required=True,
        help="STEP/STP 文件路径；相对路径以 CAD_PROJECT_ROOT 为锚点",
    )
    p_model_import.add_argument("--json", action="store_true", help="输出机读 JSON")
    p_model_import.add_argument(
        "--no-verify",
        action="store_true",
        help="跳过导入后的 resolver 消费校验",
    )

    # product-graph：生成照片级 3D 产品图契约
    p_product_graph = sub.add_parser(
        "product-graph",
        help="Generate PRODUCT_GRAPH.json contract from CAD_SPEC.md",
    )
    p_product_graph.add_argument("--subsystem", "-s", required=True)
    p_product_graph.add_argument(
        "--output",
        default=None,
        help="Output PRODUCT_GRAPH.json path (default: cad/<subsystem>/PRODUCT_GRAPH.json)",
    )

    # project-guide：普通用户/大模型只读项目下一步向导
    p_project_guide = sub.add_parser(
        "project-guide",
        help="Read-only ordinary-user project next-step guide",
        description=(
            "project-guide 普通用户/大模型向导：只读检查显式子系统、可选设计文档、"
            "固定 CAD_SPEC/codegen 文件和 ARTIFACT_INDEX.json active_run_id，写出 "
            "PROJECT_GUIDE.json 与下一条安全命令；ready_for_enhancement 时可附带 "
            "provider preset 选择、ordinary_user_options 普通用户可读选项、"
            "provider_wizard 展示向导、provider_health 只读配置健康摘要和 "
            "photo3d-handoff --provider-preset 预览命令。"
            "该命令 read-only，does not "
            "scan directories，does not mutate pipeline state；不会接受 baseline，"
            "不会运行 enhance，不接受任意 backend/URL/API key/model/JSON argv，"
            "也不会猜最新 run。"
        ),
        epilog=(
            "Typical first step: python cad_pipeline.py project-guide --subsystem <name> "
            "--design-doc <path>\n"
            "Statuses: needs_init, needs_design_doc, needs_spec, needs_codegen, "
            "needs_build_render, ready_for_photo3d_run. After ready_for_photo3d_run, "
            "run the recommended photo3d-run command. Later user-confirmed handoffs "
            "remain explicit: accept-baseline for baseline acceptance and enhance-check "
            "with an explicit render dir for ENHANCEMENT_REPORT.json. When the active "
            "run's PHOTO3D_RUN.json is ready_for_enhancement, PROJECT_GUIDE.json may "
            "include allowlisted provider preset choices, ordinary_user_options with "
            "titles/summaries/setup hints, a provider_wizard built from those options, "
            "provider_health availability status that checks local config/dependency "
            "presence without exposing secrets, URLs, endpoints, or env var values, "
            "and preview commands such as "
            "python cad_pipeline.py photo3d-handoff --provider-preset engineering; "
            "project-guide itself still does not run enhancement or append --confirm."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_project_guide.add_argument("--subsystem", "-s", required=True)
    p_project_guide.add_argument(
        "--design-doc",
        default=None,
        help="Explicit design document path; no fallback document search is performed",
    )
    p_project_guide.add_argument(
        "--artifact-index",
        default=None,
        help="Explicit ARTIFACT_INDEX.json path; default is cad/<subsystem>/.cad-spec-gen/ARTIFACT_INDEX.json if it exists",
    )
    p_project_guide.add_argument(
        "--output",
        default=None,
        help="PROJECT_GUIDE.json output path (default: guide directory or current run directory)",
    )

    # photo3d：运行照片级契约门禁
    p_photo3d = sub.add_parser(
        "photo3d",
        help="Run contract gate before photorealistic enhancement",
        description=(
            "Photo3D 契约门禁：在 AI 增强前验证当前 run_id 的产品图、模型契约、"
            "装配签名、渲染清单和 baseline 漂移。通过时可进入增强；失败时写出"
            "普通用户可读的 PHOTO3D_REPORT.json、ACTION_PLAN.json 和 "
            "LLM_CONTEXT_PACK.json，供大模型按允许动作继续。"
        ),
        epilog=(
            "Typical: python cad_pipeline.py photo3d --subsystem <name>\n"
            "Ordinary users and LLM agents can start one level higher with "
            "project-guide: python cad_pipeline.py project-guide --subsystem "
            "<name> --design-doc <path>. It writes PROJECT_GUIDE.json, is "
            "read-only, does not mutate pipeline state, and does not scan "
            "directories.\n"
            "Artifacts are resolved only through ARTIFACT_INDEX.json for the active "
            "run_id; the command does not scan directories for the newest PNG.\n"
            "Gate status: pass = CAD contract gate passed; warning = CAD gate passed "
            "with non-blocking warnings; blocked = CAD gate failed and enhancement "
            "must not run. PHOTO3D_REPORT.json enhancement_status is blocked or "
            "not_run at this gate stage.\n"
            "Ordinary users can run: python cad_pipeline.py photo3d-autopilot "
            "--subsystem <name>. It writes PHOTO3D_AUTOPILOT.json with the next "
            "safe action and still never scans directories for the newest file.\n"
            "When blocked actions are low-risk CLI recoveries, ordinary users can "
            "preview then explicitly confirm: python cad_pipeline.py photo3d-action "
            "--subsystem <name> --confirm. This writes PHOTO3D_ACTION_RUN.json and "
            "does not run enhancement or baseline acceptance. The underlying "
            "ACTION_PLAN.json recovery commands must be run-aware photo3d-recover "
            "commands with --run-id and --artifact-index; bare render/build/"
            "product-graph commands are not automatic recoveries.\n"
            "For a foolproof multi-round guide, run: python cad_pipeline.py "
            "photo3d-run --subsystem <name>. It writes PHOTO3D_RUN.json, uses "
            "--max-rounds / --confirm-actions, and stops at "
            "needs_baseline_acceptance, ready_for_enhancement, needs_user_input, "
            "needs_manual_review, execution_failed, or loop_limit_reached without "
            "silently accepting baseline or running enhancement.\n"
            "When the user says to execute the recommendation, use: python "
            "cad_pipeline.py photo3d-handoff --subsystem <name>. It writes "
            "PHOTO3D_HANDOFF.json and only with --confirm executes recognized "
            "current next actions, rebuilding argv from ARTIFACT_INDEX.json and "
            "active_run_id instead of trusting JSON argv.\n"
            "Enhancement delivery status used later: accepted = CAD gate and "
            "enhancement consistency pass; preview = CAD gate pass but enhancement "
            "consistency is unverified or failed; blocked = CAD gate failed. After "
            "enhance writes *_enhanced.* files, run python cad_pipeline.py "
            "enhance-check --subsystem <name> --dir <render_dir> to write "
            "ENHANCEMENT_REPORT.json; it does not scan directories for the newest "
            "file and only accepts enhanced images inside the explicit render dir.\n"
            "The first pass is only a candidate baseline; after user confirmation, "
            "run: python cad_pipeline.py accept-baseline --subsystem <name>. "
            "This records accepted_baseline_run_id in ARTIFACT_INDEX.json without "
            "switching active_run_id. Later photo3d --change-scope reuses that "
            "baseline unless --baseline-signature explicitly overrides it."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_photo3d.add_argument("--subsystem", "-s", required=True)
    p_photo3d.add_argument(
        "--artifact-index",
        default=None,
        help=(
            "ARTIFACT_INDEX.json path (default: "
            "cad/<subsystem>/.cad-spec-gen/ARTIFACT_INDEX.json). "
            "This is the only artifact discovery source for the current run_id."
        ),
    )
    p_photo3d.add_argument(
        "--change-scope",
        default=None,
        help="Optional CHANGE_SCOPE.json for baseline drift checking",
    )
    p_photo3d.add_argument(
        "--baseline-signature",
        default=None,
        help="Optional baseline ASSEMBLY_SIGNATURE.json for accepted baseline comparison",
    )
    p_photo3d.add_argument(
        "--output",
        default=None,
        help=(
            "PHOTO3D_REPORT.json output path; blocked runs also write "
            "ACTION_PLAN.json and LLM_CONTEXT_PACK.json beside the active run artifacts"
        ),
    )

    # photo3d-autopilot：普通用户下一步报告
    p_photo3d_autopilot = sub.add_parser(
        "photo3d-autopilot",
        help="Run Photo3D gate and write the ordinary-user next-action report",
        description=(
            "Photo3D autopilot 普通用户流程：运行契约门禁，只通过 "
            "ARTIFACT_INDEX.json 的 active run_id 找产物，写出 "
            "PHOTO3D_REPORT.json 与 PHOTO3D_AUTOPILOT.json。阻断时沿用 "
            "ACTION_PLAN.json / LLM_CONTEXT_PACK.json；通过时只给出下一步命令，"
            "不会静默 accept-baseline 或扫描目录猜最新文件。"
        ),
        epilog=(
            "Typical: python cad_pipeline.py photo3d-autopilot --subsystem <name>\n"
            "For a broader ordinary-user and LLM handoff across init/spec/codegen/"
            "build-render/photo3d-run, start with: python cad_pipeline.py "
            "project-guide --subsystem <name> --design-doc <path>. It writes "
            "PROJECT_GUIDE.json, is read-only, does not mutate pipeline state, "
            "and does not scan directories. "
            "Gate status remains pass/warning/blocked. Enhancement delivery status "
            "remains accepted/preview/blocked and is not produced by this command; "
            "PHOTO3D_REPORT.json enhancement_status stays not_run or blocked here. "
            "After ready_for_enhancement, run enhance, then run enhance-check with "
            "the explicit render dir to write ENHANCEMENT_REPORT.json; it does not "
            "scan directories for the newest file. "
            "If the first pass/warning run has no accepted baseline, autopilot "
            "recommends: python cad_pipeline.py accept-baseline --subsystem <name>. "
            "That explicit command records accepted_baseline_run_id in "
            "ARTIFACT_INDEX.json; this autopilot command only reports the next "
            "action and never mutates the baseline. If gate status is blocked, "
            "preview/execute allowlisted low-risk ACTION_PLAN.json recovery steps "
            "with: python cad_pipeline.py photo3d-action --subsystem <name> --confirm; "
            "that command writes PHOTO3D_ACTION_RUN.json and keeps user-input "
            "actions for the user. ACTION_PLAN.json low-risk CLI recoveries must "
            "be encoded as photo3d-recover --run-id <run_id> --artifact-index <path> "
            "--action product-graph|build|render, never as bare render/build/"
            "product-graph commands. Multi-round users can run: python cad_pipeline.py "
            "photo3d-run --subsystem <name>. It writes PHOTO3D_RUN.json, supports "
            "--max-rounds and --confirm-actions, and stops at needs_baseline_acceptance, "
            "ready_for_enhancement, needs_user_input, needs_manual_review, "
            "execution_failed, or loop_limit_reached. When the user says to execute "
            "the current recommendation, use python cad_pipeline.py photo3d-handoff "
            "--subsystem <name>; it writes PHOTO3D_HANDOFF.json and, only with "
            "--confirm, executes recognized current next actions without trusting "
            "JSON argv."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_photo3d_autopilot.add_argument("--subsystem", "-s", required=True)
    p_photo3d_autopilot.add_argument(
        "--artifact-index",
        default=None,
        help=(
            "ARTIFACT_INDEX.json path (default: "
            "cad/<subsystem>/.cad-spec-gen/ARTIFACT_INDEX.json). "
            "This is the only artifact discovery source for the current run_id."
        ),
    )
    p_photo3d_autopilot.add_argument(
        "--change-scope",
        default=None,
        help="Optional CHANGE_SCOPE.json for baseline drift checking",
    )
    p_photo3d_autopilot.add_argument(
        "--baseline-signature",
        default=None,
        help="Optional baseline ASSEMBLY_SIGNATURE.json for accepted baseline comparison",
    )
    p_photo3d_autopilot.add_argument(
        "--output",
        default=None,
        help="PHOTO3D_AUTOPILOT.json output path (default: current run directory)",
    )

    # photo3d-action：确认后执行当前 run 动作计划中的低风险 CLI 动作
    p_photo3d_action = sub.add_parser(
        "photo3d-action",
        help="Preview or confirm low-risk Photo3D action-plan CLI recovery steps",
        description=(
            "Photo3D action runner：读取当前 active run 的 "
            "PHOTO3D_AUTOPILOT.json / ACTION_PLAN.json，默认只预览可执行动作；"
            "只有传 --confirm 才会执行 low-risk、无需用户输入、白名单内的 CLI "
            "恢复动作。用户输入类动作会保留给用户处理。"
        ),
        epilog=(
            "Typical preview: python cad_pipeline.py photo3d-action --subsystem <name>\n"
            "Typical execute: python cad_pipeline.py photo3d-action --subsystem <name> --confirm\n"
            "Allowed automatic CLI recovery commands are limited to product-graph, "
            "build, and render for the same subsystem/run_id, and ACTION_PLAN.json "
            "must encode them as the run-aware wrapper: python cad_pipeline.py "
            "photo3d-recover --subsystem <name> --run-id <run_id> "
            "--artifact-index cad/<name>/.cad-spec-gen/ARTIFACT_INDEX.json "
            "--action product-graph|build|render. The command only "
            "resolves files through ARTIFACT_INDEX.json active_run_id and current "
            "run directory; it does not scan directories for latest artifacts and "
            "does not run enhancement or baseline acceptance.\n"
            "After all confirmed low-risk CLI actions succeed and no user-input "
            "actions remain, it 自动重跑 photo3d-autopilot and records the next "
            "ordinary-user summary under post_action_autopilot in "
            "PHOTO3D_ACTION_RUN.json. Preview, failed execution, or remaining "
            "用户输入 actions do not rerun autopilot."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_photo3d_action.add_argument("--subsystem", "-s", required=True)
    p_photo3d_action.add_argument(
        "--artifact-index",
        default=None,
        help=(
            "ARTIFACT_INDEX.json path (default: "
            "cad/<subsystem>/.cad-spec-gen/ARTIFACT_INDEX.json). "
            "This is the only active run_id source."
        ),
    )
    p_photo3d_action.add_argument(
        "--autopilot-report",
        default=None,
        help="PHOTO3D_AUTOPILOT.json path (default: active run directory)",
    )
    p_photo3d_action.add_argument(
        "--action-plan",
        default=None,
        help="ACTION_PLAN.json path (default: value referenced by PHOTO3D_AUTOPILOT.json)",
    )
    p_photo3d_action.add_argument(
        "--action-id",
        default=None,
        help="Optional action_id to execute/preview; default considers all actions",
    )
    p_photo3d_action.add_argument(
        "--confirm",
        action="store_true",
        help="Actually execute allowlisted low-risk CLI actions; omitted means preview only",
    )
    p_photo3d_action.add_argument(
        "--output",
        default=None,
        help="PHOTO3D_ACTION_RUN.json output path (default: current run directory)",
    )

    # photo3d-run：普通用户多轮向导，只推进到下一处需要确认/输入/增强的位置
    p_photo3d_run = sub.add_parser(
        "photo3d-run",
        help="Run the Photo3D ordinary-user multi-round guide",
        description=(
            "Photo3D 多轮向导：按当前 active run 的 ARTIFACT_INDEX.json 运行 "
            "photo3d gate + photo3d-autopilot，并在用户显式传 --confirm-actions "
            "时执行 low-risk action plan 恢复动作。该命令写 PHOTO3D_RUN.json，"
            "不会扫描目录猜最新产物，不会静默 accept-baseline，不会运行 enhance。"
        ),
        epilog=(
            "Typical preview: python cad_pipeline.py photo3d-run --subsystem <name>\n"
            "Typical confirmed recovery loop: python cad_pipeline.py photo3d-run "
            "--subsystem <name> --confirm-actions\n"
            "The loop stops at needs_baseline_acceptance, ready_for_enhancement, "
            "needs_user_input, needs_manual_review, execution_failed, or "
            "loop_limit_reached. All artifacts remain bound to active_run_id and "
            "PHOTO3D_RUN.json is written inside cad/<name>/.cad-spec-gen/runs/<run_id>."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_photo3d_run.add_argument("--subsystem", "-s", required=True)
    p_photo3d_run.add_argument(
        "--artifact-index",
        default=None,
        help=(
            "ARTIFACT_INDEX.json path (default: "
            "cad/<subsystem>/.cad-spec-gen/ARTIFACT_INDEX.json). "
            "This is the only artifact discovery source for active_run_id."
        ),
    )
    p_photo3d_run.add_argument(
        "--max-rounds",
        type=int,
        default=3,
        help="Maximum gate/action/autopilot rounds before stopping for review",
    )
    p_photo3d_run.add_argument(
        "--confirm-actions",
        action="store_true",
        help="Explicitly execute allowlisted low-risk recovery actions",
    )
    p_photo3d_run.add_argument(
        "--output",
        default=None,
        help="PHOTO3D_RUN.json output path (default: current run directory)",
    )

    # photo3d-handoff：普通用户/大模型确认后执行当前下一步交接动作
    p_photo3d_handoff = sub.add_parser(
        "photo3d-handoff",
        help="Preview or confirm the current Photo3D next-action handoff",
        description=(
            "Photo3D handoff：读取当前 active_run_id 的 PHOTO3D_RUN.json 或 "
            "PHOTO3D_AUTOPILOT.json，写 PHOTO3D_HANDOFF.json。默认只预览，"
            "只有传 --confirm 才会执行识别到的当前下一步动作。该命令是 "
            "photo3d-run 后给普通用户和大模型使用的确认交接层。"
        ),
        epilog=(
            "Typical preview: python cad_pipeline.py photo3d-handoff --subsystem <name>\n"
            "Typical execute: python cad_pipeline.py photo3d-handoff --subsystem <name> --confirm\n"
            "Recognized handoffs are accept-baseline, enhance, enhance-check, "
            "and photo3d-run --confirm-actions. For enhance, --provider-preset "
            "selects a known provider preset such as default, engineering, gemini, "
            "fal, fal_comfy, or comfyui. The command does not scan directories, "
            "never trusts arbitrary argv from JSON reports, and rebuilds argv from "
            "ARTIFACT_INDEX.json active_run_id plus the current run/render paths "
            "and allowlisted provider preset. "
            "After a confirmed enhance succeeds, it runs enhance-check for the same "
            "active run, records that result in followup_action, then reruns "
            "photo3d-run once without confirmation so post_handoff_photo3d_run "
            "surfaces accepted/preview/blocked delivery state. Status "
            "executed_with_followup means enhancement execution and the same-run "
            "acceptance follow-up completed; a blocked enhance-check report is "
            "still surfaced through PHOTO3D_RUN.json instead of being hidden as a "
            "raw subprocess failure. "
            "All output stays inside cad/<name>/.cad-spec-gen/runs/<run_id>/."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_photo3d_handoff.add_argument("--subsystem", "-s", required=True)
    p_photo3d_handoff.add_argument(
        "--artifact-index",
        default=None,
        help=(
            "ARTIFACT_INDEX.json path (default: "
            "cad/<subsystem>/.cad-spec-gen/ARTIFACT_INDEX.json). "
            "This is the only active_run_id source."
        ),
    )
    p_photo3d_handoff.add_argument(
        "--source",
        choices=["run", "autopilot"],
        default=None,
        help="Use PHOTO3D_RUN.json or PHOTO3D_AUTOPILOT.json; default prefers run",
    )
    p_photo3d_handoff.add_argument(
        "--confirm",
        action="store_true",
        help="Actually execute the recognized current next action; omitted means preview only",
    )
    p_photo3d_handoff.add_argument(
        "--provider-preset",
        default=None,
        help=(
            "Enhancement provider preset for run_enhancement: default, engineering, "
            "gemini, fal, fal_comfy, comfyui. Unknown presets are blocked."
        ),
    )
    p_photo3d_handoff.add_argument(
        "--output",
        default=None,
        help="PHOTO3D_HANDOFF.json output path (default: current run directory)",
    )

    # photo3d-recover：只由 action runner 调用的 run-aware 低风险恢复 wrapper
    p_photo3d_recover = sub.add_parser(
        "photo3d-recover",
        help="Run one run-aware Photo3D low-risk recovery action",
        description=(
            "Photo3D recover wrapper：执行 product-graph / build / render 恢复动作，"
            "但必须显式绑定 --run-id、--artifact-index 和当前 active run。该命令"
            "不扫描目录猜最新产物、不新建 run、不切换 active_run_id；恢复产物写回"
            "当前 run 的固定路径，并更新 ARTIFACT_INDEX.json。"
        ),
        epilog=(
            "Typical internal use: python cad_pipeline.py photo3d-recover "
            "--subsystem <name> --run-id <run_id> --artifact-index "
            "cad/<name>/.cad-spec-gen/ARTIFACT_INDEX.json --action render\n"
            "Ordinary users normally run photo3d-action --confirm instead; "
            "ACTION_PLAN.json must contain this run-aware wrapper shape."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_photo3d_recover.add_argument("--subsystem", "-s", required=True)
    p_photo3d_recover.add_argument("--run-id", required=True)
    p_photo3d_recover.add_argument(
        "--artifact-index",
        required=True,
        help="ARTIFACT_INDEX.json path for the current active run",
    )
    p_photo3d_recover.add_argument(
        "--action",
        required=True,
        choices=["product-graph", "build", "render"],
        help="Low-risk recovery action to run inside the current run scope",
    )

    # accept-baseline：显式接受通过门禁的 Photo3D run
    p_accept_baseline = sub.add_parser(
        "accept-baseline",
        help="Accept a pass/warning Photo3D run as the baseline for drift checks",
        description=(
            "接受已通过 Photo3D 门禁的 run 作为后续 baseline。该命令只更新 "
            "ARTIFACT_INDEX.json，不切换 active_run_id，也不扫描目录猜最新产物。"
        ),
        epilog=(
            "Typical: python cad_pipeline.py accept-baseline --subsystem <name>\n"
            "A run can be accepted only when its PHOTO3D_REPORT.json status is pass "
            "or warning. The accepted baseline assembly signature is then reused by "
            "photo3d when --change-scope is provided and --baseline-signature is not."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_accept_baseline.add_argument("--subsystem", "-s", required=True)
    p_accept_baseline.add_argument(
        "--artifact-index",
        default=None,
        help=(
            "ARTIFACT_INDEX.json path (default: "
            "cad/<subsystem>/.cad-spec-gen/ARTIFACT_INDEX.json)"
        ),
    )
    p_accept_baseline.add_argument(
        "--run-id",
        default=None,
        help="Run id to accept (default: active_run_id in ARTIFACT_INDEX.json)",
    )
    p_accept_baseline.add_argument(
        "--report",
        default=None,
        help="PHOTO3D_REPORT.json path (default: run artifact or run directory report)",
    )

    # sw-export-plan：只读生成 SW Toolbox 导出候选计划
    p_sw_export_plan = sub.add_parser(
        "sw-export-plan",
        help="只读生成 SolidWorks Toolbox STEP 导出候选计划",
    )
    p_sw_export_plan.add_argument("--subsystem", "-s", required=True)
    p_sw_export_plan.add_argument(
        "--spec",
        default="",
        help="CAD_SPEC.md 路径；默认 cad/<subsystem>/CAD_SPEC.md",
    )
    p_sw_export_plan.add_argument("--json", action="store_true", help="输出机读 JSON")

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
        "enhance-check": cmd_enhance_check,
        "annotate": cmd_annotate,
        "full": cmd_full,
        "init": cmd_init,
        "status": cmd_status,
        "env-check": cmd_env_check,
        "sw-warmup": cmd_sw_warmup,
        "sw-toolbox-e2e": cmd_sw_toolbox_e2e,
        "sw-inspect": cmd_sw_inspect,
        "model-audit": cmd_model_audit,
        "model-import": cmd_model_import,
        "product-graph": cmd_product_graph,
        "project-guide": cmd_project_guide,
        "photo3d": cmd_photo3d,
        "photo3d-autopilot": cmd_photo3d_autopilot,
        "photo3d-action": cmd_photo3d_action,
        "photo3d-run": cmd_photo3d_run,
        "photo3d-handoff": cmd_photo3d_handoff,
        "photo3d-recover": cmd_photo3d_recover,
        "accept-baseline": cmd_accept_baseline,
        "sw-export-plan": cmd_sw_export_plan,
    }

    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
