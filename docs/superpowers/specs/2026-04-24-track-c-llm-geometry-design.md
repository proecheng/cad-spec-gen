# Track C — LLM 驱动几何生成 + 多视角一致增强 设计规格

> 版本: v0.4 — 2026-04-24
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
| C-6 | 多视角一致性实现方式 | `cad_pipeline.py` 已有 `reference_mode: "v1_anchor"` + `hero_image` 机制，但仅对 Gemini 后端生效（line 1939：`and backend == "gemini"`）。Track C 任务是**把该机制扩展到 FAL/ComfyUI 表驱动后端**，不重新设计 |
| C-7 | FAL/ComfyUI v1_anchor 扩展方式 | FAL：在 `_enhance_fn` 调用时把 `hero_image` 路径注入 `fal_cfg`（作为 `enhance.fal.hero_image`），`fal_enhancer` 内读取并替换 canny 参考图；ComfyUI：同理替换 LoadImage 节点 #4 输入；seed 通过 `enhance.fal.seed` / `enhance.comfyui.seed` 配置传递，不改动 `_enhance_fn` 签名 |
| C-8 | 向后兼容保证 | L0 路径代码不变；所有新路径在独立函数/条件分支中；现有测试不修改 |
| C-9 | L3 占位件标识 | 生成的 `.py` 文件头写入 `# ENRICHED_PLACEHOLDER — geometry approximated, not dimensionally accurate`；STEP 文件（ISO-10303-21 格式不支持 `#` 注释）**不**添加注释，下游通过读取对应 `.py` 的首行注释来识别占位件 |

---

## 3. 几何层——四级路由升级

### 3.1 路由链全貌

**前提说明**：当前 `generate_part_files()` 使用 `_match_template()`（`template_mapping_loader.py`）作为模板触发器；`route()`（`parts_routing.py`）已存在但**休眠**（仅输出日志预览）。Track C 方案 A：**激活 `route()` 取代 `_match_template()`**，统一路由入口，消除双系统冗余。

```
BOM 自制件
    │
    │  [Track C 新增] 以 route() 取代 _match_template()，成为唯一路由入口
    │
    ├─ route() → HIT_BUILTIN / HIT_PROJECT
    │       └─ _apply_template_decision() → code 非 None ─── L0 ✅ 质量最高（不变）
    │       └─ _apply_template_decision() → code = None（缺参数）
    │               └─ _llm_extract_params() → 补全 dim_tolerances
    │                       └─ _apply_template_decision() 再次尝试 → 成功 ─ L1 ✅
    │                       └─ 失败 → _llm_generate_cadquery(..., template_hint=tpl_type) ─ L2
    │                               （tpl_type 已知，作为 hint 注入 Step 1 Prompt 减少幻觉）
    │
    ├─ route() → AMBIGUOUS（多模板同优先级命中）
    │       └─ _pick_best(ambiguous_candidates) → 取得唯一最佳 → 走 HIT_* 分支
    │          （_pick_best 已有：按 -priority, tier=project, name 字母序排序）
    │
    └─ route() → FALLBACK
            ├─ reason = "empty part name" / "degenerate geometry" → ❌ 报错退出，不触发 LLM
            └─ reason = "no keyword match" / "disc_arms..." → L2 ✅ 新增
                    └─ _llm_generate_cadquery() + 自我修正 ≤3 次
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

**全模板键表**（从 `_extract_params()` 反推，`*` 为必填，其余可由 envelope 兜底）：

| template | 必填键 * | 可选键（缺失用 envelope 推算） |
|---|---|---|
| `flange` | `FLANGE_BODY_OD*`, `FLANGE_BODY_ID*`, `FLANGE_TOTAL_THICK*`, `FLANGE_BOLT_PCD*` | `FLANGE_BOLT_N`, `FLANGE_BOSS_H` |
| `housing` | `HOUSING_W*`, `HOUSING_D*`, `HOUSING_H*` | `HOUSING_WALL_T` |
| `bracket` | `BRACKET_W*`, `BRACKET_H*`, `BRACKET_T*` | — |
| `spring_mechanism` | `SPRING_OD*`, `SPRING_L*` | `SPRING_ID`, `SPRING_WIRE_D`, `SPRING_COIL_N` |
| `sleeve` | `SLEEVE_OD*`, `SLEEVE_L*` | `SLEEVE_ID` |
| `plate` | `PLATE_W*`, `PLATE_D*`, `PLATE_T*` | `PLATE_HOLE_N` |
| `arm` | `ARM_L*`, `ARM_W*`, `ARM_T*` | `ARM_END_HOLE_D` |
| `cover` | `COVER_OD*`, `COVER_T*` | `COVER_ID`, `COVER_BOLT_N` |

L1 仅提取缺失的必填键（`*`），已存在于 `dim_tolerances` 的键不覆盖。

**验收**：`ee_001_08`（法兰件）调用后 `_extract_params("flange", patched_meta, envelope)` 拿到完整参数，`make_flange()` 生成含螺栓孔几何，面数 ≥ 30。

### 3.3 L2 — LLM CadQuery 生成 + 自我修正

**触发条件**：`route()` 返回 `FALLBACK`（reason = "no keyword match" / "disc_arms"）。

**函数签名**：

```python
def _llm_generate_cadquery(
    part_name: str,
    spec_text: str,
    envelope: tuple[float, float, float],
    template_hint: str | None = None,   # L1 失败降级时传入已知模板类型（如 "flange"）
) -> str | None:
```

`template_hint` 由调用方在 L1 失败时传入，使 Step 1 Prompt 可提示 LLM"该件已知为 X 类型"，减少特征猜测幻觉。

#### Step 1 — 特征提取（chain-of-thought，不生成代码）

```
Prompt 要求输出（严格 JSON，不含 Markdown 代码块）:
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

