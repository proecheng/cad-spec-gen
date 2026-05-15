# 设计：v2.37.6 §11-N5 + §12 f2 cleanup

- **日期**：2026-05-15
- **基线**：main@`2ab0003`（GISBOT e2e merge 后；working tree clean）
- **分支**：`feat/v2-37-6-followup-cleanup`（待建）
- **目标版本**：v2.37.6（patch release / 纯 git tag + GitHub Release / 不 bump 版本文件）
- **规模**：小 单 PR；总 diff ≈ 30 行 docs + 5 行 production + 15 行测试 + ~50 行 retro = **~100 行**
- **状态**：brainstorming 完成（含 fact-check F1+F2 + layer 6 E1 揭示 production scope 漂移 + E2+E10+E3+E5 inline 修）；待用户复审 → writing-plans

---

## 1. 背景与目标

闭合 v2.37.x §11 + §12 follow-up 2 项 user-facing docs cleanup + 1 项重新评估说明：

- **§11-N5**：`docs/cad-jury-config.md` §4 估价表加 `gpt-image-*` 前缀 entry（**$0.010/call**），来源 = GISBOT e2e profile 显式 `cost_per_call_usd=0.010` 实测（jury cost 公式 line 623 `actual_cost += profile.cost_per_call_usd`；jury report `actual_cost_usd=$0.07 / n_calls=7 → $0.010/call`）。这是单 vendor profile 实测值，非 vendor 公开价；§4.1 既有免责段说明 ±50% 偏差。

- **§12 f2**：`CLAUDE.md` §"项目术语 glossary"（v2.37.5 加）之后追加新小节"## memory 引用约定"，明示 spec/plan/retro 引 memory 时必含 ≤20 字 inline 摘要防失锚；约束**仅未来文档生效**，既有不强制 retro-fit。

- **§11-N4 重新评估说明**（retro 沉淀，不作 code 改）：jury report `ordinary_user_message` 字段实测 UTF-8 真值 `"(详见 stderr 中文提示)"`，**非 mojibake**；之前 GISBOT retro 报"mojibake"是 implementer Windows 控制台读 utf-8 显示乱码（client 端编码问题），不是 jury production bug。Lesson 沉淀进 retro。

## 2. 范围

### 2.1 In-scope

| 文件 | 改动 | 行数 |
|---|---|---|
| **`tools/jury/config.py:45-54`** | `BUILTIN_MODEL_COST_USD` list 加 `("gpt-image", 0.010)` tuple（前缀匹配 first-match）| **+1 行 production** |
| **`tests/jury/test_config.py`**（或 `test_llm_client.py`/邻接位置）| 1 个 TDD 回归测试：`lookup_builtin_cost("gpt-image-2-pro") == 0.010` | **+5-15 行测试** |
| `docs/cad-jury-config.md` §4 表 | 加 1 行 entry `gpt-image-2-pro`, `gpt-image-*` / **0.010** + 来源注 | +3 行 |
| `CLAUDE.md` §项目术语 glossary 后 | 加新小节"## memory 引用约定"（5-8 行约定 + 1 示例 + 新旧格式兼容声明 + ≤20 字 char 单位明示）| +10-12 行 |
| `docs/superpowers/reports/2026-05-15-v2-37-6-followup-cleanup-retro.md`（新写）| retro（含 §11-N4 重新评估说明 + layer 6 E1 production scope 揭示 lesson + 2 项 lesson）| ~60 行 |

**总 cad-spec-gen 仓 diff** ≈ **~100 行**（5 prod + 15 测试 + 30 docs + 60 retro）。

**Layer 6 E1 关键发现**（grep `tools/jury/config.py:45-186` 验证）：
- `BUILTIN_MODEL_COST_USD: list[tuple[str, float]]` 是 production code 真实查表源
- `cad-jury-config.md §4 表`是**人类可读 mirror**，单改 doc 不影响 jury 行为
- jury 前缀匹配规则 = `list` 按行序 first-match（`config.py:185-189 lookup_builtin_cost`）
- **必须同步改 production code 才能让新 entry 生效**

### 2.2 Out-of-scope

- 改 jury / production code（§11-N4 重新评估为非 bug）
- 改 cad-jury-config.md §1-§3 + §5-§13 + 附录 A/B 字面
- 改 CLAUDE.md §1-§4 + 技术规范 + 中文规范 + 提交规范 + §项目术语 glossary（v2.37.5）字面
- 改既有 spec/plan/retro 应用 memory 引用约定（约束仅未来生效）
- §12 f1 (max_tokens sunset) / §12 f4 (N≥50 批量成本) / §11-N1 (rebrand 工具) / §11-N2 (jury --override-subsystem) / §11-N3 (per-view 进度) —— 留 v2.37.7+ 后续 batch

