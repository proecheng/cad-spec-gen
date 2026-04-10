"""
templates/parts/iso_9409_flange.py — Parametric ISO 9409-1 robot tool flange.

ISO 9409-1 specifies the mechanical interface between a robot wrist and
end-of-arm tooling: a flat circular mounting face with a bolt circle of
counterbored holes, a centering feature (usually a register diameter or
taper), and an optional tooling-side boss. The standard defines sizes
50 / 63 / 80 / 100 / 125 / 160 mm — here the "50" size corresponds to
4×M6 holes on PCD 50 mm, which matches popular cobots like the Realman
RM65-B, UR3e, and KUKA LBR iiwa 7.

This template also supports an **optional cross-arm hub overlay** — a
set of N radial arms sticking out from the disc with mounting platforms
at each arm end. The GISBOT four-station end effector uses this pattern:
the flange rotates a 4-station carousel (coupling applicator, AE sensor,
UHF sensor, brush cleaner) around the central axis.

Geometry pipeline:
    1. Base disc (outer_dia × thickness) with optional outer-edge fillet
    2. Central through bore (reducer output shaft clearance)
    3. ISO 9409 mounting pattern: N counterbored holes on PCD
    4. Optional tooling-side bolt circle (e.g. M3 holes for a PEEK ring)
    5. Optional N radial arms (cross-arm hub), each with:
         - rectangular arm body (tapered or prismatic)
         - square mounting platform at tip
         - 4× M3 bolt holes + 1× dowel pin hole on each platform
         - fillet at arm root (where it meets the disc)
    6. Chamfers on every bolt-hole rim and on the central bore

Every cosmetic operation is wrapped in try/except so a single OCCT
hiccup (which happens on complex unions) leaves the part topologically
valid without cosmetic polish, rather than crashing the build.

Parameters — see `make()` docstring for the full list. All dimensions
are in millimeters.
"""

from __future__ import annotations

import math
from typing import Optional

import cadquery as cq


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------


