# 设计：SP1 §11 follow-up — B1 skill 描述提及闭环 + B2 L4 smoke

- **日期**：2026-05-12
- **基线**：main@a389283（ruff/mypy cleanup 本地合并后；**注意：origin/main 仍 c9ddab0，本地领先 10 commits 未 push**——本 PR 从本地 main 起分支）
- **分支**：`feat/sp1-followup-skill-desc-l4-smoke`
- **规模**：小-中 单 PR（B1 ≈ 1 个描述字符串改动；B2 ≈ 新测试文件 + marker + conftest skip hook + 合成 fixture helper，全 CI-skip）
- **状态**：brainstorming 完成；待用户复审 → writing-plans

---

## 1. 背景与目标

SP1 jury→prompt 闭环（CP-0~CP-8）已完工（v2.32~v2.34.1）。CP-8 当初把两件事登记 §11 follow-up：
- **B1**：`/cad-enhance` skill 的用户可见描述里**没提**自带的「AI 评分 → 低分自动重试一次 → 选高分张交付」闭环——用户 / 读 skill metadata 的 LLM 不知道这功能存在。
- **B2**：Task 8.2 L4 smoke（`tests/jury_loop/test_l4_smoke.py`）当初以「需真 API key + 验证过的低分 fixture + CI-skip + 自动化价值低」延期。

本 PR 把这两个收尾掉。**核心约束：零行为变更**（B1 只改 skill 描述文本；B2 全是新测试 + marker + conftest skip hook + 合成 fixture，CI 默认 skip，不动任何生产代码逻辑）。

**北极星 5 gate**：傻瓜式 ✓（B1 让用户/LLM 知道自动重试闭环存在）/ 稳定可靠 ✓（B2 文档化闭环预期 + 可手动跑的质量回归脚手架）/ 零配置 ✓（不动配置）/ 结果准确 ✓（不动判定逻辑）/ SW 装即用 ✓（不碰 SW）；Windows-only ✓（conftest hook 平台中性；无跨平台分支）。

## 2. 范围

### 2.1 In-scope
- **B1**：`src/cad_spec_gen/data/skill.json` 的 "AI Enhancement (4 backends)" skill `description` 末尾追加一句闭环说明；`python scripts/dev_sync.py` 同步（AGENTS.md 自动生成）。
- **B2**：`pyproject.toml` 注册 `requires_jury_loop_e2e` marker；`tests/conftest.py` 加 skip hook；新建 `tests/jury_loop/test_l4_smoke.py`（3 case）+ 合成 fixture helper。

### 2.2 Out-of-scope（明确划界）
- **B3（N-16 命名约定统一）** / **B4（N-15 fast-path 跳过扩展为「跳整个视角 baseline enhance」）**——留后续独立 cycle。
- **DRIFT-MINOR-8**（L4 fixture 用 git LFS 提交验证过的真低分 render PNG + 锁基线 score）——仍延期；本 PR 用合成 PNG。
- **N-12 deterministic seed**（L4-1 跑 10 次取均值升级为确定性）——延期；本 PR 用小 N（默认 3）。
- L4 smoke 进 CI——**永远不进**（要真 API key + 真花钱）。
- 改 "CAD Pipeline Assistant"（1700+ 字符的伞描述）/ "Parametric Mechanical Design" 的描述——不动，只动 "AI Enhancement (4 backends)" 一条。

## 3. B1 — `/cad-enhance` skill 描述提及闭环

### 3.1 改动
`src/cad_spec_gen/data/skill.json` → `skills[3]`（`name == "AI Enhancement (4 backends)"`）的 `description` **末尾**追加（英文，与该文件其余描述一致）：
> `Auto-retry loop: when ~/.claude/cad_jury_config.json exists, each view's enhance output is scored by a vision-LLM jury; if below threshold the prompt is rebuilt from the jury feedback and the enhance retried once, keeping the higher-scoring image; disabled silently without the jury config; aggregated into ENHANCEMENT_REPORT.loop_summary.`

（追加到末尾即可——不必塞进前 100 字符，原因见 §3.2。措辞 plan 阶段可微调，但要：英文 / 单行 / 不引入新换行 / 准确——「自动重试一次」「低于阈值才触发」「没配 jury config 静默禁用」「聚合到 loop_summary」四要素必含。）

