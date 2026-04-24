# B3 — sldprt→STEP 转换流水线修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 sw_convert_worker（DispatchEx/FrameState/CloseDoc）、在 sw_warmup preflight 加 SW 进程检测、新增 `--smoke-test` 单件验收命令。

**Architecture:** 三个独立改动点：(1) `sw_convert_worker.py` worker subprocess 内 COM 调用修正；(2) `tools/sw_warmup.py` 前置检查加 psutil 进程探测；(3) `tools/sw_warmup.py` 新增 `_run_smoke_test` + `cad_pipeline.py` argparse 新增 `--smoke-test` 标志。全部通过现有 monkeypatch 测试基础设施覆盖，无真实 SW 依赖。

**Tech Stack:** Python 3.11+、pywin32（mock）、psutil≥5.9、pytest + monkeypatch

---

## 文件清单

| 操作 | 文件 |
|------|------|
| Modify | `adapters/solidworks/sw_convert_worker.py` |
| Modify | `tests/test_sw_convert_worker.py` |
| Modify | `tools/sw_warmup.py` |
| Modify | `tests/test_sw_warmup_orchestration.py` |
| Modify | `cad_pipeline.py` |

---

## Task 0：新建功能分支

**Files:**
- （无文件修改）

- [ ] **Step 1：新建并切换到功能分支**

```bash
git checkout -b feat/b3-sldprt-step-pipeline
```

Expected: `Switched to a new branch 'feat/b3-sldprt-step-pipeline'`

---

## Task 1：worker 修复 — DispatchEx + FrameState + CloseDoc

**Files:**
- Modify: `adapters/solidworks/sw_convert_worker.py:33-57`
- Modify: `tests/test_sw_convert_worker.py:34-63`

### 背景

`sw_convert_worker.py` 的 `_convert` 函数有三处需修复：
1. `Dispatch` → `DispatchEx`（强制新 COM 实例，避免竞争）
2. `app.FrameState = 0`（抑制 Toolbox 弹窗）
3. `app.CloseDoc(model.GetTitle())` → `app.CloseDoc(model.GetPathName())`（修 TypeError）

同时，测试辅助方法 `_patch_com` patch 的是 `Dispatch`，改 `DispatchEx` 后需同步更新，否则现有 6 个测试全部失败。

- [ ] **Step 1：先更新 `_patch_com` helper（使现有测试对 DispatchEx 敏感）**

打开 `tests/test_sw_convert_worker.py`，将 `_patch_com` 方法整体替换为：

```python
def _patch_com(self, monkeypatch, *, dispatch_return=None, dispatch_raises=None):
    """安装 pythoncom + win32com.client 的 fake 模块。返回 fake_app 给测试控制 side effects。"""
    fake_pythoncom = mock.MagicMock()
    fake_pythoncom.VT_BYREF = 0x4000
    fake_pythoncom.VT_I4 = 3
    fake_pythoncom.VT_DISPATCH = 9

    fake_win32com_client = mock.MagicMock()

    if dispatch_raises is not None:
        fake_win32com_client.DispatchEx.side_effect = dispatch_raises
    else:
        fake_app = dispatch_return or mock.MagicMock()
        fake_win32com_client.DispatchEx.return_value = fake_app

    def fake_variant(vartype, initial):
        v = mock.MagicMock()
        v.value = initial
        return v

    fake_win32com_client.VARIANT.side_effect = fake_variant

    monkeypatch.setitem(sys.modules, "pythoncom", fake_pythoncom)
    monkeypatch.setitem(sys.modules, "win32com.client", fake_win32com_client)
    return (
        fake_win32com_client.DispatchEx.return_value
        if dispatch_raises is None
        else None
    )
```

- [ ] **Step 2：运行现有测试，确认全部失败（测试现在期待 DispatchEx，但 worker 还用 Dispatch）**

```bash
python -m pytest tests/test_sw_convert_worker.py -v 2>&1 | tail -20
```

Expected: 多个 FAILED（`Dispatch` 不再被 patch，调用真实模块 → ImportError 或断言失败）

- [ ] **Step 3：新增 CloseDoc + FrameState 测试（先写红测试）**

在 `tests/test_sw_convert_worker.py` 的 `TestWorkerConvert` 类末尾追加：

