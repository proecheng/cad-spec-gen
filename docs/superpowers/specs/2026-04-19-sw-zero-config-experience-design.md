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

**位置**：项目根 `sw_preflight/` 子目录（与 `adapters/`、`codegen/`、`cad_spec_gen.py` 平级）。**不在** `adapters/` 内（不是 adapter，不参与 BOM 路由）；**不在** `src/cad_spec_gen/` 下（仓库未采用 src layout，本 spec 不重构现有目录骨架）。

**职责**：把"SW 装没装好 / 缺什么 / 能不能一键修 / 修完什么状态" 集中到一处，让所有用户入口（`cad-spec` / `cad-codegen` / `mechdesign`）调用同一个函数拿一致结果。

**对外接口（伪代码）**：
```python
def run_preflight(strict: bool = True) -> PreflightResult:
    # strict=True: 修不动就 raise / sys.exit(2)
    # strict=False: 异常只在 stdout 末尾打 1 行温和提示，不卡
    ...

def dry_run_bom(bom_rows: list[dict]) -> BomDryRunResult:
    # bom_rows 复用 codegen/gen_build.parse_bom_tree() 的 list[dict] 格式
    # (字段: part_no / name_cn / material / make_buy / is_assembly)
    # 走 PartsResolver.resolve() 走一遍，标记"会进 stand-in / 完全没匹配"的行
    # 不真生成几何
    ...

def prompt_user_provided(missing_rows: list[dict]) -> UserChoiceResult:
    # 三选一全局策略 + 单行可跳过
    # 复制文件到 skill 自决位置 + 自动追加 yaml mapping
    ...

def emit_report(bom_rows: list[dict], dry_run: BomDryRunResult,
                preflight: PreflightResult, output_dir: Path) -> Path:
    # 跑完 codegen 后调，吐出三段式 HTML 报告
    ...
```

**新增数据类型**（`sw_preflight/types.py`，全部 `@dataclass(frozen=True)`）：

| 类型 | 字段（核心） | 用途 |
|---|---|---|
| `PreflightResult` | `passed: bool` / `sw_info: SwInfo` / `fixes_applied: list[FixRecord]` / `diagnosis: DiagnosisInfo \| None` / `per_step_ms: dict[str, float]` | run_preflight 返回 |
| `BomDryRunResult` | `total_rows: int` / `hit_rows: list[RowOutcome]` / `missing_rows: list[RowOutcome]` / `stand_in_rows: list[RowOutcome]` | dry_run_bom 返回 |
| `RowOutcome` | `bom_row: dict` / `category: PartCategory` (来自 `ResolveResult.category` 新字段) / `expected_adapter: str` / `actual_adapter: str` / `status: '✅' \| '⚠️' \| '❌'` / `diagnosis: DiagnosisInfo \| None` | dry-run 单行结果 |
| `UserChoiceResult` | `provided_files: dict[bom_key, Path]` / `stand_in_keys: set[bom_key]` / `skipped_keys: set[bom_key]` | prompt_user_provided 返回 |
| `PartCategory` (Enum) | `STANDARD_FASTENER` / `STANDARD_BEARING` / `STANDARD_SEAL` / `STANDARD_LOCATING` (销/键/卡簧) / `STANDARD_ELASTIC` (弹簧) / `STANDARD_TRANSMISSION` (齿轮/链/带) / `STANDARD_OTHER` (其它 GB/T 编号件) / `VENDOR_PURCHASED` / `CUSTOM` | BOM 行语义类型（来自 ResolveResult） |
| `DiagnosisCode` (Enum) | `SW_NOT_INSTALLED` / `SW_TOOLBOX_NOT_SUPPORTED` / `LICENSE_PROBLEM` / `COM_REGISTRATION_BROKEN` / `TOOLBOX_PATH_INVALID` / `TOOLBOX_PATH_NOT_ACCESSIBLE` (UNC/网络不可达) / `PYWIN32_MISSING` / `PYWIN32_INSTALL_FAILED` / `ADDIN_DISABLED` / `MULTIPLE_SW_VERSIONS_AMBIGUOUS` / `INSUFFICIENT_PRIVILEGES` / `BOM_ROW_NO_MATCH` / `BOM_ROW_FELL_THROUGH_TO_STAND_IN` / `USER_PROVIDED_SOURCE_HASH_MISMATCH` (用户提供文件已变化) / `USER_PROVIDED_SCHEMA_INVALID` (扩展名/大小/魔数任一失败) | 失败码枚举（v1 列举；增量追加策略，永不删除已发布码 — 详见 §15 后续 spec 占位） |
| `DiagnosisInfo` | `code: DiagnosisCode` / `reason: str` (中文一句) / `suggestion: str` (GUI 操作步骤) / `severity: 'block' \| 'warn'` | 诊断载体 |
| `FixRecord` | `action: str` / `before_state: str` / `after_state: str` / `elapsed_ms: float` | 一键修执行记录（落 P2 自愈段） |

**关键决策**：诊断信息**不污染**现有 `adapters/parts/parts_resolver.ResolveResult.metadata`——独立模型，仅 sw_preflight 用。这样 adapter chain 的契约保持纯净，诊断系统未来扩展不会反向影响 router。

### 3.2 与现有代码边界

**复用（无修改）**：
- `adapters/solidworks/sw_detect.detect_solidworks() -> SwInfo`（dataclass，含 `installed` / `version_year` / `toolbox_dir` / `toolbox_addin_enabled`）
- `adapters/solidworks/sw_toolbox_adapter.is_available()`（6 项检查，是 Toolbox 真正的可用性入口；**不要**用 `sw_material_bridge`——后者只解析 sldmat XML，无 is_available）
- `adapters/solidworks/sw_com_session.is_healthy()`（subprocess-per-convert 模式不暴露 dispatch 对象，体检仅靠 is_healthy + convert_sldprt_to_step 的 bool 返回）
- `adapters/solidworks/sw_probe.probe_dispatch()` / `probe_com_session()`（已返回 `per_step_ms` dict，sw_preflight 复用此 schema）
- `adapters/parts/parts_resolver.PartsResolver.resolve()`（dry-run 走每行 BOM）
- `adapters/parts/step_pool_adapter` 的现有 STEP 路径搜索（project-local `std_parts/` → shared cache）
- `adapters/parts/vendor_synthesizer.default_cache_root()`（=`~/.cad-spec-gen/step_cache/`，user_provided 在其下加 `user_provided/{standard,vendor}/`）

