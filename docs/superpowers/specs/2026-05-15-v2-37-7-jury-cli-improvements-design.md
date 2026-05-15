# 设计：v2.37.7 §11-N3 + §11-N2 — photo3d-jury CLI 改进

- **日期**：2026-05-15
- **基线**：main@`184a7e1`（v2.37.6 merge 后；working tree clean）
- **分支**：`feat/v2-37-7-jury-cli-improvements`（待建）
- **目标版本**：v2.37.7（patch release / 纯 git tag + GitHub Release / 不 bump 版本文件）
- **规模**：小 单 PR；总 diff ≈ 50 行 production + 40 行测试 + 5 行 docs + 60 行 retro ≈ **~150 行**
- **状态**：brainstorming 完成（含 fact-check F1+F2+F3+F4 inline 修，layer 6 边界审查 4 findings）；待用户复审 → writing-plans

---

## 1. 背景与目标

batch 2 — 2 项 photo3d-jury CLI 用户 UX 改进：

- **§11-N3**：jury 真跑时每 view 结束后写 1 行 stderr 进度（修 GISBOT e2e 实测"jury 跑时 stderr 0 bytes，用户不知是否挂"问题）；**含 except 失败路径同样输出**（F1 fix：避免失败 view 静默 误判"全跑了"）
- **§11-N2**：加 `--override-subsystem` alias flag（修跨项目跑 jury 时 `--subsystem` 必须匹配 report 内嵌 subsystem 的限制；让 user 显式声明 cli arg vs effective subsystem 差异）

---

## 2. 范围

### 2.1 In-scope

| 文件 | 改动 | 行数 |
|---|---|---|
| `tools/photo3d_jury.py` per-view 循环 try-success 路径（line ~620 之后）| stderr 写 1 行 `△ [V<n>/<total>] <model> photoreal=<score> verdict=<verdict> <latency>s` | +3 行 |
| `tools/photo3d_jury.py` per-view 循环 except 失败路径（line ~644 之后；**F1 fix**）| stderr 写 1 行 `△ [V<n>/<total>] <model> ERROR <error_kind> <latency>s` | +3 行 |
| `tools/photo3d_jury.py:_build_parser`（line 105+）| 加 `--override-subsystem` flag | +5 行 |
| `tools/photo3d_jury.py:main()` | 计算 effective_subsystem = `args.override_subsystem or args.subsystem`；用于 active_run_dir 解析 + report `effective_subsystem` 字段（仅 override 时存在）| +10 行 |
| `tests/jury/test_photo3d_jury_*.py`（新或扩展邻接 test）| 3 TDD 测试：per-view 进度 success + failure + --override-subsystem flag | +40 行 |
| `docs/cad-jury-config.md` 附录 A cli flag 表 | 加 `--override-subsystem` 行描述 | +2 行 |
| `docs/superpowers/reports/2026-05-15-v2-37-7-jury-cli-improvements-retro.md`（新写）| retro | ~60 行 |

**总 diff** ≈ **~125 行代码 + ~60 行 retro = ~185 行**；有 production code 改 → 必发 v2.37.7 patch tag。

### 2.2 Out-of-scope

- 不改 jury Layer 0 / Layer 1 / Layer 2 算法逻辑
- 不改 `tools/jury/*.py`（只 `tools/photo3d_jury.py`）
- 不改既有 CLI flag 行为（`--subsystem` / `--budget` / `--profile-id` 等不动）
- 不改 `--single-view` 内部 CLI 路径（短路 line 252 之前 return）
- §12 残 f1/f4 / §11-N1 rebrand 工具 — 留 batch 3

---

## 3. 设计决策

### 3.1 D1 — §11-N3 per-view 进度：try-success + except-failure 双路径输出（F1 fix）

**抉择**：每 view 跑完后写 1 行 stderr，**try-success + except-failure 两处都加**（layer 6 F1 修：避免失败 view 静默）。

**格式**：

```python
# try-success 路径（line ~620 view_verdicts.append({...}) 之后）：
latency_s = round(resp.latency_ms / 1000, 1)  # F3 fix: 从 llm_meta.latency_ms 计算
sys.stderr.write(
    f"△ [{view_name}/{total_views}] {profile.model} "
    f"photoreal={vv.photoreal_score} verdict={vv.verdict} {latency_s}s\n"
)

# except-failure 路径（line ~644 之后；F1 修必须加）：
sys.stderr.write(
    f"△ [{view_name}/{total_views}] {profile.model} "
    f"ERROR {exc.error_kind} 0.0s\n"
)
```

