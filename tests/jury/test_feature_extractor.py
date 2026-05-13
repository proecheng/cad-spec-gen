"""L3 feature_extractor 单元测试 — mock LLM + cache + fail-safe + 12 限制。"""

from __future__ import annotations

import json
import pathlib
from unittest.mock import MagicMock

from tools.jury.feature_extractor import _MAX_FEATURES, extract


def _mock_llm_returning(features: list[dict]) -> MagicMock:
    """构造一个返回 features JSON 的假 LLM client。"""
    client = MagicMock()
    client.complete.return_value = json.dumps({"features": features})
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
    client.complete.side_effect = RuntimeError("503 backend down")

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
    client.complete.return_value = "not a json at all"

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
