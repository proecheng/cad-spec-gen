"""Task 2.5.2：gemini_chat_image adapter 单元测试。

mock 策略：urllib.request.urlopen 替成假 context manager / 抛 HTTPError。
"""
from __future__ import annotations

import base64
import io
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest

from tools.jury_loop.backends.gemini_chat_image import GeminiChatImageAdapter
from tools.jury_loop.backends.protocol import (
    BackendAdapter,
    BackendAuthError,
    BackendCallError,
    BackendQuotaExceededError,
    BackendRateLimitError,
    BackendRequest,
)


@pytest.fixture
def adapter() -> GeminiChatImageAdapter:
    return GeminiChatImageAdapter()


@pytest.fixture
def png_input(tmp_path: Path) -> Path:
    """1x1 PNG 占位图（base64 解码后 ≥ 8 字节即可）。"""
    p = tmp_path / "V1_baseline.jpg"
    p.write_bytes(b"\x89PNG\r\n\x1a\n_fake_image_data_")
    return p


def _make_request(
    png: Path,
    *,
    base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    api_key: str = "sk-fake-test-key",
    model_name: str = "gemini-3-pro",
    params: dict[str, Any] | None = None,
) -> BackendRequest:
    return BackendRequest(
        input_image_path=png,
        prompt="enhance this image",
        params=params or {"temperature": 0.7},
        base_url=base_url,
        api_key=api_key,
        model_name=model_name,
    )


@contextmanager
def _fake_urlopen_ok(response_dict: dict[str, Any], status: int = 200):
    """假 urlopen 上下文：返回 200 + given JSON。"""
    body = json.dumps(response_dict).encode("utf-8")

    class _FakeResp:
        def __init__(self) -> None:
            self.status = status
            self.headers: dict[str, str] = {}

        def read(self) -> bytes:
            return body

        def __enter__(self) -> "_FakeResp":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    yield _FakeResp()


def _fake_b64_image() -> str:
    """合法 base64 PNG（最小 8 字节 PNG header）。"""
    return base64.b64encode(b"\x89PNG\r\n\x1a\n").decode("ascii")


# ============ Protocol conformance ============


def test_adapter_implements_protocol(adapter: GeminiChatImageAdapter) -> None:
    """实现 BackendAdapter Protocol（@runtime_checkable）。"""
    assert isinstance(adapter, BackendAdapter)


def test_kind_is_gemini_chat_image(adapter: GeminiChatImageAdapter) -> None:
    assert adapter.kind == "gemini_chat_image"


def test_supports_controlnet_false(adapter: GeminiChatImageAdapter) -> None:
    """gemini_chat_image 不支持 ControlNet（rule_table 不会注入 canny/depth_strength）。"""
    assert adapter.supports_controlnet() is False


def test_known_params_contains_temperature(
    adapter: GeminiChatImageAdapter,
) -> None:
    """已知参数集含 temperature 范围 (0.0, 2.0)（plan line 1043）。"""
    kp = adapter.known_params
    assert "temperature" in kp
    assert kp["temperature"] == (0.0, 2.0)
    assert "top_p" in kp and kp["top_p"] == (0.0, 1.0)
    assert "top_k" in kp and kp["top_k"] == (1, 100)


def test_known_params_returns_copy(adapter: GeminiChatImageAdapter) -> None:
    """known_params 返回副本，修改不污染 adapter 内部状态。"""
    kp = adapter.known_params
    kp["foo"] = (0.0, 1.0)
    assert "foo" not in adapter.known_params


# ============ estimate_cost_usd ============


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("gemini-3-pro", 0.04),
        ("gemini-2.5-flash", 0.01),
        ("gemini-2.5-flash-image", 0.04),
        ("unknown-model-xyz", 0.05),
    ],
)
def test_estimate_cost_usd_by_model(
    adapter: GeminiChatImageAdapter,
    png_input: Path,
    model: str,
    expected: float,
) -> None:
    """按 model 名子串匹配定价（plan line 1042）。"""
    req = _make_request(png_input, model_name=model)
    assert adapter.estimate_cost_usd(req) == expected


# ============ call() 正常路径 ============


def test_call_openai_compat_success(
    adapter: GeminiChatImageAdapter, png_input: Path
) -> None:
    """OpenAI chat-completions 兼容路径：抠 choices[0].message.images[0].b64_json。"""
    req = _make_request(png_input)
    out_b64 = _fake_b64_image()
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "images": [{"b64_json": out_b64}],
                },
                "finish_reason": "stop",
            }
        ]
    }

    with patch(
        "tools.jury_loop.backends.gemini_chat_image.urlopen",
        return_value=_fake_urlopen_ok(response),
    ):
        resp = adapter.call(req, timeout=30.0)

    assert resp.output_image_path.exists()
    assert resp.output_image_path.read_bytes().startswith(b"\x89PNG")
    assert resp.actual_cost_usd is None  # vendor 不返计费
    assert resp.raw_request_summary["kind"] == "gemini_chat_image"
    assert resp.raw_request_summary["request_format"] == "chat_completions"
    assert resp.raw_request_summary["http_status"] == 200


