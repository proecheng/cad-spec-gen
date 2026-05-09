# photo3d-autopilot 自动检测 jury config 实施计划（A1.1）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `photo3d-autopilot` 自动检测 `~/.claude/cad_jury_config.json`；已配 jury 用户在 `ready_for_enhancement` 状态自动获得 `photo3d-handoff --with-jury --confirm` 推荐而非 `enhance`；未配用户行为完全不变。

**Architecture:**
- `tools/photo3d_autopilot.py` 加 silent boolean 探针 `_jury_config_available()` + module 常量 `JURY_CONFIG_PATH`
- 修 `_next_action` 在 `ready_for_enhancement` 分支末尾调探针决定 next_action.kind / argv
- 检测 True → kind="run_handoff_with_jury" + argv 指向 photo3d-handoff；False → 现有 enhance 路径完全不变
- next_action.kind 加新枚举值（add-only schema）；status 字段保持 `ready_for_enhancement`

**Tech Stack:** Python 3.11+ / pytest / mypy strict / ruff / json + pathlib + monkeypatch

**spec 锚点：** `docs/superpowers/specs/2026-05-09-autopilot-with-jury-design.md` v1.1

---

## File Structure

| 文件 | 改动类型 | 行数估计 | 责任 |
|---|---|---|---|
| `tools/photo3d_autopilot.py` | modify | +50 行 add-only | 加 JURY_CONFIG_PATH 常量 + _jury_config_available helper + _next_action ready_for_enhancement 分支扩展 |
| `tests/test_photo3d_autopilot_jury_detection.py` | create | +200 行 | 9 helper 单测 + fixture 工厂 |
| `tests/test_photo3d_autopilot.py` | modify | +120 行 add-only | 6 集成测试覆盖 ready_for_enhancement 双路径 + 回归守门 |
| `docs/cad-jury-config.md` | modify | +15 行 | 加段落"autopilot 自动检测 jury config 行为" |
| `docs/PROGRESS.md` | modify | +5 行 | 加 v2.29.0 入口 |

**不改文件**：`tools/photo3d_handoff.py` / `tools/jury/*` / `tools/photo3d_jury.py` / `cad_pipeline.py`

---

## Task 0: 准备 + grep 守门

**Files:**
- Verify (read-only): `tools/photo3d_autopilot.py` / `tools/photo3d_provider_presets.py` / `tests/test_photo3d_autopilot.py`

- [ ] **Step 0.1: 验证当前分支**

```bash
git rev-parse --abbrev-ref HEAD
```

Expected: `feat/autopilot-with-jury`

- [ ] **Step 0.2: grep 守门核心 fact**

```bash
# 1. _next_action ready_for_enhancement 路径行号
grep -n "ready_for_enhancement\|def _next_action" tools/photo3d_autopilot.py
# Expected: line 135 def _next_action / line 216 "ready_for_enhancement"

# 2. _safe_cli_token 函数签名
grep -n "def _safe_cli_token" tools/photo3d_autopilot.py
# Expected: line 366

# 3. DEFAULT_PROVIDER_PRESET / public_provider_presets import
grep -n "DEFAULT_PROVIDER_PRESET\|public_provider_presets" tools/photo3d_autopilot.py
# Expected: line 11 import + line 210/211 用法

# 4. 现有测试文件
ls tests/test_photo3d_autopilot.py tests/test_photo3d_autopilot_jury_detection.py 2>&1
# Expected: test_photo3d_autopilot.py exists; jury_detection 不存在（本 PR 创建）
```

任一项不一致立即停下找主 agent 校准 spec。

---

## Task 1: helper 函数 + 常量（写 9 单测 → 实现 → 测试 PASS）

**Files:**
- Modify: `tools/photo3d_autopilot.py`（顶部 imports 后 add-only 加 JURY_CONFIG_PATH 常量 + module 末尾或合适位置加 _jury_config_available 函数）
- Create: `tests/test_photo3d_autopilot_jury_detection.py`

- [ ] **Step 1.1: 写 9 helper 单测 + fixture 工厂**

Create `tests/test_photo3d_autopilot_jury_detection.py`:

