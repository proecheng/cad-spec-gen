"""SolidWorks 诊断内核 — 纯函数 probe + ProbeResult dataclass。

所有 probe_* 函数：
- 不抛异常（除 KeyboardInterrupt/SystemExit）
- 不 print / 不 sys.exit
- 返回结构化 ProbeResult

被 tools/sw_inspect.py（CLI 格式化）和 scripts/sw_spike_diagnose.py（薄壳）共同调用。
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any, Literal, Optional

from adapters.solidworks import sw_detect
from adapters.solidworks.sw_detect import SwInfo


@dataclass(frozen=True)
class ProbeResult:
    """单层探测结果。

    字段：
        layer: 层名（"environment" / "pywin32" / "detect" / ...）
        ok: 本层是否健康（ok 或 warn 视为可用）
        severity: "ok" | "warn" | "fail"
        summary: 一行人读摘要
        data: 结构化字段（JSON schema 定义见 spec §4.4）
        error: 失败时的错误文案（str(exc)[:200]）
        hint: 用户可采取的下一步行动（中文，文本模式缩进打印）
    """

    layer: str
    ok: bool
    severity: Literal["ok", "warn", "fail"]
    summary: str
    data: dict[str, Any]
    error: Optional[str] = None
    hint: Optional[str] = None


def probe_environment() -> ProbeResult:
    """层 0：OS / Python 版本 / 位数 / PID。无 I/O，无可能失败点。"""
    pyver = sys.version.split()[0]
    bits = 64 if sys.maxsize > 2**32 else 32
    return ProbeResult(
        layer="environment",
        ok=True,
        severity="ok",
        summary=f"python={pyver} platform={sys.platform} arch={bits}-bit",
        data={
            "os": sys.platform,
            "python_version": pyver,
            "python_bits": bits,
            "pid": os.getpid(),
        },
    )


def probe_pywin32() -> ProbeResult:
    """层 1：import win32com.client。失败提示装 [solidworks] extra。"""
    try:
        import win32com.client

        return ProbeResult(
            layer="pywin32",
            ok=True,
            severity="ok",
            summary="pywin32 已安装",
            data={
                "available": True,
                "module_path": getattr(win32com.client, "__file__", None),
            },
        )
    except Exception as e:  # ImportError 或其他
        return ProbeResult(
            layer="pywin32",
            ok=False,
            severity="fail",
            summary="pywin32 未安装或不兼容",
            data={"available": False, "module_path": None},
            error=str(e)[:200],
            hint="运行 `pip install 'cad-spec-gen[solidworks]'`（Windows only）",
        )


def probe_detect() -> tuple[ProbeResult, SwInfo]:
    """层 2：sw_detect 静态注册表检测。

    返回 (ProbeResult, SwInfo)：info 对象透传给 probe_material_files /
    probe_toolbox_index_cache，避免重复 detect。

    每次先 `_reset_cache()` 强制重测（SAR-2：保证长驻进程场景下读到最新状态）。
    """
    try:
        sw_detect._reset_cache()
        info = sw_detect.detect_solidworks()
    except Exception as e:
        empty = SwInfo(installed=False)
        return (
            ProbeResult(
                layer="detect",
                ok=False,
                severity="fail",
                summary="detect_solidworks 调用异常",
                data={"installed": False},
                error=str(e)[:200],
            ),
            empty,
        )

    data = {
        "installed": info.installed,
        "version": info.version,
        "version_year": info.version_year,
        "install_dir": info.install_dir,
        "textures_dir": info.textures_dir,
        "p2m_dir": info.p2m_dir,
        "toolbox_dir": info.toolbox_dir,
        "com_available": info.com_available,
        "pywin32_available": info.pywin32_available,
        "toolbox_addin_enabled": info.toolbox_addin_enabled,
    }
    if info.installed:
        return (
            ProbeResult(
                layer="detect",
                ok=True,
                severity="ok",
                summary=f"SolidWorks {info.version_year} 已安装于 {info.install_dir}",
                data=data,
            ),
            info,
        )
    return (
        ProbeResult(
            layer="detect",
            ok=False,
            severity="fail",
            summary="未在注册表检测到 SolidWorks 安装",
            data=data,
            hint="检查 HKLM\\SOFTWARE\\SolidWorks\\SOLIDWORKS 202X 注册表项；或重装 SolidWorks",
        ),
        info,
    )


def probe_clsid() -> ProbeResult:
    """层 3：winreg 读 SldWorks.Application 的 CLSID（不启动进程）。"""
    if sys.platform != "win32":
        return ProbeResult(
            layer="clsid",
            ok=True,
            severity="warn",
            summary="not applicable（非 Windows 平台；CLSID 仅在 Windows 注册表）",
            data={"progid": "SldWorks.Application", "clsid": "", "registered": False},
        )
    try:
        import winreg

        progid = "SldWorks.Application"
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"{progid}\CLSID") as k:
            clsid, _ = winreg.QueryValueEx(k, "")
        return ProbeResult(
            layer="clsid",
            ok=True,
            severity="ok",
            summary=f"{progid} 已注册 CLSID={clsid}",
            data={"progid": progid, "clsid": clsid, "registered": True},
        )
    except FileNotFoundError as e:
        return ProbeResult(
            layer="clsid",
            ok=False,
            severity="fail",
            summary="SldWorks.Application progid 未注册",
            data={"progid": "SldWorks.Application", "clsid": "", "registered": False},
            error=str(e)[:200],
            hint="管理员权限运行 `sldworks.exe /regserver` 或重装 SW",
        )
    except Exception as e:
        return ProbeResult(
            layer="clsid",
            ok=False,
            severity="fail",
            summary="CLSID 查询异常",
            data={"progid": "SldWorks.Application", "clsid": "", "registered": False},
            error=str(e)[:200],
        )
