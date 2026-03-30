"""
render_label_utils.py — Accurate 2D label anchors via Object Index Mask pass.

Instead of projecting obj.location (which may be off-center or occluded),
this module uses Blender's Object Index render pass to find the *visible-pixel
centroid* of each labeled component.  The result is a sidecar JSON with the
same format as the legacy projection approach, so annotate_render.py requires
no changes.

Workflow (caller must bracket the render call):
    ctx = setup_label_pass(config, preset_key)
    bpy.ops.render.render(write_still=True)      # single render, index piggybacked
    finalize_label_pass(ctx, png_path)

Falls back to world_to_camera_view projection when:
  - The index EXR cannot be produced or read
  - A component has fewer than MIN_VISIBLE_PX visible pixels (fully occluded)
  - A component object is not found in the scene

Runs INSIDE Blender's Python environment.
"""

import glob
import json
import logging
import os
import shutil
import tempfile

import bpy
import numpy as np

log = logging.getLogger("render_label_utils")

# Minimum visible pixels before we trust the centroid.
# Below this threshold we fall back to world_to_camera_view.
MIN_VISIBLE_PX = 50


# ═══════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════

def setup_label_pass(config, preset_key):
    """Prepare Object Index pass BEFORE the render call.

    Returns a context dict (pass to ``finalize_label_pass``), or *None*
    if there is nothing to label for this view.
    """
    if not config:
        return None
    labels_cfg = config.get("labels", {}).get(preset_key, [])
    if not labels_cfg:
        return None

    scene = bpy.context.scene
    vl = bpy.context.view_layer

    # ── Save original state ──────────────────────────────────────────────
    orig_use_nodes = scene.use_nodes
    orig_use_pass = vl.use_pass_object_index
    orig_pass_indices = {}

    # ── Assign pass_index per labeled component (1-based) ────────────────
    index_map = {}  # component_name → int
    for i, item in enumerate(labels_cfg, start=1):
        comp = item.get("component", "")
        obj = _find_object(comp)
        if obj:
            orig_pass_indices[obj.name] = obj.pass_index  # key by name (survives GC)
            obj.pass_index = i
            index_map[comp] = i

    if not index_map:
        # No objects matched — restore and bail
        return None

    # ── Enable compositor first, then Object Index pass ─────────────────
    scene.use_nodes = True
    tree = scene.node_tree
    vl.use_pass_object_index = True

    # Find the (usually default) Render Layers node
    rl_node = None
    for n in tree.nodes:
        if n.type == "R_LAYERS":
            rl_node = n
            break
    if not rl_node:
        rl_node = tree.nodes.new("CompositorNodeRLayers")

    # Force Render Layers node to refresh its outputs after enabling the pass
    rl_node.scene = scene
    rl_node.layer = vl.name

    # Temp directory for the index EXR
    exr_dir = tempfile.mkdtemp(prefix="blender_idx_")

    out_node = tree.nodes.new("CompositorNodeOutputFile")
    out_node.name = "__label_idx_output__"
    out_node.base_path = exr_dir
    out_node.format.file_format = "OPEN_EXR"
    out_node.format.color_depth = "32"
    out_node.file_slots[0].path = "idx_"

    # Connect RenderLayers ▸ IndexOB → OutputFile
    # Note: Blender 4.x bpy_prop_collection[key] fails for disabled outputs;
    # must iterate to find by name and use the object reference directly.
    _idx_output = None
    for _o in rl_node.outputs:
        if _o.name == "IndexOB":
            _idx_output = _o
            break
    if _idx_output is None:
        log.error("No IndexOB output found on Render Layers node. Aborting label pass.")
        tree.nodes.remove(out_node)
        shutil.rmtree(exr_dir, ignore_errors=True)
        scene.use_nodes = orig_use_nodes
        vl.use_pass_object_index = orig_use_pass
        for obj_name, orig_idx in orig_pass_indices.items():
            obj = bpy.data.objects.get(obj_name)
            if obj:
                obj.pass_index = orig_idx
        return None
    _idx_output.enabled = True
    tree.links.new(_idx_output, out_node.inputs[0])

    return {
        "index_map": index_map,
        "labels_cfg": labels_cfg,
        "config": config,
        "preset_key": preset_key,
        "exr_dir": exr_dir,
        "out_node_name": out_node.name,
        "orig_use_nodes": orig_use_nodes,
        "orig_use_pass": orig_use_pass,
        "orig_pass_indices": orig_pass_indices,
    }


def finalize_label_pass(ctx, png_path):
    """Read the index EXR, compute centroids, write sidecar, cleanup.

    Must be called AFTER ``bpy.ops.render.render()``.
    """
    if ctx is None:
        return
    try:
        entries = _compute_centroids(ctx)
        _write_sidecar(ctx["preset_key"], png_path, entries)
    finally:
        _cleanup(ctx)


# ═══════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _find_object(component_name):
    """Find a MESH object by component name.

    Search order:
      1. Exact name match
      2. Case-insensitive exact match
      3. Suffix match: object name ends with ``_<component>`` (e.g. "EE-002_applicator_housing" matches "applicator_housing")
      4. Substring match: component name appears in object name (e.g. "applicator" matches "EE-002_applicator_housing")
    For ambiguous substring matches, the shortest object name wins (most specific).
    """
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]

    # 1. Exact
    obj = bpy.data.objects.get(component_name)
    if obj and obj.type == "MESH":
        return obj

    lower = component_name.lower()

    # 2. Case-insensitive exact
    for o in meshes:
        if o.name.lower() == lower:
            return o

    # 3. Suffix match: obj.name ends with _<component>
    suffix = "_" + lower
    for o in meshes:
        if o.name.lower().endswith(suffix):
            return o

    # 4. Substring match (shortest name wins = most specific)
    candidates = [o for o in meshes if lower in o.name.lower()]
    if candidates:
        candidates.sort(key=lambda o: len(o.name))
        return candidates[0]

    return None


