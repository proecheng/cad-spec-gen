"""
codegen/consolidate_glb.py — Post-process a CadQuery-exported GLB to
collapse per-face mesh components into per-part meshes.

## Why this exists

CadQuery's `cq.Assembly.save("file.glb", "GLTF")` walks each part's OCCT
topology and emits **one glTF Mesh node per Face**. A part with 100 faces
becomes 100 sibling mesh nodes named like:

    EE-001-01       (the first face — usually a degenerate small one)
    EE-001-01_1
    EE-001-01_2
    ...
    EE-001-01_99

Any downstream tool that reads the GLB and computes the bbox of one
component (e.g. trimesh `scene.geometry["EE-001-01"].bounds`) gets the
bbox of just one face, not the entire part. For a 4-arm flange this can
mean a 6×0×8 mm parent bbox instead of the actual 171×171×25 mm.

This module loads the GLB, groups sibling components by their name
prefix, concatenates the underlying meshes, and writes out a new GLB
where each part is a single Mesh node with the canonical part name.

The merge is **lossless**: vertex positions, normals, and face
connectivity are preserved exactly. Only the per-face split is undone.

## Trimesh dependency

`consolidate_glb_file()` is a graceful no-op when `trimesh` is not
installed — it logs a warning and returns False. This keeps the helper
truly optional and lets it slot into build pipelines that may run on
machines without the extra dependency.

## Usage

    from codegen.consolidate_glb import consolidate_glb_file
    ok = consolidate_glb_file("EE-000_assembly.glb")
    if ok:
        print("Consolidated; per-part bboxes are now correct")

Or from the CLI::

    python -m codegen.consolidate_glb path/to/assembly.glb
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Optional


__all__ = [
    "consolidate_glb_file",
    "group_meshes_by_prefix",
    "TRIMESH_AVAILABLE",
]


# Probe trimesh availability once at import time. The flag lets callers
# decide whether to bother calling consolidate_glb_file() at all without
# triggering an import error in environments where trimesh is missing.
try:
    import trimesh  # noqa: F401
    TRIMESH_AVAILABLE = True
except ImportError:
    TRIMESH_AVAILABLE = False


# Match a CadQuery-emitted face suffix at the end of a component name:
#   "EE-001-01_42" → prefix "EE-001-01"
#   "EE-001-01"    → prefix "EE-001-01" (no suffix)
# The suffix is always `_<digits>` and only at the end.
_FACE_SUFFIX_RE = re.compile(r"_\d+$")


def group_meshes_by_prefix(geometry: dict) -> dict:
    """Group a flat dict of mesh nodes by their part_no prefix.

    Args:
        geometry: ``trimesh.Scene.geometry`` dict mapping name → Trimesh.

    Returns:
        ``{prefix: [(name, mesh), ...]}`` where each prefix is the
        canonical part name (with the ``_<digit>`` face suffix stripped).
        The list inside each group is sorted by name so the merge is
        deterministic across runs.
    """
    groups: dict = {}
    for name, mesh in geometry.items():
        prefix = _FACE_SUFFIX_RE.sub("", name)
        groups.setdefault(prefix, []).append((name, mesh))
    for prefix in groups:
        groups[prefix].sort(key=lambda item: item[0])
    return groups


def consolidate_glb_file(
    glb_path: str,
    output_path: Optional[str] = None,
    logger=print,
) -> bool:
    """Read a GLB, merge per-face mesh components into per-part meshes,
    and write the result back.

    Args:
        glb_path: Path to the input GLB. Must exist.
        output_path: Where to write the consolidated GLB. Defaults to
            overwriting ``glb_path`` in place.
        logger: Callable used for status / warning lines. Defaults to
            ``print``; pass a no-op lambda to silence the helper.

    Returns:
        True if the GLB was rewritten with consolidated geometry. False
        if trimesh is unavailable, the input is missing, or the load /
        save round-trip fails. Never raises.
    """
    if not TRIMESH_AVAILABLE:
        logger("[consolidate_glb] trimesh not installed — skipping "
               "(pip install trimesh to enable)")
        return False

    if not os.path.isfile(glb_path):
        logger(f"[consolidate_glb] input not found: {glb_path}")
        return False

    import trimesh
    import trimesh.util as tutil

    try:
        scene = trimesh.load(glb_path, force="scene")
    except Exception as e:
        logger(f"[consolidate_glb] failed to load {glb_path}: {e}")
        return False

    if not hasattr(scene, "geometry") or not scene.geometry:
        logger(f"[consolidate_glb] {glb_path} has no geometry — nothing to do")
        return False

    original_count = len(scene.geometry)
    groups = group_meshes_by_prefix(scene.geometry)

    if len(groups) == original_count:
        logger(f"[consolidate_glb] {glb_path}: already consolidated "
               f"({original_count} parts, no per-face split detected)")
        return False

    # Build a fresh scene where each prefix becomes one Trimesh
    new_scene = trimesh.Scene()
    for prefix, items in sorted(groups.items()):
        meshes = [m for _, m in items]
        if len(meshes) == 1:
            merged = meshes[0]
        else:
            try:
                merged = tutil.concatenate(meshes)
            except Exception as e:
                logger(f"[consolidate_glb] concat failed for {prefix}: {e} "
                       f"— keeping per-face split for this part")
                # Re-add original sub-meshes under their original names
                # so we don't lose data on the failure path
                for sub_name, sub_mesh in items:
                    new_scene.add_geometry(sub_mesh, geom_name=sub_name)
                continue
        new_scene.add_geometry(merged, geom_name=prefix)

    target = output_path or glb_path
    try:
        new_scene.export(target)
    except Exception as e:
        logger(f"[consolidate_glb] failed to write {target}: {e}")
        return False

    new_count = len(new_scene.geometry)
    logger(f"[consolidate_glb] {glb_path}: {original_count} components → "
           f"{new_count} consolidated parts")
    return True


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    glb = argv[0]
    out = argv[1] if len(argv) > 1 else None
    ok = consolidate_glb_file(glb, out)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
