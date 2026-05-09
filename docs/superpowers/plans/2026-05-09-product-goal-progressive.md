# product-goal 多轮渐进确认实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `cad-spec-gen --product-goal "..."` 不全时不再 reject；改为写 `./PROJECT_GOAL_STATE.json` 异步状态机；用户用 `--resume --answer key=value` 多轮渐进补全 KPI；全齐自动删 state + 进入 ready_for_cad_spec。

**Architecture:**
- 新模块 `tools/product_goal_state.py`：state schema + read/write/delete/validate_answer helper（pure read-only/write）
- `cad_pipeline.py` parser 加 `--resume` `--answer key=value`（可重复）；与 `--product-goal` argparse mutually_exclusive
- `cad_pipeline.py:cmd_project_guide` 加 --resume 路径：读 state + 合并 --answer + 调 parse_product_goal + write_project_goal_guide
- `tools/project_guide.py:write_project_goal_guide` 改：缺 KPI 时写 state；全齐时删 state；message 改为引导 --resume；exit code break-change（needs_kpi_confirmation 1→0）

**Tech Stack:** Python 3.11+ / pytest / mypy strict / ruff / json + pathlib

**spec 锚点：** `docs/superpowers/specs/2026-05-09-product-goal-progressive-design.md` v1.0

---

## File Structure

| 文件 | 改动类型 | 行数估计 | 责任 |
|---|---|---|---|
| `tools/product_goal_state.py` | create | +120 | state schema / read / write / delete / validate_answer helper |
| `cad_pipeline.py` parser | modify | +25 | 加 --resume / --answer / mutually_exclusive |
| `cad_pipeline.py:cmd_project_guide` | modify | +50 | --resume 路径分支 |
| `tools/project_guide.py:write_project_goal_guide` | modify | +30 | 缺 KPI 写 state / 全齐删 state / message 改 |
| `tools/project_guide.py:command_return_code_for_project_guide` | modify | +5 | needs_kpi_confirmation 返 0 |
| `tests/test_product_goal_state.py` | create | +200 | 14 单元测试 |
| `tests/test_cad_pipeline_resume.py` | create | +250 | 13 cli 集成测试 |
| `tests/test_project_guide_progressive.py` | create | +150 | 5 project_guide 集成测试 |
| `docs/PROGRESS.md` | modify | +15 | v2.31.0 入口 + break-change 标记 |
| `README.md` | modify | +25 | 多轮渐进示例 |

**不改文件**：`tools/product_goal_parser.py` / `tools/project_guide_dict/*.json` / jury / handoff / autopilot

---

## Task 0: 准备 + grep 守门

**Files:** verify only

- [ ] **Step 0.1: 验证分支**

```bash
git rev-parse --abbrev-ref HEAD
```

Expected: `feat/product-goal-progressive`

- [ ] **Step 0.2: grep 守门关键 fact**

```bash
# 1. write_project_goal_guide 当前签名
grep -n "def write_project_goal_guide" tools/project_guide.py
# Expected: line ~684

# 2. command_return_code_for_project_guide 当前实现
grep -n "def command_return_code_for_project_guide" tools/project_guide.py
# Expected: line ~184

# 3. _derive_goal_status_and_next_action（missing_kpis 派生）
grep -n "_derive_goal_status_and_next_action\|missing_kpis" tools/project_guide.py
# Expected: line ~832 + missing 在 _action_for_needs_kpi_confirmation

# 4. parse_product_goal 接口
grep -n "def parse_product_goal" tools/product_goal_parser.py
# Expected: line ~46；签名 (text, confirmed_subsystem, confirmed_kpis, dictionary)

# 5. KPI 类型字段
cat tools/project_guide_dict/kpi_patterns.json | python -c "import sys, json; d=json.load(sys.stdin); print(list(d.keys()))"
# Expected: load_kg / stroke_mm / platform_size_mm / rot_range_deg / switch_time_s / flange_dia_mm

# 6. cmd_project_guide 入口
grep -n "def cmd_project_guide\|product_goal" cad_pipeline.py | head -5
# Expected: line ~3700 含 args.product_goal 处理

# 7. write_json_atomic 签名（确认复用方式）
grep -n "def write_json_atomic" tools/contract_io.py
# Expected: line 9 (path, data) -> Path
```

任一不一致立即停下校准 spec。

- [ ] **Step 0.3: 检查 .gitignore 是否已忽略 PROJECT_GOAL_STATE.json**

```bash
grep -n "PROJECT_GOAL_STATE" .gitignore 2>&1 || echo "NOT IGNORED"
```

如未忽略，本 task 末尾要加。

---

## Task 1: tools/product_goal_state.py 模块

**Files:**
- Create: `tools/product_goal_state.py`
- Create: `tests/test_product_goal_state.py`

- [ ] **Step 1.1: 写 14 单元测试**

新建 `tests/test_product_goal_state.py`：

