#!/usr/bin/env python3
"""
Prompt Builder — Generate Gemini enhancement prompts from render_config.json

Reads material descriptions and product name from the config's prompt_vars
section, fills them into prompt templates, and prints to stdout.

Usage:
    python tools/hybrid_render/prompt_builder.py --config cad/end_effector/render_config.json
    python tools/hybrid_render/prompt_builder.py --config render_config.json --view V4
    python tools/hybrid_render/prompt_builder.py --config render_config.json --view V5
    python tools/hybrid_render/prompt_builder.py --config render_config.json --list

Output goes to stdout. Redirect to a file or pipe to gemini_gen.py:
    python prompt_builder.py --config rc.json > prompt.txt
    python gemini_gen.py --prompt-file prompt.txt --image base.png

No Blender or GPU needed. Requires only Python stdlib.
"""

import json
import os
import sys

# Import shared prompt logic from skill root
sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..")))
from enhance_prompt import build_enhance_prompt, load_template


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate Gemini enhancement prompts from render_config.json"
    )
    parser.add_argument("--config", required=True,
                        help="Path to render_config.json")
    parser.add_argument("--view", default="V1",
                        help="View key (default: V1)")
    parser.add_argument("--list", action="store_true",
                        help="List unified template first line and exit")
    parser.add_argument("--v1-done", action="store_true",
                        help="(deprecated, has no effect — consistency is always enabled)")
    args = parser.parse_args()

    if args.list:
        print("Unified template:")
        try:
            tmpl = load_template()
            first_line = tmpl.split("\n")[0][:70]
        except FileNotFoundError:
            first_line = "(template not found)"
        print(f"  {first_line}...")
        return 0

    if not os.path.isfile(args.config):
        print(f"ERROR: Config file not found: {args.config}", file=sys.stderr)
        return 1

    with open(args.config, encoding="utf-8") as f:
        config = json.load(f)

    if not config.get("prompt_vars"):
        print("WARNING: No prompt_vars section in config. "
              "Output will use defaults.", file=sys.stderr)

    prompt = build_enhance_prompt(args.view, config, is_v1_done=args.v1_done)
    print(prompt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
