# Phase SW-B Part 2a 实施计划 — Session Part 2 + Adapter 接入 + env-check UX

> 历史文档提示（2026-04-28）：当前执行依据已合并到 `docs/PARTS_LIBRARY.md`。
> 本计划保留为当时的执行记录；若本文与 `docs/PARTS_LIBRARY.md` 冲突，以
> `docs/PARTS_LIBRARY.md` 为准。当前命名：adapter key 为 `sw_toolbox`，
> 配置段为 `solidworks_toolbox`，类名为 `SwToolboxAdapter`。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal：** 让 SW Toolbox 集成端到端跑通单零件路径——BOM 行进入 parts_resolver → 命中 SwToolboxAdapter → SwComSession 启动真实 SW + 激活 Toolbox Add-In → 转换 sldprt → STEP 落缓存。

**架构：** 在 Part 1 已完成的骨架上补齐 SwComSession 生命周期方法（`start/_maybe_restart/idle_shutdown/threading model`），把 SwToolboxAdapter 注册进 `default_resolver` 并在 `parts_library.default.yaml` 加 GB 高优先级 + ISO/DIN 兜底规则，最后让 `env-check` 给出 `toolbox_addin_enabled=False` 的 UX 指引（决策 #13）。所有实现走 TDD；真实 COM 相关验收推迟到 Part 2c 的 `@requires_solidworks` 测试。

**Tech Stack：** Python 3.11+ / pytest / pywin32 (win32com.client Dispatch — runtime optional) / 现有 parts_resolver YAML 注册机制。

---

## File Structure

**Modify:**

- `adapters/solidworks/sw_com_session.py` — 补齐 `start()` / `_maybe_restart()` / idle shutdown hook；`convert_sldprt_to_step` 加 "`_app is None` 时自动 start" 分支
- `adapters/parts/sw_toolbox_adapter.py` — 无实质修改（Part 1 已完成）；如需可补充 config 来自 yaml 的字段访问
- `parts_resolver.py` — `default_resolver()` 里注册 `SwToolboxAdapter`（在 bd_warehouse 之后、jinja_primitive 之前）
- `parts_library.default.yaml` — 新增 `solidworks_toolbox` 配置段 + GB 高优先级 + ISO/DIN 兜底 mappings
- `tools/hybrid_render/check_env.py` — `toolbox_addin_enabled` 字段纳入增强源输出；`False` 时打印 Tools→Add-ins 勾选指引

**Create:**

- `tests/test_sw_com_session_lifecycle.py` — Session Part 2 生命周期测试（start / restart / idle shutdown）
- `tests/test_sw_toolbox_adapter_registration.py` — default_resolver 集成测试（adapter 注册顺序 + yaml 配置传递）
- `docs/design/sw-com-session-threading-model.md` — 锁粒度/idle shutdown/restart 交互设计（reviewer I-4 要求）

**Per-file 责任边界：**

- `sw_com_session.py` — 生命周期状态机的唯一源；持 `_lock` 保护所有 `_app` 访问
- threading model 文档 — 描述 convert / idle-shutdown / restart 三个状态转换的锁交互，防止后续开发踩死锁
- `parts_library.default.yaml` — 纯配置，无逻辑；adapter 通过 config dict 读取，不直接 import yaml
- `check_env.py` — 检测 + 展示；不做修复动作

---

## Task 0：Threading Model 设计文档（reviewer I-4）

**Files:**

- Create: `docs/design/sw-com-session-threading-model.md`

- [ ] **Step 1：** 创建设计文档，写以下内容：

````markdown
# SwComSession 线程模型（Part 2a）

## 背景

COM 接口非线程安全（v4 决策 #22）。Part 1 用 `self._lock` 全方法包裹 `convert_sldprt_to_step`，避免两个线程同时调 COM。Part 2 要加入 `start()` / `_maybe_restart()` / idle shutdown，锁粒度若处理不当会死锁。

## 状态转换

```
  ┌───────────────┐  start() 成功 ┌─────────────┐
  │ UNINITIALIZED ├──────────────▶│   RUNNING   │
  │  (_app=None)  │               │ (_app≠None) │
  └──────┬────────┘               └──────┬──────┘
         │                               │
         │ start() 失败                  │ convert 50 次
         │ / cold timeout                │
         ▼                               ▼
  ┌───────────────┐                ┌─────────────┐
  │   UNHEALTHY   │◀───熔断────────│  RESTARTING │
  │(_unhealthy=T) │  (连续3次失败) │ shutdown + start│
  └───────────────┘                └─────────────┘
                                          │
                                          │ idle 5min
                                          ▼
                                   ┌─────────────┐
                                   │  SHUTDOWN   │
                                   │ _app=None   │
                                   └─────────────┘
```

## 锁粒度规则

1. **`_lock` 是 session 内状态的唯一锁**。`_SINGLETON_LOCK` 是模块级锁，只保护 singleton 实例化。
2. **持 `_lock` 的操作 → 可以调 COM**。不持锁调 COM = race。
3. **持 `_lock` 时禁止 acquire `_SINGLETON_LOCK`**（避免嵌套死锁；singleton 在 convert 内部不会被重建）。
4. **所有可能触发 `start()` 的入口必须已经持 `_lock`**：convert 内若发现 `_app is None` 走 `_start_locked()`，不重新 acquire。
5. **idle shutdown 不能阻塞 convert**：采用 opportunistic 模型——每次 convert 入口检查 `time.time() - _last_used_ts >= IDLE_SHUTDOWN_SEC`，命中则先 shutdown 再 start，全程在同一 `_lock` 里。不引入后台线程。
6. **restart 同样 in-band**：`convert` 成功后计数，达到 `RESTART_EVERY_N_CONVERTS` 时在下一次 convert 入口先触发 restart。

## 为什么不引入后台线程做 idle shutdown？

- 后台线程做 shutdown 要 acquire `_lock`，但 `_lock` 在 convert 期间被长期持有（单转最长 30s）。后台线程会长时间 block。
- 即使后台线程能抢到锁，shutdown 后 convert 若恢复需要重新 start，增加状态机复杂度。
- Opportunistic 模型天然避免并发：下次 convert 发现空闲 → shutdown → restart，状态转换线性化。
- 成本：若 session 空闲超过 `IDLE_SHUTDOWN_SEC` 但永远无下一次 convert，SW 进程不释放。这由 `reset_session()`（`reset_all_sw_caches` 调用链）兜底，可接受。

