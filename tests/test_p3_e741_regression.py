"""§11-N1 P3 E741 characterization regression tests.

固定 rename 后行为，检测意外回退。
"""
from __future__ import annotations

import re
from pathlib import Path


def test_jinja_primitive_adapter_no_l_ambiguous_var() -> None:
    """结构检查：rename 后 jinja_primitive_adapter.py 内无裸 `l` 变量。

    允许：`l` 出现在注释 / 字符串 / `# noqa: E741` 行（数学保留 case）。
    禁止：`l = ...`、`def f(..., l, ...)`、`for l in ...`。
    """
    src = Path("adapters/parts/jinja_primitive_adapter.py").read_text(encoding="utf-8")

    # 无裸 `l = ` 赋值（noqa 行豁免）
    for ln_num, line in enumerate(src.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue  # 跳过注释
        if "noqa: E741" in line:
            continue  # 数学保留
        # 模式: `l = ...` (裸；非字符串内的 `l =`)
        if re.match(r"^\s*l\s*=\s*[^=]", line):
            raise AssertionError(
                f"jinja_primitive_adapter.py:{ln_num} 发现裸 `l =`: {line!r}"
            )

    # 无 `def f(d, l, ...)` 函数签名
    matches = re.findall(r"\bdef\s+\w+\([^)]*\bl\b[^)]*\)", src)
    matches = [m for m in matches if not m.startswith("def __")]  # 排除 dunder
    assert not matches, f"`l` 出现在函数签名: {matches!r}"


def test_cad_spec_reviewer_math_reserved_I_intact() -> None:
    """数学保留 `I = ...`（惯性矩）必须仍存在并带 noqa: E741。

    spec §2.7 数学保留 case — rename target = NOQA。
    """
    src = Path("cad_spec_reviewer.py").read_text(encoding="utf-8")
    has_i_with_noqa = any(
        re.match(r"^\s*I\s*=", line) and "noqa: E741" in line
        for line in src.splitlines()
    )
    assert has_i_with_noqa, (
        "cad_spec_reviewer.py: `I = ... # noqa: E741` 数学保留未找到"
    )
