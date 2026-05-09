"""photo3d-handoff --with-jury / --no-strict-jury 集成测试

spec: docs/superpowers/specs/2026-05-09-photo3d-jury-v2-handoff-integration-design.md v1.4
"""
from __future__ import annotations

import json
import os
import subprocess
from contextlib import contextmanager
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


# === Task 5: H20 / H21 ===


def _fake_acquire_lock_ok(lock_path: Path) -> Any:
    """fake context manager that does nothing (i.e., lock acquired ok)"""
    @contextmanager
    def _ctx() -> Any:
        yield
    return _ctx()


# === H20: fail-fast jury config 缺失 ===

def test_h20_preflight_jury_config_missing(
    fake_run_factory: Callable[..., Any],
    make_jury_run_dir: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H20 — jury config 缺失：handoff exit=2 + 不调 enhance"""
    run_dir = make_jury_run_dir()
    # tmp/cad/<sub>/.cad-spec-gen/runs/<id> -> tmp/
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    # mock acquire_lock 直接 ok
    monkeypatch.setattr(
        "tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False
    )
    # mock subprocess: 仅期望 1 次调用（jury --dry-run preflight）返 exit=2
    fake_run = fake_run_factory([cp(2, stderr="✗ jury config 不存在")])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root,
        subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=False,
    )
    assert result["jury_handoff_status"] == "preflight_config_missing"
    assert result["exit_code"] == 2
    # 仅 1 次 subprocess 调用（preflight）；不跑实跑 / review
    assert fake_run.call_count() == 1


# === H21: handoff 自身 .handoff.lock busy ===

def test_h21_handoff_lock_busy(
    fake_run_factory: Callable[..., Any],
    make_jury_run_dir: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H21 — 同 subsystem 已有 handoff 持锁：exit=24 + 不调 enhance"""
    run_dir = make_jury_run_dir()
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    # mock acquire_lock 抛 LockBusy
    from tools._file_lock import LockBusy

    def fake_acquire_lock(lock_path: Path) -> Any:
        raise LockBusy(lock_path.name, 12345)

    monkeypatch.setattr(
        "tools.photo3d_handoff.acquire_lock", fake_acquire_lock, raising=False
    )
    fake_run = fake_run_factory([])  # 0 次调用预期
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root,
        subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=False,
    )
    assert result["jury_handoff_status"] == "handoff_lock_busy"
    assert result["exit_code"] == 24
    assert fake_run.call_count() == 0


# === Task 6: H10 / H14 / H9a / H9b ===

# H10: cost over budget
def test_h10_jury_cost_over_budget(
    fake_run_factory: Callable[..., Any],
    make_jury_run_dir: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H10 — jury dry-run cost > budget：exit=3 + jury_estimated_usd 字段 + 不调后续 step"""
    run_dir = make_jury_run_dir()
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run = fake_run_factory([
        cp(3, stdout="[dry-run] estimated=0.04 USD, allowed=False\n", stderr=""),
    ])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root,
        subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=False,
    )
    assert result["jury_handoff_status"] == "cost_over_budget"
    assert result["jury_estimated_usd"] == 0.04
    assert result["exit_code"] == 3
    assert fake_run.call_count() == 1


# H14: stderr 含中文估价文案
def test_h14_estimate_stderr_chinese(
    fake_run_factory: Callable[..., Any],
    make_jury_run_dir: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """H14 — H10 同测：handoff 自打中文 stderr 含 'jury 预估' + 'budget'"""
    run_dir = make_jury_run_dir()
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run_factory([cp(3, stdout="[dry-run] estimated=0.04 USD, allowed=False\n", stderr="")])
    from tools.photo3d_handoff import _run_jury_followup
    _run_jury_followup(
        project_root=project_root,
        subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=False,
    )
    captured = capsys.readouterr()
    # spec §5.2 模板渲染（handoff_jury_cost_over_budget）
    assert "jury 预估 0.04 USD" in captured.err
    assert "budget" in captured.err


# H9a: jury config 错 strict
def test_h9a_jury_config_error_strict(
    fake_run_factory: Callable[..., Any],
    make_jury_run_dir: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H9a — jury preflight exit=2 (config 错) + strict：透传 exit=2 + 不调后续 step"""
    run_dir = make_jury_run_dir()
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run = fake_run_factory([cp(2, stderr="✗ jury 配置错")])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root,
        subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=False,
    )
    assert result["jury_handoff_status"] == "preflight_config_missing"
    assert result["exit_code"] == 2
    assert fake_run.call_count() == 1


