# Track C — LLM 驱动几何生成 + 多视角一致增强 设计规格

> 版本: v0.1 — 2026-04-24
> 状态: 已用户批准，可落地实施
> 触发: 2026-04-24 brainstorming session — 用户目标"产品图册级视觉质量 + 工程可用几何"；
>        当前管线几何层纯规则驱动，大量自制件回退 envelope box，FAL/ComfyUI 4 视角独立增强导致不一致
> 前置: Track A（A1/A2/A3 全部合入 main @ `8045495`）+ Track B（B0/B1/B2 PR #14 已推送）
> 关联: 不依赖 Track B 合入，可并行推进；Track B 合入后 L0 命中率提升，Track C 收益叠加

---

## 1. 目标与范围

### 1.1 背景与根因

端对端测试揭示"渲染图不够真实"的根因分布在两层：

**几何层（主要根因）**：

| 问题 | 表现 | 根因 |
|---|---|---|
| 参数缺失 | 模板已有（法兰/支架/壳体），但工厂函数需要的 `od/id/bolt_pcd` 等参数在 spec 里有自然语言描述但未被提取 | `_guess_geometry()` 只解析格式化字符串，遇到自然语言放弃 |
| 无模板覆盖 | 弹簧限力器、快换接头、线缆管理座等类型超出现有 8 类 | 无模板直接 fallback box/cylinder |

**视觉层（次要根因）**：

FAL/ComfyUI 对 4 个视角独立增强（各自随机 seed），导致色调/材质/光照在视角间不一致——同一台机器的不同视角看起来像不同材质的机器。

**关键架构洞察**：ControlNet depth+canny 把几何形状锁死——好几何 × 好渲染 = 优秀；差几何 × 好渲染 = 好看的错误形状。**改善几何层比改善渲染层的 ROI 高一个数量级。**

### 1.2 调研结论（2026-04-24）

- **TripoSR / InstantMesh / Meshy** 等图片转 3D 工具输出三角网格（GLB/STL），无参数化信息，不能出工程图 → 排除
- **OpenSCAD + LLM** 编译输出 STL，同上 → 排除
- **CadQuery + LLM（项目已有框架）** 输出 STEP/BREP 参数化几何，2025 年研究基准显示自我修正后成功率 85% → **主路径**
- **Zoo.dev Text-to-CAD API** 输出 STEP，零配置，但质量不可控、外部强依赖 → **用户可选项，默认关闭**
- **富化 Envelope** 纯本地、几何保证有效、失败明确可见 → **默认 L3 兜底**

### 1.3 目标

| 层 | 目标 |
|---|---|
| 几何层 | `end_effector` 11 件自制件中 ≥ 7/11 脱离裸 envelope；L1 工厂函数成功率 ≥ 80%；L2 有效几何率 ≥ 75% |
| 视觉层 | 4 视角 SSIM 相似度（L1 色彩通道）≥ 0.85 |
| 回归 | 现有 1126 个测试全部通过 |

### 1.4 非目标（严格范围）

- 不改动 L0 现有路径（template + 完整参数 → factory），不破坏已有测试
- 不引入图片转 3D 的三角网格路径（TripoSR/Meshy 等）
- 不改动 Blender 装配/渲染逻辑
- 不改动 Track B 的 SW Toolbox 路径
- 不要求 Zoo.dev 账号（默认关闭）

---

## 2. 关键设计决策

| # | 决策点 | 选择 |
|---|---|---|
| C-1 | LLM 参数提取的调用模型 | Gemini 2.0 Flash — 与 `gemini_gen.py` 现有调用方式一致，成本低，速度快 |
| C-2 | L2 代码生成步数 | 两步（特征提取 → 代码生成），不一步到位——特征提取步用 chain-of-thought 减少幻觉 |
| C-3 | 自我修正错误反馈方式 | 按 4 类归类（几何无效 / API 签名错误 / 尺寸越界 / 拓扑错误）+ 针对性提示，不直接转发原始 traceback |
| C-4 | L3 兜底方式 | 富化 Envelope（本地，带特征，STEP 有效），不默认调 Zoo.dev |
| C-5 | Zoo.dev 集成方式 | `pipeline_config.json` 加 `"enable_zoo_fallback": false`，显式 opt-in |
| C-6 | 多视角一致性实现方式 | shared seed + IP-Adapter reference（V1 增强结果作为 V2–V4 的视觉参考）|
| C-7 | IP-Adapter 对 FAL 的实现 | `enhance.fal.model`（默认 `fal-ai/flux-general`）已通过 `controlnets` 锁定几何；多视角一致性改为 **shared seed + 强度受控的 `controlnets[0].image_url` 替换为 V1 增强结果**，而非 `image_prompt`（后者为 flux-pro 专属参数，不适用于 flux-general ControlNet 路径）|
| C-8 | 向后兼容保证 | L0 路径代码不变；所有新路径在独立函数/条件分支中；现有测试不修改 |
| C-9 | L3 占位件标识 | 生成的 `.py` 文件头写入 `# ENRICHED_PLACEHOLDER — geometry approximated, not dimensionally accurate`；STEP 文件（ISO-10303-21 格式不支持 `#` 注释）**不**添加注释，下游通过读取对应 `.py` 的首行注释来识别占位件 |

