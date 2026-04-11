# tests/fixtures/real_doc_boms/_regenerate.py
"""One-off helper to regenerate BOM YAML fixtures from source design docs.

Run manually when source design docs change:
    python tests/fixtures/real_doc_boms/_regenerate.py

NEVER writes anywhere except tests/fixtures/real_doc_boms/*.yaml.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

from cad_spec_extractors import extract_bom  # noqa: E402

_SOURCES = {
    "end_effector": Path("D:/Work/cad-tests/04-末端执行机构设计.md"),
    "lifting_platform": Path("D:/Work/cad-tests/19-液压钳升降平台设计.md"),
}

_OUT_DIR = Path(__file__).resolve().parent


def main() -> int:
    for name, source in _SOURCES.items():
        if not source.exists():
            print(f"[skip] {name}: source not found at {source}")
            continue
        bom = extract_bom(str(source))
        if bom is None:
            print(f"[skip] {name}: extract_bom returned None")
            continue
        out_path = _OUT_DIR / f"{name}.yaml"
        out_path.write_text(
            yaml.safe_dump(bom, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        print(f"[ok] {name}: wrote {len(bom.get('assemblies', []))} assemblies to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
