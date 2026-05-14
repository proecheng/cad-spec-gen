"""L4 photo3d_jury matches_spec 集成 — feature_extractor 仅 per-process 调 1 次。

测试 Task 6 集成层（spec v2.37 §5.3 F1 后段）：
- D1: feature_extractor.extract 每进程 ≤1 次（不是 per-view）
- prompt 末尾按 expected_in_views 过滤后挂相关 features + 输出 schema 含 features_status
- view_verdict dict 透传 features_status 字段（来自 Task 1 ViewVerdict.features_status）
- 向后兼容：无 --spec-md / --design-doc 时 extract 不调 + prompt 等同老 _JURY_PROMPT

实施策略（per Task 6 head-up #1）：
单元测 `_extract_features_for_run` / `_build_view_prompt` 两个 helper + 1 个集成测断
extract 调用次数。完整 mock main() 流程过 fragile 不采用。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tools.photo3d_jury import (
    _JURY_PROMPT,
    _build_view_prompt,
    _extract_features_for_run,
    main,
)


def _make_args(
    *,
    spec_md: Any = None,
    design_doc: Any = None,
    subsystem: str = "end_effector",
) -> argparse.Namespace:
    """构造仿 argparse.Namespace 的轻量对象（避开 class-scope 同名变量陷阱）。"""
    ns = argparse.Namespace()
    ns.spec_md = spec_md
    ns.design_doc = design_doc
    ns.subsystem = subsystem
    return ns


# ---------- _build_view_prompt 单测（不依赖 main() 状态） ----------


def test_build_view_prompt_no_features_returns_original() -> None:
    """无 features → 返回原 _JURY_PROMPT 完整字符串（向后兼容 v2.36 fixture）。"""
    result = _build_view_prompt("V4", [])
    assert result == _JURY_PROMPT


def test_build_view_prompt_filters_by_expected_in_views() -> None:
    """expected_in_views=["V4"] 在 V4 视角应可见；V5 视角应过滤掉。"""
    features = [
        {
            "feature_id": "v4_only",
            "description_cn": "仅 V4 可见",
            "expected_in_views": ["V4"],
        },
        {
            "feature_id": "v5_only",
            "description_cn": "仅 V5 可见",
            "expected_in_views": ["V5"],
        },
    ]
    p_v4 = _build_view_prompt("V4", features)
    p_v5 = _build_view_prompt("V5", features)
    assert "v4_only" in p_v4 and "v5_only" not in p_v4
    assert "v5_only" in p_v5 and "v4_only" not in p_v5


def test_build_view_prompt_no_filter_when_expected_views_missing() -> None:
    """expected_in_views=None 或 missing → 所有视角都见。"""
    features: list[dict[str, Any]] = [
        {"feature_id": "all_views", "description_cn": "处处可见"},
        {"feature_id": "all_views2", "description_cn": "处处2", "expected_in_views": None},
    ]
    p_v4 = _build_view_prompt("V4", features)
    p_v9 = _build_view_prompt("V9", features)
    assert "all_views" in p_v4 and "all_views2" in p_v4
    assert "all_views" in p_v9 and "all_views2" in p_v9


def test_build_view_prompt_requires_features_status_in_schema() -> None:
    """prompt 末尾应要求 LLM 返回 features_status 字段。"""
    features = [{"feature_id": "fx", "description_cn": "测试"}]
    result = _build_view_prompt("V4", features)
    assert "features_status" in result
    # 仍含原 _JURY_PROMPT 主体（不破坏 5 bool key 评审）
    assert "geometry_preserved" in result
    assert "photoreal_score" in result


# ---------- _extract_features_for_run 单测（不依赖 LLM 真调） ----------


def test_extract_features_for_run_no_spec_md_returns_empty(tmp_path: Path) -> None:
    """spec_md 与 design_doc 都未提供 → 跳过抽取，返空 list（spec D5 fail-safe）。"""
    features = _extract_features_for_run(
        args=_make_args(spec_md=None, design_doc=None),
        profile=MagicMock(),
        project_root=tmp_path,
        frozen_run_id="rid-1",
    )
    assert features == []


def test_extract_features_for_run_design_doc_missing_returns_empty(
    tmp_path: Path,
) -> None:
    """有 spec_md 但缺 design_doc → 跳过抽取（fail-safe 不阻断）。"""
    spec_md = tmp_path / "CAD_SPEC.md"
    spec_md.write_text("# Spec\n", encoding="utf-8")

    features = _extract_features_for_run(
        args=_make_args(spec_md=str(spec_md), design_doc=None),
        profile=MagicMock(),
        project_root=tmp_path,
        frozen_run_id="rid-1",
    )
    assert features == []


def test_extract_features_for_run_calls_extractor_once(tmp_path: Path) -> None:
    """spec_md + design_doc 均存在 → 调 feature_extractor.extract 恰 1 次。"""
    spec_md = tmp_path / "CAD_SPEC.md"
    spec_md.write_text("# Spec\n", encoding="utf-8")
    design = tmp_path / "design.md"
    design.write_text("design content\n", encoding="utf-8")

    expected: list[dict[str, Any]] = [
        {"feature_id": "fx1", "description_cn": "x", "expected_in_views": None},
    ]
    extract_mock = MagicMock(
        return_value={"features": expected, "parse_anomalies": []}
    )
    with patch("tools.jury.feature_extractor.extract", extract_mock):
        features = _extract_features_for_run(
            args=_make_args(spec_md=str(spec_md), design_doc=str(design)),
            profile=MagicMock(),
            project_root=tmp_path,
            frozen_run_id="rid-1",
        )
    assert extract_mock.call_count == 1
    assert features == expected


def test_extract_features_for_run_extractor_raises_returns_empty(
    tmp_path: Path,
) -> None:
    """extractor 抛异常 → fail-safe 返 [] 不阻断（spec D5）。

    feature_extractor.extract 已有自己的 fail-safe，但本层 helper 也兜底
    防御 extract import 失败 / 调用前异常等。
    """
    spec_md = tmp_path / "CAD_SPEC.md"
    spec_md.write_text("# Spec\n", encoding="utf-8")
    design = tmp_path / "design.md"
    design.write_text("design content\n", encoding="utf-8")

    with patch(
        "tools.jury.feature_extractor.extract",
        side_effect=RuntimeError("unreachable upstream"),
    ):
        features = _extract_features_for_run(
            args=_make_args(spec_md=str(spec_md), design_doc=str(design)),
            profile=MagicMock(),
            project_root=tmp_path,
            frozen_run_id="rid-1",
        )
    assert features == []


# ---------- main() 集成断言：extract 仅调 1 次 ----------


def _write_jury_config(home: Path) -> None:
    cfg = home / ".claude" / "cad_jury_config.json"
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


def _make_response(body: dict[str, Any]) -> MagicMock:
    cm = MagicMock()
    resp = MagicMock()
    resp.status = 200
    resp.read.return_value = json.dumps(body).encode("utf-8")
    resp.headers = {"Content-Type": "application/json"}
    cm.__enter__.return_value = resp
    cm.__exit__.return_value = None
    return cm


def _ok_payload_with_features_status(view: str) -> dict[str, Any]:
    """OK chat-completions payload + matches_spec features_status 全 visible。"""
    return {
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
                            "photoreal_score": 85,
                            "reason": f"view {view} OK",
                            "features_status": [
                                {
                                    "feature_id": "fx1",
                                    "visible": True,
                                    "reason": "可见",
                                }
                            ],
                        }
                    )
                },
                "finish_reason": "stop",
            }
        ],
    }


@pytest.fixture
def jury_env_with_specs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """完整 jury 环境 + CAD_SPEC.md + design_doc 真文件，让 main() 触发 extract。"""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("CAD_JURY_DISABLE_LLM", raising=False)

    _write_jury_config(tmp_path)

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

    # 加 CAD_SPEC.md + design doc（main 内 args.spec_md / args.design_doc 触发抽取）
    spec_md = tmp_path / "cad" / sub / "CAD_SPEC.md"
    spec_md.write_text("# Spec stub\nflange OD=90 mm\n", encoding="utf-8")
    design = tmp_path / "design.md"
    design.write_text("法兰 4 条径向悬臂\n", encoding="utf-8")
    return tmp_path


def test_main_calls_feature_extractor_at_most_once_per_process(
    jury_env_with_specs: Path,
) -> None:
    """spec D1：跑完 2 视角后，extract 仅被调 1 次（不是 2 次 = per-view）。

    集成测主流程 path：argparse → load_jury_config → Layer0 → extract → Layer2 LLM 循环。
    用 _ok_payload_with_features_status 让所有视角 LLM 返 OK + features_status，避免 mock layer1。
    """
    iter_responses = iter(
        [
            _make_response(_ok_payload_with_features_status("iso")),
            _make_response(_ok_payload_with_features_status("front")),
        ]
    )
    extract_mock = MagicMock(
        return_value={
            "features": [
                {"feature_id": "fx1", "description_cn": "x", "expected_in_views": None}
            ],
            "parse_anomalies": [],
        }
    )

    sub = "lifting_platform"
    spec_md = jury_env_with_specs / "cad" / sub / "CAD_SPEC.md"
    design = jury_env_with_specs / "design.md"

    with patch(
        "tools.jury.feature_extractor.extract", extract_mock
    ), patch(
        "tools.jury.llm_client.urlopen",
        side_effect=lambda *a, **kw: next(iter_responses),
    ):
        code = main(
            [
                "--subsystem",
                sub,
                "--project-root",
                str(jury_env_with_specs),
                "--spec-md",
                str(spec_md),
                "--design-doc",
                str(design),
            ]
        )
    assert code == 0, f"main 应 exit 0；实际 {code}"
    assert extract_mock.call_count == 1, (
        f"feature_extractor.extract 应每进程仅调 1 次；实际 {extract_mock.call_count}"
    )


def test_main_view_verdict_carries_features_status(
    jury_env_with_specs: Path,
) -> None:
    """spec §5.3 F1：view_verdict 应透传 features_status 字段（来自 ViewVerdict）。"""
    iter_responses = iter(
        [
            _make_response(_ok_payload_with_features_status("iso")),
            _make_response(_ok_payload_with_features_status("front")),
        ]
    )
    extract_mock = MagicMock(
        return_value={
            "features": [
                {"feature_id": "fx1", "description_cn": "x", "expected_in_views": None}
            ],
            "parse_anomalies": [],
        }
    )
    sub = "lifting_platform"
    spec_md = jury_env_with_specs / "cad" / sub / "CAD_SPEC.md"
    design = jury_env_with_specs / "design.md"

    with patch(
        "tools.jury.feature_extractor.extract", extract_mock
    ), patch(
        "tools.jury.llm_client.urlopen",
        side_effect=lambda *a, **kw: next(iter_responses),
    ):
        code = main(
            [
                "--subsystem",
                sub,
                "--project-root",
                str(jury_env_with_specs),
                "--spec-md",
                str(spec_md),
                "--design-doc",
                str(design),
            ]
        )
    assert code == 0
    rep_path = (
        jury_env_with_specs
        / "cad"
        / sub
        / ".cad-spec-gen"
        / "runs"
        / "20260508-123456"
        / "PHOTO3D_JURY_REPORT.json"
    )
    rep = json.loads(rep_path.read_text(encoding="utf-8"))
    for v in rep["views"]:
        assert "features_status" in v, (
            f"view {v['view']} 缺 features_status 字段：{v.keys()}"
        )
        assert v["features_status"] == [
            {"feature_id": "fx1", "visible": True, "reason": "可见"}
        ]


def test_main_no_spec_md_skips_extract_backward_compat(
    jury_env_with_specs: Path,
) -> None:
    """向后兼容：不传 --spec-md/--design-doc + CAD_SPEC.md 也别让 extract 被调。

    *注*：jury_env_with_specs fixture 已写 cad/<sub>/CAD_SPEC.md（用于其他测试）；
    本用例传 --spec-md=不存在路径 来确认 derive 也走 .exists() 校验，缺一项即跳。
    """
    iter_responses = iter(
        [
            _make_response(_ok_payload_with_features_status("iso")),
            _make_response(_ok_payload_with_features_status("front")),
        ]
    )
    extract_mock = MagicMock(
        return_value={"features": [], "parse_anomalies": []}
    )

    sub = "lifting_platform"
    with patch(
        "tools.jury.feature_extractor.extract", extract_mock
    ), patch(
        "tools.jury.llm_client.urlopen",
        side_effect=lambda *a, **kw: next(iter_responses),
    ):
        # 不传 --spec-md / --design-doc：默认 derive cad/<sub>/CAD_SPEC.md 存在
        # 但 design_doc 未提供 → 不触发 extract（fail-safe）
        code = main(
            [
                "--subsystem",
                sub,
                "--project-root",
                str(jury_env_with_specs),
            ]
        )
    assert code == 0
    assert extract_mock.call_count == 0, (
        "design_doc 未提供时不应触发 extract（向后兼容 v2.36）"
    )


# ---------- Task 7：RunVerdict 聚合写报告（F2 wire） ----------


def _payload_features_visible(view: str, *, visible: bool) -> dict[str, Any]:
    """构造 OK + features_status[{fx1, visible=visible}] 的 chat-completions payload。"""
    return {
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
                            "photoreal_score": 85,
                            "reason": f"view {view}",
                            "features_status": [
                                {
                                    "feature_id": "fx1",
                                    "visible": visible,
                                    "reason": "可见" if visible else "缺失",
                                }
                            ],
                        }
                    )
                },
                "finish_reason": "stop",
            }
        ],
    }


def test_photo3d_jury_report_includes_run_verdict_aggregate(
    jury_env_with_specs: Path,
) -> None:
    """跑完所有视角后 PHOTO3D_JURY_REPORT.json 顶层应含 overall_matches_spec
    + per_view_failed_features + matches_spec_status。

    场景：iso visible=True，front visible=False（fx1 missing）→
    overall_matches_spec=False / per_view_failed_features={"front": ["fx1"]}
    / matches_spec_status="fail"。
    """
    iter_responses = iter(
        [
            _make_response(_payload_features_visible("iso", visible=True)),
            _make_response(_payload_features_visible("front", visible=False)),
        ]
    )
    extract_mock = MagicMock(
        return_value={
            "features": [
                {"feature_id": "fx1", "description_cn": "x", "expected_in_views": None}
            ],
            "parse_anomalies": [],
        }
    )

    sub = "lifting_platform"
    spec_md = jury_env_with_specs / "cad" / sub / "CAD_SPEC.md"
    design = jury_env_with_specs / "design.md"

    with patch(
        "tools.jury.feature_extractor.extract", extract_mock
    ), patch(
        "tools.jury.llm_client.urlopen",
        side_effect=lambda *a, **kw: next(iter_responses),
    ):
        code = main(
            [
                "--subsystem",
                sub,
                "--project-root",
                str(jury_env_with_specs),
                "--spec-md",
                str(spec_md),
                "--design-doc",
                str(design),
            ]
        )
    assert code == 0
    rep_path = (
        jury_env_with_specs
        / "cad"
        / sub
        / ".cad-spec-gen"
        / "runs"
        / "20260508-123456"
        / "PHOTO3D_JURY_REPORT.json"
    )
    rep = json.loads(rep_path.read_text(encoding="utf-8"))
    assert rep["overall_matches_spec"] is False, (
        f"overall_matches_spec 应 False；实际 {rep.get('overall_matches_spec')!r}"
    )
    assert rep["per_view_failed_features"] == {"front": ["fx1"]}, (
        f"per_view_failed_features 应 {{'front': ['fx1']}}；"
        f"实际 {rep.get('per_view_failed_features')!r}"
    )
    assert rep["matches_spec_status"] == "fail", (
        f"matches_spec_status 应 'fail'；实际 {rep.get('matches_spec_status')!r}"
    )


def test_photo3d_jury_report_no_features_yields_pass_status(
    jury_env_with_specs: Path,
) -> None:
    """无 features (无 --design-doc) 跑 jury，matches_spec_status 应为 'pass'。

    向后兼容：v2.36 老路径 features=[] → LLM payload 不含 features_status →
    ViewVerdict.matches_spec=True（默认）→ overall_matches_spec=True →
    matches_spec_status='pass'。
    """
    iter_responses = iter(
        [
            _make_response(_ok_payload_with_features_status("iso")),
            _make_response(_ok_payload_with_features_status("front")),
        ]
    )
    extract_mock = MagicMock(
        return_value={"features": [], "parse_anomalies": []}
    )

    sub = "lifting_platform"
    with patch(
        "tools.jury.feature_extractor.extract", extract_mock
    ), patch(
        "tools.jury.llm_client.urlopen",
        side_effect=lambda *a, **kw: next(iter_responses),
    ):
        # 不传 --design-doc → extract 不调 → features=[]
        code = main(
            [
                "--subsystem",
                sub,
                "--project-root",
                str(jury_env_with_specs),
            ]
        )
    assert code == 0
    rep_path = (
        jury_env_with_specs
        / "cad"
        / sub
        / ".cad-spec-gen"
        / "runs"
        / "20260508-123456"
        / "PHOTO3D_JURY_REPORT.json"
    )
    rep = json.loads(rep_path.read_text(encoding="utf-8"))
    assert rep["overall_matches_spec"] is True, (
        f"无 features 时 overall_matches_spec 应 True；"
        f"实际 {rep.get('overall_matches_spec')!r}"
    )
    assert rep["per_view_failed_features"] == {}, (
        f"无 features 时 per_view_failed_features 应 {{}}；"
        f"实际 {rep.get('per_view_failed_features')!r}"
    )
    assert rep["matches_spec_status"] == "pass", (
        f"无 features 时 matches_spec_status 应 'pass'；"
        f"实际 {rep.get('matches_spec_status')!r}"
    )


def test_photo3d_jury_report_schema_version_unchanged(
    jury_env_with_specs: Path,
) -> None:
    """schema_version 保持 1（不破 v2.36 fixture 向后兼容）。

    决策：主 agent 与 spec §5.2.3 + 不变量 #1 一致选择不 bump schema_version；
    新字段（overall_matches_spec / per_view_failed_features / matches_spec_status）
    全部加在顶层。理由：features=[] 时 3 字段全是 default value（True/{}/pass），
    老 fixture 不被破坏。
    """
    iter_responses = iter(
        [
            _make_response(_ok_payload_with_features_status("iso")),
            _make_response(_ok_payload_with_features_status("front")),
        ]
    )
    extract_mock = MagicMock(
        return_value={"features": [], "parse_anomalies": []}
    )

    sub = "lifting_platform"
    with patch(
        "tools.jury.feature_extractor.extract", extract_mock
    ), patch(
        "tools.jury.llm_client.urlopen",
        side_effect=lambda *a, **kw: next(iter_responses),
    ):
        code = main(
            [
                "--subsystem",
                sub,
                "--project-root",
                str(jury_env_with_specs),
            ]
        )
    assert code == 0
    rep_path = (
        jury_env_with_specs
        / "cad"
        / sub
        / ".cad-spec-gen"
        / "runs"
        / "20260508-123456"
        / "PHOTO3D_JURY_REPORT.json"
    )
    rep = json.loads(rep_path.read_text(encoding="utf-8"))
    assert rep["schema_version"] == 1, (
        f"schema_version 应保持 1；实际 {rep.get('schema_version')!r}"
    )


# ---------- Task 9：_handle_single_view_mode 接 features cache ----------


def _make_single_view_jury_config(home: Path) -> None:
    """单视角模式专用 jury config（同 main path 的 _write_jury_config 内容）。"""
    _write_jury_config(home)


def test_handle_single_view_reads_features_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Task 9 (B)：single-view 子进程从 cache 读 features → prompt 附特征。

    场景：
    - cad/<sub>/.cad-spec-gen/matches_spec_features.json 存在含 1 feature
    - main([..., "--single-view", "V4", "--image", path, "--subsystem", sub])
    - request_jury_verdict 被调用时 prompt 含 feature_id + description_cn
    """
    sub = "end_effector"
    cache_dir = tmp_path / "cad" / sub / ".cad-spec-gen"
    cache_dir.mkdir(parents=True)
    cache_path = cache_dir / "matches_spec_features.json"
    cache_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "subsystem": sub,
                "run_id": "rid-task9",
                "source_files": [],
                "features": [
                    {
                        "feature_id": "flange_arms_4",
                        "description_cn": "法兰 4 臂",
                        "expected_in_views": None,
                        "doc_ref": "",
                    }
                ],
                "parse_anomalies": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    img = tmp_path / "v4.jpg"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 200)

    _make_single_view_jury_config(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("CAD_JURY_DISABLE_LLM", raising=False)
    monkeypatch.chdir(tmp_path)

    captured_prompts: list[str] = []

    def fake_request(
        *, profile: Any, image_path: Any, prompt: str, max_retries: int
    ) -> Any:
        captured_prompts.append(prompt)
        from tools.jury.llm_client import LlmResponse

        return LlmResponse(
            content_text=json.dumps(
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
                            "reason": "看到 4 臂",
                        }
                    ],
                }
            ),
            attempts=1,
            http_status=200,
            latency_ms=100,
            finish_reason="stop",
            vendor_request_id="x",
        )

    monkeypatch.setattr("tools.photo3d_jury.request_jury_verdict", fake_request)

    code = main(
        [
            "--subsystem",
            sub,
            "--single-view",
            "V4",
            "--image",
            str(img),
        ]
    )
    assert code == 0, f"single-view main 应 exit 0；实际 {code}"
    assert len(captured_prompts) == 1
    # 关键断言：prompt 含 feature_id + description_cn
    assert "flange_arms_4" in captured_prompts[0], (
        f"prompt 应含 feature_id；实际 prompt={captured_prompts[0]!r}"
    )
    assert "法兰 4 臂" in captured_prompts[0], (
        f"prompt 应含 description_cn；实际 prompt={captured_prompts[0]!r}"
    )


