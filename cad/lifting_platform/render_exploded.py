"""
Blender Exploded View Renderer — Lifting Platform

Creates an exploded view by displacing each component group along its natural
separation axis (Z for plates/motor, radial XY for vertical rods), then renders
with the same Cycles pipeline as render_3d.py.

Usage:
    blender.exe -b -P cad/lifting_platform/render_exploded.py -- --config cad/lifting_platform/render_config.json
    blender.exe -b -P cad/lifting_platform/render_exploded.py -- --config cad/lifting_platform/render_config.json --spread 80

Input:  cad/output/SLP-000_assembly.glb
Output: cad/output/renders/V5_exploded.png
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
                    help="Path to render_config.json")
parser.add_argument("--spread", type=float, default=None,
                    help="Radial/Z spread distance in mm (default: 70 or from config)")
parser.add_argument("--samples", type=int, default=512)
parser.add_argument("--resolution", type=int, nargs=2, default=[1920, 1080])
parser.add_argument("--output-dir", default=None)
parser.add_argument("--timestamp", action="store_true",
                    help="Append YYYYMMDD_HHMM to output filename")
parser.add_argument("--gpu", action="store_true", default=None,
                    help="Force GPU rendering")
parser.add_argument("--cpu", action="store_true", default=False,
                    help="Force CPU rendering")
args = parser.parse_args(argv)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CAD_OUTPUT = os.environ.get("CAD_OUTPUT_DIR", os.path.join(SCRIPT_DIR, "..", "output"))
GLB_PATH = args.glb or os.path.join(CAD_OUTPUT, "SLP-000_assembly.glb")
RENDER_DIR = args.output_dir or os.path.join(CAD_OUTPUT, "renders")
os.makedirs(RENDER_DIR, exist_ok=True)

_CONFIG = None
_EXPLODE_CFG = None

if args.config:
    sys.path.insert(0, SCRIPT_DIR)
    import render_config as rcfg
    _CONFIG = rcfg.load_config(args.config)
    _EXPLODE_CFG = _CONFIG.get("explode", {})
    if not args.glb and _CONFIG.get("_resolved", {}).get("glb_path"):
        GLB_PATH = _CONFIG["_resolved"]["glb_path"]
    log.info("Config loaded: %s", args.config)

# Resolve spread: CLI > config > default
_spread = args.spread
if _spread is None:
    _spread = (_EXPLODE_CFG or {}).get("spread_mm", 70.0)

# ── Explosion rules (prefix → displacement) ──────────────────────────────────
# z_factor:  displacement along Z = z_factor * _spread  (+ = up, - = down)
# xy_deg:    displacement along XY at this angle, magnitude = _spread
EXPLODE_RULES_DEFAULT = {
    "SLP-100": {"z":  1.00},         # top plate → up
    "SLP-200": {"xy_deg": 180.0},    # left bar  → left (−X)
    "SLP-201": {"xy_deg":   0.0},    # right bar → right (+X)
    "SLP-300": {"z":  0.50},         # moving plate → slightly up
    "SLP-400": {"z": -1.00},         # motor bracket → down
    "SLP-P01_LS1": {"xy_deg":  27.0}, # lead screw 1 → diagonal corner
    "SLP-P01_LS2": {"xy_deg": 207.0}, # lead screw 2 → opposite corner
    "SLP-P02_GS1": {"xy_deg": 333.0}, # guide shaft 1 → other diagonal
    "SLP-P02_GS2": {"xy_deg": 153.0}, # guide shaft 2 → other diagonal
    "T16":    {"z":  0.50},           # bronze nut → up with moving plate
    "LM10UU": {"z":  0.50},           # linear bearing → up with moving plate
    "KFL001": {"z":  0.25},           # bearing block → slight separation
    "NEMA23": {"z": -1.50},           # motor → down
    "L070":   {"z": -0.80},           # coupler → down
    "GT2":    {"z": -1.30},           # pulley → down
}


def _match_rule(obj_name, rules):
    """Return the first rule whose key is a prefix of obj_name (case-insensitive)."""
    name_up = obj_name.upper()
    # Longest prefix wins to avoid SLP-P01 matching before SLP-P01_LS1
    best_key = None
    best_len = 0
    for key in rules:
        if name_up.startswith(key.upper()) and len(key) > best_len:
            best_key = key
            best_len = len(key)
    return rules.get(best_key) if best_key else None


def explode_objects(spread):
    """Displace mesh objects according to EXPLODE_RULES."""
    rules = (_EXPLODE_CFG or {}).get("rules", None) or EXPLODE_RULES_DEFAULT

    moved = 0
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        rule = _match_rule(obj.name, rules)
        if rule is None:
            log.debug("  No rule for: %s", obj.name)
            continue

        if "xy_deg" in rule:
            angle = math.radians(rule["xy_deg"])
            dx = math.cos(angle) * spread
            dy = math.sin(angle) * spread
            obj.location.x += dx
            obj.location.y += dy
            log.debug("  Explode XY: %s → (%.1f, %.1f)", obj.name, dx, dy)
        elif "z" in rule:
            dz = rule["z"] * spread
            obj.location.z += dz
            log.debug("  Explode Z:  %s → %.1f", obj.name, dz)
        moved += 1

    log.info("  Exploded %d objects (spread=%.0fmm)", moved, spread)


def main():
    sys.path.insert(0, SCRIPT_DIR)
    import render_3d

    log.info("=" * 60)
    log.info("  Lifting Platform — Exploded View Renderer")
    log.info("=" * 60)

    # 1. Clear and import
    render_3d.clear_scene()
    render_3d.import_glb(GLB_PATH)

    # 2. Explode
    log.info("Exploding assembly (spread=%.0fmm)...", _spread)
    explode_objects(_spread)

    # 3. Inject config into render_3d globals
    if _CONFIG:
        import render_config as rcfg
        render_3d._CONFIG = _CONFIG
        render_3d._CONFIG_MATERIALS = rcfg.resolve_all_materials(_CONFIG)
        render_3d._CONFIG_CAMERAS = _CONFIG.get("camera", {})
        render_3d._BOUNDING_R = _CONFIG["subsystem"].get("bounding_radius_mm", 250.0)

    # 4. Materials, scene setup, GPU
    log.info("Assigning PBR materials...")
    render_3d.assign_materials()

    log.info("Setting up scene...")
    res = _CONFIG.get("resolution", {}) if _CONFIG else {}
    width = res.get("width", 1920)
    height = res.get("height", 1080)
    render_3d.setup_render(args.samples, width, height,
                           force_gpu=args.gpu, force_cpu=args.cpu)

    # 5. Camera
    preset_key = (_EXPLODE_CFG or {}).get("camera_preset", "V5")
    cam_cfg = render_3d._CONFIG_CAMERAS.get(preset_key, {}) if render_3d._CONFIG_CAMERAS else {}

    view_name = cam_cfg.get("name", "V5_exploded")

    # 6. Build output path
    if args.timestamp:
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        output_path = os.path.join(RENDER_DIR, f"{view_name}_{ts}.png")
    else:
        output_path = os.path.join(RENDER_DIR, f"{view_name}.png")

    for obj in bpy.context.scene.objects:
        if obj.type == "CAMERA":
            bpy.data.objects.remove(obj, do_unlink=True)

    render_3d.setup_camera(preset_key)
    bpy.context.scene.render.filepath = output_path
    bpy.ops.render.render(write_still=True)
    log.info("Saved: %s", output_path)

    # Always write latest copy without timestamp
    latest_path = os.path.join(RENDER_DIR, f"{view_name}.png")
    if output_path != latest_path:
        import shutil
        shutil.copy2(output_path, latest_path)
        log.info("Latest copy: %s", latest_path)

    size_kb = os.path.getsize(output_path) / 1024
    log.info("=" * 60)
    log.info("  Rendered: %s (%.1f KB)", os.path.basename(output_path), size_kb)
    log.info("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG if "--verbose" in sys.argv else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    main()
