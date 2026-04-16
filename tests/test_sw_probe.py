"""sw_probe 内核单元测试（不依赖真 SW）。"""

from __future__ import annotations

import dataclasses
import sys

import pytest

from adapters.solidworks.sw_probe import ProbeResult
from adapters.solidworks.sw_detect import SwInfo
from adapters.solidworks.sw_probe import probe_detect


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


class TestProbeDetect:
    def test_installed_happy_path(self, monkeypatch):
        """mock detect_solidworks 返回已装 SW 的 SwInfo。
        probe_detect 返回 tuple (ProbeResult, SwInfo)：让下游 probe_material_files /
        probe_toolbox_index_cache 复用 info 对象，避免重复 detect。"""
        fake = SwInfo(
            installed=True,
            version="30.1.0.0080",
            version_year=2024,
            install_dir=r"D:\SOLIDWORKS Corp\SOLIDWORKS",
            sldmat_paths=["a.sldmat", "b.sldmat"],
            textures_dir=r"D:\tex",
            p2m_dir=r"D:\p2m",
            toolbox_dir=r"C:\SOLIDWORKS Data\browser",
            com_available=True,
            pywin32_available=True,
            toolbox_addin_enabled=False,
        )
        reset_called = []

        def fake_reset():
            reset_called.append(1)

        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.sw_detect._reset_cache", fake_reset
        )
        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.sw_detect.detect_solidworks", lambda: fake
        )

        r, info = probe_detect()
        assert r.layer == "detect"
        assert r.severity == "ok"
        assert r.ok is True
        assert r.data["installed"] is True
        assert r.data["version_year"] == 2024
        assert r.data["toolbox_dir"] == r"C:\SOLIDWORKS Data\browser"
        assert r.data["toolbox_addin_enabled"] is False
        assert len(reset_called) == 1, "必须调 _reset_cache 保证读最新状态"
        assert info is fake
        assert info.sldmat_paths == ["a.sldmat", "b.sldmat"]

    def test_not_installed(self, monkeypatch):
        fake = SwInfo(installed=False)
        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.sw_detect._reset_cache", lambda: None
        )
        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.sw_detect.detect_solidworks", lambda: fake
        )

        r, info = probe_detect()
        assert r.severity == "fail"
        assert r.ok is False
        assert r.data["installed"] is False
        assert r.hint is not None
        assert info is fake

    def test_detect_raises_returns_empty_info(self, monkeypatch):
        """detect_solidworks 抛异常时 probe_detect 捕获；info 返回空 SwInfo 占位。"""
        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.sw_detect._reset_cache", lambda: None
        )

        def boom():
            raise RuntimeError("simulated registry boom")

        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.sw_detect.detect_solidworks", boom
        )

        r, info = probe_detect()
        assert r.severity == "fail"
        assert r.error is not None
        assert isinstance(info, SwInfo)
        assert info.installed is False


from adapters.solidworks.sw_probe import probe_clsid  # noqa: E402


class TestProbeClsid:
    @pytest.mark.skipif(sys.platform != "win32", reason="仅 Windows 注册表")
    def test_registered_when_sw_installed(self):
        """装了 SW 的 Windows 开发机应读到 CLSID；CI Linux 跳过。"""
        r = probe_clsid()
        assert r.layer == "clsid"
        # 装 SW 则 severity=ok，未装则 fail——两种都可接受
        assert r.severity in ("ok", "fail")
        if r.severity == "ok":
            assert r.data["registered"] is True
            assert r.data["clsid"].startswith("{")

    def test_non_windows_returns_warn(self, monkeypatch):
        """非 Windows 应返回 warn（not applicable）。"""
        monkeypatch.setattr("adapters.solidworks.sw_probe.sys.platform", "linux")
        r = probe_clsid()
        assert r.layer == "clsid"
        assert r.severity == "warn"
        assert "not applicable" in r.summary or "不适用" in r.summary
        assert r.data["registered"] is False

    @pytest.mark.skipif(sys.platform != "win32", reason="winreg 仅 Windows")
    def test_fail_when_progid_missing(self, monkeypatch):
        """mock winreg.OpenKey 抛 FileNotFoundError 模拟 progid 未注册。"""
        import winreg

        def fake_open(*args, **kwargs):
            raise FileNotFoundError("not registered")

        monkeypatch.setattr(winreg, "OpenKey", fake_open)
        r = probe_clsid()
        assert r.severity == "fail"
        assert r.data["registered"] is False
        assert r.hint is not None


