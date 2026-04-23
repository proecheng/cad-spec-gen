"""支架工厂函数：L 形板 + 加强筋 + 安装孔。"""


def make_bracket(
    width: float | None,
    height: float | None,
    thickness: float | None,
    rib_t: float = 3.0,
    fillet_r: float = 1.0,
    n_hole: int = 2,
) -> str | None:
    if any(v is None or v <= 0 for v in [width, height, thickness]):
        return None

    hole_r = round(thickness * 0.6, 2)
    hole_spacing = round(width / (n_hole + 1), 4)

    lines = [
        f"    # 支架 L2: {width}×{height}mm 厚={thickness}mm",
        f"    _base = cq.Workplane('XY').box({width}, {thickness}, {thickness},",
        f"                                    centered=(True, False, False))",
        f"    _wall = (",
        f"        cq.Workplane('XY')",
        f"        .transformed(offset=(0, 0, {thickness}))",
        f"        .box({width}, {thickness}, {height}, centered=(True, False, False))",
        f"    )",
        f"    body = _base.union(_wall)",
    ]

    lines += [
        f"    _rib = (",
        f"        cq.Workplane('XZ')",
        f"        .transformed(offset=(0, {thickness / 2}, 0))",
        f"        .polygon(3, {min(width, height) * 0.3})",
        f"        .extrude({rib_t})",
        f"    )",
        f"    try:",
        f"        body = body.union(_rib)",
        f"    except Exception:",
        f"        pass",
    ]

    for i in range(n_hole):
        hx = round(-width / 2 + hole_spacing * (i + 1), 4)
        lines += [
            f"    body = body.cut(",
            f"        cq.Workplane('XY')",
            f"        .transformed(offset=({hx}, {thickness / 2}, 0))",
            f"        .circle({hole_r}).extrude({thickness})",
            f"    )",
        ]

    if fillet_r > 0:
        lines += [
            f"    try:",
            f"        body = body.edges('>>Y').fillet({fillet_r})",
            f"    except Exception:",
            f"        pass",
        ]

    return "\n".join(lines)
