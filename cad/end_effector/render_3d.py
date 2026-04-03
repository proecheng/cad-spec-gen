"""
Blender Cycles Renderer — End Effector Photo-Realistic Rendering

Run headless via Blender:
    blender.exe -b -P cad/end_effector/render_3d.py -- --all
    blender.exe -b -P cad/end_effector/render_3d.py -- --view V1
    blender.exe -b -P cad/end_effector/render_3d.py -- --view V3 --samples 256
    blender.exe -b -P cad/end_effector/render_3d.py -- --all --cpu  # force CPU
    blender.exe -b -P cad/end_effector/render_3d.py -- --all --gpu  # force GPU

GPU auto-detection: OptiX (RTX) > CUDA > HIP (AMD) > OneAPI (Intel) > CPU fallback.
Requires: Blender 4.x (portable OK).
Input:  cad/output/EE-000_assembly.glb
Output: cad/output/renders/V1_front_iso.png ... V5_ortho.png
"""

import bpy
import logging
import math
import os
import sys
from mathutils import Vector, Euler

# ── Logging setup ─────────────────────────────────────────────────────────────
log = logging.getLogger("render_3d")

# ── Parse CLI args (after "--") ──────────────────────────────────────────────
argv = sys.argv
if "--" in argv:
    argv = argv[argv.index("--") + 1:]
else:
    argv = []

import argparse

parser = argparse.ArgumentParser(description="Render end effector assembly")
parser.add_argument("--glb", default=None,
                    help="Path to GLB file (default: auto-detect)")
parser.add_argument("--config", default=None,
                    help="Path to render_config.json (optional, fallback: hardcoded)")
parser.add_argument("--view", default=None,
                    help="Render single view: V1|V2|V3|V4|V5")
parser.add_argument("--all", action="store_true",
                    help="Render all 5 views")
parser.add_argument("--samples", type=int, default=512,
                    help="Cycles samples (default: 256)")
parser.add_argument("--resolution", type=int, nargs=2, default=[1920, 1080],
                    help="Width Height (default: 1920 1080)")
parser.add_argument("--output-dir", default=None,
                    help="Output directory (default: cad/output/renders)")
parser.add_argument("--timestamp", action="store_true",
                    help="Append YYYYMMDD_HHMM to output filenames")
parser.add_argument("--gpu", action="store_true", default=None,
                    help="Force GPU rendering (auto-detected if omitted)")
parser.add_argument("--cpu", action="store_true", default=False,
                    help="Force CPU rendering even if GPU available")
args = parser.parse_args(argv)

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CAD_OUTPUT = os.environ.get("CAD_OUTPUT_DIR", os.path.join(SCRIPT_DIR, "..", "output"))
GLB_PATH = args.glb or os.path.join(CAD_OUTPUT, "EE-000_assembly.glb")
RENDER_DIR = args.output_dir or os.path.join(CAD_OUTPUT, "renders")
os.makedirs(RENDER_DIR, exist_ok=True)

# ── Config loading (W4: --config with hardcoded fallback) ────────────────────
_CONFIG = None
_CONFIG_MATERIALS = None
_CONFIG_CAMERAS = None
_BOUNDING_R = 300.0

if args.config:
    sys.path.insert(0, SCRIPT_DIR)
    import render_config as rcfg
    _CONFIG = rcfg.load_config(args.config)
    _CONFIG_MATERIALS = rcfg.resolve_all_materials(_CONFIG)
    _CONFIG_CAMERAS = _CONFIG.get("camera", {})
    _BOUNDING_R = _CONFIG["subsystem"].get("bounding_radius_mm", 300.0)
    # Override GLB path from config if not explicitly set via --glb
    if not args.glb and _CONFIG.get("_resolved", {}).get("glb_path"):
        GLB_PATH = _CONFIG["_resolved"]["glb_path"]
    log.info("Config loaded: %s", args.config)
    log.info("  Subsystem: %s", _CONFIG['subsystem'].get('name', '?'))
    log.info("  Materials: %d", len(_CONFIG_MATERIALS))
    log.info("  Cameras: %d", len(_CONFIG_CAMERAS))
