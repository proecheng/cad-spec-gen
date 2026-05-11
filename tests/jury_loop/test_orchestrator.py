"""CP-5 orchestrator 集成测试（spec §5 矩阵 19 测试，本 task 仅 #20）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from enhance_budget import LoopBudget
from tools.jury.config import JuryProfile
from tools.jury_loop.config import BackendConfig, JuryLoopConfig
from tools.jury_loop.orchestrator import LoopResult, run_loop_if_eligible

# 保持 LoopResult 显式 import：dataclass 契约的 symbol 存在性 sanity check（spec rev 3 决议 #3）
assert LoopResult.__name__ == "LoopResult"


def _stub_budget() -> LoopBudget:
    return LoopBudget(cap_usd=1.5, n_views=1)


def _stub_jury_profile() -> JuryProfile:
    return JuryProfile(
        id="test", kind="openai_compat",
        api_base_url="https://example.test/v1",
        api_key="sk-fake-test-key",
        model="gemini-2.5-flash", cost_per_call_usd=0.005,
    )


def _stub_loop_config() -> JuryLoopConfig:
    return JuryLoopConfig(
        enabled=True, cost_cap_usd=1.5,
        backend=BackendConfig(
            kind="test_stub", base_url="https://example.test",
            api_key_env="TEST_API_KEY", model_name="test-model", timeout_s=60,
        ),
        advanced={
            "threshold": 75, "max_retries": 1, "llm_fallback": False,
            "rule_table_path": None, "score_select_strategy": "pick_max_jury",
        },
    )


def test_baseline_path_missing_raises_filenotfound(tmp_path: Path) -> None:
    """spec §5 测试 #20：baseline_path 不存在 → fail-fast raise FileNotFoundError；不写 sidecar。"""
    with pytest.raises(FileNotFoundError):
        run_loop_if_eligible(
            view="V1", backend_kind="test_stub", rc={},
            baseline_path=tmp_path / "nope.jpg",
            base_params={}, budget=_stub_budget(),
            project_root=tmp_path, config=_stub_loop_config(),
            jury_profile=_stub_jury_profile(),
            jury_profile_path=tmp_path / "profile.yaml",
        )
    # 不写 sidecar
    assert not list(tmp_path.glob("V1_enhance_meta.json"))


def test_gate1_backend_unregistered(
    tmp_path, fake_render_dir, tiny_loop_config,
    tiny_jury_profile, isolated_backend_registry,
):
    """spec §5 #1：backend_kind='engineering' 不在 BACKEND_REGISTRY → loop_disabled。

    注意：engineering 内置不注册（_BUILTIN_ADAPTERS 仅 gemini/openai/comfyui_workflow_cloud）；
    isolated_backend_registry 保 snapshot/restore 防外部 register_backend("engineering") 污染。
    """
    config = tiny_loop_config(backend_kind="engineering")
    result = run_loop_if_eligible(
        view="V1", backend_kind="engineering", rc={},
        baseline_path=fake_render_dir / "V1_enhanced_baseline.jpg",
        base_params={}, budget=_stub_budget(),
        project_root=tmp_path, config=config,
        jury_profile=tiny_jury_profile,
        jury_profile_path=tmp_path / "profile.yaml",
    )
    assert result.loop_status == "loop_disabled"
    assert result.final_path == fake_render_dir / "V1_enhanced.jpg"
    assert (fake_render_dir / "V1_enhanced.jpg").is_file()
    sidecar = json.loads((fake_render_dir / "V1_enhance_meta.json").read_text("utf-8"))
    assert sidecar["loop_eligible"] is False
    assert sidecar["loop_status"] == "loop_disabled"