**理由**：
- `△` 字符沿用 jury 既有 stderr 风格（实测 line 763 `△ CAD_JURY_DISABLE_LLM=1` + line 267/465/470/497/513/776 `✗ ...`）
- F1 修：**try-success + except-failure 必须双覆盖**，否则 GISBOT 7 view 1 失败时用户只看到 6 行 success 进度无失败行 → 误判"全跑了 = OK"；改完体验反而更差
- F3 修：`latency_s = round(llm_meta.latency_ms / 1000, 1)` 显式（既有 `llm_meta.latency_ms` 是 int 毫秒；user-friendly 1 位小数秒）
- `<view_name>` 是 V1-V7 字符串（既有 `view_verdicts[].view` 字段）；`<total_views>` 从 `enhancement_report.view_count` 取
- 不破坏既有用户工作流：stderr 输出不影响 stdout 数据通道；既有 stderr 已有 ✗ / △ 字符约定

### 3.2 D2 — §11-N2 alias flag：cli vs effective subsystem 分层（F2 fix）

**抉择**：加 `--override-subsystem ACTUAL_SUBSYSTEM` flag。

**语义**（F2 fix：明示既有 `subsystem` 字段语义不变）：

- `args.subsystem` = user-facing 项目名（cli arg + jury report 顶层 `subsystem` 字段，**语义不变**；既有 reader 不破）
- `args.override_subsystem` = effective subsystem（jury Layer 0 解析 active_run_dir + report cross-check 用此值；jury 内部所有 path 解析用 effective）
- 若不指定 override → effective = `args.subsystem`（默认行为不变，零行为变化对既有 user）
- jury report 加新字段 `effective_subsystem`（**仅 override 时存在**，向后兼容 forward-compat — v2.37.4 §13 版本承诺允许）

**实施伪代码**：
```python
effective_subsystem = args.override_subsystem or args.subsystem
# 既有 args.subsystem 用法不变（如 line 687/745 report 写）
# 新代码用 effective_subsystem 解析 path / Layer 0 cross-check
run_dir = project_root / "cad" / effective_subsystem / ".cad-spec-gen" / "runs" / active_run_id
# report 加字段（仅 override 时）：
if args.override_subsystem:
    report["effective_subsystem"] = effective_subsystem
```

**用例**（GISBOT e2e 复用）：
```
cd D:/Work/cad-tests/GISBOT && \
  python -m tools.photo3d_jury \
    --project-root . \
    --subsystem GISBOT \
    --override-subsystem end_effector \
    --budget 0.20
```

**理由**：
- alias 让 user 显式声明"project=GISBOT 实跑=end_effector"避免 silent mismatch（GISBOT e2e 实测 §11-N2 来源）
- 不强制 override 既有用户路径（默认 effective=cli arg，零行为变化）
- 既有 `subsystem` 字段语义不变（forward-compat 硬保障 v2.37.4 §13）

### 3.3 D3 — 合 1 PR + 4 commit 拆分

**抉择**：v2.37.7 1 PR；commit 拆 4（feat per-view 进度 + feat --override-subsystem + docs append + retro）。

**理由**：scope 都小且都是 jury CLI 改进；合并发 review 成本低；4 commit 便于 PR diff 阅读 + 任一项 regress 可识别（squash 后 main 1 merge commit）。

---

## 4. 验收

- **AC-1** per-view 循环每 view 跑完后 stderr 输出 1 行：
  - try-success: `△ [V<n>/<total>] <model> photoreal=<score> verdict=<verdict> <latency>s`
  - except-failure (F1): `△ [V<n>/<total>] <model> ERROR <error_kind> 0.0s`
- **AC-2** `--override-subsystem ACTUAL_SUBSYSTEM` flag 加进 argparse；不指定时 effective = `args.subsystem`（零行为变化）；既有 report `subsystem` 字段语义不变（F2 fix）
- **AC-3** GISBOT-like 用例 `--subsystem GISBOT --override-subsystem end_effector` jury Layer 0 用 end_effector 解析 run_dir + report 含 `effective_subsystem: "end_effector"` 字段（仅 override 时存在）
- **AC-4** AC grep strict（F4 fix：用 ERE `-cE`）：
  - `grep -cE "△ \[" tools/photo3d_jury.py` ≥ 2（success + failure 两处进度模板，F1）
  - `grep -c "override-subsystem" tools/photo3d_jury.py` ≥ 2（argparse 加 + main 用）
  - `grep -c "effective_subsystem" tools/photo3d_jury.py` ≥ 1（report 字段 + 计算）
