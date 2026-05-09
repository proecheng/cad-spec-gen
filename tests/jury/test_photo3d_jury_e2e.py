"""集成 e2e — patch tools.jury.llm_client.urlopen，完整 cad/<sub>/.cad-spec-gen/runs/<run>/。

Tasks 19+20+21 合并：
- Task 19: 全 happy + api_key 不落盘 (2 case)
- Task 20: 失败路径 1 视角 401 / 低 score / blocked (3 case)
- Task 21: 重跑归档 / --force 固定后缀 (2 case)
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tools.photo3d_jury import main


def _make_response(
    body: dict[str, Any] | bytes,
    status: int = 200,
    headers: dict[str, str] | None = None,
) -> MagicMock:
    """构造单个 urlopen 上下文 mock；body 可传 dict（自动 json）或 bytes（直透）。"""
    cm = MagicMock()
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = (
        body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
    )
    resp.headers = headers or {"Content-Type": "application/json"}
    cm.__enter__.return_value = resp
    cm.__exit__.return_value = None
    return cm


def _ok_payload(view: str, score: int = 80, all_true: bool = True) -> dict[str, Any]:
    """构造单视角 OK 的 chat-completions payload。"""
    checks = {
        "geometry_preserved": all_true,
        "material_consistent": all_true,
        "photorealistic": all_true,
        "no_extra_parts": all_true,
        "no_missing_parts": all_true,
    }
    return {
        "id": f"chatcmpl-{view}",
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "semantic_checks": checks,
                            "photoreal_score": score,
                            "reason": f"view {view} OK",
                        }
                    )
                },
                "finish_reason": "stop",
            }
        ],
    }


def _ok_response_iter(views: list[str]) -> Any:
    """生成器：每视角依次产出 200 OK 上下文 mock。"""
    for v in views:
        yield _make_response(
            _ok_payload(v),
            headers={
                "Content-Type": "application/json",
                "x-request-id": f"trace-{v}",
            },
        )


@pytest.fixture
def jury_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """完整 jury 测试环境：HOME / config / project_root + active_run。

    e2e 显式 opt-in：清掉 conftest autouse 的 CAD_JURY_DISABLE_LLM 让 mock urlopen 真触发。
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("CAD_JURY_DISABLE_LLM", raising=False)

    cfg = tmp_path / ".claude" / "cad_jury_config.json"
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
                        "cost_per_call_usd": 0.005,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    sub = "lifting_platform"
    run_id = "20260508-123456"
    fixtures = Path("tests/jury/fixtures")

    run_dir = tmp_path / "cad" / sub / ".cad-spec-gen" / "runs" / run_id
    run_dir.mkdir(parents=True)
    render_dir = tmp_path / "cad" / "output" / "renders" / sub / run_id
    render_dir.mkdir(parents=True)
    (render_dir / "iso_enhanced.png").write_bytes(
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 1000
    )
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
    (render_dir / "render_manifest.json").write_text(
        json.dumps(rm), encoding="utf-8"
    )
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


# === Task 19: happy + key 不落盘 ===


def test_full_happy_path_writes_two_reports(jury_env: Path) -> None:
    """2 视角全 OK + score=80 → status=accepted；落 PHOTO3D_JURY_REPORT + jury_review_input。"""
    iter_responses = _ok_response_iter(["iso", "front"])
    with patch(
        "tools.jury.llm_client.urlopen",
        side_effect=lambda *a, **kw: next(iter_responses),
    ):
        code = main(
            [
                "--subsystem",
                "lifting_platform",
                "--project-root",
                str(jury_env),
            ]
        )
    assert code == 0
    run_dir = (
        jury_env / "cad" / "lifting_platform" / ".cad-spec-gen" / "runs"
        / "20260508-123456"
    )
    rep_path = run_dir / "PHOTO3D_JURY_REPORT.json"
    rev_path = run_dir / "jury_review_input.json"
    assert rep_path.exists()
    assert rev_path.exists()
    rep = json.loads(rep_path.read_text(encoding="utf-8"))
    assert rep["status"] == "accepted"
    assert rep["jury_meta"]["actual_cost_usd"] == pytest.approx(0.010)
    assert rep["jury_meta"]["estimated_cost_usd"] == pytest.approx(0.010)
    assert all(v["verdict"] == "accepted" for v in rep["views"])


