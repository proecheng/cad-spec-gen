"""LLM HTTP 调用 + 重试 + redact + kill switch + vendor_request_id 提取 (13 case)。"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.jury.config import JuryProfile
from tools.jury.llm_client import (
    JuryDisabledByEnv,
    JuryLlmError,
    LlmResponse,
    request_jury_verdict,
)


@pytest.fixture
def profile() -> JuryProfile:
    return JuryProfile(
        id="test",
        kind="openai_compat",
        api_base_url="https://api.example.com/v1",
        api_key="dummy-not-a-real-key",
        model="gpt-4o",
        cost_per_call_usd=0.020,
    )


@pytest.fixture
def fake_image(tmp_path: Path) -> Path:
    p = tmp_path / "img.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    return p


def _mock_response(
    status: int = 200,
    body: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> MagicMock:
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = json.dumps(
        body
        or {
            "id": "chatcmpl-Abc",
            "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
        }
    ).encode("utf-8")
    resp.headers = headers or {
        "Content-Type": "application/json",
        "x-request-id": "trace-123",
    }
    return resp


def _make_cm(resp: MagicMock) -> MagicMock:
    cm = MagicMock()
    cm.__enter__.return_value = resp
    cm.__exit__.return_value = None
    return cm


def test_kill_switch_raises_jury_disabled(
    profile: JuryProfile, fake_image: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CAD_JURY_DISABLE_LLM", "1")
    with pytest.raises(JuryDisabledByEnv):
        request_jury_verdict(profile=profile, image_path=fake_image, prompt="x")


def test_200_happy_returns_llm_response(
    profile: JuryProfile, fake_image: Path, enable_llm_for_test: None
) -> None:
    with patch("tools.jury.llm_client.urlopen") as m:
        m.return_value = _make_cm(_mock_response())
        resp = request_jury_verdict(profile=profile, image_path=fake_image, prompt="x")
    assert isinstance(resp, LlmResponse)
    assert resp.http_status == 200
    assert resp.attempts == 1
    assert resp.vendor_request_id == "trace-123"


def test_api_key_not_in_exception_str(
    profile: JuryProfile, fake_image: Path, enable_llm_for_test: None
) -> None:
    """模拟 401 看 JuryLlmError str 不含 key。"""
    from urllib.error import HTTPError

    with patch("tools.jury.llm_client.urlopen") as m:
        m.side_effect = HTTPError(
            url=f"{profile.api_base_url}/chat/completions",
            code=401,
            msg="Unauthorized",
            hdrs={"Content-Type": "application/json"},  # type: ignore[arg-type]
            fp=io.BytesIO(b'{"error": "invalid_api_key"}'),
        )
        try:
            request_jury_verdict(
                profile=profile,
                image_path=fake_image,
                prompt="x",
                max_retries=0,
            )
        except JuryLlmError as exc:
            assert "dummy-not-a-real-key" not in str(exc)


def test_disable_llm_does_not_call_urlopen(
    profile: JuryProfile, fake_image: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CAD_JURY_DISABLE_LLM", "1")
    with patch("tools.jury.llm_client.urlopen") as m:
        with pytest.raises(JuryDisabledByEnv):
            request_jury_verdict(profile=profile, image_path=fake_image, prompt="x")
        m.assert_not_called()


def test_429_retries_then_succeeds(
    profile: JuryProfile, fake_image: Path, enable_llm_for_test: None
) -> None:
    """429 → retry → 200。"""
    from urllib.error import HTTPError

    err_429 = HTTPError(
        url="x",
        code=429,
        msg="too many",
        hdrs={},
        fp=io.BytesIO(b""),  # type: ignore[arg-type]
    )
    ok = _make_cm(_mock_response())
    iterator = iter([err_429, ok])

    def side_effect(*args: object, **kwargs: object) -> object:
        item = next(iterator)
        if isinstance(item, HTTPError):
            raise item
        return item

    with (
        patch("tools.jury.llm_client.urlopen", side_effect=side_effect),
        patch("tools.jury.llm_client.time.sleep"),
    ):
        resp = request_jury_verdict(
            profile=profile,
            image_path=fake_image,
            prompt="x",
            max_retries=2,
        )
    assert resp.http_status == 200
    assert resp.attempts == 2


def test_429_exhausted_raises_rate_limited(
    profile: JuryProfile, fake_image: Path, enable_llm_for_test: None
) -> None:
    from urllib.error import HTTPError

    err = HTTPError(url="x", code=429, msg="x", hdrs={}, fp=io.BytesIO(b""))  # type: ignore[arg-type]
    with (
        patch("tools.jury.llm_client.urlopen", side_effect=err),
        patch("tools.jury.llm_client.time.sleep"),
    ):
        with pytest.raises(JuryLlmError) as ei:
            request_jury_verdict(
                profile=profile,
                image_path=fake_image,
                prompt="x",
                max_retries=2,
            )
    assert ei.value.error_kind == "rate_limited"


def test_401_no_retry_auth_failed(
    profile: JuryProfile, fake_image: Path, enable_llm_for_test: None
) -> None:
    from urllib.error import HTTPError

    err = HTTPError(url="x", code=401, msg="x", hdrs={}, fp=io.BytesIO(b""))  # type: ignore[arg-type]
    with patch("tools.jury.llm_client.urlopen", side_effect=err) as m:
        with pytest.raises(JuryLlmError) as ei:
            request_jury_verdict(
                profile=profile,
                image_path=fake_image,
                prompt="x",
                max_retries=2,
            )
    assert ei.value.error_kind == "auth_failed"
    assert m.call_count == 1


def test_402_quota_exhausted(
    profile: JuryProfile, fake_image: Path, enable_llm_for_test: None
) -> None:
    from urllib.error import HTTPError

    err = HTTPError(url="x", code=402, msg="x", hdrs={}, fp=io.BytesIO(b""))  # type: ignore[arg-type]
    with patch("tools.jury.llm_client.urlopen", side_effect=err):
        with pytest.raises(JuryLlmError) as ei:
            request_jury_verdict(
                profile=profile,
                image_path=fake_image,
                prompt="x",
                max_retries=2,
            )
    assert ei.value.error_kind == "quota_exhausted"


def test_500_retries(
    profile: JuryProfile, fake_image: Path, enable_llm_for_test: None
) -> None:
    from urllib.error import HTTPError

    err = HTTPError(url="x", code=500, msg="x", hdrs={}, fp=io.BytesIO(b""))  # type: ignore[arg-type]
    ok = _make_cm(_mock_response())
    iterator = iter([err, ok])

    def side_effect(*args: object, **kwargs: object) -> object:
        item = next(iterator)
        if isinstance(item, HTTPError):
            raise item
        return item

    with (
        patch("tools.jury.llm_client.urlopen", side_effect=side_effect),
        patch("tools.jury.llm_client.time.sleep"),
    ):
        resp = request_jury_verdict(
            profile=profile,
            image_path=fake_image,
            prompt="x",
            max_retries=2,
        )
    assert resp.http_status == 200


def test_url_error_dns_failure(
    profile: JuryProfile, fake_image: Path, enable_llm_for_test: None
) -> None:
    from urllib.error import URLError

    with (
        patch(
            "tools.jury.llm_client.urlopen",
            side_effect=URLError("Name or service not known"),
        ),
        patch("tools.jury.llm_client.time.sleep"),
    ):
        with pytest.raises(JuryLlmError) as ei:
            request_jury_verdict(
                profile=profile,
                image_path=fake_image,
                prompt="x",
                max_retries=1,
            )
    assert ei.value.error_kind == "network_unreachable"


def test_max_retries_zero_no_retry(
    profile: JuryProfile, fake_image: Path, enable_llm_for_test: None
) -> None:
    from urllib.error import HTTPError

    err = HTTPError(url="x", code=500, msg="x", hdrs={}, fp=io.BytesIO(b""))  # type: ignore[arg-type]
    with patch("tools.jury.llm_client.urlopen", side_effect=err) as m:
        with pytest.raises(JuryLlmError):
            request_jury_verdict(
                profile=profile,
                image_path=fake_image,
                prompt="x",
                max_retries=0,
            )
    assert m.call_count == 1


def test_debuglevel_set_to_zero_at_import() -> None:
    """jury llm_client import 后 debuglevel=0。"""
    import http.client

    from tools.jury import llm_client  # noqa: F401

    assert http.client.HTTPConnection.debuglevel == 0


def test_timeout_kwarg_passed_to_urlopen(
    profile: JuryProfile, fake_image: Path, enable_llm_for_test: None
) -> None:
    with patch("tools.jury.llm_client.urlopen") as m:
        m.return_value = _make_cm(_mock_response())
        request_jury_verdict(profile=profile, image_path=fake_image, prompt="x")
    _, kwargs = m.call_args
    assert kwargs.get("timeout") == 60


# ============ v2.37.1 hotfix：第三方代理 anti-bot UA 兼容 ============


def test_request_jury_verdict_sends_explicit_user_agent(
    profile: JuryProfile, fake_image: Path, enable_llm_for_test: None
) -> None:
    """v2.37.1：request_jury_verdict 必须发显式 User-Agent，不能让 urllib 默认
    `Python-urllib/3.x` 被 anti-bot 第三方代理（如 micuapi.ai）403 拦截。
    """
    with patch("tools.jury.llm_client.urlopen") as m:
        m.return_value = _make_cm(_mock_response())
        request_jury_verdict(profile=profile, image_path=fake_image, prompt="x")
    req = m.call_args[0][0]
    ua = req.get_header("User-agent")
    assert ua, "应有 User-Agent header"
    assert "Python-urllib" not in ua, f"不能用 urllib 默认 UA；实际：{ua!r}"
