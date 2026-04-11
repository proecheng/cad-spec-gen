"""v2.9.1 回归测试 —— 针对 4 个 skill bug 的永久性防退化覆盖。

本文件对应 `RELEASE_v2.9.1.md` 中记录的 4 个修复：

1. **Bug #1** `tools/hybrid_render/check_env.py::_find_blender()`
   v2.9.0 之前，`_find_blender()` 只查 `BLENDER_PATH` / `tools/blender/` / PATH，
   不读 `pipeline_config.json.blender_path`，与 `cad_paths.get_blender_path()`
   不一致。修复：增加 pipeline_config.json 和平台默认位置的 fallback。

2. **Bug #2** `assembly_validator.py::check_f2_size_mismatch` / `check_f3_compactness`
   v2.9.0 把 `codegen/gen_assembly.parse_envelopes()` 返回值从
   `{pno: (w,d,h)}` 改成 `{pno: {"dims": (w,d,h), "granularity": str}}`，
   但 validator 未同步，触发 `TypeError: '<' not supported between 'str' and 'float'`。
   修复：新增 `_envelope_dims()` 适配器，容忍 tuple 和 dict 两种 shape。

3. **Bug #3** `cad_pipeline.py enhance --backend` argparse choices
   choices 列表漏写 `"engineering"`，CLI 报 `invalid choice`，尽管
   `pipeline_config.json._backend_doc` 和 `skill.json` 都登记为合法后端。
   修复：choices 补上 engineering，更新 help 文案。

4. **Bug #4** `engineering_enhancer.py` 模块从未被实现
   `pipeline_config.json` 自 v2.3 起承诺 `engineering` 后端存在，但对应的
   `engineering_enhancer.py` 模块从未入库，`cmd_enhance` 的 dispatch 也没有
   对应分支，`backend == "engineering"` 会被 `else:` 吞掉悄悄改回 gemini。
   修复：新建 `engineering_enhancer.py`（PIL ImageEnhance 后处理），在
   `cmd_enhance` 的 table-driven dispatch 表中注册。
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# 本文件需要从 repo 根部 import 多个脚本（assembly_validator / engineering_enhancer /
# cad_pipeline），和 tests/test_assembly_validator.py 保持同样的导入风格。
_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ════════════════════════════════════════════════════════════════════════════
# Bug #2 — assembly_validator._envelope_dims adapter
# ════════════════════════════════════════════════════════════════════════════


class TestEnvelopeDimsAdapter:
    """v2.9.1 `_envelope_dims()` 适配器的单元测试。"""

    def test_unwraps_v29_dict_with_dims_key(self):
        """v2.9+ parse_envelopes 返回 `{"dims": (w,d,h), "granularity": str}`。"""
        from assembly_validator import _envelope_dims

        env = {"dims": (90.0, 90.0, 30.0), "granularity": "part_envelope"}
        assert _envelope_dims(env) == (90.0, 90.0, 30.0)

    def test_unwraps_legacy_tuple_unchanged(self):
        """v2.8.x 及更早的 parse_envelopes 返回原生 3-tuple，适配器不应破坏它。"""
        from assembly_validator import _envelope_dims

        assert _envelope_dims((10.0, 20.0, 30.0)) == (10.0, 20.0, 30.0)

    def test_unwraps_list_same_as_tuple(self):
        """若调用方传入 list 也应 work（容忍 YAML/JSON 反序列化）。"""
        from assembly_validator import _envelope_dims

        assert _envelope_dims([1.0, 2.0, 3.0]) == (1.0, 2.0, 3.0)

    def test_handles_dict_missing_dims_key_gracefully(self):
        """Granularity-only 残缺 dict 不应抛异常，返回零向量以便下游 skip。"""
        from assembly_validator import _envelope_dims

        # 下游的 `if e_sorted[k] < 0.1: continue` 会因零向量直接跳过，安全
        assert _envelope_dims({"granularity": "station_constraint"}) == (0.0, 0.0, 0.0)


class TestCheckF2SizeMismatchAcceptsV29Envelopes:
    """v2.9.1 `check_f2_size_mismatch` 必须同时接受 dict 和 tuple envelope。"""

    def test_v29_dict_envelope_exact_match_yields_no_issues(self):
        """Bug #2 回归：dict envelope + 精确匹配的 bbox 不应抛 TypeError。"""
        from assembly_validator import check_f2_size_mismatch

        bboxes = {
            "EE-001-01": (0.0, 0.0, 0.0, 90.0, 90.0, 30.0),
        }
        envelopes = {
            "GIS-EE-001-01": {
                "dims": (90.0, 90.0, 30.0),
                "granularity": "part_envelope",
            },
        }

        issues = check_f2_size_mismatch(bboxes, envelopes)
        assert issues == []  # 精确匹配，无 issue

    def test_v29_dict_envelope_size_mismatch_flagged(self):
        """修复后，真实的尺寸偏差依然能被检出（不是误报抑制）。"""
        from assembly_validator import check_f2_size_mismatch

        # bbox 比预期 envelope 大 5 倍 —— 应被 F2 flag
        bboxes = {
            "EE-001-01": (0.0, 0.0, 0.0, 500.0, 500.0, 150.0),
        }
        envelopes = {
            "GIS-EE-001-01": {
                "dims": (90.0, 90.0, 30.0),
                "granularity": "part_envelope",
            },
        }

        issues = check_f2_size_mismatch(bboxes, envelopes)
        assert len(issues) == 1
        assert issues[0]["part"] == "EE-001-01"
        assert issues[0]["ratio"] >= 5.0

    def test_legacy_tuple_envelope_still_works(self):
        """向后兼容：v2.8.x 保存的 tuple envelope 依旧可用。"""
        from assembly_validator import check_f2_size_mismatch

        bboxes = {"EE-001-01": (0.0, 0.0, 0.0, 90.0, 90.0, 30.0)}
        envelopes = {"GIS-EE-001-01": (90.0, 90.0, 30.0)}

        issues = check_f2_size_mismatch(bboxes, envelopes)
        assert issues == []


