"""Stable assembly entrypoint.

Generated scaffold lives in assembly.generated.py; manual layout overrides live
in assembly_layout.py. Re-running codegen --force refreshes only the generated
scaffold and this stable entrypoint.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import sys


_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def _load_module_from_file(filename: str, label: str):
    path = os.path.join(_HERE, filename)
    module_hash = hashlib.sha256(os.path.abspath(path).encode("utf-8")).hexdigest()[:12]
    module_name = f"_cad_spec_gen_{label}_{module_hash}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {label} module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_generated = _load_module_from_file("assembly.generated.py", "assembly_generated")
_layout = _load_module_from_file("assembly_layout.py", "assembly_layout")


def make_assembly():
    assy = _generated.make_assembly()
    apply_layout = getattr(_layout, "apply_layout", None)
    if callable(apply_layout):
        assy = apply_layout(assy)
    return assy


def export_assembly(output_dir: str, glb: bool = True) -> str:
    assy = make_assembly()
    assembly_part_no = getattr(_generated, "ASSEMBLY_PART_NO", "assembly")
    path = os.path.join(output_dir, f"{assembly_part_no}_assembly.step")
    assy.save(path, "STEP")
    print(f"Exported: {path}")
    if glb:
        glb_path = os.path.join(output_dir, f"{assembly_part_no}_assembly.glb")
        assy.save(glb_path, "GLTF")
        print(f"Exported: {glb_path}")
    return path


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    export_assembly(out)
