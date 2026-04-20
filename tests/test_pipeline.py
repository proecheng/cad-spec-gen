#!/usr/bin/env python3
"""
cad_pipeline.py 的测试 — CLI 参数解析、子系统发现、_run_subprocess 契约。

运行: python -m pytest tests/ -v
"""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import cad_pipeline
from cad_paths import get_blender_path, get_subsystem_dir


class TestFindBlender(unittest.TestCase):
    def test_returns_string_or_none(self):
        result = get_blender_path()
        self.assertTrue(result is None or isinstance(result, str))

    def test_found_blender_is_file(self):
        result = get_blender_path()
        if result:
            self.assertTrue(os.path.isfile(result))


class TestFindSubsystem(unittest.TestCase):
    def test_end_effector_found(self):
        result = get_subsystem_dir("end_effector")
        self.assertIsNotNone(result)
        self.assertTrue(os.path.isdir(result))

    def test_nonexistent_returns_none(self):
        result = get_subsystem_dir("nonexistent_subsystem_xyz")
        self.assertIsNone(result)

    def test_fuzzy_match(self):
        result = get_subsystem_dir("end_eff")
        # Should find end_effector via fuzzy match
        if result:
            self.assertIn("end_effector", result)


class TestCLIParsing(unittest.TestCase):
    def test_no_args_exits_zero(self):
        # main() with no command should return 0 (print help)
        sys.argv = ["cad_pipeline.py"]
        rc = cad_pipeline.main()
        self.assertEqual(rc, 0)


class TestRunSubprocessEnvPassthrough(unittest.TestCase):
    """A1-0b: _run_subprocess 必须接受可选 env 参数并透传 subprocess.run。

    A1 SW 纹理桥靠在 cmd_render 注入 SW_TEXTURES_DIR 让 Blender 子进程读到
    材质目录；契约前提就是这里的透传。"""

    @mock.patch("cad_pipeline.subprocess.run")
    def test_explicit_env_none_kwarg_accepted(self, mock_run):
        # 新签名必须显式接受 env=None 关键字参数（不能只是 **kwargs 吃掉）
        # 且透传到 subprocess.run（env=None → 继承父进程 env，老行为不变）
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")

        ok, _ = cad_pipeline._run_subprocess(["echo", "hi"], "label", env=None)

        self.assertTrue(ok)
        mock_run.assert_called_once()
        self.assertIsNone(mock_run.call_args.kwargs.get("env"))

    @mock.patch("cad_pipeline.subprocess.run")
    def test_env_is_passed_to_subprocess_run(self, mock_run):
        # 新调用点传 env={"SW_TEXTURES_DIR": "..."} → 真的落到 subprocess.run
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        fake_env = {"SW_TEXTURES_DIR": r"C:\fake\textures", "PATH": "x"}

        ok, _ = cad_pipeline._run_subprocess(
            ["echo", "hi"], "label", env=fake_env
        )

        self.assertTrue(ok)
        self.assertEqual(mock_run.call_args.kwargs.get("env"), fake_env)


if __name__ == "__main__":
    unittest.main()
