"""End-effector vendor/specialty STEP synthesizer coverage."""

from __future__ import annotations

from pathlib import Path

import pytest

from parts_resolver import PartQuery, default_resolver


@pytest.mark.parametrize(
    ("query", "step_uri"),
    [
        (
            PartQuery(
                part_no="GIS-EE-001-04",
                name_cn="碟形弹簧垫圈",
                material="DIN 2093 A6",
                category="washer",
                make_buy="外购",
            ),
            "cache://mechanical/belleville_din2093_a6.step",
        ),
        (
            PartQuery(
                part_no="GIS-EE-001-07",
                name_cn="弹簧销组件（含弹簧）",
                material="Φ4×20mm锥形头",
                category="fastener",
                make_buy="外购",
            ),
            "cache://mechanical/spring_pin_4x20.step",
        ),
        (
            PartQuery(
                part_no="GIS-EE-001-09",
                name_cn="FFC线束总成",
                material="Molex 15168, 20芯×500mm",
                category="cable",
                make_buy="外购",
            ),
            "cache://molex/15168_ffc_20p.step",
        ),
        (
            PartQuery(
                part_no="GIS-EE-001-10",
                name_cn="ZIF连接器",
                material="Molex 5052xx",
                category="connector",
                make_buy="外购",
            ),
            "cache://molex/zif_5052xx.step",
        ),
        (
            PartQuery(
                part_no="GIS-EE-002-02",
                name_cn="储罐",
                material="不锈钢Φ38×280mm",
                category="vessel",
                make_buy="外购",
            ),
            "cache://process/reservoir_38x280.step",
        ),
        (
            PartQuery(
                part_no="GIS-EE-003-07",
                name_cn="配重块",
                material="钨合金Φ12×7mm/50g",
                category="weight",
                make_buy="外购",
            ),
            "cache://weights/tungsten_slug_12x7.step",
        ),
        (
            PartQuery(
                part_no="GIS-EE-004-10",
                name_cn="配重块",
                material="钨合金Φ14×13mm/120g",
                category="weight",
                make_buy="外购",
            ),
            "cache://weights/tungsten_slug_14x13.step",
        ),
    ],
)
def test_default_library_routes_end_effector_specialty_parts_to_cache_step(
    tmp_path, monkeypatch, query, step_uri
):
    cache_root = tmp_path / "step_cache"
    monkeypatch.setenv("CAD_SPEC_GEN_STEP_CACHE", str(cache_root))
    resolver = default_resolver(project_root=str(tmp_path))

    result = resolver.resolve(query)

    assert result.status == "hit"
    assert result.adapter == "step_pool"
    assert result.kind == "step_import"
    assert result.step_path == step_uri
    assert result.path_kind == "shared_cache"
    assert result.geometry_quality == "A"
    assert result.validated is True
    assert result.requires_model_review is False
    assert (cache_root / step_uri.removeprefix("cache://")).is_file()
