"""sw-inspect 真 SW smoke 测试。

带 @pytest.mark.requires_solidworks，tests/conftest.py 的 pytest_collection_modifyitems
钩子会在非 Windows / 无 pywin32 / 无 SW 安装时自动 skip。

本组测试不依赖任何 mock，直接调 run_sw_inspect；结果反映真实开发机环境。
"""

from __future__ import annotations

import argparse
import io
import json
from contextlib import redirect_stdout

import pytest

from tools.sw_inspect import run_sw_inspect


@pytest.mark.requires_solidworks
class TestSwInspectRealSmoke:
    def test_fast_real_smoke(self):
        args = argparse.Namespace(deep=False, json=True)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = run_sw_inspect(args)
        doc = json.loads(buf.getvalue())
        assert rc in (0, 1), f"fast 模式应 0/1；实际 {rc}，doc={doc}"
        assert doc["mode"] == "fast"
        assert doc["layers"]["detect"]["data"]["installed"] is True
        assert doc["layers"]["detect"]["data"]["version_year"] >= 2020

    def test_deep_real_smoke(self):
        args = argparse.Namespace(deep=True, json=True)
        buf = io.StringIO()
        with redirect_stdout(buf):
            run_sw_inspect(args)
        doc = json.loads(buf.getvalue())
        assert doc["mode"] == "deep"
        # dispatch 可能 ok 或 warn（已附着）；不应 fail
        disp = doc["layers"]["dispatch"]
        assert disp["severity"] in ("ok", "warn"), f"dispatch={disp}"
        assert disp["data"]["elapsed_ms"] < 30_000, (
            f"Dispatch 耗时 {disp['data']['elapsed_ms']}ms 超 30s"
        )
