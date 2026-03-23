"""
End Effector Bill of Materials — §4.8 BOM树与零件编号系统

Structured BOM data extracted from docs/design/04-末端执行机构设计.md
(lines 490–549). Cross-references params.py for dimensions and
tolerances.py for tolerance specs.

Usage:
    python cad/end_effector/bom.py              # print BOM table + export CSV
    python cad/end_effector/bom.py --csv        # CSV only
    python cad/end_effector/bom.py --markdown   # Markdown table only
"""

import csv
import os
import sys
from dataclasses import dataclass, field
from typing import List, Optional

# ─── Data structure ──────────────────────────────────────────────────────────

@dataclass
class BOMItem:
    """Single BOM line item."""
    part_no: str           # GIS-EE-NNN-NN
    name: str              # Chinese name
    material: str          # Material / model number
    qty: int               # Quantity per assembly
    make_buy: str          # 自制 / 外购 / 总成
    unit_price: float      # Unit price in RMB (0 = assembly header)
    weight_g: float = 0.0  # Weight in grams (0 = not specified)
    parent: str = ""       # Parent assembly part_no
    notes: str = ""        # Additional notes
    drawing: str = ""      # DXF drawing reference

    @property
    def total_price(self) -> float:
        return self.unit_price * self.qty

    @property
    def level(self) -> int:
        """Indentation level (0=assembly, 1=part)."""
        parts = self.part_no.split("-")
        if len(parts) == 3:  # GIS-EE-NNN = assembly
            return 0
        return 1


# ─── BOM Data (§4.8, lines 490–549) ─────────────────────────────────────────