def test_gate2_enabled_false(
    tmp_path, fake_render_dir, fake_backend_adapter,
    tiny_loop_config, tiny_jury_profile,
):
    """spec §5 #2：config.enabled=False → loop_disabled。"""
    with fake_backend_adapter() as kind:
        config = tiny_loop_config(enabled=False, backend_kind=kind)
        result = run_loop_if_eligible(
            view="V1", backend_kind=kind, rc={},
            baseline_path=fake_render_dir / "V1_enhanced_baseline.jpg",
            base_params={}, budget=_stub_budget(),
            project_root=tmp_path, config=config,
            jury_profile=tiny_jury_profile,
            jury_profile_path=tmp_path / "profile.yaml",
        )
    assert result.loop_status == "loop_disabled"
    assert (fake_render_dir / "V1_enhanced.jpg").is_file()
    sidecar = json.loads((fake_render_dir / "V1_enhance_meta.json").read_text("utf-8"))
    assert sidecar["loop_eligible"] is False


# ==== Task 5.1.5：_classify_backend_error 4 路 + errors[] 构造 unit 测试 ==== #
# 注意：本批仅 unit 测试 helper 纯函数；集成测试 #9-#12（用 run_loop_if_eligible
# 触发 BackendError）等 Task 5.1.8 retry 路径落地后才能 GREEN。

from tools.jury_loop.backends import (  # noqa: E402  集成测试与 helper 测试 imports 分组
    BackendAuthError,
    BackendCallError,
    BackendError,
    BackendQuotaExceededError,
    BackendRateLimitError,
)
from tools.jury_loop.orchestrator import _classify_backend_error  # noqa: E402


@pytest.mark.parametrize("exc_cls, expected_status, expected_code, expected_hint", [
    (BackendAuthError, "retry_auth_failed", "backend_auth_error", "API key 无效，请检查配置后重试"),
    (BackendRateLimitError, "retry_rate_limited", "backend_rate_limited", "服务限流，请稍后重试"),
    (BackendQuotaExceededError, "retry_quota_exceeded", "backend_quota_exceeded", "服务账户余额不足，请充值后重试"),
    (BackendCallError, "retry_failed", "backend_call_error", "重试调用失败，请查看 sidecar.errors[]"),
])
def test_classify_backend_error_4_known_subclasses(
    exc_cls: type[BackendError],
    expected_status: str,
    expected_code: str,
    expected_hint: str,
) -> None:
    """spec rev 3 决议 #10：4 类已知 BackendError 子类的分类、errors[].code、user_action_hint 文案锁。"""
    loop_status, error_entry = _classify_backend_error(exc_cls("vendor 错误"))
    assert loop_status == expected_status
    assert error_entry["code"] == expected_code
    assert "vendor 错误" in error_entry["message_summary"]
    assert error_entry["user_action_hint"] == expected_hint  # 父 spec §4.6 BL-3 中文文案锁


def test_classify_backend_error_unknown_subclass_falls_back_to_retry_failed() -> None:
    """未知 BackendError 子类（仅继承 BackendError）→ retry_failed + backend_unknown_error。"""
    class _CustomBackendError(BackendError):
        pass

    loop_status, error_entry = _classify_backend_error(_CustomBackendError("奇怪错误"))
    assert loop_status == "retry_failed"
    assert error_entry["code"] == "backend_unknown_error"
    assert "奇怪错误" in error_entry["message_summary"]


def test_classify_backend_error_message_summary_truncated_at_200() -> None:
    """message_summary 长度 ≤ 200 字符（避免 sidecar 文件膨胀）。"""
    huge_msg = "x" * 500
    _, error_entry = _classify_backend_error(BackendCallError(huge_msg))
    assert len(error_entry["message_summary"]) <= 200


# ==== Task 5.1.6：Gate-3（jury 不可用） + Gate-3.5（empty_reason）==== #


