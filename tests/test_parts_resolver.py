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

    def is_available(self) -> tuple[bool, None]:
        return True, None

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


class ReadyJinjaTemplateAdapter(FakeAdapter):
    """Terminal jinja adapter that returns reviewed B-grade template geometry."""

    def __init__(self):
        super().__init__(name="jinja_primitive", tag="parametric_template")

    def resolve(self, query, spec: dict):
        self.resolve_calls += 1
        return ResolveResult(
            status="hit",
            kind="codegen",
            adapter=self.name,
            body_code="    return cq.Workplane('XY').box(20, 20, 3)",
            real_dims=(20.0, 20.0, 3.0),
            source_tag="parametric_template:test_template",
            geometry_source="PARAMETRIC_TEMPLATE",
            geometry_quality="B",
            requires_model_review=False,
        )


class MissAdapter(PartsAdapter):
    """Adapter that always misses."""

    name = "miss"

    def is_available(self) -> tuple[bool, None]:
        return True, None

    def can_resolve(self, query) -> bool:
        return False

    def resolve(self, query, spec):
        return ResolveResult.miss()

    def probe_dims(self, query, spec):
        return None


class UnavailableAdapter(PartsAdapter):
    """Adapter that is_available() returns False."""

    name = "unavailable"

    def is_available(self) -> tuple[bool, None]:
        return False, None

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

    def test_terminal_ready_jinja_template_remains_hit(self, sample_query):
        """Routing through the terminal jinja adapter should not force a
        reviewed B-grade parametric template back into fallback semantics."""
        jinja = ReadyJinjaTemplateAdapter()
        resolver = PartsResolver(registry={}, adapters=[jinja])

        result = resolver.resolve(sample_query)

        assert result.status == "hit"
        assert result.adapter == "jinja_primitive"
        assert result.geometry_source == "PARAMETRIC_TEMPLATE"
        assert result.geometry_quality == "B"
        assert result.requires_model_review is False
        assert resolver.geometry_decisions()[0]["attempted_adapters"] == [
            "jinja_primitive(hit)"
        ]

    def test_adapter_exception_falls_through(self, sample_query):
        """If an adapter raises, resolver logs and tries the next rule."""
        class BoomAdapter(PartsAdapter):
            name = "boom"
            def is_available(self): return True, None
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

    def test_needs_user_decision_propagates_to_codegen(self, sample_query):
        """Broker user decisions are control flow, not adapter crashes."""
        from adapters.solidworks.sw_config_broker import NeedsUserDecision

        record = {"part_no": sample_query.part_no}

        class AmbiguousAdapter(PartsAdapter):
            name = "ambiguous"
            def is_available(self): return True, None
            def can_resolve(self, q): return True
            def resolve(self, q, spec):
                raise NeedsUserDecision(
                    part_no=q.part_no,
                    subsystem="default",
                    pending_record=record,
                )
            def probe_dims(self, q, spec): return None

        resolver = PartsResolver(
            registry={
                "mappings": [
                    {"match": {"any": True}, "adapter": "ambiguous", "spec": {}},
                ],
            },
            adapters=[AmbiguousAdapter(), FakeAdapter(name="jinja_primitive", tag="jinja")],
        )

        with pytest.raises(NeedsUserDecision) as exc_info:
            resolver.resolve(sample_query)
        assert exc_info.value.pending_record is record

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

    def test_resolve_forwards_mode_to_mode_aware_adapter(self, sample_query):
        class ModeAwareAdapter(FakeAdapter):
            def __init__(self):
                super().__init__(name="mode_aware", tag="mode")
                self.modes = []

            def resolve(self, query, spec: dict, mode="codegen"):
                self.modes.append(mode)
                return super().resolve(query, spec)

        adapter = ModeAwareAdapter()
        resolver = PartsResolver(
            registry={
                "mappings": [
                    {"match": {"any": True}, "adapter": "mode_aware", "spec": {}}
                ]
            },
            adapters=[adapter],
        )
        resolver.resolve(sample_query, mode="inspect")
        assert adapter.modes == ["inspect"]

    def test_resolve_result_has_geometry_quality_defaults(self, sample_query):
        jinja = FakeAdapter(name="jinja_primitive", tag="jinja")
        resolver = PartsResolver(registry={}, adapters=[jinja])
        result = resolver.resolve(sample_query)
        assert result.geometry_source == "JINJA_PRIMITIVE"
        assert result.geometry_quality == "D"
        assert result.requires_model_review is True

    def test_step_pool_file_template_resolves_through_resolver(self, tmp_path):
        """Resolver should pass file_template rules into StepPoolAdapter."""
        from adapters.parts.step_pool_adapter import StepPoolAdapter

        step_dir = tmp_path / "std_parts" / "vendor"
        step_dir.mkdir(parents=True)
        (step_dir / "mini_motor.step").write_text(
            "ISO-10303-21;\nEND-ISO-10303-21;\n",
            encoding="utf-8",
        )
        query = PartQuery(
            part_no="P-001",
            name_cn="Mini Motor",
            material="",
            category="motor",
            make_buy="外购",
        )
        resolver = PartsResolver(
            project_root=str(tmp_path),
            registry={
                "mappings": [
                    {
                        "match": {"category": "motor"},
                        "adapter": "step_pool",
                        "spec": {"file_template": "vendor/{normalize(name)}.step"},
                    },
                ],
            },
            adapters=[StepPoolAdapter(project_root=str(tmp_path), config={"root": "std_parts/"})],
        )
        result = resolver.resolve(query)
        assert result.status == "hit"
        assert result.kind == "step_import"
        assert result.adapter == "step_pool"
        assert result.step_path == "std_parts/vendor/mini_motor.step"
        assert result.geometry_source == "REAL_STEP"

    def test_cache_uri_step_path_validates_against_shared_cache(
        self, tmp_path, monkeypatch, sample_query
    ):
        cache_root = tmp_path / "cache"
        step_path = cache_root / "maxon" / "ecx_22l.step"
        step_path.parent.mkdir(parents=True)
        step_path.write_bytes(b"solid placeholder")
        monkeypatch.setenv("CAD_SPEC_GEN_STEP_CACHE", str(cache_root))

        resolver = PartsResolver(registry={}, adapters=[])
        result = ResolveResult(
            status="hit",
            kind="step_import",
            adapter="step_pool",
            step_path="cache://maxon/ecx_22l.step",
            source_tag="STEP:cache://maxon/ecx_22l.step",
        )

        resolver._enrich_result_geometry(result, sample_query)

        assert result.path_kind == "shared_cache"
        assert result.validated is True
        assert result.hash is not None


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
    @pytest.fixture(autouse=True)
    def _isolate_env(self, monkeypatch):
        """Clear inherited parts-library env vars so the regression CI job
        (which sets CAD_PARTS_LIBRARY_DISABLE=1 globally) doesn't poison
        these tests. Individual tests that *want* a particular env state
        can re-set it via monkeypatch and override this autouse fixture.
        """
        monkeypatch.delenv("CAD_PARTS_LIBRARY_DISABLE", raising=False)
        monkeypatch.delenv("CAD_PARTS_LIBRARY", raising=False)

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