**Step 1 失败处理**：JSON 解析失败（包括格式错误、LLM 混入解释文字）时，**跳过 Step 2，直接进入 L3**，不进行修正重试（Step 1 失败通常意味着描述信息本身不足，再试 Step 2 无意义）。

#### Step 2 — CadQuery 代码生成

```
Prompt 要求:
- 输入: Step 1 的特征 JSON + envelope 尺寸
- 输出: 严格仅一个 Python 函数 make_part() -> cq.Workplane，不含任何 import 语句
- 约束: 执行环境仅注入 cq（cadquery），不得引用其他库或全局变量
```

#### Step 3 — 自我修正循环（≤3 次，含首次）

```python
for attempt in range(3):
    try:
        ns: dict = {}
        exec(code, {"cq": cadquery}, ns)          # 统一用 exec()，测试与实现保持一致
        wp = ns["make_part"]()
        cq.exporters.export(wp, str(tmp_path))    # 项目统一 API，非 wp.val().exportStep()
        return code                               # 成功：返回有效代码字符串
    except Exception as e:
        error_class = _classify_error(e)
        code = _llm_fix(code, error_class, str(e))
return None  # 3 次均失败
```

**错误分类函数 `_classify_error()`** 的 6 类：

| 类别 | 触发异常类型 / 典型特征 | 反馈提示方向 |
|---|---|---|
| `SYNTAX_ERROR` | `SyntaxError` | "代码存在语法错误，请检查括号、缩进、引号是否配对，不得有 Markdown 标记" |
| `IMPORT_OR_NAME_ERROR` | `ImportError` / `NameError` / `AttributeError` | "执行环境仅提供 `cq`（cadquery），不得 import 其他库，所有变量须在 make_part() 内定义" |
| `INVALID_GEOMETRY` | `OCC StdFail_NotDone` / `BRep_TFace_Null` | "几何体存在自相交或零厚面，请检查 cut/union 顺序" |
| `API_SIGNATURE` | `TypeError: unexpected keyword` | "CadQuery API 签名错误，正确用法是：..." |
| `DIMENSION_OVERFLOW` | `ValueError` / 数值为负或零 | "尺寸参数越界，请检查 id < od，thickness > 0" |
| `TOPOLOGY_ERROR` | `Standard_ConstructionError` | "拓扑构造失败，建议拆分为多步 union 而非单步复合操作" |

