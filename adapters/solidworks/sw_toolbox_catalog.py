"""
adapters/solidworks/sw_toolbox_catalog.py — Toolbox 目录扫描 + 索引 + 匹配。

纯 stdlib 实现，不依赖 COM。提供：
- SwToolboxPart 数据类（v4 决策 #14）
- SCHEMA_VERSION 索引 schema 版本号（v4 决策 #21）
- build_toolbox_index / load_toolbox_index
- tokenize / extract_size_from_name / validate_size_patterns
- match_toolbox_part（加权 token overlap）
- _validate_sldprt_path（路径遍历防御，v4 决策 #20）

路径解析遵循 v4 决策 #16/#17：
- 路径覆盖链: yaml > env > 默认
- 必须用 Path.home() 不用 os.path.expanduser
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
"""每次索引结构变更必须 bump；旧缓存自动重建。"""

CACHE_ROOT_ENV = "CAD_SPEC_GEN_SW_TOOLBOX_CACHE"
INDEX_PATH_ENV = "CAD_SPEC_GEN_SW_TOOLBOX_INDEX"


@dataclass
class SwToolboxPart:
    """v4 决策 #14: 从 ToolboxPart 改名，遵循 Sw 前缀命名风格。"""

    standard: str
    """标准，如 'GB' / 'ISO' / 'DIN'"""

    subcategory: str
    """子分类，如 'bolts and studs' / 'nuts'"""

    sldprt_path: str
    """绝对路径"""

    filename: str
    """文件名（含扩展名）"""

    tokens: list[str] = field(default_factory=list)
    """拆分 + 小写 + 去 stop_words 后的 token 列表（v4 决策 #18）"""


# ---------------------------------------------------------------------------
# 停用词：英语常用连接词 + Toolbox 子目录里的粘合词
# ---------------------------------------------------------------------------

STOP_WORDS: frozenset[str] = frozenset({
    "and", "for", "with", "the", "of", "type",
    "a", "an", "in", "on", "to", "by",
})


def tokenize(text: str) -> list[str]:
    """拆分文本为小写 token 列表（v4 决策 #18）。

    拆分规则：
    - 空格、下划线、连字符作为分隔符
    - 中英文边界切分（CJK 字符整体保留，ASCII 小写化）
    - 过滤 STOP_WORDS 以避免 'bolts and studs' 产出 'and' 污染打分

    Args:
        text: 待分词的字符串

    Returns:
        小写 token 列表，空输入返回 []
    """
    if not text:
        return []

    # 用非 word 字符和 CJK 边界切分
    raw = re.findall(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]+", text)
    lowered = [tok.lower() if tok.isascii() else tok for tok in raw]
    return [t for t in lowered if t not in STOP_WORDS]


# ---------------------------------------------------------------------------
# v4 决策 #19: ReDoS 对抗样本池
# ---------------------------------------------------------------------------

REDOS_PROBE_INPUTS = (
    "a" * 100,
    "M" * 50 + "6" * 50,
    "Xx" * 40,
    "6205" * 30,
    "a" + "b" * 80 + "c",
    "M6×" * 40,
    "!!!" * 50,
    "123" * 40,
    " " * 200,
    "x" * 500,
)

REDOS_TIMEOUT_SEC = 0.05  # 50ms 单正则单样本超时


def _match_with_timeout(pattern: re.Pattern, text: str, timeout_sec: float) -> bool:
    """用独立线程做 re.search，主线程 join 超时即视为 ReDoS。

    win32 上 signal.alarm 不可用，改用 threading 策略（决策 #19 适配 Windows）。

    Args:
        pattern: 已编译的正则对象
        text: 待匹配的字符串
        timeout_sec: 超时秒数

    Returns:
        True 表示正常完成，False 表示超时（疑似 ReDoS）
    """
    result = [False]

    def worker():
        try:
            result[0] = bool(pattern.search(text))
        except Exception:
            result[0] = False

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(timeout_sec)
    return not t.is_alive()  # True 表示正常完成, False 表示超时


def validate_size_patterns(patterns: dict) -> None:
    """ReDoS 防御（v4 决策 #19）。

    对每个正则做：
    1. re.compile() 语法校验
    2. 用 REDOS_PROBE_INPUTS 的对抗样本做 50ms timeout 测试
    3. 任一样本超时 → raise RuntimeError

    Args:
        patterns: size_patterns 配置

    Raises:
        re.error: 正则语法错误
        RuntimeError: 检测到疑似 ReDoS 模式
    """
    for category, field_patterns in patterns.items():
        if not isinstance(field_patterns, dict):
            continue
        for field_name, regex in field_patterns.items():
            if field_name == "exclude_patterns":
                if not isinstance(regex, list):
                    continue
                for r in regex:
                    compiled = re.compile(r)  # raise re.error on syntax issue
                    for probe in REDOS_PROBE_INPUTS:
                        if not _match_with_timeout(compiled, probe, REDOS_TIMEOUT_SEC):
                            raise RuntimeError(
                                f"ReDoS suspected: pattern {r!r} in "
                                f"{category}.exclude_patterns timed out on {probe[:30]!r}"
                            )
                continue

            compiled = re.compile(regex)
            for probe in REDOS_PROBE_INPUTS:
                if not _match_with_timeout(compiled, probe, REDOS_TIMEOUT_SEC):
                    raise RuntimeError(
                        f"ReDoS suspected: pattern {regex!r} in "
                        f"{category}.{field_name} timed out on {probe[:30]!r}"
                    )


def extract_size_from_name(name_cn: str, patterns: dict) -> Optional[dict]:
    """从 BOM name_cn 正则抽尺寸（v4 §1.3, 决策 #9）。

    返回:
      - 成功抽到任一字段: dict，如 {"size": "M6", "length": "20"}
      - 检测到范围外螺纹（UNC/Tr/G/NPT）: None
      - 什么都没抽到: None

    调用方看到 None 就走 miss（§8 错误矩阵）。

    Args:
        name_cn: BOM name_cn 字段
        patterns: size_patterns 配置段

    Returns:
        dict 或 None
    """
    if not name_cn:
        return None

    # 先查 exclude_patterns，命中任一即范围外
    for excl in patterns.get("exclude_patterns", []) or []:
        if re.search(excl, name_cn):
            return None

    result = {}
    for field_name, pat in patterns.items():
        if field_name == "exclude_patterns":
            continue
        m = re.search(pat, name_cn)
        if m:
            value = m.group(1) if m.groups() else m.group(0)
            # 公制螺纹 size 保留 M 前缀
            if field_name == "size" and not value.startswith(("M", "m")):
                value = "M" + value
            result[field_name] = value

    return result if result else None
