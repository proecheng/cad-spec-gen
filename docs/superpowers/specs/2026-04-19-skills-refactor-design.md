# Skills 重构设计 v3 — 保守修补路线（方向 B）

**日期**：2026-04-19
**状态**：设计稿 v3（推翻 v2，改走方向 B 保守路线）
**作者**：brainstorming session 8 + 3 角色审查 + 深度现状核查
**依赖**：PR #9（sw-zero-config-experience）已合入或并行推进

## 0. 版本说明（为什么有 v3）

- **v1**（@ `ab84034`，333 行）：初稿，假设 `.claude/commands/` 是中文 SoT；设计 `skills/<id>/{zh,en}.md` 新目录
- **v2**（@ `7783479`，497 行）：3 角色审查后扩充到 497 行；但**未核对现有 `hatch_build.py` + `scripts/dev_sync.py` + `.pre-commit-config.yaml`**
- **深度核查发现**：现有基础设施已有 SoT + 双向同步 + pre-commit 守护——**v2 提议的 `skills/<id>/` SoT 重建会推翻 ~11 KB 高质量基础设施**
- **v3（本版，方向 B）**：保留现有 `.claude/commands/*.md` 作 zh SoT，只**增量**补齐 en 同步 + metadata 拆分 + AGENTS.md 生成。工作量降至 v2 的 1/5

## 1. 背景与问题

### 1.1 现状（已核实，含基础设施）

cad-spec-gen 有 5 个 skill（cad-spec / cad-codegen / cad-enhance / cad-help / mechdesign）。现有 SoT + 同步链：

| 位置 | 角色 | 谁在用 |
|---|---|---|
| `.claude/commands/*.md` | **中文 SoT**（手维护） | Claude Code 直接加载 |
| `skill_cad_help.md`（根目录） | cad-help 的中文 knowledge SoT | dev_sync/hatch 镜像到 data/knowledge/ |
| `skill_mech_design.md`（根目录） | mechdesign 的中文 knowledge SoT | 同上 |
| `system_prompt.md`（根目录） | 系统提示中文 SoT | 同上 |
| `src/cad_spec_gen/data/commands/zh/*.md` | zh 镜像 | `cad-skill-setup --lang zh` 消费 |
| `src/cad_spec_gen/data/commands/en/*.md` | **en 手维护副本**（漂移根源） | `cad-skill-setup --lang en` 消费 |
| `src/cad_spec_gen/data/knowledge/skill_cad_help_zh.md` 等 | zh 镜像 | skill_register |
| `src/cad_spec_gen/data/skill.json` | metadata 入口（内联 500 字 description） | pip / LLM 消费 |

同步基础设施：

| 组件 | 现状 | 触发 |
|---|---|---|
| `hatch_build.py`（4302 B） | `python -m build` 时同步 zh → data/ | wheel 构建 |
| `scripts/dev_sync.py`（6901 B） | 每次 commit 前跑；和 hatch_build 常量一致（AST parse） | pre-commit |
| `.pre-commit-config.yaml` | 已配 `dev-sync` hook | `git commit` |

### 1.2 真正的问题（现状给出，不是虚构）

1. **en 没自动同步**：`hatch_build.py:61` 注释原文 "en hand-written in data/commands/en/" → Task 35 zh 漂移时 en 不会自动更新 → 漂移根源
2. **zh knowledge 有 en 缺失**：`skill_cad_help_en.md` / `skill_mech_design_en.md` 不存在；`cad-skill-setup --lang en` 安装 knowledge 时走 zh 兜底或报错
3. **`skill.json` description 内联 500 字**：跟 .md body 内容重复 ~80%；改 md 时 json 不会更；也是漂移源
4. **无 AGENTS.md**：Codex CLI / Cursor 等非 Claude LLM 消费方无顶层索引
5. **翻译术语漂移风险**：en.md 手维护导致代码标识符（`PartCategory` / `GATE-3.5` / `sw_preflight`）可能翻译错

