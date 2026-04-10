"""
cad-spec-gen parts template library
===================================

Reusable parametric CadQuery templates for common mechanical part
morphologies. Each template is a self-contained module exposing a
`make(**params) -> cq.Workplane` function that returns a fully detailed,
renderable part.

Templates (current):
    - iso_9409_flange   Robot tool flange per ISO 9409-1 with optional
                        cross-arm hub overlay and station mounting holes.

Templates are intentionally **verbose and detail-rich** (fillets,
chamfers, counterbores, rib stiffeners) so renders look like real
machined parts — not like the ad-hoc "box + cylinder + union" code the
heuristic `gen_parts.py` scaffold falls back to.

Usage from a project's part module (`cad/<subsystem>/ee_*.py`)::

    from cad_spec_gen.templates.parts import iso_9409_flange

    def make_ee_001_01():
        return iso_9409_flange.make(
            outer_dia=90.0,
            thickness=25.0,
            iso_pcd=50.0,
            iso_bolt_dia=6.0,
            iso_bolt_count=4,
            ...
        )

When invoked from project-generated code that can't import the skill
package, the template module can also be copied verbatim into the
project's cad/<subsystem>/ directory — each template is pure CadQuery
with no cross-template dependencies.
"""

from . import iso_9409_flange  # noqa: F401

__all__ = ["iso_9409_flange"]
