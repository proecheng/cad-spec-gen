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


def test_cmd_spec_proceed_infers_subsystem_from_design_doc(tmp_path, monkeypatch):
    """spec --design-doc 19-*.md --proceed should not require --subsystem."""
    import json

    project_root = tmp_path / "project"
    project_root.mkdir()
    design_doc = tmp_path / "19-demo.md"
    design_doc.write_text("# demo\n", encoding="utf-8")
    config_path = tmp_path / "gisbot.json"
    config_path.write_text(
        json.dumps(
            {
                "output_dir": "./output",
                "subsystems": {
                    "19": {
                        "name": "丝杠式升降平台",
                        "prefix": "SLP",
                        "cad_dir": "lifting_platform",
                        "aliases": ["升降平台"],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    spec_gen = tmp_path / "cad_spec_gen.py"
    spec_gen.write_text("# fake spec generator\n", encoding="utf-8")

    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(project_root))
    monkeypatch.setattr(cad_pipeline, "CAD_DIR", str(project_root / "cad"))
    monkeypatch.setattr(cad_pipeline, "CONFIG_PATH", str(config_path))
    monkeypatch.setattr(cad_pipeline, "SKILL_ROOT", str(tmp_path))
    monkeypatch.setattr(cad_pipeline, "get_subsystem_dir", lambda _name: None)

    calls = []

    def fake_run(_cmd, label, **_kwargs):
        calls.append(label)
        out_dir = project_root / "output" / "lifting_platform"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "DESIGN_REVIEW.json").write_text(
            json.dumps({"critical": 0, "warning": 0, "auto_fill": 0, "items": []}),
            encoding="utf-8",
        )
        (out_dir / "DESIGN_REVIEW.md").write_text("# review\n", encoding="utf-8")
        if label.startswith("spec-gen"):
            (out_dir / "CAD_SPEC.md").write_text("# spec\n", encoding="utf-8")
        return True, 0.1

    monkeypatch.setattr(cad_pipeline, "_run_subprocess", fake_run)

    args = SimpleNamespace(
        subsystem=None,
        design_doc=str(design_doc),
        force=True,
        force_spec=False,
        dry_run=False,
        review_only=False,
        auto_fill=False,
        proceed=True,
        supplements=None,
        out_dir=None,
    )

    assert cad_pipeline.cmd_spec(args) == 0
    assert args.subsystem == "lifting_platform"
    assert len(calls) == 2
    assert (project_root / "cad" / "lifting_platform" / "CAD_SPEC.md").is_file()


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
                    from PIL import Image, ImageDraw

                    image = Image.new("RGB", (256, 256), (245, 245, 245))
                    draw = ImageDraw.Draw(image)
                    draw.rectangle((64, 64, 192, 192), fill=(40, 90, 150))
                    image.save(os.path.join(actual_output_dir, "V1_front_20260101_0000.png"))
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


class TestRenderConfigFromBom(unittest.TestCase):
    def _write_slp_spec(self, root):
        spec = os.path.join(root, "CAD_SPEC.md")
        with open(spec, "w", encoding="utf-8") as f:
            f.write(
                "# CAD Spec — 丝杠式升降平台 (SLP)\n\n"
                "## 5. BOM树\n\n"
                "| 料号 | 名称 | 材质/型号 | 数量 | 自制/外购 | 单价 |\n"
                "| --- | --- | --- | --- | --- | --- |\n"
                "| **UNKNOWN** | **未分组** | — | 1 | 总成 | — |\n"
                "| SLP-100 | 上固定板 | 6061铝 | 1 | 自制 | — |\n"
            )
        return spec

    def test_gen_render_config_creates_missing_config_from_spec_identity(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            sub_dir = os.path.join(td, "lifting_platform")
            os.makedirs(sub_dir)
            spec = self._write_slp_spec(sub_dir)

            cad_pipeline._gen_render_config_from_bom(sub_dir, spec)

            rc_path = os.path.join(sub_dir, "render_config.json")
            self.assertTrue(os.path.isfile(rc_path))
            with open(rc_path, encoding="utf-8") as f:
                rc = json.load(f)
            self.assertEqual(rc["subsystem"]["name"], "lifting_platform")
            self.assertEqual(rc["subsystem"]["name_cn"], "丝杠式升降平台")
            self.assertEqual(rc["subsystem"]["part_prefix"], "SLP")
            self.assertEqual(rc["subsystem"]["glb_file"], "SLP-000_assembly.glb")
            rendered = json.dumps(rc, ensure_ascii=False)
            self.assertNotIn("GIS-EE", rendered)
            self.assertNotIn("末端执行机构", rendered)

    def test_gen_render_config_syncs_ordinary_bom_parts(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            sub_dir = os.path.join(td, "lifting_platform")
            os.makedirs(sub_dir)
            spec = self._write_slp_spec(sub_dir)

            cad_pipeline._gen_render_config_from_bom(sub_dir, spec)

            rc_path = os.path.join(sub_dir, "render_config.json")
            with open(rc_path, encoding="utf-8") as f:
                rc = json.load(f)

            components = {
                key: value
                for key, value in rc["components"].items()
                if isinstance(value, dict)
            }
            by_bom = {
                value.get("bom_id"): value
                for value in components.values()
                if value.get("bom_id")
            }
            self.assertIn("SLP-100", by_bom)
            self.assertNotIn("UNKNOWN", by_bom)

            comp = by_bom["SLP-100"]
            self.assertEqual(comp["name_cn"], "上固定板")
            self.assertIn("material", comp)
            self.assertIn(comp["material"], rc["materials"])
            self.assertEqual(
                rc["materials"][comp["material"]]["preset"],
                "brushed_aluminum",
            )

    def test_gen_render_config_uses_visual_and_surface_material_sources(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            sub_dir = os.path.join(td, "lifting_platform")
            os.makedirs(sub_dir)
            spec = os.path.join(sub_dir, "CAD_SPEC.md")
            with open(spec, "w", encoding="utf-8") as f:
                f.write(
                    "# CAD Spec — 丝杠式升降平台 (SLP)\n\n"
                    "## 2. 公差与表面处理\n\n"
                    "### 2.3 表面处理\n\n"
                    "| 零件 | Ra(µm) | 处理方式 | material_type |\n"
                    "| --- | --- | --- | --- |\n"
                    "| 丝杠 SLP-P01 | Ra3.2 | 防锈处理 | 45# 钢 |\n\n"
                    "## 5. BOM树\n\n"
                    "| 料号 | 名称 | 材质/型号 | 数量 | 自制/外购 | 单价 |\n"
                    "| --- | --- | --- | --- | --- | --- |\n"
                    "| **UNKNOWN** | **未分组** | — | 1 | 总成 | — |\n"
                    "| SLP-100 | 上固定板 |  | 1 | 自制 | — |\n"
                    "| SLP-200 | 左支撑条 | SUS304 | 1 | 自制 | — |\n"
                    "| SLP-P01 | 丝杠 L350 |  | 2 | 自制 | — |\n"
                    "| SLP-F11 | PU 缓冲垫 20×20×3 |  | 4 | 外购 | — |\n\n"
                    "## 7. 视觉标识\n\n"
                    "| 零件 | 材质 | 表面颜色 | 唯一标签 | 外形尺寸 | 方向约束 |\n"
                    "| --- | --- | --- | --- | --- | --- |\n"
                    "| 上固定板 SLP-100 | 6061-T6 铝 | 黑色阳极氧化 | SLP-100 | 200×160×8 mm | +Z |\n"
                    "| 左支撑条 SLP-200 | 6061-T6 铝 | 黑色阳极氧化 | SLP-200 | 40×260×15 mm | +X |\n"
                    "| PU 缓冲垫 SLP-F11 | PU | 黑色 | SLP-F11 | 20×20×3 mm | — |\n"
                )

            cad_pipeline._gen_render_config_from_bom(sub_dir, spec)

            with open(os.path.join(sub_dir, "render_config.json"), encoding="utf-8") as f:
                rc = json.load(f)

            by_bom = {
                comp["bom_id"]: comp
                for comp in rc["components"].values()
                if isinstance(comp, dict) and comp.get("bom_id")
            }

            def preset_for(part_no):
                comp = by_bom[part_no]
                return rc["materials"][comp["material"]]["preset"]

            self.assertEqual(preset_for("SLP-100"), "black_anodized")
            self.assertEqual(preset_for("SLP-200"), "stainless_304")
            self.assertEqual(preset_for("SLP-P01"), "dark_steel")
            self.assertEqual(preset_for("SLP-F11"), "black_rubber")

    def test_gen_render_config_repairs_stale_reference_identity(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            sub_dir = os.path.join(td, "lifting_platform")
            os.makedirs(sub_dir)
            spec = self._write_slp_spec(sub_dir)
            rc_path = os.path.join(sub_dir, "render_config.json")
            with open(rc_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "version": 1,
                        "subsystem": {
                            "name": "end_effector",
                            "name_cn": "末端执行机构",
                            "part_prefix": "GIS-EE",
                            "glb_file": "EE-000_assembly.glb",
                        },
                        "coordinate_system": "GIS shell coordinate notes",
                        "components": {
                            "ee_001": {
                                "name_cn": "末端执行机构法兰",
                                "bom_id": "GIS-EE-001",
                                "material": "ee_001",
                            }
                        },
                        "camera": {"V1": {"type": "standard"}},
                    },
                    f,
                )

            cad_pipeline._gen_render_config_from_bom(sub_dir, spec)

            with open(rc_path, encoding="utf-8") as f:
                rc = json.load(f)
            self.assertEqual(rc["subsystem"]["name"], "lifting_platform")
            self.assertEqual(rc["subsystem"]["name_cn"], "丝杠式升降平台")
            self.assertEqual(rc["subsystem"]["part_prefix"], "SLP")
            self.assertEqual(rc["subsystem"]["glb_file"], "SLP-000_assembly.glb")
            rendered = json.dumps(rc, ensure_ascii=False)
            self.assertNotIn("GIS-EE", rendered)
            self.assertNotIn("末端执行机构", rendered)

    def test_gen_render_config_rebuilds_when_component_bom_prefix_drifts(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            sub_dir = os.path.join(td, "lifting_platform")
            os.makedirs(sub_dir)
            spec = self._write_slp_spec(sub_dir)
            rc_path = os.path.join(sub_dir, "render_config.json")
            with open(rc_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "version": 1,
                        "subsystem": {
                            "name": "lifting_platform",
                            "name_cn": "丝杠式升降平台",
                            "part_prefix": "SLP",
                            "glb_file": "SLP-000_assembly.glb",
                        },
                        "components": {
                            "ee_001": {
                                "name_cn": "末端执行机构法兰",
                                "bom_id": "GIS-EE-001",
                                "material": "ee_001",
                            }
                        },
                        "camera": {"V1": {"type": "standard"}},
                    },
                    f,
                )

            cad_pipeline._gen_render_config_from_bom(sub_dir, spec)

            with open(rc_path, encoding="utf-8") as f:
                rc = json.load(f)
            rendered = json.dumps(rc, ensure_ascii=False)
            self.assertNotIn("GIS-EE", rendered)
            self.assertNotIn("末端执行机构", rendered)


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


class TestRenderGlbMaterialCoverage(unittest.TestCase):
    def _write_glb_with_nodes(self, path, node_names):
        import json
        import struct

        gltf = {
            "asset": {"version": "2.0"},
            "nodes": [
                {"name": name, "mesh": idx}
                for idx, name in enumerate(node_names)
            ],
            "meshes": [{"primitives": []} for _ in node_names],
        }
        json_chunk = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
        json_chunk += b" " * ((4 - len(json_chunk) % 4) % 4)
        total_len = 12 + 8 + len(json_chunk)
        with open(path, "wb") as f:
            f.write(struct.pack("<4sII", b"glTF", 2, total_len))
            f.write(struct.pack("<II", len(json_chunk), 0x4E4F534A))
            f.write(json_chunk)

    def test_validate_render_glb_material_coverage_warns_for_unmatched_mesh(self):
        import json
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            rc_path = os.path.join(td, "render_config.json")
            glb_path = os.path.join(td, "assembly.glb")
            with open(rc_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "version": 1,
                        "materials": {
                            "part_100": {"preset": "black_anodized"},
                        },
                        "components": {
                            "part_100": {
                                "name_cn": "上固定板",
                                "bom_id": "SLP-100",
                                "material": "part_100",
                            },
                        },
                    },
                    f,
                )
            self._write_glb_with_nodes(glb_path, ["100", "UNMATCHED"])

            warnings = cad_pipeline._validate_render_glb_material_coverage(
                rc_path,
                glb_path,
            )

            rendered = "\n".join(warnings)
            self.assertIn("UNMATCHED", rendered)
            self.assertIn("default gray", rendered)
            self.assertNotIn("'100'", rendered)

    def test_validate_render_config_accepts_generic_bom_ids(self):
        import json
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            rc_path = os.path.join(td, "render_config.json")
            with open(rc_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "version": 1,
                        "materials": {
                            "part_100": {"preset": "black_anodized"},
                            "part_p01": {"preset": "dark_steel"},
                            "part_c02": {"preset": "stainless_304"},
                        },
                        "components": {
                            "part_100": {
                                "bom_id": "SLP-100",
                                "material": "part_100",
                            },
                            "part_p01": {
                                "bom_id": "SLP-P01",
                                "material": "part_p01",
                            },
                            "part_c02": {
                                "bom_id": "GIS-EE-001",
                                "material": "part_c02",
                            },
                        },
                        "labels": {},
                    },
                    f,
                )

            warnings = cad_pipeline._validate_render_config(rc_path)

            self.assertEqual([], warnings)


if __name__ == "__main__":
    unittest.main()