**修复函数 `_llm_fix()`**：

```python
def _llm_fix(
    code: str,
    error_class: str,
    error_msg: str,
) -> str:
    """向 LLM 发送修复请求，返回修正后的代码字符串。
    LLM 不响应或返回格式无效时，原样返回 code（由上层 loop 继续重试）。"""
```

Prompt 结构（固定模板，不允许自由发挥）：

```
你是 CadQuery 代码修复助手。以下代码运行时出错，错误类型：{error_class}。

错误信息：
{error_msg}

修复方向：{_CLASSIFY_HINT[error_class]}

原代码：
```python
{code}
```

请返回修正后的完整 make_part() 函数，不含任何 import、不含说明文字，仅 Python 代码。
```

`_CLASSIFY_HINT` 为常量字典，键与 `_classify_error()` 6 类一一对应。返回值通过正则提取第一个 ` ```python ... ``` ` 块；提取失败则返回原 `code`。

### 3.4 L3 — 富化 Envelope（默认兜底）

**触发条件**：L2 三次失败，或 `enable_llm_codegen: false`。

**新增函数** `_make_enriched_envelope(tpl_type, w, d, h) -> cq.Workplane`：

`tpl_type` 参数**复用 `_BUILTIN_KEYWORDS` 的键名**（flange / housing / bracket / …），不另立关键词表。调用方从 `_match_template()` 或 `route().template.name` 已能拿到此值。

所有比例以**命名常量**定义，不散落魔法数字：

```python
_ENRICH_FLANGE_ID_RATIO   = 0.50   # 中心孔 id = od × 此值
_ENRICH_FLANGE_PCD_RATIO  = 0.75   # 螺栓孔 PCD = od × 此值
_ENRICH_HOUSING_SLOT_W    = 0.30   # 侧面开口宽 = w × 此值
_ENRICH_HOUSING_SLOT_H    = 0.40   # 侧面开口高 = h × 此值
_ENRICH_DEFAULT_FILLET    = 3.0    # mm，通用圆角
_ENRICH_DEFAULT_CBORE_D   = 10.0   # mm，默认沉孔直径
_ENRICH_DEFAULT_CBORE_H   = 5.0    # mm，默认沉孔深度
```

| `tpl_type` | 添加特征（使用上方常量） |
|---|---|
| `flange` | 中心通孔（`_FLANGE_ID_RATIO`）+ 均匀 6 孔螺栓阵（`_FLANGE_PCD_RATIO`）+ 顶面倒角 |
| `housing` | 中心通孔 + 侧面矩形开口（`_SLOT_W × _SLOT_H`）+ 底部 4 凸台 |
| `bracket` / `plate` / `arm` | 底面 4× 长圆孔 + `_DEFAULT_FILLET` 整体圆角 |
| 其他（cover / sleeve / spring_mechanism）| box + `_DEFAULT_FILLET` 圆角 + 顶面中心沉孔（`_CBORE_D × _CBORE_H`）|

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

## 4. 视觉层——多视角一致增强（扩展现有 v1_anchor）

### 4.1 现状分析

`cad_pipeline.py` 已实现完整的 `v1_anchor` 机制（lines 1842–2198）：
- `hero_image`：存储 V1 增强结果
- `reference_mode: "v1_anchor"`：已有 `pipeline_config.json` 配置键
- V1 作为后续视角参考图的逻辑完整

**当前限制**：`_use_ref` 条件（line 1935–1940）为：
```python
_use_ref = (
    _ref_mode == "v1_anchor"
    and hero_image
    and view_key != "V1"
    and backend == "gemini"   # ← 仅 Gemini 后端生效
)
```
`_enhance_fn` 表驱动路径（FAL / ComfyUI / fal_comfy 后端）完全绕过此逻辑。

