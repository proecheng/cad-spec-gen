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

---

## #36 SINGLE_CONVERT_TIMEOUT_SEC 30→20s（2026-04-16）

**决定**：`adapters/solidworks/sw_com_session.py` 的 `SINGLE_CONVERT_TIMEOUT_SEC` 从 30 下调为 20。`parts_library.default.yaml` 的声明同步更新；`docs/design/sw-com-session-threading-model.md` 线程模型文档同步。

**依据**：Part 2c P0 真 SW smoke（2026-04-14，5 件 GB sldprt 全部成功）subprocess 模型端到端均值 11.6s/件；20 / 11.6 = 1.72x 冗余。

**已知信息 gap**：Stage C 验收代码只记 `step_size` 不记 `elapsed_sec`，大件 outlier 耗时未测；5 件 smoke 无方差数据。

**兜底与回退**：
- **兜底**：熔断器（3 次连续失败 → `_unhealthy`）+ Stage C 可观测性（commit `0e8ddc7` 的 `last_convert_diagnostics`）+ resolver 回落链路（sw_toolbox → bd_warehouse → jinja_primitive）
- **回退通道**：Follow-up F-4a（临时把 timeout 放大到 120s 测真实 `elapsed_sec` 分布，避免 20s 下的上限截断陷阱）+ F-4b（`stage_c.json` 追加 `timeout_rate` 字段）+ F-7（基于 F-4a p95 和 F-4b 命中率同时决策是否回退 25s/30s）

**spec**: `docs/superpowers/specs/2026-04-16-part2c-p2-packaging-design.md`

---

## #37 pyproject.toml solidworks optional extra（2026-04-16）

**决定**：`pyproject.toml [project.optional-dependencies]` 新增 `solidworks = ['pywin32>=306; sys_platform == "win32"']`；`all` extra 不含 pywin32。

**依据**：消除"用户需手动装 pywin32"的 friction；`sys_platform` marker 让 Linux/macOS 上 extra 装成 no-op 而非 pip 硬 reject，与项目 `@requires_solidworks` marker 的"Linux 用户合法"态度一致。

**UX 闭环**：本决策依赖 3 处代码提示同步（`tools/sw_warmup.py:252` / `scripts/sw_spike_diagnose.py:44` / `tools/hybrid_render/check_env.py:286`），否则 extra 成"影子功能"无人使用。这 3 处同步本 plan 已一并完成（Task 6-8）。

**契约守门**：`tests/test_pyproject_contract.py::TestSolidworksExtra` 用 `packaging.requirements.Requirement` 解析并显式检查 operator、version、marker 三个字段，避免字符串 `==` 断言对 PEP 508 等价写法假阴性。

**spec**: `docs/superpowers/specs/2026-04-16-part2c-p2-packaging-design.md`
