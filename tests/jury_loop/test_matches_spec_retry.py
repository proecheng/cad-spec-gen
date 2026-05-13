"""Task 9 v2.37 (C)：orchestrator 接 matches_spec FAIL → prompt_rewriter.hint() retry。

测试目标（spec §3 F5）：
- (C-1) _call_jury_subprocess 识别 matches_spec_failed anomaly：verdict.verdict='needs_review'
        + 'matches_spec_failed' in anomalies → 返 (verdict, "matches_spec_failed")
        而非 (None, "needs_review")——让上层拿到完整 verdict + features_status 走 retry
- (C-2) run_loop_if_eligible 检测 matches_spec_failed → 调 prompt_rewriter.hint() 把 missing
        features 反馈拼到 backend retry prompt 末尾
- (C-3) 当 matches_spec 失败但 photoreal_score >= threshold 时，仍走 retry 路径
        （不被 above_threshold 短路），即 above_threshold 不能盖过 spec mismatch
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from enhance_budget import LoopBudget
from tools.jury.config import JuryProfile
from tools.jury.verdict import ViewVerdict
from tools.jury_loop import orchestrator as orch
from tools.jury_loop.backends import BackendResponse


def _make_jury_profile() -> JuryProfile:
    return JuryProfile(
        id="test",
        kind="openai_compat",
        api_base_url="https://example.test/v1",
        api_key="sk-fake-test-key",
        model="gemini-2.5-flash",
        cost_per_call_usd=0.005,
    )


def _make_matches_spec_failed_verdict() -> ViewVerdict:
    """构造 matches_spec=False + needs_review verdict（features_status 含 invisible feature）。

    模拟 Task 9 (A) 决策路径：LLM 看到 features 但 invisible → matches_spec=False
    → has_real_feature_fail=True → verdict='needs_review' + anomaly 'matches_spec_failed'。
    """
    return ViewVerdict(
        semantic_checks={
            "geometry_preserved": True,
            "material_consistent": True,
            "photorealistic": True,
            "no_extra_parts": True,
            "no_missing_parts": True,
            "matches_spec": False,
        },
        photoreal_score=85,  # 高分但 spec 仍 fail，验 above_threshold 不能短路
        reason="图片质量 OK 但缺特征",
        parse_status="ok",
        parse_anomalies=["matches_spec_failed"],
        verdict="needs_review",
        features_status=[
            {"feature_id": "flange_arms_4", "visible": False, "reason": "未见 4 臂"},
            {"feature_id": "peek_ring", "visible": True, "reason": "ring ok"},
        ],
    )


# ==================================================================
# C-1: _call_jury_subprocess 透传 matches_spec_failed verdict（非 None）
# ==================================================================


def test_call_jury_subprocess_returns_verdict_when_matches_spec_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C-1：子进程 stdout 含 features_status invisible → 返 (verdict, "matches_spec_failed")

    与 (None, "needs_review") 不同：matches_spec 失败应保留 verdict 让上层提取
    missing feature_ids 给 prompt_rewriter.hint() 用。
    """
    import subprocess
    from unittest.mock import MagicMock

    # 子进程 stdout：features_status 含 invisible feature → 触发 (A) 决策升级 needs_review
    fake_stdout = json.dumps(
        [
            {
                "view": "V4",
                "image_path": "fake.jpg",
                "verdict": "needs_review",
                "photoreal_score": 85,
                "semantic_checks": {
                    "geometry_preserved": True,
                    "material_consistent": True,
                    "photorealistic": True,
                    "no_extra_parts": True,
                    "no_missing_parts": True,
                    "matches_spec": False,
                },
                "reason": "缺 4 臂",
                "features_status": [
                    {"feature_id": "flange_arms_4", "visible": False, "reason": "无"},
                ],
                "parse_status": "ok",
                "parse_anomalies": ["matches_spec_failed"],
            }
        ]
    ).encode("utf-8")

    chunks = [fake_stdout, b""]
    fake_proc = MagicMock()
    fake_proc.stdout.read.side_effect = chunks
    fake_proc.stderr.read.return_value = b""
    fake_proc.returncode = 0
    fake_proc.poll.return_value = 0

    def _fake_popen(cmd, **kwargs):  # noqa: ANN001, ARG001
        return fake_proc

    monkeypatch.setattr(subprocess, "Popen", _fake_popen)

    img = tmp_path / "img.jpg"
    img.write_bytes(b"")

    verdict, err_code = orch._call_jury_subprocess(
        view="V1",
        image_path=img,
        project_root=tmp_path,
        jury_profile_path=tmp_path / "profile.yaml",
        timeout_s=30,
    )

    # 关键断言（C-1）：verdict 不能为 None；error code 是 matches_spec_failed
    assert err_code == "matches_spec_failed", (
        f"应返 matches_spec_failed；实际 {err_code}"
    )
    assert verdict is not None, (
        "matches_spec 失败时 verdict 不可丢——上层要 features_status 反馈"
    )
    assert verdict.features_status, "features_status 必须透传给上层"
    missing = [
        f["feature_id"] for f in verdict.features_status if not f.get("visible", True)
    ]
    assert missing == ["flange_arms_4"]


