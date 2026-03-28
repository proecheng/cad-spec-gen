#!/usr/bin/env python3
"""
Enhance Prompt — Build Gemini enhancement prompts from render_config.json.

Single source of truth for prompt placeholder filling logic.
Uses a unified template (prompt_enhance_unified.txt) for ALL view types.

When a cad_dir is provided (or detectable from rc), auto-generates
assembly_description, material_descriptions, standard_parts, and
negative_constraints from params.py via prompt_data_builder.
"""

import os
import re

SKILL_ROOT = os.path.dirname(os.path.abspath(__file__))

# Template search paths (canonical first, fallback second)
_TEMPLATE_SEARCH = [
    os.path.join(SKILL_ROOT, "templates"),
    os.path.join(SKILL_ROOT, "tools", "hybrid_render", "prompts"),
]

_UNIFIED_TEMPLATE = "prompt_enhance_unified.txt"

# View type → view_type_note (§3)
_VIEW_TYPE_NOTES = {
    "standard": "",
    "exploded": (
        "Each module is displaced radially outward from the central hub "
        "to show assembly relationships. Explosion gaps MUST remain clearly visible. "
        "Add subtle shadows beneath floating components."
    ),
    "ortho": (
        "Orthographic projection — NO perspective distortion. "
        "Maintain flat, parallel projection throughout."
    ),
    "section": (
        "The assembly is cut along {cut_plane} plane to expose internal structures. "
        "Cut faces show machined cross-sections with distinct material appearance."
    ),
}

# View type → environment lighting (§9)
_VIEW_TYPE_ENV = {
    "standard": (
        "Studio lighting: soft key light from upper-left, fill light from right, "
        "subtle rim light. Neutral gradient background. "
        "8K product photography quality."
    ),
    "exploded": (
        "Studio lighting with subtle shadows beneath floating components. "
        "Neutral gradient background. 8K exploded-view product photography."
    ),
    "ortho": (
        "Flat, even studio lighting for engineering reference. "
        "Sharp edges, no depth-of-field blur. "
        "Neutral gradient background. 8K orthographic product photography."
    ),
    "section": (
        "Studio lighting with key light from upper-right emphasizing cut face depth. "
        "Neutral gradient background, no reflections on background. "
        "8K photorealistic quality."
    ),
}

# Section face treatment text (§5 extension, only for type=section)
_SECTION_FACE_TREATMENT = """Cross-section face treatment:
- Cut aluminum faces: fine machined cross-hatch pattern, slight golden tint from anodization edge
- Cut PEEK faces: warm amber translucent edge, visible subsurface depth
- Internal cavities: shadow depth with ambient occlusion
- Visible springs: chrome wire coils with specular highlights, each turn clearly defined
- Bearing cross-sections: chrome steel races, brass cage visible
- Gear teeth: machined steel with fine tooth profile shadows
- Motor windings: copper color visible through housing cut
- PCB edge: green FR4 with copper trace layers"""

# Multi-view consistency rules (§8, always enabled)
_CONSISTENCY_RULES = """\
- All views (V1-V6) depict the SAME physical assembly — use IDENTICAL materials, colors, textures in every view.
- Part orientations are FIXED by the coordinate system and NEVER change between views:
  * LONG tank (Phi38x280mm): ALWAYS horizontal (axis parallel to XY, extending radially outward)
  * SHORT tank (Phi25x110mm): ALWAYS vertical (axis parallel to Z, parallel to module body)
  * Motor+gearbox (Phi22x73mm): ALWAYS on arm-side (+Z, above flange), NEVER below
  * PEEK ring (Phi86mm): ALWAYS slightly smaller than flange (Phi90mm), 5mm thin amber ring
  * AE spring limiter axis: ALWAYS perpendicular to flange face (along -Z), NEVER horizontal
- Do NOT alter any part orientation to "look better" from this camera angle — geometry is physically fixed.
- Material consistency: same dark gray anodization shade, same amber PEEK translucency, same brushed stainless grain, same matte black rubber in every view."""


def _build_consistency_rules(rc):
    """Build generic consistency rules from render_config; no hardcoded subsystem dims."""
    nc = rc.get("negative_constraints", [])

    # Derive constraint lines from negative_constraints entries (if any)
    dim_lines = ""
    if nc:
        # Format the top N constraints as bullet points for the consistency block
        dim_lines = "".join(f"- {c}\n" for c in nc[:6])

    rules = (
        "- All views depict the SAME physical assembly — use IDENTICAL materials, colors, "
        "textures in every view.\n"
        "- Part orientations are FIXED by the coordinate system and NEVER change between views.\n"
    )
    if dim_lines:
        rules += "- Key dimensional constraints to maintain:\n" + dim_lines
    rules += (
        "- Do NOT alter any part orientation to \"look better\" from a camera angle — "
        "geometry is physically fixed.\n"
        "- Material consistency: repeat identical surface treatments, sheen, and colour in every view."
    )
    return rules


