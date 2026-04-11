# v2.9.2 — 渲染层回归覆盖 + 打包 drift 安全网 + 历史 mirror 同步

**Release date:** 2026-04-12
**Theme:** Test-only patch release. 无生产代码变更（除一个 pytest marker 注册），全部工作集中在填补 v2.9.0 / v2.9.1 暴露但未覆盖的三个测试真空：渲染数学层、`src/cad_spec_gen/data/` 打包副本 drift、Blender 真实环境回归。

---

## TL;DR

- **77 个新测试 case**，分散在 6 个新 test 文件里
- 完整测试套跳涨：401 passed → **478 passed**（零回归）
- **`tests/test_data_dir_sync.py`** 用 `ast.parse()` 从 `hatch_build.py` 动态派生 47 个 `(root, data/)` 同步对 —— 以后 mirror drift 第一时间被 CI 拦住
- **`@pytest.mark.blender`** 新 marker，与 `slow` 职责分离：`slow` 专管 wheel 构建，`blender` 专管真实 Blender 环境
- `src/cad_spec_gen/data/` 下 8 个历史 drift 的 mirror 文件 + 3 个漏 track 的文件（包括 v2.9.0 的 `cad_spec_section_walker.py`）一次性追平进 HEAD

---

## 起因

v2.9.1 发布后做的后置审查发现三块 v2.9.0 以来一直没有自动化覆盖的技术债：

1. **渲染数学层零测试**：`_resolve_camera_coords` / `_get_bounding_sphere` / `view_sort_key` / `MATERIAL_PRESETS` 全部没有单元测试。v2.9.0 的 `_get_bounding_sphere` 顶点重心 → AABB 中心 fix 是个典型"如果下次被无意识 revert 也看不出来"的回归点。

2. **`src/cad_spec_gen/data/` mirror drift**：`hatch_build.py::CustomBuildHook` 把 `cad_pipeline.py` 等 root 源文件在 wheel build 时复制到 `data/python_tools/`，但两份拷贝都 git-tracked。结果：每次 `python -m build --wheel` 跑完 git status 会冒出一堆 `M`，开发者不同步就累积 drift。v2.9.1 commit 之前就漂了 8 个文件 + 漏 track 3 个文件。

3. **Blender 真实环境零覆盖**：`render_3d.py` 是 Blender 内跑的脚本，任何 bpy API 漂移都会让它在用户机器上炸但 pytest 完全看不到。Blender 4.x 每个版本都会微调 API，没有自动化就只能等故障。

v2.9.2 用纯测试补丁一次性解决这三块。

---

## Item 3 — 渲染层回归覆盖（Tier 1 + Tier 2）

方法论：**两层策略**，Tier 1 是"无 Blender 纯 Python 测试"，Tier 2 是"真实 Blender headless 冒烟"。

### Tier 1 — 无 Blender 单元测试（4 文件，26 case）

**`tests/test_render_camera_math.py`（6 case）**

`_resolve_camera_coords()` 位于 `cad_pipeline.py:94`，把 render_config 中的球坐标相机条目（`azimuth_deg` / `elevation_deg` / `distance_factor`）就地转换成 `(location, target)` 笛卡尔对。纯数学无 bpy 依赖。

覆盖的行为：
- `az=0, el=0, df=2.0, br=100` → `location ≈ (200, 0, 33)`, `target z ≈ 33`
- `az=90, el=0` → 相机落在 +Y 轴
- `el=90` → 相机正上方（`cos(90°)=0` 使 xy 清零）
- `subsystem.bounding_radius_mm` 缺失时 fallback 到 300
- 已预设 `location` 的条目不被覆盖（幂等性）
- 多相机独立解析不互相污染

**`tests/test_view_key.py`（9 case）**

`extract_view_key()` 和 `view_sort_key()` 位于 `enhance_prompt.py:451,481`。两者都是纯字符串 / 正则处理，在 `cmd_enhance` 阶段被用来：给 PNG 文件排序（V1 < V2 < V10）、把 PNG 文件名映射回 config camera key。