# H9b: jury config 错 no-strict（验证工具故障类不可降级；spec inv 5）
def test_h9b_jury_config_error_no_strict(
    fake_run_factory: Callable[..., Any],
    make_jury_run_dir: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H9b — jury preflight exit=2 (config 错) + no-strict：仍 exit=2（工具故障类 no-strict 不可降级）"""
    run_dir = make_jury_run_dir()
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run = fake_run_factory([cp(2, stderr="")])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root,
        subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=True,  # 关键：no-strict 不能降级工具故障
    )
    assert result["jury_handoff_status"] == "preflight_config_missing"
    assert result["exit_code"] == 2  # 仍阻断
    assert fake_run.call_count() == 1


# === Task 7: H2 jury accepted 主路径 ===

def test_h2_accepted_review_ok(
    fake_run_factory: Callable[..., Any],
    make_jury_run_dir: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H2 — jury accepted (jury exit=0 status='accepted') + review ok：
    exit=0 + jury_handoff_status='accepted' + jury_actual_usd float + 3 次 subprocess"""
    run_dir = make_jury_run_dir(jury_status="accepted", review_input_state="ok")
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run = fake_run_factory([
        cp(0, stdout="[dry-run] estimated=0.04 USD, allowed=True\n"),  # preflight
        cp(0, stdout="", stderr=""),  # jury 实跑（写 PHOTO3D_JURY_REPORT.json by fixture）
        cp(0, stdout="", stderr=""),  # enhance-review
    ])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root,
        subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=False,
    )
    assert result["jury_handoff_status"] == "accepted"
    assert result["jury_status"] == "accepted"
    assert isinstance(result["jury_actual_usd"], float)
    assert result["jury_actual_usd"] == pytest.approx(0.04)  # fixture jury_meta.actual_cost_usd
    assert result["review_status"] == "ok"
    assert result["enhance_review_path"] is not None
    assert result["exit_code"] == 0
    assert fake_run.call_count() == 3


# === Task 8: H3-H6 业务降级（preview / needs_review × strict / no-strict）===

def test_h3_jury_preview_strict(
    fake_run_factory: Callable[..., Any],
    make_jury_run_dir: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H3 — jury preview + strict：exit=10 + jury_handoff_status='preview_blocked_by_strict' + 不调 review"""
    run_dir = make_jury_run_dir(jury_status="preview")
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run = fake_run_factory([
        cp(0, stdout="[dry-run] estimated=0.04 USD\n"),  # preflight
        cp(0),  # jury 实跑（fixture 写 status=preview）
    ])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root, subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=False,
    )
    assert result["jury_handoff_status"] == "preview_blocked_by_strict"
    assert result["exit_code"] == 10
    assert result["review_status"] is None  # 不调 review
    assert fake_run.call_count() == 2  # preflight + 实跑


def test_h4_jury_preview_no_strict(
    fake_run_factory: Callable[..., Any],
    make_jury_run_dir: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H4 — jury preview + no-strict：exit=0 + jury_handoff_status='preview_warning'"""
    run_dir = make_jury_run_dir(jury_status="preview")
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run = fake_run_factory([cp(0, stdout="[dry-run] estimated=0.04 USD\n"), cp(0)])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root, subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=True,
    )
    assert result["jury_handoff_status"] == "preview_warning"
    assert result["exit_code"] == 0
    assert result["review_status"] is None
    assert fake_run.call_count() == 2


def test_h5_jury_needs_review_strict(
    fake_run_factory: Callable[..., Any],
    make_jury_run_dir: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H5 — jury needs_review + strict：exit=11"""
    run_dir = make_jury_run_dir(jury_status="needs_review")
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run = fake_run_factory([cp(0, stdout="[dry-run] estimated=0.04 USD\n"), cp(0)])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root, subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=False,
    )
    assert result["jury_handoff_status"] == "needs_review_blocked_by_strict"
    assert result["exit_code"] == 11
    assert result["review_status"] is None
    assert fake_run.call_count() == 2


def test_h6_jury_needs_review_no_strict(
    fake_run_factory: Callable[..., Any],
    make_jury_run_dir: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H6 — jury needs_review + no-strict：exit=0 + warning"""
    run_dir = make_jury_run_dir(jury_status="needs_review")
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run = fake_run_factory([cp(0, stdout="[dry-run] estimated=0.04 USD\n"), cp(0)])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root, subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=True,
    )
    assert result["jury_handoff_status"] == "needs_review_warning"
    assert result["exit_code"] == 0
    assert result["review_status"] is None
    assert fake_run.call_count() == 2


