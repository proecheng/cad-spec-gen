# SolidWorks Phase SW-B Part 2c P0 — 单次 convert 超时与 subprocess 隔离

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `SwComSession._do_convert` 从"父进程内 Dispatch + threading"改成"每次 convert 启动独立 subprocess，父进程用 `subprocess.run(timeout=...)` 守卫"，根治 SW-B0 真跑第 3 轮发现的 OpenDoc6 无声 hang（pywin32 COM 阻塞无法用 threading.Timer 中断）。

**Architecture:**
- 新 worker 模块 `adapters/solidworks/sw_convert_worker.py`：独立进程入口，内部调用 `Dispatch("SldWorks.Application")` + `OpenDoc6` + `Extension.SaveAs3` + `CloseDoc` + `ExitApp`，把 STEP 写到父进程提供的 tmp 路径。退出码区分失败类型（0 成功；2 OpenDoc6；3 SaveAs3；4 异常；64 用法）。
- `SwComSession._do_convert` 重写：拼 `[sys.executable, "-m", "adapters.solidworks.sw_convert_worker", sldprt, tmp_path]`，`subprocess.run(..., timeout=SINGLE_CONVERT_TIMEOUT_SEC)`；`TimeoutExpired` → subprocess 已被杀 → 返回 False；返回码非 0 → 返回 False；返回码 0 → 父进程 validate tmp（magic + size）+ `os.replace` 原子改名。
- 删除 `_app` 字段、`_start_locked` / `_maybe_restart_locked` / `_maybe_idle_shutdown_locked` / `_shutdown_locked` / `_com_dispatch` / `_convert_count` / `_last_used_ts` 及对应常量（`COLD_START_TIMEOUT_SEC`、`RESTART_EVERY_N_CONVERTS`、`IDLE_SHUTDOWN_SEC`）。SW 生命周期现在属于每个 subprocess 自己。
- 保留：熔断器（连续 3 次失败 → `_unhealthy`；不自愈，依赖 `reset_session()`）、`_lock`（保证 singleton 串行 convert；虽然 COM 在不同进程但父进程的临时文件 / 计数仍需保护）、atomic write 校验（`_validate_step_file`）、`SINGLE_CONVERT_TIMEOUT_SEC` 常量（默认 30s）。

**Tech Stack:** Python 3.11 / pywin32 / subprocess.run / pytest + unittest.mock

**范围外（defer）：**
- P1：exit code 3 区分 lock contention / msvcrt.locking seek / `_find_sldprt` 升 public / material "-" 规范化
- P2：`COLD_START_TIMEOUT_SEC` 下调（不再存在此常量，由 subprocess timeout 吃掉）/ `@requires_solidworks` marker / packaging / sw-inspect 子命令

---

## File Structure

**新建：**
- `adapters/solidworks/sw_convert_worker.py` — 独立进程入口，纯 pywin32 调用，无 session 依赖
- `tests/test_sw_convert_worker.py` — worker 单元测试（mock win32com）
- `tests/test_sw_com_session_subprocess.py` — 父进程侧 subprocess.run 行为测试（mock subprocess）

**修改：**
- `adapters/solidworks/sw_com_session.py` — 重写 `_do_convert` + 删除生命周期方法/常量/字段
- `tests/test_sw_com_session.py` — 调整 mock 方式，从"mock `_app.OpenDoc6`"改成"mock `subprocess.run`"
- `tests/test_sw_com_session_lifecycle.py` — 绝大多数测试对应已删除的方法，**整文件删除**

**不变：**
- `sw_toolbox_adapter.py` — 仍调 `session.convert_sldprt_to_step()` 公共 API，签名不变
- `tools/sw_warmup.py` — warmup 编排层不受影响
- `_validate_step_file` 与 atomic rename 逻辑 — 父进程保留

---

## Task 0: 环境确认 + 基线跑通

**Files:** 无（只读）

- [ ] **Step 1: 确认当前分支干净 + 在项目根目录**

Run: `git status` then `pwd`
Expected: 无 modified 文件；pwd 为 `D:\Work\cad-spec-gen` 或 worktree 根。

- [ ] **Step 2: 跑基线 SW 测试套件，确认起点全绿**

Run: `uv run pytest tests/test_sw_com_session.py tests/test_sw_com_session_lifecycle.py tests/test_sw_toolbox_adapter.py tests/test_sw_toolbox_catalog.py tests/test_sw_toolbox_integration.py -v`
Expected: 所有 SW 相关测试 PASS（基线 149 个）。若有 fail 先 stop，本计划假设 Part 2b 基线全绿。

- [ ] **Step 3: 用 `python -c` 验证 `sys.executable` + 项目根路径计算**

Run:
```bash
uv run python -c "import sys; from pathlib import Path; print('exe=', sys.executable); print('root=', Path('adapters/solidworks/sw_com_session.py').resolve().parents[2])"
```
Expected: `exe=` 打印 `.venv` 中的 python.exe；`root=` 打印 `D:\Work\cad-spec-gen`。这两个是下面 subprocess 调用要用的值，先自证。

---

## Task 1: 新建 `sw_convert_worker.py` worker 入口（TDD）

**Files:**
- Create: `adapters/solidworks/sw_convert_worker.py`
- Test: `tests/test_sw_convert_worker.py`

**设计约束：**
- Worker 不得引用 `SwComSession` / `sw_com_session` 模块（进程间无共享状态）
- 所有 COM 调用用 `VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)` 包 OUT 参数（SW-B0 spike 实证，直接 `0, 0` 会 DISP_E_TYPEMISMATCH）
- Worker **不**做文件 validate，也**不**做 atomic rename；只负责把 STEP 写到 `tmp_out` 参数指向的路径
- 退出码契约：`0` 成功；`2` OpenDoc6 errors/null model；`3` SaveAs3 saved==False 或 errors≠0；`4` 任何未捕获 Exception；`64` 命令行参数错误

- [ ] **Step 1: 写失败测试 — worker main() 参数个数错时退出码 64**

Create `tests/test_sw_convert_worker.py`:
```python
"""adapters/solidworks/sw_convert_worker.py 的单元测试。

全部 mock win32com/pythoncom，不依赖真实 SW。
"""

from __future__ import annotations

import os
import sys
import unittest.mock as mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestWorkerUsage:
    def test_main_missing_args_returns_64(self, capsys):
        from adapters.solidworks import sw_convert_worker

        rc = sw_convert_worker.main([])
        assert rc == 64
        captured = capsys.readouterr()
        assert "usage" in captured.err.lower()

    def test_main_one_arg_returns_64(self, capsys):
        from adapters.solidworks import sw_convert_worker

        rc = sw_convert_worker.main(["only_one"])
        assert rc == 64
```

