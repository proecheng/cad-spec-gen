"""Task 17：验证 admin 检测 + ShellExecute runas 退化 + 三选一 prompt。

覆盖 3 条路径：
1. `is_user_admin()` 返回 bool（非 Windows 走 except 返 False，仍是 bool）
2. `elevate_with_runas()` 调用 ShellExecuteW 且第二参数 = 'runas'
3. `handle_admin_required()` 用户选 [2] 时返回 'manual'
"""
import sys
from unittest.mock import patch

import pytest


def test_is_admin_returns_bool() -> None:
    """is_user_admin 必须返回 bool（非 Windows 异常也兜底为 False）。"""
    from sw_preflight.matrix import is_user_admin
    result = is_user_admin()
    assert isinstance(result, bool)


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="ctypes.windll 仅 Windows 存在；产品 Windows-only，CI 跑 Linux 仅为防 import 炸",
)
def test_elevate_with_runas_called(monkeypatch) -> None:
    """elevate_with_runas 调 ShellExecuteW 时第二参数必须是 'runas'。"""
    from sw_preflight.matrix import elevate_with_runas
    called: list = []
    monkeypatch.setattr(
        'ctypes.windll.shell32.ShellExecuteW',
        lambda *a, **kw: called.append(a) or 42,
    )
    elevate_with_runas()
    assert len(called) == 1
    assert called[0][1] == 'runas'  # ShellExecuteW 第 2 个位置参数是 lpOperation


def test_admin_required_three_choice(monkeypatch) -> None:
    """非 admin 时三选一：用户选 [2] 手动修 → 返回 'manual'。"""
    from sw_preflight.matrix import handle_admin_required
    monkeypatch.setattr('builtins.input', lambda _: '2')
    with patch('sw_preflight.matrix.is_user_admin', return_value=False):
        result = handle_admin_required(action_desc='Add-In 启用')
        assert result == 'manual'
