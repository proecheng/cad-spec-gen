# render_manifest 多视角可见实例证据（方案 B：bbox-presence）— 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `render_manifest.json` 的每个 `files[]` 条目携带 `visible_instance_ids`（= `assembly_signature.instances[]` 里有有效 bbox 的 `instance_id` 集，所有视角相同）+ 顶层 `evidence_method: "instance_bbox_presence"`，从而让现有 `render_visual_regression.py` 的并集检查自然生效——把「少件」（required 件不在 GLB）从「总是 warn」升成「有 assembly_signature 时会 blocked」。契约层零改动、不 bump schema、不动 `cad_pipeline.py`。可证明永不比改之前差（详见 spec §1）。

**Architecture:** 新 1 个纯函数模块 `tools/view_instance_evidence.py` → `tools/render_qa.py::build_render_manifest` 调它注入 → 现成的 `tools/render_visual_regression.py::_check_current_view_instance_union` 消费。`cmd_render` 早就把 `assembly_signature` 传给 `write_render_manifest`（→ `build_render_manifest`），所以不动 `cad_pipeline.py`。

**Tech Stack:** Python 3.10+ / stdlib only（`math.isfinite`，不引 numpy）/ `pytest`（TDD）/ `ruff` / `mypy --strict`（`render_qa.py` 已在 CI gate，新模块也加进去）/ `scripts/dev_sync.py`（`tools/*.py` → `src/cad_spec_gen/data/` 镜像）。

设计文档：`docs/superpowers/specs/2026-05-12-render-manifest-view-instance-evidence-design.md`

---

## 前置约定（所有 task 通用）

- 分支 `feat/render-manifest-view-instance-evidence`（已建，spec 在分支上，3 个 docs commit `201305e`/`3769a9b`/`f65d3a2`），**不是 main**。subagent 用 `git -C "D:\Work\cad-spec-gen"` 绝对路径 + 提交前 `git -C "D:\Work\cad-spec-gen" branch --show-current` 守卫。
- 提交用 `git -c commit.gpgsign=false commit`；commit message 描述用中文。
- 工作目录 `D:\Work\cad-spec-gen`；shell PowerShell；命令从 repo root 跑。
- 「全套件」= `python -m pytest tests/ -q`；基线 **3090 PASS / 14 skipped / 0 regression**（main@6fe6e20）；本 PR 加 N 个新单测（不 skip）。
- 改 `tools/render_qa.py` 或新增 `tools/*.py` 后跑 `python scripts/dev_sync.py` 同步 `src/cad_spec_gen/data/tools/` 镜像（gitignored 还是 tracked 看实际——`dev_sync.py --check` 是 CI gate，跟着跑就对），再 `git diff --exit-code -- AGENTS.md`。
- `LF→CRLF` warning 是 noise，忽略。

---

## Task 0：确认剩余假设（无代码，无 commit）

spec §9 大部分已 ✓ 确认；这里复核 + 跑剩下的 grep。**任何 Step 发现实质不符 → 停下报告，不直接继续。**