else:
    log.info("No --config provided, using hardcoded defaults.")
    # Auto-load render_config.json from script directory if no --config given
    _auto_config = os.path.join(SCRIPT_DIR, "render_config.json")
    if os.path.isfile(_auto_config):
        log.info("Auto-loading: %s", _auto_config)
        sys.path.insert(0, SCRIPT_DIR)
        import render_config as rcfg
        _CONFIG = rcfg.load_config(_auto_config)
        _CONFIG_MATERIALS = rcfg.resolve_all_materials(_CONFIG)
        _CONFIG_CAMERAS = _CONFIG.get("camera", {})
        _BOUNDING_R = _CONFIG["subsystem"].get("bounding_radius_mm", 300.0)


# ═════════════════════════════════════════════════════════════════════════════
# Fallback material definitions (used ONLY when no config is available)
# ═════════════════════════════════════════════════════════════════════════════
# These are kept as last-resort defaults. Prefer render_config.json materials.
MATERIAL_MAP = {
    # ── Flange: brushed silver aluminum ──
    "flange_al": {
        "color": (0.82, 0.82, 0.84, 1.0),
        "metallic": 1.0,
        "roughness": 0.18,
        "anisotropic": 0.6,
        "label": "Brushed Al-7075",
    },
    # ── Adapter plate: same aluminum family ──
    "adapter": {
        "color": (0.78, 0.78, 0.80, 1.0),
        "metallic": 1.0,
        "roughness": 0.20,
        "anisotropic": 0.5,
        "label": "Brushed Al (adapter)",
    },
    # ── PEEK: deep amber/honey translucent ──
    "peek": {
        "color": (0.90, 0.60, 0.05, 1.0),
        "metallic": 0.0,
        "roughness": 0.30,
        "sss": 0.08,
        "sss_color": (0.95, 0.70, 0.10),
        "ior": 1.65,
        "specular": 0.7,
        "label": "PEEK Amber",
    },
    # ── Station 1 Applicator: steel blue (cold-rolled) ──
    "applicator": {
        "color": (0.35, 0.55, 0.75, 1.0),
        "metallic": 0.85,
        "roughness": 0.22,
        "label": "Anodized Blue (S1 applicator)",
    },
    # ── Station 2 AE: forest green anodized ──
    "station2_ae": {
        "color": (0.15, 0.50, 0.25, 1.0),
        "metallic": 0.85,
        "roughness": 0.22,
        "label": "Anodized Green (S2 AE)",
    },
    # ── Station 3 Cleaner: warm bronze/copper ──
    "cleaner": {
        "color": (0.70, 0.42, 0.20, 1.0),
        "metallic": 0.90,
        "roughness": 0.25,
        "label": "Bronze (S3 cleaner)",
    },
    # ── Station 4 UHF: deep purple anodized ──
    "uhf": {
        "color": (0.50, 0.18, 0.65, 1.0),
        "metallic": 0.85,
        "roughness": 0.22,
        "label": "Anodized Purple (S4 UHF)",
    },
    # ── Drive: dark gunmetal ──
    "drive": {
        "color": (0.18, 0.18, 0.20, 1.0),
        "metallic": 0.90,
        "roughness": 0.25,
        "label": "Gunmetal (drive)",
    },
    # ── Motor: same dark metal family ──
    "motor": {
        "color": (0.15, 0.15, 0.17, 1.0),
        "metallic": 0.90,
        "roughness": 0.28,
        "label": "Dark Steel (motor)",
    },
    # ── Rubber parts: matte black ──
    "rubber": {
        "color": (0.03, 0.03, 0.03, 1.0),
        "metallic": 0.0,
        "roughness": 0.75,
        "sss": 0.05,
        "label": "Black Rubber",
    },
    "gimbal": {
        "color": (0.04, 0.04, 0.04, 1.0),
        "metallic": 0.0,
        "roughness": 0.70,
        "sss": 0.05,
        "label": "Black Rubber (gimbal)",
    },
}

