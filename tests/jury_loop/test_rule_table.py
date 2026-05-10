"""rule_table 加载 + 安全 + 合并 + 范围校验测试。"""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.jury_loop.rule_table import (
    KNOWN_PARAMS,
    RuleTableLoadError,
    RuleTableLookupResult,
    RuleTableUnsupportedSchemaWarning,
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


class TestParamRangeClamp:
    def test_clamp_strength_to_unit_range(self) -> None:
        from tools.jury_loop.rule_table import _clamp_param

        clamped, warning = _clamp_param("canny_strength", 2.0)
        assert clamped == 1.0
        assert warning is not None
        assert "param_clamped" in warning

    def test_unknown_param_returns_orig_with_warning(self) -> None:
        from tools.jury_loop.rule_table import _clamp_param

        clamped, warning = _clamp_param("bogus_param", 99.0)
        assert clamped == 99.0
        assert warning is not None
        assert "unknown_param" in warning


class TestKnownParams:
    def test_known_params_const_has_strength_keys(self) -> None:
        assert "canny_strength" in KNOWN_PARAMS
        assert KNOWN_PARAMS["canny_strength"] == (0.0, 1.0)
        assert KNOWN_PARAMS["cfg_scale"] == (1.0, 30.0)
