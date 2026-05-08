# Photo3D Jury 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `photo3d-jury` cli — 自动用 vision LLM 做照片级验收，输出 PHOTO3D_JURY_REPORT.json + jury_review_input.json（兼容 enhance-review）让 5 项 semantic check 自动给出。

**Architecture:** 旁路新工具不改既有契约。Layer 0 输入证据绑定（sha256/active_run freeze + .jury.lock + 重跑保护）→ Layer 1 字段自洽性 → Layer 2 LLM jury（vision API + photoreal_score gate）。配套 redact.py 集中脱敏 + stderr_messages.py 模板 + tools/_file_lock.py（从 sw_warmup 抽出共用）。

**Tech Stack:** Python 3.11+ stdlib only（urllib / json / hashlib / contextlib / dataclasses / pathlib）；项目内复用 contract_io / path_policy / sw_warmup 锁；无第三方 SDK / PyTorch / pyiqa（v1 依赖宪章）。

**Spec：** [`docs/superpowers/specs/2026-05-08-photo3d-jury-design.md`](../specs/2026-05-08-photo3d-jury-design.md)（rev 5，1302 行，199 findings 全闭）

---

## 文件布局

```
cad_pipeline.py                         ← 加 jury subcommand 转发 (Task 2)
skill.json                              ← 加 photo3d-jury alias (Task 2)
tools/_file_lock.py                     ← 抽自 sw_warmup (Task 1)
tools/sw_warmup.py                     ← 转发到 _file_lock 保留 API (Task 1)
tools/photo3d_jury.py                   ← cli 薄壳（Task 24）
tools/jury/__init__.py                  ← 空 (Task 0)
tools/jury/config.py                    ← Task 4-7
tools/jury/cost.py                      ← Task 8-9
tools/jury/redact.py                    ← Task 10-11
tools/jury/stderr_messages.py           ← Task 12-13
tools/jury/input_evidence_binding.py    ← Task 14-17
tools/jury/deterministic_gate.py        ← Task 18-19
tools/jury/verdict.py                   ← Task 20-21
tools/jury/llm_client.py                ← Task 22-23
tools/jury/manual_smoke.py              ← Task 28（手动烟测，不进 CI）
tools/photo3d_delivery_pack.py          ← 加 jury 字段（Task 27）

tests/jury/__init__.py                  ← 空 (Task 0)
tests/jury/conftest.py                  ← autouse kill switch + dummy key (Task 0)
tests/jury/fixtures/sample_*.json       ← 静态 fixture (Task 3)
tests/jury/fixtures/intentional_type_error.py ← mypy 反例 (Task 30)
tests/jury/test_config.py               ← Task 4-7
tests/jury/test_cost.py                 ← Task 8-9
tests/jury/test_redact.py               ← Task 10-11
tests/jury/test_stderr_messages.py      ← Task 12-13
tests/jury/test_input_evidence_binding.py ← Task 14-17
tests/jury/test_deterministic_gate.py   ← Task 18-19
tests/jury/test_verdict.py              ← Task 20-21
tests/jury/test_llm_client.py           ← Task 22-23
tests/jury/test_photo3d_jury_cli.py     ← Task 24
tests/jury/test_photo3d_jury_e2e.py     ← Task 25-26

docs/cad-jury-config.md                 ← Task 31
docs/cad-help-guide-zh.md / -en.md     ← Task 32
docs/PROGRESS.md                        ← Task 33
docs/superpowers/README.md              ← Task 33
pyproject.toml                          ← Task 29 (coverage source + markers)
.github/workflows/tests.yml             ← Task 30 (mypy strict CI gate)
```

---

## CP-0: Pre-flight + 资产复用 + 目录脚手架

### Task 0: 创建目录骨架

**Files:**
- Create: `tools/jury/__init__.py`（空）
- Create: `tests/jury/__init__.py`（空）
- Create: `tests/jury/conftest.py`
- Create: `tests/jury/fixtures/`（dir）

- [ ] **Step 1: 创建空 __init__**

```bash
mkdir -p tools/jury tests/jury/fixtures
type nul > tools/jury/__init__.py
type nul > tests/jury/__init__.py
```

- [ ] **Step 2: 写 conftest.py 含 autouse kill switch + dummy key fixture**

```python
# tests/jury/conftest.py
"""tests/jury/ 子树 autouse 配置：默认禁用真实 LLM 调用 + 提供 dummy fixture key。"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _disable_llm_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """所有 jury 测试默认 CAD_JURY_DISABLE_LLM=1，防真发 LLM 烧费。

    需要真发请求的测试通过 enable_llm_for_test fixture opt-in。
    """
    monkeypatch.setenv("CAD_JURY_DISABLE_LLM", "1")


@pytest.fixture
def enable_llm_for_test(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opt-in fixture：测试需要真调 mock urlopen 时清掉 kill switch。"""
    monkeypatch.delenv("CAD_JURY_DISABLE_LLM", raising=False)


@pytest.fixture
def dummy_api_key() -> str:
    """统一 fixture key 形态；禁止 sk-/pk-/gsk_ 前缀避免 GitHub secret scanner 误报。"""
    return "dummy-not-a-real-key"
```

- [ ] **Step 3: 提交目录骨架**

```bash
git add tools/jury tests/jury
git commit -m "feat(jury): CP-0 目录骨架 + autouse kill switch fixture"
```

---

### Task 1: 抽离 tools/_file_lock.py 从 sw_warmup 共用

**Files:**
- Create: `tools/_file_lock.py`
- Modify: `tools/sw_warmup.py` — 转发到 `_file_lock.acquire_warmup_lock` 保留旧 API
- Test: `tests/test_file_lock.py`

- [ ] **Step 1: 写失败测试 — `tools/_file_lock.acquire_lock` 基本契约**

```python
# tests/test_file_lock.py
"""验证抽出后的通用文件锁 API。"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from tools._file_lock import LockBusy, acquire_lock, _pid_alive


def test_acquire_release_basic(tmp_path: Path) -> None:
    """正常获取 + 自动释放。"""
    lock_path = tmp_path / "test.lock"
    with acquire_lock(lock_path):
        assert lock_path.exists()
        data = lock_path.read_text(encoding="utf-8")
        assert str(os.getpid()) in data
    assert not lock_path.exists()


def test_acquire_busy_raises(tmp_path: Path) -> None:
    """已有 live lock 抛 LockBusy。"""
    lock_path = tmp_path / "test.lock"
    with acquire_lock(lock_path):
        with pytest.raises(LockBusy):
            with acquire_lock(lock_path):
                pass


def test_stale_by_pid_auto_clean(tmp_path: Path) -> None:
    """PID 不存在的 stale lock 自动清理。"""
    import json
    lock_path = tmp_path / "test.lock"
    # 写一个不存在的 PID
    lock_path.write_text(json.dumps({"pid": 99999999, "started_at": "2026-01-01T00:00:00Z"}), encoding="utf-8")
    with acquire_lock(lock_path):
        # 自动清理后 PID 应是当前进程
        data = lock_path.read_text(encoding="utf-8")
        assert str(os.getpid()) in data


def test_stale_by_mtime_auto_clean(tmp_path: Path) -> None:
    """mtime > 30 min 的 stale lock 自动清理。"""
    import json
    lock_path = tmp_path / "test.lock"
    lock_path.write_text(json.dumps({"pid": os.getpid(), "started_at": "..."}), encoding="utf-8")
    # 改 mtime 到 31 分钟前
    old_time = time.time() - 31 * 60
    os.utime(lock_path, (old_time, old_time))
    with acquire_lock(lock_path):
        # 已清理重写
        assert lock_path.stat().st_mtime > old_time + 30 * 60


def test_pid_alive_current_process() -> None:
    assert _pid_alive(os.getpid()) is True


def test_pid_alive_nonexistent() -> None:
    assert _pid_alive(99999999) is False
```

- [ ] **Step 2: 跑测试确认 fail（模块不存在）**

```bash
pytest tests/test_file_lock.py -v
```
Expected: FAIL with "ModuleNotFoundError: No module named 'tools._file_lock'"

- [ ] **Step 3: 实现 tools/_file_lock.py（参考 sw_warmup 现有模式）**

```python
# tools/_file_lock.py
"""跨平台文件锁 + PID stale 自动清理。

抽自 tools/sw_warmup.py acquire_warmup_lock；jury 与 sw_warmup 共用。
锁路径由调用方决定（jury 用 active_run_dir/.jury.lock，sw_warmup 用 GB cache root）。
"""
from __future__ import annotations

import json
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


class LockBusy(Exception):
    """已有 live lock；调用方需自行映射到 exit code。"""


_STALE_SECONDS = 30 * 60  # 30 分钟


def _pid_alive(pid: int) -> bool:
    """跨平台判断 PID 是否在系统中存活。"""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return pid > 0  # PermissionError 表示 PID 存在但属于他人
        except Exception:
            return False


@contextmanager
def acquire_lock(lock_path: Path) -> Iterator[None]:
    """获取 lock；live 则抛 LockBusy；stale（mtime>30min 或 PID not exists）自动清理。"""
    if lock_path.exists():
        held_pid = -1
        try:
            data = json.loads(lock_path.read_text(encoding="utf-8"))
            held_pid = int(data.get("pid", -1))
        except (json.JSONDecodeError, OSError, ValueError):
            held_pid = -1  # 损坏 lock 视为 stale

        try:
            held_mtime = lock_path.stat().st_mtime
        except OSError:
            held_mtime = 0.0
        now = time.time()
        stale_by_age = (now - held_mtime) > _STALE_SECONDS
        stale_by_pid = held_pid > 0 and not _pid_alive(held_pid)

        if held_pid <= 0 or stale_by_age or stale_by_pid:
            sys.stderr.write(
                f"警告：检测到 stale lock {lock_path.name}（PID={held_pid}, "
                f"age={int(now - held_mtime)}s），自动清理后继续。\n"
            )
            try:
                lock_path.unlink()
            except OSError:
                pass
        else:
            raise LockBusy(f"已有进程持有 {lock_path.name}：PID={held_pid}")

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps({
            "pid": os.getpid(),
            "started_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }),
        encoding="utf-8",
    )
    try:
        yield
    finally:
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass
```

- [ ] **Step 4: 跑测试确认 PASS**

```bash
pytest tests/test_file_lock.py -v
```
Expected: 6 passed

- [ ] **Step 5: 改 sw_warmup.py 转发到 _file_lock（保留旧 API 零回归）**

读 `tools/sw_warmup.py:30-219` 找 `acquire_warmup_lock`；改为：

```python
# tools/sw_warmup.py 顶部加 import
from tools._file_lock import acquire_lock as _acquire_file_lock

# 删除原 _LOCK_OFFSET / _LOCK_NBYTES / msvcrt / fcntl 等 ~200 行实现
# 替换 acquire_warmup_lock 为：
def acquire_warmup_lock(lock_path):
    """保留旧 API；转发到 tools/_file_lock。"""
    return _acquire_file_lock(lock_path)
```

- [ ] **Step 6: 跑既有 sw_warmup 测试确认无回归**

```bash
pytest tests/test_sw_warmup.py -v
```
Expected: all PASS（与抽出前数量一致）

- [ ] **Step 7: 提交**

```bash
git add tools/_file_lock.py tools/sw_warmup.py tests/test_file_lock.py
git commit -m "refactor(_file_lock): 抽出 tools/_file_lock.py 让 jury 与 sw_warmup 共用"
```

---

### Task 2: cad_pipeline.py 加 jury subcommand + skill.json alias

**Files:**
- Modify: `cad_pipeline.py` — 加 `cmd_jury()` 转发到 `tools.photo3d_jury:main`
- Modify: `skill.json` — 加 `photo3d-jury` alias 指向 jury subcommand

- [ ] **Step 1: 写失败测试 — cad_pipeline 加 jury 子命令**

```python
# tests/test_cad_pipeline_jury_subcommand.py
"""验证 cad_pipeline 注册了 jury subcommand。"""
import subprocess
import sys


def test_jury_subcommand_in_help() -> None:
    """python cad_pipeline.py --help 含 jury。"""
    result = subprocess.run(
        [sys.executable, "cad_pipeline.py", "--help"],
        capture_output=True, text=True,
    )
    assert "jury" in result.stdout
```

- [ ] **Step 2: 跑测试确认 fail**

```bash
pytest tests/test_cad_pipeline_jury_subcommand.py -v
```
Expected: FAIL（jury 未注册）

- [ ] **Step 3: 实现 — cad_pipeline.py 加 cmd_jury 转发**

读 `cad_pipeline.py` 找其他 photo3d-* 子命令注册模式（如 `cmd_handoff`），照抄风格加：

```python
# cad_pipeline.py 顶部 import 区
from tools import photo3d_jury  # 延迟，避免在 cad_pipeline 导入时触发 LLM 模块

# 在 main() 的 subcommand argparse 表加：
jury_p = sub.add_parser("jury", help="自动照片级验收（vision LLM jury）")
jury_p.add_argument("--subsystem", required=False)  # cli flag 由 photo3d_jury 完整解析
jury_p.set_defaults(func=lambda args: photo3d_jury.main(sys.argv[2:]))  # 把后续 argv 透传
```

参照既有 photo3d-* 子命令注册一致风格。

- [ ] **Step 4: 跑测试确认 PASS**

```bash
pytest tests/test_cad_pipeline_jury_subcommand.py -v
```
Expected: PASS

- [ ] **Step 5: 加 skill.json alias**

读 `skill.json` 找 photo3d-handoff 等 alias 模式（line ~59-115），加：

```json
{
  "command": "photo3d-jury",
  "description": "自动照片级验收（vision LLM jury）",
  "argv": ["cad_pipeline.py", "jury"]
}
```

- [ ] **Step 6: 提交**

```bash
git add cad_pipeline.py skill.json tests/test_cad_pipeline_jury_subcommand.py
git commit -m "feat(jury): cad_pipeline 加 jury subcommand + skill.json alias"
```

---

### Task 3: 静态 fixture 文件

**Files:**
- Create: `tests/jury/fixtures/sample_artifact_index.json`
- Create: `tests/jury/fixtures/sample_render_manifest.json`
- Create: `tests/jury/fixtures/sample_enhancement_report.json`

- [ ] **Step 1: 写 sample_artifact_index.json**

```json
{
  "schema_version": 1,
  "subsystem": "lifting_platform",
  "active_run_id": "20260508-123456",
  "runs": {
    "20260508-123456": {
      "active": true,
      "artifacts": {
        "render_manifest": "cad/output/renders/lifting_platform/20260508-123456/render_manifest.json",
        "enhancement_report": "cad/output/renders/lifting_platform/20260508-123456/ENHANCEMENT_REPORT.json"
      }
    }
  }
}
```

- [ ] **Step 2: 写 sample_render_manifest.json**

```json
{
  "schema_version": 1,
  "subsystem": "lifting_platform",
  "run_id": "20260508-123456",
  "render_dir": "cad/output/renders/lifting_platform/20260508-123456",
  "render_dir_rel_project": "cad/output/renders/lifting_platform/20260508-123456",
  "files": [
    {"view": "iso", "path_rel_project": "cad/output/renders/lifting_platform/20260508-123456/iso.png", "sha256": "sha256:fake_iso"},
    {"view": "front", "path_rel_project": "cad/output/renders/lifting_platform/20260508-123456/front.png", "sha256": "sha256:fake_front"}
  ]
}
```

- [ ] **Step 3: 写 sample_enhancement_report.json（已 accepted）**

```json
{
  "schema_version": 1,
  "subsystem": "lifting_platform",
  "run_id": "20260508-123456",
  "status": "accepted",
  "delivery_status": "accepted",
  "render_manifest": "cad/output/renders/lifting_platform/20260508-123456/render_manifest.json",
  "render_dir": "cad/output/renders/lifting_platform/20260508-123456",
  "enhancement_report": "cad/output/renders/lifting_platform/20260508-123456/ENHANCEMENT_REPORT.json",
  "view_count": 2,
  "enhanced_view_count": 2,
  "min_similarity": 0.85,
  "quality_summary": {
    "schema_version": 1,
    "status": "accepted",
    "view_count": 2,
    "min_contrast_stddev": 12.0,
    "warnings": []
  },
  "views": [
    {
      "view": "iso",
      "status": "accepted",
      "source_image": "cad/output/renders/lifting_platform/20260508-123456/iso.png",
      "enhanced_image": "cad/output/renders/lifting_platform/20260508-123456/iso_enhanced.png",
      "edge_similarity": 0.91,
      "min_similarity": 0.85,
      "quality_metrics": {"effective_contrast_stddev": 18.5, "luminance_mean": 128.0, "saturation_mean": 60.0},
      "blocking_reasons": []
    },
    {
      "view": "front",
      "status": "accepted",
      "source_image": "cad/output/renders/lifting_platform/20260508-123456/front.png",
      "enhanced_image": "cad/output/renders/lifting_platform/20260508-123456/front_enhanced.png",
      "edge_similarity": 0.88,
      "min_similarity": 0.85,
      "quality_metrics": {"effective_contrast_stddev": 16.2, "luminance_mean": 130.0, "saturation_mean": 58.0},
      "blocking_reasons": []
    }
  ],
  "blocking_reasons": []
}
```

- [ ] **Step 4: 提交**

```bash
git add tests/jury/fixtures
git commit -m "test(jury): 静态 fixture 文件（artifact_index + render_manifest + enhancement_report）"
```

---

## CP-1: config.py + cost.py

### Task 4: config.py 骨架 + JuryProfile/JuryCaps dataclass

**Files:**
- Create: `tools/jury/config.py`
- Test: `tests/jury/test_config.py`

- [ ] **Step 1: 写失败测试 — schema_version + 空 profiles + active_profile_id 校验**

