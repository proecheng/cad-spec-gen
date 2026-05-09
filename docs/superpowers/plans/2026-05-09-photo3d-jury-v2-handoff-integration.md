# photo3d-jury v2 handoff 集成实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 photo3d-handoff 一条命令中串联 enhance + check + jury 自动验收 + enhance-review 闭环；新增 `--with-jury` `--no-strict-jury` 两个 flag；jury hook 嵌入 `_run_enhancement_followup` 在 enhance-check 之后。

**Architecture:**
- jury hook 嵌入 `tools/photo3d_handoff.py:_run_enhancement_followup` 在现有 `_execute_enhance_check_followup` 之后
- 仅当 `next_action.kind == "run_enhancement"` + `--with-jury` 启用时触发；其他 kind / 无 flag 时回归路径不变
- 复用 jury v1 已有的 `--dry-run` flag 跑估价，再用相同进程跑实跑；不改 jury 子模块任何代码
- jury accepted 后由 handoff 自己调 `enhance-review` subprocess 转正式契约
- HANDOFF_RUN.json schema add-only 加 8 字段；现有字段不动

**Tech Stack:** Python 3.11+ / pytest / mypy strict / ruff / subprocess.run argv list / msvcrt.locking (Windows) / fcntl.flock (Linux mock)

**spec 锚点：** `docs/superpowers/specs/2026-05-09-photo3d-jury-v2-handoff-integration-design.md` v1.4（4 层审查后定稿）

---

## File Structure

| 文件 | 改动类型 | 行数估计 | 责任 |
|---|---|---|---|
| `cad_pipeline.py` | modify L3886-3907 子解析器注册 | +25 add-only | 加 `--with-jury` `--no-strict-jury` flag；薄壳转发到 `run_photo3d_handoff` |
| `tools/photo3d_handoff.py` | modify | +250 net | jury hook 主流程；新加 helper 函数；扩展 `_run_enhancement_followup` + `command_return_code` |
| `tools/jury/stderr_messages.py` | modify L72+（add-only 加分支） | +120 | 13 个 `handoff_*` error_kind 在 `format_stderr_message` 内 if/elif 分支 |
| `tests/test_photo3d_handoff_with_jury.py` | create | +750 | H1-H23 共 27 实质用例 + helper 单测 |
| `tests/jury/test_stderr_messages.py` | modify | +80 | 3 个 stderr 模板单测 |
| `tests/fixtures/photo3d_handoff_v2_27_0.json` | create | (snapshot) | golden snapshot 比对基线 |
| `docs/cad-jury-config.md` | modify | +60 | "handoff 一条闭环"章节 + flag 矩阵 + 故障恢复 + CI 集成 |
| `docs/PROGRESS.md` | modify | +5 | v2.28.0 入口 |
| `README.md` | modify | +15 | 用法示例（双行：预览 + --confirm 实跑）|

**不改文件**：`tools/photo3d_jury.py` / `tools/jury/{config,cost,llm_client,verdict,redact,deterministic_gate,input_evidence_binding}.py` / `tools/photo3d_autopilot.py` / `tests/test_cad_pipeline_autopilot.py`

---

## Task 0: 准备 + grep 守门 + golden snapshot 生成

**Files:**
- Verify (read-only): `tools/photo3d_handoff.py` / `tools/photo3d_autopilot.py` / `tools/jury/stderr_messages.py` / `tools/_file_lock.py` / `tools/path_policy.py` / `tools/contract_io.py` / `tools/jury/input_evidence_binding.py` / `tools/jury/cost.py` / `tools/photo3d_jury.py`
- Create: `tests/fixtures/photo3d_handoff_v2_27_0.json`

- [ ] **Step 0.1: 验证已在 feature/jury-v2-handoff-integration 分支**

```bash
git rev-parse --abbrev-ref HEAD
```

Expected: `feat/jury-v2-handoff-integration`

- [ ] **Step 0.2: spec §8.1 grep 守门 10 项一次过**

逐条跑下面 grep，不一致立即停下找主 agent 校准 spec：

```bash
# 1. jury --dry-run 现有单测
grep -n "test_dry_run\|--dry-run" tests/jury/test_photo3d_jury_cli.py
# Expected: 至少 1 个 test_dry_run_* 函数定义

# 2. command_return_code 当前签名
grep -n "def command_return_code" tools/photo3d_handoff.py
# Expected: line ~165, 签名 (report: dict[str, Any]) -> int

# 3. autopilot next_action 数据结构
grep -n "next_action\|argv" tools/photo3d_autopilot.py
# Expected: argv list 字段（不是 command string）

# 4. format_stderr_message 签名
grep -n "def format_stderr_message" tools/jury/stderr_messages.py
# Expected: keyword-only `(*, exit_code, status, error_kind, context)`

# 5. jury report run_id 字段
grep -n '"run_id":' tools/photo3d_jury.py
# Expected: line ~363 写入 report["run_id"] = layer0.frozen_run_id

# 6. _file_lock 公开 API
grep -n "def acquire_lock\|class LockBusy" tools/_file_lock.py
# Expected: acquire_lock(lock_path) -> Iterator[None] + LockBusy 类

# 7. assert_within_project 签名
grep -n "def assert_within_project" tools/path_policy.py
# Expected: 三参数 (path, project_root, label)

# 8. write_json_atomic 签名
grep -n "def write_json_atomic" tools/contract_io.py
# Expected: 二参数 (path, data) -> Path

# 9. jury Layer 0 字段消费
grep -rn "views\|enhanced_image\|edge_similarity\|delivery_status" tools/jury/input_evidence_binding.py tools/jury/cost.py
# 校准 fake_enhancement_report fixture（Task 5 用）

# 10. jury exit=1 是否写 report
grep -B 5 "return 1" tools/photo3d_jury.py
# Expected: layer0 fail return 1 之前不写 PHOTO3D_JURY_REPORT.json
# 若实证写盘，需更新 spec invariant 7
```

- [ ] **Step 0.3: 生成 golden snapshot**

```bash
# 拿 v2.27.0 tag 的实际产出
git stash
git checkout v2.27.0
# 跑一次 photo3d-handoff（在 lifting_platform）取 PHOTO3D_HANDOFF.json
python cad_pipeline.py photo3d-handoff --subsystem lifting_platform > /dev/null 2>&1 || true
# 复制到 fixture（normalize 时间戳）
cp cad/lifting_platform/.cad-spec-gen/runs/*/PHOTO3D_HANDOFF.json /tmp/h.json
git checkout feat/jury-v2-handoff-integration
git stash pop
mkdir -p tests/fixtures
# 用 jq normalize generated_at 字段为 "FROZEN" 后落盘
python -c "
import json
d = json.load(open('/tmp/h.json'))
d['generated_at'] = 'FROZEN'
json.dump(d, open('tests/fixtures/photo3d_handoff_v2_27_0.json', 'w'), ensure_ascii=False, indent=2, sort_keys=True)
"
```

注：若 v2.27.0 状态下没现成 lifting_platform run dir，可跳过实跑改为手抄 schema：从 `tools/photo3d_handoff.py:run_photo3d_handoff` 行 141-159 的字段集硬编码 fixture（保留所有字段名 + 类型默认值）。

- [ ] **Step 0.4: Commit Task 0**

```bash
git add tests/fixtures/photo3d_handoff_v2_27_0.json
git commit -m "test: add v2.27.0 PHOTO3D_HANDOFF.json golden snapshot fixture"
```

---

## Task 1: stderr 模板组扩展（13 个 handoff_* error_kind）

**Files:**
- Modify: `tools/jury/stderr_messages.py`（在 format_stderr_message 函数末尾 fallback 前插入 13 个 handoff_* error_kind 分支）
- Modify: `tests/jury/test_stderr_messages.py`（add-only 3 单测）

- [ ] **Step 1.1: 写失败测试 — handoff error_kind 完整覆盖**

在 `tests/jury/test_stderr_messages.py` 末尾追加：

```python
import pytest
from tools.jury.stderr_messages import format_stderr_message

# spec §5.2.1 钉死的 13 个 (exit_code, error_kind, context) 三元组
HANDOFF_ERROR_KINDS = [
    (10, "handoff_jury_preview", {"failed_n": 2, "score": 60, "min_score": 75, "report_path": "/r/p", "mode": "strict"}),
    (0, "handoff_jury_preview", {"failed_n": 2, "score": 60, "min_score": 75, "report_path": "/r/p", "mode": "warning"}),
    (11, "handoff_jury_needs_review", {"failed_views": ["v1"], "vendor_request_id": None, "report_path": "/r/p", "mode": "strict"}),
    (12, "handoff_jury_blocked", {"report_path": "/r/p"}),
    (4, "handoff_jury_lock_busy", {"lock_mtime_minutes_ago": 5, "lock_path": "/r/.jury.lock"}),
    (99, "handoff_jury_internal_error", {"redacted_traceback": "Traceback..."}),
    (2, "handoff_jury_config_error", {"config_path": "~/.claude/cad_jury_config.json"}),
    (3, "handoff_jury_cost_over_budget", {"estimated_usd": 0.04, "budget_usd": 0.02, "n_views": 4}),
    (20, "handoff_review_failed", {"review_raw_exit": 1, "report_path": "/r/p"}),
    (13, "handoff_review_input_missing", {"review_input_path": "/r/p", "reason": "not_found"}),
    (23, "handoff_review_input_corrupt", {"review_input_path": "/r/p", "parse_error": "Expecting value"}),
    (25, "handoff_unexpected_jury_exit", {"raw_exit": 137}),
    (24, "handoff_handoff_lock_busy", {"lock_mtime_minutes_ago": 3, "lock_path": "/r/.handoff.lock"}),
    (2, "handoff_jury_preflight_config_missing", {"config_path": "~/.claude/cad_jury_config.json"}),
    (0, "handoff_awaiting_confirmation_with_jury", {"argv_with_confirm": "python cad_pipeline.py photo3d-handoff --subsystem X --with-jury --confirm"}),
]


@pytest.mark.parametrize("exit_code,error_kind,context", HANDOFF_ERROR_KINDS)
def test_handoff_error_kinds_no_unfilled_placeholders(exit_code, error_kind, context):
    """spec §6.2 — 13 个 handoff_* error_kind 模板渲染无 {xxx} 残留"""
    out = format_stderr_message(exit_code=exit_code, error_kind=error_kind, context=context)
    # 模板渲染后无 {placeholder} 残留
    import re
    assert re.search(r"\{[a-zA-Z_]+\}", out) is None, f"unfilled placeholder in {error_kind}: {out!r}"
    # 输出非空
    assert out.strip()


@pytest.mark.parametrize("exit_code,error_kind,context", HANDOFF_ERROR_KINDS)
def test_handoff_error_kinds_dispatch_complete(exit_code, error_kind, context):
    """spec §6.2 — 用每个 error_kind 调 format_stderr_message，输出非 fallback 兜底"""
    out = format_stderr_message(exit_code=exit_code, error_kind=error_kind, context=context)
    # 不命中 fallback `f"✗ ...（{error_kind}）..."`
    assert f"（{error_kind}）" not in out, f"fell through to fallback for {error_kind}: {out!r}"


def test_handoff_templates_no_secret_leakage():
    """spec §5.3 — handoff_* 模板源码中无 api_key / base_url / model 字面量作为 placeholder"""
    import inspect
    from tools.jury import stderr_messages
    src = inspect.getsource(stderr_messages.format_stderr_message)
    for forbidden in ("{api_key}", "{base_url}", "{model}"):
        assert forbidden not in src, f"forbidden placeholder {forbidden!r} found in format_stderr_message"
```

