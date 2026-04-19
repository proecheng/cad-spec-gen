# SW 装即用 — 零配置体验打通（场景 A：pipeline 一键流）— 设计稿

- **Date**：2026-04-19
- **Status**：Design（brainstorming 产出，待 writing-plans）
- **Origin**：session 6 收尾后产品北极星确立（main `0c84a12`）；`memory/project_session6_handoff.md` "下一 session 起点"
- **优先级**：高（北极星 5 个 gate 在 SW 集成路径上 4 个 ❌，本 spec 关闭其中 A 场景）
- **时间预算**：~1 calendar week（含测试 + 文档）
- **范围决策**：A 场景（pipeline 一键流）；B/C 场景（手动选件 / 全新交互）留后续 spec
- **拆分决策**：本 spec **不实现** SW 几何审查（重叠/悬浮检测），仅做"审查范围透明化"提示；几何审查另开 spec

---

## 1. 背景

### 1.1 问题陈述

`memory/project_north_star.md` 列了 cad-spec-gen 的 5 个产品北极星 gate：
1. 零配置 — 用户不写 yaml / env / deps
2. 稳定可靠 — 不间歇 fail / 不静默降级
3. 结果准确 — 通过/不通过二值明确
4. SW 装即用 — 装了 SW 就自动用上 SW 资产
5. 傻瓜式 — 不问技术问题，默认用户外行

当前 SW 集成现状（同 memory §当前差距）：
- ❌ **零配置**：`parts_library.yaml` 的 `solidworks_toolbox:` 段需要用户手写（实测：default 已 ship，但用户级覆盖仍需手动）
- ❌ **稳定可靠**：`is_available()` False 时静默降级到 bd_warehouse / 硬编码
- ❌ **结果准确**：codegen 产物里 `source_tag` 不显式，用户不知道用的是 SW 还是 fallback
- ❌ **SW 装即用**：装了 SW 也因为 pywin32 没装 / Toolbox Add-In 未启用 / Toolbox 路径不对 → 还是走 fallback
- ✅ **傻瓜式**（仅当前 4 项不阻塞它的前提下）

代码基础设施已就位（`adapters/solidworks/` 6 个模块、`adapters/parts/sw_toolbox_adapter.py`、`parts_library.default.yaml` 默认 mapping），但**用户体验层没人做**——这正是本 spec 的目标。

### 1.2 用户场景（已 brainstorm 锁定）

**A 场景（最痛点，本 spec 范围）**：用户每天跑设计文档 → BOM → 渲染图，BOM 80% 是 GB/T 标准件。**痛点**：
- 大多数靠"渲染图不对劲"事后发现没用上 SW（被动、滞后、需专业判断）
- 少数人才看 coverage 报告（位置/形式不显眼）
- 极少数关注终端 stdout 滚动信息

B/C 场景（手动选件 / 新交互）暂不在本 spec。

### 1.3 北极星 5 gate 落地策略

| gate | 本 spec 落地方式 |
|---|---|
| 零配置 | yaml 由 skill 自动改（用户首次指定 STEP 后自动追加 mapping）；不要求用户手写任何配置 |
| 稳定可靠 | 引入 M 体检前置 gate；strict=True 模式下 SW 状态异常**不允许**静默降级，要么修要么停 |
| 结果准确 | P2 报告三段式（标准件/外购件/自定义件）独立判定，每行 source 显式标注，✅/⚠️/❌ 二值明确 |
| SW 装即用 | M 体检自动检测 + 一键修（pywin32 / ROT / Toolbox Add-In 启用 / SW 后台进程） |
| 傻瓜式 | 所有交互问业务/操作层（[Y/N/Q]、文件对话框），不问技术名词；修复路径有 SW UI 操作步骤而非命令行 |

---

## 2. Scope（brainstorming 锁定）

