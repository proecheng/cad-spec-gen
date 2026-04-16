# Stage C 可观测性改进 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 `SwComSession` 加 `last_convert_diagnostics` 属性，在 `stage_c.json` 的 per_target 里记录 worker 的 exit_code 和 stderr，让下次 Stage C 失败可以直接回溯。

**Architecture:** `SwComSession._do_convert` 在每个失败/成功分支写一个诊断 dict（stage + exit_code + stderr_tail）到 `self._last_convert_diagnostics`。`stage_c_session_restart` 每次 convert 后读取该属性，合并进 per_target。`convert_sldprt_to_step` 返回类型不变（仍 bool），对老调用方零破坏。

**Tech Stack:** Python 3.11+, pytest, subprocess, uv

**Spec:** `docs/superpowers/specs/2026-04-16-stage-c-diagnostics-design.md`

---

## 文件清单

| 操作 | 文件 | 变更摘要 |
|---|---|---|
| Modify | `adapters/solidworks/sw_com_session.py` | 加 `_last_convert_diagnostics` 属性 + `last_convert_diagnostics` property；`_do_convert` 和 `convert_sldprt_to_step` 在 6 个分支写诊断 |
| Modify | `tests/test_sw_com_session_subprocess.py` | 新增 7 条测试：6 种 stage + 1 条 reset 行为 |
| Modify | `tools/sw_b9_acceptance.py` | `stage_c_session_restart` 读 diag 合并 per_target |
| Create | `tests/test_sw_b9_acceptance.py` | Stage C 集成测试（mock session） |

---

## Task 1：success 路径 + 属性/Property（RED → GREEN）

**Files:**
- Modify: `adapters/solidworks/sw_com_session.py:47-50, 95-145`
- Modify: `tests/test_sw_com_session_subprocess.py`（在 class 末尾新增 1 条测试）

- [ ] **Step 1: 在 `tests/test_sw_com_session_subprocess.py` 末尾新增 success 路径测试**

在 `TestDoConvertSubprocess` 类末尾（紧接 `test_subprocess_called_with_expected_cmd` 之后）插入：

```python
    def test_diagnostics_on_success(self, tmp_path, monkeypatch):
        """成功路径 → stage=success, exit_code=0, stderr_tail 保留 worker warning。"""
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()

        def fake_run(cmd, **kwargs):
            Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(cmd[-1]).write_bytes(b"ISO-10303-214\n" + b"X" * 2000)
            return subprocess.CompletedProcess(
                cmd, 0, stdout="", stderr="worker: CloseDoc ignored: ..."
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        ok = s.convert_sldprt_to_step(
            str(tmp_path / "hex bolt.sldprt"),
            str(tmp_path / "out.step"),
        )
        assert ok is True
        diag = s.last_convert_diagnostics
        assert diag is not None
        assert diag["stage"] == "success"
        assert diag["exit_code"] == 0
        assert "CloseDoc" in diag["stderr_tail"]
```

- [ ] **Step 2: 运行新测试，确认失败（RED，属性不存在）**

```
uv run pytest "tests/test_sw_com_session_subprocess.py::TestDoConvertSubprocess::test_diagnostics_on_success" -v
```

预期：FAILED，`AttributeError: 'SwComSession' object has no attribute 'last_convert_diagnostics'`

- [ ] **Step 3: 在 `SwComSession.__init__` 里加属性，加 property，在 `_do_convert` 成功分支写 diag**

修改 `adapters/solidworks/sw_com_session.py`：

**修改 `__init__`（约第 47-50 行）：**

```python
def __init__(self) -> None:
    self._consecutive_failures = 0
    self._unhealthy = False
    self._lock = threading.Lock()
    self._last_convert_diagnostics: Optional[dict] = None
```

**在 `is_healthy` 之后（约第 55 行后）新增 property：**

```python
@property
def last_convert_diagnostics(self) -> Optional[dict]:
    """最近一次 convert_sldprt_to_step 的诊断信息（失败回溯用）。"""
    return self._last_convert_diagnostics
```

**修改 `_do_convert` 的成功分支（约第 144-145 行）：**

变更前：
```python
    os.replace(tmp_path, step_out)
    return True
```

变更后：
```python
    self._last_convert_diagnostics = {
        "stage": "success",
        "exit_code": proc.returncode,
        "stderr_tail": (proc.stderr or "")[:500],
    }
    os.replace(tmp_path, step_out)
    return True
```

- [ ] **Step 4: 运行新测试，确认通过（GREEN）**