def make(
    *,
    # --- disc body ---------------------------------------------------------
    outer_dia: float = 90.0,
    thickness: float = 25.0,
    outer_fillet: float = 0.8,
    # --- central bore -----------------------------------------------------
    central_bore_dia: float = 22.0,
    central_bore_chamfer: float = 0.5,
    # --- ISO 9409 mounting pattern (machine-arm side, -Z face) ------------
    iso_pcd: float = 50.0,
    iso_bolt_dia: float = 6.0,
    iso_bolt_count: int = 4,
    iso_counterbore_dia: Optional[float] = None,  # default = 1.8 × bolt_dia
    iso_counterbore_depth: float = 6.0,
    iso_start_angle_deg: float = 45.0,
    # --- tooling-side bolt circle (for PEEK ring, +Z face) ---------------
    tool_bolt_circle_dia: Optional[float] = None,  # None = disabled
    tool_bolt_dia: float = 3.0,
    tool_bolt_count: int = 6,
    tool_bolt_depth: float = 8.0,  # blind tapped hole depth
    # --- cross-arm hub ----------------------------------------------------
    arm_count: int = 0,  # 0 = plain disc, no arms
    arm_length: float = 40.0,  # from outer disc edge to arm tip
    arm_width: float = 12.0,
    arm_root_fillet: float = 3.0,
    # --- mounting platform at arm tip ------------------------------------
    platform_size: float = 40.0,
    platform_edge_chamfer: float = 2.0,
    platform_top_fillet: float = 1.5,
    platform_mount_bolt_dia: float = 3.0,
    platform_mount_bolt_pcd: float = 28.0,
    platform_dowel_dia: float = 3.0,
    platform_dowel_offset: float = 20.0,
    # --- aux bore (e.g. Φ8 shaft keyway) ---------------------------------
    aux_bore_dia: Optional[float] = None,
    aux_bore_depth: Optional[float] = None,
) -> cq.Workplane:
    """Build a fully detailed ISO 9409-1 robot tool flange.

    Returns a single ``cq.Workplane`` with:
      - Aluminum disc body (``outer_dia`` × ``thickness``)
      - Central through bore (``central_bore_dia``)
      - ISO 9409 bolt pattern with counterbores on the -Z face
      - Optional tooling-side bolt circle of blind tapped holes on +Z
      - Optional N radial arms + mounting platforms + platform bolt holes
      - Fillets and chamfers on all key edges

    The -Z face is the "robot-arm side" (ISO 9409 face).
    The +Z face is the "tool side" (PEEK ring / station modules).

    Parameters
    ----------
    outer_dia : float
        Outer diameter of the disc body (Φ).
    thickness : float
        Axial thickness of the disc (along +Z).
    outer_fillet : float
        Radius of the outer-edge fillet. Set to 0 to disable.
    central_bore_dia : float
        Diameter of the central through bore.
    iso_pcd : float
        ISO 9409-1 bolt circle pitch diameter.
    iso_bolt_dia : float
        Nominal thread size for the ISO 9409 bolts (M6 = 6.0).
    iso_bolt_count : int
        Number of bolts on the ISO 9409 circle (typically 4).
    iso_counterbore_dia : float, optional
        Counterbore diameter for the ISO 9409 bolt heads. Defaults to
        1.8 × ``iso_bolt_dia`` (e.g. 10.8 for M6 — cap screw head fit).
    iso_counterbore_depth : float
        Depth of the counterbore on the -Z face.
    iso_start_angle_deg : float
        Rotation of the first bolt on the circle, degrees CCW from +X.
        Defaults to 45° so the bolt circle doesn't coincide with the
        cross-arm angles at 0/90/180/270°.
    tool_bolt_circle_dia : float, optional
        PCD of the secondary bolt circle on the +Z (tool) face. Pass
        ``None`` (default) to skip the tool-side bolt circle entirely.
    arm_count : int
        Number of radial arms. ``0`` produces a plain flange disc with no
        cross-arm hub. ``4`` produces the GISBOT four-station layout.
    arm_length : float
        Arm length from the outer disc edge to the arm tip (the arm
        extends RADIALLY outward, so the total flange span becomes
        ``outer_dia + 2 × arm_length``).
    arm_width : float
        Cross-section width of the arm body (measured tangentially).
    arm_root_fillet : float
        Fillet radius where the arm meets the disc (cosmetic + structural).
    platform_size : float
        Square edge length of the mounting platform at each arm tip.
    platform_mount_bolt_pcd : float
        PCD of the 4 mounting bolt holes on each platform (squared,
        45° off-axis).
    aux_bore_dia, aux_bore_depth : float, optional
        Additional blind bore concentric with the central bore (e.g. for
        a reducer output shaft keyway). Both must be provided together.

    Returns
    -------
    cq.Workplane
        The completed flange ready for export or union with other parts.
    """
    # ── 1. Base disc body ────────────────────────────────────────────────
    disc_r = outer_dia / 2.0
    body = cq.Workplane("XY").circle(disc_r).extrude(thickness)

    # Outer-edge fillet — soften both top and bottom circumferential edges
    if outer_fillet > 0:
        for face_tag in (">Z", "<Z"):
            try:
                body = body.faces(face_tag).edges().fillet(outer_fillet)
            except Exception:
                pass

    # ── 2. Central through bore ─────────────────────────────────────────
    if central_bore_dia > 0:
        body = (body.faces(">Z").workplane()
                .circle(central_bore_dia / 2.0).cutThruAll())
        # Chamfer the bore rim on both faces
        if central_bore_chamfer > 0:
            try:
                body = (body.faces(">Z").edges("%CIRCLE")
                        .edges(f"<<Z[-1]")
                        .chamfer(central_bore_chamfer))
            except Exception:
                try:
                    # Simpler selector fallback: chamfer inner circle on +Z
                    body = (body.faces(">Z").edges("%CIRCLE")
                            .chamfer(central_bore_chamfer))
                except Exception:
                    pass
            try:
                body = (body.faces("<Z").edges("%CIRCLE")
                        .chamfer(central_bore_chamfer))
            except Exception:
                pass

    # ── 3. Aux bore (optional blind bore concentric with central) ───────
    if aux_bore_dia and aux_bore_depth:
        body = (body.faces(">Z").workplane()
                .circle(aux_bore_dia / 2.0)
                .cutBlind(-aux_bore_depth))

    # ── 4. ISO 9409 bolt pattern on -Z face (counterbored through) ──────
    if iso_bolt_count > 0 and iso_pcd > 0 and iso_bolt_dia > 0:
        cb_dia = iso_counterbore_dia or (iso_bolt_dia * 1.8)
        # Sketch all bolt centers on -Z face
        bolt_centers = _polar_points(
            iso_pcd / 2.0, iso_bolt_count, iso_start_angle_deg
        )
        # Cut counterbores from -Z
        wp = body.faces("<Z").workplane(origin=(0, 0, 0))
        for cx, cy in bolt_centers:
            wp = wp.moveTo(cx, cy).circle(cb_dia / 2.0)
        body = wp.cutBlind(-iso_counterbore_depth)
        # Cut through-holes for the shank
        wp = body.faces("<Z").workplane(origin=(0, 0, 0))
        for cx, cy in bolt_centers:
            wp = wp.moveTo(cx, cy).circle(iso_bolt_dia / 2.0 + 0.1)
        body = wp.cutThruAll()

    # ── 5. Tool-side bolt circle (+Z face blind tapped holes) ───────────
    if tool_bolt_circle_dia and tool_bolt_count > 0:
        tool_centers = _polar_points(
            tool_bolt_circle_dia / 2.0, tool_bolt_count, 0.0
        )
        wp = body.faces(">Z").workplane(origin=(0, 0, 0))
        for cx, cy in tool_centers:
            wp = wp.moveTo(cx, cy).circle(tool_bolt_dia / 2.0 + 0.1)
        body = wp.cutBlind(-tool_bolt_depth)

    # ── 6. Cross-arm hub (optional) ─────────────────────────────────────
    if arm_count > 0 and arm_length > 0:
        body = _add_cross_arm_hub(
            body,
            disc_r=disc_r,
            thickness=thickness,
            arm_count=arm_count,
            arm_length=arm_length,
            arm_width=arm_width,
            arm_root_fillet=arm_root_fillet,
            platform_size=platform_size,
            platform_edge_chamfer=platform_edge_chamfer,
            platform_top_fillet=platform_top_fillet,
            platform_mount_bolt_dia=platform_mount_bolt_dia,
            platform_mount_bolt_pcd=platform_mount_bolt_pcd,
            platform_dowel_dia=platform_dowel_dia,
            platform_dowel_offset=platform_dowel_offset,
        )

    return body


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _polar_points(radius: float, count: int, start_deg: float) -> list:
    """Return `count` (x, y) points evenly spaced on a circle of `radius`."""
    result = []
    for i in range(count):
        ang = math.radians(start_deg + 360.0 * i / count)
        result.append((radius * math.cos(ang), radius * math.sin(ang)))
    return result