- [ ] **Step 1**：`grep -rn "build_render_manifest\|write_render_manifest" cad_pipeline.py tools/` —— ✓ 应见 `cad_pipeline.py:~2229 from tools.render_qa import write_render_manifest` + `~2411 manifest_path = write_render_manifest(...)`（含 `assembly_signature=_assembly_signature_path`）+ `tools/render_qa.py:175 def write_render_manifest`（薄包装，透传所有参数给 `build_render_manifest`）。确认 `cmd_render` 确实传了 `assembly_signature`（→ 本 PR 不动 `cad_pipeline.py`）。
- [ ] **Step 2**：`sed -n "/def build_render_manifest/,/^def /p" tools/render_qa.py` —— ✓ 确认它内部 `assembly_signature_payload, _ = _load_optional_json(assembly_signature, root, "assembly signature")`（dict 透传 / 路径加载 / None→None）；`manifest_files` 列表里每项是 `{"view": _view_key(image_file), "path_rel_project":..., "path_abs_resolved":..., "sha256":..., "width":..., "height":..., "qa":{...}}`；`_view_key(path)` = `re.match(r"^(V\d+)", path.name, re.IGNORECASE)` → `V1`/`V2`/...，无匹配则 `path.stem`；函数末尾 `return { "schema_version": 2, ..., "files": manifest_files, "legacy_files": legacy_files }`。
- [ ] **Step 3**：`sed -n "/def _view_instance_evidence/,/def /p" tools/render_visual_regression.py` —— ✓ 确认它从 `manifest["files"]` 每条目读 `["visible_instance_ids","instance_ids","visible_instances","component_instance_ids","rendered_instance_ids"]`，能吃「字符串 list」（`["A","B"]`）也能吃「dict list」（`[{"instance_id":"A"}]`）；返回 `dict[str, set[str]]`（view→instance_id 集）。`grep -n "_check_current_view_instance_union\|_required_product_instance_ids\|render_evidence_missing_required_instance\|render_view_instance_evidence_missing" tools/render_visual_regression.py` —— ✓ 确认 `_check_current_view_instance_union(product_graph, {view:set})` = `required - union(all sets)`，缺则 `blocking_reasons.append({"code":"render_evidence_missing_required_instance","missing_instance_ids":sorted(missing),"message":...})`；没证据时 `warnings.append({"code":"render_view_instance_evidence_missing",...})`。`_required_product_instance_ids` 过滤 = `instance_id` 真值 ∧ `required is not False` ∧ `render_policy == "required"`。
- [ ] **Step 4**：`grep -rn "schema_version == 2\|\"schema_version\": 2" tests/ tools/ cad_pipeline.py` —— ✓ 确认涉及 render_manifest 的硬断言是 `test_render_manifest_signature.py:84/:132` + `test_photo3d_stale_artifacts.py:97`，**本 PR 不 bump schema 所以这些不动**；其余命中是别的 artifact（jury config / enhance / sw_config_broker / product_goal——无关）。
- [ ] **Step 5**：`grep -n "build_render_manifest\|assembly_signature\|instances\b\|visible_instance" tests/test_render_manifest_signature.py` + 读 `tests/test_render_manifest_signature.py:20-135`（`test_build_render_manifest_binds_contract_hashes_and_keeps_legacy_fields`）—— 看它构造的 `assembly_signature` dict 有没有 `instances[]`（有 → 本 PR 后该 test 的 manifest 会多 `visible_instance_ids`/`evidence_method`，要在 Task 2 加断言；没 → Task 2 顺手给它的 assembly_signature 加 `instances` 让新行为有覆盖）；确认 `test_render_manifest_signature.py` + `test_render_qa.py` 在 `tests/conftest.py` 的 `PHOTO3D_CONTRACT_TEST_FILES`（改这俩要跑契约测试）。
- [ ] **Step 6**：`git -C "D:\Work\cad-spec-gen" ls-files -v pyproject.toml`（应 `H`）；`grep -n "mypy --strict\|mypy --platform" .github/workflows/tests.yml` —— ✓ 确认 `mypy-strict` job 有 `run: mypy --strict tools/enhance_consistency.py tools/render_qa.py tools/path_policy.py`（cleanup Group C 加）—— Task 2 在末尾加 `tools/view_instance_evidence.py`。
- [ ] **Step 7**：汇总报告（一段）。

---

## Task 1：`tools/view_instance_evidence.py` + 单测（TDD，1 commit）

**Files:**
- Create: `tools/view_instance_evidence.py`
- Create: `tests/test_view_instance_evidence.py`

- [ ] **Step 1：写失败测试**

