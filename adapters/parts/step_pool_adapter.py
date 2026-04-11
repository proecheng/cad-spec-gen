"""
adapters/parts/step_pool_adapter.py — Phase B adapter for project-local STEP files.

This adapter lets users drop vendor STEP files into a project directory
(default: `std_parts/`) and map specific BOM part_nos to them via the
parts_library.yaml registry.

Example YAML mapping::

    mappings:
      - match: {part_no: "GIS-EE-001-05"}
        adapter: step_pool
        spec: {file: "maxon/ecx_22l_68mm.step"}

The adapter:
1. Resolves `spec.file` against `step_pool.root` (project-relative)
2. Falls back to `step_pool.cache` (shared user cache, e.g.
   `~/.cad-spec-gen/step_cache/`) if the project-local file is missing
3. Probes BoundingBox once per file and caches the (w, d, h) tuple
4. Returns `ResolveResult.kind="step_import"` so gen_std_parts.py emits
   a `make_*()` function body that imports the STEP at runtime

Design choices:
- `spec.file` is a relative path. Absolute paths are supported but
  discouraged (breaks project portability).
- `spec.file_template` (not yet implemented in Phase B) will allow
  name-based lookup: `{normalize(name)}.step` → `maxon_ecx22l.step`.
  Left as a TODO so users can rely on explicit `file:` for now.
- STEP path in generated code is resolved relative to the generated
  module's location, so the project can be moved on disk without
  re-running codegen.

Graceful degradation: if the file is missing at generation time, the
adapter returns ResolveResult.miss(), and the resolver falls through to
the next rule (typically bd_warehouse or jinja_primitive).
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

_PROJECT_ROOT = str(Path(__file__).parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from adapters.parts.base import PartsAdapter


class StepPoolAdapter(PartsAdapter):
    """Resolver adapter for a project-local directory of STEP files.

    Parameters
    ----------
    project_root : str
        Used as the base for relative `spec.file` paths.
    config : dict
        The `step_pool:` block from parts_library.yaml. Supports:
          - root: str  (default "std_parts/")  — project-relative dir
          - cache: str (optional)              — shared cache dir
    """

    name = "step_pool"

    def __init__(self, project_root: str = "", config: Optional[dict] = None):
        self.project_root = project_root or os.getcwd()
        self.config = config or {}
        self._bbox_cache: dict = {}  # path → (w, d, h)

    # ---- PartsAdapter interface -------------------------------------------

    def is_available(self) -> bool:
        """Always available — it's just filesystem lookups."""
        return True

    def can_resolve(self, query) -> bool:
        """Return True only if the query's category is sensible for STEP."""
        # STEP files can represent any part, but the adapter still requires
        # an explicit mapping rule to be used. can_resolve() is informational.
        return True

    def resolve(self, query, spec: dict):
        from parts_resolver import ResolveResult

        resolved_path = self._resolve_spec_path(spec, query)
        if not resolved_path:
            return ResolveResult.miss()
        if not os.path.isfile(resolved_path):
            # File missing → if the spec nominates a skill-level synthesizer,
            # write the parametric stand-in into the shared cache and retry.
            synthesized = self._try_synthesize(spec)
            if synthesized and os.path.isfile(synthesized):
                resolved_path = synthesized
            else:
                # Fall through to next adapter instead of crashing
                return ResolveResult(
                    status="miss",
                    kind="miss",
                    adapter=self.name,
                    warnings=[f"STEP file not found: {resolved_path}"],
                )

        # Probe bounding box for dimension consistency
        dims = self._probe_bbox(resolved_path)

        # Store the path as PROJECT-RELATIVE so the generated code is
        # portable. The runtime resolver in the generated module rebuilds
        # the absolute path from the module's __file__.
        rel_path = self._to_project_relative(resolved_path)

        return ResolveResult(
            status="hit",
            kind="step_import",
            adapter=self.name,
            step_path=rel_path,
            real_dims=dims,
            source_tag=f"STEP:{rel_path}",
        )

    def probe_dims(self, query, spec: dict) -> Optional[tuple]:
        """Return STEP bounding box without emitting code."""
        resolved_path = self._resolve_spec_path(spec, query)
        if not resolved_path:
            return None
        if not os.path.isfile(resolved_path):
            synthesized = self._try_synthesize(spec)
            if synthesized and os.path.isfile(synthesized):
                resolved_path = synthesized
            else:
                return None
        return self._probe_bbox(resolved_path)

    # ---- Path resolution --------------------------------------------------

    def _resolve_spec_path(self, spec: dict, query) -> Optional[str]:
        """Resolve spec.file or spec.file_template to an absolute path.

        Search order:
          1. `spec.file` — literal relative path, resolved against step_pool.root
          2. `spec.file_template` — template with placeholders (future work)
          3. Shared cache fallback (`step_pool.cache` or
             `adapters.parts.vendor_synthesizer.default_cache_root()` when the
             registry does not set it)
        """
        file_spec = spec.get("file") or spec.get("file_template")
        if not file_spec:
            return None

        if spec.get("file_template"):
            file_spec = self._expand_template(spec["file_template"], query)

        if os.path.isabs(file_spec):
            return os.path.normpath(file_spec)

        # Search 1: project-local step_pool.root
        root = self.config.get("root", "std_parts/")
        root = self._normalize_dir(root)
        project_path = os.path.join(root, file_spec)
        if os.path.isfile(project_path):
            return os.path.normpath(project_path)

        # Search 2: shared cache (registry override or skill-default location)
        cache_path = self._shared_cache_path(file_spec)
        if cache_path and os.path.isfile(cache_path):
            return os.path.normpath(cache_path)

        # Not found — return the shared-cache path when we can, since that is
        # the preferred write target for auto-synthesis. Falls back to the
        # project-relative path when no cache has been configured so the
        # "missing file" warning still points somewhere meaningful.
        return os.path.normpath(cache_path or project_path)

    def _shared_cache_path(self, file_spec: str) -> Optional[str]:
        """Return the absolute cached-path for a vendor-relative file.

        Honors `step_pool.cache` from parts_library.yaml if set. Falls back
        to the skill-level shared cache root (`~/.cad-spec-gen/step_cache/`)
        so a blank registry still resolves vendor parts the same way.
        """
        cache = self.config.get("cache", "")
        if cache:
            cache = self._normalize_dir(cache)
            return os.path.join(cache, file_spec)
        try:
            from adapters.parts.vendor_synthesizer import default_cache_root
        except ImportError:
            return None
        return os.path.join(str(default_cache_root()), file_spec)

    def _try_synthesize(self, spec: dict) -> Optional[str]:
        """Run a registered synthesizer to write a missing STEP into cache.

        Consulted only when `_resolve_spec_path()` pointed at a non-existent
        file. Returns the absolute path of the freshly written STEP on
        success, or None if (a) no `synthesizer:` key is set, (b) the
        factory is not registered, or (c) the synthesis itself failed.
        Failures are swallowed — the caller will simply fall through to the
        next adapter.
        """
        factory_id = spec.get("synthesizer")
        file_spec = spec.get("file") or spec.get("file_template")
        if not factory_id or not file_spec:
            return None

        try:
            from adapters.parts.vendor_synthesizer import synthesize_to_cache
        except ImportError:
            return None

        target = synthesize_to_cache(factory_id, file_spec)
        return str(target) if target else None

    def _normalize_dir(self, dir_path: str) -> str:
        """Expand ~ and resolve relative paths against project_root."""
        dir_path = os.path.expanduser(dir_path)
        if not os.path.isabs(dir_path):
            dir_path = os.path.join(self.project_root, dir_path)
        return dir_path

    def _to_project_relative(self, abs_path: str) -> str:
        """Convert an absolute path back to project-relative for emission.

        If the path is outside project_root (e.g. from the shared cache),
        return the absolute path as-is.
        """
        try:
            rel = os.path.relpath(abs_path, self.project_root)
            # On Windows os.path.relpath may return "..\\cache\\...";
            # avoid embedding parent-dir traversal in generated code
            if rel.startswith(".."):
                return abs_path.replace("\\", "/")
            return rel.replace("\\", "/")
        except ValueError:
            # Different drives on Windows → fall back to abs path
            return abs_path.replace("\\", "/")

    def _expand_template(self, template: str, query) -> str:
        """Expand a file_template like 'maxon/{normalize(name)}.step'.

        Currently supported placeholders:
          {part_no}     — raw part_no
          {name}        — raw name_cn
          {normalize(name)} — lowercase name with spaces → underscores
        """
        result = template
        result = result.replace("{part_no}", query.part_no)
        result = result.replace("{name}", query.name_cn)

        # Handle {normalize(name)}
        def _normalize(text: str) -> str:
            text = text.lower()
            text = re.sub(r"[^\w]+", "_", text)
            return text.strip("_")

        result = re.sub(
            r"\{normalize\(name\)\}",
            _normalize(query.name_cn),
            result,
        )
        return result

    # ---- BoundingBox probe ------------------------------------------------

    def _probe_bbox(self, abs_path: str) -> Optional[tuple]:
        """Load STEP, compute bbox, cache the (w, d, h) tuple in mm."""
        if abs_path in self._bbox_cache:
            return self._bbox_cache[abs_path]
        try:
            import cadquery as cq
            shape = cq.importers.importStep(abs_path)
            solid = shape.val() if hasattr(shape, "val") else shape.objects[0]
            bbox = solid.BoundingBox()
            dims = (
                round(bbox.xmax - bbox.xmin, 2),
                round(bbox.ymax - bbox.ymin, 2),
                round(bbox.zmax - bbox.zmin, 2),
            )
            self._bbox_cache[abs_path] = dims
            return dims
        except Exception:
            # Return None on any failure (missing file, broken STEP, etc.)
            self._bbox_cache[abs_path] = None
            return None
