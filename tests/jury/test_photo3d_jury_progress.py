"""§11-N3 per-view 进度 stderr 测试 (v2.37.7)。

覆盖 3 路径（spec §3.1 D1 + layer 6 F1 + E2 fix）：
- try-success：△ [V<n>/<total>] <model> photoreal=<score> verdict=<verdict> <latency>s
- except JuryLlmError：△ [V<n>/<total>] <model> ERROR <error_kind> 0.0s
- except Exception (E2 fix)：△ [V<n>/<total>] <model> CRASH <exc_type> + re-raise

fixture 沿用 test_photo3d_jury_e2e.py 的 jury_env 模式（已实证可走完 Layer 0）。
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tools.photo3d_jury import main


def _make_ok_response(view: str, score: int = 75) -> MagicMock:
    """构造单视角 OK 的 chat-completions urlopen context mock。"""
    body = {
        "id": f"chatcmpl-{view}",
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "semantic_checks": {
                                "geometry_preserved": True,
                                "material_consistent": True,
                                "photorealistic": True,
                                "no_extra_parts": True,
                                "no_missing_parts": True,
                            },
                            "photoreal_score": score,
                            "reason": "ok",
                        }
                    )
                },
                "finish_reason": "stop",
            }
        ],
    }
    cm = MagicMock()
    resp = MagicMock()
    resp.status = 200
    resp.read.return_value = json.dumps(body).encode("utf-8")
    resp.headers = {"Content-Type": "application/json"}
    cm.__enter__.return_value = resp
    cm.__exit__.return_value = None
    return cm


@pytest.fixture
def jury_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """jury Layer 0 最小 valid state — 沿用 e2e 既有 fixture 模式（lifting_platform 2 视角）。"""
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


def test_per_view_progress_stderr_emit_success(
    jury_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """v2.37.7 §11-N3 (F1 fix try-success)：success 视角 stderr 含 △ [V<n>/<total>] <model> photoreal=<score> verdict=<verdict> <latency>s。"""
    views = ["iso", "front"]
    iterator = iter(_make_ok_response(v) for v in views)
    with patch(
        "tools.jury.llm_client.urlopen",
        side_effect=lambda *a, **kw: next(iterator),
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
    captured = capsys.readouterr()
    # 两个视角都应出进度行
    assert "△ [iso/" in captured.err or "△ [1/" in captured.err, (
        f"stderr 应含 △ 进度行（iso 或 1）；实际: {captured.err!r}"
    )
    assert "photoreal=75" in captured.err
    assert "verdict=" in captured.err
    assert "gpt-4o" in captured.err


def test_per_view_progress_stderr_emit_failure(
    jury_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """v2.37.7 §11-N3 (F1 fix except JuryLlmError)：LLM 失败 stderr 含 ERROR <error_kind>。"""
    from urllib.error import HTTPError

    err_401 = HTTPError(
        url="x",
        code=401,
        msg="x",
        hdrs={},  # type: ignore[arg-type]
        fp=io.BytesIO(b""),
    )
    ok_resp = _make_ok_response("front")

    calls: list[Any] = [err_401, ok_resp]
    iterator = iter(calls)

    def side_effect(*a: object, **kw: object) -> object:
        c = next(iterator)
        if isinstance(c, HTTPError):
            raise c
        return c

    with (
        patch("tools.jury.llm_client.urlopen", side_effect=side_effect),
        patch("tools.jury.llm_client.time.sleep"),
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
    captured = capsys.readouterr()
    # iso 视角应 ERROR auth_failed（401 → JuryLlmError.error_kind）
    assert "△ [iso/" in captured.err or "△ [1/" in captured.err, (
        f"failure stderr 应含 △ 进度行；实际: {captured.err!r}"
    )
    assert "ERROR" in captured.err
    assert "auth_failed" in captured.err


def test_per_view_progress_stderr_emit_crash(
    jury_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """v2.37.7 §11-N3 (E2 fix except Exception)：non-JuryLlmError 异常 stderr 含 CRASH <exc_type> + re-raise。"""
    with patch(
        "tools.jury.llm_client.urlopen",
        side_effect=OSError("network down"),
    ):
        # E2 fix：OSError 兜底进度行 + re-raise → main 顶层 except Exception 兜 → 99
        # 验：crash 进度行必出现；exit code 99 (顶层兜底)
        code = main(
            [
                "--subsystem",
                "lifting_platform",
                "--project-root",
                str(jury_env),
            ]
        )
    captured = capsys.readouterr()
    assert "△ [iso/" in captured.err or "△ [1/" in captured.err, (
        f"crash stderr 应含 △ 进度行；实际: {captured.err!r}"
    )
    assert "CRASH" in captured.err
    assert "OSError" in captured.err
    # E2 fix 要求 re-raise → 走顶层 except Exception → 99
    assert code == 99
