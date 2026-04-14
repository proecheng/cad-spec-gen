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


class TestToolboxAddinDetection:
    """v4 决策 #13: Toolbox Add-In 启用检测 — 从注册表读取。"""

    def test_addin_enabled_returns_false_when_winreg_import_fails(self, monkeypatch):
        """非 Windows 或 winreg 不可导入时返回 False。"""
        from adapters.solidworks.sw_detect import _check_toolbox_addin_enabled

        assert _check_toolbox_addin_enabled(None, 2024) is False

    def test_addin_enabled_returns_false_when_registry_key_missing(self, monkeypatch):
        """注册表路径不存在 → False。"""
        import unittest.mock as mock
        from adapters.solidworks.sw_detect import _check_toolbox_addin_enabled

        fake_winreg = mock.MagicMock()
        fake_winreg.OpenKey.side_effect = FileNotFoundError
        fake_winreg.HKEY_CURRENT_USER = 0

        assert _check_toolbox_addin_enabled(fake_winreg, 2024) is False

    def test_addin_enabled_returns_true_when_flag_value_is_1(self):
        """注册表 AddInsStartup 下有 Toolbox GUID 值为 1 → True。"""
        import unittest.mock as mock
        from adapters.solidworks.sw_detect import _check_toolbox_addin_enabled

        fake_winreg = mock.MagicMock()
        fake_winreg.HKEY_CURRENT_USER = 0
        fake_winreg.KEY_READ = 0
        fake_key = mock.MagicMock()
        fake_winreg.OpenKey.return_value.__enter__.return_value = fake_key
        fake_winreg.EnumValue.side_effect = [
            ("{BBF84E59-...}", 1, 4),  # any Toolbox-like GUID, value=1
            OSError,  # no more
        ]

        assert _check_toolbox_addin_enabled(fake_winreg, 2024) is True

    def test_addin_enabled_returns_false_on_garbage_value_type(self):
        """注册表值为非整数类型（字符串/None）时不崩溃，视为未启用返回 False。"""
        import unittest.mock as mock
        from adapters.solidworks.sw_detect import _check_toolbox_addin_enabled

        fake_winreg = mock.MagicMock()
        fake_winreg.HKEY_CURRENT_USER = 0
        fake_winreg.KEY_READ = 0
        fake_key = mock.MagicMock()
        fake_winreg.OpenKey.return_value.__enter__.return_value = fake_key
        # 垃圾数据：字符串 "bad" 无法被 int() 转换，不应抛 ValueError
        # _check_toolbox_addin_enabled 有两个候选 subkey，每个都需要终止 OSError
        fake_winreg.EnumValue.side_effect = [
            ("{BBF84E59-toolbox}", "bad", 1),
            OSError,  # 第一个 subkey 枚举结束
            OSError,  # 第二个 subkey 枚举结束
        ]
        assert _check_toolbox_addin_enabled(fake_winreg, 2024) is False

    def test_addin_enabled_returns_false_on_none_value(self):
        """注册表值为 None 时不崩溃，视为未启用返回 False。"""
        import unittest.mock as mock
        from adapters.solidworks.sw_detect import _check_toolbox_addin_enabled

        fake_winreg = mock.MagicMock()
        fake_winreg.HKEY_CURRENT_USER = 0
        fake_winreg.KEY_READ = 0
        fake_key = mock.MagicMock()
        fake_winreg.OpenKey.return_value.__enter__.return_value = fake_key
        # None 值：int(None) 会抛 TypeError，不应冒泡
        # _check_toolbox_addin_enabled 有两个候选 subkey，每个都需要终止 OSError
        fake_winreg.EnumValue.side_effect = [
            ("{BBF84E59-toolbox}", None, 1),
            OSError,  # 第一个 subkey 枚举结束
            OSError,  # 第二个 subkey 枚举结束
        ]
        assert _check_toolbox_addin_enabled(fake_winreg, 2024) is False

    def test_addin_enabled_ignores_non_guid_friendly_name(self):
        """I-3 回归: 第三方 Add-In 用友好名（非 GUID 形状）注册且含 'toolbox' 字样时，
        不应误判为 SW 自带 Toolbox 启用。

        注册表 AddInsStartup 下的合法值名都是 `{GUID}` 形状；任何不以 `{` 开头的
        value name 一律视为第三方/手写配置，排除在 Toolbox 识别范围外。
        """
        import unittest.mock as mock
        from adapters.solidworks.sw_detect import _check_toolbox_addin_enabled

        fake_winreg = mock.MagicMock()
        fake_winreg.HKEY_CURRENT_USER = 0
        fake_winreg.KEY_READ = 0
        fake_key = mock.MagicMock()
        fake_winreg.OpenKey.return_value.__enter__.return_value = fake_key
        # 友好名 "MyToolboxPro" — 含 "toolbox" 子串但不是 GUID 形状，应被拒
        fake_winreg.EnumValue.side_effect = [
            ("MyToolboxPro", 1, 4),
            OSError,  # 第一个 subkey 枚举结束
            OSError,  # 第二个 subkey 枚举结束
        ]
        assert _check_toolbox_addin_enabled(fake_winreg, 2024) is False


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