def test_call_gemini_native_success(
    adapter: GeminiChatImageAdapter, png_input: Path
) -> None:
    """Gemini native generateContent 路径：抠 candidates[0].content.parts[i].inline_data.data。"""
    base_url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash-image:generateContent"
    )
    req = _make_request(png_input, base_url=base_url)
    out_b64 = _fake_b64_image()
    response = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "Generated image:"},
                        {
                            "inline_data": {
                                "mime_type": "image/png",
                                "data": out_b64,
                            }
                        },
                    ]
                }
            }
        ]
    }

    with patch(
        "tools.jury_loop.backends.gemini_chat_image.urlopen",
        return_value=_fake_urlopen_ok(response),
    ):
        resp = adapter.call(req, timeout=30.0)

    assert resp.output_image_path.exists()
    assert resp.raw_request_summary["request_format"] == "generateContent"


def test_call_request_body_contains_inline_image(
    adapter: GeminiChatImageAdapter, png_input: Path
) -> None:
    """请求 body 应含 base64 的输入图像（chat-completions 风格 image_url data URL）。"""
    req = _make_request(png_input)
    out_b64 = _fake_b64_image()
    response = {
        "choices": [
            {"message": {"images": [{"b64_json": out_b64}]}}
        ]
    }
    captured: dict[str, Any] = {}

    def _capture_urlopen(request, timeout=None):  # type: ignore[no-untyped-def]
        captured["body"] = request.data
        captured["headers"] = dict(request.headers)
        return _fake_urlopen_ok(response).__enter__()

    with patch(
        "tools.jury_loop.backends.gemini_chat_image.urlopen",
        side_effect=_capture_urlopen,
    ):
        adapter.call(req, timeout=30.0)

    body_dict = json.loads(captured["body"].decode("utf-8"))
    assert body_dict["model"] == "gemini-3-pro"
    content = body_dict["messages"][0]["content"]
    assert content[0]["type"] == "text"
    assert content[0]["text"] == "enhance this image"
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert body_dict["temperature"] == 0.7


def test_call_auth_header_chat_completions(
    adapter: GeminiChatImageAdapter, png_input: Path
) -> None:
    """OpenAI 兼容路径用 Authorization: Bearer。"""
    req = _make_request(png_input, api_key="my-secret-key-123")
    response = {"choices": [{"message": {"images": [{"b64_json": _fake_b64_image()}]}}]}
    captured: dict[str, Any] = {}

    def _capture(request, timeout=None):  # type: ignore[no-untyped-def]
        captured["headers"] = dict(request.headers)
        return _fake_urlopen_ok(response).__enter__()

    with patch(
        "tools.jury_loop.backends.gemini_chat_image.urlopen", side_effect=_capture
    ):
        adapter.call(req, timeout=30.0)

    # urllib.Request 的 headers key 首字母大写化
    assert "Authorization" in captured["headers"]
    assert captured["headers"]["Authorization"] == "Bearer my-secret-key-123"


def test_call_auth_header_gemini_native(
    adapter: GeminiChatImageAdapter, png_input: Path
) -> None:
    """Gemini native 路径用 x-goog-api-key header（不是 Bearer）。"""
    base_url = "https://example.com/v1beta/models/gemini-pro:generateContent"
    req = _make_request(png_input, base_url=base_url, api_key="goog-key-xyz")
    out_b64 = _fake_b64_image()
    response = {
        "candidates": [
            {"content": {"parts": [{"inline_data": {"data": out_b64}}]}}
        ]
    }
    captured: dict[str, Any] = {}

    def _capture(request, timeout=None):  # type: ignore[no-untyped-def]
        captured["headers"] = dict(request.headers)
        return _fake_urlopen_ok(response).__enter__()

    with patch(
        "tools.jury_loop.backends.gemini_chat_image.urlopen", side_effect=_capture
    ):
        adapter.call(req, timeout=30.0)

    # Header keys are normalized by urllib.Request to title case
    headers_lower = {k.lower(): v for k, v in captured["headers"].items()}
    assert "x-goog-api-key" in headers_lower
    assert headers_lower["x-goog-api-key"] == "goog-key-xyz"
    assert "authorization" not in headers_lower


def test_raw_request_summary_does_not_contain_api_key(
    adapter: GeminiChatImageAdapter, png_input: Path
) -> None:
    """raw_request_summary 写入 sidecar.backend_payload，不得含 api_key。"""
    req = _make_request(png_input, api_key="VERY-SECRET-DO-NOT-LEAK")
    response = {"choices": [{"message": {"images": [{"b64_json": _fake_b64_image()}]}}]}

    with patch(
        "tools.jury_loop.backends.gemini_chat_image.urlopen",
        return_value=_fake_urlopen_ok(response),
    ):
        resp = adapter.call(req, timeout=30.0)

    assert "VERY-SECRET" not in json.dumps(resp.raw_request_summary)


