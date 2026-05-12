# 设计：render_manifest 多视角可见实例证据（最小版 — 方案 B：bbox-presence）

- **日期**：2026-05-12
- **基线**：main@6fe6e20（ruff/mypy cleanup + SP1 §11 B1/B2 已 push、CI 全绿后）
- **分支**：`feat/render-manifest-view-instance-evidence`
- **规模**：小型 单 PR（新 1 个纯函数模块（无几何、不用 render_config）+ 改 `tools/render_qa.py` 注入一个字段 + 测试；契约层 `render_visual_regression.py` **零改动**，不 bump schema）
- **状态**：brainstorming 完成（含 3 轮 grep+实跑自审，第 3 轮把方案从 frustum A 缩到 B）；待用户复审 → writing-plans

---

## 1. 背景与目标

roadmap（`docs/PROGRESS.md` L191）："逐视角可见实例证据增强 | Phase 4 -> Phase 6 | 契约层已经能防少件，但逐视角实例证据越丰富，普通用户越容易判断图是否完整 | 渲染/交付报告能展示每个视角看到哪些实例，减少只能 warning 的情况"。

**现状（探查结论）**：`tools/render_visual_regression.py` **已经**会解析每个 manifest `files[]` 条目的 `visible_instance_ids`（首选 key，别名 `instance_ids`/`visible_instances`/`component_instance_ids`/`rendered_instance_ids`），有证据时 `_check_current_view_instance_union(product_graph, {view: set})` 算「所有视角可见实例的并集」对照 `_required_product_instance_ids(product_graph)`（product_graph 里 `instance_id` 真值 ∧ `required is not False` ∧ `render_policy == "required"` 的实例），缺则 `blocking_reasons.append({"code": "render_evidence_missing_required_instance", "missing_instance_ids": sorted(missing), ...})` → status `blocked`；**没**证据时只 `warnings.append({"code": "render_view_instance_evidence_missing", ...})` → status `warning`。**缺的唯一一块**：`render_manifest.json` 没有任何东西去填 `visible_instance_ids`，所以契约层永远走「warn」分支。

**本 PR**：让 `build_render_manifest` 给每个 `files[]` 条目填 `visible_instance_ids` = `assembly_signature.instances[]` 里「有有效 bbox」的 `instance_id` 集（所有视角相同——见 §3 为何不做 frustum 逐视角）。一旦填上，现有契约逻辑自然生效——把「少件」从「总是 warn」升成「有 assembly_signature 时会 blocked」。**契约层一行不改，不 bump schema。**

**为何这个机制抓「少件」**：`assembly_signature` 的 `instances[]` loop 是 `for object_name in sorted(bboxes)`（`bboxes` = caller 传的、Blender 从 GLB 提取的每物体实测 bbox），所以 **missing-from-GLB 的 required 件根本不在 `instances[]` 里**（只在 `coverage.missing_instance_total` 计数）→ helper 看不到它 → 不进任何视角的 `visible_instance_ids` → 并集缺它 → 契约层 `render_evidence_missing_required_instance` → blocked。

**可证明「永不比改之前差」**（这是用户的核心要求）：
- `assembly_signature` 可用 → manifest 多一个 `visible_instance_ids` 字段，值 = 「在 GLB 里有有效 bbox 的件」。契约并集检查 = 「product_graph 里的 required 件是否都在 GLB 里」：required-但-不在-GLB（= 真的少件）→ blocked（**严格优于「总是 warn」**）；required-且-在-GLB → 它有 bbox → 在 list 里 → 不 block（**永不误判好渲染**——不存在 false-positive block）。
- `assembly_signature` 不可用（None / 没 `instances[]`）→ helper 返 `None` → manifest 不写 `visible_instance_ids` / `evidence_method` → 契约层走「warn」分支 = **与现状完全一致**。
- 所以最坏退化 = 现状（warn），最好 = 抓到少件（blocked）；**绝不引入新的误判**。

