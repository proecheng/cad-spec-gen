# /cad-spec — 从设计文档生成 CAD Spec

用户输入: $ARGUMENTS

## 指令

运行 CAD Spec 生成器，从设计文档提取结构化参数/公差/BOM等数据。这是 6 阶段管线的 **Phase 1**。

### 路由规则

1. **无参数** → 显示用法：
   ```
   用法: /cad-spec <design_doc.md> [--force] [--review-only] [--auto-fill] [--supplements '{...}']

   示例:
     /cad-spec docs/design/04-末端执行机构设计.md
     /cad-spec D:/jiehuo/docs/19-液压钳升降平台设计.md
     /cad-spec docs/design/04-末端执行机构设计.md
     /cad-spec D:/jiehuo/docs/19-液压钳升降平台设计.md --review-only
     /cad-spec docs/design/05-电气系统与信号调理.md --force
     /cad-spec --all

   也可通过统一管线执行:
     python cad_pipeline.py spec --design-doc docs/design/04-*.md --auto-fill
   ```

2. **`--all`** → 处理全部子系统：
   ```bash
   python cad_pipeline.py spec --all --force
   ```

3. **文件路径** → 处理单个文档：
   ```bash
   python cad_pipeline.py spec --subsystem <subsystem> --design-doc $ARGUMENTS --force
   ```

4. **`--review-only`** → Agent 驱动设计审查工作流（推荐）：
   ```bash
   # Step 1: 生成审查报告（无交互，立即返回）
   python cad_pipeline.py spec --subsystem <名称> --design-doc <doc.md> --review-only

   # Step 2a: Agent 逐项讨论后，传入补充数据 + 自动补全
   python cad_pipeline.py spec --subsystem <名称> --supplements '{\"M03\": \"L0:适配板/固定/M6×4; L1:法兰/旋转/过盈配合\"}' --auto-fill

   # Step 2b: 或直接自动补全（无需补充数据）
   python cad_pipeline.py spec --subsystem <名称> --auto-fill

   # Step 2c: 或按现有数据直接生成（跳过补全）
   python cad_pipeline.py spec --subsystem <名称> --proceed
   ```

### Agent 审查工作流

`cad_pipeline.py spec` 采用无交互 Agent 驱动模式，分两步执行：

**Step 1 — 生成审查报告** (`--review-only`)：
1. 运行 `cad_spec_gen.py --review-only`，提取数据并执行设计审查引擎（力学/装配/材质/几何模型/完整性）
2. 输出 `output/<subsystem>/DESIGN_REVIEW.md` + `DESIGN_REVIEW.json`
3. 打印审查摘要（CRITICAL/WARNING/INFO/OK 计数 + 各问题条目）后**立即退出（exit 0）**
4. Agent 读取 `DESIGN_REVIEW.json`，按下方协议逐项与用户交互

**Step 2 — 逐项审查对话**：

Agent 读取 `DESIGN_REVIEW.json` 后，按以下协议逐项处理所有 WARNING/CRITICAL 及 `auto_fill: \"是\"` 的 INFO 项，**每次只处理一项**：

| 项目类型 | Agent 行为 |
|---------|----------|
| `auto_fill: \"是\"` | 从设计文档推断具体值，展示推断结果，询问：确认 / 修改 / 跳过 |
| `auto_fill: \"否\"`，可从 BOM/连接矩阵/参数表推断 | Agent 自行推断，用非专业语言展示，询问：确认 / 修改 / 跳过 |
| `auto_fill: \"否\"`，无足够上下文（如缺失材质） | 给出 3-5 个候选选项（根据零件名/类别推断），让用户选编号、自由输入或跳过 |
| `category: "geometry"` 或包含 `group_action` | 先批量说明哪些外购件仍是 D/E 简化几何，再只对高影响零件询问模型来源（自动查找 / 指定 STEP / 先用占位 / 跳过） |
| CRITICAL | 告知必须修复设计文档，说明原因，不进入 supplements |

**处理原则**：
- 用非专业语言描述问题，不暴露原始技术 ID（M03/D6 等），而是说
"某项数据缺失"等
- 每次只问一项，等用户回复后再进入下一项
- 推断时优先使用设计文档中的 BOM、连接矩阵、参数表数据
- 对模型库问题，优先引导用户选择真实 STEP、SW Toolbox、bd_warehouse 或 PartCAD；不要把模型选择只写成自由文本说明
- 跳过的项目不写入 supplements

**模型选择补充格式（v2.21.2+）**：

当用户明确指定某个 STEP 文件或模型候选时，Agent 应把结构化选择放进 `supplements`，让管线写入 `model_choices.json` 并应用到 `parts_library.yaml`：

```json
{
  "model_choices": [
    {
      "part_no": "GIS-EE-001-05",
      "name_cn": "减速电机",
      "step_file": "D:/models/maxon/ecx_22l.step",
      "reason": "用户指定真实供应商模型"
    }
  ]
}
```