# ── Camera presets (§4.10.4) ─────────────────────────────────────────────────
CAMERA_PRESETS = {
    "V1": {
        "name": "V1_front_iso",
        "location": (500, -500, 350),
        "target": (0, 0, 100),
        "description": "Front-left isometric — overall view",
    },
    "V2": {
        "name": "V2_rear_oblique",
        "location": (-400, 400, 450),
        "target": (0, 0, 100),
        "description": "Rear-right overhead — back face view",
    },
    "V3": {
        "name": "V3_side_elevation",
        "location": (600, 0, 100),
        "target": (0, 0, 100),
        "description": "Pure side — stacking structure",
    },
    "V4": {
        "name": "V4_exploded",
        "location": (550, -550, 400),
        "target": (0, 0, 100),
        "description": "Exploded view (use render_exploded.py)",
    },
    "V5": {
        "name": "V5_ortho_front",
        "location": (0, -700, 100),
        "target": (0, 0, 100),
        "description": "Front orthographic projection",
        "ortho": True,
        "ortho_scale": 500,
    },
}


# ═════════════════════════════════════════════════════════════════════════════
# Blender scene setup
# ═════════════════════════════════════════════════════════════════════════════

def clear_scene():
    """Remove default cube/lamp/camera."""
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in bpy.data.meshes:
        if block.users == 0:
            bpy.data.meshes.remove(block)


