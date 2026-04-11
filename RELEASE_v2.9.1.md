# v2.9.1 — 真实设计文档端到端回归 + 四个 skill bug 修复

**Release date:** 2026-04-11
**Theme:** 用 GISBOT 末端执行机构章节走完一遍 spec → codegen → build → render → enhance → annotate 的完整管线，把跑出来的 skill bug 一次性修掉。无新功能，全部是稳定性 / 一致性补丁。

---

## TL;DR

- **`engineering_enhancer.py` 新建**：`pipeline_config.json` 一直登记 `engineering` 作为合法的 enhance 后端，但真正的实现从未入库。用户选 `--backend engineering` 会被静默降级到 gemini。v2.9.1 补齐这个零成本、零 AI 依赖的兜底后端。
- **`assembly_validator.py` 适配 v2.9 `parse_envelopes` dict 返回值**：v2.9.0 把 `{pno: (w,d,h)}` 改成了 `{pno: {"dims": (w,d,h), "granularity": str}}`，但 GATE-3.5 的 validator 没跟上，触发 `TypeError: '<' not supported between instances of 'str' and 'float'`，每次 build 末尾都会抛错。
- **`check_env.py` 读 `pipeline_config.json` 的 `blender_path`**：之前 `cad_paths.get_blender_path()` 能找到 Blender，但 `check_env.py` 找不到，导致环境自检误报 Level 3 CAD。两边逻辑现在一致。
- **`cad_pipeline.py enhance --backend engineering`**：argparse choices 漏了 `engineering`，CLI 直接报 `invalid choice`；`cmd_enhance` 内部 dispatch 也没有对应分支。两处都补齐。

---

## 起因：一次完整的端到端测试

在 v2.9.0 发布后，用户要求把 skill 拉出来在 `D:\Work\cad-tests\04-末端执行机构设计.md`（GISBOT 末端执行机构章节）上做一次全流程测试：中间产物和最终结果全部落在 `D:\Work\cad-tests\GISBOT\`，并约定"如果 skill 有错误，请修改"。

整个管线分成 6 个阶段：

| Phase | 命令 | 关键产物 |
|---|---|---|
| 1 SPEC | `cad_pipeline.py spec --auto-fill` | `CAD_SPEC.md` + `DESIGN_REVIEW.{md,json}` |
| 2 CODEGEN | `cad_pipeline.py codegen --force` | `params.py` / `build_all.py` / `assembly.py` / `ee_*.py` / `std_*.py` |
| 3 BUILD | `cad_pipeline.py build` | `*.step` (26) + `*.dxf` (11) + `EE-000_assembly.{step,glb}` + GATE-3.5 `ASSEMBLY_REPORT.json` |
| 4 RENDER | `cad_pipeline.py render` | `V1..V7_*.png` (7 views × Blender Cycles) |
| 5 ENHANCE | `cad_pipeline.py enhance --backend engineering` | `V*_enhanced.jpg` (7) |
| 6 ANNOTATE | `cad_pipeline.py annotate --lang cn` | `V*_enhanced_labeled_cn.jpg` (7) |

Phases 1、2、4、6 一次跑通，Phase 3 和 Phase 5 各自暴露了 v2.9.0 遗留 / 未实现的 bug。

---

## Bug #1 — `check_env.py` 漏读 `pipeline_config.json`

**症状**：`cad_pipeline.py env-check` 报 Blender `not found`，落在 Level 3 CAD，但 `pipeline_config.json` 里明明有 `"blender_path": "D:/Blender/blender.exe"` 且后续 `cad_pipeline.py render` 能正常调用 Blender 渲染。

**根因**：`tools/hybrid_render/check_env.py::_find_blender()` 只查了 3 个位置：
1. `BLENDER_PATH` 环境变量
2. `tools/blender/blender.exe` 项目内便携版
3. `shutil.which("blender")` PATH 查找

但 `cad_paths.get_blender_path()`（实际管线使用的）多查了一个：**`pipeline_config.json.blender_path`**。两边逻辑分叉，产生了"自检失败但管线能跑"的诡异状态。

**修复**：`_find_blender()` 按以下优先级查找（与 `cad_paths.get_blender_path()` 完全一致，外加平台默认位置）：

```
1. BLENDER_PATH 环境变量
2. pipeline_config.json blender_path  ← 新增
3. skill_root/tools/blender/blender.exe
4. skill_root/tools/blender/blender  (Linux/Mac)
5. shutil.which("blender")
6. 平台默认：                          ← 新增
   - %ProgramFiles%\Blender Foundation\Blender\blender.exe
   - /usr/bin/blender
   - /Applications/Blender.app/Contents/MacOS/Blender