def load_template():
    """Load the unified prompt template.

    Returns:
        template text string
    Raises:
        FileNotFoundError if template not found
    """
    for d in _TEMPLATE_SEARCH:
        p = os.path.join(d, _UNIFIED_TEMPLATE)
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                return f.read()
    raise FileNotFoundError(
        f"Template '{_UNIFIED_TEMPLATE}' not found in: {_TEMPLATE_SEARCH}"
    )


def _get_view_type(view_key, rc):
    """Determine view type from render_config camera settings."""
    cameras = rc.get("camera", {})
    cam = cameras.get(view_key, {})
    vtype = cam.get("type", "standard")
    return vtype


def fill_prompt_template(tmpl_text, view_key, rc, is_v1_done=False):
    """Fill all placeholders in the unified enhance prompt template.

    Args:
        tmpl_text: raw template string with {placeholders}
        view_key: "V1", "V2", etc.
        rc: parsed render_config.json dict (or empty dict)
        is_v1_done: unused (kept for API compatibility), consistency always enabled
    Returns:
        filled prompt string
    """
    pv = rc.get("prompt_vars", {})
    view_type = _get_view_type(view_key, rc)

    # §2 {coordinate_system}
    coordinate_system = rc.get("coordinate_system", "")

    # §3 {product_name}, {view_description}, {view_type_note}
    product_name = pv.get("product_name", "precision mechanical assembly")
    view_desc = rc.get("view_descriptions", {}).get(view_key, "isometric view")

    view_type_note = _VIEW_TYPE_NOTES.get(view_type, "")
    # Fill {cut_plane} in section note if applicable
    if view_type == "section":
        section_cfg = rc.get("section", {})
        cut_plane = section_cfg.get("cut_plane", "YZ")
        view_type_note = view_type_note.replace("{cut_plane}", cut_plane)

    # §4 {assembly_description}
    assembly_desc = rc.get("assembly_description", {}).get(view_key, "")

    # §5 {material_descriptions}
    descs = pv.get("material_descriptions", [])
    if descs:
        mat_lines = [
            f"- {d.get('visual_cue', '')}: {d.get('material_desc', '')}"
            for d in descs
        ]
        material_desc = "\n".join(mat_lines)
    else:
        material_desc = ""

    # §5 {section_face_treatment} — only for section views
    section_face = _SECTION_FACE_TREATMENT if view_type == "section" else ""

    # §6 {standard_parts_description}
    std_parts = rc.get("standard_parts", [])
    if std_parts:
        sp_lines = [
            "STANDARD PARTS (enhance simplified shapes to real-world appearance):"
        ]
        for sp in std_parts:
            sp_lines.append(
                f"- {sp.get('visual_cue', '')}: {sp.get('real_part', '')}"
            )
        std_parts_desc = "\n".join(sp_lines)
    else:
        std_parts_desc = ""

    # §7 {negative_constraints}
    nc = rc.get("negative_constraints", [])
    neg_text = "\n".join(f"- {c}" for c in nc) if nc else ""

    # §8 {consistency_rules} — always enabled; try to use auto-generated dimensions
    consistency_rules = _build_consistency_rules(rc)

    # §9 {environment}
    environment = _VIEW_TYPE_ENV.get(view_type, _VIEW_TYPE_ENV["standard"])

    # Fill all placeholders
    prompt = tmpl_text
    for key, val in [
        ("{coordinate_system}", coordinate_system),
        ("{product_name}", product_name),
        ("{view_description}", view_desc),
        ("{view_type_note}", view_type_note),
        ("{assembly_description}", assembly_desc),
        ("{material_descriptions}", material_desc),
        ("{section_face_treatment}", section_face),
        ("{standard_parts_description}", std_parts_desc),
        ("{negative_constraints}", neg_text),
        ("{consistency_rules}", consistency_rules),
        ("{environment}", environment),
    ]:
        prompt = prompt.replace(key, val)

    # Clean up triple blank lines
    while "\n\n\n" in prompt:
        prompt = prompt.replace("\n\n\n", "\n\n")

    return prompt.strip()