## `_lock` vs `threading.Timer`

本模型**不使用** Timer 或后台线程。理由同上。`SINGLE_CONVERT_TIMEOUT_SEC` 的超时保护推迟到 Part 2c 的 SW-B0 spike 补课时再定方案（可能方向：subprocess 隔离 / ctypes.wintypes.WAIT_TIMEOUT / SW API 自带的 cancel）。

## 契约

- **`start()` 必须在 `_lock` 内调用** — 约定：只在 `_start_locked()` 方法存在，外部不直接调
- **`convert_sldprt_to_step` 是唯一可能触发状态转换的入口** — 所有生命周期副作用在此方法串行化
- **`shutdown()` 可在 `_lock` 外调用**（用于 `reset_session()` 测试兜底）——shutdown 自行 acquire `_lock`
- **`reset_session()` 会调 `shutdown()`** — 外部测试通过此入口清除状态
````

- [ ] **Step 2：** commit

```bash
git add docs/design/sw-com-session-threading-model.md
git commit -m "docs(sw-b): SwComSession Part 2 线程模型设计（reviewer I-4）"
```

---

## Task 1：`_start_locked()` 方法（session 冷启动）

**Files:**

- Modify: `adapters/solidworks/sw_com_session.py`
- Test: `tests/test_sw_com_session_lifecycle.py`

### 1.1 失败测试 — `_start_locked` 触发冷启动后 `_app` 非 None

- [ ] **Step 3：** 创建测试文件 `tests/test_sw_com_session_lifecycle.py`：

```python
"""SwComSession Part 2 生命周期测试（v4 决策 #10/#11）。"""

from __future__ import annotations

import os
import sys
import time
import unittest.mock as mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestStartLocked:
    """`_start_locked` 是 `convert` 内部 _app 未初始化时的懒加载入口。"""

    def test_start_locked_sets_app_on_success(self):
        from adapters.solidworks import sw_com_session

        sw_com_session.reset_session()
        sess = sw_com_session.get_session()

        fake_app = mock.MagicMock()
        fake_app.LoadAddIn.return_value = 1  # SW LoadAddIn 成功返回 1
        fake_dispatch = mock.MagicMock(return_value=fake_app)

        with mock.patch.object(sw_com_session, "_com_dispatch", fake_dispatch):
            with sess._lock:
                sess._start_locked()

        assert sess._app is fake_app
        assert sess._unhealthy is False
        fake_app.LoadAddIn.assert_called_once_with("SOLIDWORKS Toolbox")
        assert fake_app.Visible is False
        assert fake_app.UserControl is False
```

- [ ] **Step 4：** 运行测试确认失败：

```bash
python -m pytest tests/test_sw_com_session_lifecycle.py::TestStartLocked::test_start_locked_sets_app_on_success -v
```

预期：FAIL with `AttributeError: 'SwComSession' object has no attribute '_start_locked'` 或 `_com_dispatch not found`。

### 1.2 实现 `_com_dispatch` + `_start_locked`

- [ ] **Step 5：** 修改 `adapters/solidworks/sw_com_session.py`，在文件顶部 constants 之后（line ~48 后）加 COM dispatch helper：

```python
def _com_dispatch(prog_id: str):
    """lazy import win32com.client.Dispatch（单元测试可 monkeypatch 此函数）。

    Args:
        prog_id: 例如 "SldWorks.Application"

    Returns:
        win32com Dispatch 对象

    Raises:
        ImportError: pywin32 未安装
        pywin32 com_error: SW 未安装或启动失败
    """
    from win32com.client import Dispatch  # type: ignore[import-not-found]

    return Dispatch(prog_id)
```

- [ ] **Step 6：** 在 `SwComSession` 类里 `convert_sldprt_to_step` 之前加 `_start_locked`：

```python
    def _start_locked(self) -> None:
        """冷启动（v4 决策 #10）。必须在持 self._lock 的上下文内调用。

        流程：
        1. Dispatch("SldWorks.Application")
        2. app.Visible = False, UserControl = False（避免弹窗）
        3. app.LoadAddIn("SOLIDWORKS Toolbox")
        4. 任何步骤失败 → self._unhealthy=True，抛异常

        时间上限由调用方保证（Part 2c SW-B0 spike 补课后决定实现手段）。
        """
        assert self._lock.locked(), "_start_locked 必须在持锁上下文内调用"

        try:
            app = _com_dispatch("SldWorks.Application")
            app.Visible = False
            app.UserControl = False
            result = app.LoadAddIn("SOLIDWORKS Toolbox")
            if not result:
                raise RuntimeError(
                    "LoadAddIn('SOLIDWORKS Toolbox') 返回 0 — "
                    "Toolbox Add-In 可能未安装；请在 SolidWorks Tools → "
                    "Add-Ins 勾选 SOLIDWORKS Toolbox Library"
                )
            self._app = app
            self._last_used_ts = time.time()
        except Exception:
            self._unhealthy = True
            self._app = None
            raise
```

- [ ] **Step 7：** 运行 Step 3 的测试确认通过：

```bash
python -m pytest tests/test_sw_com_session_lifecycle.py::TestStartLocked::test_start_locked_sets_app_on_success -v
```

预期：PASS。

### 1.3 失败路径测试

- [ ] **Step 8：** 继续在 `TestStartLocked` 类中追加失败场景测试：

```python
    def test_start_locked_marks_unhealthy_on_dispatch_failure(self):
        """Dispatch 失败（SW 未安装/启动失败） → _unhealthy=True。"""
        from adapters.solidworks import sw_com_session

        sw_com_session.reset_session()
        sess = sw_com_session.get_session()

        def fake_dispatch(_prog_id):
            raise RuntimeError("COM Dispatch failed")

        with mock.patch.object(sw_com_session, "_com_dispatch", fake_dispatch):
            with sess._lock:
                with pytest.raises(RuntimeError, match="COM Dispatch failed"):
                    sess._start_locked()

        assert sess._unhealthy is True
        assert sess._app is None

    def test_start_locked_marks_unhealthy_on_loadaddin_failure(self):
        """LoadAddIn 返回 0 → _unhealthy=True + 提示 Tools→Add-Ins 勾选。"""
        from adapters.solidworks import sw_com_session

        sw_com_session.reset_session()
        sess = sw_com_session.get_session()

        fake_app = mock.MagicMock()
        fake_app.LoadAddIn.return_value = 0  # 失败

        with mock.patch.object(
            sw_com_session, "_com_dispatch", mock.MagicMock(return_value=fake_app)
        ):
            with sess._lock:
                with pytest.raises(RuntimeError, match="Tools → Add-Ins"):
                    sess._start_locked()

        assert sess._unhealthy is True
        assert sess._app is None
```

