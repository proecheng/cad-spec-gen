# Skills 重构设计 — 单一真相源 + 跨 LLM + 双语可选

**日期**：2026-04-19
**状态**：设计稿 v2（经 3 角色审查修订，待 review → writing-plans）
**作者**：brainstorming session 8 续作 + 3 角色并行审查
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

1. **漂移不可避免**：session 8 Task 35 只改了 `.claude/commands/cad-spec.md + cad-codegen.md` 的"SW 装即用集成"段落，**未同步到 packaged zh/en + skill.json**。历史多次发生。
2. **维护者改一处需 4 次同步**：违反 DRY；`skill.json.description` 字段与对应 `.md` body 重复 80%。
3. **非 Claude LLM 无文档索引**：Codex / Cursor / Zed / GLM 等读不到 `.claude/commands/`；`AGENTS.md` 不存在。
4. **双语切换无机制 for maintainer**：运行时通过 `cad-skill-setup --lang` 已解决（用户侧），但 maintainer 侧没有统一源。

### 1.3 已有资产（重构必须复用）

- **`cad-skill-setup`** CLI 支持 `--lang zh|en --target --update`
- **6-step wizard**（`src/cad_spec_gen/wizard/wizard.py`）
- **`skill_register.py`** 255 行：复制 `data/commands/{lang}/` → `.claude/commands/`；`.cad_skill_version.json` 版本标记；MD5 hash 用户修改检测；update 模式
- **`i18n.py`** 翻译层
- **build backend**：hatchling

## 2. 目标与非目标

### 2.1 目标

1. **单一真相源**：`skills/<id>/{skill.yaml,zh.md,en.md[,knowledge.{zh,en}.md]}`，其他副本由 SoT 生成
2. **防漂移**：pre-commit hook + CI 二道防线检测未同步改动，commit / merge 双重拒绝
3. **Claude + Codex CLI 兼容**：生成 `AGENTS.md` 供 Codex CLI 原生消费；Cursor / Cline / Zed / GLM 等其他 LLM 可读 `AGENTS.md` 作为**尽力兜底**（不保证跨版本稳定）
4. **双语可选**：maintainer 维护双语 SoT；用户通过 `cad-skill-setup --lang zh|en` 选一次（已有机制）；`build --lang en` 同步切换 `.claude/commands/` + `AGENTS.md`
5. **零用户侵入**：pip 用户体验 100% 不变（`cad-skill-setup` / `.claude/commands/` 消费路径不改）

### 2.2 非目标

- **不改 skill 内容**（P 方案 — 纯结构迁移 + 修 Task 35 漂移）
- **不新增 CLI**（`cad-skill-setup` 已完美匹配）
- **不做运行时语言切换**（安装时一次选）
- **不重构 wizard/skill_register**（继续消费 `data/commands/{lang}/`）
- **不做第三种语言**（schema 开放但不预装 ja/fr/…）
- **不支持 Cursor / Cline / Zed 的原生 rules 格式**（只给 AGENTS.md 兜底，未来单独 spec 扩展）
- **不做外行用户 UX**（首次体验走查 / `--lang` 自动检测 / 业务场景示例 / 从 JPG 到 3D 的 onboarding 路径 → 独立 UX spec 承载，不在本技术重构范围）

### 2.3 首要用户（按优先级）

| 用户 | 身份 | 方便 = 什么 |
|---|---|---|
| **2 — Repo maintainer** | 改 skill 内容的人 | 单一源、改一处、pre-commit 自动校验 |
| **3a — pip install 开发者/集成者** | 会 terminal、会 Python、为自己或团队部署 | 装完能用、双语可选、非 Claude 也能看懂 |
| 3b — 外行终端用户（非本 spec 范围） | 不会 terminal、不懂 slash command | **由独立 UX spec 承载**，本 spec 不服务 |
| 1 — Claude Code dev | 日常 `/cad-spec` 调用者 | （本次不优化） |

## 3. 设计

### 3.1 目录结构（重构后）

