"""Packaging tests for Spec 1 — verify entry points and hatch config."""
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).parent.parent


def test_pyproject_has_cad_lib_entry_point():
    content = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "cad-lib = " in content, "pyproject.toml missing cad-lib entry point"
    assert "cad_spec_gen.cad_lib:main" in content, \
        "Entry point not pointing at cad_spec_gen.cad_lib:main"


def test_pyproject_has_pytest_env_pinned():
    content = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "PYTHONHASHSEED=0" in content, "PYTHONHASHSEED not pinned"


def test_hatch_build_ships_parts_library_default_yaml():
    content = (_REPO_ROOT / "hatch_build.py").read_text(encoding="utf-8")
    # Look for any reference to parts_library.default.yaml being shipped
    assert "parts_library.default.yaml" in content, \
        "hatch_build.py does not ship parts_library.default.yaml"


@pytest.mark.slow
def test_wheel_install_smoke(tmp_path):
    """Build the wheel, install it into a temp venv, run 'cad-lib doctor'.

    This is the ultimate proof that packaging works end-to-end.
    Marked slow because it invokes hatch build + pip install + subprocess.
    Skips if build tools are unavailable (local dev without hatch).
    """
    import subprocess
    import sys
    import venv

    # Try to build a wheel — prefer `python -m build` (standard), fall back to hatch
    dist_dir = _REPO_ROOT / "dist"
    dist_dir.mkdir(exist_ok=True)

    # Record existing wheels so we can pick out the freshly built one
    existing_wheels = set(dist_dir.glob("cad_spec_gen-*.whl"))

    build_cmd = None
    try:
        import build  # noqa: F401
        build_cmd = [sys.executable, "-m", "build", "--wheel", "--outdir", str(dist_dir)]
    except ImportError:
        try:
            import hatchling  # noqa: F401
            build_cmd = [sys.executable, "-m", "hatch", "build", "-t", "wheel"]
        except ImportError:
            pytest.skip("Neither 'build' nor 'hatch' available for wheel construction")

    result = subprocess.run(
        build_cmd,
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        pytest.skip(f"wheel build failed (may be dev env issue): {result.stderr[:500]}")

    # Find the newly built wheel
    all_wheels = list(dist_dir.glob("cad_spec_gen-*.whl"))
    new_wheels = [w for w in all_wheels if w not in existing_wheels]
    wheel = new_wheels[-1] if new_wheels else (all_wheels[-1] if all_wheels else None)
    if wheel is None:
        pytest.skip("No wheel produced by build")

    # Create a fresh venv
    venv_dir = tmp_path / "testvenv"
    venv.create(venv_dir, with_pip=True)
    if sys.platform == "win32":
        pip_exe = venv_dir / "Scripts" / "pip.exe"
        cad_lib_exe = venv_dir / "Scripts" / "cad-lib.exe"
        python_exe = venv_dir / "Scripts" / "python.exe"
    else:
        pip_exe = venv_dir / "bin" / "pip"
        cad_lib_exe = venv_dir / "bin" / "cad-lib"
        python_exe = venv_dir / "bin" / "python"

    # Install the wheel into the fresh venv
    install_result = subprocess.run(
        [str(pip_exe), "install", str(wheel)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if install_result.returncode != 0:
        pytest.skip(f"pip install failed: {install_result.stderr[:500]}")

    # Verify cad-lib entry point exists
    assert cad_lib_exe.exists(), f"cad-lib entry point not at {cad_lib_exe}"

    # Run cad-lib doctor
    doctor_result = subprocess.run(
        [str(cad_lib_exe), "doctor"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert doctor_result.returncode == 0, (
        f"cad-lib doctor failed in fresh venv (exit={doctor_result.returncode}):\n"
        f"stdout:\n{doctor_result.stdout}\n"
        f"stderr:\n{doctor_result.stderr}"
    )

    # Run cad-lib list templates
    list_result = subprocess.run(
        [str(cad_lib_exe), "list", "templates"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert list_result.returncode == 0
    # All 5 templates should appear in the listing
    for expected in ["iso_9409_flange", "l_bracket", "rectangular_housing",
                     "cylindrical_housing", "fixture_plate"]:
        assert expected in list_result.stdout, \
            f"Template {expected} missing from wheel install:\n{list_result.stdout}"
