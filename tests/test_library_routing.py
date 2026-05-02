from types import SimpleNamespace

from parts_resolver import PartQuery


class _ProbeAdapter:
    name = "parametric_transmission"

    def __init__(self, dims):
        self._dims = dims

    def is_available(self):
        return True, None

    def probe_dims(self, query, spec):
        return self._dims


def test_library_routing_identifies_resolver_routed_custom_lead_screw():
    from codegen.library_routing import build_library_part_query, is_library_routed_row

    rules = [
        {
            "match": {"category": "transmission", "keyword_contains": ["丝杠"]},
            "adapter": "parametric_transmission",
        }
    ]
    resolver = SimpleNamespace(
        matching_rules=lambda query: rules,
        adapters=[_ProbeAdapter((16.0, 16.0, 350.0))],
    )
    part = {
        "part_no": "TST-P01",
        "name_cn": "丝杠 L350",
        "material": "Tr16×4, 45#钢",
        "make_buy": "自制",
    }

    query = build_library_part_query(
        part,
        category="transmission",
        envelope=(16.0, 16.0, 350.0),
        project_root=".",
    )

    assert isinstance(query, PartQuery)
    assert query.part_no == "TST-P01"
    assert query.spec_envelope == (16.0, 16.0, 350.0)
    assert is_library_routed_row(
        part,
        category="transmission",
        resolver=resolver,
        query=query,
    ) is True


def test_library_routing_does_not_route_plain_custom_plate():
    from codegen.library_routing import build_library_part_query, is_library_routed_row

    resolver = SimpleNamespace(matching_rules=lambda query: [])
    part = {
        "part_no": "TST-100",
        "name_cn": "安装板",
        "material": "6061-T6 铝 100×80×8mm",
        "make_buy": "自制",
    }
    query = build_library_part_query(
        part,
        category="other",
        envelope=(100.0, 80.0, 8.0),
        project_root=".",
    )

    assert is_library_routed_row(
        part,
        category="other",
        resolver=resolver,
        query=query,
    ) is False


def test_library_routing_does_not_route_when_candidate_cannot_probe_geometry():
    from codegen.library_routing import build_library_part_query, is_library_routed_row

    rules = [
        {
            "match": {"category": "transmission", "keyword_contains": ["丝杠"]},
            "adapter": "parametric_transmission",
        }
    ]
    resolver = SimpleNamespace(
        matching_rules=lambda query: rules,
        adapters=[_ProbeAdapter(None)],
    )
    part = {
        "part_no": "SLP-P01",
        "name_cn": "丝杠 L350",
        "material": "45#钢 Φ16×350mm",
        "make_buy": "自制",
    }
    query = build_library_part_query(
        part,
        category="transmission",
        envelope=(16.0, 16.0, 350.0),
        project_root=".",
    )

    assert is_library_routed_row(
        part,
        category="transmission",
        resolver=resolver,
        query=query,
    ) is False


def test_std_module_naming_is_shared_for_library_routed_custom_rows():
    from codegen.library_routing import library_make_function, library_module_name

    assert library_module_name("SLP-P01") == "std_p01"
    assert library_make_function("SLP-P01") == "make_std_p01"