```
cad-spec-gen/                              # 仓库根
├── skills/                                # ★ SoT（单一真相源，入 git）
│   ├── cad-spec/
│   │   ├── skill.yaml                     # metadata
│   │   ├── zh.md                          # 中文正文（slash command body）
│   │   └── en.md                          # 英文正文
│   ├── cad-codegen/…
│   ├── cad-enhance/…
│   ├── cad-help/                          # 额外含 knowledge files
│   │   ├── skill.yaml
│   │   ├── zh.md
│   │   ├── en.md
│   │   ├── knowledge.zh.md                # 技术百科，cad-help 专用
│   │   └── knowledge.en.md
│   └── mechdesign/                        # 同上
│
├── build/
│   ├── sync_skills.py                     # 构建脚本（4 子命令）
│   ├── hatch_sync_hook.py                 # hatchling build hook（wheel build 兜底）
│   └── targets/                           # 预留扩展槽（未来加 cursor.py / cline.py）
│
├── .gitattributes                         # *.md text eol=lf（统一换行符）
├── .pre-commit-config.yaml                # sync check hook
│
├── .claude/commands/                      # Claude Code 消费（入 git，默认 zh）
│   └── *.md                               # 首行含"auto-generated"警示
│
├── AGENTS.md                              # 跨 LLM 消费（入 git，默认 zh）
│                                          # 首行含"auto-generated"警示
│
└── src/cad_spec_gen/data/                 # pip 打包资源（★ 全部入 git，放弃 gitignore 方案）
    ├── commands/
    │   ├── zh/*.md                        # ✅ 入 git，由 sync 生成 + pre-commit 守护一致性
    │   └── en/*.md                        # ✅ 入 git，同上
    ├── skill.json                         # ✅ 入 git，由 sync 生成 + pre-commit 守护
    ├── skill_cad_help_{zh,en}.md          # ✅ 入 git，由 sync 生成（skill_register 消费）
    └── skill_mech_design_{zh,en}.md       # ✅ 入 git，由 sync 生成
```

**关键决策变更（B2 决策 A）**：原 spec 计划 `data/commands/{zh,en}/` 和 `skill.json` gitignore + hatch hook 生成——但 `pip install -e .`（editable 模式）不跑 build backend，会导致 dev checkout 后 `cad-skill-setup` 找不到文件 FileNotFoundError。改为：**全部产物入 git，由 pre-commit 守护与 SoT 一致**。代价是 PR 多一份冗余；回报是 dev 体验永远不坏 + editable install 零配置。

### 3.2 数据流

```
skills/<id>/{skill.yaml,zh.md,en.md[,knowledge.{zh,en}.md]}   ← SoT（唯一维护点）
     │
     ├── [manual] cad-sync build（pyproject.toml [project.scripts] 暴露的短命令）
     │
     ├─── 生成产物（全部入 git）：
     │    ├── .claude/commands/*.md              （默认 zh）
     │    ├── AGENTS.md                          （默认 zh）
     │    ├── src/cad_spec_gen/data/commands/{zh,en}/*.md
     │    ├── src/cad_spec_gen/data/skill.json
     │    └── src/cad_spec_gen/data/skill_{cad_help,mech_design}_{zh,en}.md
     │
     ├── [pre-commit] cad-sync check       → exit 1 if drift detected
     ├── [CI] cad-sync check              → 二道防线（防 --no-verify 绕过）
     └── [pip install 后] cad-skill-setup --lang zh|en → 用户项目 .claude/commands/（skill_register 现有逻辑）

可选：hatch_sync_hook.py 在 `python -m build` 时再跑一次 sync
     （兜底：若维护者漏跑 sync 就 push，wheel build 还能自动修复）
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
  en: "Phase 1: Extract 9 categories..."
entry_point: python cad_pipeline.py spec  # 可选，非 Claude LLM 的 CLI 入口
knowledge_file: skill_cad_help            # 可选，仅 cad-help/mechdesign 用
                                          # 语义：生成产物的文件名前缀（不含 _zh/_en 后缀和 .md）
                                          # 生成到 data/skill_cad_help_zh.md + data/skill_cad_help_en.md
                                          # skill_register 按 lang 选一份改名为 skill_cad_help.md 写到 target
# 以下字段为 v1 扩展预留（I1）
version: 1.0                              # 可选，skill 独立语义版本（不随包版本漂移）
tags: [cad, spec, phase1]                 # 可选，分类标签（AGENTS.md 索引 / 未来搜索用）
deprecated: false                         # 可选，布尔；true 则 AGENTS.md 生成时打删除线 + 提示替代
aliases: [/spec]                          # 可选，slash 别名（Claude Code 暂不支持但预留）
```

