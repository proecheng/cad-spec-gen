"""Task 3.1：LLM fallback —— 把 jury 给的 unmapped reason 翻译成 prompt addons。

设计要点：
- 复用 `JuryProfile` 配置类型（base_url + api_key + model），HTTP 调用模式与
  jury/llm_client.py 同款 chat-completions，**但不复用 prompt template**：
  jury 是评审 prompt（vision），fallback 是翻译 prompt（pure text）。
- LlmFallbackError 不静默吞底层 LLM 异常；调用方（orchestrator）catch 后决定
  loop_status 走 no_rules_hit_no_llm 还是 retry_failed 等。
- secrets scrub **不在本模块**做：metadata.write_sidecar 在写盘前统一过
  scrub_secrets（SEC-MINOR-2）。fallback 自身只做语义切分。
"""
from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tools.jury.config import JuryProfile

_TIMEOUT_SEC = 60
_MAX_ADDONS = 3
_MAX_ADDON_CHARS = 80
#: 防御性深度：max_tokens=256 已限正常路径；纯字符上限兜异常 LLM 返巨量逗号
#: 雪崩等边角，避免 split 在 1MB+ 字符串上分配大数组（review Important #5）。
_MAX_RAW_OUTPUT_CHARS = 4096
_PROMPT_TEMPLATE = (
    "你是产品摄影术导。基于此 jury 反馈：{reason}，给出 ≤3 个英文 prompt "
    "增强词，逗号分隔，不解释。"
)


class LlmFallbackError(Exception):
    """LLM fallback 翻译失败。

    与 jury/llm_client.JuryLlmError 区分：本异常专指"reason → addons"翻译
    失败，调用方据此决定 loop_status；不与 jury 评审失败混用。
    """


def translate(
    unmapped_reason: str,
    sanitized_reason: str,
    *,
    profile: JuryProfile,
) -> list[str]:
    """把 unmapped jury reason 翻译成最多 3 个 prompt addon 字串。

    参数：
        unmapped_reason: 规则表未命中的 jury 原始 reason 文本（用于决定是否短路）
        sanitized_reason: 已脱敏的 reason 文本（实际写进 prompt template）
        profile: jury 配置（复用 jury 同一 LLM endpoint + key）

    返回：
        list[str]，每元素 ≤80 字，最多 3 条；空 / 纯空白 reason 短路返 []。

    异常：
        LlmFallbackError: HTTP / 网络异常；不静默吞。
    """
    if not unmapped_reason or not unmapped_reason.strip():
        return []

    prompt = _PROMPT_TEMPLATE.format(reason=sanitized_reason)
    try:
        content_text = _request_chat_text(profile, prompt)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise LlmFallbackError(f"LLM fallback 翻译失败: {type(exc).__name__}") from exc

    return _parse_addons(content_text)


def _request_chat_text(profile: JuryProfile, prompt: str) -> str:
    """调 chat-completions 纯文本接口（无 image），返 content_text。"""
    url = f"{profile.api_base_url}/chat/completions"
    body = json.dumps(
        {
            "model": profile.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 256,
            "temperature": 0.0,
        }
    ).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {profile.api_key}",
        "Content-Type": "application/json",
        # v2.37.1 fix：显式 UA。urllib 默认 `Python-urllib/3.x` 被很多第三方
        # 代理（micuapi.ai 等）anti-bot 直接 403 拒，导致 jury 跑不通。
        "User-Agent": "cad-spec-gen-jury",
    }
    req = Request(url, data=body, headers=headers, method="POST")
    with urlopen(req, timeout=_TIMEOUT_SEC) as resp:
        resp_body: bytes = resp.read()
    return _extract_content(resp_body)


def _extract_content(resp_body: bytes) -> str:
    """从 chat-completions JSON 抠 choices[0].message.content（解析失败返 ""）。"""
    try:
        parsed: Any = json.loads(resp_body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return ""
    if not isinstance(parsed, dict):
        return ""
    choices = parsed.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    msg = first.get("message", {})
    if not isinstance(msg, dict):
        return ""
    return str(msg.get("content", "") or "")


def _parse_addons(content_text: str) -> list[str]:
    """逗号拆分 + strip + 去空 + cap 长度 + cap 个数。

    先把整体字符串截到 `_MAX_RAW_OUTPUT_CHARS` 再 split，防御异常 LLM 返巨量
    分隔符导致内存级浪费。
    """
    text = content_text[:_MAX_RAW_OUTPUT_CHARS]
    parts = [p.strip() for p in text.split(",")]
    parts = [p for p in parts if p]
    parts = [p[:_MAX_ADDON_CHARS] for p in parts]
    return parts[:_MAX_ADDONS]
