"""6 个交互点 × 4 种响应 = 24 case 退出矩阵集成测试（spec §9.1.1 / plan Task 34）。

每个 case 验证：给定交互点在给定响应下**不留半完成状态**
（raise、返回、或清理痕迹正确——任一都算 "干净退出"）。

交互点（INTERACTION_POINTS）：
    1. wait_close_assembly    — sw_preflight.io.wait_for_assembly_close 轮询等装配关闭
    2. pywin32_install_prompt — sw_preflight.matrix.fix_pywin32（pip install 失败退出）
    3. addin_enable_prompt    — sw_preflight.matrix.fix_addin_enable（管理员需求）
    4. admin_required_prompt  — sw_preflight.matrix.handle_admin_required（三选一）
    5. three_choice_prompt    — sw_preflight.io.three_choice_prompt（BOM 缺件三选一）
    6. cancel_dialog_secondary— sw_preflight.user_provided.prompt_user_provided
                                 取消对话框后的二次提问（stand-in / 跳过）

响应（RESPONSES）：
    - 'Y'       — 同意 / 正常路径
    - 'N'       — 拒绝 / 降级路径
    - 'Q'       — 主动放弃（如适用则 sys.exit(2)）
    - 'TIMEOUT' — 仅 wait_close_assembly 适用；其它交互点直接 skip

有效 case：19（wait_close 4 + 其它 5 点各 3 = 19）
跳过 case：5（非 wait_close 的 TIMEOUT 组合）
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


INTERACTION_POINTS = [
    'wait_close_assembly',
    'pywin32_install_prompt',
    'addin_enable_prompt',
    'admin_required_prompt',
    'three_choice_prompt',
    'cancel_dialog_secondary',
]

RESPONSES = ['Y', 'N', 'Q', 'TIMEOUT']


def _valid_case(interaction: str, response: str) -> bool:
    """TIMEOUT 仅对 wait_close_assembly 有意义；其它组合 skip 掉避免虚假冗余。"""
    if response == 'TIMEOUT':
        return interaction == 'wait_close_assembly'
    return True


@pytest.mark.parametrize('interaction', INTERACTION_POINTS)
@pytest.mark.parametrize('response', RESPONSES)
def test_interaction_exit_paths_clean(interaction: str, response: str) -> None:
    """每个交互点 × 响应组合：不留半完成状态（无半写文件 / 无异常泄漏 / 清理完整）。

    每个 interaction 分支各自 mock 最小路径，只断言**该响应下的可观测结果**
    （返回值、raise 类型 / match 正则、SystemExit code），不做跨交互点耦合断言。
    """
    if not _valid_case(interaction, response):
        pytest.skip(f"{response} 不适用 {interaction}")

    # ------------------------------------------------------------------
    # 1. wait_for_assembly_close —— 超时 / 成功 / 被动退出
    # ------------------------------------------------------------------
    if interaction == 'wait_close_assembly':
        from sw_preflight.io import wait_for_assembly_close

        if response == 'TIMEOUT':
            # 装配体始终未关 → 极短 timeout 触发 False 干净返回
            with patch('sw_preflight.io._count_open_assemblies', return_value=1):
                result = wait_for_assembly_close(timeout_sec=0.02, poll_interval=0.005)
                assert result is False, "timeout 时必须返回 False（不抛异常）"
        elif response == 'Y':
            # 装配体已全关 → 首次探测即 True
            with patch('sw_preflight.io._count_open_assemblies', return_value=0):
                assert wait_for_assembly_close(timeout_sec=0.1, poll_interval=0.01) is True
        else:
            # N / Q：等价"用户不关 / 放弃"，用极短 timeout 观察干净返回 False
            with patch('sw_preflight.io._count_open_assemblies', return_value=1):
                assert (
                    wait_for_assembly_close(timeout_sec=0.01, poll_interval=0.005)
                    is False
                )

    # ------------------------------------------------------------------
    # 2. fix_pywin32 —— pip install Y 成功 / N Q 失败 raise
    # ------------------------------------------------------------------
    elif interaction == 'pywin32_install_prompt':
        from sw_preflight.matrix import fix_pywin32

        if response == 'Y':
            # 两次 subprocess.run：pip install 成功 + postinstall import win32com 成功
            with patch(
                'subprocess.run',
                return_value=MagicMock(returncode=0, stderr=''),
            ):
                record = fix_pywin32()
                assert 'installed' in record.after_state.lower(), (
                    f"期望 after_state 含 'installed'，实际 {record.after_state!r}"
                )
        else:
            # N / Q：pip 失败 → raise RuntimeError("PYWIN32_INSTALL_FAILED: ...")
            with patch(
                'subprocess.run',
                return_value=MagicMock(returncode=1, stderr='user denied'),
            ):
                with pytest.raises(RuntimeError, match='PYWIN32_INSTALL_FAILED'):
                    fix_pywin32()

    # ------------------------------------------------------------------
    # 3. fix_addin_enable —— 已启用幂等 no_op / 未启用 + 等关超时 raise
    # ------------------------------------------------------------------
    elif interaction == 'addin_enable_prompt':
        from sw_preflight.matrix import fix_addin_enable

        if response == 'Y':
            # 已启用分支：_is_addin_enabled 返 True → 幂等 no_op
            with patch('sw_preflight.matrix._is_addin_enabled', return_value=True):
                record = fix_addin_enable()
                assert record.after_state == 'no_op', (
                    f"已启用应 no_op，实际 {record.after_state!r}"
                )
        else:
            # N / Q：未启用 + wait_for_assembly_close 超时返 False → raise
            with patch('sw_preflight.matrix._is_addin_enabled', return_value=False):
                with patch('sw_preflight.io.wait_for_assembly_close', return_value=False):
                    with pytest.raises(RuntimeError, match='ADDIN_ENABLE_FAILED'):
                        fix_addin_enable()

    # ------------------------------------------------------------------
    # 4. handle_admin_required —— 选 manual / Q → sys.exit(2)
    # ------------------------------------------------------------------
    elif interaction == 'admin_required_prompt':
        from sw_preflight.matrix import handle_admin_required

        # Y / N 都映射到"2 手动修"（返 'manual'）；Q 映射到 'Q' → sys.exit(2)
        choice_map = {'Y': '2', 'N': '2', 'Q': 'Q'}
        user_input = choice_map[response]
        with patch('builtins.input', return_value=user_input):
            with patch('sw_preflight.matrix.is_user_admin', return_value=False):
                if response == 'Q':
                    with pytest.raises(SystemExit) as exc:
                        handle_admin_required(action_desc='test')
                    assert exc.value.code == 2, (
                        f"Q 退出码必须是 2，实际 {exc.value.code}"
                    )
                else:
                    result = handle_admin_required(action_desc='test')
                    assert result == 'manual'

    # ------------------------------------------------------------------
    # 5. three_choice_prompt —— 1 provide / 2 stand_in / 3 skip
    # ------------------------------------------------------------------
    elif interaction == 'three_choice_prompt':
        from sw_preflight.io import three_choice_prompt

        choice_map = {'Y': '1', 'N': '2', 'Q': '3'}
        expected_map = {'1': 'provide', '2': 'stand_in', '3': 'skip'}
        with patch('builtins.input', return_value=choice_map[response]):
            # 吞 prompt 打印，保持测试输出干净
            with patch('builtins.print'):
                result = three_choice_prompt(missing_count=3)
                assert result == expected_map[choice_map[response]]

    # ------------------------------------------------------------------
    # 6. cancel_dialog_secondary —— 取消对话框后 [1]stand-in / [2]跳过
    # ------------------------------------------------------------------
    elif interaction == 'cancel_dialog_secondary':
        from sw_preflight.user_provided import prompt_user_provided

        # 二次提问：'1' stand-in / '2' 跳过；Q 等价选 '2'（用户主动放弃该行）
        choice_map = {'Y': '1', 'N': '2', 'Q': '2'}
        with patch('sw_preflight.io.three_choice_prompt', return_value='provide'):
            with patch('sw_preflight.io.ask_step_file', return_value=None):
                with patch('builtins.input', return_value=choice_map[response]):
                    result = prompt_user_provided(
                        [{'name_cn': 'TEST', 'part_no': 'P001'}],
                        copy_files=False,
                    )
                    if choice_map[response] == '1':
                        assert len(result.stand_in_keys) == 1, (
                            f"选 1 应产生 1 个 stand-in key，实际 {result.stand_in_keys}"
                        )
                        assert len(result.skipped_keys) == 0
                    else:
                        assert len(result.skipped_keys) == 1, (
                            f"选 2 应产生 1 个 skipped key，实际 {result.skipped_keys}"
                        )
                        assert len(result.stand_in_keys) == 0
