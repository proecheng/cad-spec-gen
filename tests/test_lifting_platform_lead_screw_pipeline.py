import json
from pathlib import Path

from codegen.gen_std_parts import generate_std_part_files


ROOT = Path(__file__).resolve().parent.parent
LIFTING_SPEC = ROOT / "cad" / "lifting_platform" / "CAD_SPEC.md"
LIFTING_DIR = ROOT / "cad" / "lifting_platform"


def test_lifting_platform_lead_screw_is_reported_as_parametric_template():
    generated, skipped, resolver, pending = generate_std_part_files(
        str(LIFTING_SPEC),
        str(LIFTING_DIR),
        mode="force",
    )

    std_p01 = LIFTING_DIR / "std_p01.py"
    assert std_p01.is_file()
    content = std_p01.read_text(encoding="utf-8")
    assert "make_trapezoidal_lead_screw" in content

    report = json.loads(
        (LIFTING_DIR / ".cad-spec-gen" / "geometry_report.json").read_text(
            encoding="utf-8"
        )
    )
    p01 = next(row for row in report["decisions"] if row["part_no"] == "SLP-P01")
    assert p01["adapter"] == "parametric_transmission"
    assert p01["geometry_source"] == "PARAMETRIC_TEMPLATE"
    assert p01["geometry_quality"] == "B"
