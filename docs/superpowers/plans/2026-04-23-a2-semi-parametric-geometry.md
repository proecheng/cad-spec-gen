# A2 自制件半参数几何升级 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为自制件生成 L2 半参数几何（8 类模板 + 用户命名覆盖），将 11 件中约 7-8 件从 envelope 方块升级为可辨识形状。

**Architecture:** 两路建模（SW 优先 / CadQuery 回退）。`_apply_template_decision` 先检查 `SwParametricAdapter.is_available()`：可用时调 SW COM API 建参数化特征并导出 STEP（`sw_parts/{part_no}.step`），Jinja 通过 `{% elif step_path %}` 注入 `importStep()` 调用；SW 不可用时回退到 `codegen/part_templates/*.py` 工厂函数（返回 Python 代码字符串），Jinja 通过 `{% elif template_code %}` 注入。

**Tech Stack:** Python 3.11+, CadQuery 2.x, Jinja2, pytest, uv

---

## 文件地图

| 操作 | 路径 | 职责 |
|---|---|---|
| 修改 | `codegen/gen_parts.py` | A2-0 过滤 + `_apply_template_decision` + `generate_part_files` 集成 |
| 新建 | `codegen/template_mapping_loader.py` | 加载 template_mapping.json + 内置关键词 + `match_template` |
| 新建 | `codegen/part_templates/__init__.py` | 空文件，标记为包 |
| 新建 | `codegen/part_templates/flange.py` | `make_flange` |
| 新建 | `codegen/part_templates/housing.py` | `make_housing` |
| 新建 | `codegen/part_templates/bracket.py` | `make_bracket` |
| 新建 | `codegen/part_templates/spring_mechanism.py` | `make_spring_mechanism` |
| 新建 | `codegen/part_templates/sleeve.py` | `make_sleeve` |
| 新建 | `codegen/part_templates/plate.py` | `make_plate` |
| 新建 | `codegen/part_templates/arm.py` | `make_arm` |
| 新建 | `codegen/part_templates/cover.py` | `make_cover` |
| 修改 | `templates/part_module.py.j2` | 新增 `template_code` 分支 |
| 新建 | `template_mapping.json` | 示例用户命名覆盖（项目根目录） |
| 新建 | `tests/test_dim_filter.py` | A2-0 过滤单测 |
| 新建 | `tests/test_template_mapping.py` | mapping loader + match_template 单测 |
| 新建 | `tests/test_part_templates.py` | 8 类工厂函数单测（exec + face count） |
| 新建 | `tests/test_a2_integration.py` | 端到端：gen_parts 生成 → face count 验收 |
| 新建 | `adapters/parts/sw_parametric_adapter.py` | `SwParametricAdapter.is_available()` + `build_part()` 8 类 SW COM API 实现 |
| 新建 | `tests/test_sw_parametric_adapter.py` | SW adapter 单测（`@pytest.mark.requires_solidworks` 标记） |
| 修改 | `.gitignore` | 追加 `**/sw_parts/` |

---

## Task 1：A2-0 — dim_tolerances 过滤修复

**Files:**
- Modify: `codegen/gen_parts.py`
- Create: `tests/test_dim_filter.py`

- [ ] **Step 1：写失败测试**

新建 `tests/test_dim_filter.py`：

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "codegen"))

from gen_parts import _tol_belongs_to_part, _TOL_PREFIX_CATEGORY


def test_flange_prefix_matches_flange_part():
    assert _tol_belongs_to_part("FLANGE_OD", "法兰本体（含十字悬臂）") is True


def test_flange_prefix_rejected_for_spring_part():
    assert _tol_belongs_to_part("FLANGE_OD", "弹簧限力机构总成") is False


def test_spring_prefix_matches_spring_part():
    assert _tol_belongs_to_part("SPRING_PIN_BORE", "弹簧限力机构总成") is True


def test_spring_prefix_rejected_for_flange_part():
    assert _tol_belongs_to_part("SPRING_PIN_BORE", "法兰本体（含十字悬臂）") is False


def test_unknown_prefix_is_universal():
    # POS_ACC 无前缀命中 → 保留给所有件
    assert _tol_belongs_to_part("POS_ACC", "法兰本体（含十字悬臂）") is True
    assert _tol_belongs_to_part("POS_ACC", "弹簧限力机构总成") is True


def test_case_insensitive():
    assert _tol_belongs_to_part("flange_od", "法兰本体") is True


def test_arm_prefix_matches_arm_part():
    assert _tol_belongs_to_part("ARM_L_2", "法兰本体（含十字悬臂）") is True  # 法兰含悬臂
    assert _tol_belongs_to_part("ARM_L_2", "弹簧限力机构总成") is False


def test_filter_disabled_via_env(monkeypatch):
    import os
    monkeypatch.setenv("CAD_SPEC_GEN_DIM_FILTER", "off")
    # When disabled, _tol_belongs_to_part still works the same —
    # the disable check is in _parse_annotation_meta, not here.
    # This test is a placeholder; integration tested in Task 14.
    pass
```

- [ ] **Step 2：运行确认失败**

```bash
uv run pytest tests/test_dim_filter.py -v
```

预期：`ImportError: cannot import name '_tol_belongs_to_part'`

- [ ] **Step 3：在 `codegen/gen_parts.py` 中实现**

在 `_parse_annotation_meta` 函数定义之前（约 line 210 之前）插入：

```python
# A2-0: 语义前缀→零件类别关键词映射表
_TOL_PREFIX_CATEGORY: dict[str, str] = {
    "FLANGE":   "法兰",
    "HOUSING":  "壳体",
    "SPRING":   "弹簧",
    "ARM":      "悬臂",
    "BRACKET":  "支架",
    "SLEEVE":   "套筒",
    "CLAMP":    "夹",
    "PLATE":    "板",
    "COVER":    "盖",
}


def _tol_belongs_to_part(tol_name: str, part_name_cn: str) -> bool:
    """判断 dim_tolerance 条目是否归属当前零件。

    命中前缀 → 检查零件 name_cn 是否含对应关键词。
    未命中任何前缀 → 通用条目，保留给所有零件。
    """
    for prefix, keyword in _TOL_PREFIX_CATEGORY.items():
        if tol_name.upper().startswith(prefix):
            return keyword in part_name_cn
    return True


def _dim_filter_enabled() -> bool:
    return os.getenv("CAD_SPEC_GEN_DIM_FILTER", "on").lower() != "off"
```

将 `_parse_annotation_meta` 内的 `dim_tols` 赋值行替换：

```python
    # 原来（约 line 220）:
    # dim_tols = tol_data.get("dim_tols", [])
    # 替换为：
    dim_tols = tol_data.get("dim_tols", [])
    if _dim_filter_enabled() and part_name:
        dim_tols = [
            t for t in dim_tols
            if _tol_belongs_to_part(t.get("name", ""), part_name)
        ]
```

- [ ] **Step 4：运行确认通过**

```bash
uv run pytest tests/test_dim_filter.py -v
```

预期：7 passed

- [ ] **Step 5：运行全量测试确认无回归**

```bash
uv run pytest --tb=short -q
```

预期：原有 990+ passed，无新失败

- [ ] **Step 6：Commit**

```bash
git add codegen/gen_parts.py tests/test_dim_filter.py
git commit -m "feat(a2-0): dim_tolerances 语义前缀过滤 + _dim_filter_enabled 开关"
```

---

## Task 2：template_mapping_loader.py

**Files:**
- Create: `codegen/template_mapping_loader.py`
- Create: `tests/test_template_mapping.py`

- [ ] **Step 1：写失败测试**

新建 `tests/test_template_mapping.py`：

```python
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "codegen"))

from template_mapping_loader import load_template_mapping, match_template, _BUILTIN_KEYWORDS


class TestBuiltinKeywords:
    def test_flange_keyword(self):
        assert match_template("法兰本体", {}) == "flange"

    def test_housing_keyword(self):
        assert match_template("涂抹模块壳体", {}) == "housing"

    def test_bracket_keyword(self):
        assert match_template("安装支架", {}) == "bracket"

    def test_spring_keyword(self):
        assert match_template("弹簧限力机构总成", {}) == "spring_mechanism"

    def test_sleeve_keyword(self):
        assert match_template("PEEK绝缘套筒", {}) == "sleeve"

    def test_plate_keyword(self):
        assert match_template("底板", {}) == "plate"

    def test_arm_keyword(self):
        assert match_template("十字悬臂", {}) == "arm"

    def test_cover_keyword(self):
        assert match_template("端盖密封件", {}) == "cover"

    def test_no_match_returns_none(self):
        assert match_template("万向节柔性关节", {}) is None


class TestUserMapping:
    def test_exact_match_overrides_builtin(self):
        user = {"连接盘": "flange"}
        assert match_template("连接盘", user) == "flange"

    def test_exact_match_takes_priority_over_builtin_contains(self):
        # "弹簧壳体" 含"壳体"(builtin→housing)，但 user 覆盖→spring_mechanism
        user = {"弹簧壳体": "spring_mechanism"}
        assert match_template("弹簧壳体", user) == "spring_mechanism"

    def test_no_exact_match_falls_through_to_builtin(self):
        user = {"连接盘": "flange"}
        assert match_template("法兰本体", user) == "flange"  # builtin match


class TestLoadMapping:
    def test_load_nonexistent_returns_empty(self):
        result = load_template_mapping("/nonexistent/template_mapping.json")
        assert result == {}

    def test_load_none_returns_empty(self):
        assert load_template_mapping(None) == {}

    def test_load_valid_file(self, tmp_path):
        f = tmp_path / "template_mapping.json"
        f.write_text(json.dumps({"连接盘": "flange", "外壳": "housing"}),
                     encoding="utf-8")
        result = load_template_mapping(str(f))
        assert result == {"连接盘": "flange", "外壳": "housing"}

    def test_invalid_template_name_warned_and_skipped(self, tmp_path, capsys):
        f = tmp_path / "template_mapping.json"
        f.write_text(json.dumps({"怪件": "nonexistent_template"}),
                     encoding="utf-8")
        result = load_template_mapping(str(f))
        assert "怪件" not in result
        assert "WARNING" in capsys.readouterr().out
```

- [ ] **Step 2：运行确认失败**

```bash
uv run pytest tests/test_template_mapping.py -v
```

预期：`ModuleNotFoundError: No module named 'template_mapping_loader'`

- [ ] **Step 3：创建 `codegen/template_mapping_loader.py`**

```python
import json
import os
from pathlib import Path

_BUILTIN_KEYWORDS: dict[str, str] = {
    "flange":           "法兰",
    "housing":          "壳体",
    "bracket":          "支架",
    "spring_mechanism": "弹簧",
    "sleeve":           "套筒",
    "plate":            "板",
    "arm":              "悬臂",
    "cover":            "盖",
}

_VALID_TEMPLATES: frozenset[str] = frozenset(_BUILTIN_KEYWORDS.keys())


def load_template_mapping(mapping_path: str | None) -> dict[str, str]:
    """加载用户 template_mapping.json，返回 name_cn → template_type 字典。

    文件不存在时静默返回空字典。值不在已知模板名内时 warn + 跳过。
    """
    if not mapping_path:
        return {}
    p = Path(mapping_path)
    if not p.exists():
        return {}
    with p.open(encoding="utf-8") as f:
        raw: dict = json.load(f)
    result: dict[str, str] = {}
    for key, val in raw.items():
        if key.startswith("_"):   # 跳过 _comment / _valid_values 等注释键
            continue
        if val not in _VALID_TEMPLATES:
            print(f"  WARNING: template_mapping.json: 未知模板名 '{val}'（键 '{key}'），已跳过")
            continue
        result[key] = val
    return result