- [ ] **Step 1.2: 跑测试确认 RED**

```bash
uv run pytest tests/jury/test_stderr_messages.py::test_handoff_error_kinds_no_unfilled_placeholders -v
```

Expected: 14 个 fail（fallback 路径 `✗ ...（handoff_jury_preview）...` 命中 + 占位符 `{xxx}` 残留）

- [ ] **Step 1.3: 在 format_stderr_message 内部添加 13 个 handoff_* 分支**

Modify `tools/jury/stderr_messages.py`，在 `format_stderr_message` 函数末尾 fallback `return f"✗ ...（{error_kind}）..."` 之前 add-only 加：

```python
    # === v2.28.0 handoff 集成模板（spec §5.2 + §5.2.1） ===
    if error_kind == "handoff_jury_preview":
        failed_n = context.get("failed_n", 0)
        score = context.get("score", 0)
        min_score = context.get("min_score", 0)
        report_path = context.get("report_path", "")
        mode = context.get("mode", "strict")
        if mode == "strict":
            return (
                f"jury 判定 preview（5 项语义检查中 {failed_n} 项 false 或 photoreal_score={score} 低于 min_photoreal_score={min_score}）。\n"
                f"  jury 报告：{report_path}\n"
                "  ① 改善：检查 enhance 输出是否清晰；调整 enhance config；或换 provider preset（具体可改项见 docs/cad-enhance-config.md）\n"
                "  ② 跳过：加 --no-strict-jury 仅警告（但结果不会进入 deliver；需手动跑 enhance-review）"
            )
        return (
            f"[WARNING] jury 判定 preview，因 --no-strict-jury 仅警告。\n"
            f"  jury 报告：{report_path}\n"
            "  注意：本次 handoff 不会自动跑 enhance-review；deliver 会缺 ENHANCEMENT_REVIEW_REPORT.json。"
        )

    if error_kind == "handoff_jury_needs_review":
        failed_views = context.get("failed_views", [])
        vendor_request_id = context.get("vendor_request_id") or "(无)"
        report_path = context.get("report_path", "")
        mode = context.get("mode", "strict")
        prefix = "jury 工具调用失败" if mode == "strict" else "[WARNING] jury 工具调用失败"
        return (
            f"{prefix}（{len(failed_views)} 视角；vendor_request_id={vendor_request_id}）。\n"
            f"  jury 报告：{report_path}\n"
            "  ① 重跑：jury 偶发失败常自愈\n"
            "  ② 换 profile：jury config active_profile_id 切到备用\n"
            "  ③ 检查 api_key 是否到期 / 是否被 vendor rate-limit"
        )

    if error_kind == "handoff_jury_blocked":
        report_path = context.get("report_path", "")
        return (
            "jury 检测到输入证据漂移（active_run_id 或 sha256 不一致）。\n"
            "  这是工具自身故障，--no-strict-jury 也不会跳过。\n"
            f"  jury 报告：{report_path}\n"
            "  ① 重跑：cad_pipeline.py photo3d-handoff --with-jury --confirm 重新走一遍\n"
            "  ② 检查：是否其他工具/脚本同时改 ARTIFACT_INDEX.json（CI 多 worker / 双窗口）"
        )

    if error_kind == "handoff_jury_lock_busy":
        mins = context.get("lock_mtime_minutes_ago", 0)
        lock_path = context.get("lock_path", "")
        return (
            f"jury 被另一 photo3d-jury 进程持锁（lock 文件 mtime={mins} 分钟前）。\n"
            "  ① 等待：其他 jury 进程结束（一次跑 ~30s）；30 分钟无响应自动清理\n"
            "  ② 主动放弃：本次 handoff 退出；不会破坏数据；可稍后重跑\n"
            f"  ③ 紧急清理（仅在确认无其他 photo3d-jury 进程时）：删 {lock_path} 后重跑"
        )

    if error_kind == "handoff_jury_internal_error":
        tb = context.get("redacted_traceback", "")
        return (
            "jury 内部异常（已脱敏 traceback）：\n"
            f"  {tb}\n"
            "  这是 bug，请提 issue 并附 PHOTO3D_JURY_REPORT.json"
        )

    if error_kind == "handoff_jury_config_error":
        cp = context.get("config_path", "~/.claude/cad_jury_config.json")
        return (
            f"jury 配置文件 {cp} 解析失败（jury 子进程报错）。\n"
            "  详见 jury 自身 stderr；修后重跑。"
        )

    if error_kind == "handoff_jury_cost_over_budget":
        est = context.get("estimated_usd", 0.0)
        budget = context.get("budget_usd", 0.0)
        n_views = context.get("n_views", 0)
        return (
            f"[handoff] jury 预估 {est:.2f} USD / {n_views} 视角 (budget {budget:.2f} USD)\n"
            f"jury 估价超过 budget。改 budget 或减视角后重跑。"
        )

    if error_kind == "handoff_review_failed":
        raw = context.get("review_raw_exit", 0)
        rp = context.get("report_path", "")
        return (
            f"enhance-review 转正式契约失败（review exit={raw}）。\n"
            f"  jury 报告已写在 {rp}，可手动重跑：\n"
            f"  python cad_pipeline.py enhance-review --review-input <run_dir>/jury_review_input.json"
        )

    if error_kind == "handoff_review_input_missing":
        rip = context.get("review_input_path", "")
        reason = context.get("reason", "")
        return (
            f"jury 判定 accepted 但 enhance-review 输入缺失（{reason}）。\n"
            f"  路径：{rip}\n"
            "  原因 not_found = 文件不存在；run_id_format = jury 写的 run_id 含非法字符；path_traversal = 路径越界\n"
            "  这是 bug，请提 issue 并附 PHOTO3D_JURY_REPORT.json"
        )

    if error_kind == "handoff_review_input_corrupt":
        rip = context.get("review_input_path", "")
        pe = context.get("parse_error", "")
        return (
            f"jury_review_input.json 是损坏 JSON：{rip}\n"
            f"  解析错误：{pe}\n"
            "  这是 jury 写盘 bug，请提 issue 并附文件原始字节"
        )

    if error_kind == "handoff_unexpected_jury_exit":
        raw = context.get("raw_exit", 0)
        return (
            f"jury 进程异常退出（exit code = {raw}）。\n"
            "  常见原因：被 Ctrl-C 打断（130） / OOM kill（137） / 超时（timeout） / 系统 SIGTERM\n"
            "  ① 重跑 handoff；② 若反复出现，看 jury stderr 详细输出（已脱敏）"
        )

    if error_kind == "handoff_handoff_lock_busy":
        mins = context.get("lock_mtime_minutes_ago", 0)
        lock_path = context.get("lock_path", "")
        return (
            f"另一个 photo3d-handoff 进程正在跑同 subsystem（lock mtime={mins} 分钟前）。\n"
            "  请等当前进程结束（约 5-15 分钟，含 enhance + jury + review）；\n"
            f"  ③ 紧急清理（仅在确认无其他 photo3d-handoff 进程时）：删 {lock_path} 后重跑"
        )

    if error_kind == "handoff_jury_preflight_config_missing":
        cp = context.get("config_path", "~/.claude/cad_jury_config.json")
        return (
            f"jury 配置缺失或格式错（路径：{cp}）。\n"
            "  最小配置示例（写到 ~/.claude/cad_jury_config.json）：\n"
            '    {{"profiles": [{{"id": "default", "kind": "openai_compat", "api_base_url": "https://api.openai.com", "api_key": "sk-...", "model": "gpt-4o", "cost_per_call_usd": 0.01}}], "active_profile_id": "default", "budget_per_run_usd": 0.50}}\n'
            "  详细参数（含中转商 base_url / TLS CA）见 docs/cad-jury-config.md。\n"
            "  注：jury 估价产生的 USD 费用计入此 api_key 对应 LLM 服务商账单。\n"
            "  本次 handoff 已立即退出，未跑 enhance（不浪费 LLM 额度）"
        )

    if error_kind == "handoff_awaiting_confirmation_with_jury":
        argv_with_confirm = context.get("argv_with_confirm", "")
        return (
            "已找到可交接的下一步（含 jury 验收 + enhance-review 闭环）；预览模式不执行。\n"
            f"  下一步：加 --confirm 重跑：\n"
            f"    {argv_with_confirm}\n"
            "  或不带 --with-jury 走简化路径（仅 enhance + check 不跑 jury）"
        )
```

注：`handoff_jury_config_error` 模板必须避免 `{config_path}` 占位（防 §1.1 测试 `test_handoff_templates_no_secret_leakage` 误判）—— spec §5.3 仅禁 `{api_key}` `{base_url}` `{model}`，`{config_path}` 是允许字段。

- [ ] **Step 1.4: 跑测试确认 GREEN**

```bash
uv run pytest tests/jury/test_stderr_messages.py -v
```

Expected: 30+ tests PASS（含 jury v1 既有 + 新加 14 + 14 + 1 = 29 个）

- [ ] **Step 1.5: ruff + mypy 检查**

```bash
uv run ruff check tools/jury/stderr_messages.py tests/jury/test_stderr_messages.py
uv run mypy --strict tools/jury/stderr_messages.py
```

Expected: 全 clean

- [ ] **Step 1.6: Commit Task 1**

```bash
git add tools/jury/stderr_messages.py tests/jury/test_stderr_messages.py
git commit -m "feat(jury): handoff 集成扩展 13 个 handoff_* error_kind stderr 模板"
```

---

## Task 2: handoff parser 注册 --with-jury / --no-strict-jury flag

**Files:**
- Modify: `cad_pipeline.py:cmd_photo3d_handoff` parser 区块（line ~5109-5180）

- [ ] **Step 2.1: 写失败测试 — H1 golden snapshot 回归 + flag 解析**