```
uv run pytest "tests/test_sw_com_session_subprocess.py::TestDoConvertSubprocess::test_diagnostics_on_success" -v
```

预期：PASSED

- [ ] **Step 5: 运行整个 `test_sw_com_session_subprocess.py`，确认原有测试无退化**

```
uv run pytest tests/test_sw_com_session_subprocess.py -v
```

预期：全部 PASSED（原 5 条 + 新 1 条 = 6 条全绿）

- [ ] **Step 6: 不提交，等 Task 2-3 完成后一起提交**

---

## Task 2：subprocess_error 路径（RED → GREEN）

**Files:**
- Modify: `adapters/solidworks/sw_com_session.py`（`_do_convert` rc!=0 分支）
- Modify: `tests/test_sw_com_session_subprocess.py`（新增 1 条测试）

- [ ] **Step 1: 新增 subprocess_error 测试**

在 `TestDoConvertSubprocess` 类的 `test_diagnostics_on_success` 之后插入：

```python
    def test_diagnostics_on_subprocess_error(self, tmp_path, monkeypatch):
        """worker rc=3 → stage=subprocess_error, exit_code=3, stderr_tail 含错误。"""
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                cmd, 3, stdout="", stderr="worker: SaveAs3 saved=False errors=1"
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        ok = s.convert_sldprt_to_step(
            str(tmp_path / "broken.sldprt"),
            str(tmp_path / "out.step"),
        )
        assert ok is False
        diag = s.last_convert_diagnostics
        assert diag is not None
        assert diag["stage"] == "subprocess_error"
        assert diag["exit_code"] == 3
        assert "errors=1" in diag["stderr_tail"]
```

- [ ] **Step 2: 运行新测试，确认失败（RED）**

```
uv run pytest "tests/test_sw_com_session_subprocess.py::TestDoConvertSubprocess::test_diagnostics_on_subprocess_error" -v
```

预期：FAILED（`diag is None`，该分支还未写 diag）

- [ ] **Step 3: 修改 `_do_convert` 的 `proc.returncode != 0` 分支（约第 129-137 行）**

变更前：
```python
        if proc.returncode != 0:
            log.warning(
                "convert subprocess rc=%d sldprt=%s stderr=%s",
                proc.returncode,
                sldprt_path,
                (proc.stderr or "")[:300],
            )
            self._cleanup_tmp(tmp_path)
            return False
```

变更后：
```python
        if proc.returncode != 0:
            log.warning(
                "convert subprocess rc=%d sldprt=%s stderr=%s",
                proc.returncode,
                sldprt_path,
                (proc.stderr or "")[:300],
            )
            self._last_convert_diagnostics = {
                "stage": "subprocess_error",
                "exit_code": proc.returncode,
                "stderr_tail": (proc.stderr or "")[:500],
            }
            self._cleanup_tmp(tmp_path)
            return False
```

- [ ] **Step 4: 运行新测试 + 原有测试，确认全绿**

```
uv run pytest tests/test_sw_com_session_subprocess.py -v
```

预期：全 PASSED（7 条）

- [ ] **Step 5: 不提交，等 Task 3-4 完成后一起提交**

---

## Task 3：timeout + validation_failure + circuit_breaker + unexpected_exception（RED → GREEN）

**Files:**
- Modify: `adapters/solidworks/sw_com_session.py`（4 个分支写 diag）
- Modify: `tests/test_sw_com_session_subprocess.py`（新增 4 条 + 1 条 reset 测试）

- [ ] **Step 1: 新增 4 条失败路径测试 + 1 条 reset 测试**

在 `TestDoConvertSubprocess` 类的 `test_diagnostics_on_subprocess_error` 之后插入：

