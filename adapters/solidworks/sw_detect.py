"""
adapters/solidworks/sw_detect.py — SolidWorks 安装检测模块。

从 Windows 注册表动态读取 SolidWorks 安装信息，不硬编码任何文件系统路径。
非 Windows 平台立即短路返回 installed=False。

用法::

    from adapters.solidworks.sw_detect import detect_solidworks

    info = detect_solidworks()
    if info.installed:
        print(f"SolidWorks {info.version_year} 安装于 {info.install_dir}")
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class SwInfo:
    """SolidWorks 安装信息数据类。

    所有路径均从注册表动态获取，绝不硬编码。
    未安装时所有字段保持默认值。
    """

    installed: bool = False
    """是否检测到 SolidWorks 安装"""

    version: str = ""
    """完整版本字符串，例如 '30.1.0.0080'"""

    version_year: int = 0
    """年份版本，例如 2024"""

    install_dir: str = ""
    """安装目录路径（从注册表获取）"""

    sldmat_paths: list[str] = field(default_factory=list)
    """所有找到的 .sldmat 材质库文件路径"""

    textures_dir: str = ""
    """纹理贴图目录（install_dir/data/Images/textures）"""

    p2m_dir: str = ""
    """P2M 材质预览目录（install_dir/data/graphics/Materials）"""

    toolbox_dir: str = ""
    """Toolbox 数据目录（从注册表获取，拼接 browser/）"""

    com_available: bool = False
    """SldWorks.Application COM 组件是否可用"""

    pywin32_available: bool = False
    """pywin32 (win32com) 是否可导入"""

    toolbox_addin_enabled: bool = False
    """Toolbox Add-In 是否在 SW Tools → Add-Ins 里启用（v4 决策 #13）"""


# 进程级缓存
_cached_info: Optional[SwInfo] = None


def detect_solidworks() -> SwInfo:
    """检测当前系统的 SolidWorks 安装状态。

    使用进程级缓存：首次调用执行检测，后续调用返回同一对象。
    非 Windows 平台直接返回未安装状态。

    Returns:
        SwInfo 实例，包含检测到的安装信息。
    """
    global _cached_info
    if _cached_info is not None:
        return _cached_info
    _cached_info = _detect_impl()
    return _cached_info


def _reset_cache() -> None:
    """清除进程级缓存，供测试使用。"""
    global _cached_info
    _cached_info = None


def _detect_impl() -> SwInfo:
    """执行实际的 SolidWorks 检测逻辑。

    检测流程：
    1. 非 Windows 平台 → 立即返回 installed=False
    2. 遍历注册表查找安装目录（年份从 2030 降序到 2020）
    3. 读取 Toolbox 目录
    4. 扫描 sldmat 材质库文件
    5. 检查纹理和 P2M 目录
    6. 检测 COM 可用性
    7. 检测 pywin32 可用性
    """
    if sys.platform != "win32":
        return SwInfo(installed=False)

    # 仅在 Windows 上导入 winreg，避免非 Windows 平台报错
    import winreg

    info = SwInfo()

    # --- 检测 pywin32 可用性 ---
    info.pywin32_available = _check_pywin32()

    # --- 从注册表查找安装目录 ---
    install_dir, version_year, version_str = _find_install_from_registry(winreg)
    if not install_dir:
        # 注册表中未找到 SolidWorks 安装
        return info

    info.installed = True
    info.install_dir = install_dir
    info.version_year = version_year
    info.version = version_str

    # --- 读取 Toolbox 目录 ---
    info.toolbox_dir = _find_toolbox_dir(winreg, version_year)

    # --- 扫描 sldmat 材质库文件 ---
    info.sldmat_paths = _find_sldmat_files(install_dir)

    # --- 检查纹理目录 ---
    textures = Path(install_dir) / "data" / "Images" / "textures"
    if textures.is_dir():
        info.textures_dir = str(textures)

    # --- 检查 P2M 目录 ---
    p2m = Path(install_dir) / "data" / "graphics" / "Materials"
    if p2m.is_dir():
        info.p2m_dir = str(p2m)

    # --- 检测 COM 可用性 ---
    info.com_available = _check_com_available(winreg)

    return info


