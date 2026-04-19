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


def test_write_after_user_resolves_ambiguous(monkeypatch, tmp_path):
    """用户在 MULTIPLE_SW_VERSIONS_AMBIGUOUS 对话框里选 2024 后，应持久化到 preference.json。

    与 test_read_write_preference 等价但语义独立：前者覆盖往返契约，本测试
    锚定"诊断码 08 → 用户裁决 → write_preference"这条真实调用链，防止后续
    orchestrator 改动把写 preference 的入口漏掉。
    """
    from sw_preflight import preference

    monkeypatch.setattr(preference, "PREFERENCE_PATH", tmp_path / "pref.json")
    preference.write_preference(2024)
    assert preference.read_preference() == 2024