```python
"""tools/product_goal_state.py 单元测试

spec: docs/superpowers/specs/2026-05-09-product-goal-progressive-design.md v1.0 §6.2
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest


def _state_factory(
    cwd: Path,
    *,
    raw_text: str = "做升降平台",
    subsystem_class: str = "lifting_platform",
    confirmed_kpis: dict[str, Any] | None = None,
    missing_kpis: list[str] | None = None,
    round_: int = 1,
) -> Path:
    """构造一份合法 state file 到 cwd"""
    state = {
        "schema_version": 1,
        "raw_text": raw_text,
        "subsystem_class": subsystem_class,
        "subsystem_status": "implemented",
        "confirmed_subsystem": None,
        "confirmed_kpis": confirmed_kpis or {},
        "missing_kpis": missing_kpis or ["load_kg", "stroke_mm", "platform_size_mm"],
        "design_doc": None,
        "created_at": "2026-05-09T18:00:00+00:00",
        "updated_at": "2026-05-09T18:00:00+00:00",
        "round": round_,
    }
    path = cwd / "PROJECT_GOAL_STATE.json"
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def test_read_state_missing_returns_none(tmp_path: Path) -> None:
    """spec §6.2 — 文件不存在返 None"""
    from tools.product_goal_state import read_state
    assert read_state(cwd=tmp_path) is None


def test_read_state_valid_returns_dict(tmp_path: Path) -> None:
    """spec §6.2 — 合法 JSON 返 dict 含期望字段"""
    _state_factory(tmp_path, confirmed_kpis={"load_kg": 50})
    from tools.product_goal_state import read_state
    state = read_state(cwd=tmp_path)
    assert state is not None
    assert state["schema_version"] == 1
    assert state["confirmed_kpis"] == {"load_kg": 50}
    assert state["round"] == 1


def test_read_state_corrupt_raises_value_error(tmp_path: Path) -> None:
    """spec §6.2 — JSON 损坏抛 ValueError 含详细原因"""
    (tmp_path / "PROJECT_GOAL_STATE.json").write_bytes(b"{not json")
    from tools.product_goal_state import read_state
    with pytest.raises(ValueError, match="解析失败"):
        read_state(cwd=tmp_path)


def test_read_state_unsupported_schema_version(tmp_path: Path) -> None:
    """spec §3.4 inv — schema_version != 1 抛 ValueError"""
    state = {"schema_version": 99, "raw_text": "..."}
    (tmp_path / "PROJECT_GOAL_STATE.json").write_text(
        json.dumps(state, ensure_ascii=False), encoding="utf-8"
    )
    from tools.product_goal_state import read_state
    with pytest.raises(ValueError, match="schema_version"):
        read_state(cwd=tmp_path)


def test_write_state_creates_file(tmp_path: Path) -> None:
    """spec §6.2 — write_state 后文件存在含期望字段"""
    from tools.product_goal_state import write_state
    state = {
        "schema_version": 1,
        "raw_text": "做升降平台",
        "subsystem_class": "lifting_platform",
        "subsystem_status": "implemented",
        "confirmed_subsystem": None,
        "confirmed_kpis": {"load_kg": 50},
        "missing_kpis": ["stroke_mm", "platform_size_mm"],
        "design_doc": None,
        "round": 2,
    }
    path = write_state(state, cwd=tmp_path)
    assert path.is_file()
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["confirmed_kpis"] == {"load_kg": 50}
    assert written["round"] == 2
    assert "created_at" in written
    assert "updated_at" in written


def test_write_state_preserves_created_at(tmp_path: Path) -> None:
    """spec §3.4 inv 5 — 首次写 set；后续写不覆盖 created_at"""
    from tools.product_goal_state import write_state, read_state
    state1 = {
        "schema_version": 1,
        "raw_text": "做升降平台",
        "subsystem_class": "lifting_platform",
        "subsystem_status": "implemented",
        "confirmed_subsystem": None,
        "confirmed_kpis": {},
        "missing_kpis": ["load_kg"],
        "design_doc": None,
        "round": 1,
    }
    write_state(state1, cwd=tmp_path)
    written1 = read_state(cwd=tmp_path)
    assert written1 is not None
    created_at_1 = written1["created_at"]

    # 模拟时间流逝后再写
    import time
    time.sleep(0.01)
    state2 = {**state1, "round": 2, "confirmed_kpis": {"load_kg": 50}}
    write_state(state2, cwd=tmp_path)
    written2 = read_state(cwd=tmp_path)
    assert written2 is not None
    assert written2["created_at"] == created_at_1, "created_at 应保持首次值"
    assert written2["updated_at"] != created_at_1, "updated_at 应更新"


def test_delete_state_removes_file(tmp_path: Path) -> None:
    """spec §6.2 — delete_state 后文件不存在"""
    _state_factory(tmp_path)
    from tools.product_goal_state import delete_state
    delete_state(cwd=tmp_path)
    assert not (tmp_path / "PROJECT_GOAL_STATE.json").exists()


def test_delete_state_idempotent_when_missing(tmp_path: Path) -> None:
    """spec §6.2 — 文件不存在静默不抛"""
    from tools.product_goal_state import delete_state
    delete_state(cwd=tmp_path)  # 不抛异常即通过


def test_validate_answer_kpi_float_ok() -> None:
    """spec §6.2 — load_kg=50 → 50.0"""
    from tools.product_goal_state import validate_answer
    assert validate_answer("load_kg", "50") == 50.0
    assert validate_answer("stroke_mm", "800.5") == 800.5


def test_validate_answer_kpi_size_pair_ok() -> None:
    """spec §6.2 — platform_size_mm=600x600 → (600.0, 600.0)"""
    from tools.product_goal_state import validate_answer
    assert validate_answer("platform_size_mm", "600x600") == (600.0, 600.0)
    assert validate_answer("platform_size_mm", "600x800") == (600.0, 800.0)


def test_validate_answer_subsystem_ok() -> None:
    """spec §3.3 — subsystem=end_effector 直接返字符串"""
    from tools.product_goal_state import validate_answer
    assert validate_answer("subsystem", "end_effector") == "end_effector"


def test_validate_answer_unknown_key_raises() -> None:
    """spec §6.2 — foo=bar → ValueError 中文"""
    from tools.product_goal_state import validate_answer
    with pytest.raises(ValueError, match="不在.*KPI"):
        validate_answer("foo", "bar")


def test_validate_answer_wrong_value_type_raises() -> None:
    """spec §6.2 — load_kg=fifty → ValueError 中文"""
    from tools.product_goal_state import validate_answer
    with pytest.raises(ValueError, match="解析失败"):
        validate_answer("load_kg", "fifty")


def test_validate_answer_size_pair_format_invalid_raises() -> None:
    """spec §3.3 — platform_size_mm=600 (缺 x) → ValueError"""
    from tools.product_goal_state import validate_answer
    with pytest.raises(ValueError, match="解析失败"):
        validate_answer("platform_size_mm", "600")
```

- [ ] **Step 1.2: RED**

```bash
.venv/Scripts/python.exe -m pytest tests/test_product_goal_state.py -v
```

Expected: ImportError（模块未创建）

- [ ] **Step 1.3: 实现 tools/product_goal_state.py**

