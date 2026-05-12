"""L4 smoke — jury→prompt 闭环端到端（CP-8 Task 8.2 / §11 follow-up B2）。

CI 默认全 skip（conftest hook：无 GEMINI_API_KEY → skip）。本地手动跑需：
  - GEMINI_API_KEY            retry backend (gemini_chat_image) 的 key
  - CAD_JURY_LLM_API_KEY      vision-LLM jury 的 api_key（写进 test 自带的临时 cad_jury_config.json）
  - CAD_JURY_LLM_BASE_URL     vision-LLM jury 的 OpenAI 兼容 base url（如 https://你的中转.com/v1）
  - （可选）CAD_JURY_LLM_MODEL vision 模型名，默认 gemini-2.5-flash
跑：  $env:GEMINI_API_KEY="..."; $env:CAD_JURY_LLM_API_KEY="..."; $env:CAD_JURY_LLM_BASE_URL="..."
      python -m pytest tests/jury_loop/test_l4_smoke.py -v
要花真钱（每 case ~$0.1-4）；DRIFT-MINOR-8（git-LFS 验证过的真低分 render fixture）仍延期，本文件用合成图。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from enhance_budget import LoopBudget
from tools.jury.config import load_jury_config
from tools.jury_loop import cmd_enhance_hook
from tools.jury_loop.config import DEFAULT_JURY_LOOP_DICT, load_jury_loop_config
from tools.jury_loop.orchestrator import run_loop_if_eligible

_SMOKE_RUNS = 3  # 原 plan 是 10（跑 10 次取均值抑制 jury 方差）；3 已够 smoke、调高更稳更贵
_BASE_PROMPT = "photorealistic product render, studio lighting, neutral background, high detail"

pytestmark = [pytest.mark.requires_jury_loop_e2e, pytest.mark.slow]


def _make_rough_render_png(path: Path, size: tuple[int, int] = (512, 512)) -> Path:
    """合成一张「未完成的 Blender 渲染」样子的低保真 PNG（平涂背景 + 单个简单几何体）。"""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", size, (200, 200, 205))  # 平涂浅灰背景
    d = ImageDraw.Draw(img)
    cx, cy = size[0] // 2, size[1] // 2
    d.rectangle([cx - 90, cy - 60, cx + 90, cy + 60], fill=(120, 120, 130))  # 平涂方块，无着色/贴图/阴影
    img.save(path, "PNG")
    return path


def _require_jury_env() -> None:
    """conftest hook 已 gate GEMINI_API_KEY；这里再 runtime 检 jury LLM 的两个 env var。"""
    if not os.environ.get("CAD_JURY_LLM_API_KEY"):
        pytest.skip("CAD_JURY_LLM_API_KEY 未设")
    if not os.environ.get("CAD_JURY_LLM_BASE_URL"):
        pytest.skip("CAD_JURY_LLM_BASE_URL 未设")


def _write_temp_jury_config() -> Path:
    """写 test 自带的临时 cad_jury_config.json 到 **假 home 的 ~/.claude/** 下。

    为什么这个位置（Task 0 确认）：orchestrator 的 _call_jury_subprocess 调
    `python -m tools.photo3d_jury --single-view ... --config <path>` 时**不**传
    --allow-external-config，所以 photo3d_jury 只接受 config 在「~/.claude/ 下」或
    「当前项目内」。conftest 的 autouse fixture 把 HOME/USERPROFILE env 替成假 tmp 目录
    （photo3d_jury.py 用 os.environ.get("USERPROFILE") or os.environ.get("HOME") 算 ~），
    所以写到那个假 home 的 .claude/ 下、子进程就认它在 ~/.claude/ 下。
    """
    fake_home = Path(os.environ.get("USERPROFILE") or os.environ.get("HOME") or "~")
    claude_dir = fake_home / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    cfg = {
        "schema_version": 1,
        "active_profile_id": "l4_smoke",
        "profiles": [
            {
                "id": "l4_smoke",
                "kind": "openai_compat",
                "api_base_url": os.environ["CAD_JURY_LLM_BASE_URL"],
                "api_key": os.environ["CAD_JURY_LLM_API_KEY"],
                "model": os.environ.get("CAD_JURY_LLM_MODEL", "gemini-2.5-flash"),
            }
        ],
    }
    path = claude_dir / "cad_jury_config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return path


def _run_one_view_loop(
    *,
    render_dir: Path,
    project_root: Path,
    view: str,
    baseline_png: Path,
    threshold: int | None = None,
):
    """跑一遍单视角闭环 → 返 (LoopResult, sidecar_dict)。threshold=None 用 DEFAULT(75)。"""
    cfg_path = _write_temp_jury_config()
    jury_profile, _caps = load_jury_config(cfg_path)
    loop_dict = dict(DEFAULT_JURY_LOOP_DICT)
    if threshold is not None:
        loop_dict = {**loop_dict, "advanced": {**loop_dict["advanced"], "threshold": threshold}}
    config = load_jury_loop_config(loop_dict)
    result = run_loop_if_eligible(
        view=view,
        backend_kind=config.backend.kind,  # "gemini_chat_image"
        rc={"prompt": _BASE_PROMPT},
        baseline_path=baseline_png,
        base_params={},
        budget=LoopBudget(n_views=1),  # cap_usd 默认 1.5
        project_root=project_root,
        config=config,
        jury_profile=jury_profile,
        jury_profile_path=cfg_path,
    )
    sidecar = json.loads((render_dir / f"{view}_enhance_meta.json").read_text(encoding="utf-8"))
    return result, sidecar


def test_l4_1_score_improves(tmp_path):
    """低分合成 baseline 跑 N 次闭环 → 平均 retry 提分 > 5。"""
    _require_jury_env()
    project_root = tmp_path
    render_dir = tmp_path / "render"
    render_dir.mkdir()
    deltas: list[int] = []
    for i in range(_SMOKE_RUNS):
        baseline = _make_rough_render_png(render_dir / "V1_enhanced_baseline.jpg")
        _result, sidecar = _run_one_view_loop(
            render_dir=render_dir,
            project_root=project_root,
            view="V1",
            baseline_png=baseline,
        )
        delta = sidecar.get("retry_score_delta")
        assert delta is not None, (
            f"第 {i+1} 次未触发 retry（合成图意外得高分？）："
            f"sidecar loop_status={sidecar.get('loop_status')}"
        )
        deltas.append(int(delta))
        for f in render_dir.glob("V1_*"):  # 清理供下一轮
            f.unlink()
    mean_delta = sum(deltas) / len(deltas)
    assert mean_delta > 5, f"平均 retry 提分 {mean_delta:.1f} 不 > 5（deltas={deltas}）"


def test_l4_2_no_trigger_when_score_above_threshold(tmp_path):
    """threshold 调到 1 → baseline 真实 jury score（≥1 几乎必然）≥ threshold → loop_status == 'above_threshold'（无 retry）。"""
    _require_jury_env()
    project_root = tmp_path
    render_dir = tmp_path / "render"
    render_dir.mkdir()
    baseline = _make_rough_render_png(render_dir / "V1_enhanced_baseline.jpg")
    result, sidecar = _run_one_view_loop(
        render_dir=render_dir,
        project_root=project_root,
        view="V1",
        baseline_png=baseline,
        threshold=1,
    )
    assert sidecar.get("loop_status") == "above_threshold", (
        f"期望 above_threshold，得 {sidecar.get('loop_status')}"
    )
    assert sidecar.get("retry_score_delta") is None, (
        f"above_threshold 不该有 retry，但 retry_score_delta={sidecar.get('retry_score_delta')}"
    )
    assert result.loop_status == "above_threshold"


def test_l4_3_v1_anchor_hook_returns_final_path(tmp_path):
    """v1_anchor 模式：run_loop_hook_for_view 跑完 V1 应返回 V1 的 final_path（== <render_dir>/V1_enhanced.jpg），
    供 cmd_enhance 拿去当 V2 的 anchor（BL-4 状态传递契约）。

    注：**不**走 prepare_jury_loop_state——它内部读 ~/.claude/cad_jury_config.json，会被 conftest
    的 autouse home-fake 干扰（虽然我们写了临时 config 到假 home，但 prepare 那条路径绕——直接给
    run_loop_hook_for_view 传 4 个参数最干净）。
    """
    _require_jury_env()
    project_root = tmp_path
    render_dir = tmp_path / "render"
    render_dir.mkdir()
    _make_rough_render_png(render_dir / "V1_enhanced_baseline.jpg")
    cfg_path = _write_temp_jury_config()
    jury_profile, _caps = load_jury_config(cfg_path)
    jury_loop_config = load_jury_loop_config(DEFAULT_JURY_LOOP_DICT)
    loop_budget = LoopBudget(n_views=2)
    final_path = cmd_enhance_hook.run_loop_hook_for_view(
        view_key="V1",
        new_path=str(render_dir / "V1_enhanced_baseline.jpg"),
        render_dir=render_dir,
        rc={"prompt": _BASE_PROMPT},
        rerun_loop=False,
        jury_loop_config=jury_loop_config,
        loop_budget=loop_budget,
        jury_profile=jury_profile,
        jury_profile_path=cfg_path,
        reference_mode="v1_anchor",
        project_root=project_root,
    )
    assert final_path == str(render_dir / "V1_enhanced.jpg"), (
        f"v1_anchor 模式 V1 hook 应返回 V1_enhanced.jpg 路径，得 {final_path!r}"
    )
