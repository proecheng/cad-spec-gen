"""scripts/sw_spike_diagnose.py 改造后契约：调 sw_probe.*，按顺序早退。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from adapters.solidworks.sw_probe import ProbeResult


def _fail_probe(layer: str) -> ProbeResult:
    return ProbeResult(
        layer=layer,
        ok=False,
        severity="fail",
        summary=f"{layer} fail",
        data={},
        error="mocked",
    )


def _ok_probe(layer: str) -> ProbeResult:
    return ProbeResult(
        layer=layer, ok=True, severity="ok", summary=f"{layer} ok", data={}
    )


@pytest.fixture
def reload_spike():
    """保证 scripts.sw_spike_diagnose 按当前实现重新加载。"""
    import importlib

    root = Path(__file__).resolve().parent.parent
    scripts_path = str(root / "scripts")
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    import sw_spike_diagnose

    importlib.reload(sw_spike_diagnose)
    return sw_spike_diagnose


class TestSpikeDelegatesToProbe:
    def test_pywin32_fail_returns_1(self, reload_spike, monkeypatch):
        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.probe_pywin32", lambda: _fail_probe("pywin32")
        )
        rc = reload_spike.main()
        assert rc == 1

    def test_detect_fail_returns_2(self, reload_spike, monkeypatch):
        from adapters.solidworks.sw_detect import SwInfo

        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.probe_pywin32", lambda: _ok_probe("pywin32")
        )
        # probe_detect 返回 tuple (ProbeResult, SwInfo)
        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.probe_detect",
            lambda: (_fail_probe("detect"), SwInfo(installed=False)),
        )
        rc = reload_spike.main()
        assert rc == 2

    def test_all_ok_returns_0(self, reload_spike, monkeypatch):
        from adapters.solidworks.sw_detect import SwInfo

        for fn in ("probe_pywin32", "probe_clsid", "probe_dispatch", "probe_loadaddin"):
            layer = fn.replace("probe_", "")
            monkeypatch.setattr(
                f"adapters.solidworks.sw_probe.{fn}",
                lambda layer=layer: _ok_probe(layer),
            )
        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.probe_detect",
            lambda: (_ok_probe("detect"), SwInfo(installed=True)),
        )
        rc = reload_spike.main()
        assert rc == 0

    def test_loadaddin_fail_does_not_early_exit(self, reload_spike, monkeypatch):
        """spike 脚本对 loadaddin 不早退（spec §4.8 sample code）。"""
        from adapters.solidworks.sw_detect import SwInfo

        for fn in ("probe_pywin32", "probe_clsid", "probe_dispatch"):
            layer = fn.replace("probe_", "")
            monkeypatch.setattr(
                f"adapters.solidworks.sw_probe.{fn}",
                lambda layer=layer: _ok_probe(layer),
            )
        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.probe_detect",
            lambda: (_ok_probe("detect"), SwInfo(installed=True)),
        )
        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.probe_loadaddin",
            lambda: _fail_probe("loadaddin"),
        )
        rc = reload_spike.main()
        assert rc == 0  # loadaddin fail 不影响退出码
