# Render Regression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建 `tools/render_regression.py`，对 `end_effector` 子系统执行 baseline/enhanced 双模 Blender 渲染对比，运行 5 项 feature 断言，输出 `artifacts/regression/report.md`。

**Architecture:** 单文件脚本，7 个函数依次调用：`_find_blender` → `run_render` → `build_baseline` / `build_enhanced` → `assert_features` → `write_report`。无需改动现有代码（`render_3d.py` / `sw_texture_backfill.py` 均保持原状）。

**Tech Stack:** Python 3.11+ stdlib（subprocess / json / pathlib / shutil）+ Blender 4.x CLI + `adapters.solidworks.sw_detect` + `adapters.solidworks.sw_texture_backfill` + `cad.end_effector.render_config.MATERIAL_PRESETS` + PIL（可选，F5 断言）

---

## 文件映射

| 文件 | 动作 | 职责 |
|------|------|------|
| `tools/render_regression.py` | 新建 | 全部逻辑 |
| `artifacts/regression/` | 运行时生成 | baseline/enhanced PNG + runtime_materials.json + report.md |

---

### Task 0：脚本骨架与常量定义

**Files:**
- Create: `tools/render_regression.py`

- [ ] **Step 1: 创建脚本骨架**

```python
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
```

- [ ] **Step 2: 验证文件创建成功**

```bash
python -c "import tools.render_regression" 2>&1 || python tools/render_regression.py --help
```

预期：无 ImportError（此时还没有 `main()`，会报 AttributeError 或直接退出）。

- [ ] **Step 3: 提交骨架**

```bash
git add tools/render_regression.py
git commit -m "feat(regression): 渲染回归脚本骨架与路径常量"
```

---

### Task 1：`_find_blender()` — Blender 可执行文件自动探测

**Files:**
- Modify: `tools/render_regression.py`

- [ ] **Step 1: 实现 `_find_blender()`**

```python
def _find_blender() -> str:
    """优先 PATH 中的 blender，fallback D:\\Blender\\blender.exe。

    Returns:
        可用 blender 可执行文件的绝对路径字符串。

    Raises:
        FileNotFoundError: 两处均未找到。
    """
    # 先尝试 PATH
    blender_in_path = shutil.which("blender")
    if blender_in_path:
        return blender_in_path

    # Windows fallback
    fallback = Path(r"D:\Blender\blender.exe")
    if fallback.exists():
        return str(fallback)

    raise FileNotFoundError(
        "找不到 Blender 可执行文件。\n"
        "请将 blender 加入 PATH，或确认 D:\\Blender\\blender.exe 存在。"
    )
```

- [ ] **Step 2: 手动验证**

```bash
python -c "
import sys; sys.path.insert(0,'tools')
# 直接 exec 文件，因为 tools/ 没有 __init__.py
exec(open('tools/render_regression.py').read())
print(_find_blender())
"
```

预期输出：`D:\Blender\blender.exe`（或 PATH 中的路径）。

- [ ] **Step 3: 提交**

```bash
git add tools/render_regression.py
git commit -m "feat(regression): _find_blender 自动探测 Blender 路径"
```

---

### Task 2：`run_render()` — Blender 子进程调用

**Files:**
- Modify: `tools/render_regression.py`

- [ ] **Step 1: 实现 `run_render()`**

```python
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
```

- [ ] **Step 2: 验证命令格式（dry-run）**

```bash
python -c "
exec(open('tools/render_regression.py').read())
run_render(Path('artifacts/regression/test'), {}, dry_run=True)
"
```

预期：打印 Blender 命令行，无实际调用。

- [ ] **Step 3: 提交**

```bash
git add tools/render_regression.py
git commit -m "feat(regression): run_render Blender 子进程调用"
```

---

### Task 3：`build_baseline()` — 平坦材质基线渲染

**Files:**
- Modify: `tools/render_regression.py`

- [ ] **Step 1: 实现 `build_baseline()`**

```python
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
    # 显式置空 SW_TEXTURES_DIR，让 render_3d.py 用内置平坦材质
    extra_env: dict[str, str] = {"SW_TEXTURES_DIR": ""}
    # 不设 CAD_RUNTIME_MATERIAL_PRESETS_JSON → render_3d.py 用默认 MATERIAL_PRESETS
    return run_render(output_dir, extra_env, dry_run=dry_run)
```