def test_api_key_not_in_report(jury_env: Path) -> None:
    """两份输出文件均不得含 api_key 字面量。"""
    iter_responses = _ok_response_iter(["iso", "front"])
    with patch(
        "tools.jury.llm_client.urlopen",
        side_effect=lambda *a, **kw: next(iter_responses),
    ):
        main(
            [
                "--subsystem",
                "lifting_platform",
                "--project-root",
                str(jury_env),
            ]
        )
    run_dir = (
        jury_env / "cad" / "lifting_platform" / ".cad-spec-gen" / "runs"
        / "20260508-123456"
    )
    rep = (run_dir / "PHOTO3D_JURY_REPORT.json").read_text(encoding="utf-8")
    rev = (run_dir / "jury_review_input.json").read_text(encoding="utf-8")
    assert "dummy-not-a-real-key" not in rep
    assert "dummy-not-a-real-key" not in rev


# === Task 20: 失败路径 ===


def test_one_view_401_overall_needs_review(jury_env: Path) -> None:
    """1 视角 401 → 整体 needs_review；jury_review_input.json 不写。"""
    from urllib.error import HTTPError

    err_401 = HTTPError(
        url="x",
        code=401,
        msg="x",
        hdrs={},  # type: ignore[arg-type]
        fp=io.BytesIO(b""),
    )
    ok_iter = _ok_response_iter(["front"])
    ok_resp = next(ok_iter)

    calls: list[Any] = [err_401, ok_resp]
    iterator = iter(calls)

    def side_effect(*a: object, **kw: object) -> object:
        c = next(iterator)
        if isinstance(c, HTTPError):
            raise c
        return c

    with patch(
        "tools.jury.llm_client.urlopen", side_effect=side_effect
    ), patch("tools.jury.llm_client.time.sleep"):
        code = main(
            [
                "--subsystem",
                "lifting_platform",
                "--project-root",
                str(jury_env),
            ]
        )
    assert code == 0
    run_dir = (
        jury_env / "cad" / "lifting_platform" / ".cad-spec-gen" / "runs"
        / "20260508-123456"
    )
    rep = json.loads(
        (run_dir / "PHOTO3D_JURY_REPORT.json").read_text(encoding="utf-8")
    )
    assert rep["status"] == "needs_review"
    assert any(
        v["llm_meta"]["error_kind"] == "auth_failed" for v in rep["views"]
    )
    assert not (run_dir / "jury_review_input.json").exists()


def test_low_score_overall_preview(jury_env: Path) -> None:
    """全成功但 1 视角 score=15 < min_photoreal_score=60 → preview；review_input 不写。"""
    bodies = [
        json.dumps(
            {
                "id": "x",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "semantic_checks": {
                                        k: True
                                        for k in [
                                            "geometry_preserved",
                                            "material_consistent",
                                            "photorealistic",
                                            "no_extra_parts",
                                            "no_missing_parts",
                                        ]
                                    },
                                    "photoreal_score": 15,
                                    "reason": "low",
                                }
                            )
                        },
                        "finish_reason": "stop",
                    }
                ],
            }
        ).encode("utf-8"),
        json.dumps(
            {
                "id": "y",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "semantic_checks": {
                                        k: True
                                        for k in [
                                            "geometry_preserved",
                                            "material_consistent",
                                            "photorealistic",
                                            "no_extra_parts",
                                            "no_missing_parts",
                                        ]
                                    },
                                    "photoreal_score": 80,
                                    "reason": "ok",
                                }
                            )
                        },
                        "finish_reason": "stop",
                    }
                ],
            }
        ).encode("utf-8"),
    ]
    iterator = iter(bodies)

    def side_effect(*a: object, **kw: object) -> MagicMock:
        body = next(iterator)
        return _make_response(body)

    with patch("tools.jury.llm_client.urlopen", side_effect=side_effect):
        code = main(
            [
                "--subsystem",
                "lifting_platform",
                "--project-root",
                str(jury_env),
            ]
        )
    assert code == 0
    run_dir = (
        jury_env / "cad" / "lifting_platform" / ".cad-spec-gen" / "runs"
        / "20260508-123456"
    )
    rep = json.loads(
        (run_dir / "PHOTO3D_JURY_REPORT.json").read_text(encoding="utf-8")
    )
    assert rep["status"] == "preview"
    assert not (run_dir / "jury_review_input.json").exists()


