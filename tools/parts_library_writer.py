"""Atomic writer for user-provided STEP mappings in parts_library.yaml."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.model_context import ModelProjectContext


@dataclass(frozen=True)
class UserStepMapping:
    part_no: str
    name_cn: str
    file_rel: str
    source_path: str
    source_hash: str
    bbox_mm: tuple[float, float, float] | None = None
    validated: bool = True
    validation_status: str = "resolver_verified"


def prepend_user_step_mapping(
    context: ModelProjectContext,
    mapping: UserStepMapping,
) -> Path:
    """Prepend a user STEP mapping while preserving existing YAML structure."""
    yaml_path, cfg = _load_config_for_update(context.parts_library_path)

    retained_mappings = [
        item
        for item in cfg["mappings"]
        if not _is_previous_user_mapping(item, mapping.part_no)
    ]
    cfg["mappings"] = [_build_mapping(mapping)] + retained_mappings

    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = yaml_path.with_suffix(yaml_path.suffix + ".tmp")
    import yaml  # type: ignore

    with tmp_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    os.replace(tmp_path, yaml_path)
    return yaml_path


def validate_parts_library_for_user_step(context: ModelProjectContext) -> None:
    """Validate parts_library.yaml can accept a user STEP mapping without writing."""
    _load_config_for_update(context.parts_library_path)


def _load_config_for_update(yaml_path: Path) -> tuple[Path, dict[str, Any]]:
    try:
        import yaml  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("PyYAML not installed; parts_library.yaml not updated") from exc

    if yaml_path.is_file():
        try:
            with yaml_path.open(encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML in {yaml_path}") from exc
        if not isinstance(loaded, dict):
            raise ValueError(f"{yaml_path} top-level YAML must be a mapping")
        cfg = loaded
    else:
        cfg: dict[str, Any] = {"extends": "default", "mappings": []}

    cfg.setdefault("extends", "default")
    mappings = cfg.get("mappings", [])
    if not isinstance(mappings, list):
        raise ValueError(f"{yaml_path} mappings must be a list")

    return yaml_path, cfg


def _is_previous_user_mapping(item: Any, part_no: str) -> bool:
    if not isinstance(item, dict):
        return False
    match = item.get("match") or {}
    provenance = item.get("provenance") or {}
    return (
        isinstance(match, dict)
        and match.get("part_no") == part_no
        and isinstance(provenance, dict)
        and provenance.get("provided_by_user") is True
    )


def _build_mapping(mapping: UserStepMapping) -> dict[str, Any]:
    provenance: dict[str, Any] = {
        "provided_by_user": True,
        "provided_at": datetime.now(timezone.utc).isoformat(),
        "source_path": mapping.source_path,
        "source_hash": mapping.source_hash,
        "name_cn": mapping.name_cn,
        "validated": mapping.validated,
        "validation_status": mapping.validation_status,
    }
    if mapping.bbox_mm is not None:
        provenance["bbox_mm"] = [float(value) for value in mapping.bbox_mm]
    return {
        "match": {"part_no": mapping.part_no},
        "adapter": "step_pool",
        "spec": {"file": mapping.file_rel},
        "provenance": provenance,
    }