```python
"""_jury_config_available helper 单测

spec: docs/superpowers/specs/2026-05-09-autopilot-with-jury-design.md v1.1 §6.2
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any, Callable

import pytest


# === fixture 工厂 ===

@pytest.fixture
def make_jury_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., Path]:
    """fixture 工厂：构造各种状态的 jury config 文件 + monkeypatch JURY_CONFIG_PATH 指向它

    state 枚举：
      ok / missing / corrupt / top_level_list / no_active_id / orphan_id / oserror
    """
    def _factory(state: str = "ok") -> Path:
        config_path = tmp_path / "cad_jury_config.json"

        if state == "ok":
            config_path.write_text(
                json.dumps({
                    "active_profile_id": "default",
                    "profiles": [{"id": "default", "kind": "openai_compat"}],
                }),
                encoding="utf-8",
            )
        elif state == "missing":
            pass  # 不写文件
        elif state == "corrupt":
            config_path.write_bytes(b"{not json")
        elif state == "top_level_list":
            config_path.write_text(json.dumps([{"foo": "bar"}]), encoding="utf-8")
        elif state == "no_active_id":
            config_path.write_text(
                json.dumps({"profiles": [{"id": "default"}]}),
                encoding="utf-8",
            )
        elif state == "empty_active_id":
            config_path.write_text(
                json.dumps({"active_profile_id": "", "profiles": [{"id": "default"}]}),
                encoding="utf-8",
            )
        elif state == "orphan_id":
            config_path.write_text(
                json.dumps({
                    "active_profile_id": "typo_xyz",
                    "profiles": [{"id": "default"}, {"id": "backup"}],
                }),
                encoding="utf-8",
            )
        elif state == "no_profiles":
            config_path.write_text(
                json.dumps({"active_profile_id": "default"}),
                encoding="utf-8",
            )
        elif state == "empty_profiles":
            config_path.write_text(
                json.dumps({"active_profile_id": "default", "profiles": []}),
                encoding="utf-8",
            )
        else:
            raise ValueError(f"unknown state: {state}")

        # monkeypatch 常量指向 fixture 路径
        monkeypatch.setattr("tools.photo3d_autopilot.JURY_CONFIG_PATH", config_path)
        return config_path

    return _factory


# === 9 helper 单测 ===

def test_jury_config_missing_returns_false(make_jury_config: Callable[..., Path]) -> None:
    """spec §5.1 — 文件不存在 → False"""
    make_jury_config(state="missing")
    from tools.photo3d_autopilot import _jury_config_available
    assert _jury_config_available() is False


def test_jury_config_valid_returns_true(make_jury_config: Callable[..., Path]) -> None:
    """spec §6.2 — 合法配置 → True"""
    make_jury_config(state="ok")
    from tools.photo3d_autopilot import _jury_config_available
    assert _jury_config_available() is True


def test_jury_config_corrupt_json_returns_false(make_jury_config: Callable[..., Path]) -> None:
    """spec §5.1 — 损坏 JSON → False（不抛）"""
    make_jury_config(state="corrupt")
    from tools.photo3d_autopilot import _jury_config_available
    assert _jury_config_available() is False


def test_jury_config_top_level_not_dict_returns_false(make_jury_config: Callable[..., Path]) -> None:
    """spec §5.1 — 顶层不是 dict（如 list）→ False"""
    make_jury_config(state="top_level_list")
    from tools.photo3d_autopilot import _jury_config_available
    assert _jury_config_available() is False


def test_jury_config_missing_active_profile_id(make_jury_config: Callable[..., Path]) -> None:
    """spec §5.1 — 缺 active_profile_id 字段 → False"""
    make_jury_config(state="no_active_id")
    from tools.photo3d_autopilot import _jury_config_available
    assert _jury_config_available() is False


def test_jury_config_empty_active_profile_id(make_jury_config: Callable[..., Path]) -> None:
    """spec §5.1 — active_profile_id 是空字符串 → False"""
    make_jury_config(state="empty_active_id")
    from tools.photo3d_autopilot import _jury_config_available
    assert _jury_config_available() is False


def test_jury_config_missing_profiles_list(make_jury_config: Callable[..., Path]) -> None:
    """spec §5.1 — 缺 profiles 字段 → False"""
    make_jury_config(state="no_profiles")
    from tools.photo3d_autopilot import _jury_config_available
    assert _jury_config_available() is False


def test_jury_config_empty_profiles_list(make_jury_config: Callable[..., Path]) -> None:
    """spec §5.1 — profiles 是空 list → False"""
    make_jury_config(state="empty_profiles")
    from tools.photo3d_autopilot import _jury_config_available
    assert _jury_config_available() is False


def test_jury_config_active_profile_id_not_in_profiles(make_jury_config: Callable[..., Path]) -> None:
    """spec §5.1 — typo（active_profile_id 不在 profiles[].id）→ False"""
    make_jury_config(state="orphan_id")
    from tools.photo3d_autopilot import _jury_config_available
    assert _jury_config_available() is False


def test_jury_config_oserror_silent(
    make_jury_config: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """spec §5.1 — read_text OSError → False（不抛）"""
    make_jury_config(state="ok")  # 文件存在
    # mock Path.read_text 抛 OSError
    real_read_text = Path.read_text

    def fake_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        if self.name == "cad_jury_config.json":
            raise OSError("permission denied")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)
    from tools.photo3d_autopilot import _jury_config_available
    assert _jury_config_available() is False


def test_jury_config_does_not_read_secrets() -> None:
    """spec §3.4 inv 3 — helper 实现源码不引用 api_key / base_url / model 字段名（防泄漏）"""
    from tools.photo3d_autopilot import _jury_config_available
    src = inspect.getsource(_jury_config_available)
    for forbidden in ("api_key", "base_url", "model", "cost_per_call_usd"):
        assert forbidden not in src, f"forbidden field {forbidden!r} read in _jury_config_available"
```

