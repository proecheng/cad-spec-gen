# A1 重构：SW 纹理运行时回填层 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Task 2-6 硬编码到 `render_config.py` 的 18 个 SW 纹理路径**移出分发物**，改为运行时检测 SW 装机后由独立回填模块注入；SW 未装时 preset 零污染（回到 v2.11 纯 PBR 形态，无任何 SW 路径字符串）。保留 3 个 v2.12 新 preset（abs_matte_gray/ceramic_white/carbon_fiber_weave）的纯 PBR 定义。

**Architecture:**
- `render_config.py` MATERIAL_PRESETS 回到 **纯 PBR 定义**（v2.11 字段 + 3 新 preset 的 color/metallic/roughness/appearance/ior/specular）
- 新 `adapters/solidworks/sw_texture_backfill.py`：
  - `PRESET_TO_SW_TEXTURE_MAP: dict[str, dict]`（18 映射，作为运行时实现细节）
  - `backfill_presets_for_sw(presets: dict, sw_info: SwInfo | None) → dict`（返回 copy；SW 未装/textures_dir 缺失 → no-op 返回原输入）
- `cad_pipeline._build_blender_env()` 扩展：探到 SW → 调回填 → 写 `artifacts/{run_id}/runtime_materials.json` → env `CAD_RUNTIME_MATERIAL_PRESETS_JSON` 指该路径
- `render_3d.py` 启动：读 env → JSON 覆盖 MATERIAL_PRESETS 副本；env 缺/JSON 缺 = 用内置纯 PBR（SW 未装行为）
- 公众 wheel 查 strings `"metal/brushed/brush.jpg"` 等 **只存在于 `sw_texture_backfill.py`**（即"程序回填"的实现细节），不在 preset 定义里

**Tech Stack:** Python 3.11 stdlib (json/os/pathlib) / pytest / 复用 A1-3 `_build_blender_env()` / 复用 `detect_solidworks()`。

**Base commit for this refactor:** `b0a71de`（Task 6 完成点；Task 1 gate test 已存在但需重写）

---

## File Structure

| 文件 | 动作 | 职责 |
|---|---|---|
| `render_config.py` | 修改 | 移除 18 个 preset 的 SW 路径字段；保留 3 个新 preset 的纯 PBR 定义（不带 base_color_texture） |
| `src/cad_spec_gen/data/python_tools/render_config.py` | 修改 | 同步 |
| `adapters/solidworks/sw_texture_backfill.py` | 新增 | `PRESET_TO_SW_TEXTURE_MAP` + `backfill_presets_for_sw()` |
| `tests/test_sw_texture_backfill.py` | 新增 | backfill 模块单元测试 + 分类覆盖 gate（**替代** test_a14_preset_texture_coverage 的分类测试）|
| `tests/test_a14_preset_texture_coverage.py` | 修改 | 改测"preset 无 SW 字段" + "backfill map 覆盖率 ≥10"（语义转换为"分发物干净性" + "映射表完整性"） |
| `cad_pipeline.py` | 修改 | `_build_blender_env()` 扩展：回填 → JSON 落盘 → env 注入 |
| `src/cad_spec_gen/render_3d.py` | 修改 | 启动读 `CAD_RUNTIME_MATERIAL_PRESETS_JSON` → 覆盖 MATERIAL_PRESETS 副本 |
| `tests/test_render_3d_existing_presets_no_regression.py` | 新增（Task 7 原设计调整） | v2.11 preset 名仍在 + 零 SW 字符串污染 |
| `tests/test_render_3d_texture_bridge.py` | 修改（原 Task 8） | smoke 两条路径：env 注入 JSON 挂贴图 vs 无 env 纯标量 |

---

### Task R1: 清除 render_config.py 的 SW 纹理字段（RED → GREEN）

**Rationale:** Task 2-5 把 18 条 SW 路径硬编码进 preset。回到 v2.11 纯 PBR 形态，但 3 个新 preset 的纯 PBR 定义保留（color/metallic/roughness 等）。

**Files:**
- Modify: `render_config.py`（删每个 preset 的 `base_color_texture / normal_texture / roughness_texture / metallic_texture` 四字段 + 相关 comment marker）
- Modify: `src/cad_spec_gen/data/python_tools/render_config.py`（同步）

- [ ] **Step 1: 写 RED 测试锁"preset 不含 SW 字符串"**

新建 `tests/test_render_config_no_sw_strings.py`：

```python
"""Track A1 重构验收：MATERIAL_PRESETS 分发物不含 SW 纹理路径字符串。

用户北极星"SW 装即用 / SW 未装零感知"要求：render_config.py 的 preset 定义
只含纯 PBR 标量（color/metallic/roughness/appearance/ior/specular/sss/sss_color/
anisotropic）。SW 纹理路径在 adapters/solidworks/sw_texture_backfill.py 里
作为运行时回填实现细节，不污染 preset 层。
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import render_config as rcfg


# 允许的 preset 字段白名单（v2.11 原有 + 3 新 preset 可能用的）
ALLOWED_PRESET_FIELDS = {
    "color", "metallic", "roughness", "anisotropic",
    "ior", "specular", "sss", "sss_color",
    "appearance",
    # label 由 resolve_material 动态注入，非 preset 静态字段但允许
    "label",
}

FORBIDDEN_SW_TEXTURE_FIELDS = {
    "base_color_texture", "normal_texture",
    "roughness_texture", "metallic_texture",
    "texture_scale",
}


def test_no_preset_has_sw_texture_fields():
    """分发物约束：MATERIAL_PRESETS 不应含任何 SW 纹理路径字段。"""
    violations = []
    for name, params in rcfg.MATERIAL_PRESETS.items():
        forbidden = FORBIDDEN_SW_TEXTURE_FIELDS & set(params)
        if forbidden:
            violations.append(f"{name}: {sorted(forbidden)}")
    assert not violations, (
        f"preset 含 SW 纹理字段（应移到 sw_texture_backfill.py）：{violations}"
    )


def test_preset_fields_are_all_pbr_scalars():
    """preset 字段必须全在 PBR 标量白名单内（除字符串 appearance）。"""
    violations = []
    for name, params in rcfg.MATERIAL_PRESETS.items():
        unknown = set(params) - ALLOWED_PRESET_FIELDS
        if unknown:
            violations.append(f"{name}: {sorted(unknown)}")
    assert not violations, (
        f"preset 含未知字段（白名单外）：{violations}"
    )


def test_no_sw_path_string_in_preset_values():
    """更严：preset 字符串值里不应出现 SW 纹理目录结构常见字符串。"""
    sw_markers = ("metal/", "plastic/", "painted/", "rubber/", "fibers/", "_bump.jpg")
    violations = []
    for name, params in rcfg.MATERIAL_PRESETS.items():
        for field, value in params.items():
            if isinstance(value, str):
                for marker in sw_markers:
                    if marker in value:
                        violations.append(f"{name}.{field}={value!r} 含 SW 标记 {marker!r}")
    assert not violations, f"preset 字符串值含 SW 标记：{violations}"
```

