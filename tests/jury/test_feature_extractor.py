"""L3 feature_extractor 单元测试 — mock LLM + cache + fail-safe + 12 限制。"""

from __future__ import annotations

import json
import pathlib
from unittest.mock import MagicMock

from tools.jury.feature_extractor import _MAX_FEATURES, extract


def _mock_llm_returning(features: list[dict]) -> MagicMock:
    """构造一个返回 features JSON 的假 LLM client（双端点都返同样 JSON）。

    F8 spec：feature_extractor 优先 complete_text，无则 fallback complete；
    此 helper 给两个端点都挂同样 return_value，让"路由测试以外"的用例不关心端点。
    """
    client = MagicMock()
    payload = json.dumps({"features": features})
    client.complete.return_value = payload
    client.complete_text.return_value = payload
    return client


def test_extract_happy_path_writes_cache_and_returns_features(
    tmp_path: pathlib.Path,
) -> None:
    """快乐路径：LLM 正常返回 → 特征落盘 + 返回结构正确。"""
    spec_md = tmp_path / "CAD_SPEC.md"
    spec_md.write_text("# Spec\n\nFLANGE_BODY_OD = 90 mm\n", encoding="utf-8")
    design = tmp_path / "design.md"
    design.write_text("法兰应含 4 条径向悬臂\n", encoding="utf-8")
    cache_dir = tmp_path / ".cad-spec-gen"

    features = [
        {
            "feature_id": "flange_arms_4",
            "description_cn": "法兰 4 条径向悬臂",
            "expected_in_views": ["V4", "V5"],
            "doc_ref": "design.md L1",
        },
    ]
    client = _mock_llm_returning(features)

    result = extract(
        spec_md,
        design,
        cache_dir=cache_dir,
        llm_client=client,
        subsystem="end_effector",
        run_id="test-run",
    )

    assert len(result["features"]) == 1
    assert result["features"][0]["feature_id"] == "flange_arms_4"
    # 落盘到 cache 文件
    cache_file = cache_dir / "matches_spec_features.json"
    assert cache_file.exists()
    cached = json.loads(cache_file.read_text(encoding="utf-8"))
    assert cached["subsystem"] == "end_effector"


def test_extract_llm_failure_returns_empty_features_no_raise(
    tmp_path: pathlib.Path,
) -> None:
    """fail-safe：LLM 抛异常 → 返回 {features: []}（pipeline 继续）。"""
    spec_md = tmp_path / "CAD_SPEC.md"
    spec_md.write_text("# Spec\n", encoding="utf-8")
    design = tmp_path / "design.md"
    design.write_text("design\n", encoding="utf-8")

    client = MagicMock()
    # F8：两端点都挂同样 side_effect，确保不论走哪条都触发 fail-safe
    client.complete.side_effect = RuntimeError("503 backend down")
    client.complete_text.side_effect = RuntimeError("503 backend down")

    result = extract(
        spec_md,
        design,
        cache_dir=tmp_path,
        llm_client=client,
        subsystem="end_effector",
        run_id="test-run",
    )
    assert result == {
        "features": [],
        "parse_anomalies": ["feature_extraction_failed"],
    }


def test_extract_truncates_at_12_features(tmp_path: pathlib.Path) -> None:
    """spec D6 / §5.2.1：超过 12 条截断 + parse_anomalies。"""
    spec_md = tmp_path / "CAD_SPEC.md"
    spec_md.write_text("# Spec\n", encoding="utf-8")
    design = tmp_path / "design.md"
    design.write_text("design\n", encoding="utf-8")

    too_many = [
        {
            "feature_id": f"f{i}",
            "description_cn": f"feature {i}",
            "expected_in_views": None,
            "doc_ref": "",
        }
        for i in range(20)
    ]
    client = _mock_llm_returning(too_many)

    result = extract(
        spec_md,
        design,
        cache_dir=tmp_path,
        llm_client=client,
        subsystem="end_effector",
        run_id="test-run",
    )
    assert len(result["features"]) == _MAX_FEATURES
    assert "feature_extraction_truncated" in result.get("parse_anomalies", [])


def test_extract_invalid_json_returns_empty_features(
    tmp_path: pathlib.Path,
) -> None:
    """LLM 返回非 JSON → fail-safe 不阻断。"""
    spec_md = tmp_path / "CAD_SPEC.md"
    spec_md.write_text("# Spec\n", encoding="utf-8")
    design = tmp_path / "design.md"
    design.write_text("design\n", encoding="utf-8")

    client = MagicMock()
    # F8：两端点都返同一非 JSON 字符串
    client.complete.return_value = "not a json at all"
    client.complete_text.return_value = "not a json at all"

    result = extract(
        spec_md,
        design,
        cache_dir=tmp_path,
        llm_client=client,
        subsystem="end_effector",
        run_id="test-run",
    )
    assert result["features"] == []
    assert "feature_extraction_failed" in result.get("parse_anomalies", [])


