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
    """Create ~/.cad-spec-gen/ directory layout with schema v1 YAML stubs."""
    home = _get_home()

    # Check if library already populated (shared/ or state/ exist with content)
    shared = home / "shared"
    state = home / "state"
    already_populated = False
    for check_dir in (shared, state):
        if check_dir.exists() and any(check_dir.iterdir()):
            already_populated = True
            break

    if already_populated and not args.force:
        log.error("~/.cad-spec-gen/ is already populated. Use --force to reinitialize.")
        log.error(f"  {home}")
        return 1

    # Create directory structure
    home.mkdir(parents=True, exist_ok=True)
    shared.mkdir(exist_ok=True)
    state.mkdir(exist_ok=True)
    (shared / "templates").mkdir(exist_ok=True)

    # Write library.yaml
    (shared / "library.yaml").write_text(
        "# cad-spec-gen user library - shared config\n"
        "# This file is safe to commit to git for team-sharing.\n"
        "# See ~/.cad-spec-gen/state/ for machine-local state.\n"
        "\n"
        "schema_version: 1\n"
        "\n"
        "# Template routing rules (Spec 2 populates).\n"
        "routing: []\n"
        "\n"
        "# User-defined material preset extensions (Spec 2 populates).\n"
        "materials: {}\n"
        "\n"
        "# User template keyword overrides (Spec 2 populates).\n"
        "template_keywords: {}\n",
        encoding="utf-8",
    )

    # Write shared/README.md
    (shared / "README.md").write_text(
        "# cad-spec-gen shared library\n"
        "\n"
        "This directory is **safe to commit to git** for team-sharing.\n"
        "\n"
        "Contents:\n"
        "- `library.yaml` - routing rules, material presets, keyword overrides\n"
        "- `templates/` - (Spec 2) user-added template modules\n"
        "\n"
        "Machine-local state is stored in the sibling `state/` directory and\n"
        "must NOT be committed.\n"
        "\n"
        "Run `cad-lib doctor` to check the library's health.\n",
        encoding="utf-8",
    )

    # Write state/installed.yaml
    (state / "installed.yaml").write_text(
        "# cad-spec-gen installed asset log - MACHINE-LOCAL, do not commit.\n"
        "\n"
        "schema_version: 1\n"
        "\n"
        "textures: {}\n"
        "templates: {}\n"
        "models: {}\n",
        encoding="utf-8",
    )

    # Write state/suggestions.yaml
    (state / "suggestions.yaml").write_text(
        "# cad-spec-gen library growth suggestions - MACHINE-LOCAL, do not commit.\n"
        "\n"
        "schema_version: 1\n"
        "\n"
        "suggestions: []\n",
        encoding="utf-8",
    )

    # Write state/.gitignore
    (state / ".gitignore").write_text(
        "# Machine-local state - never commit.\n"
        "*\n"
        "!.gitignore\n",
        encoding="utf-8",
    )

    log.info(f"Initialized cad-spec-gen library at {home}")
    return 0


