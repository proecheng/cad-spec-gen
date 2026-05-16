# v2.37.11 — ruff cleanup P1（safe `--fix` 4 类清零）设计

> **PR 类型**：chore（pure cleanup，零语义改动，~1-2h）
> **关联 STATUS doc**：暂无独立 STATUS（首批 cleanup，P3 落 `[tool.ruff]` 锁时再开 status doc 跟踪 3 批联动）
> **关联 v2.37.10 retro**：`docs/superpowers/reports/2026-05-16-v2-37-10-rebrand-path-real-retry-retro.md`（"360+ ruff cleanup" follow-up 出处）
> **Spec rev**：rev 2（rev 1 用户审查抓 1 BLOCKER + 2 MINOR cascade — F401 默认 `--fix` 真值校准 + noqa 估测真值化 + Task 0 unsafe-fixes scout 补强；rev 2 inline fix 三项后再 self-review）
> **3 批 cleanup 拓扑**：3 独立 spec + 3 plan（贴项目惯例）；本 spec 仅覆盖 P1，P2/P3 各自 brainstorming

---

## 1. 摘要

清掉 ruff 421 errors 里 **F401 + F541 + F811 + E401 共 154 条**；ruff `--fix` 走双步法（**default 149 + `--unsafe-fixes` 多修 3**）；剩 **2 条**（即使 `--unsafe-fixes` 也修不了）逐条加 `# noqa: <code>  # <5-15 字中文>` 注释；P1 完结时 `ruff check --select=F401,F541,F811,E401 .` exit 0。

> **rev 2 真值脚注**：rev 1 笼统称"154 条 safe `--fix`"漂移于 ruff 实际行为。真值分解 — F401 128 条 ruff statistics 标记 `[-]`（hidden fix，需 `--unsafe-fixes`）/ F541+F811+E401 = 26 条标记 `[*]`（safe auto-fix）；实跑 `--fix --select=F401,F541,F811,E401 .` default 修 149 条 / 加 `--unsafe-fixes` 再修 3 条 / 剩 2 条 ruff 不可修（候选 noqa）。Task 0 scout 实跑校准这些数字。

| 改动 | 严重度 | 内容 | 工作量 |
| --- | --- | --- | --- |
| **改动 1a** | LOW | `ruff check --fix --select=F401,F541,F811,E401 .` default 一键产物（149 条 auto-fix）| ~10min |
| **改动 1b** | LOW | `ruff check --fix --unsafe-fixes --select=F401,F541,F811,E401 .` 多修 3 条 F401 hidden 边界 case（Task 0 提前 `--diff` review）| ~10min |
| **改动 2** | LOW | ruff 全 `--fix` 跑完后剩余 case（估 2 条，±5 余地）加 noqa + 5-15 字中文注释 | ~10-30min |
| **改动 3** | — | 全套件 PASS 3244 / 0 regression + CI 8/8 守门 | AC-2/5 |

**P1 不做**（推迟 P2/P3）：
- P2 候选：F841 + F405 + F403 + E731 + E702 ≈ 143 条
- P3 候选：E402 + E741 + F821 ≈ 124 条 + `[tool.ruff]` config 锁 + CI `ruff-strict` job

---

## 2. 背景

### 2.1 现状 — 421 ruff errors / 12 规则码

2026-05-16 main@`992c791` 实跑 `ruff check . --statistics`：

```
F401 (unused-import)                   128  [✅ --fix]
E402 (module-import-not-at-top)         74  [手工]
E741 (ambiguous-variable-name)          47  [手工]
F405 (undefined-local-from-import-star) 39  [手工]
F841 (unused-variable)                  39  [手工]
F403 (undefined-local-with-import-star) 25  [手工]
E731 (lambda-assignment)                24  [手工]
F541 (f-string-missing-placeholders)    18  [✅ --fix]
E702 (multiple-statements-semicolon)    16  [手工]
F811 (redefined-while-unused)            7  [✅ --fix]
F821 (undefined-name)                    3  [手工 — 真 bug 风险]
E401 (multiple-imports-on-one-line)      1  [✅ --fix]
─────────────────────────────────────────────
Total                                  421
Auto-fix (safe)                        154   ← P1 目标
```