```python
"""PROJECT_GOAL_STATE.json schema + read/write/delete/validate_answer helper

spec: docs/superpowers/specs/2026-05-09-product-goal-progressive-design.md v1.0
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from tools.contract_io import write_json_atomic

PROJECT_GOAL_STATE_FILENAME = "PROJECT_GOAL_STATE.json"
SCHEMA_VERSION = 1
MAX_ROUND = 20

# spec §3.3 KPI_VALUE_TYPES（与 kpi_patterns.json 字段对齐；plan task 0 grep 守门验证）
KPI_VALUE_TYPES: dict[str, str] = {
    "load_kg": "float",
    "stroke_mm": "float",
    "platform_size_mm": "size_pair",
    "rot_range_deg": "float",
    "switch_time_s": "float",
    "flange_dia_mm": "float",
}

_SIZE_PAIR_PATTERN = re.compile(r"^(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)$")


def state_path(cwd: Path | None = None) -> Path:
    """返回 state file 绝对路径（cwd / PROJECT_GOAL_STATE.json）"""
    return (cwd or Path.cwd()) / PROJECT_GOAL_STATE_FILENAME


def read_state(cwd: Path | None = None) -> dict[str, Any] | None:
    """读 state file；不存在返 None；JSON 损坏 / schema_version 错抛 ValueError"""
    path = state_path(cwd)
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"./PROJECT_GOAL_STATE.json 读取失败：{exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"./PROJECT_GOAL_STATE.json 解析失败：{exc.msg}（删除后重新 --product-goal 起手）"
        ) from exc
    if not isinstance(data, dict):
        raise ValueError("./PROJECT_GOAL_STATE.json 顶层必须是 dict")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"./PROJECT_GOAL_STATE.json schema_version={data.get('schema_version')} "
            f"不识别（期望 {SCHEMA_VERSION}）"
        )
    return data


def write_state(state: Mapping[str, Any], cwd: Path | None = None) -> Path:
    """写 state file；自动加 schema_version / created_at / updated_at；返写入路径

    raises OSError if cwd 不可写
    """
    path = state_path(cwd)
    now_iso = datetime.now(timezone.utc).isoformat()

    # created_at 保留语义：首次写 set；后续写不覆盖
    existing = read_state(cwd) if path.is_file() else None
    created_at = (
        existing["created_at"]
        if existing and "created_at" in existing
        else now_iso
    )

    payload = {
        "schema_version": SCHEMA_VERSION,
        **dict(state),
        "created_at": created_at,
        "updated_at": now_iso,
    }
    write_json_atomic(path, payload)
    return path


def delete_state(cwd: Path | None = None) -> None:
    """删 state file；不存在静默"""
    path = state_path(cwd)
    if path.is_file():
        path.unlink()


def validate_answer(key: str, value: str) -> Any:
    """校验 --answer key=value：
    - key ∈ KPI_VALUE_TYPES ∪ {"subsystem"}
    - value 按类型解析（float / "AxB" → tuple / str）
    抛 ValueError 含具体原因（中文提示）
    返解析后值
    """
    key = key.strip()

    if key == "subsystem":
        if not value.strip():
            raise ValueError("--answer value 'subsystem' 不能为空")
        return value.strip()

    if key not in KPI_VALUE_TYPES:
        all_keys = sorted(set(KPI_VALUE_TYPES.keys()) | {"subsystem"})
        raise ValueError(
            f"--answer key {key!r} 不在 KPI 列表 {all_keys}"
        )

    value_type = KPI_VALUE_TYPES[key]
    if value_type == "float":
        try:
            return float(value)
        except ValueError as exc:
            raise ValueError(
                f"--answer value {value!r} 解析失败：{key} 期望 float（如 '50' / '800.5'）"
            ) from exc

    if value_type == "size_pair":
        match = _SIZE_PAIR_PATTERN.match(value.strip())
        if not match:
            raise ValueError(
                f"--answer value {value!r} 解析失败：{key} 期望 'AxB' 格式（如 '600x600' / '800x600'）"
            )
        return (float(match.group(1)), float(match.group(2)))

    raise ValueError(f"内部错误：未知 value_type {value_type!r} for key {key!r}")
```

- [ ] **Step 1.4: GREEN**

```bash
.venv/Scripts/python.exe -m pytest tests/test_product_goal_state.py -v
```

Expected: 14 PASS

- [ ] **Step 1.5: ruff + mypy**

```bash
.venv/Scripts/python.exe -m ruff check tools/product_goal_state.py tests/test_product_goal_state.py
.venv/Scripts/python.exe -m mypy --strict tools/product_goal_state.py
```

Expected: clean（不引入新告警）

- [ ] **Step 1.6: Commit**

```bash
git add tools/product_goal_state.py tests/test_product_goal_state.py
git commit -m "feat(product-goal): 加 product_goal_state 模块（schema + read/write/delete/validate_answer）"
```

---

## Task 2: cad_pipeline.py parser 加 --resume / --answer flag

**Files:**
- Modify: `cad_pipeline.py` parser 区段（grep 找 project-guide 子解析器）

- [ ] **Step 2.1: grep 定位 parser**

```bash
grep -n 'subparser_pg\|"project-guide"\|p_project_guide\|--product-goal' cad_pipeline.py | head -10
```

记下 project-guide 子解析器的注册位置。

- [ ] **Step 2.2: 加 flag**

在 project-guide 子解析器现有 `--product-goal` add_argument **之前**修改为 mutually_exclusive_group：

定位现有：
```python
p_project_guide.add_argument("--product-goal", ...)
```

替换为：
```python
group_pg = p_project_guide.add_mutually_exclusive_group()
group_pg.add_argument(
    "--product-goal",
    metavar="TEXT",
    help="自然语言产品目标（如 \"做升 50kg 的升降平台\"）；不全时进入异步多轮模式",
)
group_pg.add_argument(
    "--resume",
    action="store_true",
    help="续答多轮渐进确认；从 ./PROJECT_GOAL_STATE.json 读上次状态",
)
p_project_guide.add_argument(
    "--answer",
    action="append",
    default=[],
    metavar="KEY=VALUE",
    help="多轮渐进答案；可重复（如 --answer load_kg=50 --answer stroke_mm=800）",
)
```

注：`--answer` 不放进 mutually_exclusive_group（与 --product-goal 不冲突；有时用户也会在 --product-goal 时传 --answer 提前确认 KPI）。

- [ ] **Step 2.3: ruff（无测试只看 import 不破）**

```bash
.venv/Scripts/python.exe -m ruff check cad_pipeline.py
```

- [ ] **Step 2.4: 简单 smoke**

```bash
.venv/Scripts/python.exe cad_pipeline.py project-guide --help 2>&1 | head -30
```

Expected: 输出含 --resume / --answer。

- [ ] **Step 2.5: Commit**

```bash
git add cad_pipeline.py
git commit -m "feat(product-goal): cad_pipeline.py project-guide 加 --resume / --answer parser flag"
```

---

## Task 3: cmd_project_guide --resume 路径分支 + 集成测试

**Files:**
- Modify: `cad_pipeline.py:cmd_project_guide`（约 line 3700）
- Create: `tests/test_cad_pipeline_resume.py`

- [ ] **Step 3.1: 写 cli 集成测试**

新建 `tests/test_cad_pipeline_resume.py`：

