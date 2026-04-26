# sw_config_broker I-2 + I-3 修复实施 plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 PR #19 self-review 推迟到 §11 的 I-2（envelope 升级未持久化导致死循环 invalidate）+ I-3（msvcrt 锁无重试 UX 损害"照片级"原则），合并为单 PR `feat/sw-config-broker-i2-i3-fix`。

**Architecture:** 两处 surgical 改动到单文件 `adapters/solidworks/sw_config_broker.py`：(1) `prewarm_config_lists` 在 invalidate 分支末尾加 8 行（try/except + save）；(2) `_project_file_lock` 重写 ~30 行（LK_NBLCK + 永不超时 polling + banner + 进度提示）。新增 32 测试按 15 行为维度详尽覆盖（含 fake msvcrt setitem 模式 + tracking_save / failing_save 双模板 + time.monotonic-by-sleep 推进 mock）。

**Tech Stack:** Python 3.11 / pytest / unittest.mock / monkeypatch / msvcrt / sw_config_broker.py / sw_config_lists_cache.py

**关联 spec:** `docs/superpowers/specs/2026-04-26-sw-config-broker-i2-i3-fix-design.md`（已经过 3 轮 self-review + 1 轮 subagent 敌对审查）

---

## File Structure

| 文件 | 操作 | 责任 |
|------|------|------|
| `adapters/solidworks/sw_config_broker.py` | 修改 | I-2 (prewarm 8 行) + I-3 (_project_file_lock 重写 + 2 常量 + 1 文案 + import time) |
| `tests/test_sw_config_broker.py` | 扩展（追加） | 新增 32 测试（含 mock helper + 7 维度 I-2 + 8 维度 I-3）|
| `docs/superpowers/specs/2026-04-26-sw-toolbox-config-list-cache-design.md` | 修改 | §11 标 I-2 + I-3 closed + 反向链接本 spec |

**不改动文件**：`sw_config_lists_cache.py` / `sw_list_configs_worker.py` / `sw_toolbox_adapter.py` / `parts_resolver.py` / `gen_std_parts.py` / `tests/conftest.py` / `pyproject.toml`。

---

## Phase 0 — 准备

### Task 0.1：建 feature branch + 跑 baseline

**Files:** 无

- [ ] **Step 1：从 main 建 feature branch**

```bash
cd /d/Work/cad-spec-gen
git checkout -b feat/sw-config-broker-i2-i3-fix
git status
```

期望：`On branch feat/sw-config-broker-i2-i3-fix` + working tree clean。

- [ ] **Step 2：跑本地 baseline 拿数字**

```bash
.venv/Scripts/python.exe -m pytest -q \
  --ignore=tests/test_a2_integration.py \
  --ignore=tests/test_part_templates.py \
  2>&1 | tail -3
```

期望：`1251 passed, ... 35 failed, 32 skipped, ... 13 errors`（与 spec §6.3 baseline 一致）。

记录数字：本地 baseline = **1251 passed / 35 failed / 32 skipped / 13 errors / 2 collection errors（已 ignore）**。

### Task 0.2：grep 既有锚点验证

**Files:** 无（仅验证）

- [ ] **Step 1：验证 prewarm_config_lists 行号**

```bash
grep -n "def prewarm_config_lists\|^    cache\[\"toolbox_path\"\]\|^    miss = \[" \
  adapters/solidworks/sw_config_broker.py
```

期望（与 spec §4.1 line anchor 一致）：
```
538:def prewarm_config_lists(sldprt_list: list[str]) -> None:
565:    cache["toolbox_path"] = info.toolbox_dir
567:    miss = [
```

记录：**插入点 = line 565 之后 / line 567 之前**。

- [ ] **Step 2：验证 _project_file_lock 行号**

```bash
grep -n "^@contextlib.contextmanager\|^def _project_file_lock\|^def resolve_config_for_part" \
  adapters/solidworks/sw_config_broker.py
```

期望：
```
633:@contextlib.contextmanager
634:def _project_file_lock() -> Iterator[None]:
666:def resolve_config_for_part(
```

记录：**_project_file_lock 函数体范围 = line 634-664（含 docstring + finally 块）**。

- [ ] **Step 3：验证既有 imports 没有 time**

```bash
grep -n "^import time\|^import" adapters/solidworks/sw_config_broker.py | head -10
```

期望：line 16-22 有 contextlib/json/logging/os/re/subprocess/sys，**没有** `import time`。

记录：**需新增 `import time`（按字母顺序在 line 21 `import subprocess` 之前）**。

---

## Phase A — I-2 修复（commit 1）

### Task A.1：加 mock helper + I-2 测试 class skeleton

**Files:**
- 修改：`tests/test_sw_config_broker.py`（追加到文件末尾）

- [ ] **Step 1：读 test_sw_config_broker.py 末尾确认追加点**

```bash
wc -l tests/test_sw_config_broker.py
tail -5 tests/test_sw_config_broker.py
```

记录最后一行行号 N。新代码追加到第 N+1 行起。

- [ ] **Step 2：在 test_sw_config_broker.py 末尾追加 mock helper + I-2 测试 class 骨架**

```python


# ============================================================
# PR #19 review followup — I-2 + I-3 修复测试
# spec: docs/superpowers/specs/2026-04-26-sw-config-broker-i2-i3-fix-design.md
# ============================================================

import sys as _sys
import time as _time
import types as _types

import pytest

from adapters.solidworks import sw_config_broker as broker
from adapters.solidworks import sw_config_lists_cache as cache_mod


# ─── mock helpers (spec §6.4) ───

def make_fake_msvcrt(locking_calls: list, contention_count: int = 0):
    """构造 fake msvcrt 模块（spec §6.4）— 跨平台 universal。

    使用 setitem(sys.modules, "msvcrt", ...) 注入，函数体内 `import msvcrt` 命中 fake。
    Linux 上 real msvcrt 不存在，setattr 会炸；setitem 模式才能跨平台跑。
    """
    fake = _types.ModuleType("msvcrt")
    fake.LK_NBLCK = 1
    fake.LK_UNLCK = 2
    fake.LK_LOCK = 3
    fake.LK_NBRLCK = 4

    def locking(fd, mode, nbytes):
        mode_name = "LK_NBLCK" if mode == fake.LK_NBLCK else "LK_UNLCK"
        locking_calls.append((mode_name, fd, nbytes))
        if mode == fake.LK_NBLCK and len(locking_calls) <= contention_count:
            raise OSError("contended")
        return None

    fake.locking = locking
    return fake


def make_failing_save(exception_to_raise):
    """构造抛指定异常的 fake _save_config_lists_cache（spec §6.4）。"""
    def failing_save(cache):
        raise exception_to_raise
    return failing_save


def make_tracking_save(call_order: list, real_save):
    """构造 tracking_save：记录调用 + 真写盘（spec §6.4）。"""
    def tracking_save(cache):
        call_order.append(("save", cache.get("sw_version"), len(cache.get("entries", {}))))
        return real_save(cache)
    return tracking_save


def make_synced_time_mock(monkeypatch):
    """time.monotonic 由 time.sleep 推进（spec §6.4）— 防 busy loop bug 漏测。"""
    fake_now = [0.0]

    def fake_sleep(seconds):
        fake_now[0] += seconds

    def fake_monotonic():
        return fake_now[0]

    monkeypatch.setattr(broker.time, "sleep", fake_sleep)
    monkeypatch.setattr(broker.time, "monotonic", fake_monotonic)
    return fake_now


# ─── I-2 修复测试（14 测试 / 7 维度 / spec §6.2）───

class TestI2EnvelopePersistence:
    """spec §6.2 I-2 测试矩阵（14 测试 / 7 维度）。"""
    pass  # 测试方法在后续 task 添加
```

- [ ] **Step 3：跑测试验证 import + class 骨架不破坏既有**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py -v --no-header 2>&1 | tail -5
```

期望：所有既有测试 PASS（新 class TestI2EnvelopePersistence 无方法不计数）。

### Task A.2：写 E1 维度 — T19 + T20 RED

**Files:**
- 修改：`tests/test_sw_config_broker.py`（在 `class TestI2EnvelopePersistence` 内添加 2 方法）

- [ ] **Step 1：在 class 内 `pass` 替换为 T19 + T20 测试方法**

```python
    # ─── E1. 核心顺序 invariant（2 测试）───

    def test_invalidate_save_called_before_worker_spawn(
        self, monkeypatch, tmp_project_dir,
    ):
        """T19：spec §6.2 — call_order 列表断言：save(2025, entries={}) 出现在
        subprocess.run(worker) 之前。防 envelope 升级 save 漏写盘 bug。"""
        # 旧 cache (sw=2024) — 触发 invalidate
        old_cache = {
            "schema_version": 1,
            "generated_at": "2026-04-01T00:00:00+00:00",
            "sw_version": 2024,
            "toolbox_path": "C:/old",
            "entries": {},
        }

        call_order = []

        # mock load 返旧 cache
        monkeypatch.setattr(cache_mod, "_load_config_lists_cache", lambda: old_cache.copy())

        # mock detect 返新版本
        class FakeInfo:
            version_year = 2025
            toolbox_dir = "C:/new"
        monkeypatch.setattr(
            "adapters.solidworks.sw_detect.detect_solidworks", lambda: FakeInfo(),
        )

        # tracking_save：记录调用
        def tracking_save(cache):
            call_order.append(("save", cache.get("sw_version"), len(cache.get("entries", {}))))
        monkeypatch.setattr(cache_mod, "_save_config_lists_cache", tracking_save)

        # mock subprocess.run：worker fail
        def tracking_run(cmd, **kwargs):
            call_order.append(("spawn", "worker"))
            import subprocess
            return subprocess.CompletedProcess(cmd, returncode=1, stdout=b"", stderr=b"boom")
        monkeypatch.setattr(broker.subprocess, "run", tracking_run)

        broker.prewarm_config_lists(["C:/p1.sldprt"])

        # 断言顺序：save 必须在 spawn 之前
        assert call_order[0] == ("save", 2025, 0), f"call_order={call_order}"
        assert call_order[1] == ("spawn", "worker"), f"call_order={call_order}"

    def test_invalidate_save_content_correct(
        self, monkeypatch, tmp_project_dir,
    ):
        """T20：spec §6.2 — 测试前提：mock 旧 sw=2024 / 新 sw=2025（值显式不同），
        防 mutation `cache.get("sw_version", info.version_year)` 偷换旧值仍 pass。"""
        import json

        # 写真旧 cache 文件触发 invalidate（不 mock _load）
        cache_path = cache_mod.get_config_lists_cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({
            "schema_version": 1,
            "generated_at": "2026-04-01T00:00:00+00:00",
            "sw_version": 2024,
            "toolbox_path": "C:/old",
            "entries": {},
        }))

        class FakeInfo:
            version_year = 2025
            toolbox_dir = "C:/new"
        monkeypatch.setattr(
            "adapters.solidworks.sw_detect.detect_solidworks", lambda: FakeInfo(),
        )

        captured = {}

        def capturing_save(cache):
            # 深拷贝避免 caller mutate 影响断言
            captured["cache"] = {k: v for k, v in cache.items()}
        monkeypatch.setattr(cache_mod, "_save_config_lists_cache", capturing_save)

        # mock subprocess.run：worker fail（让 prewarm 不进 line 612 第二次 save）
        import subprocess
        monkeypatch.setattr(
            broker.subprocess, "run",
            lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, b"", b""),
        )

        broker.prewarm_config_lists(["C:/p1.sldprt"])

        cache = captured["cache"]
        assert cache["schema_version"] == 1
        assert cache["sw_version"] == 2025  # 防 cache.get() 偷换旧 2024
        assert cache["toolbox_path"] == "C:/new"
        assert cache["entries"] == {}
        # generated_at 仅验存在 + ISO 8601 格式
        assert "generated_at" in cache
        from datetime import datetime
        datetime.fromisoformat(cache["generated_at"])  # 抛 ValueError 即 fail
