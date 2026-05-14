# 设计：v2.37 §11 follow-up cleanup（#1 + #6）— v2.37.2

- **日期**：2026-05-14
- **基线**：main@`c4653d2`（PR #79 docs squash 之后；working tree clean）
- **分支**：`feat/jury-v2-37-followup-cleanup`
- **目标版本**：v2.37.2（patch release，git tag + GitHub Release，不 bump 版本文件——本项目 v2.25+ 惯例）
- **规模**：小 单 PR；总 diff ≈ 70 行（2 行实现 + 测试 + 文档 + CI gate + docstring 对齐）
- **状态**：brainstorming 完成 + **5 层审查通过**（self / cynical re-read / code-spec 对照 / edge-case hunter 7 findings 全修 / 5 角色并行 + holistic dry-run 共 34 findings 分类处置：10 inline 修 + 10 plan 层细化 + 6 §12 follow-up + 6 discard + 2 可暂缓）；待用户复审 → writing-plans

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
| `tools/jury/verdict.py:189-194` `aggregate_run_verdict` docstring | **对齐 docstring 与代码**：把 `all(view.semantic_checks["matches_spec"] for view)` 改为 `all(view.semantic_checks.get("matches_spec", True) for view)` 与 line 199 实现一致（edge-case finding #1）|
| `tools/jury/verdict.py::_make_needs_review_verdict` docstring | 注释 matches_spec=True 是兜底语义（与「空 features_status → True」一致） |
| `.github/workflows/tests.yml` | **加 `python scripts/dev_sync.py --check` step**（在 lint 之后、pytest 之前；失败即 fail）防 src 镜像漂移（edge-case finding #2）|
| `tests/jury/test_llm_client.py`（确认存在 316 行）| 1 个 TDD 回归测试：mock `urlopen`，断言序列化 request body 里 `max_tokens == 1024` |
| `tests/jury/test_verdict.py` 或 `tests/jury/test_verdict_matches_spec.py` | 2 个 TDD 回归测试，**位置由 plan 第 0 task 据职责划分决定**：(a) `_make_needs_review_verdict([...])` 返回 6-key dict 含 `matches_spec=True`（base helper 测试 → 倾向 `test_verdict.py`）(b) `aggregate_run_verdict` 把 needs_review 视角混入后 `overall_matches_spec` 行为不变（matches_spec 维度专属 → 倾向 `test_verdict_matches_spec.py`） |
| `docs/superpowers/JURY_MATCHES_SPEC_STATUS.md` §11 表 | 标 #1 + #6 closed |
| `docs/superpowers/reports/2026-05-14-...retro.md` | 提交后写 retro（小规模 PR 仍写，沉淀流程）|

**测试 lint/type 约束（edge-case finding #6）**：所有新加测试必须通过 `ruff check`；不进 mypy-strict gate（与既有 jury 测试一致——`tests/jury/` 不在 mypy-strict 路径白名单内，本 PR 不改这条边界）。

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

### 3.4 D4 — TDD RED → GREEN → REFACTOR

**抉择**：每个改动严格走 TDD 三步：先写失败测试（RED），改实现到测试通过（GREEN），最后走一遍 REFACTOR 步骤——本 PR scope 小，REFACTOR 多半是 **no-op** 显式确认而非真重构；但**禁止跳过 R 步**，避免引入冗余 dict 构造 / 重复字面量。

**REFACTOR 步具体动作**（每改动一次必跑）：
- 看新加测试 + 新改实现是否引入与 normal path / 邻近代码重复的字面量（如 6-key dict 直接写还是循环 `_REQUIRED_BOOL_KEYS + ("matches_spec",)` 构造）
- 若发现冗余 → 提取常量 / helper；若无 → 注释一行「REFACTOR: 无冗余可清，跳过」记入 commit message

**理由**：CLAUDE.md 项目铁律；scope 小到 5 分钟一轮，TDD 几乎零摩擦；防 max_tokens 字段名拼错 / matches_spec key 名拼错这种「人手抖」回归；edge-case finding #5 显式要求 R 步不缺。

