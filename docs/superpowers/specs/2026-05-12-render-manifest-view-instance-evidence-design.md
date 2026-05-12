# 设计：render_manifest 多视角可见实例证据（最小版）

- **日期**：2026-05-12
- **基线**：main@6fe6e20（ruff/mypy cleanup + SP1 §11 B1/B2 已 push、CI 全绿后）
- **分支**：`feat/render-manifest-view-instance-evidence`
- **规模**：中-小型 单 PR（新 1 个纯函数模块 + 改 `tools/render_qa.py` 注入 + bump schema + 测试；契约层 `render_visual_regression.py` **零改动**——它早就会用 `visible_instance_ids`）
- **状态**：brainstorming 完成；待用户复审 → writing-plans

---

## 1. 背景与目标

roadmap（`docs/PROGRESS.md` L191）："逐视角可见实例证据增强 | Phase 4 -> Phase 6 | 契约层已经能防少件，但逐视角实例证据越丰富，普通用户越容易判断图是否完整 | 渲染/交付报告能展示每个视角看到哪些实例，减少只能 warning 的情况"。

**现状（探查结论）**：
- `tools/render_visual_regression.py` **已经**会解析每个 manifest `files[]` 条目的 `visible_instance_ids`（首选 key，别名 `instance_ids`/`visible_instances`/`component_instance_ids`/`rendered_instance_ids`），有证据时 `_check_current_view_instance_union()` 算「所有视角可见实例的并集」对照 `_required_product_instance_ids(product_graph)`（product_graph 里 `required is not False` 且 `render_policy == "required"` 的实例），缺则 `blocking_reasons.append({"code": "render_evidence_missing_required_instance", "missing_instance_ids": [...]})` → status `blocked`；**没**证据时只 `warnings.append({"code": "render_view_instance_evidence_missing", ...})` → status `warning`。甚至有现成测试 `test_render_visual_regression_uses_view_instance_evidence_union_when_available()`。
- **缺的唯一一块**：`render_manifest.json` 没有任何东西去填 `visible_instance_ids`（`build_render_manifest` 只产图像 QA），所以契约层永远走「warn」分支。

**本 PR**：新增一个纯 Python helper，从 `assembly_signature.json`（每 instance 的 `bbox_mm`/`transform`/`render_policy`/`object_name`）+ `render_config.json`（每视角相机 preset + `subsystem.bounding_radius_mm` + `frame_fill` + `explode`/`section` 规则）算出每视角的 `visible_instance_ids`，让 `build_render_manifest` 注入进 manifest。一旦填上，现有契约逻辑自然生效——把「少件」从「总是 warn」升成「有证据可查时会 blocked」。**契约层一行不改。**

**核心约束**：除「契约层从『总是 warn』变成『有证据时会 block』」这个有意的升级 + `render_manifest` schema v2→v3（additive）外，零行为变更。北极星：结果准确 ✓（少件→blocked-able）/ 稳定可靠 ✓（graceful degradation——算不出 frustum 就保守填、缺 assembly_signature/render_config 就回退到老的「无证据→warn」）/ 零配置 ✓ / SW 装即用 ✓ / 傻瓜式 ✓（用户在 render/visual-check 报告里看到每视角标着哪些件）；Windows-only ✓（纯几何）。

## 2. 数据流