```python
def test_closedoc_uses_getpathname(self, monkeypatch):
    """CloseDoc 应调用 model.GetPathName()，不调 model.GetTitle()。"""
    from adapters.solidworks import sw_convert_worker

    fake_app = mock.MagicMock()
    model = mock.MagicMock()
    model.GetPathName.return_value = "C:/SOLIDWORKS Data/part.sldprt"
    fake_app.OpenDoc6.return_value = model
    model.Extension.SaveAs3.return_value = True
    self._patch_com(monkeypatch, dispatch_return=fake_app)

    rc = sw_convert_worker._convert("in.sldprt", "out.tmp.step")
    assert rc == 0
    fake_app.CloseDoc.assert_called_once_with("C:/SOLIDWORKS Data/part.sldprt")

def test_framestate_set_to_zero(self, monkeypatch):
    """FrameState=0（swWindowMinimized）必须在 OpenDoc6 前设置。"""
    from adapters.solidworks import sw_convert_worker

    fake_app = mock.MagicMock()
    model = mock.MagicMock()
    fake_app.OpenDoc6.return_value = model
    model.Extension.SaveAs3.return_value = True
    self._patch_com(monkeypatch, dispatch_return=fake_app)

    rc = sw_convert_worker._convert("in.sldprt", "out.tmp.step")
    assert rc == 0
    assert fake_app.FrameState == 0
```

- [ ] **Step 4：运行新测试，确认红**

```bash
python -m pytest tests/test_sw_convert_worker.py::TestWorkerConvert::test_closedoc_uses_getpathname tests/test_sw_convert_worker.py::TestWorkerConvert::test_framestate_set_to_zero -v
```

Expected: FAILED

- [ ] **Step 5：修改 `adapters/solidworks/sw_convert_worker.py`**

将文件中 `_convert` 函数的前半段（import + dispatch + app 配置 + closedoc 那行）按以下改动修改：

**改动 1 — 顶部 import（第 34 行附近）：**
```python
# 旧
from win32com.client import VARIANT, Dispatch
# 新
from win32com.client import VARIANT, DispatchEx
```

**改动 2 — Dispatch 调用（第 43 行附近）：**
```python
# 旧
app = Dispatch("SldWorks.Application")
# 新
app = DispatchEx("SldWorks.Application")
```

**改动 3 — app 配置块（第 47-49 行附近），在 `app.UserControl = False` 后插入一行：**
```python
app.Visible = False
app.UserControl = False
app.FrameState = 0  # swWindowMinimized，抑制 Toolbox 选配置弹窗
```

**改动 4 — CloseDoc 调用（第 85 行附近）：**
```python
# 旧
app.CloseDoc(model.GetTitle())
# 新
app.CloseDoc(model.GetPathName())
```

- [ ] **Step 6：运行全部 worker 测试，确认绿**

```bash
python -m pytest tests/test_sw_convert_worker.py -v
```

Expected: 8 passed（原 6 + 新 2）

- [ ] **Step 7：提交**

```bash
git add adapters/solidworks/sw_convert_worker.py tests/test_sw_convert_worker.py
git commit -m "fix(b3): worker — DispatchEx + FrameState=0 + CloseDoc GetPathName"
```

---

## Task 2：sw_warmup preflight — SW 进程检测

**Files:**
- Modify: `tools/sw_warmup.py:237-258`（`_check_preflight` 函数末尾）
- Modify: `tests/test_sw_warmup_orchestration.py`

### 背景

`_check_preflight()` 当前在"toolbox_dir 检测"后直接 `return True, ""`。需要在此之前插入 psutil 进程检测：若 `SLDWORKS.EXE` 不在进程列表，提前返回 `(False, "SolidWorks 未运行…")`。

- [ ] **Step 1：写失败测试——SW 未运行**

在 `tests/test_sw_warmup_orchestration.py` 的 `TestPreflight` 类末尾追加：

