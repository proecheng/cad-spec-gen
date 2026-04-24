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
        from adapters.solidworks.sw_com_session import (
            SwComSession,
            _PROJECT_ROOT,
            reset_session,
        )

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
        # cwd 必须严格等于 _PROJECT_ROOT（确保 `python -m` 能找到 worker 模块）
        assert Path(captured["kwargs"]["cwd"]) == _PROJECT_ROOT

    def test_diagnostics_on_success(self, tmp_path, monkeypatch):
        """成功路径 → stage=success, exit_code=0, stderr_tail 保留 worker warning。"""
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()

        def fake_run(cmd, **kwargs):
            Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(cmd[-1]).write_bytes(b"ISO-10303-214\n" + b"X" * 2000)
            return subprocess.CompletedProcess(
                cmd, 0, stdout="", stderr="worker: CloseDoc ignored: ..."
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        ok = s.convert_sldprt_to_step(
            str(tmp_path / "hex bolt.sldprt"),
            str(tmp_path / "out.step"),
        )
        assert ok is True
        diag = s.last_convert_diagnostics
        assert diag is not None
        assert diag["stage"] == "success"
        assert diag["exit_code"] == 0
        assert "CloseDoc" in diag["stderr_tail"]

    def test_diagnostics_on_subprocess_error(self, tmp_path, monkeypatch):
        """worker rc=3 → stage=subprocess_error, exit_code=3, stderr_tail 含错误。"""
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                cmd, 3, stdout="", stderr="worker: SaveAs3 saved=False errors=1"
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        ok = s.convert_sldprt_to_step(
            str(tmp_path / "broken.sldprt"),
            str(tmp_path / "out.step"),
        )
        assert ok is False
        diag = s.last_convert_diagnostics
        assert diag is not None
        assert diag["stage"] == "subprocess_error"
        assert diag["exit_code"] == 3
        assert "errors=1" in diag["stderr_tail"]

    def test_diagnostics_on_timeout(self, tmp_path, monkeypatch):
        """subprocess timeout → stage=timeout, exit_code=None, stderr_tail=''。"""
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()

        def fake_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=30)

        monkeypatch.setattr(subprocess, "run", fake_run)

        ok = s.convert_sldprt_to_step(
            str(tmp_path / "hangs.sldprt"),
            str(tmp_path / "out.step"),
        )
        assert ok is False
        diag = s.last_convert_diagnostics
        assert diag is not None
        assert diag["stage"] == "timeout"
        assert diag["exit_code"] is None
        assert diag["stderr_tail"] == ""

    def test_diagnostics_on_validation_failure(self, tmp_path, monkeypatch):
        """worker rc=0 但 tmp STEP 太小 → stage=validation_failure。"""
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()

        def fake_run(cmd, **kwargs):
            Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(cmd[-1]).write_bytes(b"tiny")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)

        ok = s.convert_sldprt_to_step(
            str(tmp_path / "fake.sldprt"),
            str(tmp_path / "out.step"),
        )
        assert ok is False
        diag = s.last_convert_diagnostics
        assert diag is not None
        assert diag["stage"] == "validation_failure"
        assert diag["exit_code"] == 0

    def test_diagnostics_on_circuit_breaker_open(self, tmp_path, monkeypatch):
        """熔断器已开 → stage=circuit_breaker_open, exit_code=None。"""
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()
        s._unhealthy = True  # 直接置位，模拟已熔断

        ok = s.convert_sldprt_to_step(
            str(tmp_path / "any.sldprt"),
            str(tmp_path / "out.step"),
        )
        assert ok is False
        diag = s.last_convert_diagnostics
        assert diag is not None
        assert diag["stage"] == "circuit_breaker_open"
        assert diag["exit_code"] is None
        assert diag["stderr_tail"] == ""

    def test_diagnostics_on_unexpected_exception(self, tmp_path, monkeypatch):
        """_do_convert 抛未预期异常 → stage=unexpected_exception, stderr_tail 含 repr。"""
        from adapters.solidworks import sw_com_session as scs
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()

        def fake_do_convert(self, sldprt_path, step_out, target_config=None):
            raise RuntimeError("simulated crash")

        monkeypatch.setattr(scs.SwComSession, "_do_convert", fake_do_convert)

        ok = s.convert_sldprt_to_step(
            str(tmp_path / "any.sldprt"),
            str(tmp_path / "out.step"),
        )
        assert ok is False
        diag = s.last_convert_diagnostics
        assert diag is not None
        assert diag["stage"] == "unexpected_exception"
        assert "simulated crash" in diag["stderr_tail"]

    def test_diagnostics_reset_between_calls(self, tmp_path, monkeypatch):
        """连续两次调用：第二次的 diag 不应保留第一次的 stage。"""
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()

        # 第一次：subprocess_error
        def fake_run_fail(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 3, stdout="", stderr="fail")

        monkeypatch.setattr(subprocess, "run", fake_run_fail)
        s.convert_sldprt_to_step(str(tmp_path / "1.sldprt"), str(tmp_path / "1.step"))
        assert s.last_convert_diagnostics["stage"] == "subprocess_error"

        # 第二次：success（不同 fake）
        def fake_run_ok(cmd, **kwargs):
            Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(cmd[-1]).write_bytes(b"ISO-10303-214\n" + b"X" * 2000)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run_ok)
        s.convert_sldprt_to_step(str(tmp_path / "2.sldprt"), str(tmp_path / "2.step"))
        assert s.last_convert_diagnostics["stage"] == "success"