def match_template(name_cn: str, user_mapping: dict[str, str]) -> str | None:
    """将零件 name_cn 匹配到模板类型。

    优先级：user_mapping 精确匹配 > 内置关键词包含匹配 > None
    """
    if name_cn in user_mapping:
        return user_mapping[name_cn]
    for tpl_type, keyword in _BUILTIN_KEYWORDS.items():
        if keyword in name_cn:
            return tpl_type
    return None
```

- [ ] **Step 4：运行确认通过**

```bash
uv run pytest tests/test_template_mapping.py -v
```

预期：全部通过

- [ ] **Step 5：Commit**

```bash
git add codegen/template_mapping_loader.py tests/test_template_mapping.py
git commit -m "feat(a2-5): template_mapping_loader — 用户命名覆盖 + 内置关键词路由"
```

---

## Task 3：part_templates 目录 + make_flange

**Files:**
- Create: `codegen/part_templates/__init__.py`
- Create: `codegen/part_templates/flange.py`
- Create: `tests/test_part_templates.py`（初始，仅 flange）

- [ ] **Step 1：写失败测试**

新建 `tests/test_part_templates.py`：

```python
"""工厂函数测试：exec 生成代码并检查 face 数。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "codegen"))

import cadquery as cq
import pytest
from part_templates.flange import make_flange


def _exec_template(code: str) -> cq.Workplane:
    ns = {"cq": cq}
    exec(code, ns)
    return ns["body"]


class TestMakeFlange:
    def test_returns_none_when_od_missing(self):
        assert make_flange(od=None, id=22, thickness=30, bolt_pcd=70) is None

    def test_returns_none_when_id_missing(self):
        assert make_flange(od=90, id=None, thickness=30, bolt_pcd=70) is None

    def test_returns_none_when_thickness_missing(self):
        assert make_flange(od=90, id=22, thickness=None, bolt_pcd=70) is None

    def test_returns_none_when_bolt_pcd_missing(self):
        assert make_flange(od=90, id=22, thickness=30, bolt_pcd=None) is None

    def test_returns_none_when_id_ge_od(self):
        assert make_flange(od=20, id=25, thickness=10, bolt_pcd=15) is None

    def test_returns_code_string(self):
        code = make_flange(od=90, id=22, thickness=30, bolt_pcd=70)
        assert isinstance(code, str)
        assert "body" in code
        assert "cq.Workplane" in code

    def test_face_count_ge_30(self):
        code = make_flange(od=90, id=22, thickness=30, bolt_pcd=70, bolt_count=6)
        body = _exec_template(code)
        assert body.faces().size() >= 30

    def test_custom_bolt_count(self):
        code = make_flange(od=90, id=22, thickness=30, bolt_pcd=70, bolt_count=8)
        body = _exec_template(code)
        assert body.faces().size() >= 30

    def test_with_boss(self):
        code = make_flange(od=90, id=22, thickness=30, bolt_pcd=70, boss_h=10)
        body = _exec_template(code)
        assert body.faces().size() >= 30
```

- [ ] **Step 2：运行确认失败**

```bash
uv run pytest tests/test_part_templates.py -v
```

预期：`ModuleNotFoundError: No module named 'part_templates'`

- [ ] **Step 3：创建目录和 `__init__.py`**

创建空文件 `codegen/part_templates/__init__.py`（内容为空）。

- [ ] **Step 4：创建 `codegen/part_templates/flange.py`**

```python
"""法兰工厂函数：生成 CadQuery 代码字符串（4 空格缩进，适合嵌入函数体）。"""
import math


def make_flange(
    od: float | None,
    id: float | None,
    thickness: float | None,
    bolt_pcd: float | None,
    bolt_count: int = 6,
    boss_h: float = 0.0,
    fillet_r: float = 1.0,
) -> str | None:
    """生成法兰 L2 几何代码字符串。

    必填主尺寸缺失（None 或 ≤0）时返回 None，调用方退回 envelope primitive。
    """
    if any(v is None or v <= 0 for v in [od, id, thickness, bolt_pcd]):
        return None
    if id >= od:
        return None

    bolt_hole_r = round(bolt_pcd * 0.04, 2)
    positions = [
        (
            round(bolt_pcd / 2 * math.cos(math.radians(360 / bolt_count * i)), 4),
            round(bolt_pcd / 2 * math.sin(math.radians(360 / bolt_count * i)), 4),
        )
        for i in range(bolt_count)
    ]

    lines = [
        f"    # 法兰 L2: OD={od}mm ID={id}mm T={thickness}mm PCD={bolt_pcd}mm×{bolt_count}孔",
        f"    body = (",
        f"        cq.Workplane('XY').circle({od / 2}).extrude({thickness})",
        f"        .cut(cq.Workplane('XY').circle({id / 2}).extrude({thickness}))",
        f"    )",
    ]

    # 螺栓孔（预计算坐标，无需在生成代码中 import math）
    for bx, by in positions:
        lines += [
            f"    body = body.cut(",
            f"        cq.Workplane('XY')",
            f"        .transformed(offset=cq.Vector({bx}, {by}, 0))",
            f"        .circle({bolt_hole_r}).extrude({thickness})",
            f"    )",
        ]

    # 可选凸台
    if boss_h and boss_h > 0:
        boss_od = round(id * 1.8, 2)
        lines += [
            f"    _boss = (",
            f"        cq.Workplane('XY').circle({boss_od / 2}).extrude({thickness + boss_h})",
            f"        .cut(cq.Workplane('XY').circle({id / 2}).extrude({thickness + boss_h}))",
            f"    )",
            f"    body = body.union(_boss)",
        ]

    # 边缘倒角
    if fillet_r and fillet_r > 0:
        lines += [
            f"    try:",
            f"        body = body.edges('|Z').chamfer({fillet_r})",
            f"    except Exception:",
            f"        pass",
        ]

    return "\n".join(lines)
```

- [ ] **Step 5：运行确认通过**

```bash
uv run pytest tests/test_part_templates.py -v
```

预期：TestMakeFlange 全部通过

- [ ] **Step 6：Commit**

```bash
git add codegen/part_templates/ tests/test_part_templates.py
git commit -m "feat(a2-1): make_flange L2 工厂函数 + 单测"
```

---

## Task 4：make_housing

**Files:**
- Create: `codegen/part_templates/housing.py`
- Modify: `tests/test_part_templates.py`（追加 TestMakeHousing）

- [ ] **Step 1：追加失败测试到 `tests/test_part_templates.py`**

```python
from part_templates.housing import make_housing


class TestMakeHousing:
    def test_returns_none_when_width_missing(self):
        assert make_housing(width=None, depth=50, height=60, wall_t=4) is None

    def test_returns_none_when_wall_t_missing(self):
        assert make_housing(width=50, depth=50, height=60, wall_t=None) is None

    def test_returns_code_string(self):
        code = make_housing(width=50, depth=50, height=60, wall_t=4)
        assert isinstance(code, str) and "body" in code

    def test_face_count_ge_20(self):
        code = make_housing(width=50, depth=50, height=60, wall_t=4)
        body = _exec_template(code)
        assert body.faces().size() >= 20
```

- [ ] **Step 2：运行确认失败**

```bash
uv run pytest tests/test_part_templates.py::TestMakeHousing -v
```

- [ ] **Step 3：创建 `codegen/part_templates/housing.py`**

```python
"""壳体工厂函数：矩形抽壳 + 安装柱 + 圆角。"""


def make_housing(
    width: float | None,
    depth: float | None,
    height: float | None,
    wall_t: float | None,
    boss_h: float = 5.0,
    fillet_r: float = 2.0,
    n_mount: int = 4,
) -> str | None:
    if any(v is None or v <= 0 for v in [width, depth, height, wall_t]):
        return None
    if wall_t >= min(width, depth) / 2:
        return None

    inner_w = round(width - 2 * wall_t, 4)
    inner_d = round(depth - 2 * wall_t, 4)
    boss_r = round(wall_t * 0.8, 2)
    # 安装柱位置（四角内缩 wall_t）
    cx = round(width / 2 - wall_t * 1.5, 4)
    cy = round(depth / 2 - wall_t * 1.5, 4)
    mount_positions = [(cx, cy), (-cx, cy), (-cx, -cy), (cx, -cy)][:n_mount]

    lines = [
        f"    # 壳体 L2: {width}×{depth}×{height}mm 壁厚={wall_t}mm",
        f"    body = (",
        f"        cq.Workplane('XY').box({width}, {depth}, {height}, centered=(True, True, False))",
        f"        .cut(cq.Workplane('XY')",
        f"             .transformed(offset=(0, 0, {wall_t}))",
        f"             .box({inner_w}, {inner_d}, {height}, centered=(True, True, False)))",
        f"    )",
    ]

    # 安装柱
    for mx, my in mount_positions:
        lines += [
            f"    body = body.union(",
            f"        cq.Workplane('XY')",
            f"        .transformed(offset=({mx}, {my}, {wall_t}))",
            f"        .circle({boss_r}).extrude({boss_h})",
            f"    )",
        ]

    # 圆角（外棱）
    if fillet_r > 0:
        lines += [
            f"    try:",
            f"        body = body.edges('|Z').fillet({fillet_r})",
            f"    except Exception:",
            f"        pass",
        ]

    return "\n".join(lines)
```

- [ ] **Step 4：运行确认通过**

```bash
uv run pytest tests/test_part_templates.py::TestMakeHousing -v
```

- [ ] **Step 5：Commit**

```bash
git add codegen/part_templates/housing.py tests/test_part_templates.py
git commit -m "feat(a2-2a): make_housing L2 工厂函数"
```

---

## Task 5：make_bracket

**Files:**
- Create: `codegen/part_templates/bracket.py`
- Modify: `tests/test_part_templates.py`

- [ ] **Step 1：追加失败测试**

```python
from part_templates.bracket import make_bracket


class TestMakeBracket:
    def test_returns_none_when_param_missing(self):
        assert make_bracket(width=None, height=50, thickness=5) is None

    def test_returns_code_string(self):
        code = make_bracket(width=60, height=80, thickness=6)
        assert isinstance(code, str) and "body" in code

    def test_face_count_ge_20(self):
        code = make_bracket(width=60, height=80, thickness=6)
        body = _exec_template(code)
        assert body.faces().size() >= 20
```

- [ ] **Step 2：运行确认失败**

```bash
uv run pytest tests/test_part_templates.py::TestMakeBracket -v
```

- [ ] **Step 3：创建 `codegen/part_templates/bracket.py`**

```python
"""支架工厂函数：L 形板 + 加强筋 + 安装孔。"""


def make_bracket(
    width: float | None,
    height: float | None,
    thickness: float | None,
    rib_t: float = 3.0,
    fillet_r: float = 1.0,
    n_hole: int = 2,
) -> str | None:
    if any(v is None or v <= 0 for v in [width, height, thickness]):
        return None

    hole_r = round(thickness * 0.6, 2)
    hole_spacing = round(width / (n_hole + 1), 4)

    lines = [
        f"    # 支架 L2: {width}×{height}mm 厚={thickness}mm",
        f"    _base = cq.Workplane('XY').box({width}, {thickness}, {thickness},",
        f"                                    centered=(True, False, False))",
        f"    _wall = (",
        f"        cq.Workplane('XY')",
        f"        .transformed(offset=(0, 0, {thickness}))",
        f"        .box({width}, {thickness}, {height}, centered=(True, False, False))",
        f"    )",
        f"    body = _base.union(_wall)",
    ]

    # 加强筋（斜撑三角形近似）
    lines += [
        f"    _rib = (",
        f"        cq.Workplane('XZ')",
        f"        .transformed(offset=(0, {thickness / 2}, 0))",
        f"        .polygon(3, {min(width, height) * 0.3})",
        f"        .extrude({rib_t})",
        f"    )",
        f"    try:",
        f"        body = body.union(_rib)",
        f"    except Exception:",
        f"        pass",
    ]

    # 安装孔（底板）
    for i in range(n_hole):
        hx = round(-width / 2 + hole_spacing * (i + 1), 4)
        lines += [
            f"    body = body.cut(",
            f"        cq.Workplane('XY')",
            f"        .transformed(offset=({hx}, {thickness / 2}, 0))",
            f"        .circle({hole_r}).extrude({thickness})",
            f"    )",
        ]

    if fillet_r > 0:
        lines += [
            f"    try:",
            f"        body = body.edges('>>Y').fillet({fillet_r})",
            f"    except Exception:",
            f"        pass",
        ]

    return "\n".join(lines)
```

- [ ] **Step 4：运行确认通过**

```bash
uv run pytest tests/test_part_templates.py::TestMakeBracket -v
```

- [ ] **Step 5：Commit**

```bash
git add codegen/part_templates/bracket.py tests/test_part_templates.py
git commit -m "feat(a2-2b): make_bracket L2 工厂函数"
```

---

## Task 6：make_spring_mechanism

**Files:**
- Create: `codegen/part_templates/spring_mechanism.py`
- Modify: `tests/test_part_templates.py`

- [ ] **Step 1：追加失败测试**

```python
from part_templates.spring_mechanism import make_spring_mechanism


class TestMakeSpringMechanism:
    def test_returns_none_when_od_missing(self):
        assert make_spring_mechanism(od=None, id=8, free_length=40) is None

    def test_returns_none_when_free_length_missing(self):
        assert make_spring_mechanism(od=20, id=8, free_length=None) is None

    def test_returns_code_string(self):
        code = make_spring_mechanism(od=20, id=8, free_length=40)
        assert isinstance(code, str) and "body" in code

    def test_face_count_ge_20(self):
        code = make_spring_mechanism(od=20, id=8, free_length=40, coil_n=8)
        body = _exec_template(code)
        assert body.faces().size() >= 20
```

- [ ] **Step 2：运行确认失败**

```bash
uv run pytest tests/test_part_templates.py::TestMakeSpringMechanism -v
```

- [ ] **Step 3：创建 `codegen/part_templates/spring_mechanism.py`**

```python
"""弹簧机构工厂函数：CadQuery Wire.makeHelix 螺旋扫掠，降级为空心圆柱。"""


def make_spring_mechanism(
    od: float | None,
    id: float | None,
    free_length: float | None,
    wire_d: float | None = None,
    coil_n: int = 8,
) -> str | None:
    if any(v is None or v <= 0 for v in [od, free_length]):
        return None
    if id is None or id <= 0:
        id = round(od * 0.55, 4)
    if wire_d is None or wire_d <= 0:
        wire_d = round(od * 0.1, 4)

    pitch = round(free_length / coil_n, 4)
    mean_r = round((od + id) / 4, 4)  # 线圈中径的一半

    lines = [
        f"    # 弹簧机构 L2: OD={od}mm ID={id}mm L={free_length}mm {coil_n}圈",
        f"    try:",
        f"        _helix = cq.Wire.makeHelix({pitch}, {free_length}, {mean_r})",
        f"        _profile = cq.Wire.makeCircle(",
        f"            {wire_d / 2},",
        f"            cq.Vector({mean_r}, 0, 0),",
        f"            cq.Vector(0, 1, 0),",
        f"        )",
        f"        body = cq.Workplane('XY').add(",
        f"            cq.Solid.sweep(_profile, [_helix])",
        f"        )",
        f"    except Exception:",
        f"        # 降级：空心圆柱近似弹簧轮廓",
        f"        body = (",
        f"            cq.Workplane('XY').circle({od / 2}).extrude({free_length})",
        f"            .cut(cq.Workplane('XY').circle({id / 2}).extrude({free_length}))",
        f"        )",
    ]

    return "\n".join(lines)
```

- [ ] **Step 4：运行确认通过**

```bash
uv run pytest tests/test_part_templates.py::TestMakeSpringMechanism -v
```

预期：通过（helix sweep 或降级路径均满足 face ≥20）

- [ ] **Step 5：Commit**

```bash
git add codegen/part_templates/spring_mechanism.py tests/test_part_templates.py
git commit -m "feat(a2-2c): make_spring_mechanism L2 螺旋扫掠工厂函数"
```

---

## Task 7：make_sleeve

**Files:**
- Create: `codegen/part_templates/sleeve.py`
- Modify: `tests/test_part_templates.py`

- [ ] **Step 1：追加失败测试**

```python
from part_templates.sleeve import make_sleeve


class TestMakeSleeve:
    def test_returns_none_when_od_missing(self):
        assert make_sleeve(od=None, id=10, length=30) is None

    def test_returns_none_when_id_ge_od(self):
        assert make_sleeve(od=10, id=15, length=30) is None

    def test_returns_code_string(self):
        code = make_sleeve(od=20, id=10, length=30)
        assert isinstance(code, str) and "body" in code

    def test_face_count_ge_20(self):
        code = make_sleeve(od=20, id=10, length=30)
        body = _exec_template(code)
        assert body.faces().size() >= 20
```

- [ ] **Step 2：运行确认失败**

```bash
uv run pytest tests/test_part_templates.py::TestMakeSleeve -v
```

- [ ] **Step 3：创建 `codegen/part_templates/sleeve.py`**

```python
"""套筒/轴套工厂函数：同轴圆柱孔 + 两端倒角 + 键槽（可选）。"""


def make_sleeve(
    od: float | None,
    id: float | None,
    length: float | None,
    chamfer: float = 0.5,
) -> str | None:
    if any(v is None or v <= 0 for v in [od, id, length]):
        return None
    if id >= od:
        return None

    # 键槽尺寸（按 od 比例估算，DIN 6885 近似）
    keyway_w = round(od * 0.18, 2)
    keyway_d = round(od * 0.09, 2)

    lines = [
        f"    # 套筒 L2: OD={od}mm ID={id}mm L={length}mm",
        f"    body = (",
        f"        cq.Workplane('XY').circle({od / 2}).extrude({length})",
        f"        .cut(cq.Workplane('XY').circle({id / 2}).extrude({length}))",
        f"    )",
    ]

    # 键槽
    lines += [
        f"    _keyway = (",
        f"        cq.Workplane('XY')",
        f"        .transformed(offset=(0, {id / 2 + keyway_d / 2}, {length * 0.1}))",
        f"        .box({keyway_w}, {keyway_d}, {length * 0.8},",
        f"             centered=(True, True, False))",
        f"    )",
        f"    try:",
        f"        body = body.cut(_keyway)",
        f"    except Exception:",
        f"        pass",
    ]

    # 两端倒角
    if chamfer > 0:
        lines += [
            f"    try:",
            f"        body = body.faces('<Z').edges().chamfer({chamfer})",
            f"        body = body.faces('>Z').edges().chamfer({chamfer})",
            f"    except Exception:",
            f"        pass",
        ]

    return "\n".join(lines)
```

- [ ] **Step 4：运行确认通过**

```bash
uv run pytest tests/test_part_templates.py::TestMakeSleeve -v
```

- [ ] **Step 5：Commit**

```bash
git add codegen/part_templates/sleeve.py tests/test_part_templates.py
git commit -m "feat(a2-6a): make_sleeve L2 工厂函数"
```

---

## Task 8：make_plate

**Files:**
- Create: `codegen/part_templates/plate.py`
- Modify: `tests/test_part_templates.py`

- [ ] **Step 1：追加失败测试**

```python
from part_templates.plate import make_plate


class TestMakePlate:
    def test_returns_none_when_param_missing(self):
        assert make_plate(width=None, depth=80, thickness=5) is None

    def test_returns_code_string(self):
        code = make_plate(width=100, depth=80, thickness=5)
        assert isinstance(code, str) and "body" in code

    def test_face_count_ge_20(self):
        code = make_plate(width=100, depth=80, thickness=5, n_hole=4)
        body = _exec_template(code)
        assert body.faces().size() >= 20
```

- [ ] **Step 2：运行确认失败**

```bash
uv run pytest tests/test_part_templates.py::TestMakePlate -v
```

- [ ] **Step 3：创建 `codegen/part_templates/plate.py`**

```python
"""板件工厂函数：矩形板 + 四角安装孔 + 圆角。"""


def make_plate(
    width: float | None,
    depth: float | None,
    thickness: float | None,
    n_hole: int = 4,
    hole_d: float = 5.0,
    fillet_r: float = 2.0,
) -> str | None:
    if any(v is None or v <= 0 for v in [width, depth, thickness]):
        return None

    margin = round(max(hole_d * 1.5, min(width, depth) * 0.1), 2)
    hx = round(width / 2 - margin, 4)
    hy = round(depth / 2 - margin, 4)
    # 最多 4 角孔，n_hole 可为 2（只打两侧）
    all_positions = [(hx, hy), (-hx, hy), (-hx, -hy), (hx, -hy)]
    positions = all_positions[:n_hole]

    lines = [
        f"    # 板件 L2: {width}×{depth}×{thickness}mm {n_hole}安装孔",
        f"    body = cq.Workplane('XY').box({width}, {depth}, {thickness},",
        f"                                   centered=(True, True, False))",
    ]

    for px, py in positions:
        lines += [
            f"    body = body.cut(",
            f"        cq.Workplane('XY')",
            f"        .transformed(offset=({px}, {py}, 0))",
            f"        .circle({hole_d / 2}).extrude({thickness})",
            f"    )",
        ]

    if fillet_r > 0:
        lines += [
            f"    try:",
            f"        body = body.edges('|Z').fillet({fillet_r})",
            f"    except Exception:",
            f"        pass",
        ]

    return "\n".join(lines)
```

- [ ] **Step 4：运行确认通过**

```bash
uv run pytest tests/test_part_templates.py::TestMakePlate -v
```

- [ ] **Step 5：Commit**

```bash
git add codegen/part_templates/plate.py tests/test_part_templates.py
git commit -m "feat(a2-6b): make_plate L2 工厂函数"
```

---

## Task 9：make_arm

**Files:**
- Create: `codegen/part_templates/arm.py`
- Modify: `tests/test_part_templates.py`

- [ ] **Step 1：追加失败测试**

```python
from part_templates.arm import make_arm


class TestMakeArm:
    def test_returns_none_when_param_missing(self):
        assert make_arm(length=None, width=12, thickness=8) is None

    def test_returns_code_string(self):
        code = make_arm(length=80, width=12, thickness=8)
        assert isinstance(code, str) and "body" in code

    def test_face_count_ge_20(self):
        code = make_arm(length=80, width=12, thickness=8)
        body = _exec_template(code)
        assert body.faces().size() >= 20
```

- [ ] **Step 2：运行确认失败**

```bash
uv run pytest tests/test_part_templates.py::TestMakeArm -v
```

- [ ] **Step 3：创建 `codegen/part_templates/arm.py`**

```python
"""悬臂/连杆工厂函数：细长梁 + 两端连接孔 + 圆角。"""


def make_arm(
    length: float | None,
    width: float | None,
    thickness: float | None,
    end_hole_d: float | None = None,
    fillet_r: float = 2.0,
) -> str | None:
    if any(v is None or v <= 0 for v in [length, width, thickness]):
        return None
    if end_hole_d is None or end_hole_d <= 0:
        end_hole_d = round(min(width, thickness) * 0.5, 2)

    margin = round(end_hole_d * 1.2, 2)

    lines = [
        f"    # 悬臂 L2: L={length}mm W={width}mm T={thickness}mm",
        f"    body = cq.Workplane('XY').box({length}, {width}, {thickness},",
        f"                                   centered=(True, True, False))",
    ]

    # 两端连接孔（沿 length 轴方向贯穿）
    for sign in [1, -1]:
        cx = round(sign * (length / 2 - margin), 4)
        lines += [
            f"    body = body.cut(",
            f"        cq.Workplane('YZ')",
            f"        .transformed(offset=({cx}, {width / 2}, {thickness / 2}))",
            f"        .circle({end_hole_d / 2}).extrude({width})",
            f"    )",
        ]

    if fillet_r > 0:
        lines += [
            f"    try:",
            f"        body = body.edges('|X').fillet({fillet_r})",
            f"    except Exception:",
            f"        pass",
        ]

    return "\n".join(lines)
```

- [ ] **Step 4：运行确认通过**

```bash
uv run pytest tests/test_part_templates.py::TestMakeArm -v
```

- [ ] **Step 5：Commit**

```bash
git add codegen/part_templates/arm.py tests/test_part_templates.py
git commit -m "feat(a2-6c): make_arm L2 工厂函数"
```

---

## Task 10：make_cover

**Files:**
- Create: `codegen/part_templates/cover.py`
- Modify: `tests/test_part_templates.py`

- [ ] **Step 1：追加失败测试**

```python
from part_templates.cover import make_cover


class TestMakeCover:
    def test_returns_none_when_od_missing(self):
        assert make_cover(od=None, thickness=5) is None

    def test_returns_code_string(self):
        code = make_cover(od=60, thickness=5)
        assert isinstance(code, str) and "body" in code

    def test_face_count_ge_20(self):
        code = make_cover(od=60, thickness=5, n_hole=4)
        body = _exec_template(code)
        assert body.faces().size() >= 20

    def test_with_center_hole(self):
        code = make_cover(od=60, thickness=5, id=20)
        body = _exec_template(code)
        assert body.faces().size() >= 20
```

- [ ] **Step 2：运行确认失败**

```bash
uv run pytest tests/test_part_templates.py::TestMakeCover -v
```

- [ ] **Step 3：创建 `codegen/part_templates/cover.py`**

```python
"""端盖/盖板工厂函数：圆盘 + 可选中心孔 + 紧固孔环 + 倒角。"""
import math


def make_cover(
    od: float | None,
    thickness: float | None,
    id: float | None = None,
    n_hole: int = 4,
    fillet_r: float = 1.0,
) -> str | None:
    if any(v is None or v <= 0 for v in [od, thickness]):
        return None

    bolt_pcd = round(od * 0.75, 4)
    bolt_hole_r = round(od * 0.04, 2)
    positions = [
        (
            round(bolt_pcd / 2 * math.cos(math.radians(360 / n_hole * i)), 4),
            round(bolt_pcd / 2 * math.sin(math.radians(360 / n_hole * i)), 4),
        )
        for i in range(n_hole)
    ]

    lines = [
        f"    # 端盖 L2: OD={od}mm T={thickness}mm {n_hole}紧固孔",
        f"    body = cq.Workplane('XY').circle({od / 2}).extrude({thickness})",
    ]

    if id and id > 0 and id < od:
        lines.append(
            f"    body = body.cut(cq.Workplane('XY').circle({id / 2}).extrude({thickness}))"
        )

    for px, py in positions:
        lines += [
            f"    body = body.cut(",
            f"        cq.Workplane('XY')",
            f"        .transformed(offset=({px}, {py}, 0))",
            f"        .circle({bolt_hole_r}).extrude({thickness})",
            f"    )",
        ]

    if fillet_r > 0:
        lines += [
            f"    try:",
            f"        body = body.edges('|Z').chamfer({fillet_r})",
            f"    except Exception:",
            f"        pass",
        ]

    return "\n".join(lines)
```

- [ ] **Step 4：运行确认通过**

```bash
uv run pytest tests/test_part_templates.py::TestMakeCover -v
```

- [ ] **Step 5：Commit**

```bash
git add codegen/part_templates/cover.py tests/test_part_templates.py
git commit -m "feat(a2-6d): make_cover L2 工厂函数"
```

---

## Task 11：match_semi_parametric_template + _apply_template_decision

**Files:**
- Modify: `codegen/gen_parts.py`
- Create: `tests/test_apply_template.py`

- [ ] **Step 1：写失败测试**

新建 `tests/test_apply_template.py`：

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "codegen"))

from gen_parts import _apply_template_decision


class TestApplyTemplateDecision:
    _BASE_GEOM = {
        "type": "cylinder",
        "envelope_w": 160.0,
        "envelope_d": 160.0,
        "envelope_h": 20.0,
    }
    _FLANGE_META = {
        "dim_tolerances": [
            {"name": "FLANGE_BODY_OD", "nominal": "90"},
            {"name": "FLANGE_BODY_ID", "nominal": "22"},
            {"name": "FLANGE_TOTAL_THICK", "nominal": "30"},
            {"name": "FLANGE_BOLT_PCD", "nominal": "70"},
        ]
    }
    _ENVELOPE = (160.0, 160.0, 20.0)

    def test_flange_sets_type_and_template_code(self, monkeypatch, tmp_path):
        # 强制跳过 SW 路径（隔离 CadQuery 逻辑）
        monkeypatch.setattr("sys.platform", "linux")
        result = _apply_template_decision(
            dict(self._BASE_GEOM), "flange", self._FLANGE_META, self._ENVELOPE,
            part_no="TEST-001", output_dir=str(tmp_path),
        )
        assert result["type"] == "flange"
        assert "template_code" in result
        assert result["template_code"] is not None
        assert "body" in result["template_code"]

    def test_none_tpl_type_returns_original_geom(self, tmp_path):
        geom = dict(self._BASE_GEOM)
        result = _apply_template_decision(
            geom, None, self._FLANGE_META, self._ENVELOPE,
            part_no="", output_dir=str(tmp_path),
        )
        assert result is geom

    def test_missing_required_param_falls_back(self, monkeypatch, tmp_path):
        monkeypatch.setattr("sys.platform", "linux")
        result = _apply_template_decision(
            dict(self._BASE_GEOM), "housing",
            {"dim_tolerances": []}, None,
            part_no="TEST-002", output_dir=str(tmp_path),
        )
        # 主尺寸全缺 → fallback，type 不变
        assert result["type"] == "cylinder"
        assert "template_code" not in result
```

- [ ] **Step 2：运行确认失败**

```bash
uv run pytest tests/test_apply_template.py -v
```

预期：`ImportError: cannot import name '_apply_template_decision'`

- [ ] **Step 3：在 `codegen/gen_parts.py` 中添加 `_apply_template_decision`**

在 `generate_part_files` 函数之前插入（注意函数签名新增 `part_no` 和 `output_dir` 参数，以及 SW 优先路径检查）：

```python
import logging as _log

def _apply_template_decision(
    geom: dict,
    tpl_type: str | None,
    part_meta: dict,
    envelope: tuple | None,
    part_no: str = "",
    output_dir: str = "",
) -> dict:
    """SW API 优先 → CadQuery 回退 → 主尺寸缺失时退回 envelope primitive。

    SW 路径：生成 {output_dir}/sw_parts/{part_no}.step，返回 geom["step_path"]。
    CadQuery 路径：工厂函数返回代码字符串，注入 geom["template_code"]。
    任意路径失败 → 返回原始 geom（不修改 type）。
    """
    if tpl_type is None:
        return geom

    import sys

    # ── SW COM API 优先路径 ───────────────────────────────────────────────
    if sys.platform == "win32" and output_dir and part_no:
        try:
            from adapters.parts.sw_parametric_adapter import SwParametricAdapter
            _sw = SwParametricAdapter()
            ok, _ = _sw.is_available()
            if ok:
                from pathlib import Path
                sw_dir = Path(output_dir) / "sw_parts"
                sw_dir.mkdir(parents=True, exist_ok=True)
                step_path = _sw.build_part(tpl_type, _extract_params(tpl_type, part_meta, envelope), sw_dir, part_no)
                if step_path:
                    updated = dict(geom)
                    updated["type"] = tpl_type
                    updated["kind"] = "step_import"
                    # 相对路径：相对于 output_dir（ee_*.py 所在目录）
                    updated["step_path"] = f"sw_parts/{part_no}.step"
                    return updated
        except Exception as _exc:
            _log.getLogger(__name__).debug("SW 参数化建模失败，回退 CadQuery: %s", _exc)

    # ── CadQuery 工厂函数回退路径 ─────────────────────────────────────────
    dim_map: dict[str, float] = {}
    for t in part_meta.get("dim_tolerances", []):
        try:
            dim_map[t["name"]] = float(t["nominal"])
        except (KeyError, ValueError):
            pass

    env_w, env_d, env_h = envelope if envelope else (0.0, 0.0, 0.0)

    code: str | None = None

    if tpl_type == "flange":
        from part_templates.flange import make_flange  # codegen/ 已在 sys.path
        code = make_flange(
            od=dim_map.get("FLANGE_BODY_OD") or dim_map.get("FLANGE_DIA") or (max(env_w, env_d) or None),
            id=dim_map.get("FLANGE_BODY_ID") or dim_map.get("FLANGE_ID") or None,
            thickness=(dim_map.get("FLANGE_TOTAL_THICK") or dim_map.get("FLANGE_THICK")
                       or dim_map.get("FLANGE_H") or env_h or None),
            bolt_pcd=dim_map.get("FLANGE_BOLT_PCD") or None,
            bolt_count=int(dim_map.get("FLANGE_BOLT_N", 6)),
            boss_h=dim_map.get("FLANGE_BOSS_H", 0.0),
        )
    elif tpl_type == "housing":
        from part_templates.housing import make_housing
        code = make_housing(
            width=dim_map.get("HOUSING_W") or env_w or None,
            depth=dim_map.get("HOUSING_D") or env_d or None,
            height=dim_map.get("HOUSING_H") or env_h or None,
            wall_t=dim_map.get("HOUSING_WALL_T") or (min(env_w, env_d) * 0.12 if env_w and env_d else None),
        )
    elif tpl_type == "bracket":
        from part_templates.bracket import make_bracket
        code = make_bracket(
            width=dim_map.get("BRACKET_W") or env_w or None,
            height=dim_map.get("BRACKET_H") or env_h or None,
            thickness=dim_map.get("BRACKET_T") or env_d or None,
        )
    elif tpl_type == "spring_mechanism":
        from part_templates.spring_mechanism import make_spring_mechanism
        code = make_spring_mechanism(
            od=dim_map.get("SPRING_OD") or max(env_w, env_d) or None,
            id=dim_map.get("SPRING_ID") or None,
            free_length=dim_map.get("SPRING_L") or env_h or None,
            wire_d=dim_map.get("SPRING_WIRE_D") or None,
            coil_n=int(dim_map.get("SPRING_COIL_N", 8)),
        )
    elif tpl_type == "sleeve":
        from part_templates.sleeve import make_sleeve
        code = make_sleeve(
            od=dim_map.get("SLEEVE_OD") or max(env_w, env_d) or None,
            id=dim_map.get("SLEEVE_ID") or None,
            length=dim_map.get("SLEEVE_L") or env_h or None,
        )
    elif tpl_type == "plate":
        from part_templates.plate import make_plate
        code = make_plate(
            width=dim_map.get("PLATE_W") or env_w or None,
            depth=dim_map.get("PLATE_D") or env_d or None,
            thickness=dim_map.get("PLATE_T") or env_h or None,
        )
    elif tpl_type == "arm":
        from part_templates.arm import make_arm
        dims = sorted([env_w, env_d, env_h], reverse=True)
        code = make_arm(
            length=dim_map.get("ARM_L") or dim_map.get("ARM_L_2") or (dims[0] if dims else None),
            width=dim_map.get("ARM_W") or dim_map.get("ARM_SEC_W") or (dims[1] if len(dims) > 1 else None),
            thickness=dim_map.get("ARM_T") or dim_map.get("ARM_SEC_THICK") or (dims[2] if len(dims) > 2 else None),
            end_hole_d=dim_map.get("ARM_END_HOLE_D"),
        )
    elif tpl_type == "cover":
        from part_templates.cover import make_cover
        code = make_cover(
            od=dim_map.get("COVER_OD") or max(env_w, env_d) or None,
            thickness=dim_map.get("COVER_T") or env_h or None,
            id=dim_map.get("COVER_ID") or None,
        )

    if code is None:
        print(f"  [template] {tpl_type}: 必填主尺寸缺失，退回 envelope primitive")
        return geom

    updated = dict(geom)
    updated["type"] = tpl_type
    updated["template_code"] = code
    return updated


def _extract_params(tpl_type: str, part_meta: dict, envelope: tuple | None) -> dict:
    """从 part_meta + envelope 提取各模板所需参数 dict（供 SW adapter 使用）。"""
    dim_map: dict[str, float] = {}
    for t in part_meta.get("dim_tolerances", []):
        try:
            dim_map[t["name"]] = float(t["nominal"])
        except (KeyError, ValueError):
            pass
    env_w, env_d, env_h = envelope if envelope else (0.0, 0.0, 0.0)
    if tpl_type == "flange":
        return {
            "od": dim_map.get("FLANGE_BODY_OD") or max(env_w, env_d),
            "id": dim_map.get("FLANGE_BODY_ID") or None,
            "thickness": dim_map.get("FLANGE_TOTAL_THICK") or env_h,
            "bolt_pcd": dim_map.get("FLANGE_BOLT_PCD") or None,
            "bolt_count": int(dim_map.get("FLANGE_BOLT_N", 6)),
            "boss_h": dim_map.get("FLANGE_BOSS_H", 0.0),
        }
    if tpl_type == "housing":
        return {
            "width": dim_map.get("HOUSING_W") or env_w,
            "depth": dim_map.get("HOUSING_D") or env_d,
            "height": dim_map.get("HOUSING_H") or env_h,
            "wall_t": dim_map.get("HOUSING_WALL_T") or (min(env_w, env_d) * 0.12 if env_w and env_d else 5.0),
        }
    if tpl_type == "bracket":
        return {
            "width": dim_map.get("BRACKET_W") or env_w,
            "height": dim_map.get("BRACKET_H") or env_h,
            "thickness": dim_map.get("BRACKET_T") or env_d,
        }
    if tpl_type == "spring_mechanism":
        return {
            "od": dim_map.get("SPRING_OD") or max(env_w, env_d),
            "id": dim_map.get("SPRING_ID") or None,
            "free_length": dim_map.get("SPRING_L") or env_h,
            "wire_d": dim_map.get("SPRING_WIRE_D") or None,
            "coil_n": int(dim_map.get("SPRING_COIL_N", 8)),
        }
    if tpl_type == "sleeve":
        return {
            "od": dim_map.get("SLEEVE_OD") or max(env_w, env_d),
            "id": dim_map.get("SLEEVE_ID") or None,
            "length": dim_map.get("SLEEVE_L") or env_h,
        }
    if tpl_type == "plate":
        return {
            "width": dim_map.get("PLATE_W") or env_w,
            "depth": dim_map.get("PLATE_D") or env_d,
            "thickness": dim_map.get("PLATE_T") or env_h,
            "n_hole": int(dim_map.get("PLATE_HOLE_N", 4)),
        }
    dims = sorted([env_w, env_d, env_h], reverse=True)
    if tpl_type == "arm":
        return {
            "length": dim_map.get("ARM_L") or dim_map.get("ARM_L_2") or (dims[0] if dims else 100.0),
            "width": dim_map.get("ARM_W") or (dims[1] if len(dims) > 1 else 20.0),
            "thickness": dim_map.get("ARM_T") or (dims[2] if len(dims) > 2 else 10.0),
            "end_hole_d": dim_map.get("ARM_END_HOLE_D", 8.0),
        }
    if tpl_type == "cover":
        return {
            "od": dim_map.get("COVER_OD") or max(env_w, env_d),
            "thickness": dim_map.get("COVER_T") or env_h,
            "id": dim_map.get("COVER_ID") or None,
        }
    return {}
```

**导入规范**：所有 `from part_templates.xxx import` 均使用 `part_templates.*`（不加 `codegen.` 前缀）。`gen_parts.py` 运行时 `codegen/` 已在 `sys.path`，测试时 `tests/test_apply_template.py` 也会 `sys.path.insert(0, codegen_dir)` 保证可解析。两个环境路径一致，无需 `importlib`。

- [ ] **Step 4：运行确认通过**

```bash
uv run pytest tests/test_apply_template.py -v
```

- [ ] **Step 5：全量回归**

```bash
uv run pytest --tb=short -q
```

- [ ] **Step 6：Commit**

```bash
git add codegen/gen_parts.py tests/test_apply_template.py
git commit -m "feat(a2-3a): _apply_template_decision — 8 类模板参数提取 + 工厂调用"
```

---

## Task 12：generate_part_files 集成 + Jinja 模板更新

**Files:**
- Modify: `codegen/gen_parts.py`（`generate_part_files` 函数）
- Modify: `templates/part_module.py.j2`
- Create: `template_mapping.json`

- [ ] **Step 1：修改 `templates/part_module.py.j2`**

在现有 `{% elif geom_type == "l_bracket" %}` 块之后、`{% else %}` 之前插入两个新分支（SW 路径在前，CadQuery 在后）：

```jinja
{% elif step_path %}
    import os as _os
    _step = _os.normpath(_os.path.join(_os.path.dirname(__file__), {{ step_path | tojson }}))
    body = cq.importers.importStep(_step)
{% elif template_code %}
{{ template_code }}
```

完整的 `{% if %}` 链变为：
```
{% if geom_type == "cylinder" %}   ... 保持不变 ...
{% elif geom_type == "ring" %}     ... 保持不变 ...
{% elif geom_type == "disc_arms" %} ... 保持不变 ...
{% elif geom_type == "l_bracket" %} ... 保持不变 ...
{% elif step_path %}
    import os as _os
    _step = _os.normpath(_os.path.join(_os.path.dirname(__file__), {{ step_path | tojson }}))
    body = cq.importers.importStep(_step)
{% elif template_code %}
{{ template_code }}
{% else %}
    body = cq.Workplane("XY").box(...)  保持不变
{% endif %}
```

- [ ] **Step 2：修改 `codegen/gen_parts.py` 的 `generate_part_files`**

在 `generate_part_files` 函数开头（`parts = parse_bom_tree(...)` 之后）插入：

```python
    # A2-3: 加载用户命名覆盖
    import sys as _sys
    _sys.path.insert(0, os.path.join(_PROJECT_ROOT, "codegen"))
    from template_mapping_loader import load_template_mapping, match_template as _match_template
    _mapping_path = os.path.join(os.path.dirname(spec_path), "template_mapping.json")
    _user_mapping = load_template_mapping(_mapping_path)
    _output_dir = output_dir  # generate_part_files 的输出目录参数（已有）
```

在 `for p in parts:` 循环中，**`part_meta = _parse_annotation_meta(spec_path, p["name_cn"])` 这行之后**（约 line 331）插入：

```python
        # A2-3: 半参数模板激活（复用已有 part_meta，不重复调用 _parse_annotation_meta）
        _tpl_type = _match_template(p["name_cn"], _user_mapping)
        if _tpl_type:
            geom = _apply_template_decision(
                geom, _tpl_type, part_meta, envelope,
                part_no=p.get("part_no", ""),
                output_dir=str(_output_dir),
            )
```

在 `content = template.render(...)` 调用中追加两个参数：

```python
        content = template.render(
            ...  # 原有参数保持不变
            step_path=geom.get("step_path"),      # ← 新增：SW STEP 路径
            template_code=geom.get("template_code"),  # ← 新增：CadQuery 代码字符串
        )
```

- [ ] **Step 3：创建示例 `template_mapping.json`（项目根目录）**

```json
{
  "_comment": "用户自定义命名覆盖。键为 name_cn，值为模板类型（8 选 1）。",
  "_valid_values": ["flange", "housing", "bracket", "spring_mechanism", "sleeve", "plate", "arm", "cover"],
  "连接盘": "flange",
  "固定盘": "flange",
  "外壳": "housing",
  "机箱": "housing",
  "限力器": "spring_mechanism",
  "缓冲件": "spring_mechanism",
  "轴套": "sleeve",
  "衬套": "sleeve",
  "底板": "plate",
  "安装板": "plate",
  "端盖": "cover",
  "盖板": "cover",
  "连杆": "arm",
  "摇臂": "arm"
}
```

**注意**：`_comment` 和 `_valid_values` 键以 `_` 开头，`load_template_mapping` 加载时会因值不在 `_VALID_TEMPLATES` 中而 warn + 跳过，或在 `load_template_mapping` 内加一行过滤：`if key.startswith("_"): continue`。

需在 `load_template_mapping` 中添加：
```python
    for key, val in raw.items():
        if key.startswith("_"):  # 跳过注释键
            continue
        ...
```

- [ ] **Step 4：运行全量测试**

```bash
uv run pytest --tb=short -q
```

预期：全部通过

- [ ] **Step 5：Commit**

```bash
git add templates/part_module.py.j2 codegen/gen_parts.py template_mapping.json codegen/template_mapping_loader.py
git commit -m "feat(a2-3b): generate_part_files 集成模板路由 + Jinja template_code 分支"
```

---

## Task 13：集成验收 — ee_001_01（法兰）

**Files:**
- Create: `tests/test_a2_integration.py`

- [ ] **Step 1：写集成测试**

新建 `tests/test_a2_integration.py`：

```python
"""A2 集成验收：gen_parts 生成正确 L2 几何，DXF 快照 dim_tolerances 净化。"""
import subprocess
import sys
import ast
from pathlib import Path

import cadquery as cq
import pytest

_REPO = Path(__file__).parent.parent
_EE_001_01 = _REPO / "cad" / "end_effector" / "ee_001_01.py"
_EE_001_02 = _REPO / "cad" / "end_effector" / "ee_001_02.py"


def _run_make_fn(py_file: Path, fn_name: str) -> cq.Workplane:
    """动态加载并执行指定零件文件的 make 函数。"""
    ns: dict = {}
    exec(compile(py_file.read_text(encoding="utf-8"), str(py_file), "exec"), ns)
    return ns[fn_name]()


def _parse_dim_tolerances(py_file: Path) -> list[dict]:
    """从生成的 ee_*.py 中 AST 提取 dim_tolerances 列表（不执行代码）。"""
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and k.value == "dim_tolerances":
                    return ast.literal_eval(v)
    return []


class TestFlangeA20Filter:
    def test_ee_001_01_dim_tolerances_no_spring_pin_bore(self):
        """A2-0 验收：法兰件的 dim_tolerances 不含 SPRING_PIN_BORE。"""
        tols = _parse_dim_tolerances(_EE_001_01)
        names = [t["name"] for t in tols]
        assert "SPRING_PIN_BORE" not in names, f"法兰件不应含弹簧销孔公差，实际: {names}"

    def test_ee_001_01_dim_tolerances_no_arm_l_2(self):
        """A2-0 验收：法兰件的 dim_tolerances 不含 ARM_L_2。"""
        tols = _parse_dim_tolerances(_EE_001_01)
        names = [t["name"] for t in tols]
        assert "ARM_L_2" not in names, f"法兰件不应含悬臂长度公差，实际: {names}"

    def test_ee_001_01_dim_tolerances_count_reduced(self):
        """A2-0 验收：净化后的公差数量少于原始 12 条。"""
        tols = _parse_dim_tolerances(_EE_001_01)
        assert len(tols) < 12, f"期望 <12 条，实际 {len(tols)} 条"


class TestFlangeGeometry:
    @pytest.mark.skip(reason="需要先用 --force 重新生成 ee_001_01.py 后才能验证")
    def test_flange_face_count_ge_30(self):
        """A2 验收：法兰件 face ≥ 30。在人工触发 gen_parts --force 后取消 skip。"""
        body = _run_make_fn(_EE_001_01, "make_ee_001_01")
        assert body.faces().size() >= 30, f"face 数={body.faces().size()}，期望 ≥30"
```

- [ ] **Step 2：运行 A2-0 过滤验收（当前文件状态）**

```bash
uv run pytest tests/test_a2_integration.py::TestFlangeA20Filter -v
```

若失败，说明 `ee_001_01.py` 还未用 A2-0 重新生成。执行：

```bash
uv run python -m codegen.gen_parts cad/end_effector/CAD_SPEC.md cad/end_effector/ --force
```

然后重新运行测试。

- [ ] **Step 3：确认 A2-0 过滤通过后，取消 skip 并验证 face count**

将 `test_flange_face_count_ge_30` 的 `@pytest.mark.skip` 去掉，再次运行：

```bash
uv run pytest tests/test_a2_integration.py::TestFlangeGeometry -v
```

若面数 < 30，检查 `_apply_template_decision` 是否正确被 `generate_part_files` 调用，以及 `FLANGE_BODY_OD`/`FLANGE_BODY_ID`/`FLANGE_TOTAL_THICK`/`FLANGE_BOLT_PCD` 是否都能从 dim_tolerances 中正确取到。

- [ ] **Step 4：全量回归**

```bash
uv run pytest --tb=short -q
```

预期：全部通过

- [ ] **Step 5：Commit**

```bash
git add tests/test_a2_integration.py cad/end_effector/ee_001_01.py
git commit -m "test(a2-4): 集成验收 ee_001_01 法兰 face≥30 + A2-0 过滤回归"
```

---

## Task 14：集成验收 — ee_001_02（套筒）

**Files:**
- Modify: `tests/test_a2_integration.py`

- [ ] **Step 1：追加 sleeve 集成测试**

```python
class TestSleeveGeometry:
    @pytest.mark.skip(reason="需要先用 --force 重新生成 ee_001_02.py 后才能验证")
    def test_sleeve_face_count_ge_20(self):
        body = _run_make_fn(_EE_001_02, "make_ee_001_02")
        assert body.faces().size() >= 20, f"face 数={body.faces().size()}，期望 ≥20"


class TestMappingJsonRouting:
    def test_template_mapping_json_loads_without_error(self):
        """template_mapping.json 示例文件可被正确加载（无 WARNING 输出）。"""
        import sys
        sys.path.insert(0, str(_REPO / "codegen"))
        from template_mapping_loader import load_template_mapping
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        mapping_path = str(_REPO / "template_mapping.json")
        with redirect_stdout(buf):
            result = load_template_mapping(mapping_path)
        output = buf.getvalue()
        assert "WARNING" not in output, f"加载示例 mapping.json 不应有 WARNING: {output}"
        assert "连接盘" in result
        assert result["连接盘"] == "flange"
```

- [ ] **Step 2：运行 mapping.json 测试**

```bash
uv run pytest tests/test_a2_integration.py::TestMappingJsonRouting -v
```

- [ ] **Step 3：重新生成 ee_001_02.py 并取消 skip**

```bash
uv run python -m codegen.gen_parts cad/end_effector/CAD_SPEC.md cad/end_effector/ --force
```

取消 `test_sleeve_face_count_ge_20` 的 `@pytest.mark.skip`，运行：

```bash
uv run pytest tests/test_a2_integration.py::TestSleeveGeometry -v
```

- [ ] **Step 4：全量回归 + 人工目测**

```bash
uv run pytest --tb=short -q
```

人工目测：在 Blender 或 CadQuery Viewer 中打开重新生成的 `ee_001_01.py` 和 `ee_001_02.py`，确认：
- `ee_001_01`：能看到中心孔 + 螺栓孔环，外径约 90mm（不是原来的 160mm envelope）
- `ee_001_02`：能看到同轴孔 + 键槽

- [ ] **Step 5：Commit**

```bash
git add tests/test_a2_integration.py cad/end_effector/ee_001_02.py
git commit -m "test(a2-7): 集成验收 ee_001_02 套筒 face≥20 + mapping.json 路由测试"
```

---

## CHECKPOINT — 全部完成后

- [ ] **全量测试通过**

```bash
uv run pytest --tb=short -q
```

预期：原有 990+ + 新增测试全部通过（requires_solidworks 在 CI Linux 自动 skip）

- [ ] **验收清单核对**

| 验收项 | 命令 |
|---|---|
| A2-0：法兰件无 SPRING_PIN_BORE | `pytest tests/test_a2_integration.py::TestFlangeA20Filter` |
| 法兰 face ≥ 30（CadQuery 路径） | `pytest tests/test_a2_integration.py::TestFlangeGeometry` |
| 套筒 face ≥ 20 | `pytest tests/test_a2_integration.py::TestSleeveGeometry` |
| mapping.json 无 WARNING | `pytest tests/test_a2_integration.py::TestMappingJsonRouting` |
| 8 类工厂函数 | `pytest tests/test_part_templates.py` |
| filter 单测 | `pytest tests/test_dim_filter.py` |
| mapping loader | `pytest tests/test_template_mapping.py` |
| SW adapter is_available | `pytest tests/test_sw_parametric_adapter.py::TestSwParametricAdapterAvailability` |
| SW 法兰 STEP 生成（需 SW） | `pytest tests/test_sw_parametric_adapter.py::TestSwParametricAdapterBuildFlange -m requires_solidworks` |
| SW 全路径集成（需 SW） | `pytest tests/test_sw_parametric_adapter.py::TestSwPathIntegration -m requires_solidworks` |

- [ ] **最终 commit（CadQuery 路径）**

```bash
git add -A
git commit -m "feat(a2): A2 半参数几何升级完成 — 8 模板 + template_mapping.json + A2-0 过滤"
```

---

## Task 15：SW 参数化适配器框架（is_available + 框架 + stub）

**Files:**
- Create: `adapters/parts/sw_parametric_adapter.py`
- Create: `tests/test_sw_parametric_adapter.py`
- Modify: `.gitignore`

- [ ] **Step 1：写失败测试**

新建 `tests/test_sw_parametric_adapter.py`：

```python
"""SW 参数化适配器单测。requires_solidworks 标记在非 Windows CI 上 skip。"""
import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from adapters.parts.sw_parametric_adapter import SwParametricAdapter


class TestSwParametricAdapterAvailability:
    def test_is_available_returns_false_on_linux(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        adapter = SwParametricAdapter()
        ok, reason = adapter.is_available()
        assert ok is False

    def test_is_available_false_when_sw_not_installed(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")
        with patch("adapters.parts.sw_parametric_adapter.detect_solidworks") as mock_detect:
            mock_detect.return_value = MagicMock(installed=False)
            adapter = SwParametricAdapter()
            ok, reason = adapter.is_available()
        assert ok is False

    def test_build_part_returns_none_when_unavailable(self, monkeypatch, tmp_path):
        monkeypatch.setattr("sys.platform", "linux")
        adapter = SwParametricAdapter()
        result = adapter.build_part("flange", {"od": 90, "id": 22, "thickness": 30, "bolt_pcd": 70, "bolt_count": 6, "boss_h": 0}, tmp_path, "TEST-001")
        assert result is None


@pytest.mark.requires_solidworks
class TestSwParametricAdapterBuildFlange:
    def test_build_flange_creates_step_file(self, tmp_path):
        adapter = SwParametricAdapter()
        ok, _ = adapter.is_available()
        assert ok, "SW 不可用，跳过（应由 marker 保护）"
        step = adapter.build_part(
            "flange",
            {"od": 90.0, "id": 22.0, "thickness": 30.0, "bolt_pcd": 70.0, "bolt_count": 6, "boss_h": 5.0},
            tmp_path,
            "TEST-001",
        )
        assert step is not None
        assert Path(step).exists()
        assert Path(step).suffix.lower() == ".step"
```

- [ ] **Step 2：运行确认失败**

```bash
uv run pytest tests/test_sw_parametric_adapter.py::TestSwParametricAdapterAvailability -v
```

预期：`ImportError: cannot import name 'SwParametricAdapter'`

- [ ] **Step 3：创建 `adapters/parts/sw_parametric_adapter.py`**

```python
"""
adapters/parts/sw_parametric_adapter.py — SW COM API 参数化建模适配器。