```python
def test_returns_2_when_sw_not_running(self, tmp_path, monkeypatch, capsys):
    """psutil 未找到 SLDWORKS.EXE → preflight 失败 → exit 2 + 含'SolidWorks 未运行'。"""
    import psutil
    from tools import sw_warmup as mod
    from adapters.solidworks import sw_detect

    sw_detect._reset_cache()
    fake_info = sw_detect.SwInfo(
        installed=True,
        version_year=2024,
        pywin32_available=True,
        toolbox_dir=str(tmp_path),
    )
    monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
    monkeypatch.setattr(mod, "_default_lock_path", lambda: tmp_path / "sw_warmup.lock")

    # 模拟进程列表中无 SolidWorks
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: iter([]))

    rc = mod.run_sw_warmup(_make_args(standard="GB"))
    captured = capsys.readouterr()
    assert rc == 2
    assert "SolidWorks 未运行" in captured.out

def test_preflight_passes_when_sw_running(self, tmp_path, monkeypatch, capsys):
    """psutil 找到 SLDWORKS.EXE → preflight 通过（后续流程继续）。"""
    import pathlib
    import psutil
    import unittest.mock as mock
    from tools import sw_warmup as mod
    from adapters.solidworks import sw_detect, sw_toolbox_catalog

    sw_detect._reset_cache()
    fake_info = sw_detect.SwInfo(
        installed=True,
        version_year=2024,
        pywin32_available=True,
        toolbox_dir=str(tmp_path),
        toolbox_addin_enabled=False,
    )
    monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
    monkeypatch.setattr(mod, "_default_lock_path", lambda: tmp_path / "sw_warmup.lock")

    # 模拟 SLDWORKS.EXE 在运行
    fake_proc = mock.MagicMock()
    fake_proc.name.return_value = "SLDWORKS.EXE"
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: iter([fake_proc]))

    # 让 catalog 函数全部返回安全值，避免 tmp_path 下文件不存在引发错误
    monkeypatch.setattr(
        sw_toolbox_catalog, "get_toolbox_index_path", lambda cfg: tmp_path / "index.json"
    )
    monkeypatch.setattr(
        sw_toolbox_catalog, "get_toolbox_cache_root", lambda cfg: tmp_path / "cache"
    )
    monkeypatch.setattr(
        sw_toolbox_catalog, "load_toolbox_index", lambda *a, **kw: {"standards": {}}
    )

    rc = mod.run_sw_warmup(_make_args(standard="GB"))
    # preflight 通过后 targets 为空 → exit 0
    assert rc == 0
    captured = capsys.readouterr()
    assert "SolidWorks 未运行" not in captured.out
```

- [ ] **Step 2：运行新测试，确认红**

```bash
python -m pytest tests/test_sw_warmup_orchestration.py::TestPreflight::test_returns_2_when_sw_not_running tests/test_sw_warmup_orchestration.py::TestPreflight::test_preflight_passes_when_sw_running -v
```

Expected: FAILED

- [ ] **Step 3：修改 `tools/sw_warmup.py` 的 `_check_preflight`**

在 `_check_preflight()` 函数末尾（`if not info.toolbox_dir:` 块之后、`return True, ""` 之前）插入：

```python
import psutil  # 局部 import，与 msvcrt/fcntl 惯例一致
sw_running = any(
    p.name().upper() == "SLDWORKS.EXE"
    for p in psutil.process_iter(["name"])
)
if not sw_running:
    return False, (
        "SolidWorks 未运行；请先打开 SolidWorks，"
        "再运行 sw-warmup（COM 转换需要 SW 进程已就绪）"
    )
```

- [ ] **Step 4：运行 Task 2 测试 + 原有 preflight 测试，确认全绿**

```bash
python -m pytest tests/test_sw_warmup_orchestration.py::TestPreflight -v
```

Expected: 全部 passed（含原有 `test_returns_2_when_sw_not_installed`、`test_addin_disabled_warns_but_continues` 等）

- [ ] **Step 5：提交**

```bash
git add tools/sw_warmup.py tests/test_sw_warmup_orchestration.py
git commit -m "feat(b3): warmup preflight — SW 进程检测（psutil SLDWORKS.EXE）"
```

---

## Task 3：`--smoke-test` 标志 + `_run_smoke_test`

**Files:**
- Modify: `cad_pipeline.py:2999`（argparse，在 `--overwrite` 后插入）
- Modify: `tools/sw_warmup.py`（新增 `_run_smoke_test` + 修改 `run_sw_warmup`）
- Modify: `tests/test_sw_warmup_orchestration.py`（新增 `_make_args` 的 `smoke_test` 字段 + 新测试类）

### 背景

