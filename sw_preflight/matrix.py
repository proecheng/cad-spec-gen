"""sw_preflight.matrix — 零配置体验预检矩阵（Task 12）。

按固定顺序跑 7 项检查，遇第一失败短路返回诊断；全过返回 passed=True。
本模块只负责"判定"，不涉及"一键修"（后者在 Task 13+ 的 fix_* 函数）。

7 项检查顺序（CHECK_ORDER）：
    1. platform          — sys.platform == 'win32'
    2. pywin32           — win32com 模块可 import
    3. sw_installed      — detect_solidworks() 报告已安装且目录存在
    4. toolbox_supported — edition ≠ Standard（Standard 不含 Toolbox）
    5. com_healthy       — SldWorks.Application COM 注册可用
    6. addin_enabled     — Toolbox Add-In 在 SW 里启用
    7. toolbox_path      — toolbox_dir 可达（本地 exists 或 UNC 可读）

platform / pywin32 是 SW 检测之前的"前置 gate"，不调 detect_solidworks；
后 5 项均调用 detect_solidworks()，该函数有模块级缓存，实际只查一次。
每个 helper 对 detect 抛异常均 try/except 兜底，返回合适 DiagnosisInfo。
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from sw_preflight.diagnosis import DiagnosisCode, DiagnosisInfo


# ---------------------------------------------------------------------------
# 前置 gate — 不调 detect_solidworks（SW 检测之前跑）
# ---------------------------------------------------------------------------
def _check_platform() -> tuple[bool, Optional[DiagnosisInfo]]:
    """检查 #1：当前平台必须是 Windows。"""
    import sys
    if sys.platform != 'win32':
        return False, DiagnosisInfo(
            code=DiagnosisCode.PLATFORM_NOT_WINDOWS,
            reason=f"本工具仅支持 Windows — 检测到 platform={sys.platform}",
            suggestion="在 Windows 机器上重跑",
            severity='block',
        )
    return True, None


def _check_pywin32() -> tuple[bool, Optional[DiagnosisInfo]]:
    """检查 #2：pywin32 的 win32com 模块必须可导入。"""
    import importlib.util
    if importlib.util.find_spec('win32com') is None:
        return False, DiagnosisInfo(
            code=DiagnosisCode.PYWIN32_MISSING,
            reason="缺 Python 与 SOLIDWORKS 通信组件 (pywin32)",
            suggestion="可一键安装",
            severity='block',
        )
    return True, None


# ---------------------------------------------------------------------------
# SW 相关 check — 调 detect_solidworks()（模块级缓存，实际只查一次）
# ---------------------------------------------------------------------------
def _check_sw_installed() -> tuple[bool, Optional[DiagnosisInfo]]:
    """检查 #3：SolidWorks 已安装且 install_dir 物理存在。"""
    try:
        from adapters.solidworks.sw_detect import detect_solidworks
        info = detect_solidworks()
    except Exception as e:  # noqa: BLE001 — detect 内部任何异常都归为"未检测到"
        return False, DiagnosisInfo(
            code=DiagnosisCode.SW_NOT_INSTALLED,
            reason=f"SolidWorks 检测失败：{e}",
            suggestion="确认已安装 SolidWorks 2021 或更新版本",
            severity='block',
        )
    if not info.installed or not info.install_dir:
        return False, DiagnosisInfo(
            code=DiagnosisCode.SW_NOT_INSTALLED,
            reason="未在注册表中检测到 SolidWorks 安装",
            suggestion="确认已安装 SolidWorks 2021 或更新版本",
            severity='block',
        )
    if not Path(info.install_dir).exists():
        return False, DiagnosisInfo(
            code=DiagnosisCode.SW_NOT_INSTALLED,
            reason=f"注册表 install_dir 指向不存在的目录：{info.install_dir}",
            suggestion="重新安装 SolidWorks 或修复注册表",
            severity='block',
        )
    return True, None