| 维度 | 决策 |
|---|---|
| 用户场景 | A（pipeline 一键流） |
| 失败信号位置 | M（前置体检异常时显形）+ P2（事后三段式 HTML 报告） |
| 修复策略 | H（一键修，不静默不降级） |
| 报告心智 | V（标准件 / 外购件 / 自定义件 三段独立判定） |
| 实现路径 | ② 内部库 `sw_preflight/`（不暴露 skill 命令） |
| 几何审查 | **不在本 spec**——仅做"审查范围透明化"提示 |
| timing AC | v1 不下数字，仪器化收集真用户数据，下 spec 再收紧 |

---

## 3. 架构

### 3.1 新增内部库

**位置**：`src/cad_spec_gen/sw_preflight/`（与 `adapters/solidworks/` 平级，**不是** adapter，不参与 BOM 路由）

**职责**：把"SW 装没装好 / 缺什么 / 能不能一键修 / 修完什么状态" 集中到一处，让所有用户入口（`cad-spec` / `cad-codegen` / `mechdesign`）调用同一个函数拿一致结果。

**对外接口（伪代码）**：
```python
def run_preflight(strict: bool = True) -> PreflightResult:
    # strict=True: 修不动就 raise / sys.exit(2)
    # strict=False: 异常只在 stdout 末尾打 1 行温和提示，不卡
    ...

def dry_run_bom(bom_rows: list[BomRow]) -> BomDryRunResult:
    # 走 router 走一遍，标记"会进 stand-in / 完全没匹配"的行
    # 不真生成几何
    ...

def prompt_user_provided(missing_rows: list[BomRow]) -> UserChoiceResult:
    # 三选一全局策略 + 单行可跳过
    # 复制文件到 skill 自决位置 + 自动追加 yaml mapping
    ...

def emit_report(bom_rows, output_dir) -> Path:
    # 跑完 codegen 后调，吐出三段式 HTML 报告
    ...
```

### 3.2 与现有代码边界

- ✅ **不动** `adapters/solidworks/` 现有 6 个文件
- ✅ **复用** `sw_detect.is_solidworks_installed()`、`sw_probe` 的诊断信号、`sw_material_bridge.is_available()`、`sw_probe` 的 per-step 仪器化
- ✅ **复用** `step_pool_adapter` 的 STEP 解析逻辑（用户指定文件校验时用）
- ✅ **新增** orchestrator 层（"判断 + 修复 + 呈现"）

### 3.3 接入点（修改 3 处 CLI 入口，每处 5-10 行）

| 入口 | strict | dry-run | P2 报告 | 备注 |
|---|---|---|---|---|
| `cad-spec` | False（异常 1 行温和预告） | ❌ | ❌ | 编辑阶段不打扰，仅"后续会需要 SW"预告 |
| `cad-codegen` (`gen_std_parts.py`) | **True** | ✅ | ✅ | 主战场 |
| `cad_pipeline` (端到端) | 复用 cad-spec + cad-codegen 各自策略 | ✅ | ✅ | 不重复体检 |
| `mechdesign` | **暂不接** | ❌ | ❌ | 保留"5 行接入"能力，下 spec 再说 |

---

## 4. M 体检 — 判定矩阵

### 4.1 自动通过（用户无感）

| 检测项 | 期望状态 |
|---|---|
| Windows 平台 | win32 ✓ |
| pywin32 已装且 postinstall 已跑 | import win32com 成功 ✓ |
| SOLIDWORKS 已安装 | sw_detect.is_solidworks_installed() ✓ |
| SW 版本支持 Toolbox | Pro 或 Premium ✓（Standard 无 Toolbox） |
| SLDWORKS COM CLSID 可实例化 | sw_com_session 拿得到 dispatch ✓ |
| Toolbox Add-In 已启用 | sw_material_bridge.is_available() ✓ |
| Toolbox 数据库路径有效 | 路径存在 + 可读 ✓ |

全过 → M 静默通过，pipeline 直接进入主任务。

### 4.2 一键修（H 策略 — 弹一行话 + 回车）

