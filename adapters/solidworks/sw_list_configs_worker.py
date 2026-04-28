"""adapters/solidworks/sw_list_configs_worker.py — 独立子进程列出 SLDPRT 的所有配置名。

Task 14.6：加 --batch 模式（stdin JSON list → stdout JSON list of {path, configs}），
保留单件 CLI 模式（python -m ... <sldprt_path>）兼容（broker fallback 路径仍调单件）。

退出码契约（spec §3.1.2，M-2/M-4 cleanup PR 生效）：
    0  EXIT_OK — 成功（stdout 输出 JSON）
    2  EXIT_TERMINAL — 重试仍失败（SLDPRT 损坏 / pywin32 未装 / 已知 terminal 错误）
    3  EXIT_TRANSIENT — 重试可能成功（资源不足 / COM 暂断 / 未识别异常兜底）
    64 EXIT_USAGE — 命令行参数错误 / batch stdin 非合法 JSON
注：rc=4 已在本 PR 废弃（分流到 rc=2/3）；broker 端保留 WORKER_EXIT_LEGACY=4 兜底旧 worker 进程。

CLI:
    python -m adapters.solidworks.sw_list_configs_worker <sldprt_path>
    python -m adapters.solidworks.sw_list_configs_worker --batch < paths.json
"""

from __future__ import annotations

import json
import sys


class OpenDocFailure(RuntimeError):
    """OpenDoc6 失败带结构化字段；分类按 errors 数值走，不解析字符串。

    spec §3.1.3 引入：替代原 RuntimeError("OpenDoc6 errors=N ...") 字符串包装，
    让 _classify_worker_exception 按 e.errors 字段分流。

    向后兼容：仍是 RuntimeError 子类，所有现有 except RuntimeError 不破。
    """

    def __init__(self, errors: int, warnings: int, model_was_null: bool):
        self.errors = errors
        self.warnings = warnings
        self.model_was_null = model_was_null
        super().__init__(
            f"OpenDoc6 errors={errors} warnings={warnings} "
            f"model={'NULL' if model_was_null else 'OK'}"
        )


# spec §3.1.2 退出码合约
EXIT_OK = 0
EXIT_TERMINAL = 2
EXIT_TRANSIENT = 3
EXIT_USAGE = 64
# 注：EXIT_LEGACY=4 仅 broker 端定义（WORKER_EXIT_LEGACY），worker 不再产出此值
# spec rev 5 B2 修：worker 端不要列 EXIT_LEGACY 常量

# spec §3.1.4 swFileLoadError transient 数值集合
# 来源：plan task 0 本机 SW 2024 swconst.tlb 校准真值（spec rev 6）
_TRANSIENT_OPENDOC_ERRORS: frozenset[int] = frozenset({
    65536,    # swFileWithSameTitleAlreadyOpen — 同名文件已开
    262144,   # swLowResourcesError — 资源不足 / 内存压力（注：复数 Resources）
    8388608,  # swApplicationBusy — SW 进程忙（典型 boot 中）
})

# spec §3.1.5 已知 transient COM hresult
_TRANSIENT_COM_HRESULTS: frozenset[int] = frozenset({
    -2147023170,  # RPC_E_DISCONNECTED — RPC 服务器不可用
    -2147418113,  # E_FAIL — 通用失败保守归 transient
    -2147023174,  # RPC_S_CALL_FAILED — 调用瞬时中断
})


def _classify_worker_exception(e: BaseException) -> int:
    """worker 端异常分类的唯一入口；单件 + batch 共享调用（DRY，spec §3.1.6 / I12）。

    返回 EXIT_TERMINAL (2) / EXIT_TRANSIENT (3)。
    KeyboardInterrupt / SystemExit 不应进入此函数 — caller 必须先 raise。
    """
    if isinstance(e, OpenDocFailure):
        if e.errors in _TRANSIENT_OPENDOC_ERRORS:
            return EXIT_TRANSIENT
        return EXIT_TERMINAL  # 含未识别 errors 值 + null model 边角

    if isinstance(e, ImportError):
        return EXIT_TERMINAL  # pywin32 没装是部署问题，重试不会变

    # pythoncom.com_error 仅在 worker 已 import pythoncom 后才能 isinstance 检查
    try:
        import pythoncom
        # type guard 防御 mock pythoncom（缺 com_error / com_error 非类型）+ 真实 unload 边角
        com_error = getattr(pythoncom, "com_error", None)
        if isinstance(com_error, type) and isinstance(e, com_error):
            hresult = getattr(e, "hresult", None) or (e.args[0] if e.args else None)
            return EXIT_TRANSIENT if hresult in _TRANSIENT_COM_HRESULTS else EXIT_TERMINAL
    except ImportError:
        # rev 3 M4 注：理论 dead code — _list_configs_returning 已 import pythoncom，
        # 此处 import 不会失败。保留作防御：worker 启动后 pythoncom 异常 unload 边角。
        pass

    # 兜底：未识别 Exception 归 transient（避免 worker 自身 bug 永久污染 cache）
    return EXIT_TRANSIENT


def _member_value(obj, name: str):
    """Return COM member value, accepting method or late-bound property forms."""
    member = getattr(obj, name)
    return member() if callable(member) else member


def _config_names_from(obj) -> list[str] | None:
    getter = getattr(obj, "GetConfigurationNames", None)
    if getter is None:
        return None
    names = getter() if callable(getter) else getter
    if names is None:
        return None
    try:
        return [str(name) for name in names]
    except TypeError:
        return None