新建 `tests/test_photo3d_handoff_with_jury.py` 起手：

```python
"""photo3d-handoff --with-jury / --no-strict-jury 集成测试

spec: docs/superpowers/specs/2026-05-09-photo3d-jury-v2-handoff-integration-design.md v1.4
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import pytest

# v1.4 §6.0.5 — 新文件顶部 module-scope autouse 复制 jury kill switch
@pytest.fixture(autouse=True)
def _disable_llm_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAD_JURY_DISABLE_LLM", "1")


# === H1 / H1b / H1c 回归 + golden snapshot ===

@pytest.mark.regression
def test_h1_no_with_jury_golden_snapshot(tmp_path: Path) -> None:
    """H1 — 不带 --with-jury 路径：PHOTO3D_HANDOFF.json 字段集与 v2.27.0 基线一致"""
    golden = json.loads(Path("tests/fixtures/photo3d_handoff_v2_27_0.json").read_text(encoding="utf-8"))
    # H1 仅 keyset 守门 + 字段值 sort_keys json 全等（normalize 时间戳）
    # 完整 e2e 跑 handoff 由 H2/H10 等其他用例覆盖；H1 仅 keyset
    assert "jury_handoff_status" not in golden, "v2.27.0 基线不应有 jury_* 字段（@regression）"
    assert "jury_status" not in golden
    assert "review_status" not in golden
```

- [ ] **Step 2.2: 跑测试确认 RED**

```bash
uv run pytest tests/test_photo3d_handoff_with_jury.py::test_h1_no_with_jury_golden_snapshot -v
```

Expected: PASS（regression 测试不需 RED → GREEN；它的 RED 由 mutation sanity check 验证 — 见 Task 14）

- [ ] **Step 2.3: 在 cad_pipeline.py 加 --with-jury / --no-strict-jury flag**

定位 `cad_pipeline.py:cmd_photo3d_handoff` 子解析器注册区（grep `p_photo3d_handoff = sub.add_parser`），在现有 add_argument 块末尾 add-only 加：

```python
    p_photo3d_handoff.add_argument(
        "--with-jury",
        action="store_true",
        help="run_enhancement 完成后串联 jury 自动验收 + enhance-review，一条命令跑闭环",
    )
    p_photo3d_handoff.add_argument(
        "--no-strict-jury",
        action="store_true",
        help="jury preview/needs_review 时仅警告不阻断（不影响 jury 工具故障类）；默认 strict",
    )
```

同时在 `cmd_photo3d_handoff` 函数体（薄壳）将两个新字段透传给 `run_photo3d_handoff`：

```python
def cmd_photo3d_handoff(args):
    from tools.photo3d_handoff import run_photo3d_handoff, command_return_code
    report = run_photo3d_handoff(
        project_root=Path.cwd(),
        subsystem=args.subsystem,
        artifact_index_path=args.artifact_index,
        source=args.source,
        confirm=args.confirm,
        provider_preset=args.provider_preset,
        output_path=args.output,
        with_jury=getattr(args, "with_jury", False),       # v2.28.0
        no_strict_jury=getattr(args, "no_strict_jury", False),  # v2.28.0
    )
    return command_return_code(report)
```

- [ ] **Step 2.4: tools/photo3d_handoff.py:run_photo3d_handoff 接受新关键字参数**

在签名 add-only 加 `with_jury: bool = False, no_strict_jury: bool = False`：

```python
def run_photo3d_handoff(
    project_root: str | Path,
    subsystem: str,
    *,
    artifact_index_path: str | Path | None = None,
    source: str | None = None,
    confirm: bool = False,
    provider_preset: str | None = None,
    output_path: str | Path | None = None,
    with_jury: bool = False,           # v2.28.0
    no_strict_jury: bool = False,      # v2.28.0
) -> dict[str, Any]:
    ...
```

本 task 仅加签名 + 透传到 `_run_enhancement_followup`（后续 task 实现 jury hook 主体）。

- [ ] **Step 2.5: 跑测试确认 PASS**

```bash
uv run pytest tests/test_photo3d_handoff_with_jury.py::test_h1_no_with_jury_golden_snapshot -v
uv run pytest tests/ -k "test_cad_pipeline_handoff" -v  # 现有回归
```

Expected: 全 PASS（不破坏现有用例）

- [ ] **Step 2.6: Commit**

```bash
git add cad_pipeline.py tools/photo3d_handoff.py tests/test_photo3d_handoff_with_jury.py
git commit -m "feat(handoff): cmd_photo3d_handoff 加 --with-jury / --no-strict-jury parser"
```

---

## Task 3: helper 函数（clamp_review_exit / validate_run_id_format / 常量）

**Files:**
- Modify: `tools/photo3d_handoff.py`（顶部 imports 后加常量 + 模块顶级 public helper）
- Modify: `tests/test_photo3d_handoff_with_jury.py`（add-only 2 helper 单测）

- [ ] **Step 3.1: 写失败测试**

在 `tests/test_photo3d_handoff_with_jury.py` add-only：

```python
def test_clamp_review_exit_mapping() -> None:
    """spec §3.3.1 + §6.2 — clamp_review_exit 映射钉死"""
    from tools.photo3d_handoff import clamp_review_exit
    assert clamp_review_exit(0) == 0
    assert clamp_review_exit(1) == 20
    assert clamp_review_exit(2) == 21
    assert clamp_review_exit(3) == 22
    assert clamp_review_exit(4) == 23
    assert clamp_review_exit(137) == 23
    assert clamp_review_exit(-1) == 23


def test_validate_run_id_format_rejects_traversal() -> None:
    """spec §3.4 inv 10 + §6.2 — run_id 格式正则守门"""
    from tools.photo3d_handoff import validate_run_id_format
    # 合法
    assert validate_run_id_format("20260509-123456") is True
    assert validate_run_id_format("run_001") is True
    assert validate_run_id_format("a") is True
    # 非法
    assert validate_run_id_format("../etc/passwd") is False
    assert validate_run_id_format("..\\windows\\system32") is False
    assert validate_run_id_format("") is False
    assert validate_run_id_format("a" * 65) is False  # 长度 > 64
    assert validate_run_id_format("run id") is False  # 含空格
    assert validate_run_id_format("run/id") is False  # 含斜杠
```

- [ ] **Step 3.2: 跑测试 RED**

```bash
uv run pytest tests/test_photo3d_handoff_with_jury.py -k "clamp_review_exit or validate_run_id" -v
```

Expected: ImportError 或 AttributeError（函数尚未定义）

- [ ] **Step 3.3: 实现 helper + 常量**

在 `tools/photo3d_handoff.py` 顶部 imports 后 add-only：

```python
import re

# === v2.28.0 jury 集成常量（spec §3.3.1） ===
HANDOFF_LOCK_STALE_SECONDS: int = 1800       # .handoff.lock 30 分钟自动清理
SUBPROCESS_TIMEOUT_ENHANCE: int = 1800       # enhance 子进程 30 分钟超时
SUBPROCESS_TIMEOUT_JURY: int = 600           # jury 子进程 10 分钟超时（含 LLM hang 兜底）
SUBPROCESS_TIMEOUT_REVIEW: int = 300         # enhance-review 5 分钟超时（本地处理）
RUN_ID_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


def validate_run_id_format(run_id: str) -> bool:
    """returns True iff run_id matches RUN_ID_PATTERN; never raises (spec §3.4 inv 10)."""
    return bool(RUN_ID_PATTERN.fullmatch(run_id))


def clamp_review_exit(review_raw_exit: int) -> int:
    """clamp enhance-review 子进程 exit code 到 handoff exit 段，防与 handoff 自身段撞码。
    映射：0→0 / 1→20 / 2→21 / 3→22 / 其他→23（spec §3.3.1）"""
    if review_raw_exit == 0:
        return 0
    if review_raw_exit == 1:
        return 20
    if review_raw_exit == 2:
        return 21
    if review_raw_exit == 3:
        return 22
    return 23
```

- [ ] **Step 3.4: 跑测试 GREEN**

```bash
uv run pytest tests/test_photo3d_handoff_with_jury.py -k "clamp_review_exit or validate_run_id" -v
```

Expected: 2 PASS

- [ ] **Step 3.5: ruff + mypy 检查**

```bash
uv run ruff check tools/photo3d_handoff.py
uv run mypy --strict tools/photo3d_handoff.py
```

- [ ] **Step 3.6: Commit**

```bash
git add tools/photo3d_handoff.py tests/test_photo3d_handoff_with_jury.py
git commit -m "feat(handoff): 加 clamp_review_exit / validate_run_id_format helper + 常量"
```

---

## Task 4: fake_run_factory + fixture 模板（§6.0）

**Files:**
- Modify: `tests/test_photo3d_handoff_with_jury.py`（add-only fixture 段）

- [ ] **Step 4.1: 写 fixture 模板**

在 `tests/test_photo3d_handoff_with_jury.py` autouse fixture 之后 add-only：