**5 个 skill metadata**：

| skill | trigger | entry_point | knowledge_file |
|---|---|---|---|
| cad-spec | `/cad-spec` | `python cad_pipeline.py spec` | - |
| cad-codegen | `/cad-codegen` | `python cad_pipeline.py codegen` | - |
| cad-enhance | `/cad-enhance` | - | - |
| cad-help | `/cad-help` | - | `skill_cad_help` |
| mechdesign | `/mechdesign` | `python cad_pipeline.py mechdesign` | `skill_mech_design` |

**Schema forward-compat**：`validate` 子命令忽略未识别字段（不 fail），允许未来无痛扩展。

**跨语言约束（v1）**：`trigger` / `entry_point` / `id` 跨语言共享（单一值）；`name` / `description` 必双语；`tags` / `aliases` 单语（英文）。

### 3.4 `build/sync_skills.py` CLI

| 子命令 | 行为 | 用途 |
|---|---|---|
| `build [--lang zh\|en]` | 从 SoT 生成全 6 类产物；默认 lang=zh | 维护者、hatchling hook、切语言 |
| `check` | 对比生成内容与磁盘 5 类入 git 产物，不一致 exit 1 | pre-commit + CI |
| `list` | 列所有 skill（id/trigger/description 一行） | 开发辅助 |
| `validate` | 校验 skill.yaml schema + .md 非空 + 5 skill 齐全 + 代码标识符术语白名单（I4） | 开发辅助 |

**Script entry（N2）**：`pyproject.toml` 的 `[project.scripts]` 加 `cad-sync = "build.sync_skills:main"`，装完 `cad-sync build` / `cad-sync check` 一行跑通，不用记 `python build/sync_skills.py` 长路径。

**生成的 6 类产物（全部入 git，B2 决策 A）**：

| # | 目标 | 来源 | 入 git |
|---|---|---|---|
| 1 | `.claude/commands/<id>.md` | `skills/<id>/<lang>.md` + auto-gen 首行 | ✅ |
| 2 | `AGENTS.md` | `skill.yaml` × 5 汇总 + auto-gen 首行 | ✅ |
| 3 | `src/cad_spec_gen/data/commands/zh/<id>.md` | `skills/<id>/zh.md` | ✅ |
| 4 | `src/cad_spec_gen/data/commands/en/<id>.md` | `skills/<id>/en.md` | ✅ |
| 5 | `src/cad_spec_gen/data/skill.json` | `skill.yaml` × 5 metadata compile | ✅ |
| 6 | `src/cad_spec_gen/data/skill_{cad_help,mech_design}_{zh,en}.md`（4 files） | `skills/{cad-help,mechdesign}/knowledge.{zh,en}.md` | ✅ |

**`check` 子命令换行符归一化规则（B3）**：

```python
def _normalize(content: str) -> str:
    """归一化用于 diff 对比。"""
    # 1. 统一换行符 LF（读文件用 open(newline='')；实际内容里的 \r\n → \n）
    content = content.replace('\r\n', '\n').replace('\r', '\n')
    # 2. 去尾换行归一化为恰好 1 个
    content = content.rstrip('\n') + '\n'
    return content
```

