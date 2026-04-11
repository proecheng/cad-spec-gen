"""cad_spec_gen.cad_lib — local-only asset library CLI (Spec 1).

Subcommands (Spec 1 scope — local only, NO network, NO downloads):
    init                      Create ~/.cad-spec-gen/ directory layout
    doctor                    Diagnose common issues
    list <kind>               List assets (templates in Spec 1)
    which <kind> <name>       Show resolution chain for an asset
    validate template <name>  Structurally validate a template file
    migrate-subsystem <dir>   Copy canonical render_3d.py to a subsystem dir
    report                    Read suggestions.yaml and print
    migrate                   Schema migration stub

See docs/superpowers/specs/2026-04-10-spec1-foundation-design.md section 8 for design.
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path
from typing import Optional

# Version is read from the package
try:
    from cad_spec_gen import __version__ as _pkg_version
except ImportError:
    _pkg_version = "unknown"

__version__ = _pkg_version

log = logging.getLogger("cad_lib")


# Name validation regex for CLI args (path traversal protection)
_SAFE_NAME_RE = re.compile(r"^[a-z0-9_]{1,64}$")


def _get_home() -> Path:
    """Return the effective ~/.cad-spec-gen/ directory.

    Respects CAD_SPEC_GEN_HOME env var for tests and for users who want
    to relocate the library root.
    """
    override = os.environ.get("CAD_SPEC_GEN_HOME")
    if override:
        return Path(override)
    return Path.home() / ".cad-spec-gen"


def _validate_name(name: str) -> bool:
    """Check that a name matches the safe regex (no path traversal)."""
    return bool(_SAFE_NAME_RE.match(name))


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="cad-lib",
        description="cad-spec-gen asset library local CLI (Spec 1)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"cad-lib {__version__}",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = subparsers.add_parser("init", help="Create ~/.cad-spec-gen/ layout")
    p_init.add_argument("--force", action="store_true",
                        help="Overwrite existing directory")

    # doctor
    p_doctor = subparsers.add_parser("doctor", help="Diagnose issues")

    # list
    p_list = subparsers.add_parser("list", help="List assets")
    p_list.add_argument("kind", choices=["templates", "textures", "models"])

    # which
    p_which = subparsers.add_parser("which", help="Show resolution chain")
    p_which.add_argument("kind", choices=["template", "texture", "material"])
    p_which.add_argument("name")

    # validate
    p_val = subparsers.add_parser("validate", help="Validate an asset")
    p_val.add_argument("kind", choices=["template"])
    p_val.add_argument("name_or_path")

    # migrate-subsystem
    p_migs = subparsers.add_parser("migrate-subsystem",
                                    help="Copy canonical render_3d.py to subsystem")
    p_migs.add_argument("directory", help="Subsystem directory (e.g. cad/end_effector)")
    p_migs.add_argument("--yes", "-y", action="store_true",
                        help="Skip confirmation prompt")

    # report
    p_report = subparsers.add_parser("report", help="Show suggestion log")

    # migrate
    p_mig = subparsers.add_parser("migrate", help="Schema version migration (stub)")

    return parser


def main(argv: Optional[list] = None) -> int:
    """Main entry point. Returns exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Dispatch to command handlers (stub implementations below, filled in later tasks)
    handlers = {
        "init": cmd_init,
        "doctor": cmd_doctor,
        "list": cmd_list,
        "which": cmd_which,
        "validate": cmd_validate,
        "migrate-subsystem": cmd_migrate_subsystem,
        "report": cmd_report,
        "migrate": cmd_migrate,
    }
    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return 2
    return handler(args)


# ---------------------------------------------------------------------------
# Command handler stubs (filled in by subsequent tasks)
# ---------------------------------------------------------------------------

def cmd_init(args) -> int:
    raise NotImplementedError("cmd_init — implemented in Task 20")


def cmd_doctor(args) -> int:
    raise NotImplementedError("cmd_doctor — implemented in Task 21")


def cmd_list(args) -> int:
    raise NotImplementedError("cmd_list — implemented in Task 22")


def cmd_which(args) -> int:
    raise NotImplementedError("cmd_which — implemented in Task 23")


def cmd_validate(args) -> int:
    raise NotImplementedError("cmd_validate — implemented in Task 24")


def cmd_migrate_subsystem(args) -> int:
    raise NotImplementedError("cmd_migrate_subsystem — implemented in Task 25")


def cmd_report(args) -> int:
    raise NotImplementedError("cmd_report — implemented in Task 26")


def cmd_migrate(args) -> int:
    raise NotImplementedError("cmd_migrate — implemented in Task 27")


if __name__ == "__main__":
    sys.exit(main())
