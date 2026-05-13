"""L4 prompt_rewriter — hint() 注入 missing features 名到 enhance prompt 末尾。"""

from __future__ import annotations

from tools.jury.prompt_rewriter import hint


def test_hint_appends_missing_features_to_base() -> None:
    """missing features 名 + 视角 id 全出现在输出 prompt 中。"""
    base = "base prompt for V4 enhance"
    out = hint(
        view_id="V4",
        missing_features=["flange_arms_4", "peek_ring"],
        base_prompt=base,
    )
    assert "flange_arms_4" in out
    assert "peek_ring" in out
    assert "V4" in out
    assert base in out, "base prompt 应保留（不是替换而是追加）"


def test_hint_empty_missing_features_returns_base_unchanged() -> None:
    """missing_features 为空 → 原 prompt 返回（不动）。"""
    base = "base prompt"
    out = hint(view_id="V1", missing_features=[], base_prompt=base)
    assert out == base, "空 missing 时 prompt 不应被改动"


def test_hint_preserves_base_prompt_content_intact() -> None:
    """Base 含特殊字符（中文 / 引号 / 换行）也能保留原貌。"""
    base = "请重画这张图：\n  - 法兰\n  - 「特殊」字符"
    out = hint(
        view_id="V5",
        missing_features=["arms"],
        base_prompt=base,
    )
    assert base in out
    assert "arms" in out
    assert "V5" in out


def test_hint_uses_chinese_phrasing() -> None:
    """spec D2 + §5.3 要中文人话；hint 末段应含中文标识（'特征'/'视角'/'矫正'等关键词）。"""
    out = hint(
        view_id="V4",
        missing_features=["flange_arms_4"],
        base_prompt="x",
    )
    # 至少有一个中文关键词（feature 反馈 / 矫正 / 视角 / 特征 / 强调 任一）
    assert any(w in out for w in ("特征", "视角", "强调", "矫正", "反馈")), (
        f"输出应含中文反馈关键词；实际：{out[-200:]}"
    )