BOM: List[BOMItem] = [
    # ═══ GIS-EE-001 法兰总成 ═══
    BOMItem("GIS-EE-001", "法兰总成", "—", 1, "总成", 0,
            weight_g=550, drawing="EE-001_flange_front.dxf, EE-001_flange_section.dxf"),
    BOMItem("GIS-EE-001-01", "法兰本体（含十字悬臂）", "7075-T6铝合金", 1, "自制", 3000,
            weight_g=280, parent="GIS-EE-001",
            drawing="EE-001_flange_front.dxf, EE-001_flange_section.dxf",
            notes="Φ90±0.1, 中心孔Φ22H7, 4×悬臂"),
    BOMItem("GIS-EE-001-02", "PEEK绝缘段", "PEEK", 1, "自制", 500,
            weight_g=30, parent="GIS-EE-001",
            drawing="EE-001-02_peek_front.dxf, EE-001-02_peek_section.dxf",
            notes="Φ86±0.05/Φ40±0.1, 台阶止口3mm"),
    BOMItem("GIS-EE-001-03", "O型圈", "FKM Φ80×2.4", 1, "外购", 15,
            parent="GIS-EE-001", notes="槽宽3.2/深1.8"),
    BOMItem("GIS-EE-001-04", "碟形弹簧垫圈", "DIN 2093 A6", 6, "外购", 5,
            parent="GIS-EE-001", notes="OD12.5/ID6.2"),
    BOMItem("GIS-EE-001-05", "伺服电机", "Maxon ECX SPEED 22L", 1, "外购", 2500,
            weight_g=110, parent="GIS-EE-001",
            drawing="EE-006_drive.dxf"),
    BOMItem("GIS-EE-001-06", "行星减速器", "Maxon GP22C (53:1)", 1, "外购", 1800,
            weight_g=70, parent="GIS-EE-001",
            drawing="EE-006_drive.dxf"),
    BOMItem("GIS-EE-001-07", "弹簧销组件（含弹簧）", "Φ4×20mm锥形头", 4, "外购", 50,
            parent="GIS-EE-001", notes="Φ4H7, 弹簧力15N"),
    BOMItem("GIS-EE-001-08", "ISO 9409适配板", "7075-T6铝合金", 1, "自制", 500,
            weight_g=50, parent="GIS-EE-001",
            drawing="EE-001-08_adapter.dxf",
            notes="Φ63, 止口Φ50×2, 4×M6@PCD50"),
    BOMItem("GIS-EE-001-09", "FFC线束总成", "Molex 15168, 20芯×500mm", 1, "外购", 500,
            parent="GIS-EE-001"),
    BOMItem("GIS-EE-001-10", "ZIF连接器", "Molex 5052xx", 2, "外购", 30,
            parent="GIS-EE-001"),
    BOMItem("GIS-EE-001-11", "Igus拖链段", "E2 micro, 内径6mm", 1, "外购", 80,
            parent="GIS-EE-001"),
    BOMItem("GIS-EE-001-12", "定位销", "Φ3×6mm H7/g6", 4, "外购", 5,
            parent="GIS-EE-001"),

    # ═══ GIS-EE-002 工位1涂抹模块 ═══
    BOMItem("GIS-EE-002", "工位1涂抹模块", "—", 1, "总成", 0,
            weight_g=400, drawing="EE-002_station1.dxf"),
    BOMItem("GIS-EE-002-01", "涂抹模块壳体", "7075-T6铝合金", 1, "自制", 800,
            weight_g=200, parent="GIS-EE-002",
            drawing="EE-002_station1.dxf",
            notes="60×40×55mm, 壁厚3mm"),
    BOMItem("GIS-EE-002-02", "储罐", "不锈钢Φ38×280mm", 1, "外购", 200,
            weight_g=120, parent="GIS-EE-002",
            notes="Φ38/Φ34, M14快拆"),
    BOMItem("GIS-EE-002-03", "齿轮泵", "—", 1, "外购", 1500,
            parent="GIS-EE-002", notes="泵腔Φ20×25"),
    BOMItem("GIS-EE-002-04", "刮涂头", "硅橡胶", 1, "外购", 30,
            parent="GIS-EE-002", notes="15×10×5mm"),
    BOMItem("GIS-EE-002-05", "LEMO插头", "FGG.0B.307", 1, "外购", 150,
            parent="GIS-EE-002"),

    # ═══ GIS-EE-003 工位2 AE检测模块 ═══
    BOMItem("GIS-EE-003", "工位2 AE检测模块", "—", 1, "总成", 0,
            weight_g=520, drawing="EE-003_station2_ae.dxf"),
    BOMItem("GIS-EE-003-01", "AE传感器", "TWAE-03", 1, "外购", 3000,
            weight_g=55, parent="GIS-EE-003",
            notes="Φ28×26mm"),
    BOMItem("GIS-EE-003-02", "六轴力传感器", "ATI Nano17/坤维KWR42", 1, "外购", 25000,
            weight_g=70, parent="GIS-EE-003",
            drawing="EE-003_station2_ae.dxf",
            notes="Φ42×20mm"),
    BOMItem("GIS-EE-003-03", "弹簧限力机构总成", "见§4.1.2零件表", 1, "自制", 300,
            weight_g=16, parent="GIS-EE-003",
            notes="弹簧OD8/线径0.5/自由长12mm, 导向轴Φ4"),
    BOMItem("GIS-EE-003-04", "柔性关节（万向节）", "硅橡胶Shore A 40", 1, "自制", 200,
            parent="GIS-EE-003",
            notes="Φ30/Φ12×15mm, 4×M2@PCD22"),
    BOMItem("GIS-EE-003-05", "阻尼垫", "黏弹性硅橡胶", 1, "外购", 50,
            parent="GIS-EE-003",
            notes="Φ28×2mm"),
    BOMItem("GIS-EE-003-06", "压力阵列", "4×4薄膜 20×20mm", 1, "外购", 500,
            parent="GIS-EE-003"),
    BOMItem("GIS-EE-003-07", "配重块", "钨合金Φ12×7mm/50g", 1, "外购", 200,
            weight_g=50, parent="GIS-EE-003"),
    BOMItem("GIS-EE-003-08", "LEMO插头", "FGG.0B.307", 1, "外购", 150,
            parent="GIS-EE-003"),
    BOMItem("GIS-EE-003-09", "Gore柔性同轴", "MicroTCA系列×500mm", 1, "外购", 800,
            parent="GIS-EE-003"),

    # ═══ GIS-EE-004 工位3卷带清洁模块 ═══
    BOMItem("GIS-EE-004", "工位3卷带清洁模块", "—", 1, "总成", 0,
            weight_g=380, drawing="EE-004_station3.dxf"),
    BOMItem("GIS-EE-004-01", "清洁模块壳体", "7075-T6铝合金", 1, "自制", 800,
            weight_g=150, parent="GIS-EE-004",
            drawing="EE-004_station3.dxf",
            notes="50×40×120mm, 含卷轴腔+清洁窗口"),
    BOMItem("GIS-EE-004-02", "清洁带盒", "超细纤维无纺布", 1, "外购", 45,
            parent="GIS-EE-004",
            notes="供带+收带卷轴+10m带, 带宽15mm"),
    BOMItem("GIS-EE-004-03", "微型电机", "DC 3V Φ16mm", 1, "外购", 50,
            parent="GIS-EE-004",
            notes="Φ16×30mm"),
    BOMItem("GIS-EE-004-04", "齿轮减速组", "塑料齿轮", 1, "外购", 30,
            parent="GIS-EE-004"),
    BOMItem("GIS-EE-004-05", "弹性衬垫", "硅橡胶Shore A 30, 20×15×5mm", 1, "外购", 15,
            parent="GIS-EE-004"),
    BOMItem("GIS-EE-004-06", "恒力弹簧（供带侧张力）", "SUS301, 0.3N", 1, "外购", 10,
            parent="GIS-EE-004"),
    BOMItem("GIS-EE-004-07", "光电编码器（带面余量）", "反射式", 1, "外购", 25,
            parent="GIS-EE-004"),
    BOMItem("GIS-EE-004-08", "溶剂储罐", "Φ25×110mm，M8快拆接口", 1, "外购", 150,
            parent="GIS-EE-004",
            notes="50mL活塞式正压密封"),
    BOMItem("GIS-EE-004-09", "微量泵（溶剂喷射）", "电磁阀式", 1, "外购", 80,
            parent="GIS-EE-004"),
    BOMItem("GIS-EE-004-10", "配重块", "钨合金Φ14×13mm/120g", 1, "外购", 400,
            weight_g=120, parent="GIS-EE-004"),
    BOMItem("GIS-EE-004-11", "微型轴承", "MR105ZZ（Φ10×Φ5×4mm）", 4, "外购", 8,
            parent="GIS-EE-004"),
    BOMItem("GIS-EE-004-12", "清洁窗口翻盖", "硅橡胶一体成型", 1, "自制", 20,
            parent="GIS-EE-004"),
    BOMItem("GIS-EE-004-13", "LEMO插头", "FGG.0B.307", 1, "外购", 150,
            parent="GIS-EE-004"),

    # ═══ GIS-EE-005 工位4 UHF模块（方案A） ═══
    BOMItem("GIS-EE-005", "工位4 UHF模块（方案A）", "—", 1, "总成", 0,
            weight_g=650, drawing="EE-005_station4.dxf"),
    BOMItem("GIS-EE-005-01", "I300-UHF-GT传感器", "波译科技", 1, "外购", 6000,
            parent="GIS-EE-005",
            notes="Φ45×60mm ※待数据手册确认"),
    BOMItem("GIS-EE-005-02", "UHF安装支架", "7075-T6铝合金", 1, "自制", 300,
            parent="GIS-EE-005",
            drawing="EE-005_station4.dxf",
            notes="L形50×40×25mm, t=3mm"),
    BOMItem("GIS-EE-005-03", "LEMO插头", "FGG.0B.307", 1, "外购", 150,
            parent="GIS-EE-005"),

    # ═══ GIS-EE-006 信号调理模块 ═══
    BOMItem("GIS-EE-006", "信号调理模块", "—", 1, "总成", 0,
            weight_g=400),
    BOMItem("GIS-EE-006-01", "壳体（含散热鳍片）", "6063铝合金 140×100×55mm", 1, "自制", 1500,
            parent="GIS-EE-006"),
    BOMItem("GIS-EE-006-02", "信号调理PCB", "定制4层混合信号", 1, "外购", 8000,
            parent="GIS-EE-006"),
    BOMItem("GIS-EE-006-03", "安装支架（抱箍+L型）", "不锈钢", 1, "自制", 300,
            parent="GIS-EE-006"),
    BOMItem("GIS-EE-006-04", "LEMO插座", "EGG.0B.307", 4, "外购", 150,
            parent="GIS-EE-006"),
    BOMItem("GIS-EE-006-05", "SMA穿壁连接器", "50Ω", 2, "外购", 50,
            parent="GIS-EE-006"),
    BOMItem("GIS-EE-006-06", "M12防水诊断接口", "4芯", 1, "外购", 80,
            parent="GIS-EE-006"),
]


