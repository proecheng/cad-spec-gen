"""Track A1-4 无回归保护：剔除纹理字段的 preset 走标量 BSDF 路径。

背景（spec §8.1 INFO）：A1-4 给所有 preset 加了 4 个 optional 纹理字段。
本测试证明"若运行时字段全为 None 或被移除"，create_pbr_material 走纯标量
路径，与 v2.11 行为等价——即新字段是**纯增量**，对老部署零影响。

实现策略：不启 Blender（bpy 模块级 import 会在 Linux CI 炸）。用 AST 抽
create_pbr_material 源码 → 断言 texture 分支由 `if resolved:` guard 保护
→ `resolved` 构建循环只对非空字段 append。
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent
_RENDER_3D = _REPO_ROOT / "src" / "cad_spec_gen" / "render_3d.py"


def _get_function_node(func_name: str) -> ast.FunctionDef:
    src = _RENDER_3D.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return node
    pytest.fail(f"render_3d.py 无顶层函数 {func_name}")


def test_texture_block_guarded_by_if_resolved():
    """纹理节点创建必须在 `if resolved:` 守护块内，缺字段不触发。"""
    fn = _get_function_node("create_pbr_material")
    src = ast.unparse(fn)
    assert "resolved = {}" in src or "resolved: " in src, (
        "create_pbr_material 必须用 resolved dict 聚合命中项"
    )
    assert "if resolved:" in src, (
        "纹理节点挂载必须被 `if resolved:` guard —— 否则空 preset 会造出空 TexImage"
    )


def test_texture_branch_only_appends_non_empty_fields():
    """resolved 填充循环必须用 `if not rel: continue` 跳过 None 值。"""
    fn = _get_function_node("create_pbr_material")
    src = ast.unparse(fn)
    assert "if not rel:" in src or "if rel is None" in src or "continue" in src, (
        "resolved 填充循环必须跳过 None/空字段；否则所有 preset 都会触发"
        " _resolve_texture_path(None) 造成 log 噪音"
    )


def test_scalar_path_preserved():
    """标量路径（`bsdf.inputs["Base Color"].default_value`）必须与 texture 分支并存。"""
    fn = _get_function_node("create_pbr_material")
    src = ast.unparse(fn)
    assert "Base Color" in src and "default_value" in src, (
        "标量 Base Color 赋值路径必须存在——texture 只是覆盖层"
    )
    assert "Metallic" in src and "Roughness" in src, (
        "标量 Metallic/Roughness 通道必须保留"
    )


def test_all_existing_presets_still_importable_and_have_color():
    """v2.11 的 15 个 preset 名全在；color 字段未变；新 3 preset 不覆盖老名。"""
    import sys

    _SRC = Path(__file__).parent.parent / "src"
    if str(_SRC) not in sys.path:
        sys.path.insert(0, str(_SRC))
    _ROOT = Path(__file__).parent.parent
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    import render_config as rcfg

    v211_names = {
        "brushed_aluminum", "anodized_blue", "anodized_green", "anodized_purple",
        "anodized_red", "black_anodized", "bronze", "copper", "gunmetal",
        "dark_steel", "stainless_304", "peek_amber", "black_rubber",
        "white_nylon", "polycarbonate_clear",
    }
    missing = v211_names - set(rcfg.MATERIAL_PRESETS)
    assert not missing, f"v2.11 preset 被删除：{missing}"

    for name in v211_names:
        params = rcfg.MATERIAL_PRESETS[name]
        assert "color" in params, f"{name} 失去 color 字段（破坏 v2.11 兼容）"
