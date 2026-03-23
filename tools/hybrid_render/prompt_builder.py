#!/usr/bin/env python3
"""
Prompt Builder — Generate Gemini enhancement prompts from render_config.json

Reads material descriptions and product name from the config's prompt_vars
section, fills them into built-in prompt templates, and prints to stdout.

Usage:
    python tools/hybrid_render/prompt_builder.py --config cad/end_effector/render_config.json
    python tools/hybrid_render/prompt_builder.py --config render_config.json --type exploded
    python tools/hybrid_render/prompt_builder.py --config render_config.json --type ortho
    python tools/hybrid_render/prompt_builder.py --config render_config.json --list

Output goes to stdout. Redirect to a file or pipe to gemini_gen.py:
    python prompt_builder.py --config rc.json > prompt.txt
    python gemini_gen.py "$(cat prompt.txt)" --image base.png

No Blender or GPU needed. Requires only Python stdlib + render_config.py.
"""

import os
import sys

# ═════════════════════════════════════════════════════════════════════════════
# Prompt templates — {{PRODUCT_NAME}} and {{MATERIAL_LINES}} are replaced
# ═════════════════════════════════════════════════════════════════════════════

TEMPLATES = {
    "enhance": """\
Enhance this CAD rendering into a photorealistic product visualization of a {{PRODUCT_NAME}}.
Keep ALL geometry, proportions, and spatial positions EXACTLY as shown
— do NOT move, resize, or add any parts.

MATERIAL ENHANCEMENT (apply to existing parts only):
{{MATERIAL_LINES}}

LIGHTING: Professional product photography, key light upper-left, soft fill right,
rim light for edge highlights. Environment reflections on all metal surfaces.
Neutral gray gradient studio background. 4K quality. No text, no labels.""",

    "exploded": """\
Enhance this CAD exploded view into a photorealistic product visualization of a {{PRODUCT_NAME}}.
Keep ALL geometry, positions, and explosion offsets EXACTLY as shown
— do NOT move, resize, reassemble, or add any parts.

MATERIAL ENHANCEMENT (apply to existing parts only):
{{MATERIAL_LINES}}

EXPLODED VIEW ENHANCEMENT:
- Add thin semi-transparent assembly guide lines (white dashed lines)
  connecting each separated module back to its mounting position
- Dark studio background with subtle gradient (darker top, lighter bottom)
- Soft shadow beneath each floating component

LIGHTING: Dramatic product photography with strong rim lights creating bright
edges on every separated part. Environment reflections. 4K. No text.""",

    "ortho": """\
Transform this orthographic CAD rendering into a professional engineering
visualization of a {{PRODUCT_NAME}}.
Keep ALL geometry and proportions EXACTLY as shown.

MATERIAL ENHANCEMENT:
{{MATERIAL_LINES}}

STYLE: Clean engineering product shot, white studio background, even shadowless
lighting from all sides (like a datasheet photo). Sharp edges, no depth of
field blur. Crisp metallic reflections. 4K. No text, no dimensions.""",
}


def build_material_lines(config):
    """Build '- visual_cue: material_desc' lines from prompt_vars."""
    pv = config.get("prompt_vars", {})
    descs = pv.get("material_descriptions", [])
    if not descs:
        return "(No material descriptions configured in prompt_vars)"
    lines = []
    for d in descs:
        vc = d.get("visual_cue", "Unknown part")
        md = d.get("material_desc", "default material")
        lines.append(f"- {vc}: {md}")
    return "\n".join(lines)


def build_prompt(config, template_type="enhance"):
    """Generate a complete prompt string from config and template type."""
    if template_type not in TEMPLATES:
        raise ValueError(
            f"Unknown template type '{template_type}'. "
            f"Available: {', '.join(TEMPLATES.keys())}"
        )

    pv = config.get("prompt_vars", {})
    product_name = pv.get("product_name", "mechanical assembly")
    material_lines = build_material_lines(config)

    prompt = TEMPLATES[template_type]
    prompt = prompt.replace("{{PRODUCT_NAME}}", product_name)
    prompt = prompt.replace("{{MATERIAL_LINES}}", material_lines)
    return prompt


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate Gemini enhancement prompts from render_config.json"
    )
    parser.add_argument("--config", required=True,
                        help="Path to render_config.json")
    parser.add_argument("--type", default="enhance",
                        choices=list(TEMPLATES.keys()),
                        help="Prompt template type (default: enhance)")
    parser.add_argument("--list", action="store_true",
                        help="List available template types and exit")
    args = parser.parse_args()

    if args.list:
        print("Available prompt templates:")
        for name in TEMPLATES:
            first_line = TEMPLATES[name].split("\n")[0][:70]
            print(f"  {name:12s}  {first_line}...")
        return 0

    # Find render_config.py
    config_dir = os.path.dirname(os.path.abspath(args.config))
    search_paths = [
        config_dir,
        os.path.normpath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "..", "cad", "end_effector")),
    ]
    for p in search_paths:
        if p not in sys.path:
            sys.path.insert(0, p)

    try:
        import render_config as rcfg
    except ImportError:
        print("ERROR: Cannot import render_config.py", file=sys.stderr)
        print(f"  Searched: {search_paths}", file=sys.stderr)
        return 1

    if not os.path.isfile(args.config):
        print(f"ERROR: Config file not found: {args.config}", file=sys.stderr)
        return 1

    config = rcfg.load_config(args.config)

    # Check prompt_vars exist
    if not config.get("prompt_vars"):
        print("WARNING: No prompt_vars section in config. "
              "Output will use defaults.", file=sys.stderr)

    prompt = build_prompt(config, args.type)
    print(prompt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