---

## 3. 几何层——四级路由升级

### 3.1 路由链全貌

```
BOM 自制件
    │
    ├─ route() → HIT_BUILTIN / HIT_PROJECT
    │       └─ factory(params) 成功? ──────────────── L0 ✅ 质量最高（不变）
    │       └─ factory(params) 返回 None（缺参数）
    │               └─ _llm_extract_params() ──────── L1 ✅ 新增
    │                       └─ factory(extracted_params) 成功?
    │                       └─ 失败 ──────────────── 进入 L2
    │
    └─ route() → AMBIGUOUS（多模板同分命中）
    │       └─ 取 candidates[0]（最高 priority 者）→ 走 HIT_* 分支
    │
    └─ route() → FALLBACK（无模板命中）
            └─ _llm_generate_cadquery() ─────────────  L2 ✅ 新增
                    └─ 自我修正 ≤3 次
                    └─ 3 次仍失败?
                            ├─ enable_zoo_fallback=True → Zoo.dev API ── L3-opt ✅
                            └─ 默认 → _make_enriched_envelope() ──────── L3 ⚠️ 明确占位
```

### 3.2 L1 — LLM 参数提取

**触发条件**：`route()` 命中模板，但 `factory()` 返回 `None`（必填参数含 `None` 或 ≤0）。

**实现位置**：`gen_parts.py` 中 `_apply_template_decision()` 内，现有 `if code is None: # fallback` 分支之前。

**与现有代码的关系**：`gen_parts.py:539` 已有 `_extract_params(tpl_type, part_meta, envelope)` 函数，从 `part_meta["dim_tolerances"]`（格式：`[{"name": "FLANGE_BODY_OD", "nominal": "90"}, ...]`）读取参数。L1 的职责是**将 LLM 提取的数值补写回 `dim_tolerances` 列表**，而非绕开这套键名体系。

**新增函数**：

```python
def _llm_extract_params(
    part_name: str,
    spec_text: str,          # CAD_SPEC.md §2.1 相关段落 + §6.x envelope
    template_name: str,      # e.g. "flange"
    required_tol_keys: list, # ["FLANGE_BODY_OD", "FLANGE_BODY_ID", "FLANGE_TOTAL_THICK", "FLANGE_BOLT_PCD"]
    existing_dim_tols: list, # 已有的 dim_tolerances（已提取到的保留）
) -> list | None:
    """从 spec 文本补全 dim_tolerances 中缺失的参数条目。
    返回补全后的 dim_tolerances 列表；解析失败返回 None，不抛异常。"""
```

**Prompt 约束**：
- 要求 LLM 输出格式：`[{"name": "FLANGE_BODY_OD", "nominal": "90"}, {"name": "FLANGE_BOLT_PCD", "nominal": "65"}]`
- 键名必须与 `required_tol_keys` 中的条目一一对应
- 超时 10s，JSON 解析失败 → 返回 `None`；若 `route()` 结果为 `HIT_*` 则降级进入 L2；若 L2 亦被禁用则走 L3

**验收**：`ee_001_08`（法兰件）调用后 `_extract_params("flange", patched_meta, envelope)` 拿到完整参数，`make_flange()` 生成含螺栓孔几何，面数 ≥ 30。

### 3.3 L2 — LLM CadQuery 生成 + 自我修正

**触发条件**：`route()` 返回 `FALLBACK`。

#### Step 1 — 特征提取（chain-of-thought，不生成代码）

```
Prompt 要求输出:
{
  "base_shape": "cylinder | box | ...",
  "dimensions": {"od": ..., "h": ...},
  "features": [
    {"type": "hole_array", "count": 6, "pcd": 65, "dia": 8, "face": "top"},
    {"type": "chamfer",    "edge": "top_outer", "size": 2},
    ...
  ],
  "principal_axis": "Z"
}
```