```
assembly_signature.json
  - instances[]: {instance_id, part_no, object_name, bbox_mm:[xmin,ymin,zmin,xmax,ymax,zmax], center_mm, size_mm,
                  transform:{translation_mm,rotation_deg,matrix}, render_policy:"required|optional|excluded", visual_priority}
    （注：bbox_mm 来自 GLB 实测；instances[] 只含「在 GLB 里有 bbox」的 object——missing-from-GLB 的 required 件不在 instances[] 里，只在 coverage.missing_instance_total 计数）
render_config.json
  - camera: {<view_id>: preset}（preset 多为 spherical {azimuth_deg, elevation_deg, distance_factor}，也可 cartesian {x,y,z}；fit-to-frame：距离由 frame_fill + min(fov_v,fov_h) 算）
  - frame_fill: 0.75；subsystem.bounding_radius_mm: 300；explode:{rules,...}；section:{cut_plane,...}
        │
        ▼  tools/view_instance_evidence.py::compute_view_visible_instances(assembly_signature: dict, render_config: dict, manifest_files: list[dict]) -> dict[str, list[str]] | None
        │    （纯函数。manifest_files = build_render_manifest 已经构造好的 files[] 列表（每项有 "view"=_view_key 给的 V<n>、"width"、"height"）。
        │     返回 None ⟺ assembly_signature 没有 instances[]（→ 无证据可算）；否则返回一个 dict、对每个出现过的 files[].view 都有一项（去重后）：
        │       先从 assembly_signature.instances[] 的并集算 bs_center / bs_radius（= Blender 渲染时的取景中心/半径）；
        │       对每个 view：从 render_config.camera 找该 view 对应的 preset（V<n> ↔ preset 的映射 = §3 + plan #1），能找到且能算出相机变换 → 复用 render_3d.py 的相机数学（lens/sensor/aspect/frame_fill + spherical→朝向 + required_dist）把每个有有效 bbox_mm 的 instance 的 8 个 bbox 角点投影到该相机，任一角点（在近平面前）落在 NDC [-1,1]² → 加进该视角的 list；
        │       找不到 preset / 算不出相机参数 → 该视角保守填「所有有有效 bbox 的 instance」；无有效 bbox 的 instance（不在 instances[]，或 bbox_mm 不是 6 个有限浮点 / 退化）→ 哪个视角都不进。
        │     每个 list 排序、确定性。见 §3。）
        ▼
build_render_manifest（tools/render_qa.py，已收 assembly_signature + render_config_path，且**已在函数内加载** render_config（`render_config = _load_optional_path_json(render_config_path, ...)` + `camera_config = render_config.get("camera")`——现成局部变量，无需补加载）：
  - 在 manifest_files 构造完之后：evidence = compute_view_visible_instances(assembly_signature_payload, render_config, manifest_files)
  - evidence is None（assembly_signature 缺/没 instances[]）→ 不写 visible_instance_ids / evidence_method（manifest 保持「无证据」→ 契约层 warn，老行为）
  - 否则：每个 manifest_files[i]["visible_instance_ids"] = evidence.get(manifest_files[i]["view"], [])（已排序）；顶层 evidence_method: "python_frustum_culling"（标记「Python 算的、非 Blender 来源」；保守回退是内部细节、不另设字段）
  - schema_version: 2 → 3（恒 bump，与是否有证据无关）
        ▼
render_manifest.json (v3)
        ▼  tools/render_visual_regression.py（**不改**）：
  - files[i] 有 visible_instance_ids → _check_current_view_instance_union(并集 vs required) → 缺则 blocked
  - 都没 → 仍 warn（老行为，graceful degradation）
```

## 3. `compute_view_visible_instances` — frustum 精度（实现方案 A）

