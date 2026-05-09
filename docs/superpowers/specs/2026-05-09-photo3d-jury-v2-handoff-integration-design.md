# photo3d-jury v2 — handoff 集成（A1 子集）设计文档

**作者**：proecheng
**日期**：2026-05-09
**状态**：spec 待审
**前置 spec**：`2026-05-08-photo3d-jury-design.md`（v2.27.0 已发布）
**关联 §**：2026-05-08-photo3d-jury-design.md §11"后续 (v2 路线)"中的 A 簇 A1 子集

---

## 修订历史

| 版本 | 日期 | 变更 |
|---|---|---|
| 1.0 | 2026-05-09 | 初稿（brainstorm 5 节 + 5 决策点收敛后落盘） |
| 1.1 | 2026-05-09 | spec 自审发现 2 处事实错误；修：(1) 复用 jury 已有 `--dry-run` flag 替代新加 `--cost-estimate-only`，jury 子模块零改动；(2) `jury_review_input.json` 路径走 subsystem + run_id 约定路径（不读 jury report 字段） |
| 1.2 | 2026-05-09 | 5 角色并行对抗审查（API / Edge / UX / Test / Security）合并 26 CRITICAL + 19 MAJOR：重写 §3.2 (orchestrator 在 `tools/photo3d_handoff.py:run_photo3d_handoff` 不在 cad_pipeline.py)；§3.3 命令归属 + command_return_code 接口扩展；§3.4 invariants 重写（jury blocked 走 status 字段 / dry-run 不取锁 / handoff 自加 .handoff.lock / path traversal 防御 / subprocess argv list / env 不注入 / stderr redact 透传 / PHOTO3D_HANDOFF.json 落盘契约）；§4.1 加 step 0 fail-fast jury config 预检；§4.2 决策表加 unexpected exit code / review_exit clamp；§5.1-5.3 错误矩阵 + redact 链；§6 测试用例 H1 加 golden snapshot / H16-H22 补 path traversal/损坏 review_input/unexpected exit/工具故障类 strict×双向；§9 race window 假设修正；§10 DoD cov source / platform split 显式 cite |
| 1.3 | 2026-05-09 | 第 3 层"代码-spec 对照实测"抓 5 大 BLOCKER（v1.0/v1.1/v1.2 共同的 brainstorm 事实错误，对抗审都没抓到）：(1) `format_stderr_message` 签名是 keyword-only `(*, exit_code, status, error_kind, context)`，分派维度三元组是 `(exit_code, status, error_kind)` 而非 spec 写的 `(exit_code, error_kind, context)`；内部是 if/elif 分支，不是 `_TEMPLATES` 字典；(2) autopilot `next_action` 字段是 `argv` list (+ 可选 `cli` string)，不是 `command` string；且 autopilot ready_for_enhancement 推荐 `enhance` subcommand 而非 `photo3d-handoff` — 整个 autopilot 集成基于错误前提，**v1.3 把 autopilot 文案变更全部移出范围**（推到独立 PR）；(3) `photo3d-handoff` cli 不是固定 5 步串联，是 `next_action.kind` driven dispatcher — jury 应嵌入 `_run_enhancement_followup` 在 enhance-check follow-up 之后；(4) 输出文件名是 `PHOTO3D_HANDOFF.json` 不是 `HANDOFF_RUN.json`；(5) PHOTO3D_HANDOFF.json 现有 `status` 字段命名冲突 — `handoff_status` 字段更名为 `jury_handoff_status` 与现有 `status` 字段共存（不同维度，前者是 jury 验收维度，后者是 handoff 执行阶段维度） |
| 1.4 | 2026-05-09 | 第 4 层"holistic dry-run + 常犯错误"4 角度并行审（Impl Dry-Run / 用户旅程 / State Lifecycle / TDD Fixture）合并 19 CRITICAL + 24 MAJOR：**新增 §6.0 fixture 与 fake 子进程模板**钉死 fake_run_factory + golden snapshot 来源 + review_input 三态工厂 + autouse kill switch 作用域 + @regression marker 划分；**§3.3 加函数签名钉死**（`_run_jury_followup` / `_validate_run_id_format` / `clamp_review_exit` 完整签名）+ argv token 完整模板 + subprocess timeout 钉死值（enhance=1800s / jury=600s / review=300s）+ creationflags；**§3.4 加 inv 16 (KeyboardInterrupt + SIGKILL Windows 路径) + inv 17 (active_run_id freeze 语义) + inv 18 (Windows .handoff.lock msvcrt.locking 实现细节) + inv 19 (subprocess 级联 kill 策略)**；**§4.1 加 step 4.0 既有 PHOTO3D_JURY_REPORT.json 归档 / step 5 read_text FileNotFoundError 归 corrupt**；**§4.2 决策表加 crashed_mid_orchestration 类目**；**§5.1 加 awaiting_confirmation_with_jury 类目**；**§5.2 13 个 error_kind 各自 context 字段表 + minimal jury config 示例 + lock age 查看命令 + 强制清 lock 动作 + 账单来源 / 修 enhance config 入口**；**§7.2 schema 兼容性 .get() 默认 None 指引**；**§7.4 README 示例钉死**（首跑预览 + 加 --confirm 实跑双行）；**§8 拆 C6 jury 实跑 13 用例为 C6a-C6e 5 段**；**§10 DoD 加 cov source explicit list**（`tools.photo3d_handoff.run_jury_followup` 等子模块） |
| 1.5 | 2026-05-09 | §11 follow-up M-1 + M-2 closed by v2.30.0：(1) §4.2 决策表 `crashed_mid_orchestration` exit 由"透传 OS 信号原值"修正为 99（与 internal_error 同段；KeyboardInterrupt 走 Python 默认 130 路径不进 command_return_code）+ 加注释说明；(2) §4.2 决策表 `review_failed` exit 加注释说明 review_raw_exit 缺时 fallback 20（review_failed clamp 段最低位；不与 review_input_corrupt 23 撞码）+ 实现 `command_return_code` line 247 改 fallback 23→20 + 加 2 测试守门 |

---

## 1. 背景与北极星对齐

### 1.1 v2.27.0 后用户体验断点

`photo3d-jury` 作为独立 cli 已上线，能自动给出 5 项语义判定 + photoreal_score。但用户的实际工作流是：

```
photo3d-handoff --confirm        # 跑 enhance + enhance-check（已自动 follow-up）
↓ 用户复制粘贴下一步命令
photo3d-jury --subsystem ...     # 手动跑 jury
↓ 用户看 jury accepted 后再复制粘贴
enhance-review --review-input .../jury_review_input.json  # 手动转正式契约
↓ 然后才能 deliver
photo3d-deliver --subsystem ...
```

**断点**：3 步本可一条命令解决。外行用户被强迫记 3 个命令名 + 2 次复制粘贴 + 1 个文件路径。

### 1.2 北极星 5 gate 对齐

| Gate | 本 PR 提升点 |
|---|---|
| 零配置 | jury config 沿用 v1 不变；新 flag `--with-jury` 复用现有 jury config |
| 稳定可靠 | 默认 strict（verdict ≠ accepted 阻断 handoff），降低用户漏看风险 |
| 结果准确 | jury → enhance-review 串联保证 deliver 前必有正式 ENHANCEMENT_REVIEW_REPORT.json |
| SW 装即用 | 无影响（jury 不涉 SW） |
| 傻瓜式操作 | 一条 `photo3d-handoff --with-jury --confirm` 跑完 enhance + check + jury + review |

### 1.3 已收敛决策点（brainstorm session 摘要）

- **范围**：仅 handoff 路径集成 jury（方案 ①）；autopilot v1.3 第 3 层审查发现当前 ready_for_enhancement 推荐 enhance 不推荐 handoff，**集成移出本 PR 范围**，推到 A1.1 独立 PR
- **strict 默认**：jury verdict ≠ accepted → handoff exit≠0；`--no-strict-jury` 反向 opt-out
- **cost 确认**：`--with-jury` 隐含 `--confirm-cost`；handoff 在 jury 跑前 stderr 强制打印估价 + budget 检查；超 budget 仍 exit=3 abort
- **enhance-review 归属**：orchestrator 层（即 handoff 自身）负责，accepted 后调 `enhance-review` subcommand；jury 子模块不动
- **strict/no-strict 边界**：仅 jury **业务质量**类（preview / needs_review）可被 no-strict 降级为警告；jury **工具自身故障**类（lock busy / config 错 / blocked / internal）必须阻断，no-strict 覆盖不了

---

## 2. 范围与非目标

### 2.1 范围（in-scope）

1. `photo3d-handoff` 加 `--with-jury` `--no-strict-jury` 两个 flag（在 `cad_pipeline.py` 子解析器层注册；解析后由 orchestrator 主体接收）
2. **orchestrator 主体改在 `tools/photo3d_handoff.py:run_photo3d_handoff`**：jury hook 嵌入 `_run_enhancement_followup`，在现有 `_execute_enhance_check_followup` 之后新增 `_run_jury_followup`（仅 `with_jury=True` 时触发）；handoff 主体 22 行薄壳保持不变
3. `tools/photo3d_handoff.py:command_return_code` 接口签名 `(report: dict[str, Any]) -> int` **保持不变**；扩展点：当 `report` 含新加 `jury_handoff_status` 字段时按 §4.2 决策表映射到新 exit code 段；现有 `status ∈ {awaiting_confirmation, executed, executed_with_followup, execution_failed, needs_manual_review}` 0/1 映射保持不变
4. **jury 嵌入点**：仅当 next_action.kind == "run_enhancement" + `--with-jury` 启用时触发；其他 next_action.kind（如 `accept_baseline` / `confirm_action_plan`）不影响
5. `photo3d-handoff --with-jury` 在 `_run_enhancement_followup` 内串联 5 步（**step 0 fail-fast jury 预检** → enhance（已由 `_execute_selected_action` 跑过）→ enhance-check（已由 `_execute_enhance_check_followup` 跑过）→ step 3 jury --dry-run 估价 → step 4 jury 实跑 → step 5 enhance-review）
6. **`tools/photo3d_jury.py` 不动**：复用 jury v1 已有的 `--dry-run` flag（已存在于 v2.27.0）；行为详细见 §3.3 表 + invariant 6
7. `PHOTO3D_HANDOFF.json` schema add-only 加六字段（`jury_handoff_status` / `jury_status` / `jury_estimated_usd` / `jury_actual_usd` / `review_status` / `enhance_review_path`）；**字段名钉死**；现有 `status` 字段（值 awaiting_confirmation 等）共存不动
8. 中文 stderr 文案模板集中在 `tools/jury/stderr_messages.py` 现有 `format_stderr_message(*, exit_code, status, error_kind, context)` keyword-only 签名 / 三元组 `(exit_code, status, error_kind)` 分派 / if/elif 内部分支（**复用现有结构而非新增字典或 string-key 分派**）；新增 13 个 `handoff_*` error_kind
9. 文档：`docs/cad-jury-config.md` 加"通过 photo3d-handoff 一条命令跑闭环"章节
10. 全量测试覆盖（单元 + handoff e2e）；含 H16-H22 新增对抗用例（path traversal / 损坏 review_input / unexpected exit code / 工具故障类 strict×no-strict 双向 / config 缺失 fail-fast）
11. **handoff 自身互斥锁**：handoff 在 jury hook 之前（即 enhance-check follow-up 完成后）acquire `<run_dir>/.handoff.lock`（与 jury `.jury.lock` 不同文件、不同生命周期）覆盖 jury hook 全程，防同机并发跑两次 handoff
12. **README 文档示例追加**：README.md 用法示例追加"`photo3d-handoff --with-jury --confirm` 一条命令跑闭环"段（不改默认推荐）

### 2.2 移出范围（pushed to next PR）

