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

---

## #38 sw-inspect 作为正式深度诊断入口（2026-04-16）

- **决策**：`cad_pipeline.py sw-inspect [--deep] [--json]` 为 SW 诊断的**正式 CLI 入口**；
  `scripts/sw_spike_diagnose.py` 保留为 SW-B0 时期 REPL 友好的历史档案，内部薄壳调
  `adapters/solidworks/sw_probe.py` 共享内核。
- **退出码独立编号**：
  - sw-inspect：`0` 全绿 / `1` warn / `2` 静态 fail / `3` deep-COM fail / `4` deep-addin fail / `64` 参数错
  - sw_spike_diagnose：`0/1/2/3/4` 继承 SW-B0 时期历史语义不变
  - 两者不互通；CI 和脚本默认消费 sw-inspect 退出码
- **JSON schema v1 稳定字段**（消费方依赖）：
  `overall.exit_code` / `overall.elapsed_ms` / `layers.*.severity` /
  `layers.dispatch.data.elapsed_ms`（F-4a baseline 数据源）
- **F-1 follow-up**：F-1.1 deep 模式材质 XML 解析；F-1.2 subprocess 隔离 Dispatch 悬挂；
  F-1.3 Windows self-hosted runner 真跑 real smoke
- **Spec**：`docs/superpowers/specs/2026-04-16-sw-inspect-design.md`
- **Plan**：`docs/superpowers/plans/2026-04-16-sw-inspect.md`
- **已发现的问题（实施过程）**：probe_dispatch 在 ThreadPoolExecutor worker 线程缺 CoInitialize，
  真 SW smoke 暴露后追加 `_dispatch_and_probe_worker` 内嵌 `pythoncom.CoInitialize/Uninitialize`
  包装整个 COM 生命周期到同一 STA 线程（commit 91caf82）

---

## #39 sw-smoke workflow：long-lived self-hosted runner + 不在 PR 跑（2026-04-17）

**决策：** F-1.3 实现 `sw-smoke` workflow 运行在 self-hosted Windows runner
（labels: `self-hosted, windows, solidworks`），触发条件为 `push: main` +
`workflow_dispatch`，**不**监听 `pull_request`。

**关键取舍：**
- **C1 路径 vs 全量 PR 触发**：public repo 下 fork PR 会在 runner 机器上
  执行任意代码（GitHub 官方警告），不值得承担风险；main 合并 + 手动触发
  覆盖 F-1.3 目标
- **Long-lived runner vs ephemeral**（D4，v3 审查修正）：ephemeral 自动
  重注册需要持续有效的 PAT，PAT 存在受限 `ghrunner` 账户即等于给它日常
  GitHub 操作权，抵消了 ephemeral 的安全收益。改 long-lived + `git clean`
  + 90 天手动轮换 credential
- **非 Service 模式**：SW COM 需要交互式 GUI 会话；runner 装成 Service
  会触发 SW Dispatch 静默挂起。用 Task Scheduler `at-logon` + Autologon
  代替（见 runbook）
- **`cancel-in-progress: false`**（D7，v3 审查修正）：true 会在新 push 到
  来时硬杀正跑 job 吃掉 artifact；false 下离线积压靠 `gh run cancel` id
  循环清理

**决策生效前提：**
- 开发者拥有一台常可开机的 Windows + SolidWorks 2024+ 机器
- 在 12 个月内至少捕获 1 次真 SW 回归（K2）；若 K2 = 0 则评估降级到
  F-1.3e（本地跑 + runbook）

**Follow-up：**
- F-1.3a：artifact → dashboard（K1 达成时）
- F-1.3b：full=true input 追加 sw-warmup / Stage C
- F-1.3c：第二台 SW 机器 runner-group 负载均衡（license/可用性连续 14 天冲突时）
- F-1.3d：actionlint 加 pre-commit
- F-1.3e：runner 低在线率降级路径（K2 = 0 或月在线率 < 30%）
- F-1.3f：elapsed_ms 门槛调整（K3 flaky > 5%）
- F-1.3g：tests.yml 迁移到 setup-cad-env composite action
- F-1.3h：pre-seed fake_home 或 fixture override 恢复 toolbox_index 断言（T2 发现）
- F-1.3i：step summary 从第三次 live SW Dispatch 改为消费已有 JSON（T4 review 发现）

**Spec**：`docs/superpowers/specs/2026-04-17-sw-self-hosted-runner-design.md` (v3)
**Plan**：`docs/superpowers/plans/2026-04-17-sw-self-hosted-runner.md`

**修订历史：**
- v1 初稿（ephemeral + cancel-in-progress: true）
- v2 二审（artifact 数据流 + 依赖安装）
- v3 多角色审查（D4 → long-lived / D7 → cancel-in-progress: false；
  + D13/D14/D15/D16 新决策）