```

---

## Bug #2 — `assembly_validator.py` 未适配 v2.9 `parse_envelopes` 返回值

**症状**：Phase 3 build 末尾的 GATE-3.5 `assembly_validator.py` 报错：

```python
TypeError: '<' not supported between instances of 'str' and 'float'
  File "assembly_validator.py", line 192, in check_f2_size_mismatch
    if e_sorted[k] < 0.1:
```

STEP、DXF、PNG 都已正常产出，GLB 装配体已完成 consolidate（330 components → 39 parts），但 validator 本身挂掉了，ASSEMBLY_REPORT.json 无法写入。

**根因**：v2.9.0 的 `codegen/gen_assembly.py::parse_envelopes` 为了承载粒度元数据，把返回值 shape 从 `{pno: (w,d,h)}` 升级成了 `{pno: {"dims": (w,d,h), "granularity": str}}`：

```python
# v2.9.0 onward
envelopes[pno] = {"dims": _parse_dims_text(dims_text + " mm"),
                  "granularity": gran_text or "part_envelope"}
```

`codegen/gen_parts.py` 和 `codegen/gen_params.py` 的旧调用方加了 `isinstance(env, dict)` 向后兼容分支，但 `assembly_validator.py`（位于 skill root，不在 `codegen/` 包内）被漏掉了。它继续按 3-tuple 使用：

```python
expected = envelopes[pno]           # 现在是 dict，不再是 tuple
a_sorted = sorted(actual, reverse=True)
e_sorted = sorted(expected, reverse=True)   # 对 dict 排序 → 得到 dict 的 keys 列表 ["granularity", "dims"]
for k in range(3):
    if e_sorted[k] < 0.1:           # str < float → TypeError
```

第二次 bug 的潜伏位置是 `check_f3_compactness`：

```python
for pno, env in envelopes.items():
    if pno.startswith(prefix):
        heights.append(env[2])      # dict[2] 会抛 KeyError
```

**修复**：新加一个 `_envelope_dims(env)` 适配器，容忍 tuple 和 dict 两种 shape，然后让 `check_f2_size_mismatch` 和 `check_f3_compactness` 都走它：

```python
def _envelope_dims(env) -> tuple:
    """将 envelope 条目规整为 (w, d, h) 三元组。

    v2.9.0 把 parse_envelopes() 返回值改成了
        {part_no: {"dims": (w, d, h), "granularity": str}}
    旧调用方仍然传原始 3-tuple。两种都接受。
    """
    if isinstance(env, dict):
        return env.get("dims") or (0.0, 0.0, 0.0)
    return tuple(env)
```

GATE-3.5 现在不再抛错，正常写入 `ASSEMBLY_REPORT.json`。真实测试中它报了 5 条合法设计告警（4 条 F1 floating + 1 条 F2 size mismatch），都是被 v2.9.0 bug 遮住的真实问题。

---

## Bug #3 — `--backend engineering` 被 argparse 拒绝

**症状**：

```
$ cad_pipeline.py enhance --subsystem end_effector --backend engineering
cad_pipeline.py enhance: error: argument --backend:
  invalid choice: 'engineering' (choose from gemini, comfyui, fal, fal_comfy)
