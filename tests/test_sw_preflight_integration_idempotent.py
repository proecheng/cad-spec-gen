"""sw_preflight 修复幂等集成测试（spec §9.1.2 / plan Task 34）。

连跑 3 次 run_preflight：
- 第 1 次：run_all_checks 首跑 fail（addin_enabled）→ try_one_click_fix 返 FixRecord
  → 重跑 pass → fixes_applied 含 1 条
- 第 2/3 次：run_all_checks 首跑就 pass → try_one_click_fix 不会被调 → fixes_applied 空

幂等含义：同一台机器连跑多次，真实修复动作只在第一次发生；后续次数识别
"已修好"直接静默通过，体现 "修完就不再折腾用户" 的产品承诺（spec §8.4）。
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from sw_preflight.types import FixRecord


def test_three_consecutive_runs_only_first_fixes(tmp_path, monkeypatch) -> None:
    """连跑 3 次 run_preflight，第 1 次修 addin，第 2/3 次已启用 → 无 fix。

    每轮的 mock 构造：
    - 第 1 次：run_all_checks side_effect 第一次返 {passed: False, failed_check: addin},
      第二次返 passed=True；try_one_click_fix 返 fake FixRecord
    - 第 2/3 次：run_all_checks side_effect 只一个 pass，不触发 fix
    """
    # cwd 切 tmp_path，避免 run_id cache 落盘污染真实 artifacts/
    monkeypatch.chdir(tmp_path)

    fake_fix = FixRecord(
        action='addin_enable',
        before_state='disabled',
        after_state='enabled_hkcu',
        elapsed_ms=50.0,
    )

    fixes_per_run: list[int] = []

    for i in range(3):
        if i == 0:
            # 第 1 次：首跑 fail → fix → 重跑 pass；两次 check 调用
            check_responses = [
                {
                    'passed': False,
                    'failed_check': 'addin_enabled',
                    'diagnosis': MagicMock(
                        severity='block',
                        reason='Toolbox Add-In 未启用',
                        suggestion='一键修',
                    ),
                },
                {'passed': True, 'failed_check': None, 'diagnosis': None},
            ]
            fix_response = fake_fix
        else:
            # 第 2/3 次：已幂等，首跑就 pass；try_one_click_fix 不会被调
            check_responses = [
                {'passed': True, 'failed_check': None, 'diagnosis': None},
            ]
            fix_response = None

        with patch(
            'sw_preflight.matrix.run_all_checks',
            side_effect=check_responses,
        ):
            with patch(
                'sw_preflight.matrix.try_one_click_fix',
                return_value=fix_response,
            ):
                # detect_solidworks 结果不影响本 case 断言，mock 成已装的 Pro
                with patch(
                    'adapters.solidworks.sw_detect.detect_solidworks',
                    return_value=MagicMock(
                        installed=True, version_year=2024, edition='Pro'
                    ),
                ):
                    from sw_preflight.preflight import run_preflight

                    result = run_preflight(
                        strict=False,
                        run_id=f'idempotent-run-{i}',
                        entry='test',
                    )
                    fixes_per_run.append(len(result.fixes_applied))

    assert fixes_per_run == [1, 0, 0], (
        f"幂等性断言失败 — 期望 [1, 0, 0]，实际 fixes_per_run = {fixes_per_run}"
    )