`tests/test_view_instance_evidence.py`：
```python
"""单测 view_instance_evidence.compute_view_visible_instances（render_manifest 逐视角实例证据 — 方案 B bbox-presence）。"""
from tools.view_instance_evidence import compute_view_visible_instances


_GOOD = {"xmin": 0.0}  # placeholder; 实际 fixture 见下
_VIEWS = ["V1", "V2", "V3"]


def _sig(*instances):
    return {"schema_version": 1, "instances": list(instances)}


def test_lists_instances_with_valid_bbox_uniform_across_views():
    sig = _sig(
        {"instance_id": "A", "bbox_mm": [0.0, 0.0, 0.0, 10.0, 5.0, 2.0]},   # 正常
        {"instance_id": "D", "bbox_mm": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]},     # 零退化——故意仍收录（不查退化）
    )
    out = compute_view_visible_instances(sig, _VIEWS)
    assert out is not None
    assert set(out.keys()) == {"V1", "V2", "V3"}
    assert out["V1"] == ["A", "D"]                # 已排序
    assert out["V1"] == out["V2"] == out["V3"]    # 每视角同一份
    # 确定性
    assert compute_view_visible_instances(sig, _VIEWS) == out


def test_excludes_invalid_bbox_and_missing_id():
    sig = _sig(
        {"instance_id": "A", "bbox_mm": [0.0, 0.0, 0.0, 10.0, 5.0, 2.0]},
        {"instance_id": "B", "bbox_mm": [0.0, 0.0, 0.0, 10.0, 5.0]},          # 长度≠6
        {"instance_id": "B2", "bbox_mm": [0.0, 0.0, 0.0, float("inf"), 5.0, 2.0]},  # 非有限
        {"instance_id": "B3", "bbox_mm": "not a list"},                       # 非 list
        {"instance_id": "B4"},                                                 # 无 bbox_mm
        {"bbox_mm": [0.0, 0.0, 0.0, 1.0, 1.0, 1.0]},                          # 无 instance_id
        {"instance_id": "", "bbox_mm": [0.0, 0.0, 0.0, 1.0, 1.0, 1.0]},       # 空 instance_id
        "not a dict",
    )
    out = compute_view_visible_instances(sig, _VIEWS)
    assert out is not None
    assert out["V1"] == ["A"]


def test_returns_none_when_no_instances():
    assert compute_view_visible_instances({}, _VIEWS) is None
    assert compute_view_visible_instances({"instances": "not a list"}, _VIEWS) is None
    assert compute_view_visible_instances("not a dict", _VIEWS) is None  # type: ignore[arg-type]


def test_empty_view_ids_returns_empty_dict():
    sig = _sig({"instance_id": "A", "bbox_mm": [0.0, 0.0, 0.0, 1.0, 1.0, 1.0]})
    assert compute_view_visible_instances(sig, []) == {}
```
（删掉骨架里没用的 `_GOOD` 占位；上面是完整测试。）

- [ ] **Step 2：跑测试，确认失败**

Run: `python -m pytest tests/test_view_instance_evidence.py -q`
Expected: collection error / ImportError —— `tools/view_instance_evidence.py` 还不存在。

- [ ] **Step 3：实现 `tools/view_instance_evidence.py`**

```python
"""render_manifest 逐视角可见实例证据（方案 B — bbox-presence）。

给 render_manifest.json 的每个 view 提供 `visible_instance_ids` = assembly_signature
里「在 GLB 里有有效 bbox」的 instance_id 集（所有视角相同）。配合 render_visual_regression
的并集检查，把「required 件不在 GLB」（= 真的少件）从 warning 升成 blocked；required 件
若在 GLB 必有 bbox → 在集里 → 不 block（无 false-positive）。

逐视角差异化（真 frustum / exploded-aware）是未来增强——只改本模块实现、不改接口。
详见 spec：docs/superpowers/specs/2026-05-12-render-manifest-view-instance-evidence-design.md
"""
from __future__ import annotations

import math
from typing import Any


def _has_valid_bbox(instance: dict[str, Any]) -> bool:
    """instance["bbox_mm"] 是恰 6 个有限数的 list。

    纯防御——assembly_signature.instances[] 里每项按构造都有 GLB 实测 bbox（且
    upstream `_float_list` 保证恰 6 个）；几乎永远为真。**故意不查退化**（[0,0,0,0,0,0]
    仍算有效）：宁可漏不可误——一个 required 件只要在 GLB 里有个 bbox 就算「在」、
    绝不因 bbox 怪异而 false-block。
    """
    bbox = instance.get("bbox_mm")
    return (
        isinstance(bbox, list)
        and len(bbox) == 6
        and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in bbox)
    )


def compute_view_visible_instances(
    assembly_signature: dict[str, Any],
    view_ids: list[str],
) -> dict[str, list[str]] | None:
    """每个 view → 「在 GLB 里有有效 bbox 的 instance_id」排序集（所有视角相同）。

    返回 None ⟺ assembly_signature 不是含 list 型 `instances` 的 dict（→ 无证据可算，
    调用方据此不写 visible_instance_ids，manifest 保持「无证据」状态 → 契约层 warn）。
    view_ids 为空 → 返回 {}。
    """
    if not isinstance(assembly_signature, dict):
        return None
    instances = assembly_signature.get("instances")
    if not isinstance(instances, list):
        return None
    valid_ids = sorted({
        str(inst["instance_id"])
        for inst in instances
        if isinstance(inst, dict) and inst.get("instance_id") and _has_valid_bbox(inst)
    })
    return {view: list(valid_ids) for view in view_ids}
```

