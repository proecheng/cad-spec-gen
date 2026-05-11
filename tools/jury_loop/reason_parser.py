"""jury reason 文本 → tag 集合的纯函数 + reason_sanitized 防 prompt injection。"""
from __future__ import annotations

import re
import string

# tag → 触发关键词 patterns（spec §4.2 内置 tag_dictionary 起步集）
BUILTIN_TAG_DICTIONARY: dict[str, list[str]] = {
    "plastic_look":   ["plastic", "toy-like", "rubbery", "matte plastic"],
    "flat_light":     ["flat lighting", "no shadows", "ambient only", "diffuse"],
    "soft_edge":      ["soft edge", "blurry edge", "out of focus", "fuzzy"],
    "blurry":         ["blurry", "low resolution"],
    "dull_color":     ["dull", "muted", "low contrast"],
    "washed_out":     ["washed out", "faded", "desaturated"],
    "dark_overall":   ["too dark", "underexposed", "low light"],
    "cluttered_bg":   ["cluttered background", "busy background"],
    "distracting_bg": ["distracting background", "noisy backdrop"],
    # 备选 tag（rule 暂未配，实施时根据 jury 输出扩充）
    "dull_metal":        [],
    "fake_glass":        [],
    "missing_pbr":       [],
    "harsh_shadow":      [],
    "blown_highlights":  [],
    "jagged":            [],
    "oversharpened":     [],
    "oversaturated":     [],
    "color_cast":        [],
    "dirty_bg":          [],
}
BUILTIN_TAGS: frozenset[str] = frozenset(BUILTIN_TAG_DICTIONARY.keys())

_PRINTABLE_ASCII = set(string.printable) - set("\x0b\x0c")  # 排除 vert tab / form feed
_REASON_MAX_LEN = 200


def reason_sanitized(text: str) -> str:
    """SEC-MAJOR-3 净化：剥控制字符、ANSI escape、非 ASCII、≤200 截断。"""
    if not isinstance(text, str):
        return ""
    no_ansi = re.sub(r"\x1b\[[0-9;]*m", "", text)
    cleaned = "".join(c for c in no_ansi if c in _PRINTABLE_ASCII and c not in {"\t", "\n", "\r"})
    return cleaned[:_REASON_MAX_LEN]


def parse_reason(
    text: str,
    tag_dictionary: dict[str, list[str]] | None = None,
) -> set[str]:
    """jury reason → tag 集合。大小写不敏感；纯函数。

    参数：
        text: jury 反馈文本（建议先经 reason_sanitized 净化）
        tag_dictionary: 可选自定义 tag→patterns 映射。None 时默认使用
            BUILTIN_TAG_DICTIONARY；orchestrator 可传 rule_table.load_rule_table
            合并后的 RuleTable.tag_dictionary 让用户 yaml 扩 tag 生效（spec §5 #8）。
    """
    if not isinstance(text, str) or not text:
        return set()
    table = BUILTIN_TAG_DICTIONARY if tag_dictionary is None else tag_dictionary
    lowered = text.lower()
    hits: set[str] = set()
    for tag, patterns in table.items():
        for pat in patterns:
            if pat.lower() in lowered:
                hits.add(tag)
                break
    return hits
