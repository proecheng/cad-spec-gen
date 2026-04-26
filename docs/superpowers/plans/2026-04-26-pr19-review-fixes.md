# PR #19 review fixes — C-1 + I-1 修复 plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans。步骤用 checkbox (`- [ ]`) 跟踪。

**Goal:** 修复 PR #19 self-review 发现的 1 Critical (C-1) + 1 Important (I-1) blocker；其余 issue 推迟到 follow-up。

**Architecture:**
- C-1：`_run_batch_mode` 当前每文件 boot SW（`_list_configs_returning` 内含完整 CoInit→DispatchEx→ExitApp→CoUninitialize）。重构：抽 `_open_doc_get_configs(app, path)` 共享 primitive，单件 / batch 各自管 lifecycle，batch 模式真正一次 boot loop N 件。
- I-1：cache 写读两端路径键不一致（写 `prewarm_config_lists` 用 raw、读 `_list_configs_via_com` 用 `Path.resolve()`、miss 检查 `_config_list_entry_valid` 用 raw）。引入 `_normalize_sldprt_key()` 单点 helper，三处替换 + 写时存归一化 key。

**Tech Stack:** Python 3.11 / pytest / unittest.mock / monkeypatch (sys.modules fake)

**修改/创建文件总览:**
- 修改 `adapters/solidworks/sw_list_configs_worker.py` — 抽 `_open_doc_get_configs`，重写 `_run_batch_mode` 单 lifecycle
- 修改 `adapters/solidworks/sw_config_broker.py` — 加 `_normalize_sldprt_key` + 三处替换
- 新增测试 `tests/test_sw_list_configs_worker.py` — batch 真单 boot SW 计数验证
- 新增测试 `tests/test_sw_config_broker.py` — prewarm 路径归一化 round-trip
- 修改 `docs/superpowers/specs/2026-04-26-sw-toolbox-config-list-persistent-cache.md` — follow-up 已知限制登记（I-2/I-3/I-4/M-1..M-7）

---

## Task 0：先验环境快查（防 plan drift）

**Files:** 不改文件

- [ ] **Step 1：grep 验证 worker 内部 boot 操作位置**

```bash
grep -n "CoInitialize\|DispatchEx\|ExitApp\|CoUninitialize" \
  adapters/solidworks/sw_list_configs_worker.py
```

预期输出（至少）：
```
32:    pythoncom.CoInitialize()
34:        app = DispatchEx("SldWorks.Application")
59:                app.ExitApp()
63:        pythoncom.CoUninitialize()
```

确认 4 个 boot 操作都在 `_list_configs_returning` 内部 → batch 重构必须把它们提到 batch 模式自己的 wrapper 里。

- [ ] **Step 2：grep 验证 broker 路径键三处用法**

```bash
grep -n "Path(.*).resolve\|cache\\[.entries.\\]\|_config_list_entry_valid" \
  adapters/solidworks/sw_config_broker.py
```

预期看到（行号近似）：
- `460: abs_path = str(Path(sldprt_path).resolve())`（reader）
- `558-561: miss = [p for p in sldprt_list if not _config_list_entry_valid(cache, p)]`（writer miss check）
- `595: cache["entries"][sldprt_path] = ...`（writer 写入）

确认三处不一致 → 后续替换点。

---

## Task 1：I-1 路径归一化（cheap，先做隔离 risk）

**Files:**
- 修改：`adapters/solidworks/sw_config_broker.py:448-602`
- 测试：`tests/test_sw_config_broker.py`（追加 1 测试）

- [ ] **Step 1：写失败测试 — prewarm 用 mixed-slash 路径写 cache，reader 用 normalized 路径读 → 命中**

追加到 `tests/test_sw_config_broker.py` 末尾（参考现有 `class TestPrewarmConfigLists` 的 fixture 用法）：