- **AC-5** 新增测试 3 个：
  - `test_per_view_progress_stderr_emit_success` mock urlopen → success → capture stderr → assert 含 `△ [V1/` + `photoreal=` + `verdict=`
  - `test_per_view_progress_stderr_emit_failure`（F1）mock urlopen → raise JuryLlmError → assert stderr 含 `△ [V1/` + `ERROR` + `<error_kind>`
  - `test_override_subsystem_flag_used` argparse 接受 flag → mock 跑 → assert effective_subsystem 字段 + 默认情况（no flag）effective = args.subsystem 不变
- **AC-6** 全套件：3194 baseline + 3 新测试 = **3197 PASS** / 0 regression
- **AC-7** CI 8/8 SUCCESS
- **AC-8** 发 v2.37.7 patch tag + GitHub Release

---

## 5. 风险与边界

| 风险 | 评估 | 缓解 |
|---|---|---|
| **try-success only 路径导致失败 view 静默**（layer 6 F1）| **中-高，改完反而更差**| **F1 fix：try-success + except-failure 双路径都加进度** |
| `args.subsystem` 字段语义破（既有 report reader 假设）| 中 | F2 fix：`subsystem` 字段保留 = args.subsystem；新 `effective_subsystem` 字段仅 override 时加 |
| `latency_ms` int → `latency_s` float 单位错 | 低 | F3 fix：明示 `latency_s = round(latency_ms / 1000, 1)` 计算 |
| 既有 stderr 重定向用户工作流破 | 低 | stderr 输出不影响 stdout 数据；既有 ✗ / △ 已有约定 |
| `--single-view` 内部路径影响 | 低 | spec §6 不变量 #5：single-view 短路 line 252 之前 return，不进 per-view 循环 |
| stderr 中文字符 Windows console 显示 | 低（v2.37.6 §11-N4 重新评估实证：jury 写 utf-8 字符串本身正确）| 进度行用 ASCII `△` + 英文字段名（model / photoreal / verdict / latency）避免 console cp936 mojibake 误判 |
| jury report `effective_subsystem` 字段破现有 reader | 低（v2.37.4 §13 forward-compat 允许加新字段）| 仅 override 时加；既有 reader 不读不破 |

---

## 6. 不变量

1. production code 改仅限：per-view 循环 try-success + except-failure 两处加 stderr 进度 + argparse 加 `--override-subsystem` flag + main() 计算 effective_subsystem + report 加 `effective_subsystem` 字段（仅 override 时）
2. jury Layer 0 / Layer 1 / Layer 2 算法逻辑不动
3. 既有 CLI flag 不动；新 flag default = None（不 override）
4. jury report `subsystem` 字段语义不变 = `args.subsystem`（F2 fix forward-compat）
5. `--single-view` 内部 CLI 路径不动（短路 line 252 之前 return）
6. 既有 `tools/jury/*.py` 不动
7. CLAUDE.md / 既有 docs / spec template 不动

---

## 7. 流程

```
brainstorming（本 spec）→ writing-plans → 5 task plan → execute
  ↓
Task 0 scout + baseline + 实测 per-view 循环 + argparse 位置
Task 1 §11-N3 TDD: per-view 进度 success + failure 双路径（RED → GREEN）
Task 2 §11-N2 TDD: --override-subsystem flag + effective_subsystem 计算（RED → GREEN）
Task 3 docs append（cad-jury-config 附录 A）+ commit
Task 4 retro 写 + commit
Task 5 PR + CI + 用户授权 merge + tag v2.37.7 + Release + memory
```

提交 4 commit：
1. `feat(jury): per-view 进度输出 stderr 单行 success+failure 双路径（§11-N3）`
2. `feat(jury): --override-subsystem alias flag + effective_subsystem 字段（§11-N2）`
3. `docs(jury-config): 附录 A 加 --override-subsystem flag 描述`
4. `docs(v2-37-7): retro 沉淀`

### 7.1 Rollback 流程

