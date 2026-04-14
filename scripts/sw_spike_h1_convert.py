"""Phase 3 H1 验证：在无 Toolbox Library add-in 的机器上，
仅靠 OpenDoc6 + SaveAs3 也能把 sldprt 转成 STEP。

流程：
  1. Dispatch SW（不调 LoadAddIn）
  2. OpenDoc6 一个 real sldprt
  3. Extension.SaveAs3 到临时目录
  4. 校验 .step 文件大小 + magic header
  5. ExitApp 清退
"""

from __future__ import annotations

import sys
import tempfile
import time
import traceback
from pathlib import Path

SLDPRT = (
    r"C:\SOLIDWORKS Data\browser\Ansi Inch\bearings\ball bearings"
    r"\instrument ball bearing_ai.sldprt"
)


def main() -> int:
    print(f"[H1] input: {SLDPRT}")
    print(f"[H1] exists: {Path(SLDPRT).exists()}  size: {Path(SLDPRT).stat().st_size if Path(SLDPRT).exists() else 'N/A'}")

    try:
        import win32com.client
    except Exception as e:
        print(f"[H1 FAIL] import win32com: {e}")
        return 1

    t0 = time.monotonic()
    try:
        app = win32com.client.Dispatch("SldWorks.Application")
        app.Visible = False
        print(f"[H1] Dispatch + Visible=False done in {time.monotonic() - t0:.1f}s")
    except Exception as e:
        print(f"[H1 FAIL] Dispatch: {e}")
        traceback.print_exc()
        return 2

    # NOTE: 不调 LoadAddIn！这是本次实验的关键点。

    with tempfile.TemporaryDirectory() as td:
        step_out = str(Path(td) / "out.step")
        print(f"[H1] step_out: {step_out}")

        try:
            # late-bind COM 下 OUT 参数必须以 VARIANT BYREF 传递，
            # 否则 pywin32 报 DISP_E_PARAMNOTOPTIONAL 或 DISP_E_TYPEMISMATCH
            import pythoncom  # noqa: PLC0415
            from win32com.client import VARIANT  # noqa: PLC0415

            err_var = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            warn_var = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            model = app.OpenDoc6(
                SLDPRT,
                1,  # swDocPART
                1,  # swOpenDocOptions_Silent
                "",
                err_var,
                warn_var,
            )
            errors = err_var.value
            warnings = warn_var.value
            print(f"[H1] OpenDoc6 returned model={'<got>' if model else None}, errors={errors}, warnings={warnings}")
            if not model:
                print("[H1 FAIL] model is None — OpenDoc6 无法打开")
                app.ExitApp()
                return 3
        except Exception as e:
            print(f"[H1 FAIL] OpenDoc6 抛异常: {e}")
            traceback.print_exc()
            try:
                app.ExitApp()
            except Exception:
                pass
            return 3

        try:
            import pythoncom  # noqa: PLC0415
            from win32com.client import VARIANT  # noqa: PLC0415

            # IDispatch* 可选参数用 VT_DISPATCH 空值传；OUT Errors/Warnings 用 BYREF I4
            export_var = VARIANT(pythoncom.VT_DISPATCH, None)
            advanced_var = VARIANT(pythoncom.VT_DISPATCH, None)
            err2 = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            warn2 = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            saved = model.Extension.SaveAs3(
                step_out,
                0,  # Version: 0 = current
                1,  # Options: 1 = swSaveAsOptions_Silent
                export_var,
                advanced_var,
                err2,
                warn2,
            )
            print(
                f"[H1] SaveAs3 returned {saved}; "
                f"errors={err2.value} warnings={warn2.value}"
            )
        except Exception as e:
            print(f"[H1 FAIL] SaveAs3 抛异常: {e}")
            traceback.print_exc()
            try:
                app.ExitApp()
            except Exception:
                pass
            return 4

        # 校验
        p = Path(step_out)
        if not p.exists():
            print("[H1 FAIL] step_out 不存在")
            try:
                app.ExitApp()
            except Exception:
                pass
            return 5

        size = p.stat().st_size
        head = p.read_bytes()[:30]
        print(f"[H1] step 文件大小 {size} bytes")
        print(f"[H1] magic head bytes: {head!r}")

        is_step = head.lstrip().startswith(b"ISO-10303")
        print(f"[H1] ISO-10303 magic: {is_step}")

    try:
        app.ExitApp()
        print("[H1] ExitApp OK")
    except Exception as e:
        print(f"[H1 WARN] ExitApp: {e}")

    if size >= 1024 and is_step:
        print("\n>>> H1 成立：无 Toolbox Library add-in，仅靠 OpenDoc6+SaveAs3 成功得到合法 STEP。")
        return 0
    print("\n>>> H1 不成立：需要进一步分析。")
    return 6


if __name__ == "__main__":
    sys.exit(main())
