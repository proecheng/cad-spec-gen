# Common Model Family Admission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 固化“通用模型族进入默认模型库”的准入规则，防止后续把项目特判、宽泛词抢路由、路径/数据漂移或几何包络错误带入照片级 3D 管线。

**Architecture:** 新增一份人读 runbook 和一份机读 JSON admission manifest。测试只读取 manifest 中的代表性案例，统一验证分类、模板元数据、负例、默认路由顺序、category-scoped 尺寸和几何包络，避免每批新增模型族都靠临时经验维护。

**Tech Stack:** Python 3.10+、pytest、CadQuery、现有 `JinjaPrimitiveAdapter`、`default_resolver`、`classify_part`、`lookup_std_part_dims`。

---

## File Structure

- Create: `docs/superpowers/runbooks/common-model-family-admission.md`
  - 面向人类和大模型的准入操作手册，说明哪些数据必须进入 manifest、哪些临时收紧禁止进入默认库。
- Create: `docs/superpowers/specs/common_model_family_admission.json`
  - 机读准入清单，保存代表性 positive/negative/route/dimension/geometry cases。
- Create: `tests/test_common_model_family_admission.py`
  - 读取 JSON manifest 并执行通用准入测试。
- Modify: `docs/superpowers/README.md`
  - 把 runbook、manifest 和本计划加入索引，并更新后续队列。
- Modify: `docs/PROGRESS.md`
  - 记录本轮分支、能力边界、验证记录和下一步建议。

## Task 1: Admission Plan Checkpoint

**Files:**
- Create: `docs/superpowers/plans/2026-05-05-common-model-family-admission.md`

- [ ] **Step 1: Save this execution plan**

Use `apply_patch` to add this plan file.

- [ ] **Step 2: Confirm worktree state**

Run:

```powershell
git status --short --untracked-files=all
```

Expected: only this plan file is untracked/modified.

## Task 2: Write Failing Admission Tests

**Files:**
- Create: `tests/test_common_model_family_admission.py`

- [ ] **Step 1: Write tests that require the missing runbook and manifest**

The test file should define:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from adapters.parts.jinja_primitive_adapter import JinjaPrimitiveAdapter
from bom_parser import classify_part
from cad_spec_defaults import lookup_std_part_dims
from parts_resolver import PartQuery, default_resolver


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "superpowers" / "specs" / "common_model_family_admission.json"
RUNBOOK_PATH = ROOT / "docs" / "superpowers" / "runbooks" / "common-model-family-admission.md"


def _manifest() -> dict:
    assert MANIFEST_PATH.exists(), f"missing admission manifest: {MANIFEST_PATH}"
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _query(case: dict) -> PartQuery:
    return PartQuery(
        part_no=case.get("part_no", case["id"]),
        name_cn=case["name"],
        material=case.get("material", ""),
        category=case["category"],
        make_buy=case.get("make_buy", "外购"),
    )
```

Then add tests for:

- required manifest sections and gates
- runbook references to manifest and mandatory gates
- positive cases classify as expected and hit reusable B-grade parametric templates
- negative cases do not hit forbidden templates and preserve expected classification
- route cases match explicit non-terminal default rules
- precedence cases keep specialized templates/routes before broad families
- dimension cases are category-scoped
- geometry cases stay within `real_dims`

- [ ] **Step 2: Run red test**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_common_model_family_admission.py -q
```

Expected: FAIL because the manifest and runbook do not exist yet.

## Task 3: Add Runbook and Manifest

**Files:**
- Create: `docs/superpowers/runbooks/common-model-family-admission.md`
- Create: `docs/superpowers/specs/common_model_family_admission.json`

- [ ] **Step 1: Add runbook**

The runbook must state:

- default library admission requires explicit category and family intent
- broad tokens alone are forbidden
- real STEP, project/user STEP, vendor cache, SolidWorks/Toolbox, bd_warehouse and PartCAD routes stay before default B-grade templates
- mature/specialized templates must not be stolen by broader families
- dimensions must be category-scoped when tokens overlap across families
- generated template geometry must stay within `real_dims`
- reusable B-grade templates require `PARAMETRIC_TEMPLATE`, `B`, `requires_model_review=False`, `template_scope=reusable_part_family`, `source_tag=parametric_template:<template>`
- project-specific exact `part_no` routes are not allowed in skill-wide default library unless clearly documented as vendor/demo stand-ins
- every new family adds positive, negative, route, dimension and geometry cases to the manifest

- [ ] **Step 2: Add manifest**

Use JSON with sections:

```json
{
  "schema_version": 1,
  "required_gates": [],
  "positive_cases": [],
  "negative_cases": [],
  "route_cases": [],
  "precedence_cases": [],
  "dimension_cases": [],
  "geometry_cases": []
}
```

Representative cases must include families from all four existing batches: LM12UU/NEMA17/M12 proximity/compact cylinder/cable harness; MGN12H/GT2/KF301/solenoid valve; UCP204/BK12/DIN terminal; IP65 enclosure/pushbutton/vacuum cup/2020 profile.

- [ ] **Step 3: Run green test**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_common_model_family_admission.py -q
```

Expected: PASS.

## Task 4: Update Progress Docs

**Files:**
- Modify: `docs/superpowers/README.md`
- Modify: `docs/PROGRESS.md`

- [ ] **Step 1: Update Superpowers README**

Add links to:

- this plan
- `runbooks/common-model-family-admission.md`
- `specs/common_model_family_admission.json`

Update the current queue to show the admission checklist as done or in verification.

- [ ] **Step 2: Update project progress board**

Record:

- current branch `codex/model-family-admission`
- new work item “通用模型族准入清单”
- current verification commands and results
- next suggested work: provider presets / UI wizard or next real-BOM-driven model-family batch

## Task 5: Verification and Commit

**Files:**
- All files above

- [ ] **Step 1: Run focused regression**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_common_model_family_admission.py tests\test_common_model_library_batch_4.py tests\test_common_model_library_batch_3.py tests\test_common_model_library_batch_2.py tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py tests\test_jinja_generators_new.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run sync and whitespace checks**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py --check
git diff --check
```

Expected: both pass, ignoring Windows line-ending notices already known in this repo.

- [ ] **Step 3: Commit**

Run:

```powershell
git add docs/superpowers/plans/2026-05-05-common-model-family-admission.md docs/superpowers/runbooks/common-model-family-admission.md docs/superpowers/specs/common_model_family_admission.json tests/test_common_model_family_admission.py docs/PROGRESS.md docs/superpowers/README.md
git commit -m "test(parts-library): 固化通用模型族准入清单"
```

Expected: commit succeeds on `codex/model-family-admission`.

## Self-Review

- Spec coverage: plan covers runbook, manifest, tests, progress docs, verification and commit.
- Placeholder scan: no `TBD` or incomplete task remains.
- Type consistency: tests reference existing APIs only: `PartQuery`, `JinjaPrimitiveAdapter.resolve`, `default_resolver.matching_rules`, `classify_part`, `lookup_std_part_dims`.
