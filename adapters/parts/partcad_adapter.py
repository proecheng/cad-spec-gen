"""
adapters/parts/partcad_adapter.py — Phase C adapter for PartCAD package manager.

PartCAD (https://github.com/partcad/partcad) is a package manager for CAD
parts. It provides a cross-project registry where teams can publish custom
parts (CadQuery / build123d / OpenSCAD / STEP / STL) and consume them from
other projects via simple `package_name:part_name` references.

This adapter is OPT-IN: it does nothing unless
`parts_library.yaml` has::

    partcad:
      enabled: true

Even when enabled, the adapter stays inactive if `import partcad` fails.
This keeps PartCAD a soft dependency — downstream projects that don't want
it can avoid the extra install weight.

## Generated code

When a mapping rule points a BOM row at this adapter::

    - match: {part_no: "GIS-EE-001-06"}
      adapter: partcad
      spec:
        part_ref: "gisbot_parts:gp22c_reducer"

the resolver emits `kind="python_import"` and gen_std_parts.py writes::

    def make_std_ee_001_06() -> cq.Workplane:
        import partcad as pc
        _solid = pc.get_part_cadquery("gisbot_parts:gp22c_reducer")
        return cq.Workplane("XY").newObject([_solid])

The lazy import keeps spec-gen machines free of the partcad dep;
only the machine that runs Phase 3 BUILD needs it installed.

## Data flow

- `is_available()` — cheap: returns True iff the registry YAML has
  `partcad.enabled: true`. Does NOT import partcad.
- `can_resolve()` — returns True if the adapter is enabled AND the rule
  has a `spec.part_ref` field.
- `resolve()` — imports partcad lazily. If import fails, returns a
  `miss` with a warning.
- `probe_dims()` — imports partcad lazily, calls get_part_cadquery() to
  actually build the geometry, computes BBox. Results cached per-adapter
  so the same part is never built twice.

## PartCAD init context

PartCAD's `init()` searches upward from cwd for a `partcad.yaml` file.
The adapter calls `init(config_path=...)` if the registry specifies
`partcad.config_path`; otherwise it relies on the default search, which
finds partcad.yaml in project_root (or any parent).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = str(Path(__file__).parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from adapters.parts.base import PartsAdapter


class PartCADAdapter(PartsAdapter):
    """Adapter that dispatches to PartCAD for cross-project part packages.

    Parameters
    ----------
    project_root : str
        Used as the working directory when PartCAD init() searches for a
        partcad.yaml config.
    config : dict
        The `partcad:` block from parts_library.yaml. Supports:
          - enabled: bool (default False) — master switch
          - config_path: str (optional) — explicit partcad.yaml path
          - packages: list (informational, not used by adapter)
    """

    name = "partcad"

    def __init__(self, project_root: str = "", config: Optional[dict] = None):
        self.project_root = project_root or os.getcwd()
        self.config = config or {}
        self._solid_cache: dict = {}  # part_ref → cq.Solid
        self._bbox_cache: dict = {}   # part_ref → (w, d, h)
        self._partcad_init_done = False

    # ---- PartsAdapter interface -------------------------------------------

    def is_available(self) -> tuple[bool, Optional[str]]:
        """Return (True, None) only if explicitly enabled in the registry.

        Does not import partcad — that would pull in a big dep chain to check.
        """
        if not self.config.get("enabled"):
            return False, "partcad.enabled=false in yaml"
        return True, None

    def can_resolve(self, query) -> bool:
        ok, _ = self.is_available()
        return ok

    def resolve(self, query, spec: dict):
        from parts_resolver import ResolveResult

        ok, _ = self.is_available()
        if not ok:
            return ResolveResult.miss()

        part_ref = spec.get("part_ref")
        if not part_ref:
            return ResolveResult(
                status="miss",
                kind="miss",
                adapter=self.name,
                warnings=["partcad adapter requires spec.part_ref"],
            )

        # Lazy import — partcad is a big optional dep
        if not self._try_init():
            return ResolveResult(
                status="miss",
                kind="miss",
                adapter=self.name,
                warnings=["partcad package not installed; skipping"],
            )

        # Probe dims (cached) so §6.4 can be populated
        dims = self._probe_dims_impl(part_ref, spec.get("params"))

        params = spec.get("params")
        params_arg = f", params={params!r}" if params is not None else ""

        return ResolveResult(
            status="hit",
            kind="python_import",
            adapter=self.name,
            import_module="partcad",
            # Emit a special symbol the gen_std_parts code-emitter knows
            # about. Because the generated function needs to call
            # `pc.get_part_cadquery(...)` and wrap the result, it's not a
            # plain "from X import Y" style. We reuse import_args to carry
            # the part_ref and params; gen_std_parts.py has a partcad-
            # specific branch (or uses a generic call template).
            import_symbol="get_part_cadquery",
            import_args=f"{part_ref!r}{params_arg}",
            real_dims=dims,
            source_tag=f"PC:{part_ref}",
        )

    def probe_dims(self, query, spec: dict) -> Optional[tuple]:
        ok, _ = self.is_available()
        if not ok:
            return None
        part_ref = spec.get("part_ref")
        if not part_ref:
            return None
        if not self._try_init():
            return None
        return self._probe_dims_impl(part_ref, spec.get("params"))

    # ---- Internal -------------------------------------------------------

    def _try_init(self) -> bool:
        """Attempt to import partcad and initialize its context. Idempotent."""
        if self._partcad_init_done:
            return True
        try:
            import partcad as pc  # noqa: F401
        except ImportError:
            return False

        try:
            config_path = self.config.get("config_path")
            if config_path:
                config_path = self._resolve_config_path(config_path)
            # Change to project_root so partcad's default search finds
            # partcad.yaml in the project (it walks up from cwd).
            _orig_cwd = os.getcwd()
            try:
                if os.path.isdir(self.project_root):
                    os.chdir(self.project_root)
                pc.init(config_path=config_path)
            finally:
                os.chdir(_orig_cwd)
            self._partcad_init_done = True
            return True
        except Exception:
            # Anything wrong with partcad init → disable adapter silently
            return False

    def _resolve_config_path(self, path: str) -> str:
        """Expand ~ and resolve relative paths against project_root."""
        path = os.path.expanduser(path)
        if not os.path.isabs(path):
            path = os.path.join(self.project_root, path)
        return os.path.normpath(path)

    def _probe_dims_impl(self, part_ref: str, params) -> Optional[tuple]:
        """Load the part, compute BBox, cache."""
        cache_key = (part_ref, repr(params))
        if cache_key in self._bbox_cache:
            return self._bbox_cache[cache_key]

        try:
            import partcad as pc
            solid = pc.get_part_cadquery(part_ref, params=params)
            if solid is None:
                self._bbox_cache[cache_key] = None
                return None
            self._solid_cache[cache_key] = solid
            # cq.Solid has a BoundingBox() method
            bbox = solid.BoundingBox()
            dims = (
                round(bbox.xmax - bbox.xmin, 2),
                round(bbox.ymax - bbox.ymin, 2),
                round(bbox.zmax - bbox.zmin, 2),
            )
            self._bbox_cache[cache_key] = dims
            return dims
        except Exception:
            self._bbox_cache[cache_key] = None
            return None