- [ ] **Step 9：** 运行两个测试确认通过：

```bash
python -m pytest tests/test_sw_com_session_lifecycle.py::TestStartLocked -v
```

预期：3 passed。

- [ ] **Step 10：** commit

```bash
git add adapters/solidworks/sw_com_session.py tests/test_sw_com_session_lifecycle.py
git commit -m "feat(sw-b): SwComSession._start_locked 冷启动实现（v4 决策 #10）"
```

---

## Task 2：`convert_sldprt_to_step` 自动触发 `_start_locked`

之前 `_do_convert` 在 `_app is None` 时返回 False 并打 warning（Part 1 保底）。Part 2 要改为"自动冷启动"。

**Files:**

- Modify: `adapters/solidworks/sw_com_session.py`
- Test: `tests/test_sw_com_session_lifecycle.py`

### 2.1 失败测试

- [ ] **Step 11：** 在 `tests/test_sw_com_session_lifecycle.py` 追加新类：

```python
class TestConvertAutoStart:
    """convert 入口发现 _app is None 时自动触发 _start_locked。"""

    def test_convert_triggers_start_when_app_none(self, tmp_path):
        """首次 convert 应自动冷启动。"""
        from adapters.solidworks import sw_com_session

        sw_com_session.reset_session()
        sess = sw_com_session.get_session()

        fake_app = mock.MagicMock()
        fake_app.LoadAddIn.return_value = 1
        # 让 _do_convert 走完但直接返回 False（不关心几何）
        # 触发路径关键：start 被调用 → _app 被赋值
        dispatch_mock = mock.MagicMock(return_value=fake_app)

        with mock.patch.object(sw_com_session, "_com_dispatch", dispatch_mock):
            # _do_convert 在 OpenDoc6 上会进一步操作 fake_app，我们只关心 start 被触发
            sldprt = tmp_path / "fake.sldprt"
            sldprt.write_bytes(b"")
            step_out = tmp_path / "out.step"

            sess.convert_sldprt_to_step(str(sldprt), str(step_out))

        dispatch_mock.assert_called_once_with("SldWorks.Application")
        assert sess._app is fake_app

    def test_convert_does_not_restart_when_already_running(self, tmp_path):
        """_app 已初始化时不应重新调用 Dispatch。"""
        from adapters.solidworks import sw_com_session

        sw_com_session.reset_session()
        sess = sw_com_session.get_session()

        fake_app = mock.MagicMock()
        fake_app.LoadAddIn.return_value = 1
        sess._app = fake_app  # 模拟已启动

        dispatch_mock = mock.MagicMock()
        with mock.patch.object(sw_com_session, "_com_dispatch", dispatch_mock):
            sldprt = tmp_path / "fake.sldprt"
            sldprt.write_bytes(b"")
            step_out = tmp_path / "out.step"
            sess.convert_sldprt_to_step(str(sldprt), str(step_out))

        dispatch_mock.assert_not_called()
```

- [ ] **Step 12：** 运行失败（现有 `_do_convert` 看到 `_app is None` 直接 `return False`，不会调 `_com_dispatch`）：

```bash
python -m pytest tests/test_sw_com_session_lifecycle.py::TestConvertAutoStart -v
```

预期：FAIL with `dispatch_mock.assert_called_once_with(...)` 检查失败。

### 2.2 实现

- [ ] **Step 13：** 修改 `adapters/solidworks/sw_com_session.py::convert_sldprt_to_step`，把 `_do_convert` 调用处改为先尝试 `_start_locked`：

```python
        with self._lock:
            if self._unhealthy:
                return False

            # Part 2a: _app 未初始化 → 自动触发冷启动（决策 #10）
            if self._app is None:
                try:
                    self._start_locked()
                except Exception as e:
                    log.warning("COM 冷启动失败: %s", e)
                    return False

            success = False
            try:
                success = self._do_convert(sldprt_path, step_out)
```

（即在原 `success = False` 之前插入 start 逻辑；其余不变）

- [ ] **Step 14：** 运行测试：

```bash
python -m pytest tests/test_sw_com_session_lifecycle.py::TestConvertAutoStart -v
```

预期：PASS。

- [ ] **Step 15：** 回归 Part 1 全 SW 测试，确保无破坏：

```bash
python -m pytest tests/test_sw_com_session.py tests/test_sw_material_bridge.py tests/test_sw_toolbox_adapter.py tests/test_sw_toolbox_catalog.py tests/test_sw_detect.py -v
```

预期：104+ passed（Part 1 103 + Part 2a 新增）。

- [ ] **Step 16：** commit

```bash
git add adapters/solidworks/sw_com_session.py tests/test_sw_com_session_lifecycle.py
git commit -m "feat(sw-b): convert_sldprt_to_step 自动触发 _start_locked（v4 决策 #10）"
```

---

## Task 3：`_maybe_restart()` — 每 50 次强制 restart（v4 决策 #11）

**Files:**

- Modify: `adapters/solidworks/sw_com_session.py`
- Test: `tests/test_sw_com_session_lifecycle.py`

### 3.1 失败测试

- [ ] **Step 17：** 在 `tests/test_sw_com_session_lifecycle.py` 追加：

