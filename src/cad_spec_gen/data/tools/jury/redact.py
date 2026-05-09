"""集中 4 路径脱敏 — 所有 jury 出口（stderr / log / report / --debug-output）唯一通过此模块。

设计约束：
- 不做语义剥离（保留可公开 trace ID 如 vendor_request_id / x-request-id）。
- redact_url：剥 query/fragment，保留 scheme://host/path。
- redact_headers：大小写不敏感移除 Authorization / Cookie / x-api-key 等敏感 header。
- redact_body：超过 max_chars 截断并加 '...truncated' 标记，不做 body 内语义剥离。
- redact_traceback_str：从 traceback 字符串去 frame locals 含 api_key= / Bearer / Cookie 的整行。
"""
from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse


# 大小写不敏感（lower-case 比对）的敏感 header 名集合
_REDACT_HEADER_NAMES: frozenset[str] = frozenset(
    {"authorization", "cookie", "set-cookie", "x-api-key", "api-key"}
)

# traceback 字符串行级匹配；MULTILINE 让 ^$ 锚到每行
_REDACT_TRACEBACK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^.*api[_-]?key.*=.*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^.*Authorization.*Bearer.*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^.*Cookie.*=.*$", re.IGNORECASE | re.MULTILINE),
)


def redact_url(s: str) -> str:
    """剥 query/fragment，保留 scheme://host/path。

    空字符串透传。
    """
    if not s:
        return s
    parsed = urlparse(s)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def redact_headers(d: dict[str, str]) -> dict[str, str]:
    """大小写不敏感移除敏感 header；其它 header 原样保留（含公开 trace ID）。"""
    return {k: v for k, v in d.items() if k.lower() not in _REDACT_HEADER_NAMES}


def redact_body(s: str, max_chars: int = 128) -> str:
    """截断到 max_chars + '...truncated' 标记。

    不做 body 内语义剥离 —— vendor_request_id 等公开 trace 应保留。
    """
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "...truncated"


def redact_traceback_str(s: str) -> str:
    """从 traceback 字符串去 frame locals 中含 api_key= / Authorization Bearer / Cookie 的整行。

    匹配整行替换为 '[REDACTED]'，避免 secret 通过 traceback locals 漏出。
    """
    for pattern in _REDACT_TRACEBACK_PATTERNS:
        s = pattern.sub("[REDACTED]", s)
    return s
