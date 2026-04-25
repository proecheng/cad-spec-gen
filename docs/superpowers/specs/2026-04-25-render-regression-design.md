# 端到端图像质量回归设计

**日期：** 2026-04-25
**目标：** 量化 Track A（PBR 纹理桥）和 Track B（SW Toolbox STEP 真件）接入后的视觉改善，建立可重复执行的对比基准。

---

## §1 总体流程

```
baseline 渲染（SW_TEXTURES_DIR="" → 平坦材质）
  → artifacts/regression/baseline/{end_effector,detection}/V1-V5.png

enhanced 渲染（SW_TEXTURES_DIR=真实路径 → PBR 纹理回填）
  → artifacts/regression/enhanced/{end_effector,detection}/V1-V5.png

feature 断言（5 项量化检查）
  → artifacts/regression/report.md
```

**入口脚本：** `tools/render_regression.py`

```bash
python tools/render_regression.py                        # 全量，两个子系统
python tools/render_regression.py --subsystem end_effector  # 单子系统
```

**前置条件：**
- `D:\Blender\blender.exe` 已确认存在（版本 4.2.16 LTS）
- `cad/output/` 下已有 STEP 文件（由此前 `build_all.py` 生成）
- SolidWorks 已装机（用于 Track A 纹理路径自动检测）；未装机时 enhanced = baseline，报告中标注

---

## §2 渲染脚本与环境配置

### 两次渲染的环境差异

| 参数 | baseline | enhanced |
|------|----------|----------|
| `SW_TEXTURES_DIR` | `""` （显式置空） | 由 `sw_texture_backfill.detect_sw_textures_dir()` 自动获取 |
| `CAD_RUNTIME_MATERIAL_PRESETS_JSON` | 不设置 | 指向 `artifacts/regression/enhanced/runtime_materials.json` |
| `BLENDER_EXE` | `D:\Blender\blender.exe` | 同左 |

### 脚本结构

```python
# tools/render_regression.py

BLENDER_EXE = r"D:\Blender\blender.exe"
SUBSYSTEMS = ["end_effector", "detection"]

def run_render(subsystem: str, mode: str, output_dir: Path, env: dict) -> None:
    """调用 Blender -b -P render_3d.py，将 V1-V5 PNG 输出到 output_dir。"""

def build_baseline(subsystem: str, out_root: Path) -> None:
    """env: SW_TEXTURES_DIR="" → 平坦材质基线。"""

def build_enhanced(subsystem: str, out_root: Path) -> None:
    """先调 backfill_presets_for_sw() 生成 runtime_materials.json，
    再 env: SW_TEXTURES_DIR=<真实路径> → PBR 纹理增强版。"""

def assert_features(out_root: Path) -> dict[str, dict]:
    """运行 5 项 feature 断言，返回每个子系统的断言结果。"""

def write_report(results: dict, out_root: Path) -> None:
    """写 report.md：断言结果表 + 肉眼评语模板。"""
```

`render_3d.py` 无需改动——baseline 时不设置 `CAD_RUNTIME_MATERIAL_PRESETS_JSON`，脚本自动使用内置平坦材质预设。

---

## §3 Feature 断言（量化部分）

共 5 项断言，每个子系统独立检查，输出 ✅/❌：

| # | 断言 | 检查方式 | 关联 Track |
|---|------|----------|-----------|
| F1 | enhanced `runtime_materials.json` 中至少 1 个 preset 含 `texture_albedo` 字段 | JSON 字段存在性 | Track A |
| F2 | `SW_TEXTURES_DIR` 指向的目录实际存在且非空 | `os.path.isdir` + `os.listdir` | Track A |
| F3 | 最近 `artifacts/*/resolve_report.json` 中 `sw_toolbox` adapter 命中数 ≥ 1 | JSON `adapters.sw_toolbox` 字段解析 | Track B |
| F4 | enhanced V1 PNG 文件大小比 baseline V1 大 5% 以上（PBR 贴图高频细节增大压缩体积） | `os.path.getsize` 比率 | Track A |
| F5 | baseline 和 enhanced 两组 PNG 均非全黑（最大像素值 > 10） | `PIL.Image` max pixel | 通用 |

**F4 说明：** 文件大小差是粗糙但可靠的"纹理是否真正被用上"代理指标。F4 为 ❌ 意味着纹理路径注入失败，需排查 `SW_TEXTURES_DIR` 路径或 `runtime_materials.json` 内容。

---

## §4 产物结构

```
artifacts/regression/
├── baseline/
│   ├── end_effector/
│   │   ├── V1_front_iso.png
│   │   ├── V2_rear_oblique.png
│   │   ├── V3_side_elevation.png
│   │   ├── V4_exploded.png
│   │   └── V5_ortho_front.png
│   └── detection/
│       └── （同上 5 视图）
├── enhanced/
│   ├── end_effector/    （同上）
│   ├── detection/       （同上）
│   └── runtime_materials.json   （SW 纹理回填后的 preset 快照）
└── report.md
```

### report.md 结构

```markdown
## Feature 断言

| 断言 | end_effector | detection |
|------|-------------|-----------|
| F1 texture_albedo 字段存在 | ✅ | ✅ |
| F2 SW_TEXTURES_DIR 目录存在 | ✅ | ✅ |
| F3 sw_toolbox 命中数 ≥ 1   | ✅ 12 | ✅ 8 |
| F4 PNG 文件大小差 > 5%      | ✅ +23% | ❌ +2% |
| F5 PNG 非全黑               | ✅ | ✅ |

## 图片索引

| 视图 | baseline | enhanced |
|------|----------|----------|
| end_effector V1 | baseline/end_effector/V1_front_iso.png | enhanced/end_effector/V1_front_iso.png |
| end_effector V2 | baseline/end_effector/V2_rear_oblique.png | enhanced/end_effector/V2_rear_oblique.png |
| detection V1    | baseline/detection/V1_front_iso.png    | enhanced/detection/V1_front_iso.png    |
| ...             | ...      | ...      |

## 肉眼观察（人工填写）

### end_effector V2（后斜视图）
- baseline: ___
- enhanced: ___
- 改善描述: ___

### detection V2（正等轴测）
- baseline: ___
- enhanced: ___
- 改善描述: ___
```

---

## §5 错误处理与边界情况

| 情况 | 处理方式 |
|------|---------|
| SW 未装机 / `SW_TEXTURES_DIR` 为空 | enhanced 渲染仍运行，F1/F2/F4 断言标记 ❌ 并注释"SW not available"；不中断脚本 |
| Blender 渲染失败（返回非零退出码） | 记录错误，跳过该子系统的后续断言，report.md 中标注 `RENDER_FAILED` |
| `resolve_report.json` 不存在 | F3 断言标记 `N/A`，提示用户先运行 `sw-inspect --resolve-report` |
| PIL 未安装 | F5 退化为仅检查文件存在性，report.md 中注明 |
| GLB 文件不存在 | `render_3d.py` 的输入是 `cad/output/EE-000_assembly.glb`（由 `build_all.py` 的 GLB 导出步骤生成），脚本在渲染前检查，缺失则提示"先运行 build_all.py --export-glb"并退出 |

---

## §6 测试范围

本工具本身不写单元测试（它是一次性验收工具，不进入 CI）。验收标准：

1. 脚本在本机成功运行，输出 `artifacts/regression/report.md`
2. F1–F5 断言结果与预期一致（至少 F1/F2/F5 全 ✅）
3. baseline 和 enhanced PNG 可在文件浏览器中肉眼对比，enhanced 明显更丰富
