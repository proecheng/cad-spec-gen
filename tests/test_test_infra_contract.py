"""测试基础设施治理契约。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]

PHOTO3D_CONTRACT_TEST_FILES = {
    "test_contract_io.py",
    "test_path_context_contract.py",
    "test_artifact_index_contract.py",
    "test_run_manifest_isolation.py",
    "test_product_graph_contract.py",
    "test_model_contract.py",
    "test_assembly_signature_contract.py",
    "test_assembly_import_isolation.py",
    "test_change_scope_gate.py",
    "test_render_manifest_signature.py",
    "test_render_qa.py",
    "test_render_manifest_no_fallback.py",
    "test_photo3d_stale_artifacts.py",
    "test_photo3d_gate_contract.py",
    "test_photo3d_gate_matrix.py",
    "test_photo3d_path_drift.py",
    "test_photo3d_baseline_binding.py",
    "test_photo3d_accept_baseline.py",
    "test_photo3d_autopilot.py",
    "test_enhance_consistency.py",
    "test_photo3d_llm_action_plan.py",
    "test_layout_contract.py",
    "test_photo3d_packaging_sync.py",
}

REAL_BLENDER_SMOKE_TEST_FILES = {
    "test_render_3d_blender_smoke.py",
    "test_render_3d_cadquery_axis_correction.py",
    "test_render_3d_texture_bridge.py",
}


def test_optional_marker_is_registered():
    text = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"optional:' in text


def test_photo3d_contract_marker_is_registered():
    text = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"photo3d_contract:' in text


def test_photo3d_contract_files_are_auto_classified_by_conftest():
    import conftest

    registered = set(conftest.PHOTO3D_CONTRACT_TEST_FILES)

    missing = PHOTO3D_CONTRACT_TEST_FILES - registered
    assert not missing, f"photo3d_contract 测试未纳入总线: {sorted(missing)}"

    unexpected_real_smoke = REAL_BLENDER_SMOKE_TEST_FILES & registered
    assert not unexpected_real_smoke, (
        "真实 Blender smoke 不能进入默认 photo3d_contract 总线: "
        f"{sorted(unexpected_real_smoke)}"
    )


def test_photo3d_contract_marker_is_added_without_manual_test_marks():
    import conftest

    class FakeItem:
        def __init__(self, filename: str):
            self.path = _ROOT / "tests" / filename
            self._markers = {}

        def get_closest_marker(self, name: str):
            return self._markers.get(name)

        def add_marker(self, marker):
            self._markers[marker.name] = marker

    contract_item = FakeItem("test_photo3d_gate_matrix.py")
    ordinary_item = FakeItem("test_version_contract.py")

    conftest._mark_photo3d_contract_tests([contract_item, ordinary_item])

    assert contract_item.get_closest_marker("photo3d_contract") is not None
    assert ordinary_item.get_closest_marker("photo3d_contract") is None


def test_photo3d_contract_marker_is_added_before_mark_selection():
    import conftest

    marker_impl = getattr(conftest.pytest_collection_modifyitems, "pytest_impl", {})
    assert marker_impl.get("tryfirst") is True


def test_photo3d_contract_marker_expression_selects_contract_bus():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_photo3d_packaging_sync.py",
            "-m",
            "photo3d_contract",
            "--collect-only",
            "-q",
        ],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "test_photo3d_packaging_sync.py::" in result.stdout
    assert "0 tests collected" not in result.stdout


def test_photo3d_contract_tests_are_not_capability_skipped_by_default():
    forbidden_markers = {
        "blender",
        "requires_solidworks",
        "real_subprocess",
        "optional",
        "slow",
    }

    for filename in PHOTO3D_CONTRACT_TEST_FILES:
        text = (_ROOT / "tests" / filename).read_text(encoding="utf-8")
        for marker in forbidden_markers:
            assert f"pytestmark = pytest.mark.{marker}" not in text
            assert f"@pytest.mark.{marker}" not in text


def test_real_blender_smoke_tests_remain_skip_capable_and_out_of_default_bus():
    for filename in REAL_BLENDER_SMOKE_TEST_FILES:
        text = (_ROOT / "tests" / filename).read_text(encoding="utf-8")
        assert "pytest.mark.blender" in text
        assert "skipif" in text


def test_ci_marker_expression_does_not_exclude_photo3d_contract_tests():
    text = (_ROOT / ".github" / "workflows" / "tests.yml").read_text(
        encoding="utf-8"
    )
    assert "not photo3d_contract" not in text


def test_packaging_smoke_does_not_skip_build_failures_on_ci():
    text = (_ROOT / "tests" / "test_packaging.py").read_text(encoding="utf-8")
    assert "_skip_or_fail_packaging" in text
    assert "os.environ.get(\"CI\")" in text


def test_ci_installs_packaging_build_tools_for_wheel_smoke():
    text = (_ROOT / ".github" / "workflows" / "tests.yml").read_text(
        encoding="utf-8"
    )
    assert "pip install build hatchling" in text


def test_ci_sync_materializes_then_checks_tracked_drift():
    text = (_ROOT / ".github" / "workflows" / "tests.yml").read_text(
        encoding="utf-8"
    )
    assert "python scripts/dev_sync.py || rc=$?" in text
    assert "git diff --exit-code -- AGENTS.md" in text
    assert "python scripts/dev_sync.py --check" in text


def test_local_runtime_noise_is_gitignored():
    ignore = (_ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in (".coverage", "htmlcov/", ".serena/"):
        assert pattern in ignore


def test_ci_upload_artifacts_use_node24_action_major():
    workflow_paths = sorted((_ROOT / ".github" / "workflows").glob("*.yml"))

    for path in workflow_paths:
        text = path.read_text(encoding="utf-8")
        assert "actions/upload-artifact@v4" not in text
        assert "actions/upload-artifact@v7" in text or "upload-artifact" not in text
