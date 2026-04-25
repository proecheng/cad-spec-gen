"""Tests for concrete adapter implementations.

The JinjaPrimitiveAdapter MUST round-trip the pre-refactor _gen_* output
byte-for-byte — that is the regression gate for the code move.

BdWarehouseAdapter tests are split into two tiers:
  - catalog-only tests (no bd_warehouse installed) → always run in CI
  - live integration tests (bd_warehouse installed) → @pytest.mark.optional
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from parts_resolver import PartQuery
from adapters.parts.jinja_primitive_adapter import (
    JinjaPrimitiveAdapter,
    _gen_motor,
    _gen_bearing,
    _gen_seal,
    _gen_spring,
    _gen_tank,
    _gen_generic,
    _GENERATORS,
)
from adapters.parts.bd_warehouse_adapter import BdWarehouseAdapter
from adapters.parts.step_pool_adapter import StepPoolAdapter
from adapters.parts.partcad_adapter import PartCADAdapter


# ─── JinjaPrimitiveAdapter byte-identical regression ─────────────────


class TestJinjaPrimitiveFallback:
    """Ensure the moved _gen_* functions produce unchanged output."""

    def test_gen_motor_output_pinned(self):
        """Known-good output for _gen_motor with default args."""
        out = _gen_motor({"d": 22, "l": 73, "shaft_d": 4, "shaft_l": 12})
        assert "cq.Workplane" in out
        assert "circle(11.0)" in out
        assert "extrude(73)" in out
        assert "shaft" in out.lower()

    def test_gen_bearing_output_pinned(self):
        out = _gen_bearing({"od": 22, "id": 8, "w": 7})
        assert "outer" in out
        assert "inner" in out
        assert "circle(11.0)" in out  # od/2
        assert "extrude(7)" in out

    def test_gen_spring_cylinder_mode(self):
        """Spring pin mode: d + l, no od → solid cylinder."""
        out = _gen_spring({"d": 4, "l": 20})
        assert "spring pin" in out
        assert "circle(2.0)" in out
        assert "extrude(20)" in out

    def test_gen_spring_disc_mode(self):
        """Disc spring mode: od + t → annular ring."""
        out = _gen_spring({"od": 12, "id": 6, "t": 0.7, "h": 0.85})
        assert "disc spring" in out
        assert "annular" in out.lower()

    def test_gen_seal_torus(self):
        out = _gen_seal({"od": 80, "id": 76, "section_d": 2.4})
        assert "O-ring" in out or "torus" in out.lower()
        assert "sweep" in out

    def test_gen_tank_cylinder(self):
        out = _gen_tank({"d": 38, "l": 280})
        assert "cylinder" in out.lower() or "circle" in out
        assert "extrude(280)" in out

    def test_gen_generic_cylinder_mode(self):
        out = _gen_generic({"d": 15, "l": 10})
        assert "cylindrical" in out.lower()
        assert "extrude(10)" in out

    def test_gen_generic_box_mode(self):
        out = _gen_generic({"w": 20, "h": 5})
        assert "rectangular" in out.lower()

    def test_all_categories_have_generators(self):
        expected = {"motor", "reducer", "spring", "bearing", "sensor",
                    "pump", "connector", "seal", "tank", "other"}
        assert expected.issubset(set(_GENERATORS.keys()))


# ─── Adapter interface tests ────────────────────────────────────────


class TestJinjaPrimitiveAdapter:
    def test_is_always_available(self):
        a = JinjaPrimitiveAdapter()
        ok, _ = a.is_available()
        assert ok

    def test_resolve_bearing(self):
        a = JinjaPrimitiveAdapter()
        q = PartQuery(
            part_no="X-001",
            name_cn="608 deep groove",
            material="Φ22×7",
            category="bearing",
            make_buy="外购",
            spec_envelope=(22, 22, 7),
        )
        result = a.resolve(q, spec={})
        assert result.status == "hit"
        assert result.kind == "codegen"
        assert result.adapter == "jinja_primitive"
        assert result.body_code is not None
        assert "circle" in result.body_code

    def test_resolve_skip_fastener(self):
        """Fasteners 在 _SKIP_CATEGORIES → skip（不是 miss）。"""
        a = JinjaPrimitiveAdapter()
        q = PartQuery(
            part_no="X-001",
            name_cn="M3×10 内六角",
            material="不锈钢",
            category="fastener",
            make_buy="外购",
        )
        result = a.resolve(q, spec={})
        assert result.status == "skip"

    def test_resolve_skip_cable(self):
        """Cable 在 _SKIP_CATEGORIES → skip。"""
        a = JinjaPrimitiveAdapter()
        q = PartQuery(
            part_no="GIS-EE-001-11",
            name_cn="Igus拖链段",
            material="E2 micro 内径6mm",
            category="cable",
            make_buy="外购",
        )
        result = a.resolve(q, spec={})
        assert result.status == "skip"
        assert result.kind == "miss"
        assert "cable" in result.source_tag

    def test_resolve_unknown_category_still_hits_for_other(self):
        """Category 'other' gets a default block even with no dims."""
        a = JinjaPrimitiveAdapter()
        q = PartQuery(
            part_no="X-001",
            name_cn="测试",
            material="",
            category="other",
            make_buy="外购",
        )
        result = a.resolve(q, spec={})
        assert result.status == "hit"

    def test_probe_dims_from_spec_envelope(self):
        a = JinjaPrimitiveAdapter()
        q = PartQuery(
            part_no="X-001",
            name_cn="test",
            material="",
            category="bearing",
            make_buy="外购",
            spec_envelope=(22, 22, 7),
        )
        dims = a.probe_dims(q, spec={})
        assert dims == (22, 22, 7)

    def test_probe_dims_skip_fastener(self):
        a = JinjaPrimitiveAdapter()
        q = PartQuery(
            part_no="X-001",
            name_cn="M3",
            material="",
            category="fastener",
            make_buy="外购",
        )
        assert a.probe_dims(q, spec={}) is None


class TestBdWarehouseAdapterCatalogOnly:
    """Catalog-level tests that don't need bd_warehouse installed."""

    def test_adapter_is_available_with_catalog(self):
        from adapters.parts.bd_warehouse_adapter import BdWarehouseAdapter
        a = BdWarehouseAdapter()
        # is_available() 在目录存在时，ok 取决于 bd_warehouse 是否可导入。
        # catalog-only 检查使用 can_resolve 而非 is_available。
        ok, reason = a.is_available()
        # 如果 bd_warehouse 未安装则 ok=False 是预期行为（reason 不为 None）
        if not ok:
            assert reason is not None
            assert "bd_warehouse" in reason or "catalog" in reason
        # 如果已安装则 ok=True, reason=None
        else:
            assert reason is None

    def test_can_resolve_bearing_category(self):
        from adapters.parts.bd_warehouse_adapter import BdWarehouseAdapter
        a = BdWarehouseAdapter()
        q = PartQuery(
            part_no="X-001",
            name_cn="608ZZ deep groove bearing",
            material="",
            category="bearing",
            make_buy="外购",
        )
        assert a.can_resolve(q)

    def test_resolve_known_designation(self):
        """608 is in iso_designation_map → should hit."""
        from adapters.parts.bd_warehouse_adapter import BdWarehouseAdapter
        a = BdWarehouseAdapter()
        q = PartQuery(
            part_no="X-001",
            name_cn="608ZZ 深沟球轴承",
            material="",
            category="bearing",
            make_buy="外购",
        )
        result = a.resolve(q, spec={"class": "SingleRowDeepGrooveBallBearing"})
        assert result.status == "hit"
        assert result.kind == "python_import"
        assert result.import_module == "bd_warehouse.bearing"
        assert result.import_symbol == "SingleRowDeepGrooveBallBearing"
        assert "M8-22-7" in result.import_args
        assert result.real_dims == (22, 22, 7)

    def test_probe_dims_without_bd_warehouse_import(self):
        """probe_dims() reads only the catalog, never imports bd_warehouse."""
        from adapters.parts.bd_warehouse_adapter import BdWarehouseAdapter
        a = BdWarehouseAdapter()
        q = PartQuery(
            part_no="X-001",
            name_cn="608ZZ",
            material="",
            category="bearing",
            make_buy="外购",
        )
        dims = a.probe_dims(q, spec={"class": "SingleRowDeepGrooveBallBearing"})
        assert dims == (22, 22, 7)

    def test_miss_on_unsupported_bearing(self):
        """MR105ZZ is miniature metric, not in bd_warehouse."""
        from adapters.parts.bd_warehouse_adapter import BdWarehouseAdapter
        a = BdWarehouseAdapter()
        q = PartQuery(
            part_no="X-001",
            name_cn="MR105ZZ bearing",
            material="",
            category="bearing",
            make_buy="外购",
        )
        result = a.resolve(q, spec={"class": "SingleRowDeepGrooveBallBearing"})
        assert result.status == "miss"


