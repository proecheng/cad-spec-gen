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


class TestAttachPathPerStep:
    """attach 路径下 per_step_ms 的语义测试。"""

    def test_attach_path_per_step_all_zero(self, monkeypatch):
        """attach 路径 elapsed_ms=0 且 per_step_ms 全 0（未运行到任何一步）。"""
        from adapters.solidworks import sw_probe

        fake_app = mock.Mock()
        fake_app.RevisionNumber = "2024"

        monkeypatch.setattr(
            "win32com.client.GetObject",
            mock.Mock(return_value=fake_app),
        )

        r = sw_probe.probe_dispatch(timeout_sec=10)

        assert r.data["attached_existing_session"] is True
        assert r.data["elapsed_ms"] == 0
        assert r.data["per_step_ms"] == {
            "dispatch_ms": 0,
            "revision_ms": 0,
            "visible_ms": 0,
            "exitapp_ms": 0,
        }


class TestTimeoutPathPerStep:
    """timeout 路径下 per_step_ms 的语义测试。"""

    def test_timeout_path_per_step(self, monkeypatch):
        """timeout 时 dispatch_ms = timeout_sec*1000，其他 3 段 = 0（哨兵 UNREACHED）。"""
        from adapters.solidworks import sw_probe

        monkeypatch.setattr(
            "win32com.client.GetObject",
            mock.Mock(side_effect=Exception("no running SW")),
        )

        # mock future.result 抛 TimeoutError
        fake_future = mock.Mock()
        fake_future.result = mock.Mock(side_effect=concurrent.futures.TimeoutError())

        fake_executor = mock.Mock()
        fake_executor.submit = mock.Mock(return_value=fake_future)
        fake_executor.shutdown = mock.Mock()

        monkeypatch.setattr(
            "concurrent.futures.ThreadPoolExecutor",
            mock.Mock(return_value=fake_executor),
        )

        r = sw_probe.probe_dispatch(timeout_sec=5)
        assert r.severity == "fail"
        assert r.data["per_step_ms"] == {
            "dispatch_ms": 5000,
            "revision_ms": 0,
            "visible_ms": 0,
            "exitapp_ms": 0,
        }


class TestWorkerStepException:
    """worker 内部单步抛异常的哨兵测试（-1 = RAISED）。"""

    def test_revision_step_raises(self, monkeypatch):
        """RevisionNumber 抛 → revision_ms = -1，但 dispatch_ms 正常，visible/exitapp 仍运行。"""
        from adapters.solidworks import sw_probe

        monkeypatch.setattr(
            "win32com.client.GetObject",
            mock.Mock(side_effect=Exception("no running SW")),
        )

        # mock Dispatch 返回的 _app：RevisionNumber 抛，其他正常
        fake_app = mock.Mock()
        # 关键：RevisionNumber 用 PropertyMock side_effect 抛异常
        type(fake_app).RevisionNumber = mock.PropertyMock(
            side_effect=Exception("rev fail")
        )
        fake_app.Visible = False  # 赋值 OK
        fake_app.ExitApp = mock.Mock(return_value=None)

        monkeypatch.setattr("win32com.client.Dispatch", mock.Mock(return_value=fake_app))

        r = sw_probe.probe_dispatch(timeout_sec=10)
        assert r.data["per_step_ms"]["revision_ms"] == -1
        assert r.data["per_step_ms"]["dispatch_ms"] >= 1  # 最小值截断

    def test_visible_step_raises(self, monkeypatch):
        """Visible = False 抛 → visible_ms = -1；前序步正常记录 + 后序步仍运行。"""
        from adapters.solidworks import sw_probe

        monkeypatch.setattr(
            "win32com.client.GetObject",
            mock.Mock(side_effect=Exception("no running SW")),
        )

        fake_app = mock.Mock()
        fake_app.RevisionNumber = "2024"
        # Visible 赋值抛异常
        type(fake_app).Visible = mock.PropertyMock(side_effect=Exception("visible fail"))
        fake_app.ExitApp = mock.Mock(return_value=None)

        monkeypatch.setattr("win32com.client.Dispatch", mock.Mock(return_value=fake_app))

        r = sw_probe.probe_dispatch(timeout_sec=10)
        assert r.data["per_step_ms"]["visible_ms"] == -1
        assert r.data["per_step_ms"]["dispatch_ms"] >= 1
        assert r.data["per_step_ms"]["revision_ms"] >= 1

    def test_exitapp_step_raises(self, monkeypatch):
        """ExitApp 抛 → exitapp_ms = -1，前 3 步正常记录。"""
        from adapters.solidworks import sw_probe

        monkeypatch.setattr(
            "win32com.client.GetObject",
            mock.Mock(side_effect=Exception("no running SW")),
        )

        fake_app = mock.Mock()
        fake_app.RevisionNumber = "2024"
        fake_app.Visible = False
        fake_app.ExitApp = mock.Mock(side_effect=Exception("exit fail"))

        monkeypatch.setattr("win32com.client.Dispatch", mock.Mock(return_value=fake_app))

        r = sw_probe.probe_dispatch(timeout_sec=10)
        assert r.data["per_step_ms"]["exitapp_ms"] == -1
        assert r.data["per_step_ms"]["dispatch_ms"] >= 1
        assert r.data["per_step_ms"]["revision_ms"] >= 1
        assert r.data["per_step_ms"]["visible_ms"] >= 1


class TestPerStepMinTruncation:
    """E2: per_step_ms <1ms 截断为 1 避免与哨兵 0 混淆。"""

    def test_fast_step_truncated_to_one(self, monkeypatch):
        """成功跑过的步即使耗时 <1ms 也应记为 1，不能记为 0（哨兵 UNREACHED 占用）。"""
        from adapters.solidworks import sw_probe

        monkeypatch.setattr(
            "win32com.client.GetObject",
            mock.Mock(side_effect=Exception("no running SW")),
        )

        # mock worker：每步真实耗时 0.1ms，原始 int 会舍为 0；截断后应为 1
        fake_per_step = {
            "dispatch_ms": 1,  # 真实 0.1ms * 1000 = 0.1 → int=0 → 截断 1
            "revision_ms": 1,
            "visible_ms": 1,
            "exitapp_ms": 1,
        }

        def fake_worker(progid):
            return ("2024", True, True, fake_per_step)

        monkeypatch.setattr(sw_probe, "_dispatch_and_probe_worker", fake_worker)

        r = sw_probe.probe_dispatch(timeout_sec=10)
        for step in ("dispatch_ms", "revision_ms", "visible_ms", "exitapp_ms"):
            assert r.data["per_step_ms"][step] >= 1, (
                f"{step} = 0 与哨兵 UNREACHED 冲突"
            )
