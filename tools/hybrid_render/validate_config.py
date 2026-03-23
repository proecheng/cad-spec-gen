#!/usr/bin/env python3
"""
Config Validator — Dry-run check for render_config.json

Loads a render config, resolves all materials/cameras/explode rules,
and reports any errors — without launching Blender.

Usage:
    python tools/hybrid_render/validate_config.py cad/end_effector/render_config.json
    python tools/hybrid_render/validate_config.py --help

No Blender or GPU needed. Requires only Python stdlib + render_config.py.
"""

import json
import os
import sys


def find_render_config_module():
    """Locate render_config.py relative to the config file or project."""
    # Search order: cad/end_effector/ → tools/hybrid_render/../cad/end_effector/
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "..", "..", "cad", "end_effector"),
    ]
    # Also try same directory as the config file (added in main)
    return candidates


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        print("\nUsage: python validate_config.py <path-to-render_config.json>")
        return 0

    config_path = sys.argv[1]
    if not os.path.isfile(config_path):
        print(f"[ERROR] Config file not found: {config_path}")
        return 1

    # Add config file's directory to path so we can import render_config
    config_dir = os.path.dirname(os.path.abspath(config_path))
    search_paths = [config_dir] + find_render_config_module()
    for p in search_paths:
        norm_p = os.path.normpath(p)
        if norm_p not in sys.path:
            sys.path.insert(0, norm_p)

    try:
        import render_config as rcfg
    except ImportError:
        print("[ERROR] Cannot import render_config.py")
        print("  Ensure render_config.py exists in same directory as config JSON")
        print(f"  Searched: {search_paths}")
        return 1

    print("=" * 62)
    print("  render_config.json — Validation Report")
    print("=" * 62)
    errors = 0
    warnings = 0

    # 1. Load config
    print(f"\n  Config: {os.path.abspath(config_path)}")
    try:
        config = rcfg.load_config(config_path)
        print(f"  [OK] JSON loaded successfully (version={config.get('version', '?')})")
    except (json.JSONDecodeError, ValueError, FileNotFoundError) as e:
        print(f"  [FAIL] Load error: {e}")
        return 1

    # 2. Subsystem info
    sub = config.get("subsystem", {})
    print(f"\n  Subsystem: {sub.get('name', '?')} ({sub.get('name_cn', '?')})")
    print(f"  Part prefix: {sub.get('part_prefix', '?')}")
    print(f"  GLB file: {sub.get('glb_file', '?')}")
    print(f"  Bounding radius: {sub.get('bounding_radius_mm', '?')}mm")

    glb_path = config.get("_resolved", {}).get("glb_path", "")
    if glb_path and os.path.isfile(glb_path):
        size_mb = os.path.getsize(glb_path) / (1024 * 1024)
        print(f"  [OK] GLB exists: {glb_path} ({size_mb:.1f} MB)")
    elif glb_path:
        print(f"  [WARN] GLB not found: {glb_path}")
        print(f"         Run build_all.py first to generate it")
        warnings += 1
    else:
        print(f"  [WARN] GLB path not resolved")
        warnings += 1

    # 3. Materials
    mat_section = config.get("materials", {})
    print(f"\n  Materials: {len(mat_section)} entries")
    try:
        resolved = rcfg.resolve_all_materials(config)
        for name, params in resolved.items():
            c = params.get("color", (0, 0, 0, 1))
            m = params.get("metallic", 0)
            r = params.get("roughness", 0.5)
            label = params.get("label", "")
            print(f"    [OK] {name:15s}  M={m:<4}  R={r:<4}  "
                  f"RGB=({c[0]:.2f},{c[1]:.2f},{c[2]:.2f})  {label}")
    except ValueError as e:
        print(f"    [FAIL] {e}")
        errors += 1

    # 4. Cameras
    cam_section = config.get("camera", {})
    print(f"\n  Cameras: {len(cam_section)} presets")
    br = sub.get("bounding_radius_mm", 300)
    for key, preset in cam_section.items():
        try:
            resolved_cam = rcfg.camera_to_blender(preset, br)
            loc = resolved_cam.get("location", "?")
            ortho = "ortho" if resolved_cam.get("ortho") else "persp"
            desc = resolved_cam.get("description", "")
            print(f"    [OK] {key}: {ortho:5s}  loc={loc}  {desc}")
        except Exception as e:
            print(f"    [FAIL] {key}: {e}")
            errors += 1

    # 5. Explode rules
    explode = config.get("explode", {})
    if explode:
        rules = explode.get("rules", {})
        print(f"\n  Explode: type={explode.get('type', '?')}  "
              f"spread={explode.get('spread_mm', '?')}mm  "
              f"z_spread={explode.get('z_spread_mm', '?')}mm  "
              f"rules={len(rules)}")
        for name, rule in rules.items():
            if rule.get("radial"):
                print(f"    [OK] {name:15s}  radial @ {rule.get('angle_deg', '?')}deg")
            elif "z_offset" in rule:
                print(f"    [OK] {name:15s}  z_offset={rule['z_offset']}")
            else:
                print(f"    [WARN] {name:15s}  unknown rule type: {rule}")
                warnings += 1
    else:
        print("\n  Explode: not configured (optional)")

    # 6. Prompt vars
    pv = config.get("prompt_vars", {})
    if pv:
        descs = pv.get("material_descriptions", [])
        print(f"\n  Prompt vars: product=\"{pv.get('product_name', '?')}\"  "
              f"material_descriptions={len(descs)}")
        for i, d in enumerate(descs):
            vc = d.get("visual_cue", "?")
            md = d.get("material_desc", "?")
            if len(md) > 50:
                md = md[:47] + "..."
            print(f"    [{i+1}] {vc}: {md}")
    else:
        print("\n  Prompt vars: not configured (optional for Blender-only rendering)")

    # 7. Lighting scale preview
    print(f"\n  Lighting scale (bounding_r={br}mm):")
    energies = rcfg.scaled_energies(br)
    for name, val in energies.items():
        print(f"    {name:8s} = {val:,.0f} W")

    # Summary
    print(f"\n  {'=' * 56}")
    if errors == 0 and warnings == 0:
        print("  [PASS] All checks passed. Ready to render!")
        print(f"\n  Next steps:")
        print(f"    blender.exe -b -P render_3d.py -- "
              f"--config {os.path.basename(config_path)} --all")
    elif errors == 0:
        print(f"  [PASS] {warnings} warning(s), 0 errors. Can render with caveats.")
    else:
        print(f"  [FAIL] {errors} error(s), {warnings} warning(s). Fix errors first.")
    print("=" * 62)

    return 1 if errors > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
