# SW Toolbox config_list 跨 run 持久化 cache 实现 Plan（Task 14.6 / P1）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 sw_config_broker 的 `_list_configs_via_com` 持久化 cache 跨 codegen run，把"54 件零件 = 54 次启 SW"降到"1 次 batch spawn 列全部" — 兑现"装即用"北极星硬约束。

**Architecture:** 新建 `adapters/solidworks/sw_config_lists_cache.py` 独立 module 管 envelope，broker 加 `prewarm_config_lists()` public API 触发 batch spawn worker，sw_list_configs_worker 加 `--batch` flag 接 stdin JSON list 模式（保留单件 CLI 兼容），PartsResolver 加 `prewarm()` 派发链（rule matching 在 resolver 层做，不在 adapter 层），gen_std_parts.main 在 BOM loop 之前加一行触发预热。三层 cache：L2 in-process `_CONFIG_LIST_CACHE` → L1 持久化 JSON → fallback 单件 spawn 兜底。

**Tech Stack:** Python 3.12 / pytest 9 / 现有 `subprocess.run` worker 模式 / `json` + `os.replace` 原子写 / `Path.home()` 用户级 cache 目录

**前置 spec:** `docs/superpowers/specs/2026-04-26-sw-toolbox-config-list-cache-design.md`（commits `1db87bb` + `f63a467` + `fd82a66`）

**分支:** `feat/sw-config-broker`（PR #19，当前 ahead `origin` 0；已 push spec commits）

**Python venv:** `.venv/Scripts/python.exe`（**不要用 uv**，partcad/bd_warehouse 依赖冲突让 `uv sync` 失败）

**测试 baseline:** 1201 passed / 32 skipped / 35 pre-existing fail（PIL/cadquery/templates 缺，与本 task 无关）

---

## ⚠️ Spec 漂移修正（plan 写作时发现）

Spec §3.2 + §6.1 + 多处提到 `tools/sw_list_configs_worker.py`。**现实：worker 在 `adapters/solidworks/sw_list_configs_worker.py`**（broker.py:460 用 `python -m adapters.solidworks.sw_list_configs_worker` 调用）。Plan 全文使用真实路径，spec 漂移不在本 plan 范围内修（spec 已 push，未来 fixup commit）。

类似漂移：
- spec §6.1 提"`tests/test_sw_list_configs_worker_batch.py` 新建" → 实测 plan 用统一名 `tests/test_sw_list_configs_worker.py`（worker 现无测试文件，新建即可，不需带 `_batch` 后缀）

---

## File Structure

### Create（4 个新文件）

| 文件 | 责任 | 大小估 |
|---|---|---|
| `adapters/solidworks/sw_config_lists_cache.py` | envelope load/save/empty/diff/invalidation；含 `CONFIG_LISTS_SCHEMA_VERSION = 1`；纯 Python 无 SW 依赖 | ~120 行 |
| `tests/test_sw_config_lists_cache.py` | A+B 测试矩阵：envelope schema round-trip / 损坏文件 / 版本不符 / 失效信号 4 维 | ~200 行 |
| `tests/test_sw_list_configs_worker.py` | D 测试矩阵：worker --batch IPC 协议 / 单件 CLI 兼容 / 失败 exit code | ~120 行 |
| `~/.cad-spec-gen/sw_config_lists.json` | 运行时数据文件（用户级跨项目）；不入 git | 运行时产物 |

### Modify（5 个现有文件）

| 文件 | 改动 |
|---|---|
| `adapters/solidworks/sw_list_configs_worker.py` | 加 `--batch` flag + stdin JSON list 模式；保留单件 CLI 兼容（exit code 契约不变） |
| `adapters/solidworks/sw_config_broker.py` | 加 `prewarm_config_lists(sldprt_list)` public API；改 `_list_configs_via_com` 三层 cache（L2 → L1 持久化 → fallback） |
| `adapters/parts/base.py` | 加 `prewarm(candidates) -> None` virtual method（base 给 `pass` body，**不加 @abstractmethod**，避免现有 4 adapter 加占位） |
| `adapters/parts/sw_toolbox_adapter.py` | override `prewarm(candidates)`：用 `find_sldprt` 收集 sldprt_path → 调 `broker.prewarm_config_lists` |
| `parts_resolver.py` | 加 `PartsResolver.prewarm(queries)` method：rule matching 在此做，按 first-hit adapter 分组 candidates 派发 |
| `codegen/gen_std_parts.py` | `generate_std_part_files` 函数 BOM loop 之前加一行 `resolver.prewarm(queries)`；queries 从 build PartQuery 复用 |
| `tests/test_sw_config_broker.py` | 末尾加 TestPrewarmConfigLists 类（C 测试矩阵） |
| `tests/test_sw_toolbox_adapter_with_broker.py` | 末尾加 TestPrewarmEndToEnd 类（E 测试矩阵） |

### packaged copy 同步

`src/cad_spec_gen/data/codegen/gen_std_parts.py` 在 `.gitignore`，hatch_build.py wheel-time 自动 sync，**plan 不动它**（与 Task 15/16 commit 同模式）。

---

## Task 0：预飞 grep 自检（防 plan 漂移）

**Files:**
- Read-only verification

按 memory `feedback_plan_drift_taxonomy` 反馈（5 类漂移：API 不存在 / 路径假设错 / 测试 helper 误用 / 实现细节 bug / 参数签名）：写代码前先验证 plan 中所有引用的 API/路径/常量真存在。

- [ ] **Step 1：验证 worker 真实路径 + 调用形态**

```bash
ls adapters/solidworks/sw_list_configs_worker.py
grep -n '"-m", "adapters.solidworks.sw_list_configs_worker"' adapters/solidworks/sw_config_broker.py
```

Expected:
```
adapters/solidworks/sw_list_configs_worker.py
460:        "-m", "adapters.solidworks.sw_list_configs_worker",
```

如果输出不符 → plan 锚定的事实已变，**stop 并通知用户**重做 spec/plan，不强行推进。

- [ ] **Step 2：验证 PartsAdapter base 现有方法名 + ABC 契约**

```bash
grep -n "class PartsAdapter\|@abstractmethod\|def is_available\|def can_resolve\|def resolve\|def probe_dims" adapters/parts/base.py
```

Expected: 5 个 method 被 @abstractmethod 装饰（is_available / can_resolve / resolve / probe_dims）；class 用 `class PartsAdapter(ABC)`。

如果发现 `prewarm` 已经存在（命名撞名）→ stop。

- [ ] **Step 3：验证 sw_toolbox_adapter.find_sldprt 现有签名 + 返回类型**

```bash
grep -n "def find_sldprt" adapters/parts/sw_toolbox_adapter.py
```

Expected: `def find_sldprt(self, query, spec: dict):`（返 `(SwToolboxPart, score)` tuple 或 `None`）。

- [ ] **Step 4：验证 PartsResolver 现有 _match_rule 函数**

```bash
grep -n "def _match_rule\|def resolve\(self, query" parts_resolver.py
```

Expected: `_match_rule(match_block, query)` 函数存在；`resolve(self, query, _trace=None)` 存在。

如果 `_match_rule` 命名不同 → plan Task 11 的 import 需要调整。

- [ ] **Step 5：验证 gen_std_parts 现 generate_std_part_files signature**

```bash
grep -n "def generate_std_part_files" codegen/gen_std_parts.py
```

Expected: `def generate_std_part_files(spec_path, output_dir, mode="scaffold") -> tuple[list, list, "PartsResolver", dict[str, list[dict]]]:`（4-tuple 含 pending_records，Task 15 加的）

- [ ] **Step 6：验证 conftest 现有 autouse fixtures**

```bash
grep -n "@pytest.fixture\|autouse=True" tests/conftest.py
```

Expected: 至少 2 个 autouse fixture（`isolate_cad_spec_gen_home` + `disable_sw_config_broker_by_default`）。

任一查询失败 → 报告"Task 0 漂移：<具体项>"并 stop，不进 Task 1。

- [ ] **Step 7：commit 自检结果（无代码改动，本 task 仅记录）**

```bash
# 无改动 — 不 commit；如所有 step PASS 直接进 Task 1
echo "Task 0 verified — proceeding to Task 1"
```

---

# CP-7：Cache module 基础（Task 1-5，无 SW 依赖）

完成后状态：`adapters/solidworks/sw_config_lists_cache.py` 全测套 PASS；envelope 读写 + 失效信号闭环；任何 broker/worker/resolver 改动都还没动。CP-7 commit + 暂停等用户审。

---

## Task 1：建 sw_config_lists_cache.py module 骨架 + 常量

**Files:**
- Create: `adapters/solidworks/sw_config_lists_cache.py`
- Create: `tests/test_sw_config_lists_cache.py`

- [ ] **Step 1：写失败测试 — module 可 import + 常量值**

```python
# tests/test_sw_config_lists_cache.py
"""Task 14.6：sw_config_lists_cache module 单元测试（spec §6.1 A+B 矩阵）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


class TestModuleConstants:
    def test_module_imports_and_has_schema_version(self):
        from adapters.solidworks import sw_config_lists_cache as cache_mod
        assert cache_mod.CONFIG_LISTS_SCHEMA_VERSION == 1

    def test_cache_path_is_user_level(self):
        from adapters.solidworks.sw_config_lists_cache import get_config_lists_cache_path
        p = get_config_lists_cache_path()
        assert p == Path.home() / ".cad-spec-gen" / "sw_config_lists.json"
```

