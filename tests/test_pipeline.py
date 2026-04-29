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


class TestBuildBlenderEnv(unittest.TestCase):
    """A1-3：`_build_blender_env()` 构造 Blender subprocess 环境变量。

    契约（Track A §3.3）：
      - 父进程 env 完整继承（PATH 等不丢）
      - SW 装 + textures_dir 存在 → 注入 SW_TEXTURES_DIR
      - SW 未装 / textures_dir 空 / 磁盘上目录不存在 → 不注入
    """

    def test_returns_copy_of_parent_env(self):
        os.environ["__A1_3_SENTINEL__"] = "keep"
        try:
            env = cad_pipeline._build_blender_env()
            self.assertIn(
                "__A1_3_SENTINEL__", env, "父进程 env 必须继承，不可凭空新造"
            )
            self.assertEqual(env["__A1_3_SENTINEL__"], "keep")
        finally:
            os.environ.pop("__A1_3_SENTINEL__", None)

    @mock.patch("cad_pipeline.detect_solidworks")
    def test_injects_sw_textures_dir_when_available(self, mock_detect):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            mock_detect.return_value = SimpleNamespace(
                installed=True, textures_dir=td
            )
            env = cad_pipeline._build_blender_env()
            self.assertEqual(
                env.get("SW_TEXTURES_DIR"),
                td,
                "SW 装 + textures_dir 存在时必须注入 SW_TEXTURES_DIR",
            )

    @mock.patch("cad_pipeline.detect_solidworks")
    def test_no_injection_when_not_installed(self, mock_detect):
        mock_detect.return_value = SimpleNamespace(installed=False, textures_dir="")
        os.environ.pop("SW_TEXTURES_DIR", None)
        env = cad_pipeline._build_blender_env()
        self.assertNotIn(
            "SW_TEXTURES_DIR", env, "SW 未装时不得自作主张设 SW_TEXTURES_DIR"
        )

    @mock.patch("cad_pipeline.detect_solidworks")
    def test_no_injection_when_textures_dir_empty(self, mock_detect):
        mock_detect.return_value = SimpleNamespace(installed=True, textures_dir="")
        os.environ.pop("SW_TEXTURES_DIR", None)
        env = cad_pipeline._build_blender_env()
        self.assertNotIn("SW_TEXTURES_DIR", env)

    @mock.patch("cad_pipeline.detect_solidworks")
    def test_no_injection_when_textures_dir_missing_on_disk(self, mock_detect):
        # 注册表说有 textures_dir 但磁盘上真的不存在（用户卸载残留 / UNC 不可达）
        mock_detect.return_value = SimpleNamespace(
            installed=True, textures_dir=r"C:\definitely\missing\textures_path"
        )
        os.environ.pop("SW_TEXTURES_DIR", None)
        env = cad_pipeline._build_blender_env()
        self.assertNotIn(
            "SW_TEXTURES_DIR",
            env,
            "textures_dir 磁盘上不存在时不该注入，否则 Blender 侧 open 会炸",
        )


class TestCmdRenderInjectsEnv(unittest.TestCase):
    """A1-3 结构性：cmd_render 必须把 _build_blender_env() 结果透传给
    所有 _run_subprocess 调用，否则 A1-2 的贴图桥拿不到 SW_TEXTURES_DIR。"""

    def test_cmd_render_calls_build_blender_env(self):
        import inspect
        src = inspect.getsource(cad_pipeline.cmd_render)
        self.assertIn(
            "_build_blender_env", src,
            "cmd_render 必须调用 _build_blender_env() 构造子进程环境",
        )

    def test_cmd_render_passes_env_kwarg_to_run_subprocess(self):
        import inspect
        src = inspect.getsource(cad_pipeline.cmd_render)
        self.assertIn(
            "env=", src,
            "cmd_render 至少有一个 _run_subprocess 调用必须带 env= kwarg",
        )

    @mock.patch("cad_pipeline._build_blender_env")
    @mock.patch("cad_pipeline._run_subprocess")
    @mock.patch("cad_pipeline.get_subsystem_dir")
    @mock.patch("cad_pipeline.get_blender_path")
    def test_cmd_render_normalizes_relative_output_dir(
        self,
        mock_get_blender_path,
        mock_get_subsystem_dir,
        mock_run_subprocess,
        mock_build_blender_env,
    ):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            subsystem_dir = os.path.join(td, "end_effector")
            os.makedirs(subsystem_dir)
            open(os.path.join(subsystem_dir, "render_3d.py"), "w").close()
            with open(
                os.path.join(subsystem_dir, "render_config.json"),
                "w",
                encoding="utf-8",
            ) as f:
                json.dump({"camera": {"V1": {"type": "standard"}}}, f)

            cwd = os.getcwd()
            try:
                os.chdir(td)
                relative_output_dir = os.path.join("artifacts", "renders")
                expected_output_dir = os.path.abspath(relative_output_dir)

                def fake_run(cmd, label, dry_run=False, timeout=600, env=None):
                    output_idx = cmd.index("--output-dir")
                    actual_output_dir = cmd[output_idx + 1]
                    self.assertTrue(
                        os.path.isabs(actual_output_dir),
                        "Blender 子进程必须收到绝对 output-dir，避免 cwd 漂移",
                    )
                    self.assertEqual(
                        os.path.normcase(actual_output_dir),
                        os.path.normcase(expected_output_dir),
                    )
                    os.makedirs(actual_output_dir, exist_ok=True)
                    with open(
                        os.path.join(actual_output_dir, "V1_front_20260101_0000.png"),
                        "wb",
                    ) as png:
                        png.write(b"png")
                    return True, 0.1

                mock_get_blender_path.return_value = os.path.join(td, "blender.exe")
                mock_get_subsystem_dir.return_value = subsystem_dir
                mock_build_blender_env.return_value = {}
                mock_run_subprocess.side_effect = fake_run

                rc = cad_pipeline.cmd_render(
                    SimpleNamespace(
                        subsystem="end_effector",
                        view="V1",
                        timestamp=True,
                        output_dir=relative_output_dir,
                        dry_run=False,
                    )
                )

                self.assertEqual(rc, 0)
                manifest_path = os.path.join(
                    expected_output_dir, "render_manifest.json"
                )
                self.assertTrue(os.path.isfile(manifest_path))
                with open(manifest_path, encoding="utf-8") as f:
                    manifest = json.load(f)
                self.assertEqual(
                    os.path.normcase(manifest["render_dir"]),
                    os.path.normcase(expected_output_dir),
                )
            finally:
                os.chdir(cwd)


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
