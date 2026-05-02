from pathlib import Path
from typing import Any


def build_run_manifest(
    run_id: str,
    subsystem: str,
    path_context_hash: str,
    command: str,
    args: list[str] | None = None,
) -> dict:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "subsystem": subsystem,
        "path_context_hash": path_context_hash,
        "command": command,
        "args": list(args or []),
        "stages": [],
        "artifacts": {},
    }


def record_stage(manifest: dict, name: str, status: str, **extra: Any) -> dict:
    stage = {"name": name, "status": status}
    stage.update(extra)

    for index, existing in enumerate(manifest.setdefault("stages", [])):
        if existing.get("name") == name:
            manifest["stages"][index] = stage
            return manifest

    manifest["stages"].append(stage)
    return manifest


def record_artifact(manifest: dict, key: str, path: str | Path) -> dict:
    manifest.setdefault("artifacts", {})[key] = str(path)
    return manifest
