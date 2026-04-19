"""Task 14 — fix_rot_orphan：静默释放 COM ROT 僵死实例 + reset sw_detect 缓存。

sw_com_session 无 release_all API（已核实），实现走 plan 脚注的 fallback：
pythoncom.CoUninitialize() + CoInitialize() 对 + sw_detect.reset_cache()。

本测试只校验对外契约（action 字段 + reset_cache 被调用），
不校验 pythoncom 内部调用形态 — 给实现留 fallback 空间。
"""
from unittest.mock import MagicMock, patch


def test_fix_rot_releases_orphan_session(monkeypatch):
    """检测到 ROT 僵死 → release + reset cache → 静默"""
    from sw_preflight.matrix import fix_rot_orphan
    fake_session = MagicMock()
    fake_session.is_healthy.side_effect = [False, True]  # 修后健康
    with patch('adapters.solidworks.sw_com_session.get_session', return_value=fake_session):
        with patch('adapters.solidworks.sw_detect.reset_cache') as mock_reset:
            record = fix_rot_orphan()
            assert record.action == 'rot_orphan_release'
            mock_reset.assert_called_once()