- [ ] **Step 2: 跑测试确认 RED**

Run: `/d/Work/cad-spec-gen/.venv/Scripts/python.exe -m pytest tests/test_render_config_no_sw_strings.py -v`

Expected: 3 FAIL（每个测试都炸，因为 Task 2-5 给 18 preset 加了 SW 字段 + SW 路径字符串）。

- [ ] **Step 3: Edit render_config.py — 移除所有 SW 纹理字段 + comment marker**

逐个 preset 删除以下 4 字段 + 其上方的 `# ── Track A1-4 纹理回填 ──` 或 `# ── Track A1-4 纹理回填（相对 SW_TEXTURES_DIR）──` comment 行：

```python
        # ── Track A1-4 纹理回填 ──   ← 删这行
        "base_color_texture": "...",   ← 删这行
        "normal_texture": ...,         ← 删这行
        "roughness_texture": None,     ← 删这行
        "metallic_texture": None,      ← 删这行
```

**保留**以下 preset 的新增（它们含纯 PBR 定义）：
- `abs_matte_gray`：保 color / metallic / roughness / appearance
- `ceramic_white`：保 color / metallic / roughness / ior / specular / appearance
- `carbon_fiber_weave`：保 color / metallic / roughness / anisotropic / appearance

这 3 个 preset 的注释 `# ── Track A1-4 新增：... ──` 也**调整措辞**（因为不再是"纹理回填"了）：
```python
    # ── v2.12 新增：塑料分类补足 ──
    # ── v2.12 新增：橡胶·陶瓷分类补足 ──
    # ── v2.12 新增：PEEK·复合分类补足 ──
```

- [ ] **Step 4: 跑 RED 测试 → 现在应 GREEN**

Run: `/d/Work/cad-spec-gen/.venv/Scripts/python.exe -m pytest tests/test_render_config_no_sw_strings.py -v`

Expected: 3 PASS。

- [ ] **Step 5: 同步 packaged copy**

```bash
/d/Work/cad-spec-gen/.venv/Scripts/python.exe -c "
import shutil, filecmp
src = 'render_config.py'
dst = 'src/cad_spec_gen/data/python_tools/render_config.py'
shutil.copy2(src, dst)
assert filecmp.cmp(src, dst, shallow=False)
print('synced')
"
```

- [ ] **Step 6: 验证 MATERIAL_PRESETS 数量仍是 18**

```bash
/d/Work/cad-spec-gen/.venv/Scripts/python.exe -c "
import sys; sys.path.insert(0, '.')
import render_config as rc
d = rc.MATERIAL_PRESETS
assert len(d) == 18, f'count drift: {len(d)}'
# 3 新 preset 存在
for name in ('abs_matte_gray', 'ceramic_white', 'carbon_fiber_weave'):
    assert name in d, f'{name} missing'
# 3 新 preset 有 color
for name in ('abs_matte_gray', 'ceramic_white', 'carbon_fiber_weave'):
    assert 'color' in d[name], f'{name} missing color'
print('OK')
"
```

Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add render_config.py src/cad_spec_gen/data/python_tools/render_config.py tests/test_render_config_no_sw_strings.py
git commit -m "refactor(render_config): 移除 preset 的 SW 纹理字段，分发物回到纯 PBR（Track A1 重构）"
```

---

### Task R2: 新建 sw_texture_backfill.py 回填模块

**Files:**
- Create: `adapters/solidworks/sw_texture_backfill.py`
- Create: `tests/test_sw_texture_backfill.py`

- [ ] **Step 1: RED 测试先行**

新建 `tests/test_sw_texture_backfill.py`：

```python
"""Track A1 SW 纹理运行时回填层 —— 单元测试 + 分类覆盖 gate。

spec §11.3 发版 gate（重构版）：PRESET_TO_SW_TEXTURE_MAP ≥10 preset 映射，
分类覆盖 金属≥3 / 塑料≥3 / 橡胶·陶瓷≥2 / PEEK·复合≥2。
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from adapters.solidworks.sw_texture_backfill import (
    PRESET_TO_SW_TEXTURE_MAP,
    backfill_presets_for_sw,
)


# —————— 映射表覆盖率 gate（移植自 test_a14_preset_texture_coverage 的分类测试）——————

PRESET_CATEGORY = {
    "brushed_aluminum": "metal",
    "anodized_blue": "metal",
    "anodized_green": "metal",
    "anodized_purple": "metal",
    "anodized_red": "metal",
    "black_anodized": "metal",
    "bronze": "metal",
    "copper": "metal",
    "gunmetal": "metal",
    "dark_steel": "metal",
    "stainless_304": "metal",
    "white_nylon": "plastic",
    "polycarbonate_clear": "plastic",
    "abs_matte_gray": "plastic",
    "black_rubber": "rubber_ceramic",
    "ceramic_white": "rubber_ceramic",
    "peek_amber": "peek_composite",
    "carbon_fiber_weave": "peek_composite",
}
CATEGORY_MIN = {"metal": 3, "plastic": 3, "rubber_ceramic": 2, "peek_composite": 2}


def test_map_has_at_least_10_entries():
    assert len(PRESET_TO_SW_TEXTURE_MAP) >= 10


def test_map_category_coverage():
    from collections import Counter
    counts: Counter[str] = Counter()
    for name in PRESET_TO_SW_TEXTURE_MAP:
        counts[PRESET_CATEGORY.get(name, "UNKNOWN")] += 1
    failures = [
        f"{cat}={counts.get(cat, 0)}/{m}"
        for cat, m in CATEGORY_MIN.items() if counts.get(cat, 0) < m
    ]
    assert not failures, f"分类覆盖未达 gate：{failures}"


def test_map_entries_contain_base_color_texture():
    for name, entry in PRESET_TO_SW_TEXTURE_MAP.items():
        assert "base_color_texture" in entry, f"{name} 缺 base_color_texture"
        assert isinstance(entry["base_color_texture"], str), f"{name} 非 str"
        assert "\\" not in entry["base_color_texture"], f"{name} 含反斜杠"


# —————— backfill_presets_for_sw 函数行为测试 ——————

def test_backfill_no_sw_returns_input_unchanged():
    presets = {"foo": {"color": (1, 1, 1, 1)}}
    result = backfill_presets_for_sw(presets, sw_info=None)
    assert result == presets
    # 不可改动原输入
    assert result is not presets or presets["foo"] == {"color": (1, 1, 1, 1)}


def test_backfill_sw_not_installed_returns_input_unchanged():
    sw_info = SimpleNamespace(installed=False, textures_dir="")
    presets = {"brushed_aluminum": {"color": (0.8, 0.8, 0.8, 1.0)}}
    result = backfill_presets_for_sw(presets, sw_info=sw_info)
    assert result == presets


def test_backfill_sw_installed_injects_texture_fields():
    sw_info = SimpleNamespace(installed=True, textures_dir="C:/fake/textures")
    presets = {
        "brushed_aluminum": {
            "color": (0.82, 0.82, 0.84, 1.0),
            "metallic": 1.0,
            "roughness": 0.18,
        }
    }
    result = backfill_presets_for_sw(presets, sw_info=sw_info)
    # 原输入不变
    assert "base_color_texture" not in presets["brushed_aluminum"]
    # 结果是 deep copy + 含纹理字段
    r = result["brushed_aluminum"]
    assert r["color"] == (0.82, 0.82, 0.84, 1.0)  # 原字段保留
    assert r["base_color_texture"] == "metal/brushed/brush.jpg"
    assert r["normal_texture"] == "metal/wire_bump.jpg"
    assert r["roughness_texture"] is None
    assert r["metallic_texture"] is None


def test_backfill_unknown_preset_not_in_map_passthrough():
    """映射表没登记的 preset 保持原样（也是 SW 装了但这 preset 没 SW 映射的场景）。"""
    sw_info = SimpleNamespace(installed=True, textures_dir="C:/fake")
    presets = {"custom_preset": {"color": (0.5, 0.5, 0.5, 1.0)}}
    result = backfill_presets_for_sw(presets, sw_info=sw_info)
    assert "base_color_texture" not in result["custom_preset"]


def test_backfill_empty_textures_dir_skips_even_when_installed():
    """sw.installed=True 但 textures_dir 空 → 不回填（目录缺失时硬挂路径=死路径）。"""
    sw_info = SimpleNamespace(installed=True, textures_dir="")
    presets = {"brushed_aluminum": {"color": (0.8, 0.8, 0.8, 1.0)}}
    result = backfill_presets_for_sw(presets, sw_info=sw_info)
    assert "base_color_texture" not in result["brushed_aluminum"]
```

- [ ] **Step 2: 跑测试确认 RED（模块不存在 ImportError）**

Run: `/d/Work/cad-spec-gen/.venv/Scripts/python.exe -m pytest tests/test_sw_texture_backfill.py -v`

Expected: ImportError → collection error（因为 `sw_texture_backfill.py` 还不存在）。

- [ ] **Step 3: 实现 sw_texture_backfill.py**

新建 `adapters/solidworks/sw_texture_backfill.py`：

```python
"""Track A1 SW 纹理运行时回填层。