```python
"""cad_pipeline.py project-guide --resume 集成测试

spec: docs/superpowers/specs/2026-05-09-product-goal-progressive-design.md v1.0 §6.3
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """跑 cad_pipeline.py project-guide ... 子进程；返 CompletedProcess"""
    project_root = Path(__file__).parent.parent
    cmd = [
        sys.executable, str(project_root / "cad_pipeline.py"),
        "project-guide", *args,
    ]
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )


def _read_state(cwd: Path) -> dict[str, Any] | None:
    path = cwd / "PROJECT_GOAL_STATE.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def test_full_one_shot_no_state_written(tmp_path: Path) -> None:
    """spec §6.3 — 一次说全 → ready_for_cad_spec / 无 state file"""
    result = _run_cli(
        "--product-goal", "做升 50kg 行程 800mm 平台 600x600 升降平台",
        cwd=tmp_path,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    # state file 不写
    assert not (tmp_path / "PROJECT_GOAL_STATE.json").exists()


def test_partial_first_call_writes_state_exit_0(tmp_path: Path) -> None:
    """spec §6.3 — 起手不全 → exit=0 + state file 含 missing_kpis"""
    result = _run_cli("--product-goal", "做升降平台", cwd=tmp_path)
    assert result.returncode == 0  # break-change v2.31.0：1→0
    state = _read_state(tmp_path)
    assert state is not None
    assert state["raw_text"] == "做升降平台"
    assert state["subsystem_class"] == "lifting_platform"
    assert state["confirmed_kpis"] == {}
    assert "load_kg" in state["missing_kpis"]
    assert state["round"] == 1


def test_resume_single_answer_updates_state(tmp_path: Path) -> None:
    """spec §6.3 — --resume --answer load_kg=50 → state 含 load_kg / 仍缺其他"""
    # 起手
    _run_cli("--product-goal", "做升降平台", cwd=tmp_path)
    # 续答
    result = _run_cli("--resume", "--answer", "load_kg=50", cwd=tmp_path)
    assert result.returncode == 0
    state = _read_state(tmp_path)
    assert state is not None
    assert state["confirmed_kpis"]["load_kg"] == 50.0
    assert state["round"] == 2
    assert "stroke_mm" in state["missing_kpis"]
    assert "load_kg" not in state["missing_kpis"]


def test_resume_multiple_answers_accepted(tmp_path: Path) -> None:
    """spec §6.3 — 一次答多 KPI"""
    _run_cli("--product-goal", "做升降平台", cwd=tmp_path)
    result = _run_cli(
        "--resume", "--answer", "load_kg=50", "--answer", "stroke_mm=800",
        cwd=tmp_path,
    )
    assert result.returncode == 0
    state = _read_state(tmp_path)
    assert state is not None
    assert state["confirmed_kpis"]["load_kg"] == 50.0
    assert state["confirmed_kpis"]["stroke_mm"] == 800.0


def test_resume_complete_deletes_state(tmp_path: Path) -> None:
    """spec §6.3 — 答完最后一项 → ready_for_cad_spec / state file 删"""
    _run_cli("--product-goal", "做升降平台", cwd=tmp_path)
    result = _run_cli(
        "--resume",
        "--answer", "load_kg=50",
        "--answer", "stroke_mm=800",
        "--answer", "platform_size_mm=600x600",
        cwd=tmp_path,
    )
    assert result.returncode == 0
    # state 已被删除
    assert not (tmp_path / "PROJECT_GOAL_STATE.json").exists()


def test_answer_invalid_key_exit_2_state_unchanged(tmp_path: Path) -> None:
    """spec §6.3 — --answer foo=bar → exit=2 + state 不修改"""
    _run_cli("--product-goal", "做升降平台", cwd=tmp_path)
    state_before = _read_state(tmp_path)
    result = _run_cli("--resume", "--answer", "foo=bar", cwd=tmp_path)
    assert result.returncode == 2
    state_after = _read_state(tmp_path)
    assert state_after is not None
    assert state_after["confirmed_kpis"] == state_before["confirmed_kpis"] if state_before else {}
    assert state_after["round"] == state_before["round"] if state_before else 1


def test_answer_invalid_value_exit_2_state_unchanged(tmp_path: Path) -> None:
    """spec §6.3 — --answer load_kg=fifty → exit=2 + state 不修改"""
    _run_cli("--product-goal", "做升降平台", cwd=tmp_path)
    state_before = _read_state(tmp_path)
    result = _run_cli("--resume", "--answer", "load_kg=fifty", cwd=tmp_path)
    assert result.returncode == 2
    state_after = _read_state(tmp_path)
    assert state_after is not None
    assert state_after["round"] == (state_before["round"] if state_before else 1)


def test_resume_without_state_exit_2(tmp_path: Path) -> None:
    """spec §6.3 — state 不存在 + --resume → exit=2"""
    result = _run_cli("--resume", "--answer", "load_kg=50", cwd=tmp_path)
    assert result.returncode == 2
    assert "PROJECT_GOAL_STATE.json" in result.stderr or "不存在" in result.stderr


def test_resume_corrupt_state_exit_2(tmp_path: Path) -> None:
    """spec §6.3 — state JSON 损坏 + --resume → exit=2"""
    (tmp_path / "PROJECT_GOAL_STATE.json").write_bytes(b"{not json")
    result = _run_cli("--resume", "--answer", "load_kg=50", cwd=tmp_path)
    assert result.returncode == 2
    assert "解析失败" in result.stderr or "JSON" in result.stderr


def test_round_exceeds_max_exit_2(tmp_path: Path) -> None:
    """spec §6.3 — round=21 → exit=2（死循环保护）"""
    state = {
        "schema_version": 1,
        "raw_text": "做升降平台",
        "subsystem_class": "lifting_platform",
        "subsystem_status": "implemented",
        "confirmed_subsystem": None,
        "confirmed_kpis": {},
        "missing_kpis": ["load_kg"],
        "design_doc": None,
        "round": 21,
        "created_at": "2026-05-09T18:00:00+00:00",
        "updated_at": "2026-05-09T18:00:00+00:00",
    }
    (tmp_path / "PROJECT_GOAL_STATE.json").write_text(
        json.dumps(state, ensure_ascii=False), encoding="utf-8",
    )
    result = _run_cli("--resume", "--answer", "load_kg=50", cwd=tmp_path)
    assert result.returncode == 2
    assert "20" in result.stderr or "死循环" in result.stderr or "round" in result.stderr


def test_resume_and_product_goal_mutually_exclusive(tmp_path: Path) -> None:
    """spec §3.4 inv 8 — argparse mutually_exclusive"""
    result = _run_cli(
        "--product-goal", "做升降平台",
        "--resume",
        cwd=tmp_path,
    )
    assert result.returncode != 0
    # argparse 错误信息含 "not allowed with"
    assert "not allowed" in result.stderr.lower() or "mutually" in result.stderr.lower()


def test_state_round_increments_per_resume(tmp_path: Path) -> None:
    """spec §3.4 — 每次 --resume round+=1"""
    _run_cli("--product-goal", "做升降平台", cwd=tmp_path)
    s1 = _read_state(tmp_path)
    assert s1 is not None and s1["round"] == 1

    _run_cli("--resume", "--answer", "load_kg=50", cwd=tmp_path)
    s2 = _read_state(tmp_path)
    assert s2 is not None and s2["round"] == 2

    _run_cli("--resume", "--answer", "stroke_mm=800", cwd=tmp_path)
    s3 = _read_state(tmp_path)
    assert s3 is not None and s3["round"] == 3


def test_subsystem_answer_overrides_state_class(tmp_path: Path) -> None:
    """spec §6.3 — --answer subsystem=end_effector → confirmed_subsystem 更新"""
    _run_cli("--product-goal", "做升降平台", cwd=tmp_path)
    result = _run_cli(
        "--resume", "--answer", "subsystem=end_effector",
        cwd=tmp_path,
    )
    assert result.returncode == 0
    state = _read_state(tmp_path)
    assert state is not None
    assert state.get("confirmed_subsystem") == "end_effector"
```