**执行前提**：若需要操作 SW（启进程、enable Add-In、写 SW 选项），先**等用户关闭当前 SW**（轮询 `ISldWorks::ActiveDoc` / `GetDocumentCount` 或检查 SW 进程退出，每 1s 一次，超时 5min）。提示文案：
```
⚠️ 检测到 SOLIDWORKS 中正在编辑文档。
修复需要重启 SW 进程（会丢失未保存内容）。
请在 SW 内保存所有工作并关闭 SOLIDWORKS，再回到这里按 [回车] 继续。
[Q] 退出我自己处理
```

| 异常 | 一键动作 | 是否需要等关 SW |
|---|---|---|
| pywin32 未装 | `pip install pywin32 && python Scripts/pywin32_postinstall.py -install` | ❌ 不需要 |
| ROT 中有僵死 SW 实例¹ | 自动 release + 重摸 ROT | ❌ 不需要（**静默自愈**，不弹提示，记 P2） |
| Toolbox Add-In 未启用 | 通过 `SldWorks.EnableAddIn` 强制开 | ✅ 需要 |
| SW 后台进程未启动（仅 Add-In 启用需要时） | 自动启 SW 后台进程（不弹界面） | ❌ 不需要（启新进程） |

> **¹ "僵死 SW 实例" 定义**：Running Object Table 里登记的 `SldWorks.Application` COM 对象，但对应进程已退出（孤儿引用）；或对应进程存在但 `IsConnected()` / 任意 API 调用返回 RPC_E_DISCONNECTED。检测靠 sw_com_session 的 health probe（已有逻辑）。

修完**重跑一次体检**，全过才放行。修了什么、修了多久 → 记 P2 "M 体检自愈记录" 段。

### 4.3 卡住（清晰诊断 + 不让继续）

| 异常 | 给用户的诊断 | 为什么不能一键 |
|---|---|---|
| 非 Windows 平台 | "本工具仅支持 Windows — 检测到 platform=darwin/linux" | 北极星平台边界 |
| SW 未安装 | "未检测到 SolidWorks 安装。本工具的标准件几何来自 SW Toolbox，请先安装 SolidWorks Pro 或 Premium。" | 装 SW 需要序列号 + 几 GB 安装包 |
| SW 是 Standard（无 Toolbox） | "检测到 SW Standard — 该版本不含 Toolbox。请联系授权管理员升级到 Pro/Premium。" | 授权问题 |
| COM 注册损坏 | "SW COM 接口异常（CLSID 实例化失败）。建议：控制面板 → 程序 → SOLIDWORKS → 修改 → 修复安装。" | 装坏了得用 SW installer 修复 |
| Toolbox 数据库路径无效（OneDrive 锁、被删等） | "Toolbox 数据库路径不可访问：`<path>`。建议：SOLIDWORKS → 工具 → 选项 → 系统选项 → 异型孔向导/Toolbox → 把路径改到本地非同步目录。" | 用户系统配置问题 |

**诊断行规范**：一句问题 + 一句"建议怎么做"，没有技术名词；建议必须是 GUI 操作步骤（用户在 SW / 控制面板里点哪几下），不是命令行。

---

## 5. 用户指定文件流（"找不到的元件"）

### 5.1 触发时机：M 阶段批量

M 体检通过 SW 状态后，多跑一步 BOM dry-run，识别 SW 找不到的行，**一次性**问用户。codegen 真跑时不再被打断。

### 5.2 询问形态：全局三选一 + 原生文件对话框

```
⚠️ BOM 中 5 行 SW 库未直接命中:
   - GB/T 70.1 M3×8 内六角   (SW Toolbox 未启用 M3 短规格)
   - 私有件 PXY-2024-A      (无标准号)
   - LEMO FGG.0B.302        (vendor 库无此型号)
   - ...

如何处理?
  [1] 我来指定 STEP 文件 (依次弹文件对话框, 单行可跳过)
  [2] 全部用参数化 stand-in (精度低但能跑)
  [3] 全部跳过 (这些零件不出现在渲染中)
```

选 [1] → 弹 Windows 原生文件对话框（`tkinter.filedialog`，标题"为 [BOM 描述] 选择 STEP (n/总)"）。**取消** = 该行再问"用 stand-in 还是跳过"。

### 5.3 存放位置（skill 自决，用户不感知）

