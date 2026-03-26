"""
Blender Cross-Section Renderer — End Effector

Reads all camera views with type:"section" from render_config.json,
applies the appropriate Boolean cut (quarter/half, YZ/XZ plane),
and renders each section view separately.

Usage:
    blender.exe -b -P cad/end_effector/render_section.py -- --config render_config.json
    blender.exe -b -P cad/end_effector/render_section.py -- --config render_config.json --view V7
"""

import bpy
import logging
import math
import os
import sys
from mathutils import Vector

log = logging.getLogger("render_section")

# ── Parse CLI args ───────────────────────────────────────────────────────────
argv = sys.argv
if "--" in argv:
    argv = argv[argv.index("--") + 1:]
else:
    argv = []

import argparse

parser = argparse.ArgumentParser(description="Render cross-section view(s)")
parser.add_argument("--glb", default=None, help="Path to GLB")
parser.add_argument("--config", default=None,
                    help="Path to render_config.json")
parser.add_argument("--view", default=None,
                    help="Render only this view ID (e.g. V6, V7). Default: all section views.")
parser.add_argument("--samples", type=int, default=512)
parser.add_argument("--resolution", type=int, nargs=2, default=[1920, 1080])
parser.add_argument("--output-dir", default=None)
parser.add_argument("--timestamp", action="store_true",
                    help="Append YYYYMMDD_HHMM to output filenames")
parser.add_argument("--gpu", action="store_true", default=None)
parser.add_argument("--cpu", action="store_true", default=False)
args = parser.parse_args(argv)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CAD_OUTPUT = os.environ.get("CAD_OUTPUT_DIR", os.path.join(SCRIPT_DIR, "..", "output"))
GLB_PATH = args.glb or os.path.join(CAD_OUTPUT, "EE-000_assembly.glb")
RENDER_DIR = args.output_dir or os.path.join(CAD_OUTPUT, "renders")
os.makedirs(RENDER_DIR, exist_ok=True)

# ── Config loading ───────────────────────────────────────────────────────────
_CONFIG = None

if args.config:
    sys.path.insert(0, SCRIPT_DIR)
    import render_config as rcfg
    _CONFIG = rcfg.load_config(args.config)
    if not args.glb and _CONFIG.get("_resolved", {}).get("glb_path"):
        GLB_PATH = _CONFIG["_resolved"]["glb_path"]
    log.info("Config loaded: %s", args.config)


def _get_section_views():
    """Return list of (view_id, cam_cfg, section_override) for all section-type views."""
    if not _CONFIG:
        # Fallback: single V6 with default camera
        return [("V6", {
            "name": "V6_cross_section",
            "location": [600, -550, 600],
            "target": [0, 0, 140],
            "lens_mm": 35,
        }, {})]

    cameras = _CONFIG.get("camera", {})
    global_section = _CONFIG.get("section", {})
    views = []
    for vid, cam in sorted(cameras.items()):
        if cam.get("type") != "section":
            continue
        if args.view and vid != args.view:
            continue
        # Per-view section override: camera can have a "section" sub-key
        per_view_section = cam.get("section", {})
        views.append((vid, cam, per_view_section))

    if not views and args.view:
        log.warning("View %s not found or not type:section. Available section views: %s",
                    args.view, [v for v, c in cameras.items() if c.get("type") == "section"])
    return views


def _make_section_material():
    """Create a light cross-hatch material for exposed cut faces."""
    mat = bpy.data.materials.new(name="SectionFace")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.85, 0.85, 0.82, 1.0)
    bsdf.inputs["Metallic"].default_value = 0.9
    bsdf.inputs["Roughness"].default_value = 0.35
    return mat


def create_cutter(cut_type="quarter", cut_plane="YZ", offset=0.0, size=2000.0):
    """Create a cutting box for Boolean DIFFERENCE.

    cut_type: "quarter" removes one quadrant, "half" removes one half.
    cut_plane: "YZ" cuts along YZ plane (removes X>0 quadrant),
               "XZ" cuts along XZ plane (removes Y<0 quadrant).
    """
    half = size / 2.0
    section_mat = _make_section_material()

    if cut_type == "quarter":
        # Remove one quadrant: X>0 AND Y<0 (default for YZ plane quarter cut)
        bpy.ops.mesh.primitive_cube_add(size=1)
        cube = bpy.context.active_object
        cube.name = "Cutter"
        cube.scale = (half, half, size)
        if cut_plane == "YZ":
            cube.location = (half + offset, -(half + abs(offset)), 0)
        elif cut_plane == "XZ":
            cube.location = (-(half + abs(offset)), -(half + abs(offset)), 0)
        else:
            cube.location = (half + offset, -(half + abs(offset)), 0)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        cube.data.materials.clear()
        cube.data.materials.append(section_mat)
        return cube

    elif cut_type == "half":
        # Remove one half along the specified plane
        bpy.ops.mesh.primitive_cube_add(size=1)
        cube = bpy.context.active_object
        cube.name = "Cutter"
        if cut_plane == "YZ":
            # Remove X > offset (front half)
            cube.scale = (half, size, size)
            cube.location = (half + offset, 0, 0)
        elif cut_plane == "XZ":
            # Remove Y < offset (back half)
            cube.scale = (size, half, size)
            cube.location = (0, -(half + abs(offset)), 0)
        else:
            cube.scale = (half, size, size)
            cube.location = (half + offset, 0, 0)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        cube.data.materials.clear()
        cube.data.materials.append(section_mat)
        return cube

    else:
        log.warning("Unknown cut_type '%s', falling back to quarter", cut_type)
        return create_cutter("quarter", cut_plane, offset, size)