```python
class TestMaybeRestart:
    """_convert_count 达 RESTART_EVERY_N_CONVERTS 时 shutdown + restart。"""

    def test_restart_fires_at_threshold(self, tmp_path, monkeypatch):
        """convert_count=50 时下次 convert 入口应先 shutdown 再 start。"""
        from adapters.solidworks import sw_com_session

        sw_com_session.reset_session()
        sess = sw_com_session.get_session()

        old_app = mock.MagicMock()
        new_app = mock.MagicMock()
        new_app.LoadAddIn.return_value = 1
        sess._app = old_app
        sess._convert_count = sw_com_session.RESTART_EVERY_N_CONVERTS  # 触发阈值

        dispatch_mock = mock.MagicMock(return_value=new_app)
        with mock.patch.object(sw_com_session, "_com_dispatch", dispatch_mock):
            sldprt = tmp_path / "fake.sldprt"
            sldprt.write_bytes(b"")
            step_out = tmp_path / "out.step"
            sess.convert_sldprt_to_step(str(sldprt), str(step_out))

        # old_app 被 ExitApp 过
        old_app.ExitApp.assert_called_once()
        # 重新 Dispatch 产出了 new_app
        dispatch_mock.assert_called_once_with("SldWorks.Application")
        assert sess._app is new_app
        # _convert_count 重置
        assert sess._convert_count <= 1  # 可能 +1（看 _do_convert 是否成功）

    def test_no_restart_below_threshold(self, tmp_path):
        """count 未达阈值时不触发 restart。"""
        from adapters.solidworks import sw_com_session

        sw_com_session.reset_session()
        sess = sw_com_session.get_session()

        app = mock.MagicMock()
        app.LoadAddIn.return_value = 1
        sess._app = app
        sess._convert_count = sw_com_session.RESTART_EVERY_N_CONVERTS - 1

        with mock.patch.object(sw_com_session, "_com_dispatch", mock.MagicMock()):
            sldprt = tmp_path / "fake.sldprt"
            sldprt.write_bytes(b"")
            step_out = tmp_path / "out.step"
            sess.convert_sldprt_to_step(str(sldprt), str(step_out))

        app.ExitApp.assert_not_called()
```

- [ ] **Step 18：** 运行失败：

```bash
python -m pytest tests/test_sw_com_session_lifecycle.py::TestMaybeRestart -v
```

预期：FAIL（`old_app.ExitApp.assert_called_once()` 失败，因为 Part 1 没有 restart 逻辑）。

### 3.2 实现

- [ ] **Step 19：** 先把现有 `shutdown()` 拆分为 `_shutdown_locked()`（无锁版，供持锁方调用） + `shutdown()`（外部入口，自 acquire 锁）。找到当前 shutdown 方法：

```python
    def shutdown(self) -> None:
        """释放 SW COM session。"""
        with self._lock:
            if self._app is not None:
                try:
                    self._app.ExitApp()
                except Exception:
                    pass
                self._app = None
```

替换为：

```python
    def _shutdown_locked(self) -> None:
        """实际 shutdown 逻辑，假设已持 self._lock。"""
        if self._app is not None:
            try:
                self._app.ExitApp()
            except Exception as e:
                # reviewer Minor M-3: shutdown COM 异常记 debug 供 Part 2 排查
                log.debug("COM ExitApp 异常（忽略）: %s", e)
            self._app = None

    def shutdown(self) -> None:
        """外部入口：acquire self._lock 后 shutdown。"""
        with self._lock:
            self._shutdown_locked()
```

- [ ] **Step 20：** 在 `_start_locked` 之后添加 `_maybe_restart_locked`：

```python
    def _maybe_restart_locked(self) -> None:
        """若已达 RESTART_EVERY_N_CONVERTS 次，先 shutdown 再 start。

        必须在持 self._lock 的上下文内调用。
        shutdown 失败被吞掉（视为进程已死），_start_locked 负责重建。
        start 失败会让 _unhealthy=True 冒泡。
        """
        assert self._lock.locked()

        if self._convert_count < RESTART_EVERY_N_CONVERTS:
            return

        log.info(
            "触发 COM session 周期重启 (count=%d，阈值 %d)",
            self._convert_count,
            RESTART_EVERY_N_CONVERTS,
        )
        self._shutdown_locked()
        self._start_locked()
        self._convert_count = 0
```

- [ ] **Step 21：** 在 `convert_sldprt_to_step` 的 `_start_locked` 调用之前插入 restart 检查：

```python
            # Part 2a: 周期重启（决策 #11）— 在冷启动检查之前
            try:
                self._maybe_restart_locked()
            except Exception as e:
                log.warning("COM 周期重启失败: %s", e)
                return False

            # Part 2a: _app 未初始化 → 自动触发冷启动（决策 #10）
            if self._app is None:
                ...
```

（顺序是关键：restart 必须先于 `_app is None` 分支，因为 restart 会把 `_app` 清成 None）

- [ ] **Step 22：** 运行 Task 3 测试：

```bash
python -m pytest tests/test_sw_com_session_lifecycle.py::TestMaybeRestart -v
```

预期：2 passed。

- [ ] **Step 23：** 回归 Part 1 + Part 2a 所有 SW 测试：

```bash
python -m pytest tests/test_sw_com_session.py tests/test_sw_material_bridge.py tests/test_sw_toolbox_adapter.py tests/test_sw_toolbox_catalog.py tests/test_sw_detect.py tests/test_sw_com_session_lifecycle.py -v
```

预期：全绿。

- [ ] **Step 24：** commit

```bash
git add adapters/solidworks/sw_com_session.py tests/test_sw_com_session_lifecycle.py
git commit -m "feat(sw-b): SwComSession 周期重启 _maybe_restart_locked（v4 决策 #11）"
```

---

## Task 4：Idle Shutdown —— opportunistic 模型

**Files:**

- Modify: `adapters/solidworks/sw_com_session.py`
- Test: `tests/test_sw_com_session_lifecycle.py`

### 4.1 失败测试

- [ ] **Step 25：** 在 `tests/test_sw_com_session_lifecycle.py` 追加：

