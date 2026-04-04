"""
Render Configuration Engine — stdlib-only helper for Blender Python.

Provides:
  - MATERIAL_PRESETS: 15 common engineering material PBR definitions
  - load_config(path): load render_config.json with validation
  - validate_config(config): JSON Schema validation (optional, needs jsonschema)
  - resolve_material(entry): preset name → full PBR params (with overrides)
  - camera_to_blender(preset, bounding_r): Cartesian or spherical → Blender coords
  - lighting_scale(bounding_r): energy scaling for scene size
  - auto_bounding_radius(scene_objects): detect from GLB geometry

Constraints:
  - Core functions use ONLY stdlib imports (json, math, os) — runs inside Blender Python
  - validate_config() optionally uses jsonschema if available
"""

import json
import logging
import math
import os

log = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# Material Presets — 15 common engineering materials (W6: embedded, not file)
# ═════════════════════════════════════════════════════════════════════════════

MATERIAL_PRESETS = {
    # ── Metals ──
    "brushed_aluminum": {
        "color": (0.82, 0.82, 0.84, 1.0),
        "metallic": 1.0,
        "roughness": 0.18,
        "anisotropic": 0.6,
    },
    "anodized_blue": {
        "color": (0.35, 0.55, 0.75, 1.0),
        "metallic": 0.85,
        "roughness": 0.22,
    },
    "anodized_green": {
        "color": (0.15, 0.50, 0.25, 1.0),
        "metallic": 0.85,
        "roughness": 0.22,
    },
    "anodized_purple": {
        "color": (0.50, 0.18, 0.65, 1.0),
        "metallic": 0.85,
        "roughness": 0.22,
    },
    "anodized_red": {
        "color": (0.75, 0.15, 0.15, 1.0),
        "metallic": 0.85,
        "roughness": 0.22,
    },
    "black_anodized": {
        "color": (0.05, 0.05, 0.05, 1.0),
        "metallic": 0.85,
        "roughness": 0.30,
    },
    "bronze": {
        "color": (0.70, 0.42, 0.20, 1.0),
        "metallic": 0.90,
        "roughness": 0.25,
    },
    "copper": {
        "color": (0.85, 0.45, 0.18, 1.0),
        "metallic": 1.0,
        "roughness": 0.15,
    },
    "gunmetal": {
        "color": (0.18, 0.18, 0.20, 1.0),
        "metallic": 0.90,
        "roughness": 0.25,
    },
    "dark_steel": {
        "color": (0.15, 0.15, 0.17, 1.0),
        "metallic": 0.90,
        "roughness": 0.28,
    },
    "stainless_304": {
        "color": (0.75, 0.75, 0.77, 1.0),
        "metallic": 1.0,
        "roughness": 0.15,
    },
    # ── Plastics / Rubber ──
    "peek_amber": {
        "color": (0.90, 0.60, 0.05, 1.0),
        "metallic": 0.0,
        "roughness": 0.30,
        "sss": 0.08,
        "sss_color": (0.95, 0.70, 0.10),
        "ior": 1.65,
        "specular": 0.7,
    },
    "black_rubber": {
        "color": (0.03, 0.03, 0.03, 1.0),
        "metallic": 0.0,
        "roughness": 0.75,
        "sss": 0.05,
    },
    "white_nylon": {
        "color": (0.92, 0.92, 0.90, 1.0),
        "metallic": 0.0,
        "roughness": 0.45,
    },
    "polycarbonate_clear": {
        "color": (0.95, 0.95, 0.97, 1.0),
        "metallic": 0.0,
        "roughness": 0.05,
        "ior": 1.58,
    },
}


# ═════════════════════════════════════════════════════════════════════════════
# Config loading & validation
# ═════════════════════════════════════════════════════════════════════════════

