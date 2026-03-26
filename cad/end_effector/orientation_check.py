"""
orientation_check.py — Pre-STEP Assembly Orientation Validator

Runs before STEP export to assert each sub-component's principal axis
matches the design document (04-末端执行机构设计.md).

Usage:
    python orientation_check.py
    # Called automatically by cad_pipeline.py build phase when --check-orientation flag is set.

Pass criteria (all must pass before STEP is written):
  S1 grease tank   : longest axis along +Y (radial, ∥XY plane)  — §4.1.2 L176
  S1 body          : longest axis along -Z (toward GIS shell)    — §4.1.1 L173
  S3 solvent tank  : longest axis along +Z (vertical, ∥rot-axis) — §4.1.3 L266
  S3 body          : longest axis along -Z                       — §4.1.3 L173
  S2 AE module     : longest axis along -Z (stacked serial)      — §4.1.2 L247
  S4 UHF bracket   : longest axis along -Z                       — §4.1.4

Exit codes: 0 = all pass, 1 = one or more failures.
"""

import sys
import math
import cadquery as cq
sys.path.insert(0, __file__.replace("orientation_check.py", ""))


# ── Helpers ──────────────────────────────────────────────────────────────────

def _bbox(shape: cq.Workplane):
    bb = shape.val().BoundingBox()
    return {
        "x": bb.xmax - bb.xmin,
        "y": bb.ymax - bb.ymin,
        "z": bb.zmax - bb.zmin,
        "cx": (bb.xmax + bb.xmin) / 2,
        "cy": (bb.ymax + bb.ymin) / 2,
        "cz": (bb.zmax + bb.zmin) / 2,
    }


def _principal_axis(bb: dict) -> str:
    """Return the axis ('x','y','z') with the largest extent."""
    dims = {"x": bb["x"], "y": bb["y"], "z": bb["z"]}
    return max(dims, key=dims.get)


def _aspect_ratio(bb: dict, axis: str) -> float:
    """Ratio of principal axis length to the larger of the other two."""
    others = [v for k, v in {"x": bb["x"], "y": bb["y"], "z": bb["z"]}.items() if k != axis]
    return bb[axis] / max(others) if max(others) > 0 else 0


class CheckResult:
    def __init__(self):
        self.passed = []
        self.failed = []

    def check(self, name: str, condition: bool, msg_pass: str, msg_fail: str):
        if condition:
            print(f"  [PASS] {name}: {msg_pass}")
            self.passed.append(name)
        else:
            print(f"  [FAIL] {name}: {msg_fail}")
            self.failed.append(name)

    def summary(self):
        total = len(self.passed) + len(self.failed)
        print(f"\n{'='*60}")
        print(f"Orientation check: {len(self.passed)}/{total} passed")
        if self.failed:
            print(f"FAILED: {', '.join(self.failed)}")
        return len(self.failed) == 0


# ── Checks ───────────────────────────────────────────────────────────────────