### 1.3 已有资产（重构零改动）

- `src/cad_spec_gen/cli.py` 的 `main_setup` / `main_check`
- `src/cad_spec_gen/wizard/{wizard,skill_register,env_detect,i18n,ui,dep_installer,blender_setup,config_gen}.py`
- `src/cad_spec_gen/data/skill.json` → 重构后内容结构改（description 缩到 200 字），但文件位置和消费路径保留
- pip install 后用户体验完全不变

## 2. 目标与非目标

### 2.1 目标

1. **en 漂移根治**：zh.md 改 → en.md 有**术语白名单守护**（自动检测代码标识符一致性）+ pre-commit 提醒"en 未同步"
2. **metadata 拆分**：`skill.json` 的 `description` 字段从 500 字内联 → 200 字摘要；长内容在 `.md` body
3. **AGENTS.md 跨 LLM**：生成一份顶层 `AGENTS.md`（Codex CLI 原生消费；其他 LLM 尽力兜底，不保证）
4. **en knowledge 补齐**：新建 `skill_cad_help_en.md` + `skill_mech_design_en.md` 根目录英文版
5. **零推翻**：`hatch_build.py` + `scripts/dev_sync.py` 增量扩展，不重写

### 2.2 非目标

- **不重写** `hatch_build.py` + `scripts/dev_sync.py`（保留现有架构）
- **不推翻** `.claude/commands/*.md` 的 SoT 地位（继续中文权威）
- **不建** `skills/<id>/` 新目录（v2 方案废弃）
- **不新增** CLI（`cad-skill-setup` 已有 `--lang`）
- **不改 skill 内容**（P 方案，最小侵入）
- **不做外行用户 UX**（独立 UX spec 承载）
- **不支持 Cursor / Cline / Zed 的原生 rules 格式**（只 AGENTS.md 尽力兜底）

### 2.3 首要用户

| 用户 | 方便 = 什么 |
|---|---|
| **2 — Repo maintainer** | 改 zh.md 时 en.md 漂移被 pre-commit 抓 |
| **3a — pip 开发者/集成者** | `cad-skill-setup --lang en` 装英文版能拿到完整 5 skill + knowledge |

## 3. 设计

### 3.1 文件布局变更（最小增量）

**新增 6 类文件**（标 ★）：

```
cad-spec-gen/
├── .claude/
│   ├── commands/                        # 现状保留 — zh SoT
│   │   ├── cad-spec.md
│   │   ├── cad-codegen.md
│   │   ├── cad-enhance.md
│   │   ├── cad-help.md
│   │   └── mechdesign.md
│   │
│   └── commands-en/                     # ★ 新增 — en SoT
│       ├── cad-spec.md
│       ├── cad-codegen.md
│       ├── cad-enhance.md
│       ├── cad-help.md
│       └── mechdesign.md
│
├── skill_cad_help.md                    # 现状 — zh knowledge SoT
├── skill_cad_help_en.md                 # ★ 新增 — en knowledge SoT
├── skill_mech_design.md                 # 现状
├── skill_mech_design_en.md              # ★ 新增
├── system_prompt.md                     # 现状（语言中性，不做双语）
│
├── skills_metadata.yaml                 # ★ 新增 — 5 skill metadata SoT（取代 skill.json 手维护）
│
├── AGENTS.md                            # ★ 新增 — 跨 LLM 兜底（自动生成）
│
├── hatch_build.py                       # 改动 — 增加 en 同步 + AGENTS.md 生成 + skill.json 生成
├── scripts/dev_sync.py                  # 改动 — 同上（保持和 hatch 一致）
│
├── .gitattributes                       # ★ 新增 — *.md text eol=lf
├── .pre-commit-config.yaml              # 现状保留 — dev-sync hook 不变（因 dev_sync 已扩展）
│
└── src/cad_spec_gen/data/               # 全 gitignore 或全入 git（见 §3.7 决策）
    ├── commands/zh/                     # 生成自 .claude/commands/
    ├── commands/en/                     # 生成自 .claude/commands-en/
    ├── knowledge/skill_cad_help_zh.md   # 生成自 skill_cad_help.md
    ├── knowledge/skill_cad_help_en.md   # ★ 生成自 skill_cad_help_en.md
    ├── knowledge/skill_mech_design_zh.md
    ├── knowledge/skill_mech_design_en.md # ★
    ├── system_prompt.md                 # 现状同步
    ├── python_tools/                    # 现状同步
    ├── codegen/ config/ templates/      # 现状同步
    ├── parts_library.default.yaml       # 现状同步
    └── skill.json                       # ★ 改为生成 — 来自 skills_metadata.yaml（metadata compile）
```

