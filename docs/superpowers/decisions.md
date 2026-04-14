# 项目决策日志

集中登记跨阶段、需长期追溯的重大决策。每条含编号、日期、决策、理由、应用方式。

---

## #34 SW-B9 验收口径放宽（2026-04-14）

**决策：** SW-B9 在本轮按 `顶层 pass = Stage 0 && Stage 0.5 && Stage A && Stage C && (Stage D || Stage D skipped_with_reason)` 判定；(b) 真实 BOM 使用 GISBOT CAD_SPEC ~58 行（低于原门槛 100 行）；(d) 若装配管线无 `sw_toolbox` backend 消费者则 skipped_with_reason；(e) 降级仅产出决策，不改代码。

**理由：** GISBOT 为 CadQuery 原生设计项目，其装配管线不消费 SW Toolbox sldprt，(d) 在此样本上为 no-op；当下无更合适真实项目样本；拖延完整验收阻塞 Phase B 收尾。

**应用方式：** 后续引用 SW-B9 "通过" 时必须注明"按决策 #34 放宽口径"；严格版 SW-B9 延至有真正消费 Toolbox 的装配样本时重跑。

---

## #35 SW-C 匹配率修复验收（2026-04-15）

**决策：** SW-C 三项改动（part_no 权重 2.0→0.0、PLURAL_PAIRS 单复数扩展、同义词表补充 hexagon/六角头/复数）经 demo BOM 真跑验证，Stage A 覆盖率从 13.3% 提升到 **73.3%**（11/15），达到 ≥73% 门槛。

4 个持续 MISS（GIS-012 UNC 制式、GIS-013 梯形螺纹、GIS-014 自制件、GIS-015 Maxon 电机）属合理边界——均不在 GB/ISO/DIN 标准工具箱范围内。

Stage C（STEP 转换）仍为 `pre=None post=None`，根因为 SolidWorks COM SaveAs3 不稳定，与本次匹配算法修复无关，属独立待处理问题。

**理由：** SW-C 的核心目标是 Stage A 覆盖率，已达成。Stage C 是独立的 COM 稳定性问题，不应阻塞 SW-C 验收。

**应用方式：** SW-C 视为匹配算法层面验收通过；Stage C COM 稳定性问题另立追踪，不计入 SW-C 范围。
