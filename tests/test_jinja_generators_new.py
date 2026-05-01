# tests/test_jinja_generators_new.py
"""jinja_primitive 新增 locating/elastic/transmission 生成器端到端测试。

PartQuery 是 parts_resolver.py 里的 @dataclass，字段：
  part_no, name_cn, material, category, make_buy,
  spec_envelope=None, spec_envelope_granularity="part_envelope", project_root=""
"""
from __future__ import annotations

from pathlib import Path

import pytest
from parts_resolver import PartQuery
from adapters.parts.jinja_primitive_adapter import JinjaPrimitiveAdapter

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _q(category: str, name: str = "test", material: str = "") -> PartQuery:
    """快捷构造一个最小化 PartQuery。"""
    return PartQuery(
        part_no="TEST-001",
        name_cn=name,
        material=material,
        category=category,
        make_buy="外购",
    )


@pytest.fixture(scope="module")
def adapter() -> JinjaPrimitiveAdapter:
    return JinjaPrimitiveAdapter()


# ── can_resolve ──────────────────────────────────────────────────────────────

def test_can_resolve_locating(adapter: JinjaPrimitiveAdapter) -> None:
    assert adapter.can_resolve(_q("locating")) is True


def test_can_resolve_elastic(adapter: JinjaPrimitiveAdapter) -> None:
    assert adapter.can_resolve(_q("elastic")) is True


def test_can_resolve_transmission(adapter: JinjaPrimitiveAdapter) -> None:
    assert adapter.can_resolve(_q("transmission")) is True


# ── resolve → hit ────────────────────────────────────────────────────────────

def test_resolve_locating_hit(adapter: JinjaPrimitiveAdapter) -> None:
    result = adapter.resolve(_q("locating"), {})
    assert result.status == "hit"
    assert result.kind == "codegen"
    assert "cq.Workplane" in result.body_code


def test_resolve_elastic_hit(adapter: JinjaPrimitiveAdapter) -> None:
    result = adapter.resolve(_q("elastic"), {})
    assert result.status == "hit"
    assert result.kind == "codegen"
    assert "cq.Workplane" in result.body_code


def test_resolve_transmission_hit(adapter: JinjaPrimitiveAdapter) -> None:
    result = adapter.resolve(_q("transmission"), {})
    assert result.status == "hit"
    assert result.kind == "codegen"
    assert "cq.Workplane" in result.body_code


# ── probe_dims 返回有效 (w, d, h) tuple ──────────────────────────────────────

def test_probe_dims_locating(adapter: JinjaPrimitiveAdapter) -> None:
    dims = adapter.probe_dims(_q("locating"), {})
    assert dims is not None
    assert len(dims) == 3
    assert all(v > 0 for v in dims)


def test_probe_dims_elastic(adapter: JinjaPrimitiveAdapter) -> None:
    dims = adapter.probe_dims(_q("elastic"), {})
    assert dims is not None
    assert len(dims) == 3
    assert all(v > 0 for v in dims)


def test_probe_dims_transmission(adapter: JinjaPrimitiveAdapter) -> None:
    dims = adapter.probe_dims(_q("transmission"), {})
    assert dims is not None
    assert len(dims) == 3
    assert all(v > 0 for v in dims)


# ── transmission envelope 正确反映齿轮厚度 w ─────────────────────────────────

def test_transmission_envelope_uses_w(adapter: JinjaPrimitiveAdapter) -> None:
    """默认 dims {"od":30,"w":8,"id":6} → probe_dims 应返回 (30, 30, 8)。

    修复前 _dims_to_envelope 不检查 "w"，返回 (30, 30, 5)。
    """
    dims = adapter.probe_dims(_q("transmission"), {})
    assert dims == (30, 30, 8)


# ── locating: dims 从 material text 提取 ─────────────────────────────────────

def test_locating_dims_from_material_text(adapter: JinjaPrimitiveAdapter) -> None:
    """material='Φ5×16mm' 经 _parse_dims_from_text 提取为 d=5, l=16。

    _gen_locating 接收 d=5 → circle(2.5)，验证字符串包含正确半径。
    """
    result = adapter.resolve(_q("locating", name="定位销", material="Φ5×16mm"), {})
    assert result.status == "hit"
    assert "circle(2.5)" in result.body_code


# ── P1 electrical / connector semi-parametric templates ─────────────────────