def test_extract_prefers_text_endpoint_when_available(
    tmp_path: pathlib.Path,
) -> None:
    """spec F8：有 complete_text 时优先用 text endpoint。"""
    spec_md = tmp_path / "CAD_SPEC.md"
    spec_md.write_text("# Spec\n", encoding="utf-8")
    design = tmp_path / "design.md"
    design.write_text("design\n", encoding="utf-8")

    client = MagicMock()
    client.complete_text = MagicMock(return_value=json.dumps({"features": []}))
    client.complete = MagicMock(return_value=json.dumps({"features": []}))

    extract(
        spec_md,
        design,
        cache_dir=tmp_path,
        llm_client=client,
        subsystem="end_effector",
        run_id="test",
    )

    # 优先 text endpoint
    client.complete_text.assert_called_once()
    client.complete.assert_not_called()


def test_extract_falls_back_to_complete_when_no_text_endpoint(
    tmp_path: pathlib.Path,
) -> None:
    """spec F8：无 complete_text 时 fallback 到 vision/通用 complete。"""
    spec_md = tmp_path / "CAD_SPEC.md"
    spec_md.write_text("# Spec\n", encoding="utf-8")
    design = tmp_path / "design.md"
    design.write_text("design\n", encoding="utf-8")

    client = MagicMock(spec=["complete"])  # 仅 complete，无 complete_text
    client.complete.return_value = json.dumps({"features": []})

    extract(
        spec_md,
        design,
        cache_dir=tmp_path,
        llm_client=client,
        subsystem="end_effector",
        run_id="test",
    )

    client.complete.assert_called_once()


# ============ v2.37.1 hotfix：LLM 包 markdown 围栏的兼容 ============


def test_extract_strips_markdown_json_fence(tmp_path: pathlib.Path) -> None:
    """v2.37.1：LLM 把 JSON 包在 ```json ... ``` 围栏里也能正确解析。

    实测 micuapi.ai gpt-image-2-pro 等模型即使 prompt 写"不要 markdown"也常坚持
    包代码围栏。extract() 现在用纯 json.loads 会 fail-safe 退化为空 features。
    本测试 + GREEN 实现给 extract() 加 fence-stripping 兜底。
    """
    spec_md = tmp_path / "CAD_SPEC.md"
    spec_md.write_text("# Spec\n", encoding="utf-8")
    design = tmp_path / "design.md"
    design.write_text("design\n", encoding="utf-8")

    features = [
        {"feature_id": "f1", "description_cn": "特征 1",
         "expected_in_views": None, "doc_ref": "x"},
    ]
    fenced = "```json\n" + json.dumps({"features": features}) + "\n```"

    client = MagicMock()
    client.complete_text.return_value = fenced
    client.complete.return_value = fenced

    result = extract(
        spec_md, design, cache_dir=tmp_path, llm_client=client,
        subsystem="end_effector", run_id="test",
    )
    assert result["features"] == features, \
        f"应脱 markdown 围栏后正确解析；实际：{result}"
    assert "feature_extraction_failed" not in result.get("parse_anomalies", [])


def test_extract_strips_markdown_fence_without_json_tag(
    tmp_path: pathlib.Path,
) -> None:
    """v2.37.1：围栏可能不带 `json` 语言标识——也要脱掉。"""
    spec_md = tmp_path / "CAD_SPEC.md"
    spec_md.write_text("# Spec\n", encoding="utf-8")
    design = tmp_path / "design.md"
    design.write_text("design\n", encoding="utf-8")

    features = [
        {"feature_id": "f1", "description_cn": "特征 1",
         "expected_in_views": None, "doc_ref": "x"},
    ]
    fenced = "```\n" + json.dumps({"features": features}) + "\n```"

    client = MagicMock()
    client.complete_text.return_value = fenced
    client.complete.return_value = fenced

    result = extract(
        spec_md, design, cache_dir=tmp_path, llm_client=client,
        subsystem="end_effector", run_id="test",
    )
    assert result["features"] == features


def test_extract_unfenced_json_still_works(tmp_path: pathlib.Path) -> None:
    """v2.37.1：原本就 unfenced 的 JSON（v2.37 happy path）回归仍 PASS。"""
    spec_md = tmp_path / "CAD_SPEC.md"
    spec_md.write_text("# Spec\n", encoding="utf-8")
    design = tmp_path / "design.md"
    design.write_text("design\n", encoding="utf-8")

    features = [
        {"feature_id": "f1", "description_cn": "特征 1",
         "expected_in_views": None, "doc_ref": "x"},
    ]
    plain = json.dumps({"features": features})

    client = MagicMock()
    client.complete_text.return_value = plain
    client.complete.return_value = plain

    result = extract(
        spec_md, design, cache_dir=tmp_path, llm_client=client,
        subsystem="end_effector", run_id="test",
    )
    assert result["features"] == features
