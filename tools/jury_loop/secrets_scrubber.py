"""SEC-MINOR-2 净化器：去除 errors[] 与 backend_payload 里的 API key 与 token。"""
from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"

_ENV_KEY_PATTERNS = [
    re.compile(r"(?i)(FAL_KEY|FAL_API_KEY)=([^\s,;\"']+)"),
    re.compile(r"(?i)(OPENAI_API_KEY|OPENAI_KEY)=([^\s,;\"']+)"),
    re.compile(r"(?i)(GEMINI_API_KEY|GOOGLE_API_KEY)=([^\s,;\"']+)"),
    re.compile(r"(?i)(ANTHROPIC_API_KEY|CLAUDE_API_KEY)=([^\s,;\"']+)"),
]
_BEARER_PATTERN = re.compile(r"(?i)Bearer\s+[A-Za-z0-9\-\._~+/=]+")
_AUTH_HEADER_PATTERN = re.compile(r'"Authorization"\s*:\s*"[^"]+"')

_SECRET_DICT_KEYS = {
    "api_key", "apikey", "fal_key", "fal_api_key",
    "openai_api_key", "gemini_api_key", "anthropic_api_key",
    "authorization", "bearer", "token",
}


def scrub_secrets(value: Any, max_len: int | None = None) -> Any:
    """递归净化 value 中的已知 secret 模式。

    支持 str / dict / list / 其他原样返回。max_len 仅对 str 生效。
    """
    if isinstance(value, str):
        return _scrub_str(value, max_len=max_len)
    if isinstance(value, dict):
        return {k: (REDACTED if k.lower() in _SECRET_DICT_KEYS else scrub_secrets(v, max_len=max_len))
                for k, v in value.items()}
    if isinstance(value, list):
        return [scrub_secrets(v, max_len=max_len) for v in value]
    return value


def _scrub_str(text: str, max_len: int | None) -> str:
    out = text
    for pat in _ENV_KEY_PATTERNS:
        out = pat.sub(lambda m: f"{m.group(1)}={REDACTED}", out)
    out = _BEARER_PATTERN.sub(f"Bearer {REDACTED}", out)
    out = _AUTH_HEADER_PATTERN.sub(f'"Authorization": "{REDACTED}"', out)
    if max_len is not None and len(out) > max_len:
        out = out[:max_len]
    return out