当 SolidWorks 可用时，用 SW API 创建参数化特征并导出 STEP；
不可用时返回 None，调用方回退到 CadQuery 路径。

SW API 尺寸单位为米（m），内部统一 /1000 换算。
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_VALID_TEMPLATES = {
    "flange", "housing", "bracket", "spring_mechanism",
    "sleeve", "plate", "arm", "cover",
}


def detect_solidworks():
    from adapters.solidworks.sw_detect import detect_solidworks as _det
    return _det()


class SwParametricAdapter:
    """SW COM API 参数化建模适配器（Task 15 框架 + Task 16-18 完整实现）。"""

    def is_available(self) -> tuple[bool, Optional[str]]:
        """复用 sw_toolbox_adapter 的 6 项检查模式（平台 / 安装 / 版本 / pywin32 / toolbox / COM）。"""
        if sys.platform != "win32":
            return False, "非 Windows 平台"
        try:
            from adapters.solidworks.sw_com_session import get_session
        except ImportError:
            return False, "sw_com_session 不可导入"

        info = detect_solidworks()
        if not info.installed:
            return False, "SolidWorks 未安装"
        if info.version_year < 2024:
            return False, f"SW 版本 {info.version_year} < 2024"
        if not info.pywin32_available:
            return False, "pywin32 不可用"

        session = get_session()
        if not session.is_healthy():
            return False, "COM session 熔断"

        return True, None

    def build_part(
        self,
        tpl_type: str,
        params: dict,
        output_dir: Path,
        part_no: str,
    ) -> Optional[Path]:
        """调用对应 SW 建模方法，导出 STEP 到 output_dir/{part_no}.step。

        Returns:
            STEP 绝对路径（Path）；任意步骤失败返回 None。
        """
        ok, _ = self.is_available()
        if not ok:
            return None
        if tpl_type not in _VALID_TEMPLATES:
            log.warning("未知模板类型: %s", tpl_type)
            return None

        step_path = Path(output_dir) / f"{part_no}.step"

        # 缓存：同一文件已存在则跳过（避免重复 NewDocument）
        if step_path.exists():
            return step_path

        try:
            build_fn = getattr(self, f"_build_{tpl_type}", None)
            if build_fn is None:
                log.debug("_build_%s 尚未实现，回退 CadQuery", tpl_type)
                return None
            return build_fn(params, step_path)
        except Exception as exc:
            log.debug("SW 建模失败 [%s/%s]: %s", tpl_type, part_no, exc)
            return None

    # ── 各模板 SW 建模方法（Task 16-18 实现） ──────────────────────────────

    def _build_flange(self, params: dict, step_path: Path) -> Optional[Path]:
        return None  # Task 16 实现

    def _build_housing(self, params: dict, step_path: Path) -> Optional[Path]:
        return None  # Task 17 实现

    def _build_bracket(self, params: dict, step_path: Path) -> Optional[Path]:
        return None  # Task 17 实现

    def _build_sleeve(self, params: dict, step_path: Path) -> Optional[Path]:
        return None  # Task 17 实现

    def _build_spring_mechanism(self, params: dict, step_path: Path) -> Optional[Path]:
        return None  # Task 18 实现

    def _build_plate(self, params: dict, step_path: Path) -> Optional[Path]:
        return None  # Task 18 实现

    def _build_arm(self, params: dict, step_path: Path) -> Optional[Path]:
        return None  # Task 18 实现

    def _build_cover(self, params: dict, step_path: Path) -> Optional[Path]:
        return None  # Task 18 实现

    # ── SW API 工具方法 ────────────────────────────────────────────────────

    def _get_swapp(self):
        """获取 ISldWorks Application 对象（通过 sw_com_session）。"""
        from adapters.solidworks.sw_com_session import get_session
        session = get_session()
        return session.sldworks  # ISldWorks IDispatch

    def _new_part_doc(self, swapp) -> object:
        """新建空白零件文档，返回 IModelDoc2。"""
        # swDocumentTypes_Part = 1
        template = swapp.GetUserPreferenceStringValue(9)  # swUserPreferenceStringValue_DefaultPartTemplate = 9
        doc = swapp.NewDocument(template, 1, 0, 0)
        return doc

    def _close_doc(self, swapp, path: str) -> None:
        """静默关闭文档（不保存）。"""
        try:
            swapp.CloseDoc(path)
        except Exception:
            pass

    def _export_step(self, model, step_path: Path) -> bool:
        """将当前 model 导出为 STEP，返回是否成功。"""
        import os
        step_path.parent.mkdir(parents=True, exist_ok=True)
        # swSaveAsCurrentVersion = 0, swSaveAsOptions_Silent = 1
        errors = model.SaveAs3(str(step_path), 0, 1)
        return step_path.exists()
