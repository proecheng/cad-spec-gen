
# 末端执行机构 3D 渲染 Prompt 与设计说明文档

> **文档版本**：V1.0 | **日期**：2026-03-25  
> **源文档**：04-末端执行机构设计.md（V2.4，R9 2026-03-21）  
> **用途**：记录文生图渲染的完整 prompt、§4.10 渲染数据规范，以及各部件对照说明

---

## 1. V1 视角渲染 Prompt（实际使用）

以下为上一轮对话中传入 `create_image` 工具的完整 prompt 原文：

```
Technical illustration, cutaway-style 3D render, matte studio lighting, neutral gray gradient 
background, 8K resolution, precise engineering visualization with dimensioned callout labels.

CAMERA: V1 Front-Left Isometric — elevation 30°, azimuth 45°. The flange disc is HORIZONTAL 
(like a tabletop, ∥XY plane). Z-axis is vertical (parallel to gravity). +Z = arm-side (top), 
-Z = workstation-side (bottom, toward GIS shell).

ASSEMBLY STRUCTURE (from +Z arm-side down to -Z GIS-shell side):

Layer L1 (+Z top, arm-side):
- flat dark gray adapter plate (ISO 9409, GIS-EE-001-08): Φ63×8mm disc, 4×M6 bolt holes 
  @PCD50mm. ONLY on arm-side.
- single dark gray cylinder (ECX 22L motor + GP22C gearbox): Φ22×73mm, mounted on adapter 
  plate back face (+Z side), axis along Z. ONLY on arm-side, NEVER on workstation side.

Layer L3 (Z=0 reference, center):
- cross-shaped dark gray disc (flange body, GIS-EE-001-01): Φ90×25mm, 7075-T6 aluminum, 
  hard anodized dark gray. Four 12×8×40mm cantilever arms extend radially at 0°/90°/180°/270°, 
  each ending in a 40×40mm mounting face at R=65mm from rotation axis. The center hole Φ22mm 
  is EMPTY (no mechanism protrudes through it toward workstation side).

Layer L4 (Z=-25mm to -30mm, just below flange):
- black FKM O-ring: Φ80×2.4mm cross-section, seated in groove on aluminum side.
- golden amber ring (PEEK insulation ring, GIS-EE-001-02): Φ86×5mm, semi-translucent amber 
  gold color. Slightly SMALLER than flange (Φ86 < Φ90). Thin ring, NOT a large disc.

Layer L5a — Station 1 (0°, left-front foreground in V1 view):
Applicator Module (GIS-EE-002) hanging vertically DOWN (-Z) from 0° cantilever arm end:
- applicator aluminum box: 60×40×55mm dark gray body, hanging from mounting face.
- LONG silver tank (LONGEST part, Φ38×280mm): SUS316L brushed silver, axis ∥XY plane 
  (HORIZONTAL, extending radially outward along cantilever axis), ⊥ rotation axis Z. 
  M14 quick-release thread at outer end.
- tan silicone brush tip: 15×10×5mm brownish-tan, at the BOTTOM of applicator module.

Layer L5b — Station 2 (90°, right-front foreground in V1 view):
AE Detection Module (GIS-EE-003) — serial stack hanging vertically DOWN (-Z) from 90° arm:
- Force sensor KWR42 (Φ42×20mm, silver disc) bolted to mounting face → 
- tight helix coil spring in sleeve (spring limiter mechanism: OD=8mm compression spring, 
  ~6 visible coils, inside Φ12×14mm aluminum sleeve, with Φ4mm chrome guide shaft. 
  Axis along -Z, ⊥ flange face, NEVER horizontal) →
- black rubber universal joint (Φ30×15mm silicone rubber gimbal) →
- Damping pad →
- AE probe TWAE-03 (Φ28×26mm) at bottom.
Total stack height ~120mm along -Z. Spring coils MUST be visible.

Layer L5c — Station 3 (180°, right-rear partially occluded in V1 view):
Tape-Wipe Cleaning Module (GIS-EE-004) hanging vertically DOWN from 180° arm:
- cleaner aluminum box: 50×40×120mm dark gray body with dual spool chambers inside.
- SHORT small silver tank (solvent reservoir, Φ25×110mm): SUS304 polished silver, axis 
  along -Z (VERTICAL, ∥ rotation axis), mounted on side wall of cleaner box, PARALLEL 
  to module body. Much shorter and thinner than the applicator reservoir.
- Silicone rubber flip-cover at cleaning window (bottom).
- Tungsten counterweight (Φ14×13mm, 120g) at module TOP.

Layer L5d — Station 4 (270°, left-rear partially occluded in V1 view):
UHF Detection Module (GIS-EE-005) hanging vertically DOWN from 270° arm:
- L-shaped bracket: dark gray 7075-T6 aluminum, short edge 25mm bolted to mounting face, 
  long edge 50mm extending down.
- cylindrical sensor with gold SMA connector (I300-UHF-GT, Φ45×60mm): clamped in L-bracket 
  arc. SMA RF connector (gold) facing UP (+Z, away from GIS shell), antenna end facing 
  DOWN (-Z, toward GIS shell).

Cable routing:
- black cable chain (Igus E2 micro, ID 6mm): black engineering plastic, arc-shaped along 
  flange edge near 0° position, fixed end on adapter plate, moving end on flange.

GEOMETRY ANCHORS with dimension callouts:
- Label "Φ90mm" pointing to flange disc diameter
- Label "Φ86mm PEEK" pointing to golden amber ring
- Label "Φ38×280mm 储液罐" pointing to LONG horizontal silver tank
- Label "Φ25×110mm 溶剂罐" pointing to SHORT vertical silver tank
- Label "弹簧限力 K=1667N/m" pointing to visible coil spring in AE stack
- Label "KWR42 力传感器" pointing to force sensor disc
- Label "TWAE-03 AE探头" pointing to AE probe at bottom of stack
- Label "I300-UHF-GT" pointing to UHF cylindrical sensor
- Label "ECX 22L + GP22C" pointing to motor cylinder on arm-side
- Label "Igus E2 拖链" pointing to black cable chain

CRITICAL CONSTRAINTS (negative prompts):
- N1: Flange center hole Φ22mm is EMPTY — no mechanism protrudes through it downward.
- N2: Motor+gearbox cylinder (Φ22×73mm) is ONLY above the flange (arm-side), NEVER below.
- N3: LONG reservoir (Φ38×280) is always HORIZONTAL (∥XY); SHORT solvent tank (Φ25×110) 
  is always VERTICAL (∥Z). Do NOT swap their orientations.
- N4: Do NOT invent parts not described in this specification.
- N5: Signal conditioning module (GIS-EE-006) is NOT on the flange — do NOT draw it.
- N6: PEEK ring (Φ86mm) is slightly SMALLER than flange (Φ90mm), only 5mm thin amber ring.
- N7: All four station modules mount at cantilever arm TIPS (R=65mm), NOT on the disc face.
- N8: Flange disc is HORIZONTAL (like a tabletop), NOT a vertical wheel.
- N9: AE spring limiter axis is always ⊥ flange face (along -Z), NEVER parallel to flange.
- N10: All four station modules hang vertically DOWN (-Z) from arm tips, NOT horizontally outward.

Lighting: soft studio key light from upper-left, fill light from right, subtle rim light. 
Clean technical illustration style with white dimension lines and Chinese labels.
```