def test_gate3_jury_returns_none_maps_to_jury_unavailable(
    tmp_path,
    fake_render_dir,
    fake_backend_adapter,
    tiny_loop_config,
    tiny_jury_profile,
    monkeypatch,
):
    """spec §5 #3：_call_jury_subprocess 返 (None, code) → jury_unavailable + sidecar.errors[0].code。"""
    monkeypatch.setattr(
        "tools.jury_loop.orchestrator._call_jury_subprocess",
        lambda **kw: (None, "exit_nonzero"),
    )
    with fake_backend_adapter() as kind:
        config = tiny_loop_config(backend_kind=kind)
        result = run_loop_if_eligible(
            view="V1",
            backend_kind=kind,
            rc={},
            baseline_path=fake_render_dir / "V1_enhanced_baseline.jpg",
            base_params={},
            budget=_stub_budget(),
            project_root=tmp_path,
            config=config,
            jury_profile=tiny_jury_profile,
            jury_profile_path=tmp_path / "profile.yaml",
        )
    assert result.loop_status == "jury_unavailable"
    sidecar = json.loads(
        (fake_render_dir / "V1_enhance_meta.json").read_text("utf-8")
    )
    assert sidecar["delivered_kind"] == "baseline"
    assert sidecar["errors"][0]["code"] == "exit_nonzero"


def test_gate3_5_empty_reason(
    tmp_path,
    fake_render_dir,
    fake_backend_adapter,
    tiny_loop_config,
    tiny_jury_profile,
    fake_view_verdict,
    monkeypatch,
):
    """spec §5 #4：jury 返非 None 但 reason='' → empty_reason（Gate-3.5）。"""
    verdict = fake_view_verdict(score=50, reason="")
    monkeypatch.setattr(
        "tools.jury_loop.orchestrator._call_jury_subprocess",
        lambda **kw: (verdict, None),
    )
    with fake_backend_adapter() as kind:
        config = tiny_loop_config(backend_kind=kind)
        result = run_loop_if_eligible(
            view="V1",
            backend_kind=kind,
            rc={},
            baseline_path=fake_render_dir / "V1_enhanced_baseline.jpg",
            base_params={},
            budget=_stub_budget(),
            project_root=tmp_path,
            config=config,
            jury_profile=tiny_jury_profile,
            jury_profile_path=tmp_path / "profile.yaml",
        )
    assert result.loop_status == "empty_reason"
    sidecar = json.loads(
        (fake_render_dir / "V1_enhance_meta.json").read_text("utf-8")
    )
    assert sidecar["baseline"]["photoreal_score"] == 50
    assert sidecar["baseline"]["reason"] == ""


# ==== Task 5.1.7：Gate-4/5/6/7（above_threshold / cost_capped / no_tags_parsed /
# no_rules_hit_no_llm）顶层 Step 4-7 集成测试 ==== #


def test_gate4_score_above_threshold(
    tmp_path,
    fake_render_dir,
    fake_backend_adapter,
    tiny_loop_config,
    tiny_jury_profile,
    fake_view_verdict,
    monkeypatch,
):
    """spec §5 #5：score=80 ≥ threshold=75 → above_threshold。"""
    monkeypatch.setattr(
        "tools.jury_loop.orchestrator._call_jury_subprocess",
        lambda **kw: (fake_view_verdict(score=80, reason="quite good"), None),
    )
    with fake_backend_adapter() as kind:
        config = tiny_loop_config(backend_kind=kind, threshold=75)
        result = run_loop_if_eligible(
            view="V1",
            backend_kind=kind,
            rc={},
            baseline_path=fake_render_dir / "V1_enhanced_baseline.jpg",
            base_params={},
            budget=_stub_budget(),
            project_root=tmp_path,
            config=config,
            jury_profile=tiny_jury_profile,
            jury_profile_path=tmp_path / "profile.yaml",
        )
    assert result.loop_status == "above_threshold"
    sidecar = json.loads(
        (fake_render_dir / "V1_enhance_meta.json").read_text("utf-8")
    )
    # spec §4.4 line 528 锁动态摘要含 score 数字
    assert "80" in sidecar["user_friendly_summary"]


def test_gate4_score_equals_threshold(
    tmp_path,
    fake_render_dir,
    fake_backend_adapter,
    tiny_loop_config,
    tiny_jury_profile,
    fake_view_verdict,
    monkeypatch,
):
    """spec §5 #5b：score=75=threshold 边界，锁 ≥ 而非 >。"""
    monkeypatch.setattr(
        "tools.jury_loop.orchestrator._call_jury_subprocess",
        lambda **kw: (fake_view_verdict(score=75, reason="exact threshold"), None),
    )
    with fake_backend_adapter() as kind:
        config = tiny_loop_config(backend_kind=kind, threshold=75)
        result = run_loop_if_eligible(
            view="V1",
            backend_kind=kind,
            rc={},
            baseline_path=fake_render_dir / "V1_enhanced_baseline.jpg",
            base_params={},
            budget=_stub_budget(),
            project_root=tmp_path,
            config=config,
            jury_profile=tiny_jury_profile,
            jury_profile_path=tmp_path / "profile.yaml",
        )
    assert result.loop_status == "above_threshold"


