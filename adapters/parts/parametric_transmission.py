from __future__ import annotations

import math

import cadquery as cq


def _positive_float(value: float, *, name: str) -> float:
    out = float(value)
    if out <= 0:
        raise ValueError(f"{name} must be positive")
    return out


def _non_negative_float(value: float, *, name: str) -> float:
    out = float(value)
    if out < 0:
        raise ValueError(f"{name} must be non-negative")
    return out


def _cylinder(diameter_mm: float, height_mm: float, z_mm: float) -> cq.Shape:
    return (
        cq.Workplane("XY")
        .workplane(offset=z_mm)
        .circle(diameter_mm / 2.0)
        .extrude(height_mm)
        .val()
    )


def _helical_rib_solids(
    *,
    outer_diameter_mm: float,
    root_diameter_mm: float,
    pitch_mm: float,
    thread_length_mm: float,
    start_z_mm: float,
    starts: int,
) -> list[cq.Shape]:
    """Return segmented helical ribs without boolean-fusing them away."""
    if thread_length_mm <= 0:
        return []

    root_r = root_diameter_mm / 2.0
    outer_r = outer_diameter_mm / 2.0
    rib_depth = max(0.2, outer_r - root_r)
    rib_width = max(0.35, pitch_mm * 0.28)
    rib_height = max(0.35, pitch_mm * 0.18)
    segments_per_turn = 8
    turns = max(1, int(round(thread_length_mm / pitch_mm)))
    total_segments = max(segments_per_turn, turns * segments_per_turn)
    solid_starts = max(1, int(starts))
    solids: list[cq.Shape] = []

    for start in range(solid_starts):
        phase = start * 360.0 / solid_starts
        for index in range(total_segments):
            z_mm = start_z_mm + min(
                max(0.0, thread_length_mm - rib_height),
                index * pitch_mm / segments_per_turn,
            )
            angle = phase + index * 360.0 / segments_per_turn
            radial_center = root_r + rib_depth / 2.0
            rib = (
                cq.Workplane("XY")
                .box(rib_depth, rib_width, rib_height, centered=(True, True, False))
                .translate((radial_center, 0, z_mm))
                .rotate((0, 0, 0), (0, 0, 1), angle)
                .val()
            )
            solids.append(rib)
    return solids


def _thread_cue_ring_solids(
    *,
    outer_diameter_mm: float,
    root_diameter_mm: float,
    pitch_mm: float,
    thread_length_mm: float,
    start_z_mm: float,
) -> list[cq.Shape]:
    if thread_length_mm <= 0:
        return []

    ring_height = min(max(0.25, pitch_mm * 0.12), max(0.25, thread_length_mm))
    count = max(1, int(math.floor(thread_length_mm / max(0.01, pitch_mm))))
    solids: list[cq.Shape] = []
    for idx in range(count + 1):
        z_mm = start_z_mm + min(
            max(0.0, thread_length_mm - ring_height),
            idx * pitch_mm,
        )
        ring = (
            cq.Workplane("XY")
            .workplane(offset=z_mm)
            .circle(outer_diameter_mm / 2.0)
            .circle(root_diameter_mm / 2.0)
            .extrude(ring_height)
            .val()
        )
        solids.append(ring)
    return solids


def make_trapezoidal_lead_screw(
    *,
    outer_diameter_mm: float,
    pitch_mm: float,
    total_length_mm: float,
    thread_length_mm: float | None = None,
    lower_shaft_diameter_mm: float | None = None,
    lower_shaft_length_mm: float = 0.0,
    upper_shaft_diameter_mm: float | None = None,
    upper_shaft_length_mm: float = 0.0,
    root_diameter_mm: float | None = None,
    starts: int = 1,
) -> cq.Workplane:
    """Build a render-grade trapezoidal lead screw.

    The result is centered on XY with Z=0 at the lower tip. The thread cue is
    intended for rendering and recognition, not manufacturing inspection.
    """
    outer_d = _positive_float(outer_diameter_mm, name="outer_diameter_mm")
    pitch = _positive_float(pitch_mm, name="pitch_mm")
    total_l = _positive_float(total_length_mm, name="total_length_mm")
    lower_l = _non_negative_float(lower_shaft_length_mm, name="lower_shaft_length_mm")
    upper_l = _non_negative_float(upper_shaft_length_mm, name="upper_shaft_length_mm")

    available_thread_l = max(0.0, total_l - lower_l - upper_l)
    if thread_length_mm is None:
        thread_l = available_thread_l
    else:
        thread_l = _non_negative_float(thread_length_mm, name="thread_length_mm")
        thread_l = min(thread_l, available_thread_l)

    root_d = (
        _positive_float(root_diameter_mm, name="root_diameter_mm")
        if root_diameter_mm is not None
        else max(outer_d - pitch * 0.55, outer_d * 0.72)
    )
    root_d = min(root_d, outer_d)
    lower_d = (
        _positive_float(lower_shaft_diameter_mm, name="lower_shaft_diameter_mm")
        if lower_shaft_diameter_mm is not None
        else root_d
    )
    upper_d = (
        _positive_float(upper_shaft_diameter_mm, name="upper_shaft_diameter_mm")
        if upper_shaft_diameter_mm is not None
        else root_d
    )
    lower_d = min(lower_d, outer_d)
    upper_d = min(upper_d, outer_d)

    shapes: list[cq.Shape] = [
        cq.Workplane("XY").circle(min(root_d, lower_d, upper_d) / 2.0).extrude(0.001).val()
    ]
    if lower_l:
        shapes.append(_cylinder(lower_d, lower_l, 0.0))

    if thread_l:
        shapes.append(_cylinder(root_d, thread_l, lower_l))
        shapes.extend(
            _thread_cue_ring_solids(
                outer_diameter_mm=outer_d,
                root_diameter_mm=root_d,
                pitch_mm=pitch,
                thread_length_mm=thread_l,
                start_z_mm=lower_l,
            )
        )
        shapes.extend(
            _helical_rib_solids(
                outer_diameter_mm=outer_d,
                root_diameter_mm=root_d,
                pitch_mm=pitch,
                thread_length_mm=thread_l,
                start_z_mm=lower_l,
                starts=starts,
            )
        )

    upper_start = lower_l + thread_l
    upper_height = max(0.0, total_l - upper_start)
    if upper_height:
        shapes.append(_cylinder(upper_d, upper_height, upper_start))

    compound = cq.Compound.makeCompound(shapes)
    return cq.Workplane("XY").newObject([compound])