- [ ] **Step 3.2: RED**

```bash
.venv/Scripts/python.exe -m pytest tests/test_cad_pipeline_resume.py -v
```

Expected: 多 fail（cmd_project_guide 还没加 --resume 路径）

- [ ] **Step 3.3: 实现 cmd_project_guide --resume 分支**

定位 `cad_pipeline.py:cmd_project_guide`（grep `def cmd_project_guide`）。在函数体顶部 imports 之后、`if getattr(args, "product_goal", None) is not None:` 之前 add-only 加 --resume 分支：

```python
def cmd_project_guide(args):
    from tools.project_guide import (
        command_return_code_for_project_guide,
        write_project_entry_guide,
        write_project_goal_guide,
        write_project_guide,
    )

    # NEW v2.31.0: --resume 路径分支（异步多轮渐进）
    if getattr(args, "resume", False):
        from tools.product_goal_state import (
            MAX_ROUND, read_state, validate_answer,
        )
        try:
            state = read_state()
        except ValueError as exc:
            log.error(str(exc))
            return 2

        if state is None:
            log.error(
                "./PROJECT_GOAL_STATE.json 不存在；先跑 "
                "'cad-spec-gen project-guide --product-goal \"...\"' 起手"
            )
            return 2

        if state.get("round", 0) >= MAX_ROUND:
            log.error(
                f"已续答 {state['round']} 轮仍未完整（>= MAX_ROUND={MAX_ROUND}）；"
                f"建议检查 --answer 是否覆盖 missing_kpis: {state.get('missing_kpis', [])}"
            )
            return 2

        # 解析 --answer
        confirmed_kpis: dict[str, Any] = dict(state.get("confirmed_kpis", {}))
        confirmed_subsystem = state.get("confirmed_subsystem")
        for kv in getattr(args, "answer", []) or []:
            if "=" not in kv:
                log.error(f"--answer 需要 key=value 格式；收到 {kv!r}")
                return 2
            key, value_str = kv.split("=", 1)
            try:
                parsed = validate_answer(key.strip(), value_str.strip())
            except ValueError as exc:
                log.error(str(exc))
                return 2
            if key.strip() == "subsystem":
                confirmed_subsystem = parsed
            else:
                confirmed_kpis[key.strip()] = parsed

        # 调 write_project_goal_guide（透传 _state_round）
        report = write_project_goal_guide(
            PROJECT_ROOT,
            state["raw_text"],
            confirmed_subsystem=confirmed_subsystem,
            confirmed_kpis=confirmed_kpis,
            design_doc=state.get("design_doc"),
            output_path=getattr(args, "output", None),
            _state_round=state.get("round", 1) + 1,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        log.info("PROJECT_GUIDE: %s", report.get("ordinary_user_message"))
        return command_return_code_for_project_guide(report)

    # 现有路径（v2.25.0 不动）
    if getattr(args, "product_goal", None) is not None:
        ...
```

注：`Any` 已 import；`log` 是模块内 logger 已有；`PROJECT_ROOT` 已有。

- [ ] **Step 3.4: 改 write_project_goal_guide 签名加 _state_round（仅签名；实现待 Task 4）**

定位 `tools/project_guide.py:write_project_goal_guide`（line ~684）。在签名加 keyword-only `_state_round`：

```python
def write_project_goal_guide(
    project_root: str | Path,
    product_goal: str,
    *,
    design_doc: str | Path | None = None,
    confirmed_subsystem: str | None = None,
    confirmed_kpis: Mapping[str, float | tuple[float, float]] | None = None,
    output_path: str | Path | None = None,
    _state_round: int = 1,  # v2.31.0 内部参数；--resume 时递增
) -> dict[str, Any]:
    """..."""
    # 实现暂不读 _state_round（Task 4 加）；仅占位防 cmd_project_guide 调用 TypeError
    _ = _state_round
    ...
```

- [ ] **Step 3.5: GREEN（部分）**

```bash
.venv/Scripts/python.exe -m pytest tests/test_cad_pipeline_resume.py -v
```

Expected: 多数 PASS（state 写入由 Task 4 实现；Task 3 仅 cli 路径与错误处理）。
某些用例可能仍 fail（状态写入相关）—— 留到 Task 4 完整 GREEN。

- [ ] **Step 3.6: ruff + mypy**

```bash
.venv/Scripts/python.exe -m ruff check cad_pipeline.py tools/project_guide.py tests/test_cad_pipeline_resume.py
.venv/Scripts/python.exe -m mypy --strict cad_pipeline.py tools/project_guide.py
```

- [ ] **Step 3.7: Commit**

```bash
git add cad_pipeline.py tools/project_guide.py tests/test_cad_pipeline_resume.py
git commit -m "feat(product-goal): cmd_project_guide --resume 分支 + write_project_goal_guide 签名加 _state_round"
```

---

## Task 4: write_project_goal_guide 改造（写/删 state + message + return code）

**Files:**
- Modify: `tools/project_guide.py:write_project_goal_guide`（line ~684）
- Modify: `tools/project_guide.py:command_return_code_for_project_guide`（line ~184）
- Create: `tests/test_project_guide_progressive.py`

- [ ] **Step 4.1: 写 5 集成测试**

新建 `tests/test_project_guide_progressive.py`：