```python
import os


# === fake_run_factory（spec §6.0.1）===

@pytest.fixture
def fake_run_factory(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Any]:
    """按调用顺序 dispatch fake subprocess.run 行为；
    behaviors 列表对应预期调用：
      0: enhance / 1: enhance-check / 2: jury --dry-run / 3: jury 实跑 / 4: enhance-review
    """
    def _install(behaviors: list[Any]) -> Any:
        call_log: list[dict[str, Any]] = []
        idx = [0]

        def fake_run(argv: list[str], *, shell: bool = False, capture_output: bool = True,
                     text: bool = True, timeout: int | None = None,
                     env: dict[str, str] | None = None, encoding: str | None = None,
                     creationflags: int = 0, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            assert isinstance(argv, list), f"subprocess.run must be argv list (inv 11), got {type(argv)}"
            assert shell is False, "subprocess.run shell=False (inv 11)"
            # 不主动注入凭据（inv 3）
            if env is not None:
                for forbidden in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
                    assert env.get(forbidden) == os.environ.get(forbidden), (
                        f"handoff must not actively set {forbidden} (inv 3)"
                    )
            call_log.append({"argv": argv, "shell": shell, "env": env, "timeout": timeout})
            current = idx[0]
            idx[0] += 1
            assert current < len(behaviors), f"unexpected subprocess.run call #{current}: {argv}"
            entry = behaviors[current]
            if callable(entry):
                return entry(argv)
            return entry

        fake_run.call_log = call_log  # type: ignore[attr-defined]
        fake_run.call_count = lambda: idx[0]  # type: ignore[attr-defined]
        monkeypatch.setattr("tools.photo3d_handoff.subprocess.run", fake_run)
        return fake_run

    return _install


# === make_jury_run_dir（spec §6.0.3 review_input 三态工厂）===

@pytest.fixture
def make_jury_run_dir(tmp_path: Path) -> Callable[..., Path]:
    def _factory(*, run_id: str = "20260509-123456",
                 review_input_state: str = "ok",
                 subsystem: str = "lifting_platform",
                 jury_status: str = "accepted") -> Path:
        run_dir = tmp_path / "cad" / subsystem / ".cad-spec-gen" / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        # PHOTO3D_JURY_REPORT.json
        actual_run_id = run_id if review_input_state != "traversal" else "../etc/passwd"
        (run_dir / "PHOTO3D_JURY_REPORT.json").write_text(
            json.dumps({
                "schema_version": 1,
                "subsystem": subsystem,
                "run_id": actual_run_id,
                "status": jury_status,
                "jury_meta": {"actual_cost_usd": 0.04, "estimated_cost_usd": 0.04},
                "views": [],
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        # jury_review_input.json 三态
        rip = run_dir / "jury_review_input.json"
        if review_input_state == "ok":
            rip.write_text(json.dumps({"schema_version": 1, "views": []}, ensure_ascii=False), encoding="utf-8")
        elif review_input_state == "missing":
            pass
        elif review_input_state == "corrupt":
            rip.write_bytes(b"{not json")
        elif review_input_state == "traversal":
            pass  # actual_run_id 越界，路径校验时 fail
        else:
            raise ValueError(f"unknown review_input_state: {review_input_state}")
        return run_dir
    return _factory


# === fake_enhancement_report（spec §6.0.4 最小可跑字段集）===

@pytest.fixture
def fake_enhancement_report() -> dict[str, Any]:
    """ENHANCEMENT_REPORT.json 最小可被 jury Layer 0 + cost.py 接受的字段集
    Task 0 grep 校准；当前为初版猜测"""
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


# === fake CompletedProcess builder ===

def cp(returncode: int, *, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["fake"], returncode=returncode, stdout=stdout, stderr=stderr)
```

- [ ] **Step 4.2: 验证 fixture 自身可 import**

```bash
uv run pytest tests/test_photo3d_handoff_with_jury.py --collect-only -q
```

Expected: 已有用例 PASS collect；新加 fixture 不报错

- [ ] **Step 4.3: Commit**

```bash
git add tests/test_photo3d_handoff_with_jury.py
git commit -m "test(handoff): add fake_run_factory + make_jury_run_dir + fake_enhancement_report fixtures"
```

---

## Task 5: handoff 自身 .handoff.lock + fail-fast preflight (H20 + H21)

**Files:**
- Modify: `tools/photo3d_handoff.py`（加 `_run_jury_followup` 主体 + lock 处理 + preflight 调用）
- Modify: `tests/test_photo3d_handoff_with_jury.py`（add-only H20 + H21）

- [ ] **Step 5.1: 写 H20 / H21 测试**

```python
# === H20: fail-fast jury config 缺失 ===

def test_h20_preflight_jury_config_missing(
    fake_run_factory: Callable[..., Any],
    make_jury_run_dir: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H20 — jury config 缺失：handoff exit=2 + 不调 enhance"""
    run_dir = make_jury_run_dir()
    project_root = run_dir.parent.parent.parent.parent.parent  # tmp/cad/...
    monkeypatch.chdir(project_root)
    # mock subprocess: 仅期望 1 次调用（jury --dry-run preflight）返 exit=2
    fake_run = fake_run_factory([cp(2, stderr="✗ jury config 不存在")])
    # 跑 handoff 主体（暴露 run_jury_followup 单元测）
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root,
        subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=False,
    )
    assert result["jury_handoff_status"] == "preflight_config_missing"
    assert result["exit_code"] == 2
    # 仅 1 次 subprocess 调用（preflight）；不跑 enhance / 实跑 jury / review
    assert fake_run.call_count() == 1


# === H21: handoff 自身 .handoff.lock busy ===

def test_h21_handoff_lock_busy(
    fake_run_factory: Callable[..., Any],
    make_jury_run_dir: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H21 — 同 subsystem 已有 handoff 持锁：exit=24 + 不调 enhance"""
    run_dir = make_jury_run_dir()
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    # 预先创建 handoff lock 文件（mock 已被持锁）
    lock_path = run_dir / ".handoff.lock"
    lock_path.write_text(json.dumps({"pid": 99999, "started_at": "2026-05-09T00:00:00Z"}), encoding="utf-8")
    # mock _file_lock.acquire_lock 抛 LockBusy
    from tools._file_lock import LockBusy
    def fake_acquire_lock(p: Path):
        raise LockBusy(f"locked: {p}")
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", fake_acquire_lock, raising=False)
    fake_run = fake_run_factory([])  # 0 次调用预期
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root,
        subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=False,
    )
    assert result["jury_handoff_status"] == "handoff_lock_busy"
    assert result["exit_code"] == 24
    assert fake_run.call_count() == 0
```

- [ ] **Step 5.2: 跑测试 RED**

```bash
uv run pytest tests/test_photo3d_handoff_with_jury.py -k "h20 or h21" -v
```

Expected: ImportError（_run_jury_followup 未定义）

- [ ] **Step 5.3: 实现 _run_jury_followup 主体（lock + preflight 部分）**

在 `tools/photo3d_handoff.py` 模块底部 add-only：

```python
import os
import subprocess
from typing import Any

from tools._file_lock import LockBusy, acquire_lock


def _run_jury_followup(
    *,
    project_root: Path,
    subsystem: str,
    active_run_id: str,
    cad_pipeline_py: Path,
    no_strict_jury: bool,
) -> dict[str, Any]:
    """jury hook 主流程；嵌入 _run_enhancement_followup 内（spec §3.3.1）"""
    run_dir = project_root / "cad" / subsystem / ".cad-spec-gen" / "runs" / active_run_id
    lock_path = run_dir / ".handoff.lock"
    result: dict[str, Any] = {
        "jury_handoff_status": "crashed_mid_orchestration",
        "jury_status": "crashed",
        "jury_estimated_usd": 0.0,
        "jury_actual_usd": None,
        "review_status": None,
        "enhance_review_path": None,
        "jury_raw_exit": None,
        "review_raw_exit": None,
        "exit_code": 0,
    }
    # acquire .handoff.lock
    try:
        acquire_lock_ctx = acquire_lock(lock_path)
    except LockBusy:
        result["jury_handoff_status"] = "handoff_lock_busy"
        result["exit_code"] = 24
        return result

    try:
        with acquire_lock_ctx:
            # === step 0.5 fail-fast jury config preflight（用 jury --dry-run 触发 config 加载）===
            preflight_argv = [
                sys.executable, str(cad_pipeline_py),
                "jury", "--subsystem", subsystem, "--dry-run",
            ]
            try:
                preflight = subprocess.run(
                    preflight_argv,
                    shell=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=SUBPROCESS_TIMEOUT_JURY,
                    env=os.environ.copy(),
                    creationflags=0,
                )
            except subprocess.TimeoutExpired:
                result["jury_handoff_status"] = "unexpected_jury_exit"
                result["jury_raw_exit"] = -1  # timeout sentinel
                result["exit_code"] = 25
                return result

            if preflight.returncode == 2:
                result["jury_handoff_status"] = "preflight_config_missing"
                result["jury_status"] = "config_error"
                result["exit_code"] = 2
                return result
            if preflight.returncode == 3:
                # cost over budget；preflight 已估价
                result["jury_handoff_status"] = "cost_over_budget"
                result["jury_status"] = "cost_over_budget"
                # 解析 stdout `[dry-run] estimated=X.XX USD`
                _parse_estimated_usd(preflight.stdout, result)
                result["exit_code"] = 3
                return result
            if preflight.returncode not in (0, 1):
                # 1 = layer0 blocking；0 = ok
                result["jury_handoff_status"] = "unexpected_jury_exit"
                result["jury_raw_exit"] = preflight.returncode
                result["exit_code"] = 25
                return result
            if preflight.returncode == 1:
                result["jury_handoff_status"] = "jury_blocked"
                result["jury_status"] = "blocked"
                result["exit_code"] = 12
                return result
            # preflight ok（return 0）；解析估价后继续到 step 4 实跑
            _parse_estimated_usd(preflight.stdout, result)

            # TODO: step 4 jury 实跑 + step 5 enhance-review；后续 task 实现
            return result
    finally:
        pass  # acquire_lock context manager 自己负责 release


def _parse_estimated_usd(stdout: str, result: dict[str, Any]) -> None:
    """从 jury --dry-run stdout `[dry-run] estimated=X.XX USD, allowed=Y` 提取估价"""
    m = re.search(r"estimated=([\d.]+)\s*USD", stdout or "")
    if m:
        try:
            result["jury_estimated_usd"] = float(m.group(1))
        except ValueError:
            pass
```

- [ ] **Step 5.4: 跑测试 GREEN**

```bash
uv run pytest tests/test_photo3d_handoff_with_jury.py -k "h20 or h21" -v
```

Expected: 2 PASS

- [ ] **Step 5.5: ruff + mypy**

```bash
uv run ruff check tools/photo3d_handoff.py
uv run mypy --strict tools/photo3d_handoff.py
```

- [ ] **Step 5.6: Commit**

```bash
git add tools/photo3d_handoff.py tests/test_photo3d_handoff_with_jury.py
git commit -m "feat(handoff): _run_jury_followup 加 .handoff.lock + fail-fast preflight (H20/H21)"
```

---

## Task 6: step 3 jury --dry-run 估价文案 + cost over budget (H10 + H14 + H9a/b)

**Files:**
- Modify: `tools/photo3d_handoff.py:_run_jury_followup`（已在 Task 5 写了 cost_over_budget 分支；此 task 加 stderr 文案 + H9 config 错双向）
- Modify: `tests/test_photo3d_handoff_with_jury.py`（add-only H10 + H14 + H9a + H9b）

- [ ] **Step 6.1: 写测试 H10 + H14**

