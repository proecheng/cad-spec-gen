# tests/test_conftest_tripwire.py
"""Meta-tests for the conftest.py autouse fixture."""
import os
from pathlib import Path


def test_home_is_redirected():
    """Path.home() must point inside tmp_path, not the real user home."""
    home = Path.home()
    assert "fake_home" in str(home), f"Expected fake_home in {home}"


def test_cad_spec_gen_home_env_set():
    """CAD_SPEC_GEN_HOME env var must be set to the fake home."""
    val = os.environ.get("CAD_SPEC_GEN_HOME", "")
    assert "fake_home" in val, f"Expected fake_home in CAD_SPEC_GEN_HOME={val}"


def test_fake_cad_spec_gen_dir_exists():
    """The fake ~/.cad-spec-gen directory is pre-created for us."""
    fake_dir = Path.home() / ".cad-spec-gen"
    assert fake_dir.exists()
    assert fake_dir.is_dir()