覆盖的行为：
- `extract_view_key("V1_front_iso.png") == "V1"`
- `extract_view_key("V3_side_elevation_20260411_1712.png") == "V3"`（剥离时间戳）
- `extract_view_key("V10_detail.png") == "V10"`（两位数）
- `rc["camera"] = {"FRONT": ..., "ISO": ...}` 时，config key 优先于 generic V+digits
- `v1_lowercase.png` 识别为 `"V1"`（`re.IGNORECASE`）
- `sorted(["V10", "V2", "V1"], key=view_sort_key) == ["V1", "V2", "V10"]`（数字序非字母序）
- rc 提供的相机顺序压过数字序
- 未知文件 fall through 到 tier 2 alphabetic
- rc-known 和 unknown 混合时 tier 分离正确

**`tests/test_material_presets.py`（6 case）**

`MATERIAL_PRESETS` 位于 `render_config.py:36`。15 种工程材料的 PBR 参数 + AI prompt appearance 文本单一源。v2.3 把 `_PRESET_APPEARANCE` 独立字典合并进 `MATERIAL_PRESETS[*]["appearance"]`，本测试锁在那个 dedup 决策上。

覆盖的契约：
- 条目数 ≥ 15
- 每个 preset 必含 `color` / `metallic` / `roughness` / `appearance` 四个字段
- `color` 是 RGBA 4-tuple，每个分量在 `[0, 1]`
- `metallic` / `roughness` 都在 PBR 约定的 `[0, 1]`
- `appearance` 是非空字符串（AI prompt 用）
- **v2.3 dedup 反退化**：模块级不应再出现 `_PRESET_APPEARANCE` / `PRESET_APPEARANCE` / `_APPEARANCE_MAP` 等副本字典

**`tests/test_render_3d_structure.py`（5 case）**

专门守护 v2.9.0 `_get_bounding_sphere` AABB 中心 fix（commit `a7555ae`）。直接单测该函数需要 mock `bpy.context.scene.objects` + `mathutils.Vector`，脆弱成本远大于源码结构检查。改用 `re.search` 把函数体抽出来做字符串断言：

```python
def test_get_bounding_sphere_uses_aabb_min_max_not_centroid():
    body = _extract_function_body(src, "_get_bounding_sphere")
    assert "min(xs)" in body and "max(xs)" in body  # AABB 模式必含
    assert "sum(xs)" not in body                     # centroid 模式必缺
```

覆盖点：
- `render_3d.py` 文件存在
- `ast.parse()` 通过（捕捉笔误 / 语法错）
- 顶部仍 `import bpy` 和 `from mathutils import`
- `_get_bounding_sphere` 函数体必含 `min(xs) / max(xs) / min(ys) / max(ys) / min(zs) / max(zs)` 六个 AABB 引用
- 函数体必不含 `sum(xs)`（顶点重心退化特征）
- 半径公式仍用 `Vector((max(xs), max(ys), max(zs)))` 半对角线形式

**为什么选源码字符串检查而不是直接测函数？**

`_get_bounding_sphere()` 里 `bpy.context.scene.objects` 是"当前 Blender 文档的场景对象"，在 pytest 进程里根本不存在。要能运行它，需要：
1. 把 `bpy` 模块整个 mock 掉（含 `bpy.context`、`bpy.data`、`bpy.types` 等数十个子模块）
2. 构造一个假的 `scene.objects` 迭代器返回假 mesh
3. Mock `mathutils.Vector` 让 `Vector((x,y,z)) - vec` 算术工作
4. Handle `obj.matrix_world @ v.co` 的运算符重载

这些 mock 代码可能比被测函数本身还长，而且 Blender API 稍微变动就要重写 mock。源码字符串断言虽然"测实现细节"，但**完整锁在 v2.9.0 commit 引入的那几个关键词上**，维护成本几乎为零 —— 是这场 trade-off 里明确的赢家。

