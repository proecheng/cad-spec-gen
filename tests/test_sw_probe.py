"""sw_probe 内核单元测试（不依赖真 SW）。"""

from __future__ import annotations

import dataclasses
import sys

import pytest

from adapters.solidworks.sw_probe import ProbeResult


class TestProbeResult:
    def test_minimal_fields(self):
        r = ProbeResult(layer="x", ok=True, severity="ok", summary="hello", data={})
        assert r.layer == "x"
        assert r.ok is True
        assert r.severity == "ok"
        assert r.summary == "hello"
        assert r.data == {}
        assert r.error is None
        assert r.hint is None

    def test_with_error_and_hint(self):
        r = ProbeResult(
            layer="y",
            ok=False,
            severity="fail",
            summary="bad",
            data={"k": 1},
            error="boom",
            hint="run pip install ...",
        )
        assert r.error == "boom"
        assert r.hint == "run pip install ..."

    def test_frozen_dataclass(self):
        r = ProbeResult(layer="x", ok=True, severity="ok", summary="", data={})
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.layer = "changed"  # frozen=True 应当禁止修改

    def test_severity_accepts_three_values(self):
        for sev in ("ok", "warn", "fail"):
            r = ProbeResult(layer="x", ok=True, severity=sev, summary="", data={})
            assert r.severity == sev


from adapters.solidworks.sw_probe import probe_environment  # noqa: E402


class TestProbeEnvironment:
    def test_ok_shape(self):
        r = probe_environment()
        assert r.layer == "environment"
        assert r.severity == "ok"
        assert r.ok is True
        assert r.data["os"] == sys.platform
        assert r.data["python_version"].count(".") >= 2  # X.Y.Z
        assert r.data["python_bits"] in (32, 64)
        assert isinstance(r.data["pid"], int)
        assert r.data["pid"] > 0

    def test_summary_contains_python_version(self):
        r = probe_environment()
        # summary 至少提到 python 版本号前两位
        short_ver = ".".join(sys.version.split()[0].split(".")[:2])
        assert short_ver in r.summary


from adapters.solidworks.sw_probe import probe_pywin32  # noqa: E402


class TestProbePywin32:
    def test_available_path(self):
        """真装了 pywin32 时（Windows 开发机）走此路径；Linux CI 走下一条。"""
        try:
            import win32com.client  # noqa: F401

            has_pywin32 = True
        except ImportError:
            has_pywin32 = False

        r = probe_pywin32()
        assert r.layer == "pywin32"
        if has_pywin32:
            assert r.severity == "ok"
            assert r.ok is True
            assert r.data["available"] is True
            assert r.data["module_path"] is not None
            assert r.hint is None
        else:
            assert r.severity == "fail"
            assert r.ok is False
            assert r.data["available"] is False
            assert r.hint is not None
            assert "solidworks" in r.hint.lower()

    def test_fail_when_import_error(self, monkeypatch):
        """模拟 pywin32 未装：monkeypatch 让 import win32com.client 抛 ImportError。"""
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "win32com.client" or name.startswith("win32com"):
                raise ImportError("mocked: pywin32 not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        r = probe_pywin32()
        assert r.severity == "fail"
        assert r.ok is False
        assert r.data["available"] is False
        assert "mocked" in r.error or "pywin32" in r.error
        assert r.hint is not None
