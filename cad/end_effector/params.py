"""
End Effector Parametric Dimensions — Single Source of Truth

All values extracted from docs/design/04-末端执行机构设计.md (557 lines).
Line numbers reference that file for traceability.
Units: mm, degrees, grams unless noted.
"""

import math

# ═══════════════════════════════════════════════════════════════════════════
# §4.1.1 结构参数 (lines 22–38)
# ═══════════════════════════════════════════════════════════════════════════
ROTATION_STEP_DEG = 90.0           # 4工位等分 (line 25)
ROTATION_RANGE_DEG = 135.0         # ±135° 限位旋转 (line 29)
NUM_STATIONS = 4
STATION_ANGLES = [0.0, 90.0, 180.0, 270.0]
STATION_NAMES = ["applicator", "ae", "cleaner", "uhf"]

# ═══════════════════════════════════════════════════════════════════════════
# §4.4.1 法兰本体 (7075-T6 Al)  (lines 334–390)
# ═══════════════════════════════════════════════════════════════════════════
FLANGE_OD = 90.0                   # Φ90±0.1mm 圆盘外径 (line 340)
FLANGE_R = FLANGE_OD / 2.0        # 45mm
FLANGE_CENTER_HOLE = 22.0         # Φ22mm H7 中心孔 (line 341)
FLANGE_AL_THICK = 25.0            # 铝合金段厚度 (line 342)
FLANGE_TOTAL_THICK = 30.0         # 含PEEK总厚度 (line 343)
FLANGE_PEEK_THICK = 5.0           # PEEK段 = 30 - 25 (line 343)

# 悬臂 (Arms, line 344–348)
ARM_WIDTH = 12.0                   # 截面宽 (line 344)
ARM_THICK = 8.0                    # 截面厚 (line 345)
ARM_LENGTH = 40.0                  # 法兰边缘→安装面中心 (line 346)
MOUNT_CENTER_R = 65.0              # 安装面中心到旋转轴 (line 347)
MOUNT_FACE = 40.0                  # 安装面40×40mm (line 348)

# 安装面螺栓孔 (lines 415–418)
MOUNT_BOLT_PCD = 28.0             # M3 PCD 28mm 正方形 (line 416)
MOUNT_BOLT_DIA = 3.2              # M3 通孔 Φ3.2mm
MOUNT_BOLT_TAP_DIA = 2.5          # M3 螺纹底孔 Φ2.5mm
MOUNT_BOLT_NUM = 4                # 每安装面4颗
MOUNT_PIN_DIA = 3.0               # Φ3 定位销孔 (line 417)
MOUNT_PIN_DEPTH = 6.0             # 定位销孔深 6mm (line 417)
MOUNT_PIN_OFFSET_X = 14.0         # 右上角偏移 (line 417)
MOUNT_PIN_OFFSET_Y = 14.0

# ISO 9409 背面接口 (line 349)
ISO9409_PCD = 50.0                # 4×M6 PCD Φ50mm
ISO9409_BOLT_DIA = 6.6            # M6 通孔
ISO9409_BOLT_NUM = 4

# 弹簧销 (lines 350–351, §4.4.2 lines 396–405)
SPRING_PIN_R = 42.0               # 安装半径 (line 350)
SPRING_PIN_DIA = 4.0              # Φ4mm H7 (line 351)
SPRING_PIN_DEPTH = 12.0           # 深度12mm (line 351)
SPRING_PIN_LENGTH = 20.0          # 含锥形头总长 (line 400)
SPRING_PIN_CONE_LENGTH = 5.0      # 锥头长5mm (line 401)
SPRING_PIN_CONE_RATIO = 0.1       # 1:10 锥角 (line 401)
SPRING_PIN_FORCE_N = 15.0         # 15N弹簧力 (line 402)

# 减速器安装 (line 375, §4.6 line 436)
REDUCER_MOUNT_PCD = 22.0          # GP22C 安装 PCD（标准值）
REDUCER_MOUNT_BOLT_DIA = 2.5      # M3螺纹底孔
REDUCER_MOUNT_BOLT_NUM = 4