- [ ] **Step 2: 跑失败测试确认 RED**

Run: `uv run pytest tests/test_sw_convert_worker.py::TestWorkerUsage -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'adapters.solidworks.sw_convert_worker'`

- [ ] **Step 3: 写最小 worker 骨架让 usage 测试通过**

Create `adapters/solidworks/sw_convert_worker.py`:
```python
"""
adapters/solidworks/sw_convert_worker.py — 独立进程内做单次 sldprt→STEP 转换。

为什么独立进程：pywin32 的 COM Dispatch 调用（OpenDoc6 / SaveAs3）一旦
进入阻塞（SW-B0 spike 实证，330 个文件中会有 hang 20+ 分钟的坏 part），
threading.Timer / signal 均无法打断——唯一可靠手段是由父进程 kill 子进程。
父进程 `subprocess.run(timeout=...)` 是这个打断机制。

Worker 职责：
- Dispatch → OpenDoc6 → Extension.SaveAs3(tmp_out) → CloseDoc → ExitApp
- 把 STEP 写到 argv[2]（tmp 路径，父进程提供，含 `.tmp.step` 扩展名）
- 不做大小/magic 校验（父进程 validate），不做 atomic rename（父进程 os.replace）

退出码契约：
    0  成功
    2  OpenDoc6 errors 非 0 或返回 null model
    3  SaveAs3 saved=False 或 errors 非 0
    4  任何未预期 Exception（COM 崩溃、pywin32 import 失败等）
    64 命令行参数错误

CLI:
    python -m adapters.solidworks.sw_convert_worker <sldprt_path> <tmp_out_path>
"""

from __future__ import annotations

import sys


def _convert(sldprt_path: str, tmp_out_path: str) -> int:
    """实际 COM 转换；返回上面契约中的 exit code。"""
    try:
        import pythoncom
        from win32com.client import VARIANT, Dispatch
    except ImportError as e:
        print(f"worker: pywin32 import failed: {e!r}", file=sys.stderr)
        return 4

    pythoncom.CoInitialize()
    try:
        try:
            app = Dispatch("SldWorks.Application")
        except Exception as e:
            print(f"worker: Dispatch failed: {e!r}", file=sys.stderr)
            return 4

        try:
            app.Visible = False
            app.UserControl = False

            err_var = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            warn_var = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            model = app.OpenDoc6(sldprt_path, 1, 1, "", err_var, warn_var)
            if err_var.value or model is None:
                print(
                    f"worker: OpenDoc6 errors={err_var.value} "
                    f"warnings={warn_var.value} model={'NULL' if model is None else 'OK'}",
                    file=sys.stderr,
                )
                return 2

            try:
                disp_none_a = VARIANT(pythoncom.VT_DISPATCH, None)
                disp_none_b = VARIANT(pythoncom.VT_DISPATCH, None)
                err2 = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                warn2 = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                saved = model.Extension.SaveAs3(
                    tmp_out_path,
                    0,
                    1,
                    disp_none_a,
                    disp_none_b,
                    err2,
                    warn2,
                )
                if not saved or err2.value:
                    print(
                        f"worker: SaveAs3 saved={saved} errors={err2.value}",
                        file=sys.stderr,
                    )
                    return 3
                return 0
            finally:
                try:
                    app.CloseDoc(model.GetTitle())
                except Exception as e:
                    print(f"worker: CloseDoc ignored: {e!r}", file=sys.stderr)
        finally:
            try:
                app.ExitApp()
            except Exception as e:
                print(f"worker: ExitApp ignored: {e!r}", file=sys.stderr)
    except Exception as e:
        print(f"worker: unexpected exception: {e!r}", file=sys.stderr)
        return 4
    finally:
        pythoncom.CoUninitialize()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print(
            "usage: python -m adapters.solidworks.sw_convert_worker "
            "<sldprt_path> <tmp_out_path>",
            file=sys.stderr,
        )
        return 64
    return _convert(argv[0], argv[1])


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 跑 usage 测试确认 GREEN**

Run: `uv run pytest tests/test_sw_convert_worker.py::TestWorkerUsage -v`
Expected: 2 PASSED。

- [ ] **Step 5: 加失败测试 — OpenDoc6 errors 非 0 → 退出码 2**

Append to `tests/test_sw_convert_worker.py`:
```python
class TestWorkerConvert:
    """_convert 的退出码契约；全部 mock pythoncom + Dispatch。"""

    def _patch_com(self, monkeypatch, *, dispatch_return=None, dispatch_raises=None):
        """安装 pythoncom + win32com.client 的 fake 模块。返回 fake_app 给测试控制 side effects。"""
        fake_pythoncom = mock.MagicMock()
        fake_pythoncom.VT_BYREF = 0x4000
        fake_pythoncom.VT_I4 = 3
        fake_pythoncom.VT_DISPATCH = 9

        fake_win32com_client = mock.MagicMock()

        if dispatch_raises is not None:
            fake_win32com_client.Dispatch.side_effect = dispatch_raises
        else:
            fake_app = dispatch_return or mock.MagicMock()
            fake_win32com_client.Dispatch.return_value = fake_app

        # VARIANT 的 mock：每次构造返回一个有 .value 属性的对象，初值为传入的 initial
        def fake_variant(vartype, initial):
            v = mock.MagicMock()
            v.value = initial
            return v

        fake_win32com_client.VARIANT.side_effect = fake_variant

        monkeypatch.setitem(sys.modules, "pythoncom", fake_pythoncom)
        monkeypatch.setitem(sys.modules, "win32com.client", fake_win32com_client)
        return fake_win32com_client.Dispatch.return_value if dispatch_raises is None else None

    def test_opendoc6_errors_returns_2(self, monkeypatch, capsys):
        """OpenDoc6 调用后 err_var.value 非 0 → exit 2。"""
        from adapters.solidworks import sw_convert_worker

        fake_app = mock.MagicMock()
        self._patch_com(monkeypatch, dispatch_return=fake_app)

        def opendoc_sets_error(sldprt, doctype, opts, cfg, err_v, warn_v):
            err_v.value = 256  # swFileLoadError
            return mock.MagicMock()  # non-None model

        fake_app.OpenDoc6.side_effect = opendoc_sets_error

        rc = sw_convert_worker._convert("in.sldprt", "out.tmp.step")
        assert rc == 2
        assert "OpenDoc6 errors=256" in capsys.readouterr().err
