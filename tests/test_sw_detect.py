"""
tests/test_sw_detect.py — SwInfo 数据类与 detect_solidworks() 的单元测试。
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from adapters.solidworks.sw_detect import SwInfo, detect_solidworks, _reset_cache


class TestSwInfoDataclass:
    """SwInfo 数据类的默认值验证。"""

    def test_sw_info_dataclass_defaults(self):
        """验证 SwInfo 所有字段的默认值正确。"""
        info = SwInfo()
        assert info.installed is False
        assert info.version == ""
        assert info.version_year == 0
        assert info.install_dir == ""
        assert info.sldmat_paths == []
        assert info.textures_dir == ""
        assert info.p2m_dir == ""
        assert info.toolbox_dir == ""
        assert info.com_available is False
        assert info.pywin32_available is False

    def test_sw_info_sldmat_paths_not_shared(self):
        """验证不同实例的 sldmat_paths 不共享同一列表。"""
        a = SwInfo()
        b = SwInfo()
        a.sldmat_paths.append("/fake")
        assert b.sldmat_paths == []

    def test_sw_info_has_toolbox_addin_enabled_field_default_false(self):
        """v4 决策 #13: SwInfo 新增 toolbox_addin_enabled 字段，默认 False。"""
        info = SwInfo()
        assert hasattr(info, "toolbox_addin_enabled")
        assert info.toolbox_addin_enabled is False


class TestNonWindows:
    """非 Windows 平台的短路行为。"""

    def test_non_windows_returns_not_installed(self, monkeypatch):
        """monkeypatch sys.platform 为 'linux'，验证返回 installed=False。"""
        _reset_cache()
        monkeypatch.setattr(sys, "platform", "linux")
        result = detect_solidworks()
        assert result.installed is False
        assert result.version == ""
        assert result.install_dir == ""
        # 清理缓存，避免污染其他测试
        _reset_cache()


class TestCaching:
    """进程级缓存机制。"""

    def test_detect_caches_result(self, monkeypatch):
        """验证第二次调用返回同一对象（缓存命中）。"""
        _reset_cache()
        monkeypatch.setattr(sys, "platform", "linux")
        first = detect_solidworks()
        second = detect_solidworks()
        assert first is second
        _reset_cache()

    def test_reset_cache_clears(self, monkeypatch):
        """验证 _reset_cache() 后重新执行检测。"""
        _reset_cache()
        monkeypatch.setattr(sys, "platform", "linux")
        first = detect_solidworks()
        _reset_cache()
        second = detect_solidworks()
        # 值相同但不是同一对象
        assert first is not second
        assert first.installed == second.installed
        _reset_cache()


@pytest.mark.skipif(sys.platform != "win32", reason="仅在 Windows 上执行真实检测")
class TestRealDetection:
    """Windows 上的真实检测（CI 可跳过）。"""

    def test_detect_on_current_machine(self):
        """在 Windows 上跑真实检测，验证返回类型正确。"""
        _reset_cache()
        result = detect_solidworks()
        assert isinstance(result, SwInfo)
        # 无论是否安装了 SW，字段类型应正确
        assert isinstance(result.installed, bool)
        assert isinstance(result.version, str)
        assert isinstance(result.version_year, int)
        assert isinstance(result.install_dir, str)
        assert isinstance(result.sldmat_paths, list)
        assert isinstance(result.textures_dir, str)
        assert isinstance(result.p2m_dir, str)
        assert isinstance(result.toolbox_dir, str)
        assert isinstance(result.com_available, bool)
        assert isinstance(result.pywin32_available, bool)
        _reset_cache()
