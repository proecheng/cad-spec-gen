"""v2.9.0 `_get_bounding_sphere` 修复的结构性回归（v2.9.2 Tier 1）。

v2.9.0 commit `a7555ae`（`fix(render): AABB center instead of vertex
centroid for bounding sphere`）把 `_get_bounding_sphere()` 的中心点计算
从"顶点重心"（`sum(xs) / len(xs)`）改成"AABB 中心"（`(min(xs) + max(xs)) / 2`），
原因：模型一侧顶点密度高时，旧算法会把相机拉偏，导致框选不准。

直接单测 `_get_bounding_sphere()` 需要 mock `bpy.context.scene.objects` +
`mathutils.Vector` 等 Blender 运行时对象 —— 比源码级结构检查脆弱得多。
这里采取**源码字符串断言**：把函数体抽出来，断言必含 `min(xs)` / `max(xs)`
的 AABB pattern，且不含 `sum(xs)` 的 centroid pattern。

同时附带几个"模块健康"的廉价 sanity 检查：
- render_3d.py 文件存在
- 能被 `ast.parse()` 成功解析（捕捉笔误）
- 顶部仍 import bpy / mathutils（没被谁误删）
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
_RENDER_3D = _REPO_ROOT / "src" / "cad_spec_gen" / "render_3d.py"


def _extract_function_body(src: str, func_name: str) -> str:
    """从源码里把一个顶层函数的完整块抽出来。

    简单做法：从 `def func_name` 开始匹配，直到下一个顶层 `def ` /
    `class ` 或文件末尾。不处理嵌套函数，对本文件够用。
    """
    pattern = rf"def {func_name}\b.*?(?=\n(?:def |class |\Z))"
    match = re.search(pattern, src, re.DOTALL)
    assert match, f"在 render_3d.py 里找不到函数 {func_name}"
    return match.group(0)


def test_render_3d_file_exists():
    """廉价 sanity：render_3d.py 真的在预期位置。"""
    assert _RENDER_3D.exists(), (
        f"render_3d.py 不在 {_RENDER_3D}，是否被重命名或移动了？"
    )


def test_render_3d_parses_as_valid_python():
    """`ast.parse()` 能通过 —— 捕捉语法错误而不需要真启动 Blender。"""
    src = _RENDER_3D.read_text(encoding="utf-8")
    try:
        ast.parse(src)
    except SyntaxError as e:
        import pytest

        pytest.fail(f"render_3d.py 语法错误: {e}")


def test_render_3d_imports_bpy_and_mathutils():
    """render_3d.py 是 Blender 内跑的脚本 —— 必须 import bpy 和 mathutils。

    这条 sanity 检查防止有人重构时把 bpy import 误删（会让文件在 Blender
    内瞬间 ImportError 失败，但在标准 Python 环境下看不出来）。
    """
    src = _RENDER_3D.read_text(encoding="utf-8")
    assert "import bpy" in src, "render_3d.py 必须 `import bpy`"
    assert (
        "from mathutils import" in src or "import mathutils" in src
    ), "render_3d.py 必须从 mathutils 导入 Vector 等"


def test_get_bounding_sphere_uses_aabb_min_max_not_centroid():
    """v2.9.0 AABB 中心 fix 的硬核回归：函数体必须含 `min(xs)` / `max(xs)`。

    若有人把它改回 `sum(xs) / len(xs)`（顶点重心），本测试会 fail 并在
    错误信息里指向 v2.9.0 commit hash。
    """
    src = _RENDER_3D.read_text(encoding="utf-8")
    body = _extract_function_body(src, "_get_bounding_sphere")

    # 必含 AABB 模式
    assert "min(xs)" in body and "max(xs)" in body, (
        "_get_bounding_sphere 不再引用 min(xs) / max(xs)。v2.9.0 的 AABB "
        "中心 fix 可能被意外 revert 了。参考 commit a7555ae "
        "`fix(render): AABB center instead of vertex centroid`。"
    )
    assert "min(ys)" in body and "max(ys)" in body, (
        "_get_bounding_sphere 缺 min(ys)/max(ys) —— AABB 模式不完整"
    )
    assert "min(zs)" in body and "max(zs)" in body, (
        "_get_bounding_sphere 缺 min(zs)/max(zs) —— AABB 模式不完整"
    )

    # 不应含顶点重心模式
    assert "sum(xs)" not in body, (
        "_get_bounding_sphere 含 sum(xs) —— 回退到顶点重心算法。"
        "必须用 AABB min/max 中心（v2.9.0 a7555ae）。"
    )


def test_get_bounding_sphere_radius_is_half_diagonal():
    """半径应是"从 AABB 中心到 AABB 角点"的距离（半对角线），不是其他启发式。

    v2.9.0 代码：`radius = (Vector((max(xs), max(ys), max(zs))) - center).length`
    这是对 AABB 包围球的紧致上界。若被改成 `max(width, height, depth) / 2`
    之类，外接球不再能保证覆盖所有顶点，本检查会 fail。
    """
    src = _RENDER_3D.read_text(encoding="utf-8")
    body = _extract_function_body(src, "_get_bounding_sphere")

    # 半对角线的典型写法：Vector((max(xs), max(ys), max(zs))) - center
    assert "Vector((max(xs)" in body or "Vector((max(xs), max(ys), max(zs)))" in body, (
        "_get_bounding_sphere 不再用半对角线公式计算半径。"
        "参考 v2.9.0 的原始写法：\n"
        "    radius = (Vector((max(xs), max(ys), max(zs))) - center).length"
    )
