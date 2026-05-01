"""End-effector vendor/specialty STEP synthesizer coverage."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from adapters.parts import vendor_synthesizer
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
        (
            PartQuery(
                part_no="GIS-EE-002-03",
                name_cn="齿轮泵",
                material="",
                category="pump",
                make_buy="外购",
            ),
            "cache://process/gear_pump_30x25x40.step",
        ),
        (
            PartQuery(
                part_no="GIS-EE-002-04",
                name_cn="刮涂头",
                material="硅橡胶",
                category="other",
                make_buy="外购",
            ),
            "cache://process/scraper_head_20x10x8.step",
        ),
        (
            PartQuery(
                part_no="GIS-EE-003-05",
                name_cn="阻尼垫",
                material="黏弹性硅橡胶",
                category="other",
                make_buy="外购",
            ),
            "cache://elastomer/damping_pad_20x20.step",
        ),
        (
            PartQuery(
                part_no="GIS-EE-003-06",
                name_cn="压力阵列",
                material="4×4薄膜 20×20mm",
                category="sensor",
                make_buy="外购",
            ),
            "cache://sensors/pressure_array_4x4_20mm.step",
        ),
        (
            PartQuery(
                part_no="GIS-EE-004-02",
                name_cn="清洁带盒（供带卷轴+收带卷轴+10m无纺布带）",
                material="超细纤维无纺布",
                category="other",
                make_buy="外购",
            ),
            "cache://process/cleaning_tape_cassette_42x28x12.step",
        ),
        (
            PartQuery(
                part_no="GIS-EE-004-03",
                name_cn="微型电机",
                material="DC 3V Φ16mm",
                category="motor",
                make_buy="外购",
            ),
            "cache://motors/dc_motor_16x30.step",
        ),
        (
            PartQuery(
                part_no="GIS-EE-004-04",
                name_cn="齿轮减速组（电机→收带卷轴）",
                material="塑料齿轮",
                category="reducer",
                make_buy="外购",
            ),
            "cache://transmission/gear_train_reducer_25x25x35.step",
        ),
        (
            PartQuery(
                part_no="GIS-EE-004-05",
                name_cn="弹性衬垫",
                material="硅橡胶Shore A 30, 20×15×5mm",
                category="other",
                make_buy="外购",
            ),
            "cache://elastomer/cushion_pad_20x15x5.step",
        ),
        (
            PartQuery(
                part_no="GIS-EE-004-06",
                name_cn="恒力弹簧（供带侧张力）",
                material="SUS301, 0.3N",
                category="spring",
                make_buy="外购",
            ),
            "cache://mechanical/constant_force_spring_10mm.step",
        ),
        (
            PartQuery(
                part_no="GIS-EE-004-07",
                name_cn="光电编码器（带面余量）",
                material="反射式",
                category="sensor",
                make_buy="外购",
            ),
            "cache://sensors/photoelectric_encoder_15x15x12.step",
        ),
        (
            PartQuery(
                part_no="GIS-EE-004-08",
                name_cn="溶剂储罐（活塞式正压密封）",
                material="Φ25×110mm，M8快拆接口",
                category="tank",
                make_buy="外购",
            ),
            "cache://process/solvent_cartridge_25x110.step",
        ),
        (
            PartQuery(
                part_no="GIS-EE-004-09",
                name_cn="微量泵（溶剂喷射）",
                material="电磁阀式",
                category="pump",
                make_buy="外购",
            ),
            "cache://process/micro_dosing_pump_20x15x30.step",
        ),
        (
            PartQuery(
                part_no="GIS-EE-005-01",
                name_cn="I300-UHF-GT传感器",
                material="波译科技",
                category="sensor",
                make_buy="外购",
            ),
            "cache://sensors/i300_uhf_gt.step",
        ),
        (
            PartQuery(
                part_no="GIS-EE-006-02",
                name_cn="信号调理PCB",
                material="定制4层混合信号",
                category="electronics",
                make_buy="外购",
            ),
            "cache://electronics/signal_conditioning_pcb_45x35.step",
        ),
        (
            PartQuery(
                part_no="GIS-EE-006-05",
                name_cn="SMA穿壁连接器",
                material="50Ω",
                category="connector",
                make_buy="外购",
            ),
            "cache://connectors/sma_bulkhead_50ohm.step",
        ),
        (
            PartQuery(
                part_no="GIS-EE-006-06",
                name_cn="M12防水诊断接口",
                material="4芯",
                category="connector",
                make_buy="外购",
            ),
            "cache://connectors/m12_4pin_bulkhead.step",
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


@pytest.mark.parametrize(
    ("query", "gis_step_uri"),
    [
        (
            PartQuery(
                part_no="OTHER-PUMP-001",
                name_cn="齿轮泵",
                material="",
                category="pump",
                make_buy="外购",
            ),
            "cache://process/gear_pump_30x25x40.step",
        ),
        (
            PartQuery(
                part_no="OTHER-PAD-001",
                name_cn="阻尼垫",
                material="硅橡胶",
                category="other",
                make_buy="外购",
            ),
            "cache://elastomer/damping_pad_20x20.step",
        ),
        (
            PartQuery(
                part_no="OTHER-REDUCER-001",
                name_cn="小型减速器",
                material="塑料齿轮",
                category="reducer",
                make_buy="外购",
            ),
            "cache://transmission/gear_train_reducer_25x25x35.step",
        ),
        (
            PartQuery(
                part_no="OTHER-SENSOR-001",
                name_cn="光电编码器",
                material="5V",
                category="sensor",
                make_buy="外购",
            ),
            "cache://sensors/photoelectric_encoder_15x15x12.step",
        ),
        (
            PartQuery(
                part_no="OTHER-CONN-001",
                name_cn="SMA穿壁连接器",
                material="75Ω",
                category="connector",
                make_buy="外购",
            ),
            "cache://connectors/sma_bulkhead_50ohm.step",
        ),
    ],
)
def test_default_library_does_not_route_generic_parts_to_gisbot_stand_ins(
    tmp_path, monkeypatch, query, gis_step_uri
):
    cache_root = tmp_path / "step_cache"
    monkeypatch.setenv("CAD_SPEC_GEN_STEP_CACHE", str(cache_root))
    resolver = default_resolver(project_root=str(tmp_path))

    result = resolver.resolve(query)

    assert not (
        result.adapter == "step_pool" and result.step_path == gis_step_uri
    )


def test_default_library_synthesizer_mappings_match_vendor_registry():
    default_paths = vendor_synthesizer.DEFAULT_STEP_FILES
    registry = yaml.safe_load(
        Path("parts_library.default.yaml").read_text(encoding="utf-8")
    )

    mapped_paths = {
        rule["spec"]["synthesizer"]: rule["spec"]["file"]
        for rule in registry["mappings"]
        if rule.get("adapter") == "step_pool"
        and (rule.get("spec") or {}).get("synthesizer")
    }

    assert set(mapped_paths) <= set(vendor_synthesizer.SYNTHESIZERS)
    assert mapped_paths == {
        factory_id: default_paths[factory_id]
        for factory_id in mapped_paths
    }


def test_project_library_routes_lifting_platform_kfl001_to_cache_step(
    tmp_path, monkeypatch
):
    cache_root = tmp_path / "step_cache"
    monkeypatch.setenv("CAD_SPEC_GEN_STEP_CACHE", str(cache_root))
    resolver = default_resolver(project_root=".")

    result = resolver.resolve(
        PartQuery(
            part_no="SLP-C03",
            name_cn="KFL001",
            material="",
            category="custom",
            make_buy="外购",
        )
    )

    assert result.status == "hit"
    assert result.adapter == "step_pool"
    assert result.kind == "step_import"
    assert result.step_path == "cache://mechanical/kfl001_flange_bearing.step"
    assert result.path_kind == "shared_cache"
    assert result.geometry_quality == "A"
    assert result.validated is True
    assert result.requires_model_review is False
    assert (cache_root / "mechanical" / "kfl001_flange_bearing.step").is_file()


def test_project_library_routes_lifting_platform_t16_nut_to_cache_step(
    tmp_path, monkeypatch
):
    cache_root = tmp_path / "step_cache"
    monkeypatch.setenv("CAD_SPEC_GEN_STEP_CACHE", str(cache_root))
    resolver = default_resolver(project_root=".")

    result = resolver.resolve(
        PartQuery(
            part_no="SLP-C01",
            name_cn="T16 螺母 C7",
            material="",
            category="transmission",
            make_buy="外购",
        )
    )

    assert result.status == "hit"
    assert result.adapter == "step_pool"
    assert result.kind == "step_import"
    assert result.step_path == "cache://transmission/t16_lead_screw_nut.step"
    assert result.path_kind == "shared_cache"
    assert result.geometry_quality == "A"
    assert result.validated is True
    assert result.requires_model_review is False
    assert (cache_root / "transmission" / "t16_lead_screw_nut.step").is_file()


def test_project_library_routes_lifting_platform_cl57t_to_cache_step(
    tmp_path, monkeypatch
):
    cache_root = tmp_path / "step_cache"
    monkeypatch.setenv("CAD_SPEC_GEN_STEP_CACHE", str(cache_root))
    resolver = default_resolver(project_root=".")

    result = resolver.resolve(
        PartQuery(
            part_no="SLP-C08",
            name_cn="CL57T 闭环驱动器",
            material="",
            category="electronics",
            make_buy="外购",
        )
    )

    assert result.status == "hit"
    assert result.adapter == "step_pool"
    assert result.kind == "step_import"
    assert result.step_path == "cache://electronics/cl57t_stepper_driver.step"
    assert result.path_kind == "shared_cache"
    assert result.geometry_quality == "A"
    assert result.validated is True
    assert result.requires_model_review is False
    assert (cache_root / "electronics" / "cl57t_stepper_driver.step").is_file()


def test_project_library_routes_lifting_platform_gt2_pulley_to_cache_step(
    tmp_path, monkeypatch
):
    cache_root = tmp_path / "step_cache"
    monkeypatch.setenv("CAD_SPEC_GEN_STEP_CACHE", str(cache_root))
    resolver = default_resolver(project_root=".")

    result = resolver.resolve(
        PartQuery(
            part_no="SLP-C04",
            name_cn="GT2 20T 开式带轮 φ12",
            material="",
            category="transmission",
            make_buy="外购",
        )
    )

    assert result.status == "hit"
    assert result.adapter == "step_pool"
    assert result.kind == "step_import"
    assert result.step_path == "cache://transmission/gt2_20t_timing_pulley.step"
    assert result.path_kind == "shared_cache"
    assert result.geometry_quality == "A"
    assert result.validated is True
    assert result.requires_model_review is False
    assert (cache_root / "transmission" / "gt2_20t_timing_pulley.step").is_file()


def test_project_library_routes_lifting_platform_gt2_belt_to_cache_step(
    tmp_path, monkeypatch
):
    cache_root = tmp_path / "step_cache"
    monkeypatch.setenv("CAD_SPEC_GEN_STEP_CACHE", str(cache_root))
    resolver = default_resolver(project_root=".")

    result = resolver.resolve(
        PartQuery(
            part_no="SLP-C05",
            name_cn="GT2-310-6mm 带",
            material="",
            category="transmission",
            make_buy="外购",
        )
    )

    assert result.status == "hit"
    assert result.adapter == "step_pool"
    assert result.kind == "step_import"
    assert result.step_path == "cache://transmission/gt2_310_6mm_timing_belt.step"
    assert result.path_kind == "shared_cache"
    assert result.geometry_quality == "A"
    assert result.validated is True
    assert result.requires_model_review is False
    assert (cache_root / "transmission" / "gt2_310_6mm_timing_belt.step").is_file()


def test_project_library_routes_lifting_platform_l070_to_cache_step(
    tmp_path, monkeypatch
):
    cache_root = tmp_path / "step_cache"
    monkeypatch.setenv("CAD_SPEC_GEN_STEP_CACHE", str(cache_root))
    resolver = default_resolver(project_root=".")

    result = resolver.resolve(
        PartQuery(
            part_no="SLP-C06",
            name_cn="L070 联轴器",
            material="",
            category="transmission",
            make_buy="外购",
        )
    )

    assert result.status == "hit"
    assert result.adapter == "step_pool"
    assert result.kind == "step_import"
    assert result.step_path == "cache://transmission/l070_clamping_coupling.step"
    assert result.path_kind == "shared_cache"
    assert result.geometry_quality == "A"
    assert result.validated is True
    assert result.requires_model_review is False
    assert (cache_root / "transmission" / "l070_clamping_coupling.step").is_file()
