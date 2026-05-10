"""openai_images_edit adapter — multipart POST /v1/images/edits。

按 spec §2.1 + plan line 1049-1066：
- multipart 含 image (file) + prompt + model + response_format
- response.data[0].b64_json 优先；data[0].url 次选（再发一次 GET 下载）
- known_params: quality/style/size 字符串字段 (None, None)；n (1, 4)
- estimate_cost_usd 按 size 维度
- 异常映射同 gemini_chat_image，但 400 + content_policy_violation 走
  BackendCallError 不是 BackendQuotaExceededError（plan TRAP）
"""
from __future__ import annotations

import base64
import json
import secrets
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
    "quality": (None, None),
    "style": (None, None),
    "n": (1, 4),
    "size": (None, None),
}

# 按 size 维度的定价（USD / image）。未匹配走 _DEFAULT_SIZE_PRICE。
_SIZE_PRICING: dict[str, float] = {
    "1024x1024": 0.04,
    "1024x1792": 0.08,
    "1792x1024": 0.08,
    "1024x1536": 0.06,
    "1536x1024": 0.06,
}
_DEFAULT_SIZE_PRICE = 0.04


def _encode_multipart(
    fields: dict[str, str],
    files: dict[str, tuple[str, bytes, str]],
) -> tuple[bytes, str]:
    """构造 multipart/form-data body。

    files: name → (filename, content_bytes, content_type)
    返回 (body, content_type_header)。
    """
    boundary = f"----jury_loop_{secrets.token_hex(16)}"
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        )
        parts.append(str(value).encode("utf-8"))
        parts.append(b"\r\n")
    for name, (filename, content, mime) in files.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(
            f'Content-Disposition: form-data; name="{name}"; '
            f'filename="{filename}"\r\n'.encode()
        )
        parts.append(f"Content-Type: {mime}\r\n\r\n".encode())
        parts.append(content)
        parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())

    body = b"".join(parts)
    return body, f"multipart/form-data; boundary={boundary}"


def _classify_http_error(status: int, body_text: str) -> Exception:
    """HTTP 状态码 + body 关键字 → 4 类 BackendError。

    分类顺序（优先级从高到低）：
    1. 401/403 → Auth
    2. 402 → Quota
    3. body 含 quota/billing/insufficient 关键字 → Quota
       （OpenAI 实际把 quota 不足返 429 + insufficient_quota，
       此优先级高于"429 视为 RateLimit"，避免误分类）
    4. 429（不含 quota 关键字）→ RateLimit
    5. content_policy_violation 不命中 quota 关键字 → 落到 5 → CallError（plan TRAP）
    6. 其他 → CallError 兜底
    """
    body_lower = body_text.lower()
    if status in (401, 403):
        return BackendAuthError(f"HTTP {status}: 认证失败")
    if status == 402:
        return BackendQuotaExceededError(f"HTTP 402: 余额不足（{body_text[:200]}）")
    if (
        "insufficient_quota" in body_lower
        or "quota_exceeded" in body_lower
        or "billing" in body_lower
    ):
        return BackendQuotaExceededError(
            f"HTTP {status}: quota/billing 关键字命中（{body_text[:200]}）"
        )
    if status == 429:
        return BackendRateLimitError(f"HTTP 429: rate limited（{body_text[:200]}）")
    return BackendCallError(f"HTTP {status}: {body_text[:200]}")


def _extract_image_b64(parsed: dict[str, Any]) -> tuple[str | None, str | None]:
    """从 OpenAI images/edits 响应抠 base64 或 URL。

    返回 (b64, url)；只会有一个非 None。
    Raises BackendCallError 当 data[] 为空 / 字段缺失时。
    """
    data = parsed.get("data") or []
    if not isinstance(data, list) or not data:
        raise BackendCallError("response.data 为空（无生成图像）")
    first = data[0]
    if not isinstance(first, dict):
        raise BackendCallError("response.data[0] 非对象")
    b64 = first.get("b64_json")
    if isinstance(b64, str) and b64:
        return b64, None
    url = first.get("url")
    if isinstance(url, str) and url:
        return None, url
    raise BackendCallError("response.data[0] 无 b64_json 也无 url")


def _download_image(url: str, timeout: float) -> bytes:
    """下载远程 URL 的二进制；失败抛 BackendCallError。"""
    req = Request(url, method="GET")
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.read()  # type: ignore[no-any-return]
    except (HTTPError, URLError, TimeoutError) as e:
        raise BackendCallError(f"下载生成图像失败：{type(e).__name__}: {e}") from None


class OpenAIImagesEditAdapter:
    """openai_images_edit — multipart POST /v1/images/edits。"""

    @property
    def kind(self) -> str:
        return "openai_images_edit"

    @property
    def known_params(
        self,
    ) -> dict[str, tuple[float | None, float | None]]:
        return dict(_KNOWN_PARAMS)

    def supports_controlnet(self) -> bool:
        return False

    def estimate_cost_usd(self, request: BackendRequest) -> float:
        size = str(request.params.get("size", "1024x1024")).lower()
        return _SIZE_PRICING.get(size, _DEFAULT_SIZE_PRICE)

    def call(
        self, request: BackendRequest, timeout: float
    ) -> BackendResponse:
        image_bytes = request.input_image_path.read_bytes()
        image_filename = request.input_image_path.name

        fields: dict[str, str] = {
            "model": request.model_name,
            "prompt": request.prompt,
            "response_format": "b64_json",
        }
        # 仅传 known_params 里的字段（rule_table 已 clamp + 类型校验）
        for k in ("quality", "style", "n", "size"):
            if k in request.params:
                fields[k] = str(request.params[k])

        files = {
            "image": (image_filename, image_bytes, "image/png"),
        }
        body, content_type = _encode_multipart(fields, files)

        headers = {
            "Authorization": f"Bearer {request.api_key}",
            "Content-Type": content_type,
        }
        req = Request(
            request.base_url, data=body, headers=headers, method="POST"
        )

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

        b64, url = _extract_image_b64(parsed)
        if b64 is not None:
            try:
                out_bytes = base64.b64decode(b64, validate=True)
            except (ValueError, base64.binascii.Error) as e:  # type: ignore[attr-defined]
                raise BackendCallError(f"base64 解码失败：{e}") from None
        else:
            assert url is not None
            out_bytes = _download_image(url, timeout)

        out_path = (
            request.input_image_path.parent
            / f"{request.input_image_path.stem}_retry{request.input_image_path.suffix}"
        )
        out_path.write_bytes(out_bytes)

        raw_request_summary: dict[str, Any] = {
            "kind": "openai_images_edit",
            "endpoint": request.base_url,
            "model": request.model_name,
            "params": {k: request.params[k] for k in ("quality", "style", "n", "size") if k in request.params},
            "http_status": resp_status,
            "image_filename": image_filename,
        }

        return BackendResponse(
            output_image_path=out_path,
            actual_cost_usd=None,
            raw_request_summary=raw_request_summary,
        )
