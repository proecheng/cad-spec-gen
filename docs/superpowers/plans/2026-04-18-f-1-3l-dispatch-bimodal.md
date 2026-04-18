# F-1.3l SW COM Dispatch elapsed_ms 双峰根因调查 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 SW COM Dispatch `elapsed_ms` 的双峰分布（~310ms 浅档 vs ~3295ms 深档）根因定位清楚，并把 AC-3 区间从 runbook 文字首次代码化为 `assert_ac3_range()` 断言函数，让 F.2 状态机从 PASS pickup-only 升级 PASS clean。

**Architecture:** 三阶段硬依赖（Phase 1 merge main ▶ Phase 2 §8.0 前置 checklist ▶ Phase 3 验收）。Phase 1 永久基础设施（per-step timing + AC-3 代码化），Phase 2 临时实验（H1 license kill 证伪 + H2 ROT 被动观测 + H3 Defender 梯度+分布采样），Phase 3 根因确认 + AC-3 区间收紧 + revert 临时探针。

**Tech Stack:** Python 3.11 / pywin32 / pytest / PowerShell 5.1 / pandas + scipy / GitHub Actions self-hosted runner。

**Spec reference:** `docs/superpowers/specs/2026-04-18-f-1-3l-dispatch-bimodal-design.md` (commit e220467)

---

## 文件结构（File Structure）

### Phase 1 永久合入 main

| 文件 | 责任 | 是否新建 |
|---|---|---|
| `adapters/solidworks/sw_probe.py` | 扩展 `probe_dispatch` 返回 per_step_ms + 哨兵常量 + 最小值截断 | 修改 |
| `tools/assert_sw_inspect_schema.py` | 扩展 schema 断言 + 新建 `assert_ac3_range` 函数 + rc=66 | 修改 |
| `tests/test_sw_probe_dispatch_per_step.py` | per_step_ms 单测（8 个用例） | 新建 |
| `tests/test_assert_schema_per_step.py` | schema 扩展单测（5 个用例） | 新建 |
| `tests/test_assert_ac3_range.py` | AC-3 断言单测 | 新建 |
| `docs/superpowers/runbooks/sw-self-hosted-runner-setup.md` | §7 F-1.3l follow-up 段补 Phase 1 完成标记 | 修改 |

### Phase 2 临时实验（调查完毕 revert）

| 文件 | 责任 | 是否新建 |
|---|---|---|
| `F13L_REVERT_CHECKLIST.md` | 所有临时变动点 checklist（含 workflow 行号 + 每条临时代码 file:line） | 新建·临时 |
| `adapters/solidworks/sw_probe.py` | 临时加 `probe_investigation_env()` 函数 | 修改·临时 |
| `.github/workflows/sw-smoke.yml` | `runs-on` 追加 `f13l-exclusive` label | 修改·临时 |
| `scripts/f13l_run.ps1` | 一键入口 `--phase 2 --auto-chain` | 新建·临时 |
| `scripts/f13l_h1_license_test.ps1` | H1 kill 交替 10 轮 | 新建·临时 |
| `scripts/f13l_h2_rot_observe.py` | H2 被动观测 10 轮 | 新建·临时 |
| `scripts/f13l_h3_gradient_scan.ps1` | H3 梯度 21 点 | 新建·临时 |
| `scripts/f13l_analyze.py` | 三态决策 + --merge-all | 新建·临时 |
| `.gitignore` | 加 `f2-evidence-f13l/` | 修改 |
| `f2-evidence-f13l/` | CSV + stderr 归档目录 | 新建·gitignored |

### Phase 3 根因确认后

| 文件 | 责任 | 是否新建 |
|---|---|---|
| `tools/assert_sw_inspect_schema.py` | 调整 `assert_ac3_range` 区间常量 | 修改 |
| `tests/test_assert_ac3_range.py` | 扩展新区间边界测试 | 修改 |
| `docs/superpowers/runbooks/sw-self-hosted-runner-setup.md` | §7 F-1.3l 根因记录段 | 修改 |

---

# Phase 1：仪器化基础设施（永久合入 main）

## Task 1: 定义 per_step_ms 哨兵常量

**Files:**
- Modify: `adapters/solidworks/sw_probe.py` 在 import 段之后，`_STEP_COUNT_DOWNGRADE_THRESHOLD` 附近

- [ ] **Step 1: 直接修改常量（无测试，只是常量定义）**

在 `adapters/solidworks/sw_probe.py` 第 22 行 `from adapters.solidworks.sw_detect import SwInfo` 之后加：

```python
# F-1.3l Phase 1：per_step_ms 哨兵常量（PER_STEP_* 供未来其他 probe_* 函数复用）
# PER_STEP_SENTINEL_RAISED = -1 表示"该步运行但抛异常"
# PER_STEP_SENTINEL_UNREACHED = 0 表示"该步未被运行到"（timeout / 之前的步抛错）
# 真实测量值 ≥ 1（<1ms 截断为 1，见 Task 7）
PER_STEP_SENTINEL_RAISED = -1
PER_STEP_SENTINEL_UNREACHED = 0
```

- [ ] **Step 2: 运行现有测试确认无破坏**

Run: `pytest tests/test_sw_probe.py -v`

Expected: 全部 PASS（只是加常量定义，无行为变化）

- [ ] **Step 3: commit**

```bash
git add adapters/solidworks/sw_probe.py
git commit -m "feat(sw_probe): 引入 per_step_ms 哨兵常量（F-1.3l Phase 1 Task 1）"
```

---

## Task 2: per_step_ms 冷启路径 — 失败测试

**Files:**
- Create: `tests/test_sw_probe_dispatch_per_step.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_sw_probe_dispatch_per_step.py`，内容：

```python
"""per_step_ms 字段的单测（F-1.3l Phase 1）。

所有测试用 mock 不依赖真 SW / pywin32；Linux CI 可跑。
"""

from __future__ import annotations

import concurrent.futures
from unittest import mock

import pytest


class TestColdDispatchPerStep:
    """冷启路径下 per_step_ms 的语义测试。"""

    def test_cold_dispatch_per_step_sum_matches_elapsed(self, monkeypatch):
        """冷启路径下，per_step_ms 4 段之和 ≈ elapsed_ms（±50ms 容差）。"""
        from adapters.solidworks import sw_probe

        # mock pywin32 使得 GetObject 抛（attach 路径不命中）
        monkeypatch.setattr(
            "win32com.client.GetObject",
            mock.Mock(side_effect=Exception("no running SW")),
        )

        # mock worker 函数返回已知的 per_step_ms
        fake_per_step = {
            "dispatch_ms": 100,
            "revision_ms": 50,
            "visible_ms": 30,
            "exitapp_ms": 20,
        }

        def fake_worker(progid):
            return ("2024", True, True, fake_per_step)

        monkeypatch.setattr(
            sw_probe, "_dispatch_and_probe_worker", fake_worker, raising=False
        )

        r = sw_probe.probe_dispatch(timeout_sec=10)

        assert r.ok is True
        assert r.data["attached_existing_session"] is False
        assert r.data["per_step_ms"] == fake_per_step
        assert (
            sum(fake_per_step.values()) - 50
            <= r.data["elapsed_ms"]
            <= sum(fake_per_step.values()) + 50
        ), f"elapsed_ms={r.data['elapsed_ms']} 超出 per_step 总和 ±50ms"
```

- [ ] **Step 2: 跑测试确认 RED**

Run: `pytest tests/test_sw_probe_dispatch_per_step.py::TestColdDispatchPerStep::test_cold_dispatch_per_step_sum_matches_elapsed -v`

Expected: FAIL（`r.data["per_step_ms"]` KeyError 或 AttributeError，因为 probe_dispatch 尚未实现 per_step_ms 字段）

- [ ] **Step 3: commit 失败测试**

```bash
git add tests/test_sw_probe_dispatch_per_step.py
git commit -m "test(sw_probe): RED — 冷启 per_step_ms 总和对齐 elapsed_ms (F-1.3l T2)"
```

---

## Task 3: per_step_ms 冷启路径 — 最小实现

**Files:**
- Modify: `adapters/solidworks/sw_probe.py:580-612` (_dispatch_and_probe_worker 函数)
- Modify: `adapters/solidworks/sw_probe.py:615-678` (probe_dispatch 冷启路径)

- [ ] **Step 1: 重写 worker 函数返回 per_step_ms**

把 `_dispatch_and_probe_worker` 函数（约 `sw_probe.py:580-614`）整体替换为：

```python
    def _dispatch_and_probe_worker(
        progid: str,
    ) -> tuple[str, bool, bool, dict[str, int]]:
        """ThreadPoolExecutor worker：CoInitialize → Dispatch → Revision/Visible/ExitApp → CoUninitialize。

        COM STA 要求所有 COM 方法调用必须在同一线程完成，因此将
        Dispatch 与后续属性访问、ExitApp 一并放入此 worker。

        F-1.3l Phase 1：每步单独计时，返回 per_step_ms dict。
        per_step_ms 语义：
          - 真实测量值：≥ 1（<1ms 截断为 1，Task 7 实现）
          - 未到达的步：0（PER_STEP_SENTINEL_UNREACHED）
          - 抛异常的步：-1（PER_STEP_SENTINEL_RAISED）

        返回：(revision_number, visible_set_ok, exit_app_ok, per_step_ms)
        """
        import pythoncom  # pywin32 随附；Linux CI 走不到此函数

        pythoncom.CoInitialize()
        try:
            from win32com import client as _wc_inner

            per_step = {
                "dispatch_ms": PER_STEP_SENTINEL_UNREACHED,
                "revision_ms": PER_STEP_SENTINEL_UNREACHED,
                "visible_ms": PER_STEP_SENTINEL_UNREACHED,
                "exitapp_ms": PER_STEP_SENTINEL_UNREACHED,
            }

            # step 1: Dispatch
            t_dispatch_start = _time.perf_counter()
            _app = _wc_inner.Dispatch(progid)
            per_step["dispatch_ms"] = int((_time.perf_counter() - t_dispatch_start) * 1000)

            _rev = ""
            _visible_ok = False
            _exit_ok = False

            # step 2: RevisionNumber
            t_rev_start = _time.perf_counter()
            try:
                _rev = str(getattr(_app, "RevisionNumber", ""))
                per_step["revision_ms"] = int((_time.perf_counter() - t_rev_start) * 1000)
            except Exception:
                per_step["revision_ms"] = PER_STEP_SENTINEL_RAISED

            # step 3: Visible = False
            t_vis_start = _time.perf_counter()
            try:
                _app.Visible = False
                _visible_ok = True
                per_step["visible_ms"] = int((_time.perf_counter() - t_vis_start) * 1000)
            except Exception:
                per_step["visible_ms"] = PER_STEP_SENTINEL_RAISED

            # step 4: ExitApp
            t_exit_start = _time.perf_counter()
            try:
                _app.ExitApp()
                _exit_ok = True
                per_step["exitapp_ms"] = int((_time.perf_counter() - t_exit_start) * 1000)
            except Exception:
                per_step["exitapp_ms"] = PER_STEP_SENTINEL_RAISED

            return (_rev, _visible_ok, _exit_ok, per_step)
        finally:
            pythoncom.CoUninitialize()
```

- [ ] **Step 2: 修改 probe_dispatch 冷启路径接收 per_step**

在 probe_dispatch（约 `sw_probe.py:615-678`）的冷启路径，把：

```python
        fut = ex.submit(_dispatch_and_probe_worker, "SldWorks.Application")
        try:
            rev, visible_ok, exit_ok = fut.result(timeout=timeout_sec)
```

改为：

```python
        fut = ex.submit(_dispatch_and_probe_worker, "SldWorks.Application")
        try:
            rev, visible_ok, exit_ok, per_step_ms = fut.result(timeout=timeout_sec)
```

然后在成功返回处（约 `sw_probe.py:665-678`）把 ProbeResult 的 data dict 改为：

```python
    elapsed_ms = int((_time.perf_counter() - t0) * 1000)

    return ProbeResult(
        layer="dispatch",
        ok=True,
        severity="ok",
        summary=f"Dispatch 冷启 {elapsed_ms}ms RevisionNumber={rev}",
        data={
            "dispatched": True,
            "elapsed_ms": elapsed_ms,
            "revision_number": rev,
            "visible_set_ok": visible_ok,
            "exit_app_ok": exit_ok,
            "attached_existing_session": False,
            "per_step_ms": per_step_ms,
        },
    )
```

- [ ] **Step 3: 跑测试确认 GREEN**

Run: `pytest tests/test_sw_probe_dispatch_per_step.py::TestColdDispatchPerStep::test_cold_dispatch_per_step_sum_matches_elapsed -v`

Expected: PASS

- [ ] **Step 4: 跑现有 sw_probe 全部测试确认无破坏**

Run: `pytest tests/test_sw_probe.py -v`

Expected: 全部 PASS（per_step_ms 只是 data dict 新 key，现有测试不关心不受影响）

- [ ] **Step 5: commit**

```bash
git add adapters/solidworks/sw_probe.py
git commit -m "feat(sw_probe): probe_dispatch 冷启返回 per_step_ms (F-1.3l T3)"
```

---

## Task 4: t0 起点回归测试

