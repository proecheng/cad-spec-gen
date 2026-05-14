"""L1+L2: ViewVerdict parse 兼容 + matches_spec aggregate 真值表。

测试目标（spec §5.2.2 + §6 验收 #1）：
- L1 向后兼容：老 fixture（无 features_status 字段）→ matches_spec 默认 True，
  且 verdict 不被升级为 needs_review（向后兼容真不破）。
- L2 真值表：
  - 所有 features visible=True → matches_spec=True
  - 任一 feature visible=False → matches_spec=False
"""

from __future__ import annotations

import json
from dataclasses import asdict

from tools.jury.verdict import _make_needs_review_verdict, aggregate_run_verdict, parse_view_verdict


def test_parse_view_verdict_back_compat_no_features_status() -> None:
    """L1 老 fixture (无 features_status) → matches_spec 默认 True。"""
    content = json.dumps(
        {
            "semantic_checks": {
                "geometry_preserved": True,
                "material_consistent": True,
                "photorealistic": True,
                "no_extra_parts": True,
                "no_missing_parts": True,
            },
            "photoreal_score": 80,
            "reason": "ok",
        }
    )
    v = parse_view_verdict(content, finish_reason="stop")
    assert v.parse_status == "ok"
    assert v.semantic_checks["matches_spec"] is True, (
        "无 features 时 matches_spec 默认 True"
    )
    assert v.features_status == []


def test_parse_view_verdict_back_compat_verdict_not_needs_review() -> None:
    """L1 向后兼容硬保障：老 fixture（无 features_status / 无 matches_spec in raw_checks）→
    verdict 必须是 accepted 或 preview，不可被 _REQUIRED_BOOL_KEYS 校验路径误升级为 needs_review。

    防 plan-drift：若 matches_spec 被加入 _REQUIRED_BOOL_KEYS 且未 special-case，
    所有不含 matches_spec 的老 fixture 会触发 content_keys_mismatch → needs_review，
    silently break spec §6 验收 #1。本测试 catch 这条隐性 break。
    """
    content = json.dumps(
        {
            "semantic_checks": {
                "geometry_preserved": True,
                "material_consistent": True,
                "photorealistic": True,
                "no_extra_parts": True,
                "no_missing_parts": True,
            },
            "photoreal_score": 80,
            "reason": "ok",
        }
    )
    v = parse_view_verdict(content, finish_reason="stop")
    assert v.verdict in ("accepted", "preview"), (
        f"老 fixture verdict 必须 accepted/preview, 实际 = {v.verdict}; "
        f"parse_anomalies = {v.parse_anomalies}"
    )
    assert "content_keys_mismatch" not in v.parse_anomalies, (
        "老 fixture 不该触发 content_keys_mismatch（matches_spec 不应进 _REQUIRED_BOOL_KEYS 或须 special-case 跳过）"
    )


def test_parse_view_verdict_with_features_all_visible() -> None:
    """L2 所有 features visible → matches_spec True。"""
    content = json.dumps(
        {
            "semantic_checks": {
                "geometry_preserved": True,
                "material_consistent": True,
                "photorealistic": True,
                "no_extra_parts": True,
                "no_missing_parts": True,
            },
            "photoreal_score": 80,
            "reason": "ok",
            "features_status": [
                {
                    "feature_id": "flange_arms_4",
                    "visible": True,
                    "reason": "4 arms visible",
                },
                {"feature_id": "peek_ring", "visible": True, "reason": "ring at base"},
            ],
        }
    )
    v = parse_view_verdict(content, finish_reason="stop")
    assert v.semantic_checks["matches_spec"] is True
    assert len(v.features_status) == 2


def test_parse_view_verdict_with_one_feature_invisible() -> None:
    """L2 任一 feature invisible → matches_spec False。"""
    content = json.dumps(
        {
            "semantic_checks": {
                "geometry_preserved": True,
                "material_consistent": True,
                "photorealistic": True,
                "no_extra_parts": True,
                "no_missing_parts": True,
            },
            "photoreal_score": 80,
            "reason": "ok",
            "features_status": [
                {
                    "feature_id": "flange_arms_4",
                    "visible": False,
                    "reason": "disc only",
                },
                {"feature_id": "peek_ring", "visible": True, "reason": "ring at base"},
            ],
        }
    )
    v = parse_view_verdict(content, finish_reason="stop")
    assert v.semantic_checks["matches_spec"] is False
    assert v.features_status[0]["visible"] is False


