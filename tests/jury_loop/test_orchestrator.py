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