```python
def test_prewarm_writes_normalized_key_so_reader_hits(
    monkeypatch, tmp_project_dir, isolate_cad_spec_gen_home,
):
    """I-1 regression：prewarm 用 mixed-slash 路径 → cache key 必须归一化 →
    `_list_configs_via_com` 用同物理文件的不同字面值（forward-slash / 反向）也命中 cache，
    不再 spawn fallback subprocess。
    """
    import json as _json
    import subprocess as _sp
    from adapters.solidworks import sw_config_broker as broker

    sldprt = tmp_project_dir / "p1.SLDPRT"
    sldprt.write_text("dummy")
    # 故意用 forward-slash 字面值（Windows 上与 resolve() 后的反斜杠不同）
    forward_slash_path = sldprt.as_posix()

    # mock detect_solidworks 返合理 envelope
    class _Info:
        version_year = 2024
        toolbox_dir = "C:\\\\sw\\\\toolbox"
    monkeypatch.setattr(
        "adapters.solidworks.sw_detect.detect_solidworks",
        lambda: _Info(),
    )

    # mock subprocess.run：batch 模式返一条假 result
    def _fake_run(cmd, **kwargs):
        if "--batch" in cmd:
            results = [{"path": forward_slash_path, "configs": ["6201"]}]
            return _sp.CompletedProcess(
                cmd, 0, stdout=_json.dumps(results).encode(), stderr=b"",
            )
        # 单件 fallback 不应被调（该断言在 reader 阶段验证）
        raise AssertionError(f"unexpected single-file spawn: {cmd}")

    monkeypatch.setattr(broker.subprocess, "run", _fake_run)

    broker._CONFIG_LIST_CACHE.clear()
    broker.prewarm_config_lists([forward_slash_path])

    # reader 用 raw forward-slash → 必须命中 cache（不抛 AssertionError）
    configs = broker._list_configs_via_com(forward_slash_path)
    assert configs == ["6201"]

    # 第二次：reader 用反斜杠版同一文件 → 也必须命中（key 归一化）
    backslash_path = str(sldprt)
    broker._CONFIG_LIST_CACHE.clear()  # 清 L2 强制走 L1
    configs2 = broker._list_configs_via_com(backslash_path)
    assert configs2 == ["6201"]
```

- [ ] **Step 2：跑测试确认 RED**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::test_prewarm_writes_normalized_key_so_reader_hits -v
```

预期：FAIL（第二次 reader spawn fallback → AssertionError；或 cache miss）

- [ ] **Step 3：实现 `_normalize_sldprt_key` helper + 三处替换**

在 `adapters/solidworks/sw_config_broker.py` line 445 (`_PROJECT_ROOT_FOR_WORKER` 之后) 加 helper：

```python
def _normalize_sldprt_key(sldprt_path: str) -> str:
    """归一化 sldprt 路径为 cache key（spec §3.1 issue I-1 修复）。

    确保 prewarm 写入与 _list_configs_via_com 读取使用同一 key 字面值，
    防 mixed slash / 未 resolve 路径导致 silent cache miss。
    """
    return str(Path(sldprt_path).resolve())
```

替换三处：

1) `_list_configs_via_com` line 460：
```python
    abs_path = _normalize_sldprt_key(sldprt_path)
```

2) `prewarm_config_lists` line 558-561 改为：
```python
    miss = [
        p for p in sldprt_list
        if not cache_mod._config_list_entry_valid(
            cache, _normalize_sldprt_key(p),
        )
    ]
```

3) `prewarm_config_lists` line 588-599 写入循环改为（worker 输出 path 字段不一定归一化，本地 normalize 后存 + 返查 mtime/size 用本地物理路径）：
```python
        for entry in results:
            sldprt_path = entry.get("path", "")
            configs = entry.get("configs", [])
            mtime = cache_mod._stat_mtime(sldprt_path)
            size = cache_mod._stat_size(sldprt_path)
            if mtime is None or size is None:
                continue  # sldprt 文件已删 — 跳过不写
            key = _normalize_sldprt_key(sldprt_path)
            cache["entries"][key] = {
                "mtime": mtime,
                "size": size,
                "configs": configs,
            }
