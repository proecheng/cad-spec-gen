"""SW Toolbox real-model E2E runner contract tests.

These tests do not require real SolidWorks. They pin the orchestration layer
that the self-hosted runner uses for the optional full Toolbox validation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def test_minimal_spec_is_parseable_by_codegen_bom_parser(tmp_path):
    from codegen.gen_build import parse_bom_tree
    from tools.sw_toolbox_e2e import write_minimal_spec

    spec_path = tmp_path / "CAD_SPEC.md"
    write_minimal_spec(spec_path)

    rows = parse_bom_tree(str(spec_path))

    assert len(rows) == 1
    assert rows[0]["part_no"] == "SW-E2E-001"
    assert "轴承" in rows[0]["name_cn"]
    assert rows[0]["make_buy"] == "标准"


def test_run_e2e_accepts_sw_toolbox_geometry_report(
    tmp_path, monkeypatch,
):
    from tools import sw_toolbox_e2e

    def fake_generate_std_part_files(spec_path, output_dir, mode):
        out = Path(output_dir)
        step_file = out / "bearing.step"
        step_file.write_bytes(b"ISO-10303-21;\n" + b"x" * 2048)
        generated = out / "std_e2e_001.py"
        generated.write_text(
            "import cadquery as cq\n"
            "def make_std_e2e_001():\n"
            f"    return cq.importers.importStep({str(step_file)!r})\n",
            encoding="utf-8",
        )
        report = {
            "schema_version": 1,
            "total": 1,
            "quality_counts": {"A": 1},
            "decisions": [
                {
                    "part_no": "SW-E2E-001",
                    "adapter": "sw_toolbox",
                    "kind": "step_import",
                    "geometry_source": "SW_TOOLBOX_STEP",
                    "geometry_quality": "A",
                    "step_path": str(step_file),
                    "metadata": {"configuration": "6205"},
                }
            ],
        }
        report_path = out / ".cad-spec-gen" / "geometry_report.json"
        report_path.parent.mkdir(parents=True)
        report_path.write_text(json.dumps(report), encoding="utf-8")
        return [str(generated)], [], object(), {}

    monkeypatch.setattr(
        sw_toolbox_e2e.gen_std_parts,
        "generate_std_part_files",
        fake_generate_std_part_files,
    )

    rc = sw_toolbox_e2e.run_sw_toolbox_e2e(
        argparse.Namespace(out_dir=str(tmp_path / "artifacts")),
    )

    assert rc == 0
    summary = json.loads((tmp_path / "artifacts" / "sw_toolbox_e2e.json").read_text())
    assert summary["status"] == "pass"
    assert summary["sw_toolbox_hits"] == 1
    assert summary["generated_count"] == 1
    assert summary["geometry_report"]["decisions"][0]["geometry_quality"] == "A"


def test_run_e2e_fails_when_broker_needs_user_decision(tmp_path, monkeypatch):
    from tools import sw_toolbox_e2e

    def fake_generate_std_part_files(spec_path, output_dir, mode):
        return [], [], object(), {
            "sw_toolbox_e2e": [
                {
                    "part_no": "SW-E2E-001",
                    "match_failure_reason": "no_exact_or_fuzzy_match_with_high_confidence",
                }
            ]
        }

    monkeypatch.setattr(
        sw_toolbox_e2e.gen_std_parts,
        "generate_std_part_files",
        fake_generate_std_part_files,
    )

    rc = sw_toolbox_e2e.run_sw_toolbox_e2e(
        argparse.Namespace(out_dir=str(tmp_path / "artifacts")),
    )

    assert rc == 3
    summary = json.loads((tmp_path / "artifacts" / "sw_toolbox_e2e.json").read_text())
    assert summary["status"] == "pending_config_decision"
    assert summary["pending_records"]["sw_toolbox_e2e"][0]["part_no"] == "SW-E2E-001"


def test_sw_smoke_workflow_has_manual_full_toolbox_e2e_gate():
    workflow = Path(".github/workflows/sw-smoke.yml").read_text(encoding="utf-8")

    assert "full:" in workflow
    assert "Run SW Toolbox model-library E2E" in workflow
    assert "github.event_name == 'workflow_dispatch'" in workflow
    assert "inputs.full" in workflow
    assert "cad_pipeline.py sw-toolbox-e2e" in workflow
