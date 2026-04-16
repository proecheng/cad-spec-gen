"""tools/sw_inspect.py CLI 契约测试。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
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


class TestJsonSchemaShape:
    def _assert_inspect_json_shape(self, doc: dict):
        """唯一的 JSON schema 源头断言（spec §6.3）。"""
        assert doc["version"] == "1"
        assert doc["mode"] in {"fast", "deep"}
        assert isinstance(doc["overall"]["exit_code"], int)
        assert isinstance(doc["overall"]["elapsed_ms"], int)
        assert doc["overall"]["severity"] in {"ok", "warn", "fail"}
        assert "warning_count" in doc["overall"]
        assert "fail_count" in doc["overall"]
        assert set(doc["layers"].keys()) >= {
            "environment",
            "pywin32",
            "detect",
            "clsid",
            "toolbox_index",
            "materials",
            "warmup",
        }
        if doc["mode"] == "deep":
            assert "dispatch" in doc["layers"]
            # loadaddin 可选（dispatch fail 时不存在）——不强制
        # generated_at 必须以 Z 结尾（UTC）
        assert doc["generated_at"].endswith("Z")
        for name, layer in doc["layers"].items():
            assert {"ok", "severity", "summary", "data"} <= layer.keys(), (
                f"layer {name} 缺字段：{layer.keys()}"
            )
            assert layer["severity"] in {"ok", "warn", "fail"}

    def test_fast_json_shape(self, monkeypatch, capsys):
        _patch_all_ok(monkeypatch)
        sw_inspect.run_sw_inspect(_fake_args(as_json=True))
        captured = capsys.readouterr().out
        doc = json.loads(captured)
        self._assert_inspect_json_shape(doc)
        assert doc["mode"] == "fast"
        assert "dispatch" not in doc["layers"]

    def test_deep_json_shape(self, monkeypatch, capsys):
        _patch_all_ok(monkeypatch)
        sw_inspect.run_sw_inspect(_fake_args(deep=True, as_json=True))
        doc = json.loads(capsys.readouterr().out)
        self._assert_inspect_json_shape(doc)
        assert doc["mode"] == "deep"
        assert "dispatch" in doc["layers"]
        assert "loadaddin" in doc["layers"]

    def test_deep_dispatch_fail_loadaddin_absent(self, monkeypatch, capsys):
        _patch_all_ok(monkeypatch)
        monkeypatch.setattr(
            "tools.sw_inspect.probe_dispatch",
            lambda timeout_sec=60: _fail_probe("dispatch"),
        )
        sw_inspect.run_sw_inspect(_fake_args(deep=True, as_json=True))
        doc = json.loads(capsys.readouterr().out)
        self._assert_inspect_json_shape(doc)
        assert "dispatch" in doc["layers"]
        assert "loadaddin" not in doc["layers"]

    def test_generated_at_is_utc(self, monkeypatch, capsys):
        _patch_all_ok(monkeypatch)
        sw_inspect.run_sw_inspect(_fake_args(as_json=True))
        doc = json.loads(capsys.readouterr().out)
        ts = doc["generated_at"]
        assert ts.endswith("Z")
        assert "T" in ts
        # 反解能成功
        from datetime import datetime

        datetime.fromisoformat(ts.replace("Z", "+00:00"))


class TestCadPipelineIntegration:
    def test_subparser_registered(self):
        """cad_pipeline.py 构建 parser 后，sw-inspect 应为已注册的子命令。"""
        import os
        import subprocess

        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        result = subprocess.run(
            [sys.executable, "cad_pipeline.py", "sw-inspect", "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=Path(__file__).parent.parent,
            env=env,
        )
        assert result.returncode == 0, f"stderr={result.stderr}"
        assert "--deep" in result.stdout
        assert "--json" in result.stdout
