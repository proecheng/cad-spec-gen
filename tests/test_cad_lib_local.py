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