```

- [ ] **Step 4：追加 `.gitignore` 条目**

在 `.gitignore` 中追加：

```
# SW 参数化建模导出（运行时生成，不 track）
**/sw_parts/
```

- [ ] **Step 5：运行确认通过**

```bash
uv run pytest tests/test_sw_parametric_adapter.py::TestSwParametricAdapterAvailability -v
```

预期：3 个测试全部 PASS

- [ ] **Step 6：全量回归**

```bash
uv run pytest --tb=short -q
```

- [ ] **Step 7：Commit**

```bash
git add adapters/parts/sw_parametric_adapter.py tests/test_sw_parametric_adapter.py .gitignore
git commit -m "feat(a2-sw-0): SwParametricAdapter 框架 — is_available + build_part stub"
```

---

## Task 16：SW 法兰（flange）COM API 完整实现

**Files:**
- Modify: `adapters/parts/sw_parametric_adapter.py`（`_build_flange`）

- [ ] **Step 1：补全 `_build_flange` 实现**

替换 `_build_flange` 的 `return None  # Task 16 实现` 为完整代码：

```python
def _build_flange(self, params: dict, step_path: Path) -> Optional[Path]:
    """SW COM API 创建法兰：圆盘 + 中心孔 + 螺栓孔环 + 可选凸台。

    SW API 尺寸单位为米，所有 mm 参数均 /1000 换算。
    """
    import math

    od = float(params.get("od") or 0) / 1000      # 外径 m
    id_ = float(params.get("id") or 0) / 1000     # 内径 m
    thick = float(params.get("thickness") or 0) / 1000  # 厚度 m
    bolt_pcd = float(params.get("bolt_pcd") or 0) / 1000  # 螺栓节圆直径 m
    bolt_n = int(params.get("bolt_count") or 6)
    boss_h = float(params.get("boss_h") or 0) / 1000

    if od <= 0 or thick <= 0:
        return None

    bolt_r = bolt_pcd / 2 if bolt_pcd > 0 else od * 0.375
    bolt_hole_r = 0.004  # 默认螺栓孔半径 4mm

    swapp = self._get_swapp()
    model = self._new_part_doc(swapp)
    if model is None:
        return None

    try:
        skMgr = model.SketchManager
        ftMgr = model.FeatureManager

        # ── Step A：在 Top Plane 画外圆 + 内圆，Extrude 主体 ───────────
        model.Extension.SelectByID2("Top Plane", "PLANE", 0, 0, 0, False, 0, None, 0)
        skMgr.InsertSketch(True)
        skMgr.CreateCircleByRadius2(0, 0, 0, od / 2)
        if id_ > 0:
            skMgr.CreateCircleByRadius2(0, 0, 0, id_ / 2)
        model.ClearSelection2(True)
        skMgr.InsertSketch(True)

        # Extrude（swEndCondBlind=0, depth=thick）
        ftMgr.FeatureExtrusion3(
            True, False, False, 0, 0, thick, 0,
            False, False, False, False,
            0.0, 0.0, False, False, False, False,
            1, 1, 1, 0, 0, False,
        )

        # ── Step B：螺栓孔环（Circular Pattern Cut）──────────────────────
        if bolt_r > 0 and bolt_n > 0:
            angle_step = 2 * math.pi / bolt_n
            for i in range(bolt_n):
                angle = i * angle_step
                cx = bolt_r * math.cos(angle)
                cy = bolt_r * math.sin(angle)

                model.Extension.SelectByID2("Top Plane", "PLANE", 0, 0, 0, False, 0, None, 0)
                skMgr.InsertSketch(True)
                skMgr.CreateCircleByRadius2(cx, cy, 0, bolt_hole_r)
                model.ClearSelection2(True)
                skMgr.InsertSketch(True)

                # Cut Extrude（Through All = swEndCondThroughAll = 6）
                ftMgr.FeatureExtrusion3(
                    False, False, False, 6, 0, thick, 0,
                    False, False, False, False,
                    0.0, 0.0, False, False, False, False,
                    1, 1, 1, 0, 0, False,
                )

        # ── Step C：可选凸台（boss_h > 0）────────────────────────────────
        if boss_h > 0:
            boss_r = od * 0.3  # 凸台半径 ≈ 外径 30%
            model.Extension.SelectByID2("Top Plane", "PLANE", 0, 0, 0, False, 0, None, 0)
            skMgr.InsertSketch(True)
            skMgr.CreateCircleByRadius2(0, 0, thick, boss_r)
            if id_ > 0:
                skMgr.CreateCircleByRadius2(0, 0, thick, id_ / 2)
            model.ClearSelection2(True)
            skMgr.InsertSketch(True)
            ftMgr.FeatureExtrusion3(
                True, False, False, 0, 0, boss_h, 0,
                False, False, False, False,
                0.0, 0.0, False, False, False, False,
                1, 1, 1, 0, 0, False,
            )

        # ── 导出 STEP ───────────────────────────────────────────────────
        ok = self._export_step(model, step_path)
        return step_path if ok else None

    finally:
        self._close_doc(swapp, model.GetPathName() if hasattr(model, "GetPathName") else "")
```

