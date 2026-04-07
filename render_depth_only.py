"""
render_depth_only.py — Standalone depth-pass renderer for fal.ai ControlNet.

Loads a GLB assembly, reads camera positions from render_config.json,
renders depth-only EXR for each view (1 sample, ~2s per view).

Runs in an INDEPENDENT Blender session — never interferes with render_3d.py's
compositor, label pass, or any other render setup.

Usage:
    blender -b -P render_depth_only.py -- \
        --glb path/to/assembly.glb \
        --config path/to/render_config.json \
        --output-dir path/to/renders

Output: {output_dir}/{view_key}_depth.exr (32-bit float, near=small, far=large)
"""

import argparse
import math
import os
import sys

# ── Parse args (after Blender's --)  ─────────────────────────────────────────
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
parser = argparse.ArgumentParser(description="Depth-only renderer")
parser.add_argument("--glb", required=True, help="Path to GLB assembly file")
parser.add_argument("--config", required=True, help="Path to render_config.json")
parser.add_argument("--output-dir", required=True, help="Output directory for depth EXR files")
args = parser.parse_args(argv)

import bpy
import json
import logging

log = logging.getLogger("render_depth_only")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def clear_scene():
    """Remove all objects from the scene."""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    # Remove orphan data
    for block in bpy.data.meshes:
        if block.users == 0:
            bpy.data.meshes.remove(block)


def import_glb(filepath):
    """Import GLB file."""
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"GLB not found: {filepath}")
    bpy.ops.import_scene.gltf(filepath=filepath)
    log.info("Imported GLB: %s", os.path.basename(filepath))


def setup_depth_compositor(scene, output_path):
    """Set up minimal compositor for depth-only output.

    Uses scene.render.filepath for depth EXR output (avoids File Output node
    frame-number suffix issues). Sets output format to EXR 32-bit.
    """
    scene.use_nodes = True
    tree = scene.node_tree
    tree.nodes.clear()

    # Render Layers node
    rl = tree.nodes.new("CompositorNodeRLayers")
    rl.location = (0, 0)

    # Enable Z pass
    scene.view_layers[0].use_pass_z = True

    # Route DEPTH to Composite output (not Image)
    # This way scene.render.filepath controls the output path
    comp = tree.nodes.new("CompositorNodeComposite")
    comp.location = (400, 0)
    tree.links.new(rl.outputs["Depth"], comp.inputs["Image"])

    # Set output format to EXR
    scene.render.image_settings.file_format = "OPEN_EXR"
    scene.render.image_settings.color_depth = "32"
    scene.render.filepath = output_path


def setup_camera(scene, cam_preset, bounding_radius):
    """Position camera from render_config.json camera preset.

    Supports both formats:
    - Cartesian: {"location": [x,y,z], "target": [x,y,z]}
    - Spherical: {"azimuth_deg": N, "elevation_deg": N, "distance_factor": N}
    """
    cam_data = bpy.data.cameras.new("DepthCam")
    cam_obj = bpy.data.objects.new("DepthCam", cam_data)
    scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj

    if "location" in cam_preset:
        # Cartesian format
        loc = cam_preset["location"]
        target = cam_preset.get("target", [0, 0, 0])
        cam_obj.location = (loc[0], loc[1], loc[2])
        dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(loc, target)))
    elif "azimuth_deg" in cam_preset:
        # Spherical format
        az = math.radians(cam_preset.get("azimuth_deg", 45))
        el = math.radians(cam_preset.get("elevation_deg", 30))
        dist_factor = cam_preset.get("distance_factor", 2.5)
        dist = bounding_radius * dist_factor
        target = cam_preset.get("target", [0, 0, bounding_radius * 0.33])
        x = dist * math.cos(el) * math.cos(az) + target[0]
        y = dist * math.cos(el) * math.sin(az) + target[1]
        z = dist * math.sin(el) + target[2]
        cam_obj.location = (x, y, z)
    else:
        # Fallback
        dist = bounding_radius * 2.5
        target = [0, 0, 0]
        cam_obj.location = (dist, -dist, dist)

    # Point camera at target
    from mathutils import Vector
    direction = Vector(target) - cam_obj.location
    rot_quat = direction.to_track_quat('-Z', 'Y')
    cam_obj.rotation_euler = rot_quat.to_euler()

    # Lens
    cam_data.lens = cam_preset.get("lens_mm", 65)
    cam_data.clip_start = 0.1
    cam_data.clip_end = max(dist * 5, 100)

    return cam_obj


def compute_bounding_radius():
    """Compute scene bounding radius from all mesh objects."""
    max_dist = 0
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            from mathutils import Vector
            world_pt = obj.matrix_world @ Vector(corner)
            d = world_pt.length
            if d > max_dist:
                max_dist = d
    return max(max_dist * 1.1, 1.0)


def main():
    os.makedirs(args.output_dir, exist_ok=True)

    # Load config
    with open(args.config, encoding="utf-8") as f:
        config = json.load(f)

    cameras = config.get("camera", {})
    if not cameras:
        log.error("No cameras in render_config.json")
        return

    # Setup scene
    clear_scene()
    import_glb(args.glb)
    bounding_r = compute_bounding_radius()
    log.info("Bounding radius: %.1f", bounding_r)

    # Render settings: minimal for depth (1 sample)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 1  # Depth is exact at 1 sample
    scene.cycles.use_denoising = False
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.image_settings.file_format = "PNG"  # For the composite (unused)

    rendered = 0
    for view_key, cam_preset in sorted(cameras.items()):
        if not isinstance(cam_preset, dict):
            continue
        # Skip non-standard views (exploded, section) — depth not meaningful
        vtype = cam_preset.get("type", "standard")
        if vtype in ("exploded",):
            log.info("Skipping %s (type=%s)", view_key, vtype)
            continue

        # Need at least location or azimuth to position camera
        if "location" not in cam_preset and "azimuth_deg" not in cam_preset:
            log.info("Skipping %s (no camera position data)", view_key)
            continue

        output_exr = os.path.join(args.output_dir, f"{view_key}_depth.exr")

        # Remove old camera
        for obj in bpy.data.objects:
            if obj.name == "DepthCam":
                bpy.data.objects.remove(obj, do_unlink=True)

        # Setup camera
        cam_obj = setup_camera(scene, cam_preset, bounding_r)

        log.info("Rendering depth: %s", view_key)
        setup_depth_compositor(scene, output_exr)
        bpy.ops.render.render(write_still=True)

        # Verify output
        if os.path.isfile(output_exr):
            log.info("  Saved: %s (%.0fKB)",
                     os.path.basename(output_exr),
                     os.path.getsize(output_exr) / 1024)
            rendered += 1
        else:
            # Blender may append frame number
            for candidate in [output_exr.replace(".exr", "0001.exr"),
                              output_exr.replace(".exr", ".exr0001.exr")]:
                if os.path.isfile(candidate):
                    os.rename(candidate, output_exr)
                    log.info("  Saved: %s (%.0fKB)",
                             os.path.basename(output_exr),
                             os.path.getsize(output_exr) / 1024)
                    rendered += 1
                    break
            else:
                log.warning("  Depth output not found for %s", view_key)

    log.info("Depth rendering complete: %d/%d views", rendered, len(cameras))


if __name__ == "__main__":
    main()
