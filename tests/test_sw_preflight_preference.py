"""tests/test_sw_preflight_preference.py — sw_preflight.preference 读写测试（Task 5）。"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_read_write_preference(tmp_path, monkeypatch):
    """验证 read_preference / write_preference 往返正确，且未设时返回 None。"""
    from sw_preflight import preference

    monkeypatch.setattr(preference, "PREFERENCE_PATH", tmp_path / "pref.json")
    assert preference.read_preference() is None
    preference.write_preference(2024)
    assert preference.read_preference() == 2024
