# CAD Spec — 通信架构 (GIS-COM)
<!-- Generated: 2026-03-22 10:27 | Source: D:/GISBOT/docs/design/12-通信架构.md | Hash: 540caf2b12c2 -->

## 1. 全局参数表

| 参数名 | 值 | 单位 | 公差 | 来源 | 备注 |
| --- | --- | --- | --- | --- | --- |
| （暂无数据） | | | | | |

## 2. 公差与表面处理

### 2.1 尺寸公差

| 参数名 | 标称值 | 上偏差 | 下偏差 | 配合代号 | 标注文本 |
| --- | --- | --- | --- | --- | --- |
| （暂无数据） | | | | | |

### 2.2 形位公差

| 符号 | 值 | 基准 | 适用零件 |
| --- | --- | --- | --- |
| （暂无数据） | | | |

### 2.3 表面处理

| 零件 | Ra(µm) | 处理方式 | material_type |
| --- | --- | --- | --- |
| power_management_node | /power/*, /temperature/* |  |  |
| mission_planner_node | /pd_detection/result, /nav/status |  |  |

## 3. 紧固件清单

| 连接位置 | 螺栓规格 | 数量 | 力矩(Nm) | 材料等级 | 备注 |
| --- | --- | --- | --- | --- | --- |
| pd_detection_node | /pd_detection/result | 1 |  |  |  |
| force_control_node | /force/cmd | 1 |  |  |  |
| end_effector_node | /rotary_flange/cmd, /system_health | 1 |  |  |  |
| navigation_node | /cmd_vel, /nav/status | 1 |  |  |  |
| power_management_node | /battery/status, /consumable/status | 1 |  |  |  |
| mission_planner_node | /mission/current_point | 1 |  |  |  |
| 周期时间 | 1ms（1kHz） | 1 |  |  |  |
| 数据帧大小 | 6×32bit = 24B/周期 | 1 |  |  |  |
| 延迟 | <500µs（单从站） | 1 |  |  |  |
| 线缆 | 独立屏蔽双绞线（不经FFC） | 1 |  |  |  |
| 理论速率 | 1.2Gbps | 1 |  |  |  |
| 实际可用 | >100Mbps | 1 |  |  |  |
| 延迟 | <10ms | 1 |  |  |  |
| 加密 | WPA3-Enterprise | 1 |  |  |  |
| 用途 | 巡检数据批量上传、实时状态监控、固件更新 | 1 |  |  |  |
| robot/{id}/detection/result | 机器人→站端 | 1 |  |  |  |
| robot/{id}/command | 站端→机器人 | 1 |  |  |  |
| robot/{id}/ota | 站端→机器人 | 1 |  |  |  |
| station/{id}/charge/status | 站端→机器人 | 1 |  |  |  |
| 上行速率 | >100Mbps | 1 |  |  |  |
| 延迟 | <20ms | 1 |  |  |  |
| 月流量预算 | ~50GB | 1 |  |  |  |
| 用途 | 检测数据同步、远程运维、模型更新 | 1 |  |  |  |
| Detection.LastResult | 结构体 | 1 |  |  |  |
| Detection.AbnormalCount | Int | 1 |  |  |  |
| L2（机器人） | DDS Security（ROS 2 SROS2） | 1 |  |  |  |
| L3（WiFi） | WPA3-Enterprise + TLS 1.3 | 1 |  |  |  |
| L4（5G） | 运营商加密 + 应用层TLS | 1 |  |  |  |
| 数据存储 | AES-256-GCM | 1 |  |  |  |
| 身份认证 | X.509设备证书 | 1 |  |  |  |

## 4. 连接矩阵

| 零件A | 零件B | 连接类型 | 配合代号 | 预紧力矩 | 装配顺序 |
| --- | --- | --- | --- | --- | --- |
| HMAC-SHA256帧认证 | DDS Security（ROS 2 SROS2） |  |  |  | 1 |
| DDS Security（ROS 2 SROS2） | WPA3-Enterprise + TLS 1.3 |  |  |  | 2 |
| WPA3-Enterprise + TLS 1.3 | 运营商加密 + 应用层TLS | WPA3-Enterprise |  |  | 3 |
| 运营商加密 + 应用层TLS | AES-256-GCM | WPA3-Enterprise |  |  | 4 |
| AES-256-GCM | X.509设备证书 |  |  |  | 5 |

## 5. BOM树

（未找到BOM表）

## 6. 装配姿态与定位

### 6.1 坐标系定义

| 术语 | 定义 | 等价表述 |
| --- | --- | --- |
| （暂无数据） | | |

### 6.2 装配层叠

| 层级 | 零件/模块 | 固定/运动 | 连接方式 | 偏移(Z/R/θ) | 轴线方向 |
| --- | --- | --- | --- | --- | --- |
| L1（末端） | HMAC-SHA256帧认证 |  |  |  |  |
| L2（机器人） | DDS Security（ROS 2 SROS2） |  |  |  |  |
| L3（WiFi） | WPA3-Enterprise + TLS 1.3 |  |  |  |  |
| L4（5G） | 运营商加密 + 应用层TLS |  |  |  |  |
| 数据存储 | AES-256-GCM |  |  |  |  |
| 身份认证 | X.509设备证书 |  |  |  |  |

## 7. 视觉标识

| 零件 | 材质 | 表面颜色 | 唯一标签 | 外形尺寸 | 方向约束 |
| --- | --- | --- | --- | --- | --- |
| （暂无数据） | | | | | |

## 8. 渲染规划

### 8.1 迭代分组

| 步骤 | 添加内容 | 画面位置 | prompt要点 | 依赖步骤 |
| --- | --- | --- | --- | --- |
| （暂无数据） | | | | |

### 8.2 视角

| 视角ID | 名称 | 仰角/方位 | 可见模块 | 被遮挡模块 | 重点 |
| --- | --- | --- | --- | --- | --- |
| （暂无数据） | | | | | |

### 8.3 否定约束

| 约束ID | 约束描述 | 原因 |
| --- | --- | --- |
| （暂无数据） | | |

## 9. 缺失数据报告

| 编号 | 章节 | 缺失项 | 严重度 | 建议默认值 | 说明 |
| --- | --- | --- | --- | --- | --- |
| M01 | §1 全局参数表 | 尺寸参数不足5个 | CRITICAL | — | 请在设计文档中补充完整的参数表（至少含5个关键尺寸） |
| M02 | §1 全局参数表 | 缺少重量预算参数 | WARNING | 由BOM计算派生 | 在参数表中添加 '总重量' 行 |
| M03 | §1 全局参数表 | 缺少包络尺寸参数 | WARNING | — | 添加外径/宽/高/长等包络尺寸 |
| M04 | §5 BOM树 | 未找到BOM表 | CRITICAL | — | 请在 §X.8 添加BOM章节，模板: docs/templates/bom_section_template.md |
| M05 | §6 装配姿态与定位 | 缺少坐标系定义 | WARNING | 使用标准坐标系：Z=垂直向上, X=水平向右, Y=水平向前 | 在 §X.10.0 添加装配姿态定义表（术语|定义|等价表述） |
| M06 | §2 公差与表面处理 | 未提取到尺寸公差 | INFO | GB/T 1804-m | 在参数表中补充公差列，或添加独立公差表 |
| M07 | §7 视觉标识 | 缺少视觉标识表 | INFO | 从BOM生成骨架 | 在 §X.10.2 添加视觉标识表（零件|材质|颜色|唯一标签|尺寸|方向约束） |
| M08 | §8 渲染规划 | 缺少渲染规划数据 | INFO | 使用标准5视角方案 | 在 §X.10.3~5 添加迭代分组/视角/否定约束表 |