仓库根 `.gitattributes` 加：
```
*.md text eol=lf
```
确保 Windows 维护者 clone 后 checkout 是 LF；提交时不被 git 自动转 CRLF。

**规模估算（O1）**：`sync_skills.py` ~500 LOC（含 load skills / render Jinja2 / 写 6 类产物 / 4 子命令 / schema 校验 / 术语白名单）；`hatch_sync_hook.py` ~20 LOC。

### 3.5 hatchling build hook（兜底角色）

B2 决策 A 后，hatch hook 不再是主路径（`data/commands/` 已入 git）。但仍作为**兜底**：

```toml
[tool.hatch.build.hooks.custom]
path = "build/hatch_sync_hook.py"
```

`build/hatch_sync_hook.py` 跑 `sync_skills.py build`，若 SoT 跟磁盘 commit 产物不一致就**修复**——理论上被 pre-commit + CI 挡住了，但若真漂进 main（force push 场景），wheel build 还能自愈。

### 3.6 AGENTS.md 结构

模板（≈ 80 行，从 `skill.yaml` × 5 生成）：

```markdown
<!-- AUTO-GENERATED by build/sync_skills.py — DO NOT EDIT -->
<!-- Source: skills/*/skill.yaml + skills/*/{lang}.md -->

# AGENTS.md — cad-spec-gen 代理指南

> 请勿手改；变更在 `skills/<id>/{skill.yaml,zh.md,en.md}` 提交后跑 `cad-sync build`。
> Generated from git rev: {{rev_label}}

## 项目概述
cad-spec-gen 是 6 阶段 CAD 混合渲染管线。仓库：https://github.com/proecheng/cad-spec-gen

## 可用 Skill（5 个）

| Skill | Trigger | 说明 | 入口命令 |
|---|---|---|---|
| {{name.zh}} | {{trigger}} | {{description.zh}} | {{entry_point or '-'}} |
... (5 行)

## 详细用法

### {{trigger}} — {{name.zh}}
{{description.zh}}

**典型调用**：
```
{{trigger}} ...（示例从 skills/<id>/<lang>.md 抓）
```

完整用法：见 `skills/<id>/<lang>.md`。

## 约定

- 所有输出中文（代码标识符除外）
- 测试：`.venv/Scripts/python.exe -m pytest`
- commit：`<type>(<scope>): <中文描述>`
- 零硬编码：`sw_preflight/` 子包禁止路径/版本字面值

## 开发者

改 skill 走 `skills/<id>/{zh,en}.md`；跑 `cad-sync build` 生成所有产物。
pre-commit 自动 check；CI 二道守护。

---
_v{{skill_json.version}}_
```

**`{{rev_label}}` fallback 策略（I2 + N4）**：

```python
def _get_rev_label() -> str:
    # 1. 优先读 git rev-parse
    try:
        sha = subprocess.check_output(
            ['git', 'rev-parse', '--short', 'HEAD'],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        # dirty 检测
        dirty = bool(subprocess.check_output(
            ['git', 'status', '--porcelain'],
            stderr=subprocess.DEVNULL
        ).decode().strip())
        return f"{sha}-dirty" if dirty else sha
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    # 2. fallback: CI 环境变量
    if sha := os.environ.get('GITHUB_SHA'):
        return sha[:7]
    # 3. final fallback
    return 'unknown'
```

**`build --lang en` 行为（O2）**：同时覆盖 `.claude/commands/*.md` + `AGENTS.md` 两个顶层文件为英文；`data/commands/{zh,en}/` 保持双份。

**确定性**：`{{rev_label}}` 不走 timestamp；`AGENTS.md` 字节级稳定（L2 测试 + L6 golden snapshot 守护）。

### 3.7 pre-commit hook + CI 二道防线（I6）

**`.pre-commit-config.yaml`**：
```yaml
repos:
  - repo: local
    hooks:
      - id: sync-skills-check
        name: sync-skills drift check
        entry: cad-sync check      # 用 project.scripts 短命令
        language: system
        files: ^(skills/|\.claude/commands/|AGENTS\.md$|src/cad_spec_gen/data/)
        pass_filenames: false
```

