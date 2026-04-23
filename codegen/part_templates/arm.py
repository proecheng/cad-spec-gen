"""悬臂/连杆工厂函数：细长梁 + 两端 Y 向连接孔 + 上下加强筋 + 圆角（面数 ≥20）。"""


def make_arm(
    length: float | None,
    width: float | None,
    thickness: float | None,
    end_hole_d: float | None = None,
    fillet_r: float = 2.0,
) -> str | None:
    """生成悬臂 L2 几何代码字符串。

    两端沿 Y 轴穿透孔 + 上下各一道加强筋，面数 ≥20。
    """
    if any(v is None or v <= 0 for v in [length, width, thickness]):
        return None
    if end_hole_d is None or end_hole_d <= 0:
        end_hole_d = 8.0

    margin = round(end_hole_d * 1.2, 2)
    rib_w = round(thickness * 0.35, 2)
    rib_h = round(width * 0.4, 2)
    rib_len_main = round(length * 0.65, 4)
    rib_len_sec = round(length * 0.4, 4)

    lines = [
        f"    # 悬臂 L2: L={length}mm W={width}mm T={thickness}mm",
        f"    body = cq.Workplane('XY').box({length}, {width}, {thickness},",
        f"                                   centered=(True, True, False))",
        f"    # 主加强筋（底面）",
        f"    _rib1 = (",
        f"        cq.Workplane('XY')",
        f"        .transformed(offset=(0, {-width / 2 - rib_h}, {thickness}))",
        f"        .box({rib_len_main}, {rib_h}, {rib_w}, centered=(True, False, False))",
        f"    )",
        f"    try:",
        f"        body = body.union(_rib1)",
        f"    except Exception:",
        f"        pass",
        f"    # 副加强筋（顶面）",
        f"    _rib2 = (",
        f"        cq.Workplane('XY')",
        f"        .transformed(offset=(0, {width / 2}, {thickness}))",
        f"        .box({rib_len_sec}, {round(rib_h * 0.6, 2)}, {rib_w},",
        f"             centered=(True, False, False))",
        f"    )",
        f"    try:",
        f"        body = body.union(_rib2)",
        f"    except Exception:",
        f"        pass",
    ]

    # 两端沿 Y 轴穿透孔
    for sign in [1, -1]:
        cx = round(sign * (length / 2 - margin), 4)
        lines += [
            f"    # 端部连接孔（沿 Y 轴）",
            f"    body = body.cut(",
            f"        cq.Workplane('XZ')",
            f"        .transformed(offset=({cx}, {thickness / 2}, 0))",
            f"        .circle({end_hole_d / 2})",
            f"        .extrude({width * 2}, both=True)",
            f"    )",
        ]

    if fillet_r > 0:
        lines += [
            f"    try:",
            f"        body = body.edges('|X').fillet({fillet_r})",
            f"    except Exception:",
            f"        pass",
        ]

    return "\n".join(lines)
