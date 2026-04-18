# SW self-hosted runner F-1.3j workspace ACL 修复 + F-1.3k K1 第二数据点 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal：** 一次性 admin 清掉 F.1 遗留的 protected-ACL `.pytest_cache` + 在 sw-smoke.yml 加 pre-checkout cleanup step + 修复 line 59 `|| true` 击穿 + 改 skip-guard `real == 2` + 通过 workflow_dispatch 采集 K1 第二数据点 + runbook §7 同步状态升级。

**Architecture：** TDD 双 RED（assert_schema retcode 65 + skip-guard real==2）→ 双 GREEN 实现（assert_schema_py + sw-smoke.yml 3 处）→ feature branch PR → merge → workflow_dispatch K1 采集 → runbook 4 处同步。`.pytest_cache` 一次性 admin 清，靠下次 ghrunner 跑 pytest 自然继承父 workspace 的 ghrunner:M ACL 永不复发。

**Tech Stack：** PowerShell 7+（pwsh）/ Python 3.12 / pytest tmp_path / GitHub Actions self-hosted runner / gh CLI ≥ 2.20 / actionlint ≥ 1.6.20

**Spec：** `docs/superpowers/specs/2026-04-18-sw-self-hosted-runner-f13jk-design.md` v5（511 行 / commit `0a67641`）

**前置：** spec v5 已 commit；本机 admin PowerShell + ghrunner desktop session（runbook §4 Autologon 已配）+ gh CLI ≥ 2.20 + actionlint（任一：本机 / docker / warn-only fallback）

---

### Task 1：S1 admin PowerShell 一次性 fix（手工动作，不 commit）

**Files：** 无（手工 PowerShell 命令）

**前置：** admin PowerShell 已开 / `gh` 已认证

- [ ] **Step 1.1：runner Idle 检查**

```powershell
gh api repos/proecheng/cad-spec-gen/actions/runners --jq '.runners[] | select(.name=="procheng-sw-smoke") | {status, busy}'
```

期望输出：`{"status": "online", "busy": false}`。如果 `busy=true`，等待 GitHub Actions UI 看到 in_progress run 跑完再继续。

- [ ] **Step 1.2：污染目录验证 + LastWriteTime 复核**

```powershell
Test-Path 'D:\actions-runner\_work\cad-spec-gen\cad-spec-gen\.pytest_cache'
(Get-Item 'D:\actions-runner\_work\cad-spec-gen\cad-spec-gen\.pytest_cache').LastWriteTime
```

期望：`True` + 时间 ≈ 2026-04-17 16:09 ± 48h（F.1 baseline 时间戳容差）。如果时间戳是当天新近的（< 48h 内），停 ghrunner Task Scheduler 排查后再继续。

- [ ] **Step 1.3：admin 强删 .pytest_cache**

```powershell
Remove-Item -Recurse -Force 'D:\actions-runner\_work\cad-spec-gen\cad-spec-gen\.pytest_cache'
```

期望：无输出（成功）。Administrators 组有 Full 权限，无视 protected ACL。

- [ ] **Step 1.4：清掉所有 __pycache__ 残留**

```powershell
Get-ChildItem -Path 'D:\actions-runner\_work\cad-spec-gen\cad-spec-gen' `
              -Filter '__pycache__' -Recurse -Force -Directory -EA SilentlyContinue |
  Remove-Item -Recurse -Force
```

期望：无输出。

- [ ] **Step 1.5：验证清空**

```powershell
Test-Path 'D:\actions-runner\_work\cad-spec-gen\cad-spec-gen\.pytest_cache'
```

期望：`False`。

---

### Task 2：S2.0(a) RED — assert_sw_inspect_schema JSONDecodeError 测试

**Files：**
- Create: `tests/test_assert_sw_inspect_schema.py`

- [ ] **Step 2.1：写 RED 测试**

```python
"""F-1.3j+k S2.0(a)：验证 assert_sw_inspect_schema.py 在空文件输入时抛 JSONDecodeError 并以 retcode 65 退出。

当前 main() 无 try/except → AssertionError 抛 retcode=1 → 测试 RED。
S2 commit 1 加 try/except 后 retcode=65 → 测试 GREEN。
"""

import subprocess
import sys
from pathlib import Path