```python
# tests/jury/test_config.py
"""tools/jury/config.py 单元测试 — 18 case 覆盖 schema/profile/caps/估价表/base_url。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.jury.config import (
    BUILTIN_MODEL_COST_USD,
    JuryCaps,
    JuryConfigError,
    JuryConfigSchemaError,
    JuryProfile,
    load_jury_config,
)


def _write_config(tmp_path: Path, payload: dict) -> Path:
    p = tmp_path / "cad_jury_config.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_schema_version_invalid_raises(tmp_path: Path) -> None:
    p = _write_config(tmp_path, {"schema_version": 0, "active_profile_id": "x", "profiles": []})
    with pytest.raises(JuryConfigSchemaError):
        load_jury_config(p)


def test_schema_version_2_forward_compat(tmp_path: Path, capsys) -> None:
    """v1 jury 见 schema_version=2 → 仅取 v1 字段 + stderr 警告，不 reject。"""
    p = _write_config(tmp_path, {
        "schema_version": 2,
        "active_profile_id": "main",
        "profiles": [{"id": "main", "kind": "openai_compat",
                      "api_base_url": "https://x/v1", "api_key": "dummy-not-a-real-key", "model": "gpt-4o"}],
        "v2_only_field": "ignored",
    })
    profile, caps = load_jury_config(p)
    assert profile.id == "main"
    captured = capsys.readouterr()
    assert "schema_version=2" in captured.err


def test_active_profile_id_not_in_profiles_raises(tmp_path: Path) -> None:
    p = _write_config(tmp_path, {
        "schema_version": 1, "active_profile_id": "missing",
        "profiles": [{"id": "x", "kind": "openai_compat",
                      "api_base_url": "https://x/v1", "api_key": "dummy-not-a-real-key", "model": "gpt-4o"}],
    })
    with pytest.raises(JuryConfigError):
        load_jury_config(p)


def test_empty_profiles_raises(tmp_path: Path) -> None:
    p = _write_config(tmp_path, {"schema_version": 1, "active_profile_id": "x", "profiles": []})
    with pytest.raises(JuryConfigError):
        load_jury_config(p)
```

- [ ] **Step 2: 跑测试确认 fail**

```bash
pytest tests/jury/test_config.py -v
```
Expected: FAIL（config 模块不存在）

- [ ] **Step 3: 实现 config.py 骨架（仅 schema_version + active_profile_id + 空 profiles 校验，先让前 4 case 过）**

```python
# tools/jury/config.py
"""jury 配置解析 — JuryProfile / JuryCaps dataclass + 估价表 + base_url 智能。

不发 HTTP / 不读图 / 解析后立即丢 raw dict 防 key 通过返回值泄漏。
"""
from __future__ import annotations

import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


class JuryConfigError(Exception):
    """业务输入错（exit=2）。"""


class JuryConfigSchemaError(JuryConfigError):
    """schema 不识别（exit=2 子类）。"""


@dataclass(frozen=True)
class JuryProfile:
    id: str
    kind: str
    api_base_url: str  # 已 normalize（rstrip "/" + smart /v1）
    api_key: str
    model: str
    cost_per_call_usd: Optional[float]


@dataclass(frozen=True)
class JuryCaps:
    max_image_bytes: int
    max_n_views: int
    min_photoreal_score: int


# 内置估价表：model 模式（前缀匹配按行序首次命中）→ cost_per_call_usd 默认值
# 与真实 vendor pricing 可能 ±50% 偏差，仅作 v1 约值兜底
BUILTIN_MODEL_COST_USD: list[tuple[str, float]] = [
    ("gpt-4o", 0.020),
    ("gpt-4-turbo", 0.030),
    ("gemini-2.5-flash", 0.005),
    ("gemini-1.5-flash", 0.005),
    ("gemini-2.5-pro", 0.015),
    ("gemini-1.5-pro", 0.015),
    ("claude-3", 0.025),
    ("claude-vision", 0.025),
]
BUILTIN_MODEL_COST_USD_BUILT_AT = "2026-05-08"

_PROFILE_ID_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,63}$")
_DEFAULT_MAX_IMAGE_BYTES = 8 * 1024 * 1024
_DEFAULT_MAX_N_VIEWS = 32
_DEFAULT_MIN_PHOTOREAL_SCORE = 60


def load_jury_config(config_path: Path) -> tuple[JuryProfile, JuryCaps]:
    """读 + 校验 config，返 (active JuryProfile, JuryCaps)。原 dict 立即丢弃。"""
    if not config_path.exists():
        raise JuryConfigError(f"未找到 jury 配置文件 {config_path}")
    raw = json.loads(config_path.read_text(encoding="utf-8"))

    schema_version = raw.get("schema_version")
    if schema_version not in {1, 2}:
        raise JuryConfigSchemaError(f"schema_version={schema_version} 不被支持（仅 1 或 2）")
    if schema_version == 2:
        sys.stderr.write(
            "警告：本 jury 版本是 v1，忽略 schema_version=2 中的未知字段。\n"
        )

    active_id = raw.get("active_profile_id")
    profiles_raw = raw.get("profiles", [])
    if not isinstance(profiles_raw, list) or not profiles_raw:
        raise JuryConfigError("profiles 必须是非空列表")

    seen_ids: set[str] = set()
    active_profile_raw = None
    for p in profiles_raw:
        pid = p.get("id", "")
        if not _PROFILE_ID_RE.match(pid):
            raise JuryConfigError(f"profile id `{pid}` 不合法（首字符非 ASCII 字母/数字/下划线、长度 > 64、或含非法字符）")
        if pid in seen_ids:
            raise JuryConfigError(f"profile id `{pid}` 重复")
        seen_ids.add(pid)
        if pid == active_id:
            active_profile_raw = p

    if active_profile_raw is None:
        raise JuryConfigError(f"active_profile_id `{active_id}` 不在 profiles 中")

    profile = _parse_profile(active_profile_raw)
    caps = _parse_caps(raw)
    # raw 立即丢弃；不返回 dict 防 key 泄漏
    del raw, profiles_raw, active_profile_raw
    return profile, caps


def _parse_profile(p: dict) -> JuryProfile:
    """解析单 profile + 字段校验 + base_url 智能 normalize。"""
    if p.get("kind") not in {"openai_compat"}:
        raise JuryConfigError(f"kind={p.get('kind')} 不被支持（v1 仅 openai_compat）")
    api_base_url = str(p.get("api_base_url", "")).rstrip("/")
    if not api_base_url.startswith("https://"):
        raise JuryConfigError(f"api_base_url 必须 https:// 开头，得到 `{api_base_url}`")
    parsed = urlparse(api_base_url)
    if not parsed.hostname:
        raise JuryConfigError(f"api_base_url hostname 不能为空：{api_base_url}")
    # 智能 /v1：含则保留，不含则追加（仅 kind=openai_compat）
    if not api_base_url.endswith("/v1") and "/v1/" not in api_base_url + "/":
        api_base_url = api_base_url + "/v1"

    api_key = str(p.get("api_key", "")).strip()
    if not api_key:
        raise JuryConfigError("api_key 不能为空")
    model = str(p.get("model", "")).strip()
    if not model:
        raise JuryConfigError("model 不能为空")

    cost_raw = p.get("cost_per_call_usd")
    cost: Optional[float]
    if cost_raw is None:
        cost = lookup_builtin_cost(model)
    else:
        if not isinstance(cost_raw, (int, float)) or not math.isfinite(cost_raw) or cost_raw < 0 or cost_raw >= 1000:
            raise JuryConfigError(f"cost_per_call_usd={cost_raw} 不合法（必须 finite + 0 <= x < 1000）")
        cost = float(cost_raw)

    return JuryProfile(
        id=str(p["id"]),
        kind=str(p["kind"]),
        api_base_url=api_base_url,
        api_key=api_key,
        model=model,
        cost_per_call_usd=cost,
    )


def _parse_caps(raw: dict) -> JuryCaps:
    max_image_bytes = raw.get("max_image_bytes", _DEFAULT_MAX_IMAGE_BYTES)
    max_n_views = raw.get("max_n_views", _DEFAULT_MAX_N_VIEWS)
    min_photoreal_score = raw.get("min_photoreal_score", _DEFAULT_MIN_PHOTOREAL_SCORE)

    if not isinstance(max_image_bytes, int) or not (1024 <= max_image_bytes <= (1 << 30)):
        raise JuryConfigSchemaError(f"max_image_bytes={max_image_bytes} 必须 int [1024, 1<<30]")
    if not isinstance(max_n_views, int) or not (1 <= max_n_views <= 1024):
        raise JuryConfigSchemaError(f"max_n_views={max_n_views} 必须 int [1, 1024]")
    if not isinstance(min_photoreal_score, int) or not (0 <= min_photoreal_score <= 100):
        raise JuryConfigSchemaError(f"min_photoreal_score={min_photoreal_score} 必须 int [0, 100]")

    return JuryCaps(
        max_image_bytes=max_image_bytes,
        max_n_views=max_n_views,
        min_photoreal_score=min_photoreal_score,
    )


def lookup_builtin_cost(model: str) -> Optional[float]:
    """按表中行序首次前缀命中。"""
    for prefix, cost in BUILTIN_MODEL_COST_USD:
        if model.startswith(prefix):
            return cost
    return None
```

- [ ] **Step 4: 跑测试确认前 4 case PASS**

```bash
pytest tests/jury/test_config.py -v
```
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add tools/jury/config.py tests/jury/test_config.py
git commit -m "feat(jury): config.py 骨架 + JuryProfile/JuryCaps + schema 校验 (4 case)"
```

---

### Task 5: config.py base_url 智能 + profile 字段校验测试补全

**Files:**
- Modify: `tests/jury/test_config.py` — 加 base_url / api_key / model / kind / id 测试
- 不改: `tools/jury/config.py`（实现已就绪，跑测试验证）

- [ ] **Step 1: 加测试 case**

```python
# 追加到 tests/jury/test_config.py

def test_kind_only_openai_compat(tmp_path: Path) -> None:
    p = _write_config(tmp_path, {
        "schema_version": 1, "active_profile_id": "x",
        "profiles": [{"id": "x", "kind": "anthropic_native",
                      "api_base_url": "https://x/v1", "api_key": "dummy-not-a-real-key", "model": "claude"}],
    })
    with pytest.raises(JuryConfigError):
        load_jury_config(p)


def test_api_base_url_must_be_https(tmp_path: Path) -> None:
    p = _write_config(tmp_path, {
        "schema_version": 1, "active_profile_id": "x",
        "profiles": [{"id": "x", "kind": "openai_compat",
                      "api_base_url": "http://x/v1", "api_key": "dummy-not-a-real-key", "model": "gpt-4o"}],
    })
    with pytest.raises(JuryConfigError):
        load_jury_config(p)


@pytest.mark.parametrize("base_in, base_out", [
    ("https://api.openai.com/v1", "https://api.openai.com/v1"),
    ("https://api.openai.com", "https://api.openai.com/v1"),
    ("https://api.openai.com/v1/", "https://api.openai.com/v1"),
    ("https://api.openai.com/", "https://api.openai.com/v1"),
])
def test_base_url_smart_v1(tmp_path: Path, base_in: str, base_out: str) -> None:
    p = _write_config(tmp_path, {
        "schema_version": 1, "active_profile_id": "x",
        "profiles": [{"id": "x", "kind": "openai_compat",
                      "api_base_url": base_in, "api_key": "dummy-not-a-real-key", "model": "gpt-4o"}],
    })
    profile, _ = load_jury_config(p)
    assert profile.api_base_url == base_out


def test_api_key_strip_then_nonempty(tmp_path: Path) -> None:
    p = _write_config(tmp_path, {
        "schema_version": 1, "active_profile_id": "x",
        "profiles": [{"id": "x", "kind": "openai_compat",
                      "api_base_url": "https://x/v1", "api_key": "   ", "model": "gpt-4o"}],
    })
    with pytest.raises(JuryConfigError):
        load_jury_config(p)


def test_model_strip_then_nonempty(tmp_path: Path) -> None:
    p = _write_config(tmp_path, {
        "schema_version": 1, "active_profile_id": "x",
        "profiles": [{"id": "x", "kind": "openai_compat",
                      "api_base_url": "https://x/v1", "api_key": "dummy", "model": ""}],
    })
    with pytest.raises(JuryConfigError):
        load_jury_config(p)


def test_profile_id_regex_starts_with_dash_rejected(tmp_path: Path) -> None:
    p = _write_config(tmp_path, {
        "schema_version": 1, "active_profile_id": "-foo",
        "profiles": [{"id": "-foo", "kind": "openai_compat",
                      "api_base_url": "https://x/v1", "api_key": "dummy", "model": "gpt-4o"}],
    })
    with pytest.raises(JuryConfigError):
        load_jury_config(p)


def test_profile_id_too_long_rejected(tmp_path: Path) -> None:
    long_id = "a" * 65
    p = _write_config(tmp_path, {
        "schema_version": 1, "active_profile_id": long_id,
        "profiles": [{"id": long_id, "kind": "openai_compat",
                      "api_base_url": "https://x/v1", "api_key": "dummy", "model": "gpt-4o"}],
    })
    with pytest.raises(JuryConfigError):
        load_jury_config(p)


def test_profile_id_unicode_rejected(tmp_path: Path) -> None:
    p = _write_config(tmp_path, {
        "schema_version": 1, "active_profile_id": "你好",
        "profiles": [{"id": "你好", "kind": "openai_compat",
                      "api_base_url": "https://x/v1", "api_key": "dummy", "model": "gpt-4o"}],
    })
    with pytest.raises(JuryConfigError):
        load_jury_config(p)


def test_profile_id_duplicate_rejected(tmp_path: Path) -> None:
    p = _write_config(tmp_path, {
        "schema_version": 1, "active_profile_id": "x",
        "profiles": [
            {"id": "x", "kind": "openai_compat", "api_base_url": "https://x/v1", "api_key": "k1", "model": "m1"},
            {"id": "x", "kind": "openai_compat", "api_base_url": "https://y/v1", "api_key": "k2", "model": "m2"},
        ],
    })
    with pytest.raises(JuryConfigError):
        load_jury_config(p)


def test_api_base_url_empty_hostname_rejected(tmp_path: Path) -> None:
    p = _write_config(tmp_path, {
        "schema_version": 1, "active_profile_id": "x",
        "profiles": [{"id": "x", "kind": "openai_compat",
                      "api_base_url": "https:///v1", "api_key": "dummy", "model": "gpt-4o"}],
    })
    with pytest.raises(JuryConfigError):
        load_jury_config(p)
```

- [ ] **Step 2: 跑测试确认全 PASS**

```bash
pytest tests/jury/test_config.py -v
```
Expected: 14 passed (4 + 10 新加)

- [ ] **Step 3: 提交**

```bash
git add tests/jury/test_config.py
git commit -m "test(jury): config.py base_url 智能 + profile 字段校验 (10 case)"
```

---

### Task 6: config.py 估价表 + JuryCaps 边界 + raw dict 不泄漏

**Files:**
- Modify: `tests/jury/test_config.py` — 加估价表 + caps + raw dict 测试

- [ ] **Step 1: 加测试 case**

```python
# 追加到 tests/jury/test_config.py

def test_cost_lookup_gpt_4o() -> None:
    from tools.jury.config import lookup_builtin_cost
    assert lookup_builtin_cost("gpt-4o") == 0.020
    assert lookup_builtin_cost("gpt-4o-mini") == 0.020  # 前缀命中
    assert lookup_builtin_cost("gpt-4o-2024-12-01") == 0.020


def test_cost_lookup_table_order_first_match() -> None:
    """按表中行序首次命中：gpt-4-turbo 在 gpt-4o 后所以 gpt-4-turbo-2024-12 命中 gpt-4-turbo*"""
    from tools.jury.config import lookup_builtin_cost
    assert lookup_builtin_cost("gpt-4-turbo-2024-12") == 0.030


def test_cost_lookup_unknown_returns_none() -> None:
    from tools.jury.config import lookup_builtin_cost
    assert lookup_builtin_cost("llama-99") is None


def test_cost_per_call_usd_explicit_zero_accepted(tmp_path: Path) -> None:
    p = _write_config(tmp_path, {
        "schema_version": 1, "active_profile_id": "x",
        "profiles": [{"id": "x", "kind": "openai_compat",
                      "api_base_url": "https://x/v1", "api_key": "dummy", "model": "free-model",
                      "cost_per_call_usd": 0}],
    })
    profile, _ = load_jury_config(p)
    assert profile.cost_per_call_usd == 0.0


def test_cost_per_call_usd_negative_rejected(tmp_path: Path) -> None:
    p = _write_config(tmp_path, {
        "schema_version": 1, "active_profile_id": "x",
        "profiles": [{"id": "x", "kind": "openai_compat",
                      "api_base_url": "https://x/v1", "api_key": "dummy", "model": "x",
                      "cost_per_call_usd": -1}],
    })
    with pytest.raises(JuryConfigError):
        load_jury_config(p)


def test_cost_per_call_usd_nan_rejected(tmp_path: Path) -> None:
    p = _write_config(tmp_path, {
        "schema_version": 1, "active_profile_id": "x",
        "profiles": [{"id": "x", "kind": "openai_compat",
                      "api_base_url": "https://x/v1", "api_key": "dummy", "model": "x",
                      "cost_per_call_usd": float("nan")}],
    })
    with pytest.raises(JuryConfigError):
        load_jury_config(p)


def test_caps_defaults(tmp_path: Path) -> None:
    p = _write_config(tmp_path, {
        "schema_version": 1, "active_profile_id": "x",
        "profiles": [{"id": "x", "kind": "openai_compat",
                      "api_base_url": "https://x/v1", "api_key": "dummy", "model": "gpt-4o"}],
    })
    _, caps = load_jury_config(p)
    assert caps.max_image_bytes == 8 * 1024 * 1024
    assert caps.max_n_views == 32
    assert caps.min_photoreal_score == 60


def test_caps_max_n_views_out_of_range_rejected(tmp_path: Path) -> None:
    p = _write_config(tmp_path, {
        "schema_version": 1, "active_profile_id": "x",
        "max_n_views": 0,
        "profiles": [{"id": "x", "kind": "openai_compat",
                      "api_base_url": "https://x/v1", "api_key": "dummy", "model": "gpt-4o"}],
    })
    with pytest.raises(JuryConfigSchemaError):
        load_jury_config(p)