```

- [ ] **Step 6: 跑新测试确认 PASS（实现已支持此路径）**

Run: `uv run pytest tests/test_sw_convert_worker.py::TestWorkerConvert::test_opendoc6_errors_returns_2 -v`
Expected: PASS。

- [ ] **Step 7: 加 SaveAs3 失败路径测试**

Append inside `TestWorkerConvert`:
```python
    def test_saveas3_saved_false_returns_3(self, monkeypatch, capsys):
        from adapters.solidworks import sw_convert_worker

        fake_app = mock.MagicMock()
        self._patch_com(monkeypatch, dispatch_return=fake_app)

        model = mock.MagicMock()
        fake_app.OpenDoc6.return_value = model  # err_v.value 保持 0 → OpenDoc6 通过
        model.Extension.SaveAs3.return_value = False  # saved=False

        rc = sw_convert_worker._convert("in.sldprt", "out.tmp.step")
        assert rc == 3
        assert "SaveAs3 saved=False" in capsys.readouterr().err

    def test_saveas3_success_returns_0(self, monkeypatch):
        from adapters.solidworks import sw_convert_worker

        fake_app = mock.MagicMock()
        self._patch_com(monkeypatch, dispatch_return=fake_app)

        model = mock.MagicMock()
        fake_app.OpenDoc6.return_value = model
        model.Extension.SaveAs3.return_value = True  # saved=True，err2 默认 0

        rc = sw_convert_worker._convert("in.sldprt", "out.tmp.step")
        assert rc == 0
        fake_app.ExitApp.assert_called_once()

    def test_dispatch_exception_returns_4(self, monkeypatch, capsys):
        from adapters.solidworks import sw_convert_worker

        self._patch_com(monkeypatch, dispatch_raises=RuntimeError("COM unavailable"))

        rc = sw_convert_worker._convert("in.sldprt", "out.tmp.step")
        assert rc == 4
        assert "Dispatch failed" in capsys.readouterr().err
```

- [ ] **Step 8: 跑 worker 全套测试确认 GREEN**

Run: `uv run pytest tests/test_sw_convert_worker.py -v`
Expected: 6 PASSED（2 usage + 4 convert）。

- [ ] **Step 9: ruff 检查**

Run: `uv run ruff check adapters/solidworks/sw_convert_worker.py tests/test_sw_convert_worker.py && uv run ruff format --check adapters/solidworks/sw_convert_worker.py tests/test_sw_convert_worker.py`
Expected: `All checks passed!` + `would format 0 files`。若 format 有差异，先 `ruff format` 再重跑 check。

- [ ] **Step 10: Commit**

```bash
git add adapters/solidworks/sw_convert_worker.py tests/test_sw_convert_worker.py
git commit -m "$(cat <<'EOF'
feat(sw-b): sw_convert_worker 独立 subprocess 入口（Part 2c P0 Task 1）

SW-B0 spike 实证 pywin32 COM 调用（OpenDoc6/SaveAs3）一旦进入阻塞，
threading.Timer/signal 都无法中断——唯一手段是由父进程 kill 子进程。
本任务交付 worker 侧：独立进程内完成 Dispatch + OpenDoc6 + SaveAs3 +
CloseDoc + ExitApp，退出码 0/2/3/4/64 区分成功/OpenDoc6/SaveAs3/异常/用法。

Task 2 把 SwComSession._do_convert 改成 subprocess.run 调用本 worker。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: 重写 `SwComSession._do_convert` 为 subprocess.run + timeout（TDD）

**Files:**
- Modify: `adapters/solidworks/sw_com_session.py`
- Create: `tests/test_sw_com_session_subprocess.py`

**设计约束：**
- 父进程用 `subprocess.run(cmd, timeout=SINGLE_CONVERT_TIMEOUT_SEC, capture_output=True, text=True, encoding="utf-8", errors="replace")`
- `TimeoutExpired` 异常被 subprocess.run 内部捕获后会先 `kill` 子进程 + 等退出，然后才 raise；父进程无需再手动 kill
- 子进程 `cwd` 必须设成项目根（计算方式 `Path(__file__).resolve().parents[2]`），否则 `-m adapters.solidworks.sw_convert_worker` 找不到模块
- 子进程 `env` 继承父进程（保证 `.venv` / PYTHONPATH 一致）
- 子进程 cmd 用 `sys.executable`，不用 `"python"` 字符串（避免 PATH 里的老版本）
- 成功路径：subprocess rc=0 → 父进程 `_validate_step_file(tmp_path)` → `os.replace(tmp, final)` → 返回 True
- 任何失败路径（timeout / rc≠0 / validate 失败）：返回 False；上层 `convert_sldprt_to_step` 累加 `_consecutive_failures`

- [ ] **Step 1: 写失败测试 — subprocess 返回 0 + 合法 STEP → True，且父进程 os.replace 到最终路径**