### 3.2 AGENTS.md 同步（多半无变化）
`dev_sync.py` 的 `_render_skill_row` 把 description 裁到 100 字符（`if len(desc) > 100: desc = desc[:100] + "..."`），AGENTS.md 的 skill 表只显示前 100 字符的预览（当前 "AI Enhancement" 那行已经在 "~$0.0..." 处截断）。所以追加到描述末尾 → AGENTS.md 表格单元格**不变** → `dev_sync.py` 重生 AGENTS.md 无 diff。这是预期的：

- 描述改动的真正受益方是 **Claude 的 skill metadata 加载** 和 **`cad-skill-setup --agent codex` 从 skill.json 生成的 Codex `SKILL.md`**——它们用完整 description，不是 100 字预览。
- §11 意图「跑 `dev_sync.py` 同步」仍满足：跑一遍 + `dev_sync.py --check` 确认 AGENTS.md 在磁盘上 == 重生结果（无变化时这自然通过）。
- B1 的 commit = **skill.json**（若 dev_sync 真重生了 AGENTS.md 变化也一起，但 100 字截断下不会有）。

### 3.3 测试影响（已核实）
- `tests/test_agents_md.py`：只断言 5 个 skill trigger（`/cad-help` 等）+ "代理指南"/"6 阶段"/"cad-skill-setup --agent codex"/"AUTO-GENERATED" + 确定性 + 无 volatile 字段——**不**断言 description 文本 → 改描述不破它。
- `tests/test_photo3d_packaging_sync.py`：断言 photo3d 契约**工具文件**有打包镜像——不涉 skill.json description → 不受影响。
- **Plan 调查步**：仍 grep `tests/test_*.py` 有没有别的地方断言 "AI Enhancement" description 的精确字符串（如某 skill metadata 契约测试）→ 是则同步期望值。

## 4. B2 — L4 smoke 测试（Task 8.2）

### 4.1 marker 名：`requires_jury_loop_e2e`（**不是** `requires_fal_key`）
原 plan（cp7-plan L295 / jury-loop-plan Task 8.2）写的 `@pytest.mark.requires_fal_key` 是误名：闭环的 **retry backend** 默认是 `gemini_chat_image`（jury_loop backend，cp7 实施确认），需要的是 jury LLM key + retry backend 的 API key——**不是** FAL_KEY。`fal` 是 `cad_pipeline.cmd_enhance` 的 baseline-enhance backend（`--backend fal`），而 L4 测的是闭环（`orchestrator.run_loop_if_eligible`），闭环吃的是「已 enhance 的 baseline」、自己不做 baseline enhance（前置 `baseline_path.is_file()`），所以闭环路径上没有 fal。**本 PR 纠正这个误名**：marker 叫 `requires_jury_loop_e2e`。

`pyproject.toml` `[tool.pytest.ini_options].markers` 加一行：
```
requires_jury_loop_e2e: jury-loop L4 端到端 smoke；需 jury LLM key + retry backend key（测试自带临时 jury config）；CI / 无 key 时自动 skip
```

### 4.2 conftest skip hook
`tests/conftest.py` 加 `import os`；在既有 `pytest_collection_modifyitems`（`tryfirst=True`）里加一段（照搬 `requires_solidworks` 自动 skip 模式）：`requires_jury_loop_e2e` 的 item 若所需 env var 未设 → `add_marker(pytest.mark.skip(reason="requires_jury_loop_e2e：<env var> 未设"))`。具体 env var 名（jury LLM key / retry backend key）= **plan 调查**（grep `photo3d_jury` / `cad_jury_config` / `gemini_chat_image` backend 看用哪个 env var 名）；conftest hook 检最关键的一个（缺它就 skip），test 内 runtime 再细查另一个、缺则 `pytest.skip(...)`（双保险）。