- [ ] **Step 4：跑测试，确认通过**

Run: `python -m pytest tests/test_view_instance_evidence.py -q`
Expected: 4 passed.

- [ ] **Step 5：ruff + mypy + 全套件**

Run: `python -m ruff check tools/view_instance_evidence.py tests/test_view_instance_evidence.py` → `All checks passed!`
Run: `python -m mypy --strict tools/view_instance_evidence.py` → `Success: no issues found in 1 source file`
Run: `python -m pytest tests/ -q` → ≥ 3090 + 4 PASS / 0 regression。

- [ ] **Step 6：dev_sync + commit**

Run: `python scripts/dev_sync.py && python scripts/dev_sync.py --check && git -C "D:\Work\cad-spec-gen" diff --exit-code -- AGENTS.md` → 通过（新 `tools/view_instance_evidence.py` 被镜像同步）。
```
git -C "D:\Work\cad-spec-gen" branch --show-current   # 必须是 feat/render-manifest-view-instance-evidence
git -C "D:\Work\cad-spec-gen" add tools/view_instance_evidence.py tests/test_view_instance_evidence.py
git -C "D:\Work\cad-spec-gen" -c commit.gpgsign=false commit -m "feat(render-evidence): view_instance_evidence helper（方案 B — bbox-presence）

新纯函数 compute_view_visible_instances(assembly_signature, view_ids) → 每视角「在 GLB
里有有效 bbox 的 instance_id」排序集（所有视角相同）；assembly_signature 无 instances[]
→ 返 None。_has_valid_bbox 故意不查退化（宁漏不误）。+4 单测 TDD。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2：`build_render_manifest` 注入 + mypy gate + 集成/契约测试（1 commit）

**Files:**
- Modify: `tools/render_qa.py`（`build_render_manifest`）
- Modify: `.github/workflows/tests.yml`（`mypy-strict` job 那行加 `tools/view_instance_evidence.py`）
- Modify: `tests/test_render_manifest_signature.py`（给已有的 `test_build_render_manifest_binds_contract_hashes_and_keeps_legacy_fields` 加 `visible_instance_ids`/`evidence_method` 断言；按 Task 0 Step 5 结论，若它的 assembly_signature fixture 没 `instances` 则补上）
- Modify: `tests/test_render_visual_regression.py`（补 missing-from-GLB → blocked 的契约测试）

- [ ] **Step 1：写/改失败测试（集成）**

在 `tests/test_render_manifest_signature.py` 的 `test_build_render_manifest_binds_contract_hashes_and_keeps_legacy_fields` 里：
- 确保它构造的 `assembly_signature` dict 有 `instances`（按 Task 0 Step 5；若没有，加，比如 `"instances": [{"instance_id": "GIS-EE-001-1", "bbox_mm": [0.0,0.0,0.0,10.0,5.0,2.0]}, {"instance_id": "GIS-EE-001-2", "bbox_mm": [0.0,0.0,0.0,3.0,3.0,3.0]}]`）。
- 在断言区加：
  ```python
  assert manifest["evidence_method"] == "instance_bbox_presence"
  assert manifest["files"][0]["visible_instance_ids"] == ["GIS-EE-001-1", "GIS-EE-001-2"]  # 排序后；按你 fixture 的 instance_id 调整
  ```
- 再加一个新 test（不传 assembly_signature → 无证据字段）：
  ```python
  def test_build_render_manifest_omits_evidence_when_no_assembly_signature(tmp_path):
      from tools.render_qa import build_render_manifest
      # ……搭最小输入（参照同文件 test_build_render_manifest_marks_manifest_blocked_when_image_qa_fails 的 fixture 风格），不传 assembly_signature……
      manifest = build_render_manifest(project_root, render_dir, [png], subsystem="demo", run_id="r1", path_context_hash=None)
      assert "evidence_method" not in manifest
      assert "visible_instance_ids" not in manifest["files"][0]
      assert manifest["schema_version"] == 2  # 没 bump
  ```

- [ ] **Step 2：跑测试，确认失败**

Run: `python -m pytest tests/test_render_manifest_signature.py -q`
Expected: `test_build_render_manifest_binds_contract_hashes_and_keeps_legacy_fields` FAIL（`KeyError: 'evidence_method'` / `KeyError: 'visible_instance_ids'`）；`test_build_render_manifest_omits_evidence_when_no_assembly_signature` 这条本来就该 PASS（build_render_manifest 现在不写这些字段——所以它是「确认现状不被破坏」的回归锁，写完它应直接绿）。

- [ ] **Step 3：改 `tools/render_qa.py::build_render_manifest`**

在函数里——`assembly_signature_payload` 已由现有代码 `_load_optional_json(...)` 得到；`manifest_files` 列表已构造完。在 `return { ... }` 之前加：
```python
    from tools.view_instance_evidence import compute_view_visible_instances

    view_ids = sorted({str(f["view"]) for f in manifest_files})
    view_evidence = compute_view_visible_instances(assembly_signature_payload, view_ids)
    if view_evidence is not None:
        for entry in manifest_files:
            entry["visible_instance_ids"] = view_evidence[str(entry["view"])]