候选方案（本 spec 定为 **A**，但留 plan 一个退路 B——见末尾）：
- **A（采用）best-effort frustum + 逐视角保守回退**：
  - **取景**：bs_center / bs_radius 从 `assembly_signature.instances[].bbox_mm` 的并集算（= Blender 渲染时实际取景的中心/半径——比用 `render_config.subsystem.bounding_radius_mm` 的 spec 值更贴近 Blender 真做的，因为 Blender 也是从 GLB 物体合并 bbox 算 bs_center/bs_radius 的）。
  - **相机数学**（复现 `render_3d.py` ~L827-911）：perspective；`lens` = `preset.get("lens_mm", 65)`；sensor_width = 36（Blender 默认）；aspect = 该 view 的 `width/height`（从 `manifest_files[i]`）；sensor_h = 36/aspect；`fov_v = atan(sensor_h/(2*lens))`、`fov_h = atan(36/(2*lens))`（半角，弧度）；`fov_half = min(fov_v, fov_h)`；`frame_fill` = `render_config.get("frame_fill", 0.75)`；`required_dist = bs_radius / sin(fov_half) / frame_fill`；view_dir 从 spherical preset 算（`x=cos(el)cos(az), y=cos(el)sin(az), z=sin(el)`）；camera location = bs_center + view_dir * required_dist，camera look-at bs_center（plan 抄 `render_config.py::camera_to_blender` + `render_3d.py` 的准确公式 + target offset：`camera_to_blender` 里 spherical 的 target 默认是 `[0,0,bounding_r*0.33]`——这个 0.33 偏移要照抄）。
  - **可见判定**：对每个有有效 `bbox_mm` 的 instance（`bbox_mm` 是 6 个有限浮点且 xmax>xmin / ymax>ymin / zmax>zmin 非退化），取世界坐标 8 个 bbox 角点（`bbox_mm` 若是 local 则先 apply `transform`——plan #2 查它是 world 还是 local），变换到相机空间、透视投影到 NDC，**若任一角点在近平面前且投影落在 [-1,1]×[-1,1] → 该 instance 加进该视角的 list**。
  - **逐视角保守回退**：该 view 在 `render_config.camera` 里找不到对应 preset（V<n> ↔ preset 映射见 plan #1）/ preset 不是可解析的 spherical 或 cartesian / 任何中间值非有限 → 该视角保守填「所有有有效 bbox 的 instance」（不抓该视角的 placement bug，但仍抓 missing-from-GLB）。
  - **无证据**：`assembly_signature` 缺 / 没 `instances[]` → helper 返回 `None` → `build_render_manifest` 不写 `visible_instance_ids` / `evidence_method` → manifest 保持「无证据」→ 契约层 warn（老行为）。`evidence_method` 恒为 `"python_frustum_culling"`（保守回退是内部细节、不另设字段）。
- **B（备用退路）保守 only**：永远「所有有有效 bbox 的 instance 可见于所有视角」——最简单，只抓 missing-from-GLB。**若 plan Task 0 读 `render_3d.py` 后发现相机数学太难可靠复现 / 渲染分辨率·aspect·V<n>↔preset 映射混乱无法确定 → 退到 B 作本 PR 的 MVP，frustum 精度留后续迭代**——本 PR 的核心价值（block on missing-from-GLB）与 frustum 精度无关，B 也满足。退到 B 时 `evidence_method` 可叫 `"python_bbox_presence"`（更诚实），spec 不强制名字。
- C（不采用）完整 AABB-frustum 相交：最精确，复杂度高，对 fit-to-frame 相机收益小。

**所有方案的共同关键点**：没有有效 `bbox_mm` 的 instance（= missing-from-GLB，根本不在 `assembly_signature.instances[]` 里——那个 loop 是 `for object_name in sorted(bboxes)`，只含 GLB 有 bbox 的物体；或 bbox 6 个浮点里有非有限值/退化）**永远不进任何视角的 `visible_instance_ids`** → 并集缺它 → blocked。这是抓「少件」的核心机制，与 frustum 精度无关。

**exploded / section 视角**：MVP 不特殊处理——frustum 检查直接用 instance 原始 bbox（不 apply `render_config.explode` 的 offset / `section` 的切割）。后果：exploded 视角的件被 explode 规则偏移出框时，本算法仍认为它「在框内」（用未偏移 bbox 算）——会**漏报**（绝不误报）。对本 PR 的目标（抓 missing-from-GLB）无影响。后续迭代再精确处理。Plan 调查：哪个 view 是 exploded/section、`explode`/`section` 规则结构，确认本 MVP 简化不引入误报。

## 4. 文件结构

