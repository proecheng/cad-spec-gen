from __future__ import annotations

import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bom_parser import classify_part
from codegen.gen_assembly import parse_constraints, parse_envelopes, parse_render_exclusions
from codegen.gen_build import parse_bom_tree
from tools.contract_io import file_sha256, write_json_atomic
from tools.path_policy import (
    assert_within_project,
    build_path_context,
    project_relative,
    strict_subsystem_dir,
)


PARSER_VERSION = "product_graph.v1"

_HEADER_ALIASES = {
    "part_no": ("料号", "零件号", "partno", "part_no", "part no"),
    "name_cn": ("名称", "零件名称", "name", "name_cn"),
    "material": ("材质", "材料", "material"),
    "quantity": ("数量", "qty", "quantity", "数量/套"),
    "make_buy": ("自制/外购", "制造方式", "makebuy", "make_buy", "来源"),
}

_CHINESE_DIGITS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def build_product_graph(
    project_root: str | Path,
    subsystem: str,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    actual_run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    subsystem_dir = strict_subsystem_dir(root, subsystem).resolve()
    assert_within_project(subsystem_dir, root, "subsystem_dir")
    spec_path = subsystem_dir / "CAD_SPEC.md"
    if not spec_path.is_file():
        raise FileNotFoundError(f"CAD_SPEC.md not found: {spec_path}")

    path_context = build_path_context(root, subsystem, run_id=actual_run_id)
    bom_metadata = _parse_bom_table(spec_path)
    normalized_spec = _normalized_bom_spec(spec_path, bom_metadata)
    legacy_parts = _parse_bom_tree_compat(spec_path, normalized_spec)
    legacy_by_part_no = {part.get("part_no", ""): part for part in legacy_parts}

    envelopes = parse_envelopes(str(spec_path))
    exclusions = parse_render_exclusions(str(spec_path))
    excluded_parts = set(exclusions.get("parts", set()))
    excluded_assemblies = set(exclusions.get("assemblies", set()))
    known_part_nos = [row["part_no"] for row in bom_metadata["rows"] if row.get("part_no")]

    warnings: list[dict[str, Any]] = list(bom_metadata["warnings"])
    parts = []
    counts_by_part_no: dict[str, int] = {}
    for row in bom_metadata["rows"]:
        part_no = row["part_no"]
        legacy = legacy_by_part_no.get(part_no, {})
        quantity = row["quantity"]
        counts_by_part_no[part_no] = quantity
        excluded = part_no in excluded_parts or _under_excluded_assembly(part_no, excluded_assemblies)
        render_policy = "excluded" if excluded else "required"
        required = not excluded
        material = row.get("material") or legacy.get("material", "")
        name_cn = row.get("name_cn") or legacy.get("name_cn", "")
        confidence = row["parse_confidence"]
        if confidence < 1.0:
            warnings.append({
                "code": "low_confidence_bom_row",
                "part_no": part_no,
                "source_line": row["source_line"],
                "message": f"Low-confidence BOM row for {part_no}: quantity={row.get('quantity_raw', '')!r}",
            })
        parts.append({
            "part_no": part_no,
            "name_cn": name_cn,
            "make_buy": row.get("make_buy") or legacy.get("make_buy", ""),
            "category": classify_part(name_cn, material) if name_cn or material else "unknown",
            "quantity": quantity,
            "required": required,
            "visual_priority": _visual_priority(part_no, legacy, excluded),
            "render_policy": render_policy,
            "change_policy": _change_policy(required),
            "bbox_expected_mm": _bbox_for_part(envelopes.get(part_no)),
            "parent_part_no": _infer_parent_part_no(part_no, known_part_nos),
            "source_ref": row["source_ref"],
            "source_line": row["source_line"],
            "parse_confidence": confidence,
        })

    instances = []
    for part in parts:
        for occurrence in range(1, part["quantity"] + 1):
            instances.append({
                "instance_id": f"{part['part_no']}#{occurrence:02d}",
                "part_no": part["part_no"],
                "occurrence_index": occurrence,
                "parent_instance_id": (
                    f"{part['parent_part_no']}#01" if part.get("parent_part_no") else None
                ),
                "required": part["required"],
                "visual_priority": part["visual_priority"],
                "render_policy": part["render_policy"],
                "change_policy": part["change_policy"],
            })

    graph = {
        "schema_version": 1,
        "run_id": actual_run_id,
        "subsystem": path_context["resolved_subsystem"],
        "path_context_hash": path_context["path_context_hash"],
        "source_spec": project_relative(spec_path, root),
        "source_hashes": {"CAD_SPEC.md": file_sha256(spec_path)},
        "parser": {
            "version": PARSER_VERSION,
            "bom_header_mapping": bom_metadata["header_mapping"],
            "bom_header_line": bom_metadata.get("header_line"),
            "source_lines_available": True,
            "source_lines_note": "Markdown BOM rows are recorded using 1-based CAD_SPEC.md line numbers.",
            "legacy_parse_bom_tree_used": True,
        },
        "parts": parts,
        "instances": instances,
        "counts_by_part_no": counts_by_part_no,
        "constraints": _normalize_constraints(parse_constraints(str(spec_path)), counts_by_part_no),
        "warnings": warnings,
    }
    return graph


def write_product_graph(
    project_root: str | Path,
    subsystem: str,
    output: str | Path | None = None,
    *,
    run_id: str | None = None,
) -> Path:
    graph = build_product_graph(project_root, subsystem, run_id=run_id)
    root = Path(project_root).resolve()
    if output is not None:
        requested_output = Path(output)
        output_path = requested_output if requested_output.is_absolute() else root / requested_output
        output_path = output_path.resolve()
        assert_within_project(output_path, root, "product graph output")
    else:
        # Standalone CLI default. Orchestrated pipeline runs may pass an
        # explicit run-scoped output path under .cad-spec-gen/runs/<run_id>/.
        output_path = root / "cad" / subsystem / "PRODUCT_GRAPH.json"
    return write_json_atomic(output_path, graph)


def _parse_bom_table(spec_path: Path) -> dict[str, Any]:
    lines = spec_path.read_text(encoding="utf-8").splitlines()
    in_section = False
    header: list[str] | None = None
    header_line: int | None = None
    rows = []
    warnings = []

    for line_no, line in enumerate(lines, start=1):
        if re.match(r"##\s*5\.\s*BOM", line):
            in_section = True
            continue
        if in_section and line.startswith("##") and not re.match(r"##\s*5\.\s*BOM", line):
            break
        if not in_section or not line.startswith("|"):
            continue
        if re.match(r"\|\s*:?-{3,}", line):
            continue

        cells = _split_markdown_row(line)
        if header is None and _looks_like_bom_header(cells):
            header = cells
            header_line = line_no
            continue
        if header is None or not cells:
            continue

        mapping = _build_header_mapping(header)
        part_no = _cell(cells, mapping["part_no"])
        if not part_no:
            continue
        quantity_raw = _cell(cells, mapping.get("quantity", -1)) or "1"
        quantity, confidence, warning = _parse_quantity(quantity_raw)
        row = {
            "part_no": _clean_cell(part_no),
            "name_cn": _clean_cell(_cell(cells, mapping.get("name_cn", -1))),
            "material": _clean_cell(_cell(cells, mapping.get("material", -1))),
            "quantity": quantity,
            "quantity_raw": quantity_raw,
            "make_buy": _clean_cell(_cell(cells, mapping.get("make_buy", -1))),
            "source_line": line_no,
            "source_ref": f"{spec_path.name}:{line_no}",
            "parse_confidence": confidence,
        }
        if warning:
            warnings.append({
                "code": "quantity_parse_fallback",
                "part_no": row["part_no"],
                "source_line": line_no,
                "message": warning,
            })
        rows.append(row)

    if header is None:
        raise ValueError(f"BOM header not found in {spec_path}")
    mapping = _build_header_mapping(header)
    return {
        "header": header,
        "header_line": header_line,
        "header_mapping": {
            field: header[idx] for field, idx in mapping.items() if idx >= 0 and idx < len(header)
        },
        "rows": rows,
        "warnings": warnings,
    }


def _normalized_bom_spec(spec_path: Path, bom_metadata: dict[str, Any]) -> str:
    canonical_header = ["料号", "名称", "材质", "数量", "自制/外购"]
    rows = []
    for row in bom_metadata["rows"]:
        rows.append(
            "| "
            + " | ".join([
                row["part_no"],
                row["name_cn"],
                row["material"],
                str(row["quantity"]),
                row["make_buy"],
            ])
            + " |"
        )
    return "\n".join([
        "## 5. BOM",
        "",
        "| " + " | ".join(canonical_header) + " |",
        "| --- | --- | --- | --- | --- |",
        *rows,
    ])


def _parse_bom_tree_compat(spec_path: Path, normalized_spec: str) -> list[dict[str, Any]]:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as handle:
        handle.write(normalized_spec)
        temp_path = Path(handle.name)
    try:
        return parse_bom_tree(str(temp_path))
    finally:
        temp_path.unlink(missing_ok=True)


def _split_markdown_row(line: str) -> list[str]:
    cells = [cell.strip() for cell in line.split("|")]
    if cells and cells[0] == "":
        cells = cells[1:]
    if cells and cells[-1] == "":
        cells = cells[:-1]
    return cells


def _looks_like_bom_header(cells: list[str]) -> bool:
    compact = "|".join(cells)
    return ("料号" in compact or "零件号" in compact) and "名称" in compact


def _build_header_mapping(header: list[str]) -> dict[str, int]:
    result = {}
    compact_header = [re.sub(r"\s+", "", cell).lower() for cell in header]
    for field, aliases in _HEADER_ALIASES.items():
        idx = -1
        for pos, cell in enumerate(compact_header):
            normalized_aliases = [alias.lower().replace(" ", "") for alias in aliases]
            if cell in normalized_aliases or any(
                _is_cjk_alias(alias) and alias in header[pos]
                for alias in aliases
            ):
                idx = pos
                break
        result[field] = idx
    if result["part_no"] < 0:
        raise ValueError(f"BOM part number column not found: {header}")
    return result


def _cell(cells: list[str], idx: int) -> str:
    if idx < 0 or idx >= len(cells):
        return ""
    return cells[idx].strip()


def _clean_cell(value: str) -> str:
    return value.replace("**", "").strip()


def _is_cjk_alias(alias: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in alias)


def _parse_quantity(raw: str) -> tuple[int, float, str | None]:
    text = _clean_cell(raw).strip()
    if not text:
        return 1, 0.6, "Missing quantity; defaulted to 1"
    match = re.search(r"\d+", text)
    if match:
        value = int(match.group(0))
        return max(value, 1), 1.0, None
    if text in _CHINESE_DIGITS and _CHINESE_DIGITS[text] > 0:
        return _CHINESE_DIGITS[text], 0.95, None
    chinese_value = _parse_chinese_integer(text)
    if chinese_value is not None:
        return chinese_value, 0.9, None
    return 1, 0.4, f"Could not parse quantity {raw!r}; defaulted to 1"


def _parse_chinese_integer(raw: str) -> int | None:
    text = raw.strip()
    for suffix in ("件", "个", "套", "只", "根"):
        if text.endswith(suffix):
            text = text[:-len(suffix)].strip()
            break
    if not text or any(char not in _CHINESE_DIGITS for char in text):
        return None
    if text in _CHINESE_DIGITS:
        value = _CHINESE_DIGITS[text]
        return value if 1 <= value <= 99 else None
    if "十" not in text:
        return None

    if text == "十":
        return 10
    tens_text, _, ones_text = text.partition("十")
    tens = 1 if tens_text == "" else _CHINESE_DIGITS.get(tens_text)
    ones = 0 if ones_text == "" else _CHINESE_DIGITS.get(ones_text)
    if tens is None or ones is None or tens <= 0 or tens > 9 or ones >= 10:
        return None
    value = tens * 10 + ones
    return value if 1 <= value <= 99 else None


def _under_excluded_assembly(part_no: str, excluded_assemblies: set[str]) -> bool:
    return any(part_no == assembly or part_no.startswith(f"{assembly}-") for assembly in excluded_assemblies)


def _visual_priority(part_no: str, legacy: dict[str, Any], excluded: bool) -> str:
    if excluded:
        return "low"
    if legacy.get("is_assembly"):
        return "hero"
    if part_no.count("-") <= 1:
        return "hero"
    return "normal"


def _change_policy(required: bool) -> str:
    return "preserve" if required else "optional"


def _bbox_for_part(envelope: Any) -> list[float] | None:
    if not envelope:
        return None
    dims = envelope.get("dims") if isinstance(envelope, dict) else None
    if not dims:
        return None
    return [float(value) for value in dims]


def _infer_parent_part_no(part_no: str, known_part_nos: list[str]) -> str | None:
    candidates = [
        candidate for candidate in known_part_nos
        if candidate != part_no and part_no.startswith(candidate + "-")
    ]
    if not candidates:
        return None
    return max(candidates, key=len)


def _normalize_constraints(
    constraints: list[dict[str, Any]],
    counts_by_part_no: dict[str, int],
) -> list[dict[str, Any]]:
    normalized = []
    for constraint in constraints:
        item = dict(constraint)
        part_a = item.get("part_a", "")
        part_b = item.get("part_b", "")
        item["instance_a"] = f"{part_a}#01" if part_a in counts_by_part_no else None
        item["instance_b"] = f"{part_b}#01" if part_b in counts_by_part_no else None
        normalized.append(item)
    return normalized
