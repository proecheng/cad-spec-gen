# CAD Spec — 末端执行机构 (GIS-EE)
<!-- Generated: 2026-04-24 21:43 | Source: D:/Work/cad-tests/04-末端执行机构设计.md | Hash: 8344444b6bcc -->

## 1. 全局参数表

| 参数名 | 值 | 单位 | 公差 | 来源 | 备注 |
| --- | --- | --- | --- | --- | --- |
| INDEX | 90 | ° |  | L24 |  |
| SWITCH_T | 1.5 | s |  | L27 | S形速度曲线 |
| ROT_RANGE | 135 | ° | ±135° | L28 | 柔性线缆缠绕方案 |
| FLANGE_DIA | 90 | mm | ±0.1mm | L29 | 圆盘部分外径 |
| ARM_L | 40 | mm |  | L30 | 4根等长，90°等分 |
| FLANGE_THICK | 30 | mm | ±0.5mm | L32 | 铝合金段25mm + PEEK段5mm |
| MOTOR_RATED_TORQUE | 0.027 | N |  | L36 | 堵转2.85Nm，满足切换需求 |
| MOTOR_OD | 22 | mm |  | L37 | 安装于法兰背面中心 |
| OD | 86 |  | ±0.05mm | L108 |  |
| ID | 40 |  | ±0.1mm | L109 |  |
| THICK | 5 |  | ±0.2mm | L110 |  |
| CREEP_D | 10 | mm |  | L112 |  |
| WITHSTAND_V | 2500 | V |  | L113 |  |
| INSUL_R | 100 | MΩ |  | L114 |  |
| WALL | 3 | mm |  | L190 | 7075-T6铝合金，兼顾强度与轻量化 |
| OD_2 | 38 | mm |  | L191 | SUS316L不锈钢，耐硅脂腐蚀 |
| FLANGE_BODY_OD | 90 | mm | ±0.1mm | L429 | 圆盘部分 |
| FLANGE_BODY_ID | 22 | mm | +0.021/0mm | L430 | 与减速器壳体Φ22mm定位配合（内含Φ8mm阶梯孔用于输出轴过盈配合） |
| FLANGE_AL_THICK | 25 | mm | ±0.5mm | L431 | 不含PEEK段 |
| FLANGE_TOTAL_THICK | 30 | mm | ±0.5mm | L432 | 铝合金25mm+PEEK 5mm |
| ARM_SEC_W | 12 | mm | ±0.2mm | L433 | 矩形截面 |
| ARM_SEC_THICK | 8 | mm | ±0.2mm | L434 | 与法兰端面平齐 |
| ARM_L_2 | 40 | mm | ±0.3mm | L435 | 4根等长 |
| FLANGE_MOUNT_FACE | 50 | mm |  | L438 | 机械臂侧，4×M6螺栓孔 |
| SPRING_PIN_BORE | 4 | mm | +0.012/0mm | L440 | 锥形头弹簧销，深度12mm |
| FLANGE_BOLT_PCD | 70 | mm | ±0.2mm | L441 | 6×M3螺栓孔，与PEEK段通孔对应 |
| SPRING_PIN_DIA | 4 | mm |  | L502 | 销：g6（-0.004/-0.012mm） |
| SPRING_L | 20 | mm |  | L503 | 含锥形头5mm |
| SPRING_F | 15 | N |  | L505 | 抵抗旋转惯量+可靠定位 |
| SPRING_POS_ACC | 0.2 | ° |  | L508 | 在R=65mm处对应≤0.23mm |
| MOUNT_FLAT | 0.03 | mm |  | L524 |  |
| TOTAL_COST | 60922.0 | 元 |  | [计算] | BOM合计 (48零件) |
| BOM_PARTS_COUNT | 48 |  |  | [计算] | 6总成 |
| BOM_COMPLETENESS | 99.3 | % |  | [计算] | 143/144 cells filled |

## 2. 公差与表面处理

### 2.1 尺寸公差

| 参数名 | 标称值 | 上偏差 | 下偏差 | 配合代号 | 标注文本 |
| --- | --- | --- | --- | --- | --- |
| FLANGE_BODY_OD | 90mm | +0.1 | -0.1 |  | ±0.1mm |
| FLANGE_BODY_ID | 22mm | +0.021 | 0 |  | +0.021/0mm（H7） |
| FLANGE_AL_THICK | 25mm | +0.5 | -0.5 |  | ±0.5mm |
| FLANGE_TOTAL_THICK | 30mm | +0.5 | -0.5 |  | ±0.5mm |
| ARM_SEC_W | 12mm | +0.2 | -0.2 |  | ±0.2mm |
| ARM_SEC_THICK | 8mm | +0.2 | -0.2 |  | ±0.2mm |
| ARM_L | 40mm | +0.3 | -0.3 |  | ±0.3mm |
| MOUNT_FACE | 65mm | +0.3 | -0.3 |  | ±0.3mm |
| ARM_MOUNT_FACE | 40 | +0.2 | -0.2 |  | ±0.2mm |
| SPRING_PIN_BORE | 4mm | +0.012 | 0 |  | H7（+0.012/0mm） |
| BOLT_PCD | 70mm | +0.2 | -0.2 |  | ±0.2mm |

### 2.2 形位公差

