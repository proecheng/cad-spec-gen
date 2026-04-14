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
from functools import lru_cache
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


DEFAULT_CN_SYNONYMS_PATH = Path(__file__).parent.parent.parent / "config" / "toolbox_cn_synonyms.yaml"


def _load_cn_synonyms_from_path(path: Path) -> dict[str, list[str]]:
    """读取 YAML 并打平分组结构为 {cn_key: [en_tokens]}。"""
    import yaml

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    flat: dict[str, list[str]] = {}
    for group_name, entries in raw.items():
        if not isinstance(entries, dict):
            continue
        for cn_key, en_tokens in entries.items():
            if not isinstance(en_tokens, list):
                continue
            flat[cn_key] = [str(t).lower() for t in en_tokens]
    return flat


@lru_cache(maxsize=1)
def _load_cn_synonyms_cached() -> dict[str, list[str]]:
    return _load_cn_synonyms_from_path(DEFAULT_CN_SYNONYMS_PATH)


def load_cn_synonyms(path: Optional[Path] = None) -> dict[str, list[str]]:
    """加载中英文同义词表。

    无参数调用走 lru_cache（生产路径）；带 path 参数绕开缓存（测试隔离用）。

    Returns:
        {cn_morpheme: [en_token, ...]} 扁平 dict
    """
    if path is None:
        return _load_cn_synonyms_cached()
    return _load_cn_synonyms_from_path(path)


