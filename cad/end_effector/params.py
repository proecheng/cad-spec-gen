"""
end_effector Parametric Dimensions — Single Source of Truth

Auto-generated from CAD_SPEC.md by codegen/gen_params.py
Source: D:\Work\cad-spec-gen\cad\end_effector\CAD_SPEC.md
Generated: 2026-04-04 11:58

All values extracted from design document (? lines).
Units: mm, degrees, grams unless noted.
"""

import math

# ═══════════════════════════════════════════════════════════════════════════
# Parameters
# ═══════════════════════════════════════════════════════════════════════════
INDEX = 90                       # ° L24
SWITCH_T = 1.5                   # s (S形速度曲线) L27
ROT_RANGE = 135                  # ° — 柔性线缆缠绕方案 (L28) ±135°
FLANGE_DIA = 90                  # mm — 圆盘部分外径 (L29) ±0.1mm
ARM_L = 40                       # mm (4根等长，90°等分) L30
FLANGE_THICK = 30                # mm — 铝合金段25mm + PEEK段5mm (L32) ±0.5mm
MOTOR_RATED_TORQUE = 0.027       # N (堵转2.85Nm，满足切换需求) L36
MOTOR_OD = 22                    # mm (安装于法兰背面中心) L37
OD = 86                          # ±0.05mm L108
ID = 40                          # ±0.1mm L109
THICK = 5                        # ±0.2mm L110
CREEP_D = 10                     # mm L112
WITHSTAND_V = 2500               # V L113
INSUL_R = 100                    # MΩ L114
WALL = 3                         # mm (7075-T6铝合金，兼顾强度与轻量化) L190
OD_2 = 38                        # mm (SUS316L不锈钢，耐硅脂腐蚀) L191
FLANGE_BODY_OD = 90              # mm — 圆盘部分 (L429) ±0.1mm
FLANGE_BODY_ID = 22              # mm — 与减速器壳体Φ22mm定位配合（内含Φ8mm阶梯孔用于输出轴过盈配合） (L430) +0.021/0mm
FLANGE_AL_THICK = 25             # mm — 不含PEEK段 (L431) ±0.5mm
FLANGE_TOTAL_THICK = 30          # mm — 铝合金25mm+PEEK 5mm (L432) ±0.5mm
ARM_SEC_W = 12                   # mm — 矩形截面 (L433) ±0.2mm
ARM_SEC_THICK = 8                # mm — 与法兰端面平齐 (L434) ±0.2mm
ARM_L_2 = 40                     # mm — 4根等长 (L435) ±0.3mm
FLANGE_MOUNT_FACE = 50           # mm (机械臂侧，4×M6螺栓孔) L438
SPRING_PIN_BORE = 4              # mm — 锥形头弹簧销，深度12mm (L440) +0.012/0mm
FLANGE_BOLT_PCD = 70             # mm — 6×M3螺栓孔，与PEEK段通孔对应 (L441) ±0.2mm
SPRING_PIN_DIA = 4               # mm (销：g6（-0.004/-0.012mm）) L502
SPRING_L = 20                    # mm (含锥形头5mm) L503
SPRING_F = 15                    # N (抵抗旋转惯量+可靠定位) L505
SPRING_POS_ACC = 0.2             # ° (在R=65mm处对应≤0.23mm) L508
MOUNT_FLAT = 0.03                # mm L524
TOTAL_COST = 60922.0             # 元 (BOM合计 (48零件)) [计算]
BOM_PARTS_COUNT = 48             # [计算] 6总成
BOM_COMPLETENESS = 100.0         # % (144/144 cells filled) [计算]

# ═══════════════════════════════════════════════════════════════════════════
# Derived (computed)
# ═══════════════════════════════════════════════════════════════════════════
MOUNT_CENTER_R = 65              # mm — 工位安装面中心到旋转轴距离 (§6.2)
MOTOR_L = 73.0                   # mm — 电机+减速器总长 (§6.2 Z=+73mm(向上))
STATION_ANGLES = [0, 90, 180, 270]# ° — 4工位角度 (§6.2)
