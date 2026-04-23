"""cad_pipeline.py sw-inspect 子命令实现。

职责：
1. 加载 parts_library registry 得 sw_cfg
2. 顺序调 sw_probe 的 9 条 probe（deep 时额外 2 条）
3. 聚合 ProbeResult → 顶层 payload
4. 按 args.json 分流 JSON/彩色文本输出
5. 按 spec §5.1 计算 exit code
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone

from adapters.solidworks.sw_probe import (
    ProbeResult,
    probe_clsid,
    probe_detect,
    probe_dispatch,
    probe_environment,
    probe_loadaddin,
    probe_material_files,
    probe_pywin32,
    probe_toolbox_index_cache,
    probe_warmup_artifacts,
)

# Part 2c P1：parts_resolver.load_registry 加载 parts_library.default.yaml
# 延迟 import 以便测试 monkeypatch
try:
    from parts_resolver import load_registry
except ImportError:  # pragma: no cover

    def load_registry():  # type: ignore[misc]
        return {}


_SCHEMA_VERSION = "1"


def _layer_dict(r: ProbeResult) -> dict:
    """把 ProbeResult 转成 JSON schema 定义的 layer dict。"""
    d: dict = {
        "ok": r.ok,
        "severity": r.severity,
        "summary": r.summary,
        "data": r.data,
    }
    if r.error is not None:
        d["error"] = r.error
    if r.hint is not None:
        d["hint"] = r.hint
    return d


def _severity_rank(sev: str) -> int:
    """将 severity 字符串映射到整数排名（越大越严重）。"""
    return {"ok": 0, "warn": 1, "fail": 2}[sev]


def _overall_severity(layers: dict) -> str:
    """取所有 layer 中最高 severity。"""
    max_rank = 0
    sev = "ok"
    for layer in layers.values():
        r = _severity_rank(layer["severity"])
        if r > max_rank:
            max_rank, sev = r, layer["severity"]
    return sev


def _exit_code(mode: str, layers: dict) -> int:
    """spec §5.1 退出码表。

    0 — 全部 ok
    1 — 至少一个 warn，无 fail
    2 — 静态层（environment/pywin32/detect/clsid）任意 fail
    3 — deep 模式：dispatch fail
    4 — deep 模式：loadaddin fail
    """
    static_layers = ("environment", "pywin32", "detect", "clsid")
    for name in static_layers:
        if name in layers and layers[name]["severity"] == "fail":
            return 2
    if mode == "deep":
        if layers.get("dispatch", {}).get("severity") == "fail":
            return 3
        if layers.get("loadaddin", {}).get("severity") == "fail":
            return 4
    sev = _overall_severity(layers)
    if sev == "warn":
        return 1
    return 0


def _print_text(payload: dict) -> None:
    """彩色文本渲染（复用 check_env 风格）。"""
    icon = {"ok": "[OK]  ", "warn": "[WARN]", "fail": "[FAIL]"}
    print(f"=== sw-inspect ({payload['mode']}) ===")
    for name, layer in payload["layers"].items():
        tag = icon[layer["severity"]]
        print(f"{tag} {name:16s} {layer['summary']}")
        if layer.get("hint"):
            print(f"       \u21aa {layer['hint']}")
        if layer.get("error"):
            print(f"       ! {layer['error']}")
    print()
    ov = payload["overall"]
    print(
        f"Overall: {ov['severity']} "
        f"(exit {ov['exit_code']}, elapsed {ov['elapsed_ms']}ms, "
        f"warn={ov['warning_count']} fail={ov['fail_count']})"
    )
    if ov.get("summary"):
        print(f"  {ov['summary']}")


def run_sw_inspect(args: argparse.Namespace) -> int:
    """sw-inspect 主入口。返回退出码。"""
    if getattr(args, "resolve_report", None):
        return _cmd_show_resolve_report(args.resolve_report)

    t_start = time.perf_counter()

    sw_cfg = load_registry().get("solidworks_toolbox", {})

    layers: dict[str, dict] = {}

    r_env = probe_environment()
    layers[r_env.layer] = _layer_dict(r_env)

    r_py = probe_pywin32()
    layers[r_py.layer] = _layer_dict(r_py)

    r_det, info = probe_detect()
    layers[r_det.layer] = _layer_dict(r_det)

    r_cl = probe_clsid()
    layers[r_cl.layer] = _layer_dict(r_cl)

    r_ti = probe_toolbox_index_cache(sw_cfg, info)
    layers[r_ti.layer] = _layer_dict(r_ti)

    r_mat = probe_material_files(info)
    layers[r_mat.layer] = _layer_dict(r_mat)

    r_wm = probe_warmup_artifacts(sw_cfg)
    layers[r_wm.layer] = _layer_dict(r_wm)

    mode = "deep" if getattr(args, "deep", False) else "fast"
    if mode == "deep":
        r_dp = probe_dispatch()
        layers[r_dp.layer] = _layer_dict(r_dp)
        # spec §5.3：dispatch fail 则跳过 loadaddin
        if r_dp.severity != "fail":
            r_la = probe_loadaddin()
            layers[r_la.layer] = _layer_dict(r_la)

    warn_count = sum(1 for lyr in layers.values() if lyr["severity"] == "warn")
    fail_count = sum(1 for lyr in layers.values() if lyr["severity"] == "fail")
    overall_sev = _overall_severity(layers)
    exit_code = _exit_code(mode, layers)
    elapsed_ms = int((time.perf_counter() - t_start) * 1000)

    payload = {
        "version": _SCHEMA_VERSION,
        "generated_at": datetime.now(tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "mode": mode,
        "overall": {
            "ok": overall_sev != "fail",
            "severity": overall_sev,
            "exit_code": exit_code,
            "warning_count": warn_count,
            "fail_count": fail_count,
            "elapsed_ms": elapsed_ms,
            "summary": layers.get("detect", {}).get("summary", ""),
        },
        "layers": layers,
    }

    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_text(payload)

    return exit_code


def _cmd_show_resolve_report(path: str) -> int:
    """打印 resolve_report.json 的路由摘要。"""
    import json
    import sys
    from pathlib import Path

    p = Path(path)
    if not p.is_file():
        print(f"[sw-inspect] resolve_report.json 不存在: {path}", file=sys.stderr)
        return 1

    data = json.loads(p.read_text(encoding="utf-8"))
    schema = data.get("schema_version", "?")
    if schema != 1:
        print(f"[sw-inspect] 未知 schema_version={schema}，展示原始字段")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    print(f"Routing report — run_id: {data.get('run_id', '?')} | "
          f"total_rows: {data.get('total_rows', '?')}")
    print()
    hits = data.get("adapter_hits", {})
    width = max((len(n) for n in hits), default=10)
    for name, hit in hits.items():
        reason = hit.get("unavailable_reason") or ""
        suffix = f"  ← {reason}" if reason else ""
        print(f"  {name:<{width}}  {hit['count']:>4} 命中{suffix}")
    return 0