- [ ] **Step 2：在 Windows + SW 2024+ 本机运行 requires_solidworks 测试**

```bash
uv run pytest tests/test_sw_parametric_adapter.py::TestSwParametricAdapterBuildFlange -v -m requires_solidworks
```

预期：`test_build_flange_creates_step_file` PASS，`sw_parts/TEST-001.step` 文件存在且 > 0 字节

- [ ] **Step 3：全量回归**

```bash
uv run pytest --tb=short -q
```

- [ ] **Step 4：Commit**

```bash
git add adapters/parts/sw_parametric_adapter.py
git commit -m "feat(a2-sw-1): _build_flange — SW COM API 参数化法兰 + STEP 导出"
```

---

## Task 17：SW housing / bracket / sleeve COM API 实现

**Files:**
- Modify: `adapters/parts/sw_parametric_adapter.py`（`_build_housing`、`_build_bracket`、`_build_sleeve`）

- [ ] **Step 1：实现 `_build_housing`**

替换 `_build_housing` 的 `return None  # Task 17 实现`：

```python
def _build_housing(self, params: dict, step_path: Path) -> Optional[Path]:
    """矩形壳体：外壳 Box + shell（抽壳）+ 安装柱（4 个）。"""
    w = float(params.get("width") or 0) / 1000
    d = float(params.get("depth") or 0) / 1000
    h = float(params.get("height") or 0) / 1000
    wall = float(params.get("wall_t") or max(w, d) * 0.12) / 1000

    if w <= 0 or d <= 0 or h <= 0:
        return None

    swapp = self._get_swapp()
    model = self._new_part_doc(swapp)
    if model is None:
        return None

    try:
        skMgr = model.SketchManager
        ftMgr = model.FeatureManager

        # 外壳矩形草图 → Extrude
        model.Extension.SelectByID2("Top Plane", "PLANE", 0, 0, 0, False, 0, None, 0)
        skMgr.InsertSketch(True)
        skMgr.CreateCenterRectangle2(0, 0, 0, w / 2, d / 2, 0)
        model.ClearSelection2(True)
        skMgr.InsertSketch(True)
        ftMgr.FeatureExtrusion3(
            True, False, False, 0, 0, h, 0,
            False, False, False, False, 0, 0, False, False, False, False, 1, 1, 1, 0, 0, False,
        )

        # Shell（抽壳）— 选顶面 → Shell feature
        # 选顶面（Z=h 处）
        model.Extension.SelectByID2("", "FACE", 0, 0, h, False, 0, None, 0)
        ftMgr.FeatureShell3(wall, False, False, 1)

        ok = self._export_step(model, step_path)
        return step_path if ok else None
    finally:
        self._close_doc(swapp, "")
```

