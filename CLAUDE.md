# 项目开发规范

## Superpowers 插件工作流

本项目使用 [Superpowers](https://github.com/obra/superpowers) 插件，**所有开发任务必须遵循以下流程**，禁止跳步直接写代码。

### 开发流程（强制）

```
brainstorming → write-plan → execute-plan → code-review → receiving-code-review
```

1. **需求阶段** — 先运行 `superpowers:brainstorming`，用苏格拉底式提问厘清需求，输出设计文档后再进入下一步
2. **计划阶段** — 运行 `superpowers:writing-plans`，将任务拆成每步 2-5 分钟的子任务，每步包含验收标准
3. **执行阶段** — 运行 `superpowers:executing-plans`，由 subagent 批量执行，每个检查点完成后暂停确认
4. **复审阶段** — 每次任务完成后调用 `superpowers:requesting-code-review` + `superpowers:receiving-code-review`

### TDD 铁律

- **先写失败测试，再写实现代码**，测试通过后不得多写额外逻辑
- 使用 `superpowers:tdd` skill 强制执行 RED → GREEN → REFACTOR 循环
- 禁止提交未经测试覆盖的新功能代码

### 调试规范

遇到 bug 时必须使用 `superpowers:systematic-debugging`：
1. 复现并记录现象
2. 追踪根因（不得猜测修复）
3. 修复后验证原始场景

### 并行任务

独立子任务可通过 `superpowers:executing-plans` 的并行 subagent 分发机制同时执行，以加快交付。

---

## 技术规范

### TypeScript
- **运行时**：Node.js；包管理器优先 `pnpm`
- **测试**：`vitest`（单元）/ `playwright`（E2E）；命令 `pnpm test`
- **构建**：`pnpm build`（tsc 严格模式，`strict: true`）
- **代码风格**：ESLint + Prettier，提交前 `pnpm lint && pnpm format`
- **类型**：禁止 `any`，接口优先于 `type`，导出类型用 `export type`

### Python
- **版本**：3.11+；包管理器 `uv`
- **测试**：`pytest`；命令 `uv run pytest`
- **代码风格**：`ruff`（lint + format）；提交前 `uv run ruff check . && uv run ruff format .`
- **类型**：全量 `mypy` 检查，禁止 `# type: ignore`（有理由时须注释说明）
- **依赖**：生产依赖写入 `pyproject.toml`，禁止裸 `pip install`

### .NET
- **版本**：.NET 8+；包管理器 `dotnet CLI`
- **测试**：`xUnit`；命令 `dotnet test`
- **代码风格**：`.editorconfig` + `dotnet format`；提交前 `dotnet format --verify-no-changes`
- **类型**：启用可空引用类型（`<Nullable>enable</Nullable>`），禁止 `null!` 强制断言（有理由时须注释说明）
- **依赖**：通过 `dotnet add package` 管理，禁止手动编辑 `.csproj` 版本号
- **架构**：按 Clean Architecture 分层（Domain / Application / Infrastructure / API）

## 语言规范（强制）

**所有输出必须使用中文**，无例外：
- 对话回复、解释说明
- 代码注释（行注释 / 文档注释 / JSDoc / docstring / XML doc）
- 任务计划、检查点、验收标准
- Git commit message 描述部分
- 文档、README、设计文档
- Code review 意见与反馈

> 代码标识符（变量名、函数名、类名）保持英文；仅文字内容强制中文。

---

## 提交规范

```
<type>(<scope>): <描述>

type: feat | fix | test | refactor | docs | chore
```

提交前必须：测试全部通过 → code-review 无阻断性问题 → lint 检查通过

---

## 项目术语 glossary

本节集中定义 spec / plan / retro 反复出现的项目内部术语，新工程师快速理解上下文。

> **memory 引用约定**：下表 "见 memory `xxx.md`" 引用为本仓主 maintainer 的 Claude Code session memory（per-instance；位于 `~/.claude/projects/D--Work-cad-spec-gen/memory/`，其他开发者本机路径相对应）。每项术语已附 1 行含义，可独立读懂；memory 引用为深入查阅入口而非必需（layer 6 F1 教训：git tracked 文档避免假定用户特定路径）。

1. **北极星 5 gate** — 零配置 / 稳定可靠 / 结果准确 / SW 装即用 / 傻瓜式操作；任何新 plan 必过这 5 条 gate（见 memory `project_north_star.md`）

2. **v2.25+ tag-only release** — 纯 git tag + GitHub Release notes 发布模式；不 bump `pyproject.toml` 版本（停留 `2.24.0`）；用户安装走 `pip install git+https://github.com/proecheng/cad-spec-gen.git@vX.Y.Z`（见 memory `project_current_status.md` / `project_v2_31_1_packaging_cleanup.md`）

3. **canonical / mirror** — `tools/jury/*.py` 等是 canonical（git tracked）；`src/cad_spec_gen/data/tools/jury/*.py` 是 mirror（gitignored，`scripts/dev_sync.py` 同步）；`hatch_build.py` `COPY_DIRS = {"tools": "tools"}` 打包发用户（定义见 v2.37.2 spec §6 #7-#9 + `scripts/dev_sync.py`；漂移防御见 memory `feedback_subagent_cwd_drift.md`）

4. **§11 vs §12 follow-up 轨道** — §11 = 项目级 STATUS doc（如 `docs/superpowers/JURY_MATCHES_SPEC_STATUS.md`）的 follow-up 表；§12 = 单个 spec doc 自身 PR-self follow-up 表；两个独立轨道不混，新登必明确归哪个（见 memory `project_v2_37_4_done.md`）

5. **pure refactor PR / no-RED phase** — refactor 或 docs-only PR 用既有测试作 GREEN safety net，不需 TDD RED 阶段；R-only 模式；commit body 必显式标注（见 v2.37.3 spec §3.4 D4）

6. **5 层 + 1 scout 审查** — spec ≥ 100 行默认跑：self / cynical re-read / code-spec 对照 / edge-case hunter / 5 角色 adversarial + dry-run 五层 + writing-plans 入口 scout grep；每层抓不同 bug 类别（见 memory `feedback_spec_review_4layers.md`）

7. **subagent-driven 模式** — 主 agent 每 plan task 派发 fresh subagent 实施，跑 2 阶段 review（spec compliance + code quality）；fresh context 防污染；项目连续 13+ PR 一次过 CI 实证（见 memory `feedback_subagent_driven_main_agent_scouts.md`）

8. **layer 6 grep AC predicates** — spec AC 用 grep strict 验证时：(a) 抽 helper 类 refactor 用 exclusion-zone（`grep -v` 排除 helper 自身行）或 indent-anchor（`grep "    pattern"` 限 test-body context）；(b) OR pattern 用 `grep -cE "X|Y"` 显式 ERE 跨平台可靠；不用 `\|`（GNU grep BRE 支持但 BSD / MSYS grep BRE 不识别，跨 grep 实现不可靠）（见 v2.37.3 / v2.37.4 retro）

9. **sw-smoke CI flake** — `.github/workflows/sw-smoke.yml` 的 `actions/upload-artifact@v7` 步是已知 transient flake 点；非 SW 测试本身挂；与 `tests.yml` 8 job release gate 无关，单独失败不阻断 release（见 memory `feedback_sw_runner_infra.md`）

10. **plan-drift 5 分类** — spec 写时常踩的假设漂移类型：(a) API 不存在 (b) 路径假设错 (c) 测试 helper 误用 (d) 实现细节 bug (e) 参数签名；plan 第 0 task scout grep 防御（见 memory `feedback_plan_drift_taxonomy.md`）

> **新增术语门槛**：同一术语在 ≥ 3 份 spec/plan/retro 重复出现 → 开 follow-up PR 加入本表。维持 mini-glossary 精简性。

---

## memory 引用约定

spec / plan / retro 文档引用 session memory 时，必含 ≤20 **字符**（不是字节；中文 1 char = 1 字符 ≠ 3 utf-8 bytes）inline 摘要防 memory 改名/归档后失锚（layer 5 R2 L3 教训）。

**约定格式**：

```
见 memory `xxx.md`（摘要：≤20 字含义）
```

**约束范围**：

- **仅未来 spec/plan/retro 文档生效**；既有文档（v2.37.5 之前）不强制 retro-fit
- 鼓励渐进改进：触及既有文档 memory 引用时顺手补摘要
- 新旧格式兼容：v2.37.5 §项目术语 glossary 既有写法 `（见 memory `xxx.md`）` 不删；新约定 = 新写文档时含摘要；新旧并存合法

**示例**（新写）：

```
见 memory `feedback_spec_review_4layers.md`（摘要：spec ≥100 行 5 层默认审）
```