Create `tests/test_sw_com_session_subprocess.py`:
```python
"""SwComSession._do_convert 的 subprocess 守卫行为测试（Part 2c P0 Task 2）。

全部 mock subprocess.run 以快速验证父进程侧逻辑；真实 subprocess 启动
测试在 Task 4 的 slow 标记集成用例里单独覆盖。
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest.mock as mock
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestDoConvertSubprocess:
    def _fake_run_success(self, tmp_out_content: bytes):
        """返回一个 side_effect：模拟 worker 写好 tmp 文件并 rc=0。"""

        def _run(cmd, **kwargs):
            # cmd 形如 [sys.executable, "-m", "adapters...sw_convert_worker", sldprt, tmp]
            tmp_path = cmd[-1]
            Path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
            Path(tmp_path).write_bytes(tmp_out_content)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        return _run

    def test_subprocess_success_validates_and_renames(self, tmp_path, monkeypatch):
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()
        step_out = tmp_path / "out.step"

        valid_step = b"ISO-10303-214\n" + b"X" * 2000
        monkeypatch.setattr(
            subprocess, "run", self._fake_run_success(valid_step)
        )

        ok = s.convert_sldprt_to_step(
            str(tmp_path / "hex bolt.sldprt"),
            str(step_out),
        )
        assert ok is True
        assert step_out.exists()
        assert step_out.read_bytes().startswith(b"ISO-10303")
        # tmp 应被 os.replace 消费
        assert not (tmp_path / "out.tmp.step").exists()

    def test_subprocess_nonzero_rc_returns_false(self, tmp_path, monkeypatch):
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                cmd, 2, stdout="", stderr="worker: OpenDoc6 errors=256"
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        step_out = tmp_path / "out.step"
        ok = s.convert_sldprt_to_step(
            str(tmp_path / "broken.sldprt"), str(step_out)
        )
        assert ok is False
        assert not step_out.exists()
        assert s._consecutive_failures == 1

    def test_subprocess_timeout_returns_false(self, tmp_path, monkeypatch):
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()

        def fake_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=30)

        monkeypatch.setattr(subprocess, "run", fake_run)

        step_out = tmp_path / "out.step"
        ok = s.convert_sldprt_to_step(
            str(tmp_path / "hangs.sldprt"), str(step_out)
        )
        assert ok is False
        assert not step_out.exists()
        assert s._consecutive_failures == 1

    def test_subprocess_success_but_invalid_step_returns_false(
        self, tmp_path, monkeypatch
    ):
        """worker rc=0 但写出的 tmp 文件过小/magic 错 → 父进程 validate 拒收。"""
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()

        # rc=0 但 tmp 只有 "tiny" — _validate_step_file 应拒。
        monkeypatch.setattr(subprocess, "run", self._fake_run_success(b"tiny"))

        step_out = tmp_path / "out.step"
        ok = s.convert_sldprt_to_step(
            str(tmp_path / "fake.sldprt"), str(step_out)
        )
        assert ok is False
        assert not step_out.exists()
        # tmp 应被清理
        assert not (tmp_path / "out.tmp.step").exists()

    def test_subprocess_called_with_expected_cmd(self, tmp_path, monkeypatch):
        """验证命令行拼装：sys.executable + -m + 模块路径 + 两个位置参数；cwd 为项目根。"""
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()

        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            # 模拟写合法 tmp
            Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(cmd[-1]).write_bytes(b"ISO-10303-214\n" + b"X" * 2000)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)

        sldprt = tmp_path / "hex bolt.sldprt"
        step_out = tmp_path / "out.step"
        s.convert_sldprt_to_step(str(sldprt), str(step_out))

        assert captured["cmd"][0] == sys.executable
        assert captured["cmd"][1] == "-m"
        assert captured["cmd"][2] == "adapters.solidworks.sw_convert_worker"
        assert captured["cmd"][3] == str(sldprt)
        assert captured["cmd"][4].endswith(".tmp.step")
        assert captured["kwargs"]["timeout"] > 0
        assert captured["kwargs"]["capture_output"] is True
        # cwd 应指向 cad-spec-gen 根（包含 adapters/ 目录）
        cwd = Path(captured["kwargs"]["cwd"])
        assert (cwd / "adapters" / "solidworks").is_dir()
```

- [ ] **Step 2: 跑失败测试确认 RED**

Run: `uv run pytest tests/test_sw_com_session_subprocess.py -v`
Expected: 全部 FAIL（当前 `_do_convert` 仍是直接 COM 调用，不吃 `subprocess.run` mock）。

- [ ] **Step 3: 改写 `sw_com_session.py` 使测试 GREEN**

Replace `adapters/solidworks/sw_com_session.py` 的顶部 docstring 和 `_do_convert` / `convert_sldprt_to_step`。其他生命周期方法**留到 Task 3 删**，本步只聚焦 _do_convert。

具体改动：

**(a) 顶部新 docstring + import + 项目根常量**

把文件开头（到第一个常量定义前）替换为：
```python
"""
adapters/solidworks/sw_com_session.py — SolidWorks COM 会话管理（Part 2c P0 重写）。

设计：每次 convert 启动独立 subprocess 跑 `sw_convert_worker`，父进程用
`subprocess.run(timeout=SINGLE_CONVERT_TIMEOUT_SEC)` 守护；timeout 触发
时 subprocess.run 内部会先 kill 再 raise，父进程把失败计入熔断器。

为什么 subprocess：pywin32 COM 调用阻塞后 threading 无法中断（SW-B0 spike
第 3 轮真跑实证）；只有杀子进程是可靠手段。

Session 公共 API 不变：`convert_sldprt_to_step(sldprt, step_out) -> bool` +
`is_healthy()` + `shutdown()` + `get_session()/reset_session()`。

父进程职责：subprocess 编排 + timeout 守护 + STEP validate + atomic rename +
熔断器。Worker 职责（另一个模块）：Dispatch + OpenDoc6 + SaveAs3 + 写 tmp。
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_WORKER_MODULE = "adapters.solidworks.sw_convert_worker"

SINGLE_CONVERT_TIMEOUT_SEC = 30
CIRCUIT_BREAKER_THRESHOLD = 3

MIN_STEP_FILE_SIZE = 1024
STEP_MAGIC_PREFIX = b"ISO-10303"
```

（删除原先的 `COLD_START_TIMEOUT_SEC` / `IDLE_SHUTDOWN_SEC` / `RESTART_EVERY_N_CONVERTS` / `_com_dispatch` 常量和函数。Task 3 会统一处理遗留测试，本步只改 session 模块本身。）

**(b) `SwComSession.__init__` 精简 + 删除生命周期字段**

替换 `SwComSession.__init__`：
```python
    def __init__(self) -> None:
        self._consecutive_failures = 0
        self._unhealthy = False
        self._lock = threading.Lock()
```

**(c) `is_healthy` 保持；删除 `_start_locked` / `_maybe_restart_locked` / `_maybe_idle_shutdown_locked` / `_shutdown_locked`**

本步把这四个方法整体删除，连同它们的 docstring。`shutdown()` 改成 no-op（保留 API）：
```python
    def shutdown(self) -> None:
        """保留 API 兼容；subprocess 模型下父进程无持久 COM 状态要释放。"""
        return
```

**(d) `convert_sldprt_to_step` 重写**

替换方法体：
```python
    def convert_sldprt_to_step(self, sldprt_path, step_out) -> bool:
        sldprt_path = str(os.fspath(sldprt_path))
        step_out = str(os.fspath(step_out))

        with self._lock:
            if self._unhealthy:
                log.info(
                    "熔断器已开：跳过 convert（系统性故障，call reset_session() 清除）"
                )
                return False

            success = False
            try:
                success = self._do_convert(sldprt_path, step_out)
            except Exception as e:
                log.warning("convert 未预期异常: %s", e)
                success = False

            if success:
                self._consecutive_failures = 0
            else:
                self._consecutive_failures += 1
                if self._consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
                    log.error(
                        "COM 熔断触发（连续 %d 次失败）",
                        self._consecutive_failures,
                    )
                    self._unhealthy = True
            return success
```