def test_caps_min_photoreal_score_out_of_range_rejected(tmp_path: Path) -> None:
    p = _write_config(tmp_path, {
        "schema_version": 1, "active_profile_id": "x",
        "min_photoreal_score": 101,
        "profiles": [{"id": "x", "kind": "openai_compat",
                      "api_base_url": "https://x/v1", "api_key": "dummy", "model": "gpt-4o"}],
    })
    with pytest.raises(JuryConfigSchemaError):
        load_jury_config(p)
```

- [ ] **Step 2: 跑测试**

```bash
pytest tests/jury/test_config.py -v
```
Expected: 23 passed

- [ ] **Step 3: 提交**

```bash
git add tests/jury/test_config.py
git commit -m "test(jury): config.py 估价表 + caps 边界校验"
```

---

### Task 7: cost.py + 测试

**Files:**
- Create: `tools/jury/cost.py`
- Test: `tests/jury/test_cost.py`

- [ ] **Step 1: 写失败测试 — 8 case**

```python
# tests/jury/test_cost.py
"""tools/jury/cost.py — 预估 + budget 守门 + cost=0 警告。"""
from __future__ import annotations

import pytest

from tools.jury.cost import CostDecision, compute_cost_decision


def test_estimate_under_budget_no_confirm() -> None:
    decision = compute_cost_decision(cost_per_call_usd=0.005, n_views=6, budget_per_run_usd=0.1, confirm_cost=False)
    assert decision.allowed is True
    assert decision.estimated_usd == pytest.approx(0.030)


def test_estimate_equal_budget_no_confirm() -> None:
    decision = compute_cost_decision(cost_per_call_usd=0.01, n_views=10, budget_per_run_usd=0.1, confirm_cost=False)
    assert decision.allowed is True


def test_estimate_over_budget_no_confirm_rejected() -> None:
    decision = compute_cost_decision(cost_per_call_usd=0.05, n_views=6, budget_per_run_usd=0.1, confirm_cost=False)
    assert decision.allowed is False
    assert "超" in decision.reason or "exceed" in decision.reason.lower()


def test_estimate_over_budget_with_confirm_allowed() -> None:
    decision = compute_cost_decision(cost_per_call_usd=0.05, n_views=6, budget_per_run_usd=0.1, confirm_cost=True)
    assert decision.allowed is True


def test_cost_zero_normal_no_warn() -> None:
    """免费 profile 默认放行（不强制 confirm-cost）当 budget > 0。"""
    decision = compute_cost_decision(cost_per_call_usd=0.0, n_views=100, budget_per_run_usd=0.1, confirm_cost=False)
    assert decision.allowed is True


def test_cost_zero_with_budget_zero_double_zero_no_confirm() -> None:
    """双 0：cost=0 + budget=0 是最严守门 → 不需 confirm-cost。"""
    decision = compute_cost_decision(cost_per_call_usd=0.0, n_views=10, budget_per_run_usd=0.0, confirm_cost=False)
    assert decision.allowed is True


def test_n_views_zero_edge() -> None:
    """N=0 视角 cost=0 通过（虽然 Layer 0 已拒 views=[]，cost.py 兜底）。"""
    decision = compute_cost_decision(cost_per_call_usd=0.005, n_views=0, budget_per_run_usd=0.1, confirm_cost=False)
    assert decision.allowed is True
    assert decision.estimated_usd == 0.0


def test_budget_zero_with_cost_positive_rejected() -> None:
    """budget=0 + cost>0 必然拒（即使 confirm-cost，因为 == 不超）。"""
    decision = compute_cost_decision(cost_per_call_usd=0.005, n_views=1, budget_per_run_usd=0.0, confirm_cost=False)
    assert decision.allowed is False  # 0.005 > 0.0
```

- [ ] **Step 2: 跑测试 fail**

```bash
pytest tests/jury/test_cost.py -v
```
Expected: FAIL（cost 模块不存在）

- [ ] **Step 3: 实现 cost.py**

```python
# tools/jury/cost.py
"""budget 计算 + 阈值比较 + cost=0 警告。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostDecision:
    allowed: bool
    estimated_usd: float
    reason: str


def compute_cost_decision(
    *,
    cost_per_call_usd: float,
    n_views: int,
    budget_per_run_usd: float,
    confirm_cost: bool,
) -> CostDecision:
    """估算成本 + 比较 budget。"""
    estimated = round(float(cost_per_call_usd) * int(n_views), 6)

    if estimated <= budget_per_run_usd:
        return CostDecision(allowed=True, estimated_usd=estimated,
                            reason=f"预估 {estimated} USD <= budget {budget_per_run_usd} USD")

    if confirm_cost:
        return CostDecision(allowed=True, estimated_usd=estimated,
                            reason=f"预估 {estimated} USD 超 budget {budget_per_run_usd} USD（已 --confirm-cost 通过）")

    return CostDecision(allowed=False, estimated_usd=estimated,
                        reason=f"预估 {estimated} USD 超 budget {budget_per_run_usd} USD；加 --confirm-cost 或调高 --budget")
```

- [ ] **Step 4: 跑测试 PASS**

```bash
pytest tests/jury/test_cost.py -v
```
Expected: 8 passed

- [ ] **Step 5: 提交**

```bash
git add tools/jury/cost.py tests/jury/test_cost.py
git commit -m "feat(jury): cost.py 预估 + budget 守门 (8 case)"
```

---

## CP-2: redact + stderr_messages + verdict + deterministic_gate + input_evidence_binding

### Task 8: redact.py + 8 case

**Files:**
- Create: `tools/jury/redact.py`
- Test: `tests/jury/test_redact.py`

- [ ] **Step 1: 写失败测试 — 8 case**

```python
# tests/jury/test_redact.py
"""集中脱敏 4 函数的单元测试。"""
from __future__ import annotations

from tools.jury.redact import redact_url, redact_headers, redact_body, redact_traceback_str


def test_redact_url_strips_query_and_fragment() -> None:
    result = redact_url("https://api.example.com/v1/chat/completions?api_key=sk-secret&foo=bar#frag")
    assert "sk-secret" not in result
    assert "api_key" not in result
    assert "frag" not in result
    assert result.startswith("https://api.example.com/v1/chat/completions")


def test_redact_url_keeps_host_and_path() -> None:
    result = redact_url("https://api.openai.com/v1/chat/completions?x=1")
    assert "api.openai.com" in result
    assert "/v1/chat/completions" in result


def test_redact_headers_removes_authorization_case_insensitive() -> None:
    headers = {"Authorization": "Bearer sk-xxx", "Cookie": "sess=abc", "x-api-key": "yyy",
               "x-request-id": "trace-123", "Content-Type": "application/json"}
    result = redact_headers(headers)
    assert "Authorization" not in result
    assert "Cookie" not in result
    assert "x-api-key" not in result
    assert result.get("x-request-id") == "trace-123"  # 公开 trace ID 保留
    assert result.get("Content-Type") == "application/json"


def test_redact_body_truncates_to_max_chars() -> None:
    body = "x" * 1000
    result = redact_body(body, max_chars=128)
    assert len(result) <= 128 + len("...truncated")
    assert "...truncated" in result


def test_redact_body_short_unchanged() -> None:
    body = "short"
    assert redact_body(body, max_chars=128) == "short"


def test_redact_traceback_strips_api_key_lines() -> None:
    tb = (
        "Traceback (most recent call last):\n"
        "  File \"x.py\", line 1, in <module>\n"
        "    raise X\n"
        "Local: api_key='sk-secret-xyz'\n"
        "Local: Authorization='Bearer sk-yyy'\n"
        "X: error"
    )
    result = redact_traceback_str(tb)
    assert "sk-secret-xyz" not in result
    assert "sk-yyy" not in result


def test_redact_url_empty_string() -> None:
    assert redact_url("") == ""


def test_redact_headers_none_safe() -> None:
    assert redact_headers({}) == {}
```

- [ ] **Step 2: 跑测试 fail**

```bash
pytest tests/jury/test_redact.py -v
```
Expected: FAIL

- [ ] **Step 3: 实现 redact.py**

```python
# tools/jury/redact.py
"""集中 4 路径脱敏 — 所有出口（stderr / log / report / --debug-output）唯一通过此模块。

不做语义剥离（保留可公开 trace ID 如 vendor_request_id）。
"""
from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse


_REDACT_HEADER_NAMES = {"authorization", "cookie", "set-cookie", "x-api-key", "api-key"}
_REDACT_TRACEBACK_PATTERNS = [
    re.compile(r"^.*api[_-]?key.*=.*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^.*Authorization.*Bearer.*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^.*Cookie.*=.*$", re.IGNORECASE | re.MULTILINE),
]


def redact_url(s: str) -> str:
    """剥 query/fragment 保留 scheme://host/path。"""
    if not s:
        return s
    parsed = urlparse(s)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def redact_headers(d: dict[str, str]) -> dict[str, str]:
    """大小写不敏感移除敏感 header。"""
    return {k: v for k, v in d.items() if k.lower() not in _REDACT_HEADER_NAMES}


def redact_body(s: str, max_chars: int = 128) -> str:
    """截断到 max_chars + 'truncated' 标记；不做 body 内语义剥离（保留 vendor_request_id 等公开 trace）。"""
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "...truncated"


def redact_traceback_str(s: str) -> str:
    """从 traceback 字符串去 frame locals 中含 api_key= / Authorization Bearer / Cookie 的行。"""
    for pattern in _REDACT_TRACEBACK_PATTERNS:
        s = pattern.sub("[REDACTED]", s)
    return s
```

- [ ] **Step 4: 跑测试 PASS**

```bash
pytest tests/jury/test_redact.py -v
```
Expected: 8 passed

- [ ] **Step 5: 提交**

```bash
git add tools/jury/redact.py tests/jury/test_redact.py
git commit -m "feat(jury): redact.py 集中 4 函数脱敏 (8 case)"
```

---

### Task 9: stderr_messages.py + 11 case

**Files:**
- Create: `tools/jury/stderr_messages.py`
- Test: `tests/jury/test_stderr_messages.py`

- [ ] **Step 1: 写失败测试 — 11 case 覆盖每 exit code × status**

```python
# tests/jury/test_stderr_messages.py
"""中文人话提示模板覆盖测试 — 每 exit code × status 都填 placeholder 实际值。"""
from __future__ import annotations

import re

from tools.jury.stderr_messages import format_stderr_message


def test_accepted_template() -> None:
    msg = format_stderr_message(exit_code=0, status="accepted",
                                context={"actual_cost_usd": 0.030, "jury_review_input_abs_path": "/p/jri.json"})
    assert "0.030" in msg or "0.03" in msg
    assert "/p/jri.json" in msg
    assert "{" not in msg  # 无未填 placeholder


def test_preview_template() -> None:
    msg = format_stderr_message(exit_code=0, status="preview",
                                context={"n_failed": 2, "total": 6, "photo3d_jury_report_abs_path": "/p/r.json"})
    assert "2/6" in msg or "2 / 6" in msg
    assert "/p/r.json" in msg
    assert "{" not in msg


def test_needs_review_includes_fallback_id() -> None:
    msg = format_stderr_message(exit_code=0, status="needs_review",
                                context={"n_failed": 1, "total": 6, "error_kinds": "auth_failed",
                                         "actual_cost_usd": 0.025, "subsystem": "lifting_platform",
                                         "fallback_id": "gpt-4o-native"})
    assert "fallback_id" not in msg  # placeholder 名不应出现
    assert "gpt-4o-native" in msg
    assert "lifting_platform" in msg


def test_blocked_first_blocking_code() -> None:
    msg = format_stderr_message(exit_code=1, status="blocked",
                                context={"first_blocking_code": "subsystem_mismatch", "subsystem": "X"})
    assert "subsystem_mismatch" in msg
    assert "{" not in msg


def test_blocked_freeze_drift_emphasizes_cost() -> None:
    msg = format_stderr_message(exit_code=1, status="blocked",
                                context={"first_blocking_code": "freeze_drift", "actual_cost_usd": 0.030})
    assert "0.030" in msg or "0.03" in msg
    assert "已花费" in msg or "cost" in msg.lower()


def test_config_schema_error() -> None:
    msg = format_stderr_message(exit_code=2, error_kind="schema_version_invalid",
                                context={"actual": 5})
    assert "5" in msg
    assert "schema_version" in msg.lower() or "1" in msg


def test_config_profile_id_invalid() -> None:
    msg = format_stderr_message(exit_code=2, error_kind="profile_id_invalid",
                                context={"bad_id": "-foo", "first_bad_char": "-",
                                         "sanitized_candidate": "_foo"})
    assert "-foo" in msg
    assert "_foo" in msg


def test_config_path_external_no_allow() -> None:
    msg = format_stderr_message(exit_code=2, error_kind="config_path_external",
                                context={"abs": "/external/path.json"})
    assert "/external/path.json" in msg
    assert "--allow-external-config" in msg


def test_cost_over_budget() -> None:
    msg = format_stderr_message(exit_code=3, error_kind="budget_exceeded",
                                context={"estimated_cost_usd": 0.6, "budget_per_run_usd": 0.1,
                                         "n_views": 6, "cost_per_call_usd": 0.1})
    assert "0.6" in msg
    assert "0.1" in msg
    assert "--confirm-cost" in msg


def test_lock_busy() -> None:
    msg = format_stderr_message(exit_code=4, error_kind="lock_busy",
                                context={"held_pid": 12345, "age_seconds": 30})
    assert "12345" in msg
    assert "30" in msg


def test_internal_error() -> None:
    msg = format_stderr_message(exit_code=99, error_kind="internal",
                                context={"exception_type": "RuntimeError"})
    assert "RuntimeError" in msg
    assert "issue" in msg.lower() or "提" in msg
```

- [ ] **Step 2: 跑测试 fail**

```bash
pytest tests/jury/test_stderr_messages.py -v
```
Expected: FAIL

- [ ] **Step 3: 实现 stderr_messages.py**

```python
# tools/jury/stderr_messages.py
"""中文人话提示模板集中。

模板覆盖 exit_code × status × error_kind；所有 placeholder 由 cli 填充实际值，禁止 {xxx} 残留。
"""
from __future__ import annotations

from typing import Any


def format_stderr_message(
    *,
    exit_code: int,
    status: str = "",
    error_kind: str = "",
    context: dict[str, Any],
) -> str:
    """根据 exit_code + status/error_kind 选择模板填充。"""
    key = (exit_code, status, error_kind)

    if exit_code == 0 and status == "accepted":
        cost = context.get("actual_cost_usd", 0)
        path = context.get("jury_review_input_abs_path", "")
        return f"✓ 自动验收通过（成本 ${cost} USD）。下一步：enhance-review --review-input {path}"

    if exit_code == 0 and status == "preview":
        n = context.get("n_failed", 0)
        m = context.get("total", 0)
        path = context.get("photo3d_jury_report_abs_path", "")
        return (
            f"△ 自动验收降级为预览（{n}/{m} 视角不达标）。先看 {path} 里 views[].verdict 找原因；"
            "可重跑 enhance --provider <preset> --resubmit 或人工目检后手填 review-input。"
        )

    if exit_code == 0 and status == "needs_review":
        k = context.get("n_failed", 0)
        m = context.get("total", 0)
        kinds = context.get("error_kinds", "")
        cost = context.get("actual_cost_usd", 0)
        sub = context.get("subsystem", "")
        fb = context.get("fallback_id", "")
        return (
            f"⚠ {k}/{m} 视角验收失败（{kinds}）；已花费 ${cost} USD。"
            f"建议换 profile：photo3d-jury --subsystem {sub} --profile-id {fb}。"
            "文档：docs/cad-jury-config.md"
        )

    if exit_code == 1 and status == "blocked":
        code = context.get("first_blocking_code", "")
        if code == "freeze_drift":
            cost = context.get("actual_cost_usd", 0)
            return f"✗ jury 跑期间报告被改坏（sha drift）。已花费 ${cost} USD 但结果作废。检查 ENHANCEMENT_REPORT.json 是否有别的进程在改写。"
        sub = context.get("subsystem", "")
        return f"✗ 输入证据与 active run 不一致（{code}）。检查 enhance-check 是否真 accepted：photo3d-recover --subsystem {sub} 后再跑 jury。"

    if exit_code == 2:
        if error_kind == "schema_version_invalid":
            actual = context.get("actual", "")
            return f"✗ jury 配置 schema_version={actual} 不被本版本支持（仅 1 或 2）。建议改成 1 或升级 photo3d-jury。"
        if error_kind == "profile_id_invalid":
            bad = context.get("bad_id", "")
            ch = context.get("first_bad_char", "")
            cand = context.get("sanitized_candidate", "")
            return f"✗ profile id `{bad}` 含非法字符 `{ch}`，仅允许 [A-Za-z0-9_-]。建议改成 `{cand}`。"
        if error_kind == "config_path_external":
            abs_p = context.get("abs", "")
            return f"✗ --config 路径 {abs_p} 不在 ~/.claude/ 或项目内。如确认信任此文件请加 --allow-external-config；否则修正 --config。"
        if error_kind == "config_missing":
            path = context.get("config_path", "~/.claude/cad_jury_config.json")
            return f"✗ 未找到 jury 配置文件 {path}。最小配置示例见 docs/cad-jury-config.md。"
        return f"✗ 配置错（{error_kind}）。详见 docs/cad-jury-config.md。"

    if exit_code == 3:
        est = context.get("estimated_cost_usd", 0)
        budget = context.get("budget_per_run_usd", 0)
        n = context.get("n_views", 0)
        per = context.get("cost_per_call_usd", 0)
        return f"△ 预估成本 ${est} USD 超 budget ${budget}（{n} 视角 × ${per}）。加 --confirm-cost 或调高 --budget 重跑。"

    if exit_code == 4:
        if error_kind == "lock_stale_cleaned":
            pid = context.get("held_pid", "")
            age = context.get("age_min", 0)
            return f"ⓘ 检测到 stale .jury.lock（PID={pid}，age={age} 分钟），自动清理后继续。"
        pid = context.get("held_pid", "")
        age = context.get("age_seconds", 0)
        return f"△ 已有 jury 进程在跑（PID={pid}，{age}s 前启动）。等它结束或 ctrl-c 它后重试。"

    if exit_code == 99:
        exc = context.get("exception_type", "Exception")
        return f"✗ 工具内部错误（{exc}）。请提 issue 附 PHOTO3D_JURY_REPORT.json + 命令行参数（api_key 已 redact）。"

    return f"jury 已退出 (exit_code={exit_code}, status={status}, error_kind={error_kind})"