```

注意：`_config_list_entry_valid` 内部也要看 cache `entries` key — 既然外部都传归一化 key，`_config_list_entry_valid` 本身不必改（接收什么 key 就查什么），但要给 caller 文档化"传归一化 key"。在 `sw_config_lists_cache.py` 的 `_config_list_entry_valid` docstring 加一行：

```python
def _config_list_entry_valid(cache: dict, sldprt_path: str) -> bool:
    """检查 cache 中 sldprt_path 对应 entry 是否有效（mtime + size 一致）。

    caller 必须传归一化 key（spec §3.1 issue I-1）：通常是
    `sw_config_broker._normalize_sldprt_key(p)` 的输出。
    """
```

- [ ] **Step 4：跑测试确认 GREEN**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::test_prewarm_writes_normalized_key_so_reader_hits -v
```

预期：PASS。

- [ ] **Step 5：跑邻近测试无 regression**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py tests/test_sw_config_lists_cache.py -v
```

预期：所有 prewarm / cache 相关测试全 PASS（含原 26+ broker 测 + 12+ cache 测）。

- [ ] **Step 6：commit**

```bash
git add adapters/solidworks/sw_config_broker.py adapters/solidworks/sw_config_lists_cache.py tests/test_sw_config_broker.py
git commit -m "fix(sw_config_broker): I-1 cache key 归一化（PR #19 review fix）

reader (_list_configs_via_com) 用 Path.resolve() 而 writer (prewarm) 用 raw
sldprt_path → mixed-slash 路径触发 silent cache miss，prewarm 优化失效。

引入 _normalize_sldprt_key 单点 helper，三处 (reader / miss check / writer)
统一调用，确保写读 key 一致；新加 round-trip 回归测试。"
```

---

## Task 2：C-1 worker batch 真单 boot 重构

**Files:**
- 修改：`adapters/solidworks/sw_list_configs_worker.py:23-122`
- 测试：`tests/test_sw_list_configs_worker.py`（追加 3 测试 + 修改 1 现有 mock 路径）

- [ ] **Step 1：写失败测试 1 — batch 3 件，COM lifecycle 各 1 次**

追加到 `tests/test_sw_list_configs_worker.py` 末尾：

```python
def _make_fake_com_modules(open_doc_fail_paths: set[str] | None = None):
    """构造 fake pythoncom + win32com.client 模块，注入 sys.modules，
    返 (counters dict, app instance) 供测试断言。

    open_doc_fail_paths：模拟 OpenDoc6 失败的 sldprt 路径集合（err_var.value=1）。
    """
    open_doc_fail_paths = open_doc_fail_paths or set()
    counters = {
        "co_init": 0, "co_uninit": 0, "dispatch": 0,
        "exit_app": 0, "open_doc": 0, "close_doc": 0,
    }

    class FakeVariant:
        def __init__(self, *args, **kwargs):
            self.value = 0

    class FakeConfigMgr:
        def __init__(self, configs):
            self._configs = configs
        def GetConfigurationNames(self):
            return self._configs

    class FakeModel:
        def __init__(self, path):
            self._path = path
            # 简单按文件名末位返不同 configs
            self.ConfigurationManager = FakeConfigMgr([f"cfg-{Path(path).stem}"])
        def GetPathName(self):
            return self._path

    class FakeApp:
        Visible = True
        UserControl = True
        FrameState = -1
        def OpenDoc6(self, path, *args):
            counters["open_doc"] += 1
            err_var = args[3] if len(args) >= 4 else None
            if path in open_doc_fail_paths and err_var is not None:
                err_var.value = 1
                return None
            return FakeModel(path)
        def CloseDoc(self, path):
            counters["close_doc"] += 1
        def ExitApp(self):
            counters["exit_app"] += 1

    app_singleton = FakeApp()

    class FakePythoncom:
        VT_BYREF = 0
        VT_I4 = 0
        @staticmethod
        def CoInitialize():
            counters["co_init"] += 1
        @staticmethod
        def CoUninitialize():
            counters["co_uninit"] += 1

    fake_pythoncom_mod = type(sys)("pythoncom")
    fake_pythoncom_mod.VT_BYREF = FakePythoncom.VT_BYREF
    fake_pythoncom_mod.VT_I4 = FakePythoncom.VT_I4
    fake_pythoncom_mod.CoInitialize = FakePythoncom.CoInitialize
    fake_pythoncom_mod.CoUninitialize = FakePythoncom.CoUninitialize

    fake_win32com_mod = type(sys)("win32com")
    fake_win32com_client_mod = type(sys)("win32com.client")
    fake_win32com_client_mod.VARIANT = FakeVariant
    fake_win32com_client_mod.DispatchEx = lambda name: (
        counters.__setitem__("dispatch", counters["dispatch"] + 1),
        app_singleton,
    )[1]
    fake_win32com_mod.client = fake_win32com_client_mod

    return counters, fake_pythoncom_mod, fake_win32com_mod, fake_win32com_client_mod


