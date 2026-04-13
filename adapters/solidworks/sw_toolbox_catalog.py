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
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
"""每次索引结构变更必须 bump；旧缓存自动重建。"""

CACHE_ROOT_ENV = "CAD_SPEC_GEN_SW_TOOLBOX_CACHE"
INDEX_PATH_ENV = "CAD_SPEC_GEN_SW_TOOLBOX_INDEX"


def get_toolbox_cache_root(config: dict) -> Path:
    """cache 路径解析（v4 决策 #16/#17）。

    优先级: config['cache'] > env CAD_SPEC_GEN_SW_TOOLBOX_CACHE > 默认。

    默认: Path.home() / '.cad-spec-gen' / 'step_cache' / 'sw_toolbox'
    ⚠️ 必须 Path.home()，不用 os.path.expanduser（后者不被 conftest monkeypatch 覆盖）。
    """
    yaml_cache = config.get("cache") if config else None
    if yaml_cache:
        return Path(yaml_cache)

    env_cache = os.environ.get(CACHE_ROOT_ENV)
    if env_cache:
        return Path(env_cache)

    return Path.home() / ".cad-spec-gen" / "step_cache" / "sw_toolbox"


def get_toolbox_index_path(config: dict) -> Path:
    """索引路径解析（v4 决策 #16/#17）。

    优先级: env CAD_SPEC_GEN_SW_TOOLBOX_INDEX > 默认。

    默认: Path.home() / '.cad-spec-gen' / 'sw_toolbox_index.json'
    """
    env_idx = os.environ.get(INDEX_PATH_ENV)
    if env_idx:
        return Path(env_idx)

    return Path.home() / ".cad-spec-gen" / "sw_toolbox_index.json"


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

STOP_WORDS: frozenset[str] = frozenset(
    {
        "and",
        "for",
        "with",
        "the",
        "of",
        "type",
        "a",
        "an",
        "in",
        "on",
        "to",
        "by",
    }
)


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

REDOS_PROBE_INPUTS: tuple[str, ...] = (
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
    # 非匹配后缀探针：触发 (a+)+$ 类灾难性回溯
    # 原理：全 'a' 序列 + 非字母后缀 → 引擎穷举所有分组组合后整体失败
    "a" * 25 + "!",
    "a" * 20 + "\x00",
    "x" * 22 + "?",
    "M" * 20 + "#",
)

# CPython 的 re 模块是 C 扩展，持有 GIL 期间不让出控制权，
# 因此 threading.join(timeout) 无法中断正在运行的 re.search。
# 必须用独立子进程 + subprocess.TimeoutExpired 检测（决策 #19 适配 Windows）。
REDOS_TIMEOUT_SEC = 0.5  # 每个正则所有探针总超时（含进程启动约 50ms）