```

但 `pipeline_config.json` 的 `_backend_doc` 明确写着：

```json
"_backend_doc": "Options: 'gemini' ... | 'engineering' (no AI, Blender PBR direct, free)..."
```

`skill.json` 的 `cad-enhance` skill 描述也承诺 4 个后端包含 `engineering`。

**根因**：`p_enhance.add_argument("--backend", choices=[...])` 的 choices 列表漏写了 `"engineering"`。自 v2.3 引入该文档起从未被真实测过。

**修复**：

```python
p_enhance.add_argument("--backend",
                       choices=["gemini", "comfyui", "fal", "fal_comfy", "engineering"],
                       help="Override enhance backend (default: from pipeline_config.json). "
                            "'engineering' = no AI, Blender PBR direct + post-processing.")
```

---

## Bug #4 — `engineering` 后端从未被实现

**症状**：即便修掉 Bug #3 的 argparse，传入 `backend == "engineering"` 也会被 `cmd_enhance` 的 dispatch `else:` 分支吞掉并悄悄重置为 `"gemini"`：

```python
if backend == "comfyui":
    ...
elif backend in ("fal", "fal_comfy"):
    ...
else:
    backend = "gemini"   # normalise
    gemini_script = get_gemini_script()
```

换句话说，这个后端从 v2.3 开始就只存在于文档和 config 里，代码从来没写过。没人 CI 能抓到，只有完整跑一次管线才会暴露。

**根因**：半完成功能沉积。`pipeline_config.json` 的 `enhance.engineering` 段落连参数都列齐了：

```json
"engineering": {
  "_doc": "No AI — Blender PBR render → light post-processing → JPG. Perfect geometry, zero cost.",
  "sharpness": 1.3,
  "contrast": 1.1,
  "quality": 95
}
```

但对应的 `engineering_enhancer.py` 不存在，cmd_enhance 的 dispatch 也没写 branch。

**修复**：

1. 新建 `engineering_enhancer.py`（~75 行），函数签名与 `comfyui_enhancer.enhance_image()` / `fal_enhancer.enhance_image()` 严格一致：

```python
def enhance_image(png_path: str, prompt: str, engineering_cfg: dict,
                  view_key: str, rc: dict) -> str:
    """将 Blender PNG 转为工程风格的 JPG。

    步骤：
      1) 以 RGB 模式打开源图（若为 RGBA，合成到纯白背景避免透明）
      2) 依次应用 ImageEnhance.Contrast / Sharpness / Color
      3) 保存到临时 .jpg 文件，返回路径
    """
```

参数全部从 `pipeline_config.json["enhance"]["engineering"]` 读取，支持 `sharpness` / `contrast` / `saturation` / `quality` 四项，与文档声明一致。

2. 在 `cad_pipeline.py::cmd_enhance` 的 dispatch 表加一个分支：

```python
elif backend == "engineering":
    # 零 AI 工程后端：Blender PBR PNG → PIL 轻量后处理 → JPG。
    # 无外部依赖（仅 Pillow），用于兜底 / 离线 / 零成本场景。
    from engineering_enhancer import enhance_image as _eng_fn
    _enhance_fn, _enhance_cfg_key = _eng_fn, "engineering"