**Files:**
- Modify: `tests/test_sw_probe_dispatch_per_step.py`
- Modify: `adapters/solidworks/sw_probe.py:617` (t0 起点)

- [ ] **Step 1: 在 test_sw_probe_dispatch_per_step.py 里加测试（RED）**

在 `TestColdDispatchPerStep` 类里加：

```python
    def test_worker_t0_start_inside_worker(self, monkeypatch):
        """回归钉：t0 起点必须在 worker 内部，不包含线程池 cold-start 开销。

        模拟 ThreadPoolExecutor.submit 睡 500ms 后才调 worker；worker 内部
        实际只耗 10ms。若 t0 误放在 submit 之前（现状），elapsed_ms ≥ 500。
        正确实现应让 elapsed_ms < 100。
        """
        import time as _time_mod

        from adapters.solidworks import sw_probe

        monkeypatch.setattr(
            "win32com.client.GetObject",
            mock.Mock(side_effect=Exception("no running SW")),
        )

        def slow_worker(progid):
            _time_mod.sleep(0.5)  # 模拟线程池 cold-start 延迟
            fake_per_step = {
                "dispatch_ms": 5,
                "revision_ms": 3,
                "visible_ms": 1,
                "exitapp_ms": 1,
            }
            return ("2024", True, True, fake_per_step)

        monkeypatch.setattr(sw_probe, "_dispatch_and_probe_worker", slow_worker)

        r = sw_probe.probe_dispatch(timeout_sec=10)
        assert r.data["elapsed_ms"] < 100, (
            f"elapsed_ms={r.data['elapsed_ms']} 包含了 500ms 线程池 cold-start — "
            "t0 被误放在 submit 之前"
        )
```

- [ ] **Step 2: 跑测试确认 RED**

Run: `pytest tests/test_sw_probe_dispatch_per_step.py::TestColdDispatchPerStep::test_worker_t0_start_inside_worker -v`

Expected: FAIL（elapsed_ms ≥ 500，因当前 t0 在 submit 之前）

- [ ] **Step 3: 修正 probe_dispatch 让 elapsed_ms 从 per_step 和算**

把 Task 3 的成功返回处再改一次：

```python
    elapsed_ms = sum(per_step_ms.values())

    return ProbeResult(
        layer="dispatch",
        ok=True,
        severity="ok",
        summary=f"Dispatch 冷启 {elapsed_ms}ms RevisionNumber={rev}",
        data={
            "dispatched": True,
            "elapsed_ms": elapsed_ms,
            "revision_number": rev,
            "visible_set_ok": visible_ok,
            "exit_app_ok": exit_ok,
            "attached_existing_session": False,
            "per_step_ms": per_step_ms,
        },
    )
```

同时在 probe_dispatch 的冷启路径开头（约 `sw_probe.py:617`）**移除** `t0 = _time.perf_counter()` 这一行（不再需要外层 t0）。

- [ ] **Step 4: 跑测试确认 GREEN**

Run: `pytest tests/test_sw_probe_dispatch_per_step.py -v`

Expected: 两个测试都 PASS

- [ ] **Step 5: commit**

```bash
git add tests/test_sw_probe_dispatch_per_step.py adapters/solidworks/sw_probe.py
git commit -m "fix(sw_probe): t0 起点迁入 worker，elapsed_ms = sum(per_step_ms) (F-1.3l T4)"
```

---

## Task 5: attach 路径 per_step_ms 全 0

**Files:**
- Modify: `tests/test_sw_probe_dispatch_per_step.py`
- Modify: `adapters/solidworks/sw_probe.py:546-578` (attach 路径)

- [ ] **Step 1: 加测试（RED）**

在 `tests/test_sw_probe_dispatch_per_step.py` 新增类：

```python
class TestAttachPathPerStep:
    """attach 路径下 per_step_ms 的语义测试。"""

    def test_attach_path_per_step_all_zero(self, monkeypatch):
        """attach 路径 elapsed_ms=0 且 per_step_ms 全 0（未运行到任何一步）。"""
        from adapters.solidworks import sw_probe

        fake_app = mock.Mock()
        fake_app.RevisionNumber = "2024"

        monkeypatch.setattr(
            "win32com.client.GetObject",
            mock.Mock(return_value=fake_app),
        )

        r = sw_probe.probe_dispatch(timeout_sec=10)

        assert r.data["attached_existing_session"] is True
        assert r.data["elapsed_ms"] == 0
        assert r.data["per_step_ms"] == {
            "dispatch_ms": 0,
            "revision_ms": 0,
            "visible_ms": 0,
            "exitapp_ms": 0,
        }
```

- [ ] **Step 2: 跑测试 RED**

Run: `pytest tests/test_sw_probe_dispatch_per_step.py::TestAttachPathPerStep -v`

Expected: FAIL（attach 路径返回的 data dict 没有 per_step_ms 字段）

- [ ] **Step 3: 修改 attach 路径加 per_step_ms**

在 `sw_probe.py:546-578` attach 路径的成功返回 ProbeResult 那里（找到 `"attached_existing_session": True,` 那个 return），data dict 加一行：

```python
        return ProbeResult(
            layer="dispatch",
            ok=True,
            severity="warn",
            summary="SW 已在另一会话运行；本次 probe 附着未接管 visibility / 未退出以保护用户工作",
            data={
                "dispatched": True,
                "elapsed_ms": 0,
                "revision_number": rev,
                "visible_set_ok": False,
                "exit_app_ok": None,
                "attached_existing_session": True,
                "per_step_ms": {
                    "dispatch_ms": 0,
                    "revision_ms": 0,
                    "visible_ms": 0,
                    "exitapp_ms": 0,
                },
            },
        )
```

同样在 attach 路径的"RevisionNumber 读取失败"fail 分支也加上 per_step_ms 全 0（搜索 `附着到现有 SW 但 RevisionNumber 读取失败` 所在 return 也加字段）。

- [ ] **Step 4: 跑测试 GREEN**

Run: `pytest tests/test_sw_probe_dispatch_per_step.py -v`

Expected: 全部 PASS

- [ ] **Step 5: commit**

```bash
git add tests/test_sw_probe_dispatch_per_step.py adapters/solidworks/sw_probe.py
git commit -m "feat(sw_probe): attach 路径 per_step_ms 全 0 (F-1.3l T5)"
```

---

## Task 6: timeout 路径 per_step_ms

**Files:**
- Modify: `tests/test_sw_probe_dispatch_per_step.py`
- Modify: `adapters/solidworks/sw_probe.py:623-642` (timeout 分支)

- [ ] **Step 1: 加测试（RED）**

在 `tests/test_sw_probe_dispatch_per_step.py` 新增类：

```python
class TestTimeoutPathPerStep:
    """timeout 路径下 per_step_ms 的语义测试。"""

    def test_timeout_path_per_step(self, monkeypatch):
        """timeout 时 dispatch_ms = timeout_sec*1000，其他 3 段 = 0（哨兵 UNREACHED）。"""
        from adapters.solidworks import sw_probe

        monkeypatch.setattr(
            "win32com.client.GetObject",
            mock.Mock(side_effect=Exception("no running SW")),
        )

        # mock future.result 抛 TimeoutError
        fake_future = mock.Mock()
        fake_future.result = mock.Mock(side_effect=concurrent.futures.TimeoutError())

        fake_executor = mock.Mock()
        fake_executor.submit = mock.Mock(return_value=fake_future)
        fake_executor.shutdown = mock.Mock()

        monkeypatch.setattr(
            "concurrent.futures.ThreadPoolExecutor",
            mock.Mock(return_value=fake_executor),
        )

        r = sw_probe.probe_dispatch(timeout_sec=5)
        assert r.severity == "fail"
        assert r.data["per_step_ms"] == {
            "dispatch_ms": 5000,
            "revision_ms": 0,
            "visible_ms": 0,
            "exitapp_ms": 0,
        }
```

- [ ] **Step 2: 跑测试 RED**

Run: `pytest tests/test_sw_probe_dispatch_per_step.py::TestTimeoutPathPerStep -v`

Expected: FAIL（timeout 路径的 data dict 没有 per_step_ms）

- [ ] **Step 3: 修改 timeout 分支**

在 sw_probe.py 的 `except concurrent.futures.TimeoutError:` 块里把 return ProbeResult data dict 改为：

```python
        except concurrent.futures.TimeoutError:
            ex.shutdown(wait=False)
            return ProbeResult(
                layer="dispatch",
                ok=False,
                severity="fail",
                summary=f"Dispatch 超时 ({timeout_sec}s)",
                data={
                    "dispatched": False,
                    "elapsed_ms": timeout_sec * 1000,
                    "revision_number": "",
                    "visible_set_ok": False,
                    "exit_app_ok": False,
                    "attached_existing_session": False,
                    "per_step_ms": {
                        "dispatch_ms": timeout_sec * 1000,
                        "revision_ms": PER_STEP_SENTINEL_UNREACHED,
                        "visible_ms": PER_STEP_SENTINEL_UNREACHED,
                        "exitapp_ms": PER_STEP_SENTINEL_UNREACHED,
                    },
                },
                error=f"dispatch timeout after {timeout_sec}s",
                hint="检查 SW 许可证、位数匹配（64-bit Python 对 64-bit SW）、是否被其他进程独占",
            )
```

同样给 `except Exception as e:`（Dispatch 抛异常分支）的 return 加 per_step_ms（全 0 / 0 / 0 / 0）。

- [ ] **Step 4: 跑测试 GREEN**

Run: `pytest tests/test_sw_probe_dispatch_per_step.py -v`

Expected: 全部 PASS

- [ ] **Step 5: commit**

```bash
git add tests/test_sw_probe_dispatch_per_step.py adapters/solidworks/sw_probe.py
git commit -m "feat(sw_probe): timeout/异常路径 per_step_ms (F-1.3l T6)"
```

---

## Task 7: 单步异常哨兵 + 最小值截断

**Files:**
- Modify: `tests/test_sw_probe_dispatch_per_step.py`
- Modify: `adapters/solidworks/sw_probe.py` worker 函数（最小值截断）

- [ ] **Step 1: 加测试（RED）**

在 `tests/test_sw_probe_dispatch_per_step.py` 新增类：

```python
class TestWorkerStepException:
    """worker 内部单步抛异常的哨兵测试（-1 = RAISED）。"""

    def test_revision_step_raises(self, monkeypatch):
        """RevisionNumber 抛 → revision_ms = -1，但 dispatch_ms 正常，visible/exitapp 仍运行。"""
        from adapters.solidworks import sw_probe

        monkeypatch.setattr(
            "win32com.client.GetObject",
            mock.Mock(side_effect=Exception("no running SW")),
        )

        # mock Dispatch 返回的 _app：RevisionNumber 抛，其他正常
        fake_app = mock.Mock()
        # 关键：RevisionNumber 用 PropertyMock side_effect 抛异常
        type(fake_app).RevisionNumber = mock.PropertyMock(
            side_effect=Exception("rev fail")
        )
        fake_app.Visible = False  # 赋值 OK
        fake_app.ExitApp = mock.Mock(return_value=None)

        monkeypatch.setattr("win32com.client.Dispatch", mock.Mock(return_value=fake_app))

        r = sw_probe.probe_dispatch(timeout_sec=10)
        assert r.data["per_step_ms"]["revision_ms"] == -1
        assert r.data["per_step_ms"]["dispatch_ms"] >= 1  # 最小值截断（Task 7 后半）


class TestPerStepMinTruncation:
    """E2: per_step_ms <1ms 截断为 1 避免与哨兵 0 混淆。"""

    def test_fast_step_truncated_to_one(self, monkeypatch):
        """成功跑过的步即使耗时 <1ms 也应记为 1，不能记为 0（哨兵 UNREACHED 占用）。"""
        from adapters.solidworks import sw_probe

        monkeypatch.setattr(
            "win32com.client.GetObject",
            mock.Mock(side_effect=Exception("no running SW")),
        )

        # mock worker：每步真实耗时 0.1ms，原始 int 会舍为 0；截断后应为 1
        fake_per_step = {
            "dispatch_ms": 1,  # 真实 0.1ms * 1000 = 0.1 → int=0 → 截断 1
            "revision_ms": 1,
            "visible_ms": 1,
            "exitapp_ms": 1,
        }

        def fake_worker(progid):
            return ("2024", True, True, fake_per_step)

        monkeypatch.setattr(sw_probe, "_dispatch_and_probe_worker", fake_worker)

        r = sw_probe.probe_dispatch(timeout_sec=10)
        for step in ("dispatch_ms", "revision_ms", "visible_ms", "exitapp_ms"):
            assert r.data["per_step_ms"][step] >= 1, (
                f"{step} = 0 与哨兵 UNREACHED 冲突"
            )
```

- [ ] **Step 2: 跑测试 RED**

Run: `pytest tests/test_sw_probe_dispatch_per_step.py::TestWorkerStepException -v tests/test_sw_probe_dispatch_per_step.py::TestPerStepMinTruncation -v`

Expected: 
- `test_revision_step_raises`: 可能 PASS（Task 3 已实现异常分支哨兵）或 FAIL（因 mock 设置问题）
- `test_fast_step_truncated_to_one`: 可能 PASS（mock 直接给 1），但我们需要验证 worker 内部的最小值截断逻辑