### 3.2 数据流

```
.claude/commands/*.md         ← zh SoT（手维护，现状）
.claude/commands-en/*.md      ← en SoT（新增，手维护）
skill_cad_help.md             ← zh knowledge SoT（现状）
skill_cad_help_en.md          ← en knowledge SoT（新增）
skill_mech_design{,_en}.md    ← mechdesign knowledge SoT
skills_metadata.yaml          ← metadata SoT（新增）
     │
     ├── [pre-commit] python scripts/dev_sync.py   → 有变更 exit 1
     ├── [hatch] python -m build                   → wheel 构建同步
     │
     └─── 生成产物：
          ├── src/cad_spec_gen/data/commands/{zh,en}/*.md
          ├── src/cad_spec_gen/data/knowledge/skill_{cad_help,mech_design}_{zh,en}.md
          ├── src/cad_spec_gen/data/skill.json               # 从 skills_metadata.yaml 编译
          ├── AGENTS.md（仓库根，入 git）                    # 从 skills_metadata.yaml + .md body 摘要生成
          └── .claude/commands/*.md + .claude/commands-en/*.md 不变（它们是 SoT）
```

### 3.3 `skills_metadata.yaml` schema

单文件 5 section：

```yaml
# skills_metadata.yaml — 5 skill metadata 单一真相源
# 由 scripts/dev_sync.py 读取生成 src/cad_spec_gen/data/skill.json 和 AGENTS.md

version: "2.10.0"                      # 项目版本（跟 pyproject.toml 一致）
homepage: https://github.com/proecheng/cad-spec-gen
license: MIT
requires:
  python: ">=3.10"
  jinja2: ">=3.0"

skills:
  - id: cad-spec
    trigger: /cad-spec
    name:
      zh: CAD Spec 生成器
      en: CAD Spec Generator
    description:                       # ≤ 200 字
      zh: "Phase 1: 从设计文档提取 9 类结构化数据到 CAD_SPEC.md。v2.10: §6.4 envelopes P7 backfill + §9.2 constraints。支持 --review 模式产出 DESIGN_REVIEW.md。"
      en: "Phase 1: Extract 9 categories of structured data from design documents into CAD_SPEC.md. v2.10: §6.4 envelopes P7 backfill + §9.2 constraints. Supports --review mode."
    entry_point: python cad_pipeline.py spec
    tags: [cad, spec, phase1]

  - id: cad-codegen
    trigger: /cad-codegen
    name:
      zh: CAD Code 生成器
      en: CAD Code Generator
    description:
      zh: "Phase 2: 从 CAD_SPEC.md 生成 CadQuery 脚手架（params/build_all/assembly/part/std 5 类模块）。v2.10: consumes §6.3/6.4/9.1/9.2；GATE-3.5 assembly validation。"
      en: "Phase 2: Generate CadQuery scaffolds from CAD_SPEC.md (5 generator families). v2.10: consumes §6.3/6.4/9.1/9.2; GATE-3.5 assembly validation."
    entry_point: python cad_pipeline.py codegen
    tags: [cad, codegen, phase2]

  - id: cad-enhance
    trigger: /cad-enhance
    name:
      zh: AI 增强
      en: AI Enhancement
    description:
      zh: "Phase 5: Blender 渲染 PNG → 照片级 JPG（4 后端：gemini/fal/comfyui/engineering）。几何锁定仅换皮。多视图一致性 via viewpoint lock。"
      en: "Phase 5: Blender PNG → photorealistic JPG (4 backends: gemini/fal/comfyui/engineering). Geometry locked, reskin only."
    tags: [render, ai, phase5]

  - id: cad-help
    trigger: /cad-help
    name:
      zh: Pipeline 助手
      en: Pipeline Assistant
    description:
      zh: "自然语言管线助手（16 意图：环境/配置/材料/相机/渲染/AI 增强/故障排查/文件结构/状态/BOM/Spec/codegen/设计审查）"
      en: "Natural-language pipeline assistant covering 16 intents."
    knowledge_file: skill_cad_help       # 生成 data/knowledge/skill_cad_help_{zh,en}.md
    tags: [help, assistant]

  - id: mechdesign
    trigger: /mechdesign
    name:
      zh: 参数化机械设计
      en: Parametric Mechanical Design
    description:
      zh: "手动参数化机械子系统工作流（params.py → CadQuery 3D → GB/T 2D 图纸 → Blender 渲染 → AI 增强 6 阶段）"
      en: "Manual parametric mechanical workflow (6 phases)."
    entry_point: python cad_pipeline.py mechdesign
    knowledge_file: skill_mech_design
    tags: [mechanical, parametric]
```