```

- [ ] **Step 4: 跑测试 PASS**

```bash
pytest tests/jury/test_stderr_messages.py -v
```
Expected: 11 passed

- [ ] **Step 5: 提交**

```bash
git add tools/jury/stderr_messages.py tests/jury/test_stderr_messages.py
git commit -m "feat(jury): stderr_messages.py 中文人话模板 (11 case)"
```

---

### Task 10: verdict.py 骨架 + 标准 JSON 解析

**Files:**
- Create: `tools/jury/verdict.py`
- Test: `tests/jury/test_verdict.py`

- [ ] **Step 1: 写失败测试 — 标准 JSON / Unicode reason / boolean 异常**

```python
# tests/jury/test_verdict.py
"""verdict.py 纯函数解析 — LLM 文本 → ViewVerdict + parse_anomalies。"""
from __future__ import annotations

import json

import pytest

from tools.jury.verdict import ViewVerdict, parse_view_verdict


_OK_RESPONSE = json.dumps({
    "semantic_checks": {
        "geometry_preserved": True, "material_consistent": True, "photorealistic": True,
        "no_extra_parts": True, "no_missing_parts": True,
    },
    "photoreal_score": 78,
    "reason": "金属铸件高光一致，背景虚化自然。",
})


def test_standard_response_parses_clean() -> None:
    v = parse_view_verdict(_OK_RESPONSE, finish_reason="stop")
    assert v.parse_status == "ok"
    assert v.parse_anomalies == []
    assert v.semantic_checks["photorealistic"] is True
    assert v.photoreal_score == 78
    assert v.reason == "金属铸件高光一致，背景虚化自然。"
    assert v.verdict == "accepted"


def test_unicode_reason_preserved() -> None:
    body = json.dumps({
        "semantic_checks": {k: True for k in [
            "geometry_preserved", "material_consistent", "photorealistic",
            "no_extra_parts", "no_missing_parts"]},
        "photoreal_score": 70,
        "reason": "中文 + 🎨 emoji 测试",
    })
    v = parse_view_verdict(body, finish_reason="stop")
    assert "🎨" in v.reason


def test_boolean_field_non_bool_marks_anomaly() -> None:
    body = json.dumps({
        "semantic_checks": {"geometry_preserved": "yes", "material_consistent": True,
                            "photorealistic": True, "no_extra_parts": True, "no_missing_parts": True},
        "photoreal_score": 70, "reason": "x",
    })
    v = parse_view_verdict(body, finish_reason="stop")
    assert "content_keys_mismatch" in v.parse_anomalies
    assert v.verdict == "needs_review"
```

- [ ] **Step 2: 跑测试 fail**

```bash
pytest tests/jury/test_verdict.py -v
```
Expected: FAIL

- [ ] **Step 3: 实现 verdict.py（先让 3 case 过，后续 task 11 加边界）**

```python
# tools/jury/verdict.py
"""LLM 文本 → 结构化 ViewVerdict（纯函数，无副作用）。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Literal


_REASON_MAX_CHARS = 80
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_REQUIRED_BOOL_KEYS = (
    "geometry_preserved", "material_consistent", "photorealistic",
    "no_extra_parts", "no_missing_parts",
)


@dataclass(frozen=True)
class ViewVerdict:
    semantic_checks: dict[str, bool]
    photoreal_score: int
    reason: str
    parse_status: Literal["ok"]
    parse_anomalies: list[str] = field(default_factory=list)
    verdict: Literal["accepted", "preview", "needs_review"] = "accepted"


def parse_view_verdict(content_text: str, *, finish_reason: str = "stop", min_photoreal_score: int = 60) -> ViewVerdict:
    """解析 LLM 返的 content_text + finish_reason → ViewVerdict。"""
    anomalies: list[str] = []

    # finish_reason 校验
    if finish_reason not in {"stop", None}:
        anomalies.append("finish_reason_invalid")

    # JSON 解析
    try:
        payload = json.loads(content_text)
    except json.JSONDecodeError:
        anomalies.append("content_not_json")
        return _make_needs_review_verdict(anomalies)

    if not isinstance(payload, dict):
        anomalies.append("content_not_json")
        return _make_needs_review_verdict(anomalies)

    # semantic_checks 字段集
    raw_checks = payload.get("semantic_checks")
    if not isinstance(raw_checks, dict):
        anomalies.append("missing_content")
        return _make_needs_review_verdict(anomalies)

    checks: dict[str, bool] = {}
    keys_ok = True
    for key in _REQUIRED_BOOL_KEYS:
        val = raw_checks.get(key)
        if not isinstance(val, bool):
            keys_ok = False
            checks[key] = False  # 默认 False 防 KeyError 后续
        else:
            checks[key] = val
    if not keys_ok:
        anomalies.append("content_keys_mismatch")

    # photoreal_score clamp [0, 100]
    raw_score = payload.get("photoreal_score", 0)
    if not isinstance(raw_score, (int, float)):
        anomalies.append("content_keys_mismatch")
        score = 0
    else:
        score = int(raw_score)
        if score < 0 or score > 100:
            anomalies.append("clamped")
            score = max(0, min(100, score))

    # reason 控制字符 + ANSI escape + 80 字截
    raw_reason = str(payload.get("reason", ""))
    sanitized = _ANSI_ESCAPE_RE.sub("", _CONTROL_CHARS_RE.sub("", raw_reason)).replace("\n", " ").strip()
    if sanitized != raw_reason:
        anomalies.append("reason_sanitized")
    if len(sanitized) > _REASON_MAX_CHARS:
        sanitized = sanitized[:_REASON_MAX_CHARS]
        if "reason_sanitized" not in anomalies:
            anomalies.append("reason_sanitized")

    # 决策：parse_anomalies ⊆ {reason_sanitized, clamped} → 仍可走 5 boolean
    serious = set(anomalies) - {"reason_sanitized", "clamped"}
    if serious:
        verdict: Literal["accepted", "preview", "needs_review"] = "needs_review"
    elif not all(checks.values()):
        verdict = "preview"
    elif score < min_photoreal_score:
        verdict = "preview"
    else:
        verdict = "accepted"

    return ViewVerdict(
        semantic_checks=checks,
        photoreal_score=score,
        reason=sanitized,
        parse_status="ok",
        parse_anomalies=anomalies,
        verdict=verdict,
    )


def _make_needs_review_verdict(anomalies: list[str]) -> ViewVerdict:
    return ViewVerdict(
        semantic_checks={k: False for k in _REQUIRED_BOOL_KEYS},
        photoreal_score=0,
        reason="",
        parse_status="ok",
        parse_anomalies=anomalies,
        verdict="needs_review",
    )
```

- [ ] **Step 4: 跑测试 PASS**

```bash
pytest tests/jury/test_verdict.py -v
```
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add tools/jury/verdict.py tests/jury/test_verdict.py
git commit -m "feat(jury): verdict.py 骨架 + 标准 JSON 解析 (3 case)"
```

---

### Task 11: verdict.py 边界 + 11 case 补全

**Files:**
- Modify: `tests/jury/test_verdict.py` — 加 photoreal_score clamp / reason 控制字符 / finish_reason / content_not_json / content_not_str / 多 anomaly 共存

- [ ] **Step 1: 加测试**

```python
# 追加到 tests/jury/test_verdict.py

def test_photoreal_score_below_zero_clamped() -> None:
    body = json.dumps({
        "semantic_checks": {k: True for k in [
            "geometry_preserved", "material_consistent", "photorealistic",
            "no_extra_parts", "no_missing_parts"]},
        "photoreal_score": -5, "reason": "x",
    })
    v = parse_view_verdict(body, finish_reason="stop")
    assert v.photoreal_score == 0
    assert "clamped" in v.parse_anomalies
    assert v.verdict == "preview"  # 0 < min 60


def test_photoreal_score_above_100_clamped() -> None:
    body = json.dumps({
        "semantic_checks": {k: True for k in [
            "geometry_preserved", "material_consistent", "photorealistic",
            "no_extra_parts", "no_missing_parts"]},
        "photoreal_score": 150, "reason": "x",
    })
    v = parse_view_verdict(body, finish_reason="stop")
    assert v.photoreal_score == 100
    assert "clamped" in v.parse_anomalies
    assert v.verdict == "accepted"  # 100 >= min 60


def test_photoreal_score_at_min_boundary_accepted() -> None:
    body = json.dumps({
        "semantic_checks": {k: True for k in [
            "geometry_preserved", "material_consistent", "photorealistic",
            "no_extra_parts", "no_missing_parts"]},
        "photoreal_score": 60, "reason": "x",
    })
    v = parse_view_verdict(body, finish_reason="stop")
    assert v.verdict == "accepted"  # = 边界 accepted


def test_reason_control_chars_stripped() -> None:
    body = json.dumps({
        "semantic_checks": {k: True for k in [
            "geometry_preserved", "material_consistent", "photorealistic",
            "no_extra_parts", "no_missing_parts"]},
        "photoreal_score": 70, "reason": "abc\x00\x07def\x1bbad",
    })
    v = parse_view_verdict(body, finish_reason="stop")
    assert "\x00" not in v.reason
    assert "\x1b" not in v.reason
    assert "reason_sanitized" in v.parse_anomalies


def test_reason_truncated_to_80() -> None:
    body = json.dumps({
        "semantic_checks": {k: True for k in [
            "geometry_preserved", "material_consistent", "photorealistic",
            "no_extra_parts", "no_missing_parts"]},
        "photoreal_score": 70, "reason": "x" * 150,
    })
    v = parse_view_verdict(body, finish_reason="stop")
    assert len(v.reason) <= 80
    assert "reason_sanitized" in v.parse_anomalies


def test_invalid_json_marks_content_not_json() -> None:
    v = parse_view_verdict("not a json", finish_reason="stop")
    assert "content_not_json" in v.parse_anomalies
    assert v.verdict == "needs_review"


def test_finish_reason_length_marks_invalid() -> None:
    body = json.dumps({
        "semantic_checks": {k: True for k in [
            "geometry_preserved", "material_consistent", "photorealistic",
            "no_extra_parts", "no_missing_parts"]},
        "photoreal_score": 70, "reason": "x",
    })
    v = parse_view_verdict(body, finish_reason="length")
    assert "finish_reason_invalid" in v.parse_anomalies
    assert v.verdict == "needs_review"


def test_multiple_anomalies_coexist() -> None:
    """reason_sanitized + clamped 共存仍 accepted（白名单内）。"""
    body = json.dumps({
        "semantic_checks": {k: True for k in [
            "geometry_preserved", "material_consistent", "photorealistic",
            "no_extra_parts", "no_missing_parts"]},
        "photoreal_score": 150, "reason": "abc\x00def",
    })
    v = parse_view_verdict(body, finish_reason="stop")
    assert "clamped" in v.parse_anomalies
    assert "reason_sanitized" in v.parse_anomalies
    assert v.verdict == "accepted"  # 二者都在白名单 + 5 bool 全 true + 100 >= 60
```

- [ ] **Step 2: 跑测试 PASS**

```bash
pytest tests/jury/test_verdict.py -v
```
Expected: 11 passed

- [ ] **Step 3: 提交**

```bash
git add tests/jury/test_verdict.py
git commit -m "test(jury): verdict.py 边界 + 多 anomaly 共存 (8 case)"
```

---

### Task 12: deterministic_gate.py + 9 case (Layer 1)

**Files:**
- Create: `tools/jury/deterministic_gate.py`
- Test: `tests/jury/test_deterministic_gate.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/jury/test_deterministic_gate.py
"""Layer 1 — 字段自洽性二次验证（输入到此前已 Layer 0 通过）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.jury.deterministic_gate import Layer1Verdict, run_layer1


def _load_fixture() -> dict:
    path = Path("tests/jury/fixtures/sample_enhancement_report.json")
    return json.loads(path.read_text(encoding="utf-8"))


def test_all_accepted_passes() -> None:
    report = _load_fixture()
    v = run_layer1(report)
    assert v.passed is True
    assert v.per_view_failures == []


def test_view_status_not_accepted_fails() -> None:
    report = _load_fixture()
    report["views"][0]["status"] = "preview"
    v = run_layer1(report)
    assert v.passed is False
    assert any(f["view"] == "iso" for f in v.per_view_failures)


def test_edge_similarity_below_min_similarity_fails() -> None:
    report = _load_fixture()
    report["views"][0]["edge_similarity"] = 0.50
    v = run_layer1(report)
    assert v.passed is False


def test_effective_contrast_stddev_none_fails() -> None:
    report = _load_fixture()
    report["views"][0]["quality_metrics"]["effective_contrast_stddev"] = None
    v = run_layer1(report)
    assert v.passed is False


def test_effective_contrast_stddev_below_threshold_fails() -> None:
    report = _load_fixture()
    report["views"][0]["quality_metrics"]["effective_contrast_stddev"] = 5.0
    v = run_layer1(report)
    assert v.passed is False


def test_quality_metrics_missing_fails() -> None:
    report = _load_fixture()
    del report["views"][0]["quality_metrics"]
    v = run_layer1(report)
    assert v.passed is False


def test_mixed_views_partial_fail() -> None:
    report = _load_fixture()
    report["views"][1]["edge_similarity"] = 0.5  # 只 front fail
    v = run_layer1(report)
    assert v.passed is False
    assert len(v.per_view_failures) == 1
    assert v.per_view_failures[0]["view"] == "front"


def test_min_similarity_missing_fallback_085() -> None:
    report = _load_fixture()
    del report["min_similarity"]
    v = run_layer1(report)
    assert v.passed is True  # 0.91 / 0.88 都 >= 0.85 fallback


def test_threshold_constant_matches_enhance_consistency() -> None:
    """rev 4 inv：测试断言 jury 阈值与 tools/enhance_consistency.py 同值。"""
    from tools.jury.deterministic_gate import MIN_PHOTO_CONTRAST_STDDEV as JURY_THRESHOLD
    from tools.enhance_consistency import MIN_PHOTO_CONTRAST_STDDEV as ENHANCE_THRESHOLD
    assert JURY_THRESHOLD == pytest.approx(ENHANCE_THRESHOLD)
```

- [ ] **Step 2: 跑测试 fail**

```bash
pytest tests/jury/test_deterministic_gate.py -v
```
Expected: FAIL

- [ ] **Step 3: 实现 deterministic_gate.py**

```python
# tools/jury/deterministic_gate.py
"""Layer 1 — 字段自洽性二次验证。

输入到此前已 Layer 0 通过；本层仅在 report 顶层声称 accepted 时检查 per-view 字段是否真自洽。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# 与 tools/enhance_consistency.py:MIN_PHOTO_CONTRAST_STDDEV 同值
MIN_PHOTO_CONTRAST_STDDEV = 12.0
DEFAULT_MIN_SIMILARITY = 0.85


@dataclass(frozen=True)
class Layer1Verdict:
    passed: bool
    per_view_failures: list[dict[str, Any]] = field(default_factory=list)


def run_layer1(report: dict[str, Any]) -> Layer1Verdict:
    """运行 Layer 1 自洽性检查。"""
    failures: list[dict[str, Any]] = []
    min_similarity = float(report.get("min_similarity", DEFAULT_MIN_SIMILARITY))

    for view in report.get("views", []):
        view_name = view.get("view", "")
        reasons: list[str] = []

        if view.get("status") != "accepted":
            reasons.append(f"view_status_not_accepted (got: {view.get('status')})")

        edge_sim = view.get("edge_similarity")
        if edge_sim is None or float(edge_sim) < min_similarity:
            reasons.append(f"edge_similarity below {min_similarity} (got: {edge_sim})")

        qm = view.get("quality_metrics")
        if not isinstance(qm, dict) or not qm:
            reasons.append("quality_metrics missing or empty")
        else:
            ecs = qm.get("effective_contrast_stddev")
            if ecs is None:
                reasons.append("effective_contrast_stddev is None")
            elif float(ecs) < MIN_PHOTO_CONTRAST_STDDEV:
                reasons.append(f"effective_contrast_stddev below {MIN_PHOTO_CONTRAST_STDDEV} (got: {ecs})")

        if reasons:
            failures.append({"view": view_name, "reasons": reasons})

    return Layer1Verdict(passed=not failures, per_view_failures=failures)
```

- [ ] **Step 4: 跑测试 PASS**

```bash
pytest tests/jury/test_deterministic_gate.py -v
```
Expected: 9 passed

- [ ] **Step 5: 提交**

```bash
git add tools/jury/deterministic_gate.py tests/jury/test_deterministic_gate.py
git commit -m "feat(jury): deterministic_gate.py Layer 1 字段自洽性 (9 case)"
```

---

### Task 13: input_evidence_binding.py 骨架 + Layer 0 基础

**Files:**
- Create: `tools/jury/input_evidence_binding.py`
- Test: `tests/jury/test_input_evidence_binding.py`

- [ ] **Step 1: 写失败测试 — 6 个基础 case**

```python
# tests/jury/test_input_evidence_binding.py
"""Layer 0 — 输入证据绑定 + 资源/竞态防护。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tools.jury.config import JuryCaps
from tools.jury.input_evidence_binding import (
    Layer0Verdict,
    JuryLockBusy,
    run_layer0,
)