`pre-commit` 加到 dev deps；`README.md` 文档化 `pre-commit install`。

**CI 二道防线**：`.github/workflows/` 的主 CI job（或新加 `sync-check.yml`）在 Linux + Windows 两个 runner 上跑：
```yaml
- name: Skills SoT drift check
  shell: bash
  run: cad-sync check
```

CI 防止 `git commit --no-verify` 或 fork PR 绕过 pre-commit。

### 3.8 `cad-skill-setup` 衔接 + 增强要求

**现有逻辑零改**——`cad-skill-setup` 继续消费 `data/commands/{lang}/*.md`。

**本 spec 新增要求（给后续 cad-skill-setup spec 接单）**：

1. **OneDrive / 共享盘检测（B4）**：setup 前检测 `target` 路径，命中 `OneDrive` / UNC `\\server\share` / known cloud sync pattern → 警告 + 要求 `--force` 确认
2. **多语言团队说明（I5）**：`README.md` 文档化：
   > "多语言团队：每位开发者本地 `cad-skill-setup --lang xx --target .` 覆盖自己的 `.claude/commands/`；**不要 commit 回仓库**（仓库的 `.claude/commands/` 是维护者默认中文，个人语言切换是本地事项）。如果确需整仓改英文，maintainer 跑 `cad-sync build --lang en` 并 commit。"

这两项**不由本 spec 实现**，但 spec 登记需求；后续由 `cad-skill-setup` 独立 spec 追加。

### 3.9 "Auto-generated" 头部约定（B7）

生成的 `.claude/commands/*.md` 首行加：
```markdown
<!-- AUTO-GENERATED from skills/cad-spec/zh.md — DO NOT EDIT; change source and run `cad-sync build` -->
<!-- 本文件由 build/sync_skills.py 自动生成自 skills/<id>/<lang>.md；手改会被 sync 覆盖 -->

# /cad-spec — 从设计文档生成 CAD Spec
...（原 body）
```

Claude Code 的 slash command markdown 正常忽略 HTML 注释（不参与指令解析），零副作用。

`AGENTS.md` 同样约定（§3.6 模板首行已含）。

### 3.10 漂移段锚点（N3）

为让 L3 "字节对等"测试能自动识别**预期漂移**（Task 35 "SW 装即用集成"等），SoT 源文件里的漂移段前后加注释锚点：

```markdown
<!-- drift:sw-install-ready start -->
## SW 装即用集成 (spec 2026-04-19)
...
<!-- drift:sw-install-ready end -->
```

测试按锚点切片比对非漂移段字节对等，漂移段单独验证已更新。

## 4. 迁移计划（分 3 PR）

### PR1 — 建立 SoT + sync 脚本 + pre-commit（合并原 PR1+PR3，避免循环依赖 B1）
1. 建 `skills/<id>/` × 5 目录：
   - 从 `skill.json` 抽 metadata → `skill.yaml`
   - 从 `.claude/commands/<id>.md` 拷 → `skills/<id>/zh.md`
   - 从 `data/commands/en/<id>.md` 拷 → `skills/<id>/en.md`
   - 从 `data/skill_cad_help_{zh,en}.md` 拷 → `skills/cad-help/knowledge.{zh,en}.md`
   - 从 `data/skill_mech_design_{zh,en}.md` 拷 → `skills/mechdesign/knowledge.{zh,en}.md`
2. 修 Task 35 漂移（"SW 装即用集成"段同步到 `skills/cad-spec/en.md` + `cad-codegen/en.md`，含代码标识符反引号锁）
3. 加漂移段锚点（N3）到 `skills/*/zh.md` + `en.md`
4. 写 `build/sync_skills.py`（4 子命令 + 换行归一化 + Jinja2 渲染 + 术语白名单）
5. 写 `build/hatch_sync_hook.py`（兜底）
6. 加 `.gitattributes`（`*.md text eol=lf`）
7. 改 `pyproject.toml`：
   - 加 `cad-sync` scripts entry
   - 加 hatch custom build hook
   - 加 `pre-commit` 到 dev deps
