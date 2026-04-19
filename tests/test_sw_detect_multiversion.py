"""tests/test_sw_detect_multiversion.py — 多版本枚举三档优先级测试（Task 5）。

验证 _select_version 的三档优先级：env > preference.json > 最新已安装版本。
所有测试通过 mock _enumerate_registered_years 模拟注册表返回 [2022, 2024, 2026]，
并通过 mock _find_install_for_year 让被选中年份都"有 install_dir"。
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch


def _fake_install_lookup(year: int) -> tuple[str, str]:
    """为任意年份返回一个占位 install_dir + version 字符串。

    让 _find_install_for_year 总能返回成功，测试焦点就是 version_year 的选择逻辑。
    """
    return (f"C:\\fake\\SW{year}", f"{year - 1994}.0.0.0")


def test_env_var_overrides_preference_and_latest(monkeypatch):
    """env > preference.json > 最新版。"""
    monkeypatch.setenv("CAD_SPEC_GEN_SW_PREFERRED_YEAR", "2022")
    # mock 注册表枚举返回 [2026, 2024, 2022]（降序）
    with patch(
        "adapters.solidworks.sw_detect._enumerate_registered_years",
        return_value=[2026, 2024, 2022],
    ), patch(
        "adapters.solidworks.sw_detect._find_install_for_year",
        side_effect=lambda _winreg, year: _fake_install_lookup(year),
    ), patch(
        "adapters.solidworks.sw_detect._find_toolbox_dir",
        return_value="",
    ), patch(
        "adapters.solidworks.sw_detect._find_sldmat_files",
        return_value=[],
    ), patch(
        "adapters.solidworks.sw_detect._check_com_available",
        return_value=False,
    ), patch(
        "adapters.solidworks.sw_detect._check_toolbox_addin_enabled",
        return_value=False,
    ), patch(
        "adapters.solidworks.sw_detect._find_edition",
        return_value="unknown",
    ), patch(
        "adapters.solidworks.sw_detect._check_pywin32",
        return_value=False,
    ):
        if sys.platform != "win32":
            pytest.skip("sw_detect 非 Windows 平台直接短路 installed=False")
        from adapters.solidworks.sw_detect import detect_solidworks, reset_cache

        reset_cache()
        info = detect_solidworks()
        assert info.version_year == 2022  # env 强制


def test_preference_json_used_when_no_env(monkeypatch, tmp_path):
    """没有 env 时，preference.json 的值生效。"""
    monkeypatch.delenv("CAD_SPEC_GEN_SW_PREFERRED_YEAR", raising=False)
    pref = tmp_path / "sw_version_preference.json"
    pref.write_text('{"preferred_year": 2024}', encoding="utf-8")
    monkeypatch.setattr("sw_preflight.preference.PREFERENCE_PATH", pref)

    with patch(
        "adapters.solidworks.sw_detect._enumerate_registered_years",
        return_value=[2026, 2024, 2022],
    ), patch(
        "adapters.solidworks.sw_detect._find_install_for_year",
        side_effect=lambda _winreg, year: _fake_install_lookup(year),
    ), patch(
        "adapters.solidworks.sw_detect._find_toolbox_dir",
        return_value="",
    ), patch(
        "adapters.solidworks.sw_detect._find_sldmat_files",
        return_value=[],
    ), patch(
        "adapters.solidworks.sw_detect._check_com_available",
        return_value=False,
    ), patch(
        "adapters.solidworks.sw_detect._check_toolbox_addin_enabled",
        return_value=False,
    ), patch(
        "adapters.solidworks.sw_detect._find_edition",
        return_value="unknown",
    ), patch(
        "adapters.solidworks.sw_detect._check_pywin32",
        return_value=False,
    ):
        if sys.platform != "win32":
            pytest.skip("sw_detect 非 Windows 平台直接短路 installed=False")
        from adapters.solidworks.sw_detect import detect_solidworks, reset_cache

        reset_cache()
        info = detect_solidworks()
        assert info.version_year == 2024


def test_latest_default_when_no_env_no_preference(monkeypatch):
    """无 env 无 preference → 走最新版（枚举第一项）。"""
    monkeypatch.delenv("CAD_SPEC_GEN_SW_PREFERRED_YEAR", raising=False)
    # 让 read_preference 返回 None（模拟文件不存在或 preferred_year 未设）
    monkeypatch.setattr("sw_preflight.preference.read_preference", lambda: None)

    with patch(
        "adapters.solidworks.sw_detect._enumerate_registered_years",
        return_value=[2026, 2024, 2022],
    ), patch(
        "adapters.solidworks.sw_detect._find_install_for_year",
        side_effect=lambda _winreg, year: _fake_install_lookup(year),
    ), patch(
        "adapters.solidworks.sw_detect._find_toolbox_dir",
        return_value="",
    ), patch(
        "adapters.solidworks.sw_detect._find_sldmat_files",
        return_value=[],
    ), patch(
        "adapters.solidworks.sw_detect._check_com_available",
        return_value=False,
    ), patch(
        "adapters.solidworks.sw_detect._check_toolbox_addin_enabled",
        return_value=False,
    ), patch(
        "adapters.solidworks.sw_detect._find_edition",
        return_value="unknown",
    ), patch(
        "adapters.solidworks.sw_detect._check_pywin32",
        return_value=False,
    ):
        if sys.platform != "win32":
            pytest.skip("sw_detect 非 Windows 平台直接短路 installed=False")
        from adapters.solidworks.sw_detect import detect_solidworks, reset_cache

        reset_cache()
        info = detect_solidworks()
        assert info.version_year == 2026  # 降序第一项 = 最新