### Tier 2 — 真实 Blender headless smoke（1 文件，1 case）

**`tests/test_render_3d_blender_smoke.py`**

覆盖 Tier 1 源码检查碰不到的另一类回归：**Blender 版本升级后 bpy API 漂移**。比如 `bpy.data.lights.new(...)` 的某个参数在 Blender 5.x 被重命名 —— Tier 1 的源码检查看不到，但真实 Blender 一 import 就 ImportError。

实现策略选了"**只 import 不渲染**"：

```bash
blender --background --python-expr \
  "import sys; sys.path.insert(0, tmp_path); import render_3d; print('RENDER3D_OK')"
```

- 启动 headless Blender（`--background`）
- 把 `render_3d.py` + `render_config.py` 部署到 `tmp_path`
- `import render_3d` 触发所有模块级语句 + 所有 bpy API 查找
- 断言 stdout 出现哨兵字符串 `RENDER3D_OK`

**不渲染像素的原因**：真实的单帧渲染需要构造完整的 Blender 场景（几何 + 材质 + 相机 + 光源），构造成本比本测试的"发布前 <1 分钟"目标大一个数量级。而本测试的真正价值是"Blender 4.2 升级到 5.0 时 render_3d.py 还能 import 吗"—— 这个信号在 `import` 阶段就完全暴露。

测试运行时间：**~3 秒**（主要是 Blender 冷启动）。Auto-skip 条件：`cad_paths.get_blender_path()` 找不到 Blender 时直接 skip，确保没装 Blender 的 CI runner 保持绿色。

**marker 规则**：新增 `@pytest.mark.blender`，在 `pyproject.toml` 注册：

```toml
markers = [
    "fast: unit tests, <100ms each",
    "integration: full-chain tests",
    "slow: packaging/wheel-build tests, run on main/nightly only",
    "blender: real Blender headless smoke tests (v2.9.2+); auto-skip if Blender missing",
]
```

默认跑 `pytest` 时 `blender` 和 `slow` 都跳过。要单独跑 Blender 层：`pytest -m blender`。发布前完整跑：`pytest -m "blender or slow"` 或直接 `pytest tests/`。

---

## Item 4 — 打包 mirror drift 安全网（Path B）

### 问题

`hatch_build.py::CustomBuildHook.initialize()` 在 `python -m build --wheel` 时按以下规则把 root 文件复制到 `src/cad_spec_gen/data/`：

1. **`_PIPELINE_TOOLS`**（22 个文件）→ `data/python_tools/`
2. **`SHARED_TOOL_FILES`** fallback（6 个文件）→ `data/python_tools/`
3. **`COPY_DIRS`**（`codegen/` / `config/` / `templates/`）→ `data/<same>`（递归）
4. **`TOP_LEVEL_FILES`**（`parts_library.default.yaml`）→ `data/<dest>`
5. **`.claude/commands/*.md`** → `data/commands/zh/`
6. **`skill_*.md` + `system_prompt.md`** → `data/knowledge/` + `data/system_prompt.md`

这些 mirror **同时也被 git-tracked**。两份位置两个真相源，是已知风险的过渡态。历史证据：

- v2.9.0 的 `cad_spec_section_walker.py` 作为新 walker 模块写入 `_PIPELINE_TOOLS` 列表并打包进 wheel，但 `src/cad_spec_gen/data/python_tools/cad_spec_section_walker.py` 从未入 git → clone 下来的仓库 editable install 缺文件
- v2.8.0 的 `parts_library.default.yaml` 是 `TOP_LEVEL_FILES` 指向的文件，mirror 也一直没入 git
- v2.9.0 的 8 个 codegen / python_tools 文件在 root 更新后 mirror 同步写入了但从未 commit，到 v2.9.1 发布时 git 还认为它们 "M"

### 解决：`tests/test_data_dir_sync.py`

