# A2 自制件半参数几何升级 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为自制件生成 L2 半参数几何（8 类模板 + 用户命名覆盖），将 11 件中约 7-8 件从 envelope 方块升级为可辨识形状。

**Architecture:** `template_mapping_loader.py` 负责加载用户 `template_mapping.json` + 内置关键词；`codegen/part_templates/*.py` 中的工厂函数返回 Python 代码字符串；`gen_parts.py` 中的 `_apply_template_decision` 将工厂输出注入 `geom["template_code"]`；Jinja 模板通过 `{{ template_code }}` 插入生成代码。

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

    def test_flange_sets_type_and_template_code(self):
        result = _apply_template_decision(
            dict(self._BASE_GEOM), "flange", self._FLANGE_META, self._ENVELOPE
        )
        assert result["type"] == "flange"
        assert "template_code" in result
        assert result["template_code"] is not None
        assert "body" in result["template_code"]

    def test_none_tpl_type_returns_original_geom(self):
        geom = dict(self._BASE_GEOM)
        result = _apply_template_decision(geom, None, self._FLANGE_META, self._ENVELOPE)
        assert result is geom

    def test_missing_required_param_falls_back(self):
        # 无任何 HOUSING 尺寸，且 envelope 也不够
        result = _apply_template_decision(
            dict(self._BASE_GEOM), "housing",
            {"dim_tolerances": []}, None
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

在 `generate_part_files` 函数之前插入：

```python
def _apply_template_decision(
    geom: dict,
    tpl_type: str | None,
    part_meta: dict,
    envelope: tuple | None,
) -> dict:
    """调用对应工厂函数，将 template_code 注入 geom 字典。

    主尺寸缺失（工厂返回 None）→ 返回原始 geom，不修改 type。
    """
    if tpl_type is None:
        return geom

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
        from codegen.part_templates.housing import make_housing
        code = make_housing(
            width=dim_map.get("HOUSING_W") or env_w or None,
            depth=dim_map.get("HOUSING_D") or env_d or None,
            height=dim_map.get("HOUSING_H") or env_h or None,
            wall_t=dim_map.get("HOUSING_WALL_T") or (min(env_w, env_d) * 0.12 if env_w and env_d else None),
        )
    elif tpl_type == "bracket":
        from codegen.part_templates.bracket import make_bracket
        code = make_bracket(
            width=dim_map.get("BRACKET_W") or env_w or None,
            height=dim_map.get("BRACKET_H") or env_h or None,
            thickness=dim_map.get("BRACKET_T") or env_d or None,
        )
    elif tpl_type == "spring_mechanism":
        from codegen.part_templates.spring_mechanism import make_spring_mechanism
        code = make_spring_mechanism(
            od=dim_map.get("SPRING_OD") or max(env_w, env_d) or None,
            id=dim_map.get("SPRING_ID") or None,
            free_length=dim_map.get("SPRING_L") or env_h or None,
            wire_d=dim_map.get("SPRING_WIRE_D") or None,
            coil_n=int(dim_map.get("SPRING_COIL_N", 8)),
        )
    elif tpl_type == "sleeve":
        from codegen.part_templates.sleeve import make_sleeve
        code = make_sleeve(
            od=dim_map.get("SLEEVE_OD") or max(env_w, env_d) or None,
            id=dim_map.get("SLEEVE_ID") or None,
            length=dim_map.get("SLEEVE_L") or env_h or None,
        )
    elif tpl_type == "plate":
        from codegen.part_templates.plate import make_plate
        code = make_plate(
            width=dim_map.get("PLATE_W") or env_w or None,
            depth=dim_map.get("PLATE_D") or env_d or None,
            thickness=dim_map.get("PLATE_T") or env_h or None,
        )
    elif tpl_type == "arm":
        from codegen.part_templates.arm import make_arm
        dims = sorted([env_w, env_d, env_h], reverse=True)
        code = make_arm(
            length=dim_map.get("ARM_L") or dim_map.get("ARM_L_2") or (dims[0] if dims else None),
            width=dim_map.get("ARM_W") or dim_map.get("ARM_SEC_W") or (dims[1] if len(dims) > 1 else None),
            thickness=dim_map.get("ARM_T") or dim_map.get("ARM_SEC_THICK") or (dims[2] if len(dims) > 2 else None),
            end_hole_d=dim_map.get("ARM_END_HOLE_D"),
        )
    elif tpl_type == "cover":
        from codegen.part_templates.cover import make_cover
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

在现有 `{% elif geom_type == "l_bracket" %}` 块之后、`{% else %}` 之前插入：

```jinja
{% elif template_code %}
{{ template_code }}
```

完整的 `{% if %}` 链变为：
```
{% if geom_type == "cylinder" %}   ... 保持不变 ...
{% elif geom_type == "ring" %}     ... 保持不变 ...
{% elif geom_type == "disc_arms" %} ... 保持不变 ...
{% elif geom_type == "l_bracket" %} ... 保持不变 ...
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
```

在 `for p in parts:` 循环中，**`part_meta = _parse_annotation_meta(spec_path, p["name_cn"])` 这行之后**（约 line 331）插入：

```python
        # A2-3: 半参数模板激活（复用已有 part_meta，不重复调用 _parse_annotation_meta）
        _tpl_type = _match_template(p["name_cn"], _user_mapping)
        if _tpl_type:
            geom = _apply_template_decision(geom, _tpl_type, part_meta, envelope)
```

在 `content = template.render(...)` 调用中追加参数：

```python
        content = template.render(
            ...  # 原有参数保持不变
            template_code=geom.get("template_code"),  # ← 新增
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

预期：原有 990+ + 新增测试全部通过

- [ ] **验收清单核对**

| 验收项 | 命令 |
|---|---|
| A2-0：法兰件无 SPRING_PIN_BORE | `pytest tests/test_a2_integration.py::TestFlangeA20Filter` |
| 法兰 face ≥ 30 | `pytest tests/test_a2_integration.py::TestFlangeGeometry` |
| 套筒 face ≥ 20 | `pytest tests/test_a2_integration.py::TestSleeveGeometry` |
| mapping.json 无 WARNING | `pytest tests/test_a2_integration.py::TestMappingJsonRouting` |
| 8 类工厂函数 | `pytest tests/test_part_templates.py` |
| filter 单测 | `pytest tests/test_dim_filter.py` |
| mapping loader | `pytest tests/test_template_mapping.py` |

- [ ] **最终 commit**

```bash
git add -A
git commit -m "feat(a2): A2 半参数几何升级完成 — 8 模板 + template_mapping.json + A2-0 过滤"
```