- ❌ `cad_pipeline.py:cmd_photo3d_autopilot` 改 next_action 推荐 `--with-jury` —— **v1.3 移出范围**：autopilot 当前 `ready_for_enhancement` 状态推荐的是 `enhance` subcommand（`next_action.kind == "run_enhancement"`，argv = `["python", "cad_pipeline.py", "enhance", ...]`），**不推荐 photo3d-handoff**；`enhance` 不识别 `--with-jury`，加上去会 argparse 错。autopilot 行为重设计需要新增"已跑 enhance 但未跑 handoff"的中间状态分支，超出本 PR 用户体验集成范围；推到 A1.1 独立 PR
- ❌ autopilot 集成相关测试（`tests/test_cad_pipeline_autopilot.py` next_action 含 jury cmd 用例）—— v1.3 同步移出

### 2.3 非目标（out-of-scope；推到独立 PR）

- `photo3d-autopilot --with-jury` 端到端化（autopilot 升级为真正 orchestrator）— 属于 spec §11 方案 ②，本 PR 不做
- `photo3d-jury --summary` 跨 run 聚合视图 — 属于 A2 簇
- `photo3d-jury --json` 机器友好输出 — 属于 A2 簇
- `photo3d-recover` 注册 jury 文件 — 属于 A2 簇
- jury 子模块的 4 层判定逻辑改造（`fallback_profile_ids` chain / `anthropic_native` kind / quota tracker 等）— 属于 B/C/D/E 簇
- jury 自身加 `--auto-review` flag — 已决策由 orchestrator 串联，jury 自身不动

### 2.4 非目标的兼容性承诺

- jury v1 cli 行为**完全不变**（本 PR 不动 jury 子模块任何代码；handoff 复用 v1 已有的 `--dry-run` flag）
- 独立用户跑 `photo3d-jury` 仍按 v1 流程（不会"突然多跑 enhance-review"）
- `PHOTO3D_HANDOFF.json` 现有字段不动；新加字段在不带 `--with-jury` 时**不出现**（不污染回归用户的报告）

---

## 3. 架构

### 3.1 上下文图

```
┌─ 用户视角 ────────────────────────────────────────┐
│ 一条命令：                                          │
│   cad_pipeline.py photo3d-handoff \                │
│     --subsystem <name> --with-jury [--no-strict-jury] --confirm                       │
└────────────────────┬───────────────────────────────┘
                     ↓
┌─ handoff orchestrator (cad_pipeline.py) ──────────┐
│  1. enhance        (现有 cli call)                 │
│  2. enhance-check  (现有 follow-up)                │
│  3. jury --dry-run  (复用 v1 已有 flag, 估价 + budget 检查)  │
│     → stderr 打印估价 + budget 检查                 │
│  4. jury  (jury v1 4 层主流程, --confirm-cost 内传) │
│     → 等 PHOTO3D_JURY_REPORT.json 落盘             │
│     → 读 jury_report.status 决策                    │
│  5. enhance-review (仅 accepted 才调)              │
│     → 写 ENHANCEMENT_REVIEW_REPORT.json            │
│  6. 写 PHOTO3D_HANDOFF.json 终态                        │
└─────────────────────────────────────────────────┘

┌─ photo3d-autopilot (本 PR 不改) ──────────────────┐
│  v1.3 第 3 层审查发现 autopilot 当前 ready_for_     │
│  enhancement 状态推荐的是 enhance 命令（不是         │
│  photo3d-handoff），加 --with-jury 不通顺；          │
│  autopilot 集成移出本 PR 范围，推到 A1.1 独立 PR     │
└─────────────────────────────────────────────────┘
```

### 3.2 文件布局

```
cad_pipeline.py                       ← cmd_photo3d_handoff parser add-only 加 --with-jury / --no-strict-jury（~25 行）；
                                       cmd_photo3d_autopilot 不动（v1.3 移出范围）
tools/photo3d_handoff.py              ← run_photo3d_handoff add-only 接受 with_jury / no_strict_jury 关键字参数（~10 行）
                                       _run_enhancement_followup 扩展加 jury hook（~30 行）
                                       新加 _run_jury_followup helper（~150 行）+ _validate_run_id_format helper（~10 行）
                                       + clamp_review_exit helper（~10 行）
                                       command_return_code 扩展（~30 行）
tools/jury/stderr_messages.py          ← format_stderr_message 内 if/elif 分支 add-only 加 13 个 handoff_* error_kind（~80 行；
                                       签名 `(*, exit_code, status="", error_kind="", context)` 不动）
docs/cad-jury-config.md                ← 新增"handoff 一条闭环"章节（~40 行）
docs/PROGRESS.md                       ← 加 v2.28.0 入口（~5 行）
README.md                              ← 用法示例追加 --with-jury 推荐（~10 行）
tests/test_photo3d_handoff_with_jury.py（新文件，~600 行；含 H1-H23 共 27 用例 含 H7/8/9/11 双向）
tests/jury/test_stderr_messages.py     ← 加 handoff_* error_kind 模板覆盖测试（~50 行）

注：
- `tools/photo3d_jury.py` 与其他 jury 子模块文件 0 改动；handoff 复用 jury v1 已有的 `--dry-run` flag
- `tools/photo3d_autopilot.py` 不动（v1.3 第 3 层审查发现 autopilot ready_for_enhancement 推荐 enhance 不推荐 handoff，集成推到独立 PR）
- `tests/test_cad_pipeline_autopilot.py` 不改（v1.3 同步移出）
```

### 3.3 模块契约

| 模块 / 函数 | 单一职责 | 输入 | 输出 | 不做 |
|---|---|---|---|---|
| `cad_pipeline.py:cmd_photo3d_handoff`（薄壳，仅加 parser 注册） | argparse 子解析器加 `--with-jury` `--no-strict-jury`；args 透传 `tools/photo3d_handoff.py:run_photo3d_handoff` | argv | run_photo3d_handoff 返回值 | 不实现 orchestrator |
| `tools/photo3d_handoff.py:run_photo3d_handoff`（主改动） | orchestrator：6 步串联（含 step 0 fail-fast）、读 jury report status 字段判定 / 透传 jury exit、决定 strict 行为、写 PHOTO3D_HANDOFF.json 终态、acquire `.handoff.lock` | args + project_root | report dict | 不实现 jury 业务逻辑；不动 enhance/check 已有逻辑；不直接 import jury 模块函数 |
| `tools/photo3d_handoff.py:command_return_code`（扩展） | 把 report 终态映射到 exit code；现有签名 `(report: dict[str, Any]) -> int` 不变；扩展点：当 `report` 含新加 `jury_handoff_status` 字段时按 §4.2 决策表映射；现有 `status ∈ {awaiting_confirmation, executed, executed_with_followup, execution_failed, needs_manual_review}` 0/1 映射保持不变 | report dict（含新 jury_status / jury_handoff_status 字段） | exit code ∈ {0, 1, 2, 3, 4, 10, 11, 12, 13, 20, 21, 22, 23, 24, 25, 99} | 不做副作用 |
| `tools/photo3d_jury.py`（不动） | jury v1 已有 `--dry-run` flag（v2.27.0 落地）：跑 Layer 0（不取 `.jury.lock`）+ Layer 1 deterministic_gate + cost gate 后 print + return；**Layer 2 才 acquire `.jury.lock`** | argv | exit code（0 = 估价 ok 或 jury 内部 fail soft / 1 = layer0 blocking / 2 = config 错 / 3 = over budget；其他 exit 由 jury v1 已有路径决定） | 本 PR 不改 jury 子模块任何代码 |
| `tools/jury/stderr_messages.py:format_stderr_message`（add-only 扩展） | 复用现有 keyword-only 签名 `(*, exit_code: int, status: str = "", error_kind: str = "", context: dict[str, Any]) -> str`；分派维度三元组是 **(exit_code, status, error_kind)**；内部是 if/elif 分支（**不是 _TEMPLATES 字典**）；本 PR 在该函数加 if 分支处理 `error_kind ∈ {handoff_jury_preview, handoff_jury_needs_review, handoff_jury_blocked, handoff_jury_lock_busy, handoff_jury_internal_error, handoff_jury_config_error, handoff_jury_cost_over_budget, handoff_review_failed, handoff_review_input_missing, handoff_review_input_corrupt, handoff_unexpected_jury_exit, handoff_handoff_lock_busy, handoff_jury_preflight_config_missing}`（13 个新 error_kind） | exit_code + status + error_kind + context dict (keyword-only) | 单字符串（无 `{xxx}` 残留；输出前由调用方过 `redact.py:redact_traceback_str`） | 不做 IO；纯 string format；**不引入新签名 / 不创建并行的 string-key 分派函数** |
| `cmd_photo3d_autopilot`（**v1.3 不动**） | autopilot 行为完全保持现状；本 PR 不改 | n/a | n/a | n/a |

#### 3.3.1 新加 helper 函数签名钉死（v1.4）

防 plan subagent 各自猜函数签名导致 plan-drift：

```python
# tools/photo3d_handoff.py 模块顶部 add-only

import subprocess
import re
from pathlib import Path
from typing import Any

# 常量（module-level；不通过 env / config 覆盖）
HANDOFF_LOCK_STALE_SECONDS: int = 1800       # .handoff.lock 30 分钟自动清理
SUBPROCESS_TIMEOUT_ENHANCE: int = 1800       # enhance 子进程 30 分钟超时
SUBPROCESS_TIMEOUT_JURY: int = 600           # jury 子进程 10 分钟超时（含 LLM API hang 兜底）
SUBPROCESS_TIMEOUT_REVIEW: int = 300         # enhance-review 子进程 5 分钟超时（本地处理）
RUN_ID_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


def validate_run_id_format(run_id: str) -> bool:
    """returns True iff run_id matches RUN_ID_PATTERN; never raises."""
    return bool(RUN_ID_PATTERN.fullmatch(run_id))


def clamp_review_exit(review_raw_exit: int) -> int:
    """clamp enhance-review 子进程 exit code 到 handoff exit 段，防与 handoff 自身段撞码。
    映射：0→0 / 1→20 / 2→21 / 3→22 / 其他→23"""
    if review_raw_exit == 0:
        return 0
    if review_raw_exit == 1:
        return 20
    if review_raw_exit == 2:
        return 21
    if review_raw_exit == 3:
        return 22
    return 23


def _run_jury_followup(
    *,
    project_root: Path,
    subsystem: str,
    active_run_id: str,
    cad_pipeline_py: Path,
    no_strict_jury: bool,
) -> dict[str, Any]:
    """jury hook 主流程；在 _run_enhancement_followup 内部调用。
    返回 dict 含 jury_handoff_status / jury_status / jury_estimated_usd / jury_actual_usd /
    review_status / enhance_review_path / jury_raw_exit / review_raw_exit 字段。
    本函数自身不抛业务异常；KeyboardInterrupt / OSError 等 BaseException 透传给调用方 finally 块处理。
    """
    ...
```

#### 3.3.2 subprocess argv 完整模板（v1.4）

handoff 调子进程 argv list 模板钉死：