---

## 4. 验收标准

- **AC-1** `tools/jury/llm_client.py` `request_jury_verdict` 序列化 body 后，`json.loads(body)["max_tokens"] == 1024`（mock urlopen 拦截 request data；新测试 GREEN）
- **AC-2** `_make_needs_review_verdict(["content_not_json"])` 返回的 `ViewVerdict.semantic_checks` 含 6 key（原 5 + `matches_spec`），`matches_spec is True`；新测试 GREEN
- **AC-3** `aggregate_run_verdict({...含 1 个 needs_review 视角 + 1 个 normal 视角...})` 的 `overall_matches_spec` 与改动前等价（True iff normal 视角的 matches_spec 是 True）；新测试 GREEN
- **AC-4** 全套件 jury 子集 `pytest tests/jury/ tests/jury_loop/ -q` ≥ 当前基线 PASS（plan 第 0 task 实测填入；v2.37.1 后近似 ~700+ PASS）；总套件 ≥ 当前基线 PASS（近似 3180 PASS / 17 skipped）/ **0 regression**
- **AC-5** CI 8/8 全绿（ubuntu/windows × py3.10/11/12 + mypy-strict + regression）。**Transient flake 容忍**：允许同 commit re-run（如 GitHub Actions infrastructure 偶发 / pip cache miss）；连续 2 次同 job 同失败签名才视为真 regression、必须修代码而非 re-run（edge-case finding #4）
- **AC-6** `docs/superpowers/JURY_MATCHES_SPEC_STATUS.md` §11 表 #1 + #6 标 **closed (v2.37.2)**
- **AC-7** PR squash merged → tag v2.37.2 → GitHub Release published，覆盖 #1 + #6 两点

---

## 5. 风险与边界

| 风险 | 评估 | 缓解 |
|---|---|---|
| max_tokens 1024 让 LLM 偶尔走更长输出 → API 成本略增 | 单视角 +1¢ 级，每 run 7 视角 ≤ +7¢；可忽略 | 不缓解；YAGNI |
| `matches_spec=True` 在某 downstream 用了 `len(semantic_checks)` 或精确 key 集断言 | 低（grep `semantic_checks` 用法多是 `.get(key)` 或迭代 _REQUIRED_BOOL_KEYS）| plan 第 0 task grep 验证 |
| 改 verdict.py docstring 触发 `tests/test_agents_md.py` 等元测试 | 极低（描述文档不进 AGENTS.md skill 表）| AC-5 CI 覆盖 |
| dev_sync 镜像同步漏 | **降级为低**（本 PR 加 CI gate 强制，§6 #8）| plan 第 0 task 跑 `git ls-files \| grep llm_client.py$` + `verdict.py$` 确认 canonical 路径；CI dev_sync --check step 自动拦截漏 sync |
| max_tokens 1024 仍偶发截断（vendor 不尊重字段 / LLM 超长输出）| 低（finish_reason='length' 自动进 needs_review，verdict.py:61 早闭环）| 现有 `parse_view_verdict` `finish_reason ∉ {"stop", None}` 逻辑兜底；若实测高频再扩 v2.37.3 → 2048（§7.1 不回退边界）|
| **vendor 返 400 bad_request 因 max_tokens 超 vendor 上限**（如 micuapi.ai 部分 proxy 上限 512/768）| 低-中（v2.37.1 实测 micuapi.ai 不报 400；但其它代理未测）| 现有 `_classify_http_error` 把 400 标 `bad_request` fail-fast；若用户报「v2.37.2 后某代理 400」→ 触发 §7.1 rollback（R3 U6）|
| **max_tokens 1024 被 LLM 用满 → 单视角 jury 延迟 ~3s → ~6s 压 orchestrator Popen timeout 边界**（CP-6 SEC-MINOR-4 历史 timeout 值未在本 spec 量化）| 低（temperature=0 + 800 token 实测 ~3-5s，远低于 orchestrator 内部 60s `_TOTAL_SECONDS_PER_CALL`）| plan 第 0 task grep `_TIMEOUT_SEC` + `_TOTAL_SECONDS_PER_CALL` 量化当前阈值；实测若 p95 latency 突破 30s 加 v2.37.3 follow-up（R1 M6）|

