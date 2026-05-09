"""photo3d-handoff --with-jury / --no-strict-jury 集成测试

spec: docs/superpowers/specs/2026-05-09-photo3d-jury-v2-handoff-integration-design.md v1.4
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable

import pytest


# v1.4 §6.0.5 — 新文件顶部 module-scope autouse 复制 jury kill switch
@pytest.fixture(autouse=True)
def _disable_llm_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAD_JURY_DISABLE_LLM", "1")


# === H1 / H1b / H1c 回归 + golden snapshot ===

@pytest.mark.regression
def test_h1_no_with_jury_golden_snapshot() -> None:
    """H1 — 不带 --with-jury 路径：v2.27.0 基线 fixture 不应有 jury_* 字段"""
    golden = json.loads(
        Path("tests/fixtures/photo3d_handoff_v2_27_0.json").read_text(encoding="utf-8")
    )
    assert "jury_handoff_status" not in golden, (
        "v2.27.0 基线不应有 jury_* 字段（@regression）"
    )
    assert "jury_status" not in golden
    assert "review_status" not in golden
    assert "enhance_review_path" not in golden
    assert "jury_estimated_usd" not in golden
    assert "jury_actual_usd" not in golden
    assert "jury_raw_exit" not in golden
    assert "review_raw_exit" not in golden
    # 同时守门 v2.27.0 字段集存在
    expected_keys = {
        "artifacts",
        "confirmed",
        "executed_action",
        "followup_action",
        "generated_at",
        "manual_action",
        "ordinary_user_message",
        "post_handoff_photo3d_run",
        "run_id",
        "schema_version",
        "selected_action",
        "source",
        "source_report",
        "status",
        "subsystem",
    }
    assert set(golden.keys()) == expected_keys, (
        f"golden snapshot keyset 漂移: {set(golden.keys()) ^ expected_keys}"
    )


def test_run_photo3d_handoff_accepts_with_jury_kwarg() -> None:
    """spec §3.2 — run_photo3d_handoff 签名 add-only 加 with_jury / no_strict_jury 参数"""
    import inspect

    from tools.photo3d_handoff import run_photo3d_handoff

    sig = inspect.signature(run_photo3d_handoff)
    assert "with_jury" in sig.parameters
    assert "no_strict_jury" in sig.parameters
    # 都是 keyword-only with default False
    assert sig.parameters["with_jury"].default is False
    assert sig.parameters["no_strict_jury"].default is False
    assert sig.parameters["with_jury"].kind == inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["no_strict_jury"].kind == inspect.Parameter.KEYWORD_ONLY


def test_clamp_review_exit_mapping() -> None:
    """spec §3.3.1 + §6.2 — clamp_review_exit 映射钉死"""
    from tools.photo3d_handoff import clamp_review_exit
    assert clamp_review_exit(0) == 0
    assert clamp_review_exit(1) == 20
    assert clamp_review_exit(2) == 21
    assert clamp_review_exit(3) == 22
    assert clamp_review_exit(4) == 23
    assert clamp_review_exit(137) == 23
    assert clamp_review_exit(-1) == 23


def test_validate_run_id_format_rejects_traversal() -> None:
    """spec §3.4 inv 10 + §6.2 — run_id 格式正则守门"""
    from tools.photo3d_handoff import validate_run_id_format
    assert validate_run_id_format("20260509-123456") is True
    assert validate_run_id_format("run_001") is True
    assert validate_run_id_format("a") is True
    assert validate_run_id_format("../etc/passwd") is False
    assert validate_run_id_format("..\\windows\\system32") is False
    assert validate_run_id_format("") is False
    assert validate_run_id_format("a" * 65) is False
    assert validate_run_id_format("run id") is False
    assert validate_run_id_format("run/id") is False


# === fake_run_factory（spec §6.0.1）===

@pytest.fixture
def fake_run_factory(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Any]:
    """按调用顺序 dispatch fake subprocess.run 行为；
    behaviors 列表对应预期调用：
      0: enhance / 1: enhance-check / 2: jury --dry-run / 3: jury 实跑 / 4: enhance-review
    """
    def _install(behaviors: list[Any]) -> Any:
        call_log: list[dict[str, Any]] = []
        idx = [0]

        def fake_run(argv: list[str], *, shell: bool = False, capture_output: bool = True,
                     text: bool = True, timeout: int | None = None,
                     env: dict[str, str] | None = None, encoding: str | None = None,
                     creationflags: int = 0, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            assert isinstance(argv, list), f"subprocess.run must be argv list (inv 11), got {type(argv)}"
            assert shell is False, "subprocess.run shell=False (inv 11)"
            # 不主动注入凭据（inv 3）
            if env is not None:
                for forbidden in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
                    assert env.get(forbidden) == os.environ.get(forbidden), (
                        f"handoff must not actively set {forbidden} (inv 3)"
                    )
            call_log.append({"argv": argv, "shell": shell, "env": env, "timeout": timeout})
            current = idx[0]
            idx[0] += 1
            assert current < len(behaviors), f"unexpected subprocess.run call #{current}: {argv}"
            entry = behaviors[current]
            if callable(entry):
                result: subprocess.CompletedProcess[str] = entry(argv)
                return result
            assert isinstance(entry, subprocess.CompletedProcess)
            return entry

        fake_run.call_log = call_log  # type: ignore[attr-defined]
        fake_run.call_count = lambda: idx[0]  # type: ignore[attr-defined]
        monkeypatch.setattr("tools.photo3d_handoff.subprocess.run", fake_run)
        return fake_run

    return _install


# === make_jury_run_dir（spec §6.0.3 review_input 三态工厂）===

@pytest.fixture
def make_jury_run_dir(tmp_path: Path) -> Callable[..., Path]:
    def _factory(*, run_id: str = "20260509-123456",
                 review_input_state: str = "ok",
                 subsystem: str = "lifting_platform",
                 jury_status: str = "accepted") -> Path:
        run_dir = tmp_path / "cad" / subsystem / ".cad-spec-gen" / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        # PHOTO3D_JURY_REPORT.json
        actual_run_id = run_id if review_input_state != "traversal" else "../etc/passwd"
        (run_dir / "PHOTO3D_JURY_REPORT.json").write_text(
            json.dumps({
                "schema_version": 1,
                "subsystem": subsystem,
                "run_id": actual_run_id,
                "status": jury_status,
                "jury_meta": {"actual_cost_usd": 0.04, "estimated_cost_usd": 0.04},
                "views": [],
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        # jury_review_input.json 三态
        rip = run_dir / "jury_review_input.json"
        if review_input_state == "ok":
            rip.write_text(json.dumps({"schema_version": 1, "views": []}, ensure_ascii=False), encoding="utf-8")
        elif review_input_state == "missing":
            pass
        elif review_input_state == "corrupt":
            rip.write_bytes(b"{not json")
        elif review_input_state == "traversal":
            pass
        else:
            raise ValueError(f"unknown review_input_state: {review_input_state}")
        return run_dir
    return _factory


# === fake_enhancement_report（spec §6.0.4 最小可跑字段集）===

@pytest.fixture
def fake_enhancement_report() -> dict[str, Any]:
    """ENHANCEMENT_REPORT.json 最小可被 jury Layer 0 + cost.py 接受的字段集
    Task 0 grep 校准：input_evidence_binding 校验 'view'（视角名，唯一）+ 'enhanced_image'（路径）
    """
    return {
        "schema_version": 1,
        "subsystem": "lifting_platform",
        "run_id": "20260509-123456",
        "delivery_status": "accepted",
        "quality_summary": {},
        "views": [
            {"view": f"view{i}", "enhanced_image": f"img{i}.jpg", "edge_similarity": 0.9}
            for i in range(4)
        ],
    }


# === fake CompletedProcess builder ===

def cp(returncode: int, *, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["fake"], returncode=returncode, stdout=stdout, stderr=stderr)