- [ ] **Step 1.2: 跑测试 RED**

```bash
.venv/Scripts/python.exe -m pytest tests/test_photo3d_autopilot_jury_detection.py -v
```

Expected: ImportError（_jury_config_available 未定义；JURY_CONFIG_PATH 也未定义）

- [ ] **Step 1.3: 实现常量 + helper**

修改 `tools/photo3d_autopilot.py`，在文件**顶部 imports 区**（line 11 `from tools.photo3d_provider_presets import` 之后）add-only 加：

```python
import json

# === v2.29.0 jury config 自动检测（spec §3.3 + §3.4 inv 1-3）===
JURY_CONFIG_PATH: Path = Path.home() / ".claude" / "cad_jury_config.json"


def _jury_config_available() -> bool:
    """silent boolean 探针：检测 jury config 是否存在 + 合法（spec §3.4 inv 1-3 + §4.2）

    任何失败路径返 False；不抛异常 / 不写 stderr / 不调 subprocess / 不读敏感字段。
    """
    config_path = JURY_CONFIG_PATH

    if not config_path.is_file():
        return False

    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        return False

    try:
        config = json.loads(text)
    except json.JSONDecodeError:
        return False

    if not isinstance(config, dict):
        return False

    profile_id = config.get("active_profile_id")
    if not isinstance(profile_id, str) or not profile_id:
        return False

    profiles = config.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        return False

    return any(
        isinstance(p, dict) and p.get("id") == profile_id
        for p in profiles
    )
```

注：`json` 模块如果当前文件已 import 则跳过；`Path` 应已 import（grep 验证）。

注：spec §4.2 流程图含 `Path.home()` try/except RuntimeError 分支；本实现 module-level 常量已经把 `Path.home()` 移到 import 时（一次解析）；如果 `Path.home()` 在 import 时炸 → 整个模块炸（autopilot 起不来）这不算 helper 的责任范围。spec 要求 helper 不抛；module-level 常量解析失败属于"环境根本错误"，本 PR 不处理。

- [ ] **Step 1.4: GREEN**

```bash
.venv/Scripts/python.exe -m pytest tests/test_photo3d_autopilot_jury_detection.py -v
```