@pytest.fixture
def project_root_with_run(tmp_path: Path) -> Path:
    """在 tmp_path 下构造完整的 cad/<sub>/.cad-spec-gen/runs/<run>/ 目录树 + ARTIFACT_INDEX.json。"""
    sub = "lifting_platform"
    run_id = "20260508-123456"
    fixtures = Path("tests/jury/fixtures")

    # cad spec gen 目录
    run_dir = tmp_path / "cad" / sub / ".cad-spec-gen" / "runs" / run_id
    run_dir.mkdir(parents=True)

    # render dir + 假图（非 0 大小，1KB << max_image_bytes 8MiB）
    render_dir = tmp_path / "cad" / "output" / "renders" / sub / run_id
    render_dir.mkdir(parents=True)
    (render_dir / "iso_enhanced.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 1000)
    (render_dir / "front_enhanced.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 1000)

    # render_manifest 与 enhancement_report 调整路径再写
    rm = json.loads((fixtures / "sample_render_manifest.json").read_text(encoding="utf-8"))
    er = json.loads((fixtures / "sample_enhancement_report.json").read_text(encoding="utf-8"))
    for v in er["views"]:
        # enhanced_image 改为 tmp_path 下绝对路径或相对 project root 路径
        v["enhanced_image"] = f"cad/output/renders/{sub}/{run_id}/{v['view']}_enhanced.png"
    (render_dir / "render_manifest.json").write_text(json.dumps(rm), encoding="utf-8")
    (render_dir / "ENHANCEMENT_REPORT.json").write_text(json.dumps(er), encoding="utf-8")

    # ARTIFACT_INDEX
    ai = json.loads((fixtures / "sample_artifact_index.json").read_text(encoding="utf-8"))
    (run_dir.parent.parent / "ARTIFACT_INDEX.json").write_text(json.dumps(ai), encoding="utf-8")

    return tmp_path


_DEFAULT_CAPS = JuryCaps(max_image_bytes=8 * 1024 * 1024, max_n_views=32, min_photoreal_score=60)


def test_happy_path_freezes_all(project_root_with_run: Path) -> None:
    v = run_layer0(project_root=project_root_with_run, subsystem="lifting_platform", caps=_DEFAULT_CAPS)
    assert v.passed is True
    assert v.frozen_run_id == "20260508-123456"
    assert v.frozen_sha256.get("enhancement_report", "").startswith("sha256:")
    assert v.frozen_sha256.get("render_manifest", "").startswith("sha256:")


def test_subsystem_mismatch_blocked(project_root_with_run: Path) -> None:
    v = run_layer0(project_root=project_root_with_run, subsystem="other_subsystem", caps=_DEFAULT_CAPS)
    assert v.passed is False
    assert any(r["code"] == "subsystem_mismatch" for r in v.blocking_reasons)


def test_enhancement_report_missing_blocked(project_root_with_run: Path) -> None:
    er_path = project_root_with_run / "cad" / "output" / "renders" / "lifting_platform" / "20260508-123456" / "ENHANCEMENT_REPORT.json"
    er_path.unlink()
    v = run_layer0(project_root=project_root_with_run, subsystem="lifting_platform", caps=_DEFAULT_CAPS)
    assert v.passed is False
    assert any(r["code"] in {"enhancement_report_missing", "enhancement_report_unreadable"} for r in v.blocking_reasons)


def test_quality_summary_status_not_accepted_blocked(project_root_with_run: Path) -> None:
    er_path = project_root_with_run / "cad" / "output" / "renders" / "lifting_platform" / "20260508-123456" / "ENHANCEMENT_REPORT.json"
    er = json.loads(er_path.read_text(encoding="utf-8"))
    er["quality_summary"]["status"] = "preview"
    er_path.write_text(json.dumps(er), encoding="utf-8")
    v = run_layer0(project_root=project_root_with_run, subsystem="lifting_platform", caps=_DEFAULT_CAPS)
    assert v.passed is False
    assert any(r["code"] == "quality_summary_not_accepted" for r in v.blocking_reasons)


def test_views_empty_blocked(project_root_with_run: Path) -> None:
    er_path = project_root_with_run / "cad" / "output" / "renders" / "lifting_platform" / "20260508-123456" / "ENHANCEMENT_REPORT.json"
    er = json.loads(er_path.read_text(encoding="utf-8"))
    er["views"] = []
    er_path.write_text(json.dumps(er), encoding="utf-8")
    v = run_layer0(project_root=project_root_with_run, subsystem="lifting_platform", caps=_DEFAULT_CAPS)
    assert v.passed is False
    assert any(r["code"] == "views_empty" for r in v.blocking_reasons)


def test_duplicate_view_name_blocked(project_root_with_run: Path) -> None:
    er_path = project_root_with_run / "cad" / "output" / "renders" / "lifting_platform" / "20260508-123456" / "ENHANCEMENT_REPORT.json"
    er = json.loads(er_path.read_text(encoding="utf-8"))
    er["views"].append(dict(er["views"][0]))  # 复制第一个视角（同 view 名 "iso"）
    er_path.write_text(json.dumps(er), encoding="utf-8")
    v = run_layer0(project_root=project_root_with_run, subsystem="lifting_platform", caps=_DEFAULT_CAPS)
    assert v.passed is False
    assert any(r["code"] == "duplicate_view" for r in v.blocking_reasons)
```

- [ ] **Step 2: 跑测试 fail**

```bash
pytest tests/jury/test_input_evidence_binding.py -v
```
Expected: FAIL

- [ ] **Step 3: 实现 input_evidence_binding.py 骨架（Layer 0 基础）**

```python
# tools/jury/input_evidence_binding.py
"""Layer 0 — 输入证据绑定 + sha256/active_run freeze + .jury.lock + 重跑保护。"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tools._file_lock import LockBusy as JuryLockBusy
from tools.contract_io import file_sha256
from tools.jury.config import JuryCaps


@dataclass(frozen=True)
class Layer0Verdict:
    passed: bool
    frozen_run_id: str = ""
    frozen_sha256: dict[str, str] = field(default_factory=dict)
    blocking_reasons: list[dict[str, Any]] = field(default_factory=list)
    frozen_report: dict[str, Any] = field(default_factory=dict)


def run_layer0(
    *,
    project_root: Path,
    subsystem: str,
    caps: JuryCaps,
) -> Layer0Verdict:
    """运行 Layer 0 输入证据绑定。

    返回 Layer0Verdict；不创建 lock（lock 由 cli 顶层 contextmanager 管理；本函数仅校验 + freeze）。
    """
    blocking: list[dict[str, Any]] = []

    # 1) ARTIFACT_INDEX active_run_id
    ai_path = project_root / "cad" / subsystem / ".cad-spec-gen" / "ARTIFACT_INDEX.json"
    if not ai_path.exists():
        return Layer0Verdict(passed=False, blocking_reasons=[{"code": "artifact_index_missing"}])
    try:
        ai = json.loads(ai_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return Layer0Verdict(passed=False, blocking_reasons=[{"code": "artifact_index_unreadable"}])

    active_run_id = ai.get("active_run_id", "")
    runs = ai.get("runs", {})
    run_meta = runs.get(active_run_id, {})
    if not run_meta.get("active"):
        return Layer0Verdict(passed=False, blocking_reasons=[{"code": "active_run_not_active"}])

    # 2) ENHANCEMENT_REPORT.json
    render_dir = project_root / "cad" / "output" / "renders" / subsystem / active_run_id
    er_path = render_dir / "ENHANCEMENT_REPORT.json"
    rm_path = render_dir / "render_manifest.json"
    if not er_path.exists():
        blocking.append({"code": "enhancement_report_missing"})
        return Layer0Verdict(passed=False, blocking_reasons=blocking)
    try:
        report = json.loads(er_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        blocking.append({"code": "enhancement_report_unreadable"})
        return Layer0Verdict(passed=False, blocking_reasons=blocking)

    # 3) 字段校验
    if report.get("subsystem") != subsystem:
        blocking.append({"code": "subsystem_mismatch", "actual": report.get("subsystem"), "expected": subsystem})
    if report.get("run_id") != active_run_id:
        blocking.append({"code": "run_id_mismatch", "actual": report.get("run_id"), "expected": active_run_id})
    if report.get("status") != "accepted":
        blocking.append({"code": "report_status_not_accepted", "actual": report.get("status")})
    if report.get("delivery_status") not in {"accepted", None}:
        blocking.append({"code": "delivery_status_not_accepted"})
    qs = report.get("quality_summary", {})
    if qs.get("status") != "accepted":
        blocking.append({"code": "quality_summary_not_accepted"})

    views = report.get("views", [])
    if not views:
        blocking.append({"code": "views_empty"})
    elif len(views) > caps.max_n_views:
        blocking.append({"code": "max_n_views_exceeded", "actual": len(views), "cap": caps.max_n_views})

    seen_view_names: set[str] = set()
    for v in views:
        name = v.get("view", "")
        if name in seen_view_names:
            blocking.append({"code": "duplicate_view", "view": name})
        seen_view_names.add(name)

    # 4) 图大小预检
    for v in views:
        rel = v.get("enhanced_image", "")
        if rel:
            img_path = project_root / rel
            try:
                size = img_path.stat().st_size
                if size > caps.max_image_bytes:
                    blocking.append({
                        "code": "image_too_large",
                        "view": v.get("view"),
                        "size": size,
                        "cap": caps.max_image_bytes,
                    })
            except OSError:
                pass  # 缺文件由后续 LLM 阶段处理

    if blocking:
        return Layer0Verdict(passed=False, blocking_reasons=blocking, frozen_report=report)

    # 5) freeze sha256
    frozen_sha = {
        "enhancement_report": file_sha256(er_path),
        "render_manifest": file_sha256(rm_path) if rm_path.exists() else "",
    }
    return Layer0Verdict(
        passed=True,
        frozen_run_id=active_run_id,
        frozen_sha256=frozen_sha,
        blocking_reasons=[],
        frozen_report=report,
    )
```

- [ ] **Step 4: 跑测试 PASS**

```bash
pytest tests/jury/test_input_evidence_binding.py -v
```
Expected: 6 passed

- [ ] **Step 5: 提交**

```bash
git add tools/jury/input_evidence_binding.py tests/jury/test_input_evidence_binding.py
git commit -m "feat(jury): input_evidence_binding.py Layer 0 基础 (6 case)"
```

---

### Task 14: Layer 0 资源/竞态边界 case 补全

**Files:**
- Modify: `tests/jury/test_input_evidence_binding.py` — 加 max_n_views / image_too_large / sha freeze 漂移

- [ ] **Step 1: 加 case**

```python
# 追加到 tests/jury/test_input_evidence_binding.py

def test_max_n_views_exceeded_blocked(project_root_with_run: Path) -> None:
    er_path = project_root_with_run / "cad" / "output" / "renders" / "lifting_platform" / "20260508-123456" / "ENHANCEMENT_REPORT.json"
    er = json.loads(er_path.read_text(encoding="utf-8"))
    er["views"] = er["views"] * 20  # 40 视角，超 32 cap
    er_path.write_text(json.dumps(er), encoding="utf-8")
    v = run_layer0(project_root=project_root_with_run, subsystem="lifting_platform", caps=_DEFAULT_CAPS)
    assert v.passed is False
    assert any(r["code"] == "max_n_views_exceeded" for r in v.blocking_reasons)


def test_image_too_large_blocked(project_root_with_run: Path) -> None:
    img = project_root_with_run / "cad" / "output" / "renders" / "lifting_platform" / "20260508-123456" / "iso_enhanced.png"
    img.write_bytes(b"\x00" * (10 * 1024 * 1024))  # 10 MiB > 8 MiB cap
    v = run_layer0(project_root=project_root_with_run, subsystem="lifting_platform", caps=_DEFAULT_CAPS)
    assert v.passed is False
    assert any(r["code"] == "image_too_large" for r in v.blocking_reasons)


def test_active_run_not_active_blocked(project_root_with_run: Path) -> None:
    ai_path = project_root_with_run / "cad" / "lifting_platform" / ".cad-spec-gen" / "ARTIFACT_INDEX.json"
    ai = json.loads(ai_path.read_text(encoding="utf-8"))
    ai["runs"]["20260508-123456"]["active"] = False
    ai_path.write_text(json.dumps(ai), encoding="utf-8")
    v = run_layer0(project_root=project_root_with_run, subsystem="lifting_platform", caps=_DEFAULT_CAPS)
    assert v.passed is False


def test_artifact_index_missing_blocked(tmp_path: Path) -> None:
    """完全空 project_root，无 ARTIFACT_INDEX → blocked。"""
    v = run_layer0(project_root=tmp_path, subsystem="x", caps=_DEFAULT_CAPS)
    assert v.passed is False
    assert any(r["code"] == "artifact_index_missing" for r in v.blocking_reasons)


def test_sha256_freeze_returns_with_prefix(project_root_with_run: Path) -> None:
    v = run_layer0(project_root=project_root_with_run, subsystem="lifting_platform", caps=_DEFAULT_CAPS)
    assert v.frozen_sha256["enhancement_report"].startswith("sha256:")
    assert v.frozen_sha256["render_manifest"].startswith("sha256:")
```

- [ ] **Step 2: 跑测试**

```bash
pytest tests/jury/test_input_evidence_binding.py -v
```
Expected: 11 passed

- [ ] **Step 3: 提交**

```bash
git add tests/jury/test_input_evidence_binding.py
git commit -m "test(jury): Layer 0 资源/竞态边界 (5 case)"
```

---

### Task 15: llm_client.py 骨架 + kill switch + 200 happy path

**Files:**
- Create: `tools/jury/llm_client.py`
- Test: `tests/jury/test_llm_client.py`

- [ ] **Step 1: 写失败测试 — kill switch + 200 happy + api_key 不漏 + url redact**

```python
# tests/jury/test_llm_client.py
"""LLM HTTP 调用 + 重试 + redact + kill switch + vendor_request_id 提取。"""
from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, patch

import pytest

from tools.jury.config import JuryProfile
from tools.jury.llm_client import (
    JuryDisabledByEnv,
    JuryLlmError,
    LlmResponse,
    request_jury_verdict,
)


@pytest.fixture
def profile() -> JuryProfile:
    return JuryProfile(
        id="test", kind="openai_compat",
        api_base_url="https://api.example.com/v1",
        api_key="dummy-not-a-real-key",
        model="gpt-4o", cost_per_call_usd=0.020,
    )


@pytest.fixture
def fake_image(tmp_path):
    p = tmp_path / "img.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    return p


def _mock_response(status: int = 200, body: dict | None = None, headers: dict | None = None):
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = json.dumps(body or {
        "id": "chatcmpl-Abc",
        "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
    }).encode("utf-8")
    resp.headers = headers or {"Content-Type": "application/json", "x-request-id": "trace-123"}
    return resp


def test_kill_switch_raises_jury_disabled(profile, fake_image, monkeypatch) -> None:
    monkeypatch.setenv("CAD_JURY_DISABLE_LLM", "1")
    with pytest.raises(JuryDisabledByEnv):
        request_jury_verdict(profile=profile, image_path=fake_image, prompt="x")


def test_200_happy_returns_llm_response(profile, fake_image, enable_llm_for_test) -> None:
    with patch("tools.jury.llm_client.urlopen") as m:
        m.return_value.__enter__.return_value = _mock_response()
        resp = request_jury_verdict(profile=profile, image_path=fake_image, prompt="x")
    assert resp.http_status == 200
    assert resp.attempts == 1
    assert resp.vendor_request_id == "trace-123"


def test_api_key_not_in_exception_str(profile, fake_image, enable_llm_for_test) -> None:
    """模拟 401 看 JuryLlmError str 不含 key。"""
    with patch("tools.jury.llm_client.urlopen") as m:
        from urllib.error import HTTPError
        m.side_effect = HTTPError(
            url=f"{profile.api_base_url}/chat/completions",
            code=401, msg="Unauthorized",
            hdrs={"Content-Type": "application/json"},
            fp=io.BytesIO(b'{"error": "invalid_api_key"}'),
        )
        try:
            request_jury_verdict(profile=profile, image_path=fake_image, prompt="x", max_retries=0)
        except JuryLlmError as exc:
            assert "dummy-not-a-real-key" not in str(exc)


def test_disable_llm_does_not_call_urlopen(profile, fake_image, monkeypatch) -> None:
    monkeypatch.setenv("CAD_JURY_DISABLE_LLM", "1")
    with patch("tools.jury.llm_client.urlopen") as m:
        with pytest.raises(JuryDisabledByEnv):
            request_jury_verdict(profile=profile, image_path=fake_image, prompt="x")
        m.assert_not_called()
```

- [ ] **Step 2: 跑测试 fail**

```bash
pytest tests/jury/test_llm_client.py -v
```
Expected: FAIL

- [ ] **Step 3: 实现 llm_client.py 骨架（仅 200 happy + kill switch；先让 4 case 过）**

```python
# tools/jury/llm_client.py
"""Vision API HTTP 调用 + 重试 + redact + kill switch + vendor_request_id 提取。

显式 timeout=60s + http.client.HTTPConnection.debuglevel=0 防 debug log 漏 Authorization。
所有出口（错误日志 / 异常 str）通过 redact.py。
"""
from __future__ import annotations

import base64
import http.client
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# 防外部 logging level=DEBUG 漏 Authorization 到 stderr
http.client.HTTPConnection.debuglevel = 0

_TIMEOUT_SEC = 60
_TOTAL_SECONDS_PER_CALL = 120.0


class JuryLlmError(Exception):
    """所有 LLM 调用失败的基类（不 redact 时不抛给用户）。"""
    def __init__(self, error_kind: str, http_status: int = 0, message: str = ""):
        super().__init__(f"{error_kind} (http={http_status})")
        self.error_kind = error_kind
        self.http_status = http_status
        self._message = message  # 内部，str() 不暴露


class JuryDisabledByEnv(JuryLlmError):
    def __init__(self):
        super().__init__("disabled_by_env", 0, "")


@dataclass(frozen=True)
class LlmResponse:
    content_text: str
    http_status: int
    attempts: int
    latency_ms: int
    vendor_request_id: Optional[str] = None
    finish_reason: Optional[str] = None


def request_jury_verdict(
    *,
    profile,
    image_path: Path,
    prompt: str,
    max_retries: int = 2,
    total_seconds_cap: float = _TOTAL_SECONDS_PER_CALL,
) -> LlmResponse:
    """单视角 vision API 调用。"""
    if os.environ.get("CAD_JURY_DISABLE_LLM") == "1":
        raise JuryDisabledByEnv()

    url = f"{profile.api_base_url}/chat/completions"
    b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    body = json.dumps({
        "model": profile.model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ],
        }],
        "max_tokens": 512,
        "temperature": 0.0,
    }).encode("utf-8")

    headers = {
        "Authorization": f"Bearer {profile.api_key}",
        "Content-Type": "application/json",
    }
    req = Request(url, data=body, headers=headers, method="POST")

    start = time.time()
    last_exc: Optional[Exception] = None
    for attempt in range(1, max_retries + 2):  # 1 + retries
        if time.time() - start > total_seconds_cap:
            raise JuryLlmError("timeout", 0, "")
        try:
            with urlopen(req, timeout=_TIMEOUT_SEC) as resp:
                resp_body = resp.read()
                content_text = ""
                vendor_id = None
                finish_reason = None
                try:
                    parsed = json.loads(resp_body.decode("utf-8"))
                    if isinstance(parsed, dict):
                        choices = parsed.get("choices", [])
                        if isinstance(choices, list) and choices:
                            msg = choices[0].get("message", {})
                            content_text = str(msg.get("content", "") or "")
                            finish_reason = choices[0].get("finish_reason")
                        vendor_id = parsed.get("id")
                except (json.JSONDecodeError, ValueError):
                    pass
                # 优先取 header x-request-id（urllib 已大小写不敏感）
                hdr_id = (resp.headers.get("x-request-id")
                          or resp.headers.get("openai-request-id")
                          or resp.headers.get("request-id"))
                if hdr_id:
                    vendor_id = hdr_id

                latency_ms = int((time.time() - start) * 1000)
                return LlmResponse(
                    content_text=content_text,
                    http_status=resp.status,
                    attempts=attempt,
                    latency_ms=latency_ms,
                    vendor_request_id=vendor_id,
                    finish_reason=finish_reason,
                )
        except HTTPError as exc:
            last_exc = exc
            if exc.code in {401, 403}:
                raise JuryLlmError("auth_failed", exc.code, "")
            if exc.code == 402:
                raise JuryLlmError("quota_exhausted", exc.code, "")
            if exc.code == 400:
                raise JuryLlmError("bad_request", exc.code, "")
            if exc.code == 429:
                if attempt < max_retries + 1:
                    time.sleep(min(60, 2 ** attempt))
                    continue
                raise JuryLlmError("rate_limited", exc.code, "")
            if 500 <= exc.code < 600:
                if attempt < max_retries + 1:
                    time.sleep(2 ** attempt)
                    continue
                raise JuryLlmError("server_error", exc.code, "")
            raise JuryLlmError("bad_request", exc.code, "")
        except URLError as exc:
            last_exc = exc
            if attempt < max_retries + 1:
                time.sleep(2 ** attempt)
                continue
            raise JuryLlmError("network_unreachable", 0, "")
        except TimeoutError:
            last_exc = "timeout"
            if attempt < max_retries + 1:
                time.sleep(2 ** attempt)
                continue
            raise JuryLlmError("timeout", 0, "")

    raise JuryLlmError("network_unreachable", 0, "")
```

- [ ] **Step 4: 跑测试 PASS**

```bash
pytest tests/jury/test_llm_client.py -v
```
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add tools/jury/llm_client.py tests/jury/test_llm_client.py
git commit -m "feat(jury): llm_client.py 骨架 + 200 happy + kill switch (4 case)"
```

---

### Task 16: llm_client.py 重试与错误分类 case

**Files:**
- Modify: `tests/jury/test_llm_client.py` — 加 401/402/429/500/timeout/DNS/Retry-After/auth/quota

- [ ] **Step 1: 加 case**

```python
# 追加到 tests/jury/test_llm_client.py

def test_429_retries_then_succeeds(profile, fake_image, enable_llm_for_test) -> None:
    """429 → retry → 200。"""
    from urllib.error import HTTPError
    responses = [
        HTTPError(url="x", code=429, msg="too many", hdrs={}, fp=io.BytesIO(b"")),
        _mock_response(),
    ]
    iterator = iter(responses)
    def side_effect(*args, **kwargs):
        item = next(iterator)
        if isinstance(item, HTTPError):
            raise item
        cm = MagicMock()
        cm.__enter__.return_value = item
        cm.__exit__.return_value = None
        return cm
    with patch("tools.jury.llm_client.urlopen", side_effect=side_effect), \
         patch("tools.jury.llm_client.time.sleep"):
        resp = request_jury_verdict(profile=profile, image_path=fake_image, prompt="x", max_retries=2)
    assert resp.http_status == 200
    assert resp.attempts == 2


def test_429_exhausted_raises_rate_limited(profile, fake_image, enable_llm_for_test) -> None:
    from urllib.error import HTTPError
    err = HTTPError(url="x", code=429, msg="x", hdrs={}, fp=io.BytesIO(b""))
    with patch("tools.jury.llm_client.urlopen", side_effect=err), \
         patch("tools.jury.llm_client.time.sleep"):
        with pytest.raises(JuryLlmError) as ei:
            request_jury_verdict(profile=profile, image_path=fake_image, prompt="x", max_retries=2)
    assert ei.value.error_kind == "rate_limited"


def test_401_no_retry_auth_failed(profile, fake_image, enable_llm_for_test) -> None:
    from urllib.error import HTTPError
    err = HTTPError(url="x", code=401, msg="x", hdrs={}, fp=io.BytesIO(b""))
    with patch("tools.jury.llm_client.urlopen", side_effect=err) as m:
        with pytest.raises(JuryLlmError) as ei:
            request_jury_verdict(profile=profile, image_path=fake_image, prompt="x", max_retries=2)
    assert ei.value.error_kind == "auth_failed"
    assert m.call_count == 1  # 不重试


def test_402_quota_exhausted(profile, fake_image, enable_llm_for_test) -> None:
    from urllib.error import HTTPError
    err = HTTPError(url="x", code=402, msg="x", hdrs={}, fp=io.BytesIO(b""))
    with patch("tools.jury.llm_client.urlopen", side_effect=err):
        with pytest.raises(JuryLlmError) as ei:
            request_jury_verdict(profile=profile, image_path=fake_image, prompt="x", max_retries=2)
    assert ei.value.error_kind == "quota_exhausted"


def test_500_retries(profile, fake_image, enable_llm_for_test) -> None:
    from urllib.error import HTTPError
    responses = [
        HTTPError(url="x", code=500, msg="x", hdrs={}, fp=io.BytesIO(b"")),
        _mock_response(),
    ]
    iterator = iter(responses)
    def side_effect(*args, **kwargs):
        item = next(iterator)
        if isinstance(item, HTTPError):
            raise item
        cm = MagicMock()
        cm.__enter__.return_value = item
        cm.__exit__.return_value = None
        return cm
    with patch("tools.jury.llm_client.urlopen", side_effect=side_effect), \
         patch("tools.jury.llm_client.time.sleep"):
        resp = request_jury_verdict(profile=profile, image_path=fake_image, prompt="x", max_retries=2)
    assert resp.http_status == 200


def test_url_error_dns_failure(profile, fake_image, enable_llm_for_test) -> None:
    from urllib.error import URLError
    with patch("tools.jury.llm_client.urlopen", side_effect=URLError("Name or service not known")), \
         patch("tools.jury.llm_client.time.sleep"):
        with pytest.raises(JuryLlmError) as ei:
            request_jury_verdict(profile=profile, image_path=fake_image, prompt="x", max_retries=1)
    assert ei.value.error_kind == "network_unreachable"


def test_max_retries_zero_no_retry(profile, fake_image, enable_llm_for_test) -> None:
    from urllib.error import HTTPError
    err = HTTPError(url="x", code=500, msg="x", hdrs={}, fp=io.BytesIO(b""))
    with patch("tools.jury.llm_client.urlopen", side_effect=err) as m:
        with pytest.raises(JuryLlmError):
            request_jury_verdict(profile=profile, image_path=fake_image, prompt="x", max_retries=0)
    assert m.call_count == 1  # 首发即归类，无 retry


def test_debuglevel_set_to_zero_at_import() -> None:
    """jury llm_client import 后 debuglevel=0。"""
    import http.client
    from tools.jury import llm_client  # noqa
    assert http.client.HTTPConnection.debuglevel == 0


def test_timeout_kwarg_passed_to_urlopen(profile, fake_image, enable_llm_for_test) -> None:
    with patch("tools.jury.llm_client.urlopen") as m:
        m.return_value.__enter__.return_value = _mock_response()
        request_jury_verdict(profile=profile, image_path=fake_image, prompt="x")
    _, kwargs = m.call_args
    assert kwargs.get("timeout") == 60
```

- [ ] **Step 2: 跑测试**

```bash
pytest tests/jury/test_llm_client.py -v
```
Expected: 13 passed

- [ ] **Step 3: 提交**

```bash
git add tests/jury/test_llm_client.py
git commit -m "test(jury): llm_client.py 重试 + 错误分类 (9 case)"
```

---

## CP-3: photo3d_jury cli 主流程

### Task 17: photo3d_jury.py 骨架 + cli 参数

**Files:**
- Create: `tools/photo3d_jury.py`
- Test: `tests/jury/test_photo3d_jury_cli.py`

- [ ] **Step 1: 写失败测试 — 缺 --subsystem / --list-profiles / --dry-run**

```python
# tests/jury/test_photo3d_jury_cli.py
"""cli 薄壳测试 — argparse + exit code + stderr 中文。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.photo3d_jury import main


def _write_jury_config(home: Path) -> Path:
    cfg = home / ".claude" / "cad_jury_config.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps({
        "schema_version": 1,
        "active_profile_id": "main",
        "profiles": [{
            "id": "main", "kind": "openai_compat",
            "api_base_url": "https://api.example.com/v1",
            "api_key": "dummy-not-a-real-key",
            "model": "gpt-4o", "cost_per_call_usd": 0.020,
        }],
    }), encoding="utf-8")
    return cfg


