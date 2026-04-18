"""per_step_ms 字段的单测（F-1.3l Phase 1）。

所有测试用 mock 不依赖真 SW / pywin32；Linux CI 可跑。
"""

from __future__ import annotations

import concurrent.futures  # noqa: F401  # T6 TestTimeoutPathPerStep 使用
from unittest import mock

import pytest  # noqa: F401  # T7 TestWorkerStepException / T10 TestSchemaPerStep 使用


class TestColdDispatchPerStep:
    """冷启路径下 per_step_ms 的语义测试。"""

    def test_cold_dispatch_per_step_sum_matches_elapsed(self, monkeypatch):
        """冷启路径下，per_step_ms 4 段之和 ≈ elapsed_ms（±50ms 容差）。"""
        from adapters.solidworks import sw_probe

        # mock pywin32 使得 GetObject 抛（attach 路径不命中）
        monkeypatch.setattr(
            "win32com.client.GetObject",
            mock.Mock(side_effect=Exception("no running SW")),
        )

        # mock worker 函数返回已知的 per_step_ms
        fake_per_step = {
            "dispatch_ms": 100,
            "revision_ms": 50,
            "visible_ms": 30,
            "exitapp_ms": 20,
        }

        def fake_worker(progid):
            return ("2024", True, True, fake_per_step)

        monkeypatch.setattr(
            sw_probe, "_dispatch_and_probe_worker", fake_worker, raising=False
        )

        r = sw_probe.probe_dispatch(timeout_sec=10)

        assert r.ok is True
        assert r.data["attached_existing_session"] is False
        assert r.data["per_step_ms"] == fake_per_step
        assert (
            sum(fake_per_step.values()) - 50
            <= r.data["elapsed_ms"]
            <= sum(fake_per_step.values()) + 50
        ), f"elapsed_ms={r.data['elapsed_ms']} 超出 per_step 总和 ±50ms"

    def test_worker_t0_start_inside_worker(self, monkeypatch):
        """回归钉：elapsed_ms 不应包含线程池 cold-start 开销。

        模拟 worker 先 sleep 500ms 再返回 per_step 总和 10。
        若 elapsed_ms 误用外层 t0（即 int((perf_counter() - t0) * 1000)），
        则 elapsed ≥ 500；正确实现应 elapsed = sum(per_step) = 10 < 100。
        """
        import time as _time_mod

        from adapters.solidworks import sw_probe

        monkeypatch.setattr(
            "win32com.client.GetObject",
            mock.Mock(side_effect=Exception("no running SW")),
        )

        def slow_worker(progid):
            _time_mod.sleep(0.5)  # 模拟线程池 cold-start 延迟
            fake_per_step = {
                "dispatch_ms": 5,
                "revision_ms": 3,
                "visible_ms": 1,
                "exitapp_ms": 1,
            }
            return ("2024", True, True, fake_per_step)

        monkeypatch.setattr(sw_probe, "_dispatch_and_probe_worker", slow_worker)

        r = sw_probe.probe_dispatch(timeout_sec=10)
        assert r.data["elapsed_ms"] < 100, (
            f"elapsed_ms={r.data['elapsed_ms']} 包含了 500ms 线程池 cold-start — "
            "t0 被误放在 submit 之前"
        )
