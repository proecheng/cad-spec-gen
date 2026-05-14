# 设计：v2.37 §11 follow-up cleanup（#1 + #6）— v2.37.2

- **日期**：2026-05-14
- **基线**：main@`c4653d2`（PR #79 docs squash 之后；working tree clean）
- **分支**：`feat/jury-v2-37-followup-cleanup`
- **目标版本**：v2.37.2（patch release，git tag + GitHub Release，不 bump 版本文件——本项目 v2.25+ 惯例）
- **规模**：小 单 PR；总 diff ≈ 50 行（2 行实现 + 测试 + 文档）
- **状态**：brainstorming 完成；待用户复审 → writing-plans

---

## 1. 背景与目标

v2.37（jury matches_spec 维度）+ v2.37.1（第三方代理兼容 hotfix）发布后，§11 follow-up 表登记了 6 项 LOW-severity 事项；其中两条因「v2.37 主功能 / 第三方代理实测路径都不阻断」延期：

- **§11 #1**（v2.37 self-review 暴露）：`tools/jury/verdict.py::_make_needs_review_verdict` 返回 5-key `semantic_checks`（无 `matches_spec`），与 normal path 的 6-key 形态不一致；`aggregate_run_verdict` 已用 `.get("matches_spec", True)` 兜底，所以**非 bug、是脆性设计**——加未来第 7 维度时会忘改这个 helper 且 type checker 不报警。
- **§11 #6**（v2.37.1 micuapi.ai 实测暴露）：`tools/jury/llm_client.py::request_jury_verdict` 把 `max_tokens=512` 硬编码进 chat-completions body；12 features × 几十字 + 5 standard check + reason ≈ 远超 512，实测 9/12 features_status 被截断进 needs_review。

本 PR 把这两条收尾。**核心约束：零行为变更**——`matches_spec=True` 与 `aggregate` 的 `.get` 默认 True 等价；`max_tokens` 只增不减响应空间（temperature=0 决定 LLM 在原 512 token 内的输出不变）。

**北极星 5 gate**：
- 零配置 ✓（不加 env / config 字段，硬编码 1024）
- 稳定可靠 ✓（修脆性 helper；扩响应空间不丢字段）
- 结果准确 ✓（max_tokens 1024 让长 feature 列表完整返回，不被截断进 needs_review）
- 傻瓜式 ✓（用户无感）
- SW 装即用 ✓（不碰 SW 路径）
- Windows-only ✓（无平台分支）

---

## 2. 范围

### 2.1 In-scope

| 文件 | 改动 |
|---|---|
| `tools/jury/llm_client.py:105` | `"max_tokens": 512` → `1024` |
| `tools/jury/verdict.py::_make_needs_review_verdict` | `semantic_checks` 在 5 key 基础上加 `"matches_spec": True` |
| `tools/jury/verdict.py` docstring | 注释 matches_spec=True 是兜底语义（与「空 features_status → True」一致） |
| `tests/jury/test_llm_client.py` 或同位置 | 1 个 TDD 回归测试：mock `urlopen`，断言序列化 request body 里 `max_tokens == 1024` |
| `tests/jury/test_verdict.py` | 2 个 TDD 回归测试：(a) `_make_needs_review_verdict([...])` 返回 6-key dict 含 `matches_spec=True` (b) `aggregate_run_verdict` 把 needs_review 视角混入后 `overall_matches_spec` 行为不变 |
| `docs/superpowers/JURY_MATCHES_SPEC_STATUS.md` §11 表 | 标 #1 + #6 closed |
| `docs/superpowers/reports/2026-05-14-...retro.md` | 提交后写 retro（小规模 PR 仍写，沉淀流程）|

### 2.2 Out-of-scope

- §11 #2 `_derive_matches_spec_status` 加 warn/blocked 中间态——延期（需 retry 历史追溯，无紧迫痛点）
- §11 #3 `tools/render_qa.py` mirror drift cleanup——pre-existing 历史债，独立 PR
- §11 #4 plan-drift 模板纠正（spec review checklist 加「真实第三方代理实测一次」）——已在 `feedback_third_party_proxy_real_test_finds_bugs` memory 里沉淀，下次新 spec 自动触发，不需本 PR 改 doc
- §11 #5 Task 13 cad-tests README——真 e2e 时补
- 加 env override / config 字段控制 `max_tokens`——破坏「零配置」北极星
- 改 `_REQUIRED_BOOL_KEYS`（仍 5 key，matches_spec 仍是 derived field；spec §8 不变量 #1 守住）
- 改 retry 触发逻辑 / `aggregate_run_verdict` 实现

