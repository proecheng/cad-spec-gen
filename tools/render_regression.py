#!/usr/bin/env python3
"""端到端渲染回归工具 — 对比 baseline（平坦材质）与 enhanced（PBR 纹理）渲染输出。

用法:
    python tools/render_regression.py
    python tools/render_regression.py --dry-run   # 仅做前置检查，不运行 Blender
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# ── 路径常量 ──────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).parent.parent.resolve()

# render_3d.py 和 render_config.py 都在这里
_EE_DIR = _REPO_ROOT / "cad" / "end_effector"
_RENDER_SCRIPT = _EE_DIR / "render_3d.py"

# render_3d.py 默认读取此 GLB 作为场景输入
_GLB_PATH = _REPO_ROOT / "cad" / "output" / "EE-000_assembly.glb"

# 产物根目录
_OUT_ROOT = _REPO_ROOT / "artifacts" / "regression"

# render_config.MATERIAL_PRESETS 需要从子目录导入
sys.path.insert(0, str(_EE_DIR))
sys.path.insert(0, str(_REPO_ROOT))

VIEW_NAMES = [
    "V1_front_iso",
    "V2_rear_oblique",
    "V3_side_elevation",
    "V4_exploded",
    "V5_ortho_front",
]


def _find_blender() -> str:
    """优先 PATH 中的 blender，fallback D:\\Blender\\blender.exe。

    Returns:
        可用 blender 可执行文件的绝对路径字符串。

    Raises:
        FileNotFoundError: 两处均未找到。
    """
    blender_in_path = shutil.which("blender")
    if blender_in_path:
        return blender_in_path

    fallback = Path(r"D:\Blender\blender.exe")
    if fallback.exists():
        return str(fallback)

    raise FileNotFoundError(
        "找不到 Blender 可执行文件。\n"
        "请将 blender 加入 PATH，或确认 D:\\Blender\\blender.exe 存在。"
    )


def run_render(output_dir: Path, extra_env: dict[str, str], dry_run: bool = False) -> bool:
    """调用 Blender 渲染 end_effector 全部 5 视图到 output_dir。

    Args:
        output_dir: PNG 输出目录（自动创建）。
        extra_env:  追加/覆写的环境变量 dict（叠加在 os.environ 上）。
        dry_run:    True 时只打印命令不执行，用于调试。

    Returns:
        True 表示渲染成功，False 表示 Blender 返回非零退出码。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    blender = _find_blender()

    cmd = [
        blender, "-b", "-P", str(_RENDER_SCRIPT),
        "--",
        "--all",
        "--glb", str(_GLB_PATH),
        "--output-dir", str(output_dir),
    ]

    env = {**os.environ, **extra_env}

    print(f"\n[render] 命令: {' '.join(cmd)}")
    print(f"[render] 输出目录: {output_dir}")
    for k, v in extra_env.items():
        print(f"[render] env {k}={v!r}")

    if dry_run:
        print("[render] --dry-run 模式，跳过实际渲染")
        return True

    result = subprocess.run(cmd, env=env, cwd=str(_REPO_ROOT))
    if result.returncode != 0:
        print(f"[render] ❌ Blender 退出码 {result.returncode}")
        return False
    print("[render] ✅ 渲染完成")
    return True


def build_baseline(out_root: Path, dry_run: bool = False) -> bool:
    """渲染 baseline 版本：SW_TEXTURES_DIR 置空，不注入 runtime presets。

    Args:
        out_root: artifacts/regression/ 根目录。
        dry_run:  传递给 run_render。

    Returns:
        True 表示渲染成功。
    """
    print("\n=== BASELINE 渲染（平坦材质）===")
    output_dir = out_root / "baseline" / "end_effector"
    extra_env: dict[str, str] = {"SW_TEXTURES_DIR": ""}
    return run_render(output_dir, extra_env, dry_run=dry_run)


