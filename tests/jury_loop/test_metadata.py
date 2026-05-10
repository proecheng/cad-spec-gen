"""metadata.py 单元测试 — Task 4.2。

按 spec §4.4（A-3 + BL-2 + BL-3 + M-9）：sidecar `<view>_enhance_meta.json` schema
+ 5 种状态形态 + SEC-MAJOR-2 路径净化 + SEC-MINOR-2 secrets 净化。

测试分组：
- Schema 字段顺序：与 spec §4.4 块定义保序
- 路径净化（SEC-MAJOR-2）：view 含 .. / 绝对路径 / 路径分隔符 → ValueError
- 5 状态形态：loop_disabled / above_threshold / delivered_retry × 2 / delivered_baseline
- write_degraded_sidecar：异常隔离回退 + traceback scrub_secrets
- secrets 净化（SEC-MINOR-2）：errors[].message_summary + backend_payload
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.jury_loop.metadata import (
    SidecarSchema,
    _validate_view_basename,
    write_degraded_sidecar,
    write_sidecar,
)


# ---------------------------------------------------------------------------
# Schema 字段顺序（spec §4.4 块定义保序）
# ---------------------------------------------------------------------------

_SPEC_FIELD_ORDER = [
    "$schema_version",
    "view",
    "backend",
    "loop_eligible",
    "loop_status",
    "loop_skipped_reason",
    "delivered_kind",
    "baseline",
    "retry",
    "tags_parsed",
    "rules_hit",
    "rules_missed_tags",
    "llm_fallback_used",
    "prompt_addons_applied",
    "param_overrides_applied",
    "user_friendly_summary",
    "loop_status_zh",
    "retry_score_delta",
    "delivered_score_delta",
    "extra_cost_usd",
    "warnings",
    "errors",
]


def test_schema_field_order_matches_spec_4_4(tmp_path: Path) -> None:
    """write_sidecar 写出的 JSON 字段顺序必须与 spec §4.4 块定义一致。"""
    write_sidecar(
        view="V1",
        render_dir=tmp_path,
        backend="fal_comfy",
        loop_status="loop_disabled",
    )
    sidecar = tmp_path / "V1_enhance_meta.json"
    raw = sidecar.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert list(parsed.keys()) == _SPEC_FIELD_ORDER


# ---------------------------------------------------------------------------
# 路径净化（SEC-MAJOR-2）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_view",
    [
        "../../etc/passwd",        # 父目录穿越
        "..",                      # 单纯父目录
        "/abs/path",               # POSIX 绝对路径
        "C:\\Windows\\bad",        # Windows 绝对路径
        "sub/V1",                  # 包含斜杠
        "sub\\V1",                 # 包含反斜杠
        "",                        # 空串
    ],
)
def test_validate_view_basename_rejects_bad_inputs(bad_view: str) -> None:
    """所有"非纯 basename"形式必须抛 ValueError。"""
    with pytest.raises(ValueError):
        _validate_view_basename(bad_view)


@pytest.mark.parametrize("good_view", ["V1", "view_123", "front-iso"])
def test_validate_view_basename_accepts_clean_names(good_view: str) -> None:
    """合法 basename 原样返回。"""
    assert _validate_view_basename(good_view) == good_view


def test_write_sidecar_rejects_path_traversal(tmp_path: Path) -> None:
    """write_sidecar 在 view 不洁时直接拒绝写入。"""
    with pytest.raises(ValueError):
        write_sidecar(
            view="../../etc/passwd",
            render_dir=tmp_path,
            backend="fal_comfy",
            loop_status="loop_disabled",
        )
    # 确认完全没写出 sidecar（根 conftest fake_home 不算）
    assert not (tmp_path / "V1_enhance_meta.json").exists()
    assert not any(p.name.endswith("_enhance_meta.json") for p in tmp_path.rglob("*"))


# ---------------------------------------------------------------------------
# 形态 1：loop_disabled
# ---------------------------------------------------------------------------


def test_loop_disabled_form(tmp_path: Path) -> None:
    """spec §4.4：loop_eligible=false / delivered_kind="baseline" / retry=null /
    extra_cost_usd=0 / delivered_score_delta=0 / 中文摘要锁文案。"""
    write_sidecar(
        view="V1",
        render_dir=tmp_path,
        backend="engineering",
        loop_status="loop_disabled",
    )
    parsed = json.loads((tmp_path / "V1_enhance_meta.json").read_text("utf-8"))
    assert parsed["loop_eligible"] is False
    assert parsed["delivered_kind"] == "baseline"
    assert parsed["retry"] is None
    assert parsed["tags_parsed"] == []
    assert parsed["prompt_addons_applied"] == []
    assert parsed["extra_cost_usd"] == 0
    assert parsed["retry_score_delta"] is None
    assert parsed["delivered_score_delta"] == 0
    assert parsed["user_friendly_summary"] == "该 backend 不支持闭环优化"
    assert parsed["loop_status_zh"] == "该 backend 不支持闭环优化"


# ---------------------------------------------------------------------------
# 形态 2：above_threshold
# ---------------------------------------------------------------------------


def test_above_threshold_form(tmp_path: Path) -> None:
    """baseline 完整 verdict / retry=null / delivered_score_delta=0 / 摘要含分数。"""
    write_sidecar(
        view="V1",
        render_dir=tmp_path,
        backend="fal_comfy",
        loop_status="above_threshold",
        baseline={
            "image_path": "V1_enhanced_baseline.jpg",
            "photoreal_score": 78,
            "semantic_checks": {
                "geometry_preserved": True,
                "material_consistent": True,
                "photorealistic": True,
                "no_extra_parts": True,
                "no_missing_parts": True,
            },
            "reason": "已达标",
        },
        tags_parsed=[],
    )
    parsed = json.loads((tmp_path / "V1_enhance_meta.json").read_text("utf-8"))
    assert parsed["delivered_kind"] == "baseline"
    assert parsed["baseline"]["photoreal_score"] == 78
    assert parsed["retry"] is None
    assert parsed["retry_score_delta"] is None
    assert parsed["delivered_score_delta"] == 0
    assert "78" in parsed["user_friendly_summary"]


# ---------------------------------------------------------------------------
# 形态 3：delivered_retry (pick_max_jury)
# ---------------------------------------------------------------------------


def test_delivered_retry_pick_max_jury_form(tmp_path: Path) -> None:
    """baseline+retry 完整 verdict / retry_score_delta = retry.score - baseline.score。"""
    write_sidecar(
        view="V1",
        render_dir=tmp_path,
        backend="fal_comfy",
        loop_status="delivered_retry",
        delivered_kind="retry",
        baseline={
            "image_path": "V1_enhanced_baseline.jpg",
            "photoreal_score": 58,
            "semantic_checks": {"geometry_preserved": True, "material_consistent": True,
                                "photorealistic": False, "no_extra_parts": True, "no_missing_parts": True},
            "reason": "plastic look, flat lighting",
        },
        retry={
            "image_path": "V1_enhanced_retry.jpg",
            "photoreal_score": 78,
            "semantic_checks": {"geometry_preserved": True, "material_consistent": True,
                                "photorealistic": True, "no_extra_parts": True, "no_missing_parts": True},
            "reason": "improved metallic finish",
            "final_prompt": "matte metallic finish, studio softbox",
            "backend_payload": {"cfg_scale": 7.5, "steps": 30},
        },
        retry_score_delta=20,
        delivered_score_delta=20,
        extra_cost_usd=0.18,
    )
    parsed = json.loads((tmp_path / "V1_enhance_meta.json").read_text("utf-8"))
    assert parsed["delivered_kind"] == "retry"
    assert parsed["retry"]["photoreal_score"] == 78
    assert parsed["retry_score_delta"] == 20
    assert parsed["delivered_score_delta"] == 20
    assert parsed["extra_cost_usd"] == 0.18


# ---------------------------------------------------------------------------
# 形态 4：delivered_retry (force_retry)
# ---------------------------------------------------------------------------


def test_delivered_retry_force_retry_form(tmp_path: Path) -> None:
    """force_retry：retry.photoreal_score=null / semantic_checks=null / reason=null
    但 final_prompt + backend_payload 仍写；retry_score_delta=null / delivered_score_delta=null。"""
    write_sidecar(
        view="V1",
        render_dir=tmp_path,
        backend="fal_comfy",
        loop_status="delivered_retry",
        delivered_kind="retry",
        baseline={
            "image_path": "V1_enhanced_baseline.jpg",
            "photoreal_score": 58,
            "semantic_checks": {"geometry_preserved": True, "material_consistent": True,
                                "photorealistic": False, "no_extra_parts": True, "no_missing_parts": True},
            "reason": "plastic look",
        },
        retry={
            "image_path": "V1_enhanced_retry.jpg",
            "photoreal_score": None,
            "semantic_checks": None,
            "reason": None,
            "final_prompt": "<完整 prompt>",
            "backend_payload": {"cfg_scale": 7.5},
        },
        retry_score_delta=None,
        delivered_score_delta=None,
    )
    parsed = json.loads((tmp_path / "V1_enhance_meta.json").read_text("utf-8"))
    assert parsed["delivered_kind"] == "retry"
    assert parsed["retry"]["photoreal_score"] is None
    assert parsed["retry"]["semantic_checks"] is None
    assert parsed["retry"]["reason"] is None
    assert parsed["retry"]["final_prompt"] == "<完整 prompt>"
    assert parsed["retry"]["backend_payload"]["cfg_scale"] == 7.5
    assert parsed["retry_score_delta"] is None
    assert parsed["delivered_score_delta"] is None


# ---------------------------------------------------------------------------
# 形态 5：delivered_baseline (jury_unavailable / no_tags_parsed / cost_capped / retry_failed)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "loop_status",
    ["jury_unavailable", "no_tags_parsed", "cost_capped", "retry_failed",
     "no_rules_hit_no_llm", "empty_reason", "llm_fallback_failed"],
)
def test_delivered_baseline_subforms(tmp_path: Path, loop_status: str) -> None:
    """spec §4.4 第六条：delivered_baseline 系列 / retry=null /
    retry_score_delta=null / delivered_score_delta=0。"""
    write_sidecar(
        view="V1",
        render_dir=tmp_path,
        backend="fal_comfy",
        loop_status=loop_status,
        baseline={
            "image_path": "V1_enhanced_baseline.jpg",
            "photoreal_score": 50,
            "semantic_checks": {"geometry_preserved": True, "material_consistent": True,
                                "photorealistic": False, "no_extra_parts": True, "no_missing_parts": True},
            "reason": "low light",
        },
    )
    parsed = json.loads((tmp_path / "V1_enhance_meta.json").read_text("utf-8"))
    assert parsed["loop_status"] == loop_status
    assert parsed["delivered_kind"] == "baseline"
    assert parsed["retry"] is None
    assert parsed["retry_score_delta"] is None
    assert parsed["delivered_score_delta"] == 0


# ---------------------------------------------------------------------------
# write_degraded_sidecar — cmd_enhance 异常隔离
# ---------------------------------------------------------------------------


def test_write_degraded_sidecar_writes_retry_failed_status(tmp_path: Path) -> None:
    """spec line 261-265：cmd_enhance 视角级异常时写降级 sidecar；loop_status=retry_failed。"""
    err = RuntimeError("某 vendor 调用炸了")
    write_degraded_sidecar(view="V1", render_dir=tmp_path, error=err)
    parsed = json.loads((tmp_path / "V1_enhance_meta.json").read_text("utf-8"))
    assert parsed["loop_status"] == "retry_failed"
    assert parsed["delivered_kind"] == "baseline"
    assert len(parsed["errors"]) == 1
    assert "某 vendor 调用炸了" in parsed["errors"][0]["message_summary"]


def test_write_degraded_sidecar_scrubs_secrets_from_traceback(tmp_path: Path) -> None:
    """traceback 含 FAL_KEY=sk-real 时必须 scrub 后才写盘（SEC-MINOR-2）。"""
    err = RuntimeError("auth fail FAL_KEY=sk-real-leaked-12345")
    write_degraded_sidecar(view="V1", render_dir=tmp_path, error=err)
    raw = (tmp_path / "V1_enhance_meta.json").read_text("utf-8")
    assert "sk-real-leaked-12345" not in raw
    assert "[REDACTED]" in raw


def test_write_degraded_sidecar_rejects_bad_view(tmp_path: Path) -> None:
    """降级路径同样过路径净化（SEC-MAJOR-2）。"""
    with pytest.raises(ValueError):
        write_degraded_sidecar(
            view="../../etc/passwd",
            render_dir=tmp_path,
            error=RuntimeError("x"),
        )


# ---------------------------------------------------------------------------
# secrets 净化（SEC-MINOR-2）— write_sidecar errors[].message_summary + backend_payload
# ---------------------------------------------------------------------------


def test_write_sidecar_scrubs_secrets_in_errors(tmp_path: Path) -> None:
    """errors[].message_summary 含 FAL_KEY=sk-real → [REDACTED]。"""
    write_sidecar(
        view="V1",
        render_dir=tmp_path,
        backend="fal_comfy",
        loop_status="retry_failed",
        baseline={
            "image_path": "V1_enhanced_baseline.jpg",
            "photoreal_score": 50,
            "semantic_checks": {"geometry_preserved": True, "material_consistent": True,
                                "photorealistic": False, "no_extra_parts": True, "no_missing_parts": True},
            "reason": "x",
        },
        errors=[{
            "code": "retry_http_401",
            "message_summary": "auth fail FAL_KEY=sk-real-leaked",
            "user_action_hint": "检查 API key",
        }],
    )
    raw = (tmp_path / "V1_enhance_meta.json").read_text("utf-8")
    assert "sk-real-leaked" not in raw
    assert "[REDACTED]" in raw


def test_write_sidecar_scrubs_secrets_in_backend_payload(tmp_path: Path) -> None:
    """retry.backend_payload 含 Authorization header → [REDACTED]。"""
    write_sidecar(
        view="V1",
        render_dir=tmp_path,
        backend="fal_comfy",
        loop_status="delivered_retry",
        delivered_kind="retry",
        baseline={
            "image_path": "V1_enhanced_baseline.jpg",
            "photoreal_score": 58,
            "semantic_checks": {"geometry_preserved": True, "material_consistent": True,
                                "photorealistic": False, "no_extra_parts": True, "no_missing_parts": True},
            "reason": "x",
        },
        retry={
            "image_path": "V1_enhanced_retry.jpg",
            "photoreal_score": 78,
            "semantic_checks": {"geometry_preserved": True, "material_consistent": True,
                                "photorealistic": True, "no_extra_parts": True, "no_missing_parts": True},
            "reason": "ok",
            "final_prompt": "matte",
            "backend_payload": {
                "cfg_scale": 7.5,
                "Authorization": "Bearer sk-leaked-token-xxx",
            },
        },
        retry_score_delta=20,
        delivered_score_delta=20,
    )
    raw = (tmp_path / "V1_enhance_meta.json").read_text("utf-8")
    assert "sk-leaked-token-xxx" not in raw
    assert "[REDACTED]" in raw


# ---------------------------------------------------------------------------
# Schema sanity
# ---------------------------------------------------------------------------


def test_schema_version_is_locked_to_1() -> None:
    """spec §4.4 BL-2：SP1 锁 $schema_version=1。"""
    assert SidecarSchema.SCHEMA_VERSION == 1