**修改（小改动，列入 §11）**：
- `adapters/solidworks/sw_detect.py`：
  - `SwInfo` 加 `edition: Literal['Standard', 'Pro', 'Premium', 'unknown']` 字段
  - 新增 `reset_cache()` API（清 `_cached_info` 进程级缓存——一键修后必须调，否则拿旧值假成功）
  - 多版本共存：默认选最新；尝试读 `~/.cad-spec-gen/sw_version_preference.json` 的 `preferred_year`；env `CAD_SPEC_GEN_SW_PREFERRED_YEAR` 强制覆盖
- `adapters/parts/parts_resolver.py`：
  - `ResolveResult` 加 `category: PartCategory` 字段（来源：mapping 命中规则的 `match.category` + 兜底 inference）
  - **理由**：避免 sw_preflight 反向依赖 adapter 实现细节（架构师审查 #1）。category 由 router 权威决定，sw_preflight 只消费

**新增（orchestrator 层）**：
- `sw_preflight/`（"判断 + 修复 + 呈现 + 诊断"集中处）

### 3.5 通用性约束（零硬编码 + 自主发现）

> **铁律**：sw_preflight 任何代码、文档、测试**禁止**硬编码以下任一项。所有信息必须**运行时自主发现**。违者 plan 阶段 code-review 直接 reject。
>
> **来由**：memory `solidworks_asset_extraction.md` 已记录"SW 真路径 `C:\Program Files\` 非 `D:\`"事故；不同用户安装位置 / 版本 / 授权 / 网络环境差异巨大，硬编码会让 skill 在用户机器上静默失败。

#### 3.5.1 禁止硬编码清单

| 信息 | 禁止 | 必须 |
|---|---|---|
| SW 安装路径 | `C:\Program Files\SOLIDWORKS Corp\...` / `D:\...` | 注册表 / COM ApplicationDirectory API / Shell ProgID 反查 |
| SW 版本年份 | `2020` / `2024` 等具体年份 | 注册表枚举所有 `SOLIDWORKS <year>` 子键 / `ISldWorks::RevisionNumber()` |
| Toolbox 数据库路径 | 任何字面路径 | `ISldWorks::GetUserPreferenceStringValue(swToolboxFolder)` 或 SW 选项 API |
| 授权 edition | "Pro 必有 Toolbox" 等假设 | 注册表 edition 字段 + **运行时 sw_toolbox_adapter.is_available() 真测兜底** |
| pywin32 安装路径 | `site-packages/win32com` 等 | `importlib.util.find_spec('win32com')` |
| Add-In GUID | SW Toolbox Add-In 的具体 GUID 字面值 | 复用 `sw_toolbox_adapter` 现有发现机制（不要在 sw_preflight 重复一份） |
| 注册表 hive 选择 | 仅查 HKLM 或仅查 HKCU | **HKCU 优先 → HKLM 兜底**（用户级 add-in 配置覆盖系统级） |

#### 3.5.2 自主发现策略（多源交叉验证）

每项关键信息**至少 2 个独立来源**，结果不一致时记 P2 警告但不 fail：

| 信息 | 主源 | 兜底源 | 不一致时 |
|---|---|---|---|
| SW 是否安装 | 注册表 `SOFTWARE\SolidWorks\Setup\SOLIDWORKS *` 子键存在 | COM ProgID `SldWorks.Application` 可解析 | 任一命中即"装"，记 P2 |
| SW 版本号 | 注册表 `Setup\<year>` 子键名 | `ISldWorks::RevisionNumber()` 实运行返回 | 不一致 → 优先信运行时 |
| SW 安装路径 | 注册表 `SOFTWARE\SolidWorks\SOLIDWORKS <ver>\Setup\SolidWorks Folder` | COM `ISldWorks.GetExecutablePath()` 实运行 | 同上 |
| Toolbox 路径 | SW 选项 API 运行时取 | 注册表 `Toolbox\<ver>\Folder` | 同上 |
| edition (Std/Pro/Premium) | 注册表 `Setup\<year>\Edition` | sw_toolbox_adapter.is_available() 真测：能 Add-In + 能列零件 = 至少 Pro | 真测优先（注册表可能滞后于授权切换） |
| 多版本共存 | 注册表枚举所有 `SOLIDWORKS *` 年份子键 | — | 默认选**最新**版本；P2 报告头显示"检测到多版本：[2022, 2024]，本次用 2024" |

#### 3.5.3 工具函数边界

所有"自主发现"逻辑**集中**在 `adapters/solidworks/sw_detect.py` 内（本 spec 在那里加 `reset_cache()` + `edition` 字段时顺手把多源发现也补全），sw_preflight 仅消费 `SwInfo` dataclass，不直接读注册表 / 不直接调底层 API——保持职责分层。

> 这条约束的副作用是**本 spec 顺手清理 sw_detect.py 现有的任何硬编码**（如果 audit 阶段发现）——plan 阶段第一个 task。

### 3.3 接入点（修改 3 处 CLI 入口）

| 入口 | 实际文件路径 | strict | dry-run | P2 报告 | 备注 |
|---|---|---|---|---|---|
| `cad-spec` | `cad_spec_gen.py`（项目根） | False（异常 1 行温和预告） | ❌ | ❌ | 编辑阶段不打扰，仅"后续会需要 SW"预告 |
| `cad-codegen` | `codegen/gen_std_parts.py` | **True** | ✅ | ✅ | 主战场 |
| `cad_pipeline` (端到端) | `cad_pipeline.py`（项目根） | 复用 cad-spec + cad-codegen 各自策略 | ✅ | ✅ | 不重复体检 |
| `mechdesign` | （多 phase 文件） | **暂不接** | ❌ | ❌ | 保留"15 行接入"能力，下 spec 再说 |

> **路径与复杂度说明**：
> - 现有入口在**项目根 + `codegen/`** 子目录，**不在** `src/cad_spec_gen/cli/`——本 spec 不重构 CLI 骨架
> - 仓库无统一 CLI 框架（混合 argparse），sw_preflight 接入要分别适配三个入口的 argparse 结构
> - 实际接入复杂度 ~15-30 行/入口（含 import / 错误处理 / 参数透传 / strict 模式分支），**不是** 5-10 行——orchestrator 层吸收大部分逻辑后入口才能瘦

#### 跨入口状态共享（IPC via cache.json）

**问题**：cad-spec 阶段做的 SW 体检、cad-codegen 阶段不该重复做（§10 采样时序约束 + 性能）。但两个入口可能是独立进程（用户分别敲 cad-spec 和 cad-codegen 命令），无法共享内存。