def _check_toolbox_supported() -> tuple[bool, Optional[DiagnosisInfo]]:
    """检查 #4：edition 不是 Standard（Standard 版本不包含 Toolbox）。

    Pro / Premium / unknown（注册表读不到版本级别）均放行，走后续检测；
    仅 Standard 明确判定为 warn，上层走 stand-in 降级流程。
    """
    try:
        from adapters.solidworks.sw_detect import detect_solidworks
        info = detect_solidworks()
    except Exception as e:  # noqa: BLE001
        # detect 失败应由 _check_sw_installed 拦截；此处兜底放行
        return False, DiagnosisInfo(
            code=DiagnosisCode.SW_TOOLBOX_NOT_SUPPORTED,
            reason=f"读取 SolidWorks 版本级别失败：{e}",
            suggestion="可继续使用 stand-in 标准件占位",
            severity='warn',
        )
    if info.edition == 'standard':
        return False, DiagnosisInfo(
            code=DiagnosisCode.SW_TOOLBOX_NOT_SUPPORTED,
            reason="SolidWorks Standard 版本不包含 Toolbox 标准件库",
            suggestion="升级到 Professional/Premium，或继续使用 stand-in 占位",
            severity='warn',
        )
    return True, None


def _check_com_healthy() -> tuple[bool, Optional[DiagnosisInfo]]:
    """检查 #5：SldWorks.Application COM 注册可用。"""
    try:
        from adapters.solidworks.sw_detect import detect_solidworks
        info = detect_solidworks()
    except Exception as e:  # noqa: BLE001
        return False, DiagnosisInfo(
            code=DiagnosisCode.COM_REGISTRATION_BROKEN,
            reason=f"COM 组件探测抛异常：{e}",
            suggestion="以管理员身份运行 'sldworks.exe /regserver' 重新注册 COM",
            severity='block',
        )
    if not info.com_available:
        return False, DiagnosisInfo(
            code=DiagnosisCode.COM_REGISTRATION_BROKEN,
            reason="SldWorks.Application COM 组件未注册或注册损坏",
            suggestion="以管理员身份运行 'sldworks.exe /regserver' 重新注册 COM",
            severity='block',
        )
    return True, None


def _check_addin_enabled() -> tuple[bool, Optional[DiagnosisInfo]]:
    """检查 #6：Toolbox Add-In 在 SW Tools → Add-Ins 里启用。"""
    try:
        from adapters.solidworks.sw_detect import detect_solidworks
        info = detect_solidworks()
    except Exception as e:  # noqa: BLE001
        return False, DiagnosisInfo(
            code=DiagnosisCode.ADDIN_DISABLED,
            reason=f"读取 Toolbox Add-In 启用状态失败：{e}",
            suggestion="在 SOLIDWORKS 的 Tools → Add-Ins 中勾选 SOLIDWORKS Toolbox",
            severity='warn',
        )
    if not info.toolbox_addin_enabled:
        return False, DiagnosisInfo(
            code=DiagnosisCode.ADDIN_DISABLED,
            reason="Toolbox Add-In 未在 SOLIDWORKS 中启用",
            suggestion="在 SOLIDWORKS 的 Tools → Add-Ins 中勾选 SOLIDWORKS Toolbox（可一键修）",
            severity='warn',
        )
    return True, None


def _check_toolbox_path_healthy() -> tuple[bool, Optional[DiagnosisInfo]]:
    """检查 #7（Track B 版）：toolbox_dir 物理健康（sldedb + sldprt 可读）。

    委托给 sw_detect.check_toolbox_path_healthy，保持 matrix check 接口统一。
    """
    try:
        from adapters.solidworks.sw_detect import detect_solidworks, check_toolbox_path_healthy
        info = detect_solidworks()
    except Exception as e:  # noqa: BLE001
        return False, DiagnosisInfo(
            code=DiagnosisCode.TOOLBOX_PATH_INVALID,
            reason=f"读取 Toolbox 路径状态失败：{e}",
            suggestion="检查 SOLIDWORKS 安装完整性",
            severity='block',
        )

    ok, reason = check_toolbox_path_healthy(info)
    if not ok:
        return False, DiagnosisInfo(
            code=DiagnosisCode.TOOLBOX_PATH_INVALID,
            reason=reason or "Toolbox 目录不健康",
            suggestion=(
                "在 SOLIDWORKS Tools → Options → Hole Wizard/Toolbox 中"
                "重新指定有效 Toolbox 目录，并确保 Toolbox 组件已完整安装"
            ),
            severity='block',
        )
    return True, None


