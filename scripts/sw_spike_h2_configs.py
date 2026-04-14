"""Phase 1 续：验证 GB sldprt 是配置多态零件假设。

对一个 GB 文件：
  1. 列出其所有 configuration
  2. 不指定 config 尝试 SaveAs3（预期 errors=256）
  3. 指定第一个 config 再 SaveAs3（验证能否走通）

若第 3 步成功 → 根因确认：需在 OpenDoc6 / SaveAs3 前先激活 config。
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

SLDPRT_GB = (
    r"C:\SOLIDWORKS Data\browser\GB\bearing\rolling bearings"
    r"\angular contact ball bearings gb.sldprt"
)


def main() -> int:
    import pythoncom
    import win32com.client
    from win32com.client import VARIANT

    print(f"[H2] file: {SLDPRT_GB}")
    print(f"[H2] size: {Path(SLDPRT_GB).stat().st_size} bytes")

    app = win32com.client.Dispatch("SldWorks.Application")
    app.Visible = False

    # 1. 打开 part（Configuration 字段留空）
    err = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warn = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    model = app.OpenDoc6(SLDPRT_GB, 1, 1, "", err, warn)
    print(
        f"[H2] OpenDoc6: model={'OK' if model else 'NULL'}, errors={err.value}, warnings={warn.value}"
    )
    if not model:
        return 1

    # 2. 列 configurations
    try:
        names = model.GetConfigurationNames()
        print(f"[H2] configurations ({len(names) if names else 0}):")
        if names:
            for n in names[:10]:
                print(f"    - {n}")
            if len(names) > 10:
                print(f"    ... 其余 {len(names) - 10} 个")
        active = model.GetConfigurationCount
        print(f"[H2] GetConfigurationCount: {active}")
    except Exception as e:
        print(f"[H2] GetConfigurationNames failed: {e}")

    # 3. 当前 active config
    try:
        active_cfg = model.GetActiveConfiguration().Name
        print(f"[H2] active configuration: {active_cfg!r}")
    except Exception as e:
        print(f"[H2] GetActiveConfiguration failed: {e}")

    # 4. 尝试 SaveAs3 without config switch (expect fail 256)
    with tempfile.TemporaryDirectory() as td:
        step_out = str(Path(td) / "gb_no_config.step")
        export_var = VARIANT(pythoncom.VT_DISPATCH, None)
        advanced_var = VARIANT(pythoncom.VT_DISPATCH, None)
        err2 = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        warn2 = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        saved = model.Extension.SaveAs3(
            step_out, 0, 1, export_var, advanced_var, err2, warn2
        )
        print(f"[H2] SaveAs3(no active switch): saved={saved}, errors={err2.value}")

        # 5. 如果有 configs，切到第一个然后再 SaveAs3
        if names:
            cfg_name = names[0]
            print(f"[H2] activating config {cfg_name!r} ...")
            rc = model.ShowConfiguration2(cfg_name)
            print(f"[H2] ShowConfiguration2 rc={rc}")

            step_out2 = str(Path(td) / "gb_with_config.step")
            err3 = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            warn3 = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            saved2 = model.Extension.SaveAs3(
                step_out2,
                0,
                1,
                VARIANT(pythoncom.VT_DISPATCH, None),
                VARIANT(pythoncom.VT_DISPATCH, None),
                err3,
                warn3,
            )
            print(
                f"[H2] SaveAs3(after config activate): saved={saved2}, errors={err3.value}"
            )
            if Path(step_out2).exists():
                sz = Path(step_out2).stat().st_size
                head = Path(step_out2).read_bytes()[:30]
                print(f"[H2] step size {sz}, head {head!r}")
                print(
                    f"\n>>> H2 {'成立' if sz > 1024 and head.lstrip().startswith(b'ISO-10303') else '不成立'}"
                )

    # 清理
    try:
        app.CloseDoc(model.GetTitle())
    except Exception:
        pass
    try:
        app.ExitApp()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