**职责**：探测 SolidWorks 装机后，把 `PRESET_TO_SW_TEXTURE_MAP` 里的纹理路径
注入到 MATERIAL_PRESETS 的 copy，供 `render_3d.create_pbr_material` 挂 PBR 贴图。

**分发物约束**（CLAUDE.md 用户北极星"SW 装即用 / SW 未装零感知"）：
- `render_config.py` MATERIAL_PRESETS 保持纯 PBR（无 SW 路径字符串）
- SW 纹理映射表存在本模块里（实现细节，不污染 preset 定义层）
- SW 未装 → `backfill_presets_for_sw` 返回原输入，字段不出现

**映射表来源**：18 个 preset 对应的 SW 纹理库相对路径（基于 SOLIDWORKS 2024
`data/Images/textures/` 结构实地探查，见 Track A spec §3.1 + §11.3 发版 gate 分类）。
文件名含空格合法（`rubber/texture/tire tread.jpg`），pathlib 透传。
"""
from __future__ import annotations

import copy
import os
from typing import Any, Mapping, Optional


# preset 名 → SW 纹理路径（相对 SwInfo.textures_dir）
# 值是 4 字段 dict：base_color_texture (必填 str) / normal_texture (str | None)
# / roughness_texture (str | None) / metallic_texture (str | None)
PRESET_TO_SW_TEXTURE_MAP: dict[str, dict[str, Optional[str]]] = {
    # ── 金属 (11) ──
    "brushed_aluminum": {
        "base_color_texture": "metal/brushed/brush.jpg",
        "normal_texture": "metal/wire_bump.jpg",
        "roughness_texture": None,
        "metallic_texture": None,
    },
    "anodized_blue": {
        "base_color_texture": "painted/powdercoat_light.jpg",
        "normal_texture": None,
        "roughness_texture": None,
        "metallic_texture": None,
    },
    "anodized_green": {
        "base_color_texture": "painted/powdercoat_light.jpg",
        "normal_texture": None,
        "roughness_texture": None,
        "metallic_texture": None,
    },
    "anodized_purple": {
        "base_color_texture": "painted/powdercoat_light.jpg",
        "normal_texture": None,
        "roughness_texture": None,
        "metallic_texture": None,
    },
    "anodized_red": {
        "base_color_texture": "painted/powdercoat_light.jpg",
        "normal_texture": None,
        "roughness_texture": None,
        "metallic_texture": None,
    },
    "black_anodized": {
        "base_color_texture": "painted/powdercoat_dark.jpg",
        "normal_texture": None,
        "roughness_texture": None,
        "metallic_texture": None,
    },
    "bronze": {
        "base_color_texture": "metal/cast/cast_iron.jpg",
        "normal_texture": "metal/cast/cast_bump.jpg",
        "roughness_texture": None,
        "metallic_texture": None,
    },
    "copper": {
        "base_color_texture": "metal/polished/chrome1.jpg",
        "normal_texture": None,
        "roughness_texture": None,
        "metallic_texture": None,
    },
    "gunmetal": {
        "base_color_texture": "metal/rough/rmetal3.jpg",
        "normal_texture": None,
        "roughness_texture": None,
        "metallic_texture": None,
    },
    "dark_steel": {
        "base_color_texture": "metal/steelplaincarbon_diffusemap.jpg",
        "normal_texture": None,
        "roughness_texture": None,
        "metallic_texture": None,
    },
    "stainless_304": {
        "base_color_texture": "metal/polished/polishedsteel_diffusemap.jpg",
        "normal_texture": None,
        "roughness_texture": None,
        "metallic_texture": None,
    },
    # ── 塑料 (3) ──
    "white_nylon": {
        "base_color_texture": "plastic/smooth/sgray.jpg",
        "normal_texture": None,
        "roughness_texture": None,
        "metallic_texture": None,
    },
    "polycarbonate_clear": {
        "base_color_texture": "plastic/polished/pplastic.jpg",
        "normal_texture": None,
        "roughness_texture": None,
        "metallic_texture": None,
    },
    "abs_matte_gray": {
        "base_color_texture": "plastic/smooth/sgray.jpg",
        "normal_texture": None,
        "roughness_texture": None,
        "metallic_texture": None,
    },
    # ── 橡胶/陶瓷 (2) ──
    "black_rubber": {
        "base_color_texture": "rubber/texture/tire tread.jpg",
        "normal_texture": "rubber/texture/tire tread bump.jpg",
        "roughness_texture": None,
        "metallic_texture": None,
    },
    "ceramic_white": {
        "base_color_texture": "plastic/polished/pplastic.jpg",
        "normal_texture": None,
        "roughness_texture": None,
        "metallic_texture": None,
    },
    # ── PEEK/复合 (2) ──
    "peek_amber": {
        "base_color_texture": "plastic/bumpy/plasticmt11030_bump.jpg",
        "normal_texture": None,
        "roughness_texture": None,
        "metallic_texture": None,
    },
    "carbon_fiber_weave": {
        "base_color_texture": "fibers/glassfibre_bump.jpg",
        "normal_texture": "fibers/glassfibre_bump.jpg",
        "roughness_texture": None,
        "metallic_texture": None,
    },
}


def backfill_presets_for_sw(
    presets: Mapping[str, Mapping[str, Any]],
    sw_info: Any | None,
) -> dict[str, dict[str, Any]]:
    """把 PRESET_TO_SW_TEXTURE_MAP 的纹理路径注入 preset 副本。

    行为表：
    | sw_info          | textures_dir       | 行为                     |
    |------------------|--------------------|--------------------------|
    | None             | —                  | 返 deep copy（no-op）    |
    | installed=False  | —                  | 返 deep copy（no-op）    |
    | installed=True   | "" (空串)          | 返 deep copy（no-op）    |
    | installed=True   | 不存在磁盘路径     | 返 deep copy（no-op；防死路径） |
    | installed=True   | 有效目录           | 返 copy + 合并映射表字段 |

    Parameters
    ----------
    presets : Mapping[str, Mapping[str, Any]]
        原 MATERIAL_PRESETS（或任意形状一致的映射）。不会被改动。
    sw_info : Any | None
        `SwInfo` 或等效 dataclass（需有 installed / textures_dir 属性）。
        None 视为 SW 未装。

    Returns
    -------
    dict
        deep copy 后的 preset dict。SW 回填成功时各命中 preset 增加 4 字段。
    """
    result: dict[str, dict[str, Any]] = {k: dict(v) for k, v in presets.items()}

    if sw_info is None:
        return result
    if not getattr(sw_info, "installed", False):
        return result
    tex_dir = getattr(sw_info, "textures_dir", "") or ""
    if not tex_dir:
        return result
    if not os.path.isdir(tex_dir):
        return result

    for name, texture_fields in PRESET_TO_SW_TEXTURE_MAP.items():
        if name not in result:
            # 映射表预留但 preset 未定义（v2.13+ 自定义场景）——跳过
            continue
        result[name].update(texture_fields)
    return result
```

- [ ] **Step 4: 跑 RED 测试 → 现在应 8 GREEN**

Run: `/d/Work/cad-spec-gen/.venv/Scripts/python.exe -m pytest tests/test_sw_texture_backfill.py -v`

Expected: 8 tests 全 PASS。

- [ ] **Step 5: Commit**

```bash
git add adapters/solidworks/sw_texture_backfill.py tests/test_sw_texture_backfill.py
git commit -m "feat(solidworks): 新增 sw_texture_backfill 运行时回填层（Track A1 重构）"
```

---

### Task R3: `_build_blender_env()` 扩展 — 落 JSON + env 注入

**Files:**
- Modify: `cad_pipeline.py`（`_build_blender_env` 函数，line 203-231）

**Rationale:** 现 `_build_blender_env` 已注入 `SW_TEXTURES_DIR`（A1-3 commit）。扩展为：探到 SW + `textures_dir` 有效 → 调 `backfill_presets_for_sw(MATERIAL_PRESETS, sw)` → 落盘 `artifacts/{run_id}/runtime_materials.json` → env `CAD_RUNTIME_MATERIAL_PRESETS_JSON=<path>`。

- [ ] **Step 1: RED 测试**

新建 `tests/test_build_blender_env_backfill.py`：

```python
"""Track A1 R3：_build_blender_env 扩展 — SW 装了要落盘 runtime_materials.json。"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def test_build_env_sw_installed_writes_runtime_materials_json(tmp_path, monkeypatch):
    """SW 装了 + textures_dir 真存在 → 落盘 runtime_materials.json + env 指路径。"""
    # 构造 fake SW textures 目录
    fake_sw_tex = tmp_path / "sw_textures"
    fake_sw_tex.mkdir()
    fake_sw = SimpleNamespace(installed=True, textures_dir=str(fake_sw_tex))

    # monkeypatch run_id artifact dir 到 tmp_path
    run_artifacts = tmp_path / "artifacts" / "run_123"
    run_artifacts.mkdir(parents=True)
    monkeypatch.setenv("CAD_RUN_ARTIFACTS_DIR", str(run_artifacts))

    import cad_pipeline
    with patch.object(cad_pipeline, "detect_solidworks", return_value=fake_sw):
        env = cad_pipeline._build_blender_env()

    # env 注入检查
    assert env.get("SW_TEXTURES_DIR") == str(fake_sw_tex)
    json_path = env.get("CAD_RUNTIME_MATERIAL_PRESETS_JSON")
    assert json_path, "CAD_RUNTIME_MATERIAL_PRESETS_JSON env 未注入"

    # 落盘的 JSON 可读 + 含纹理字段
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    assert "brushed_aluminum" in data
    assert data["brushed_aluminum"]["base_color_texture"] == "metal/brushed/brush.jpg"


