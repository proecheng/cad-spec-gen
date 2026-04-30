"""Shared path context for model-library artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelProjectContext:
    """Canonical paths for model-library state within a CAD project."""

    project_root: Path
    subsystem: str | None = None

    def __post_init__(self) -> None:
        root = Path(self.project_root).expanduser().resolve()
        subsystem = self.subsystem.strip() if isinstance(self.subsystem, str) else self.subsystem
        if subsystem == "":
            subsystem = None
        object.__setattr__(self, "project_root", root)
        object.__setattr__(self, "subsystem", subsystem)

    @classmethod
    def for_subsystem(
        cls,
        subsystem: str | None,
        *,
        project_root: str | Path,
    ) -> "ModelProjectContext":
        return cls(project_root=Path(project_root), subsystem=subsystem)

    @classmethod
    def from_review_json(
        cls,
        review_json_path: str | Path,
        *,
        project_root: str | Path,
    ) -> "ModelProjectContext":
        root = Path(project_root).expanduser().resolve()
        review_dir = Path(review_json_path).expanduser().resolve().parent
        subsystem: str | None = None
        try:
            rel_parts = review_dir.relative_to(root).parts
        except ValueError:
            rel_parts = ()
        if len(rel_parts) >= 2 and rel_parts[0] in {"output", "cad"} and rel_parts[1]:
            subsystem = rel_parts[1]
        return cls.for_subsystem(subsystem, project_root=root)

    @property
    def cad_dir(self) -> Path:
        if self.subsystem:
            return self.project_root / "cad" / self.subsystem
        return self.project_root / "cad"

    @property
    def meta_dir(self) -> Path:
        if self.subsystem:
            return self.cad_dir / ".cad-spec-gen"
        return self.project_root / ".cad-spec-gen"

    @property
    def std_parts_dir(self) -> Path:
        return self.project_root / "std_parts"

    @property
    def user_provided_dir(self) -> Path:
        return self.std_parts_dir / "user_provided"

    @property
    def parts_library_path(self) -> Path:
        return self.project_root / "parts_library.yaml"

    @property
    def model_choices_path(self) -> Path:
        return self.meta_dir / "model_choices.json"

    @property
    def model_imports_path(self) -> Path:
        return self.meta_dir / "model_imports.json"

    @property
    def geometry_report_path(self) -> Path:
        return self.meta_dir / "geometry_report.json"

    @property
    def sw_export_plan_path(self) -> Path:
        return self.meta_dir / "sw_export_plan.json"
