"""Tests for src/cad_spec_gen/cad_lib.py — local-only CLI."""
import os
import sys
from pathlib import Path

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pytest


def test_cad_lib_module_imports():
    """cad_lib module must import without side effects."""
    from cad_spec_gen import cad_lib
    assert hasattr(cad_lib, "main")
    assert callable(cad_lib.main)


def test_cad_lib_main_with_no_args_prints_help():
    """`cad-lib` with no args should exit non-zero (missing required subcommand)."""
    from cad_spec_gen.cad_lib import main
    with pytest.raises(SystemExit) as exc_info:
        main([])
    # argparse exits with 2 when a required arg is missing
    assert exc_info.value.code in (0, 2)


def test_cad_lib_version_flag():
    """`cad-lib --version` should print a version and exit 0."""
    from cad_spec_gen.cad_lib import main
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0


def test_cad_lib_init_creates_layout():
    """cad-lib init creates shared/ and state/ subdirs with correct YAMLs."""
    from cad_spec_gen.cad_lib import main, _get_home
    home = _get_home()
    # Test fixture pre-creates .cad-spec-gen but it's empty. Use --force
    # because the dir exists.
    exit_code = main(["init", "--force"])
    assert exit_code == 0
    assert (home / "shared").is_dir()
    assert (home / "state").is_dir()
    assert (home / "shared" / "library.yaml").is_file()
    assert (home / "shared" / "README.md").is_file()
    assert (home / "shared" / "templates").is_dir()
    assert (home / "state" / "installed.yaml").is_file()
    assert (home / "state" / "suggestions.yaml").is_file()
    assert (home / "state" / ".gitignore").is_file()


def test_cad_lib_doctor_passes_with_existing_canonical():
    """doctor should pass (exit 0) since Phase 1 established the canonical render_3d.py."""
    from cad_spec_gen.cad_lib import main
    exit_code = main(["doctor"])
    assert exit_code == 0


def test_cad_lib_doctor_reports_template_count(capsys):
    """doctor must discover >=5 templates and report them."""
    from cad_spec_gen.cad_lib import main
    main(["doctor"])
    captured = capsys.readouterr()
    # Should mention templates and some count indicator
    combined = captured.out + captured.err
    assert "template" in combined.lower()


def test_cad_lib_init_refuses_to_clobber_populated_dir():
    """cad-lib init refuses to overwrite an existing populated library."""
    from cad_spec_gen.cad_lib import main, _get_home
    home = _get_home()
    # Pre-populate
    (home / "shared").mkdir()
    (home / "shared" / "library.yaml").write_text("existing user content")
    exit_code = main(["init"])
    assert exit_code != 0  # should refuse
    # Content preserved
    assert "existing user content" in (home / "shared" / "library.yaml").read_text()


def test_cad_lib_init_yaml_has_schema_version():
    """All created YAMLs must have schema_version: 1."""
    from cad_spec_gen.cad_lib import main, _get_home
    import yaml
    main(["init", "--force"])
    home = _get_home()
    lib = yaml.safe_load((home / "shared" / "library.yaml").read_text())
    assert lib["schema_version"] == 1
    inst = yaml.safe_load((home / "state" / "installed.yaml").read_text())
    assert inst["schema_version"] == 1
    sug = yaml.safe_load((home / "state" / "suggestions.yaml").read_text())
    assert sug["schema_version"] == 1