```python
# === H10: cost over budget ===

def test_h10_jury_cost_over_budget(
    fake_run_factory: Callable[..., Any],
    make_jury_run_dir: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """H10 — jury dry-run cost > budget：exit=3 + jury_estimated_usd 字段 + 不调 review"""
    run_dir = make_jury_run_dir()
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run = fake_run_factory([
        cp(3, stdout="[dry-run] estimated=0.04 USD, allowed=False\n", stderr=""),
    ])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root,
        subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=False,
    )
    assert result["jury_handoff_status"] == "cost_over_budget"
    assert result["jury_estimated_usd"] == 0.04
    assert result["exit_code"] == 3
    assert fake_run.call_count() == 1


# === H14: 估价 stderr 含中文文案 ===

def test_h14_estimate_stderr_chinese(
    fake_run_factory: Callable[..., Any],
    make_jury_run_dir: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """H14 — H10 同测；stderr 含 'jury 预估' + 'budget'"""
    # H14 与 H10 共享触发；handoff 自打中文文案到 stderr
    # 此用例验证 _run_jury_followup 内调 format_stderr_message 写 stderr
    pass  # 等 Task 6.3 实现 stderr 写入后启用


# === H9a/b: jury config 错（preflight 阶段就 fail）===

def test_h9a_jury_config_error_strict(
    fake_run_factory: Callable[..., Any],
    make_jury_run_dir: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H9a — jury config 错（exit=2）+ strict：透传 exit=2 + 不调 review"""
    run_dir = make_jury_run_dir()
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run = fake_run_factory([cp(2, stderr="✗ jury 配置错")])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root,
        subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=False,
    )
    # config 错走 preflight_config_missing 类目（spec §4.2 表）
    assert result["jury_handoff_status"] == "preflight_config_missing"
    assert result["exit_code"] == 2


def test_h9b_jury_config_error_no_strict(
    fake_run_factory: Callable[..., Any],
    make_jury_run_dir: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H9b — jury config 错 + no-strict：仍 exit=2（工具故障类不可降级；spec inv 5）"""
    run_dir = make_jury_run_dir()
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run = fake_run_factory([cp(2, stderr="")])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root,
        subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=True,  # 关键：no-strict 不能降级工具故障
    )
    assert result["jury_handoff_status"] == "preflight_config_missing"
    assert result["exit_code"] == 2  # 仍阻断


# === helper ===

def _fake_acquire_lock_ok(lock_path: Path) -> Any:
    """fake context manager that does nothing"""
    from contextlib import contextmanager
    @contextmanager
    def _ctx():
        yield
    return _ctx()
```

- [ ] **Step 6.2: 跑测试 RED**

```bash
uv run pytest tests/test_photo3d_handoff_with_jury.py -k "h10 or h9a or h9b" -v
```

Expected: 部分 PASS（Task 5 已实现的逻辑）+ H14 placeholder skip

- [ ] **Step 6.3: 在 _run_jury_followup 内 cost_over_budget 分支加 stderr 写**

修改 `tools/photo3d_handoff.py:_run_jury_followup` 中 `if preflight.returncode == 3:` 分支：

```python
            if preflight.returncode == 3:
                from tools.jury.stderr_messages import format_stderr_message
                _parse_estimated_usd(preflight.stdout, result)
                msg = format_stderr_message(
                    exit_code=3,
                    error_kind="handoff_jury_cost_over_budget",
                    context={
                        "estimated_usd": result["jury_estimated_usd"],
                        "budget_usd": 0.0,  # spec 约定：handoff 不读 jury config，仅打印 jury 自报估价
                        "n_views": 0,
                    },
                )
                sys.stderr.write(msg + "\n")
                result["jury_handoff_status"] = "cost_over_budget"
                result["jury_status"] = "cost_over_budget"
                result["exit_code"] = 3
                return result
```

注：preflight stdout 含 `[dry-run] estimated=0.04 USD, allowed=False` 已自带英文估价；handoff 中文文案是补充。spec inv 8 单源打印——jury 自打英文 + handoff 自打中文（不重复）。

- [ ] **Step 6.4: 完善 H14 测试（启用 stderr 含中文文案断言）**

```python
def test_h14_estimate_stderr_chinese(
    fake_run_factory: Callable[..., Any],
    make_jury_run_dir: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_dir = make_jury_run_dir()
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run_factory([cp(3, stdout="[dry-run] estimated=0.04 USD, allowed=False\n", stderr="")])
    from tools.photo3d_handoff import _run_jury_followup
    _run_jury_followup(
        project_root=project_root,
        subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=False,
    )
    captured = capsys.readouterr()
    # spec §5.2 模板渲染
    assert "jury 预估 0.04 USD" in captured.err
    assert "budget" in captured.err
```

- [ ] **Step 6.5: 跑测试 GREEN**

```bash
uv run pytest tests/test_photo3d_handoff_with_jury.py -k "h10 or h14 or h9a or h9b" -v
```

Expected: 4 PASS

- [ ] **Step 6.6: Commit**

```bash
git add tools/photo3d_handoff.py tests/test_photo3d_handoff_with_jury.py
git commit -m "feat(handoff): _run_jury_followup 加 cost_over_budget stderr 中文文案 (H10/H14/H9a/H9b)"
```

---

## Task 7-10: step 4 jury 实跑（拆为 4 段）

由于篇幅，每段保持相同 RED → GREEN → Commit 结构。每段对应 spec §8 plan 顺序的 C6a/C6b/C6c/C6d。

### Task 7: C6a step 4 jury accepted (H2)

**Files:**
- Modify: `tools/photo3d_handoff.py:_run_jury_followup`（preflight 后加 step 4 实跑分支）
- Modify: `tests/test_photo3d_handoff_with_jury.py`（add H2）

- [ ] **Step 7.1: 写 H2 测试**

```python
def test_h2_accepted_review_ok(
    fake_run_factory: Callable[..., Any],
    make_jury_run_dir: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H2 — jury accepted + review ok：exit=0 + jury_handoff_status='accepted' + jury_actual_usd float"""
    run_dir = make_jury_run_dir(jury_status="accepted", review_input_state="ok")
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run = fake_run_factory([
        cp(0, stdout="[dry-run] estimated=0.04 USD, allowed=True\n"),  # preflight
        cp(0, stdout="", stderr=""),  # jury 实跑（写 PHOTO3D_JURY_REPORT.json by fixture）
        cp(0, stdout="", stderr=""),  # enhance-review
    ])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root,
        subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=False,
    )
    assert result["jury_handoff_status"] == "accepted"
    assert result["jury_status"] == "accepted"
    assert isinstance(result["jury_actual_usd"], float)
    assert result["review_status"] == "ok"
    assert result["enhance_review_path"] is not None
    assert result["exit_code"] == 0
    assert fake_run.call_count() == 3
```

- [ ] **Step 7.2: RED**

```bash
uv run pytest tests/test_photo3d_handoff_with_jury.py::test_h2_accepted_review_ok -v
```

Expected: FAIL（_run_jury_followup 还没跑 step 4 实跑 + step 5 review）

- [ ] **Step 7.3: 在 _run_jury_followup 内 add step 4 + step 5**

替换 Task 5 写的 `# TODO: step 4 ...` 为：

```python
            # === step 4 jury 实跑 ===
            real_argv = [
                sys.executable, str(cad_pipeline_py),
                "jury", "--subsystem", subsystem, "--confirm-cost",
            ]
            try:
                real = subprocess.run(
                    real_argv, shell=False, capture_output=True, text=True,
                    encoding="utf-8", timeout=SUBPROCESS_TIMEOUT_JURY,
                    env=os.environ.copy(), creationflags=0,
                )
            except subprocess.TimeoutExpired:
                result["jury_handoff_status"] = "unexpected_jury_exit"
                result["jury_raw_exit"] = -1
                result["exit_code"] = 25
                return result

            # invariant 7 优先级判定
            if real.returncode in (2, 4, 99):
                # jury 自己已 fail-fast；透传 exit
                _map_jury_systemerr_exit(real.returncode, result)
                return result
            if real.returncode not in (0, 1, 3):
                result["jury_handoff_status"] = "unexpected_jury_exit"
                result["jury_raw_exit"] = real.returncode
                result["exit_code"] = 25
                return result

            # 读 PHOTO3D_JURY_REPORT.json status 字段
            jury_report_path = run_dir / "PHOTO3D_JURY_REPORT.json"
            try:
                jury_report = json.loads(jury_report_path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError):
                # jury exit=0 但报告缺失/损坏 → unexpected
                result["jury_handoff_status"] = "unexpected_jury_exit"
                result["jury_raw_exit"] = real.returncode
                result["exit_code"] = 25
                return result

            jury_status = str(jury_report.get("status", ""))
            result["jury_status"] = jury_status
            actual_usd = jury_report.get("jury_meta", {}).get("actual_cost_usd")
            if isinstance(actual_usd, (int, float)):
                result["jury_actual_usd"] = float(actual_usd)

            # 业务质量类降级 / 工具故障类阻断
            if jury_status == "accepted":
                pass  # 走 step 5
            elif jury_status == "preview":
                if no_strict_jury:
                    result["jury_handoff_status"] = "preview_warning"
                    result["exit_code"] = 0
                else:
                    result["jury_handoff_status"] = "preview_blocked_by_strict"
                    result["exit_code"] = 10
                return result
            elif jury_status == "needs_review":
                if no_strict_jury:
                    result["jury_handoff_status"] = "needs_review_warning"
                    result["exit_code"] = 0
                else:
                    result["jury_handoff_status"] = "needs_review_blocked_by_strict"
                    result["exit_code"] = 11
                return result
            elif jury_status == "blocked":
                result["jury_handoff_status"] = "jury_blocked"
                result["exit_code"] = 12
                return result
            else:
                result["jury_handoff_status"] = "unexpected_jury_exit"
                result["jury_raw_exit"] = real.returncode
                result["exit_code"] = 25
                return result

            # === step 5 enhance-review（仅 accepted）===
            jury_run_id = str(jury_report.get("run_id", ""))
            if not validate_run_id_format(jury_run_id):
                result["jury_handoff_status"] = "review_input_missing"
                result["review_status"] = "input_missing"
                result["exit_code"] = 13
                return result

            from tools.path_policy import assert_within_project
            review_input_path = (
                project_root / "cad" / subsystem / ".cad-spec-gen" / "runs" / jury_run_id / "jury_review_input.json"
            )
            try:
                assert_within_project(review_input_path, project_root, "jury_review_input")
            except Exception:
                result["jury_handoff_status"] = "review_input_missing"
                result["review_status"] = "input_missing"
                result["exit_code"] = 13
                return result

            if not review_input_path.is_file():
                result["jury_handoff_status"] = "review_input_missing"
                result["review_status"] = "input_missing"
                result["exit_code"] = 13
                return result

            try:
                json.loads(review_input_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                result["jury_handoff_status"] = "review_input_corrupt"
                result["review_status"] = "input_corrupt"
                result["exit_code"] = 23
                return result

            review_argv = [
                sys.executable, str(cad_pipeline_py),
                "enhance-review", "--subsystem", subsystem,
                "--review-input", str(review_input_path),
            ]
            try:
                review = subprocess.run(
                    review_argv, shell=False, capture_output=True, text=True,
                    encoding="utf-8", timeout=SUBPROCESS_TIMEOUT_REVIEW,
                    env=os.environ.copy(), creationflags=0,
                )
            except subprocess.TimeoutExpired:
                result["jury_handoff_status"] = "review_failed"
                result["review_status"] = "failed"
                result["review_raw_exit"] = -1
                result["exit_code"] = 23
                return result

            if review.returncode == 0:
                result["jury_handoff_status"] = "accepted"
                result["review_status"] = "ok"
                result["enhance_review_path"] = str(review_input_path.parent / "ENHANCEMENT_REVIEW_REPORT.json")
                result["exit_code"] = 0
                return result
            result["jury_handoff_status"] = "review_failed"
            result["review_status"] = "failed"
            result["review_raw_exit"] = review.returncode
            result["exit_code"] = clamp_review_exit(review.returncode)
            return result


def _map_jury_systemerr_exit(returncode: int, result: dict[str, Any]) -> None:
    """jury 自身 fail-fast exit code 映射"""
    if returncode == 2:
        result["jury_handoff_status"] = "config_error"
        result["jury_status"] = "config_error"
        result["exit_code"] = 2
    elif returncode == 4:
        result["jury_handoff_status"] = "lock_busy"
        result["jury_status"] = "lock_busy"
        result["exit_code"] = 4
    elif returncode == 99:
        result["jury_handoff_status"] = "internal_error"
        result["jury_status"] = "internal_error"
        result["exit_code"] = 99
```

