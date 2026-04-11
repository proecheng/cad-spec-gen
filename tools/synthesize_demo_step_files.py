#!/usr/bin/env python3
"""
synthesize_demo_step_files.py — CLI wrapper around vendor_synthesizer.

As of v2.8.2-dev the factory functions that build parametric stand-ins for
Maxon / LEMO / ATI parts live in `adapters/parts/vendor_synthesizer.py`, and
`step_pool_adapter` auto-invokes them into the shared cache
(`~/.cad-spec-gen/step_cache/`) the first time a project needs each file.

This tool remains as a manual bootstrap helper for users who want to pre-
populate the cache (e.g. for offline runs) or write the STEPs to a custom
directory (`--out <DIR>`). The default behavior is to warm the shared cache.

Usage:
    python tools/synthesize_demo_step_files.py                # warm shared cache
    python tools/synthesize_demo_step_files.py --out ./parts  # custom root
    python tools/synthesize_demo_step_files.py --force        # overwrite existing
    python tools/synthesize_demo_step_files.py --list         # list registered IDs

Real STEP files from vendor websites should always replace these parametric
stand-ins when available:
  - Maxon GP22C reducer:     https://www.maxongroup.com/maxon/view/product/110364
  - Maxon ECX SPEED 22L:     https://www.maxongroup.com/maxon/view/product/473797
  - LEMO FGG.0B.307 plug:    https://www.lemo.com/en/products/series/fgg-0b
  - ATI Nano17 force sensor: https://www.ati-ia.com/products/ft/ft_models.aspx?id=Nano17
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Ensure the project root is on sys.path so `adapters.parts.*` imports
# resolve when the tool is run directly from the tools/ directory.
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from adapters.parts.vendor_synthesizer import (  # noqa: E402
    SYNTHESIZERS,
    default_cache_root,
    list_factory_ids,
    synthesize_to_cache,
)


# Default cache layout kept in lockstep with parts_library.default.yaml
DEFAULT_PATHS: dict[str, tuple[str, str]] = {
    "maxon_ecx_22l": ("maxon/ecx_22l.step", "Maxon ECX SPEED 22L motor"),
    "maxon_gp22c": ("maxon/gp22c.step", "Maxon GP22C 53:1 reducer"),
    "lemo_fgg_0b_307": ("lemo/fgg_0b_307.step", "LEMO FGG.0B.307 plug"),
    "ati_nano17": ("ati/nano17.step", "ATI Nano17 6-axis F/T sensor"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=None,
        help="Custom output root (default: shared cache "
             "~/.cad-spec-gen/step_cache/ or $CAD_SPEC_GEN_STEP_CACHE).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-synthesize even if a target STEP already exists.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List registered factory IDs and exit.",
    )
    args = parser.parse_args()

    if args.list:
        print("Registered vendor factories:")
        for fid in list_factory_ids():
            rel, desc = DEFAULT_PATHS.get(fid, ("", ""))
            print(f"  {fid:20s} → {rel}  {desc}")
        return 0

    # Honor --out by temporarily overriding the cache root via the env var.
    if args.out:
        os.environ["CAD_SPEC_GEN_STEP_CACHE"] = args.out

    cache_root = default_cache_root()
    print(f"Synthesizing demo vendor STEP files into: {cache_root}")
    print()

    written = 0
    skipped = 0
    for fid, (rel, desc) in DEFAULT_PATHS.items():
        target = cache_root / rel
        exists_before = target.exists()
        result = synthesize_to_cache(fid, rel, overwrite=args.force)
        if result is None:
            print(f"  ! {rel}")
            print(f"      {desc}")
            print(f"      FAILED — see stderr for details")
            continue
        if exists_before and not args.force:
            print(f"  · {rel}   (exists, skip; pass --force to overwrite)")
            print(f"      {desc}")
            skipped += 1
        else:
            print(f"  + {rel}")
            print(f"      {desc}")
            written += 1
        print()

    total = len(DEFAULT_PATHS)
    print(f"Done. {written} written, {skipped} skipped, total {total} parts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
