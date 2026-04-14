"""check_env.py 对 SW toolbox_addin_enabled 字段的 UX 回归测试。"""

from __future__ import annotations

import os
import sys
import importlib.util

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_detect_environment_includes_toolbox_addin_flag(monkeypatch):
    """enhancements.solidworks 应含 toolbox_addin_enabled 字段。"""
    from adapters.solidworks import sw_detect

    sw_detect._reset_cache()
    fake_info = sw_detect.SwInfo(
        installed=True,
        version_year=2024,
        version="2024.0",
        pywin32_available=True,
        com_available=True,
        toolbox_addin_enabled=True,
    )
    monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)

    # 动态 import check_env（位于 tools/ 下）
    check_env_path = os.path.join(
        os.path.dirname(__file__), "..", "tools", "hybrid_render", "check_env.py"
    )
    spec = importlib.util.spec_from_file_location("check_env", check_env_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    result = mod.detect_environment()
    sw_enh = result.get("enhancements", {}).get("solidworks", {})
    assert "toolbox_addin_enabled" in sw_enh
    assert sw_enh["toolbox_addin_enabled"] is True


def test_detect_environment_reports_addin_disabled(monkeypatch):
    """Add-In 未启用时 toolbox_addin_enabled=False 字段应被正确传递。"""
    from adapters.solidworks import sw_detect

    sw_detect._reset_cache()
    fake_info = sw_detect.SwInfo(
        installed=True,
        version_year=2024,
        version="2024.0",
        pywin32_available=True,
        com_available=True,
        toolbox_addin_enabled=False,  # 关键：未启用
    )
    monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)

    check_env_path = os.path.join(
        os.path.dirname(__file__), "..", "tools", "hybrid_render", "check_env.py"
    )
    spec = importlib.util.spec_from_file_location("check_env", check_env_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    result = mod.detect_environment()
    sw_enh = result["enhancements"]["solidworks"]
    assert sw_enh["toolbox_addin_enabled"] is False
    assert sw_enh["path_b"] is True  # 版本 + COM + pywin32 都满足
