"""Stage C 可观测性集成测试：验证 per_target 含 diagnostics 字段。"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestStageCDiagnosticsIntegration:
    def _fake_matched_list(self) -> list[dict]:
        """造 8 条 matched 记录（Stage C 最小阈值）。"""
        return [
            {
                "part_no": f"P-{i}",
                "sldprt": rf"C:\fake\{i}.sldprt",
                "score": 0.5,
            }
            for i in range(8)
        ]

    def test_per_target_includes_diagnostics_on_success(self, tmp_path):
        """所有 convert 成功 → per_target 每条含 stage=success, exit_code=0。"""
        from tools import sw_b9_acceptance

        matched = self._fake_matched_list()

        # mock session：所有 convert 返回 True 并写有效 STEP
        def fake_convert(self, sldprt, step_out):
            Path(step_out).parent.mkdir(parents=True, exist_ok=True)
            Path(step_out).write_bytes(b"ISO-10303-214\n" + b"X" * 2000)
            self._last_convert_diagnostics = {
                "stage": "success",
                "exit_code": 0,
                "stderr_tail": "",
            }
            return True

        with mock.patch(
            "adapters.solidworks.sw_com_session.SwComSession.convert_sldprt_to_step",
            fake_convert,
        ):
            result = sw_b9_acceptance.stage_c_session_restart(matched, tmp_path)

        assert result["pass"] is True
        assert result["success_count"] == 8
        for entry in result["per_target"]:
            assert entry["stage"] == "success"
            assert entry["exit_code"] == 0
            assert "stderr_tail" in entry

    def test_per_target_includes_diagnostics_on_subprocess_error(self, tmp_path):
        """某 convert 返回 subprocess_error → per_target 对应条目含 exit_code + stderr。"""
        from tools import sw_b9_acceptance

        matched = self._fake_matched_list()

        def fake_convert(self, sldprt, step_out):
            self._last_convert_diagnostics = {
                "stage": "subprocess_error",
                "exit_code": 3,
                "stderr_tail": "worker: SaveAs3 saved=False errors=1",
            }
            return False

        with mock.patch(
            "adapters.solidworks.sw_com_session.SwComSession.convert_sldprt_to_step",
            fake_convert,
        ):
            result = sw_b9_acceptance.stage_c_session_restart(matched, tmp_path)

        assert result["pass"] is False
        for entry in result["per_target"]:
            assert entry.get("failed") is True
            assert entry["stage"] == "subprocess_error"
            assert entry["exit_code"] == 3
            assert "errors=1" in entry["stderr_tail"]