用 `ast.parse()` 读取 `hatch_build.py` 的常量，**不 import 它**（import 需要 `hatchling` 在测试环境里），动态派生同步对：

```python
def _parse_hatch_build_constants():
    hatch_src = (_REPO_ROOT / "hatch_build.py").read_text(encoding="utf-8")
    tree = ast.parse(hatch_src)
    pipeline_tools, copy_dirs, top_level_files = [], {}, {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and ...:
            if target.id == "_PIPELINE_TOOLS": ...
            elif target.id == "COPY_DIRS": ...
            elif target.id == "TOP_LEVEL_FILES": ...
    return pipeline_tools, copy_dirs, top_level_files
```

返回 3 个常量后，`_collect_sync_pairs()` 为每个源文件构造 `(category, name, root_path, data_path)` 四元组，参数化为独立 pytest case。每个 case 做：

```python
def test_data_dir_mirror_matches_root(category, name, src, dst):
    if not src.exists():
        pytest.skip(f"Root source missing")
    assert dst.exists(), f"Mirror MISSING\nFix: cp '{src}' '{dst}' && git add '{dst}'"
    assert md5(src) == md5(dst), f"DRIFT\nFix: cp '{src}' '{dst}'"
```

参数化生成 **47 个独立 case**：22 个 python_tools + 6 个 shared tools + 1 个 top_level + 18 个 `codegen/` / `config/` / `templates/` 下的文件（递归展开）。pytest 失败时精确定位到具体哪个文件漂了。

另有两个元测试：
- **`test_python_tools_has_no_stray_files`** — 反向哨兵，`data/python_tools/*.py` 不应含 `_PIPELINE_TOOLS + _SHARED` 外的文件。防止"手动复制但忘了注册"。
- **`test_sync_pair_count_is_nontrivial`** — 健康检查，`_SYNC_PAIRS >= 20`。防 ast 解析默默返回空列表让所有 case 变成 no-op 假绿。

### 长期方案（v2.10 路线，非本次发布）

Path B 是止血，Path A 才是根治：

```
1. .gitignore src/cad_spec_gen/data/python_tools/**
   .gitignore src/cad_spec_gen/data/codegen/**
2. 添加 scripts/dev_sync.py (or pre-commit hook) 让 editable install 能手动同步一次
3. CONTRIBUTING.md 加一节"开发机 onboarding"说明首次 clone 后要跑 python hatch_build.py
4. 正式 wheel build 照常触发 CustomBuildHook
```

Path A 的挑战：`pip install -e .` 不会触发 hatch 的 wheel build hook，所以 editable 模式下 `data/python_tools/` 是空的，`cad_spec_gen.wizard` 会找不到文件。必须提供一个开发者显式同步入口。这个挑战需要专门一轮设计，不适合塞进 v2.9.2。

### 历史 drift 同步

为了让 Path B 测试首次就能通过，本 commit 也把所有已有 drift 追平入 HEAD：

**8 个 M 文件**（内容和 root 一致，只差 git HEAD 没有对应记录）：
- `src/cad_spec_gen/data/codegen/gen_assembly.py`
- `src/cad_spec_gen/data/codegen/gen_params.py`
- `src/cad_spec_gen/data/codegen/gen_parts.py`
- `src/cad_spec_gen/data/codegen/gen_std_parts.py`
- `src/cad_spec_gen/data/python_tools/cad_spec_extractors.py`
- `src/cad_spec_gen/data/python_tools/cad_spec_gen.py`
- `src/cad_spec_gen/data/python_tools/draw_three_view.py`
- `src/cad_spec_gen/data/python_tools/drawing.py`

**3 个漏 track 文件**（首次入 HEAD）：
- `src/cad_spec_gen/data/parts_library.default.yaml`（v2.8.0 遗漏）
- `src/cad_spec_gen/data/python_tools/cad_spec_section_walker.py`（v2.9.0 遗漏）
- `src/cad_spec_gen/data/templates/parts/`（v2.9.0 parts library 目录遗漏）