def build_enhanced(out_root: Path, dry_run: bool = False) -> tuple[bool, str]:
    """渲染 enhanced 版本：注入 SW 纹理路径 + runtime_materials.json。

    Returns:
        (success: bool, textures_dir: str)  textures_dir 供 F2 断言使用。
    """
    from adapters.solidworks.sw_detect import detect_solidworks
    from adapters.solidworks.sw_texture_backfill import backfill_presets_for_sw
    from render_config import MATERIAL_PRESETS  # 已在 sys.path 中（_EE_DIR）

    print("\n=== ENHANCED 渲染（PBR 纹理）===")

    sw_info = detect_solidworks()
    textures_dir = getattr(sw_info, "textures_dir", "") or ""

    if not sw_info.installed:
        print("[enhanced] ⚠️  SolidWorks 未装机，enhanced 渲染将等同 baseline")
    elif not textures_dir:
        print("[enhanced] ⚠️  textures_dir 为空，纹理回填为 no-op")
    else:
        print(f"[enhanced] SW textures_dir: {textures_dir}")

    runtime_presets = backfill_presets_for_sw(MATERIAL_PRESETS, sw_info)

    enhanced_dir = out_root / "enhanced"
    enhanced_dir.mkdir(parents=True, exist_ok=True)
    json_path = enhanced_dir / "runtime_materials.json"
    json_path.write_text(json.dumps(runtime_presets, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[enhanced] runtime_materials.json → {json_path}")

    output_dir = enhanced_dir / "end_effector"
    extra_env: dict[str, str] = {
        "SW_TEXTURES_DIR": textures_dir,
        "CAD_RUNTIME_MATERIAL_PRESETS_JSON": str(json_path),
    }

    success = run_render(output_dir, extra_env, dry_run=dry_run)
    return success, textures_dir


def assert_features(out_root: Path, textures_dir: str) -> dict:
    """运行 5 项 feature 断言，返回结果 dict。

    Returns:
        {
          "F1": {"ok": bool, "detail": str},
          "F2": {"ok": bool, "detail": str},
          "F3": {"ok": bool | None, "detail": str},
          "F4": {"ok": bool, "detail": str},
          "F5": {"ok": bool, "detail": str},
        }
    """
    results: dict[str, dict] = {}

    # F1: enhanced runtime_materials.json 至少 1 个 preset 含 base_color_texture
    json_path = out_root / "enhanced" / "runtime_materials.json"
    if json_path.exists():
        data = json.loads(json_path.read_text(encoding="utf-8"))
        has_texture = any(
            "base_color_texture" in preset
            for preset in data.values()
            if isinstance(preset, dict)
        )
        results["F1"] = {
            "ok": has_texture,
            "detail": "base_color_texture 字段存在" if has_texture else "无 base_color_texture（SW 未装或纹理回填失败）",
        }
    else:
        results["F1"] = {"ok": False, "detail": "runtime_materials.json 不存在"}

    # F2: SW_TEXTURES_DIR 目录存在且非空
    if textures_dir and os.path.isdir(textures_dir):
        files = os.listdir(textures_dir)
        ok = len(files) > 0
        results["F2"] = {"ok": ok, "detail": f"{len(files)} 个文件/子目录" if ok else "目录为空"}
    else:
        results["F2"] = {"ok": False, "detail": f"目录不存在或为空: {textures_dir!r}"}

    # F3: 最近 resolve_report.json 中 sw_toolbox 命中数 >= 1
    import glob as _glob
    reports = sorted(
        _glob.glob(str(_REPO_ROOT / "artifacts" / "*" / "resolve_report.json"))
    )
    if reports:
        rpt = json.loads(Path(reports[-1]).read_text(encoding="utf-8"))
        sw_hits = rpt.get("adapter_hits", {}).get("sw_toolbox", {}).get("count", 0)
        ok = sw_hits >= 1
        results["F3"] = {
            "ok": ok,
            "detail": f"sw_toolbox 命中 {sw_hits} 次（来自 {Path(reports[-1]).parent.name}）",
        }
    else:
        results["F3"] = {
            "ok": None,
            "detail": "未找到 resolve_report.json，先运行 sw-inspect --resolve-report",
        }

    # F4: enhanced V1 PNG 文件大小比 baseline V1 大 5% 以上
    v1_base = out_root / "baseline" / "end_effector" / "V1_front_iso.png"
    v1_enh = out_root / "enhanced" / "end_effector" / "V1_front_iso.png"
    if v1_base.exists() and v1_enh.exists():
        sz_base = v1_base.stat().st_size
        sz_enh = v1_enh.stat().st_size
        ratio = (sz_enh - sz_base) / sz_base if sz_base > 0 else 0.0
        ok = ratio > 0.05
        results["F4"] = {
            "ok": ok,
            "detail": f"enhanced/baseline 大小比：{ratio:+.1%}（{sz_enh:,}B / {sz_base:,}B）",
        }
    else:
        missing = []
        if not v1_base.exists():
            missing.append("baseline V1")
        if not v1_enh.exists():
            missing.append("enhanced V1")
        results["F4"] = {"ok": False, "detail": f"PNG 不存在: {', '.join(missing)}"}

    # F5: baseline 和 enhanced 两组 PNG 均非全黑（max pixel > 10）
    all_pngs = list((out_root / "baseline" / "end_effector").glob("*.png")) + \
               list((out_root / "enhanced" / "end_effector").glob("*.png"))
    if not all_pngs:
        results["F5"] = {"ok": False, "detail": "PNG 文件不存在"}
    else:
        try:
            from PIL import Image
            black_files = []
            for p in all_pngs:
                img = Image.open(p).convert("L")
                if max(img.getdata()) <= 10:  # type: ignore[arg-type]
                    black_files.append(p.name)
            ok = len(black_files) == 0
            results["F5"] = {
                "ok": ok,
                "detail": "所有 PNG 非全黑" if ok else f"全黑文件: {black_files}",
            }
        except ImportError:
            ok = all(p.stat().st_size > 1024 for p in all_pngs)
            results["F5"] = {
                "ok": ok,
                "detail": f"PIL 未安装，退化为文件大小检查（>1KB），{len(all_pngs)} 个文件{'均通过' if ok else '有失败'}",
            }

    return results


def write_report(
    feature_results: dict,
    out_root: Path,
    render_ok_baseline: bool,
    render_ok_enhanced: bool,
) -> Path:
    """生成 artifacts/regression/report.md。

    Returns:
        report.md 的 Path。
    """
    def mark(result: dict) -> str:
        if result["ok"] is None:
            return f"N/A — {result['detail']}"
        return f"{'✅' if result['ok'] else '❌'} {result['detail']}"

    lines = [
        "# 渲染回归报告",
        "",
        "## 渲染状态",
        "",
        "| 模式 | 状态 |",
        "|------|------|",
        f"| baseline | {'✅ 成功' if render_ok_baseline else '❌ RENDER_FAILED'} |",
        f"| enhanced | {'✅ 成功' if render_ok_enhanced else '❌ RENDER_FAILED'} |",
        "",
        "## Feature 断言",
        "",
        "| 断言 | 结果 |",
        "|------|------|",
        f"| F1 base_color_texture 字段存在 | {mark(feature_results['F1'])} |",
        f"| F2 SW_TEXTURES_DIR 目录存在且非空 | {mark(feature_results['F2'])} |",
        f"| F3 sw_toolbox 命中数 ≥ 1（项目级） | {mark(feature_results['F3'])} |",
        f"| F4 enhanced PNG 大小 > baseline 5% | {mark(feature_results['F4'])} |",
        f"| F5 所有 PNG 非全黑 | {mark(feature_results['F5'])} |",
        "",
        "## 图片索引",
        "",
        "| 视图 | baseline | enhanced |",
        "|------|----------|----------|",
    ]

    for view in VIEW_NAMES:
        b = f"baseline/end_effector/{view}.png"
        e = f"enhanced/end_effector/{view}.png"
        lines.append(f"| {view} | {b} | {e} |")

    lines += [
        "",
        "## 肉眼观察（人工填写）",
        "",
    ]
    for view in VIEW_NAMES:
        lines += [
            f"### {view}",
            "- baseline: ___",
            "- enhanced: ___",
            "- 改善描述: ___",
            "",
        ]

    report_path = out_root / "report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[report] 报告已写入: {report_path}")
    return report_path


def _preflight_check(dry_run: bool) -> None:
    """前置检查：Blender 可用 + GLB 存在。"""
    blender = _find_blender()
    print(f"[preflight] Blender: {blender}")

    if not _GLB_PATH.exists():
        if dry_run:
            print(f"[preflight] ⚠️  GLB 不存在（dry-run 模式不中断）: {_GLB_PATH}")
        else:
            raise FileNotFoundError(
                f"GLB 不存在: {_GLB_PATH}\n"
                "请先运行: python cad/end_effector/build_all.py"
            )
    else:
        print(f"[preflight] GLB: {_GLB_PATH}")


def main() -> None:
    """主函数：解析参数，运行完整的渲染回归流程。"""
    parser = argparse.ArgumentParser(description="端到端渲染回归工具")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅做前置检查，打印命令，不实际调用 Blender",
    )
    args = parser.parse_args()

    out_root = _OUT_ROOT
    out_root.mkdir(parents=True, exist_ok=True)

    print(f"[main] 产物根目录: {out_root}")

    _preflight_check(args.dry_run)

    ok_baseline = build_baseline(out_root, dry_run=args.dry_run)
    ok_enhanced, textures_dir = build_enhanced(out_root, dry_run=args.dry_run)

    feature_results = assert_features(out_root, textures_dir)

    report_path = write_report(feature_results, out_root, ok_baseline, ok_enhanced)

    print("\n=== 断言摘要 ===")
    all_pass = True
    for key, res in feature_results.items():
        mark = "✅" if res["ok"] else ("⬜" if res["ok"] is None else "❌")
        print(f"  {key} {mark}: {res['detail']}")
        if res["ok"] is False:
            all_pass = False

    print(f"\n[main] 报告: {report_path}")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