```python
# step 3 jury --dry-run（与 step 4 实跑共用 argv 模板，仅最后多/少 --dry-run）
argv_jury_dry_run: list[str] = [
    sys.executable, str(cad_pipeline_py),
    "jury",
    "--subsystem", subsystem,
    "--dry-run",
    "--budget", str(budget_per_run_usd),    # 来自用户 args 或 jury config 默认（本 PR 沿用 jury v1 默认）
    # --profile-id 不传：让 jury 走 config active 选取（jury v1 默认行为）
]

# step 4 jury 实跑
argv_jury_real: list[str] = [
    sys.executable, str(cad_pipeline_py),
    "jury",
    "--subsystem", subsystem,
    "--confirm-cost",                       # --with-jury 隐含 --confirm-cost
    "--budget", str(budget_per_run_usd),
]

# step 5 enhance-review
argv_review: list[str] = [
    sys.executable, str(cad_pipeline_py),
    "enhance-review",
    "--subsystem", subsystem,
    "--review-input", str(review_input_path),
]

# 所有 subprocess.run 调用统一形式
result = subprocess.run(
    argv,
    shell=False,
    capture_output=True,
    text=True,
    encoding="utf-8",
    timeout=SUBPROCESS_TIMEOUT_<KIND>,
    env=os.environ.copy(),                  # 不主动注入凭据（invariant 3）
    creationflags=0,                        # Windows 不创建 new process group；让 Ctrl-C 正常级联到子进程
)
```

注：step 1 enhance / step 2 enhance-check 的 argv 复用 `tools/photo3d_handoff.py` 现有 `_trusted_argv()` helper（v2.27.0 已有；本 PR 不改）。

#### 3.3.3 timeout 触发后处理

`subprocess.TimeoutExpired` 异常归 handoff_unexpected_jury_exit 类目（exit=25），与 jury return ∈ {130, 137, 其他} 同一处理路径；不单独占新 exit code 段。

### 3.4 不变量

1. **autopilot 完全不动**（v1.3 修正 v1.2 错判）：本 PR 不改 `tools/photo3d_autopilot.py` 任何代码；不改 next_action 字段；autopilot ready_for_enhancement 状态推荐 enhance 命令（next_action.argv = `["python", "cad_pipeline.py", "enhance", ...]`）的现状保持。autopilot 集成推到 A1.1 独立 PR（需先重设计 autopilot 增加"已 enhance 未 handoff"的中间状态）
2. **jury 子模块边界不动**：`tools/jury/{config,cost,llm_client,verdict,redact,deterministic_gate,input_evidence_binding}.py` 与 `tools/photo3d_jury.py` 全部 0 改动；只在 `tools/jury/stderr_messages.py` 的 `format_stderr_message` 函数 add-only 扩展 `error_kind` 枚举支持 `handoff_*` 前缀（不引入并行的 string-key 分派接口）
3. **handoff 调子进程方式**：必须用 `subprocess.run([sys.executable, str(cad_pipeline_py_path), subcommand, *args], shell=False, ...)` argv list 形式（**禁止字符串拼接 + shell=True**，防 Windows cmd `&` `|` `^` 等元字符注入）；**禁止**直接 import jury 模块函数（避免 cli 副作用泄漏）；**子进程 env 不注入任何凭据**：`subprocess.run(env=os.environ.copy())` 即可，handoff 自己不读 / 不传 jury api_key / 不复制任何 `OPENAI_API_KEY` 等敏感环境变量
4. **`PHOTO3D_HANDOFF.json` 落盘契约（v1.4 加强）**：
   - 路径 = `<project_root>/cad/<subsystem>/.cad-spec-gen/runs/<frozen_active_run_id>/PHOTO3D_HANDOFF.json`（详见 invariant 17 freeze 语义）
   - 写入走 `tools/contract_io.py:write_json_atomic(path, data) -> Path`（**实测签名 2 参数**）+ `tools/path_policy.py:assert_within_project(path, project_root, "PHOTO3D_HANDOFF")` 三参数全填（继承 jury v1 invariant 4）
   - schema add-only：现有字段集严格保持；新加字段（`jury_handoff_status` / `jury_status` / `jury_estimated_usd` / `jury_actual_usd` / `review_status` / `enhance_review_path` / `jury_raw_exit` / `review_raw_exit`）**仅在** `--with-jury` 启用时出现；不带 flag 时 H1 golden snapshot 守门
   - **partial state 字段允许 null 表**（v1.4 钉死）：
     - 必填非 null：`jury_handoff_status`（崩溃时填 `crashed_mid_orchestration`），`jury_status`（崩溃时填 `crashed`），`jury_estimated_usd`（崩溃前未估则 `0.0`）
     - 允许 null：`jury_actual_usd` / `review_status` / `enhance_review_path` / `jury_raw_exit` / `review_raw_exit`
   - **永远写**：handoff 主体用 outer `try: ... finally: write_json_atomic(...)` 包裹 step 0-6 全程；finally 块内 `try/except OSError: pass` 防 finally 二次抛；详见 invariant 16
5. **strict/no-strict 边界硬约束**：
   - 业务质量类（jury report `status ∈ {preview, needs_review}`）：strict → exit=10/11 abort；no-strict → exit=0 + warning
   - 工具故障类（jury report `status == "blocked"` / handoff 检测的 `JuryLockBusy` / `JuryConfigError` / `JuryInternalError` / unexpected jury exit / handoff 自身 `.handoff.lock` busy）：**永远阻断**，no-strict 不能覆盖
   - 工具故障类的"永远阻断"必须 H7/H8/H9/H11 + 对应 `--no-strict-jury` 变体（H7b/H8b/H9b/H11b）双向用例守门
6. **dry-run 行为校正（v1.2 修正 v1.1 错判）**：jury v1 现有 `--dry-run` 实际行为（grep 实证 `tools/photo3d_jury.py` 行 95/236/248）：跑 Layer 0 input_evidence_binding（**不取 `.jury.lock`**——`.jury.lock` 在 Layer 2 取，dry-run 在 cost gate 之前 return 不触达）+ Layer 1 deterministic_gate + cost gate 后 stdout `[dry-run] estimated=X.XX USD, allowed=Y` + return 0/3；**dry-run 不写 `PHOTO3D_JURY_REPORT.json`**；handoff step 3 与 step 4 之间没有"自己锁释放后被抢"的 race（dry-run 根本不取锁）；**handoff 自身 `.handoff.lock` 在 step 0 之前 acquire** 覆盖 step 0-6 全程，防同机并发跑两次 handoff
7. **jury return 0 但 status="blocked" 判定**：jury 实跑遇 freeze drift 时**写 `PHOTO3D_JURY_REPORT.json` `status="blocked"` 后 return 0**（非 exit≠0）；handoff 必须**先读 PHOTO3D_JURY_REPORT.json `status` 字段** 再决定 jury_status，**不能仅靠 exit code 判定**；exit code 与 status 字段的判定优先级：(a) exit code ∈ {2, 4, 99}（jury 自己已 fail-fast 写 stderr）→ 直接透传不读 report；(b) exit code ∈ {0, 1, 3} → 读 report `status` 字段；(c) exit code 为其他值（130 / 137 / SIGTERM / 等 unexpected）→ 归 `unexpected_jury_exit`，exit=25 阻断
8. **estimated_usd 单源打印**：jury 实跑会打印估价；handoff dry-run 也会触发 jury 自己打印（jury stdout `[dry-run] ...`）；handoff **不**自行重复打印估价，**只**在 dry-run 失败（exit=3 budget 超）时输出中文人话提示。用户最多看到 jury 自打的英文一行 + handoff 中文一行（含错误处置建议），不重复
9. **enhance-review 失败不污染 jury 报告**：`PHOTO3D_JURY_REPORT.json` 保持 jury 自己写完时的内容；handoff 把 review 失败记到 `PHOTO3D_HANDOFF.json` 自己的字段（review_status / enhance_review_path）
10. **jury_review_input.json 路径走约定 + path traversal 防御**：
    - handoff 通过 `subsystem`（自身 args）+ jury report 的 `run_id` 字段构造路径
    - **run_id 字段格式校验**（防 path traversal）：必须 `re.fullmatch(r"^[A-Za-z0-9_\-]+$", run_id)`；不匹配 → exit=13 `handoff_review_input_missing` 子类目 `run_id_format`
    - 路径 = `<project_root>/cad/<subsystem>/.cad-spec-gen/runs/<run_id>/jury_review_input.json`
    - 构造后立即 `tools/path_policy.py:assert_within_project(path, project_root, "jury_review_input")` 三参数全填（防 subsystem 含 `..` 越界）
    - 再 `Path.exists()` 校验 + `Path.is_file()` 校验
    - **禁止扫目录猜文件**（北极星硬约束）
    - 缺路径报 `handoff_review_input_missing`，文件损坏（非合法 JSON）报 `handoff_review_input_corrupt` 子类目；测试用例 H15 / H16 / H17 守门
11. **subprocess 调用契约**：
    - 必须 `subprocess.run([list], shell=False, capture_output=True, text=True, timeout=...)`
    - **subsystem / run_id / profile_id / budget 等用户可控值**必须作为 argv list 元素，**不允许** f-string / `+` / `%s` 拼成单字符串
    - 测试用例必须 assert `monkeypatch.setattr("subprocess.run", fake)` 接收的第一个位置参数是 `list[str]` 且 `shell` 关键字 ∉ kwargs 或 `shell=False`
12. **stderr 透传 redact 链**：
    - handoff 透传 jury / enhance / enhance-review 子进程 stderr 前必走 `tools/jury/redact.py:redact_traceback_str` + `redact_body`（jury v1 invariant 5 兜底沿用）
    - handoff 自身 stderr 文案常量必须固定，禁止动态 `f"... {api_key} ..."` 模板（即使变量名不叫 api_key 也禁）
    - HANDOFF stderr 模板**仅显示** profile_id（不显示 model / base_url / api_key），防 model 名意外含敏感前缀
13. **encoding 强制（沿用 jury v1 invariant 12）**：handoff 所有文件 IO 必传 `encoding="utf-8"`；`json.dumps(..., ensure_ascii=False, indent=2)` 中文不转义
14. **`.handoff.lock` 生命周期**：
    - 路径 = `<project_root>/cad/<subsystem>/.cad-spec-gen/runs/<active_run_id>/.handoff.lock`
    - 用 `tools/_file_lock.py`（jury v1 设计沿用；若 v1 没抽出则本 PR 不抽，handoff 直接复用 jury `.jury.lock` 同机制写另一文件）
    - try/finally 释放；stale lock 自动清理：mtime > 30 min 或 PID 不在系统 → 下次 cli 自动覆盖 + stderr 警告
    - acquire 失败 → exit=24 `handoff_handoff_lock_busy`
15. **add-only schema 兼容性宪章（沿用 jury v1 invariant 14）**：本 PR add-only 加字段不需升 `PHOTO3D_HANDOFF.json` `schema_version`；只有删字段、改字段语义、改字段类型才需升

16. **KeyboardInterrupt / SIGTERM / SIGKILL 路径钉死（v1.4 新增）**：
    - 顶层 `try/finally` 用 `try: ... finally: ...`（**不带 except** — 让所有异常含 KeyboardInterrupt / BaseException 子类正常向外传播；finally 块仍跑）
    - `KeyboardInterrupt`（继承 BaseException）→ finally 块跑 PHOTO3D_HANDOFF.json 落盘 + 释放 .handoff.lock；finally 块内 `try/except OSError: pass` 包裹文件 IO 防 finally 二次抛异常盖原 KeyboardInterrupt
    - SIGTERM（Windows 等价 TerminateProcess 由用户 Task Manager 触发）→ Python 不会跑 finally（SIGTERM 在 POSIX 默认杀进程；Windows TerminateProcess 类似），spec 不假设 finally 一定跑；下游靠 stale .handoff.lock 30 min 自动清理兜底
    - SIGKILL（POSIX kill -9 / Windows TerminateProcess）→ 不可拦；spec 不假设 finally 跑；同 stale lock 兜底
    - finally 块内 `jury_handoff_status` 默认值 = `"crashed_mid_orchestration"`（决策表 §4.2 新加类目）；现有 `status` 字段 = `"execution_failed"`（沿用 v2.27.0 既有路径）

