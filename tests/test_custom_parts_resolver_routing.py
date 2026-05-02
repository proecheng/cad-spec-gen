from pathlib import Path

from codegen.gen_assembly import generate_assembly
from codegen.gen_build import generate_build_tables, parse_bom_tree
from codegen.gen_parts import generate_part_files
from codegen.gen_std_parts import generate_std_part_files


CAD_SPEC = """# CAD Spec - demo (TST)

## 5. BOM

| 料号 | 名称 | 材质/型号 | 数量 | 自制/外购 | 单价 |
| --- | --- | --- | --- | --- | --- |
| TST-000 | 测试总成 | — | 1 | 总成 | — |
| TST-P01 | 丝杠 L350 | Tr16×4, 45#钢 | 2 | 自制 | — |
| TST-100 | 安装板 | 6061-T6 铝 100×80×8mm | 1 | 自制 | — |

## 6.4 零件包络尺寸

| 料号 | 包络尺寸 |
| --- | --- |
| TST-P01 | φ16×350 mm |
| TST-100 | 100×80×8 mm |

## 7. 装配关系

| 父级 | 子级 | 数量 | 位姿/约束 |
| --- | --- | --- | --- |
| TST-000 | TST-P01 | 1 | 坐标(0,0,0), 旋转(0,0,0) |
| TST-000 | TST-100 | 1 | 坐标(20,0,0), 旋转(0,0,0) |
"""


def _write_spec(tmp_path: Path) -> Path:
    spec = tmp_path / "cad" / "demo" / "CAD_SPEC.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(CAD_SPEC, encoding="utf-8")
    return spec


def test_resolver_generates_standardized_custom_lead_screw(tmp_path):
    spec = _write_spec(tmp_path)

    generated, skipped, resolver, pending = generate_std_part_files(
        str(spec),
        str(spec.parent),
        mode="force",
    )

    generated_names = {Path(p).name for p in generated}
    assert "std_p01.py" in generated_names
    content = (spec.parent / "std_p01.py").read_text(encoding="utf-8")
    assert "make_trapezoidal_lead_screw" in content
    assert "Geometry source: PARAMETRIC_TEMPLATE" in content


def test_custom_generator_skips_resolver_routed_lead_screw_but_keeps_plate(tmp_path):
    spec = _write_spec(tmp_path)

    generated, skipped = generate_part_files(str(spec), str(spec.parent), mode="force")

    generated_names = {Path(p).name for p in generated}
    assert "p01.py" not in generated_names
    assert "p100.py" in generated_names


def test_build_tables_export_resolver_routed_custom_as_std_step(tmp_path):
    spec = _write_spec(tmp_path)

    parts = parse_bom_tree(str(spec))
    tables = generate_build_tables(parts, spec_path=str(spec))

    std_modules = {row["module"] for row in tables["std_step_builds"]}
    dxf_modules = {row["module"] for row in tables["dxf_builds"]}
    assert "std_p01" in std_modules
    assert "p01" not in dxf_modules
    assert "p100" in dxf_modules


def test_assembly_imports_resolver_routed_custom_from_std_module(tmp_path):
    spec = _write_spec(tmp_path)

    source = generate_assembly(str(spec))

    assert "from std_p01 import make_std_p01" in source
    assert "from p01 import make_p01" not in source
    assert "make_std_p01()" in source
