"""cad_spec_gen.parts_routing — pure functions for template routing.

This module is intentionally side-effect-free:
  - No importlib.import_module of template code
  - No filesystem writes
  - No downloads
  - No prints (only logging at DEBUG)

It is consumed by:
  - codegen/gen_parts.py (Spec 1, log-only)
  - Spec 2's cad_spec_reviewer.py Phase R (invariant #9: same simulation path)

See docs/superpowers/specs/2026-04-10-spec1-foundation-design.md §7 for design.
"""
from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Frozen data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GeomInfo:
    """Frozen snapshot of _guess_geometry output — no dict ambiguity.

    Converted from codegen/gen_parts.py's _guess_geometry() dict return
    via a small adapter function in that file.
    """
    type: str                    # "box" | "cylinder" | "disc_arms" | "ring" | "l_bracket" | "plate"
    envelope_w: float
    envelope_d: float
    envelope_h: float
    extras: dict = field(default_factory=dict)


@dataclass(frozen=True)
class TemplateDescriptor:
    """What parts_routing knows about a template — metadata only.

    Extracted via AST parsing without importing/executing template code.
    Tier: "builtin" (Tier 1, skill-shipped) | "project" (Tier 3, project-local)
    """
    name: str                    # module stem, e.g. "l_bracket"
    keywords: tuple              # from MATCH_KEYWORDS, sorted
    priority: int                # from MATCH_PRIORITY
    category: str                # from TEMPLATE_CATEGORY
    tier: str                    # "builtin" | "project"
    source_path: Path            # for debug / validate template command


@dataclass(frozen=True)
class RouteDecision:
    """Result of a routing decision — consumed by gen_parts or reviewer.

    Pure data: no exceptions, no logging from inside route().
    """
    outcome: str                 # "HIT_BUILTIN" | "HIT_PROJECT" | "FALLBACK" | "AMBIGUOUS"
    template: TemplateDescriptor | None
    reason: str = ""
    ambiguous_candidates: tuple = ()


# Category allowlist (matches §6.2.3 of the spec)
ALLOWED_CATEGORIES = {
    "bracket",
    "housing",
    "plate",
    "mechanical_interface",
    "fastener_family",
}
