from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LIFTING_RENDER_CONFIG = ROOT / "cad" / "lifting_platform" / "render_config.json"
CANONICAL_RENDER_3D = ROOT / "src" / "cad_spec_gen" / "render_3d.py"
DEPLOYED_RENDER_3D = ROOT / "cad" / "lifting_platform" / "render_3d.py"
CANONICAL_RENDER_CONFIG = ROOT / "render_config.py"
DEPLOYED_RENDER_CONFIG = ROOT / "cad" / "lifting_platform" / "render_config.py"


def _load_cad_pipeline():
    spec = importlib.util.spec_from_file_location(
        "cad_pipeline_under_test",
        ROOT / "cad_pipeline.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lifting_platform_render_runtime_scripts_match_canonical_sources():
    """The lifting_platform Blender runtime copy must include BOM material bridging."""
    assert DEPLOYED_RENDER_3D.read_text(encoding="utf-8") == (
        CANONICAL_RENDER_3D.read_text(encoding="utf-8")
    )
    assert DEPLOYED_RENDER_CONFIG.read_text(encoding="utf-8") == (
        CANONICAL_RENDER_CONFIG.read_text(encoding="utf-8")
    )


def test_lifting_platform_render_config_has_valid_material_references():
    pipeline = _load_cad_pipeline()

    warnings = pipeline._validate_render_config(str(LIFTING_RENDER_CONFIG))

    assert warnings == []


def test_lifting_platform_glb_nodes_resolve_to_configured_materials():
    pipeline = _load_cad_pipeline()
    rc = json.loads(LIFTING_RENDER_CONFIG.read_text(encoding="utf-8"))
    mesh_nodes = [
        "SLP-100",
        "SLP-200",
        "SLP-201",
        "SLP-300",
        "SLP-400",
        "SLP-403",
        "SLP-404",
        "SLP-500",
        "SLP-P01-LS1",
        "SLP-P01-LS2",
        "SLP-P02-GS1",
        "SLP-P02-GS2",
        "STD-SLP-C02-GS1",
        "STD-SLP-C02-GS2",
        "STD-SLP-C03-LS1-BOT",
        "STD-SLP-C03-LS2-BOT",
        "STD-SLP-C03-LS1-TOP",
        "STD-SLP-C03-LS2-TOP",
        "STD-SLP-C06",
        "STD-SLP-C07",
        "STD-SLP-F11",
        "STD-SLP-F12-LOW",
        "STD-SLP-F12-HIGH",
    ]

    assignments = pipeline._simulate_render_material_assignment(rc, mesh_nodes)
    unmatched = [a["node"] for a in assignments if a["reason"] == "default_gray"]

    assert unmatched == []
