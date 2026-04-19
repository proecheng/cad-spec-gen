"""Task 15：sw_preflight.matrix.fix_addin_enable 测试。

覆盖两条契约：
1. 安全性：必须写 HKCU（不写 HKLM，避免 admin 需求）——
   所有 winreg.OpenKey 调用的 hive 实参必含 'HKEY_CURRENT_USER'。
2. 幂等：`_is_addin_enabled()` 返 True 时不重复写 SetValueEx。

注 — plan 原测试没 mock `_is_addin_enabled` / `get_toolbox_addin_guid`，
但实际实现里有前置判断和 GUID 发现，真环境下会直接走 no_op 或 raise
RuntimeError → OpenKey 永远不被调 → assertion 空跑 vacuous-true。
按 subagent 指令"按实现所需补 mock，保留 HKCU 契约 assert 不变"处理。
"""
from __future__ import annotations

import sys
from unittest.mock import patch, MagicMock

import pytest


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="winreg 仅 Windows 存在；产品 Windows-only，CI 跑 Linux 仅为防 import 炸",
)
def test_addin_enable_writes_hkcu_only():
    """Add-In enable 必须写 HKCU，不写 HKLM（避免 admin 需求）。"""
    import winreg

    from sw_preflight.matrix import fix_addin_enable

    fake_guid = "{BBF84E59-1234-5678-9ABC-DEF012345678}"
    fake_ctx = MagicMock()
    fake_ctx.__enter__.return_value = MagicMock()
    fake_ctx.__exit__.return_value = False

    with patch('sw_preflight.matrix._is_addin_enabled', return_value=False), \
         patch(
             'adapters.parts.sw_toolbox_adapter.get_toolbox_addin_guid',
             return_value=fake_guid,
         ), \
         patch('sw_preflight.io.wait_for_assembly_close', return_value=True), \
         patch('winreg.OpenKey', return_value=fake_ctx) as mock_open, \
         patch('winreg.SetValueEx') as _mock_set:
        fix_addin_enable()

        # 校验：至少有一次 OpenKey 调用，且所有 OpenKey 调用都以 HKCU 为 hive
        # （winreg.HKEY_CURRENT_USER 是整数常量 0x80000001，直接比整数值）
        assert mock_open.call_args_list, "fix_addin_enable 必须至少调一次 winreg.OpenKey"
        for call in mock_open.call_args_list:
            hive = call.args[0] if call.args else call.kwargs.get('key')
            assert hive == winreg.HKEY_CURRENT_USER, (
                f"期望 hive=HKEY_CURRENT_USER(0x80000001)，实得 {hive!r}"
            )


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="winreg 仅 Windows 存在；产品 Windows-only，CI 跑 Linux 仅为防 import 炸",
)
def test_addin_enable_idempotent():
    """已启用 → 跳过写入（不重复调 SetValueEx）。"""
    from sw_preflight.matrix import fix_addin_enable

    with patch('sw_preflight.matrix._is_addin_enabled', return_value=True), \
         patch('winreg.SetValueEx') as mock_set, \
         patch('sw_preflight.io.wait_for_assembly_close', return_value=True):
        result = fix_addin_enable()
        mock_set.assert_not_called()  # 幂等：不重复写
        # 返回记录应标识已启用 / no_op
        assert result.before_state == 'already_enabled'
        assert result.after_state == 'no_op'