Expected: 11 PASS（9 主测 + `empty_active_id` + `does_not_read_secrets`）

- [ ] **Step 1.5: ruff + mypy**

```bash
.venv/Scripts/python.exe -m ruff check tools/photo3d_autopilot.py tests/test_photo3d_autopilot_jury_detection.py
.venv/Scripts/python.exe -m mypy --strict tools/photo3d_autopilot.py
```

Expected: 全 clean（不引入新 mypy 告警）

- [ ] **Step 1.6: Commit**

```bash
git add tools/photo3d_autopilot.py tests/test_photo3d_autopilot_jury_detection.py
git commit -m "feat(autopilot): 加 _jury_config_available silent boolean 探针 + JURY_CONFIG_PATH 常量"
```

---

## Task 2: _next_action ready_for_enhancement 分支集成

**Files:**
- Modify: `tools/photo3d_autopilot.py:_next_action`（约 line 195-217 ready_for_enhancement 分支末尾）
- Modify: `tests/test_photo3d_autopilot.py`（add-only 加 6 集成测试）

- [ ] **Step 2.1: 写 6 集成测试**

在 `tests/test_photo3d_autopilot.py` 末尾追加：

```python
# === v2.29.0 A1.1: ready_for_enhancement × jury config 自动检测 ===

import json
from pathlib import Path
from typing import Any, Callable

# 注：本测试文件可能已 import pytest / json / Path；如已有 import 跳过


@pytest.fixture
def jury_config_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """fixture 工厂：在 tmp_path 内构造 jury config + monkeypatch JURY_CONFIG_PATH"""
    def _factory(state: str = "ok") -> None:
        config_path = tmp_path / "cad_jury_config.json"
        if state == "ok":
            config_path.write_text(
                json.dumps({
                    "active_profile_id": "default",
                    "profiles": [{"id": "default", "kind": "openai_compat"}],
                }),
                encoding="utf-8",
            )
        elif state == "missing":
            pass
        elif state == "corrupt":
            config_path.write_bytes(b"{not json")
        else:
            raise ValueError(f"unknown state: {state}")
        monkeypatch.setattr("tools.photo3d_autopilot.JURY_CONFIG_PATH", config_path)

    return _factory


def test_ready_for_enhancement_with_jury_config_recommends_handoff(
    jury_config_factory: Callable[..., None],
) -> None:
    """spec §6.3 — jury config 合法 → next_action.kind="run_handoff_with_jury" / argv 含 --with-jury --confirm"""
    jury_config_factory(state="ok")
    from tools.photo3d_autopilot import _next_action
    status, action = _next_action(
        subsystem="lifting_platform",
        gate_status="pass",
        accepted_baseline_run_id="20260509-120000",
        artifacts={"render_manifest": "cad/lifting_platform/.cad-spec-gen/runs/20260509-120000/render_manifest.json"},
        enhancement_summary=None,
    )
    assert status == "ready_for_enhancement"
    assert action["kind"] == "run_handoff_with_jury"
    argv = action["argv"]
    assert "photo3d-handoff" in argv
    assert "--with-jury" in argv
    assert "--confirm" in argv
    assert "--subsystem" in argv
    assert "lifting_platform" in argv


def test_ready_for_enhancement_no_jury_config_recommends_enhance(
    jury_config_factory: Callable[..., None],
) -> None:
    """spec §6.3 — jury config 缺失 → kind="run_enhancement"（v2.27.0 regression）"""
    jury_config_factory(state="missing")
    from tools.photo3d_autopilot import _next_action
    status, action = _next_action(
        subsystem="lifting_platform",
        gate_status="pass",
        accepted_baseline_run_id="20260509-120000",
        artifacts={"render_manifest": "cad/lifting_platform/.cad-spec-gen/runs/20260509-120000/render_manifest.json"},
        enhancement_summary=None,
    )
    assert status == "ready_for_enhancement"
    assert action["kind"] == "run_enhancement"
    argv = action["argv"]
    assert "enhance" in argv
    assert "--with-jury" not in argv


def test_ready_for_enhancement_invalid_jury_config_falls_back_to_enhance(
    jury_config_factory: Callable[..., None],
) -> None:
    """spec §6.3 — jury config 损坏 → fallback enhance（silent）"""
    jury_config_factory(state="corrupt")
    from tools.photo3d_autopilot import _next_action
    status, action = _next_action(
        subsystem="lifting_platform",
        gate_status="pass",
        accepted_baseline_run_id="20260509-120000",
        artifacts={"render_manifest": "cad/lifting_platform/.cad-spec-gen/runs/20260509-120000/render_manifest.json"},
        enhancement_summary=None,
    )
    assert status == "ready_for_enhancement"
    assert action["kind"] == "run_enhancement"


def test_status_remains_ready_for_enhancement_both_paths(
    jury_config_factory: Callable[..., None],
) -> None:
    """spec §3.4 inv 5 — 两路径 status 都是 ready_for_enhancement（不引入新 status）"""
    for state in ("ok", "missing"):
        jury_config_factory(state=state)
        from tools.photo3d_autopilot import _next_action
        status, _ = _next_action(
            subsystem="lifting_platform",
            gate_status="pass",
            accepted_baseline_run_id="20260509-120000",
            artifacts={"render_manifest": "cad/lifting_platform/.cad-spec-gen/runs/20260509-120000/render_manifest.json"},
            enhancement_summary=None,
        )
        assert status == "ready_for_enhancement", f"state={state}: status drifted to {status}"


def test_argv_uses_safe_cli_token_for_subsystem_with_special_chars(
    jury_config_factory: Callable[..., None],
) -> None:
    """spec §6.3 — 特殊字符 subsystem → action 不含 cli 字段（仅 argv）"""
    jury_config_factory(state="ok")
    from tools.photo3d_autopilot import _next_action
    status, action = _next_action(
        subsystem="my space",  # _safe_cli_token 应拒绝（含空格）
        gate_status="pass",
        accepted_baseline_run_id="20260509-120000",
        artifacts={"render_manifest": "cad/my space/.cad-spec-gen/runs/20260509-120000/render_manifest.json"},
        enhancement_summary=None,
    )
    assert action["kind"] == "run_handoff_with_jury"
    assert "argv" in action
    assert "cli" not in action  # _safe_cli_token False → 不带 cli 字符串


def test_other_states_not_affected_by_jury_detection(
    jury_config_factory: Callable[..., None],
) -> None:
    """spec §3.4 inv 6 + §6.3 — blocked / accept_baseline / enhancement_summary 三态不触发 jury 检测

    用 jury config 损坏，但 gate_status="blocked" 应该走 follow_action_plan 路径（不读 jury config）。
    若 helper 被误调，损坏 config 会 silent 返 False 但应留可观察痕迹（当前不可观察；本测试仅验证 status / kind 正确）。
    """
    jury_config_factory(state="corrupt")
    from tools.photo3d_autopilot import _next_action

    # blocked
    status, action = _next_action(
        subsystem="lifting_platform",
        gate_status="blocked",
        accepted_baseline_run_id="20260509-120000",
        artifacts={"action_plan": "cad/lifting_platform/.cad-spec-gen/runs/20260509-120000/ACTION_PLAN.json"},
        enhancement_summary=None,
    )
    assert status == "blocked"
    assert action["kind"] == "follow_action_plan"

    # accept_baseline
    status, action = _next_action(
        subsystem="lifting_platform",
        gate_status="pass",
        accepted_baseline_run_id=None,
        artifacts={},
        enhancement_summary=None,
    )
    assert status == "needs_baseline_acceptance"
    assert action["kind"] == "accept_baseline"

    # enhancement_summary accepted
    status, action = _next_action(
        subsystem="lifting_platform",
        gate_status="pass",
        accepted_baseline_run_id="20260509-120000",
        artifacts={},
        enhancement_summary={"delivery_status": "accepted"},
    )
    assert status == "enhancement_accepted"
    assert action["kind"] == "delivery_complete"
```

