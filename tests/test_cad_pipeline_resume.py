"""cad_pipeline.py project-guide --resume 集成测试"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
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
    assert not (tmp_path / "PROJECT_GOAL_STATE.json").exists()


def test_partial_first_call_writes_state_exit_0(tmp_path: Path) -> None:
    """spec §6.3 — 起手不全 → exit=0 + state file 含 missing_kpis"""
    result = _run_cli("--product-goal", "做升降平台", cwd=tmp_path)
    assert result.returncode == 0
    state = _read_state(tmp_path)
    assert state is not None
    assert state["raw_text"] == "做升降平台"
    assert state["subsystem_class"] == "lifting_platform"
    assert state["confirmed_kpis"] == {}
    assert "load_kg" in state["missing_kpis"]
    assert state["round"] == 1


def test_resume_single_answer_updates_state(tmp_path: Path) -> None:
    """spec §6.3 — --resume --answer load_kg=50 → state 含 load_kg / 仍缺其他"""
    _run_cli("--product-goal", "做升降平台", cwd=tmp_path)
    result = _run_cli("--resume", "--answer", "load_kg=50", cwd=tmp_path)
    assert result.returncode == 0
    state = _read_state(tmp_path)
    assert state is not None
    assert state["confirmed_kpis"]["load_kg"] == 50.0
    assert state["round"] == 2
    assert "stroke_mm" in state["missing_kpis"]
    assert "load_kg" not in state["missing_kpis"]


def test_resume_multiple_answers_accepted(tmp_path: Path) -> None:
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
    _run_cli("--product-goal", "做升降平台", cwd=tmp_path)
    result = _run_cli(
        "--resume",
        "--answer", "load_kg=50",
        "--answer", "stroke_mm=800",
        "--answer", "platform_size_mm=600x600",
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert not (tmp_path / "PROJECT_GOAL_STATE.json").exists()


def test_answer_invalid_key_exit_2_state_unchanged(tmp_path: Path) -> None:
    _run_cli("--product-goal", "做升降平台", cwd=tmp_path)
    state_before = _read_state(tmp_path)
    result = _run_cli("--resume", "--answer", "foo=bar", cwd=tmp_path)
    assert result.returncode == 2
    state_after = _read_state(tmp_path)
    if state_before is not None and state_after is not None:
        assert state_after["confirmed_kpis"] == state_before["confirmed_kpis"]
        assert state_after["round"] == state_before["round"]


def test_answer_invalid_value_exit_2_state_unchanged(tmp_path: Path) -> None:
    _run_cli("--product-goal", "做升降平台", cwd=tmp_path)
    state_before = _read_state(tmp_path)
    result = _run_cli("--resume", "--answer", "load_kg=fifty", cwd=tmp_path)
    assert result.returncode == 2
    state_after = _read_state(tmp_path)
    if state_before is not None and state_after is not None:
        assert state_after["round"] == state_before["round"]


def test_resume_without_state_exit_2(tmp_path: Path) -> None:
    result = _run_cli("--resume", "--answer", "load_kg=50", cwd=tmp_path)
    assert result.returncode == 2
    assert "PROJECT_GOAL_STATE.json" in result.stderr or "不存在" in result.stderr


def test_resume_corrupt_state_exit_2(tmp_path: Path) -> None:
    (tmp_path / "PROJECT_GOAL_STATE.json").write_bytes(b"{not json")
    result = _run_cli("--resume", "--answer", "load_kg=50", cwd=tmp_path)
    assert result.returncode == 2
    assert "解析失败" in result.stderr or "JSON" in result.stderr


def test_round_exceeds_max_exit_2(tmp_path: Path) -> None:
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
    assert "20" in result.stderr or "round" in result.stderr or "MAX_ROUND" in result.stderr


def test_resume_and_product_goal_mutually_exclusive(tmp_path: Path) -> None:
    result = _run_cli(
        "--product-goal", "做升降平台",
        "--resume",
        cwd=tmp_path,
    )
    assert result.returncode != 0
    assert "not allowed" in result.stderr.lower() or "mutually" in result.stderr.lower()


def test_state_round_increments_per_resume(tmp_path: Path) -> None:
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
    _run_cli("--product-goal", "做升降平台", cwd=tmp_path)
    result = _run_cli(
        "--resume", "--answer", "subsystem=end_effector",
        cwd=tmp_path,
    )
    assert result.returncode == 0
    state = _read_state(tmp_path)
    assert state is not None
    assert state.get("confirmed_subsystem") == "end_effector"