不允许 LLM 在此步生成任何 Python 代码。

#### Step 2 — CadQuery 代码生成

```
Prompt 要求:
- 输入: Step 1 的特征 JSON + envelope 尺寸
- 输出: 一个 Python 函数 make_part() -> cq.Workplane
- 约束: 可 exec()，可 .val().exportStep()，不得 import 非标准库
```

#### Step 3 — 自我修正循环（≤3 次）

```python
for attempt in range(3):
    try:
        ns = {}
        exec(code, {"cq": cadquery}, ns)
        wp = ns["make_part"]()
        cq.exporters.export(wp, str(tmp_path))  # 项目统一 API，非 wp.val().exportStep()
        return code  # 成功：返回有效代码字符串
    except Exception as e:
        error_class = _classify_error(e)  # 4 类分类
        code = _llm_fix(code, error_class, str(e))
return None  # 3 次均失败
```

**错误分类函数 `_classify_error()`** 的 4 类：

| 类别 | 典型错误特征 | 反馈提示方向 |
|---|---|---|
| `INVALID_GEOMETRY` | `OCC StdFail_NotDone` / `BRep_TFace_Null` | "几何体存在自相交或零厚面，请检查 cut/union 顺序" |
| `API_SIGNATURE` | `TypeError: unexpected keyword` | "CadQuery API 签名错误，正确用法是：..." |
| `DIMENSION_OVERFLOW` | `ValueError` / 数值为负 / 零 | "尺寸参数越界，请检查 id < od，thickness > 0" |
| `TOPOLOGY_ERROR` | `Standard_ConstructionError` | "拓扑构造失败，建议拆分为多步 union 而非单步复合操作" |

### 3.4 L3 — 富化 Envelope（默认兜底）

**触发条件**：L2 三次失败，或 `enable_llm_codegen: false`。

**新增函数** `_make_enriched_envelope(type_hint, w, d, h, spec_text) -> cq.Workplane`：

| `type_hint` 关键词 | 添加特征 |
|---|---|
| `法兰 / 盘` | 中心通孔（id≈0.5×min(w,d)）+ 均匀 6 孔螺栓阵（PCD≈0.75×od）+ 顶面 2mm 倒角 |
| `壳体 / 筒` | 中心通孔 + 侧面矩形开口（0.3×w × 0.4×h）+ 底部 4 个安装凸台 |
| `支架 / 座` | 底面 4× 长圆孔 + 两侧安装耳片 + 3mm 整体圆角 |
| 其他 | box + 四棱柱 4mm 圆角 + 顶面中心沉孔（Φ10，深 5mm）|

输出 STEP 写入正常路径，但 `.py` 文件头写入：
```python
# ENRICHED_PLACEHOLDER — geometry approximated, not dimensionally accurate
```

### 3.5 L3-opt — Zoo.dev API（可选）

**启用方式**：`pipeline_config.json` 中：
```json
"enable_zoo_fallback": true,
"zoo_api_key": "${ZOO_API_KEY}"
```

**接入点**：L2 失败后，优先于富化 Envelope 执行。

```python
def _zoo_text_to_cad(part_name: str, description: str, envelope: tuple) -> Path | None:
    # POST https://api.zoo.dev/ai/text-to-cad
    # {"output_format": "step", "prompt": f"{part_name}: {description}"}
    # 轮询 job → 下载 STEP → 返回 Path，失败返回 None
```

失败时自动降级到富化 Envelope，不中断管线。

---

## 4. 视觉层——多视角联合增强

### 4.1 当前问题

```
enhance(V1, seed=random_A) → enhanced_V1
enhance(V2, seed=random_B) → enhanced_V2  ← 与 V1 材质色调可能完全不同
enhance(V3, seed=random_C) → enhanced_V3
enhance(V4, seed=random_D) → enhanced_V4
```

### 4.2 改进方案

```
shared_seed = pipeline_config["enhance"].get("shared_seed") or random.randint(0, 2**32)

enhance(V1, seed=shared_seed) → enhanced_V1
enhance(V2, seed=shared_seed, ip_ref=enhanced_V1)
enhance(V3, seed=shared_seed, ip_ref=enhanced_V1)
enhance(V4, seed=shared_seed, ip_ref=enhanced_V1)
```

### 4.3 FAL 实现