---

## 2. 装配姿态定义

本末端执行器安装于 RM65-B 机械臂末端，工作时朝下对准 GIS 壳体。

| 术语 | 定义 | 等价表述 |
|------|------|---------|
| **旋转轴方向** | 垂直方向（平行于重力） | Z轴 |
| **法兰盘平面** | 水平面（像桌面） | XY平面 |
| **"上方" (+Z)** | 机械臂侧（适配板+电机所在侧） | arm-side / top |
| **"下方" (-Z)** | GIS壳体侧（工位模块悬挂侧） | workstation-side / bottom |
| **"径向外"** | 从法兰中心到悬臂末端（在XY平面内） | radially outward in flange plane |

### 强制规则（所有 prompt 必须遵守）

1. 法兰盘始终**水平**（像桌面），**不是竖直的车轮**
2. 所有工位模块从悬臂末端**沿 -Z 垂直向下悬挂**（垂直于法兰面）
3. "水平"指 ∥ 法兰面（XY平面），"垂直"指 ⊥ 法兰面（沿Z轴）
4. 储液罐"水平" = 在 XY 平面内径向外伸，溶剂罐"垂直" = 沿 Z 轴

---

## 3. 装配层叠结构表（§4.10.1）

从机械臂侧 (+Z) 到 GIS 壳体侧 (-Z) 的物理连接顺序：

