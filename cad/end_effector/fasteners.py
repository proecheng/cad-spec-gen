"""
Standard Fasteners — Parametric bolts, washers, and LEMO connectors.

Used by assembly.py to add visible fastener detail in GLB for rendering.
All dimensions per ISO 4762 (hex socket head cap screw).
"""

import cadquery as cq
import math


# ═══════════════════════════════════════════════════════════════════
# ISO 4762 Hex Socket Head Cap Screw
# ═══════════════════════════════════════════════════════════════════

# Head dimensions by nominal size {M: (head_dia, head_height, hex_af)}
_ISO4762 = {
    2:  (3.8,  2.0,  1.5),
    2.5:(4.5,  2.5,  2.0),
    3:  (5.5,  3.0,  2.5),
    4:  (7.0,  4.0,  3.0),
    5:  (8.5,  5.0,  4.0),
    6:  (10.0, 6.0,  5.0),
    8:  (13.0, 8.0,  6.0),
}


def make_hex_socket_bolt(m: float, length: float) -> cq.Workplane:
    """ISO 4762 hex socket head cap screw.

    Args:
        m: Nominal size (e.g. 3 for M3)
        length: Shank length in mm (excluding head)

    Returns:
        CadQuery Workplane. Origin at head top center, shank extends in -Z.
    """
    hd, hh, hex_af = _ISO4762.get(int(m), (m * 1.8, m, m * 0.8))

    # Head cylinder
    head = cq.Workplane("XY").circle(hd / 2.0).extrude(-hh)

    # Hex socket recess (approximate as hexagonal prism)
    hex_r = hex_af / (2.0 * math.cos(math.radians(30)))  # circumscribed radius
    socket = (
        cq.Workplane("XY")
        .polygon(6, hex_r * 2)
        .extrude(-hh * 0.7)
    )
    head = head.cut(socket)

    # Shank
    shank = (
        cq.Workplane("XY")
        .workplane(offset=-hh)
        .circle(m / 2.0)
        .extrude(-length)
    )
    bolt = head.union(shank)
    return bolt


# ═══════════════════════════════════════════════════════════════════
# Bolt ring helper — place N bolts on a PCD circle
# ═══════════════════════════════════════════════════════════════════

def make_bolt_ring(m: float, length: float, pcd: float, n: int,
                   start_angle: float = 0.0) -> cq.Workplane:
    """Create N bolts equally spaced on a PCD circle.

    Args:
        m: Bolt nominal size
        length: Shank length
        pcd: Pitch circle diameter
        n: Number of bolts
        start_angle: Starting angle offset in degrees

    Returns:
        Union of all bolts. Origin at PCD center, heads at Z=0.
    """
    result = None
    for i in range(n):
        angle = math.radians(start_angle + i * 360.0 / n)
        bx = (pcd / 2.0) * math.cos(angle)
        by = (pcd / 2.0) * math.sin(angle)
        bolt = make_hex_socket_bolt(m, length).translate((bx, by, 0))
        if result is None:
            result = bolt
        else:
            result = result.union(bolt)
    return result


def make_bolt_square(m: float, length: float, pcd: float) -> cq.Workplane:
    """Create 4 bolts on a square pattern (like station mount).

    Args:
        m: Bolt nominal size
        length: Shank length
        pcd: Square side length between bolt centers

    Returns:
        Union of 4 bolts at corners.
    """
    half = pcd / 2.0
    result = None
    for dx, dy in [(half, half), (half, -half), (-half, half), (-half, -half)]:
        bolt = make_hex_socket_bolt(m, length).translate((dx, dy, 0))
        if result is None:
            result = bolt
        else:
            result = result.union(bolt)
    return result


# ═══════════════════════════════════════════════════════════════════
# LEMO 0B connector (simplified visual)
# ═══════════════════════════════════════════════════════════════════

