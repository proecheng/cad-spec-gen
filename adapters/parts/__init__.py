"""
adapters/parts/ — Parts library adapters for the unified PartsResolver.

Each adapter implements the PartsAdapter protocol (see base.py):
    - is_available() — can the adapter be used in this environment?
    - can_resolve(query) — will a resolve() call hit for this query?
    - resolve(query, spec) — return a ResolveResult describing the geometry source
    - probe_dims(query, spec) — return (w, d, h) without building geometry

Adapters are loaded lazily by `parts_resolver.default_resolver()`. An adapter
that fails to import (e.g. bd_warehouse missing) is silently skipped — it is
never the system's responsibility to install optional dependencies.

Phase A ships:
    - JinjaPrimitiveAdapter (always available, fallback)
    - BdWarehouseAdapter    (optional, bd_warehouse package)

Phase B adds:
    - StepPoolAdapter       (always available, uses project std_parts/ dir)

Phase C adds:
    - PartCADAdapter        (optional, partcad package)
"""

from .base import PartsAdapter

__all__ = ["PartsAdapter"]