### 4.2 Track C 目标：扩展到 FAL / ComfyUI

**改动策略**：不修改 `_enhance_fn` 函数签名（避免破坏所有后端接口），而是在调用前把 `hero_image` 路径**注入到 cfg dict** 中，各后端自行读取。

```python
# cad_pipeline.py 改动（_enhance_fn 调用处）
enhance_cfg = _pcfg.get("enhance", {}).get(_enhance_cfg_key, {})
if (_ref_mode == "v1_anchor" and hero_image
        and view_key != "V1" and backend in ("fal", "comfyui", "fal_comfy")):
    enhance_cfg = dict(enhance_cfg)          # 浅拷贝，不污染原 cfg
    enhance_cfg["hero_image"] = hero_image   # 注入 V1 参考路径
raw_path = _enhance_fn(png, prompt, enhance_cfg, view_key, rc)
```

### 4.3 FAL 实现

`fal_enhancer.enhance_image()` 读取 `fal_cfg.get("hero_image")`：

```python
hero = fal_cfg.get("hero_image")
if hero and os.path.isfile(hero):
    ref_url = _upload_with_retry(hero)
    controlnets[0]["control_image_url"] = ref_url  # 替换 canny 参考为 V1 增强图
```

Seed 固定复现：在 `api_args` 中加 `"seed": fal_cfg.get("seed")` （None 时不传，保持随机）。

### 4.4 ComfyUI 实现

`comfyui_enhancer.enhance_image()` 读取 `comfyui_cfg.get("hero_image")`，替换 LoadImage 节点 `"4"` 的输入（该节点是 canny 参考图来源，已确认于 12 节点模板中）：

```python
hero = cfg.get("hero_image")
if hero and os.path.isfile(hero):
    workflow["4"]["inputs"]["image"] = _load_image_as_comfyui_path(hero)
```

### 4.5 `pipeline_config.json` 变更

Track C **复用现有配置键**，不新增：

```json
"enhance": {
  "reference_mode": "v1_anchor",  // 已有键，之前仅 Gemini 生效；Track C 扩展到 fal/comfyui
  "fal": {
    "seed": null                  // null = 每次随机；整数 = 固定复现（新增子键）
  },
  "comfyui": {
    "seed": null                  // 同上（新增子键）
  }
}
```

`engineering` 后端（纯 PIL）和 `gemini` 后端行为不变。

---

## 5. 文件改动清单

| 文件 | 改动类型 | 说明 |
|---|---|---|
| `src/cad_spec_gen/data/codegen/gen_parts.py` | 修改 | 加 `_llm_extract_params()` + `_llm_generate_cadquery()` + `_classify_error()` + `_make_enriched_envelope()` |
| `src/cad_spec_gen/data/python_tools/fal_enhancer.py` | 修改 | 从 cfg dict 读取 `hero_image` 路径，替换 canny 参考图；读取 `fal_cfg.get("seed")` 注入 api_args |
| `src/cad_spec_gen/data/python_tools/comfyui_enhancer.py` | 修改 | 从 cfg dict 读取 `hero_image`，替换 LoadImage 节点 `"4"` 输入；读取 `comfyui_cfg.get("seed")` |
| `src/cad_spec_gen/data/python_tools/cad_pipeline.py` | 修改 | `_enhance_fn` 调用前把 `hero_image` 注入 enhance_cfg dict（浅拷贝，不改 `_enhance_fn` 签名） |
| `pipeline_config.json`（模板） | 修改 | 加 `enable_zoo_fallback` / `enable_llm_codegen` / `enhance.fal.seed` / `enhance.comfyui.seed` |
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
    # 验证代码可执行且能导出有效 STEP（与实现层 exec 写法保持一致）
    ns: dict = {}
    exec(code, {"cq": cadquery}, ns)  # noqa: S102
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