- **新建** `tools/view_instance_evidence.py`：纯函数 `compute_view_visible_instances(assembly_signature: dict, render_config: dict) -> dict[str, list[str]]` + 内部 frustum 几何 helper（向量/矩阵运算用 stdlib `math`，不引 numpy——保持依赖轻）。无 IO、无 Blender、可单测。**写成 mypy-strict-clean**（见 §6 它会进 CI mypy gate）。
- **改** `tools/render_qa.py`：① `build_render_manifest` 里把 `render_config_path` 加载成 dict（目前只 `_load_optional_json` 哈希；需要 payload）；② `view_ids = [f["view"] for f in files]`，调 `compute_view_visible_instances(assembly_signature_payload, render_config_payload, view_ids)`；③ 返回非 None → 把 `evidence[f["view"]]` 注入 `f["visible_instance_ids"]`（canonical 名 `visible_instance_ids`，与 `render_visual_regression.py` 首选 key 一致），顶层加 `evidence_method = "python_frustum_culling"`；返回 None 或缺输入 → 不写这两项（manifest 保持「无证据」→ 契约层 warn）；④ `schema_version` 2 → 3（恒 bump）。**保持 mypy-strict-clean**（`render_qa.py` 已在 CI gate）。
- **改** `cad_pipeline.py::cmd_render`（或其调 `build_render_manifest` 处）：确认已传 `assembly_signature` + `render_config_path`（探查显示函数签名已收这俩——plan 确认 `cmd_render` 确实在传；若没传则补传）。
- **改** `tests/test_render_manifest_signature.py`：`schema_version == 2` 的 2 处断言改 `== 3`（line ~84 + ~132）。
- **新建** `tests/test_view_instance_evidence.py`：单测 helper。
- **改/新增** `tests/test_render_qa.py`（或 `test_render_manifest_signature.py`）：集成测——`build_render_manifest` 现在产 `visible_instance_ids` + `evidence_method` + `schema_version==3`；老调用（不传 assembly_signature/render_config）→ 不产这些（向后兼容）。
- **改/新增** `tests/test_render_visual_regression.py`：补一个「manifest 携带证据但缺一个 required 实例（missing-from-GLB 场景）→ status blocked + `render_evidence_missing_required_instance`」；确认「老 manifest 无证据 → 仍 warn」没回归。
- **不改** `tools/render_visual_regression.py`、`tools/photo3d_gate.py`、Blender `render_3d.py`（3 份都不动）、`tools/assembly_signature.py`。
- canonical/mirror：`tools/view_instance_evidence.py`（新）+ `tools/render_qa.py` + `cad_pipeline.py` 都在 repo root（或 tools/），`src/cad_spec_gen/data/` 下是 dev_sync 镜像——改完跑 `python scripts/dev_sync.py` + `--check`。

## 5. 测试（TDD）

- **`tests/test_view_instance_evidence.py`**（先写失败测试 → 实现 helper → 绿）：
  - 合成 `assembly_signature`：instance A（正常摆放、有 bbox）、instance B（无 bbox / 不在 instances[]——模拟 missing-from-GLB）、instance C（bbox 在装配 bounding sphere 外几倍处——模拟 placement bug）。
  - 合成 `render_config`：2-3 个 spherical preset 视角 + `bounding_radius_mm` + `frame_fill`。
  - 断言：A 出现在它在框内的视角里；B 哪个视角都不出现（因为它根本不在 instances[]，helper 看不到它）；C 在 frustum 模式下哪都不出现（保守模式下都出现）；render_config 缺 `camera` / preset 异常 → 保守回退（所有有效-bbox instance 都在所有视角）；缺 `assembly_signature.instances` → 返回空 dict；输出每个 list 已排序、确定性（连跑两次相等）。
- **集成测**（`test_render_qa.py` 或 `test_render_manifest_signature.py`）：传 assembly_signature + render_config 给 `build_render_manifest` → `manifest["schema_version"] == 3`，每个 `files[]` 条目有 `visible_instance_ids`（list），顶层有 `evidence_method`；不传 → 无这些字段、`schema_version == 3`（或保持？plan 定：schema 总是 v3 还是只在有证据时？——本 spec 定 **schema_version 总是 3**，`visible_instance_ids`/`evidence_method` 只在有证据时出现，与「字段可选」一致）。
- **契约测**（`test_render_visual_regression.py`）：① manifest `files[]` 携带 `visible_instance_ids`，并集覆盖所有 required → status 不含 `render_evidence_missing_required_instance`（已有类似测试，确认仍过）；② manifest `files[]` 携带证据，但某个 required 实例不在任何视角的并集里（missing-from-GLB）→ status `blocked` + `blocking_reasons` 含 `render_evidence_missing_required_instance` + `missing_instance_ids` 含那个实例；③ manifest `files[]` 无 `visible_instance_ids`（老 v2 风格）→ status `warning` + `warnings` 含 `render_view_instance_evidence_missing`（确认 graceful degradation 没回归）。
- 全套件不回归（render_manifest schema v2→v3 + 新字段不能破现有 render/photo3d 契约测试——`test_render_manifest_signature.py` 的 `== 2` 断言已在 §4 列出要改；plan 还要 grep 别处有没有断言 `schema_version == 2` 或 manifest 字段集）。

