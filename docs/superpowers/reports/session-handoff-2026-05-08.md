# Session Handoff — 2026-05-08

## 仓库当前状态

- **工作目录**：`D:\Work\cad-spec-gen`
- **当前分支**：`main`
- **HEAD**：`99c0e938` `feat(photo3d): 完成升降平台照片级交付 (#58)`
- **远端同步**：`origin/main` 与本地 `main` 一致
- **最新 tag**：**v2.26.0**（本 session 第二个 release）
- **OPEN PR**：无
- **整体进度**：约 **89%**

### 工作树清单

```
D:/Work/cad-spec-gen                                             99c0e93 [main]
D:/Work/cad-spec-gen/.worktrees/generic-threaded-photo-autopilot 4caf35f [codex/generic-threaded-photo-autopilot]
```

`.worktrees/product-goal-entry/` 已在 PR #59 merge 后清理。`.worktrees/generic-threaded-photo-autopilot/` 是历史 worktree，与本 session 无关。

### 工作树残留

- `.claude/settings.local.json` 本地配置文件，session 开头就 dirty，**非任何 PR scope**，保留不动
- `git stash list`：`stash@{0}: On codex/product-goal-entry: non-feature lifting_platform std_*.py side effects`——这是 session 中创建产品目标入口分支时 pytest codegen 副作用产生的 13 个 std_*.py 改动，**现在 PR #58 已 merge 自己的 std_*.py 版本进 main，此 stash 内容已过期**，建议下次 session 直接 `git stash drop` 丢弃

## 本 session 完成事项

### 同日两个 release

| Tag | PR | 主题 | 规模 |
|---|---|---|---|
| **v2.25.0** | #59 | Phase 1 入口前移到产品目标自然语言模式 | 4582 行 / 22 commits（spec rev 4 + plan + 17 实施 + 2 hotfix）/ 92 测试 |
| **v2.26.0** | #58 | 升降平台子系统照片级端到端交付 | 66375 行 / 1 squash commit / 14 测试文件改 |

### v2.25.0 PR #59 — 产品目标自然语言入口

**新模式**：`project-guide --product-goal "<自然语言>"`

**7 状态机**：
- `needs_product_goal` / `needs_subsystem_confirmation` / `not_yet_implemented` + alternatives / `unknown_subsystem` / `needs_kpi_confirmation` / **`needs_design_doc`**（rev 4 DR-1 死路修复）/ `ready_for_cad_spec`

**词典 + KPI**：
- 19 子系统：2 implemented（lifting_platform、end_effector）+ 17 not_yet_implemented
- 6 顶层 KPI：lifting=load_kg/stroke_mm/platform_size_mm；end_effector=rot_range_deg/switch_time_s/flange_dia_mm

**关键文件**：
- `tools/product_goal_parser.py` — 3 层确定性解析器（subsystem 识别 + KPI 抽取 + 歧义检测）
- `tools/project_guide_dict/` — JSON 词典（subsystem_keywords.json + kpi_patterns.json + dataclass 自校验加载器）
- `tools/project_guide.py` — 新增 `write_project_goal_guide` + `_derive_goal_status_and_next_action` + 配套 helpers
- `cad_pipeline.py` — 7 个 `--confirm-X` flag + dispatch fallback（rev 4 DR-3）+ `_collect_confirmed_kpis`

**spec 4 轮严格演进**（`docs/superpowers/specs/2026-05-07-product-goal-entry-design.md`）：
- rev 1 自审 → rev 2（4 角色对抗：机械/3D 建模/程序员/潜在用户）→ rev 3（实地 grep 代码核验，11 项漂移修复）→ rev 4（5 场景 dry-run，3 死路修复）

**plan 14 task / 5 checkpoint**（`docs/superpowers/plans/2026-05-07-product-goal-entry-plan.md`）

**附带价值**：顺手修了 main 既有 Windows CI 8.3 短路径 bug（`tests/test_pipeline.py::test_cmd_render_normalizes_relative_output_dir`），让所有未来 PR 的 Windows test matrix 重新可用。

### v2.26.0 PR #58 — 升降平台子系统端到端

**完整覆盖 Phase 2-6 五阶段**：
- Phase 2 CODEGEN：8 零件参数化 + `assembly.generated.py` + `LAYOUT_CONTRACT.json` + `PRODUCT_GRAPH.json` + 7 真实 vendor STEP 落 `user_provided/`
- Phase 3 BUILD：`std_c01-c08` / `std_f06`（新增）/ `std_f11/f12/f13` / `std_p01` 标准件改造
- Phase 4 RENDER：`render_3d.py` 同步 + `render_depth_only.py`（深度图）+ `render_label_utils.py`（标注）+ `render_config.json` 重构
- Phase 5 ENHANCE：`engineering_enhancer.py` + `enhance_consistency` 增强
- Phase 6 ANNOTATE/DELIVER：`photo3d_autopilot` / `photo3d_recover` / `model_contract` / `product_graph` 跨工具协同

**子系统进度**：从 1 个 implemented（end_effector）→ **2 个 implemented**（+ lifting_platform）

## 验证记录

| 命令 | 结果 |
|---|---|
| `gh pr checks 59` | 8/8 SUCCESS（含 Linux 3.10/3.11/3.12 + Windows 3.10/3.11/3.12 + mypy-strict + regression） |
| `gh pr checks 58` | 8/8 SUCCESS（merge main 拿 v2.25.0 fix 后） |
| `python -m pytest`（PR #59 范围） | 92 PASS / 0 fail |
| 全量 regression | 2470 PASS / 11 skipped / 0 failed |
| `python scripts/dev_sync.py --check` | PASS |
| ruff + mypy strict | clean |

