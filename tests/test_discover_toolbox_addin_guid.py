# tests/test_discover_toolbox_addin_guid.py
import sys
import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="requires winreg")
class TestScanAllAddinsByDescription:
    def test_scan_function_is_callable(self):
        """_scan_all_addins_by_description 可导入且可调用。"""
        from adapters.solidworks.sw_detect import _scan_all_addins_by_description
        assert callable(_scan_all_addins_by_description)

    def test_addins_candidates_returns_4_paths(self):
        """_addins_candidates(2024) 返回 4 条 (hive, path) 元组。"""
        import winreg
        from adapters.solidworks.sw_detect import _addins_candidates
        result = _addins_candidates(2024)
        assert len(result) == 4
        hives = {r[0] for r in result}
        assert winreg.HKEY_LOCAL_MACHINE in hives
        assert winreg.HKEY_CURRENT_USER in hives

    def test_addins_candidates_contains_year(self):
        """_addins_candidates(2024) 返回的路径里包含年份字符串。"""
        from adapters.solidworks.sw_detect import _addins_candidates
        result = _addins_candidates(2024)
        year_paths = [p for _, p in result if "2024" in p]
        assert len(year_paths) == 2  # HKLM + HKCU 各一条

    def test_scan_returns_none_on_non_windows(self, monkeypatch):
        """非 Windows 平台（模拟）→ 返回 None。"""
        import adapters.solidworks.sw_detect as sd
        monkeypatch.setattr("sys.platform", "linux")
        result = sd._scan_all_addins_by_description()
        assert result is None

    def test_scan_returns_guid_when_description_matches(self, monkeypatch):
        """AddIns 下某 GUID 的 Description 含 'toolbox' → 返回该 GUID。"""
        import winreg
        import adapters.solidworks.sw_detect as sd

        sd._reset_cache()
        fake_guid = "{BBBBBBBB-CCCC-DDDD-EEEE-FFFFFFFFFFFF}"

        # mock detect_solidworks 返回已知 version_year
        monkeypatch.setattr(sd, "detect_solidworks",
                            lambda: sd.SwInfo(installed=True, version_year=2024))

        # mock _addins_candidates 只返回一条路径
        monkeypatch.setattr(sd, "_addins_candidates",
                            lambda year: [(winreg.HKEY_LOCAL_MACHINE,
                                           r"SOFTWARE\SolidWorks\AddIns")])

        # 用于记录 OpenKey 调用序列
        call_log = []

        class FakeRootKey:
            """模拟 HKLM\SOFTWARE\SolidWorks\AddIns，枚举出 fake_guid。"""
            def __enter__(self): return self
            def __exit__(self, *_): pass

        class FakeGuidKey:
            """模拟 fake_guid 子键，有 Description='SOLIDWORKS Toolbox'。"""
            def __enter__(self): return self
            def __exit__(self, *_): pass

        def fake_open_key(hive, path, *args):
            call_log.append(path)
            if path == r"SOFTWARE\SolidWorks\AddIns":
                return FakeRootKey()
            if fake_guid in path:
                return FakeGuidKey()
            raise FileNotFoundError(path)

        def fake_enum_key(key, i):
            if isinstance(key, FakeRootKey):
                if i == 0:
                    return fake_guid
                raise OSError
            raise OSError

        def fake_query_value_ex(key, name):
            if isinstance(key, FakeGuidKey) and name == "Description":
                return ("SOLIDWORKS Toolbox", 1)
            raise FileNotFoundError

        monkeypatch.setattr(winreg, "OpenKey", fake_open_key)
        monkeypatch.setattr(winreg, "EnumKey", fake_enum_key)
        monkeypatch.setattr(winreg, "QueryValueEx", fake_query_value_ex)
        monkeypatch.setattr(winreg, "KEY_READ", 1)

        result = sd._scan_all_addins_by_description()
        assert result == fake_guid


class TestScanAddinDllClsid:
    def test_no_install_dir_returns_none(self, monkeypatch):
        """install_dir 为空 → None。"""
        from adapters.solidworks import sw_detect
        sw_detect._reset_cache()
        monkeypatch.setattr(
            sw_detect, "detect_solidworks",
            lambda: sw_detect.SwInfo(installed=False, install_dir=""),
        )
        result = sw_detect._scan_addin_dll_clsid()
        assert result is None

    def test_no_dll_returns_none(self, tmp_path, monkeypatch):
        """AddIns/toolbox 和 AddIns/Toolbox 下无 dll → None。"""
        from adapters.solidworks import sw_detect
        sw_detect._reset_cache()
        # 有 AddIns/Toolbox 目录但里面没有 dll
        (tmp_path / "AddIns" / "Toolbox").mkdir(parents=True)
        monkeypatch.setattr(
            sw_detect, "detect_solidworks",
            lambda: sw_detect.SwInfo(installed=True, install_dir=str(tmp_path)),
        )
        result = sw_detect._scan_addin_dll_clsid()
        assert result is None

    @pytest.mark.skipif(sys.platform != "win32", reason="requires winreg")
    def test_returns_none_when_clsid_not_in_registry(self, tmp_path, monkeypatch):
        """DLL 存在但 HKCR\\CLSID 里没有匹配条目 → None。"""
        import winreg
        from adapters.solidworks import sw_detect
        sw_detect._reset_cache()

        addin_dir = tmp_path / "AddIns" / "Toolbox"
        addin_dir.mkdir(parents=True)
        (addin_dir / "SWToolbox.dll").write_bytes(b"MZ")

        monkeypatch.setattr(
            sw_detect, "detect_solidworks",
            lambda: sw_detect.SwInfo(installed=True, install_dir=str(tmp_path)),
        )
        # mock HKCR\CLSID → 打开即失败（无匹配）
        original_open = winreg.OpenKey

        def fake_open_key(hive, path, *args, **kwargs):
            if hive == winreg.HKEY_CLASSES_ROOT and path == "CLSID":
                raise FileNotFoundError("mock: no CLSID")
            return original_open(hive, path, *args, **kwargs)

        monkeypatch.setattr(winreg, "OpenKey", fake_open_key)
        result = sw_detect._scan_addin_dll_clsid()
        assert result is None