- [ ] **Step 2: 验证（dry-run）**

```bash
python -c "
exec(open('tools/render_regression.py').read())
build_baseline(Path('artifacts/regression'), dry_run=True)
"
```

预期：打印 `=== BASELINE 渲染（平坦材质）===` 和命令，env 中 `SW_TEXTURES_DIR=''`。

- [ ] **Step 3: 提交**

```bash
git add tools/render_regression.py
git commit -m "feat(regression): build_baseline 平坦材质基线渲染"
```

---

### Task 4：`build_enhanced()` — PBR 纹理增强版渲染

**Files:**
- Modify: `tools/render_regression.py`

- [ ] **Step 1: 实现 `build_enhanced()`**

```python
def build_enhanced(out_root: Path, dry_run: bool = False) -> tuple[bool, str]:
    """渲染 enhanced 版本：注入 SW 纹理路径 + runtime_materials.json。

    流程：
    1. detect_solidworks() 获取 SwInfo
    2. backfill_presets_for_sw(MATERIAL_PRESETS, sw_info) 生成含纹理字段的 preset
    3. 写 out_root/enhanced/runtime_materials.json（F1 断言用）
    4. 以 CAD_RUNTIME_MATERIAL_PRESETS_JSON + SW_TEXTURES_DIR 调用 Blender

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

    # 写 runtime_materials.json
    enhanced_dir = out_root / "enhanced"
    enhanced_dir.mkdir(parents=True, exist_ok=True)
    json_path = enhanced_dir / "runtime_materials.json"
    json_path.write_text(json.dumps(runtime_presets, indent=2, ensure_ascii=False))
    print(f"[enhanced] runtime_materials.json → {json_path}")

    output_dir = enhanced_dir / "end_effector"
    extra_env: dict[str, str] = {
        "SW_TEXTURES_DIR": textures_dir,
        "CAD_RUNTIME_MATERIAL_PRESETS_JSON": str(json_path),
    }

    success = run_render(output_dir, extra_env, dry_run=dry_run)
    return success, textures_dir
```

- [ ] **Step 2: 验证 SW detect + backfill（dry-run）**

```bash
python -c "
exec(open('tools/render_regression.py').read())
ok, td = build_enhanced(Path('artifacts/regression'), dry_run=True)
print('textures_dir:', td)
import json, pathlib
j = pathlib.Path('artifacts/regression/enhanced/runtime_materials.json')
if j.exists():
    data = json.loads(j.read_text())
    keys = list(data.keys())[:3]
    print('preset keys sample:', keys)
    first = data[keys[0]]
    print('first preset fields:', list(first.keys()))
"
```

预期：
- 打印 `SW textures_dir: C:\Program Files\...` 或 `⚠️ SolidWorks 未装机`
- `artifacts/regression/enhanced/runtime_materials.json` 存在
- enhanced preset 若 SW 有效，应含 `texture_albedo` 等字段

- [ ] **Step 3: 提交**

```bash
git add tools/render_regression.py
git commit -m "feat(regression): build_enhanced SW 检测+纹理回填+增强渲染"
```

---

### Task 5：`assert_features()` — 5 项量化断言

**Files:**
- Modify: `tools/render_regression.py`

- [ ] **Step 1: 实现 `assert_features()`**