- [ ] **Step 2.2: 跑测试 RED**

```bash
.venv/Scripts/python.exe -m pytest tests/test_photo3d_autopilot.py -k "ready_for_enhancement_with_jury or ready_for_enhancement_no_jury or invalid_jury_config or status_remains or safe_cli_token or other_states_not_affected" -v
```

Expected: 部分 fail（kind="run_handoff_with_jury" 不存在；当前实现总返 kind="run_enhancement"）

- [ ] **Step 2.3: 实现 _next_action ready_for_enhancement 分支扩展**

定位 `tools/photo3d_autopilot.py:_next_action` 的 ready_for_enhancement 默认分支（约 line 200-216）。当前：

```python
    render_dir = _render_dir_from_manifest_path(artifacts.get("render_manifest"))
    if not render_dir:
        raise ValueError("Photo3D autopilot cannot recommend enhancement without render_manifest")
    argv = ["python", "cad_pipeline.py", "enhance", "--subsystem", subsystem]
    argv.extend(["--dir", render_dir])
    action = {
        "kind": "run_enhancement",
        "requires_user_confirmation": False,
        "argv": argv,
        "default_provider_preset": DEFAULT_PROVIDER_PRESET,
        "provider_presets": public_provider_presets(),
    }
    if _safe_cli_token(subsystem) and render_dir:
        action["cli"] = " ".join(argv)
    return (
        "ready_for_enhancement",
        action,
    )
```