```

- [ ] **Step 2：跑 T19 + T20 验证 RED**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestI2EnvelopePersistence::test_invalidate_save_called_before_worker_spawn tests/test_sw_config_broker.py::TestI2EnvelopePersistence::test_invalidate_save_content_correct -v 2>&1 | tail -15
```

期望：**2 FAILED**（call_order[0] 实际是 ("spawn", "worker") 不是 ("save", ...) — 因 I-2 未修；T20 captured["cache"] 永远没被赋值因为 worker fail 后从未触发既有 line 612 save，新 save 也还没加）。

### Task A.3：写 E2 维度 — T21 + T22 (parametrize) + T22b RED

**Files:**
- 修改：`tests/test_sw_config_broker.py`（在 `TestI2EnvelopePersistence` class 内添加 3 方法）

- [ ] **Step 1：追加 E2 三个测试方法（紧接 T20 之后）**

```python
    # ─── E2. save 失败路径（3 测试）───

    def test_invalidate_save_oserror_warns_and_continues_to_worker(
        self, monkeypatch, tmp_project_dir, caplog,
    ):
        """T21：spec §6.2 — mock save 抛 OSError → log.warning（含"envelope save 失败"）+
        worker spawn 仍调用 + prewarm 不抛。"""
        import logging

        old_cache = {
            "schema_version": 1, "generated_at": "2026-04-01T00:00:00+00:00",
            "sw_version": 2024, "toolbox_path": "C:/old", "entries": {},
        }
        monkeypatch.setattr(cache_mod, "_load_config_lists_cache", lambda: old_cache.copy())

        class FakeInfo:
            version_year = 2025
            toolbox_dir = "C:/new"
        monkeypatch.setattr(
            "adapters.solidworks.sw_detect.detect_solidworks", lambda: FakeInfo(),
        )

        monkeypatch.setattr(
            cache_mod, "_save_config_lists_cache",
            make_failing_save(OSError("disk full")),
        )

        spawn_called = []
        import subprocess
        def tracking_run(cmd, **kwargs):
            spawn_called.append(cmd)
            return subprocess.CompletedProcess(cmd, 1, b"", b"")
        monkeypatch.setattr(broker.subprocess, "run", tracking_run)

        with caplog.at_level(logging.WARNING):
            broker.prewarm_config_lists(["C:/p1.sldprt"])  # 不应抛

        assert any("envelope save 失败" in rec.message for rec in caplog.records), \
            f"warn missing: {[r.message for r in caplog.records]}"
        assert len(spawn_called) == 1, "worker spawn 未被调用（fire-and-forget 契约破）"

    @pytest.mark.parametrize("exc_type", [
        RuntimeError, KeyError, TypeError, ValueError, AttributeError,
    ])
    def test_invalidate_save_any_exception_warns_and_continues(
        self, exc_type, monkeypatch, tmp_project_dir, caplog,
    ):
        """T22：spec §6.2 — 5 种 Exception 子类 parametrize；防 mutation
        `except (OSError, RuntimeError)` 漏 KeyError 等。"""
        import logging

        old_cache = {
            "schema_version": 1, "generated_at": "2026-04-01T00:00:00+00:00",
            "sw_version": 2024, "toolbox_path": "C:/old", "entries": {},
        }
        monkeypatch.setattr(cache_mod, "_load_config_lists_cache", lambda: old_cache.copy())

        class FakeInfo:
            version_year = 2025
            toolbox_dir = "C:/new"
        monkeypatch.setattr(
            "adapters.solidworks.sw_detect.detect_solidworks", lambda: FakeInfo(),
        )

        monkeypatch.setattr(
            cache_mod, "_save_config_lists_cache",
            make_failing_save(exc_type("test")),
        )

        spawn_called = []
        import subprocess
        def tracking_run(cmd, **kwargs):
            spawn_called.append(cmd)
            return subprocess.CompletedProcess(cmd, 1, b"", b"")
        monkeypatch.setattr(broker.subprocess, "run", tracking_run)

        with caplog.at_level(logging.WARNING):
            broker.prewarm_config_lists(["C:/p1.sldprt"])  # 不应抛

        assert any("envelope save 失败" in rec.message for rec in caplog.records), \
            f"warn missing for {exc_type.__name__}"
        assert len(spawn_called) == 1, \
            f"worker spawn 未被调用 for {exc_type.__name__}（fire-and-forget 契约破）"

    def test_invalidate_save_baseexception_propagates(
        self, monkeypatch, tmp_project_dir,
    ):
        """T22b：spec §6.2 — KeyboardInterrupt 是 BaseException 子类，
        except Exception 天然不 catch → 上抛 + worker spawn 不调用。"""
        old_cache = {
            "schema_version": 1, "generated_at": "2026-04-01T00:00:00+00:00",
            "sw_version": 2024, "toolbox_path": "C:/old", "entries": {},
        }
        monkeypatch.setattr(cache_mod, "_load_config_lists_cache", lambda: old_cache.copy())

        class FakeInfo:
            version_year = 2025
            toolbox_dir = "C:/new"
        monkeypatch.setattr(
            "adapters.solidworks.sw_detect.detect_solidworks", lambda: FakeInfo(),
        )

        monkeypatch.setattr(
            cache_mod, "_save_config_lists_cache",
            make_failing_save(KeyboardInterrupt()),
        )

        spawn_called = []
        monkeypatch.setattr(
            broker.subprocess, "run",
            lambda cmd, **kw: spawn_called.append(cmd) or None,
        )

        with pytest.raises(KeyboardInterrupt):
            broker.prewarm_config_lists(["C:/p1.sldprt"])

        assert len(spawn_called) == 0, "worker spawn 不应被调用（KeyboardInterrupt 应立即上抛）"
```

- [ ] **Step 2：跑 E2 三测试（含 parametrize 5 子测试，共 7 计数）**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestI2EnvelopePersistence -v -k "save_oserror or any_exception or baseexception" 2>&1 | tail -15
```

期望：**7 FAILED**（T21 + T22[5 parametrize] + T22b）。原因：I-2 修复未实施，新 save 路径不存在，failing_save 不被调；prewarm 走既有路径不会触发 warn；KeyboardInterrupt 测试反而会 PASS（因 save 不被调，自然不抛）—— **这点要注意**：T22b 在 RED 阶段意外 PASS 是合理的（无新 save = 无 KeyboardInterrupt 来源）。

### Task A.4：写 E3 维度 — T23 + T24 RED

**Files:**
- 修改：`tests/test_sw_config_broker.py`（追加 2 方法）

- [ ] **Step 1：追加 E3 测试方法**

```python
    # ─── E3. 第二次 prewarm 验证（2 测试）───

    def test_two_prewarm_calls_after_worker_fail_no_redundant_invalidate(
        self, monkeypatch, tmp_project_dir,
    ):
        """T23：spec §6.2 — 第 1 次 prewarm worker fail → 第 2 次 prewarm 进入时
        envelope_invalidated == False（这是 I-2 修复的核心 user value）。"""
        import json

        # 旧 cache (sw=2024) 写盘
        cache_path = cache_mod.get_config_lists_cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({
            "schema_version": 1, "generated_at": "2026-04-01T00:00:00+00:00",
            "sw_version": 2024, "toolbox_path": "C:/old", "entries": {},
        }))

        class FakeInfo:
            version_year = 2025
            toolbox_dir = "C:/new"
        monkeypatch.setattr(
            "adapters.solidworks.sw_detect.detect_solidworks", lambda: FakeInfo(),
        )

        # mock worker fail
        import subprocess
        monkeypatch.setattr(
            broker.subprocess, "run",
            lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, b"", b""),
        )

        broker.prewarm_config_lists(["C:/p1.sldprt"])

        # 第 2 次进入：load 应读到新 envelope（sw=2025）→ invalidated False
        cache_after = cache_mod._load_config_lists_cache()
        assert cache_after["sw_version"] == 2025, \
            f"第 1 次 prewarm 后磁盘 sw_version 仍={cache_after.get('sw_version')}（envelope 未持久化）"
        assert cache_mod._envelope_invalidated(cache_after) is False, \
            "第 2 次 prewarm envelope_invalidated 应为 False（修复后不再死循环）"

    def test_two_prewarm_calls_after_worker_fail_retries_failed_sldprt(
        self, monkeypatch, tmp_project_dir,
    ):
        """T24：spec §6.2 — 第 2 次 prewarm 走 miss diff → spawn worker 重试上次失败的 sldprt。"""
        import json

        cache_path = cache_mod.get_config_lists_cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({
            "schema_version": 1, "generated_at": "2026-04-01T00:00:00+00:00",
            "sw_version": 2024, "toolbox_path": "C:/old", "entries": {},
        }))

        class FakeInfo:
            version_year = 2025
            toolbox_dir = "C:/new"
        monkeypatch.setattr(
            "adapters.solidworks.sw_detect.detect_solidworks", lambda: FakeInfo(),
        )

        spawn_count = [0]
        import subprocess
        def tracking_run(cmd, **kwargs):
            spawn_count[0] += 1
            return subprocess.CompletedProcess(cmd, 1, b"", b"")
        monkeypatch.setattr(broker.subprocess, "run", tracking_run)

        broker.prewarm_config_lists(["C:/p1.sldprt"])
        broker.prewarm_config_lists(["C:/p1.sldprt"])

        assert spawn_count[0] == 2, \
            f"第 2 次 prewarm 未重试 worker；spawn_count={spawn_count[0]}"