**核心约束**：除「契约层从『总是 warn』→『有 assembly_signature 时会 block 少件』」这个有意的升级 + manifest 多两个可选 additive 字段外，零行为变更。北极星：结果准确 ✓（少件 → blocked-able）/ 稳定可靠 ✓（assembly_signature 缺时优雅退回 warn；无 false-positive）/ 零配置 ✓ / SW 装即用 ✓ / 傻瓜式 ✓（用户在 render/visual-check 报告里看到每张图标着「该有哪些件」）；Windows-only ✓（纯字典处理）。

## 2. 数据流

```
assembly_signature.json
  - instances[]: {instance_id, part_no, object_name, bbox_mm:[xmin,ymin,zmin,xmax,ymax,zmax], center_mm, size_mm, transform, render_policy, visual_priority}
    （bbox_mm 来自 GLB 实测；instances[] 只含「GLB 里有 bbox」的 object——missing-from-GLB 的 required 件不在 instances[]，只在 coverage.missing_instance_total）
        │
        ▼  tools/view_instance_evidence.py::compute_view_visible_instances(assembly_signature: dict, view_ids: list[str]) -> dict[str, list[str]] | None
        │    纯函数。view_ids = build_render_manifest 从 manifest_files 提取的（去重后的）实际渲染视角集（如 ["V1","V2","V3","V4","V5"]）。
        │    返回 None ⟺ assembly_signature 不是含 list 型 instances 的 dict（→ 无证据可算）。
        │    否则：valid_ids = sorted({ str(inst["instance_id"]) for inst in assembly_signature["instances"]
        │                               if isinstance(inst, dict) and inst.get("instance_id") and _has_valid_bbox(inst) })
        │      （_has_valid_bbox：inst.get("bbox_mm") 是恰 6 个有限 float 的 list——纯防御，因 instances[] 里每项按构造都有 GLB 实测 bbox，几乎永远为真；
        │       **故意不查退化（xmax==xmin 之类）**：宁可漏不可误——一个 required 件只要在 GLB 里有个像样的 bbox 就算「在」、绝不因 bbox 怪异而 false-block）
        │    返回 { view: list(valid_ids) for view in view_ids }（每视角同一个 list；逐视角差异化是未来增强——见 §3）。确定性、已排序。
        ▼
build_render_manifest（tools/render_qa.py，已收 assembly_signature 参数并在函数内 _load_optional_json 成 assembly_signature_payload）：
  - 在 manifest_files 构造完之后：view_ids = sorted({ f["view"] for f in manifest_files })
  - evidence = compute_view_visible_instances(assembly_signature_payload, view_ids)
  - evidence is None → 不写（manifest 保持「无证据」→ 契约层 warn，老行为）
  - 否则：for f in manifest_files: f["visible_instance_ids"] = evidence[f["view"]]（已排序的 list）；返回的 manifest dict 顶层加 evidence_method: "instance_bbox_presence"
  - **不动 schema_version**（仍 2；新字段是可选 additive；consumer 用「字段在不在」判断而非版本号）
        ▼
render_manifest.json（仍 schema v2，多了 files[].visible_instance_ids + 顶层 evidence_method——都可选）
        ▼  tools/render_visual_regression.py（**不改**）：
  - files[i] 有 visible_instance_ids → _check_current_view_instance_union(并集 vs required) → required 件不在并集 → blocked + render_evidence_missing_required_instance
  - 都没（assembly_signature 缺时 / 老 v2 manifest）→ 仍 warn（老行为，graceful degradation）
```

## 3. 为什么 MVP 用「bbox-presence」而不做 frustum 逐视角