def test_subsystem_mismatch_blocked(jury_env: Path) -> None:
    """--subsystem 不匹配 → ARTIFACT_INDEX 缺失 → Layer 0 fail → exit 1。"""
    code = main(
        [
            "--subsystem",
            "wrong_sub",
            "--project-root",
            str(jury_env),
        ]
    )
    assert code == 1


# === Task 21: 重跑保护 ===


def test_rerun_archives_existing_report(jury_env: Path) -> None:
    """已有 PHOTO3D_JURY_REPORT.json + 重跑 → 归档前次（紧凑 utc_iso + short_hash）+ 写新报告。"""
    iter_resp = _ok_response_iter(["iso", "front"])
    with patch(
        "tools.jury.llm_client.urlopen",
        side_effect=lambda *a, **kw: next(iter_resp),
    ):
        main(
            [
                "--subsystem",
                "lifting_platform",
                "--project-root",
                str(jury_env),
            ]
        )
    iter_resp2 = _ok_response_iter(["iso", "front"])
    with patch(
        "tools.jury.llm_client.urlopen",
        side_effect=lambda *a, **kw: next(iter_resp2),
    ):
        main(
            [
                "--subsystem",
                "lifting_platform",
                "--project-root",
                str(jury_env),
            ]
        )
    run_dir = (
        jury_env / "cad" / "lifting_platform" / ".cad-spec-gen" / "runs"
        / "20260508-123456"
    )
    archived = list(run_dir.glob("PHOTO3D_JURY_REPORT.20*Z.*.json"))
    assert len(archived) >= 1, (
        f"应有归档文件，实际: {list(run_dir.iterdir())}"
    )
    # 归档名无冒号（Windows NTFS 兼容）
    assert ":" not in archived[0].name
    # 新报告仍存在
    assert (run_dir / "PHOTO3D_JURY_REPORT.json").exists()


def test_force_archives_with_fixed_suffix(jury_env: Path) -> None:
    """--force → 归档名固定为 PHOTO3D_JURY_REPORT.forced.json。"""
    iter_resp = _ok_response_iter(["iso", "front"])
    with patch(
        "tools.jury.llm_client.urlopen",
        side_effect=lambda *a, **kw: next(iter_resp),
    ):
        main(
            [
                "--subsystem",
                "lifting_platform",
                "--project-root",
                str(jury_env),
            ]
        )
    iter_resp2 = _ok_response_iter(["iso", "front"])
    with patch(
        "tools.jury.llm_client.urlopen",
        side_effect=lambda *a, **kw: next(iter_resp2),
    ):
        main(
            [
                "--subsystem",
                "lifting_platform",
                "--project-root",
                str(jury_env),
                "--force",
            ]
        )
    run_dir = (
        jury_env / "cad" / "lifting_platform" / ".cad-spec-gen" / "runs"
        / "20260508-123456"
    )
    assert (run_dir / "PHOTO3D_JURY_REPORT.forced.json").exists()
    assert (run_dir / "PHOTO3D_JURY_REPORT.json").exists()
