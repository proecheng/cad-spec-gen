"""cad-spec-gen parts template library — data directory.

Templates in this directory are discovered at runtime via filesystem
iteration by `cad_spec_gen.parts_routing.discover_templates`. They are
NOT imported as Python modules through this __init__.py — each template
file is parsed via AST or loaded on demand via importlib.util.

Each template file must define:
    - make(**params) -> cq.Workplane
    - MATCH_KEYWORDS: list[str]
    - MATCH_PRIORITY: int
    - TEMPLATE_CATEGORY: str (bracket | housing | plate | mechanical_interface | fastener_family)
    - TEMPLATE_VERSION: str
    - example_params() -> dict

See templates/parts/iso_9409_flange.py for the canonical example.

This directory is shipped to pip users at:
    <site-packages>/cad_spec_gen/data/templates/parts/
via hatch_build.py's COPY_DIRS mechanism.
"""