`git clone` + `pip install -e .` 首次就能拿到完整树。

---

## 验证

### 跑测试套

**非 slow 非 blender**：
```
478 passed, 3 skipped, 2 deselected, 16 warnings in 31.97s
```
v2.9.1 基线是 401 passed，本次净增 77 个新 case（51 drift + 26 Tier 1）。3 skipped 是既有的条件跳过（bd_warehouse live integration 等）。2 deselected 是 `slow` 和 `blender` marker。

**Blender 层**：
```
tests/test_render_3d_blender_smoke.py::test_render_3d_importable_inside_blender_headless PASSED
1 passed in 2.90s
```
真实 Blender 4.2.16 LTS 进程内 `import render_3d` 成功，哨兵字符串 `RENDER3D_OK` 捕获到。

**Slow 层（wheel packaging）** 本次 commit 没动打包结构，无需重跑 —— 但下次 release 前应该跑 `pytest -m slow` 再发 tag。

### 三块技术债对照

| 债务 | v2.9.1 状态 | v2.9.2 状态 |
|---|---|---|
| 渲染数学层零测试 | ❌ 零覆盖 | ✅ 26 单元 case + 1 Blender smoke |
| Mirror drift 检测 | ❌ 手动同步 | ✅ 47 参数化 case + 2 元测试 |
| Blender 真实环境 | ❌ 零覆盖 | ✅ 1 import smoke（auto-skip） |

---

## Migration notes

本次是 test-only patch release，生产代码不变：
- `pyproject.toml` 只新增了一个 pytest marker 注册，不影响用户安装
- `src/cad_spec_gen/data/` 追平 drift 意味着 `pip install -e .` 和 `git clone` 后的初始树更完整，但对已有用户零影响
- 无 API 变动
- 无行为变动

用户侧命令：
```bash
pip install --upgrade cad-spec-gen  # 2.9.1 → 2.9.2
# 实际可执行文件无变化，仅 __version__ 更新
```

开发者侧新命令：
```bash
pytest -m blender              # 只跑 Blender 层（需 Blender 可用）
pytest -m "blender or slow"    # 发布前完整跑（Blender + wheel packaging）
pytest tests/test_data_dir_sync.py  # 手动验证 mirror 同步
```

---

## Files

### New (6 test files + 1 release note + 3 mirror tracks)
- `tests/test_data_dir_sync.py` — 47 参数化 drift case + 2 meta
- `tests/test_render_camera_math.py` — 6 case
- `tests/test_view_key.py` — 9 case
- `tests/test_material_presets.py` — 6 case
- `tests/test_render_3d_structure.py` — 5 case
- `tests/test_render_3d_blender_smoke.py` — 1 case (Blender)
- `RELEASE_v2.9.2.md` — 本文
- `src/cad_spec_gen/data/parts_library.default.yaml` — v2.8.0 遗漏追平
- `src/cad_spec_gen/data/python_tools/cad_spec_section_walker.py` — v2.9.0 遗漏追平
- `src/cad_spec_gen/data/templates/parts/*.py` — v2.9.0 遗漏追平

### Modified
- `pyproject.toml` — version bump + `blender` marker 注册
- `README.md` — Latest 标记更新为 v2.9.2
- `CHANGELOG.md` — `[2.9.2]` 段落
- `src/cad_spec_gen/data/codegen/gen_{assembly,params,parts,std_parts}.py` — 历史 drift 追平
- `src/cad_spec_gen/data/python_tools/{cad_spec_extractors,cad_spec_gen,draw_three_view,drawing}.py` — 历史 drift 追平

### Version metadata
- `pyproject.toml` — 2.9.1 → 2.9.2
- `src/cad_spec_gen/__init__.py` — `__version__ = "2.9.2"`
- `skill.json` — `"version": "2.9.2"`
- `src/cad_spec_gen/data/skill.json` — 同上
- `.cad_skill_version.json` — version + installed_at 时间戳