```

- [ ] **Step 2：跑 E3 验证 RED**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestI2EnvelopePersistence -v -k "two_prewarm" 2>&1 | tail -10
```

期望：**2 FAILED**。T23 的 cache_after sw_version 实际仍 = 2024（修复未实施 envelope 不写盘）；T24 spawn_count 第 2 次仍触发 invalidate 重新 spawn，但**因为旧实施 worker fail 时第 2 次 prewarm 还会走 invalidate 路径**，spawn_count 实际是 2 —— T24 在 RED 阶段会 PASS。这是合理 noise，T24 真正价值在 GREEN 后验证不退化。

### Task A.5：写 E4 维度 — T25 + T26 RED

**Files:**
- 修改：`tests/test_sw_config_broker.py`（追加 2 方法）

- [ ] **Step 1：追加 E4 测试方法**

```python
    # ─── E4. detect 边角（2 测试）───

    def test_invalidate_save_when_sw_not_installed(
        self, monkeypatch, tmp_project_dir,
    ):
        """T25：spec §6.2 — detect 返 SwInfo(installed=False, version_year=0,
        toolbox_dir="") → 仍 save sw_version=0 / toolbox_path="" 到磁盘。"""
        import json

        cache_path = cache_mod.get_config_lists_cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({
            "schema_version": 1, "generated_at": "2026-04-01T00:00:00+00:00",
            "sw_version": 2024, "toolbox_path": "C:/old", "entries": {},
        }))

        class FakeInfo:
            installed = False
            version_year = 0
            toolbox_dir = ""
        monkeypatch.setattr(
            "adapters.solidworks.sw_detect.detect_solidworks", lambda: FakeInfo(),
        )

        import subprocess
        monkeypatch.setattr(
            broker.subprocess, "run",
            lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, b"", b""),
        )

        broker.prewarm_config_lists(["C:/p1.sldprt"])

        cache_after = cache_mod._load_config_lists_cache()
        assert cache_after["sw_version"] == 0
        assert cache_after["toolbox_path"] == ""

    def test_invalidate_save_propagates_detect_unexpected_exception(
        self, monkeypatch, tmp_project_dir,
    ):
        """T26：spec §6.2 — detect 抛 RuntimeError → 上抛（detect 调用不在新 try/except 包围范围内；
        防实施者把 except 范围误扩到包整个 invalidate 分支）。"""
        old_cache = {
            "schema_version": 1, "generated_at": "2026-04-01T00:00:00+00:00",
            "sw_version": 2024, "toolbox_path": "C:/old", "entries": {},
        }
        monkeypatch.setattr(cache_mod, "_load_config_lists_cache", lambda: old_cache.copy())

        def raising_detect():
            raise RuntimeError("detect 内部 bug")
        monkeypatch.setattr(
            "adapters.solidworks.sw_detect.detect_solidworks", raising_detect,
        )

        with pytest.raises(RuntimeError, match="detect 内部 bug"):
            broker.prewarm_config_lists(["C:/p1.sldprt"])
```

- [ ] **Step 2：跑 E4 验证**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestI2EnvelopePersistence -v -k "sw_not_installed or detect_unexpected" 2>&1 | tail -10
```

期望：T25 **FAIL**（save 不持久化 sw=0）；T26 **PASS**（既有行为已经上抛 detect 异常）。

### Task A.6：写 E5 + E6 + E7 维度 — T27 / T28 / T29 / T30 / T31 RED

**Files:**
- 修改：`tests/test_sw_config_broker.py`（追加 5 方法）

- [ ] **Step 1：追加 E5/E6/E7 测试方法**

```python
    # ─── E5. 安全阀 regression（1 测试）───

    def test_prewarm_disable_env_skips_all_cache_ops(
        self, monkeypatch, tmp_project_dir,
    ):
        """T27：spec §6.2 — CAD_SW_BROKER_DISABLE=1 → 整函数早返；
        磁盘 cache 文件不被读 / 不被写。"""
        monkeypatch.setenv("CAD_SW_BROKER_DISABLE", "1")

        save_calls = []
        load_calls = []
        monkeypatch.setattr(
            cache_mod, "_save_config_lists_cache",
            lambda c: save_calls.append(c),
        )
        monkeypatch.setattr(
            cache_mod, "_load_config_lists_cache",
            lambda: load_calls.append(1) or {},
        )

        broker.prewarm_config_lists(["C:/p1.sldprt"])

        assert save_calls == [], "DISABLE=1 时不应调 save"
        assert load_calls == [], "DISABLE=1 时不应调 load"

    # ─── E6. 磁盘内容精确性（3 测试）───

    def test_invalidate_save_disk_json_schema_full_match(
        self, monkeypatch, tmp_project_dir,
    ):
        """T28：spec §6.2 — save 后磁盘 JSON 5 字段全员；schema_version=1 / sw=新 /
        toolbox=新 / entries={}；generated_at 仅验存在 + ISO 8601 格式。"""
        import json
        from datetime import datetime

        cache_path = cache_mod.get_config_lists_cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({
            "schema_version": 1, "generated_at": "2026-04-01T00:00:00+00:00",
            "sw_version": 2024, "toolbox_path": "C:/old", "entries": {},
        }))

        class FakeInfo:
            version_year = 2025
            toolbox_dir = "C:/new"
        monkeypatch.setattr(
            "adapters.solidworks.sw_detect.detect_solidworks", lambda: FakeInfo(),
        )

        import subprocess
        monkeypatch.setattr(
            broker.subprocess, "run",
            lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, b"", b""),
        )

        broker.prewarm_config_lists(["C:/p1.sldprt"])

        disk = json.loads(cache_path.read_text())
        # 5 字段全员
        for k in ("schema_version", "generated_at", "sw_version", "toolbox_path", "entries"):
            assert k in disk, f"字段 {k} 缺失"
        assert disk["schema_version"] == 1
        assert disk["sw_version"] == 2025
        assert disk["toolbox_path"] == "C:/new"
        assert disk["entries"] == {}
        # generated_at ISO 8601 格式校验
        datetime.fromisoformat(disk["generated_at"])

    def test_invalidate_save_then_worker_success_disk_has_entries(
        self, monkeypatch, tmp_project_dir, tmp_path,
    ):
        """T29：spec §6.2 — invalidate save → worker success → 第 2 次 save → 磁盘 JSON 含 entries{p1, p2}。"""
        import json

        cache_path = cache_mod.get_config_lists_cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({
            "schema_version": 1, "generated_at": "2026-04-01T00:00:00+00:00",
            "sw_version": 2024, "toolbox_path": "C:/old", "entries": {},
        }))

        class FakeInfo:
            version_year = 2025
            toolbox_dir = "C:/new"
        monkeypatch.setattr(
            "adapters.solidworks.sw_detect.detect_solidworks", lambda: FakeInfo(),
        )

        # 真建 sldprt 文件让 _stat_mtime/_stat_size 返合理值
        p1 = tmp_path / "p1.sldprt"
        p1.write_text("dummy1")
        p2 = tmp_path / "p2.sldprt"
        p2.write_text("dummy2")

        import subprocess
        def success_run(cmd, **kwargs):
            results = [
                {"path": str(p1), "configs": ["A"]},
                {"path": str(p2), "configs": ["B"]},
            ]
            return subprocess.CompletedProcess(cmd, 0, json.dumps(results).encode(), b"")
        monkeypatch.setattr(broker.subprocess, "run", success_run)

        broker.prewarm_config_lists([str(p1), str(p2)])

        disk = json.loads(cache_path.read_text())
        assert disk["sw_version"] == 2025
        assert len(disk["entries"]) == 2
        # 既有 _normalize_sldprt_key 决定 key 格式（resolve()），用同样 normalize 验证
        from adapters.solidworks.sw_config_broker import _normalize_sldprt_key
        assert _normalize_sldprt_key(str(p1)) in disk["entries"]
        assert _normalize_sldprt_key(str(p2)) in disk["entries"]

    def test_invalidate_save_does_not_overwrite_unrelated_user_files(
        self, monkeypatch, tmp_project_dir,
    ):
        """T30：spec §6.2 — save 只写 sw_config_lists.json；同目录 sw_toolbox_index.json 等不被 touched。"""
        import json

        cache_path = cache_mod.get_config_lists_cache_path()
        user_dir = cache_path.parent
        user_dir.mkdir(parents=True, exist_ok=True)

        # 旧 cache + 同目录其他文件
        cache_path.write_text(json.dumps({
            "schema_version": 1, "generated_at": "2026-04-01T00:00:00+00:00",
            "sw_version": 2024, "toolbox_path": "C:/old", "entries": {},
        }))
        unrelated_index = user_dir / "sw_toolbox_index.json"
        unrelated_index.write_text('{"unrelated": true}')
        unrelated_decisions = user_dir / "decisions.json"
        unrelated_decisions.write_text('{"some": "data"}')

        index_mtime_before = unrelated_index.stat().st_mtime
        decisions_mtime_before = unrelated_decisions.stat().st_mtime

        class FakeInfo:
            version_year = 2025
            toolbox_dir = "C:/new"
        monkeypatch.setattr(
            "adapters.solidworks.sw_detect.detect_solidworks", lambda: FakeInfo(),
        )

        import subprocess
        monkeypatch.setattr(
            broker.subprocess, "run",
            lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, b"", b""),
        )

        broker.prewarm_config_lists(["C:/p1.sldprt"])

        # 不相关文件 mtime 不变
        assert unrelated_index.stat().st_mtime == index_mtime_before
        assert unrelated_decisions.stat().st_mtime == decisions_mtime_before
        assert unrelated_index.read_text() == '{"unrelated": true}'
        assert unrelated_decisions.read_text() == '{"some": "data"}'

    # ─── E7. 路径 gating（1 测试）───

    def test_no_invalidate_no_extra_envelope_save(
        self, monkeypatch, tmp_project_dir,
    ):
        """T31：spec §6.2 — envelope 已新（_envelope_invalidated 返 False）→
        call_order 中不出现 invalidate 分支 save；只有既有 line 612 save。
        防实施者把新 save 写成无条件调用、漏在 if 分支外。"""
        # cache 已是新 envelope（不 invalidate）
        new_cache = {
            "schema_version": 1, "generated_at": "2026-04-01T00:00:00+00:00",
            "sw_version": 2025, "toolbox_path": "C:/new", "entries": {},
        }
        monkeypatch.setattr(cache_mod, "_load_config_lists_cache", lambda: new_cache.copy())

        # 强制 _envelope_invalidated 返 False
        monkeypatch.setattr(cache_mod, "_envelope_invalidated", lambda c: False)

        # 不需 detect mock，因为不进 invalidate 分支

        call_order = []

        def tracking_save(cache):
            call_order.append(("save", cache.get("sw_version"), len(cache.get("entries", {}))))
        monkeypatch.setattr(cache_mod, "_save_config_lists_cache", tracking_save)

        # mock subprocess.run worker fail 让既有 line 612 save 也不触发
        import subprocess
        monkeypatch.setattr(
            broker.subprocess, "run",
            lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, b"", b""),
        )

        broker.prewarm_config_lists(["C:/p1.sldprt"])

        # 关键断言：cache 已新 + worker fail → call_order 应为空（无 save）
        assert call_order == [], \
            f"envelope 已新且 worker fail 时不应有 save；实际 call_order={call_order}"