```python
class TestIdleShutdown:
    """convert 入口若发现距上次 convert 超过 IDLE_SHUTDOWN_SEC，先 shutdown 再 start。"""

    def test_idle_shutdown_triggers_restart(self, tmp_path, monkeypatch):
        from adapters.solidworks import sw_com_session

        sw_com_session.reset_session()
        sess = sw_com_session.get_session()

        old_app = mock.MagicMock()
        new_app = mock.MagicMock()
        new_app.LoadAddIn.return_value = 1
        sess._app = old_app
        # 上次 convert 是 IDLE_SHUTDOWN_SEC + 1 秒之前
        sess._last_used_ts = time.time() - (sw_com_session.IDLE_SHUTDOWN_SEC + 1)

        dispatch_mock = mock.MagicMock(return_value=new_app)
        with mock.patch.object(sw_com_session, "_com_dispatch", dispatch_mock):
            sldprt = tmp_path / "fake.sldprt"
            sldprt.write_bytes(b"")
            step_out = tmp_path / "out.step"
            sess.convert_sldprt_to_step(str(sldprt), str(step_out))

        old_app.ExitApp.assert_called_once()
        dispatch_mock.assert_called_once()
        assert sess._app is new_app

    def test_no_idle_shutdown_within_window(self, tmp_path):
        """最近有 convert 活动 → 不触发 idle shutdown。"""
        from adapters.solidworks import sw_com_session

        sw_com_session.reset_session()
        sess = sw_com_session.get_session()

        app = mock.MagicMock()
        app.LoadAddIn.return_value = 1
        sess._app = app
        sess._last_used_ts = time.time()  # 刚用过

        with mock.patch.object(sw_com_session, "_com_dispatch", mock.MagicMock()):
            sldprt = tmp_path / "fake.sldprt"
            sldprt.write_bytes(b"")
            step_out = tmp_path / "out.step"
            sess.convert_sldprt_to_step(str(sldprt), str(step_out))

        app.ExitApp.assert_not_called()
```

- [ ] **Step 26：** 运行失败：

```bash
python -m pytest tests/test_sw_com_session_lifecycle.py::TestIdleShutdown -v
```

预期：FAIL（`old_app.ExitApp.assert_called_once()` 失败）。

### 4.2 实现

- [ ] **Step 27：** 在 `sw_com_session.py` 的 `_maybe_restart_locked` 之后添加 `_maybe_idle_shutdown_locked`：

```python
    def _maybe_idle_shutdown_locked(self) -> None:
        """若距上次 convert 已超 IDLE_SHUTDOWN_SEC，shutdown 释放 SW。
        必须在持 self._lock 的上下文内调用。下次 convert 会重新 start。

        _app is None 或 _last_used_ts==0 时 no-op（还没用过或已释放）。
        """
        assert self._lock.locked()

        if self._app is None:
            return
        if self._last_used_ts == 0.0:
            return
        if time.time() - self._last_used_ts < IDLE_SHUTDOWN_SEC:
            return

        log.info("idle shutdown（距上次 convert %.0f 秒）",
                 time.time() - self._last_used_ts)
        self._shutdown_locked()
```

- [ ] **Step 28：** 在 `convert_sldprt_to_step` 的 restart 检查之前插入 idle shutdown：

```python
            # Part 2a: idle shutdown（决策 #3 + threading model doc）
            # 先于 restart 检查 —— idle 已经 shutdown，restart 判断无意义
            self._maybe_idle_shutdown_locked()

            # Part 2a: 周期重启（决策 #11）
            try:
                self._maybe_restart_locked()
            ...
```

- [ ] **Step 29：** 运行 Task 4 测试：

```bash
python -m pytest tests/test_sw_com_session_lifecycle.py::TestIdleShutdown -v
```

预期：2 passed。

- [ ] **Step 30：** 回归全量：

```bash
python -m pytest tests/ -k "sw_" -v
```

预期：全绿。

- [ ] **Step 31：** commit

```bash
git add adapters/solidworks/sw_com_session.py tests/test_sw_com_session_lifecycle.py
git commit -m "feat(sw-b): SwComSession idle shutdown opportunistic 模型（threading model doc）"
```

---

## Task 5：SW-B6（上）—— `default_resolver` 注册 SwToolboxAdapter

**Files:**

- Modify: `parts_resolver.py`
- Test: `tests/test_sw_toolbox_adapter_registration.py`

### 5.1 失败测试

- [ ] **Step 32：** 创建 `tests/test_sw_toolbox_adapter_registration.py`：

```python
"""default_resolver 集成 SwToolboxAdapter 的注册测试（SW-B6）。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestSwToolboxRegistration:
    """v4 §3.1: SwToolboxAdapter 在 bd_warehouse 之后、jinja_primitive 之前。"""

    def test_default_resolver_registers_sw_toolbox_adapter(self, tmp_path):
        """default_resolver 返回的 PartsResolver 应含名为 'sw_toolbox' 的 adapter。"""
        from parts_resolver import default_resolver

        # 给 tmp_path 一个空 yaml（走 default registry）
        resolver = default_resolver(project_root=str(tmp_path))
        adapter_names = [a.name for a in resolver.adapters]
        assert "sw_toolbox" in adapter_names

    def test_sw_toolbox_registered_after_bd_warehouse(self, tmp_path):
        """注册顺序：bd_warehouse → sw_toolbox → jinja_primitive（前者优先）。"""
        from parts_resolver import default_resolver

        resolver = default_resolver(project_root=str(tmp_path))
        names = [a.name for a in resolver.adapters]
        if "bd_warehouse" in names and "sw_toolbox" in names:
            assert names.index("sw_toolbox") > names.index("bd_warehouse")
        if "sw_toolbox" in names and "jinja_primitive" in names:
            assert names.index("sw_toolbox") < names.index("jinja_primitive")

    def test_sw_toolbox_receives_config_from_yaml(self, tmp_path):
        """yaml `solidworks_toolbox:` 段应作为 config 传入 SwToolboxAdapter。"""
        from parts_resolver import default_resolver

        resolver = default_resolver(project_root=str(tmp_path))
        sw_adapter = next(
            (a for a in resolver.adapters if a.name == "sw_toolbox"), None
        )
        assert sw_adapter is not None
        # default yaml 应至少提供 min_score 字段
        assert "min_score" in sw_adapter.config or sw_adapter.config == {}
```

- [ ] **Step 33：** 运行失败：

```bash
python -m pytest tests/test_sw_toolbox_adapter_registration.py -v
```

预期：FAIL（`sw_toolbox` 不在 adapter_names 里）。

### 5.2 实现

- [ ] **Step 34：** 修改 `parts_resolver.py::default_resolver`，在 bd_warehouse 注册之后、step_pool 之前插入：

（原代码大约在 line 577 后，bd_warehouse 注册完成的位置）

```python
    # Phase SW-B Part 2a — SwToolboxAdapter (opt-in via yaml config +
    # runtime is_available() self-report)
    try:
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        resolver.register_adapter(SwToolboxAdapter(
            project_root=project_root,
            config=registry.get("solidworks_toolbox", {}),
        ))
    except ImportError as e:
        if logger:
            logger(f"  [resolver] SwToolboxAdapter unavailable: {e}")
    except RuntimeError as e:
        # validate_size_patterns 拒绝恶意 yaml → 不注册但管道继续
        if logger:
            logger(f"  [resolver] SwToolboxAdapter config rejected: {e}")
```