**(e) `_do_convert` 重写**

替换方法体：
```python
    def _do_convert(self, sldprt_path: str, step_out: str) -> bool:
        """启动 worker subprocess，成功则 validate + atomic rename。"""
        # tmp 必须以 .step 结尾（SaveAs3 按扩展名推断格式；.step.tmp 会被 SW
        # 拒为 swFileSaveAsNotSupported=256，SW-B0 spike H3 实证）
        tmp_path = str(Path(step_out).with_suffix(".tmp.step"))
        Path(step_out).parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            sys.executable,
            "-m",
            _WORKER_MODULE,
            sldprt_path,
            tmp_path,
        ]

        try:
            proc = subprocess.run(
                cmd,
                timeout=SINGLE_CONVERT_TIMEOUT_SEC,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(_PROJECT_ROOT),
            )
        except subprocess.TimeoutExpired:
            log.warning(
                "convert subprocess 超时 %ds，已被 subprocess.run kill；sldprt=%s",
                SINGLE_CONVERT_TIMEOUT_SEC,
                sldprt_path,
            )
            self._cleanup_tmp(tmp_path)
            return False

        if proc.returncode != 0:
            log.warning(
                "convert subprocess rc=%d sldprt=%s stderr=%s",
                proc.returncode,
                sldprt_path,
                (proc.stderr or "")[:300],
            )
            self._cleanup_tmp(tmp_path)
            return False

        if not self._validate_step_file(tmp_path):
            log.warning("convert tmp STEP 校验失败: %s", tmp_path)
            self._cleanup_tmp(tmp_path)
            return False

        os.replace(tmp_path, step_out)
        return True

    @staticmethod
    def _cleanup_tmp(tmp_path: str) -> None:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except OSError:
            pass
```

（保持 `_validate_step_file` 不变；保持 `get_session` / `reset_session` / 末尾 singleton 块不变。`reset_session` 仍调 `shutdown()`，但后者现在是 no-op，OK。）

- [ ] **Step 4: 跑 Task 2 新测试确认 GREEN**

Run: `uv run pytest tests/test_sw_com_session_subprocess.py -v`
Expected: 5 PASSED。

- [ ] **Step 5: 跑 worker 测试确认 Task 1 仍 GREEN（回归）**

Run: `uv run pytest tests/test_sw_convert_worker.py -v`
Expected: 6 PASSED。

- [ ] **Step 6: 老测试 test_sw_com_session.py / test_sw_com_session_lifecycle.py 会红，先跑一下确认基线**

Run: `uv run pytest tests/test_sw_com_session.py tests/test_sw_com_session_lifecycle.py -v`
Expected: 多个 FAIL（它们 mock `_app.OpenDoc6`，但新实现不走 in-process COM）。**不要现在修**——Task 3 会统一处理。记录下 fail 数量以便 Task 3 对比。

- [ ] **Step 7: ruff 检查 + format**

Run: `uv run ruff check adapters/solidworks/sw_com_session.py tests/test_sw_com_session_subprocess.py && uv run ruff format --check adapters/solidworks/sw_com_session.py tests/test_sw_com_session_subprocess.py`
Expected: 全 pass。

- [ ] **Step 8: Commit（此时 test_sw_com_session.py 仍红，暂存跳过）**