**BOM 语义类型判定**：复用现有 router 逻辑——`parts_library.default.yaml` 的 `mappings` 段 `match.category` 字段（`fastener` / `bearing` / 无 category 的 vendor model 命中 / `match.any: true` 兜底）已经把"标准件 / 外购件 / 自定义件"分流落地。三类语义：

- **标准件** = router 候选 adapter 含 `sw_toolbox` 或 `bd_warehouse`（GB/ISO/DIN 紧固件、轴承）
- **外购件** = router 候选 adapter 是 `step_pool` 且 mapping 有显式 `synthesizer`（Maxon / LEMO / ATI 等 vendor model）
- **自定义件** = router 走兜底 `jinja_primitive`（项目特有的设计师画的件）

| BOM 语义 | 存放位置 | 为什么 |
|---|---|---|
| 标准件 | `~/.cad-spec-gen/step_cache/user_provided/standard/` | 跨项目复用 |
| 外购件 | `~/.cad-spec-gen/step_cache/user_provided/vendor/` | 跨项目复用 |
| 自定义件 | `./std_parts/custom/` (项目本地) | 项目特有，跨项目无意义 |

skill **复制**文件（不是 symlink），防止用户后来动原文件。

### 5.4 跨次复用：自动写 yaml mapping

首次指定后，skill 自动在项目 `parts_library.yaml`（没有则新建）追加：
```yaml
mappings:
  - match:
      keyword_contains: ["GB/T 70.1 M3×8"]
    adapter: step_pool
    spec:
      file: "user_provided/standard/gbt70.1_m3x8.step"
    note: "用户提供 2026-04-19"
```

下次跑同 BOM 直接命中，不再问。**yaml 是 skill 行为，不是用户负担**——北极星 #1 gate 通过。

---

## 6. P2 报告形态

### 6.1 物理形态：HTML 单文件 + 终端入口提示

- **HTML 单文件**：CSS 内联、无外链 JS，不依赖网络
- **生成位置**：`./artifacts/<run-id>/sw_report.html` + `sw_report_data.json`（机器可读）
- **入口提示**：cad-codegen 跑完最后一行 stdout：
  ```
  ✅ Done. 构建产物 → ./artifacts/2026-04-19-foo/
  📋 SW 资产报告 → ./artifacts/2026-04-19-foo/sw_report.html （建议先看）
  ```
- **不自动开浏览器**——避免抢用户焦点

### 6.2 内容结构：三段式（V 心智）

```
┌───────────────────────────────────────────────────┐
│ SW 资产报告 — 2026-04-19 14:32  耗时 2m18s        │
│ SW 状态：✅ Pro 2024 | Toolbox: ✅ | pywin32: ✅  │
├───────────────────────────────────────────────────┤
│ 标准件 (12 行) — SW Toolbox: 11 ✅  缺口: 1 ⚠️    │
│   ✅ GB/T 70.1 M6×20 内六角  → SW Toolbox         │
│   ⚠️ GB/T 70.1 M3×8 内六角   → bd_warehouse 近似  │
│      原因: SW Toolbox 中 M3 短规格库未启用        │
│      建议: SW → 选项 → Toolbox → 启用 M3 短规格   │
├───────────────────────────────────────────────────┤
│ 外购件 (4 行) — vendor STEP: 4 ✅                 │
│   ✅ Maxon ECX SPEED 22L → maxon/ecx_22l.step     │
├───────────────────────────────────────────────────┤
│ 自定义件 (8 行) — jinja primitive: 8 ✅           │
│   ✅ 立柱 P1-001 → 参数化生成（80×80×500）         │
├───────────────────────────────────────────────────┤
│ M 体检自愈记录 (3 项)                             │
│   🛠️ ROT 释放 1 个僵死 SW 实例 (静默自愈, 1.2s)   │
└───────────────────────────────────────────────────┘
```

### 6.3 三段独立判定（V 心智落地）

