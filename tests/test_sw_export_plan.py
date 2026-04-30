import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from parts_resolver import PartQuery, PartsResolver
from tools.model_context import ModelProjectContext
from tools.sw_export_plan import build_sw_export_plan, write_sw_export_plan


class ExplodingAdapter:
    name = "sw_toolbox"

    def is_available(self):
        raise AssertionError("matching_rules must not inspect adapter availability")

    def resolve(self, query, spec):
        raise AssertionError("matching_rules must not resolve")


def test_matching_rules_filters_by_adapter_name_without_invoking_adapters():
    registry = {
        "mappings": [
            {
                "match": {"category": "bearing"},
                "adapter": "sw_toolbox",
                "spec": {"part_category": "bearing"},
            },
            {
                "match": {"category": "bearing"},
                "adapter": "step_pool",
                "spec": {"path": "ignored.step"},
            },
        ]
    }
    resolver = PartsResolver(registry=registry, adapters=[ExplodingAdapter()])
    query = PartQuery(
        part_no="P-001",
        name_cn="深沟球轴承 6205",
        material="GB/T 276 6205",
        category="bearing",
        make_buy="标准",
    )

    rules = resolver.matching_rules(query, adapter_name="sw_toolbox")

    assert len(rules) == 1
    assert rules[0]["adapter"] == "sw_toolbox"
    assert rules[0]["spec"] == {"part_category": "bearing"}


def test_matching_rules_skips_malformed_rule_without_raising():
    registry = {
        "mappings": [
            {
                "match": {"category": "bearing", "name_contains": [1]},
                "adapter": "sw_toolbox",
                "spec": {"part_category": "bearing"},
            }
        ]
    }
    resolver = PartsResolver(registry=registry)
    query = PartQuery(
        part_no="P-001",
        name_cn="深沟球轴承 6205",
        material="GB/T 276 6205",
        category="bearing",
        make_buy="标准",
    )

    assert resolver.matching_rules(query, adapter_name="sw_toolbox") == []


@dataclass
class FakeSwPart:
    standard: str
    subcategory: str
    sldprt_path: str
    filename: str
    target_config: str | None = None


class FakeSwAdapter:
    name = "sw_toolbox"

    def __init__(self, cache_root: Path):
        self.cache_root = cache_root
        self.find_calls = 0
        self.resolve_calls = 0

    def is_available(self):
        return True, None

    def find_sldprt(self, query, spec):
        self.find_calls += 1
        return (
            FakeSwPart(
                standard="GB",
                subcategory="bearing",
                sldprt_path=str(self.cache_root / "6205.sldprt"),
                filename="6205.sldprt",
            ),
            0.91,
        )

    def resolve(self, query, spec):
        self.resolve_calls += 1
        raise AssertionError("sw export plan must not call resolve")


def test_build_sw_export_plan_finds_candidate_without_resolve(tmp_path):
    cache_root = tmp_path / "cache"
    adapter = FakeSwAdapter(cache_root)
    registry = {
        "solidworks_toolbox": {"cache": str(cache_root)},
        "mappings": [
            {
                "match": {"category": "bearing"},
                "adapter": "sw_toolbox",
                "spec": {"standard": "GB", "part_category": "bearing"},
            }
        ],
    }
    context = ModelProjectContext.for_subsystem(
        "end_effector",
        project_root=tmp_path,
    )

    plan = build_sw_export_plan(
        [
            {
                "part_no": "P-001",
                "name_cn": "深沟球轴承 6205",
                "material": "GB/T 276 6205",
                "category": "bearing",
                "make_buy": "标准",
            }
        ],
        registry,
        context,
        adapter=adapter,
    )

    assert adapter.find_calls == 1
    assert adapter.resolve_calls == 0
    assert plan["schema_version"] == 1
    assert plan["project_root"] == str(tmp_path.resolve())
    assert plan["subsystem"] == "end_effector"
    assert len(plan["candidates"]) == 1
    candidate = plan["candidates"][0]
    expected_step_path = cache_root / "GB" / "bearing" / "6205_Default.step"
    assert candidate["action"] == "export"
    assert candidate["adapter"] == "sw_toolbox"
    assert candidate["config_match"] == "matched"
    assert candidate["config_name"] == "Default"
    assert candidate["cache_state"] == "missing"
    assert candidate["recommended_operation"] == "export"
    assert candidate["match_score"] == 0.91
    assert candidate["sldprt_path"].endswith("6205.sldprt")
    assert candidate["step_cache_path"] == str(expected_step_path)
    assert candidate["warnings"] == []


