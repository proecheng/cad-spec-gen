"""Manual assembly layout overrides.

CP-1 Task 4 (2026-05-13) — 装配 placement 修复：
新架构把 placement 拆成 `assembly.generated.py`（codegen 生成，每件原点放置）+
本文件（手工 layout override）。本次重构后 27 条 part-specific placement 丢失，
36 个 mesh 全部坍塌在世界原点。修法：把 `assembly_legacy.py:90-260` 那 27 条
placement 抄进 `apply_layout()`，按 `assembly.generated.py` 的 `assy.add(..., name=...)`
命名查 child 设 loc。

坐标系：原点在下板顶面中心，+Z 向上。
"""

from __future__ import annotations

import cadquery as cq


# ── 装配 placement 表 (CAD_SPEC §6.2 + assembly_legacy.py 90-260) ──────────
# 每行: (assembly child name, (x, y, z), 可选 (axis_dir, angle_deg))
# 旋转先于平移；rot=None 表示纯平移
_PLACEMENTS: list[tuple[str, tuple[float, float, float], tuple[tuple[float, float, float], float] | None]] = [
    # ── 自制结构件 ──
    ("SLP-100#01", (0.0, 0.0, 272.0), None),                     # 上固定板：板底面 Z=+272
    ("SLP-200#01", (-80.0, 0.0, 0.0), None),                     # 左支撑条：p200.py 已设计为竖直立柱（local +Z），无需旋转
    ("SLP-201#01", (80.0, 0.0, 0.0), None),                      # 右支撑条：镜像至 X=+80
    ("SLP-300#01", (0.0, 0.0, 100.0), None),                     # 动板：mid-stroke Z=+100
    ("SLP-400#01", (80.0, 0.0, -16.0), None),                    # 电机支架：右支撑条底面 Z=-8 → 板顶=Z=-8 → 板底 Z=-16
    ("SLP-403#01", (-80.0, 0.0, 0.0), None),                     # 下限位传感器支架：左支撑条顶面 (-80,0,0)
    ("SLP-404#01", (-80.0, 0.0, 272.0), None),                   # 上限位传感器支架：上板底面 (-80,0,272)
    ("SLP-500#01", (0.0, 0.0, -8.0), None),                      # 同步带护罩：底面 Z=-8

    # ── 丝杠 ×2 (SLP-P01) ──
    ("SLP-P01#01", (-60.0, 30.0, -48.0), None),                  # LS1 at (-60,+30,-48)
    ("SLP-P01#02", (60.0, -30.0, -48.0), None),                  # LS2 at (+60,-30,-48)

    # ── 导向轴 ×2 (SLP-P02) ──
    ("SLP-P02#01", (60.0, 30.0, -12.0), None),                   # GS1 at (+60,+30,-12)
    ("SLP-P02#02", (-60.0, -30.0, -12.0), None),                 # GS2 at (-60,-30,-12)

    # ── KFL001 法兰轴承 ×4 (SLP-C03) — 两根丝杠的上下端各一个 ──
    ("SLP-C03#01", (-60.0, 30.0, 0.0), None),                    # LS1 下端轴承（下板顶面 Z=0）
    ("SLP-C03#02", (60.0, -30.0, 0.0), None),                    # LS2 下端轴承
    ("SLP-C03#03", (-60.0, 30.0, 280.0), None),                  # LS1 上端轴承（上板底面下方）
    ("SLP-C03#04", (60.0, -30.0, 280.0), None),                  # LS2 上端轴承

    # ── T16 螺母 C7 ×2 (SLP-C01) — 嵌在动板的 Φ32 沉台里 ──
    ("SLP-C01#01", (-60.0, 30.0, 100.0), None),                  # LS1 螺母 at 动板高度
    ("SLP-C01#02", (60.0, -30.0, 100.0), None),                  # LS2 螺母

    # ── LM10UU 直线轴承 ×2 (SLP-C02) — 嵌在动板的 Φ19H7 沉孔里 ──
    ("SLP-C02#01", (60.0, 30.0, 100.0), None),                   # GS1 轴承 at 动板高度
    ("SLP-C02#02", (-60.0, -30.0, 100.0), None),                 # GS2 轴承

    # ── 传动链：联轴器 + 电机 + 驱动器 + 带轮 + 同步带 ──
    ("SLP-C06#01", (60.0, -30.0, -48.0), None),                  # L070 联轴器（电机轴-丝杠 LS2 之间）
    ("SLP-C07#01", (60.0, -30.0, -110.0), None),                 # NEMA23 电机
    ("SLP-C08#01", (0.0, 100.0, 0.0), None),                     # CL57T 驱动器（外置，放侧面 +Y 方向）
    ("SLP-C04#01", (-60.0, 30.0, -30.0), None),                  # GT2 带轮 LS1 端
    ("SLP-C04#02", (60.0, -30.0, -30.0), None),                  # GT2 带轮 LS2/motor 端
    ("SLP-C05#01", (0.0, 0.0, -30.0), None),                     # GT2-310 同步带（横跨两个丝杠下端）

    # ── 接近开关 ×2 (SLP-F12) — 转 -90°Y 让感测端朝 +X，放左支撑条上 ──
    ("SLP-F12#01", (-80.0, 0.0, 43.0), ((0.0, 1.0, 0.0), -90.0)),    # 下限位 Z=+43
    ("SLP-F12#02", (-80.0, 0.0, 240.0), ((0.0, 1.0, 0.0), -90.0)),   # 上限位 Z=+240

    # ── PU 缓冲垫 ×4 (SLP-F11) — 4 个限位位置（分散，不重叠）──
    ("SLP-F11#01", (-20.0, 20.0, 36.0), None),
    ("SLP-F11#02", (20.0, 20.0, 36.0), None),
    ("SLP-F11#03", (-20.0, -20.0, 36.0), None),
    ("SLP-F11#04", (20.0, -20.0, 36.0), None),

    # ── 导向轴保护帽 ×4 (SLP-F13) — 2 个导向轴顶 + 2 个丝杠顶 ──
    ("SLP-F13#01", (60.0, 30.0, 284.0), None),                   # GS1 顶
    ("SLP-F13#02", (-60.0, -30.0, 284.0), None),                 # GS2 顶
    ("SLP-F13#03", (-60.0, 30.0, 302.0), None),                  # LS1 顶（丝杠顶 -48+350=302）
    ("SLP-F13#04", (60.0, -30.0, 302.0), None),                  # LS2 顶
]


# 备用：MANUAL_LAYOUT_OVERRIDES 字典（兼容旧代码，目前未使用 — 主路径走 _PLACEMENTS）
MANUAL_LAYOUT_OVERRIDES: dict[str, dict] = {}


def apply_layout(assy: "cq.Assembly") -> "cq.Assembly":
    """Apply 27 part-specific placements per CAD_SPEC §6.2.

    Each assy child (added at origin by assembly.generated.py) gets its
    `loc` set to the (rotation × translation) per `_PLACEMENTS`. Children
    not present are silently skipped so changes in generated.py don't break
    this hook.
    """
    for name, (x, y, z), rot in _PLACEMENTS:
        if name not in assy.objects:
            continue
        trans_loc = cq.Location(cq.Vector(x, y, z))
        if rot is None:
            loc = trans_loc
        else:
            axis_dir, angle_deg = rot
            rot_loc = cq.Location(
                cq.Vector(0.0, 0.0, 0.0),
                cq.Vector(*axis_dir),
                angle_deg,
            )
            # apply rotation first (around world origin), then translate
            loc = trans_loc * rot_loc
        assy.objects[name].loc = loc
    return assy