17. **active_run_id freeze 语义钉死**：handoff 主体 step 0 时刻读 `ARTIFACT_INDEX.json` `active_run_id` 字段后赋值给 Python 局部变量 `frozen_active_run_id`；后续所有 step 0-7 内部用此局部变量，**不重读 `ARTIFACT_INDEX.json`**；不写入磁盘 freeze 副本；jury 子进程会自己重新 freeze 一次，handoff 不与 jury freeze 互校（race 由 jury 自己的 sha drift 检测兜底）

18. **Windows-only `.handoff.lock` 实现细节**：
    - 复用 `tools/_file_lock.py:acquire_lock(lock_path)` context manager（jury v1 已实证；plan task 0 grep 守门）
    - 锁文件内容：JSON `{"pid": int, "started_at": ISO 8601 UTC}`；stale 清理时读 PID 用 `tools/_file_lock.py:_pid_alive` 校验
    - 锁文件路径 = `<project_root>/cad/<subsystem>/.cad-spec-gen/runs/<frozen_active_run_id>/.handoff.lock`
    - `tools/_file_lock.py` 内部：Windows 用 `msvcrt.locking(LK_NBLCK)` 非阻塞锁（已抽出为通用接口，jury v1 与本 PR handoff 复用）；POSIX 用 `fcntl.flock(LOCK_EX | LOCK_NB)`（CI Linux job 用，但项目北极星 Windows-only — Linux 仅为 mock 测试服务）
    - acquire 失败立即抛 `tools._file_lock:LockBusy`；handoff 顶层 try/except 捕到后报 exit=24

19. **subprocess 级联 kill 与 timeout 处理**：
    - `subprocess.run(creationflags=0)`（Windows 不创建独立 process group；Ctrl-C 正常级联到子进程）
    - `subprocess.TimeoutExpired` 异常 → handoff_unexpected_jury_exit（exit=25）+ stderr 模板 `handoff_unexpected_jury_exit` `context["raw_exit"]="timeout"`
    - jury 子进程被外部 kill 残留 `.jury.lock` → 由 jury v1 invariant 11 stale lock 30 min 自动清理兜底；handoff 不主动 kill jury 子进程

---

## 4. 数据流

### 4.1 完整流程

**关键修正（v1.3）**：handoff 不是"5 步固定串联 cli"，是 **next_action.kind driven dispatcher** + follow-up 嵌入模型。jury hook 仅在 `next_action.kind == "run_enhancement"` 且 `--with-jury` 启用时触发。

```
photo3d-handoff --confirm --with-jury [--no-strict-jury]
        │
        ▼ (现有流程保持不变)
读 PHOTO3D_RUN.json / PHOTO3D_AUTOPILOT.json 的 next_action
        │
        ▼
_classify_next_action → selected_action（kind ∈ {run_enhancement, accept_baseline, confirm_action_plan, ...}）
        │
        ▼
[现有逻辑] 若 kind != run_enhancement：按既有路径处理；--with-jury 不影响（H-NJ 用例守门）
        │
        ▼ kind == "run_enhancement" + --confirm
_execute_selected_action 跑 enhance subprocess（enhance 失败 → status="execution_failed" 现有路径）
        │ enhance returncode == 0
        ▼
_run_enhancement_followup 入口
        │
        ▼
[现有] _execute_enhance_check_followup 跑 enhance-check（失败 → 透传现有路径）
        │ ok
        ▼
————————— 以下是本 PR jury hook 嵌入点 —————————

step J0 acquire <run_dir>/.handoff.lock（防同机并发；with_jury=False 时跳过此 step）
   ──acquire 失败──▶ jury_handoff_status="handoff_lock_busy" exit=24

step J0.5 fail-fast jury 配置预检
   调 `python cad_pipeline.py jury --dry-run --subsystem <s> --profile-id <p>`（jury 自身会走 config 加载 + Layer 0）
   ──jury return ∈ {1, 2}（layer0/config 错）──▶ jury_handoff_status="preflight_config_missing" exit=2
   ──jury return == 0──▶ continue (估价已得，但 jury 此时只到 Layer 0 + cost gate 之前；为避免重跑 dry-run 浪费 IO，
                          v1.3 决策：J0.5 与 step 3 dry-run 合并为同一次调用，本调用既做预检又做估价)

step 3 jury --dry-run（实际就是 J0.5 的同一次调用）
   stdout: "[dry-run] estimated=0.04 USD, allowed=True"  (jury 自打)
   ──jury return 3 (cost over budget)──▶ jury_handoff_status="cost_over_budget" exit=3
                                        + jury_estimated_usd 字段
                                        + stderr 中文提示
   ──jury return ∈ {1, 2}──▶ 透传 jury exit；jury_handoff_status="config_error" 或 "blocked"
   ──jury return ∈ {130, 137, 其他}──▶ jury_handoff_status="unexpected_jury_exit" exit=25
        ▼
step 4 jury 实跑（jury return 0 后才走；handoff 显式传 `--confirm-cost`；jury Layer 2 取 `.jury.lock`）
   等 PHOTO3D_JURY_REPORT.json 落盘
   优先级判定（invariant 7）：
   (a) jury exit ∈ {2, 4, 99}                  → 透传 exit；不读 report
   (b) jury exit ∈ {0, 1, 3}                   → 读 PHOTO3D_JURY_REPORT.json 的 status 字段
   (c) jury exit ∈ {130, 137, 其他 unexpected} → exit=25 handoff_unexpected_jury_exit
   ┌─────────────────────────────────────────────────────────────────────────┐
   │ jury exit │ jury status (若读)  │ strict           │ no-strict          │
   ├─────────────────────────────────────────────────────────────────────────┤
   │ 0         │ accepted            │ → step 5         │ → step 5           │
   │ 0         │ preview             │ → exit=10        │ → warning + exit=0 │
   │ 0         │ needs_review        │ → exit=11        │ → warning + exit=0 │
   │ 0         │ blocked (sha drift) │ → exit=12（**no-strict 不覆盖**）   │
   │ 1         │ (layer0 blocking)   │ → exit=12（同 blocked 类目）        │
   │ 2         │ (config 错)         │ → exit=2 透传（**永远阻断**）       │
   │ 3         │ (cost gate)         │ → exit=3 透传 不应该到 step 4     │
   │ 4         │ (lock busy)         │ → exit=4 透传（**永远阻断**）       │
   │ 99        │ (internal)          │ → exit=99 透传（**永远阻断**）      │
   │ 其他       │ -                   │ → exit=25 unexpected_jury_exit     │
   └─────────────────────────────────────────────────────────────────────────┘
        │ accepted（jury_status:"accepted"）
        ▼
step 5 enhance-review subprocess
   路径构造（invariant 10）：
     校验 jury report run_id 字段格式 `^[A-Za-z0-9_\-]+$`
     review_input_path = <project_root>/cad/<subsystem>/.cad-spec-gen/runs/<run_id>/jury_review_input.json
     assert_within_project(review_input_path, project_root, "jury_review_input")
     校验 .exists() + .is_file()
     校验 json.loads(read_text(encoding="utf-8")) 不抛
   ──run_id 格式不合法──▶ exit=13 handoff_review_input_missing("run_id_format")
   ──path 不存在──▶ exit=13 handoff_review_input_missing("not_found")
   ──path 在 project root 之外──▶ exit=13 handoff_review_input_missing("path_traversal")
   ──读取 / JSON 解析失败──▶ exit=23 handoff_review_input_corrupt
   ──enhance-review 子进程 fail──▶ exit=clamp_review_exit(review_exit)
                                  + PHOTO3D_HANDOFF.json{review_status:"failed", review_raw_exit:N}
        │ ok（review_status:"ok"）
        ▼
step 6 写 PHOTO3D_HANDOFF.json 终态（add-only 字段，与现有 status 字段共存）
   现有字段（保持不变）：schema_version / generated_at / run_id / subsystem / source / source_report
                       / confirmed / status / ordinary_user_message / selected_action
                       / manual_action / executed_action / followup_action
                       / post_handoff_photo3d_run / artifacts
   新加字段（仅 --with-jury 启用时出现）：
   {
     jury_handoff_status: "accepted" | "preview_warning" | "review_failed" | ... ,
     jury_status: str,                        # jury 报告的 status，或 handoff 自己的工具故障类目
     jury_estimated_usd: float,
     jury_actual_usd: float | null,           # 字段名钉死，不带 _or_null 后缀
     review_status: str,                      # ok | failed | input_missing | input_corrupt
     enhance_review_path: str | null,
     jury_raw_exit: int | null,               # 仅 jury_status="unexpected_exit" 时非 null
     review_raw_exit: int | null,             # review 失败时记原始 exit
   }
        │
        ▼
step 7 release `.handoff.lock`（finally 块；whether or not with_jury，with_jury=False 时本 step 之前 step 不取锁也无须释放）

clamp_review_exit:
  review_exit ∈ {0}      → 0
  review_exit ∈ {1}      → 20  (handoff_review_failed)
  review_exit ∈ {2}      → 21  (clamp 防与 handoff exit=2 撞码)
  review_exit ∈ {3}      → 22
  review_exit ∈ 其他      → 23  (透传含义模糊归 corrupt 类目；仍记 review_raw_exit)
```

### 4.2 jury 实跑后 jury_handoff_status 决策表

注：`jury_handoff_status` 是 PHOTO3D_HANDOFF.json 新增字段（仅 `--with-jury` 启用时出现），与现有 `status` 字段（值 awaiting_confirmation/executed/executed_with_followup/execution_failed/needs_manual_review，handoff 执行阶段维度）**共存不冲突**。

| jury_status | strict | review_status | jury_handoff_status | exit |
|---|---|---|---|---|
| accepted | * | ok | accepted | 0 |
| accepted | * | failed | review_failed | clamp_review_exit(review_raw) |
| accepted | * | input_missing | review_input_missing | 13 |
| accepted | * | input_corrupt | review_input_corrupt | 23 |
| preview | strict | n/a (skip) | preview_blocked_by_strict | 10 |
| preview | no-strict | n/a (skip) | preview_warning | 0 |
| needs_review | strict | n/a (skip) | needs_review_blocked_by_strict | 11 |
| needs_review | no-strict | n/a (skip) | needs_review_warning | 0 |
| blocked | * | n/a (skip) | jury_blocked | 12 |
| cost_over_budget | * | n/a (skip) | cost_over_budget | 3 |
| config_error | * | n/a (skip) | config_error | 2 |
| lock_busy | * | n/a (skip) | lock_busy | 4 |
| internal_error | * | n/a (skip) | internal_error | 99 |
| unexpected_exit | * | n/a (skip) | unexpected_jury_exit | 25 |
| (handoff 自身) | * | n/a (skip) | handoff_lock_busy | 24 |
| (handoff preflight) | * | n/a (skip) | preflight_config_missing | 2 |
| (handoff 崩溃 mid-step) | * | n/a (skip) | crashed_mid_orchestration | 99（与 internal_error 同段；详见下注释；v2.30.0 §11 M-1 修正）|
| (handoff awaiting_confirm) | * | n/a (skip) | awaiting_confirmation | 0（沿用现有 status 字段路径）|

**jury_handoff_status 字段值钉死**：上表 `jury_handoff_status` 列字符串值是契约；测试 H1-H23 必须 assert PHOTO3D_HANDOFF.json 写出的 `jury_handoff_status` 字符串与表完全一致（防拼写错如 `config_err` vs `config_error`）。

**crashed_mid_orchestration exit code 注释（v2.30.0 §11 M-1 修订）**：
- `KeyboardInterrupt`（用户 Ctrl-C）→ Python 不调 `command_return_code`，进程默认 exit=130
- `SIGTERM` / `SIGKILL` → 进程被强制终止，不调 `command_return_code`
- 其他主流程没崩但 jury hook 留 partial state（如 finally 块写完报告后 main 流程仍正常 return）→ `command_return_code` 看 `jury_handoff_status="crashed_mid_orchestration"` → 返 99（与 `internal_error` 同段）
- 故 spec rev 1.4 "透传 OS 信号原值" 在 v1.5 修订为 99（实现现状对齐；signal 透传由 Python 自然路径处理，不经过 `command_return_code`）