# ==================================================================
# C-2 + C-3: orchestrator 接 matches_spec_failed → prompt_rewriter.hint
# ==================================================================


def test_matches_spec_failed_triggers_retry_with_hint(
    tmp_path: Path,
    fake_render_dir,  # noqa: ANN001 — fixture
    fake_backend_adapter,  # noqa: ANN001 — fixture
    tiny_loop_config,  # noqa: ANN001 — fixture
    tiny_jury_profile,  # noqa: ANN001 — fixture
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C-2+C-3：matches_spec 失败 + photoreal_score=85 ≥ threshold → 仍走 retry，
    backend.call() 收到的 prompt 含 prompt_rewriter.hint() 注入的 missing features 反馈。
    """
    # 第一次 jury（baseline）返 matches_spec_failed verdict
    # 第二次 jury（retry score_select）返 high-score visible verdict
    verdicts_iter = iter(
        [
            _make_matches_spec_failed_verdict(),
            ViewVerdict(
                semantic_checks={
                    "geometry_preserved": True,
                    "material_consistent": True,
                    "photorealistic": True,
                    "no_extra_parts": True,
                    "no_missing_parts": True,
                    "matches_spec": True,
                },
                photoreal_score=90,
                reason="retry ok",
                parse_status="ok",
                verdict="accepted",
                features_status=[
                    {"feature_id": "flange_arms_4", "visible": True, "reason": "ok"},
                ],
            ),
        ]
    )

    err_codes_iter = iter(["matches_spec_failed", None])

    def _stub_subprocess(**_kw):  # noqa: ANN003
        return (next(verdicts_iter), next(err_codes_iter))

    monkeypatch.setattr(
        "tools.jury_loop.orchestrator._call_jury_subprocess", _stub_subprocess
    )

    # 捕捉 backend.call() 收到的 prompt
    captured_prompts: list[str] = []

    response = BackendResponse(
        output_image_path=fake_render_dir / "V1_enhanced_retry.jpg",
        actual_cost_usd=0.04,
        raw_request_summary={},
    )
    (fake_render_dir / "V1_enhanced_retry.jpg").write_bytes(b"\x89PNG\r\n\x1a\n")

    with fake_backend_adapter(call_returns=response) as kind:
        # 注入 wrapper 捕 prompt（在 adapter.call 调用前抓 request.prompt）
        from tools.jury_loop.backends import BACKEND_REGISTRY

        adapter = BACKEND_REGISTRY[kind]
        orig_call = adapter.call

        def _spy_call(request, timeout):  # noqa: ANN001
            captured_prompts.append(request.prompt)
            return orig_call(request, timeout)

        adapter.call = _spy_call  # type: ignore[method-assign]

        config = tiny_loop_config(backend_kind=kind, threshold=75)
        result = orch.run_loop_if_eligible(
            view="V1",
            backend_kind=kind,
            rc={"prompt": "base enhance prompt"},
            baseline_path=fake_render_dir / "V1_enhanced_baseline.jpg",
            base_params={},
            budget=LoopBudget(cap_usd=1.5, n_views=1),
            project_root=tmp_path,
            config=config,
            jury_profile=tiny_jury_profile,
            jury_profile_path=tmp_path / "profile.yaml",
        )

    # C-3 锁：score=85 ≥ threshold=75 但 matches_spec=False → 不允许 above_threshold 短路
    assert result.loop_status != "above_threshold", (
        f"matches_spec=False 时 above_threshold 不能短路；实际 {result.loop_status}"
    )

    # C-2 锁：backend 收到的 prompt 含 hint() 注入的 missing feature 反馈
    assert len(captured_prompts) == 1
    assert "matches_spec 反馈" in captured_prompts[0], (
        f"backend 应收 hint()-rewritten prompt；实际 {captured_prompts[0]!r}"
    )
    assert "flange_arms_4" in captured_prompts[0], (
        f"prompt 应含 missing feature_id；实际 {captured_prompts[0]!r}"
    )
    # base_prompt 仍要保留（hint() 是末尾追加）
    assert "base enhance prompt" in captured_prompts[0]


def test_matches_spec_failed_path_finalizes_normally(
    tmp_path: Path,
    fake_render_dir,  # noqa: ANN001
    fake_backend_adapter,  # noqa: ANN001
    tiny_loop_config,  # noqa: ANN001
    tiny_jury_profile,  # noqa: ANN001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C-2 补：matches_spec retry 后写 sidecar；sidecar.loop_status 不是 jury_unavailable。

    Regression 防：(A) 决策升级后若 _call_jury_subprocess 仍把 matches_spec_failed 当
    None 走 jury_unavailable，会丢 retry 机会，本测试 catch 这条隐性回归。
    """
    verdicts_iter = iter(
        [
            _make_matches_spec_failed_verdict(),
            ViewVerdict(
                semantic_checks={
                    "geometry_preserved": True,
                    "material_consistent": True,
                    "photorealistic": True,
                    "no_extra_parts": True,
                    "no_missing_parts": True,
                    "matches_spec": True,
                },
                photoreal_score=90,
                reason="retry ok",
                parse_status="ok",
                verdict="accepted",
                features_status=[],
            ),
        ]
    )
    err_codes_iter = iter(["matches_spec_failed", None])

    def _stub_subprocess(**_kw):  # noqa: ANN003
        return (next(verdicts_iter), next(err_codes_iter))

    monkeypatch.setattr(
        "tools.jury_loop.orchestrator._call_jury_subprocess", _stub_subprocess
    )

    response = BackendResponse(
        output_image_path=fake_render_dir / "V1_enhanced_retry.jpg",
        actual_cost_usd=0.04,
        raw_request_summary={},
    )
    (fake_render_dir / "V1_enhanced_retry.jpg").write_bytes(b"\x89PNG\r\n\x1a\n")

    with fake_backend_adapter(call_returns=response) as kind:
        config = tiny_loop_config(backend_kind=kind, threshold=75)
        result = orch.run_loop_if_eligible(
            view="V1",
            backend_kind=kind,
            rc={"prompt": "base prompt"},
            baseline_path=fake_render_dir / "V1_enhanced_baseline.jpg",
            base_params={},
            budget=LoopBudget(cap_usd=1.5, n_views=1),
            project_root=tmp_path,
            config=config,
            jury_profile=tiny_jury_profile,
            jury_profile_path=tmp_path / "profile.yaml",
        )

    # 不应是 jury_unavailable（regression catch）
    assert result.loop_status != "jury_unavailable", (
        "matches_spec_failed 不应被当作 jury 不可用"
    )
    # 正常 retry 退出路径之一（delivered_retry / delivered_baseline）
    assert result.loop_status in (
        "delivered_retry",
        "delivered_baseline",
    ), f"unexpected loop_status: {result.loop_status}"
    sidecar = json.loads(
        (fake_render_dir / "V1_enhance_meta.json").read_text("utf-8")
    )
    assert sidecar["loop_status"] == result.loop_status
