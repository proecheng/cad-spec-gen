"""板件工厂函数：矩形板 + 带倒角安装孔 + 竖向圆角（面数 ≥20）。"""


def make_plate(
    width: float | None,
    depth: float | None,
    thickness: float | None,
    n_hole: int = 4,
    hole_d: float = 5.0,
    fillet_r: float = 2.0,
) -> str | None:
    """生成板件 L2 几何代码字符串。

    孔预先倒角（top + bottom 各一圈），再对竖边做圆角，面数 ≥20。
    """
    if any(v is None or v <= 0 for v in [width, depth, thickness]):
        return None

    margin = round(max(hole_d * 1.5, min(width, depth) * 0.1), 2)
    hx = round(width / 2 - margin, 4)
    hy = round(depth / 2 - margin, 4)
    all_positions = [(hx, hy), (-hx, hy), (-hx, -hy), (hx, -hy)]
    positions = all_positions[:n_hole]
    chamfer_size = round(min(hole_d * 0.08, thickness * 0.12, 0.4), 2)

    lines = [
        f"    # 板件 L2: {width}×{depth}×{thickness}mm {n_hole}安装孔（带倒角）",
        f"    body = cq.Workplane('XY').box({width}, {depth}, {thickness},",
        f"                                   centered=(True, True, False))",
    ]

    for px, py in positions:
        lines += [
            f"    # 孔 ({px},{py}): 带倒角 → 每孔 3 face",
            f"    _hole = (",
            f"        cq.Workplane('XY')",
            f"        .transformed(offset=({px}, {py}, 0))",
            f"        .circle({hole_d / 2}).extrude({thickness})",
            f"    )",
            f"    try:",
            f"        _hole = _hole.faces('>Z').edges().chamfer({chamfer_size})",
            f"        _hole = _hole.faces('<Z').edges().chamfer({chamfer_size})",
            f"    except Exception:",
            f"        pass",
            f"    body = body.cut(_hole)",
        ]

    if fillet_r > 0:
        lines += [
            f"    try:",
            f"        body = body.edges('|Z').fillet({fillet_r})",
            f"    except Exception:",
            f"        pass",
        ]

    return "\n".join(lines)