def expand_cn_synonyms(
    tokens_weighted: list[tuple[str, float]],
    synonyms: dict[str, list[str]],
) -> list[tuple[str, float]]:
    """对每个 CJK token 做子串同义词匹配，注入对等英文 token（同权重）。

    规则：
    - 只对含 CJK 字符的 token 做子串扫描（ASCII token 原样透传）
    - 同一英文 token 被多源注入时取最大权重（与 build_query_tokens_weighted 一致）
    - 原 CJK token 保留（不删除），扩展只做添加

    Args:
        tokens_weighted: tokenize + 加权后的 [(token, weight), ...]
        synonyms: load_cn_synonyms 返回的 {cn_morpheme: [en_tokens]}

    Returns:
        扩展后的 [(token, weight), ...]
    """
    if not tokens_weighted or not synonyms:
        return list(tokens_weighted)

    collected: dict[str, float] = {}
    for tok, w in tokens_weighted:
        if tok not in collected or collected[tok] < w:
            collected[tok] = w

    for tok, w in tokens_weighted:
        # 仅对 CJK token 做子串扫描（包含 \u4e00-\u9fff 字符即判定）
        has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in tok)
        if not has_cjk:
            continue
        for cn_key, en_tokens in synonyms.items():
            if cn_key in tok:
                for en in en_tokens:
                    if en not in collected or collected[en] < w:
                        collected[en] = w

    return list(collected.items())


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
        patterns: size_patterns 配置（必须是 dict；非 dict 立即 raise RuntimeError）

    Raises:
        re.error: 正则语法错误
        RuntimeError: patterns 非 dict / 检测到疑似 ReDoS 模式（子进程超时）
    """
    if not isinstance(patterns, dict):
        raise RuntimeError(
            f"size_patterns 必须是 dict，实际类型 {type(patterns).__name__}; "
            f"检查 yaml 配置 solidworks_toolbox.size_patterns 段"
        )

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


def _make_index_envelope(
    standards: dict[str, dict[str, list[SwToolboxPart]]],
    fingerprint: str,
) -> dict:
    """构建索引 dict 信封（Minor #5 去重辅助函数）。

    统一 build_toolbox_index 与 _empty_index 的返回结构，避免两处重复定义。

    Args:
        standards: 已扫描的标准分类表（可为空 dict）
        fingerprint: Toolbox 指纹（SHA1 hex 或 "unavailable"）

    Returns:
        dict:
            schema_version: int
            scan_time: ISO 时间戳（UTC）
            toolbox_fingerprint: str
            standards: dict
    """
    from datetime import datetime, timezone

    return {
        "schema_version": SCHEMA_VERSION,
        "scan_time": datetime.now(timezone.utc).isoformat(),
        "toolbox_fingerprint": fingerprint,
        "standards": standards,
    }


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
    toolbox_dir = Path(toolbox_dir)
    standards: dict[str, dict[str, list[SwToolboxPart]]] = {}

    if not toolbox_dir.exists():
        log.warning("Toolbox dir does not exist: %s", toolbox_dir)
        return _empty_index()

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

    return _make_index_envelope(standards, _compute_toolbox_fingerprint(toolbox_dir))


def _empty_index() -> dict:
    """返回空索引 dict（目录不存在时使用）。

    Minor #4: 不再接受 toolbox_dir 参数（该参数未被使用），
    改为直接调用 _make_index_envelope({}, "unavailable")。

    Returns:
        包含空 standards 的索引 dict
    """
    return _make_index_envelope({}, "unavailable")


def load_toolbox_index(cache_path: Path, toolbox_dir: Path) -> dict:
    """读缓存；自动重建条件（v4 决策 #21）：

    1. 缓存文件不存在
    2. cache['schema_version'] != SCHEMA_VERSION
    3. cache['toolbox_fingerprint'] != _compute_toolbox_fingerprint(toolbox_dir)

    重建时追加事件到 ~/.cad-spec-gen/sw_toolbox_index_history.log（SRE #7）。

    Args:
        cache_path: 索引 JSON 文件路径
        toolbox_dir: Toolbox 根目录（用于重新扫描及指纹比对）

    Returns:
        索引 dict（含 SwToolboxPart 对象）
    """
    cache_path = Path(cache_path)
    toolbox_dir = Path(toolbox_dir)

    cached = None
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            log.warning("toolbox index 缓存损坏，将重建: %s", e)
            cached = None

    rebuild_reason = None
    if cached is None:
        rebuild_reason = "missing or corrupt"
    elif cached.get("schema_version") != SCHEMA_VERSION:
        rebuild_reason = (
            f"schema_version bump {cached.get('schema_version')} -> {SCHEMA_VERSION}"
        )
    else:
        current_fp = _compute_toolbox_fingerprint(toolbox_dir)
        cached_fp = cached.get("toolbox_fingerprint", "")
        if current_fp != cached_fp and current_fp != "unavailable":
            rebuild_reason = f"fingerprint mismatch {cached_fp[:8]}->{current_fp[:8]}"

    if rebuild_reason is None:
        # 缓存有效：反序列化 SwToolboxPart 对象
        # I-1: 信任边界上移——cache hit 路径的 sldprt_path 来自磁盘 JSON，
        # 可能被篡改；在返回前统一过滤非 toolbox_dir 子路径的 part，
        # 让下游 resolve/_find_sldprt/sw-warmup 可以直接信任 index。
        return _filter_tampered_paths(_rehydrate_index(cached), toolbox_dir)

    # 重建
    log.info("toolbox 索引重建: %s", rebuild_reason)
    _append_history_log(rebuild_reason)

    new_idx = build_toolbox_index(toolbox_dir)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(_dehydrate_index(new_idx), encoding="utf-8")
    except OSError as e:
        log.warning("toolbox 索引缓存写入失败（非致命）: %s", e)
    return new_idx


def _dehydrate_index(idx: dict) -> str:
    """把索引中的 SwToolboxPart 转 dict 以便 JSON 序列化。"""
    out = dict(idx)
    out["standards"] = {
        std: {sub: [asdict(p) for p in parts] for sub, parts in sub_dict.items()}
        for std, sub_dict in idx["standards"].items()
    }
    return json.dumps(out, ensure_ascii=False, indent=2)


def _filter_tampered_paths(idx: dict, toolbox_dir: Path) -> dict:
    """I-1 信任边界上移: 过滤 sldprt_path 非 toolbox_dir 子路径的 part。

    仅用于 cache hit 路径——build_toolbox_index 的扫描结果天然都在 toolbox_dir 下，
    但反序列化自磁盘 JSON 的路径可能被攻击者篡改指向任意位置。
    被过滤的 part 会由 _validate_sldprt_path 内部 log.error 记录。

    Args:
        idx: 已 rehydrate 的索引 dict
        toolbox_dir: Toolbox 根目录（信任边界）

    Returns:
        新的 dict（不修改入参），standards 下只保留合法子路径 part。
    """
    out = dict(idx)
    out["standards"] = {
        std: {
            sub: [p for p in parts if _validate_sldprt_path(p.sldprt_path, toolbox_dir)]
            for sub, parts in sub_dict.items()
        }
        for std, sub_dict in idx.get("standards", {}).items()
    }
    return out


def _rehydrate_index(cached: dict) -> dict:
    """把 JSON dict 转回含 SwToolboxPart 的索引 dict。"""
    out = dict(cached)
    out["standards"] = {
        std: {
            sub: [SwToolboxPart(**p) for p in parts] for sub, parts in sub_dict.items()
        }
        for std, sub_dict in cached.get("standards", {}).items()
    }
    return out


def _append_history_log(reason: str) -> None:
    """追加索引 rebuild 事件到 history log（SRE #7）。

    日志路径: ~/.cad-spec-gen/sw_toolbox_index_history.log
    写入失败不阻断 load_toolbox_index 的正常返回。
    """
    from datetime import datetime, timezone

    log_path = Path.home() / ".cad-spec-gen" / "sw_toolbox_index_history.log"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            ts = datetime.now(timezone.utc).isoformat()
            f.write(f"{ts}: rebuild — {reason}\n")
    except OSError:
        pass  # 日志失败不阻断


def _validate_sldprt_path(sldprt_path: str, toolbox_dir: Path) -> bool:
    """路径遍历防御（v4 决策 #20）。

    sldprt_path.resolve() 必须是 toolbox_dir.resolve() 的真子路径。
    任何 resolve 异常 → False。

    Args:
        sldprt_path: 待验证的 .sldprt 文件路径字符串
        toolbox_dir: Toolbox 根目录（信任边界）

    Returns:
        True 表示 sldprt_path 是 toolbox_dir 的合法子路径，False 表示疑似路径遍历攻击
    """
    try:
        sld = Path(sldprt_path).resolve()
        root = Path(toolbox_dir).resolve()
        sld.relative_to(root)  # 若非子路径则抛 ValueError
        return True
    except (ValueError, OSError, RuntimeError):
        log.error(
            "索引篡改疑似: sldprt_path 非 toolbox_dir 子路径: %s vs %s",
            sldprt_path,
            toolbox_dir,
        )
        return False


def build_query_tokens_weighted(
    query,
    size_dict: Optional[dict],
    weights: dict,
) -> list[tuple[str, float]]:
    """构造加权 query tokens（v4 决策 #12）。

    weights 示例: {"part_no": 2.0, "name_cn": 1.0, "material": 0.5, "size": 1.5}

    同一 token 出现在多个字段时取最大权重（不累加），确保 dedup 后 dict() 不会覆盖高权重。

    Args:
        query: 含 part_no / name_cn / material 属性的对象（缺失属性回退空字符串）
        size_dict: 尺寸 dict，如 {"size": "M6", "length": "20"}，None 时跳过
        weights: 字段权重配置

    Returns:
        [(token, weight), ...] —— 同一 token 出现在多个字段时取最大权重
    """
    collected: dict[str, float] = {}

    def add(tokens: list[str], w: float) -> None:
        for t in tokens:
            if t not in collected or collected[t] < w:
                collected[t] = w

    add(tokenize(getattr(query, "part_no", "")), weights.get("part_no", 1.0))
    add(tokenize(getattr(query, "name_cn", "")), weights.get("name_cn", 1.0))
    add(tokenize(getattr(query, "material", "")), weights.get("material", 0.5))

    if size_dict:
        for value in size_dict.values():
            add(tokenize(str(value)), weights.get("size", 1.5))

    return [(t, w) for t, w in collected.items()]


def match_toolbox_part(
    index: dict,
    query_tokens_weighted: list[tuple[str, float]],
    standards: list[str],
    subcategories: list[str],
    min_score: float = 0.30,
) -> Optional[tuple[SwToolboxPart, float]]:
    """加权 token overlap 打分（v4 决策 #3/#12/#18）。

    score = Σ(命中 token 的权重) / Σ(query token 总权重)

    Args:
        index: build/load_toolbox_index 返回的 dict
        query_tokens_weighted: [(token, weight), ...]
        standards: 候选标准白名单（如 ["GB"]）
        subcategories: 候选子分类白名单
        min_score: 最低命中分数（低于此值返回 None）

    Returns:
        (part, score) 或 None（低于 min_score）
    """
    if not query_tokens_weighted:
        return None

    total_weight = sum(w for _, w in query_tokens_weighted)
    if total_weight == 0:
        return None

    query_map = dict(query_tokens_weighted)

    best: Optional[tuple[SwToolboxPart, float]] = None
    for std_name, sub_dict in index.get("standards", {}).items():
        if std_name not in standards:
            continue
        for sub_name, parts in sub_dict.items():
            if sub_name not in subcategories:
                continue
            for part in parts:
                part_token_set = set(part.tokens)
                hit_weight = sum(w for t, w in query_map.items() if t in part_token_set)
                score = hit_weight / total_weight
                if best is None or score > best[1]:
                    best = (part, score)

    if best and best[1] >= min_score:
        return best
    return None


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
