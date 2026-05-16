"""tools/jury_loop/config.py 测试。

覆盖 spec §4.1 BackendConfig + JuryLoopConfig dataclass + load_jury_loop_config 加载器：
    - 最小 dict 解析（顶层默认 enabled=True / cost_cap_usd=1.5）
    - DRIFT-MAJOR-4 顶层与 advanced 同名 key 共存 → ValueError
    - api_key_env 指向不存在的环境变量 → warn 不抛
    - enabled=False 的合法 dataclass 形态
"""

from __future__ import annotations

import logging

import pytest

from tools.jury_loop.config import BackendConfig, JuryLoopConfig, load_jury_loop_config


def test_load_jury_loop_config_minimal_dict() -> None:
    """最小 dict 加载得到合法 JuryLoopConfig（用顶层默认 enabled=True / cost_cap_usd=1.5）。"""
    config = load_jury_loop_config(
        {
            "backend": {
                "kind": "fal_comfy",
                "base_url": "https://example.test",
                "api_key_env": "FAL_KEY",
                "model_name": "test-model",
                "timeout_s": 60,
            },
            "advanced": {
                "threshold": 75,
                "max_retries": 2,
                "llm_fallback": False,
                "rule_table_path": None,
                "score_select_strategy": "pick_max_jury",
            },
        }
    )
    assert isinstance(config, JuryLoopConfig)
    assert config.enabled is True
    assert config.cost_cap_usd == 1.5
    assert isinstance(config.backend, BackendConfig)
    assert config.backend.kind == "fal_comfy"
    assert config.backend.base_url == "https://example.test"
    assert config.backend.api_key_env == "FAL_KEY"
    assert config.backend.model_name == "test-model"
    assert config.backend.timeout_s == 60
    assert config.advanced["threshold"] == 75
    assert config.advanced["max_retries"] == 2
    assert config.advanced["llm_fallback"] is False
    assert config.advanced["rule_table_path"] is None
    assert config.advanced["score_select_strategy"] == "pick_max_jury"


def test_load_rejects_top_level_advanced_key_collision() -> None:
    """顶层与 advanced 同名 key (顶层 'threshold') → ValueError (DRIFT-MAJOR-4)。"""
    with pytest.raises(ValueError, match="顶层.*advanced.*共存"):
        load_jury_loop_config(
            {
                "threshold": 80,  # 顶层不应出现的 advanced 段 key
                "backend": {
                    "kind": "x",
                    "base_url": "x",
                    "api_key_env": "x",
                    "model_name": "x",
                    "timeout_s": 60,
                },
                "advanced": {
                    "threshold": 75,
                    "max_retries": 2,
                    "llm_fallback": False,
                    "rule_table_path": None,
                    "score_select_strategy": "pick_max_jury",
                },
            }
        )


def test_load_missing_api_key_env_warns_not_raise(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """api_key_env 指向不存在的环境变量 → warn 不抛（启动期柔性，首次 retry 时再 hard fail）。"""
    monkeypatch.delenv("NON_EXIST_KEY", raising=False)
    with caplog.at_level(logging.WARNING):
        config = load_jury_loop_config(
            {
                "backend": {
                    "kind": "x",
                    "base_url": "x",
                    "api_key_env": "NON_EXIST_KEY",
                    "model_name": "x",
                    "timeout_s": 60,
                },
                "advanced": {
                    "threshold": 75,
                    "max_retries": 2,
                    "llm_fallback": False,
                    "rule_table_path": None,
                    "score_select_strategy": "pick_max_jury",
                },
            }
        )
    assert config is not None  # 不抛
    assert any("NON_EXIST_KEY" in m for m in caplog.messages)


def test_jury_loop_config_disabled_form() -> None:
    """enabled=False 时其他字段仍合法 dataclass。"""
    config = load_jury_loop_config(
        {
            "enabled": False,
            "backend": {
                "kind": "x",
                "base_url": "x",
                "api_key_env": "x",
                "model_name": "x",
                "timeout_s": 60,
            },
            "advanced": {
                "threshold": 75,
                "max_retries": 2,
                "llm_fallback": False,
                "rule_table_path": None,
                "score_select_strategy": "pick_max_jury",
            },
        }
    )
    assert config.enabled is False
    assert config.backend.kind == "x"