# ═══════════════════════════════════════════════════════════════════════════
# PEEK 绝缘段 (lines 40–58)
# ═══════════════════════════════════════════════════════════════════════════
PEEK_OD = 86.0                    # Φ86±0.05mm (line 47)
PEEK_ID = 40.0                    # Φ40±0.1mm (line 48)
PEEK_THICK = FLANGE_PEEK_THICK    # 5±0.2mm (line 49)
PEEK_STEP_HEIGHT = 3.0            # 台阶止口高度3mm (line 50)
PEEK_STEP_CLEARANCE = 0.02        # H7/h7间隙 (line 50)
PEEK_BOLT_NUM = 6                 # 6×M3 (line 434)
PEEK_BOLT_DIA = 3.2               # M3通孔
PEEK_BOLT_PCD = 70.0              # 6×M3 PCD Φ70mm (line 367)
PEEK_BELLEVILLE_OD = 12.5         # DIN 2093 A6 碟形弹簧垫圈 (line 444)
PEEK_BELLEVILLE_ID = 6.2

# ═══════════════════════════════════════════════════════════════════════════
# O型圈密封槽 (line 374)
# ═══════════════════════════════════════════════════════════════════════════
ORING_CENTER_DIA = 80.0           # Φ80mm O型圈中心 (line 374)
ORING_CS = 2.4                    # 截面直径2.4mm (line 374)
ORING_GROOVE_WIDTH = 3.2          # 槽宽3.2mm (line 374)
ORING_GROOVE_DEPTH = 1.8          # 槽深1.8mm (line 374)
ORING_GROOVE_BOTTOM_DIA = 76.4    # 底径Φ76.4mm (line 374)

# ═══════════════════════════════════════════════════════════════════════════
# FFC走线 (lines 72–92)
# ═══════════════════════════════════════════════════════════════════════════
FFC_WIDTH = 12.0                  # 总宽12mm (line 73)
FFC_THICK = 0.3                   # 厚0.3mm (line 73)
FFC_MIN_BEND_R = 10.0             # 最小弯曲半径10mm (line 75)

# ZIF防护盖 (line 88)
ZIF_COVER_L = 15.0                # 15mm (line 88)
ZIF_COVER_W = 10.0                # 10mm (line 88)
ZIF_COVER_H = 3.0                 # 3mm突出 (line 88)
ZIF_BOLT_DIA = 3.2                # 2×M3 (line 440)

# Igus拖链段 (line 74, line 491)
IGUS_CHAIN_ID = 6.0               # 内径6mm
IGUS_CHAIN_OD = 10.0              # 外径约10mm（E2 micro标准）

# LEMO连接器通用 (line 419)
LEMO_BORE_DIA = 9.4               # Φ9.4mm安装孔 (line 419)
LEMO_BODY_DIA = 9.0               # 连接器本体约Φ9mm
LEMO_BODY_LENGTH = 20.0           # 突出长度约20mm

# ═══════════════════════════════════════════════════════════════════════════
# §4.1.2 工位1 — 耦合剂涂抹 (Station 1, 0°)  (lines 110–119)
# ═══════════════════════════════════════════════════════════════════════════
S1_BODY_W = 60.0                  # 壳体宽 (line 117)
S1_BODY_D = 40.0                  # 壳体深 (line 117)
S1_BODY_H = 55.0                  # 壳体主体高度 (line 125)
S1_BODY_FULL_H = 290.0            # 含储罐总高 (line 117)
S1_WALL_THICK = 3.0               # 壳体壁厚 (line 126)
S1_TANK_OD = 38.0                 # 储罐外径 Φ38mm (line 111)
S1_TANK_ID = 34.0                 # 储罐内径Φ34mm（壁厚2mm） (line 127)
S1_TANK_LENGTH = 280.0            # 储罐长度280mm (line 111)
S1_TANK_CAP_THREAD = 14.0         # M14快拆螺纹 (line 111)
S1_PUMP_CAVITY_DIA = 20.0         # 泵腔直径Φ20mm (line 128)
S1_PUMP_CAVITY_DEPTH = 25.0       # 泵腔深度25mm (line 128)
S1_SCRAPER_W = 15.0               # 刮涂头宽 (line 115)
S1_SCRAPER_H = 10.0               # 刮涂头高度10mm (line 129)
S1_SCRAPER_D = 5.0                # 刮涂头厚度5mm (line 129)
S1_NTC_BORE_DIA = 3.5             # NTC安装孔Φ3.5mm (line 130)
S1_NTC_BORE_DEPTH = 15.0          # NTC安装孔深15mm (line 130)
S1_WEIGHT = 400.0                 # 约400g (line 119)