### 4.3 绕开 autouse `_redirect_home`
conftest 有 autouse fixture 把 `Path.home()` monkeypatch 成 per-test 假 tmp 目录——所以 L4 test **读不到真的 `~/.claude/cad_jury_config.json`**。解法：test 不读真配置，**自带临时 jury config**——在 `tmp_path` 写一个 `cad_jury_config.json`，`api_key` 字段从 env var 取（env var 名 = plan 调查；同 §4.2 的 jury LLM key），然后 `run_loop_if_eligible(jury_profile_path=tmp_path / "cad_jury_config.json", ...)`。这样 test 完全不依赖真实 home。

### 4.4 新文件 `tests/jury_loop/test_l4_smoke.py`
3 个 case，每个 `@pytest.mark.requires_jury_loop_e2e @pytest.mark.slow`。模块顶常量 `_SMOKE_RUNS = 3`（注释「原 plan 是 10；3 已足够 smoke，调高更稳更贵」）。

**驱动路径**（= plan 调查 + 决策）：`orchestrator.run_loop_if_eligible` 是 keyword-only：`view / backend_kind / rc(dict) / baseline_path(Path) / base_params(dict) / budget(LoopBudget) / project_root(Path) / config(JuryLoopConfig) / jury_profile(JuryProfile) / jury_profile_path(Path) -> LoopResult`。其中 `rc`（render config）和 `base_params`（base enhance prompt 参数）是 `cmd_enhance` 上下文里的 dict——手搓最小有效版本要 plan 阶段 grep `cmd_enhance` 里的调用点确认结构。**备选**：驱动整个 `cad_pipeline.cmd_enhance(args)`（它从 render manifest + baseline PNG 自己构造 `rc`/`base_params`，但要先搭最小 active-run 项目——查 photo3d_contract 测试有没有现成 helper）。Plan 选摩擦小的那条。

1. **`test_l4_1_score_improves`**：1-view 临时 `project_root` + 合成「粗糙 render」PNG 作 `baseline_path` + `backend_kind="gemini_chat_image"` + 自带临时 jury config（正常阈值，如 `min_score=75`）→ 跑闭环 `_SMOKE_RUNS` 次 → 断言 `mean(retry_score - baseline_score) > 5`（从 `LoopResult` / loop_summary / sidecar 读分数 —— 字段名 plan 调查）。

2. **`test_l4_2_no_trigger_when_score_above_threshold`**：同上但临时 jury config 的 `min_score` 调到极低（如 1）→ baseline 真实 jury score（≥1 几乎必然）≥ 阈值 → 断言该视角 **`loop_triggered == False`**（无 retry；从 `LoopResult` / sidecar 读 —— 字段名 plan 调查）。跑 1 次即可。

3. **`test_l4_3_v1_anchor_chains`**：2-view 临时 `project_root` + 两张合成 PNG + `backend_kind="gemini_chat_image"` + v1_anchor 模式 → 跑 V1 闭环、再跑 V2 闭环（传 V1 的 enhanced 产物作 anchor）→ 断言 V2 的 enhance 输入锚定在 V1 的 enhanced 产物（**断言机制 = plan 调查**：看 `LoopResult` / loop_summary / sidecar 记不记 anchor 路径；若都不记 → 退到弱断言「v1_anchor 模式下两视角都跑完无错、都出产物」）。

### 4.5 合成 fixture helper
`tests/jury_loop/test_l4_smoke.py`（或 `tests/jury_loop/conftest.py`）里 `_make_rough_render_png(path: Path, size: tuple[int, int] = (512, 512)) -> Path`：用 PIL 画一个平涂背景 + 单个简单几何体（看着像未完成的 Blender 渲染、非照片级），写到 `path` 返回。DRIFT-MINOR-8（git-LFS 验证过的真低分 render）仍延期。
（注意：合成图不保证 jury 一定给低分——`test_l4_1` 若它意外得高分会 fail；但本 case CI-skip、只手动跑，跑的人可换真低分图；这是 DRIFT-MINOR-8 要解的，本 PR 不解。）