def cmd_doctor(args) -> int:
    """Run diagnostic checks and report issues.

    Returns 0 if all critical checks pass, 1 if any error.
    """
    checks = []  # list of (name, status, detail)
    errors = 0

    # Check 1: canonical render_3d.py exists
    canonical_exists = False
    try:
        import importlib.resources as ir
        try:
            canonical_ref = ir.files("cad_spec_gen") / "render_3d.py"
            canonical_exists = canonical_ref.is_file()
        except (FileNotFoundError, AttributeError):
            canonical_exists = False
    except ImportError:
        canonical_exists = False

    if not canonical_exists:
        # Fallback: repo-checkout filesystem check
        canonical_path = Path(__file__).parent / "render_3d.py"
        canonical_exists = canonical_path.exists()

    if canonical_exists:
        checks.append(("canonical render_3d.py", "OK", ""))
    else:
        checks.append(("canonical render_3d.py", "ERROR", "not found"))
        errors += 1

    # Check 2: parts_routing module importable
    try:
        from cad_spec_gen import parts_routing  # noqa: F401
        checks.append(("parts_routing module", "OK", ""))
    except ImportError as e:
        checks.append(("parts_routing module", "ERROR", str(e)))
        errors += 1

    # Check 3: template discovery
    try:
        from cad_spec_gen.parts_routing import (
            discover_templates, locate_builtin_templates_dir,
        )
        tier1 = locate_builtin_templates_dir()
        if tier1 is None:
            checks.append(("builtin templates dir", "ERROR",
                          "locate_builtin_templates_dir() returned None"))
            errors += 1
        else:
            templates = discover_templates([tier1])
            count = len(templates)
            if count >= 5:
                checks.append(("template discovery", "OK", f"{count} templates found"))
            else:
                checks.append(("template discovery", "WARN",
                              f"only {count} templates found, expected >= 5"))
    except Exception as e:
        checks.append(("template discovery", "ERROR", str(e)))
        errors += 1

    # Check 4: ~/.cad-spec-gen/ layout (if initialized)
    home = _get_home()
    if home.exists():
        if (home / "shared").is_dir() and (home / "state").is_dir():
            checks.append(("~/.cad-spec-gen layout", "OK", ""))
        else:
            checks.append(("~/.cad-spec-gen layout", "WARN",
                          "run 'cad-lib init' to create shared/ and state/"))
    else:
        checks.append(("~/.cad-spec-gen layout", "INFO",
                      "not initialized; run 'cad-lib init'"))

    # Check 5: pyproject entry point (informational)
    import shutil
    if shutil.which("cad-lib"):
        checks.append(("pyproject entry point", "OK", ""))
    else:
        checks.append(("pyproject entry point", "INFO",
                      "cad-lib not on PATH; run via 'python -m cad_spec_gen.cad_lib'"))

    # Print results
    print("cad-lib doctor report")
    print("-" * 40)
    for name, status, detail in checks:
        marker = {"OK": "[OK]", "WARN": "[!]", "ERROR": "[X]", "INFO": "[i]"}.get(status, "[?]")
        line = f"  {marker} {name}: {status}"
        if detail:
            line += f" - {detail}"
        print(line)
    print("-" * 40)

    if errors > 0:
        print(f"{errors} error(s) found")
        return 1
    return 0


def cmd_list(args) -> int:
    """List assets of a given kind."""
    if args.kind == "templates":
        try:
            from cad_spec_gen.parts_routing import (
                discover_templates, locate_builtin_templates_dir,
            )
        except ImportError as e:
            print(f"Error: cannot import parts_routing: {e}", file=sys.stderr)
            return 1
        tier1 = locate_builtin_templates_dir()
        if tier1 is None:
            print("No builtin templates directory found.", file=sys.stderr)
            return 1
        templates = discover_templates([tier1])
        if not templates:
            print("No templates found.")
            return 0
        print(f"{'NAME':<25} {'CATEGORY':<22} {'TIER':<10} {'PRIORITY'}")
        print("-" * 70)
        for t in templates:
            print(f"{t.name:<25} {t.category:<22} {t.tier:<10} {t.priority}")
        return 0

    elif args.kind in ("textures", "models"):
        print(f"{args.kind} are not available in Spec 1 - see Spec 2 (deferred).")
        return 0

    return 1


def cmd_which(args) -> int:
    """Show resolution chain for an asset."""
    if args.kind != "template":
        print(f"'which {args.kind}' is not available in Spec 1.")
        return 0

    if not _validate_name(args.name):
        print(f"Invalid template name: {args.name!r} (must match [a-z0-9_]{{1,64}})",
              file=sys.stderr)
        return 2

    try:
        from cad_spec_gen.parts_routing import (
            discover_templates, locate_builtin_templates_dir,
        )
    except ImportError as e:
        print(f"Error: cannot import parts_routing: {e}", file=sys.stderr)
        return 1

    tier1 = locate_builtin_templates_dir()
    if tier1 is None:
        print("No builtin templates directory found.", file=sys.stderr)
        return 1

    templates = discover_templates([tier1])
    match = next((t for t in templates if t.name == args.name), None)

    if match is None:
        print(f"Template {args.name!r} not found.")
        print(f"Searched: {tier1}")
        return 1

    print(f"Template: {match.name}")
    print(f"  Tier:      {match.tier}")
    print(f"  Category:  {match.category}")
    print(f"  Priority:  {match.priority}")
    print(f"  Keywords:  {', '.join(match.keywords)}")
    print(f"  Source:    {match.source_path}")
    return 0