# ═══════════════════════════════════════════════════════════════════════════
# §4.1.2 工位2 — AE超声检测 (Station 2, 90°)  (lines 121–165)
# ═══════════════════════════════════════════════════════════════════════════

# --- AE 探头 TWAE-03 (line 122) ---
S2_AE_DIA = 28.0
S2_AE_H = 26.0
S2_AE_WEIGHT = 55.0
S2_AE_CABLE_DIA = 3.0             # 同轴电缆外径

# --- 六轴力传感器 KWR42 (line 130, line 501) ---
S2_FORCE_DIA = 42.0               # Φ42mm
S2_FORCE_H = 12.0                 # KWR42高度Φ42×12mm (line 141, 弹簧限力零件表)
S2_FORCE_BOLT_PCD = 36.0          # 安装孔PCD
S2_FORCE_BOLT_DIA = 3.2           # M3通孔
S2_FORCE_BOLT_NUM = 4
S2_FORCE_CENTER_HOLE = 10.0       # 中心走线孔
S2_FORCE_WEIGHT = 70.0            # 70g (line 155)

# --- 弹簧限力机构 (lines 141–151) ---
S2_SPRING_OD = 8.0                # 弹簧外径 (line 145)
S2_SPRING_WIRE = 0.5              # 线径 (line 145)
S2_SPRING_FREE_L = 12.0           # 自由长度 (line 145)
S2_SPRING_TURNS = 6               # 有效圈数 (line 145)
S2_SPRING_K = 1667.0              # 刚度 N/m (line 145)
S2_GUIDE_DIA = 4.0                # 导向轴 Φ4mm (line 146)
S2_GUIDE_LENGTH = 15.0            # 导向轴长 (line 146)
S2_GUIDE_BORE = 4.1               # 端板导向孔 (line 147)
S2_ENDPLATE_DIA = 12.0            # 上/下端板 Φ12mm (line 147–148)
S2_ENDPLATE_THICK = 2.0           # 端板厚 2mm (line 147–148)
S2_SLEEVE_OD = 12.0               # 套筒外径 (line 149)
S2_SLEEVE_ID = 8.2                # 套筒内径 (line 149)
S2_SLEEVE_H = 14.0                # 套筒高度 (line 149)
S2_SHIM_DIA = 8.0                 # 预紧垫片 Φ8mm (line 150)
S2_SHIM_THICK = 0.5               # 垫片厚 0.5mm (line 150)
S2_LIMITER_WEIGHT = 16.0          # 合计~16g (line 151)

# --- 柔性万向节 (lines 124–127) ---
S2_GIMBAL_OD = 30.0               # 外径 (line 125)
S2_GIMBAL_ID = 12.0               # 内径 (line 125)
S2_GIMBAL_H = 15.0                # 自由高度 (line 125)
S2_GIMBAL_HARDNESS = 40           # Shore A (line 125)
S2_GIMBAL_FLANGE_DIA = 30.0       # 法兰面直径 (line 126)
S2_GIMBAL_FLANGE_THICK = 3.0      # 法兰面厚度
S2_GIMBAL_FLANGE_PCD = 22.0       # 4×M2 PCD (line 126)
S2_GIMBAL_BOLT_DIA = 2.2          # M2通孔
S2_GIMBAL_BOLT_NUM = 4

# --- 零位回复弹簧 (line 127) ---
S2_RETURN_SPRING_DIA = 1.5        # Φ1.5mm拉簧 (line 127)
S2_RETURN_SPRING_NUM = 4

# --- 阻尼垫 (line 128) ---
S2_DAMPER_DIA = 28.0              # 与AE同径
S2_DAMPER_THICK = 2.0             # 约2mm

# --- 压力阵列 (line 129) ---
S2_PRESSURE_W = 20.0              # 20×20mm (line 129)
S2_PRESSURE_H = 20.0
S2_PRESSURE_THICK = 0.5           # 薄膜

# --- 配重块 (line 162) ---
S2_CW_DIA = 12.0                  # 钨合金 Φ12mm (line 162)
S2_CW_H = 7.0                     # 7mm (line 162)
S2_CW_BOLT_DIA = 2.2              # 2×M2 (line 441)
S2_CW_BOLT_SPACING = 8.0          # 螺栓间距
S2_CW_WEIGHT = 50.0               # 50g (line 162)

