"""Tests for schema versioning invariants (Phase 6)."""
import sys
from pathlib import Path

import pytest
import yaml

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def test_init_creates_schema_version_1():
    """cad-lib init must write schema_version: 1 to all 3 YAML files."""
    from cad_spec_gen.cad_lib import main, _get_home
    main(["init", "--force"])
    home = _get_home()
    for path in [
        home / "shared" / "library.yaml",
        home / "state" / "installed.yaml",
        home / "state" / "suggestions.yaml",
    ]:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data["schema_version"] == 1, \
            f"{path.name} has schema_version={data.get('schema_version')}"


def test_migrate_stub_rejects_unknown_version():
    """cad-lib migrate must exit non-zero on unknown schema_version."""
    from cad_spec_gen.cad_lib import main, _get_home
    main(["init", "--force"])
    home = _get_home()
    # Tamper with library.yaml to have unknown version
    lib_file = home / "shared" / "library.yaml"
    lib_file.write_text(
        "schema_version: 99\n"
        "routing: []\n"
        "materials: {}\n"
        "template_keywords: {}\n",
        encoding="utf-8",
    )
    exit_code = main(["migrate"])
    assert exit_code != 0, "migrate should reject unknown version"


def test_migrate_stub_accepts_v1():
    """cad-lib migrate on a fresh init must exit 0 (all schemas are v1)."""
    from cad_spec_gen.cad_lib import main
    main(["init", "--force"])
    exit_code = main(["migrate"])
    assert exit_code == 0, "migrate should accept v1 schemas"


def test_library_yaml_round_trip_preserves_unknown_keys():
    """Readers must preserve unknown top-level keys when round-tripping.

    Scenario: user adds an experimental_flag or future_section to library.yaml
    and re-saves via yaml.safe_dump. The content must still be intact on
    re-read.
    """
    from cad_spec_gen.cad_lib import main, _get_home
    main(["init", "--force"])
    home = _get_home()
    lib_file = home / "shared" / "library.yaml"

    # Read current content, add unknown keys, write back
    original = yaml.safe_load(lib_file.read_text(encoding="utf-8"))
    assert original.get("schema_version") == 1
    original["experimental_flag"] = True
    original["future_section"] = {"foo": "bar"}
    lib_file.write_text(
        yaml.safe_dump(original, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )

    # Re-read and verify the keys survive
    round_tripped = yaml.safe_load(lib_file.read_text(encoding="utf-8"))
    assert round_tripped.get("experimental_flag") is True
    assert round_tripped.get("future_section") == {"foo": "bar"}
    assert round_tripped.get("schema_version") == 1
    # Original keys still present
    assert "routing" in round_tripped
    assert "materials" in round_tripped
    assert "template_keywords" in round_tripped


def test_migrate_preserves_unknown_top_level_keys():
    """cad-lib migrate must not drop unknown top-level keys when checking versions.

    Spec §10.3 invariant #3: readers must preserve unknown keys round-trip.
    """
    from cad_spec_gen.cad_lib import main, _get_home
    main(["init", "--force"])
    home = _get_home()
    lib_file = home / "shared" / "library.yaml"

    # Add an unknown key
    data = yaml.safe_load(lib_file.read_text(encoding="utf-8"))
    data["my_custom_extension"] = "preserve_me"
    lib_file.write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )

    # Run migrate (should pass — schema_version is still 1)
    exit_code = main(["migrate"])
    assert exit_code == 0

    # Verify the custom extension survived
    after = yaml.safe_load(lib_file.read_text(encoding="utf-8"))
    assert after.get("my_custom_extension") == "preserve_me", \
        "migrate dropped unknown top-level key"
