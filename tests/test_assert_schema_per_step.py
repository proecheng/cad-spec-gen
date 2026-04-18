"""per_step_ms schema 扩展单测（F-1.3l Phase 1 Task 9）。"""

from __future__ import annotations

import json

import pytest

from tools.assert_sw_inspect_schema import assert_schema_v1


def _make_valid_doc() -> dict:
    """构造一个合法的 deep 模式 sw-inspect 文档（F-1.3l 扩展后）。"""
    return {
        "version": "1",
        "generated_at": "2026-04-18T00:00:00Z",
        "mode": "deep",
        "overall": {
            "ok": True,
            "severity": "ok",
            "exit_code": 0,
            "warning_count": 0,
            "fail_count": 0,
            "elapsed_ms": 1000,
            "summary": "",
        },
        "layers": {
            name: {
                "ok": True,
                "severity": "ok",
                "summary": "",
                "data": {},
            }
            for name in (
                "environment",
                "pywin32",
                "detect",
                "clsid",
                "toolbox_index",
                "materials",
                "warmup",
                "loadaddin",
            )
        }
        | {
            "dispatch": {
                "ok": True,
                "severity": "ok",
                "summary": "",
                "data": {
                    "elapsed_ms": 200,
                    "per_step_ms": {
                        "dispatch_ms": 100,
                        "revision_ms": 50,
                        "visible_ms": 30,
                        "exitapp_ms": 20,
                    },
                    "attached_existing_session": False,
                },
            }
        },
    }


class TestSchemaPerStep:
    def test_schema_accepts_valid_per_step(self, tmp_path):
        """合法的 per_step_ms 字段应通过断言。"""
        doc = _make_valid_doc()
        path = tmp_path / "ok.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        assert_schema_v1(path)  # 不抛

    def test_schema_rejects_missing_per_step_field(self, tmp_path):
        """dispatch.data 缺 per_step_ms 子字段应抛 AssertionError。"""
        doc = _make_valid_doc()
        del doc["layers"]["dispatch"]["data"]["per_step_ms"]
        path = tmp_path / "missing.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        with pytest.raises(AssertionError, match="per_step_ms"):
            assert_schema_v1(path)

    def test_schema_rejects_non_int_per_step_value(self, tmp_path):
        """per_step_ms 的值非 int 应抛。"""
        doc = _make_valid_doc()
        doc["layers"]["dispatch"]["data"]["per_step_ms"]["dispatch_ms"] = "100"
        path = tmp_path / "non_int.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        with pytest.raises(AssertionError, match="per_step_ms"):
            assert_schema_v1(path)

    def test_schema_rejects_sum_mismatch_cold_path(self, tmp_path):
        """冷启路径（非 attach / 非异常）总和必须 ≈ elapsed_ms（±50ms）。"""
        doc = _make_valid_doc()
        # per_step 和 = 100+50+30+20 = 200；设 elapsed_ms = 500（差 300ms，超 ±50）
        doc["layers"]["dispatch"]["data"]["elapsed_ms"] = 500
        doc["layers"]["dispatch"]["data"]["attached_existing_session"] = False
        # 让所有 per_step 都 > 0（代表冷启路径，非 timeout / 非异常）
        doc["layers"]["dispatch"]["data"]["per_step_ms"] = {
            "dispatch_ms": 100,
            "revision_ms": 50,
            "visible_ms": 30,
            "exitapp_ms": 20,
        }
        path = tmp_path / "sum_mismatch.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        with pytest.raises(AssertionError, match="per_step.*sum"):
            assert_schema_v1(path)

    def test_schema_accepts_sum_mismatch_exception_path(self, tmp_path):
        """异常路径（某步 = -1 哨兵）总和不等 elapsed_ms 是合法的。"""
        doc = _make_valid_doc()
        doc["layers"]["dispatch"]["data"]["elapsed_ms"] = 200
        # revision_ms = -1 表示"运行但抛异常"，总和含 -1 不可能等 elapsed
        doc["layers"]["dispatch"]["data"]["per_step_ms"] = {
            "dispatch_ms": 100,
            "revision_ms": -1,
            "visible_ms": 30,
            "exitapp_ms": 20,
        }
        path = tmp_path / "exc_path.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        assert_schema_v1(path)  # 不抛（异常路径宽松）

    def test_schema_accepts_attach_path_all_zero(self, tmp_path):
        """attach 路径 per_step 全 0 + elapsed_ms = 0 合法。"""
        doc = _make_valid_doc()
        doc["layers"]["dispatch"]["data"]["elapsed_ms"] = 0
        doc["layers"]["dispatch"]["data"]["attached_existing_session"] = True
        doc["layers"]["dispatch"]["data"]["per_step_ms"] = {
            "dispatch_ms": 0,
            "revision_ms": 0,
            "visible_ms": 0,
            "exitapp_ms": 0,
        }
        path = tmp_path / "attach.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        assert_schema_v1(path)  # 不抛（attach 路径宽松）