第 3 轮自审推演：若按 frustum 算每视角真正在画面里的 instance，需复现 `render_3d.py` ~L827-911 的相机数学（lens 65 / sensor 36 / aspect / `required_dist = bs_radius/sin(min(fov_v,fov_h))/frame_fill` / `camera_to_blender` 的 spherical→朝向 + target 偏移），且 `bs_center`/`bs_radius` 是从 instance bbox 并集算的——**取景球按构造包含所有 instance**，所以 fit-to-frame 相机总把整个球框住 → 实践中**所有有效-bbox 的 instance 在所有视角都在画面里** → frustum 检查退化成「所有有 bbox 的 instance 可见于所有视角」= 本节的 bbox-presence。pipeline 里也没有 zoom/detail 视角（`render_config.camera` 的 ~7 个 preset 全是 front/back/iso/exploded/section，都框整个装配；exploded 视角的 explode-offset 会改部件位置，但 Blender 渲那个视角时取景球也跟着扩，仍框全部）。所以 frustum A 在实践中**等价于 bbox-presence、却额外引入「相机数学若复现有 bug 就 false-positive block 一个好渲染」的风险**——比改之前更差。故 MVP 取 bbox-presence（零几何、零相机数学、零 false-positive 风险）。**逐视角差异化（真 frustum / exploded-aware）留作未来增强，IF 哪天 pipeline 加了 zoom/detail 视角再做**（届时只改 `compute_view_visible_instances` 的实现、不改接口、不改契约层）。

## 4. 文件结构

- **新建** `tools/view_instance_evidence.py`：`compute_view_visible_instances(assembly_signature: dict, view_ids: list[str]) -> dict[str, list[str]] | None` + 内部 `_has_valid_bbox(inst: dict) -> bool`。纯函数、只用 stdlib（`math.isfinite`）、无 IO、无 Blender、无 render_config。**写成 mypy-strict-clean**（§6：会进 CI mypy gate）。
- **改** `tools/render_qa.py`：`build_render_manifest` 里——`view_ids = sorted({f["view"] for f in manifest_files})`，`evidence = compute_view_visible_instances(assembly_signature_payload, view_ids)`；非 None → 给每个 `manifest_files[i]` 加 `"visible_instance_ids": evidence[manifest_files[i]["view"]]`，返回的 manifest 顶层加 `"evidence_method": "instance_bbox_presence"`；为 None 或没 assembly_signature → 不加这两项。**schema_version 不动**（仍 2）。**保持 mypy-strict-clean**（`render_qa.py` 已在 CI gate）。
- **改** 生产路径里调 `build_render_manifest` 的地方（plan #1 先找到是谁——`cad_pipeline.py` 里 grep 不到直接调用，可能是 `cmd_render` 经一个 `write_render_manifest` 包装）：确认它给 `build_render_manifest` 传了 `assembly_signature`；**若没传 → 本 PR 补传**（否则 feature 在生产里是 no-op）。
- **新建** `tests/test_view_instance_evidence.py`：单测 helper。
- **改/新增** `tests/test_render_qa.py`（或 `tests/test_render_manifest_signature.py`）：集成测——传 assembly_signature 给 `build_render_manifest` → 每个 `files[]` 有 `visible_instance_ids`（= 有有效 bbox 的 instance_id 排序集），顶层有 `evidence_method == "instance_bbox_presence"`，`schema_version` 仍 2；不传 assembly_signature → 无这两项、`schema_version` 仍 2（向后兼容）。
- **改/新增** `tests/test_render_visual_regression.py`：补「manifest 携带 `visible_instance_ids`，但某 required 实例不在并集（missing-from-GLB）→ status blocked + `render_evidence_missing_required_instance` + `missing_instance_ids` 含它」；确认「manifest 携带证据 + 并集覆盖全部 required → 不 block」（已有类似测试，确认仍过）；确认「老 manifest 无 `visible_instance_ids` → 仍 warn」（graceful degradation 没回归）。
- **不改** `tools/render_visual_regression.py`、`tools/photo3d_gate.py`、Blender `render_3d.py`、`tools/assembly_signature.py`、`render_config.py`、`tests/test_render_manifest_signature.py` 的 `schema_version == 2` 断言（不 bump，所以不动）。
- canonical/mirror：`tools/view_instance_evidence.py`（新）+ `tools/render_qa.py` + 生产 caller（`cad_pipeline.py`?）都在 repo root（或 tools/），`src/cad_spec_gen/data/` 下是 dev_sync 镜像——改完跑 `python scripts/dev_sync.py` + `--check` + `git diff --exit-code -- AGENTS.md`。