def test_batch_mode_initializes_com_only_once(monkeypatch, capsys):
    """C-1 regression：batch 3 件 → CoInit/Dispatch/ExitApp/CoUninitialize
    各调 1 次；OpenDoc6 / CloseDoc 各调 3 次。"""
    counters, fake_py, fake_w32, fake_w32_client = _make_fake_com_modules()
    monkeypatch.setitem(sys.modules, "pythoncom", fake_py)
    monkeypatch.setitem(sys.modules, "win32com", fake_w32)
    monkeypatch.setitem(sys.modules, "win32com.client", fake_w32_client)

    from adapters.solidworks import sw_list_configs_worker as w
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps([
            "C:/p1.sldprt", "C:/p2.sldprt", "C:/p3.sldprt",
        ])),
    )

    rc = w.main(["--batch"])
    assert rc == 0

    assert counters["co_init"] == 1, f"CoInitialize 应 1 次，实 {counters['co_init']}"
    assert counters["dispatch"] == 1, f"DispatchEx 应 1 次，实 {counters['dispatch']}"
    assert counters["exit_app"] == 1, f"ExitApp 应 1 次，实 {counters['exit_app']}"
    assert counters["co_uninit"] == 1, f"CoUninitialize 应 1 次，实 {counters['co_uninit']}"
    assert counters["open_doc"] == 3, f"OpenDoc6 应 3 次，实 {counters['open_doc']}"
    assert counters["close_doc"] == 3, f"CloseDoc 应 3 次，实 {counters['close_doc']}"

    # 输出健全性
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert len(parsed) == 3
    assert all("configs" in entry for entry in parsed)
```

- [ ] **Step 2：写失败测试 2 — batch 单件 OpenDoc6 失败不阻其他件 + COM lifecycle 仍单次**

```python
def test_batch_mode_per_file_open_failure_keeps_single_lifecycle(
    monkeypatch, capsys,
):
    """C-1 regression 配套：batch 中某件 OpenDoc6 失败 → 记 configs=[] 跳过 →
    其他件继续；CoInit/ExitApp 仍各 1 次（单 lifecycle 不被 reset）。"""
    counters, fake_py, fake_w32, fake_w32_client = _make_fake_com_modules(
        open_doc_fail_paths={"C:/bad.sldprt"},
    )
    monkeypatch.setitem(sys.modules, "pythoncom", fake_py)
    monkeypatch.setitem(sys.modules, "win32com", fake_w32)
    monkeypatch.setitem(sys.modules, "win32com.client", fake_w32_client)

    from adapters.solidworks import sw_list_configs_worker as w
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps([
            "C:/good1.sldprt", "C:/bad.sldprt", "C:/good2.sldprt",
        ])),
    )

    rc = w.main(["--batch"])
    assert rc == 0
    assert counters["co_init"] == 1
    assert counters["exit_app"] == 1

    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed[0]["configs"] == ["cfg-good1"]
    assert parsed[1]["configs"] == []  # bad 失败
    assert parsed[2]["configs"] == ["cfg-good2"]
```

- [ ] **Step 3：写失败测试 3 — batch 空 list 不 boot SW**

```python
def test_batch_mode_empty_list_skips_com_boot(monkeypatch, capsys):
    """边界：空 batch list → 不 CoInitialize / Dispatch（避免无谓 SW 启动）。"""
    counters, fake_py, fake_w32, fake_w32_client = _make_fake_com_modules()
    monkeypatch.setitem(sys.modules, "pythoncom", fake_py)
    monkeypatch.setitem(sys.modules, "win32com", fake_w32)
    monkeypatch.setitem(sys.modules, "win32com.client", fake_w32_client)

    from adapters.solidworks import sw_list_configs_worker as w
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps([])))

    rc = w.main(["--batch"])
    assert rc == 0
    assert counters["co_init"] == 0
    assert counters["dispatch"] == 0
    out = capsys.readouterr().out
    assert json.loads(out) == []