```bash
git add adapters/solidworks/sw_com_session.py tests/test_sw_com_session_subprocess.py
git commit -m "$(cat <<'EOF'
feat(sw-b): SwComSession._do_convert 改 subprocess 守护（Part 2c P0 Task 2）

父进程用 subprocess.run(timeout=SINGLE_CONVERT_TIMEOUT_SEC=30) 调 worker
模块做单次 convert；timeout 触发时 subprocess.run 内部 kill 子进程，父
进程把失败计入熔断器。成功路径：worker rc=0 → _validate_step_file →
os.replace tmp 到最终路径（atomic write 保持）。

旧 test_sw_com_session.py / test_sw_com_session_lifecycle.py 大量依赖
in-process COM mock，暂未通过；Task 3 统一删除死代码测试。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 删除死代码（`_start_locked` / `_maybe_restart_locked` / `_maybe_idle_shutdown_locked` 等）+ 清理老测试

**Files:**
- Modify: `adapters/solidworks/sw_com_session.py` — 已在 Task 2 删除，本步是 sanity check
- Modify: `tests/test_sw_com_session.py` — 调整 fixture，删依赖 `_app` 的用例
- Delete: `tests/test_sw_com_session_lifecycle.py` — 整个文件测的是已删除方法

**约束：**
- `test_sw_com_session_lifecycle.py` 里 18 个测试全部对应已删除的方法（`_start_locked` / `_maybe_restart_locked` / idle shutdown / convert auto-start），无保留价值，**直接删文件**
- `test_sw_com_session.py` 里 `TestSwComSessionBasics` / `TestSessionSingleton` 与 `_app` 无关，保留
- `test_sw_com_session.py` 里 `TestConvertSldprtToStep` 全部 mock `_app.OpenDoc6`——在 subprocess 模型下无意义；对应覆盖已经由 `tests/test_sw_com_session_subprocess.py` 承担；**删除整个 TestConvertSldprtToStep 类**

- [ ] **Step 1: sanity — 确认 sw_com_session.py 里已没有死代码残余**

Run:
```bash
uv run python -c "from adapters.solidworks import sw_com_session as m; names = [n for n in dir(m) if not n.startswith('__')]; print('\n'.join(sorted(names)))"
```
Expected: 输出里**不应**出现 `COLD_START_TIMEOUT_SEC` / `RESTART_EVERY_N_CONVERTS` / `IDLE_SHUTDOWN_SEC` / `_com_dispatch`；`SwComSession` 类应无 `_start_locked` / `_maybe_restart_locked` / `_maybe_idle_shutdown_locked` / `_shutdown_locked` 方法。若发现残余，回到 Task 2 Step 3 补删。

- [ ] **Step 2: 删除 `tests/test_sw_com_session_lifecycle.py` 整个文件**

Run:
```bash
git rm tests/test_sw_com_session_lifecycle.py
```

- [ ] **Step 3: 删除 `tests/test_sw_com_session.py` 里 `TestConvertSldprtToStep` 整个类**

Edit `tests/test_sw_com_session.py`：
- 保留 `TestSwComSessionBasics`（3 个测试）
- 保留 `TestSessionSingleton`（2 个测试）
- **删除** `TestConvertSldprtToStep` 类（从 `class TestConvertSldprtToStep` 开始到文件结束的 5 个测试方法）
- 删除顶部不再用到的 imports：`import pytest`, `from pathlib import Path`, 以及 `from adapters.solidworks.sw_com_session import (SwComSession, get_session, reset_session,)` 里的 `SwComSession` 改为只 import `get_session, reset_session`（Basics 里用 `SwComSession()` 构造？检查一下——是的有用到，保留）

操作后 `test_sw_com_session.py` 应从 ~209 行缩减到 ~68 行，内容大致：
```python
"""sw_com_session 单元测试（Part 2c 精简版）。

subprocess 守卫行为的覆盖已转移到 tests/test_sw_com_session_subprocess.py。
本文件只保留与 subprocess 模型无关的基础 invariant：健康初态、
singleton 语义、reset_session 清空状态。
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from adapters.solidworks.sw_com_session import (
    SwComSession,
    get_session,
    reset_session,
)


class TestSwComSessionBasics:
    def test_new_session_is_healthy(self):
        reset_session()
        s = SwComSession()
        assert s.is_healthy() is True
        assert s._consecutive_failures == 0

    def test_session_has_threading_lock(self):
        s = SwComSession()
        assert hasattr(s, "_lock")
        assert hasattr(s._lock, "acquire")
        assert hasattr(s._lock, "release")

    def test_reset_session_clears_state(self):
        reset_session()
        s = get_session()
        s._consecutive_failures = 2
        s._unhealthy = True
        reset_session()
        s2 = get_session()
        assert s2._consecutive_failures == 0
        assert s2._unhealthy is False


class TestSessionSingleton:
    def test_get_session_returns_singleton(self):
        reset_session()
        s1 = get_session()
        s2 = get_session()
        assert s1 is s2

    def test_reset_session_creates_new_instance(self):
        reset_session()
        s1 = get_session()
        reset_session()
        s2 = get_session()
        assert s1 is not s2
```

注意：原 Basics 里 `assert s._convert_count == 0` 删掉（字段已不存在）。

- [ ] **Step 4: 跑 session 相关测试确认全绿**

Run: `uv run pytest tests/test_sw_com_session.py tests/test_sw_com_session_subprocess.py tests/test_sw_convert_worker.py -v`
Expected: 5 + 5 + 6 = 16 PASSED，0 FAILED。

- [ ] **Step 5: 跑 SW 全量回归**

Run: `uv run pytest tests/test_sw_com_session.py tests/test_sw_com_session_subprocess.py tests/test_sw_convert_worker.py tests/test_sw_toolbox_adapter.py tests/test_sw_toolbox_catalog.py tests/test_sw_toolbox_integration.py tests/test_sw_toolbox_adapter_registration.py tests/test_sw_warmup_orchestration.py tests/test_sw_detect.py tests/test_sw_material_bridge.py -v`
Expected: 全部 PASS（合计约 130+ 个 SW 相关测试）。若有 fail，读出 fail 名，判断是否还有 `_app` / `_convert_count` 残留引用，补修。

- [ ] **Step 6: ruff**

Run: `uv run ruff check adapters/solidworks/ tests/test_sw_com_session.py tests/test_sw_com_session_subprocess.py && uv run ruff format --check adapters/solidworks/ tests/test_sw_com_session.py tests/test_sw_com_session_subprocess.py`
Expected: 全 pass。

- [ ] **Step 7: Commit**

```bash
git add tests/test_sw_com_session.py
git rm tests/test_sw_com_session_lifecycle.py 2>/dev/null || true
git add -u
git commit -m "$(cat <<'EOF'
refactor(sw-b): 删除 in-process COM 生命周期遗留代码 + 对应测试（Part 2c P0 Task 3）

subprocess 模型下以下结构全部失效、整体删除：
- SwComSession._app / _convert_count / _last_used_ts 字段
- _start_locked / _maybe_restart_locked / _maybe_idle_shutdown_locked / _shutdown_locked
- _com_dispatch 辅助函数
- COLD_START_TIMEOUT_SEC / RESTART_EVERY_N_CONVERTS / IDLE_SHUTDOWN_SEC 常量
- tests/test_sw_com_session_lifecycle.py（整个文件测已删方法）
- tests/test_sw_com_session.py::TestConvertSldprtToStep（mock in-process OpenDoc6）

保留：circuit breaker / _lock / _validate_step_file / atomic rename /
SINGLE_CONVERT_TIMEOUT_SEC / shutdown() 无操作存根（API 兼容）。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: 真 subprocess 超时集成测试（无 SW 依赖）

**Files:**
- Create: `tests/test_sw_com_session_real_subprocess.py`
- Create: `tests/fixtures/sw_convert_worker_stub_sleep.py` — fake worker 脚本（sleep 60s）

**为什么单独一个任务：**
前面的测试全部 mock `subprocess.run`——证明了父进程的调用拼装和退出码处理正确，但没验证"真的 spawn 了子进程，真的 kill 了它"。本任务用一个 sleep 脚本当替代 worker，用 monkeypatch 改 `_WORKER_MODULE` 指向它，`SINGLE_CONVERT_TIMEOUT_SEC` 改小成 2 秒，观察真 Popen 行为。这是唯一能验证 subprocess 杀进程路径的测试，且无需真实 SW。

- [ ] **Step 1: 创建 sleep fixture 脚本**

Create `tests/fixtures/sw_convert_worker_stub_sleep.py`:
```python
"""测试桩：模拟 worker 进入无限 sleep；父进程应在 timeout 时 kill。

使用方式：python -m tests.fixtures.sw_convert_worker_stub_sleep <sldprt> <tmp>
"""

from __future__ import annotations

import sys
import time


def main() -> int:
    if len(sys.argv) != 3:
        return 64
    time.sleep(120)  # 父进程应在 SINGLE_CONVERT_TIMEOUT_SEC 秒内 kill 我们
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 确保 `tests/fixtures/` 有 `__init__.py`**

Run:
```bash
uv run python -c "from pathlib import Path; p = Path('tests/fixtures/__init__.py'); print('exists' if p.exists() else 'MISSING')"
```

Expected: 输出 `exists`（之前 Part 2b 已建）。若 `MISSING`，则 `touch tests/fixtures/__init__.py` 并 `git add`。

- [ ] **Step 3: 写失败/慢测试**

Create `tests/test_sw_com_session_real_subprocess.py`:
```python
"""真 subprocess.run 集成测试：验证 timeout 触发时子进程被杀、父进程返回 False。

