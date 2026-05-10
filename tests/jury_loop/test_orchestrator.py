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


@pytest.mark.parametrize("exc_cls, expected_status, expected_code", [
    (BackendAuthError, "retry_auth_failed", "backend_auth_error"),
    (BackendRateLimitError, "retry_rate_limited", "backend_rate_limited"),
    (BackendQuotaExceededError, "retry_quota_exceeded", "backend_quota_exceeded"),
    (BackendCallError, "retry_failed", "backend_call_error"),
])
def test_classify_backend_error_4_known_subclasses(
    exc_cls: type[BackendError], expected_status: str, expected_code: str,
) -> None:
    """spec rev 3 决议 #10：4 类已知 BackendError 子类的分类与 errors[].code 对齐。"""
    loop_status, error_entry = _classify_backend_error(exc_cls("vendor 错误"))
    assert loop_status == expected_status
    assert error_entry["code"] == expected_code
    assert "vendor 错误" in error_entry["message_summary"]
    assert error_entry["user_action_hint"]  # 非空


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