```

- [ ] **Step 2：跑 E5/E6/E7 验证**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestI2EnvelopePersistence -v -k "disable_env or disk_json_schema or worker_success or unrelated_user or no_invalidate_no_extra" 2>&1 | tail -10
```

期望：T27 PASS（既有 disable env 已实施）；T28-T30 FAIL（新 save 未实施）；T31 PASS（既有路径无新 save）。

### Task A.7：跑全 14 I-2 测试拿到 RED 总状态

**Files:** 无

- [ ] **Step 1：跑 I-2 全部测试**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestI2EnvelopePersistence -v --no-header 2>&1 | tail -25
```

预期 RED 状态（按 T 编号）：
- T19 FAIL（call_order 顺序错）
- T20 FAIL（captured 为空）
- T21 FAIL（warn 不触发）
- T22 FAIL × 5 parametrize（同 T21）
- T22b PASS（save 不被调，KeyboardInterrupt 不抛但测试用 raises 反而 fail — 实际**这个会 FAIL**：raises 没拿到异常）
- T23 FAIL（磁盘 sw=2024）
- T24 PASS（spawn_count=2 巧合）
- T25 FAIL（save 不写盘）
- T26 PASS（detect 上抛是既有行为）
- T27 PASS（既有 disable env）
- T28 FAIL（disk schema 不更新）
- T29 FAIL（entries 不写）
- T30 PASS（atomic write 既有行为）
- T31 PASS（既有无新 save）

**预期 RED 数 ≈ 9-10 fail / 5-6 pass**（具体见 step 2 实际跑）。

记录实际 RED 计数 R0 = ?；GREEN 后应至少 14 个全过。

### Task A.8：实施 I-2 修复（8 行）

**Files:**
- 修改：`adapters/solidworks/sw_config_broker.py:565-566`（在 line 565 之后插入）

- [ ] **Step 1：在 broker.py line 565 之后插入修复代码**

精确插入位置：`cache["toolbox_path"] = info.toolbox_dir`（line 565）**之后**、`miss = [` 之前。

插入内容（注意缩进与既有 `if cache_mod._envelope_invalidated(cache):` 分支体一致 = 8 空格）：

```python
        # ━━ I-2 修复（PR #19 review fix）：envelope 升级决策立即落盘 ━━━━━━━━━━━━━━━
        # 不依赖后续 worker 成功；防"worker 失败 → 内存 envelope 丢 → 下次 prewarm
        # 又重检测 invalidate"循环。spec §4.1 / §5.2。
        try:
            cache_mod._save_config_lists_cache(cache)
        except Exception as e:
            # fire-and-forget 契约（spec §5.3 invariant 1）：BOM loop 必须能拿到结果。
            # except Exception 而非 OSError：cache_mod 内部 bug（KeyError/AttributeError 等）
            # 也应 warn 而非 abort 整个 codegen。BaseException 子类（KeyboardInterrupt /
            # SystemExit）天然不被 catch，仍上抛保证 Ctrl+C 立即生效。
            log.warning(
                "config_lists envelope save 失败 (%s)；下次 prewarm 仍会重检测 invalidate",
                e,
            )
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

实现后效果：原 line 567 起的 `miss = [...]` 不变。

- [ ] **Step 2：grep 确认插入正确**

```bash
grep -n "I-2 修复\|envelope save 失败" adapters/solidworks/sw_config_broker.py
```

期望：3 行匹配（注释开头 + 代码 + log.warning 文案）。

- [ ] **Step 3：再次 grep 验证函数体结构**

```bash
grep -n "^    if cache_mod._envelope_invalidated\|^    miss = \[\|^    if not miss:" adapters/solidworks/sw_config_broker.py
```

期望（行号略有偏移因新增 ~13 行）：
```
560:    if cache_mod._envelope_invalidated(cache):
580:    miss = [
586:    if not miss:
```

记录新行号供后续验证。

### Task A.9：跑 14 I-2 测试 GREEN 验证

**Files:** 无

- [ ] **Step 1：跑 I-2 全部测试**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestI2EnvelopePersistence -v --no-header 2>&1 | tail -20
```

期望：**14 passed**（含 T22 的 5 parametrize 子测试）。

- [ ] **Step 2：跑既有 broker 全测套确认 0 regression**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py -v --no-header 2>&1 | tail -3
```

期望：既有测试数 + 14 新 = 全 PASS，0 fail。

### Task A.10：跑全测套确认 baseline + 14 数字

**Files:** 无

- [ ] **Step 1：全测套（绕过 cadquery 依赖）**

```bash
.venv/Scripts/python.exe -m pytest -q \
  --ignore=tests/test_a2_integration.py \
  --ignore=tests/test_part_templates.py \
  2>&1 | tail -3
```

期望：`1265 passed, ... 35 failed, 32 skipped, ... 13 errors`（baseline 1251 + 14 新）。

记录数字：实际 = ?；如有意外 fail/regression，**停下排查**不要继续 commit。

### Task A.11：Commit 1（I-2 修复）

**Files:**
- 修改：`adapters/solidworks/sw_config_broker.py`
- 修改：`tests/test_sw_config_broker.py`

- [ ] **Step 1：git status 确认 staged 文件**

```bash
git status -s
```

期望：仅 `M adapters/solidworks/sw_config_broker.py` + `M tests/test_sw_config_broker.py`。如有其他文件修改，**停下排查不要 add**。

- [ ] **Step 2：commit**

```bash
git add adapters/solidworks/sw_config_broker.py tests/test_sw_config_broker.py
git commit -m "$(cat <<'EOF'
fix(sw_config_broker): I-2 envelope 升级立即落盘（PR #19 review fix）

prewarm_config_lists 在 _envelope_invalidated 分支末尾立即调
_save_config_lists_cache 持久化新 envelope，不再依赖后续 worker 成功。

修复前：worker spawn 失败时内存 envelope 升级丢失，下次 prewarm 又重检测
invalidate 形成死循环；磁盘 sw_version 永远停在升级前的旧值。

修复后：磁盘 sw_version + toolbox_path 永远反映最近一次 prewarm 见到的真实
SW/Toolbox 状态，与 worker 输出无关。worker 失败时 BOM loop 仍走 fallback
单件 spawn 兜底，不影响图像质量（fire-and-forget 契约）。

新增 14 测试 / 7 行为维度（spec §6.2）：
- E1 核心顺序 invariant: T19 (call_order) + T20 (mutation 防御 sw=2024 vs 2025)
- E2 save 失败路径: T21 (OSError) + T22 (parametrize 5 Exception 子类) + T22b (KeyboardInterrupt 上抛)
- E3 第二次 prewarm: T23 (无 invalidate) + T24 (重试 sldprt)
- E4 detect 边角: T25 (SwInfo not installed) + T26 (RuntimeError 上抛)
- E5 安全阀 regression: T27 (DISABLE=1)
- E6 磁盘内容: T28 (5 字段 + ISO 8601) + T29 (entries 累积) + T30 (不 overwrite unrelated)
- E7 路径 gating: T31 (envelope 已新时无新 save)

mock 模板按 spec §6.4：make_fake_msvcrt setitem 跨平台 + tracking_save / failing_save 双模板。

spec: docs/superpowers/specs/2026-04-26-sw-config-broker-i2-i3-fix-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git log --oneline -3
```

期望：新 commit 在 HEAD，commit message 完整无截断。

---

## Phase B — I-3 修复（commit 2）

### Task B.1：在 broker.py 顶部加 `import time`

**Files:**
- 修改：`adapters/solidworks/sw_config_broker.py:21`（在 `import subprocess` 之前）

- [ ] **Step 1：用 Edit 工具在 line 20-21 之间加 import time**

精确替换：
- old: `import re\nimport subprocess`
- new: `import re\nimport subprocess\nimport time`

或更精确：在 line 20 `import re` 之后插入新行 `import time`。

注意 imports 区按字母顺序排：contextlib → json → logging → os → re → **subprocess** → sys。新 `import time` 应在 subprocess 之**后**、sys 之**前**（按字母 s-t-... 顺序），即 line 22。

- [ ] **Step 2：grep 验证**

```bash
grep -n "^import time\|^import sys\|^import subprocess" adapters/solidworks/sw_config_broker.py | head -5
```

期望：
```
21:import subprocess
22:import time
23:import sys
```

（注意：标准库通常按字母排，t < y 所以 time 在 sys 之前。但项目既有 `import sys` 在 line 22 — 让 plan 与此保持。Step 1 实际操作：在既有 `import subprocess` (line 21) 与 `import sys` (line 22) 之间插入 `import time`，新行号 22 = time，line 23 = sys。）

### Task B.2：加 I-3 模块级常量与文案

**Files:**
- 修改：`adapters/solidworks/sw_config_broker.py:630`（在 `LOCK_FILE_NAME = "lock"` 之后）

- [ ] **Step 1：在 LOCK_FILE_NAME 后追加常量与 banner 文案**

精确替换：
- old:
```python
LOCK_FILE_NAME = "lock"


@contextlib.contextmanager
def _project_file_lock() -> Iterator[None]:
```

- new:
```python
LOCK_FILE_NAME = "lock"

# ━━ I-3 锁等待行为参数（PR #19 review fix，spec §3.2）━━━━━━━━━━━━━━━━━━━━━━━━
LOCK_POLL_INTERVAL_SEC = 0.5        # 每次 LK_NBLCK 失败后 sleep
LOCK_PROGRESS_INTERVAL_SEC = 5      # 进度提示间隔（首次立刻，之后每 5s）

_LOCK_WAITING_BANNER = (
    "⏳ 检测到另一个 codegen 实例正占用项目锁 ({path})，正在排队等待。\n"
    "   - 想中止：按 Ctrl+C\n"
    "   - 不要手动删除锁文件：与运行中实例并发改 cache 会损坏决策记录，\n"
    "     导致下次跑用错的 SW 配置（图像与 BOM 不一致）"
)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@contextlib.contextmanager
def _project_file_lock() -> Iterator[None]:
```

- [ ] **Step 2：grep 验证**

```bash
grep -n "LOCK_POLL_INTERVAL_SEC\|LOCK_PROGRESS_INTERVAL_SEC\|_LOCK_WAITING_BANNER" adapters/solidworks/sw_config_broker.py
```

期望：3 个新常量定义 + 后续函数体引用（暂无，下一 task 加）。

### Task B.3：写 D1 维度 — T1 + T2 RED

**Files:**
- 修改：`tests/test_sw_config_broker.py`（在 TestI2EnvelopePersistence class 之后追加新 class）

- [ ] **Step 1：在 TestI2EnvelopePersistence 之后追加 TestI3LockBehavior class + D1 测试**

```python


# ─── I-3 修复测试（18 测试 / 8 维度 / spec §6.1）───

class TestI3LockBehavior:
    """spec §6.1 I-3 测试矩阵（18 测试 / 8 维度）。"""

    # ─── D1. happy path（2 测试）───

    def test_lock_yields_immediately_when_uncontended(
        self, monkeypatch, tmp_project_dir,
    ):
        """T1：spec §6.1 — LK_NBLCK 第 1 次成功 → 0 banner / 0 进度 / yield 正常 / unlock 调用 1 次。"""
        monkeypatch.setattr(_sys, "platform", "win32")
        locking_calls = []
        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=0)
        monkeypatch.setitem(_sys.modules, "msvcrt", fake_msvcrt)

        entered = []
        with broker._project_file_lock():
            entered.append(True)

        assert entered == [True], "yield body 未执行"
        assert len(locking_calls) == 2, f"应有 1 LK_NBLCK + 1 LK_UNLCK；实际 {locking_calls}"
        assert locking_calls[0][0] == "LK_NBLCK"
        assert locking_calls[1][0] == "LK_UNLCK"

    def test_lock_yield_body_exception_still_releases_lock(
        self, monkeypatch, tmp_project_dir,
    ):
        """T2：spec §6.1 — yield body 抛 ValueError → 异常上抛 + unlock 仍调用 + fp.close() 仍执行。"""
        monkeypatch.setattr(_sys, "platform", "win32")
        locking_calls = []
        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=0)
        monkeypatch.setitem(_sys.modules, "msvcrt", fake_msvcrt)

        with pytest.raises(ValueError, match="boom"):
            with broker._project_file_lock():
                raise ValueError("boom")

        # unlock 仍被调
        assert any(c[0] == "LK_UNLCK" for c in locking_calls), \
            f"unlock 未调用；locking_calls={locking_calls}"
```

- [ ] **Step 2：跑 D1 验证 RED**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestI3LockBehavior -v -k "yields_immediately or yield_body_exception" 2>&1 | tail -10
```

期望：T1 + T2 **FAIL**（既有 _project_file_lock 用 LK_LOCK 不是 LK_NBLCK；fake_msvcrt 的 locking 在 LK_LOCK mode 不被验证）。

### Task B.4：写 D2 维度 — T3 + T4 + T5 + T6 RED

**Files:**
- 修改：`tests/test_sw_config_broker.py`（在 D1 测试后追加 4 方法）

- [ ] **Step 1：追加 D2 测试**

```python
    # ─── D2. 进度提示节奏（4 测试）───

    def test_lock_banner_printed_immediately_on_first_contention(
        self, monkeypatch, tmp_project_dir, capsys,
    ):
        """T3：spec §6.1 — 第 1 次 LK_NBLCK 抛 OSError → banner 立即印（不等 5s）。"""
        monkeypatch.setattr(_sys, "platform", "win32")
        locking_calls = []
        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=2)  # 2 次失败
        monkeypatch.setitem(_sys.modules, "msvcrt", fake_msvcrt)
        make_synced_time_mock(monkeypatch)

        with broker._project_file_lock():
            pass

        err = capsys.readouterr().err
        # banner 应在 t=0 立即印（等待 0s 即印）
        assert "检测到另一个 codegen" in err or "codegen" in err, f"banner 缺失；stderr={err}"
        assert "占用" in err

    def test_lock_no_progress_when_acquired_within_5s(
        self, monkeypatch, tmp_project_dir, capsys,
    ):
        """T4：spec §6.1 — 撞锁 3s 后拿到 → banner 印 1 次 + 进度行 0 行。"""
        monkeypatch.setattr(_sys, "platform", "win32")
        locking_calls = []
        # contention_count=6 → 6 次失败 × 0.5s = 3s 后第 7 次成功
        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=6)
        monkeypatch.setitem(_sys.modules, "msvcrt", fake_msvcrt)
        make_synced_time_mock(monkeypatch)

        with broker._project_file_lock():
            pass

        err = capsys.readouterr().err
        assert err.count("仍在等待锁释放") == 0, \
            f"撞锁 3s 不应印进度；stderr={err}"

    def test_lock_one_progress_at_5s_threshold(
        self, monkeypatch, tmp_project_dir, capsys,
    ):
        """T5：spec §6.1 — 撞锁 6s 后拿到 → banner 1 + 进度行 1 行（含 "已等 5s"）。"""
        monkeypatch.setattr(_sys, "platform", "win32")
        locking_calls = []
        # contention_count=12 → 12 × 0.5s = 6s 后第 13 次成功
        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=12)
        monkeypatch.setitem(_sys.modules, "msvcrt", fake_msvcrt)
        make_synced_time_mock(monkeypatch)

        with broker._project_file_lock():
            pass

        err = capsys.readouterr().err
        assert err.count("仍在等待锁释放") == 1, \
            f"撞锁 6s 应印 1 行进度；stderr={err}"
        assert "已等 5s" in err, f"进度行 elapsed 数不对；stderr={err}"

    def test_lock_progress_intervals_strictly_5s(
        self, monkeypatch, tmp_project_dir, capsys,
    ):
        """T6：spec §6.1 — 撞锁 16s 后拿到 → 进度行 3 行（5s/10s/15s 时刻）；
        4s/9s/14s 时刻不印。"""
        monkeypatch.setattr(_sys, "platform", "win32")
        locking_calls = []
        # contention_count=32 → 32 × 0.5s = 16s 后第 33 次成功
        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=32)
        monkeypatch.setitem(_sys.modules, "msvcrt", fake_msvcrt)
        make_synced_time_mock(monkeypatch)

        with broker._project_file_lock():
            pass

        err = capsys.readouterr().err
        progress_count = err.count("仍在等待锁释放")
        assert progress_count == 3, \
            f"撞锁 16s 应印 3 行进度（5/10/15s）；实际 {progress_count}；stderr={err}"
        for n in [5, 10, 15]:
            assert f"已等 {n}s" in err, f"缺 已等 {n}s；stderr={err}"