@pytest.mark.parametrize(
    ("category", "name", "material", "template_id", "body_marker"),
    [
        ("connector", "ZIF连接器", "Molex 5052xx", "zif_connector", "ZIF connector"),
        ("connector", "FFC线束总成", "Molex 15168, 20芯×500mm", "ffc_ribbon", "FFC ribbon"),
        ("other", "信号调理PCB", "定制4层混合信号", "pcb_board", "PCB assembly"),
        ("connector", "SMA穿壁连接器", "50Ω", "sma_bulkhead", "SMA bulkhead"),
        ("other", "M12防水诊断接口", "4芯", "m12_connector", "M12 connector"),
        ("sensor", "I300-UHF-GT传感器", "波译科技", "uhf_sensor", "UHF sensor"),
        ("other", "压力阵列", "4×4薄膜 20×20mm", "pressure_array", "pressure array"),
    ],
)
def test_p1_electrical_parts_use_specialized_templates(
    adapter: JinjaPrimitiveAdapter,
    category: str,
    name: str,
    material: str,
    template_id: str,
    body_marker: str,
) -> None:
    result = adapter.resolve(_q(category, name=name, material=material), {})

    assert result.status == "hit"
    assert result.kind == "codegen"
    assert result.geometry_source == "JINJA_TEMPLATE"
    assert result.geometry_quality == "C"
    assert result.requires_model_review is True
    assert result.metadata["template"] == template_id
    assert body_marker in result.body_code


def test_ffc_template_keeps_actual_length_metadata(
    adapter: JinjaPrimitiveAdapter,
) -> None:
    result = adapter.resolve(
        _q("connector", name="FFC线束总成", material="Molex 15168, 20芯×500mm"),
        {},
    )

    assert result.metadata["actual_length_mm"] == 500
    assert result.metadata["pins"] == 20
    assert result.real_dims[0] == 12
    assert result.real_dims[1] == 50
    assert result.real_dims[2] == 1


def test_non_sma_50_ohm_connector_does_not_use_sma_template(
    adapter: JinjaPrimitiveAdapter,
) -> None:
    result = adapter.resolve(
        _q("connector", name="BNC穿壁连接器", material="50Ω"),
        {},
    )

    assert result.metadata.get("template") != "sma_bulkhead"
    assert result.source_tag == "jinja_primitive:connector"


def test_generic_thin_film_part_does_not_use_pressure_array_template(
    adapter: JinjaPrimitiveAdapter,
) -> None:
    result = adapter.resolve(
        _q("other", name="绝缘薄膜垫片", material="20×20mm"),
        {},
    )

    assert result.metadata.get("template") != "pressure_array"
    assert result.source_tag == "jinja_primitive:other"


# ── P2 fluid / cleaning semi-parametric templates ──────────────────────────

@pytest.mark.parametrize(
    ("category", "name", "material", "template_id", "body_marker", "dims"),
    [
        (
            "tank",
            "储罐",
            "不锈钢Φ38×280mm",
            "fluid_reservoir",
            "fluid reservoir",
            (38.0, 38.0, 280.0),
        ),
        (
            "pump",
            "齿轮泵",
            "",
            "gear_pump",
            "gear pump",
            (30, 25, 40),
        ),
        (
            "other",
            "刮涂头",
            "硅橡胶",
            "scraper_head",
            "scraper head",
            (15, 8, 6),
        ),
        (
            "tank",
            "溶剂储罐（活塞式正压密封）",
            "Φ25×110mm，M8快拆接口",
            "solvent_cartridge",
            "solvent cartridge",
            (25.0, 25.0, 110.0),
        ),
        (
            "pump",
            "微量泵（溶剂喷射）",
            "电磁阀式",
            "micro_dosing_pump",
            "micro dosing pump",
            (20, 15, 30),
        ),
        (
            "other",
            "清洁带盒（供带卷轴+收带卷轴+10m无纺布带）",
            "超细纤维无纺布",
            "cleaning_tape_cassette",
            "cleaning tape cassette",
            (42, 28, 12),
        ),
    ],
)
def test_p2_fluid_and_cleaning_parts_use_specialized_templates(
    adapter: JinjaPrimitiveAdapter,
    category: str,
    name: str,
    material: str,
    template_id: str,
    body_marker: str,
    dims: tuple[float, float, float],
) -> None:
    result = adapter.resolve(_q(category, name=name, material=material), {})

    assert result.status == "hit"
    assert result.kind == "codegen"
    assert result.geometry_source == "JINJA_TEMPLATE"
    assert result.geometry_quality == "C"
    assert result.requires_model_review is True
    assert result.metadata["template"] == template_id
    assert result.real_dims == dims
    assert body_marker in result.body_code