**机制**：preflight 跑完后落盘 `./artifacts/<run-id>/sw_preflight_cache.json`：
```json
{
  "schema_version": 1,
  "ran_at": "2026-04-19T14:32:00Z",
  "ran_by_entry": "cad-spec",
  "preflight_result": {...},   // 序列化的 PreflightResult
  "dry_run_result": null,       // cad-spec strict=False 不做 dry-run，此处 null
  "ttl_seconds": 300            // 5min 后自动失效
}
```

cad-codegen 入口启动时按下面顺序决定是否复用：
1. 找最近的 `sw_preflight_cache.json`（同 run-id 优先；找不到全局 latest 也可）
2. 校验 `now - ran_at < ttl_seconds` + `schema_version 匹配` + `preflight_result.passed=true`
3. 命中 → 复用 preflight 结果（不重做 M），但 dry_run **必须** cad-codegen 自己跑一次（cad-spec 没做）
4. 未命中或失效 → 完整重跑 M + dry-run

**副作用**：cache.json 也是 P2 报告生成的输入源（§6 报告引用同一份数据，避免数据漂移）。

---

## 4. M 体检 — 判定矩阵

### 4.1 自动通过（用户无感）

| 检测项 | 期望状态 |
|---|---|
| Windows 平台 | `sys.platform == 'win32'` ✓ |
| pywin32 已装且 postinstall 已跑 | `import win32com` 成功 + `pythoncom` 可初始化 ✓ |
| SOLIDWORKS 已安装（任一版本） | `sw_detect.detect_solidworks().installed` ✓（多源交叉验证，见 §3.5.2） |
| 多版本共存检测 | 注册表枚举所有 `SOLIDWORKS *` 子键，默认用**最新**版；P2 报告显式列出所有版本与本次选择 |
| SW 版本支持 Toolbox（**真测，不查年份**） | `sw_toolbox_adapter.is_available()` 真跑 6 项 = ✓ ³ |
| 授权状态可用 | COM 实例化无 license 异常 + Toolbox API 可调用 ⁵ |
| SLDWORKS COM 可用 | `sw_com_session.is_healthy()` ✓⁴ |
| Toolbox Add-In 已启用 | `sw_toolbox_adapter.is_available()` ✓ |
| Toolbox 数据库路径有效 | `SwInfo.toolbox_dir`（运行时由 SW 选项 API 取，不假设路径）存在 + 可读 ✓ |
| Toolbox 路径**网络可达性**（仅 UNC 路径时） | 若 `toolbox_dir` 是 `\\server\share\...` UNC 路径，校验网络 mount 可读 ✓⁶ |

全过 → M 静默通过，pipeline 直接进入主任务。

