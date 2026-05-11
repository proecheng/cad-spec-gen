"""SEC-MINOR-2 secrets_scrubber 测试。"""
from __future__ import annotations

import pytest

from tools.jury_loop.secrets_scrubber import scrub_secrets


class TestScrubSecrets:
    def test_redacts_fal_key_envvar(self) -> None:
        text = "Error: FAL_KEY=sk-abc123 expired"
        assert scrub_secrets(text) == "Error: FAL_KEY=[REDACTED] expired"

    def test_redacts_bearer_token(self) -> None:
        text = "Authorization: Bearer eyJhbGc.payload.signature"
        assert "[REDACTED]" in scrub_secrets(text)
        assert "eyJhbGc" not in scrub_secrets(text)

    def test_redacts_authorization_header_quoted(self) -> None:
        text = '{"Authorization": "Bearer abc123"}'
        out = scrub_secrets(text)
        assert "abc123" not in out

    def test_redacts_openai_gemini_anthropic_keys(self) -> None:
        text = "OPENAI_API_KEY=sk-foo GEMINI_API_KEY=ai-bar ANTHROPIC_API_KEY=sk-ant-baz"
        out = scrub_secrets(text)
        assert "sk-foo" not in out
        assert "ai-bar" not in out
        assert "sk-ant-baz" not in out

    def test_passthrough_when_no_secrets(self) -> None:
        text = "rule_table miss tag plastic_look"
        assert scrub_secrets(text) == text

    def test_handles_nested_dict(self) -> None:
        payload = {"api_key": "sk-secret", "model": "gemini-1.5"}
        out = scrub_secrets(payload)
        assert out["api_key"] == "[REDACTED]"
        assert out["model"] == "gemini-1.5"

    def test_handles_list_of_dicts(self) -> None:
        payload = [{"api_key": "k1"}, {"FAL_KEY": "k2"}]
        out = scrub_secrets(payload)
        assert all(d.get("api_key") == "[REDACTED]" or d.get("FAL_KEY") == "[REDACTED]" for d in out)

    def test_truncate_at_200_chars(self) -> None:
        text = "x" * 500
        out = scrub_secrets(text, max_len=200)
        assert len(out) == 200
