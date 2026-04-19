# Skills 重构设计 — 单一真相源 + 跨 LLM + 双语可选

**日期**：2026-04-19
**状态**：设计稿（待 review → writing-plans）
**作者**：brainstorming session 8 续作
**依赖**：PR #9（sw-zero-config-experience）已合入或并行推进

## 1. 背景与问题

### 1.1 现状

cad-spec-gen 有 5 个 skill（cad-spec / cad-codegen / cad-enhance / cad-help / mechdesign），维护在 **4 处副本**：

| 位置 | 角色 | 语言 |
|---|---|---|
| `.claude/commands/*.md` | Claude Code 加载（仓库根，入 git） | 中文 |
| `src/cad_spec_gen/data/commands/zh/*.md` | pip install 用户装包（packaged，入 git） | 中文 |
| `src/cad_spec_gen/data/commands/en/*.md` | 同上，英文版（入 git） | 英文 |
| `src/cad_spec_gen/data/skill.json` | metadata 汇总，`description` 字段内联 5 个 skill 长文本 | 英文 |

### 1.2 痛点

1. **漂移不可避免**：2026-04-19 session 8 Task 35 只改了 `.claude/commands/cad-spec.md + cad-codegen.md` 的"SW 装即用集成"段落，**未同步到 packaged zh/en + skill.json**。这类漂移历史上发生多次，没有结构性防护。
2. **维护者改一处需 4 次同步**：违反 DRY；`skill.json` 的 `description` 字段与对应 `.md` body 内容重复约 80%。
3. **非 Claude LLM 无文档索引**：Codex / Cursor / Zed / GLM 等读不到 `.claude/commands/`；`AGENTS.md` 不存在。
4. **双语切换无机制**：pip 用户装完包只能用 `.claude/commands/*.md`（固定中文），切英文要手改 `skill_register.py` 配置。**但已有 `cad-skill-setup --lang zh|en` CLI 解决这部分**——只是维护层面依然不存在统一源。

### 1.3 已有资产（重构必须复用，不重造）

在设计前已探查发现：

- **`cad-skill-setup`** CLI（`src/cad_spec_gen/cli.py:main_setup`）已支持 `--lang zh|en --target --update`
- **6-step wizard**（`src/cad_spec_gen/wizard/wizard.py`）含 banner / env / 依赖 / Blender / Gemini / skill 注册
- **`skill_register.py`** 255 行已做：从 `data/commands/{lang}/` 复制到用户 `.claude/commands/`、`.cad_skill_version.json` 版本标记、MD5 hash 用户修改检测、update 模式保留用户改动
- **`i18n.py`** 翻译层
- **build backend**：hatchling

## 2. 目标与非目标

### 2.1 目标

1. **单一真相源**：`skills/<id>/{skill.yaml,zh.md,en.md}`，其他副本全部由 SoT 生成
2. **防漂移**：pre-commit hook 检测未同步的改动，commit 拒绝
3. **跨 LLM 兜底**：生成 `AGENTS.md` 给 Codex / Cursor / Zed / GLM 等非 Claude LLM
4. **双语可选**：用户在 `cad-skill-setup --lang zh|en` 选一次（安装时决定）；maintainer 维护双语 SoT
5. **零用户侵入**：pip 用户体验 100% 不变（`cad-skill-setup` / `.claude/commands/` 消费路径不改）

### 2.2 非目标

- **不改 skill 内容**（P 方案 — 纯结构迁移 + 修 Task 35 漂移，不刷新措辞）
- **不新增 CLI**（`cad-skill-setup` 已完美匹配，不造新 `cad-spec-gen init`）
- **不做运行时语言切换**（安装时一次选，和北极星"零配置/傻瓜式"一致）
- **不重构 wizard/skill_register**（它们消费 `data/commands/{lang}/`，继续可用）
- **不做第三种语言**（schema 开放但不预装 ja/fr/…）

### 2.3 首要用户（按优先级）

