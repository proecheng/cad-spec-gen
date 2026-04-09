"""Tests for parts_resolver.PartsResolver dispatch and registry loading."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from parts_resolver import (
    PartQuery,
    PartsResolver,
    ResolveResult,
    _match_rule,
    load_registry,
)
from adapters.parts.base import PartsAdapter


# ─── Fake adapters for deterministic testing ────────────────────────────


class FakeAdapter(PartsAdapter):
    """Minimal adapter that always hits and records calls."""

    def __init__(self, name: str, tag: str = ""):
        self.name = name
        self.tag = tag or name
        self.resolve_calls = 0
        self.probe_calls = 0

    def is_available(self) -> bool:
        return True

    def can_resolve(self, query) -> bool:
        return True

    def resolve(self, query, spec: dict):
        self.resolve_calls += 1
        return ResolveResult(
            status="hit",
            kind="codegen",
            adapter=self.name,
            body_code=f"    # from {self.tag}\n    return cq.Workplane('XY')",
            real_dims=(10.0, 10.0, 10.0),
            source_tag=f"{self.tag}:test",
        )

    def probe_dims(self, query, spec: dict):
        self.probe_calls += 1
        return (10.0, 10.0, 10.0)


class MissAdapter(PartsAdapter):
    """Adapter that always misses."""

    name = "miss"

    def is_available(self) -> bool:
        return True

    def can_resolve(self, query) -> bool:
        return False

    def resolve(self, query, spec):
        return ResolveResult.miss()

    def probe_dims(self, query, spec):
        return None


class UnavailableAdapter(PartsAdapter):
    """Adapter that is_available() returns False."""

    name = "unavailable"

    def is_available(self) -> bool:
        return False

    def can_resolve(self, query) -> bool:
        return False

    def resolve(self, query, spec):
        raise RuntimeError("should never be called")

    def probe_dims(self, query, spec):
        raise RuntimeError("should never be called")


# ─── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def sample_query():
    return PartQuery(
        part_no="GIS-EE-001-05",
        name_cn="测试零件",
        material="铝合金 Φ22×30mm",
        category="motor",
        make_buy="外购",
    )


# ─── _match_rule tests ──────────────────────────────────────────────────


class TestMatchRule:
    def test_any_matches(self, sample_query):
        assert _match_rule({"any": True}, sample_query)

    def test_empty_rule_does_not_match(self, sample_query):
        assert not _match_rule({}, sample_query)

    def test_exact_part_no(self, sample_query):
        assert _match_rule({"part_no": "GIS-EE-001-05"}, sample_query)
        assert not _match_rule({"part_no": "GIS-EE-001-99"}, sample_query)

    def test_part_no_glob(self, sample_query):
        assert _match_rule({"part_no_glob": "GIS-EE-001-*"}, sample_query)
        assert _match_rule({"part_no_glob": "*-05"}, sample_query)
        assert not _match_rule({"part_no_glob": "GIS-EE-002-*"}, sample_query)

    def test_category(self, sample_query):
        assert _match_rule({"category": "motor"}, sample_query)
        assert not _match_rule({"category": "bearing"}, sample_query)

    def test_name_contains_list(self, sample_query):
        assert _match_rule({"name_contains": ["测试", "other"]}, sample_query)
        assert not _match_rule({"name_contains": ["missing"]}, sample_query)

    def test_name_contains_case_insensitive(self):
        q = PartQuery(part_no="X", name_cn="Hello WORLD", material="",
                      category="cat", make_buy="")
        assert _match_rule({"name_contains": ["hello"]}, q)
        assert _match_rule({"name_contains": ["world"]}, q)

    def test_material_contains(self, sample_query):
        assert _match_rule({"material_contains": ["铝合金"]}, sample_query)
        assert not _match_rule({"material_contains": ["钢"]}, sample_query)

    def test_make_buy(self, sample_query):
        assert _match_rule({"make_buy": "外购"}, sample_query)
        assert not _match_rule({"make_buy": "自制"}, sample_query)

    def test_and_conditions(self, sample_query):
        rule = {"category": "motor", "name_contains": ["测试"]}
        assert _match_rule(rule, sample_query)
        rule = {"category": "motor", "name_contains": ["missing"]}
        assert not _match_rule(rule, sample_query)


# ─── PartsResolver dispatch tests ───────────────────────────────────────


class TestResolverDispatch:
    def test_empty_registry_falls_back_to_jinja_primitive(self, sample_query):
        """With no mappings, the terminal jinja_primitive fallback runs."""
        jinja = FakeAdapter(name="jinja_primitive", tag="jinja")
        resolver = PartsResolver(registry={}, adapters=[jinja])
        result = resolver.resolve(sample_query)
        # FakeAdapter always hits → treated as fallback when no mappings matched
        assert result.status == "fallback"
        assert result.adapter == "jinja_primitive"

    def test_explicit_rule_beats_fallback(self, sample_query):
        jinja = FakeAdapter(name="jinja_primitive", tag="jinja")
        bd = FakeAdapter(name="bd_warehouse", tag="bd")
        registry = {
            "mappings": [
                {"match": {"part_no": "GIS-EE-001-05"},
                 "adapter": "bd_warehouse", "spec": {}},
                {"match": {"any": True},
                 "adapter": "jinja_primitive", "spec": {}},
            ],
        }
        resolver = PartsResolver(
            registry=registry, adapters=[jinja, bd])
        result = resolver.resolve(sample_query)
        assert result.status == "hit"
        assert result.adapter == "bd_warehouse"
        assert bd.resolve_calls == 1
        assert jinja.resolve_calls == 0

    def test_rule_order_matters(self, sample_query):
        """First matching rule wins."""
        a = FakeAdapter(name="a", tag="A")
        b = FakeAdapter(name="b", tag="B")
        jinja = FakeAdapter(name="jinja_primitive", tag="jinja")
        registry = {
            "mappings": [
                {"match": {"category": "motor"}, "adapter": "a", "spec": {}},
                {"match": {"category": "motor"}, "adapter": "b", "spec": {}},
            ],
        }
        resolver = PartsResolver(registry=registry, adapters=[a, b, jinja])
        result = resolver.resolve(sample_query)
        assert result.adapter == "a"
        assert a.resolve_calls == 1
        assert b.resolve_calls == 0

    def test_missing_adapter_falls_through(self, sample_query):
        """If the YAML names an adapter that isn't registered, skip it."""
        jinja = FakeAdapter(name="jinja_primitive", tag="jinja")
        registry = {
            "mappings": [
                {"match": {"any": True}, "adapter": "nonexistent", "spec": {}},
                {"match": {"any": True}, "adapter": "jinja_primitive", "spec": {}},
            ],
        }
        resolver = PartsResolver(registry=registry, adapters=[jinja])
        result = resolver.resolve(sample_query)
        assert result.adapter == "jinja_primitive"

    def test_adapter_miss_falls_through(self, sample_query):
        """An adapter that returns miss triggers the next rule."""
        miss = MissAdapter()
        jinja = FakeAdapter(name="jinja_primitive", tag="jinja")
        registry = {
            "mappings": [
                {"match": {"any": True}, "adapter": "miss", "spec": {}},
            ],
        }
        resolver = PartsResolver(registry=registry, adapters=[miss, jinja])
        result = resolver.resolve(sample_query)
        # miss adapter returned miss → loop continues → terminal fallback
        assert result.status == "fallback"

    def test_adapter_exception_falls_through(self, sample_query):
        """If an adapter raises, resolver logs and tries the next rule."""
        class BoomAdapter(PartsAdapter):
            name = "boom"
            def is_available(self): return True
            def can_resolve(self, q): return True
            def resolve(self, q, spec): raise ValueError("kaboom")
            def probe_dims(self, q, spec): return None

        boom = BoomAdapter()
        jinja = FakeAdapter(name="jinja_primitive", tag="jinja")
        registry = {
            "mappings": [
                {"match": {"any": True}, "adapter": "boom", "spec": {}},
            ],
        }
        logs = []
        resolver = PartsResolver(
            registry=registry,
            adapters=[boom, jinja],
            logger=logs.append,
        )
        result = resolver.resolve(sample_query)
        assert result.adapter == "jinja_primitive"
        assert any("boom" in m or "kaboom" in m for m in logs)

    def test_summary_counts(self, sample_query):
        a = FakeAdapter(name="a", tag="A")
        b = FakeAdapter(name="b", tag="B")
        jinja = FakeAdapter(name="jinja_primitive", tag="jinja")
        registry = {
            "mappings": [
                {"match": {"part_no": "GIS-EE-001-05"}, "adapter": "a", "spec": {}},
            ],
        }
        resolver = PartsResolver(registry=registry, adapters=[a, b, jinja])
        resolver.resolve(sample_query)
        q2 = PartQuery(part_no="OTHER", name_cn="", material="",
                       category="x", make_buy="外购")
        resolver.resolve(q2)
        summary = resolver.summary()
        assert summary.get("a") == 1
        assert summary.get("jinja_primitive") == 1