```
然后在 `return { "schema_version": 2, ..., "files": manifest_files, "legacy_files": legacy_files }` 这个 dict 里——条件性地加 `evidence_method`。最干净：先建 dict 再 set：
```python
    manifest: dict[str, Any] = {
        "schema_version": 2,
        # ……（原来所有字段，不变）……
        "files": manifest_files,
        "legacy_files": legacy_files,
    }
    if view_evidence is not None:
        manifest["evidence_method"] = "instance_bbox_presence"
    return manifest
```
（`import compute_view_visible_instances` 放函数内 local import 还是模块顶——模块顶更常规；但 `tools/render_qa.py` 已 import 一堆，加一行 `from tools.view_instance_evidence import compute_view_visible_instances` 到顶部 import 区即可。任选；若顶部 import 触发循环 import 再改 local——`view_instance_evidence.py` 只 import stdlib，不会循环。）**保持 `tools/render_qa.py` mypy-strict-clean**（它在 CI gate）。

- [ ] **Step 4：CI mypy gate 加新模块**

`.github/workflows/tests.yml` 的 `mypy-strict` job：把
`run: mypy --strict tools/enhance_consistency.py tools/render_qa.py tools/path_policy.py`
改成
`run: mypy --strict tools/enhance_consistency.py tools/render_qa.py tools/path_policy.py tools/view_instance_evidence.py`

- [ ] **Step 5：写契约测试（locks end-to-end，非 RED→GREEN——契约逻辑已存在）**

`tests/test_render_visual_regression.py` 加一个 test（参照同文件已有的 `test_render_visual_regression_uses_view_instance_evidence_union_when_available` 的 fixture 风格）：
```python
def test_render_visual_regression_blocks_when_required_instance_missing_from_evidence(...):
    """manifest 携带 visible_instance_ids，但 product_graph 里某 required 实例不在任何视角的并集
    （= 它不在 GLB 里、assembly_signature 没收录、helper 没填进证据）→ status blocked +
    blocking_reasons 含 render_evidence_missing_required_instance + missing_instance_ids 含它。"""
    # product_graph: instances=[{instance_id:"A",render_policy:"required"},{instance_id:"MISSING",render_policy:"required"}]
    # render_manifest.files[*].visible_instance_ids = ["A"]（每视角；"MISSING" 不在）
    # ……调 render_visual_regression 的入口（参照已有 test 怎么调）……
    # assert result["status"] == "blocked"
    # assert any(r["code"] == "render_evidence_missing_required_instance" and "MISSING" in r["missing_instance_ids"]
    #            for r in result["blocking_reasons"])
