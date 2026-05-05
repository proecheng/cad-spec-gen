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


def _write_cache_uri_geometry_report(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "total": 1,
                "quality_counts": {"A": 1},
                "decisions": [
                    {
                        "part_no": "A-001",
                        "name_cn": "缓存电机",
                        "geometry_quality": "A",
                        "geometry_source": "STEP_POOL",
                        "adapter": "step_pool",
                        "requires_model_review": False,
                        "step_path": "cache://maxon/ecx_22l.step",
                    }
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


def test_model_audit_json_includes_user_model_quality_summary(tmp_path):
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
    summary = doc["model_quality_summary"]
    assert summary["schema_version"] == 1
    assert summary["source"] == "geometry_report"
    assert summary["source_report"] == "cad/demo/.cad-spec-gen/geometry_report.json"
    assert summary["binding_status"] == "project_report"
    assert summary["readiness_status"] == "blocked"
    assert summary["photoreal_risk"] == "blocked"
    assert summary["total"] == 3
    assert summary["quality_counts"] == {"A": 1, "C": 2}
    assert summary["source_counts"] == {
        "real_step": 1,
        "simplified_template": 1,
        "user_step": 1,
    }
    assert summary["review_recommended_count"] == 2
    assert summary["blocking_count"] == 1
    assert summary["recommended_next_action"]["kind"] == "import_missing_models"
    assert summary["quality_scale"]["A"]["photoreal_risk"] == "low"

    parts = {item["part_no"]: item for item in summary["part_summaries"]}
    assert parts["A-001"]["user_status"] == "ready"
    assert parts["A-001"]["source_kind"] == "real_step"
    assert parts["A-001"]["public_step_path"].endswith("a001.step")
    assert parts["C-001"]["user_status"] == "needs_review"
    assert parts["C-001"]["source_kind"] == "simplified_template"
    assert parts["C-002"]["user_status"] == "blocked"
    assert parts["C-002"]["source_kind"] == "user_step"
    assert parts["C-002"]["missing_step"] is True


def test_model_audit_summary_normalizes_unknown_quality_counts(tmp_path):
    report_path = tmp_path / "cad" / "demo" / ".cad-spec-gen" / "geometry_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "total": 1,
                "quality_counts": {"Z": 1},
                "decisions": [
                    {
                        "part_no": "Z-001",
                        "name_cn": "未知模型等级",
                        "geometry_quality": "Z",
                        "geometry_source": "CUSTOM_BACKEND",
                        "adapter": "custom",
                        "requires_model_review": False,
                        "step_path": None,
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

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
    summary = json.loads(result.stdout)["model_quality_summary"]
    assert summary["quality_counts"] == {"unknown": 1}
    assert summary["part_summaries"][0]["geometry_quality"] == "unknown"
    assert summary["readiness_status"] == "needs_review"


def test_model_audit_json_resolves_shared_cache_uri(tmp_path):
    report_path = tmp_path / "cad" / "demo" / ".cad-spec-gen" / "geometry_report.json"
    _write_cache_uri_geometry_report(report_path)
    cache_root = tmp_path / "step_cache"
    step_path = cache_root / "maxon" / "ecx_22l.step"
    step_path.parent.mkdir(parents=True)
    step_path.write_bytes(b"ISO-10303-21;\n")

    env = {
        **os.environ,
        "CAD_PROJECT_ROOT": str(tmp_path),
        "CAD_SPEC_GEN_STEP_CACHE": str(cache_root),
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
    assert doc["status"] == "pass"
    assert doc["missing_step_count"] == 0
    assert doc["missing_step_paths"] == []


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


def test_model_audit_text_describes_parametric_template_quality(tmp_path):
    report_path = tmp_path / "cad" / "demo" / ".cad-spec-gen" / "geometry_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "total": 1,
                "quality_counts": {"B": 1},
                "decisions": [
                    {
                        "part_no": "P-001",
                        "name_cn": "丝杠",
                        "geometry_quality": "B",
                        "geometry_source": "PARAMETRIC_TEMPLATE",
                        "adapter": "parametric_transmission",
                        "requires_model_review": False,
                        "step_path": None,
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    env = {
        **os.environ,
        "CAD_PROJECT_ROOT": str(tmp_path),
        "PYTHONIOENCODING": "utf-8",
    }
    result = subprocess.run(
        [sys.executable, "cad_pipeline.py", "model-audit", "--subsystem", "demo"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=Path(__file__).resolve().parents[1],
        env=env,
    )

    assert result.returncode == 0
    assert "status: pass" in result.stdout
    assert "B = curated parametric template" in result.stdout
