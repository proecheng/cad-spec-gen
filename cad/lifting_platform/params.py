"""
lifting_platform Parametric Dimensions — Single Source of Truth

Auto-generated from CAD_SPEC.md by codegen/gen_params.py
Source: D:\Work\cad-spec-gen\cad\lifting_platform\CAD_SPEC.md
Generated: 2026-04-04 13:51

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