def cmd_validate(args) -> int:
    """Validate a template structurally."""
    if args.kind != "template":
        return 2

    name_or_path = args.name_or_path

    # Resolution: try as filesystem path first, then as module name
    path: Optional[Path] = None

    # Option 1: filesystem path (absolute or relative to cwd)
    candidate = Path(name_or_path)
    if candidate.exists() and candidate.is_file() and candidate.suffix == ".py":
        path = candidate.resolve()
    else:
        # Option 2: treat as module name — validate regex + look up via discover_templates
        if not _validate_name(name_or_path):
            print(f"Invalid template name: {name_or_path!r} "
                  f"(must match [a-z0-9_]{{1,64}} or be a valid file path)",
                  file=sys.stderr)
            return 2
        try:
            from cad_spec_gen.parts_routing import (
                discover_templates, locate_builtin_templates_dir,
            )
        except ImportError as e:
            print(f"Error: cannot import parts_routing: {e}", file=sys.stderr)
            return 1
        tier1 = locate_builtin_templates_dir()
        if tier1 is None:
            print("No builtin templates dir.", file=sys.stderr)
            return 1
        templates = discover_templates([tier1])
        match = next((t for t in templates if t.name == name_or_path), None)
        if match is None:
            print(f"Template {name_or_path!r} not found.", file=sys.stderr)
            return 1
        path = match.source_path

    # Parse + validate
    import ast
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError, UnicodeDecodeError) as e:
        print(f"[X] Parse error: {e}", file=sys.stderr)
        return 1

    # Check required constants and functions via AST
    required_funcs = {"make", "example_params"}
    required_consts = {"MATCH_KEYWORDS", "MATCH_PRIORITY",
                       "TEMPLATE_CATEGORY", "TEMPLATE_VERSION"}
    found_funcs = set()
    found_consts = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in required_funcs:
            found_funcs.add(node.name)
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = [node.target] if isinstance(node, ast.AnnAssign) else node.targets
            for t in targets:
                if isinstance(t, ast.Name) and t.id in required_consts:
                    found_consts.add(t.id)

    missing = []
    if required_funcs - found_funcs:
        missing.append(f"functions: {required_funcs - found_funcs}")
    if required_consts - found_consts:
        missing.append(f"constants: {required_consts - found_consts}")

    if missing:
        print(f"[X] Template {path} is missing: {'; '.join(missing)}", file=sys.stderr)
        return 1

    print(f"[OK] Template {path} passes structural validation.")
    return 0


def cmd_migrate_subsystem(args) -> int:
    """Copy canonical render_3d.py to a subsystem directory with .bak backup."""
    import shutil
    from datetime import datetime

    target_dir = Path(args.directory).resolve()
    if not target_dir.is_dir():
        print(f"[X] Not a directory: {target_dir}", file=sys.stderr)
        return 1

    target_file = target_dir / "render_3d.py"

    # Locate canonical source
    canonical: Optional[Path] = None
    try:
        import importlib.resources as ir
        try:
            canonical_ref = ir.files("cad_spec_gen") / "render_3d.py"
            canonical_path = Path(str(canonical_ref))
            if canonical_path.is_file():
                canonical = canonical_path
        except (FileNotFoundError, AttributeError):
            pass
    except ImportError:
        pass

    if canonical is None:
        # Fallback: try the repo-checkout location (this file's sibling)
        fallback = Path(__file__).parent / "render_3d.py"
        if fallback.is_file():
            canonical = fallback

    if canonical is None or not canonical.is_file():
        print(f"[X] Canonical render_3d.py not found.", file=sys.stderr)
        return 1

    # Prompt unless --yes
    if not args.yes:
        print(f"This will replace {target_file}")
        print(f"  with:           {canonical}")
        print(f"  backup to:      {target_file}.bak.<timestamp>")
        try:
            resp = input("Proceed? [y/N] ").strip().lower()
        except EOFError:
            resp = ""
        if resp not in ("y", "yes"):
            print("Aborted.")
            return 0

    # Backup existing if present
    if target_file.exists():
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        backup = target_file.parent / f"{target_file.name}.bak.{timestamp}"
        shutil.copy2(target_file, backup)
        print(f"  backup: {backup}")

    # Copy canonical
    shutil.copy2(canonical, target_file)
    print(f"[OK] Migrated {target_file}")
    return 0


def cmd_report(args) -> int:
    raise NotImplementedError("cmd_report — implemented in Task 26")


def cmd_migrate(args) -> int:
    raise NotImplementedError("cmd_migrate — implemented in Task 27")


if __name__ == "__main__":
    sys.exit(main())
