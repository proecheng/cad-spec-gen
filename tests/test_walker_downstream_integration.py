# tests/test_walker_downstream_integration.py
"""End-to-end test for the six-step granularity enforcement chain.

Walker → extract_part_envelopes → parse_envelopes → PartQuery →
JinjaPrimitiveAdapter. Without any one of the six steps, a
station_constraint envelope would silently size an individual std part.
"""
from __future__ import annotations


def test_station_constraint_not_used_as_part_size(tmp_path):
    """The invariant test: walker emits station_constraint; adapter rejects it."""
    # Step 1-2: build a synthetic CAD_SPEC.md with a station_constraint row
    spec_path = tmp_path / "CAD_SPEC.md"
    spec_path.write_text(
        "### 6.4 零件包络尺寸\n"
        "\n"
        "| 料号 | 零件名 | 类型 | 尺寸(mm) | 来源 | 粒度 |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| GIS-EE-002 | 工位1涂抹模块 | box | 60×40×290 | P2:walker:tier1 | station_constraint |\n",
        encoding="utf-8",
    )

    # Step 3: parse_envelopes reads it with granularity
    from codegen.gen_assembly import parse_envelopes
    envs = parse_envelopes(str(spec_path))
    assert envs["GIS-EE-002"]["granularity"] == "station_constraint"

    # Step 4: PartQuery is built with the granularity
    from parts_resolver import PartQuery
    from codegen.gen_std_parts import (
        _envelope_to_spec_envelope,
        _envelope_to_granularity,
    )
    env = envs["GIS-EE-002"]
    query = PartQuery(
        part_no="GIS-EE-002-05",  # a CHILD part inside the station
        name_cn="LEMO Connector",
        material="",
        category="connector",
        make_buy="外购",
        spec_envelope=_envelope_to_spec_envelope(env),
        spec_envelope_granularity=_envelope_to_granularity(env),
    )
    assert query.spec_envelope_granularity == "station_constraint"
    assert query.spec_envelope == (60.0, 40.0, 290.0)

    # Step 5: JinjaPrimitiveAdapter MUST NOT size the part as 60×40×290
    from adapters.parts.jinja_primitive_adapter import (
        _resolve_dims_from_spec_envelope_or_lookup,
    )
    dims = _resolve_dims_from_spec_envelope_or_lookup(query)

    # The bug would be: dims == {"w": 60, "d": 40, "h": 290}
    if dims is not None:
        assert dims.get("w") != 60.0 or dims.get("d") != 40.0 or dims.get("h") != 290.0, (
            "REGRESSION: station_constraint envelope leaked into per-part dims. "
            "The six-step granularity enforcement chain is broken — check which "
            "step dropped the tag."
        )
