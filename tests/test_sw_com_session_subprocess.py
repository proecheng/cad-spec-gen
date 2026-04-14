"""SwComSession._do_convert 的 subprocess 守卫行为测试（Part 2c P0 Task 2）。

全部 mock subprocess.run 以快速验证父进程侧逻辑；真实 subprocess 启动
测试在 Task 4 的 slow 标记集成用例里单独覆盖。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestDoConvertSubprocess:
    def _fake_run_success(self, tmp_out_content: bytes):
        """返回一个 side_effect：模拟 worker 写好 tmp 文件并 rc=0。"""

        def _run(cmd, **kwargs):
            tmp_path = cmd[-1]
            Path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
            Path(tmp_path).write_bytes(tmp_out_content)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        return _run

    def test_subprocess_success_validates_and_renames(self, tmp_path, monkeypatch):
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()
        step_out = tmp_path / "out.step"

        valid_step = b"ISO-10303-214\n" + b"X" * 2000
        monkeypatch.setattr(subprocess, "run", self._fake_run_success(valid_step))

        ok = s.convert_sldprt_to_step(
            str(tmp_path / "hex bolt.sldprt"),
            str(step_out),
        )
        assert ok is True
        assert step_out.exists()
        assert step_out.read_bytes().startswith(b"ISO-10303")
        assert not (tmp_path / "out.tmp.step").exists()

    def test_subprocess_nonzero_rc_returns_false(self, tmp_path, monkeypatch):
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                cmd, 2, stdout="", stderr="worker: OpenDoc6 errors=256"
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        step_out = tmp_path / "out.step"
        ok = s.convert_sldprt_to_step(str(tmp_path / "broken.sldprt"), str(step_out))
        assert ok is False
        assert not step_out.exists()
        assert s._consecutive_failures == 1

    def test_subprocess_timeout_returns_false(self, tmp_path, monkeypatch):
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()

        def fake_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=30)

        monkeypatch.setattr(subprocess, "run", fake_run)

        step_out = tmp_path / "out.step"
        ok = s.convert_sldprt_to_step(str(tmp_path / "hangs.sldprt"), str(step_out))
        assert ok is False
        assert not step_out.exists()
        assert s._consecutive_failures == 1

    def test_subprocess_success_but_invalid_step_returns_false(
        self, tmp_path, monkeypatch
    ):
        """worker rc=0 但写出的 tmp 文件过小/magic 错 → 父进程 validate 拒收。"""
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()

        monkeypatch.setattr(subprocess, "run", self._fake_run_success(b"tiny"))

        step_out = tmp_path / "out.step"
        ok = s.convert_sldprt_to_step(str(tmp_path / "fake.sldprt"), str(step_out))
        assert ok is False
        assert not step_out.exists()
        assert not (tmp_path / "out.tmp.step").exists()

    def test_subprocess_called_with_expected_cmd(self, tmp_path, monkeypatch):
        """验证命令行拼装：sys.executable + -m + 模块路径 + 两个位置参数；cwd 为项目根。"""
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()

        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(cmd[-1]).write_bytes(b"ISO-10303-214\n" + b"X" * 2000)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)

        sldprt = tmp_path / "hex bolt.sldprt"
        step_out = tmp_path / "out.step"
        s.convert_sldprt_to_step(str(sldprt), str(step_out))

        assert captured["cmd"][0] == sys.executable
        assert captured["cmd"][1] == "-m"
        assert captured["cmd"][2] == "adapters.solidworks.sw_convert_worker"
        assert captured["cmd"][3] == str(sldprt)
        assert captured["cmd"][4].endswith(".tmp.step")
        assert captured["kwargs"]["timeout"] > 0
        assert captured["kwargs"]["capture_output"] is True
        cwd = Path(captured["kwargs"]["cwd"])
        assert (cwd / "adapters" / "solidworks").is_dir()
