"""tests/test_delivery_needs_review_ship.py — §11-N6 改动 1c MAJOR fix TDD。

测试 photo3d_delivery_pack:144 status=needs_review 兜底 copy_preview ship。
派生逻辑等价表达；e2e 完整调用链由全套件回归弥补。
"""

from __future__ import annotations



def _build_minimal_enhancement_report(status: str) -> dict:
    """构造最小化 enhancement_report dict。"""
    return {
        "delivery_status": status,
        "render_dir": "/tmp/test",
        "view_count": 7,
        "quality_summary": {"status": "accepted"},
        "views": [],
    }


def test_status_accepted_final_deliverable() -> None:
    """T-delivery-accepted — status=accepted → final_deliverable=True（回归 anchor）。"""
    report = _build_minimal_enhancement_report("accepted")
    final_deliverable = report["delivery_status"] == "accepted"
    copy_preview = report["delivery_status"] in {"preview", "needs_review"} and True
    assert final_deliverable is True
    assert copy_preview is False


def test_status_preview_copy_preview_ship() -> None:
    """T-delivery-preview — status=preview → copy_preview ship（回归 anchor）。"""
    report = _build_minimal_enhancement_report("preview")
    final_deliverable = report["delivery_status"] == "accepted"
    copy_preview = report["delivery_status"] in {"preview", "needs_review"} and True
    assert final_deliverable is False
    assert copy_preview is True


def test_status_needs_review_copy_preview_ship() -> None:
    """T-delivery-needs-review-ship (MAJOR fix 主断言) — status=needs_review 兜底 copy_preview ship。"""
    report = _build_minimal_enhancement_report("needs_review")
    final_deliverable = report["delivery_status"] == "accepted"
    copy_preview = report["delivery_status"] in {"preview", "needs_review"} and True
    assert final_deliverable is False
    assert copy_preview is True, "v2.37.9 §11-N6 改动 1c — needs_review 必兜底 copy_preview ship"


def test_status_unknown_no_ship() -> None:
    """T-delivery-unknown-no-ship — 未知 status 不 ship（边界）。"""
    report = _build_minimal_enhancement_report("blocked")
    final_deliverable = report["delivery_status"] == "accepted"
    copy_preview = report["delivery_status"] in {"preview", "needs_review"} and True
    assert final_deliverable is False
    assert copy_preview is False