---

## 3. 设计决策

### 3.1 D1 — `max_tokens` 硬编码 512 → 1024（不加配置项）

**抉择**：硬编码改值，不加 env / config。

**理由**：
- 北极星「零配置」拍板；用户 / 傻瓜路径无感
- v2.32.0 (CP-5) 写下 512 时还没 features_status 维度，是历史值
- 1024 对 12 features + 5 check + 短 reason 是合理上限（实测 micuapi.ai 长输出 ~800 token）
- 真有用户跑超长 prompt 再扩 env / config，YAGNI

**风险**：上调 max_tokens 可能略增成本（仅在 LLM 用足新增空间时），单视角 +1¢ 级，可忽略。

### 3.2 D2 — `_make_needs_review_verdict` 加 `matches_spec=True`（不加 False / 不保持 5 key）

**抉择**：6-key dict，`matches_spec=True`。

**理由**：
- 与 normal path「空 features_status / features_status 非 list → matches_spec=True 兜底」（spec §6 验收 #1 向后兼容硬保障）同语义：缺/失数据 = 默认通过
- `aggregate_run_verdict:199` 已用 `.get("matches_spec", True)` 走 True 默认 → 显式 True 与之等价 → 零行为变化
- 选 False 会让 `aggregate.overall_matches_spec` 在 parse 失败视角混入后变 False，可能误触发 prompt_rewriter 的「spec mismatch retry」（实际是 parse 失败不是 vision 错），是 bug 放大
- 保持 5 key + 文档化（C 选项）保留了「下游靠 `.get` 兜」的脆性，未来加第 7 维度还得改两处——A 选项一次根治

**不变量保留**：`_REQUIRED_BOOL_KEYS` 不动（仍 5 key），matches_spec 仍是 derived field，spec §8 不变量 #1 守住。

### 3.3 D3 — 单 PR 合并发 v2.37.2

**抉择**：1 个 PR 同时发布 #1 + #6，发 v2.37.2 patch tag。

**理由**：
- 两条都是 v2.37 收尾 cleanup，scope 一致
- 总 diff ~50 行，review 成本远低于 2 PR
- 项目 v2.30.0、v2.32.1、v2.32.2 都是同等 scope 单 PR 发布，已有惯例

### 3.4 D4 — TDD RED→GREEN

**抉择**：每个改动先写失败测试，再改实现。

**理由**：CLAUDE.md 项目铁律；scope 小到 5 分钟一轮，TDD 几乎零摩擦；防 max_tokens 字段名拼错 / matches_spec key 名拼错这种「人手抖」回归。

---

## 4. 验收标准

- **AC-1** `tools/jury/llm_client.py` `request_jury_verdict` 序列化 body 后，`json.loads(body)["max_tokens"] == 1024`（mock urlopen 拦截 request data；新测试 GREEN）
- **AC-2** `_make_needs_review_verdict(["content_not_json"])` 返回的 `ViewVerdict.semantic_checks` 含 6 key（原 5 + `matches_spec`），`matches_spec is True`；新测试 GREEN
- **AC-3** `aggregate_run_verdict({...含 1 个 needs_review 视角 + 1 个 normal 视角...})` 的 `overall_matches_spec` 与改动前等价（True iff normal 视角的 matches_spec 是 True）；新测试 GREEN
- **AC-4** 全套件 jury 子集 `pytest tests/jury/ tests/jury_loop/ -q` ≥ 当前基线 PASS（plan 第 0 task 实测填入；v2.37.1 后近似 ~700+ PASS）；总套件 ≥ 当前基线 PASS（近似 3180 PASS / 17 skipped）/ **0 regression**
- **AC-5** CI 8/8 全绿（ubuntu/windows × py3.10/11/12 + mypy-strict + regression）
- **AC-6** `docs/superpowers/JURY_MATCHES_SPEC_STATUS.md` §11 表 #1 + #6 标 **closed (v2.37.2)**
- **AC-7** PR squash merged → tag v2.37.2 → GitHub Release published，覆盖 #1 + #6 两点