@pytest.mark.parametrize(
    ("category", "name", "material"),
    [
        ("tank", "储罐", "不锈钢Φ38×280mm"),
        ("pump", "齿轮泵", ""),
        ("other", "刮涂头", "硅橡胶"),
        ("tank", "溶剂储罐（活塞式正压密封）", "Φ25×110mm，M8快拆接口"),
        ("pump", "微量泵（溶剂喷射）", "电磁阀式"),
        ("other", "清洁带盒（供带卷轴+收带卷轴+10m无纺布带）", "超细纤维无纺布"),
    ],
)
def test_p2_template_geometry_stays_within_reported_real_dims(
    adapter: JinjaPrimitiveAdapter,
    category: str,
    name: str,
    material: str,
) -> None:
    import cadquery as cq

    result = adapter.resolve(_q(category, name=name, material=material), {})
    namespace = {"cq": cq}
    exec(f"def _make():\n{result.body_code}\n", namespace)
    shape = namespace["_make"]()
    bbox = shape.val().BoundingBox()

    actual = (bbox.xlen, bbox.ylen, bbox.zlen)
    assert result.real_dims is not None
    for measured, expected in zip(actual, result.real_dims):
        assert measured <= expected + 1e-6


def test_non_fluid_tank_does_not_use_fluid_reservoir_template(
    adapter: JinjaPrimitiveAdapter,
) -> None:
    result = adapter.resolve(
        _q("tank", name="样品容器", material="Φ20×40mm"),
        {},
    )

    assert result.metadata.get("template") not in {
        "fluid_reservoir",
        "solvent_cartridge",
    }
    assert result.source_tag == "jinja_primitive:tank"


def test_end_effector_ffc_spec_envelope_matches_template_dims() -> None:
    from codegen.gen_assembly import parse_envelopes

    spec_path = _REPO_ROOT / "cad" / "end_effector" / "CAD_SPEC.md"
    envelopes = parse_envelopes(str(spec_path))

    assert envelopes["GIS-EE-001-09"]["dims"] == (12.0, 50.0, 1.0)
    assert envelopes["GIS-EE-001-09"]["granularity"] == "part_envelope"


def test_end_effector_p3_spec_envelopes_match_template_dims() -> None:
    from codegen.gen_assembly import parse_envelopes

    spec_path = _REPO_ROOT / "cad" / "end_effector" / "CAD_SPEC.md"
    envelopes = parse_envelopes(str(spec_path))

    expected = {
        "GIS-EE-001-07": (4.0, 4.0, 20.0),
        "GIS-EE-004-03": (16.0, 16.0, 30.0),
        "GIS-EE-004-04": (25.0, 25.0, 35.0),
        "GIS-EE-004-06": (10.0, 10.0, 0.85),
        "GIS-EE-004-07": (15.0, 15.0, 12.0),
    }

    for part_no, dims in expected.items():
        assert envelopes[part_no]["dims"] == dims
        assert envelopes[part_no]["granularity"] == "part_envelope"


def test_end_effector_p4_spec_envelopes_match_template_dims() -> None:
    from codegen.gen_assembly import parse_envelopes

    spec_path = _REPO_ROOT / "cad" / "end_effector" / "CAD_SPEC.md"
    envelopes = parse_envelopes(str(spec_path))

    expected = {
        "GIS-EE-001-04": (12.5, 12.5, 0.85),
        "GIS-EE-003-05": (20.0, 20.0, 20.0),
        "GIS-EE-003-07": (12.0, 12.0, 7.0),
        "GIS-EE-004-05": (20.0, 15.0, 5.0),
        "GIS-EE-004-10": (14.0, 14.0, 13.0),
    }

    for part_no, dims in expected.items():
        assert envelopes[part_no]["dims"] == dims
        assert envelopes[part_no]["granularity"] == "part_envelope"


# ── P3 motion / cleaning drive semi-parametric templates ──────────────────

