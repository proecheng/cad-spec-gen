"""
end_effector Parametric Dimensions — Single Source of Truth

Auto-generated from CAD_SPEC.md by codegen/gen_params.py
Source: D:\cad-skill\cad\end_effector\CAD_SPEC.md
Generated: 2026-03-24 22:51

All values extracted from design document (? lines).
Units: mm, degrees, grams unless noted.
"""

import math

# ═══════════════════════════════════════════════════════════════════════════
# Parameters
# ═══════════════════════════════════════════════════════════════════════════
INDEX = 90                       # ° L24
FLANGE_PARAM_L25 = 22            # L (输出轴Φ8mm，法兰连接) L25
SPRING_POS_ACC = 0.2             # ° (弹簧销 + 伺服闭环双重保证) L26
PARAM_L27 = 1.5                  # s (S形速度曲线) L27
PARAM_L28 = 135                  # ° — 柔性线缆缠绕方案 (L28) ±135°
FLANGE_DIA = 90                  # ±0.1mm (圆盘部分外径) L29
L = 40                           # mm (4根等长，90°等分) L30
DIA = 160                        # mm (含所有工位模块包络) L31
FLANGE_THICK = 30                # ±0.5mm (铝合金段25mm + PEEK段5mm) L32
FLANGE_PARAM_L33 = 7075          # L33 轻量化 + 电气绝缘
PARAM_L34 = 9409                 # L34 兼容RM65-B
MOTOR_WEIGHT = 180               # g (ECX 22L(70g)+GP22C(110g)) L35
MOTOR_PARAM_L36 = 0.027          # N (堵转2.85Nm，满足切换需求) L36
FLANGE_OD = 22                   # mm (安装于法兰背面中心) L37
FLANGE_PARAM_L38 = 8             # mm — 传递堵转2.85Nm，剪应力τ=11.3MPa＜许用45MPa (L38) H7/k6
PARAM_L107 = "安全绝缘（防止GIS壳体故障电位传导至机器人）"# L107
OD = 86                          # ±0.05mm L108
ID = 40                          # ±0.1mm L109
THICK = 5                        # ±0.2mm L110
PARAM_L111 = 3                   # mm (L111) H7/h7
PARAM_L112 = 10                  # mm L112
PARAM_L113 = 2500                # V L113
PARAM_L114 = 100                 # MΩ L114
PARAM_L115 = 1.6                 # L115
PARAM_L116 = 3.2                 # L116
TEMP = 10                        # L117
PARAM_L118 = 120                 # ° L118
PARAM_L119 = 2                   # L119
PARAM_L189 = 60                  # L189 不含储罐延伸部分，模块主体高度
WALL = 3                         # mm (7075-T6铝合金，兼顾强度与轻量化) L190
OD = 38                          # mm (SUS316L不锈钢，耐硅脂腐蚀) L191
HOUSING_PARAM_L192 = 20          # L192 位于壳体下部，与储罐出口对接
PARAM_L193 = 15                  # L193 硅橡胶Shore A 60，可插拔更换
PARAM_L194 = 3.5                 # L194 盲孔，位于储罐侧壁，导热硅脂填充
FLANGE_OD = 90                   # mm — 圆盘部分 (L429) ±0.1mm
FLANGE_ID = 22                   # mm — 与减速器壳体Φ22mm定位配合（内含Φ8mm阶梯孔用于输出轴过盈配合） (L430) +0.021/0mm
FLANGE_THICK = 25                # mm — 不含PEEK段 (L431) ±0.5mm
FLANGE_THICK = 30                # mm — 铝合金25mm+PEEK 5mm (L432) ±0.5mm
W = 12                           # mm — 矩形截面 (L433) ±0.2mm
FLANGE_THICK = 8                 # mm — 与法兰端面平齐 (L434) ±0.2mm
FLANGE_L = 40                    # mm — 4根等长 (L435) ±0.3mm
FLANGE_PARAM_L436 = 65           # mm — 法兰半径45mm + 悬臂长度40mm − 安装面半宽20mm = 65mm (L436) ±0.3mm
PARAM_L437 = 40                  # ±0.2mm (4×M3螺纹孔+1×Φ3定位销孔) L437
PARAM_L438 = 50                  # mm (机械臂侧，4×M6螺栓孔) L438
SPRING_PARAM_L439 = 42           # mm (每90°一个销孔，共4个) L439
SPRING_PARAM_L440 = 4            # mm — 锥形头弹簧销，深度12mm (L440) +0.012/0mm
PARAM_L441 = 70                  # mm — 6×M3螺栓孔，与PEEK段通孔对应 (L441) ±0.2mm
SPRING_PARAM_L501 = "锥形头自对中弹簧销"  # L501 标准件（DME/MISUMI）
DIA = 4                          # mm (销：g6（-0.004/-0.012mm）) L502
L = 20                           # mm (含锥形头5mm) L503
PARAM_L504 = 1                   # L504 自对中消除间隙
SPRING_PARAM_L505 = 15           # N (抵抗旋转惯量+可靠定位) L505
FLANGE_PARAM_L506 = "减速器输出端（固定侧）"# L506 销插入法兰外缘销孔（旋转侧）
PARAM_L507 = 7                   # +0.012/0mm (与销g6配合间隙0.004~0.024mm) L507
POS_ACC = 0.2                    # ° (在R=65mm处对应≤0.23mm) L508
PARAM_L518 = 40                  # L518 位于悬臂末端
PARAM_L519 = 4                   # L519 PCD=28mm正方形分布
PARAM_L520 = 1                   # L520 位于安装面右上角（距中心14mm×14mm）
PARAM_L521 = 7                   # H7/g6 (保证安装重复性) L521
PARAM_L522 = 0                   # L522 安装于悬臂侧面，安装孔Φ9.4mm
PARAM_L523 = 1.6                 # L523 保证定位精度
PARAM_L524 = 0.03                # mm L524
TOTAL_COST = 60922.0             # 元 (BOM合计 (48零件)) [计算]
BOM_PARTS_COUNT = 48             # [计算] 6总成
BOM_COMPLETENESS = 100.0         # % (144/144 cells filled) [计算]