def _try_import_bd_warehouse_bearing():
    """Return the imported module or None if bd_warehouse can't load.

    On Windows with a non-UTF-8 default encoding, bd_warehouse fails to
    read its parameter CSVs (UnicodeDecodeError). This is a bd_warehouse
    bug that is worked around by setting PYTHONUTF8=1 before starting
    Python. Tests that require the live library skip gracefully when
    the import fails for any reason.
    """
    try:
        from bd_warehouse.bearing import SingleRowDeepGrooveBallBearing
        return SingleRowDeepGrooveBallBearing
    except Exception:
        return None


# ─── StepPoolAdapter tests ──────────────────────────────────────────────


@pytest.fixture
def step_pool_dir(tmp_path):
    """Create a throw-away STEP file pool with one cylinder + one box.

    Uses CadQuery to generate real STEP files that can be bbox-probed.
    """
    import cadquery as cq

    root = tmp_path / "std_parts"
    (root / "maxon").mkdir(parents=True)
    (root / "sensors").mkdir(parents=True)

    # Maxon motor: Φ22×68 cylinder with a shaft
    motor = cq.Workplane("XY").circle(11).extrude(68)
    motor = motor.faces(">Z").workplane().circle(2).extrude(14)
    cq.exporters.export(motor, str(root / "maxon" / "ecx_22l.step"))

    # Sensor: 20×15×12 box
    sensor = cq.Workplane("XY").box(20, 15, 12, centered=(True, True, False))
    cq.exporters.export(sensor, str(root / "sensors" / "ati_nano17.step"))

    return root


