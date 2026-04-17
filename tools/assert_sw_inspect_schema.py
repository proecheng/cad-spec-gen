"""断言 sw-inspect --json 输出符合 v1 schema（决策 #38）。

workflow / CI / 任何机读消费方统一调用此脚本而非自己写断言。
schema 升级到 v2 时只改本文件。

schema v1 真实字段来自 tools/sw_inspect.py:165-181 的 payload 构造，
非 spec §4.6 原文（v3 spec §4.6 的常量列表凭想当然，2026-04-17 F-1.3
final review 发现并对齐真实输出）：

payload = {
    "version":       _SCHEMA_VERSION,        # str
    "generated_at":  ISO 8601 UTC Z,         # str
    "mode":          "fast" | "deep",
    "overall": {
        "ok":            bool,
        "severity":      "ok"|"warn"|"fail",
        "exit_code":     int,
        "warning_count": int,
        "fail_count":    int,
        "elapsed_ms":    int,                # 总耗时（F-4a baseline 候选 #2）
        "summary":       str,
    },
    "layers": {
        "<layer_name>": {
            "ok":       bool,
            "severity": "ok"|"warn"|"fail",
            "summary":  str,
            "data":     dict,
            "error":    str,     # 可选
            "hint":     str,     # 可选
        },
        ...  # fast=7 层，deep=9 层；layer 名由 key 表达，不在 value dict 里
    },
}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


REQUIRED_TOP_KEYS = ("version", "generated_at", "mode", "overall", "layers")
REQUIRED_OVERALL_FIELDS = ("severity", "exit_code", "elapsed_ms")
REQUIRED_LAYERS_FAST = (
    "environment",
    "pywin32",
    "detect",
    "clsid",
    "toolbox_index",
    "materials",
    "warmup",
)
REQUIRED_LAYERS_DEEP = REQUIRED_LAYERS_FAST + ("dispatch", "loadaddin")
REQUIRED_LAYER_FIELDS = ("ok", "severity", "summary", "data")


def assert_schema_v1(path: Path) -> None:
    """对 path 指向的 sw-inspect JSON 做 v1 schema 断言。

    Raises:
        AssertionError: schema 不符合 v1 时，消息包含具体缺失字段名。
    """
    doc = json.loads(Path(path).read_text(encoding="utf-8"))

    for k in REQUIRED_TOP_KEYS:
        assert k in doc, f"缺顶层字段 {k!r}"

    # overall 子字段：severity / exit_code / elapsed_ms（F-4a baseline 候选字段）
    overall = doc["overall"]
    for f in REQUIRED_OVERALL_FIELDS:
        assert f in overall, f"overall 缺字段 {f!r}"

    mode = doc["mode"]
    layers = doc["layers"]
    required = REQUIRED_LAYERS_DEEP if mode == "deep" else REQUIRED_LAYERS_FAST
    for layer_name in required:
        assert layer_name in layers, f"mode={mode} 缺 layer {layer_name!r}"
        for field in REQUIRED_LAYER_FIELDS:
            assert field in layers[layer_name], f"layer {layer_name} 缺字段 {field!r}"

    # deep 模式：dispatch.data.elapsed_ms 是 F-4a baseline 主要消费字段（Dispatch 冷启耗时）
    if mode == "deep":
        assert "elapsed_ms" in layers["dispatch"]["data"], (
            "deep 模式 dispatch.data 缺 elapsed_ms（F-4a baseline 消费字段）"
        )


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <sw-inspect-json-path>", file=sys.stderr)
        return 64
    assert_schema_v1(Path(argv[1]))
    print(f"schema v1 OK: {argv[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