# ─── extends: default merge tests ──────────────────────────────────────


class TestExtendsDefault:
    """Tests for the `extends: default` inheritance mechanism added in
    v2.8.1. Project YAML can be sparse and inherit category-driven rules
    from parts_library.default.yaml without copy-paste."""

    @pytest.fixture(autouse=True)
    def _isolate_env(self, monkeypatch):
        """Same isolation rationale as TestLoadRegistry: regression CI sets
        CAD_PARTS_LIBRARY_DISABLE=1 globally, which would short-circuit
        load_registry() to {} before any extends merging can occur."""
        monkeypatch.delenv("CAD_PARTS_LIBRARY_DISABLE", raising=False)
        monkeypatch.delenv("CAD_PARTS_LIBRARY", raising=False)

    def test_project_mappings_prepended_to_default(self, tmp_path):
        """Project mappings come BEFORE default mappings in dispatch order."""
        try:
            import yaml  # noqa: F401
        except ImportError:
            pytest.skip("PyYAML not installed")

        p = tmp_path / "parts_library.yaml"
        p.write_text(
            "extends: default\n"
            "mappings:\n"
            "  - match: {part_no: \"X-001\"}\n"
            "    adapter: bd_warehouse\n"
            "    spec: {class: SingleRowDeepGrooveBallBearing}\n"
        )
        reg = load_registry(project_root=str(tmp_path))
        if not reg:
            pytest.skip("default registry not on disk")
        mappings = reg.get("mappings", [])
        # Project's X-001 rule must be the first one
        assert mappings[0]["match"]["part_no"] == "X-001"
        # Default rules should still be present after the project rule
        assert len(mappings) > 1
        # The terminal {any: true} fallback from default must still be last
        assert mappings[-1]["match"].get("any") is True

    def test_extends_drops_extends_key_from_result(self, tmp_path):
        """The synthetic `extends` key should not appear in the merged dict."""
        try:
            import yaml  # noqa: F401
        except ImportError:
            pytest.skip("PyYAML not installed")

        p = tmp_path / "parts_library.yaml"
        p.write_text("extends: default\nmappings: []\n")
        reg = load_registry(project_root=str(tmp_path))
        if not reg:
            pytest.skip("default registry not on disk")
        assert "extends" not in reg

    def test_extends_top_level_keys_override_default(self, tmp_path):
        """Project top-level keys (e.g. step_pool, version) override default."""
        try:
            import yaml  # noqa: F401
        except ImportError:
            pytest.skip("PyYAML not installed")

        p = tmp_path / "parts_library.yaml"
        p.write_text(
            "extends: default\n"
            "version: 99\n"
            "step_pool:\n"
            "  root: my_custom_pool/\n"
            "mappings: []\n"
        )
        reg = load_registry(project_root=str(tmp_path))
        if not reg:
            pytest.skip("default registry not on disk")
        assert reg.get("version") == 99
        assert reg.get("step_pool", {}).get("root") == "my_custom_pool/"

    def test_extends_unknown_value_falls_back_to_project_only(self, tmp_path):
        """`extends: foo` (unknown value) is logged and ignored gracefully."""
        try:
            import yaml  # noqa: F401
        except ImportError:
            pytest.skip("PyYAML not installed")

        p = tmp_path / "parts_library.yaml"
        p.write_text(
            "extends: nonexistent_keyword\n"
            "version: 7\n"
            "mappings:\n"
            "  - match: {any: true}\n"
            "    adapter: jinja_primitive\n"
        )
        logs = []
        reg = load_registry(project_root=str(tmp_path), logger=logs.append)
        # Project data should still be loaded
        assert reg.get("version") == 7
        # And a log should mention the unknown extends value
        assert any("unknown extends" in m for m in logs)

    def test_no_extends_behaves_like_pre_v2_8_1(self, tmp_path):
        """Without `extends:`, project YAML completely replaces default
        (legacy behavior preserved for backwards compat)."""
        try:
            import yaml  # noqa: F401
        except ImportError:
            pytest.skip("PyYAML not installed")

        p = tmp_path / "parts_library.yaml"
        p.write_text(
            "version: 1\n"
            "mappings:\n"
            "  - match: {any: true}\n"
            "    adapter: jinja_primitive\n"
        )
        reg = load_registry(project_root=str(tmp_path))
        if not reg:
            pytest.skip("PyYAML not installed")
        # Only the project's single rule should be present
        assert len(reg.get("mappings", [])) == 1
        assert reg.get("version") == 1

    def test_kill_switch_overrides_extends(self, monkeypatch, tmp_path):
        """CAD_PARTS_LIBRARY_DISABLE=1 must short-circuit before reading any
        YAML, including projects with extends: default."""
        try:
            import yaml  # noqa: F401
        except ImportError:
            pytest.skip("PyYAML not installed")

        p = tmp_path / "parts_library.yaml"
        p.write_text("extends: default\nmappings: []\n")
        monkeypatch.setenv("CAD_PARTS_LIBRARY_DISABLE", "1")
        reg = load_registry(project_root=str(tmp_path))
        assert reg == {}