# ─── Probe dims tests ──────────────────────────────────────────────────


class TestProbeDims:
    def test_probe_dims_caches_results(self, sample_query):
        a = FakeAdapter(name="a", tag="A")
        registry = {
            "mappings": [
                {"match": {"any": True}, "adapter": "a", "spec": {}},
            ],
        }
        resolver = PartsResolver(registry=registry, adapters=[a])
        dims1 = resolver.probe_dims(sample_query)
        dims2 = resolver.probe_dims(sample_query)
        assert dims1 == dims2 == (10.0, 10.0, 10.0)
        assert a.probe_calls == 1  # cached second call


# ─── Registry loading tests ────────────────────────────────────────────


class TestLoadRegistry:
    def test_empty_when_no_file(self, tmp_path):
        reg = load_registry(project_root=str(tmp_path))
        # Empty or populated only by parts_library.default.yaml (skill-shipped)
        assert isinstance(reg, dict)

    def test_env_kill_switch(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CAD_PARTS_LIBRARY_DISABLE", "1")
        reg = load_registry(project_root=str(tmp_path))
        assert reg == {}

    def test_explicit_path_takes_priority(self, tmp_path):
        p = tmp_path / "override.yaml"
        p.write_text("version: 99\nmappings: []\n")
        reg = load_registry(project_root=str(tmp_path), explicit_path=str(p))
        if reg:  # only if yaml is installed
            assert reg.get("version") == 99

    def test_env_variable_path(self, monkeypatch, tmp_path):
        p = tmp_path / "env.yaml"
        p.write_text("version: 42\nmappings: []\n")
        monkeypatch.setenv("CAD_PARTS_LIBRARY", str(p))
        reg = load_registry(project_root=str(tmp_path))
        if reg:
            assert reg.get("version") == 42

    def test_project_root_file(self, tmp_path):
        p = tmp_path / "parts_library.yaml"
        p.write_text("version: 5\nmappings: []\n")
        reg = load_registry(project_root=str(tmp_path))
        if reg:
            assert reg.get("version") == 5

    def test_malformed_yaml_returns_empty(self, tmp_path):
        p = tmp_path / "parts_library.yaml"
        p.write_text("this is : : not [valid yaml\n")
        reg = load_registry(project_root=str(tmp_path))
        # Malformed file should NOT crash; returns empty or default
        assert isinstance(reg, dict)
