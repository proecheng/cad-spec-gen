# tests/test_b0_edition.py
import sys
import types
import pytest
from adapters.solidworks import sw_detect


def _make_winreg_raises():
    """构造一个所有 OpenKey 都抛 OSError 的 winreg mock（模拟注册表键不存在）。"""
    m = types.SimpleNamespace()
    m.HKEY_LOCAL_MACHINE = 2
    m.KEY_READ = 1
    m.KEY_WOW64_64KEY = 0x0100
    m.KEY_WOW64_32KEY = 0x0200
    m.OpenKey = lambda *a, **kw: (_ for _ in ()).throw(OSError())
    return m


@pytest.mark.skipif(sys.platform != "win32", reason="需要 Windows")
def test_edition_normalized_professional(monkeypatch):
    """注册表 'Professional' → 归一化为 'professional'（小写）。"""
    import winreg as real_winreg
    sw_detect._reset_cache()

    # 同时 mock _read_registry_value 和 _read_registry_dword，隔离真实注册表
    def fake_read(wr, hive, path, name):
        if "SOLIDWORKS 2024" in path and name == "Edition":
            return "Professional"
        return None
    monkeypatch.setattr(sw_detect, "_read_registry_value", fake_read)
    monkeypatch.setattr(sw_detect, "_read_registry_dword", lambda *a, **kw: None)

    result = sw_detect._find_edition(real_winreg, 2024, "")
    assert result == "professional"


@pytest.mark.skipif(sys.platform != "win32", reason="需要 Windows")
def test_edition_standard_lower(monkeypatch):
    """注册表 'Standard' → 归一化为 'standard'。"""
    import winreg as real_winreg
    sw_detect._reset_cache()

    def fake_read(wr, hive, path, name):
        if name == "Edition":
            return "Standard"
        return None
    monkeypatch.setattr(sw_detect, "_read_registry_value", fake_read)
    monkeypatch.setattr(sw_detect, "_read_registry_dword", lambda *a, **kw: None)

    result = sw_detect._find_edition(real_winreg, 2024, "")
    assert result == "standard"


@pytest.mark.skipif(sys.platform != "win32", reason="需要 Windows")
def test_edition_office_installed_3_returns_premium(monkeypatch):
    """SolidWorks Office Installed = 3（DWORD） → 'premium'。"""
    import winreg as real_winreg
    sw_detect._reset_cache()

    monkeypatch.setattr(sw_detect, "_read_registry_value", lambda *a, **kw: None)
    monkeypatch.setattr(sw_detect, "_read_registry_dword", lambda wr, hive, path, name: 3)

    result = sw_detect._find_edition(real_winreg, 2024, "")
    assert result == "premium"


@pytest.mark.skipif(sys.platform != "win32", reason="需要 Windows")
def test_edition_office_installed_1_returns_professional(monkeypatch):
    """SolidWorks Office Installed = 1（DWORD） → 'professional'。"""
    import winreg as real_winreg
    sw_detect._reset_cache()

    monkeypatch.setattr(sw_detect, "_read_registry_value", lambda *a, **kw: None)
    monkeypatch.setattr(sw_detect, "_read_registry_dword", lambda wr, hive, path, name: 1)

    result = sw_detect._find_edition(real_winreg, 2024, "")
    assert result == "professional"


def test_edition_filesystem_probe_finds_dll(tmp_path):
    """注册表无 Edition，install_dir 下有 Toolbox DLL → 返回 'professional'。"""
    addin_dir = tmp_path / "AddIns" / "Toolbox"
    addin_dir.mkdir(parents=True)
    (addin_dir / "SWToolboxBrowser.dll").write_bytes(b"MZ")

    wr = _make_winreg_raises()
    result = sw_detect._find_edition(wr, 2024, str(tmp_path))
    assert result == "professional"


def test_edition_filesystem_probe_no_dll_returns_standard(tmp_path):
    """注册表无 Edition，install_dir 存在但无 Toolbox DLL → 返回 'standard'。"""
    (tmp_path / "AddIns").mkdir()  # 有 AddIns 目录但无 toolbox 子目录

    wr = _make_winreg_raises()
    result = sw_detect._find_edition(wr, 2024, str(tmp_path))
    assert result == "standard"


def test_edition_unknown_when_no_install_dir():
    """注册表无 Edition，install_dir 为空 → 'unknown'。"""
    wr = _make_winreg_raises()
    result = sw_detect._find_edition(wr, 2024, "")
    assert result == "unknown"