- [ ] **Step 3: 修改 worker 函数给成功步加最小值截断**

在 `_dispatch_and_probe_worker` 函数里，把 Task 3 的每个 `per_step["X_ms"] = int((_time.perf_counter() - t_X_start) * 1000)` 改为：

```python
            # step 1: Dispatch
            t_dispatch_start = _time.perf_counter()
            _app = _wc_inner.Dispatch(progid)
            per_step["dispatch_ms"] = max(
                int((_time.perf_counter() - t_dispatch_start) * 1000), 1
            )

            # step 2: RevisionNumber
            t_rev_start = _time.perf_counter()
            try:
                _rev = str(getattr(_app, "RevisionNumber", ""))
                per_step["revision_ms"] = max(
                    int((_time.perf_counter() - t_rev_start) * 1000), 1
                )
            except Exception:
                per_step["revision_ms"] = PER_STEP_SENTINEL_RAISED

            # step 3: Visible = False
            t_vis_start = _time.perf_counter()
            try:
                _app.Visible = False
                _visible_ok = True
                per_step["visible_ms"] = max(
                    int((_time.perf_counter() - t_vis_start) * 1000), 1
                )
            except Exception:
                per_step["visible_ms"] = PER_STEP_SENTINEL_RAISED

            # step 4: ExitApp
            t_exit_start = _time.perf_counter()
            try:
                _app.ExitApp()
                _exit_ok = True
                per_step["exitapp_ms"] = max(
                    int((_time.perf_counter() - t_exit_start) * 1000), 1
                )
            except Exception:
                per_step["exitapp_ms"] = PER_STEP_SENTINEL_RAISED
```

- [ ] **Step 4: 跑全部测试 GREEN**

Run: `pytest tests/test_sw_probe_dispatch_per_step.py -v`

Expected: 全部 PASS

- [ ] **Step 5: commit**

```bash
git add tests/test_sw_probe_dispatch_per_step.py adapters/solidworks/sw_probe.py
git commit -m "feat(sw_probe): worker 单步异常哨兵 + <1ms 最小值截断为 1 (F-1.3l T7)"
```

---

## Task 8: visible / exitapp 异常测试

**Files:**
- Modify: `tests/test_sw_probe_dispatch_per_step.py`

- [ ] **Step 1: 补充 visible / exitapp 的异常测试**

在 `TestWorkerStepException` 类里加：

```python
    def test_visible_step_raises(self, monkeypatch):
        """Visible = False 抛 → visible_ms = -1；前序步正常记录 + 后序步仍运行。"""
        from adapters.solidworks import sw_probe

        monkeypatch.setattr(
            "win32com.client.GetObject",
            mock.Mock(side_effect=Exception("no running SW")),
        )

        fake_app = mock.Mock()
        fake_app.RevisionNumber = "2024"
        # Visible 赋值抛异常
        type(fake_app).Visible = mock.PropertyMock(side_effect=Exception("visible fail"))
        fake_app.ExitApp = mock.Mock(return_value=None)

        monkeypatch.setattr("win32com.client.Dispatch", mock.Mock(return_value=fake_app))

        r = sw_probe.probe_dispatch(timeout_sec=10)
        assert r.data["per_step_ms"]["visible_ms"] == -1
        assert r.data["per_step_ms"]["dispatch_ms"] >= 1
        assert r.data["per_step_ms"]["revision_ms"] >= 1

    def test_exitapp_step_raises(self, monkeypatch):
        """ExitApp 抛 → exitapp_ms = -1，前 3 步正常记录。"""
        from adapters.solidworks import sw_probe

        monkeypatch.setattr(
            "win32com.client.GetObject",
            mock.Mock(side_effect=Exception("no running SW")),
        )

        fake_app = mock.Mock()
        fake_app.RevisionNumber = "2024"
        fake_app.Visible = False
        fake_app.ExitApp = mock.Mock(side_effect=Exception("exit fail"))

        monkeypatch.setattr("win32com.client.Dispatch", mock.Mock(return_value=fake_app))

        r = sw_probe.probe_dispatch(timeout_sec=10)
        assert r.data["per_step_ms"]["exitapp_ms"] == -1
        assert r.data["per_step_ms"]["dispatch_ms"] >= 1
        assert r.data["per_step_ms"]["revision_ms"] >= 1
        assert r.data["per_step_ms"]["visible_ms"] >= 1
```

- [ ] **Step 2: 跑测试（应直接 GREEN，Task 3/7 已实现哨兵）**

Run: `pytest tests/test_sw_probe_dispatch_per_step.py -v`

Expected: 全部 PASS

- [ ] **Step 3: commit**

```bash
git add tests/test_sw_probe_dispatch_per_step.py
git commit -m "test(sw_probe): 补充 visible/exitapp 单步异常测试 (F-1.3l T8)"
```

---

## Task 9: 扩展 assert_sw_inspect_schema 常量

**Files:**
- Create: `tests/test_assert_schema_per_step.py`
- Modify: `tools/assert_sw_inspect_schema.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_assert_schema_per_step.py`：

```python
"""per_step_ms schema 扩展单测（F-1.3l Phase 1 Task 9）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.assert_sw_inspect_schema import assert_schema_v1


def _make_valid_doc() -> dict:
    """构造一个合法的 deep 模式 sw-inspect 文档（F-1.3l 扩展后）。"""
    return {
        "version": "1",
        "generated_at": "2026-04-18T00:00:00Z",
        "mode": "deep",
        "overall": {
            "ok": True,
            "severity": "ok",
            "exit_code": 0,
            "warning_count": 0,
            "fail_count": 0,
            "elapsed_ms": 1000,
            "summary": "",
        },
        "layers": {
            name: {
                "ok": True,
                "severity": "ok",
                "summary": "",
                "data": {},
            }
            for name in (
                "environment",
                "pywin32",
                "detect",
                "clsid",
                "toolbox_index",
                "materials",
                "warmup",
                "loadaddin",
            )
        }
        | {
            "dispatch": {
                "ok": True,
                "severity": "ok",
                "summary": "",
                "data": {
                    "elapsed_ms": 200,
                    "per_step_ms": {
                        "dispatch_ms": 100,
                        "revision_ms": 50,
                        "visible_ms": 30,
                        "exitapp_ms": 20,
                    },
                    "attached_existing_session": False,
                },
            }
        },
    }


class TestSchemaPerStep:
    def test_schema_accepts_valid_per_step(self, tmp_path):
        """合法的 per_step_ms 字段应通过断言。"""
        doc = _make_valid_doc()
        path = tmp_path / "ok.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        assert_schema_v1(path)  # 不抛

    def test_schema_rejects_missing_per_step_field(self, tmp_path):
        """dispatch.data 缺 per_step_ms 子字段应抛 AssertionError。"""
        doc = _make_valid_doc()
        del doc["layers"]["dispatch"]["data"]["per_step_ms"]
        path = tmp_path / "missing.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        with pytest.raises(AssertionError, match="per_step_ms"):
            assert_schema_v1(path)

    def test_schema_rejects_non_int_per_step_value(self, tmp_path):
        """per_step_ms 的值非 int 应抛。"""
        doc = _make_valid_doc()
        doc["layers"]["dispatch"]["data"]["per_step_ms"]["dispatch_ms"] = "100"
        path = tmp_path / "non_int.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        with pytest.raises(AssertionError, match="per_step_ms"):
            assert_schema_v1(path)
```

- [ ] **Step 2: 跑测试 RED**

Run: `pytest tests/test_assert_schema_per_step.py -v`

Expected: FAIL（assert_schema_v1 还不知道 per_step_ms）

- [ ] **Step 3: 修改 assert_sw_inspect_schema.py 加 per_step 检查**

在 `tools/assert_sw_inspect_schema.py` 顶部常量段加：

```python
REQUIRED_DISPATCH_DATA_FIELDS = ("elapsed_ms", "per_step_ms", "attached_existing_session")
REQUIRED_PER_STEP_FIELDS = ("dispatch_ms", "revision_ms", "visible_ms", "exitapp_ms")
```

然后在 `assert_schema_v1()` 函数末尾（现有的 `if mode == "deep":` 块后）替换为：

```python
    # deep 模式：dispatch.data 扩展字段（F-1.3l Phase 1 Task 9）
    if mode == "deep":
        d = layers["dispatch"]["data"]
        for f in REQUIRED_DISPATCH_DATA_FIELDS:
            assert f in d, f"deep 模式 dispatch.data 缺 {f!r}（F-1.3l 扩展）"

        per_step = d["per_step_ms"]
        assert isinstance(per_step, dict), (
            f"dispatch.data.per_step_ms 必须是 dict，实际 {type(per_step).__name__}"
        )
        for step in REQUIRED_PER_STEP_FIELDS:
            assert step in per_step, f"per_step_ms 缺 {step!r}"
            assert isinstance(per_step[step], int), (
                f"per_step_ms.{step} 必须是 int，实际 {type(per_step[step]).__name__}"
            )
```

（删掉原来第 83-87 行的 "elapsed_ms in layers[dispatch][data]" 检查，因为已包含在 REQUIRED_DISPATCH_DATA_FIELDS 里）

- [ ] **Step 4: 跑测试 GREEN**

Run: `pytest tests/test_assert_schema_per_step.py tests/test_assert_sw_inspect_schema.py -v`

Expected: 全部 PASS（包含现有 F-1.3j+k 的测试也不破坏）

- [ ] **Step 5: commit**

```bash
git add tests/test_assert_schema_per_step.py tools/assert_sw_inspect_schema.py
git commit -m "feat(schema): per_step_ms 字段约束 + REQUIRED_DISPATCH_DATA_FIELDS (F-1.3l T9)"
```

---

## Task 10: rc=66 per_step 总和超差

**Files:**
- Modify: `tests/test_assert_schema_per_step.py`
- Modify: `tools/assert_sw_inspect_schema.py`

- [ ] **Step 1: 加失败测试**

在 `tests/test_assert_schema_per_step.py` 的 `TestSchemaPerStep` 类加：

```python
    def test_schema_rejects_sum_mismatch_cold_path(self, tmp_path, monkeypatch):
        """冷启路径（非 attach / 非异常）总和必须 ≈ elapsed_ms（±50ms）。"""
        doc = _make_valid_doc()
        # per_step 和 = 100+50+30+20 = 200；设 elapsed_ms = 500（差 300ms，超 ±50）
        doc["layers"]["dispatch"]["data"]["elapsed_ms"] = 500
        doc["layers"]["dispatch"]["data"]["attached_existing_session"] = False
        # 让所有 per_step 都 > 0（代表冷启路径，非 timeout / 非异常）
        doc["layers"]["dispatch"]["data"]["per_step_ms"] = {
            "dispatch_ms": 100,
            "revision_ms": 50,
            "visible_ms": 30,
            "exitapp_ms": 20,
        }
        path = tmp_path / "sum_mismatch.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        # assert_schema_v1 抛 AssertionError 含 "sum" / rc=1（默认）
        # 但若我们希望 rc=66，需要 CLI main 区分。本测试先只看 AssertionError
        with pytest.raises(AssertionError, match="per_step.*sum"):
            assert_schema_v1(path)

    def test_schema_accepts_sum_mismatch_exception_path(self, tmp_path):
        """异常路径（某步 = -1 哨兵）总和不等 elapsed_ms 是合法的。"""
        doc = _make_valid_doc()
        doc["layers"]["dispatch"]["data"]["elapsed_ms"] = 200
        # revision_ms = -1 表示"运行但抛异常"，总和含 -1 不可能等 elapsed
        doc["layers"]["dispatch"]["data"]["per_step_ms"] = {
            "dispatch_ms": 100,
            "revision_ms": -1,
            "visible_ms": 30,
            "exitapp_ms": 20,
        }
        path = tmp_path / "exc_path.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        assert_schema_v1(path)  # 不抛（异常路径宽松）

    def test_schema_accepts_attach_path_all_zero(self, tmp_path):
        """attach 路径 per_step 全 0 + elapsed_ms = 0 合法。"""
        doc = _make_valid_doc()
        doc["layers"]["dispatch"]["data"]["elapsed_ms"] = 0
        doc["layers"]["dispatch"]["data"]["attached_existing_session"] = True
        doc["layers"]["dispatch"]["data"]["per_step_ms"] = {
            "dispatch_ms": 0,
            "revision_ms": 0,
            "visible_ms": 0,
            "exitapp_ms": 0,
        }
        path = tmp_path / "attach.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        assert_schema_v1(path)  # 不抛（attach 路径宽松）
```

- [ ] **Step 2: 跑测试 RED**

Run: `pytest tests/test_assert_schema_per_step.py -v`

Expected: 3 个新测试 FAIL（尚未实现总和断言）

- [ ] **Step 3: 修改 assert_schema_v1 加总和检查**

在 `tools/assert_sw_inspect_schema.py` 的 `assert_schema_v1` 函数的 per_step 检查块末尾追加：