| 用户 | 身份 | 方便 = 什么 |
|---|---|---|
| **2 — Repo maintainer** | 改 skill 内容的人 | 单一源、改一处、pre-commit 自动校验 |
| **3 — pip install 终端用户** | `pip install cad-spec-gen` 后使用 | 装完能用、双语可选、非 Claude 也能看懂 |
| 1 — Claude Code dev | 日常 `/cad-spec` 调用者 | （本次不优化此类——他们已用得好） |

## 3. 设计

### 3.1 目录结构（重构后）

```
cad-spec-gen/                              # 仓库根
├── skills/                                # ★ SoT（单一真相源，入 git）
│   ├── cad-spec/
│   │   ├── skill.yaml                     # metadata (id/trigger/name.zh/en/description.zh/en)
│   │   ├── zh.md                          # 中文正文（slash command body）
│   │   └── en.md                          # 英文正文
│   ├── cad-codegen/…                      # 同上
│   ├── cad-enhance/…
│   ├── cad-help/                          # 额外含 knowledge files
│   │   ├── skill.yaml
│   │   ├── zh.md
│   │   ├── en.md
│   │   ├── knowledge.zh.md                # ★ 长 knowledge 文档（技术百科），cad-help 专用
│   │   └── knowledge.en.md
│   └── mechdesign/                        # 同上（knowledge.{zh,en}.md）
│
├── build/
│   ├── sync_skills.py                     # 构建脚本（CLI：build/check/list/validate）
│   └── hatch_sync_hook.py                 # hatchling build hook
│
├── .claude/commands/                      # Claude Code 消费（入 git，默认 zh）
│   └── *.md                               # 生成自 skills/<id>/zh.md
│
├── AGENTS.md                              # 跨 LLM 消费（入 git，默认 zh）
│
├── src/cad_spec_gen/data/                 # pip 打包资源
│   ├── commands/zh/*.md                   # ❌ gitignore，hatch hook 生成
│   ├── commands/en/*.md                   # ❌ gitignore，hatch hook 生成
│   └── skill.json                         # ❌ gitignore，hatch hook 生成
│
└── .pre-commit-config.yaml                # sync check hook
```

### 3.2 数据流

```
skills/<id>/{skill.yaml,zh.md,en.md}   ← SoT（唯一维护点）
     │
     ├── [manual] python build/sync_skills.py build        → .claude/commands/*.md (入 git，默认 zh)
     ├── [manual] python build/sync_skills.py build        → AGENTS.md             (入 git，默认 zh)
     ├── [hatch]  python -m build 触发 hatch_sync_hook.py  → data/commands/{zh,en}/*.md, skill.json (gitignored，入 wheel)
     ├── [pip install 后] cad-skill-setup --lang zh|en    → 用户项目 .claude/commands/*.md (现有逻辑)
     └── [pre-commit] sync_skills.py check                 → exit 1 if drift detected
```

### 3.3 skill.yaml schema

```yaml
id: cad-spec                              # 必填，全局唯一
trigger: /cad-spec                        # 必填，Claude slash trigger
name:
  zh: CAD Spec 生成器                     # 必填
  en: CAD Spec Generator                  # 必填
description:                              # 必填，≤ 200 字给列表/AGENTS.md 用
  zh: "Phase 1: 从设计文档提取 9 类结构化数据到 CAD_SPEC.md。"
  en: "Phase 1: Extract 9 categories of structured data..."
entry_point: python cad_pipeline.py spec  # 可选，非 Claude LLM 的 CLI 入口
knowledge_file: skill_cad_help.md         # 可选，仅 cad-help 用
```

5 个 skill 的 metadata（从现有 `skill.json` 抽出）：

| skill | trigger | entry_point | knowledge_file |
|---|---|---|---|
| cad-spec | `/cad-spec` | `python cad_pipeline.py spec` | - |
| cad-codegen | `/cad-codegen` | `python cad_pipeline.py codegen` | - |
| cad-enhance | `/cad-enhance` | - | - |
| cad-help | `/cad-help` | - | `skill_cad_help.md` |
| mechdesign | `/mechdesign` | `python cad_pipeline.py mechdesign` | `skill_mech_design.md` |