def _compute_centroids(ctx):
    """Read index EXR → per-component visible-pixel centroid."""
    scene = bpy.context.scene
    cam = scene.camera
    res_x = scene.render.resolution_x
    res_y = scene.render.resolution_y

    # Reference resolution (matches annotate_render.py default)
    ref_res = ctx["config"].get("reference_resolution", {})
    ref_w = ref_res.get("width", 1920)
    ref_h = ref_res.get("height", 1080)

    index_map = ctx["index_map"]
    labels_cfg = ctx["labels_cfg"]

    # ── Try to load the index mask ───────────────────────────────────────
    mask = _load_index_mask(ctx["exr_dir"], res_x, res_y)

    entries = []
    for item in labels_cfg:
        comp = item.get("component", "")
        idx = index_map.get(comp)

        # ── Method 1: centroid from index mask ───────────────────────────
        if mask is not None and idx is not None:
            comp_mask = np.abs(mask - idx) < 0.5
            visible = int(np.sum(comp_mask))

            if visible >= MIN_VISIBLE_PX:
                ys, xs = np.where(comp_mask)
                cx = int(np.mean(xs))
                cy = int(np.mean(ys))
                # Render resolution → reference resolution
                ax = int(cx * ref_w / res_x)
                ay = int(cy * ref_h / res_y)
                entries.append({"component": comp, "anchor": [ax, ay]})
                log.info("  Mask anchor [%s] %s: (%d, %d) [%d px]",
                         ctx["preset_key"], comp, ax, ay, visible)
                continue

        # ── Method 2: fallback — world_to_camera_view ────────────────────
        anchor = _fallback_projection(comp, item, cam, scene, ref_w, ref_h)
        entries.append(anchor)

    return entries


def _load_index_mask(exr_dir, res_x, res_y):
    """Load the index EXR written by the compositor, return a 2D numpy array.

    Returns None if the EXR is missing or unreadable.
    Pixel order is top-left origin (standard image coordinates).
    """
    exr_files = sorted(glob.glob(os.path.join(exr_dir, "idx_*.exr")))
    if not exr_files:
        log.warning("Index EXR not found in %s — will use fallback projection", exr_dir)
        return None

    exr_path = exr_files[0]
    idx_img = None
    try:
        idx_img = bpy.data.images.load(exr_path)
        pixels = np.array(idx_img.pixels[:], dtype=np.float32)
        # Blender loads EXR as RGBA (4 channels); R channel = Object Index value
        mask = pixels.reshape(-1, 4)[:, 0].reshape(res_y, res_x)
        # Blender pixel storage: bottom-left origin → flip to top-left
        mask = np.flipud(mask)
        return mask
    except Exception as e:
        log.warning("Failed to read index EXR %s: %s", exr_path, e)
        return None
    finally:
        if idx_img is not None:
            try:
                bpy.data.images.remove(idx_img)
            except Exception:
                pass


def _fallback_projection(comp, item, cam, scene, ref_w, ref_h):
    """Project obj.location via world_to_camera_view (legacy method)."""
    import bpy_extras.object_utils as _bou

    obj = _find_object(comp)
    if obj and cam:
        co_2d = _bou.world_to_camera_view(scene, cam, obj.location)
        ax = int(co_2d.x * ref_w)
        ay = int((1.0 - co_2d.y) * ref_h)
        log.info("  Fallback anchor [%s]: (%d, %d)", comp, ax, ay)
        return {"component": comp, "anchor": [ax, ay], "fallback": True}

    # Last resort: use whatever is in render_config.json
    log.warning("  No anchor source for %s — using config default", comp)
    return {"component": comp, "anchor": item.get("anchor", [0, 0])}


def _write_sidecar(preset_key, png_path, entries):
    """Write sidecar JSON next to the rendered PNG."""
    sidecar = {"view": preset_key, "labels": entries}
    stem = os.path.splitext(png_path)[0]
    sidecar_path = stem + "_labels.json"
    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(sidecar, f, indent=2)
    log.info("  Sidecar written: %s (%d entries)", sidecar_path, len(entries))


def _cleanup(ctx):
    """Remove injected compositor nodes and restore all Blender state."""
    scene = bpy.context.scene
    vl = bpy.context.view_layer
    tree = scene.node_tree

    # Remove injected OutputFile node and its dangling links
    if tree:
        node_name = ctx.get("out_node_name", "")
        node = tree.nodes.get(node_name)
        if node:
            # Remove links TO this node first (prevents orphaned link references)
            for link in list(tree.links):
                if link.to_node == node:
                    tree.links.remove(link)
            tree.nodes.remove(node)

    # Restore scene.use_nodes
    scene.use_nodes = ctx["orig_use_nodes"]

    # Restore view_layer pass setting
    vl.use_pass_object_index = ctx["orig_use_pass"]

    # Restore original pass_index on objects (keyed by name for GC safety)
    for obj_name, orig_idx in ctx.get("orig_pass_indices", {}).items():
        obj = bpy.data.objects.get(obj_name)
        if obj:
            obj.pass_index = orig_idx

    # Clean up temp EXR directory
    exr_dir = ctx.get("exr_dir")
    if exr_dir and os.path.isdir(exr_dir):
        shutil.rmtree(exr_dir, ignore_errors=True)
