# §11-N16 闭环 — Plan verify 命令白名单实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `CLAUDE.md ## Superpowers 插件工作流` 新增 `### Plan 中 verify 命令必抄 CI（防 N-16 类 false-alarm）` 子节 + 7 行 verify 白名单表 + 边界规则；同时在 `v2.37.15 retro §3.3 N-16 row` 末追加 closure 引用 → release v2.37.16。

**Architecture:** Pure docs append（CLAUDE.md + retro 共 2 文件改动），无 RED/GREEN 阶段分。subagent 派发 6 task：scout grep → 2 edit → AC 验证 → commit + PR → CI + tag。

**Tech Stack:** `git` / `gh` CLI / `grep -E` ERE / Edit tool。无代码、无测试、无 lint scope 变更。

**Spec source:** `docs/superpowers/specs/2026-05-18-n16-plan-verify-cmd-whitelist-design.md` (rev 3)

---

## File Structure

| 文件 | 操作 | 责任 |
|---|---|---|
| `CLAUDE.md` | Modify（在 `### 并行任务` 后、`---` 前插入新 `### Plan 中 verify 命令必抄 CI` 子节）| 新工艺规则落地 |
| `docs/superpowers/reports/2026-05-18-v2-37-15-retro.md` | Modify（§3.3 表 N-16 row 末段替换"下次写 ruff verify step plan 触发"为 closure 引用） | follow-up 闭合记录 |
| `docs/superpowers/specs/2026-05-18-n16-plan-verify-cmd-whitelist-design.md` | 已存在（brainstorming 阶段写入）| spec |
| `docs/superpowers/plans/2026-05-18-n16-plan-verify-cmd-whitelist.md` | 已存在（本文件）| plan |

不改：`.github/workflows/*.yml` / `JURY_MATCHES_SPEC_STATUS.md` / `tools/` / `tests/` / `pyproject.toml` / 其他 spec / 其他 plan。

---

## Task 0: Scout grep 真值核验（plan-drift 5 分类预防）

**目的**：CLAUDE.md §10 plan-drift 5 分类 — 实施前先 grep 真值锚，防 (b) 路径假设错 / (d) 实现细节 bug。

**Files:**
- Read: `CLAUDE.md` line 31-35
- Read: `.github/workflows/tests.yml` lines 141 / 143 / 150 / 178
- Read: `docs/superpowers/reports/2026-05-18-v2-37-15-retro.md` line ~73

- [ ] **Step 1: grep CLAUDE.md ### 并行任务 位置**

Run:
```bash
grep -nE "^### 并行任务|^---" CLAUDE.md | head -5
```
Expected output:
```
31:### 并行任务
35:---
```
（行号若与 spec 不符也无妨；只要"### 并行任务"后第一个"---"是插入点上方分隔线即可。）

- [ ] **Step 2: grep tests.yml 7 白名单命令字面**

Run:
```bash
grep -nE "ruff check \.|mypy --platform=win32 adapters/solidworks|mypy --strict tools/jury|mypy --strict tools/enhance_consistency|pytest tests/test_parts_resolver|--cov-fail-under=95" .github/workflows/tests.yml
```
Expected output（顺序无关）:
```
65:          pytest tests/ -v --tb=short \
70:            --cov-fail-under=95
82:          pytest tests/ -v --tb=short -m "not mypy" --cov=adapters.solidworks.sw_config_broker --cov=adapters.solidworks.sw_config_lists_cache --cov=adapters.solidworks.sw_list_configs_worker --cov-report=term-missing --cov-fail-under=95
126:          pytest tests/test_parts_resolver.py tests/test_parts_adapters.py -v
141:        run: mypy --platform=win32 adapters/solidworks/sw_config_broker.py
143:        run: mypy --strict tools/jury tools/photo3d_jury.py tools/_file_lock.py
150:        run: mypy --strict tools/enhance_consistency.py tools/render_qa.py tools/path_policy.py tools/view_instance_evidence.py
178:        run: ruff check .
```
**判定**：所有 7 命令字面存在于 tests.yml。如某行无匹配（tests.yml 演进），停 plan 改 spec rev 4 与真值对齐。

- [ ] **Step 3: grep v2.37.15 retro N-16 row 末段**