```

- [ ] **Step 4：跑 3 测试确认全 RED**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_list_configs_worker.py::test_batch_mode_initializes_com_only_once tests/test_sw_list_configs_worker.py::test_batch_mode_per_file_open_failure_keeps_single_lifecycle tests/test_sw_list_configs_worker.py::test_batch_mode_empty_list_skips_com_boot -v
```

预期：3 全 FAIL（counters["co_init"] 实际 = 3 / 0 / 0 三种情况）

- [ ] **Step 5：重构 `sw_list_configs_worker.py`**

整体替换 `_list_configs_returning` + `_run_batch_mode` 为：

```python
def _open_doc_get_configs(app, sldprt_path: str) -> list[str]:
    """共享 primitive：在已 boot 的 app 上 OpenDoc6 取配置名 CloseDoc。

    单件 + batch 都用此函数，差别仅在 SW lifecycle 谁管。失败抛 RuntimeError。
    """
    import pythoncom
    from win32com.client import VARIANT

    err_var = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warn_var = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    model = app.OpenDoc6(sldprt_path, 1, 1, "", err_var, warn_var)
    if err_var.value or model is None:
        raise RuntimeError(
            f"OpenDoc6 errors={err_var.value} "
            f"warnings={warn_var.value} "
            f"model={'NULL' if model is None else 'OK'}"
        )
    try:
        config_mgr = model.ConfigurationManager
        return list(config_mgr.GetConfigurationNames())
    finally:
        try:
            app.CloseDoc(model.GetPathName())
        except Exception as e:
            print(f"worker: CloseDoc ignored: {e!r}", file=sys.stderr)


def _list_configs_returning(sldprt_path: str) -> list[str]:
    """单件路径：自管 SW lifecycle（CoInit + Dispatch + ExitApp + CoUninit）。

    保留向后兼容（broker 单件 fallback 路径仍调此函数）。失败抛 RuntimeError。
    """
    import pythoncom
    from win32com.client import DispatchEx

    pythoncom.CoInitialize()
    try:
        app = DispatchEx("SldWorks.Application")
        try:
            app.Visible = False
            app.UserControl = False
            app.FrameState = 0
            return _open_doc_get_configs(app, sldprt_path)
        finally:
            try:
                app.ExitApp()
            except Exception as e:
                print(f"worker: ExitApp ignored: {e!r}", file=sys.stderr)
    finally:
        pythoncom.CoUninitialize()


def _list_configs(sldprt_path: str) -> int:
    """单件 CLI 模式入口：返 exit code，stdout 打印 JSON list of strings。"""
    try:
        try:
            import pythoncom  # noqa: F401
            import win32com.client  # noqa: F401
        except ImportError as e:
            print(f"worker: pywin32 import failed: {e!r}", file=sys.stderr)
            return 4
        try:
            names = _list_configs_returning(sldprt_path)
        except RuntimeError as e:
            print(f"worker: {e}", file=sys.stderr)
            if "OpenDoc6" in str(e):
                return 2
            return 4
        print(json.dumps(names, ensure_ascii=False))
        return 0
    except Exception as e:
        print(f"worker: unexpected exception: {e!r}", file=sys.stderr)
        return 4


def _run_batch_mode() -> int:
    """--batch：从 stdin 读 JSON list of sldprt_path → **真正一次** boot SW →
    loop _open_doc_get_configs → 一次 ExitApp。

    单件失败（OpenDoc6 fail / 任何异常）→ configs=[] 不阻其他件；整 batch exit 0。
    空 list → 不 boot SW（早返）避免无谓启动。
    """
    try:
        sldprt_list = json.load(sys.stdin)
        if not isinstance(sldprt_list, list):
            print("worker --batch: stdin must be JSON list", file=sys.stderr)
            return 64
    except json.JSONDecodeError as e:
        print(f"worker --batch: invalid stdin JSON: {e}", file=sys.stderr)
        return 64

    if not sldprt_list:
        print(json.dumps([], ensure_ascii=False))
        return 0

    try:
        import pythoncom
        from win32com.client import DispatchEx
    except ImportError as e:
        print(f"worker --batch: pywin32 import failed: {e!r}", file=sys.stderr)
        return 4

    pythoncom.CoInitialize()
    try:
        app = DispatchEx("SldWorks.Application")
        try:
            app.Visible = False
            app.UserControl = False
            app.FrameState = 0

            results = []
            for sldprt_path in sldprt_list:
                try:
                    configs = _open_doc_get_configs(app, sldprt_path)
                except Exception as e:
                    print(
                        f"worker --batch: {sldprt_path} failed: {e!r}",
                        file=sys.stderr,
                    )
                    configs = []
                results.append({"path": sldprt_path, "configs": configs})

            print(json.dumps(results, ensure_ascii=False))
            return 0
        finally:
            try:
                app.ExitApp()
            except Exception as e:
                print(f"worker --batch: ExitApp ignored: {e!r}", file=sys.stderr)
    finally:
        pythoncom.CoUninitialize()
```

