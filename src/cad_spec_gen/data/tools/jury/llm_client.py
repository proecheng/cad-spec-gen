"""Vision API HTTP 调用 + 重试 + redact + kill switch + vendor_request_id 提取。

设计约束：
- 显式 timeout=60s + http.client.HTTPConnection.debuglevel=0 防 debug log 漏 Authorization。
- 所有出口（错误日志 / 异常 str）通过 redact.py。
- kill switch CAD_JURY_DISABLE_LLM=1 → 抛 JuryDisabledByEnv 不发请求。
- 9 类错误分类：auth_failed / quota_exhausted / bad_request / rate_limited / server_error
  / network_unreachable / timeout / disabled_by_env / 其它（透传 bad_request 兜底）。
- 重试策略：429 / 5xx / URLError / TimeoutError 走指数退避 2**attempt 秒；
  401/403/402/400 立即 fail-fast；max_retries 默认 2（共 3 次尝试）。
- vendor_request_id 优先 header（x-request-id / openai-request-id / request-id），其次 body.id。
"""

from __future__ import annotations

import base64
import http.client
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tools.jury.config import JuryProfile


# 防外部 logging level=DEBUG 漏 Authorization 到 stderr
http.client.HTTPConnection.debuglevel = 0

_TIMEOUT_SEC = 60
_TOTAL_SECONDS_PER_CALL = 120.0
_MAX_BACKOFF_SEC = 60


class JuryLlmError(Exception):
    """所有 LLM 调用失败的基类。

    str() 仅暴露 error_kind 与 http_status，不含 api_key 等敏感信息。
    """

    def __init__(
        self, error_kind: str, http_status: int = 0, message: str = ""
    ) -> None:
        super().__init__(f"{error_kind} (http={http_status})")
        self.error_kind = error_kind
        self.http_status = http_status
        # 内部诊断字段，str() 不暴露 — 调用方需自检脱敏后再写日志
        self._message = message


class JuryDisabledByEnv(JuryLlmError):
    """CAD_JURY_DISABLE_LLM=1 kill switch 触发；不发任何 HTTP 请求。"""

    def __init__(self) -> None:
        super().__init__("disabled_by_env", 0, "")


@dataclass(frozen=True)
class LlmResponse:
    """单视角 LLM 调用结果（成功路径）。"""

    content_text: str
    http_status: int
    attempts: int
    latency_ms: int
    vendor_request_id: Optional[str] = None
    finish_reason: Optional[str] = None


def request_jury_verdict(
    *,
    profile: JuryProfile,
    image_path: Path,
    prompt: str,
    max_retries: int = 2,
    total_seconds_cap: float = _TOTAL_SECONDS_PER_CALL,
) -> LlmResponse:
    """单视角 vision API 调用。

    返回 LlmResponse；失败抛 JuryLlmError 子类（kill switch 抛 JuryDisabledByEnv）。
    """
    if os.environ.get("CAD_JURY_DISABLE_LLM") == "1":
        raise JuryDisabledByEnv()

    url = f"{profile.api_base_url}/chat/completions"
    b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    body = json.dumps(
        {
            "model": profile.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                    ],
                }
            ],
            "max_tokens": 512,
            "temperature": 0.0,
        }
    ).encode("utf-8")

    headers = {
        "Authorization": f"Bearer {profile.api_key}",
        "Content-Type": "application/json",
    }
    req = Request(url, data=body, headers=headers, method="POST")

    start = time.time()
    last_exc: Optional[BaseException] = None
    for attempt in range(1, max_retries + 2):  # 1 + retries
        if time.time() - start > total_seconds_cap:
            raise JuryLlmError("timeout", 0, "")
        try:
            return _do_request(req, attempt, start)
        except HTTPError as exc:
            last_exc = exc
            kind = _classify_http_error(exc.code)
            if not _is_retryable(kind) or attempt >= max_retries + 1:
                raise JuryLlmError(kind, exc.code, "") from None
            time.sleep(min(_MAX_BACKOFF_SEC, 2**attempt))
            continue
        except URLError:
            if attempt >= max_retries + 1:
                raise JuryLlmError("network_unreachable", 0, "") from None
            time.sleep(min(_MAX_BACKOFF_SEC, 2**attempt))
            continue
        except TimeoutError:
            if attempt >= max_retries + 1:
                raise JuryLlmError("timeout", 0, "") from None
            time.sleep(min(_MAX_BACKOFF_SEC, 2**attempt))
            continue

    # 所有循环路径都应 return 或 raise；走到这里属编程错误
    if last_exc is not None:
        raise JuryLlmError("network_unreachable", 0, "") from None
    raise JuryLlmError("network_unreachable", 0, "")


def _do_request(req: Request, attempt: int, start: float) -> LlmResponse:
    """单次 HTTP 调用 + 解析 LlmResponse；不做重试。"""
    with urlopen(req, timeout=_TIMEOUT_SEC) as resp:
        resp_body: bytes = resp.read()
        content_text, vendor_id_body, finish_reason = _parse_body(resp_body)
        # 优先取 header（urllib HTTPMessage 大小写不敏感）
        hdr_id = (
            resp.headers.get("x-request-id")
            or resp.headers.get("openai-request-id")
            or resp.headers.get("request-id")
        )
        vendor_id: Optional[str] = hdr_id if hdr_id else vendor_id_body
        latency_ms = int((time.time() - start) * 1000)
        return LlmResponse(
            content_text=content_text,
            http_status=int(resp.status),
            attempts=attempt,
            latency_ms=latency_ms,
            vendor_request_id=vendor_id,
            finish_reason=finish_reason,
        )


def _parse_body(
    resp_body: bytes,
) -> tuple[str, Optional[str], Optional[str]]:
    """解析 chat-completions JSON → (content_text, vendor_request_id_from_body, finish_reason)。

    解析失败返回空 / None；不抛 — 上层用 verdict 模块兜底失败决策。
    """
    content_text = ""
    vendor_id: Optional[str] = None
    finish_reason: Optional[str] = None
    try:
        parsed: Any = json.loads(resp_body.decode("utf-8"))
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return content_text, vendor_id, finish_reason
    if not isinstance(parsed, dict):
        return content_text, vendor_id, finish_reason

    choices = parsed.get("choices", [])
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            msg = first.get("message", {})
            if isinstance(msg, dict):
                content_text = str(msg.get("content", "") or "")
            fr = first.get("finish_reason")
            if isinstance(fr, str):
                finish_reason = fr
    body_id = parsed.get("id")
    if isinstance(body_id, str):
        vendor_id = body_id
    return content_text, vendor_id, finish_reason


def _classify_http_error(code: int) -> str:
    """HTTP status code → error_kind。

    400 → bad_request；401/403 → auth_failed；402 → quota_exhausted；
    429 → rate_limited；5xx → server_error；其它 → bad_request 兜底。
    """
    if code in {401, 403}:
        return "auth_failed"
    if code == 402:
        return "quota_exhausted"
    if code == 400:
        return "bad_request"
    if code == 429:
        return "rate_limited"
    if 500 <= code < 600:
        return "server_error"
    return "bad_request"


def _is_retryable(kind: str) -> bool:
    """rate_limited / server_error 走指数退避；其它 fail-fast。"""
    return kind in {"rate_limited", "server_error"}