```

- [ ] **Step 2：跑 D2 验证 RED**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestI3LockBehavior -v -k "banner_printed or no_progress or one_progress or progress_intervals_strictly" 2>&1 | tail -10
```

期望：4 全 FAIL（既有 LK_LOCK 不进 retry 路径，没有 banner / 进度提示输出）。

### Task B.5：写 D3 + D4 维度 — T7 + T8 + T9 + T10 RED

**Files:**
- 修改：`tests/test_sw_config_broker.py`（追加 4 方法）

- [ ] **Step 1：追加 D3 + D4 测试**

```python
    # ─── D3. 永不超时（2 测试）───

    def test_lock_never_raises_timeout_at_60s_and_sleeps_between_polls(
        self, monkeypatch, tmp_project_dir,
    ):
        """T7：spec §6.1 — 撞锁 60s+ → 不抛 OSError + sleep 调用次数 ≥ 100
        + 每次 sleep == LOCK_POLL_INTERVAL_SEC（防 CPU busy loop / 间隔被改）。"""
        monkeypatch.setattr(_sys, "platform", "win32")
        locking_calls = []
        # contention_count=120 → 120 × 0.5s = 60s 后第 121 次成功
        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=120)
        monkeypatch.setitem(_sys.modules, "msvcrt", fake_msvcrt)

        # 自定义 mock 跟踪 sleep 调用
        sleep_calls = []
        fake_now = [0.0]

        def tracking_sleep(seconds):
            sleep_calls.append(seconds)
            fake_now[0] += seconds

        monkeypatch.setattr(broker.time, "sleep", tracking_sleep)
        monkeypatch.setattr(broker.time, "monotonic", lambda: fake_now[0])

        with broker._project_file_lock():
            pass

        assert len(sleep_calls) >= 100, \
            f"sleep 调用次数 {len(sleep_calls)} < 100（防 CPU busy loop）"
        assert all(s == broker.LOCK_POLL_INTERVAL_SEC for s in sleep_calls), \
            f"sleep 间隔不严格 {broker.LOCK_POLL_INTERVAL_SEC}s；首 5 个: {sleep_calls[:5]}"

    def test_lock_progress_count_matches_floor_elapsed_div_5(
        self, monkeypatch, tmp_project_dir, capsys,
    ):
        """T8：spec §6.1 — 撞锁 27s 后拿到 → 进度行恰 5 行（5/10/15/20/25 时刻）。"""
        monkeypatch.setattr(_sys, "platform", "win32")
        locking_calls = []
        # contention_count=54 → 54 × 0.5s = 27s 后第 55 次成功
        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=54)
        monkeypatch.setitem(_sys.modules, "msvcrt", fake_msvcrt)
        make_synced_time_mock(monkeypatch)

        with broker._project_file_lock():
            pass

        err = capsys.readouterr().err
        progress_count = err.count("仍在等待锁释放")
        assert progress_count == 5, \
            f"撞锁 27s 应印 5 行进度（5/10/15/20/25s）；实际 {progress_count}；stderr={err}"

    # ─── D4. Ctrl+C 中止（2 测试）───

    def test_lock_keyboard_interrupt_during_sleep_propagates(
        self, monkeypatch, tmp_project_dir,
    ):
        """T9：spec §6.1 — sleep 期间 raise KeyboardInterrupt → 立即上抛 +
        fp.close() 仍执行 + 不调 unlock（锁未拿到）。"""
        monkeypatch.setattr(_sys, "platform", "win32")
        locking_calls = []
        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=999)  # 永不成功
        monkeypatch.setitem(_sys.modules, "msvcrt", fake_msvcrt)

        def kbd_sleep(seconds):
            raise KeyboardInterrupt()
        monkeypatch.setattr(broker.time, "sleep", kbd_sleep)
        monkeypatch.setattr(broker.time, "monotonic", lambda: 0.0)

        with pytest.raises(KeyboardInterrupt):
            with broker._project_file_lock():
                pass

        # unlock 不应被调（锁从未拿到）
        unlock_count = sum(1 for c in locking_calls if c[0] == "LK_UNLCK")
        assert unlock_count == 0, f"锁未拿到不应 unlock；locking_calls={locking_calls}"

    def test_lock_keyboard_interrupt_after_lk_nblck_fails_propagates(
        self, monkeypatch, tmp_project_dir,
    ):
        """T10：spec §6.1 — LK_NBLCK 抛 OSError 后、进 sleep 前 raise KeyboardInterrupt
        → 立即上抛 + fp.close() 仍执行。"""
        monkeypatch.setattr(_sys, "platform", "win32")

        # locking 抛 OSError，print 抛 KeyboardInterrupt（在 sleep 之前）
        locking_calls = []
        def lk_nblck_fail(fd, mode, nbytes):
            locking_calls.append((mode, fd, nbytes))
            raise OSError("contended")

        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=0)
        fake_msvcrt.locking = lk_nblck_fail
        monkeypatch.setitem(_sys.modules, "msvcrt", fake_msvcrt)

        # print 抛 KeyboardInterrupt（在 banner 那一行）
        original_print = __builtins__["print"] if isinstance(__builtins__, dict) else __builtins__.print

        def kbd_print(*args, **kwargs):
            raise KeyboardInterrupt()

        monkeypatch.setattr("builtins.print", kbd_print)
        monkeypatch.setattr(broker.time, "monotonic", lambda: 0.0)

        with pytest.raises(KeyboardInterrupt):
            with broker._project_file_lock():
                pass
```

