"""Task 2.5.3：openai_images_edit adapter 单元测试。"""
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

from tools.jury_loop.backends.openai_images_edit import OpenAIImagesEditAdapter
from tools.jury_loop.backends.protocol import (
    BackendAdapter,
    BackendAuthError,
    BackendCallError,
    BackendQuotaExceededError,
    BackendRateLimitError,
    BackendRequest,
)


@pytest.fixture
def adapter() -> OpenAIImagesEditAdapter:
    return OpenAIImagesEditAdapter()


@pytest.fixture
def png_input(tmp_path: Path) -> Path:
    p = tmp_path / "V1_baseline.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n_fake_image_data_")
    return p


def _make_request(
    png: Path,
    *,
    base_url: str = "https://api.openai.com/v1/images/edits",
    api_key: str = "sk-fake-test",
    model_name: str = "gpt-image-1",
    params: dict[str, Any] | None = None,
) -> BackendRequest:
    return BackendRequest(
        input_image_path=png,
        prompt="enhance this product shot",
        params=params or {"size": "1024x1024", "quality": "high", "n": 1},
        base_url=base_url,
        api_key=api_key,
        model_name=model_name,
    )


def _fake_b64() -> str:
    return base64.b64encode(b"\x89PNG\r\n\x1a\n").decode("ascii")


@contextmanager
def _fake_urlopen_ok(response_dict: dict[str, Any], status: int = 200):
    body = json.dumps(response_dict).encode("utf-8")

    class _R:
        def __init__(self) -> None:
            self.status = status
            self.headers: dict[str, str] = {}

        def read(self) -> bytes:
            return body

        def __enter__(self) -> "_R":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    yield _R()


def _http_error_factory(status: int, body: str = ""):
    fp = io.BytesIO(body.encode("utf-8")) if body else None
    return HTTPError(
        url="https://api.openai.com",
        code=status,
        msg=f"HTTP {status}",
        hdrs={},  # type: ignore[arg-type]
        fp=fp,
    )


# ============ Protocol ============


def test_adapter_implements_protocol(adapter: OpenAIImagesEditAdapter) -> None:
    assert isinstance(adapter, BackendAdapter)


def test_kind(adapter: OpenAIImagesEditAdapter) -> None:
    assert adapter.kind == "openai_images_edit"


def test_supports_controlnet(adapter: OpenAIImagesEditAdapter) -> None:
    assert adapter.supports_controlnet() is False


def test_known_params_n_range(adapter: OpenAIImagesEditAdapter) -> None:
    """plan line 1064: known_params n 字段范围 (1, 4)。"""
    kp = adapter.known_params
    assert kp["n"] == (1, 4)


def test_known_params_non_numeric_fields(
    adapter: OpenAIImagesEditAdapter,
) -> None:
    """quality / style / size 用 (None, None) 标记非数值字段。"""
    kp = adapter.known_params
    assert kp["quality"] == (None, None)
    assert kp["style"] == (None, None)
    assert kp["size"] == (None, None)


def test_known_params_returns_copy(adapter: OpenAIImagesEditAdapter) -> None:
    kp = adapter.known_params
    kp["foo"] = (1, 2)
    assert "foo" not in adapter.known_params


# ============ estimate_cost_usd ============


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        ("1024x1024", 0.04),
        ("1024x1792", 0.08),
        ("1792x1024", 0.08),
        ("1024x1536", 0.06),
        ("1536x1024", 0.06),
        ("custom-unknown", 0.04),
    ],
)
def test_estimate_cost_usd_by_size(
    adapter: OpenAIImagesEditAdapter,
    png_input: Path,
    size: str,
    expected: float,
) -> None:
    """plan line 1055：按 size 维度（1024×1024=0.04 / 1024×1792=0.08）。"""
    req = _make_request(png_input, params={"size": size})
    assert adapter.estimate_cost_usd(req) == expected


def test_estimate_cost_default_size_when_missing(
    adapter: OpenAIImagesEditAdapter, png_input: Path
) -> None:
    """size 缺失默认 1024x1024 → 0.04。"""
    req = _make_request(png_input, params={})
    assert adapter.estimate_cost_usd(req) == 0.04


# ============ multipart body ============