## 3. 设计决策

### 3.1 D1 — `gpt-image` 前缀 entry 同步加进 production list + §4 表 mirror

**抉择**：**同时**改两处保持一致：
- **production**：`tools/jury/config.py:45-54` `BUILTIN_MODEL_COST_USD` list 在 `("gemini-2.5-flash", 0.005)` 之前 / `("gpt-4o", 0.020)` 之后插入 `("gpt-image", 0.010)`
- **doc mirror**：`cad-jury-config.md §4 表`加同步行 `\`gpt-image-2-pro\`, \`gpt-image-*\` / **0.010** / 来源注`

**理由（F1 fact-check 修 + Layer 6 E1 production scope 揭示）**：
- jury cost 公式（`tools/photo3d_jury.py:623` `actual_cost += profile.cost_per_call_usd`）依赖 profile 显式 `cost_per_call_usd` 字段
- **Profile 优先级（E2+E10 fix）**：jury 实际查表逻辑 = 若 profile 显式 `cost_per_call_usd` ≠ null 直接用；否则走 `lookup_builtin_cost(model)` 查 `BUILTIN_MODEL_COST_USD` list 按行序 first-match。本 PR 加 entry 仅影响"未显式填 cost 的新用户"——GISBOT 既有 profile 显式填了 $0.010 → 零影响
- **来源严格（F1 修）**：GISBOT e2e profile 显式值 + 单 vendor (micuapi.ai) 实测一次 → $0.010；非 vendor 公开价；§4.1 ±50% 偏差免责保留
- **前缀匹配规则（E1 fix）**：`tools/jury/config.py:185-189` `lookup_builtin_cost` 按 list 行序 first-match。`gpt-image` 不与 `gpt-4o` / `gpt-4-turbo` 字面冲突（model.startswith 严格前缀）；插入位置选 `gpt-4o` 之后 / `gemini-2.5-flash` 之前保 OpenAI 系连续

### 3.2 D2 — §11-N4 mojibake 重新评估为非 bug

**抉择**：retro 第 1 段加澄清"§11-N4 重新评估"，**不改 production code**。

**事实依据**：cat 实测 GISBOT jury report `ordinary_user_message` 字段 = `"(详见 stderr 中文提示)"`（UTF-8 中文真值，jury.py:693 写死兜底 message）。Implementer 之前看 `"(��� stderr ������ʾ)"` 是 Windows console 默认 cp936 读 utf-8 JSON 显示乱码（client 端问题）。

**Lesson 沉淀**：报 production bug 前先 `cat -A` 或 `python -c "import json; print(repr(json.load(open(...))['field']))"` 实测字节，不只看控制台显示。

### 3.3 D3 — CLAUDE.md "memory 引用约定" 紧邻 glossary

**抉择**：在 CLAUDE.md 既有"## 项目术语 glossary"（v2.37.5 加，line 87-113）之后追加新小节"## memory 引用约定"。

**约定核心**（5-8 行）：
- spec/plan/retro 引 memory 必含 ≤20 **字符**（不是字节；E4 修：中文 1 char ≠ 3 utf-8 bytes 歧义已澄清）inline 摘要
- 格式：`见 memory \`xxx.md\`（摘要：≤20 字含义）`
- **约束范围（F2 fact-check 修）**：仅未来 spec/plan/retro 文档生效；既有文档不强制 retro-fit；鼓励渐进改进
- **与既有格式兼容（E3+E5 fix）**：v2.37.5 glossary 既有写法 `（见 memory \`xxx.md\`）` 不删；新约定 = 新写文档时含摘要；新旧并存合法
- 防"1 年后 memory 改名/归档 → 引用失锚"问题（layer 5 R2 L3 教训）

**理由**：
- 紧邻 glossary 让"glossary + memory 约定 = 同节簇"概念清晰
- CLAUDE.md always-loaded，spec writer 主 agent 必看
- 不破坏既有 glossary 的"见 memory `xxx.md`"格式（已部分含 inline 含义）

---

## 4. 验收

