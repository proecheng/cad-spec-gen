"""
adapters/parts/bd_warehouse_adapter.py — Phase A adapter for bd_warehouse.

bd_warehouse ships parametric bearings, fasteners, and threaded parts. This
adapter:

1. Uses a static catalog YAML (`catalogs/bd_warehouse_catalog.yaml`) to
   answer `is_available()` and `can_resolve()` WITHOUT importing bd_warehouse
   — essential for CI environments where bd_warehouse is not installed.
2. Lazy-imports bd_warehouse only inside `resolve()` / `probe_dims()` when a
   match has been confirmed.
3. Emits `ResolveResult.kind="python_import"` so gen_std_parts.py produces
   a `make_*()` function body that defers bd_warehouse import to run time
   (so build_all.py only needs bd_warehouse on the machine that executes
   the build, not on the spec-gen machine).

The generated code looks like this::

    import cadquery as cq
    from parts_resolver import bd_to_cq

    def make_std_ee_001_03() -> cq.Workplane:
        from bd_warehouse.bearing import SingleRowDeepGrooveBallBearing
        part = SingleRowDeepGrooveBallBearing(
            size="M8-22-7", bearing_type="SKT"
        )
        return bd_to_cq(part)

Graceful degradation: if bd_warehouse is not installed at build time, the
generated module will fail at import. The pipeline should catch this and
either warn the user to `pip install bd_warehouse` or regenerate without
the bd_warehouse mapping.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = str(Path(__file__).parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from adapters.parts.base import PartsAdapter


_DEFAULT_CATALOG_PATH = os.path.join(
    _PROJECT_ROOT, "catalogs", "bd_warehouse_catalog.yaml")


class BdWarehouseAdapter(PartsAdapter):
    """Adapter that dispatches to bd_warehouse parametric classes.

    Matching strategy (executed in resolve()):
      1. Check the YAML rule's `spec.class` — explicit class to use
      2. If spec.size or spec.size_from is set, use that size directly
      3. Else try to extract the size from query.name_cn / query.material
         using the catalog's size_patterns
      4. Look up the size in the class's iso_designation_map to get dims
      5. Return kind="python_import" with the class + constructor args
    """

    name = "bd_warehouse"

    def __init__(self, project_root: str = "", catalog_path: Optional[str] = None):
        self.project_root = project_root
        self.catalog_path = catalog_path or _DEFAULT_CATALOG_PATH
        self._catalog: Optional[dict] = None

    # ---- PartsAdapter interface -------------------------------------------

    def is_available(self) -> bool:
        # We only need the catalog YAML, not bd_warehouse itself.
        return os.path.isfile(self.catalog_path) and self._try_load_catalog()

    def can_resolve(self, query) -> bool:
        if not self._try_load_catalog():
            return False
        # Quick check: does any catalog class mention this category?
        if query.category == "bearing":
            return bool(self._catalog.get("bearings"))
        if query.category == "fastener":
            return bool(self._catalog.get("fasteners"))
        return False

    def resolve(self, query, spec: dict):
        from parts_resolver import ResolveResult

        if not self._try_load_catalog():
            return ResolveResult.miss()

        # Find the target class — either from spec or by category auto-match
        class_info = self._find_class(query, spec)
        if class_info is None:
            return ResolveResult.miss()

        # Determine constructor args (size + type)
        ctor_args = self._build_ctor_args(query, spec, class_info)
        if ctor_args is None:
            return ResolveResult.miss()

        # Probe dims from the catalog (cheap)
        dims = self._probe_dims_from_catalog(query, spec, class_info, ctor_args)

        module_name = class_info["module"]
        class_name = class_info["class"]
        args_str = ", ".join(f"{k}={v!r}" for k, v in ctor_args.items())

        return ResolveResult(
            status="hit",
            kind="python_import",
            adapter=self.name,
            import_module=module_name,
            import_symbol=class_name,
            import_args=args_str,
            real_dims=dims,
            source_tag=f"BW:{class_name}({args_str})",
        )

    def probe_dims(self, query, spec: dict) -> Optional[tuple]:
        if not self._try_load_catalog():
            return None
        class_info = self._find_class(query, spec)
        if class_info is None:
            return None
        ctor_args = self._build_ctor_args(query, spec, class_info)
        if ctor_args is None:
            return None
        return self._probe_dims_from_catalog(query, spec, class_info, ctor_args)

    # ---- Catalog loading --------------------------------------------------

    def _try_load_catalog(self) -> bool:
        if self._catalog is not None:
            return bool(self._catalog)
        try:
            import yaml
        except ImportError:
            self._catalog = {}
            return False
        if not os.path.isfile(self.catalog_path):
            self._catalog = {}
            return False
        try:
            with open(self.catalog_path, encoding="utf-8") as f:
                self._catalog = yaml.safe_load(f) or {}
            return bool(self._catalog)
        except Exception:
            self._catalog = {}
            return False

    # ---- Class lookup + size extraction -----------------------------------

    def _find_class(self, query, spec: dict) -> Optional[dict]:
        """Resolve the catalog class info to use for this query."""
        # Case 1: YAML rule explicitly names a class
        explicit_class = spec.get("class")
        if explicit_class:
            for entry in self._iter_catalog_entries():
                if entry.get("class") == explicit_class:
                    return entry
            return None

        # Case 2: auto-match by category + name keywords
        if query.category == "bearing":
            candidates = self._catalog.get("bearings", [])
        elif query.category == "fastener":
            candidates = self._catalog.get("fasteners", [])
        else:
            return None

        name_lower = query.name_cn.lower()
        mat_lower = query.material.lower()
        for entry in candidates:
            for kw in entry.get("name_keywords", []):
                if kw.lower() in name_lower:
                    return entry
            for kw in entry.get("material_keywords", []):
                if kw.lower() in mat_lower:
                    return entry
            for kw in entry.get("size_keywords", []):
                if kw.lower() in mat_lower or kw.lower() in name_lower:
                    return entry
        return None

    def _iter_catalog_entries(self):
        for section in ("bearings", "fasteners"):
            for entry in self._catalog.get(section, []):
                yield entry

    def _build_ctor_args(self, query, spec: dict, class_info: dict) -> Optional[dict]:
        """Resolve the size + type args to pass to the bd_warehouse class.

        Priority:
          1. spec.size (exact literal, e.g. {"size": "M8-22-7"})
          2. spec.size_from = "name" → extract from query.name_cn
          3. spec.size_from = "material" → extract from query.material
          4. spec.size_from = {"regex": ..., "template": ...} → regex capture
          5. Auto-extract from BOM text using catalog size_patterns
        """
        size_from = spec.get("size_from")
        explicit_size = spec.get("size")

        if explicit_size:
            size = explicit_size
        elif isinstance(size_from, str):
            text = query.name_cn if size_from == "name" else query.material
            size = self._extract_size(text, class_info)
        elif isinstance(size_from, dict):
            rx = size_from.get("regex", "")
            tmpl = size_from.get("template", "{0}")
            text = query.name_cn + " " + query.material
            m = re.search(rx, text)
            if not m:
                return None
            size = tmpl.format(*m.groups())
        else:
            # Auto
            size = self._auto_extract_size(query, class_info)

        if not size:
            return None

        args = {"size": size}

        # Bearing type defaults
        if "default_bearing_type" in class_info:
            args["bearing_type"] = class_info["default_bearing_type"]
        if "default_fastener_type" in class_info:
            args["fastener_type"] = class_info["default_fastener_type"]

        # Allow YAML rule to override
        for k, v in spec.get("extra_args", {}).items():
            args[k] = v

        return args

    def _extract_size(self, text: str, class_info: dict) -> Optional[str]:
        """Extract a size string from a single text field."""
        return self._auto_extract_size_from_text(text, class_info)

    def _auto_extract_size(self, query, class_info: dict) -> Optional[str]:
        """Try name_cn then material then name+material."""
        for text in (query.name_cn, query.material, query.name_cn + " " + query.material):
            size = self._auto_extract_size_from_text(text, class_info)
            if size:
                return size
        return None

    def _auto_extract_size_from_text(self, text: str, class_info: dict) -> Optional[str]:
        """Match catalog size_patterns against free text.

        Strategy for bearings:
          1. Direct longest-key substring match against iso_designation_map.
             This catches designations like 'NU2204', '7202B', '623-2Z'
             where the suffix/prefix letters distinguish bearing classes.
          2. Fall back to the iso_bearing regex (digit-only pattern) for
             cases where the BOM uses just the numeric core like '608'.

        Strategy for fasteners:
          1. metric_screw regex: 'M3×10' → ('M3-0.5')
          2. metric_diameter regex: 'M6 平垫圈' → ('M6-1') for washers/nuts
        """
        patterns = self._catalog.get("size_patterns", {})

        # ── Bearings ──
        iso_map = class_info.get("iso_designation_map", {})
        if iso_map:
            # Pass 1: longest-key substring match (handles letter suffixes)
            # Sort keys by length DESC so 'NU2204' beats 'NU220' on overlap
            for designation in sorted(iso_map.keys(), key=len, reverse=True):
                if designation in text:
                    return iso_map[designation]["csv_key"]

            # Pass 2: digit-only iso_bearing regex (legacy path)
            rx = patterns.get("iso_bearing", "")
            if rx:
                for m in re.finditer(rx, text):
                    designation = m.group(1)
                    if designation in iso_map:
                        return iso_map[designation]["csv_key"]

        # ── Fasteners ──
        # First try the M{d}×{length} pattern (screws with explicit length)
        rx = patterns.get("metric_screw", "")
        if rx:
            m = re.search(rx, text)
            if m:
                d = float(m.group(1))
                l = float(m.group(2))
                pitch_map = {1.6: 0.35, 2: 0.4, 2.5: 0.45, 3: 0.5,
                             4: 0.7, 5: 0.8, 6: 1.0, 8: 1.25,
                             10: 1.5, 12: 1.75, 14: 2.0, 16: 2.0,
                             20: 2.5, 24: 3.0, 30: 3.5, 36: 4.0}
                pitch = pitch_map.get(d, pitch_map.get(int(d), 0.5))
                return f"M{int(d) if d == int(d) else d}-{pitch}"

        # Fall back to M{d} alone (washers, nuts, parts without length)
        m = re.search(r'\bM(\d+(?:\.\d+)?)\b', text)
        if m:
            d = float(m.group(1))
            pitch_map = {1.6: 0.35, 2: 0.4, 2.5: 0.45, 3: 0.5,
                         4: 0.7, 5: 0.8, 6: 1.0, 8: 1.25,
                         10: 1.5, 12: 1.75, 14: 2.0, 16: 2.0,
                         20: 2.5, 24: 3.0, 30: 3.5, 36: 4.0}
            pitch = pitch_map.get(d, pitch_map.get(int(d), 0.5))
            # Some bd_warehouse classes (washers) use bare "M{d}" not "M{d}-{p}"
            # so try both forms downstream — return the dashed form first.
            return f"M{int(d) if d == int(d) else d}-{pitch}"

        return None

    def _probe_dims_from_catalog(
        self, query, spec: dict, class_info: dict, ctor_args: dict
    ) -> Optional[tuple]:
        """Return (w, d, h) without importing bd_warehouse.

        For bearings, look up the csv_key in iso_designation_map.
        For fasteners, we don't know the length without parsing the size
        string further — return None and let §6.4 keep the P3:BOM value.
        """
        size = ctor_args.get("size", "")

        iso_map = class_info.get("iso_designation_map", {})
        for designation, entry in iso_map.items():
            if entry.get("csv_key") == size:
                d = entry.get("D", 0)  # outer diameter
                b = entry.get("B", 0)  # width
                return (d, d, b)

        # Fastener: size like "M3-0.5" — no length info here
        return None
