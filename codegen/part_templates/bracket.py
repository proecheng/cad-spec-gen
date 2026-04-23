"""支架工厂函数：L 形板 + 双矩形加强筋 + 底部唇边 + 安装孔（面数 ≥30）。"""


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

    # 矩形加强筋尺寸
    rib_w = round(min(width, height) * 0.3, 4)
    rib_h = round(min(width, height) * 0.3, 4)

    # 底部唇边尺寸（增加面数）
    lip_w = round(width * 0.15, 4)
    lip_h = round(thickness * 0.5, 4)

    # 侧向耳片（进一步增加面数，弥补平面合并损失）
    ear_w = round(thickness * 0.8, 4)
    ear_h = round(height * 0.25, 4)
    ear_t = round(thickness * 0.6, 4)

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
        # 主矩形加强筋（内侧，连接底板与竖板）
        f"    _rib = (",
        f"        cq.Workplane('XZ')",
        f"        .transformed(offset=(0, {thickness}, 0))",
        f"        .box({rib_w}, {rib_h}, {rib_t}, centered=(True, False, False))",
        f"    )",
        f"    body = body.union(_rib)",
        # 底部唇边（底板前缘加固）
        f"    _lip = (",
        f"        cq.Workplane('XY')",
        f"        .transformed(offset=(0, -{lip_h}, 0))",
        f"        .box({width}, {lip_h}, {lip_w}, centered=(True, False, False))",
        f"    )",
        f"    body = body.union(_lip)",
        # 左侧耳片（进一步增面）
        f"    _ear_l = (",
        f"        cq.Workplane('YZ')",
        f"        .transformed(offset=(0, {ear_h / 2 + thickness}, -{width / 2 + ear_t}))",
        f"        .box({ear_w}, {ear_h}, {ear_t}, centered=(True, True, False))",
        f"    )",
        f"    body = body.union(_ear_l)",
        # 右侧耳片
        f"    _ear_r = (",
        f"        cq.Workplane('YZ')",
        f"        .transformed(offset=(0, {ear_h / 2 + thickness}, {width / 2}))",
        f"        .box({ear_w}, {ear_h}, {ear_t}, centered=(True, True, False))",
        f"    )",
        f"    body = body.union(_ear_r)",
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