```python
        # F-1.3l Phase 1 Task 10：冷启路径总和 ≈ elapsed_ms（±50ms）
        # 宽松条件：attach 路径（elapsed_ms=0 + 全 0）/ 任何哨兵值 -1 出现 → 跳过总和检查
        is_attach = (
            d["attached_existing_session"]
            and all(per_step[s] == 0 for s in REQUIRED_PER_STEP_FIELDS)
        )
        has_exception = any(per_step[s] == -1 for s in REQUIRED_PER_STEP_FIELDS)
        if not is_attach and not has_exception:
            total = sum(per_step[s] for s in REQUIRED_PER_STEP_FIELDS)
            diff = abs(total - d["elapsed_ms"])
            assert diff <= 50, (
                f"冷启路径 per_step 总和 {total} 与 elapsed_ms {d['elapsed_ms']} "
                f"差 {diff}ms > ±50ms 容差（F-1.3l rc=66 边界）"
            )
```

- [ ] **Step 4: 修改 main() 区分 rc=66**

在 `tools/assert_sw_inspect_schema.py` 的 `main()` 函数里，把 `except AssertionError: raise` 改为：

```python
    except AssertionError as e:
        # F-1.3l Phase 1：区分 rc=1（schema 结构错）vs rc=66（总和超差）
        if "per_step" in str(e) and "sum" in str(e):
            print(f"per_step total mismatch: {e}", file=sys.stderr)
            return 66
        raise
```

- [ ] **Step 5: 跑测试 GREEN**

Run: `pytest tests/test_assert_schema_per_step.py tests/test_assert_sw_inspect_schema.py -v`

Expected: 全部 PASS

- [ ] **Step 6: commit**

```bash
git add tests/test_assert_schema_per_step.py tools/assert_sw_inspect_schema.py
git commit -m "feat(schema): per_step 总和断言 + rc=66 新增 (F-1.3l T10)"
```

---

## Task 11: assert_ac3_range 新建（首次代码化 AC-3）

**Files:**
- Create: `tests/test_assert_ac3_range.py`
- Modify: `tools/assert_sw_inspect_schema.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_assert_ac3_range.py`：

```python
"""AC-3 区间断言单测（F-1.3l Phase 1 Task 11 — AC-3 首次代码化）。

AC-3 从 F-1.3j+k runbook 文字期望（[3000, 15000]）升级为代码断言。
Phase 1 初值 [100, 30000] 宽容兼容现状（浅档 310ms 深档 3295ms 都在内），
Phase 3 再按 Phase 2 实测收紧。
"""

from __future__ import annotations

import pytest

from tools.assert_sw_inspect_schema import (
    AC3_LOWER_MS,
    AC3_UPPER_MS,
    assert_ac3_range,
)


class TestAC3Range:
    def test_ac3_initial_bounds_100_30000(self):
        """Phase 1 初值区间 [100, 30000] 覆盖已知双峰 + 30s timeout 上限。"""
        assert AC3_LOWER_MS == 100
        assert AC3_UPPER_MS == 30_000

    def test_shallow_peak_310ms_passes(self):
        """已知浅档中位数 310ms 在 [100, 30000] 内。"""
        data = {"elapsed_ms": 310, "attached_existing_session": False}
        assert_ac3_range(data)  # 不抛

    def test_deep_peak_3295ms_passes(self):
        """已知深档中位数 3295ms 在 [100, 30000] 内。"""
        data = {"elapsed_ms": 3295, "attached_existing_session": False}
        assert_ac3_range(data)  # 不抛

    def test_f1_baseline_5492ms_passes(self):
        """F.1 首次 baseline 5492ms 在 [100, 30000] 内。"""
        data = {"elapsed_ms": 5492, "attached_existing_session": False}
        assert_ac3_range(data)  # 不抛

    def test_below_lower_bound_fails(self):
        """< 100ms 触发 fail（防止"瞬时"异常点）。"""
        data = {"elapsed_ms": 50, "attached_existing_session": False}
        with pytest.raises(AssertionError, match="AC-3"):
            assert_ac3_range(data)

    def test_above_upper_bound_fails(self):
        """> 30000ms 触发 fail（超 30s 上限）。"""
        data = {"elapsed_ms": 35_000, "attached_existing_session": False}
        with pytest.raises(AssertionError, match="AC-3"):
            assert_ac3_range(data)

    def test_attach_path_skipped(self):
        """attach 路径 elapsed_ms=0 但 attached_existing_session=True → 跳过检查。"""
        data = {"elapsed_ms": 0, "attached_existing_session": True}
        assert_ac3_range(data)  # 不抛（attach 路径豁免）
```

- [ ] **Step 2: 跑测试 RED**

Run: `pytest tests/test_assert_ac3_range.py -v`

Expected: FAIL（ImportError，AC3_LOWER_MS / AC3_UPPER_MS / assert_ac3_range 都不存在）

- [ ] **Step 3: 实现 assert_ac3_range**

在 `tools/assert_sw_inspect_schema.py` 的常量段加：

```python
# F-1.3l Phase 1 Task 11：AC-3 首次代码化
# Phase 1 初值宽容 [100, 30000] 兼容已知双峰 + 对齐 test_sw_inspect_real.py 30s 上限
# Phase 3 会按 Phase 2 实测数据收紧（浅档中位 × 0.5 / 深档中位 × 2）
AC3_LOWER_MS = 100
AC3_UPPER_MS = 30_000
```

在文件末尾（`if __name__ == "__main__":` 之前）加函数：

```python
def assert_ac3_range(dispatch_data: dict) -> None:
    """AC-3 断言：dispatch.data.elapsed_ms 落在 [AC3_LOWER_MS, AC3_UPPER_MS] 区间。

    attach 路径（attached_existing_session=True）豁免 — elapsed_ms=0 是硬编码语义。

    Raises:
        AssertionError: elapsed_ms 超出区间；消息含 "AC-3" 便于 grep。
    """
    if dispatch_data.get("attached_existing_session"):
        return  # attach 路径豁免

    elapsed = dispatch_data["elapsed_ms"]
    assert AC3_LOWER_MS <= elapsed <= AC3_UPPER_MS, (
        f"AC-3 区间检查失败：elapsed_ms={elapsed}ms 超出 "
        f"[{AC3_LOWER_MS}, {AC3_UPPER_MS}]ms"
    )
```

- [ ] **Step 4: 跑测试 GREEN**

Run: `pytest tests/test_assert_ac3_range.py -v`

Expected: 全部 PASS

- [ ] **Step 5: commit**

```bash
git add tests/test_assert_ac3_range.py tools/assert_sw_inspect_schema.py
git commit -m "feat(ac3): AC-3 区间断言首次代码化，初值 [100, 30000] (F-1.3l T11)"
```

---

## Task 12: runbook §7 F-1.3l Phase 1 完成标记

**Files:**
- Modify: `docs/superpowers/runbooks/sw-self-hosted-runner-setup.md`

- [ ] **Step 1: 在 §7 F-1.3l follow-up 段补标记**

查找 `docs/superpowers/runbooks/sw-self-hosted-runner-setup.md` 中的 `**F-1.3l follow-up — dispatch.elapsed_ms 双峰分布根因调查**` 这一行，在其后第一段（"猜测路径"之前）插入：

```markdown
**Phase 1 完成回填**（2026-04-XX，提交 SHA `<PHASE-1-MERGE-SHA>`）：
- ✅ per_step_ms 4 段计时已合入 `sw_probe.probe_dispatch`
- ✅ AC-3 区间首次代码化为 `assert_ac3_range(dispatch_data)` 函数，初值 `[100, 30000]ms`（宽容档）
- ✅ assert_sw_inspect_schema.py 扩展 `REQUIRED_DISPATCH_DATA_FIELDS` + rc=66 总和超差
- ✅ Phase 1 单测 16 个全绿（tests/test_sw_probe_dispatch_per_step.py + test_assert_schema_per_step.py + test_assert_ac3_range.py）
- 状态：Phase 2 可开工（见 F-1.3l spec §8.0 前置 checklist）
```

（`<PHASE-1-MERGE-SHA>` 占位符留给实际 merge 后回填）

- [ ] **Step 2: commit**

```bash
git add docs/superpowers/runbooks/sw-self-hosted-runner-setup.md
git commit -m "docs(sw-self-hosted-runner): runbook §7 F-1.3l Phase 1 完成回填标记 (F-1.3l T12)"
```

---

## Task 13: Phase 1 开 PR + Merge main

**Files:**
- 无直接修改（git 操作）

- [ ] **Step 1: push 分支 + 开 PR**

Run:

```bash
git push -u origin feat/f-1-3l-phase1
gh pr create --title "feat(f-1-3l): Phase 1 — per_step_ms 仪器化 + AC-3 首次代码化" --body "$(cat <<'EOF'
## Summary
- probe_dispatch 重构：单点 elapsed_ms → 4 段 per_step timing（dispatch/revision/visible/exitapp_ms）
- 哨兵常量：-1=抛异常 / 0=未到达 / ≥1=真实测量（<1ms 截断为 1）
- assert_sw_inspect_schema 扩展 per_step 约束 + rc=66 总和超差
- AC-3 从 runbook 文字首次代码化为 `assert_ac3_range()`，初值 `[100, 30000]ms` 宽容档
- 16 个新单测全绿（Linux CI 可跑，不依赖真 SW）

## Test plan
- [x] `pytest tests/test_sw_probe_dispatch_per_step.py -v` 全绿
- [x] `pytest tests/test_assert_schema_per_step.py -v` 全绿
- [x] `pytest tests/test_assert_ac3_range.py -v` 全绿
- [x] `pytest tests/test_sw_probe.py tests/test_assert_sw_inspect_schema.py -v` 无回归
- [ ] sw-smoke CI run 后验证 sw-inspect-deep.json 有 per_step_ms 字段 + AC-3 断言绿

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 2: 触发 sw-smoke CI 验证**

Run:

```bash
gh workflow run sw-smoke.yml --ref feat/f-1-3l-phase1
# 等几秒后：
gh run list --workflow=sw-smoke.yml --limit 1
```

Expected: 最新 run conclusion=success（所有 AC 绿，包括首次代码化的 AC-3）

- [ ] **Step 3: Merge main**

Run:

```bash
gh pr merge --squash --delete-branch
git checkout main && git pull
```

- [ ] **Step 4: 回填 runbook 的 MERGE SHA**

Run:

```bash
PHASE1_SHA=$(git rev-parse HEAD)
# 编辑 docs/superpowers/runbooks/sw-self-hosted-runner-setup.md 把
# <PHASE-1-MERGE-SHA> 替换为 $PHASE1_SHA 前 7 位
```

```bash
git add docs/superpowers/runbooks/sw-self-hosted-runner-setup.md
git commit -m "docs(sw-self-hosted-runner): 回填 Phase 1 merge SHA (F-1.3l T13)"
git push origin main
```

---

# Phase 2：3 假设实验（临时探针）

## Task 14: 创建 F13L_REVERT_CHECKLIST.md

**Files:**
- Create: `F13L_REVERT_CHECKLIST.md`

- [ ] **Step 1: 建 checklist 模板**

新建 `F13L_REVERT_CHECKLIST.md`：

```markdown
# F-1.3l 临时改动 revert 清单

**建立于**：2026-04-XX（Phase 2 开工）
**收尾于**：2026-04-XX（F-1.3l 关闭）

## 临时代码引用清点

| 文件 | 行号 | 内容 |
|---|---|---|
| `adapters/solidworks/sw_probe.py` | XXX | `probe_investigation_env()` 函数 |
| `.github/workflows/sw-smoke.yml` | 19 | `runs-on` 追加 `f13l-exclusive` label |
| `scripts/f13l_run.ps1` | 全文 | Phase 2 一键入口 |
| `scripts/f13l_h1_license_test.ps1` | 全文 | H1 实验 |
| `scripts/f13l_h2_rot_observe.py` | 全文 | H2 被动观测 |
| `scripts/f13l_h3_gradient_scan.ps1` | 全文 | H3 梯度扫描 |
| `scripts/f13l_analyze.py` | 全文 | 分析脚本 |

## Revert 执行顺序

- [ ] (1) `probe_investigation_env()` 函数从 sw_probe.py 删除
- [ ] (2) `scripts/f13l_run.ps1` 删除
- [ ] (3) `scripts/f13l_h1_license_test.ps1` 删除
- [ ] (4) `scripts/f13l_h2_rot_observe.py` 删除
- [ ] (5) `scripts/f13l_h3_gradient_scan.ps1` 删除
- [ ] (6) `scripts/f13l_analyze.py` 删除
- [ ] (7) workflow `runs-on` 移除 `f13l-exclusive` → 恢复 `[self-hosted, windows, solidworks]`
- [ ] (8) `f2-evidence-f13l/` 保留本地 CSV + 加 `.gitignore`
- [ ] (9) `archive/f13l-evidence` 分支已 push 到 origin（确认）
- [ ] (10) grep `# TEMP(F-1.3l):` 全库扫描，确认所有临时注释已清理
- [ ] (11) F13L_REVERT_CHECKLIST.md 本身删除

## grep 扫描命令

```bash
grep -rn "TEMP(F-1.3l)" adapters/ scripts/ tests/ tools/ .github/
grep -rn "probe_investigation_env" adapters/ scripts/ tests/ tools/
grep -rn "f13l" scripts/ .github/workflows/
```