| 段 | ✅ | ⚠️ | ❌ |
|---|---|---|---|
| 标准件 | sw_toolbox 命中 / user_provided² | bd_warehouse fallback | 全失败 |
| 外购件 | step_pool 命中真实文件 / user_provided² | step_pool 命中 vendor_synthesizer stand-in | 全失败 |
| 自定义件 | jinja_primitive 生成 | 参数推断不全（用了默认值） | 生成失败 |

> **² "user_provided 等价于 ✅"判定**：用户在段 5 主动指定的 STEP 文件被视为**真实几何**，与 SW Toolbox 命中等价。理由：用户提供的 STEP 来自 SW 模型 / 厂家原厂 / 用户自画完整模型，几何精度 ≥ Toolbox/vendor 库；这是用户主动选择，**不算 fallback**。报告里仍显式标"来源: 用户提供 (2026-04-19)"以便事后追溯。

**三段独立** → 标准件没用 SW 不会被外购件 ✅ 稀释成混合好看。

---

## 7. cad-spec 审查范围透明化（不实现几何审查）

cad-spec `--review` 模式跑完后，报告末尾**显式列出**覆盖范围 + 未覆盖范围：

```
✅ 本次审查覆盖:
   - 机械参数完整性 (3/3 通过)
   - 装配关系完整性 (5/5 通过)
   - 材料指定完整性 (8/8 通过)

⚠️ 本次审查 *未* 覆盖（需要几何引擎，当前阶段做不到）:
   - 元件重叠 / 碰撞检测
   - 元件悬浮（无支撑结构）
   - 紧固件配合间隙
   - 装配可行性（拆装顺序、避让空间）

💡 这些检查计划在未来版本由 SOLIDWORKS 几何引擎自动完成
   （已装 SW 即可用，无需额外配置）。
```

**本 spec 不实现几何审查**。SW 几何审查（`InterferenceDetectionMgr` / 悬浮检测 / 装配可行性）独立 spec，本 spec 仅做透明化提示。

---

## 8. 错误路径全景

| 场景 | 处理 |
|---|---|
| 用户在"等关 SW"按 [Q] | M 干净退出、pipeline 终止；不破坏；下次跑从 M 重新开始 |
| 文件对话框选了非 .step | 校验扩展名 → 报错 → 重弹一次 |
| 选的 STEP 解析失败 | step_pool 校验失败 → 报"文件可能损坏，是否换一个？" → 重弹 |
| 几何与 BOM 描述不符（用户给 M8 标 M6） | **skill 不做内容校验**——用户责任。报告里标"用户提供 + 日期"，事后可追责 |
| 项目根 yaml 已存在但格式损坏 | 不强写、不修复；提示"`parts_library.yaml` 解析失败，请检查后重跑。本次选择已缓存在 `~/.cad-spec-gen/...`" |
| Toolbox Add-In API 调用失败（个别 SW 版本） | 退化"卡住"类：清晰诊断 + GUI 手动启用步骤 |
| SW 在修复中途用户手动重启了 | 修复动作幂等：重摸 ROT、重判定 |
| 用户选 [3] 跳过 → 渲染图大缺口 | skill 不替判断"哪个零件关键"；P2 ❌ 显式标，用户自负 |
| BOM dry-run 自身报错（router 异常） | 退化"M 不通过"：报"BOM 解析失败"，让用户检查 spec |

**主原则**：用户责任不替担——几何对错 / 零件关键性 / yaml 修复 都是用户的事，skill 只负责呈现透明、不替决定。

---

## 9. 测试策略（windows-only 约束下）

| 测试层 | 范围 | 工具 / 跑哪 |
|---|---|---|
| 单元测试（跨平台） | sw_preflight 内纯逻辑：状态判定、报告生成、yaml 追加、文件分流 | pytest + mock `win32com`（复用现有 `_install_fake_win32com` 思路） |
| 集成测试（仅 Windows + 真 SW） | M 全流程、修复幂等、dry-run、P2 生成 | `@pytest.mark.requires_solidworks` |
| 交互测试（仅 Windows） | "等关 SW" 轮询、文件对话框、三选一 prompt | mock `tkinter.filedialog`、`input()` |
| CI 矩阵 | Linux CI = 单元 + mock；self-hosted Windows runner = 集成 + 真 SW | 走现有 sw-smoke runner（runbook §11） |

