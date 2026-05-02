from adapters.parts.parametric_transmission_adapter import ParametricTransmissionAdapter
from parts_resolver import PartQuery, PartsResolver, default_resolver
from sw_preflight.types import PartCategory


def test_adapter_parses_tr16x4_l350_from_query_text():
    adapter = ParametricTransmissionAdapter()
    query = PartQuery(
        part_no="SLP-P01",
        name_cn="丝杠 L350",
        material="Tr16×4, 45#钢",
        category="transmission",
        make_buy="自制",
        spec_envelope=(16.0, 16.0, 350.0),
    )

    result = adapter.resolve(
        query,
        {"template": "trapezoidal_lead_screw", "defaults": {"thread_length_mm": 230.0}},
    )

    assert result.status == "hit"
    assert result.kind == "codegen"
    assert result.adapter == "parametric_transmission"
    assert result.geometry_source == "PARAMETRIC_TEMPLATE"
    assert result.geometry_quality == "B"
    assert result.validated is True
    assert result.requires_model_review is False
    assert result.real_dims == (16.0, 16.0, 350.0)
    assert "make_trapezoidal_lead_screw" in result.body_code
    assert "outer_diameter_mm=16.0" in result.body_code
    assert "pitch_mm=4.0" in result.body_code
    assert "total_length_mm=350.0" in result.body_code


def test_adapter_keeps_null_thread_length_as_derived_value():
    adapter = ParametricTransmissionAdapter()
    query = PartQuery(
        part_no="P-001",
        name_cn="Lead screw",
        material="Tr12x3 L100",
        category="transmission",
        make_buy="自制",
    )

    result = adapter.resolve(
        query,
        {
            "template": "trapezoidal_lead_screw",
            "defaults": {
                "thread_length_mm": None,
                "lower_shaft_length_mm": 10.0,
                "upper_shaft_length_mm": 15.0,
            },
        },
    )

    assert result.status == "hit"
    assert "thread_length_mm=None" in result.body_code
    assert result.real_dims == (12.0, 12.0, 100.0)


def test_adapter_misses_unknown_template():
    adapter = ParametricTransmissionAdapter()
    query = PartQuery(
        part_no="P-001",
        name_cn="丝杠",
        material="Tr16x4",
        category="transmission",
        make_buy="自制",
    )

    result = adapter.resolve(query, {"template": "unknown"})

    assert result.status == "miss"


def test_default_resolver_registers_parametric_transmission_adapter():
    resolver = default_resolver(project_root=".")

    assert "parametric_transmission" in [adapter.name for adapter in resolver.adapters]


def test_resolver_infers_standard_transmission_for_exact_parametric_mapping():
    resolver = PartsResolver(
        registry={
            "mappings": [
                {
                    "match": {"part_no": "P-001"},
                    "adapter": "parametric_transmission",
                    "spec": {"template": "trapezoidal_lead_screw"},
                }
            ]
        },
        adapters=[ParametricTransmissionAdapter()],
    )
    query = PartQuery(
        part_no="P-001",
        name_cn="丝杠 L100",
        material="Tr12x3",
        category="transmission",
        make_buy="自制",
    )

    result = resolver.resolve(query)

    assert result.status == "hit"
    assert result.category == PartCategory.STANDARD_TRANSMISSION


def test_default_registry_routes_lead_screw_before_generic_transmission_fallback():
    resolver = default_resolver(project_root=".")
    query = PartQuery(
        part_no="P-002",
        name_cn="Lead screw L120",
        material="Tr16x4",
        category="transmission",
        make_buy="自制",
        spec_envelope=(16.0, 16.0, 120.0),
    )

    result = resolver.resolve(query)

    assert result.status == "hit"
    assert result.adapter == "parametric_transmission"
    assert result.geometry_source == "PARAMETRIC_TEMPLATE"


def test_emitted_parametric_std_module_adds_project_root_to_sys_path():
    from codegen.gen_std_parts import _emit_module_source

    adapter = ParametricTransmissionAdapter()
    query = PartQuery(
        part_no="P-001",
        name_cn="丝杠 L100",
        material="Tr12x3",
        category="transmission",
        make_buy="自制",
    )
    result = adapter.resolve(query, {"template": "trapezoidal_lead_screw"})

    source = _emit_module_source(
        {
            "part_no": "P-001",
            "name_cn": "丝杠 L100",
            "material": "Tr12x3",
            "make_buy": "自制",
        },
        "std_p001",
        "transmission",
        result,
    )

    assert "import sys" in source
    assert "_project_root" in source
    assert "adapters.parts.parametric_transmission" in source