def test_gate5_budget_capped(
    tmp_path,
    fake_render_dir,
    fake_backend_adapter,
    tiny_loop_config,
    tiny_jury_profile,
    fake_view_verdict,
    monkeypatch,
):
    """spec §5 #6：budget cap 极小让 try_spend 返 False → cost_capped。"""
    monkeypatch.setattr(
        "tools.jury_loop.orchestrator._call_jury_subprocess",
        lambda **kw: (fake_view_verdict(score=58, reason="plastic look"), None),
    )
    # cap 0.001 远低于 estimate (0.05 base + 0.005 jury) → try_spend 必 False
    tiny_budget = LoopBudget(cap_usd=0.001, n_views=1)
    with fake_backend_adapter() as kind:
        config = tiny_loop_config(backend_kind=kind)
        result = run_loop_if_eligible(
            view="V1",
            backend_kind=kind,
            rc={},
            baseline_path=fake_render_dir / "V1_enhanced_baseline.jpg",
            base_params={},
            budget=tiny_budget,
            project_root=tmp_path,
            config=config,
            jury_profile=tiny_jury_profile,
            jury_profile_path=tmp_path / "profile.yaml",
        )
    assert result.loop_status == "cost_capped"
    sidecar = json.loads(
        (fake_render_dir / "V1_enhance_meta.json").read_text("utf-8")
    )
    # try_spend 返 False 未扣额度，sidecar.extra_cost_usd 必为 0
    assert sidecar["extra_cost_usd"] == 0


def test_gate6_no_tags_parsed(
    tmp_path,
    fake_render_dir,
    fake_backend_adapter,
    tiny_loop_config,
    tiny_jury_profile,
    fake_view_verdict,
    monkeypatch,
):
    """spec §5 #7：reason 全 ASCII 不含已知 tag → no_tags_parsed。"""
    monkeypatch.setattr(
        "tools.jury_loop.orchestrator._call_jury_subprocess",
        lambda **kw: (fake_view_verdict(score=58, reason="abc xyz blah"), None),
    )
    with fake_backend_adapter() as kind:
        config = tiny_loop_config(backend_kind=kind)
        result = run_loop_if_eligible(
            view="V1",
            backend_kind=kind,
            rc={},
            baseline_path=fake_render_dir / "V1_enhanced_baseline.jpg",
            base_params={},
            budget=_stub_budget(),
            project_root=tmp_path,
            config=config,
            jury_profile=tiny_jury_profile,
            jury_profile_path=tmp_path / "profile.yaml",
        )
    assert result.loop_status == "no_tags_parsed"
    sidecar = json.loads(
        (fake_render_dir / "V1_enhance_meta.json").read_text("utf-8")
    )
    assert sidecar["tags_parsed"] == []


def test_gate7_all_miss_llm_fallback_off(
    tmp_path,
    fake_render_dir,
    fake_backend_adapter,
    tiny_loop_config,
    tiny_jury_profile,
    fake_view_verdict,
    user_yaml_with_tag_no_rule,
    monkeypatch,
):
    """spec §5 #8：reason 含用户 yaml 扩展的 tag (无 rule) + llm_fallback=False
    → no_rules_hit_no_llm。
    """
    # reason 含 "weird vibe" 命中 user_yaml_with_tag_no_rule 中的
    # unknown_aesthetic_tag 但 rules: [] 故无规则匹配
    monkeypatch.setattr(
        "tools.jury_loop.orchestrator._call_jury_subprocess",
        lambda **kw: (
            fake_view_verdict(score=58, reason="weird vibe everywhere"),
            None,
        ),
    )
    with fake_backend_adapter() as kind:
        config = tiny_loop_config(
            backend_kind=kind,
            llm_fallback=False,
            rule_table_path=user_yaml_with_tag_no_rule,
        )
        result = run_loop_if_eligible(
            view="V1",
            backend_kind=kind,
            rc={},
            baseline_path=fake_render_dir / "V1_enhanced_baseline.jpg",
            base_params={},
            budget=_stub_budget(),
            project_root=tmp_path,
            config=config,
            jury_profile=tiny_jury_profile,
            jury_profile_path=tmp_path / "profile.yaml",
        )
    assert result.loop_status == "no_rules_hit_no_llm"