@pytest.mark.parametrize(
    ("category", "name", "material", "template_id", "body_marker", "dims"),
    [
        (
            "spring",
            "弹簧销组件（含弹簧）",
            "Φ4×20mm锥形头",
            "spring_pin_assembly",
            "spring pin assembly",
            (4.0, 4.0, 20.0),
        ),
        (
            "motor",
            "微型电机",
            "DC 3V Φ16mm",
            "mini_dc_motor",
            "mini DC motor",
            (16, 16, 30),
        ),
        (
            "reducer",
            "齿轮减速组（电机→收带卷轴）",
            "塑料齿轮",
            "gear_train_reducer",
            "gear train reducer",
            (25, 25, 35),
        ),
        (
            "spring",
            "恒力弹簧（供带侧张力）",
            "SUS301, 0.3N",
            "constant_force_spring",
            "constant force spring",
            (10, 10, 0.85),
        ),
        (
            "sensor",
            "光电编码器（带面余量）",
            "反射式",
            "photoelectric_encoder",
            "photoelectric encoder",
            (15, 15, 12),
        ),
    ],
)
def test_p3_motion_cleaning_parts_use_specialized_templates(
    adapter: JinjaPrimitiveAdapter,
    category: str,
    name: str,
    material: str,
    template_id: str,
    body_marker: str,
    dims: tuple[float, float, float],
) -> None:
    result = adapter.resolve(_q(category, name=name, material=material), {})

    assert result.status == "hit"
    assert result.kind == "codegen"
    assert result.geometry_source == "JINJA_TEMPLATE"
    assert result.geometry_quality == "C"
    assert result.requires_model_review is True
    assert result.metadata["template"] == template_id
    assert result.real_dims == dims
    assert body_marker in result.body_code


@pytest.mark.parametrize(
    ("category", "name", "material"),
    [
        ("spring", "弹簧销组件（含弹簧）", "Φ4×20mm锥形头"),
        ("motor", "微型电机", "DC 3V Φ16mm"),
        ("reducer", "齿轮减速组（电机→收带卷轴）", "塑料齿轮"),
        ("spring", "恒力弹簧（供带侧张力）", "SUS301, 0.3N"),
        ("sensor", "光电编码器（带面余量）", "反射式"),
    ],
)
def test_p3_template_geometry_stays_within_reported_real_dims(
    adapter: JinjaPrimitiveAdapter,
    category: str,
    name: str,
    material: str,
) -> None:
    import cadquery as cq

    result = adapter.resolve(_q(category, name=name, material=material), {})
    namespace = {"cq": cq}
    exec(f"def _make():\n{result.body_code}\n", namespace)
    shape = namespace["_make"]()
    bbox = shape.val().BoundingBox()

    actual = (bbox.xlen, bbox.ylen, bbox.zlen)
    assert result.real_dims is not None
    for measured, expected in zip(actual, result.real_dims):
        assert measured <= expected + 1e-6


def test_disc_spring_does_not_use_motion_specific_templates(
    adapter: JinjaPrimitiveAdapter,
) -> None:
    result = adapter.resolve(
        _q("spring", name="碟簧垫圈", material="DIN 2093 A6"),
        {},
    )

    assert result.metadata.get("template") not in {
        "spring_pin_assembly",
        "constant_force_spring",
    }
    assert result.metadata["template"] == "belleville_spring_washer"


@pytest.mark.parametrize(
    ("category", "name", "material", "forbidden_template", "source_tag"),
    [
        (
            "motor",
            "普通Φ16空心杯电机",
            "Φ16mm",
            "mini_dc_motor",
            "jinja_primitive:motor",
        ),
        (
            "spring",
            "SUS301压缩弹簧",
            "SUS301",
            "constant_force_spring",
            "jinja_primitive:spring",
        ),
        (
            "sensor",
            "反射式接近传感器",
            "反射式",
            "photoelectric_encoder",
            "jinja_primitive:sensor",
        ),
    ],
)
def test_p3_motion_templates_require_specific_part_intent(
    adapter: JinjaPrimitiveAdapter,
    category: str,
    name: str,
    material: str,
    forbidden_template: str,
    source_tag: str,
) -> None:
    result = adapter.resolve(_q(category, name=name, material=material), {})

    assert result.metadata.get("template") != forbidden_template
    assert result.source_tag == source_tag


# ── P4 remaining D-grade small hardware templates ─────────────────────────

