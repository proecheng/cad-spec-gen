"""adapters/solidworks/sw_list_configs_worker.py — 独立子进程列出 SLDPRT 的所有配置名。

Task 14.6：加 --batch 模式（stdin JSON list → stdout JSON list of {path, configs}），
保留单件 CLI 模式（python -m ... <sldprt_path>）兼容（broker fallback 路径仍调单件）。

退出码契约：
    0  成功（stdout 输出 JSON）
    2  OpenDoc6 errors 非 0 或返回 null model（仅单件模式）
    4  任何未预期 Exception（COM 崩溃、pywin32 import 失败等，仅单件模式）
    64 命令行参数错误 / batch stdin 非合法 JSON

CLI:
    python -m adapters.solidworks.sw_list_configs_worker <sldprt_path>
    python -m adapters.solidworks.sw_list_configs_worker --batch < paths.json
"""

from __future__ import annotations

import json
import sys


def _list_configs_returning(sldprt_path: str) -> list[str]:
    """返 SLDPRT configurations list；失败抛 RuntimeError 给调用方处理。

    与 _list_configs 不同：不打印 stdout / 不返 exit code，纯函数。
    单件 CLI 模式包此函数 + 退出码契约；batch 模式直接调此函数收集结果。
    """
    import pythoncom
    from win32com.client import VARIANT, DispatchEx

    pythoncom.CoInitialize()
    try:
        app = DispatchEx("SldWorks.Application")
        try:
            app.Visible = False
            app.UserControl = False
            app.FrameState = 0

            err_var = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            warn_var = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            model = app.OpenDoc6(sldprt_path, 1, 1, "", err_var, warn_var)
            if err_var.value or model is None:
                raise RuntimeError(
                    f"OpenDoc6 errors={err_var.value} "
                    f"warnings={warn_var.value} "
                    f"model={'NULL' if model is None else 'OK'}"
                )
            try:
                config_mgr = model.ConfigurationManager
                return list(config_mgr.GetConfigurationNames())
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
    finally:
        pythoncom.CoUninitialize()


def _list_configs(sldprt_path: str) -> int:
    """单件 CLI 模式入口：返 exit code，stdout 打印 JSON list of strings。

    保留向后兼容（broker._list_configs_via_com fallback 路径仍调此模式）。
    """
    try:
        try:
            import pythoncom  # noqa: F401
            import win32com.client  # noqa: F401
        except ImportError as e:
            print(f"worker: pywin32 import failed: {e!r}", file=sys.stderr)
            return 4
        try:
            names = _list_configs_returning(sldprt_path)
        except RuntimeError as e:
            # 区分 OpenDoc6 失败 (rc=2) vs 其他 RuntimeError (rc=4)
            print(f"worker: {e}", file=sys.stderr)
            if "OpenDoc6" in str(e):
                return 2
            return 4
        print(json.dumps(names, ensure_ascii=False))
        return 0
    except Exception as e:
        print(f"worker: unexpected exception: {e!r}", file=sys.stderr)
        return 4


def _run_batch_mode() -> int:
    """--batch：从 stdin 读 JSON list of sldprt_path → 启 SW 一次 → 逐件
    调 _list_configs_returning → stdout 输出 JSON list of {path, configs}。

    单件失败（RuntimeError / 任何异常）→ configs=[] 不阻其他件；整 batch exit 0。
    """
    try:
        sldprt_list = json.load(sys.stdin)
        if not isinstance(sldprt_list, list):
            print("worker --batch: stdin must be JSON list", file=sys.stderr)
            return 64
    except json.JSONDecodeError as e:
        print(f"worker --batch: invalid stdin JSON: {e}", file=sys.stderr)
        return 64

    results = []
    for sldprt_path in sldprt_list:
        try:
            configs = _list_configs_returning(sldprt_path)
        except Exception as e:
            print(
                f"worker --batch: {sldprt_path} failed: {e!r}",
                file=sys.stderr,
            )
            configs = []
        results.append({"path": sldprt_path, "configs": configs})

    print(json.dumps(results, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    if len(argv) == 1 and argv[0] == "--batch":
        return _run_batch_mode()

    if len(argv) == 1:
        return _list_configs(argv[0])

    print(
        "usage: python -m adapters.solidworks.sw_list_configs_worker <sldprt_path>\n"
        "       python -m adapters.solidworks.sw_list_configs_worker --batch < paths.json",
        file=sys.stderr,
    )
    return 64


if __name__ == "__main__":
    sys.exit(main())
