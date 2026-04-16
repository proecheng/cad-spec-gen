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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from adapters.solidworks import sw_detect
from adapters.solidworks import sw_toolbox_catalog
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


def probe_toolbox_index_cache(sw_cfg: dict, info: SwInfo) -> ProbeResult:
    """层：Toolbox index 缓存健康度（对齐 spec §3.4 真实结构）。

    - entry_count：probe 自行聚合 standards dict
    - by_standard：从 idx["standards"] 的 key 直接聚合，无硬编码白名单
    - stale：cached_fp 与 current_fp 不一致时（两端均非 "unavailable"）为 True
    """
    try:
        index_path = sw_toolbox_catalog.get_toolbox_index_path(sw_cfg)
    except Exception as e:
        return ProbeResult(
            layer="toolbox_index",
            ok=False,
            severity="fail",
            summary="解析 index 路径异常",
            data={"exists": False},
            error=str(e)[:200],
        )

    exists = index_path.is_file()
    size_bytes = index_path.stat().st_size if exists else 0

    if not exists:
        return ProbeResult(
            layer="toolbox_index",
            ok=True,
            severity="warn",
            summary=f"index 缓存不存在：{index_path}",
            data={
                "index_path": str(index_path),
                "exists": False,
                "entry_count": 0,
                "toolbox_fingerprint_cached": "",
                "toolbox_fingerprint_current": "",
                "stale": False,
                "size_bytes": 0,
                "by_standard": {},
            },
            hint="运行 `cad_pipeline.py sw-warmup --standard GB --dry-run` 首次生成索引",
        )

    if not info.installed or not info.toolbox_dir:
        return ProbeResult(
            layer="toolbox_index",
            ok=True,
            severity="warn",
            summary="SW 未安装或 toolbox_dir 不明，跳过 fingerprint 校验",
            data={
                "index_path": str(index_path),
                "exists": True,
                "entry_count": 0,
                "toolbox_fingerprint_cached": "",
                "toolbox_fingerprint_current": "",
                "stale": False,
                "size_bytes": size_bytes,
                "by_standard": {},
            },
        )

    try:
        toolbox_dir = Path(info.toolbox_dir)
        idx = sw_toolbox_catalog.load_toolbox_index(index_path, toolbox_dir)
        cached_fp = idx.get("toolbox_fingerprint", "")
        current_fp = sw_toolbox_catalog._compute_toolbox_fingerprint(toolbox_dir)
        standards = idx.get("standards", {})
        entry_count = sum(
            len(sub) for std_dict in standards.values() for sub in std_dict.values()
        )
        by_standard = {
            std: sum(len(sub) for sub in std_dict.values())
            for std, std_dict in standards.items()
        }
        stale = (
            cached_fp != current_fp
            and cached_fp != "unavailable"
            and current_fp != "unavailable"
        )

        data = {
            "index_path": str(index_path),
            "exists": True,
            "entry_count": entry_count,
            "toolbox_fingerprint_cached": cached_fp,
            "toolbox_fingerprint_current": current_fp,
            "stale": stale,
            "size_bytes": size_bytes,
            "by_standard": by_standard,
        }
        if stale:
            return ProbeResult(
                layer="toolbox_index",
                ok=True,
                severity="warn",
                summary=f"index 已 stale（cached {cached_fp[:8]} vs current {current_fp[:8]}），{entry_count} 条",
                data=data,
                hint="删除 index JSON 后重跑 sw-warmup 刷新；或 sw-warmup 自身会 fingerprint mismatch 触发重建",
            )
        return ProbeResult(
            layer="toolbox_index",
            ok=True,
            severity="ok",
            summary=f"index 健康，{entry_count} 条；{', '.join(f'{k}={v}' for k, v in by_standard.items())}",
            data=data,
        )
    except Exception as e:
        return ProbeResult(
            layer="toolbox_index",
            ok=False,
            severity="fail",
            summary="index 加载异常",
            data={
                "index_path": str(index_path),
                "exists": True,
                "size_bytes": size_bytes,
            },
            error=str(e)[:200],
        )


_STEP_COUNT_DOWNGRADE_THRESHOLD = 5000


def _read_last_line(path: Path) -> Optional[str]:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            lines = [ln.rstrip("\r\n") for ln in fh if ln.strip()]
        return lines[-1] if lines else None
    except Exception:
        return None


def _try_acquire_lock(lock_path: Path) -> tuple[bool, Optional[int]]:
    """non-blocking try-acquire：拿到 → 立即 release → 返回 (held_by_other=False, None)；
    EAGAIN → (True, pid_or_None)。"""
    if not lock_path.exists():
        return False, None
    try:
        if sys.platform == "win32":
            import msvcrt

            with lock_path.open("a+") as fh:
                fh.seek(0)
                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                    return False, None
                except OSError:
                    return True, None
        else:
            import fcntl

            with lock_path.open("a+") as fh:
                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                    return False, None
                except (OSError, BlockingIOError):
                    return True, None
    except Exception:
        return False, None


