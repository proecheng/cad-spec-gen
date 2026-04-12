"""生成测试用最小化 sldmat 文件。不含任何 SolidWorks 原始数据。

sldmat 是 UTF-16 LE + BOM 编码的 XML 文件，包含材质分类和属性。
本脚本构造 2 种虚构材质用于单元测试。
"""

import xml.etree.ElementTree as ET
from pathlib import Path

NS = "http://www.solidworks.com/sldmaterials"


def generate_minimal_sldmat(out_path: Path) -> None:
    """构造一个含 2 种材质的最小 sldmat（UTF-16 LE + BOM）。

    材质列表：
    1. Steel / "Test Carbon Steel 1000" — density 7850, KX 50, SIGXT 420e6
    2. Aluminum Alloys / "Test 6061 Alloy" — density 2700, KX 167
    """
    root = ET.Element(f"{{{NS}}}materials", attrib={
        "version": "2008.03",
    })

    # classification: Steel
    steel = ET.SubElement(root, "classification", name="Steel")
    mat1 = ET.SubElement(steel, "material", name="Test Carbon Steel 1000", matid="1")
    props1 = ET.SubElement(mat1, "physicalproperties")
    ET.SubElement(props1, "DENS", displayname="Mass density", value="7850.0")
    ET.SubElement(props1, "KX", displayname="Thermal conductivity", value="50.0")
    ET.SubElement(props1, "SIGXT", displayname="Tensile strength", value="420000000")
    shaders1 = ET.SubElement(mat1, "shaders")
    ET.SubElement(shaders1, "pwshader2",
                  path=r"\metal\steel\matte steel.p2m", name="matte steel")

    # classification: Aluminum Alloys
    al = ET.SubElement(root, "classification", name="Aluminum Alloys")
    mat2 = ET.SubElement(al, "material", name="Test 6061 Alloy", matid="2")
    props2 = ET.SubElement(mat2, "physicalproperties")
    ET.SubElement(props2, "DENS", displayname="Mass density", value="2700.0")
    ET.SubElement(props2, "KX", displayname="Thermal conductivity", value="167.0")
    shaders2 = ET.SubElement(mat2, "shaders")
    ET.SubElement(shaders2, "pwshader2",
                  path=r"\metal\aluminum\polished aluminum.p2m",
                  name="polished aluminum")

    tree = ET.ElementTree(root)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(b"\xff\xfe")  # UTF-16 LE BOM
        tree.write(f, encoding="utf-16-le", xml_declaration=False)


if __name__ == "__main__":
    out = Path(__file__).parent / "test_materials.sldmat"
    generate_minimal_sldmat(out)
    print(f"Generated: {out}")
