"""reason_parser 测试 — 含 reason_sanitized + parse_reason 单元 + hypothesis property。"""
from __future__ import annotations

import string

from hypothesis import given, strategies as st

from tools.jury_loop.reason_parser import (
    BUILTIN_TAGS,
    parse_reason,
    reason_sanitized,
)


class TestReasonSanitized:
    def test_preserves_ascii_printable(self) -> None:
        assert reason_sanitized("plastic look, flat lighting") == "plastic look, flat lighting"

    def test_strips_control_chars(self) -> None:
        # \x1b[31m 整段是 ANSI escape（ESC + CSI 31m），整段剥；\x00 也是控制字符剥
        assert reason_sanitized("plastic\x00look\x1b[31m") == "plasticlook"

    def test_truncates_at_200(self) -> None:
        out = reason_sanitized("x" * 500)
        assert len(out) <= 200

    def test_strips_non_ascii(self) -> None:
        assert "中文" not in reason_sanitized("plastic 中文 look")


class TestParseReason:
    def test_single_tag_hit(self) -> None:
        assert parse_reason("plastic look") == {"plastic_look"}

    def test_multi_tag_hit(self) -> None:
        tags = parse_reason("plastic look, flat lighting")
        assert tags == {"plastic_look", "flat_light"}

    def test_case_insensitive(self) -> None:
        assert parse_reason("PLASTIC LOOK") == {"plastic_look"}

    def test_empty_string_returns_empty_set(self) -> None:
        assert parse_reason("") == set()

    def test_no_match_returns_empty_set(self) -> None:
        assert parse_reason("absolutely amazing render") == set()

    def test_returns_set_type(self) -> None:
        result = parse_reason("plastic look")
        assert isinstance(result, set)


class TestParseReasonProperty:
    @given(text=st.text(
        alphabet=string.ascii_letters + string.digits + " .,;-",
        max_size=80,
    ))
    def test_always_returns_set_subset_of_builtin(self, text: str) -> None:
        # TRAP-3 alphabet 限定为 jury 实际输出字符集
        result = parse_reason(text)
        assert isinstance(result, set)
        assert result <= BUILTIN_TAGS

    @given(text=st.text(
        alphabet=string.ascii_letters + " ",
        max_size=80,
    ))
    def test_pure_function_same_input_same_output(self, text: str) -> None:
        assert parse_reason(text) == parse_reason(text)
