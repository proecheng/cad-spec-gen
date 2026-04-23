"""弹簧机构工厂函数：空心圆柱 + 两端法兰 + 外部分段凸缘（近似弹簧轮廓，面数 ≥30）。"""


def make_spring_mechanism(
    od: float | None,
    id: float | None,
    free_length: float | None,
    wire_d: float | None = None,
    coil_n: int = 8,
) -> str | None:
    """生成弹簧机构 L2 几何代码字符串。

    采用"空心圆柱 + 两端法兰 + n 段外部分节凸缘"方案，
    面数稳定 ≥30，无需 Wire.makeHelix 高级 API。
    """
    if any(v is None or v <= 0 for v in [od, free_length]):
        return None
    if id is None or id <= 0:
        id = round(od * 0.55, 4)
    if wire_d is None or wire_d <= 0:
        wire_d = round(od * 0.1, 4)

    # 端部法兰参数
    flange_od = round(od * 1.25, 4)
    flange_h = round(min(free_length * 0.08, wire_d * 1.5), 4)
    # 分节凸缘参数（模拟弹簧圈外轮廓）
    n_segment = max(coil_n, 4)
    seg_h = round(free_length / n_segment, 4)
    seg_offset = round(seg_h * 0.2, 4)
    seg_od = round(od + wire_d * 0.8, 4)
    seg_len = round(seg_h * 0.5, 4)

    lines = [
        f"    # 弹簧机构 L2: OD={od}mm ID={id}mm L={free_length}mm {coil_n}圈",
        "    # 主体：空心圆柱",
        "    body = (",
        f"        cq.Workplane('XY').circle({od / 2}).extrude({free_length})",
        f"        .cut(cq.Workplane('XY').circle({id / 2}).extrude({free_length}))",
        "    )",
        "    # 底端法兰",
        "    _bot = (",
        f"        cq.Workplane('XY').transformed(offset=(0, 0, -{flange_h}))",
        f"        .circle({flange_od / 2}).extrude({flange_h})",
        f"        .cut(cq.Workplane('XY').transformed(offset=(0, 0, -{flange_h}))",
        f"             .circle({id / 2}).extrude({flange_h}))",
        "    )",
        "    body = body.union(_bot)",
        "    # 顶端法兰",
        "    _top = (",
        f"        cq.Workplane('XY').transformed(offset=(0, 0, {free_length}))",
        f"        .circle({flange_od / 2}).extrude({flange_h})",
        f"        .cut(cq.Workplane('XY').transformed(offset=(0, 0, {free_length}))",
        f"             .circle({id / 2}).extrude({flange_h}))",
        "    )",
        "    body = body.union(_top)",
    ]

    # 添加分节外部凸缘（模拟弹簧圈轮廓）
    for seg_i in range(n_segment):
        z_start = round(seg_i * seg_h + seg_offset, 4)
        lines += [
            f"    _seg{seg_i} = (",
            f"        cq.Workplane('XY').transformed(offset=(0, 0, {z_start}))",
            f"        .circle({seg_od / 2}).extrude({seg_len})",
            f"        .cut(cq.Workplane('XY').transformed(offset=(0, 0, {z_start}))",
            f"             .circle({od / 2}).extrude({seg_len}))",
            "    )",
            f"    body = body.union(_seg{seg_i})",
        ]

    return "\n".join(lines)
