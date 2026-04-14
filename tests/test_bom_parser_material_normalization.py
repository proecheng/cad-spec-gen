"""BOM material 缺省字符串规范化测试（Part 2c P1 T5 / Part 2b M-6）。

_normalize_material 把工程 BOM 里的"无材质"惯用写法（CJK + 英文 + Excel 自动替换
后的全角破折号）统一归一为空字符串，下游视同 unset；真值（如 Q235B）保持原样。
"""

from __future__ import annotations

import pytest


# 9 条缺省 token：与 bom_parser._MATERIAL_ABSENT_TOKENS 对齐
# （"—" 是 U+2014 em dash；"——" 是 U+2014×2 两 em dash 连写）
@pytest.mark.parametrize(
    "raw",
    [
        "",
        "-",
        "—",  # U+2014
        "——",  # U+2014 × 2
        "/",
        "N/A",
        "n/a",
        "NA",
        "na",
        "无",
        "无材质",
    ],
)
def test_normalize_material_absent_tokens_return_empty(raw):
    """9 条（+3 大小写变体）缺省 token 都归一为 ""。"""
    from bom_parser import _normalize_material

    assert _normalize_material(raw) == ""


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, ""),  # 非 str 类型契约
        ("   ", ""),  # 纯空白 → strip 后 ""
        ("\tN/A\n", ""),  # 两端空白 + 缺省值
    ],
)
def test_normalize_material_edge_cases(raw, expected):
    """QA Q3：None / 纯空白 / 两端空白边界。"""
    from bom_parser import _normalize_material

    assert _normalize_material(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "Q235B",
        "45#",
        "7075-T6铝合金",
        "Al 6061-T6  硬质阳极氧化≥25μm",
        "S355JR",
    ],
)
def test_normalize_material_real_values_preserved(raw):
    """真值反例：不被误杀（T5 集合只 == 比较，非 substring）。"""
    from bom_parser import _normalize_material

    assert _normalize_material(raw) == raw.strip()