不依赖真实 SolidWorks——用 tests/fixtures/sw_convert_worker_stub_sleep.py
当替代 worker（sleep 120s）。测试把 SINGLE_CONVERT_TIMEOUT_SEC 调成 2s，
期望父进程在 ~2s 内返回 False 且不产出 STEP 文件。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


pytestmark = pytest.mark.slow


def test_subprocess_timeout_actually_kills_child(tmp_path, monkeypatch):
    from adapters.solidworks import sw_com_session
    from adapters.solidworks.sw_com_session import SwComSession, reset_session

    reset_session()

    # 改 worker 指向 sleep stub；改 timeout 到 2s 加速测试
    monkeypatch.setattr(
        sw_com_session,
        "_WORKER_MODULE",
        "tests.fixtures.sw_convert_worker_stub_sleep",
    )
    monkeypatch.setattr(sw_com_session, "SINGLE_CONVERT_TIMEOUT_SEC", 2)

    s = SwComSession()
    step_out = tmp_path / "out.step"
    sldprt = tmp_path / "fake.sldprt"
    sldprt.write_bytes(b"")

    t0 = time.time()
    ok = s.convert_sldprt_to_step(str(sldprt), str(step_out))
    elapsed = time.time() - t0

    assert ok is False
    assert elapsed < 10, f"subprocess 没被及时 kill：耗时 {elapsed:.1f}s"
    assert not step_out.exists()
    # tmp 若被创建也应被 _cleanup_tmp 清
    assert not (tmp_path / "out.tmp.step").exists()
    assert s._consecutive_failures == 1
```

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/test_sw_com_session_real_subprocess.py -v -m slow`
Expected: 1 PASSED，耗时约 2-5 秒。

若耗时 > 10s：说明 `subprocess.run` 在 Windows 上 kill 不够快，或 `_PROJECT_ROOT` 计算错误导致 `-m` 找不到模块、fallback 成 ImportError 立刻退出（那样测试也 pass 但不是本意）。加日志排查 — 在 `_do_convert` 里 stderr 一行 `log.debug("subprocess rc=%s stderr=%s", proc.returncode, proc.stderr[:200])`。

- [ ] **Step 5: ruff**

Run: `uv run ruff check tests/test_sw_com_session_real_subprocess.py tests/fixtures/sw_convert_worker_stub_sleep.py && uv run ruff format --check tests/test_sw_com_session_real_subprocess.py tests/fixtures/sw_convert_worker_stub_sleep.py`
Expected: 全 pass。

- [ ] **Step 6: 确认 pyproject.toml 有 slow marker 注册（如没有则补）**

Run: `uv run python -c "import tomllib; d = tomllib.loads(open('pyproject.toml','rb').read().decode()); print(d.get('tool',{}).get('pytest',{}).get('ini_options',{}).get('markers',[]))"`
Expected: 输出中包含 `"slow: ..."`。若不包含，在 `pyproject.toml` 的 `[tool.pytest.ini_options]` 下 `markers = [...]` 里追加 `"slow: 真 subprocess / 真 IO 集成测试，默认 pytest 不跑"`。

- [ ] **Step 7: Commit**

```bash
git add tests/test_sw_com_session_real_subprocess.py tests/fixtures/sw_convert_worker_stub_sleep.py
# 如 pyproject.toml 有改动
git add pyproject.toml
git commit -m "$(cat <<'EOF'
test(sw-b): 真 subprocess 超时 kill 集成测试（Part 2c P0 Task 4）

用 tests/fixtures/sw_convert_worker_stub_sleep.py 当 worker 替身
（sleep 120s），monkeypatch 把 SINGLE_CONVERT_TIMEOUT_SEC 改成 2s，
验证：
- subprocess.run 真的 spawn 出 python 子进程
- timeout 到期时 subprocess.run 真的 kill 子进程
- 父进程在 ~2s 内返回 False，不产出 STEP，_consecutive_failures 自增

打 @pytest.mark.slow 标记，默认 `uv run pytest` 不跑；需 `-m slow`。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: 真 SolidWorks 手动验收 + memory 更新

**Files:**
- Modify: `C:\Users\procheng\.claude\projects\D--Work-cad-spec-gen\memory\solidworks_asset_extraction.md`
- Modify: `C:\Users\procheng\.claude\projects\D--Work-cad-spec-gen\memory\MEMORY.md`（index 行）

**前置条件：** 本机装有 SolidWorks 2024 + pywin32。这个任务是手动 acceptance，不是自动化测试。

**注意：** 本任务会真实启动 SolidWorks 多次（每个 sldprt 一个 subprocess），全量 GB 标准件约 330 个、预期耗时 60-90 分钟（15s 冷启 × 330 ≈ 82min，视机器）。执行前告知用户时间开销，得到 OK 后再跑。

- [ ] **Step 1: 清理可能的残留 SLDWORKS 进程 + 基线检查**

Run:
```bash
uv run pytest tests/test_sw_com_session.py tests/test_sw_com_session_subprocess.py tests/test_sw_convert_worker.py tests/test_sw_toolbox_integration.py -v
```
Expected: 全绿（Task 3 已验证，这里是本任务的自证基线）。

然后 PowerShell（如有残留卡死的 SW）：`Stop-Process -Name SLDWORKS -Force -ErrorAction SilentlyContinue`

- [ ] **Step 2: 清理老 cache**

Run（PowerShell）:
```powershell
Remove-Item -Recurse -Force "$env:USERPROFILE\.cad-spec-gen\sw-toolbox" -ErrorAction SilentlyContinue
```

这一步是为了跑完整 cold start + warmup 流程，不吃老 STEP cache 命中。

- [ ] **Step 3: 告知用户时间开销 + 等确认**

在这个步骤实施 Agent 应暂停、用文字告诉用户：
> "即将跑 `uv run python cad_pipeline.py sw-warmup --standard GB`，预计 60-90 分钟，期间会看到大量 SLDWORKS.EXE 启动/退出。是否继续？"

等用户回应。若不 continue，跳到 Step 7（只做 smoke 而非全量）。

- [ ] **Step 4（长耗时）: 跑全量 GB warmup**

Run:
```bash
uv run python cad_pipeline.py sw-warmup --standard GB 2>&1 | tee sw-warmup-gb.log
```

Expected: 命令正常结束（非 Ctrl+C），末尾打印形如 `已成功转换 N / 330 个 Toolbox 零件为 STEP，M 个失败或跳过`。N 应远超 SW-B0 spike 的 99（预期 N ≥ 250，即 75%+）。单文件超时数应有限（10 个以内，具体取决于 sldprt 质量）。

若中途进程卡死整体（不是单文件，而是整个 Python）→ subprocess.run 的 timeout 机制有问题，回到 Task 2 排查，**不要** Ctrl+C 后当成功。

- [ ] **Step 5: 分析日志**

Run（grep 日志）:
```bash
grep -c "convert subprocess 超时" sw-warmup-gb.log || true
grep -c "convert subprocess rc=" sw-warmup-gb.log || true
grep -c "熔断" sw-warmup-gb.log || true
grep "已成功转换" sw-warmup-gb.log
```

记录下：超时数 / 非零退出数 / 熔断次数 / 总成功数。这些数会写进 memory。

- [ ] **Step 6: 抽检 3 个成功的 STEP**

Run（PowerShell）:
```powershell
Get-ChildItem "$env:USERPROFILE\.cad-spec-gen\sw-toolbox\cache" -Recurse -Filter *.step | Select-Object -First 3 | ForEach-Object { $head = [System.Text.Encoding]::ASCII.GetString([System.IO.File]::ReadAllBytes($_.FullName)[0..20]); Write-Host "$($_.Name): $head" }
```

Expected: 每个文件头应以 `ISO-10303` 开头。若不是，说明 atomic write validate 有 bug，回查 `_validate_step_file`。

- [ ] **Step 7: Smoke（当 Step 4 被用户拒绝时的回退路径）**

Run:
```bash
uv run python cad_pipeline.py sw-warmup --standard GB --limit 5 --dry-run=False 2>&1 | tee sw-warmup-smoke.log
```

（若 `--limit` / `--dry-run` 参数实际名不同，看 `cad_pipeline.py cmd_sw_warmup` 实际签名校正。）

Expected: 5 个文件里至少 3 个成功。记录结果。

- [ ] **Step 8: 更新 memory**

在 `C:\Users\procheng\.claude\projects\D--Work-cad-spec-gen\memory\solidworks_asset_extraction.md` 的末尾加一段（保留 frontmatter + 原内容）：

```markdown

