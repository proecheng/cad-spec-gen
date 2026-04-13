"""SwToolboxAdapter 单元测试（v4 决策 #13/#22）。"""
from __future__ import annotations

import os
import sys
import unittest.mock as mock
import pytest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestIsAvailable:
    """v4 §5.3: 6 项检查全通过才 True。"""

    def test_non_windows_returns_false(self, monkeypatch):
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        monkeypatch.setattr(sys, "platform", "linux")
        a = SwToolboxAdapter()
        assert a.is_available() is False

    def test_sw_not_installed_returns_false(self, monkeypatch):
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_detect
        sw_detect._reset_cache()
        fake_info = sw_detect.SwInfo(installed=False)
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
        a = SwToolboxAdapter()
        assert a.is_available() is False

    def test_version_below_2024_returns_false(self, monkeypatch):
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_detect
        sw_detect._reset_cache()
        fake_info = sw_detect.SwInfo(
            installed=True, version_year=2023, pywin32_available=True,
            toolbox_dir="C:/fake", toolbox_addin_enabled=True,
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
        a = SwToolboxAdapter()
        assert a.is_available() is False

    def test_pywin32_missing_returns_false(self, monkeypatch):
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_detect
        sw_detect._reset_cache()
        fake_info = sw_detect.SwInfo(
            installed=True, version_year=2024, pywin32_available=False,
            toolbox_dir="C:/fake", toolbox_addin_enabled=True,
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
        a = SwToolboxAdapter()
        assert a.is_available() is False

    def test_toolbox_dir_missing_returns_false(self, monkeypatch):
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_detect
        sw_detect._reset_cache()
        fake_info = sw_detect.SwInfo(
            installed=True, version_year=2024, pywin32_available=True,
            toolbox_dir="", toolbox_addin_enabled=True,
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
        a = SwToolboxAdapter()
        assert a.is_available() is False

    def test_addin_disabled_returns_false(self, monkeypatch):
        """v4 决策 #13: Toolbox Add-In 未启用 → False。"""
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_detect
        sw_detect._reset_cache()
        fake_info = sw_detect.SwInfo(
            installed=True, version_year=2024, pywin32_available=True,
            toolbox_dir="C:/fake", toolbox_addin_enabled=False,
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
        a = SwToolboxAdapter()
        assert a.is_available() is False

    def test_unhealthy_session_returns_false(self, monkeypatch, tmp_path):
        """v4 决策 #22: SwComSession 熔断 → False。"""
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_detect, sw_com_session
        sw_detect._reset_cache()
        fake_info = sw_detect.SwInfo(
            installed=True, version_year=2024, pywin32_available=True,
            toolbox_dir=str(tmp_path), toolbox_addin_enabled=True,
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
        sw_com_session.reset_session()
        sess = sw_com_session.get_session()
        sess._unhealthy = True
        a = SwToolboxAdapter()
        assert a.is_available() is False

    def test_all_checks_pass_returns_true(self, monkeypatch, tmp_path):
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_detect, sw_com_session
        sw_detect._reset_cache()
        sw_com_session.reset_session()
        fake_info = sw_detect.SwInfo(
            installed=True, version_year=2024, pywin32_available=True,
            toolbox_dir=str(tmp_path), toolbox_addin_enabled=True,
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
        a = SwToolboxAdapter()
        assert a.is_available() is True


class TestCanResolve:
    def test_can_resolve_always_true(self):
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        a = SwToolboxAdapter()
        class Q:
            pass
        assert a.can_resolve(Q()) is True