# --- 模块包络 (lines 163–165) ---
S2_ENVELOPE_DIA = 45.0            # Φ45mm (line 163)
S2_ENVELOPE_H = 120.0             # 120mm (line 163)
S2_WEIGHT = 520.0                 # 约520g (line 165)

# ═══════════════════════════════════════════════════════════════════════════
# §4.1.2 工位3 — 卷带清洁 (Station 3, 180°)  (lines 167–198)
# ═══════════════════════════════════════════════════════════════════════════
S3_BODY_W = 50.0                  # 壳体切向宽 (line 195)
S3_BODY_D = 40.0                  # 壳体径向深 (line 195)
S3_BODY_H = 120.0                 # 壳体轴向高 (line 195)
S3_WALL_THICK = 3.0               # 壳体壁厚

# 清洁带 (lines 171)
S3_TAPE_WIDTH = 15.0              # 带宽15mm (line 171)
S3_TAPE_THICK = 0.12              # 厚0.12mm (line 171)
S3_TAPE_LENGTH = 10000.0          # 10m (line 171)

# 双卷轴 (lines 172–177)
S3_SUPPLY_CORE_ID = 8.0           # 供带芯径 Φ8mm (line 173)
S3_SUPPLY_FULL_OD = 28.0          # 满卷外径 Φ28mm (line 173)
S3_TAKEUP_CORE_ID = 10.0          # 收带芯径 Φ10mm (line 174)
S3_TAKEUP_FULL_OD = 28.0          # 满卷外径 Φ28mm (line 174)
S3_SPOOL_WIDTH = 17.0             # 卷轴宽度 (lines 173–174)
S3_SPOOL_SPACING = 30.0           # 中心距30mm (line 175)
S3_SPOOL_WALL_THICK = 1.0         # 卷轴侧壁

# 轴承 MR105ZZ (line 177)
S3_BEARING_OD = 10.0              # Φ10mm
S3_BEARING_ID = 5.0               # Φ5mm
S3_BEARING_THICK = 4.0            # 4mm
S3_BEARING_NUM = 4                # 每轴2个，共4个
S3_SHAFT_DIA = 5.0                # 轴Φ5mm

# 弹性衬垫 (line 180)
S3_PAD_W = 20.0                   # 20mm
S3_PAD_D = 15.0                   # 15mm
S3_PAD_H = 5.0                    # 5mm
S3_PAD_SHORE_A = 30               # Shore A 30

# 清洁窗口
S3_WINDOW_W = 20.0                # 清洁窗口宽（≥带宽）
S3_WINDOW_D = 15.0                # 清洁窗口深

# 恒力弹簧 (line 179)
S3_TENSION_SPRING_FORCE = 0.3     # 0.3N (line 179)
S3_TENSION_SPRING_STROKE = 60.0   # 有效行程60mm (line 179)

# 溶剂储罐 (line 182)
S3_TANK_OD = 25.0                 # Φ25mm (line 182)
S3_TANK_ID = 21.0                 # 壁厚2mm
S3_TANK_LENGTH = 110.0            # 110mm (line 182)
S3_TANK_CAP_THREAD = 8.0          # M8快拆 (line 185)
S3_TANK_VOLUME_ML = 50.0          # 50mL (line 182)

# 微型电机 (line 186)
S3_MOTOR_DIA = 16.0               # Φ16mm (line 186)
S3_MOTOR_LENGTH = 30.0            # 30mm (line 186)
S3_MOTOR_VOLTAGE = 3.0            # 3V DC

# 翻盖 (line 188)
S3_FLAP_THICK = 2.0               # 硅橡胶翻盖厚度
S3_FLAP_W = 22.0                  # 翻盖宽度

# 配重块 (line 194)
S3_CW_DIA = 14.0                  # 钨合金 Φ14mm (line 194)
S3_CW_H = 13.0                    # 13mm (line 194)
S3_CW_BOLT_DIA = 2.2              # 2×M2 (line 442)
S3_CW_WEIGHT = 120.0              # 120g (line 194)

S3_WEIGHT = 380.0                 # 约380g (line 197)

# 卡扣式带盒 (line 198)
S3_CASSETTE_W = 44.0              # 带盒宽度（壳体内壁宽-间隙）
S3_CASSETTE_D = 34.0              # 带盒深度
S3_CASSETTE_H = 70.0              # 带盒高度（双卷轴区域）
S3_CASSETTE_GUIDE_W = 4.0         # 底部导轨宽度
S3_CASSETTE_NOTCH = 5.0           # 左侧缺角防反插