def _find_install_from_registry(winreg) -> tuple[str, int, str]:
    """从注册表查找 SolidWorks 安装目录。

    双路查询两种注册表键名格式（SolidWorks / SOLIDWORKS），
    年份从 2030 降序到 2020，返回找到的最新版本。

    Args:
        winreg: winreg 模块引用。

    Returns:
        (install_dir, version_year, version_str) 三元组，
        未找到时返回 ("", 0, "")。
    """
    # 两种注册表键名格式
    key_patterns = [
        r"SOFTWARE\SolidWorks\SolidWorks {year}\Setup",
        r"SOFTWARE\SolidWorks\SOLIDWORKS {year}\Setup",
    ]

    for year in range(2030, 2019, -1):
        for pattern in key_patterns:
            key_path = pattern.format(year=year)
            install_dir = _read_registry_value(
                winreg, winreg.HKEY_LOCAL_MACHINE, key_path, "SolidWorks Folder"
            )
            if install_dir and Path(install_dir).is_dir():
                # 尝试读取版本号
                version_str = _read_registry_value(
                    winreg, winreg.HKEY_LOCAL_MACHINE, key_path, "Version"
                ) or ""
                return install_dir, year, version_str

    return "", 0, ""


def _find_toolbox_dir(winreg, version_year: int) -> str:
    """从注册表读取 Toolbox 数据目录。

    读取后拼接 ``\\browser\\`` 子路径。

    Args:
        winreg: winreg 模块引用。
        version_year: SolidWorks 年份版本。

    Returns:
        Toolbox browser 目录路径，未找到时返回空字符串。
    """
    key_patterns = [
        r"SOFTWARE\SolidWorks\SolidWorks {year}\General",
        r"SOFTWARE\SolidWorks\SOLIDWORKS {year}\General",
    ]

    for pattern in key_patterns:
        key_path = pattern.format(year=version_year)
        toolbox_base = _read_registry_value(
            winreg, winreg.HKEY_LOCAL_MACHINE, key_path, "Toolbox Data Location"
        )
        if toolbox_base:
            browser_dir = Path(toolbox_base) / "browser"
            if browser_dir.is_dir():
                return str(browser_dir)

    return ""


def _find_sldmat_files(install_dir: str) -> list[str]:
    """扫描安装目录下所有语言目录中的 .sldmat 文件。

    搜索路径：``install_dir/lang/*/sldmaterials/*.sldmat``

    Args:
        install_dir: SolidWorks 安装目录。

    Returns:
        所有找到的 .sldmat 文件绝对路径列表。
    """
    sldmat_files: list[str] = []
    lang_dir = Path(install_dir) / "lang"
    if lang_dir.is_dir():
        for sldmat in lang_dir.glob("*/sldmaterials/*.sldmat"):
            sldmat_files.append(str(sldmat))
    return sorted(sldmat_files)


def _check_com_available(winreg) -> bool:
    """检查 SldWorks.Application COM 组件是否在注册表中注册。

    查询 ``HKCR\\SldWorks.Application\\CLSID`` 的存在性。

    Args:
        winreg: winreg 模块引用。

    Returns:
        COM 组件是否可用。
    """
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CLASSES_ROOT, r"SldWorks.Application\CLSID"
        )
        winreg.CloseKey(key)
        return True
    except OSError:
        return False


def _check_pywin32() -> bool:
    """检查 pywin32 (win32com.client) 是否可导入。

    Returns:
        pywin32 是否可用。
    """
    try:
        import win32com.client  # noqa: F401 — 仅检测可导入性

        return True
    except ImportError:
        return False


def _read_registry_value(
    winreg, hive, key_path: str, value_name: str
) -> str | None:
    """安全地从注册表读取字符串值。

    同时尝试 64 位和 32 位注册表视图。

    Args:
        winreg: winreg 模块引用。
        hive: 注册表根键（如 HKEY_LOCAL_MACHINE）。
        key_path: 注册表键路径。
        value_name: 值名称。

    Returns:
        读取到的字符串值，失败时返回 None。
    """
    for access_flag in (winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                        winreg.KEY_READ | winreg.KEY_WOW64_32KEY):
        try:
            key = winreg.OpenKey(hive, key_path, 0, access_flag)
            try:
                value, _ = winreg.QueryValueEx(key, value_name)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            finally:
                winreg.CloseKey(key)
        except OSError:
            continue
    return None
