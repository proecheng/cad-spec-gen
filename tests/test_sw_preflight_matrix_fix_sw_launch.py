"""Task 16：验证 fix_sw_launch_background 启动 SW 后台进程（不弹 GUI）。

测试层面通过 mock `get_session` 让 `is_healthy()` 返回 True，模拟 SW 已在运行
的场景——此时 fix 函数走 early return 路径，不实际触发 pythoncom Dispatch。
断言 action 名称正确 + after_state 含 'launched'（early return 用
'launched_already'，真正 Dispatch 用 'launched_invisible'，均含 'launched'）。
"""
from unittest.mock import MagicMock, patch


def test_fix_sw_launch_background() -> None:
    """SW 已健康时 fix 幂等返回含 'launched' 的 after_state。"""
    from sw_preflight.matrix import fix_sw_launch_background
    fake_session = MagicMock()
    fake_session.is_healthy.return_value = True
    with patch(
        'adapters.solidworks.sw_com_session.get_session',
        return_value=fake_session,
    ):
        record = fix_sw_launch_background()
        assert record.action == 'sw_launch_background'
        assert 'launched' in record.after_state.lower()