`main()` 函数保持不变。

- [ ] **Step 6：跑 3 测试确认 GREEN**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_list_configs_worker.py -v
```

预期：3 新测试 PASS + 7 现有测试全 PASS（共 10 PASS）。

特别注意：现有 `test_batch_mode_reads_stdin_and_writes_stdout` 和
`test_batch_mode_per_file_failure_continues` 用 `monkeypatch.setattr(w, "_list_configs_returning", ...)` 来 mock，
**但重构后 batch 路径不再调 `_list_configs_returning`，改调 `_open_doc_get_configs`**——
这两个测试需要改成 mock `_open_doc_get_configs`：

修改 `test_batch_mode_reads_stdin_and_writes_stdout` line 73-76：

```python
    def fake_open_doc_get_configs(app, sldprt_path):
        return fake_results.get(sldprt_path, [])

    monkeypatch.setattr(w, "_open_doc_get_configs", fake_open_doc_get_configs)
    # 同时 mock COM 模块（_run_batch_mode 仍要 import + DispatchEx）
    counters, fake_py, fake_w32, fake_w32_client = _make_fake_com_modules()
    monkeypatch.setitem(sys.modules, "pythoncom", fake_py)
    monkeypatch.setitem(sys.modules, "win32com", fake_w32)
    monkeypatch.setitem(sys.modules, "win32com.client", fake_w32_client)
```

类似地修改 `test_batch_mode_per_file_failure_continues` line 107-112：

```python
    def flaky(app, sldprt_path):
        if "bad" in sldprt_path:
            raise RuntimeError("simulated COM failure")
        return ["A"]

    monkeypatch.setattr(w, "_open_doc_get_configs", flaky)
    counters, fake_py, fake_w32, fake_w32_client = _make_fake_com_modules()
    monkeypatch.setitem(sys.modules, "pythoncom", fake_py)
    monkeypatch.setitem(sys.modules, "win32com", fake_w32)
    monkeypatch.setitem(sys.modules, "win32com.client", fake_w32_client)
```

- [ ] **Step 7：跑全测套确认 0 regression**

```bash
.venv/Scripts/python.exe -m pytest -q --no-header 2>&1 | tail -20
```

预期：1247 + 4 新测试 = **1251 passed**（与 PR baseline 同数 fail/skip/error）。

- [ ] **Step 8：commit**

```bash
git add adapters/solidworks/sw_list_configs_worker.py tests/test_sw_list_configs_worker.py
git commit -m "fix(sw_list_configs_worker): C-1 batch 模式真正一次 boot SW（PR #19 review fix）

原实现 _run_batch_mode 每文件调 _list_configs_returning（含完整 SW lifecycle）→
N 件 = N×SW boot ≈ 25min/50件，性能契约破，宣传的 prewarm 优化失效。

抽 _open_doc_get_configs(app, path) 共享 primitive：
- 单件路径 (_list_configs_returning)：自管 lifecycle（兼容 broker fallback 路径）
- batch 路径 (_run_batch_mode)：单 lifecycle wrap 全 loop（真正一次 boot）