> **³ Toolbox 支持判定 = 真测，不查版本年份**：旧 `sw_toolbox_adapter` 用 `version_year < 2024` 做硬编码判定——**违反 §3.5 通用性约束**，本 spec 顺手清理。新规则：
> - 不论 SW 是哪一年的（2018 / 2020 / 2024 / 2025+），统一调 `sw_toolbox_adapter.is_available()` 6 项检查
> - `SwInfo.edition` 字段（新增）仅作为**辅助信息**写进报告头，不参与可用性决策
> - 这样 SW 出新版本（如 2026 / 2027）不需要改本 spec 任何代码
>
> **⁴ sw_com_session 不暴露 dispatch 对象**：现 subprocess-per-convert 模式，体检通过 `is_healthy()` 间接验证 COM 可用——若不足以覆盖"CLSID 可实例化"，sw_preflight 内做一次 spawn-test-die 子进程探测（`subprocess.run([python, '-c', 'import win32com.client; win32com.client.Dispatch("SldWorks.Application")'])`），不污染 sw_com_session 现有 API。
>
> **⁵ 授权多样性兜底**：用户机器上 SW 可能是 Standard / Pro / Premium / 教育版 / 试用版 / 网络浮动 / 借用授权 / 临时授权——种类太多无法逐种分支。统一策略：**任何 license 异常都归一到 `LICENSE_PROBLEM` 诊断码**（见 §4.3），让用户打开 SOLIDWORKS GUI 一次看具体报错（SW 自己的 license 报错最权威），修后重跑。
>
> **⁶ UNC 路径企业部署**：企业环境 Toolbox 常在网络共享 `\\fileserver\SOLIDWORKS\Toolbox\`（用户 SW 客户端通过 mount 访问）。检测方法：`pathlib.Path(unc).exists()` + `os.access(unc, os.R_OK)`；不可达 → `TOOLBOX_PATH_NOT_ACCESSIBLE` 诊断码（区分本地路径不存在 `TOOLBOX_PATH_INVALID`）。建议文案："网络路径不可访问 — 请检查网络/VPN/共享映射是否正常，或联系 IT 管理员"。
>
> **多版本默认选择策略**（解决 SW 操作员审查 #5）：检测到多版本时按下面顺序决定使用哪个：
> 1. env `CAD_SPEC_GEN_SW_PREFERRED_YEAR=2024` 强制（最高优先）
> 2. `~/.cad-spec-gen/sw_version_preference.json` 的 `preferred_year` 记忆
> 3. 默认选**最新**版本
> 4. 选定版本不可用 → 回退候选（按年份降序）；全失败 → `MULTIPLE_SW_VERSIONS_AMBIGUOUS` 让用户人工裁决，并把选择写入 preference.json 记住

### 4.2 一键修（H 策略 — 弹一行话 + 回车）

**执行前提**：若需要操作 SW（启进程、enable Add-In、写 SW 选项），先**等用户关闭装配体**（不强制全关，因为工程师常多文档同时开 — 5+ 个零件 + 1 个装配体）。

具体策略（SW 操作员审查 #1 优化）：
- 通过 `ISldWorks::GetDocuments()` 枚举所有打开文档，按类型分类（装配体 .sldasm / 零件 .sldprt / 工程图 .slddrw）
- **只要求关闭装配体** — 装配体关了 Toolbox 操作就不会与之冲突
- 零件文件保留 — 用户的设计上下文不被打断

提示文案：
```
⚠️ 检测到 SOLIDWORKS 中有 N 个装配体打开（保留了 K 个零件文件不影响）。
修复需要先关闭装配体。请在 SW 内保存装配体并关闭，
再回到这里按 [回车] 继续（零件文件无需关闭）。
[Q] 退出我自己处理
```

轮询 `ISldWorks::ActiveDoc` / `GetDocumentTypes` 检测装配体是否全关，每 1s 一次，超时 5min。

| 异常 | 一键动作 | 需要等关 SW | 需要管理员权限 |
|---|---|---|---|
| pywin32 未装 | `pip install pywin32 && python Scripts/pywin32_postinstall.py -install` | ❌ | 取决于 Python 环境（venv 用户级不需要 / 系统 Python 需要） |
| ROT 中有僵死 SW 实例¹ | 自动 release + 重摸 ROT | ❌（**静默自愈**，不弹提示，记 P2） | ❌ |
| Toolbox Add-In 未启用 | 通过 `SldWorks.EnableAddIn` 强制开（向 **HKCU** 写"启动时加载"标记）⁷ | ✅（仅装配体） | ❌ HKCU 不需要 admin（仅当用户配置异常落到 HKLM 时才需要 — 罕见） |

> **⁷ Toolbox Add-In 启用的注册表层级**（SW 操作员审查 #2）：SW Add-In 配置分两层：
> - **HKCU\SOFTWARE\SolidWorks\Addins\<GUID>** = 当前用户启动时加载（用户级，不需要 admin）
> - **HKLM\SOFTWARE\SolidWorks\Addins\<GUID>** = 所有用户启动时加载（系统级，需要 admin）
>
> 本 spec 修复**仅写 HKCU**：
> 1. 多用户机器（公司共享 PC）每用户独立配置，不互相影响
> 2. 不需 admin 权限（傻瓜 gate 通过）
> 3. **幂等**：写前先读，已是启用状态则跳过（不重复写注册表）
> 4. SW 重启后**保持启用**（HKCU 是持久化的，非"当前会话"）
> 5. 如果 HKLM 已显式禁用（企业策略），HKCU 启用可能被覆盖 → 落到 `INSUFFICIENT_PRIVILEGES` 诊断引导联系 IT
| SW 后台进程未启动（仅 Add-In 启用需要时） | 自动启 SW 后台进程（不弹界面） | ❌（启新进程） | ❌ |

> **管理员权限不足时的退化（H 策略增强）**：执行修复前用 `ctypes.windll.shell32.IsUserAnAdmin()` 检测当前进程权限。若修复需要管理员权限但当前不是 admin：
> ```
> ⚠️ 此修复步骤需要管理员权限。
>    [1] 以管理员身份重启本工具（系统会弹 UAC 确认）
>    [2] 我自己手动修（按报告里的 GUI 步骤）
>    [Q] 退出
> ```
> 选 [1] → `ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)` 重启当前进程为 admin。当前进程干净退出，新进程从 M 体检重新开始。
> 选 [2] → 退化为 §4.3 卡住类 `INSUFFICIENT_PRIVILEGES` 诊断 + GUI 步骤。

> **¹ "僵死 SW 实例" 定义**：Running Object Table 里登记的 `SldWorks.Application` COM 对象，但对应进程已退出（孤儿引用）；或对应进程存在但 `IsConnected()` / 任意 API 调用返回 RPC_E_DISCONNECTED。检测靠 sw_com_session 的 health probe（已有逻辑）。

修完**重跑一次体检**，全过才放行。

> **⚠️ 重跑前必须调 `sw_detect.reset_cache()`**：`detect_solidworks()` 内部有进程级 `_cached_info`，不 reset 会拿到修前的旧值导致**假成功**。`reset_cache()` 是本 spec 在 sw_detect.py 新增的 API（§3.2 列入）。所有自动修复函数返回前必须调一次 `reset_cache()` 再交还控制流。

修了什么、修了多久 → 记 P2 "M 体检自愈记录" 段（数据结构 = `FixRecord`，见 §3.1）。

### 4.3 卡住（清晰诊断 + 不让继续）

> **诊断载体**：每条诊断由 `DiagnosisInfo` dataclass 实例承载（字段：`code: DiagnosisCode` / `reason: str` / `suggestion: str` / `severity: 'block'`，定义见 §3.1）。下表"诊断"列是 `reason` 字段示例，"建议"是 `suggestion` 字段。诊断**不**写入 `ResolveResult.metadata`——独立模型，避免污染 router 契约。

| `DiagnosisCode` | `reason` (诊断) | `suggestion` (建议) | 为什么不能一键 |
|---|---|---|---|
| `PLATFORM_NOT_WINDOWS` | 本工具仅支持 Windows — 检测到 platform=darwin/linux | 在 Windows 机器上重跑 | 北极星平台边界 |
| `SW_NOT_INSTALLED` | 未检测到 SolidWorks 安装 | 请先安装 SolidWorks Pro 或 Premium。本工具的标准件几何来自 SW Toolbox。 | 装 SW 需要序列号 + 几 GB 安装包 |
| `SW_TOOLBOX_NOT_SUPPORTED` | 检测到 SW（版本 `<runtime version>`）但 Toolbox 不可用——可能是 Standard 版本或 Toolbox 模块未安装 | 请打开 SOLIDWORKS → 帮助 → 关于 → 查看许可证类型；若为 Standard 请联系授权管理员升级，若为 Pro/Premium 请运行 SW installer 修改安装勾选 Toolbox 模块 | 授权或安装范围问题（**不假设是 Standard，让用户自己看 SW 报告的实际类型**） |
| `LICENSE_PROBLEM` | SW 已安装但 license 异常（实例化失败 / Toolbox API 报错） | 请双击桌面 SOLIDWORKS 图标启动一次，查看 SW 自己弹的 license 报错（过期 / 服务器不通 / 未激活 / 借用到期 等），按 SW 提示修复后重跑本工具 | license 异常类型太多（网络浮动 / 单机 / 试用 / 教育 / 借用 / 临时），逐种分支不现实——SW 自己的报错最权威 |
| `COM_REGISTRATION_BROKEN` | SW COM 接口异常（CLSID 实例化失败） | 控制面板 → 程序 → SOLIDWORKS → 修改 → 修复安装 | 装坏了得用 SW installer 修复 |
| `TOOLBOX_PATH_INVALID` | Toolbox 数据库路径配置无效（本地路径不存在）：`<runtime path>` | SOLIDWORKS → 工具 → 选项 → 系统选项 → 异型孔向导/Toolbox → 把路径改到本地非同步目录 | 用户系统配置问题 |
| `TOOLBOX_PATH_NOT_ACCESSIBLE` | Toolbox 路径配置存在但访问失败（UNC/网络不可达）：`<runtime unc path>` | 检查网络连接、VPN、共享映射；联系 IT 管理员确认权限 | 企业网络环境问题 |
| `MULTIPLE_SW_VERSIONS_AMBIGUOUS` | 检测到多个 SW 版本 `[<v1>, <v2>, ...]`，最新版 `<vN>` 不可用，回退候选也都失败 | 请打开期望使用的 SW 版本一次（确认它能正常启动），或卸载坏的版本 | 多版本场景下自动选最新失败，需人工裁决 |
| `INSUFFICIENT_PRIVILEGES` | 修复需要管理员权限（写 HKLM 注册表 / 系统目录） | 重新以"以管理员身份运行"启动终端再跑本工具，或按报告中的 GUI 步骤手动修复 | 当前进程权限不足，无法静默 elevate（需用户授权） |

**诊断行规范**：一句问题 + 一句"建议怎么做"，没有技术名词；建议必须是 GUI 操作步骤（用户在 SW / 控制面板里点哪几下），不是命令行。

---

## 5. 用户指定文件流（"找不到的元件"）

### 5.1 触发时机：cad-codegen 的 M 阶段批量

M 体检通过 SW 状态后，多跑一步 BOM dry-run，识别 SW 找不到的行，**一次性**问用户。codegen 真跑时不再被打断。

> **dry-run 仅在 cad-codegen 阶段做** — cad-spec strict=False 不做 dry-run（避免编辑阶段被打断）。两入口通过 `sw_preflight_cache.json` 共享 preflight 结果但 dry-run 必须 cad-codegen 自己跑（cache.json 中 `dry_run_result` 为 null 时触发）。
>
> **BOM 行匹配算法**：dry-run **复用现有 `PartsResolver.resolve()` 的 token overlap 算法**（参考 `parts_library.default.yaml` 第 63-68 行 `token_weights`），不在 sw_preflight 内重新实现 normalize 逻辑——保持单一真相源。
>
> **机械工程师审查 #2 已知缺口**：现有 token overlap 对 BOM 写法多样性（"M3×8 内六角螺钉 GB/T 70.1-2008" / "M3*8 内六角" / "GB70.1 M3X8"）的 normalize 能力**有限**，可能命中率参差。本 spec **不在此修复**——属于 PartsResolver 自身能力问题，列入 §15 后续 spec 占位"BOM normalize 增强"。dry-run 命中率不足时降级为 stand-in/skip，由用户在三选一交互兜底。

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

**BOM 语义类型扩展**（机械工程师审查 #1 修订）— "标准件"涵盖**所有 GB/T、ISO、DIN 编号件**，不限于紧固件和轴承：

| 大类 | 子类 (`PartCategory` enum) | 典型示例 | 现状 mapping |
|---|---|---|---|
| **标准件** | `STANDARD_FASTENER` | 螺钉/螺栓/螺母/垫圈 | ✅ 已 ship（GB/T 70.1, 6170, 5783...） |
| | `STANDARD_BEARING` | 深沟球/角接触/圆柱滚子 | ✅ 已 ship（GB/T 276, 296, 297...） |
| | `STANDARD_SEAL` | O 圈/油封/密封圈 | ⚠️ **缺 mapping**，本 spec 列入 plan 任务（GB/T 1235, 13871...） |
| | `STANDARD_LOCATING` | 销/键/卡簧 | ⚠️ **缺 mapping**（GB/T 117, 1096, 894...） |
| | `STANDARD_ELASTIC` | 压簧/拉簧/碟簧/扭簧 | ⚠️ **缺 mapping**（GB/T 2089, 2087...） |
| | `STANDARD_TRANSMISSION` | 齿轮/链轮/同步带轮 | ⚠️ **缺 mapping**（GB/T 1357, 1243...） |
| | `STANDARD_OTHER` | 其它 GB/T 编号件 | 🛟 兜底走 sw_toolbox 或 bd_warehouse 通配 |
| **外购件** | `VENDOR_PURCHASED` | Maxon / LEMO / ATI 等厂家件 | ✅ 已 ship vendor STEP synthesizer |
| **自定义件** | `CUSTOM` | 设计师画的非标件 | ✅ jinja_primitive 兜底 |

> **plan 阶段任务**：补全 `parts_library.default.yaml` 的 `STANDARD_*` mapping（密封件 / 定位件 / 弹性件 / 传动件），优先 GB/T 高频规格。每补一类需配单元测试覆盖典型 BOM 行 → adapter 命中。

| BOM 语义存放 | 实际位置 | 为什么 |
|---|---|---|
| 标准件 用户提供 | `./std_parts/user_provided/standard/` (项目本地)⁸ | 跟项目走，跨机器复制可复现 |
| 外购件 用户提供 | `./std_parts/user_provided/vendor/` (项目本地)⁸ | 同上 |
| 自定义件 用户提供 | `./std_parts/custom/` (项目本地) | 项目特有 |

> **⁸ 路径决策修订**（3D 设计师审查 #2 + 系统分析师审查 #2 冲突协调）：原 spec 把标准件/外购件存全局 cache `~/.cad-spec-gen/step_cache/user_provided/`——优点跨项目复用、缺点跨机器复制项目时丢失几何。**本轮决议改为全部存项目本地** `./std_parts/user_provided/{standard,vendor}/`，跟项目走，保证"同 BOM 跨机器出同渲染图"（北极星 #3 准确 gate）。跨项目复用通过用户手动 yaml import 或 git submodule 解决，不由 skill 隐式处理。

skill **复制**文件（不是 symlink），防止用户后来动原文件。

### 5.4 跨次复用：自动写 yaml mapping

首次指定后，skill 自动在项目 `parts_library.yaml`（没有则新建）追加：
```yaml
mappings:
  - match:
      keyword_contains: ["GB/T 70.1 M3×8"]
    adapter: step_pool
    spec:
      file: "std_parts/user_provided/standard/gbt70.1_m3x8.step"
    provenance:                              # 用户提供文件溯源 + 失效检测
      provided_by_user: true
      provided_at: "2026-04-19T14:32:00Z"
      source_path: "C:/Users/foo/Desktop/m3x8.step"  # 用户原始文件路径（仅记录）
      source_hash: "sha256:a3f1...c89e"             # 复制时计算的源文件哈希
      source_mtime: "2026-04-18T09:15:22Z"          # 源文件 mtime