# ==== Task 5.1.8：retry 调用 + Gate-8 + score_select + _finalize 主流程 ==== #
# spec §5 矩阵 #9-#16：
#   #9-#12：4 类 BackendError 通过集成路径分类
#   #13：retry 提分 → delivered_retry
#   #14：retry 降分 → delivered_baseline + retry verdict 仍含完整字段
#   #15：actual_cost_usd=None → warnings 含 cost_estimated_only
#   #16：force_retry 策略不二轮评分（5 字段约束）

from tools.jury_loop.backends import BackendResponse  # noqa: E402  Task 5.1.8 集成路径需要


@pytest.mark.parametrize("exc_cls, expected_status, expected_code", [
    (BackendAuthError, "retry_auth_failed", "backend_auth_error"),
    (BackendRateLimitError, "retry_rate_limited", "backend_rate_limited"),
    (BackendQuotaExceededError, "retry_quota_exceeded", "backend_quota_exceeded"),
    (BackendCallError, "retry_failed", "backend_call_error"),
])
def test_gate8_backend_error_classification_integration(
    tmp_path,
    fake_render_dir,
    fake_backend_adapter,
    tiny_loop_config,
    tiny_jury_profile,
    fake_view_verdict,
    monkeypatch,
    exc_cls,
    expected_status,
    expected_code,
):
    """spec §5 #9-#12：4 类 BackendError 通过 orchestrator 集成路径分类。

    reason='plastic look, flat lighting' 命中内置规则 → 走到 Step 8 adapter.call →
    raises 触发 Gate-8 分类 → 写富 sidecar.errors[]。
    """
    monkeypatch.setattr(
        "tools.jury_loop.orchestrator._call_jury_subprocess",
        lambda **kw: (
            fake_view_verdict(score=58, reason="plastic look, flat lighting"),
            None,
        ),
    )
    with fake_backend_adapter(raises=exc_cls("vendor 错误")) as kind:
        config = tiny_loop_config(backend_kind=kind)
        result = run_loop_if_eligible(
            view="V1",
            backend_kind=kind,
            rc={"prompt": "test"},
            baseline_path=fake_render_dir / "V1_enhanced_baseline.jpg",
            base_params={},
            budget=LoopBudget(cap_usd=1.5, n_views=1),
            project_root=tmp_path,
            config=config,
            jury_profile=tiny_jury_profile,
            jury_profile_path=tmp_path / "profile.yaml",
        )
    assert result.loop_status == expected_status
    sidecar = json.loads(
        (fake_render_dir / "V1_enhance_meta.json").read_text("utf-8")
    )
    assert sidecar["errors"][0]["code"] == expected_code
    # baseline-only 退出路径：delivered_kind="baseline" + final 文件存在
    assert sidecar["delivered_kind"] == "baseline"
    assert (fake_render_dir / "V1_enhanced.jpg").is_file()