| 符号 | 值 | 基准 | 适用零件 |
| --- | --- | --- | --- |
| （暂无数据） |  |  | |

### 2.3 表面处理

| 零件 | Ra(µm) | 处理方式 | material_type |
| --- | --- | --- | --- |
| 一般面粗糙度 | **一般面粗糙度** |  |  |
| 工作温度 | 工作温度 |  |  |
| 加工后处理 | **加工后处理** |  |  |
| 老化评估 | 老化评估 |  |  |
| 安装面平面度 | 安装面平面度 |  |  |
| PEEK绝缘环 | golden amber ring |  |  |
| ISO 9409适配板 | flat dark gray adapter plate |  |  |
| 电机+减速器 | single dark gray cylinder |  |  |
| 储液罐 | LONG silver tank (LONGEST part) |  |  |
| 溶剂罐 | SHORT small silver tank |  |  |
| 涂抹模块壳体 | applicator aluminum box |  |  |
| AE串联堆叠 | serial stack with visible coil spring |  |  |
| 弹簧限力机构 | tight helix coil spring in sleeve |  |  |
| 清洁模块壳体 | cleaner aluminum box |  |  |
| UHF支架 | L-shaped bracket |  |  |
| UHF传感器 | cylindrical sensor with gold SMA connector |  |  |
| 拖链 | black cable chain |  |  |
| 刮涂头 | tan silicone brush tip |  |  |
| 柔性关节 | black rubber universal joint |  |  |
| 2 | LONG horizontal silver tank (280mm, LONGEST part), tan brush tip at bottom |  |  |
| 3 | serial stack with visible coil spring (~6 turns), 从悬臂向下串联 |  |  |
| 4 | SHORT vertical silver tank (110mm, much shorter than reservoir), cleaner box |  |  |
| 5 | L-bracket with cylindrical sensor, gold SMA connector visible |  |  |
| 法兰本体 | Ra3.2 |  | 7075-T6铝合金 |

## 3. 紧固件清单

| 连接位置 | 螺栓规格 | 数量 | 力矩(Nm) | 材料等级 | 备注 |
| --- | --- | --- | --- | --- | --- |
| 法兰→RM65-B（ISO 9409） | M6×12 内六角 12.9级 | 4 | 9.0±0.5 |  | ISO 9409标准要求 |
| PEEK段→法兰本体 | M3×10 内六角 A2-70不锈钢 | 6 | 0.7±0.1 |  | +碟形弹簧垫圈DIN 2093 A6 |
| 工位模块→悬臂 | M3×8 内六角 A2-70不锈钢 | 4 | 0.7±0.1 |  | 各工位统一 |
| 减速器→法兰背面 | M3×6 内六角 A2-70不锈钢 | 4 | 0.7±0.1 |  | GP22C安装 |
| 信号调理模块→臂连杆 | M4×10 内六角 A2-70不锈钢 | 4 | 1.5±0.2 |  | 抱箍+L型支架 |
| 力传感器→悬臂安装面 | M3×6 内六角 A2-70不锈钢 | 4 | 0.5±0.1 |  | 力传感器标准接口 |
| 柔性关节法兰面 | M2×5 内六角 A2-70不锈钢 | 4 | 0.2±0.05 |  | 上下法兰面各4颗 |
| ZIF防护盖 | M3×5 十字盘头 A2-70不锈钢 | 2 | 0.5±0.1 |  |  |
| 配重块（工位2） | M2×6 内六角 A2-70不锈钢 | 2 | 0.2±0.05 |  |  |
| 配重块（工位3） | M2×6 内六角 A2-70不锈钢 | 2 | 0.2±0.05 |  | 120g钨合金 |

## 4. 连接矩阵

| 零件A | 零件B | 连接类型 | 配合代号 | 预紧力矩 | 装配顺序 |
| --- | --- | --- | --- | --- | --- |
| ISO 9409适配板 (GIS-EE-001-08) | ECX 22L电机+GP22C减速器 | 4×M3, 0.7Nm |  |  | 1 |
| ISO 9409适配板 (GIS-EE-001-08) | Igus E2拖链段 | 2×M2 L形支架 |  |  | 2 |
| Igus E2拖链段 | 法兰本体 Φ90mm (GIS-EE-001-01) | 过盈配合Φ8 H7/k6 + M4压紧 | H7/k6 |  | 3 |
| Igus E2拖链段 | 弹簧销×4 (GIS-EE-001-07) | Φ4×20mm锥形头 |  |  | 4 |
| 弹簧销×4 (GIS-EE-001-07) | O型圈 FKM Φ80×2.4 | 嵌入密封槽 |  |  | 5 |
| 弹簧销×4 (GIS-EE-001-07) | PEEK绝缘环 Φ86mm (GIS-EE-001-02) | 6×M3+碟簧垫圈 |  |  | 6 |
| PEEK绝缘环 Φ86mm (GIS-EE-001-02) | 涂抹工位(0°) (GIS-EE-002) | 4×M3+Φ3销, 0.7Nm |  |  | 7 |
| 涂抹工位(0°) (GIS-EE-002) | AE检测工位(90°) (GIS-EE-003) | 4×M3+Φ3销, 0.7Nm |  |  | 8 |
| AE检测工位(90°) (GIS-EE-003) | 卷带清洁工位(180°) (GIS-EE-004) | 4×M3+Φ3销, 0.7Nm |  |  | 9 |
| 卷带清洁工位(180°) (GIS-EE-004) | UHF检测工位(270°) (GIS-EE-005) | 4×M3+Φ3销, 0.7Nm |  |  | 10 |
| UHF检测工位(270°) (GIS-EE-005) | 全部 |  |  |  | 11 |