# ═══════════════════════════════════════════════════════════════════════════
# §4.1.2 工位4 — UHF (Station 4, 270°)  (lines 213–221)
# ═══════════════════════════════════════════════════════════════════════════
S4_SENSOR_DIA = 45.0              # I300-UHF-GT外径Φ45mm (line 228) ※待数据手册确认
S4_SENSOR_H = 60.0                # I300-UHF-GT高度60mm (line 228) ※待数据手册确认
S4_BRACKET_W = 50.0               # L形支架宽50mm (line 231)
S4_BRACKET_D = 40.0               # L形支架深40mm (line 231)
S4_BRACKET_H = 25.0               # L形支架高25mm (line 231)
S4_BRACKET_THICK = 3.0            # L形支架壁厚3mm (line 231)
S4_ENVELOPE_DIA = 50.0            # Φ50mm (line 219)
S4_ENVELOPE_H = 85.0              # 85mm (line 219)
S4_WEIGHT = 650.0                 # 方案A 650g (line 221)

# ═══════════════════════════════════════════════════════════════════════════
# 驱动总成 (lines 25–38)
# ═══════════════════════════════════════════════════════════════════════════
MOTOR_OD = 22.0                   # ECX 22L Φ22mm (line 38)
MOTOR_BODY_LENGTH = 48.0          # 电机本体长约48mm
REDUCER_OD = 22.0                 # GP22C与电机同径 Φ22mm
REDUCER_LENGTH = 25.0             # 减速器长约25mm
MOTOR_TOTAL_LENGTH = 73.0         # 电机+减速器总长 (line 38)
MOTOR_WEIGHT = 180.0              # 电机+减速器约180g (line 36)
REDUCER_OUTPUT_DIA = 8.0          # 输出轴 Φ8mm (line 26)
REDUCER_OUTPUT_LENGTH = 15.0      # 输出轴突出长度
REDUCER_FLANGE_DIA = 25.0         # GP22C法兰面直径

# 电机安装法兰面
MOTOR_FLANGE_DIA = 25.0           # 法兰面直径
MOTOR_FLANGE_THICK = 2.0          # 法兰面厚

# ISO 9409 适配板 (GIS-EE-001-08)
ADAPTER_OD = 63.0                 # ISO 9409-1-50 标准（设计文档§4.5视觉表写Φ63，详细描述写Φ80，取63mm符合ISO标准）
ADAPTER_THICK = 8.0               # 适配板厚度
ADAPTER_CENTER_HOLE = 22.0        # 中心孔（电机/线缆通道）
ADAPTER_PILOT_DIA = 50.0          # 定位止口直径
ADAPTER_PILOT_DEPTH = 2.0         # 止口深度

# ═══════════════════════════════════════════════════════════════════════════
# 信号调理模块 (lines 527–533) — 安装于J3-J4连杆，非末端
# ═══════════════════════════════════════════════════════════════════════════
SIG_COND_W = 140.0                # 壳体宽 (line 528)
SIG_COND_D = 100.0                # 壳体深
SIG_COND_H = 55.0                 # 壳体高
SIG_COND_WEIGHT = 400.0           # 400g (line 256)

# ═══════════════════════════════════════════════════════════════════════════
# 整体重量预算 (lines 245–258)
# ═══════════════════════════════════════════════════════════════════════════
FLANGE_ASSY_WEIGHT = 550.0        # 法兰总成含电机+减速器 (line 249)
CABLES_WEIGHT = 200.0             # 线缆+连接器+绝缘段 (line 254)
TOTAL_WEIGHT_A = 2700.0           # 方案A总重 2.70kg (line 255)
TOTAL_WEIGHT_B = 2400.0           # 方案B总重 2.40kg (line 255)

# ═══════════════════════════════════════════════════════════════════════════
# 颜色定义 (RGBA for visualization)
# ═══════════════════════════════════════════════════════════════════════════
COLOR_AL7075 = "aluminum"
COLOR_PEEK = "goldenrod"
COLOR_STEEL = "gray"
COLOR_TUNGSTEN = "dimgray"
COLOR_RUBBER = "darkslategray"
COLOR_SENSOR = "steelblue"
COLOR_MOTOR = "darkgray"
COLOR_COPPER = "peru"
COLOR_NOVEC = "lightskyblue"
