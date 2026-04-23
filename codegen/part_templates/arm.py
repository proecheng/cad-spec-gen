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
    rib_h = round(width * 0.4, 2)
    rib_len_main = round(length * 0.65, 4)
    rib_len_sec = round(length * 0.4, 4)

    # 筋条与主体的 Y 向重叠量，确保 union 不退化为边接触
    rib_overlap = round(rib_h * 0.3, 4)
    # 主体 Y ∈ [-W/2, W/2]；筋条从 -W/2 + rib_overlap 往 -Y 延伸
    rib1_y_start = round(-width / 2 + rib_overlap, 4)
    rib2_y_start = round(width / 2 - rib_overlap, 4)

    lines = [
        f"    # 悬臂 L2: L={length}mm W={width}mm T={thickness}mm",
        f"    body = cq.Workplane('XY').box({length}, {width}, {thickness},",
        "                                   centered=(True, True, False))",
        "    # 主加强筋（-Y 侧面，与主体 Y 向重叠确保 union 有效）",
        "    _rib1 = (",
        "        cq.Workplane('XZ')",
        f"        .transformed(offset=(0, {rib1_y_start}, 0))",
        f"        .box({rib_len_main}, {thickness}, {rib_h + rib_overlap},",
        "             centered=(True, False, True))",
        "    )",
        "    body = body.union(_rib1)",
        "    # 副加强筋（+Y 侧面，与主体 Y 向重叠确保 union 有效）",
        "    _rib2 = (",
        "        cq.Workplane('XZ')",
        f"        .transformed(offset=(0, {rib2_y_start}, 0))",
        f"        .box({rib_len_sec}, {thickness}, {round((rib_h + rib_overlap) * 0.6, 4)},",
        "             centered=(True, False, True))",
        "    )",
        "    body = body.union(_rib2)",
    ]

    # 两端沿 Y 轴穿透孔
    for sign in [1, -1]:
        cx = round(sign * (length / 2 - margin), 4)
        lines += [
            "    # 端部连接孔（沿 Y 轴）",
            "    body = body.cut(",
            "        cq.Workplane('XZ')",
            f"        .transformed(offset=({cx}, {thickness / 2}, 0))",
            f"        .circle({end_hole_d / 2})",
            f"        .extrude({width * 2}, both=True)",
            "    )",
        ]

    if fillet_r > 0:
        lines += [
            "    try:",
            f"        body = body.edges('|X').fillet({fillet_r})",
            "    except Exception:",
            "        pass",
        ]

    return "\n".join(lines)