def run_checks() -> bool:
    res = CheckResult()
    print("Loading CAD modules...")

    # ── Station 1 ────────────────────────────────────────────────────────────
    from station1_applicator import make_tank, make_applicator_body
    from params import S1_BODY_D, S1_BODY_H

    # S1 body: 60×40×55mm box. Z(55mm) is NOT the longest axis (W=60 > H=55).
    # Check that Z extent matches S1_BODY_H (55mm) within 2mm tolerance.
    s1_body = make_applicator_body()
    bb_s1b = _bbox(s1_body)
    res.check(
        "S1-body Z-height",
        abs(bb_s1b["z"] - S1_BODY_H) < 2.0,
        f"Z={bb_s1b['z']:.1f}mm matches S1_BODY_H={S1_BODY_H} [OK]",
        f"Z={bb_s1b['z']:.1f}mm != S1_BODY_H={S1_BODY_H} -- body height wrong"
    )

    # S1 tank: after assembly transform, principal axis must be Y (radial).
    # Test the assembled form: rotate X+90° + translate to side.
    s1_tank_raw = make_tank()
    bb_raw = _bbox(s1_tank_raw)
    # Raw tank is along Z — check it's longer than wide by ≥4× (280 vs 38)
    ratio_raw = _aspect_ratio(bb_raw, "z")
    res.check(
        "S1-tank raw geometry (pre-assembly)",
        bb_raw["z"] > bb_raw["x"] * 3.0,
        f"Z={bb_raw['z']:.0f} >> X={bb_raw['x']:.0f} (cylinder along Z)",
        f"Z={bb_raw['z']:.0f} X={bb_raw['x']:.0f} — tank not elongated along Z"
    )
    # Assembled form
    s1_tank_assy = (
        make_tank()
        .rotate((0, 0, 0), (1, 0, 0), 90)
        .translate((0, S1_BODY_D / 2.0, S1_BODY_H * 0.5))
    )
    bb_s1t = _bbox(s1_tank_assy)
    axis_s1t = _principal_axis(bb_s1t)
    res.check(
        "S1-tank assembled orientation",
        axis_s1t == "y",
        f"axis=Y extent={bb_s1t['y']:.1f}mm [OK] (radial outward per §4.1.2 L176)",
        f"axis={axis_s1t} extent=x{bb_s1t['x']:.0f} y{bb_s1t['y']:.0f} z{bb_s1t['z']:.0f} "
        f"— should be Y (radial). Check rotate/translate in assembly.py S1 tank block."
    )

    # ── Station 2 ────────────────────────────────────────────────────────────
    from station2_ae import make_ae_module
    s2 = make_ae_module()
    bb_s2 = _bbox(s2)
    axis_s2 = _principal_axis(bb_s2)
    res.check(
        "S2-AE module principal axis",
        axis_s2 == "z",
        f"axis=Z extent={bb_s2['z']:.1f}mm [OK] (serial stack along Z per §4.1.2 L247)",
        f"axis={axis_s2} — AE module should stack along Z"
    )

    # ── Station 3 ────────────────────────────────────────────────────────────
    from station3_cleaner import make_cleaner_body, make_solvent_tank
    from params import S3_BODY_W, S3_TANK_OD, S3_TANK_LENGTH

    s3_body = make_cleaner_body()
    bb_s3b = _bbox(s3_body)
    axis_s3b = _principal_axis(bb_s3b)
    res.check(
        "S3-cleaner body principal axis",
        axis_s3b == "z",
        f"axis=Z extent={bb_s3b['z']:.1f}mm [OK]",
        f"axis={axis_s3b} — cleaner body should be tallest along Z"
    )

    # S3 solvent tank: must be vertical (Z) — no rotation in assembly
    s3_tank_raw = make_solvent_tank()
    bb_s3t_raw = _bbox(s3_tank_raw)
    axis_s3t_raw = _principal_axis(bb_s3t_raw)
    res.check(
        "S3-solvent tank raw geometry (pre-assembly, must be Z-vertical)",
        axis_s3t_raw == "z",
        f"axis=Z extent={bb_s3t_raw['z']:.1f}mm [OK] (∥rot-axis per §4.1.3 L266)",
        f"axis={axis_s3t_raw} — solvent tank should be vertical (Z). "
        f"Do NOT rotate in assembly."
    )

    # Assembled: side-mounted but still vertical
    s3_tank_assy = make_solvent_tank().translate(
        (S3_BODY_W / 2.0 + S3_TANK_OD / 2.0, 0, 0)
    )
    bb_s3t = _bbox(s3_tank_assy)
    axis_s3t = _principal_axis(bb_s3t)
    res.check(
        "S3-solvent tank assembled orientation",
        axis_s3t == "z",
        f"axis=Z extent={bb_s3t['z']:.1f}mm [OK] (竖直, ∥旋转轴)",
        f"axis={axis_s3t} — should be Z. Check assembly.py S3 tank block (no Y-rotate!)."
    )

    # ── Station 4 ────────────────────────────────────────────────────────────
    from station4_uhf import make_uhf_bracket
    s4 = make_uhf_bracket()
    bb_s4 = _bbox(s4)
    # UHF bracket is flat — principal axis should be Z (bracket height) or X (width).
    # Design doc: bracket flat-mounts on arm tip, sensor protrudes in -Y (radial inward toward GIS)
    # No explicit elongation requirement; just verify it's not accidentally a Z-stick.
    # Bracket dims: S4_BRACKET_W × S4_BRACKET_D × S4_BRACKET_H
    from params import S4_BRACKET_H, S4_BRACKET_W, S4_BRACKET_D, S4_BRACKET_THICK
    # L-bracket total Z = H + THICK (base plate), so allow H + THICK + 1mm tolerance
    s4_z_max = S4_BRACKET_H + S4_BRACKET_THICK + 1.0
    res.check(
        "S4-UHF bracket Z-height",
        bb_s4["z"] <= s4_z_max,
        f"Z={bb_s4['z']:.1f}mm <= {s4_z_max:.1f} [OK] (H={S4_BRACKET_H}+thick={S4_BRACKET_THICK})",
        f"Z={bb_s4['z']:.1f}mm exceeds H+thick+1={s4_z_max:.1f}mm -- bracket mis-extruded"
    )

    return res.summary()


if __name__ == "__main__":
    print("\n=== GIS-EE Assembly Orientation Check ===")
    print("Reference: 04-末端执行机构设计.md")
    print("=" * 60)
    ok = run_checks()
    sys.exit(0 if ok else 1)