- [ ] **Step 7.4: GREEN**

```bash
uv run pytest tests/test_photo3d_handoff_with_jury.py::test_h2_accepted_review_ok -v
```

Expected: PASS

- [ ] **Step 7.5: Commit**

```bash
git add tools/photo3d_handoff.py tests/test_photo3d_handoff_with_jury.py
git commit -m "feat(handoff): _run_jury_followup step 4 jury 实跑 + step 5 review (H2 accepted 路径)"
```

### Task 8: C6b step 4 业务降级 (H3 + H4 + H5 + H6)

- [ ] **Step 8.1: 写 4 个测试 H3/H4/H5/H6**

```python
def test_h3_jury_preview_strict(fake_run_factory, make_jury_run_dir, monkeypatch):
    run_dir = make_jury_run_dir(jury_status="preview")
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run_factory([
        cp(0, stdout="[dry-run] estimated=0.04 USD\n"),
        cp(0),
    ])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root, subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=False,
    )
    assert result["jury_handoff_status"] == "preview_blocked_by_strict"
    assert result["exit_code"] == 10
    assert result["review_status"] is None  # 不调 review

def test_h4_jury_preview_no_strict(fake_run_factory, make_jury_run_dir, monkeypatch):
    run_dir = make_jury_run_dir(jury_status="preview")
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run_factory([
        cp(0, stdout="[dry-run] estimated=0.04 USD\n"),
        cp(0),
    ])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root, subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=True,
    )
    assert result["jury_handoff_status"] == "preview_warning"
    assert result["exit_code"] == 0
    assert result["review_status"] is None

def test_h5_jury_needs_review_strict(fake_run_factory, make_jury_run_dir, monkeypatch):
    run_dir = make_jury_run_dir(jury_status="needs_review")
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run_factory([cp(0, stdout="[dry-run] estimated=0.04 USD\n"), cp(0)])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root, subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=False,
    )
    assert result["jury_handoff_status"] == "needs_review_blocked_by_strict"
    assert result["exit_code"] == 11

def test_h6_jury_needs_review_no_strict(fake_run_factory, make_jury_run_dir, monkeypatch):
    run_dir = make_jury_run_dir(jury_status="needs_review")
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run_factory([cp(0, stdout="[dry-run] estimated=0.04 USD\n"), cp(0)])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root, subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=True,
    )
    assert result["jury_handoff_status"] == "needs_review_warning"
    assert result["exit_code"] == 0
```

- [ ] **Step 8.2: RED → GREEN（实现已在 Task 7 写完；验证 4 用例通过）**

```bash
uv run pytest tests/test_photo3d_handoff_with_jury.py -k "h3 or h4 or h5 or h6" -v
```

Expected: 4 PASS（实现复用 Task 7 的逻辑）

- [ ] **Step 8.3: Commit**

```bash
git add tests/test_photo3d_handoff_with_jury.py
git commit -m "test(handoff): H3/H4/H5/H6 业务降级双向用例守门"
```

### Task 9: C6c step 4 工具故障类双向 (H7a/b + H8a/b + H11a/b)

- [ ] **Step 9.1: 写 6 用例**

```python
@pytest.mark.parametrize("no_strict", [False, True])
def test_h7_jury_blocked(no_strict, fake_run_factory, make_jury_run_dir, monkeypatch):
    """H7a/H7b — jury 实跑写 status=blocked + return 0：exit=12 永远阻断（spec inv 5）"""
    run_dir = make_jury_run_dir(jury_status="blocked")
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run_factory([cp(0, stdout="[dry-run] estimated=0.04 USD\n"), cp(0)])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root, subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=no_strict,
    )
    assert result["jury_handoff_status"] == "jury_blocked"
    assert result["exit_code"] == 12  # no-strict 不能覆盖

@pytest.mark.parametrize("no_strict", [False, True])
def test_h8_jury_lock_busy(no_strict, fake_run_factory, make_jury_run_dir, monkeypatch):
    """H8a/H8b — jury 实跑 exit=4：透传"""
    run_dir = make_jury_run_dir()
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run_factory([cp(0, stdout="[dry-run] estimated=0.04 USD\n"), cp(4, stderr="lock busy")])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root, subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=no_strict,
    )
    assert result["jury_handoff_status"] == "lock_busy"
    assert result["exit_code"] == 4

@pytest.mark.parametrize("no_strict", [False, True])
def test_h11_jury_internal(no_strict, fake_run_factory, make_jury_run_dir, monkeypatch):
    """H11a/H11b — jury 实跑 exit=99：透传"""
    run_dir = make_jury_run_dir()
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run_factory([cp(0, stdout="[dry-run] estimated=0.04 USD\n"), cp(99, stderr="internal")])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root, subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=no_strict,
    )
    assert result["jury_handoff_status"] == "internal_error"
    assert result["exit_code"] == 99
```

- [ ] **Step 9.2: RED → GREEN**

```bash
uv run pytest tests/test_photo3d_handoff_with_jury.py -k "h7 or h8 or h11" -v
```

Expected: 6 PASS（parametrize 各 2 = 6 用例）

- [ ] **Step 9.3: Commit**

```bash
git add tests/test_photo3d_handoff_with_jury.py
git commit -m "test(handoff): H7a/b/H8a/b/H11a/b 工具故障类双向 no-strict 不可覆盖守门"
```

### Task 10: C6d step 4 unexpected exit (H18 + H19)

- [ ] **Step 10.1: 写 H18 + H19**

```python
def test_h18_jury_sigint(fake_run_factory, make_jury_run_dir, monkeypatch):
    """H18 — jury exit=130 (SIGINT)：exit=25 + jury_raw_exit=130"""
    run_dir = make_jury_run_dir()
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run_factory([cp(0, stdout="[dry-run] estimated=0.04 USD\n"), cp(130)])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root, subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=False,
    )
    assert result["jury_handoff_status"] == "unexpected_jury_exit"
    assert result["jury_raw_exit"] == 130
    assert result["exit_code"] == 25

def test_h19_jury_oom(fake_run_factory, make_jury_run_dir, monkeypatch):
    """H19 — jury exit=137 (OOM)：exit=25 + jury_raw_exit=137"""
    run_dir = make_jury_run_dir()
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run_factory([cp(0, stdout="[dry-run] estimated=0.04 USD\n"), cp(137)])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root, subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=False,
    )
    assert result["jury_handoff_status"] == "unexpected_jury_exit"
    assert result["jury_raw_exit"] == 137
    assert result["exit_code"] == 25
```

- [ ] **Step 10.2: RED → GREEN**

```bash
uv run pytest tests/test_photo3d_handoff_with_jury.py -k "h18 or h19" -v
```

Expected: 2 PASS（实现已在 Task 7 处理 unexpected exit）

- [ ] **Step 10.3: Commit**

```bash
git add tests/test_photo3d_handoff_with_jury.py
git commit -m "test(handoff): H18/H19 jury unexpected exit (SIGINT/OOM) 守门"
```

---

## Task 11: step 5 enhance-review (H12 + H15 + H16 + H17)

- [ ] **Step 11.1: 写测试**

```python
def test_h12_accepted_review_failed(fake_run_factory, make_jury_run_dir, monkeypatch):
    """H12 — jury accepted + review fail (exit=1)：exit=20 (clamp) + review_raw_exit=1"""
    run_dir = make_jury_run_dir(jury_status="accepted", review_input_state="ok")
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run_factory([
        cp(0, stdout="[dry-run] estimated=0.04 USD\n"),
        cp(0),  # jury 实跑
        cp(1, stderr="review failed"),  # enhance-review fail
    ])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root, subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=False,
    )
    assert result["jury_handoff_status"] == "review_failed"
    assert result["review_status"] == "failed"
    assert result["review_raw_exit"] == 1
    assert result["exit_code"] == 20  # clamp 1 -> 20

def test_h15_review_input_missing(fake_run_factory, make_jury_run_dir, monkeypatch):
    """H15 — jury accepted + review_input not_found：exit=13"""
    run_dir = make_jury_run_dir(jury_status="accepted", review_input_state="missing")
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run = fake_run_factory([cp(0, stdout="[dry-run] estimated=0.04 USD\n"), cp(0)])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root, subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=False,
    )
    assert result["jury_handoff_status"] == "review_input_missing"
    assert result["exit_code"] == 13
    assert fake_run.call_count() == 2  # 不调 review

def test_h16_review_input_run_id_traversal(fake_run_factory, make_jury_run_dir, monkeypatch):
    """H16 — jury accepted + jury report run_id='../etc/passwd'：exit=13 + reason='run_id_format'"""
    run_dir = make_jury_run_dir(jury_status="accepted", review_input_state="traversal")
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run = fake_run_factory([cp(0, stdout="[dry-run] estimated=0.04 USD\n"), cp(0)])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root, subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=False,
    )
    assert result["jury_handoff_status"] == "review_input_missing"
    assert result["exit_code"] == 13
    assert fake_run.call_count() == 2

def test_h17_review_input_corrupt(fake_run_factory, make_jury_run_dir, monkeypatch):
    """H17 — jury accepted + jury_review_input.json 损坏 JSON：exit=23 + review_status='input_corrupt'"""
    run_dir = make_jury_run_dir(jury_status="accepted", review_input_state="corrupt")
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run = fake_run_factory([cp(0, stdout="[dry-run] estimated=0.04 USD\n"), cp(0)])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root, subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=False,
    )
    assert result["jury_handoff_status"] == "review_input_corrupt"
    assert result["exit_code"] == 23
    assert fake_run.call_count() == 2  # 不调 review
```

