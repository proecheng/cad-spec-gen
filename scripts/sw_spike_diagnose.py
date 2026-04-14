"""SW-B0 spike 诊断脚本：在 Python → win32com → COM → SldWorks → LoadAddIn
每层边界打日志，定位"开发机 SW 启动失败"的精确断点。

不调 _start_locked，不绕过现有代码；只在最底层逐步抬起。
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def _fail(layer: str, exc: BaseException) -> None:
    print(f"  [FAIL@{layer}] {type(exc).__name__}: {exc}")
    traceback.print_exc()


def main() -> int:
    print("=" * 60)
    print("SW-B0 spike diagnose — 逐层边界探测")
    print("=" * 60)

    # 层 0：Python 版本 + 平台
    print(f"\n[层 0] python={sys.version.split()[0]} platform={sys.platform} arch={8 * sys.maxsize.bit_length() // 63}-bit pid={os.getpid()}")

    # 层 1：pywin32 import
    print("\n[层 1] import win32com.client")
    try:
        import win32com.client  # noqa: F401
        _ok(f"win32com.client imported from {win32com.client.__file__}")
    except Exception as e:
        _fail("层 1", e)
        print("\n诊断结论：pywin32 未安装或不兼容当前 Python。跑 `pip install pywin32` 再试。")
        return 1

    # 层 2：detect_solidworks — 静态检测
    print("\n[层 2] detect_solidworks()")
    try:
        from adapters.solidworks.sw_detect import detect_solidworks, _reset_cache
        _reset_cache()
        info = detect_solidworks()
        print(f"  installed={info.installed}")
        print(f"  version_year={info.version_year}")
        print(f"  pywin32_available={info.pywin32_available}")
        print(f"  toolbox_dir={info.toolbox_dir}")
        print(f"  toolbox_addin_enabled={info.toolbox_addin_enabled}")
        print(f"  sldworks_exe={getattr(info, 'sldworks_exe', '(未暴露)')}")
        if not info.installed:
            print("\n诊断结论：detect_solidworks 认为 SW 未安装。检查注册表 HKLM\\SOFTWARE\\SolidWorks\\SOLIDWORKS 202X。")
            return 2
        _ok("静态检测通过")
    except Exception as e:
        _fail("层 2", e)
        return 2

    # 层 3：CLSID 注册表查询（不启动进程）
    print("\n[层 3] 查 SldWorks.Application 的 CLSID（纯注册表读，不启进程）")
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"SldWorks.Application\CLSID") as k:
            clsid, _ = winreg.QueryValueEx(k, "")
        print(f"  CLSID={clsid}")
        _ok("progid 已注册")
    except Exception as e:
        _fail("层 3", e)
        print("\n诊断结论：SldWorks.Application 的 progid 未注册。SW 装了但 COM server 没注册。跑管理员权限 'sldworks.exe /regserver'。")
        return 3

    # 层 4：win32com.client.Dispatch — 启动或附着 SW 进程
    #       关键：这是最常见的失败点。打 wall-clock 计时 + 连接池状态。
    print("\n[层 4] win32com.client.Dispatch('SldWorks.Application')")
    print("      (首次冷启动可能 60-90 秒；观察任务管理器 SLDWORKS.exe 是否出现)")
    t0 = time.monotonic()
    try:
        import win32com.client
        app = win32com.client.Dispatch("SldWorks.Application")
        elapsed = time.monotonic() - t0
        _ok(f"Dispatch 返回，耗时 {elapsed:.1f}s")
        # 能拿到 app 就说明 COM 通了；取 Revision 确认不是空壳
        try:
            rev = app.RevisionNumber
            _ok(f"RevisionNumber={rev}")
        except Exception as e:
            print(f"  [WARN] Dispatch OK 但 RevisionNumber 取值失败: {e}")
        # Visibility 控制（不强制显示窗口）
        try:
            app.Visible = False
            _ok("Visible=False 设置成功（后台模式）")
        except Exception as e:
            print(f"  [WARN] Visible 设置失败: {e}")
    except Exception as e:
        elapsed = time.monotonic() - t0
        print(f"  [FAIL@层 4] 耗时 {elapsed:.1f}s 才抛出")
        _fail("层 4", e)
        print("\n诊断结论：COM Dispatch 本身失败。可能原因：")
        print("  - SW 许可证过期 / 未激活")
        print("  - Python 与 SW 位数不匹配（64-bit Python 必须对 64-bit SW）")
        print("  - 注册表 progid 存在但 .exe 路径错误（重装或路径迁移过）")
        print("  - SW 正在另一个会话中独占运行")
        return 4

    # 层 5：LoadAddIn（Toolbox 加载是后续 convert 的前置）
    print("\n[层 5] LoadAddIn('SwToolbox')")
    try:
        # progid 形式（v4 spec）；某些 SW 版本用 SldWorks.SwToolbox
        for addin_id in ["SwToolbox.1", "SwToolbox"]:
            rc = app.LoadAddIn(addin_id)
            print(f"  LoadAddIn({addin_id!r}) → {rc}")
            if rc == 1:
                _ok(f"{addin_id} 加载成功")
                break
        else:
            print("\n诊断结论：LoadAddIn 返回非 1。Tools → Add-Ins 里手动勾选 'SOLIDWORKS Toolbox Library' 后重跑。")
    except Exception as e:
        _fail("层 5", e)
        print("\n诊断结论：LoadAddIn 本身抛异常。可能 SW 版本不支持此 progid。")

    # 层 6：尝试关掉 SW 会话（以免在诊断间悬挂）
    print("\n[层 6] 主动 ExitApp 以清退诊断用会话")
    try:
        app.ExitApp()
        _ok("ExitApp 调用返回")
    except Exception as e:
        print(f"  [WARN] ExitApp 失败（可忽略，进程可能已独立运行）: {e}")

    print("\n" + "=" * 60)
    print("诊断完成")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