- **AC-1** `tools/jury/config.py:BUILTIN_MODEL_COST_USD` list 加 `("gpt-image", 0.010)` tuple；`lookup_builtin_cost("gpt-image-2-pro")` 返 `0.010`（新测试 GREEN）
- **AC-2** `docs/cad-jury-config.md` §4 表加 `gpt-image-*` entry → 0.010 + 来源注（与 production list 同步）
- **AC-3** `CLAUDE.md` 加新小节"## memory 引用约定"含约定 + 1 示例 + 约束范围 + 新旧格式兼容声明 + ≤20 字符（非字节）明示
- **AC-4** AC grep strict（v2.37.4 layer 6 E4 ERE 教训复用）：
  - `grep -c "gpt-image" tools/jury/config.py` ≥ 1（production list 加 entry）
  - `grep -c "gpt-image" docs/cad-jury-config.md` ≥ 1（doc mirror 同步）
  - `grep -c "## memory 引用约定" CLAUDE.md` == 1
  - `grep -cE "≤20 字符|inline 摘要" CLAUDE.md` ≥ 1
  - `grep -c "仅未来" CLAUDE.md` ≥ 1
- **AC-5** retro 文档新写 ≥ 50 行；含 §11-N5 closed + §12 f2 closed + §11-N4 重新评估 + layer 6 E1 production scope 揭示 lesson
- **AC-6** 全套件 PASS：3193 baseline + 1 新测试 = **3194 PASS** / 0 regression（layer 6 E1 修后新增 1 测试）
- **AC-7** CI 8/8 SUCCESS
- **AC-8** 发 v2.37.6 patch tag + GitHub Release（**有 production code 改，必发**）

---

## 5. 风险与边界

| 风险 | 评估 | 缓解 |
|---|---|---|
| §4 表新 entry 与既有前缀冲突 | 极低（`gpt-image-*` 与 `gpt-4-*`/`gpt-4o-*` 独立）| Task 0 grep 验证既有前缀 |
| `$0.010/call` 是单数据点（GISBOT 1 次实测）| 中（vendor 实际计费按 token + image 多维）| §4.1 ±50% 偏差免责声明保留 + 新 entry 注引 |
| CLAUDE.md "memory 引用约定" 与既有 glossary disclaimer 冲突 | 低 | 两节相邻职责清晰，约定补充 glossary 未覆盖的"约束范围" |
| 元测试 `tests/test_agents_md.py` 触发 | 低（CLAUDE.md 不影响 AGENTS.md regen，v2.37.5 实证）| AC-5 + plan task 0 baseline |
| §11-N4 drop 不修，未来读者 false-report | 极低 | retro 明示"client 环境问题非 production bug"+ memory 沉淀 |

---

## 6. 不变量

1. **production code 改仅限 1 行**：`tools/jury/config.py:45-54` `BUILTIN_MODEL_COST_USD` list 插入 1 个 tuple；`lookup_builtin_cost` 函数本体（line 184-189）不动；其它 production 字面零改（layer 6 E1 揭示后 spec 加 production scope，#1 改）
2. **测试覆盖**：1 新 TDD 回归测试覆盖 `lookup_builtin_cost("gpt-image-2-pro") == 0.010`；既有测试不动
3. `cad-jury-config.md` §1-§3 + §5-§13 + 附录 A/B 字面零改；本 PR 仅 §4 表内追加 1 行
4. `CLAUDE.md` §1-§4 + 技术规范 + 中文规范 + 提交规范 + §项目术语 glossary（v2.37.5）**字面零改**；本 PR 仅在 glossary 之后追加新小节
5. v2.37.5 之前所有 spec 不变量保留
6. AGENTS.md 自动 regen 不动（CLAUDE.md → AGENTS.md 不衍生；v2.37.5 实证）
7. 0 schema / 0 env-config / 0 CI workflow 改

---

## 7. 流程

```
brainstorming（本 spec）→ writing-plans → 3 task plan → execute
  ↓
Task 0 scout + baseline + 实测 cad-jury-config §4 既有 entries + CLAUDE.md 末位置
Task 1 cad-jury-config.md §4 加 entry + CLAUDE.md 加 memory 引用约定 + AC-3 grep 验证
Task 2 retro 写（§11-N5 closed + §12 f2 closed + §11-N4 重新评估说明）+ commit docs
Task 3 PR + 等 CI + 用户授权 merge + tag v2.37.6 + Release + memory
```

提交 3 commit（layer 6 E1 揭示 production scope 后拆分便于 review）：
1. `feat(jury): BUILTIN_MODEL_COST_USD list 加 gpt-image entry + 回归测试（§11-N5 production）`
2. `docs(jury-config,claude-md): §4 表 mirror 同步 + memory 引用约定（§11-N5 doc + §12 f2）`
3. `docs(v2-37-6): retro 沉淀 + §11-N4 重新评估 + layer 6 E1 production scope 揭示 lesson`

### 7.1 Rollback 流程