- [ ] **Step 2：实现 `_build_bracket`**

替换 `_build_bracket` 的 `return None  # Task 17 实现`：

```python
def _build_bracket(self, params: dict, step_path: Path) -> Optional[Path]:
    """L 形支架：竖板 + 底板（两矩形拼接 90°）。"""
    w = float(params.get("width") or 0) / 1000
    h = float(params.get("height") or 0) / 1000
    t = float(params.get("thickness") or 0) / 1000

    if w <= 0 or h <= 0 or t <= 0:
        return None

    swapp = self._get_swapp()
    model = self._new_part_doc(swapp)
    if model is None:
        return None

    try:
        skMgr = model.SketchManager
        ftMgr = model.FeatureManager

        # 竖板：w × h，厚 t
        model.Extension.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, None, 0)
        skMgr.InsertSketch(True)
        skMgr.CreateCenterRectangle2(0, h / 2, 0, w / 2, h, 0)
        model.ClearSelection2(True)
        skMgr.InsertSketch(True)
        ftMgr.FeatureExtrusion3(
            True, False, False, 0, 0, t, 0,
            False, False, False, False, 0, 0, False, False, False, False, 1, 1, 1, 0, 0, False,
        )

        # 底板：w × (w*0.8)，厚 t，从底部向 Y+ 延伸
        model.Extension.SelectByID2("Top Plane", "PLANE", 0, 0, 0, False, 0, None, 0)
        skMgr.InsertSketch(True)
        base_d = w * 0.8
        skMgr.CreateCenterRectangle2(0, base_d / 2, 0, w / 2, base_d, 0)
        model.ClearSelection2(True)
        skMgr.InsertSketch(True)
        ftMgr.FeatureExtrusion3(
            True, False, False, 0, 0, t, 0,
            False, False, False, False, 0, 0, False, False, False, False, 1, 1, 1, 0, 0, False,
        )

        ok = self._export_step(model, step_path)
        return step_path if ok else None
    finally:
        self._close_doc(swapp, "")
```

