"""
tests/test_sw_detect_no_hardcode.py — 防御性测试：确保 sw_detect.py 不含硬编码路径/年份。

测试策略：
- 读取源文件文本，用正则检查非注释行中是否出现禁用字面值。
- 此测试不依赖 Windows / SW 环境，任何 CI 平台均可运行。
"""

import inspect
import re
from pathlib import Path

# ---- 辅助函数 ---------------------------------------------------------------

def _load_sw_detect_source() -> str:
    """读取 sw_detect.py 源码文本。"""
    src_path = Path(__file__).parent.parent / "adapters" / "solidworks" / "sw_detect.py"
    assert src_path.exists(), f"源文件不存在：{src_path}"
    return src_path.read_text(encoding="utf-8")


def _non_comment_lines(src: str) -> list[tuple[int, str]]:
    """返回源码中的非注释行（行号从 1 起）。"""
    return [
        (i + 1, line)
        for i, line in enumerate(src.splitlines())
        if not re.match(r"^\s*#", line)
    ]


# ---- §3.5.1 item 1+2 — 安装路径 + 年份字面值（原有测试）-------------------

def test_sw_detect_no_hardcoded_paths_or_years():
    """sw_detect.py 非注释行不得出现具体路径/年份字面值。

    禁用字面值（出现在字符串字面量中）：
    - "Program Files"（硬编码 Windows 系统目录）
    - "D:\\"（硬编码驱动器路径）
    - "20XX"（2020-2039 的年份，如 "2024"）

    注释行（以 # 开头，允许前置空格）可保留历史描述性说明，不计入检查。
    """
    src = _load_sw_detect_source()

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


# ---- §3.5.1 item 3 — range 硬编码年份上界 -----------------------------------

def test_enumerate_years_uses_no_range_literals():
    """_enumerate_registered_years 或 _find_install_from_registry 不得使用 range(20XX...) 字面值。

    spec §4.1 脚注 ³：SW 出新版本不需要改任何代码。
    range(2030, 2019, -1) 会在 SW 2031 出现时悄悄失效，必须消除。
    """
    from adapters.solidworks import sw_detect

    # 检查两个候选函数（新函数名 or 旧函数名）
    target_names = ["_enumerate_registered_years", "_find_install_from_registry"]
    found_range = False
    for name in target_names:
        fn = getattr(sw_detect, name, None)
        if fn is None:
            continue
        src = inspect.getsource(fn)
        # range(20 开头 → 硬编码年份上界
        if re.search(r"range\s*\(\s*20\d{2}", src):
            found_range = True
            break

    assert not found_range, (
        "_find_install_from_registry / _enumerate_registered_years 仍含 range(20XX...) 字面值，"
        "请改用 winreg.EnumKey 动态枚举注册表子键。"
    )


# ---- §3.5.1 item 4 — Toolbox 路径字面值 ------------------------------------

def test_no_toolbox_path_literal():
    """sw_detect.py 非注释行不得出现 Toolbox 目录硬编码路径字面值。

    禁用：含 '\\\\Toolbox\\\\' / '\\\\Toolbox Library\\\\' 的字符串字面量。
    注：从注册表键名 "Toolbox Data Location" 读取是允许的（键名不是路径）。
    """
    src = _load_sw_detect_source()
    # 检测：字符串引号内出现 \\Toolbox\\ 或 Toolbox Library\ 等绝对路径片段
    forbidden = re.compile(
        r'^(?!\s*#).*(["\']).*[/\\\\]Toolbox[/\\\\].*\1'
    )
    bad = [
        (lineno, line)
        for lineno, line in _non_comment_lines(src)
        if forbidden.search(line)
    ]
    assert not bad, (
        "sw_detect.py 检测到 Toolbox 路径硬编码（行号: 内容）:\n"
        + "\n".join(f"  L{lineno}: {line}" for lineno, line in bad)
    )


# ---- §3.5.1 item 5 — pywin32 安装路径字面值 ---------------------------------

def test_no_pywin32_path_literal():
    """sw_detect.py 非注释行不得出现 pywin32 安装路径硬编码字面值。

    禁用：'site-packages' / 'win32com\\\\' 等路径字面量。
    用 'import win32com.client' 动态检测是允许的（不含路径）。
    """
    src = _load_sw_detect_source()
    forbidden_patterns = [
        r'"site-packages"',
        r"'site-packages'",
        r'"win32com\\\\"',
        r"'win32com\\\\'",
    ]
    combined = re.compile(
        r'^(?!\s*#).*(' + "|".join(forbidden_patterns) + r")"
    )
    bad = [
        (lineno, line)
        for lineno, line in _non_comment_lines(src)
        if combined.search(line)
    ]
    assert not bad, (
        "sw_detect.py 检测到 pywin32 路径硬编码（行号: 内容）:\n"
        + "\n".join(f"  L{lineno}: {line}" for lineno, line in bad)
    )


# ---- §3.5.1 item 6 — Add-In GUID 完整字面值 ---------------------------------

def test_no_addin_guid_literal():
    """sw_detect.py 非注释行不得出现完整 Add-In GUID 字面值。

    完整 GUID 格式：{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}（32 hex + 4 连字符）
    允许：GUID 前缀片段（如 'bbf84e59' 用于宽松匹配），禁止完整 GUID。
    """
    src = _load_sw_detect_source()
    # 完整 GUID：{8hex-4hex-4hex-4hex-12hex}
    full_guid = re.compile(
        r'^(?!\s*#).*["\']'
        r'\{[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\}'
        r'["\']'
    )
    bad = [
        (lineno, line)
        for lineno, line in _non_comment_lines(src)
        if full_guid.search(line)
    ]
    assert not bad, (
        "sw_detect.py 检测到完整 GUID 硬编码（行号: 内容）:\n"
        + "\n".join(f"  L{lineno}: {line}" for lineno, line in bad)
    )


# ---- §3.5.1 item 7 — 双 hive 覆盖（弱防御）---------------------------------

def test_uses_both_hkcu_and_hklm():
    """sw_detect.py 必须同时引用 HKEY_CURRENT_USER 和 HKEY_LOCAL_MACHINE。

    弱防御：防止实现者只查 HKLM 而遗漏 HKCU（部分 SW 配置写入 HKCU）。
    检查方式：源文件中两个标识符均须出现至少一次。
    """
    src = _load_sw_detect_source()
    assert "HKEY_CURRENT_USER" in src, (
        "sw_detect.py 缺少 HKEY_CURRENT_USER 引用，"
        "部分 SW 配置（如 AddInsStartup）写入 HKCU，必须查询。"
    )
    assert "HKEY_LOCAL_MACHINE" in src, (
        "sw_detect.py 缺少 HKEY_LOCAL_MACHINE 引用，"
        "SW 安装信息写入 HKLM，必须查询。"
    )