```python
def assert_features(out_root: Path, textures_dir: str) -> dict:
    """运行 5 项 feature 断言，返回结果 dict。

    Args:
        out_root:     artifacts/regression/ 根目录。
        textures_dir: build_enhanced() 返回的 SW 纹理目录路径。

    Returns:
        dict，结构：
        {
          "F1": {"ok": bool, "detail": str},
          "F2": {"ok": bool, "detail": str},
          "F3": {"ok": bool | None, "detail": str},   # None = N/A
          "F4": {"ok": bool, "detail": str},
          "F5": {"ok": bool, "detail": str},
        }
    """
    results: dict[str, dict] = {}

    # F1: enhanced runtime_materials.json 至少 1 个 preset 含 texture_albedo
    json_path = out_root / "enhanced" / "runtime_materials.json"
    if json_path.exists():
        data = json.loads(json_path.read_text(encoding="utf-8"))
        has_texture = any(
            "texture_albedo" in preset
            for preset in data.values()
            if isinstance(preset, dict)
        )
        results["F1"] = {
            "ok": has_texture,
            "detail": "texture_albedo 字段存在" if has_texture else "无 texture_albedo（SW 未装或纹理回填失败）",
        }
    else:
        results["F1"] = {"ok": False, "detail": "runtime_materials.json 不存在"}

    # F2: SW_TEXTURES_DIR 目录存在且非空
    if textures_dir and os.path.isdir(textures_dir):
        files = os.listdir(textures_dir)
        ok = len(files) > 0
        results["F2"] = {"ok": ok, "detail": f"{len(files)} 个文件" if ok else "目录为空"}
    else:
        results["F2"] = {"ok": False, "detail": f"目录不存在或为空: {textures_dir!r}"}

    # F3: 最近 resolve_report.json 中 sw_toolbox 命中数 ≥ 1
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
```

- [ ] **Step 2: 验证断言函数（不依赖 Blender 输出）**

```bash
python -c "
exec(open('tools/render_regression.py').read())
# 用现有 enhanced/runtime_materials.json 测试 F1/F2
r = assert_features(Path('artifacts/regression'), '')
for k, v in r.items():
    mark = '✅' if v['ok'] else ('N/A' if v['ok'] is None else '❌')
    print(f'{k} {mark}: {v[\"detail\"]}')
"
```

预期：F1/F2 因缺 PNG 而 F4/F5 为 ❌，F3 视 resolve_report 存在与否显示 ✅ 或 N/A。

- [ ] **Step 3: 提交**

```bash
git add tools/render_regression.py
git commit -m "feat(regression): assert_features 5 项量化断言实现"
```

---

### Task 6：`write_report()` — 输出 report.md

**Files:**
- Modify: `tools/render_regression.py`

- [ ] **Step 1: 实现 `write_report()`**

```python
def write_report(
    feature_results: dict,
    out_root: Path,
    render_ok_baseline: bool,
    render_ok_enhanced: bool,
) -> Path:
    """生成 artifacts/regression/report.md。

    Args:
        feature_results:      assert_features() 的返回值。
        out_root:             artifacts/regression/ 根目录。
        render_ok_baseline:   build_baseline() 是否成功。
        render_ok_enhanced:   build_enhanced() 是否成功。

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
        f"| 模式 | 状态 |",
        f"|------|------|",
        f"| baseline | {'✅ 成功' if render_ok_baseline else '❌ RENDER_FAILED'} |",
        f"| enhanced | {'✅ 成功' if render_ok_enhanced else '❌ RENDER_FAILED'} |",
        "",
        "## Feature 断言",
        "",
        "| 断言 | 结果 |",
        "|------|------|",
        f"| F1 texture_albedo 字段存在 | {mark(feature_results['F1'])} |",
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
```

- [ ] **Step 2: 验证报告生成**

```bash
python -c "
exec(open('tools/render_regression.py').read())
dummy = {k: {'ok': True, 'detail': 'test'} for k in ['F1','F2','F4','F5']}
dummy['F3'] = {'ok': None, 'detail': 'N/A'}
p = write_report(dummy, Path('artifacts/regression'), True, True)
print(open(p).read()[:500])
"
```

预期：打印 report.md 前 500 字符，包含断言表格和图片索引。

- [ ] **Step 3: 提交**

```bash
git add tools/render_regression.py
git commit -m "feat(regression): write_report 输出 report.md"
```

---

### Task 7：CLI `main()` + 完整 smoke test

**Files:**
- Modify: `tools/render_regression.py`

- [ ] **Step 1: 实现 `main()` 和 CLI 入口**

```python
def _preflight_check(dry_run: bool) -> None:
    """前置检查：Blender 可用 + GLB 存在。"""
    blender = _find_blender()
    print(f"[preflight] Blender: {blender}")

    if not dry_run and not _GLB_PATH.exists():
        raise FileNotFoundError(
            f"GLB 不存在: {_GLB_PATH}\n"
            "请先运行: python cad/end_effector/build_all.py"
        )
    if dry_run and not _GLB_PATH.exists():
        print(f"[preflight] ⚠️  GLB 不存在（dry-run 模式不中断）: {_GLB_PATH}")
    else:
        print(f"[preflight] GLB: {_GLB_PATH}")


def main() -> None:
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

    # 打印摘要
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
```