def test_build_sw_export_plan_with_target_config_reports_cache_path(tmp_path):
    cache_root = tmp_path / "cache"

    class ConfiguredFakeSwAdapter(FakeSwAdapter):
        def find_sldprt(self, query, spec):
            self.find_calls += 1
            return (
                FakeSwPart(
                    standard="GB",
                    subcategory="bearing",
                    sldprt_path=str(cache_root / "6205.sldprt"),
                    filename="6205.sldprt",
                    target_config="M6x20",
                ),
                0.91,
            )

    adapter = ConfiguredFakeSwAdapter(cache_root)
    registry = {
        "solidworks_toolbox": {"cache": str(cache_root)},
        "mappings": [
            {
                "match": {"category": "bearing"},
                "adapter": "sw_toolbox",
                "spec": {"standard": "GB", "part_category": "bearing"},
            }
        ],
    }
    step_path = cache_root / "GB" / "bearing" / "6205_M6x20.step"
    step_path.parent.mkdir(parents=True)
    step_path.write_text("cached", encoding="utf-8")
    context = ModelProjectContext.for_subsystem("end_effector", project_root=tmp_path)

    plan = build_sw_export_plan(
        [
            {
                "part_no": "P-001",
                "name_cn": "深沟球轴承 6205",
                "material": "GB/T 276 6205",
                "category": "bearing",
                "make_buy": "标准",
            }
        ],
        registry,
        context,
        adapter=adapter,
    )

    candidate = plan["candidates"][0]
    assert candidate["action"] == "reuse_cache"
    assert candidate["config_match"] == "matched"
    assert candidate["config_name"] == "M6x20"
    assert candidate["step_cache_path"] == str(step_path)
    assert candidate["cache_state"] == "present"
    assert candidate["recommended_operation"] == "reuse_cache"


def test_build_sw_export_plan_reuses_legacy_default_warmup_cache(tmp_path):
    cache_root = tmp_path / "cache"
    adapter = FakeSwAdapter(cache_root)
    registry = {
        "solidworks_toolbox": {"cache": str(cache_root)},
        "mappings": [
            {
                "match": {"category": "bearing"},
                "adapter": "sw_toolbox",
                "spec": {"standard": "GB", "part_category": "bearing"},
            }
        ],
    }
    legacy_step_path = cache_root / "GB" / "bearing" / "6205.step"
    legacy_step_path.parent.mkdir(parents=True)
    legacy_step_path.write_text("cached", encoding="utf-8")
    context = ModelProjectContext.for_subsystem("end_effector", project_root=tmp_path)

    plan = build_sw_export_plan(
        [
            {
                "part_no": "P-001",
                "name_cn": "深沟球轴承 6205",
                "material": "GB/T 276 6205",
                "category": "bearing",
                "make_buy": "标准",
            }
        ],
        registry,
        context,
        adapter=adapter,
    )

    candidate = plan["candidates"][0]
    assert candidate["action"] == "reuse_cache"
    assert candidate["config_name"] == "Default"
    assert candidate["step_cache_path"] == str(legacy_step_path)
    assert candidate["cache_state"] == "present"
    assert candidate["recommended_operation"] == "reuse_cache"


def test_build_sw_export_plan_no_candidate_has_stable_schema(tmp_path):
    adapter = FakeSwAdapter(tmp_path / "cache")
    registry = {
        "mappings": [
            {
                "match": {"category": "bearing"},
                "adapter": "sw_toolbox",
                "spec": {"part_category": "bearing"},
            }
        ],
    }
    context = ModelProjectContext.for_subsystem("end_effector", project_root=tmp_path)

    plan = build_sw_export_plan(
        [
            {
                "part_no": "P-002",
                "name_cn": "自制支架",
                "material": "铝合金",
                "category": "custom",
                "make_buy": "自制",
            }
        ],
        registry,
        context,
        adapter=adapter,
    )

    candidate = plan["candidates"][0]
    assert candidate["action"] == "no_candidate"
    assert candidate["adapter"] == "sw_toolbox"
    assert candidate["config_match"] == "n/a"
    assert candidate["config_name"] == ""


def test_write_sw_export_plan_writes_json_to_context_path(tmp_path):
    context = ModelProjectContext.for_subsystem("arm", project_root=tmp_path)
    plan = {
        "schema_version": 1,
        "generated_at": "2026-04-30T00:00:00Z",
        "project_root": str(tmp_path),
        "subsystem": "arm",
        "candidates": [],
    }

    path = write_sw_export_plan(plan, context)

    assert path == context.sw_export_plan_path
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8")) == plan


def test_cmd_sw_export_plan_missing_spec_returns_error(tmp_path, monkeypatch):
    import cad_pipeline

    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))
    args = SimpleNamespace(subsystem="__missing__", spec="", json=False)

    assert cad_pipeline.cmd_sw_export_plan(args) == 1