## 后续工作队列（按优先级）

### 1. Phase 5：真实 AI backend adapter 准入（**最高优**）

`gpt-image-2-pro` 等云后端必须先做：
- 配置隔离（key 不落盘）
- 白名单 preset（参考既有 6 preset 模式）
- 同 run 验收
- 多视角一致性测试

当前白名单都是 mock 类 preset（`default` / `engineering` / `gemini` / `fal` / `fal_comfy` / `comfyui`），实际产线未真实使能云增强。

### 2. Phase 4 → 6：逐视角可见实例证据增强

- 契约层已能防"少件"，但只能 warning
- 需要让 manifest 携带每视角可见实例集合，把"图是否完整"从 warning 升到 blocked-able
- 影响：`render_visual_check` / `render_quality_check` / `enhance_check` / `enhance_review` / `photo3d_deliver` 5 个工具

### 3. Phase 6：最终交付报告可视化

- `delivery/README.md` 现在是 JSON 证据汇总
- 需补：缩略图 / 模型质量摘要可读化 / 语义复核状态 / 下一步动作建议
- 目标：普通用户直接看 README 就能签收

### 4. v2.25.x cleanup PR — §11 6 项 follow-up

- §11.I-1 unit_normalize 索引脆弱（按 dict 序对齐 regex 序，建议改 list of {pattern, factor}）
- §11.I-2 spec rev 4 line 286/316 软硬窗口语义矛盾（spec 内部矛盾，下次修订收敛）
- §11.I-3 evidence_token 用 NFKC 后字符串而非原文（audit 友好性）
- §11.I-4 `_derive_goal_status_and_next_action` 函数 80 行偏长（可拆 helper）
- §11.I-5 降级文案与 spec 模板 `\"等"` 字面差异
- §11.M-3 Windows Path 反斜杠在 preview_cli（已被 unsafe 降级路径兜住，但文案不区分中文 vs 反斜杠）

### 5. Phase 1 入口继续前移（v2.27+，外行用户体验深化）

- 当前 v2.25.0 仅识别 19 类 + 6 KPI
- 下一步：扩展到"产品目标 + 子系统类别 + 多 KPI 多轮渐进确认"——让外行不必一次说全
- 引入"项目向导记忆"：用户多次跑同一项目，guide 记住已确认的子系统/KPI

### 6. 新子系统开发（17 个 not_yet_implemented 选 1）

如果用户优先扩横向，可选：
- `navigation` — SLAM / 路径规划
- `motion_ctrl` — 伺服 / 电机控制
- `electrical` — 配电 / 线缆
- `power` — 电池 / 电源管理
- 其他 13 个

每个新子系统按 v2.26.0 升降平台模式：参数化 → 装配契约 → vendor STEP → 跨 Phase 测试。

## 下个 session 起手参考

### 必读文件（按顺序）

1. `docs/superpowers/reports/session-handoff-2026-05-08.md`（本文件）
2. `C:\Users\procheng\.claude\projects\D--Work-cad-spec-gen\memory\project_current_status.md`（memory 摘要）
3. `docs/PROGRESS.md`（项目看板）
4. `docs/superpowers/specs/2026-05-07-product-goal-entry-design.md`（v2.25.0 spec rev 4，含 §11 follow-up）

### 立即可做的动作

| 选项 | 动作 |
|---|---|
| A | 处理 stash@{0}（直接 `git stash drop` 清理过期 stash）|
| B | brainstorming Phase 5 真实 AI adapter 准入 |
| C | brainstorming v2.25.x cleanup PR（§11 6 项）|
| D | 选一个 not_yet_implemented 子系统开新分支（参考 lifting_platform 模式）|

### 工作流约束（项目 CLAUDE.md，强制）

- **TDD 铁律**：先写失败测试 → 跑红 → 实现 → 跑绿 → commit
- **superpowers 工作流**：brainstorming → write-plan → execute-plan → code-review
- **subagent-driven**：spec rev 4 + plan 14 task + 三层 review（implementer + spec + quality + final）模式可复用
- **中文输出 + 中文 commit message 描述**
- **dev_sync**：改 mirror 文件后跑 `python scripts/dev_sync.py && python scripts/dev_sync.py --check`
- **每轮收尾**：更新 `docs/PROGRESS.md` + 本 session-handoff 模式

## Memory 资产复用清单

下个 session 加载 memory 后即可使用：

- `project_north_star.md` — 北极星 5 gate（零配置/稳定可靠/准确/SW 装即用/傻瓜式）
- `user_windows_only_scope.md` — Windows-only 范围
- `user_simplicity_and_accuracy.md` — 用户要简单+准确不要技术细节
- `feedback_subagent_driven_main_agent_scouts.md` — 主 agent 前置 grep + subagent 精准执行
- `feedback_plan_drift_taxonomy.md` — 5 类 plan drift 防御
- `feedback_cp_batch_quality_review.md` — CP-末整体 review 替代 per-task review
- `feedback_subagent_complete_rewrite_drops_regression.md` — subagent 重写文件可能丢历史回归
- `feedback_external_subsystem_safety_valve.md` — 外部子系统接入安全阀
- `feedback_spec_review_4layers.md` — spec ≥100 行默认跑 4 层审查
- `project_current_status.md` — 当前进度（已更新到 v2.26.0）