```

> **缓存失效检测（系统分析师审查 #2 修订）**：以前 `note:` 字段是纯人读元数据，本 spec 升级为 `provenance:` 结构，含 `source_hash` + `source_mtime`。
>
> **每次跑 dry-run 时**，对每条 user_provided 命中规则，user_provided.py 校验：
> 1. **源文件仍存在** → 比对 mtime 和 hash
>    - 都一致 → 直接复用 cache 副本（命中）
>    - mtime 或 hash 变化 → 提示用户："检测到原始文件已变化（源 mtime: 2026-04-19 → 2026-04-22）。是否用新版本替换缓存？[Y/N/Skip]"
>    - Y → 重新复制 + 更新 provenance；N → 仍用旧 cache，警告记 P2；Skip → 当 stand-in
> 2. **源文件已删除** → 仅警告（不阻塞）："源文件已不存在，当前用缓存副本（hash: a3f1...）"
> 3. **provenance 字段缺失**（旧 yaml 兼容） → 跳过校验，警告"该 mapping 无溯源信息，建议重新指定"

> **插入位置**：mappings 列表中**第一个 `match: {any: true}` 兜底规则之前**——保证规则能命中且不抢其它特化规则；若 yaml 中无兜底则追加到列表末尾。
>
> **理由**：`parts_library.default.yaml` 第 285 行（`- match: {any: true}` → `jinja_primitive`）是 first-hit-wins 的兜底；`parts_library.default.yaml` 第 273 行附近还有 `sw_toolbox` ISO/DIN fastener / bearing 兜底。若 user_provided mapping 插在末尾，会被 `{any: true}` 抢走；若插在最前，会抢其它特化规则。"插在第一个 `{any: true}` 之前"是平衡点。
>
> **`note:` 字段的 schema 兼容性**：现有 yaml 解析器（`adapters/parts/parts_library_loader.py`）的 mapping schema 仅识别 `match` / `adapter` / `spec` 三键，`note` 是无害自定义字段（loader 忽略未知键）。本 spec 明确该字段作为人读元数据保留，不参与 router 决策。

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
│ 后台修复记录 (3 项)                               │
│   🛠️ 程序残留清理 — 清除 1 个未关闭的 SOLIDWORKS │
│      后台进程 (1.2s)                              │
│   🛠️ Toolbox 模块自动启用 (0.8s)                 │
│   ℹ️ [展开技术细节]  ← 折叠区，外行看不到         │
└───────────────────────────────────────────────────┘
```