def make_lemo_0b(bore_dia: float = 9.4) -> cq.Workplane:
    """LEMO 0B connector simplified visual model.

    Origin at panel face center, plug extends in +Z.
    """
    # Panel nut (hexagonal flange)
    nut_af = bore_dia + 4.0  # across-flats
    hex_r = nut_af / (2.0 * math.cos(math.radians(30)))
    nut = cq.Workplane("XY").polygon(6, hex_r * 2).extrude(3.0)

    # Connector body
    body = (
        cq.Workplane("XY")
        .workplane(offset=3.0)
        .circle(bore_dia / 2.0 - 0.3)
        .extrude(12.0)
    )
    nut = nut.union(body)

    # Cable strain relief
    relief = (
        cq.Workplane("XY")
        .workplane(offset=15.0)
        .circle(3.0)
        .extrude(8.0)
    )
    nut = nut.union(relief)
    return nut


# ═══════════════════════════════════════════════════════════════════
# Compression spring (visual)
# ═══════════════════════════════════════════════════════════════════

def make_compression_spring(od: float, wire_dia: float, free_length: float,
                            n_coils: int = 8) -> cq.Workplane:
    """Helical compression spring (visual approximation).

    Uses stacked tori to approximate a helix (CadQuery helix is complex).
    Origin at bottom center, spring extends in +Z.
    """
    mean_r = (od - wire_dia) / 2.0
    pitch = free_length / n_coils

    # Build as stacked torus segments
    result = None
    for i in range(n_coils):
        z = i * pitch + pitch / 2.0
        torus = (
            cq.Workplane("XY")
            .workplane(offset=z)
            .circle(mean_r + wire_dia / 2.0)
            .circle(mean_r - wire_dia / 2.0)
            .extrude(wire_dia)
        )
        if result is None:
            result = torus
        else:
            result = result.union(torus)
    return result


def make_helix_spring(od: float, wire_dia: float, free_length: float,
                      n_coils: int = 6) -> cq.Workplane:
    """Helical spring using Wire.makeHelix + sweep.

    Creates a true helix coil spring. Falls back to stacked tori
    (make_compression_spring) if the CadQuery helix API is unavailable.

    Args:
        od: Outer diameter (mm)
        wire_dia: Wire diameter (mm)
        free_length: Free length (mm)
        n_coils: Number of active coils
    Returns:
        CadQuery Workplane. Origin at bottom center, spring extends in +Z.
    """
    mean_r = (od - wire_dia) / 2.0
    pitch = free_length / n_coils

    try:
        wire = cq.Wire.makeHelix(pitch, free_length, mean_r)
        helix_path = cq.Workplane("XY").newObject([wire])
        spring = (
            cq.Workplane("XZ")
            .center(mean_r, 0)
            .circle(wire_dia / 2.0)
            .sweep(helix_path, isFrenet=True)
        )
        return spring
    except Exception:
        # Fallback to stacked tori if makeHelix/sweep fails
        return make_compression_spring(od, wire_dia, free_length, n_coils)


# ═══════════════════════════════════════════════════════════════════
# Belleville (disc/conical) spring washer — DIN 2093
# ═══════════════════════════════════════════════════════════════════

def make_belleville_washer(od: float, id: float, thick: float) -> cq.Workplane:
    """DIN 2093 conical spring washer (simplified flat annulus).

    Args:
        od: Outer diameter (e.g. 12.5 for A6)
        id: Inner diameter (e.g. 6.2)
        thick: Material thickness
    Returns:
        CadQuery Workplane. Origin at bottom center.
    """
    washer = (
        cq.Workplane("XY")
        .circle(od / 2.0)
        .circle(id / 2.0)
        .extrude(thick)
    )
    return washer


# ═══════════════════════════════════════════════════════════════════
# ZIF connector (visual block)
# ═══════════════════════════════════════════════════════════════════

def make_zif_connector(length: float = 15.0, width: float = 10.0,
                       height: float = 3.0) -> cq.Workplane:
    """ZIF FFC connector simplified visual model.

    Origin at bottom center, connector extends in +Z.
    """
    body = (
        cq.Workplane("XY")
        .rect(length, width)
        .extrude(height)
    )
    # Actuator lever (thin flap on top)
    lever = (
        cq.Workplane("XY")
        .workplane(offset=height)
        .center(0, -width / 4.0)
        .rect(length * 0.9, width * 0.3)
        .extrude(0.5)
    )
    return body.union(lever)


# ═══════════════════════════════════════════════════════════════════
# Locating pin (dowel pin)
# ═══════════════════════════════════════════════════════════════════

