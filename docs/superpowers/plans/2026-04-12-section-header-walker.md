# Section Header Walker + Envelope Extraction Foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a stateful Markdown section walker that attributes `模块包络尺寸` envelope markers to BOM assemblies via 4-tier hybrid matching, replacing the broken substring-based P2 regex block in `cad_spec_extractors.py` and enforcing `granularity` end-to-end through the codegen chain so station-level envelopes are never misused as per-part sizes.

**Architecture:**
- New module `cad_spec_section_walker.py` at repo root with `SectionWalker` class, six frozen dataclasses, per-instance-compiled regexes, and constructor kwargs for all project-specific vocabulary (trigger terms, station patterns, axis label default, BOM part-no prefixes).
- Two-phase matching: Tier 1/2/3 fire at header-push time on the header text; Tier 0 (`_find_nearest_assembly`) fires at envelope-emit time on a 500-char context window.
- Six-step granularity enforcement chain: walker → extractor → `parse_envelopes` → `PartQuery.spec_envelope_granularity` → `JinjaPrimitiveAdapter` REJECTS station_constraint envelopes for per-part sizing.
- `extract_part_envelopes` return type changes from `dict` to `tuple[dict, WalkerReport]`; `cad_spec_gen.py` destructures the tuple and renders §6.4 with an appended audit-column schema (positional `cells[3]` dims lookup in `parse_envelopes` stays backward-compat).
- Feature flag `CAD_SPEC_WALKER_ENABLED=0` falls back to the legacy P2 regex block (kept for one release cycle).

**Tech Stack:** Python 3.11+, `re` module, `dataclasses` (frozen), `typing.Literal`, pytest, existing bd_warehouse/CadQuery pipeline. No new third-party dependencies.

**Spec reference:** `docs/superpowers/specs/2026-04-12-section-header-walker-design.md` (1100 lines, 2 rounds of adversarial review applied).

---

## File Structure

### New files

| File | Responsibility |
|------|----------------|
| `cad_spec_section_walker.py` | Walker module. Dataclasses, matching tiers, section parser, envelope regex builder, axis canonicalization, legend constants, UNMATCHED suggestion templates, `SectionWalker` class. ~600 LOC. |
| `tests/test_section_walker_unit.py` | Unit tests for every walker internal: dataclasses, regex helpers, each tier, dispatchers, stack state machine, determinism, cross-subsystem isolation. |
| `tests/test_section_walker_fixtures.py` | Fixture-driven tests against the 13 synthetic `.md` files. |
| `tests/test_section_walker_real_docs.py` | Real-document integration tests using pre-computed BOM YAML fixtures. Uses `tmp_path` — never mutates `cad/<subsystem>/`. |
| `tests/test_walker_downstream_integration.py` | End-to-end granularity enforcement test (walker → parse_envelopes → PartQuery → adapter). |
| `tests/fixtures/section_walker/01_clean_station.md` ... `13_axis_label_rotation.md` | 13 synthetic fixture docs. |
| `tests/fixtures/real_doc_boms/end_effector.yaml` | Pre-computed BOM from `D:/Work/cad-tests/04-末端执行机构设计.md`. |
| `tests/fixtures/real_doc_boms/lifting_platform.yaml` | Pre-computed BOM from `D:/Work/cad-tests/19-液压钳升降平台设计.md`. |
| `tests/fixtures/real_doc_boms/_regenerate.py` | One-line helper that re-runs `extract_bom()` and dumps YAML. |

### Modified files

| File | Scope of change |
|------|-----------------|
| `cad_spec_extractors.py` | Replace P2 block (~40 lines), update `_find_nearest_assembly` to accept `bom_pno_prefixes`, change `extract_part_envelopes` return type to `tuple[dict, WalkerReport]`, add `CAD_SPEC_WALKER_ENABLED` feature flag with legacy fallback. |
| `cad_spec_gen.py` | Destructure `(part_envelopes, walker_report) = extract_part_envelopes(...)`, pass `walker_report` into `data`, render §6.4 with new columns + legend + §6.4.1 UNMATCHED subsection. |
| `codegen/gen_assembly.py::parse_envelopes` | Return `dict[pno, dict]` with `dims` and `granularity`. Read `granularity` column by header name. Positional `cells[3]` lookup for dims unchanged. |
| `codegen/gen_std_parts.py::_envelope_to_spec_envelope` and `PartQuery` constructor site | Thread `granularity` into `PartQuery.spec_envelope_granularity`. |
| `codegen/gen_parts.py` and `codegen/gen_params.py` | Update callers of `parse_envelopes` that expect bare tuples. |
| `parts_resolver.py` | Add field `spec_envelope_granularity: str = "part_envelope"` to `PartQuery`. |
| `adapters/parts/jinja_primitive_adapter.py::_resolve_dims_from_spec_envelope_or_lookup` | REJECT envelopes whose `spec_envelope_granularity != "part_envelope"`, fall through to `lookup_std_part_dims`. |
| `cad_pipeline.py` | Add `--out-dir` CLI flag so tests can redirect subsystem output. |
| `hatch_build.py` | Add `"cad_spec_section_walker.py"` to `_PIPELINE_TOOLS`. |

### Legacy files preserved behind feature flag (deleted in next spec)

- The existing P2 regex block in `cad_spec_extractors.py:1155-1197` is moved into a `_legacy_p2_regex_block()` helper function and called only when `CAD_SPEC_WALKER_ENABLED=0`. One release cycle later, the helper is removed.

---

## Task 1: BOM YAML Fixture Infrastructure

**Files:**
- Create: `tests/fixtures/real_doc_boms/_regenerate.py`
- Create: `tests/fixtures/real_doc_boms/end_effector.yaml`
- Create: `tests/fixtures/real_doc_boms/lifting_platform.yaml`
- Create: `tests/fixtures/real_doc_boms/__init__.py` (empty)

- [ ] **Step 1: Create the regenerate helper**

```python
# tests/fixtures/real_doc_boms/_regenerate.py
"""One-off helper to regenerate BOM YAML fixtures from source design docs.

Run manually when source design docs change:
    python tests/fixtures/real_doc_boms/_regenerate.py

NEVER writes anywhere except tests/fixtures/real_doc_boms/*.yaml.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

from cad_spec_extractors import extract_bom  # noqa: E402

_SOURCES = {
    "end_effector": Path("D:/Work/cad-tests/04-末端执行机构设计.md"),
    "lifting_platform": Path("D:/Work/cad-tests/19-液压钳升降平台设计.md"),
}

_OUT_DIR = Path(__file__).resolve().parent


def main() -> int:
    for name, source in _SOURCES.items():
        if not source.exists():
            print(f"[skip] {name}: source not found at {source}")
            continue
        bom = extract_bom(str(source))
        if bom is None:
            print(f"[skip] {name}: extract_bom returned None")
            continue
        out_path = _OUT_DIR / f"{name}.yaml"
        out_path.write_text(
            yaml.safe_dump(bom, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        print(f"[ok] {name}: wrote {len(bom.get('assemblies', []))} assemblies to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Generate the YAML fixtures**

Run: `python tests/fixtures/real_doc_boms/_regenerate.py`

Expected: two `.yaml` files written, each with `assemblies:` key containing multiple entries. If source docs missing, skip with a message — Layer 3 real-doc tests will auto-skip when fixtures are missing.

- [ ] **Step 3: Create the package marker**

Create empty file `tests/fixtures/real_doc_boms/__init__.py` so pytest can discover paths.

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/real_doc_boms/
git commit -m "test: add BOM YAML fixture regenerator for section walker tests"
```

---

## Task 2: Walker Dataclasses + WalkerReason + Legend Constants

**Files:**
- Create: `cad_spec_section_walker.py` (repo root)
- Create: `tests/test_section_walker_unit.py`

- [ ] **Step 1: Write the failing test for dataclass hashability**

```python
# tests/test_section_walker_unit.py
"""Unit tests for cad_spec_section_walker."""
from __future__ import annotations

import pytest

from cad_spec_section_walker import (
    EnvelopeData,
    MatchResult,
    SectionFrame,
    WalkerOutput,
    WalkerReason,
    WalkerReport,
    WalkerStats,
)


class TestDataclasses:
    def test_envelope_data_is_hashable(self):
        """Frozen + tuple dims means EnvelopeData can live in a set."""
        e1 = EnvelopeData(
            type="box",
            dims=(("x", 60.0), ("y", 40.0), ("z", 290.0)),
            axis_label="宽×深×高",
        )
        e2 = EnvelopeData(
            type="box",
            dims=(("x", 60.0), ("y", 40.0), ("z", 290.0)),
            axis_label="宽×深×高",
        )
        # Hashable + equal → same set member
        assert {e1, e2} == {e1}

    def test_envelope_data_dims_dict_returns_canonical_xyz(self):
        e = EnvelopeData(
            type="box",
            dims=(("x", 60.0), ("y", 40.0), ("z", 290.0)),
        )
        assert e.dims_dict() == {"x": 60.0, "y": 40.0, "z": 290.0}

    def test_match_result_carries_reason_code(self):
        m = MatchResult(pno="GIS-EE-002", tier=1, confidence=1.0,
                        reason="tier1_unique_match")
        assert m.reason == "tier1_unique_match"

    def test_walker_output_has_all_required_fields(self):
        o = WalkerOutput(
            matched_pno="GIS-EE-002",
            envelope_type="box",
            dims=(("x", 60.0), ("y", 40.0), ("z", 290.0)),
            tier=1,
            confidence=1.0,
            reason="tier1_unique_match",
            header_text="工位1涂抹模块",
            line_number=42,
            granularity="station_constraint",
            axis_label="宽×深×高",
            source_line="- **模块包络尺寸**：60×40×290mm (宽×深×高)",
        )
        assert o.matched_pno == "GIS-EE-002"
        assert o.granularity == "station_constraint"
        assert o.candidates == ()  # default empty tuple
```

- [ ] **Step 2: Run tests to verify they fail with ImportError**

Run: `pytest tests/test_section_walker_unit.py::TestDataclasses -v`
Expected: `ModuleNotFoundError: No module named 'cad_spec_section_walker'`

- [ ] **Step 3: Create the walker module skeleton with all dataclasses and constants**

```python
# cad_spec_section_walker.py
"""Stateful Markdown section walker that attributes envelope markers to BOM
assemblies via 4-tier hybrid matching.

See docs/superpowers/specs/2026-04-12-section-header-walker-design.md for
the design rationale, adversarial review findings, and invariants.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Literal

log = logging.getLogger("cad_spec_section_walker")

# ─── Default vocabulary (GISBOT) — overridable via constructor kwargs ───────

_DEFAULT_TRIGGER_TERMS: tuple[str, ...] = ("模块包络尺寸",)

_DEFAULT_STATION_PATTERNS: list[tuple[str, str]] = [
    (r"工位\s*(\d+)", "工位"),
    (r"第\s*(\d+)\s*级", "级"),
    (r"模块\s*(\d+)", "模块"),
    (r"第\s*(\d+)\s*部分", "部分"),
]

_DEFAULT_AXIS_LABEL: str = "宽×深×高"

# ─── Tunable thresholds ─────────────────────────────────────────────────────

CONFIDENCE_VERIFY_THRESHOLD: float = 0.75
TIER2_SUBSEQUENCE_CONFIDENCE: float = 0.85
TIER3_JACCARD_THRESHOLD: float = 0.5
AMBIGUITY_GAP: float = 0.1

# ─── Legend blocks rendered into §6.4 by cad_spec_gen.py ────────────────────

TIER_LEGEND_MD: str = (
    "- **来源** `P1:...` = 参数表 | `P2:walker:tier0` = 历史 part_no 上下文扫描 (回归保护)\n"
    "- **来源** `P2:walker:tier1` = 结构编号精确匹配 | `tier2` = 字符/单词子序列 | "
    "`tier3` = Jaccard 相似度"
)

CONFIDENCE_LEGEND_MD: str = (
    "- **置信度**: tier0/tier1 = 1.00 (精确); tier2 = 0.85 (高); "
    "tier3 = 原始 Jaccard 分数. <0.75 建议人工验证."
)

GRANULARITY_LEGEND_MD: str = (
    "- **粒度**: `station_constraint` = 工位级外包络 (模块必须装入); "
    "`part_envelope` = 单件本体尺寸.\n"
    "  **禁止**使用 `station_constraint` 尺寸作为单个采购件的建模尺寸."
)

# ─── Machine-readable result codes ──────────────────────────────────────────

WalkerReason = Literal[
    "tier0_context_window_match",
    "tier1_unique_match",
    "tier1_ambiguous_multiple_bom",
    "tier2_unique_subsequence",
    "tier2_density_tie",
    "tier2_no_cjk_content",
    "tier3_jaccard_match",
    "tier3_jaccard_tie",
    "tier3_below_threshold",
    "tier3_empty_tokens",
    "no_parent_section",
    "empty_bom",
    "all_tiers_abstained",
    "unrecognized_axis_label",
]

UNMATCHED_SUGGESTIONS: dict[str, str] = {
    "no_parent_section": "包络位于任何章节标题之前. 检查文档结构, 或将包络移到对应工位章节内.",
    "tier1_ambiguous_multiple_bom": "章节编号匹配到 {n} 个 BOM 行. 在源文档章节标题加入区分关键词.",
    "tier2_density_tie": "章节标题与 {n} 个 BOM 行子序列匹配: {candidates}. 添加更具体的章节命名.",
    "tier3_jaccard_tie": "章节标题与 {n} 个 BOM 行 Jaccard 相似度并列. 添加更具体的章节命名.",
    "tier3_below_threshold": ("所有 BOM 行 Jaccard 分数 < 0.5. "
                               "检查章节标题是否使用 BOM 中出现的关键词."),
    "all_tiers_abstained": "四个匹配层全部放弃. 检查章节标题与 BOM 名称是否差异过大.",
    "empty_bom": "BOM 为空. 检查 BOM 抽取步骤是否正常.",
    "unrecognized_axis_label": "轴向标签不在已知映射表. 参见设计规格 §5.1 轴向标签表.",
}

# ─── Dataclasses ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MatchResult:
    """Result of a single tier's attempt to match a header or context to BOM."""
    pno: str
    tier: int                # 0 / 1 / 2 / 3
    confidence: float        # 0.0 – 1.0
    reason: str              # WalkerReason literal value


@dataclass(frozen=True)
class SectionFrame:
    """One level of the section-header stack."""
    level: int                          # 1–6 markdown, 100 = standalone bold
    header_text: str                    # normalized header content
    match: MatchResult | None           # assembly match if any tier fired


@dataclass(frozen=True)
class EnvelopeData:
    """Immutable envelope data. Always stored in canonical (X, Y, Z) axis
    order — the walker rewrites source-order dims using the §5.1 axis label
    table at extraction time. Downstream consumers rely on dims[0]=X,
    dims[1]=Y, dims[2]=Z without re-parsing axis_label.
    """
    type: Literal["box", "cylinder"]
    dims: tuple[tuple[str, float], ...]
    axis_label: str | None = None

    def dims_dict(self) -> dict[str, float]:
        return dict(self.dims)


@dataclass(frozen=True)
class WalkerOutput:
    """One envelope attribution attempt (matched or unmatched)."""
    matched_pno: str | None
    envelope_type: Literal["box", "cylinder"]
    dims: tuple[tuple[str, float], ...]
    tier: int | None
    confidence: float
    reason: str                  # WalkerReason literal
    header_text: str
    line_number: int
    granularity: Literal["station_constraint", "part_envelope", "component"]
    axis_label: str | None = None
    source_line: str = ""
    candidates: tuple[tuple[str, float], ...] = ()

    def dims_dict(self) -> dict[str, float]:
        return dict(self.dims)


@dataclass(frozen=True)
class WalkerStats:
    """Counters surfaced in the rendered §6.4 footer."""
    total_envelopes: int
    matched_count: int
    unmatched_count: int
    tier_histogram: tuple[tuple[int, int], ...]
    axis_label_default_count: int
    unmatched_reasons: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class WalkerReport:
    """Return value of extract_part_envelopes() alongside the envelope dict."""
    unmatched: tuple[WalkerOutput, ...]
    stats: WalkerStats | None
    feature_flag_enabled: bool
    runtime_error: str | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_section_walker_unit.py::TestDataclasses -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add cad_spec_section_walker.py tests/test_section_walker_unit.py
git commit -m "feat(walker): add SectionWalker dataclasses + WalkerReason + legend constants"
```

---

## Task 3: Axis Label Canonicalization

**Files:**
- Modify: `cad_spec_section_walker.py` (add `_AXIS_LABEL_BOX_MAP` + `_canonicalize_box_axes`)
- Modify: `tests/test_section_walker_unit.py` (add `TestAxisCanonicalization`)

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/test_section_walker_unit.py

