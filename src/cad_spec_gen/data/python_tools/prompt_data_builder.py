#!/usr/bin/env python3
"""
Prompt Data Builder — Auto-generate Gemini prompt variables from CAD code.

Reads params.py for dimensions and assembly.py for positions/transforms,
then generates assembly_description, material_descriptions, standard_parts,
and negative_constraints — eliminating manual description errors.

Usage:
    python prompt_data_builder.py --cad-dir cad/end_effector
    python prompt_data_builder.py --cad-dir cad/end_effector --view V1
    python prompt_data_builder.py --cad-dir cad/end_effector --update-config
"""

import importlib.util
import json
import math
import os
import sys
import types

SKILL_ROOT = os.path.dirname(os.path.abspath(__file__))


# ═══════════════════════════════════════════════════════════════════════════
# §1  Parameter Extraction — read params.py as data dictionary
# ═══════════════════════════════════════════════════════════════════════════

def load_params(cad_dir):
    """Import params.py from cad_dir and return all uppercase constants as dict."""
    params_path = os.path.join(cad_dir, "params.py")
    if not os.path.isfile(params_path):
        raise FileNotFoundError(f"params.py not found in {cad_dir}")

    spec = importlib.util.spec_from_file_location("params", params_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    params = {}
    for name in dir(mod):
        if name.isupper() and not name.startswith("_"):
            val = getattr(mod, name)
            if isinstance(val, (int, float, str, list, tuple)):
                params[name] = val
    return params


# ═══════════════════════════════════════════════════════════════════════════
# §2  Part Registry — structured description of each assembly component
# ═══════════════════════════════════════════════════════════════════════════

def _fmt(val, unit="mm"):
    """Format dimension: integer if whole, else 1 decimal."""
    if isinstance(val, float) and val == int(val):
        return f"{int(val)}{unit}"
    return f"{val}{unit}"


def _phi(dia, length=None):
    """Format cylindrical dimension: Phi38x280mm."""
    s = f"Phi{_fmt(dia)}"
    if length is not None:
        s += f"x{_fmt(length)}"
    return s


def build_part_registry(p):
    """Build structured part registry from params dict.

    Each entry: {
        name, name_cn, station, angle_deg, mount_r,
        shape, dims_text, material, color_desc,
        z_position, orientation, key_features
    }
    """
    mount_r = p.get("MOUNT_CENTER_R", 65.0)
    flange_thick = p.get("FLANGE_AL_THICK", 25.0)
    flange_od = p.get("FLANGE_OD", 90.0)
    peek_od = p.get("PEEK_OD", 86.0)
    peek_thick = p.get("FLANGE_PEEK_THICK", 5.0)

    # Drive assembly Z positions (from assembly.py)
    adapter_thick = p.get("ADAPTER_THICK", 8.0)
    reducer_len = p.get("REDUCER_LENGTH", 25.0)
    motor_body_len = p.get("MOTOR_BODY_LENGTH", 48.0)
    motor_flange_thick = p.get("MOTOR_FLANGE_THICK", 2.0)
    motor_total = p.get("MOTOR_TOTAL_LENGTH", 73.0)

    parts = []

    # ── Flange body ──
    parts.append({
        "name": "flange_body",
        "name_cn": "法兰本体",
        "station": "center",
        "angle_deg": None,
        "shape": "cross-shaped disc with 4 cantilever arms",
        "dims_text": f"{_phi(flange_od)}x{_fmt(flange_thick)} disc, arms {_fmt(p.get('ARM_WIDTH',12))}x{_fmt(p.get('ARM_THICK',8))}x{_fmt(p.get('ARM_LENGTH',40))}",
        "material": "7075-T6 aluminum, hard anodized dark gray",
        "color_desc": "dark gray",
        "z_range": (0, flange_thick),
        "orientation": "horizontal disc in XY plane",
        "key_features": f"4 arms at 0/90/180/270deg, mount faces at R={_fmt(mount_r)}, center hole {_phi(p.get('FLANGE_CENTER_HOLE',22))}",
    })

    # ── PEEK ring ──
    parts.append({
        "name": "peek_ring",
        "name_cn": "PEEK绝缘段",
        "station": "center",
        "angle_deg": None,
        "shape": "thin ring",
        "dims_text": f"{_phi(peek_od)}x{_fmt(peek_thick)}",
        "material": "PEEK engineering plastic",
        "color_desc": "warm honey-amber semi-translucent",
        "z_range": (flange_thick, flange_thick + peek_thick),
        "orientation": "horizontal, concentric below flange disc",
        "key_features": f"slightly smaller than flange ({_phi(peek_od)} vs {_phi(flange_od)})",
    })

    # ── Adapter plate ──
    adapter_od = p.get("ADAPTER_OD", 63.0)
    parts.append({
        "name": "adapter_plate",
        "name_cn": "ISO9409适配板",
        "station": "drive",
        "angle_deg": None,
        "shape": "flat disc",
        "dims_text": f"{_phi(adapter_od)}x{_fmt(adapter_thick)}",
        "material": "7075-T6 brushed aluminum",
        "color_desc": "brushed dark gray",
        "z_range": (-adapter_thick, 0),
        "orientation": "horizontal, below flange center",
        "key_features": f"4xM6 bolt holes on PCD {_phi(p.get('ISO9409_PCD',50))}",
    })

    # ── Motor ──
    motor_z_top = -adapter_thick - 1 - reducer_len - motor_flange_thick
    motor_z_bot = motor_z_top - motor_body_len
    parts.append({
        "name": "motor",
        "name_cn": "驱动电机",
        "station": "drive",
        "angle_deg": None,
        "shape": "cylinder",
        "dims_text": f"{_phi(p.get('MOTOR_OD',22))}x{_fmt(motor_body_len)}",
        "material": "Maxon ECX SPEED 22L",
        "color_desc": "dark steel with black endcap",
        "z_range": (motor_z_bot, motor_z_top),
        "orientation": "vertical, below adapter plate (arm-side, -Z)",
        "key_features": "brushed DC motor, thin cable exit at bottom",
    })

    # ── Reducer/Gearbox ──
    reducer_z_top = -adapter_thick - 1
    reducer_z_bot = reducer_z_top - reducer_len
    parts.append({
        "name": "reducer",
        "name_cn": "行星减速器",
        "station": "drive",
        "angle_deg": None,
        "shape": "cylinder",
        "dims_text": f"{_phi(p.get('REDUCER_OD',22))}x{_fmt(reducer_len)}",
        "material": "Maxon GP22C planetary gearbox",
        "color_desc": "silver machined aluminum",
        "z_range": (reducer_z_bot, reducer_z_top),
        "orientation": "vertical, between adapter and motor",
        "key_features": "hex output shaft visible on top",
    })

    # ── Station 1: Applicator (0°) ──
    s1_body_h = p.get("S1_BODY_H", 55.0)
    s1_body_w = p.get("S1_BODY_W", 60.0)
    s1_body_d = p.get("S1_BODY_D", 40.0)
    s1_tank_od = p.get("S1_TANK_OD", 38.0)
    s1_tank_len = p.get("S1_TANK_LENGTH", 280.0)

    parts.append({
        "name": "applicator_body",
        "name_cn": "涂抹模块壳体",
        "station": "S1",
        "angle_deg": 0.0,
        "shape": "box",
        "dims_text": f"{_fmt(s1_body_w)}x{_fmt(s1_body_d)}x{_fmt(s1_body_h)}",
        "material": "7075-T6 aluminum, hard anodized",
        "color_desc": "dark gray",
        "z_range": (flange_thick, flange_thick + s1_body_h),
        "orientation": f"hanging DOWN from 0deg arm tip at R={_fmt(mount_r)}",
        "key_features": "gear pump cavity, scraper at bottom, NTC sensor bore",
    })

    parts.append({
        "name": "applicator_tank",
        "name_cn": "耦合剂储罐",
        "station": "S1",
        "angle_deg": 0.0,
        "shape": "long cylinder",
        "dims_text": f"{_phi(s1_tank_od)}x{_fmt(s1_tank_len)}",
        "material": "SUS316L stainless steel, brushed silver",
        "color_desc": "brushed silver",
        "z_range": (flange_thick + s1_body_h, flange_thick + s1_body_h + s1_tank_od),
        "orientation": "HORIZONTAL, axis in XY plane, extending RADIALLY OUTWARD from station body",
        "key_features": f"LONGEST part in assembly ({_fmt(s1_tank_len)}), M14 quick-release thread at outer end",
    })

    parts.append({
        "name": "applicator_scraper",
        "name_cn": "刮涂头",
        "station": "S1",
        "angle_deg": 0.0,
        "shape": "small block",
        "dims_text": f"{_fmt(p.get('S1_SCRAPER_W',15))}x{_fmt(p.get('S1_SCRAPER_D',5))}x{_fmt(p.get('S1_SCRAPER_H',10))}",
        "material": "silicone rubber",
        "color_desc": "tan/brownish",
        "z_range": (flange_thick - p.get("S1_SCRAPER_H", 10), flange_thick),
        "orientation": "at bottom of applicator body",
        "key_features": "soft matte surface, scraper profile",
    })

    # ── Station 2: AE (90°) ──
    s2_force_dia = p.get("S2_FORCE_DIA", 42.0)
    s2_force_h = p.get("S2_FORCE_H", 12.0)
    s2_ae_dia = p.get("S2_AE_DIA", 28.0)
    s2_ae_h = p.get("S2_AE_H", 26.0)
    s2_gimbal_od = p.get("S2_GIMBAL_OD", 30.0)
    s2_gimbal_h = p.get("S2_GIMBAL_H", 15.0)
    s2_spring_od = p.get("S2_SPRING_OD", 8.0)
    s2_sleeve_od = p.get("S2_SLEEVE_OD", 12.0)
    s2_sleeve_h = p.get("S2_SLEEVE_H", 14.0)
    s2_guide_dia = p.get("S2_GUIDE_DIA", 4.0)
    s2_envelope_h = p.get("S2_ENVELOPE_H", 120.0)

    parts.append({
        "name": "ae_force_sensor",
        "name_cn": "六轴力传感器",
        "station": "S2",
        "angle_deg": 90.0,
        "shape": "flat disc",
        "dims_text": f"{_phi(s2_force_dia)}x{_fmt(s2_force_h)}",
        "material": "KWR42 force/torque sensor",
        "color_desc": "silver aluminum",
        "z_range": (flange_thick, flange_thick + s2_force_h),
        "orientation": f"horizontal disc at top of S2 stack, mounted to 90deg arm face",
        "key_features": f"center wire-through hole {_phi(p.get('S2_FORCE_CENTER_HOLE',10))}",
    })

    parts.append({
        "name": "ae_spring_limiter",
        "name_cn": "弹簧限力机构",
        "station": "S2",
        "angle_deg": 90.0,
        "shape": "cylindrical sleeve with internal spring",
        "dims_text": f"sleeve {_phi(s2_sleeve_od)}x{_fmt(s2_sleeve_h)}, spring OD {_fmt(s2_spring_od)}",
        "material": "aluminum sleeve + stainless spring",
        "color_desc": "silver with visible chrome coil",
        "z_range": (flange_thick + s2_force_h, flange_thick + s2_force_h + s2_sleeve_h),
        "orientation": "vertical axis PERPENDICULAR to flange face (along -Z), NEVER horizontal",
        "key_features": f"~{p.get('S2_SPRING_TURNS',6)} visible turns, guide shaft {_phi(s2_guide_dia)}, end plates {_phi(p.get('S2_ENDPLATE_DIA',12))}",
    })

    parts.append({
        "name": "ae_gimbal",
        "name_cn": "柔性万向节",
        "station": "S2",
        "angle_deg": 90.0,
        "shape": "annular rubber joint",
        "dims_text": f"{_phi(s2_gimbal_od)}x{_fmt(s2_gimbal_h)}",
        "material": "NBR rubber, Shore A 40",
        "color_desc": "matte black",
        "z_range_note": "below spring limiter, above AE probe",
        "orientation": "horizontal disc connecting spring limiter to probe",
        "key_features": f"flange PCD {_phi(p.get('S2_GIMBAL_FLANGE_PCD',22))}, 4xM2 bolts",
    })

    parts.append({
        "name": "ae_probe",
        "name_cn": "AE超声探头",
        "station": "S2",
        "angle_deg": 90.0,
        "shape": "cylinder",
        "dims_text": f"{_phi(s2_ae_dia)}x{_fmt(s2_ae_h)}",
        "material": "TWAE-03 acoustic emission sensor",
        "color_desc": "dark cylindrical body",
        "z_range_note": "bottom of S2 serial stack",
        "orientation": "vertical, sensing face pointing DOWN (-Z)",
        "key_features": f"coaxial cable exit ({_fmt(p.get('S2_AE_CABLE_DIA',3))} dia)",
    })

    # ── Station 3: Cleaner (180°) ──
    s3_body_w = p.get("S3_BODY_W", 50.0)
    s3_body_d = p.get("S3_BODY_D", 40.0)
    s3_body_h = p.get("S3_BODY_H", 120.0)
    s3_tank_od = p.get("S3_TANK_OD", 25.0)
    s3_tank_len = p.get("S3_TANK_LENGTH", 110.0)

    parts.append({
        "name": "cleaner_body",
        "name_cn": "清洁模块壳体",
        "station": "S3",
        "angle_deg": 180.0,
        "shape": "tall box",
        "dims_text": f"{_fmt(s3_body_w)}x{_fmt(s3_body_d)}x{_fmt(s3_body_h)}",
        "material": "7075-T6 aluminum, hard anodized",
        "color_desc": "dark gray",
        "z_range": (flange_thick, flange_thick + s3_body_h),
        "orientation": f"hanging DOWN from 180deg arm tip at R={_fmt(mount_r)}",
        "key_features": f"dual spool chambers, silicone flip-cover at bottom, tungsten counterweight ({_phi(p.get('S3_CW_DIA',14))}x{_fmt(p.get('S3_CW_H',13))}) at top",
    })

    parts.append({
        "name": "cleaner_tank",
        "name_cn": "溶剂储罐",
        "station": "S3",
        "angle_deg": 180.0,
        "shape": "short cylinder",
        "dims_text": f"{_phi(s3_tank_od)}x{_fmt(s3_tank_len)}",
        "material": "SUS304 stainless steel, polished",
        "color_desc": "polished silver",
        "z_range_note": "mounted on cleaner body side wall",
        "orientation": "VERTICAL, axis parallel to Z, parallel to cleaner body",
        "key_features": f"MUCH smaller than applicator tank ({_phi(s3_tank_od)} vs {_phi(s1_tank_od)}), M8 quick-release",
    })

    # ── Station 4: UHF (270°) ──
    s4_sensor_dia = p.get("S4_SENSOR_DIA", 45.0)
    s4_sensor_h = p.get("S4_SENSOR_H", 60.0)
    s4_bracket_w = p.get("S4_BRACKET_W", 50.0)
    s4_bracket_d = p.get("S4_BRACKET_D", 40.0)
    s4_bracket_h = p.get("S4_BRACKET_H", 25.0)

    parts.append({
        "name": "uhf_bracket",
        "name_cn": "UHF支架",
        "station": "S4",
        "angle_deg": 270.0,
        "shape": "L-bracket",
        "dims_text": f"{_fmt(s4_bracket_w)}x{_fmt(s4_bracket_d)}x{_fmt(s4_bracket_h)}",
        "material": "7075-T6 aluminum",
        "color_desc": "dark gray",
        "z_range": (flange_thick, flange_thick + s4_bracket_h),
        "orientation": f"mounted to 270deg arm face at R={_fmt(mount_r)}",
        "key_features": "short edge bolted to mount face, long edge extending down",
    })

    parts.append({
        "name": "uhf_sensor",
        "name_cn": "UHF传感器",
        "station": "S4",
        "angle_deg": 270.0,
        "shape": "cylinder",
        "dims_text": f"{_phi(s4_sensor_dia)}x{_fmt(s4_sensor_h)}",
        "material": "I300-UHF-GT inspection sensor",
        "color_desc": "dark grey ABS housing",
        "z_range_note": "clamped by L-bracket",
        "orientation": "vertical, sensing face DOWN",
        "key_features": "gold SMA RF connector facing UP",
    })

    return parts


# ═══════════════════════════════════════════════════════════════════════════
# §3  View Visibility — which parts are visible from each camera angle
# ═══════════════════════════════════════════════════════════════════════════

def _camera_visible_stations(cam_loc, station_angles=None):
    """Determine which stations are foreground/background based on camera XY angle.

    Args:
        cam_loc: [x, y, z] camera position
        station_angles: list of station angles in degrees (default: [0, 90, 180, 270])
    """
    station_angles = station_angles or [0.0, 90.0, 180.0, 270.0]
    station_names = [f"S{i+1}" for i in range(len(station_angles))]

    if cam_loc is None:
        return {"foreground": station_names, "background": []}

    cx, cy = cam_loc[0], cam_loc[1]
    cam_angle = math.degrees(math.atan2(cy, cx)) % 360

    # Stations within ±110° of camera direction are foreground
    fg, bg = [], []
    for i, sa in enumerate(station_angles):
        diff = abs(((cam_angle - sa + 180) % 360) - 180)
        if diff <= 110:  # generous: 110° to include near-side stations
            fg.append(station_names[i])
        else:
            bg.append(station_names[i])
    return {"foreground": fg, "background": bg}


# ═══════════════════════════════════════════════════════════════════════════
# §4  Assembly Description Generator
# ═══════════════════════════════════════════════════════════════════════════

_STATION_LABEL = {
    "S1": ("0deg", "Applicator"),
    "S2": ("90deg", "AE detection"),
    "S3": ("180deg", "Cleaner"),
    "S4": ("270deg", "UHF"),
}

# Part name → English label for Gemini prompt
_PART_EN_NAME = {
    "flange_body": "Flange body",
    "peek_ring": "PEEK ring",
    "adapter_plate": "Adapter plate",
    "motor": "Motor",
    "reducer": "Gearbox",
    "applicator_body": "Applicator housing",
    "applicator_tank": "Applicator reservoir tank",
    "applicator_scraper": "Scraper head",
    "ae_force_sensor": "Force sensor",
    "ae_spring_limiter": "Spring limiter",
    "ae_gimbal": "Rubber gimbal joint",
    "ae_probe": "AE probe",
    "cleaner_body": "Cleaner housing",
    "cleaner_tank": "Solvent tank",
    "uhf_bracket": "UHF bracket",
    "uhf_sensor": "UHF sensor",
}


def _part_one_liner(part):
    """Generate a one-line description of a part for assembly_description."""
    shape = part["shape"]
    dims = part["dims_text"]
    color = part["color_desc"]
    orient = part.get("orientation", "")
    features = part.get("key_features", "")

    line = f"{color} {shape} ({dims})"
    if orient:
        line += f", {orient}"
    if features:
        line += f". {features}"
    return line


def generate_assembly_description(parts, cam_loc, view_type, p):
    """Generate a structured assembly description for one view.

    Returns a multi-line text string describing visible parts from top to bottom.
    """
    station_angles = p.get("STATION_ANGLES", [0.0, 90.0, 180.0, 270.0])
    vis = _camera_visible_stations(cam_loc, station_angles)
    flange_od = p.get("FLANGE_OD", 90.0)
    flange_thick = p.get("FLANGE_AL_THICK", 25.0)
    peek_od = p.get("PEEK_OD", 86.0)
    peek_thick = p.get("FLANGE_PEEK_THICK", 5.0)
    mount_r = p.get("MOUNT_CENTER_R", 65.0)
    motor_od = p.get("MOTOR_OD", 22.0)
    motor_total = p.get("MOTOR_TOTAL_LENGTH", 73.0)

    lines = []

    # Center hub
    lines.append(
        f"Center: cross-shaped dark gray flange disc ({_phi(flange_od)}x{_fmt(flange_thick)}) "
        f"lying HORIZONTAL like a tabletop. Four cantilever arms extend at 0/90/180/270 degrees, "
        f"each ending in a {_fmt(p.get('MOUNT_FACE',40))}x{_fmt(p.get('MOUNT_FACE',40))} "
        f"mounting face at R={_fmt(mount_r)} from center."
    )

    # PEEK
    lines.append(
        f"Below flange: thin golden amber PEEK insulation ring ({_phi(peek_od)}x{_fmt(peek_thick)}, "
        f"slightly smaller than flange)."
    )

    # Drive (always below flange center, in -Z direction)
    lines.append(
        f"Below flange center: flat brushed adapter plate ({_phi(p.get('ADAPTER_OD',63))}x{_fmt(p.get('ADAPTER_THICK',8))}) "
        f"with motor+gearbox cylinder ({_phi(motor_od)}x{_fmt(motor_total)}) hanging down from it."
    )

    # Station descriptions — group by foreground/background
    for group_label, station_list in [("Foreground", vis["foreground"]),
                                       ("Background", vis["background"])]:
        for stn in station_list:
            angle_label, stn_name = _STATION_LABEL[stn]
            stn_parts = [pt for pt in parts if pt.get("station") == stn]
            if not stn_parts:
                continue

            part_descs = []
            for pt in stn_parts:
                en_name = _PART_EN_NAME.get(pt["name"], pt["name_cn"])
                part_descs.append(f"{en_name}: {_part_one_liner(pt)}")

            visibility = "partially occluded" if group_label == "Background" else "visible"
            lines.append(
                f"{group_label} ({angle_label} arm, {stn_name} module, {visibility}): "
                + "; ".join(part_descs) + "."
            )

    # Extras
    lines.append("Black cable chain arc along flange edge near 0deg position.")

    if view_type == "exploded":
        lines.append(
            "All modules displaced radially outward from center hub to reveal assembly relationships. "
            "Each module maintains its hanging-down orientation. Assembly guide gaps clearly visible."
        )
    elif view_type == "section":
        lines.append(
            "Assembly cut along plane exposing internal structures: pump cavities, spring limiter stack, "
            "spool chambers, gear train, motor windings, bearing cross-sections, cable routing channels."
        )

    return " ".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# §5  Material Descriptions Generator
# ═══════════════════════════════════════════════════════════════════════════

def generate_material_descriptions(parts, p):
    """Generate material_descriptions list for prompt_vars.

    Returns list of dicts with visual_cue and material_desc.
    """
    mat_map = {
        "flange_body": {
            "visual_cue": lambda pt: f"Cross-shaped disc with 4 cantilever arms (center body {_phi(p.get('FLANGE_OD',90))})",
            "material_desc": "7075-T6 aluminum, hard anodized dark gray, fine brushed machining marks visible, matte finish",
        },
        "peek_ring": {
            "visual_cue": lambda pt: f"Thin ring below flange disc ({_phi(p.get('PEEK_OD',86))}, slightly smaller than flange)",
            "material_desc": "PEEK engineering plastic, warm honey-amber semi-translucent, subsurface scattering glow, smooth polished",
        },
        "adapter_plate": {
            "visual_cue": lambda pt: f"Flat disc below flange (drive-side, {pt['dims_text']})",
            "material_desc": lambda pt: f"7075-T6 aluminum adapter plate, brushed dark gray, 4xM6 bolt holes visible on PCD {_phi(p.get('ISO9409_PCD',50))}",
        },
        "motor": {
            "visual_cue": lambda pt: f"Small cylinder below adapter plate (drive-side, {pt['dims_text']})",
            "material_desc": "Dark steel motor housing (Maxon ECX 22L), black endcap, precision machined surface",
        },
        "reducer": {
            "visual_cue": lambda pt: f"Cylinder between adapter plate and motor (drive-side, {pt['dims_text']})",
            "material_desc": "Silver aluminum planetary gearbox housing (Maxon GP22C), hex output shaft visible",
        },
        "applicator_body": {
            "visual_cue": lambda pt: f"Box-shaped module hanging from 0deg arm tip ({pt['dims_text']})",
            "material_desc": "Dark gray anodized aluminum housing, sharp edges, visible M3 bolt heads on mounting face",
        },
        "applicator_tank": {
            "visual_cue": lambda pt: f"LONG horizontal cylinder extending radially outward from 0deg station ({pt['dims_text']}, LONGEST part in assembly)",
            "material_desc": "SUS316L stainless steel, brushed silver with fine linear grain, M14 quick-release thread at outer end",
        },
        "applicator_scraper": {
            "visual_cue": lambda pt: "Small brownish piece at bottom of applicator module",
            "material_desc": "Tan/brownish silicone rubber scraper head, soft matte surface",
        },
        "ae_force_sensor": {
            "visual_cue": lambda pt: f"Silver disc at top of S2 serial stack ({pt['dims_text']})",
            "material_desc": lambda pt: f"KWR42 six-axis force/torque sensor, silver aluminum body, center wire-through hole {_phi(p.get('S2_FORCE_CENTER_HOLE',10))}",
        },
        "ae_spring_limiter": {
            "visual_cue": lambda pt: f"Cylindrical sleeve with visible coil spring ({pt['dims_text']})",
            "material_desc": lambda pt: (
                f"Aluminum spring limiter sleeve with visible tight helix compression coil spring "
                f"(~{p.get('S2_SPRING_TURNS',6)} visible turns, OD {_fmt(p.get('S2_SPRING_OD',8))}), "
                f"{_phi(p.get('S2_GUIDE_DIA',4))} chrome guide shaft, "
                f"end plates {_phi(p.get('S2_ENDPLATE_DIA',12))}"
            ),
        },
        "ae_gimbal": {
            "visual_cue": lambda pt: f"Black rubber annular joint below spring limiter ({pt['dims_text']})",
            "material_desc": "NBR rubber universal gimbal joint, matte black, Shore A 40",
        },
        "ae_probe": {
            "visual_cue": lambda pt: f"Cylindrical sensor at bottom of S2 stack ({pt['dims_text']})",
            "material_desc": "TWAE-03 acoustic emission sensor, dark cylindrical body, coaxial cable exit",
        },
        "cleaner_body": {
            "visual_cue": lambda pt: f"Tall box-shaped module hanging from 180deg arm tip ({pt['dims_text']})",
            "material_desc": lambda pt: (
                f"Dark gray anodized aluminum housing, dual spool chambers inside, "
                f"silicone rubber flip-cover at bottom cleaning window, "
                f"tungsten counterweight ({_phi(p.get('S3_CW_DIA',14))}x{_fmt(p.get('S3_CW_H',13))}) at module top"
            ),
        },
        "cleaner_tank": {
            "visual_cue": lambda pt: f"SHORT vertical cylinder on 180deg station side wall ({pt['dims_text']}, MUCH smaller than applicator tank)",
            "material_desc": "SUS304 stainless steel, polished silver, mounted vertically parallel to cleaner body axis",
        },
        "uhf_bracket": {
            "visual_cue": lambda pt: f"L-shaped bracket at 270deg arm ({pt['dims_text']})",
            "material_desc": "Dark gray 7075-T6 aluminum L-bracket, short edge bolted to mounting face, long edge extending down",
        },
        "uhf_sensor": {
            "visual_cue": lambda pt: f"Cylindrical sensor clamped by UHF L-bracket ({pt['dims_text']})",
            "material_desc": "I300-UHF-GT inspection sensor, dark grey ABS housing, gold SMA RF connector facing UP",
        },
    }

    result = []
    for pt in parts:
        name = pt["name"]
        if name not in mat_map:
            continue
        entry = mat_map[name]
        vc = entry["visual_cue"]
        md = entry["material_desc"]
        result.append({
            "visual_cue": vc(pt) if callable(vc) else vc,
            "material_desc": md(pt) if callable(md) else md,
        })

    # O-ring and rubber (always present)
    result.append({
        "visual_cue": f"Black O-ring seated in groove on flange ({_phi(p.get('ORING_CENTER_DIA',80))}x{_fmt(p.get('ORING_CS',2.4))} section)",
        "material_desc": "FKM fluoroelastomer, matte black, Shore A 70 hardness appearance",
    })

    return result


# ═══════════════════════════════════════════════════════════════════════════
# §6  Standard Parts Generator
# ═══════════════════════════════════════════════════════════════════════════

def generate_standard_parts(p):
    """Generate standard_parts list with correct dimensions from params."""
    motor_od = p.get("MOTOR_OD", 22.0)
    motor_body = p.get("MOTOR_BODY_LENGTH", 48.0)
    reducer_od = p.get("REDUCER_OD", 22.0)
    reducer_len = p.get("REDUCER_LENGTH", 25.0)

    return [
        {
            "visual_cue": f"Small cylinder ({_phi(motor_od)}x{_fmt(motor_body)}) — motor body below adapter plate",
            "real_part": "Maxon ECX SPEED 22L brushed DC motor, silver aluminum cylindrical housing, black plastic endcap with thin cable",
        },
        {
            "visual_cue": f"Cylinder ({_phi(reducer_od)}x{_fmt(reducer_len)}) above motor",
            "real_part": "Maxon GP22C planetary gearbox, silver machined aluminum housing, hex output shaft visible on top",
        },
        {
            "visual_cue": f"Thin flat ring/disc stack ({_phi(p.get('PEEK_BELLEVILLE_OD',12.5))})",
            "real_part": "DIN 2093 A6 disc spring washer stack, blued spring steel, slight iridescent golden-blue tint",
        },
        {
            "visual_cue": f"Small annular rings ({_phi(p.get('S3_BEARING_OD',10))}x{_fmt(p.get('S3_BEARING_THICK',4))}) at bearing locations",
            "real_part": "MR105ZZ miniature ball bearing, chrome steel races with rubber seals, precise metallic finish",
        },
        {
            "visual_cue": f"Black rubber torus ring ({_phi(p.get('ORING_CENTER_DIA',80))}x{_fmt(p.get('ORING_CS',2.4))} section) on flange sealing surface",
            "real_part": "FKM O-ring, matte black fluoroelastomer, soft rubber appearance",
        },
        {
            "visual_cue": f"Silver disc sensor ({_phi(p.get('S2_FORCE_DIA',42))}x{_fmt(p.get('S2_FORCE_H',12))}) at S2 station top",
            "real_part": "KWR42 six-axis force/torque sensor, silver aluminum body, precision instrument",
        },
        {
            "visual_cue": f"Cylindrical transducer ({_phi(p.get('S2_AE_DIA',28))}x{_fmt(p.get('S2_AE_H',26))}) at S2 bottom",
            "real_part": "TWAE-03 acoustic emission sensor, dark body, coaxial cable connector",
        },
        {
            "visual_cue": "Small cylindrical connectors (Phi10-12mm) on module sides",
            "real_part": "LEMO push-pull connectors, chrome-plated brass body, colored coding ring, precision round plug",
        },
        {
            "visual_cue": f"LONG horizontal cylinder ({_phi(p.get('S1_TANK_OD',38))}x{_fmt(p.get('S1_TANK_LENGTH',280))}) at S1 station (LONGEST part, HORIZONTAL)",
            "real_part": "Stainless steel solvent reservoir tank, mirror-polished SUS316L, welded end caps, industrial vessel look",
        },
        {
            "visual_cue": "Box shape with pipe stubs at S1 applicator",
            "real_part": "Miniature gear pump, silver aluminum body, two barbed tube fittings, compact industrial pump",
        },
        {
            "visual_cue": f"Large cylindrical sensor ({_phi(p.get('S4_SENSOR_DIA',45))}x{_fmt(p.get('S4_SENSOR_H',60))}) at S4 UHF station",
            "real_part": "I300-UHF inspection sensor, dark grey ABS housing, front aperture window, industrial sensor module",
        },
    ]


# ═══════════════════════════════════════════════════════════════════════════
# §7  Negative Constraints Generator
# ═══════════════════════════════════════════════════════════════════════════

def generate_negative_constraints(p):
    """Generate negative constraints from params + coordinate rules."""
    flange_od = p.get("FLANGE_OD", 90.0)
    peek_od = p.get("PEEK_OD", 86.0)
    center_hole = p.get("FLANGE_CENTER_HOLE", 22.0)
    motor_od = p.get("MOTOR_OD", 22.0)
    motor_total = p.get("MOTOR_TOTAL_LENGTH", 73.0)
    s1_tank_od = p.get("S1_TANK_OD", 38.0)
    s1_tank_len = p.get("S1_TANK_LENGTH", 280.0)
    s3_tank_od = p.get("S3_TANK_OD", 25.0)
    s3_tank_len = p.get("S3_TANK_LENGTH", 110.0)
    mount_r = p.get("MOUNT_CENTER_R", 65.0)

    return [
        f"N1: Flange center hole ({_phi(center_hole)}) is EMPTY — no mechanism protrudes through it toward workstation side",
        f"N2: Motor+gearbox cylinder ({_phi(motor_od)}x{_fmt(motor_total)}) is ONLY below flange center (in -Z direction), NEVER on workstation-side or on arm tips",
        f"N3: LONG reservoir ({_phi(s1_tank_od)}x{_fmt(s1_tank_len)}) is ALWAYS HORIZONTAL (axis in XY plane, extending radially outward); SHORT solvent tank ({_phi(s3_tank_od)}x{_fmt(s3_tank_len)}) is ALWAYS VERTICAL (axis along Z). Do NOT swap their orientations",
        "N4: Do NOT invent or add parts not described in the design specification or not visible in the input image",
        "N5: Signal conditioning module (GIS-EE-006) is NOT on the flange — it is mounted on the robot arm 250mm away. Do NOT draw it in end effector views",
        f"N6: PEEK ring ({_phi(peek_od)}) is slightly SMALLER than flange ({_phi(flange_od)}), only {_fmt(p.get('FLANGE_PEEK_THICK',5))} thin amber ring — do NOT enlarge it to match flange diameter",
        f"N7: All four station modules mount at cantilever arm TIPS (R={_fmt(mount_r)} from center), NOT on the disc face",
        "N8: Flange disc is HORIZONTAL (like a tabletop), NOT a vertical wheel. Z-axis is vertical, flange face is in XY plane",
        "N9: AE spring limiter axis is ALWAYS perpendicular to flange face (along -Z), NEVER parallel to flange face (NEVER horizontal)",
        "N10: All four station modules hang vertically DOWN (-Z) from arm tips, NOT horizontally outward. Module bodies are oriented along -Z",
    ]


# ═══════════════════════════════════════════════════════════════════════════
# §8  Main: generate all prompt data for render_config
# ═══════════════════════════════════════════════════════════════════════════

def generate_prompt_data(cad_dir, rc=None):
    """Generate all prompt data from CAD code.

    Args:
        cad_dir: path to cad/<subsystem>/ containing params.py
        rc: existing render_config.json dict (for camera positions)

    Returns:
        dict with keys: assembly_description, prompt_vars, standard_parts, negative_constraints
    """
    p = load_params(cad_dir)
    parts = build_part_registry(p)

    rc = rc or {}
    cameras = rc.get("camera", {})

    # Generate per-view assembly descriptions
    assembly_desc = {}
    for vk in sorted(cameras.keys()):
        cam = cameras[vk]
        cam_loc = cam.get("location")
        view_type = cam.get("type", "standard")
        assembly_desc[vk] = generate_assembly_description(parts, cam_loc, view_type, p)

    # Material descriptions
    mat_descs = generate_material_descriptions(parts, p)

    # Standard parts
    std_parts = generate_standard_parts(p)

    # Negative constraints
    neg_constraints = generate_negative_constraints(p)

    return {
        "assembly_description": assembly_desc,
        "prompt_vars": {
            "product_name": rc.get("prompt_vars", {}).get("product_name", "precision mechanical assembly"),
            "material_descriptions": mat_descs,
        },
        "standard_parts": std_parts,
        "negative_constraints": neg_constraints,
    }


def merge_into_config(rc, generated):
    """Merge generated prompt data into render_config dict (in-place).

    Generated data OVERRIDES manual entries for assembly_description,
    prompt_vars.material_descriptions, standard_parts, negative_constraints.
    """
    rc["assembly_description"] = generated["assembly_description"]
    rc.setdefault("prompt_vars", {})
    rc["prompt_vars"]["material_descriptions"] = generated["prompt_vars"]["material_descriptions"]
    if generated["prompt_vars"].get("product_name"):
        rc["prompt_vars"]["product_name"] = generated["prompt_vars"]["product_name"]
    rc["standard_parts"] = generated["standard_parts"]
    rc["negative_constraints"] = generated["negative_constraints"]
    return rc


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Auto-generate Gemini prompt data from CAD code (params.py + assembly.py)"
    )
    parser.add_argument("--cad-dir", required=True,
                        help="Path to cad/<subsystem>/ directory containing params.py")
    parser.add_argument("--view", default=None,
                        help="Show generated data for a specific view (V1-V6)")
    parser.add_argument("--update-config", action="store_true",
                        help="Update render_config.json in cad-dir with generated data")
    parser.add_argument("--json", action="store_true",
                        help="Output all generated data as JSON")
    args = parser.parse_args()

    cad_dir = os.path.abspath(args.cad_dir)

    # Load existing render_config if present
    rc_path = os.path.join(cad_dir, "render_config.json")
    rc = {}
    if os.path.isfile(rc_path):
        with open(rc_path, encoding="utf-8") as f:
            rc = json.load(f)

    generated = generate_prompt_data(cad_dir, rc)

    if args.json:
        print(json.dumps(generated, indent=2, ensure_ascii=False))
        return 0

    if args.view:
        vk = args.view.upper()
        desc = generated["assembly_description"].get(vk)
        if desc:
            print(f"=== Assembly Description for {vk} ===")
            print(desc)
        else:
            print(f"No data for view {vk}. Available: {list(generated['assembly_description'].keys())}")
        return 0

    if args.update_config:
        if not os.path.isfile(rc_path):
            print(f"ERROR: render_config.json not found in {cad_dir}", file=sys.stderr)
            return 1
        merge_into_config(rc, generated)
        with open(rc_path, "w", encoding="utf-8") as f:
            json.dump(rc, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"Updated: {rc_path}")
        print(f"  - {len(generated['assembly_description'])} assembly descriptions")
        print(f"  - {len(generated['prompt_vars']['material_descriptions'])} material descriptions")
        print(f"  - {len(generated['standard_parts'])} standard parts")
        print(f"  - {len(generated['negative_constraints'])} negative constraints")
        return 0

    # Default: print summary
    print("Generated prompt data:")
    for vk, desc in sorted(generated["assembly_description"].items()):
        print(f"\n  {vk}: {desc[:120]}...")
    print(f"\n  Materials: {len(generated['prompt_vars']['material_descriptions'])} entries")
    print(f"  Standard parts: {len(generated['standard_parts'])} entries")
    print(f"  Negative constraints: {len(generated['negative_constraints'])} entries")
    print(f"\nUse --update-config to write to render_config.json")
    print(f"Use --view V1 to see full description for a view")
    print(f"Use --json to dump all data as JSON")
    return 0


if __name__ == "__main__":
    sys.exit(main())