若发布后用户报"进度行干扰 / override 语义误导"：
- `git revert <v2.37.7 merge_sha>` 回退两 feat commit
- 发 v2.37.8 修
- GitHub Release UI 标 v2.37.7 "Pre-release"

---

## 8. Plan 调查步（plan 第 0 task 跑）

1. `cd D:/Work/cad-spec-gen && git status --short && git log --oneline -3` — baseline main@`184a7e1`（v2.37.6 merge）clean
2. `python scripts/dev_sync.py --check` rc=0
3. `pytest -q tests/jury/ tests/jury_loop/ 2>&1 | tail -3` — baseline 504 PASS（v2.37.6 后）
4. `pytest -q tests/jury/test_photo3d_jury_*.py 2>&1 | tail -3` — photo3d_jury 既有测试 baseline
5. `grep -nE "view_verdicts\.append" tools/photo3d_jury.py` — 实测 try-success + except-failure 两处 append 位置（spec D1 try ~620 / except ~644 snapshot 验证）
6. `sed -n '105,135p' tools/photo3d_jury.py` — 实测 _build_parser flag 顺序 + 新 flag 插入位置
7. `grep -nE '"subsystem":\s*args\.subsystem' tools/photo3d_jury.py` — 实测 report 写 subsystem 字段位置（line 687/745 snapshot）+ 改为 effective_subsystem 计算后 cross-check
8. `grep -nE "△|✗|✓" tools/photo3d_jury.py` — 实测既有 stderr 字符使用样本（spec D1 沿用风格 verify）

---

## 9. Plan 必 cover 项

- 每 commit 含 production + 测试同步（无 docs-only commit；feat 必含测试，spec §3.1+§3.2 双 TDD）
- baseline `dev_sync --check` rc=0（v2.37.3 R5 D2 教训）
- AC-4 grep `-cE` 显式 ERE（v2.37.4 layer 6 E4 教训）
- spec §3 D1 行号是 snapshot；Task 0 实测重定位（v2.37.4 layer 6 E10 教训）
- spec §3.1 D1 except 失败路径必加进度（F1 fix 不漏；防"改完反而更差"）
- Task 1+2 TDD 严格 RED→GREEN→REFACTOR（v2.37.6 §11-N5 实证 1 行 production 也走完整 TDD）

---

## 10. 不写代码 / 不进 plan 的事

- 不改 jury Layer 0 / Layer 1 / Layer 2 算法
- 不改 `tools/jury/*.py` 任何文件
- 不改既有 `--subsystem` / `--budget` 等 CLI flag 行为
- 不动 `--single-view` 内部 CLI 路径
- 不动 CLAUDE.md / 既有 docs / spec template
- 不开 §12 残 f1/f4 / §11-N1 rebrand 工具（留 batch 3）
- 不加 TTY progress bar（D1 stderr 单行更简单 + 跨 tty/pipe 兼容）

---

## 11. v2.37.x §11 + §12 follow-up 表（本 PR 闭合后）

| 项 | 严重度 | 内容 | 状态 |
|---|---|---|---|
| §12 F1/F2/f3/f5/f6 + f2 | LOW | v2.37.3-v2.37.6 closed | ✓ |
| §12 f1 | LOW | max_tokens sunset 条件 | 未闭合（batch 3）|
| §12 f4 | LOW | N≥50 批量场景成本评估 | 未闭合（batch 3）|
| §11-N1 | LOW | rebrand_test_archive.py | 未闭合（batch 3 dev 工具）|
| **§11-N2** | **LOW** | **photo3d-jury --override-subsystem** | **closed v2.37.7**（本 PR）|
| **§11-N3** | **LOW** | **photo3d-jury per-view 进度** | **closed v2.37.7**（本 PR）|
| §11-N4 | — | stderr mojibake | drop（v2.37.6 重新评估为非 bug）|
| §11-N5 | LOW | 估价表 gpt-image-* | closed v2.37.6 ✓ |

---

## 12. 本 PR 自身 follow-up

| # | 严重度 | 内容 | 触发条件 |
|---|---|---|---|
| h1 | LOW | per-view 进度加 retry 次数 / cost 累计字段 | 用户实测要求更详细进度信息 |
| h2 | LOW | TTY progress bar 升级（替换 stderr 单行）| ≥ 50% 用户报"7 行进度刷屏" |
| h3 | LOW | `--override-subsystem` 用例文档化进 jury-loop-config.md / cad-jury-config.md user guide | 用户多次问"如何跨项目跑 jury" |