替换为（add-only 加 jury 路径分支，原 enhance 路径保留为 else）：

```python
    render_dir = _render_dir_from_manifest_path(artifacts.get("render_manifest"))
    if not render_dir:
        raise ValueError("Photo3D autopilot cannot recommend enhancement without render_manifest")

    # v2.29.0 A1.1: jury config 已配 → 推荐 photo3d-handoff --with-jury 一条龙；否则 fallback enhance（spec §3.4 inv 6）
    if _jury_config_available():
        argv = [
            "python", "cad_pipeline.py", "photo3d-handoff",
            "--subsystem", subsystem, "--with-jury", "--confirm",
        ]
        action: dict[str, Any] = {
            "kind": "run_handoff_with_jury",
            "requires_user_confirmation": False,
            "argv": argv,
        }
        if _safe_cli_token(subsystem):
            action["cli"] = " ".join(argv)
        return ("ready_for_enhancement", action)

    # 现有 enhance 路径（v2.27.0 行为不变）
    argv = ["python", "cad_pipeline.py", "enhance", "--subsystem", subsystem]
    argv.extend(["--dir", render_dir])
    action = {
        "kind": "run_enhancement",
        "requires_user_confirmation": False,
        "argv": argv,
        "default_provider_preset": DEFAULT_PROVIDER_PRESET,
        "provider_presets": public_provider_presets(),
    }
    if _safe_cli_token(subsystem) and render_dir:
        action["cli"] = " ".join(argv)
    return (
        "ready_for_enhancement",
        action,
    )
```

注：`Any` 类型注解导入（`from typing import Any`）应已存在；如果未导入需 add。

- [ ] **Step 2.4: GREEN**

```bash
.venv/Scripts/python.exe -m pytest tests/test_photo3d_autopilot.py -k "ready_for_enhancement_with_jury or ready_for_enhancement_no_jury or invalid_jury_config or status_remains or safe_cli_token or other_states_not_affected" -v
```

Expected: 6 PASS

- [ ] **Step 2.5: 现有回归**

```bash
.venv/Scripts/python.exe -m pytest tests/test_photo3d_autopilot.py -v
```

Expected: 之前所有 + 新 6 = 全 PASS

- [ ] **Step 2.6: ruff + mypy**

```bash
.venv/Scripts/python.exe -m ruff check tools/photo3d_autopilot.py tests/test_photo3d_autopilot.py
.venv/Scripts/python.exe -m mypy --strict tools/photo3d_autopilot.py
```

- [ ] **Step 2.7: Commit**

```bash
git add tools/photo3d_autopilot.py tests/test_photo3d_autopilot.py
git commit -m "feat(autopilot): _next_action ready_for_enhancement 分支按 jury config 自动选 handoff/enhance"
```

---

## Task 3: 全量回归 + 北极星 5 gate