`sw-warmup --smoke-test` 跑单件验收：取 GB/bearing 第一个件 → convert → 检查 STEP 有效性 → 清理临时文件。锁路径和 preflight 走正常流程。`run_sw_warmup` 在持锁后、进入 `_run_warmup_locked` 前检测 `args.smoke_test` 标志。

- [ ] **Step 1：更新 `_make_args` helper 加入 `smoke_test=False`**

在 `tests/test_sw_warmup_orchestration.py` 中找到 `_make_args` 函数：
```python
def _make_args(**overrides) -> argparse.Namespace:
    base = dict(standard=None, bom=None, all=False, dry_run=False, overwrite=False)
```
改为：
```python
def _make_args(**overrides) -> argparse.Namespace:
    base = dict(standard=None, bom=None, all=False, dry_run=False, overwrite=False, smoke_test=False)
```

- [ ] **Step 2：写失败测试——smoke-test PASS 路径**

在 `tests/test_sw_warmup_orchestration.py` 末尾新增 `TestSmokeTest` 类：

```python
class TestSmokeTest:
    """_run_smoke_test 的单元测试；全部 mock，不依赖真实 SW。"""

    def _setup_preflight_mocks(self, monkeypatch, tmp_path):
        """共用前置 mock：SW 已安装 + SW 进程运行中。"""
        import psutil
        import unittest.mock as mock
        from adapters.solidworks import sw_detect

        sw_detect._reset_cache()
        fake_info = sw_detect.SwInfo(
            installed=True,
            version_year=2024,
            pywin32_available=True,
            toolbox_dir=str(tmp_path),
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)

        fake_proc = mock.MagicMock()
        fake_proc.name.return_value = "SLDWORKS.EXE"
        monkeypatch.setattr(psutil, "process_iter", lambda attrs: iter([fake_proc]))

    def test_smoke_test_pass_prints_pass_and_returns_0(
        self, tmp_path, monkeypatch, capsys
    ):
        import unittest.mock as mock
        from tools import sw_warmup as mod
        from adapters.solidworks import sw_toolbox_catalog, sw_com_session

        self._setup_preflight_mocks(monkeypatch, tmp_path)
        monkeypatch.setattr(mod, "_default_lock_path", lambda: tmp_path / "sw_warmup.lock")

        # 构造一个有 GB/bearing 件的 fake index
        fake_part = mock.MagicMock()
        fake_part.sldprt_path = str(tmp_path / "fake.sldprt")
        monkeypatch.setattr(
            sw_toolbox_catalog,
            "load_toolbox_index",
            lambda *a, **kw: {"standards": {"GB": {"bearing": [fake_part]}}},
        )
        monkeypatch.setattr(sw_toolbox_catalog, "get_toolbox_index_path", lambda cfg: tmp_path / "index.json")

        # mock session：convert 成功，并在 tmp 目录创建一个假 STEP 文件
        fake_session = mock.MagicMock()

        def fake_convert(sldprt, step_out):
            from pathlib import Path
            Path(step_out).write_bytes(b"ISO-10303-21;\n" + b"x" * 2000)
            return True

        fake_session.convert_sldprt_to_step.side_effect = fake_convert
        monkeypatch.setattr(sw_com_session, "get_session", lambda: fake_session)

        rc = mod.run_sw_warmup(_make_args(smoke_test=True))
        captured = capsys.readouterr()
        assert rc == 0
        assert "smoke-test PASS" in captured.out

    def test_smoke_test_fail_prints_fail_and_returns_2(
        self, tmp_path, monkeypatch, capsys
    ):
        import unittest.mock as mock
        from tools import sw_warmup as mod
        from adapters.solidworks import sw_toolbox_catalog, sw_com_session

        self._setup_preflight_mocks(monkeypatch, tmp_path)
        monkeypatch.setattr(mod, "_default_lock_path", lambda: tmp_path / "sw_warmup.lock")

        fake_part = mock.MagicMock()
        fake_part.sldprt_path = str(tmp_path / "fake.sldprt")
        monkeypatch.setattr(
            sw_toolbox_catalog,
            "load_toolbox_index",
            lambda *a, **kw: {"standards": {"GB": {"bearing": [fake_part]}}},
        )
        monkeypatch.setattr(sw_toolbox_catalog, "get_toolbox_index_path", lambda cfg: tmp_path / "index.json")

        fake_session = mock.MagicMock()
        fake_session.convert_sldprt_to_step.return_value = False
        fake_session.last_convert_diagnostics = {"stderr_tail": "OpenDoc6 errors=256"}
        monkeypatch.setattr(sw_com_session, "get_session", lambda: fake_session)

        rc = mod.run_sw_warmup(_make_args(smoke_test=True))
        captured = capsys.readouterr()
        assert rc == 2
        assert "smoke-test FAIL" in captured.out

    def test_smoke_test_fail_when_no_bearing_parts(
        self, tmp_path, monkeypatch, capsys
    ):
        import unittest.mock as mock
        from tools import sw_warmup as mod
        from adapters.solidworks import sw_toolbox_catalog

        self._setup_preflight_mocks(monkeypatch, tmp_path)
        monkeypatch.setattr(mod, "_default_lock_path", lambda: tmp_path / "sw_warmup.lock")

        # index 里无 GB/bearing
        monkeypatch.setattr(
            sw_toolbox_catalog,
            "load_toolbox_index",
            lambda *a, **kw: {"standards": {}},
        )
        monkeypatch.setattr(sw_toolbox_catalog, "get_toolbox_index_path", lambda cfg: tmp_path / "index.json")

        rc = mod.run_sw_warmup(_make_args(smoke_test=True))
        captured = capsys.readouterr()
        assert rc == 2
        assert "smoke-test FAIL" in captured.out
```