## 5. 测试（TDD）

- **`tests/test_view_instance_evidence.py`**（先写失败测试 → 实现 helper → 绿）：
  - `assembly_signature` 含：instance A（`bbox_mm` 正常 6 浮点）、instance B（`bbox_mm` 缺 / 含 `inf`/`nan` / 不是 list / 长度 ≠ 6——被 `_has_valid_bbox` 排除）、instance C（`instance_id` 缺/空——跳过）、instance D（`bbox_mm` == `[0,0,0,0,0,0]` 零退化——**故意期望它仍被收录**，证明「不查退化」）；`view_ids = ["V1","V2","V3"]`。
  - 断言：返回 dict、key 集 == `{"V1","V2","V3"}`；每视角的 list == `["A","D"]`（B 因 bbox 无效、C 因无 id 被排除；D 保留），且每视角内容相等、已排序、连跑两次相等；`assembly_signature` 不是 dict / 没 `instances` / `instances` 不是 list → 返回 `None`；`view_ids` 空 list → 返回空 dict（`{}`）。
- **集成测**（`test_render_qa.py` / `test_render_manifest_signature.py`）：见 §4。
- **契约测**（`test_render_visual_regression.py`）：见 §4 三条。
- 全套件不回归（不 bump schema → `test_render_manifest_signature.py` 的 `== 2` 断言不动；plan 仍 grep 确认没别处因新字段炸——`if key in entry` 模式应都安全）。

## 6. mypy / ruff / CI

- `tools/render_qa.py` **已在 CI mypy-strict gate**（`.github/workflows/tests.yml` `mypy-strict` job 的 `run: mypy --strict tools/enhance_consistency.py tools/render_qa.py tools/path_policy.py`）—— 本 PR 改它必须保持 strict clean（新增的几行：`view_ids` 推导、`compute_view_visible_instances` 调用、注入循环——都要正确标注类型）。
- 新 `tools/view_instance_evidence.py` 写成 strict clean，**并加进上面那行**：`mypy --strict tools/enhance_consistency.py tools/render_qa.py tools/path_policy.py tools/view_instance_evidence.py`（与 cleanup PR Group C 把清理/新增的纯函数模块纳入 gate 的意图一致）。
- 只用 stdlib（`math.isfinite`），不引 numpy/任何第三方——mypy gate job 只 `pip install "mypy>=1.10" pillow`，新文件不能依赖别的（不依赖 pillow，纯字典/数）。
- `ruff check` 所有动过的文件 clean。

## 7. 验证清单

1. `python -m pytest tests/test_view_instance_evidence.py tests/test_render_qa.py tests/test_render_manifest_signature.py tests/test_render_visual_regression.py tests/test_photo3d_gate_contract.py -q` → 全 PASS（+新测试）。
2. `python -m pytest tests/ -q` → ≥ 3090 PASS / 0 regression（+新测试；schema 不 bump，不应触现有断言）。
3. `python -m ruff check tools/view_instance_evidence.py tools/render_qa.py <生产 caller 文件> tests/test_view_instance_evidence.py` → `All checks passed!`
4. `python -m mypy --strict tools/render_qa.py tools/view_instance_evidence.py`（含 transitive）→ `Success`；CI mypy-strict gate 那行加 `tools/view_instance_evidence.py` 后，在干净 venv（`pip install "mypy>=1.10" pillow`，从 repo root）跑绿（`feedback_preflight_mirror_ci.md`：本地 dev env 不算 CI 等价）。
5. `python scripts/dev_sync.py && python scripts/dev_sync.py --check && git diff --exit-code -- AGENTS.md` → 通过。
6. 北极星 5 gate + Windows-only：全过（见 §1）。

## 8. 范围外