---

## 6. 不变量

1. `_REQUIRED_BOOL_KEYS` 仍 5 key（matches_spec 仍是 derived field）— spec §8 不变量 #1
2. `aggregate_run_verdict` 实现不变（`.get("matches_spec", True)` 与显式 True 在所有现有路径上等价）
3. retry 触发逻辑不变（`has_real_feature_fail` 仍要求 `features_status` 非空）
4. 「空 features_status → matches_spec=True」向后兼容路径不变 — spec §6 验收 #1
5. CI 8 job 矩阵不变；不加新 marker、不加新 fixture、不动 conftest
6. 不加 env var、不加 JuryProfile 字段（零配置北极星）
7. **`src/cad_spec_gen/data/tools/` 镜像与 `tools/jury/` canonical 不漂移**：每个 commit 改 canonical 后 plan 任务里必跑 `python scripts/dev_sync.py`；PR push 前必跑 `python scripts/dev_sync.py --check` 验证 git diff 干净（fact-check 自发现 #1 + memory `feedback_subagent_cwd_drift` / `feedback_check_conftest_marker_first` 双教训）
8. **CI gate 强制 dev_sync 同步**：本 PR 在 `.github/workflows/tests.yml` 加 `python scripts/dev_sync.py --check` step，失败即 CI 红——把人工纪律降级为机器强制（edge-case finding #2）；下次任何 PR 改 canonical 漏 sync 直接被 CI 拦
9. **CI test path（canonical `tools/jury/`）== 用户 runtime path（`src/cad_spec_gen/data/tools/jury/`，由 hatch_build COPY_DIRS 打包）**：因不变量 #7 + #8 锁定镜像与 canonical 字节级一致，CI 测 canonical 通过 ⇔ 用户 install 后跑镜像也通过；本 PR 「零行为变化」声明因此同时覆盖 CI 路径与 runtime 路径（edge-case finding #3）
10. **`finish_reason='length' → needs_review` 是 max_tokens 安全网**（layer 5 R2 L6）：`tools/jury/verdict.py:61-63` 「`if finish_reason not in {"stop", None}: anomalies.append("finish_reason_invalid")`」+ 「serious anomaly → verdict='needs_review'」是 max_tokens 1024 仍偶发不够时的兜底护栏；本 PR 依赖此契约，**改动 `parse_view_verdict` finish_reason 处理需同步评估对本 PR 的影响**
11. **历史 5-key 存档反序列化兼容**（layer 5 R3 U3）：v2.37.1 时代用户已经存的 ENHANCEMENT_REPORT.json / matches_spec sidecar / verdict.json 含 5-key `semantic_checks`（无 matches_spec）；v2.37.2 升级后这些历史存档被 `aggregate_run_verdict` 重新加载时仍走 `.get("matches_spec", True)` 默认路径（不变量 #2 锁定）→ overall_matches_spec 行为与 v2.37.1 等价；用户磁盘上历史数据**零迁移、零行为变化**

---

## 7. 流程与提交建议

```
brainstorming（本 spec）→ writing-plans → 5-7 task plan → executing-plans
  ↓
TDD 串行：RED 测试 → impl 1 行 → GREEN → REFACTOR → 下一个改动
  ↓
self-review → PR CI 8/8 全绿 → squash merge main → 等 main CI 全绿 → tag v2.37.2（指向 main HEAD sha 非分支 sha）→ GitHub Release
  ↓
（layer 5 R5 D5 + R1 M7：tag 必须基于 squash merge 后 main 的实际 sha；Release notes 引用 v2.37.2 tag 而非分支 sha）
```