def make_locating_pin(dia: float, length: float) -> cq.Workplane:
    """Cylindrical dowel / locating pin.

    Origin at top center, pin extends in -Z.
    """
    pin = cq.Workplane("XY").circle(dia / 2.0).extrude(-length)
    return pin


# ═══════════════════════════════════════════════════════════════════
# FFC flat flexible cable (simplified ribbon)
# ═══════════════════════════════════════════════════════════════════

def make_ffc_ribbon(width: float, thick: float,
                    length: float) -> cq.Workplane:
    """FFC ribbon cable as a flat rectangular strip.

    Origin at one end center, cable extends in +X.
    """
    ribbon = (
        cq.Workplane("XY")
        .rect(length, width, centered=False)
        .extrude(thick)
        .translate((-length / 2.0, -width / 2.0, -thick / 2.0))
    )
    return ribbon


# ═══════════════════════════════════════════════════════════════════
# Igus E2 micro energy chain (simplified segmented tube)
# ═══════════════════════════════════════════════════════════════════

def make_igus_chain(inner_dia: float, outer_dia: float,
                    length: float, segment_len: float = 5.0) -> cq.Workplane:
    """Igus E2 micro cable chain — simplified as segmented annuli.

    Origin at one end center, chain extends in +Z.
    """
    n_seg = max(1, int(length / segment_len))
    gap = 0.5  # gap between segments
    result = None
    for i in range(n_seg):
        z = i * segment_len
        seg = (
            cq.Workplane("XY")
            .workplane(offset=z)
            .circle(outer_dia / 2.0)
            .circle(inner_dia / 2.0)
            .extrude(segment_len - gap)
        )
        if result is None:
            result = seg
        else:
            result = result.union(seg)
    return result


# ═══════════════════════════════════════════════════════════════════
# SMA 50Ω bulkhead connector
# ═══════════════════════════════════════════════════════════════════

def make_sma_connector(bore_dia: float = 6.5,
                       body_len: float = 12.0) -> cq.Workplane:
    """SMA bulkhead RF connector simplified model.

    Origin at panel face center, connector extends in +Z.
    """
    # Panel nut (hex)
    nut_af = 8.0
    hex_r = nut_af / (2.0 * math.cos(math.radians(30)))
    nut = cq.Workplane("XY").polygon(6, hex_r * 2).extrude(2.5)

    # Body cylinder
    body = (
        cq.Workplane("XY")
        .workplane(offset=2.5)
        .circle(bore_dia / 2.0 - 0.3)
        .extrude(body_len - 2.5)
    )
    nut = nut.union(body)

    # Center pin
    pin = (
        cq.Workplane("XY")
        .workplane(offset=body_len)
        .circle(0.65)
        .extrude(3.0)
    )
    return nut.union(pin)


# ═══════════════════════════════════════════════════════════════════
# M12 circular connector (diagnostic port)
# ═══════════════════════════════════════════════════════════════════

def make_m12_connector(bore_dia: float = 12.0,
                       length: float = 25.0) -> cq.Workplane:
    """M12 A-coded circular connector simplified model.

    Origin at panel face center, connector extends in +Z.
    """
    # Knurled nut (simplified as cylinder with grooves)
    nut = cq.Workplane("XY").circle(bore_dia / 2.0 + 1.5).extrude(8.0)

    # Body
    body = (
        cq.Workplane("XY")
        .workplane(offset=8.0)
        .circle(bore_dia / 2.0)
        .extrude(length - 8.0)
    )
    nut = nut.union(body)

    # Panel flange
    flange = (
        cq.Workplane("XY")
        .workplane(offset=-2.0)
        .circle(bore_dia / 2.0 + 3.0)
        .extrude(2.0)
    )
    return nut.union(flange)


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)

    # Test: M3×8 bolt
    bolt = make_hex_socket_bolt(3, 8)
    cq.exporters.export(bolt, os.path.join(out, "test_M3x8_bolt.step"))
    print("Exported test bolt")

    # Test: 6-bolt ring (PEEK pattern)
    ring = make_bolt_ring(3, 10, 70.0, 6)
    cq.exporters.export(ring, os.path.join(out, "test_bolt_ring.step"))
    print("Exported bolt ring")