## 5. BOM树

**编号规则**: GIS-EE-NNN-NN

| 料号 | 名称 | 材质/型号 | 数量 | 自制/外购 | 单价 |
| --- | --- | --- | --- | --- | --- |
| **GIS-EE-001** | **法兰总成** | — | 1 | 总成 | — |
| GIS-EE-001-01 | 法兰本体（含十字悬臂） | 7075-T6铝合金 | 1 | 自制 | 3000元 |
| GIS-EE-001-02 | PEEK绝缘段 | PEEK | 1 | 自制 | 500元 |
| GIS-EE-001-03 | O型圈 | FKM Φ80×2.4 | 1 | 外购 | 15元 |
| GIS-EE-001-04 | 碟形弹簧垫圈 | DIN 2093 A6 | 6 | 外购 | 30元 |
| GIS-EE-001-05 | 伺服电机 | Maxon ECX SPEED 22L | 1 | 外购 | 2500元 |
| GIS-EE-001-06 | 行星减速器 | Maxon GP22C (53:1) | 1 | 外购 | 1800元 |
| GIS-EE-001-07 | 弹簧销组件（含弹簧） | Φ4×20mm锥形头 | 4 | 外购 | 200元 |
| GIS-EE-001-08 | ISO 9409适配板 | 7075-T6铝合金 | 1 | 自制 | 500元 |
| GIS-EE-001-09 | FFC线束总成 | Molex 15168, 20芯×500mm | 1 | 外购 | 500元 |
| GIS-EE-001-10 | ZIF连接器 | Molex 5052xx | 2 | 外购 | 60元 |
| GIS-EE-001-11 | Igus拖链段 | E2 micro, 内径6mm | 1 | 外购 | 80元 |
| GIS-EE-001-12 | 定位销 | Φ3×6mm H7/g6 | 4 | 外购 | 20元 |
| **GIS-EE-002** | **工位1涂抹模块** | — | 1 | 总成 | — |
| GIS-EE-002-01 | 涂抹模块壳体 | 7075-T6铝合金 | 1 | 自制 | 800元 |
| GIS-EE-002-02 | 储罐 | 不锈钢Φ38×280mm | 1 | 外购 | 200元 |
| GIS-EE-002-03 | 齿轮泵 |  | 1 | 外购 | 1500元 |
| GIS-EE-002-04 | 刮涂头 | 硅橡胶 | 1 | 外购 | 30元 |
| GIS-EE-002-05 | LEMO插头 | FGG.0B.307 | 1 | 外购 | 150元 |
| **GIS-EE-003** | **工位2 AE检测模块** | — | 1 | 总成 | — |
| GIS-EE-003-01 | AE传感器 | TWAE-03 | 1 | 外购 | 3000元 |
| GIS-EE-003-02 | 六轴力传感器 | ATI Nano17/坤维KWR42 | 1 | 外购 | 25000元 |
| GIS-EE-003-03 | 弹簧限力机构总成 | 见§4.1.2零件表 | 1 | 自制 | 300元 |
| GIS-EE-003-04 | 柔性关节（万向节） | 硅橡胶Shore A 40 | 1 | 自制 | 200元 |
| GIS-EE-003-05 | 阻尼垫 | 黏弹性硅橡胶 | 1 | 外购 | 50元 |
| GIS-EE-003-06 | 压力阵列 | 4×4薄膜 20×20mm | 1 | 外购 | 500元 |
| GIS-EE-003-07 | 配重块 | 钨合金Φ12×7mm/50g | 1 | 外购 | 200元 |
| GIS-EE-003-08 | LEMO插头 | FGG.0B.307 | 1 | 外购 | 150元 |
| GIS-EE-003-09 | Gore柔性同轴 | MicroTCA系列×500mm | 1 | 外购 | 800元 |
| **GIS-EE-004** | **工位3卷带清洁模块** | — | 1 | 总成 | — |
| GIS-EE-004-01 | 清洁模块壳体（含卷轴腔+清洁窗口） | 7075-T6铝合金 | 1 | 自制 | 800元 |
| GIS-EE-004-02 | 清洁带盒（供带卷轴+收带卷轴+10m无纺布带） | 超细纤维无纺布 | 1 | 外购 | 45元 |
| GIS-EE-004-03 | 微型电机 | DC 3V Φ16mm | 1 | 外购 | 50元 |
| GIS-EE-004-04 | 齿轮减速组（电机→收带卷轴） | 塑料齿轮 | 1 | 外购 | 30元 |
| GIS-EE-004-05 | 弹性衬垫 | 硅橡胶Shore A 30, 20×15×5mm | 1 | 外购 | 15元 |
| GIS-EE-004-06 | 恒力弹簧（供带侧张力） | SUS301, 0.3N | 1 | 外购 | 10元 |
| GIS-EE-004-07 | 光电编码器（带面余量） | 反射式 | 1 | 外购 | 25元 |
| GIS-EE-004-08 | 溶剂储罐（活塞式正压密封） | Φ25×110mm，M8快拆接口 | 1 | 外购 | 150元 |
| GIS-EE-004-09 | 微量泵（溶剂喷射） | 电磁阀式 | 1 | 外购 | 80元 |
| GIS-EE-004-10 | 配重块 | 钨合金Φ14×13mm/120g | 1 | 外购 | 400元 |
| GIS-EE-004-11 | 微型轴承 | MR105ZZ（Φ10×Φ5×4mm） | 4 | 外购 | 32元 |
| GIS-EE-004-12 | 清洁窗口翻盖 | 硅橡胶一体成型 | 1 | 自制 | 20元 |
| GIS-EE-004-13 | LEMO插头 | FGG.0B.307 | 1 | 外购 | 150元 |
| **GIS-EE-005** | **工位4 UHF模块（方案A）** | — | 1 | 总成 | — |
| GIS-EE-005-01 | I300-UHF-GT传感器 | 波译科技 | 1 | 外购 | 6000元 |
| GIS-EE-005-02 | UHF安装支架 | 7075-T6铝合金 | 1 | 自制 | 300元 |
| GIS-EE-005-03 | LEMO插头 | FGG.0B.307 | 1 | 外购 | 150元 |
| **GIS-EE-006** | **信号调理模块** | — | 1 | 总成 | — |
| GIS-EE-006-01 | 壳体（含散热鳍片） | 6063铝合金 140×100×55mm | 1 | 自制 | 1500元 |
| GIS-EE-006-02 | 信号调理PCB | 定制4层混合信号 | 1 | 外购 | 8000元 |
| GIS-EE-006-03 | 安装支架（抱箍+L型） | 不锈钢 | 1 | 自制 | 300元 |
| GIS-EE-006-04 | LEMO插座 | EGG.0B.307 | 4 | 外购 | 600元 |
| GIS-EE-006-05 | SMA穿壁连接器 | 50Ω | 2 | 外购 | 100元 |
| GIS-EE-006-06 | M12防水诊断接口 | 4芯 | 1 | 外购 | 80元 |