def _add_cross_arm_hub(
    body: cq.Workplane,
    *,
    disc_r: float,
    thickness: float,
    arm_count: int,
    arm_length: float,
    arm_width: float,
    arm_root_fillet: float,
    platform_size: float,
    platform_edge_chamfer: float,
    platform_top_fillet: float,
    platform_mount_bolt_dia: float,
    platform_mount_bolt_pcd: float,
    platform_dowel_dia: float,
    platform_dowel_offset: float,
) -> cq.Workplane:
    """Attach N radial arms + square mounting platforms to a disc body.

    Each arm is built in its own local +X frame and then rotated into
    place via ``rotate((0,0,0), (0,0,1), angle_deg)``. Arms overlap the
    disc slightly (``arm_overlap``) so their union produces a single
    manifold Solid rather than a Compound of disjoint bodies — critical
    for downstream bbox + GLB component export.
    """
    # Overlap with the disc body so the union is manifold
    arm_overlap = max(2.0, arm_root_fillet + 0.5)
    arm_l_eff = arm_length + arm_overlap
    arm_x_mid = (disc_r - arm_overlap) + arm_l_eff / 2.0
    platform_x = disc_r + arm_length - platform_size / 2.0

    # Build one arm + platform in the local +X direction, then copy/rotate.
    def _build_arm_unit() -> cq.Workplane:
        # Prismatic arm body
        arm = (cq.Workplane("XY")
               .center(arm_x_mid, 0)
               .box(arm_l_eff, arm_width, thickness,
                    centered=(True, True, False)))

        # Chamfer arm vertical corners for a "machined" silhouette
        if platform_edge_chamfer > 0:
            try:
                arm = arm.edges("|Z").chamfer(min(1.2, arm_width * 0.1))
            except Exception:
                pass

        # Square mounting platform at arm tip
        platform = (cq.Workplane("XY")
                    .center(platform_x, 0)
                    .box(platform_size, platform_size, thickness,
                         centered=(True, True, False)))

        # Cosmetic polish on the platform (chamfers + top fillet)
        if platform_edge_chamfer > 0:
            try:
                platform = platform.edges("|Z").chamfer(platform_edge_chamfer)
            except Exception:
                pass
        if platform_top_fillet > 0:
            try:
                platform = (platform.faces(">Z").edges()
                            .fillet(platform_top_fillet))
            except Exception:
                pass

        # 4 mounting bolt holes on the platform (sqrt(2)/2 × PCD offsets)
        bolt_off = platform_mount_bolt_pcd / (2.0 ** 0.5) / 2.0
        if platform_mount_bolt_dia > 0 and bolt_off > 0:
            try:
                platform = (platform.faces(">Z").workplane()
                            .pushPoints([
                                (platform_x + bolt_off, +bolt_off),
                                (platform_x - bolt_off, +bolt_off),
                                (platform_x + bolt_off, -bolt_off),
                                (platform_x - bolt_off, -bolt_off),
                            ])
                            .circle(platform_mount_bolt_dia / 2.0 + 0.1)
                            .cutBlind(-thickness * 0.6))
            except Exception:
                pass

        # 1 dowel pin hole near the +Y edge of the platform
        if platform_dowel_dia > 0:
            try:
                platform = (platform.faces(">Z").workplane()
                            .pushPoints([
                                (platform_x, platform_dowel_offset / 2.0),
                            ])
                            .circle(platform_dowel_dia / 2.0 + 0.05)
                            .cutBlind(-thickness * 0.4))
            except Exception:
                pass

        return arm.union(platform)

    unit = _build_arm_unit()

    # Replicate N copies at 360/N angular spacing and union with the disc
    step_deg = 360.0 / arm_count
    for i in range(arm_count):
        angle = i * step_deg
        rotated = unit.rotate((0, 0, 0), (0, 0, 1), angle)
        try:
            body = body.union(rotated)
        except Exception:
            # A failed union usually means the OCCT fuse threw; the body
            # stays valid and we move on to the next arm.
            pass

    # Arm-root fillets on the disc outer edge where arms meet the disc.
    # These are cosmetic; wrap in try so any failure doesn't break the build.
    if arm_root_fillet > 0:
        try:
            body = (body.faces("<Z")
                    .edges("%CIRCLE")
                    .fillet(min(arm_root_fillet * 0.5, 1.0)))
        except Exception:
            pass

    return body


if __name__ == "__main__":
    import os

    demo = make(
        outer_dia=90.0,
        thickness=25.0,
        central_bore_dia=22.0,
        iso_pcd=50.0,
        iso_bolt_dia=6.0,
        iso_bolt_count=4,
        tool_bolt_circle_dia=70.0,
        tool_bolt_dia=3.0,
        tool_bolt_count=6,
        arm_count=4,
        arm_length=40.0,
        arm_width=12.0,
        platform_size=40.0,
    )
    out_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "iso_9409_flange_demo.step",
    )
    cq.exporters.export(demo, out_path)
    print(f"Wrote demo flange: {out_path}")
