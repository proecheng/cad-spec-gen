"""tools/product_goal_state.py 单元测试"""
from __future__ import annotations

import json
import time
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
    from tools.product_goal_state import read_state
    assert read_state(cwd=tmp_path) is None


def test_read_state_valid_returns_dict(tmp_path: Path) -> None:
    _state_factory(tmp_path, confirmed_kpis={"load_kg": 50})
    from tools.product_goal_state import read_state
    state = read_state(cwd=tmp_path)
    assert state is not None
    assert state["schema_version"] == 1
    assert state["confirmed_kpis"] == {"load_kg": 50}
    assert state["round"] == 1


def test_read_state_corrupt_raises_value_error(tmp_path: Path) -> None:
    (tmp_path / "PROJECT_GOAL_STATE.json").write_bytes(b"{not json")
    from tools.product_goal_state import read_state
    with pytest.raises(ValueError, match="解析失败"):
        read_state(cwd=tmp_path)


def test_read_state_unsupported_schema_version(tmp_path: Path) -> None:
    state = {"schema_version": 99, "raw_text": "..."}
    (tmp_path / "PROJECT_GOAL_STATE.json").write_text(
        json.dumps(state, ensure_ascii=False), encoding="utf-8"
    )
    from tools.product_goal_state import read_state
    with pytest.raises(ValueError, match="schema_version"):
        read_state(cwd=tmp_path)


def test_write_state_creates_file(tmp_path: Path) -> None:
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

    time.sleep(0.01)
    state2 = {**state1, "round": 2, "confirmed_kpis": {"load_kg": 50}}
    write_state(state2, cwd=tmp_path)
    written2 = read_state(cwd=tmp_path)
    assert written2 is not None
    assert written2["created_at"] == created_at_1, "created_at 应保持首次值"
    assert written2["updated_at"] != created_at_1, "updated_at 应更新"


def test_delete_state_removes_file(tmp_path: Path) -> None:
    _state_factory(tmp_path)
    from tools.product_goal_state import delete_state
    delete_state(cwd=tmp_path)
    assert not (tmp_path / "PROJECT_GOAL_STATE.json").exists()


def test_delete_state_idempotent_when_missing(tmp_path: Path) -> None:
    from tools.product_goal_state import delete_state
    delete_state(cwd=tmp_path)


def test_validate_answer_kpi_float_ok() -> None:
    from tools.product_goal_state import validate_answer
    assert validate_answer("load_kg", "50") == 50.0
    assert validate_answer("stroke_mm", "800.5") == 800.5


def test_validate_answer_kpi_size_pair_ok() -> None:
    from tools.product_goal_state import validate_answer
    assert validate_answer("platform_size_mm", "600x600") == (600.0, 600.0)
    assert validate_answer("platform_size_mm", "600x800") == (600.0, 800.0)


def test_validate_answer_subsystem_ok() -> None:
    from tools.product_goal_state import validate_answer
    assert validate_answer("subsystem", "end_effector") == "end_effector"


def test_validate_answer_unknown_key_raises() -> None:
    from tools.product_goal_state import validate_answer
    with pytest.raises(ValueError, match="不在.*KPI"):
        validate_answer("foo", "bar")


def test_validate_answer_wrong_value_type_raises() -> None:
    from tools.product_goal_state import validate_answer
    with pytest.raises(ValueError, match="解析失败"):
        validate_answer("load_kg", "fifty")


def test_validate_answer_size_pair_format_invalid_raises() -> None:
    from tools.product_goal_state import validate_answer
    with pytest.raises(ValueError, match="解析失败"):
        validate_answer("platform_size_mm", "600")