def test_normal_retry_improves_score(
    tmp_path,
    fake_render_dir,
    fake_backend_adapter,
    tiny_loop_config,
    tiny_jury_profile,
    fake_jury_sequence,
    monkeypatch,
):
    """spec §5 #13：retry score=80 > baseline=58 → delivered_retry + score_delta=22。"""
    next_jury = fake_jury_sequence(
        [(58, "plastic look, flat lighting"), (80, "metallic finish")]
    )
    monkeypatch.setattr(
        "tools.jury_loop.orchestrator._call_jury_subprocess",
        lambda **kw: (next_jury(), None),
    )
    response = BackendResponse(
        output_image_path=fake_render_dir / "V1_enhanced_retry.jpg",
        actual_cost_usd=0.04,
        raw_request_summary={"cfg_scale": 7.5},
    )
    # _finalize rename 需要 retry 文件存在
    (fake_render_dir / "V1_enhanced_retry.jpg").write_bytes(b"\x89PNG\r\n\x1a\n")
    with fake_backend_adapter(call_returns=response) as kind:
        config = tiny_loop_config(backend_kind=kind)
        result = run_loop_if_eligible(
            view="V1",
            backend_kind=kind,
            rc={"prompt": "test"},
            baseline_path=fake_render_dir / "V1_enhanced_baseline.jpg",
            base_params={},
            budget=LoopBudget(cap_usd=1.5, n_views=1),
            project_root=tmp_path,
            config=config,
            jury_profile=tiny_jury_profile,
            jury_profile_path=tmp_path / "profile.yaml",
        )
    assert result.loop_status == "delivered_retry"
    sidecar = json.loads(
        (fake_render_dir / "V1_enhance_meta.json").read_text("utf-8")
    )
    assert sidecar["delivered_kind"] == "retry"
    assert sidecar["retry_score_delta"] == 22
    assert sidecar["delivered_score_delta"] == 22


def test_normal_retry_degrades_score(
    tmp_path,
    fake_render_dir,
    fake_backend_adapter,
    tiny_loop_config,
    tiny_jury_profile,
    fake_jury_sequence,
    monkeypatch,
):
    """spec §5 #14：retry=50 < baseline=58 → delivered_baseline + retry 字段含完整 verdict。

    父 spec line 531：保守退 baseline 时 sidecar.retry 仍含 retry candidate 的
    完整 verdict（observability：让用户知道二轮跑了什么），不该写 None。
    """
    next_jury = fake_jury_sequence(
        [(58, "plastic look, flat lighting"), (50, "still plastic")]
    )
    monkeypatch.setattr(
        "tools.jury_loop.orchestrator._call_jury_subprocess",
        lambda **kw: (next_jury(), None),
    )
    response = BackendResponse(
        output_image_path=fake_render_dir / "V1_enhanced_retry.jpg",
        actual_cost_usd=0.04,
        raw_request_summary={},
    )
    (fake_render_dir / "V1_enhanced_retry.jpg").write_bytes(b"\x89PNG\r\n\x1a\n")
    with fake_backend_adapter(call_returns=response) as kind:
        config = tiny_loop_config(backend_kind=kind)
        result = run_loop_if_eligible(
            view="V1",
            backend_kind=kind,
            rc={"prompt": "test"},
            baseline_path=fake_render_dir / "V1_enhanced_baseline.jpg",
            base_params={},
            budget=LoopBudget(cap_usd=1.5, n_views=1),
            project_root=tmp_path,
            config=config,
            jury_profile=tiny_jury_profile,
            jury_profile_path=tmp_path / "profile.yaml",
        )
    assert result.loop_status == "delivered_baseline"
    sidecar = json.loads(
        (fake_render_dir / "V1_enhance_meta.json").read_text("utf-8")
    )
    assert sidecar["delivered_kind"] == "baseline"
    assert sidecar["retry_score_delta"] == -8
    assert sidecar["delivered_score_delta"] == 0
    # 父 spec line 531：retry 字段仍含完整 verdict
    assert sidecar["retry"] is not None
    assert sidecar["retry"]["photoreal_score"] == 50