新加 3 测试 _make_fake_com_modules helper 用 sys.modules 注入 fake pythoncom/win32com，
计数 CoInit/Dispatch/ExitApp/CoUninit 各应 1 次（不再随 N 增长）；
现有 2 mock _list_configs_returning 测改为 mock _open_doc_get_configs。"
```

---

## Task 3：spec follow-up + push

**Files:**
- 修改：`docs/superpowers/specs/2026-04-26-sw-toolbox-config-list-persistent-cache.md`

- [ ] **Step 1：spec 末尾追加 follow-up issues 章节**

在 spec 文件末尾追加：

```markdown
---

## §10 Review Follow-Up Issues（PR #19 self-review）

C-1 + I-1 已在 PR #19 同 commit 修复。其余推迟到下个 PR / 技术债清单：

- **I-2 envelope 升级未持久化**：worker fail 时 in-memory cache 升级 envelope 但不写盘 → 下次 prewarm 重复无效检查。修复：envelope invalidated 时先 save empty cache 再尝试 worker spawn。
- **I-3 msvcrt.locking 无重试 UX**：并发 codegen 撞锁 → raw OSError 出。修复：bounded retry + 用户面提示。北极星"傻瓜式"gate 项。
- **I-4 mtime+size collision 边界**：极罕见情况 (SW UI 编辑后 mtime+size 撞老缓存)。已知限制，文档化即可。
- **M-1 fsync 缺失**：tmpfile→rename 不带 fsync，power-loss 可能留空文件。Windows 桌面用例可接受。
- **M-2 _save_config_lists_cache 异常上抛**：PermissionError 等会冒泡。修复：包 try/except 静默 + warn。
- **M-3 _PROJECT_ROOT_FOR_WORKER 模块级 vs 函数级 import 不对称**：仅文档化，加 reload 测试。
- **M-4 transient COM 失败永久缓存**：单次 hiccup 缓存空 list 拖累全 BOM。修复：区分 transient vs terminal failure，加 --retry-failed CLI flag。
- **M-5 prewarm timeout 缩放**：C-1 修复后总时长 ≈ 30s + 2s×N，timeout 公式相应调整。
- **M-6 detect_solidworks 重复 import**：函数内 import 每次 prewarm 都执行；可提到模块级（注意 reload 兼容）。
- **M-7 INVALIDATION_REASONS frozenset 校验**：内部单 caller 函数加防御校验属过度防御，可去除。
```

- [ ] **Step 2：git diff 自查 + commit**

```bash
git diff docs/superpowers/specs/2026-04-26-sw-toolbox-config-list-persistent-cache.md | head -50
git add docs/superpowers/specs/2026-04-26-sw-toolbox-config-list-persistent-cache.md
git commit -m "docs(spec): PR #19 review follow-up issues 登记 §10

C-1 + I-1 已修；I-2/I-3/I-4 + M-1..M-7 推迟到下个 PR / 技术债清单，
spec §10 章节登记修复方向，便于后续 plan 直接 cherry-pick。"
```

- [ ] **Step 3：push 触发 CI**

```bash
git push origin feat/sw-config-broker
gh pr view 19 --json statusCheckRollup -q '.statusCheckRollup[].conclusion' 2>&1 | sort -u
```

预期：触发新 CI 跑；2-3min 后 7/7 全 SUCCESS。

- [ ] **Step 4：等 CI 全绿后报告用户**

CI 全绿 → 准备 merge → tag v2.19.0。
CI 红 → 排查（log 失败 job stderr / 本地复现 / hotfix）。

---

## 完成验收

- [ ] Task 0：Step 1-2 grep 验证通过
- [ ] Task 1：6 步全过 + 1 commit（I-1 fix）
- [ ] Task 2：8 步全过 + 1 commit（C-1 fix）
- [ ] Task 3：4 步全过 + 1 commit（spec follow-up + push）
- [ ] CI：7/7 SUCCESS on new HEAD
- [ ] 全测套：1251 passed（baseline 1247 + 4 new）/ 0 regression

完成后回到主 session，由用户决定 merge + v2.19.0 release 操作。