class TestJsonDecodeError:
    def test_empty_file_returns_65(self, tmp_path: Path) -> None:
        """空文件触发 JSONDecodeError，应以 retcode 65 退出（DATAERR sysexits）"""
        empty = tmp_path / "empty.json"
        empty.write_text("", encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "tools/assert_sw_inspect_schema.py", str(empty)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 65, (
            f"expected retcode 65 (DATAERR for JSONDecodeError), got {result.returncode}; "
            f"stderr={result.stderr[:300]}"
        )
        assert "JSONDecodeError" in result.stderr or "json" in result.stderr.lower(), (
            f"expected JSONDecodeError mention in stderr, got: {result.stderr[:300]}"
        )
```

- [ ] **Step 2.2：跑测试验证 RED**

```bash
.venv/Scripts/python.exe -m pytest tests/test_assert_sw_inspect_schema.py::TestJsonDecodeError::test_empty_file_returns_65 -v
```

期望：FAIL，retcode 实际 = 1（AssertionError 抛出）而非 65。这是预期 RED。

---

### Task 3：S2.0(b) RED — sw-smoke.yml skip-guard real==2 测试

**Files：**
- Create: `tests/test_sw_smoke_skip_guard.py`

- [ ] **Step 3.1：写 RED 测试**

```python
"""F-1.3j+k S2.0(b)：验证 sw-smoke.yml line 44-52 skip-guard 真要求 real==2（而非 real>=1）。

当前 sw-smoke.yml line 51 是 `assert real >= 1` → 1 个 testcase 也 PASS → 测试 RED（期望 1 testcase fail 但实际 pass）。
S2 commit 2 改成 `assert real == 2` 后 → 测试 GREEN。
"""

import subprocess
import sys
import textwrap
from pathlib import Path


def _skip_guard_inline_script(xml_path: Path) -> str:
    """把 sw-smoke.yml line 44-52 的 python 块抽成 helper（保持与 yaml 同步：见 spec §3.4 P4-F）。

    v5 P4-F 修订：assert 由 `real >= 1` 改为 `real == 2`。
    本 helper 模拟"修复后"的 skip-guard 逻辑。
    """
    return textwrap.dedent(f"""
        from xml.etree import ElementTree as ET
        root = ET.parse(r'{xml_path}').getroot()
        all_tcs = list(root.iter('testcase'))
        skipped = [tc for tc in all_tcs if tc.find('skipped') is not None]
        real = len(all_tcs) - len(skipped)
        print(f'skip-guard: total={{len(all_tcs)}} skipped={{len(skipped)}} real={{real}}')
        assert real == 2, f'expected exactly 2 real testcases, got {{real}}'
    """).strip()


def _make_junit_xml(tmp_path: Path, n_real: int) -> Path:
    """生成 n 个非 skipped testcase 的 junit xml fixture"""
    cases = "\n".join(
        f'    <testcase name="test_real_{i}" classname="C"></testcase>'
        for i in range(n_real)
    )
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="x" tests="{n_real}" skipped="0">
{cases}
  </testsuite>
</testsuites>
"""
    p = tmp_path / f"junit-real-{n_real}.xml"
    p.write_text(xml, encoding="utf-8")
    return p


class TestSkipGuard:
    def test_real_equals_2_passes(self, tmp_path: Path) -> None:
        xml = _make_junit_xml(tmp_path, n_real=2)
        result = subprocess.run(
            [sys.executable, "-c", _skip_guard_inline_script(xml)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"expected real==2 PASS, got rc={result.returncode}; stderr={result.stderr[:300]}"
        )

    def test_real_equals_1_fails(self, tmp_path: Path) -> None:
        """当前 sw-smoke.yml `real >= 1` 让此 fixture PASS → 修复后 `real == 2` 会让其 fail"""
        xml = _make_junit_xml(tmp_path, n_real=1)
        result = subprocess.run(
            [sys.executable, "-c", _skip_guard_inline_script(xml)],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0, (
            f"expected real==1 FAIL after S2 fix, got rc=0; stdout={result.stdout[:300]}"
        )

    def test_real_equals_3_fails(self, tmp_path: Path) -> None:
        xml = _make_junit_xml(tmp_path, n_real=3)
        result = subprocess.run(
            [sys.executable, "-c", _skip_guard_inline_script(xml)],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0, (
            f"expected real==3 FAIL, got rc=0; stdout={result.stdout[:300]}"
        )
```

- [ ] **Step 3.2：跑测试验证 RED**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_smoke_skip_guard.py::TestSkipGuard -v
```

期望：3 个测试全 PASS（因为 helper 已经写的是 `real == 2`，与未来修复一致）。

> 注：本 task 的"RED"含义不是 helper 失败，而是"sw-smoke.yml 现状若直接复制 helper 逻辑则 line 51 的 `>= 1` 与 helper 的 `== 2` 不一致"——helper 锁定的是 spec §3.4 P4-F 修复后的契约，sw-smoke.yml 修改前后由 helper 强制一致性。

- [ ] **Step 3.3：commit S2.0 双 RED**

```bash
git -C /d/Work/cad-spec-gen add tests/test_assert_sw_inspect_schema.py tests/test_sw_smoke_skip_guard.py
git -C /d/Work/cad-spec-gen checkout -b feat/sw-f13jk
git -C /d/Work/cad-spec-gen commit -m "$(cat <<'EOF'
test(sw-smoke): RED for retcode 65 + real==2 skip-guard

S2.0 TDD 前置：
- test_assert_sw_inspect_schema.py: 验空文件输入应 retcode 65（当前 main()
  无 try/except → AssertionError → retcode 1 → RED）
- test_sw_smoke_skip_guard.py: 锁定 sw-smoke.yml skip-guard 修复后契约
  (real == 2)；helper _skip_guard_inline_script 锁定 yaml 改动后行为

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

期望：commit 成功，分支切换到 `feat/sw-f13jk`。

---

### Task 4：S2 commit 1 — assert_sw_inspect_schema.py main() 加 try/except → GREEN

**Files：**
- Modify: `tools/assert_sw_inspect_schema.py`

- [ ] **Step 4.1：先 Read 现状定位 main() 函数**

```bash
grep -n "^def main\|^if __name__" /d/Work/cad-spec-gen/tools/assert_sw_inspect_schema.py
```

记录 main() 起止行号（用于 Edit 精确替换）。

- [ ] **Step 4.2：Edit main() 加 try/except + retcode 65**

把 main() 函数体（具体内容由 Step 4.1 定位）改成：

```python
def main(argv: list[str]) -> int:
    """CLI 入口。

    退出码：
      0  = schema 合规
      1  = schema 不合规（AssertionError）
      64 = 用法错误（参数缺失）
      65 = JSON parse 失败（DATAERR，sysexits 标准；F-1.3j+k S2 commit 1 新增）
    """
    if len(argv) != 2:
        print(f"usage: {argv[0]} <path-to-sw-inspect.json>", file=sys.stderr)
        return 64

    path = Path(argv[1])
    try:
        # 关键：把原 assert_schema_v1 调用包在 JSONDecodeError 守卫里
        # 不动 assert_schema_v1 函数本身（继承 v3 L3 P3#2 决策）
        assert_schema_v1(path)
    except json.JSONDecodeError as e:
        print(
            f"sw-inspect 输出非合法 JSON: path={path}; "
            f"err={e}; "
            f"前 200 字节={path.read_bytes()[:200]!r}",
            file=sys.stderr,
        )
        return 65
    except AssertionError:
        # AssertionError 由 assert_schema_v1 抛出 → 走 Python 默认退出码 1
        # 不在这里 catch，让回溯保留
        raise

    return 0
```

> 注：保持 `import json` / `from pathlib import Path` 在文件顶部已有；如果 `import json` 不存在，加 `import json`。

- [ ] **Step 4.3：跑 S2.0(a) RED 测试验证 GREEN**

```bash
.venv/Scripts/python.exe -m pytest tests/test_assert_sw_inspect_schema.py::TestJsonDecodeError::test_empty_file_returns_65 -v
```

期望：PASS（retcode 65 + stderr 含 "JSONDecodeError" / "json"）。

- [ ] **Step 4.4：跑同题域回归测试（local test scope feedback memory）**

```bash
.venv/Scripts/python.exe -m pytest tests/test_assert_sw_inspect_schema.py tests/test_sw_inspect_real.py -v
```

期望：全 PASS（含 1 新测试 + 任何既有相关测试，real_smoke 在 Linux/Win 没 SW 时 skip OK）。

- [ ] **Step 4.5：commit**

```bash
git -C /d/Work/cad-spec-gen add tools/assert_sw_inspect_schema.py
git -C /d/Work/cad-spec-gen commit -m "$(cat <<'EOF'
fix(assert_schema): retcode 65 for JSONDecodeError

S2 commit 1：让 S2.0(a) RED → GREEN。

把 assert_schema_v1 调用包在 JSONDecodeError 守卫里（不动 assert_schema_v1
函数本身，继承 v3 L3 P3#2 决策），retcode 65 = DATAERR sysexits 标准。
副作用：sw-smoke.yml line 59 删 `|| true` 后，sw-inspect crash 写空文件
将以 retcode 65 + 友好 stderr 暴露，而非被 AssertionError 模糊为 1。

退出码矩阵：0 合规 / 1 schema 不合规 / 64 usage / 65 JSON parse 失败。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

期望：commit 成功。

---

### Task 5：S2 commit 2 — sw-smoke.yml 三处改动 → GREEN

**Files：**
- Modify: `.github/workflows/sw-smoke.yml`

> 注：Edit 时**必须先加 cleanup step（让既有 step 行号下移），再改原 line 59 / line 51**——否则后改的行号会漂移。但更稳的做法是按 anchor（"|| true" / "real >= 1"）替换，不依赖行号。本计划用 anchor。

- [ ] **Step 5.1：Edit 加 cleanup step 为新 steps[0]（在 actions/checkout 之前）**

把现有 yaml 的 `      - uses: actions/checkout@v6` 改成：

```yaml
      - name: Pre-checkout workspace cleanup (F-1.3j 防 protected-ACL 残留)
        shell: pwsh
        env:
          PYTHONUTF8: "1"
        run: |
          # P2-O：兜底 kill SW 残留进程
          Get-Process SLDWORKS -ErrorAction SilentlyContinue | ForEach-Object {
            Write-Host "Stopping orphan SLDWORKS PID=$($_.Id) StartTime=$($_.StartTime)"
            $_ | Stop-Process -Force -ErrorAction SilentlyContinue
          }

          # P2-D part 2：守卫强化 — workspace 未定义 / 空字符串 / 不存在 三种均跳过
          $ws = $env:GITHUB_WORKSPACE
          if (-not $ws -or $ws.Trim() -eq '' -or -not (Test-Path -LiteralPath $ws)) {
            Write-Host "workspace not yet created or undefined, skip"
            exit 0
          }

          # 仅清理白名单内路径（spec §2.2 cleanup 白名单）
          $cache = Join-Path $ws '.pytest_cache'
          if (Test-Path -LiteralPath $cache) {
            Write-Host "Removing $cache (best-effort)"
            Remove-Item -Recurse -Force -LiteralPath $cache -ErrorAction SilentlyContinue
            # P2-L：silent-fail 可观测性 — 失败时发 GitHub workflow command annotation
            if (Test-Path -LiteralPath $cache) {
              Write-Host "::warning title=cleanup_residual::pre-checkout cleanup left .pytest_cache; ACL drift suspected; checkout fallback will attempt recreate"
            }
          }
          Get-ChildItem -Path $ws -Filter '__pycache__' -Recurse -Force -Directory -EA SilentlyContinue |
            Remove-Item -Recurse -Force -EA SilentlyContinue

      - uses: actions/checkout@v6
```

- [ ] **Step 5.2：Edit 删 line 59 `|| true`（用 anchor）**

把：

```yaml
          python cad_pipeline.py sw-inspect --deep --json > sw-inspect-deep.json || true
          python tools/assert_sw_inspect_schema.py sw-inspect-deep.json
```

改成（直接让 sw-inspect 退出码传染 step）：

```yaml
          python cad_pipeline.py sw-inspect --deep --json > sw-inspect-deep.json
          python tools/assert_sw_inspect_schema.py sw-inspect-deep.json
```

- [ ] **Step 5.3：Edit 改 skip-guard `real >= 1` 为 `real == 2`（用 anchor）**

把：

```python
          assert real >= 1, 'expected >= 1 real testcase, got 0 — @requires_solidworks 可能被全量 skip'
```

改成：

```python
          assert real == 2, f'expected exactly 2 real testcases (test_fast_real_smoke + test_deep_real_smoke), got {real} — marker 漂移或新测试未授 @requires_solidworks'
```

- [ ] **Step 5.4：跑 S2.0(b) RED 测试验证 GREEN**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_smoke_skip_guard.py::TestSkipGuard -v
```

期望：3 个测试全 PASS（real==2 PASS / real==1 FAIL / real==3 FAIL）。

- [ ] **Step 5.5：跑 ruff 与全 pytest（与 CI 镜像一致）**

```bash
.venv/Scripts/python.exe -m ruff check tools/assert_sw_inspect_schema.py
.venv/Scripts/python.exe -m pytest tests/ -v -k "not real_smoke"
```

期望：ruff 0 issue；pytest 全 PASS（exclude real_smoke 因本地非 ghrunner 真跑）。

- [ ] **Step 5.6：commit**

```bash
git -C /d/Work/cad-spec-gen add .github/workflows/sw-smoke.yml
git -C /d/Work/cad-spec-gen commit -m "$(cat <<'EOF'
fix(sw-smoke): add pre-checkout cleanup + skip-guard tighten

S2 commit 2：让 S2.0(b) RED → GREEN，同时修 F-1.3j 根因。

3 处改动：
1. 加 Pre-checkout workspace cleanup step 为新 steps[0]：
   pwsh / best-effort / Stop-Process SLDWORKS / GITHUB_WORKSPACE 三重守卫 /
   仅清白名单路径 (.pytest_cache + __pycache__) / silent-fail 走
   ::warning::cleanup_residual annotation
2. 删 line 59 `|| true`：让 sw-inspect 退出码不再被吞，配合
   assert_schema_py retcode 65 兑现 AC-2 fail-fast 承诺
3. 改 skip-guard line 51 `real >= 1` → `real == 2`：
   兑现 AC-4 自动化（不再需人工核 junit xml）

测试：tests/test_sw_smoke_skip_guard.py 3 fixture PASS（S2.0(b) GREEN）。
ghrunner 限权下 protected-ACL 路径靠真跑覆盖（S2.5 仅本地 happy-path）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

期望：commit 成功。

---

### Task 6：S2.5 本地 pwsh dry-run（手工预检 3 fixture，不 commit）

**Files：** 无（手工 PowerShell 模拟）

> 限制：本地 procheng admin 身份不能复现 ghrunner 限权 EPERM；本 task 仅查 happy-path 三分支语法/逻辑，protected-ACL 路径靠 S4 run-A / S5 run-B 真 ghrunner 跑覆盖。

- [ ] **Step 6.1：fixture 1 — workspace 不存在守卫**

```powershell
# 模拟 GITHUB_WORKSPACE 指向不存在路径
$env:GITHUB_WORKSPACE = "$env:TEMP\f13j-dryrun-nonexistent-$(Get-Random)"

# 把 sw-smoke.yml cleanup step 的 run: 块复制到临时 .ps1 文件跑（或直接复制到 PS console）
# 期望输出：workspace not yet created or undefined, skip
```

- [ ] **Step 6.2：fixture 2 — workspace 存在 + .pytest_cache happy-path**

```powershell
$tmpWs = "$env:TEMP\f13j-dryrun-happy-$(Get-Random)"
New-Item -ItemType Directory -Force $tmpWs | Out-Null
New-Item -ItemType Directory -Force "$tmpWs\.pytest_cache\v\cache" | Out-Null
"dummy" | Out-File "$tmpWs\.pytest_cache\v\cache\nodeids"

$env:GITHUB_WORKSPACE = $tmpWs
# 跑 cleanup 块
# 期望输出：Removing <path>\.pytest_cache (best-effort)
# 期望：Test-Path "$tmpWs\.pytest_cache" 返 False

# 清理
Remove-Item -Recurse -Force $tmpWs
```

- [ ] **Step 6.3：fixture 3 — GITHUB_WORKSPACE 未设守卫**

```powershell
Remove-Item Env:GITHUB_WORKSPACE -ErrorAction SilentlyContinue
# 跑 cleanup 块
# 期望输出：workspace not yet created or undefined, skip
```

- [ ] **Step 6.4：跑 Stop-Process SLDWORKS（如本机有 SW 进程）**

```powershell
# 如果当前没开 SW，跳过这步
Get-Process SLDWORKS -ErrorAction SilentlyContinue
# 如果有，运行 cleanup 块开头的 Get-Process 块，期望日志 "Stopping orphan SLDWORKS PID=..."
```

> 注：v4 已删除 v3 第 4 fixture（runas + icacls），protected-ACL 路径靠 S4 run-A 真 ghrunner 跑覆盖。

---

### Task 7：S3 actionlint 验证（不 commit）

**Files：** 无（lint）

- [ ] **Step 7.1：检测本机 actionlint**

```bash
actionlint --version 2>/dev/null || echo "no actionlint"
```

- [ ] **Step 7.2：按三级 fallback 跑**

```bash
# 路 a：本机 actionlint ≥ 1.6.20
if command -v actionlint >/dev/null 2>&1; then
  actionlint .github/workflows/sw-smoke.yml
# 路 b：docker
elif command -v docker >/dev/null 2>&1; then
  docker run --rm -v "${PWD}:/repo" rhysd/actionlint:latest -color
# 路 c：warn-only console only
else
  echo "WARN: actionlint + docker 均无，跳过 yaml lint（F-1.3d 后续提前装）"
fi
```

期望：路 a/b 0 error；允许 pwsh inline 命令 "unknown command" warning（已知噪声 ignore）。

---

### Task 8：S4 PR + merge to main + 烟雾 run-A

**Files：** 无（git/gh CLI）

- [ ] **Step 8.1：push feature branch**

```bash
git -C /d/Work/cad-spec-gen push -u origin feat/sw-f13jk
```

期望：成功；feature branch push 不触发 sw-smoke（监听 main only）。

- [ ] **Step 8.2：开 PR**

```bash
gh pr create --title "fix(sw-smoke): F-1.3j+k workspace ACL 修复 + K1 第二数据点" --body "$(cat <<'EOF'
## Summary
- 修 F.2 PASS pickup-only 后 sw-smoke checkout EPERM 阻断（一次性 admin Remove + workflow pre-checkout cleanup step）
- 修 sw-smoke.yml `|| true` 击穿 + skip-guard `real == 2` 加严
- 新增 S2.0 双 RED → S2 双 GREEN TDD 闭环
- 详见 `docs/superpowers/specs/2026-04-18-sw-self-hosted-runner-f13jk-design.md` v5

## Test plan
- [x] tests/test_assert_sw_inspect_schema.py PASS（retcode 65）
- [x] tests/test_sw_smoke_skip_guard.py PASS（real==2 边界）
- [ ] merge 后 sw-smoke run-A 烟雾 PASS（修复有效性）
- [ ] S5 workflow_dispatch 采 K1 第二数据点 → AC-1..5 全 ✅
- [ ] S7 runbook §7 回填 + F.2 状态升级行

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

期望：PR 创建成功，URL 输出。

- [ ] **Step 8.3：merge to main**

```bash
gh pr merge --merge --delete-branch
```

期望：merge 成功；自动触发 sw-smoke run-A（push event）。

- [ ] **Step 8.4：等 run-A 跑完 + 失败定位**

```bash
# 取最新 push event run id
RUN_A=$(gh run list --workflow sw-smoke.yml --event push --limit 1 --json databaseId --jq '.[0].databaseId')
echo "run-A id: $RUN_A"

# 等跑完
gh run watch "$RUN_A" --exit-status

# 如果失败，一键查失败 step
gh run view "$RUN_A" --json jobs --jq '.jobs[].steps[] | select(.conclusion=="failure") | .name'
# 或更详细：
gh run view "$RUN_A" --log-failed
```

期望分支：

- run-A success → 进 Step 8.5 / Task 9
- run-A fail，失败 step = `Run actions/checkout@v6` → S1 admin fix 未生效，**回 Task 1 复诊**
- run-A fail，失败 step ≠ checkout → 不阻塞 S5（concurrency 不传染失败），记 follow-up 排查后进 Task 9

- [ ] **Step 8.5：拉 main 到本机**

```bash
git -C /d/Work/cad-spec-gen checkout main
git -C /d/Work/cad-spec-gen pull
```

期望：本地 main 与 origin/main 同步。

---

### Task 9：S5 ghrunner SW 首启 + workflow_dispatch K1 采集

**Files：** 无（手工 + gh CLI）

> v5 L6-1 关键澄清：分两路应对 ghrunner desktop session 是否 active。

- [ ] **Step 9.1：等 SW seat 释放（持久授权下）**

```powershell
# admin PowerShell
Get-Process SLDWORKS -ErrorAction SilentlyContinue
# 期望：null 或空（run-A 跑完后 SW 进程已退）
# 如有，Stop-Process -Force 后等 30s（持久授权下保险余量）
Start-Sleep -Seconds 30
```

- [ ] **Step 9.2：验证 ghrunner desktop session 状态**

```powershell
query session
```

期望：看到 `ghrunner ... Active` 行。如果 ghrunner 行 State 是 Disc / 不存在，**走 fallback 路径 B**（见下）。

- [ ] **Step 9.3：路 A — ghrunner desktop active 时人工启 SW 首启**

> 仅在**首次 S5** 跑前需做（之后 ghrunner profile sldmaterials 已建好）

物理操作（在 ghrunner desktop session）：

1. 双击桌面 SOLIDWORKS 图标
2. 等 SW 启动完（~10s）
3. `File → Open` 任意 sldprt（比如 `C:\SOLIDWORKS Data\browser` 下任意 GB toolbox 件），让 sldmaterials 路径加载
4. 关闭 SW

完成信号验证（admin PowerShell）：

```powershell
Test-Path "C:\Users\ghrunner\AppData\Roaming\SolidWorks\SolidWorks 2024\sldmaterials\*.sldmat"
```

期望：`True`。

- [ ] **Step 9.4：路 B fallback — ghrunner 仅 service-style 无 desktop**

如果 Step 9.2 ghrunner 无 Active session：

1. admin 临时改 ghrunner Task Scheduler 任务 `LogonType` 为 `Interactive`
2. 重启机器，让 Autologon 进 ghrunner desktop
3. 重启后 Step 9.2 验 desktop active → 回 Step 9.3 走路 A

> v5 L6-1 已澄清 `runas /user:ghrunner` 启 GUI 在 service-style session 下 Session 0 isolation 不可见，本 step 不再尝试 runas，必走人工/fallback。

- [ ] **Step 9.5：触发 workflow_dispatch run-B**

```bash
gh workflow run sw-smoke.yml --ref main
```

期望：成功；GitHub Actions UI 看到新 dispatch run 进入 queued / in_progress。

- [ ] **Step 9.6：取 run-B id**

```bash
RUN_B=$(gh run list --workflow sw-smoke.yml --event workflow_dispatch --limit 1 --json databaseId,url --jq '.[0]')
echo "run-B: $RUN_B"
RUN_B_ID=$(echo "$RUN_B" | jq -r '.databaseId')
RUN_B_URL=$(echo "$RUN_B" | jq -r '.url')
echo "run-B id=$RUN_B_ID  url=$RUN_B_URL"
```

期望：拿到 run-B URL + runId。

> v5 P2#8：如果 dispatch 后 90s 内未见 in_progress，看 runner 状态 `gh api /repos/proecheng/cad-spec-gen/actions/runners`；必要时手动重启 Task Scheduler → 重 dispatch；K1 数据点采纳的是首次 PASS run。

---

### Task 10：S6 验收 AC-1..AC-5

**Files：** 无（核对 + 手工）

- [ ] **Step 10.1：等 run-B 跑完（with --exit-status）**

```bash
gh run watch "$RUN_B_ID" --exit-status
```

期望：retcode 0 = success（AC-1 ✅）；retcode 非 0 = fail，回 Task 8 / Task 9 排查。

- [ ] **Step 10.2：下载 artifact**

```powershell
# pwsh
$evidenceDir = ".\f2-evidence-$RUN_B_ID"
gh run download $RUN_B_ID --name sw-smoke-artifacts --dir $evidenceDir
Get-ChildItem $evidenceDir
```

期望：目录含 `sw-inspect-deep.json` + `sw-smoke-junit.xml`。

- [ ] **Step 10.3：取数（pwsh 主路径）**

```powershell
$json = Get-Content "$evidenceDir\sw-inspect-deep.json" | ConvertFrom-Json
$dispatch = $json.layers.dispatch.data
$materials = $json.layers.materials.data

Write-Host "AC-2 schema: dispatch.elapsed_ms=$($dispatch.elapsed_ms)"
Write-Host "AC-2.5 materials: sldmat_files=$($materials.sldmat_files)"
Write-Host "AC-3 attached: attached_existing_session=$($dispatch.attached_existing_session)"
Write-Host "AC-3 elapsed: $($dispatch.elapsed_ms) ms (期望 [3000, 15000])"
```

> cross-check 仅作可选：bash + `jq -e '.layers.dispatch.data | .attached_existing_session == false and .elapsed_ms >= 3000 and .elapsed_ms <= 15000' "$evidenceDir/sw-inspect-deep.json"`

- [ ] **Step 10.4：核 AC-1..AC-5 + 警示档判读**

| # | 标准 | 取数 | PASS? |
|---|---|---|---|
| AC-1 | conclusion=success | `$RUN_B` watch 退出码 0 | ⬜ |
| AC-2 | schema fail-fast 兑现（assert exit=0） | `$dispatch.elapsed_ms` 非空 | ⬜ |
| AC-2.5 | materials.sldmat_files > 0 | `$materials.sldmat_files` | ⬜ |
| AC-3 | attached=false AND 3000 ≤ elapsed_ms ≤ 15000 | `$dispatch.elapsed_ms` 区间 + attached false | ⬜ |
| AC-3 警示档 | [10000, 15000] → ⚠️ 接近上限 | 与 baseline 5492 比 ±X% | ⬜ |
| AC-4 | junit total=2 skipped=0 real=2 | `Select-Xml` junit / 自动 by skip-guard | ⬜ |
| AC-5 | runbook §7 同步 | Task 11 完成后 | 留 Task 11 |

如全 PASS 进 Task 11；如 AC-3 越界进 F-1.3l 排查。

---

### Task 11：S7 runbook 4 处回填（1 commit + `[skip smoke]`）

**Files：**
- Modify: `docs/superpowers/runbooks/sw-self-hosted-runner-setup.md`

- [ ] **Step 11.1：runbook §1 前置加 gh CLI ≥ 2.20**

定位 runbook §1 现有列表（`Windows 11 / SolidWorks 2024+ / 机器可联网 / Python 3.12 / Git for Windows`），追加一行：

```markdown
- gh CLI ≥ 2.20（验证：`gh --version`；F-1.3j+k 的 runner Idle 检查 + workflow_dispatch 触发 + artifact 下载链路依赖此版本）
```

- [ ] **Step 11.2：runbook §7 F.2 块开头加状态升级行**

定位 §7 现有 `**F.2 完整生产链路验收记录**...` 行，紧跟其下追加：

```markdown
**状态：→ 2026-04-18 升级见 F-1.3j+k 块（PASS pickup-only → PASS clean）**
```

- [ ] **Step 11.3：runbook §7 F.2 块之后追加 F-1.3j+k 新块**

在 §7 F.2 验收块**末尾之后** + §8 章节标题**之前**插入（spec §5.2 模板，含回填的 K1 第二数据点 + 8 条承诺 checklist）：

```markdown
**F-1.3j workspace ACL 修复 + F-1.3k K1 第二数据点**（2026-04-18，PASS / state upgrade carrier）：

- 修复日期：2026-04-18
- 根因：F.1 baseline 跑（procheng admin session）创建的 `.pytest_cache` 持有 protected ACL（仅 Owner/Admin/SYSTEM Full，无 ghrunner 条目且不继承），F.2 切到 ghrunner 身份后 `git clean -ffdx` 无权 scandir 触发 EPERM
- 一次性手工 fix：admin PowerShell `Remove-Item -Recurse -Force` 清掉 `D:\actions-runner\_work\cad-spec-gen\cad-spec-gen\.pytest_cache` + 所有 `__pycache__` 残留
- 防御性变更：`.github/workflows/sw-smoke.yml` 在 `actions/checkout@v6` 之前新增 `Pre-checkout workspace cleanup` step（pwsh / best-effort / `$env:GITHUB_WORKSPACE` 三重守卫 / SW 残留进程清理 + `::warning::cleanup_residual` annotation）
- 衍生修复：line 59 删 `|| true`（修 AC-2 fail-fast 击穿）/ line 51 skip-guard 由 `real >= 1` 加严到 `real == 2`（修 AC-4 自动化）
- **验证 run**：
  - K1 数据点 run-B（workflow_dispatch 触发 / 入 K1）：<run-B URL>  / runId=<RUN_B_ID>
  - S4 烟雾 run-A（merge push 自动触发 / 仅参考）：<run-A URL>（可选）

**AC 验收结果**：

- AC-1 conclusion: ✅ success
- AC-2 schema fail-fast: ✅（assert_sw_inspect_schema.py exit=0，含 `layers.dispatch.data.elapsed_ms`）
- AC-2.5 materials 业务承诺: ✅ `layers.materials.data.sldmat_files = <数值>` (> 0)
- AC-3 K1 第二数据点：`layers.dispatch.data.elapsed_ms = <数值> ms` / `layers.dispatch.data.attached_existing_session = false`
  - F.1 baseline 对照：5492 ms
  - K1 区间合规判读：[ ] 正常区间 [3000, 10000] / [ ] ⚠️ 警示区间 [10001, 15000] / [ ] ❌ 越界（触发 F-1.3l）
  - Δ vs baseline：(K1 - 5492) / 5492 × 100 = <±X%>
- AC-4 junit: ✅ total=2 skipped=0 real=2（workflow 自动断言）
- AC-5 文档同步: ✅ 本块 + F.2 状态升级行 + §1 gh CLI 前置 + §8.3 自动化补充

**F.2 §0.2 八条承诺复核**（机械设计师消费视角）：

承诺侧：
- [ ] 链路层 — runner 自启动 OK，workflow_dispatch 触发 pickup（已核 sw-smoke.yml `if: head_commit.message` 在 dispatch 时 `head_commit=null` 故 contains 返 false，dispatch 与 push 路径在 step 行为层等价）
- [ ] schema 回归 — `assert_sw_inspect_schema.py` PASS，sw-inspect JSON v1 字段不漂
- [ ] materials 业务回归 — `layers.materials.data.sldmat_files > 0`（test_deep_real_smoke 已断言）
- [ ] 运行时回归 — 真 SW Dispatch 5492 ms ± Δ 量级未异常退化（K1 第二点见 AC-3）

不承诺侧（不变）：
- [ ] toolbox 业务层回归 ❌ 未在 sw-smoke 内（F-1.3h 待办）
- [ ] STEP 转换正确性 ❌ 未跑 sw-warmup / Stage C
- [ ] 永久有效 ❌ 90 天 token 轮换 + Windows / SW 升级须复验
- [ ] 跨机器 ❌ F.2 仅本机 procheng-sw-smoke 验证

**后续状态**：runner long-lived 在线，sw-smoke 重新进入 ready-for-merge 状态。

🎉 **F.2 → PASS clean，原 F.2 块 "PASS pickup-only" 状态正式升级**（升级判据 = 本块 AC-1..5 全 ✅ + F-1.3j / F-1.3k follow-up 标注 closed）
```

- [ ] **Step 11.4：runbook §8.3 末尾加 Stop-Process 自动化补充行**

定位 §8.3 现有末行（"持续冲突可在 Actions → sw-smoke → Disable workflow 临时关闭"），追加：

```markdown
**自动化补充**（F-1.3j+k 起）：sw-smoke `Pre-checkout workspace cleanup` step 已加 `Stop-Process SLDWORKS` 兜底 kill 残留进程（详见 F-1.3j+k 块 + spec §3.2 P2-O），处理人手动关 SW 与本自动化互补。
```

- [ ] **Step 11.5：commit（[skip smoke]）**

```bash
git -C /d/Work/cad-spec-gen add docs/superpowers/runbooks/sw-self-hosted-runner-setup.md
git -C /d/Work/cad-spec-gen commit -m "$(cat <<'EOF'
docs(sw-self-hosted-runner): F-1.3j+k §7 验证回填 + §1/§8.3 同步 [skip smoke]

S7：4 处 runbook 同步（单文件 1 commit OK，属同一 logical unit "F-1.3j+k 验证收尾"）：

1. §1 前置加 gh CLI ≥ 2.20
2. §7 F.2 块开头加状态升级行（PASS pickup-only → PASS clean）
3. §7 F.2 块之后追加 F-1.3j+k 新块（K1 第二数据点 + 8 条承诺 checklist）
4. §8.3 末尾加 Stop-Process 自动化补充行（与 §3.2 P2-O 双向引用）

[skip smoke] 避免纯文档 commit 触发 ~57s 物理跑（runbook 改动不动 sw-smoke.yml，
re-trigger 走全 PASS 路径，忘加无 fail 风险）。

F.2 状态机正式升级到 PASS clean。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 11.6：push main**

```bash
git -C /d/Work/cad-spec-gen push origin main
```

期望：成功；commit message `[skip smoke]` 让 sw-smoke workflow 跳过本次 push（防 ~57s 无意义跑）。

- [ ] **Step 11.7：最后状态确认**

```bash
gh run list --workflow sw-smoke.yml --limit 5
# 期望：最近 5 个 run 含 run-B success；最后一个 push commit 因 [skip smoke] 不在列表
```

更新 memory（superpowers 一致性）：

```
solidworks_asset_extraction.md：
- 把"F-1.3 Phase F.2 PASS pickup-only" 段落更新为 "PASS clean (2026-04-18, F-1.3j+k 完成)"
- 移除 "未修复前不要推 main" 约束
- 加 K1 第二数据点 dispatch.elapsed_ms = <数值> ms (vs F.1 5492ms)
```

---

## 完成判据

- 所有 11 task 的 checkbox 全 ✅
- AC-1..AC-5 全 ✅（含 AC-2.5 / AC-3 attached + 区间）
- F.2 状态机升级到 PASS clean
- runbook §7 完整反映 K1 第二数据点 + 8 条承诺复核
- main 分支：feat/sw-f13jk 已 merge + 1 commit S7 docs

## 失败回滚

- Task 5 yaml 语法错 → `git revert <commit>`
- Task 8 run-A 持续红 → commit message 加 `[skip smoke]` / Settings → Disable workflow
- Task 9 SW seat race → 等 60s 重 dispatch
- Task 10 AC-3 越界 → 开 F-1.3l follow-up
- Task 11 runbook 编辑出错 → `git revert` 单 commit 即可

详见 spec §7.2 回滚方案。