管线会校验路径和扩展名，复制 STEP 到 `<project_root>/std_parts/user_provided/`，计算 SHA256，向 `parts_library.yaml` 前置 `step_pool` 映射，并在 `model_choices.json` 记录应用结果。普通文字补充仍写入 `user_supplements.json` 和 CAD_SPEC §10，但不会驱动模型库。

**Phase 1 新增提取步骤**（v2.5.0+）：

除基础参数/BOM/公差提取外，Phase 1 现在还运行：
- `extract_part_placements()` — 串联链与非轴向模式提取，生成零件级定位数据
- `extract_part_envelopes()` — 多源零件尺寸采集（BOM 材质列 + 参数表 + 连接矩阵）
- `_apply_exclude_markers()` — 负约束交叉引用，标记装配排除项
- `compute_serial_offsets()` — 从串联链计算 Z 轴偏移量

生成的 CAD_SPEC.md 因此新增三个章节：
- **§6.3 零件级定位**：每个零件的定位模式（serial/radial/fixed）与置信度
- **§6.4 零件包络尺寸**：汇总各零件的多源包络尺寸（长×宽×高 或 Φd×l）
- **§9 装配约束**：来自负约束表的装配排除清单（非本地总成）

**Phase 1 约束声明系统**（v2.7.0+）：

`extract_assembly_constraints()` 从连接矩阵自动推导 §9.2 约束声明：
- **contact 约束**：从「接触面」列提取零件间面接触关系（如 `端面接触` → `contact(A, B, face="end")`）
- **stack_on 约束**：从串联链推导堆叠顺序（如 `stack_on(B, A)` 表示 B 堆叠于 A 之上）
- **配合代号提取**：从连接类型列提取标准配合代号（如 `过渡配合 H7/m6` → `fit="H7/m6"`）
- **EN_PARAM 英文别名**：参数名自动生成英文别名（如 `法兰外径` → `FLANGE_OD`）

生成的 CAD_SPEC.md §9.2 包含约束声明表，供 Phase 2 codegen 消费用于精确装配定位。

**Phase 1 P7 包络回填**（v2.8.0+）：

如果项目根存在 `parts_library.yaml`，Phase 1 在 P5/P6 之后追加 **P7 backfill 循环**：对每个外购件调 `parts_resolver.PartsResolver.probe_dims()`，把库探测到的真实尺寸写入 §6.4。源标签：

| 标签 | 含义 |
|---|---|
| `P7:STEP` | 来自项目本地 STEP 文件 (`std_parts/`) |
| `P7:BW` | 来自 `bd_warehouse` 参数化零件 |
| `P7:sw_toolbox` | 来自 SolidWorks Toolbox 缓存 STEP |
| `P7:PC` | 来自 `partcad` 包 |
| `P7:STEP(override_P5)` | P7 覆盖了 P5/P6 自动推断 |

P1..P4（作者提供的尺寸）**永不**被 P7 覆盖,只补充缺失的 §6.4 行 + 替换 P5/P6 自动推断的行。详见 `docs/PARTS_LIBRARY.md`。

**Step 3 — 生成 CAD_SPEC.md**（所有项处理完后）：

```bash
# 有用户补充数据时（supplements 为 JSON 字符串）
python cad_pipeline.py spec --subsystem <名称> --design-doc <doc.md> \
  --supplements '{"M01": "总重量: 2.5kg", "D6": "铸铁"}' --auto-fill

# 仅自动补全时
python cad_pipeline.py spec --subsystem <名称> --design-doc <doc.md> --auto-fill

# 跳过所有时
python cad_pipeline.py spec --subsystem <名称> --design-doc <doc.md> --proceed
```

**supplements JSON 格式**：键为 DESIGN_REVIEW.json 中的 `id`，值为确认的内容字符串。

**注意**：
- 整个流程无 `input()` 调用，Agent 完全通过对话 + CLI 参数驱动
- 不直接修改用户的设计文档，所有修改仅反映在 CAD_SPEC.md 中
- CRITICAL 问题需用户修改设计文档后重跑 `--review-only`

### 生成后汇总

读取输出的 CAD_SPEC.md 并汇总：
- 提取到的参数、紧固件、BOM零件数量
- 任何 CRITICAL 或 WARNING 缺失数据项
- 设计审查结果（如有）
- 输出文件位置

### 下一步

CAD_SPEC.md 生成后，建议用户：
- **`/cad-codegen <子系统>`** → 自动生成 CadQuery 脚手架代码（Phase 2）
- **`python cad_pipeline.py full`** → 一键执行全部 6 阶段管线
- **`/mechdesign <子系统>`** → 手动参数化建模流程（需要更精细的几何控制时）

## SW 装即用 集成 (spec 2026-04-19)

cad-spec 入口在启动时跑 `sw_preflight.run_preflight(strict=False)`：
- 正常情况静默通过
- SW 状态异常时 stdout 末尾打 1 行温和预告，不卡用户编辑
- `--review` 模式输出末尾追加"审查范围透明化"段（说明几何审查未覆盖）