# ============ HTTP 错误分类 ============


def _http_error_factory(status: int, body: str = ""):
    """构造可抛的 HTTPError，body 通过 e.read() 返回。"""
    fp = io.BytesIO(body.encode("utf-8")) if body else None
    return HTTPError(
        url="https://example.com",
        code=status,
        msg=f"HTTP {status}",
        hdrs={},  # type: ignore[arg-type]
        fp=fp,
    )


@pytest.mark.parametrize("status", [401, 403])
def test_call_auth_error(
    adapter: GeminiChatImageAdapter, png_input: Path, status: int
) -> None:
    """401/403 → BackendAuthError（plan line 1041）。"""
    req = _make_request(png_input)
    with patch(
        "tools.jury_loop.backends.gemini_chat_image.urlopen",
        side_effect=_http_error_factory(status, '{"error": "unauthorized"}'),
    ):
        with pytest.raises(BackendAuthError, match=str(status)):
            adapter.call(req, timeout=30.0)


def test_call_rate_limit_error(
    adapter: GeminiChatImageAdapter, png_input: Path
) -> None:
    """429 → BackendRateLimitError（plan line 1042）。"""
    req = _make_request(png_input)
    with patch(
        "tools.jury_loop.backends.gemini_chat_image.urlopen",
        side_effect=_http_error_factory(429, '{"error": "rate limit"}'),
    ):
        with pytest.raises(BackendRateLimitError, match="429"):
            adapter.call(req, timeout=30.0)


def test_call_quota_402(
    adapter: GeminiChatImageAdapter, png_input: Path
) -> None:
    """402 → BackendQuotaExceededError。"""
    req = _make_request(png_input)
    with patch(
        "tools.jury_loop.backends.gemini_chat_image.urlopen",
        side_effect=_http_error_factory(402, '{"error": "billing"}'),
    ):
        with pytest.raises(BackendQuotaExceededError, match="402"):
            adapter.call(req, timeout=30.0)


def test_call_quota_keyword_in_body(
    adapter: GeminiChatImageAdapter, png_input: Path
) -> None:
    """body 含 'quota' 关键字（即使非 402）→ BackendQuotaExceededError。"""
    req = _make_request(png_input)
    with patch(
        "tools.jury_loop.backends.gemini_chat_image.urlopen",
        side_effect=_http_error_factory(400, '{"error": "insufficient_quota"}'),
    ):
        with pytest.raises(BackendQuotaExceededError):
            adapter.call(req, timeout=30.0)


def test_call_500_server_error(
    adapter: GeminiChatImageAdapter, png_input: Path
) -> None:
    """500 → BackendCallError 兜底。"""
    req = _make_request(png_input)
    with patch(
        "tools.jury_loop.backends.gemini_chat_image.urlopen",
        side_effect=_http_error_factory(500, '{"error": "internal"}'),
    ):
        with pytest.raises(BackendCallError):
            adapter.call(req, timeout=30.0)


def test_call_network_unreachable(
    adapter: GeminiChatImageAdapter, png_input: Path
) -> None:
    """URLError（DNS 失败 / 连接失败）→ BackendCallError。"""
    req = _make_request(png_input)
    with patch(
        "tools.jury_loop.backends.gemini_chat_image.urlopen",
        side_effect=URLError("Connection refused"),
    ):
        with pytest.raises(BackendCallError, match="网络/超时"):
            adapter.call(req, timeout=30.0)


def test_call_timeout(
    adapter: GeminiChatImageAdapter, png_input: Path
) -> None:
    """TimeoutError → BackendCallError。"""
    req = _make_request(png_input)
    with patch(
        "tools.jury_loop.backends.gemini_chat_image.urlopen",
        side_effect=TimeoutError("read timeout"),
    ):
        with pytest.raises(BackendCallError, match="网络/超时"):
            adapter.call(req, timeout=30.0)


def test_call_response_no_image(
    adapter: GeminiChatImageAdapter, png_input: Path
) -> None:
    """响应 JSON 无图像数据 → BackendCallError。"""
    req = _make_request(png_input)
    response = {"choices": [{"message": {"content": "no image returned"}}]}
    with patch(
        "tools.jury_loop.backends.gemini_chat_image.urlopen",
        return_value=_fake_urlopen_ok(response),
    ):
        with pytest.raises(BackendCallError, match="无图像数据"):
            adapter.call(req, timeout=30.0)


def test_call_response_invalid_json(
    adapter: GeminiChatImageAdapter, png_input: Path
) -> None:
    """响应非 JSON → BackendCallError。"""
    req = _make_request(png_input)

    class _BadJsonResp:
        status = 200
        headers: dict[str, str] = {}

        def read(self) -> bytes:
            return b"<html>not json</html>"

        def __enter__(self) -> "_BadJsonResp":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    with patch(
        "tools.jury_loop.backends.gemini_chat_image.urlopen",
        return_value=_BadJsonResp(),
    ):
        with pytest.raises(BackendCallError, match="解析失败"):
            adapter.call(req, timeout=30.0)
