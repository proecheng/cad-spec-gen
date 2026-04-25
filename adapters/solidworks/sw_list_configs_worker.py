"""adapters/solidworks/sw_list_configs_worker.py — 独立子进程列出 SLDPRT 的所有配置名。

复用 sw_convert_worker.py 模式（subprocess + timeout + 退出码契约）。

退出码契约：
    0  成功（stdout 输出 JSON list of strings）
    2  OpenDoc6 errors 非 0 或返回 null model
    4  任何未预期 Exception（COM 崩溃、pywin32 import 失败等）
    64 命令行参数错误

CLI:
    python -m adapters.solidworks.sw_list_configs_worker <sldprt_path>
"""

from __future__ import annotations

import json
import sys


def _list_configs(sldprt_path: str) -> int:
    """返回退出码；成功时 stdout 打印 JSON list。"""
    try:
        import pythoncom
        from win32com.client import VARIANT, DispatchEx
    except ImportError as e:
        print(f"worker: pywin32 import failed: {e!r}", file=sys.stderr)
        return 4

    pythoncom.CoInitialize()
    try:
        try:
            app = DispatchEx("SldWorks.Application")
        except Exception as e:
            print(f"worker: Dispatch failed: {e!r}", file=sys.stderr)
            return 4

        try:
            app.Visible = False
            app.UserControl = False
            app.FrameState = 0

            err_var = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            warn_var = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            model = app.OpenDoc6(sldprt_path, 1, 1, "", err_var, warn_var)
            if err_var.value or model is None:
                print(
                    f"worker: OpenDoc6 errors={err_var.value} model={'NULL' if model is None else 'OK'}",
                    file=sys.stderr,
                )
                return 2

            try:
                config_mgr = model.ConfigurationManager
                names = list(config_mgr.GetConfigurationNames())
                print(json.dumps(names, ensure_ascii=False))
                return 0
            finally:
                try:
                    app.CloseDoc(model.GetPathName())
                except Exception as e:
                    print(f"worker: CloseDoc ignored: {e!r}", file=sys.stderr)
        finally:
            try:
                app.ExitApp()
            except Exception as e:
                print(f"worker: ExitApp ignored: {e!r}", file=sys.stderr)
    except Exception as e:
        print(f"worker: unexpected exception: {e!r}", file=sys.stderr)
        return 4
    finally:
        pythoncom.CoUninitialize()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(
            "usage: python -m adapters.solidworks.sw_list_configs_worker <sldprt_path>",
            file=sys.stderr,
        )
        return 64
    return _list_configs(argv[0])


if __name__ == "__main__":
    sys.exit(main())
