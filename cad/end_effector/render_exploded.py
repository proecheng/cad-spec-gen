"""
Blender Exploded View Renderer — End Effector

Creates an exploded view by displacing station modules along their radial
mounting directions, then renders with the same pipeline as render_3d.py.

Usage:
    blender.exe -b -P cad/end_effector/render_exploded.py
    blender.exe -b -P cad/end_effector/render_exploded.py -- --spread 80

Input:  cad/output/EE-000_assembly.glb
Output: cad/output/renders/V4_exploded.png
"""

import bpy
import logging
import math
import os
import sys
from mathutils import Vector

log = logging.getLogger("render_exploded")

# ── Parse CLI args ───────────────────────────────────────────────────────────
argv = sys.argv
if "--" in argv:
    argv = argv[argv.index("--") + 1:]
else:
    argv = []

import argparse

parser = argparse.ArgumentParser(description="Render exploded view")
parser.add_argument("--glb", default=None, help="Path to GLB")
parser.add_argument("--config", default=None,
                    help="Path to render_config.json (optional, fallback: hardcoded)")
parser.add_argument("--spread", type=float, default=None,
                    help="Radial displacement for stations (mm, default: 70 or from config)")
parser.add_argument("--z-spread", type=float, default=None,
                    help="Z displacement for drive/peek (mm, default: 50 or from config)")
parser.add_argument("--samples", type=int, default=512)
parser.add_argument("--resolution", type=int, nargs=2, default=[1920, 1080])
parser.add_argument("--output-dir", default=None)
parser.add_argument("--gpu", action="store_true", default=None,
                    help="Force GPU rendering (auto-detected if omitted)")
parser.add_argument("--cpu", action="store_true", default=False,
                    help="Force CPU rendering even if GPU available")
args = parser.parse_args(argv)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CAD_OUTPUT = os.environ.get("CAD_OUTPUT_DIR", os.path.join(SCRIPT_DIR, "..", "output"))
GLB_PATH = args.glb or os.path.join(CAD_OUTPUT, "EE-000_assembly.glb")
RENDER_DIR = args.output_dir or os.path.join(CAD_OUTPUT, "renders")
os.makedirs(RENDER_DIR, exist_ok=True)

# ── Config loading ───────────────────────────────────────────────────────────
_CONFIG = None
_EXPLODE_CFG = None

if args.config:
    sys.path.insert(0, SCRIPT_DIR)
    import render_config as rcfg
    _CONFIG = rcfg.load_config(args.config)
    _EXPLODE_CFG = _CONFIG.get("explode", {})
    # Override GLB path from config if not explicitly set
    if not args.glb and _CONFIG.get("_resolved", {}).get("glb_path"):
        GLB_PATH = _CONFIG["_resolved"]["glb_path"]
    log.info("Config loaded: %s", args.config)

# Resolve spread values: CLI > config > hardcoded default
_spread = args.spread
if _spread is None:
    _spread = (_EXPLODE_CFG or {}).get("spread_mm", 70.0)
_z_spread = args.z_spread
if _z_spread is None:
    _z_spread = (_EXPLODE_CFG or {}).get("z_spread_mm", 50.0)

# Station angles from config or hardcoded
STATION_ANGLES = (_EXPLODE_CFG or {}).get(
    "station_angles_deg", [0.0, 90.0, 180.0, 270.0])
MOUNT_CENTER_R = (_EXPLODE_CFG or {}).get("mount_radius_mm", 65.0)

# Explosion rules from config or hardcoded default
EXPLODE_RULES = (_EXPLODE_CFG or {}).get("rules", {
    "station1": {"angle_deg": 0.0, "radial": True},
    "station2": {"angle_deg": 90.0, "radial": True},
    "station3": {"angle_deg": 180.0, "radial": True},
    "station4": {"angle_deg": 270.0, "radial": True},
    "applicator": {"angle_deg": 0.0, "radial": True},
    "ae": {"angle_deg": 90.0, "radial": True},
    "cleaner": {"angle_deg": 180.0, "radial": True},
    "uhf": {"angle_deg": 270.0, "radial": True},
    "drive": {"z_offset": -1},
    "motor": {"z_offset": -1},
    "peek": {"z_offset": 1},
})


def explode_objects(spread, z_spread):
    """Displace objects according to explosion rules."""
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        name_lower = obj.name.lower()

        for pattern, rule in EXPLODE_RULES.items():
            if pattern not in name_lower:
                continue

            if rule.get("radial"):
                angle = math.radians(rule["angle_deg"])
                dx = spread * math.cos(angle)
                dy = spread * math.sin(angle)
                obj.location.x += dx
                obj.location.y += dy
                log.debug("  Explode radial: %s += (%.1f, %.1f, 0)", obj.name, dx, dy)
            elif "z_offset" in rule:
                dz = z_spread * rule["z_offset"]
                if "peek" in name_lower:
                    dz = z_spread * 0.4  # smaller displacement for PEEK
                obj.location.z += dz
                log.debug("  Explode Z: %s += (0, 0, %.1f)", obj.name, dz)
            break


def main():
    # Reuse render_3d functions — import from same directory
    # Since this runs inside Blender, we add the script dir to path
    sys.path.insert(0, SCRIPT_DIR)
    import render_3d

    log.info("=" * 60)
    log.info("  End Effector — Exploded View Renderer")
    log.info("=" * 60)

    # 1. Clear and import
    render_3d.clear_scene()
    render_3d.import_glb(GLB_PATH)

    # 2. Explode
    log.info("Exploding assembly (radial=%.0fmm, z=%.0fmm)...", _spread, _z_spread)
    explode_objects(_spread, _z_spread)

    # 3. Materials, lighting, render settings
    # If config loaded, inject it into render_3d module globals
    if _CONFIG:
        import render_config as rcfg
        render_3d._CONFIG = _CONFIG
        render_3d._CONFIG_MATERIALS = rcfg.resolve_all_materials(_CONFIG)
        render_3d._CONFIG_CAMERAS = _CONFIG.get("camera", {})
        render_3d._BOUNDING_R = _CONFIG["subsystem"].get(
            "bounding_radius_mm", 300.0)

    log.info("Assigning PBR materials...")
    render_3d.assign_materials()

    log.info("Setting up studio lighting...")
    render_3d.setup_lighting()

    render_3d.setup_render(args.samples, args.resolution[0], args.resolution[1],
                           force_gpu=args.gpu, force_cpu=args.cpu)

    # 4. Render V4 preset
    output_path = os.path.join(RENDER_DIR, "V4_exploded.png")

    # Remove any existing camera
    for obj in bpy.context.scene.objects:
        if obj.type == "CAMERA":
            bpy.data.objects.remove(obj, do_unlink=True)

    render_3d.setup_camera("V4")
    bpy.context.scene.render.filepath = output_path

    log.info("Rendering V4 exploded view...")
    log.info("  Output: %s", output_path)
    bpy.ops.render.render(write_still=True)

    size_kb = os.path.getsize(output_path) / 1024
    log.info("=" * 60)
    log.info("  Rendered: V4_exploded.png (%.1f KB)", size_kb)
    log.info("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG if "--verbose" in sys.argv else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    main()