def test_build_env_sw_not_installed_no_runtime_json(tmp_path, monkeypatch):
    """SW 未装 → 不落盘 runtime_materials.json + env 不含 CAD_RUNTIME 变量。"""
    fake_sw = SimpleNamespace(installed=False, textures_dir="")
    monkeypatch.setenv("CAD_RUN_ARTIFACTS_DIR", str(tmp_path))

    import cad_pipeline
    with patch.object(cad_pipeline, "detect_solidworks", return_value=fake_sw):
        env = cad_pipeline._build_blender_env()

    assert "SW_TEXTURES_DIR" not in env
    assert "CAD_RUNTIME_MATERIAL_PRESETS_JSON" not in env


def test_build_env_sw_installed_but_textures_dir_missing(tmp_path, monkeypatch):
    """SW 装了但 textures_dir 不是有效目录 → 不注入（防死路径）。"""
    fake_sw = SimpleNamespace(installed=True, textures_dir="/nonexistent/xyz123")
    monkeypatch.setenv("CAD_RUN_ARTIFACTS_DIR", str(tmp_path))

    import cad_pipeline
    with patch.object(cad_pipeline, "detect_solidworks", return_value=fake_sw):
        env = cad_pipeline._build_blender_env()

    assert "SW_TEXTURES_DIR" not in env
    assert "CAD_RUNTIME_MATERIAL_PRESETS_JSON" not in env