> **报告语言原则（3D 设计师审查 #3 + 北极星傻瓜 gate）**：用工程师能理解的术语，**不暴露**底层概念：
> - "ROT 僵死" → "未关闭的后台进程"
> - "COM CLSID 实例化失败" → "SOLIDWORKS 接口异常"
> - "pywin32" → "Python 与 SOLIDWORKS 通信组件"
> - "HKCU 注册表写入" → 不出现在用户面文案
>
> 技术细节放在折叠区（HTML `<details>` 标签），点开才显示原始字段——给高级用户/IT 排错用。

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
| 文件对话框选了非 `.step`/`.stp` 扩展名 | 校验扩展名 → 报"请选 STEP 文件（.step / .stp）" → 重弹一次 |
| 选的文件 — 大小不在 [10KB, 500MB] 区间 | 报"文件过小（疑似不含几何）" 或 "文件过大（可能装配体导出，建议拆分）" → 重弹 |
| 选的文件 — 魔数头校验失败（非 ISO-10303 格式 — 防 .stl 改后缀蒙混） | 复用 `sw_com_session._validate_step_file()`（检查文件大小 + ISO-10303 魔数头）→ 报"非 STEP 文件或文件已损坏" → 重弹一次 → 触发 `USER_PROVIDED_SCHEMA_INVALID` 诊断 |
| 选的文件 — 魔数头通过但 cadquery/OCP 几何解析失败 | 仅 **warn**："文件几何解析有警告（可能影响渲染），是否仍使用？[Y/N]" → 用户选 Y 接受、N 重弹（**用户责任不替担**——平衡严格性 vs 速度，不强制 reject） |
| 项目根 yaml 已存在 — **类型 1：YAML 语法错** | 不强写、不修复；提示"`parts_library.yaml` YAML 语法错误（第 N 行：xxx），请检查后重跑。本次选择已缓存在 `./std_parts/user_provided/...`" |
| 项目根 yaml 已存在 — **类型 2：合法 YAML 但 schema 错**（如 `mappings` 是 dict 而非 list） | 不强写；提示"`parts_library.yaml` 结构错误：mappings 应为列表（list），当前是字典（dict）。请修复后重跑。" |
| 项目根 yaml 已存在 — **类型 3：语法 + schema 都通过** | 正常追加新 mapping 到第一个 `{any:true}` 之前 |
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
| **零硬编码静态校验**（CI step） | `git grep -nE 'Program Files\|D:\\\\\|2024\|2025\|2026' -- sw_preflight/` 命中 → fail | Linux + Windows 都跑（git grep 是 git 自带，无外部依赖） |
| **多版本 mock 测试** | `mock_sw_registry_versions([2022, 2024, 2026])` fixture 注入虚假注册表数据 | conftest.py 提供 fixture；sw_detect.py 的注册表读取在测试时可被 mock 替换；CI 不需真装多版本 SW |

### 9.1 新增专门测试（吸取 session 4-5 教训）

1. **修复幂等性** — 连续跑 3 次 sw_preflight，第 1 次修、第 2/3 次必须静默通过（避免死循环）
2. **"按 Q 退出" 全路径** — 6 个交互点 × 4 种用户响应矩阵（详见 §9.1.1）
3. **yaml 损坏 3 类** — 语法错 / schema 错 / 通过 三种情形（详见 §9.1.2）
4. **file dialog 全取消退化** — 用户选 [1] 但每个对话框都按取消 → 平稳退化到 [2]/[3] 二选问
5. **SW 状态突变** — 修复中用户手动操作了 SW（关 / 重启 / 卸载）
6. **user_provided 失效检测** — 源文件 mtime/hash 变化、源文件被删 三种 case
7. **多版本默认选择** — env / preference.json / 最新版 三档优先级正确

#### 9.1.1 AC-6.2 "按 Q 退出" 完整测试矩阵

6 个交互点 × 4 种响应（[Y]/[N]/[Q]/[超时]）= 24 个 case；标 ✅ 必测、— 不适用：

| 交互点 | [Y/Enter] | [N] | [Q] | [超时 5min] |
|---|---|---|---|---|
| M 体检"等关装配体" 提示 | ✅ 继续修 | — | ✅ 干净退出 | ✅ 干净退出 |
| 一键修 pywin32 install 提示 | ✅ 装并重测 | — | ✅ 退出 | — |
| 一键修 Add-In 启用提示 | ✅ 启用并重测 | — | ✅ 退出 | — |
| 管理员权限不足三选一 [1/2/Q] | ✅ ShellExecute runas | ✅ 手动修退化 | ✅ 退出 | — |
| dry-run 三选一 [1/2/3] | ✅ 进 file dialog | ✅ 全 stand-in | (=Q 退出) | — |
| file dialog 取消 → 二次问 [stand-in/skip] | ✅ stand-in | ✅ skip | (=Q 退出) | — |
| cadquery warn → [Y/N] | ✅ 接受 | ✅ 重弹 dialog | (=Q 退出) | — |