| 层级 | 零件/模块 | 固定/运动 | 连接方式 | 安装面朝向 | 相对上一层偏移 | 模块轴线方向 |
|------|----------|----------|---------|-----------|-------------|-------------|
| L1 | ISO 9409适配板 (GIS-EE-001-08) | 固定(机械臂) | 4×M6@PCD50mm, 9.0Nm | 正面朝-Z | 基准原点 | 盘面∥XY |
| L2 | ECX 22L电机+GP22C减速器 | 固定(适配板) | 4×M3, 0.7Nm | 背面(+Z侧) | Z=+73mm(向上) | 轴沿Z |
| L2 | Igus E2拖链段 | 固定端→适配板,活动端→法兰 | 2×M2 L形支架 | 法兰边缘0°位置 | 径向R≈45mm | 弧形∥XY |
| L3 | 法兰本体 Φ90mm (GIS-EE-001-01) | 旋转(90°×4) | 过盈配合Φ8 H7/k6 + M4压紧 | 正面朝-Z | Z=0(参考面) | 盘面∥XY |
| L3 | 弹簧销×4 (GIS-EE-001-07) | 固定(减速器壳体侧) | Φ4×20mm锥形头 | 径向@R=42mm | — | 轴沿Z |
| L4 | O型圈 FKM Φ80×2.4 | 随法兰旋转 | 嵌入密封槽 | — | Z=-25mm(向下) | 环∥XY |
| L4 | PEEK绝缘环 Φ86mm (GIS-EE-001-02) | 随法兰旋转 | 6×M3+碟簧垫圈 | 正面朝-Z | Z=-27mm(向下) | 盘面∥XY |
| L5a | 涂抹工位(0°) (GIS-EE-002) | 随法兰旋转 | 4×M3+Φ3销, 0.7Nm | 悬臂末端 | R=65mm, θ=0° | **壳体轴沿-Z（垂直向下），储罐轴∥XY（水平径向外伸）** |
| L5b | AE检测工位(90°) (GIS-EE-003) | 随法兰旋转 | 4×M3+Φ3销, 0.7Nm | 悬臂末端 | R=65mm, θ=90° | **串联堆叠轴沿-Z（垂直向下），弹簧轴⊥法兰面** |
| L5c | 卷带清洁工位(180°) (GIS-EE-004) | 随法兰旋转 | 4×M3+Φ3销, 0.7Nm | 悬臂末端 | R=65mm, θ=180° | **壳体轴沿-Z（垂直向下），溶剂罐轴沿-Z（垂直）** |
| L5d | UHF检测工位(270°) (GIS-EE-005) | 随法兰旋转 | 4×M3+Φ3销, 0.7Nm | 悬臂末端 | R=65mm, θ=270° | **L支架挂载沿-Z（垂直向下）** |

