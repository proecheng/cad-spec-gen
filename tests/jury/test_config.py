"""tools/jury/config.py 单元测试 — 18 case 覆盖 schema/profile/caps/估价表/base_url。

Task 4 ships 4 case (schema/active_id/empty/forward-compat). Tasks 5/6 add the rest.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.jury.config import (
    BUILTIN_MODEL_COST_USD,
    JuryCaps,
    JuryConfigError,
    JuryConfigSchemaError,
    JuryProfile,
    load_jury_config,
)


def _write_config(tmp_path: Path, payload: dict) -> Path:
    p = tmp_path / "cad_jury_config.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_schema_version_invalid_raises(tmp_path: Path) -> None:
    p = _write_config(tmp_path, {"schema_version": 0, "active_profile_id": "x", "profiles": []})
    with pytest.raises(JuryConfigSchemaError):
        load_jury_config(p)


def test_schema_version_2_forward_compat(tmp_path: Path, capsys) -> None:
    """v1 jury 见 schema_version=2 → 仅取 v1 字段 + stderr 警告，不 reject。"""
    p = _write_config(tmp_path, {
        "schema_version": 2,
        "active_profile_id": "main",
        "profiles": [{"id": "main", "kind": "openai_compat",
                      "api_base_url": "https://x/v1", "api_key": "dummy-not-a-real-key", "model": "gpt-4o"}],
        "v2_only_field": "ignored",
    })
    profile, caps = load_jury_config(p)
    assert profile.id == "main"
    captured = capsys.readouterr()
    assert "schema_version=2" in captured.err


def test_active_profile_id_not_in_profiles_raises(tmp_path: Path) -> None:
    p = _write_config(tmp_path, {
        "schema_version": 1, "active_profile_id": "missing",
        "profiles": [{"id": "x", "kind": "openai_compat",
                      "api_base_url": "https://x/v1", "api_key": "dummy-not-a-real-key", "model": "gpt-4o"}],
    })
    with pytest.raises(JuryConfigError):
        load_jury_config(p)


def test_empty_profiles_raises(tmp_path: Path) -> None:
    p = _write_config(tmp_path, {"schema_version": 1, "active_profile_id": "x", "profiles": []})
    with pytest.raises(JuryConfigError):
        load_jury_config(p)