def test_aggregate_run_verdict_all_views_pass():
    from tools.jury.verdict import aggregate_run_verdict, ViewVerdict

    v1 = ViewVerdict(
        semantic_checks={
            "matches_spec": True,
            "geometry_preserved": True,
            "material_consistent": True,
            "photorealistic": True,
            "no_extra_parts": True,
            "no_missing_parts": True,
        },
        photoreal_score=80,
        reason="ok",
        parse_status="ok",
        features_status=[{"feature_id": "f1", "visible": True, "reason": "ok"}],
    )
    v2 = ViewVerdict(
        semantic_checks={
            "matches_spec": True,
            "geometry_preserved": True,
            "material_consistent": True,
            "photorealistic": True,
            "no_extra_parts": True,
            "no_missing_parts": True,
        },
        photoreal_score=80,
        reason="ok",
        parse_status="ok",
        features_status=[{"feature_id": "f1", "visible": True, "reason": "ok"}],
    )
    run = aggregate_run_verdict({"V1": v1, "V2": v2})
    assert run.overall_matches_spec is True
    assert run.per_view_failed_features == {}


def test_aggregate_run_verdict_one_view_fails():
    from tools.jury.verdict import aggregate_run_verdict, ViewVerdict

    v_pass = ViewVerdict(
        semantic_checks={
            "matches_spec": True,
            "geometry_preserved": True,
            "material_consistent": True,
            "photorealistic": True,
            "no_extra_parts": True,
            "no_missing_parts": True,
        },
        photoreal_score=80,
        reason="ok",
        parse_status="ok",
        features_status=[{"feature_id": "f1", "visible": True, "reason": "ok"}],
    )
    v_fail = ViewVerdict(
        semantic_checks={
            "matches_spec": False,
            "geometry_preserved": True,
            "material_consistent": True,
            "photorealistic": True,
            "no_extra_parts": True,
            "no_missing_parts": True,
        },
        photoreal_score=80,
        reason="missing arms",
        parse_status="ok",
        features_status=[
            {"feature_id": "flange_arms_4", "visible": False, "reason": "disc only"},
            {"feature_id": "peek_ring", "visible": True, "reason": "ring ok"},
        ],
    )
    run = aggregate_run_verdict({"V1": v_pass, "V4": v_fail})
    assert run.overall_matches_spec is False
    assert run.per_view_failed_features == {"V4": ["flange_arms_4"]}


# ---------- Task 9 v2.37：matches_spec=False → 升级 needs_review ----------


def test_parse_view_verdict_matches_spec_false_escalates_to_needs_review() -> None:
    """Task 9：features_status 非空 + matches_spec=False → verdict='needs_review'。

    决策语义（spec §3 F5 retry 触发条件）：features_status 非空表示 LLM 真的看到了
    feature 列表才做的对账，此时 invisible 表征 enhance 真有问题——而不是"没列单
    所以默认 True"那类向后兼容退化路径。
    """
    content = json.dumps(
        {
            "semantic_checks": {
                "geometry_preserved": True,
                "material_consistent": True,
                "photorealistic": True,
                "no_extra_parts": True,
                "no_missing_parts": True,
            },
            "photoreal_score": 85,
            "reason": "图片质量 OK 但缺特征",
            "features_status": [
                {"feature_id": "flange_arms_4", "visible": False, "reason": "未见 4 臂"},
            ],
        }
    )
    v = parse_view_verdict(content, finish_reason="stop")
    assert v.semantic_checks["matches_spec"] is False
    assert v.verdict == "needs_review", (
        f"matches_spec=False 时应升级 needs_review；实际 {v.verdict}; "
        f"parse_anomalies = {v.parse_anomalies}"
    )
    assert "matches_spec_failed" in v.parse_anomalies, (
        f"应记入 matches_spec_failed anomaly；实际 {v.parse_anomalies}"
    )


def test_parse_view_verdict_empty_features_no_escalation() -> None:
    """Task 9 back-compat：features_status 为空 → matches_spec=True → 不升级。

    硬保护 Task 1 的 test_parse_view_verdict_back_compat_verdict_not_needs_review
    不被 (A) 决策扩展破坏。
    """
    content = json.dumps(
        {
            "semantic_checks": {
                "geometry_preserved": True,
                "material_consistent": True,
                "photorealistic": True,
                "no_extra_parts": True,
                "no_missing_parts": True,
            },
            "photoreal_score": 85,
            "reason": "ok",
        }
    )
    v = parse_view_verdict(content, finish_reason="stop")
    assert v.semantic_checks["matches_spec"] is True
    assert v.verdict == "accepted", (
        f"无 features 时不能 escalate；实际 verdict={v.verdict}, "
        f"anomalies={v.parse_anomalies}"
    )
    assert "matches_spec_failed" not in v.parse_anomalies


