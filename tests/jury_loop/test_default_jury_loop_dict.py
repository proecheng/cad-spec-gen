"""CP-7 Task 7.2.1：`DEFAULT_JURY_LOOP_DICT` 内嵌默认配置（approach A）。

pipeline_config.json 带 skip-worktree（per-machine local override）不能 stage 新字段，
故 enhance.jury_loop 默认配置以 module-level 常量内嵌进 tools.jury_loop.config。
cmd_enhance / enhance_consistency 加载时若 pipeline_config 缺该段则 fall back 至此默认。
"""
from __future__ import annotations

from tools.jury_loop.config import (
    DEFAULT_JURY_LOOP_DICT,
    JuryLoopConfig,
    load_jury_loop_config,
)


def test_default_dict_is_module_level_dict() -> None:
    """DEFAULT_JURY_LOOP_DICT 是 dict 实例。"""
    assert isinstance(DEFAULT_JURY_LOOP_DICT, dict)


def test_default_dict_loads_without_raising() -> None:
    """load_jury_loop_config(DEFAULT_JURY_LOOP_DICT) 不抛，返 JuryLoopConfig。"""
    cfg = load_jury_loop_config(DEFAULT_JURY_LOOP_DICT)
    assert isinstance(cfg, JuryLoopConfig)


def test_default_dict_enabled_true_cost_cap_1_5() -> None:
    """spec §4.1 零配置默认：enabled=True / cost_cap_usd=1.5。"""
    cfg = load_jury_loop_config(DEFAULT_JURY_LOOP_DICT)
    assert cfg.enabled is True
    assert cfg.cost_cap_usd == 1.5


def test_default_backend_kind_is_gemini_chat_image() -> None:
    """漂移 #3 修正：backend.kind 必须 ∈ BACKEND_REGISTRY 三 key 集，默认选 gemini_chat_image。"""
    # 硬编码 3 元素集合断言；不 import tools.jury_loop.backends 触发 lazy register 副作用。
    valid_kinds = {"gemini_chat_image", "openai_images_edit", "comfyui_workflow_cloud"}
    assert DEFAULT_JURY_LOOP_DICT["backend"]["kind"] in valid_kinds
    assert DEFAULT_JURY_LOOP_DICT["backend"]["kind"] == "gemini_chat_image"


def test_default_backend_has_5_required_keys() -> None:
    """BackendConfig 5 字段必须全在。"""
    assert set(DEFAULT_JURY_LOOP_DICT["backend"]) == {
        "kind", "base_url", "api_key_env", "model_name", "timeout_s",
    }


def test_default_advanced_keys_match_ADVANCED_KEYS() -> None:
    """advanced 5 key 必须对齐 _ADVANCED_KEYS（spec §4.1）。"""
    expected = {"threshold", "max_retries", "llm_fallback",
                "rule_table_path", "score_select_strategy"}
    assert set(DEFAULT_JURY_LOOP_DICT["advanced"]) == expected


def test_default_no_collision_between_top_and_advanced() -> None:
    """DRIFT-MAJOR-4：顶层 key 与 advanced key 无同名碰撞。"""
    top_keys = set(DEFAULT_JURY_LOOP_DICT.keys()) - {"backend", "advanced"}
    advanced_keys = set(DEFAULT_JURY_LOOP_DICT["advanced"].keys())
    assert not (top_keys & advanced_keys)