- [ ] **Step 2：跑 D3 + D4 验证 RED**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestI3LockBehavior -v -k "never_raises or progress_count_matches or keyboard_interrupt" 2>&1 | tail -12
```

期望：4 全 FAIL（_project_file_lock 还是 LK_LOCK 行为）。

### Task B.6：写 D5 维度 — T11 + T12 + T13 RED

**Files:**
- 修改：`tests/test_sw_config_broker.py`（追加 3 方法）

- [ ] **Step 1：追加 D5 测试**

```python
    # ─── D5. 清理路径（3 测试）───

    def test_lock_unlock_oserror_silently_warned(
        self, monkeypatch, tmp_project_dir, caplog,
    ):
        """T11：spec §6.1 — unlock 抛 OSError → log.warning 触发 + 不冒到 caller。"""
        import logging

        monkeypatch.setattr(_sys, "platform", "win32")
        locking_calls = []
        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=0)

        def fail_on_unlock(fd, mode, nbytes):
            locking_calls.append((mode, fd, nbytes))
            if mode == fake_msvcrt.LK_UNLCK:
                raise OSError("unlock failed")
            return None

        fake_msvcrt.locking = fail_on_unlock
        monkeypatch.setitem(_sys.modules, "msvcrt", fake_msvcrt)

        with caplog.at_level(logging.WARNING):
            with broker._project_file_lock():
                pass  # 不应抛

        assert any("unlock 异常" in rec.message for rec in caplog.records), \
            f"warn 缺；records={[r.message for r in caplog.records]}"

    def test_lock_unlock_non_oserror_propagates(
        self, monkeypatch, tmp_project_dir,
    ):
        """T12：spec §6.1 — unlock 抛 RuntimeError → 上抛（异常类型严格性，防"宽 except"）。"""
        monkeypatch.setattr(_sys, "platform", "win32")
        locking_calls = []
        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=0)

        def fail_on_unlock(fd, mode, nbytes):
            locking_calls.append((mode, fd, nbytes))
            if mode == fake_msvcrt.LK_UNLCK:
                raise RuntimeError("unexpected")
            return None

        fake_msvcrt.locking = fail_on_unlock
        monkeypatch.setitem(_sys.modules, "msvcrt", fake_msvcrt)

        with pytest.raises(RuntimeError, match="unexpected"):
            with broker._project_file_lock():
                pass

    def test_lock_path_with_chinese_chars_works(
        self, monkeypatch, tmp_path,
    ):
        """T13：spec §6.1 — lock_path 父目录路径含中文字符 → open + locking + unlock
        全程无 UnicodeError；Windows msvcrt 对 unicode 路径的支持回归。"""
        chinese_dir = tmp_path / "工作" / "项目"
        chinese_dir.mkdir(parents=True, exist_ok=True)

        # mock cad_paths.PROJECT_ROOT 指向中文目录
        import cad_paths
        monkeypatch.setattr(cad_paths, "PROJECT_ROOT", str(chinese_dir))

        monkeypatch.setattr(_sys, "platform", "win32")
        locking_calls = []
        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=0)
        monkeypatch.setitem(_sys.modules, "msvcrt", fake_msvcrt)

        with broker._project_file_lock():
            pass  # 不应抛 UnicodeError

        # 验证 lock 文件创建在中文目录
        lock_path = chinese_dir / ".cad-spec-gen" / broker.LOCK_FILE_NAME
        assert lock_path.exists(), f"lock 文件未创建于中文路径 {lock_path}"
```

- [ ] **Step 2：跑 D5 验证 RED**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestI3LockBehavior -v -k "unlock_oserror or unlock_non_oserror or chinese_chars" 2>&1 | tail -10
```

期望：T11 + T12 部分行为已是既有（OSError 被 catch / RuntimeError 上抛），但因 fake_msvcrt 用 LK_NBLCK 不是既有 LK_LOCK 路径，可能 FAIL；T13 PASS（既有路径处理 unicode 正常）。

### Task B.7：写 D6 + D7 + D8 维度 — T14-T18 RED

**Files:**
- 修改：`tests/test_sw_config_broker.py`（追加 5 方法）

- [ ] **Step 1：追加 D6/D7/D8 测试**