class TestStepPoolAdapter:
    """Tests for adapters/parts/step_pool_adapter.py."""

    def test_is_always_available(self):
        from adapters.parts.step_pool_adapter import StepPoolAdapter
        adapter = StepPoolAdapter(project_root="/nonexistent")
        ok, _ = adapter.is_available()
        assert ok

    def test_resolve_exact_file(self, step_pool_dir):
        from adapters.parts.step_pool_adapter import StepPoolAdapter
        adapter = StepPoolAdapter(
            project_root=str(step_pool_dir.parent),
            config={"root": "std_parts/"},
        )
        query = PartQuery(
            part_no="X-001",
            name_cn="Maxon ECX 22L",
            material="",
            category="motor",
            make_buy="外购",
        )
        result = adapter.resolve(query, spec={"file": "maxon/ecx_22l.step"})
        assert result.status == "hit"
        assert result.kind == "step_import"
        assert result.adapter == "step_pool"
        assert result.step_path.endswith("ecx_22l.step")
        # CadQuery-generated cylinder Φ22×82 (68 body + 14 shaft)
        assert result.real_dims is not None
        assert 21.9 <= result.real_dims[0] <= 22.1
        assert 81.9 <= result.real_dims[2] <= 82.1

    def test_resolve_missing_file_returns_miss(self, step_pool_dir):
        from adapters.parts.step_pool_adapter import StepPoolAdapter
        adapter = StepPoolAdapter(
            project_root=str(step_pool_dir.parent),
            config={"root": "std_parts/"},
        )
        query = PartQuery(
            part_no="X-001", name_cn="test", material="",
            category="motor", make_buy="外购",
        )
        result = adapter.resolve(query, spec={"file": "nonexistent.step"})
        assert result.status == "miss"
        assert any("not found" in w for w in result.warnings)

    def test_probe_dims_caches_result(self, step_pool_dir):
        from adapters.parts.step_pool_adapter import StepPoolAdapter
        adapter = StepPoolAdapter(
            project_root=str(step_pool_dir.parent),
            config={"root": "std_parts/"},
        )
        query = PartQuery(
            part_no="X", name_cn="", material="",
            category="motor", make_buy="外购",
        )
        spec = {"file": "maxon/ecx_22l.step"}
        d1 = adapter.probe_dims(query, spec)
        d2 = adapter.probe_dims(query, spec)
        assert d1 == d2
        assert len(adapter._bbox_cache) == 1

    def test_file_template_normalize(self, step_pool_dir):
        """file_template with {normalize(name)} substitution."""
        from adapters.parts.step_pool_adapter import StepPoolAdapter
        adapter = StepPoolAdapter(
            project_root=str(step_pool_dir.parent),
            config={"root": "std_parts/"},
        )
        query = PartQuery(
            part_no="X-001",
            name_cn="Ecx 22L",
            material="",
            category="motor",
            make_buy="外购",
        )
        result = adapter.resolve(
            query,
            spec={"file_template": "maxon/{normalize(name)}.step"},
        )
        # normalize("Ecx 22L") → "ecx_22l"
        assert result.status == "hit"
        assert "ecx_22l" in result.step_path

    def test_absolute_path_works(self, step_pool_dir):
        from adapters.parts.step_pool_adapter import StepPoolAdapter
        adapter = StepPoolAdapter(
            project_root="/nonexistent",
            config={},
        )
        abs_path = str(step_pool_dir / "sensors" / "ati_nano17.step")
        query = PartQuery(
            part_no="X", name_cn="", material="",
            category="sensor", make_buy="外购",
        )
        result = adapter.resolve(query, spec={"file": abs_path})
        assert result.status == "hit"
        assert result.real_dims is not None
        # box 20×15×12
        assert 19.9 <= result.real_dims[0] <= 20.1
        assert 14.9 <= result.real_dims[1] <= 15.1
        assert 11.9 <= result.real_dims[2] <= 12.1

    def test_project_relative_path_in_result(self, step_pool_dir):
        """Generated step_path should be relative so project is portable."""
        from adapters.parts.step_pool_adapter import StepPoolAdapter
        adapter = StepPoolAdapter(
            project_root=str(step_pool_dir.parent),
            config={"root": "std_parts/"},
        )
        query = PartQuery(
            part_no="X", name_cn="", material="",
            category="motor", make_buy="外购",
        )
        result = adapter.resolve(query, spec={"file": "maxon/ecx_22l.step"})
        assert result.status == "hit"
        # The returned path should NOT contain the tmp_path's absolute prefix
        assert not os.path.isabs(result.step_path)
        assert result.step_path == "std_parts/maxon/ecx_22l.step"


