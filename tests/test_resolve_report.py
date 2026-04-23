"""tests/test_resolve_report.py — PartsResolver.resolve_report() 单元测试。"""
from __future__ import annotations

import json

import pytest

from parts_resolver import (
    AdapterHit,
    PartsResolver,
    ResolveReport,
    ResolveReportRow,
)
from adapters.parts.jinja_primitive_adapter import JinjaPrimitiveAdapter
from adapters.parts.partcad_adapter import PartCADAdapter


def _make_resolver(extra_adapters=None) -> PartsResolver:
    resolver = PartsResolver(registry={"mappings": []})
    resolver.register_adapter(JinjaPrimitiveAdapter())
    for a in (extra_adapters or []):
        resolver.register_adapter(a)
    return resolver


def _make_bom_rows(n: int = 3) -> list[dict]:
    # category="bearing" 在 JinjaPrimitiveAdapter._GENERATORS 中，
    # 可触发 fallback 路径（resolver 无 mapping 规则时 jinja_primitive 兜底）
    return [
        {
            "part_no": f"P-00{i}",
            "name_cn": f"零件{i}",
            "material": "",
            "category": "bearing",
            "make_buy": "外购",
        }
        for i in range(1, n + 1)
    ]


class TestResolveReportBasic:
    def test_returns_resolve_report_instance(self):
        resolver = _make_resolver()
        rows = _make_bom_rows(2)
        report = resolver.resolve_report(rows)
        assert isinstance(report, ResolveReport)

    def test_total_rows_matches_input(self):
        resolver = _make_resolver()
        rows = _make_bom_rows(5)
        report = resolver.resolve_report(rows)
        assert report.total_rows == 5

    def test_rows_length_matches_input(self):
        resolver = _make_resolver()
        rows = _make_bom_rows(3)
        report = resolver.resolve_report(rows)
        assert len(report.rows) == 3

    def test_all_fallback_to_jinja_when_no_rules(self):
        resolver = _make_resolver()
        rows = _make_bom_rows(4)
        report = resolver.resolve_report(rows)
        for row in report.rows:
            assert row.status == "fallback"
            assert row.matched_adapter == "jinja_primitive"

    def test_run_id_preserved(self):
        resolver = _make_resolver()
        report = resolver.resolve_report([], run_id="test-run-42")
        assert report.run_id == "test-run-42"

    def test_empty_bom_returns_empty_rows(self):
        resolver = _make_resolver()
        report = resolver.resolve_report([])
        assert report.total_rows == 0
        assert report.rows == []


class TestResolveReportAdapterHits:
    def test_jinja_primitive_hit_counted(self):
        resolver = _make_resolver()
        rows = _make_bom_rows(3)
        report = resolver.resolve_report(rows)
        assert report.adapter_hits["jinja_primitive"].count == 3

    def test_unavailable_adapter_has_reason(self):
        resolver = _make_resolver(extra_adapters=[PartCADAdapter(config={})])
        rows = _make_bom_rows(2)
        report = resolver.resolve_report(rows)
        hit = report.adapter_hits.get("partcad")
        assert hit is not None
        assert hit.unavailable_reason is not None
        assert "enabled" in hit.unavailable_reason.lower()

    def test_available_adapter_has_no_reason(self):
        resolver = _make_resolver()
        rows = _make_bom_rows(1)
        report = resolver.resolve_report(rows)
        assert report.adapter_hits["jinja_primitive"].unavailable_reason is None

    def test_adapter_hits_initialized_for_all_adapters(self):
        resolver = _make_resolver(extra_adapters=[PartCADAdapter(config={})])
        rows = _make_bom_rows(1)
        report = resolver.resolve_report(rows)
        # 两个 adapter 都应在 adapter_hits 里
        assert "jinja_primitive" in report.adapter_hits
        assert "partcad" in report.adapter_hits


class TestResolveReportSerialization:
    def test_to_dict_schema_version(self):
        resolver = _make_resolver()
        d = resolver.resolve_report([]).to_dict()
        assert d["schema_version"] == 1

    def test_to_dict_is_json_serializable(self):
        resolver = _make_resolver()
        rows = _make_bom_rows(2)
        d = resolver.resolve_report(rows).to_dict()
        serialized = json.dumps(d)
        loaded = json.loads(serialized)
        assert loaded["total_rows"] == 2

    def test_rows_have_required_fields(self):
        resolver = _make_resolver()
        rows = _make_bom_rows(1)
        report = resolver.resolve_report(rows)
        r = report.rows[0]
        assert hasattr(r, "bom_id")
        assert hasattr(r, "name_cn")
        assert hasattr(r, "matched_adapter")
        assert hasattr(r, "attempted_adapters")
        assert hasattr(r, "status")
        assert r.status in ("hit", "fallback", "miss")

    def test_attempted_adapters_is_list(self):
        resolver = _make_resolver()
        rows = _make_bom_rows(1)
        report = resolver.resolve_report(rows)
        r = report.rows[0]
        assert isinstance(r.attempted_adapters, list)
        assert len(r.attempted_adapters) >= 1


class TestResolveReportTrace:
    def test_trace_contains_fallback_marker(self):
        resolver = _make_resolver()
        rows = _make_bom_rows(1)
        report = resolver.resolve_report(rows)
        r = report.rows[0]
        # jinja_primitive 的 fallback 路径应留下 trace
        assert any("jinja_primitive" in t for t in r.attempted_adapters)
