from pathlib import Path


def _write_assembly_module(directory: Path, tag: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "assembly.py").write_text(
        "def make_assembly():\n"
        f"    return {tag!r}\n",
        encoding="utf-8",
        newline="\n",
    )


def test_load_make_assembly_isolated_by_absolute_path(tmp_path):
    from tools.import_policy import load_make_assembly

    first = tmp_path / "cad" / "first"
    second = tmp_path / "cad" / "second"
    _write_assembly_module(first, "first")
    _write_assembly_module(second, "second")

    first_make = load_make_assembly(first)
    second_make = load_make_assembly(second)

    assert first_make() == "first"
    assert second_make() == "second"


def test_load_make_assembly_reloads_changed_file_without_sys_modules_alias(tmp_path):
    from tools.import_policy import load_make_assembly

    subsystem_dir = tmp_path / "cad" / "demo"
    _write_assembly_module(subsystem_dir, "before")
    first_make = load_make_assembly(subsystem_dir)
    _write_assembly_module(subsystem_dir, "after")

    second_make = load_make_assembly(subsystem_dir)

    assert first_make() == "before"
    assert second_make() == "after"