def test_actual_cost_none_adds_cost_estimated_only_warning(
    tmp_path,
    fake_render_dir,
    fake_backend_adapter,
    tiny_loop_config,
    tiny_jury_profile,
    fake_jury_sequence,
    monkeypatch,
):
    """spec §5 #15：BackendResponse.actual_cost_usd=None → sidecar.warnings 含 cost_estimated_only。"""
    next_jury = fake_jury_sequence(
        [(58, "plastic look, flat lighting"), (80, "metallic")]
    )
    monkeypatch.setattr(
        "tools.jury_loop.orchestrator._call_jury_subprocess",
        lambda **kw: (next_jury(), None),
    )
    response = BackendResponse(
        output_image_path=fake_render_dir / "V1_enhanced_retry.jpg",
        actual_cost_usd=None,  # 关键：不调 record_actual + 加 warning
        raw_request_summary={},
    )
    (fake_render_dir / "V1_enhanced_retry.jpg").write_bytes(b"\x89PNG\r\n\x1a\n")
    with fake_backend_adapter(call_returns=response) as kind:
        config = tiny_loop_config(backend_kind=kind)
        run_loop_if_eligible(
            view="V1",
            backend_kind=kind,
            rc={"prompt": "test"},
            baseline_path=fake_render_dir / "V1_enhanced_baseline.jpg",
            base_params={},
            budget=LoopBudget(cap_usd=1.5, n_views=1),
            project_root=tmp_path,
            config=config,
            jury_profile=tiny_jury_profile,
            jury_profile_path=tmp_path / "profile.yaml",
        )
    sidecar = json.loads(
        (fake_render_dir / "V1_enhance_meta.json").read_text("utf-8")
    )
    assert "cost_estimated_only" in sidecar["warnings"]


def test_force_retry_strategy_skips_second_jury(
    tmp_path,
    fake_render_dir,
    fake_backend_adapter,
    tiny_loop_config,
    tiny_jury_profile,
    fake_view_verdict,
    monkeypatch,
):
    """spec §5 #16：force_retry → retry.photoreal_score=null + final_prompt 非空 + score_delta=null。

    父 spec line 530 force_retry 5 字段约束：
    - retry.photoreal_score=null
    - retry.semantic_checks=null
    - retry.reason=null
    - retry.final_prompt 非空（写实际发给 backend 的 prompt）
    - retry.backend_payload 非空（adapter response.raw_request_summary）
    """
    monkeypatch.setattr(
        "tools.jury_loop.orchestrator._call_jury_subprocess",
        lambda **kw: (
            fake_view_verdict(score=58, reason="plastic look, flat lighting"),
            None,
        ),
    )
    response = BackendResponse(
        output_image_path=fake_render_dir / "V1_enhanced_retry.jpg",
        actual_cost_usd=0.04,
        raw_request_summary={"cfg_scale": 7.5},
    )
    (fake_render_dir / "V1_enhanced_retry.jpg").write_bytes(b"\x89PNG\r\n\x1a\n")
    with fake_backend_adapter(call_returns=response) as kind:
        config = tiny_loop_config(
            backend_kind=kind, score_select_strategy="force_retry"
        )
        result = run_loop_if_eligible(
            view="V1",
            backend_kind=kind,
            rc={"prompt": "test"},
            baseline_path=fake_render_dir / "V1_enhanced_baseline.jpg",
            base_params={},
            budget=LoopBudget(cap_usd=1.5, n_views=1),
            project_root=tmp_path,
            config=config,
            jury_profile=tiny_jury_profile,
            jury_profile_path=tmp_path / "profile.yaml",
        )
    assert result.loop_status == "delivered_retry"
    sidecar = json.loads(
        (fake_render_dir / "V1_enhance_meta.json").read_text("utf-8")
    )
    # force_retry 5 字段约束（父 spec line 530）
    assert sidecar["retry"]["photoreal_score"] is None
    assert sidecar["retry"]["semantic_checks"] is None
    assert sidecar["retry"]["reason"] is None
    assert sidecar["retry"]["final_prompt"]  # 非空
    assert sidecar["retry"]["backend_payload"]  # 非空
    assert sidecar["retry_score_delta"] is None
    assert sidecar["delivered_score_delta"] is None