from adapters.solidworks.sw_probe import probe_toolbox_index_cache  # noqa: E402


def _make_fake_index(fingerprint: str, counts: dict[str, dict[str, int]]) -> dict:
    """构造与 _make_index_envelope 同结构的 dict。

    counts: {"GB": {"bolts": 3, "nuts": 2}, "ISO": {"bolts": 1}}
    """
    from adapters.solidworks.sw_toolbox_catalog import SwToolboxPart

    standards = {}
    for std, subs in counts.items():
        std_dict = {}
        for sub, n in subs.items():
            std_dict[sub] = [
                SwToolboxPart(
                    standard=std,
                    subcategory=sub,
                    sldprt_path=f"C:\\{std}\\{sub}\\p{i}.sldprt",
                    filename=f"p{i}.sldprt",
                    tokens=[],
                )
                for i in range(n)
            ]
        standards[std] = std_dict
    return {"toolbox_fingerprint": fingerprint, "standards": standards}


class TestProbeToolboxIndexCache:
    def test_happy_path_not_stale(self, tmp_path, monkeypatch):
        idx = _make_fake_index("fp-abc", {"GB": {"bolts": 3}, "ISO": {"nuts": 2}})
        index_path = tmp_path / "sw_toolbox_index.json"
        index_path.write_text("{}", encoding="utf-8")
        info = SwInfo(installed=True, toolbox_dir=str(tmp_path / "tb"))
        (tmp_path / "tb").mkdir()

        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.sw_toolbox_catalog.get_toolbox_index_path",
            lambda cfg: index_path,
        )
        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.sw_toolbox_catalog.load_toolbox_index",
            lambda ip, td: idx,
        )
        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.sw_toolbox_catalog._compute_toolbox_fingerprint",
            lambda td: "fp-abc",  # 与 cached 一致 → 不 stale
        )

        r = probe_toolbox_index_cache({}, info)
        assert r.layer == "toolbox_index"
        assert r.severity == "ok"
        assert r.data["exists"] is True
        assert r.data["entry_count"] == 5  # 3 + 2
        assert r.data["toolbox_fingerprint_cached"] == "fp-abc"
        assert r.data["toolbox_fingerprint_current"] == "fp-abc"
        assert r.data["stale"] is False
        assert r.data["by_standard"] == {"GB": 3, "ISO": 2}

    def test_stale_warning(self, tmp_path, monkeypatch):
        idx = _make_fake_index("fp-old", {"GB": {"bolts": 1}})
        index_path = tmp_path / "sw_toolbox_index.json"
        index_path.write_text("{}", encoding="utf-8")
        info = SwInfo(installed=True, toolbox_dir=str(tmp_path / "tb"))
        (tmp_path / "tb").mkdir()

        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.sw_toolbox_catalog.get_toolbox_index_path",
            lambda cfg: index_path,
        )
        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.sw_toolbox_catalog.load_toolbox_index",
            lambda ip, td: idx,
        )
        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.sw_toolbox_catalog._compute_toolbox_fingerprint",
            lambda td: "fp-new",
        )

        r = probe_toolbox_index_cache({}, info)
        assert r.severity == "warn"
        assert r.data["stale"] is True
        assert r.hint is not None
        assert "sw-warmup" in r.hint or "刷新" in r.hint

    def test_index_missing(self, tmp_path, monkeypatch):
        info = SwInfo(installed=True, toolbox_dir=str(tmp_path / "tb"))
        (tmp_path / "tb").mkdir()
        missing_path = tmp_path / "nope.json"

        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.sw_toolbox_catalog.get_toolbox_index_path",
            lambda cfg: missing_path,
        )

        r = probe_toolbox_index_cache({}, info)
        assert r.severity == "warn"
        assert r.data["exists"] is False
        assert r.data["entry_count"] == 0
