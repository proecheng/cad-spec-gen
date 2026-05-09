"""cli 薄壳测试 — argparse + exit code + stderr 中文 + 主流程串联 (Tasks 17+18, 6 case)。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.photo3d_jury import main


def _write_jury_config(home: Path, cost_per_call: float = 0.005) -> Path:
    """写最小 jury 配置到 home/.claude/cad_jury_config.json。

    cost_per_call 默认 0.005（2 视角 = 0.01 < 默认 budget 0.1）；
    高 cost 场景测试自行覆盖。
    """
    cfg = home / ".claude" / "cad_jury_config.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "active_profile_id": "main",
                "profiles": [
                    {
                        "id": "main",
                        "kind": "openai_compat",
                        "api_base_url": "https://api.example.com/v1",
                        "api_key": "dummy-not-a-real-key",
                        "model": "gpt-4o",
                        "cost_per_call_usd": cost_per_call,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return cfg


@pytest.fixture
def project_root_with_run(tmp_path: Path) -> Path:
    """构造完整 cad/<sub>/.cad-spec-gen/runs/<run>/ + ARTIFACT_INDEX.json + 假图。

    与 test_input_evidence_binding.py 同形态；不复用 fixture 防跨文件耦合。
    """
    sub = "lifting_platform"
    run_id = "20260508-123456"
    fixtures = Path("tests/jury/fixtures")

    run_dir = tmp_path / "cad" / sub / ".cad-spec-gen" / "runs" / run_id
    run_dir.mkdir(parents=True)
    render_dir = tmp_path / "cad" / "output" / "renders" / sub / run_id
    render_dir.mkdir(parents=True)
    (render_dir / "iso_enhanced.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 1000)
    (render_dir / "front_enhanced.png").write_bytes(
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 1000
    )

    rm = json.loads(
        (fixtures / "sample_render_manifest.json").read_text(encoding="utf-8")
    )
    er = json.loads(
        (fixtures / "sample_enhancement_report.json").read_text(encoding="utf-8")
    )
    for v in er["views"]:
        v["enhanced_image"] = (
            f"cad/output/renders/{sub}/{run_id}/{v['view']}_enhanced.png"
        )
    (render_dir / "render_manifest.json").write_text(json.dumps(rm), encoding="utf-8")
    (render_dir / "ENHANCEMENT_REPORT.json").write_text(
        json.dumps(er), encoding="utf-8"
    )

    ai = json.loads(
        (fixtures / "sample_artifact_index.json").read_text(encoding="utf-8")
    )
    (run_dir.parent.parent / "ARTIFACT_INDEX.json").write_text(
        json.dumps(ai), encoding="utf-8"
    )
    return tmp_path


def test_missing_subsystem_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """无 --subsystem 立即退 2（在 list-profiles 检查之后）。"""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    _write_jury_config(tmp_path)
    code = main([])
    assert code == 2


def test_config_missing_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """无 jury 配置文件 → exit 2 + config_missing。"""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    code = main(["--subsystem", "x"])
    assert code == 2


def test_list_profiles_exits_0(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--list-profiles 优先级最高，无 --subsystem 也能跑；输出 active profile 一行。"""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    _write_jury_config(tmp_path)
    code = main(["--list-profiles"])
    assert code == 0
    captured = capsys.readouterr()
    assert "main" in captured.out
    assert "openai_compat" in captured.out


def test_dry_run_no_writes(
    project_root_with_run: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--dry-run + 成本在 budget 内 → exit 0，且 PHOTO3D_JURY_REPORT.json 不落盘。"""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    _write_jury_config(tmp_path)
    code = main(
        [
            "--subsystem",
            "lifting_platform",
            "--project-root",
            str(project_root_with_run),
            "--dry-run",
        ]
    )
    assert code == 0
    run_dir = (
        project_root_with_run
        / "cad"
        / "lifting_platform"
        / ".cad-spec-gen"
        / "runs"
        / "20260508-123456"
    )
    assert not (run_dir / "PHOTO3D_JURY_REPORT.json").exists()


def test_input_evidence_error_exits_1(
    project_root_with_run: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """子系统名错（artifact_index_missing） → Layer 0 fail → exit 1。"""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    _write_jury_config(tmp_path)
    code = main(
        [
            "--subsystem",
            "wrong_subsystem",
            "--project-root",
            str(project_root_with_run),
            "--dry-run",
        ]
    )
    assert code == 1


def test_cost_over_budget_no_confirm_exits_3(
    project_root_with_run: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """高 cost 触发超 budget；dry-run 仍走 cost gate；无 --confirm-cost → exit 3。"""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    _write_jury_config(
        tmp_path, cost_per_call=1.0
    )  # 2 视角 × 1.0 = 2.0 USD > 默认 budget 0.1
    code = main(
        [
            "--subsystem",
            "lifting_platform",
            "--project-root",
            str(project_root_with_run),
            "--dry-run",
        ]
    )
    assert code == 3