class TestDetectImplToolboxAddinIntegration:
    """v4 决策 #13: _detect_impl 集成 toolbox_addin_enabled 字段填充。"""

    def test_detect_impl_populates_toolbox_addin_enabled_field(
        self, tmp_path, monkeypatch
    ):
        """使用真实 tmp_path 目录树，验证 _detect_impl 正确填充 toolbox_addin_enabled。

        改用 tmp_path 创建真实目录，避免全局 patch Path.is_dir 导致所有路径
        检查被静默通过的副作用。
        """
        import unittest.mock as mock
        import adapters.solidworks.sw_detect as sw_detect_mod

        _reset_cache()
        monkeypatch.setattr(sys, "platform", "win32")

        # 创建真实的 fake 安装目录树，让 is_dir() 自然返回 True
        fake_install = tmp_path / "SOLIDWORKS Corp" / "SOLIDWORKS"
        fake_install.mkdir(parents=True)
        # 创建 _detect_impl 里会检查的子目录
        (fake_install / "data" / "Images" / "textures").mkdir(parents=True)
        (fake_install / "data" / "graphics" / "Materials").mkdir(parents=True)
        (fake_install / "lang").mkdir(parents=True)

        fake_install_dir = str(fake_install)

        # 构造最小化 winreg mock — 让 _find_install_from_registry 返回真实 tmp_path 目录
        fake_winreg = mock.MagicMock()
        fake_winreg.HKEY_LOCAL_MACHINE = 0
        fake_winreg.HKEY_CLASSES_ROOT = 0
        fake_winreg.HKEY_CURRENT_USER = 0
        fake_winreg.KEY_READ = 1
        fake_winreg.KEY_WOW64_64KEY = 256
        fake_winreg.KEY_WOW64_32KEY = 512

        def fake_open_key(hive, path, *args, **kwargs):
            return mock.MagicMock()

        fake_winreg.OpenKey.side_effect = fake_open_key

        def fake_query_value_ex(key, name):
            if name == "SolidWorks Folder":
                return (fake_install_dir, 1)
            if name == "Version":
                return ("30.1.0.0080", 1)
            raise OSError("不存在")

        fake_winreg.QueryValueEx.side_effect = fake_query_value_ex

        # monkeypatch winreg 导入
        monkeypatch.setitem(sys.modules, "winreg", fake_winreg)

        # 不再全局 patch Path.is_dir — 真实目录树使 is_dir() 自然工作
        # glob 返回空列表（无 .sldmat 文件）
        monkeypatch.setattr("pathlib.Path.glob", lambda self, pat: iter([]))

        # 关键：monkeypatch _check_toolbox_addin_enabled 返回 True
        monkeypatch.setattr(
            sw_detect_mod, "_check_toolbox_addin_enabled", lambda winreg, year: True
        )
        # monkeypatch _check_com_available / _check_pywin32 避免副作用
        monkeypatch.setattr(sw_detect_mod, "_check_com_available", lambda winreg: False)
        monkeypatch.setattr(sw_detect_mod, "_check_pywin32", lambda: False)

        result = sw_detect_mod._detect_impl()

        assert result.toolbox_addin_enabled is True
        # 验证真实路径检测也正常工作
        assert result.textures_dir != ""
        assert result.p2m_dir != ""
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