纯 docs PR rollback 极低风险。若用户报"§4 entry $0.010 与实际 vendor 大幅偏差"或"memory 引用约定措辞误导"：
- `git revert <v2.37.6 merge_sha>` 回退两节
- 发 v2.37.7 修措辞
- GitHub Release UI 标 v2.37.6 "Pre-release"（v2.37.2 D7 模式）

---

## 8. Plan 调查步（plan 第 0 task 跑）

1. `cd D:/Work/cad-spec-gen && git status --short && git log --oneline -3` — baseline main@`2ab0003` clean
2. `python scripts/dev_sync.py --check` rc=0 — 镜像干净
3. `pytest -q tests/jury/ tests/jury_loop/ tests/test_agents_md.py tests/test_no_tracked_mirror.py 2>&1 | tail -3` — baseline PASS 数实测
4. `grep -nE "^\| \`gpt-|^\| \`gemini-|^\| \`claude-" docs/cad-jury-config.md` — 实测 §4 表既有 entries 位置 + 格式（D1 新 entry 风格沿用）
5. `grep -nE "^## " CLAUDE.md` — 实测 CLAUDE.md 既有 ## 节列表，确认末节是"## 项目术语 glossary"（v2.37.5 加），D3 追加位置
6. `cat D:/Work/cad-tests/GISBOT/cad/end_effector/.cad-spec-gen/runs/20260513T115709Z/PHOTO3D_JURY_REPORT.json | python -c "import json,sys; d=json.load(sys.stdin); print('actual_cost:', d.get('actual_cost_usd'), '/ n_calls:', d.get('n_calls'))"` — 实测 GISBOT cost 数字校验 spec D1 引用准确

---

## 9. Plan 必 cover 项

- 每 commit 含 docs only（无 dev_sync mirror sync 需求；docs 不进镜像）
- PR push 前 `git fetch origin main` 验证无并行 docs 改动
- baseline `dev_sync --check` rc=0 验证（v2.37.3 R5 D2 教训）
- AC-3 grep `-cE` ERE OR pattern（v2.37.4 layer 6 E4 教训）
- spec D1 来源 "GISBOT e2e profile 显式值 + 单实测"必明示，不假称"vendor 公开价"（F1 fact-check 教训）
- §11-N4 retro 说明明示 "client 环境问题"+ 字节级 verify 方法（GISBOT e2e 实施期发现教训）

---

## 10. 不写代码 / 不进 plan 的事

- 不改 cad-jury-config §1-§3 / §5-§13 字面
- 不改 CLAUDE.md §1-§4 字面 / §项目术语 glossary 字面
- 不强制 retro-fit 既有 spec/plan/retro 应用 memory 引用约定（仅未来生效）
- 不动 jury production code（§11-N4 评估为非 bug）

---

## 11. v2.37.x §11 + §12 follow-up 表（本 PR 闭合后）

| 项 | 严重度 | 内容 | 状态 |
|---|---|---|---|
| §12 F1 | LOW | mock helper 抽取 | closed v2.37.3 ✓ |
| §12 F2 | LOW | line 105 注释扩 rationale | closed v2.37.3 ✓ |
| §12 f3 | LOW | CLAUDE.md spec mini-glossary | closed v2.37.5 ✓ |
| §12 f5 | LOW | cad-jury-config §12 输出字段语义 | closed v2.37.4 ✓ |
| §12 f6 | LOW | cad-jury-config §13 版本承诺 | closed v2.37.4 ✓ |
| **§12 f2** | **LOW** | **memory inline 摘要约定** | **closed v2.37.6**（本 PR）|
| §12 f1 | LOW | max_tokens sunset 条件 | 未闭合 |
| §12 f4 | LOW | N≥50 批量场景成本评估 | 未闭合 |
| §11-N1 | LOW | rebrand_test_archive.py | 未闭合（batch 3）|
| §11-N2 | LOW | photo3d-jury --override-subsystem | 未闭合（batch 2 / v2.37.7）|
| §11-N3 | LOW | photo3d-jury per-view 进度 | 未闭合（batch 2 / v2.37.7）|
| §11-N4 | — | stderr mojibake | **重新评估为非 bug，retro 说明**（本 PR）|
| **§11-N5** | **LOW** | **估价表 gpt-image-***| **closed v2.37.6**（本 PR）|

---

## 12. 本 PR 自身 follow-up

| # | 严重度 | 内容 | 触发条件 |
|---|---|---|---|
| h1 | LOW | `$0.010/call` 实测更多 micuapi.ai sample 后校准 | 实测 ≥ 3 个不同 GISBOT-like 项目 cost 偏差 |
| h2 | LOW | memory 引用约定 retro-fit 老 spec/plan/retro 加 inline 摘要 | 选定时机批量做 cleanup PR |
