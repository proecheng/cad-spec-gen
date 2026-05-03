"""Photo3D 契约工具的打包同步总线。"""

from __future__ import annotations

import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]

PHOTO3D_CONTRACT_TOOL_FILES = {
    "artifact_index.py",
    "assembly_signature.py",
    "change_scope.py",
    "contract_io.py",
    "enhance_consistency.py",
    "import_policy.py",
    "layout_contract.py",
    "model_contract.py",
    "path_policy.py",
    "photo3d_actions.py",
    "photo3d_gate.py",
    "product_graph.py",
    "render_qa.py",
    "run_manifest.py",
}


def test_photo3d_contract_tools_have_packaged_mirrors():
    for tool_name in sorted(PHOTO3D_CONTRACT_TOOL_FILES):
        source = _ROOT / "tools" / tool_name
        mirror = _ROOT / "src" / "cad_spec_gen" / "data" / "tools" / tool_name

        assert source.is_file(), f"missing source tool: {tool_name}"
        assert mirror.is_file(), f"missing packaged mirror: {tool_name}"
        assert mirror.read_bytes() == source.read_bytes(), (
            f"packaged mirror drifted for tools/{tool_name}"
        )


def test_build_and_install_copy_the_tools_directory():
    src = _ROOT / "src"
    if str(src) in sys.path:
        sys.path.remove(str(src))
    sys.path.insert(0, str(src))
    loaded = sys.modules.get("cad_spec_gen")
    if loaded is not None and not hasattr(loaded, "__path__"):
        del sys.modules["cad_spec_gen"]

    from cad_spec_gen.wizard import skill_register
    import hatch_build

    assert hatch_build.COPY_DIRS["tools"] == "tools"
    assert "tools" in skill_register.COPY_DIRS


def test_dev_sync_covers_photo3d_contract_tool_mirrors():
    from scripts import dev_sync

    changed = dev_sync.check(_ROOT)

    mirrored_tools = {
        str(path.relative_to(_ROOT)).replace("\\", "/")
        for path in changed
        if "src/cad_spec_gen/data/tools/" in str(path.relative_to(_ROOT)).replace(
            "\\", "/"
        )
    }

    assert mirrored_tools == set(), (
        "photo3d contract packaged mirrors are out of sync: "
        f"{sorted(mirrored_tools)}"
    )