- [ ] **Step 3.1: 全量回归**

```bash
.venv/Scripts/python.exe -m pytest tests/ -q --tb=no
```

Expected: ≥2706 + 17（11 helper 单测 + 6 集成）= ≥2723 PASS / 0 regression

- [ ] **Step 3.2: ruff + mypy strict 全量**

```bash
.venv/Scripts/python.exe -m ruff check tools/photo3d_autopilot.py tests/test_photo3d_autopilot_jury_detection.py tests/test_photo3d_autopilot.py
.venv/Scripts/python.exe -m mypy --strict tools/photo3d_autopilot.py
```

Expected: 全 clean（本 PR 改的文件不引入新 mypy 告警；30 baseline 历史债不动）

- [ ] **Step 3.3: 北极星 5 gate 体检（人工核对）**

输出：

```
- 零配置：✓ 静默检测；未配 jury config 用户行为完全不变（v2.27.0 regression 守门 test_ready_for_enhancement_no_jury_config_recommends_enhance）
- 稳定可靠：✓ silent boolean 探针；任何失败 fallback 推荐 enhance（test_ready_for_enhancement_invalid_jury_config_falls_back_to_enhance 守门）
- 结果准确：✓ 已配 jury 用户自动获 handoff --with-jury 闭环推荐（test_ready_for_enhancement_with_jury_config_recommends_handoff 守门）
- SW 装即用：✓ 无 SW 涉及
- 傻瓜式操作：✓ autopilot → handoff 一步到一条龙；少打 3 个命令
```

- [ ] **Step 3.4: Commit（空 commit 记录验证）**

```bash
git commit --allow-empty -m "test(autopilot): A1.1 全量回归 PASS + 北极星 5 gate 体检过"
```

---

## Task 4: 文档（cad-jury-config / PROGRESS）

- [ ] **Step 4.1: 加 docs/cad-jury-config.md 段落**

在现有"通过 photo3d-handoff 一条命令跑闭环（v2.28.0+）"章节末尾追加（add-only）：

```markdown
### v2.29.0+ autopilot 自动检测 jury config

photo3d-autopilot 在 `ready_for_enhancement` 状态会自动检测 `~/.claude/cad_jury_config.json`：

- **已配 jury（合法 active_profile_id 在 profiles[].id 中）**：autopilot 推荐 `photo3d-handoff --with-jury --confirm`（一条命令跑 enhance + check + jury + review 闭环）
- **未配 jury / config 损坏**：autopilot 推荐 `enhance` 单跑命令（v2.27.0 行为；用户需手动跑后续步骤）

检测是 silent advisory（不写 stderr / 不抛异常）；handoff 自身 step 0.5 fail-fast preflight 是真守门（autopilot 检测时 config 合法但用户跑前删了 / 改坏会被 handoff 兜底报错）。

要关闭 autopilot 自动推荐 jury，删 `~/.claude/cad_jury_config.json` 或重命名（不引入 cli flag）。
```

- [ ] **Step 4.2: 加 docs/PROGRESS.md v2.29.0 入口**

在 PROGRESS.md 顶部最新 entry 之前 add-only 加：

```markdown
## v2.29.0 — 2026-05-09 photo3d-autopilot 自动检测 jury config（A1.1）

- photo3d-autopilot 静默检测 `~/.claude/cad_jury_config.json`；已配 jury 用户在 ready_for_enhancement 状态自动获得 `photo3d-handoff --with-jury --confirm` 推荐
- 未配用户行为完全不变（v2.27.0 regression 守门）
- 不引入 cli flag / 不引入新 status / 不引入新 stderr 文案
- next_action.kind 加新枚举值 `run_handoff_with_jury`（add-only schema）
- 11 helper 单测 + 6 集成测试 = 17 用例 PASS
- 全量回归 ≥2723 PASS / 0 regression
```

- [ ] **Step 4.3: Commit**

```bash
git add docs/cad-jury-config.md docs/PROGRESS.md
git commit -m "docs(autopilot): A1.1 加 autopilot 自动检测 jury config 用户文档 + PROGRESS v2.29.0 入口"
```