- [ ] **Step 2: dry-run smoke test**

```bash
python tools/render_regression.py --dry-run
```

预期输出（示例）：
```
[main] 产物根目录: D:\Work\cad-spec-gen\artifacts\regression
[preflight] Blender: D:\Blender\blender.exe
[preflight] GLB: D:\Work\cad-spec-gen\cad\output\EE-000_assembly.glb  （或 ⚠️ 不存在）

=== BASELINE 渲染（平坦材质）===
[render] 命令: D:\Blender\blender.exe -b -P ... -- --all --glb ... --output-dir ...
[render] --dry-run 模式，跳过实际渲染

=== ENHANCED 渲染（PBR 纹理）===
[enhanced] SW textures_dir: C:\Program Files\SOLIDWORKS Corp\...
...

=== 断言摘要 ===
  F1 ✅/❌: ...
  F2 ✅/❌: ...
  F3 ✅/⬜: ...
  F4 ❌: PNG 不存在（干跑不生成）
  F5 ❌: PNG 文件不存在
```

- [ ] **Step 3: 提交**

```bash
git add tools/render_regression.py
git commit -m "feat(regression): main CLI 入口 + preflight 检查"
```

---

### Task 8：真实渲染验收

> 此任务需要本机 Blender 环境 + GLB 文件就绪。如 GLB 不存在，先执行：
> `python cad/end_effector/build_all.py`（需 CadQuery 环境）

- [ ] **Step 1: 确认 GLB 存在**

```bash
ls cad/output/EE-000_assembly.glb
```

若不存在：`python cad/end_effector/build_all.py`（可能耗时 5-15 分钟）。

- [ ] **Step 2: 运行完整回归（仅 baseline，验证 Blender 链路）**

```bash
python -c "
exec(open('tools/render_regression.py').read())
ok = build_baseline(Path('artifacts/regression'))
print('baseline ok:', ok)
import os; print(list(Path('artifacts/regression/baseline/end_effector').glob('*.png')))
"
```

预期：5 个 PNG 文件生成，无 Blender 错误。

- [ ] **Step 3: 运行完整回归**

```bash
python tools/render_regression.py
```

预期：
- `artifacts/regression/baseline/end_effector/` 含 5 PNG
- `artifacts/regression/enhanced/end_effector/` 含 5 PNG
- `artifacts/regression/enhanced/runtime_materials.json` 存在
- `artifacts/regression/report.md` 生成
- F1/F2 ✅（SW 装机），F3 ✅ 或 ⬜，F4 ✅（有纹理则 enhanced 更大），F5 ✅

- [ ] **Step 4: 用文件浏览器对比 PNG**

打开 `artifacts/regression/`，并排查看 `baseline/end_effector/V1_front_iso.png` 与 `enhanced/end_effector/V1_front_iso.png`，在 report.md 的"肉眼观察"区填写评语。

- [ ] **Step 5: 最终提交**

```bash
git add artifacts/regression/report.md
git add artifacts/regression/enhanced/runtime_materials.json
git commit -m "feat(regression): 渲染回归完成 — report.md + runtime_materials 快照"
```

（不提交 PNG 文件，体积过大）

---

## 自审 checklist

- [x] **Spec 覆盖：** §1 流程 ✅ Task 3/4 | §2 环境配置 ✅ Task 2/3/4 | §3 F1-F5 ✅ Task 5 | §4 产物结构 ✅ Task 6/8 | §5 错误处理 ✅ Task 5/7 | §6 验收标准 ✅ Task 8
- [x] **Placeholder 扫描：** 无 TBD / TODO
- [x] **类型一致性：** `run_render(output_dir, extra_env, dry_run)` 在 Task 2 定义，Task 3/4 调用签名一致；`assert_features(out_root, textures_dir)` Task 5 定义，Task 7 调用一致；`write_report(feature_results, out_root, bool, bool)` Task 6 定义，Task 7 调用一致
- [x] **函数名一致性：** `_find_blender()` Task 1 定义，Task 2/7 内调用；`build_enhanced()` 返回 `(bool, str)` tuple，Task 7 以 `ok_enhanced, textures_dir` 接收