**review_failed exit code 注释（v2.30.0 §11 M-2 修订）**：
- `review_raw_exit` 是 int → `clamp_review_exit` 映射（0→0 / 1→20 / 2→21 / 3→22 / 其他→23）
- `review_raw_exit` 缺 / 非 int → fallback 20（review_failed clamp 段最低位；不与 `review_input_corrupt` 23 撞码）
- 测试守门：`test_command_return_code_review_failed_with_missing_raw_returns_20` / `test_command_return_code_review_failed_with_non_int_raw_returns_20`

### 4.3 不带 --with-jury 的回归路径

- handoff 行为完全等同 v2.27.0：跑 enhance + enhance-check follow-up，写 `PHOTO3D_HANDOFF.json` 不含 jury 字段
- 测试用例必须显式 assert 不带 `--with-jury` 时 `PHOTO3D_HANDOFF.json` 字段集与现有 schema 完全一致

---

## 5. 错误处理

### 5.1 异常分类与 exit code

| 类目 | exit | strict 可降级 | stderr error_kind |
|---|---|---|---|
| enhance 自身失败 | 透传 enhance | n/a | (沿用现有) |
| enhance-check 失败 | 透传 check | n/a | (沿用现有) |
| handoff preflight: jury config 缺失 | 2 | ✗ | `handoff_jury_preflight_config_missing` |
| handoff 自身 lock busy | 24 | ✗ | `handoff_handoff_lock_busy` |
| jury config 错 | 2 | ✗ | `handoff_jury_config_error` |
| jury cost 超 budget | 3 | ✗ | `handoff_jury_cost_over_budget` |
| jury lock busy | 4 | ✗ | `handoff_jury_lock_busy` |
| jury preview | 10 / 0 | ✓ | `handoff_jury_preview` (context["mode"]="strict"/"warning") |
| jury needs_review | 11 / 0 | ✓ | `handoff_jury_needs_review` (context["mode"]="strict"/"warning") |
| jury blocked | 12 | ✗ | `handoff_jury_blocked` |
| jury internal | 99 | ✗ | `handoff_jury_internal_error` |
| jury unexpected exit (130/137/其他) | 25 | ✗ | `handoff_unexpected_jury_exit` (context["raw_exit"]=N) |
| enhance-review 失败（review_raw=1） | 20 | n/a | `handoff_review_failed` |
| enhance-review 失败（review_raw=2） | 21 | n/a | `handoff_review_failed` |
| enhance-review 失败（review_raw=3） | 22 | n/a | `handoff_review_failed` |
| enhance-review 子进程其他异常 | 23 | n/a | `handoff_review_input_corrupt` |
| review_input 路径缺失（含 path traversal） | 13 | n/a | `handoff_review_input_missing` (context["reason"]∈{"not_found", "run_id_format", "path_traversal"}) |
| handoff awaiting_confirmation 但启用 --with-jury | 0 | n/a | `handoff_awaiting_confirmation_with_jury` (旅程 A step 2 卡点修复) |
| handoff crashed mid-step | 透传信号 | n/a | (无独立 stderr 模板；finally 块仅落盘 PHOTO3D_HANDOFF.json) |

**POSIX 兼容性脚注**：handoff exit code 段（10/11/12/13/20/21/22/23/24/25）属于业务自定义码，不与 POSIX 保留段（126 / 127 / 128+N 信号）冲突；CI 配置 retry-on-exit 时需显式排除 10-25 段，否则会误重试用户操作错误。

### 5.2 stderr 模板示例（中文人话；外行用户可操作）

模板在 `tools/jury/stderr_messages.py:format_stderr_message` 函数内 if/elif 分支 add-only 加入（**不是 `_TEMPLATES` 字典 — 现有实现是 if/elif 分支**）。新加 13 个 `error_kind` 处理分支，按 `(exit_code, error_kind)` 选模板字符串后 `.format(**context)` 填充：

```python
# (exit_code, "handoff_jury_preview", mode="strict")
"jury 判定 preview（5 项语义检查中 {failed_n} 项 false 或 photoreal_score={score} 低于 min_photoreal_score={min_score}）。\n"
"  jury 报告：{report_path}\n"
"  ① 改善：检查 enhance 输出是否清晰；调整 enhance config；或换 provider preset\n"
"  ② 跳过：加 --no-strict-jury 仅警告（但结果不会进入 deliver；需手动跑 enhance-review）"

# (exit_code, "handoff_jury_blocked")
"jury 检测到输入证据漂移（active_run_id 或 sha256 不一致）。\n"
"  这是工具自身故障，--no-strict-jury 也不会跳过。\n"
"  ① 重跑：cad_pipeline.py photo3d-handoff --with-jury --confirm 重新走一遍\n"
"  ② 检查：是否其他工具/脚本同时改 ARTIFACT_INDEX.json（CI 多 worker / 双窗口）"

# (exit_code, "handoff_jury_lock_busy")
"jury 被另一 photo3d-jury 进程持锁（lock 文件 mtime={lock_mtime_minutes_ago} 分钟前）。\n"
"  ① 等待：其他 jury 进程结束（一次跑 ~30s）；30 分钟无响应自动清理\n"
"  ② 主动放弃：本次 handoff 退出；不会破坏数据；可稍后重跑\n"
"  ③ 紧急清理（仅在确认无其他 photo3d-jury 进程时）：删 {lock_path} 后重跑"
# 注：不要求外行用户用 Task Manager / ps 查 PID；超 30 分钟自动清理已托底

# (exit_code, "handoff_handoff_lock_busy")
"另一个 photo3d-handoff 进程正在跑同 subsystem（lock mtime={lock_mtime_minutes_ago} 分钟前）。\n"
"  请等当前进程结束（约 5-15 分钟，含 enhance + jury + review）；\n"
"  ③ 紧急清理（仅在确认无其他 photo3d-handoff 进程时）：删 {lock_path} 后重跑"

# (exit_code, "handoff_jury_preflight_config_missing")
"jury 配置缺失或格式错（路径：{config_path}）。\n"
"  最小配置示例（写到 ~/.claude/cad_jury_config.json）：\n"
'    {{"profiles": [{{"id": "default", "kind": "openai_compat", "api_base_url": "https://api.openai.com", "api_key": "sk-...", "model": "gpt-4o", "cost_per_call_usd": 0.01}}], "active_profile_id": "default", "budget_per_run_usd": 0.50}}\n'
"  详细参数（含中转商 base_url / TLS CA）见 docs/cad-jury-config.md。\n"
"  注：jury 估价产生的 USD 费用计入此 api_key 对应 LLM 服务商账单。\n"
"  本次 handoff 已立即退出，未跑 enhance（不浪费 LLM 额度）"

# (exit_code, "handoff_review_input_missing")
"jury 判定 accepted 但 enhance-review 输入缺失（{reason}）。\n"
"  原因 {reason}：not_found = 文件不存在；run_id_format = jury 写的 run_id 含非法字符；path_traversal = 路径越界\n"
"  这是 bug，请提 issue 并附 PHOTO3D_JURY_REPORT.json"

# (exit_code, "handoff_unexpected_jury_exit")
"jury 进程异常退出（exit code = {raw_exit}）。\n"
"  常见原因：被 Ctrl-C 打断（130） / OOM kill（137） / 系统 SIGTERM\n"
"  ① 重跑 handoff；② 若反复出现，看 jury stderr 详细输出（已脱敏）"
```

**外行用户优先**：所有模板必须给"下一步动作"清单，禁止只描述错误现象不给出路。

#### 5.2.1 每个 error_kind 的 context 字段表（v1.4 钉死）

防 plan subagent 各自猜 context dict 字段集导致 KeyError 或 placeholder 残留：

| error_kind | exit_code | context 必填字段 |
|---|---|---|
| `handoff_jury_preview` | 10 / 0 | `failed_n: int`, `score: int`, `min_score: int`, `report_path: str`, `mode: "strict"\|"warning"` |
| `handoff_jury_needs_review` | 11 / 0 | `failed_views: list[str]`, `vendor_request_id: str\|None`, `report_path: str`, `mode: "strict"\|"warning"` |
| `handoff_jury_blocked` | 12 | `report_path: str` |
| `handoff_jury_lock_busy` | 4 | `lock_mtime_minutes_ago: int`, `lock_path: str` |
| `handoff_jury_internal_error` | 99 | `redacted_traceback: str` |
| `handoff_jury_config_error` | 2 | `config_path: str` |
| `handoff_jury_cost_over_budget` | 3 | `estimated_usd: float`, `budget_usd: float`, `n_views: int` |
| `handoff_review_failed` | 20/21/22 | `review_raw_exit: int`, `report_path: str` |
| `handoff_review_input_missing` | 13 | `review_input_path: str`, `reason: "not_found"\|"run_id_format"\|"path_traversal"` |
| `handoff_review_input_corrupt` | 23 | `review_input_path: str`, `parse_error: str` |
| `handoff_unexpected_jury_exit` | 25 | `raw_exit: int\|"timeout"` |
| `handoff_handoff_lock_busy` | 24 | `lock_mtime_minutes_ago: int`, `lock_path: str` |
| `handoff_jury_preflight_config_missing` | 2 | `config_path: str` |
| `handoff_awaiting_confirmation_with_jury` | 0 | `argv_with_confirm: str` (建议命令字符串) |

#### 5.2.2 awaiting_confirmation_with_jury 模板（v1.4 加；旅程 A step 2 卡点修复）

```python
# (exit_code=0, error_kind="handoff_awaiting_confirmation_with_jury")
"已找到可交接的下一步（含 jury 验收 + enhance-review 闭环）；预览模式不执行。\n"
"  下一步：加 --confirm 重跑：\n"
"    {argv_with_confirm}\n"
"  或不带 --with-jury 走简化路径（仅 enhance + check 不跑 jury）"
```

### 5.3 集中处理位置 + redact 链

- **唯一入口**：`tools/jury/stderr_messages.py:format_stderr_message(*, exit_code, status, error_kind, context)`（**keyword-only 签名**；沿用 jury v1 三元组 `(exit_code, status, error_kind)` 分派接口；本 PR 不引入并行函数）
- **handoff 调用方**：`tools/photo3d_handoff.py:run_photo3d_handoff` 在每个失败分支唯一通过 `format_stderr_message(exit_code=N, status=..., error_kind="handoff_...", context={...})` 取字符串后写 stderr；从 `tools/jury/redact.py:redact_traceback_str` 兜底过一次再写
- **子进程 stderr 透传**：handoff 不直接 `print(subprocess.stderr.decode())`；必须先 `redact_traceback_str(subprocess.stderr)` 后再 stderr 写。**仅 traceback 类内容走 redact**：jury 自打的 `[dry-run] estimated=X.XX USD, allowed=Y` 之类业务输出不需 redact（redact_traceback_str 仅处理含 `Bearer`/`api_key=`/`Cookie` 等 traceback 行；业务输出未命中 pattern 透传不变）；子进程 stdout 同理
- **stderr 模板内容限制**：context 字典的 value 仅允许 profile_id / run_id / 文件路径（已 path_policy 校验过的项目内路径）/ 数值（cost / view 数）/ 整数 exit code；**禁止** model 名 / base_url / 任意 api_key prefix / 任何环境变量值
- **禁止**：handoff 自己拼字符串、handoff 自己保留 string-key 文案常量、并行 string-key 分派函数；所有 `handoff_*` error_kind 模板都必须落在 `format_stderr_message` 函数内 if/elif 分支中（**不是** `_TEMPLATES` 字典 — 该字典在 v2.27.0 实现里不存在）