```

- [ ] **Step 2: 跑测试确认 RED**

Run: `/d/Work/cad-spec-gen/.venv/Scripts/python.exe -m pytest tests/test_build_blender_env_backfill.py -v`

Expected: 1 test fail（`test_build_env_sw_installed_writes_runtime_materials_json` — 新功能未实现）+ 2 tests 可能 pass（当前不注入=已满足否定条件）。

- [ ] **Step 3: 修改 `_build_blender_env`**

编辑 `cad_pipeline.py` line 203-231 区块，扩展为：

```python
def _build_blender_env():
    """A1-3 + A1 重构 Track A §3.3：构造 Blender subprocess 的环境变量。

    基于父进程 env 的拷贝。若 SW 装了 + textures_dir 有效：
      1. 注入 SW_TEXTURES_DIR（原 A1-3 行为，render_3d.py 的
         _resolve_texture_path 依赖它做相对路径 → 绝对路径解析）
      2. 调 adapters.solidworks.sw_texture_backfill.backfill_presets_for_sw()
         给 MATERIAL_PRESETS 副本合并 SW 纹理字段 → 落盘
         artifacts/{run}/runtime_materials.json → env CAD_RUNTIME_MATERIAL_PRESETS_JSON
         指该路径，让 Blender 子进程 render_3d.py 启动时加载覆盖内置 preset

    SW 未装 / textures_dir 空 / 目录不存在 → 两条都不注入。
    Blender 子进程 env 缺 → MATERIAL_PRESETS 保持纯 PBR（preset 定义层干净）。
    """
    import json as _json  # module-local，避免全局 import 顺序影响
    env = os.environ.copy()
    try:
        sw = detect_solidworks()
    except Exception as exc:
        log.debug("SW detection skipped (%s): %s", type(exc).__name__, exc)
        return env

    if not (
        getattr(sw, "installed", False)
        and getattr(sw, "textures_dir", "")
        and os.path.isdir(sw.textures_dir)
    ):
        return env

    # —— (1) SW_TEXTURES_DIR（A1-3 原有）——
    env["SW_TEXTURES_DIR"] = sw.textures_dir
    log.info("SW_TEXTURES_DIR -> %s (injected into Blender env)", sw.textures_dir)

    # —— (2) runtime_materials.json（A1 重构）——
    try:
        import sys
        if os.path.abspath(".") not in sys.path:
            sys.path.insert(0, os.path.abspath("."))
        import render_config as _rcfg
        from adapters.solidworks.sw_texture_backfill import backfill_presets_for_sw

        backfilled = backfill_presets_for_sw(_rcfg.MATERIAL_PRESETS, sw)

        # 落盘到 artifacts/{run_id}/runtime_materials.json
        # CAD_RUN_ARTIFACTS_DIR 由 pipeline orchestrator 提前 set；缺则写到 tmp
        artifact_dir = os.environ.get("CAD_RUN_ARTIFACTS_DIR")
        if artifact_dir and os.path.isdir(artifact_dir):
            json_path = os.path.join(artifact_dir, "runtime_materials.json")
        else:
            import tempfile
            json_path = os.path.join(tempfile.gettempdir(), "runtime_materials.json")

        with open(json_path, "w", encoding="utf-8") as f:
            _json.dump(
                {k: dict(v) for k, v in backfilled.items()},
                f, ensure_ascii=False, indent=2,
            )
        env["CAD_RUNTIME_MATERIAL_PRESETS_JSON"] = json_path
        log.info("CAD_RUNTIME_MATERIAL_PRESETS_JSON -> %s", json_path)
    except Exception as exc:
        log.warning("runtime_materials.json 回填失败（preset 将走 v2.11 纯色）：%s", exc)

    return env