- [ ] **Step 3：运行新测试，确认红**

```bash
python -m pytest tests/test_sw_warmup_orchestration.py::TestSmokeTest -v
```

Expected: FAILED（`_run_smoke_test` 不存在，`smoke_test` attr 未被 run_sw_warmup 识别）

- [ ] **Step 4：在 `tools/sw_warmup.py` 中新增 `_run_smoke_test` 函数**

在 `_run_warmup_locked` 函数**之前**插入（文件第 341 行附近）：

```python
def _run_smoke_test(args) -> int:
    """单件 smoke test：取 GB/bearing 第一个件做转换验收（spec B3 §5.3）。"""
    import shutil
    import tempfile
    from pathlib import Path

    from adapters.solidworks import sw_toolbox_catalog
    from adapters.solidworks.sw_com_session import get_session
    from adapters.solidworks.sw_detect import detect_solidworks
    from parts_resolver import load_registry

    ok, reason = _check_preflight()
    if not ok:
        _print_preflight_failure(reason)
        return 2

    info = detect_solidworks()
    registry = load_registry()
    sw_cfg = registry.get("solidworks_toolbox", {})
    index_path = sw_toolbox_catalog.get_toolbox_index_path(sw_cfg)
    index = sw_toolbox_catalog.load_toolbox_index(index_path, Path(info.toolbox_dir))

    bearing_parts = index.get("standards", {}).get("GB", {}).get("bearing", [])
    if not bearing_parts:
        print("[sw-warmup] smoke-test FAIL — Toolbox index 无 GB/bearing 件")
        return 2

    part = bearing_parts[0]
    tmp_dir = Path(tempfile.mkdtemp(prefix="sw_smoke_"))
    step_out = str(tmp_dir / "smoke_test.step")

    try:
        session = get_session()
        success = session.convert_sldprt_to_step(part.sldprt_path, step_out)
        if success:
            size_kb = Path(step_out).stat().st_size // 1024
            print(f"[sw-warmup] smoke-test PASS — STEP 文件 {size_kb}KB")
            return 0
        else:
            stderr_tail = (session.last_convert_diagnostics or {}).get(
                "stderr_tail", ""
            )
            print(f"[sw-warmup] smoke-test FAIL — {stderr_tail}")
            return 2
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
```

- [ ] **Step 5：修改 `run_sw_warmup` 加入 smoke_test 分叉**

在 `run_sw_warmup` 函数的 `with acquire_warmup_lock(...)` 块内，`_run_warmup_locked(args)` 调用前插入判断：

```python
def run_sw_warmup(args) -> int:
    try:
        with acquire_warmup_lock(_default_lock_path()):
            if getattr(args, "smoke_test", False):
                return _run_smoke_test(args)
            return _run_warmup_locked(args)
    except WarmupLockContentionError as e:
        print(f"[sw-warmup] {e}")
        return 3
    except RuntimeError as e:
        print(f"[sw-warmup] {e}")
        return 1
```

- [ ] **Step 6：在 `cad_pipeline.py` argparse 块加 `--smoke-test`**