## Phase SW-B Part 2c P0（2026-04-14 完成）

- 交付：`sw_convert_worker.py` 独立 worker 模块 + `SwComSession._do_convert` 重写为 `subprocess.run(timeout=30)` 守护
- 删除：`_start_locked` / `_maybe_restart_locked` / `_maybe_idle_shutdown_locked` / `_shutdown_locked` / `_com_dispatch` 及对应常量（`COLD_START_TIMEOUT_SEC` 等）、`test_sw_com_session_lifecycle.py` 整个文件、`test_sw_com_session.py::TestConvertSldprtToStep`
- 退出码契约：worker 0 成功 / 2 OpenDoc6 / 3 SaveAs3 / 4 异常 / 64 用法；父进程只区分 0 vs 非 0
- 实测 GB 全量 warmup（2026-04-14）：成功 {N}/330，超时 {T} 次，熔断 {B} 次。耗时约 {X} 分钟。对比 SW-B0 spike 的 99/330 + 卡死，提升 {...}
- **How to apply（下一步）**：Part 2c P1 入口 backlog — exit code 3 区分 lock contention vs 部分失败（sw_warmup.py）/ msvcrt.locking 首次 acquire 前加 `fh.seek(0)` / `_find_sldprt` 升 public / material "-"/"N/A" 规范化
```

（花括号 `{N}` 等由实际数值填）

同时把 `MEMORY.md` 的 `solidworks_asset_extraction.md` 那行索引更新成：
```markdown
- [SolidWorks 集成方案](solidworks_asset_extraction.md) — SW-A + Part 1 + 2a + 2b + SW-B0 spike + Part 2c P0（subprocess 超时守护）完成，真跑 {N}/330；下一步 Part 2c P1 backlog
```

- [ ] **Step 9: 最终 SW 全量回归**

Run: `uv run pytest tests/ -k "sw_" -v` + `uv run pytest tests/test_sw_com_session_real_subprocess.py -v -m slow`
Expected: 所有 SW 相关测试 PASS（包括 slow marker 的 subprocess 真测）。

- [ ] **Step 10: Commit memory 更新（memory 在 user 目录，不是 repo，实际只 commit 代码侧如果有遗漏）**

Memory 文件不在 git 仓库里，Step 8 的修改直接落盘即可。repo 侧若 Task 1-4 之后还有 uncommit 的格式化/小调整，在这里一并 commit：

```bash
git status  # 看有没有遗漏
# 如有：git add ... && git commit -m "chore(sw-b): Part 2c P0 收尾格式化"
```

---

## Self-Review（写完计划后自检）

**1. Spec 覆盖：**
- ✅ subprocess-per-convert 架构（Task 2）
- ✅ worker 模块独立进程（Task 1）
- ✅ subprocess.run timeout 守护（Task 2）
- ✅ 删除死代码（Task 3）
- ✅ 真 subprocess kill 验证（Task 4）
- ✅ 真 SW 手动验收（Task 5）
- ✅ memory 更新 + P1 backlog pointer（Task 5 Step 8）

**2. Placeholder 扫描：** 无 TBD / TODO / "similar to Task N" / "appropriate error handling"。Task 5 的 `{N}` 是实测变量，不是 placeholder（Step 8 明确说明由实测数值填）。

**3. 类型一致性：**
- `_WORKER_MODULE = "adapters.solidworks.sw_convert_worker"` 在 Task 2 Step 3 定义，Task 4 Step 3 monkeypatch 时引用一致
- `SINGLE_CONVERT_TIMEOUT_SEC` 常量在 Task 2 定义 = 30，Task 4 monkeypatch = 2，Task 5 用默认 30
- 退出码 0/2/3/4/64 在 Task 1 docstring + Task 2 测试 `fake_run` + Task 5 Step 5 grep 一致

**4. 跨任务依赖：**
- Task 2 依赖 Task 1 的 worker 模块存在 → Task 2 Step 2 会 RED 直到 Task 1 已 commit（顺序执行 OK）
- Task 3 依赖 Task 2 的 _do_convert 重写 + 常量删除 → OK
- Task 4 依赖 Task 2/3 完成（需 `_WORKER_MODULE` 常量） → OK
- Task 5 依赖全部前 4 → OK

---

**Plan complete and saved to `docs/superpowers/plans/2026-04-14-sw-integration-phase-b-part2c-p0.md`. Two execution options:**

**1. Subagent-Driven（推荐）** — 我给每个 task 派一个新 subagent，两阶段审查（spec → quality）间隔，迭代快
**2. Inline Execution** — 本会话内批量执行，按 checkpoint 暂停确认

**选哪个？**
