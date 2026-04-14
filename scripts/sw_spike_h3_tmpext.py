"""H3 验证：SaveAs3 对扩展名敏感（.step.tmp → errors=256）。"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

SLDPRT = (
    r"C:\SOLIDWORKS Data\browser\GB\bearing\rolling bearings"
    r"\angular contact ball bearings gb.sldprt"
)


def main() -> int:
    import pythoncom
    import win32com.client
    from win32com.client import VARIANT

    app = win32com.client.Dispatch("SldWorks.Application")
    app.Visible = False

    err = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warn = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    model = app.OpenDoc6(SLDPRT, 1, 1, "", err, warn)
    print(
        f"[H3] OpenDoc6 errors={err.value} warnings={warn.value} model={'OK' if model else 'NULL'}"
    )
    if not model:
        return 1

    with tempfile.TemporaryDirectory() as td:
        # 变体 A：.step.tmp（生产代码当前用法）
        p_a = str(Path(td) / "out.step.tmp")
        # 变体 B：.tmp.step（扩展名保持 .step）
        p_b = str(Path(td) / "out.tmp.step")
        # 变体 C：.step（直接）
        p_c = str(Path(td) / "out.step")

        for label, path in [
            ("A (.step.tmp)", p_a),
            ("B (.tmp.step)", p_b),
            ("C (.step)", p_c),
        ]:
            e = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            w = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            saved = model.Extension.SaveAs3(
                path,
                0,
                1,
                VARIANT(pythoncom.VT_DISPATCH, None),
                VARIANT(pythoncom.VT_DISPATCH, None),
                e,
                w,
            )
            sz = Path(path).stat().st_size if Path(path).exists() else 0
            print(f"[H3 {label}] saved={saved} errors={e.value} size={sz}")

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