def load_config(path):
    """Load render_config.json with basic validation.

    Returns dict or raises ValueError with clear message.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        try:
            config = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {path}: {e}") from e

    # Version check
    version = config.get("version")
    if version is not None and version != 1:
        raise ValueError(f"Unsupported config version: {version} (expected 1)")

    # Validate required top-level keys
    for key in ("subsystem", "materials", "camera"):
        if key not in config:
            raise ValueError(f"Config missing required key: '{key}'")

    # Validate subsystem
    sub = config["subsystem"]
    if "glb_file" not in sub:
        raise ValueError("subsystem.glb_file is required")
    if not sub.get("name"):
        raise ValueError("subsystem.name is required")

    # Validate materials non-empty
    if not config["materials"]:
        raise ValueError("materials must contain at least one entry")

    # Validate material presets
    for pattern, entry in config["materials"].items():
        if "preset" in entry and entry["preset"] not in MATERIAL_PRESETS:
            raise ValueError(
                f"Material '{pattern}' uses unknown preset '{entry['preset']}'. "
                f"Available: {sorted(MATERIAL_PRESETS.keys())}"
            )

    # Validate cameras
    if not config["camera"]:
        raise ValueError("camera must contain at least one view")

    # JSON Schema validation (optional)
    _validate_schema(config, path)

    # Resolve GLB path relative to config file directory
    config_dir = os.path.dirname(os.path.abspath(path))
    output_dir = os.environ.get(
        "CAD_OUTPUT_DIR",
        os.path.join(config_dir, "..", "output"),
    )
    config["_resolved"] = {
        "config_dir": config_dir,
        "output_dir": os.path.normpath(output_dir),
        "glb_path": os.path.normpath(
            os.path.join(output_dir, sub["glb_file"])
        ),
    }

    return config


def _validate_schema(config, config_path):
    """Validate config against JSON Schema if jsonschema is available."""
    try:
        import jsonschema
    except ImportError:
        return  # schema validation is optional

    schema_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "..", "templates", "render_config.schema.json",
    )
    if not os.path.isfile(schema_path):
        return

    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
        jsonschema.validate(config, schema)
        log.debug("JSON Schema validation passed: %s", config_path)
    except jsonschema.ValidationError as e:
        log.warning("JSON Schema validation warning: %s (path: %s)",
                    e.message, ".".join(str(p) for p in e.absolute_path))


# ═════════════════════════════════════════════════════════════════════════════
# Material resolution
# ═════════════════════════════════════════════════════════════════════════════

def resolve_material(mat_entry):
    """Resolve a material config entry to full PBR parameters.

    mat_entry can be:
      - {"preset": "anodized_blue"} → lookup from MATERIAL_PRESETS
      - {"preset": "anodized_blue", "overrides": {"roughness": 0.3}} → merge
      - {"color": [0.5,0.5,0.5,1], "metallic": 0.8, ...} → use directly

    Returns dict with at minimum: color, metallic, roughness.
    """
    if "preset" in mat_entry:
        preset_name = mat_entry["preset"]
        if preset_name not in MATERIAL_PRESETS:
            raise ValueError(
                f"Unknown preset '{preset_name}'. "
                f"Available: {sorted(MATERIAL_PRESETS.keys())}"
            )
        params = dict(MATERIAL_PRESETS[preset_name])  # copy
        # Apply overrides
        overrides = mat_entry.get("overrides", {})
        params.update(overrides)
        # Copy label if present
        if "label" in mat_entry:
            params["label"] = mat_entry["label"]
        return params

    # Direct specification (no preset)
    params = dict(mat_entry)
    # Ensure color is tuple
    if "color" in params and isinstance(params["color"], list):
        params["color"] = tuple(params["color"])
    return params


def resolve_all_materials(config):
    """Resolve all materials in config to full PBR dicts.

    Returns dict: {pattern_name: {color, metallic, roughness, ...}}
    """
    result = {}
    for pattern, entry in config.get("materials", {}).items():
        result[pattern] = resolve_material(entry)
    return result


def resolve_bom_materials(config, resolved_materials=None):
    """Build bom_id→material mapping from components section.

    Bridges the components (with bom_id) to materials (with PBR presets)
    via the component's 'material' field. Falls back to comp_key as
    material name if no explicit 'material' field.

    Args:
        config: parsed render_config.json dict
        resolved_materials: pre-resolved {pattern: PBR_params} dict,
            or None to resolve from config

    Returns:
        {normalized_bom_id: material_key} dict.
        Normalized = project prefix stripped, lowercased (e.g. "ee-001").
    """
    import re as _re
    if resolved_materials is None:
        resolved_materials = resolve_all_materials(config)

    result = {}
    for comp_key, comp in config.get("components", {}).items():
        if isinstance(comp, str) or comp_key.startswith("_"):
            continue
        bom_id = comp.get("bom_id", "")
        mat_key = comp.get("material", comp_key)
        if not bom_id or mat_key not in resolved_materials:
            continue
        # Normalize: strip project prefix (GIS-EE-001 → EE-001 → ee-001)
        normalized = _re.sub(r'^[A-Z]+-', '', bom_id).lower()
        result[normalized] = mat_key
    return result


# ═════════════════════════════════════════════════════════════════════════════
# Camera helpers
# ═════════════════════════════════════════════════════════════════════════════

def camera_to_blender(preset, bounding_r=300):
    """Convert camera preset to Blender-ready dict.

    Supports two modes (W3):
      - Cartesian: {"location": [x,y,z], "target": [x,y,z]}
      - Spherical: {"azimuth_deg": 45, "elevation_deg": 30, "distance_factor": 2.5}

    For spherical, distance = bounding_r * distance_factor.
    Returns dict with "location" and "target" as tuples.
    """
    result = dict(preset)

    if "azimuth_deg" in preset:
        # Spherical → Cartesian
        az = math.radians(preset["azimuth_deg"])
        el = math.radians(preset.get("elevation_deg", 30))
        dist = bounding_r * preset.get("distance_factor", 2.5)
        target = preset.get("target", [0, 0, bounding_r * 0.33])

        x = dist * math.cos(el) * math.cos(az)
        y = dist * math.cos(el) * math.sin(az)
        z = dist * math.sin(el)

        if isinstance(target, list):
            target = tuple(target)

        result["location"] = (
            x + target[0],
            y + target[1],
            z + target[2],
        )
        result["target"] = target
    else:
        # Cartesian — ensure tuples
        if "location" in result and isinstance(result["location"], list):
            result["location"] = tuple(result["location"])
        if "target" in result and isinstance(result["target"], list):
            result["target"] = tuple(result["target"])

    return result


# ═════════════════════════════════════════════════════════════════════════════
# Lighting scale
# ═════════════════════════════════════════════════════════════════════════════

# Reference energies calibrated for bounding_r=300mm
_REF_BOUNDING_R = 300.0
_REF_ENERGIES = {
    "key": 80000,
    "fill": 40000,
    "rim": 60000,
    "bounce": 15000,
}


def lighting_scale(bounding_r):
    """Scale factor for light energy: energy ∝ (bounding_r / 300)².

    Returns a multiplier to apply to reference energies.
    """
    return (bounding_r / _REF_BOUNDING_R) ** 2


def scaled_energies(bounding_r):
    """Return dict of light energies scaled for given scene size."""
    s = lighting_scale(bounding_r)
    return {name: energy * s for name, energy in _REF_ENERGIES.items()}


# ═════════════════════════════════════════════════════════════════════════════
# Bounding radius auto-detection (W14)
# ═════════════════════════════════════════════════════════════════════════════

def auto_bounding_radius(scene_objects):
    """Detect bounding radius from Blender scene objects.

    Call AFTER importing GLB into Blender scene.
    scene_objects: iterable of bpy.types.Object

    Returns float (mm). Falls back to 300 if no mesh found.
    """
    max_dist = 0.0
    found_mesh = False

    for obj in scene_objects:
        if obj.type != "MESH":
            continue
        found_mesh = True
        # Get world-space bounding box corners
        for corner in obj.bound_box:
            # bound_box is in local coords, transform to world
            world_pt = obj.matrix_world @ __import__("mathutils").Vector(corner)
            dist = world_pt.length
            if dist > max_dist:
                max_dist = dist

    if not found_mesh or max_dist < 1.0:
        return 300.0  # safe fallback

    # Add 10% margin
    return max_dist * 1.1