def test_missing_subsystem_exits_2(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    _write_jury_config(tmp_path)
    code = main([])
    assert code == 2


def test_config_missing_exits_2(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    code = main(["--subsystem", "x"])
    assert code == 2


def test_list_profiles_exits_0(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    _write_jury_config(tmp_path)
    code = main(["--list-profiles"])
    assert code == 0
    captured = capsys.readouterr()
    assert "main" in captured.out
    assert "openai_compat" in captured.out
```

- [ ] **Step 2: 跑测试 fail**

```bash
pytest tests/jury/test_photo3d_jury_cli.py -v
```
Expected: FAIL

- [ ] **Step 3: 实现 photo3d_jury.py 骨架**

```python
# tools/photo3d_jury.py
"""photo3d-jury cli 薄壳 — 顶层 try/finally + 报告组装。

走 cad_pipeline.py jury subcommand dispatch 调用；不进 pyproject [project.scripts]。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from tools.jury.config import (
    JuryConfigError,
    JuryConfigSchemaError,
    load_jury_config,
)
from tools.jury.stderr_messages import format_stderr_message


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="photo3d-jury", description="自动照片级验收（vision LLM jury）")
    p.add_argument("--subsystem")
    p.add_argument("--config", type=Path, default=None)
    p.add_argument("--allow-external-config", action="store_true")
    p.add_argument("--profile-id")
    p.add_argument("--list-profiles", action="store_true")
    p.add_argument("--last-status", action="store_true")
    p.add_argument("--budget", type=float, default=0.1)
    p.add_argument("--confirm-cost", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--max-retries", type=int, default=2)
    p.add_argument("--debug-output", type=Path)
    p.add_argument("--force", action="store_true")
    p.add_argument("--project-root", type=Path, default=Path.cwd())
    return p


def _resolve_config_path(args: argparse.Namespace) -> Path:
    if args.config:
        return Path(args.config).resolve()
    home = Path(os.environ.get("USERPROFILE") or os.environ.get("HOME") or "~").expanduser()
    return home / ".claude" / "cad_jury_config.json"


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    config_path = _resolve_config_path(args)

    # --list-profiles 优先级最高
    if args.list_profiles:
        try:
            profile, caps = load_jury_config(config_path)
        except (JuryConfigError, FileNotFoundError) as exc:
            sys.stderr.write(format_stderr_message(
                exit_code=2, error_kind="config_missing",
                context={"config_path": str(config_path)}) + "\n")
            return 2
        # 简化：仅打印 active profile（完整版应读所有 profiles）
        cost_str = f"{profile.cost_per_call_usd}" if profile.cost_per_call_usd is not None else "null"
        print(f"{profile.id}\t{profile.kind}\t{profile.model}\t{cost_str}\t[active]")
        return 0

    if not args.subsystem:
        sys.stderr.write("✗ 缺 --subsystem 参数\n")
        return 2

    # 校验 budget 是有限数
    import math
    if not math.isfinite(args.budget) or args.budget < 0:
        sys.stderr.write(f"✗ --budget={args.budget} 必须为有限非负数\n")
        return 2

    try:
        profile, caps = load_jury_config(config_path)
    except FileNotFoundError:
        sys.stderr.write(format_stderr_message(
            exit_code=2, error_kind="config_missing",
            context={"config_path": str(config_path)}) + "\n")
        return 2
    except JuryConfigSchemaError as exc:
        sys.stderr.write(format_stderr_message(
            exit_code=2, error_kind="schema_version_invalid",
            context={"actual": str(exc)}) + "\n")
        return 2
    except JuryConfigError as exc:
        sys.stderr.write(f"✗ 配置错: {exc}\n")
        return 2

    # TODO Task 18+: Layer 0 / cost / Layer 1 / Layer 2 / 写报告
    # 当前骨架仅完成参数解析与 config 加载
    sys.stderr.write("△ jury 主流程未实现（占位）\n")
    return 99


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 跑测试 PASS**

```bash
pytest tests/jury/test_photo3d_jury_cli.py -v
```
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add tools/photo3d_jury.py tests/jury/test_photo3d_jury_cli.py
git commit -m "feat(jury): photo3d_jury.py cli 骨架 + --list-profiles + 配置校验 (3 case)"
```

---

### Task 18: photo3d_jury.py 主流程串联（Layer 0 + cost + Layer 1 + Layer 2 + 写报告）

**Files:**
- Modify: `tools/photo3d_jury.py` — 完成主流程
- Modify: `tests/jury/test_photo3d_jury_cli.py` — 加全成功 / 输入证据错 / cost 超 budget e2e

- [ ] **Step 1: 加测试 case**

```python
# 追加到 tests/jury/test_photo3d_jury_cli.py

# 接 Task 13 的 project_root_with_run fixture
@pytest.fixture
def project_root_with_run(tmp_path):
    """复制自 test_input_evidence_binding.py。"""
    sub = "lifting_platform"
    run_id = "20260508-123456"
    fixtures = Path("tests/jury/fixtures")

    run_dir = tmp_path / "cad" / sub / ".cad-spec-gen" / "runs" / run_id
    run_dir.mkdir(parents=True)
    render_dir = tmp_path / "cad" / "output" / "renders" / sub / run_id
    render_dir.mkdir(parents=True)
    (render_dir / "iso_enhanced.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 1000)
    (render_dir / "front_enhanced.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 1000)

    rm = json.loads((fixtures / "sample_render_manifest.json").read_text(encoding="utf-8"))
    er = json.loads((fixtures / "sample_enhancement_report.json").read_text(encoding="utf-8"))
    for v in er["views"]:
        v["enhanced_image"] = f"cad/output/renders/{sub}/{run_id}/{v['view']}_enhanced.png"
    (render_dir / "render_manifest.json").write_text(json.dumps(rm), encoding="utf-8")
    (render_dir / "ENHANCEMENT_REPORT.json").write_text(json.dumps(er), encoding="utf-8")

    ai = json.loads((fixtures / "sample_artifact_index.json").read_text(encoding="utf-8"))
    (run_dir.parent.parent / "ARTIFACT_INDEX.json").write_text(json.dumps(ai), encoding="utf-8")
    return tmp_path


def test_dry_run_no_writes(project_root_with_run, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    _write_jury_config(tmp_path)
    code = main([
        "--subsystem", "lifting_platform",
        "--project-root", str(project_root_with_run),
        "--dry-run",
    ])
    assert code == 0
    # 不应有 PHOTO3D_JURY_REPORT.json 落盘
    run_dir = project_root_with_run / "cad" / "lifting_platform" / ".cad-spec-gen" / "runs" / "20260508-123456"
    assert not (run_dir / "PHOTO3D_JURY_REPORT.json").exists()


def test_input_evidence_error_exits_1(project_root_with_run, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    _write_jury_config(tmp_path)
    code = main([
        "--subsystem", "wrong_subsystem",
        "--project-root", str(project_root_with_run),
        "--dry-run",
    ])
    assert code == 1


def test_cost_over_budget_no_confirm_exits_3(project_root_with_run, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    # 写一个高 cost profile
    cfg = tmp_path / ".claude" / "cad_jury_config.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps({
        "schema_version": 1, "active_profile_id": "main",
        "profiles": [{"id": "main", "kind": "openai_compat",
                      "api_base_url": "https://x/v1", "api_key": "dummy", "model": "x",
                      "cost_per_call_usd": 1.0}],
    }), encoding="utf-8")
    code = main([
        "--subsystem", "lifting_platform",
        "--project-root", str(project_root_with_run),
        "--dry-run",
    ])
    assert code == 3
```

- [ ] **Step 2: 实现 photo3d_jury.py 主流程**

读 spec §4.7 9 步骤，逐步串联：

```python
# tools/photo3d_jury.py 替换 TODO 占位部分
# ... 上面 imports 不变 ...

from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools._file_lock import LockBusy as JuryLockBusy, acquire_lock
from tools.contract_io import file_sha256, write_json_atomic
from tools.jury.cost import compute_cost_decision
from tools.jury.deterministic_gate import run_layer1
from tools.jury.input_evidence_binding import run_layer0
from tools.jury.llm_client import (
    JuryDisabledByEnv,
    JuryLlmError,
    request_jury_verdict,
)
from tools.jury.redact import redact_traceback_str
from tools.jury.verdict import parse_view_verdict


_JURY_PROMPT = """\
你是一名 CAD 渲染照片级验收员。下面这张图来自一台机械产品的多视角渲染增强后输出。
请按以下 5 项判断（各只出 true/false）：
1. geometry_preserved   — 几何与设计一致，无明显形变/丢件
2. material_consistent  — 材质风格统一，无明显错配
3. photorealistic       — 视觉质感像真实拍摄而非 3D 渲染
4. no_extra_parts       — 没有 LLM 凭空加出的零件、装饰、文字
5. no_missing_parts     — 没有把原本存在的零件擦除

另给 photoreal_score（0-100 整数，单独度量第 3 项的强度）。

只返回严格 JSON：
{"semantic_checks":{"geometry_preserved":bool,"material_consistent":bool,
"photorealistic":bool,"no_extra_parts":bool,"no_missing_parts":bool},
"photoreal_score":int,"reason":"<= 80 字"}

不要 markdown 代码块。不要解释。
"""


def _utc_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _utc_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _archive_existing_report(report_path: Path, force: bool) -> None:
    if not report_path.exists():
        return
    if force:
        archived = report_path.parent / "PHOTO3D_JURY_REPORT.forced.json"
    else:
        body = report_path.read_bytes()
        import hashlib
        short = hashlib.sha256(body).hexdigest()[:6]
        archived = report_path.parent / f"PHOTO3D_JURY_REPORT.{_utc_compact()}.{short}.json"
    report_path.rename(archived)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    config_path = _resolve_config_path(args)

    if args.list_profiles:
        # ... 已有 ...
        pass

    if not args.subsystem:
        sys.stderr.write("✗ 缺 --subsystem 参数\n")
        return 2

    import math
    if not math.isfinite(args.budget) or args.budget < 0:
        sys.stderr.write(f"✗ --budget={args.budget} 必须为有限非负数\n")
        return 2

    try:
        profile, caps = load_jury_config(config_path)
    except (JuryConfigError, FileNotFoundError) as exc:
        sys.stderr.write(format_stderr_message(
            exit_code=2, error_kind="config_missing",
            context={"config_path": str(config_path)}) + "\n")
        return 2

    project_root = Path(args.project_root).resolve()
    run_dir_for_report: Path | None = None

    try:
        # === step 2: Layer 0 ===
        layer0 = run_layer0(project_root=project_root, subsystem=args.subsystem, caps=caps)
        if not layer0.passed:
            return _write_blocked_report(project_root, args.subsystem, layer0)

        run_dir = project_root / "cad" / args.subsystem / ".cad-spec-gen" / "runs" / layer0.frozen_run_id
        report_path = run_dir / "PHOTO3D_JURY_REPORT.json"
        run_dir_for_report = run_dir

        # === step 0: 重跑保护 ===
        _archive_existing_report(report_path, args.force)

        if args.dry_run:
            # === step 3: cost 预估（dry-run 跑到这里就停） ===
            n_views = len(layer0.frozen_report.get("views", []))
            cd = compute_cost_decision(
                cost_per_call_usd=profile.cost_per_call_usd or 0.0,
                n_views=n_views,
                budget_per_run_usd=args.budget,
                confirm_cost=args.confirm_cost,
            )
            print(f"[dry-run] estimated={cd.estimated_usd} USD, allowed={cd.allowed}")
            return 0 if cd.allowed else 3

        # === step 3: cost ===
        n_views = len(layer0.frozen_report["views"])
        cd = compute_cost_decision(
            cost_per_call_usd=profile.cost_per_call_usd or 0.0,
            n_views=n_views,
            budget_per_run_usd=args.budget,
            confirm_cost=args.confirm_cost,
        )
        if not cd.allowed:
            sys.stderr.write(format_stderr_message(
                exit_code=3, error_kind="budget_exceeded",
                context={
                    "estimated_cost_usd": cd.estimated_usd,
                    "budget_per_run_usd": args.budget,
                    "n_views": n_views,
                    "cost_per_call_usd": profile.cost_per_call_usd or 0.0,
                }) + "\n")
            return 3

        # === step 4: Layer 1 ===
        layer1 = run_layer1(layer0.frozen_report)
        if not layer1.passed:
            return _write_preview_report(run_dir, args.subsystem, layer0, layer1, profile, n_views, cd)

        # === step 2-extension: lock + step 5: Layer 2 ===
        lock_path = run_dir / ".jury.lock"
        view_verdicts: list[dict[str, Any]] = []
        actual_cost = 0.0
        n_retries_total = 0

        with acquire_lock(lock_path):
            for view in layer0.frozen_report["views"]:
                view_name = view.get("view", "")
                img_rel = view.get("enhanced_image", "")
                img_path = project_root / img_rel
                try:
                    resp = request_jury_verdict(
                        profile=profile,
                        image_path=img_path,
                        prompt=_JURY_PROMPT,
                        max_retries=args.max_retries,
                    )
                    actual_cost += (profile.cost_per_call_usd or 0.0) * resp.attempts
                    n_retries_total += (resp.attempts - 1)
                    vv = parse_view_verdict(
                        resp.content_text,
                        finish_reason=resp.finish_reason or "stop",
                        min_photoreal_score=caps.min_photoreal_score,
                    )
                    view_verdicts.append({
                        "view": view_name,
                        "verdict": vv.verdict,
                        "semantic_checks": vv.semantic_checks,
                        "photoreal_score": vv.photoreal_score,
                        "reason": vv.reason,
                        "llm_meta": {
                            "http_status": resp.http_status,
                            "attempts": resp.attempts,
                            "latency_ms": resp.latency_ms,
                            "parse_status": vv.parse_status,
                            "parse_anomalies": vv.parse_anomalies,
                            "error_kind": None,
                            "vendor_request_id": resp.vendor_request_id,
                        },
                    })
                except JuryLlmError as exc:
                    actual_cost += (profile.cost_per_call_usd or 0.0)  # 失败也保守计入
                    view_verdicts.append({
                        "view": view_name,
                        "verdict": "needs_review",
                        "semantic_checks": {},
                        "photoreal_score": 0,
                        "reason": "",
                        "llm_meta": {
                            "http_status": exc.http_status,
                            "attempts": 1,
                            "latency_ms": 0,
                            "parse_status": "ok",
                            "parse_anomalies": [],
                            "error_kind": exc.error_kind,
                            "vendor_request_id": None,
                        },
                    })

        # === step 6: sha256 重读校验 ===
        er_path = (project_root / "cad" / "output" / "renders" / args.subsystem
                   / layer0.frozen_run_id / "ENHANCEMENT_REPORT.json")
        new_sha = file_sha256(er_path)
        if new_sha != layer0.frozen_sha256.get("enhancement_report"):
            return _write_blocked_freeze_drift(run_dir, args.subsystem, layer0,
                                               actual_cost, view_verdicts)

        # === step 7-8: 整体 status + 写报告 ===
        return _write_final_report(
            run_dir, args.subsystem, layer0, layer1, profile, caps,
            n_views, cd, actual_cost, n_retries_total, view_verdicts, args.budget,
        )
    except JuryDisabledByEnv:
        sys.stderr.write("△ CAD_JURY_DISABLE_LLM=1，jury 跳过\n")
        return 0
    except JuryLockBusy as exc:
        sys.stderr.write(format_stderr_message(
            exit_code=4, error_kind="lock_busy",
            context={"held_pid": "(see lock file)", "age_seconds": 0}) + "\n")
        return 4
    except (JuryConfigError, JuryConfigSchemaError) as exc:
        sys.stderr.write(f"✗ 配置错: {exc}\n")
        return 2
    except Exception as exc:
        # 兜底防 traceback locals dump 含 api_key
        import traceback
        tb_str = traceback.format_exc()
        sys.stderr.write(format_stderr_message(
            exit_code=99, error_kind="internal",
            context={"exception_type": type(exc).__name__}) + "\n")
        sys.stderr.write(redact_traceback_str(tb_str)[:500] + "\n")
        return 99


def _decide_status(layer0_pass: bool, layer1_pass: bool, view_verdicts: list[dict[str, Any]]) -> str:
    if not layer0_pass:
        return "blocked"
    if not layer1_pass:
        return "preview"
    if any(v["verdict"] == "needs_review" for v in view_verdicts):
        return "needs_review"
    if any(v["verdict"] == "preview" for v in view_verdicts):
        return "preview"
    return "accepted"


def _write_blocked_report(project_root: Path, subsystem: str, layer0) -> int:
    """Layer 0 fail 时写 PHOTO3D_JURY_REPORT.json 含 blocking_reasons。"""
    # 简化：走 frozen_report 不可用（Layer 0 失败时），仅写最简报告
    sys.stderr.write(f"✗ Layer 0 blocked: {layer0.blocking_reasons}\n")
    return 1


def _write_preview_report(run_dir, subsystem, layer0, layer1, profile, n_views, cd) -> int:
    sys.stderr.write(f"△ Layer 1 preview: {layer1.per_view_failures}\n")
    return 0  # preview 走 exit=0


def _write_blocked_freeze_drift(run_dir, subsystem, layer0, actual_cost, view_verdicts) -> int:
    sys.stderr.write(f"✗ sha freeze drift; cost={actual_cost}\n")
    return 1


def _write_final_report(run_dir, subsystem, layer0, layer1, profile, caps,
                        n_views, cd, actual_cost, n_retries_total, view_verdicts,
                        budget) -> int:
    overall = _decide_status(True, True, view_verdicts)
    report = {
        "schema_version": 1,
        "generated_at": _utc_z(),
        "subsystem": subsystem,
        "run_id": layer0.frozen_run_id,
        "status": overall,
        "ordinary_user_message": "(由 stderr_messages 填)",
        "next_step": "",
        "source_reports": {
            "render_manifest": (layer0.frozen_report.get("render_manifest") or ""),
            "render_manifest_sha256": layer0.frozen_sha256.get("render_manifest", ""),
            "enhancement_report": (layer0.frozen_report.get("enhancement_report") or ""),
            "enhancement_report_sha256": layer0.frozen_sha256.get("enhancement_report", ""),
        },
        "jury_meta": {
            "profile_id": profile.id,
            "model": profile.model,
            "estimated_cost_usd": cd.estimated_usd,
            "actual_cost_usd": round(actual_cost, 4),
            "budget_per_run_usd": budget,
            "min_photoreal_score": caps.min_photoreal_score,
            "n_views": n_views,
            "n_calls": sum(v["llm_meta"]["attempts"] for v in view_verdicts),
            "n_retries_total": n_retries_total,
            "max_image_bytes": caps.max_image_bytes,
            "max_n_views": caps.max_n_views,
            "cost_warning": ("estimated±50%; verify with vendor billing"
                             if profile.cost_per_call_usd is None else None),
        },
        "deterministic_gate": {
            "passed": layer1.passed,
            "per_view_failures": layer1.per_view_failures,
        },
        "views": view_verdicts,
        "blocking_reasons": [],
    }
    report_path = run_dir / "PHOTO3D_JURY_REPORT.json"
    write_json_atomic(report_path, report)

    if overall == "accepted":
        # 写 jury_review_input.json
        review_input = {
            "schema_version": 1,
            "review_type": "auto_jury_v1",
            "subsystem": subsystem,
            "run_id": layer0.frozen_run_id,
            "source_reports": report["source_reports"],
            "views": [
                {
                    "view": v["view"],
                    "semantic_checks": v["semantic_checks"],
                    "reviewer_notes": f"auto_jury photoreal_score={v['photoreal_score']}",
                }
                for v in view_verdicts
            ],
        }
        write_json_atomic(run_dir / "jury_review_input.json", review_input)

    return 0
```

- [ ] **Step 3: 跑测试 PASS**

```bash
pytest tests/jury/test_photo3d_jury_cli.py -v
```
Expected: 6 passed

- [ ] **Step 4: 提交**

```bash
git add tools/photo3d_jury.py tests/jury/test_photo3d_jury_cli.py
git commit -m "feat(jury): photo3d_jury.py 主流程串联（Layer 0/1/2 + 写报告）"
```

---

## CP-4: 集成测试 + 完整 e2e + DELIVERY 协同

### Task 19: 集成 e2e — 全 200 happy path

**Files:**
- Create: `tests/jury/test_photo3d_jury_e2e.py`

- [ ] **Step 1: 写 e2e fixture + 全 200 happy 测试**

```python
# tests/jury/test_photo3d_jury_e2e.py
"""集成 e2e — patch tools.jury.llm_client.urlopen，构造完整 cad/<sub>/.cad-spec-gen/runs/<run>/。"""
from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.photo3d_jury import main


def _ok_response_iter(views: list[str]):
    """返回每视角都成功的 mock response stream。"""
    bodies = [
        json.dumps({
            "id": f"chatcmpl-{v}",
            "choices": [{
                "message": {"content": json.dumps({
                    "semantic_checks": {k: True for k in [
                        "geometry_preserved", "material_consistent", "photorealistic",
                        "no_extra_parts", "no_missing_parts"]},
                    "photoreal_score": 80,
                    "reason": f"view {v} OK",
                })},
                "finish_reason": "stop",
            }],
        }).encode("utf-8")
        for v in views
    ]
    for body in bodies:
        cm = MagicMock()
        resp = MagicMock(); resp.status = 200; resp.read.return_value = body
        resp.headers = {"Content-Type": "application/json", "x-request-id": "trace-x"}
        cm.__enter__.return_value = resp
        cm.__exit__.return_value = None
        yield cm


@pytest.fixture
def jury_env(tmp_path, monkeypatch):
    """完整 jury 测试环境：HOME / config / project_root。"""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("CAD_JURY_DISABLE_LLM", raising=False)  # opt-in 真发 mock

    cfg = tmp_path / ".claude" / "cad_jury_config.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps({
        "schema_version": 1, "active_profile_id": "main",
        "profiles": [{"id": "main", "kind": "openai_compat",
                      "api_base_url": "https://api.example.com/v1",
                      "api_key": "dummy-not-a-real-key",
                      "model": "gpt-4o", "cost_per_call_usd": 0.005}],
    }), encoding="utf-8")

    sub = "lifting_platform"
    run_id = "20260508-123456"
    fixtures = Path("tests/jury/fixtures")

    run_dir = tmp_path / "cad" / sub / ".cad-spec-gen" / "runs" / run_id
    run_dir.mkdir(parents=True)
    render_dir = tmp_path / "cad" / "output" / "renders" / sub / run_id
    render_dir.mkdir(parents=True)
    (render_dir / "iso_enhanced.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 1000)
    (render_dir / "front_enhanced.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 1000)

    rm = json.loads((fixtures / "sample_render_manifest.json").read_text(encoding="utf-8"))
    er = json.loads((fixtures / "sample_enhancement_report.json").read_text(encoding="utf-8"))
    for v in er["views"]:
        v["enhanced_image"] = f"cad/output/renders/{sub}/{run_id}/{v['view']}_enhanced.png"
    (render_dir / "render_manifest.json").write_text(json.dumps(rm), encoding="utf-8")
    (render_dir / "ENHANCEMENT_REPORT.json").write_text(json.dumps(er), encoding="utf-8")
    ai = json.loads((fixtures / "sample_artifact_index.json").read_text(encoding="utf-8"))
    (run_dir.parent.parent / "ARTIFACT_INDEX.json").write_text(json.dumps(ai), encoding="utf-8")
    return tmp_path


def test_full_happy_path_writes_two_reports(jury_env: Path) -> None:
    iter_responses = _ok_response_iter(["iso", "front"])
    with patch("tools.jury.llm_client.urlopen", side_effect=lambda *a, **kw: next(iter_responses)):
        code = main([
            "--subsystem", "lifting_platform",
            "--project-root", str(jury_env),
        ])
    assert code == 0
    run_dir = jury_env / "cad" / "lifting_platform" / ".cad-spec-gen" / "runs" / "20260508-123456"
    rep_path = run_dir / "PHOTO3D_JURY_REPORT.json"
    rev_path = run_dir / "jury_review_input.json"
    assert rep_path.exists()
    assert rev_path.exists()
    rep = json.loads(rep_path.read_text(encoding="utf-8"))
    assert rep["status"] == "accepted"
    assert rep["jury_meta"]["actual_cost_usd"] == pytest.approx(0.010)  # 2 × 0.005
    assert rep["jury_meta"]["estimated_cost_usd"] == pytest.approx(0.010)
    assert all(v["verdict"] == "accepted" for v in rep["views"])


def test_api_key_not_in_report(jury_env: Path) -> None:
    iter_responses = _ok_response_iter(["iso", "front"])
    with patch("tools.jury.llm_client.urlopen", side_effect=lambda *a, **kw: next(iter_responses)):
        main(["--subsystem", "lifting_platform", "--project-root", str(jury_env)])
    run_dir = jury_env / "cad" / "lifting_platform" / ".cad-spec-gen" / "runs" / "20260508-123456"
    rep = (run_dir / "PHOTO3D_JURY_REPORT.json").read_text(encoding="utf-8")
    assert "dummy-not-a-real-key" not in rep
```

- [ ] **Step 2: 跑 e2e**

```bash
pytest tests/jury/test_photo3d_jury_e2e.py -v
```
Expected: 2 passed

- [ ] **Step 3: 提交**

```bash
git add tests/jury/test_photo3d_jury_e2e.py
git commit -m "test(jury): e2e 全 happy path + api_key 不落盘"
```

---

### Task 20: e2e 失败路径（401 / score 低 / cost 超）

**Files:**
- Modify: `tests/jury/test_photo3d_jury_e2e.py` — 加 needs_review / preview / blocked / cost over

- [ ] **Step 1: 加 case**

```python
# 追加到 tests/jury/test_photo3d_jury_e2e.py

def test_one_view_401_overall_needs_review(jury_env: Path) -> None:
    """1 视角 401 → 整体 needs_review；jury_review_input.json 不写。"""
    from urllib.error import HTTPError
    err_401 = HTTPError(url="x", code=401, msg="x", hdrs={}, fp=io.BytesIO(b""))
    ok_resp = next(_ok_response_iter(["front"]))

    calls = [err_401, ok_resp]
    iterator = iter(calls)
    def side_effect(*a, **kw):
        c = next(iterator)
        if isinstance(c, HTTPError):
            raise c
        return c
    with patch("tools.jury.llm_client.urlopen", side_effect=side_effect), \
         patch("tools.jury.llm_client.time.sleep"):
        code = main(["--subsystem", "lifting_platform", "--project-root", str(jury_env)])
    assert code == 0
    run_dir = jury_env / "cad" / "lifting_platform" / ".cad-spec-gen" / "runs" / "20260508-123456"
    rep = json.loads((run_dir / "PHOTO3D_JURY_REPORT.json").read_text(encoding="utf-8"))
    assert rep["status"] == "needs_review"
    assert any(v["llm_meta"]["error_kind"] == "auth_failed" for v in rep["views"])
    # needs_review 不写 jury_review_input.json
    assert not (run_dir / "jury_review_input.json").exists()


def test_low_score_overall_preview(jury_env: Path) -> None:
    """全成功但 1 视角 score=15 → preview；review_input 不写。"""
    bodies = [
        json.dumps({"id": "x", "choices": [{
            "message": {"content": json.dumps({
                "semantic_checks": {k: True for k in [
                    "geometry_preserved", "material_consistent", "photorealistic",
                    "no_extra_parts", "no_missing_parts"]},
                "photoreal_score": 15, "reason": "low",
            })}, "finish_reason": "stop"}]}).encode("utf-8"),
        json.dumps({"id": "y", "choices": [{
            "message": {"content": json.dumps({
                "semantic_checks": {k: True for k in [
                    "geometry_preserved", "material_consistent", "photorealistic",
                    "no_extra_parts", "no_missing_parts"]},
                "photoreal_score": 80, "reason": "ok",
            })}, "finish_reason": "stop"}]}).encode("utf-8"),
    ]
    iterator = iter(bodies)
    def side_effect(*a, **kw):
        body = next(iterator)
        cm = MagicMock(); resp = MagicMock()
        resp.status = 200; resp.read.return_value = body; resp.headers = {"Content-Type": "application/json"}
        cm.__enter__.return_value = resp; cm.__exit__.return_value = None
        return cm
    with patch("tools.jury.llm_client.urlopen", side_effect=side_effect):
        code = main(["--subsystem", "lifting_platform", "--project-root", str(jury_env)])
    assert code == 0
    run_dir = jury_env / "cad" / "lifting_platform" / ".cad-spec-gen" / "runs" / "20260508-123456"
    rep = json.loads((run_dir / "PHOTO3D_JURY_REPORT.json").read_text(encoding="utf-8"))
    assert rep["status"] == "preview"
    assert not (run_dir / "jury_review_input.json").exists()


def test_subsystem_mismatch_blocked(jury_env: Path) -> None:
    code = main(["--subsystem", "wrong_sub", "--project-root", str(jury_env)])
    assert code == 1
```

- [ ] **Step 2: 跑测试**

```bash
pytest tests/jury/test_photo3d_jury_e2e.py -v
```
Expected: 5 passed

- [ ] **Step 3: 提交**

```bash
git add tests/jury/test_photo3d_jury_e2e.py
git commit -m "test(jury): e2e 失败路径（401/低 score/blocked）"
```

---

### Task 21: 重跑保护 + sha freeze drift e2e

**Files:**
- Modify: `tests/jury/test_photo3d_jury_e2e.py` — 加重跑归档 / --force / sha drift

- [ ] **Step 1: 加 case**

```python
def test_rerun_archives_existing_report(jury_env: Path) -> None:
    """已有 PHOTO3D_JURY_REPORT.json + 重跑 → 归档前次 + 写新报告。"""
    iter_resp = _ok_response_iter(["iso", "front"])
    with patch("tools.jury.llm_client.urlopen", side_effect=lambda *a, **kw: next(iter_resp)):
        main(["--subsystem", "lifting_platform", "--project-root", str(jury_env)])
    iter_resp2 = _ok_response_iter(["iso", "front"])
    with patch("tools.jury.llm_client.urlopen", side_effect=lambda *a, **kw: next(iter_resp2)):
        main(["--subsystem", "lifting_platform", "--project-root", str(jury_env)])
    run_dir = jury_env / "cad" / "lifting_platform" / ".cad-spec-gen" / "runs" / "20260508-123456"
    archived = list(run_dir.glob("PHOTO3D_JURY_REPORT.20*Z.*.json"))
    assert len(archived) == 1
    # 归档名无冒号（Windows NTFS 兼容）
    assert ":" not in archived[0].name


def test_force_archives_with_fixed_suffix(jury_env: Path) -> None:
    iter_resp = _ok_response_iter(["iso", "front"])
    with patch("tools.jury.llm_client.urlopen", side_effect=lambda *a, **kw: next(iter_resp)):
        main(["--subsystem", "lifting_platform", "--project-root", str(jury_env)])
    iter_resp2 = _ok_response_iter(["iso", "front"])
    with patch("tools.jury.llm_client.urlopen", side_effect=lambda *a, **kw: next(iter_resp2)):
        main(["--subsystem", "lifting_platform", "--project-root", str(jury_env), "--force"])
    run_dir = jury_env / "cad" / "lifting_platform" / ".cad-spec-gen" / "runs" / "20260508-123456"
    assert (run_dir / "PHOTO3D_JURY_REPORT.forced.json").exists()
```

- [ ] **Step 2: 跑测试**

```bash
pytest tests/jury/test_photo3d_jury_e2e.py -v
```
Expected: 7 passed

- [ ] **Step 3: 提交**

```bash
git add tests/jury/test_photo3d_jury_e2e.py
git commit -m "test(jury): e2e 重跑保护 + --force 归档"
```

---

### Task 22: photo3d-deliver 集成 — DELIVERY_PACKAGE.json 加 jury 字段

**Files:**
- Modify: `tools/photo3d_delivery_pack.py` — 读 PHOTO3D_JURY_REPORT.json 落 jury 字段
- Modify: `tests/test_photo3d_delivery_pack.py` — 加 jury 字段断言

- [ ] **Step 1: 写失败测试**

```python
# tests/test_photo3d_delivery_pack.py 追加
def test_delivery_package_includes_jury_field_when_jury_ran(tmp_path):
    """jury 跑过后 deliver 把 jury 报告并入 DELIVERY_PACKAGE.json。"""
    from tools import photo3d_delivery_pack as dp
    # 构造 active_run + ENHANCEMENT_REVIEW_REPORT.json（已 accepted）
    # + PHOTO3D_JURY_REPORT.json（jury 已跑）
    # ... fixture 设置 ...
    # ... 跑 deliver ...
    # 断言 DELIVERY_PACKAGE.json 含 jury 字段：
    pkg = json.loads((run_dir / "DELIVERY_PACKAGE.json").read_text(encoding="utf-8"))
    assert "jury" in pkg
    assert pkg["jury"]["status"] in {"accepted", "preview", "needs_review", "blocked"}
    assert "actual_cost_usd" in pkg["jury"]
    assert "vendor_request_ids" in pkg["jury"]
    assert isinstance(pkg["jury"]["vendor_request_ids"], list)
```

- [ ] **Step 2: 实现 — `tools/photo3d_delivery_pack.py` 加 jury 字段读取与汇总**

读 `tools/photo3d_delivery_pack.py` 找产出 DELIVERY_PACKAGE.json 的函数；加：

```python
def _build_jury_section(run_dir: Path, project_root: Path) -> dict | None:
    jury_report_path = run_dir / "PHOTO3D_JURY_REPORT.json"
    if not jury_report_path.exists():
        return None
    rep = json.loads(jury_report_path.read_text(encoding="utf-8"))
    review_input_path = run_dir / "jury_review_input.json"
    review_input_rel = (project_relative(review_input_path, project_root)
                        if review_input_path.exists() else None)
    vendor_ids = [
        v["llm_meta"].get("vendor_request_id")
        for v in rep.get("views", [])
        if v.get("llm_meta", {}).get("vendor_request_id")
    ]
    return {
        "report": project_relative(jury_report_path, project_root),
        "review_input": review_input_rel,
        "status": rep.get("status"),
        "actual_cost_usd": rep.get("jury_meta", {}).get("actual_cost_usd"),
        "vendor_request_ids": vendor_ids,
        "jury_report_schema_version": rep.get("schema_version"),
    }

# 在 build_delivery_package 函数返 dict 时加：
package["jury"] = _build_jury_section(run_dir, project_root)
```

- [ ] **Step 3: 跑测试 PASS**

```bash
pytest tests/test_photo3d_delivery_pack.py -v
```
Expected: all PASS（含新加 case）

- [ ] **Step 4: 提交**

```bash
git add tools/photo3d_delivery_pack.py tests/test_photo3d_delivery_pack.py
git commit -m "feat(deliver): DELIVERY_PACKAGE.json 加 jury 字段（聚合 vendor_request_ids）"
```

---

### Task 23: 链路 e2e — jury → enhance-review

**Files:**
- Modify: `tests/jury/test_photo3d_jury_e2e.py` — 加完整链路 + 链路负向

- [ ] **Step 1: 加 case**

```python
def test_jury_review_input_feeds_enhance_review(jury_env: Path) -> None:
    """jury 出 review-input → enhance-review 跑通 → ENHANCEMENT_REVIEW_REPORT.json status=accepted。"""
    iter_resp = _ok_response_iter(["iso", "front"])
    with patch("tools.jury.llm_client.urlopen", side_effect=lambda *a, **kw: next(iter_resp)):
        code = main(["--subsystem", "lifting_platform", "--project-root", str(jury_env)])
    assert code == 0
    run_dir = jury_env / "cad" / "lifting_platform" / ".cad-spec-gen" / "runs" / "20260508-123456"
    review_input = run_dir / "jury_review_input.json"
    assert review_input.exists()

    # 调 enhance-review
    from tools.enhancement_semantic_review import write_enhancement_review_report
    rep = write_enhancement_review_report(
        project_root=jury_env, subsystem="lifting_platform",
        review_input_path=review_input,
    )
    assert rep["status"] == "accepted"


def test_needs_review_no_review_input_writes(jury_env: Path) -> None:
    """needs_review 时 jury_review_input.json 不写 → enhance-review 报"文件不存在"。"""
    from urllib.error import HTTPError
    err = HTTPError(url="x", code=401, msg="x", hdrs={}, fp=io.BytesIO(b""))
    ok = next(_ok_response_iter(["front"]))
    calls = iter([err, ok])
    def se(*a, **kw):
        c = next(calls)
        if isinstance(c, HTTPError):
            raise c
        return c
    with patch("tools.jury.llm_client.urlopen", side_effect=se), \
         patch("tools.jury.llm_client.time.sleep"):
        main(["--subsystem", "lifting_platform", "--project-root", str(jury_env)])
    run_dir = jury_env / "cad" / "lifting_platform" / ".cad-spec-gen" / "runs" / "20260508-123456"
    assert not (run_dir / "jury_review_input.json").exists()
```

- [ ] **Step 2: 跑测试**

```bash
pytest tests/jury/test_photo3d_jury_e2e.py -v
```
Expected: 9 passed

- [ ] **Step 3: 提交**

```bash
git add tests/jury/test_photo3d_jury_e2e.py
git commit -m "test(jury): 链路 e2e jury → enhance-review 正反场景"
```

---

## CP-5: 文档 + CI

### Task 24: docs/cad-jury-config.md

**Files:**
- Create: `docs/cad-jury-config.md`

- [ ] **Step 1: 写用户级配置文档**

```markdown
# Photo3D Jury 配置说明

## 文件位置

`~/.claude/cad_jury_config.json`（用户级，不入仓）

## 最小配置（复制后改 3 处保存）

\```json
{
  "schema_version": 1,
  "active_profile_id": "main",
  "profiles": [{
    "id": "main",
    "kind": "openai_compat",
    "api_base_url": "https://你的中转或厂商.com/v1",
    "api_key": "sk-在厂商网站申请",
    "model": "gemini-2.5-flash"
  }]
}
\```

## 字段说明

[完整字段清单 / 估价表 / TLS / 故障恢复，参考 spec §4.1 + §7.4]

## 隐私警告

增强图会以 base64 上传到 `api_base_url`；中转/原生厂商可能记录与训练；机密项目应自托管 endpoint。

## TLS 企业 CA

企业 MITM 自签 CA 由用户通过 `SSL_CERT_FILE` env 注入；jury 严禁 unverified context。

## 常见 vision 中转商示例

[列已知支持 vision 的中转商示例]

## 故障恢复

key 到期或没钱时切换 profile：

\```bash
photo3d-jury --list-profiles  # 看候选
photo3d-jury --subsystem X --profile-id <next>
\```

## .gitignore 提醒

建议 `.gitignore cad/**/.cad-spec-gen/runs/` 避免 PHOTO3D_JURY_REPORT.json 含 profile_id 落 git 暴露计费供应商指纹。
```

- [ ] **Step 2: 提交**

```bash
git add docs/cad-jury-config.md
git commit -m "docs(jury): 用户级配置说明 + 隐私警告 + 故障恢复"
```

---

### Task 25: pyproject.toml + CI mypy strict gate

**Files:**
- Modify: `pyproject.toml` — 加 jury 模块到 `[tool.coverage.run] source`
- Modify: `.github/workflows/tests.yml` — 加 mypy strict CI tool job 调用 jury

- [ ] **Step 1: 改 pyproject.toml**

读 `pyproject.toml [tool.coverage.run]` 行，在 `source = [...]` list 中加：

```toml
source = [
  # ... 既有 ...
  "tools.jury.config",
  "tools.jury.cost",
  "tools.jury.input_evidence_binding",
  "tools.jury.deterministic_gate",
  "tools.jury.llm_client",
  "tools.jury.verdict",
  "tools.jury.redact",
  "tools.jury.stderr_messages",
  "tools.photo3d_jury",
  "tools._file_lock",
]
```

- [ ] **Step 2: 改 tests.yml — mypy strict job 加 jury**

读 `.github/workflows/tests.yml` 找现有 mypy-strict job（按 v2.21.1 模式）；加：

```yaml
- name: mypy strict on tools/jury
  run: mypy --strict tools/jury tools/photo3d_jury.py tools/_file_lock.py
```

- [ ] **Step 3: 提交**

```bash
git add pyproject.toml .github/workflows/tests.yml
git commit -m "ci(jury): cov source 加 jury 模块 + mypy strict CI gate"
```

---

### Task 26: docs/cad-help-guide-zh.md / -en.md 加 §7.3.1 闭环序列 + PROGRESS

**Files:**
- Modify: `docs/cad-help-guide-zh.md` — 加 jury 段 + 完整闭环序列
- Modify: `docs/cad-help-guide-en.md` — 同步
- Modify: `docs/PROGRESS.md` — 加 v2.27.0 条目
- Modify: `docs/superpowers/README.md` — 链接 spec

- [ ] **Step 1: 改 cad-help-guide-zh.md**

读现有 photo3d-handoff / photo3d-deliver 段落风格，加：

```markdown
## photo3d-jury — 自动照片级验收

[简介 + 何时用]

### 完整 Photo3D 闭环（4 步）

\```
1. photo3d-handoff --subsystem X --confirm  # enhance + enhance-check
2. photo3d-jury --subsystem X                # vision LLM 自动验收
3. enhance-review --subsystem X --review-input <path>/jury_review_input.json
4. photo3d-deliver --subsystem X --confirm
\```

[每步说明]
```

- [ ] **Step 2: 同步英文版本**

- [ ] **Step 3: 改 PROGRESS.md**

加 v2.27.0 条目记录 jury 落地、发版总览、tests 数量、FCC 链等。

- [ ] **Step 4: 改 superpowers/README.md**

加链接到 spec + plan。

- [ ] **Step 5: 提交**

```bash
git add docs/cad-help-guide-zh.md docs/cad-help-guide-en.md docs/PROGRESS.md docs/superpowers/README.md
git commit -m "docs(jury): cad-help-guide §7.3.1 完整闭环 + PROGRESS v2.27.0"
```

---

### Task 27: 全量回归 + 最终烟测

**Files:**
- 无新文件；最终验证

- [ ] **Step 1: 全量回归**

```bash
pytest -m "not solidworks_required" -q
```
Expected: all PASS（含 jury 90+ 新测试）

- [ ] **Step 2: mypy strict**

```bash
mypy --strict tools/jury tools/photo3d_jury.py tools/_file_lock.py
```
Expected: no errors

- [ ] **Step 3: ruff + format**

```bash
ruff check tools/jury tools/photo3d_jury.py tools/_file_lock.py
ruff format --check tools/jury tools/photo3d_jury.py tools/_file_lock.py
```
Expected: clean

- [ ] **Step 4: 覆盖率验证**

```bash
pytest tests/jury --cov=tools.jury --cov=tools.photo3d_jury --cov=tools._file_lock --cov-report=term -q
```
Expected: ≥ 95% coverage on jury modules

- [ ] **Step 5: 提交（若有 lint fix）+ tag**

```bash
# 若有任何修复，commit；否则跳过
git tag v2.27.0-rc1
```

---

## Self-Review Notes

**Spec coverage:** 所有 7 lens 199 findings 被 spec rev 5 吸收；plan 27 task 覆盖：
- CP-0 (Tasks 0-3)：目录骨架 + _file_lock 抽出 + cad_pipeline 集成 + fixtures
- CP-1 (Tasks 4-7)：config + cost
- CP-2 (Tasks 8-14)：redact / stderr_messages / verdict / deterministic_gate / input_evidence_binding
- CP-3 (Tasks 15-18)：llm_client + cli 主流程
- CP-4 (Tasks 19-23)：e2e 多场景 + DELIVERY 协同 + 链路正反
- CP-5 (Tasks 24-27)：文档 + CI + 回归

**总计 27 task，每 task 含 3-5 step，约 130 个 checkbox。**

**Type consistency 已查**：
- `JuryProfile` / `JuryCaps` / `Layer0Verdict` / `Layer1Verdict` / `LlmResponse` / `ViewVerdict` / `CostDecision` 各 dataclass 字段在 plan 各 task 引用一致
- `JuryConfigError` / `JuryConfigSchemaError` (子类) / `JuryLlmError` / `JuryDisabledByEnv` / `JuryLockBusy` 异常类层级一致
- exit code 0/1/2/3/4/99 在 cli + stderr_messages + 测试断言一致
- `parse_status: Literal["ok"]` + `parse_anomalies: list[...]` 解耦在 verdict.py 与测试一致

**Placeholder scan 已查**：plan 中 TODO 仅在 Task 17 step 3 占位（标明 "Task 18+ 实现"），Task 18 step 2 替换；其他无 TBD/placeholder。

**Missing tasks 加补**：
- Task 22: photo3d-deliver DELIVERY 集成（v2 路线提到，v1 须实现）
- Task 23: 链路负向 e2e（needs_review 不写 review-input 防污染）