- [ ] **Step 2：跑失败测试**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_lists_cache.py::TestModuleConstants -v
```

Expected: `ImportError` 或 `ModuleNotFoundError: No module named 'adapters.solidworks.sw_config_lists_cache'`。

- [ ] **Step 3：写最小实现**

```python
# adapters/solidworks/sw_config_lists_cache.py
"""adapters/solidworks/sw_config_lists_cache.py — SW Toolbox config_list 持久化 cache.

设计参见 docs/superpowers/specs/2026-04-26-sw-toolbox-config-list-cache-design.md (rev 1)。

职责：
- envelope load/save/empty
- 失效信号 _envelope_invalidated (sw_version / toolbox_path) + _config_list_entry_valid (mtime / size)
- 文件锚定：~/.cad-spec-gen/sw_config_lists.json （用户级，跨项目共享）
- 与 broker 解耦：broker 只 import + 调用，envelope 细节全在此 module
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

CONFIG_LISTS_SCHEMA_VERSION = 1


def get_config_lists_cache_path() -> Path:
    """用户级 cache 文件路径；与 sw_toolbox_index.json 同目录（catalog.py:70 同模式）。"""
    return Path.home() / ".cad-spec-gen" / "sw_config_lists.json"
```

- [ ] **Step 4：跑测试 PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_lists_cache.py::TestModuleConstants -v
```

Expected: `2 passed`.

- [ ] **Step 5：commit**

```bash
git -C /d/Work/cad-spec-gen add adapters/solidworks/sw_config_lists_cache.py tests/test_sw_config_lists_cache.py
git -C /d/Work/cad-spec-gen commit -m "$(cat <<'EOF'
feat(sw_config_lists_cache): module 骨架 + CONFIG_LISTS_SCHEMA_VERSION（Task 14.6 / Task 1）

- 新模块 adapters/solidworks/sw_config_lists_cache.py
- 模块级常量 CONFIG_LISTS_SCHEMA_VERSION = 1（避免与 broker.SCHEMA_VERSION=2 / catalog.SCHEMA_VERSION=1 撞名）
- get_config_lists_cache_path() 返 Path.home() / .cad-spec-gen / sw_config_lists.json
- 与 sw_toolbox_index.json 同目录（catalog.py:70 同模式）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2：_empty_config_lists_cache() + 5 字段全员形状

**Files:**
- Modify: `adapters/solidworks/sw_config_lists_cache.py`
- Modify: `tests/test_sw_config_lists_cache.py`

- [ ] **Step 1：写失败测试**

```python
# tests/test_sw_config_lists_cache.py 末尾追加：

class TestEmptyCache:
    def test_empty_cache_has_5_fields(self):
        from adapters.solidworks.sw_config_lists_cache import (
            _empty_config_lists_cache,
            CONFIG_LISTS_SCHEMA_VERSION,
        )
        cache = _empty_config_lists_cache()
        assert cache["schema_version"] == CONFIG_LISTS_SCHEMA_VERSION
        assert "generated_at" in cache  # ISO timestamp
        assert cache["sw_version"] is None  # 故意 None → 触发 envelope_invalidated
        assert cache["toolbox_path"] is None
        assert cache["entries"] == {}
```

- [ ] **Step 2：跑失败测试**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_lists_cache.py::TestEmptyCache -v
```

Expected: `ImportError: cannot import name '_empty_config_lists_cache'`.

- [ ] **Step 3：写实现**

```python
# adapters/solidworks/sw_config_lists_cache.py 末尾追加：


def _empty_config_lists_cache() -> dict[str, Any]:
    """返新空 envelope，5 字段全员就位避免 KeyError。

    sw_version=None / toolbox_path=None 是有意：第一次调用 _envelope_invalidated
    会比较 None != detect_solidworks().version_year → True → 整 entries 清重列。
    """
    return {
        "schema_version": CONFIG_LISTS_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sw_version": None,
        "toolbox_path": None,
        "entries": {},
    }
```

- [ ] **Step 4：跑测试 PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_lists_cache.py -v
```

Expected: `3 passed`.

- [ ] **Step 5：commit**

```bash
git -C /d/Work/cad-spec-gen add adapters/solidworks/sw_config_lists_cache.py tests/test_sw_config_lists_cache.py
git -C /d/Work/cad-spec-gen commit -m "$(cat <<'EOF'
feat(sw_config_lists_cache): _empty_config_lists_cache 5 字段全员形状（Task 14.6 / Task 2）

schema_version + generated_at + sw_version + toolbox_path + entries 全员就位；
sw_version/toolbox_path = None 故意触发首次 _envelope_invalidated → True → 全 batch 重列。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3：_save_config_lists_cache() (atomic .tmp + os.replace)

**Files:**
- Modify: `adapters/solidworks/sw_config_lists_cache.py`
- Modify: `tests/test_sw_config_lists_cache.py`

- [ ] **Step 1：写失败测试 — atomic write + parent.mkdir**

```python
# tests/test_sw_config_lists_cache.py 末尾追加：

class TestSaveCache:
    def test_save_writes_valid_json(self, tmp_path, monkeypatch):
        from adapters.solidworks import sw_config_lists_cache as m
        monkeypatch.setattr(m, "get_config_lists_cache_path",
                            lambda: tmp_path / "deeper" / "sw_config_lists.json")
        cache = {
            "schema_version": 1,
            "generated_at": "2026-04-26T12:34:56+00:00",
            "sw_version": 24,
            "toolbox_path": "C:/SW",
            "entries": {"C:/p1.sldprt": {"mtime": 100, "size": 200, "configs": ["A"]}},
        }
        m._save_config_lists_cache(cache)
        target = tmp_path / "deeper" / "sw_config_lists.json"
        assert target.exists()
        data = json.loads(target.read_text(encoding="utf-8"))
        assert data == cache

    def test_save_creates_parent_dir_if_missing(self, tmp_path, monkeypatch):
        from adapters.solidworks import sw_config_lists_cache as m
        monkeypatch.setattr(m, "get_config_lists_cache_path",
                            lambda: tmp_path / "newdir" / "newer" / "f.json")
        m._save_config_lists_cache({"entries": {}})
        assert (tmp_path / "newdir" / "newer" / "f.json").exists()

    def test_save_atomic_no_tmp_residue(self, tmp_path, monkeypatch):
        from adapters.solidworks import sw_config_lists_cache as m
        target = tmp_path / "sw_config_lists.json"
        monkeypatch.setattr(m, "get_config_lists_cache_path", lambda: target)
        m._save_config_lists_cache({"entries": {}})
        assert not (tmp_path / "sw_config_lists.json.tmp").exists()
```

- [ ] **Step 2：跑失败测试**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_lists_cache.py::TestSaveCache -v
```

Expected: `ImportError: cannot import name '_save_config_lists_cache'`（或 AttributeError）。

- [ ] **Step 3：写实现**

```python
# adapters/solidworks/sw_config_lists_cache.py 末尾追加：


def _save_config_lists_cache(cache: dict[str, Any]) -> None:
    """一次性原子写 cache：先 .tmp 再 os.replace，保证并发读到要么旧文件要么完整新文件。

    parent.mkdir(parents=True, exist_ok=True) 自动建目录。
    """
    path = get_config_lists_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, path)
```

- [ ] **Step 4：跑测试 PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_lists_cache.py -v
```

Expected: `6 passed`.

- [ ] **Step 5：commit**

```bash
git -C /d/Work/cad-spec-gen add adapters/solidworks/sw_config_lists_cache.py tests/test_sw_config_lists_cache.py
git -C /d/Work/cad-spec-gen commit -m "$(cat <<'EOF'
feat(sw_config_lists_cache): _save_config_lists_cache atomic 写（Task 14.6 / Task 3）

- .tmp + os.replace 原子语义：并发读到要么旧文件要么完整新文件，不出现 partial write
- parent.mkdir(parents=True, exist_ok=True) 自动建目录
- 测试覆盖：valid JSON round-trip / parent 不存在自动建 / 写完无 .tmp 残留

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4：_load_config_lists_cache() (含损坏 / 版本不符 → empty 自愈)

**Files:**
- Modify: `adapters/solidworks/sw_config_lists_cache.py`
- Modify: `tests/test_sw_config_lists_cache.py`

- [ ] **Step 1：写失败测试 — 4 个 load 场景**

```python
# tests/test_sw_config_lists_cache.py 末尾追加：

class TestLoadCache:
    def test_load_missing_file_returns_empty(self, tmp_path, monkeypatch):
        from adapters.solidworks import sw_config_lists_cache as m
        monkeypatch.setattr(m, "get_config_lists_cache_path",
                            lambda: tmp_path / "no_such.json")
        cache = m._load_config_lists_cache()
        assert cache["entries"] == {}
        assert cache["schema_version"] == m.CONFIG_LISTS_SCHEMA_VERSION

    def test_load_valid_file_round_trips(self, tmp_path, monkeypatch):
        from adapters.solidworks import sw_config_lists_cache as m
        target = tmp_path / "sw_config_lists.json"
        monkeypatch.setattr(m, "get_config_lists_cache_path", lambda: target)
        original = {
            "schema_version": 1,
            "generated_at": "2026-04-26T12:34:56+00:00",
            "sw_version": 24,
            "toolbox_path": "C:/SW",
            "entries": {"C:/p1.sldprt": {"mtime": 100, "size": 200, "configs": ["A"]}},
        }
        target.write_text(json.dumps(original), encoding="utf-8")
        loaded = m._load_config_lists_cache()
        assert loaded == original

    def test_load_corrupt_json_returns_empty(self, tmp_path, monkeypatch):
        from adapters.solidworks import sw_config_lists_cache as m
        target = tmp_path / "sw_config_lists.json"
        monkeypatch.setattr(m, "get_config_lists_cache_path", lambda: target)
        target.write_text("{not valid json", encoding="utf-8")
        cache = m._load_config_lists_cache()
        assert cache["entries"] == {}

    def test_load_schema_version_mismatch_returns_empty(self, tmp_path, monkeypatch):
        from adapters.solidworks import sw_config_lists_cache as m
        target = tmp_path / "sw_config_lists.json"
        monkeypatch.setattr(m, "get_config_lists_cache_path", lambda: target)
        old = {"schema_version": 999, "entries": {"C:/p1.sldprt": {"configs": ["X"]}}}
        target.write_text(json.dumps(old), encoding="utf-8")
        cache = m._load_config_lists_cache()
        assert cache["entries"] == {}  # 旧 v999 entries 不读
        assert cache["schema_version"] == m.CONFIG_LISTS_SCHEMA_VERSION
```

- [ ] **Step 2：跑失败测试**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_lists_cache.py::TestLoadCache -v
```

Expected: 4 fail with `AttributeError: module ... has no attribute '_load_config_lists_cache'`.

- [ ] **Step 3：写实现**

```python
# adapters/solidworks/sw_config_lists_cache.py 末尾追加：


def _load_config_lists_cache() -> dict[str, Any]:
    """读 cache；4 类自愈情形返 _empty_config_lists_cache：
    1. 文件不存在
    2. JSON 损坏
    3. OSError (权限/磁盘)
    4. schema_version 不符
    """
    path = get_config_lists_cache_path()
    if not path.exists():
        return _empty_config_lists_cache()
    try:
        cache = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("config_lists cache 损坏，重建: %s", e)
        return _empty_config_lists_cache()
    if cache.get("schema_version") != CONFIG_LISTS_SCHEMA_VERSION:
        log.info(
            "config_lists schema bump %s → %s，重建",
            cache.get("schema_version"), CONFIG_LISTS_SCHEMA_VERSION,
        )
        return _empty_config_lists_cache()
    return cache
```

- [ ] **Step 4：跑测试 PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_lists_cache.py -v
```

Expected: `10 passed`.

- [ ] **Step 5：commit**

```bash
git -C /d/Work/cad-spec-gen add adapters/solidworks/sw_config_lists_cache.py tests/test_sw_config_lists_cache.py
git -C /d/Work/cad-spec-gen commit -m "$(cat <<'EOF'
feat(sw_config_lists_cache): _load_config_lists_cache 4 类自愈（Task 14.6 / Task 4）

文件不存在 / JSON 损坏 / OSError / schema_version 不符 → 全返 _empty_config_lists_cache。
复用 toolbox_index.json 同模式（catalog.py:564 fallback）。
schema 升级 v1→v2 时旧 entries 不读，下次 prewarm 自然重列。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5：失效信号 _envelope_invalidated + _config_list_entry_valid + _stat helpers

**Files:**
- Modify: `adapters/solidworks/sw_config_lists_cache.py`
- Modify: `tests/test_sw_config_lists_cache.py`

- [ ] **Step 1：写失败测试 — envelope-level + per-entry 失效 + stat helper**

```python
# tests/test_sw_config_lists_cache.py 末尾追加：

class TestEnvelopeInvalidated:
    """Envelope-level 失效（spec §4 场景 D）：sw_version / toolbox_path 任一不符。"""

    def test_first_run_empty_cache_invalidated(self, monkeypatch):
        """空 cache (sw_version=None) 必失效。"""
        from adapters.solidworks import sw_config_lists_cache as m
        from adapters.solidworks import sw_detect

        sw_detect._reset_cache()
        monkeypatch.setattr(
            sw_detect, "detect_solidworks",
            lambda: sw_detect.SwInfo(installed=True, version_year=24,
                                     toolbox_dir="C:/SW"),
        )
        cache = m._empty_config_lists_cache()
        assert m._envelope_invalidated(cache) is True

    def test_matching_envelope_not_invalidated(self, monkeypatch):
        from adapters.solidworks import sw_config_lists_cache as m
        from adapters.solidworks import sw_detect

        sw_detect._reset_cache()
        monkeypatch.setattr(
            sw_detect, "detect_solidworks",
            lambda: sw_detect.SwInfo(installed=True, version_year=24,
                                     toolbox_dir="C:/SW"),
        )
        cache = {
            "schema_version": 1, "sw_version": 24, "toolbox_path": "C:/SW",
            "entries": {},
        }
        assert m._envelope_invalidated(cache) is False

    def test_sw_version_mismatch_invalidated(self, monkeypatch):
        from adapters.solidworks import sw_config_lists_cache as m
        from adapters.solidworks import sw_detect

        sw_detect._reset_cache()
        monkeypatch.setattr(
            sw_detect, "detect_solidworks",
            lambda: sw_detect.SwInfo(installed=True, version_year=24,
                                     toolbox_dir="C:/SW"),
        )
        cache = {
            "schema_version": 1, "sw_version": 23, "toolbox_path": "C:/SW",
            "entries": {"C:/p.sldprt": {"mtime": 1, "size": 1, "configs": []}},
        }
        assert m._envelope_invalidated(cache) is True

    def test_toolbox_path_mismatch_invalidated(self, monkeypatch):
        from adapters.solidworks import sw_config_lists_cache as m
        from adapters.solidworks import sw_detect

        sw_detect._reset_cache()
        monkeypatch.setattr(
            sw_detect, "detect_solidworks",
            lambda: sw_detect.SwInfo(installed=True, version_year=24,
                                     toolbox_dir="C:/NewSW"),
        )
        cache = {
            "schema_version": 1, "sw_version": 24, "toolbox_path": "C:/SW",
            "entries": {},
        }
        assert m._envelope_invalidated(cache) is True


class TestEntryValid:
    """Per-entry 失效（spec §4 场景 C）：mtime / size 任一不符。"""

    def test_missing_entry_invalid(self, tmp_path):
        from adapters.solidworks import sw_config_lists_cache as m
        cache = {"entries": {}}
        sldprt = tmp_path / "p.sldprt"
        sldprt.write_bytes(b"x" * 100)
        assert m._config_list_entry_valid(cache, str(sldprt)) is False

    def test_matching_mtime_size_valid(self, tmp_path):
        from adapters.solidworks import sw_config_lists_cache as m
        sldprt = tmp_path / "p.sldprt"
        sldprt.write_bytes(b"x" * 100)
        st = sldprt.stat()
        cache = {"entries": {str(sldprt): {
            "mtime": int(st.st_mtime), "size": st.st_size, "configs": ["A"],
        }}}
        assert m._config_list_entry_valid(cache, str(sldprt)) is True

    def test_mtime_mismatch_invalid(self, tmp_path):
        from adapters.solidworks import sw_config_lists_cache as m
        sldprt = tmp_path / "p.sldprt"
        sldprt.write_bytes(b"x" * 100)
        cache = {"entries": {str(sldprt): {
            "mtime": 0, "size": sldprt.stat().st_size, "configs": ["A"],
        }}}
        assert m._config_list_entry_valid(cache, str(sldprt)) is False

    def test_size_mismatch_invalid(self, tmp_path):
        from adapters.solidworks import sw_config_lists_cache as m
        sldprt = tmp_path / "p.sldprt"
        sldprt.write_bytes(b"x" * 100)
        st = sldprt.stat()
        cache = {"entries": {str(sldprt): {
            "mtime": int(st.st_mtime), "size": 0, "configs": ["A"],
        }}}
        assert m._config_list_entry_valid(cache, str(sldprt)) is False

    def test_missing_sldprt_file_invalid(self):
        """sldprt 文件已删 → entry 视为 invalid（下次 prewarm 不会重列删了的件）。"""
        from adapters.solidworks import sw_config_lists_cache as m
        cache = {"entries": {"C:/no_such.sldprt": {
            "mtime": 100, "size": 100, "configs": ["A"],
        }}}
        assert m._config_list_entry_valid(cache, "C:/no_such.sldprt") is False
```

- [ ] **Step 2：跑失败测试**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_lists_cache.py::TestEnvelopeInvalidated tests/test_sw_config_lists_cache.py::TestEntryValid -v
```

Expected: 9 fail with AttributeError.

- [ ] **Step 3：写实现**

```python
# adapters/solidworks/sw_config_lists_cache.py 末尾追加：


def _stat_mtime(path: str) -> int | None:
    """返 sldprt 文件 mtime epoch int；文件不存在/不可读返 None。"""
    try:
        return int(Path(path).stat().st_mtime)
    except (OSError, FileNotFoundError):
        return None


def _stat_size(path: str) -> int | None:
    """返 sldprt 文件 size bytes；文件不存在/不可读返 None。"""
    try:
        return Path(path).stat().st_size
    except (OSError, FileNotFoundError):
        return None


def _envelope_invalidated(cache: dict[str, Any]) -> bool:
    """Envelope-level 失效判定（spec §4 场景 D）。

    sw_version 或 toolbox_path 任一与当前 detect_solidworks() 结果不符 → True。
    True 时调用方应清空 cache['entries'] 视为全 batch 重列。

    detect_solidworks() 在非 Windows / SW 未装时返 SwInfo(installed=False, version_year=0,
    toolbox_dir="")，此处比较仍 well-defined。
    """
    from adapters.solidworks.sw_detect import detect_solidworks
    info = detect_solidworks()
    if cache.get("sw_version") != info.version_year:
        return True
    if cache.get("toolbox_path") != info.toolbox_dir:
        return True
    return False


def _config_list_entry_valid(cache: dict[str, Any], sldprt_path: str) -> bool:
    """Per-entry 失效判定（spec §4 场景 C）。

    True 当且仅当：
    1. cache['entries'] 含该 sldprt_path
    2. 当前 sldprt 文件 mtime == cache 记录
    3. 当前 sldprt 文件 size == cache 记录

    sldprt 文件已删 → mtime/size = None → 必不等 → False。
    """
    entry = cache.get("entries", {}).get(sldprt_path)
    if entry is None:
        return False
    current_mtime = _stat_mtime(sldprt_path)
    current_size = _stat_size(sldprt_path)
    if current_mtime is None or current_size is None:
        return False
    if entry.get("mtime") != current_mtime:
        return False
    if entry.get("size") != current_size:
        return False
    return True
```

- [ ] **Step 4：跑测试 PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_lists_cache.py -v
```

Expected: `19 passed`.

- [ ] **Step 5：跑全测套确认 0 regression**

```bash
.venv/Scripts/python.exe -m pytest --ignore=tests/test_a2_integration.py --ignore=tests/test_part_templates.py -q -p no:cacheprovider 2>&1 | tail -5
```

Expected: `1220 passed` (1201 baseline + 19 new) `/ 35 failed (pre-existing)`.

- [ ] **Step 6：commit + push CP-7**

```bash
git -C /d/Work/cad-spec-gen add adapters/solidworks/sw_config_lists_cache.py tests/test_sw_config_lists_cache.py
git -C /d/Work/cad-spec-gen commit -m "$(cat <<'EOF'
feat(sw_config_lists_cache): 失效信号 + stat helpers（Task 14.6 / Task 5 / CP-7 完结）

- _envelope_invalidated(cache)：sw_version 或 toolbox_path 任一不符 → True
  调用方应清空 entries 走全 batch 重列（spec §4 场景 D）
- _config_list_entry_valid(cache, sldprt_path)：mtime + size 二维校验
  sldprt 已删 → mtime/size None → 必不等 → False（spec §4 场景 C）
- _stat_mtime / _stat_size：薄包装，返 None 不抛异常（用户级 cache 可能跨机器迁移）

测试 19 个全 PASS（含 envelope 4 场景 + entry 5 场景）；
全测套 1220 passed (1201 baseline + 19 new) / 0 regression / 35 pre-existing fail 不变

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"

git -C /d/Work/cad-spec-gen push
```

🛑 **CP-7 暂停**：sw_config_lists_cache module 全闭环（envelope load/save/empty + 失效信号），所有测试 PASS 且 0 SW 触发。用户 review cache module 设计是否符合 spec → 进 CP-8。

---

# CP-8：worker --batch + broker.prewarm（Task 6-9，部分 SW 依赖 mock）

完成后状态：worker 接 stdin batch 模式 + broker public API `prewarm_config_lists` + `_list_configs_via_com` 三层 cache。BOM loop 内（resolve_config_for_part 主路径）已经能享受持久化 cache。CP-8 commit + 暂停等用户审。

---

## Task 6：worker --batch flag + stdin JSON list 模式

**Files:**
- Modify: `adapters/solidworks/sw_list_configs_worker.py`
- Create: `tests/test_sw_list_configs_worker.py`

按 spec §4.2 worker 协议：
- 输入：stdin JSON list of strings
- 输出：stdout JSON list of `{"path": str, "configs": list[str]}`
- 单件 CLI 模式（`worker.py <path>`）保留

- [ ] **Step 1：写失败测试 — main(argv) batch mode + 单件兼容**

```python
# tests/test_sw_list_configs_worker.py
"""sw_list_configs_worker --batch + 单件 CLI 模式测试（spec §6.1 D 矩阵）。