```
（具体调用参照同文件已有测试；这条不需要任何生产代码改动就该绿——它是 end-to-end 行为锁。）

- [ ] **Step 6：跑测试**

Run: `python -m pytest tests/test_render_manifest_signature.py tests/test_render_visual_regression.py tests/test_render_qa.py tests/test_photo3d_gate_contract.py -q` → 全 PASS。
Run: `python -m ruff check tools/render_qa.py tests/test_render_manifest_signature.py tests/test_render_visual_regression.py` → `All checks passed!`
Run: `python -m mypy --strict tools/render_qa.py tools/view_instance_evidence.py` → `Success`。
Run: `python -m pytest tests/ -q` → ≥ 3090 + (Task 1 的 4) + (Task 2 新增的 ~2-3) PASS / 0 regression。

- [ ] **Step 7：dev_sync + 干净 venv 复核 CI mypy 步**

Run: `python scripts/dev_sync.py && python scripts/dev_sync.py --check && git -C "D:\Work\cad-spec-gen" diff --exit-code -- AGENTS.md` → 通过。
Run（模拟 CI mypy-strict job，`feedback_preflight_mirror_ci.md`）：
```
python -m venv .mypy-ci-check
.\.mypy-ci-check\Scripts\python -m pip install --quiet "mypy>=1.10" pillow
.\.mypy-ci-check\Scripts\python -m mypy --strict tools/enhance_consistency.py tools/render_qa.py tools/path_policy.py tools/view_instance_evidence.py
Remove-Item -Recurse -Force .mypy-ci-check
```
Expected: `Success: no issues found in 4 source files`（或等价）。`.mypy-ci-check` 不要 commit。

- [ ] **Step 8：commit**

```
git -C "D:\Work\cad-spec-gen" branch --show-current   # 必须是 feat/render-manifest-view-instance-evidence
git -C "D:\Work\cad-spec-gen" add tools/render_qa.py .github/workflows/tests.yml tests/test_render_manifest_signature.py tests/test_render_visual_regression.py
git -C "D:\Work\cad-spec-gen" -c commit.gpgsign=false commit -m "feat(render-evidence): build_render_manifest 注入 visible_instance_ids + evidence_method（方案 B）

build_render_manifest 调 compute_view_visible_instances 给每个 files[] 条目填
visible_instance_ids（assembly_signature 有 instances[] 时）+ 顶层 evidence_method=
instance_bbox_presence；不 bump schema（新字段可选 additive）。现有 render_visual_regression
并集检查自然生效：required 件不在 GLB → blocked。cmd_render 早就把 assembly_signature 传给
write_render_manifest，所以不动 cad_pipeline.py。CI mypy-strict gate 加 view_instance_evidence.py。
+集成测（有/无 assembly_signature 两路）+契约测（missing-from-GLB → blocked）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3：收尾验证 + code-review + push + PR

**Files:** 无改动。

- [ ] **Step 1：最终验证**

Run: `python -m pytest tests/ -q` → ≥ 3090 + (本 PR 新增单测数) PASS / 14 skipped / 0 regression。
Run: `python -m ruff check tools/view_instance_evidence.py tools/render_qa.py tests/test_view_instance_evidence.py tests/test_render_manifest_signature.py tests/test_render_visual_regression.py` → `All checks passed!`
Run: `python -m mypy --strict tools/enhance_consistency.py tools/render_qa.py tools/path_policy.py tools/view_instance_evidence.py` → `Success`。
Run: `python scripts/dev_sync.py && python scripts/dev_sync.py --check && git -C "D:\Work\cad-spec-gen" diff --exit-code -- AGENTS.md` → 通过。
Run: `git -C "D:\Work\cad-spec-gen" status --porcelain` → clean（无 `.mypy-ci-check` / 镜像残留）。
Run: `python -m pytest tests/ -v -m "not mypy" -q`（CI 等价命令，系统 Python）→ 全 PASS。

- [ ] **Step 2：requesting-code-review**

按 CLAUDE.md，调 `superpowers:requesting-code-review` 对本分支相对 main 的 diff（不含 docs commit 的纯代码改动）做一次 review；按 `superpowers:receiving-code-review` 处理意见（本 PR 常见意见：`_has_valid_bbox` 不查退化是否合理 / `visible_instance_ids` 字段名 / `evidence_method` 命名 / build_render_manifest 里 import 位置 / 「永不更差」论证是否成立——逐条核实，不盲改）。有阻断性问题就修完再继续。

- [ ] **Step 3：push + 开 PR（需用户确认）**