```python
    # ─── D6. 跨平台（2 测试）───

    def test_lock_noop_on_linux(self, monkeypatch, tmp_project_dir):
        """T14：spec §6.1 — sys.platform = "linux" → 静默 yield + 无 msvcrt 调用 + 无 banner / 进度。"""
        monkeypatch.setattr(_sys, "platform", "linux")

        # 设 msvcrt 为禁用 sentinel 让任何调用炸
        class FailMsvcrt:
            def __getattr__(self, name):
                raise AssertionError(f"msvcrt.{name} should NOT be accessed on Linux")

        monkeypatch.setitem(_sys.modules, "msvcrt", FailMsvcrt())

        entered = []
        with broker._project_file_lock():
            entered.append(True)

        assert entered == [True]

    def test_lock_noop_on_darwin(self, monkeypatch, tmp_project_dir):
        """T15：spec §6.1 — sys.platform = "darwin" → 同 T14。"""
        monkeypatch.setattr(_sys, "platform", "darwin")

        class FailMsvcrt:
            def __getattr__(self, name):
                raise AssertionError(f"msvcrt.{name} should NOT be accessed on macOS")

        monkeypatch.setitem(_sys.modules, "msvcrt", FailMsvcrt())

        entered = []
        with broker._project_file_lock():
            entered.append(True)

        assert entered == [True]

    # ─── D7. 文案完整性（2 测试）───

    def test_lock_banner_contains_all_required_keywords(
        self, monkeypatch, tmp_project_dir, capsys,
    ):
        """T16：spec §6.1 — banner stderr 包含全部 6 实体关键词组：
        codegen / 占用 / Ctrl+C / 删除 / 配置 / BOM。"""
        monkeypatch.setattr(_sys, "platform", "win32")
        locking_calls = []
        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=2)
        monkeypatch.setitem(_sys.modules, "msvcrt", fake_msvcrt)
        make_synced_time_mock(monkeypatch)

        with broker._project_file_lock():
            pass

        err = capsys.readouterr().err
        for kw in ["codegen", "占用", "Ctrl+C", "删除", "配置", "BOM"]:
            assert kw in err, f"banner 缺关键词 '{kw}'；stderr={err}"

    def test_lock_banner_contains_lock_file_path_literal(
        self, monkeypatch, tmp_project_dir, capsys,
    ):
        """T17：spec §6.1 — banner 含 lock_path 字面字符串。"""
        monkeypatch.setattr(_sys, "platform", "win32")
        locking_calls = []
        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=2)
        monkeypatch.setitem(_sys.modules, "msvcrt", fake_msvcrt)
        make_synced_time_mock(monkeypatch)

        with broker._project_file_lock():
            pass

        err = capsys.readouterr().err
        # tmp_project_dir 路径片段应在 banner 中
        assert str(tmp_project_dir) in err or ".cad-spec-gen" in err, \
            f"banner 缺 lock_path；stderr={err}"

    # ─── D8. 输出 channel（1 测试）───

    def test_lock_banner_and_progress_only_on_stderr(
        self, monkeypatch, tmp_project_dir, capsys,
    ):
        """T18：spec §6.1 — capsys: stdout 为空 / stderr 含 banner + 进度。"""
        monkeypatch.setattr(_sys, "platform", "win32")
        locking_calls = []
        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=12)  # 6s 撞锁
        monkeypatch.setitem(_sys.modules, "msvcrt", fake_msvcrt)
        make_synced_time_mock(monkeypatch)

        with broker._project_file_lock():
            pass

        captured = capsys.readouterr()
        assert captured.out == "", f"stdout 应为空；实际 {captured.out!r}"
        assert "codegen" in captured.err
        assert "仍在等待" in captured.err
```

- [ ] **Step 2：跑 D6/D7/D8 验证 RED**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestI3LockBehavior -v -k "noop_on or banner_contains or only_on_stderr" 2>&1 | tail -10
```

期望：T14 + T15 PASS（既有 sys.platform != "win32" 早返路径）；T16-T18 FAIL（既有无 banner / 进度）。

### Task B.8：跑全 18 I-3 测试拿 RED 总状态

**Files:** 无

- [ ] **Step 1：跑 I-3 全测试**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestI3LockBehavior -v --no-header 2>&1 | tail -25
```

预期 RED 状态（按 T 编号）：
- T1 FAIL（fake_msvcrt LK_NBLCK 既有不调）
- T2 FAIL（同 T1）
- T3-T8 FAIL（无 banner / 进度提示路径）
- T9-T10 FAIL（既有 LK_LOCK 不响应 KeyboardInterrupt 测试设计）
- T11-T12 PASS or FAIL 不定（既有 LK_UNLCK 行为部分一致）
- T13 PASS（既有 unicode 路径行为）
- T14-T15 PASS（既有 sys.platform 早返）
- T16-T18 FAIL（无 banner / stderr 输出）

**预期 RED 数 ≈ 12-13 fail / 5-6 pass**。

记录实际数 R1 = ?。

### Task B.9：重写 _project_file_lock 函数体

**Files:**
- 修改：`adapters/solidworks/sw_config_broker.py:634-664`（既有 _project_file_lock 函数体）

- [ ] **Step 1：用 Edit 工具替换整个 _project_file_lock 函数体**

精确替换（删除既有 line 634-664 函数体，含 docstring 与 finally 块）：

old:
```python
@contextlib.contextmanager
def _project_file_lock() -> Iterator[None]:
    """文件锁 <project>/.cad-spec-gen/lock（spec §6 并发跑 codegen）。

    Windows: msvcrt.locking 阻塞模式 LK_LOCK 获取独占锁；
    非 Windows: 静默 yield（无锁——CI Linux 单元测试不依赖真并发）。
    """
    if sys.platform != "win32":
        yield
        return

    import msvcrt

    # 函数内 import 与 _decisions_path 一致：让 tmp_project_dir 的 importlib.reload 生效
    from cad_paths import PROJECT_ROOT
    lock_path = Path(PROJECT_ROOT) / ".cad-spec-gen" / LOCK_FILE_NAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    fp = lock_path.open("a+b")
    try:
        # LK_LOCK = 阻塞模式获取独占锁（最多重试 ~10s 后抛 OSError）
        msvcrt.locking(fp.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            try:
                msvcrt.locking(fp.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError as e:
                log.warning("msvcrt unlock 异常（忽略）: %s", e)
    finally:
        fp.close()
```

new:
```python
@contextlib.contextmanager
def _project_file_lock() -> Iterator[None]:
    """文件锁 <project>/.cad-spec-gen/lock（spec §6 + PR #19 review I-3）。

    Windows: msvcrt.LK_NBLCK 非阻塞 + 永不超时 polling + 撞锁立即提示 + 每 5s 进度
    非 Windows: 静默 yield（CI Linux 单元测试不依赖真并发；产品 Windows-only）

    永不超时的理由（spec §3.4）：Windows msvcrt 锁 handle 与进程严格绑定，对方进程
    死必释放，不存在 stale lock。让用户用 Ctrl+C 主动控制，避免自动 hard fail 后引诱
    用户手动删锁文件造成 cache 数据竞争（损坏 spec_decisions.json → 下次跑用错配置 →
    SW 件 mismatch → 图像非照片级）。
    """
    if sys.platform != "win32":
        yield
        return

    import msvcrt

    # 函数内 import 与 _decisions_path 一致：让 tmp_project_dir 的 importlib.reload 生效
    from cad_paths import PROJECT_ROOT
    lock_path = Path(PROJECT_ROOT) / ".cad-spec-gen" / LOCK_FILE_NAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    fp = lock_path.open("a+b")
    try:
        wait_started_at = time.monotonic()
        last_progress_at = 0.0
        first_attempt = True
        while True:
            try:
                msvcrt.locking(fp.fileno(), msvcrt.LK_NBLCK, 1)
                break  # 拿到锁
            except OSError:
                now = time.monotonic()
                elapsed = now - wait_started_at
                if first_attempt:
                    print(
                        _LOCK_WAITING_BANNER.format(path=lock_path),
                        file=sys.stderr,
                        flush=True,
                    )
                    first_attempt = False
                    last_progress_at = now
                elif now - last_progress_at >= LOCK_PROGRESS_INTERVAL_SEC:
                    print(
                        f"⏳ 仍在等待锁释放...（已等 {int(elapsed)}s）",
                        file=sys.stderr,
                        flush=True,
                    )
                    last_progress_at = now
                time.sleep(LOCK_POLL_INTERVAL_SEC)

        try:
            yield
        finally:
            try:
                msvcrt.locking(fp.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError as e:
                log.warning("msvcrt unlock 异常（忽略）: %s", e)
    finally:
        fp.close()
```

- [ ] **Step 2：grep 验证函数体结构**

```bash
grep -n "msvcrt.LK_NBLCK\|msvcrt.LK_LOCK\|msvcrt.LK_UNLCK\|first_attempt\|wait_started_at\|_LOCK_WAITING_BANNER" adapters/solidworks/sw_config_broker.py
```

期望：
- LK_NBLCK 出现 1 次（新代码）
- LK_LOCK 出现 0 次（已删除）
- LK_UNLCK 出现 1 次（unlock 路径不变）
- first_attempt + wait_started_at + _LOCK_WAITING_BANNER 各出现 1+ 次（新逻辑）

### Task B.10：跑 18 I-3 测试 GREEN 验证

**Files:** 无

- [ ] **Step 1：跑 I-3 全测试**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestI3LockBehavior -v --no-header 2>&1 | tail -25
```

期望：**18 passed**。如有 fail，**逐个排查**不要继续。

- [ ] **Step 2：跑 broker 全测套确认 0 regression**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py -v --no-header 2>&1 | tail -3
```

期望：既有 + 14 (I-2) + 18 (I-3) = 全 PASS。

### Task B.11：跑全测套确认 baseline + 32 数字

**Files:** 无

- [ ] **Step 1：全测套**

```bash
.venv/Scripts/python.exe -m pytest -q \
  --ignore=tests/test_a2_integration.py \
  --ignore=tests/test_part_templates.py \
  2>&1 | tail -3
```

期望：`1283 passed, ... 35 failed, 32 skipped, ... 13 errors`（baseline 1251 + 32 新）。

记录实际：?

### Task B.12：Commit 2（I-3 修复）

**Files:**
- 修改：`adapters/solidworks/sw_config_broker.py`
- 修改：`tests/test_sw_config_broker.py`

- [ ] **Step 1：git status 确认**

```bash
git status -s
```

期望：仅 `M adapters/solidworks/sw_config_broker.py` + `M tests/test_sw_config_broker.py`。

- [ ] **Step 2：commit**