Run:
```bash
grep -nE "§11-N16.*下次写 ruff" docs/superpowers/reports/2026-05-18-v2-37-15-retro.md
```
Expected output:
```
73:| **§11-N16** | plan ruff command scope 校准 — v2.37.15 Task 8 step 2 ruff check 命令带显式 path `tools/ src/ tests/`，逾出 pyproject.toml 配的 ruff scope，触发 24 pre-existing 历史债 errors；项目 CI 真用 `ruff check .`（pyproject scope）。**未来 plan ruff/mypy command 必须 verbatim 抄项目 CI 命令** | 下次写 ruff verify step plan 触发 |
```
**判定**：行存在、末段是 " 下次写 ruff verify step plan 触发 |"（Task 2 用此末段做 old_string 锚）。

- [ ] **Step 4: 报告 scout 结果**

如 Step 1-3 全部如预期，登记"Task 0 scout PASS"进入 Task 1；若任一不符，停 plan 回 spec rev 4。

**预计**：3 min。

---

## Task 1: CLAUDE.md 新增 `### Plan 中 verify 命令必抄 CI` 子节

**Files:**
- Modify: `CLAUDE.md`（在 `独立子任务可通过...加快交付。` 后、`---` 前）

- [ ] **Step 1: 用 Edit tool 替换 anchor**

Edit `CLAUDE.md`:

**old_string**（精确字面，含末尾空行）:
```
独立子任务可通过 `superpowers:executing-plans` 的并行 subagent 分发机制同时执行，以加快交付。

---
```

