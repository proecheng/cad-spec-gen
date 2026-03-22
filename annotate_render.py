#!/usr/bin/env python3
"""
annotate_render.py — Add component labels to enhanced 3D renders.

Draws leader lines + text labels on rendered images using PIL.
Supports Chinese (SimHei) and English (Arial) labels.

Usage:
    python annotate_render.py V1_enhanced.jpg --config render_config.json --lang cn
    python annotate_render.py V1_enhanced.jpg --config render_config.json --lang en
    python annotate_render.py --all --dir ./renders --config render_config.json --lang cn

Dependencies: Pillow
"""

import argparse
import glob
import json
import os
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ── Font discovery (same strategy as render_dxf.py) ──────────────────────────

_CJK_CANDIDATES = ["SimHei", "Microsoft YaHei", "FangSong", "SimSun"]
_EN_CANDIDATES = ["Arial", "Helvetica", "DejaVu Sans", "Calibri"]

def _find_font(candidates, fallback="arial.ttf"):
    """Find first available TrueType font from candidates list."""
    import matplotlib.font_manager as fm
    for name in candidates:
        matches = [f.fname for f in fm.fontManager.ttflist if f.name == name]
        if matches:
            return matches[0]
    # Fallback: try system default
    try:
        return fm.findfont(fm.FontProperties(family="sans-serif"))
    except Exception:
        return fallback

_CJK_FONT_PATH = None
_EN_FONT_PATH = None

def _ensure_fonts():
    global _CJK_FONT_PATH, _EN_FONT_PATH
    if _CJK_FONT_PATH is None:
        _CJK_FONT_PATH = _find_font(_CJK_CANDIDATES)
    if _EN_FONT_PATH is None:
        _EN_FONT_PATH = _find_font(_EN_CANDIDATES)


# ── Label rendering ──────────────────────────────────────────────────────────

# Default reference resolution (Blender output); overridden by config
_DEFAULT_REF_W, _DEFAULT_REF_H = 1920, 1080


def detect_view_id(filename: str, valid_views: list = None) -> str:
    """Extract view ID from filename.

    If valid_views is provided (e.g. from config labels keys),
    match against those first (longest-first to avoid V1 matching V10).
    Falls back to generic V + digits pattern.
    """
    basename_upper = os.path.basename(filename).upper()
    if valid_views:
        for vid in sorted(valid_views, key=len, reverse=True):
            if vid.upper() in basename_upper:
                return vid.upper()
        return None
    # Generic fallback: any V + digits
    m = re.search(r"(V\d+)", filename, re.IGNORECASE)
    return m.group(1).upper() if m else None


