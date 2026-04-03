"""
end_effector Parametric Dimensions — Single Source of Truth

Auto-generated from CAD_SPEC.md by codegen/gen_params.py
Source: D:\Work\cad-spec-gen\cad\end_effector\CAD_SPEC.md
Generated: 2026-04-03 16:18

All values extracted from design document (? lines).
Units: mm, degrees, grams unless noted.
"""

import math

# ═══════════════════════════════════════════════════════════════════════════
# Parameters
# ═══════════════════════════════════════════════════════════════════════════
INDEX = 90                       # ° L11
SWITCH_T = 1.5                   # s (S形速度曲线) L14
FLANGE_DIA = 90                  # ±0.1mm (圆盘部分外径) L15
ARM_L = 40                       # mm (4根等长，90°等分) L16
FLANGE_THICK = 30                # ±0.5mm (铝合金段25mm + PEEK段5mm) L17
MOTOR_RATED_TORQUE = 0.027       # N (堵转2.85Nm) L20
MOTOR_OD = 22                    # mm (安装于法兰背面中心) L21
TOTAL_COST = 58180.0             # 元 (BOM合计 (35零件)) [计算]
BOM_PARTS_COUNT = 35             # [计算] 6总成
BOM_COMPLETENESS = 100.0         # % (105/105 cells filled) [计算]