每个 ✅ 一个 unit test case；状态机不遗留半完成状态。

#### 9.1.2 AC-3.5 yaml 损坏 3 类测试

| 测试 case | 输入 yaml 内容 | 预期行为 |
|---|---|---|
| 语法错 | `mappings:\n  - match: {any: true\n  adapter: jinja_primitive` (缺 `}`) | 报"YAML 语法错误（第 N 行）"；选择已存到 std_parts/user_provided/，提示重跑 |
| schema 错 | `mappings:\n  some_key: some_value` (mappings 应为 list 实为 dict) | 报"mappings 应为列表（list），当前是字典（dict）" |
| 通过 | 合法 mapping list | 正常追加新 mapping 到第一个 `{any:true}` 之前 |

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
- 复用 sw_probe.probe_dispatch() / probe_com_session() 已有的 `per_step_ms` dict schema
- M 体检自身每步（detect / com_init / addin_check / dry_run / fix_*）也带 per_step 计时

**采样时序（避免重复采样污染基线）**：
- ✅ **preflight 阶段**调 `sw_probe.probe_dispatch()` 采 per_step（cold-start 全数据，含 dispatch / revision / visible / exitapp 4 段）
- ❌ **codegen 阶段不重复采**——SW 已被 preflight 热启过，per_step 数据无新信息（且会扭曲冷启基线）
- ⚠️ **fallback**：仅当 preflight **未跑过**（如 cad-spec strict=False 关闭、用户直接命令行跳过 preflight）时，codegen 入口检测到无 preflight 数据 → 当次自己采一份作为兜底
- 数据共同落 P2 "M 体检自愈记录" 段（按"采样阶段"标签区分 `preflight` / `codegen-fallback`）

---

## 11. 文件清单（plan 阶段细化）

### 新增

```
sw_preflight/                        # 项目根，与 adapters/ codegen/ 平级
  __init__.py
  types.py              # PreflightResult / BomDryRunResult / RowOutcome / UserChoiceResult / FixRecord / PartCategory
  diagnosis.py          # DiagnosisCode enum + DiagnosisInfo dataclass
  preflight.py          # run_preflight 主入口（编排 matrix + dry_run + cache.json 读写）
  matrix.py             # 4.1/4.2/4.3 检测矩阵 + 一键修函数（含 sw_detect.reset_cache 调用 + IsUserAnAdmin 检测）
  dry_run.py            # dry_run_bom (复用 PartsResolver.resolve) + RowOutcome 构造
  user_provided.py      # prompt_user_provided + 文件复制（→ ./std_parts/user_provided/）+ provenance 校验 + yaml 追加
  cache.py              # sw_preflight_cache.json IPC 读写 + ttl 校验 + schema_version 兼容
  preference.py         # sw_version_preference.json 读写（多版本记忆）
  report.py             # emit_report HTML 生成 + sw_report_data.json + 报告语言去技术化（折叠区显技术细节）
  templates/
    sw_report.html.j2   # 三段式 HTML 模板，CSS 内联无外链
  io.py                 # SW 进程/装配体/文档检测 + 等关闭轮询 + tkinter.filedialog 包装 + STEP 三档校验

tests/test_sw_preflight_*.py         # 8 文件：matrix / dry_run / user_provided / report / io / diagnosis / cache / preference
tests/conftest.py                    # 加 mock_sw_registry_versions / mock_filedialog / mock_admin / mock_provenance fixtures

# 跨 run 用户偏好（自动生成，无需手编；用户级，跨项目共享）
~/.cad-spec-gen/sw_version_preference.json    # {"preferred_year": 2024, "set_at": "..."}

# 项目级中间产物（gitignore 加入）
./artifacts/<run-id>/sw_preflight_cache.json  # IPC 共享 PreflightResult，TTL 5min
./artifacts/<run-id>/sw_report.html           # P2 报告
./artifacts/<run-id>/sw_report_data.json      # 报告机器可读源数据

# 项目级用户提供文件（跟项目走，git 加入）
./std_parts/user_provided/standard/           # 用户提供的标准件 STEP
./std_parts/user_provided/vendor/             # 用户提供的外购件 STEP
./std_parts/custom/                           # 自定义件 STEP（设计师画的）
```

### 修改

```
cad_spec_gen.py                              # +15-25 行：sw_preflight.run_preflight(strict=False) + 审查范围透明化 + 写 cache.json
codegen/gen_std_parts.py                     # +20-30 行：读 cache.json 复用 preflight + dry_run_bom + prompt_user_provided + emit_report
cad_pipeline.py                              # +5-10 行：串联（不新加体检逻辑，复用上面两个策略）
adapters/solidworks/sw_detect.py             # +SwInfo.edition + reset_cache() + 多版本枚举/preference.json/UNC 校验
                                             # plan 阶段 task 1 = grep 清查现有硬编码（§3.5 通用性约束）
adapters/parts/parts_resolver.py             # +ResolveResult.category: PartCategory 字段（router 权威决定语义）
parts_library.default.yaml                   # +补 mapping：STANDARD_SEAL/LOCATING/ELASTIC/TRANSMISSION（GB/T 编号件）
                                             # 注：§11 "不动" 段说"已 ship mapping 不动"指不删/改现有规则，**追加新规则允许**
.claude/skills/cad-spec/SKILL.md             # 文档化 strict=False 预告行为 + 审查范围透明化
.claude/skills/cad-codegen/SKILL.md          # 文档化 M 体检 + P2 报告路径 + dry-run 三选一
.gitignore                                   # +artifacts/<run-id>/sw_preflight_cache.json 等中间产物
```

### 不动（保留现有 API 契约）

- `adapters/solidworks/` 其它 5 个文件（sw_com_session / sw_probe / sw_material_bridge / sw_toolbox_catalog / sw_convert_worker）
- `adapters/parts/` 其它 7 个文件（sw_toolbox_adapter / step_pool_adapter / bd_warehouse_adapter / vendor_synthesizer / parts_library_loader / jinja_primitive_adapter / base）
- `parts_library.default.yaml` **现有 mapping 不删/不改**；本 spec 仅**追加** `STANDARD_*` 子类新规则（不打破已 ship 的紧固件/轴承规则的 first-hit 顺序）