# ─── Utility functions ───────────────────────────────────────────────────────

def get_assemblies() -> List[BOMItem]:
    """Return only top-level assembly items."""
    return [b for b in BOM if b.level == 0]


def get_parts(assembly_no: str) -> List[BOMItem]:
    """Return child parts for a given assembly."""
    return [b for b in BOM if b.parent == assembly_no]


def summary() -> dict:
    """Return BOM summary statistics."""
    assemblies = get_assemblies()
    parts = [b for b in BOM if b.level == 1]
    make_parts = [p for p in parts if p.make_buy == "自制"]
    buy_parts = [p for p in parts if p.make_buy == "外购"]
    total_cost = sum(p.total_price for p in parts)
    total_weight = sum(a.weight_g for a in assemblies if a.weight_g > 0)
    return {
        "assemblies": len(assemblies),
        "total_parts": len(parts),
        "make": len(make_parts),
        "buy": len(buy_parts),
        "total_cost_rmb": total_cost,
        "total_weight_g": total_weight,
    }


# ─── Export functions ────────────────────────────────────────────────────────

def to_csv(output_path: str) -> str:
    """Export BOM to CSV file."""
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "层级", "料号", "名称", "材质/型号", "数量",
            "自制/外购", "单价(元)", "小计(元)", "重量(g)",
            "工程图", "备注",
        ])
        for item in BOM:
            indent = "  " if item.level == 1 else ""
            writer.writerow([
                item.level,
                item.part_no,
                indent + item.name,
                item.material,
                item.qty,
                item.make_buy,
                f"{item.unit_price:.0f}" if item.unit_price else "—",
                f"{item.total_price:.0f}" if item.total_price else "—",
                f"{item.weight_g:.0f}" if item.weight_g else "",
                item.drawing,
                item.notes,
            ])
        # Summary row
        s = summary()
        writer.writerow([])
        writer.writerow(["", "", f"合计: {s['total_parts']}种零件 "
                         f"({s['make']}自制 + {s['buy']}外购), "
                         f"{s['assemblies']}个总成",
                         "", "", "", "",
                         f"{s['total_cost_rmb']:.0f}",
                         f"{s['total_weight_g']:.0f}",
                         "", ""])
    return output_path


