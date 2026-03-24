"""CLI entry points for cad-spec-gen.

Entry points:
    cad-skill-setup  → main_setup()
    cad-skill-check  → main_check()
"""

import argparse
import io
import sys

# Fix Windows GBK encoding
if sys.stdout.encoding and sys.stdout.encoding.lower().startswith("gbk"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def main_setup():
    """Interactive setup wizard entry point."""
    parser = argparse.ArgumentParser(
        description="cad-spec-gen interactive setup wizard",
        prog="cad-skill-setup",
    )
    parser.add_argument(
        "--lang", choices=["zh", "en"],
        help="Language (skip language prompt)",
    )
    parser.add_argument(
        "--target", "-t", default=None,
        help="Target project directory (default: current directory)",
    )
    parser.add_argument(
        "--skip-deps", action="store_true",
        help="Skip optional dependency installation",
    )
    parser.add_argument(
        "--update", "-u", action="store_true",
        help="Update existing installation (preserves user-modified config)",
    )
    args = parser.parse_args()

    from .wizard.wizard import run_wizard
    sys.exit(run_wizard(
        lang=args.lang,
        target=args.target,
        skip_deps=args.skip_deps,
        update=args.update,
    ))


def main_check():
    """Environment check entry point."""
    parser = argparse.ArgumentParser(
        description="Check cad-spec-gen environment and installation status",
        prog="cad-skill-check",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output as JSON",
    )
    args = parser.parse_args()

    from .wizard import env_detect, ui
    from . import __version__

    results = env_detect.run_full_check()

    if args.json:
        import json
        results["skill_version"] = __version__
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    ui.banner("cad-spec-gen", __version__)
    print("  Environment Check\n")

    ui.status_line("Python", results["python"]["version"],
                   ok=results["python"]["ok"])
    for name, (ver, ok) in results["packages"].items():
        ui.status_line(name, ver or "not installed", ok=ok)
    ui.status_line("Blender",
                   results["blender"]["version"] or "not found",
                   ok=results["blender"]["path"] is not None)
    ui.status_line("Gemini",
                   "configured" if results["gemini"]["ok"] else "not configured",
                   ok=results["gemini"]["ok"])

    level = results["level"]
    level_names = {1: "MINIMAL", 2: "IMPORT", 3: "CAD", 4: "RENDER", 5: "FULL"}
    print(f"\n  Capability: Level {level} ({level_names.get(level, '?')})")


if __name__ == "__main__":
    main_setup()
