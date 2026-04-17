"""断言 sw-inspect --json 输出符合 v1 schema（决策 #38）。

workflow / CI / 任何机读消费方统一调用此脚本而非自己写断言。
schema 升级到 v2 时只改本文件。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


REQUIRED_TOP_KEYS = ("version", "mode", "layers", "overall", "elapsed_ms")
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
REQUIRED_LAYER_FIELDS = ("layer", "ok", "severity", "summary", "data")


def assert_schema_v1(path: Path) -> None:
    """对 path 指向的 sw-inspect JSON 做 v1 schema 断言。

    Raises:
        AssertionError: schema 不符合 v1 时，消息包含具体缺失字段名。
    """
    doc = json.loads(Path(path).read_text(encoding="utf-8"))

    for k in REQUIRED_TOP_KEYS:
        assert k in doc, f"缺顶层字段 {k!r}"

    mode = doc["mode"]
    layers = doc["layers"]
    required = REQUIRED_LAYERS_DEEP if mode == "deep" else REQUIRED_LAYERS_FAST
    for layer_name in required:
        assert layer_name in layers, f"mode={mode} 缺 layer {layer_name!r}"
        for field in REQUIRED_LAYER_FIELDS:
            assert field in layers[layer_name], f"layer {layer_name} 缺字段 {field!r}"

    # deep 模式：dispatch.data.elapsed_ms 是 F-4a baseline 消费字段，必须存在
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