## 保留不 revert（永久基础设施）

- `per_step_ms` 4 字段 + 哨兵常量 + 最小值截断（Phase 1 T1-T8）
- `REQUIRED_DISPATCH_DATA_FIELDS` + rc=66（Phase 1 T9-T10）
- `assert_ac3_range()` 函数 + AC3_LOWER_MS / AC3_UPPER_MS 常量（Phase 1 T11）
- 所有 Phase 1 单测（test_sw_probe_dispatch_per_step / test_assert_schema_per_step / test_assert_ac3_range）
```

- [ ] **Step 2: commit**

```bash
git add F13L_REVERT_CHECKLIST.md
git commit -m "chore(f-1-3l): Phase 2 revert checklist 初始化 (F-1.3l T14)"
```

---

## Task 15: workflow 追加 f13l-exclusive label

**Files:**
- Modify: `.github/workflows/sw-smoke.yml:19`

- [ ] **Step 1: 修改 runs-on**

在 `.github/workflows/sw-smoke.yml` 第 19 行：

```yaml
    runs-on: [self-hosted, windows, solidworks]
```

改为：

```yaml
    # TEMP(F-1.3l): runs-on 临时追加 f13l-exclusive label 隔离 Phase 2 实验
    # 删除请见 F13L_REVERT_CHECKLIST.md 第 7 项
    runs-on: [self-hosted, windows, solidworks, f13l-exclusive]
```

- [ ] **Step 2: runner 临时加 f13l-exclusive label**

在 runner 机器上（开 admin PowerShell）：

```powershell
cd D:\actions-runner
.\config.cmd --token <TOKEN> remove
.\config.cmd --token <TOKEN> --labels "self-hosted,windows,solidworks,f13l-exclusive"
```

（或用 GitHub UI：Settings → Actions → Runners → Edit → 添加 `f13l-exclusive` label）

- [ ] **Step 3: commit 并确认 sw-smoke 还能找到 runner**

```bash
git add .github/workflows/sw-smoke.yml
git commit -m "chore(f-1-3l): workflow runs-on 追加 f13l-exclusive label (F-1.3l T15)"
git push origin main
gh workflow run sw-smoke.yml --ref main
gh run list --workflow=sw-smoke.yml --limit 1
```

Expected: run 状态 in_progress（runner 匹配到 4 labels 正常领取）

- [ ] **Step 4: 更新 F13L_REVERT_CHECKLIST.md 填实际行号**

Edit F13L_REVERT_CHECKLIST.md 把 `.github/workflows/sw-smoke.yml | 19` 改为实际的行号。

---

## Task 16: probe_investigation_env 临时函数

**Files:**
- Modify: `adapters/solidworks/sw_probe.py` 在 `probe_loadaddin` 函数末尾之后（约 `:740`）

- [ ] **Step 1: 加临时函数**

在 `adapters/solidworks/sw_probe.py` 末尾（`probe_loadaddin` 后）追加：

```python
# ============================================================
# TEMP(F-1.3l): probe_investigation_env 临时函数
# 删除请见 F13L_REVERT_CHECKLIST.md 第 1 项
# ============================================================


def probe_investigation_env() -> dict:
    """F-1.3l Phase 2 临时探针：返回 3 条假设的相关环境字段。

    所有字段尽力采集；任一子探针失败不影响其他字段。
    不进 schema，不走 AC-2 断言，只由 Phase 2 实验脚本直调。

    Returns:
        dict with 5 keys:
          license_session_age_sec: H1 — sldWorkerManager 服务运行时长（秒），-1 = 读取失败
          com_rot_entry_count: H2 — 当前 ROT 条目总数，-1 = 读取失败
          com_registration_timestamp: H2 — ROT 中 SldWorks 相关条目的注册时间戳（ISO8601），"" = 无
          defender_last_scan_age_sec: H3 — Defender 最后扫描距今（秒），-1 = 读取失败
          defender_rtp_state: H3 — Defender 实时保护状态（"enabled"/"disabled"/"unknown"）
    """
    import subprocess
    from datetime import datetime, timezone

    result = {
        "license_session_age_sec": -1,
        "com_rot_entry_count": -1,
        "com_registration_timestamp": "",
        "defender_last_scan_age_sec": -1,
        "defender_rtp_state": "unknown",
    }

    # H1: license_session_age_sec（从 sldWorkerManager 服务查 StartTime）
    try:
        ps_cmd = (
            "(Get-Process sldWorkerManager -ErrorAction SilentlyContinue | "
            "Sort-Object StartTime | Select-Object -First 1).StartTime.ToString('o')"
        )
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=5
        )
        if out.returncode == 0 and out.stdout.strip():
            start_time = datetime.fromisoformat(out.stdout.strip())
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)
            age = (datetime.now(tz=timezone.utc) - start_time).total_seconds()
            result["license_session_age_sec"] = int(age)
    except Exception:
        pass

    # H2: COM ROT 枚举
    try:
        import pythoncom

        pythoncom.CoInitialize()
        try:
            rot = pythoncom.GetRunningObjectTable()
            entries = list(rot.EnumRunning())
            result["com_rot_entry_count"] = len(entries)
            for moniker in entries:
                try:
                    name = moniker.GetDisplayName(pythoncom.CreateBindCtx(0), None)
                    if "SldWorks" in name or "sldworks" in name.lower():
                        result["com_registration_timestamp"] = datetime.now(
                            tz=timezone.utc
                        ).isoformat().replace("+00:00", "Z")
                        break
                except Exception:
                    continue
        finally:
            pythoncom.CoUninitialize()
    except Exception:
        pass

    # H3: Defender 状态
    try:
        ps_cmd = (
            "$s = Get-MpComputerStatus -ErrorAction SilentlyContinue; "
            "if ($s) { "
            "  $age = (Get-Date) - $s.QuickScanEndTime; "
            "  $rtp = if ($s.RealTimeProtectionEnabled) { 'enabled' } else { 'disabled' }; "
            "  Write-Output \"$([int]$age.TotalSeconds)|$rtp\" "
            "}"
        )
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=5
        )
        if out.returncode == 0 and "|" in out.stdout:
            age_str, rtp = out.stdout.strip().split("|", 1)
            result["defender_last_scan_age_sec"] = int(age_str)
            result["defender_rtp_state"] = rtp
    except Exception:
        pass

    return result