提交按改动拆 commit 便于 review：
1. `fix(jury): _make_needs_review_verdict 6-key 形态一致性（§11 #1）` — verdict.py + 2 测试
2. `fix(jury): max_tokens 512→1024 防 features_status 截断（§11 #6）` — llm_client.py + 1 测试
3. `chore(ci): tests.yml 加 dev_sync --check gate（不变量 §6 #8）` — workflow
4. `docs(jury): STATUS §11 #1+#6 closed + v2.37.2 retro` — docs

也可合 1 commit，plan 决定。commit message 描述部分中文；提交 `git -c commit.gpgsign=false commit`；分支 `feat/jury-v2-37-followup-cleanup`（不要在 main 上直接动）。

### 7.0 用户升级路径（layer 5 R3 U2）

本项目 v2.25+ 惯例：**纯 git tag + GitHub Release notes**，`pyproject.toml` 与 `src/cad_spec_gen/__init__.py` 不 bump 版本（停留 `2.24.0`）。用户升级路径：

- **PyPI**：本项目当前未发 PyPI；`pip install cad-spec-gen` 拿不到 v2.37.2
- **git+https**：`pip install git+https://github.com/proecheng/cad-spec-gen.git@v2.37.2`（推荐）
- **GitHub Release zip**：从 Release 页下载 tarball / zip → `pip install ./cad-spec-gen-v2.37.2.tar.gz`
- **本地开发**：`git fetch && git checkout v2.37.2 && pip install -e .`

GitHub Release notes 必须 inline 复述此清单（每次 release 都写，因没自动化 PyPI）。

### 7.1 Rollback 流程（edge-case finding #7）

**触发条件**：v2.37.2 发布后 24h 内用户实测报 regression（jury 决策异常 / max_tokens 1024 触发新截断 finish_reason='length' 进 needs_review 不预期 / aggregate overall_matches_spec 行为变化）。

**回退路径**：
1. `git revert <v2.37.2 merge sha>` 在 main 创回退 commit（**不** 强推、不删 v2.37.2 tag）
2. push main → CI 8/8 全绿后发 v2.37.3 hotfix tag + GitHub Release notes 解释为何回退
3. 保留 v2.37.1 tag + v2.37.2 tag + v2.37.3 tag 都不动（git 历史可追溯）
4. **GitHub Release UI 把 v2.37.2 标 "Pre-release"（layer 5 R5 D7）**：因本项目"纯 git tag + Release notes"惯例下，用户 `pip install git+https://...@v2.37.2` 仍会拉到坏代码——单靠 revert + 新 tag 不够；Release notes 顶部加 ⚠️ banner: "**已知 regression，请用 v2.37.3 替换；详见 #N**"
5. 把触发回退的具体 regression 写进 §11 follow-up 新条目 + memory `feedback_jury_v2_37_2_rollback_lesson` 便于下次

**回退原子性边界**（layer 5 R1 M4）：squash merge 后 #1 + #6 已合为 1 个 commit，整 `git revert` 会同时回退两改动；**触发回退前先判定 regression 来源**——若仅 #6 截断锅，优先 `git cherry-pick -n <merge_sha>` 后只反向 patch llm_client.py 那段、保留 #1 helper 改动；只在两改动都疑似时整 revert。

**不回退的边界**：
- transient CI flake（finding #4 已覆盖）→ re-run 不回退
- 用户报"max_tokens 1024 仍偶发截断" → 不算 regression（v2.37.1 基线就会截断，本 PR 只是放宽）；登记 §11 新条目等更多数据再 v2.37.3 扩 1024 → 2048
- 用户报"某第三方代理返 400 因 max_tokens 超 vendor 上限"（layer 5 R3 U6）→ 取决于该代理用户规模：单代理 / <5 用户 → 走 §11 follow-up 加"vendor-specific max_tokens override"等候；多代理 / ≥1/3 实测用户受影响 → 触发 rollback

---

## 8. Plan 调查步（plan 第 0 task 跑）

