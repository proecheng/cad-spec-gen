# CAD 参数化模型 — 末端执行器

CadQuery 参数化脚本，从 `docs/design/04-末端执行机构设计.md`（§4）提取全部尺寸，生成 STEP 文件供 SolidWorks/FreeCAD 精细建模。

## 参数来源

所有尺寸参数集中在 `end_effector/params.py`，每个值注释了 §4 对应行号。当 §4 设计变更时，只需更新 `params.py` 并重新运行 `build_all.py`。

## 文件结构

```
cad/
├── end_effector/
│   ├── params.py              全部尺寸参数（单一数据源）
│   ├── flange.py              法兰本体（Al圆盘+PEEK+4悬臂+孔位）
│   ├── station1_applicator.py 工位1：耦合剂涂覆
│   ├── station2_ae.py         工位2：AE检测（串联堆叠）
│   ├── station3_cleaner.py    工位3：卷带清洁（双卷轴+溶剂罐）
│   ├── station4_uhf.py        工位4：UHF传感器
│   ├── drive_assembly.py      驱动总成（电机+减速器+适配板）
│   ├── assembly.py            顶层装配（CadQuery Assembly API）
│   └── build_all.py           主入口：一键生成所有 STEP
└── output/                    STEP 输出（已 .gitignore 排除）
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

输出 8 个 STEP 文件到 `cad/output/`：

| 文件 | 内容 |
|------|------|
| EE-001_flange_al.step | 法兰铝合金本体 |
| EE-001_flange_peek.step | PEEK绝缘环 |
| EE-002_station1_applicator.step | 工位1涂覆模块 |
| EE-003_station2_ae.step | 工位2 AE模块 |
| EE-004_station3_cleaner.step | 工位3清洁模块 |
| EE-005_station4_uhf.step | 工位4 UHF模块 |
| EE-006_drive.step | 驱动总成 |
| EE-000_assembly.step | 完整装配体 |

### 后续 SolidWorks 工作流

1. 打开 `EE-000_assembly.step` 验证整体布局
2. 逐个导入零件 STEP 作为参考基准
3. 在 SolidWorks 中添加圆角、倒角、螺纹等精细特征
4. 参数变更时重新运行 `build_all.py` 并对比差异

## 与 §4 同步规则

1. §4 变更 → 更新 `params.py` 对应参数（保持行号注释同步）
2. 重新运行 `build_all.py`
3. 用 CAD 软件打开 STEP 验证几何正确
4. 提交 `params.py` 变更（STEP 文件不入版本库）

## 建模精度说明

当前模型为概念级参数化几何，包含：
- 主要外形尺寸和包络
- 安装接口（螺栓孔、定位销孔、ISO 9409）
- 串联装配关系

不包含（需在 SolidWorks 中完善）：
- 圆角/倒角
- 螺纹（仅通孔）
- 表面处理标注
- 形位公差标注
- 密封槽精细截面