```python
    def test_diagnostics_on_timeout(self, tmp_path, monkeypatch):
        """subprocess timeout → stage=timeout, exit_code=None, stderr_tail=''。"""
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()

        def fake_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=30)

        monkeypatch.setattr(subprocess, "run", fake_run)

        ok = s.convert_sldprt_to_step(
            str(tmp_path / "hangs.sldprt"),
            str(tmp_path / "out.step"),
        )
        assert ok is False
        diag = s.last_convert_diagnostics
        assert diag is not None
        assert diag["stage"] == "timeout"
        assert diag["exit_code"] is None
        assert diag["stderr_tail"] == ""

    def test_diagnostics_on_validation_failure(self, tmp_path, monkeypatch):
        """worker rc=0 但 tmp STEP 太小 → stage=validation_failure。"""
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()

        def fake_run(cmd, **kwargs):
            Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(cmd[-1]).write_bytes(b"tiny")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)

        ok = s.convert_sldprt_to_step(
            str(tmp_path / "fake.sldprt"),
            str(tmp_path / "out.step"),
        )
        assert ok is False
        diag = s.last_convert_diagnostics
        assert diag is not None
        assert diag["stage"] == "validation_failure"
        assert diag["exit_code"] == 0

    def test_diagnostics_on_circuit_breaker_open(self, tmp_path, monkeypatch):
        """熔断器已开 → stage=circuit_breaker_open, exit_code=None。"""
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()
        s._unhealthy = True  # 直接置位，模拟已熔断

        ok = s.convert_sldprt_to_step(
            str(tmp_path / "any.sldprt"),
            str(tmp_path / "out.step"),
        )
        assert ok is False
        diag = s.last_convert_diagnostics
        assert diag is not None
        assert diag["stage"] == "circuit_breaker_open"
        assert diag["exit_code"] is None
        assert diag["stderr_tail"] == ""

    def test_diagnostics_on_unexpected_exception(self, tmp_path, monkeypatch):
        """_do_convert 抛未预期异常 → stage=unexpected_exception, stderr_tail 含 repr。"""
        from adapters.solidworks import sw_com_session as scs
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()

        def fake_do_convert(self, sldprt_path, step_out):
            raise RuntimeError("simulated crash")

        monkeypatch.setattr(scs.SwComSession, "_do_convert", fake_do_convert)

        ok = s.convert_sldprt_to_step(
            str(tmp_path / "any.sldprt"),
            str(tmp_path / "out.step"),
        )
        assert ok is False
        diag = s.last_convert_diagnostics
        assert diag is not None
        assert diag["stage"] == "unexpected_exception"
        assert "simulated crash" in diag["stderr_tail"]

    def test_diagnostics_reset_between_calls(self, tmp_path, monkeypatch):
        """连续两次调用：第二次的 diag 不应保留第一次的 stage。"""
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()

        # 第一次：subprocess_error
        def fake_run_fail(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 3, stdout="", stderr="fail")

        monkeypatch.setattr(subprocess, "run", fake_run_fail)
        s.convert_sldprt_to_step(
            str(tmp_path / "1.sldprt"), str(tmp_path / "1.step")
        )
        assert s.last_convert_diagnostics["stage"] == "subprocess_error"

        # 第二次：success（不同 fake）
        def fake_run_ok(cmd, **kwargs):
            Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(cmd[-1]).write_bytes(b"ISO-10303-214\n" + b"X" * 2000)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run_ok)
        s.convert_sldprt_to_step(
            str(tmp_path / "2.sldprt"), str(tmp_path / "2.step")
        )
        assert s.last_convert_diagnostics["stage"] == "success"
```

- [ ] **Step 2: 运行 5 条新测试，确认全部失败（RED）**

```
uv run pytest tests/test_sw_com_session_subprocess.py::TestDoConvertSubprocess -k "diagnostics_on_timeout or diagnostics_on_validation or diagnostics_on_circuit or diagnostics_on_unexpected or diagnostics_reset" -v
```

预期：5 条全部 FAILED（4 个分支未写 diag + reset 也因此失败）

- [ ] **Step 3: 在 `_do_convert` 和 `convert_sldprt_to_step` 补齐 4 个分支**

修改 `adapters/solidworks/sw_com_session.py`：

**修改 `_do_convert` 的 `TimeoutExpired` 分支（约第 120-127 行）：**

变更前：
```python
        except subprocess.TimeoutExpired:
            log.warning(
                "convert subprocess 超时 %ds，已被 subprocess.run kill；sldprt=%s",
                SINGLE_CONVERT_TIMEOUT_SEC,
                sldprt_path,
            )
            self._cleanup_tmp(tmp_path)
            return False
```

变更后：
```python
        except subprocess.TimeoutExpired:
            log.warning(
                "convert subprocess 超时 %ds，已被 subprocess.run kill；sldprt=%s",
                SINGLE_CONVERT_TIMEOUT_SEC,
                sldprt_path,
            )
            self._last_convert_diagnostics = {
                "stage": "timeout",
                "exit_code": None,
                "stderr_tail": "",
            }
            self._cleanup_tmp(tmp_path)
            return False
```

**修改 `_do_convert` 的 validation_failure 分支（约第 139-142 行）：**

变更前：
```python
        if not self._validate_step_file(tmp_path):
            log.warning("convert tmp STEP 校验失败: %s", tmp_path)
            self._cleanup_tmp(tmp_path)
            return False
```