8. 写 `.pre-commit-config.yaml`
9. **原子操作**：
   - `git rm .claude/commands/*.md` + `git rm src/cad_spec_gen/data/commands/{zh,en}/*.md` + `git rm src/cad_spec_gen/data/skill.json` + `git rm src/cad_spec_gen/data/skill_{cad_help,mech_design}_{zh,en}.md`
   - 跑 `cad-sync build` 重新生成全 6 类产物（含 auto-gen 首行注释）
   - `git add` 全部
10. 字节对等验证：Phase 9 生成的 `.claude/commands/*.md`（去 auto-gen 首行）= 迁移前 `.claude/commands/*.md`（除漂移段，按 drift 锚点切片比）
11. `README.md` 加 "pre-commit install" 步骤 + 多语言团队说明（I5）

**PR1 合入后**：完整 SoT + 自动同步 + 守护全就位。原"分 3 PR"简化为 1 个大 PR。

### PR2 — AGENTS.md（可与 PR1 合并或分开）
12. `sync_skills.py build` 生成 `AGENTS.md`
13. `git add AGENTS.md` commit
14. 验证 `AGENTS.md` 含 5 skill + 约定段 + `{{rev_label}}` 正确解析

PR2 可以 squash 进 PR1，也可以独立（让 PR1 先 review 通过再加 AGENTS.md）。**推荐独立**（PR 大小可控）。

### PR3 — CI 二道防线（可选独立）
15. 加 `.github/workflows/sync-check.yml`（Linux + Windows 两 runner 跑 `cad-sync check`）
16. 验证：故意改 `skills/cad-spec/zh.md` 不跑 sync → push PR → CI fail

### 回滚策略
- PR1 若出问题（hatch hook 冲突 / pre-commit 误判 / 字节对等不过）→ `git revert` 回到 PR#9 tip
- PR2/PR3 独立，各自可 revert 不影响 PR1

## 5. 测试策略

### 5.1 TDD 分层

| Layer | 目标 | 文件 |
|---|---|---|
| L1 单元 | `sync_skills.py` 各子命令逻辑 | `tests/test_sync_skills.py` |
| L2 确定性 | AGENTS.md 无 timestamp / 连跑字节稳定 | `tests/test_agents_md_deterministic.py` |
| L3 迁移回归 | `.claude/commands/*.md` 字节对等（按漂移锚点切片，除 auto-gen 首行）+ cad-skill-setup regression | `tests/test_migration_byte_parity.py` |
| L4 pre-commit | hook 正确阻塞 / 放行 | `tests/test_pre_commit_hook.py` |
| L5 hatch hook | `python -m build` 触发 sync + wheel 含 generated（Linux + Windows 双跑） | `tests/test_hatch_build_hook.py` |
| L6 golden snapshot | `tests/golden/AGENTS.md` 跟 sync 输出字节相等 | `tests/test_agents_md_golden.py` |

### 5.2 测试夹具

`tests/fixtures/sample_skills/` — 2 个假 skill（foo / bar），含 skill.yaml + zh.md + en.md，驱动 L1/L2/L4/L6 单元测试。

L3/L5 用真 `skills/`（验证真迁移/真 build），tmp_path + git worktree 隔离。

### 5.3 CI matrix（I3）

```yaml
strategy:
  matrix:
    os: [ubuntu-latest, windows-latest]
    python-version: ['3.10', '3.12']
env:
  PYTHONIOENCODING: utf-8       # Windows 默认 cp936 常坑中文
```

Windows runner 必须覆盖——本项目北极星 "Windows-only"，CI 不跑 Windows 等于没测。

### 5.4 覆盖率
- `build/sync_skills.py` 行覆盖 ≥ 90%
- 关键路径（build/check/validate）100%

