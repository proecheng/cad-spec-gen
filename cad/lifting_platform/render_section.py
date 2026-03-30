"""
Blender Cross-Section Renderer — Lifting Platform

Reads all camera views with type:"section" from render_config.json,
applies a Boolean half-cut along the YZ plane to reveal the internal
lead-screw and guide-shaft mechanism, and renders each section view.

Usage:
    blender.exe -b -P cad/lifting_platform/render_section.py -- --config cad/lifting_platform/render_config.json
    blender.exe -b -P cad/lifting_platform/render_section.py -- --config cad/lifting_platform/render_config.json --view V6

Input:  cad/output/SLP-000_assembly.glb
Output: cad/output/renders/V6_section.png
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
                    help="Render only this view ID (e.g. V6)")
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
GLB_PATH = args.glb or os.path.join(CAD_OUTPUT, "SLP-000_assembly.glb")
RENDER_DIR = args.output_dir or os.path.join(CAD_OUTPUT, "renders")
os.makedirs(RENDER_DIR, exist_ok=True)

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
            "name": "V6_section",
            "location": [500, 0, 200],
            "target": [0, 0, 130],
            "lens_mm": 65,
        }, {})]

    cameras = _CONFIG.get("camera", {})
    views = []
    for vid, cam in sorted(cameras.items()):
        if cam.get("type") != "section":
            continue
        if args.view and vid != args.view:
            continue
        per_view_section = cam.get("section", {})
        views.append((vid, cam, per_view_section))
    return views


def _make_cut_cube(size, half, cut_type, cut_plane, offset, section_mat):
    """
    Create a Boolean cutter cube.

    cut_type: "half" — remove one half of the assembly
    cut_plane: "YZ" — cut perpendicular to X (expose internal X cross-section)
               "XZ" — cut perpendicular to Y (expose internal Y cross-section)
    offset: shift the cut plane by this amount in mm
    """
    if cut_type == "quarter":
        # Remove a quarter block: X>0 and Y<0 region
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

    # cut_type == "half" (default)
    bpy.ops.mesh.primitive_cube_add(size=1)
    cube = bpy.context.active_object
    cube.name = "Cutter"
    if cut_plane == "YZ":
        # Remove X > offset half
        cube.scale = (half, size, size)
        cube.location = (half + offset, 0, 0)
    elif cut_plane == "XZ":
        # Remove Y < offset half (front face)
        cube.scale = (size, half, size)
        cube.location = (0, -(half + abs(offset)), 0)
    else:
        cube.scale = (half, size, size)
        cube.location = (half + offset, 0, 0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    cube.data.materials.clear()
    cube.data.materials.append(section_mat)
    return cube


def apply_boolean_cut(section_cfg):
    """
    Apply Boolean difference cut to all mesh objects.
    Returns the cutter object (already removed from scene after modifiers applied).
    """
    cut_type  = section_cfg.get("cut_type",  "half")
    cut_plane = section_cfg.get("cut_plane", "YZ")
    offset    = section_cfg.get("offset_mm", 0.0)

    log.info("Section cut: type=%s plane=%s offset=%.1fmm", cut_type, cut_plane, offset)

    # Create cut-face material (orange-tinted aluminum)
    section_mat = bpy.data.materials.new("SectionFace")
    section_mat.use_nodes = True
    bsdf = section_mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.75, 0.55, 0.30, 1.0)
        bsdf.inputs["Metallic"].default_value    = 0.7
        bsdf.inputs["Roughness"].default_value   = 0.35

    # Bounding size for the cutter — must encompass the whole assembly
    size = 800.0
    half = size / 2.0

    cutter = _make_cut_cube(size, half, cut_type, cut_plane, offset, section_mat)

    # Apply Boolean modifier to every mesh
    mesh_objects = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.name != "Cutter"]
    log.info("  Applying Boolean to %d mesh objects...", len(mesh_objects))
    for obj in mesh_objects:
        bpy.context.view_layer.objects.active = obj
        mod = obj.modifiers.new(name="SectionCut", type="BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.object = cutter
        bpy.ops.object.modifier_apply(modifier="SectionCut")

    # Remove cutter
    bpy.data.objects.remove(cutter, do_unlink=True)
    log.info("  Boolean cut complete")


def render_section_view(view_id, cam_cfg, section_cfg, render_3d):
    """Clear, import, cut, setup, and render one section view."""
    view_name = cam_cfg.get("name", f"{view_id}_section")

    # Determine output path
    if args.timestamp:
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        output_path = os.path.join(RENDER_DIR, f"{view_name}_{ts}.png")
    else:
        output_path = os.path.join(RENDER_DIR, f"{view_name}.png")

    log.info("--- %s → %s ---", view_id, output_path)

    # Clear and re-import for each view (Boolean is destructive)
    render_3d.clear_scene()
    render_3d.import_glb(GLB_PATH)

    # Inject config into render_3d globals
    if _CONFIG:
        import render_config as rcfg
        render_3d._CONFIG = _CONFIG
        render_3d._CONFIG_MATERIALS = rcfg.resolve_all_materials(_CONFIG)
        render_3d._CONFIG_CAMERAS = _CONFIG.get("camera", {})
        render_3d._BOUNDING_R = _CONFIG["subsystem"].get("bounding_radius_mm", 250.0)

    # Apply section cut
    global_section = _CONFIG.get("section", {}) if _CONFIG else {}
    merged_section = {**global_section, **section_cfg}
    apply_boolean_cut(merged_section)

    # Materials, lighting, render settings
    render_3d.assign_materials()
    res = _CONFIG.get("resolution", {}) if _CONFIG else {}
    width = res.get("width", 1920)
    height = res.get("height", 1080)
    render_3d.setup_render(args.samples, width, height,
                           force_gpu=args.gpu, force_cpu=args.cpu)

    # Camera
    for obj in bpy.context.scene.objects:
        if obj.type == "CAMERA":
            bpy.data.objects.remove(obj, do_unlink=True)

    render_3d.setup_camera(view_id)
    bpy.context.scene.render.filepath = output_path
    bpy.ops.render.render(write_still=True)
    log.info("Saved: %s", output_path)

    # Latest copy without timestamp
    latest_path = os.path.join(RENDER_DIR, f"{view_name}.png")
    if output_path != latest_path:
        import shutil
        shutil.copy2(output_path, latest_path)
        log.info("Latest copy: %s", latest_path)

    size_kb = os.path.getsize(output_path) / 1024
    log.info("  Size: %.1f KB", size_kb)
    return output_path


def main():
    sys.path.insert(0, SCRIPT_DIR)
    import render_3d

    log.info("=" * 60)
    log.info("  Lifting Platform — Cross-Section Renderer")
    log.info("=" * 60)

    section_views = _get_section_views()
    if not section_views:
        log.error("No section views found in config (type=\"section\")")
        return

    log.info("Section views to render: %s", [v[0] for v in section_views])

    results = []
    for view_id, cam_cfg, section_cfg in section_views:
        path = render_section_view(view_id, cam_cfg, section_cfg, render_3d)
        results.append(path)

    log.info("=" * 60)
    log.info("  Rendered %d section view(s):", len(results))
    for r in results:
        log.info("    %s", os.path.basename(r))
    log.info("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG if "--verbose" in sys.argv else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    main()
