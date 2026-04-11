"""Hatch custom build hook: assemble data/ from root-level project files.

This copies Python tools, templates, codegen, config, commands, and knowledge
files into src/cad_spec_gen/data/ before wheel assembly, so the PyPI package
contains everything needed by the setup wizard.
"""

import os
import shutil
from pathlib import Path
from hatchling.builders.hooks.plugin.interface import BuildHookInterface


# Files from project root → data/python_tools/
# NOTE: SHARED_TOOL_FILES (drawing.py, cq_to_dxf.py, etc.) are appended
# from cad_paths.py to ensure a single source of truth.
_PIPELINE_TOOLS = [
    "cad_pipeline.py",
    "cad_spec_gen.py",
    "cad_spec_extractors.py",
    "cad_spec_section_walker.py",
    "cad_spec_reviewer.py",
    "cad_paths.py",
    "bom_parser.py",
    "annotate_render.py",
    "enhance_prompt.py",
    "prompt_data_builder.py",
    "gemini_gen.py",
    "comfyui_enhancer.py",
    "comfyui_env_check.py",
    "fal_enhancer.py",
    "pipeline_config.json",
]

# Import shared tool list from cad_paths (single source of truth)
try:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent))
    from cad_paths import SHARED_TOOL_FILES as _SHARED
except ImportError:
    # Hardcoded fallback for isolated build environments (pip wheel)
    # Keep in sync with cad_paths.py SHARED_TOOL_FILES
    _SHARED = ["drawing.py", "draw_three_view.py", "cq_to_dxf.py",
               "render_dxf.py", "render_config.py", "cad_spec_defaults.py"]

PYTHON_TOOLS = _PIPELINE_TOOLS + list(_SHARED)

# Directories to copy as-is
COPY_DIRS = {
    "codegen": "codegen",
    "config": "config",
    "templates": "templates",
}

# Spec 1 Phase 5: top-level files shipped as data payload inside the wheel.
# These land at src/cad_spec_gen/data/<basename> at build time.
TOP_LEVEL_FILES = {
    "parts_library.default.yaml": "parts_library.default.yaml",
}

# Command files (zh from .claude/commands/, en hand-written in data/commands/en/)
COMMAND_SOURCE = ".claude/commands"


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        root = Path(self.root)
        data_dir = root / "src" / "cad_spec_gen" / "data"

        # --- python_tools/ ---
        tools_dir = data_dir / "python_tools"
        tools_dir.mkdir(parents=True, exist_ok=True)
        for fname in PYTHON_TOOLS:
            src = root / fname
            if src.exists():
                shutil.copy2(src, tools_dir / fname)

        # --- directories (codegen, config, templates) ---
        for src_name, dst_name in COPY_DIRS.items():
            src = root / src_name
            dst = data_dir / dst_name
            if src.is_dir():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst, dirs_exist_ok=True)

        # --- commands/zh/ from adapters ---
        cmd_src = root / COMMAND_SOURCE
        cmd_zh = data_dir / "commands" / "zh"
        cmd_zh.mkdir(parents=True, exist_ok=True)
        if cmd_src.is_dir():
            for md in cmd_src.glob("*.md"):
                shutil.copy2(md, cmd_zh / md.name)

        # --- knowledge/*_zh.md ---
        knowledge_dir = data_dir / "knowledge"
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        zh_help = root / "skill_cad_help.md"
        if zh_help.exists():
            shutil.copy2(zh_help, knowledge_dir / "skill_cad_help_zh.md")
        zh_mech = root / "skill_mech_design.md"
        if zh_mech.exists():
            shutil.copy2(zh_mech, knowledge_dir / "skill_mech_design_zh.md")

        # --- system_prompt.md ---
        sys_prompt = root / "system_prompt.md"
        if sys_prompt.exists():
            shutil.copy2(sys_prompt, data_dir / "system_prompt.md")

        # --- Spec 1 Phase 5: copy top-level data files (parts_library.default.yaml, etc.) ---
        for src_name, dest_rel in TOP_LEVEL_FILES.items():
            src_path = root / src_name
            if not src_path.exists():
                continue
            dest_path = data_dir / dest_rel
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dest_path)