- [ ] **Step 35：** 运行测试：

```bash
python -m pytest tests/test_sw_toolbox_adapter_registration.py -v
```

预期：3 passed。

- [ ] **Step 36：** commit

```bash
git add parts_resolver.py tests/test_sw_toolbox_adapter_registration.py
git commit -m "feat(sw-b): default_resolver 注册 SwToolboxAdapter（SW-B6 上）"
```

---

## Task 6：SW-B6（下）—— `parts_library.default.yaml` 增加配置段

**Files:**

- Modify: `parts_library.default.yaml`
- Test: `tests/test_sw_toolbox_adapter_registration.py`

### 6.1 失败测试 — yaml 配置项生效

- [ ] **Step 37：** 在 `tests/test_sw_toolbox_adapter_registration.py` 追加：

```python
class TestDefaultYamlConfig:
    """v4 §6: parts_library.default.yaml 的 solidworks_toolbox 段内容。"""

    def test_default_yaml_provides_solidworks_toolbox_section(self, tmp_path):
        from parts_resolver import default_resolver

        resolver = default_resolver(project_root=str(tmp_path))
        sw_adapter = next(a for a in resolver.adapters if a.name == "sw_toolbox")
        cfg = sw_adapter.config

        assert cfg.get("enabled") == "auto"
        assert set(cfg.get("standards", [])) >= {"GB", "ISO", "DIN"}
        assert cfg.get("min_score") == 0.30

        # token_weights 四字段齐全（决策 #12）
        weights = cfg.get("token_weights", {})
        assert weights == {
            "part_no": 2.0,
            "name_cn": 1.0,
            "material": 0.5,
            "size": 1.5,
        }

        # size_patterns 两个类别齐全（决策 #9 + §1.3）
        sp = cfg.get("size_patterns", {})
        assert "fastener" in sp
        assert "bearing" in sp
        # fastener 含 exclude_patterns 防 UNC/Tr/G/NPT
        assert any("UN" in p for p in sp["fastener"].get("exclude_patterns", []))

        # com 超时常量可覆盖
        com_cfg = cfg.get("com", {})
        assert com_cfg.get("cold_start_timeout_sec") == 90
        assert com_cfg.get("restart_every_n_converts") == 50

    def test_default_yaml_has_gb_fastener_rule_before_generic_fallback(self, tmp_path):
        """YAML mapping: GB 高优先级规则必须在 bd_warehouse generic fallback 之前。"""
        import yaml
        from parts_resolver import load_registry

        reg = load_registry(str(tmp_path))
        mappings = reg.get("mappings", [])
        # 找到第一个 adapter=solidworks_toolbox 且含 GB 的规则
        sw_gb_idx = None
        bd_any_idx = None
        for i, m in enumerate(mappings):
            if m.get("adapter") == "solidworks_toolbox":
                keywords = m.get("match", {}).get("keyword_contains", [])
                if any("GB" in k for k in keywords) and sw_gb_idx is None:
                    sw_gb_idx = i
            if m.get("adapter") == "jinja_primitive" and bd_any_idx is None:
                bd_any_idx = i

        assert sw_gb_idx is not None, "缺少 SW Toolbox GB 规则"
        assert bd_any_idx is not None, "缺少 jinja_primitive 兜底"
        assert sw_gb_idx < bd_any_idx, "GB 规则必须在 jinja_primitive 兜底之前"
```

- [ ] **Step 38：** 运行失败：

```bash
python -m pytest tests/test_sw_toolbox_adapter_registration.py::TestDefaultYamlConfig -v
```

预期：FAIL（`cfg.get("enabled") is None` — yaml 里没有该段）。

### 6.2 实现 — yaml 配置段 + mappings

- [ ] **Step 39：** 修改 `parts_library.default.yaml`。在 `partcad: ... enabled: false` 之后、`mappings:` 之前插入：

```yaml
# ═══════════════════════════════════════════════════════════════════════
# SolidWorks Toolbox integration (Phase SW-B, opt-in + runtime self-report)
# ═══════════════════════════════════════════════════════════════════════
# `enabled: auto` — adapter runs `is_available()` to self-report; no user
# action required. When SW is absent, this section is silently ignored.
#
# Cache path resolution order (决策 #16):
#   1. This yaml's `cache` field (leave unset to skip)
#   2. Env var CAD_SPEC_GEN_SW_TOOLBOX_CACHE
#   3. Default: Path.home() / '.cad-spec-gen' / 'step_cache' / 'sw_toolbox'
#
# ⚠️ 浅覆盖陷阱（v3）：project-level parts_library.yaml 若 `extends: default`
# 并只想覆盖单字段，必须把本段完整重抄一遍，否则未覆盖字段会丢失。
solidworks_toolbox:
  enabled: auto
  standards: [GB, ISO, DIN]
  # cache: ~/.cad-spec-gen/step_cache/sw_toolbox/   # 默认注释掉
  min_score: 0.30

  # 加权 token overlap（决策 #12）
  token_weights:
    part_no: 2.0        # 标准号最高权重
    name_cn: 1.0
    material: 0.5
    size: 1.5           # 从 name_cn 抽出的 M6/6205 等

  # 尺寸正则（仅公制 M 螺纹和基本轴承，决策 §1.3）
  size_patterns:
    fastener:
      size: '[Mm](\d+(?:\.\d+)?)'
      length: '[×xX*\-\s](\d+(?:\.\d+)?)'
      exclude_patterns: ['UN[CFEF]', '\bTr\d', '\bG\d/', '\bNPT']
    bearing:
      model: '\b(\d{4,5})\b'

  # COM 超时/重启（决策 #10、#11，可按机型调整）
  com:
    cold_start_timeout_sec: 90
    single_convert_timeout_sec: 30
    restart_every_n_converts: 50
    idle_shutdown_sec: 300
    circuit_breaker_threshold: 3
```

- [ ] **Step 40：** 修改 `parts_library.default.yaml::mappings`，在现有 bd_warehouse 规则**之前**插入 SW Toolbox 高优先级 + ISO/DIN 兜底规则。具体位置：在 "Specialized bearing classes" 注释块之前。