---

## 12. 验收标准（Acceptance Criteria）

### AC-1：M 体检触发正确

- AC-1.1 cad-spec 入口：strict=False，正常时静默；异常时 stdout 末尾 1 行温和预告
- AC-1.2 cad-codegen 入口：strict=True，异常时弹交互；修不动时 sys.exit(2)
- AC-1.3 mechdesign 入口：本 spec 不接入（验证 import 路径存在但未调用）

### AC-2：一键修流程正确

- AC-2.1 pywin32 未装：自动 pip install + postinstall，不要求等关 SW
- AC-2.2 Toolbox Add-In 未启用：先等关 SW、再 enable、调 sw_detect.reset_cache()、再重跑体检
- AC-2.3 ROT 僵死：静默自愈，不打扰用户，记 P2
- AC-2.4 修不动场景（SW 未装 / Toolbox 不支持 / license 异常 / COM 损坏）：清晰诊断 + GUI 操作步骤
- AC-2.5 **管理员权限不足时**：检测 IsUserAnAdmin → 弹"以管理员重启 / 手动修 / 退出"三选一
- AC-2.6 **多 SW 版本共存**：默认选最新；最新不可用时回退候选；全失败 → `MULTIPLE_SW_VERSIONS_AMBIGUOUS`

### AC-2.5：通用性铁律（零硬编码）— **CI 自动化**

- AC-2.5.1 **CI step 自动检测**：`git grep -nE 'Program Files\|D:\\\\\|^[^#]*"20(2[0-9]|3[0-9])"' -- sw_preflight/` 命中即 fail
  - 跑在 Linux + Windows 两个 CI runner（git grep 是 git 自带，无外部依赖）
  - 注释里的历史描述（`# 曾经误以为 D:\...`）允许保留——pattern 排除 `^[^#]*` 避免误伤
- AC-2.5.2 SW 安装路径 / 版本号 / Toolbox 路径 / edition 全部由运行时 API / 注册表枚举发现
- AC-2.5.3 Toolbox 支持判定**仅**靠 `sw_toolbox_adapter.is_available()`，不查版本年份
- AC-2.5.4 注册表读取 HKCU 优先 HKLM 兜底
- AC-2.5.5 多源交叉验证：装机/版本/路径每项至少 2 来源，不一致时记 P2 警告
- AC-2.5.6 SW 多版本 mock 测试：`mock_sw_registry_versions([2022, 2024, 2026])` fixture 跑通三档优先级（env / preference.json / 最新版）

### AC-3：用户指定文件流正确

- AC-3.1 dry-run 识别"会进 stand-in"的行；BOM 行匹配复用 PartsResolver token overlap
- AC-3.2 三选一全局策略：[1]/[2]/[3] 各自走对路径
- AC-3.3 文件对话框：取消单行 → 二次问 stand-in/skip
- AC-3.4 文件复制到 `./std_parts/user_provided/{standard,vendor}/` 或 `./std_parts/custom/`；yaml 自动追加 + provenance 字段（source_hash + source_mtime）
- AC-3.5 yaml 处理 3 类（详见 §9.1.2）：语法错 / schema 错 / 通过 各自走对路径
- AC-3.6 跨次重跑：源文件未变 → 直接命中；源文件变化 → 提示重新指定
- AC-3.7 文件 schema 校验：扩展名 `.step`/`.stp` + 大小区间 [10KB, 500MB] + ISO-10303 魔数头 三层校验

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
- AC-6.2 全交互点 [Q] 退出：6 个交互点 × 4 种响应 = 24 case（详见 §9.1.1 矩阵），无半完成状态
- AC-6.3 yaml 损坏 3 类（语法错 / schema 错 / 通过）：详见 §9.1.2，各自走对路径
- AC-6.4 file dialog 全取消退化
- AC-6.5 SW 状态突变：修复中重启 SW 不死循环
- AC-6.6 user_provided 失效检测：源文件 mtime/hash 变化 → 提示重新指定；源文件被删 → 仅警告
- AC-6.7 多版本 mock：env / preference.json / 最新版三档优先级测试通过

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
| **多版本 SW 共存自动选最新失败** | P2 报告显式列出所有版本；`MULTIPLE_SW_VERSIONS_AMBIGUOUS` 诊断码引导用户人工裁决 |
| **管理员权限不足** | §4.2 加 IsUserAnAdmin 检测 + ShellExecute "runas" 二选一退化 |
| **license 异常类型多（网络/单机/教育/试用/借用）** | 统一归 `LICENSE_PROBLEM` 诊断码，让用户在 SW GUI 里看具体报错（SW 自己最权威） |
| **用户机器有 Toolbox 自定义路径（企业网络共享/重命名）** | SW 选项 API 运行时取，不假设路径；网络路径不可达则 `TOOLBOX_PATH_INVALID` |
| **用户机器装的是非 SOLIDWORKS Corp 厂家定制版** | sw_detect 多源交叉（注册表 + COM ProgID）任一命中即"装"；不识别 edition 时归 unknown 但不阻断 |
| **未来 SW 出新版本（2026/2027）spec 失效** | §3.5 + §4.1 ³ 明确不查年份、按运行时真测——新版本无需改 spec |
| **注册表 hive 选错（HKLM vs HKCU）** | §3.5.1 强制 HKCU 优先 → HKLM 兜底，避免漏读用户级 Add-In 配置 |

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
5. **DiagnosisCode 版本化策略** spec（架构师审查 #2）：v1 不形式化版本管理，下个 spec 加 `DiagnosisCode.version` 字段 + migration 策略；现策略只增不删（追加到 enum 末尾）
6. **几何精度评分** spec（3D 设计师审查 #1）：解析 STEP `TOLERANCE` 段 + facet 密度，给 0-100 评分；P2 报告里 user_provided 行显示评分，对比 SW Toolbox 同型号
7. **组合外购件多 STEP 拼装** spec（机械工程师审查 #3）：用户 BOM 行常含"电机+减速机+编码器"三 STEP 组合，本 spec 只支持单 STEP；下 spec brainstorm 用户怎么提交组合包
8. **Toolbox Standard/Customize 配置流程** spec（SW 操作员审查 #3）：v1 仅走 Standard 模式（直接 sldprt）；下 spec 加 Customize 参数化对话框集成
9. **BOM normalize 增强** spec（机械工程师审查 #2）：现 PartsResolver token overlap 对 BOM 写法多样性命中率有限；下 spec 加 normalize 层（标准号正则、单位统一、规格抽取）
