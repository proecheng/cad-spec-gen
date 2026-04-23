#!/usr/bin/env python3
"""
Code Generator: CAD_SPEC.md §5 BOM → Part Module Scaffolds

Generates a CadQuery .py file for each custom-made leaf part in the BOM.
Only creates NEW files — never overwrites existing ones.

Usage:
    python codegen/gen_parts.py cad/end_effector/CAD_SPEC.md
    python codegen/gen_parts.py cad/end_effector/CAD_SPEC.md --output-dir cad/end_effector
"""

import argparse
import logging as _log
import os
import re
import sys
from pathlib import Path

import jinja2

_PROJECT_ROOT = str(Path(__file__).parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Spec 1: make the cad_spec_gen package importable in repo-checkout mode.
# hatch_build.py publishes it as an installed package for wheel users;
# repo-checkout users need src/ on sys.path BEFORE the repo root so the
# package at src/cad_spec_gen/ wins over the top-level cad_spec_gen.py script.
#
# When cad-spec-gen is pip-installed in editable mode, pip writes a .pth
# file that puts src/ into sys.path automatically — but AFTER site-packages
# which comes AFTER our _PROJECT_ROOT insertion above. That means the
# top-level cad_spec_gen.py script would shadow the src/cad_spec_gen/
# package. To fix this, we force _SRC to position 0 by removing any
# existing occurrence first (a simple `if _SRC not in sys.path: insert`
# check would skip the reinsertion when .pth already put it deeper in
# the list).
_SRC = str(Path(__file__).parent.parent / "src")
while _SRC in sys.path:
    sys.path.remove(_SRC)
sys.path.insert(0, _SRC)

try:
    from cad_spec_gen.parts_routing import (
        GeomInfo,
        route,
        discover_templates,
        locate_builtin_templates_dir,
    )

    _PARTS_ROUTING_AVAILABLE = True
except ImportError as _exc:
    _PARTS_ROUTING_AVAILABLE = False
    import logging as _log

    _log.getLogger(__name__).debug("parts_routing unavailable: %s", _exc)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from codegen.gen_build import parse_bom_tree
from cad_spec_defaults import strip_part_prefix


def _safe_module_name(part_no: str, name_cn: str) -> str:
    """Generate a clean Python module/function name from part number."""
    # 通用前缀剥离: GIS-EE-001-01 → EE-001-01 → ee_001_01
    suffix = strip_part_prefix(part_no).lower().replace("-", "_")
    # Python identifiers cannot start with a digit; prefix with 'p' if needed
    if suffix and suffix[0].isdigit():
        suffix = "p" + suffix
    return suffix


def _guess_geometry(name_cn: str, material: str, envelope: tuple = None) -> dict:
    """Infer approximate geometry type and dimensions for a custom part.

    Priority 0: §6.4 envelope dimensions (most accurate, multi-source).
    Priority 1: Parse explicit dimensions from BOM material column
                (e.g. "6063铝合金 140×100×55mm" → box, "Φ38×280mm" → cylinder).
    Priority 2: Keyword-based heuristics from part name (generic types only).

    Returns dict with "type" key and type-specific dimension keys.
    Also always includes "envelope_w/d/h" for docstring use.
    """
    # ── Priority 0: §6.4 envelope (from parse_envelopes) ──
    if envelope:
        w, d, h = envelope
        is_round = abs(w - d) < 0.1  # w ≈ d → cylindrical
        if is_round:
            if "法兰" in name_cn and "悬臂" in name_cn:
                # Arms extend OUTWARD from the disc edge by arm_l. Each arm
                # ends in a 40×40mm mounting platform whose center sits at
                # the workstation mount radius R=65mm (per §4.1.1 and the
                # assembly's R=65mm constraint in §6.2). With disc Φ90 →
                # disc_r=45, arm_l = (R - disc_r) + plat_size/2 = 20 + 20
                # = 40mm. Platform extends ±20mm in Y (40×40 cross section)
                # while the arm itself is 12mm × 8mm (W × thickness).
                arm_l = max(20.0, round(w * 0.45, 1))
                arm_w = 12.0  # arm cross-section width (Y direction)
                arm_t = 8.0  # arm cross-section thickness (Z direction)
                arm_count = 4  # default
                if "十字" in name_cn or "四" in name_cn:
                    arm_count = 4
                elif "三叉" in name_cn or "三" in name_cn:
                    arm_count = 3
                elif "六" in name_cn:
                    arm_count = 6
                return {
                    "type": "disc_arms",
                    "d": w,
                    "arm_l": arm_l,
                    "arm_w": arm_w,
                    "arm_t": arm_t,
                    "t": h,
                    "arm_count": arm_count,
                    "envelope_w": w + arm_l * 2,
                    "envelope_d": d + arm_l * 2,
                    "envelope_h": h,
                }
            if "环" in name_cn or "绝缘" in name_cn:
                return {
                    "type": "ring",
                    "od": w,
                    "id": round(w * 0.75, 1),
                    "h": h,
                    "envelope_w": w,
                    "envelope_d": d,
                    "envelope_h": h,
                }
            return {
                "type": "cylinder",
                "d": w,
                "h": h,
                "envelope_w": w,
                "envelope_d": d,
                "envelope_h": h,
            }
        else:
            if "支架" in name_cn and ("L" in name_cn or "抱箍" in name_cn):
                return {
                    "type": "l_bracket",
                    "w": w,
                    "d": d,
                    "h": h,
                    "t": 3.0,
                    "envelope_w": w,
                    "envelope_d": d,
                    "envelope_h": h,
                }
            return {
                "type": "box",
                "w": w,
                "d": d,
                "h": h,
                "envelope_w": w,
                "envelope_d": d,
                "envelope_h": h,
            }

    # ── Priority 1: Parse explicit dimensions from material text ──
    # Cylinder: Φ38×280mm or φ38x280mm
    m_cyl = re.search(r"[Φφ](\d+(?:\.\d+)?)\s*[×xX]\s*(\d+(?:\.\d+)?)\s*mm", material)
    if m_cyl:
        d, h = float(m_cyl.group(1)), float(m_cyl.group(2))
        return {
            "type": "cylinder",
            "d": d,
            "h": h,
            "envelope_w": d,
            "envelope_d": d,
            "envelope_h": h,
        }

    # Box: 140×100×55mm (three dimensions with ×)
    m_box = re.search(
        r"(\d+(?:\.\d+)?)\s*[×xX]\s*(\d+(?:\.\d+)?)\s*[×xX]\s*(\d+(?:\.\d+)?)\s*mm",
        material,
    )
    if m_box:
        w, d, h = float(m_box.group(1)), float(m_box.group(2)), float(m_box.group(3))
        return {
            "type": "box",
            "w": w,
            "d": d,
            "h": h,
            "envelope_w": w,
            "envelope_d": d,
            "envelope_h": h,
        }

    # Diameter only: Φ90mm (no height) → flat disc
    m_dia = re.search(r"[Φφ](\d+(?:\.\d+)?)\s*mm", material)
    if m_dia:
        d = float(m_dia.group(1))
        h = max(5.0, round(d * 0.25, 1))
        return {
            "type": "cylinder",
            "d": d,
            "h": h,
            "envelope_w": d,
            "envelope_d": d,
            "envelope_h": h,
        }

    # ── Priority 2: Keyword heuristics (generic types) ──
    if "壳体" in name_cn or "筒" in name_cn or "缸" in name_cn:
        return {
            "type": "cylinder",
            "d": 50.0,
            "h": 60.0,
            "envelope_w": 50.0,
            "envelope_d": 50.0,
            "envelope_h": 60.0,
        }

    if "法兰" in name_cn and "悬臂" in name_cn:
        arm_count = 4  # default
        if "十字" in name_cn or "四" in name_cn:
            arm_count = 4
        elif "三叉" in name_cn or "三" in name_cn:
            arm_count = 3
        elif "六" in name_cn:
            arm_count = 6
        return {
            "type": "disc_arms",
            "d": 80.0,
            "arm_l": 40.0,
            "arm_w": 12.0,
            "arm_t": 8.0,
            "t": 20.0,
            "arm_count": arm_count,
            "envelope_w": 160.0,
            "envelope_d": 160.0,
            "envelope_h": 20.0,
        }

    if "法兰" in name_cn or "盘" in name_cn:
        return {
            "type": "cylinder",
            "d": 80.0,
            "h": 20.0,
            "envelope_w": 80.0,
            "envelope_d": 80.0,
            "envelope_h": 20.0,
        }

    if "环" in name_cn or "绝缘段" in name_cn:
        d = 80.0
        return {
            "type": "ring",
            "od": d,
            "id": round(d * 0.75, 1),
            "h": 5.0,
            "envelope_w": d,
            "envelope_d": d,
            "envelope_h": 5.0,
        }

    if "支架" in name_cn and ("L" in name_cn or "抱箍" in name_cn):
        return {
            "type": "l_bracket",
            "w": 50.0,
            "d": 40.0,
            "h": 25.0,
            "t": 3.0,
            "envelope_w": 50.0,
            "envelope_d": 40.0,
            "envelope_h": 25.0,
        }

    if "支架" in name_cn:
        return {
            "type": "box",
            "w": 50.0,
            "d": 40.0,
            "h": 25.0,
            "envelope_w": 50.0,
            "envelope_d": 40.0,
            "envelope_h": 25.0,
        }

    if "适配" in name_cn:
        return {
            "type": "cylinder",
            "d": 60.0,
            "h": 10.0,
            "envelope_w": 60.0,
            "envelope_d": 60.0,
            "envelope_h": 10.0,
        }

    if "板" in name_cn:
        return {
            "type": "box",
            "w": 60.0,
            "d": 40.0,
            "h": 10.0,
            "envelope_w": 60.0,
            "envelope_d": 40.0,
            "envelope_h": 10.0,
        }

    # Default fallback
    return {
        "type": "box",
        "w": 40.0,
        "d": 40.0,
        "h": 20.0,
        "envelope_w": 40.0,
        "envelope_d": 40.0,
        "envelope_h": 20.0,
    }


def _parse_spec_title(spec_path: str) -> tuple:
    """Extract project_name and subsystem_name from CAD_SPEC.md title line.

    Returns (project_name, subsystem_name).
    """
    text = Path(spec_path).read_text(encoding="utf-8")
    m = re.search(r"# CAD Spec\s*[—\-]\s*(.+?)(?:\s*\((.+?)\)|$)", text.split("\n")[0])
    if m:
        subsystem_name = m.group(1).strip()
        project_prefix = m.group(2).strip() if m.group(2) else ""
        return project_prefix, subsystem_name
    return "", ""


# A2-0: 语义前缀→零件类别关键词映射表
_TOL_PREFIX_CATEGORY: dict[str, str] = {
    "FLANGE": "法兰",
    "HOUSING": "壳体",
    "SPRING": "弹簧",
    "ARM": "悬臂",
    "BRACKET": "支架",
    "SLEEVE": "套筒",
    "CLAMP": "夹",
    "PLATE": "板",
    "COVER": "盖",
}


def _tol_belongs_to_part(tol_name: str, part_name_cn: str) -> bool:
    """判断 dim_tolerance 条目是否归属当前零件。

    命中前缀 → 检查零件 name_cn 是否含对应关键词。
    未命中任何前缀 → 通用条目，保留给所有零件。

    约定：tolerance 名称前缀应属于单一类别（不应出现如 SLEEVE_CLAMP_OD 这类
    跨类别复合前缀）。出现时，首个命中的前缀类别生效（dict 插入顺序）。
    """
    for prefix, keyword in _TOL_PREFIX_CATEGORY.items():
        if tol_name.upper().startswith(prefix):
            return keyword in part_name_cn
    return True


def _dim_filter_enabled() -> bool:
    return os.getenv("CAD_SPEC_GEN_DIM_FILTER", "on").lower() != "off"


def _parse_annotation_meta(spec_path: str, part_name: str) -> dict:
    """Extract §2 annotation metadata for a specific part.

    Returns dict with dim_tolerances, gdt, surfaces filtered for this part.
    """
    from cad_spec_extractors import extract_tolerances

    text = Path(spec_path).read_text(encoding="utf-8")
    tol_data = extract_tolerances(text.splitlines())

    # Filter tolerances — 按语义前缀过滤，仅保留归属当前零件的条目
    dim_tols = tol_data.get("dim_tols", [])
    if _dim_filter_enabled() and part_name:
        dim_tols = [
            t for t in dim_tols if _tol_belongs_to_part(t.get("name", ""), part_name)
        ]
    # Filter GD&T — keep entries matching this part name
    gdt = [
        g
        for g in tol_data.get("gdt", [])
        if not g.get("parts") or part_name in g["parts"]
    ]
    # Filter surfaces — keep entries matching this part name
    surfaces = [
        s
        for s in tol_data.get("surfaces", [])
        if not s.get("part") or part_name in s["part"]
    ]

    return {
        "dim_tolerances": dim_tols,
        "gdt": gdt,
        "surfaces": surfaces,
    }


def _apply_template_decision(
    geom: dict,
    tpl_type: str | None,
    part_meta: dict,
    envelope: tuple | None,
    part_no: str = "",
    output_dir: str = "",
) -> dict:
    """SW API 优先 → CadQuery 回退 → 主尺寸缺失时退回 envelope primitive。

    SW 路径：生成 {output_dir}/sw_parts/{part_no}.step，返回 geom["step_path"]。
    CadQuery 路径：工厂函数返回代码字符串，注入 geom["template_code"]。
    任意路径失败 → 返回原始 geom（不修改 type）。
    """
    if tpl_type is None:
        return geom

    import sys as _sys_inner

    # ── SW COM API 优先路径 ───────────────────────────────────────────────
    if _sys_inner.platform == "win32" and output_dir and part_no:
        try:
            from adapters.parts.sw_parametric_adapter import SwParametricAdapter
            _sw = SwParametricAdapter()
            ok, _ = _sw.is_available()
            if ok:
                from pathlib import Path as _Path
                sw_dir = _Path(output_dir) / "sw_parts"
                sw_dir.mkdir(parents=True, exist_ok=True)
                step_path = _sw.build_part(
                    tpl_type, _extract_params(tpl_type, part_meta, envelope),
                    sw_dir, part_no
                )
                if step_path:
                    updated = dict(geom)
                    updated["type"] = tpl_type
                    updated["kind"] = "step_import"
                    updated["step_path"] = f"sw_parts/{part_no}.step"
                    return updated
        except Exception as _exc:
            _log.getLogger(__name__).debug("SW 参数化建模失败，回退 CadQuery: %s", _exc)

    # ── CadQuery 工厂函数回退路径 ─────────────────────────────────────────
    dim_map: dict[str, float] = {}
    for t in part_meta.get("dim_tolerances", []):
        try:
            dim_map[t["name"]] = float(t["nominal"])
        except (KeyError, ValueError):
            pass

    env_w, env_d, env_h = envelope if envelope else (0.0, 0.0, 0.0)

    # Ensure codegen/ is importable for part_templates
    _codegen_dir = os.path.join(_PROJECT_ROOT, "codegen")
    if _codegen_dir not in sys.path:
        sys.path.insert(0, _codegen_dir)

    code: str | None = None

    if tpl_type == "flange":
        from part_templates.flange import make_flange
        code = make_flange(
            od=dim_map.get("FLANGE_BODY_OD") or dim_map.get("FLANGE_DIA") or (max(env_w, env_d) or None),
            id=dim_map.get("FLANGE_BODY_ID") or dim_map.get("FLANGE_ID") or None,
            thickness=(dim_map.get("FLANGE_TOTAL_THICK") or dim_map.get("FLANGE_THICK")
                       or dim_map.get("FLANGE_H") or env_h or None),
            bolt_pcd=dim_map.get("FLANGE_BOLT_PCD") or None,
            bolt_count=int(dim_map.get("FLANGE_BOLT_N", 6)),
            boss_h=dim_map.get("FLANGE_BOSS_H", 0.0),
        )
    elif tpl_type == "housing":
        from part_templates.housing import make_housing
        code = make_housing(
            width=dim_map.get("HOUSING_W") or env_w or None,
            depth=dim_map.get("HOUSING_D") or env_d or None,
            height=dim_map.get("HOUSING_H") or env_h or None,
            wall_t=dim_map.get("HOUSING_WALL_T") or (min(env_w, env_d) * 0.12 if env_w and env_d else None),
        )
    elif tpl_type == "bracket":
        from part_templates.bracket import make_bracket
        code = make_bracket(
            width=dim_map.get("BRACKET_W") or env_w or None,
            height=dim_map.get("BRACKET_H") or env_h or None,
            thickness=dim_map.get("BRACKET_T") or env_d or None,
        )
    elif tpl_type == "spring_mechanism":
        from part_templates.spring_mechanism import make_spring_mechanism
        code = make_spring_mechanism(
            od=dim_map.get("SPRING_OD") or max(env_w, env_d) or None,
            id=dim_map.get("SPRING_ID") or None,
            free_length=dim_map.get("SPRING_L") or env_h or None,
            wire_d=dim_map.get("SPRING_WIRE_D") or None,
            coil_n=int(dim_map.get("SPRING_COIL_N", 8)),
        )
    elif tpl_type == "sleeve":
        from part_templates.sleeve import make_sleeve
        code = make_sleeve(
            od=dim_map.get("SLEEVE_OD") or max(env_w, env_d) or None,
            id=dim_map.get("SLEEVE_ID") or None,
            length=dim_map.get("SLEEVE_L") or env_h or None,
        )
    elif tpl_type == "plate":
        from part_templates.plate import make_plate
        code = make_plate(
            width=dim_map.get("PLATE_W") or env_w or None,
            depth=dim_map.get("PLATE_D") or env_d or None,
            thickness=dim_map.get("PLATE_T") or env_h or None,
        )
    elif tpl_type == "arm":
        from part_templates.arm import make_arm
        dims = sorted([env_w, env_d, env_h], reverse=True)
        code = make_arm(
            length=dim_map.get("ARM_L") or dim_map.get("ARM_L_2") or (dims[0] if dims else None),
            width=dim_map.get("ARM_W") or dim_map.get("ARM_SEC_W") or (dims[1] if len(dims) > 1 else None),
            thickness=dim_map.get("ARM_T") or dim_map.get("ARM_SEC_THICK") or (dims[2] if len(dims) > 2 else None),
            end_hole_d=dim_map.get("ARM_END_HOLE_D"),
        )
    elif tpl_type == "cover":
        from part_templates.cover import make_cover
        code = make_cover(
            od=dim_map.get("COVER_OD") or max(env_w, env_d) or None,
            thickness=dim_map.get("COVER_T") or env_h or None,
            id=dim_map.get("COVER_ID") or None,
        )

    if code is None:
        print(f"  [template] {tpl_type}: 必填主尺寸缺失，退回 envelope primitive")
        return geom

    updated = dict(geom)
    updated["type"] = tpl_type
    updated["template_code"] = code
    return updated


def _extract_params(tpl_type: str, part_meta: dict, envelope: tuple | None) -> dict:
    """从 part_meta + envelope 提取各模板所需参数 dict（供 SW adapter 使用）。"""
    dim_map: dict[str, float] = {}
    for t in part_meta.get("dim_tolerances", []):
        try:
            dim_map[t["name"]] = float(t["nominal"])
        except (KeyError, ValueError):
            pass
    env_w, env_d, env_h = envelope if envelope else (0.0, 0.0, 0.0)
    if tpl_type == "flange":
        return {
            "od": dim_map.get("FLANGE_BODY_OD") or max(env_w, env_d),
            "id": dim_map.get("FLANGE_BODY_ID") or None,
            "thickness": dim_map.get("FLANGE_TOTAL_THICK") or env_h,
            "bolt_pcd": dim_map.get("FLANGE_BOLT_PCD") or None,
            "bolt_count": int(dim_map.get("FLANGE_BOLT_N", 6)),
            "boss_h": dim_map.get("FLANGE_BOSS_H", 0.0),
        }
    if tpl_type == "housing":
        return {
            "width": dim_map.get("HOUSING_W") or env_w,
            "depth": dim_map.get("HOUSING_D") or env_d,
            "height": dim_map.get("HOUSING_H") or env_h,
            "wall_t": dim_map.get("HOUSING_WALL_T") or (min(env_w, env_d) * 0.12 if env_w and env_d else 5.0),
        }
    if tpl_type == "bracket":
        return {
            "width": dim_map.get("BRACKET_W") or env_w,
            "height": dim_map.get("BRACKET_H") or env_h,
            "thickness": dim_map.get("BRACKET_T") or env_d,
        }
    if tpl_type == "spring_mechanism":
        return {
            "od": dim_map.get("SPRING_OD") or max(env_w, env_d),
            "id": dim_map.get("SPRING_ID") or None,
            "free_length": dim_map.get("SPRING_L") or env_h,
            "wire_d": dim_map.get("SPRING_WIRE_D") or None,
            "coil_n": int(dim_map.get("SPRING_COIL_N", 8)),
        }
    if tpl_type == "sleeve":
        return {
            "od": dim_map.get("SLEEVE_OD") or max(env_w, env_d),
            "id": dim_map.get("SLEEVE_ID") or None,
            "length": dim_map.get("SLEEVE_L") or env_h,
        }
    if tpl_type == "plate":
        return {
            "width": dim_map.get("PLATE_W") or env_w,
            "depth": dim_map.get("PLATE_D") or env_d,
            "thickness": dim_map.get("PLATE_T") or env_h,
            "n_hole": int(dim_map.get("PLATE_HOLE_N", 4)),
        }
    dims = sorted([env_w, env_d, env_h], reverse=True)
    if tpl_type == "arm":
        return {
            "length": dim_map.get("ARM_L") or dim_map.get("ARM_L_2") or (dims[0] if dims else 100.0),
            "width": dim_map.get("ARM_W") or (dims[1] if len(dims) > 1 else 20.0),
            "thickness": dim_map.get("ARM_T") or (dims[2] if len(dims) > 2 else 10.0),
            "end_hole_d": dim_map.get("ARM_END_HOLE_D", 8.0),
        }
    if tpl_type == "cover":
        return {
            "od": dim_map.get("COVER_OD") or max(env_w, env_d),
            "thickness": dim_map.get("COVER_T") or env_h,
            "id": dim_map.get("COVER_ID") or None,
        }
    return {}


def generate_part_files(
    spec_path: str, output_dir: str, mode: str = "scaffold"
) -> list:
    """Generate part module scaffolds for all custom-made leaf parts.

    Args:
        mode: "scaffold" (skip existing), "force" (overwrite existing)

    Returns list of generated file paths.
    """
    parts = parse_bom_tree(spec_path)
    generated = []
    skipped = []

    # A2-3: 加载用户命名覆盖（template_mapping.json 与 spec 同级目录）
    _codegen_dir = os.path.join(_PROJECT_ROOT, "codegen")
    if _codegen_dir not in sys.path:
        sys.path.insert(0, _codegen_dir)
    from template_mapping_loader import load_template_mapping, match_template as _match_template
    _mapping_path = os.path.join(os.path.dirname(spec_path), "template_mapping.json")
    _user_mapping = load_template_mapping(_mapping_path)

    # Parse project/subsystem name from spec title
    project_name, subsystem_name = _parse_spec_title(spec_path)
    if not subsystem_name:
        print(
            f"  WARNING: Could not extract subsystem name from spec title in {os.path.basename(spec_path)} "
            f"— expected '# CAD Spec — <name>' on first line"
        )

    # Parse §2 annotation metadata (once for all parts)
    try:
        full_meta = _parse_annotation_meta(spec_path, "")
    except Exception:
        full_meta = {"dim_tolerances": [], "gdt": [], "surfaces": []}

    template_dir = os.path.join(_PROJECT_ROOT, "templates")
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(template_dir),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("part_module.py.j2")

    # Parse §6.4 envelope dimensions (most accurate source)
    from codegen.gen_assembly import parse_envelopes

    envelopes_raw = parse_envelopes(spec_path)
    # Legacy callers expect bare tuples: unwrap the new dict shape.
    envelopes = {
        pno: (e["dims"] if isinstance(e, dict) else e)
        for pno, e in envelopes_raw.items()
    }

    for p in parts:
        # Only generate for custom-made leaf parts
        if p["is_assembly"]:
            continue
        if "自制" not in p.get("make_buy", ""):
            continue

        mod_name = _safe_module_name(p["part_no"], p["name_cn"])
        func_name = mod_name
        out_file = os.path.join(output_dir, f"{mod_name}.py")

        # Skip existing unless force mode
        if os.path.exists(out_file) and mode != "force":
            skipped.append(out_file)
            continue

        envelope = envelopes.get(p["part_no"])
        geom = _guess_geometry(p["name_cn"], p["material"], envelope=envelope)

        # Spec 1: log routing preview (dormant integration; emission unchanged).
        if _PARTS_ROUTING_AVAILABLE:
            try:
                _geom = GeomInfo(
                    type=geom.get("type", "unknown"),
                    envelope_w=float(geom.get("envelope_w") or 0),
                    envelope_d=float(geom.get("envelope_d") or 0),
                    envelope_h=float(geom.get("envelope_h") or 0),
                    extras={
                        k: v
                        for k, v in geom.items()
                        if k not in {"type", "envelope_w", "envelope_d", "envelope_h"}
                    },
                )
                _tier1 = locate_builtin_templates_dir()
                _search = [_tier1] if _tier1 else []
                _templates = discover_templates(_search)
                _decision = route(p["name_cn"] or "", _geom, _templates)
                _tpl = _decision.template.name if _decision.template else "fallback"
                # Spec 1: print to stdout so the preview is observable during
                # standalone gen_parts runs. gen_parts.py does not configure
                # logging.basicConfig, so log.info() is silently dropped; use
                # print() to match the rest of gen_parts.py's status output style.
                print(
                    f"  [routing preview] {p['name_cn']} -> "
                    f"{_decision.outcome} ({_tpl})"
                )
            except Exception as _err:
                # Don't crash gen_parts on routing preview failure — diagnostic only.
                print(f"  [routing preview] {p['name_cn']} -> failed: {_err}")

        # Derive material_type
        from cad_spec_defaults import classify_material_type, SURFACE_RA

        mat_type = classify_material_type(p["material"])
        if mat_type is None:
            print(
                f"  WARNING: Cannot classify material '{p['material']}' for {p['part_no']}, "
                f"defaulting to 'al'"
            )
            mat_type = "al"

        # Per-part annotation meta
        part_meta = _parse_annotation_meta(spec_path, p["name_cn"])

        # A2-3: 半参数模板激活
        _tpl_type = _match_template(p["name_cn"], _user_mapping)
        if _tpl_type:
            geom = _apply_template_decision(
                geom, _tpl_type, part_meta, envelope,
                part_no=p.get("part_no", ""),
                output_dir=str(output_dir),
            )

        # Default Ra from material type
        default_ra = SURFACE_RA.get(mat_type, SURFACE_RA.get("default", 3.2))

        # Flatten geometry dict for template: geom_type, geom_d, geom_h, etc.
        geom_vars = {f"geom_{k}": v for k, v in geom.items() if k != "type"}
        geom_vars["geom_type"] = geom["type"]

        content = template.render(
            part_name_cn=p["name_cn"],
            part_no=p["part_no"],
            source_ref="CAD_SPEC.md §5 BOM",
            material=p["material"],
            func_name=func_name,
            param_imports=[],  # Empty — user adds specific params
            envelope_w=geom["envelope_w"],
            envelope_d=geom["envelope_d"],
            envelope_h=geom["envelope_h"],
            weight="?",
            has_mounting_holes=False,
            has_dxf=True,
            # Geometry type dispatch
            **geom_vars,
            # Annotation metadata — from CAD_SPEC.md §2 + BOM material
            material_type=mat_type,
            project_name=project_name,
            subsystem_name=subsystem_name,
            dim_tolerances=part_meta["dim_tolerances"],
            gdt_entries=part_meta["gdt"],
            surface_ra=part_meta["surfaces"],
            default_ra=default_ra,
            step_path=geom.get("step_path"),
            template_code=geom.get("template_code"),
        )

        Path(out_file).write_text(content, encoding="utf-8")
        generated.append(out_file)

    return generated, skipped


def scan_todos(files: list) -> dict:
    """Scan generated files for unfilled TODO markers.

    Returns dict of {filepath: [line_numbers]} for files with TODOs.
    """
    result = {}
    for f in files:
        todos = []
        try:
            lines = Path(f).read_text(encoding="utf-8").splitlines()
            for i, line in enumerate(lines, 1):
                if "TODO:" in line:
                    todos.append((i, line.strip()))
        except OSError:
            pass
        if todos:
            result[f] = todos
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Generate part module scaffolds from CAD_SPEC.md §5 BOM"
    )
    parser.add_argument("spec", help="Path to CAD_SPEC.md")
    parser.add_argument(
        "--output-dir",
        "-o",
        default=None,
        help="Output directory (default: same dir as spec)",
    )
    parser.add_argument(
        "--mode",
        choices=["scaffold", "force"],
        default="scaffold",
        help="scaffold=skip existing, force=overwrite",
    )
    args = parser.parse_args()

    spec_path = os.path.abspath(args.spec)
    output_dir = args.output_dir or os.path.dirname(spec_path)
    os.makedirs(output_dir, exist_ok=True)

    generated, skipped = generate_part_files(spec_path, output_dir, mode=args.mode)
    print(
        f"[gen_parts] Generated {len(generated)} part scaffold(s), "
        f"skipped {len(skipped)} existing"
    )
    for f in generated:
        print(f"  + {os.path.basename(f)}")
    if skipped:
        print(f"  (skipped: {', '.join(os.path.basename(f) for f in skipped)})")

    # ── TODO scan: warn on unfilled coordinate system blocks ─────────────────
    todos = scan_todos(generated)
    if todos:
        print(f"\n[gen_parts] WARNING: {len(todos)} file(s) have unfilled TODO markers")
        print(
            "  Fill these before running 'cad_pipeline.py build' or orientation_check will fail:"
        )
        for fpath, items in todos.items():
            print(f"  {os.path.basename(fpath)}:")
            for lineno, text in items:
                print(f"    L{lineno}: {text}")
        sys.exit(2)  # exit code 2 = scaffold generated but TODOs remain
    else:
        print("[gen_parts] All coordinate system blocks filled. Ready for build.")


if __name__ == "__main__":
    main()