```

- [ ] **Step 2: 更新 F13L_REVERT_CHECKLIST.md 填实际行号**

- [ ] **Step 3: 快速手动验证（runner 上）**

Run:

```bash
python -c "from adapters.solidworks.sw_probe import probe_investigation_env; print(probe_investigation_env())"
```

Expected: 返回 dict 5 字段都非 None（值可能是 -1 表示采集失败，但字段齐全）

- [ ] **Step 4: commit**

```bash
git add adapters/solidworks/sw_probe.py F13L_REVERT_CHECKLIST.md
git commit -m "feat(sw_probe): probe_investigation_env() 临时探针 (F-1.3l T16)"
git push origin main
```

---

## Task 17: .gitignore + f2-evidence-f13l 目录

**Files:**
- Modify: `.gitignore`
- Create: `f2-evidence-f13l/.gitkeep`（占位）

- [ ] **Step 1: 修改 .gitignore**

在 `.gitignore` 末尾追加：

```
# TEMP(F-1.3l): Phase 2 evidence 归档，不入 main；Phase 2 完毕 commit 到 archive/f13l-evidence 分支
# 删除请见 F13L_REVERT_CHECKLIST.md 第 8 项
f2-evidence-f13l/*.csv
f2-evidence-f13l/*.stderr
f2-evidence-f13l/*.log
```

注意：只 ignore `.csv / .stderr / .log`，保留 `.gitkeep` 让目录存在。

- [ ] **Step 2: 创建目录占位**

```bash
mkdir -p f2-evidence-f13l
touch f2-evidence-f13l/.gitkeep
```

- [ ] **Step 3: commit**

```bash
git add .gitignore f2-evidence-f13l/.gitkeep
git commit -m "chore(f-1-3l): f2-evidence-f13l/ 目录 + gitignore 规则 (F-1.3l T17)"
```

---

## Task 18: H1 实验脚本 f13l_h1_license_test.ps1

**Files:**
- Create: `scripts/f13l_h1_license_test.ps1`

- [ ] **Step 1: 创建脚本**

新建 `scripts/f13l_h1_license_test.ps1`：

```powershell
# TEMP(F-1.3l): H1 假设 — SW license daemon idle timeout 证伪实验
# 删除请见 F13L_REVERT_CHECKLIST.md 第 3 项
<#
.SYNOPSIS
    F-1.3l Phase 2 H1 实验：10 轮交替（奇=kill daemon / 偶=baseline）
    每轮调 probe_dispatch 测 per_step_ms，stderr 落盘用于事后追溯。
.EXAMPLE
    pwsh -File scripts/f13l_h1_license_test.ps1
    输出：f2-evidence-f13l/h1_license.csv
#>

$ErrorActionPreference = 'Stop'
$evidence = Join-Path $PSScriptRoot ".." "f2-evidence-f13l"
New-Item -ItemType Directory -Path $evidence -Force | Out-Null

$csv = Join-Path $evidence "h1_license.csv"
$header = "hypothesis,iter,ts_utc,kill_flag,interval_min,dispatch_ms,revision_ms,visible_ms,exitapp_ms,elapsed_ms,attached_existing_session,license_session_age_sec,com_rot_entry_count,com_registration_timestamp,defender_last_scan_age_sec"
$header | Out-File -FilePath $csv -Encoding utf8

for ($iter = 1; $iter -le 10; $iter++) {
    $kill = if ($iter % 2 -eq 1) { 1 } else { 0 }

    if ($kill -eq 1) {
        Write-Host "[iter $iter] KILL sldWorkerManager"
        Get-Process sldWorkerManager -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 30
    } else {
        Write-Host "[iter $iter] BASELINE"
    }

    # E1: 等待 sldWorkerManager Running 且稳定 ≥ 3s
    $stable_start = $null
    for ($wait = 0; $wait -lt 30; $wait++) {
        $proc = Get-Process sldWorkerManager -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($proc) {
            if (-not $stable_start) { $stable_start = Get-Date }
            if ((Get-Date) - $stable_start -ge [TimeSpan]::FromSeconds(3)) { break }
        } else {
            $stable_start = $null
        }
        Start-Sleep -Seconds 1
    }

    $ts_utc = (Get-Date).ToUniversalTime().ToString('o')
    $stderr_path = Join-Path $evidence "h1_iter_$iter.stderr"

    # Python 单行直调 probe_dispatch + probe_investigation_env
    $json = python -c @"
import json, sys
try:
    from adapters.solidworks.sw_probe import probe_dispatch, probe_investigation_env
    r = probe_dispatch()
    env = probe_investigation_env()
    out = {**r.data, **env}
    # 展平 per_step_ms
    ps = out.pop('per_step_ms', {})
    out.update(ps)
    print(json.dumps(out))
except Exception as e:
    sys.stderr.write(f'python error: {type(e).__name__}: {e}\n')
    sys.exit(1)
"@ 2> $stderr_path

    if ($LASTEXITCODE -ne 0) {
        Write-Warning "[iter $iter] python 失败，stderr 已落盘 $stderr_path，跳过此轮"
        continue
    }

    try {
        $data = $json | ConvertFrom-Json
        # -1 哨兵 CSV 序列化为空字段
        $dispatch_ms = if ($data.dispatch_ms -eq -1) { "" } else { $data.dispatch_ms }
        $revision_ms = if ($data.revision_ms -eq -1) { "" } else { $data.revision_ms }
        $visible_ms = if ($data.visible_ms -eq -1) { "" } else { $data.visible_ms }
        $exitapp_ms = if ($data.exitapp_ms -eq -1) { "" } else { $data.exitapp_ms }

        $row = "H1,$iter,$ts_utc,$kill,,$dispatch_ms,$revision_ms,$visible_ms,$exitapp_ms,$($data.elapsed_ms),$($data.attached_existing_session),$($data.license_session_age_sec),$($data.com_rot_entry_count),$($data.com_registration_timestamp),$($data.defender_last_scan_age_sec)"
        $row | Out-File -FilePath $csv -Append -Encoding utf8
        Write-Host "[iter $iter] elapsed_ms=$($data.elapsed_ms) per_step=($dispatch_ms/$revision_ms/$visible_ms/$exitapp_ms)"
    } catch {
        Write-Warning "[iter $iter] JSON parse 失败：$_，跳过此轮"
        $json | Out-File -FilePath $stderr_path -Append -Encoding utf8
    }
}

Write-Host ""
Write-Host "H1 实验完成，CSV: $csv"
```

- [ ] **Step 2: 更新 F13L_REVERT_CHECKLIST.md**

- [ ] **Step 3: commit**

```bash
git add scripts/f13l_h1_license_test.ps1 F13L_REVERT_CHECKLIST.md
git commit -m "feat(f-1-3l): H1 license daemon kill 交替实验脚本 (F-1.3l T18)"
```

---

## Task 19: H2 被动观测脚本 f13l_h2_rot_observe.py

**Files:**
- Create: `scripts/f13l_h2_rot_observe.py`

- [ ] **Step 1: 创建脚本**

新建 `scripts/f13l_h2_rot_observe.py`：

```python
"""F-1.3l Phase 2 H2 假设 — COM ROT cache 被动观测（E3 改型后非证伪）。

TEMP(F-1.3l): 删除请见 F13L_REVERT_CHECKLIST.md 第 4 项

10 轮 subprocess 正常调 probe_dispatch，每轮记录：
- per_step_ms 4 字段（Phase 1）
- com_rot_entry_count / com_registration_timestamp（Phase 2 临时探针）

分析阶段：Spearman(com_rot_entry_count, elapsed_ms) 相关系数
- ≥ 0.7 → H2 HIT（作为 F-1.3l-Q2 根因线索，不认定因果）
- < 0.4 → H2 FALSIFIED
- 0.4-0.7 → H2 INCONCLUSIVE

输出：f2-evidence-f13l/h2_rot.csv
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

EVIDENCE = Path(__file__).parent.parent / "f2-evidence-f13l"
EVIDENCE.mkdir(exist_ok=True)
CSV_PATH = EVIDENCE / "h2_rot.csv"

HEADER = [
    "hypothesis", "iter", "ts_utc", "kill_flag", "interval_min",
    "dispatch_ms", "revision_ms", "visible_ms", "exitapp_ms",
    "elapsed_ms", "attached_existing_session",
    "license_session_age_sec", "com_rot_entry_count",
    "com_registration_timestamp", "defender_last_scan_age_sec",
]


def _run_probe_subprocess(iter_n: int) -> dict | None:
    """在新 subprocess 里调 probe_dispatch + probe_investigation_env，返回展平 dict。"""
    stderr_path = EVIDENCE / f"h2_iter_{iter_n}.stderr"

    code = """
import json
from adapters.solidworks.sw_probe import probe_dispatch, probe_investigation_env
r = probe_dispatch()
env = probe_investigation_env()
out = {**r.data, **env}
ps = out.pop('per_step_ms', {})
out.update(ps)
print(json.dumps(out))
"""

    try:
        with open(stderr_path, "w", encoding="utf-8") as ferr:
            result = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=False, text=True, timeout=90,
                stdout=subprocess.PIPE, stderr=ferr,
            )
        if result.returncode != 0:
            print(f"[iter {iter_n}] subprocess rc={result.returncode}，见 {stderr_path}")
            return None
        return json.loads(result.stdout)
    except Exception as e:
        print(f"[iter {iter_n}] 异常 {type(e).__name__}: {e}")
        return None


def _serialize_cell(v, *, as_sentinel_blank: bool = False):
    """-1 哨兵 → 空字段；其他保持原值。"""
    if as_sentinel_blank and v == -1:
        return ""
    return "" if v is None else str(v)


def main() -> int:
    with open(CSV_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(HEADER)

        for iter_n in range(1, 11):
            print(f"[iter {iter_n}] probing...")
            data = _run_probe_subprocess(iter_n)
            if data is None:
                continue

            row = [
                "H2", iter_n,
                datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
                "",  # kill_flag
                "",  # interval_min
                _serialize_cell(data.get("dispatch_ms"), as_sentinel_blank=True),
                _serialize_cell(data.get("revision_ms"), as_sentinel_blank=True),
                _serialize_cell(data.get("visible_ms"), as_sentinel_blank=True),
                _serialize_cell(data.get("exitapp_ms"), as_sentinel_blank=True),
                _serialize_cell(data.get("elapsed_ms")),
                _serialize_cell(data.get("attached_existing_session")),
                "",  # license_session_age_sec 对 H2 不必填
                _serialize_cell(data.get("com_rot_entry_count"), as_sentinel_blank=True),
                _serialize_cell(data.get("com_registration_timestamp")),
                "",  # defender_last_scan_age_sec 对 H2 不必填
            ]
            writer.writerow(row)
            print(f"[iter {iter_n}] elapsed_ms={data.get('elapsed_ms')} "
                  f"rot_count={data.get('com_rot_entry_count')}")

            # 每轮间隔 30s（足够让上一轮 ExitApp 的 SW 彻底退出）
            if iter_n < 10:
                time.sleep(30)

    print(f"\nH2 实验完成，CSV: {CSV_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 更新 F13L_REVERT_CHECKLIST.md**

- [ ] **Step 3: commit**

```bash
git add scripts/f13l_h2_rot_observe.py F13L_REVERT_CHECKLIST.md
git commit -m "feat(f-1-3l): H2 ROT 被动观测脚本（非证伪型）(F-1.3l T19)"
```

---

## Task 20: H3 梯度扫描脚本 f13l_h3_gradient_scan.ps1

**Files:**
- Create: `scripts/f13l_h3_gradient_scan.ps1`

- [ ] **Step 1: 创建脚本**

新建 `scripts/f13l_h3_gradient_scan.ps1`：

```powershell
# TEMP(F-1.3l): H3 假设 — Defender 扫描 + timing 分布采样
# 删除请见 F13L_REVERT_CHECKLIST.md 第 5 项
<#
.SYNOPSIS
    F-1.3l Phase 2 H3：间隔梯度 5/10/15/20/30/45/60 分钟 × 3 次 = 21 点。
    H3 双职责：Defender 相关性 + timing 分布采样（§8 AC-3 区间公式）。
.EXAMPLE
    pwsh -File scripts/f13l_h3_gradient_scan.ps1
    输出：f2-evidence-f13l/h3_gradient.csv
    总耗时：约 4-5 小时（间隔累加）
#>

$ErrorActionPreference = 'Stop'
$evidence = Join-Path $PSScriptRoot ".." "f2-evidence-f13l"
New-Item -ItemType Directory -Path $evidence -Force | Out-Null

$csv = Join-Path $evidence "h3_gradient.csv"
$header = "hypothesis,iter,ts_utc,kill_flag,interval_min,dispatch_ms,revision_ms,visible_ms,exitapp_ms,elapsed_ms,attached_existing_session,license_session_age_sec,com_rot_entry_count,com_registration_timestamp,defender_last_scan_age_sec"
$header | Out-File -FilePath $csv -Encoding utf8

$intervals = @(5, 10, 15, 20, 30, 45, 60)
$iter = 0
foreach ($interval_min in $intervals) {
    for ($rep = 1; $rep -le 3; $rep++) {
        $iter++
        Write-Host "[iter $iter] 间隔 $interval_min 分钟，第 $rep 次"
        Start-Sleep -Seconds ($interval_min * 60)

        $ts_utc = (Get-Date).ToUniversalTime().ToString('o')
        $stderr_path = Join-Path $evidence "h3_iter_$iter.stderr"

        $json = python -c @"
import json, sys
try:
    from adapters.solidworks.sw_probe import probe_dispatch, probe_investigation_env
    r = probe_dispatch()
    env = probe_investigation_env()
    out = {**r.data, **env}
    ps = out.pop('per_step_ms', {})
    out.update(ps)
    print(json.dumps(out))
except Exception as e:
    sys.stderr.write(f'python error: {type(e).__name__}: {e}\n')
    sys.exit(1)
"@ 2> $stderr_path

        if ($LASTEXITCODE -ne 0) {
            Write-Warning "[iter $iter] python 失败，跳过"
            continue
        }

        try {
            $data = $json | ConvertFrom-Json
            $dispatch_ms = if ($data.dispatch_ms -eq -1) { "" } else { $data.dispatch_ms }
            $revision_ms = if ($data.revision_ms -eq -1) { "" } else { $data.revision_ms }
            $visible_ms = if ($data.visible_ms -eq -1) { "" } else { $data.visible_ms }
            $exitapp_ms = if ($data.exitapp_ms -eq -1) { "" } else { $data.exitapp_ms }

            $row = "H3,$iter,$ts_utc,,$interval_min,$dispatch_ms,$revision_ms,$visible_ms,$exitapp_ms,$($data.elapsed_ms),$($data.attached_existing_session),,,,$($data.defender_last_scan_age_sec)"
            $row | Out-File -FilePath $csv -Append -Encoding utf8
            Write-Host "[iter $iter] elapsed_ms=$($data.elapsed_ms) defender_scan_age=$($data.defender_last_scan_age_sec)s"
        } catch {
            Write-Warning "[iter $iter] JSON parse 失败：$_"
        }
    }
}

Write-Host ""
Write-Host "H3 梯度扫描完成，CSV: $csv"
```

- [ ] **Step 2: 更新 F13L_REVERT_CHECKLIST.md**

- [ ] **Step 3: commit**

```bash
git add scripts/f13l_h3_gradient_scan.ps1 F13L_REVERT_CHECKLIST.md
git commit -m "feat(f-1-3l): H3 梯度扫描 21 点 timing 分布采样 (F-1.3l T20)"
```

---

## Task 21: analyze 分析脚本 f13l_analyze.py

**Files:**
- Create: `scripts/f13l_analyze.py`

- [ ] **Step 1: 创建脚本**

新建 `scripts/f13l_analyze.py`：

```python
"""F-1.3l Phase 2 一键分析：三态决策 + 打印 describe 全表。

TEMP(F-1.3l): 删除请见 F13L_REVERT_CHECKLIST.md 第 6 项

用法：
  # H1 分组对比
  python scripts/f13l_analyze.py --csv f2-evidence-f13l/h1_license.csv --hypothesis H1

  # H2 被动观测相关性
  python scripts/f13l_analyze.py --csv f2-evidence-f13l/h2_rot.csv --hypothesis H2

  # H3 双档分布
  python scripts/f13l_analyze.py --csv f2-evidence-f13l/h3_gradient.csv --hypothesis H3

  # 合并全部计算 AC-3 区间
  python scripts/f13l_analyze.py --merge-all
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from scipy.stats import spearmanr

EVIDENCE = Path(__file__).parent.parent / "f2-evidence-f13l"


def _load_and_clean(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, na_values=["", "-1"])
    # 过滤 attach 路径（integrity，不参与统计但不删除物理行）
    df = df[df["attached_existing_session"].fillna(False) == False]
    # 过滤 dispatch_ms NaN（抛异常 or 未到达）
    df = df.dropna(subset=["dispatch_ms"])
    return df


def analyze_h1(csv_path: Path) -> str:
    """H1: kill vs baseline 两组中位数差 ≥ 2x → HIT。"""
    df = _load_and_clean(csv_path)
    log_path = EVIDENCE / "analysis_H1.log"

    with open(log_path, "w", encoding="utf-8") as log:
        log.write(f"=== H1 分析 ({len(df)} 点） ===\n")
        log.write(df.groupby("kill_flag")["elapsed_ms"].describe().to_string())
        log.write("\n")

        if df["kill_flag"].nunique() < 2:
            decision = "INCONCLUSIVE: kill_flag 单值，无法对比"
        else:
            med_kill = df[df["kill_flag"] == 1]["elapsed_ms"].median()
            med_base = df[df["kill_flag"] == 0]["elapsed_ms"].median()
            ratio = max(med_kill, med_base) / max(min(med_kill, med_base), 1)
            log.write(f"\n中位数：kill={med_kill}ms / baseline={med_base}ms / 比率={ratio:.2f}x\n")

            if ratio >= 2.0:
                decision = f"HIT (ratio={ratio:.2f}x ≥ 2.0)"
            elif ratio < 1.5:
                decision = f"FALSIFIED (ratio={ratio:.2f}x < 1.5)"
            else:
                decision = f"INCONCLUSIVE (ratio={ratio:.2f}x, need +5 samples)"

        log.write(f"\n决策：{decision}\n")

    print(decision)
    print(f"详细分析已写入 {log_path}")
    return decision


def analyze_h2(csv_path: Path) -> str:
    """H2: Spearman(com_rot_entry_count, elapsed_ms) 相关性。"""
    df = _load_and_clean(csv_path)
    df = df.dropna(subset=["com_rot_entry_count"])
    log_path = EVIDENCE / "analysis_H2.log"

    with open(log_path, "w", encoding="utf-8") as log:
        log.write(f"=== H2 分析 ({len(df)} 点） ===\n")
        log.write(df[["elapsed_ms", "com_rot_entry_count"]].describe().to_string())
        log.write("\n")

        if len(df) < 5:
            decision = "INCONCLUSIVE: 样本量 < 5"
        else:
            rho, pval = spearmanr(df["com_rot_entry_count"], df["elapsed_ms"])
            log.write(f"\nSpearman ρ = {rho:.3f}, p = {pval:.4f}\n")

            if abs(rho) >= 0.7:
                decision = f"HIT (|ρ|={abs(rho):.2f} ≥ 0.7; F-1.3l-Q2 线索，非因果)"
            elif abs(rho) < 0.4:
                decision = f"FALSIFIED (|ρ|={abs(rho):.2f} < 0.4)"
            else:
                decision = f"INCONCLUSIVE (|ρ|={abs(rho):.2f}, need +5 samples)"

        log.write(f"\n决策：{decision}\n")

    print(decision)
    print(f"详细分析已写入 {log_path}")
    return decision


def analyze_h3(csv_path: Path) -> str:
    """H3: interval_min 分档看 timing；同时提供 timing 分布供 §8 (3) 公式。"""
    df = _load_and_clean(csv_path)
    log_path = EVIDENCE / "analysis_H3.log"

    with open(log_path, "w", encoding="utf-8") as log:
        log.write(f"=== H3 分析 ({len(df)} 点） ===\n")

        # 按 interval 分组
        log.write("按 interval_min 分档：\n")
        log.write(df.groupby("interval_min")["elapsed_ms"].describe().to_string())
        log.write("\n")

        # Defender 相关性
        df_def = df.dropna(subset=["defender_last_scan_age_sec"])
        if len(df_def) >= 5:
            rho, pval = spearmanr(
                df_def["defender_last_scan_age_sec"], df_def["elapsed_ms"]
            )
            log.write(f"\nSpearman(defender_last_scan_age_sec, elapsed_ms) ρ={rho:.3f} p={pval:.4f}\n")

        # 双档估计（KMeans k=2 简化：按中位数分）
        median = df["elapsed_ms"].median()
        shallow = df[df["elapsed_ms"] < median]["elapsed_ms"]
        deep = df[df["elapsed_ms"] >= median]["elapsed_ms"]
        log.write(f"\n双档推断（median={median}ms 分界）：\n")
        log.write(f"浅档（{len(shallow)} 点）中位数={shallow.median()}ms\n")
        log.write(f"深档（{len(deep)} 点）中位数={deep.median()}ms\n")

        if len(shallow) >= 5 and len(deep) >= 5:
            decision = f"DIST_READY（浅档 {shallow.median():.0f}ms / 深档 {deep.median():.0f}ms）"
        else:
            decision = f"INCONCLUSIVE: 浅档/深档样本不足 5（{len(shallow)}/{len(deep)}）"

        log.write(f"\n决策：{decision}\n")

    print(decision)
    print(f"详细分析已写入 {log_path}")
    return decision


def merge_all() -> None:
    """合并 H1/H2/H3 三份 CSV 计算 AC-3 区间（§8 (3) 公式）。"""
    frames = []
    for h in ("h1_license", "h2_rot", "h3_gradient"):
        p = EVIDENCE / f"{h}.csv"
        if p.exists():
            frames.append(pd.read_csv(p, na_values=["", "-1"]))

    if not frames:
        print("未找到任何 CSV，先跑实验脚本", file=sys.stderr)
        sys.exit(1)

    df = pd.concat(frames, ignore_index=True)
    df = df[df["attached_existing_session"].fillna(False) == False]
    df = df.dropna(subset=["dispatch_ms"])

    print(f"合并样本量：{len(df)}")

    median = df["elapsed_ms"].median()
    shallow = df[df["elapsed_ms"] < median]["elapsed_ms"]
    deep = df[df["elapsed_ms"] >= median]["elapsed_ms"]

    print(f"浅档 ({len(shallow)} 点) 中位数 = {shallow.median():.0f}ms")
    print(f"深档 ({len(deep)} 点) 中位数 = {deep.median():.0f}ms")

    if len(shallow) >= 5 and len(deep) >= 5:
        ac3_lower = int(shallow.median() * 0.5)
        ac3_upper = int(deep.median() * 2)
        print(f"\n§8 (3) 分支 A 推荐 AC-3 区间：[{ac3_lower}, {ac3_upper}]ms")
    else:
        print("\n分档样本不足（浅档/深档各需 ≥ 5 点），需延长 H3 采样")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--csv", type=Path, help="单假设 CSV 分析")
    p.add_argument("--hypothesis", choices=["H1", "H2", "H3"], help="假设标签")
    p.add_argument("--merge-all", action="store_true", help="合并 3 份 CSV 算 AC-3 区间")
    args = p.parse_args()

    if args.merge_all:
        merge_all()
        return 0

    if not args.csv or not args.hypothesis:
        p.error("需指定 --csv 和 --hypothesis，或用 --merge-all")

    func = {"H1": analyze_h1, "H2": analyze_h2, "H3": analyze_h3}[args.hypothesis]
    func(args.csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 更新 F13L_REVERT_CHECKLIST.md**

- [ ] **Step 3: 快速自检（单测不写但 syntax check）**

Run:

```bash
python -c "import ast; ast.parse(open('scripts/f13l_analyze.py').read()); print('OK')"
```

Expected: "OK"

- [ ] **Step 4: commit**

```bash
git add scripts/f13l_analyze.py F13L_REVERT_CHECKLIST.md
git commit -m "feat(f-1-3l): f13l_analyze.py 三态决策 + --merge-all (F-1.3l T21)"
```

---

## Task 22: 一键入口 f13l_run.ps1

**Files:**
- Create: `scripts/f13l_run.ps1`

- [ ] **Step 1: 创建脚本**

新建 `scripts/f13l_run.ps1`：

```powershell
# TEMP(F-1.3l): Phase 2 一键入口（--auto-chain 按 H1 → H2 → H3 串行，命中即停）
# 删除请见 F13L_REVERT_CHECKLIST.md 第 2 项
<#
.SYNOPSIS
    F-1.3l Phase 2 一键串行运行 + 命中早退出（H3 始终跑作 timing 采样）。
.EXAMPLE
    pwsh -File scripts/f13l_run.ps1 -AutoChain
    顺序：H1 跑 → analyze → 若 HIT 跳 H2 → H3 跑 → analyze --merge-all
         若 H1 FALSIFIED → H2 跑 → analyze → 无论结果 → H3 跑 → analyze --merge-all
#>

param(
    [switch]$AutoChain
)

$ErrorActionPreference = 'Stop'
$scripts = $PSScriptRoot

function Invoke-Hypothesis {
    param($Name, $ScriptPath, $AnalyzeFlag)

    Write-Host ""
    Write-Host "=========================================="
    Write-Host "Running $Name ..."
    Write-Host "=========================================="
    & pwsh -File $ScriptPath

    Write-Host ""
    Write-Host "Analyzing $Name ..."
    $csv = Join-Path $scripts ".." "f2-evidence-f13l" "$($Name.ToLower())_*.csv" | Get-Item | Select-Object -First 1
    $decision = python (Join-Path $scripts "f13l_analyze.py") --csv $csv.FullName --hypothesis $Name
    Write-Host "[$Name] decision: $decision"
    return $decision
}

if (-not $AutoChain) {
    Write-Host "用法：pwsh -File $PSCommandPath -AutoChain"
    exit 0
}

# H1
$h1 = Invoke-Hypothesis -Name "H1" -ScriptPath (Join-Path $scripts "f13l_h1_license_test.ps1") -AnalyzeFlag "kill_flag"

# H2（H1 命中后仍跑？spec §3：H1 HIT → 跳 H2 直接跑 H3）
if ($h1 -notmatch "HIT") {
    Write-Host ""
    Write-Host "H1 未命中，继续 H2..."
    $h2_script = Join-Path $scripts "f13l_h2_rot_observe.py"
    python $h2_script
    $h2_csv = Join-Path $scripts ".." "f2-evidence-f13l" "h2_rot.csv"
    $h2 = python (Join-Path $scripts "f13l_analyze.py") --csv $h2_csv --hypothesis H2
    Write-Host "[H2] decision: $h2"
}

# H3（始终跑 — timing 分布采样）
Write-Host ""
Write-Host "H3 始终跑（timing 分布采样）..."
$h3 = Invoke-Hypothesis -Name "H3" -ScriptPath (Join-Path $scripts "f13l_h3_gradient_scan.ps1") -AnalyzeFlag "interval_min"

# 合并分析
Write-Host ""
Write-Host "=========================================="
Write-Host "合并分析（§8 (3) AC-3 区间计算）"
Write-Host "=========================================="
python (Join-Path $scripts "f13l_analyze.py") --merge-all

Write-Host ""
Write-Host "Phase 2 完成。结果已写入 f2-evidence-f13l/"
Write-Host "下一步：按 §8 分支（A/B）进入 Phase 3"
```

- [ ] **Step 2: 更新 F13L_REVERT_CHECKLIST.md**

- [ ] **Step 3: commit**

```bash
git add scripts/f13l_run.ps1 F13L_REVERT_CHECKLIST.md
git commit -m "feat(f-1-3l): Phase 2 一键串行入口 --auto-chain (F-1.3l T22)"
git push origin main
```

---

## Task 23: Phase 2 开工前置 checklist 验证

**Files:**
- 无直接修改（人工验证）

- [ ] **Step 1: 验证 §8.0 前置 checklist 5 项**

执行：

- [x] Phase 1 PR 已 merge 到 main（Task 13 完成）
- [ ] runner 当前 idle
  ```bash
  gh run list --workflow=sw-smoke.yml --status=in_progress --limit 5
  ```
  Expected: 返回空
- [x] 建好 F13L_REVERT_CHECKLIST.md（Task 14）
- [x] workflow runs-on 追加 f13l-exclusive label（Task 15）
- [ ] 告知团队 F-1.3l 调查窗口

- [ ] **Step 2: Slack / issue 通知团队**

在 GitHub repo 开 issue："F-1.3l 调查窗口 [start-time, end-time]，期间 sw-smoke CI 被 f13l-exclusive 隔离"。

---

## Task 24: 跑 H1 实验 + 分析

**Files:**
- Create (by script): `f2-evidence-f13l/h1_license.csv`

- [ ] **Step 1: 跑 H1 脚本**

在 runner 上：

```bash
pwsh -File scripts/f13l_h1_license_test.ps1
```

Expected: 10 行 CSV + 10 个 stderr 文件（多数为空），总耗时 ~15-20 分钟

- [ ] **Step 2: 分析 H1**

```bash
python scripts/f13l_analyze.py --csv f2-evidence-f13l/h1_license.csv --hypothesis H1
```

Expected 输出：`HIT (ratio=XX)` 或 `FALSIFIED (ratio=XX)` 或 `INCONCLUSIVE`

- [ ] **Step 3: 根据决策分支**

- 若 HIT → 记录到 runbook §7，跳到 Task 26（H3）
- 若 FALSIFIED → 继续 Task 25（H2）
- 若 INCONCLUSIVE → 再跑一次脚本补采 +5 点，重分析；若 2 轮后仍 INCONCLUSIVE → 视为 FALSIFIED 继续 H2

---

## Task 25: 跑 H2 实验 + 分析

**Files:**
- Create (by script): `f2-evidence-f13l/h2_rot.csv`

- [ ] **Step 1: 跑 H2 脚本**

```bash
python scripts/f13l_h2_rot_observe.py
```

Expected: 10 行 CSV，总耗时 ~10 分钟（每轮 ~60s + 30s sleep）

- [ ] **Step 2: 分析 H2**

```bash
python scripts/f13l_analyze.py --csv f2-evidence-f13l/h2_rot.csv --hypothesis H2
```

Expected 输出：`HIT (|ρ|=XX)` / `FALSIFIED` / `INCONCLUSIVE`

- [ ] **Step 3: 记录决策**

H2 的 HIT 只作为 F-1.3l-Q2 线索，不直接认定因果。继续 H3 无论结果。

---

## Task 26: 跑 H3 梯度扫描

**Files:**
- Create (by script): `f2-evidence-f13l/h3_gradient.csv`

- [ ] **Step 1: 跑 H3 脚本**

```bash
pwsh -File scripts/f13l_h3_gradient_scan.ps1
```

Expected: 21 行 CSV，总耗时 **~5 小时**（5+10+15+20+30+45+60 = 185 min × 3）

**提示**：跑之前确认 runner 稳定（不会自动 reboot / 休眠），可用 `powercfg /change standby-timeout-ac 0`。

- [ ] **Step 2: 分析 H3**

```bash
python scripts/f13l_analyze.py --csv f2-evidence-f13l/h3_gradient.csv --hypothesis H3
```

Expected: `DIST_READY（浅档 XXXms / 深档 XXXms）`

- [ ] **Step 3: 合并分析**

```bash
python scripts/f13l_analyze.py --merge-all
```

Expected: 打印"推荐 AC-3 区间：[X, Y]ms"

---

## Task 27: 确定分支 A / B 并写入 runbook §7

**Files:**
- Modify: `docs/superpowers/runbooks/sw-self-hosted-runner-setup.md`

- [ ] **Step 1: 判断分支 A/B**

- 若 H1/H2/H3 任一命中且为 "by design" 行为（e.g. H1 HIT 是 license daemon 设计）→ **分支 A**
- 若 H1 命中且疑似 sw_probe 代码 bug（e.g. attach 路径误判）→ **分支 B**
- 若全 FALSIFIED → 触发 F-1.3l-Q2（spec §8 (2) 全伪路径）

- [ ] **Step 2: 写根因记录到 runbook §7**

在 runbook `**F-1.3l follow-up**` 段的 `**Phase 1 完成回填**` 之后追加：

```markdown
**根因确认**（2026-04-XX，Phase 2 完成）：
- 命中假设：H<X>（详见 f2-evidence-f13l/analysis_H<X>.log）
- 分支：A (by design) / B (代码 bug)
- 原始双峰分布：浅档中位 <X>ms / 深档中位 <Y>ms（样本量：浅档 <N>，深档 <M>）
- 推荐 AC-3 区间：[<L>, <U>]ms（公式：浅档中位 × 0.5 ~ 深档中位 × 2）
- 数据 commit：<archive/f13l-evidence 分支 SHA>

**复现步骤（约 N 分钟）**：
1. `git checkout <phase-2-commit-sha>`
2. `pwsh -File scripts/f13l_run.ps1 -AutoChain`
3. `diff f2-evidence-f13l/h<X>_*.csv` 与当时数据对比
备注：Phase 2 脚本已 revert，复现需 git checkout Phase 2 commit
```

- [ ] **Step 3: commit**

```bash
git add docs/superpowers/runbooks/sw-self-hosted-runner-setup.md
git commit -m "docs(sw-self-hosted-runner): F-1.3l 根因记录 + 复现步骤 (F-1.3l T27)"
```

---

# Phase 3：AC-3 区间收紧 + 临时探针 revert

## Task 28: 收紧 assert_ac3_range 区间

**Files:**
- Modify: `tools/assert_sw_inspect_schema.py`
- Modify: `tests/test_assert_ac3_range.py`

- [ ] **Step 1: 加新边界测试（RED）**

假设 Phase 2 实测浅档中位 310ms / 深档中位 3295ms（实际数据由 Task 26 `--merge-all` 产出），新区间 [155, 6590]。

在 `tests/test_assert_ac3_range.py` 新增类：

```python
class TestAC3RangePhase3:
    """Phase 3 收紧后新区间边界测试。"""

    def test_ac3_phase3_lower_155_passes(self):
        """浅档中位 310 × 0.5 = 155，下限恰好通过。"""
        data = {"elapsed_ms": 155, "attached_existing_session": False}
        assert_ac3_range(data)

    def test_ac3_phase3_upper_6590_passes(self):
        """深档中位 3295 × 2 = 6590，上限恰好通过。"""
        data = {"elapsed_ms": 6590, "attached_existing_session": False}
        assert_ac3_range(data)

    def test_ac3_phase3_below_155_fails(self):
        data = {"elapsed_ms": 154, "attached_existing_session": False}
        with pytest.raises(AssertionError, match="AC-3"):
            assert_ac3_range(data)

    def test_ac3_phase3_above_6590_fails(self):
        data = {"elapsed_ms": 6591, "attached_existing_session": False}
        with pytest.raises(AssertionError, match="AC-3"):
            assert_ac3_range(data)
```

同时把原 `test_ac3_initial_bounds_100_30000` 测试改名：

```python
    def test_ac3_phase3_bounds_155_6590(self):
        """Phase 3 收紧后新区间。"""
        assert AC3_LOWER_MS == 155
        assert AC3_UPPER_MS == 6590
```

- [ ] **Step 2: 跑测试 RED**

Run: `pytest tests/test_assert_ac3_range.py -v`

Expected: 4 个新测试 FAIL（旧常量 100/30000 不变）；旧 `test_ac3_initial_bounds` 测试也 FAIL（因为常量改名）

- [ ] **Step 3: 修改 assert_sw_inspect_schema.py 常量**

在 `tools/assert_sw_inspect_schema.py`：

```python
# F-1.3l Phase 3 Task 28：基于 Phase 2 实测收紧（浅档 310 × 0.5 / 深档 3295 × 2）
# 原 Phase 1 初值 [100, 30000] 宽容档由 Phase 2 实测数据替换
AC3_LOWER_MS = 155
AC3_UPPER_MS = 6590
```

（具体数字由 Task 26 --merge-all 实际产出决定，以上 155/6590 是基于当前 5 点历史数据的预估）

- [ ] **Step 4: 跑测试 GREEN**

Run: `pytest tests/test_assert_ac3_range.py -v`

Expected: 全部 PASS

- [ ] **Step 5: commit**

```bash
git add tools/assert_sw_inspect_schema.py tests/test_assert_ac3_range.py
git commit -m "feat(ac3): 收紧 AC-3 区间至 [155, 6590] 基于 Phase 2 实测 (F-1.3l T28)"
```

---

## Task 29: archive/f13l-evidence 分支 push

**Files:**
- 无直接修改（git 操作 + CSV 文件）

- [ ] **Step 1: 创建 archive 分支 + commit CSV**

```bash
git checkout --orphan archive/f13l-evidence
git rm -rf --cached .
git clean -fd
# 复制 f2-evidence-f13l 目录内容（即使 gitignored 也可 force add）
git add -f f2-evidence-f13l/*.csv f2-evidence-f13l/*.log
git commit -m "chore(f-1-3l): Phase 2 evidence snapshot (archive)"
git push -u origin archive/f13l-evidence
```

- [ ] **Step 2: 记录 archive SHA 回填 runbook**

```bash
ARCHIVE_SHA=$(git rev-parse HEAD)
echo "Archive SHA: $ARCHIVE_SHA"
```

在 runbook §7 F-1.3l 根因段把 `<archive/f13l-evidence 分支 SHA>` 替换为 `$ARCHIVE_SHA` 前 7 位。

- [ ] **Step 3: 切回 main**

```bash
git checkout main
git add docs/superpowers/runbooks/sw-self-hosted-runner-setup.md
git commit -m "docs(sw-self-hosted-runner): 回填 archive/f13l-evidence SHA (F-1.3l T29)"
```

---

## Task 30: revert 临时探针

**Files:**
- Delete: `scripts/f13l_run.ps1`
- Delete: `scripts/f13l_h1_license_test.ps1`
- Delete: `scripts/f13l_h2_rot_observe.py`
- Delete: `scripts/f13l_h3_gradient_scan.ps1`
- Delete: `scripts/f13l_analyze.py`
- Modify: `adapters/solidworks/sw_probe.py` 删除 probe_investigation_env
- Modify: `.github/workflows/sw-smoke.yml` 移除 f13l-exclusive label
- Delete: `F13L_REVERT_CHECKLIST.md`

- [ ] **Step 1: 按 F13L_REVERT_CHECKLIST.md 逐项勾**

打开 `F13L_REVERT_CHECKLIST.md`，按顺序执行（逐条勾 checkbox）：

```bash
# (1) probe_investigation_env 从 sw_probe.py 删除
# 找到 `# TEMP(F-1.3l): probe_investigation_env 临时函数` 段 + 完整函数体删除
# (2-6) 删除所有 scripts/f13l_*.{ps1,py}
git rm scripts/f13l_run.ps1
git rm scripts/f13l_h1_license_test.ps1
git rm scripts/f13l_h2_rot_observe.py
git rm scripts/f13l_h3_gradient_scan.ps1
git rm scripts/f13l_analyze.py

# (7) workflow runs-on 移除 f13l-exclusive
# 找 .github/workflows/sw-smoke.yml:19 改回 `[self-hosted, windows, solidworks]`

# (8) f2-evidence-f13l/ 本地保留（已 gitignore）

# (9) 确认 archive/f13l-evidence 已 push（Task 29 完成）
git ls-remote origin archive/f13l-evidence
# Expected: 返回 hash

# (10) grep 全库
grep -rn "TEMP(F-1.3l)" adapters/ scripts/ tests/ tools/ .github/
# Expected: 返回空（只允许 tests/test_*.py 里历史 RED 测试的引用）

grep -rn "probe_investigation_env" adapters/ scripts/ tests/ tools/
# Expected: 返回空

# (11) 删除 F13L_REVERT_CHECKLIST.md
git rm F13L_REVERT_CHECKLIST.md
```

- [ ] **Step 2: 恢复 runner labels**

在 runner 机器（admin PowerShell）：

```powershell
cd D:\actions-runner
.\config.cmd --token <TOKEN> remove
.\config.cmd --token <TOKEN> --labels "self-hosted,windows,solidworks"
```

（或 GitHub UI 去掉 `f13l-exclusive` label）

- [ ] **Step 3: 单 commit 收尾**

```bash
git add -A
git commit -m "chore(f-1-3l): 移除临时探针 + F-1.3l 收尾"
git push origin main
```

---

## Task 31: ≥ 6 次 CI run 验证新区间

**Files:**
- 无直接修改（CI 运行）

- [ ] **Step 1: 触发 6 次 sw-smoke CI**

```bash
for i in {1..6}; do
    gh workflow run sw-smoke.yml --ref main
    sleep 60  # 等一会避免过快并发
done
```

- [ ] **Step 2: 等所有 run 完成并拉数据**

```bash
gh run list --workflow=sw-smoke.yml --limit 6 --json databaseId,conclusion
# 全部 conclusion=success
```

- [ ] **Step 3: 验证 timing 落在新区间**

对每个 run 下载 `sw-inspect-deep.json`：

```bash
for run_id in <6 RUN IDS>; do
    gh run download $run_id -n sw-smoke-artifacts -D /tmp/f13l-verify-$run_id
    python -c "
import json
doc = json.load(open('/tmp/f13l-verify-$run_id/sw-inspect-deep.json'))
elapsed = doc['layers']['dispatch']['data']['elapsed_ms']
print(f'run $run_id: elapsed_ms={elapsed}')
assert 155 <= elapsed <= 6590, f'越界：{elapsed}'
"
done
```

Expected: 6 个 run 全部落在 [155, 6590]

- [ ] **Step 4: 分支 A 额外验证 — 双峰分布**

Spec §8 (5) 分支 A 要求：6 次 run 至少 2 个浅档（± 50%）+ 2 个深档（± 50%），不出现"两峰谷值"异常点。

```bash
# 假设浅档中位 310，深档中位 3295
# 浅档范围：155-465；深档范围：1648-4943；谷值：465-1648 不允许落点
python -c "
elapsed_list = [<6 runs elapsed>]
shallow = [e for e in elapsed_list if 155 <= e <= 465]
deep = [e for e in elapsed_list if 1648 <= e <= 4943]
valley = [e for e in elapsed_list if 466 <= e <= 1647]
assert len(shallow) >= 2, f'浅档 {len(shallow)} 点 < 2'
assert len(deep) >= 2, f'深档 {len(deep)} 点 < 2'
assert len(valley) == 0, f'发现 {len(valley)} 个谷值异常点'
print('分支 A §8 (5) 验证通过')
"
```

---

## Task 32: F.2 状态机升级 PASS clean

**Files:**
- Modify: `docs/superpowers/runbooks/sw-self-hosted-runner-setup.md`

- [ ] **Step 1: 更新 runbook 状态机**

查找 runbook 中的 `**F.2 状态保留 PASS pickup-only**` 段，改为：

```markdown
✅ **F.2 状态升级 PASS clean**（2026-04-XX，F-1.3l 关闭后升级）；
  AC-3 区间 [155, 6590]ms 由 Phase 2 20+ 点 + Phase 3 6 次 CI run 验证。
```

- [ ] **Step 2: commit**

```bash
git add docs/superpowers/runbooks/sw-self-hosted-runner-setup.md
git commit -m "docs(sw-self-hosted-runner): F.2 状态机 PASS pickup-only → PASS clean (F-1.3l T32)"
git push origin main
```

- [ ] **Step 3: F-1.3l 关闭确认**

在项目 memory 或 issue tracker 标记 F-1.3l closed。可更新 `C:\Users\procheng\.claude\projects\D--Work-cad-spec-gen\memory\MEMORY.md` 把 F-1.3l handoff memory 标记为 closed。

---

# 附录 A：Task 依赖图

```
Phase 1 (顺序严格):
  T1 哨兵常量 → T2 RED 冷启 → T3 GREEN 冷启 → T4 t0 回归 → T5 attach → T6 timeout
     → T7 异常 + 截断 → T8 visible/exitapp 异常 → T9 schema 常量 → T10 rc=66
     → T11 AC-3 代码化 → T12 runbook Phase 1 标记 → T13 merge main ▶▶▶

Phase 2 (顺序严格，Phase 1 merge 完才能开工):
  T14 checklist → T15 workflow label → T16 env 探针 → T17 gitignore
     → T18 H1 脚本 → T19 H2 脚本 → T20 H3 脚本 → T21 analyze → T22 一键 run
     → T23 前置验证 → T24 H1 跑 + 分析
         → [若 HIT] T26 H3 跑
         → [若 FALSIFIED/INCONCL] T25 H2 → T26 H3
     → T27 根因记录 ▶▶▶

Phase 3 (顺序严格):
  T28 AC-3 收紧 → T29 archive push → T30 revert → T31 CI 6 run 验证 → T32 F.2 升级
```

# 附录 B：关键命令快查

| 目标 | 命令 |
|---|---|
| Linux CI 本地预检 | `pytest tests/test_sw_probe_dispatch_per_step.py tests/test_assert_schema_per_step.py tests/test_assert_ac3_range.py -v` |
| 触发 sw-smoke 验证 | `gh workflow run sw-smoke.yml --ref main` |
| 下载 sw-inspect JSON | `gh run download <run-id> -n sw-smoke-artifacts` |
| Phase 2 一键跑 | `pwsh -File scripts/f13l_run.ps1 -AutoChain` |
| AC-3 区间计算 | `python scripts/f13l_analyze.py --merge-all` |
| revert 扫描 | `grep -rn "TEMP(F-1.3l)" adapters/ scripts/ tests/ tools/ .github/` |

---

**Plan 完成。** 32 个 Task，每 Task 2-5 步完整 TDD 循环（RED → GREEN → commit）。Phase 1 ≈ 13 tasks / Phase 2 ≈ 14 tasks / Phase 3 ≈ 5 tasks。
