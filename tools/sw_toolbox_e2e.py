"""Real SolidWorks Toolbox model-library E2E runner.

This module is intentionally small and orchestration-focused. The heavy work
is delegated to the existing production path:

CAD_SPEC.md -> codegen.gen_std_parts -> PartsResolver -> SwToolboxAdapter ->
sw_config_broker -> SolidWorks COM STEP export -> generated std_*.py.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codegen import gen_std_parts


DEFAULT_PART = {
    "part_no": "SW-E2E-001",
    "name_cn": "GB/T 276 深沟球轴承 6205",
    "material": "GCr15",
    "quantity": "1",
    "make_buy": "标准",
}
DEFAULT_SLDPRT_FILENAME = "deep groove ball bearings gb.sldprt"


def write_minimal_spec(spec_path: Path, part: dict[str, str] | None = None) -> None:
    """Write a tiny CAD_SPEC.md whose BOM is parseable by gen_std_parts."""
    part = dict(DEFAULT_PART if part is None else part)
    spec_path = Path(spec_path)
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(
        f"""# SolidWorks Toolbox E2E CAD_SPEC

## 5. BOM树

| 零件号 | 名称 | 材料 | 数量 | 外购/自制 |
|---|---|---|---|---|
| {part["part_no"]} | {part["name_cn"]} | {part["material"]} | {part["quantity"]} | {part["make_buy"]} |

## 6. 几何与装配

本文件仅用于 self-hosted SolidWorks Toolbox 端到端验收。
""",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_summary(out_dir: Path, summary: dict[str, Any]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "sw_toolbox_e2e.json"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def _refresh_cad_project_root() -> None:
    """Refresh cad_paths.PROJECT_ROOT after changing CAD_PROJECT_ROOT."""
    module = sys.modules.get("cad_paths")
    if module is not None:
        importlib.reload(module)


def _seed_default_config_decision(project_dir: Path, part: dict[str, str]) -> Path:
    """Seed the noninteractive E2E with an explicit user config decision.

    On the self-hosted SW 2024 runner, the GB deep-groove bearing SLDPRT exposes
    only Default/PreviewCfg configurations through COM. The smoke test is meant
    to verify real Toolbox STEP export and codegen consumption, so it uses the
    same persisted decision path a user would create after choosing Default.
    """
    now = datetime.now(timezone.utc).isoformat()
    part_no = part["part_no"]
    envelope = {
        "schema_version": 2,
        "last_updated": now,
        "decisions_by_subsystem": {
            "default": {
                part_no: {
                    "bom_dim_signature": f"{part['name_cn']}|{part['material']}",
                    "sldprt_filename": DEFAULT_SLDPRT_FILENAME,
                    "decision": "use_config",
                    "config_name": "Default",
                    "user_note": (
                        "Seeded for noninteractive sw-toolbox-e2e smoke; "
                        "the runner's GB bearing SLDPRT exposes Default/PreviewCfg."
                    ),
                    "decided_at": now,
                },
            },
        },
        "decisions_history": [],
    }
    path = Path(project_dir) / ".cad-spec-gen" / "spec_decisions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def _generated_step_import_files(generated: list[str]) -> list[str]:
    files: list[str] = []
    for item in generated:
        path = Path(item)
        try:
            src = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "cq.importers.importStep" in src:
            files.append(str(path))
    return files


def _sw_toolbox_step_decisions(report: dict[str, Any]) -> list[dict[str, Any]]:
    decisions = report.get("decisions") or []
    return [
        d for d in decisions
        if d.get("adapter") == "sw_toolbox"
        and d.get("kind") == "step_import"
        and d.get("geometry_source") == "SW_TOOLBOX_STEP"
        and d.get("geometry_quality") == "A"
    ]


def _missing_step_paths(decisions: list[dict[str, Any]]) -> list[str]:
    missing: list[str] = []
    for decision in decisions:
        raw = decision.get("step_path")
        if not raw or not Path(raw).is_file():
            missing.append(str(raw or ""))
    return missing


def _base_summary(out_dir: Path, project_dir: Path, spec_path: Path) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "out_dir": str(out_dir),
        "project_dir": str(project_dir),
        "spec_path": str(spec_path),
    }


def run_sw_toolbox_e2e(args: argparse.Namespace) -> int:
    """Run the real Toolbox E2E and write a machine-readable artifact.

    Exit codes:
      0: pass
      2: generation/runtime error
      3: broker requires user config decision
      4: no validated sw_toolbox STEP consumption was observed
    """
    out_dir = Path(getattr(args, "out_dir", "") or "artifacts/sw-toolbox-e2e").resolve()
    project_dir = out_dir / "project"
    cad_dir = project_dir / "cad" / "sw_toolbox_e2e"
    spec_path = cad_dir / "CAD_SPEC.md"
    write_minimal_spec(spec_path)

    # Make broker pending paths deterministic if gen_std_parts ever needs them.
    previous_project_root = os.environ.get("CAD_PROJECT_ROOT")
    os.environ["CAD_PROJECT_ROOT"] = str(project_dir)
    _refresh_cad_project_root()
    seeded_decision_path = _seed_default_config_decision(project_dir, DEFAULT_PART)

    summary = _base_summary(out_dir, project_dir, spec_path)
    summary["seeded_decision_path"] = str(seeded_decision_path)
    try:
        try:
            generated, skipped, _resolver, pending_records = (
                gen_std_parts.generate_std_part_files(
                    spec_path=str(spec_path),
                    output_dir=str(cad_dir),
                    mode="force",
                )
            )
        except Exception as exc:
            summary.update({
                "status": "error",
                "error_type": type(exc).__name__,
                "error": str(exc),
            })
            _write_summary(out_dir, summary)
            return 2

        summary.update({
            "generated": list(generated),
            "generated_count": len(generated),
            "skipped": list(skipped),
            "pending_records": pending_records,
        })

        if pending_records:
            summary["status"] = "pending_config_decision"
            _write_summary(out_dir, summary)
            return 3

        geometry_report_path = cad_dir / ".cad-spec-gen" / "geometry_report.json"
        geometry_report = _read_json(geometry_report_path)
        if geometry_report is None:
            summary["status"] = "missing_geometry_report"
            _write_summary(out_dir, summary)
            return 4

        decisions = _sw_toolbox_step_decisions(geometry_report)
        step_import_files = _generated_step_import_files(list(generated))
        missing_steps = _missing_step_paths(decisions)
        summary.update({
            "geometry_report_path": str(geometry_report_path),
            "geometry_report": geometry_report,
            "sw_toolbox_hits": len(decisions),
            "step_import_files": step_import_files,
            "missing_step_paths": missing_steps,
        })

        if not decisions:
            summary["status"] = "no_sw_toolbox_step_decision"
            _write_summary(out_dir, summary)
            return 4
        if not step_import_files:
            summary["status"] = "codegen_did_not_consume_step"
            _write_summary(out_dir, summary)
            return 4
        if missing_steps:
            summary["status"] = "missing_exported_step"
            _write_summary(out_dir, summary)
            return 4

        summary["status"] = "pass"
        _write_summary(out_dir, summary)
        return 0
    finally:
        if previous_project_root is None:
            os.environ.pop("CAD_PROJECT_ROOT", None)
        else:
            os.environ["CAD_PROJECT_ROOT"] = previous_project_root
        _refresh_cad_project_root()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run real SolidWorks Toolbox -> STEP -> codegen E2E.",
    )
    parser.add_argument(
        "--out-dir",
        default="artifacts/sw-toolbox-e2e",
        help="Artifact directory for the generated mini project and summary JSON.",
    )
    return run_sw_toolbox_e2e(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
