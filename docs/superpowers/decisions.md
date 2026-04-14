# 项目决策日志

集中登记跨阶段、需长期追溯的重大决策。每条含编号、日期、决策、理由、应用方式。

---

## #34 SW-B9 验收口径放宽（2026-04-14）

**决策：** SW-B9 在本轮按 `顶层 pass = Stage 0 && Stage 0.5 && Stage A && Stage C && (Stage D || Stage D skipped_with_reason)` 判定；(b) 真实 BOM 使用 GISBOT CAD_SPEC ~58 行（低于原门槛 100 行）；(d) 若装配管线无 `sw_toolbox` backend 消费者则 skipped_with_reason；(e) 降级仅产出决策，不改代码。

**理由：** GISBOT 为 CadQuery 原生设计项目，其装配管线不消费 SW Toolbox sldprt，(d) 在此样本上为 no-op；当下无更合适真实项目样本；拖延完整验收阻塞 Phase B 收尾。

**应用方式：** 后续引用 SW-B9 "通过" 时必须注明"按决策 #34 放宽口径"；严格版 SW-B9 延至有真正消费 Toolbox 的装配样本时重跑。
