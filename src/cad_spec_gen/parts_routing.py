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


# ---------------------------------------------------------------------------
# Template location
# ---------------------------------------------------------------------------

def locate_builtin_templates_dir() -> Path | None:
    """Find the builtin templates/parts directory in both pip-install
    and repo-checkout modes. Returns None if neither location exists.

    Resolution order:
      1. Pip-installed: <cad_spec_gen package>/data/templates/parts/
      2. Repo-checkout: <repo_root>/templates/parts/
    """
    # Option 1: pip-installed — templates shipped as package data
    try:
        import importlib.resources as ir
        pkg_data = ir.files("cad_spec_gen") / "data" / "templates" / "parts"
        if pkg_data.is_dir():
            return Path(str(pkg_data))
    except (ImportError, ModuleNotFoundError, FileNotFoundError, AttributeError):
        pass

    # Option 2: repo-checkout — templates at repo root
    # This file lives at src/cad_spec_gen/parts_routing.py
    # → repo root = parents[2]
    repo_root = Path(__file__).resolve().parents[2]
    repo_templates = repo_root / "templates" / "parts"
    if repo_templates.is_dir():
        return repo_templates

    return None


# ---------------------------------------------------------------------------
# Discovery via AST
# ---------------------------------------------------------------------------

def _literal_eval_node(node):
    """Safely evaluate an AST node as a Python literal. Returns None on failure."""
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        return None


def _extract_descriptor_from_ast(
    tree,
    name: str,
    source_path: Path,
    tier: str,
) -> "TemplateDescriptor | None":
    """Parse a template module AST and extract its descriptor constants.

    Returns None if any required constant is missing or malformed.
    Never executes template code.
    """
    extracted: dict = {}
    has_make = False
    has_example_params = False

    for node in tree.body:
        # Function definitions
        if isinstance(node, ast.FunctionDef):
            if node.name == "make":
                has_make = True
            elif node.name == "example_params":
                has_example_params = True
            continue

        # Annotated assignments: MATCH_KEYWORDS: list[str] = [...]
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.value is not None:
                val = _literal_eval_node(node.value)
                if val is not None:
                    extracted[node.target.id] = val
            continue

        # Plain assignments: MATCH_KEYWORDS = [...]
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    val = _literal_eval_node(node.value)
                    if val is not None:
                        extracted[target.id] = val

    # Validate required fields
    if not has_make or not has_example_params:
        log.warning("Template %s missing make() or example_params()", source_path)
        return None

    required = ("MATCH_KEYWORDS", "MATCH_PRIORITY", "TEMPLATE_CATEGORY", "TEMPLATE_VERSION")
    for key in required:
        if key not in extracted:
            log.warning("Template %s missing %s constant", source_path, key)
            return None

    keywords = extracted["MATCH_KEYWORDS"]
    if not isinstance(keywords, list) or not all(isinstance(k, str) for k in keywords):
        log.warning("Template %s has invalid MATCH_KEYWORDS (expected list[str])", source_path)
        return None

    priority = extracted["MATCH_PRIORITY"]
    if not isinstance(priority, int):
        log.warning("Template %s has invalid MATCH_PRIORITY (expected int)", source_path)
        return None

    category = extracted["TEMPLATE_CATEGORY"]
    if category not in ALLOWED_CATEGORIES:
        log.warning("Template %s has unknown category '%s' (allowed: %s)",
                    source_path, category, ALLOWED_CATEGORIES)
        return None

    return TemplateDescriptor(
        name=name,
        keywords=tuple(sorted(keywords)),
        priority=priority,
        category=category,
        tier=tier,
        source_path=source_path,
    )


def _literal_eval(node: "ast.expr") -> Any:
    """Public alias kept for import compatibility. Delegates to _literal_eval_node."""
    return _literal_eval_node(node)


def discover_templates(search_paths: "list[Path]") -> "list[TemplateDescriptor]":
    """Scan search_paths for template .py files. Returns a list of descriptors.

    Pure function — reads files as text, parses with ast, does NOT import
    or execute template code. Malformed templates are logged (WARNING) and
    skipped. Duplicate names are resolved by tier order: later paths
    (Tier 3 project-local) override earlier paths (Tier 1 builtin).
    """
    descriptors_by_name: dict = {}

    for idx, search_dir in enumerate(search_paths):
        if not search_dir or not search_dir.is_dir():
            continue
        # Later paths are higher-tier (project overrides builtin)
        tier = "project" if idx > 0 else "builtin"
        for py_file in sorted(search_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            try:
                source = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except (SyntaxError, UnicodeDecodeError, OSError) as exc:
                log.warning("Skipping malformed template %s: %s", py_file, exc)
                continue
            desc = _extract_descriptor_from_ast(
                tree, name=py_file.stem, source_path=py_file, tier=tier,
            )
            if desc is not None:
                # Later tier wins on name collision
                descriptors_by_name[desc.name] = desc

    return sorted(descriptors_by_name.values(), key=lambda d: d.name)