```

- [ ] **Step 4: 跑测试 → 全 PASS**

Run: `/d/Work/cad-spec-gen/.venv/Scripts/python.exe -m pytest tests/test_build_blender_env_backfill.py -v`

Expected: 3 tests 全 PASS。

- [ ] **Step 5: Commit**

```bash
git add cad_pipeline.py tests/test_build_blender_env_backfill.py
git commit -m "feat(cad_pipeline): _build_blender_env 扩展落盘 runtime_materials.json（Track A1 重构）"
```

---

### Task R4: `render_3d.py` 读 env JSON 覆盖内置 preset

**Files:**
- Modify: `src/cad_spec_gen/render_3d.py`（MATERIAL_PRESETS import 后加一步 runtime 覆盖）
- Modify: `render_config.py`（新增 `load_runtime_materials_override(env_var_name)` helper，放在 MATERIAL_PRESETS 下方）

- [ ] **Step 1: RED — 加测 helper**

新建 `tests/test_render_config_runtime_override.py`：

```python
"""A1 重构 R4：render_config 能从 env JSON 载入 runtime preset 覆盖。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import render_config as rcfg


def test_load_runtime_override_env_missing_returns_none(monkeypatch):
    monkeypatch.delenv("CAD_RUNTIME_MATERIAL_PRESETS_JSON", raising=False)
    assert rcfg.load_runtime_materials_override() is None


def test_load_runtime_override_env_points_to_missing_file(monkeypatch, tmp_path):
    monkeypatch.setenv("CAD_RUNTIME_MATERIAL_PRESETS_JSON", str(tmp_path / "nope.json"))
    assert rcfg.load_runtime_materials_override() is None


def test_load_runtime_override_env_valid_returns_dict(monkeypatch, tmp_path):
    payload = {
        "brushed_aluminum": {
            "color": [0.82, 0.82, 0.84, 1.0],
            "metallic": 1.0,
            "roughness": 0.18,
            "base_color_texture": "metal/brushed/brush.jpg",
        }
    }
    json_path = tmp_path / "runtime_materials.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("CAD_RUNTIME_MATERIAL_PRESETS_JSON", str(json_path))
    result = rcfg.load_runtime_materials_override()
    assert result is not None
    assert "brushed_aluminum" in result
    assert result["brushed_aluminum"]["base_color_texture"] == "metal/brushed/brush.jpg"


def test_load_runtime_override_invalid_json_returns_none(monkeypatch, tmp_path):
    json_path = tmp_path / "bad.json"
    json_path.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setenv("CAD_RUNTIME_MATERIAL_PRESETS_JSON", str(json_path))
    assert rcfg.load_runtime_materials_override() is None
```

- [ ] **Step 2: 跑 RED**

Run: `/d/Work/cad-spec-gen/.venv/Scripts/python.exe -m pytest tests/test_render_config_runtime_override.py -v`

Expected: AttributeError（`load_runtime_materials_override` 不存在）。

- [ ] **Step 3: 在 render_config.py 加 helper**

在 `MATERIAL_PRESETS = {...}` 闭合 dict 之后、`def load_config` 之前插入：

```python
# ═════════════════════════════════════════════════════════════════════════════
# Runtime override loader（Track A1 重构：从 env 指向的 JSON 加载 SW 回填结果）
# ═════════════════════════════════════════════════════════════════════════════

def load_runtime_materials_override():
    """从 CAD_RUNTIME_MATERIAL_PRESETS_JSON env 指的路径加载 runtime preset 覆盖。

    由 cad_pipeline._build_blender_env 在 SW 装了的场景下落盘；Blender 子进程
    里 render_3d.py 启动时读本 helper 合并到 MATERIAL_PRESETS 副本。

    Returns
    -------
    dict | None
        成功 → dict（preset_name → params）；env 缺失 / 文件缺失 / JSON 无效 → None。
    """
    path = os.environ.get("CAD_RUNTIME_MATERIAL_PRESETS_JSON")
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    return data
```

- [ ] **Step 4: 跑测试 → 4/4 PASS**

- [ ] **Step 5: 在 render_3d.py 启动时调用**

编辑 `render_3d.py`：找到 `MATERIAL_PRESETS = rcfg.MATERIAL_PRESETS` 或 `_CONFIG_MATERIALS = ...` 定义区（约 line 142-160 附近），加入：

```python
# —— A1 重构：SW 装了时 _build_blender_env 落了 runtime_materials.json；
# 此处加载覆盖内置 MATERIAL_PRESETS（仅当前进程副本，源码不被污染）——
_runtime_override = rcfg.load_runtime_materials_override()
if _runtime_override:
    # 按 preset 名合并；老 preset 不在 override 里的保留原 PBR
    _MATERIAL_PRESETS_RUNTIME = dict(rcfg.MATERIAL_PRESETS)
    for name, params in _runtime_override.items():
        if name in _MATERIAL_PRESETS_RUNTIME:
            merged = dict(_MATERIAL_PRESETS_RUNTIME[name])
            merged.update(params)
            _MATERIAL_PRESETS_RUNTIME[name] = merged
        else:
            _MATERIAL_PRESETS_RUNTIME[name] = dict(params)
    log.info("runtime preset override loaded: %d entries", len(_runtime_override))
else:
    _MATERIAL_PRESETS_RUNTIME = rcfg.MATERIAL_PRESETS

# assign_materials 里对 MATERIAL_PRESETS 的引用改成 _MATERIAL_PRESETS_RUNTIME
```

**定位具体行**：read `src/cad_spec_gen/render_3d.py` 看现有 MATERIAL_PRESETS 引用点，替换成 `_MATERIAL_PRESETS_RUNTIME`。

- [ ] **Step 6: 跑 AST 结构测试确认**

Run: `/d/Work/cad-spec-gen/.venv/Scripts/python.exe -m pytest tests/test_render_3d_texture_bridge.py -v`

Expected: 现有 10 个 structural test 仍 PASS。

- [ ] **Step 7: Commit**

```bash
git add render_config.py src/cad_spec_gen/data/python_tools/render_config.py src/cad_spec_gen/render_3d.py tests/test_render_config_runtime_override.py
git commit -m "feat(render_config): load_runtime_materials_override + render_3d 启动合并（Track A1 重构）"
```

---

### Task R5: 重写 test_a14_preset_texture_coverage.py — 分发物干净性 + map 覆盖

**Files:**
- Modify: `tests/test_a14_preset_texture_coverage.py`

**Rationale:** Task 1 的 gate 测试语义变了。现在 gate 测：
- MATERIAL_PRESETS 里 **零 SW 字段**（test_render_config_no_sw_strings 已覆盖）
- `PRESET_TO_SW_TEXTURE_MAP` **覆盖率 ≥10 + 分类 3+3+2+2**（test_sw_texture_backfill 已覆盖）

所以 `tests/test_a14_preset_texture_coverage.py` 现在是**语义冗余** — 要么删除，要么重写为对**分发物干净 + 回填表覆盖**的 smoke 级集成断言（高层验收视角）。

推荐 **重写为 1 个顶层集成测试**，供发版 checklist 用。

- [ ] **Step 1: 替换文件内容**

用以下内容覆盖 `tests/test_a14_preset_texture_coverage.py`：

```python
"""Track A1-4 发版 hard gate（重构版集成测试）。

**约束对齐（v2.12 发版 checklist 第 2 条）**：

1. **分发物干净**：MATERIAL_PRESETS 无 SW 纹理字段（细节测试在
   test_render_config_no_sw_strings.py）
