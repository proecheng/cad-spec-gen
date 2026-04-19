"""Task 13：fix_pywin32 一键安装测试 — 覆盖成功 / pip 失败两条路径。"""
from unittest.mock import patch, MagicMock


def test_fix_pywin32_install_success():
    """pywin32 装好 + postinstall 跑完 → 返回 FixRecord(success=True)"""
    from sw_preflight.matrix import fix_pywin32
    with patch('subprocess.run', return_value=MagicMock(returncode=0)):
        with patch('importlib.util.find_spec', return_value=MagicMock()):
            record = fix_pywin32()
            assert record.action == 'pywin32_install'
            assert 'success' in record.after_state.lower()


def test_fix_pywin32_install_fail():
    """pip install 失败 → raise RuntimeError(PYWIN32_INSTALL_FAILED)"""
    from sw_preflight.matrix import fix_pywin32
    with patch('subprocess.run', return_value=MagicMock(returncode=1, stderr='no network')):
        import pytest
        with pytest.raises(RuntimeError, match="PYWIN32_INSTALL_FAILED"):
            fix_pywin32()
