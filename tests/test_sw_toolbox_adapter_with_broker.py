"""SwToolboxAdapter × sw_config_broker 集成测试（Task 14 / spec §3.2）。

验证 adapter.resolve() 委托给 broker：
- source=auto + config_name 非空 → 触发 STEP 导出，cache 路径含 config 后缀
- source=cached_decision + config_name=None → adapter 返回 miss（让 CadQuery 兜底）
- broker 抛 NeedsUserDecision → adapter 不吞，向上 propagate 给 gen_std_parts

mock 锚点：patch broker 源模块 `adapters.solidworks.sw_config_broker.resolve_config_for_part`。
该函数在 adapter.resolve() 内部以 `from ... import ...` 形式取，runtime
查名走 broker 源模块，与 patch 锚点一致。
"""

from __future__ import annotations

import os
import sys
import unittest.mock as mock
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _build_query(
    name_cn: str = "内六角螺栓 GB/T 70.1 M8×20",
    material: str = "GB/T 70.1 M8×20",
    part_no: str = "GIS-EE-001-01",
    subsystem: str = "default",
):
    """构造 PartsQuery duck-type（resolver 用 getattr 取字段）。"""
    return SimpleNamespace(
        name_cn=name_cn,
        material=material,
        part_no=part_no,
        subsystem=subsystem,
    )


def _build_fake_part():
    """构造 SwToolboxPart duck-type — 仅暴露 resolve() 用到的字段。"""
    return SimpleNamespace(
        filename="bolt.sldprt",
        sldprt_path="C:/SW/data/Toolbox/GB/Bolt/bolt.sldprt",
        standard="GB",
        subcategory="Bolt",
    )


class _FakeSwInfo:
    def __init__(self, toolbox_dir: str = "C:/SW/data/Toolbox"):
        self.toolbox_dir = toolbox_dir


@pytest.fixture
def adapter_with_mocks(monkeypatch, tmp_path):
    """统一搭好 adapter 上游 mock：detect / catalog / get_session / _probe_step_bbox。

    返回 (adapter, mock_session, cache_root)；测试只需 patch broker。
    """
    from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
    from adapters.solidworks import sw_detect, sw_toolbox_catalog
    from adapters.solidworks import sw_com_session

    sw_detect._reset_cache()
    monkeypatch.setattr(
        sw_detect,
        "detect_solidworks",
        lambda: _FakeSwInfo(toolbox_dir=str(tmp_path / "Toolbox")),
    )

    fake_part = _build_fake_part()
    monkeypatch.setattr(
        sw_toolbox_catalog,
        "get_toolbox_index_path",
        lambda cfg: tmp_path / "index.json",
    )
    monkeypatch.setattr(
        sw_toolbox_catalog,
        "load_toolbox_index",
        lambda path, root: object(),
    )
    monkeypatch.setattr(
        sw_toolbox_catalog,
        "extract_size_from_name",
        lambda name, patterns: {"M": "8", "L": "20"},
    )
    monkeypatch.setattr(
        sw_toolbox_catalog,
        "build_query_tokens_weighted",
        lambda q, sd, w: ["m8", "20"],
    )
    monkeypatch.setattr(
        sw_toolbox_catalog,
        "match_toolbox_part",
        lambda *args, **kwargs: (fake_part, 0.85),
    )
    monkeypatch.setattr(
        sw_toolbox_catalog,
        "_validate_sldprt_path",
        lambda p, root: True,
    )
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    monkeypatch.setattr(
        sw_toolbox_catalog,
        "get_toolbox_cache_root",
        lambda cfg: cache_root,
    )

    fake_session = mock.MagicMock()
    fake_session.is_healthy.return_value = True
    fake_session.convert_sldprt_to_step.return_value = True
    monkeypatch.setattr(sw_com_session, "get_session", lambda: fake_session)

    adapter = SwToolboxAdapter(config={"size_patterns": {}, "min_score": 0.30})
    monkeypatch.setattr(
        adapter, "_probe_step_bbox", lambda p: (10.0, 8.0, 20.0)
    )

    return adapter, fake_session, cache_root, fake_part