### 9.1 新增专门测试（吸取 session 4-5 教训）

1. **修复幂等性** — 连续跑 3 次 sw_preflight，第 1 次修、第 2/3 次必须静默通过（避免死循环）
2. **"按 Q 退出" 全路径** — M 体检 / 等关 SW / 文件对话框 / 三选一 各交互点按退出都不留半完成状态
3. **yaml 自动追加 3 情形** — 项目无 yaml / 有 yaml / 有但损坏
4. **file dialog 全取消退化** — 用户选 [1] 但每个对话框都按取消 → 平稳退化到 [2]/[3] 二选问
5. **SW 状态突变** — 修复中用户手动操作了 SW（关 / 重启 / 卸载）

### 9.2 timing AC 策略（不重蹈 F-1.3l 覆辙）

- ❌ v1 **不**给具体 timing AC 数字
- ✅ 内置仪器化：M 体检每个步骤（detect / com_init / addin_check / dry_run / fix_*）带 per_step 计时
- ✅ 数据进 P2 "M 体检自愈记录" 段
- ✅ 等 ≥3 个真 SW 真用户使用周期，下个 spec 才下区间
- 严禁单点定区间（`feedback_sw_k1_baseline_drift.md`）

---

## 10. 与 F-1.3l 宽容档的关系

**本 spec 不收紧 sw_probe 的 [100, 30000]ms 宽容档**。原因：

1. sw_preflight 是新模块、新指标，与 sw_probe timing AC **解耦**
2. F-1.3l 宽容档要等"SW 装即用打通后的真实使用数据"才能收紧——**本 spec 正是产生这些数据的途径**
3. 收紧动作放到下一个 spec

**接触面**：
- 复用 sw_probe 的 per_step 仪器化机制
- M 体检自身也带 per_step 计时
- 数据共同落进 P2 报告，作为未来 timing AC 收紧依据

---

## 11. 文件清单（plan 阶段细化）

### 新增

```
src/cad_spec_gen/sw_preflight/
  __init__.py
  preflight.py          # run_preflight 主入口 + PreflightResult
  matrix.py             # 4.1/4.2/4.3 检测矩阵 + 修复函数
  dry_run.py            # dry_run_bom + 识别 missing 行
  user_provided.py      # prompt_user_provided + 文件复制 + yaml 追加
  report.py             # emit_report HTML 生成（jinja 模板）
  templates/
    sw_report.html.j2
  io.py                 # SW 进程检测 / 等关闭轮询 / tkinter 对话框包装

tests/test_sw_preflight_*.py    # 至少 5 个文件覆盖：matrix / dry_run / user_provided / report / io
```

### 修改

```
src/cad_spec_gen/cli/cad_spec.py            # +5-10 行：strict=False 调用
src/cad_spec_gen/cli/gen_std_parts.py       # +10-15 行：strict=True + dry_run + emit_report
src/cad_spec_gen/cli/cad_pipeline.py        # +5 行：串联无新逻辑
.claude/skills/cad-spec/SKILL.md            # 文档化 strict=False 提示行为 + 审查范围透明化
.claude/skills/cad-codegen/SKILL.md         # 文档化 M 体检 + P2 报告路径
```

### 不动

- `adapters/solidworks/` 6 个文件（保留现有 API 契约）
- `adapters/parts/sw_toolbox_adapter.py`
- `parts_library.default.yaml`（已 ship 的 mapping 不动；用户级 yaml 追加是 user_provided.py 的事）

---

## 12. 验收标准（Acceptance Criteria）

### AC-1：M 体检触发正确

- AC-1.1 cad-spec 入口：strict=False，正常时静默；异常时 stdout 末尾 1 行温和预告
- AC-1.2 cad-codegen 入口：strict=True，异常时弹交互；修不动时 sys.exit(2)
- AC-1.3 mechdesign 入口：本 spec 不接入（验证 import 路径存在但未调用）

### AC-2：一键修流程正确