@pytest.mark.parametrize(
    ("category", "name", "material", "template_id", "body_marker", "dims"),
    [
        (
            "spring",
            "碟形弹簧垫圈",
            "DIN 2093 A6",
            "belleville_spring_washer",
            "Belleville spring washer",
            (12.5, 12.5, 0.85),
        ),
        (
            "other",
            "阻尼垫",
            "黏弹性硅橡胶",
            "viscoelastic_damping_pad",
            "viscoelastic damping pad",
            (15, 15, 10),
        ),
        (
            "other",
            "配重块",
            "钨合金Φ12×7mm/50g",
            "tungsten_counterweight_slug",
            "tungsten counterweight slug",
            (12.0, 12.0, 7.0),
        ),
        (
            "other",
            "弹性衬垫",
            "硅橡胶Shore A 30, 20×15×5mm",
            "elastomer_cushion_pad",
            "elastomer cushion pad",
            (20.0, 15.0, 5.0),
        ),
        (
            "other",
            "配重块",
            "钨合金Φ14×13mm/120g",
            "tungsten_counterweight_slug",
            "tungsten counterweight slug",
            (14.0, 14.0, 13.0),
        ),
    ],
)
def test_p4_remaining_d_grade_parts_use_specialized_templates(
    adapter: JinjaPrimitiveAdapter,
    category: str,
    name: str,
    material: str,
    template_id: str,
    body_marker: str,
    dims: tuple[float, float, float],
) -> None:
    result = adapter.resolve(_q(category, name=name, material=material), {})

    assert result.status == "hit"
    assert result.kind == "codegen"
    assert result.geometry_source == "JINJA_TEMPLATE"
    assert result.geometry_quality == "C"
    assert result.requires_model_review is True
    assert result.metadata["template"] == template_id
    assert result.real_dims == dims
    assert body_marker in result.body_code


@pytest.mark.parametrize(
    ("category", "name", "material"),
    [
        ("spring", "碟形弹簧垫圈", "DIN 2093 A6"),
        ("other", "阻尼垫", "黏弹性硅橡胶"),
        ("other", "配重块", "钨合金Φ12×7mm/50g"),
        ("other", "弹性衬垫", "硅橡胶Shore A 30, 20×15×5mm"),
        ("other", "配重块", "钨合金Φ14×13mm/120g"),
    ],
)
def test_p4_remaining_d_grade_geometry_stays_within_reported_real_dims(
    adapter: JinjaPrimitiveAdapter,
    category: str,
    name: str,
    material: str,
) -> None:
    import cadquery as cq

    result = adapter.resolve(_q(category, name=name, material=material), {})
    namespace = {"cq": cq}
    exec(f"def _make():\n{result.body_code}\n", namespace)
    shape = namespace["_make"]()
    bbox = shape.val().BoundingBox()

    actual = (bbox.xlen, bbox.ylen, bbox.zlen)
    assert result.real_dims is not None
    for measured, expected in zip(actual, result.real_dims):
        assert measured <= expected + 1e-6


def test_generic_other_cylinder_does_not_use_counterweight_template(
    adapter: JinjaPrimitiveAdapter,
) -> None:
    result = adapter.resolve(
        _q("other", name="普通圆柱垫块", material="铝合金Φ12×7mm"),
        {},
    )

    assert result.metadata.get("template") != "tungsten_counterweight_slug"
    assert result.source_tag == "jinja_primitive:other"


# ── lifting_platform B-grade curated parametric replacements ───────────────

_LIFTING_PLATFORM_TEMPLATE_CASES = [
    (
        "bearing",
        "LM10UU",
        "",
        "linear_bearing_lm10uu",
        "LM10UU linear bearing",
        (19, 19, 29),
    ),
    (
        "bearing",
        "KFL001",
        "",
        "pillow_block_bearing_kfl001",
        "KFL001 pillow block bearing",
        (60, 36, 16),
    ),
    (
        "transmission",
        "L070 联轴器",
        "",
        "clamping_coupling_l070",
        "L070 clamping coupling",
        (25, 25, 30),
    ),
    (
        "transmission",
        "T16 螺母 C7",
        "",
        "t16_lead_screw_nut",
        "T16 lead screw nut",
        (28, 28, 16),
    ),
    (
        "transmission",
        "GT2 20T 开式带轮 φ12",
        "",
        "gt2_timing_pulley_20t",
        "GT2 20T timing pulley",
        (16, 16, 8),
    ),
    (
        "transmission",
        "GT2-310-6mm 带",
        "",
        "gt2_timing_belt_loop",
        "GT2 timing belt loop",
        (170, 80, 6),
    ),
    (
        "motor",
        "NEMA23 闭环步进 ≥1.0Nm",
        "",
        "nema23_stepper_motor",
        "NEMA23 stepper motor",
        (57, 57, 80),
    ),
    (
        "other",
        "CL57T 闭环驱动器",
        "",
        "cl57t_stepper_driver",
        "CL57T stepper driver",
        (118, 75, 34),
    ),
    (
        "seal",
        "PU 缓冲垫 20×20×3",
        "",
        "pu_buffer_pad",
        "PU buffer pad",
        (20, 20, 3),
    ),
    (
        "sensor",
        "M8 电感接近开关 NPN-NO",
        "",
        "m8_inductive_proximity_sensor",
        "M8 inductive proximity sensor",
        (8, 8, 45),
    ),
    (
        "other",
        "导向轴保护帽 φ10",
        "",
        "guide_shaft_protective_cap",
        "guide shaft protective cap",
        (10, 10, 8),
    ),
]