---

## 6. 测试策略

### 6.0 fixture 与 fake 子进程模板（v1.4 新增；plan 阶段必走）

为防 plan task subagent 各自猜 fixture/mock 致 plan-drift，本节钉死所有共享 fixture 与 mock pattern。

#### 6.0.1 fake_run_factory（mock subprocess.run 按调用顺序 dispatch）

`tests/test_photo3d_handoff_with_jury.py` 内部定义并复用：

```python
import subprocess
from pathlib import Path
from typing import Any, Callable
import pytest


@pytest.fixture
def fake_run_factory(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """按调用顺序 dispatch fake subprocess.run 行为；
    behaviors 列表对应 5 次预期调用：
      0: enhance / 1: enhance-check / 2: jury --dry-run / 3: jury 实跑 / 4: enhance-review
    """
    def _install(behaviors: list[subprocess.CompletedProcess[str] | Callable[..., subprocess.CompletedProcess[str]]]) -> Callable[..., subprocess.CompletedProcess[str]]:
        call_log: list[dict[str, Any]] = []
        idx = [0]

        def fake_run(argv: list[str], *, shell: bool = False, capture_output: bool = True, text: bool = True, timeout: int | None = None, env: dict[str, str] | None = None, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            assert isinstance(argv, list), "subprocess.run must be argv list (invariant 11)"
            assert shell is False, "subprocess.run shell=False (invariant 11)"
            assert "OPENAI_API_KEY" not in (env or {}), "handoff must not actively inject api_key (invariant 3)"
            call_log.append({"argv": argv, "shell": shell, "env": env, "timeout": timeout})
            current = idx[0]
            idx[0] += 1
            assert current < len(behaviors), f"unexpected subprocess.run call #{current}"
            entry = behaviors[current]
            return entry(argv) if callable(entry) else entry

        fake_run.call_log = call_log  # type: ignore[attr-defined]
        monkeypatch.setattr("tools.photo3d_handoff.subprocess.run", fake_run)
        return fake_run

    return _install
```

每用例必须 `assert fake_run.call_count == N`（N = 该用例预期调用数；防早退假绿）。

#### 6.0.2 golden snapshot 来源 + 比对方式

- **fixture 文件**：`tests/fixtures/photo3d_handoff_v2_27_0.json` —— plan task 0 必须 git checkout v2.27.0 tag → 跑一次 lifting_platform / end_effector subsystem photo3d-handoff → 取实际产出 → normalize 浮点 + 时间戳后落盘
- **比对函数**：双重断言
  ```python
  # 1. keyset 严格相等（防字段增删）
  assert set(actual.keys()) == set(golden.keys())
  # 2. 字段值（时间戳/浮点 normalize 后）排序后 JSON 全等
  def normalize(d: dict) -> dict:
      out = dict(d)
      out.pop("generated_at", None)  # 时间戳 ignore
      return out
  assert json.dumps(normalize(actual), sort_keys=True) == json.dumps(normalize(golden), sort_keys=True)
  ```

#### 6.0.3 review_input 三态工厂

```python
@pytest.fixture
def make_jury_run_dir(tmp_path: Path) -> Callable[..., Path]:
    def _factory(*, run_id: str = "20260509-123456", review_input_state: str = "ok",
                 subsystem: str = "lifting_platform") -> Path:
        run_dir = tmp_path / "cad" / subsystem / ".cad-spec-gen" / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "PHOTO3D_JURY_REPORT.json").write_text(
            json.dumps({"schema_version": 1, "subsystem": subsystem, "run_id": run_id, "status": "accepted"}),
            encoding="utf-8",
        )
        if review_input_state == "ok":
            (run_dir / "jury_review_input.json").write_text(json.dumps({"schema_version": 1, "views": []}), encoding="utf-8")
        elif review_input_state == "missing":
            pass  # 不写
        elif review_input_state == "corrupt":
            (run_dir / "jury_review_input.json").write_bytes(b"{not json")
        elif review_input_state == "traversal":
            (run_dir / "PHOTO3D_JURY_REPORT.json").write_text(
                json.dumps({"schema_version": 1, "subsystem": subsystem, "run_id": "../etc/passwd", "status": "accepted"}),
                encoding="utf-8",
            )
        else:
            raise ValueError(f"unknown review_input_state: {review_input_state}")
        return run_dir
    return _factory
```

#### 6.0.4 fake_enhancement_report 字段集（最小可跑）

plan task 0 必须 grep `tools/jury/input_evidence_binding.py` 与 `tools/jury/cost.py` 实证字段消费。当前最小猜测（plan task 0 校准）：

```python
@pytest.fixture
def fake_enhancement_report() -> dict[str, Any]:
    """ENHANCEMENT_REPORT.json 最小可被 jury Layer 0 + cost.py 接受的字段集"""
    return {
        "schema_version": 1,
        "subsystem": "lifting_platform",
        "run_id": "20260509-123456",
        "delivery_status": "accepted",
        "quality_summary": {},
        "views": [
            {"view": f"view{i}", "enhanced_image": f"img{i}.jpg", "edge_similarity": 0.9}
            for i in range(4)
        ],
    }
```

**plan task 0 强制 grep 守门**：若 jury 真实字段消费比这更广，plan task 0 必须先扩 fixture 再开始 C1。

#### 6.0.5 autouse kill switch 作用域

`tests/jury/conftest.py` 现有 autouse `_disable_llm_by_default` 作用域为 `tests/jury/` 子树；本 PR 测试在 `tests/test_photo3d_handoff_with_jury.py` 顶层。**决策**：

- 本 PR 测试**全 mock subprocess**，不会真起 LLM 子进程；不依赖 jury kill switch
- 但 plan 必须在新测试文件**顶部** module-scope `pytest.fixture(autouse=True)` 复制等价 monkeypatch（`monkeypatch.setenv("CAD_JURY_DISABLE_LLM", "1")`）作为额外安全阀

#### 6.0.6 RED 节奏豁免标注

不所有 §6 用例都能 RED→GREEN 走完：

| 用例类目 | RED→GREEN 走法 | 标注 |
|---|---|---|
| H1/H1b/H1c golden snapshot | 必须 mutation sanity check：先故意改一行实现 → 测试 fail → 还原 → PASS | `@pytest.mark.regression` |
| H22 subprocess argv 守门 | 同上 | `@pytest.mark.regression` |
| §6.2 stderr 模板单测 | 同上 | `@pytest.mark.regression` |
| H2-H21 / H23 实质用例 | 标准 RED→GREEN → REFACTOR | (无 marker) |

#### 6.0.7 helper 模块归属 + import path

`clamp_review_exit` / `validate_run_id_format` 是**模块顶级 public 函数**（不带下划线），定义在 `tools/photo3d_handoff.py`：

```python
from tools.photo3d_handoff import clamp_review_exit, validate_run_id_format
```

私有 helper（如 `_run_jury_followup`）保留下划线前缀；测试不直接 import 私有 helper，通过 `run_photo3d_handoff` 顶层入口测。

#### 6.0.8 H7a/H7b 等双向用例形式

钉死：**独立 function** 而非 parametrize。命名 `test_h7a_jury_blocked_strict` / `test_h7b_jury_blocked_no_strict` 等。理由：每个 test id 与 §10 DoD 用例计数一对一。

---

### 6.1 TDD 铁律

每节落 commit 必须先写失败测试再实现。CLAUDE.md 强制：
- RED：先写测试 + 跑确认失败
- GREEN：写最小实现让测试 PASS
- REFACTOR：清理冗余 + 不增多余逻辑

### 6.2 单元测试

| 测试文件 | 用例 | 预期 |
|---|---|---|
| `tests/jury/test_stderr_messages.py` | `test_handoff_error_kinds_no_unfilled_placeholders` | 13 个 `handoff_*` error_kind 在 `format_stderr_message(exit_code=..., error_kind=...)` 输出无 `{xxx}` 残留（用合法 context fixture 调每个 error_kind） |
| `tests/jury/test_stderr_messages.py` | `test_handoff_error_kinds_dispatch_complete` | 用每个 `handoff_*` error_kind 调 `format_stderr_message`，输出非空且不命中 fallback `f"✗ ...（{error_kind}）..."` 兜底分支 |
| `tests/jury/test_stderr_messages.py` | `test_handoff_templates_no_secret_leakage` | grep `format_stderr_message` 函数源码（`inspect.getsource`），不含 `api_key` `base_url` `model` 字面量字符串作为模板 placeholder |
| `tests/test_photo3d_handoff_with_jury.py` | `test_clamp_review_exit_mapping` | clamp_review_exit(0)→0, (1)→20, (2)→21, (3)→22, (其他)→23 |
| `tests/test_photo3d_handoff_with_jury.py` | `test_validate_run_id_format_rejects_traversal` | `validate_run_id("../etc/passwd")` 返 False；`validate_run_id("20260509-123456")` 返 True |

注：jury `--dry-run` flag 已存在 v2.27.0，本 PR plan task 0 必须先 grep 确认现有单测路径与覆盖范围（不假设）。

### 6.3 handoff 集成测试

新文件：`tests/test_photo3d_handoff_with_jury.py`（~600 行）

**mock 策略（钉死防假绿）**：
- patch target 必须是 `tools.photo3d_handoff.subprocess.run`（不是 `subprocess.run` 全局）
- fake 函数签名：`def fake_run(argv, *, shell=False, capture_output=True, text=True, timeout=None, env=None, **kw) -> CompletedProcess`
- **每个用例必须 assert 至少一次**：`argv` 是 `list[str]` 且第 0 元素 == `sys.executable` 且第 1 元素以 "cad_pipeline.py" 结尾
- **每个用例必须 assert**：`shell` 关键字未传入 / 或为 False
- **每个用例必须 assert**：`env` 不含 `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` 等敏感键（继承的不算 handoff 主动注入）
- fixture `fake_enhancement_report` 在 tmp_path 写 `ENHANCEMENT_REPORT.json` 含 `views: [{}, {}, {}, {}]`（n_views=4）；H14 估价测试依赖
- fixture `fake_jury_report_<status>` 在 tmp_path 的 jury run_dir 写 `PHOTO3D_JURY_REPORT.json` 各种 status；H2-H7 用

