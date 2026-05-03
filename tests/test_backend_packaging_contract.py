"""增强后端工具必须被打包并被安装向导复制。"""

from __future__ import annotations

import sys
from pathlib import Path


def test_all_enhance_backend_helpers_are_registered_for_build_and_install():
    src = Path(__file__).resolve().parents[1] / "src"
    if str(src) in sys.path:
        sys.path.remove(str(src))
    sys.path.insert(0, str(src))
    loaded = sys.modules.get("cad_spec_gen")
    if loaded is not None and not hasattr(loaded, "__path__"):
        del sys.modules["cad_spec_gen"]

    from cad_spec_gen.wizard import skill_register
    import hatch_build

    required = {
        "comfyui_enhancer.py",
        "comfyui_env_check.py",
        "fal_enhancer.py",
        "fal_comfy_enhancer.py",
        "fal_comfy_env_check.py",
        "engineering_enhancer.py",
    }

    assert required <= set(hatch_build.PYTHON_TOOLS)
    assert required <= set(skill_register.PYTHON_TOOLS)


def test_runtime_assembly_validator_is_registered_for_build_and_install():
    src = Path(__file__).resolve().parents[1] / "src"
    if str(src) in sys.path:
        sys.path.remove(str(src))
    sys.path.insert(0, str(src))
    loaded = sys.modules.get("cad_spec_gen")
    if loaded is not None and not hasattr(loaded, "__path__"):
        del sys.modules["cad_spec_gen"]

    from cad_spec_gen.wizard import skill_register
    import hatch_build

    assert "assembly_validator.py" in hatch_build.PYTHON_TOOLS
    assert "assembly_validator.py" in skill_register.PYTHON_TOOLS
    assert "tools" in skill_register.COPY_DIRS
    assert hatch_build.COPY_DIRS["tools"] == "tools"


def test_contract_gate_tools_are_mirrored_for_packaged_installs():
    root = Path(__file__).resolve().parents[1]

    for tool_name in [
        "assembly_signature.py",
        "change_scope.py",
        "import_policy.py",
        "enhance_consistency.py",
        "model_contract.py",
        "photo3d_gate.py",
        "render_qa.py",
    ]:
        source = root / "tools" / tool_name
        mirror = root / "src" / "cad_spec_gen" / "data" / "tools" / tool_name
        assert mirror.is_file(), f"missing packaged mirror for {tool_name}"
        assert mirror.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