> **CAD消费**：assembly.py 读取偏移量（Z/R/θ）定位零件  
> **文生图消费**：ASSEMBLY STRUCTURE 段直接从此表生成层叠顺序和连接描述

---

## 4. 视觉标识表（§4.10.2）

为每个零件/模块定义唯一视觉标签，防止 AI 混淆相似零件。

| 零件 | 材质 | 表面颜色 | 唯一标签 | 外形尺寸(mm) | 方向约束 |
|------|------|---------|---------|------------|---------|
| 法兰本体 | 7075-T6铝合金 | 深灰色（硬质阳极氧化） | cross-shaped dark gray disc | Φ90×25, 4悬臂12×8×40 | 十字中心对称 |
| PEEK绝缘环 | PEEK | 琥珀金色（半透明） | golden amber ring | Φ86×5 | slightly smaller than flange |
| ISO 9409适配板 | 7075-T6铝合金 | 深灰色 | flat dark gray adapter plate | Φ63×8 | ONLY on arm-side |
| 电机+减速器 | — | 深灰色金属壳 | single dark gray cylinder | Φ22×73 | ONLY on arm-side, NEVER on workstation side |
| 储液罐 | SUS316L不锈钢 | 银色拉丝 | LONG silver tank (LONGEST part) | Φ38×280 | 轴线∥XY平面（∥法兰面），沿径向外伸，⊥旋转轴Z |
| 溶剂罐 | SUS304不锈钢 | 银色抛光 | SHORT small silver tank | Φ25×110 | 轴线沿-Z（∥旋转轴），⊥法兰面 |
| 涂抹模块壳体 | 7075-T6铝合金 | 深灰色 | applicator aluminum box | 60×40×55 | 壳体从悬臂末端沿-Z垂直向下悬挂 |
| AE串联堆叠 | 混合 | 银+黑+弹簧可见 | serial stack with visible coil spring | Φ42×120(总长) | 轴线沿-Z(⊥法兰面)，从悬臂末端垂直向下悬挂，NEVER水平 |
| 弹簧限力机构 | 65Mn弹簧钢 | 银色弹簧+铝套筒 | tight helix coil spring in sleeve | OD=8mm, ~6 turns | 轴线沿-Z(⊥法兰面)，与AE堆叠同轴，NEVER∥法兰面 |
| 清洁模块壳体 | 7075-T6铝合金 | 深灰色 | cleaner aluminum box | 50×40×120 | 壳体从悬臂末端沿-Z垂直向下悬挂 |
| UHF支架 | 7075-T6铝合金 | 深灰色 | L-shaped bracket | 60×30×80 | L形，传感器夹持 |
| UHF传感器 | — | 金色SMA接头可见 | cylindrical sensor with gold SMA connector | Φ45×60 | 夹持于L支架 |
| 拖链 | 黑色工程塑料 | 黑色 | black cable chain | 内径6mm | 沿法兰边缘弧形 |
| 刮涂头 | 硅橡胶 | 棕褐色 | tan silicone brush tip | 20×10×8 | 涂抹模块底端 |
| 柔性关节 | 硅橡胶Shore A 40 | 黑色 | black rubber universal joint | Φ20×15 | AE串联底端 |

> **CAD消费**：material_type 参数匹配 drawing.py 的技术要求区（al/peek/steel/rubber）  
> **文生图消费**：GEOMETRY ANCHOR 段直接引用唯一标签列

---

## 5. 迭代渲染分组表（§4.10.3）

将 15+ 零件分为 5 个迭代步骤（底图 + 4 个叠加步骤），前景优先。