# === Task 9: H7a/b/H8a/b/H11a/b 工具故障类双向（spec inv 5 no-strict 不可降级）===

@pytest.mark.parametrize("no_strict", [False, True])
def test_h7_jury_blocked(
    no_strict: bool,
    fake_run_factory: Callable[..., Any],
    make_jury_run_dir: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H7a/H7b — jury 实跑写 status=blocked + return 0：exit=12 永远阻断（spec inv 5）"""
    run_dir = make_jury_run_dir(jury_status="blocked")
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run = fake_run_factory([cp(0, stdout="[dry-run] estimated=0.04 USD\n"), cp(0)])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root, subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=no_strict,
    )
    assert result["jury_handoff_status"] == "jury_blocked"
    assert result["exit_code"] == 12  # no-strict 不能覆盖
    assert result["review_status"] is None
    assert fake_run.call_count() == 2


@pytest.mark.parametrize("no_strict", [False, True])
def test_h8_jury_lock_busy(
    no_strict: bool,
    fake_run_factory: Callable[..., Any],
    make_jury_run_dir: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H8a/H8b — jury 实跑 exit=4：透传"""
    run_dir = make_jury_run_dir()
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run = fake_run_factory([cp(0, stdout="[dry-run] estimated=0.04 USD\n"), cp(4, stderr="lock busy")])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root, subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=no_strict,
    )
    assert result["jury_handoff_status"] == "lock_busy"
    assert result["exit_code"] == 4
    assert result["review_status"] is None
    assert fake_run.call_count() == 2


@pytest.mark.parametrize("no_strict", [False, True])
def test_h11_jury_internal(
    no_strict: bool,
    fake_run_factory: Callable[..., Any],
    make_jury_run_dir: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H11a/H11b — jury 实跑 exit=99：透传"""
    run_dir = make_jury_run_dir()
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run = fake_run_factory([cp(0, stdout="[dry-run] estimated=0.04 USD\n"), cp(99, stderr="internal")])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root, subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=no_strict,
    )
    assert result["jury_handoff_status"] == "internal_error"
    assert result["exit_code"] == 99
    assert result["review_status"] is None
    assert fake_run.call_count() == 2


# === Task 10: H18/H19 unexpected exit ===

def test_h18_jury_sigint(
    fake_run_factory: Callable[..., Any],
    make_jury_run_dir: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H18 — jury exit=130 (SIGINT)：exit=25 + jury_raw_exit=130"""
    run_dir = make_jury_run_dir()
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run_factory([cp(0, stdout="[dry-run] estimated=0.04 USD\n"), cp(130)])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root, subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=False,
    )
    assert result["jury_handoff_status"] == "unexpected_jury_exit"
    assert result["jury_raw_exit"] == 130
    assert result["exit_code"] == 25


def test_h19_jury_oom(
    fake_run_factory: Callable[..., Any],
    make_jury_run_dir: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H19 — jury exit=137 (OOM)：exit=25 + jury_raw_exit=137"""
    run_dir = make_jury_run_dir()
    project_root = run_dir.parent.parent.parent.parent.parent
    monkeypatch.chdir(project_root)
    monkeypatch.setattr("tools.photo3d_handoff.acquire_lock", _fake_acquire_lock_ok, raising=False)
    fake_run_factory([cp(0, stdout="[dry-run] estimated=0.04 USD\n"), cp(137)])
    from tools.photo3d_handoff import _run_jury_followup
    result = _run_jury_followup(
        project_root=project_root, subsystem="lifting_platform",
        active_run_id="20260509-123456",
        cad_pipeline_py=project_root / "cad_pipeline.py",
        no_strict_jury=False,
    )
    assert result["jury_handoff_status"] == "unexpected_jury_exit"
    assert result["jury_raw_exit"] == 137
    assert result["exit_code"] == 25