向用户确认后：
```
git -C "D:\Work\cad-spec-gen" push -u origin feat/render-manifest-view-instance-evidence
gh pr create --base main --head feat/render-manifest-view-instance-evidence --title "feat(render-evidence): render_manifest 多视角可见实例证据（队列 C，方案 B）" --body "..."
```
PR body 要点：
- 队列 C：让 render_manifest 每个 view 携带 `visible_instance_ids`（= assembly_signature 里有有效 bbox 的 instance_id 集，所有视角相同）+ 顶层 `evidence_method`；现有 `render_visual_regression` 的并集检查自然生效 → 「required 件不在 GLB」从「总是 warn」升成「blocked」。**契约层零改动、不 bump schema、不动 cad_pipeline.py**（`cmd_render` 早就传 assembly_signature）。
- **可证明永不比改之前差**：assembly_signature 有 → 只多 block「真的少件」（required 件不在 GLB；required 件在 GLB 必有 bbox → 不 block，无 false-positive）；assembly_signature 无 → 退回 warn = 现状。
- frustum 逐视角差异化判定为过度设计（fit-to-frame 相机总框全部 → frustum 实践中 = bbox-presence；且带 false-block 风险）—— 留作未来增强（IF 加了 zoom 视角）。链 spec。
- 范围外：Blender 侧改动 / 交付报告可视化（队列 D）/ 逐视角强制检查 / 「无证据→blocked」更严立场。
- 结尾：`🤖 Generated with [Claude Code](https://claude.com/claude-code)`

- [ ] **Step 4：盯 CI（push 到 PR 分支；PowerShell 用 `gh pr checks <PR#> --watch`——`feedback_monitor_windows_gnu_tools.md`）**

Expected: 8 checks 全 SUCCESS。有红的 → 看日志、`superpowers:systematic-debugging` 修、push 修复 commit、再 watch。

---

## 自审（writing-plans skill 要求）

**1. Spec 覆盖**：spec §2 数据流 → Task 1（helper）+ Task 2 Step 3（build_render_manifest 注入）；§3「为什么不做 frustum」→ 已体现在 helper 实现（bbox-presence）+ PR body；§4 文件结构 → Task 1/2 的 Files 列表（含「不动 cad_pipeline.py」——Task 0 Step 1 确认 cmd_render 已传 assembly_signature）；§5 测试 → Task 1 Step 1（单测）+ Task 2 Step 1/5（集成 + 契约）；§6 mypy/ruff/CI → Task 1 Step 5 + Task 2 Step 4/6/7；§7 验证清单 → Task 1 Step 5 + Task 2 Step 6/7 + Task 3 Step 1；§9 调查项 → Task 0。无遗漏。

**2. Placeholder 扫描**：Task 1 的 helper 代码 + 测试代码完整给出（删了骨架里的 `_GOOD` 占位）；Task 2 Step 1/5 的测试给了具体断言 + 「参照同文件已有测试的 fixture 风格」（不是空洞——指明了参照对象 + 关键断言）；Task 2 Step 3 给了完整的注入代码片段。Task 0 的「确认」步是「跑这个 grep、对照 ✓ 的预期、不符就停」，不是 TBD。无 "TODO/类似上文"。

**3. 类型/命名一致**：`compute_view_visible_instances(assembly_signature: dict, view_ids: list[str]) -> dict[str, list[str]] | None` 全程同签名（Task 1 实现 / Task 2 调用 / commit msg / PR body）；`_has_valid_bbox`、`visible_instance_ids`（canonical key，与 `render_visual_regression` 首选 key 一致）、`evidence_method = "instance_bbox_presence"` 全程一致；`tools/view_instance_evidence.py` 路径全程一致；分支名 `feat/render-manifest-view-instance-evidence` 全程一致。

**4. 已知留给执行期判断的小点**（Task 0 驱动，非 placeholder）：`test_build_render_manifest_binds_contract_hashes_and_keeps_legacy_fields` 的 assembly_signature fixture 现在有没有 `instances`（Task 0 Step 5 → Task 2 Step 1 据此决定要不要补 `instances` 到 fixture + 断言里的 instance_id 列表照 fixture 调）；`build_render_manifest` 里 `compute_view_visible_instances` 的 import 放模块顶还是函数内（任选，spec/plan 倾向模块顶——无循环 import 风险）。