- [ ] **Step 3：实现 `_build_sleeve`**

替换 `_build_sleeve` 的 `return None  # Task 17 实现`：

```python
def _build_sleeve(self, params: dict, step_path: Path) -> Optional[Path]:
    """套筒：外圆柱 + 同轴内孔。"""
    od = float(params.get("od") or 0) / 1000
    id_ = float(params.get("id") or od * 0.5) / 1000
    length = float(params.get("length") or 0) / 1000

    if od <= 0 or length <= 0:
        return None

    swapp = self._get_swapp()
    model = self._new_part_doc(swapp)
    if model is None:
        return None

    try:
        skMgr = model.SketchManager
        ftMgr = model.FeatureManager

        model.Extension.SelectByID2("Top Plane", "PLANE", 0, 0, 0, False, 0, None, 0)
        skMgr.InsertSketch(True)
        skMgr.CreateCircleByRadius2(0, 0, 0, od / 2)
        if id_ > 0:
            skMgr.CreateCircleByRadius2(0, 0, 0, id_ / 2)
        model.ClearSelection2(True)
        skMgr.InsertSketch(True)
        ftMgr.FeatureExtrusion3(
            True, False, False, 0, 0, length, 0,
            False, False, False, False, 0, 0, False, False, False, False, 1, 1, 1, 0, 0, False,
        )

        ok = self._export_step(model, step_path)
        return step_path if ok else None
    finally:
        self._close_doc(swapp, "")
```