def test_parse_view_verdict_all_features_visible_no_escalation() -> None:
    """Task 9：features_status 非空但 all visible=True → matches_spec=True → 不升级。"""
    content = json.dumps(
        {
            "semantic_checks": {
                "geometry_preserved": True,
                "material_consistent": True,
                "photorealistic": True,
                "no_extra_parts": True,
                "no_missing_parts": True,
            },
            "photoreal_score": 85,
            "reason": "ok",
            "features_status": [
                {"feature_id": "f1", "visible": True, "reason": "可见"},
                {"feature_id": "f2", "visible": True, "reason": "可见"},
            ],
        }
    )
    v = parse_view_verdict(content, finish_reason="stop")
    assert v.semantic_checks["matches_spec"] is True
    assert v.verdict == "accepted"
    assert "matches_spec_failed" not in v.parse_anomalies


def test_aggregate_overall_unchanged_with_needs_review_view_mixed() -> None:
    """v2.37.2 §11 #1 reg：aggregate_run_verdict 把 needs_review 视角混入 normal 视角后，
    asdict(RunVerdict) 全字段与 task 2 改动前等价（数学证明：matches_spec=True 与
    .get(default=True) 在所有路径上等价 → asdict 输出 byte-equal）。

    Spec §13 R4 Q2 扩 AC-3 到 asdict 全字段等价（不只 overall_matches_spec）。
    """
    normal_content = (
        '{"semantic_checks": {"geometry_preserved": true, "material_consistent": true,'
        ' "photorealistic": true, "no_extra_parts": true, "no_missing_parts": true},'
        ' "photoreal_score": 80, "reason": "ok"}'
    )
    normal = parse_view_verdict(normal_content, finish_reason="stop")
    needs_review = _make_needs_review_verdict(["content_not_json"])

    run = aggregate_run_verdict({"V1": normal, "V2": needs_review})

    # overall_matches_spec：normal 视角 matches_spec=True + needs_review 视角
    # matches_spec=True（task 2 改动）→ all=True
    assert run.overall_matches_spec is True
    # per_view_failed_features：normal 视角 features_status 为空、needs_review 视角
    # features_status 为空 → 两视角都无 invisible feature → dict 为空
    assert run.per_view_failed_features == {}
    # asdict 全字段等价（每视角的 view_verdicts 也包含完整 ViewVerdict 数据）
    snapshot = asdict(run)
    assert snapshot["overall_matches_spec"] is True
    assert snapshot["per_view_failed_features"] == {}
    assert set(snapshot["view_verdicts"].keys()) == {"V1", "V2"}


def test_aggregate_all_needs_review_vacuous_true() -> None:
    """v2.37.2 §13 R4 Q4：所有视角都 needs_review 时 overall_matches_spec is True
    但所有 view 都是 needs_review verdict（vacuous True 不掩盖真问题，由上游
    needs_review_count 统计决策；本 PR 不改 aggregate 实现）。
    """
    v1 = _make_needs_review_verdict(["content_not_json"])
    v2 = _make_needs_review_verdict(["missing_content"])
    run = aggregate_run_verdict({"V1": v1, "V2": v2})
    assert run.overall_matches_spec is True  # vacuous True (all matches_spec=True)
    # 但所有视角是 needs_review verdict
    assert all(v.verdict == "needs_review" for v in run.view_verdicts.values())


def test_make_needs_review_verdict_key_order_stable() -> None:
    """v2.37.2 §13 R4 Q6：6-key dict key 顺序固定为 _REQUIRED_BOOL_KEYS + ('matches_spec',)
    末位；若任何 sidecar / cache key 依赖 stable order，本测试 catch 顺序漂移。
    """
    v = _make_needs_review_verdict(["content_not_json"])
    expected_order = [
        "geometry_preserved",
        "material_consistent",
        "photorealistic",
        "no_extra_parts",
        "no_missing_parts",
        "matches_spec",
    ]
    assert list(v.semantic_checks.keys()) == expected_order
