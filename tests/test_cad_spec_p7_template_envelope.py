"""P7 envelope probing should use curated parametric template dimensions."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _load_cad_spec_gen_module():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "_cad_spec_gen_p7_template_test",
        root / "cad_spec_gen.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_p7_overrides_p5_chain_span_with_b_grade_parametric_template(
    tmp_path,
    monkeypatch,
):
    cad_spec_gen = _load_cad_spec_gen_module()
    cad_spec_gen.SUBSYSTEM_MAP = {
        "19": {
            "name": "lifting_platform",
            "prefix": "SLP",
            "cad_dir": "cad/lifting_platform",
        }
    }

    bom = {
        "encoding_rule": "SLP",
        "assemblies": [
            {
                "part_no": "SLP-000",
                "name": "升降平台总成",
                "parts": [
                    {
                        "part_no": "SLP-C08",
                        "name": "CL57T 闭环驱动器",
                        "material": "",
                        "qty": 1,
                        "make_buy": "外购",
                    }
                ],
            }
        ],
        "summary": {"total_parts": 1, "total_cost": 0},
    }

    monkeypatch.setattr(cad_spec_gen, "extract_params", lambda _lines: [])
    monkeypatch.setattr(
        cad_spec_gen,
        "extract_tolerances",
        lambda _lines: {"dim_tols": [], "gdt": [], "surfaces": []},
    )
    monkeypatch.setattr(cad_spec_gen, "extract_fasteners", lambda _lines: [])
    monkeypatch.setattr(cad_spec_gen, "extract_bom", lambda _path: bom)
    monkeypatch.setattr(
        cad_spec_gen,
        "extract_assembly_pose",
        lambda _lines: {"coord_sys": [], "layers": []},
    )
    monkeypatch.setattr(cad_spec_gen, "extract_visual_ids", lambda _lines, _bom: [])
    monkeypatch.setattr(
        cad_spec_gen,
        "extract_part_envelopes",
        lambda _lines, _bom, _visual_ids, _params: ({}, None),
    )
    monkeypatch.setattr(
        cad_spec_gen,
        "extract_render_plan",
        lambda _lines: {"groups": [], "views": [], "constraints": []},
    )
    monkeypatch.setattr(cad_spec_gen, "extract_connection_matrix", lambda *_args: [])
    monkeypatch.setattr(cad_spec_gen, "extract_part_placements", lambda *_args: [])
    monkeypatch.setattr(
        cad_spec_gen,
        "compute_serial_offsets",
        lambda *_args: {
            "SLP-C08": {
                "mode": "axial_stack",
                "h": 40.0,
                "z": -40.0,
                "source": "serial_chain",
                "confidence": "high",
            }
        },
    )
    monkeypatch.setattr(cad_spec_gen, "compute_derived", lambda _data: [])
    monkeypatch.setattr(cad_spec_gen, "check_completeness", lambda _data: [])

    import parts_resolver

    class FakeResolver:
        def resolve(self, _query):
            return SimpleNamespace(
                status="hit",
                kind="codegen",
                adapter="jinja_primitive",
                real_dims=(118, 75, 34),
                source_tag="parametric_template:cl57t_stepper_driver",
                geometry_source="PARAMETRIC_TEMPLATE",
                geometry_quality="B",
                requires_model_review=False,
            )

    monkeypatch.setattr(parts_resolver, "default_resolver", lambda **_kw: FakeResolver())

    design_doc = tmp_path / "19-template.md"
    design_doc.write_text("# 19 lifting platform\n", encoding="utf-8")

    result = cad_spec_gen.process_doc(str(design_doc), str(tmp_path), force=True)
    spec_text = Path(result["output_path"]).read_text(encoding="utf-8")

    assert "| SLP-C08 | CL57T 闭环驱动器 | box | 118×75×34 | P7:TEMPLATE(override_P5)" in spec_text
    assert "P5:chain_span" not in spec_text
