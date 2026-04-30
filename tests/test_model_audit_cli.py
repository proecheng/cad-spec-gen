"""Model library audit CLI contract tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _write_geometry_report(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    (path.parent / "a001.step").write_bytes(b"ISO-10303-21;\n")
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "total": 3,
                "quality_counts": {"A": 1, "C": 2},
                "decisions": [
                    {
                        "part_no": "A-001",
                        "name_cn": "真实轴承",
                        "geometry_quality": "A",
                        "geometry_source": "SW_TOOLBOX_STEP",
                        "adapter": "sw_toolbox",
                        "requires_model_review": False,
                        "step_path": str(path.parent / "a001.step"),
                    },
                    {
                        "part_no": "C-001",
                        "name_cn": "模板联轴器",
                        "geometry_quality": "C",
                        "geometry_source": "JINJA_TEMPLATE",
                        "adapter": "jinja_primitive",
                        "requires_model_review": True,
                        "step_path": None,
                    },
                    {
                        "part_no": "C-002",
                        "name_cn": "缺失 STEP",
                        "geometry_quality": "C",
                        "geometry_source": "USER_STEP",
                        "adapter": "step_pool",
                        "requires_model_review": False,
                        "step_path": str(path.parent / "missing.step"),
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def test_model_audit_json_reads_project_root_geometry_report(tmp_path):
    report_path = tmp_path / "cad" / "demo" / ".cad-spec-gen" / "geometry_report.json"
    _write_geometry_report(report_path)

    env = {
        **os.environ,
        "CAD_PROJECT_ROOT": str(tmp_path),
        "PYTHONIOENCODING": "utf-8",
    }
    result = subprocess.run(
        [
            sys.executable,
            "cad_pipeline.py",
            "model-audit",
            "--subsystem",
            "demo",
            "--json",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=Path(__file__).resolve().parents[1],
        env=env,
    )

    assert result.returncode == 0, result.stderr
    doc = json.loads(result.stdout)
    assert doc["schema_version"] == 1
    assert doc["subsystem"] == "demo"
    assert Path(doc["report_path"]) == report_path
    assert doc["quality_counts"] == {"A": 1, "C": 2}
    assert doc["review_required_count"] == 1
    assert doc["missing_step_count"] == 1
    assert doc["status"] == "review_required"
    assert [item["part_no"] for item in doc["review_required"]] == ["C-001"]


def test_model_audit_strict_exits_nonzero_for_review_items(tmp_path):
    report_path = tmp_path / "cad" / "demo" / ".cad-spec-gen" / "geometry_report.json"
    _write_geometry_report(report_path)

    env = {
        **os.environ,
        "CAD_PROJECT_ROOT": str(tmp_path),
        "PYTHONIOENCODING": "utf-8",
    }
    result = subprocess.run(
        [
            sys.executable,
            "cad_pipeline.py",
            "model-audit",
            "--subsystem",
            "demo",
            "--strict",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=Path(__file__).resolve().parents[1],
        env=env,
    )

    assert result.returncode == 1
    assert "C-001" in result.stdout
    assert "缺失 STEP" in result.stdout


def test_model_audit_missing_report_is_clear(tmp_path):
    env = {
        **os.environ,
        "CAD_PROJECT_ROOT": str(tmp_path),
        "PYTHONIOENCODING": "utf-8",
    }
    result = subprocess.run(
        [sys.executable, "cad_pipeline.py", "model-audit", "--subsystem", "missing"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=Path(__file__).resolve().parents[1],
        env=env,
    )

    assert result.returncode == 2
    assert "geometry_report.json 不存在" in result.stderr