> 合计: 48零件 / 6总成 / 11自制 / 37外购 / ¥60,922

## 6. 装配姿态与定位

### 6.1 坐标系定义

| 术语 | 定义 | 等价表述 |
| --- | --- | --- |
| **法兰正面**（工位侧） | 安装PEEK环和四工位模块的一面 | 朝向GIS壳体 |
| **法兰背面**（机械臂侧） | 安装ISO 9409适配板、电机+减速器的一面 | 朝向RM65-B机械臂末端 |
| **悬臂径向外侧** | 悬臂末端安装面（远离旋转中心的一端） | 朝向工位模块 |
| **悬臂径向内侧** | 悬臂根部（靠近法兰圆盘的一端） | 朝向法兰中心 |
| **旋转轴方向** | 垂直方向（平行于重力） | Z轴 |
| **法兰盘平面** | 水平面（像桌面） | XY平面 |
| **"上方" (+Z)** | 机械臂侧（适配板+电机所在侧） | arm-side / top |
| **"下方" (-Z)** | GIS壳体侧（工位模块悬挂侧） | workstation-side / bottom |
| **"径向外"** | 从法兰中心到悬臂末端（在XY平面内） | radially outward in flange plane |

### 6.2 装配层叠

| 层级 | 零件/模块 | 固定/运动 | 连接方式 | 偏移(Z/R/θ) | 轴线方向 | 排除 |
| --- | --- | --- | --- | --- | --- | --- |
| L1 | ISO 9409适配板 (GIS-EE-001-08) | 固定(机械臂) | 4×M6@PCD50mm, 9.0Nm | 基准原点 | 盘面∥XY |  |
| L2 | ECX 22L电机+GP22C减速器 | 固定(适配板) | 4×M3, 0.7Nm | Z=+73mm(向上) | 轴沿Z |  |
| L2 | Igus E2拖链段 | 固定端→适配板,活动端→法兰 | 2×M2 L形支架 | 径向R≈45mm | 弧形∥XY |  |
| L3 | 法兰本体 Φ90mm (GIS-EE-001-01) | 旋转(90°×4) | 过盈配合Φ8 H7/k6 + M4压紧 | Z=0(参考面) | 盘面∥XY |  |
| L3 | 弹簧销×4 (GIS-EE-001-07) | 固定(减速器壳体侧) | Φ4×20mm锥形头 | — | 轴沿Z |  |
| L4 | O型圈 FKM Φ80×2.4 | 随法兰旋转 | 嵌入密封槽 | Z=-25mm(向下) | 环∥XY |  |
| L4 | PEEK绝缘环 Φ86mm (GIS-EE-001-02) | 随法兰旋转 | 6×M3+碟簧垫圈 | Z=-27mm(向下) | 盘面∥XY |  |
| L5a | 涂抹工位(0°) (GIS-EE-002) | 随法兰旋转 | 4×M3+Φ3销, 0.7Nm | R=65mm, θ=0° | **壳体轴沿-Z（垂直向下），储罐轴∥XY（水平径向外伸）** |  |
| L5b | AE检测工位(90°) (GIS-EE-003) | 随法兰旋转 | 4×M3+Φ3销, 0.7Nm | R=65mm, θ=90° | **串联堆叠轴沿-Z（垂直向下），弹簧轴⊥法兰面** |  |
| L5c | 卷带清洁工位(180°) (GIS-EE-004) | 随法兰旋转 | 4×M3+Φ3销, 0.7Nm | R=65mm, θ=180° | **壳体轴沿-Z（垂直向下），溶剂罐轴沿-Z（垂直）** |  |
| L5d | UHF检测工位(270°) (GIS-EE-005) | 随法兰旋转 | 4×M3+Φ3销, 0.7Nm | R=65mm, θ=270° | **L支架挂载沿-Z（垂直向下）** |  |
| 尺寸标注+螺栓孔位 | 全部 |  |  |  |  |  |
|  | 信号调理模块 (GIS-EE-006) |  |  |  |  | exclude |

