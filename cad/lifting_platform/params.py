"""
lifting_platform Parametric Dimensions — Single Source of Truth

Auto-generated from CAD_SPEC.md by codegen/gen_params.py
Source: D:\Work\cad-spec-gen\cad\lifting_platform\CAD_SPEC.md
Generated: 2026-05-06 12:21

All values extracted from design document (? lines).
Units: mm, degrees, grams unless noted.
"""

import math

# ═══════════════════════════════════════════════════════════════════════════
# Parameters
# ═══════════════════════════════════════════════════════════════════════════
PARAM_L25 = 10                   # kg L25
PARAM_L26 = 2.5                  # L26
PARAM_L27 = 25                   # kg L27
SENSOR_STROKE = 192              # mm (下极限 = 传感器触发点 Z=+43，保留 7mm 至 PU 垫) L28
PITCH = 280                      # mm L29
PARAM_L30 = 8                    # mm L30
PARAM_L169 = 5.19                # ° L169
PARAM_L170 = 8.83                # ° L170
PARAM_L394 = 350                 # mm L394
PARAM_L395 = 230                 # mm L395
PARAM_L396 = 12                  # L396
PARAM_L397 = 12                  # L397
PARAM_L470 = 10                  # h L470
L = 296                          # mm L471
PARAM_L662 = 0.15                # mm L662
PARAM_L663 = 0.4                 # mm L663
MOTOR_RATED_TORQUE = 1.0         # N L681
MOTOR_L = 56                     # mm L682
MOTOR_SPEED = 20                 # mm L683
MOTOR_PARAM_L684 = 20            # W L684
MOTOR_RPM = 400                  # rpm L687
SENSOR_PARAM_L753 = 25           # L753
SENSOR_PARAM_L754 = 20           # L754
SENSOR_PARAM_L763 = 25           # L763
SENSOR_PARAM_L764 = 20           # L764
SENSOR_PARAM_L793 = 2            # mm L793
SENSOR_PARAM_L794 = 0.8          # L794
SENSOR_PITCH = 1.2               # mm L795
SPEED = 20                       # mm L1194
SPEED_2 = 30                     # mm L1195
ACCEL = 50                       # mm L1196
SPEED_3 = 50                     # mm L1197
PARAM_L1199 = 16                 # L1199
PARAM_L1200 = 0.1125             # ° L1200
PARAM_L1201 = 0.00125            # mm L1201
FREQ = 16                        # L1202
POS_ACC = 0.1                    # mm (L1203) ±0.1 mm
PARAM_L1204 = 0.05               # mm (L1204) ±0.05 mm
PARAM_L1205 = 0.15               # mm L1205
BOM_PARTS_COUNT = 32             # [计算] 1总成
BOM_COMPLETENESS = 33.3          # % (32/96 cells filled) [计算]

# ═══════════════════════════════════════════════════════════════════════════
# Derived (computed)
# ═══════════════════════════════════════════════════════════════════════════
MOUNT_CENTER_R = 28.5            # mm — 工位安装面中心到旋转轴距离 (§6.2)

# ═══════════════════════════════════════════════════════════════════════════
# 自制件结构尺寸（CP-1 Task 5 / 2026-05-13 沉淀；推断自 draw_*.py + §6.2）
# ═══════════════════════════════════════════════════════════════════════════
# 板厚（所有自制结构件统一）
PLATE_THICK = 8                  # mm — Al 6061-T6 阳极氧化板

# SLP-100 上固定板（200×100 mm，4 工位机器人接口板）
TOP_PLATE_W = 200                # mm — draw_top_plate.py:42 注释
TOP_PLATE_H = 100                # mm

# SLP-300 动板（150×100 mm，挂液压钳）
MOV_PLATE_W = 150                # mm — draw_moving_plate.py:33 注释
MOV_PLATE_H = 100                # mm

# SLP-400 电机支架（70×90 mm 板，挂 NEMA23 4×M5 PCD47.14）
BRACKET_W = 70                   # mm — draw_motor_bracket.py:33 注释
BRACKET_H = 90                   # mm
BRACKET_CENTER_HOLE = 28         # mm — NEMA23 轴端 Φ28 定位孔

# SLP-200/201 左右支撑条（50×8×280 竖直立柱）
SUP_BAR_W = 50                   # mm — 立柱宽
SUP_BAR_T = 8                    # mm — 立柱厚（即 PLATE_THICK）
SUP_BAR_LEN = 280                # mm — 立柱高度（接近 z=0 到 z=272 上板距离 + 余量）

# 杆位（丝杠 + 导向轴在板平面内的 XY 偏移；diagonal 布置）
LS_X = 60                        # mm — 丝杠中心 X 偏移
LS_Y = 25                        # mm — 丝杠中心 Y 偏移
GS_X = 60                        # mm — 导向轴中心 X 偏移（与 LS 异侧对角）
GS_Y = 25                        # mm — 导向轴中心 Y 偏移

# 外购件名义外径（draw_*.py 用得到的）
LM10UU_OD = 19                   # mm — LM10UU 外径，§6.4 envelope
