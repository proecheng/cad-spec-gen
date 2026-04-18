"""AC-3 区间断言单测（F-1.3l Phase 1 Task 11 — AC-3 首次代码化）。

AC-3 从 F-1.3j+k runbook 文字期望（[3000, 15000]）升级为代码断言。
Phase 1 初值 [100, 30000] 宽容兼容现状（浅档 310ms 深档 3295ms 都在内），
Phase 3 再按 Phase 2 实测收紧。
"""

from __future__ import annotations

import pytest

from tools.assert_sw_inspect_schema import (
    AC3_LOWER_MS,
    AC3_UPPER_MS,
    assert_ac3_range,
)


class TestAC3Range:
    def test_ac3_initial_bounds_100_30000(self):
        """Phase 1 初值区间 [100, 30000] 覆盖已知双峰 + 30s timeout 上限。"""
        assert AC3_LOWER_MS == 100
        assert AC3_UPPER_MS == 30_000

    def test_shallow_peak_310ms_passes(self):
        """已知浅档中位数 310ms 在 [100, 30000] 内。"""
        data = {"elapsed_ms": 310, "attached_existing_session": False}
        assert_ac3_range(data)  # 不抛

    def test_deep_peak_3295ms_passes(self):
        """已知深档中位数 3295ms 在 [100, 30000] 内。"""
        data = {"elapsed_ms": 3295, "attached_existing_session": False}
        assert_ac3_range(data)  # 不抛

    def test_f1_baseline_5492ms_passes(self):
        """F.1 首次 baseline 5492ms 在 [100, 30000] 内。"""
        data = {"elapsed_ms": 5492, "attached_existing_session": False}
        assert_ac3_range(data)  # 不抛

    def test_below_lower_bound_fails(self):
        """< 100ms 触发 fail（防止"瞬时"异常点）。"""
        data = {"elapsed_ms": 50, "attached_existing_session": False}
        with pytest.raises(AssertionError, match="AC-3"):
            assert_ac3_range(data)

    def test_above_upper_bound_fails(self):
        """> 30000ms 触发 fail（超 30s 上限）。"""
        data = {"elapsed_ms": 35_000, "attached_existing_session": False}
        with pytest.raises(AssertionError, match="AC-3"):
            assert_ac3_range(data)

    def test_attach_path_skipped(self):
        """attach 路径 elapsed_ms=0 但 attached_existing_session=True → 跳过检查。"""
        data = {"elapsed_ms": 0, "attached_existing_session": True}
        assert_ac3_range(data)  # 不抛（attach 路径豁免）