- AC-2.1 pywin32 未装：自动 pip install + postinstall，不要求等关 SW
- AC-2.2 Toolbox Add-In 未启用：先等关 SW、再 enable、再重跑体检
- AC-2.3 ROT 僵死：静默自愈，不打扰用户，记 P2
- AC-2.4 修不动场景（SW 未装 / Standard / COM 损坏）：清晰诊断 + GUI 操作步骤

### AC-3：用户指定文件流正确

- AC-3.1 dry-run 识别"会进 stand-in"的行
- AC-3.2 三选一全局策略：[1]/[2]/[3] 各自走对路径
- AC-3.3 文件对话框：取消单行 → 二次问 stand-in/skip
- AC-3.4 文件复制 + yaml 自动追加：跨次重跑直接命中
- AC-3.5 yaml 损坏时不强写、不修复，提示用户

### AC-4：P2 报告正确

- AC-4.1 HTML 单文件可双击打开（无外链依赖）
- AC-4.2 三段独立判定（标准件/外购件/自定义件）
- AC-4.3 顶部 SW 状态卡片显示版本 + Toolbox + pywin32 状态
- AC-4.4 M 体检自愈记录段含 ROT 释放等静默事件
- AC-4.5 cad-codegen 跑完 stdout 最后一行有报告路径提示

### AC-5：cad-spec 审查范围透明化

- AC-5.1 `--review` 输出末尾含"未覆盖"段
- AC-5.2 提示文案明示"未来 SW 几何引擎自动完成"

### AC-6：测试覆盖

- AC-6.1 修复幂等性：连续 3 次 sw_preflight 第 2/3 次静默通过
- AC-6.2 全交互点 [Q] 退出：无半完成状态
- AC-6.3 yaml 自动追加 3 情形覆盖
- AC-6.4 file dialog 全取消退化
- AC-6.5 SW 状态突变：修复中重启 SW 不死循环

### AC-7：timing AC（v1 暂不下数字）

- AC-7.1 仪器化数据落 P2（每步骤 per_step_ms）
- AC-7.2 不强制 timing 区间（等下个 spec）

---

## 13. 风险与未知

| 风险 | 缓解 |
|---|---|
| `SldWorks.EnableAddIn` 个别 SW 版本不可用 | 退化"卡住"类，给 GUI 手动启用步骤 |
| pywin32 自动安装失败（网络/权限） | 退化"卡住"类，给手动安装命令 |
| Toolbox 数据库路径在 OneDrive 锁定（公司常见） | 卡住 + GUI 操作建议改本地路径 |
| BOM dry-run 在大型 BOM（500+ 行）耗时长 | M 阶段加进度条；router 缓存优化（plan 阶段评估） |
| tkinter 在 Python embedded 环境不可用 | 退化为 CLI 路径输入（带 tab 补全） |
| 用户系统多版本 SW 共存 | sw_detect 选最新；P2 报告显示用了哪个版本 |

---

## 14. 引用 memory（plan 阶段必读）

- `project_north_star.md` — 5 个 gate 硬门槛
- `user_simplicity_and_accuracy.md` — 答复风格 + brainstorm 提问收窄
- `user_windows_only_scope.md` — 平台边界
- `project_session6_handoff.md` — 起点指引
- `project_f13l_handoff.md` — F-1.3l 宽容档现状
- `feedback_sw_k1_baseline_drift.md` — timing 单点定区间陷阱
- `feedback_check_conftest_marker_first.md` — 测试 marker 先看 conftest
- `feedback_local_test_scope.md` — 改 yaml/config 后跑同题域 glob
- `feedback_preflight_mirror_ci.md` — pre-flight 验证镜像 CI

---

## 15. 后续 spec 占位（不在本 spec 范围）

1. **SW 几何审查独立 spec**（重叠 / 悬浮 / 间隙 / 装配可行性）
2. **B/C 场景** spec（手动选件 / 全新交互入口）
3. **timing AC 收紧** spec（基于本 spec 收集的真用户 per_step 数据）
4. **mechdesign 接入 sw_preflight** spec（如果届时需要）