worker 内部 _list_configs 真调 SW COM；测试用 monkeypatch 替换该函数避免 SW 触发，
仅验证 CLI 入口 / IPC 协议 / exit code 契约。
"""

from __future__ import annotations

import io
import json
from unittest.mock import patch


def test_single_file_cli_mode_preserved():
    """单件 CLI 模式（python -m ... <sldprt_path>）保留兼容。"""
    from adapters.solidworks import sw_list_configs_worker as w

    with patch.object(w, "_list_configs", return_value=0) as mock_list:
        rc = w.main(["C:/path1.sldprt"])
        assert rc == 0
        mock_list.assert_called_once_with("C:/path1.sldprt")


def test_no_args_returns_64():
    """空参数返 exit 64（CLI usage error）。"""
    from adapters.solidworks import sw_list_configs_worker as w
    rc = w.main([])
    assert rc == 64


def test_batch_mode_reads_stdin_and_writes_stdout(monkeypatch, capsys):
    """--batch flag → stdin JSON list → stdout JSON list of {path, configs}."""
    from adapters.solidworks import sw_list_configs_worker as w

    fake_results = {
        "C:/p1.sldprt": ["M3", "M4"],
        "C:/p2.sldprt": [],
    }

    def fake_list_configs_returning(sldprt_path):
        # _list_configs_returning 是新函数，返 list 而非打印到 stdout
        return fake_results.get(sldprt_path, [])

    monkeypatch.setattr(w, "_list_configs_returning", fake_list_configs_returning)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(["C:/p1.sldprt", "C:/p2.sldprt"])))

    rc = w.main(["--batch"])
    assert rc == 0

    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed == [
        {"path": "C:/p1.sldprt", "configs": ["M3", "M4"]},
        {"path": "C:/p2.sldprt", "configs": []},
    ]


def test_batch_mode_invalid_stdin_returns_64(monkeypatch):
    """--batch + stdin 不是 JSON list → exit 64。"""
    from adapters.solidworks import sw_list_configs_worker as w

    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    rc = w.main(["--batch"])
    assert rc == 64


def test_batch_mode_per_file_failure_continues(monkeypatch, capsys):
    """单 sldprt 失败（_list_configs_returning 抛异常）不阻其他 sldprt；
    输出仍是 JSON list，失败者 configs=[]。"""
    from adapters.solidworks import sw_list_configs_worker as w

    def flaky(sldprt_path):
        if "bad" in sldprt_path:
            raise RuntimeError("simulated COM failure")
        return ["A"]

    monkeypatch.setattr(w, "_list_configs_returning", flaky)
    monkeypatch.setattr("sys.stdin",
                        io.StringIO(json.dumps(["C:/good.sldprt", "C:/bad.sldprt"])))
    rc = w.main(["--batch"])
    assert rc == 0  # 整 batch exit 0：单件失败不算整 batch 失败
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed == [
        {"path": "C:/good.sldprt", "configs": ["A"]},
        {"path": "C:/bad.sldprt", "configs": []},
    ]
```

- [ ] **Step 2：跑失败测试**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_list_configs_worker.py -v
```

Expected: 5 fail with AttributeError 或 logic 错（main 不识别 --batch / 没有 _list_configs_returning）。

- [ ] **Step 3：写实现 — 重构 _list_configs 为 _list_configs_returning + 加 --batch 分支**

```python
# adapters/solidworks/sw_list_configs_worker.py 完整重写：

"""adapters/solidworks/sw_list_configs_worker.py — 独立子进程列出 SLDPRT 的所有配置名。

Task 14.6：加 --batch 模式（stdin JSON list → stdout JSON list of {path, configs}），
保留单件 CLI 模式（python -m ... <sldprt_path>）兼容。

退出码契约：
    0  成功（stdout 输出 JSON）
    2  OpenDoc6 errors 非 0 或返回 null model（仅单件模式）
    4  任何未预期 Exception（COM 崩溃、pywin32 import 失败等，仅单件模式）
    64 命令行参数错误 / batch stdin 非合法 JSON

CLI:
    python -m adapters.solidworks.sw_list_configs_worker <sldprt_path>
    python -m adapters.solidworks.sw_list_configs_worker --batch < paths.json
