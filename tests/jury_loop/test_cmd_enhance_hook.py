"""CP-7 Task 7.1.2：`cmd_enhance_hook` 模块单元测试。

测试两个公开函数：
- `prepare_jury_loop_state`：config 加载 + jury_profile 加载 + LoopBudget 实例化
- `run_loop_hook_for_view`：异常隔离 / fast-path 跳过 / v1_anchor 状态传递

通过 monkeypatch `tools.jury.config.load_jury_config` 与
`tools.jury_loop.cmd_enhance_hook.orchestrator.run_loop_if_eligible` 隔离外部依赖。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from enhance_budget import LoopBudget
from tools.jury_loop import cmd_enhance_hook
from tools.jury_loop.config import (
    DEFAULT_JURY_LOOP_DICT,
    JuryLoopConfig,
    load_jury_loop_config,
)


# ════════════════════════════════════════════════════════════════════════════
# resolve_jury_config_path
# ════════════════════════════════════════════════════════════════════════════


def test_resolve_jury_config_path_under_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """jury config 路径在 ~/.claude/cad_jury_config.json。"""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert cmd_enhance_hook.resolve_jury_config_path() == tmp_path / ".claude" / "cad_jury_config.json"


# ════════════════════════════════════════════════════════════════════════════
# prepare_jury_loop_state
# ════════════════════════════════════════════════════════════════════════════


def _stub_load_jury_config(monkeypatch: pytest.MonkeyPatch, *, raises: Exception | None = None,
                            profile: Any = None, caps: Any = None) -> None:
    """注入 fake load_jury_config。"""
    def _fake(path: Path) -> tuple[Any, Any]:
        if raises is not None:
            raise raises
        return (profile or object(), caps or object())
    # 注入到 prepare_jury_loop_state 内部 from tools.jury.config import 触发的 binding
    monkeypatch.setattr("tools.jury.config.load_jury_config", _fake)


def test_prepare_disabled_when_jury_loop_enabled_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """enhance.jury_loop.enabled=false → 整体禁用，返 (None, None, None, None)。"""
    pcfg = {"enhance": {"jury_loop": {**DEFAULT_JURY_LOOP_DICT, "enabled": False}}}
    result = cmd_enhance_hook.prepare_jury_loop_state(pipeline_config=pcfg, n_views=3)
    assert result == (None, None, None, None)


def test_prepare_disabled_when_config_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    """无效 jury_loop dict（顶层与 advanced 同名碰撞）→ 整体禁用。"""
    bad = {**DEFAULT_JURY_LOOP_DICT, "threshold": 75}  # threshold 在顶层 + advanced 共存
    pcfg = {"enhance": {"jury_loop": bad}}
    result = cmd_enhance_hook.prepare_jury_loop_state(pipeline_config=pcfg, n_views=3)
    assert result == (None, None, None, None)


def test_prepare_falls_back_to_default_when_pipeline_missing_section(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """pipeline_config 无 enhance.jury_loop 段 → 用 DEFAULT_JURY_LOOP_DICT。"""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _stub_load_jury_config(monkeypatch, profile=object())  # jury config 假装能加载
    pcfg: dict[str, Any] = {}  # 完全没有 enhance 段
    jl_cfg, budget, profile, profile_path = cmd_enhance_hook.prepare_jury_loop_state(
        pipeline_config=pcfg, n_views=5,
    )
    assert isinstance(jl_cfg, JuryLoopConfig)
    assert jl_cfg.enabled is True
    assert jl_cfg.backend.kind == "gemini_chat_image"
    assert isinstance(budget, LoopBudget)
    assert budget.cap_usd == 1.5
    assert profile is not None
    assert profile_path == tmp_path / ".claude" / "cad_jury_config.json"


def test_prepare_disabled_when_jury_profile_file_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """jury_profile 文件不存在 → 视为整体禁用。"""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)  # ~/.claude/cad_jury_config.json 不存在
    # 让真实 load_jury_config 跑（不 stub），它会抛 JuryConfigError
    result = cmd_enhance_hook.prepare_jury_loop_state(pipeline_config={}, n_views=2)
    assert result == (None, None, None, None)


def test_prepare_disabled_when_jury_profile_schema_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """jury_profile schema 错 → 整体禁用（不 raise，hook 跳过即可）。"""
    from tools.jury.config import JuryConfigSchemaError
    _stub_load_jury_config(monkeypatch, raises=JuryConfigSchemaError("bad schema"))
    result = cmd_enhance_hook.prepare_jury_loop_state(pipeline_config={}, n_views=2)
    assert result == (None, None, None, None)


# ════════════════════════════════════════════════════════════════════════════
# run_loop_hook_for_view
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def loaded_config() -> JuryLoopConfig:
    """真实加载 DEFAULT_JURY_LOOP_DICT 得到 JuryLoopConfig 实例。"""
    return load_jury_loop_config(DEFAULT_JURY_LOOP_DICT)


@pytest.fixture
def real_budget(loaded_config: JuryLoopConfig) -> LoopBudget:
    """真实 LoopBudget 实例（容量 1.5 USD / 3 视角）。"""
    return LoopBudget(cap_usd=loaded_config.cost_cap_usd, n_views=3)


@pytest.fixture
def baseline_file(tmp_path: Path) -> Path:
    """tmp_path 下创建一份假 baseline 文件（V1_<ts>_enhanced.jpg）。"""
    p = tmp_path / "V1_20260512_1430_enhanced.jpg"
    p.write_bytes(b"\xff\xd8\xff\xe0fakejpeg")
    return p


def _make_loop_result(final_path: Path, loop_status: str = "delivered_retry") -> Any:
    """构造 LoopResult — 用 orchestrator 真实 dataclass 保证字段一致。"""
    from tools.jury_loop.orchestrator import LoopResult
    return LoopResult(final_path=final_path, loop_status=loop_status)


def test_hook_returns_none_when_jury_loop_config_none(tmp_path: Path) -> None:
    """jury_loop_config=None → 直接返 None（hook 整体禁用）。"""
    ret = cmd_enhance_hook.run_loop_hook_for_view(
        view_key="V1", new_path=None, render_dir=tmp_path, rc={},
        rerun_loop=False, jury_loop_config=None, loop_budget=None,
        jury_profile=None, jury_profile_path=None, reference_mode="none",
        project_root=tmp_path,
    )
    assert ret is None


def test_hook_returns_none_when_new_path_missing(
    loaded_config: JuryLoopConfig, real_budget: LoopBudget, tmp_path: Path,
) -> None:
    """new_path=None（baseline enhance 未定位产物）→ 跳过 hook。"""
    ret = cmd_enhance_hook.run_loop_hook_for_view(
        view_key="V1", new_path=None, render_dir=tmp_path, rc={},
        rerun_loop=False, jury_loop_config=loaded_config, loop_budget=real_budget,
        jury_profile=object(), jury_profile_path=tmp_path / "fake.json",
        reference_mode="none", project_root=tmp_path,
    )
    assert ret is None


def test_hook_returns_none_when_new_path_file_missing(
    loaded_config: JuryLoopConfig, real_budget: LoopBudget, tmp_path: Path,
) -> None:
    """new_path 字符串非空但文件不存在 → 跳过 hook。"""
    ret = cmd_enhance_hook.run_loop_hook_for_view(
        view_key="V1", new_path=str(tmp_path / "nonexistent.jpg"),
        render_dir=tmp_path, rc={}, rerun_loop=False,
        jury_loop_config=loaded_config, loop_budget=real_budget,
        jury_profile=object(), jury_profile_path=tmp_path / "fake.json",
        reference_mode="none", project_root=tmp_path,
    )
    assert ret is None


def test_hook_fast_path_skip_when_sidecar_terminal(
    monkeypatch: pytest.MonkeyPatch, loaded_config: JuryLoopConfig,
    real_budget: LoopBudget, baseline_file: Path, tmp_path: Path,
) -> None:
    """既有 V1_enhance_meta.json `loop_status=delivered_retry` + rerun=False → 跳过且 orchestrator 不被调。"""
    (tmp_path / "V1_enhance_meta.json").write_text(
        json.dumps({"$schema_version": 1, "view": "V1", "loop_status": "delivered_retry"}),
        encoding="utf-8",
    )
    call_count = [0]

    def _fail_if_called(**_kwargs: Any) -> Any:
        call_count[0] += 1
        raise AssertionError("orchestrator 不应被调用")

    monkeypatch.setattr(cmd_enhance_hook.orchestrator, "run_loop_if_eligible", _fail_if_called)

    ret = cmd_enhance_hook.run_loop_hook_for_view(
        view_key="V1", new_path=str(baseline_file), render_dir=tmp_path, rc={},
        rerun_loop=False, jury_loop_config=loaded_config, loop_budget=real_budget,
        jury_profile=object(), jury_profile_path=tmp_path / "fake.json",
        reference_mode="none", project_root=tmp_path,
    )
    assert ret is None
    assert call_count[0] == 0


def test_hook_runs_and_returns_none_for_v2_in_v1_anchor(
    monkeypatch: pytest.MonkeyPatch, loaded_config: JuryLoopConfig,
    real_budget: LoopBudget, baseline_file: Path, tmp_path: Path,
) -> None:
    """hook 正常跑 + view=V2 + v1_anchor → 返 None（不更新 hero_image）。"""
    monkeypatch.setattr(
        cmd_enhance_hook.orchestrator, "run_loop_if_eligible",
        lambda **_k: _make_loop_result(tmp_path / "V2_enhanced.jpg", "delivered_retry"),
    )
    ret = cmd_enhance_hook.run_loop_hook_for_view(
        view_key="V2", new_path=str(baseline_file), render_dir=tmp_path, rc={},
        rerun_loop=False, jury_loop_config=loaded_config, loop_budget=real_budget,
        jury_profile=object(), jury_profile_path=tmp_path / "fake.json",
        reference_mode="v1_anchor", project_root=tmp_path,
    )
    assert ret is None


def test_hook_returns_final_path_for_v1_in_v1_anchor(
    monkeypatch: pytest.MonkeyPatch, loaded_config: JuryLoopConfig,
    real_budget: LoopBudget, baseline_file: Path, tmp_path: Path,
) -> None:
    """BL-4：hook 正常跑 + view=V1 + v1_anchor → 返 final_path 字符串供 hero_image 用。"""
    final = tmp_path / "V1_enhanced.jpg"
    monkeypatch.setattr(
        cmd_enhance_hook.orchestrator, "run_loop_if_eligible",
        lambda **_k: _make_loop_result(final, "delivered_retry"),
    )
    ret = cmd_enhance_hook.run_loop_hook_for_view(
        view_key="V1", new_path=str(baseline_file), render_dir=tmp_path, rc={},
        rerun_loop=False, jury_loop_config=loaded_config, loop_budget=real_budget,
        jury_profile=object(), jury_profile_path=tmp_path / "fake.json",
        reference_mode="v1_anchor", project_root=tmp_path,
    )
    assert ret == str(final)


def test_hook_returns_none_for_v1_when_reference_mode_none(
    monkeypatch: pytest.MonkeyPatch, loaded_config: JuryLoopConfig,
    real_budget: LoopBudget, baseline_file: Path, tmp_path: Path,
) -> None:
    """reference_mode='none' + V1 → 即使 hook 跑也返 None（不传 hero）。"""
    monkeypatch.setattr(
        cmd_enhance_hook.orchestrator, "run_loop_if_eligible",
        lambda **_k: _make_loop_result(tmp_path / "V1_enhanced.jpg", "delivered_retry"),
    )
    ret = cmd_enhance_hook.run_loop_hook_for_view(
        view_key="V1", new_path=str(baseline_file), render_dir=tmp_path, rc={},
        rerun_loop=False, jury_loop_config=loaded_config, loop_budget=real_budget,
        jury_profile=object(), jury_profile_path=tmp_path / "fake.json",
        reference_mode="none", project_root=tmp_path,
    )
    assert ret is None


def test_hook_isolates_filenotfounderror(
    monkeypatch: pytest.MonkeyPatch, loaded_config: JuryLoopConfig,
    real_budget: LoopBudget, baseline_file: Path, tmp_path: Path,
) -> None:
    """orchestrator raise FileNotFoundError → log + 返 None，不 propagate。"""
    def _raise(**_k: Any) -> Any:
        raise FileNotFoundError("baseline gone")
    monkeypatch.setattr(cmd_enhance_hook.orchestrator, "run_loop_if_eligible", _raise)

    ret = cmd_enhance_hook.run_loop_hook_for_view(
        view_key="V1", new_path=str(baseline_file), render_dir=tmp_path, rc={},
        rerun_loop=False, jury_loop_config=loaded_config, loop_budget=real_budget,
        jury_profile=object(), jury_profile_path=tmp_path / "fake.json",
        reference_mode="v1_anchor", project_root=tmp_path,
    )
    assert ret is None


def test_hook_isolates_valueerror(
    monkeypatch: pytest.MonkeyPatch, loaded_config: JuryLoopConfig,
    real_budget: LoopBudget, baseline_file: Path, tmp_path: Path,
) -> None:
    """orchestrator raise ValueError（view 名注入）→ log + 返 None。"""
    def _raise(**_k: Any) -> Any:
        raise ValueError("invalid view name")
    monkeypatch.setattr(cmd_enhance_hook.orchestrator, "run_loop_if_eligible", _raise)

    ret = cmd_enhance_hook.run_loop_hook_for_view(
        view_key="V1", new_path=str(baseline_file), render_dir=tmp_path, rc={},
        rerun_loop=False, jury_loop_config=loaded_config, loop_budget=real_budget,
        jury_profile=object(), jury_profile_path=tmp_path / "fake.json",
        reference_mode="v1_anchor", project_root=tmp_path,
    )
    assert ret is None


def test_hook_isolates_unknown_exception(
    monkeypatch: pytest.MonkeyPatch, loaded_config: JuryLoopConfig,
    real_budget: LoopBudget, baseline_file: Path, tmp_path: Path,
) -> None:
    """DRIFT-MAJOR-7：orchestrator raise 未知 Exception → log + 返 None。"""
    def _raise(**_k: Any) -> Any:
        raise RuntimeError("boom")
    monkeypatch.setattr(cmd_enhance_hook.orchestrator, "run_loop_if_eligible", _raise)

    ret = cmd_enhance_hook.run_loop_hook_for_view(
        view_key="V1", new_path=str(baseline_file), render_dir=tmp_path, rc={},
        rerun_loop=False, jury_loop_config=loaded_config, loop_budget=real_budget,
        jury_profile=object(), jury_profile_path=tmp_path / "fake.json",
        reference_mode="v1_anchor", project_root=tmp_path,
    )
    assert ret is None


def test_hook_passes_correct_args_to_orchestrator(
    monkeypatch: pytest.MonkeyPatch, loaded_config: JuryLoopConfig,
    real_budget: LoopBudget, baseline_file: Path, tmp_path: Path,
) -> None:
    """传给 orchestrator.run_loop_if_eligible 的 kwargs 与 plan §Task 7.1.2 一致。"""
    captured: dict[str, Any] = {}

    def _capture(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return _make_loop_result(tmp_path / "V1_enhanced.jpg", "delivered_retry")

    monkeypatch.setattr(cmd_enhance_hook.orchestrator, "run_loop_if_eligible", _capture)
    profile_obj = object()
    profile_path = tmp_path / "fake_jury.json"
    cmd_enhance_hook.run_loop_hook_for_view(
        view_key="V1", new_path=str(baseline_file), render_dir=tmp_path,
        rc={"subsystem": "demo"}, rerun_loop=False,
        jury_loop_config=loaded_config, loop_budget=real_budget,
        jury_profile=profile_obj, jury_profile_path=profile_path,
        reference_mode="v1_anchor", project_root=tmp_path,
    )
    assert captured["view"] == "V1"
    assert captured["backend_kind"] == "gemini_chat_image"
    assert captured["rc"] == {"subsystem": "demo"}
    assert captured["baseline_path"] == baseline_file
    assert captured["base_params"] == {}
    assert captured["budget"] is real_budget
    assert captured["project_root"] == tmp_path
    assert captured["config"] is loaded_config
    assert captured["jury_profile"] is profile_obj
    assert captured["jury_profile_path"] == profile_path