### 6.3 零件级定位

#### GIS-EE-003 工位2 AE检测模块

| 料号 | 零件名 | 模式 | 高度(mm) | 底面Z(mm) | 来源 | 置信度 |
| --- | --- | --- | --- | --- | --- | --- |
| GIS-EE-003-02 | 六轴力传感器 | axial_stack | 20.0 | -20.0 | serial_chain | high |
| GIS-EE-003-03 | 弹簧限力机构总成 | axial_stack | 16.0 | -36.0 | serial_chain | high |
| GIS-EE-003-04 | 柔性关节（万向节） | axial_stack | 15.0 | -51.0 | serial_chain | high |
| GIS-EE-003-05 | 阻尼垫 | axial_stack | 20.0 | -71.0 | serial_chain | high |
| GIS-EE-003-01 | AE传感器 | axial_stack | 26.0 | -97.0 | serial_chain | high |

### 6.4 零件包络尺寸

> 说明 / Legend
> - **来源** `P1:...` = 参数表 | `P2:walker:tier0` = 历史 part_no 上下文扫描 (回归保护)
> - **来源** `P2:walker:tier1` = 结构编号精确匹配 | `tier2` = 字符/单词子序列 | `tier3` = Jaccard 相似度
> - **置信度**: tier0/tier1 = 1.00 (精确); tier2 = 0.85 (高); tier3 = 原始 Jaccard 分数. <0.75 建议人工验证.
> - **粒度**: `station_constraint` = 工位级外包络 (模块必须装入); `part_envelope` = 单件本体尺寸.
>   **禁止**使用 `station_constraint` 尺寸作为单个采购件的建模尺寸.