**forward-compat**：dev_sync.py 读时忽略未知字段，允许未来扩展 `version` / `deprecated` / `aliases`。

### 3.4 `hatch_build.py` + `scripts/dev_sync.py` 改动

**增量添加**（不重写）：

```python
# hatch_build.py 改动（约 +40 行）

# 新增：en commands 源
COMMAND_SOURCE_EN = ".claude/commands-en"

# 新增：en knowledge 源（根目录）
EN_KNOWLEDGE_FILES = {
    "skill_cad_help_en.md": "knowledge/skill_cad_help_en.md",
    "skill_mech_design_en.md": "knowledge/skill_mech_design_en.md",
}

# 新增：skills_metadata.yaml → skill.json 编译
def _compile_skill_json(root: Path, data_dir: Path) -> None:
    import yaml as pyyaml
    meta = pyyaml.safe_load((root / "skills_metadata.yaml").read_text(encoding='utf-8'))
    # 生成 skill.json 结构（保持现有 consumer 兼容）
    # ...
    (data_dir / "skill.json").write_text(json.dumps(...), encoding='utf-8')

# 新增：AGENTS.md 生成
def _generate_agents_md(root: Path) -> None:
    """从 skills_metadata.yaml 生成 AGENTS.md 到仓库根。"""
    # ...
    (root / "AGENTS.md").write_text(..., encoding='utf-8')

class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        # ... 现有逻辑（zh commands / knowledge / python_tools / dirs / system_prompt / parts_library）

        # ★ 新增：en commands
        cmd_src_en = root / COMMAND_SOURCE_EN
        cmd_en = data_dir / "commands" / "en"
        cmd_en.mkdir(parents=True, exist_ok=True)
        if cmd_src_en.is_dir():
            for md in cmd_src_en.glob("*.md"):
                shutil.copy2(md, cmd_en / md.name)

        # ★ 新增：en knowledge
        for src_name, dst_rel in EN_KNOWLEDGE_FILES.items():
            src = root / src_name
            if src.exists():
                shutil.copy2(src, data_dir / dst_rel)

        # ★ 新增：skill.json 编译 + AGENTS.md 生成
        _compile_skill_json(root, data_dir)
        _generate_agents_md(root)
```

`scripts/dev_sync.py` 镜像上述改动（保持 AST parse 常量对齐机制）。

**术语白名单守护**（I4）：