---

## 5. 风险与边界

| 风险 | 评估 | 缓解 |
|---|---|---|
| max_tokens 1024 让 LLM 偶尔走更长输出 → API 成本略增 | 单视角 +1¢ 级，每 run 7 视角 ≤ +7¢；可忽略 | 不缓解；YAGNI |
| `matches_spec=True` 在某 downstream 用了 `len(semantic_checks)` 或精确 key 集断言 | 低（grep `semantic_checks` 用法多是 `.get(key)` 或迭代 _REQUIRED_BOOL_KEYS）| plan 第 0 task grep 验证 |
| 改 verdict.py docstring 触发 `tests/test_agents_md.py` 等元测试 | 极低（描述文档不进 AGENTS.md skill 表）| AC-5 CI 覆盖 |
| dev_sync 镜像同步漏 | 中（项目有 `src/cad_spec_gen/data/tools/` 镜像）| plan 第 0 task 跑 `git ls-files \| grep llm_client.py$` + `verdict.py$` 确认 canonical 路径 |

---

## 6. 不变量

1. `_REQUIRED_BOOL_KEYS` 仍 5 key（matches_spec 仍是 derived field）— spec §8 不变量 #1
2. `aggregate_run_verdict` 实现不变（`.get("matches_spec", True)` 与显式 True 在所有现有路径上等价）
3. retry 触发逻辑不变（`has_real_feature_fail` 仍要求 `features_status` 非空）
4. 「空 features_status → matches_spec=True」向后兼容路径不变 — spec §6 验收 #1
5. CI 8 job 矩阵不变；不加新 marker、不加新 fixture、不动 conftest
6. 不加 env var、不加 JuryProfile 字段（零配置北极星）

---

## 7. 流程与提交建议

```
brainstorming（本 spec）→ writing-plans → 5-7 task plan → executing-plans
  ↓
TDD 串行：RED 测试 → impl 1 行 → GREEN → 下一个改动
  ↓
self-review → CI → squash merge main → tag v2.37.2 → GitHub Release
```

提交按改动拆 commit 便于 review：
1. `fix(jury): _make_needs_review_verdict 6-key 形态一致性（§11 #1）` — verdict.py + 2 测试
2. `fix(jury): max_tokens 512→1024 防 features_status 截断（§11 #6）` — llm_client.py + 1 测试
3. `docs(jury): STATUS §11 #1+#6 closed + v2.37.2 retro` — docs

也可合 1 commit，plan 决定。commit message 描述部分中文；提交 `git -c commit.gpgsign=false commit`；分支 `feat/jury-v2-37-followup-cleanup`（不要在 main 上直接动）。

---

## 8. Plan 调查步（plan 第 0 task 跑）

1. `git ls-files | grep -E '(llm_client|verdict)\.py$'` — 确认 canonical 路径与 `src/cad_spec_gen/data/tools/` 镜像；改 canonical 后是否要 `python scripts/dev_sync.py`
2. `grep -rn "_make_needs_review_verdict\|semantic_checks\[" tools/ tests/ src/` — 找 downstream 是否用 `len(semantic_checks)` 或精确 key 集断言（spec §5 风险表）
3. `grep -rn "max_tokens" tools/jury tests/jury` — 是否其它地方也硬编码 512（同步改或确认本 PR 只覆盖一处）
4. `git ls-files -v | grep -E '(llm_client|verdict)\.py'` — skip-worktree 守卫（`feedback_skip_worktree_per_machine_config.md`）
5. 看 `tests/jury/test_llm_client.py` 现状 — 找现有 urlopen mock 风格、复用 fixture
6. 看 `tests/jury/test_verdict.py` 现状 — 找现有 `_make_needs_review_verdict` 测试（spec §6 验收 #1 类）作邻接参考

---

## 9. 不写代码 / 不进 plan 的事

- 不重构 `verdict.py` 整体形态（如把 `_REQUIRED_BOOL_KEYS` 改 dataclass）
- 不动 `tools/jury/feature_extractor.py`（v2.37.1 已处理 markdown 围栏 bug）
- 不补 micuapi.ai 之外的第三方代理实测——v2.37.1 已建立"真实代理实测"checklist 项，留下次新 spec 触发
- 不改 verdict 决策树 / 阈值 / 白名单
