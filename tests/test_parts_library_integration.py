"""Multi-adapter integration tests for the parts library system.

Where the per-adapter tests in `test_parts_adapters.py` exercise each adapter
in isolation, this file proves that **all four adapters cooperate inside a
single resolver instance** — the configuration that production projects
actually run with.

Three layers of integration are covered:

1. **Resolver dispatch layer** (`TestMultiAdapterDispatch`)
   One PartsResolver instance, one registry, four BOM rows that should each
   route to a different adapter (step_pool / bd_warehouse / partcad /
   jinja_primitive). Verifies first-hit-wins ordering and graceful skip when
   an adapter is unavailable.

2. **Module emission layer** (`TestMultiAdapterEmission`)
   For each `ResolveResult.kind`, drive `gen_std_parts._emit_module_source`
   directly and assert the generated module text has the right shape
   (importStep call / lazy library import / inline jinja code).

3. **End-to-end pipeline layer** (`TestEndToEndPipeline`)
   Monkeypatch `parse_bom_tree` + `parse_envelopes` and call the public
   `generate_std_part_files()` function. Verifies that one invocation
   produces files routed to multiple adapters AND that each generated file
   parses as valid Python.
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from parts_resolver import PartQuery, PartsResolver, ResolveResult
from adapters.parts.base import PartsAdapter
from adapters.parts.jinja_primitive_adapter import JinjaPrimitiveAdapter
from adapters.parts.bd_warehouse_adapter import BdWarehouseAdapter
from adapters.parts.step_pool_adapter import StepPoolAdapter
from adapters.parts.partcad_adapter import PartCADAdapter


# ═══ Shared fixtures ════════════════════════════════════════════════════════


@pytest.fixture
def step_pool_dir(tmp_path):
    """Build a tiny STEP file pool with one cylinder + one box.

    Mirrors the fixture in test_parts_adapters.py but kept local to make
    this file runnable on its own.
    """
    import cadquery as cq

    root = tmp_path / "std_parts"
    (root / "maxon").mkdir(parents=True)
    (root / "sensors").mkdir(parents=True)

    # Maxon ECX 22L stand-in: Φ22×68 cylinder + Φ4×14 shaft
    motor = cq.Workplane("XY").circle(11).extrude(68)
    motor = motor.faces(">Z").workplane().circle(2).extrude(14)
    cq.exporters.export(motor, str(root / "maxon" / "ecx_22l.step"))

    # ATI Nano17 stand-in: 20×15×12 box
    sensor = cq.Workplane("XY").box(20, 15, 12, centered=(True, True, False))
    cq.exporters.export(sensor, str(root / "sensors" / "ati_nano17.step"))

    return root


@pytest.fixture
def multi_adapter_registry():
    """A registry that routes four distinct BOM rows to four distinct adapters.

    Rule order is significant — the resolver picks the first match top-down,
    so more-specific rules go first.
    """
    return {
        "step_pool": {"root": "std_parts/"},
        "bd_warehouse": {"enabled": True},
        "partcad": {"enabled": True},
        "mappings": [
            # 1. Exact part_no → STEP pool (most specific)
            {
                "match": {"part_no": "GIS-EE-001-05"},
                "adapter": "step_pool",
                "spec": {"file": "maxon/ecx_22l.step"},
            },
            # 2. Bearing category → bd_warehouse with explicit class
            {
                "match": {"category": "bearing", "name_contains": ["608"]},
                "adapter": "bd_warehouse",
                "spec": {"class": "SingleRowDeepGrooveBallBearing"},
            },
            # 3. Connector category → partcad (opt-in, may fall through)
            {
                "match": {"category": "connector"},
                "adapter": "partcad",
                "spec": {"part_ref": "demo_pkg:lemo_fgg_0b"},
            },
            # 4. Anything else → jinja_primitive (terminal fallback)
            {"match": {"any": True}, "adapter": "jinja_primitive"},
        ],
    }


def _fake_partcad_adapter():
    """Build a fake PartCAD adapter that always reports a hit.

    Production tests should not assume partcad is installed. This stand-in
    lets us prove the dispatch path works **as if** partcad were available,
    without depending on the real package.
    """

    class FakePartCAD(PartsAdapter):
        name = "partcad"

        def __init__(self):
            self.calls = 0

        def is_available(self) -> tuple[bool, None]:
            return True, None

        def can_resolve(self, query) -> bool:
            return True

        def resolve(self, query, spec: dict):
            self.calls += 1
            part_ref = spec.get("part_ref", "")
            if not part_ref:
                return ResolveResult.miss()
            pkg, _, name = part_ref.partition(":")
            return ResolveResult(
                status="hit",
                kind="python_import",
                adapter="partcad",
                import_module="partcad",
                import_symbol="get_part_cadquery",
                import_args=f'{part_ref!r}',
                real_dims=(15.0, 15.0, 30.0),
                source_tag=f"PC:{part_ref}",
            )

        def probe_dims(self, query, spec: dict):
            return (15.0, 15.0, 30.0)

    return FakePartCAD()


# ═══ Layer 1 — Resolver dispatch ════════════════════════════════════════════


class TestMultiAdapterDispatch:
    """Single resolver instance routing to four different adapters."""

    def test_four_adapters_dispatch_correctly(
        self, step_pool_dir, multi_adapter_registry
    ):
        """Four BOM rows → four different adapter wins, all in one resolver."""
        fake_pc = _fake_partcad_adapter()
        resolver = PartsResolver(
            project_root=str(step_pool_dir.parent),
            registry=multi_adapter_registry,
            adapters=[
                StepPoolAdapter(
                    project_root=str(step_pool_dir.parent),
                    config={"root": "std_parts/"},
                ),
                BdWarehouseAdapter(),
                fake_pc,
                JinjaPrimitiveAdapter(),
            ],
        )

        # Row 1 — exact part_no → step_pool
        q_motor = PartQuery(
            part_no="GIS-EE-001-05",
            name_cn="Maxon ECX SPEED 22L 减速电机",
            material="",
            category="motor",
            make_buy="外购",
        )
        r_motor = resolver.resolve(q_motor)
        assert r_motor.adapter == "step_pool"
        assert r_motor.kind == "step_import"
        assert r_motor.step_path.endswith("ecx_22l.step")

        # Row 2 — bearing category + 608 keyword → bd_warehouse
        q_bearing = PartQuery(
            part_no="GIS-EE-002-11",
            name_cn="608ZZ 深沟球轴承",
            material="",
            category="bearing",
            make_buy="外购",
        )
        r_bearing = resolver.resolve(q_bearing)
        assert r_bearing.adapter == "bd_warehouse"
        assert r_bearing.kind == "python_import"
        assert r_bearing.import_module == "bd_warehouse.bearing"
        assert "M8-22-7" in r_bearing.import_args

        # Row 3 — connector category → partcad (using fake adapter)
        q_conn = PartQuery(
            part_no="GIS-EE-003-08",
            name_cn="LEMO FGG.0B 连接器",
            material="",
            category="connector",
            make_buy="外购",
        )
        r_conn = resolver.resolve(q_conn)
        assert r_conn.adapter == "partcad"
        assert r_conn.kind == "python_import"
        assert "demo_pkg:lemo_fgg_0b" in r_conn.import_args
        assert fake_pc.calls == 1

        # Row 4 — unmapped category → terminal jinja_primitive fallback
        q_other = PartQuery(
            part_no="GIS-EE-004-99",
            name_cn="某种容器",
            material="304不锈钢 Φ38×120mm",
            category="tank",
            make_buy="外购",
        )
        r_other = resolver.resolve(q_other)
        assert r_other.adapter == "jinja_primitive"
        assert r_other.kind == "codegen"
        assert r_other.body_code is not None

        # Summary should show all four adapters used in one session
        summary = resolver.summary()
        assert summary == {
            "step_pool": 1,
            "bd_warehouse": 1,
            "partcad": 1,
            "jinja_primitive": 1,
        }

    def test_partcad_unavailable_falls_through_to_jinja(
        self, step_pool_dir, multi_adapter_registry
    ):
        """When the real PartCADAdapter has no `partcad` package installed,
        a connector BOM row should silently fall through to jinja_primitive
        instead of crashing the pipeline.
        """
        # Use the REAL PartCADAdapter — without partcad installed it will
        # report unavailable and the rule simply doesn't match.
        resolver = PartsResolver(
            project_root=str(step_pool_dir.parent),
            registry=multi_adapter_registry,
            adapters=[
                StepPoolAdapter(
                    project_root=str(step_pool_dir.parent),
                    config={"root": "std_parts/"},
                ),
                BdWarehouseAdapter(),
                PartCADAdapter(config={"enabled": True}),
                JinjaPrimitiveAdapter(),
            ],
        )

        q_conn = PartQuery(
            part_no="GIS-EE-003-08",
            name_cn="LEMO FGG.0B 连接器",
            material="",
            category="connector",
            make_buy="外购",
        )
        result = resolver.resolve(q_conn)

        # Either partcad is genuinely installed and wins, OR the resolver
        # falls through to jinja_primitive — both outcomes are valid.
        assert result.adapter in ("partcad", "jinja_primitive")
        # If partcad isn't actually importable, jinja must have caught it
        try:
            import partcad  # noqa: F401
            partcad_importable = True
        except Exception:
            partcad_importable = False
        if not partcad_importable:
            assert result.adapter == "jinja_primitive"

    def test_bd_warehouse_miss_falls_through_to_jinja(
        self, step_pool_dir, multi_adapter_registry
    ):
        """A bearing whose designation is NOT in the bd_warehouse catalog
        (e.g. miniature MR105ZZ) must continue past the bearing rule and
        eventually land on jinja_primitive.
        """
        resolver = PartsResolver(
            project_root=str(step_pool_dir.parent),
            registry=multi_adapter_registry,
            adapters=[
                StepPoolAdapter(
                    project_root=str(step_pool_dir.parent),
                    config={"root": "std_parts/"},
                ),
                BdWarehouseAdapter(),
                JinjaPrimitiveAdapter(),
            ],
        )

        # MR105ZZ is miniature; bearing rule has name_contains=["608"], so
        # this query never matches the bd_warehouse rule and goes straight
        # to the terminal fallback.
        q = PartQuery(
            part_no="GIS-EE-002-22",
            name_cn="MR105ZZ 微型轴承",
            material="Φ10×4",
            category="bearing",
            make_buy="外购",
            spec_envelope=(10, 10, 4),
        )
        result = resolver.resolve(q)
        assert result.adapter == "jinja_primitive"
        assert result.kind == "codegen"

    def test_resolver_summary_after_mixed_workload(
        self, step_pool_dir, multi_adapter_registry
    ):
        """Run a 6-part workload (2 motors + 2 bearings + 2 fallbacks) and
        verify the summary counts the adapter mix correctly. This is the
        observability surface that production projects rely on to spot a
        misconfigured registry.
        """
        resolver = PartsResolver(
            project_root=str(step_pool_dir.parent),
            registry=multi_adapter_registry,
            adapters=[
                StepPoolAdapter(
                    project_root=str(step_pool_dir.parent),
                    config={"root": "std_parts/"},
                ),
                BdWarehouseAdapter(),
                JinjaPrimitiveAdapter(),
            ],
        )

        # 2 motors → step_pool
        for pno in ("GIS-EE-001-05", "GIS-EE-001-05"):  # same part_no twice
            resolver.resolve(PartQuery(
                part_no=pno, name_cn="Maxon", material="",
                category="motor", make_buy="外购"))

        # 2 bearings → bd_warehouse
        for pno in ("GIS-EE-002-11", "GIS-EE-002-12"):
            resolver.resolve(PartQuery(
                part_no=pno, name_cn="608ZZ", material="",
                category="bearing", make_buy="外购"))

        # 2 fallbacks → jinja_primitive
        for pno in ("GIS-EE-009-01", "GIS-EE-009-02"):
            resolver.resolve(PartQuery(
                part_no=pno, name_cn="测试件", material="",
                category="other", make_buy="外购"))

        summary = resolver.summary()
        assert summary.get("step_pool") == 2
        assert summary.get("bd_warehouse") == 2
        assert summary.get("jinja_primitive") == 2


# ═══ Layer 2 — Module emission ══════════════════════════════════════════════


class TestMultiAdapterEmission:
    """gen_std_parts._emit_module_source must produce a valid Python module
    for every ResolveResult.kind. Each kind has a different code shape but
    they all expose make_*() returning a cq.Workplane."""

    def _bom_part(self, part_no: str, name_cn: str = "test part") -> dict:
        return {
            "part_no": part_no,
            "name_cn": name_cn,
            "material": "Φ22×68",
            "make_buy": "外购",
            "is_assembly": False,
        }

    def test_emit_step_import_module(self, step_pool_dir):
        from codegen.gen_std_parts import _emit_module_source

        result = ResolveResult(
            status="hit",
            kind="step_import",
            adapter="step_pool",
            step_path="std_parts/maxon/ecx_22l.step",
            real_dims=(22.0, 22.0, 82.0),
            source_tag="STEP:maxon/ecx_22l.step",
        )
        src = _emit_module_source(
            self._bom_part("GIS-EE-001-05", "Maxon ECX 22L"),
            "std_ee_001_05",
            "motor",
            result,
        )
        # Must compile as valid Python
        ast.parse(src)
        # Must contain the STEP import call
        assert "cq.importers.importStep" in src
        assert "ecx_22l.step" in src
        assert "def make_std_ee_001_05" in src
        # Must NOT contain the legacy jinja header
        assert "Auto-generated by codegen/gen_std_parts.py via parts_resolver" in src
        assert "真实 STEP 导入件" in src
        assert "simplified representation" not in src

    def test_emit_python_import_module_bd_warehouse(self):
        from codegen.gen_std_parts import _emit_module_source

        result = ResolveResult(
            status="hit",
            kind="python_import",
            adapter="bd_warehouse",
            import_module="bd_warehouse.bearing",
            import_symbol="SingleRowDeepGrooveBallBearing",
            import_args="size='M8-22-7', bearing_type='SKT'",
            real_dims=(22.0, 22.0, 7.0),
            source_tag="BW:SingleRowDeepGrooveBallBearing(M8-22-7)",
        )
        src = _emit_module_source(
            self._bom_part("GIS-EE-002-11", "608ZZ"),
            "std_ee_002_11",
            "bearing",
            result,
        )
        ast.parse(src)
        # bd_warehouse path inlines the _bd_to_cq() helper for self-containment
        assert "_bd_to_cq" in src
        assert "from bd_warehouse.bearing import SingleRowDeepGrooveBallBearing" in src
        assert "M8-22-7" in src
        assert "def make_std_ee_002_11" in src

    def test_emit_python_import_module_partcad(self):
        from codegen.gen_std_parts import _emit_module_source

        result = ResolveResult(
            status="hit",
            kind="python_import",
            adapter="partcad",
            import_module="partcad",
            import_symbol="get_part_cadquery",
            import_args="'demo_pkg:lemo_fgg_0b'",
            real_dims=(15.0, 15.0, 30.0),
            source_tag="PC:demo_pkg:lemo_fgg_0b",
        )
        src = _emit_module_source(
            self._bom_part("GIS-EE-003-08", "LEMO FGG.0B"),
            "std_ee_003_08",
            "connector",
            result,
        )
        ast.parse(src)
        # partcad path uses pc.get_part_cadquery() returning a cq.Solid directly
        assert "import partcad as pc" in src
        assert "pc.get_part_cadquery" in src
        # partcad path does NOT inline _bd_to_cq (that's bd_warehouse-specific)
        assert "_bd_to_cq" not in src
        assert "def make_std_ee_003_08" in src

    def test_emit_codegen_module_legacy_header(self):
        """jinja_primitive results must keep the pre-refactor header format
        verbatim — this is the byte-identical regression gate."""
        from codegen.gen_std_parts import _emit_module_source

        result = ResolveResult(
            status="fallback",
            kind="codegen",
            adapter="jinja_primitive",
            body_code='    return cq.Workplane("XY").circle(11).extrude(20)',
            source_tag="jinja:tank",
            metadata={"dims": {"d": 22, "l": 20}},
        )
        src = _emit_module_source(
            self._bom_part("GIS-EE-009-01", "测试容器"),
            "std_ee_009_01",
            "tank",
            result,
        )
        ast.parse(src)
        # The legacy header DOES NOT mention parts_resolver — this is the
        # property that keeps byte-identical regression passing.
        assert "Auto-generated by codegen/gen_std_parts.py" in src
        assert "via parts_resolver" not in src
        assert "Dimensions: {'d': 22, 'l': 20}" in src
        assert "def make_std_ee_009_01" in src
        assert "import cadquery as cq" in src

    def test_emit_codegen_module_parametric_template_header(self):
        """Curated B-grade templates are still emitted as codegen bodies, but
        their module header must not call them simplified fallback geometry."""
        from codegen.gen_std_parts import _emit_module_source

        result = ResolveResult(
            status="hit",
            kind="codegen",
            adapter="jinja_primitive",
            body_code='    return cq.Workplane("XY").box(20, 20, 3)',
            source_tag="jinja_template:pu_buffer_pad",
            geometry_source="PARAMETRIC_TEMPLATE",
            geometry_quality="B",
            requires_model_review=False,
            metadata={"dims": {"w": 20, "d": 20, "h": 3}},
        )
        src = _emit_module_source(
            self._bom_part("SLP-F11", "PU 缓冲垫"),
            "std_f11",
            "seal",
            result,
        )

        ast.parse(src)
        assert "Auto-generated by codegen/gen_std_parts.py via parts_resolver" in src
        assert "参数化模板几何" in src
        assert "Source: jinja_template:pu_buffer_pad" in src
        assert "simplified representation" not in src
        assert "简化标准件几何" not in src


# ═══ Layer 3 — End-to-end pipeline ══════════════════════════════════════════


class TestEndToEndPipeline:
    """Full generate_std_part_files() invocation with a synthetic BOM that
    routes to multiple adapters at once. Monkeypatches the BOM/envelope
    parsers to avoid needing a real CAD_SPEC.md fixture file."""

    @pytest.fixture
    def synthetic_bom(self):
        """5 BOM rows: motor (STEP), bearing (BW), connector (PC), tank (jinja),
        and a fastener (skipped by category filter)."""
        return [
            {
                "part_no": "GIS-EE-001-05",
                "name_cn": "Maxon ECX SPEED 22L 减速电机",
                "material": "",
                "make_buy": "外购",
                "is_assembly": False,
            },
            {
                "part_no": "GIS-EE-002-11",
                "name_cn": "608ZZ 深沟球轴承",
                "material": "",
                "make_buy": "外购",
                "is_assembly": False,
            },
            {
                "part_no": "GIS-EE-003-08",
                "name_cn": "LEMO FGG.0B 连接器",
                "material": "",
                "make_buy": "外购",
                "is_assembly": False,
            },
            {
                "part_no": "GIS-EE-004-99",
                "name_cn": "304不锈钢储罐",
                "material": "Φ38×120mm",
                "make_buy": "外购",
                "is_assembly": False,
            },
            {
                "part_no": "GIS-EE-005-01",
                "name_cn": "M3×10 内六角螺栓",
                "material": "不锈钢",
                "make_buy": "外购",
                "is_assembly": False,
            },
        ]

    def test_generate_files_for_multi_adapter_bom(
        self, tmp_path, step_pool_dir, multi_adapter_registry, synthetic_bom, monkeypatch
    ):
        """One generate_std_part_files() call → four files routed to four
        different adapters (motor=step / bearing=bd / connector=jinja /
        tank=jinja, with the fastener filtered out by category)."""
        from codegen import gen_std_parts

        # Stand up a fake project root that contains both the std_parts pool
        # and the parts_library.yaml that wires up the four adapter routes.
        project_root = step_pool_dir.parent
        (project_root / "cad" / "end_effector").mkdir(parents=True)
        spec_path = project_root / "cad" / "end_effector" / "CAD_SPEC.md"
        spec_path.write_text("# placeholder\n", encoding="utf-8")

        # Write the registry to disk so default_resolver() picks it up via
        # the project_root search path. The registry uses the same rules as
        # the multi_adapter_registry fixture.
        import yaml
        (project_root / "parts_library.yaml").write_text(
            yaml.safe_dump(multi_adapter_registry), encoding="utf-8"
        )

        # Monkeypatch the BOM parser and envelope parser to return our
        # synthetic data instead of reading the placeholder spec file.
        monkeypatch.setattr(gen_std_parts, "parse_bom_tree",
                            lambda path: synthetic_bom)
        monkeypatch.setattr(gen_std_parts, "parse_envelopes", lambda path: {})

        out_dir = tmp_path / "generated"
        out_dir.mkdir()

        generated, skipped, _resolver, _pending = gen_std_parts.generate_std_part_files(
            spec_path=str(spec_path),
            output_dir=str(out_dir),
            mode="force",
        )

        # The fastener (M3×10) is filtered out by _SKIP_CATEGORIES;
        # everything else should produce a file.
        produced = {Path(f).name for f in generated}
        assert "std_ee_001_05.py" in produced  # motor → step_pool
        assert "std_ee_002_11.py" in produced  # bearing → bd_warehouse
        # connector → partcad (real adapter, not installed) → jinja_primitive fallback
        assert "std_ee_003_08.py" in produced
        assert "std_ee_004_99.py" in produced  # tank → jinja_primitive
        assert "std_ee_005_01.py" not in produced  # fastener filtered out

        # Each generated file must compile as valid Python
        for f in generated:
            content = Path(f).read_text(encoding="utf-8")
            ast.parse(content)
            assert "import cadquery as cq" in content

        # Inspect the motor file: should be a STEP import
        motor_src = (out_dir / "std_ee_001_05.py").read_text(encoding="utf-8")
        assert "cq.importers.importStep" in motor_src
        assert "ecx_22l.step" in motor_src

        # Inspect the bearing file: should be a bd_warehouse lazy import
        bearing_src = (out_dir / "std_ee_002_11.py").read_text(encoding="utf-8")
        assert "from bd_warehouse.bearing import SingleRowDeepGrooveBallBearing" in bearing_src
        assert "M8-22-7" in bearing_src
        assert "_bd_to_cq" in bearing_src  # inlined helper

        # Inspect the tank file: should be the legacy jinja header
        tank_src = (out_dir / "std_ee_004_99.py").read_text(encoding="utf-8")
        assert "Auto-generated by codegen/gen_std_parts.py" in tank_src
        # No parts_resolver in the header — byte-identical legacy format
        assert "via parts_resolver" not in tank_src

    def test_kill_switch_forces_all_to_jinja(
        self, tmp_path, step_pool_dir, multi_adapter_registry, synthetic_bom, monkeypatch
    ):
        """With CAD_PARTS_LIBRARY_DISABLE=1, every BOM row that the legacy
        path could draw must end up at jinja_primitive — proving the kill
        switch fully bypasses step_pool / bd_warehouse / partcad even when
        the registry says otherwise."""
        from codegen import gen_std_parts

        project_root = step_pool_dir.parent
        (project_root / "cad" / "end_effector").mkdir(parents=True)
        spec_path = project_root / "cad" / "end_effector" / "CAD_SPEC.md"
        spec_path.write_text("# placeholder\n", encoding="utf-8")

        import yaml
        (project_root / "parts_library.yaml").write_text(
            yaml.safe_dump(multi_adapter_registry), encoding="utf-8"
        )

        monkeypatch.setattr(gen_std_parts, "parse_bom_tree",
                            lambda path: synthetic_bom)
        monkeypatch.setattr(gen_std_parts, "parse_envelopes", lambda path: {})
        monkeypatch.setenv("CAD_PARTS_LIBRARY_DISABLE", "1")

        out_dir = tmp_path / "generated_kill"
        out_dir.mkdir()

        generated, _, _resolver, _pending = gen_std_parts.generate_std_part_files(
            spec_path=str(spec_path),
            output_dir=str(out_dir),
            mode="force",
        )

        # Every produced file must use the legacy jinja header — that's the
        # byte-identical regression guarantee.
        for f in generated:
            content = Path(f).read_text(encoding="utf-8")
            assert "Auto-generated by codegen/gen_std_parts.py" in content
            assert "via parts_resolver" not in content
            # No bd_warehouse / partcad / importStep imports
            assert "from bd_warehouse" not in content
            assert "import partcad" not in content
            assert "cq.importers.importStep" not in content


def test_resolver_skip_not_in_gen_output(tmp_path, monkeypatch):
    """resolver 返回 skip 状态的件不应产生 gen_std_parts 输出文件。

    这是防御性测试：即使 category 不在 gen_std_parts._SKIP_CATEGORIES，
    只要 resolver.resolve() 返回 status='skip'，也必须静默跳过，不产生输出。
    """
    from codegen import gen_std_parts
    from parts_resolver import ResolveResult

    # 构造一个 BOM：bearing 类型，category 不在 gen_std_parts._SKIP_CATEGORIES
    bom = [
        {
            "part_no": "GIS-TEST-002-99",
            "name_cn": "608ZZ 深沟球轴承",
            "material": "",
            "make_buy": "外购",
            "is_assembly": False,
        }
    ]

    # 构造一个 mock resolver：resolve() 始终返回 skip
    class _MockResolver:
        def resolve(self, query):
            return ResolveResult.skip(reason="测试用 skip")

        def coverage_report(self):
            return ""

    monkeypatch.setattr(gen_std_parts, "parse_bom_tree", lambda path: bom)
    monkeypatch.setattr(gen_std_parts, "parse_envelopes", lambda path: {})
    monkeypatch.setattr(gen_std_parts, "default_resolver",
                        lambda **kwargs: _MockResolver())

    # 准备最小 project 结构
    (tmp_path / "cad" / "end_effector").mkdir(parents=True)
    spec_path = tmp_path / "cad" / "end_effector" / "CAD_SPEC.md"
    spec_path.write_text("# placeholder\n", encoding="utf-8")
    out_dir = tmp_path / "std_parts"
    out_dir.mkdir()

    generated, skipped, _resolver, _pending = gen_std_parts.generate_std_part_files(
        spec_path=str(spec_path),
        output_dir=str(out_dir),
        mode="force",
    )

    assert generated == [], (
        f"resolver 返回 skip 的件不应产生输出文件，但找到：{generated}"
    )