| 料号 | 零件名 | 类型 | 尺寸(mm) | 来源 | 轴向标签 | 置信度 | 粒度 | 理由 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GIS-EE-001-01 | 法兰本体（含十字悬臂） | cylinder | Φ90.0×25.0 | P4:visual | — | — | — | — |  |
| GIS-EE-001-02 | PEEK绝缘段 | cylinder | Φ86.0×5.0 | P4:visual | — | — | — | — |  |
| GIS-EE-001-03 | O型圈 | cylinder | Φ80.0×2.4 | P3:BOM | — | — | — | — |  |
| GIS-EE-001-07 | 弹簧销组件（含弹簧） | cylinder | Φ4.0×20.0 | P3:BOM+template | — | — | part_envelope | spring_pin_assembly | 锥形头弹簧销半参数模型 |
| GIS-EE-001-08 | ISO 9409适配板 | cylinder | Φ63.0×8.0 | P4:visual | — | — | — | — |  |
| GIS-EE-001-09 | FFC线束总成 | box | 12.0×50.0×1.0 | P3:BOM+template | — | — | part_envelope | ffc_ribbon visual stub | 实际长度500mm，建模显示段限长50mm |
| GIS-EE-001-12 | 定位销 | disc | Φ3.0×5 | P1:part_table | — | — | — | — |  |
| GIS-EE-002 | 工位1涂抹模块 | box | ×× | P2:walker:tier1 | 宽×深×高，含储罐延伸 | 1.00 | station_constraint | tier1_unique_match |  |
| GIS-EE-002-01 | 涂抹模块壳体 | cylinder | Φ50.0×60.0 | P6:guess_geometry | — | — | — | — |  |
| GIS-EE-002-02 | 储罐 | cylinder | Φ38.0×280.0 | P3:BOM | — | — | — | — |  |
| GIS-EE-002-04 | 刮涂头 | box | 20.0×10.0×8.0 | P4:visual | — | — | part_envelope | scraper_head | 涂抹模块底端硅橡胶刮涂头 |
| GIS-EE-003 | 工位2 AE检测模块 | cylinder | Φ45.0× | P2:walker:tier1 | 含弹簧限力+柔性关节+AE探头串联 | 1.00 | station_constraint | tier1_unique_match |  |
| GIS-EE-003-01 | AE传感器 | cylinder | Φ20.0×26.0 | P5:chain_span | — | — | — | — |  |
| GIS-EE-003-02 | 六轴力传感器 | cylinder | Φ20.0×20.0 | P5:chain_span | — | — | — | — |  |
| GIS-EE-003-03 | 弹簧限力机构总成 | cylinder | Φ20.0×16.0 | P5:chain_span | — | — | part_envelope | spring_limit_mechanism | AE串联弹簧机构单件包络 |
| GIS-EE-003-04 | 柔性关节（万向节） | cylinder | Φ20.0×15.0 | P4:visual | — | — | part_envelope | rubber_universal_joint | AE串联柔性关节单件包络 |
| GIS-EE-003-05 | 阻尼垫 | cylinder | Φ20.0×20.0 | P5:chain_span | — | — | — | — |  |
| GIS-EE-003-07 | 配重块 | cylinder | Φ12.0×7.0 | P3:BOM | — | — | — | — |  |
| GIS-EE-004 | 工位3卷带清洁模块 | box | ×× | P2:walker:tier1 | 切向宽×径向深×轴向高，双卷轴区域 | 1.00 | station_constraint | tier1_unique_match |  |
| GIS-EE-004-01 | 清洁模块壳体（含卷轴腔+清洁窗口） | cylinder | Φ50.0×60.0 | P6:guess_geometry | — | — | — | — |  |
| GIS-EE-004-03 | 微型电机 | cylinder | Φ16.0×30.0 | P3:BOM+template | — | — | part_envelope | mini_dc_motor | 轴伸收敛在本体包络内 |
| GIS-EE-004-04 | 齿轮减速组（电机→收带卷轴） | box | 25.0×25.0×35.0 | P7:JINJA_TEMPLATE | — | — | part_envelope | gear_train_reducer | 半参数齿轮箱包络 |
| GIS-EE-004-05 | 弹性衬垫 | box | 20.0×15.0×5.0 | P3:BOM | — | — | — | — |  |
| GIS-EE-004-06 | 恒力弹簧（供带侧张力） | cylinder | Φ10.0×0.85 | P7:JINJA_TEMPLATE | — | — | part_envelope | constant_force_spring | 平面卷簧可视化包络 |
| GIS-EE-004-07 | 光电编码器（带面余量） | box | 15.0×15.0×12.0 | P7:JINJA_TEMPLATE | — | — | part_envelope | photoelectric_encoder | 反射式传感器半参数包络 |
| GIS-EE-004-08 | 溶剂储罐（活塞式正压密封） | cylinder | Φ25.0×110.0 | P3:BOM | — | — | — | — |  |
| GIS-EE-004-10 | 配重块 | cylinder | Φ14.0×13.0 | P3:BOM | — | — | — | — |  |
| GIS-EE-004-11 | 微型轴承 | ring | Φ10.0×4.0 | P3:BOM | — | — | — | — |  |
| GIS-EE-004-12 | 清洁窗口翻盖 | cylinder | Φ40.0×20.0 | P6:guess_geometry | — | — | — | — |  |
| GIS-EE-005 | 工位4 UHF模块（方案A） | cylinder | Φ50.0× | P2:walker:tier1 | 含安装支架 | 1.00 | station_constraint | tier1_unique_match |  |
| GIS-EE-005-01 | I300-UHF-GT传感器 | cylinder | Φ45.0×60.0 | P4:visual | — | — | — | — |  |
| GIS-EE-005-02 | UHF安装支架 | box | 50.0×50.0×25.0 | P6:guess_geometry | — | — | — | — |  |
| GIS-EE-006-01 | 壳体（含散热鳍片） | box | 140.0×100.0×55.0 | P3:BOM | — | — | — | — |  |
| GIS-EE-006-03 | 安装支架（抱箍+L型） | box | 50.0×50.0×25.0 | P6:guess_geometry | — | — | — | — |  |

## 7. 视觉标识

| 零件 | 材质 | 表面颜色 | 唯一标签 | 外形尺寸 | 方向约束 |
| --- | --- | --- | --- | --- | --- |
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

## 8. 渲染规划

### 8.1 迭代分组

| 步骤 | 添加内容 | 画面位置 | prompt要点 | 依赖步骤 |
| --- | --- | --- | --- | --- |
| 1 | 法兰本体安装O型圈（Φ80×2.4mm FKM），涂硅脂润滑 |  |  |  |
| 2 | PEEK段嵌入法兰本体台阶止口 |  |  |  |
| 3 | PEEK段螺栓固定（6×M3+碟形弹簧垫圈） |  |  |  |
| 4 | 安装减速器GP22C至法兰背面（4×M3） |  |  |  |
| 5 | 电机ECX 22L连接减速器 |  |  |  |
| 6 | 弹簧销组件安装至减速器输出端 |  |  |  |
| 7 | 法兰本体连接ISO 9409适配板（4×M6） |  |  |  |
| 8 | **FFC预布置**：FFC穿过Igus拖链段，两端ZIF连接器不锁定 |  |  |  |
| 9 | **独立线缆预布置**：AE同轴+UHF线缆+力传感器EtherCAT从法兰背面引出 |  |  |  |
| 10 | 安装工位1（涂抹模块）：定位销对齐→4×M3→LEMO插头 |  |  |  |
| 11 | 安装工位2（AE模块）：定位销对齐→4×M3→LEMO插头→AE同轴连接 |  |  |  |
| 12 | 安装工位3（卷带清洁模块）：定位销对齐→4×M3→LEMO插头→装入清洁带盒→确认U形带路就位→溶剂储罐旋入M8接口→确认翻盖弹簧回位 |  |  |  |
| 13 | 安装工位4（UHF模块）：定位销对齐→4×M3→LEMO插头→UHF线缆连接 |  |  |  |
| 14 | **FFC锁定**：法兰侧和模块侧ZIF锁扣压下→安装防护盖（2×M3） |  |  |  |
| 15 | **功能测试**：通电→法兰旋转4个工位→弹簧销锁定确认→各工位LEMO通信确认→**清洁模块专项**：电机驱动带推进5mm确认+泵喷射1次确认+编码器读数变化确认 |  |  |  |
| 1 | 主体框架：法兰+PEEK环+电机减速器+适配板+拖链 | 全画面中心 | cross-shaped dark gray disc, golden amber ring, 空悬臂末端螺栓孔可见 | — |
| 2 | 涂抹工位(0°)：壳体+储液罐+刮涂头 | 画面左下前景 | LONG horizontal silver tank (280mm, LONGEST part), tan brush tip at bottom | 1 |
| 3 | AE工位(90°)：力传感器+弹簧限力+万向节+AE探头 | 画面右下前景 | serial stack with visible coil spring (~6 turns), 从悬臂向下串联 | 1 |
| 4 | 清洁工位(180°)：壳体+溶剂罐+清洁带盒 | 画面右后(部分遮挡) | SHORT vertical silver tank (110mm, much shorter than reservoir), cleaner box | 1 |
| 5 | UHF工位(270°)：L支架+传感器 | 画面左后(部分遮挡) | L-bracket with cylindrical sensor, gold SMA connector visible | 1 |