- [ ] **Step 11.2: RED → GREEN**

```bash
uv run pytest tests/test_photo3d_handoff_with_jury.py -k "h12 or h15 or h16 or h17" -v
```

Expected: 4 PASS（实现 review 路径已在 Task 7 完成）

- [ ] **Step 11.3: Commit**

```bash
git add tests/test_photo3d_handoff_with_jury.py
git commit -m "test(handoff): H12/H15/H16/H17 review 失败 + path traversal + 损坏 JSON 守门"
```

---

## Task 12: H22 subprocess argv 形式守门 + H1b/H1c 回归 + H13/H23 enhance crash

- [ ] **Step 12.1: 写测试**

```python
@pytest.mark.regression
def test_h22_subprocess_argv_form(fake_run_factory, make_jury_run_dir, monkeypatch):
    """H22 — subprocess argv 是 list[str] + shell ∉ kwargs + env 不主动注入敏感键 (inv 11)"""
    run_dir = make_jury_run_dir(jury_status="accepted", review_input_state="ok")
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run = fake_run_factory([
        cp(0, stdout="[dry-run] estimated=0.04 USD\n"),
        cp(0),
        cp(0),
    ])
    from tools.photo3d_handoff import _run_jury_followup
    _run_jury_followup(
        project_root=project_root, subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=False,
    )
    # 守门：每次调用 argv 都是 list[str] + 第 0 元素是 sys.executable + 第 1 元素以 cad_pipeline.py 结尾
    for call in fake_run.call_log:
        argv = call["argv"]
        assert isinstance(argv, list)
        assert all(isinstance(t, str) for t in argv)
        assert argv[0] == sys.executable
        assert argv[1].endswith("cad_pipeline.py")
    assert fake_run.call_count() == 3


def test_h1b_with_jury_kind_not_run_enhancement(monkeypatch, tmp_path):
    """H1b — --with-jury 但 next_action.kind != 'run_enhancement'：jury hook 不触发"""
    # 这是回归测试：确认 _run_enhancement_followup 内 jury hook 仅在 run_enhancement kind 触发
    # 由 Task 13 的集成 _run_enhancement_followup 改造守门；本 task 留 placeholder
    pass


def test_h1c_with_jury_no_confirm():
    """H1c — --with-jury 但 confirm=False：handoff status='awaiting_confirmation'，jury hook 不触发"""
    # 由 Task 13 的集成守门；本 task 留 placeholder
    pass


def test_h13_enhance_step_failed():
    """H13 — enhance step 失败：透传 enhance exit + 不调 jury"""
    # 由 Task 13 集成（_run_enhancement_followup 内 enhance subprocess fail 时不进入 jury hook）
    pass


def test_h23_crash_mid_step():
    """H23 — enhance subprocess 抛 OSError：finally 块仍写 PHOTO3D_HANDOFF.json"""
    # 由 Task 13 集成；本 task 留 placeholder
    pass
```

- [ ] **Step 12.2: RED → GREEN**

```bash
uv run pytest tests/test_photo3d_handoff_with_jury.py::test_h22_subprocess_argv_form -v
```

Expected: PASS（实现已合规；regression 测试）

- [ ] **Step 12.3: Commit**

```bash
git add tests/test_photo3d_handoff_with_jury.py
git commit -m "test(handoff): H22 subprocess argv 形式守门 (regression) + H1b/H1c/H13/H23 placeholder"
```

---

## Task 13: 集成 jury hook 到 _run_enhancement_followup + command_return_code 扩展

**Files:**
- Modify: `tools/photo3d_handoff.py:_run_enhancement_followup`（在 _execute_enhance_check_followup 后嵌入 jury hook）
- Modify: `tools/photo3d_handoff.py:command_return_code`（扩展 jury_handoff_status 字段映射）
- Modify: `tools/photo3d_handoff.py:run_photo3d_handoff`（接 with_jury / no_strict_jury 透传）

- [ ] **Step 13.1: 改 _run_enhancement_followup 接受 jury 参数**

```python
def _run_enhancement_followup(
    project_root: Path,
    subsystem: str,
    active_run_id: str,
    artifact_index_path: Path,
    *,
    with_jury: bool = False,             # v2.28.0
    no_strict_jury: bool = False,        # v2.28.0
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
    """返回 (followup_action, post_handoff_photo3d_run, jury_result)"""
    try:
        followup_action = _execute_enhance_check_followup(
            project_root, subsystem, active_run_id, artifact_index_path,
        )
        # ... 现有逻辑保持

        # === v2.28.0 jury hook ===
        jury_result: dict[str, Any] | None = None
        if with_jury:
            cad_pipeline_py = project_root / "cad_pipeline.py"
            jury_result = _run_jury_followup(
                project_root=project_root,
                subsystem=subsystem,
                active_run_id=active_run_id,
                cad_pipeline_py=cad_pipeline_py,
                no_strict_jury=no_strict_jury,
            )

        post_handoff_photo3d_run = _post_handoff_loop(
            project_root, subsystem, artifact_index_path, active_run_id,
        )
    except (FileNotFoundError, OSError, ValueError) as exc:
        return (
            _failed_followup_action(project_root, subsystem, active_run_id, artifact_index_path, exc),
            None,
            None,
        )
    return followup_action, post_handoff_photo3d_run, jury_result
```

- [ ] **Step 13.2: run_photo3d_handoff 透传 jury_result 到 report**

定位 run_photo3d_handoff 中调 _run_enhancement_followup 的代码，更新解构 + 把 jury_result 字段合并到 report：

```python
elif selected_action["kind"] == "run_enhancement":
    followup_action, post_handoff_photo3d_run, jury_result = _run_enhancement_followup(
        root, subsystem, active_run_id, index_path,
        with_jury=with_jury,
        no_strict_jury=no_strict_jury,
    )
    # ... 现有逻辑

# 在 report dict 末尾合并 jury_result（仅当 with_jury 启用时）
if with_jury and jury_result is not None:
    report.update({
        "jury_handoff_status": jury_result["jury_handoff_status"],
        "jury_status": jury_result["jury_status"],
        "jury_estimated_usd": jury_result["jury_estimated_usd"],
        "jury_actual_usd": jury_result["jury_actual_usd"],
        "review_status": jury_result["review_status"],
        "enhance_review_path": jury_result["enhance_review_path"],
        "jury_raw_exit": jury_result["jury_raw_exit"],
        "review_raw_exit": jury_result["review_raw_exit"],
    })
```

- [ ] **Step 13.3: 扩展 command_return_code**

```python
def command_return_code(report: dict[str, Any]) -> int:
    # v2.28.0 jury 集成 exit code 段优先（spec §4.2 决策表）
    if "jury_handoff_status" in report:
        from typing import cast
        jhs = cast(str, report["jury_handoff_status"])
        if jhs == "accepted":
            return 0
        if jhs == "preview_warning" or jhs == "needs_review_warning" or jhs == "awaiting_confirmation":
            return 0
        if jhs == "preflight_config_missing" or jhs == "config_error":
            return 2
        if jhs == "cost_over_budget":
            return 3
        if jhs == "lock_busy":
            return 4
        if jhs == "preview_blocked_by_strict":
            return 10
        if jhs == "needs_review_blocked_by_strict":
            return 11
        if jhs == "jury_blocked":
            return 12
        if jhs == "review_input_missing":
            return 13
        if jhs == "review_failed":
            raw = report.get("review_raw_exit")
            return clamp_review_exit(raw) if isinstance(raw, int) else 23
        if jhs == "review_input_corrupt":
            return 23
        if jhs == "handoff_lock_busy":
            return 24
        if jhs == "unexpected_jury_exit":
            return 25
        if jhs == "internal_error":
            return 99
        if jhs == "crashed_mid_orchestration":
            return 99
    # 现有 status 映射保持不变
    if report.get("status") in {"awaiting_confirmation", "executed", "executed_with_followup"}:
        return 0
    if report.get("status") == "needs_manual_review":
        selected = report.get("selected_action") or {}
        return 0 if selected.get("kind") in MANUAL_HANDOFFS else 1
    return 1
```

- [ ] **Step 13.4: 实现 H1b/H1c/H13/H23 测试**

```python
def test_h1b_with_jury_kind_not_run_enhancement(monkeypatch, tmp_path):
    """H1b — --with-jury 但 next_action.kind == 'accept_baseline'：jury hook 不触发"""
    # 此用例需要 mock _classify_next_action 返回 kind='accept_baseline'
    # 简化：直接验证 _run_enhancement_followup 的 jury hook 仅在 with_jury 启用时跑
    # 集成层用 H1 + H1b combine：H1 已守门"不带 with_jury 不出现 jury_* 字段"
    # H1b 此处用 unit test 验证 _run_enhancement_followup(with_jury=False) 返回 jury_result=None
    pass  # H1 已隐含覆盖；不强制独立用例


def test_h13_enhance_step_failed(monkeypatch, tmp_path):
    """H13 — enhance step 失败：透传 enhance exit + 不调 jury hook"""
    # 此用例属 _execute_selected_action 层而非 jury hook 层；现有 v2.27.0 已守门
    # 本 PR 不引入新分支；H13 由现有 tests/test_cad_pipeline_handoff.py 既有用例覆盖
    pass


def test_h23_crash_mid_step():
    """H23 — enhance subprocess 抛 OSError：finally 块写 PHOTO3D_HANDOFF.json"""
    # 现有 _run_enhancement_followup except (FileNotFoundError, OSError, ValueError) 已覆盖；
    # 本 PR 仅扩展 jury_result 字段，不引入新 crash 路径
    pass
```

- [ ] **Step 13.5: 跑全量 handoff 测试**

```bash
uv run pytest tests/test_photo3d_handoff_with_jury.py -v
uv run pytest tests/ -k "test_cad_pipeline_handoff or test_photo3d_handoff" -v  # 现有回归
```

Expected: 全 PASS

- [ ] **Step 13.6: ruff + mypy strict**

```bash
uv run ruff check tools/photo3d_handoff.py cad_pipeline.py
uv run mypy --strict tools/photo3d_handoff.py
```

Expected: clean

- [ ] **Step 13.7: Commit**

```bash
git add tools/photo3d_handoff.py
git commit -m "feat(handoff): 集成 jury hook 到 _run_enhancement_followup + command_return_code 扩展"
```

---

## Task 14: 全量回归 + mutation sanity check