### 2.2 项目历史债隔离原则

`memory/feedback_historical_debt_isolation.md` 约定：**历史债开独立 cleanup commit / 独立 PR 专治**，否则功能 diff 被淹没、code-review 阅读成本暴涨。P1 是首批历史债 cleanup，本 PR **仅含 ruff cleanup**，不混任何功能改动。

### 2.3 3 批风险分层策略

| 批 | 规则码 | 工作量类型 | 估行数 |
| --- | --- | --- | --- |
| **P1（本 PR）** | F401 + F541 + F811 + E401 | `ruff --fix` 一键 | 154 |
| P2 | F841 + F405 + F403 + E731 + E702 | 看一眼能改 / 部分需手工 | ~143 |
| P3 | E402 + E741 + F821 + `[tool.ruff]` config + CI `ruff-strict` job | 跨 file 重组 + 锁规则集 | ~124 + config |

3 批共用同一发布 tag 序列（v2.37.11 / v2.37.12 / v2.37.13），不 bump `pyproject.toml` 版本（v2.25+ tag-only release 惯例，停留 `2.24.0`）。

### 2.4 项目当前 baseline

- 全套件 **3244 PASS / 17 SKIP / 0 regression**（v2.37.10 实测值）
- CI 连续 **20 PR 一次过零 hotfix**（subagent-driven 流程稳定）
- pyproject.toml **无 `[tool.ruff]` 配置段** — 当前跑 ruff default ruleset

---

## 3. 改动范围

### 3.1 In Scope

**改动 1 — ruff `--fix` 自动产物（双步法）**

> rev 2 真值校准：rev 1 写"`--fix` 一键修 154"漂移于 ruff 实际行为。F401 128 条标记 `[-]`（hidden fix），其中 125 条 default `--fix` 即修 + 3 条 `--unsafe-fixes` 才修；F541+F811+E401 = 26 条标记 `[*]` default 即修。total 真值 = 149 + 3 = 152 自动可修 + 2 不可修（候选 noqa）。命令必双步。

**Step A — default `--fix`**（修 149 条）：
```bash
ruff check --fix --select=F401,F541,F811,E401 .
```

**Step B — `--unsafe-fixes`**（多修 3 条 F401 hidden 边界 case）：
```bash
ruff check --fix --unsafe-fixes --select=F401,F541,F811,E401 .
```

各步预期数字：

| 步 | 命令 | 预期 fix | 累计 |
| --- | --- | --- | --- |
| A | `ruff --fix` | 149 | 149 |
| B | `ruff --fix --unsafe-fixes` | 3 | 152 |
| — | 剩余加 noqa（改动 2） | 2 | 154 |

各规则分布（Task 0 实跑校准）：
- F401 unused-import 128 条 — 125 default fix + 3 unsafe-fix（共 128 — 等 Task 0 真值确认；可能 ≤125 fix + ≤5 hidden / 真值 ±3 容差）
- F541 f-string-missing-placeholders 18 条 — 全 `[*]` default fix
- F811 redefined-while-unused 7 条 — 全 `[*]` default fix（全在 tests/ 函数参数 shadow imported name pattern；ruff 删 module-level 重复 import）
- E401 multiple-imports-on-one-line 1 条 — `[*]` default fix

**改动 2 — ruff 双步 `--fix` 跑完后剩余加 noqa**

跑完改动 1 后再跑 `ruff check --select=F401,F541,F811,E401 .` 收集剩余条数 N（估 2 条 ±5 容差）。逐条评估归类，加 `# noqa: <code>  # <5-15 字中文>` 注释。

中文注释**约定 3 类文案**（防漂移）：
- `# noqa: F401  # re-export` — `__init__.py` / 模块公开接口转出口
- `# noqa: F401  # side-effect` — 触发 register / monkey-patch / 模块初始化
- `# noqa: F401  # fixture 触发` — 测试模块导入触发 pytest fixture / conftest 钩子