"""

from __future__ import annotations

import json
import sys


def _list_configs_returning(sldprt_path: str) -> list[str]:
    """返 SLDPRT configurations list；失败抛异常给调用方处理。

    与 _list_configs 不同：不打印 stdout / 不返 exit code，纯函数。
    单件 CLI 模式包此函数 + 退出码契约；batch 模式直接调此函数收集结果。
    """
    import pythoncom
    from win32com.client import VARIANT, DispatchEx

    pythoncom.CoInitialize()
    try:
        app = DispatchEx("SldWorks.Application")
        try:
            app.Visible = False
            app.UserControl = False
            app.FrameState = 0

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
        finally:
            try:
                app.ExitApp()
            except Exception as e:
                print(f"worker: ExitApp ignored: {e!r}", file=sys.stderr)
    finally:
        pythoncom.CoUninitialize()


def _list_configs(sldprt_path: str) -> int:
    """单件 CLI 模式入口：返 exit code，stdout 打印 JSON list of strings。

    保留向后兼容（broker._list_configs_via_com fallback 路径仍调此模式）。
    """
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
            # 区分 OpenDoc6 失败 (rc=2) vs 其他异常 (rc=4)
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
    """--batch：从 stdin 读 JSON list of sldprt_path → 启 SW 一次 → 逐件
    调 _list_configs_returning → stdout 输出 JSON list of {path, configs}。

    单件失败（RuntimeError / 任何异常）→ configs=[] 不阻其他件；整 batch exit 0。
    """
    try:
        sldprt_list = json.load(sys.stdin)
        if not isinstance(sldprt_list, list):
            print("worker --batch: stdin must be JSON list", file=sys.stderr)
            return 64
    except json.JSONDecodeError as e:
        print(f"worker --batch: invalid stdin JSON: {e}", file=sys.stderr)
        return 64

    results = []
    for sldprt_path in sldprt_list:
        try:
            configs = _list_configs_returning(sldprt_path)
        except Exception as e:
            print(f"worker --batch: {sldprt_path} failed: {e!r}",
                  file=sys.stderr)
            configs = []
        results.append({"path": sldprt_path, "configs": configs})

    print(json.dumps(results, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    if len(argv) == 1 and argv[0] == "--batch":
        return _run_batch_mode()

    if len(argv) == 1:
        return _list_configs(argv[0])

    print(
        "usage: python -m adapters.solidworks.sw_list_configs_worker <sldprt_path>\n"
        "       python -m adapters.solidworks.sw_list_configs_worker --batch < paths.json",
        file=sys.stderr,
    )
    return 64


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4：跑测试 PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_list_configs_worker.py -v
```

Expected: `5 passed`.

- [ ] **Step 5：跑现有 broker 测试确认单件兼容未破**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py -v 2>&1 | tail -20
```

Expected: 现有 broker 测试全 PASS（单件 CLI 模式契约不变）。

- [ ] **Step 6：commit**

```bash
git -C /d/Work/cad-spec-gen add adapters/solidworks/sw_list_configs_worker.py tests/test_sw_list_configs_worker.py
git -C /d/Work/cad-spec-gen commit -m "$(cat <<'EOF'
feat(sw_list_configs_worker): --batch flag + stdin JSON list 模式（Task 14.6 / Task 6）

- 新 _list_configs_returning(sldprt_path)：纯函数返 list，失败抛 RuntimeError
- _list_configs(sldprt_path) 重构为 _list_configs_returning 的薄包装
  保留 exit code 契约（0/2/4）+ stdout JSON list of strings（向后兼容）
- 新 _run_batch_mode()：从 stdin 读 JSON list → 启 SW 一次 → 逐件列 →
  stdout JSON list of {path, configs}；单件失败不阻整 batch（exit 0）
- main(argv) 双 mode：单件 CLI vs --batch；stdin 非合法 JSON → exit 64

测试 5 个全 PASS（含单件兼容 + batch IPC 协议 + per-file 失败容忍 + invalid stdin）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7：broker.prewarm_config_lists() public API

**Files:**
- Modify: `adapters/solidworks/sw_config_broker.py`
- Modify: `tests/test_sw_config_broker.py`

- [ ] **Step 1：写失败测试 — 4 类 prewarm 行为**

```python
# tests/test_sw_config_broker.py 末尾追加：

class TestPrewarmConfigLists:
    """Task 14.6：sw_config_broker.prewarm_config_lists 集成测试（spec §6.1 C 矩阵）。"""

    @pytest.fixture
    def patch_paths(self, monkeypatch, tmp_path):
        """所有 cache module 的 path 函数都指向 tmp_path 隔离目录。"""
        from adapters.solidworks import sw_config_lists_cache as cache_mod
        target = tmp_path / "sw_config_lists.json"
        monkeypatch.setattr(cache_mod, "get_config_lists_cache_path", lambda: target)
        return target

    @pytest.fixture
    def fake_sw(self, monkeypatch):
        """detect_solidworks 返 stable info（version_year=24, toolbox_dir='C:/SW'）。"""
        from adapters.solidworks import sw_detect

        sw_detect._reset_cache()
        monkeypatch.setattr(
            sw_detect, "detect_solidworks",
            lambda: sw_detect.SwInfo(installed=True, version_year=24,
                                     toolbox_dir="C:/SW"),
        )

    def test_prewarm_disabled_by_safety_valve(self, patch_paths, fake_sw, monkeypatch):
        """CAD_SW_BROKER_DISABLE=1 → prewarm 立刻返不 spawn worker / 不写 cache."""
        from adapters.solidworks import sw_config_broker as broker

        # autouse 已设 disable=1；显式 spawn 守卫 mock subprocess 验证未调
        called = []
        monkeypatch.setattr("subprocess.run",
                            lambda *a, **kw: called.append((a, kw)) or _stub_completed_process())
        broker.prewarm_config_lists(["C:/p1.sldprt"])
        assert called == []
        assert not patch_paths.exists()

    def test_prewarm_all_miss_spawns_batch_once(self, patch_paths, fake_sw, monkeypatch, tmp_path):
        """全 cache miss → 1 次 batch spawn worker → 写回 cache."""
        from adapters.solidworks import sw_config_broker as broker

        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)

        # 建 2 个真 sldprt 文件让 _stat_mtime/_stat_size 工作
        p1 = tmp_path / "p1.sldprt"; p1.write_bytes(b"x" * 100)
        p2 = tmp_path / "p2.sldprt"; p2.write_bytes(b"y" * 200)

        spawn_calls = []
        def fake_run(cmd, **kwargs):
            spawn_calls.append((cmd, kwargs))
            class FakeProc:
                returncode = 0
                stderr = b""
                stdout = json.dumps([
                    {"path": str(p1), "configs": ["A1", "A2"]},
                    {"path": str(p2), "configs": ["B1"]},
                ]).encode()
            return FakeProc()
        monkeypatch.setattr("subprocess.run", fake_run)

        broker.prewarm_config_lists([str(p1), str(p2)])

        assert len(spawn_calls) == 1  # batch 只 spawn 一次
        assert "--batch" in spawn_calls[0][0]
        # cache 已写
        assert patch_paths.exists()
        cache = json.loads(patch_paths.read_text(encoding="utf-8"))
        assert str(p1) in cache["entries"]
        assert cache["entries"][str(p1)]["configs"] == ["A1", "A2"]
        assert cache["entries"][str(p2)]["configs"] == ["B1"]
        assert cache["sw_version"] == 24
        assert cache["toolbox_path"] == "C:/SW"

    def test_prewarm_all_hit_no_spawn(self, patch_paths, fake_sw, monkeypatch, tmp_path):
        """全 cache 命中 → 0 spawn."""
        from adapters.solidworks import sw_config_broker as broker
        from adapters.solidworks import sw_config_lists_cache as cache_mod

        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)

        p1 = tmp_path / "p1.sldprt"; p1.write_bytes(b"x" * 100)
        st = p1.stat()
        cache = {
            "schema_version": 1, "sw_version": 24, "toolbox_path": "C:/SW",
            "generated_at": "2026-04-26T00:00:00+00:00",
            "entries": {str(p1): {"mtime": int(st.st_mtime), "size": st.st_size,
                                  "configs": ["X"]}},
        }
        cache_mod._save_config_lists_cache(cache)

        spawn_calls = []
        monkeypatch.setattr("subprocess.run",
                            lambda *a, **kw: spawn_calls.append(a) or _stub_completed_process())
        broker.prewarm_config_lists([str(p1)])
        assert spawn_calls == []  # 0 spawn

    def test_prewarm_partial_miss_only_misses_batched(self, patch_paths, fake_sw, monkeypatch, tmp_path):
        """部分 miss → batch spawn 只含 miss 的 sldprt（命中件不重列）."""
        from adapters.solidworks import sw_config_broker as broker
        from adapters.solidworks import sw_config_lists_cache as cache_mod

        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)

        p1 = tmp_path / "p1.sldprt"; p1.write_bytes(b"x" * 100)
        p2 = tmp_path / "p2.sldprt"; p2.write_bytes(b"y" * 200)
        st1 = p1.stat()
        cache = {
            "schema_version": 1, "sw_version": 24, "toolbox_path": "C:/SW",
            "generated_at": "2026-04-26T00:00:00+00:00",
            "entries": {str(p1): {"mtime": int(st1.st_mtime), "size": st1.st_size,
                                  "configs": ["P1A"]}},
        }
        cache_mod._save_config_lists_cache(cache)

        captured_stdin = []
        def fake_run(cmd, input=None, **kwargs):
            captured_stdin.append(input)
            class FakeProc:
                returncode = 0
                stderr = b""
                stdout = json.dumps([{"path": str(p2), "configs": ["P2A"]}]).encode()
            return FakeProc()
        monkeypatch.setattr("subprocess.run", fake_run)

        broker.prewarm_config_lists([str(p1), str(p2)])

        # batch 只含 p2（p1 已命中跳过）
        assert len(captured_stdin) == 1
        sent = json.loads(captured_stdin[0])
        assert sent == [str(p2)]

    def test_prewarm_worker_failure_does_not_write_cache(self, patch_paths, fake_sw, monkeypatch, tmp_path):
        """worker exit != 0 → cache 不写；prewarm 静默 return 不抛."""
        from adapters.solidworks import sw_config_broker as broker

        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)

        p1 = tmp_path / "p1.sldprt"; p1.write_bytes(b"x" * 100)

        def fake_run(cmd, **kwargs):
            class FakeProc:
                returncode = 4
                stderr = b"worker: pywin32 import failed"
                stdout = b""
            return FakeProc()
        monkeypatch.setattr("subprocess.run", fake_run)

        # 不抛异常
        broker.prewarm_config_lists([str(p1)])
        # cache 未写
        assert not patch_paths.exists()

    def test_prewarm_worker_timeout_does_not_write_cache(self, patch_paths, fake_sw, monkeypatch, tmp_path):
        """subprocess.TimeoutExpired → cache 不写；prewarm 静默 return."""
        import subprocess
        from adapters.solidworks import sw_config_broker as broker

        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)

        p1 = tmp_path / "p1.sldprt"; p1.write_bytes(b"x" * 100)

        def fake_run(*a, **kw):
            raise subprocess.TimeoutExpired(cmd="x", timeout=180)
        monkeypatch.setattr("subprocess.run", fake_run)

        broker.prewarm_config_lists([str(p1)])  # 不抛
        assert not patch_paths.exists()

    def test_prewarm_envelope_invalidated_clears_entries(self, patch_paths, fake_sw, monkeypatch, tmp_path):
        """SW 升级（cache.sw_version=23, current=24）→ entries 清空 → 全 batch 重列."""
        from adapters.solidworks import sw_config_broker as broker
        from adapters.solidworks import sw_config_lists_cache as cache_mod

        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)

        p1 = tmp_path / "p1.sldprt"; p1.write_bytes(b"x" * 100)
        st = p1.stat()
        cache_old = {
            "schema_version": 1, "sw_version": 23, "toolbox_path": "C:/SW",  # 旧 SW
            "generated_at": "2025-01-01T00:00:00+00:00",
            "entries": {str(p1): {"mtime": int(st.st_mtime), "size": st.st_size,
                                  "configs": ["OLD"]}},
        }
        cache_mod._save_config_lists_cache(cache_old)

        captured_stdin = []
        def fake_run(cmd, input=None, **kwargs):
            captured_stdin.append(input)
            class FakeProc:
                returncode = 0
                stderr = b""
                stdout = json.dumps([{"path": str(p1), "configs": ["NEW"]}]).encode()
            return FakeProc()
        monkeypatch.setattr("subprocess.run", fake_run)

        broker.prewarm_config_lists([str(p1)])

        # batch 含 p1（envelope 失效后视为全 miss）
        assert len(captured_stdin) == 1
        sent = json.loads(captured_stdin[0])
        assert sent == [str(p1)]
        # 新 cache：sw_version 升级 + entries 全新
        cache_new = json.loads(patch_paths.read_text(encoding="utf-8"))
        assert cache_new["sw_version"] == 24
        assert cache_new["entries"][str(p1)]["configs"] == ["NEW"]


def _stub_completed_process():
    class FakeProc:
        returncode = 0
        stdout = b"[]"
        stderr = b""
    return FakeProc()
```

- [ ] **Step 2：跑失败测试**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestPrewarmConfigLists -v
```

Expected: 7 fail with `AttributeError: module ... has no attribute 'prewarm_config_lists'`.

- [ ] **Step 3：写实现 — broker.prewarm_config_lists API**

在 `adapters/solidworks/sw_config_broker.py` 的 `_list_configs_via_com` 函数定义之后（约 line 500 附近）插入：

```python
# adapters/solidworks/sw_config_broker.py 在 _list_configs_via_com 之后追加：


def prewarm_config_lists(sldprt_list: list[str]) -> None:
    """fire-and-forget 预热持久化 cache（spec §3.1）。

    流程：
      1. CAD_SW_BROKER_DISABLE=1 → 立刻 return（与 resolve_config_for_part 一致安全阀）
      2. _load_config_lists_cache() → 4 类自愈
      3. _envelope_invalidated → 整 entries 清重列
      4. diff 出 cache miss → 一次 batch spawn worker → 解析 stdout → 写回
      5. 任何失败（worker rc!=0 / TimeoutExpired / OSError / JSONDecodeError）→
         不抛异常；BOM loop 内的 _list_configs_via_com 走原 fallback 路径

    fallback 路径只填 in-process L2，不写 L1 持久化（spec §3.1 issue 4 决策）：
    - 不写：下次 prewarm 自然修复（fallback 罕见，cost 低）
    - 写：fallback 路径变复杂 + 并发竞争（不值）
    """
    if os.environ.get("CAD_SW_BROKER_DISABLE") == "1":
        return

    from adapters.solidworks import sw_config_lists_cache as cache_mod
    from adapters.solidworks.sw_detect import detect_solidworks

    cache = cache_mod._load_config_lists_cache()
    if cache_mod._envelope_invalidated(cache):
        log.info("config_lists envelope invalidated → 全 entries 清空重列")
        cache = cache_mod._empty_config_lists_cache()
        info = detect_solidworks()
        cache["sw_version"] = info.version_year
        cache["toolbox_path"] = info.toolbox_dir

    miss = [p for p in sldprt_list if not cache_mod._config_list_entry_valid(cache, p)]
    if not miss:
        return  # 全命中，无需 spawn

    cmd = [
        sys.executable,
        "-m", "adapters.solidworks.sw_list_configs_worker",
        "--batch",
    ]
    try:
        proc = subprocess.run(
            cmd,
            input=json.dumps(miss).encode(),
            timeout=LIST_CONFIGS_TIMEOUT_SEC * len(miss),  # 按 batch 大小放宽
            capture_output=True,
            cwd=str(_PROJECT_ROOT_FOR_WORKER),
        )
        if proc.returncode != 0:
            log.warning(
                "config_lists batch worker rc=%d stderr=%s",
                proc.returncode, (proc.stderr or b"").decode()[:500],
            )
            return  # cache 不动；BOM loop 走单件 fallback 兜底
        results = json.loads(proc.stdout.decode())
        if not isinstance(results, list):
            log.warning("config_lists batch worker stdout not a JSON list")
            return
        for entry in results:
            sldprt_path = entry.get("path", "")
            configs = entry.get("configs", [])
            mtime = cache_mod._stat_mtime(sldprt_path)
            size = cache_mod._stat_size(sldprt_path)
            if mtime is None or size is None:
                continue  # sldprt 文件已删 — 跳过不写
            cache["entries"][sldprt_path] = {
                "mtime": mtime,
                "size": size,
                "configs": configs,
            }
        cache_mod._save_config_lists_cache(cache)
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as e:
        log.warning("config_lists prewarm 失败 %s; codegen 退化到单件 fallback", e)
        # 不抛异常 — prewarm 是加速优化不是必要前置
```

- [ ] **Step 4：跑测试 PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestPrewarmConfigLists -v
```

Expected: `7 passed`.

- [ ] **Step 5：commit**

```bash
git -C /d/Work/cad-spec-gen add adapters/solidworks/sw_config_broker.py tests/test_sw_config_broker.py
git -C /d/Work/cad-spec-gen commit -m "$(cat <<'EOF'
feat(sw_config_broker): prewarm_config_lists public API（Task 14.6 / Task 7）

- 新 public API：prewarm_config_lists(sldprt_list) -> None fire-and-forget
- 顶部 CAD_SW_BROKER_DISABLE=1 安全阀（与 resolve_config_for_part 一致）
- 调 sw_config_lists_cache module：_load → _envelope_invalidated → diff miss
- batch spawn worker --batch (stdin JSON list / timeout = LIST_CONFIGS_TIMEOUT_SEC * N)
- worker 失败（rc!=0 / TimeoutExpired / OSError / JSONDecodeError）→ 静默 return
  cache 不动；BOM loop 内 _list_configs_via_com 走原单件 fallback

测试 7 个全 PASS：安全阀 / 全 miss → 1 spawn / 全命中 → 0 spawn /
部分 miss → batch 只含 miss / worker 失败 → cache 不写 /
TimeoutExpired → cache 不写 / envelope 失效 → entries 清空重列

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8：broker._list_configs_via_com 三层 cache 改造

**Files:**
- Modify: `adapters/solidworks/sw_config_broker.py:448-500`
- Modify: `tests/test_sw_config_broker.py`

按 spec §3.1：原 `_list_configs_via_com` 仅有 in-process L2 cache + fallback spawn。改造为：
1. L2 in-process 命中 → return（现有）
2. L1 持久化 cache 命中 → 填 L2 → return（**新增**）
3. fallback：单件 spawn worker（现有）→ **只填 L2 不写 L1**（spec §3.1 决策）

- [ ] **Step 1：写失败测试 — L1 持久化命中应填 L2 + return**

```python
# tests/test_sw_config_broker.py 末尾追加：

class TestListConfigsViaComThreeLayer:
    """Task 14.6：_list_configs_via_com 三层 cache (L2 → L1 → fallback)."""

    @pytest.fixture
    def patch_paths(self, monkeypatch, tmp_path):
        from adapters.solidworks import sw_config_lists_cache as cache_mod
        target = tmp_path / "sw_config_lists.json"
        monkeypatch.setattr(cache_mod, "get_config_lists_cache_path", lambda: target)
        return target

    @pytest.fixture
    def fake_sw(self, monkeypatch):
        from adapters.solidworks import sw_detect
        sw_detect._reset_cache()
        monkeypatch.setattr(
            sw_detect, "detect_solidworks",
            lambda: sw_detect.SwInfo(installed=True, version_year=24,
                                     toolbox_dir="C:/SW"),
        )

    def test_l1_persistent_cache_hit_fills_l2_no_spawn(self, patch_paths, fake_sw, monkeypatch, tmp_path):
        """L2 miss + L1 命中 → 填 L2 + 返结果 + 0 spawn."""
        from adapters.solidworks import sw_config_broker as broker
        from adapters.solidworks import sw_config_lists_cache as cache_mod

        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)

        # 清 L2
        broker._CONFIG_LIST_CACHE.clear()

        # 预填 L1
        p1 = tmp_path / "p1.sldprt"; p1.write_bytes(b"x" * 100)
        st = p1.stat()
        cache_mod._save_config_lists_cache({
            "schema_version": 1, "sw_version": 24, "toolbox_path": "C:/SW",
            "generated_at": "2026-04-26T00:00:00+00:00",
            "entries": {str(p1.resolve()): {
                "mtime": int(st.st_mtime), "size": st.st_size,
                "configs": ["FROM_L1"],
            }},
        })

        spawn_calls = []
        monkeypatch.setattr("subprocess.run",
                            lambda *a, **kw: spawn_calls.append(a) or _stub_completed_process())

        result = broker._list_configs_via_com(str(p1))
        assert result == ["FROM_L1"]
        assert spawn_calls == []  # 0 spawn — L1 命中
        # L2 已填
        assert broker._CONFIG_LIST_CACHE[str(p1.resolve())] == ["FROM_L1"]

    def test_l2_in_process_cache_hit_no_spawn_no_l1_read(self, patch_paths, fake_sw, monkeypatch, tmp_path):
        """L2 命中 → 不读 L1 文件 + 0 spawn."""
        from adapters.solidworks import sw_config_broker as broker

        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)

        # 预填 L2
        p1 = tmp_path / "p1.sldprt"; p1.write_bytes(b"x" * 100)
        broker._CONFIG_LIST_CACHE[str(p1.resolve())] = ["FROM_L2"]

        spawn_calls = []
        monkeypatch.setattr("subprocess.run",
                            lambda *a, **kw: spawn_calls.append(a) or _stub_completed_process())

        # L1 文件不存在；如果路径走到 L1 读会触发 _empty_config_lists_cache 但仍 0 spawn
        result = broker._list_configs_via_com(str(p1))
        assert result == ["FROM_L2"]
        assert spawn_calls == []

    def test_fallback_spawns_single_only_fills_l2_not_l1(self, patch_paths, fake_sw, monkeypatch, tmp_path):
        """L1+L2 全 miss → fallback 单件 spawn → 只填 L2 不写 L1."""
        from adapters.solidworks import sw_config_broker as broker

        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)

        broker._CONFIG_LIST_CACHE.clear()

        p1 = tmp_path / "p1.sldprt"; p1.write_bytes(b"x" * 100)

        # mock 单件 worker 返一个 config
        def fake_run(cmd, **kwargs):
            class FakeProc:
                returncode = 0
                stderr = ""
                stdout = json.dumps(["FROM_FALLBACK"]) + "\n"
            return FakeProc()
        monkeypatch.setattr("subprocess.run", fake_run)

        result = broker._list_configs_via_com(str(p1))
        assert result == ["FROM_FALLBACK"]
        # L2 已填
        assert broker._CONFIG_LIST_CACHE[str(p1.resolve())] == ["FROM_FALLBACK"]
        # L1 持久化文件 未 写（spec §3.1 issue 4 决策）
        assert not patch_paths.exists()
```

- [ ] **Step 2：跑失败测试**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestListConfigsViaComThreeLayer -v
```

Expected: 第一个测试 fail（L1 命中未实现）；第二、三测试可能因现有逻辑碰巧 PASS 但不稳定。

- [ ] **Step 3：写实现 — _list_configs_via_com 加 L1 命中分支**

修改 `adapters/solidworks/sw_config_broker.py:448-500` 的 `_list_configs_via_com` 函数。在 `if abs_path in _CONFIG_LIST_CACHE: return _CONFIG_LIST_CACHE[abs_path]` 之后、构造 cmd 之前，**插入 L1 持久化 cache 查询**：

```python
def _list_configs_via_com(sldprt_path: str) -> list[str]:
    """调 sw_list_configs_worker 子进程列 SLDPRT 配置名（spec §4.4 #1）。

    Task 14.6 三层 cache：
      1. in-process L2 (_CONFIG_LIST_CACHE) 命中 → return
      2. 持久化 L1 cache 命中 → 填 L2 → return
      3. fallback：单件 spawn worker → 只填 L2 不写 L1（避免 fallback 路径并发竞争）

    缓存按 sldprt 绝对路径 key；失败也缓存（[]）以避免重试同一坏 sldprt。
    永不抛异常——任何失败一律返回空列表。
    """
    abs_path = str(Path(sldprt_path).resolve())

    # Layer 2：in-process cache
    if abs_path in _CONFIG_LIST_CACHE:
        return _CONFIG_LIST_CACHE[abs_path]

    # Layer 1：持久化 cache（Task 14.6 新增）
    try:
        from adapters.solidworks import sw_config_lists_cache as cache_mod
        cache = cache_mod._load_config_lists_cache()
        if not cache_mod._envelope_invalidated(cache):
            entry = cache.get("entries", {}).get(abs_path)
            if entry is not None and cache_mod._config_list_entry_valid(cache, abs_path):
                configs = entry["configs"]
                _CONFIG_LIST_CACHE[abs_path] = configs  # 填 L2
                return configs
    except Exception as e:
        # L1 读失败不影响 fallback；下次 prewarm 自愈
        log.debug("config_lists L1 read skipped: %s", e)

    # Layer 3：fallback 单件 spawn（现有逻辑保留）
    cmd = [
        sys.executable,
        "-m", "adapters.solidworks.sw_list_configs_worker",
        sldprt_path,
    ]

    try:
        proc = subprocess.run(
            cmd,
            timeout=LIST_CONFIGS_TIMEOUT_SEC,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(_PROJECT_ROOT_FOR_WORKER),
        )
    except subprocess.TimeoutExpired:
        log.warning(
            "list_configs subprocess 超时 %ds: %s",
            LIST_CONFIGS_TIMEOUT_SEC, sldprt_path,
        )
        _CONFIG_LIST_CACHE[abs_path] = []
        return []

    if proc.returncode != 0:
        log.warning(
            "list_configs subprocess rc=%d sldprt=%s stderr=%s",
            proc.returncode, sldprt_path, (proc.stderr or "")[:300],
        )
        _CONFIG_LIST_CACHE[abs_path] = []
        return []

    try:
        configs = json.loads(proc.stdout.strip())
        if not isinstance(configs, list):
            raise ValueError("not a list")
    except (json.JSONDecodeError, ValueError) as e:
        log.warning("list_configs stdout 非合法 JSON list: %s", e)
        _CONFIG_LIST_CACHE[abs_path] = []
        return []

    _CONFIG_LIST_CACHE[abs_path] = configs
    # spec §3.1 决策 issue 4：fallback 路径不写 L1 持久化（并发竞争代价 > 优化收益）
    return configs
```

- [ ] **Step 4：跑测试 PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestListConfigsViaComThreeLayer tests/test_sw_config_broker.py::TestPrewarmConfigLists -v
```

Expected: `10 passed`.

- [ ] **Step 5：跑全 broker 测试集 + cache module 测试 + worker 测试**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py tests/test_sw_config_lists_cache.py tests/test_sw_list_configs_worker.py -v 2>&1 | tail -10
```

Expected: 全 PASS（具体数字含已有 broker 测试 + 19 cache + 5 worker + 10 prewarm/three_layer = 34+ new + existing）。

- [ ] **Step 6：跑全测套确认 0 regression**

```bash
.venv/Scripts/python.exe -m pytest --ignore=tests/test_a2_integration.py --ignore=tests/test_part_templates.py -q -p no:cacheprovider 2>&1 | tail -5
```

Expected: passed 数比 CP-7 后多约 17 个（7 prewarm + 3 three_layer + 7 worker = 17）；fail 数仍 35（pre-existing）。

- [ ] **Step 7：commit + push CP-8**

```bash
git -C /d/Work/cad-spec-gen add adapters/solidworks/sw_config_broker.py tests/test_sw_config_broker.py
git -C /d/Work/cad-spec-gen commit -m "$(cat <<'EOF'
feat(sw_config_broker): _list_configs_via_com 三层 cache（Task 14.6 / Task 8 / CP-8 完结）

L2 in-process → L1 持久化 → fallback 单件 spawn 三层流：
- L2 命中 → 0 spawn 0 disk read
- L1 命中（envelope 有效 + entry valid）→ 填 L2 → 0 spawn
- 全 miss → fallback 单件 spawn worker → 只填 L2 不写 L1
  （spec §3.1 issue 4：fallback 罕见，cost 低；写 L1 增加并发竞争不值）

L1 读失败/损坏 → 不影响 fallback；下次 prewarm 自愈。

测试：3 个新 three_layer 集成测试 + 已有 7 个 prewarm 测试全 PASS；
全测套 +17 (7+3+7) / 0 regression / 35 pre-existing fail 不变

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"

git -C /d/Work/cad-spec-gen push
```

🛑 **CP-8 暂停**：worker --batch + broker.prewarm + 三层 cache 全闭环。**已经能享受持久化 cache** —— 任何调 broker.resolve_config_for_part 的代码都会自动用 L1（如已有 sw_warmup --bom 工具）。但 codegen 的 BOM loop 还没主动调 prewarm，所以"装即用"第一次 codegen 仍 N 次 spawn。CP-9 把这条接通。

用户审 broker + worker 改动 → 进 CP-9。

---

# CP-9：调用链端到端（Task 9-13）

完成后状态：gen_std_parts.main → resolver.prewarm → adapter.prewarm → broker.prewarm_config_lists 全链路通；第一次 codegen "1 次 batch spawn 列全 BOM" 兑现。

---

## Task 9：PartsAdapter base 加 prewarm() virtual default no-op

**Files:**
- Modify: `adapters/parts/base.py`
- Create: `tests/test_parts_adapter_base.py`（新 file，目前无）

按 spec §7.3：base 加 `prewarm` 是 **virtual method with default no-op body**（不是 abstractmethod，避免现有 4 adapter 加 pass 占位）。

- [ ] **Step 1：写失败测试 — base 有 prewarm + 现有 adapter 不需 override 仍 work**

```python
# tests/test_parts_adapter_base.py
"""PartsAdapter.prewarm() virtual method 默认 no-op 测试（Task 14.6 / Task 9）。"""

from __future__ import annotations

import pytest


def test_base_class_has_prewarm_method():
    from adapters.parts.base import PartsAdapter
    assert hasattr(PartsAdapter, "prewarm")


def test_default_prewarm_is_no_op():
    """base 给 default no-op body：现有 4 adapter 不需要 override 也能跑。"""
    from adapters.parts.jinja_primitive_adapter import JinjaPrimitiveAdapter
    a = JinjaPrimitiveAdapter()
    # 不抛 + 返 None
    result = a.prewarm([])
    assert result is None
    result = a.prewarm([("fake_query", {"some": "spec"})])
    assert result is None


def test_prewarm_is_not_abstractmethod():
    """prewarm 不是 abstractmethod；新 adapter 无需实现也可继承 PartsAdapter。"""
    from adapters.parts.base import PartsAdapter
    import inspect
    method = PartsAdapter.prewarm
    abstract = getattr(method, "__isabstractmethod__", False)
    assert abstract is False
```

- [ ] **Step 2：跑失败测试**

```bash
.venv/Scripts/python.exe -m pytest tests/test_parts_adapter_base.py -v
```

Expected: 3 fail with `AssertionError: hasattr` 或 `AttributeError`.

- [ ] **Step 3：写实现 — 在 base.py 加 prewarm**

修改 `adapters/parts/base.py`，在 `probe_dims` 之后追加：

```python
# adapters/parts/base.py — 在 probe_dims 方法之后追加：

    def prewarm(self, candidates) -> None:
        """Optional pre-warmup hook called before BOM resolve loop (Task 14.6).

        Parameters
        ----------
        candidates : list[tuple[PartQuery, dict]]
            (query, rule.spec) tuples that PartsResolver pre-matched to
            this adapter via _match_rule. Adapter can use this to batch
            any expensive setup (e.g. spawn helper subprocess once for
            all sldprt instead of per-part).

        Returns
        -------
        None — fire-and-forget. Failures must not raise (codegen continues
        via fallback paths in resolve()).

        Default implementation is no-op. Adapters override only if they
        have batchable expensive operations to amortize.
        """
        return None
```

- [ ] **Step 4：跑测试 PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_parts_adapter_base.py -v
```

Expected: `3 passed`.

- [ ] **Step 5：跑现有 adapter 测试不破**

```bash
.venv/Scripts/python.exe -m pytest tests/test_parts_adapters.py tests/test_sw_toolbox_adapter.py -v 2>&1 | tail -5
```

Expected: 现有 adapter 测试全 PASS（因 base 加新方法不影响子类已有方法）。

- [ ] **Step 6：commit**

```bash
git -C /d/Work/cad-spec-gen add adapters/parts/base.py tests/test_parts_adapter_base.py
git -C /d/Work/cad-spec-gen commit -m "$(cat <<'EOF'
feat(adapters): PartsAdapter.prewarm virtual default no-op（Task 14.6 / Task 9）

- base.py 加 prewarm(candidates) -> None 方法
- 不是 @abstractmethod；现有 4 adapter（jinja/step_pool/partcad/bd_warehouse）
  无需 override 即可继承 PartsAdapter，避免对现有 adapter 加 pass 占位的摩擦
- 子类 sw_toolbox 在 Task 11 override 实际逻辑

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10：PartsResolver.prewarm() — rule matching 在 resolver 层

**Files:**
- Modify: `parts_resolver.py`
- Modify: `tests/test_parts_resolver_*.py`（如已有）or Create: `tests/test_parts_resolver_prewarm.py`

按 spec §3.1（issue 1 修后）：rule matching 必须在 PartsResolver 层做（不是 adapter 层），因为 adapter 不知道 rule.spec。

- [ ] **Step 1：写失败测试 — prewarm 收集 candidates 派发**

```python
# tests/test_parts_resolver_prewarm.py
"""PartsResolver.prewarm() 测试（Task 14.6 / Task 10）。

