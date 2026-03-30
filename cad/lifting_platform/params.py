"""
lifting_platform Parametric Dimensions — Single Source of Truth
Based on: 19-液压钳升降平台设计.md V12.0
Units: mm unless noted.
"""
import math

# ═══ 整体参数 ═══
RATED_LOAD_KG = 10
SAFETY_FACTOR = 2.5
DESIGN_LOAD_N = RATED_LOAD_KG * 9.813 * SAFETY_FACTOR  # ≈245.3N
PLATE_THICK = 8
TOTAL_HEIGHT = 280       # 上板顶面 − 下板顶面
STROKE = 192             # 有效行程 mm
STROKE_Z_MIN = 43        # 动板底最低
STROKE_Z_MAX = 235       # 动板底最高

# ═══ 立柱坐标 ═══
LS_X = 60    # 丝杠 X 偏移
LS_Y = 30    # 丝杠 Y 偏移
GS_X = 60    # 导向轴 X 偏移
GS_Y = 30    # 导向轴 Y 偏移

# ═══ 上固定板 SLP-100 ═══
TOP_PLATE_W = 200
TOP_PLATE_H = 100
TOP_PLATE_Z_BOT = 272
TOP_PLATE_Z_TOP = 280

# ═══ 下固定板（左右支撑条）═══
SUP_BAR_W = 50
SUP_BAR_H = 100
SUP_BAR_Z_BOT = -8
SUP_BAR_Z_TOP = 0
LEFT_BAR_X_CENTER = -60
RIGHT_BAR_X_CENTER = 60

# ═══ 动板 SLP-300 ═══
MOV_PLATE_W = 150
MOV_PLATE_H = 100

# ═══ 丝杠 SLP-P01 ═══
SCREW_TOTAL_L = 350
SCREW_THREAD_D = 16      # Tr16x4 大径
SCREW_SHAFT_D = 12       # 轴头直径
SCREW_UPPER_SHAFT_L = 40
SCREW_THREAD_L = 230
SCREW_LOWER_SHAFT_L = 70
SCREW_Z_TOP = 302        # 上轴尖
SCREW_Z_BOT = -48        # 下轴尖

# ═══ 导向轴 SLP-P02 ═══
GUIDE_D = 10
GUIDE_L = 296
GUIDE_Z_TOP = 284
GUIDE_Z_BOT = -12

# ═══ KFL001 轴承座 ═══
KFL_HEIGHT = 30
KFL_BORE = 12

# ═══ 电机支架 SLP-400 ═══
BRACKET_W = 70   # X
BRACKET_H = 90   # Y
BRACKET_CENTER_HOLE = 28
BRACKET_Z_TOP = -8
BRACKET_Z_BOT = -16

# ═══ 电机 NEMA23 ═══
MOTOR_BODY_SIZE = 56.4   # 56.4x56.4 法兰
MOTOR_BODY_L = 56        # 机身长度
MOTOR_FLANGE_Z = -52
MOTOR_Z_BOT = -108

# ═══ T16 螺母 ═══
NUT_FLANGE_D = 32
NUT_FLANGE_THICK = 5
NUT_BODY_D = 22
NUT_BODY_L = 20
NUT_RECESS_DEPTH = 2

# ═══ 导向轴 SLP-P02 ═══
GUIDE_D = 10       # φ10h6 轴径
GUIDE_L = 296      # 有效长度 mm

# ═══ LM10UU ═══
LM10UU_OD = 19
LM10UU_L = 29

# ═══ GT2 同步带系统 ═══
PULLEY_OD = 12.2
BELT_CENTER_DIST = math.sqrt(120**2 + 60**2)  # ≈134.2
PULLEY_Z_TOP = -14
PULLEY_Z_BOT = -23

# ═══ 联轴器 ═══
COUPLER_OD = 25
COUPLER_L = 30  # Z = -30 to -48 (联轴器区间 -30~-48 不精确，实际 30mm 长)