罕见的真不可归类 case 允许自由文案，但仍须 5-15 字中文 + 不抽象（如"v2.X.Y 占位"非"暂保留"）。

### 3.2 显式 Out of Scope

下列 **本 PR 不动**，违反即视作 scope 漂移：

- 不动 `pyproject.toml` `[tool.ruff]`（P3 才加）
- 不动 `pyproject.toml` `[tool.mypy]`（与 ruff 正交）
- 不动 CI `.github/workflows/*.yml` ruff gate（P3 才加）
- 不动 `pyproject.toml` 版本号（停留 `2.24.0`）
- 不动 P2/P3 规则码（F841 / F405 / F403 / E731 / E702 / E402 / E741 / F821）
- 不重命名变量（即使 F401 误删触发短期变量重命名也不做，spec 选 noqa 路径保 API 稳定）
- 不改 `__all__` / 不加 `as X as X` 别名（同样选 noqa 路径）
- 不做"顺手 cleanup"（typo / 未用 helper / 注释重排等都推迟）

---

## 4. 验收标准（AC）

- **AC-1 ruff 4 类清零**：`ruff check --select=F401,F541,F811,E401 .` exit 0 / `--statistics` 输出 F401/F541/F811/E401 行计数为 0（前提：改动 1 双步 `--fix` + `--unsafe-fixes` 都跑完 + 改动 2 剩余加 noqa）
- **AC-2 全套件不退化**：`pytest` 3244 PASS / 17 SKIP / 0 regression（基线 v2.37.10 main@`992c791`）
- **AC-3 noqa 注释规范**：所有新增 `# noqa: <code>` 必含 5-15 字中文注释；不允许"裸 noqa"或"`# noqa` 无 code"；统一文案 3 类（re-export / side-effect / fixture 触发）+ 罕见自由文案
- **AC-4 commit 二分**：implementation 部分 = 恰 2 个 commit — `commit-impl-1` 仅含 ruff `--fix` 工具产物（不含 noqa 行），`commit-impl-2` 仅含人工 noqa 标注（不改源码语义，diff 全是 `+ # noqa:` 行）
- **AC-5 CI 全绿**：CI 8/8 SUCCESS（Linux / Windows tests + mypy-strict + 其他 job）
- **AC-6 边界证据**：`ruff check . --statistics` 输出 8 类未触动规则（E402 / E741 / F405 / F841 / F403 / E731 / E702 / F821）计数不变（74 / 47 / 39 / 39 / 25 / 24 / 16 / 3 = 267 不变）

---

## 5. 实施步骤（plan 草纲）

| Task | 行为 | 验收 |
|---|---|---|
| **0** | Task 0 scout — (a) 跑 `ruff check --select=F401,F541,F811,E401 . --statistics` 实跑数字校准 == spec 声明 154；(b) **新增**：跑 `ruff check --fix --unsafe-fixes --select=F401 . --diff > /tmp/ruff_unsafe.diff` 提前 review `--unsafe-fixes` 多修的 3 条 F401 具体改什么 file:line（防 hidden side-effect import 误删）；(c) 列出 4 类涉及的 file paths（防 spec 自漂移） | 实跑 statistics == spec / unsafe-fixes diff 内容已 review / file list 留 plan 文档 |
| **1a** | Step A `ruff check --fix --select=F401,F541,F811,E401 .` default 跑 → diff 检视 | `git diff --stat` 看变动文件数 / 行数；预期修 149 |
| **1b** | Step B `ruff check --fix --unsafe-fixes --select=F401,F541,F811,E401 .` 跑 → diff 检视 | `git diff --stat` 显示额外 ≤5 文件变动；预期再修 3（合计 152） |
| **2** | 跑全套件 `pytest` 复跑 | 3244 PASS / 0 regression |
| **3** | `git add -A` + commit-impl-1 `chore(ruff): apply --fix (default + --unsafe-fixes) F401+F541+F811+E401` | commit 落地（含 1a + 1b 双 step 产物，commit body 注明 149 default + 3 unsafe）|
| **4** | 再跑 `ruff check --select=F401,F541,F811,E401 .` 收集 fix 跳过的剩余条目（按 file:line 列出） | 剩余条数 N（估 2 ±5 容差）|
| **5** | 逐条评估 N 条归 3 类（re-export / side-effect / fixture 触发）或罕见自由文案 | 决策表（plan 文档登记 file:line → 类型 → 文案）|
| **6** | 加 `# noqa: <code>  # <5-15 字中文>` | grep `# noqa: F401\|# noqa: F541\|# noqa: F811\|# noqa: E401` 计数 == N |
| **7** | 跑 `ruff check --select=F401,F541,F811,E401 .` exit 0 | AC-1 过 |
| **8** | 跑全套件 `pytest` 复跑 | 3244 PASS / 0 regression |
| **9** | `git add -A` + commit-impl-2 `chore(ruff): add noqa for ruff-not-fixable cases` | commit 落地（diff 全 `+ # noqa:` 行）|
| **10** | self-review + Task 0 scout grep 复跑 + spec/plan 完整性自检 | 通过 |
| **11** | 写 retro doc `docs/superpowers/reports/2026-05-16-v2-37-11-ruff-p1-retro.md` + commit | retro 落地 |
| **12** | open PR → 监 CI → 等 8/8 SUCCESS → squash merge → tag v2.37.11 → GitHub Release notes | release URL |