### 5.5 不测
- `.md` body 内容（P 方案不改内容）
- Claude Code 真实 slash 触发
- 跨 LLM 对 AGENTS.md 的实际消费

## 6. 风险与缓解

| 风险 | 触发 | 缓解 |
|---|---|---|
| hatch hook 在 `python -m build` 失败 | sync_skills.py bug | fail-fast；L5 覆盖；CI matrix 跑 Linux+Windows |
| pre-commit 阻止紧急 hotfix | hook 误判 | 临时 `--no-verify` 绕过；README 文档化；CI 二道防线兜底 |
| 漂移检测误报（CRLF / 尾换行） | Windows 编辑器 | `_normalize` 函数 + `.gitattributes`；L3 测试跨平台验证 |
| `{{rev_label}}` 浅克隆 / sdist 场景坏 | `fetch-depth:1` / pip install from sdist | fallback 到 `GITHUB_SHA` → `"unknown"`；L2 测试覆盖 |
| `data/commands/` 入 git 导致 PR 冗余 | B2 决策 A 的代价 | 接受；pre-commit 确保改 SoT 必改副本，review 看 diff 知道是"代码在变"；将来 PR 大可 squash |
| OneDrive 写锁 | 用户装到云盘 | `cad-skill-setup` OneDrive 检测（§3.8）；不是本 spec 实现 |
| 英文 en.md 代码标识符翻译错 | 手动翻译漂移 | 反引号锁 + `validate` 白名单；L3 术语一致性测试 |
| Cursor/Cline/Zed 用户投诉 AGENTS.md 不起作用 | 超出 v1 承诺 | §2.1 明确不保证；`build/targets/` 预留槽，未来单独 spec |

## 7. 开放问题 — 已清

| # | 问题 | 决议 |
|---|---|---|
| O1 | sync_skills.py 规模 | 500 LOC 估算；plan 按此拆 task |
| O2 | AGENTS.md 是否分 zh/en | 跟 `.claude/commands/` 共享 `--lang` 开关；默认 zh；`build --lang en` 同时覆盖 |
| O3 | knowledge_file 字段语义 | **生成产物文件名前缀**（不含 `_zh/_en.md`）；`sync build` 生成 `data/skill_cad_help_{zh,en}.md`；`skill_register` 按 lang 选一份改名 `skill_cad_help.md` 写 target |
| O4 | SW 操作员建议 `--doctor` / per-skill lang / 版本 hash | 全部**不纳入本 spec**；登记给 `cad-skill-setup` 独立迭代 |

## 8. 附录：用户回答的关键决策

| 问题 | 选择 |
|---|---|
| 跨 LLM 目标平台 | Claude + Codex CLI 原生（AGENTS.md）；其他 LLM 不保证 |
| 语言选择时机 | 安装时（`cad-skill-setup --lang`，已有） |
| SoT 布局 | X — skill-per-folder + 语言并列 |
| 构建产物入 git | **丙修正版**：全部入 git + pre-commit 守护（B2 决策 A） |
| 首要用户 | 2 + 3a（maintainer + 会 terminal 的 pip 用户）；**3b 外行划出范围** |
| pip 交付机制 | γ — 复用现有 `cad-skill-setup` |
| 内容重构深度 | P — 最小侵入 |
| 3 方向性决策（审查后） | B2=A / B6=A（Claude+Codex only）/ B5=A（外行 UX 划出） |

## 9. 附录：审查历史

- **初稿** 2026-04-19 （brainstorming 7 节对话产出）
- **v1 committed** @ `ab84034`（333 行）
- **3 角色审查**（Skill 程序员 + SW 操作员 + 外行潜在用户）并行返 ~30 项 findings
- **v2 修订**（本文件）：纳入 7 项 blocker + 6 项 important + 4 项 nit + 4 项 open 的决议；整体扩 ~100 行

---

_下一步：用户 approve v2 后，调 `superpowers:writing-plans` skill 产出实施 plan。_