1. `git ls-files | grep -E '(llm_client|verdict)\.py$'` — 确认 canonical 路径（应在 `tools/jury/`）与 `src/cad_spec_gen/data/tools/jury/` 镜像（`hatch_build.py:62` `COPY_DIRS = {"tools": "tools"}`）
2. `grep -rn "_make_needs_review_verdict\|semantic_checks\[" tools/ tests/ src/` — 找 downstream 是否用 `len(semantic_checks)` 或精确 key 集断言（spec §5 风险表）
3. `grep -rn "max_tokens" tools/jury tests/jury` — 是否其它地方也硬编码 512（同步改或确认本 PR 只覆盖一处）
4. `git ls-files -v | grep -E '(llm_client|verdict)\.py'` — skip-worktree 守卫（`feedback_skip_worktree_per_machine_config.md`）
5. 看 `tests/jury/test_llm_client.py`（316 行）现状 — 找现有 urlopen mock 风格、复用 fixture
6. 看 `tests/jury/test_verdict.py`（242 行）+ `tests/jury/test_verdict_matches_spec.py` 两文件现状 — **按职责定测试放哪：** base helper 改动（`_make_needs_review_verdict` 6-key）倾向放 `test_verdict.py`，matches_spec 维度集成（aggregate 行为不变）倾向放 `test_verdict_matches_spec.py`（fact-check 自发现 #3）
7. **`python scripts/dev_sync.py --check`** baseline 跑一遍 — 确认起点 git diff 干净，再开 TDD 改动；每改一次 canonical 后 plan 任务里必跑 `python scripts/dev_sync.py`（不变量 §6 #7）
8. `pytest -q tests/jury/ tests/jury_loop/ 2>&1 | tail -3` — 实测当前基线 PASS 数填入 AC-4
9. **读 `.github/workflows/tests.yml` 现状** — 找 lint job / pytest job 的相对顺序与 step 风格；定 `dev_sync --check` step 应插在 lint 之后、pytest 之前；确认 step 在 ubuntu / windows job 都跑（不变量 §6 #8）
10. **读 `tools/jury/verdict.py:189-194` aggregate_run_verdict docstring 原文** — 准确拷出待替换字符串避免 Edit 失败（finding #1 docstring 对齐改动）

---

## 9. 不写代码 / 不进 plan 的事

- 不重构 `verdict.py` 整体形态（如把 `_REQUIRED_BOOL_KEYS` 改 dataclass）
- 不动 `tools/jury/feature_extractor.py`（v2.37.1 已处理 markdown 围栏 bug）
- 不补 micuapi.ai 之外的第三方代理实测——v2.37.1 已建立"真实代理实测"checklist 项，留下次新 spec 触发
- 不改 verdict 决策树 / 阈值 / 白名单

---

## 10. 扩展新维度 checklist（防 §11 #1 类脆性再现 — layer 5 R2 L1）

1 年后若加第 7 维度（如 `render_quality`），按此 5 步硬清单同步改：

1. `tools/jury/verdict.py::_REQUIRED_BOOL_KEYS` —— **不动**（仍 5 key；新维度走 derived field 模式，与 `matches_spec` 一致）
2. `tools/jury/verdict.py::parse_view_verdict` 正常路径 —— 加 derived field 计算逻辑（参考 line 93-107 `matches_spec` 实现）
3. **`tools/jury/verdict.py::_make_needs_review_verdict`** —— 加 `"<新维度>": True` 兜底（**本 spec 修的位置；下次必同步！**）
4. `tools/jury/verdict.py::aggregate_run_verdict` —— 加 `.get("<新维度>", True)` 兜底聚合
5. `tools/jury/verdict.py:189-194` docstring —— 与代码 `.get` 用法一致；不直接索引

加测试时 parametrize 6→7 key 覆盖；任何 sidecar / verdict.json 写盘点同步加新字段（spec §6 不变量 #11 历史存档兼容路径自动覆盖向后兼容）。

---

## 11. 上游 §11 follow-up（v2.37 + v2.37.1）

