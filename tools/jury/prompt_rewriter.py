"""Prompt rewriter — 把 matches_spec retry 的反馈信息注入到 enhance prompt 末尾。

供 jury_loop retry 路径用（Task 9 wire）：
    jury 看 V4 时发现 missing features = ["flange_arms_4"] →
    prompt_rewriter.hint("V4", ["flange_arms_4"], 原 enhance prompt) →
    新 prompt = 原 + 中文反馈段（点名 missing features 让 enhance LLM 强调它们）

v1 朴素拼接（spec §3 D2 / §4 Out of Scope v2 智能化）：
    - 空 missing → 返原 prompt（不变）
    - 非空 missing → 末尾拼接固定中文模板 + missing feature_id 列表
"""

from __future__ import annotations


def hint(
    *,
    view_id: str,
    missing_features: list[str],
    base_prompt: str,
) -> str:
    """注入 missing features 反馈到 enhance prompt 末尾。

    Args:
        view_id: 视角标识（如 "V4"），写进反馈段让 enhance LLM 知道针对哪个视角。
        missing_features: feature_id 字符串列表（如 ["flange_arms_4", "peek_ring"]）。
        base_prompt: 原 enhance prompt 文本。

    Returns:
        新 prompt：base_prompt + 中文反馈段（missing 非空时），
        或 base_prompt 原样（missing 空时）。
    """
    if not missing_features:
        return base_prompt
    feature_list = ", ".join(missing_features)
    suffix = (
        f"\n\n[matches_spec 反馈 / 视角 {view_id}] "
        f"上次未在图里看到以下设计特征：{feature_list}。"
        f"\n请在新一轮增强时**保留并强调**这些几何/装配特征的可见性。"
    )
    return base_prompt + suffix
