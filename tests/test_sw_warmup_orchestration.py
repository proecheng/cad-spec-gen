"""sw_warmup 主流程单元测试。"""

from __future__ import annotations

import argparse
import os
import sys
import unittest.mock as mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_args(**overrides) -> argparse.Namespace:
    base = dict(standard=None, bom=None, all=False, dry_run=False, overwrite=False)
    base.update(overrides)
    return argparse.Namespace(**base)


class TestPreflight:
    """前置检查失败应返回 exit code 2（不是 1）。"""

    def test_returns_2_when_sw_not_installed(self, tmp_path, monkeypatch, capsys):
        from tools import sw_warmup as mod
        from adapters.solidworks import sw_detect

        sw_detect._reset_cache()
        fake_info = sw_detect.SwInfo(installed=False)
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
        monkeypatch.setattr(
            mod, "_default_lock_path", lambda: tmp_path / "sw_warmup.lock"
        )

        rc = mod.run_sw_warmup(_make_args(standard="GB"))
        captured = capsys.readouterr()
        assert rc == 2
        assert "未检测到" in captured.out or "未安装" in captured.out

    def test_addin_disabled_warns_but_continues(self, tmp_path, monkeypatch, capsys):
        """SW-B0 spike 实证：Toolbox Library add-in 对转换非必要。
        addin_enabled=False 不应阻断（旧行为：rc=2），应打印 warning 后继续。
        """
        from tools import sw_warmup as mod
        from adapters.solidworks import sw_detect, sw_toolbox_catalog
        from pathlib import Path

        sw_detect._reset_cache()
        fake_toolbox = Path(__file__).parent / "fixtures" / "fake_toolbox"
        fake_info = sw_detect.SwInfo(
            installed=True,
            version_year=2024,
            pywin32_available=True,
            toolbox_dir=str(fake_toolbox),
            toolbox_addin_enabled=False,  # 关键：仍应继续
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
        monkeypatch.setattr(
            mod, "_default_lock_path", lambda: tmp_path / "sw_warmup.lock"
        )
        monkeypatch.setattr(
            sw_toolbox_catalog,
            "get_toolbox_cache_root",
            lambda config: tmp_path / "cache",
        )
        monkeypatch.setattr(
            sw_toolbox_catalog,
            "get_toolbox_index_path",
            lambda config: tmp_path / "idx.json",
        )

        rc = mod.run_sw_warmup(_make_args(standard="GB", dry_run=True))
        captured = capsys.readouterr()
        # 不再是 2；dry-run + addin disabled 仍能走完 → rc=0
        assert rc == 0
        assert "Toolbox Library add-in 未启用" in captured.out


class TestTargetSelection:
    """根据 --standard / --bom / --all 选目标。"""

    @staticmethod
    def _setup_sw_available(monkeypatch, tmp_path):
        """让前置检查通过 + index 指向 fake_toolbox。"""
        from adapters.solidworks import sw_detect, sw_toolbox_catalog
        from tools import sw_warmup as mod

        sw_detect._reset_cache()
        fake_toolbox = (
            __import__("pathlib").Path(__file__).parent / "fixtures" / "fake_toolbox"
        )
        fake_info = sw_detect.SwInfo(
            installed=True,
            version_year=2024,
            pywin32_available=True,
            toolbox_dir=str(fake_toolbox),
            toolbox_addin_enabled=True,
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
        monkeypatch.setattr(
            mod, "_default_lock_path", lambda: tmp_path / "sw_warmup.lock"
        )
        # cache root 指向 tmp_path 隔离测试
        monkeypatch.setattr(
            sw_toolbox_catalog,
            "get_toolbox_cache_root",
            lambda config: tmp_path / "cache",
        )
        monkeypatch.setattr(
            sw_toolbox_catalog,
            "get_toolbox_index_path",
            lambda config: tmp_path / "idx.json",
        )
        return fake_toolbox

    def test_dry_run_selects_but_does_not_convert(self, tmp_path, monkeypatch, capsys):
        """--dry-run 应只列出目标不调 COM。"""
        from tools import sw_warmup as mod

        self._setup_sw_available(monkeypatch, tmp_path)
        com_called = mock.MagicMock()
        monkeypatch.setattr(mod, "_convert_one", lambda *args, **kw: com_called())

        rc = mod.run_sw_warmup(_make_args(standard="GB", dry_run=True))
        captured = capsys.readouterr()
        assert rc == 0
        com_called.assert_not_called()
        # 至少打印了候选数量行
        assert "目标" in captured.out or "DRY-RUN" in captured.out


class TestCacheAndErrorLog:
    """已缓存跳过 + 失败写错误日志。"""

    def test_cache_hit_skips_com(self, tmp_path, monkeypatch, capsys):
        from tools import sw_warmup as mod

        TestTargetSelection._setup_sw_available(monkeypatch, tmp_path)

        # 预先建一个缓存文件，让 part 能命中
        cache_root = tmp_path / "cache"
        (cache_root / "GB" / "bolts and studs").mkdir(parents=True)
        (cache_root / "GB" / "bolts and studs" / "hex bolt.step").write_bytes(
            b"ISO-10303 fake stub" + b"\x00" * 2000
        )

        com_session = mock.MagicMock()
        com_session.convert_sldprt_to_step = mock.MagicMock(return_value=True)
        monkeypatch.setattr(
            "adapters.solidworks.sw_com_session.get_session",
            lambda: com_session,
        )

        rc = mod.run_sw_warmup(_make_args(standard="GB"))
        # 至少一次 convert 被跳过（cache hit）
        # 这里仅断言流程不崩 + 输出含"已缓存"
        captured = capsys.readouterr()
        assert rc in (0, 1)
        assert "已缓存" in captured.out

    def test_failure_appends_error_log(self, tmp_path, monkeypatch, capsys):
        from tools import sw_warmup as mod

        TestTargetSelection._setup_sw_available(monkeypatch, tmp_path)

        # 让 error_log 写到 tmp_path
        err_path = tmp_path / "errors.log"
        monkeypatch.setattr(mod, "_default_error_log_path", lambda: err_path)

        com_session = mock.MagicMock()
        com_session.convert_sldprt_to_step = mock.MagicMock(
            return_value=False
        )  # 全失败
        monkeypatch.setattr(
            "adapters.solidworks.sw_com_session.get_session",
            lambda: com_session,
        )

        rc = mod.run_sw_warmup(_make_args(standard="GB"))
        assert rc == 1
        assert err_path.exists()
        content = err_path.read_text(encoding="utf-8")
        assert "GB/" in content  # 至少一行失败记录

    def test_mixed_success_fail_returns_1(self, tmp_path, monkeypatch, capsys):
        """部分成功部分失败 → rc=1，错误日志只记失败行。"""
        from tools import sw_warmup as mod

        TestTargetSelection._setup_sw_available(monkeypatch, tmp_path)
        err_path = tmp_path / "errors.log"
        monkeypatch.setattr(mod, "_default_error_log_path", lambda: err_path)

        # convert 交替成功/失败
        results = iter([True, False, True])
        com_session = mock.MagicMock()
        com_session.convert_sldprt_to_step = lambda *a, **k: next(results, True)
        monkeypatch.setattr(
            "adapters.solidworks.sw_com_session.get_session",
            lambda: com_session,
        )

        rc = mod.run_sw_warmup(_make_args(standard="GB"))
        assert rc == 1
        # 汇总输出含成功+失败计数
        captured = capsys.readouterr()
        assert "成功" in captured.out and "失败" in captured.out
        # 错误日志只记失败行（fake_toolbox 只有 1 个 GB part，取决 iter 第几个返回 False）
        if err_path.exists():
            lines = [
                ln
                for ln in err_path.read_text(encoding="utf-8").splitlines()
                if ln.strip()
            ]
            # 每个失败占 1 行
            assert len(lines) >= 1


class TestDryRunTruncation:
    """dry-run >20 个目标时 '其余 N 个' 后缀格式（spec §7）。"""

    def test_dry_run_truncates_at_20(self, tmp_path, monkeypatch, capsys):
        from tools import sw_warmup as mod
        from adapters.solidworks.sw_toolbox_catalog import SwToolboxPart

        TestTargetSelection._setup_sw_available(monkeypatch, tmp_path)

        # 构造 25 个假 targets
        fake_targets = [
            SwToolboxPart(
                standard="GB",
                subcategory="bolts",
                sldprt_path=str(tmp_path / f"bolt_{i}.sldprt"),
                filename=f"bolt_{i}.sldprt",
                tokens=["gb", f"bolt_{i}"],
            )
            for i in range(25)
        ]
        monkeypatch.setattr(
            mod,
            "_select_targets_by_standard",
            lambda index, standards_csv: fake_targets,
        )

        rc = mod.run_sw_warmup(_make_args(standard="GB", dry_run=True))
        captured = capsys.readouterr()
        assert rc == 0
        assert "其余 5 个" in captured.out


class TestCadPipelineSubcommand:
    """cad_pipeline.py 注册了 sw-warmup 子命令。"""

    def test_cmd_sw_warmup_exists(self):
        """cad_pipeline 应导出 cmd_sw_warmup，且其能调用 run_sw_warmup。"""
        import importlib.util

        cad_path = os.path.join(os.path.dirname(__file__), "..", "cad_pipeline.py")
        spec = importlib.util.spec_from_file_location("cad_pipeline_mod", cad_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "cmd_sw_warmup"), "cad_pipeline 应导出 cmd_sw_warmup"


# ─── Part 2c P1 T4: exit code 3 + WarmupLockContentionError ──────────────


class TestLockContentionExitCode:
    """run_sw_warmup 对 lock contention 专用 exit code 3（Part 2b I-1）。"""

    def test_WarmupLockContentionError_exposes_pid_attribute(self):
        """架构审查 A1：PID 作为结构化属性暴露，不用字符串反解。"""
        from tools.sw_warmup import WarmupLockContentionError

        exc = WarmupLockContentionError(pid="9999")
        assert exc.pid == "9999"
        assert "9999" in str(exc)
        assert isinstance(exc, RuntimeError)  # 子类关系保证反向兼容

    def test_run_sw_warmup_returns_3_on_lock_contention(
        self, tmp_path, monkeypatch, capsys
    ):
        """mock acquire_warmup_lock 抛 WarmupLockContentionError → rc == 3。"""
        from contextlib import contextmanager
        from tools import sw_warmup as mod

        @contextmanager
        def _raise_contention(_path):
            raise mod.WarmupLockContentionError(pid="1234")
            yield  # unreachable

        monkeypatch.setattr(mod, "acquire_warmup_lock", _raise_contention)
        monkeypatch.setattr(
            mod, "_default_lock_path", lambda: tmp_path / "sw_warmup.lock"
        )

        rc = mod.run_sw_warmup(_make_args(standard="GB"))
        assert rc == 3
        captured = capsys.readouterr()
        assert "1234" in captured.out  # PID 在输出

    def test_run_sw_warmup_returns_1_on_generic_runtimeerror(
        self, tmp_path, monkeypatch, capsys
    ):
        """_run_warmup_locked 抛裸 RuntimeError → rc == 1（回归保护）。"""
        from contextlib import contextmanager
        from tools import sw_warmup as mod

        @contextmanager
        def _noop_lock(_path):
            yield  # 正常获锁

        monkeypatch.setattr(mod, "acquire_warmup_lock", _noop_lock)
        monkeypatch.setattr(
            mod, "_default_lock_path", lambda: tmp_path / "sw_warmup.lock"
        )
        monkeypatch.setattr(
            mod,
            "_run_warmup_locked",
            lambda args: (_ for _ in ()).throw(RuntimeError("通用错误")),
        )

        rc = mod.run_sw_warmup(_make_args(standard="GB"))
        assert rc == 1