```bash
git add adapters/solidworks/sw_config_broker.py tests/test_sw_config_broker.py
git commit -m "$(cat <<'EOF'
fix(sw_config_broker): I-3 锁等待永不超时 + 进度提示（PR #19 review fix）

_project_file_lock 重写为 msvcrt.LK_NBLCK 非阻塞 + 永不超时 polling + 撞锁
立即印 banner（含 6 实体关键词 codegen/占用/Ctrl+C/删除/配置/BOM 警告勿删
锁文件）+ 每 5s 进度提示。

修复前：msvcrt.LK_LOCK 阻塞模式 ~10s 后抛 raw OSError 给用户面，违反"傻瓜式"
gate；急切用户撞 hard fail 会去手动删锁文件 → 与持锁 holder 并发改 cache →
spec_decisions.json 损坏 → 下次 codegen 用错配置 → SW 件 mismatch → 图像
非照片级。

修复后：永不超时 + 用户 Ctrl+C 主动控制，对齐"照片级 > 傻瓜式"原则。
LK_NBLCK + time.sleep(0.5) polling 让 KeyboardInterrupt 能立即中断；
banner 文案明确警告勿删锁文件防 cache 数据竞争。

新增 18 测试 / 8 行为维度（spec §6.1）：
- D1 happy path: T1 (uncontended) + T2 (yield body 异常仍释放)
- D2 进度提示节奏: T3 (banner 立即) + T4 (5s 内无进度) + T5 (6s 1 行) + T6 (16s 3 行严格 5s 间隔)
- D3 永不超时: T7 (60s 不抛 + sleep call count ≥100 防 busy loop) + T8 (27s 5 行进度)
- D4 Ctrl+C 中止: T9 (sleep 期间) + T10 (LK_NBLCK 后 print 期间)
- D5 清理路径: T11 (unlock OSError silent) + T12 (unlock RuntimeError 上抛) + T13 (中文路径 unicode)
- D6 跨平台: T14 (Linux noop) + T15 (macOS noop)
- D7 文案完整性: T16 (6 实体关键词) + T17 (lock_path 字面值)
- D8 输出 channel: T18 (仅 stderr 不污染 stdout)

新增 2 模块级常量 LOCK_POLL_INTERVAL_SEC=0.5 / LOCK_PROGRESS_INTERVAL_SEC=5
+ 1 文案常量 _LOCK_WAITING_BANNER + 1 import time。

mock 模板按 spec §6.4：fake_msvcrt setitem 跨平台 + time.monotonic-by-sleep
同步推进（防 busy loop bug 漏测）。

spec: docs/superpowers/specs/2026-04-26-sw-config-broker-i2-i3-fix-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git log --oneline -5
```

期望：新 commit 在 HEAD，3 commit 历史链清晰。

---

## Phase C — spec close（commit 3）

### Task C.1：改 cache-design spec §11 标 closed

**Files:**
- 修改：`docs/superpowers/specs/2026-04-26-sw-toolbox-config-list-cache-design.md`

- [ ] **Step 1：grep §11 内容找到 I-2 + I-3 行**

```bash
grep -n "I-2\|I-3" docs/superpowers/specs/2026-04-26-sw-toolbox-config-list-cache-design.md
```

记录 I-2 / I-3 所在行号。

- [ ] **Step 2：用 Edit 工具改 §11 中 I-2 + I-3 两条标 closed**

精确替换 I-2 行（从 grep 结果取 old_string 实际文本，下面是模板，需按实际微调）：

例如，若 §11 含 `- **I-2 envelope 升级未持久化**：worker fail 时 in-memory cache 升级 envelope 但不写盘 → 下次 prewarm 重复无效检查。修复：envelope invalidated 时先 save empty cache 再尝试 worker spawn。`

改为：
`- ~~**I-2 envelope 升级未持久化**：worker fail 时 in-memory cache 升级 envelope 但不写盘 → 下次 prewarm 重复无效检查。修复：envelope invalidated 时先 save empty cache 再尝试 worker spawn。~~ ✅ **closed (2026-04-26)**：见 [I-2 + I-3 修复设计](2026-04-26-sw-config-broker-i2-i3-fix-design.md)`

类似处理 I-3。

- [ ] **Step 3：grep 验证 closed 标记**

```bash
grep -n "closed (2026-04-26)\|sw-config-broker-i2-i3-fix-design" docs/superpowers/specs/2026-04-26-sw-toolbox-config-list-cache-design.md
```

期望：2 行匹配（I-2 + I-3 各 1 行）。

### Task C.2：Commit 3（spec close）

**Files:**
- 修改：`docs/superpowers/specs/2026-04-26-sw-toolbox-config-list-cache-design.md`

- [ ] **Step 1：commit**

```bash
git add docs/superpowers/specs/2026-04-26-sw-toolbox-config-list-cache-design.md
git commit -m "$(cat <<'EOF'
docs(spec): I-2 + I-3 §11 follow-up 标 closed

PR #19 self-review §11 follow-up 中的 I-2（envelope 升级未持久化）+ I-3（msvcrt
锁无重试 UX）已在本 PR 修复。spec §11 中 I-2 + I-3 条目标 closed (2026-04-26)
+ 反向链接到本次修复设计 spec。

仍 open 的 §11 follow-up（推迟到下个 PR）：I-4 mtime+size collision /
M-1 fsync / M-2 _save_config_lists_cache 异常上抛 / M-3 import 不对称 /
M-4 transient COM 永久缓存 / M-5 timeout 缩放 / M-6 detect_solidworks 重复 import /
M-7 INVALIDATION_REASONS 校验。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git log --oneline -5
```

期望：4 commit 历史链：
```
<C2 sha> docs(spec): I-2 + I-3 §11 follow-up 标 closed
<B12 sha> fix(sw_config_broker): I-3 锁等待永不超时 + 进度提示...
<A11 sha> fix(sw_config_broker): I-2 envelope 升级立即落盘...
8de8984 docs(spec): I-2/I-3 spec 第三轮敌对审查修订...
```

---

## Phase D — PR + CI

### Task D.1：push branch + 开 PR

**Files:** 无

- [ ] **Step 1：push feature branch**

```bash
git push -u origin feat/sw-config-broker-i2-i3-fix
```

期望：远程建立 tracking branch。

- [ ] **Step 2：开 PR**

```bash
gh pr create --title "fix(sw_config_broker): I-2 + I-3 PR #19 review followup" --body "$(cat <<'EOF'
## Summary
- **I-2**: envelope 升级决策立即持久化，避免 worker 失败导致死循环 invalidate
- **I-3**: 锁等待永不超时 + Ctrl+C 友好 + 文案防误删锁文件，对齐"照片级 > 傻瓜式"原则

## 关联
- spec: docs/superpowers/specs/2026-04-26-sw-config-broker-i2-i3-fix-design.md（3 轮 self-review + 1 轮 subagent 敌对审查）
- 跟进 PR #19 self-review §11 follow-up
- close cache-design spec §11 中 I-2 + I-3

## Test plan
- 新增 32 测试（I-3: 18 / I-2: 14）按 15 个行为维度详尽覆盖
- 总 1283 passed (本地 baseline 1251 + 32 new)
- CI 7/7 全平台绿
- mock 模板：fake_msvcrt setitem 跨平台 / tracking_save + failing_save 双模板 / time.monotonic-by-sleep 同步推进

## Test plan checklist
- [ ] CI Ubuntu / Windows / macOS 全平台绿
- [ ] 本地 .venv pytest 1283 passed
- [ ] git log 显示 3 commit 干净
- [ ] no new ruff / mypy 警告

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

期望：PR URL 返回。

### Task D.2：等 CI 全绿验证

**Files:** 无

- [ ] **Step 1：查 CI 状态**

```bash
gh pr view --json statusCheckRollup -q '.statusCheckRollup[].conclusion' | sort -u
```

期望（最终）：仅 `SUCCESS`（且仅 SUCCESS）。

- [ ] **Step 2：如 CI 红，看具体 fail job**

```bash
gh pr view --json statusCheckRollup
```

排查方式：
- Linux fail：常见是 fake_msvcrt 没正确 mock 真 import；查 §6.4 setitem 模式
- Windows fail：常见是 sys.platform mock 与真 platform 冲突；查 monkeypatch.setattr 顺序
- macOS fail：同 Linux

修复后 push 同分支自动重跑 CI。

---

## 完成验收（与 spec §8 对齐）

### 功能验收
- [ ] I-3：撞锁 → 立即印 banner（含 6 实体关键词 + lock_path）+ 每 5s 进度 + 永不超时 + Ctrl+C 立即上抛
- [ ] I-3：unlock OSError 静默 / 非 OSError 上抛
- [ ] I-3：非 Windows 静默 yield
- [ ] I-2：envelope_invalidated → save 在 worker spawn 之前 → 第 2 次 prewarm 不再 invalidate
- [ ] I-2：save 失败 warn + 继续；非 Exception 异常上抛
- [ ] I-2：detect SW 未装时仍 save sw_version=0
- [ ] I-2：CAD_SW_BROKER_DISABLE=1 整函数早返

### 测试验收
- [ ] 32 新测试 100% pass
- [ ] 既有 1251 测试 0 regression
- [ ] CI 7/7 SUCCESS

### 代码质量验收
- [ ] 改动 surgical（仅 1 文件 + 2 函数 + 32 测试 + 1 import + 3 常量）
- [ ] 不破坏既有"血管"

### 文档验收
- [ ] 本 plan + spec commit 入库
- [ ] PR #19 cache-design spec §11 标 I-2 / I-3 closed + 反向链接
- [ ] PR 描述完整含 summary / 关联 / 测试

---

## Self-Review Checklist（plan 自审）

在执行 plan 前，跑过这个 checklist：

1. **每 task 是否 2-5 分钟**：✓ Phase A 11 task / Phase B 12 task / Phase C 2 task / Phase D 2 task = 27 task，每 task 平均 3-5 分钟
2. **是否 placeholder**：✓ 所有测试代码完整（没有 "类似 T19" 简略）；所有 commit message 完整；所有 grep / pytest 命令完整含期望输出
3. **类型一致性**：✓ TestI2EnvelopePersistence / TestI3LockBehavior class 名 + make_fake_msvcrt / make_failing_save / make_tracking_save / make_synced_time_mock helper 名跨 task 一致
4. **spec 覆盖完整**：✓ §3 / §4 / §5 / §6 全部 32 测试落地 / §7 commit 拆分 / §8 验收 / §9 实施顺序

如发现 gap，**修 plan 不修 spec**（spec 已批不动）。