def apply_section_cut(cutting_obj):
    """Apply Boolean DIFFERENCE to all mesh objects using EXACT solver."""
    cut_count = 0
    skip_count = 0
    for obj in list(bpy.context.scene.objects):
        if obj.type != "MESH" or obj == cutting_obj:
            continue
        if obj.name in ("Ground",):
            continue

        # Skip tiny objects that may cause boolean failures
        dims = obj.dimensions
        if max(dims.x, dims.y, dims.z) < 0.5:
            skip_count += 1
            continue

        mod = obj.modifiers.new(name="SectionCut", type='BOOLEAN')
        mod.operation = 'DIFFERENCE'
        mod.solver = 'EXACT'
        mod.object = cutting_obj

        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        try:
            bpy.ops.object.modifier_apply(modifier=mod.name)
            cut_count += 1
        except RuntimeError:
            log.warning("  EXACT failed on %s, trying FAST...", obj.name)
            obj.modifiers.remove(mod)
            mod2 = obj.modifiers.new(name="SectionCut", type='BOOLEAN')
            mod2.operation = 'DIFFERENCE'
            mod2.solver = 'FAST'
            mod2.object = cutting_obj
            try:
                bpy.ops.object.modifier_apply(modifier=mod2.name)
                cut_count += 1
            except RuntimeError:
                log.warning("  FAST also failed on %s, skipping", obj.name)
                obj.modifiers.remove(mod2)
        obj.select_set(False)

    log.info("Applied section cut to %d objects (%d tiny skipped)", cut_count, skip_count)
    return cut_count


def render_section_view(view_id, cam_cfg, section_override):
    """Import GLB, apply section cut, set camera, render one view."""
    sys.path.insert(0, SCRIPT_DIR)
    import render_3d

    # 1. Clear and import fresh (each view needs its own cut)
    render_3d.clear_scene()
    render_3d.import_glb(GLB_PATH)

    # 2. Determine cut parameters
    global_section = _CONFIG.get("section", {}) if _CONFIG else {}
    cut_type = section_override.get("cut_type", global_section.get("cut_type", "quarter"))
    cut_plane = section_override.get("cut_plane", global_section.get("cut_plane", "YZ"))
    offset = section_override.get("offset_mm", global_section.get("offset_mm", 0.0))

    log.info("Section %s: cut_type=%s, cut_plane=%s, offset=%.1fmm",
             view_id, cut_type, cut_plane, offset)

    # 3. Create cutting geometry and apply boolean
    cutter = create_cutter(cut_type, cut_plane, offset)
    apply_section_cut(cutter)
    bpy.data.objects.remove(cutter, do_unlink=True)

    # 4. Materials
    if _CONFIG:
        import render_config as rcfg
        render_3d._CONFIG_MATERIALS = rcfg.resolve_all_materials(_CONFIG)
    render_3d.assign_materials()

    # 5. Studio environment + lighting + render settings
    render_3d.setup_studio_environment()
    render_3d.setup_lighting()
    render_3d.setup_render(
        samples=args.samples,
        width=args.resolution[0],
        height=args.resolution[1],
        force_gpu=None if args.cpu else args.gpu,
        force_cpu=args.cpu,
    )

    # 6. Camera from config
    loc = cam_cfg.get("location", [600, -550, 600])
    target = cam_cfg.get("target", [0, 0, 140])
    lens_mm = cam_cfg.get("lens_mm", 35)
    view_name = cam_cfg.get("name", f"{view_id}_section")

    cam_data = bpy.data.cameras.new(f"{view_id}_Cam")
    cam_data.clip_start = 1.0
    cam_data.clip_end = 10000.0
    cam_data.lens = lens_mm
    cam_obj = bpy.data.objects.new(f"{view_id}_Cam", cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj

    cam_obj.location = Vector(loc)
    center = Vector(target)
    direction = center - cam_obj.location
    rot = direction.to_track_quat('-Z', 'Y')
    cam_obj.rotation_euler = rot.to_euler()

    log.info("Camera %s at (%s) → target (%s), lens=%dmm",
             view_id, ", ".join(f"{v:.0f}" for v in loc),
             ", ".join(f"{v:.0f}" for v in target), lens_mm)

    # 7. Render
    base_path = os.path.join(RENDER_DIR, f"{view_name}.png")
    bpy.context.scene.render.filepath = base_path
    bpy.ops.render.render(write_still=True)
    log.info("Saved: %s", base_path)

    if args.timestamp:
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        ts_path = os.path.join(RENDER_DIR, f"{view_name}_{ts}.png")
        import shutil
        shutil.copy2(base_path, ts_path)
        log.info("Copied: %s", ts_path)

    if os.path.isfile(base_path):
        size_kb = os.path.getsize(base_path) / 1024
        log.info("  Size: %.1f KB", size_kb)

    return base_path


def main():
    log.info("=" * 60)
    log.info("  End Effector — Cross-Section Renderer")
    log.info("=" * 60)

    section_views = _get_section_views()
    if not section_views:
        log.error("No section views found in render_config.json")
        return

    log.info("Section views to render: %s", [v[0] for v in section_views])

    for view_id, cam_cfg, section_override in section_views:
        log.info("\n--- Rendering %s ---", view_id)
        render_section_view(view_id, cam_cfg, section_override)

    log.info("\nAll %d section view(s) complete.", len(section_views))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    main()