变更后：
```python
        if not self._validate_step_file(tmp_path):
            log.warning("convert tmp STEP 校验失败: %s", tmp_path)
            self._last_convert_diagnostics = {
                "stage": "validation_failure",
                "exit_code": proc.returncode,
                "stderr_tail": (proc.stderr or "")[:500],
            }
            self._cleanup_tmp(tmp_path)
            return False
```

**修改 `convert_sldprt_to_step` 的熔断分支（约第 69-74 行）：**

变更前：
```python
        with self._lock:
            if self._unhealthy:
                log.info(
                    "熔断器已开：跳过 convert（系统性故障，call reset_session() 清除）"
                )
                return False
```

变更后：
```python
        with self._lock:
            if self._unhealthy:
                log.info(
                    "熔断器已开：跳过 convert（系统性故障，call reset_session() 清除）"
                )
                self._last_convert_diagnostics = {
                    "stage": "circuit_breaker_open",
                    "exit_code": None,
                    "stderr_tail": "",
                }
                return False
```

**修改 `convert_sldprt_to_step` 的 except 分支（约第 79-81 行）：**

变更前：
```python
            try:
                success = self._do_convert(sldprt_path, step_out)
            except Exception as e:
                log.warning("convert 未预期异常: %s", e)
                success = False
```

变更后：
```python
            try:
                success = self._do_convert(sldprt_path, step_out)
            except Exception as e:
                log.warning("convert 未预期异常: %s", e)
                self._last_convert_diagnostics = {
                    "stage": "unexpected_exception",
                    "exit_code": None,
                    "stderr_tail": repr(e)[:500],
                }
                success = False
```

- [ ] **Step 4: 运行完整 test_sw_com_session_subprocess.py，确认全绿**

```
uv run pytest tests/test_sw_com_session_subprocess.py -v
```

预期：全部 PASSED（原 5 条 + 新 6 条 = 11 条全绿）

- [ ] **Step 5: 不提交，等 Task 4 完成后一起提交**

---

## Task 4：Stage C 集成（RED → GREEN）

**Files:**
- Modify: `tools/sw_b9_acceptance.py:294-306`（`stage_c_session_restart` 的 convert 循环）
- Create: `tests/test_sw_b9_acceptance.py`（新文件）

- [ ] **Step 1: 创建 `tests/test_sw_b9_acceptance.py`，写 Stage C 集成测试（RED）**

创建新文件，内容：

```python
"""Stage C 可观测性集成测试：验证 per_target 含 diagnostics 字段。"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestStageCDiagnosticsIntegration:
    def _fake_matched_list(self) -> list[dict]:
        """造 8 条 matched 记录（Stage C 最小阈值）。"""
        return [
            {
                "part_no": f"P-{i}",
                "sldprt": rf"C:\fake\{i}.sldprt",
                "score": 0.5,
            }
            for i in range(8)
        ]

    def test_per_target_includes_diagnostics_on_success(self, tmp_path):
        """所有 convert 成功 → per_target 每条含 stage=success, exit_code=0。"""
        from tools import sw_b9_acceptance

        matched = self._fake_matched_list()

        # mock session：所有 convert 返回 True 并写有效 STEP
        def fake_convert(self, sldprt, step_out):
            Path(step_out).parent.mkdir(parents=True, exist_ok=True)
            Path(step_out).write_bytes(b"ISO-10303-214\n" + b"X" * 2000)
            self._last_convert_diagnostics = {
                "stage": "success",
                "exit_code": 0,
                "stderr_tail": "",
            }
            return True

        with mock.patch(
            "adapters.solidworks.sw_com_session.SwComSession.convert_sldprt_to_step",
            fake_convert,
        ):
            result = sw_b9_acceptance.stage_c_session_restart(matched, tmp_path)

        assert result["pass"] is True
        assert result["success_count"] == 8
        for entry in result["per_target"]:
            assert entry["stage"] == "success"
            assert entry["exit_code"] == 0
            assert "stderr_tail" in entry

    def test_per_target_includes_diagnostics_on_subprocess_error(self, tmp_path):
        """某 convert 返回 subprocess_error → per_target 对应条目含 exit_code + stderr。"""
        from tools import sw_b9_acceptance

        matched = self._fake_matched_list()

        def fake_convert(self, sldprt, step_out):
            self._last_convert_diagnostics = {
                "stage": "subprocess_error",
                "exit_code": 3,
                "stderr_tail": "worker: SaveAs3 saved=False errors=1",
            }
            return False

        with mock.patch(
            "adapters.solidworks.sw_com_session.SwComSession.convert_sldprt_to_step",
            fake_convert,
        ):
            result = sw_b9_acceptance.stage_c_session_restart(matched, tmp_path)

        assert result["pass"] is False
        for entry in result["per_target"]:
            assert entry.get("failed") is True
            assert entry["stage"] == "subprocess_error"
            assert entry["exit_code"] == 3
            assert "errors=1" in entry["stderr_tail"]
```