class TestDoConvertExit5:
    """exit 5 (config_not_found) 不计熔断器，通过 diagnostics stage 传递。"""

    def test_exit5_returns_false_and_no_breaker_increment(self, tmp_path, monkeypatch):
        import subprocess
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()

        def fake_run_exit5(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 5, stdout="", stderr="config not found")

        monkeypatch.setattr(subprocess, "run", fake_run_exit5)

        ok = s.convert_sldprt_to_step(
            str(tmp_path / "part.sldprt"),
            str(tmp_path / "out.step"),
            "GB_T70.1-M6x20",
        )
        assert ok is False
        assert s._consecutive_failures == 0  # 不计熔断
        assert s.is_healthy() is True

    def test_exit5_sets_config_not_found_stage(self, tmp_path, monkeypatch):
        import subprocess
        from adapters.solidworks.sw_com_session import (
            SwComSession, reset_session, _STAGE_CONFIG_NOT_FOUND,
        )

        reset_session()
        s = SwComSession()

        def fake_run_exit5(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 5, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run_exit5)

        s.convert_sldprt_to_step(
            str(tmp_path / "part.sldprt"),
            str(tmp_path / "out.step"),
            "GB_T70.1-M6x20",
        )
        diag = s.last_convert_diagnostics
        assert diag is not None
        assert diag["stage"] == _STAGE_CONFIG_NOT_FOUND
        assert diag["exit_code"] == 5

    def test_exit5_three_times_does_not_trip_breaker(self, tmp_path, monkeypatch):
        import subprocess
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()

        def fake_run_exit5(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 5, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run_exit5)

        for _ in range(3):
            s.convert_sldprt_to_step(
                str(tmp_path / "part.sldprt"),
                str(tmp_path / "out.step"),
                "GB_T70.1-M6x20",
            )
        assert s.is_healthy() is True

    def test_target_config_appended_to_cmd(self, tmp_path, monkeypatch):
        import subprocess
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()
        captured_cmds = []

        def fake_run_success(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            out_path = cmd[-2]  # tmp_path = argv[-2] when target_config present
            from pathlib import Path
            Path(out_path).parent.mkdir(parents=True, exist_ok=True)
            Path(out_path).write_bytes(b"ISO-10303-214\n" + b"X" * 2000)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run_success)

        s.convert_sldprt_to_step(
            str(tmp_path / "part.sldprt"),
            str(tmp_path / "out.step"),
            "GB_T70.1-M6x20",
        )
        cmd = captured_cmds[0]
        assert cmd[-1] == "GB_T70.1-M6x20"

    def test_nonzero_non5_rc_increments_breaker(self, tmp_path, monkeypatch):
        import subprocess
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()

        def fake_run_exit2(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 2, stdout="", stderr="OpenDoc6 fail")

        monkeypatch.setattr(subprocess, "run", fake_run_exit2)

        s.convert_sldprt_to_step(str(tmp_path / "part.sldprt"), str(tmp_path / "out.step"))
        assert s._consecutive_failures == 1
