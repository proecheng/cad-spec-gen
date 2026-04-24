"""
adapters/solidworks/sw_convert_worker.py — 独立进程内做单次 sldprt→STEP 转换。

为什么独立进程：pywin32 的 COM Dispatch 调用（OpenDoc6 / SaveAs3）一旦
进入阻塞（SW-B0 spike 实证，330 个文件中会有 hang 20+ 分钟的坏 part），
threading.Timer / signal 均无法打断——唯一手段是由父进程 kill 子进程。
父进程 `subprocess.run(timeout=...)` 是这个打断机制。

Worker 职责：
- Dispatch → OpenDoc6 → Extension.SaveAs3(tmp_out) → CloseDoc → ExitApp
- 把 STEP 写到 argv[2]（tmp 路径，父进程提供，含 `.tmp.step` 扩展名）
- 不做大小/magic 校验（父进程 validate），不做 atomic rename（父进程 os.replace）

退出码契约：
    0  成功
    2  OpenDoc6 errors 非 0 或返回 null model
    3  SaveAs3 saved=False 或 errors 非 0
    4  任何未预期 Exception（COM 崩溃、pywin32 import 失败等）
    5  config 未找到（ShowConfiguration2 前匹配失败）
    64 命令行参数错误

CLI:
    python -m adapters.solidworks.sw_convert_worker <sldprt_path> <tmp_out_path> [config_name]
"""

from __future__ import annotations

import re
import sys


def _resolve_config(candidate: str, available: list[str]) -> str | None:
    """两步匹配：精确（大小写不敏感）→ 模糊（去 -_/ 空格后比较）。"""
    lower_map = {n.lower(): n for n in available}
    if candidate.lower() in lower_map:
        return lower_map[candidate.lower()]

    def _norm(s: str) -> str:
        return re.sub(r'[-_\s]', '', s).lower()

    norm_map = {_norm(n): n for n in available}
    return norm_map.get(_norm(candidate))


def _convert(sldprt_path: str, tmp_out_path: str,
             target_config: str | None = None) -> int:
    """实际 COM 转换；返回上面契约中的 exit code。"""
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
            app.FrameState = 0  # swWindowState_e.swWindowMinimized=0；数字常量避免依赖 pywin32 gen_py cache

            err_var = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            warn_var = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            model = app.OpenDoc6(sldprt_path, 1, 1, "", err_var, warn_var)
            if err_var.value or model is None:
                print(
                    f"worker: OpenDoc6 errors={err_var.value} "
                    f"warnings={warn_var.value} model={'NULL' if model is None else 'OK'}",
                    file=sys.stderr,
                )
                return 2

            if target_config:
                config_mgr = model.ConfigurationManager
                available = list(config_mgr.GetConfigurationNames())
                matched = _resolve_config(target_config, available)
                if matched is None:
                    print(
                        f"[B-16] config 未匹配: {target_config!r}",
                        file=sys.stderr,
                    )
                    print(f"[B-16] 可用列表: {available}", file=sys.stderr)
                    return 5
                model.ShowConfiguration2(matched)

            try:
                disp_none_a = VARIANT(pythoncom.VT_DISPATCH, None)
                disp_none_b = VARIANT(pythoncom.VT_DISPATCH, None)
                err2 = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                warn2 = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                saved = model.Extension.SaveAs3(
                    tmp_out_path,
                    0,
                    1,
                    disp_none_a,
                    disp_none_b,
                    err2,
                    warn2,
                )
                if not saved or err2.value:
                    print(
                        f"worker: SaveAs3 saved={saved} errors={err2.value}",
                        file=sys.stderr,
                    )
                    return 3
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
    if len(argv) not in (2, 3):
        print(
            "usage: python -m adapters.solidworks.sw_convert_worker "
            "<sldprt_path> <tmp_out_path> [config_name]",
            file=sys.stderr,
        )
        return 64
    target_config = argv[2] if len(argv) == 3 else None
    return _convert(argv[0], argv[1], target_config)


if __name__ == "__main__":
    sys.exit(main())
