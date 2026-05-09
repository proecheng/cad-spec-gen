"""_jury_config_available helper 单测

spec: docs/superpowers/specs/2026-05-09-autopilot-with-jury-design.md v1.1 §6.2
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any, Callable

import pytest


# === fixture 工厂 ===

@pytest.fixture
def make_jury_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., Path]:
    """fixture 工厂：构造各种状态的 jury config 文件 + monkeypatch JURY_CONFIG_PATH

    state 枚举：ok / missing / corrupt / top_level_list / no_active_id / empty_active_id /
                orphan_id / no_profiles / empty_profiles
    """
    def _factory(state: str = "ok") -> Path:
        config_path = tmp_path / "cad_jury_config.json"

        if state == "ok":
            config_path.write_text(
                json.dumps({
                    "active_profile_id": "default",
                    "profiles": [{"id": "default", "kind": "openai_compat"}],
                }),
                encoding="utf-8",
            )
        elif state == "missing":
            pass
        elif state == "corrupt":
            config_path.write_bytes(b"{not json")
        elif state == "top_level_list":
            config_path.write_text(json.dumps([{"foo": "bar"}]), encoding="utf-8")
        elif state == "no_active_id":
            config_path.write_text(
                json.dumps({"profiles": [{"id": "default"}]}),
                encoding="utf-8",
            )
        elif state == "empty_active_id":
            config_path.write_text(
                json.dumps({"active_profile_id": "", "profiles": [{"id": "default"}]}),
                encoding="utf-8",
            )
        elif state == "orphan_id":
            config_path.write_text(
                json.dumps({
                    "active_profile_id": "typo_xyz",
                    "profiles": [{"id": "default"}, {"id": "backup"}],
                }),
                encoding="utf-8",
            )
        elif state == "no_profiles":
            config_path.write_text(
                json.dumps({"active_profile_id": "default"}),
                encoding="utf-8",
            )
        elif state == "empty_profiles":
            config_path.write_text(
                json.dumps({"active_profile_id": "default", "profiles": []}),
                encoding="utf-8",
            )
        else:
            raise ValueError(f"unknown state: {state}")

        monkeypatch.setattr("tools.photo3d_autopilot.JURY_CONFIG_PATH", config_path)
        return config_path

    return _factory


# === 11 helper 单测 ===

def test_jury_config_missing_returns_false(make_jury_config: Callable[..., Path]) -> None:
    make_jury_config(state="missing")
    from tools.photo3d_autopilot import _jury_config_available
    assert _jury_config_available() is False


def test_jury_config_valid_returns_true(make_jury_config: Callable[..., Path]) -> None:
    make_jury_config(state="ok")
    from tools.photo3d_autopilot import _jury_config_available
    assert _jury_config_available() is True


def test_jury_config_corrupt_json_returns_false(make_jury_config: Callable[..., Path]) -> None:
    make_jury_config(state="corrupt")
    from tools.photo3d_autopilot import _jury_config_available
    assert _jury_config_available() is False


def test_jury_config_top_level_not_dict_returns_false(make_jury_config: Callable[..., Path]) -> None:
    make_jury_config(state="top_level_list")
    from tools.photo3d_autopilot import _jury_config_available
    assert _jury_config_available() is False


def test_jury_config_missing_active_profile_id(make_jury_config: Callable[..., Path]) -> None:
    make_jury_config(state="no_active_id")
    from tools.photo3d_autopilot import _jury_config_available
    assert _jury_config_available() is False


def test_jury_config_empty_active_profile_id(make_jury_config: Callable[..., Path]) -> None:
    make_jury_config(state="empty_active_id")
    from tools.photo3d_autopilot import _jury_config_available
    assert _jury_config_available() is False


def test_jury_config_missing_profiles_list(make_jury_config: Callable[..., Path]) -> None:
    make_jury_config(state="no_profiles")
    from tools.photo3d_autopilot import _jury_config_available
    assert _jury_config_available() is False


def test_jury_config_empty_profiles_list(make_jury_config: Callable[..., Path]) -> None:
    make_jury_config(state="empty_profiles")
    from tools.photo3d_autopilot import _jury_config_available
    assert _jury_config_available() is False


def test_jury_config_active_profile_id_not_in_profiles(make_jury_config: Callable[..., Path]) -> None:
    make_jury_config(state="orphan_id")
    from tools.photo3d_autopilot import _jury_config_available
    assert _jury_config_available() is False


def test_jury_config_oserror_silent(
    make_jury_config: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """spec §5.1 — read_text OSError → False（不抛）"""
    make_jury_config(state="ok")
    real_read_text = Path.read_text

    def fake_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        if self.name == "cad_jury_config.json":
            raise OSError("permission denied")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)
    from tools.photo3d_autopilot import _jury_config_available
    assert _jury_config_available() is False


def test_jury_config_does_not_read_secrets() -> None:
    """spec §3.4 inv 3 — helper 实现源码不引用 api_key / base_url / model 字段名（防泄漏）"""
    from tools.photo3d_autopilot import _jury_config_available
    src = inspect.getsource(_jury_config_available)
    for forbidden in ("api_key", "base_url", "model", "cost_per_call_usd"):
        assert forbidden not in src, f"forbidden field {forbidden!r} read in _jury_config_available"