def annotate_image(img_path: str, config: dict, lang: str = "cn",
                   font_size: int = 20, style: str = "clean") -> str:
    """
    Annotate a single image with component labels.
    Returns path to the annotated image.
    """
    _ensure_fonts()

    # Determine valid view IDs from config
    labels_all = config.get("labels", {})
    valid_views = [k for k in labels_all if not k.startswith("_")]

    view_id = detect_view_id(os.path.basename(img_path), valid_views)
    if not view_id:
        print(f"  SKIP: cannot detect view ID from {img_path}")
        return None

    labels = labels_all.get(view_id, [])
    if not labels:
        print(f"  SKIP: no labels defined for {view_id}")
        return None

    # Component name lookup dict (names sourced from design doc BOM)
    components = config.get("components", {})

    # Open image
    img = Image.open(img_path).convert("RGBA")
    w, h = img.size

    # Reference resolution (config-driven, defaults to 1920x1080)
    ref_res = config.get("reference_resolution", {})
    ref_w = ref_res.get("width", _DEFAULT_REF_W)
    ref_h = ref_res.get("height", _DEFAULT_REF_H)

    # Scale factor from reference resolution
    sx = w / ref_w
    sy = h / ref_h
    scaled_font_size = max(16, int(font_size * min(sx, sy)))

    # Load font
    font_path = _CJK_FONT_PATH if lang == "cn" else _EN_FONT_PATH
    try:
        font = ImageFont.truetype(font_path, scaled_font_size)
    except Exception:
        font = ImageFont.load_default()

    # Create overlay for semi-transparent elements
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Style colors
    if style == "clean":
        # Clean engineering style: black text, no background, thin gray lines
        line_color = (80, 80, 80, 180)
        bg_color = None  # no background
        text_color = (30, 30, 30, 255)
        dot_color = (200, 50, 50, 230)
    elif style == "dark":
        line_color = (255, 255, 255, 220)
        bg_color = (0, 0, 0, 180)
        text_color = (255, 255, 255, 255)
        dot_color = (255, 80, 80, 255)
    else:  # light
        line_color = (40, 40, 40, 220)
        bg_color = (255, 255, 255, 200)
        text_color = (20, 20, 20, 255)
        dot_color = (220, 60, 60, 255)

    line_width = max(1, int(1.5 * min(sx, sy)))
    dot_r = max(3, int(3.5 * min(sx, sy)))
    pad_x = max(6, int(8 * min(sx, sy)))
    pad_y = max(3, int(4 * min(sx, sy)))

    for lbl in labels:
        # Resolve name: component-id reference (preferred) or inline name (legacy)
        comp_id = lbl.get("component")
        if comp_id and components:
            comp = components.get(comp_id, {})
            name = comp.get(f"name_{lang}", comp.get("name_en", comp_id))
        else:
            name = lbl.get(f"name_{lang}", lbl.get("name_en", "?"))
        ax, ay = int(lbl["anchor"][0] * sx), int(lbl["anchor"][1] * sy)
        lx, ly = int(lbl["label"][0] * sx), int(lbl["label"][1] * sy)

        # Leader line
        draw.line([(ax, ay), (lx, ly)], fill=line_color, width=line_width)

        # Anchor dot
        draw.ellipse(
            [(ax - dot_r, ay - dot_r), (ax + dot_r, ay + dot_r)],
            fill=dot_color
        )

        # Text bounding box
        bbox = font.getbbox(name)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

        # Background rectangle (skip in clean mode)
        if bg_color:
            rx0 = lx - pad_x
            ry0 = ly - th // 2 - pad_y
            rx1 = lx + tw + pad_x
            ry1 = ly + th // 2 + pad_y
            draw.rounded_rectangle([rx0, ry0, rx1, ry1], radius=4, fill=bg_color)

        # Text
        draw.text((lx, ly - th // 2), name, fill=text_color, font=font)

    # Composite
    result = Image.alpha_composite(img, overlay).convert("RGB")

    # Output path
    base, ext = os.path.splitext(img_path)
    # Remove existing _labeled suffix if re-running
    base = re.sub(r"_labeled_(cn|en)$", "", base)
    out_path = f"{base}_labeled_{lang}.jpg"
    result.save(out_path, "JPEG", quality=95)

    size_kb = os.path.getsize(out_path) / 1024
    print(f"  OK: {os.path.basename(out_path)} ({size_kb:.0f} KB, {len(labels)} labels)")
    return out_path


def main():
    parser = argparse.ArgumentParser(
        description="Add component labels to enhanced 3D renders"
    )
    parser.add_argument("input", nargs="?", help="Input image path")
    parser.add_argument("--config", required=True, help="render_config.json path")
    parser.add_argument("--lang", default="cn", choices=["cn", "en"],
                        help="Label language (default: cn)")
    parser.add_argument("--all", action="store_true",
                        help="Annotate all V*_enhanced.jpg in --dir")
    parser.add_argument("--dir", default=".", help="Directory for --all mode")
    parser.add_argument("--font-size", type=int, default=20,
                        help="Base font size at 1080p (default: 20)")
    parser.add_argument("--style", default="clean", choices=["clean", "dark", "light"],
                        help="Label style (default: clean)")
    args = parser.parse_args()

    # Load config
    with open(args.config, encoding="utf-8") as f:
        config = json.load(f)

    if not config.get("labels"):
        print("ERROR: No 'labels' section in config file.")
        sys.exit(1)

    if args.all:
        # Discover files by scanning all JPGs and matching against config view IDs
        labels_cfg = config.get("labels", {})
        valid_views = [k for k in labels_cfg if not k.startswith("_")]
        all_jpgs = sorted(glob.glob(os.path.join(args.dir, "*.jpg")))
        # Exclude already-labeled files, then filter to those matching a valid view
        files = [f for f in all_jpgs
                 if "_labeled_" not in f
                 and detect_view_id(os.path.basename(f), valid_views)]
        if not files:
            print(f"No annotatable images found in {args.dir} "
                  f"(expected views: {', '.join(valid_views)})")
            sys.exit(1)
        print(f"Annotating {len(files)} images ({args.lang})...")
        results = []
        for f in files:
            r = annotate_image(f, config, args.lang, args.font_size, args.style)
            if r:
                results.append(r)
        print(f"\n{len(results)}/{len(files)} annotated.")
    elif args.input:
        annotate_image(args.input, config, args.lang, args.font_size, args.style)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
