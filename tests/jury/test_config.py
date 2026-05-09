"""tools/jury/config.py 单元测试 — 24 case 覆盖 schema/profile/caps/估价表/base_url（Tasks 4-6 累积）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.jury.config import (
    JuryConfigError,
    JuryConfigSchemaError,
    load_jury_config,
)


def _write_config(tmp_path: Path, payload: dict[str, object]) -> Path:
    p = tmp_path / "cad_jury_config.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_schema_version_invalid_raises(tmp_path: Path) -> None:
    p = _write_config(
        tmp_path, {"schema_version": 0, "active_profile_id": "x", "profiles": []}
    )
    with pytest.raises(JuryConfigSchemaError):
        load_jury_config(p)


def test_schema_version_2_forward_compat(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """v1 jury 见 schema_version=2 → 仅取 v1 字段 + stderr 警告，不 reject。"""
    p = _write_config(
        tmp_path,
        {
            "schema_version": 2,
            "active_profile_id": "main",
            "profiles": [
                {
                    "id": "main",
                    "kind": "openai_compat",
                    "api_base_url": "https://x/v1",
                    "api_key": "dummy-not-a-real-key",
                    "model": "gpt-4o",
                }
            ],
            "v2_only_field": "ignored",
        },
    )
    profile, caps = load_jury_config(p)
    assert profile.id == "main"
    captured = capsys.readouterr()
    assert "schema_version=2" in captured.err


def test_active_profile_id_not_in_profiles_raises(tmp_path: Path) -> None:
    p = _write_config(
        tmp_path,
        {
            "schema_version": 1,
            "active_profile_id": "missing",
            "profiles": [
                {
                    "id": "x",
                    "kind": "openai_compat",
                    "api_base_url": "https://x/v1",
                    "api_key": "dummy-not-a-real-key",
                    "model": "gpt-4o",
                }
            ],
        },
    )
    with pytest.raises(JuryConfigError):
        load_jury_config(p)


def test_empty_profiles_raises(tmp_path: Path) -> None:
    p = _write_config(
        tmp_path, {"schema_version": 1, "active_profile_id": "x", "profiles": []}
    )
    with pytest.raises(JuryConfigError):
        load_jury_config(p)


def test_kind_only_openai_compat(tmp_path: Path) -> None:
    p = _write_config(
        tmp_path,
        {
            "schema_version": 1,
            "active_profile_id": "x",
            "profiles": [
                {
                    "id": "x",
                    "kind": "anthropic_native",
                    "api_base_url": "https://x/v1",
                    "api_key": "dummy-not-a-real-key",
                    "model": "claude",
                }
            ],
        },
    )
    with pytest.raises(JuryConfigError):
        load_jury_config(p)


def test_api_base_url_must_be_https(tmp_path: Path) -> None:
    p = _write_config(
        tmp_path,
        {
            "schema_version": 1,
            "active_profile_id": "x",
            "profiles": [
                {
                    "id": "x",
                    "kind": "openai_compat",
                    "api_base_url": "http://x/v1",
                    "api_key": "dummy-not-a-real-key",
                    "model": "gpt-4o",
                }
            ],
        },
    )
    with pytest.raises(JuryConfigError):
        load_jury_config(p)


@pytest.mark.parametrize(
    "base_in, base_out",
    [
        ("https://api.openai.com/v1", "https://api.openai.com/v1"),
        ("https://api.openai.com", "https://api.openai.com/v1"),
        ("https://api.openai.com/v1/", "https://api.openai.com/v1"),
        ("https://api.openai.com/", "https://api.openai.com/v1"),
    ],
)
def test_base_url_smart_v1(tmp_path: Path, base_in: str, base_out: str) -> None:
    p = _write_config(
        tmp_path,
        {
            "schema_version": 1,
            "active_profile_id": "x",
            "profiles": [
                {
                    "id": "x",
                    "kind": "openai_compat",
                    "api_base_url": base_in,
                    "api_key": "dummy-not-a-real-key",
                    "model": "gpt-4o",
                }
            ],
        },
    )
    profile, _ = load_jury_config(p)
    assert profile.api_base_url == base_out


def test_api_key_strip_then_nonempty(tmp_path: Path) -> None:
    p = _write_config(
        tmp_path,
        {
            "schema_version": 1,
            "active_profile_id": "x",
            "profiles": [
                {
                    "id": "x",
                    "kind": "openai_compat",
                    "api_base_url": "https://x/v1",
                    "api_key": "   ",
                    "model": "gpt-4o",
                }
            ],
        },
    )
    with pytest.raises(JuryConfigError):
        load_jury_config(p)


def test_model_strip_then_nonempty(tmp_path: Path) -> None:
    p = _write_config(
        tmp_path,
        {
            "schema_version": 1,
            "active_profile_id": "x",
            "profiles": [
                {
                    "id": "x",
                    "kind": "openai_compat",
                    "api_base_url": "https://x/v1",
                    "api_key": "dummy",
                    "model": "",
                }
            ],
        },
    )
    with pytest.raises(JuryConfigError):
        load_jury_config(p)


def test_profile_id_regex_starts_with_dash_rejected(tmp_path: Path) -> None:
    p = _write_config(
        tmp_path,
        {
            "schema_version": 1,
            "active_profile_id": "-foo",
            "profiles": [
                {
                    "id": "-foo",
                    "kind": "openai_compat",
                    "api_base_url": "https://x/v1",
                    "api_key": "dummy",
                    "model": "gpt-4o",
                }
            ],
        },
    )
    with pytest.raises(JuryConfigError):
        load_jury_config(p)


def test_profile_id_too_long_rejected(tmp_path: Path) -> None:
    long_id = "a" * 65
    p = _write_config(
        tmp_path,
        {
            "schema_version": 1,
            "active_profile_id": long_id,
            "profiles": [
                {
                    "id": long_id,
                    "kind": "openai_compat",
                    "api_base_url": "https://x/v1",
                    "api_key": "dummy",
                    "model": "gpt-4o",
                }
            ],
        },
    )
    with pytest.raises(JuryConfigError):
        load_jury_config(p)


def test_profile_id_unicode_rejected(tmp_path: Path) -> None:
    p = _write_config(
        tmp_path,
        {
            "schema_version": 1,
            "active_profile_id": "你好",
            "profiles": [
                {
                    "id": "你好",
                    "kind": "openai_compat",
                    "api_base_url": "https://x/v1",
                    "api_key": "dummy",
                    "model": "gpt-4o",
                }
            ],
        },
    )
    with pytest.raises(JuryConfigError):
        load_jury_config(p)


def test_profile_id_duplicate_rejected(tmp_path: Path) -> None:
    p = _write_config(
        tmp_path,
        {
            "schema_version": 1,
            "active_profile_id": "x",
            "profiles": [
                {
                    "id": "x",
                    "kind": "openai_compat",
                    "api_base_url": "https://x/v1",
                    "api_key": "k1",
                    "model": "m1",
                },
                {
                    "id": "x",
                    "kind": "openai_compat",
                    "api_base_url": "https://y/v1",
                    "api_key": "k2",
                    "model": "m2",
                },
            ],
        },
    )
    with pytest.raises(JuryConfigError):
        load_jury_config(p)


def test_api_base_url_empty_hostname_rejected(tmp_path: Path) -> None:
    p = _write_config(
        tmp_path,
        {
            "schema_version": 1,
            "active_profile_id": "x",
            "profiles": [
                {
                    "id": "x",
                    "kind": "openai_compat",
                    "api_base_url": "https:///v1",
                    "api_key": "dummy",
                    "model": "gpt-4o",
                }
            ],
        },
    )
    with pytest.raises(JuryConfigError):
        load_jury_config(p)


def test_cost_lookup_gpt_4o() -> None:
    from tools.jury.config import lookup_builtin_cost

    assert lookup_builtin_cost("gpt-4o") == 0.020
    assert lookup_builtin_cost("gpt-4o-mini") == 0.020  # 前缀命中
    assert lookup_builtin_cost("gpt-4o-2024-12-01") == 0.020


def test_cost_lookup_table_order_first_match() -> None:
    """按表中行序首次命中：gpt-4-turbo 在 gpt-4o 后所以 gpt-4-turbo-2024-12 命中 gpt-4-turbo*"""
    from tools.jury.config import lookup_builtin_cost

    assert lookup_builtin_cost("gpt-4-turbo-2024-12") == 0.030


def test_cost_lookup_unknown_returns_none() -> None:
    from tools.jury.config import lookup_builtin_cost

    assert lookup_builtin_cost("llama-99") is None


def test_cost_per_call_usd_explicit_zero_accepted(tmp_path: Path) -> None:
    p = _write_config(
        tmp_path,
        {
            "schema_version": 1,
            "active_profile_id": "x",
            "profiles": [
                {
                    "id": "x",
                    "kind": "openai_compat",
                    "api_base_url": "https://x/v1",
                    "api_key": "dummy",
                    "model": "free-model",
                    "cost_per_call_usd": 0,
                }
            ],
        },
    )
    profile, _ = load_jury_config(p)
    assert profile.cost_per_call_usd == 0.0


def test_cost_per_call_usd_negative_rejected(tmp_path: Path) -> None:
    p = _write_config(
        tmp_path,
        {
            "schema_version": 1,
            "active_profile_id": "x",
            "profiles": [
                {
                    "id": "x",
                    "kind": "openai_compat",
                    "api_base_url": "https://x/v1",
                    "api_key": "dummy",
                    "model": "x",
                    "cost_per_call_usd": -1,
                }
            ],
        },
    )
    with pytest.raises(JuryConfigError):
        load_jury_config(p)


def test_cost_per_call_usd_nan_rejected(tmp_path: Path) -> None:
    p = _write_config(
        tmp_path,
        {
            "schema_version": 1,
            "active_profile_id": "x",
            "profiles": [
                {
                    "id": "x",
                    "kind": "openai_compat",
                    "api_base_url": "https://x/v1",
                    "api_key": "dummy",
                    "model": "x",
                    "cost_per_call_usd": float("nan"),
                }
            ],
        },
    )
    with pytest.raises(JuryConfigError):
        load_jury_config(p)


def test_caps_defaults(tmp_path: Path) -> None:
    p = _write_config(
        tmp_path,
        {
            "schema_version": 1,
            "active_profile_id": "x",
            "profiles": [
                {
                    "id": "x",
                    "kind": "openai_compat",
                    "api_base_url": "https://x/v1",
                    "api_key": "dummy",
                    "model": "gpt-4o",
                }
            ],
        },
    )
    _, caps = load_jury_config(p)
    assert caps.max_image_bytes == 8 * 1024 * 1024
    assert caps.max_n_views == 32
    assert caps.min_photoreal_score == 60


def test_caps_max_n_views_out_of_range_rejected(tmp_path: Path) -> None:
    p = _write_config(
        tmp_path,
        {
            "schema_version": 1,
            "active_profile_id": "x",
            "max_n_views": 0,
            "profiles": [
                {
                    "id": "x",
                    "kind": "openai_compat",
                    "api_base_url": "https://x/v1",
                    "api_key": "dummy",
                    "model": "gpt-4o",
                }
            ],
        },
    )
    with pytest.raises(JuryConfigSchemaError):
        load_jury_config(p)


def test_caps_min_photoreal_score_out_of_range_rejected(tmp_path: Path) -> None:
    p = _write_config(
        tmp_path,
        {
            "schema_version": 1,
            "active_profile_id": "x",
            "min_photoreal_score": 101,
            "profiles": [
                {
                    "id": "x",
                    "kind": "openai_compat",
                    "api_base_url": "https://x/v1",
                    "api_key": "dummy",
                    "model": "gpt-4o",
                }
            ],
        },
    )
    with pytest.raises(JuryConfigSchemaError):
        load_jury_config(p)