## 6. mypy / ruff / CI

- `tools/render_qa.py` **已在 CI mypy-strict gate**（`.github/workflows/tests.yml` 的 `mypy-strict` job 有 `mypy --strict tools/enhance_consistency.py tools/render_qa.py tools/path_policy.py`）—— 本 PR 改它必须保持 strict clean。
- 新 `tools/view_instance_evidence.py` 写成 strict clean，**并加进 CI mypy-strict gate 那行**（与 cleanup PR Group C 的意图一致：清理/新增的纯函数模块纳入 gate 防回归）：`mypy --strict tools/enhance_consistency.py tools/render_qa.py tools/path_policy.py tools/view_instance_evidence.py`。
- 不引 numpy（frustum 用 stdlib `math` + 手写 3×3/4×4 矩阵乘）—— 保持 mypy gate job 的最小依赖（它只 `pip install "mypy>=1.10" pillow`；不能再依赖别的）。frustum 几何不需要 pillow，纯 stdlib。
- `ruff check` 所有动过的文件 clean。

## 7. 验证清单

1. `python -m pytest tests/test_view_instance_evidence.py tests/test_render_qa.py tests/test_render_manifest_signature.py tests/test_render_visual_regression.py tests/test_photo3d_gate_contract.py -q` → 全 PASS（+新测试）。
2. `python -m pytest tests/ -q` → ≥ 3090 PASS / 0 regression（+新测试；注意 §4 改的 schema 断言）。
3. `python -m ruff check tools/view_instance_evidence.py tools/render_qa.py cad_pipeline.py tests/test_view_instance_evidence.py` → `All checks passed!`
4. `python -m mypy --strict tools/render_qa.py tools/view_instance_evidence.py`（含 transitive）→ `Success`；CI mypy-strict gate 那行加 `tools/view_instance_evidence.py` 后在干净 venv（`pip install "mypy>=1.10" pillow`）跑绿（`feedback_preflight_mirror_ci.md`：本地 dev env 不算 CI 等价）。
5. `python scripts/dev_sync.py && python scripts/dev_sync.py --check && git diff --exit-code -- AGENTS.md` → 通过。
6. 北极星 5 gate + Windows-only：全过（见 §1）。

## 8. 范围外

- Blender 侧改动（写 per-view sidecar 用 Blender 真知道场景里有啥）—— 用户选了纯 Python，不做。
- 交付报告 / `DELIVERY_PACKAGE.json` / `delivery/README.md` 接入「每视角看到哪些件」可视化 —— 留队列 D。
- 逐视角强制检查（「V_i 必须看到它该看到的件」，需「每视角期望集」spec 字段）—— 留后续。
- 「无证据 → blocked」的更严立场 —— 不做（保留 warn 作 graceful degradation，与 roadmap「减少只能 warning 的情况」一致）。
- 占用/遮挡判定（件在画面内但被前面的件挡住）—— jury 的活，契约只管「在不在画面里」≈「在不在 frustum 里」。
- exploded 视角的 explode-offset 精确处理 —— MVP 简化（用未偏移 bbox 算 → 漏报不误报），后续迭代。

## 9. Plan 第 0 task 调查项（已确认的标 ✓；剩下的 plan Task 0 跑）