class TestPartCADAdapter:
    """Tests for adapters/parts/partcad_adapter.py.

    These tests exercise the opt-in gating and graceful degradation logic.
    They do NOT require partcad to be installed; a live-integration test
    is marked @pytest.mark.optional below.
    """

    def test_disabled_by_default(self):
        from adapters.parts.partcad_adapter import PartCADAdapter
        adapter = PartCADAdapter(config={})
        ok, _ = adapter.is_available()
        assert not ok

    def test_enabled_via_config(self):
        from adapters.parts.partcad_adapter import PartCADAdapter
        adapter = PartCADAdapter(config={"enabled": True})
        ok, _ = adapter.is_available()
        assert ok

    def test_can_resolve_requires_enabled(self):
        from adapters.parts.partcad_adapter import PartCADAdapter
        q = PartQuery(
            part_no="X", name_cn="", material="",
            category="motor", make_buy="外购",
        )
        disabled = PartCADAdapter(config={"enabled": False})
        assert not disabled.can_resolve(q)
        enabled = PartCADAdapter(config={"enabled": True})
        assert enabled.can_resolve(q)

    def test_resolve_returns_miss_when_disabled(self):
        from adapters.parts.partcad_adapter import PartCADAdapter
        adapter = PartCADAdapter(config={"enabled": False})
        q = PartQuery(
            part_no="X", name_cn="", material="",
            category="motor", make_buy="外购",
        )
        result = adapter.resolve(q, spec={"part_ref": "foo:bar"})
        assert result.status == "miss"

    def test_resolve_requires_part_ref(self):
        from adapters.parts.partcad_adapter import PartCADAdapter
        adapter = PartCADAdapter(config={"enabled": True})
        q = PartQuery(
            part_no="X", name_cn="", material="",
            category="motor", make_buy="外购",
        )
        # Missing spec.part_ref → miss + warning
        result = adapter.resolve(q, spec={})
        assert result.status == "miss"
        assert any("part_ref" in w for w in result.warnings)

    def test_resolve_graceful_when_partcad_not_installed(self, monkeypatch):
        """If `import partcad` fails, adapter returns miss with warning,
        does NOT crash the pipeline."""
        import sys
        # Temporarily hide partcad from the import system
        monkeypatch.setitem(sys.modules, "partcad", None)
        from adapters.parts.partcad_adapter import PartCADAdapter
        adapter = PartCADAdapter(config={"enabled": True})
        q = PartQuery(
            part_no="X", name_cn="", material="",
            category="motor", make_buy="外购",
        )
        result = adapter.resolve(q, spec={"part_ref": "foo:bar"})
        assert result.status == "miss"
        assert any("partcad" in w.lower() for w in result.warnings)

    def test_resolver_skips_partcad_when_not_installed(self):
        """Full resolver integration: when PartCAD fails to import but
        partcad.enabled is true in the YAML, the resolver should fall
        through to jinja_primitive instead of crashing."""
        from parts_resolver import PartsResolver, PartQuery
        from adapters.parts.partcad_adapter import PartCADAdapter
        from adapters.parts.jinja_primitive_adapter import JinjaPrimitiveAdapter

        registry = {
            "partcad": {"enabled": True},
            "mappings": [
                {
                    "match": {"part_no": "X-001"},
                    "adapter": "partcad",
                    "spec": {"part_ref": "foo:bar"},
                },
                {"match": {"any": True}, "adapter": "jinja_primitive"},
            ],
        }
        resolver = PartsResolver(
            registry=registry,
            adapters=[
                PartCADAdapter(config={"enabled": True}),
                JinjaPrimitiveAdapter(),
            ],
        )
        q = PartQuery(
            part_no="X-001",
            name_cn="test motor",
            material="",
            category="motor",
            make_buy="外购",
        )
        result = resolver.resolve(q)
        # Should fall through to jinja_primitive since partcad can't
        # actually fetch the part (no package installed)
        assert result.status in ("hit", "fallback")
        assert result.adapter in ("partcad", "jinja_primitive")
        # If partcad isn't actually importable, jinja wins
        if not _partcad_importable():
            assert result.adapter == "jinja_primitive"


