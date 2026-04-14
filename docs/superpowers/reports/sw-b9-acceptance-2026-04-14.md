# SW-B9 真跑验收报告 — 2026-04-14

## 顶层结论

- SW-B9 状态: **FAIL**（按决策 #34 放宽口径判定）
- Stage D 是否 skipped: False
- 触发 ROI 熔断降级: True

## Stage 汇总表

| Stage | 目标 | 实测 | Pass |
| --- | --- | --- | --- |
| 0 preflight | toolbox 探测 + index 构建 | index=1844 | True |
| 0.5 token 健康 | cn_hit_rate > 0 | 0.8666666666666667 | True |
| A demo 覆盖率 | ≥ 73% | 0.13333333333333333 | False |
| B GISBOT 覆盖率 | informational | 0.0 | informational |
| C session 重启 | 前5 后3 STEP 合法 | pre=None post=None | False |
| D 装配回归 | after ≥ before | True | True |
| E ROI 熔断 | coverage ≥ 55% | 0.0 → downgrade_gb_only | informational |

## 样本不足声明（决策 B1 / 决策 #34）

真实 BOM 样本为 GISBOT 58 行，低于 ≥100 行门槛。
GISBOT 为 CadQuery 原生设计项目，不消费 SW Toolbox sldprt，Stage D 在此样本下 skipped。
严格版 SW-B9 延至有合适样本时重跑（见 decisions.md #34）。

## 详细数据

- preflight.json: toolbox=C:\SolidWorks Data\browser, min_score=0.3
- stage_a.json: unmatched=['GIS-DEMO-001', 'GIS-DEMO-003', 'GIS-DEMO-004', 'GIS-DEMO-005', 'GIS-DEMO-006', 'GIS-DEMO-008', 'GIS-DEMO-009', 'GIS-DEMO-010', 'GIS-DEMO-011', 'GIS-DEMO-012', 'GIS-DEMO-013', 'GIS-DEMO-014', 'GIS-DEMO-015']
- stage_b.json: excluded=45 rows
- stage_c.json: restart_duration=Nones