- frustum 逐视角差异化（真 frustum / exploded-aware）—— §3 分析后判定为过度设计 + 有 false-positive 风险，不做；IF 未来加 zoom/detail 视角再做（只改 helper 实现）。
- Blender 侧改动（写 per-view sidecar）—— 用户选了纯 Python，且 §3 表明无必要。
- 交付报告 / `DELIVERY_PACKAGE.json` / `delivery/README.md` 接入「每视角看到哪些件」可视化 —— 留队列 D。
- 逐视角强制检查（「V_i 必须看到它该看到的件」，需「每视角期望集」spec 字段）—— 留后续。
- 「无证据 → blocked」的更严立场 —— 不做（保留 warn 作 graceful degradation，与 roadmap「减少只能 warning 的情况」一致）。
- 占用/遮挡判定 —— jury 的活。
- bump schema_version —— 不做（新字段可选 additive，零 blast radius）。

## 9. Plan 第 0 task 调查项（已确认的标 ✓；剩下的 plan Task 0 跑）

1. **生产路径里谁调 `build_render_manifest`、传不传 `assembly_signature`（重要——不传则本 PR 还要让它传）**：`cad_pipeline.py` 里 grep 不到 `build_render_manifest(` 直接调用 → `grep -rn "build_render_manifest\|write_render_manifest" cad_pipeline.py tools/` 找到生产 caller（`cmd_render`?一个 `write_render_manifest` 包装?），看它给 `build_render_manifest` 传了哪些参数；若没传 `assembly_signature` → 本 PR 补传。
2. ✓ `build_render_manifest` 签名已收 `assembly_signature: dict|str|Path|None`（关键字、可选），内部 `assembly_signature_payload, _ = _load_optional_json(assembly_signature, root, "assembly signature")`（dict 透传 / 路径加载 / None→None）；`files[i]["view"]` 由 `_view_key(path)` = `re.match(r"^(V\d+)", name, re.IGNORECASE)`（→ `V1`/`V2`/...，无匹配则 `path.stem`）。✓ 不 bump schema → 不动 `render_config` 加载逻辑（虽然它内部已加载 render_config，本 PR 用不上）。
3. ✓ `assembly_signature.py`：`instances[]` loop 是 `for object_name in sorted(bboxes)`（missing-from-GLB 件不在 instances[]，只在 `coverage.missing_instance_total`）；`bbox_mm` = caller 传的 `bboxes` dict（GLB 实测）。`bbox_mm` 是否恒为 6 浮点 / 何时可能退化（空 / `[0,...]`）—— plan 顺手看下 `_float_list` / bbox 提取，不影响设计（`_has_valid_bbox` 已防御）。
4. ✓ `render_visual_regression.py`：view-instance key 列表首选 `visible_instance_ids`；`_required_product_instance_ids` 过滤 = `instance_id` 真值 ∧ `required is not False` ∧ `render_policy == "required"`；`_check_current_view_instance_union(product_graph, {view: set})` = `required - union(all views' sets)`，缺则 blocked + `render_evidence_missing_required_instance`；baseline-v2-vs-current（多了字段但仍 v2）比较不 choke（`_compare_baseline_views` 只比视角集；per-view evidence 比较单向「current 缺 baseline 有的」）。
5. `grep -rn "schema_version == 2\|\"schema_version\": 2\|schema_version\b" tests/ tools/` —— 确认没有别处（除 `test_render_manifest_signature.py` 的两处，不动）会因新增 `visible_instance_ids`/`evidence_method` 字段炸；✓ `test_render_manifest_signature.py` + `test_render_qa.py` 在 `PHOTO3D_CONTRACT_TEST_FILES`（改这俩要跑契约测试）。
6. ✓ `pyproject.toml` 是 `H`（可正常 stage）；✓ `.github/workflows/tests.yml` `mypy-strict` job 有 `run: mypy --strict tools/enhance_consistency.py tools/render_qa.py tools/path_policy.py`—— 本 PR 在末尾加 `tools/view_instance_evidence.py`。
