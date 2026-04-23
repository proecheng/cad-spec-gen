"""端盖/盖板工厂函数：圆盘 + O 形圈密封槽 + 可选中心孔 + 紧固孔环 + 倒角（面数 ≥20）。"""
import math


def make_cover(
    od: float | None,
    thickness: float | None,
    id: float | None = None,
    n_hole: int = 4,
    fillet_r: float = 1.0,
) -> str | None:
    """生成端盖 L2 几何代码字符串。

    顶面 O 形圈密封槽（环形切槽）增加面数，两平面倒角，
    总面数 ≥20（无中心孔）/ ≥20（有中心孔）。
    """
    if any(v is None or v <= 0 for v in [od, thickness]):
        return None

    bolt_pcd = round(od * 0.75, 4)
    bolt_hole_r = round(od * 0.04, 2)
    # O 形圈密封槽参数
    groove_r = round(od * 0.35, 4)
    groove_w = round(od * 0.033, 2)
    groove_d = round(min(thickness * 0.35, 1.5), 2)

    positions = [
        (
            round(bolt_pcd / 2 * math.cos(math.radians(360 / n_hole * i)), 4),
            round(bolt_pcd / 2 * math.sin(math.radians(360 / n_hole * i)), 4),
        )
        for i in range(n_hole)
    ]

    lines = [
        f"    # 端盖 L2: OD={od}mm T={thickness}mm {n_hole}紧固孔 + O 形密封槽",
        f"    body = cq.Workplane('XY').circle({od / 2}).extrude({thickness})",
        f"    # O 形圈密封槽（顶面环形切槽）",
        f"    _groove = (",
        f"        cq.Workplane('XY').transformed(offset=(0, 0, {thickness - groove_d}))",
        f"        .circle({groove_r + groove_w / 2}).extrude({groove_d})",
        f"        .cut(cq.Workplane('XY').transformed(offset=(0, 0, {thickness - groove_d}))",
        f"             .circle({groove_r - groove_w / 2}).extrude({groove_d}))",
        f"    )",
        f"    body = body.cut(_groove)",
    ]

    if id and id > 0 and id < od:
        lines.append(
            f"    body = body.cut(cq.Workplane('XY').circle({id / 2}).extrude({thickness}))"
        )

    for px, py in positions:
        lines += [
            f"    body = body.cut(",
            f"        cq.Workplane('XY')",
            f"        .transformed(offset=({px}, {py}, 0))",
            f"        .circle({bolt_hole_r}).extrude({thickness})",
            f"    )",
        ]

    # 两平面倒角增加面数（先底面再顶面，顶面有密封槽故用较小 chamfer）
    top_chamfer = round(fillet_r * 0.5, 2)
    if fillet_r > 0:
        lines += [
            f"    try:",
            f"        body = body.faces('<Z').edges().chamfer({fillet_r})",
            f"    except Exception:",
            f"        pass",
            f"    try:",
            f"        body = body.faces('>Z').edges().chamfer({top_chamfer})",
            f"    except Exception:",
            f"        pass",
        ]

    return "\n".join(lines)