```yaml
  # ─── SolidWorks Toolbox — GB 高优先级（v4 §6） ──────────────────────
  # GB/T 国标紧固件和轴承走 SW Toolbox（1818 个标准件 sldprt），仅在
  # `is_available()` 全通过时生效（SW 装了 + Toolbox Add-In 启用）。
  - match:
      category: fastener
      keyword_contains: ["GB/T", "国标", "GB "]
    adapter: sw_toolbox
    spec:
      standard: GB
      subcategories: ["bolts and studs", "nuts", "screws",
                      "washers and rings", "pins", "rivets"]
      part_category: fastener

  - match:
      category: bearing
      keyword_contains: ["GB/T", "国标", "深沟球", "圆柱滚子", "推力"]
    adapter: sw_toolbox
    spec:
      standard: GB
      subcategories: ["bearing"]
      part_category: bearing

```

- [ ] **Step 41：** 同文件，在现有 bd_warehouse "Everything else" 兜底规则**之前**插入 ISO/DIN 兜底规则（位置：在 `- match: {any: true}` 之前）：

```yaml
  # ─── SolidWorks Toolbox — ISO/DIN 兜底（v4 §6） ──────────────────────
  - match:
      category: fastener
    adapter: sw_toolbox
    spec:
      standard: [ISO, DIN]
      subcategories: ["bolts", "nuts", "screws", "washers"]
      part_category: fastener

  - match:
      category: bearing
    adapter: sw_toolbox
    spec:
      standard: [ISO, DIN]
      subcategories: ["bearings"]
      part_category: bearing

```

- [ ] **Step 42：** 运行 Task 6 测试：

```bash
python -m pytest tests/test_sw_toolbox_adapter_registration.py -v
```

预期：5 passed（3 from Task 5 + 2 from Task 6）。

- [ ] **Step 43：** 回归全量 SW：

```bash
python -m pytest tests/ -k "sw_" -v
```

预期：全绿。

- [ ] **Step 44：** 跑一次 smoke test，验证不破坏既有 resolver 行为：

```bash
python -m pytest tests/test_parts_resolver.py -v 2>&1 | tail -20
```

预期：既有测试全绿（或已知失败数不变）。

- [ ] **Step 45：** commit

```bash
git add parts_library.default.yaml tests/test_sw_toolbox_adapter_registration.py
git commit -m "feat(sw-b): parts_library.default.yaml solidworks_toolbox 配置段 + GB/ISO/DIN mappings（SW-B6 下）"
```

---

## Task 7：env-check UX —— `toolbox_addin_enabled` 指引（决策 #13）

**Files:**

- Modify: `tools/hybrid_render/check_env.py`
- Test: 无专用测试（`check_env.py` 是 CLI 工具，靠集成 smoke test 验证；可选：加一个 import-only 测试）

### 7.1 修改增强源展示

- [ ] **Step 46：** 修改 `tools/hybrid_render/check_env.py::detect_environment`（line ~161 附近），在 `enhancements["solidworks"]` dict 中增加字段：

```python
        enhancements["solidworks"] = {
            "ok": sw.installed and (sw.version_year or 0) >= 2020,
            "version": sw.version,
            "path_a": (sw.version_year or 0) >= 2020,
            "path_b": (sw.version_year or 0) >= 2024 and sw.com_available,
            "pywin32": sw.pywin32_available,
            "materials": len(sw.sldmat_paths),
            "toolbox_addin_enabled": sw.toolbox_addin_enabled,  # 新增
        }
```

- [ ] **Step 47：** 修改同文件的展示逻辑（line ~260 附近 `sw_enh = enhancements.get("solidworks", {})` 之后的 if/else 块）：

```python
    if sw_enh.get("ok"):
        sw_ver = sw_enh.get("version", "?")
        path_a = "材质 ✓" if sw_enh.get("path_a") else "材质 ✗"
        if sw_enh.get("path_b"):
            # Path B 细分：pywin32 + Toolbox Add-In 两个前置条件
            if sw_enh.get("toolbox_addin_enabled"):
                path_b = "Toolbox ✓"
            else:
                path_b = "Toolbox ✗ (Add-In 未启用)"
        elif sw_enh.get("pywin32"):
            path_b = "Toolbox ✗ (版本 < 2024)"
        else:
            path_b = "Toolbox ✗ (pywin32 未安装)"
        print(f"  SolidWorks    [OK]    {sw_ver} — {path_a} / {path_b}")

        # 决策 #13: Add-In 未启用时给出明确勾选指引
        if sw_enh.get("path_b") and not sw_enh.get("toolbox_addin_enabled"):
            print("                        启用 Toolbox Library：")
            print("                          SolidWorks → Tools → Add-Ins →")
            print("                          勾选 'SOLIDWORKS Toolbox Library'")
            print("                          （可同时勾选右侧 Startup 自动加载）")
    else:
        print("  SolidWorks    [  ]    未检测到安装")
        print("                        已有 SolidWorks 许可？安装后可自动集成材质库和标准件。")
```

### 7.2 集成 smoke test

- [ ] **Step 48：** 运行 check_env.py 看输出格式，确保不崩：

```bash
python tools/hybrid_render/check_env.py 2>&1 | head -30
```

预期：运行完成，能看到 SolidWorks 行；如果本机已装 SW 且 Toolbox Add-In 未启用，会看到勾选指引。

- [ ] **Step 49：** 追加一个极简 unit test 防止字段名漂移。在 `tests/` 下新建或复用 `tests/test_check_env_sw.py`：

```python
"""check_env.py 对 SW toolbox_addin_enabled 字段的 UX 回归测试。"""

from __future__ import annotations

import os
import sys
import unittest.mock as mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_detect_environment_includes_toolbox_addin_flag(monkeypatch):
    """enhancements.solidworks 应含 toolbox_addin_enabled 字段。"""
    # patch detect_solidworks 返回带 addin=True 的 SwInfo
    from adapters.solidworks import sw_detect

    sw_detect._reset_cache()
    fake_info = sw_detect.SwInfo(
        installed=True,
        version_year=2024,
        version="2024.0",
        pywin32_available=True,
        com_available=True,
        toolbox_addin_enabled=True,
    )
    monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)

    # 动态 import check_env（它位于 tools/ 下，需要 sys.path 支持）
    check_env_path = os.path.join(
        os.path.dirname(__file__), "..", "tools", "hybrid_render", "check_env.py"
    )
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_env", check_env_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    result = mod.detect_environment()
    sw_enh = result.get("enhancements", {}).get("solidworks", {})
    assert "toolbox_addin_enabled" in sw_enh
    assert sw_enh["toolbox_addin_enabled"] is True
```

