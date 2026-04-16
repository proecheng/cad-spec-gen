"""tools/sw_inspect.py CLI 契约测试。"""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock

from adapters.solidworks.sw_probe import ProbeResult
from tools import sw_inspect


def _fake_args(deep: bool = False, as_json: bool = False) -> argparse.Namespace:
    return argparse.Namespace(deep=deep, json=as_json)


def _ok_probe(layer: str) -> ProbeResult:
    return ProbeResult(
        layer=layer, ok=True, severity="ok", summary=f"{layer} ok", data={}
    )


def _warn_probe(layer: str) -> ProbeResult:
    return ProbeResult(
        layer=layer, ok=True, severity="warn", summary=f"{layer} warn", data={}
    )


def _fail_probe(layer: str) -> ProbeResult:
    return ProbeResult(
        layer=layer,
        ok=False,
        severity="fail",
        summary=f"{layer} fail",
        data={},
        error="boom",
    )


def _patch_all_ok(monkeypatch):
    """所有 probe 都返回 ok。"""
    monkeypatch.setattr(
        "tools.sw_inspect.probe_environment", lambda: _ok_probe("environment")
    )
    monkeypatch.setattr("tools.sw_inspect.probe_pywin32", lambda: _ok_probe("pywin32"))
    fake_info = MagicMock()
    fake_info.installed = True
    monkeypatch.setattr(
        "tools.sw_inspect.probe_detect", lambda: (_ok_probe("detect"), fake_info)
    )
    monkeypatch.setattr("tools.sw_inspect.probe_clsid", lambda: _ok_probe("clsid"))
    monkeypatch.setattr(
        "tools.sw_inspect.probe_toolbox_index_cache",
        lambda cfg, info: _ok_probe("toolbox_index"),
    )
    monkeypatch.setattr(
        "tools.sw_inspect.probe_material_files", lambda info: _ok_probe("materials")
    )
    monkeypatch.setattr(
        "tools.sw_inspect.probe_warmup_artifacts", lambda cfg: _ok_probe("warmup")
    )
    monkeypatch.setattr(
        "tools.sw_inspect.probe_dispatch", lambda timeout_sec=60: _ok_probe("dispatch")
    )
    monkeypatch.setattr(
        "tools.sw_inspect.probe_loadaddin", lambda: _ok_probe("loadaddin")
    )
    monkeypatch.setattr(
        "tools.sw_inspect.load_registry", lambda: {"solidworks_toolbox": {}}
    )


class TestRunSwInspect:
    def test_fast_all_ok_exit_0(self, monkeypatch, capsys):
        _patch_all_ok(monkeypatch)
        rc = sw_inspect.run_sw_inspect(_fake_args())
        assert rc == 0
        out = capsys.readouterr().out
        assert "Overall" in out
        assert "environment" in out

    def test_fast_warn_exit_1(self, monkeypatch, capsys):
        _patch_all_ok(monkeypatch)
        monkeypatch.setattr(
            "tools.sw_inspect.probe_warmup_artifacts", lambda cfg: _warn_probe("warmup")
        )
        rc = sw_inspect.run_sw_inspect(_fake_args())
        assert rc == 1

    def test_fast_fail_exit_2(self, monkeypatch):
        _patch_all_ok(monkeypatch)
        monkeypatch.setattr(
            "tools.sw_inspect.probe_pywin32", lambda: _fail_probe("pywin32")
        )
        rc = sw_inspect.run_sw_inspect(_fake_args())
        assert rc == 2

    def test_deep_dispatch_fail_exit_3(self, monkeypatch):
        _patch_all_ok(monkeypatch)
        monkeypatch.setattr(
            "tools.sw_inspect.probe_dispatch",
            lambda timeout_sec=60: _fail_probe("dispatch"),
        )
        rc = sw_inspect.run_sw_inspect(_fake_args(deep=True))
        assert rc == 3

    def test_deep_loadaddin_fail_exit_4(self, monkeypatch):
        _patch_all_ok(monkeypatch)
        monkeypatch.setattr(
            "tools.sw_inspect.probe_loadaddin", lambda: _fail_probe("loadaddin")
        )
        rc = sw_inspect.run_sw_inspect(_fake_args(deep=True))
        assert rc == 4

    def test_deep_dispatch_fail_skips_loadaddin(self, monkeypatch):
        """spec §5.3：dispatch fail 时 loadaddin 不执行、不出现在 layers。"""
        _patch_all_ok(monkeypatch)
        called = []
        monkeypatch.setattr(
            "tools.sw_inspect.probe_dispatch",
            lambda timeout_sec=60: _fail_probe("dispatch"),
        )
        monkeypatch.setattr(
            "tools.sw_inspect.probe_loadaddin",
            lambda: (called.append(1), _ok_probe("loadaddin"))[1],
        )
        sw_inspect.run_sw_inspect(_fake_args(deep=True))
        assert called == [], "probe_loadaddin 不应被调用"
