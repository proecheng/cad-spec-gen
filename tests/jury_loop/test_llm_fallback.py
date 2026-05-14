"""Task 3.1：llm_fallback 单元测试（RED → GREEN）。

mock 策略：urllib.request.urlopen 替成假 context manager / 抛 HTTPError，与
session 2 三 adapter 同款。fallback 自身**不** scrub secrets（调用方在
sidecar 写出前负责），因此测试断言 secrets 字符串原样保留。
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from tools.jury.config import JuryProfile
from tools.jury_loop.llm_fallback import LlmFallbackError, translate


@pytest.fixture
def profile() -> JuryProfile:
    """fake JuryProfile（chat-completions 兼容形态）。"""
    return JuryProfile(
        id="test",
        kind="openai_compat",
        api_base_url="https://example.test/v1",
        api_key="sk-fake-test-key",
        model="gemini-2.5-flash",
        cost_per_call_usd=0.005,
    )


@contextmanager
def _fake_urlopen_text(content_text: str, status: int = 200):
    """假 urlopen 上下文：返回 200 + chat-completions JSON 含 content_text。"""
    body = json.dumps(
        {
            "choices": [
                {"message": {"role": "assistant", "content": content_text}}
            ]
        }
    ).encode("utf-8")

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


# ============ 1. 正常路径：返 list[str]，每条 ≤80 字 ============


def test_translate_returns_list_of_str_under_80_chars(profile: JuryProfile) -> None:
    """正常调用返 list[str]，每元素 ≤80 字（plan line 1128）。"""
    response_text = "soft volumetric lighting, warm color tone, sharp focus"
    with patch(
        "tools.jury_loop.llm_fallback.urlopen",
        return_value=_fake_urlopen_text(response_text).__enter__(),
    ):
        addons = translate(
            unmapped_reason="some unknown jury reason",
            sanitized_reason="some unknown jury reason",
            profile=profile,
        )
    assert isinstance(addons, list)
    assert all(isinstance(a, str) for a in addons)
    assert all(len(a) <= 80 for a in addons), (
        f"每条 addon 必须 ≤80 字，实际：{[(a, len(a)) for a in addons]}"
    )
    assert len(addons) >= 1
    # 内容应去除空白、按逗号拆分
    assert "soft volumetric lighting" in addons


def test_translate_caps_addon_length_at_80_chars(profile: JuryProfile) -> None:
    """LLM 返超长元素时截断到 80 字（防 prompt 注入巨长字串）。"""
    long_addon = "x" * 200
    response_text = f"{long_addon}, normal addon"
    with patch(
        "tools.jury_loop.llm_fallback.urlopen",
        return_value=_fake_urlopen_text(response_text).__enter__(),
    ):
        addons = translate(
            unmapped_reason="reason",
            sanitized_reason="reason",
            profile=profile,
        )
    assert all(len(a) <= 80 for a in addons)


# ============ 2. 空 reason 短路：返 [] 不调 LLM ============


def test_translate_empty_unmapped_returns_empty_list(profile: JuryProfile) -> None:
    """空 unmapped_reason 返 [] 不发请求（plan line 1129）。"""
    with patch("tools.jury_loop.llm_fallback.urlopen") as mock_urlopen:
        addons = translate(
            unmapped_reason="",
            sanitized_reason="anything",
            profile=profile,
        )
    assert addons == []
    mock_urlopen.assert_not_called()


def test_translate_whitespace_only_unmapped_returns_empty_list(
    profile: JuryProfile,
) -> None:
    """纯空白 unmapped_reason 同样短路。"""
    with patch("tools.jury_loop.llm_fallback.urlopen") as mock_urlopen:
        addons = translate(
            unmapped_reason="   \n\t  ",
            sanitized_reason="anything",
            profile=profile,
        )
    assert addons == []
    mock_urlopen.assert_not_called()


# ============ 3. LLM 异常 → raise LlmFallbackError（不静默吞） ============


def test_translate_http_error_raises_fallback_error(profile: JuryProfile) -> None:
    """LLM client 抛 HTTPError → raise LlmFallbackError（plan line 1130）。"""
    err = HTTPError(
        url="https://example.test/v1/chat/completions",
        code=401,
        msg="Unauthorized",
        hdrs=None,  # type: ignore[arg-type]
        fp=None,
    )
    with patch("tools.jury_loop.llm_fallback.urlopen", side_effect=err):
        with pytest.raises(LlmFallbackError):
            translate(
                unmapped_reason="reason",
                sanitized_reason="reason",
                profile=profile,
            )


def test_translate_url_error_raises_fallback_error(profile: JuryProfile) -> None:
    """网络不可达同样 raise（不静默吞）。"""
    from urllib.error import URLError

    with patch(
        "tools.jury_loop.llm_fallback.urlopen", side_effect=URLError("dns fail")
    ):
        with pytest.raises(LlmFallbackError):
            translate(
                unmapped_reason="reason",
                sanitized_reason="reason",
                profile=profile,
            )


# ============ 4. secrets 字符串：fallback 自身不 scrub（调用方负责） ============


def test_translate_does_not_scrub_secrets_caller_responsibility(
    profile: JuryProfile,
) -> None:
    """LLM 返回含 FAL_KEY=xxx 时 fallback 不 scrub（plan line 1131）。

    设计：scrub 由 metadata.write_sidecar 在写盘前统一做（SEC-MINOR-2），
    fallback 自身只做语义切分。Memory `feedback_silent_failure_*` 不适用：
    本测试断言 secrets 不被静默吞掉，而是原样向调用方暴露——调用方有责
    任 scrub 后再写盘。
    """
    response_text = "FAL_KEY=sk-real-leak, soft lighting, warm tone"
    with patch(
        "tools.jury_loop.llm_fallback.urlopen",
        return_value=_fake_urlopen_text(response_text).__enter__(),
    ):
        addons = translate(
            unmapped_reason="reason with secret",
            sanitized_reason="reason with secret",
            profile=profile,
        )
    joined = " ".join(addons)
    assert "FAL_KEY=sk-real-leak" in joined, (
        "fallback 自身不 scrub；secret 必须原样返给调用方，由 metadata "
        "层 scrub_secrets 统一去除（SEC-MINOR-2）"
    )


def test_parse_addons_caps_huge_llm_output_at_4k(profile: JuryProfile) -> None:
    """Important #5：恶意/异常 LLM 返回 1MB 文本时，先 cap 到 4096 字再 split。

    max_tokens=256 已限定正常路径，但纯字符限定是更稳的兜底（防御性深度）。
    """
    huge_payload = ("addon" + "," * 200_000 + "tail")  # ~1MB 逗号雪崩
    with patch(
        "tools.jury_loop.llm_fallback.urlopen",
        return_value=_fake_urlopen_text(huge_payload).__enter__(),
    ):
        addons = translate(
            unmapped_reason="x", sanitized_reason="x", profile=profile,
        )
    # 输出仍切到前 _MAX_ADDONS=3 项；不会因 split 1M 字符消耗内存
    assert len(addons) <= 3
    # 每条仍 ≤ _MAX_ADDON_CHARS=80
    assert all(len(a) <= 80 for a in addons)


# ============ v2.37.1 hotfix：第三方代理 anti-bot UA 兼容 ============


def test_request_chat_text_sends_explicit_user_agent(profile: JuryProfile) -> None:
    """v2.37.1：_request_chat_text 必须发显式 User-Agent，不能让 urllib 默认
    `Python-urllib/3.x` 被 anti-bot 第三方代理（如 micuapi.ai）403。

    用 `mock.patch` 拦截 urlopen，断 Request 对象含 `User-agent` header（urllib
    把 header 名规范化为首字母大写其余小写）。
    """
    with patch("tools.jury_loop.llm_fallback.urlopen") as m:
        m.return_value = _fake_urlopen_text("addon1,addon2").__enter__()
        translate(unmapped_reason="x", sanitized_reason="x", profile=profile)

    # 抓 Request 对象（urlopen 第一个位置参数）
    call_args = m.call_args
    req = call_args[0][0]
    ua = req.get_header("User-agent")
    assert ua, "应有 User-Agent header（不能是 Python urllib 默认）"
    assert "Python-urllib" not in ua, f"不能用 urllib 默认 UA；实际：{ua!r}"