**Knowledge files 说明**：cad-help 和 mechdesign 各有一份独立 knowledge 文档（技术百科），给 Claude 消费的完整知识库。SoT 里分别位于 `skills/cad-help/knowledge.{zh,en}.md` 和 `skills/mechdesign/knowledge.{zh,en}.md`。`sync_skills.py build` 时生成到 `data/skill_cad_help_{zh,en}.md` 和 `data/skill_mech_design_{zh,en}.md`（扁平结构，兼容现有 `skill_register.py` 的消费路径）。

### 3.4 `build/sync_skills.py` CLI

| 子命令 | 行为 | 用途 |
|---|---|---|
| `build [--lang zh\|en]` | 从 SoT 生成全 5 类产物；默认 lang=zh | 维护者手动、hatchling hook、切语言 |
| `check` | 对比"应当生成"vs 磁盘现有 `.claude/commands/*` 和 `AGENTS.md`，不一致 exit 1 | pre-commit 守护 |
| `list` | 列所有 skill（id/trigger/description 一行） | 开发辅助 |
| `validate` | 校验 skill.yaml schema + .md 非空 + 5 skill 齐全 | 开发辅助 |

生成的 6 类产物：

| # | 目标 | 来源 | 入 git |
|---|---|---|---|
| 1 | `.claude/commands/<id>.md` | `skills/<id>/<lang>.md` | ✅ |
| 2 | `AGENTS.md` | `skill.yaml` × 5 汇总 | ✅ |
| 3 | `src/cad_spec_gen/data/commands/zh/<id>.md` | `skills/<id>/zh.md` | ❌ |
| 4 | `src/cad_spec_gen/data/commands/en/<id>.md` | `skills/<id>/en.md` | ❌ |
| 5 | `src/cad_spec_gen/data/skill.json` | `skill.yaml` × 5 metadata compile | ❌ |
| 6 | `src/cad_spec_gen/data/skill_{cad_help,mech_design}_{zh,en}.md` (4 files) | `skills/{cad-help,mechdesign}/knowledge.{zh,en}.md` | ❌ |

### 3.5 hatchling build hook

`pyproject.toml`：
```toml
[tool.hatch.build.hooks.custom]
path = "build/hatch_sync_hook.py"
```

`build/hatch_sync_hook.py` ≈ 20 行，调 `subprocess.run([sys.executable, "build/sync_skills.py", "build"])`，失败则 `python -m build` 失败（fail-fast，防发布坏包）。

### 3.6 AGENTS.md 结构

模板（≈ 80 行，从 `skill.yaml` × 5 生成）：

```markdown
# AGENTS.md — cad-spec-gen 代理指南

> 自动生成 @ git rev {{short_sha}}。请勿手改；变更在 `skills/<id>/{skill.yaml,zh.md,en.md}` 提交。

## 项目概述
cad-spec-gen 是 6 阶段 CAD 混合渲染管线。仓库：https://github.com/proecheng/cad-spec-gen

## 可用 Skill（5 个）

| Skill | Trigger | 说明 | 入口命令 |
|---|---|---|---|
| CAD Spec 生成器 | `/cad-spec` | {{description.zh}} | `python cad_pipeline.py spec` |
| ... (5 行) |

## 详细用法

### /cad-spec — CAD Spec 生成器
{{description.zh}}

**典型调用**：
```
/cad-spec docs/design/04-xxx.md
/cad-spec --all --force
```

完整用法：见 `skills/cad-spec/zh.md`。

### /cad-codegen ... (×5 skill)

## 约定

- 所有输出中文（代码标识符除外）
- 测试：`.venv/Scripts/python.exe -m pytest`
- commit：`<type>(<scope>): <中文描述>`
- 零硬编码：`sw_preflight/` 子包禁止路径/版本字面值

## 开发者

改 skill 走 `skills/<id>/{zh,en}.md`；跑 `python build/sync_skills.py build`。
pre-commit 自动 check。

---
_v{{skill_json.version}}_
```