class TestSwToolboxAdapterDelegatesToBroker:
    """spec §3.2: sw_toolbox_adapter.resolve 委托给 sw_config_broker."""

    def test_broker_use_config_triggers_step_export(self, adapter_with_mocks):
        """broker auto + config_name="80×2.4" → STEP 导出，cache stem 含 config 后缀。"""
        from adapters.solidworks import sw_config_broker as broker

        adapter, fake_session, cache_root, fake_part = adapter_with_mocks

        with mock.patch.object(
            broker,
            "resolve_config_for_part",
            return_value=broker.ConfigResolution(
                config_name="80×2.4",
                source="auto",
                confidence=0.95,
                available_configs=["80×2.4", "100×3.0"],
                notes="规则匹配（confidence=0.95）",
            ),
        ) as mock_resolve:
            result = adapter.resolve(_build_query(), spec={})

        assert result.status == "hit"
        assert result.kind == "step_import"
        assert result.metadata["configuration"] == "80×2.4"
        assert result.metadata["config_match"] == "auto"
        assert result.metadata["config_confidence"] == 0.95

        # broker 被调用一次，且签名包含 bom_row + sldprt_path + subsystem
        mock_resolve.assert_called_once()
        kwargs = mock_resolve.call_args.kwargs
        assert kwargs["sldprt_path"] == fake_part.sldprt_path
        assert kwargs["subsystem"] == "default"
        assert kwargs["bom_row"]["part_no"] == "GIS-EE-001-01"

        # COM 被触发（cache 未命中）+ STEP 路径含 config 后缀（safe_config 替换 ×→_）
        assert fake_session.convert_sldprt_to_step.called
        step_path_arg = fake_session.convert_sldprt_to_step.call_args.args[1]
        assert "80_2.4" in step_path_arg

    def test_broker_fallback_returns_miss(self, adapter_with_mocks):
        """broker cached_decision + config_name=None → adapter 返回 miss 让 CadQuery 兜底。"""
        from adapters.solidworks import sw_config_broker as broker

        adapter, fake_session, _, _ = adapter_with_mocks

        with mock.patch.object(
            broker,
            "resolve_config_for_part",
            return_value=broker.ConfigResolution(
                config_name=None,
                source="cached_decision",
                confidence=1.0,
                available_configs=["Default"],
                notes="用户决策 fallback（2026-04-26）",
            ),
        ):
            result = adapter.resolve(_build_query(), spec={})

        assert result.status == "miss"
        # COM 不应被触发（broker 已宣告 fallback）
        assert not fake_session.convert_sldprt_to_step.called
        assert any("fallback" in w.lower() for w in (result.warnings or []))

    def test_broker_raises_propagates(self, adapter_with_mocks):
        """NeedsUserDecision 应该 propagate 给 caller (gen_std_parts)，adapter 不吞。"""
        from adapters.solidworks import sw_config_broker as broker

        adapter, _, _, _ = adapter_with_mocks

        record = {
            "part_no": "GIS-EE-001-01",
            "match_failure_reason": "no_exact_or_fuzzy_match_with_high_confidence",
        }
        with mock.patch.object(
            broker,
            "resolve_config_for_part",
            side_effect=broker.NeedsUserDecision(
                part_no="GIS-EE-001-01",
                subsystem="default",
                pending_record=record,
            ),
        ):
            with pytest.raises(broker.NeedsUserDecision) as exc_info:
                adapter.resolve(_build_query(), spec={})

        assert exc_info.value.part_no == "GIS-EE-001-01"
        assert exc_info.value.subsystem == "default"
        assert exc_info.value.pending_record == record


class TestGenStdPartsAccumulation:
    """Task 15：generate_std_part_files 捕获 NeedsUserDecision，按 subsystem 分组累积。"""

    def test_multiple_needs_decision_accumulated_into_pending(
        self, tmp_path, monkeypatch
    ):
        """3 个零件分跨 2 个 subsystem 都抛 NeedsUserDecision → 返回的 pending_records
        含全部 3 项嵌套到正确 subsystem，零件 std_*.py 不生成。
        """
        from adapters.solidworks.sw_config_broker import NeedsUserDecision
        from codegen import gen_std_parts as g

        # bearing：不在 _SKIP_CATEGORIES（fastener / cable）里，loop 会调 resolver.resolve
        fake_parts = [
            {"part_no": "GIS-EE-001-01", "name_cn": "微型轴承1", "material": "MR105ZZ",
             "is_assembly": False, "make_buy": "外购"},
            {"part_no": "GIS-EE-001-02", "name_cn": "微型轴承2", "material": "608ZZ",
             "is_assembly": False, "make_buy": "外购"},
            {"part_no": "GIS-EL-002-01", "name_cn": "电机轴承", "material": "623ZZ",
             "is_assembly": False, "make_buy": "外购"},
        ]
        monkeypatch.setattr(g, "parse_bom_tree", lambda spec_path: fake_parts)
        monkeypatch.setattr(g, "parse_envelopes", lambda spec_path: {})
        monkeypatch.setattr(g, "classify_part", lambda name, mat: "bearing")

        def fake_resolve(query):
            subsystem = "end_effector" if query.part_no.startswith("GIS-EE") else "electrical"
            raise NeedsUserDecision(
                part_no=query.part_no,
                subsystem=subsystem,
                pending_record={
                    "part_no": query.part_no,
                    "match_failure_reason": "no_exact_or_fuzzy_match_with_high_confidence",
                },
            )

        class FakeResolver:
            adapters = []

            def resolve(self, q):
                return fake_resolve(q)

            def coverage_report(self):
                return ""

        monkeypatch.setattr(g, "default_resolver", lambda **kw: FakeResolver())

        spec_path = tmp_path / "spec.md"
        spec_path.write_text("# fake spec\n", encoding="utf-8")
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        result = g.generate_std_part_files(str(spec_path), str(out_dir))

        # Task 15：signature 由 (generated, skipped, resolver) → 4-tuple 加 pending_records
        assert len(result) == 4
        generated, skipped, _resolver, pending = result
        assert generated == []
        assert pending == {
            "end_effector": [
                {"part_no": "GIS-EE-001-01",
                 "match_failure_reason": "no_exact_or_fuzzy_match_with_high_confidence"},
                {"part_no": "GIS-EE-001-02",
                 "match_failure_reason": "no_exact_or_fuzzy_match_with_high_confidence"},
            ],
            "electrical": [
                {"part_no": "GIS-EL-002-01",
                 "match_failure_reason": "no_exact_or_fuzzy_match_with_high_confidence"},
            ],
        }

    def test_no_needs_decision_returns_empty_pending(self, tmp_path, monkeypatch):
        """空 BOM → pending_records 为空 dict（function 仍返 4-tuple）。"""
        from codegen import gen_std_parts as g

        monkeypatch.setattr(g, "parse_bom_tree", lambda spec_path: [])
        monkeypatch.setattr(g, "parse_envelopes", lambda spec_path: {})

        spec_path = tmp_path / "spec.md"
        spec_path.write_text("# fake spec\n", encoding="utf-8")
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        result = g.generate_std_part_files(str(spec_path), str(out_dir))
        assert len(result) == 4
        _, _, _, pending = result
        assert pending == {}
