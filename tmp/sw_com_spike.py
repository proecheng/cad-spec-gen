"""SW-B0 COM Spike — Phase SW-B 前置开发机实测。

验证 v4 spec 决策 #10（冷启动 90s 预算）和决策 #23（STEP magic 'ISO-10303'）。

用法::
    python tmp/sw_com_spike.py

不需要任何环境变量；自动发现 Toolbox 目录并选取一个 sldprt 做 OpenDoc6+SaveAs3 测试。
产出: 屏幕输出测量数据；用户手动填入 docs/spikes/2026-04-13-sw-com-spike.md。
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path


def pick_test_sldprt(toolbox_root: Path) -> Path | None:
    """从 Toolbox 目录挑一个小的 hex bolt 作测试目标。"""
    candidates = [
        "GB/bolts and studs/hex bolt.sldprt",
        "ansi inch/bolts/hex bolt.sldprt",
        "iso/bolts/hex bolt.sldprt",
    ]
    for rel in candidates:
        p = toolbox_root / rel
        if p.is_file():
            return p

    # Fallback: first *.sldprt under toolbox_root
    for p in toolbox_root.rglob("*.sldprt"):
        if p.is_file():
            return p
    return None


def main() -> int:
    # 固定路径（用户机器已知）
    toolbox_root = Path(r"C:\SOLIDWORKS Data\browser")
    tmp_step = Path(r"D:\Work\cad-spec-gen\tmp\spike_out.step")
    tmp_step.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("SW-B0 COM Spike")
    print("=" * 60)
    print(f"Toolbox root: {toolbox_root}")
    print(f"Toolbox exists: {toolbox_root.exists()}")

    if not toolbox_root.exists():
        print("\n❌ Toolbox 目录不存在。请检查 SW 安装或 Add-In 是否激活。")
        return 1

    sldprt = pick_test_sldprt(toolbox_root)
    if not sldprt:
        print("\n❌ Toolbox 下找不到任何 sldprt 文件。")
        return 1
    print(f"测试 sldprt: {sldprt}")
    print(f"文件大小: {sldprt.stat().st_size} bytes")
    print()

    # Step 1: Dispatch 冷启动
    print("[1/5] Dispatch SldWorks.Application ...")
    t0 = time.time()
    import win32com.client
    swApp = win32com.client.Dispatch("SldWorks.Application")
    dispatch_time = time.time() - t0
    print(f"    完成 {dispatch_time:.1f}s")

    # Step 2: Visible=False + UserControl=False
    swApp.Visible = False
    try:
        swApp.UserControl = False
    except Exception as e:
        print(f"    ⚠️  UserControl=False 失败（非致命）: {e}")

    # Step 3: LoadAddIn Toolbox
    print("[2/5] LoadAddIn SOLIDWORKS Toolbox ...")
    t1 = time.time()
    try:
        addin_result = swApp.LoadAddIn("SOLIDWORKS Toolbox")
        addin_time = time.time() - t1
        print(f"    返回值 {addin_result}, 耗时 {addin_time:.1f}s")
    except Exception as e:
        addin_time = time.time() - t1
        print(f"    ⚠️  LoadAddIn 异常（非致命）: {e}")
        addin_result = -1

    cold_start_total = dispatch_time + addin_time
    print(f"    ★ 冷启动总耗时: {cold_start_total:.1f}s (预算 90s)")

    # Step 4: OpenDoc6
    print("[3/5] OpenDoc6 Toolbox sldprt ...")
    t2 = time.time()
    errors = 0
    warnings = 0
    try:
        # swDocPART=1, swOpenDocOptions_Silent=1
        model = swApp.OpenDoc6(str(sldprt), 1, 1, "", errors, warnings)
        open_time = time.time() - t2
        print(f"    耗时 {open_time:.1f}s")

        if model is None:
            print("    ❌ model is None —— OpenDoc6 返回失败")
            return 1

        try:
            cfg_mgr = model.ConfigurationManager
            active_cfg = cfg_mgr.ActiveConfiguration
            print(f"    激活 configuration: {active_cfg.Name!r}")
            # 枚举所有 configuration
            cfg_names = model.GetConfigurationNames()
            print(f"    configuration 总数: {len(cfg_names) if cfg_names else 0}")
            if cfg_names and len(cfg_names) <= 10:
                print(f"    所有 configurations: {list(cfg_names)}")
            elif cfg_names:
                print(f"    前 5 个 configurations: {list(cfg_names)[:5]}")
        except Exception as e:
            print(f"    ⚠️  configuration 查询失败: {e}")
    except Exception as e:
        open_time = time.time() - t2
        print(f"    ❌ OpenDoc6 异常 (耗时 {open_time:.1f}s): {e}")
        return 1

    # Step 5: SaveAs3 STEP
    print("[4/5] SaveAs3 STEP ...")
    if tmp_step.exists():
        tmp_step.unlink()
    t3 = time.time()
    try:
        saved = model.Extension.SaveAs3(
            str(tmp_step),
            0,   # version = current
            1,   # options = silent
            None,
            None,
            0, 0,
        )
        save_time = time.time() - t3
        print(f"    saved={saved}, 耗时 {save_time:.1f}s")
    except Exception as e:
        save_time = time.time() - t3
        print(f"    ❌ SaveAs3 异常 (耗时 {save_time:.1f}s): {e}")
        try:
            swApp.CloseDoc(model.GetTitle())
        except Exception:
            pass
        return 1

    # Close doc
    try:
        swApp.CloseDoc(model.GetTitle())
    except Exception:
        pass

    # Step 6: 校验 STEP 产物
    print("[5/5] 校验 STEP 产物 ...")
    if not tmp_step.exists():
        print("    ❌ STEP 文件未生成")
        return 1
    size = tmp_step.stat().st_size
    with tmp_step.open("rb") as f:
        header = f.read(32)
    print(f"    文件大小: {size} bytes")
    print(f"    前 32 字节: {header!r}")
    print(f"    是否 'ISO-10303' 开头: {header.startswith(b'ISO-10303')}")

    # 从 header 里找 units 信息
    with tmp_step.open("r", encoding="utf-8", errors="replace") as f:
        content_head = f.read(3000)
    has_mm = "MILLIMETRE" in content_head.upper() or "MILLIM" in content_head.upper()
    has_inch = "INCH" in content_head.upper()
    has_metre = "METRE" in content_head.upper() and not has_mm
    print(f"    units: mm={has_mm}, inch={has_inch}, metre={has_metre}")

    # 汇总
    print()
    print("=" * 60)
    print("汇总（请填入 spike 报告）:")
    print("=" * 60)
    print(f"  Dispatch:            {dispatch_time:.2f}s")
    print(f"  LoadAddIn Toolbox:   {addin_time:.2f}s (返回 {addin_result})")
    print(f"  冷启动总计:           {cold_start_total:.2f}s (预算 90s)")
    print(f"  OpenDoc6:            {open_time:.2f}s")
    print(f"  SaveAs3:             {save_time:.2f}s")
    print(f"  STEP 文件大小:        {size} bytes")
    print(f"  STEP header ISO-10303: {header.startswith(b'ISO-10303')}")
    print(f"  STEP units 含 mm:     {has_mm}")
    print(f"  决策 #10 (90s 预算):  {'✅ 通过' if cold_start_total <= 90 else '❌ 超预算'}")
    print(f"  决策 #23 (ISO-10303): {'✅ 通过' if header.startswith(b'ISO-10303') else '❌ 不匹配'}")
    print()
    print("Tearing down SW ...")
    try:
        swApp.ExitApp()
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