**确定性保证**：不含 ISO timestamp；`{{short_sha}}` 从 git 读；版本号从 skill.json 读。连跑 2 次 sync build，`AGENTS.md` 字节相等（测试守护）。

### 3.7 pre-commit hook

`.pre-commit-config.yaml`：
```yaml
repos:
  - repo: local
    hooks:
      - id: sync-skills-check
        name: sync-skills drift check
        entry: python build/sync_skills.py check
        language: system
        files: ^(skills/|\.claude/commands/|AGENTS\.md$)
        pass_filenames: false
```

`pre-commit` 加到 dev deps（`pyproject.toml` 的 `[project.optional-dependencies].dev`）。`README.md` 文档化："clone 后跑 `pre-commit install` 一次"。

### 3.8 `cad-skill-setup` 零改动

现有 `src/cad_spec_gen/wizard/skill_register.py` 消费 `data/commands/{lang}/*.md` → 复制到用户 `.claude/commands/`。

新 SoT 下 `data/commands/{lang}/` 由 hatch hook 在 `python -m build` 时生成到 wheel。pip install 后 `data/commands/{lang}/` 还是存在（在 site-packages 里）。**skill_register.py 消费路径零变化**。

## 4. 迁移计划（分 3 PR）

### PR1 — 建立 SoT + sync 脚本（Phase 1-2）
1. 建 `skills/<id>/` × 5 目录（从现有 `skill.json` 抽 metadata 写 `skill.yaml`，从 `.claude/commands/` 拷 zh.md，从 `data/commands/en/` 拷 en.md）
2. 建 knowledge files：`skills/cad-help/knowledge.{zh,en}.md` 和 `skills/mechdesign/knowledge.{zh,en}.md`（从现有 `data/skill_cad_help_{zh,en}.md` 和 `data/skill_mech_design_{zh,en}.md` 拷入）
3. 修 Task 35 漂移（"SW 装即用集成"段同步到 `skills/cad-spec/en.md` + `cad-codegen/en.md`）
4. 写 `build/sync_skills.py` + `build/hatch_sync_hook.py`（覆盖全 6 类产物）
5. 跑 `sync build` 验证 `.claude/commands/*.md` + `data/skill_*_{zh,en}.md` 与迁移前字节相等（除漂移段）
6. 改 `pyproject.toml` 加 hatch hook

**PR1 合入后状态**：SoT 存在 + sync 可用 + `.claude/commands/` 继续由 SoT 生成；旧 `src/cad_spec_gen/data/commands/{zh,en}/` 依然手维护（未切换）；仓库处于"SoT + 旧手维护"共存的稳态，随时可回滚。

### PR2 — 切换 packaged 为生成产物 + 加 AGENTS.md（Phase 3-4）
7. 删除 `src/cad_spec_gen/data/commands/{zh,en}/` + `data/skill.json` + `data/skill_cad_help_{zh,en}.md` + `data/skill_mech_design_{zh,en}.md` 现有文件
8. `.gitignore` 加对应 6 类规则（commands/zh/, commands/en/, skill.json, skill_cad_help_*.md, skill_mech_design_*.md）
9. 跑 `pip install -e . --force-reinstall` 验证 `cad-skill-setup --lang zh/en` 仍工作（skill_register 依赖的 4 个 knowledge files 由 sync 生成到 `data/`）
10. 生成 `AGENTS.md` 并 commit

**PR2 合入后状态**：SoT 完全就位，packaged 是 build 产物；AGENTS.md 可用。仍无防漂移守护。