2. **回填表完整**：PRESET_TO_SW_TEXTURE_MAP ≥10 preset + 分类 3+3+2+2（细节
   测试在 test_sw_texture_backfill.py）
3. **端到端可用**：SW 装了时 backfill_presets_for_sw 返回的 dict 至少 10 条
   含 base_color_texture

本文件只保留高层集成断言；细粒度单元测试在上述两个姐妹文件。
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import render_config as rcfg
from adapters.solidworks.sw_texture_backfill import (
    PRESET_TO_SW_TEXTURE_MAP,
    backfill_presets_for_sw,
)


def test_release_gate_sw_installed_end_to_end_coverage(tmp_path):
    """端到端：假设 SW 已装 + textures_dir 有效，backfill 后 ≥10 preset 带纹理。"""
    # mock SW 装机（用 tmp_path 造一个有效 textures_dir）
    fake_tex_dir = tmp_path / "textures"
    fake_tex_dir.mkdir()
    sw = SimpleNamespace(installed=True, textures_dir=str(fake_tex_dir))

    backfilled = backfill_presets_for_sw(rcfg.MATERIAL_PRESETS, sw)
    with_tex = [n for n, p in backfilled.items() if p.get("base_color_texture")]

    assert len(with_tex) >= 10, (
        f"发版 gate：SW 装后 backfilled preset 仅 {len(with_tex)} 带 texture，"
        f"要求 ≥10。命中：{sorted(with_tex)}"
    )


def test_release_gate_sw_absent_presets_unchanged():
    """无 SW → backfill 返回的 dict 各 preset 字段数与 MATERIAL_PRESETS 完全一致。"""
    sw = SimpleNamespace(installed=False, textures_dir="")
    backfilled = backfill_presets_for_sw(rcfg.MATERIAL_PRESETS, sw)
    for name, original in rcfg.MATERIAL_PRESETS.items():
        # 不新增字段
        assert set(backfilled[name]) == set(original), (
            f"{name} 字段集被动（SW 未装应无回填）："
            f"{set(backfilled[name]) - set(original)}"
        )


def test_release_gate_map_entries_subset_of_preset_names():
    """PRESET_TO_SW_TEXTURE_MAP 不应预留 MATERIAL_PRESETS 没定义的 preset 名。"""
    unknown = set(PRESET_TO_SW_TEXTURE_MAP) - set(rcfg.MATERIAL_PRESETS)
    assert not unknown, f"映射表含未定义的 preset：{sorted(unknown)}"
```

- [ ] **Step 2: 跑整套 gate**

Run:
```bash
/d/Work/cad-spec-gen/.venv/Scripts/python.exe -m pytest \
  tests/test_a14_preset_texture_coverage.py \
  tests/test_sw_texture_backfill.py \
  tests/test_render_config_no_sw_strings.py \
  tests/test_render_config_runtime_override.py \
  tests/test_build_blender_env_backfill.py \
  -v
```

Expected: 全 PASS（3 + 8 + 3 + 4 + 3 = 21 tests 绿）。

- [ ] **Step 3: Commit**

```bash
git add tests/test_a14_preset_texture_coverage.py
git commit -m "refactor(test): A1-4 gate 改测分发物干净 + 回填表覆盖（Track A1 重构）"
```

---

### Task R6: A1-2 Blender smoke — 反映"env 注入 vs 无 env"两条路径

**Files:**
- Modify: `tests/test_render_3d_texture_bridge.py`（替换现有 placeholder 注释）

**Rationale:** 原 Task 8 设计的 smoke 假设 preset 自带 texture 字段 → 现在 preset 干净，需要测"env 注入 runtime_materials.json 后 Blender 子进程读到 + 挂贴图"这条新路径。

- [ ] **Step 1: 替换 placeholder 注释区块（line 135-139）**

编辑 `tests/test_render_3d_texture_bridge.py`，末尾替换为：

```python
# ───────────── Blender headless smoke（A1 重构：env + runtime_materials.json）──

import json as _json
import subprocess
import sys


def _blender_available() -> bool:
    try:
        _REPO = Path(__file__).parent.parent
        if str(_REPO) not in sys.path:
            sys.path.insert(0, str(_REPO))
        from cad_paths import get_blender_path
        return get_blender_path() is not None
    except Exception:
        return False