```python
# scripts/dev_sync.py 新增函数
CODE_IDENTIFIERS = [
    "PartCategory", "GATE-3.5", "sw_preflight", "parts_library.yaml",
    "CAD_SPEC.md", "DESIGN_REVIEW.md", "cad_pipeline.py",
    # ... (从 skills_metadata.yaml 可配置)
]

def _check_code_identifier_consistency(zh: str, en: str) -> list[str]:
    """zh.md 和 en.md 里代码标识符出现次数必须相等；否则返回不一致项。"""
    errors = []
    for ident in CODE_IDENTIFIERS:
        if zh.count(ident) != en.count(ident):
            errors.append(f"'{ident}' zh={zh.count(ident)} en={en.count(ident)}")
    return errors
```

dev_sync.py 跑完 sync 后对每对 `.claude/commands/<id>.md` + `.claude/commands-en/<id>.md` 跑 `_check_code_identifier_consistency`；不一致 exit 1 + 提示 maintainer。

### 3.5 AGENTS.md 生成

模板（≈ 80 行，从 `skills_metadata.yaml` + 每个 skill 的 zh.md 头部摘要抽）：

```markdown
<!-- AUTO-GENERATED by scripts/dev_sync.py — DO NOT EDIT -->
<!-- Source: skills_metadata.yaml + .claude/commands/*.md -->

# AGENTS.md — cad-spec-gen 代理指南

> 请勿手改；变更在 `skills_metadata.yaml` 或 `.claude/commands/*.md` 后跑 `python scripts/dev_sync.py`。
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

完整用法：见 `.claude/commands/{{id}}.md`。

## 约定

- 所有输出中文（代码标识符除外）
- 测试：`.venv/Scripts/python.exe -m pytest`
- commit：`<type>(<scope>): <中文描述>`

## 开发者

改 skill 正文走 `.claude/commands/{id}.md`（中文）或 `.claude/commands-en/{id}.md`（英文）；
改 metadata 走 `skills_metadata.yaml`；
跑 `python scripts/dev_sync.py` 同步所有产物；pre-commit 自动守护。

---
_v{{version}}_
```

**`{{rev_label}}` fallback 策略**（跟 v2 一致）：git → `GITHUB_SHA` → `"unknown"`；dirty 时加后缀。

**AGENTS.md 默认语言**：zh（跟 `.claude/commands/` 对齐）。`build --lang en` 暂不实现（方向 B 不做语言切换控制，用户需要英文 AGENTS.md 自己切 zh/en section）。

### 3.6 `cad-skill-setup` 衔接（零改动）

现有 `skill_register.py` 消费 `data/commands/{lang}/*.md` + `data/knowledge/skill_*_{lang}.md`——改造后：

- `data/commands/en/*.md` 将由 dev_sync/hatch 自动生成（之前是手维护，现在是 SoT 镜像）
- `data/knowledge/skill_cad_help_en.md` + `skill_mech_design_en.md` 将由 dev_sync/hatch 自动生成（之前缺失，现在补齐）

**用户体验零变化**：`cad-skill-setup --lang en` 现在能装到完整的英文 skill + knowledge（以前 knowledge 会 fallback 到 zh 或报错）。

### 3.7 `src/cad_spec_gen/data/` 是否入 git（v3 的 B2 答案）

v3 继承 v2 B2 决策 A：**全部入 git + pre-commit 守护**。理由同 v2：editable install 不跑 build hook，gitignore 会炸 dev 体验。

**已有** `dev_sync.py` + `.pre-commit-config.yaml` 完美支持此决策（现有机制本来就是这么做的——dev_sync 有 diff 就 exit 1 强制 re-commit）。零改动需求。

### 3.8 `.gitattributes`（B3）

新增：
```
*.md text eol=lf
```

防 Windows CRLF 让 dev_sync 误报漂移。

### 3.9 CI 二道防线（I6）

dev_sync.py 现有只在 pre-commit 跑（本地）。新增 CI job：

```yaml
# .github/workflows/skills-sync.yml（新建或合并到现有 workflow）
jobs:
  check-sync:
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.10'
      - run: python scripts/dev_sync.py || (echo "::error::dev_sync detected drift"; exit 1)
```

CI 防止 `git commit --no-verify` 或 fork PR 绕过 pre-commit。

## 4. 迁移计划（1 个 PR）

v3 方向 B 工作量小，**1 个 PR 就够**（不分 3 个）。

1. 新建 `.claude/commands-en/*.md` × 5（从现有 `data/commands/en/*.md` 拷贝；**同步修 Task 35 漂移**：给 `.claude/commands-en/cad-spec.md` + `cad-codegen.md` 加"SW 装即用集成" 段英文翻译，代码标识符反引号锁）
2. 新建 `skill_cad_help_en.md` + `skill_mech_design_en.md`（根目录，翻译自现有 zh 版）
3. 新建 `skills_metadata.yaml`（从现有 `data/skill.json` 抽 + 裁剪 description 到 ≤ 200 字）
4. 新建 `.gitattributes`（`*.md text eol=lf`）
5. 改 `hatch_build.py`：加 en commands + en knowledge + skill.json 编译 + AGENTS.md 生成（约 +50 行）
6. 改 `scripts/dev_sync.py`：镜像上述改动 + 代码标识符白名单守护（约 +60 行）
7. 跑 `python scripts/dev_sync.py` 生成 `data/commands/en/*.md`（现有手写 en 版被覆盖为 SoT 镜像）+ `data/knowledge/*_en.md` + `data/skill.json`（从 yaml 编译）+ `AGENTS.md`
8. 验证 `pip install -e . --force-reinstall` + `cad-skill-setup --lang en --target /tmp/test` 能装出完整英文 5 skill + 2 knowledge
9. 加 `.github/workflows/skills-sync.yml`（CI 二道防线）
10. `README.md` 加"多语言团队"说明：每人本地 `cad-skill-setup --lang xx` 不 commit

### 回滚
PR 合入后若出问题 → `git revert` 回到 PR#9 tip。

## 5. 测试策略

### 5.1 TDD 分层

| Layer | 目标 | 文件 |
|---|---|---|
| L1 单元 | dev_sync.py 新增函数（en sync / AGENTS.md 生成 / skill.json 编译 / 术语白名单） | `tests/test_dev_sync_en.py` |
| L2 确定性 | AGENTS.md 无 timestamp / 连跑字节稳定 | `tests/test_agents_md_deterministic.py` |
| L3 回归 | hatch_build.py 产出的 zh 副本字节对等（现状保留） + en 新产物齐全 | `tests/test_hatch_build_parity.py` |
| L4 pre-commit | 改 zh.md 不改 en.md 被抓（术语漂移）/ 改 en.md 不跑 sync 被抓 | `tests/test_pre_commit_drift.py` |
| L5 hatch build | `python -m build` 触发 hatch_build 完整路径（Linux + Windows） | `tests/test_hatch_build_wheel.py` |
| L6 golden snapshot | `tests/golden/AGENTS.md` 跟 sync 输出字节相等 | `tests/test_agents_md_golden.py` |
| L7 安装回归 | `cad-skill-setup --lang en --target tmp` 产出 5 md + 2 knowledge | `tests/test_skill_setup_en_install.py` |

### 5.2 CI matrix

```yaml
strategy:
  matrix:
    os: [ubuntu-latest, windows-latest]
    python-version: ['3.10', '3.12']
env:
  PYTHONIOENCODING: utf-8
```

### 5.3 不测
- `.md` body 内容（P 方案不改内容）
- Claude Code 真实 slash 触发
- 跨 LLM 对 AGENTS.md 的实际消费

## 6. 风险与缓解

| 风险 | 触发 | 缓解 |
|---|---|---|
| 现有 `data/commands/en/*.md` 被 sync 覆盖 | PR1 第 7 步 | Task 1 先从 `data/commands/en/` 拷到 `.claude/commands-en/` 作 SoT；然后允许覆盖（产物 = SoT 镜像） |
| 手维护的 en 版跟 zh 已有深度漂移（不仅 Task 35） | 未知长度 | L3 测试显示 diff；维护者 review 决定保留哪版；实际 PR 时先 diff 审一遍 |
| `skill.json` 现有消费方（现在包含 500 字 description）依赖长文本 | LLM 消费 description 但 spec 只给 200 字摘要 | 检查现有 skill.json 实际消费方（大概率只是 pip 元数据，不是 LLM 上下文）；若真依赖长文本，保留长字段在 skill.yaml 里以 `description_long` 命名 |
| `.claude/commands-en/` 新路径 `cad-skill-setup` 识别 | `skill_register.py:51 COMMAND_FILES` 只认文件名 | 不需要改 register；因为它读的是 `data/commands/{lang}/`，SoT 位置它不关心 |
| CI Windows runner 上 dev_sync.py 行为漂移 | encoding / CRLF | `.gitattributes` + `PYTHONIOENCODING=utf-8` + L5 测试覆盖 |
| 术语白名单维护成本 | 代码标识符随项目演化 | `skills_metadata.yaml` 里加 `code_identifiers:` 段，维护者扩展 |
| 5 个 skill 的英文 body 与 zh 长期漂移 | 业务扩展 | 术语白名单只防代码标识符；业务语义漂移靠 human review；spec 承认这点 |

## 7. 开放问题 — 已清

| # | 问题 | 决议 |
|---|---|---|
| O1 | dev_sync.py 扩展规模 | ~+60 行（远小于 v2 的 500 行 sync_skills.py）|
| O2 | AGENTS.md 是否分 zh/en | **v3 不做双语切换**；默认 zh；用户要英文自己从 en SoT 生成本地版本 |
| O3 | knowledge_file 字段语义 | `skills_metadata.yaml.skills[].knowledge_file` = 文件名前缀（不含 _zh/_en.md）；dev_sync 生成 `data/knowledge/<prefix>_{zh,en}.md` |
| O4 | skill.json 从手维护变生成后，现有消费方是否受影响 | 检查后决定保留/删除/缩 description 字段 |

## 8. 附录：用户关键决策

| 问题 | 选择 |
|---|---|
| 跨 LLM 目标 | Claude + Codex CLI（AGENTS.md）；其他不保证 |
| 语言选择时机 | 安装时（`cad-skill-setup --lang`，已有） |
| SoT 布局（v3 方向 B） | `.claude/commands/` zh + `.claude/commands-en/` en；根目录 knowledge 双版；`skills_metadata.yaml` 单文件 metadata |
| 构建产物入 git | 全部入 git + pre-commit 守护（复用现有机制） |
| 首要用户 | maintainer + 会 terminal 的 pip 用户 |
| pip 交付 | 复用现有 `cad-skill-setup` |
| 内容重构深度 | P — 最小侵入 |
| 推翻 v2 改走方向 B | 保留 `hatch_build.py` + `scripts/dev_sync.py`（~11 KB 投资）|

## 9. 附录：审查历史

- **v1**（@ `ab84034`，333 行）：brainstorming 初稿
- **3 角色审查**（Skill 程序员 + SW 操作员 + 外行用户）并行返 ~30 项
- **v2**（@ `7783479`，497 行）：纳入 17 项 findings；设计 `skills/<id>/` 新 SoT + `build/sync_skills.py`（500 LOC）
- **深度现状核查**：发现 `hatch_build.py` + `scripts/dev_sync.py` + `.pre-commit-config.yaml` 已存在并提供完整 SoT + 同步链；v2 会推翻高价值基础设施
- **v3（本版，方向 B）**：推翻 v2；改走保守路线——**保留 `.claude/commands/*.md` zh SoT、新增 `.claude/commands-en/*.md` en SoT、扩展现有 dev_sync/hatch 而不重写**。工作量 v2 的 1/5。

---

_下一步：用户 approve v3 后，调 `superpowers:writing-plans` skill 产出实施 plan。_