| 用例编号 | 场景 | 预期 | 守门 invariant |
|---|---|---|---|
| H1 | 不带 --with-jury（回归 + golden snapshot） | exit=0/1（按现有 status 映射）+ PHOTO3D_HANDOFF.json 字段 keyset 与 v2.27.0 基线 snapshot 完全一致（fixture 存 `tests/fixtures/photo3d_handoff_v2_27_0.json`）；不出现 `jury_*` 字段 | inv 4 add-only |
| H1b | --with-jury 但 next_action.kind == "accept_baseline" | jury hook 不触发；exit + 字段集与 v2.27.0 现有路径完全一致；不出现 `jury_*` 字段 | inv 1（jury 嵌入点限制） |
| H1c | --with-jury 但 confirm=False（preview 模式 awaiting_confirmation） | jury hook 不触发；exit + 字段集与现有 awaiting_confirmation 路径一致；不出现 `jury_*` 字段 | inv 1 |
| H2 | --with-jury jury accepted + review ok (jury exit=0 status="accepted") | exit=0 + jury_handoff_status="accepted" + jury_actual_usd 字段是 float | inv 4/7 |
| H3 | --with-jury jury preview + strict | exit=10 + jury_handoff_status="preview_blocked_by_strict" + 不调 review + stderr 含 handoff_jury_preview 模板渲染文本 | inv 5 业务降级 |
| H4 | --with-jury --no-strict-jury jury preview | exit=0 + jury_handoff_status="preview_warning" + 不调 review | inv 5 业务降级 |
| H5 | --with-jury jury needs_review + strict | exit=11 + 不调 review | inv 5 |
| H6 | --with-jury --no-strict-jury jury needs_review | exit=0 + warning + 不调 review | inv 5 |
| H7a | --with-jury jury blocked + strict | exit=12 + jury_handoff_status="jury_blocked" + 不调 review | inv 5 工具故障 |
| H7b | --with-jury **--no-strict-jury** jury blocked | exit=12（**no-strict 不覆盖**）+ 不调 review | inv 5 双向 |
| H8a | --with-jury jury lock busy (jury exit=4) | exit=4 透传 + 不调 review | inv 5 |
| H8b | --with-jury **--no-strict-jury** jury lock busy | exit=4 透传（**no-strict 不覆盖**） | inv 5 双向 |
| H9a | --with-jury jury config 错 (jury exit=2) | exit=2 透传 + 不调 review | inv 5 |
| H9b | --with-jury **--no-strict-jury** jury config 错 | exit=2 透传（**no-strict 不覆盖**） | inv 5 双向 |
| H10 | --with-jury jury cost over budget (dry-run jury exit=3) | exit=3 + jury_handoff_status="cost_over_budget" + jury_estimated_usd 字段 + 不调 review；**enhance 已跑过**（dry-run 在 step 3 不在 step 0） | inv 6 / inv 8 |
| H11a | --with-jury jury internal (exit=99) | exit=99 透传 + 不调 review | inv 5 |
| H11b | --with-jury **--no-strict-jury** jury internal | exit=99 透传（**no-strict 不覆盖**） | inv 5 双向 |
| H12 | --with-jury jury accepted + review 失败 (review exit=1) | exit=20 (clamp) + jury_handoff_status="review_failed" + review_raw_exit=1 字段 | inv 8 review_exit clamp |
| H13 | enhance step 失败 (enhance exit=1) | exit=1 透传 + 不调 jury（PHOTO3D_HANDOFF.json 仅 enhance_status="failed"） | inv 4 |
| H14 | --with-jury jury exit=3 时 stderr 含中文估价文案 | H10 同测；stderr 含 "jury 预估 X.XX USD" + budget 字符串 | inv 8 |
| H15 | --with-jury accepted + review_input 约定路径不存在 | exit=13 + jury_handoff_status="review_input_missing" + reason="not_found" | inv 10 |
| H16 | --with-jury accepted + jury report run_id="../etc/passwd" | exit=13 + reason="run_id_format" + 不调 review | inv 10 path traversal |
| H17 | --with-jury accepted + jury_review_input.json 是损坏 JSON | exit=23 + jury_handoff_status="review_input_corrupt" + 不调 review | inv 10 |
| H18 | --with-jury jury 进程 SIGINT (exit=130) | exit=25 + jury_handoff_status="unexpected_jury_exit" + jury_raw_exit=130 + 不调 review | inv 7 |
| H19 | --with-jury jury 进程 OOM (exit=137) | exit=25 + jury_raw_exit=137 | inv 7 |
| H20 | --with-jury fail-fast jury config 缺失 | exit=2 + jury_handoff_status="preflight_config_missing" + **不调 enhance**（防 enhance 白花钱） | step 0.5 |
| H21 | --with-jury 同 subsystem 已有 handoff 在跑 (`.handoff.lock` busy) | exit=24 + jury_handoff_status="handoff_lock_busy" + 不调 enhance | inv 14 |
| H22 | --with-jury subprocess argv 形式 | fake_run.call_args_list 每次第 0 位置参数 isinstance(list) + shell ∉ kwargs + env 不主动注入敏感键 | inv 3/11 |
| H23 | --with-jury crash mid-step（mock enhance 抛 OSError） | PHOTO3D_HANDOFF.json 仍写出（finally 块），enhance_status="crashed" | inv 4 永远写 |

### 6.4 autopilot 测试（v1.3 移出本 PR）

autopilot 集成 v1.3 移出范围（§2.2）；本 PR 不加 autopilot 测试用例；推到 A1.1 独立 PR。

仅保留**回归守门**（在现有 `tests/test_cad_pipeline_autopilot.py` 内本 PR 不动；CI 全量跑确认 autopilot 行为未受 handoff 改动牵连）。

### 6.5 不写的测试（YAGNI 边界）

- 不测真实 LLM 调用：沿用 jury v1 conftest autouse kill switch（`tests/jury/conftest.py`）
- 不测真实 enhance/render：handoff 测试全 mock 子进程
- 不测 jury v1 已覆盖的 4 层判定逻辑：本 PR 不动那部分

### 6.6 CI 矩阵

- Linux + Windows 都跑（subprocess mock 在两平台行为一致）
- mypy strict 必过：本 PR 改的 `tools/photo3d_handoff.py` / `tools/jury/stderr_messages.py` / `cad_pipeline.py` 保持 strict（不降级；jury v1 已上 mypy strict CI gate）
- ruff check + format 必过
- coverage：
  - **cov source explicit list**：`--cov=tools.photo3d_handoff --cov=tools.jury.stderr_messages`（不依赖默认 `--cov` source 自动发现）
  - **platform split**：Linux job 与 Windows job 分别 explicit 列 cov source（沿用 memory `feedback_ci_cov_gate_platform_split`：requires_solidworks 模块 Linux 全 SKIP 拖死 gate 教训；本 PR 模块均 platform-agnostic 但仍按规范分列）
  - 阈值：本 PR 新加路径 ≥90% 覆盖；测量命令 `uv run pytest tests/test_photo3d_handoff_with_jury.py tests/jury/test_stderr_messages.py --cov=tools.photo3d_handoff --cov=tools.jury.stderr_messages --cov-fail-under=90`

---

## 7. 兼容性与迁移

### 7.1 cli 层

- 不带 `--with-jury` 跑 `photo3d-handoff`：行为完全等同 v2.27.0；H1 用例守门
- jury v1 独立用户跑 `photo3d-jury`：行为完全等同 v2.27.0（本 PR 不改 jury 任何代码）

### 7.2 报告 schema + 消费方读取契约（v1.4 加）

- `PHOTO3D_HANDOFF.json`：add-only 加 8 字段（详见 invariant 4）；`schema_version` 不升（按 jury v1 invariant 14 add-only 兼容性宪章）
- `PHOTO3D_JURY_REPORT.json`：完全不变（jury 子模块 0 改）
- `ENHANCEMENT_REVIEW_REPORT.json`：完全不变（enhance-review 子命令不变；handoff step 5 跑半失败留 partial 文件由 photo3d-deliver 现有路径处理，本 PR 不接管）

**消费方读取契约（CI / 脚本 / 下游）**：
- 读 `jury_*` 字段必须用 `dict.get("...", default)` 模式，**禁止** `report["jury_..."]` 直接索引（不带 `--with-jury` 时字段不存在；带 flag 时崩溃前可能为 null）
- 推荐读法示例：`if report.get("jury_handoff_status") == "accepted": ...`
- handoff exit code 段（10/11/12/13/20/21/22/23/24/25）属业务自定义码；CI 配置 retry-on-exit 时**显式排除** 10-25 段，否则误重试用户操作错误

### 7.3 配置

- `~/.claude/cad_jury_config.json`：完全不变（v1 配置直接可用）
- 不引入新环境变量
- 不引入新的 `~/.claude/` 文件

### 7.4 文档迁移（v1.4 钉死 README 示例）

- `docs/cad-jury-config.md` 加新章节"通过 photo3d-handoff 一条命令跑闭环"，必含：
  - 双行示例（首跑预览 + 加 --confirm 实跑）
  - `--with-jury` `--no-strict-jury` flag 矩阵（4 组合行为表）
  - "故障恢复"段：lock 残留判断 + 强制清理动作
  - "CI 集成"段：GitHub Actions / Bash trap 两段配置示例钉死 exit 10-25 段排除
  - "jury preview 时常见可改 enhance config 入口"段
- `docs/PROGRESS.md` 加 v2.28.0 入口
- `README.md` 用法示例追加（最小改动；钉死示例文本）：

```markdown
### 一条命令跑完 photo3d 验收闭环（v2.28.0+）

# 第一步：预览（不执行；看下一步要跑什么）
python cad_pipeline.py photo3d-handoff --subsystem lifting_platform --with-jury

# 第二步：加 --confirm 实跑（触发 enhance + check + jury 自动验收 + enhance-review）
python cad_pipeline.py photo3d-handoff --subsystem lifting_platform --with-jury --confirm

# 进阶：质量验收 preview 时仅警告不阻断（CI 用）
python cad_pipeline.py photo3d-handoff --subsystem lifting_platform --with-jury --no-strict-jury --confirm
```

---

## 8. 实施顺序（plan 阶段拆分预想）

预估 plan 阶段会拆 ~14-16 task。粗顺序：

1. **C0 准备 + 验证现有事实**：spec commit（已）；plan task 0 加 grep 守门：confirm jury `--dry-run` 现有单测路径 + confirm `command_return_code` 当前签名 + confirm autopilot next_action 数据结构
2. **C1 stderr 模板组扩展**：在 `format_stderr_message` keyword-only 签名 `(*, exit_code, status, error_kind, context)` 的 if/elif 分支 add-only 加 13 个 `handoff_*` error_kind 模板 + 3 单测（no_unfilled_placeholders / dispatch_complete / no_secret_leakage）
3. **C2 handoff parser 注册**：cad_pipeline.py 子解析器加 `--with-jury` `--no-strict-jury`；H1 golden snapshot 守门
4. **C3 handoff 自身 lock + fail-fast preflight**：实现 step 0 `.handoff.lock` + step 0.5 jury config 预检；H20 + H21
5. **C4 handoff orchestrator step 1-2 (enhance + check)**：H13 + H23（crash mid-step）
6. **C5 handoff orchestrator step 3 (jury --dry-run)**：H10 + H14 + H9a/b（cost over budget / 估价文案 / config 错双向）
7. **C6a step 4 jury accepted 路径**：H2（accepted + review ok）
8. **C6b step 4 jury preview / needs_review 业务降级**：H3 + H4 + H5 + H6（业务质量类双向）
9. **C6c step 4 jury 工具故障类双向**：H7a/b + H8a/b + H11a/b（6 用例）
10. **C6d step 4 jury unexpected exit**：H18 + H19
11. **C7 handoff orchestrator step 5 (enhance-review)**：H12 + H15 + H16 + H17（accepted + review 失败 / 路径不存在 / path traversal / 损坏 JSON）
12. **C8 subprocess argv 形式守门**：H22（专用 invariant 11 守门）
13. **C9 文档**：docs/cad-jury-config.md / PROGRESS.md / README.md（用 §7.4 钉死示例文本）
14. **C10 全量回归 + ruff/mypy strict 检查 + cov ≥90% + 北极星 5 gate 体检**
15. **C11 PR 与 review 流程 + tag v2.28.0 + GitHub Release**

注：v1.2 草拟的 autopilot next_action 文案任务 **v1.3 移出本 PR 范围**（autopilot 当前推荐 enhance 不推荐 handoff，集成需先重设计 autopilot 增加新中间状态分支；推到 A1.1 独立 PR）。

#### 8.1 plan task 0 grep 守门清单（v1.4 强化）

防 spec 假设漂移；session 39/40 教训。task 0 必须 grep 实证：