@pytest.mark.blender
@pytest.mark.skipif(
    not _blender_available(),
    reason="Blender not found via cad_paths.get_blender_path()",
)
class TestCreatePbrMaterialBlenderSmoke:
    """真启 Blender 子进程验证 create_pbr_material 节点图（env 注入 vs 无注入）。"""

    def _make_1x1_png(self, path: Path, rgb: tuple[int, int, int] = (200, 50, 50)) -> None:
        """stdlib 手搓 1×1 PNG（不引 PIL 依赖）。"""
        import struct, zlib

        def _chunk(tag: bytes, data: bytes) -> bytes:
            return (
                struct.pack(">I", len(data))
                + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
            )

        sig = b"\x89PNG\r\n\x1a\n"
        ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        raw = b"\x00" + bytes(rgb)
        idat = _chunk(b"IDAT", zlib.compress(raw))
        iend = _chunk(b"IEND", b"")
        path.write_bytes(sig + ihdr + idat + iend)

    def test_env_injected_runtime_json_produces_tex_nodes(self, tmp_path):
        """env 指向 runtime_materials.json 时 → 节点图含 TexImage + Mapping + TexCoord。"""
        from cad_paths import get_blender_path
        blender = get_blender_path()

        tex_dir = tmp_path / "textures"
        tex_dir.mkdir()
        png_path = tex_dir / "diffuse.png"
        self._make_1x1_png(png_path)

        # 构造 runtime_materials.json: 一个带 base_color_texture 的 preset
        runtime_json = tmp_path / "runtime_materials.json"
        payload = {
            "smoke_preset": {
                "color": (0.8, 0.2, 0.2, 1.0),
                "metallic": 0.0,
                "roughness": 0.5,
                "base_color_texture": "diffuse.png",
            }
        }
        runtime_json.write_text(_json.dumps(payload), encoding="utf-8")

        # 部署 render_3d + render_config
        (tmp_path / "render_3d.py").write_text(
            (_REPO_ROOT / "src" / "cad_spec_gen" / "render_3d.py").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (tmp_path / "render_config.py").write_text(
            (_REPO_ROOT / "render_config.py").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        expr = (
            "import sys, os; "
            f"sys.path.insert(0, {str(tmp_path)!r}); "
            f"os.environ['CAD_SPEC_GEN_TEXTURE_DIR'] = {str(tex_dir)!r}; "
            f"os.environ['CAD_RUNTIME_MATERIAL_PRESETS_JSON'] = {str(runtime_json)!r}; "
            "import render_config as rc; "
            "import render_3d; "
            "params = dict(rc.load_runtime_materials_override()['smoke_preset']); "
            "mat = render_3d.create_pbr_material('smoke', params); "
            "kinds = sorted({n.bl_idname for n in mat.node_tree.nodes}); "
            "print('NODE_KINDS=' + ','.join(kinds)); "
            "print('SMOKE_OK')"
        )

        result = subprocess.run(
            [blender, "--background", "--python-expr", expr],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120,
        )
        assert "SMOKE_OK" in result.stdout, (
            f"stdout: {result.stdout[-1500:]}\nstderr: {result.stderr[-1500:]}"
        )
        for line in result.stdout.splitlines():
            if line.startswith("NODE_KINDS="):
                kinds = set(line.split("=", 1)[1].split(","))
                break
        else:
            pytest.fail("未发现 NODE_KINDS 诊断行")

        for required in ("ShaderNodeTexImage", "ShaderNodeMapping", "ShaderNodeTexCoord"):
            assert required in kinds, f"{required} 缺失，kinds={sorted(kinds)}"

    def test_no_env_pure_scalar_graph(self, tmp_path):
        """无 CAD_RUNTIME_MATERIAL_PRESETS_JSON env → 纯标量 BSDF 节点图，无 TexImage。"""
        from cad_paths import get_blender_path
        blender = get_blender_path()

        (tmp_path / "render_3d.py").write_text(
            (_REPO_ROOT / "src" / "cad_spec_gen" / "render_3d.py").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (tmp_path / "render_config.py").write_text(
            (_REPO_ROOT / "render_config.py").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        expr = (
            "import sys; "
            f"sys.path.insert(0, {str(tmp_path)!r}); "
            "import render_3d; "
            "params = {'color': (0.5, 0.5, 0.5, 1.0), 'metallic': 0.0, 'roughness': 0.5}; "
            "mat = render_3d.create_pbr_material('scalar', params); "
            "kinds = sorted({n.bl_idname for n in mat.node_tree.nodes}); "
            "print('NODE_KINDS=' + ','.join(kinds)); "
            "print('SMOKE_OK')"
        )

        result = subprocess.run(
            [blender, "--background", "--python-expr", expr],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120,
        )
        assert "SMOKE_OK" in result.stdout
        for line in result.stdout.splitlines():
            if line.startswith("NODE_KINDS="):
                kinds = set(line.split("=", 1)[1].split(","))
                break
        else:
            pytest.fail("未发现 NODE_KINDS 诊断行")

        assert "ShaderNodeTexImage" not in kinds, f"无 env 应无 TexImage：{sorted(kinds)}"
        assert "ShaderNodeBsdfPrincipled" in kinds
```

- [ ] **Step 2: 跑 smoke（本机）**

Run: `/d/Work/cad-spec-gen/.venv/Scripts/python.exe -m pytest tests/test_render_3d_texture_bridge.py -v -m blender`

Expected: 2 tests PASS（本机 Blender 4.2）。

- [ ] **Step 3: 默认 pytest 不触 marker**

Run: `/d/Work/cad-spec-gen/.venv/Scripts/python.exe -m pytest tests/test_render_3d_texture_bridge.py -v`

Expected: 10 structural tests PASS；2 smoke deselected。

- [ ] **Step 4: Commit**

```bash
git add tests/test_render_3d_texture_bridge.py
git commit -m "test(render_3d): A1-2 smoke 反映 env 注入 vs 纯标量双路径（Track A1 重构）"
```

---

### Task R7: 最终回归 + lint + mypy + push

- [ ] **Step 1: 跑 A1 scope 完整测试**

```bash
/d/Work/cad-spec-gen/.venv/Scripts/python.exe -m pytest \
  tests/test_render_config_no_sw_strings.py \
  tests/test_sw_texture_backfill.py \
  tests/test_a14_preset_texture_coverage.py \
  tests/test_render_config_runtime_override.py \
  tests/test_build_blender_env_backfill.py \
  tests/test_render_3d_texture_bridge.py \
  tests/test_render_3d_structure.py \
  tests/test_render_3d_texture_path.py \
  -v
```

Expected: 全绿（blender smoke deselected 除非 -m blender）。

- [ ] **Step 2: ruff**

```bash
/d/Work/cad-spec-gen/.venv/Scripts/python.exe -m ruff check \
  render_config.py \
  src/cad_spec_gen/data/python_tools/render_config.py \
  src/cad_spec_gen/render_3d.py \
  adapters/solidworks/sw_texture_backfill.py \
  cad_pipeline.py \
  tests/test_*.py
```

Expected: 无新增违规（pre-existing bpy unused-import 可忽略）。

- [ ] **Step 3: mypy**

```bash
/d/Work/cad-spec-gen/.venv/Scripts/python.exe -m mypy \
  adapters/solidworks/sw_texture_backfill.py \
  render_config.py
```

Expected: 0 errors。

- [ ] **Step 4: 本机 blender smoke**

```bash
/d/Work/cad-spec-gen/.venv/Scripts/python.exe -m pytest tests/test_render_3d_texture_bridge.py -v -m blender
```

Expected: 2 tests PASS。

- [ ] **Step 5: Push feature 分支**

```bash
git push -u origin feat/a1-wrapup-preset-textures
```

- [ ] **Step 6: 更新 MEMORY.md handoff**

在 `C:\Users\procheng\.claude\projects\D--Work-cad-spec-gen\memory\MEMORY.md` 加 handoff 指向新 memory 文件 `project_session12_handoff.md`（内容：A1 重构闭环 / preset 层干净 / 运行时回填模块独立 / 发版 gate 语义从"静态 preset 字段"转为"回填表覆盖 + 分发物干净"）。

---

## Out-of-Scope

- `blender_texture_count.json`（spec §3.3 + §8.2 #1）— 另起 task A1-6
- sldmat `parse_sldmat` 自动填纹理（spec §9 A1-5）— 另起
- `material_overrides` JSON 用户覆盖 — 已由 resolve_material 合并逻辑天然覆盖

---

## Execution Handoff

Plan 保存在 `docs/superpowers/plans/2026-04-20-a1-refactor-sw-texture-backfill-layer.md`。延续 Subagent-Driven 执行。