```python
"""tools/project_guide.py:write_project_goal_guide 渐进路径集成测试

spec: docs/superpowers/specs/2026-05-09-product-goal-progressive-design.md v1.0 §6.4
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


def test_write_project_goal_guide_writes_state_when_missing_kpis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """spec §6.4 — parse 缺 KPI → state file 落盘到 cwd"""
    monkeypatch.chdir(tmp_path)
    from tools.project_guide import write_project_goal_guide

    write_project_goal_guide(
        tmp_path,
        "做升降平台",
        output_path=tmp_path / "PROJECT_GUIDE.json",
    )
    state_path = tmp_path / "PROJECT_GOAL_STATE.json"
    assert state_path.is_file()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["subsystem_class"] == "lifting_platform"
    assert "load_kg" in state["missing_kpis"]


def test_write_project_goal_guide_deletes_state_when_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """spec §6.4 — parse 全齐 → state file 删（如果存在）"""
    monkeypatch.chdir(tmp_path)
    # 预先写 state（模拟前一轮结果）
    (tmp_path / "PROJECT_GOAL_STATE.json").write_text(
        json.dumps({
            "schema_version": 1,
            "raw_text": "做升降平台",
            "subsystem_class": "lifting_platform",
            "subsystem_status": "implemented",
            "confirmed_subsystem": None,
            "confirmed_kpis": {"load_kg": 50, "stroke_mm": 800},
            "missing_kpis": ["platform_size_mm"],
            "design_doc": "docs/d.md",
            "round": 3,
            "created_at": "2026-05-09T18:00:00+00:00",
            "updated_at": "2026-05-09T18:00:00+00:00",
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    from tools.project_guide import write_project_goal_guide
    write_project_goal_guide(
        tmp_path,
        "做升降平台",
        confirmed_kpis={
            "load_kg": 50,
            "stroke_mm": 800,
            "platform_size_mm": (600.0, 600.0),
        },
        design_doc="docs/d.md",
        output_path=tmp_path / "PROJECT_GUIDE.json",
        _state_round=4,
    )
    # state file 应被删（全 KPI 齐 + ready_for_cad_spec）
    assert not (tmp_path / "PROJECT_GOAL_STATE.json").exists()


def test_write_project_goal_guide_no_state_when_one_shot_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """spec §6.4 — 一次说全 + 全齐 → 不写 state"""
    monkeypatch.chdir(tmp_path)
    from tools.project_guide import write_project_goal_guide
    write_project_goal_guide(
        tmp_path,
        "做升 50kg 行程 800mm 平台 600x600 升降平台",
        design_doc="docs/d.md",
        output_path=tmp_path / "PROJECT_GUIDE.json",
    )
    # state 永不被写
    assert not (tmp_path / "PROJECT_GOAL_STATE.json").exists()


def test_command_return_code_needs_kpi_confirmation_returns_0() -> None:
    """spec §3.3 break-change — needs_kpi_confirmation 返 0（v2.25.0 是 1）"""
    from tools.project_guide import command_return_code_for_project_guide
    assert command_return_code_for_project_guide({"status": "needs_kpi_confirmation"}) == 0


def test_ordinary_user_message_contains_resume_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """spec §5.2 — needs_kpi_confirmation 文案含 --resume + --answer"""
    monkeypatch.chdir(tmp_path)
    from tools.project_guide import write_project_goal_guide
    report = write_project_goal_guide(
        tmp_path,
        "做升降平台",
        output_path=tmp_path / "PROJECT_GUIDE.json",
    )
    msg = report.get("ordinary_user_message", "")
    assert "--resume" in msg
    assert "--answer" in msg
    assert "load_kg" in msg or "stroke_mm" in msg or "platform_size_mm" in msg
```

- [ ] **Step 4.2: RED**

```bash
.venv/Scripts/python.exe -m pytest tests/test_project_guide_progressive.py -v
```

Expected: 4-5 fail（state file 写入逻辑还没加；message 文案 v2.25.0 还不含 --resume；exit code 还是 v2.25.0）

- [ ] **Step 4.3: 改 write_project_goal_guide 实现（写/删 state + message）**

定位 `tools/project_guide.py:write_project_goal_guide`（line ~684）。完整替换函数体：

```python
def write_project_goal_guide(
    project_root: str | Path,
    product_goal: str,
    *,
    design_doc: str | Path | None = None,
    confirmed_subsystem: str | None = None,
    confirmed_kpis: Mapping[str, float | tuple[float, float]] | None = None,
    output_path: str | Path | None = None,
    _state_round: int = 1,  # v2.31.0 内部参数；--resume 时递增
) -> dict[str, Any]:
    """产品目标自然语言入口；写 PROJECT_GUIDE.json + 异步多轮 state（v2.31.0+）

    与 write_project_entry_guide 平行；不动 pipeline state，纯只读。
    v2.31.0 break-change：needs_kpi_confirmation 不再 exit≠0；写 state file 进入异步模式。
    """
    from tools.product_goal_parser import parse_product_goal
    from tools.product_goal_state import write_state, delete_state

    root = Path(project_root).resolve()
    target = _project_entry_guide_target(root, output_path)

    parse_result = parse_product_goal(
        text=product_goal,
        confirmed_subsystem=confirmed_subsystem,
        confirmed_kpis=confirmed_kpis,
    )

    status, next_action = _derive_goal_status_and_next_action(
        parse_result, design_doc, root
    )

    # v2.31.0: 缺 KPI / ready_for_cad_spec 决定写/删 state file
    missing_kpis: list[str] = []
    if status == "needs_kpi_confirmation":
        # 从 next_action.missing_kpis 派生（_action_for_needs_kpi_confirmation 已填）
        missing_kpis = list(next_action.get("missing_kpis", []))

    if status == "needs_kpi_confirmation" and missing_kpis:
        # 写 state file（cwd 路径）
        write_state({
            "raw_text": parse_result.raw_text,
            "subsystem_class": parse_result.subsystem_class,
            "subsystem_status": parse_result.subsystem_status,
            "confirmed_subsystem": confirmed_subsystem,
            "confirmed_kpis": dict(confirmed_kpis or {}),
            "missing_kpis": missing_kpis,
            "design_doc": str(design_doc) if design_doc else None,
            "round": _state_round,
        })
        # 改 ordinary_user_message：引导 --resume
        ordinary_message = _ordinary_user_message_for_progressive(
            parse_result.subsystem_class, missing_kpis,
            already_confirmed=dict(confirmed_kpis or {}),
        )
    elif status == "ready_for_cad_spec":
        # 全 KPI 齐 → 删 state file（如果存在）
        delete_state()
        ordinary_message = _ordinary_user_message_for_goal(status)
    else:
        ordinary_message = _ordinary_user_message_for_goal(status)

    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entry_mode": "product_goal",
        "status": status,
        "ordinary_user_message": ordinary_message,
        "mutates_pipeline_state": False,
        "does_not_scan_directories": True,
        "product_goal": _serialize_parse_result(parse_result),
        "next_action": next_action,
        "artifacts": {
            "project_guide": project_relative(target, root),
        },
    }

    write_json_atomic(target, report)
    return report


def _ordinary_user_message_for_progressive(
    subsystem_class: str | None,
    missing_kpis: list[str],
    already_confirmed: Mapping[str, Any],
) -> str:
    """v2.31.0 多轮渐进 needs_kpi_confirmation 文案（含 --resume hint）"""
    subsystem_label = subsystem_class or "(未识别)"
    confirmed_lines = ""
    if already_confirmed:
        confirmed_str = ", ".join(f"{k}={v}" for k, v in sorted(already_confirmed.items()))
        confirmed_lines = f"\n  已记录：{confirmed_str}"

    first_missing = missing_kpis[0] if missing_kpis else "<KEY>"
    missing_str = " / ".join(missing_kpis)
    return (
        f"已识别为 {subsystem_label}。还缺 KPI：{missing_str}。{confirmed_lines}\n"
        f"  下一步答任一项：cad-spec-gen project-guide --resume --answer {first_missing}=<值>\n"
        f"  状态已记到 ./PROJECT_GOAL_STATE.json；可断点续答"
    )
```

