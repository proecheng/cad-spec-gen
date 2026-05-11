"""rule_table 加载 + 安全 + 合并 + 范围校验测试。

Task 2.5.5：_clamp_param / lookup 接入 BACKEND_REGISTRY.known_params；
原静态 KNOWN_PARAMS 常量已删；测试改为通过 BACKEND_REGISTRY 验证。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.jury_loop.backends import BACKEND_REGISTRY
from tools.jury_loop.rule_table import (
    RuleTableLoadError,
    RuleTableLookupResult,
    RuleTableUnsupportedSchemaWarning,
    _clamp_param,
    load_rule_table,
    lookup,
)


class TestLoadBuiltin:
    def test_load_default_returns_table(self) -> None:
        table = load_rule_table()
        assert table.schema_version == 1
        assert len(table.rules) == 6
        assert "plastic_look" in table.tag_dictionary

    def test_safe_load_blocks_python_obj(self, tmp_path: Path) -> None:
        evil = tmp_path / "evil.yaml"
        evil.write_text("!!python/object/apply:os.system ['echo pwn']")
        with pytest.raises(RuleTableLoadError):
            load_rule_table(user_yaml_path=evil, project_root=tmp_path)

    def test_user_yaml_outside_project_root_rejects(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside.yaml"
        outside.write_text("schema_version: 1\nrules: []\n")
        with pytest.raises(RuleTableLoadError, match="rule_table_path 必须在项目目录内"):
            load_rule_table(user_yaml_path=outside, project_root=tmp_path / "elsewhere")


class TestSchemaValidation:
    def test_unknown_field_hard_fail(self, fixture_dir: Path) -> None:
        with pytest.raises(RuleTableLoadError, match="unknown field"):
            load_rule_table(
                user_yaml_path=fixture_dir / "user_rule_yaml_unknown_field.yaml",
                project_root=fixture_dir.parent.parent,
            )

    def test_wrong_schema_version_warns_falls_back(self, fixture_dir: Path) -> None:
        with pytest.warns(RuleTableUnsupportedSchemaWarning):
            table = load_rule_table(
                user_yaml_path=fixture_dir / "user_rule_yaml_wrong_schema.yaml",
                project_root=fixture_dir.parent.parent,
            )
        assert len(table.rules) == 6


class TestUserOverrideMerge:
    def test_user_yaml_replaces_same_id_keeps_position(self, fixture_dir: Path) -> None:
        table = load_rule_table(
            user_yaml_path=fixture_dir / "user_rule_yaml_valid.yaml",
            project_root=fixture_dir.parent.parent,
        )
        assert table.rules[0].id == "plastic_look_to_metallic"
        assert table.rules[0].prompt_addons == ("custom premium metallic finish",)

    def test_user_yaml_appends_new_rule_to_tail(self, fixture_dir: Path) -> None:
        table = load_rule_table(
            user_yaml_path=fixture_dir / "user_rule_yaml_valid.yaml",
            project_root=fixture_dir.parent.parent,
        )
        assert table.rules[-1].id == "user_custom_rule"

    def test_tag_dict_user_patterns_appended_not_replaced(self, fixture_dir: Path) -> None:
        table = load_rule_table(
            user_yaml_path=fixture_dir / "user_rule_yaml_valid.yaml",
            project_root=fixture_dir.parent.parent,
        )
        assert "plastic" in table.tag_dictionary["plastic_look"]
        assert "fake plastic" in table.tag_dictionary["plastic_look"]


class TestLookup:
    def test_single_tag_hit(self) -> None:
        table = load_rule_table()
        result = lookup(table, tags={"plastic_look"}, backend_kind="comfyui_workflow_cloud")
        assert "matte metallic finish, anodized aluminum" in result.prompt_addons
        assert result.param_overrides["denoise_strength"] == 0.45

    def test_multi_tag_hit_addons_dedup_preserve_order(self) -> None:
        table = load_rule_table()
        result = lookup(table, tags={"plastic_look", "flat_light"}, backend_kind="comfyui_workflow_cloud")
        assert result.prompt_addons[0] == "matte metallic finish, anodized aluminum"
        assert "studio softbox lighting from left, fill light from right" in result.prompt_addons

    def test_no_match_returns_empty(self) -> None:
        table = load_rule_table()
        result = lookup(table, tags={"unmapped_tag"}, backend_kind="gemini_chat_image")
        assert result.prompt_addons == []
        assert result.param_overrides == {}

    def test_param_overrides_per_backend_isolated(self) -> None:
        table = load_rule_table()
        result_gemini = lookup(table, tags={"plastic_look"}, backend_kind="gemini_chat_image")
        result_comfy = lookup(table, tags={"plastic_look"}, backend_kind="comfyui_workflow_cloud")
        assert "denoise_strength" not in result_gemini.param_overrides
        assert "temperature" not in result_comfy.param_overrides

    def test_unknown_backend_kind_raises(self) -> None:
        """plan line 1111：backend_kind 未注册到 BACKEND_REGISTRY 时 lookup 抛 ValueError。"""
        table = load_rule_table()
        with pytest.raises(ValueError, match="未注册到 BACKEND_REGISTRY"):
            lookup(table, tags={"plastic_look"}, backend_kind="unknown_kind_xyz")


class TestClampParamPerBackend:
    """plan line 1108-1110：_clamp_param 按 backend_kind 切分白名单 + 范围。"""

    def test_gemini_temperature_in_range_no_clamp(self) -> None:
        clamped, warning = _clamp_param("temperature", 1.0, "gemini_chat_image")
        assert clamped == 1.0
        assert warning is None

    def test_gemini_temperature_above_range_clamps(self) -> None:
        """gemini_chat_image temperature (0.0, 2.0)：3.5 → 2.0。"""
        clamped, warning = _clamp_param("temperature", 3.5, "gemini_chat_image")
        assert clamped == 2.0
        assert warning is not None
        assert "param_clamped" in warning

    def test_gemini_unknown_param_warns(self) -> None:
        """gemini_chat_image 不识别 canny_strength（属 comfyui）→ unknown_param。"""
        clamped, warning = _clamp_param("canny_strength", 0.5, "gemini_chat_image")
        assert clamped == 0.5
        assert warning is not None
        assert "unknown_param" in warning
        assert "gemini_chat_image" in warning

    def test_comfyui_canny_in_range(self) -> None:
        """plan line 1109：comfyui_workflow_cloud canny_strength 命中。"""
        clamped, warning = _clamp_param("canny_strength", 0.7, "comfyui_workflow_cloud")
        assert clamped == 0.7
        assert warning is None

    def test_comfyui_canny_above_range_clamps(self) -> None:
        clamped, warning = _clamp_param("canny_strength", 2.0, "comfyui_workflow_cloud")
        assert clamped == 1.0
        assert warning is not None

    def test_comfyui_steps_below_range_clamps(self) -> None:
        clamped, warning = _clamp_param("steps", 0, "comfyui_workflow_cloud")
        assert clamped == 1
        assert "param_clamped" in (warning or "")

    def test_openai_quality_string_no_clamp(self) -> None:
        """plan line 1110：openai_images_edit quality 字符串字段 (None, None) 仅存在性校验。"""
        clamped, warning = _clamp_param("quality", "high", "openai_images_edit")
        assert clamped == "high"
        assert warning is None

    def test_openai_style_string_no_clamp(self) -> None:
        clamped, warning = _clamp_param("style", "vivid", "openai_images_edit")
        assert clamped == "vivid"
        assert warning is None

    def test_openai_size_string_no_clamp(self) -> None:
        clamped, warning = _clamp_param("size", "1024x1024", "openai_images_edit")
        assert clamped == "1024x1024"
        assert warning is None

    def test_openai_n_in_range(self) -> None:
        clamped, warning = _clamp_param("n", 2, "openai_images_edit")
        assert clamped == 2
        assert warning is None

    def test_openai_n_above_range_clamps(self) -> None:
        clamped, warning = _clamp_param("n", 10, "openai_images_edit")
        assert clamped == 4
        assert warning is not None

    def test_unknown_backend_kind_raises_in_clamp(self) -> None:
        """_clamp_param 也守门 backend_kind 注册（lookup 已守门，此处兜底）。"""
        with pytest.raises(ValueError, match="未注册到 BACKEND_REGISTRY"):
            _clamp_param("temperature", 1.0, "unknown_kind_xyz")


class TestKnownParamsViaRegistry:
    """Task 2.5.5：原 KNOWN_PARAMS 静态常量已删；改为通过 BACKEND_REGISTRY 验证。"""

    def test_all_three_backends_have_known_params(self) -> None:
        for kind in ("gemini_chat_image", "openai_images_edit", "comfyui_workflow_cloud"):
            assert kind in BACKEND_REGISTRY
            kp = BACKEND_REGISTRY[kind].known_params
            assert isinstance(kp, dict)
            assert len(kp) > 0

    def test_comfyui_has_canny_strength_unit_range(self) -> None:
        kp = BACKEND_REGISTRY["comfyui_workflow_cloud"].known_params
        assert kp["canny_strength"] == (0.0, 1.0)
        assert kp["cfg_scale"] == (1.0, 30.0)


def test_rule_table_no_static_known_params_const() -> None:
    """Task 2.5.5：删除 rule_table.KNOWN_PARAMS 静态常量（CP-2 临时占位）。"""
    import tools.jury_loop.rule_table as rt

    assert not hasattr(rt, "KNOWN_PARAMS"), (
        "rule_table.KNOWN_PARAMS 应已被 Task 2.5.5 删除，"
        "改用 BACKEND_REGISTRY[backend_kind].known_params 动态查询"
    )