**现有 FAL 路径**：`fal-ai/flux-general`（可配置）通过 `controlnets` 列表传入 depth+canny，走 image-to-image 路径。

**多视角一致改进**：不引入 `image_prompt`（该参数为 `fal-ai/flux-pro` 系列专属，flux-general ControlNet 路径不支持）。改为：

1. `shared_seed`：4 次调用共享同一 `seed` 值（在 `api_args` 中传递），确保扩散过程的随机起点相同
2. `fal_enhancer.enhance_image()` 新增可选参数 `ip_ref_path: str | None = None`，当传入时将 V1 增强结果**替换** canny ControlNet 的 `control_image_url`（V2–V4 的 canny 参考改为 V1 增强图而非原始 Blender 渲染），强迫后续视角的风格向 V1 对齐

```python
# fal_enhancer.py 改动点
if ip_ref_path:
    # 上传 V1 增强结果作为 canny 参考
    ref_url = _upload_with_retry(ip_ref_path)
    controlnets[0]["control_image_url"] = ref_url  # 替换 canny 参考
```

`ip_strength` 从 `fal_cfg`（`enhance.fal` 子对象）读取，不在顶层 `enhance` 对象。

### 4.4 ComfyUI 实现

**注意**：现有 workflow 模板（12 节点）**不包含** IPAdapterNode，节点列表为：CheckpointLoaderSimple / CLIPTextEncode×2 / LoadImage / VAEEncode / ControlNetLoader×2 / Canny / ControlNetApply / KSampler / VAEDecode / SaveImage。

添加 IP-Adapter 支持需**新增节点**到 workflow JSON（IPAdapterModelLoader + IPAdapterAdvanced + 额外 LoadImage），改动量大于"激活已有节点"。

**Track C 阶段采用与 FAL 相同的简化策略**：用 V1 增强结果替换 canny ControlNet 的 LoadImage 输入节点（节点 `4`），不新增 IPAdapter 节点链——改动量最小，且保持与 FAL 实现策略对称。

```python
# comfyui_enhancer.py 改动点
if ip_ref_path:
    # 节点 4 = LoadImage（canny 参考图输入）
    workflow["4"]["inputs"]["image"] = _load_image_as_comfyui_path(ip_ref_path)
```

### 4.5 `pipeline_config.json` 新增字段

```json
"enhance": {
  "shared_seed": null,           // null = 每次随机但4视角共享；整数 = 固定复现
  "enable_multiview_ref": true,  // V2–V4 canny 参考图改为 V1 增强结果
  "fal": {
    "ip_strength": 0.3           // canny 控制强度微调（替换参考图后生效）
  }
}
```

`engineering` 后端（纯 PIL）不受影响，`shared_seed` 和 `enable_multiview_ref` 均忽略。

---

## 5. 文件改动清单

| 文件 | 改动类型 | 说明 |
|---|---|---|
| `src/cad_spec_gen/data/codegen/gen_parts.py` | 修改 | 加 `_llm_extract_params()` + `_llm_generate_cadquery()` + `_classify_error()` + `_make_enriched_envelope()` |
| `src/cad_spec_gen/data/python_tools/fal_enhancer.py` | 修改 | 加 `ip_ref_path` 参数 + shared_seed 支持 |
| `src/cad_spec_gen/data/python_tools/comfyui_enhancer.py` | 修改 | 激活 IPAdapterNode + shared_seed 支持 |
| `src/cad_spec_gen/data/python_tools/cad_pipeline.py` | 修改 | enhance 步骤串行传递 enhanced_V1 作为 ip_ref |
| `pipeline_config.json`（模板） | 修改 | 加 `enable_zoo_fallback` / `enable_llm_codegen` / `shared_seed` / `ip_strength` |
| `tests/test_llm_geometry.py` | 新增 | L1/L2/L3 单元测试 |
| `tests/test_multiview_consistency.py` | 新增 | SSIM 基准测试 |

---

## 6. 测试策略

### 6.1 L1 测试

```python
# 测试：给定法兰描述文字，LLM 能否补全 dim_tolerances 中缺失的参数
def test_l1_param_extraction_flange():
    spec_text = "法兰外径 90mm，中心孔 45mm，厚度 20mm，螺栓孔中心距 65mm，6 孔均布"
    required = ["FLANGE_BODY_OD", "FLANGE_BODY_ID", "FLANGE_TOTAL_THICK", "FLANGE_BOLT_PCD"]
    result = _llm_extract_params("法兰盘", spec_text, "flange", required, existing_dim_tols=[])
    assert result is not None
    names = {d["name"]: float(d["nominal"]) for d in result}
    assert abs(names["FLANGE_BODY_OD"] - 90) < 1
    assert int(names.get("FLANGE_BOLT_N", 6)) == 6
```