### 8.2 视角

| 视角ID | 名称 | 仰角/方位 | 可见模块 | 被遮挡模块 | 重点 |
| --- | --- | --- | --- | --- | --- |
| V1 | 前左等轴测 | 30°/45° | 涂抹(0°)+AE(90°)+PEEK环+拖链+法兰正面 | 清洁(180°部分)+UHF(270°部分)+电机(适配板后) | 全貌+工位分布+PEEK色带 |
| V2 | 后右俯视 | 40°/225° | 电机+减速器+清洁(180°)+UHF(270°)+拖链+适配板 | 涂抹(0°部分)+AE(90°部分) | 驱动结构+背面布局 |
| V3 | 纯侧视 | 0°/90° | AE串联堆叠+UHF支架+法兰层叠(Al+PEEK) | 涂抹+清洁(正交方向) | 层叠结构+弹簧限力 |
| V4 | 爆炸图 | 30°/45° | 全部零件(分离) | 无 | 装配层级L1→L5 |
| V5 | 三视图 | 正投影 | 全部 | 无(虚线表示) | 尺寸标注+螺栓孔位 |

### 8.3 否定约束

| 约束ID | 约束描述 | 原因 |
| --- | --- | --- |
| 法兰本体 | 十字中心对称 |  |
| PEEK绝缘环 | slightly smaller than flange |  |
| ISO 9409适配板 | ONLY on arm-side |  |
| 电机+减速器 | ONLY on arm-side, NEVER on workstation side |  |
| 储液罐 | 轴线∥XY平面（∥法兰面），沿径向外伸，⊥旋转轴Z |  |
| 溶剂罐 | 轴线沿-Z（∥旋转轴），⊥法兰面 |  |
| 涂抹模块壳体 | 壳体从悬臂末端沿-Z垂直向下悬挂 |  |
| AE串联堆叠 | 轴线沿-Z(⊥法兰面)，从悬臂末端垂直向下悬挂，NEVER水平 |  |
| 弹簧限力机构 | 轴线沿-Z(⊥法兰面)，与AE堆叠同轴，NEVER∥法兰面 |  |
| 清洁模块壳体 | 壳体从悬臂末端沿-Z垂直向下悬挂 |  |
| UHF支架 | L形，传感器夹持 |  |
| UHF传感器 | 夹持于L支架 |  |
| 拖链 | 沿法兰边缘弧形 |  |
| 刮涂头 | 涂抹模块底端 |  |
| 柔性关节 | AE串联底端 |  |
| N1 | 法兰中心孔是空的（Φ22mm通孔），无任何机构从法兰中心向工位侧伸出；减速器输出轴在内部不可见 | AI倾向在空位补零件 |
| N2 | 电机+减速器(Φ22×73mm深灰圆柱)仅在臂侧(法兰上方)，绝不在工位侧(法兰下方) | 方向歧义导致电机画反 |
| N3 | LONG储液罐(Φ38×280mm)始终水平沿悬臂轴向延伸；SHORT溶剂罐(Φ25×110mm)始终垂直平行于模块高度 | 两个银色圆柱易混淆 |
| N4 | 不要发明设计文档中未描述的零件或连接件 | AI创造性补全倾向 |
| N5 | 信号调理模块(GIS-EE-006)不在法兰上，安装在机械臂J3-J4连杆上，距法兰250mm，渲染末端执行器时不画此模块 | 位置容易搞错 |
| N6 | PEEK环(Φ86mm)略小于法兰(Φ90mm)，厚度仅5mm，是琥珀金色薄环而非大圆盘 | AI容易画成与法兰等大 |
| N7 | 四个工位模块安装在悬臂末端(R=65mm)，不在法兰圆盘表面上 | AI容易把模块画在盘面上 |
| N8 | 法兰圆盘是**水平的**（像桌面），不是竖直的轮子；Z轴垂直向上，法兰面∥XY平面 | AI默认竖直展示圆盘 |
| N9 | AE弹簧限力机构的轴线始终⊥法兰面（沿-Z），NEVER与法兰面平行（NEVER水平） | V1渲染曾画反弹簧方向 |
| N10 | 所有四个工位模块从法兰悬臂末端沿-Z方向垂直向下悬挂，不向侧面水平伸出 | AI容易把模块画成径向水平 |

