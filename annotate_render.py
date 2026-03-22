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

# Reference resolution (Blender output)
REF_W, REF_H = 1920, 1080


def detect_view_id(filename: str) -> str:
    """Extract view ID (V1-V5) from filename."""
    m = re.search(r"(V[1-5])", filename, re.IGNORECASE)
    return m.group(1).upper() if m else None


def annotate_image(img_path: str, config: dict, lang: str = "cn",
                   font_size: int = 32, style: str = "dark") -> str:
    """
    Annotate a single image with component labels.
    Returns path to the annotated image.
    """
    _ensure_fonts()

    view_id = detect_view_id(os.path.basename(img_path))
    if not view_id:
        print(f"  SKIP: cannot detect view ID from {img_path}")
        return None

    labels_all = config.get("labels", {})
    labels = labels_all.get(view_id, [])
    if not labels:
        print(f"  SKIP: no labels defined for {view_id}")
        return None

    # Open image
    img = Image.open(img_path).convert("RGBA")
    w, h = img.size

    # Scale factor from reference resolution
    sx = w / REF_W
    sy = h / REF_H
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
    if style == "dark":
        line_color = (255, 255, 255, 220)
        bg_color = (0, 0, 0, 180)
        text_color = (255, 255, 255, 255)
        dot_color = (255, 80, 80, 255)
    else:
        line_color = (40, 40, 40, 220)
        bg_color = (255, 255, 255, 200)
        text_color = (20, 20, 20, 255)
        dot_color = (220, 60, 60, 255)

    line_width = max(2, int(2 * min(sx, sy)))
    dot_r = max(4, int(5 * min(sx, sy)))
    pad_x = max(6, int(8 * min(sx, sy)))
    pad_y = max(3, int(4 * min(sx, sy)))

    for lbl in labels:
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

        # Background rectangle
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
    parser.add_argument("--font-size", type=int, default=32,
                        help="Base font size at 1080p (default: 32)")
    parser.add_argument("--style", default="dark", choices=["dark", "light"],
                        help="Label style (default: dark)")
    args = parser.parse_args()

    # Load config
    with open(args.config, encoding="utf-8") as f:
        config = json.load(f)

    if not config.get("labels"):
        print("ERROR: No 'labels' section in config file.")
        sys.exit(1)

    if args.all:
        pattern = os.path.join(args.dir, "V*_*enhanced*.jpg")
        files = sorted(glob.glob(pattern))
        # Exclude already-labeled files
        files = [f for f in files if "_labeled_" not in f]
        if not files:
            print(f"No V*_enhanced.jpg files found in {args.dir}")
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
