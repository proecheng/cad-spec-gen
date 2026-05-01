"""Render import regression: consolidated CadQuery GLTF must stay Z-up.

CadQuery/OCC exports GLTF using a convention that Blender's glTF importer maps
correctly when the original CadQuery node transforms are preserved.  The
post-build consolidator used to rebuild a fresh trimesh Scene and drop that
orientation contract.  Blender then imported the consolidated file as X, -Z, Y,
so a CAD model whose height is along Z rendered lying on its side.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).parent.parent
def _blender_path() -> str | None:
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from cad_paths import get_blender_path

    return get_blender_path()


@pytest.mark.blender
@pytest.mark.skipif(_blender_path() is None, reason="Blender not found")
def test_consolidated_glb_preserves_cadquery_z_up_in_blender(tmp_path):
    """A consolidated 20x30x40 box must import as 20x30x40, not 20x40x30."""
    cq = pytest.importorskip("cadquery")
    from codegen.consolidate_glb import consolidate_glb_file

    step = tmp_path / "z_up_box.step"
    glb = tmp_path / "z_up_box.glb"
    cq.exporters.export(
        cq.Workplane("XY").box(20, 30, 40, centered=(True, True, False)),
        str(step),
    )
    imported_step = cq.importers.importStep(str(step))

    assy = cq.Assembly()
    assy.add(
        imported_step.translate((0, 0, 100)),
        name="TALL-Z",
    )
    assy.save(str(glb), "GLTF")
    assert consolidate_glb_file(str(glb), logger=lambda _msg: None) is True

    expr = (
        "import bpy; "
        "from mathutils import Vector; "
        "bpy.ops.object.delete(); "
        f"bpy.ops.import_scene.gltf(filepath={str(glb)!r}); "
        "dims=[]; "
        "\nfor obj in bpy.context.scene.objects:\n"
        "    if obj.type == 'MESH' and obj.name.startswith('TALL-Z'):\n"
        "        xs=[]; ys=[]; zs=[]\n"
        "        for corner in obj.bound_box:\n"
        "            w = obj.matrix_world @ Vector(corner)\n"
        "            xs.append(w.x); ys.append(w.y); zs.append(w.z)\n"
        "        dims=[max(xs)-min(xs), max(ys)-min(ys), max(zs)-min(zs)]\n"
        "        break\n"
        "print('DIMS=' + ','.join(f'{d:.3f}' for d in dims)); "
    )

    result = subprocess.run(
        [_blender_path(), "--background", "--python-expr", expr],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )

    dims_line = next(
        (line for line in result.stdout.splitlines() if line.startswith("DIMS=")),
        None,
    )
    assert dims_line is not None, (
        f"stdout:\n{result.stdout[-2000:]}\n\nstderr:\n{result.stderr[-2000:]}"
    )
    dims = tuple(float(v) for v in dims_line.split("=", 1)[1].split(","))
    assert dims == pytest.approx((20.0, 30.0, 40.0), abs=0.05)