def _try_auto_enrich(rc, cad_dir=None):
    """Auto-enrich rc with generated prompt data from params.py if available.

    Looks for params.py in cad_dir (or guesses from SKILL_ROOT/cad/<subsystem>).
    Returns enriched rc (modified in-place).
    """
    try:
        from prompt_data_builder import generate_prompt_data, merge_into_config
    except ImportError:
        return rc

    # Determine cad_dir
    if cad_dir is None:
        # Try to guess from rc subsystem info
        sub = rc.get("subsystem", {}).get("name", "")
        if sub:
            cad_dir = os.path.join(SKILL_ROOT, "cad", sub)
        else:
            return rc

    params_path = os.path.join(cad_dir, "params.py")
    if not os.path.isfile(params_path):
        return rc

    try:
        generated = generate_prompt_data(cad_dir, rc)
        merge_into_config(rc, generated)
    except Exception as e:
        import warnings
        warnings.warn(f"prompt_data_builder auto-enrich failed: {e}", stacklevel=2)

    return rc


def build_enhance_prompt(view_key, rc, is_v1_done=False, cad_dir=None, auto_enrich=True):
    """Load unified template + fill placeholders in one call.

    Args:
        view_key: "V1"..."V6" (or any new view)
        rc: parsed render_config.json dict
        is_v1_done: unused (kept for API compatibility); consistency always enabled
        cad_dir: path to cad/<subsystem>/ for auto-generation (optional)
        auto_enrich: if True, auto-generate prompt data from params.py (default True)
    Returns:
        filled prompt string
    """
    if auto_enrich:
        rc = _try_auto_enrich(rc, cad_dir)
    tmpl = load_template()
    return fill_prompt_template(tmpl, view_key, rc, is_v1_done)


def extract_view_key(png_path, rc=None):
    """Extract view key from a PNG filename.

    If rc is provided, matches against known camera keys first (e.g. 'V1', 'FRONT', 'ISO').
    Falls back to generic V+digits pattern, then the bare stem.
    """
    import warnings
    basename = os.path.basename(png_path)
    stem = os.path.splitext(basename)[0]

    # Match against config-defined view keys (longest first to avoid prefix collisions)
    if rc:
        known = sorted(rc.get("camera", {}).keys(), key=len, reverse=True)
        stem_up = stem.upper()
        for k in known:
            if k.upper() in stem_up:
                return k

    # Generic V+digits fallback
    m = re.search(r"(V\d+)", basename, re.IGNORECASE)
    if m:
        return m.group(1).upper()

    warnings.warn(
        f"No view key found in filename '{png_path}'; defaulting to stem '{stem}'",
        stacklevel=2,
    )
    return stem


def view_sort_key(path, rc=None):
    """Sort key: config-defined order first, then numeric V\d+, then alphabetic."""
    basename = os.path.basename(path)
    stem = os.path.splitext(basename)[0]

    if rc:
        order = list(rc.get("camera", {}).keys())
        stem_up = stem.upper()
        for i, k in enumerate(order):
            if k.upper() in stem_up:
                return (0, i, stem)

    m = re.search(r"V(\d+)", basename.upper())
    if m:
        return (1, int(m.group(1)), stem)
    return (2, 0, stem)


def build_labeled_prompt(view_key, rc, **kwargs):
    """Build enhance prompt WITH English label instructions appended.

    The base enhance prompt is generated normally, then:
    1. The "Do NOT add text, labels" constraint is relaxed to allow labels
    2. A COMPONENT LABELS section is appended listing visible components

    If no labels are configured for this view, returns the base prompt unchanged.
    """
    base = build_enhance_prompt(view_key, rc, **kwargs)

    labels_cfg = rc.get("labels", {}).get(view_key, [])
    components = rc.get("components", {})
    if not labels_cfg:
        return base

    # Relax the no-labels constraint (allow component labels only)
    _NO_LABEL_LINE = "- Do NOT add text, labels, dimensions, or annotations."
    result = base.replace(_NO_LABEL_LINE,
                          "- Do NOT add dimensions or measurement annotations.")
    if _NO_LABEL_LINE in result:
        import warnings
        warnings.warn("build_labeled_prompt: failed to relax no-labels constraint — "
                      "template may have changed", stacklevel=2)

    # Build label instructions
    lines = [
        "",
        "COMPONENT LABELS:",
        "Add clean engineering-style labels to the enhanced image:",
        "- Thin dark gray leader lines from each component to its label text",
        "- Small red anchor dot on each component's visible surface",
        "- English text in clean sans-serif font (e.g. Arial, Helvetica)",
        "- Place labels outside the assembly body, avoid overlapping",
        "- Keep ALL geometry and materials EXACTLY as enhanced above",
        "",
        "Components to label (use EXACTLY these English names):",
    ]
    for lbl in labels_cfg:
        comp_id = lbl.get("component", "")
        comp = components.get(comp_id, {})
        name_en = comp.get("name_en", comp_id)
        lines.append(f"  - {name_en}")

    return result + "\n".join(lines) + "\n"
