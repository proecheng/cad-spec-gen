#!/usr/bin/env python3
"""A1-1 纹理路径解析 + 法线约定探测的行为测试。

render_3d.py 顶层 `import bpy` + import-time argparse 让常规 import 跑不起来
（非 Blender 环境立即炸）。本文件沿用 test_render_3d_structure.py 的 AST 抽函数
模式扩展：取函数源码 → `exec` 到干净 namespace 注入必要 stdlib → 直接调用。

被测函数是纯 Python（os/pathlib/logging），隔离可行；一旦引 bpy/mathutils，
测试需要改 requires_windows marker。
"""

from __future__ import annotations

import ast
import os
import tempfile
import unittest
from pathlib import Path


_REPO_ROOT = Path(__file__).parent.parent
_RENDER_3D = _REPO_ROOT / "src" / "cad_spec_gen" / "render_3d.py"


def _load_function(func_name: str):
    """从 render_3d.py 抽一个顶层函数并 exec 到干净 namespace 返回可调用对象。

    用 `ast` 精确定位函数 AST 节点 → `ast.get_source_segment` 取源码片段。
    相比 regex 贪婪扫至下一个 `def`/`class`，AST 路径能正确终止在 decorator
    前的顶层函数边界，避免把 CLI 模块级代码（含 `sys.argv` 等）误吞进 exec
    namespace 触发 NameError。

    约束：被抽函数必须只依赖 os / pathlib.Path / logging / typing（本 namespace
    预注入）。引用 bpy / mathutils 的函数在这里不可测，交给 smoke 测试。
    """
    src = _RENDER_3D.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            segment = ast.get_source_segment(src, node)
            if segment is None:
                raise AssertionError(
                    f"ast.get_source_segment 对 {func_name} 返 None — Python 版本过旧？"
                )
            import logging
            from typing import Optional, Literal  # noqa: F401 — 注入 namespace 备用
            ns: dict = {
                "__builtins__": __builtins__,
                "os": os,
                "Path": Path,
                "logging": logging,
                "Optional": Optional,
                "Literal": Literal,
            }
            exec(segment, ns)
            return ns[func_name]
    raise AssertionError(
        f"render_3d.py 里找不到顶层函数 {func_name}；A1-1 尚未实现？"
    )


class TestDetectNormalConvention(unittest.TestCase):
    """A1-1 法线贴图约定探测 — DirectX (Y-) vs OpenGL (Y+)。"""

    def setUp(self):
        self.fn = _load_function("_detect_normal_convention")

    def test_default_is_dx_for_generic_name(self):
        # 默认 DX（SW 导出约定），无特殊后缀时不瞎猜成 GL
        self.assertEqual(self.fn("brass_normal.jpg"), "dx")

    def test_gl_suffix_detected(self):
        # 明确 GL 标记 → 返 gl
        self.assertEqual(self.fn("brass_normal_gl.jpg"), "gl")
        self.assertEqual(self.fn("brass_normal_opengl.png"), "gl")

    def test_dx_suffix_detected(self):
        # 明确 DX 标记 → 返 dx
        self.assertEqual(self.fn("brass_normal_dx.jpg"), "dx")
        self.assertEqual(self.fn("brass_normal_directx.png"), "dx")

    def test_case_insensitive(self):
        # 大小写不应影响判断（SW 纹理名常见大小写混用）
        self.assertEqual(self.fn("Brass_Normal_GL.JPG"), "gl")
        self.assertEqual(self.fn("Brass_Normal_DX.JPG"), "dx")


class TestResolveTexturePath(unittest.TestCase):
    """A1-1 纹理路径解析 — 4 级查找 + miss fallback。

    查找顺序（spec §3.3）：
      1. 绝对路径 → 存在即返回
      2. 相对路径 + CAD_SPEC_GEN_TEXTURE_DIR env → 拼接并检查存在
      3. 相对路径 + SW_TEXTURES_DIR env → 拼接并检查存在
      4. 以上全 miss → None（上层自行 warning 降级）
    """

    def setUp(self):
        self.fn = _load_function("_resolve_texture_path")
        # 测试隔离：清掉相关 env 变量，各 test 按需 setenv
        self._saved_env = {}
        for k in ("CAD_SPEC_GEN_TEXTURE_DIR", "SW_TEXTURES_DIR"):
            self._saved_env[k] = os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_absolute_path_existing_returns_path(self):
        with tempfile.NamedTemporaryFile(
            prefix="tex_", suffix=".jpg", delete=False
        ) as f:
            f.write(b"fake")
            tmp = f.name
        try:
            result = self.fn(tmp)
            self.assertIsNotNone(result)
            self.assertEqual(str(result), tmp)
        finally:
            os.unlink(tmp)

    def test_absolute_path_missing_returns_none(self):
        result = self.fn(r"C:\definitely\does\not\exist\nowhere.jpg")
        self.assertIsNone(result)

    def test_empty_input_returns_none(self):
        self.assertIsNone(self.fn(""))
        self.assertIsNone(self.fn(None))

    def test_relative_via_cad_spec_gen_texture_dir(self):
        with tempfile.TemporaryDirectory() as td:
            rel = "metals/brass.jpg"
            full = Path(td) / rel
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_bytes(b"fake")
            os.environ["CAD_SPEC_GEN_TEXTURE_DIR"] = td
            result = self.fn(rel)
            self.assertIsNotNone(result)
            self.assertTrue(
                os.path.samefile(str(result), str(full)),
                f"expected to resolve to {full}, got {result}",
            )

    def test_relative_via_sw_textures_dir(self):
        with tempfile.TemporaryDirectory() as td:
            rel = "plastic/abs.jpg"
            full = Path(td) / rel
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_bytes(b"fake")
            os.environ["SW_TEXTURES_DIR"] = td
            result = self.fn(rel)
            self.assertIsNotNone(result)
            self.assertTrue(os.path.samefile(str(result), str(full)))

    def test_cad_spec_gen_takes_precedence_over_sw(self):
        # 两个 env 都 set 时 CAD_SPEC_GEN_TEXTURE_DIR 优先（用户自订覆盖 SW 默认）
        with tempfile.TemporaryDirectory() as td_user:
            with tempfile.TemporaryDirectory() as td_sw:
                rel = "shared.jpg"
                (Path(td_user) / rel).write_bytes(b"user")
                (Path(td_sw) / rel).write_bytes(b"sw")
                os.environ["CAD_SPEC_GEN_TEXTURE_DIR"] = td_user
                os.environ["SW_TEXTURES_DIR"] = td_sw
                result = self.fn(rel)
                self.assertIsNotNone(result)
                self.assertTrue(
                    os.path.samefile(str(result), str(Path(td_user) / rel))
                )

    def test_relative_all_miss_returns_none(self):
        # 两 env 都未 set，相对路径无处可找 → None
        result = self.fn("nonexistent/tex.jpg")
        self.assertIsNone(result)

    def test_env_set_but_file_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            os.environ["CAD_SPEC_GEN_TEXTURE_DIR"] = td
            result = self.fn("not_there.jpg")
            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