def test_call_multipart_body_contains_image_and_prompt(
    adapter: OpenAIImagesEditAdapter, png_input: Path
) -> None:
    """plan line 1060：multipart body 含 image + prompt 字段。"""
    req = _make_request(png_input)
    response = {"data": [{"b64_json": _fake_b64()}]}
    captured: dict[str, Any] = {}

    def _capture(request, timeout=None):  # type: ignore[no-untyped-def]
        captured["body"] = request.data
        captured["headers"] = dict(request.headers)
        return _fake_urlopen_ok(response).__enter__()

    with patch(
        "tools.jury_loop.backends.openai_images_edit.urlopen",
        side_effect=_capture,
    ):
        adapter.call(req, timeout=30.0)

    body = captured["body"]
    assert isinstance(body, bytes)
    body_text = body.decode("utf-8", errors="replace")
    assert 'name="image"' in body_text
    assert 'filename="V1_baseline.png"' in body_text
    assert 'name="prompt"' in body_text
    assert "enhance this product shot" in body_text
    assert 'name="model"' in body_text
    assert "gpt-image-1" in body_text
    assert 'name="response_format"' in body_text
    assert "b64_json" in body_text
    # n / quality / size 也在 body 中
    assert 'name="size"' in body_text
    assert "1024x1024" in body_text

    # Content-Type header 含 boundary
    ct = captured["headers"]["Content-type"]
    assert ct.startswith("multipart/form-data; boundary=")


def test_call_b64_response_writes_file(
    adapter: OpenAIImagesEditAdapter, png_input: Path
) -> None:
    """正常 b64_json 响应 → 落盘 + actual_cost_usd=None。"""
    req = _make_request(png_input)
    response = {"data": [{"b64_json": _fake_b64()}]}

    with patch(
        "tools.jury_loop.backends.openai_images_edit.urlopen",
        return_value=_fake_urlopen_ok(response),
    ):
        resp = adapter.call(req, timeout=30.0)

    assert resp.output_image_path.exists()
    assert resp.output_image_path.read_bytes().startswith(b"\x89PNG")
    assert resp.actual_cost_usd is None
    assert resp.raw_request_summary["kind"] == "openai_images_edit"


def test_call_url_response_downloads(
    adapter: OpenAIImagesEditAdapter, png_input: Path
) -> None:
    """response.data[0].url → 第二次 urlopen GET 下载。"""
    req = _make_request(png_input)
    download_url = "https://oai-storage.example.com/img/abc.png"
    response_post = {"data": [{"url": download_url}]}

    @contextmanager
    def _fake_get():
        class _R:
            status = 200

            def read(self) -> bytes:
                return b"\x89PNG\r\n\x1a\n_downloaded_"

            def __enter__(self) -> "_R":
                return self

            def __exit__(self, *args: object) -> None:
                return None

        yield _R()

    call_count = {"n": 0}

    def _urlopen_side(request, timeout=None):  # type: ignore[no-untyped-def]
        call_count["n"] += 1
        if call_count["n"] == 1:
            assert request.method == "POST"
            return _fake_urlopen_ok(response_post).__enter__()
        # second call: GET download
        assert request.full_url == download_url
        return _fake_get().__enter__()

    with patch(
        "tools.jury_loop.backends.openai_images_edit.urlopen",
        side_effect=_urlopen_side,
    ):
        resp = adapter.call(req, timeout=30.0)

    assert resp.output_image_path.exists()
    assert call_count["n"] == 2


def test_raw_request_summary_no_api_key(
    adapter: OpenAIImagesEditAdapter, png_input: Path
) -> None:
    """raw_request_summary 不得含 api_key（写入 sidecar）。"""
    req = _make_request(png_input, api_key="VERY-SECRET")
    response = {"data": [{"b64_json": _fake_b64()}]}

    with patch(
        "tools.jury_loop.backends.openai_images_edit.urlopen",
        return_value=_fake_urlopen_ok(response),
    ):
        resp = adapter.call(req, timeout=30.0)

    assert "VERY-SECRET" not in json.dumps(resp.raw_request_summary)


# ============ HTTP 错误分类 ============