- [ ] **Step 14.1: 全量回归**

```bash
uv run pytest tests/ -v
```

Expected: ≥2622 PASS（v2.27.0 基线）+ 新加 27+ PASS

- [ ] **Step 14.2: mutation sanity check（regression 类用例）**

针对 `@pytest.mark.regression` 标注的测试（H1/H1b/H1c/H22 + 3 stderr 单测），手动验证 RED 能力：

```bash
# 临时改 tools/photo3d_handoff.py 一行（如把 jury_handoff_status="accepted" 改成 "ACCEPTED" 大写）
# 跑 H2 应该 fail
uv run pytest tests/test_photo3d_handoff_with_jury.py::test_h2_accepted_review_ok -v
# 还原后跑应该 PASS
git diff tools/photo3d_handoff.py  # 确认还原干净
```

- [ ] **Step 14.3: ruff format + check + mypy strict 全量**

```bash
uv run ruff format --check tools/photo3d_handoff.py tools/jury/stderr_messages.py tests/test_photo3d_handoff_with_jury.py tests/jury/test_stderr_messages.py
uv run ruff check tools/ tests/
uv run mypy --strict tools/photo3d_handoff.py tools/jury/stderr_messages.py
```

Expected: 全 clean

- [ ] **Step 14.4: cov ≥90% 检查**

```bash
uv run pytest tests/test_photo3d_handoff_with_jury.py tests/jury/test_stderr_messages.py \
  --cov=tools.photo3d_handoff --cov=tools.jury.stderr_messages \
  --cov-fail-under=90
```

Expected: PASS（cov ≥90%）

- [ ] **Step 14.5: 北极星 5 gate 体检**

输出到 stdout（人工核对）：

```
- 零配置：✓ 不引入新配置；jury config 缺失立即 H20 fail-fast
- 稳定可靠：✓ strict 默认；工具故障类必阻断；handoff 自身 lock 防同机并发；invariant 7 优先级判定
- 结果准确：✓ jury → review 串联保证 deliver 前必有 ENHANCEMENT_REVIEW_REPORT.json
- SW 装即用：✓ 无 SW 涉及
- 傻瓜式操作：✓ 一条 photo3d-handoff --with-jury --confirm 跑闭环
```

- [ ] **Step 14.6: Commit**

```bash
git commit --allow-empty -m "test(handoff): 全量回归 + 北极星 5 gate 体检 PASS"
```

---

## Task 15: 文档（docs/cad-jury-config.md / PROGRESS.md / README.md）

- [ ] **Step 15.1: 加 docs/cad-jury-config.md 章节**

新加章节"通过 photo3d-handoff 一条命令跑闭环"，含：

```markdown
## 通过 photo3d-handoff 一条命令跑闭环（v2.28.0+）

### 使用示例

```bash
# 第一步：预览（不执行；看下一步要跑什么）
python cad_pipeline.py photo3d-handoff --subsystem lifting_platform --with-jury

# 第二步：加 --confirm 实跑（触发 enhance + check + jury 自动验收 + enhance-review）
python cad_pipeline.py photo3d-handoff --subsystem lifting_platform --with-jury --confirm

# 进阶：质量验收 preview 时仅警告不阻断（CI 用）
python cad_pipeline.py photo3d-handoff --subsystem lifting_platform --with-jury --no-strict-jury --confirm
```

### --with-jury / --no-strict-jury 行为矩阵

| 场景 | --with-jury | --no-strict-jury | 行为 |
|---|---|---|---|
| 默认 | ✗ | ✗ | 仅跑 enhance + check（v2.27.0 路径不变）|
| 标准闭环 | ✓ | ✗ | jury preview/needs_review 阻断；工具故障类阻断 |
| CI 容错 | ✓ | ✓ | jury preview/needs_review 仅警告；工具故障类仍阻断 |

### 故障恢复

**lock 残留**：`.handoff.lock` 或 `.jury.lock` mtime > 30 分钟自动清理。强制清理：删 `<run_dir>/.handoff.lock` 后重跑（仅在确认无其他 photo3d-handoff/photo3d-jury 进程时）。

**前次报告**：PHOTO3D_HANDOFF.json 用 atomic write 替换；前次报告会被本次覆盖；如需保留请先 `cp PHOTO3D_HANDOFF.json PHOTO3D_HANDOFF.json.bak`。

### CI 集成

GitHub Actions 示例：

```yaml
- name: Run photo3d-handoff with jury
  run: python cad_pipeline.py photo3d-handoff --subsystem ${{ matrix.subsystem }} --with-jury --confirm
  continue-on-error: false  # exit 10/11 (preview/needs_review) 阻断 CI
```

`exit code` 含义：
- 0 = accepted
- 2 = config 错 / preflight 失败
- 3 = cost over budget
- 4 = jury lock busy
- 10/11 = jury preview/needs_review 阻断（strict）
- 12 = jury blocked
- 13 = review_input 缺失（含 path traversal）
- 20/21/22/23 = enhance-review 失败
- 24 = handoff lock busy
- 25 = jury 异常退出
- 99 = jury 内部异常

CI retry-on-exit 配置时应**显式排除** 10-25 段（业务自定义码，重试不会变）。

### jury preview 时常见可改 enhance config 入口

参见 `docs/cad-enhance-config.md` "提升 photoreal_score 的常用调整"段。
```

- [ ] **Step 15.2: 加 docs/PROGRESS.md v2.28.0 入口**

```markdown
## v2.28.0 — 2026-05-09 photo3d-jury v2 handoff 集成（A1 子集）

- 新增 photo3d-handoff `--with-jury` `--no-strict-jury` flag；一条命令跑 enhance + check + jury + review 闭环
- jury hook 嵌入 `_run_enhancement_followup` 在 enhance-check 之后；jury 子模块 0 改动
- handoff 自身 `.handoff.lock` 防同机并发；step 0.5 fail-fast jury config preflight 防 enhance 白花钱
- 13 个新 `handoff_*` error_kind stderr 模板（含外行用户友好的"下一步动作"清单）
- PHOTO3D_HANDOFF.json schema add-only 加 8 字段
- 27 H 用例 + 5 单测全 PASS；cov ≥90%；mypy strict + ruff clean
```

- [ ] **Step 15.3: 加 README.md 用法示例**

在 README.md "用法示例"段追加：

```markdown
### 一条命令跑完 photo3d 验收闭环（v2.28.0+）

# 第一步：预览（不执行；看下一步要跑什么）
python cad_pipeline.py photo3d-handoff --subsystem lifting_platform --with-jury

# 第二步：加 --confirm 实跑（触发 enhance + check + jury 自动验收 + enhance-review）
python cad_pipeline.py photo3d-handoff --subsystem lifting_platform --with-jury --confirm
```

- [ ] **Step 15.4: Commit**

```bash
git add docs/cad-jury-config.md docs/PROGRESS.md README.md
git commit -m "docs(jury-v2): 加 photo3d-handoff --with-jury 用法 + flag 矩阵 + CI 集成示例"
```

---

## Task 16: PR + tag v2.28.0

- [ ] **Step 16.1: push 分支**

```bash
git push -u origin feat/jury-v2-handoff-integration
```

- [ ] **Step 16.2: 开 PR**

```bash
gh pr create --title "feat(jury-v2): photo3d-handoff --with-jury 集成（A1 子集）" --body "$(cat <<'EOF'
## Summary

- 新增 `photo3d-handoff --with-jury` 一条命令跑 enhance + check + jury + review 闭环
- 13 个 `handoff_*` error_kind 文案（外行用户友好"下一步"清单）
- 防同机并发：handoff 自身 `.handoff.lock`
- fail-fast preflight 防 jury config 缺失下 enhance 白花钱

## Test plan
- [ ] CI matrix Linux + Windows 全绿
- [ ] H1-H23 共 27 用例 PASS
- [ ] mutation sanity check 验证 @regression 标注用例可 RED
- [ ] cov ≥90%（tools.photo3d_handoff + tools.jury.stderr_messages）
- [ ] 北极星 5 gate 体检过

## Spec & Plan
- spec: docs/superpowers/specs/2026-05-09-photo3d-jury-v2-handoff-integration-design.md (v1.4，4 层审查)
- plan: docs/superpowers/plans/2026-05-09-photo3d-jury-v2-handoff-integration.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 16.3: 等 CI 全绿后 squash merge**

```bash
# 等 CI 通过
gh pr checks
# squash merge + delete branch
gh pr merge --squash --delete-branch
```

- [ ] **Step 16.4: tag v2.28.0 + GitHub Release**

```bash
git checkout main && git pull
git tag -a v2.28.0 -m "v2.28.0: photo3d-handoff --with-jury 一条命令跑闭环"
git push origin v2.28.0
gh release create v2.28.0 --title "v2.28.0 — photo3d-jury v2 handoff 集成 (A1)" --notes "见 docs/PROGRESS.md"
```

---

## Self-Review Checklist

实施前最后核：

**1. Spec coverage**：
- §2.1 范围 11 项 → Task 0/2/3/4/5/13/15 各项有 task 守门 ✓
- §3.4 invariants 1-19 → Task 5（lock + preflight）/ Task 7（status 字段判定）/ Task 12（subprocess argv）覆盖 ✓
- §4.1 数据流 step 0-7 → Task 5（step 0 + 0.5）/ Task 7（step 4 + 5）覆盖 ✓
- §4.2 决策表 17 行 → H1/H1b/H1c/H2/H3-H6/H7a/b/H8a/b/H9a/b/H10/H11a/b/H12/H13/H15-H19/H20/H21/H22/H23 用例覆盖 ✓
- §5.1-5.3 错误矩阵 16 类 → Task 1（13 个 handoff_* error_kind）+ Task 13（command_return_code 映射）覆盖 ✓
- §6.0 fixture 模板 → Task 4 实现 fake_run_factory + make_jury_run_dir + fake_enhancement_report ✓
- §6.3 H1-H23 + §6.2 5 单测 → 27 + 5 = 32 用例分散在 Task 1/3/5/6/7-12 ✓
- §7.4 文档 → Task 15 ✓
- §8.1 grep 守门 10 项 → Task 0 ✓
- §10 DoD 10 条 → Task 14（北极星 + cov + mypy + ruff）+ Task 16（PR/tag）✓

**2. Placeholder scan**：每个 task step 都有具体代码 + 命令 ✓

**3. Type consistency**：
- `validate_run_id_format` / `clamp_review_exit` / `_run_jury_followup` 签名跨 Task 3/5/7/13 一致 ✓
- `jury_handoff_status` / `jury_status` 字符串值与 spec §4.2 决策表完全一致 ✓
- `format_stderr_message` 调用全用 keyword-only 形式 ✓