**总 commit 数 = 6**：spec rev 1 + spec rev 2 + plan + impl-1 + impl-2 + retro

---

## 6. 风险与缓解

| Risk | 影响 | 缓解 |
| --- | --- | --- |
| **R1** ruff `--fix` 删某 `from x import y` 但 y 是 re-export 给下游 | 下游 import 挂 / 测试 fail | 全套件 pytest 守门（AC-2）；Task 2 + Task 8 各跑一次 pytest；ruff fix 跳过的 re-export case 在 Task 5-6 加 noqa（不删）|
| **R2** noqa 中文文案不一致（漂移）| review 不可读 / 后续 cleanup 难匹配 | §3.1 锁 3 类约定文案（re-export / side-effect / fixture 触发）；plan Task 5 决策表强制按 3 类归 |
| **R3** 154 条 statistics 实跑 != spec 声明（main 当前漂移）| spec 自漂移 | Task 0 scout grep 强制 plan 起手前先跑 ruff statistics 校准（若 != 154，先更新 spec 再继续）|
| **R4** commit-impl-1 + impl-2 混淆（一方 diff 漏入另一方）| review 难分辨工具 vs 人工 | AC-4 强制二分；Task 3 commit-impl-1 时 `git diff --staged` 检视 0 处 `# noqa:` 新增；Task 9 commit-impl-2 时 `git diff --staged` 检视 0 处 import 删除 |
| **R5** P1 fix 副作用使 P2/P3 错误重新统计漂移 | P2/P3 spec 数字漂移 | retro 末记录 P1 之后 ruff statistics 重跑数字作 P2 入口 baseline（如 F841 从 39 → 38 是正常的，F841 行数变化 retro 表登记）|
| **R6**（rev 2 新增）F811 7 条全在 tests/ fixture pattern（`broker` 函数参数 shadow line 17 module-level import）；ruff `--fix` 默认删 module-level 重复 import | 若 module-level import 被其他 fixture 真用过 → 测试挂 | 全套件 pytest 守门 + Task 5 noqa 评估时若 R6 真触发则归 "fixture 触发" 类加 noqa 不删 |
| **R7**（rev 2 新增）`--unsafe-fixes` 3 条 F401 hidden 含 side-effect import / typing 假阳 / 跨模块 re-export 等边界 case | side-effect import 误删 → 运行时挂；pytest 不一定覆盖 import-time | Task 0 scout 提前 `--unsafe-fixes --diff` review 3 条；若任一 case 是 side-effect import → 从 unsafe-fixes 命令 fallback 改 Task 5 加 noqa；同时全套件 pytest 守门兜底 |

---

## 7. Review 与流程