def probe_warmup_artifacts(sw_cfg: dict) -> ProbeResult:
    """层：warmup 产物快照。

    路径（对齐 spec §3.3 常量表）：
      home = Path.home() / ".cad-spec-gen"
      lock_path = home / "sw_warmup.lock"
      error_log_path = home / "sw_warmup_errors.log"
      step_cache_root = get_toolbox_cache_root(sw_cfg)

    SA-2：lock 用 non-blocking try + immediate release，不与 sw-warmup 争锁。
    SAR-3：step_files > _STEP_COUNT_DOWNGRADE_THRESHOLD 时跳过 size 计算。
    """
    try:
        home = Path.home() / ".cad-spec-gen"
        lock_path = home / "sw_warmup.lock"
        error_log_path = home / "sw_warmup_errors.log"
        step_cache_root = sw_toolbox_catalog.get_toolbox_cache_root(sw_cfg)
    except Exception as e:
        return ProbeResult(
            layer="warmup",
            ok=False,
            severity="fail",
            summary="warmup 路径解析异常",
            data={},
            error=str(e)[:200],
        )

    lock_held, lock_pid = _try_acquire_lock(lock_path)
    error_log_last = (
        _read_last_line(error_log_path) if error_log_path.exists() else None
    )
    error_log_mtime = None
    if error_log_path.exists():
        ts = datetime.fromtimestamp(error_log_path.stat().st_mtime, tz=timezone.utc)
        error_log_mtime = ts.isoformat().replace("+00:00", "Z")

    step_files = 0
    step_size_bytes = 0
    if step_cache_root.is_dir():
        step_paths = list(step_cache_root.rglob("*.step"))
        step_files = len(step_paths)
        if step_files <= _STEP_COUNT_DOWNGRADE_THRESHOLD:
            step_size_bytes = sum(p.stat().st_size for p in step_paths if p.is_file())

    data = {
        "home": str(home),
        "step_cache_root": str(step_cache_root),
        "step_files": step_files,
        "step_size_bytes": step_size_bytes,
        "lock_path": str(lock_path),
        "lock_held": lock_held,
        "lock_pid": lock_pid,
        "error_log_path": str(error_log_path),
        "error_log_last_line": error_log_last,
        "error_log_mtime": error_log_mtime,
    }

    if error_log_last or lock_held:
        parts = []
        if error_log_last:
            parts.append("error_log 有内容")
        if lock_held:
            parts.append("另一进程持有 warmup 锁")
        return ProbeResult(
            layer="warmup",
            ok=True,
            severity="warn",
            summary=f"warmup: {'; '.join(parts)}；STEP {step_files} 件",
            data=data,
            hint="查看 sw_warmup_errors.log 末行；或等待占锁进程释放",
        )
    if step_files == 0:
        return ProbeResult(
            layer="warmup",
            ok=True,
            severity="warn",
            summary="warmup 缓存为空；尚未跑过 sw-warmup",
            data=data,
            hint="运行 `cad_pipeline.py sw-warmup --standard GB` 预热常用 Toolbox",
        )
    return ProbeResult(
        layer="warmup",
        ok=True,
        severity="ok",
        summary=f"STEP {step_files} 件 / {step_size_bytes // 1024} KiB",
        data=data,
    )


def probe_material_files(info: SwInfo) -> ProbeResult:
    """层：材质/贴图/P2M 文件数（仅 count；不解析 XML，见 spec ME-2 升级路径）。"""
    sldmat_count = len(info.sldmat_paths or [])
    tex_cats = 0
    tex_total = 0
    p2m_count = 0

    try:
        tex_root = Path(info.textures_dir) if info.textures_dir else None
        if tex_root and tex_root.is_dir():
            cats = [p for p in tex_root.iterdir() if p.is_dir()]
            tex_cats = len(cats)
            for cat in cats:
                tex_total += sum(1 for _ in cat.iterdir() if _.is_file())

        p2m_root = Path(info.p2m_dir) if info.p2m_dir else None
        if p2m_root and p2m_root.is_dir():
            p2m_count = sum(1 for p in p2m_root.iterdir() if p.suffix.lower() == ".p2m")
    except Exception as e:
        return ProbeResult(
            layer="materials",
            ok=False,
            severity="fail",
            summary="材质目录扫描异常",
            data={
                "sldmat_files": sldmat_count,
                "textures_categories": tex_cats,
                "textures_total": tex_total,
                "p2m_files": p2m_count,
            },
            error=str(e)[:200],
        )

    data = {
        "sldmat_files": sldmat_count,
        "textures_categories": tex_cats,
        "textures_total": tex_total,
        "p2m_files": p2m_count,
    }
    all_zero = sldmat_count == 0 and tex_cats == 0 and p2m_count == 0
    if all_zero:
        return ProbeResult(
            layer="materials",
            ok=True,
            severity="warn",
            summary="未找到任何材质/贴图/P2M 文件",
            data=data,
            hint="检查 SW 安装是否完整；或确认 SwInfo 的 textures_dir / p2m_dir 已正确解析",
        )
    return ProbeResult(
        layer="materials",
        ok=True,
        severity="ok",
        summary=f"sldmat={sldmat_count} textures_cats={tex_cats} textures={tex_total} p2m={p2m_count}",
        data=data,
    )
