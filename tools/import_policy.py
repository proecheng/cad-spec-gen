from __future__ import annotations

import hashlib
import sys
import types
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator


def load_make_assembly(subsystem_dir: str | Path) -> Callable[[], object]:
    """Load make_assembly() from a subsystem assembly.py by absolute path."""
    root = Path(subsystem_dir).resolve()
    assembly_path = root / "assembly.py"
    if not assembly_path.is_file():
        raise FileNotFoundError(f"assembly.py not found: {assembly_path}")

    module_name = "_cad_spec_gen_assembly_" + hashlib.sha256(
        str(assembly_path).encode("utf-8")
    ).hexdigest()[:16]
    source = assembly_path.read_text(encoding="utf-8")
    module = types.ModuleType(module_name)
    module.__file__ = str(assembly_path)
    module.__package__ = ""

    with _isolated_local_imports(root):
        exec(compile(source, str(assembly_path), "exec"), module.__dict__)

    raw_make_assembly = module.__dict__.get("make_assembly")
    if not callable(raw_make_assembly):
        raise AttributeError(f"make_assembly() not found in {assembly_path}")

    def _wrapped_make_assembly():
        with _isolated_local_imports(root):
            return raw_make_assembly()

    return _wrapped_make_assembly


@contextmanager
def _isolated_local_imports(subsystem_dir: Path) -> Iterator[None]:
    """Temporarily prefer subsystem-local modules and avoid stale local imports."""
    local_module_names = _local_module_names(subsystem_dir)
    previous_modules = {
        name: sys.modules[name]
        for name in local_module_names
        if name in sys.modules
    }
    previous_path = list(sys.path)
    for name in local_module_names:
        sys.modules.pop(name, None)
    sys.path.insert(0, str(subsystem_dir))
    try:
        yield
    finally:
        for name in local_module_names:
            sys.modules.pop(name, None)
        sys.modules.update(previous_modules)
        sys.path[:] = previous_path


def _local_module_names(subsystem_dir: Path) -> set[str]:
    names = {"assembly", "params"}
    for path in subsystem_dir.glob("*.py"):
        names.add(path.stem)
    return names