---

## Task 5: PR + tag v2.29.0 + GitHub Release

- [ ] **Step 5.1: push 分支**

```bash
git push -u origin feat/autopilot-with-jury
```

- [ ] **Step 5.2: 开 PR**

```bash
gh pr create --title "feat(autopilot): 自动检测 jury config + 推荐 handoff 一条龙（A1.1）" --body "$(cat <<'EOF'
## Summary

- photo3d-autopilot 静默检测 ~/.claude/cad_jury_config.json
- 已配 jury 用户：ready_for_enhancement 状态自动获得 photo3d-handoff --with-jury --confirm 推荐
- 未配用户：行为完全不变（v2.27.0 regression 守门）
- 不引入 cli flag / 不引入新 status / 不引入新 stderr 文案
- next_action.kind 加新枚举值 run_handoff_with_jury（add-only schema）

## Test plan
- [ ] CI matrix Linux + Windows 全绿
- [ ] 11 helper 单测 + 6 集成测试 PASS
- [ ] 全量回归 ≥2723 PASS / 0 regression
- [ ] mypy strict + ruff clean（本 PR 改的文件）
- [ ] 北极星 5 gate 体检过

## Spec & Plan
- spec: docs/superpowers/specs/2026-05-09-autopilot-with-jury-design.md (v1.1)
- plan: docs/superpowers/plans/2026-05-09-autopilot-with-jury.md

## 与 v2.28.0 关系

v2.28.0 已落 photo3d-handoff --with-jury 一条命令；A1.1 让 autopilot 自动引导用户进入此命令。
两个 PR 加起来：用户从"跑 autopilot 看推荐"到"跑 handoff 一条龙"全流程一步到位。

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 5.3: 等 CI 全绿**

```bash
gh pr checks
```

Expected: 所有 check pass

- [ ] **Step 5.4: squash merge + delete branch**

```bash
gh pr merge --squash --delete-branch
```

- [ ] **Step 5.5: tag v2.29.0 + GitHub Release**

```bash
git checkout main && git pull
git tag -a v2.29.0 -m "v2.29.0: photo3d-autopilot 自动检测 jury config 推荐 handoff 一条龙"
git push origin v2.29.0
gh release create v2.29.0 --title "v2.29.0 — autopilot 自动引导 jury 闭环 (A1.1)" --notes "见 docs/PROGRESS.md"
```

---

## Self-Review Checklist

实施前最后核：

**1. Spec coverage**：
- §2.1 范围 7 项 → Task 1（helper + 常量）/ Task 2（_next_action 集成）/ Task 4（文档）覆盖 ✓
- §3.4 invariants 1-10 → Task 1 helper 9 单测覆盖 inv 1-3 + inv 9-10；Task 2 集成测试覆盖 inv 4-7 ✓
- §4.1 数据流 → Task 2 实现覆盖 ✓
- §4.2 helper 内部数据流 → Task 1 实现覆盖 ✓
- §5.1 错误分类 8 行 → Task 1 helper 9 单测覆盖 ✓
- §6.2 9 helper 单测 + §6.3 6 集成测试 → Task 1 + Task 2 ✓
- §6.4 fixture 工厂 → Task 1 + Task 2 各自 fixture ✓
- §7 兼容性（cli 不变 / schema add-only / config 不变）→ Task 2 集成测试守门 ✓
- §10 DoD 10 条 → Task 3（回归 + 北极星）+ Task 5（PR + tag）✓

**2. Placeholder scan**：每个 step 含完整代码 + 命令；无 TBD/TODO ✓

**3. Type consistency**：
- `_jury_config_available()` 签名一致（无参数 → bool）跨 Task 1/2/3 ✓
- `JURY_CONFIG_PATH` 常量名一致 ✓
- `next_action.kind` 字符串值 `run_handoff_with_jury` 跨 spec / Task 2 / Task 4 一致 ✓
- `next_action.argv` 列表内容（["python", "cad_pipeline.py", "photo3d-handoff", "--subsystem", X, "--with-jury", "--confirm"]）一致 ✓