def _check_toolbox_path() -> tuple[bool, Optional[DiagnosisInfo]]:
    """检查 #7：toolbox_dir 可达（区分本地 invalid vs UNC not_accessible）。"""
    try:
        from adapters.solidworks.sw_detect import (
            detect_solidworks,
            probe_toolbox_path_reachability,
        )
        info = detect_solidworks()
    except Exception as e:  # noqa: BLE001
        return False, DiagnosisInfo(
            code=DiagnosisCode.TOOLBOX_PATH_INVALID,
            reason=f"读取 Toolbox 路径失败：{e}",
            suggestion="检查 SOLIDWORKS 安装完整性及注册表 Toolbox 配置",
            severity='block',
        )
    if not info.toolbox_dir:
        return False, DiagnosisInfo(
            code=DiagnosisCode.TOOLBOX_PATH_INVALID,
            reason="SOLIDWORKS 注册表未配置 Toolbox 数据目录",
            suggestion="在 SOLIDWORKS Tools → Options → Hole Wizard/Toolbox 中设置 Toolbox 文件夹",
            severity='block',
        )
    reachability = probe_toolbox_path_reachability(info.toolbox_dir)
    if reachability == 'invalid':
        return False, DiagnosisInfo(
            code=DiagnosisCode.TOOLBOX_PATH_INVALID,
            reason=f"Toolbox 本地路径不存在：{info.toolbox_dir}",
            suggestion="在 SOLIDWORKS Tools → Options → Hole Wizard/Toolbox 中重新指定有效目录",
            severity='block',
        )
    if reachability == 'not_accessible':
        return False, DiagnosisInfo(
            code=DiagnosisCode.TOOLBOX_PATH_NOT_ACCESSIBLE,
            reason=f"Toolbox 网络路径不可达（权限或网络问题）：{info.toolbox_dir}",
            suggestion="检查 VPN / 网络共享权限，或切换到本地 Toolbox 目录",
            severity='block',
        )
    return True, None


# ---------------------------------------------------------------------------
# 检查顺序与主调度
# ---------------------------------------------------------------------------
CheckFn = Callable[[], tuple[bool, Optional[DiagnosisInfo]]]

# CHECK_ORDER 存 (name, helper_attr_name) — 运行时用模块级名字动态解析，
# 这样 unittest.mock.patch 替换模块级属性时，run_all_checks 能拿到被 patch 的版本。
# （若直接存函数对象，patch 替换不到列表内的引用，导致 monkeypatch 失效。）
CHECK_ORDER: list[tuple[str, str]] = [
    ('platform', '_check_platform'),
    ('pywin32', '_check_pywin32'),
    ('sw_installed', '_check_sw_installed'),
    ('toolbox_supported', '_check_toolbox_supported'),
    ('com_healthy', '_check_com_healthy'),
    ('addin_enabled', '_check_addin_enabled'),
    ('toolbox_path', '_check_toolbox_path_healthy'),
]

_BLOCKING_CHECKS: frozenset[str] = frozenset({
    "platform",
    "pywin32",
    "sw_installed",
    "toolbox_supported",
    "com_healthy",
    "toolbox_path",
    # addin_enabled 故意不在此集合 —— B-5 advisory only
})


