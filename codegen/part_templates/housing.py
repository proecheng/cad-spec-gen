"""壳体工厂函数：矩形抽壳 + 安装柱 + 圆角。"""


def make_housing(
    width: float | None,
    depth: float | None,
    height: float | None,
    wall_t: float | None,
    boss_h: float = 5.0,
    fillet_r: float = 2.0,
    n_mount: int = 4,
) -> str | None:
    if any(v is None or v <= 0 for v in [width, depth, height, wall_t]):
        return None
    if wall_t >= min(width, depth) / 2:
        return None

    inner_w = round(width - 2 * wall_t, 4)
    inner_d = round(depth - 2 * wall_t, 4)
    boss_r = round(wall_t * 0.8, 2)
    cx = round(width / 2 - wall_t * 1.5, 4)
    cy = round(depth / 2 - wall_t * 1.5, 4)
    mount_positions = [(cx, cy), (-cx, cy), (-cx, -cy), (cx, -cy)][:n_mount]

    lines = [
        f"    # 壳体 L2: {width}×{depth}×{height}mm 壁厚={wall_t}mm",
        "    body = (",
        f"        cq.Workplane('XY').box({width}, {depth}, {height}, centered=(True, True, False))",
        "        .cut(cq.Workplane('XY')",
        f"             .transformed(offset=(0, 0, {wall_t}))",
        f"             .box({inner_w}, {inner_d}, {height}, centered=(True, True, False)))",
        "    )",
    ]

    for mx, my in mount_positions:
        lines += [
            "    body = body.union(",
            "        cq.Workplane('XY')",
            f"        .transformed(offset=({mx}, {my}, {wall_t}))",
            f"        .circle({boss_r}).extrude({boss_h})",
            "    )",
        ]

    if fillet_r > 0:
        lines += [
            "    try:",
            f"        body = body.edges('|Z').fillet({fillet_r})",
            "    except Exception:",
            "        pass",
        ]

    return "\n".join(lines)