本 PR 闭合的事项（来自 `docs/superpowers/JURY_MATCHES_SPEC_STATUS.md` §11 表）：
- **#1** `_make_needs_review_verdict` 5→6 key 一致性 → 本 PR D2
- **#6** `max_tokens=512` 偏紧 → 本 PR D1

未闭合（独立 PR / future）：#2 `_derive_matches_spec_status` warn/blocked / #3 render_qa mirror drift / #4 plan-drift 模板 / #5 cad-tests README

---

## 12. 本 PR 自身 follow-up（layer 5 R2 L5 — 未来 v2.37.3 / v2.38.0 可挂载位置）

发布后实测 / 长期演化发现的事项登记到这里，**不阻断 v2.37.2 发布**：

| # | 严重度 | 内容 | 来源 |
|---|---|---|---|
| (待) | — | （v2.37.2 发布后实测发现的新事项）| |

**预登记** 6 项（layer 5 5 角色审查产生，不阻断本 PR）：

| # | 严重度 | 内容 | 来源 layer 5 |
|---|---|---|---|
| f1 | LOW | max_tokens sunset 条件：若 12 月内连续 3 次扩 → 升级 env override；当前坚持零配置 | R2 L2 |
| f2 | LOW | spec 引用 memory 时加 inline 摘要（≤20 字）防 memory 改名/归档失锚 | R2 L3 |
| f3 | LOW | spec 顶加术语 mini-glossary（北极星 5 gate / dev_sync / 项目惯例）或链接 ADR | R2 L4 |
| f4 | LOW | N≥50 批量场景 API 月度成本评估 + 用户可见监控建议 | R3 U1 |
| f5 | LOW | user-visible 6-key debug 注释（说明 matches_spec=True 在 needs_review 视角下是兜底而非测量）| R3 U4 |
| f6 | LOW | `~/.claude/cad_jury_config.json` schema 不变 + `CAD_JURY_DISABLE_LLM=1` 路径 no-op 声明 | R3 U5+U7 |

---

## 13. Plan 阶段必 cover 项（layer 5 plan 层细化 10 条传递 — writing-plans 时 inline 拾起）

不写进 spec scope，但 plan 必须 cover：

| Plan task 应 cover | 来源 |
|---|---|
| commit 粒度原子（每 commit 含 canonical + dev_sync 镜像，不分 task）| R5 D3 |
| plan task 顺序：`add CI step` 必须先于 `改 canonical`，否则前几次 push CI gate 未生效 | R5 D4 |
| 测试 mock 风格沿用 `tests/jury/test_llm_client.py` 现有 `_make_cm` / `_mock_response` / `patch('tools.jury.llm_client.urlopen')` | R4 Q1 |
| AC-2 测试 parametrize 3 个 `_make_needs_review_verdict` 调用 path（content_not_json / missing_content / 非 dict payload）| R4 Q3 |
| AC-4 「基线」明确定义为 plan task 0 实测数；完工 PASS = 基线 + 新加测试数 | R4 Q5 |
| AC-3 扩 `asdict(aggregate)` 全字段等价（不只 overall_matches_spec）| R4 Q2 |
| 加 AC-3b：所有视角 needs_review 时 `overall_matches_spec is True 但 needs_review_count == N` | R4 Q4 |
| 加 AC-2b：6-key dict 序列化 JSON 后 key 顺序 = `_REQUIRED_BOOL_KEYS + ('matches_spec',)`；plan task 0 grep `json.dumps.*semantic_checks` 找写盘点 | R4 Q6 |
| PR push 前 `git fetch origin main && git log --oneline origin/main..HEAD -- tools/jury/` 验证无并行改动冲突 | R1 M1 |
| dev_sync 跑完后立刻 `git status` 验证两文件镜像 modified；不信任单次 exit 0 | R1 M2 + R5 D2 |
| baseline `dev_sync --check` dirty 时 abort plan 主任务，独立 cleanup commit 先修 | R5 D2 |
