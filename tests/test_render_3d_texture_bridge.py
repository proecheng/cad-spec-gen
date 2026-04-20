#!/usr/bin/env python3
"""A1-2 `create_pbr_material` 贴图桥的结构性 + headless smoke 测试。

分两层（都在本文件，但职责分离）：

1. **结构性断言**（默认跑，不需要 Blender）：
   用 AST 抽出 `create_pbr_material` 函数源码，字符串级断言它包含了
   base_color / normal / roughness / metallic 四个贴图分支的 bpy API 调用
   + `_resolve_texture_path` / `_detect_normal_convention` helper 的引用。
   价值：CI 无 Blender 也能 catch 重构时误删分支 / 改错 socket 名 /
   漏挂 helper 的 bug。

2. **Blender headless smoke**（`@pytest.mark.blender` + skipif 无 Blender）：
   真启动 Blender 子进程，`bpy.data.materials.new` 出材质 → 调
   `create_pbr_material` 挂 4 类贴图 → 断言节点树包含预期的
   ShaderNodeTexImage / ShaderNodeNormalMap / ShaderNodeMapping / TexCoord。
   价值：catches bpy API 漂移 / socket 名改动。

测试文件命名呼应 Track A spec §8.2。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent
_RENDER_3D = _REPO_ROOT / "src" / "cad_spec_gen" / "render_3d.py"


# ───────────── 结构性断言（CI 友好）──────────────────────────────────────────


def _get_function_source(func_name: str) -> str:
    """从 render_3d.py 抽一个顶层函数的源码文本（AST 精确边界）。"""
    src = _RENDER_3D.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            segment = ast.get_source_segment(src, node)
            if segment is None:
                pytest.fail(f"ast.get_source_segment 对 {func_name} 返 None")
            return segment
    pytest.fail(f"render_3d.py 里找不到顶层函数 {func_name}")


class TestCreatePbrMaterialStructural:
    """`create_pbr_material` 函数体结构性检查 —— 不启 Blender。"""

    def test_base_color_texture_branch_exists(self):
        src = _get_function_source("create_pbr_material")
        assert "base_color_texture" in src, (
            "create_pbr_material 必须处理 params['base_color_texture'] 分支"
        )
        assert "ShaderNodeTexImage" in src, (
            "base_color_texture 分支必须 nodes.new('ShaderNodeTexImage')"
        )

    def test_normal_texture_branch_exists(self):
        src = _get_function_source("create_pbr_material")
        assert "normal_texture" in src, (
            "create_pbr_material 必须处理 params['normal_texture'] 分支"
        )
        assert "ShaderNodeNormalMap" in src, (
            "normal_texture 分支必须用 ShaderNodeNormalMap 挂切线空间法线"
        )

    def test_roughness_texture_branch_exists(self):
        src = _get_function_source("create_pbr_material")
        assert "roughness_texture" in src, (
            "create_pbr_material 必须处理 params['roughness_texture'] 分支"
        )

    def test_metallic_texture_branch_exists(self):
        src = _get_function_source("create_pbr_material")
        assert "metallic_texture" in src, (
            "create_pbr_material 必须处理 params['metallic_texture'] 分支"
        )

    def test_non_color_colorspace_for_data_textures(self):
        # roughness / metallic / normal 都是"数据"而非"颜色"，必须标 Non-Color
        # 否则 Blender sRGB 解码会把线性 0-1 数据错算
        src = _get_function_source("create_pbr_material")
        assert "Non-Color" in src, (
            "data 类贴图（roughness/metallic/normal）必须指定 "
            "colorspace_settings.name = 'Non-Color'"
        )

    def test_tex_coord_and_mapping_nodes_present(self):
        # Track A §3.2：TexCoord → Mapping(Scale) → TexImage.Vector
        # 无 UV 回退时 Generated 坐标是唯一可用投影源
        src = _get_function_source("create_pbr_material")
        assert "ShaderNodeTexCoord" in src, (
            "必须有 ShaderNodeTexCoord 节点作为 UV fallback 坐标源"
        )
        assert "ShaderNodeMapping" in src, (
            "必须有 ShaderNodeMapping 节点做 Scale 缩放（物理尺度对齐）"
        )

    def test_box_projection_for_no_uv_fallback(self):
        # Track A §3.2：projection='BOX' + projection_blend=0.2 避免圆柱拉伸条纹
        src = _get_function_source("create_pbr_material")
        assert "BOX" in src, (
            "TexImage 必须设 projection='BOX' —— 无 UV 时 Generated 坐标的"
            "圆柱/倒角件不设 BOX 会出强拉伸条纹"
        )

    def test_uses_resolve_texture_path_helper(self):
        # A1-1 helper 必须被集成 —— 否则相对路径永远不通
        src = _get_function_source("create_pbr_material")
        assert "_resolve_texture_path" in src, (
            "必须调用 A1-1 的 _resolve_texture_path 查找贴图文件；"
            "直接 bpy.data.images.load(rel_path) 在相对路径下会失败"
        )

    def test_uses_detect_normal_convention_helper(self):
        # DX/GL 约定必须探测 —— 否则法线 Y 翻转时凹凸倒置
        src = _get_function_source("create_pbr_material")
        assert "_detect_normal_convention" in src, (
            "normal_texture 分支必须用 _detect_normal_convention 判断 DX/GL"
        )

    def test_texture_miss_does_not_break_material(self):
        # _resolve_texture_path 返 None 时必须 graceful 降级（不挂 TexImage）
        # 而不是抛异常整张材质崩
        src = _get_function_source("create_pbr_material")
        # 至少应出现 None 的条件分支守护
        assert " is None" in src or "is not None" in src or "if resolved" in src, (
            "resolve 失败时必须有 None guard 分支，防止 bpy.data.images.load(None) 炸"
        )


# ───────────── Blender headless smoke —— 留给下一 commit ──────────────────────
# 需要 (a) 在 Blender 子进程内生成真 1x1 PNG、(b) env 注入 CAD_SPEC_GEN_TEXTURE_DIR、
# (c) 节点图拓扑断言（ShaderNodeTexImage in graph）。独立 commit 做，避免把
# TDD 循环拖长 + 避免 smoke 在 miss 路径下误 PASS。
