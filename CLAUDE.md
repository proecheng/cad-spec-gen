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
