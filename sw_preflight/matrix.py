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
    if info.edition == 'Standard':
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
    ('toolbox_path', '_check_toolbox_path'),
]


def run_all_checks() -> dict:
    """按 CHECK_ORDER 顺序跑 7 项检查；遇第一失败短路返回；全过返回 passed=True。

    Returns:
        - 失败：``{'passed': False, 'failed_check': <name>, 'diagnosis': DiagnosisInfo}``
        - 全过：``{'passed': True, 'failed_check': None, 'diagnosis': None}``
    """
    import sys
    this_module = sys.modules[__name__]
    for name, attr in CHECK_ORDER:
        check: CheckFn = getattr(this_module, attr)
        ok, diag = check()
        if not ok:
            return {'passed': False, 'failed_check': name, 'diagnosis': diag}
    return {'passed': True, 'failed_check': None, 'diagnosis': None}


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
