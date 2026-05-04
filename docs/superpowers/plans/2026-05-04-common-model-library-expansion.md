# Common Model Library Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Execution Status

2026-05-04：已在 `codex/common-model-library-expansion` 功能分支执行第一批常用模型库扩展。实现覆盖 LMxxUU 直线轴承、NEMA17/23 步进电机、M8/M12/M18 圆柱接近传感器、可复用线束可视段、紧凑气缸；新增默认库显式规则和包络几何测试，避免只靠终端 fallback 或项目特判。子代理新开时触达线程上限，本轮改由主代理本地只读复核；复核发现并修复了线束/气动模板几何超出 `real_dims` 的通用性缺口。

已验证：
- `D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_common_model_library_expansion.py -q` -> `26 passed`
- `D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_parts_adapters.py tests\test_jinja_generators_new.py tests\test_resolve_report.py tests\test_parts_library_integration.py tests\test_parts_library_standard_categories.py tests\test_common_model_library_expansion.py -q` -> `208 passed, 2 skipped`
- `D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py --check` -> 通过

**Goal:** Expand the default parts library so non-programming users can get recognizable common purchased parts across new products without project-specific rules.

**Architecture:** Keep project-specific `parts_library.yaml` sparse and move reusable rules into `parts_library.default.yaml`. Use existing resolver contracts: category/keyword routing, `JinjaPrimitiveAdapter` reusable B-grade templates, optional STEP/synthesizer routes only when the model is safely generic, and geometry reports to tell users what remains simplified.

**Tech Stack:** Python 3.10+, pytest, CadQuery, YAML-driven `PartsResolver`, existing `dev_sync.py` mirrors.

---

### Task 1: Red Tests for Generic Category Coverage

**Files:**
- Create: `tests/test_common_model_library_expansion.py`
- Modify: none

- [x] **Step 1: Write failing tests**

```python
from __future__ import annotations

import pytest

from adapters.parts import vendor_synthesizer
from adapters.parts.jinja_primitive_adapter import JinjaPrimitiveAdapter
from bom_parser import classify_part
from parts_resolver import PartQuery, default_resolver


def _q(category: str, name: str, material: str = "") -> PartQuery:
    return PartQuery(
        part_no="GEN-001",
        name_cn=name,
        material=material,
        category=category,
        make_buy="外购",
    )


@pytest.mark.parametrize(
    ("name", "material", "expected"),
    [
        ("LM12UU 直线轴承", "", "bearing"),
        ("NEMA17 步进电机", "", "motor"),
        ("M12 电感接近开关", "PNP NO", "sensor"),
        ("薄型气缸", "MGPM20-50", "pneumatic"),
        ("拖链线束", "4芯×1200mm", "cable"),
    ],
)
def test_common_purchased_part_names_classify_to_reusable_categories(
    name: str,
    material: str,
    expected: str,
) -> None:
    assert classify_part(name, material) == expected


@pytest.mark.parametrize(
    ("category", "name", "material", "template", "dims"),
    [
        ("bearing", "LM12UU 直线轴承", "", "linear_bearing_lmxxuu", (21, 21, 30)),
        ("motor", "NEMA17 步进电机", "", "nema_stepper_motor", (42.3, 42.3, 72)),
        ("sensor", "M12 电感接近开关", "", "cylindrical_proximity_sensor", (12, 12, 55)),
        ("pneumatic", "薄型气缸", "MGPM20-50", "compact_pneumatic_cylinder", (42, 34, 70)),
        ("cable", "拖链线束", "4芯×1200mm", "cable_harness_stub", (10, 50, 6)),
    ],
)
def test_jinja_adapter_has_reusable_templates_for_common_categories(
    category: str,
    name: str,
    material: str,
    template: str,
    dims: tuple[float, float, float],
) -> None:
    result = JinjaPrimitiveAdapter().resolve(_q(category, name, material), {})

    assert result.status == "hit"
    assert result.geometry_source == "PARAMETRIC_TEMPLATE"
    assert result.geometry_quality == "B"
    assert result.requires_model_review is False
    assert result.metadata["template"] == template
    assert result.real_dims == dims


@pytest.mark.parametrize(
    ("query", "expected_adapter"),
    [
        (_q("bearing", "LM12UU 直线轴承"), "jinja_primitive"),
        (_q("motor", "NEMA17 步进电机"), "jinja_primitive"),
        (_q("sensor", "M12 电感接近开关"), "jinja_primitive"),
        (_q("pneumatic", "薄型气缸", "MGPM20-50"), "jinja_primitive"),
        (_q("cable", "拖链线束", "4芯×1200mm"), "jinja_primitive"),
    ],
)
def test_default_library_routes_common_categories_without_project_part_numbers(
    query: PartQuery,
    expected_adapter: str,
) -> None:
    result = default_resolver(project_root="__missing_project__").resolve(query)

    assert result.status in {"hit", "fallback"}
    assert result.adapter == expected_adapter
    assert result.kind == "codegen"
    assert not result.requires_model_review


def test_default_library_synthesizer_registry_remains_in_lockstep() -> None:
    assert set(vendor_synthesizer.DEFAULT_STEP_FILES) == set(
        vendor_synthesizer.SYNTHESIZERS
    )
```

