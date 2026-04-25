"""
Top-Level Assembly — 检测方法与信号处理 (DET-000)

Auto-generated scaffold by codegen/gen_assembly.py
Source: D:\Work\cad-spec-gen\cad\detection\CAD_SPEC.md
Generated: 2026-04-24 22:25

Coordinate system:
- Origin at assembly geometric center
- Z-up, X-right

Assembly hierarchy:
"""

import cadquery as cq
import math
import os
import params  # noqa: F401


def _station_transform(part, angle: float, tx: float, ty: float, tz: float):
    """Apply station rotation + translation."""
    part = part.rotate((0, 0, 0), (0, 0, 1), angle)
    part = part.translate((tx, ty, tz))
    return part


def make_assembly() -> cq.Assembly:
    """Build CadQuery Assembly with split sub-components."""

    assy = cq.Assembly()

    # ── Colors (custom parts) ──
    C_DARK = cq.Color(0.15, 0.15, 0.15)
    C_SILVER = cq.Color(0.8, 0.8, 0.82)
    C_AMBER = cq.Color(0.85, 0.65, 0.13)
    C_BLUE = cq.Color(0.35, 0.55, 0.75)
    C_GREEN = cq.Color(0.15, 0.5, 0.25)
    C_BRONZE = cq.Color(0.7, 0.42, 0.2)
    C_PURPLE = cq.Color(0.5, 0.18, 0.65)
    C_RUBBER = cq.Color(0.1, 0.1, 0.1)

    # ── Colors (standard/purchased parts) ──

    return assy


def export_assembly(output_dir: str, glb: bool = True) -> str:
    """Build and export the full assembly STEP (and optionally GLB).

    The GLB is post-processed by `cad_pipeline.py build` to collapse
    CadQuery's per-face mesh split into per-part meshes — see
    `codegen/consolidate_glb.py`.
    """
    assy = make_assembly()
    path = os.path.join(output_dir, "DET-000_assembly.step")
    assy.save(path, "STEP")
    print(f"Exported: {path}")
    if glb:
        glb_path = os.path.join(output_dir, "DET-000_assembly.glb")
        assy.save(glb_path, "GLTF")
        print(f"Exported: {glb_path}")
    return path


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    export_assembly(out)
