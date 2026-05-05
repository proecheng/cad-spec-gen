from __future__ import annotations

import json
from pathlib import Path

import pytest

from adapters.parts.jinja_primitive_adapter import JinjaPrimitiveAdapter
from bom_parser import classify_part
from cad_spec_defaults import lookup_std_part_dims
from parts_resolver import PartQuery, default_resolver


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "common_model_family_admission.json"
)
RUNBOOK_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "runbooks"
    / "common-model-family-admission.md"
)

REQUIRED_SECTIONS = {
    "schema_version",
    "required_gates",
    "positive_cases",
    "negative_cases",
    "route_cases",
    "precedence_cases",
    "dimension_cases",
    "geometry_cases",
}
REQUIRED_GATES = {
    "explicit_category_and_family_intent",
    "broad_token_negative_examples",
    "nonterminal_default_route",
    "specific_template_precedence",
    "category_scoped_dimensions",
    "geometry_within_real_dims",
    "b_grade_reusable_metadata",
    "real_model_sources_before_default_templates",
    "no_project_exact_part_no_in_default_family_routes",
}


def _manifest() -> dict:
    assert MANIFEST_PATH.exists(), f"missing admission manifest: {MANIFEST_PATH}"
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _query(case: dict) -> PartQuery:
    return PartQuery(
        part_no=case.get("part_no", case["id"]),
        name_cn=case["name"],
        material=case.get("material", ""),
        category=case["category"],
        make_buy=case.get("make_buy", "外购"),
    )


def _assert_dict_contains(actual: dict, expected: dict) -> None:
    for key, value in expected.items():
        assert actual.get(key) == value


def test_admission_manifest_documents_required_sections_and_gates() -> None:
    manifest = _manifest()

    assert set(manifest) >= REQUIRED_SECTIONS
    assert manifest["schema_version"] == 1
    assert set(manifest["required_gates"]) >= REQUIRED_GATES
    for section in REQUIRED_SECTIONS - {"schema_version", "required_gates"}:
        assert manifest[section], f"{section} must contain representative cases"


def test_admission_runbook_mentions_manifest_and_gates() -> None:
    assert RUNBOOK_PATH.exists(), f"missing admission runbook: {RUNBOOK_PATH}"

    text = RUNBOOK_PATH.read_text(encoding="utf-8")
    assert "common_model_family_admission.json" in text
    assert "explicit_category_and_family_intent" in text
    assert "broad_token_negative_examples" in text
    assert "category_scoped_dimensions" in text
    assert "geometry_within_real_dims" in text
    assert "PARAMETRIC_TEMPLATE" in text
    assert "template_scope=reusable_part_family" in text


def test_admission_positive_cases_have_b_grade_reusable_metadata() -> None:
    for case in _manifest()["positive_cases"]:
        assert classify_part(case["name"], case.get("material", "")) == case["category"]

        result = JinjaPrimitiveAdapter().resolve(_query(case), {})

        assert result.status == "hit", case["id"]
        assert result.kind == "codegen", case["id"]
        assert result.geometry_source == "PARAMETRIC_TEMPLATE", case["id"]
        assert result.geometry_quality == "B", case["id"]
        assert result.requires_model_review is False, case["id"]
        assert result.source_tag == f"parametric_template:{case['template']}", case["id"]
        assert result.metadata["template"] == case["template"], case["id"]
        assert result.metadata["template_scope"] == "reusable_part_family", case["id"]
        assert tuple(result.real_dims or ()) == tuple(case["real_dims"]), case["id"]


def test_admission_negative_cases_do_not_hit_forbidden_templates() -> None:
    for case in _manifest()["negative_cases"]:
        assert classify_part(case["name"], case.get("material", "")) == case[
            "expected_category"
        ], case["id"]

        result = JinjaPrimitiveAdapter().resolve(_query(case), {})

        assert result.metadata.get("template") != case["forbidden_template"], case["id"]


def test_admission_route_cases_use_explicit_nonterminal_default_rules() -> None:
    resolver = default_resolver(project_root="__missing_project__")

    for case in _manifest()["route_cases"]:
        rules = resolver.matching_rules(
            _query(case),
            adapter_name=case["expected_adapter"],
        )

        assert rules, case["id"]
        assert rules[0]["match"] != {"any": True}, case["id"]
        assert rules[0]["match"].get("category") == case["category"], case["id"]
        _assert_dict_contains(rules[0]["match"], case.get("expected_match", {}))


def test_admission_route_aliases_keep_template_and_dims_consistent() -> None:
    resolver = default_resolver(project_root="__missing_project__")

    for case in _manifest()["route_cases"]:
        expected_template = case.get("expected_template")
        expected_dims = case.get("expected_dims")
        expected_real_dims = case.get("expected_real_dims")
        keywords = case.get("expected_match", {}).get("keyword_contains", [])
        if not (expected_template and keywords):
            continue

        for alias in keywords:
            alias_case = {
                **case,
                "id": f"{case['id']}::{alias}",
                "name": alias,
                "material": "",
            }
            query = _query(alias_case)
            rules = resolver.matching_rules(
                query,
                adapter_name=case["expected_adapter"],
            )
            result = JinjaPrimitiveAdapter().resolve(query, {})

            assert rules, alias_case["id"]
            assert rules[0]["match"] != {"any": True}, alias_case["id"]
            assert result.source_tag == (
                f"parametric_template:{expected_template}"
            ), alias_case["id"]
            if expected_real_dims:
                assert tuple(result.real_dims or ()) == tuple(
                    expected_real_dims
                ), alias_case["id"]
            if expected_dims:
                dims = lookup_std_part_dims(
                    alias,
                    "",
                    category=case["category"],
                )
                assert dims == expected_dims, alias_case["id"]


def test_admission_precedence_cases_keep_specific_routes_first() -> None:
    for case in _manifest()["precedence_cases"]:
        result = JinjaPrimitiveAdapter().resolve(_query(case), {})

        if "expected_template" in case:
            assert (
                result.source_tag == f"parametric_template:{case['expected_template']}"
            ), case["id"]

        if "first_adapter" in case:
            rules = default_resolver(project_root="__missing_project__").matching_rules(
                _query(case)
            )
            assert rules, case["id"]
            assert rules[0]["adapter"] == case["first_adapter"], case["id"]
            if "forbidden_first_adapter" in case:
                assert rules[0]["adapter"] != case["forbidden_first_adapter"], case["id"]


def test_admission_dimension_cases_are_category_scoped() -> None:
    for case in _manifest()["dimension_cases"]:
        result = lookup_std_part_dims(
            case["name"],
            case.get("material", ""),
            category=case["category"],
        )

        assert result == case["expected_dims"], case["id"]


def test_admission_geometry_cases_stay_within_reported_real_dims() -> None:
    import cadquery as cq

    for case in _manifest()["geometry_cases"]:
        result = JinjaPrimitiveAdapter().resolve(_query(case), {})
        namespace = {"cq": cq}

        exec(f"def _make():\n{result.body_code}\n", namespace)
        shape = namespace["_make"]()
        bbox = shape.val().BoundingBox()

        assert result.real_dims is not None, case["id"]
        assert result.metadata["template"] == case["template"], case["id"]
        for measured, expected in zip(
            (bbox.xlen, bbox.ylen, bbox.zlen),
            result.real_dims,
        ):
            assert measured <= expected + 1e-6, case["id"]