- [ ] **Step 2: 运行新测试，确认失败（RED）**

```
uv run pytest tests/test_sw_b9_acceptance.py -v
```

预期：2 条全 FAILED（`per_target` 还未合并 diag 字段）

- [ ] **Step 3: 修改 `stage_c_session_restart` 合并 diag 进 per_target**

修改 `tools/sw_b9_acceptance.py` 的 `stage_c_session_restart`（约第 294-306 行）：

变更前：
```python
    session = get_session()
    success = 0
    per_target: list[dict[str, Any]] = []
    for i, t in enumerate(targets):
        sldprt = t["sldprt"]
        step_path = step_dir / f"{i:02d}_{Path(sldprt).stem}.step"
        ok = session.convert_sldprt_to_step(sldprt, str(step_path))
        if ok and step_path.exists() and step_path.stat().st_size > 1024:
            success += 1
            per_target.append({"index": i, "sldprt": sldprt, "step_size": step_path.stat().st_size})
        else:
            per_target.append({"index": i, "sldprt": sldprt, "step_size": 0, "failed": True})
```

变更后：
```python
    session = get_session()
    success = 0
    per_target: list[dict[str, Any]] = []
    for i, t in enumerate(targets):
        sldprt = t["sldprt"]
        step_path = step_dir / f"{i:02d}_{Path(sldprt).stem}.step"
        ok = session.convert_sldprt_to_step(sldprt, str(step_path))
        diag = session.last_convert_diagnostics or {}
        step_size = step_path.stat().st_size if step_path.exists() else 0
        entry: dict[str, Any] = {"index": i, "sldprt": sldprt, "step_size": step_size}
        if ok and step_size > 1024:
            success += 1
        else:
            entry["failed"] = True
        entry.update(diag)
        per_target.append(entry)
```

- [ ] **Step 4: 运行新测试，确认通过（GREEN）**

```
uv run pytest tests/test_sw_b9_acceptance.py -v
```

预期：2 条全部 PASSED

- [ ] **Step 5: 运行完整测试套件，确认无退化**

```
uv run pytest tests/test_sw_com_session_subprocess.py tests/test_sw_b9_acceptance.py -v
```

预期：全绿（11 + 2 = 13 条）

- [ ] **Step 6: ruff 检查**

```
uv run ruff check . && uv run ruff format --check .
```

预期：零告警（Task 3 的必要 `subprocess` 导入已经在 subprocess_error 测试里存在，无新依赖）

- [ ] **Step 7: 提交 Task 1-4 全部改动**

```bash
git add adapters/solidworks/sw_com_session.py \
        tests/test_sw_com_session_subprocess.py \
        tools/sw_b9_acceptance.py \
        tests/test_sw_b9_acceptance.py
git commit -m "feat(sw-b9): Stage C 可观测性 — capture worker stderr/exit_code 进 per_target

SwComSession 加 last_convert_diagnostics 属性记录 6 种 stage（success/
subprocess_error/timeout/validation_failure/circuit_breaker_open/
unexpected_exception），stage_c_session_restart 合并进 per_target。

下次 Stage C 失败可以直接从 stage_c.json 回溯 exit_code 和 stderr，
无需再实时手跑 worker 取证。

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## 验收清单

- [ ] `uv run pytest tests/test_sw_com_session_subprocess.py -v` 全绿（11 条）
- [ ] `uv run pytest tests/test_sw_b9_acceptance.py -v` 全绿（2 条）
- [ ] `uv run pytest -x` 完整套件无退化
- [ ] `uv run ruff check .` 零告警
- [ ] 对真 SW 手跑一次 Stage C（可选验证）：
  ```bash
  python -c "
  from adapters.solidworks.sw_com_session import reset_session
  reset_session()
  import json; from pathlib import Path
  from tools.sw_b9_acceptance import stage_c_session_restart
  stage_a = json.loads(Path('artifacts/sw_b9/stage_a.json').read_text(encoding='utf-8'))
  r = stage_c_session_restart(stage_a['matched_list'], Path('artifacts_temp/diag_probe'))
  print(r['per_target'][0])
  "
  ```
  预期 per_target[0] 含 `stage`/`exit_code`/`stderr_tail` 字段