| 步骤 | 添加内容 | 画面位置 | prompt要点 | 依赖步骤 |
|------|---------|---------|-----------|---------|
| 1 | 主体框架：法兰+PEEK环+电机减速器+适配板+拖链 | 全画面中心 | cross-shaped dark gray disc, golden amber ring, 空悬臂末端螺栓孔可见 | — |
| 2 | 涂抹工位(0°)：壳体+储液罐+刮涂头 | 画面左下前景 | LONG horizontal silver tank (280mm, LONGEST part), tan brush tip at bottom | 1 |
| 3 | AE工位(90°)：力传感器+弹簧限力+万向节+AE探头 | 画面右下前景 | serial stack with visible coil spring (~6 turns), 从悬臂向下串联 | 1 |
| 4 | 清洁工位(180°)：壳体+溶剂罐+清洁带盒 | 画面右后(部分遮挡) | SHORT vertical silver tank (110mm, much shorter than reservoir), cleaner box | 1 |
| 5 | UHF工位(270°)：L支架+传感器 | 画面左后(部分遮挡) | L-bracket with cylindrical sensor, gold SMA connector visible | 1 |

> **分组依据**：总零件约15个主要模块/零件，ceil(15/2.5)+1=7，合并紧密相关件后压缩至5步。前景（涂抹0°+AE90°）在 Step 2-3，背景（清洁180°+UHF270°）在 Step 4-5。

---

## 6. 视角规划表（§4.10.4）

| 视角ID | 名称 | 仰角/方位 | 可见模块 | 被遮挡模块 | 重点表达 |
|--------|------|----------|---------|-----------|---------|
| **V1** | 前左等轴测 | 30°/45° | 涂抹(0°)+AE(90°)+PEEK环+拖链+法兰正面 | 清洁(180°部分)+UHF(270°部分)+电机(适配板后) | 全貌+工位分布+PEEK色带 |
| V2 | 后右俯视 | 40°/225° | 电机+减速器+清洁(180°)+UHF(270°)+拖链+适配板 | 涂抹(0°部分)+AE(90°部分) | 驱动结构+背面布局 |
| V3 | 纯侧视 | 0°/90° | AE串联堆叠+UHF支架+法兰层叠(Al+PEEK) | 涂抹+清洁(正交方向) | 层叠结构+弹簧限力 |
| V4 | 爆炸图 | 30°/45° | 全部零件(分离) | 无 | 装配层级L1→L5 |
| V5 | 三视图 | 正投影 | 全部 | 无(虚线表示) | 尺寸标注+螺栓孔位 |

> 本次渲染采用 **V1 前左等轴测** 视角。

---

## 7. 否定约束表（§4.10.5）

AI 容易犯的错误，生成 CRITICAL CONSTRAINTS 段：

| 约束ID | 约束描述 | 原因 |
|--------|---------|------|
| **N1** | 法兰中心孔是空的（Φ22mm通孔），无任何机构从法兰中心向工位侧伸出；减速器输出轴在内部不可见 | AI倾向在空位补零件 |
| **N2** | 电机+减速器(Φ22×73mm深灰圆柱)仅在臂侧(法兰上方)，绝不在工位侧(法兰下方) | 方向歧义导致电机画反 |
| **N3** | LONG储液罐(Φ38×280mm)始终水平沿悬臂轴向延伸；SHORT溶剂罐(Φ25×110mm)始终垂直平行于模块高度 | 两个银色圆柱易混淆 |
| **N4** | 不要发明设计文档中未描述的零件或连接件 | AI创造性补全倾向 |
| **N5** | 信号调理模块(GIS-EE-006)不在法兰上，安装在机械臂J3-J4连杆上，距法兰250mm，渲染末端执行器时不画此模块 | 位置容易搞错 |
| **N6** | PEEK环(Φ86mm)略小于法兰(Φ90mm)，厚度仅5mm，是琥珀金色薄环而非大圆盘 | AI容易画成与法兰等大 |
| **N7** | 四个工位模块安装在悬臂末端(R=65mm)，不在法兰圆盘表面上 | AI容易把模块画在盘面上 |
| **N8** | 法兰圆盘是**水平的**（像桌面），不是竖直的轮子；Z轴垂直向上，法兰面∥XY平面 | AI默认竖直展示圆盘 |
| **N9** | AE弹簧限力机构的轴线始终⊥法兰面（沿-Z），NEVER与法兰面平行（NEVER水平） | V1渲染曾画反弹簧方向 |
| **N10** | 所有四个工位模块从法兰悬臂末端沿-Z方向垂直向下悬挂，不向侧面水平伸出 | AI容易把模块画成径向水平 |