def to_markdown() -> str:
    """Return BOM as a formatted Markdown table string."""
    lines = []
    lines.append("# 末端执行器 BOM — GIS-EE 系列")
    lines.append("")
    lines.append("| 料号 | 名称 | 材质/型号 | 数量 | 自制/外购 | "
                 "单价(元) | 小计(元) | 重量(g) | 备注 |")
    lines.append("|------|------|----------|------|----------|"
                 "---------|---------|---------|------|")
    for item in BOM:
        if item.level == 0:
            name = f"**{item.name}**"
            pno = f"**{item.part_no}**"
            price = "—"
            subtotal = "—"
        else:
            name = item.name
            pno = item.part_no
            price = f"{item.unit_price:,.0f}"
            subtotal = f"{item.total_price:,.0f}"
        wt = f"{item.weight_g:.0f}" if item.weight_g else ""
        lines.append(f"| {pno} | {name} | {item.material} | "
                     f"{item.qty} | {item.make_buy} | {price} | "
                     f"{subtotal} | {wt} | {item.notes} |")

    s = summary()
    lines.append("")
    lines.append(f"**合计**: {s['total_parts']}种零件 "
                 f"({s['make']}自制 + {s['buy']}外购), "
                 f"{s['assemblies']}个总成 | "
                 f"总成本 ¥{s['total_cost_rmb']:,.0f} | "
                 f"总重量 {s['total_weight_g']:.0f}g ({s['total_weight_g']/1000:.2f}kg)")
    return "\n".join(lines)


def print_table():
    """Print BOM table to console."""
    hdr = (f"{'料号':<18s} {'名称':<28s} {'材质':<26s} "
           f"{'数量':>4s} {'类型':<6s} {'单价':>8s} {'小计':>8s} {'重量':>6s}")
    sep = "-" * 120
    print(f"\n{sep}")
    print(f"  GISBOT 末端执行器 BOM (§4.8)")
    print(f"{sep}")
    print(hdr)
    print(sep)

    for item in BOM:
        if item.level == 0:
            print(sep)
            pno = item.part_no
            name = f">> {item.name}"
            price = "—"
            subtotal = "—"
        else:
            pno = f"  {item.part_no}"
            name = item.name
            price = f"¥{item.unit_price:,.0f}"
            subtotal = f"¥{item.total_price:,.0f}"
        wt = f"{item.weight_g:.0f}g" if item.weight_g else ""
        print(f"{pno:<18s} {name:<28s} {item.material:<26s} "
              f"{item.qty:>4d} {item.make_buy:<6s} {price:>8s} {subtotal:>8s} {wt:>6s}")

    s = summary()
    print(sep)
    print(f"  合计: {s['total_parts']}种零件 ({s['make']}自制 + {s['buy']}外购), "
          f"{s['assemblies']}个总成")
    print(f"  总成本: ¥{s['total_cost_rmb']:,.0f}")
    print(f"  总重量: {s['total_weight_g']:.0f}g ({s['total_weight_g']/1000:.2f}kg)")
    print(sep)


# ─── CLI ─────────────────────────────────────────────────────────────────────

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output")


if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if "--csv" in sys.argv:
        p = to_csv(os.path.join(OUTPUT_DIR, "GIS-EE_BOM.csv"))
        print(f"Exported: {p}")
    elif "--markdown" in sys.argv:
        print(to_markdown())
    else:
        print_table()
        p = to_csv(os.path.join(OUTPUT_DIR, "GIS-EE_BOM.csv"))
        print(f"\nCSV exported: {p}")