@pytest.mark.parametrize(
    ("category", "name", "material", "template_id", "body_marker", "dims"),
    _LIFTING_PLATFORM_TEMPLATE_CASES,
)
def test_lifting_platform_curated_parts_report_b_grade_parametric_templates(
    adapter: JinjaPrimitiveAdapter,
    category: str,
    name: str,
    material: str,
    template_id: str,
    body_marker: str,
    dims: tuple[float, float, float],
) -> None:
    result = adapter.resolve(_q(category, name=name, material=material), {})

    assert result.status == "hit"
    assert result.kind == "codegen"
    assert result.geometry_source == "PARAMETRIC_TEMPLATE"
    assert result.geometry_quality == "B"
    assert result.requires_model_review is False
    assert result.source_tag == f"parametric_template:{template_id}"
    assert result.metadata["template"] == template_id
    assert result.metadata["template_scope"] == "reusable_part_family"
    assert result.real_dims == dims
    assert body_marker in result.body_code


@pytest.mark.parametrize(
    ("category", "name", "material", "_template_id", "_body_marker", "_dims"),
    _LIFTING_PLATFORM_TEMPLATE_CASES,
)
def test_lifting_platform_template_geometry_stays_within_reported_real_dims(
    adapter: JinjaPrimitiveAdapter,
    category: str,
    name: str,
    material: str,
    _template_id: str,
    _body_marker: str,
    _dims: tuple[float, float, float],
) -> None:
    import cadquery as cq

    result = adapter.resolve(_q(category, name=name, material=material), {})
    namespace = {"cq": cq}
    exec(f"def _make():\n{result.body_code}\n", namespace)
    shape = namespace["_make"]()
    bbox = shape.val().BoundingBox()

    actual = (bbox.xlen, bbox.ylen, bbox.zlen)
    assert result.real_dims is not None
    for measured, expected in zip(actual, result.real_dims):
        assert measured <= expected + 1e-6


def test_lifting_platform_spec_envelopes_match_template_dims() -> None:
    from codegen.gen_assembly import parse_envelopes

    spec_path = _REPO_ROOT / "cad" / "lifting_platform" / "CAD_SPEC.md"
    envelopes = parse_envelopes(str(spec_path))

    expected = {
        "SLP-C02": (19.0, 19.0, 29.0),
        "SLP-C03": (60.0, 36.0, 16.0),
        "SLP-C06": (25.0, 25.0, 30.0),
        "SLP-C07": (57.0, 57.0, 80.0),
        "SLP-C08": (118.0, 75.0, 34.0),
        "SLP-F11": (20.0, 20.0, 3.0),
        "SLP-F12": (8.0, 8.0, 45.0),
        "SLP-F13": (10.0, 10.0, 8.0),
    }

    for part_no, dims in expected.items():
        assert envelopes[part_no]["dims"] == dims
        assert envelopes[part_no]["granularity"] == "part_envelope"


@pytest.mark.parametrize(
    ("category", "name", "material", "forbidden_template", "source_tag"),
    [
        (
            "bearing",
            "608ZZ 深沟球轴承",
            "",
            "linear_bearing_lm10uu",
            "jinja_primitive:bearing",
        ),
        (
            "connector",
            "普通夹紧联轴器",
            "Φ20×25mm",
            "clamping_coupling_l070",
            "jinja_primitive:connector",
        ),
        (
            "motor",
            "NEMA17 步进电机",
            "",
            "nema23_stepper_motor",
            "jinja_primitive:motor",
        ),
    ],
)
def test_lifting_platform_templates_require_specific_part_intent(
    adapter: JinjaPrimitiveAdapter,
    category: str,
    name: str,
    material: str,
    forbidden_template: str,
    source_tag: str,
) -> None:
    result = adapter.resolve(_q(category, name=name, material=material), {})

    assert result.metadata.get("template") != forbidden_template
    assert result.source_tag == source_tag