---

## 8. 各工位关键参数速查

### 8.1 法兰总成核心参数

| 参数 | 设计值 |
|------|-------|
| 旋转分度 | 90° × 4工位 |
| 驱动 | Maxon ECX SPEED 22L + GP22C行星减速器（53:1） |
| 定位精度 | 重复定位优于0.2° |
| 切换时间 | ＜1.5s（90°切换） |
| 旋转范围 | ±135°（限位旋转） |
| 法兰本体直径 | Φ90±0.1mm |
| 法兰厚度 | 30±0.5mm（铝合金25mm + PEEK 5mm） |
| 接口标准 | ISO 9409-1-50-4-M6 |

### 8.2 四工位模块总览

| 工位 | 角度 | 功能 | 模块包络尺寸 | 重量 |
|------|------|------|-------------|------|
| 工位1 | 0° | 耦合剂涂抹 | 60×40×290mm（含储罐延伸） | 400g |
| 工位2 | 90° | AE超声波检测 | Φ45×120mm（串联堆叠） | 520g |
| 工位3 | 180° | 卷带擦拭清洁 | 50×40×120mm + 溶剂罐Φ25×110mm | 380g |
| 工位4 | 270° | UHF特高频检测 | Φ50×85mm | 650g（方案A） |

### 8.3 整体重量预算（方案A）

| 组件 | 重量 |
|------|------|
| 法兰本体（含电机、减速器） | 550g |
| 工位1 涂抹模块 | 400g |
| 工位2 AE检测模块 | 520g |
| 工位3 卷带清洁模块 | 380g |
| 工位4 UHF检测模块 | 650g |
| 线缆、连接器、绝缘段 | 200g |
| **末端执行器合计** | **≈2.70kg** |

> RM65-B 额定负载 5kg，余量 2.30kg。

---

## 9. 传动链与装配层叠示意

### 9.1 传动链（旋转/固定关系）

```
┌─────────────────────────────────────────────────────────┐
│  RM65-B 机械臂末端法兰（ISO 9409接口）                    │
│         │ 4×M6@PCD50mm                                   │
│         ▼                                                │
│  ┌─ ISO 9409 适配板 (GIS-EE-001-08) ─┐  ← 固定件        │
│  │  4×M3↓                             │                  │
│  │  GP22C 减速器壳体 ← 固定件          │                  │
│  │  │ (内部齿轮传动53:1)               │                  │
│  │  ECX 22L 电机壳体 ← 固定件          │                  │
│  └──────────────────────────────────────┘                 │
│                    │                                      │
│            减速器输出轴 Φ8mm                               │
│            (过盈配合 H7/k6 + M4压紧螺栓)                   │
│                    ▼                                      │
│  ┌─ 法兰本体 Φ90mm (GIS-EE-001-01) ─┐  ← 旋转件         │
│  │  十字悬臂 ×4                       │                  │
│  │  弹簧销孔 ×4 @R42mm               │                  │
│  │  PEEK绝缘环（正面，M3×6螺栓连接）   │                  │
│  │  工位模块 ×4（正面，M3×8螺栓连接）   │                  │
│  └──────────────────────────────────────┘                 │
│                                                          │
│  弹簧销定位：安装在减速器输出端（固定侧）壳体上，            │
│  销头插入法兰外缘旋转侧销孔，每90°一个锁止位。              │
│  15N弹簧力锁止 → 物理级定位冗余。                          │
└─────────────────────────────────────────────────────────┘
```

### 9.2 层叠装配关系（从机械臂侧到 GIS 壳体侧）

```
机械