def test_call_401_auth_error(
    adapter: OpenAIImagesEditAdapter, png_input: Path
) -> None:
    """plan line 1062：401 → BackendAuthError。"""
    req = _make_request(png_input)
    with patch(
        "tools.jury_loop.backends.openai_images_edit.urlopen",
        side_effect=_http_error_factory(401, '{"error": "invalid_api_key"}'),
    ):
        with pytest.raises(BackendAuthError):
            adapter.call(req, timeout=30.0)


def test_call_402_quota_exceeded(
    adapter: OpenAIImagesEditAdapter, png_input: Path
) -> None:
    """plan line 1063：402 → BackendQuotaExceededError。"""
    req = _make_request(png_input)
    with patch(
        "tools.jury_loop.backends.openai_images_edit.urlopen",
        side_effect=_http_error_factory(402, '{"error": "billing"}'),
    ):
        with pytest.raises(BackendQuotaExceededError):
            adapter.call(req, timeout=30.0)


def test_call_insufficient_quota_keyword(
    adapter: OpenAIImagesEditAdapter, png_input: Path
) -> None:
    """body 含 'insufficient_quota' → BackendQuotaExceededError（OpenAI 实际错误码）。"""
    req = _make_request(png_input)
    body = '{"error": {"code": "insufficient_quota", "message": "..."}}'
    with patch(
        "tools.jury_loop.backends.openai_images_edit.urlopen",
        side_effect=_http_error_factory(429, body),
    ):
        with pytest.raises(BackendQuotaExceededError):
            adapter.call(req, timeout=30.0)


def test_call_429_rate_limited(
    adapter: OpenAIImagesEditAdapter, png_input: Path
) -> None:
    """429 不含 quota 关键字 → BackendRateLimitError。"""
    req = _make_request(png_input)
    body = '{"error": "rate limit hit"}'
    with patch(
        "tools.jury_loop.backends.openai_images_edit.urlopen",
        side_effect=_http_error_factory(429, body),
    ):
        with pytest.raises(BackendRateLimitError):
            adapter.call(req, timeout=30.0)


def test_call_400_content_policy_is_call_error_not_auth(
    adapter: OpenAIImagesEditAdapter, png_input: Path
) -> None:
    """plan line 1061 TRAP：400 + content_policy_violation → BackendCallError，
    不是 BackendAuthError、不是 BackendQuotaExceededError。"""
    req = _make_request(png_input)
    body = '{"error": {"code": "content_policy_violation", "message": "..."}}'
    with patch(
        "tools.jury_loop.backends.openai_images_edit.urlopen",
        side_effect=_http_error_factory(400, body),
    ):
        # 必须是 BackendCallError 直接捕获，且不能是任何子类
        with pytest.raises(BackendCallError) as exc_info:
            adapter.call(req, timeout=30.0)
        # 严格断言：raise 的精确类型不是 Auth/Quota/RateLimit 子类
        assert type(exc_info.value) is BackendCallError
        assert not isinstance(exc_info.value, BackendAuthError)
        assert not isinstance(exc_info.value, BackendQuotaExceededError)
        assert not isinstance(exc_info.value, BackendRateLimitError)


def test_call_500_call_error(
    adapter: OpenAIImagesEditAdapter, png_input: Path
) -> None:
    req = _make_request(png_input)
    with patch(
        "tools.jury_loop.backends.openai_images_edit.urlopen",
        side_effect=_http_error_factory(500, '{"error": "internal"}'),
    ):
        with pytest.raises(BackendCallError):
            adapter.call(req, timeout=30.0)


def test_call_url_error_call_error(
    adapter: OpenAIImagesEditAdapter, png_input: Path
) -> None:
    req = _make_request(png_input)
    with patch(
        "tools.jury_loop.backends.openai_images_edit.urlopen",
        side_effect=URLError("dns failed"),
    ):
        with pytest.raises(BackendCallError):
            adapter.call(req, timeout=30.0)


def test_call_response_data_empty(
    adapter: OpenAIImagesEditAdapter, png_input: Path
) -> None:
    req = _make_request(png_input)
    response = {"data": []}
    with patch(
        "tools.jury_loop.backends.openai_images_edit.urlopen",
        return_value=_fake_urlopen_ok(response),
    ):
        with pytest.raises(BackendCallError, match="data"):
            adapter.call(req, timeout=30.0)
