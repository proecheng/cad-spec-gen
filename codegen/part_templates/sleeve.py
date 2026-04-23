"""套筒/轴套工厂函数：同轴圆柱孔 + 双侧键槽 + 两端倒角（面数 ≥20）。"""


def make_sleeve(
    od: float | None,
    id: float | None,
    length: float | None,
    chamfer: float = 0.5,
) -> str | None:
    """生成套筒 L2 几何代码字符串。

    双侧键槽（180° 互为对称）+ 两端倒角，面数 ≥20。
    """
    if any(v is None or v <= 0 for v in [od, id, length]):
        return None
    if id >= od:
        return None

    keyway_w = round(od * 0.18, 2)
    keyway_d = round(od * 0.09, 2)
    keyway_start = round(length * 0.1, 4)
    keyway_len = round(length * 0.8, 4)
    # 键槽偏置：从内孔壁往外切
    keyway_offset_y = round(id / 2 + keyway_d / 2, 4)

    lines = [
        f"    # 套筒 L2: OD={od}mm ID={id}mm L={length}mm",
        f"    body = (",
        f"        cq.Workplane('XY').circle({od / 2}).extrude({length})",
        f"        .cut(cq.Workplane('XY').circle({id / 2}).extrude({length}))",
        f"    )",
        f"    # 键槽 1（+Y 方向）",
        f"    _kw1 = (",
        f"        cq.Workplane('XY')",
        f"        .transformed(offset=(0, {keyway_offset_y}, {keyway_start}))",
        f"        .box({keyway_w}, {keyway_d}, {keyway_len},",
        f"             centered=(True, True, False))",
        f"    )",
        f"    try:",
        f"        body = body.cut(_kw1)",
        f"    except Exception:",
        f"        pass",
        f"    # 键槽 2（-Y 方向，对称）",
        f"    _kw2 = (",
        f"        cq.Workplane('XY')",
        f"        .transformed(offset=(0, -{keyway_offset_y}, {keyway_start}))",
        f"        .box({keyway_w}, {keyway_d}, {keyway_len},",
        f"             centered=(True, True, False))",
        f"    )",
        f"    try:",
        f"        body = body.cut(_kw2)",
        f"    except Exception:",
        f"        pass",
    ]

    if chamfer > 0:
        lines += [
            f"    # 两端倒角",
            f"    try:",
            f"        body = body.faces('<Z').edges().chamfer({chamfer})",
            f"    except Exception:",
            f"        pass",
            f"    try:",
            f"        body = body.faces('>Z').edges().chamfer({chamfer})",
            f"    except Exception:",
            f"        pass",
        ]

    return "\n".join(lines)