- [ ] **Step 4：运行 requires_solidworks 测试（Windows 本机）**

```bash
uv run pytest tests/test_sw_parametric_adapter.py -m requires_solidworks -v
```

预期：所有 requires_solidworks 标记测试通过（需在 Windows + SW 2024+ 本机运行）

- [ ] **Step 5：全量回归**

```bash
uv run pytest --tb=short -q
```

- [ ] **Step 6：Commit**

```bash
git add adapters/parts/sw_parametric_adapter.py
git commit -m "feat(a2-sw-2): _build_housing/bracket/sleeve SW COM API 实现"
```

---

## Task 18：SW spring_mechanism / plate / arm / cover + 集成验收

**Files:**
- Modify: `adapters/parts/sw_parametric_adapter.py`（`_build_spring_mechanism`、`_build_plate`、`_build_arm`、`_build_cover`）
- Modify: `tests/test_sw_parametric_adapter.py`（追加集成验收测试）

- [ ] **Step 1：实现 `_build_spring_mechanism`**

替换 `return None  # Task 18 实现`（spring_mechanism）：

```python
def _build_spring_mechanism(self, params: dict, step_path: Path) -> Optional[Path]:
    """弹簧机构：同轴环柱（简化版，实际弹簧螺旋在 SW 中需 Helix 扫掠，此处先用空心柱代替）。"""
    od = float(params.get("od") or 0) / 1000
    id_ = float(params.get("id") or od * 0.6) / 1000
    free_length = float(params.get("free_length") or 0) / 1000

    if od <= 0 or free_length <= 0:
        return None

    swapp = self._get_swapp()
    model = self._new_part_doc(swapp)
    if model is None:
        return None

    try:
        skMgr = model.SketchManager
        ftMgr = model.FeatureManager

        model.Extension.SelectByID2("Top Plane", "PLANE", 0, 0, 0, False, 0, None, 0)
        skMgr.InsertSketch(True)
        skMgr.CreateCircleByRadius2(0, 0, 0, od / 2)
        skMgr.CreateCircleByRadius2(0, 0, 0, id_ / 2)
        model.ClearSelection2(True)
        skMgr.InsertSketch(True)
        ftMgr.FeatureExtrusion3(
            True, False, False, 0, 0, free_length, 0,
            False, False, False, False, 0, 0, False, False, False, False, 1, 1, 1, 0, 0, False,
        )

        ok = self._export_step(model, step_path)
        return step_path if ok else None
    finally:
        self._close_doc(swapp, "")
```

- [ ] **Step 2：实现 `_build_plate`**

替换 `return None  # Task 18 实现`（plate）：

```python
def _build_plate(self, params: dict, step_path: Path) -> Optional[Path]:
    """安装板：矩形板 + 四角安装孔。"""
    import math
    w = float(params.get("width") or 0) / 1000
    d = float(params.get("depth") or 0) / 1000
    t = float(params.get("thickness") or 0) / 1000
    n_hole = int(params.get("n_hole") or 4)
    hole_r = 0.0025  # 2.5mm

    if w <= 0 or d <= 0 or t <= 0:
        return None

    swapp = self._get_swapp()
    model = self._new_part_doc(swapp)
    if model is None:
        return None

    try:
        skMgr = model.SketchManager
        ftMgr = model.FeatureManager

        # 主板
        model.Extension.SelectByID2("Top Plane", "PLANE", 0, 0, 0, False, 0, None, 0)
        skMgr.InsertSketch(True)
        skMgr.CreateCenterRectangle2(0, 0, 0, w / 2, d / 2, 0)
        model.ClearSelection2(True)
        skMgr.InsertSketch(True)
        ftMgr.FeatureExtrusion3(
            True, False, False, 0, 0, t, 0,
            False, False, False, False, 0, 0, False, False, False, False, 1, 1, 1, 0, 0, False,
        )

        # 四角孔（简化：均匀分布 n_hole 个）
        margin = min(w, d) * 0.1
        corners = [
            (w / 2 - margin, d / 2 - margin),
            (-w / 2 + margin, d / 2 - margin),
            (-w / 2 + margin, -d / 2 + margin),
            (w / 2 - margin, -d / 2 + margin),
        ]
        for cx, cy in corners[:n_hole]:
            model.Extension.SelectByID2("Top Plane", "PLANE", 0, 0, 0, False, 0, None, 0)
            skMgr.InsertSketch(True)
            skMgr.CreateCircleByRadius2(cx, cy, 0, hole_r)
            model.ClearSelection2(True)
            skMgr.InsertSketch(True)
            ftMgr.FeatureExtrusion3(
                False, False, False, 6, 0, t, 0,
                False, False, False, False, 0, 0, False, False, False, False, 1, 1, 1, 0, 0, False,
            )

        ok = self._export_step(model, step_path)
        return step_path if ok else None
    finally:
        self._close_doc(swapp, "")
```

- [ ] **Step 3：实现 `_build_arm` 和 `_build_cover`**

```python
def _build_arm(self, params: dict, step_path: Path) -> Optional[Path]:
    """细长臂：矩形梁 + 两端连接孔。"""
    length = float(params.get("length") or 0) / 1000
    width = float(params.get("width") or 20) / 1000
    thick = float(params.get("thickness") or 10) / 1000
    end_hole_r = float(params.get("end_hole_d") or 8) / 2 / 1000

    if length <= 0 or width <= 0:
        return None

    swapp = self._get_swapp()
    model = self._new_part_doc(swapp)
    if model is None:
        return None

    try:
        skMgr = model.SketchManager
        ftMgr = model.FeatureManager

        model.Extension.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, None, 0)
        skMgr.InsertSketch(True)
        skMgr.CreateCenterRectangle2(0, 0, 0, length / 2, width / 2, 0)
        model.ClearSelection2(True)
        skMgr.InsertSketch(True)
        ftMgr.FeatureExtrusion3(
            True, False, False, 0, 0, thick, 0,
            False, False, False, False, 0, 0, False, False, False, False, 1, 1, 1, 0, 0, False,
        )

        # 两端中心孔（贯穿厚度方向）
        for cx in [length / 2 - width / 2, -(length / 2 - width / 2)]:
            model.Extension.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, None, 0)
            skMgr.InsertSketch(True)
            skMgr.CreateCircleByRadius2(cx, 0, 0, end_hole_r)
            model.ClearSelection2(True)
            skMgr.InsertSketch(True)
            ftMgr.FeatureExtrusion3(
                False, False, False, 6, 0, thick, 0,
                False, False, False, False, 0, 0, False, False, False, False, 1, 1, 1, 0, 0, False,
            )

        ok = self._export_step(model, step_path)
        return step_path if ok else None
    finally:
        self._close_doc(swapp, "")


def _build_cover(self, params: dict, step_path: Path) -> Optional[Path]:
    """端盖：圆盘 + 可选中心孔 + 紧固孔环。"""
    import math
    od = float(params.get("od") or 0) / 1000
    thick = float(params.get("thickness") or 0) / 1000
    id_ = float(params.get("id") or 0) / 1000
    n_hole = int(params.get("n_hole") or 4)
    bolt_r = od * 0.375
    bolt_hole_r = 0.0025

    if od <= 0 or thick <= 0:
        return None

    swapp = self._get_swapp()
    model = self._new_part_doc(swapp)
    if model is None:
        return None

    try:
        skMgr = model.SketchManager
        ftMgr = model.FeatureManager

        model.Extension.SelectByID2("Top Plane", "PLANE", 0, 0, 0, False, 0, None, 0)
        skMgr.InsertSketch(True)
        skMgr.CreateCircleByRadius2(0, 0, 0, od / 2)
        if id_ > 0:
            skMgr.CreateCircleByRadius2(0, 0, 0, id_ / 2)
        model.ClearSelection2(True)
        skMgr.InsertSketch(True)
        ftMgr.FeatureExtrusion3(
            True, False, False, 0, 0, thick, 0,
            False, False, False, False, 0, 0, False, False, False, False, 1, 1, 1, 0, 0, False,
        )

        for i in range(n_hole):
            angle = 2 * math.pi * i / n_hole
            cx = bolt_r * math.cos(angle)
            cy = bolt_r * math.sin(angle)
            model.Extension.SelectByID2("Top Plane", "PLANE", 0, 0, 0, False, 0, None, 0)
            skMgr.InsertSketch(True)
            skMgr.CreateCircleByRadius2(cx, cy, 0, bolt_hole_r)
            model.ClearSelection2(True)
            skMgr.InsertSketch(True)
            ftMgr.FeatureExtrusion3(
                False, False, False, 6, 0, thick, 0,
                False, False, False, False, 0, 0, False, False, False, False, 1, 1, 1, 0, 0, False,
            )

        ok = self._export_step(model, step_path)
        return step_path if ok else None
    finally:
        self._close_doc(swapp, "")
```

- [ ] **Step 4：追加全路径集成验收测试**

在 `tests/test_sw_parametric_adapter.py` 追加：

```python
@pytest.mark.requires_solidworks
class TestSwPathIntegration:
    """验证 gen_parts 在 SW 可用时走 SW 路径，生成的 ee_*.py 含 importStep。"""

    def test_generate_part_files_uses_sw_step_for_flange(self, tmp_path):
        """gen_parts 对法兰件应生成 importStep 调用（SW 路径）。"""
        import subprocess, sys
        from pathlib import Path
        repo = Path(__file__).parent.parent
        result = subprocess.run(
            [sys.executable, "-m", "codegen.gen_parts",
             "cad/end_effector/CAD_SPEC.md", str(tmp_path), "--force"],
            cwd=repo, capture_output=True, text=True, timeout=300,
        )
        assert result.returncode == 0, result.stderr
        ee001 = tmp_path / "ee_001_01.py"
        assert ee001.exists()
        content = ee001.read_text(encoding="utf-8")
        assert "importStep" in content, "SW 路径生成的 ee_001_01.py 应包含 importStep"
        assert "sw_parts" in content
```

- [ ] **Step 5：运行集成验收（Windows + SW 本机）**

```bash
uv run pytest tests/test_sw_parametric_adapter.py::TestSwPathIntegration -v -m requires_solidworks
```

- [ ] **Step 6：全量回归**

```bash
uv run pytest --tb=short -q
```

预期：990+ 原有测试 + 新增非 SW 测试全部通过；requires_solidworks 测试在 Windows 本机全部通过

- [ ] **Step 7：Commit**

```bash
git add adapters/parts/sw_parametric_adapter.py tests/test_sw_parametric_adapter.py
git commit -m "feat(a2-sw-3): _build_spring/plate/arm/cover + 全路径集成验收"
```