def _get_configuration_names(model) -> list[str]:
    """Return configuration names from the stable ModelDoc2 API.

    SolidWorks exposes GetConfigurationNames on ModelDoc2. Some historical
    mocks and COM wrappers expose the same name through ConfigurationManager,
    so keep that as a fallback.
    """
    model_names = _config_names_from(model)
    if model_names:
        return model_names

    config_mgr = getattr(model, "ConfigurationManager", None)
    if config_mgr is not None:
        mgr_names = _config_names_from(config_mgr)
        if mgr_names is not None:
            return mgr_names

    if model_names is not None:
        return model_names
    raise AttributeError("GetConfigurationNames not available on ModelDoc2")


def _model_path_name(model, fallback: str) -> str:
    try:
        path_name = _member_value(model, "GetPathName")
    except Exception:
        return fallback
    return str(path_name or fallback)


def _open_doc_get_configs(app, sldprt_path: str) -> list[str]:
    """共享 primitive：在已 boot 的 app 上 OpenDoc6 取配置名 CloseDoc。

    单件 + batch 都用此函数，差别仅在 SW lifecycle 谁管。失败抛 RuntimeError。
    """
    import pythoncom
    from win32com.client import VARIANT

    err_var = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warn_var = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    model = app.OpenDoc6(sldprt_path, 1, 1, "", err_var, warn_var)
    if err_var.value or model is None:
        raise OpenDocFailure(
            errors=err_var.value,
            warnings=warn_var.value,
            model_was_null=model is None,
        )
    try:
        return _get_configuration_names(model)
    finally:
        try:
            app.CloseDoc(_model_path_name(model, sldprt_path))
        except Exception as e:
            print(f"worker: CloseDoc ignored: {e!r}", file=sys.stderr)


def _list_configs_returning(sldprt_path: str) -> list[str]:
    """单件路径：自管 SW lifecycle（CoInit + Dispatch + ExitApp + CoUninit）。

    保留向后兼容（broker 单件 fallback 路径仍调此函数）。失败抛 RuntimeError。
    """
    import pythoncom
    from win32com.client import DispatchEx

    pythoncom.CoInitialize()
    try:
        app = DispatchEx("SldWorks.Application")
        try:
            app.Visible = False
            app.UserControl = False
            app.FrameState = 0
            return _open_doc_get_configs(app, sldprt_path)
        finally:
            try:
                app.ExitApp()
            except Exception as e:
                print(f"worker: ExitApp ignored: {e!r}", file=sys.stderr)
    finally:
        pythoncom.CoUninitialize()


def _list_configs(sldprt_path: str) -> int:
    """单件 CLI 模式入口：返 exit code，stdout 打印 JSON list of strings.

    spec §3.1.7：所有异常喂给 _classify_worker_exception 分流（DRY，I12）。
    """
    try:
        names = _list_configs_returning(sldprt_path)
        print(json.dumps(names, ensure_ascii=False))
        return EXIT_OK
    except (KeyboardInterrupt, SystemExit):
        raise  # 永不当作可恢复错误吞掉
    except BaseException as e:
        print(f"worker: {type(e).__name__}: {e!r}", file=sys.stderr)
        return _classify_worker_exception(e)


def _run_batch_mode() -> int:
    """--batch：从 stdin 读 JSON list of sldprt_path → **真正一次** boot SW →
    loop _open_doc_get_configs → 一次 ExitApp。

    单件失败（OpenDoc6 fail / 任何异常）→ configs=[] 不阻其他件；整 batch exit 0。
    空 list → 不 boot SW（早返）避免无谓启动。
    """
    try:
        sldprt_list = json.load(sys.stdin)
        if not isinstance(sldprt_list, list):
            print("worker --batch: stdin must be JSON list", file=sys.stderr)
            return 64
    except json.JSONDecodeError as e:
        print(f"worker --batch: invalid stdin JSON: {e}", file=sys.stderr)
        return 64

    if not sldprt_list:
        print(json.dumps([], ensure_ascii=False))
        return 0

    try:
        import pythoncom
        from win32com.client import DispatchEx
    except ImportError as e:
        print(f"worker --batch: pywin32 import failed: {e!r}", file=sys.stderr)
        # rev 4 A1：emit per-entry transient/terminal stdout 让 broker 走 entry 分流
        # 防整批 fallthrough M-4 失效
        print(json.dumps([
            {"path": p, "configs": [], "exit_code": EXIT_TERMINAL}
            for p in sldprt_list
        ], ensure_ascii=False))
        return EXIT_OK

    pythoncom.CoInitialize()
    try:
        try:
            app = DispatchEx("SldWorks.Application")
        except pythoncom.com_error as e:
            # rev 4 A1：DispatchEx 失败也透 entry-level rc
            print(f"worker --batch: DispatchEx failed: {e!r}", file=sys.stderr)
            print(json.dumps([
                {"path": p, "configs": [], "exit_code": _classify_worker_exception(e)}
                for p in sldprt_list
            ], ensure_ascii=False))
            return EXIT_OK
        try:
            app.Visible = False
            app.UserControl = False
            app.FrameState = 0

            results = []
            for sldprt_path in sldprt_list:
                try:
                    configs = _open_doc_get_configs(app, sldprt_path)
                    exit_code = EXIT_OK
                except (KeyboardInterrupt, SystemExit):
                    raise
                except BaseException as e:
                    print(
                        f"worker --batch: {sldprt_path} failed: "
                        f"{type(e).__name__}: {e!r}",
                        file=sys.stderr,
                    )
                    configs = []
                    exit_code = _classify_worker_exception(e)
                results.append({
                    "path": sldprt_path,
                    "configs": configs,
                    "exit_code": exit_code,  # 新增字段（spec §3.3）
                })

            print(json.dumps(results, ensure_ascii=False))
            return EXIT_OK
        finally:
            try:
                app.ExitApp()
            except Exception as e:
                print(f"worker --batch: ExitApp ignored: {e!r}", file=sys.stderr)
    finally:
        pythoncom.CoUninitialize()


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