def import_glb(filepath):
    """Import GLB file into scene."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"GLB not found: {filepath}")
    bpy.ops.import_scene.gltf(filepath=filepath)
    log.info("Imported: %s", filepath)
    for obj in bpy.context.scene.objects:
        log.debug("  Object: %s (type=%s)", obj.name, obj.type)


def create_pbr_material(name, params):
    """Create a Principled BSDF material with given PBR parameters."""
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # Clear default nodes
    for node in nodes:
        nodes.remove(node)

    # Output
    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (400, 0)

    # Principled BSDF
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (0, 0)
    bsdf.inputs["Base Color"].default_value = params["color"]
    bsdf.inputs["Metallic"].default_value = params.get("metallic", 0.0)
    bsdf.inputs["Roughness"].default_value = params.get("roughness", 0.5)

    if "anisotropic" in params:
        bsdf.inputs["Anisotropic"].default_value = params["anisotropic"]
    if "ior" in params:
        bsdf.inputs["IOR"].default_value = params["ior"]
    if "specular" in params:
        bsdf.inputs["Specular IOR Level"].default_value = params["specular"]
    if "sss" in params:
        bsdf.inputs["Subsurface Weight"].default_value = params["sss"]
        if "sss_color" in params:
            sc = params["sss_color"]
            bsdf.inputs["Subsurface Radius"].default_value = (sc[0], sc[1], sc[2])

    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    return mat


def assign_materials():
    """Match objects to materials based on name patterns.

    Uses _CONFIG_MATERIALS from render_config.json if loaded,
    otherwise falls back to hardcoded MATERIAL_MAP.
    """
    source = _CONFIG_MATERIALS if _CONFIG_MATERIALS else MATERIAL_MAP

    materials = {}
    for pattern, params in source.items():
        mat = create_pbr_material(f"PBR_{pattern}", params)
        materials[pattern] = mat

    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        name_lower = obj.name.lower()
        assigned = False
        for pattern, mat in materials.items():
            if pattern in name_lower:
                obj.data.materials.clear()
                obj.data.materials.append(mat)
                log.debug("  Material '%s' → %s", pattern, obj.name)
                assigned = True
                break
        if not assigned:
            if "PBR_default" not in bpy.data.materials:
                default_mat = create_pbr_material("PBR_default", {
                    "color": (0.6, 0.6, 0.62, 1.0),
                    "metallic": 0.5,
                    "roughness": 0.35,
                })
            else:
                default_mat = bpy.data.materials["PBR_default"]
            obj.data.materials.clear()
            obj.data.materials.append(default_mat)
            log.debug("  Material 'default' → %s", obj.name)

    # Smooth shading for all meshes
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH":
            for poly in obj.data.polygons:
                poly.use_smooth = True


def setup_studio_environment():
    """Create a studio-like environment with gradient background and ground plane.

    Metal materials need environmental reflections to look realistic.
    A plain transparent background kills all reflection detail.
    Ground plane scales with _BOUNDING_R when config is loaded.
    """
    ground_size = _BOUNDING_R * 6 if _CONFIG else 2000
    # ── Ground plane (large, matte gray, catches shadows) ──
    bpy.ops.mesh.primitive_plane_add(size=ground_size, location=(0, 0, -80))
    ground = bpy.context.active_object
    ground.name = "Ground"
    ground_mat = bpy.data.materials.new(name="GroundMat")
    ground_mat.use_nodes = True
    g_nodes = ground_mat.node_tree.nodes
    g_bsdf = g_nodes.get("Principled BSDF")
    g_bsdf.inputs["Base Color"].default_value = (0.95, 0.95, 0.96, 1.0)
    g_bsdf.inputs["Roughness"].default_value = 0.15
    g_bsdf.inputs["Specular IOR Level"].default_value = 0.8
    ground.data.materials.clear()
    ground.data.materials.append(ground_mat)

    # ── World: gradient sky for environment reflections ──
    world = bpy.data.worlds.new("StudioWorld")
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links

    # Clear defaults
    for node in nodes:
        nodes.remove(node)

    # Gradient: light top → slightly darker bottom
    output = nodes.new("ShaderNodeOutputWorld")
    output.location = (600, 0)

    bg = nodes.new("ShaderNodeBackground")
    bg.location = (400, 0)
    bg.inputs["Strength"].default_value = 1.0

    color_ramp = nodes.new("ShaderNodeValToRGB")
    color_ramp.location = (150, 0)
    # Top = light blue-white, Bottom = warm gray
    color_ramp.color_ramp.elements[0].position = 0.0
    color_ramp.color_ramp.elements[0].color = (0.75, 0.78, 0.82, 1.0)
    color_ramp.color_ramp.elements[1].position = 1.0
    color_ramp.color_ramp.elements[1].color = (0.95, 0.96, 0.98, 1.0)

    gradient = nodes.new("ShaderNodeTexGradient")
    gradient.location = (-50, 0)
    gradient.gradient_type = "LINEAR"

    mapping = nodes.new("ShaderNodeMapping")
    mapping.location = (-250, 0)
    mapping.inputs["Rotation"].default_value = (math.radians(90), 0, 0)

    tex_coord = nodes.new("ShaderNodeTexCoord")
    tex_coord.location = (-450, 0)

    links.new(tex_coord.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], gradient.inputs["Vector"])
    links.new(gradient.outputs["Color"], color_ramp.inputs["Fac"])
    links.new(color_ramp.outputs["Color"], bg.inputs["Color"])
    links.new(bg.outputs["Background"], output.inputs["Surface"])

    bpy.context.scene.world = world


def setup_lighting():
    """Professional 3-point + environment lighting for mechanical parts.

    Light sizes and energies scaled for a scene ~300mm across.
    When config is loaded, energies scale with _BOUNDING_R.
    Automatically creates studio environment (ground + sky) if not present.
    """
    # Ensure studio environment exists (called by render_3d main, but
    # render_exploded.py / render_section.py may skip it)
    if not any(o.name == "Ground" for o in bpy.context.scene.objects):
        setup_studio_environment()
    # Energy scaling factor (1.0 at 300mm)
    if _CONFIG:
        sys.path.insert(0, SCRIPT_DIR)
        import render_config as rcfg
        _e = rcfg.scaled_energies(_BOUNDING_R)
        e_key, e_fill, e_rim, e_bounce = (
            _e["key"], _e["fill"], _e["rim"], _e["bounce"])
    else:
        e_key, e_fill, e_rim, e_bounce = 80000, 40000, 60000, 15000

    # Key light — large area, warm white, overhead-right
    key = bpy.data.lights.new(name="Key", type="AREA")
    key.energy = e_key
    key.color = (1.0, 0.96, 0.92)
    key.size = 400           # 400mm soft box
    key.spread = math.radians(120)
    key_obj = bpy.data.objects.new("Key_Light", key)
    key_obj.location = (300, -250, 500)
    direction = Vector((0, 0, 50)) - key_obj.location
    key_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.collection.objects.link(key_obj)

    # Fill light — cool, soft, camera-left
    fill = bpy.data.lights.new(name="Fill", type="AREA")
    fill.energy = e_fill
    fill.color = (0.88, 0.92, 1.0)
    fill.size = 500          # Even larger for soft fill
    fill_obj = bpy.data.objects.new("Fill_Light", fill)
    fill_obj.location = (-350, -200, 300)
    direction = Vector((0, 0, 80)) - fill_obj.location
    fill_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.collection.objects.link(fill_obj)

    # Rim light — bright, narrow, behind to create edge highlights
    rim = bpy.data.lights.new(name="Rim", type="AREA")
    rim.energy = e_rim
    rim.color = (1.0, 1.0, 1.0)
    rim.size = 200
    rim_obj = bpy.data.objects.new("Rim_Light", rim)
    rim_obj.location = (-100, 350, 400)
    direction = Vector((0, 0, 80)) - rim_obj.location
    rim_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.collection.objects.link(rim_obj)

    # Bottom bounce — subtle, warm, from below to lift shadows
    bounce = bpy.data.lights.new(name="Bounce", type="AREA")
    bounce.energy = e_bounce
    bounce.color = (1.0, 0.98, 0.95)
    bounce.size = 600
    bounce_obj = bpy.data.objects.new("Bounce_Light", bounce)
    bounce_obj.location = (0, 0, -60)
    bounce_obj.rotation_euler = (math.radians(180), 0, 0)  # pointing up
    bpy.context.scene.collection.objects.link(bounce_obj)


def _get_bounding_sphere():
    """Return (center, radius) of all non-ground mesh objects in scene."""
    verts = []
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH" and obj.name not in ("Ground",):
            matrix = obj.matrix_world
            for v in obj.data.vertices:
                verts.append(matrix @ v.co)
    if not verts:
        return Vector((0.0, 0.0, 0.0)), float(_BOUNDING_R)
    center = sum(verts, Vector()) / len(verts)
    radius = max((v - center).length for v in verts)
    return center, radius


def setup_camera(preset_key):
    """Create and position camera from preset.

    Uses _CONFIG_CAMERAS from render_config.json if loaded,
    otherwise falls back to hardcoded CAMERA_PRESETS.

    Auto-framing (enabled by default for perspective cameras):
      Computes the scene bounding sphere after GLB import, then moves the
      camera along its view direction so the object fills `frame_fill`
      (default 0.75) of the vertical field of view — independent of which
      direction the camera points. Disable per-view with "auto_frame": false.
    """
    source = _CONFIG_CAMERAS if _CONFIG_CAMERAS else CAMERA_PRESETS

    if preset_key not in source:
        raise ValueError(f"Unknown camera preset '{preset_key}'. "
                         f"Available: {list(source.keys())}")

    preset = dict(source[preset_key])

    # If from config, resolve spherical coords via render_config helper
    if _CONFIG and "azimuth_deg" in preset:
        sys.path.insert(0, SCRIPT_DIR)
        import render_config as rcfg
        preset = rcfg.camera_to_blender(preset, _BOUNDING_R)

    cam_data = bpy.data.cameras.new(name=preset.get("name", preset_key))

    if preset.get("ortho"):
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = preset.get("ortho_scale", 200)
    else:
        cam_data.type = "PERSP"
        cam_data.lens = preset.get("lens_mm", 65)  # from render_config.json, fallback 65mm
        cam_data.clip_start = 1
        cam_data.clip_end = 5000

    cam_obj = bpy.data.objects.new(preset.get("name", preset_key), cam_data)
    loc = preset["location"]
    if isinstance(loc, list):
        loc = tuple(loc)
    cam_obj.location = Vector(loc)
    bpy.context.scene.collection.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj

    # Point camera at target
    tgt = preset.get("target", (0, 0, 0))
    if isinstance(tgt, list):
        tgt = tuple(tgt)
    target = Vector(tgt)
    direction = target - cam_obj.location
    rot_quat = direction.to_track_quat("-Z", "Y")
    cam_obj.rotation_euler = rot_quat.to_euler()

    # ── Auto-frame: normalize distance so object fills frame_fill of vertical FOV ──
    # Works for any view direction; disable per-view with "auto_frame": false
    auto_frame = preset.get("auto_frame", True)
    if auto_frame:
        try:
            bs_center, bs_radius = _get_bounding_sphere()
            frame_fill = (_CONFIG.get("frame_fill", 0.75) if _CONFIG else 0.75)

            if cam_data.type == "PERSP":
                scene = bpy.context.scene
                sensor_w = cam_data.sensor_width  # Blender default 36mm
                aspect = scene.render.resolution_x / scene.render.resolution_y
                sensor_h = sensor_w / aspect
                fov_half = math.atan(sensor_h / (2.0 * cam_data.lens))
                required_dist = bs_radius / math.sin(fov_half) / frame_fill
                # Direction: from bounding-sphere center toward camera
                view_dir = (cam_obj.location - Vector(tgt)).normalized()
                cam_obj.location = bs_center + view_dir * required_dist
                # Re-aim at bounding-sphere center
                aim = bs_center - cam_obj.location
                cam_obj.rotation_euler = aim.to_track_quat("-Z", "Y").to_euler()
                log.info("  Auto-frame [%s]: center=(%.0f,%.0f,%.0f) r=%.0f dist=%.0f fill=%.0f%%",
                         preset_key,
                         bs_center.x, bs_center.y, bs_center.z,
                         bs_radius, required_dist, frame_fill * 100)

            elif cam_data.type == "ORTHO":
                # Auto-scale ortho to fit model bounding sphere
                cam_data.ortho_scale = bs_radius * 2.0 / frame_fill
                # Re-center camera aim at bounding-sphere center
                view_dir = (cam_obj.location - Vector(tgt)).normalized()
                cam_obj.location = bs_center + view_dir * (bs_radius * 4)
                aim = bs_center - cam_obj.location
                cam_obj.rotation_euler = aim.to_track_quat("-Z", "Y").to_euler()
                log.info("  Auto-frame ORTHO [%s]: ortho_scale=%.0f r=%.0f fill=%.0f%%",
                         preset_key, cam_data.ortho_scale,
                         bs_radius, frame_fill * 100)

        except Exception as _af_err:
            log.warning("  Auto-frame skipped: %s", _af_err)

    return cam_obj


def setup_render(samples, width, height, force_gpu=None, force_cpu=False):
    """Configure Cycles render settings with automatic GPU detection.

    Priority: --cpu flag > --gpu flag > auto-detect (OPTIX > CUDA > CPU).
    """
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"

    prefs = bpy.context.preferences.addons["cycles"].preferences

    # ── GPU auto-detection ──
    device_type = "NONE"
    device_name = "CPU"

    if not force_cpu:
        # Try OptiX first (RTX cards, fastest), then CUDA, then fallback CPU
        for candidate in ["OPTIX", "CUDA", "HIP", "ONEAPI"]:
            try:
                prefs.compute_device_type = candidate
                prefs.get_devices()
                # Check if any compute device is available
                devices = prefs.devices
                gpu_devices = [d for d in devices if d.type != "CPU"]
                if gpu_devices:
                    device_type = candidate
                    device_name = gpu_devices[0].name
                    # Enable all GPU devices + CPU for hybrid
                    for d in devices:
                        d.use = True
                    break
            except Exception:
                continue

        if device_type == "NONE" and force_gpu:
            log.warning("  --gpu requested but no GPU found, falling back to CPU")

    prefs.compute_device_type = device_type
    if device_type != "NONE":
        scene.cycles.device = "GPU"
        log.info("  Render device: %s — %s", device_type, device_name)
    else:
        scene.cycles.device = "CPU"
        log.info("  Render device: CPU")

    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"

    # Bounce settings for better metallic reflections
    scene.cycles.max_bounces = 8
    scene.cycles.diffuse_bounces = 4
    scene.cycles.glossy_bounces = 8
    scene.cycles.transmission_bounces = 4

    # Output settings
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"   # Opaque background
    scene.render.image_settings.compression = 15

    # NOT transparent — we need the environment for reflections
    scene.render.film_transparent = False

    # Color management: filmic for better dynamic range
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "Medium Contrast"
    scene.view_settings.exposure = 0.0

    scene.render.threads_mode = "AUTO"


def render_view(preset_key, timestamp=False):
    """Set up camera for a preset and render to file."""
    source = _CONFIG_CAMERAS if _CONFIG_CAMERAS else CAMERA_PRESETS
    preset = source[preset_key]
    view_name = preset.get("name", preset_key)

    # Build output filename with optional timestamp
    if timestamp:
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        output_path = os.path.join(RENDER_DIR, f"{view_name}_{ts}.png")
    else:
        output_path = os.path.join(RENDER_DIR, f"{view_name}.png")

    # Always write a "latest" copy (no timestamp) for downstream tools
    latest_path = os.path.join(RENDER_DIR, f"{view_name}.png")

    for obj in bpy.context.scene.objects:
        if obj.type == "CAMERA":
            bpy.data.objects.remove(obj, do_unlink=True)

    setup_camera(preset_key)
    bpy.context.scene.render.filepath = output_path

    # ── Label pass setup (Object Index mask — before render) ──
    _label_ctx = None
    try:
        import render_label_utils as _rlu
        _label_ctx = _rlu.setup_label_pass(_CONFIG, preset_key)
    except ImportError:
        pass

    log.info("\nRendering %s: %s", preset_key, preset.get('description', ''))
    log.info("  Output: %s", output_path)
    try:
        bpy.ops.render.render(write_still=True)
        log.info("  Done: %s", output_path)

        # Copy to latest BEFORE sidecar (sidecar references latest_path)
        if timestamp and output_path != latest_path:
            import shutil
            shutil.copy2(output_path, latest_path)
            log.info("  Latest: %s", latest_path)
    finally:
        # ── Label pass finalize (compute centroids, write sidecar, cleanup) ──
        if _label_ctx:
            try:
                import render_label_utils as _rlu
                _rlu.finalize_label_pass(_label_ctx, latest_path)
            except Exception as _le:
                log.warning("Label sidecar failed: %s", _le)

    return output_path


# ═════════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════════

def main():
    global _BOUNDING_R

    sub_name = "End Effector"
    if _CONFIG:
        sub_name = _CONFIG["subsystem"].get("name_cn",
                   _CONFIG["subsystem"].get("name", "Assembly"))

    log.info("=" * 60)
    log.info("  %s — Blender Cycles Renderer", sub_name)
    log.info("=" * 60)

    # 1. Clear and import
    clear_scene()
    import_glb(GLB_PATH)

    # 1b. Auto-detect bounding radius from GLB (W14)
    if _CONFIG:
        sys.path.insert(0, SCRIPT_DIR)
        import render_config as rcfg
        auto_r = rcfg.auto_bounding_radius(bpy.context.scene.objects)
        log.info("  Auto bounding radius: %.1fmm (config fallback: %.1fmm)",
                 auto_r, _BOUNDING_R)
        _BOUNDING_R = auto_r

    # 2. Materials + smooth shading
    log.info("Assigning PBR materials...")
    assign_materials()

    # 3. Studio environment (ground plane + gradient sky)
    log.info("Setting up studio environment...")
    setup_studio_environment()

    # 4. Lighting
    log.info("Setting up 4-point studio lighting...")
    setup_lighting()

    # 5. Render settings
    setup_render(args.samples, args.resolution[0], args.resolution[1],
                 force_gpu=args.gpu, force_cpu=args.cpu)

    # 6. Render requested views
    available = _CONFIG_CAMERAS if _CONFIG_CAMERAS else CAMERA_PRESETS
    views_to_render = []
    if args.all:
        # Skip any view with type "section" or "exploded" — handled by dedicated scripts
        skip = {k for k, v in available.items() if v.get("type") in ("section", "exploded")}
        views_to_render = [k for k in available if k not in skip]
        log.info("Rendering all standard views: %s", views_to_render)
        log.info("  (V4/V6 require render_exploded.py / render_section.py)")
    elif args.view:
        vk = args.view.upper()
        if vk not in available:
            log.error("Unknown view '%s'. Available: %s", vk, list(available.keys()))
            sys.exit(1)
        views_to_render = [vk]
    else:
        views_to_render = ["V1"]

    results = []
    for vk in views_to_render:
        path = render_view(vk, timestamp=args.timestamp)
        results.append(path)

    log.info("=" * 60)
    log.info("  Rendered %d view(s):", len(results))
    for r in results:
        size_kb = os.path.getsize(r) / 1024
        log.info("    %-40s %6.1f KB", os.path.basename(r), size_kb)
    log.info("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG if "--verbose" in sys.argv else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    main()