- [x] **Step 2: Run tests to verify red**

Run: `D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_common_model_library_expansion.py -q`

Expected: FAIL for missing `pneumatic` classification and missing reusable templates/routes.

### Task 2: Generic Classifier and Template Support

**Files:**
- Modify: `bom_parser.py`
- Modify: `cad_spec_defaults.py`
- Modify: `adapters/parts/jinja_primitive_adapter.py`

- [x] **Step 1: Implement minimal classifier and dims**

Add `pneumatic` keyword classification before `pump`, add model dimensions for LM12UU, NEMA17 full visual height, M12 proximity sensor, cable harness, and compact cylinder fallback.

- [x] **Step 2: Implement reusable jinja templates**

Generalize the existing LM10UU, NEMA23, and M8-specific templates to reusable LMxxUU, NEMA stepper, cylindrical proximity sensor, cable harness stub, and compact pneumatic cylinder templates.

- [x] **Step 3: Run focused tests**

Run: `D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_common_model_library_expansion.py -q`

Expected: PASS.

### Task 3: Default Registry Routes

**Files:**
- Modify: `parts_library.default.yaml`
- Modify: `tests/test_parts_library_standard_categories.py`

- [x] **Step 1: Add default category mappings**

Add generic default `jinja_primitive` mappings before terminal fallback:

```yaml
  - match:
      category: motor
      keyword_contains: ["NEMA", "步进", "stepper"]
    adapter: jinja_primitive

  - match:
      category: sensor
      keyword_contains: ["接近开关", "proximity", "M8", "M12"]
    adapter: jinja_primitive

  - match:
      category: cable
    adapter: jinja_primitive

  - match:
      category: pneumatic
    adapter: jinja_primitive
```

- [x] **Step 2: Add rule-presence tests**

Extend category-rule tests to assert the new default mappings exist and resolve through `matching_rules()` for non-project part numbers.

- [x] **Step 3: Run focused routing tests**

Run: `D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py -q`

Expected: PASS.

### Task 4: Documentation, Mirrors, and Verification

**Files:**
- Modify: `docs/PROGRESS.md`
- Modify: `docs/superpowers/README.md`
- Mirror updates via `scripts/dev_sync.py`

- [x] **Step 1: Update progress docs**

Record the new branch, current work item, tests, and next step.

- [x] **Step 2: Sync mirrors**

Run: `D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py`

- [x] **Step 3: Verify**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py tests\test_parts_adapters.py tests\test_jinja_generators_new.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q
D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py --check
git diff --check
```

Expected: all pass, no mirror drift.
