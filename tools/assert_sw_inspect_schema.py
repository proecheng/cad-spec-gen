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

# F-1.3l Phase 1 Task 9：per_step_ms 4 段必填 + dispatch.data 扩展
REQUIRED_DISPATCH_DATA_FIELDS = ("elapsed_ms", "per_step_ms", "attached_existing_session")
REQUIRED_PER_STEP_FIELDS = ("dispatch_ms", "revision_ms", "visible_ms", "exitapp_ms")


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

    # deep 模式：dispatch.data 扩展字段（F-1.3l Phase 1 Task 9）
    if mode == "deep":
        d = layers["dispatch"]["data"]
        for f in REQUIRED_DISPATCH_DATA_FIELDS:
            assert f in d, f"deep 模式 dispatch.data 缺 {f!r}（F-1.3l 扩展）"

        per_step = d["per_step_ms"]
        assert isinstance(per_step, dict), (
            f"dispatch.data.per_step_ms 必须是 dict，实际 {type(per_step).__name__}"
        )
        for step in REQUIRED_PER_STEP_FIELDS:
            assert step in per_step, f"per_step_ms 缺 {step!r}"
            assert isinstance(per_step[step], int), (
                f"per_step_ms.{step} 必须是 int，实际 {type(per_step[step]).__name__}"
            )


def main(argv: list[str]) -> int:
    """CLI 入口。

    退出码：
      0  = schema 合规
      1  = schema 不合规（AssertionError）
      64 = 用法错误（参数缺失）
      65 = JSON parse 失败（DATAERR，sysexits 标准；F-1.3j+k S2 commit 1 新增）
    """
    if len(argv) != 2:
        print(f"usage: {argv[0]} <sw-inspect-json-path>", file=sys.stderr)
        return 64

    path = Path(argv[1])
    try:
        # 关键：把原 assert_schema_v1 调用包在 JSONDecodeError 守卫里
        # 不动 assert_schema_v1 函数本身（继承 v3 L3 P3#2 决策）
        assert_schema_v1(path)
    except json.JSONDecodeError as e:
        # stderr 文案强制 ASCII：项目 PYTHONIOENCODING=utf-8 注入子进程，
        # 但 subprocess.run(text=True) 父端按 locale (Windows=GBK) 解码，
        # UTF-8 中文字节会触发父端 UnicodeDecodeError → stderr=None。
        # 中文留在代码注释里供人读，stderr 给消费方机读用 ASCII。
        # 含 "JSONDecodeError" 关键字便于 grep 与测试断言。
        # M1 fix（v3 L3 P3#2 + Task 4 follow-up）：read_bytes 二次失败不应吞掉
        # 原始 JSONDecodeError——若 .pytest_cache 锁 / 文件被删致 OSError，
        # 父进程仅见 traceback 而非 retcode 65 + 友好 stderr，CI 可观测性丢失。
        try:
            preview = path.read_bytes()[:200]
        except OSError as read_err:
            # fallback 字符串编码为 ASCII bytes 保持类型一致（既存逻辑用 !r repr bytes）
            preview = f"<read failed: {read_err}>".encode("ascii", errors="replace")
        print(
            f"sw-inspect output is not valid JSON (JSONDecodeError): "
            f"path={path}; err={e}; first 200 bytes={preview!r}",
            file=sys.stderr,
        )
        return 65
    except AssertionError:
        # AssertionError 由 assert_schema_v1 抛出 → 走 Python 默认退出码 1
        # 不在这里 catch，让回溯保留
        raise

    print(f"schema v1 OK: {argv[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