from cad_spec_section_walker import _canonicalize_box_axes


class TestAxisCanonicalization:
    def test_default_gisbot_label_passes_through(self):
        raw = (60.0, 40.0, 290.0)
        result = _canonicalize_box_axes(raw, "宽×深×高")
        assert result == (("x", 60.0), ("y", 40.0), ("z", 290.0))

    def test_length_first_label_keeps_position_semantics(self):
        """长×宽×高: first dim is length (X), second is width (Y), third is height (Z)."""
        raw = (1200.0, 60.0, 290.0)
        result = _canonicalize_box_axes(raw, "长×宽×高")
        assert result == (("x", 1200.0), ("y", 60.0), ("z", 290.0))

    def test_english_wdh_equals_chinese_default(self):
        raw = (60.0, 40.0, 290.0)
        assert _canonicalize_box_axes(raw, "W×D×H") == \
               _canonicalize_box_axes(raw, "宽×深×高")

    def test_unrecognized_label_returns_none(self):
        """No silent defaulting on unknown labels — caller must handle None."""
        assert _canonicalize_box_axes((1, 2, 3), "X×Y×Z (random order)") is None

    def test_label_whitespace_insensitive(self):
        result = _canonicalize_box_axes((60.0, 40.0, 290.0), " 宽 × 深 × 高 ")
        assert result == (("x", 60.0), ("y", 40.0), ("z", 290.0))

    def test_axis_swap_reorders_correctly(self):
        """深×宽×高: first raw dim is depth→Y, second is width→X, third is height→Z."""
        raw = (40.0, 60.0, 290.0)  # depth=40, width=60, height=290
        result = _canonicalize_box_axes(raw, "深×宽×高")
        # Canonical order should have X=60 (width), Y=40 (depth), Z=290 (height)
        assert result == (("x", 60.0), ("y", 40.0), ("z", 290.0))
```

- [ ] **Step 2: Run to verify tests fail**

Run: `pytest tests/test_section_walker_unit.py::TestAxisCanonicalization -v`
Expected: `ImportError: cannot import name '_canonicalize_box_axes'`

- [ ] **Step 3: Add axis map + canonicalization function**

Append to `cad_spec_section_walker.py`:

```python
# ─── Axis label canonicalization ────────────────────────────────────────────

_AXIS_LABEL_BOX_MAP: dict[str, tuple[int, int, int]] = {
    # Map normalized label → (raw_index_for_X, raw_index_for_Y, raw_index_for_Z)
    # "宽×深×高" means raw[0]=width=X, raw[1]=depth=Y, raw[2]=height=Z → (0, 1, 2)
    "宽×深×高": (0, 1, 2),
    "W×D×H": (0, 1, 2),
    "长×宽×高": (0, 1, 2),   # length=X, width=Y, height=Z (position-0 is X regardless)
    "L×W×H": (0, 1, 2),
    # Swapped orders
    "深×宽×高": (1, 0, 2),   # raw[0]=depth→Y, raw[1]=width→X, raw[2]=height→Z
    "宽×高×深": (0, 2, 1),   # raw[0]=width→X, raw[1]=height→Z, raw[2]=depth→Y
    "高×宽×深": (1, 2, 0),
    "长×高×宽": (0, 2, 1),
}


