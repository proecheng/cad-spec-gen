"""法兰工厂函数：生成 CadQuery 代码字符串（4 空格缩进，适合嵌入函数体）。"""

import math


def make_flange(
    od: float | None,
    id: float | None,
    thickness: float | None,
    bolt_pcd: float | None,
    bolt_count: int = 6,
    boss_h: float = 0.0,
    fillet_r: float = 1.0,
) -> str | None:
    """生成法兰 L2 几何代码字符串。

    必填主尺寸缺失（None 或 ≤0）时返回 None，调用方退回 envelope primitive。
    螺栓孔带沉孔（counterbore），顶面设置定位密封圈台阶，面数 ≥30。
    """
    if any(v is None or v <= 0 for v in [od, id, thickness, bolt_pcd]):
        return None
    if id >= od:
        return None
    # bolt_pcd >= od 时密封台阶数学产生负几何，直接返回 None
    if bolt_pcd >= od:
        return None

    bolt_hole_r = round(bolt_pcd * 0.04, 2)
    cbore_r = round(bolt_hole_r * 1.8, 2)
    cbore_depth = round(min(thickness * 0.15, 5.0), 2)
    # 定位密封台阶（seating ring）位于顶面，增加面数
    seating_r = round((od / 2 + bolt_pcd / 2) / 2, 4)
    seating_h = round(min(thickness * 0.1, 2.0), 2)
    seating_w = round(min(od / 2 - bolt_pcd / 2, 4.0) * 0.6, 2)

    positions = [
        (
            round(bolt_pcd / 2 * math.cos(math.radians(360 / bolt_count * i)), 4),
            round(bolt_pcd / 2 * math.sin(math.radians(360 / bolt_count * i)), 4),
        )
        for i in range(bolt_count)
    ]

    lines = [
        f"    # 法兰 L2: OD={od}mm ID={id}mm T={thickness}mm PCD={bolt_pcd}mm×{bolt_count}孔",
        "    body = (",
        f"        cq.Workplane('XY').circle({od / 2}).extrude({thickness})",
        f"        .cut(cq.Workplane('XY').circle({id / 2}).extrude({thickness}))",
        "    )",
        "    # 顶面定位密封台阶",
        "    _seat = (",
        f"        cq.Workplane('XY').transformed(offset=(0, 0, {thickness}))",
        f"        .circle({seating_r + seating_w / 2}).extrude({seating_h})",
        f"        .cut(cq.Workplane('XY').transformed(offset=(0, 0, {thickness}))",
        f"             .circle({seating_r - seating_w / 2}).extrude({seating_h}))",
        "    )",
        "    body = body.union(_seat)",
    ]

    for bx, by in positions:
        total_h = round(thickness + seating_h, 4)
        lines += [
            "    # 通孔",
            "    body = body.cut(",
            "        cq.Workplane('XY')",
            f"        .transformed(offset=cq.Vector({bx}, {by}, 0))",
            f"        .circle({bolt_hole_r}).extrude({total_h})",
            "    )",
            "    # 沉孔",
            "    body = body.cut(",
            "        cq.Workplane('XY')",
            f"        .transformed(offset=cq.Vector({bx}, {by}, {thickness - cbore_depth}))",
            f"        .circle({cbore_r}).extrude({cbore_depth + seating_h})",
            "    )",
        ]

    if boss_h and boss_h > 0:
        boss_od = round(id * 1.8, 2)
        lines += [
            "    _boss = (",
            f"        cq.Workplane('XY').circle({boss_od / 2}).extrude({thickness + boss_h})",
            f"        .cut(cq.Workplane('XY').circle({id / 2}).extrude({thickness + boss_h}))",
            "    )",
            "    body = body.union(_boss)",
        ]

    return "\n".join(lines)
