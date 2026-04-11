"""
adapters/parts/jinja_primitive_adapter.py — Fallback adapter wrapping the
current `_gen_*` dispatch from codegen/gen_std_parts.py.

This adapter is ALWAYS available and ALWAYS the last-resort fallback. It
preserves the existing simplified-primitive behavior byte-for-byte: the
`_gen_*` functions below are copied verbatim from gen_std_parts.py before the
refactor. Any behavioral change here is a bug.

Behavior:
- `is_available()` always returns True
- `resolve()` returns kind="codegen" with body_code exactly as before
- `probe_dims()` returns the dims that would be passed to _gen_*, so the
  Phase 1 backfill can pre-populate §6.4 with "what the fallback would draw"

This file plus the spec → dims resolution logic (lifted from gen_std_parts.py)
is the *only* piece that must produce byte-identical output for the
regression test in A9.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

# Ensure project root on sys.path so we can import the existing helpers
_PROJECT_ROOT = str(Path(__file__).parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from adapters.parts.base import PartsAdapter


# ─── Category geometry generators (lifted verbatim from gen_std_parts.py) ──
# Do NOT modify these functions without running the byte-identical regression
# test (A9). Any edit that changes the output of _gen_bearing, _gen_motor,
# etc. will break existing projects that rely on the generated code.


def _gen_motor(dims: dict) -> str:
    d = dims.get("d", 22)
    l = dims.get("l", 50)
    sd = dims.get("shaft_d", 4)
    sl = dims.get("shaft_l", 12)
    return f"""    # Simplified motor: cylinder + shaft
    body = cq.Workplane("XY").circle({d/2}).extrude({l})
    # Output shaft
    body = body.faces(">Z").workplane().circle({sd/2}).extrude({sl})
    return body"""


def _gen_reducer(dims: dict) -> str:
    d = dims.get("d", 25)
    l = dims.get("l", 35)
    sd = dims.get("shaft_d", 6)
    sl = dims.get("shaft_l", 10)
    return f"""    # Simplified reducer/gearbox: cylinder + output shaft
    body = cq.Workplane("XY").circle({d/2}).extrude({l})
    body = body.faces(">Z").workplane().circle({sd/2}).extrude({sl})
    return body"""


def _gen_spring(dims: dict) -> str:
    # Cylindrical mode (e.g. spring pin Φ4×20mm) — when only d/l given,
    # generate a solid pin instead of an annular disc spring.
    if "d" in dims and "l" in dims and "od" not in dims:
        d = dims["d"]
        l = dims["l"]
        return f"""    # Simplified spring pin: solid cylinder
    body = cq.Workplane("XY").circle({d/2}).extrude({l})
    return body"""
    od = dims.get("od", dims.get("d", 10))
    t = dims.get("t", 0.7)
    h = dims.get("h", dims.get("l", 0.85))
    id_ = dims.get("id", od * 0.5)
    return f"""    # Simplified disc spring: annular ring (stack approximation)
    body = (cq.Workplane("XY")
            .circle({od/2}).circle({id_/2}).extrude({max(t, h)})
            )
    return body"""


def _gen_bearing(dims: dict) -> str:
    od = dims.get("od", 12)
    id_ = dims.get("id", 6)
    w = dims.get("w", 4)
    return f"""    # Simplified bearing: outer ring + inner ring + gap
    outer = cq.Workplane("XY").circle({od/2}).circle({od/2 - 1}).extrude({w})
    inner = cq.Workplane("XY").circle({id_/2 + 1}).circle({id_/2}).extrude({w})
    body = outer.union(inner)
    return body"""


def _gen_sensor(dims: dict) -> str:
    if "d" in dims:
        d = dims["d"]
        l = dims.get("l", 12)
        return f"""    # Simplified sensor: cylinder
    body = cq.Workplane("XY").circle({d/2}).extrude({l})
    return body"""
    w = dims.get("w", 20)
    h = dims.get("h", 15)
    l = dims.get("l", 12)
    return f"""    # Simplified sensor: box
    body = cq.Workplane("XY").box({w}, {h}, {l}, centered=(True, True, False))
    return body"""


def _gen_pump(dims: dict) -> str:
    w = dims.get("w", 30)
    h = dims.get("h", 25)
    l = dims.get("l", 40)
    return f"""    # Simplified pump: box with port stubs
    body = cq.Workplane("XY").box({w}, {h}, {l}, centered=(True, True, False))
    # Input/output port stubs
    body = body.faces(">X").workplane().center(0, {l/2}).circle(3).extrude(5)
    body = body.faces("<X").workplane().center(0, {l/2}).circle(3).extrude(5)
    return body"""


def _gen_connector(dims: dict) -> str:
    d = dims.get("d", 10)
    l = min(dims.get("l", 25), 50)  # cap for assembly visualization
    if "w" in dims:
        w = dims["w"]
        h = dims.get("h", 3)
        l = min(dims.get("l", 8), 50)
        return f"""    # Simplified flat connector
    body = cq.Workplane("XY").box({w}, {l}, {h}, centered=(True, True, False))
    return body"""
    return f"""    # Simplified round connector
    body = cq.Workplane("XY").circle({d/2}).extrude({l})
    return body"""


def _gen_seal(dims: dict) -> str:
    od = dims.get("od", 80)
    section_d = dims.get("section_d", 2.4)
    id_ = dims.get("id", od - 2 * section_d)
    r_center = (od + id_) / 4
    return f"""    # Simplified O-ring: torus
    path = cq.Workplane("XY").circle({r_center})
    body = (cq.Workplane("XZ")
            .center({r_center}, 0)
            .circle({section_d/2})
            .sweep(path))
    return body"""


def _gen_tank(dims: dict) -> str:
    d = dims.get("d", 38)
    l = dims.get("l", 280)
    return f"""    # Simplified tank: cylinder with domed ends
    body = cq.Workplane("XY").circle({d/2}).extrude({l})
    return body"""


def _gen_generic(dims: dict) -> str:
    """Generic block for parts that don't match a specialized category.

    Used for things like 阻尼垫 (damping pad), 配重块 (counterweight), 压力阵列
    (pressure array) which are real physical parts that show up in BOM and
    chains but have no obvious geometric category. Without a generic
    fallback, the assembly validator reports gaps where these should be.
    """
    if "d" in dims and "l" in dims:
        return f"""    # Generic cylindrical block
    body = cq.Workplane("XY").circle({dims['d']/2}).extrude({dims['l']})
    return body"""
    w = dims.get("w", 20)
    h = dims.get("h", 5)
    l = dims.get("l", dims.get("d", 20))
    return f"""    # Generic rectangular block
    body = cq.Workplane("XY").box({w}, {l}, {h}, centered=(True, True, False))
    return body"""


_GENERATORS = {
    "motor":     _gen_motor,
    "reducer":   _gen_reducer,
    "spring":    _gen_spring,
    "bearing":   _gen_bearing,
    "sensor":    _gen_sensor,
    "pump":      _gen_pump,
    "connector": _gen_connector,
    "seal":      _gen_seal,
    "tank":      _gen_tank,
    "other":     _gen_generic,
}

# Categories to skip (too small or too complex for simplified geometry).
_SKIP_CATEGORIES = {"fastener", "cable"}


def _resolve_dims_from_spec_envelope_or_lookup(query) -> Optional[dict]:
    """Reproduce the original dims-resolution logic from gen_std_parts.py.

    Order:
      0. If query.spec_envelope is set BUT granularity is NOT "part_envelope"
         (i.e. it's a station_constraint or component-level envelope),
         REJECT and fall through to lookup — station constraints describe
         an outer bounding box that multiple parts must fit inside, NOT
         the size of an individual part. This enforcement is the last
         step of the six-step granularity chain from the walker spec.
      1. If query.spec_envelope is set AND granularity is "part_envelope",
         convert (w,d,h) → dims dict
      2. Else call lookup_std_part_dims(name, material, category)
      3. Else for category="other", use a small default block
      4. Else return None (caller should skip)
    """
    from cad_spec_defaults import lookup_std_part_dims

    if query.spec_envelope is not None:
        granularity = getattr(query, "spec_envelope_granularity", "part_envelope")
        if granularity == "part_envelope":
            w, d, h = query.spec_envelope
            if abs(w - d) < 0.1:  # cylindrical
                return {"d": w, "l": h}
            else:
                return {"w": w, "d": d, "h": h}
        else:
            # station_constraint / component — do NOT size an individual part.
            import logging
            logging.getLogger("jinja_primitive_adapter").debug(
                "spec_envelope for %s has granularity=%s; deferring to lookup",
                query.part_no, granularity,
            )

    dims = lookup_std_part_dims(query.name_cn, query.material, query.category)
    if dims:
        return dims

    # "other" parts always need a file because gen_assembly.py imports them
    if query.category == "other":
        return {"d": 15, "l": 10}

    return None


# ─── The adapter class itself ──────────────────────────────────────────────


class JinjaPrimitiveAdapter(PartsAdapter):
    """Always-available fallback that reproduces pre-refactor behavior.

    This adapter exists so that the refactor of gen_std_parts.py into the
    resolver architecture is behaviorally identical when no parts_library.yaml
    is present.
    """

    name = "jinja_primitive"

    def is_available(self) -> bool:
        return True

    def can_resolve(self, query) -> bool:
        if query.category in _SKIP_CATEGORIES:
            return False
        return query.category in _GENERATORS

    def resolve(self, query, spec: dict):
        # Import ResolveResult lazily to avoid circular import during package
        # init (parts_resolver.py → default_resolver → adapters.parts → here)
        from parts_resolver import ResolveResult

        if query.category in _SKIP_CATEGORIES:
            return ResolveResult.miss()

        gen_func = _GENERATORS.get(query.category)
        if gen_func is None:
            return ResolveResult.miss()

        dims = _resolve_dims_from_spec_envelope_or_lookup(query)
        if dims is None:
            return ResolveResult.miss()

        body_code = gen_func(dims)
        return ResolveResult(
            status="hit",
            kind="codegen",
            adapter=self.name,
            body_code=body_code,
            real_dims=self._dims_to_envelope(dims),
            source_tag=f"jinja_primitive:{query.category}",
            metadata={"dims": dims},  # preserved for legacy header format
        )

    def probe_dims(self, query, spec: dict) -> Optional[tuple]:
        """Return (w, d, h) as the jinja adapter would draw it.

        Used by Phase 1 backfill to pre-populate §6.4 for parts where the
        only information source is classify_part + lookup_std_part_dims.
        Same dims the _gen_* function would consume.
        """
        if query.category in _SKIP_CATEGORIES:
            return None
        dims = _resolve_dims_from_spec_envelope_or_lookup(query)
        if dims is None:
            return None
        return self._dims_to_envelope(dims)

    @staticmethod
    def _dims_to_envelope(dims: dict) -> Optional[tuple]:
        """Best-effort conversion of a _gen_* dims dict to a (w, d, h) tuple."""
        if "d" in dims and "l" in dims and "od" not in dims:
            return (dims["d"], dims["d"], dims["l"])
        if "od" in dims:
            h = dims.get("h", dims.get("l", dims.get("t", 5)))
            return (dims["od"], dims["od"], h)
        if "w" in dims and "h" in dims and "l" in dims:
            return (dims["w"], dims["d"] if "d" in dims else dims["w"],
                    dims["h"] if dims.get("h") else dims.get("l", 20))
        if "w" in dims and "l" in dims:
            return (dims["w"],
                    dims.get("d", dims["w"]),
                    dims.get("h", 20))
        return None
