"""tools/assert_sw_inspect_schema.py 的单元测试（D13，spec §4.6）。

覆盖场景：
1. 合法 fast 模式 JSON 通过
2. 合法 deep 模式 JSON 通过
3. 缺顶层 key（version / generated_at / mode / overall / layers）抛 AssertionError
4. overall 缺 severity / exit_code / elapsed_ms 抛 AssertionError
5. deep 模式缺必需 layer 抛 AssertionError
6. deep 模式 dispatch.data 缺 elapsed_ms 抛 AssertionError（F-4a baseline 消费字段）

fixtures 的 shape 对齐 tools/sw_inspect.py:165-181 真实 payload
（v3 spec §4.6 凭想当然的列表已在 F-1.3 final review 后对齐）。
"""

from __future__ import annotations

import json
import pytest

from tools.assert_sw_inspect_schema import assert_schema_v1


# ---- fixtures ----


def _sample_fast() -> dict:
    """合法 fast 模式 payload：7 层 probe，无 dispatch/loadaddin。"""
    return {
        "version": "1",
        "generated_at": "2026-04-17T12:00:00Z",
        "mode": "fast",
        "overall": {
            "ok": True,
            "severity": "ok",
            "exit_code": 0,
            "warning_count": 0,
            "fail_count": 0,
            "elapsed_ms": 120,
            "summary": "ok",
        },
        "layers": {
            layer: {
                "ok": True,
                "severity": "ok",
                "summary": "ok",
                "data": {},
            }
            for layer in (
                "environment",
                "pywin32",
                "detect",
                "clsid",
                "toolbox_index",
                "materials",
                "warmup",
            )
        },
    }


def _sample_deep() -> dict:
    """合法 deep 模式 payload：fast 7 层 + dispatch + loadaddin。"""
    payload = _sample_fast()
    payload["mode"] = "deep"
    payload["layers"]["dispatch"] = {
        "ok": True,
        "severity": "ok",
        "summary": "ok",
        "data": {"elapsed_ms": 12345, "dispatched": True},
    }
    payload["layers"]["loadaddin"] = {
        "ok": True,
        "severity": "ok",
        "summary": "ok",
        "data": {},
    }
    return payload


# ---- tests ----


class TestAssertSchemaV1:
    def test_valid_fast_passes(self, tmp_path):
        p = tmp_path / "fast.json"
        p.write_text(json.dumps(_sample_fast()), encoding="utf-8")
        assert_schema_v1(p)  # 不抛即通过

    def test_valid_deep_passes(self, tmp_path):
        p = tmp_path / "deep.json"
        p.write_text(json.dumps(_sample_deep()), encoding="utf-8")
        assert_schema_v1(p)

    @pytest.mark.parametrize(
        "missing_key", ["version", "generated_at", "mode", "overall", "layers"]
    )
    def test_missing_top_key_fails(self, tmp_path, missing_key):
        doc = _sample_fast()
        del doc[missing_key]
        p = tmp_path / "bad.json"
        p.write_text(json.dumps(doc), encoding="utf-8")
        with pytest.raises(AssertionError, match=missing_key):
            assert_schema_v1(p)

    @pytest.mark.parametrize("missing_field", ["severity", "exit_code", "elapsed_ms"])
    def test_overall_missing_field_fails(self, tmp_path, missing_field):
        """overall 子字段缺失（含 F-4a baseline 候选 elapsed_ms）必须显式 fail。"""
        doc = _sample_fast()
        del doc["overall"][missing_field]
        p = tmp_path / "bad.json"
        p.write_text(json.dumps(doc), encoding="utf-8")
        with pytest.raises(AssertionError, match=missing_field):
            assert_schema_v1(p)

    def test_deep_missing_layer_fails(self, tmp_path):
        doc = _sample_deep()
        del doc["layers"]["dispatch"]
        p = tmp_path / "bad.json"
        p.write_text(json.dumps(doc), encoding="utf-8")
        with pytest.raises(AssertionError, match="dispatch"):
            assert_schema_v1(p)

    def test_deep_missing_dispatch_elapsed_ms_fails(self, tmp_path):
        """F-4a baseline 主要消费字段 dispatch.data.elapsed_ms 缺失必须显式 fail。"""
        doc = _sample_deep()
        del doc["layers"]["dispatch"]["data"]["elapsed_ms"]
        p = tmp_path / "bad.json"
        p.write_text(json.dumps(doc), encoding="utf-8")
        with pytest.raises(AssertionError, match="elapsed_ms"):
            assert_schema_v1(p)

    def test_fast_mode_allows_missing_dispatch_loadaddin(self, tmp_path):
        """fast 模式不应要求 deep-only 的两层。"""
        doc = _sample_fast()
        # fast 没有 dispatch / loadaddin 是合法的
        p = tmp_path / "fast.json"
        p.write_text(json.dumps(doc), encoding="utf-8")
        assert_schema_v1(p)  # 不抛