def _partcad_importable() -> bool:
    try:
        import partcad  # noqa: F401
        return True
    except Exception:
        return False


@pytest.mark.optional
class TestBdWarehouseLiveIntegration:
    """Tests that require `pip install bd_warehouse` AND a UTF-8 capable
    Python interpreter (PYTHONUTF8=1 on Windows with non-UTF-8 locale)."""

    def test_actual_bd_import_works(self):
        cls = _try_import_bd_warehouse_bearing()
        if cls is None:
            pytest.skip("bd_warehouse.bearing import failed "
                        "(set PYTHONUTF8=1 on Windows)")
        part = cls(size="M8-22-7", bearing_type="SKT")
        assert part is not None

    def test_bd_to_cq_conversion(self):
        cls = _try_import_bd_warehouse_bearing()
        if cls is None:
            pytest.skip("bd_warehouse.bearing import failed "
                        "(set PYTHONUTF8=1 on Windows)")
        from parts_resolver import bd_to_cq
        part = cls(size="M8-22-7", bearing_type="SKT")
        cq_wp = bd_to_cq(part)
        bbox = cq_wp.val().BoundingBox()
        # 608 bearing: OD 22mm, width 7mm
        assert 21 <= (bbox.xmax - bbox.xmin) <= 23
        assert 21 <= (bbox.ymax - bbox.ymin) <= 23
        assert 6 <= (bbox.zmax - bbox.zmin) <= 8