## 9. 装配约束

### 9.1 装配排除

| 零件/模块 | 原因 |
| --- | --- |
| 信号调理模块 (GIS-EE-006) | 信号调理模块(GIS-EE-006)不在法兰上，安装在机械臂J3-J4连杆上，距法兰250mm，渲染末端执行器时不画此模块 |

### 9.2 约束声明（自动生成草稿）

| 约束ID | 类型 | 零件A | 零件B | 参数 | 来源 | 置信度 |
| --- | --- | --- | --- | --- | --- | --- |
| C01 | contact | GIS-EE-001 | RM65-B（ISO 9409） | gap=0, bolt=M6×12 内六角 12.9级 | §3 紧固件 M6×12 内六角 12.9级 | high |
| C02 | contact | GIS-EE-001-02 | GIS-EE-001-01 | gap=0, bolt=M3×10 内六角 A2-70不锈钢 | §3 紧固件 M3×10 内六角 A2-70不锈钢 | high |
| C03 | contact | GIS-EE-002 | GIS-EE-001-01 | gap=0, bolt=M3×8 内六角 A2-70不锈钢 | §3 紧固件 M3×8 内六角 A2-70不锈钢 | high |
| C04 | contact | GIS-EE-001-06 | GIS-EE-001 | gap=0, bolt=M3×6 内六角 A2-70不锈钢 | §3 紧固件 M3×6 内六角 A2-70不锈钢 | high |
| C05 | contact | GIS-EE-006 | 臂连杆 | gap=0, bolt=M4×10 内六角 A2-70不锈钢 | §3 紧固件 M4×10 内六角 A2-70不锈钢 | high |
| C06 | contact | GIS-EE-003-02 | 悬臂安装面 | gap=0, bolt=M3×6 内六角 A2-70不锈钢 | §3 紧固件 M3×6 内六角 A2-70不锈钢 | high |
| C07 | stack_on | ECX 22L电机+GP22C减速器 | GIS-EE-001-08 |  | §6.2 LL1→LL2 | medium |
| C08 | stack_on | GIS-EE-001-11 | ECX 22L电机+GP22C减速器 |  | §6.2 LL2→LL2 | medium |
| C09 | stack_on | GIS-EE-001-01 | GIS-EE-001-11 |  | §6.2 LL2→LL3 | medium |
| C10 | stack_on | GIS-EE-001-07 | GIS-EE-001-01 |  | §6.2 LL3→LL3 | medium |
| C11 | stack_on | GIS-EE-001-03 | GIS-EE-001-07 |  | §6.2 LL3→LL4 | medium |
| C12 | stack_on | GIS-EE-001-02 | GIS-EE-001-03 |  | §6.2 LL4→LL4 | medium |
| C13 | stack_on | 全部 | GIS-EE-005 |  | §6.2 LL5d→L尺寸标注+螺栓孔位 | medium |
| C14 | stack_on | GIS-EE-006 | 全部 |  | §6.2 L尺寸标注+螺栓孔位→L | medium |
| C15 | exclude_stack | GIS-EE-001-09 |  | type=connector | §5 BOM category=connector | high |
| C16 | exclude_stack | GIS-EE-001-10 |  | type=connector | §5 BOM category=connector | high |
| C17 | exclude_stack | GIS-EE-001-11 |  | type=cable | §5 BOM category=cable | high |
| C18 | exclude_stack | GIS-EE-002-05 |  | type=connector | §5 BOM category=connector | high |
| C19 | exclude_stack | GIS-EE-003-08 |  | type=connector | §5 BOM category=connector | high |
| C20 | exclude_stack | GIS-EE-003-09 |  | type=cable | §5 BOM category=cable | high |
| C21 | exclude_stack | GIS-EE-004-13 |  | type=connector | §5 BOM category=connector | high |
| C22 | exclude_stack | GIS-EE-005-03 |  | type=connector | §5 BOM category=connector | high |
| C23 | exclude_stack | GIS-EE-006-04 |  | type=connector | §5 BOM category=connector | high |
| C24 | exclude_stack | GIS-EE-006-05 |  | type=connector | §5 BOM category=connector | high |
| C25 | horizontal | 储液罐 |  | axis=radial | §7 方向约束: 轴线∥XY平面（∥法兰面），沿径向外伸，⊥旋转轴Z | high |
| C26 | horizontal | AE串联堆叠 |  | axis=radial | §7 方向约束: 轴线沿-Z(⊥法兰面)，从悬臂末端垂直向下悬挂，NEVER水平 | high |
| C27 | coaxial | 弹簧限力机构 |  | axis=Z | §7: 轴线沿-Z(⊥法兰面)，与AE堆叠同轴，NEVER∥法兰面 | medium |

## 10. 缺失数据报告

| 编号 | 章节 | 缺失项 | 严重度 | 建议默认值 | 说明 |
| --- | --- | --- | --- | --- | --- |
| M01 | §1 全局参数表 | 缺少重量预算参数 | WARNING | 由BOM计算派生 | 在参数表中添加 '总重量' 行 |