def run_all_checks() -> dict:
    """按 CHECK_ORDER 顺序跑全部检查；不短路，全量收集结果。

    Returns:
        {
          'passed': bool,                   # True 当且仅当所有 _BLOCKING_CHECKS 中的 check 都通过
          'failed_check': Optional[str],    # 第一个 blocking 失败的 check 名
          'diagnosis': Optional[DiagnosisInfo],  # 第一个 blocking 失败的诊断
          'advisory_failures': dict[str, Optional[DiagnosisInfo]],  # 非 blocking 失败集合
        }
    """
    import sys
    this_module = sys.modules[__name__]

    first_blocking_fail: Optional[str] = None
    first_blocking_diag = None
    advisory_failures: dict = {}

    for name, attr in CHECK_ORDER:
        check: CheckFn = getattr(this_module, attr)
        ok, diag = check()
        if not ok:
            if name in _BLOCKING_CHECKS:
                if first_blocking_fail is None:
                    first_blocking_fail = name
                    first_blocking_diag = diag
            else:
                advisory_failures[name] = diag

    passed = first_blocking_fail is None
    return {
        "passed": passed,
        "failed_check": first_blocking_fail,
        "diagnosis": first_blocking_diag,
        "advisory_failures": advisory_failures,
    }


# ---------------------------------------------------------------------------
# Task 13：一键修 pywin32
# ---------------------------------------------------------------------------
import subprocess
import sys
import time

from sw_preflight.types import FixRecord


def fix_pywin32() -> FixRecord:
    """一键修复 pywin32 缺失：pip install + postinstall import 验证。

    成功 → 返回 FixRecord(action='pywin32_install', after_state='installed_success', ...)
    失败 → raise RuntimeError("PYWIN32_INSTALL_FAILED: ...") 带具体原因
    """
    start = time.time()
    # 第一步：pip install pywin32
    r = subprocess.run(
        [sys.executable, '-m', 'pip', 'install', 'pywin32'],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"PYWIN32_INSTALL_FAILED: pip install 失败: {r.stderr}")
    # 第二步：postinstall 验证 — 新子进程 import win32com 确认已装好
    r2 = subprocess.run(
        [sys.executable, '-c', 'import win32com'],
        capture_output=True,
        text=True,
    )
    if r2.returncode != 0:
        raise RuntimeError("PYWIN32_INSTALL_FAILED: postinstall 后 import 仍失败")
    elapsed = (time.time() - start) * 1000
    return FixRecord(
        action='pywin32_install',
        before_state='missing',
        after_state='installed_success',
        elapsed_ms=elapsed,
    )


# ---------------------------------------------------------------------------
# Task 14：一键修 ROT 僵死释放（静默自愈）
# ---------------------------------------------------------------------------
def fix_rot_orphan() -> FixRecord:
    """静默释放 COM ROT 僵死实例 + reset sw_detect 缓存。

    sw_com_session 无 release_all API（已核实），走 plan 脚注的 pythoncom
    重初始化 fallback：CoUninitialize() → CoInitialize() 对 — 在当前线程
    彻底释放 COM 再重建干净状态。之后调 sw_detect.reset_cache() 让下次
    detect_solidworks 重新探测，避免被旧缓存带偏。

    本函数设计为"静默自愈"——任一底层调用失败都吞掉异常，
    由上层（preflight 下一轮）的诊断流程判定是否仍为 unhealthy。
    """
    from adapters.solidworks import sw_detect
    start = time.time()
    try:
        import pythoncom  # type: ignore[import-not-found]  # Windows-only
        try:
            pythoncom.CoUninitialize()
        except Exception:  # noqa: BLE001
            # 当前线程可能未初始化 COM，CoUninitialize 抛异常属正常情况
            pass
        try:
            pythoncom.CoInitialize()
        except Exception:  # noqa: BLE001
            # 非 Windows 或 pywin32 缺失 — 继续走 reset_cache，由上层再诊断
            pass
    except ImportError:
        # pywin32 不可用 — 前置 gate(_check_pywin32) 已拦截；
        # 若执行到此说明极端并发/状态异常，跳过 pythoncom 步骤继续 reset_cache
        pass
    sw_detect.reset_cache()
    elapsed = (time.time() - start) * 1000
    return FixRecord(
        action='rot_orphan_release',
        before_state='unhealthy',
        after_state='healthy',
        elapsed_ms=elapsed,
    )