### 6.2 L2 测试

```python
# 测试：LLM 生成的代码字符串能通过自我修正并在验证时成功导出 STEP
def test_l2_codegen_spring_mechanism(tmp_path):
    code = _llm_generate_cadquery("弹簧限力机构", spec_text, envelope=(50, 50, 80))
    assert code is not None                  # 返回的是代码字符串，不是文件路径
    assert "cq.Workplane" in code or "cadquery" in code
    # 验证代码可执行且能导出有效 STEP
    ns = {}
    eval(compile(code, "<llm>", "exec"), {"cq": cadquery}, ns)  # noqa: S307
    wp = ns["make_part"]()
    out = tmp_path / "test.step"
    cq.exporters.export(wp, str(out))
    assert out.stat().st_size > 1000
```

### 6.3 L3 测试

```python
def test_l3_enriched_envelope_flange_hint():
    wp = _make_enriched_envelope("法兰座", 90, 90, 20, "")
    assert wp is not None
    faces = wp.val().Faces()
    assert len(faces) >= 15  # 比裸圆柱（3面）多得多
```

### 6.4 多视角一致性测试

```python
def test_multiview_shared_seed_payload_differs_from_independent():
    # 验证 ip_ref_path 传入时，FAL payload 的 canny control_image_url 确实被替换
    with patch("fal_enhancer._upload_with_retry", return_value="https://mock/ref.jpg") as mock_up:
        payload_with_ref = _build_fal_payload(png, fal_cfg, ip_ref_path="ref.png")
        payload_without  = _build_fal_payload(png, fal_cfg, ip_ref_path=None)
    assert payload_with_ref["controlnets"][0]["control_image_url"] == "https://mock/ref.jpg"
    assert payload_without["controlnets"][0]["control_image_url"] != "https://mock/ref.jpg"

# 注：engineering_enhancer 不涉及 seed 参数（纯 PIL 确定性操作），不在此测试
```

---

## 7. 实施顺序建议

```
Step C1: L1 参数提取（风险最低，2-3天）
    → 为已有模板补参数，立即可见改善，不涉及代码生成

Step C2: L3 富化 Envelope（无 LLM 风险，1-2天）
    → 替换裸 box fallback，改善"所有无模板件"视觉效果

Step C3: 多视角一致增强（视觉层，独立，2天）
    → fal_enhancer + comfyui_enhancer 改动，不影响几何

Step C4: L2 CadQuery 生成（最复杂，3-5天）
    → 在 C1/C3 基础上，为无模板件提供真正的 LLM 几何生成

Step C5: L3-opt Zoo.dev（可选，1天）
    → 仅当用户有需求时实现
```

---

## 附录 A：为什么不用图片转 3D 工具

| 工具 | 排除原因 |
|---|---|
| TripoSR / InstantMesh / Meshy | 输出三角网格（GLB/STL），无参数化信息，不能出工程图 |
| OpenSCAD + LLM | 编译输出 STL，同上 |
| BrepGen / DeepCAD | 研究原型，部署极难，无生产级 API |
| STEP-LLM | 2025 年研究前沿，尚未可用 |

**唯一满足"文字→工程可用 STEP + 开源可集成"的成熟方案 = CadQuery + LLM。**

## 附录 B：为什么 Zoo.dev 默认关闭

1. 质量不可控：无法保证机械零件的接口尺寸、螺栓孔位置准确
2. 外部强依赖：定价/服务变更无法控制
3. "兜底"场景 L2 失败时，Zoo.dev 面对同样描述未必更好
4. 工程原则：明确的占位件（富化 Envelope + 注释）比"看起来像真件但数据错误"的几何体更安全

## 附录 C：研究来源（2026-04-24 调研）

- Text-to-CadQuery 论文（2025）：自我修正将成功率 53% → 85%
- ICML 2025：视觉反馈注入 LLM 改善 CAD 代码质量
- NeurIPS 2024 Text2CAD Spotlight：多级文本到参数化 CAD
- BrepGen SIGGRAPH 2024：扩散模型 B-rep 生成（研究原型）
- Zoo.dev 官方文档：text-to-CAD API，STEP 输出