- [ ] **Step 4.4: 改 command_return_code_for_project_guide**

定位 `tools/project_guide.py:command_return_code_for_project_guide`（line ~184）。改实现：

当前可能：
```python
def command_return_code_for_project_guide(report: dict[str, Any]) -> int:
    status = report.get("status")
    if status == "ready_for_cad_spec":
        return 0
    return 1
```

改为（v2.31.0 break-change：把 needs_kpi_confirmation 也归 0）：

```python
def command_return_code_for_project_guide(report: dict[str, Any]) -> int:
    status = report.get("status")
    # v2.31.0 break-change：needs_kpi_confirmation 改为 0（异步多轮模式正常状态）
    if status in {
        "ready_for_cad_spec",
        "needs_kpi_confirmation",  # NEW v2.31.0
        "needs_subsystem_confirmation",
        "needs_design_doc",
        "needs_product_goal",
        "not_yet_implemented",
        "unknown_subsystem",
    }:
        return 0
    return 1
```

注：实际 v2.25.0 已有的某些 status 可能已是 0；plan task 0 grep 守门核对原行为；不破坏 v2.25.0 测试。

- [ ] **Step 4.5: GREEN**

```bash
.venv/Scripts/python.exe -m pytest tests/test_project_guide_progressive.py tests/test_cad_pipeline_resume.py -v
```

Expected: 全部 PASS（5 progressive + 13 resume = 18）

- [ ] **Step 4.6: 现有 v2.25.0 测试回归**

```bash
.venv/Scripts/python.exe -m pytest tests/ -k "product_goal or project_guide" -v
```

Expected: 现有用例全 PASS；如有 v2.25.0 老用例期望 needs_kpi_confirmation exit=1，现需期望 0（**break-change 守门**：如有老用例需迁移）。

- [ ] **Step 4.7: ruff + mypy**

```bash
.venv/Scripts/python.exe -m ruff check tools/project_guide.py tests/test_project_guide_progressive.py
.venv/Scripts/python.exe -m mypy --strict tools/project_guide.py
```

- [ ] **Step 4.8: Commit**

```bash
git add tools/project_guide.py tests/test_project_guide_progressive.py
git commit -m "feat(product-goal): write_project_goal_guide 改造（写/删 state / message / break-change exit code）"
```

---

## Task 5: 全量回归 + break-change 守门 + 北极星 5 gate

- [ ] **Step 5.1: 全量回归**

```bash
.venv/Scripts/python.exe -m pytest tests/ -q --tb=no
```

Expected: ≥2725（v2.30.0 基线）+ 32（14 单元 + 13 cli + 5 progressive）= ≥2757 PASS / 0 regression

如有 v2.25.0 老用例 fail（期望 needs_kpi_confirmation exit=1）→ 迁移到期望 0 + 在 commit 信中标记。

- [ ] **Step 5.2: ruff + mypy 全量**

```bash
.venv/Scripts/python.exe -m ruff check tools/product_goal_state.py tools/project_guide.py cad_pipeline.py tests/test_product_goal_state.py tests/test_cad_pipeline_resume.py tests/test_project_guide_progressive.py
.venv/Scripts/python.exe -m mypy --strict tools/product_goal_state.py tools/project_guide.py
```

Expected: 本 PR 改的文件全 clean（baseline 历史债不动）

- [ ] **Step 5.3: break-change 文档化**

确认本 PR 在 commit 信、spec、PROGRESS、README 都明确标记 needs_kpi_confirmation exit code 1→0。

- [ ] **Step 5.4: 北极星 5 gate 体检**

```
- 零配置 ✓ state 写 cwd；不引入 home dir 配置
- 稳定可靠 ✓ MAX_ROUND=20 防死循环；错误路径不污染 state；atomic write
- 结果准确 ✓ parse_product_goal 接口完全复用；--answer 严格 KPI schema 校验
- SW 装即用 ✓ 无 SW 涉及
- 傻瓜式操作 ✓ 不必一次说全；中文文案引导每一步
```

- [ ] **Step 5.5: Commit（空 commit 记录验证）**

```bash
git commit --allow-empty -m "test(product-goal): 全量回归 PASS + break-change 守门 + 北极星 5 gate 体检过

- pytest tests/: ≥2757 passed / 0 regression（v2.30.0 基线 2725 + 32 新加）
- ruff check 本 PR 改的 6 文件: All checks passed
- mypy --strict 本 PR 改的文件: 0 新增（baseline 历史债不动）

break-change：needs_kpi_confirmation exit code 1→0（异步多轮模式正常状态）
spec / PROGRESS / README 已标记 + 迁移示例

北极星 5 gate 全过：零配置 ✓ / 稳定可靠 ✓ / 结果准确 ✓ / SW 装即用 ✓ / 傻瓜式 ✓"
```

---

## Task 6: 文档（PROGRESS + README）

- [ ] **Step 6.1: 改 docs/PROGRESS.md 加 v2.31.0**

```bash
grep -n "v2.30.0\|^## v2" docs/PROGRESS.md | head -3
```

在最新 entry 之前 add-only 加：

```markdown
## v2.31.0 — 2026-05-09 product-goal 多轮渐进确认（Phase 1 入口前移 — A）

- `cad-spec-gen project-guide --product-goal "..."` 不全时不再 reject；写 `./PROJECT_GOAL_STATE.json` 异步状态机；用户用 `--resume --answer key=value` 多轮渐进补全 KPI
- 全 KPI 齐 → 自动删 state + ready_for_cad_spec
- `--answer` 可重复（一次答多 KPI）；严格 schema 校验（key ∈ KPI 列表 / value 类型对）
- 死循环保护 MAX_ROUND=20
- 14 单元测试 + 13 cli 集成测试 + 5 project_guide 集成测试 = 32 用例 PASS
- 全量回归 ≥2757 PASS / 0 regression（v2.30.0 基线 2725 + 32 新加）

**break-change**：v2.25.0 needs_kpi_confirmation 路径 exit code 由非 0 → 0（异步多轮模式正常状态）。CI / 脚本如依赖 exit code 判断"输入不全"需迁移到读 status 字段：
```bash
# v2.31.0 新脚本：
status=$(jq -r .status PROJECT_GUIDE.json)
if [ "$status" = "ready_for_cad_spec" ]; then echo OK; fi
```
```