# ---------------------------------------------------------------------------
# Task 15：一键修 Toolbox Add-In enable（HKCU 幂等）
# ---------------------------------------------------------------------------
def _is_addin_enabled() -> bool:
    """委托 sw_detect 的已知机制检查 Toolbox Add-In 启用状态。

    直接读 `SwInfo.toolbox_addin_enabled`——detect_solidworks 已做过
    HKCU AddInsStartup 枚举（与 fix 写回的路径互为反函数）。
    任何异常视为"未启用"，让调用方走写入路径；写入幂等性由此前置判断保证。
    """
    try:
        from adapters.solidworks.sw_detect import detect_solidworks
        return detect_solidworks().toolbox_addin_enabled
    except Exception:  # noqa: BLE001
        return False


def fix_addin_enable() -> FixRecord:
    """一键修：HKCU\\Software\\SolidWorks\\AddInsStartup 下写 GUID=1。

    流程：
    1. 已启用 → 直接返回 no_op（幂等守护）
    2. 等关装配体（避免修改 registry 时 SW 正在读）
    3. 通过 sw_toolbox_adapter.get_toolbox_addin_guid 拿到 Toolbox GUID
    4. 写 HKCU（绝不触 HKLM——避免 admin 需求）；value name = GUID，value = 1

    路径对齐：与 `sw_detect._check_toolbox_addin_enabled` 读取路径完全一致
    （`AddInsStartup` 下以 GUID 为 value name 的 REG_DWORD），否则会"写了
    但 detect 读不到 → 预检仍判 unhealthy"的 bug。plan 原写的
    `Addins\\{guid}\\(default)` 与读路径不符，此处按实现一致性修正。

    失败模式：
    - 等装配体超时 → RuntimeError("ADDIN_ENABLE_FAILED: 等关装配体超时")
    - 注册表里没发现 Toolbox GUID（从未装过 Toolbox）→
      RuntimeError("ADDIN_ENABLE_FAILED: Toolbox Add-in GUID not discoverable from registry")
    """
    from sw_preflight.io import wait_for_assembly_close
    from adapters.parts.sw_toolbox_adapter import get_toolbox_addin_guid
    import winreg  # type: ignore[import-not-found]  # Windows-only

    if _is_addin_enabled():
        return FixRecord(
            action='addin_enable',
            before_state='already_enabled',
            after_state='no_op',
            elapsed_ms=0.0,
        )

    if not wait_for_assembly_close(timeout_sec=300):
        raise RuntimeError("ADDIN_ENABLE_FAILED: 等关装配体超时")

    guid = get_toolbox_addin_guid()
    if guid is None:
        raise RuntimeError(
            "ADDIN_DLL_NOT_FOUND: install_dir 下找不到 Toolbox Add-in DLL — "
            "可能是 Standard 版未装 Toolbox Library"
        )

    start = time.time()
    # 写 HKCU AddInsStartup 下的 GUID value（REG_DWORD=1）——与 detect 读路径对齐
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\SolidWorks\AddInsStartup",
        0,
        winreg.KEY_SET_VALUE,
    ) as k:
        winreg.SetValueEx(k, guid, 0, winreg.REG_DWORD, 1)
    elapsed = (time.time() - start) * 1000
    return FixRecord(
        action='addin_enable',
        before_state='disabled',
        after_state='enabled_hkcu',
        elapsed_ms=elapsed,
    )


