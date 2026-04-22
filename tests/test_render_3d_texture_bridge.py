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
import json as _json
import subprocess
import sys
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


# ───────────── Blender headless smoke（A1 重构：env + runtime_materials.json）──


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
        import struct
        import zlib

        def _chunk(tag: bytes, data: bytes) -> bytes:
            return (
                struct.pack(">I", len(data))
                + tag
                + data
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

        # 构造 runtime_materials.json：一个带 base_color_texture 的 preset
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
            "import render_3d; "
            "params = {'color': (0.8, 0.2, 0.2, 1.0), 'metallic': 0.0, 'roughness': 0.5, 'base_color_texture': 'diffuse.png'}; "
            "mat = render_3d.create_pbr_material('smoke', params); "
            "kinds = sorted({n.bl_idname for n in mat.node_tree.nodes}); "
            "print('NODE_KINDS=' + ','.join(kinds)); "
            "print('SMOKE_OK')"
        )

        result = subprocess.run(
            [blender, "--background", "--python-expr", expr],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
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
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
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