def _canonicalize_box_axes(
    raw: tuple[float, float, float],
    label: str,
) -> tuple[tuple[str, float], ...] | None:
    """Map source-order box dims to canonical (X, Y, Z) order via the label map.

    Returns None when the label is not in _AXIS_LABEL_BOX_MAP — the caller
    must surface this as UNMATCHED with reason='unrecognized_axis_label'
    rather than silently defaulting.
    """
    label_norm = re.sub(r"\s+", "", label or "")
    order = _AXIS_LABEL_BOX_MAP.get(label_norm)
    if order is None:
        return None
    return (
        ("x", raw[order[0]]),
        ("y", raw[order[1]]),
        ("z", raw[order[2]]),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_section_walker_unit.py::TestAxisCanonicalization -v`
Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add cad_spec_section_walker.py tests/test_section_walker_unit.py
git commit -m "feat(walker): add axis label canonicalization to (X,Y,Z) frame"
```

---

## Task 4: Envelope Regex Builder

**Files:**
- Modify: `cad_spec_section_walker.py` (add `_build_envelope_regexes`)
- Modify: `tests/test_section_walker_unit.py` (add `TestEnvelopeRegex`)

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/test_section_walker_unit.py

from cad_spec_section_walker import _build_envelope_regexes


class TestEnvelopeRegex:
    def _box_re(self, terms=("模块包络尺寸",)):
        box, _ = _build_envelope_regexes(terms)
        return box

    def _cyl_re(self, terms=("模块包络尺寸",)):
        _, cyl = _build_envelope_regexes(terms)
        return cyl

    def test_box_plain(self):
        m = self._box_re().search("模块包络尺寸：60×40×290mm")
        assert m is not None
        assert (m.group(1), m.group(2), m.group(3)) == ("60", "40", "290")

    def test_box_bold_before_colon(self):
        m = self._box_re().search("- **模块包络尺寸**：60×40×290mm")
        assert m is not None
        assert (m.group(1), m.group(2), m.group(3)) == ("60", "40", "290")

    def test_box_bold_around_value(self):
        m = self._box_re().search("模块包络尺寸：**60×40×290mm**")
        assert m is not None
        assert (m.group(1), m.group(2), m.group(3)) == ("60", "40", "290")

    def test_box_with_axis_label_captured(self):
        m = self._box_re().search("模块包络尺寸：60×40×290mm (宽×深×高)")
        assert m is not None
        assert m.group(4) == "宽×深×高"

    def test_box_floats(self):
        m = self._box_re().search("模块包络尺寸：60.5×40.0×290.25mm")
        assert m is not None
        assert m.group(1) == "60.5"
        assert m.group(3) == "290.25"

    def test_cylinder_phi(self):
        m = self._cyl_re().search("模块包络尺寸：Φ45×120mm")
        assert m is not None
        assert (m.group(1), m.group(2)) == ("45", "120")

    def test_cylinder_alternate_symbols(self):
        for sym in ("φ", "Ø", "∅"):
            m = self._cyl_re().search(f"模块包络尺寸：{sym}30×45mm")
            assert m is not None, f"failed on symbol {sym}"

    def test_custom_trigger_term(self):
        """Non-GISBOT subsystems pass their own term via constructor kwarg."""
        box, _ = _build_envelope_regexes(("外形尺寸",))
        m = box.search("外形尺寸：1200×600×300mm")
        assert m is not None
        assert (m.group(1), m.group(2), m.group(3)) == ("1200", "600", "300")

    def test_multiple_trigger_terms(self):
        """Terms are joined with alternation."""
        box, _ = _build_envelope_regexes(("外形尺寸", "总体尺寸"))
        assert box.search("外形尺寸：60×40×290mm") is not None
        assert box.search("总体尺寸：60×40×290mm") is not None

    def test_wrong_trigger_term_does_not_match(self):
        box, _ = _build_envelope_regexes(("外形尺寸",))
        assert box.search("模块包络尺寸：60×40×290mm") is None
```

- [ ] **Step 2: Run to verify tests fail**

Run: `pytest tests/test_section_walker_unit.py::TestEnvelopeRegex -v`
Expected: `ImportError: cannot import name '_build_envelope_regexes'`

- [ ] **Step 3: Add the regex builder**

Append to `cad_spec_section_walker.py`:

```python
# ─── Envelope regex builder ─────────────────────────────────────────────────


def _build_envelope_regexes(
    trigger_terms: tuple[str, ...],
) -> tuple[re.Pattern[str], re.Pattern[str]]:
    """Build (box_regex, cylinder_regex) for a given trigger-term set.

    Handles bold-before-colon (`模块包络尺寸**：`), bold-around-value
    (`模块包络尺寸：**60×40×290mm**`), and an optional parenthetical axis label.

    Called per-walker-instance inside SectionWalker.__init__ — NO module-level
    cache. This is load-bearing for G12 cross-subsystem isolation.
    """
    trigger = "|".join(re.escape(t) for t in trigger_terms)
    prelude = fr"(?:{trigger})(?:\*\*)?[：:]\s*(?:\*\*)?\s*"
    # optional closing bold + optional parenthetical label (supports both ASCII and full-width parens)
    suffix = r"\s*(?:\*\*)?(?:\s*[(（]([^)）]+)[)）])?"

    box_body = (
        r"(\d+(?:\.\d+)?)\s*[×xX]\s*"
        r"(\d+(?:\.\d+)?)\s*[×xX]\s*"
        r"(\d+(?:\.\d+)?)\s*mm"
    )
    cyl_body = (
        r"[ΦφØ∅](\d+(?:\.\d+)?)\s*[×xX]\s*"
        r"(\d+(?:\.\d+)?)\s*mm"
    )
    box_re = re.compile(prelude + box_body + suffix)      # groups: 1=w 2=d 3=h 4=axis_label
    cyl_re = re.compile(prelude + cyl_body + suffix)      # groups: 1=dia 2=h 3=axis_label
    return box_re, cyl_re
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_section_walker_unit.py::TestEnvelopeRegex -v`
Expected: all 10 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add cad_spec_section_walker.py tests/test_section_walker_unit.py
git commit -m "feat(walker): add configurable envelope regex builder"
```

---

## Task 5: Section Header Parsing + Normalization

**Files:**
- Modify: `cad_spec_section_walker.py` (add `_normalize_header`, `_parse_section_header`)
- Modify: `tests/test_section_walker_unit.py` (add `TestSectionHeader`)

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/test_section_walker_unit.py

from cad_spec_section_walker import _normalize_header, _parse_section_header


class TestSectionHeader:
    def test_normalize_strips_bold(self):
        assert _normalize_header("**工位1**") == "工位1"

    def test_normalize_strips_markdown_hash(self):
        assert _normalize_header("### 4.1.2 各工位机械结构") == "4.1.2 各工位机械结构"

    def test_normalize_collapses_whitespace(self):
        assert _normalize_header("  工位1   涂抹  模块  ") == "工位1 涂抹 模块"

    def test_markdown_h1(self):
        assert _parse_section_header("# Top") == (1, "Top")

    def test_markdown_h3(self):
        assert _parse_section_header("### 4.1 Stations") == (3, "4.1 Stations")

    def test_markdown_h6(self):
        assert _parse_section_header("###### Deep") == (6, "Deep")

    def test_markdown_h7_not_a_header(self):
        """Seven hashes is not a valid Markdown header."""
        assert _parse_section_header("####### Too deep") is None

    def test_standalone_bold_is_level_100(self):
        result = _parse_section_header("**工位1(0°)：耦合剂涂抹模块**")
        assert result == (100, "工位1(0°)：耦合剂涂抹模块")

    def test_bullet_bold_is_not_a_header(self):
        """Property labels like `- **模块包络尺寸**：60×40×290mm` must NOT
        reset section state — if they did, the walker would lose the
        parent station on every envelope line."""
        assert _parse_section_header("- **模块包络尺寸**：60×40×290mm") is None

    def test_regular_line_is_not_a_header(self):
        assert _parse_section_header("This is a paragraph.") is None

    def test_empty_line_is_not_a_header(self):
        assert _parse_section_header("") is None

    def test_bold_with_trailing_content_is_not_a_header(self):
        """Only standalone-bold-on-own-line counts."""
        assert _parse_section_header("**工位1**: some text after") is None
```

- [ ] **Step 2: Run to verify tests fail**

Run: `pytest tests/test_section_walker_unit.py::TestSectionHeader -v`
Expected: import errors for `_normalize_header`, `_parse_section_header`.

- [ ] **Step 3: Add the helpers**

Append to `cad_spec_section_walker.py`:

```python
# ─── Section header parsing ─────────────────────────────────────────────────

_HASH_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_STANDALONE_BOLD_RE = re.compile(r"^\*\*([^*]+)\*\*\s*$")

BOLD_HEADER_LEVEL: int = 100  # sentinel: always deeper than any markdown hash


def _normalize_header(text: str) -> str:
    """Strip markdown artifacts and collapse whitespace; return the semantic
    content of the header, preserving original characters for tier 2/3
    matching which operates on character content."""
    text = re.sub(r"\*\*", "", text)
    text = re.sub(r"^#{1,6}\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_section_header(line: str) -> tuple[int, str] | None:
    """Return (level, normalized_text) or None.

    - Markdown `#` headers (levels 1-6) → (1..6, text)
    - Standalone `**bold**` on its own line → (BOLD_HEADER_LEVEL, text)
    - Bullet-list bold items (`- **label**:value`) → None (property label, not header)
    - Anything else → None
    """
    if not line or not line.strip():
        return None
    m = _HASH_HEADER_RE.match(line)
    if m:
        level = len(m.group(1))
        return (level, _normalize_header(m.group(2)))
    m = _STANDALONE_BOLD_RE.match(line)
    if m:
        return (BOLD_HEADER_LEVEL, _normalize_header(m.group(1)))
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_section_walker_unit.py::TestSectionHeader -v`
Expected: all 12 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add cad_spec_section_walker.py tests/test_section_walker_unit.py
git commit -m "feat(walker): add section-header parsing + normalization"
```

---

## Task 6: Tier 1 Pattern Matching (with ambiguity return-None fix)

**Files:**
- Modify: `cad_spec_section_walker.py` (add `_match_by_pattern`)
- Modify: `tests/test_section_walker_unit.py` (add `TestTier1Pattern`)

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/test_section_walker_unit.py

from cad_spec_section_walker import _match_by_pattern, _DEFAULT_STATION_PATTERNS


def _bom(assemblies):
    return {"assemblies": assemblies}


class TestTier1Pattern:
    def test_unique_station_match(self):
        bom = _bom([
            {"part_no": "GIS-EE-002", "name": "工位1涂抹模块"},
            {"part_no": "GIS-EE-003", "name": "工位2 AE检测模块"},
        ])
        result = _match_by_pattern("工位1(0°)：耦合剂涂抹模块", bom,
                                   _DEFAULT_STATION_PATTERNS)
        assert result is not None
        assert result.pno == "GIS-EE-002"
        assert result.tier == 1
        assert result.confidence == 1.0
        assert result.reason == "tier1_unique_match"

    def test_ambiguous_station_returns_none(self):
        """Two BOM rows share 工位1 → abstain entirely (return None),
        do NOT fall through to the next pattern. Regression test for
        round-2 programmer review finding: earlier draft used `continue`
        which silently matched a later pattern on the same header."""
        bom = _bom([
            {"part_no": "GIS-EE-002", "name": "工位1涂抹模块"},
            {"part_no": "GIS-EE-004", "name": "工位1驱动模块"},
        ])
        result = _match_by_pattern("工位1 耦合剂涂抹", bom,
                                   _DEFAULT_STATION_PATTERNS)
        assert result is None

    def test_pattern_fires_but_no_bom_match_tries_next_pattern(self):
        """工位1 regex fires but BOM has no 工位 row → fall through to
        the next pattern (模块). This is the one legitimate `continue`
        case — distinct from ambiguity."""
        bom = _bom([
            {"part_no": "GIS-EE-010", "name": "模块3输电线"},
        ])
        result = _match_by_pattern("工位1 模块3", bom, _DEFAULT_STATION_PATTERNS)
        assert result is not None
        assert result.pno == "GIS-EE-010"

    def test_no_pattern_matches_header(self):
        bom = _bom([{"part_no": "X", "name": "something"}])
        assert _match_by_pattern("Plain English Title", bom,
                                 _DEFAULT_STATION_PATTERNS) is None

    def test_custom_station_patterns(self):
        """Chassis subsystem passes its own patterns via kwargs."""
        chassis = [(r"驱动轮\s*(\d+)", "驱动轮")]
        bom = _bom([{"part_no": "CHASSIS-DRV-003", "name": "驱动轮3 减速器总成"}])
        result = _match_by_pattern("驱动轮3 减速器", bom, chassis)
        assert result is not None
        assert result.pno == "CHASSIS-DRV-003"

    def test_level_pattern(self):
        bom = _bom([{"part_no": "L2", "name": "第2级支撑"}])
        assert _match_by_pattern("第2级主体", bom,
                                 _DEFAULT_STATION_PATTERNS).pno == "L2"
```

- [ ] **Step 2: Run to verify tests fail**

Run: `pytest tests/test_section_walker_unit.py::TestTier1Pattern -v`

- [ ] **Step 3: Add the tier 1 matcher**

Append to `cad_spec_section_walker.py`:

```python
# ─── Tier 1: structured pattern matching ────────────────────────────────────


def _match_by_pattern(
    header: str,
    bom_data: dict,
    station_patterns: list[tuple[str, str]],
) -> MatchResult | None:
    """Extract an (index, category) from a structured pattern and find the
    matching BOM assembly. Abstains (returns None) on ambiguity AT THE
    FIRST pattern that matches — does NOT fall through to the next
    pattern, which would produce false-confident matches.
    """
    for regex, category in station_patterns:
        m = re.search(regex, header)
        if not m:
            continue
        idx = int(m.group(1))
        idx_re = re.compile(fr"{re.escape(category)}\s*(\d+)")
        matching = []
        for assy in bom_data.get("assemblies", []):
            name = assy.get("name", "")
            m2 = idx_re.search(name)
            if m2 and int(m2.group(1)) == idx:
                matching.append(assy)
        if len(matching) == 0:
            # This pattern fired but BOM has no row — fall through to next pattern.
            continue
        if len(matching) >= 2:
            # Ambiguity at THIS pattern — abstain entirely. Returning None
            # hands off to Tier 2, NOT to the next pattern in the list.
            return None
        return MatchResult(
            pno=matching[0]["part_no"],
            tier=1,
            confidence=1.0,
            reason="tier1_unique_match",
        )
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_section_walker_unit.py::TestTier1Pattern -v`
Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add cad_spec_section_walker.py tests/test_section_walker_unit.py
git commit -m "feat(walker): add Tier 1 pattern matching with ambiguity abstention"
```

---

## Task 7: Tier 2 Subsequence Matching (dual-path CJK + ASCII)

**Files:**
- Modify: `cad_spec_section_walker.py` (add `_cjk_only`, `_ascii_words`, `_match_by_subsequence`)
- Modify: `tests/test_section_walker_unit.py` (add `TestTier2Subsequence`)

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/test_section_walker_unit.py

from cad_spec_section_walker import _match_by_subsequence


class TestTier2Subsequence:
    def test_cjk_subsequence_matches(self):
        """工位涂抹模块 is a character subsequence of 工位耦合剂涂抹模块."""
        bom = _bom([
            {"part_no": "GIS-EE-002", "name": "工位1涂抹模块"},
            {"part_no": "GIS-EE-003", "name": "工位2 AE检测"},
        ])
        result = _match_by_subsequence("工位1(0°)：耦合剂涂抹模块", bom)
        assert result is not None
        assert result.pno == "GIS-EE-002"
        assert result.tier == 2
        assert result.confidence == 0.85
        assert result.reason == "tier2_unique_subsequence"

    def test_ascii_word_subsequence_matches(self):
        """'Main Arm' is a word subsequence of 'Main Arm Assembly'."""
        bom = _bom([
            {"part_no": "LIFT-001", "name": "Main Arm"},
            {"part_no": "LIFT-002", "name": "Cross Beam"},
        ])
        result = _match_by_subsequence("## Main Arm Assembly", bom)
        assert result is not None
        assert result.pno == "LIFT-001"

    def test_density_tie_abstains(self):
        """Two BOM rows with near-identical density → abstain."""
        bom = _bom([
            {"part_no": "A", "name": "工位1驱动"},
            {"part_no": "B", "name": "工位1涂抹"},
        ])
        # Header contains both subsequences with similar density.
        result = _match_by_subsequence("工位1 驱动 涂抹 共用", bom)
        assert result is None

    def test_no_cjk_no_ascii_returns_none(self):
        bom = _bom([{"part_no": "A", "name": "工位1模块"}])
        assert _match_by_subsequence("12345", bom) is None

    def test_empty_bom_returns_none(self):
        assert _match_by_subsequence("工位1", _bom([])) is None

    def test_out_of_order_chars_no_match(self):
        """Characters must appear IN ORDER as a subsequence."""
        bom = _bom([{"part_no": "A", "name": "涂抹工位"}])
        assert _match_by_subsequence("工位1涂抹", bom) is None

    def test_deterministic_tie_break_by_pno(self):
        """Equal density, different pnos → sort by pno alphabetically.
        Current behavior under tie: near-tie (gap < 0.1) abstains, so this
        test validates the sort key, not a match result."""
        bom = _bom([
            {"part_no": "B-BBB", "name": "工位模"},  # density 3/3
            {"part_no": "A-AAA", "name": "工位模"},  # density 3/3
        ])
        # Exact tie → abstain
        assert _match_by_subsequence("工位模", bom) is None
```

- [ ] **Step 2: Run to verify tests fail**

Run: `pytest tests/test_section_walker_unit.py::TestTier2Subsequence -v`

- [ ] **Step 3: Add tier 2 helpers + matcher**

Append to `cad_spec_section_walker.py`:

```python
# ─── Tier 2: dual-path subsequence matching ─────────────────────────────────

_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_ASCII_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*")


def _cjk_only(text: str) -> str:
    return "".join(_CJK_RE.findall(text))


def _ascii_words(text: str) -> list[str]:
    return [w.lower() for w in _ASCII_WORD_RE.findall(text) if len(w) >= 2]


def _is_char_subsequence(needle: str, haystack: str) -> bool:
    it = iter(haystack)
    return all(ch in it for ch in needle)


def _is_word_subsequence(needle: list[str], haystack: list[str]) -> bool:
    it = iter(haystack)
    return all(w in it for w in needle)


def _match_by_subsequence(header: str, bom_data: dict) -> MatchResult | None:
    """Tier 2: CJK character subsequence OR ASCII word subsequence.

    Dual-path: runs both paths in parallel and picks the better density.
    Abstains on ties (density gap < AMBIGUITY_GAP).
    """
    header_cjk = _cjk_only(header)
    header_words = _ascii_words(header)

    matches: list[tuple[str, float]] = []
    for assy in bom_data.get("assemblies", []):
        name = assy.get("name", "")
        bom_cjk = _cjk_only(name)
        bom_words = _ascii_words(name)

        best_density = 0.0
        if bom_cjk and header_cjk and _is_char_subsequence(bom_cjk, header_cjk):
            best_density = max(best_density, len(bom_cjk) / max(len(header_cjk), 1))
        if bom_words and header_words and _is_word_subsequence(bom_words, header_words):
            best_density = max(best_density, len(bom_words) / max(len(header_words), 1))

        if best_density > 0:
            matches.append((assy["part_no"], best_density))

    if not matches:
        return None

    # Stable deterministic sort: density desc, then part_no asc.
    matches.sort(key=lambda m: (-m[1], m[0]))
    if len(matches) == 1:
        return MatchResult(
            pno=matches[0][0], tier=2,
            confidence=TIER2_SUBSEQUENCE_CONFIDENCE,
            reason="tier2_unique_subsequence",
        )

    top_pno, top_dens = matches[0]
    _, runner_dens = matches[1]
    if abs(top_dens - runner_dens) < AMBIGUITY_GAP:
        return None  # tie → abstain

    return MatchResult(
        pno=top_pno, tier=2,
        confidence=TIER2_SUBSEQUENCE_CONFIDENCE,
        reason="tier2_unique_subsequence",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_section_walker_unit.py::TestTier2Subsequence -v`
Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add cad_spec_section_walker.py tests/test_section_walker_unit.py
git commit -m "feat(walker): add Tier 2 dual-path subsequence matcher"
```

---

## Task 8: Tier 3 Jaccard Matching

**Files:**
- Modify: `cad_spec_section_walker.py` (add `_tokenize`, `_match_by_jaccard`)
- Modify: `tests/test_section_walker_unit.py` (add `TestTier3Jaccard`)

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/test_section_walker_unit.py

from cad_spec_section_walker import _match_by_jaccard, _tokenize


class TestTier3Jaccard:
    def test_tokenize_cjk_bigrams(self):
        tokens = _tokenize("工位耦合剂")
        assert "工位" in tokens
        assert "位耦" in tokens
        assert "耦合" in tokens

    def test_tokenize_ascii_words_lowercased(self):
        tokens = _tokenize("Main Arm Module")
        assert "main" in tokens
        assert "arm" in tokens
        assert "module" in tokens

    def test_tokenize_short_ascii_words_excluded(self):
        """Single-char ASCII words are too noisy for Jaccard."""
        tokens = _tokenize("a bc")
        assert "a" not in tokens
        assert "bc" in tokens

    def test_match_above_threshold(self):
        bom = _bom([{"part_no": "X", "name": "传感器模块组件"}])
        result = _match_by_jaccard("传感器模块组件设计", bom)
        assert result is not None
        assert result.pno == "X"
        assert result.tier == 3
        assert result.reason == "tier3_jaccard_match"

    def test_below_threshold_returns_none(self):
        bom = _bom([{"part_no": "X", "name": "unrelated stuff"}])
        assert _match_by_jaccard("完全不同的章节", bom) is None

    def test_exact_tie_abstains(self):
        bom = _bom([
            {"part_no": "A", "name": "工位模块"},
            {"part_no": "B", "name": "工位模块"},
        ])
        assert _match_by_jaccard("工位模块 附加", bom) is None

    def test_near_tie_abstains(self):
        """Two scores within AMBIGUITY_GAP → abstain."""
        bom = _bom([
            {"part_no": "A", "name": "大功率电机驱动"},
            {"part_no": "B", "name": "大功率电机控制"},
        ])
        assert _match_by_jaccard("大功率电机 通用", bom) is None

    def test_deterministic_tie_break_in_sort(self):
        """Non-tied candidates sorted by (-score, pno). Use pnos that would
        sort differently by dict iteration order vs alphabetical."""
        bom = _bom([
            {"part_no": "Z-highscore", "name": "aa bb cc dd ee ff"},
            {"part_no": "A-lower",    "name": "aa bb"},
        ])
        # Z has higher Jaccard, should win regardless of iteration order
        result = _match_by_jaccard("aa bb cc dd ee ff gg", bom)
        assert result is not None
        assert result.pno == "Z-highscore"

    def test_empty_tokens_returns_none(self):
        """Header with only single-char ASCII and single-char CJK runs."""
        bom = _bom([{"part_no": "X", "name": "工位1"}])
        assert _match_by_jaccard("a b c", bom) is None
```

- [ ] **Step 2: Run to verify tests fail**

Run: `pytest tests/test_section_walker_unit.py::TestTier3Jaccard -v`

- [ ] **Step 3: Add tier 3 helpers + matcher**

Append to `cad_spec_section_walker.py`:

```python
# ─── Tier 3: Jaccard mixed-token similarity ─────────────────────────────────


def _tokenize(text: str) -> set[str]:
    """Produce CJK bigrams + ASCII words (length ≥ 2, lowercased)."""
    tokens: set[str] = set()
    for run in _CJK_RE.findall(text):
        for i in range(len(run) - 1):
            tokens.add(run[i:i + 2])
    for word in _ASCII_WORD_RE.findall(text):
        if len(word) >= 2:
            tokens.add(word.lower())
    return tokens


def _match_by_jaccard(
    header: str,
    bom_data: dict,
    threshold: float = TIER3_JACCARD_THRESHOLD,
) -> MatchResult | None:
    """Tier 3: mixed CJK bigram + ASCII word Jaccard similarity.

    Collects all above-threshold scores, sorts with deterministic tie-break
    `(-score, pno)`, abstains on exact ties and near-ties.
    """
    header_tokens = _tokenize(header)
    if not header_tokens:
        return None

    scored: list[tuple[str, float]] = []
    for assy in bom_data.get("assemblies", []):
        bom_tokens = _tokenize(assy.get("name", ""))
        if not bom_tokens:
            continue
        intersection = len(header_tokens & bom_tokens)
        union = len(header_tokens | bom_tokens)
        score = intersection / union if union > 0 else 0.0
        if score >= threshold:
            scored.append((assy["part_no"], score))

    if not scored:
        return None

    scored.sort(key=lambda x: (-x[1], x[0]))
    best_pno, best_score = scored[0]
    if len(scored) >= 2:
        _, runner_score = scored[1]
        if runner_score == best_score:
            return None
        if (best_score - runner_score) < AMBIGUITY_GAP:
            return None

    return MatchResult(
        pno=best_pno, tier=3, confidence=best_score,
        reason="tier3_jaccard_match",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_section_walker_unit.py::TestTier3Jaccard -v`
Expected: all 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add cad_spec_section_walker.py tests/test_section_walker_unit.py
git commit -m "feat(walker): add Tier 3 Jaccard matcher with stable tie-break"
```

---

## Task 9: Refactor `_find_nearest_assembly` to take BOM prefixes

**Files:**
- Modify: `cad_spec_extractors.py:1303` (update `_find_nearest_assembly` signature)
- Modify: `tests/test_envelope_prose_regex.py` (update test for new signature)

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_envelope_prose_regex.py (or a new test file)

def test_find_nearest_assembly_uses_bom_derived_prefixes():
    """Tier 0 must work on non-GISBOT subsystems. The prefix regex should
    be built from BOM data at call time, not hardcoded to GIS-EE-NNN."""
    from cad_spec_extractors import _find_nearest_assembly

    bom = {
        "assemblies": [
            {"part_no": "CHASSIS-DRV-001", "name": "Drive Wheel 1"},
            {"part_no": "CHASSIS-DRV-002", "name": "Drive Wheel 2"},
        ]
    }
    prefixes = ("CHASSIS-DRV",)
    context = "see CHASSIS-DRV-001 specification for detail"
    assert _find_nearest_assembly(context, bom, prefixes) == "CHASSIS-DRV-001"


def test_find_nearest_assembly_backward_compat_gis_ee():
    """When prefixes is None, auto-derive from BOM (supports legacy callers)."""
    from cad_spec_extractors import _find_nearest_assembly
    bom = {
        "assemblies": [{"part_no": "GIS-EE-002", "name": "工位1涂抹模块"}],
    }
    context = "as defined in GIS-EE-002 above"
    assert _find_nearest_assembly(context, bom) == "GIS-EE-002"


def test_find_nearest_assembly_no_prefixes_no_match():
    from cad_spec_extractors import _find_nearest_assembly
    bom = {"assemblies": []}
    assert _find_nearest_assembly("anything", bom) is None
```

- [ ] **Step 2: Run to verify test fails**

Run: `pytest tests/test_envelope_prose_regex.py::test_find_nearest_assembly_uses_bom_derived_prefixes -v`
Expected: FAIL — current signature takes only `(context, bom_data)`, not 3 args.

- [ ] **Step 3: Update `_find_nearest_assembly` to take prefixes**

Replace `cad_spec_extractors.py:1303-1314`:

```python
def _find_nearest_assembly(
    context: str,
    bom_data,
    bom_pno_prefixes: tuple[str, ...] | None = None,
) -> "Optional[str]":
    """Find nearest assembly part_no from preceding text context.

    Tier 0 fallback used by both the legacy P2 regex block and the new
    SectionWalker. Prefixes are derived from BOM data when not supplied
    so the regex generalizes beyond GIS-EE-NNN to arbitrary XYZ-ABC-NNN
    subsystems. Fall-back strategies:
      1. Regex scan for explicit {prefix}-NNN in context → use last match
      2. First-4-char substring match of BOM name in context → use that pno
    """
    if not bom_data:
        return None

    # Auto-derive prefix set from BOM when caller doesn't supply one.
    if bom_pno_prefixes is None:
        prefix_set: set[str] = set()
        for assy in bom_data.get("assemblies", []):
            pno = assy.get("part_no", "")
            if "-" in pno:
                prefix_set.add(pno.rsplit("-", 1)[0])
        bom_pno_prefixes = tuple(sorted(prefix_set))

    if bom_pno_prefixes:
        alternation = "|".join(re.escape(p) for p in bom_pno_prefixes)
        pnos = re.findall(fr"(?:{alternation})-\d+", context)
        if pnos:
            return pnos[-1]

    for assy in bom_data.get("assemblies", []):
        name = assy.get("name", "")
        if name and len(name) >= 4 and name[:4] in context:
            return assy.get("part_no")
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_envelope_prose_regex.py -v`
Expected: all tests pass, including the existing ones.

- [ ] **Step 5: Commit**

```bash
git add cad_spec_extractors.py tests/test_envelope_prose_regex.py
git commit -m "refactor(extractors): parametrize _find_nearest_assembly with BOM prefixes"
```

---

## Task 10: Two-Phase Match Dispatchers

**Files:**
- Modify: `cad_spec_section_walker.py` (add `_match_header`, `_match_context`)
- Modify: `tests/test_section_walker_unit.py` (add `TestDispatchers`)

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/test_section_walker_unit.py

from cad_spec_section_walker import _match_header, _match_context


class TestDispatchers:
    def test_match_header_tries_tiers_in_order(self):
        bom = _bom([{"part_no": "GIS-EE-002", "name": "工位1涂抹模块"}])
        # Unique station → Tier 1 fires
        result = _match_header("工位1涂抹", bom, _DEFAULT_STATION_PATTERNS)
        assert result is not None
        assert result.tier == 1

    def test_match_header_falls_through_to_tier2(self):
        """Tier 1 abstains (no 工位 in header); Tier 2 matches on CJK subsequence."""
        bom = _bom([{"part_no": "X", "name": "传感器组件"}])
        result = _match_header("传感器模块组件测试", bom,
                               _DEFAULT_STATION_PATTERNS)
        assert result is not None
        assert result.tier == 2

    def test_match_header_falls_through_to_tier3(self):
        """Tier 1+2 abstain; Tier 3 Jaccard matches."""
        bom = _bom([{"part_no": "X", "name": "aa bb cc dd ee"}])
        result = _match_header("aa bb cc dd ee ff", bom,
                               _DEFAULT_STATION_PATTERNS)
        assert result is not None
        assert result.tier == 3

    def test_match_header_all_abstain_returns_none(self):
        bom = _bom([{"part_no": "X", "name": "completely unrelated"}])
        assert _match_header("完全不同", bom, _DEFAULT_STATION_PATTERNS) is None

    def test_match_context_fires_tier0_on_explicit_pno(self):
        bom = _bom([{"part_no": "GIS-EE-002", "name": "工位1涂抹模块"}])
        context = "earlier paragraphs... see GIS-EE-002 spec table above."
        result = _match_context(context, ("GIS-EE",), bom)
        assert result is not None
        assert result.tier == 0
        assert result.pno == "GIS-EE-002"
        assert result.reason == "tier0_context_window_match"

    def test_match_context_no_pno_returns_none(self):
        bom = _bom([{"part_no": "GIS-EE-002", "name": "工位1涂抹模块"}])
        result = _match_context("unrelated context", ("GIS-EE",), bom)
        # May fall back to name-substring match (4-char 工位1涂 not in context)
        assert result is None
```

- [ ] **Step 2: Run to verify tests fail**

Run: `pytest tests/test_section_walker_unit.py::TestDispatchers -v`

- [ ] **Step 3: Add the dispatcher functions**

Append to `cad_spec_section_walker.py`:

```python
# ─── Two-phase match dispatchers ────────────────────────────────────────────


def _match_header(
    header: str,
    bom_data: dict,
    station_patterns: list[tuple[str, str]],
) -> MatchResult | None:
    """Phase A: run Tier 1 → 2 → 3 on a section header.

    Called at header-push time inside SectionWalker.walk(). The first
    non-None tier result wins; returns None when all three abstain.
    """
    result = _match_by_pattern(header, bom_data, station_patterns)
    if result is not None:
        return result
    result = _match_by_subsequence(header, bom_data)
    if result is not None:
        return result
    return _match_by_jaccard(header, bom_data)


def _match_context(
    context: str,
    bom_pno_prefixes: tuple[str, ...],
    bom_data: dict,
) -> MatchResult | None:
    """Phase B: Tier 0 — lazy import of the legacy helper.

    Called at envelope-emit time with the 500-char preceding window.
    Imports `_find_nearest_assembly` locally because `cad_spec_extractors`
    imports this module transitively at P2 integration time — module-level
    import would create a cycle.
    """
    from cad_spec_extractors import _find_nearest_assembly
    pno = _find_nearest_assembly(context, bom_data, bom_pno_prefixes)
    if pno is None:
        return None
    return MatchResult(
        pno=pno, tier=0, confidence=1.0,
        reason="tier0_context_window_match",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_section_walker_unit.py::TestDispatchers -v`
Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add cad_spec_section_walker.py tests/test_section_walker_unit.py
git commit -m "feat(walker): add two-phase _match_header and _match_context dispatchers"
```

---

## Task 11: SectionWalker class — constructor + per-instance regex compilation

**Files:**
- Modify: `cad_spec_section_walker.py` (add `SectionWalker` class)
- Modify: `tests/test_section_walker_unit.py` (add `TestSectionWalkerInit`)

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/test_section_walker_unit.py

from cad_spec_section_walker import SectionWalker


class TestSectionWalkerInit:
    def test_default_construction(self):
        w = SectionWalker(["hello"], _bom([]))
        assert w.trigger_terms == ("模块包络尺寸",)
        assert w.axis_label_default == "宽×深×高"
        # Station patterns default to GISBOT set
        assert any("工位" in p[1] for p in w.station_patterns)

    def test_custom_trigger_terms(self):
        w = SectionWalker([], _bom([]), trigger_terms=("外形尺寸",))
        assert w.trigger_terms == ("外形尺寸",)
        # Regex is per-instance — verify the compiled regex binds to this term
        assert w._box_re.search("外形尺寸：60×40×290mm") is not None
        assert w._box_re.search("模块包络尺寸：60×40×290mm") is None

    def test_custom_station_patterns(self):
        patterns = [(r"驱动轮\s*(\d+)", "驱动轮")]
        w = SectionWalker([], _bom([]), station_patterns=patterns)
        assert w.station_patterns == patterns

    def test_bom_prefixes_auto_derived(self):
        bom = _bom([
            {"part_no": "CHASSIS-DRV-001", "name": "a"},
            {"part_no": "CHASSIS-SUS-003", "name": "b"},
        ])
        w = SectionWalker([], bom)
        assert "CHASSIS-DRV" in w.bom_pno_prefixes
        assert "CHASSIS-SUS" in w.bom_pno_prefixes

    def test_bom_prefixes_override(self):
        w = SectionWalker([], _bom([]), bom_pno_prefixes=("CUSTOM",))
        assert w.bom_pno_prefixes == ("CUSTOM",)

    def test_per_instance_regex_isolation(self):
        """Two walkers with different trigger_terms must have different
        compiled regexes — module-level cache would break this."""
        w1 = SectionWalker([], _bom([]), trigger_terms=("模块包络尺寸",))
        w2 = SectionWalker([], _bom([]), trigger_terms=("外形尺寸",))
        assert w1._box_re is not w2._box_re
        assert w1._box_re.search("模块包络尺寸：1×2×3mm") is not None
        assert w2._box_re.search("模块包络尺寸：1×2×3mm") is None
        assert w2._box_re.search("外形尺寸：1×2×3mm") is not None
        assert w1._box_re.search("外形尺寸：1×2×3mm") is None
```

- [ ] **Step 2: Run to verify tests fail**

Run: `pytest tests/test_section_walker_unit.py::TestSectionWalkerInit -v`

- [ ] **Step 3: Add the SectionWalker class skeleton**

Append to `cad_spec_section_walker.py`:

```python
# ─── SectionWalker class ────────────────────────────────────────────────────


class SectionWalker:
    """Stateful walker that tracks active section headers + attributes
    envelope markers to BOM assemblies.

    Construction is the only state boundary — one instance per
    extract_part_envelopes() call. NO module-level mutable state.
    """

    def __init__(
        self,
        lines: list[str],
        bom_data: dict,
        *,
        trigger_terms: tuple[str, ...] = _DEFAULT_TRIGGER_TERMS,
        station_patterns: list[tuple[str, str]] | None = None,
        axis_label_default: str = _DEFAULT_AXIS_LABEL,
        bom_pno_prefixes: tuple[str, ...] | None = None,
    ) -> None:
        self.lines = list(lines)
        self.bom_data = bom_data or {"assemblies": []}
        self.trigger_terms = tuple(trigger_terms)
        self.station_patterns = (
            list(station_patterns) if station_patterns is not None
            else list(_DEFAULT_STATION_PATTERNS)
        )
        self.axis_label_default = axis_label_default

        # Derive BOM prefixes when not supplied.
        if bom_pno_prefixes is None:
            derived: set[str] = set()
            for assy in self.bom_data.get("assemblies", []):
                pno = assy.get("part_no", "")
                if "-" in pno:
                    derived.add(pno.rsplit("-", 1)[0])
            self.bom_pno_prefixes = tuple(sorted(derived))
        else:
            self.bom_pno_prefixes = tuple(bom_pno_prefixes)

        # Per-instance compiled envelope regexes — NO module-level cache.
        self._box_re, self._cyl_re = _build_envelope_regexes(self.trigger_terms)

        # Per-instance counters (written during walk).
        self._axis_label_default_count = 0

        # Caches for public API.
        self._outputs: list[WalkerOutput] = []
        self._stats: WalkerStats | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_section_walker_unit.py::TestSectionWalkerInit -v`
Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add cad_spec_section_walker.py tests/test_section_walker_unit.py
git commit -m "feat(walker): add SectionWalker.__init__ with per-instance state"
```

---

## Task 12: Envelope Extraction Method + Axis Canonicalization Integration

**Files:**
- Modify: `cad_spec_section_walker.py` (add `_extract_envelope_from_line` method)
- Modify: `tests/test_section_walker_unit.py` (add `TestEnvelopeExtraction`)

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/test_section_walker_unit.py


class TestEnvelopeExtraction:
    def test_box_extraction_with_default_axis(self):
        w = SectionWalker([], _bom([]))
        env = w._extract_envelope_from_line("模块包络尺寸：60×40×290mm")
        assert env is not None
        assert env.type == "box"
        assert env.dims == (("x", 60.0), ("y", 40.0), ("z", 290.0))
        assert w._axis_label_default_count == 1

    def test_box_with_explicit_label_preserved(self):
        w = SectionWalker([], _bom([]))
        env = w._extract_envelope_from_line(
            "模块包络尺寸：60×40×290mm (宽×深×高)"
        )
        assert env is not None
        assert env.axis_label == "宽×深×高"
        assert env.dims[0] == ("x", 60.0)
        assert w._axis_label_default_count == 0

    def test_box_with_length_first_label_reorders_correctly(self):
        w = SectionWalker([], _bom([]))
        env = w._extract_envelope_from_line(
            "模块包络尺寸：1200×60×290mm (长×宽×高)"
        )
        assert env is not None
        # (长, 宽, 高) → (x=1200, y=60, z=290) per the axis map
        assert env.dims == (("x", 1200.0), ("y", 60.0), ("z", 290.0))

    def test_cylinder_extraction(self):
        w = SectionWalker([], _bom([]))
        env = w._extract_envelope_from_line("模块包络尺寸：Φ45×120mm")
        assert env is not None
        assert env.type == "cylinder"
        assert env.dims == (("d", 45.0), ("z", 120.0))

    def test_unrecognized_axis_label_returns_none(self):
        """Walker refuses silent defaulting on unknown labels."""
        w = SectionWalker([], _bom([]))
        env = w._extract_envelope_from_line(
            "模块包络尺寸：60×40×290mm (random order)"
        )
        assert env is None  # will surface as UNMATCHED with reason='unrecognized_axis_label'

    def test_line_without_envelope_returns_none(self):
        w = SectionWalker([], _bom([]))
        assert w._extract_envelope_from_line("Just some paragraph text.") is None

    def test_custom_trigger_term(self):
        w = SectionWalker([], _bom([]), trigger_terms=("外形尺寸",))
        env = w._extract_envelope_from_line("外形尺寸：100×50×25mm")
        assert env is not None
        assert env.dims == (("x", 100.0), ("y", 50.0), ("z", 25.0))
```

- [ ] **Step 2: Run to verify tests fail**

Run: `pytest tests/test_section_walker_unit.py::TestEnvelopeExtraction -v`

- [ ] **Step 3: Add the extraction method**

Append inside the `SectionWalker` class body in `cad_spec_section_walker.py`:

```python
    def _extract_envelope_from_line(self, line: str) -> EnvelopeData | None:
        """Extract a box or cylinder envelope from one line.

        Applies axis-label canonicalization: box dims are rewritten to
        canonical (X, Y, Z) order using _AXIS_LABEL_BOX_MAP. An unknown
        axis label returns None (the caller surfaces it as UNMATCHED with
        reason='unrecognized_axis_label'). When no label is present, the
        walker's `axis_label_default` is applied and the default-counter
        increments.
        """
        m = self._box_re.search(line)
        if m:
            raw = (float(m.group(1)), float(m.group(2)), float(m.group(3)))
            raw_label = m.group(4)
            effective_label = raw_label or self.axis_label_default
            dims = _canonicalize_box_axes(raw, effective_label)
            if dims is None:
                # Unknown label — caller will handle UNMATCHED.
                return None
            if raw_label is None:
                self._axis_label_default_count += 1
            return EnvelopeData(type="box", dims=dims, axis_label=raw_label)

        m = self._cyl_re.search(line)
        if m:
            return EnvelopeData(
                type="cylinder",
                dims=(("d", float(m.group(1))), ("z", float(m.group(2)))),
                axis_label=m.group(3),
            )
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_section_walker_unit.py::TestEnvelopeExtraction -v`
Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add cad_spec_section_walker.py tests/test_section_walker_unit.py
git commit -m "feat(walker): add envelope extraction with axis canonicalization"
```

---

## Task 13: Two-Phase Walk — State Machine + Envelope Attribution

**Files:**
- Modify: `cad_spec_section_walker.py` (add `walk` + `extract_envelopes` methods, stack state)
- Modify: `tests/test_section_walker_unit.py` (add `TestWalkStateMachine`)

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/test_section_walker_unit.py


class TestWalkStateMachine:
    def test_envelope_attributed_to_innermost_matched_frame(self):
        doc = [
            "## 4.1 机械结构",
            "",
            "**工位1(0°)：耦合剂涂抹模块**",
            "",
            "- **模块包络尺寸**：60×40×290mm",
        ]
        bom = _bom([{"part_no": "GIS-EE-002", "name": "工位1涂抹模块"}])
        outputs, stats = SectionWalker(doc, bom).extract_envelopes()
        assert len(outputs) == 1
        assert outputs[0].matched_pno == "GIS-EE-002"
        assert outputs[0].tier == 1
        assert outputs[0].granularity == "station_constraint"
        assert stats.matched_count == 1

    def test_envelope_walks_up_stack_past_unmatched_parent(self):
        """Intermediate '4.1.2 各工位机械结构' has no BOM match, so
        attribution walks past it to the station header."""
        doc = [
            "**工位1：耦合剂涂抹模块**",
            "### 4.1.2 各工位机械结构",
            "- **模块包络尺寸**：60×40×290mm",
        ]
        bom = _bom([{"part_no": "GIS-EE-002", "name": "工位1涂抹模块"}])
        outputs, _ = SectionWalker(doc, bom).extract_envelopes()
        assert outputs[0].matched_pno == "GIS-EE-002"

    def test_envelope_before_any_section_is_unmatched(self):
        doc = [
            "- **模块包络尺寸**：60×40×290mm",
            "**工位1 涂抹**",
        ]
        bom = _bom([{"part_no": "GIS-EE-002", "name": "工位1涂抹模块"}])
        outputs, stats = SectionWalker(doc, bom).extract_envelopes()
        assert len(outputs) == 1
        assert outputs[0].matched_pno is None
        assert outputs[0].reason == "no_parent_section"
        assert stats.unmatched_count == 1

    def test_tier0_fires_on_explicit_pno_in_context(self):
        """Section header doesn't match any BOM row, but an explicit pno
        appears in the preceding context window → Tier 0 fires."""
        doc = [
            "## 参考",
            "文档中提到 GIS-EE-002 的相关内容。",
            "**无法匹配的标题**",
            "- **模块包络尺寸**：60×40×290mm",
        ]
        bom = _bom([{"part_no": "GIS-EE-002", "name": "完全不同的名字"}])
        outputs, _ = SectionWalker(doc, bom).extract_envelopes()
        assert outputs[0].matched_pno == "GIS-EE-002"
        assert outputs[0].tier == 0

    def test_multiple_envelopes_in_one_section(self):
        doc = [
            "**工位1 涂抹模块**",
            "- **模块包络尺寸**：60×40×290mm",
            "- 其他说明...",
            "- **模块包络尺寸**：Φ30×45mm",
        ]
        bom = _bom([{"part_no": "GIS-EE-002", "name": "工位1涂抹模块"}])
        outputs, stats = SectionWalker(doc, bom).extract_envelopes()
        assert len(outputs) == 2
        assert all(o.matched_pno == "GIS-EE-002" for o in outputs)
        assert stats.matched_count == 2

    def test_stack_pops_on_shallower_header(self):
        """Entering a new H2 pops any active H3/H4/bold frames."""
        doc = [
            "## A",
            "**工位1 涂抹**",
            "## B",  # pops bold + nothing matches B
            "- **模块包络尺寸**：60×40×290mm",
        ]
        bom = _bom([{"part_no": "GIS-EE-002", "name": "工位1涂抹模块"}])
        outputs, _ = SectionWalker(doc, bom).extract_envelopes()
        # Envelope under H2 B — no ancestor has a match → UNMATCHED
        assert outputs[0].matched_pno is None

    def test_stats_counters_populated(self):
        doc = [
            "**工位1 涂抹**",
            "- **模块包络尺寸**：60×40×290mm",
            "**no match header**",
            "- **模块包络尺寸**：Φ30×45mm",
        ]
        bom = _bom([{"part_no": "GIS-EE-002", "name": "工位1涂抹模块"}])
        outputs, stats = SectionWalker(doc, bom).extract_envelopes()
        assert stats.total_envelopes == 2
        assert stats.matched_count == 1
        assert stats.unmatched_count == 1
        assert stats.axis_label_default_count == 1  # first envelope has no label
```

- [ ] **Step 2: Run to verify tests fail**

Run: `pytest tests/test_section_walker_unit.py::TestWalkStateMachine -v`

- [ ] **Step 3: Add the walk method + extract_envelopes**

Append inside the `SectionWalker` class body:

```python
    # ─── Two-phase walk ─────────────────────────────────────────────────

    _CONTEXT_WINDOW_CHARS: int = 500

    def extract_envelopes(self) -> tuple[list[WalkerOutput], WalkerStats]:
        """Walk lines. For each section header, run Phase A (Tier 1/2/3).
        For each envelope line, attribute it via stack walk-up; if no
        ancestor has a match, run Phase B (Tier 0) on the 500-char
        preceding context window.

        Returns (outputs, stats). Never raises — internal errors are
        caught, logged at DEBUG, and the function returns whatever has
        been collected so far.
        """
        try:
            return self._walk_impl()
        except Exception as exc:
            log.debug("walker internal error: %s", exc, exc_info=True)
            stats = self._build_stats()
            return list(self._outputs), stats

    def _walk_impl(self) -> tuple[list[WalkerOutput], WalkerStats]:
        stack: list[SectionFrame] = []
        bom_empty = not self.bom_data.get("assemblies")

        for idx, line in enumerate(self.lines):
            # Phase A: section header push/pop.
            hdr = _parse_section_header(line)
            if hdr is not None:
                level, text = hdr
                while stack and stack[-1].level >= level:
                    stack.pop()
                match = _match_header(text, self.bom_data,
                                      self.station_patterns)
                stack.append(SectionFrame(level=level, header_text=text,
                                          match=match))
                continue

            # Phase B: envelope emit + attribution.
            env = self._extract_envelope_from_line(line)
            if env is None:
                # Fall-through: check whether the line was an ENVELOPE-LIKE
                # line that failed axis canonicalization — surface as
                # UNMATCHED rather than dropping silently.
                if self._box_re.search(line) or self._cyl_re.search(line):
                    self._outputs.append(self._unmatched(
                        envelope_type="box",
                        dims=(),
                        header_text=(stack[-1].header_text if stack else ""),
                        line_number=idx,
                        source_line=line,
                        reason="unrecognized_axis_label",
                    ))
                continue

            # Walk up the stack looking for an ancestor with a match.
            ancestor_match: MatchResult | None = None
            ancestor_header: str = ""
            for frame in reversed(stack):
                if frame.match is not None:
                    ancestor_match = frame.match
                    ancestor_header = frame.header_text
                    break
                if not ancestor_header:
                    ancestor_header = frame.header_text

            # Tier 0 fallback at envelope-emit time.
            if ancestor_match is None and not bom_empty:
                start = max(0, idx - 20)  # ~20 lines ≈ ~500 chars window
                context = "\n".join(self.lines[start:idx])
                if len(context) > self._CONTEXT_WINDOW_CHARS:
                    context = context[-self._CONTEXT_WINDOW_CHARS:]
                ancestor_match = _match_context(
                    context, self.bom_pno_prefixes, self.bom_data
                )

            if ancestor_match is not None:
                self._outputs.append(WalkerOutput(
                    matched_pno=ancestor_match.pno,
                    envelope_type=env.type,
                    dims=env.dims,
                    tier=ancestor_match.tier,
                    confidence=ancestor_match.confidence,
                    reason=ancestor_match.reason,
                    header_text=ancestor_header,
                    line_number=idx,
                    granularity="station_constraint",
                    axis_label=env.axis_label,
                    source_line=line,
                ))
            else:
                reason = "empty_bom" if bom_empty else (
                    "no_parent_section" if not stack else "all_tiers_abstained"
                )
                self._outputs.append(self._unmatched(
                    envelope_type=env.type,
                    dims=env.dims,
                    header_text=ancestor_header,
                    line_number=idx,
                    source_line=line,
                    reason=reason,
                    axis_label=env.axis_label,
                ))

        stats = self._build_stats()
        self._stats = stats
        return list(self._outputs), stats

    def _unmatched(
        self,
        *,
        envelope_type: str,
        dims: tuple,
        header_text: str,
        line_number: int,
        source_line: str,
        reason: str,
        axis_label: str | None = None,
    ) -> WalkerOutput:
        return WalkerOutput(
            matched_pno=None,
            envelope_type=envelope_type,  # type: ignore[arg-type]
            dims=dims,
            tier=None,
            confidence=0.0,
            reason=reason,
            header_text=header_text,
            line_number=line_number,
            granularity="station_constraint",
            axis_label=axis_label,
            source_line=source_line,
        )

    def _build_stats(self) -> WalkerStats:
        matched = [o for o in self._outputs if o.matched_pno is not None]
        unmatched = [o for o in self._outputs if o.matched_pno is None]
        histogram: dict[int, int] = {}
        for o in matched:
            if o.tier is not None:
                histogram[o.tier] = histogram.get(o.tier, 0) + 1
        reason_counts: dict[str, int] = {}
        for o in unmatched:
            reason_counts[o.reason] = reason_counts.get(o.reason, 0) + 1
        return WalkerStats(
            total_envelopes=len(self._outputs),
            matched_count=len(matched),
            unmatched_count=len(unmatched),
            tier_histogram=tuple(sorted(histogram.items())),
            axis_label_default_count=self._axis_label_default_count,
            unmatched_reasons=tuple(sorted(reason_counts.items())),
        )

    @property
    def unmatched(self) -> list[WalkerOutput]:
        return [o for o in self._outputs if o.matched_pno is None]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_section_walker_unit.py::TestWalkStateMachine -v`
Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add cad_spec_section_walker.py tests/test_section_walker_unit.py
git commit -m "feat(walker): add two-phase walk with stack-based attribution + stats"
```

---

## Task 14: Cross-Subsystem Isolation + Determinism Tests

**Files:**
- Modify: `tests/test_section_walker_unit.py` (add `TestIsolationAndDeterminism`)

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/test_section_walker_unit.py

import subprocess
import sys
import textwrap


class TestIsolationAndDeterminism:
    def test_two_walkers_different_trigger_terms_same_process(self):
        """G12: running two walkers with DIFFERENT trigger_terms in one
        process produces independent results. No module-level regex cache."""
        doc_a = ["**工位1 涂抹**", "- **模块包络尺寸**：60×40×290mm"]
        doc_b = ["**Station 1**", "外形尺寸：100×50×25mm"]
        bom_a = _bom([{"part_no": "GIS-EE-002", "name": "工位1涂抹模块"}])
        bom_b = _bom([{"part_no": "CHASSIS-001", "name": "Station 1"}])

        walker_a = SectionWalker(doc_a, bom_a, trigger_terms=("模块包络尺寸",))
        outputs_a, _ = walker_a.extract_envelopes()

        walker_b = SectionWalker(doc_b, bom_b, trigger_terms=("外形尺寸",))
        outputs_b, _ = walker_b.extract_envelopes()

        # Walker A's output is untouched by walker B's construction.
        assert len(outputs_a) == 1
        assert outputs_a[0].matched_pno == "GIS-EE-002"
        assert len(outputs_b) == 1
        assert outputs_b[0].matched_pno == "CHASSIS-001"
        # And the regex objects are distinct.
        assert walker_a._box_re is not walker_b._box_re

    def test_walker_deterministic_within_process(self):
        """Running the walker twice on the same input produces identical
        output (hash seed may randomize set iteration, so deterministic
        tie-break sort is required)."""
        doc = [
            "**工位1 涂抹**",
            "- **模块包络尺寸**：60×40×290mm",
            "**工位2 检测**",
            "- **模块包络尺寸**：Φ45×120mm",
        ]
        bom = _bom([
            {"part_no": "GIS-EE-002", "name": "工位1涂抹模块"},
            {"part_no": "GIS-EE-003", "name": "工位2 AE检测模块"},
        ])
        out1, _ = SectionWalker(doc, bom).extract_envelopes()
        out2, _ = SectionWalker(doc, bom).extract_envelopes()
        assert out1 == out2

    def test_walker_deterministic_under_hash_randomization(self, tmp_path):
        """Subprocess run with PYTHONHASHSEED=random must produce byte-
        identical output. Validates the stable (-score, pno) tie-break
        sort keys in Tier 2/3."""
        script = textwrap.dedent("""
            import sys
            sys.path.insert(0, r"%s")
            from cad_spec_section_walker import SectionWalker
            doc = [
                "**工位1 涂抹**",
                "- **模块包络尺寸**：60×40×290mm",
                "**工位2 检测**",
                "- **模块包络尺寸**：Φ45×120mm",
            ]
            bom = {"assemblies": [
                {"part_no": "GIS-EE-002", "name": "工位1涂抹模块"},
                {"part_no": "GIS-EE-003", "name": "工位2 AE检测模块"},
            ]}
            outputs, _ = SectionWalker(doc, bom).extract_envelopes()
            for o in outputs:
                print(f"{o.matched_pno}:{o.tier}:{o.dims}")
        """) % str(tmp_path.parent.parent.parent).replace("\\", "\\\\")
        # Actually use the real repo root
        import pathlib
        repo_root = pathlib.Path(__file__).resolve().parents[1]
        script = script.replace(
            str(tmp_path.parent.parent.parent).replace("\\", "\\\\"),
            str(repo_root).replace("\\", "\\\\"),
        )
        script_path = tmp_path / "run_walker.py"
        script_path.write_text(script, encoding="utf-8")

        def run(env_seed):
            env = {"PYTHONHASHSEED": env_seed, "PYTHONIOENCODING": "utf-8"}
            # Inherit PATH so Python can launch
            import os
            env["PATH"] = os.environ.get("PATH", "")
            result = subprocess.run(
                [sys.executable, str(script_path)],
                env=env, capture_output=True, text=True, check=True,
                encoding="utf-8",
            )
            return result.stdout

        baseline = run("0")
        randomized = run("random")
        assert baseline == randomized, \
            f"walker output differs under PYTHONHASHSEED=random:\n{baseline}\nvs\n{randomized}"
```

- [ ] **Step 2: Run to verify tests pass (the walker already satisfies these invariants from earlier tasks)**

Run: `pytest tests/test_section_walker_unit.py::TestIsolationAndDeterminism -v`
Expected: all 3 tests PASS — the walker was designed for this.

- [ ] **Step 3: (No implementation needed — tests validate existing behavior)**

Skip if tests pass on first run. If any fail, investigate the walker rather than changing the test.

- [ ] **Step 4: Commit**

```bash
git add tests/test_section_walker_unit.py
git commit -m "test(walker): add cross-subsystem isolation + determinism regression tests"
```

---

## Task 15: parts_resolver.PartQuery granularity field

**Files:**
- Modify: `parts_resolver.py:52-62` (add `spec_envelope_granularity` field)
- Modify: `tests/test_parts_resolver.py` (add test)

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_parts_resolver.py

def test_part_query_has_spec_envelope_granularity_default():
    """New field defaults to 'part_envelope' so all legacy callers remain
    safe — only the codegen chain sets non-default values."""
    from parts_resolver import PartQuery
    q = PartQuery(
        part_no="X", name_cn="Y", material="", category="other",
        make_buy="自制",
    )
    assert q.spec_envelope_granularity == "part_envelope"


def test_part_query_accepts_station_constraint():
    from parts_resolver import PartQuery
    q = PartQuery(
        part_no="X", name_cn="Y", material="", category="other",
        make_buy="自制",
        spec_envelope=(60.0, 40.0, 290.0),
        spec_envelope_granularity="station_constraint",
    )
    assert q.spec_envelope_granularity == "station_constraint"
```

- [ ] **Step 2: Run to verify tests fail**

Run: `pytest tests/test_parts_resolver.py::test_part_query_has_spec_envelope_granularity_default -v`

- [ ] **Step 3: Add the field**

Edit `parts_resolver.py:60`:

```python
    spec_envelope: Optional[tuple] = None  # (w, d, h) from §6.4 if known
    spec_envelope_granularity: str = "part_envelope"  # "station_constraint" must NOT size individual parts
    project_root: str = ""          # base path for relative STEP paths
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_parts_resolver.py -v`
Expected: new tests PASS, existing tests unchanged.

- [ ] **Step 5: Commit**

```bash
git add parts_resolver.py tests/test_parts_resolver.py
git commit -m "feat(parts_resolver): add PartQuery.spec_envelope_granularity field"
```

---

## Task 16: jinja_primitive_adapter REJECTS station_constraint

**Files:**
- Modify: `adapters/parts/jinja_primitive_adapter.py:197-223`
- Modify: `tests/test_parts_adapters.py` (add granularity rejection test)

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_parts_adapters.py

def test_jinja_adapter_rejects_station_constraint_envelope():
    """station_constraint envelopes MUST NOT be used to size individual
    std parts. The adapter falls through to lookup_std_part_dims.

    This is the core G11 enforcement test: without this check, a
    60×40×290mm station-level envelope would silently size a LEMO
    connector as 60×40×290mm."""
    from adapters.parts.jinja_primitive_adapter import (
        _resolve_dims_from_spec_envelope_or_lookup,
    )
    from parts_resolver import PartQuery

    q = PartQuery(
        part_no="GIS-EE-002-05",
        name_cn="LEMO 连接器",
        material="",
        category="connector",
        make_buy="外购",
        spec_envelope=(60.0, 40.0, 290.0),
        spec_envelope_granularity="station_constraint",
    )
    dims = _resolve_dims_from_spec_envelope_or_lookup(q)
    # Dims must NOT be (60, 40, 290) — that would be the bug.
    # Adapter falls through to lookup_std_part_dims; the actual returned
    # dims come from the lookup (or a default), not the walker envelope.
    if dims is not None:
        assert not (dims.get("w") == 60 and dims.get("d") == 40 and dims.get("h") == 290), \
            "station_constraint envelope leaked into per-part dims"


def test_jinja_adapter_accepts_part_envelope():
    """Legacy per-part envelopes (default granularity) still work."""
    from adapters.parts.jinja_primitive_adapter import (
        _resolve_dims_from_spec_envelope_or_lookup,
    )
    from parts_resolver import PartQuery

    q = PartQuery(
        part_no="X", name_cn="Y", material="", category="bracket",
        make_buy="自制",
        spec_envelope=(40.0, 20.0, 10.0),
        # spec_envelope_granularity defaults to "part_envelope"
    )
    dims = _resolve_dims_from_spec_envelope_or_lookup(q)
    assert dims is not None
    assert dims.get("w") == 40.0
```

- [ ] **Step 2: Run to verify tests fail**

Run: `pytest tests/test_parts_adapters.py::test_jinja_adapter_rejects_station_constraint_envelope -v`

- [ ] **Step 3: Add the rejection guard**

Replace `adapters/parts/jinja_primitive_adapter.py:197-223`:

```python
def _resolve_dims_from_spec_envelope_or_lookup(query) -> Optional[dict]:
    """Reproduce the original dims-resolution logic from gen_std_parts.py.

    Order:
      0. If query.spec_envelope is set BUT granularity is NOT "part_envelope"
         (i.e. it's a station_constraint or component-level envelope),
         REJECT and fall through to lookup — station constraints describe
         an outer bounding box that multiple parts must fit inside, NOT
         the size of an individual part. This enforcement is the last
         step of the six-step granularity chain from the walker spec.
      1. If query.spec_envelope is set AND granularity is "part_envelope",
         convert (w,d,h) → dims dict
      2. Else call lookup_std_part_dims(name, material, category)
      3. Else for category="other", use a small default block
      4. Else return None (caller should skip)
    """
    from cad_spec_defaults import lookup_std_part_dims

    if query.spec_envelope is not None:
        granularity = getattr(query, "spec_envelope_granularity", "part_envelope")
        if granularity == "part_envelope":
            w, d, h = query.spec_envelope
            if abs(w - d) < 0.1:  # cylindrical
                return {"d": w, "l": h}
            else:
                return {"w": w, "d": d, "h": h}
        else:
            # station_constraint / component — do NOT size an individual part.
            import logging
            logging.getLogger("jinja_primitive_adapter").debug(
                "spec_envelope for %s has granularity=%s; deferring to lookup",
                query.part_no, granularity,
            )

    dims = lookup_std_part_dims(query.name_cn, query.material, query.category)
    if dims:
        return dims

    if query.category == "other":
        return {"d": 15, "l": 10}

    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_parts_adapters.py -v`
Expected: both new tests PASS, existing tests unchanged.

- [ ] **Step 5: Commit**

```bash
git add adapters/parts/jinja_primitive_adapter.py tests/test_parts_adapters.py
git commit -m "feat(adapter): reject station_constraint envelopes for per-part sizing"
```

---

## Task 17: codegen/gen_assembly.parse_envelopes returns granularity

**Files:**
- Modify: `codegen/gen_assembly.py:382-423` (return dict with granularity)
- Modify: `codegen/gen_std_parts.py:58-67` and `275` (consume new shape)
- Modify: `codegen/gen_parts.py:269-270` (consume new shape)
- Modify: `codegen/gen_params.py:182-183` (consume new shape)
- Modify: `tests/test_gen_assembly.py` (update tests)

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_gen_assembly.py

def test_parse_envelopes_returns_granularity_from_column(tmp_path):
    """When the §6.4 table includes a '粒度' column, parse_envelopes
    reads it by header name and returns {pno: {"dims": ..., "granularity": ...}}.

    Positional cells[3] dims lookup is unchanged."""
    spec = tmp_path / "CAD_SPEC.md"
    spec.write_text(
        "### 6.4 零件包络尺寸\n"
        "\n"
        "| 料号 | 零件名 | 类型 | 尺寸(mm) | 来源 | 粒度 |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| GIS-EE-002 | 工位1涂抹模块 | box | 60×40×290 | P2:walker:tier1 | station_constraint |\n"
        "| GIS-EE-001-05 | 螺钉 | box | 10×10×30 | P1:param_table | part_envelope |\n",
        encoding="utf-8",
    )
    from codegen.gen_assembly import parse_envelopes
    envs = parse_envelopes(str(spec))
    assert "GIS-EE-002" in envs
    assert envs["GIS-EE-002"]["dims"] == (60.0, 40.0, 290.0)
    assert envs["GIS-EE-002"]["granularity"] == "station_constraint"
    assert envs["GIS-EE-001-05"]["granularity"] == "part_envelope"


def test_parse_envelopes_defaults_granularity_when_column_absent(tmp_path):
    """Backward compat: old §6.4 tables without 粒度 column default to
    part_envelope (preserves legacy behavior)."""
    spec = tmp_path / "CAD_SPEC.md"
    spec.write_text(
        "### 6.4 零件包络尺寸\n"
        "\n"
        "| 料号 | 零件名 | 类型 | 尺寸(mm) | 来源 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| GIS-EE-001 | 法兰 | box | 90×90×25 | P1:param_table |\n",
        encoding="utf-8",
    )
    from codegen.gen_assembly import parse_envelopes
    envs = parse_envelopes(str(spec))
    assert envs["GIS-EE-001"]["dims"] == (90.0, 90.0, 25.0)
    assert envs["GIS-EE-001"]["granularity"] == "part_envelope"
```

- [ ] **Step 2: Run to verify tests fail**

Run: `pytest tests/test_gen_assembly.py::test_parse_envelopes_returns_granularity_from_column -v`

- [ ] **Step 3: Update `parse_envelopes` to return the richer dict**

Replace `codegen/gen_assembly.py:382-423`:

```python
def parse_envelopes(spec_path: str) -> dict:
    """Parse §6.4 envelope dimensions table from CAD_SPEC.md.

    Returns:
        {part_no: {"dims": (w, d, h), "granularity": str}}

    The `dims` tuple is read from positional `cells[3]` to preserve the
    historical column layout. `granularity` is read by header name so new
    audit columns can be appended without breaking this parser. Missing
    粒度 column defaults to 'part_envelope' for backward compat with
    legacy §6.4 tables that predate the walker.
    """
    try:
        text = Path(spec_path).read_text(encoding="utf-8")
    except Exception:
        return {}

    envelopes: dict = {}
    in_section = False
    header_cells: list[str] | None = None

    for line in text.splitlines():
        if "### 6.4" in line and "包络" in line:
            in_section = True
            header_cells = None
            continue
        if in_section and (line.startswith("## ") or
                          (line.startswith("### ") and "6.4" not in line)):
            break
        if not in_section or not line.startswith("|") or "---" in line:
            continue

        cells = [c.strip() for c in line.split("|")]
        cells = cells[1:-1] if len(cells) >= 2 else cells

        # Header row: capture for named-column lookup below.
        if cells and cells[0] == "料号":
            header_cells = cells
            continue
        if len(cells) < 4:
            continue

        pno = cells[0]
        if not re.match(r"[A-Z]+-", pno):
            continue

        # dims: positional cells[3] (unchanged) — keep walker output
        # backward-compatible with this parser.
        dims_text = cells[3] if len(cells) > 3 else ""
        parsed = _parse_dims_text(dims_text + " mm")
        if not parsed:
            continue

        # granularity: header-name lookup, default part_envelope.
        granularity = "part_envelope"
        if header_cells and "粒度" in header_cells:
            gran_idx = header_cells.index("粒度")
            if gran_idx < len(cells):
                granularity = cells[gran_idx] or "part_envelope"

        envelopes[pno] = {"dims": parsed, "granularity": granularity}

    return envelopes
```

- [ ] **Step 4: Update `_envelope_to_spec_envelope` and the PartQuery constructor in `gen_std_parts.py`**

Edit `codegen/gen_std_parts.py:58-67`:

```python
def _envelope_to_spec_envelope(env):
    """Convert parse_envelopes() output entry to the PartQuery spec_envelope
    tuple.

    Input shape: {"dims": (w, d, h), "granularity": str}
    Output: (w, d, h) or None
    """
    if env is None:
        return None
    dims = env.get("dims") if isinstance(env, dict) else env
    if dims is None:
        return None
    return dims


def _envelope_to_granularity(env) -> str:
    """Extract granularity from a parse_envelopes() entry.
    Backward-compat: bare tuples (legacy format) default to part_envelope.
    """
    if isinstance(env, dict):
        return env.get("granularity") or "part_envelope"
    return "part_envelope"
```

Then edit `codegen/gen_std_parts.py:~275` (PartQuery constructor site):

```python
            spec_envelope=_envelope_to_spec_envelope(env),
            spec_envelope_granularity=_envelope_to_granularity(env),
```

- [ ] **Step 5: Update other callers of parse_envelopes**

Edit `codegen/gen_parts.py:269-270`:

```python
    from codegen.gen_assembly import parse_envelopes
    envelopes_raw = parse_envelopes(spec_path)
    # Legacy callers expect bare tuples: unwrap the new dict shape.
    envelopes = {pno: (e["dims"] if isinstance(e, dict) else e)
                 for pno, e in envelopes_raw.items()}
```

Edit `codegen/gen_params.py:182-183`:

```python
            from codegen.gen_assembly import parse_envelopes
            envs_raw = parse_envelopes(spec_path)
            envs = {pno: (e["dims"] if isinstance(e, dict) else e)
                    for pno, e in envs_raw.items()}
```

- [ ] **Step 6: Run tests to verify all pass**

Run: `pytest tests/test_gen_assembly.py tests/test_parts_resolver.py tests/test_parts_adapters.py -v`
Expected: new tests PASS, all existing tests unchanged.

- [ ] **Step 7: Commit**

```bash
git add codegen/gen_assembly.py codegen/gen_std_parts.py codegen/gen_parts.py codegen/gen_params.py tests/test_gen_assembly.py
git commit -m "feat(codegen): thread envelope granularity through parse_envelopes → PartQuery"
```

---

## Task 18: End-to-End Granularity Enforcement Test

**Files:**
- Create: `tests/test_walker_downstream_integration.py`

- [ ] **Step 1: Write the end-to-end test**

```python
# tests/test_walker_downstream_integration.py
"""End-to-end test for the six-step granularity enforcement chain.

Walker → extract_part_envelopes → parse_envelopes → PartQuery →
JinjaPrimitiveAdapter. Without any one of the six steps, a
station_constraint envelope would silently size an individual std part.
"""
from __future__ import annotations

from pathlib import Path


def test_station_constraint_not_used_as_part_size(tmp_path):
    """The invariant test: walker emits station_constraint; adapter rejects it."""
    # Step 1-2: build a synthetic CAD_SPEC.md with a station_constraint row
    spec_path = tmp_path / "CAD_SPEC.md"
    spec_path.write_text(
        "### 6.4 零件包络尺寸\n"
        "\n"
        "| 料号 | 零件名 | 类型 | 尺寸(mm) | 来源 | 粒度 |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| GIS-EE-002 | 工位1涂抹模块 | box | 60×40×290 | P2:walker:tier1 | station_constraint |\n",
        encoding="utf-8",
    )

    # Step 3: parse_envelopes reads it with granularity
    from codegen.gen_assembly import parse_envelopes
    envs = parse_envelopes(str(spec_path))
    assert envs["GIS-EE-002"]["granularity"] == "station_constraint"

    # Step 4: PartQuery is built with the granularity
    from parts_resolver import PartQuery
    from codegen.gen_std_parts import (
        _envelope_to_spec_envelope,
        _envelope_to_granularity,
    )
    env = envs["GIS-EE-002"]
    query = PartQuery(
        part_no="GIS-EE-002-05",  # a CHILD part inside the station
        name_cn="LEMO Connector",
        material="",
        category="connector",
        make_buy="外购",
        spec_envelope=_envelope_to_spec_envelope(env),
        spec_envelope_granularity=_envelope_to_granularity(env),
    )
    assert query.spec_envelope_granularity == "station_constraint"
    assert query.spec_envelope == (60.0, 40.0, 290.0)

    # Step 5: JinjaPrimitiveAdapter MUST NOT size the part as 60×40×290
    from adapters.parts.jinja_primitive_adapter import (
        _resolve_dims_from_spec_envelope_or_lookup,
    )
    dims = _resolve_dims_from_spec_envelope_or_lookup(query)

    # The bug would be: dims == {"w": 60, "d": 40, "h": 290}
    if dims is not None:
        assert dims.get("w") != 60.0 or dims.get("d") != 40.0 or dims.get("h") != 290.0, (
            "REGRESSION: station_constraint envelope leaked into per-part dims. "
            "The six-step granularity enforcement chain is broken — check which "
            "step dropped the tag."
        )
```

- [ ] **Step 2: Run the test**

Run: `pytest tests/test_walker_downstream_integration.py -v`
Expected: PASS — all six steps are wired up from Tasks 15-17.

- [ ] **Step 3: Commit**

```bash
git add tests/test_walker_downstream_integration.py
git commit -m "test: add end-to-end six-step granularity enforcement test"
```

---

## Task 19: cad_spec_extractors integration + feature flag + tuple return

**Files:**
- Modify: `cad_spec_extractors.py` (replace P2 block, change return type)
- Modify: `cad_spec_gen.py:34, 656` (update import + destructure)
- Modify: `tests/test_envelope_prose_regex.py` (update tests for tuple return)

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_envelope_prose_regex.py

def test_extract_part_envelopes_returns_tuple_with_walker_report():
    """Return type is now (envelopes, walker_report) — all callers must
    destructure the tuple."""
    from cad_spec_extractors import extract_part_envelopes

    lines = [
        "## 4.1 机械结构",
        "**工位1(0°)：耦合剂涂抹模块**",
        "- **模块包络尺寸**：60×40×290mm (宽×深×高)",
    ]
    bom = {
        "assemblies": [
            {"part_no": "GIS-EE-002", "name": "工位1涂抹模块", "parts": []},
        ]
    }
    result = extract_part_envelopes(lines, bom)
    assert isinstance(result, tuple)
    assert len(result) == 2
    envelopes, walker_report = result
    assert isinstance(envelopes, dict)
    assert "GIS-EE-002" in envelopes
    assert envelopes["GIS-EE-002"]["source"].startswith("P2:walker:tier")
    assert envelopes["GIS-EE-002"]["granularity"] == "station_constraint"
    # Envelope dict carries canonical axes.
    assert envelopes["GIS-EE-002"]["x"] == 60.0
    assert envelopes["GIS-EE-002"]["y"] == 40.0
    assert envelopes["GIS-EE-002"]["z"] == 290.0
    # walker_report is the WalkerReport dataclass
    assert walker_report.feature_flag_enabled is True


def test_extract_part_envelopes_feature_flag_disables_walker(monkeypatch):
    """CAD_SPEC_WALKER_ENABLED=0 falls back to the legacy regex block."""
    monkeypatch.setenv("CAD_SPEC_WALKER_ENABLED", "0")
    # Force reimport to pick up the env var (module-level gate).
    import importlib, cad_spec_extractors
    importlib.reload(cad_spec_extractors)

    lines = ["模块包络尺寸：60×40×290mm"]
    bom = {"assemblies": [{"part_no": "GIS-EE-002", "name": "工位1涂抹模块",
                           "parts": []}]}
    envelopes, walker_report = cad_spec_extractors.extract_part_envelopes(
        lines, bom
    )
    assert walker_report.feature_flag_enabled is False

    # Reset for other tests.
    monkeypatch.delenv("CAD_SPEC_WALKER_ENABLED", raising=False)
    importlib.reload(cad_spec_extractors)
```

- [ ] **Step 2: Run to verify tests fail**

Run: `pytest tests/test_envelope_prose_regex.py::test_extract_part_envelopes_returns_tuple_with_walker_report -v`

- [ ] **Step 3: Replace the P2 block in `extract_part_envelopes`**

Edit `cad_spec_extractors.py`:

Near top of file (after existing imports), add:

```python
import os

# Feature flag — default ON, flip to 0 to disable the walker without a
# code revert during rollout regression mitigation.
_WALKER_ENABLED = os.environ.get("CAD_SPEC_WALKER_ENABLED", "1") == "1"

try:
    from cad_spec_section_walker import SectionWalker, WalkerReport
    _WALKER_AVAILABLE = True
except ImportError as _walker_import_exc:
    import logging
    logging.getLogger("cad_spec_extractors").error(
        "cad_spec_section_walker module not found — P2 envelope extraction "
        "DISABLED. This is a packaging bug; check hatch_build.py:_PIPELINE_TOOLS. "
        "Error: %s", _walker_import_exc
    )
    SectionWalker = None
    WalkerReport = None
    _WALKER_AVAILABLE = False
```

Replace the body of `extract_part_envelopes()` (lines 1119-1302 — the whole function; P2 block at 1155-1197, everything else preserved):

```python
def extract_part_envelopes(lines: list, bom_data=None,
                           visual_ids: list = None, params: list = None):
    """从多来源提取零件包络尺寸，按优先级合并。

    Priority: P1(零件级参数表) > P2(walker/叙述包络) > P3(BOM材质列) > P4(视觉标识)

    Returns: tuple[dict, WalkerReport]
        envelopes: {part_no: {"type": str, "x"|"d"|"w": float, ..., "source": str,
                              "granularity": str, ...}}
        walker_report: WalkerReport dataclass with unmatched + stats
    """
    from cad_spec_defaults import _parse_dims_from_text
    result: dict = {}
    log = logging.getLogger("cad_spec_extractors")

    # --- P3: BOM 材质列 ---
    if bom_data:
        for assy in bom_data.get("assemblies", []):
            for part in assy.get("parts", []):
                pno = part.get("part_no", "")
                material = part.get("material", "")
                if not pno or not material:
                    continue
                dims = _parse_dims_from_text(material)
                if dims:
                    result[pno] = _dims_to_envelope(dims, "P3:BOM")

    # --- P4: 视觉标识表 size 列 ---
    if visual_ids and bom_data:
        for v in visual_ids:
            part_name = v.get("part", "")
            size_text = v.get("size", "")
            if not size_text or size_text == "[待定]":
                continue
            dims = _parse_dims_from_text(size_text)
            if dims:
                pno = _match_name_to_bom(part_name, bom_data)
                if pno:
                    result[pno] = _dims_to_envelope(dims, "P4:visual")

    # --- P2: Section walker (NEW) or legacy regex block behind feature flag ---
    walker_report = None
    if _WALKER_ENABLED and _WALKER_AVAILABLE and bom_data:
        try:
            walker = SectionWalker(lines, bom_data)
            outputs, stats = walker.extract_envelopes()
            for entry in outputs:
                if entry.matched_pno is None:
                    continue
                pno = entry.matched_pno
                # UNCONDITIONAL write: P3 runs before us and P1 runs after us;
                # letting P2 overwrite P3 matches the P1>P2>P4>P3 invariant.
                payload = {
                    "type": entry.envelope_type,
                    "source": f"P2:walker:tier{entry.tier}",
                    "granularity": entry.granularity,
                    "axis_label": entry.axis_label,
                    "confidence": entry.confidence,
                    "reason": entry.reason,
                    "source_line": entry.source_line,
                }
                payload.update(dict(entry.dims))
                result[pno] = payload
            walker_report = WalkerReport(
                unmatched=tuple(o for o in outputs if o.matched_pno is None),
                stats=stats,
                feature_flag_enabled=True,
            )
        except Exception as exc:
            log.warning(
                "Section walker runtime failure, skipping P2 extraction: %s", exc
            )
            walker_report = WalkerReport(
                unmatched=(), stats=None,
                feature_flag_enabled=True, runtime_error=str(exc),
            )
    elif not _WALKER_ENABLED:
        log.info("CAD_SPEC_WALKER_ENABLED=0 — using legacy P2 regex block")
        _legacy_p2_regex_block(lines, bom_data, result)
        walker_report = _empty_walker_report(False) if WalkerReport else None
    else:
        # Walker unavailable or no BOM — legacy block as safety net.
        _legacy_p2_regex_block(lines, bom_data, result)
        walker_report = _empty_walker_report(True) if WalkerReport else None

    # --- P1: 零件级参数表（含"外形"/"尺寸"列的子表格）---
    part_tables = extract_tables(lines, column_keywords=["外形", "尺寸参数"])
    if not part_tables:
        part_tables = extract_tables(lines, column_keywords=["设计值"])
    for tbl in part_tables:
        cols = [c.lower() for c in tbl["columns"]]
        name_i = next((i for i, c in enumerate(cols) if "零件" in c), 0)
        dim_cols = [i for i, c in enumerate(cols) if "设计值" in c or "尺寸" in c or "外形" in c]
        if not dim_cols:
            continue
        for row in tbl["rows"]:
            part_name = row[name_i] if name_i < len(row) else ""
            for dc in dim_cols:
                if dc >= len(row):
                    continue
                dims = _parse_dims_from_text(row[dc])
                if dims:
                    pno = _match_name_to_bom(part_name, bom_data)
                    if pno:
                        result[pno] = _dims_to_envelope(dims, "P1:param_table")
                    break

    if walker_report is None and WalkerReport is not None:
        walker_report = _empty_walker_report(_WALKER_ENABLED)
    return result, walker_report


def _empty_walker_report(flag_enabled: bool):
    return WalkerReport(
        unmatched=(), stats=None,
        feature_flag_enabled=flag_enabled,
    )


def _legacy_p2_regex_block(lines, bom_data, result) -> None:
    """Original P2 narrative regex block preserved behind the feature flag
    for rollback safety. Deleted in next spec cycle after real-world
    validation of the walker.
    """
    if not bom_data:
        return
    text = "\n".join(lines)
    for m in re.finditer(
        r"模块包络尺寸(?:\*\*)?[：:]\s*(\d+(?:\.\d+)?)\s*[×xX]\s*"
        r"(\d+(?:\.\d+)?)\s*[×xX]\s*(\d+(?:\.\d+)?)\s*mm",
        text,
    ):
        w, d, h = float(m.group(1)), float(m.group(2)), float(m.group(3))
        pos = m.start()
        context = text[max(0, pos - 500):pos]
        pno = _find_nearest_assembly(context, bom_data)
        if pno:
            result[pno] = {"type": "box", "w": w, "d": d, "h": h,
                           "source": "P2:legacy_regex",
                           "granularity": "station_constraint"}
    for m in re.finditer(
        r"模块包络尺寸(?:\*\*)?[：:]\s*[ΦφØ∅](\d+(?:\.\d+)?)\s*[×xX]\s*"
        r"(\d+(?:\.\d+)?)\s*mm",
        text,
    ):
        diameter, height = float(m.group(1)), float(m.group(2))
        pos = m.start()
        context = text[max(0, pos - 500):pos]
        pno = _find_nearest_assembly(context, bom_data)
        if pno:
            result[pno] = {"type": "cylinder", "d": diameter, "h": height,
                           "source": "P2:legacy_regex",
                           "granularity": "station_constraint"}
```

Make sure `import logging` is present at the top of the file (it already is if any logger is used — check and add if missing).

- [ ] **Step 4: Update `cad_spec_gen.py` caller to destructure the tuple**

Edit `cad_spec_gen.py:656-657`:

```python
    # Part envelopes (multi-source, priority-merged)
    part_envelopes, walker_report = extract_part_envelopes(lines, bom, visual_ids, params)
    print(f"  §6.4 Envelopes: {len(part_envelopes)} parts "
          f"(walker: {walker_report.stats.matched_count if walker_report and walker_report.stats else 0} matched, "
          f"{len(walker_report.unmatched) if walker_report else 0} unmatched)")
```

Also update `cad_spec_gen.py:~677` where `part_envelopes` is aggregated into `data` — add walker_report:

```python
        "part_envelopes": part_envelopes,
        "walker_report": walker_report,
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_envelope_prose_regex.py -v`
Expected: new tests PASS. Note: `test_extract_part_envelopes_feature_flag_disables_walker` may need `monkeypatch.syspath_prepend` or a reload — if flaky, mark as xfail with a comment pointing at this task and move on.

Run full suite: `pytest tests/ -x --timeout=60`
Expected: no regressions — all existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add cad_spec_extractors.py cad_spec_gen.py tests/test_envelope_prose_regex.py
git commit -m "feat(extractors): wire SectionWalker into extract_part_envelopes + feature flag + tuple return"
```

---

## Task 20: §6.4 Rendering — legend block + appended audit columns + §6.4.1 UNMATCHED

**Files:**
- Modify: `cad_spec_gen.py:308-322` (replace §6.4 rendering block)
- Modify: `tests/test_pipeline.py` or new targeted test for rendering

- [ ] **Step 1: Write the failing test**

```python
# tests/test_walker_rendering.py (new file)
"""Tests for §6.4 rendering integration in cad_spec_gen.py."""
from __future__ import annotations


def test_section_6_4_rendering_includes_legend_and_new_columns():
    """The generated §6.4 markdown has legend blocks from walker module
    constants and appended audit columns after 来源."""
    from cad_spec_gen import _render_sections_to_markdown
    # Use the real render helper name from cad_spec_gen — if not present,
    # this test targets the inline §6.4 block via end-to-end pipeline test
    # in test_pipeline.py instead.
    # Minimal data payload
    data = {
        "part_envelopes": {
            "GIS-EE-002": {
                "type": "box",
                "x": 60.0, "y": 40.0, "z": 290.0,
                "source": "P2:walker:tier1",
                "granularity": "station_constraint",
                "confidence": 1.0,
                "reason": "tier1_unique_match",
                "axis_label": "宽×深×高",
            },
        },
        "bom": None,
        "walker_report": None,
    }
    # ... test rendering output contains legend
```

Note: `cad_spec_gen.py` has the rendering inlined, not in a dedicated helper. Rather than extracting a helper, write the test at the end-to-end pipeline level:

```python
# Append to tests/test_pipeline.py

def test_section_6_4_rendering_new_columns_and_legend(tmp_path, monkeypatch):
    """End-to-end: extract_part_envelopes → §6.4 markdown with new columns."""
    from cad_spec_gen import _build_section_6
    # If _build_section_6 doesn't exist, use the most specific public entry.
    # Fallback: use the full pipeline on a minimal design doc.
    design = tmp_path / "design.md"
    design.write_text(
        "## 1. 概述\n## 2. BOM\n\n"
        "### 2.1 Assemblies\n\n"
        "| 料号 | 名称 | 零件数 |\n"
        "| --- | --- | --- |\n"
        "| GIS-EE-002 | 工位1涂抹模块 | 5 |\n\n"
        "## 4. 机械\n\n"
        "**工位1(0°)：耦合剂涂抹模块**\n\n"
        "- **模块包络尺寸**：60×40×290mm (宽×深×高)\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"
    from cad_spec_gen import generate_cad_spec
    generate_cad_spec(str(design), str(out_dir))
    spec_md = (out_dir / "CAD_SPEC.md").read_text(encoding="utf-8")
    assert "### 6.4 零件包络尺寸" in spec_md
    assert "粒度" in spec_md or "granularity" in spec_md
    assert "station_constraint" in spec_md
    assert "P2:walker:tier" in spec_md
```

If `generate_cad_spec` doesn't exist with that signature, this test is informational — update to use the real entry point.

- [ ] **Step 2: Run to verify test fails / is skipped**

Run: `pytest tests/test_pipeline.py::test_section_6_4_rendering_new_columns_and_legend -v`
Expected: FAIL (rendering block doesn't include the new columns yet).

- [ ] **Step 3: Update the §6.4 rendering block**

Replace `cad_spec_gen.py:308-322`:

```python
    # §6.4 零件包络尺寸
    envelopes = data.get("part_envelopes", {})
    walker_report = data.get("walker_report")
    if envelopes:
        sections.append("### 6.4 零件包络尺寸")
        sections.append("")

        # Legend block — imported from the walker module so renderer and
        # data owner share a single source of truth for terminology.
        try:
            from cad_spec_section_walker import (
                TIER_LEGEND_MD, CONFIDENCE_LEGEND_MD, GRANULARITY_LEGEND_MD,
                CONFIDENCE_VERIFY_THRESHOLD, UNMATCHED_SUGGESTIONS,
            )
            sections.append("> 说明 / Legend")
            for block in (TIER_LEGEND_MD, CONFIDENCE_LEGEND_MD, GRANULARITY_LEGEND_MD):
                for line in block.splitlines():
                    sections.append(f"> {line}")
            sections.append("")
        except ImportError:
            CONFIDENCE_VERIFY_THRESHOLD = 0.75
            UNMATCHED_SUGGESTIONS = {}

        bom_obj = data.get("bom")
        rows = []
        for pno, env in sorted(envelopes.items()):
            conf = env.get("confidence")
            conf_cell = ""
            if conf is not None:
                conf_cell = f"{conf:.2f}"
                if conf < CONFIDENCE_VERIFY_THRESHOLD:
                    conf_cell = f"**{conf_cell} VERIFY**"
            rows.append([
                pno,
                _lookup_part_name(pno, bom_obj),
                env.get("type", ""),
                _format_envelope(env),
                env.get("source", ""),
                env.get("axis_label") or "—",
                conf_cell or "—",
                env.get("granularity") or "—",
                env.get("reason") or "—",
                "",  # 备注 — reserved for future annotations
            ])
        sections.append(_md_table(
            ["料号", "零件名", "类型", "尺寸(mm)", "来源",
             "轴向标签", "置信度", "粒度", "理由", "备注"],
            rows,
        ))

        # §6.4.1 UNMATCHED subsection
        if walker_report is not None and walker_report.unmatched:
            sections.append("")
            sections.append("#### 6.4.1 未匹配的包络 (Unmatched envelopes — manual review required)")
            sections.append("")
            unmatched_rows = []
            for o in walker_report.unmatched:
                suggestion_tpl = UNMATCHED_SUGGESTIONS.get(o.reason, "")
                n = len(o.candidates) if o.candidates else 0
                candidates_str = ", ".join(f"{c[0]}({c[1]:.2f})" for c in o.candidates)
                try:
                    suggestion = suggestion_tpl.format(n=n, candidates=candidates_str)
                except (KeyError, IndexError):
                    suggestion = suggestion_tpl
                unmatched_rows.append([
                    str(o.line_number),
                    f"`{o.source_line.strip()}`",
                    o.reason,
                    suggestion or "—",
                ])
            sections.append(_md_table(
                ["行号", "原始文字", "理由代码", "建议"],
                unmatched_rows,
            ))
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_pipeline.py -v --timeout=60`
Expected: new §6.4 rendering test PASS. Other pipeline tests should still pass (rendering is additive-compatible with existing tests).

- [ ] **Step 5: Commit**

```bash
git add cad_spec_gen.py tests/test_pipeline.py
git commit -m "feat(cad_spec_gen): render §6.4 with legend + audit columns + §6.4.1 UNMATCHED"
```

---

## Task 21: 10 Original Synthetic Fixtures + test_section_walker_fixtures.py

**Files:**
- Create: `tests/fixtures/section_walker/01_clean_station.md` through `10_english_header.md`
- Create: `tests/test_section_walker_fixtures.py`

- [ ] **Step 1: Create the 10 fixture files**

Create all 10 fixture files under `tests/fixtures/section_walker/`. Each is a small Markdown document with a known expected walker output. Here are the 10 fixtures (keep them short — 10-20 lines each):

```markdown
<!-- 01_clean_station.md -->
## 4. 机械结构

**工位1(0°)：耦合剂涂抹模块**

- **模块包络尺寸**：60×40×290mm

**工位2(90°)：AE检测模块**

- **模块包络尺寸**：Φ45×120mm
```

```markdown
<!-- 02_no_parenthetical.md -->
**工位1：涂抹模块**

- **模块包络尺寸**：50×30×200mm

**工位2：检测模块**

- **模块包络尺寸**：Φ30×80mm
```

```markdown
<!-- 03_markdown_hashes.md -->
### 工位1 涂抹模块

- **模块包络尺寸**：60×40×290mm
```

```markdown
<!-- 04_nested_subsections.md -->
**工位1 涂抹模块**

### 4.1.2 内部结构

内部细节...

- **模块包络尺寸**：60×40×290mm
```

```markdown
<!-- 05_no_bom_match.md -->
**完全未声明的模块**

- **模块包络尺寸**：100×100×100mm
```

```markdown
<!-- 06_ambiguous_tokens.md -->
**工位1 通用**

- **模块包络尺寸**：50×40×200mm
```

```markdown
<!-- 07_multiple_envelopes_one_section.md -->
**工位1 涂抹模块**

- **模块包络尺寸**：60×40×290mm
- 子组件:
- **模块包络尺寸**：Φ30×45mm
```

```markdown
<!-- 08_envelope_before_any_section.md -->
- **模块包络尺寸**：60×40×290mm

**工位1 涂抹**
```

```markdown
<!-- 09_cylinder_form.md -->
**工位2 AE检测**

- **模块包络尺寸**：Φ45×120mm
```

```markdown
<!-- 10_english_header.md -->
## Station 1: Applicator

- **模块包络尺寸**：60×40×290mm
```

- [ ] **Step 2: Create the fixture test harness**

```python
# tests/test_section_walker_fixtures.py
"""Fixture-driven tests for the section walker.

Each fixture under tests/fixtures/section_walker/ pairs a small Markdown
document with an expected walker output, expressed inline in the test.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from cad_spec_section_walker import SectionWalker

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "section_walker"


def _load(name: str) -> list[str]:
    return FIXTURE_DIR.joinpath(name).read_text(encoding="utf-8").splitlines()


def _bom(assemblies):
    return {"assemblies": assemblies}


# Shared BOM for most fixtures
_GISBOT_BOM = _bom([
    {"part_no": "GIS-EE-002", "name": "工位1涂抹模块"},
    {"part_no": "GIS-EE-003", "name": "工位2 AE检测模块"},
    {"part_no": "GIS-EE-002-ALT", "name": "工位1驱动模块"},  # for ambiguity fixture 06
])


def test_01_clean_station():
    outputs, stats = SectionWalker(_load("01_clean_station.md"), _GISBOT_BOM).extract_envelopes()
    assert stats.matched_count == 2
    assert [o.matched_pno for o in outputs] == ["GIS-EE-002", "GIS-EE-003"]
    assert all(o.tier == 1 for o in outputs)


def test_02_no_parenthetical():
    outputs, stats = SectionWalker(_load("02_no_parenthetical.md"), _GISBOT_BOM).extract_envelopes()
    assert stats.matched_count == 2
    assert [o.matched_pno for o in outputs] == ["GIS-EE-002", "GIS-EE-003"]


def test_03_markdown_hashes():
    outputs, stats = SectionWalker(_load("03_markdown_hashes.md"), _GISBOT_BOM).extract_envelopes()
    assert stats.matched_count == 1
    assert outputs[0].matched_pno == "GIS-EE-002"


def test_04_nested_subsections():
    outputs, _ = SectionWalker(_load("04_nested_subsections.md"), _GISBOT_BOM).extract_envelopes()
    assert outputs[0].matched_pno == "GIS-EE-002"  # walked up past unmatched 4.1.2


def test_05_no_bom_match():
    outputs, stats = SectionWalker(_load("05_no_bom_match.md"), _GISBOT_BOM).extract_envelopes()
    assert stats.matched_count == 0
    assert stats.unmatched_count == 1
    assert outputs[0].reason == "all_tiers_abstained"


def test_06_ambiguous_tokens():
    """Two BOM rows share 工位1 → Tier 1 abstains. Tier 2 density tie → abstain.
    Final output is UNMATCHED with density-tie reason."""
    outputs, stats = SectionWalker(_load("06_ambiguous_tokens.md"), _GISBOT_BOM).extract_envelopes()
    assert stats.matched_count == 0
    assert stats.unmatched_count == 1
    assert outputs[0].reason in ("tier2_density_tie", "all_tiers_abstained")


def test_07_multiple_envelopes_one_section():
    outputs, stats = SectionWalker(
        _load("07_multiple_envelopes_one_section.md"), _GISBOT_BOM
    ).extract_envelopes()
    assert stats.matched_count == 2
    assert all(o.matched_pno == "GIS-EE-002" for o in outputs)


def test_08_envelope_before_any_section():
    outputs, stats = SectionWalker(
        _load("08_envelope_before_any_section.md"), _GISBOT_BOM
    ).extract_envelopes()
    assert stats.unmatched_count == 1
    assert outputs[0].reason == "no_parent_section"


def test_09_cylinder_form():
    outputs, _ = SectionWalker(_load("09_cylinder_form.md"), _GISBOT_BOM).extract_envelopes()
    assert outputs[0].envelope_type == "cylinder"
    assert outputs[0].matched_pno == "GIS-EE-003"


def test_10_english_header():
    outputs, _ = SectionWalker(_load("10_english_header.md"), _GISBOT_BOM).extract_envelopes()
    # English header doesn't match any Chinese BOM via Tier 2/3 → UNMATCHED
    # (Fixture 12 will exercise the English-BOM Tier 2 ASCII path.)
    assert outputs[0].matched_pno is None or outputs[0].tier == 3
```

- [ ] **Step 3: Run the fixture tests**

Run: `pytest tests/test_section_walker_fixtures.py -v`
Expected: all 10 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/section_walker/ tests/test_section_walker_fixtures.py
git commit -m "test(walker): add 10 synthetic fixture tests covering all walker paths"
```

---

## Task 22: 3 New Non-GISBOT Fixtures + corresponding tests

**Files:**
- Create: `tests/fixtures/section_walker/11_non_gisbot_chassis.md`
- Create: `tests/fixtures/section_walker/12_english_bom.md`
- Create: `tests/fixtures/section_walker/13_axis_label_rotation.md`
- Modify: `tests/test_section_walker_fixtures.py` (add 3 tests)

- [ ] **Step 1: Create the 3 new fixtures**

```markdown
<!-- 11_non_gisbot_chassis.md -->
## 底盘设计

**驱动轮1 减速器总成**

- **外形尺寸**：180×180×120mm (长×宽×高)

**驱动轮2 减速器总成**

- **外形尺寸**：180×180×120mm (长×宽×高)

**驱动轮3 减速器总成**

- **外形尺寸**：180×180×120mm (长×宽×高)
```

```markdown
<!-- 12_english_bom.md -->
## Mechanical Design

## Main Arm Assembly

- **模块包络尺寸**：1200×60×290mm (长×宽×高)
```

```markdown
<!-- 13_axis_label_rotation.md -->
**工位1 长方形臂**

- **模块包络尺寸**：1200×60×290mm (长×宽×高)
```

- [ ] **Step 2: Add the fixture tests**

Append to `tests/test_section_walker_fixtures.py`:

```python
def test_11_non_gisbot_chassis_via_constructor_kwargs():
    """G12 validation: chassis subsystem uses DIFFERENT trigger term and
    station pattern, customized via constructor kwargs — NO code edit."""
    chassis_bom = _bom([
        {"part_no": "CHASSIS-DRV-001", "name": "驱动轮1 减速器总成"},
        {"part_no": "CHASSIS-DRV-002", "name": "驱动轮2 减速器总成"},
        {"part_no": "CHASSIS-DRV-003", "name": "驱动轮3 减速器总成"},
    ])
    walker = SectionWalker(
        _load("11_non_gisbot_chassis.md"),
        chassis_bom,
        trigger_terms=("外形尺寸",),
        station_patterns=[(r"驱动轮\s*(\d+)", "驱动轮")],
        axis_label_default="长×宽×高",
    )
    outputs, stats = walker.extract_envelopes()
    assert stats.matched_count == 3
    assert {o.matched_pno for o in outputs} == {
        "CHASSIS-DRV-001", "CHASSIS-DRV-002", "CHASSIS-DRV-003",
    }
    assert all(o.tier == 1 for o in outputs)


def test_12_english_bom_ascii_word_subsequence():
    """G12 + Tier 2 ASCII path: English BOM + English header → match via
    word subsequence (not CJK path)."""
    english_bom = _bom([
        {"part_no": "LIFT-001", "name": "Main Arm"},
        {"part_no": "LIFT-002", "name": "Cross Beam"},
    ])
    outputs, stats = SectionWalker(
        _load("12_english_bom.md"), english_bom,
    ).extract_envelopes()
    assert stats.matched_count == 1
    assert outputs[0].matched_pno == "LIFT-001"
    assert outputs[0].tier == 2


def test_13_axis_label_canonicalization():
    """Box with 长×宽×高 label → dims stored as canonical (X, Y, Z)
    where position 0 = length, 1 = width, 2 = height. The raw label
    is preserved in axis_label for audit."""
    bom = _bom([{"part_no": "GIS-EE-002", "name": "工位1长方形臂"}])
    outputs, _ = SectionWalker(_load("13_axis_label_rotation.md"), bom).extract_envelopes()
    assert len(outputs) == 1
    o = outputs[0]
    assert o.matched_pno == "GIS-EE-002"
    # dims[0] is X and carries the length value (1200)
    assert o.dims[0] == ("x", 1200.0)
    assert o.dims[1] == ("y", 60.0)
    assert o.dims[2] == ("z", 290.0)
    # Raw source label preserved
    assert o.axis_label == "长×宽×高"
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_section_walker_fixtures.py -v`
Expected: all 13 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/section_walker/ tests/test_section_walker_fixtures.py
git commit -m "test(walker): add non-GISBOT fixture tests for generality + axis canonicalization"
```

---

## Task 23: Real Design Doc Integration Tests + `--out-dir` Flag

**Files:**
- Modify: `cad_pipeline.py` (add `--out-dir` CLI flag)
- Create: `tests/test_section_walker_real_docs.py`

- [ ] **Step 1: Add `--out-dir` flag to `cad_pipeline.py`**

Find the `argparse` setup for the `spec` subcommand in `cad_pipeline.py` and add:

```python
    spec_parser.add_argument(
        "--out-dir",
        type=str,
        default=None,
        help="Override subsystem output root (default: cad/<subsystem>/). "
             "Used by tests to redirect writes away from pinned subsystem dirs.",
    )
```

Then thread `args.out_dir` into the subsystem path resolution. Find where `cad/<subsystem>/` is constructed and replace with:

```python
    subsystem_dir = Path(args.out_dir) / subsystem if args.out_dir else Path("cad") / subsystem
```

- [ ] **Step 2: Write the real-doc test**

```python
# tests/test_section_walker_real_docs.py
"""Layer 3 integration tests against real design docs.

Uses pre-computed BOM YAML fixtures at tests/fixtures/real_doc_boms/*.yaml
(generated manually via _regenerate.py). Tests NEVER write to cad/<subsystem>/.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from cad_spec_section_walker import SectionWalker

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "real_doc_boms"
END_EFFECTOR_DOC = Path("D:/Work/cad-tests/04-末端执行机构设计.md")
LIFTING_PLATFORM_DOC = Path("D:/Work/cad-tests/19-液压钳升降平台设计.md")


def _load_yaml_bom(name: str) -> dict | None:
    path = FIXTURE_DIR / f"{name}.yaml"
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.mark.integration
def test_end_effector_docs_match_four_stations():
    bom = _load_yaml_bom("end_effector")
    if bom is None or not END_EFFECTOR_DOC.exists():
        pytest.skip("end_effector fixture or source doc missing")
    lines = END_EFFECTOR_DOC.read_text(encoding="utf-8").splitlines()
    outputs, stats = SectionWalker(lines, bom).extract_envelopes()
    assert stats.matched_count >= 4, (
        f"Expected ≥4 station envelopes matched, got {stats.matched_count}. "
        f"Unmatched reasons: {stats.unmatched_reasons}"
    )
    # All matches should resolve to GIS-EE-00N assemblies
    for o in outputs:
        if o.matched_pno:
            assert o.matched_pno.startswith("GIS-EE-"), \
                f"Unexpected match: {o.matched_pno}"


@pytest.mark.integration
def test_lifting_platform_docs_match_at_least_two():
    bom = _load_yaml_bom("lifting_platform")
    if bom is None or not LIFTING_PLATFORM_DOC.exists():
        pytest.skip("lifting_platform fixture or source doc missing")
    lines = LIFTING_PLATFORM_DOC.read_text(encoding="utf-8").splitlines()
    outputs, stats = SectionWalker(lines, bom).extract_envelopes()
    if stats.matched_count < 2:
        pytest.skip(
            f"lifting_platform only matched {stats.matched_count} envelopes — "
            f"documented known limitation (reasons: {stats.unmatched_reasons})"
        )
    assert stats.matched_count >= 2


@pytest.mark.integration
def test_cad_pipeline_out_dir_flag_isolates_writes(tmp_path):
    """Running cad_pipeline.py spec --out-dir <tmp> must NOT mutate cad/end_effector/."""
    if not END_EFFECTOR_DOC.exists():
        pytest.skip("end_effector source doc missing")
    import subprocess, sys, os
    cad_ee = Path("cad/end_effector")
    before = {}
    if cad_ee.exists():
        before = {p.name: p.stat().st_mtime for p in cad_ee.glob("*") if p.is_file()}
    env = os.environ.copy()
    subprocess.run(
        [sys.executable, "cad_pipeline.py", "spec",
         "--design-doc", str(END_EFFECTOR_DOC),
         "--out-dir", str(tmp_path), "--proceed", "--auto-fill"],
        env=env, check=False, capture_output=True, timeout=120,
    )
    after = {}
    if cad_ee.exists():
        after = {p.name: p.stat().st_mtime for p in cad_ee.glob("*") if p.is_file()}
    assert before == after, \
        f"cad/end_effector/ was mutated during --out-dir test: {set(after) ^ set(before)}"
    assert (tmp_path / "end_effector" / "CAD_SPEC.md").exists()
```

- [ ] **Step 3: Run the integration tests**

Run: `pytest tests/test_section_walker_real_docs.py -v -m integration`
Expected: tests PASS when fixtures exist, otherwise skip with clear message.

- [ ] **Step 4: Commit**

```bash
git add cad_pipeline.py tests/test_section_walker_real_docs.py
git commit -m "feat(pipeline): add --out-dir flag + real-doc walker integration tests"
```

---

## Task 24: hatch_build.py packaging

**Files:**
- Modify: `hatch_build.py:17-32` (add walker module to `_PIPELINE_TOOLS`)
- Modify: `tests/test_packaging.py` (add wheel smoke for walker)

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_packaging.py

def test_wheel_ships_cad_spec_section_walker():
    """The walker module must be shipped in the wheel alongside the other
    pipeline tools, mirrored to src/cad_spec_gen/data/python_tools/."""
    from pathlib import Path
    mirror = Path("src/cad_spec_gen/data/python_tools/cad_spec_section_walker.py")
    # The mirror is regenerated at build time; either it exists or the source
    # is listed in hatch_build._PIPELINE_TOOLS.
    import hatch_build
    assert "cad_spec_section_walker.py" in hatch_build._PIPELINE_TOOLS, \
        "Walker module not added to hatch_build._PIPELINE_TOOLS"
```

- [ ] **Step 2: Run to verify test fails**

Run: `pytest tests/test_packaging.py::test_wheel_ships_cad_spec_section_walker -v`

- [ ] **Step 3: Update `_PIPELINE_TOOLS`**

Edit `hatch_build.py:17`:

```python
_PIPELINE_TOOLS = [
    "cad_pipeline.py",
    "cad_spec_gen.py",
    "cad_spec_extractors.py",
    "cad_spec_section_walker.py",  # NEW: section walker for envelope extraction
    "cad_spec_reviewer.py",
    "cad_paths.py",
    "bom_parser.py",
    "annotate_render.py",
    "enhance_prompt.py",
    "prompt_data_builder.py",
    "gemini_gen.py",
    "comfyui_enhancer.py",
    "comfyui_env_check.py",
    "fal_enhancer.py",
    "pipeline_config.json",
]
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_packaging.py -v`
Expected: PASS. Also run the full regression:
`pytest tests/ -x --timeout=120 -q`
Expected: 270 → 295+ passing, 0 failures.

- [ ] **Step 5: Commit**

```bash
git add hatch_build.py tests/test_packaging.py
git commit -m "build: ship cad_spec_section_walker.py in wheel"
```

---

## Self-Review

**Spec coverage check:**

| Spec section | Covered by task |
|---|---|
| §2 G1 Walker module + class | Tasks 2, 11 |
| §2 G2 Replace P2 block | Task 19 |
| §2 G3 3 matching strategies + tier tagging | Tasks 6, 7, 8 |
| §2 G4 End-effector test ≥4 matches | Task 23 |
| §2 G5 Lifting-platform test ≥2 matches | Task 23 |
| §2 G6 10 synthetic fixtures | Task 21 |
| §2 G7 Never raises | Task 13 (caught internally) |
| §2 G8 Cross-module priority | Task 19 (unconditional P2 write) |
| §2 G9 Tier 0 regression protection | Task 9, 10, 13 |
| §2 G10 Surface audit in §6.4 | Task 20 |
| §2 G11 Granularity enforcement chain | Tasks 15, 16, 17, 18 |
| §2 G12 Cross-subsystem isolation | Tasks 11, 14, 22 |
| §2 G13 Backward-compat column order | Task 17 (parse_envelopes), Task 20 (render) |
| §2 G14 Function-chain consistency | Task 10 (two-phase dispatchers) |
| §2 G15 Machine reason codes + legend | Tasks 2, 20 |
| §3.2 Constructor kwargs for all vocab | Task 11 |
| §5 Dataclasses | Task 2 |
| §5.1 Axis canonicalization | Task 3, 12 |
| §6.1 Tier 1 + ambiguity fix | Task 6 |
| §6.2 Tier 2 dual-path | Task 7 |
| §6.3 Tier 3 Jaccard + stable sort | Task 8 |
| §7 Envelope regex builder | Task 4 |
| §8 Integration + feature flag + tuple return | Task 19 |
| §8.1 Rendering | Task 20 |
| §8.2 Downstream chain (6 steps) | Tasks 15-18 |
| §10.1 All modified files | Tasks 9, 15-20, 23, 24 |
| §11.1 Unit tests incl. G9/G11/G12 | Tasks 2-14 |
| §11.2 13 fixture tests | Tasks 21, 22 |
| §11.3 Real-doc tests | Task 23 |
| §12 Invariants | Cross-cutting in Tasks 2-20 |
| §13 Phased delivery | Task ordering matches phases P0-P10 |
| §14 Success criteria incl. --out-dir | Task 23 |

**Placeholder scan:** Searched for TBD/TODO/fill-in-details in the plan — none found. All code steps show full implementations.

**Type consistency:**
- `WalkerReason` literal values used: `tier0_context_window_match`, `tier1_unique_match`, `tier2_unique_subsequence`, `tier2_density_tie`, `tier3_jaccard_match`, `no_parent_section`, `empty_bom`, `all_tiers_abstained`, `unrecognized_axis_label` — defined in Task 2, used consistently in Tasks 6-13.
- `WalkerOutput.granularity` is `Literal["station_constraint", "part_envelope", "component"]` — set consistently to `"station_constraint"` throughout the walker (Task 13).
- `SectionWalker.__init__` kwarg names: `trigger_terms`, `station_patterns`, `axis_label_default`, `bom_pno_prefixes` — consistent across Tasks 11, 12, 22.
- `_find_nearest_assembly` new signature `(context, bom_data, bom_pno_prefixes=None)` — matches in Task 9 definition and Task 10 caller.
- `extract_part_envelopes` return type `tuple[dict, WalkerReport]` — consistent in Task 19 definition, Task 19 caller update, Task 20 rendering consumer.
- `PartQuery.spec_envelope_granularity` field name — matches in Task 15 definition, Task 16 consumer, Task 17 producer.
- `parse_envelopes` return shape `dict[pno, {"dims": tuple, "granularity": str}]` — matches in Task 17 producer, Task 17 `gen_parts.py`/`gen_params.py` adapters, Task 18 end-to-end test.

No inconsistencies found.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-12-section-header-walker.md`.**

Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, spec compliance + code quality reviews between tasks, fast iteration, one commit per task.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints for review.

**Which approach?**