- [ ] **Step 6.2: 改 README.md 加多轮渐进示例**

定位 README.md 现有 `--product-goal` 用法段（grep `product-goal`）。在末尾或合适位置 add-only 加：

```markdown
### 多轮渐进确认（v2.31.0+）

不必一次说全 KPI；起手只说大方向，系统主动追问：

```bash
# 第一步：起手（不全也 ok）
$ python cad_pipeline.py project-guide --product-goal "做升降平台"
# → status=needs_kpi_confirmation；状态已记到 ./PROJECT_GOAL_STATE.json
# → 提示：cad-spec-gen project-guide --resume --answer load_kg=50

# 第二步：续答任一项（可重复）
$ python cad_pipeline.py project-guide --resume --answer load_kg=50
$ python cad_pipeline.py project-guide --resume --answer stroke_mm=800
$ python cad_pipeline.py project-guide --resume --answer platform_size_mm=600x600

# 全齐自动删 state + ready_for_cad_spec
```

也可一次答多个 KPI：
```bash
$ python cad_pipeline.py project-guide --resume --answer load_kg=50 --answer stroke_mm=800
```

`./PROJECT_GOAL_STATE.json` 是 project-local 状态文件（建议加 .gitignore）。
```

- [ ] **Step 6.3: 加 .gitignore（如未忽略）**

```bash
grep -n "PROJECT_GOAL_STATE" .gitignore 2>&1 | head -3
```

如未忽略，在 .gitignore 末尾加：
```
PROJECT_GOAL_STATE.json
```

- [ ] **Step 6.4: Commit**

```bash
git add docs/PROGRESS.md README.md .gitignore
git commit -m "docs(product-goal): A 加多轮渐进示例 + PROGRESS v2.31.0 入口 + .gitignore"
```

---

## Task 7: PR + tag v2.31.0 + Release

- [ ] **Step 7.1: push 分支**

```bash
git push -u origin feat/product-goal-progressive
```

- [ ] **Step 7.2: 开 PR**

```bash
gh pr create --title "feat(product-goal): 多轮渐进确认（Phase 1 入口前移 — A）" --body "$(cat <<'EOF'
## Summary

- cad-spec-gen project-guide --product-goal "..." 不全时不再 reject
- 写 ./PROJECT_GOAL_STATE.json 异步状态机
- --resume --answer key=value 多轮渐进补全 KPI；可重复
- 全齐自动删 state + ready_for_cad_spec
- 死循环保护 MAX_ROUND=20

## Break-change

v2.25.0 needs_kpi_confirmation 路径 exit code 由非 0 → 0（异步多轮模式正常状态）
PROGRESS / README / spec 已标记 + 迁移示例

## 不变

- parse_product_goal 公开 API 完全保持
- 19 类子系统词典 / 6 KPI patterns 不动
- jury / handoff / autopilot 0 改动
- PROJECT_GUIDE.json schema_version 不升

## Test plan

- [x] 14 单元测试（state helper）
- [x] 13 cli 集成测试（--resume 完整流程 + 错误路径）
- [x] 5 project_guide 集成测试（write_state / delete_state / message）
- [x] 全量回归 ≥2757 PASS / 0 regression（v2.30.0 基线 2725 + 32 新加）
- [x] mypy strict + ruff clean（本 PR 改的 6 文件）
- [x] 北极星 5 gate 体检过
- [ ] CI matrix Linux + Windows 全绿（待 CI 跑）

## Spec & Plan

- spec: docs/superpowers/specs/2026-05-09-product-goal-progressive-design.md (v1.0)
- plan: docs/superpowers/plans/2026-05-09-product-goal-progressive.md

## 工程方法学

- spec brainstorm 4 决策点收敛（scope / 交互模式 / 状态文件位置 / cli 入口语义）
- spec self-review 无 placeholder
- plan 7 task TDD 节奏
- subagent-driven 实施

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 7.3: 等 CI 全绿**

```bash
gh pr checks
```

Expected: 8/8 pass

- [ ] **Step 7.4: squash merge + delete branch**

```bash
gh pr merge --squash --delete-branch
```

- [ ] **Step 7.5: tag v2.31.0 + Release**

```bash
git checkout main && git pull
git tag -a v2.31.0 -m "v2.31.0: product-goal 多轮渐进确认（Phase 1 入口前移 — A）"
git push origin v2.31.0
gh release create v2.31.0 --title "v2.31.0 — product-goal 多轮渐进确认 (Phase 1 A)" --notes "见 docs/PROGRESS.md"
```

---

## Self-Review Checklist

**1. Spec coverage**：
- §2.1 范围 7 项 → Task 1（state helper）/ Task 2（parser）/ Task 3（cmd 分支）/ Task 4（write_project_goal_guide 改造）/ Task 5（回归）/ Task 6（文档）/ Task 7（PR）覆盖 ✓
- §3.4 invariants 1-10 → Task 1 单测覆盖 inv 1-3 / inv 9-10；Task 3-4 集成测试覆盖 inv 4-8 ✓
- §4.1 PROJECT_GOAL_STATE.json schema → Task 1 实现 ✓
- §4.2 完整流程（一次说全 / 渐进 3 轮 / 边界）→ Task 3 + Task 4 集成测试覆盖 ✓
- §5.1 错误分类表 8 行 → Task 3 集成测试覆盖（exit=2 + state 不修改）✓
- §6 32 用例 → Task 1 + Task 3 + Task 4 ✓
- §7 兼容性 → Task 4（break-change）+ Task 6（文档迁移示例）✓
- §10 DoD 10 条 → Task 5（回归）+ Task 7（PR + tag）✓

**2. Placeholder scan**：每 step 含完整代码 + 命令；无 TBD/TODO ✓

**3. Type consistency**：
- `state_path()` / `read_state()` / `write_state()` / `delete_state()` / `validate_answer()` 跨 Task 1/3/4 一致 ✓
- `KPI_VALUE_TYPES` 字段 `load_kg/stroke_mm/platform_size_mm/rot_range_deg/switch_time_s/flange_dia_mm` 与 spec §3.3 / kpi_patterns.json 一致 ✓
- `_state_round` keyword-only int 参数跨 Task 3/4 一致 ✓
- PROJECT_GOAL_STATE.json schema 字段名跨 spec / Task 1 / Task 4 一致 ✓