**轻档 review**（用户在 brainstorming 第三问明确授权；尽管本 spec 实际 234 行超 CLAUDE.md §6 "≥100 行默认 5 层" 临界点，按 superpowers instruction priority "用户明确指令优先于默认规则" 走轻档；豁免理由 = pure 工具产物 + 行为零改动 + 无 vendor 调用 + spec 234 行大半为 list/table 真实 prose 复杂度低）：

- spec 写完跑 **self-review 一遍** — 4 项 inline check：placeholder（TBD/TODO/vague）/ internal consistency / scope check / ambiguity check
- **Task 0 scout grep** — plan 起手前实跑 ruff statistics 校准 spec 数字

**不跑**（轻档明示豁免）：

- ❌ 5 角色 adversarial review
- ❌ edge-case hunter
- ❌ dry-run state lifecycle
- ❌ 真 vendor 实测（无 vendor 调用）

**subagent-driven 流程**：

- plan 12 task 由 implementer subagent 顺序执行（每 task 主 agent 验证 AC 后才进下一 task）
- commit-impl-2 完成后跑 **2 stage subagent review**：1 次 spec compliance reviewer + 1 次 code quality reviewer（fresh context 防污染）
- final retro+PR 由 1 个 combined subagent 完成

---

## 8. 文档与归档

| 类型 | 路径 |
| --- | --- |
| spec | `docs/superpowers/specs/2026-05-16-v2-37-11-ruff-cleanup-p1-design.md`（本文件，**rev 2**）|
| plan | `docs/superpowers/plans/2026-05-16-v2-37-11-ruff-cleanup-p1.md`（12 task）|
| retro | `docs/superpowers/reports/2026-05-16-v2-37-11-ruff-cleanup-p1-retro.md`|

**Release**：tag `v2.37.11` + GitHub Release notes（不 bump `pyproject.toml` 版本，停留 `2.24.0` — v2.25+ tag-only release 惯例）

**§11 follow-up 状态变化**：

- 新登记：§11 cleanup track P1 closed（待 PR merge 后登）
- 仍 open：P2（F841 + F405 + F403 + E731 + E702 ≈ 143 条）/ P3（E402 + E741 + F821 + `[tool.ruff]` config 锁 + CI gate）/ §11-N7 / §11-N10 / §11-N11 / §11-N12 / §12 f4（同 v2.37.10 handoff 表）

---

## 9. 关联资源

- v2.37.10 retro：`docs/superpowers/reports/2026-05-16-v2-37-10-rebrand-path-real-retry-retro.md`（"360+ ruff cleanup" follow-up 出处）
- v2.37.10 spec：`docs/superpowers/specs/2026-05-16-v2-37-10-rebrand-path-real-retry-design.md`（前序 PR）
- memory 引用约定（CLAUDE.md §memory 引用约定，≤20 字摘要）：
  - 见 memory `feedback_historical_debt_isolation.md`（摘要：cleanup 独立 PR 不混功能）
  - 见 memory `feedback_subagent_driven_main_agent_scouts.md`（摘要：主 agent scout + subagent 执行）
  - 见 memory `project_current_status.md`（摘要：v2.25+ tag-only release）
  - 见 memory `project_v2_37_10_done.md`（摘要：v2.37.10 完工，360+ ruff 待 cleanup）
  - 见 memory `feedback_spec_review_4layers.md`（摘要：spec ≥100 行 5 层默认审）

---

## 10. Spec self-review

### rev 1 self-review（首版）

按 brainstorming skill Step 7 inline 4 项 check：

1. **Placeholder 扫描** — 无 TBD / TODO / vague；唯一估测值 "N（估 0-15）" 在 Task 4 实跑后填实数；"154 条" 在 Task 0 实跑后校准
2. **Internal consistency** — §3.1 改动 1 (154 fix) + §3.1 改动 2 (N noqa) 对齐 §5 Task 1-9 / §4 AC-1+AC-3+AC-4 / §6 R3+R4；commit 二分约定贯穿 §3.1 / §4 AC-4 / §5 Task 3+9 / §6 R4
3. **Scope check** — §3.2 显式 8 项 out-of-scope；§2.3 3 批拓扑明确 P1 边界；scope 适合单 PR
4. **Ambiguity check** — noqa 3 类约定文案明确（re-export / side-effect / fixture 触发）；commit 二分边界明确（impl-1 = 工具，impl-2 = noqa）；轻档 review 4 项明确豁免
5. **行数偏差校准** — spec 写完 234 行（超 100 行临界点），§7 文案已 inline 修正为"按用户 brainstorming 明确授权走轻档"，附豁免理由 4 项