def test_unknown_exception_invokes_degraded_sidecar(
    tmp_path,
    fake_render_dir,
    fake_backend_adapter,
    tiny_loop_config,
    tiny_jury_profile,
    fake_view_verdict,
    monkeypatch,
):
    """spec §5 #22：未知 Exception (rule_table.lookup 抛 ValueError) →
    write_degraded_sidecar 被调一次后 re-raise；防 cmd_enhance 视角级 try/except
    再 write 一次形成无限循环（spec rev 3 决议 #6）。
    """
    # 拦截 metadata.write_degraded_sidecar，统计调用次数 + 透传给原函数保留副作用
    write_degraded_calls: list[dict] = []
    from tools.jury_loop import metadata as _metadata

    original = _metadata.write_degraded_sidecar

    def _mock_degraded(*args, **kwargs):
        write_degraded_calls.append(dict(kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(
        "tools.jury_loop.orchestrator.metadata.write_degraded_sidecar",
        _mock_degraded,
    )
    # 让 jury 第一次评 baseline 返低分 verdict（驱动主流程进 Step 5/6/7）
    monkeypatch.setattr(
        "tools.jury_loop.orchestrator._call_jury_subprocess",
        lambda **kw: (
            fake_view_verdict(score=58, reason="plastic look, flat lighting"),
            None,
        ),
    )
    # 让 rule_table.lookup 抛未知 ValueError（不在 BackendError 4 类内 → 落到顶层 except）
    def _raise_unknown(*_args: object, **_kwargs: object) -> None:
        raise ValueError("oops 内部错误")

    monkeypatch.setattr(
        "tools.jury_loop.orchestrator.rule_table.lookup",
        _raise_unknown,
    )

    with fake_backend_adapter() as kind:
        config = tiny_loop_config(backend_kind=kind)
        with pytest.raises(ValueError, match="oops 内部错误"):
            run_loop_if_eligible(
                view="V1",
                backend_kind=kind,
                rc={"prompt": "test"},
                baseline_path=fake_render_dir / "V1_enhanced_baseline.jpg",
                base_params={},
                budget=LoopBudget(cap_usd=1.5, n_views=1),
                project_root=tmp_path,
                config=config,
                jury_profile=tiny_jury_profile,
                jury_profile_path=tmp_path / "profile.yaml",
            )
    assert (
        len(write_degraded_calls) == 1
    ), "未知 Exception 应触发 write_degraded_sidecar 仅 1 次"
    # 校验落地 sidecar 内容（透传 original 已写）：retry_failed + 错误码记录
    sidecar = json.loads(
        (fake_render_dir / "V1_enhance_meta.json").read_text("utf-8")
    )
    assert sidecar["loop_status"] == "retry_failed"
    assert any(
        e.get("code") == "cmd_enhance_uncaught_exception" for e in sidecar["errors"]
    )


# ==== Task 6.1.3：SEC-MINOR-4 stdout cap 防 OOM ==== #


def test_call_jury_subprocess_stdout_overflow_kills_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SEC-MINOR-4：stdout > 1 MiB → 立即 kill 子进程 + 返 (None, "stdout_overflow")。"""
    import subprocess
    from unittest.mock import MagicMock
    from tools.jury_loop import orchestrator as orch

    # 制造 > 1 MiB stdout（按 64 KiB chunk 分段，模拟真实子进程渐进输出）
    overflow_bytes = b"x" * (1024 * 1024 + 1024)  # 1 MiB + 1 KiB
    chunks = [overflow_bytes[i:i + 65536] for i in range(0, len(overflow_bytes), 65536)]
    chunks.append(b"")  # EOF sentinel

    fake_proc = MagicMock()
    fake_proc.stdout.read.side_effect = chunks
    fake_proc.stderr.read.return_value = b""
    fake_proc.returncode = 0
    fake_proc.poll.return_value = None

    captured_popen_args: dict = {}

    def _fake_popen(cmd, **kwargs):  # noqa: ANN001
        captured_popen_args["cmd"] = cmd
        captured_popen_args["kwargs"] = kwargs
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

    assert verdict is None
    assert err_code == "stdout_overflow"
    fake_proc.kill.assert_called()  # 溢出时必须 kill
    # 校验 Popen 用 PIPE 收 stdout/stderr（不是 capture_output）
    assert captured_popen_args["kwargs"].get("stdout") == subprocess.PIPE
    assert captured_popen_args["kwargs"].get("stderr") == subprocess.PIPE
