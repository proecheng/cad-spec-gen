"""集中脱敏 4 函数的单元测试 — 8 case 覆盖 url/headers/body/traceback_str。"""

from __future__ import annotations

from tools.jury.redact import (
    redact_body,
    redact_headers,
    redact_traceback_str,
    redact_url,
)


def test_redact_url_strips_query_and_fragment() -> None:
    """剥 query/fragment — api_key / 任意 query / fragment 全部消失。"""
    result = redact_url(
        "https://api.example.com/v1/chat/completions?api_key=sk-secret&foo=bar#frag"
    )
    assert "sk-secret" not in result
    assert "api_key" not in result
    assert "frag" not in result
    assert result.startswith("https://api.example.com/v1/chat/completions")


def test_redact_url_keeps_host_and_path() -> None:
    """保留 scheme://host/path（公开诊断信息）。"""
    result = redact_url("https://api.openai.com/v1/chat/completions?x=1")
    assert "api.openai.com" in result
    assert "/v1/chat/completions" in result


def test_redact_headers_removes_authorization_case_insensitive() -> None:
    """大小写不敏感移除 Authorization/Cookie/x-api-key；保留公开 trace ID + Content-Type。"""
    headers = {
        "Authorization": "Bearer sk-xxx",
        "Cookie": "sess=abc",
        "x-api-key": "yyy",
        "x-request-id": "trace-123",
        "Content-Type": "application/json",
    }
    result = redact_headers(headers)
    assert "Authorization" not in result
    assert "Cookie" not in result
    assert "x-api-key" not in result
    assert result.get("x-request-id") == "trace-123"  # 公开 trace ID 保留
    assert result.get("Content-Type") == "application/json"


def test_redact_body_truncates_to_max_chars() -> None:
    """超过 max_chars 截断 + 追加 '...truncated' 标记。"""
    body = "x" * 1000
    result = redact_body(body, max_chars=128)
    assert len(result) <= 128 + len("...truncated")
    assert "...truncated" in result


def test_redact_body_short_unchanged() -> None:
    """短 body 不变（不引入意外变化）。"""
    body = "short"
    assert redact_body(body, max_chars=128) == "short"


def test_redact_traceback_strips_api_key_lines() -> None:
    """traceback 字符串内 frame locals 含 api_key= / Authorization Bearer 的整行被脱敏。"""
    tb = (
        "Traceback (most recent call last):\n"
        '  File "x.py", line 1, in <module>\n'
        "    raise X\n"
        "Local: api_key='sk-secret-xyz'\n"
        "Local: Authorization='Bearer sk-yyy'\n"
        "X: error"
    )
    result = redact_traceback_str(tb)
    assert "sk-secret-xyz" not in result
    assert "sk-yyy" not in result


def test_redact_url_empty_string() -> None:
    """空字符串透传，不抛异常。"""
    assert redact_url("") == ""


def test_redact_headers_empty_safe() -> None:
    """空 dict 透传。"""
    assert redact_headers({}) == {}