def _test_pattern_safe(regex: str) -> bool:
    """在独立子进程中对所有探针运行 re.search，超时即返回 False（疑似 ReDoS）。

    使用子进程而非线程原因：CPython re 模块为 C 扩展，持有 GIL 期间
    threading.Thread.join(timeout) 实际上会阻塞至 C 函数返回，
    无法实现真正的超时中断。子进程有独立 GIL，可被 OS 强制 kill。

    Args:
        regex: 待检测的正则字符串

    Returns:
        True: 子进程在 timeout 内正常完成（无 ReDoS）
        False: 子进程 timeout 被 OS kill（疑似 ReDoS）

    Raises:
        RuntimeError: 子进程启动失败（FileNotFoundError / PermissionError / OSError）
            或子进程以非零返回码异常退出（segfault / AV kill 等）——这是环境错误，
            不是 ReDoS，调用方应区别对待。
        re.error: 正则语法错误（compile 失败时由调用方捕获）
    """
    probes_repr = repr(list(REDOS_PROBE_INPUTS))
    code = (
        "import re\n"
        f"pat = re.compile({regex!r})\n"
        f"probes = {probes_repr}\n"
        "for p in probes:\n"
        "    pat.search(p)\n"
        "print('ok')\n"
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            timeout=REDOS_TIMEOUT_SEC,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired:
        return False  # 真正的 ReDoS —— 超时被 OS kill
    except (FileNotFoundError, PermissionError, OSError) as e:
        raise RuntimeError(f"ReDoS validator subprocess 启动失败: {e}") from e

    if proc.returncode != 0:
        # 子进程以非零码退出（segfault / re.error / AV kill 等）
        raise RuntimeError(
            f"ReDoS validator subprocess 异常退出 (rc={proc.returncode}): "
            f"stderr={proc.stderr.strip()!r}"
        )
    return "ok" in proc.stdout


def validate_size_patterns(patterns: dict) -> None:
    """ReDoS 防御（v4 决策 #19）。

    对每个正则做：
    1. re.compile() 语法校验（main 进程内，快速失败）
    2. 在独立子进程中对 REDOS_PROBE_INPUTS 全量探针运行，总超时 500ms
    3. 超时 → raise RuntimeError（调用方不得捕获后继续使用该 patterns）

    实现说明：CPython re 模块为 C 扩展，持有 GIL 期间 threading.join(timeout)
    无法中断正在运行的 C 级 re.search；必须用子进程隔离（#19 Windows 适配）。

    Args:
        patterns: size_patterns 配置

    Raises:
        re.error: 正则语法错误
        RuntimeError: 检测到疑似 ReDoS 模式（子进程超时）
    """
    for category, field_patterns in patterns.items():
        if not isinstance(field_patterns, dict):
            continue
        for field_name, regex in field_patterns.items():
            if field_name == "exclude_patterns":
                if not isinstance(regex, list):
                    continue
                for r in regex:
                    re.compile(r)  # 语法校验，raise re.error on error
                    if not _test_pattern_safe(r):
                        raise RuntimeError(
                            f"ReDoS suspected: pattern {r!r} in "
                            f"{category}.exclude_patterns timed out"
                        )
                continue

            re.compile(regex)  # 语法校验，raise re.error on error
            if not _test_pattern_safe(regex):
                raise RuntimeError(
                    f"ReDoS suspected: pattern {regex!r} in "
                    f"{category}.{field_name} timed out"
                )


def _compute_toolbox_fingerprint(toolbox_dir: Path) -> str:
    """计算 Toolbox 目录指纹（v4 决策 #21）。

    指纹 = SHA1(sorted [(relative_path, size, mtime_int) of all *.sldprt])

    扫描时若 PermissionError → retry 一次（QA #13）；仍失败返回 'unavailable'。

    Args:
        toolbox_dir: Toolbox 根目录路径

    Returns:
        SHA1 hex string (40 chars) 或 "unavailable"（目录不存在或权限错误）
    """
    toolbox_dir = Path(toolbox_dir)
    if not toolbox_dir.exists():
        return "unavailable"

    for attempt in range(2):
        try:
            items: list[tuple[str, int, int]] = []
            for path in sorted(toolbox_dir.rglob("*.sldprt")):
                try:
                    st = path.stat()
                    rel = path.relative_to(toolbox_dir).as_posix()
                    items.append((rel, st.st_size, int(st.st_mtime)))
                except (PermissionError, OSError):
                    continue
            h = hashlib.sha1()
            for rel, size, mtime in items:
                h.update(f"{rel}|{size}|{mtime}\n".encode("utf-8"))
            return h.hexdigest()
        except PermissionError:
            if attempt == 0:
                continue
            return "unavailable"

    return "unavailable"


def build_toolbox_index(toolbox_dir: Path) -> dict:
    """扫描 Toolbox 目录 → 索引 dict（v4 §5.1 + 决策 #21）。

    目录结构假设：
        toolbox_dir/
            <standard>/
                <subcategory>/
                    *.sldprt
                    (其他非 sldprt 文件被过滤)

    Args:
        toolbox_dir: Toolbox 根目录（sw_detect.toolbox_dir）

    Returns:
        dict:
            schema_version: int
            scan_time: ISO 时间戳
            toolbox_fingerprint: SHA1 hex
            standards: {standard: {subcategory: [SwToolboxPart, ...]}}
    """
    from datetime import datetime, timezone

    toolbox_dir = Path(toolbox_dir)
    standards: dict[str, dict[str, list[SwToolboxPart]]] = {}

    if not toolbox_dir.exists():
        log.warning("Toolbox dir does not exist: %s", toolbox_dir)
        return _empty_index(toolbox_dir)

    for std_dir in toolbox_dir.iterdir():
        if not std_dir.is_dir():
            continue
        std_name = std_dir.name
        std_entry: dict[str, list[SwToolboxPart]] = {}

        for sub_dir in std_dir.iterdir():
            if not sub_dir.is_dir():
                continue
            sub_name = sub_dir.name
            parts: list[SwToolboxPart] = []
            for sldprt in sub_dir.rglob("*.sldprt"):
                if not sldprt.is_file():
                    continue
                tokens = tokenize(sldprt.stem) + tokenize(sub_name)
                parts.append(
                    SwToolboxPart(
                        standard=std_name,
                        subcategory=sub_name,
                        sldprt_path=str(sldprt.resolve()),
                        filename=sldprt.name,
                        tokens=list(dict.fromkeys(tokens)),  # 去重保序
                    )
                )
            if parts:
                std_entry[sub_name] = parts

        if std_entry:
            standards[std_name] = std_entry

    return {
        "schema_version": SCHEMA_VERSION,
        "scan_time": datetime.now(timezone.utc).isoformat(),
        "toolbox_fingerprint": _compute_toolbox_fingerprint(toolbox_dir),
        "standards": standards,
    }


def _empty_index(toolbox_dir: Path) -> dict:
    """返回空索引 dict（目录不存在时使用）。

    Args:
        toolbox_dir: Toolbox 根目录路径（仅用于日志，不写入结果）

    Returns:
        包含空 standards 的索引 dict
    """
    from datetime import datetime, timezone

    return {
        "schema_version": SCHEMA_VERSION,
        "scan_time": datetime.now(timezone.utc).isoformat(),
        "toolbox_fingerprint": "unavailable",
        "standards": {},
    }


def extract_size_from_name(name_cn: str, patterns: dict) -> Optional[dict[str, str]]:
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
        if not isinstance(pat, str):
            continue  # 跳过 exclude_patterns (list) 或任何非 str 配置键
        m = re.search(pat, name_cn)
        if m:
            value = m.group(1) if m.groups() else m.group(0)
            # 公制螺纹 size 保留 M 前缀
            if field_name == "size" and not value.startswith(("M", "m")):
                value = "M" + value
            result[field_name] = value

    return result if result else None