# ---------------------------------------------------------------------------
# Task 16：一键修 SW 后台进程启动（不弹 GUI）
# ---------------------------------------------------------------------------
def fix_sw_launch_background() -> FixRecord:
    """启动 SOLIDWORKS 后台进程（Visible=False），不弹 GUI。

    设计要点：
    - sw_com_session 无 start_background API（已核实），走 plan 脚注许可的
      pythoncom Dispatch fallback：`Dispatch('SldWorks.Application')` 会自动
      启动 SW 进程（若未运行），成功后设 `Visible = False` 隐藏界面。
    - 先调 `get_session().is_healthy()`：已健康则走 early return（幂等守护），
      避免无谓地二次 CoInitialize/Dispatch。
    - COM 初始化使用 try/finally 配对，确保异常路径也会 CoUninitialize。
    - 某些 SW 版本对 Visible 属性设置有差异，设置失败降级为"已启动但可能可见"，
      不视为整体失败（启动成功本身已满足 FixRecord 语义）。

    Returns:
        FixRecord(action='sw_launch_background', ...)
          - 已运行 → after_state='launched_already'
          - 新启成功 → after_state='launched_invisible'

    Raises:
        RuntimeError("SW_LAUNCH_FAILED: <type>: <msg>"):
          pythoncom 不可用 / Dispatch 抛异常 / 其它底层错误
    """
    from adapters.solidworks.sw_com_session import get_session

    start = time.time()
    sess = get_session()
    if sess.is_healthy():
        # SW 已在运行且 COM 可通信 — 幂等返回，不触发 Dispatch
        elapsed = (time.time() - start) * 1000
        return FixRecord(
            action='sw_launch_background',
            before_state='already_running',
            after_state='launched_already',
            elapsed_ms=elapsed,
        )

    # 未健康 → 走 Dispatch 启动 SW
    try:
        import pythoncom  # type: ignore[import-not-found]  # Windows-only
        import win32com.client  # type: ignore[import-not-found]  # Windows-only

        pythoncom.CoInitialize()
        try:
            sw_app = win32com.client.Dispatch("SldWorks.Application")
            try:
                sw_app.Visible = False
            except Exception:  # noqa: BLE001
                # 某些 SW 版本不支持直接设 Visible — 启动成功本身已达成目标
                pass
            elapsed = (time.time() - start) * 1000
            return FixRecord(
                action='sw_launch_background',
                before_state='not_running',
                after_state='launched_invisible',
                elapsed_ms=elapsed,
            )
        finally:
            pythoncom.CoUninitialize()
    except Exception as e:  # noqa: BLE001 — 统一包装为 RuntimeError 供上层诊断
        raise RuntimeError(f"SW_LAUNCH_FAILED: {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Task 17：管理员权限检测 + ShellExecute "runas" 退化 + 三选一 prompt
# ---------------------------------------------------------------------------
import ctypes  # noqa: E402 — 按任务分段组织；仅 Task 17 相关函数使用


def is_user_admin() -> bool:
    """检测当前进程是否以管理员身份运行。

    走 `shell32.IsUserAnAdmin`；非 Windows 或 ctypes 调用抛异常时兜底为 False
    （产品范围 Windows-only，非 Windows 路径上游已由 platform gate 拦截）。
    """
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001 — 非 Windows / 不支持环境均视为"非管理员"
        return False


def elevate_with_runas() -> int:
    """通过 ShellExecute "runas" 重启当前进程为管理员（弹 UAC 确认）。

    返回 ShellExecuteW 的原始返回码（> 32 表示成功调度）；调用方可据此判断
    是否需要降级到手动指引。实际进程重启由 Windows Shell 完成，本函数不阻塞。
    """
    return ctypes.windll.shell32.ShellExecuteW(
        None, 'runas', sys.executable, ' '.join(sys.argv), None, 1
    )


def handle_admin_required(action_desc: str) -> str:
    """非 admin 时弹三选一 prompt：[1] 重启 admin / [2] 手动修 / [Q] 退出。

    - 选 [1]：调 `elevate_with_runas()` 然后 `sys.exit(0)`（当前进程让位给 admin 进程）
    - 选 [2]：返回 'manual'，调用方走手动 GUI 指引降级路径
    - 选 [Q]：`sys.exit(2)` 用户主动放弃
    非法输入循环再询，直到得到有效选择。

    Args:
        action_desc: 动作的中文描述（如 "Add-In 启用"），用于 prompt 提示。
    """
    print(f"\n⚠️ 此修复 ({action_desc}) 需要管理员权限。")
    print("  [1] 以管理员身份重启本工具（系统会弹 UAC 确认）")
    print("  [2] 我自己手动修（按报告里的 GUI 步骤）")
    print("  [Q] 退出")
    while True:
        choice = input("请选 [1/2/Q]: ").strip().upper()
        if choice == '1':
            elevate_with_runas()
            sys.exit(0)
        if choice == '2':
            return 'manual'
        if choice == 'Q':
            sys.exit(2)


# ---------------------------------------------------------------------------
# Task 18：DiagnosisCode → DiagnosisInfo 模板工厂（9 个诊断码）
# ---------------------------------------------------------------------------
# 模板按 DiagnosisCode 分发；每个模板是 lambda ctx → DiagnosisInfo。
# context dict 用 .get(key, default) 防守缺 key 场景，避免 KeyError。
# 本 task 只覆盖 plan 1679-1723 行列出的 9 个 code；其余 7 个 code
# （PYWIN32_MISSING / PYWIN32_INSTALL_FAILED / ADDIN_DISABLED /
#  BOM_ROW_NO_MATCH / BOM_ROW_FELL_THROUGH_TO_STAND_IN /
#  USER_PROVIDED_SOURCE_HASH_MISMATCH / USER_PROVIDED_SCHEMA_INVALID）
# plan 未要求模板化——make_diagnosis 遇未覆盖 code 会 raise ValueError。
DIAGNOSIS_TEMPLATES = {
    DiagnosisCode.PLATFORM_NOT_WINDOWS: lambda ctx: DiagnosisInfo(
        code=DiagnosisCode.PLATFORM_NOT_WINDOWS,
        reason=f"本工具仅支持 Windows — 检测到 platform={ctx.get('platform','?')}",
        suggestion="在 Windows 机器上重跑", severity='block'),
    DiagnosisCode.SW_NOT_INSTALLED: lambda ctx: DiagnosisInfo(
        code=DiagnosisCode.SW_NOT_INSTALLED,
        reason="未检测到 SolidWorks 安装",
        suggestion="请先安装 SolidWorks Pro 或 Premium", severity='block'),
    DiagnosisCode.SW_TOOLBOX_NOT_SUPPORTED: lambda ctx: DiagnosisInfo(
        code=DiagnosisCode.SW_TOOLBOX_NOT_SUPPORTED,
        reason=f"检测到 SW 但 Toolbox 不可用",
        suggestion="请打开 SOLIDWORKS → 帮助 → 关于 → 查看许可证类型；按需升级 Pro/Premium 或用 SW installer 修改安装勾选 Toolbox",
        severity='block'),
    DiagnosisCode.LICENSE_PROBLEM: lambda ctx: DiagnosisInfo(
        code=DiagnosisCode.LICENSE_PROBLEM,
        reason="SW 已安装但 license 异常",
        suggestion="请双击桌面 SOLIDWORKS 图标启动一次，查看 SW 自己弹的 license 报错并按提示修复",
        severity='block'),
    DiagnosisCode.COM_REGISTRATION_BROKEN: lambda ctx: DiagnosisInfo(
        code=DiagnosisCode.COM_REGISTRATION_BROKEN,
        reason="SW COM 接口异常 (CLSID 实例化失败)",
        suggestion="控制面板 → 程序 → SOLIDWORKS → 修改 → 修复安装",
        severity='block'),
    DiagnosisCode.TOOLBOX_PATH_INVALID: lambda ctx: DiagnosisInfo(
        code=DiagnosisCode.TOOLBOX_PATH_INVALID,
        reason=f"Toolbox 数据库路径配置无效 (本地路径不存在): {ctx.get('path','?')}",
        suggestion="SOLIDWORKS → 工具 → 选项 → 异型孔向导/Toolbox → 把路径改到本地非同步目录",
        severity='block'),
    DiagnosisCode.TOOLBOX_PATH_NOT_ACCESSIBLE: lambda ctx: DiagnosisInfo(
        code=DiagnosisCode.TOOLBOX_PATH_NOT_ACCESSIBLE,
        reason=f"Toolbox 路径配置存在但访问失败 (UNC/网络不可达): {ctx.get('path','?')}",
        suggestion="检查网络连接、VPN、共享映射；联系 IT 管理员确认权限",
        severity='block'),
    DiagnosisCode.MULTIPLE_SW_VERSIONS_AMBIGUOUS: lambda ctx: DiagnosisInfo(
        code=DiagnosisCode.MULTIPLE_SW_VERSIONS_AMBIGUOUS,
        reason=f"检测到多个 SW 版本 {ctx.get('versions','?')}，自动选择失败",
        suggestion="请打开期望使用的 SW 版本一次（确认它能正常启动），或卸载坏的版本",
        severity='block'),
    DiagnosisCode.INSUFFICIENT_PRIVILEGES: lambda ctx: DiagnosisInfo(
        code=DiagnosisCode.INSUFFICIENT_PRIVILEGES,
        reason="修复需要管理员权限",
        suggestion="重新以'以管理员身份运行'启动终端再跑本工具，或按报告中的 GUI 步骤手动修复",
        severity='block'),
}


def make_diagnosis(code: DiagnosisCode, context: dict = None) -> DiagnosisInfo:
    """按 DiagnosisCode 查模板、注入 context、构造 DiagnosisInfo。

    Args:
        code: 诊断码；必须存在于 DIAGNOSIS_TEMPLATES 中。
        context: 可选的上下文 dict，模板用 .get(key, default) 读取（容错缺 key）。

    Raises:
        ValueError: code 未在 DIAGNOSIS_TEMPLATES 中注册（即本 task 9 个码之外）。
    """
    ctx = context or {}
    template = DIAGNOSIS_TEMPLATES.get(code)
    if template is None:
        raise ValueError(f"未知 DiagnosisCode: {code}")
    return template(ctx)


# ---------------------------------------------------------------------------
# Task 26：一键修 dispatch helper（run_preflight 调用入口）
# ---------------------------------------------------------------------------
def try_one_click_fix(
    failed_check: str,
    diagnosis: Optional[DiagnosisInfo],  # noqa: ARG001 — 保留形参供未来按 code 细分
) -> Optional[FixRecord]:
    """按 failed_check 名字 dispatch 到具体 fix_* 函数。不可修返 None。

    映射规则（与 CHECK_ORDER 7 项一一对应）：
      - platform          → None（无法改 OS，只能让用户换机器）
      - pywin32           → fix_pywin32
      - sw_installed      → None（用户必须装 SW）
      - toolbox_supported → None（edition 升级属用户行为）
      - com_healthy       → fix_rot_orphan（COM 不健康尝试释放 ROT）
      - addin_enabled     → fix_addin_enable
      - toolbox_path      → None（路径问题需用户在 SW GUI 里改）

    Args:
        failed_check: `run_all_checks` 返回的 `failed_check` 名字。
        diagnosis: 对应的 DiagnosisInfo（暂未使用，保留供未来按 code 细分 fix 策略）。

    Returns:
        FixRecord: 成功修复时的记录；无法修复或修复途中异常均返回 None。
    """
    fix_map: dict[str, Optional[Callable[[], FixRecord]]] = {
        'platform': None,
        'pywin32': fix_pywin32,
        'sw_installed': None,
        'toolbox_supported': None,
        'com_healthy': fix_rot_orphan,
        'addin_enabled': fix_addin_enable,
        'toolbox_path': None,
    }
    fn = fix_map.get(failed_check)
    if fn is None:
        return None
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        # silent-failure-hunter 反模式守护：修复失败**必须**打印根因到 stderr，
        # 否则用户只看到 preflight 给的通用"建议：手动 xxx"却不知道"一键修其实
        # 抛了 ADDIN_ENABLE_FAILED: GUID not discoverable"这种可诊断信息。
        # 上层 preflight 仍按 strict 决定 exit/告警；返回 None 的契约保持不变。
        import sys as _sys
        print(
            f"[preflight] 一键修 {failed_check} 抛异常（不阻断上层决策）: "
            f"{type(exc).__name__}: {exc}",
            file=_sys.stderr,
        )
        return None