找到 `cad_pipeline.py` 第 2999 行（`p_sw_warmup.add_argument("--overwrite", ...)`）后插入：

```python
p_sw_warmup.add_argument(
    "--smoke-test",
    action="store_true",
    help="转换单件验收（GB/bearing 第一个件），exit 0=PASS / exit 2=FAIL",
)
```

- [ ] **Step 7：运行 Task 3 全部测试，确认绿**

```bash
python -m pytest tests/test_sw_warmup_orchestration.py::TestSmokeTest -v
```

Expected: 3 passed

- [ ] **Step 8：运行完整 warmup 测试套件，确认无回归**

```bash
python -m pytest tests/test_sw_warmup_orchestration.py tests/test_sw_warmup_bom_reader.py tests/test_sw_warmup_lock.py -v 2>&1 | tail -20
```

Expected: 全部 passed

- [ ] **Step 9：提交**

```bash
git add tools/sw_warmup.py tests/test_sw_warmup_orchestration.py cad_pipeline.py
git commit -m "feat(b3): warmup --smoke-test 单件验收 + _run_smoke_test"
```

---

## Task 4：全套测试 + 本机手工验收

**Files:**
- （无文件修改）

- [ ] **Step 1：运行全套测试**

```bash
python -m pytest tests/test_sw_convert_worker.py tests/test_sw_warmup_orchestration.py tests/test_sw_warmup_bom_reader.py tests/test_sw_warmup_lock.py -v 2>&1 | tail -30
```

Expected: 全部 passed，无 FAILED

- [ ] **Step 2：本机手工验收——smoke-test（SW 已开启）**

确保 SolidWorks 2024 已打开，然后：

```bash
python cad_pipeline.py sw-warmup --smoke-test
```

Expected 输出（含）：
```
[sw-warmup] smoke-test PASS — STEP 文件 <N>KB
```
Exit code：`echo $?` → `0`

- [ ] **Step 3：本机手工验收——SW 未运行时提示**

关闭 SolidWorks，然后：

```bash
python cad_pipeline.py sw-warmup --smoke-test
```

Expected 输出（含）：
```
[sw-warmup] 前置检查失败：SolidWorks 未运行；请先打开 SolidWorks，再运行 sw-warmup
```
Exit code：`echo $?` → `2`

---

## Task 5：PR + CI + merge + v2.16.0

**Files:**
- （无文件修改）

- [ ] **Step 1：推送分支**

```bash
git push -u origin feat/b3-sldprt-step-pipeline
```

- [ ] **Step 2：创建 PR**

```bash
gh pr create \
  --title "feat(b3): sldprt→STEP 流水线修复（DispatchEx/FrameState/CloseDoc/SW进程检测/smoke-test）" \
  --body "## 改动
- worker: Dispatch→DispatchEx + FrameState=0 + CloseDoc GetPathName 修 TypeError
- warmup preflight: psutil 检测 SLDWORKS.EXE，未运行时 exit 2 + 友好提示
- warmup: --smoke-test 单件验收命令（GB/bearing，exit 0=PASS/exit 2=FAIL）

## 测试
- 新增 8 个单元测试（worker 2 + preflight 2 + smoke-test 3 + _make_args 无感知）
- 全套 warmup + worker 测试通过
- 本机手工验收 sw-warmup --smoke-test exit 0 ✓

🤖 Generated with Claude Code"
```

- [ ] **Step 3：等待 CI 全绿**

```bash
gh pr checks
```

Expected: 全部 pass（regression + Ubuntu/Windows × 3.10/3.11/3.12）

- [ ] **Step 4：合并**

```bash
gh pr merge --merge
```

- [ ] **Step 5：拉取 main 并发布 v2.16.0**

```bash
git checkout main && git pull origin main
gh release create v2.16.0 \
  --title "v2.16.0 — B3 sldprt→STEP 转换流水线修复" \
  --notes "## 新功能
- sw-warmup --smoke-test：单件验收命令，exit 0=PASS
- SW 未运行时友好提示（preflight exit 2）

## 修复
- sw_convert_worker：DispatchEx 强制新 COM 实例
- sw_convert_worker：FrameState=0 抑制 Toolbox 弹窗
- sw_convert_worker：CloseDoc 改用 GetPathName()，修 TypeError"
```