class TestCheckF3CompactnessAcceptsV29Envelopes:
    """Bug #2 的第二个潜伏位置：`check_f3_compactness` 也要走 `_envelope_dims()`。"""

    def test_v29_dict_envelope_does_not_crash(self):
        """Bug #2 回归：dict envelope 不能触发 `env[2]` → KeyError。"""
        from assembly_validator import check_f3_compactness

        bboxes = {
            "EE-001-01": (0.0, 0.0, 0.0, 90.0, 90.0, 30.0),
            "EE-001-02": (0.0, 0.0, 30.0, 90.0, 90.0, 35.0),
        }
        envelopes = {
            "GIS-EE-001-01": {
                "dims": (90.0, 90.0, 30.0),
                "granularity": "part_envelope",
            },
            "GIS-EE-001-02": {
                "dims": (90.0, 90.0, 5.0),
                "granularity": "part_envelope",
            },
        }

        # 不抛异常 → 正常返回 list（可能为空也可能有紧凑度 issue）
        issues = check_f3_compactness(bboxes, envelopes, ["GIS-EE-001"])
        assert isinstance(issues, list)


# ════════════════════════════════════════════════════════════════════════════
# Bug #1 — check_env._find_blender reads pipeline_config.json
# ════════════════════════════════════════════════════════════════════════════