```

这样它就走和 comfyui / fal / fal_comfy 同样的 table-driven dispatch 路径，自动获得 v1 anchor / reference / seed 注入的所有已有逻辑（尽管 engineering 本身都用不上）。

3. 在打包清单里同步：
   - `hatch_build._PIPELINE_TOOLS` — 让 wheel 包含 `engineering_enhancer.py`
   - `cad_spec_gen.wizard.skill_register._PIPELINE_TOOLS` — 让 `cad-skill-setup` 在用户项目根部署这个文件
   - `src/cad_spec_gen/data/python_tools/engineering_enhancer.py` — 同步打包副本
   - `.cad_skill_version.json` — 加入 md5 哈希，让 `cad-skill-check` 能识别

---

## 端到端验证结果

修复后把 GISBOT 目录全部清空，按 `CAD_PROJECT_ROOT=D:/Work/cad-tests/GISBOT` 环境变量跑完整条管线。产物清单：

| 类别 | 数量 | 位置 |
|---|---|---|
| `CAD_SPEC.md` | 2 份（源 + 部署） | `output/end_effector/` · `cad/end_effector/` |
| `DESIGN_REVIEW.{md,json}` | 2 对 | 同上 |
| STEP 3D 文件 | 26（11 自制 + 14 std + 1 assembly） | `cad/output/*.step` |
| DXF 2D 工程图 | 11 | `cad/output/EE-*.dxf` |
| 2D 工程图 PNG | 11 | `cad/output/EE-*.png` |
| Blender 3D 渲染 PNG | 14（7 views × 2 timestamp 副本） | `cad/output/renders/V*.png` |
| engineering 增强 JPG | 7 | `cad/output/renders/V*_enhanced.jpg` |
| 中文标注 JPG | 7 | `cad/output/renders/V*_labeled_cn.jpg` |
| GLB 装配体 | 1 | `cad/output/EE-000_assembly.glb` |
| ASSEMBLY_REPORT.json | 1 | `cad/output/ASSEMBLY_REPORT.json` |

Phase 1-6 全部 `OK`，GATE-3.5 从"crash"变成"5 条合法设计 WARNING"。engineering 后端在 ~1 秒内完成 7 张图的后处理（对比 Gemini 云 API 每张 20-60 秒）。

---

## Migration notes

本次是 bug-fix patch release，不改动 API 契约：

- **使用 `parse_envelopes()` 的外部代码**：如果你在项目中独立调用了 `codegen.gen_assembly.parse_envelopes`，v2.9.0 已经把返回值从 tuple 变成 dict，本次 release 没有再改。如果你的调用方还在当 tuple 用，请参考 `assembly_validator._envelope_dims()` 写一个适配器。
- **`--backend engineering`**：从本版开始真正可用。若之前 CI 里写了 `--backend engineering || --backend gemini` 的降级链，降级分支可以去掉了。
- **`cad-skill-setup` 升级**：旧安装升级到 v2.9.1 后会新增部署 `engineering_enhancer.py`。无用户可见变化，除非用户有自定义的 `engineering_enhancer.py` —— 此时 `cad-skill-check` 会提示冲突，按正常 upgrade 流程选择保留/覆盖即可。

---

## Files

### New
- `engineering_enhancer.py` — 零 AI 工程后端实现
- `src/cad_spec_gen/data/python_tools/engineering_enhancer.py` — 打包副本
- `RELEASE_v2.9.1.md` — 本文

### Modified
- `tools/hybrid_render/check_env.py` — `_find_blender()` 增加 pipeline_config.json + 平台默认路径 fallback
- `assembly_validator.py` — 增加 `_envelope_dims()` 适配器，`check_f2_size_mismatch` / `check_f3_compactness` 走新函数
- `cad_pipeline.py` — `p_enhance.add_argument` choices 增加 `"engineering"`；`cmd_enhance` 增加 `elif backend == "engineering"` 分支
- `src/cad_spec_gen/data/python_tools/cad_pipeline.py` — 同步打包副本
- `hatch_build.py` — `_PIPELINE_TOOLS` 增加 `engineering_enhancer.py`
- `src/cad_spec_gen/wizard/skill_register.py` — `_PIPELINE_TOOLS` 增加 `engineering_enhancer.py`
- `README.md` — 顶部 Latest 标记更新为 v2.9.1
- `CHANGELOG.md` — [2.9.1] 段落

### Version metadata
- `pyproject.toml` — 2.9.0 → 2.9.1
- `src/cad_spec_gen/__init__.py` — `__version__ = "2.9.1"`
- `skill.json` — `"version": "2.9.1"`
- `src/cad_spec_gen/data/skill.json` — 同上
- `.cad_skill_version.json` — version + `cad_pipeline.py` 哈希更新 + `engineering_enhancer.py` 新条目