# ─── Coverage report tests ──────────────────────────────────────────────


class TestCoverageReport:
    """Tests for PartsResolver.coverage_report() — the human-readable
    end-of-build summary that tells users which parts went where."""

    def _make_resolver_with_decisions(self, decisions: list) -> PartsResolver:
        """Build a resolver and synthesize a decision log without actually
        running adapters. Each entry is (part_no, adapter_name, source_tag)."""
        resolver = PartsResolver(registry={}, adapters=[])
        resolver._decision_log = list(decisions)
        return resolver

    def test_empty_when_no_decisions(self):
        resolver = PartsResolver(registry={}, adapters=[])
        assert resolver.coverage_report() == ""

    def test_groups_by_adapter_with_counts(self):
        resolver = self._make_resolver_with_decisions([
            ("P-001", "step_pool", "STEP:foo.step"),
            ("P-002", "bd_warehouse", "BW:608"),
            ("P-003", "jinja_primitive", "jinja:tank"),
            ("P-004", "jinja_primitive", "jinja:tank"),
        ])
        report = resolver.coverage_report()
        assert "resolver coverage:" in report
        assert "step_pool" in report
        assert "bd_warehouse" in report
        assert "jinja_primitive" in report
        # Counts visible: 1, 1, 2
        assert "P-001" in report
        assert "P-002" in report
        # Aggregate row
        assert "Total: 4 parts" in report
        assert "Ready geometry: 2" in report
        assert "Fallback: 2" in report

    def test_jinja_primitive_listed_last(self):
        """Library backends should appear above the simplified-geometry
        fallback so the most informative rows are visually prominent."""
        resolver = self._make_resolver_with_decisions([
            ("P-001", "jinja_primitive", "jinja"),
            ("P-002", "step_pool", "STEP"),
        ])
        report = resolver.coverage_report()
        step_pos = report.index("step_pool")
        jinja_pos = report.index("jinja_primitive")
        assert step_pos < jinja_pos

    def test_truncates_long_example_lists(self):
        """Adapters handling many parts get a `... (and N more)` suffix."""
        decisions = [
            (f"P-{i:03d}", "jinja_primitive", "jinja")
            for i in range(20)
        ]
        resolver = self._make_resolver_with_decisions(decisions)
        report = resolver.coverage_report(max_examples_per_adapter=5)
        assert "and 15 more" in report

    def test_hint_appears_only_when_fallback_present(self):
        """Hint footer is only shown when the user can act on it
        (i.e. when there are lower-quality or review-required parts to upgrade)."""
        # No fallback → no hint
        resolver = self._make_resolver_with_decisions([
            ("P-001", "step_pool", "STEP"),
            ("P-002", "bd_warehouse", "BW"),
        ])
        assert "need model review" not in resolver.coverage_report()
        assert "extends: default" not in resolver.coverage_report()

        # Some fallback → hint appears
        resolver2 = self._make_resolver_with_decisions([
            ("P-003", "jinja_primitive", "jinja"),
        ])
        report2 = resolver2.coverage_report()
        assert "need model review" in report2
        assert "extends: default" in report2
        assert "PARTS_LIBRARY.md" in report2

    def test_b_grade_parametric_templates_do_not_count_as_fallback(self):
        """A curated B-grade parametric template is codegen-backed but should
        not be reported as simplified fallback needing model review."""
        from parts_resolver import GeometryDecision

        resolver = self._make_resolver_with_decisions([
            GeometryDecision(
                part_no="SLP-F11",
                name_cn="PU 缓冲垫",
                status="hit",
                kind="codegen",
                adapter="jinja_primitive",
                source_tag="parametric_template:pu_buffer_pad",
                geometry_source="PARAMETRIC_TEMPLATE",
                geometry_quality="B",
                requires_model_review=False,
            ),
        ])

        report = resolver.coverage_report()
        assert "parametric_template" in report
        assert "jinja_primitive" not in report
        assert "Ready geometry: 1" in report
        assert "Fallback: 0" in report
        assert "need model review" not in report

    def test_fallback_count_uses_review_flag_and_normalized_quality(self):
        """Fallback accounting follows the geometry contract, not adapter
        names, and quality grades are normalized before classification."""
        from parts_resolver import GeometryDecision

        resolver = self._make_resolver_with_decisions([
            GeometryDecision(
                part_no="P-001",
                name_cn="B-but-review",
                status="hit",
                kind="codegen",
                adapter="jinja_primitive",
                source_tag="parametric_template:needs_review",
                geometry_source="PARAMETRIC_TEMPLATE",
                geometry_quality="B",
                requires_model_review=True,
            ),
            GeometryDecision(
                part_no="P-002",
                name_cn="lowercase-quality",
                status="hit",
                kind="python_import",
                adapter="bd_warehouse",
                source_tag="bd:test",
                geometry_source="BD_WAREHOUSE",
                geometry_quality="c",
                requires_model_review=False,
            ),
            GeometryDecision(
                part_no="P-003",
                name_cn="ready-template",
                status="hit",
                kind="codegen",
                adapter="jinja_primitive",
                source_tag="parametric_template:ready",
                geometry_source="PARAMETRIC_TEMPLATE",
                geometry_quality="B",
                requires_model_review=False,
            ),
        ])

        report = resolver.coverage_report()
        assert "Ready geometry: 1" in report
        assert "Fallback: 2" in report
        assert "2 parts need model review" in report

    def test_decisions_by_adapter_returns_part_lists(self):
        """The lower-level decisions_by_adapter() returns adapter → list."""
        resolver = self._make_resolver_with_decisions([
            ("P-001", "step_pool", "STEP:a"),
            ("P-002", "step_pool", "STEP:b"),
            ("P-003", "jinja_primitive", "jinja"),
        ])
        d = resolver.decisions_by_adapter()
        assert d["step_pool"] == [("P-001", "STEP:a"), ("P-002", "STEP:b")]
        assert d["jinja_primitive"] == [("P-003", "jinja")]

    def test_report_is_pure_ascii(self):
        """The report must use only ASCII (the box-drawing dash is intentional)
        — no emoji, no high-Unicode characters that break Windows GBK consoles."""
        decisions = [
            ("P-001", "step_pool", "STEP"),
            ("P-002", "jinja_primitive", "jinja"),
        ]
        resolver = self._make_resolver_with_decisions(decisions)
        report = resolver.coverage_report()
        # ─ (U+2500) is the only non-ASCII char we use, intentionally for the
        # separator line. Everything else must encode under cp1252/cp936.
        non_ascii = [c for c in report if ord(c) > 127 and c != "─"]
        assert non_ascii == [], f"unexpected non-ASCII: {non_ascii!r}"


# ─── PartQuery spec_envelope_granularity field tests ─────────────────────


def test_part_query_has_spec_envelope_granularity_default():
    """New field defaults to 'part_envelope' so all legacy callers remain
    safe — only the codegen chain sets non-default values."""
    q = PartQuery(
        part_no="X", name_cn="Y", material="", category="other",
        make_buy="自制",
    )
    assert q.spec_envelope_granularity == "part_envelope"


def test_part_query_accepts_station_constraint():
    q = PartQuery(
        part_no="X", name_cn="Y", material="", category="other",
        make_buy="自制",
        spec_envelope=(60.0, 40.0, 290.0),
        spec_envelope_granularity="station_constraint",
    )
    assert q.spec_envelope_granularity == "station_constraint"