- [ ] **Step 50：** 运行：

```bash
python -m pytest tests/test_check_env_sw.py -v
```

预期：PASS。

- [ ] **Step 51：** commit

```bash
git add tools/hybrid_render/check_env.py tests/test_check_env_sw.py
git commit -m "feat(sw-b): env-check 展示 toolbox_addin_enabled + 勾选指引（决策 #13）"
```

---

## Task 8：Part 2a 收尾 — 全量测试 + ruff + 代码审查

**Files:** 无新改动，仅 QA。

### 8.1 全量回归

- [ ] **Step 52：** 运行所有 SW 相关测试：

```bash
python -m pytest tests/ -k "sw_ or test_sw or check_env" -v
```

预期：全绿；Part 1 103 + Part 2a 新增（~10+ 项）总计 ≥ 113。

- [ ] **Step 53：** 运行关键非 SW 测试确保无副作用：

```bash
python -m pytest tests/test_parts_resolver.py -v 2>&1 | tail -15
```

预期：parts_resolver 既有测试通过状态不变。

### 8.2 Ruff

- [ ] **Step 54：** Lint：

```bash
python -m ruff check adapters/solidworks/ adapters/parts/sw_toolbox_adapter.py parts_resolver.py tests/test_sw_com_session_lifecycle.py tests/test_sw_toolbox_adapter_registration.py tests/test_check_env_sw.py tools/hybrid_render/check_env.py
```

预期："All checks passed!"。有 error 则当场修。

- [ ] **Step 55：** Format：

```bash
python -m ruff format adapters/solidworks/ adapters/parts/sw_toolbox_adapter.py parts_resolver.py tests/test_sw_com_session_lifecycle.py tests/test_sw_toolbox_adapter_registration.py tests/test_check_env_sw.py tools/hybrid_render/check_env.py
```

若有 reformat 则 commit：

```bash
git add -u
git commit -m "style(sw-b): ruff format Part 2a 收尾"
```

### 8.3 Code review

- [ ] **Step 56：** 用 `superpowers:requesting-code-review` 做审查：

```
BASE_SHA = Part 2a 起点（Part 1 最后的 a8feda6 "style(sw-b): ruff format 收尾"）
HEAD_SHA = git rev-parse HEAD
```

派 code-reviewer subagent：

- WHAT_WAS_IMPLEMENTED: Phase SW-B Part 2a — SwComSession 生命周期（start/restart/idle shutdown + threading model doc）+ parts_resolver 注册 SwToolboxAdapter + yaml 配置段 + env-check UX
- PLAN_OR_REQUIREMENTS: `docs/superpowers/plans/2026-04-13-sw-integration-phase-b-part2a.md`
- 重点审查项：
  1. threading model 文档声明的锁规则在代码中是否都落实（`_start_locked`/`_shutdown_locked`/`_maybe_restart_locked`/`_maybe_idle_shutdown_locked` 都有 `assert self._lock.locked()`）
  2. 状态转换顺序（idle shutdown → restart → cold start → convert）有无死循环/漏状态
  3. `parts_library.default.yaml` 浅覆盖陷阱警告是否足够醒目（决策 #6.1）
  4. env-check 的 UX 在各种组合下（Path A + Path B + addin）是否都有清晰输出

- [ ] **Step 57：** 按 review 结果修改（如有 Important 问题），每个修复走 TDD。

- [ ] **Step 58：** 更新 memory `C:\Users\<user>\.claude\projects\D--Work-cad-spec-gen\memory\solidworks_asset_extraction.md`：

  - 在 "进度" 区块把 "Phase SW-B Part 2（编排/接入）: 未开始" 改成三行：
    - `Phase SW-B Part 2a（Session Part 2 + 接入 + env-check）: 已完成 ✅ — Tasks 0-8 全绿`
    - `Phase SW-B Part 2b（sw-warmup + 集成测试 + min_score 校准）: 未开始`
    - `Phase SW-B Part 2c（SW-B0 spike + real COM 验收 + packaging + 文档）: 未开始`
  - 把 "How to apply" 最后一段改为：`下一步是 superpowers:writing-plans 写 Phase SW-B Part 2b 实施计划（覆盖 SW-B7 sw-warmup CLI + SW-B8 端到端 mocked 集成测试 + min_score 校准）`
  - 同步更新 `MEMORY.md` 索引条目 hook 为：`SW-A + SW-B Part 1/2a 完成，下一步 writing-plans Part 2b`

- [ ] **Step 59：** Part 2a 最终 commit（若 review 后有修改）：

```bash
git add -u
git commit -m "fix(sw-b): Part 2a code review 修复"
```

---

## 交付物（Part 2a 完成态）

1. **SwComSession Part 2 生命周期完整**：start / convert 自动 start / 50 次 restart / idle shutdown，全在 `_lock` 内 in-band 调度，零后台线程
2. **Threading model 文档**：`docs/design/sw-com-session-threading-model.md`，Part 2b/2c 开发依此为准
3. **default_resolver 挂载 SwToolboxAdapter**：yaml 配置自动注入，无 SW 环境下 `is_available()→False` 静默略过
4. **parts_library.default.yaml solidworks_toolbox 段**：GB 高优先级 + ISO/DIN 兜底，`token_weights`/`size_patterns`/`com` 按 spec §6
5. **env-check 对 Add-In 未启用有明确 UX**：打印 Tools → Add-Ins 勾选路径

## 后续交付（Part 2b 范围）

- SW-B7: `cad_pipeline.py` 新增 `sw-warmup` 子命令（BOM / standard / all / dry-run / overwrite / 进程锁）
- SW-B8: `demo_bom.csv` 扩到 ≥ 15 行 + `test_sw_toolbox_integration.py` 端到端 mocked + 覆盖率 regression + min_score 校准子任务
- Part 2b 完成后，Part 2c 处理 SW-B0 spike 补课 + SW-B9 `@requires_solidworks` 真实 COM 验收 + SW-B10 pyproject optional-deps + sw-inspect + 文档