## 5. 验证清单
1. `python -m pytest tests/jury_loop/test_l4_smoke.py -q`（无所需 env var）→ 3 case 全 **skipped**（reason 含 "requires_jury_loop_e2e"）。
2. `python -m pytest tests/ -q` → ≥ **3090 PASS / 14 skipped（11 baseline + 3 新 L4）/ 0 regression**（L4 三 case 被 conftest hook 标 skip、不计 pass；conftest 加 `import os` + 新 skip hook 段不影响其它 marker / 测试）。
3. `python -m ruff check tests/jury_loop/test_l4_smoke.py tests/conftest.py tests/jury_loop/conftest.py src/cad_spec_gen/data/skill.json` → `All checks passed!`（skill.json 是 JSON，ruff 不检；列出只为完整性——实际只检 .py）。新 test 文件不进 mypy gate（与既有 jury_loop 测试一致）。
4. `python scripts/dev_sync.py && python scripts/dev_sync.py --check && git diff --exit-code -- AGENTS.md` → 通过（B1 改 skill.json 后 AGENTS.md 多半不变；若变了则 commit 它）。
5. 北极星 5 gate + Windows-only：全过（见 §1）。
6. （手动，可选）若有真 jury LLM key + retry backend key：`<set env vars>; python -m pytest --run-slow tests/jury_loop/test_l4_smoke.py -v` —— 3 case 真跑（要花钱）；不强制，PR 描述里写明手动验证步骤即可。

## 6. 不写更多新测试 / 不进 CI 的理由
B1 是描述文本改动（无逻辑），覆盖靠 `dev_sync.py --check` + 现有 `test_agents_md.py`。B2 的 3 个 case **本身就是测试**——但它们 `requires_jury_loop_e2e` 门控，CI 无 env var → 全 skip；这是有意的（e2e 要真 key + 真花钱，不能进 CI）。它们的价值 = 文档化闭环预期 + 给有 key 的维护者一个可手动跑的质量回归脚手架（CP-8 当初以「自动化价值低」延期；本 PR 把脚手架建起来，DRIFT-MINOR-8 解「真低分 fixture」后这脚手架就能升级成更可靠的回归）。conftest 改动（`import os` + skip hook 段）要被「全套件不回归」覆盖（验证清单 #2）。

## 7. 提交建议
按 B1 / B2 分 commit 便于 review：
1. `chore(skill): /cad-enhance 描述提及 jury 自动重试闭环（§11 B1）` —— skill.json（+ AGENTS.md 若有变化）
2. `test(jury-loop): L4 smoke 三 case + requires_jury_loop_e2e marker + conftest skip hook（§11 B2，CI skip）` —— pyproject.toml + tests/conftest.py + tests/jury_loop/test_l4_smoke.py（+ tests/jury_loop/conftest.py 若 fixture helper 放那）

（也可合一个 commit；plan 定。commit message 描述部分用中文；提交用 `git -c commit.gpgsign=false commit`；分支必须是 `feat/sp1-followup-skill-desc-l4-smoke` 不是 main——subagent 用 `git -C <abs>` + branch 守卫，见 `feedback_subagent_cwd_drift.md`。）

## 8. Plan 调查步汇总（plan 第 0 task 跑）
1. grep `tests/test_*.py` 有没有断言 "AI Enhancement (4 backends)" description 精确字符串（除已确认的 `test_agents_md.py` / `test_photo3d_packaging_sync.py` 外）。
2. grep `photo3d_jury` / `cad_jury_config` / `tools/jury_loop/backends/gemini_chat_image.py` —— jury LLM key 和 retry backend key 各用哪个 env var 名。
3. grep `cmd_enhance` 里 `run_loop_if_eligible` 的调用点 —— `rc` / `base_params` dict 的最小有效结构；以及 `cmd_enhance` 走整流程要的最小 active-run 项目结构（查 photo3d_contract 测试 helper）；决定 L4 test 的驱动路径。
4. grep `LoopResult` dataclass / `loop_summary` / sidecar（`<V>_enhance_meta.json`?）schema —— `baseline_score` / `retry_score` / `loop_triggered` / `v1_anchor` 路径等字段名，定 3 个 case 的断言。
5. `git ls-files -v` 确认 `pyproject.toml` 没有 skip-worktree flag（`feedback_skip_worktree_per_machine_config.md`：有的话加 marker 行要换做法）。
6. 确认 `tests/jury_loop/conftest.py` 现状（fixture helper 放它还是放 test 文件）。
