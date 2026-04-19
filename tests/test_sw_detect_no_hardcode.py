"""
tests/test_sw_detect_no_hardcode.py — 防御性测试：确保 sw_detect.py 不含硬编码路径/年份。

测试策略：
- 读取源文件文本，用正则检查非注释行中是否出现禁用字面值。
- 此测试不依赖 Windows / SW 环境，任何 CI 平台均可运行。
"""

import re
from pathlib import Path


def test_sw_detect_no_hardcoded_paths_or_years():
    """sw_detect.py 非注释行不得出现具体路径/年份字面值。

    禁用字面值（出现在字符串字面量中）：
    - "Program Files"（硬编码 Windows 系统目录）
    - "D:\\"（硬编码驱动器路径）
    - "20XX"（2020-2039 的年份，如 "2024"）

    注释行（以 # 开头，允许前置空格）可保留历史描述性说明，不计入检查。
    """
    src_path = Path(__file__).parent.parent / "adapters" / "solidworks" / "sw_detect.py"
    assert src_path.exists(), f"源文件不存在：{src_path}"

    src = src_path.read_text(encoding="utf-8")

    # 匹配：非注释行（允许前置空白）中出现禁用字面值（包裹在双/单引号内）
    # ^[^#]* 排除以 # 开头（含前置空格）的注释行
    # 对带前置空格的注释行：如 "    # comment"，[^#]* 会匹配 "    "，需要用 \s*# 守卫
    forbidden = re.compile(
        r'^(?!\s*#).*("Program Files"|\'Program Files\'|"D:\\\\"|\'D:\\\\\'|"20(?:2[0-9]|3[0-9])"|\'20(?:2[0-9]|3[0-9])\')'
    )

    bad = [
        (i + 1, line)
        for i, line in enumerate(src.splitlines())
        if forbidden.search(line)
    ]

    assert not bad, (
        "sw_detect.py 检测到硬编码（行号: 内容）:\n"
        + "\n".join(f"  L{lineno}: {content}" for lineno, content in bad)
    )