| 检查项 | 命令 | 期望 |
|---|---|---|
| jury `--dry-run` 现有单测路径 | `grep -n "test_dry_run\|--dry-run" tests/jury/` | 至少 1 个测试用例 |
| `command_return_code` 当前签名 | `grep -n "def command_return_code" tools/photo3d_handoff.py` | 行号确认 |
| autopilot next_action 数据结构 | `grep -n "next_action\|argv" tools/photo3d_autopilot.py` | argv list（不是 command string）|
| `format_stderr_message` 签名 | `grep -n "def format_stderr_message" tools/jury/stderr_messages.py` | keyword-only `(*, exit_code, status, error_kind, context)` |
| jury report `run_id` 字段写入位置 | `grep -n "run_id" tools/photo3d_jury.py` | 行 362-363 写入 |
| `_file_lock.py` acquire_lock 签名 | `grep -n "def acquire_lock\|class LockBusy" tools/_file_lock.py` | `(lock_path) -> Iterator[None]` + `LockBusy` |
| `assert_within_project` 签名 | `grep -n "def assert_within_project" tools/path_policy.py` | 三参数 `(path, project_root, label)` |
| `write_json_atomic` 签名 | `grep -n "def write_json_atomic" tools/contract_io.py` | 二参数 `(path, data) -> Path` |
| jury Layer 0 字段消费 | `grep -rn "views\|pixel_metrics\|edge_similarity" tools/jury/input_evidence_binding.py tools/jury/cost.py` | 字段集供 fake_enhancement_report fixture 校准 |
| jury exit=1 是否写 PHOTO3D_JURY_REPORT.json | `grep -B 5 "return 1" tools/photo3d_jury.py` | 确认 layer0 fail 路径是否写盘 |

每个 C 段一个 commit；C1-C9 内每个 H 用例独立子任务，先 RED 后 GREEN。

**plan task 0 grep 守门清单**（防 spec 假设漂移；session 39 教训）：
- `grep -n "def run_photo3d_handoff\|def command_return_code" tools/photo3d_handoff.py` → 确认行号与签名
- `grep -n "test_dry_run" tests/jury/` → 确认 jury --dry-run 现有单测覆盖范围
- `grep -n "next_action" tools/photo3d_autopilot.py cad_pipeline.py` → 确认 autopilot next_action 数据结构
- `grep -n "_TEMPLATES\|format_stderr_message" tools/jury/stderr_messages.py` → 确认现有三元组分派内部存储结构
- `grep -rn "run_id" tools/photo3d_jury.py` → 确认 jury report run_id 字段写入位置 + 格式

---

## 9. 风险与已知 unknown

### 9.1 已知风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| handoff e2e mock 子进程在 Windows / Linux 行为差异 | 测试 flake | patch target 钉死 `tools.photo3d_handoff.subprocess.run`；fake 函数签名固定；H22 专用守门 |
| 同机并发跑 photo3d-handoff（双 terminal / CI 多 worker）| 数据 corruption 或 race | invariant 14 handoff 自身 `.handoff.lock` 覆盖 step 0-6；H21 守门 |
| jury report `run_id` 字段被恶意改写为 `..` 路径 | path traversal 攻击 | invariant 10 三层守门：正则格式校验 + `assert_within_project` + `.is_file()`；H16 守门 |
| `jury_review_input.json` 是损坏 JSON | enhance-review 报错信息混淆 | invariant 10 校验 `json.loads()`；exit=23 独立类目；H17 守门 |
| jury 进程被 SIGINT / SIGKILL（exit=130/137 等 unexpected）| handoff 静默走入 step 5 | invariant 7 优先级判定 (c) 分支：unexpected → exit=25；H18 + H19 守门 |
| jury cost 估价依赖 `ENHANCEMENT_REPORT.json` 已存在 | 步骤 3 在步骤 1+2 失败时跑不起来 | 实现保证：handoff 严格 step 顺序 |
| jury config 缺失但用户已跑了 5 分钟 enhance | LLM 额度白花 | step 0.5 fail-fast preflight 在 step 1 之前；H20 守门；jury config 缺失立即 exit=2 |
| handoff stderr 透传 jury subprocess stderr 含 traceback | 潜在 api_key / 路径泄漏 | invariant 12 stderr 透传必走 `redact_traceback_str` + `redact_body` |
| handoff 子进程 env 注入凭据 | 凭据扩散到子进程 | invariant 3 `env=os.environ.copy()` 不主动注入；H22 assert env 不含敏感键的主动注入 |
| `--no-strict-jury` 命名歧义（用户误以为"跳过 jury"）| UX 混淆 | docs/cad-jury-config.md 显式表格列出 strict/no-strict 行为；模板含"加 --no-strict-jury 仅警告（结果不进入 deliver）"明确措辞 |
| autopilot next_action 子串误判（subsystem 名含 `--with-jury`）| 测试假绿 | autopilot 测试用 token 边界正则；invariant 1 + 6.4 守门 |
| review 子进程 exit code 与 handoff exit 段撞码 | 用户从 exit code 判断不出阶段 | clamp_review_exit 函数 1→20/2→21/3→22/其他→23 |
| step 4 后 ARTIFACT_INDEX.json 被外部进程改 | jury report 内 run_id 失效 | H 用例 fixture 不模拟（实战频率低）；如有问题靠 invariant 14 handoff lock 兜底 |
| 双 stderr 估价打印（jury + handoff）造成用户困惑 | 看到两次估价 | invariant 8 单源打印：handoff 不重复打印估价，仅在 over budget 时打中文提示 |

### 9.2 已知 unknown

- handoff 当前 description epilog 的实际文本是否需要重写（行数较多）— C8 阶段决定
- jury `--dry-run` 是否需要 handoff 显式传 `--budget`/`--profile-id` — 当前假设走 jury v1 默认；C3 阶段验证

### 9.3 不接受的风险（Red Team 防线）

- **不允许**：handoff 自己 import jury 模块函数直接调（破坏 invariant 3 子进程隔离）
- **不允许**：handoff 自己拼 stderr 文案（破坏 invariant 5.3 唯一入口）
- **不允许**：handoff stderr 用 f-string 含变量名 api_key/base_url/model（防意外泄漏）
- **不允许**：autopilot 实跑 jury 或 enhance（破坏 invariant 1 autopilot 行为不变）
- **不允许**：handoff 修改 jury 子模块的任何文件（除 `tools/jury/stderr_messages.py` 的 `format_stderr_message` 函数 if/elif 分支 add-only 扩展；**v1.4 修正 v1.2 错描述：不是 _TEMPLATES 字典**）
- **不允许**：handoff 调子进程用 shell=True 或字符串拼接 argv（防注入）
- **不允许**：handoff 用并行的 string-key 分派函数 `format_handoff_message`（必须复用 `format_stderr_message` 三元组分派）
- **不允许**：handoff 写 PHOTO3D_HANDOFF.json 不走 `write_json_atomic` + `assert_within_project` 三参数

---

## 10. 验收标准（DoD）

完成本 PR 必须满足：

1. **测试**：所有 §6 测试 PASS（H1-H23 共 29 用例：H1/H1b/H1c 三回归 + H7a/H7b/H8a/H8b/H9a/H9b/H11a/H11b 工具故障双向 + H2/H3/H4/H5/H6/H10/H12-H23 单 = 29 用例 + 5 stderr 模板/clamp/格式单测；**autopilot 测试本 PR 不加**）
2. **回归**：`tests/` 全量 PASS 不少于 v2.27.0 基线（≥2622 PASS）
3. **mypy strict**：本 PR 改的所有文件（tools/photo3d_handoff.py / tools/jury/stderr_messages.py / cad_pipeline.py）保持 strict 不降级；不允许 `# type: ignore` 无注释（CLAUDE.md）
4. **ruff check + format**：clean，无 violations
5. **CI**：Linux + Windows 双平台全绿
6. **coverage**：
   - 命令：`uv run pytest tests/test_photo3d_handoff_with_jury.py tests/jury/test_stderr_messages.py --cov=tools.photo3d_handoff --cov=tools.jury.stderr_messages --cov-fail-under=90`
   - **cov source explicit list**（不依赖默认发现）
   - **Linux + Windows 各自独立测**（platform split）
7. **文档**：
   - `docs/cad-jury-config.md` 加 "通过 photo3d-handoff 一条命令跑闭环" 章节，含 `--with-jury` `--no-strict-jury` flag 矩阵
   - `docs/PROGRESS.md` 加 v2.28.0 入口
   - 本 spec commit 在 `docs/superpowers/specs/`
   - `README.md` 用法示例追加 `--with-jury` 推荐用法（不改默认推荐）
8. **北极星 5 gate 体检**（每条须有具体证据）：
   - 零配置：✓ 不引入新配置；jury config 缺失时 step 0.5 fail-fast 立即报错引导用户到 `docs/cad-jury-config.md`，不跑 enhance（不浪费 LLM 额度）
   - 稳定可靠：✓ strict 默认 + 工具故障类必阻断；`.handoff.lock` 防同机并发；invariant 7 优先级判定杜绝 jury exit code 静默漏判；invariant 6 dry-run 不取锁消除 race window
   - 结果准确：✓ jury accepted → enhance-review 串联保证 deliver 前必有正式 ENHANCEMENT_REVIEW_REPORT.json；review_input path traversal / 损坏 JSON 三层守门
   - SW 装即用：✓ 无 SW 涉及
   - 傻瓜式操作：✓ 一条 `photo3d-handoff --with-jury --confirm` 跑完整闭环；模板含"下一步动作"清单不要求外行用 Task Manager
9. **schema 钉死**：PHOTO3D_HANDOFF.json 字段 keyset 与 §4.2 决策表 + 数据流 §4.1 步骤 6 完全一致；`jury_handoff_status` 字符串值与决策表完全一致（H1-H23 各用例 assert 字段值）；现有 `status` 字段（值 awaiting_confirmation 等）的枚举值与 v2.27.0 完全一致 H1 守门
10. **PR 流程**：feature/jury-v2-handoff-integration → PR → CI 全绿 → squash merge → tag v2.28.0 + GitHub Release

---

## 11. 后续 (v3 路线，不在本 PR)

承袭 jury v1 spec §11 列表中本 PR 未覆盖项，按簇拆为独立 PR：

- **A2 簇**：`photo3d-jury --summary` 跨 run 聚合 / `--json` 机器友好 / `photo3d-recover` 注册 jury 文件
- **B 簇**：`anthropic_native` kind / `fallback_profile_ids` chain / 月度 quota tracker / 同 key 跨进程 RPM 协调
- **C 簇**：incremental flush（ctrl-c safe）/ `--max-tokens` 自适应 / 中转商中文 quota 文案匹配
- **D 簇**：cost 自动同步 vendor pricing / multi-dim cost model / per-profile cap override
- **E 簇**：NIQE/BRISQUE Layer 1 扩展 / 多视角投票交叉验证
- **F 簇**：schema_version=2 升级（add-only 加 quota_per_month_usd 等）
- **方案 ② 升级**：autopilot 端到端化（gate-only → 真正 orchestrator）

---

## 附录 A：参考文件

| 文件 | 用途 |
|---|---|
| `docs/superpowers/specs/2026-05-08-photo3d-jury-design.md` | jury v1 设计（架构 / 4 层判定 / 异常类层级 / 不变量） |
| `tools/photo3d_jury.py` | jury main 入口（本 PR 不动；复用 v1 已有 `--dry-run` flag） |
| `tools/jury/cost.py` | cost 估价逻辑（dry-run 模式复用） |
| `tools/jury/stderr_messages.py` | 中文文案模板模块（本 PR add-only 加 HANDOFF_* 组） |
| `cad_pipeline.py:cmd_photo3d_handoff` | handoff 主体（本 PR orchestrator 改造） |
| `cad_pipeline.py:cmd_photo3d_autopilot` | autopilot 主体（本 PR 仅文案改动） |
| `tests/jury/conftest.py` | autouse kill switch + dummy fixture key |
| `CLAUDE.md` | 项目工作流约束（superpowers + TDD + 中文输出） |