1. **相机数学 + V<n>↔preset 映射（最关键，影响 helper 实现 + 决定要不要退到方案 B）**：读 `render_3d.py` ~L827-911（`required_dist = bs_radius/sin(min(fov_v,fov_h))/frame_fill`、`fov_{v,h}=atan(sensor_{h,w}/(2*lens))`、`bs_center`/`bs_radius` 从 GLB 物体合并 bbox 算、look-at）+ `render_config.py::camera_to_blender`（spherical→朝向、target 默认 `[0,0,bounding_r*0.33]`）—— 抄准确公式。**`render_config.camera` 的键是 `V1..V5` 还是描述性名（front/iso/exploded/...）？`render_3d.py` 怎么把 camera preset 映射到 `V<n>_*.png` 文件名（按 dict 插入顺序枚举 → V1=第 1 个？还是文件名带描述性后缀、preset 按名匹配？）** —— 这决定 helper 怎么从 `manifest_files[i]["view"]`（= `_view_key` 给的 `V<n>`）找到对应 preset；找不到 → 该视角保守回退。渲染分辨率/aspect：固定（多少？）还是从 `render_config` / `files[].width/height` 取（spec 已定从 `files[].width/height` 取）。哪个 view 是 exploded/section、`explode`/`section` 规则结构（确认 MVP 简化不引入误报）。
2. **`assembly_signature.instances[].bbox_mm` 坐标系**：world-space（已含 transform）还是 local（需 apply `transform`）？`transform`（`{translation_mm, rotation_deg, matrix}`）何时 `matrix` 是 4×4 何时 null（`_normalize_transform` 的逻辑）？✓ 已确认 `instances[]` loop 是 `for object_name in sorted(bboxes)`（missing-from-GLB 件不在 instances[]，只在 `coverage.missing_instance_total`）。✓ `bbox_mm` 来自 caller 传的 `bboxes` dict（= Blender 提取的实测 bbox）。
3. **生产路径里谁调 `build_render_manifest`、传不传 `assembly_signature` + `render_config_path`（重要——不传则本 PR 还要让它传）**：`cad_pipeline.py` 里 grep 不到 `build_render_manifest(` 直接调用 → `grep -rn "build_render_manifest\|write_render_manifest" cad_pipeline.py tools/` 找到生产 caller（`cmd_render`?一个 `write_render_manifest` 包装?），看它给 `build_render_manifest` 传了哪些参数；若没传 `assembly_signature` / `render_config_path` → 本 PR 补传。✓ 已确认 `build_render_manifest` 内部已 `render_config = _load_optional_path_json(render_config_path, ...)` + `camera_config = render_config.get("camera")`（现成局部变量，无需补加载）；✓ `files[i]["view"]` 由 `_view_key(path)` = `re.match(r"^(V\d+)", name, re.IGNORECASE)`（→ `V1`/`V2`/...，无匹配则 `path.stem`）。
4. ✓ `render_visual_regression.py` 已确认：view-instance key 列表 `["visible_instance_ids","instance_ids","visible_instances","component_instance_ids","rendered_instance_ids"]`（首选 `visible_instance_ids`）；`_required_product_instance_ids` 过滤 = `instance_id` 真值 ∧ `required is not False` ∧ `render_policy == "required"`；`_check_current_view_instance_union(product_graph, current_view_evidence)` = `required - union(all views' evidence sets)`，缺则 `blocking_reasons.append({"code":"render_evidence_missing_required_instance","missing_instance_ids":sorted(missing),...})`；baseline 比较（`_compare_baseline_views` 只比视角集；per-view evidence 比较是单向「current 缺 baseline 有的」→ `render_view_instance_evidence_missing_from_current` warn）→ v2-baseline + v3-current **不会 choke**。
5. `test_render_manifest_signature.py` —— ✓ 确认有 2 处 `schema_version == 2` 硬断言（约 line 84 + 132）要改 `== 3`；grep `schema_version == 2` / `"schema_version": 2` 在所有 `tests/` 列全要改的；✓ `test_render_manifest_signature.py` + `test_render_qa.py` 在 `PHOTO3D_CONTRACT_TEST_FILES`（改 schema 要跑这些契约测试）。
6. ✓ `pyproject.toml` 是 `H`（非 skip-worktree，可正常 stage）；✓ `.github/workflows/tests.yml` `mypy-strict` job 有 `run: mypy --strict tools/enhance_consistency.py tools/render_qa.py tools/path_policy.py`（cleanup Group C 加）—— 本 PR 在这行末尾加 `tools/view_instance_evidence.py`。
