"""Layer 1 — 字段自洽性二次验证（输入到此前已 Layer 0 通过）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from tools.jury.deterministic_gate import run_layer1


def _load_fixture() -> dict[str, Any]:
    path = Path("tests/jury/fixtures/sample_enhancement_report.json")
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def test_all_accepted_passes() -> None:
    report = _load_fixture()
    v = run_layer1(report)
    assert v.passed is True
    assert v.per_view_failures == []


def test_view_status_not_accepted_fails() -> None:
    report = _load_fixture()
    report["views"][0]["status"] = "preview"
    v = run_layer1(report)
    assert v.passed is False
    assert any(f["view"] == "iso" for f in v.per_view_failures)


def test_edge_similarity_below_min_similarity_fails() -> None:
    report = _load_fixture()
    report["views"][0]["edge_similarity"] = 0.50
    v = run_layer1(report)
    assert v.passed is False


def test_effective_contrast_stddev_none_fails() -> None:
    report = _load_fixture()
    report["views"][0]["quality_metrics"]["effective_contrast_stddev"] = None
    v = run_layer1(report)
    assert v.passed is False


def test_effective_contrast_stddev_below_threshold_fails() -> None:
    report = _load_fixture()
    report["views"][0]["quality_metrics"]["effective_contrast_stddev"] = 5.0
    v = run_layer1(report)
    assert v.passed is False


def test_quality_metrics_missing_fails() -> None:
    report = _load_fixture()
    del report["views"][0]["quality_metrics"]
    v = run_layer1(report)
    assert v.passed is False


def test_mixed_views_partial_fail() -> None:
    report = _load_fixture()
    report["views"][1]["edge_similarity"] = 0.5  # 只 front fail
    v = run_layer1(report)
    assert v.passed is False
    assert len(v.per_view_failures) == 1
    assert v.per_view_failures[0]["view"] == "front"


def test_min_similarity_missing_fallback_085() -> None:
    report = _load_fixture()
    del report["min_similarity"]
    v = run_layer1(report)
    assert v.passed is True  # 0.91 / 0.88 都 >= 0.85 fallback


def test_threshold_constant_matches_enhance_consistency() -> None:
    """rev 4 inv：测试断言 jury 阈值与 tools/enhance_consistency.py 同值。"""
    from tools.enhance_consistency import MIN_PHOTO_CONTRAST_STDDEV as ENHANCE_THRESHOLD
    from tools.jury.deterministic_gate import (
        MIN_PHOTO_CONTRAST_STDDEV as JURY_THRESHOLD,
    )

    assert JURY_THRESHOLD == pytest.approx(ENHANCE_THRESHOLD)
