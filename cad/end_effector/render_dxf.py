"""
DXF → PNG Renderer — uses ezdxf matplotlib backend with Chinese font.

Usage:
    python cad/end_effector/render_dxf.py              # render all DXF
    python cad/end_effector/render_dxf.py FILE.dxf     # render one file
"""

import glob
import os
import sys

import ezdxf
import matplotlib
matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.font_manager import FontProperties

from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
from ezdxf.addons.drawing.config import (
    Configuration, ColorPolicy, BackgroundPolicy, HatchPolicy,
)

# ── Chinese font config ──────────────────────────────────────────────────────
_CJK_CANDIDATES = ["SimHei", "SimSun", "Microsoft YaHei", "FangSong"]
_CJK_FONT = None
for name in _CJK_CANDIDATES:
    matches = [f for f in fm.fontManager.ttflist if f.name == name]
    if matches:
        _CJK_FONT = name
        break

if _CJK_FONT:
    plt.rcParams["font.sans-serif"] = [_CJK_FONT, "DejaVu Sans"]
    plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["axes.unicode_minus"] = False

# Dark background like AutoCAD model space — makes color-7 (white) text visible
BG_COLOR = "#000000"

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output")


def render_dxf_to_png(dxf_path: str, png_path: str = None,
                       dpi: int = 200) -> str:
    """Render a DXF file to PNG image with dark background + Chinese text."""
    if png_path is None:
        png_path = os.path.splitext(dxf_path)[0] + ".png"

    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    # Override all text styles to use CJK TTF font
    if _CJK_FONT:
        for style in doc.styles:
            style.dxf.font = ""
            style.set_extended_font_data(_CJK_FONT)

    fig = plt.figure(dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(BG_COLOR)

    ctx = RenderContext(doc)
    config = Configuration(
        background_policy=BackgroundPolicy.CUSTOM,
        custom_bg_color=BG_COLOR,
        color_policy=ColorPolicy.COLOR,
        hatch_policy=HatchPolicy.NORMAL,
        lineweight_scaling=1.5,
    )
    out = MatplotlibBackend(ax)

    Frontend(ctx, out, config=config).draw_layout(msp)

    ax.set_aspect("equal")
    ax.autoscale(True)
    ax.set_axis_off()

    fig.savefig(png_path, dpi=dpi, bbox_inches="tight",
                facecolor=BG_COLOR, pad_inches=0.3)
    plt.close(fig)

    size_kb = os.path.getsize(png_path) / 1024
    print(f"  Rendered: {os.path.basename(png_path)} ({size_kb:.0f} KB)")
    return png_path


def render_all(output_dir: str = None) -> list:
    """Render all DXF files in output_dir to PNG."""
    if output_dir is None:
        output_dir = OUTPUT_DIR

    dxf_files = sorted(glob.glob(os.path.join(output_dir, "*.dxf")))
    if not dxf_files:
        print(f"No DXF files found in {output_dir}")
        return []

    print(f"Rendering {len(dxf_files)} DXF files to PNG...")
    print(f"  Font: {_CJK_FONT}, Background: {BG_COLOR}")
    png_files = []
    for dxf in dxf_files:
        try:
            png = render_dxf_to_png(dxf)
            png_files.append(png)
        except Exception as e:
            print(f"  ERROR rendering {os.path.basename(dxf)}: {e}")

    print(f"\n{len(png_files)}/{len(dxf_files)} PNG files generated.")
    return png_files


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for f in sys.argv[1:]:
            render_dxf_to_png(f)
    else:
        render_all()