✅ rev 1 self-review 通过；§7 文案行数偏差 inline fix 已落（"<100 行" → "234 行但按用户明确授权走轻档"）。

### rev 2 用户审查抓获

用户 2026-05-16 在 rev 1 commit 落 chore 分支后明确要求"审查防漂移"，抓 1 BLOCKER + 2 MINOR cascade：

| # | 严重度 | 漂移 | rev 2 fix |
| --- | --- | --- | --- |
| **A** | **BLOCKER** | rev 1 §3.1 §5 §4 命令 `ruff check --fix --select=F401,F541,F811,E401 .` 默认只修 149 条（F401 128 标记 `[-]` hidden 中 125 default fix + 3 unsafe-fixes 才修）→ AC-1 永远过不去 | §1 摘要 + §3.1 改双步法（Step A default `--fix` 149 + Step B `--fix --unsafe-fixes` 多 3）；§4 AC-1 加前提说明；§5 Task 1 拆 1a + 1b |
| **B** | MINOR | rev 1 noqa 估测 "5-15 条" 漂移于真值 2（即使 `--unsafe-fixes` 也修不了的剩余）| §1 摘要 + §3.1 改动 2 + §5 Task 4 改 "估 2（±5 容差）" |
| **C** | MINOR | rev 1 §6 R1 暗示 `__init__.py` re-export 风险但实测 19 个 `__init__.py` 全无 F401（count = 0）；R5 暗示 platform-conditional 但 F811 实测全在 tests/ fixture pattern；`--unsafe-fixes` 3 条 hidden 没单独 review | §6 加 R6 (F811 tests/ fixture pattern) + R7 (`--unsafe-fixes` 3 条 Task 0 提前 review)；Task 0 加 unsafe-fixes diff scout |

rev 2 inline 4 项 check：

1. **Placeholder 扫描** — rev 2 数字真值化（149 / 3 / 2）；剩 `±5 容差` 是合理估测不视作 placeholder
2. **Internal consistency** — §1 / §3.1 / §4 AC-1 / §5 Task 1a+1b / §6 R6+R7 双步法贯穿；commit 数字从 5 升 6（spec rev 1 + rev 2 + plan + impl-1 + impl-2 + retro）已在 §5 末更新；commit-impl-1 含 1a+1b 双 step 仍是单 commit（§4 AC-4 commit 二分约定不破）
3. **Scope check** — rev 2 fix 全在 §1/§3.1/§4/§5/§6 范围内，未引入新 scope；§3.2 out-of-scope 列表不变
4. **Ambiguity check** — rev 2 真值脚注明确"149 default + 3 unsafe + 2 noqa"分解；Task 0 scout 三步 (a)/(b)/(c) 明确

✅ rev 2 self-review 通过；3 漂移项全 inline fix。

---

## 11. § follow-up 表（本 PR 自身 self follow-up）

> § 编号约定：本 spec 自身的 self follow-up 进 §12（与 STATUS doc §11 follow-up 区分）

| § | 来源 | 内容 | 状态 |
| --- | --- | --- | --- |
| **§12 f1** | rev 2 抓获 | rev 1 漂移教训：spec 写工具命令前必须 dry-run 校准（不能凭 ruff statistics `[*]` / `[-]` 标号字面推断），lesson 进 retro | open（PR 末进 retro）|
| **§12 f2** | rev 2 抓获 | Task 0 scout 三步可推广为 ruff cleanup spec 模板（P2/P3 复用），lesson 进 retro | open（PR 末进 retro）|

---

**rev 2 写讫**。下一步：用户 review 本 spec 文档（rev 2，路径上方），通过后进 writing-plans 出 plan 文件。
