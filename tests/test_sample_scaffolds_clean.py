"""Repository sample scaffolds should not carry naked TODO markers."""

from pathlib import Path


def test_tracked_cad_samples_have_no_naked_todo_markers():
    root = Path(__file__).resolve().parents[1]
    files = [
        *sorted((root / "cad" / "end_effector").glob("*.py")),
        *sorted((root / "cad" / "lifting_platform").glob("*.py")),
        root / "cad_spec_defaults.py",
    ]
    offenders = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        if "TODO:" in text or "TODO(P3): axial_gap" in text:
            offenders.append(str(path.relative_to(root)))
    assert offenders == []