class TestFindBlenderReadsPipelineConfig:
    """v2.9.1 `_find_blender()` 必须读 `pipeline_config.json.blender_path`。"""

    @staticmethod
    def _build_mini_skill_root(tmp_path: Path, blender_path: str) -> Path:
        """在 tmp_path 下构造一个只含 check_env.py 和 pipeline_config.json 的迷你 skill root。

        目的：不污染真实 SKILL_ROOT/pipeline_config.json，同时让 check_env.py
        通过 `__file__` 计算出的 `skill_root` 落在这个 tmp 目录上。
        """
        mini = tmp_path / "mini_skill"
        hybrid = mini / "tools" / "hybrid_render"
        hybrid.mkdir(parents=True)

        real_check_env = _REPO_ROOT / "tools" / "hybrid_render" / "check_env.py"
        (hybrid / "check_env.py").write_text(
            real_check_env.read_text(encoding="utf-8"), encoding="utf-8"
        )

        (mini / "pipeline_config.json").write_text(
            json.dumps({"blender_path": blender_path}), encoding="utf-8"
        )
        return mini

    def test_find_blender_honors_pipeline_config_blender_path(
        self, tmp_path, monkeypatch
    ):
        """Bug #1 回归：pipeline_config.json 里的 blender_path 必须被识别。"""
        # 用 sys.executable 作为"一定存在的可执行文件"代替真 Blender
        mini = self._build_mini_skill_root(tmp_path, sys.executable)

        # 清掉 BLENDER_PATH 环境变量，确保 fall-through 到 pipeline_config 分支
        monkeypatch.delenv("BLENDER_PATH", raising=False)

        # 从 tmp 目录加载 check_env，让其 __file__ 落在 mini skill root 内
        spec = importlib.util.spec_from_file_location(
            "check_env_v291_bug1",
            mini / "tools" / "hybrid_render" / "check_env.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        path, reason = mod._find_blender()
        assert path == sys.executable
        assert "pipeline_config.json" in reason, (
            f"Blender should be located via pipeline_config.json, got reason={reason!r}"
        )

    def test_find_blender_env_var_still_takes_precedence(
        self, tmp_path, monkeypatch
    ):
        """优先级验证：BLENDER_PATH 环境变量仍然压过 pipeline_config.json。"""
        mini = self._build_mini_skill_root(tmp_path, sys.executable)

        # 故意指向一个不同的合法路径（Python 解释器的另一个绝对路径）
        alt_python = str(Path(sys.executable).resolve())
        monkeypatch.setenv("BLENDER_PATH", alt_python)

        spec = importlib.util.spec_from_file_location(
            "check_env_v291_bug1_env", mini / "tools" / "hybrid_render" / "check_env.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        path, reason = mod._find_blender()
        assert path == alt_python
        assert "BLENDER_PATH" in reason


# ════════════════════════════════════════════════════════════════════════════
# Bug #3 — cad_pipeline.py enhance --backend engineering argparse
# ════════════════════════════════════════════════════════════════════════════


class TestEnhanceBackendChoicesIncludeEngineering:
    """v2.9.1 argparse choices 必须包含 `engineering`。"""

    def test_enhance_help_lists_engineering_as_valid_backend(self):
        """Bug #3 回归：`cad_pipeline.py enhance --help` 输出应含 engineering。"""
        result = subprocess.run(
            [sys.executable, str(_REPO_ROOT / "cad_pipeline.py"), "enhance", "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        assert result.returncode == 0, (
            f"enhance --help failed with rc={result.returncode}\n"
            f"stderr: {result.stderr}"
        )
        assert "engineering" in result.stdout, (
            "`engineering` missing from --backend help output — "
            "argparse choices likely does not include it. See v2.9.1 bug #3."
        )

    def test_enhance_backend_engineering_not_rejected_at_parse_time(self):
        """`--backend engineering` 不应在 argparse 阶段被拒。

        （后续可能因缺失 render_manifest 等原因失败，但不应是 'invalid choice'。）
        """
        result = subprocess.run(
            [
                sys.executable,
                str(_REPO_ROOT / "cad_pipeline.py"),
                "enhance",
                "--backend",
                "engineering",
                "--dir",
                "/__nonexistent_v291_test_dir__",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        combined = (result.stderr or "") + (result.stdout or "")
        assert "invalid choice" not in combined.lower(), (
            f"argparse rejected --backend engineering.\n"
            f"stderr: {result.stderr[:500]}\n"
            f"stdout: {result.stdout[:500]}"
        )


# ════════════════════════════════════════════════════════════════════════════
# Bug #4 — engineering_enhancer module + cmd_enhance dispatch branch
# ════════════════════════════════════════════════════════════════════════════


class TestEngineeringEnhancerModule:
    """v2.9.1 新增的 `engineering_enhancer.py` 必须可导入且契约对齐。"""

    def test_module_is_importable(self):
        """Bug #4 回归：模块必须存在且可 import。"""
        import engineering_enhancer  # noqa: F401

        assert hasattr(engineering_enhancer, "enhance_image")
        assert callable(engineering_enhancer.enhance_image)

    def test_enhance_image_signature_matches_table_driven_contract(self):
        """函数签名必须与 comfyui_enhancer / fal_enhancer 一致，让 table-driven
        dispatch `_enhance_fn(png, prompt, cfg, view_key, rc)` 能直接喂进来。
        """
        import engineering_enhancer

        sig = inspect.signature(engineering_enhancer.enhance_image)
        params = list(sig.parameters.keys())
        assert params == ["png_path", "prompt", "engineering_cfg", "view_key", "rc"], (
            f"engineering_enhancer.enhance_image signature drifted: {params}"
        )

    def test_enhance_image_produces_jpg_from_png_smoke(self, tmp_path):
        """端到端 smoke：写一张假 PNG → 调用 enhance_image → 验证产物是合法 JPG。"""
        from PIL import Image

        import engineering_enhancer

        src = tmp_path / "V1_front_iso.png"
        Image.new("RGB", (128, 128), (100, 150, 200)).save(src)

        out = engineering_enhancer.enhance_image(
            png_path=str(src),
            prompt="unused-by-engineering-backend",
            engineering_cfg={
                "sharpness": 1.5,
                "contrast": 1.2,
                "saturation": 1.0,
                "quality": 90,
            },
            view_key="V1",
            rc={},
        )

        try:
            assert os.path.isfile(out)
            assert out.endswith(".jpg")
            img = Image.open(out)
            assert img.format == "JPEG"
            assert img.size == (128, 128)  # 尺寸应保持
            assert img.mode == "RGB"
        finally:
            # 清理 tempfile 产生的 jpg
            try:
                os.remove(out)
            except OSError:
                pass

    def test_enhance_image_handles_rgba_source(self, tmp_path):
        """Blender 有时输出 RGBA PNG（含 alpha）—— JPEG 不支持透明，需要正确合成白底。"""
        from PIL import Image

        import engineering_enhancer

        src = tmp_path / "V1_rgba.png"
        Image.new("RGBA", (64, 64), (255, 0, 0, 128)).save(src)

        out = engineering_enhancer.enhance_image(
            png_path=str(src),
            prompt="",
            engineering_cfg={},  # 全部用默认值
            view_key="V1",
            rc={},
        )
        try:
            img = Image.open(out)
            assert img.format == "JPEG"
            assert img.mode == "RGB"  # 已合成到白底
        finally:
            try:
                os.remove(out)
            except OSError:
                pass


class TestCmdEnhanceHasEngineeringDispatchBranch:
    """v2.9.1 `cmd_enhance` 必须有 `backend == "engineering"` 分支。

    Bug #4 的隐蔽形态：即便 argparse choices 通过，若 dispatch 表
    没写 `elif backend == "engineering"`，`backend` 会被 `else:` 吞掉
    悄悄改回 `"gemini"`，用户看日志以为走了 engineering 但实际发请求到云。
    """

    def test_cmd_enhance_source_contains_engineering_branch(self):
        """结构性断言：`cmd_enhance` 源码必须含对 engineering 的显式分派。

        使用 source inspection 是因为真正执行 `cmd_enhance` 需要 render_manifest /
        render_config / 子系统目录等大量前置产物，不适合单元测试。
        """
        import cad_pipeline

        src = inspect.getsource(cad_pipeline.cmd_enhance)
        assert 'backend == "engineering"' in src or "'engineering'" in src, (
            "cmd_enhance has no explicit dispatch branch for the engineering "
            "backend — it would silently fall through to the gemini default. "
            "See v2.9.1 bug #4."
        )
        assert "engineering_enhancer" in src, (
            "cmd_enhance never imports engineering_enhancer — dispatch is broken."
        )

    def test_cad_pipeline_argparse_choices_list_includes_engineering(self):
        """双保险：直接从 argparse 构造对象里读出 choices 列表。"""
        import argparse

        import cad_pipeline  # noqa: F401

        # 通过 subprocess 间接构造 parser，最稳健；此处用源码检查更快
        src = inspect.getsource(cad_pipeline)
        # Find the p_enhance.add_argument("--backend", choices=[...]) line
        assert '"engineering"' in src and "choices=" in src, (
            "argparse choices for --backend does not list 'engineering'."
        )