def test_handle_single_view_no_cache_falls_back_to_default_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Task 9 (B) fail-safe：cache 不存在 → 用 _JURY_PROMPT 默认（行为同 v2.36）。"""
    sub = "end_effector"
    img = tmp_path / "v4.jpg"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 200)

    _make_single_view_jury_config(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("CAD_JURY_DISABLE_LLM", raising=False)
    monkeypatch.chdir(tmp_path)

    captured_prompts: list[str] = []

    def fake_request(
        *, profile: Any, image_path: Any, prompt: str, max_retries: int
    ) -> Any:
        captured_prompts.append(prompt)
        from tools.jury.llm_client import LlmResponse

        return LlmResponse(
            content_text=json.dumps(
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
            ),
            attempts=1,
            http_status=200,
            latency_ms=100,
            finish_reason="stop",
            vendor_request_id="x",
        )

    monkeypatch.setattr("tools.photo3d_jury.request_jury_verdict", fake_request)

    code = main(
        [
            "--subsystem",
            sub,
            "--single-view",
            "V4",
            "--image",
            str(img),
        ]
    )
    assert code == 0
    assert len(captured_prompts) == 1
    # 关键断言：无 cache 时不附加 features 段（与 _JURY_PROMPT 完全一致）
    assert captured_prompts[0] == _JURY_PROMPT, (
        "cache 缺时应回落 _JURY_PROMPT；实际 prompt 已被 augment"
    )


def test_handle_single_view_corrupt_cache_falls_back_safely(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Task 9 (B) fail-safe：cache 文件烂 JSON → 用 _JURY_PROMPT 默认（不抛异常）。"""
    sub = "end_effector"
    cache_dir = tmp_path / "cad" / sub / ".cad-spec-gen"
    cache_dir.mkdir(parents=True)
    (cache_dir / "matches_spec_features.json").write_text(
        "this is not valid JSON{{{", encoding="utf-8"
    )

    img = tmp_path / "v4.jpg"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 200)

    _make_single_view_jury_config(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("CAD_JURY_DISABLE_LLM", raising=False)
    monkeypatch.chdir(tmp_path)

    captured_prompts: list[str] = []

    def fake_request(
        *, profile: Any, image_path: Any, prompt: str, max_retries: int
    ) -> Any:
        captured_prompts.append(prompt)
        from tools.jury.llm_client import LlmResponse

        return LlmResponse(
            content_text=json.dumps(
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
            ),
            attempts=1,
            http_status=200,
            latency_ms=100,
            finish_reason="stop",
            vendor_request_id="x",
        )

    monkeypatch.setattr("tools.photo3d_jury.request_jury_verdict", fake_request)

    code = main(
        [
            "--subsystem",
            sub,
            "--single-view",
            "V4",
            "--image",
            str(img),
        ]
    )
    assert code == 0
    assert captured_prompts[0] == _JURY_PROMPT, (
        "cache 烂时应回落 _JURY_PROMPT（fail-safe，不阻塞 single-view）"
    )