**new_string**:
```
独立子任务可通过 `superpowers:executing-plans` 的并行 subagent 分发机制同时执行，以加快交付。

### Plan 中 verify 命令必抄 CI（防 N-16 类 false-alarm）

**适用范围**：本节规则仅约束 **plan 文件**（`docs/superpowers/plans/*.md`）中的 verify step（步骤含"运行 ruff" / "运行 mypy" / "运行 pytest" 等之类的 CI 镜像验证）。**不**约束本地开发 pre-commit 提示（见 `## 技术规范 → Python` 的 `uv run ruff check .` 是本地工作流），**不**约束单文件 / single-test pytest 调用。

plan verify step 中所有 ruff / mypy / pytest 命令必须 **verbatim 抄** `.github/workflows/tests.yml` 中对应 step 的整行命令（含 quote 风格 / 空格 / 续行符），**不许** 自加 path scope / select override。否则会触发 pyproject 配置外的 false-alarm（v2.37.15 plan Task 8 实证：写 `ruff check tools/ src/ tests/` 触发 24 historical errors，应改 `ruff check .`）。

**verify 命令白名单**（截至 2026-05-18 / v2.37.15）：

| 用途 | tests.yml step 名 | plan 中允许写法 |
|---|---|---|
| ruff lint 全仓 | `ruff-strict` → "Run ruff check (P1+P2+P3 全规则集 守门)" | `ruff check .` |
| mypy broker | `mypy-strict` → "Run mypy strict on sw_config_broker.py" | `mypy --platform=win32 adapters/solidworks/sw_config_broker.py` |
| mypy jury | `mypy-strict` → "Run mypy strict on tools/jury" | `mypy --strict tools/jury tools/photo3d_jury.py tools/_file_lock.py` |
| mypy render-QA | `mypy-strict` → "Run mypy strict on render QA / path_policy" | `mypy --strict tools/enhance_consistency.py tools/render_qa.py tools/path_policy.py tools/view_instance_evidence.py` |
| pytest 全套 (Linux) | `test` → "Run tests with coverage gate (Linux / macOS)" | `pytest tests/ -v --tb=short -m "not mypy" --cov=adapters.solidworks.sw_config_broker --cov=adapters.solidworks.sw_config_lists_cache --cov-report=term-missing --cov-fail-under=95` |
| pytest 全套 (Windows) | `test` → "Run tests with coverage gate (Windows, PYTHONUTF8=1)" | `pytest tests/ -v --tb=short -m "not mypy" --cov=adapters.solidworks.sw_config_broker --cov=adapters.solidworks.sw_config_lists_cache --cov=adapters.solidworks.sw_list_configs_worker --cov-report=term-missing --cov-fail-under=95` |
| pytest regression | `regression` → "Run parts_resolver unit tests with kill switch" | `pytest tests/test_parts_resolver.py tests/test_parts_adapters.py -v` |

**narrowing 允许 vs scope override 禁止**：

- ✓ 允许 `-k filter` / `-x` / `--lf` 等 selector narrowing（在 CI scope 内做子集筛选）
- ✗ 禁止 `ruff check tools/ src/`（path override）/ `ruff check --select=X`（rule override）/ `mypy --strict <与 tests.yml 不同的 files>` / `pytest tests/ --cov=other`（cov target override）

**sync 责任**：`tests.yml` 中 ruff / mypy / pytest step 增删改时，PR **建议同步改本表**（INFO，非阻断）；reviewer 抓 `tests.yml` diff 含 lint/test 命令变动但 CLAUDE.md 未动 → 提示同步即可。

**例外**：

- 单测 / single-test pytest（如 `pytest tests/test_foo.py::test_bar -v`）不算 verify step，可自由写
- 本地 pre-commit 检查（见 `## 技术规范 → Python` 的 `uv run` 形式）独立轨道，不在本节范围

---
```

注意 old_string 末尾 `---` 与 new_string 末尾 `---` 是同一个分隔线 —— Edit 把新子节插入到 `---` 上方。

- [ ] **Step 2: grep 验证插入成功**

Run:
```bash
grep -n "^### Plan 中 verify 命令必抄 CI" CLAUDE.md
```
Expected output（行号视插入位置而定）:
```
<line>:### Plan 中 verify 命令必抄 CI（防 N-16 类 false-alarm）
```

**预计**：5 min（Edit 工具一次到位 + grep 验证）。

---

## Task 2: v2.37.15 retro §3.3 N-16 row 附 closure 引用

**Files:**
- Modify: `docs/superpowers/reports/2026-05-18-v2-37-15-retro.md`（line 73，§3.3 表 N-16 row 末段）

- [ ] **Step 1: 用 Edit tool 替换 N-16 row 末段**

Edit `docs/superpowers/reports/2026-05-18-v2-37-15-retro.md`:

**old_string**（精确字面，N-16 row 末 7 词）:
```
**未来 plan ruff/mypy command 必须 verbatim 抄项目 CI 命令** | 下次写 ruff verify step plan 触发 |
```

**new_string**:
```
**未来 plan ruff/mypy command 必须 verbatim 抄项目 CI 命令** | ✅ **closed v2.37.16**（CLAUDE.md `## Superpowers 插件工作流` 新增 `### Plan 中 verify 命令必抄 CI` 子节 + 7 行白名单 + narrowing-vs-override + sync 责任，见 [spec](../specs/2026-05-18-n16-plan-verify-cmd-whitelist-design.md)） |
```

- [ ] **Step 2: grep 验证 retro 更新成功**

Run:
```bash
grep -nE "§11-N16.*closed v2\.37\.16" docs/superpowers/reports/2026-05-18-v2-37-15-retro.md
```
Expected output:
```
73:| **§11-N16** | ... | ✅ **closed v2.37.16**（...） |
```

**预计**：3 min。

---

## Task 3: AC-1 ~ AC-5 grep 验证

**目的**：spec §4 验收标准 AC-1 ~ AC-5 全部 grep 验证一次性跑过（AC-6 = CI gate 在 PR 后跑）。

**Files:**
- Read: `CLAUDE.md` + `docs/superpowers/reports/2026-05-18-v2-37-15-retro.md`

- [ ] **Step 1: AC-1 — CLAUDE.md 含新 ### 子节标题**

Run:
```bash
grep -n "Plan 中 verify 命令必抄 CI" CLAUDE.md
```
Expected: ≥ 1 line（实际预期 2 处：一处 heading "### Plan 中 verify 命令必抄 CI（防 N-16 类 false-alarm）"，可能正文未再引用 → 至少 1 命中）。

- [ ] **Step 2: AC-2 — 白名单 7 行 6 模式 grep 命中**

Run:
```bash
grep -cE "ruff check \.|mypy --platform=win32 adapters/solidworks|mypy --strict tools/jury|mypy --strict tools/enhance_consistency|--cov-fail-under=95|pytest tests/test_parts_resolver" CLAUDE.md
```
Expected: ≥ 7（实际预期 9 = baseline 1 [line 49 `uv run ruff check .`] + 新增 8 [whitelist 7 行 + 适用范围段 1 处 `ruff check .` 例]）。

- [ ] **Step 3: AC-3 — 3 处 tests.yml 提及**

Run:
```bash
grep -c "tests.yml" CLAUDE.md
```
Expected: ≥ 3（适用范围段 1 + 主规则 1 + sync 责任段 1）。

- [ ] **Step 4: AC-4 — narrowing-vs-override + single-test 段存在**

Run:
```bash
grep -nE "narrowing 允许 vs scope override 禁止|single-test pytest" CLAUDE.md
```
Expected: ≥ 2 lines。

- [ ] **Step 5: AC-5 — retro 含 closure 引用**

Run:
```bash
grep -n "v2\.37\.16" docs/superpowers/reports/2026-05-18-v2-37-15-retro.md
```
Expected: ≥ 1 line（应命中 Task 2 写入的 "closed v2.37.16"）。

- [ ] **Step 6: 汇报 AC 全过**

5 项 AC 全部预期匹配 → 进入 Task 4 commit。任一 fail → 回 Task 1/2 修。

**预计**：3 min。

---

## Task 4: 切分支 + commit + push + open PR

**Files:**
- 4 staged: `CLAUDE.md` + `docs/superpowers/reports/2026-05-18-v2-37-15-retro.md` + `docs/superpowers/specs/2026-05-18-n16-plan-verify-cmd-whitelist-design.md`（spec 已落盘但未 stage）+ `docs/superpowers/plans/2026-05-18-n16-plan-verify-cmd-whitelist.md`（plan 已落盘但未 stage）

- [ ] **Step 1: 确认当前在 main 分支 + clean working tree（除本 PR 文件）**

Run:
```bash
git status
git branch --show-current
```
Expected：
- `git branch --show-current` 输出 `main`
- `git status` 应见 2 个 modified（CLAUDE.md / 2026-05-18-v2-37-15-retro.md）+ 2 个 untracked（spec / plan 新文件）

- [ ] **Step 2: 切 feature 分支**

Run:
```bash
git checkout -b feat/n16-plan-verify-whitelist
```
Expected: `Switched to a new branch 'feat/n16-plan-verify-whitelist'`

- [ ] **Step 3: git add 4 文件**

Run:
```bash
git add CLAUDE.md docs/superpowers/reports/2026-05-18-v2-37-15-retro.md docs/superpowers/specs/2026-05-18-n16-plan-verify-cmd-whitelist-design.md docs/superpowers/plans/2026-05-18-n16-plan-verify-cmd-whitelist.md
git status
```
Expected: 4 文件全 staged，无其他 untracked / modified。

- [ ] **Step 4: commit（pre-commit hook 已配 `commit.gpgsign=false`）**

Run:
```bash
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(workflow): §11-N16 — plan verify 命令必抄 CI 白名单 + retro 闭环 (v2.37.16)

CLAUDE.md ## Superpowers 插件工作流 新增 ### Plan 中 verify 命令必抄 CI 子节：
- 适用范围段（隔本地 pre-commit / single-test pytest）
- 主规则 + 反例（v2.37.15 plan Task 8 ruff check tools/ src/ tests/ → 24 historical errors）
- 7 行 verify 白名单（ruff 1 + mypy broker/jury/render-QA + pytest Linux/Windows/regression）
- narrowing-vs-override 子条（-k 允许；path/select/cov override 禁）
- sync 责任段（tests.yml 演进时同 PR 改本表，reviewer 提示，INFO 非阻断）

docs/superpowers/reports/2026-05-18-v2-37-15-retro.md §3.3 N-16 row：
- 末段 "下次写 ruff verify step plan 触发" → "✅ closed v2.37.16（...）"
- 同 v2.37.13b retro §3.3 N12 → v2.37.14 closure 模式

零代码、零测试、零 lint scope 改动；CLAUDE.md 不在 lint scope。

spec: docs/superpowers/specs/2026-05-18-n16-plan-verify-cmd-whitelist-design.md (rev 3)
plan: docs/superpowers/plans/2026-05-18-n16-plan-verify-cmd-whitelist.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```
Expected: `[feat/n16-plan-verify-whitelist <sha>] feat(workflow): §11-N16 — ...`

- [ ] **Step 5: push 分支**

Run:
```bash
git push -u origin feat/n16-plan-verify-whitelist
```
Expected: `* [new branch] feat/n16-plan-verify-whitelist -> feat/n16-plan-verify-whitelist`

注：本仓 git config 已配 SSH（HTTPS:443 被封）。如 push 报 auth 错，确认 `git remote -v` 是 git@github.com:proecheng/cad-spec-gen.git。

- [ ] **Step 6: 用 gh CLI 开 PR**

Run:
```bash
gh pr create --base main --head feat/n16-plan-verify-whitelist --title "feat(workflow): §11-N16 plan verify 命令白名单 + retro 闭环 (v2.37.16)" --body "$(cat <<'EOF'
## Summary

闭合 v2.37.15 retro §3.3 **§11-N16**：plan 中 ruff/mypy/pytest verify 命令必须 verbatim 抄 `tests.yml` 真命令，防 plan-drift 触发 pyproject 配置外 false-alarm。

## 改动

- `CLAUDE.md ## Superpowers 插件工作流` 新增 `### Plan 中 verify 命令必抄 CI（防 N-16 类 false-alarm）` 子节
- `docs/superpowers/reports/2026-05-18-v2-37-15-retro.md` §3.3 N-16 row 附 closure 引用 v2.37.16

零代码、零测试、零 lint scope 改动；CLAUDE.md 不在 lint scope。

## 验收

- AC-1 ~ AC-5：5 项 grep verify pass（见 plan Task 3）
- AC-6：CI 9/9 SUCCESS（本 PR 待）
- 北极星 5 gate：全过
- plan-drift 5 分类 scout：Task 0 已跑（tests.yml 真值 + retro 真值 ✓）

## 相关

- spec: `docs/superpowers/specs/2026-05-18-n16-plan-verify-cmd-whitelist-design.md` (rev 3，含 rev 1→3 演进 audit log)
- plan: `docs/superpowers/plans/2026-05-18-n16-plan-verify-cmd-whitelist.md`
- 起源：v2.37.15 retro §3.3 N-16（plan Task 8 写 `ruff check tools/ src/ tests/` → 24 historical errors）
- 闭环模式参考：v2.37.13b retro §3.3 N12 → v2.37.14

## 不涉

- N-13 / N-14 / N-15 仍 ⬜ open（plan-writing 工艺类规则，后续 PR 处理）
- STATUS doc `JURY_MATCHES_SPEC_STATUS.md`：N-16 本就不在 §9.3（该 STATUS doc 装 jury matches_spec 实现 follow-up，N-13~N-17 工艺规则不同性质）

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
Expected: `https://github.com/proecheng/cad-spec-gen/pull/<N>` URL 输出。

**预计**：5 min（含 commit msg 输入 + push wait + gh pr create）。

---

## Task 5: CI 监控 + merge + tag v2.37.16 + GitHub Release

**Files:** 无文件改动；外部操作 GitHub。

- [ ] **Step 1: 等 CI 完成（9 jobs）**

Run:
```bash
gh pr checks <PR>
```
（替换 `<PR>` 为 Task 4 Step 6 输出的 PR 号）

Expected: 全 `pass` 或 9/9 SUCCESS。

注：pure docs append 不动 lint scope，理论上 CI 稳过；sw-smoke.yml 是已知 transient flake 但单独失败不阻断 release（CLAUDE.md §9）。如 9 个核心 job 全过即可 merge。

- [ ] **Step 2: squash merge PR**

Run:
```bash
gh pr merge <PR> --squash --delete-branch
```
Expected: PR 状态 → MERGED + 远程分支删除。

- [ ] **Step 3: 回 main + pull latest**

Run:
```bash
git checkout main
git pull --ff-only origin main
git log --oneline -1
```
Expected: 最新 commit 是 squash merge 的 N-16 commit。

- [ ] **Step 4: 打 tag v2.37.16**

Run:
```bash
git tag v2.37.16
git push origin v2.37.16
```
Expected: `* [new tag] v2.37.16 -> v2.37.16`

- [ ] **Step 5: 创建 GitHub Release**

Run:
```bash
gh release create v2.37.16 --title "v2.37.16 — §11-N16 plan verify 命令白名单 + retro 闭环" --notes "$(cat <<'EOF'
## §11-N16 闭环

闭合 v2.37.15 retro §3.3 **§11-N16**：plan 中 ruff/mypy/pytest verify 命令必须 verbatim 抄 `.github/workflows/tests.yml` 真命令，防 plan-drift 触发 false-alarm。

## 改动

- `CLAUDE.md ## Superpowers 插件工作流` 新增 `### Plan 中 verify 命令必抄 CI（防 N-16 类 false-alarm）` 子节
- `docs/superpowers/reports/2026-05-18-v2-37-15-retro.md` §3.3 N-16 row 附 closure 引用 v2.37.16

## 安装

无变化（v2.25+ tag-only release，`pyproject.toml` 仍 `2.24.0`；docs-only PR 不影响 runtime）。

`pip install git+https://github.com/proecheng/cad-spec-gen.git@v2.37.16`

## 相关

- spec: `docs/superpowers/specs/2026-05-18-n16-plan-verify-cmd-whitelist-design.md` (rev 3)
- plan: `docs/superpowers/plans/2026-05-18-n16-plan-verify-cmd-whitelist.md`

## 不涉

- N-13/N-14/N-15 仍 open（plan-writing 工艺规则后续 PR）
- STATUS doc `JURY_MATCHES_SPEC_STATUS.md`：N-16 本就不在 §9.3（性质不同）

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
Expected: Release URL 输出 + GitHub Release 页面可见。

- [ ] **Step 6: 汇报本 PR 完工**

报：PR <N> merged → tag v2.37.16 pushed → Release published → CI 连续 28 PR 一次过纪录 +1。

**预计**：5-8 min（含 CI 等待 ~7 min + merge/tag/release ~3 min）。

---

## 实施完整估时

| Task | 预计 |
|---|---|
| Task 0: scout grep | 3 min |
| Task 1: CLAUDE.md edit | 5 min |
| Task 2: retro edit | 3 min |
| Task 3: AC 验证 | 3 min |
| Task 4: commit + PR | 5 min |
| Task 5: CI + merge + tag | 5-8 min |
| **总计** | **~24-27 min** |

retro PR 单独后续：~5 min。

---

## 子-skill 调度建议

本 plan **不**建议每 task 派 subagent — task 极简（6 个，每个 < 5 min），主 agent 自跑 + per-task 主 agent inline verify 即可。

**派遣模式**：

- Task 0：主 agent 自跑（scout 不派 subagent，CLAUDE.md §6 / `feedback_subagent_driven_main_agent_scouts.md`）
- Task 1-3：主 agent 自跑（mechanical edit + grep verify，无复杂判断）
- Task 4-5：主 agent 自跑（git/gh 调用主 agent 直接做更稳）

如用户偏好 subagent 派发，Task 1 / Task 2 可派 haiku 各做一次 edit（spec compliance reviewer skip — task 极轻 + spec ↔ plan 1:1 对应）。

---

## 风险与缓解

| 风险 | 概率 | 缓解 |
|---|---|---|
| Task 1 Edit anchor 不唯一 | 低 | `独立子任务可通过...加快交付。\n\n---\n` 在 CLAUDE.md 全文应只 1 处（### 并行任务 段末）；Task 0 Step 1 grep 已验证 |
| Task 2 Edit anchor 不唯一 | 低 | N-16 row 末段 `下次写 ruff verify step plan 触发 \|` 是 retro doc 唯一字符串（Task 0 Step 3 grep 已验证）|
| CI flake（sw-smoke） | 低 | 已知 transient 不阻断 release（CLAUDE.md §9）；只看 9 个核心 test job |
| push auth fail（SSH 配置漂移）| 极低 | 本仓 `git remote -v` 应是 SSH；如失败手工 `git remote set-url origin git@github.com:proecheng/cad-spec-gen.git`|
| AC-2 grep 误命中（baseline 污染） | 极低 | spec self-review 已 dry-run：CLAUDE.md 现状 = 1 命中 + 改后 +8 = 9 总命中，阈值 ≥7 留 22% margin |
| 用户中途要求改 spec | 中（任意时刻）| brainstorming 已 3 轮审，理论稳定；如改 → 退回 brainstorm 第 5 步 |

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