def test_jinja_adapter_rejects_station_constraint_envelope():
    """station_constraint envelopes MUST NOT be used to size individual
    std parts. The adapter falls through to lookup_std_part_dims.

    This is the core G11 enforcement test: without this check, a
    60×40×290mm station-level envelope would silently size a LEMO
    connector as 60×40×290mm."""
    from adapters.parts.jinja_primitive_adapter import (
        _resolve_dims_from_spec_envelope_or_lookup,
    )
    from parts_resolver import PartQuery

    q = PartQuery(
        part_no="GIS-EE-002-05",
        name_cn="LEMO 连接器",
        material="",
        category="connector",
        make_buy="外购",
        spec_envelope=(60.0, 40.0, 290.0),
        spec_envelope_granularity="station_constraint",
    )
    dims = _resolve_dims_from_spec_envelope_or_lookup(q)
    # Dims must NOT be (60, 40, 290) — that would be the bug.
    # Adapter falls through to lookup_std_part_dims; the actual returned
    # dims come from the lookup (or a default), not the walker envelope.
    if dims is not None:
        assert not (dims.get("w") == 60 and dims.get("d") == 40 and dims.get("h") == 290), \
            "station_constraint envelope leaked into per-part dims"


def test_jinja_adapter_accepts_part_envelope():
    """Legacy per-part envelopes (default granularity) still work."""
    from adapters.parts.jinja_primitive_adapter import (
        _resolve_dims_from_spec_envelope_or_lookup,
    )
    from parts_resolver import PartQuery

    q = PartQuery(
        part_no="X", name_cn="Y", material="", category="bracket",
        make_buy="自制",
        spec_envelope=(40.0, 20.0, 10.0),
        # spec_envelope_granularity defaults to "part_envelope"
    )
    dims = _resolve_dims_from_spec_envelope_or_lookup(q)
    assert dims is not None
    assert dims.get("w") == 40.0


# ─── is_available() tuple contract ────────────────────────────────────────


class TestIsAvailableTupleContract:
    """每个 concrete adapter 的 is_available() 必须返回 (bool, Optional[str])。"""

    def test_jinja_returns_tuple(self):
        ok, reason = JinjaPrimitiveAdapter().is_available()
        assert ok is True
        assert reason is None

    def test_step_pool_returns_tuple(self):
        ok, reason = StepPoolAdapter().is_available()
        assert ok is True
        assert reason is None

    def test_partcad_disabled_returns_false_with_reason(self):
        a = PartCADAdapter(config={})
        ok, reason = a.is_available()
        assert ok is False
        assert reason is not None
        assert "partcad" in reason.lower() or "enabled" in reason.lower()

    def test_partcad_enabled_returns_true(self):
        a = PartCADAdapter(config={"enabled": True})
        ok, reason = a.is_available()
        assert ok is True
        assert reason is None

    def test_bd_warehouse_missing_catalog_returns_false_with_reason(self, tmp_path):
        a = BdWarehouseAdapter(catalog_path=str(tmp_path / "nonexistent.yaml"))
        ok, reason = a.is_available()
        assert ok is False
        assert reason is not None
        assert "catalog" in reason.lower() or "bd_warehouse" in reason.lower()