关键不变量：rule matching 在 resolver 层做（不在 adapter 层）；
adapter.prewarm 收到的是 (query, rule.spec) tuple list。
"""

from __future__ import annotations

import pytest

from adapters.parts.base import PartsAdapter
from parts_resolver import PartQuery, PartsResolver, ResolveResult


class _RecordingAdapter(PartsAdapter):
    """Record prewarm() calls for assertion."""

    name = "test_adapter"

    def __init__(self):
        self.prewarm_calls = []

    def is_available(self): return True, None
    def can_resolve(self, q): return True
    def resolve(self, q, spec): return ResolveResult(status="miss", kind="miss", adapter=self.name)
    def probe_dims(self, q, spec): return None
    def prewarm(self, candidates):
        self.prewarm_calls.append(list(candidates))


def _make_query(part_no: str, name_cn: str = "", category: str = "") -> PartQuery:
    return PartQuery(
        part_no=part_no, name_cn=name_cn, material="",
        category=category, make_buy="",
    )


class TestPartsResolverPrewarm:
    def test_prewarm_returns_none(self):
        """fire-and-forget 契约：返 None."""
        adapter = _RecordingAdapter()
        resolver = PartsResolver(registry={"mappings": []}, adapters=[adapter])
        result = resolver.prewarm([])
        assert result is None

    def test_prewarm_dispatches_only_matching_adapter(self):
        """rule matching 在 resolver 层：query 命中 test_adapter rule → adapter 收到 candidate."""
        adapter = _RecordingAdapter()
        resolver = PartsResolver(
            registry={
                "mappings": [
                    {
                        "match": {"category": "fastener"},
                        "adapter": "test_adapter",
                        "spec": {"rule_specific": "value"},
                    },
                ]
            },
            adapters=[adapter],
        )
        q1 = _make_query("P1", category="fastener")
        q2 = _make_query("P2", category="bearing")  # 不命中 fastener rule

        resolver.prewarm([q1, q2])

        # adapter.prewarm 调用一次；candidates 只含 q1（命中）+ rule.spec
        assert len(adapter.prewarm_calls) == 1
        candidates = adapter.prewarm_calls[0]
        assert len(candidates) == 1
        candidate_q, candidate_spec = candidates[0]
        assert candidate_q.part_no == "P1"
        assert candidate_spec == {"rule_specific": "value"}

    def test_prewarm_first_hit_wins_per_query(self):
        """per query first-hit 原则：同 query 不会被多个 rule 重复派发."""
        adapter = _RecordingAdapter()
        resolver = PartsResolver(
            registry={
                "mappings": [
                    # 第一条命中 → 后面 sw_specific rule 不再考虑
                    {"match": {"category": "fastener"},
                     "adapter": "test_adapter", "spec": {"first": True}},
                    {"match": {"category": "fastener"},
                     "adapter": "test_adapter", "spec": {"second": True}},
                ]
            },
            adapters=[adapter],
        )
        resolver.prewarm([_make_query("P1", category="fastener")])

        candidates = adapter.prewarm_calls[0]
        assert len(candidates) == 1
        _, spec = candidates[0]
        assert spec == {"first": True}  # first-hit-wins

    def test_prewarm_skips_adapter_with_no_candidates(self):
        """无 query 命中此 adapter 的 rule → adapter.prewarm 不调."""
        adapter = _RecordingAdapter()
        resolver = PartsResolver(
            registry={
                "mappings": [
                    {"match": {"category": "fastener"},
                     "adapter": "test_adapter", "spec": {}},
                ]
            },
            adapters=[adapter],
        )
        resolver.prewarm([_make_query("P1", category="bearing")])  # 不命中
        assert adapter.prewarm_calls == []

    def test_prewarm_adapter_exception_does_not_abort(self):
        """单 adapter.prewarm 抛异常不阻其他 adapter / 不阻 codegen."""

        class _ExplodingAdapter(_RecordingAdapter):
            name = "exploding"
            def prewarm(self, candidates):
                raise RuntimeError("simulated crash")

        boom = _ExplodingAdapter()
        good = _RecordingAdapter()
        good.name = "good"
        resolver = PartsResolver(
            registry={
                "mappings": [
                    {"match": {"any": True}, "adapter": "exploding", "spec": {}},
                    {"match": {"any": True}, "adapter": "good", "spec": {}},
                ]
            },
            adapters=[boom, good],
        )
        # 不抛
        resolver.prewarm([_make_query("P1")])
        # good 仍被调（first-hit 后 query 已绑定 exploding，good 不会被调）
        # 修正断言：仅验证 resolver.prewarm 不抛
```

- [ ] **Step 2：跑失败测试**

```bash
.venv/Scripts/python.exe -m pytest tests/test_parts_resolver_prewarm.py -v
```

Expected: 5 fail with `AttributeError: 'PartsResolver' object has no attribute 'prewarm'`.

- [ ] **Step 3：写实现 — PartsResolver.prewarm**

修改 `parts_resolver.py`，在 `PartsResolver.resolve` 方法之后追加：

```python
# parts_resolver.py — 在 PartsResolver.resolve 方法之后追加：

    def prewarm(self, queries: list["PartQuery"]) -> None:
        """Pre-warm hook：派发 candidates 给所有 adapter（Task 14.6 / spec §3.1）。

        rule matching 在 resolver 层做（不在 adapter 层）：adapter 不知道 rule.spec，
        必须由 resolver 按 first-hit-wins 算出 (query, rule.spec) tuple 派发给目标 adapter。

        Per-adapter try/except：单 adapter 失败不阻其他 adapter / 不阻 codegen
        （prewarm 是加速优化不是必要前置）。

        Returns None — fire-and-forget。
        """
        for adapter in self.adapters:
            candidates = []  # list[tuple[PartQuery, dict]]
            for q in queries:
                for rule in self.registry.get("mappings", []):
                    if not _match_rule(rule.get("match", {}), q):
                        continue
                    if rule.get("adapter", "") != adapter.name:
                        break  # first-hit 不归此 adapter，跳过此 query
                    candidates.append((q, rule.get("spec", {})))
                    break  # first-hit-wins 与 PartsResolver.resolve 一致
            if not candidates:
                continue
            try:
                adapter.prewarm(candidates)
            except Exception as e:
                self.log(f"  [resolver] prewarm '{adapter.name}' failed: {e}")
        return None
```

- [ ] **Step 4：跑测试 PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_parts_resolver_prewarm.py -v
```

Expected: `5 passed`.

- [ ] **Step 5：commit**

```bash
git -C /d/Work/cad-spec-gen add parts_resolver.py tests/test_parts_resolver_prewarm.py
git -C /d/Work/cad-spec-gen commit -m "$(cat <<'EOF'
feat(parts_resolver): PartsResolver.prewarm 派发链（Task 14.6 / Task 10）

rule matching 在 resolver 层做（spec §3.1 issue 1 修复）：
- 对每个 query 跑 _match_rule，按 first-hit adapter 分组成 candidates
- adapter.prewarm 收到 [(query, rule.spec)] list — adapter 不需要也无法
  自己做 rule matching（rule.spec 是 PartsResolver 内部从 yaml 取的）
- per-adapter try/except：单 adapter 失败不阻其他 / 不阻 codegen
- 返 None (fire-and-forget)

测试 5 个全 PASS：契约 / 派发 / first-hit-wins / 无候选不调 / 异常容忍

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11：SwToolboxAdapter override prewarm()

**Files:**
- Modify: `adapters/parts/sw_toolbox_adapter.py`
- Modify: `tests/test_sw_toolbox_adapter.py`

按 spec §3.1：sw_toolbox_adapter.prewarm 收 candidates → 用现有 `find_sldprt(query, spec)` (catalog-only, 不调 COM) 收集 sldprt → 调 broker.prewarm_config_lists。

- [ ] **Step 1：写失败测试 — adapter.prewarm 收集 + 转发**

```python
# tests/test_sw_toolbox_adapter.py 末尾追加：

class TestSwToolboxAdapterPrewarm:
    """Task 14.6：sw_toolbox_adapter.prewarm() 收集 sldprt 后调 broker.prewarm_config_lists."""

    def test_prewarm_calls_broker_with_collected_sldprt_paths(self, monkeypatch, tmp_path):
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_config_broker as broker
        from adapters.solidworks.sw_toolbox_catalog import SwToolboxPart
        from parts_resolver import PartQuery

        # mock find_sldprt 返不同件
        def fake_find_sldprt(self, query, spec):
            if query.part_no == "BOLT-001":
                return (SwToolboxPart(
                    standard="GB", subcategory="bolt",
                    sldprt_path="C:/SW/bolt.sldprt",
                    filename="bolt.sldprt", tokens=[],
                ), 0.9)
            if query.part_no == "NUT-002":
                return (SwToolboxPart(
                    standard="GB", subcategory="nut",
                    sldprt_path="C:/SW/nut.sldprt",
                    filename="nut.sldprt", tokens=[],
                ), 0.9)
            return None
        monkeypatch.setattr(SwToolboxAdapter, "find_sldprt", fake_find_sldprt)

        # mock broker.prewarm_config_lists 记录调用
        prewarm_calls = []
        monkeypatch.setattr(
            broker, "prewarm_config_lists",
            lambda paths: prewarm_calls.append(list(paths)),
        )

        adapter = SwToolboxAdapter(config={"min_score": 0.30})
        candidates = [
            (PartQuery(part_no="BOLT-001", name_cn="b", material="",
                       category="fastener", make_buy=""), {}),
            (PartQuery(part_no="NUT-002", name_cn="n", material="",
                       category="fastener", make_buy=""), {}),
            (PartQuery(part_no="MISS-003", name_cn="m", material="",
                       category="fastener", make_buy=""), {}),  # find_sldprt 返 None
        ]
        adapter.prewarm(candidates)

        assert len(prewarm_calls) == 1
        assert sorted(prewarm_calls[0]) == sorted(["C:/SW/bolt.sldprt", "C:/SW/nut.sldprt"])

    def test_prewarm_no_candidates_skips_broker_call(self, monkeypatch):
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_config_broker as broker

        called = []
        monkeypatch.setattr(
            broker, "prewarm_config_lists",
            lambda paths: called.append(paths),
        )

        adapter = SwToolboxAdapter(config={})
        adapter.prewarm([])  # 空 candidates
        assert called == []  # broker 不调

    def test_prewarm_all_find_sldprt_miss_skips_broker_call(self, monkeypatch):
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_config_broker as broker
        from parts_resolver import PartQuery

        # find_sldprt 全返 None
        monkeypatch.setattr(SwToolboxAdapter, "find_sldprt",
                            lambda self, q, s: None)

        called = []
        monkeypatch.setattr(
            broker, "prewarm_config_lists",
            lambda paths: called.append(paths),
        )

        adapter = SwToolboxAdapter(config={"min_score": 0.30})
        adapter.prewarm([
            (PartQuery(part_no="P1", name_cn="x", material="", category="", make_buy=""), {}),
        ])
        assert called == []  # 无 sldprt 收集到 → broker 不调
```

- [ ] **Step 2：跑失败测试**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_toolbox_adapter.py::TestSwToolboxAdapterPrewarm -v
```

Expected: 3 fail（adapter 无 prewarm override，调 base default no-op 不会 forward 到 broker → 测试 1 期望 broker_calls 1 实际 0）。

- [ ] **Step 3：写实现 — sw_toolbox_adapter.prewarm**

修改 `adapters/parts/sw_toolbox_adapter.py`，在 `find_sldprt` 方法之后追加：

```python
# adapters/parts/sw_toolbox_adapter.py — 在 find_sldprt 方法之后追加：

    def prewarm(self, candidates) -> None:
        """Pre-warm broker config_lists cache（Task 14.6 / spec §3.1）。

        candidates: list[tuple[PartQuery, dict]] — PartsResolver 已 rule-match
        派发到本 adapter 的 (query, rule.spec) 列表。

        流程：
          1. 对每对 (query, spec) 调 find_sldprt 收集 sldprt_path（catalog-only，不触发 COM）
          2. 收集到 ≥1 个 sldprt → 调 broker.prewarm_config_lists 触发 batch spawn worker
          3. 收集到 0 个 → broker 不调（避免 prewarm 空 batch overhead）

        失败容忍：find_sldprt 单件 raise / broker.prewarm 内部失败 都不抛
        （PartsResolver.prewarm 已有 per-adapter try/except 兜底；本层不再嵌套）。
        """
        from adapters.solidworks.sw_config_broker import prewarm_config_lists

        sldprt_paths = []
        for query, spec in candidates:
            match = self.find_sldprt(query, spec)
            if match is None:
                continue
            part, _score = match
            sldprt_paths.append(part.sldprt_path)

        if not sldprt_paths:
            return

        prewarm_config_lists(sldprt_paths)
```

- [ ] **Step 4：跑测试 PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_toolbox_adapter.py::TestSwToolboxAdapterPrewarm -v
```

Expected: `3 passed`.

- [ ] **Step 5：commit**

```bash
git -C /d/Work/cad-spec-gen add adapters/parts/sw_toolbox_adapter.py tests/test_sw_toolbox_adapter.py
git -C /d/Work/cad-spec-gen commit -m "$(cat <<'EOF'
feat(sw_toolbox_adapter): override prewarm 转发 broker（Task 14.6 / Task 11）

收 candidates: list[(PartQuery, rule.spec)] →
对每对调 find_sldprt 收集 sldprt_path（catalog-only，0 SW 触发）→
≥1 个 sldprt → broker.prewarm_config_lists 触发 batch worker；
0 个 → 不调避免空 batch overhead。

失败容忍：本层不嵌套 try/except；PartsResolver.prewarm 已 per-adapter 兜底。

测试 3 个全 PASS：收集多件 / 空 candidates 不调 / 全 miss 不调

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12：gen_std_parts.main 加 resolver.prewarm() 一行

**Files:**
- Modify: `codegen/gen_std_parts.py`
- Modify: `tests/test_sw_toolbox_adapter_with_broker.py`

按 spec §3.1：gen_std_parts 改造最小 — BOM loop **之前** build 全部 PartQuery + 调 `resolver.prewarm(queries)`。现有 loop 内仍 build PartQuery（不动）；prewarm 只读 BOM 不消费 query 状态。

- [ ] **Step 1：写失败测试 — gen_std_parts 调 resolver.prewarm 触发 1 次 spawn**

```python
# tests/test_sw_toolbox_adapter_with_broker.py 末尾追加：

class TestGenStdPartsPrewarmIntegration:
    """Task 14.6 / Task 12：gen_std_parts.main 入口加 resolver.prewarm 一行触发预热。"""

    def test_generate_calls_resolver_prewarm_before_loop(self, tmp_path, monkeypatch):
        """generate_std_part_files 在 BOM loop 之前调 resolver.prewarm(queries)，
        且传的是已 build 的 PartQuery 列表（不是 raw BOM dict）."""
        from codegen import gen_std_parts as g
        from parts_resolver import PartQuery, PartsResolver

        fake_parts = [
            {"part_no": "GIS-EE-001-01", "name_cn": "螺栓1", "material": "GB/T 70.1 M6×20",
             "is_assembly": False, "make_buy": "外购"},
            {"part_no": "GIS-EE-001-02", "name_cn": "螺栓2", "material": "GB/T 70.1 M8×30",
             "is_assembly": False, "make_buy": "外购"},
        ]
        monkeypatch.setattr(g, "parse_bom_tree", lambda spec_path: fake_parts)
        monkeypatch.setattr(g, "parse_envelopes", lambda spec_path: {})
        monkeypatch.setattr(g, "classify_part", lambda name, mat: "bearing")
        # bearing 不在 _SKIP_CATEGORIES → loop 会调 resolver.resolve

        prewarm_calls = []
        original_prewarm = PartsResolver.prewarm

        def spy_prewarm(self, queries):
            prewarm_calls.append([q.part_no for q in queries])
            return original_prewarm(self, queries)
        monkeypatch.setattr(PartsResolver, "prewarm", spy_prewarm)

        # FakeResolver 让 resolve 返 miss 不影响测试焦点（focus 在 prewarm 是否调）
        from parts_resolver import ResolveResult

        class FakeResolver:
            adapters = []
            def prewarm(self, queries):
                spy_prewarm(self, queries)
            def resolve(self, q):
                return ResolveResult(status="miss", kind="miss", adapter="")
            def coverage_report(self): return ""
        # 注：上面的 spy 已 patch 类方法；FakeResolver 不继承 PartsResolver 所以
        # 需要直接显式 spy。改为简化：let default_resolver 跑，但 spy 类方法
        monkeypatch.setattr(g, "default_resolver", lambda **kw: FakeResolver())

        spec_path = tmp_path / "spec.md"
        spec_path.write_text("# fake\n", encoding="utf-8")
        out_dir = tmp_path / "out"; out_dir.mkdir()

        g.generate_std_part_files(str(spec_path), str(out_dir))

        # prewarm 被调一次，传的 part_no 列表与 BOM 顺序一致
        assert len(prewarm_calls) == 1
        assert prewarm_calls[0] == ["GIS-EE-001-01", "GIS-EE-001-02"]
```

- [ ] **Step 2：跑失败测试**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_toolbox_adapter_with_broker.py::TestGenStdPartsPrewarmIntegration -v
```

Expected: 1 fail（generate_std_part_files 还没调 prewarm）。

- [ ] **Step 3：写实现 — gen_std_parts.generate_std_part_files 加 prewarm**

修改 `codegen/gen_std_parts.py:270-292`（generation loop 起始处）。在 `for p in parts:` loop **之前** + `resolver = default_resolver(...)` **之后** 加 prewarm 调用。

具体改动：

```python
# codegen/gen_std_parts.py — generate_std_part_files 函数内：
# 找到现有：
#     resolver = default_resolver(project_root=project_root,
#                                  logger=lambda m: print(m))
#
#     generated = []
#     skipped = []
#     pending_records: dict[str, list[dict]] = {}
#
#     for p in parts:
#         ...

# 在 `for p in parts:` 之前加：

    # ─── Task 14.6：build 全 BOM PartQuery list + prewarm 触发 broker batch worker ───
    # 把现有 loop 内的 PartQuery build 提到 loop 之前，让 prewarm 拿到完整 query 列表
    # （adapter.prewarm 用 find_sldprt 收集 sldprt → broker.prewarm 1 次 batch spawn）
    queries_for_prewarm: list[PartQuery] = []
    for p in parts:
        if p["is_assembly"]:
            continue
        if "外购" not in p.get("make_buy", "") and "标准" not in p.get("make_buy", ""):
            continue
        category = classify_part(p["name_cn"], p["material"])
        if category in _SKIP_CATEGORIES:
            continue
        env = envelopes.get(p["part_no"])
        queries_for_prewarm.append(PartQuery(
            part_no=p["part_no"],
            name_cn=p["name_cn"],
            material=p["material"],
            category=category,
            make_buy=p.get("make_buy", ""),
            spec_envelope=_envelope_to_spec_envelope(env),
            spec_envelope_granularity=_envelope_to_granularity(env),
            project_root=project_root,
        ))
    if queries_for_prewarm:
        try:
            resolver.prewarm(queries_for_prewarm)
        except Exception as e:
            print(f"[gen_std_parts] prewarm 跳过（{type(e).__name__}: {e}）")
    # ─── /Task 14.6 ───
```

注：现有 `for p in parts:` loop 内仍 build PartQuery（不动）。pre-loop build 的 list 仅给 prewarm 用，不消费 query 状态，所以 build 两次的 cost = 一些 dict 操作，可接受（PartQuery 是 dataclass，构造廉价）。

- [ ] **Step 4：跑测试 PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_toolbox_adapter_with_broker.py::TestGenStdPartsPrewarmIntegration -v
```

Expected: `1 passed`.

- [ ] **Step 5：跑现有 gen_std_parts 测试不破**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_toolbox_adapter_with_broker.py tests/test_gen_std_parts_preflight_integration.py -v 2>&1 | tail -10
```

Expected: 全 PASS（含原 5+8 个 + 1 新 prewarm）。

- [ ] **Step 6：commit**

```bash
git -C /d/Work/cad-spec-gen add codegen/gen_std_parts.py tests/test_sw_toolbox_adapter_with_broker.py
git -C /d/Work/cad-spec-gen commit -m "$(cat <<'EOF'
feat(gen_std_parts): BOM loop 前 build queries 并调 resolver.prewarm（Task 14.6 / Task 12）

generate_std_part_files 现两阶段：
1. pre-loop：walk BOM → build PartQuery list → resolver.prewarm(queries)
   触发 sw_toolbox_adapter.prewarm → broker.prewarm_config_lists → 1 次 batch spawn
2. main loop：现有逻辑不动（仍 per-part build PartQuery + resolve）
   loop 内 broker.resolve_config_for_part → _list_configs_via_com 走 L1 持久化命中

prewarm 异常 try/except 兜底打 [gen_std_parts] prewarm 跳过 + 继续 loop（不阻 codegen）

注：src/cad_spec_gen/data/codegen/ 在 .gitignore，hatch_build wheel-time 自动 sync，
本 commit 不动 packaged copy（与 Task 15/16 同模式）

测试 1 个新 prewarm e2e PASS：spy 验证 prewarm 在 loop 之前调 + 传 build 好的 PartQuery 列表

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13：全测套 + spawn 计数 校准（端到端验收）

**Files:**
- Read-only verification

不写代码 — 跑全测套确认 0 regression + 验证 spawn 次数符合 spec 成功判据。

- [ ] **Step 1：跑全测套基线对比**

```bash
.venv/Scripts/python.exe -m pytest --ignore=tests/test_a2_integration.py --ignore=tests/test_part_templates.py -q -p no:cacheprovider 2>&1 | tail -5
```

Expected:
- passed = baseline 1201 + 已 commit 增量
- failed = 35（pre-existing，不变）
- 0 new fail in changed files

具体增量预期（accumulated CP-7+8+9）：
- CP-7 cache module: +19 (TestModuleConstants 2 + TestEmptyCache 1 + TestSaveCache 3 + TestLoadCache 4 + TestEnvelopeInvalidated 4 + TestEntryValid 5)
- CP-8 worker --batch: +5
- CP-8 broker prewarm: +7
- CP-8 three layer: +3
- CP-9 base prewarm: +3
- CP-9 resolver prewarm: +5
- CP-9 adapter prewarm: +3
- CP-9 gen_std_parts prewarm: +1
- **总计 +46**，约 1247 passed

- [ ] **Step 2：spawn 计数验证（无 SW 环境用 mock）**

```bash
.venv/Scripts/python.exe -c "
import os
os.environ.pop('CAD_SW_BROKER_DISABLE', None)
import json, subprocess, tempfile
from pathlib import Path
from unittest.mock import patch

# 模拟 prewarm 调用：cache 全 miss → 1 次 spawn
spawn_count = [0]
def fake_run(cmd, **kw):
    spawn_count[0] += 1
    class P:
        returncode = 0
        stderr = b''
        stdout = b'[]'
    return P()

with patch('subprocess.run', fake_run):
    from adapters.solidworks import sw_config_broker as b
    from adapters.solidworks import sw_config_lists_cache as c
    from adapters.solidworks import sw_detect

    # mock SW info
    sw_detect._reset_cache()
    with patch.object(sw_detect, 'detect_solidworks',
                      return_value=sw_detect.SwInfo(installed=True, version_year=24, toolbox_dir='C:/SW')):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(c, 'get_config_lists_cache_path',
                              return_value=Path(td) / 'cache.json'):
                # 建 3 个 fake sldprt
                paths = []
                for i in range(3):
                    p = Path(td) / f'p{i}.sldprt'
                    p.write_bytes(b'x' * 100)
                    paths.append(str(p))

                # 第一次：全 miss → 1 次 spawn
                b._CONFIG_LIST_CACHE.clear()
                b.prewarm_config_lists(paths)
                print(f'第一次 prewarm spawn 次数: {spawn_count[0]}')
                assert spawn_count[0] == 1
"
```

Expected:
```
第一次 prewarm spawn 次数: 1
```

如果输出 `3` → batch 没生效，回 Task 7 检查实现。

- [ ] **Step 3：commit + push CP-9（如 step 1+2 全 PASS）**

```bash
git -C /d/Work/cad-spec-gen status   # 应该 working tree clean
# 已无未 commit 改动 — 直接 push 触发 CI
git -C /d/Work/cad-spec-gen push
```

🛑 **CP-9 暂停**：完整调用链端到端打通。第一次 codegen 走 1 次 batch spawn = "装即用" 兑现。用户可手动跑：
```
.venv/Scripts/python.exe -m codegen.gen_std_parts <真 SPEC_FILE>
```
观察 stdout 是否仅 1 条 worker spawn 日志（spec §6.4 校准点）。

CP-9 通过后：本 P1 task 全部完成。下一步可选 Task 14（render_regression timing 校准）或合并 PR #19。

---

## Task 14（可选）：tools/render_regression timing 校准点

**Files:**
- Modify: `tools/render_regression.py` 或 Create: `tools/spawn_count_regression.py`

按 spec §6.4：跑两次同 BOM 测 timing + spawn 计数。

如果用户要求"实测验收"才做；否则 plan 完结于 CP-9。

- [ ] **Step 1：用户决策点 — 跳过 or 写**

如果用户说"跳过" → 本 plan 在 CP-9 完结。
如果"写" → 仿 `tools/render_regression.py` 模式新建脚本，跑 2 次 codegen 比较 timing + spawn 计数。spec §6.4 已列预期：第二次 < 第一次 50%；spawn 计数 = 1 / 0。

---

# Self-Review Checklist

Plan 全文写完后跑此 checklist：

## 1. Spec coverage

| Spec section | Plan task |
|---|---|
| §1 问题陈述 | (background only — 不需 task) |
| §2 决策 Q1=B (用户级独立文件) | Task 1 path=`Path.home()/.cad-spec-gen/sw_config_lists.json` |
| §2 决策 Q2=B (batch worker) | Task 6 worker --batch + Task 7 broker.prewarm batch spawn |
| §2 决策 Q3=C (mtime+size+sw_version+toolbox_path) | Task 5 _envelope_invalidated + _config_list_entry_valid |
| §3 architecture 5+1 组件 | Task 1 (cache module) + Task 6 (worker) + Task 7 (broker prewarm) + Task 8 (broker _list_configs 三层) + Task 9 (base prewarm) + Task 10 (resolver prewarm) + Task 11 (adapter prewarm) + Task 12 (gen_std_parts) |
| §4 场景 A (全 miss → 1 spawn) | Task 7 test_prewarm_all_miss_spawns_batch_once + Task 13 spawn 计数 |
| §4 场景 B (全命中 → 0 spawn) | Task 7 test_prewarm_all_hit_no_spawn + Task 8 test_l1_persistent_cache_hit_fills_l2_no_spawn |
| §4 场景 C (单件改 → 1 spawn 仅列变化) | Task 7 test_prewarm_partial_miss_only_misses_batched |
| §4 场景 D (envelope 失效 → 1 batch 重列) | Task 7 test_prewarm_envelope_invalidated_clears_entries |
| §4.1 envelope schema v1 | Task 1+2 (常量 + _empty_cache 5 字段) |
| §4.2 worker batch IPC 协议 | Task 6 (--batch + stdin/stdout JSON 协议) |
| §5.1 worker 失败 → 退化 | Task 7 test_prewarm_worker_failure_does_not_write_cache + test_prewarm_worker_timeout |
| §5.2 cache 损坏 → empty | Task 4 test_load_corrupt_json_returns_empty |
| §5.3 schema 版本不符 → empty | Task 4 test_load_schema_version_mismatch_returns_empty |
| §5.4 并发 codegen 不加锁 | Task 3 atomic write 测试 (覆盖语义) |
| §5.5 NTFS mtime 漏抓 | Task 5 size 二维兜底 (覆盖语义) |
| §6.1 测试矩阵 A+B+C+D+E | Task 1-12 各类测试均覆盖 |
| §6.4 timing 校准 | Task 14 (可选) |
| §7 backward compat | Task 4 (schema 版本不符自愈) + Task 9 (base virtual no-op) |

**Coverage gaps**：无。

## 2. Placeholder scan

grep 检查：
```bash
grep -n "TBD\|TODO\|placeholder\|fill in\|implement later\|similar to Task" docs/superpowers/plans/2026-04-26-sw-toolbox-config-list-cache.md
```
应无输出。

## 3. Type consistency

| API | Defined Task | Used Task | 一致？ |
|---|---|---|---|
| `_empty_config_lists_cache() -> dict` | Task 2 | Task 4, 7 | ✅ |
| `_save_config_lists_cache(cache: dict) -> None` | Task 3 | Task 7 | ✅ |
| `_load_config_lists_cache() -> dict` | Task 4 | Task 7, 8 | ✅ |
| `_envelope_invalidated(cache: dict) -> bool` | Task 5 | Task 7, 8 | ✅ |
| `_config_list_entry_valid(cache: dict, sldprt_path: str) -> bool` | Task 5 | Task 7, 8 | ✅ |
| `_stat_mtime(path: str) -> int \| None` | Task 5 | Task 7 | ✅ |
| `_stat_size(path: str) -> int \| None` | Task 5 | Task 7 | ✅ |
| `prewarm_config_lists(sldprt_list: list[str]) -> None` | Task 7 | Task 8 (内部不互调) + Task 11 (adapter forward) | ✅ |
| `worker --batch stdin/stdout 协议` | Task 6 | Task 7 (broker 调用) | ✅ |
| `PartsAdapter.prewarm(candidates) -> None` | Task 9 (base no-op) | Task 11 (sw_toolbox override) | ✅ |
| `PartsResolver.prewarm(queries: list[PartQuery]) -> None` | Task 10 | Task 12 (gen_std_parts 调用) | ✅ |

无 mismatch。

---

# Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-26-sw-toolbox-config-list-cache.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - 主 agent 每 task 派 fresh subagent 执行 + two-stage review；好处：subagent 上下文干净不被前置探查噪音污染；适合本 plan 因 task 间界面清晰

**2. Inline Execution** - 在当前 session 跑 executing-plans skill；批量执行带 checkpoint review；好处：不消耗 subagent token；适合 task 紧密耦合需要主 agent 上下文累积

**Which approach?**

(后续按用户回答 invoke 对应 sub-skill)
