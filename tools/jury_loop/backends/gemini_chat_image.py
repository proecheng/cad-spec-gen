"""gemini_chat_image adapter — chat-completions 传图 + Gemini native fallback。

base_url 路径含 ``:generateContent`` 时走 Gemini native generateContent；
否则按 OpenAI chat-completions 兼容（Gemini 的 /v1beta/openai/chat/completions
形如 OpenAI 的 messages + image_url data URL）。

异常映射：HTTP 401/403 → BackendAuthError；429 → BackendRateLimitError；
402 / "quota" / "billing" → BackendQuotaExceededError；其他 → BackendCallError。
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .protocol import (
    BackendAuthError,
    BackendCallError,
    BackendQuotaExceededError,
    BackendRateLimitError,
    BackendRequest,
    BackendResponse,
)

_KNOWN_PARAMS: dict[str, tuple[float | None, float | None]] = {
    "temperature": (0.0, 2.0),
    "top_p": (0.0, 1.0),
    "top_k": (1, 100),
}

# 内置定价表（USD / call）。未匹配走 _DEFAULT_PRICE。
# 注：更具体的 key 必须放前面（"gemini-2.5-flash-image" 含 "gemini-2.5-flash" 子串）；
# _lookup_price 按定义顺序匹配避免短前缀误命中。
_PRICING_USD: dict[str, float] = {
    "gemini-3-pro": 0.04,
    "gemini-2.5-flash-image": 0.04,
    "gemini-2.5-flash": 0.01,
}
_DEFAULT_PRICE = 0.05


def _lookup_price(model_name: str) -> float:
    """按 model 名子串匹配定价（按 _PRICING_USD 定义顺序，更具体在前）；未匹配返 _DEFAULT_PRICE。"""
    name = model_name.lower()
    for key, price in _PRICING_USD.items():
        if key in name:
            return price
    return _DEFAULT_PRICE


def _is_gemini_native(base_url: str) -> bool:
    """base_url 路径含 :generateContent 即认定 Gemini native generateContent。"""
    return ":generateContent" in base_url


def _build_chat_completions_body(
    request: BackendRequest, image_b64: str
) -> bytes:
    """OpenAI chat-completions 风格 body：messages 含 text + image_url(data:URL)。"""
    params = request.params
    body: dict[str, Any] = {
        "model": request.model_name,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": request.prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_b64}"
                        },
                    },
                ],
            }
        ],
    }
    for k in ("temperature", "top_p", "top_k"):
        if k in params:
            body[k] = params[k]
    return json.dumps(body).encode("utf-8")


def _build_generate_content_body(
    request: BackendRequest, image_b64: str
) -> bytes:
    """Gemini native generateContent body：contents.parts 含 inline_data + text。"""
    params = request.params
    gen_cfg: dict[str, Any] = {}
    for src, dst in (("temperature", "temperature"), ("top_p", "topP"), ("top_k", "topK")):
        if src in params:
            gen_cfg[dst] = params[src]
    body: dict[str, Any] = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": image_b64,
                        }
                    },
                    {"text": request.prompt},
                ]
            }
        ],
    }
    if gen_cfg:
        body["generationConfig"] = gen_cfg
    return json.dumps(body).encode("utf-8")


def _extract_image_b64(parsed: dict[str, Any]) -> str:
    """从响应抠 base64 图像数据。优先 OpenAI chat-completions，回退 Gemini native。

    Raises BackendCallError 当两个路径都无图像时。
    """
    # OpenAI chat-completions: choices[0].message.images[0].b64_json (or .image_url.url data URL)
    choices = parsed.get("choices") or []
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        msg = choices[0].get("message") or {}
        images = msg.get("images") or []
        if isinstance(images, list) and images and isinstance(images[0], dict):
            b64 = images[0].get("b64_json")
            if isinstance(b64, str) and b64:
                return b64
            url = (images[0].get("image_url") or {}).get("url") or ""
            if isinstance(url, str) and url.startswith("data:image/"):
                return url.split(",", 1)[-1]

    # Gemini native: candidates[0].content.parts[i].inline_data.data
    candidates = parsed.get("candidates") or []
    if isinstance(candidates, list) and candidates and isinstance(candidates[0], dict):
        parts = (candidates[0].get("content") or {}).get("parts") or []
        if isinstance(parts, list):
            for part in parts:
                if not isinstance(part, dict):
                    continue
                inline = part.get("inline_data") or part.get("inlineData") or {}
                if isinstance(inline, dict):
                    data = inline.get("data")
                    if isinstance(data, str) and data:
                        return data

    raise BackendCallError(
        "response 无图像数据（已尝试 choices[0].message.images / candidates[0].content.parts）"
    )


def _classify_http_error(status: int, body_text: str) -> Exception:
    """HTTP 状态码 + body 关键字 → 4 类 BackendError。

    分类顺序（与 openai_images_edit 一致）：
    1. 401/403 → Auth；2. 402 → Quota；3. body 含 quota 关键字 → Quota（优先于 429）；
    4. 429（无关键字）→ RateLimit；5. 其他 → CallError 兜底。
    """
    body_lower = body_text.lower()
    if status in (401, 403):
        return BackendAuthError(f"HTTP {status}: 认证失败（API key 错误 / 无权限）")
    if status == 402:
        return BackendQuotaExceededError(f"HTTP 402: 余额不足（{body_text[:200]}）")
    if "quota" in body_lower or "billing" in body_lower or "insufficient" in body_lower:
        return BackendQuotaExceededError(
            f"HTTP {status}: quota/billing 关键字命中（{body_text[:200]}）"
        )
    if status == 429:
        return BackendRateLimitError(f"HTTP 429: rate limited（{body_text[:200]}）")
    return BackendCallError(f"HTTP {status}: {body_text[:200]}")


class GeminiChatImageAdapter:
    """gemini_chat_image — 通用 OpenAI chat-completions 兼容 + Gemini native generateContent。"""

    @property
    def kind(self) -> str:
        return "gemini_chat_image"

    @property
    def known_params(self) -> dict[str, tuple[float | None, float | None]]:
        return dict(_KNOWN_PARAMS)

    def supports_controlnet(self) -> bool:
        return False

    def estimate_cost_usd(self, request: BackendRequest) -> float:
        return _lookup_price(request.model_name)

    def call(
        self, request: BackendRequest, timeout: float
    ) -> BackendResponse:
        image_bytes = request.input_image_path.read_bytes()
        image_b64 = base64.b64encode(image_bytes).decode("ascii")

        is_native = _is_gemini_native(request.base_url)
        if is_native:
            body = _build_generate_content_body(request, image_b64)
            headers = {
                "x-goog-api-key": request.api_key,
                "Content-Type": "application/json",
            }
        else:
            body = _build_chat_completions_body(request, image_b64)
            headers = {
                "Authorization": f"Bearer {request.api_key}",
                "Content-Type": "application/json",
            }

        req = Request(request.base_url, data=body, headers=headers, method="POST")
        try:
            with urlopen(req, timeout=timeout) as resp:
                resp_body: bytes = resp.read()
                resp_status = int(resp.status)
        except HTTPError as e:
            err_body = ""
            try:
                err_body = (e.read() or b"").decode("utf-8", errors="replace")
            except Exception:
                err_body = ""
            raise _classify_http_error(e.code, err_body) from None
        except (URLError, TimeoutError) as e:
            raise BackendCallError(f"网络/超时错误：{type(e).__name__}") from None

        try:
            parsed = json.loads(resp_body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise BackendCallError(f"响应解析失败：{e}") from None

        out_b64 = _extract_image_b64(parsed)
        try:
            out_bytes = base64.b64decode(out_b64, validate=True)
        except (ValueError, base64.binascii.Error) as e:  # type: ignore[attr-defined]
            raise BackendCallError(f"base64 解码失败：{e}") from None

        out_path = (
            request.input_image_path.parent
            / f"{request.input_image_path.stem}_retry{request.input_image_path.suffix}"
        )
        out_path.write_bytes(out_bytes)

        # raw_request_summary：不含 api_key（已 scrub），供 sidecar.backend_payload。
        raw_request_summary: dict[str, Any] = {
            "kind": "gemini_chat_image",
            "endpoint": request.base_url,
            "model": request.model_name,
            "params": dict(request.params),
            "http_status": resp_status,
            "request_format": "generateContent" if is_native else "chat_completions",
        }

        return BackendResponse(
            output_image_path=out_path,
            actual_cost_usd=None,
            raw_request_summary=raw_request_summary,
        )