### PR3 — pre-commit 守护（Phase 5）
11. 加 `pre-commit` 到 dev deps
12. 写 `.pre-commit-config.yaml`
13. `README.md` 文档化 `pre-commit install`
14. 验证：改 `skills/` 未跑 sync 直接 commit → hook 阻止

**PR3 合入后状态**：完整终态；漂移从"偶尔发生"变"结构上不可能"。

### 回滚策略
- 任一 PR 合入后若出问题，`git revert` 回退
- PR1 合入后仓库进入"稳态 A"（SoT + 旧手维护共存），可长期驻留
- PR2 若出问题（比如 `cad-skill-setup` 在 wheel 里找不到 generated 文件），revert 回 PR1 状态即可

## 5. 测试策略

### 5.1 TDD 分层（详见章节 G）

| Layer | 目标 | 文件 |
|---|---|---|
| L1 单元 | `sync_skills.py` 各子命令逻辑 | `tests/test_sync_skills.py` |
| L2 确定性 | AGENTS.md 无 timestamp / 字节稳定 | `tests/test_agents_md_deterministic.py` |
| L3 迁移回归 | `.claude/commands/*.md` 字节对等 + cad-skill-setup regression | `tests/test_migration_byte_parity.py` |
| L4 pre-commit | hook 正确阻塞 / 放行 | `tests/test_pre_commit_hook.py` |
| L5 hatch hook | `python -m build` 触发 sync + wheel 含 generated | `tests/test_hatch_build_hook.py` |

### 5.2 测试夹具

`tests/fixtures/sample_skills/` — 2 个假 skill（foo / bar），各含 skill.yaml + zh.md + en.md，驱动 L1/L2/L4 单元测试，避免污染 5 个真 skill。

### 5.3 覆盖率
- `build/sync_skills.py` 行覆盖 ≥ 90%
- 关键路径（build/check/validate）100%

### 5.4 不测
- `.md` body 内容（P 方案不改内容）
- Claude Code 真实 slash 触发（需 Claude Code 运行）
- 跨 LLM 对 AGENTS.md 的实际消费

## 6. 风险与缓解

| 风险 | 触发 | 缓解 |
|---|---|---|
| hatch hook 在 `python -m build` 失败 | sync_skills.py bug | fail-fast；L5 集成测试守护；CI 跑 wheel build |
| pre-commit 阻止紧急 hotfix | hook 误判 | 临时 `git commit --no-verify` 绕过；README 文档化 |
| skills/ 删除历史丢失翻译 | PR1 误操作 | 迁移前 tag；翻译源从现 `.claude/commands/` + `data/commands/en/` 提取，不丢 |
| pip 用户卡在 `data/commands/` gitignore | 误 pip install dev 模式 | `pip install -e .` 需先跑一次 `python -m build` 生成 packaged；README 明示 |
| 漂移检测误报（大小写/换行符差异） | Windows CRLF | sync_skills.py 用 `universal_newlines=True` 统一；测试验证跨平台 |

## 7. 开放问题（进入 plan 前解决）

无。设计定稿。

## 8. 附录：用户回答的关键决策

| 问题 | 选择 |
|---|---|
| 跨 LLM 目标平台 | Claude 原生 + AGENTS.md 跨 LLM 兜底 |
| 语言选择时机 | 安装时（`cad-skill-setup --lang`，已有） |
| SoT 布局 | X — skill-per-folder + 语言并列 |
| 构建产物入 git | 丙 — SoT + `.claude/commands/` + AGENTS.md 入 git；packaged/skill.json gitignore |
| 首要用户 | 2 + 3（maintainer + pip 终端用户） |
| pip 交付机制 | γ — 复用现有 `cad-skill-setup`（不新建 CLI） |
| 内容重构深度 | P — 最小侵入，仅同步 + 修 Task 35 漂移，不改措辞 |
| 3 个次要问题 | 按"用户使用方便简单为准" — description ≤ 200 字、entry_point 可选、knowledge_file 可选 |

---

_下一步：调 `superpowers:writing-plans` skill 产出实施 plan。_
