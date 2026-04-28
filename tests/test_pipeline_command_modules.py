"""cad_pipeline 命令实现应能按阶段拆分导入。"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


def test_pipeline_command_modules_exist_for_major_phases():
    src = Path(__file__).resolve().parents[1] / "src"
    if str(src) in sys.path:
        sys.path.remove(str(src))
    sys.path.insert(0, str(src))
    loaded = sys.modules.get("cad_spec_gen")
    if loaded is not None and not hasattr(loaded, "__path__"):
        del sys.modules["cad_spec_gen"]

    for name in ("spec", "codegen", "build", "render", "enhance", "annotate"):
        mod = importlib.import_module(f"cad_spec_gen.pipeline.commands.{name}")
        assert hasattr(mod, "run")
        assert callable(mod.run)
