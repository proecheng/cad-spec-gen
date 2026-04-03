# CAD 参数化模型 — 末端执行器

CadQuery 参数化脚本，从 `docs/design/04-末端执行机构设计.md`（§4）提取全部尺寸，生成 STEP 文件供 SolidWorks/FreeCAD 精细建模。

## 参数来源

所有尺寸参数集中在 `end_effector/params.py`，每个值注释了 §4 对应行号。当 §4 设计变更时，只需更新 `params.py` 并重新运行 `build_all.py`。

## 文件结构

由 `/cad-codegen` 自动生成，命名规则：`GIS-EE-NNN-NN` → `ee_nnn_nn.py`（自制件）/ `std_ee_nnn_nn.py`（外购件）。

```
cad/
├── end_effector/
│   ├── CAD_SPEC.md            结构化规范（由 /cad-spec 生成）
│   ├── params.py              全部尺寸参数 + 派生装配参数（MOUNT_CENTER_R等）
│   ├── ee_001_01.py           GIS-EE-001-01 法兰本体（含十字悬臂）
│   ├── ee_001_02.py           GIS-EE-001-02 PEEK绝缘环
│   ├── ee_001_08.py           GIS-EE-001-08 ISO 9409适配板
│   ├── ee_002_01.py           GIS-EE-002-01 涂抹模块壳体
│   ├── ee_003_03.py           GIS-EE-003-03 弹簧限力机构
│   ├── ee_003_04.py           GIS-EE-003-04 柔性万向节
│   ├── ee_004_01.py           GIS-EE-004-01 清洁模块壳体
│   ├── ee_004_12.py           GIS-EE-004-12 清洁窗口翻盖
│   ├── ee_005_02.py           GIS-EE-005-02 UHF安装支架
│   ├── ee_006_01.py           GIS-EE-006-01 信号调理壳体
│   ├── ee_006_03.py           GIS-EE-006-03 信号调理安装支架
│   ├── std_ee_*.py (×22)      外购件简化几何（电机/传感器/储罐等）
│   ├── assembly.py            顶层装配（含方向变换，从§6.2自动生成）
│   ├── build_all.py           构建调度（STD STEP + DXF）
│   ├── drawing.py             ezdxf 2D工程图引擎
│   └── draw_three_view.py     GB/T三视图图框（ThreeViewSheet）
└── output/                    构建输出（STEP/DXF/PNG/GLB）
```

## 使用方法

### 安装依赖

```bash
pip install cadquery
```

### 生成 STEP

```bash
python cad/end_effector/build_all.py
```

输出到 `cad/output/`：

| 类型 | 数量 | 示例 |
|------|------|------|
| 装配体 STEP + GLB | 1+1 | `EE-000_assembly.step`, `.glb` |
| 标准件 STEP | ~24 | `GIS-EE-001-05_std.step`（电机）, `GIS-EE-004-08_std.step`（溶剂罐）|
| 2D 工程图 DXF | ~11 | `EE-001-01_flange.dxf`（法兰）, `EE-005-02_uhf_bracket.dxf` |
| DXF 预览 PNG | ~11 | `EE-001-01_flange.png` |

### 后续 SolidWorks 工作流

1. 打开 `EE-000_assembly.step` 验证整体布局
2. 逐个导入零件 STEP 作为参考基准
3. 在 SolidWorks 中添加圆角、倒角、螺纹等精细特征
4. 参数变更时重新运行 `build_all.py` 并对比差异

## 与设计文档同步规则

1. 设计文档变更 → 重新运行 `/cad-spec` 生成新的 `CAD_SPEC.md`
2. 重新运行 `/cad-codegen --force` 更新所有脚手架（会覆盖 params.py、build_all.py、assembly.py）
3. **注意**：`--force` 会覆盖坐标系声明和手动修改的几何代码，需重新填写
4. 运行 `cad_pipeline.py build` 生成 STEP/DXF
5. 提交代码变更（output/ 文件不入版本库）

## 建模精度说明

**脚手架阶段**（codegen 生成）：
- 自制件为占位方块几何（需通过 `/mechdesign` 手动实现实际形状）
- 标准件为简化圆柱/方盒（尺寸从 BOM 自动提取，方向从 §6.2 自动推导）
- 装配定位正确（工位角度、安装半径、储罐水平/竖直方向）
- 2D 工程图仅有图框和标题栏（视图待实现几何后填充）

**精细建模阶段**（mechdesign / SolidWorks）：
- 圆角/倒角、螺纹、密封槽精细截面
- 形位公差标注、表面处理标注
- 内腔/盲孔剖视图
