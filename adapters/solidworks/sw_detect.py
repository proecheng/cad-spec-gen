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

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

# Task 5：多版本优先级读取 preference.json 时使用模块引用（而非 from...import），
# 确保测试可用 monkeypatch.setattr("sw_preflight.preference.read_preference", ...) 命中。
from sw_preflight import preference as _preference

# Task 5：env 变量名 — 用户 / CI 指定常用 SW 年份版本。
_ENV_PREFERRED_YEAR = "CAD_SPEC_GEN_SW_PREFERRED_YEAR"


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

    edition: Literal["Standard", "Pro", "Premium", "unknown"] = "unknown"
    """SolidWorks 版本级别（Standard/Pro/Premium），注册表读不到时为 'unknown'。"""


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
    """清除进程级缓存，供测试使用（历史私有 API，保留反引兼容）。"""
    global _cached_info
    _cached_info = None


def reset_cache() -> None:
    """清除进程级缓存的公开 API（Task 4 新增）。

    用途：sw_preflight 一键修复后必须调此函数，否则 detect_solidworks()
    会返回修复前的旧 SwInfo（_cached_info 存着）导致假成功。

    实现等价于 _reset_cache()，只是语义公开化。
    """
    _reset_cache()


def _detect_impl() -> SwInfo:
    """执行实际的 SolidWorks 检测逻辑。

    检测流程：
    1. 非 Windows 平台 → 立即返回 installed=False
    2. 动态枚举注册表子键查找安装目录（无年份范围硬编码）
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

    # --- 选版本：env > preference.json > 最新已安装（Task 5）---
    version_year = _select_version(winreg)
    if version_year is None:
        # 注册表中无任何已安装 SW
        return info

    # --- 取该年份的 install_dir（Task 5 拆出 _find_install_for_year）---
    install_dir, version_str = _find_install_for_year(winreg, version_year)
    if not install_dir:
        # 该年份注册表子键存在但 install_dir 读不到 / 目录不存在
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

    # --- 检测 Toolbox Add-In 启用状态（v4 决策 #13）---
    info.toolbox_addin_enabled = _check_toolbox_addin_enabled(winreg, info.version_year)

    # --- 检测 edition（Standard / Pro / Premium，Task 4）---
    info.edition = _find_edition(winreg, info.version_year)

    return info


def _enumerate_registered_years(winreg) -> list[int]:
    """枚举注册表 HKLM\\SOFTWARE\\SolidWorks 下所有子键的年份，无范围硬编码。

    匹配 'SolidWorks XXXX' 或 'SOLIDWORKS XXXX'（大小写不敏感），
    提取四位数字年份，降序返回。

    Args:
        winreg: winreg 模块引用。

    Returns:
        找到的年份列表（降序），未找到时返回空列表。
    """
    import re

    years: list[int] = []
    pattern = re.compile(r"SOLIDWORKS\s+(\d{4})", re.IGNORECASE)
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\SolidWorks",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as root:
            i = 0
            while True:
                try:
                    name = winreg.EnumKey(root, i)
                    m = pattern.match(name)
                    if m:
                        years.append(int(m.group(1)))
                    i += 1
                except OSError:
                    break
    except OSError:
        pass
    return sorted(years, reverse=True)


def _select_version(winreg) -> Optional[int]:
    """Task 5：按三档优先级裁决 SolidWorks 年份版本。

    优先级（严格顺序，跳档仅在"当前档为空或目标年份未安装"时发生）：

    1. 环境变量 ``CAD_SPEC_GEN_SW_PREFERRED_YEAR`` — int 字符串，
       解析失败 / 不在 _enumerate_registered_years 列表 → 降级下一档。
    2. ``sw_preflight.preference.read_preference()`` — 用户持久化偏好，
       None / 不在 _enumerate_registered_years 列表 → 降级下一档。
    3. ``_enumerate_registered_years(winreg)`` 第一项 — 降序排列，即最新已安装版。

    Args:
        winreg: winreg 模块引用。

    Returns:
        选中的年份 int；注册表中无任何 SW 子键时返回 None。
    """
    installed_years = _enumerate_registered_years(winreg)
    if not installed_years:
        return None

    # 档 1：env var
    env_raw = os.environ.get(_ENV_PREFERRED_YEAR)
    if env_raw:
        try:
            env_year = int(env_raw.strip())
        except (ValueError, TypeError):
            env_year = None
        if env_year is not None and env_year in installed_years:
            return env_year
        # env 设了但无效 → 继续降级

    # 档 2：preference.json（模块引用，支持 monkeypatch）
    pref_year = _preference.read_preference()
    if pref_year is not None and pref_year in installed_years:
        return pref_year

    # 档 3：最新（降序第一项）
    return installed_years[0]


def _find_install_for_year(winreg, year: int) -> tuple[str, str]:
    """Task 5：查某个具体年份的 install_dir + version 字符串。

    双路查询两种键名格式（SolidWorks / SOLIDWORKS），任一命中即返回。

    Args:
        winreg: winreg 模块引用。
        year: 目标 SolidWorks 年份版本。

    Returns:
        (install_dir, version_str) 二元组；目录不存在 / 读不到 → ("", "")。
    """
    key_patterns = [
        r"SOFTWARE\SolidWorks\SolidWorks {year}\Setup",
        r"SOFTWARE\SolidWorks\SOLIDWORKS {year}\Setup",
    ]

    for pattern in key_patterns:
        key_path = pattern.format(year=year)
        install_dir = _read_registry_value(
            winreg, winreg.HKEY_LOCAL_MACHINE, key_path, "SolidWorks Folder"
        )
        if install_dir and Path(install_dir).is_dir():
            version_str = (
                _read_registry_value(
                    winreg, winreg.HKEY_LOCAL_MACHINE, key_path, "Version"
                )
                or ""
            )
            return install_dir, version_str

    return "", ""


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


def _find_edition(
    winreg, version_year: int
) -> Literal["Standard", "Pro", "Premium", "unknown"]:
    """从注册表读取 SolidWorks edition 字段（Task 4）。

    路径：``HKLM\\SOFTWARE\\SolidWorks\\SOLIDWORKS <year>\\Setup\\Edition``
    （也兼容旧键名 ``SolidWorks <year>``）。

    归一化规则：
    - "Professional" → "Pro"
    - "Standard" / "Pro" / "Premium" 原样保留
    - 任何其他值 / 读不到 / 异常 → "unknown"

    Args:
        winreg: winreg 模块引用。
        version_year: SolidWorks 年份版本。

    Returns:
        归一化后的 edition 字面量。
    """
    key_patterns = [
        r"SOFTWARE\SolidWorks\SolidWorks {year}\Setup",
        r"SOFTWARE\SolidWorks\SOLIDWORKS {year}\Setup",
    ]

    for pattern in key_patterns:
        key_path = pattern.format(year=version_year)
        raw = _read_registry_value(
            winreg, winreg.HKEY_LOCAL_MACHINE, key_path, "Edition"
        )
        if not raw:
            continue

        # 归一化（大小写不敏感）
        normalized = raw.strip()
        lower = normalized.lower()
        if lower == "professional" or lower == "pro":
            return "Pro"
        if lower == "standard":
            return "Standard"
        if lower == "premium":
            return "Premium"
        # 读到但值异常 → 继续尝试下一个 key pattern 或最终返回 unknown

    return "unknown"


def probe_toolbox_path_reachability(
    path: str,
) -> Literal["ok", "invalid", "not_accessible"]:
    """Task 6：区分本地路径不存在 vs UNC/网络不可达。

    - UNC 路径（``\\\\server\\share\\...``）：
      - exists() + os.R_OK 通过 → ``'ok'``
      - 否则 / OSError → ``'not_accessible'``（诊断归类为网络/权限问题）
    - 本地路径（含磁盘盘符或相对）：
      - exists() + os.R_OK 通过 → ``'ok'``
      - 否则 → ``'invalid'``（诊断归类为用户配置错误）

    Args:
        path: 待校验的文件系统路径字符串。

    Returns:
        三态字面量：``'ok'`` / ``'invalid'`` / ``'not_accessible'``。
    """
    p = Path(path)
    if str(p).startswith("\\\\"):  # UNC
        try:
            return "ok" if p.exists() and os.access(p, os.R_OK) else "not_accessible"
        except OSError:
            return "not_accessible"
    return "ok" if p.exists() and os.access(p, os.R_OK) else "invalid"


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
        key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"SldWorks.Application\CLSID")
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


def _check_toolbox_addin_enabled(winreg, version_year: int) -> bool:
    """检查 SolidWorks Toolbox Add-In 是否启用（v4 决策 #13）。

    路径: HKCU\\Software\\SolidWorks\\AddInsStartup
          下遍历所有值；值 1 表示启用，值 0 表示禁用。
          Toolbox 的 Add-In GUID 在 SW 各版本间稳定。

    任何异常（winreg 不可用、路径缺失、读值失败）→ False。
    """
    if winreg is None:
        return False

    # 多个可能的注册表路径（SW 版本间略有差异）
    candidates = [
        r"Software\SolidWorks\AddInsStartup",
        rf"Software\SolidWorks\SOLIDWORKS {version_year}\AddInsStartup",
    ]

    for subkey in candidates:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, subkey, 0, winreg.KEY_READ
            ) as key:
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                    except OSError:
                        break
                    # Toolbox Add-In 的 GUID 特征字符串（保守匹配）
                    # I-3: AddInsStartup 下合法 value name 必为 `{GUID}` 形状；
                    # 用 startswith("{") 守卫防止第三方 Add-In 的友好名误中 "toolbox" 子串。
                    if not name.startswith("{"):
                        i += 1
                        continue
                    if "toolbox" in name.lower() or _is_toolbox_guid(name):
                        try:
                            if int(value) == 1:
                                return True
                        except (TypeError, ValueError):
                            pass  # 非预期类型（字符串/None）→ 视为未启用，继续枚举
                    i += 1
        except (OSError, FileNotFoundError):
            continue

    return False


# Toolbox Add-In 已知 GUID 前缀（保守识别，避免硬编码单一 GUID）
_TOOLBOX_GUID_HINTS = (
    "bbf84e59",  # SW Toolbox Library 常见 GUID 前缀
)


def _is_toolbox_guid(name: str) -> bool:
    """粗略识别注册表值名是否 Toolbox Add-In GUID（v4 决策 #13）。"""
    lowered = name.lower()
    return any(h in lowered for h in _TOOLBOX_GUID_HINTS)


def _read_registry_value(winreg, hive, key_path: str, value_name: str) -> str | None:
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
    for access_flag in (
        winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        winreg.KEY_READ | winreg.KEY_WOW64_32KEY,
    ):
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
