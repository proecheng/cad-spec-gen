"""SW-B0 spike 诊断脚本（薄壳版）—— 委托 adapters.solidworks.sw_probe。

历史兜底工具：当 `cad_pipeline.py sw-inspect --deep` 出问题时在此直跑最底层。
一般用户优先用 CLI；本脚本保留为 SW-B0 时期 REPL 友好的调试入口。

退出码（与 CLI sw-inspect 独立，保留历史语义）：
  0 = 全绿
  1 = probe_pywin32 fail
  2 = probe_detect fail
  3 = probe_clsid fail
  4 = probe_dispatch fail
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from adapters.solidworks import sw_probe  # noqa: E402


_ICON = {"ok": "[OK]  ", "warn": "[WARN]", "fail": "[FAIL]"}


def _print(r) -> None:
    print(f"{_ICON[r.severity]} {r.layer:12s} {r.summary}")
    if r.hint:
        print(f"       ↪ {r.hint}")
    if r.error:
        print(f"       ! {r.error}")


def main() -> int:
    print("=" * 60)
    print("SW-B0 spike diagnose — 逐层边界探测（薄壳；委托 sw_probe）")
    print("=" * 60)

    # probe_detect 返回 tuple (ProbeResult, SwInfo)，spike 只消费 ProbeResult
    probes = [
        (sw_probe.probe_pywin32, 1),
        (lambda: sw_probe.probe_detect()[0], 2),
        (sw_probe.probe_clsid, 3),
        (sw_probe.probe_dispatch, 4),
        (sw_probe.probe_loadaddin, None),  # 不早退
    ]
    for probe_fn, exit_on_fail in probes:
        r = probe_fn()
        _print(r)
        if r.severity == "fail" and exit_on_fail is not None:
            return exit_on_fail

    print("\n" + "=" * 60)
    print("诊断完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
