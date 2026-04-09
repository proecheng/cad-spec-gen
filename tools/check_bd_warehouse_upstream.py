#!/usr/bin/env python3
"""
check_bd_warehouse_upstream.py — Poll the bd_warehouse upstream for the
Windows CSV encoding fix (gumyr/bd_warehouse#75).

Run this periodically (manually or via a cron) to know when it's safe to:
  1. Remove the `PYTHONUTF8=1` requirement from the Windows workflow
  2. Bump `bd_warehouse` pin in pyproject.toml
  3. Delete the `_try_import_bd_warehouse_bearing()` exception wrapper
     from tests/test_parts_adapters.py

Usage:
    python tools/check_bd_warehouse_upstream.py           # check only
    python tools/check_bd_warehouse_upstream.py --fix     # check + print
                                                            upgrade recipe

Exit codes:
    0 — fix is available (merged or released with the fix)
    1 — not yet available
    2 — transient error (network / gh cli)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys


PR_NUMBER = 75
REPO = "gumyr/bd_warehouse"
MIN_RELEASE_WITH_FIX = "0.3.0"  # speculative; update when PR lands


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30)
        return result.returncode, result.stdout
    except Exception as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        return 2, ""


def check_pr_merged() -> tuple[bool, str]:
    """Return (merged, human_readable_status)."""
    rc, out = _run([
        "gh", "pr", "view", str(PR_NUMBER),
        "--repo", REPO,
        "--json", "state,mergedAt,reviewDecision,comments",
    ])
    if rc != 0:
        return False, "gh pr view failed"
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return False, "gh returned non-JSON"
    if data.get("state") == "MERGED" or data.get("mergedAt"):
        return True, f"PR #{PR_NUMBER} MERGED at {data.get('mergedAt')}"
    comment_count = len(data.get("comments", []))
    review = data.get("reviewDecision") or "no review"
    return False, (f"PR #{PR_NUMBER} {data.get('state')}, "
                    f"review={review}, comments={comment_count}")


def check_released() -> tuple[bool, str]:
    """Check PyPI for a bd_warehouse release containing the fix.

    This is a heuristic: we check if the installed version's source contains
    `encoding="utf-8"` in fastener.py's data_resource.open() calls.
    """
    try:
        import bd_warehouse  # noqa: F401
        from importlib import resources
        import inspect
        from bd_warehouse import fastener
        src = inspect.getsource(fastener)
    except Exception as e:
        return False, f"bd_warehouse not importable: {e}"

    fixed = 'data_resource.open(encoding="utf-8"' in src
    if fixed:
        return True, (f"Installed bd_warehouse {bd_warehouse.__version__} "
                       f"already has the fix")
    return False, (f"Installed bd_warehouse {bd_warehouse.__version__} "
                    f"still uses bare .open()")


def print_upgrade_recipe() -> None:
    """Print the steps to remove the workaround once the fix lands."""
    print()
    print("=" * 70)
    print(" Upgrade recipe (apply when PR merged and released)")
    print("=" * 70)
    print("""
1. Bump pin in pyproject.toml:

     parts_library_bd = ["PyYAML>=6.0", "bd_warehouse>=X.Y.Z"]

   where X.Y.Z is the first release containing the fix.

2. Remove PYTHONUTF8=1 from CI workflows:

     - .github/workflows/tests.yml  (if present)
     - Any manual invocation notes in docs/PARTS_LIBRARY.md

3. Delete the exception wrapper in tests/test_parts_adapters.py:

     -def _try_import_bd_warehouse_bearing():
     -    \"\"\"Return the imported module or None...\"\"\"
     -    try:
     -        from bd_warehouse.bearing import SingleRowDeepGrooveBallBearing
     -        return SingleRowDeepGrooveBallBearing
     -    except Exception:
     -        return None

   Replace usage sites with direct imports:

     -cls = _try_import_bd_warehouse_bearing()
     -if cls is None:
     -    pytest.skip("bd_warehouse.bearing import failed")
     +pytest.importorskip("bd_warehouse.bearing")
     +from bd_warehouse.bearing import SingleRowDeepGrooveBallBearing as cls

4. Remove the Windows note from docs/PARTS_LIBRARY.md.

5. Re-run full test suite to confirm nothing depends on the workaround.
""")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check gumyr/bd_warehouse#75 merge status")
    parser.add_argument("--fix", action="store_true",
                        help="Print upgrade recipe if the fix is available")
    args = parser.parse_args()

    print(f"Checking {REPO} PR #{PR_NUMBER} ...")
    pr_merged, pr_msg = check_pr_merged()
    print(f"  PR status : {pr_msg}")

    print("Checking installed bd_warehouse ...")
    released, release_msg = check_released()
    print(f"  Release   : {release_msg}")

    available = pr_merged and released
    if available:
        print()
        print("✓ Fix is available — you can upgrade")
        if args.fix:
            print_upgrade_recipe()
        return 0

    print()
    if pr_merged and not released:
        print("○ PR merged but release not yet published or not installed")
        return 1
    if not pr_merged and released:
        print("○ Installed version has fix (maybe downstream patch) but "
              "upstream PR still open")
        return 1
    print("○ Not yet — PR open, no release")
    return 1


if __name__ == "__main__":
    sys.exit(main())
