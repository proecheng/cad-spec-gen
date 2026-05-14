# 设计：v2.37.3 §12 follow-up — mock helper + line rationale

- **日期**：2026-05-14
- **基线**：main@`82ecd7a`（v2.37.2 merge 后；working tree clean）
- **分支**：`feat/v2-37-3-mock-helper-line-rationale`（待建）
- **目标版本**：v2.37.3（patch release / 纯 git tag + GitHub Release / 不 bump 版本文件）
- **规模**：极小 单 PR；总 diff ≈ 20-25 行
- **状态**：brainstorming 完成（2 处 F1+F2 漂移 inline 修）；待用户复审 → writing-plans

---

## 1. 背景与目标

v2.37.2 发布后 §12 预登记 2 项（Task 4 code-review 提出）：

- **F1** `tests/jury/test_llm_client.py` 有 2 处 `m.call_args[0][0]` mock 内部解构（line 312 + line 336-337），耦合到 urllib `Request` 实现细节；抽 `_get_urlopen_request(m)` test helper 单一化耦合点
- **F2** `tools/jury/llm_client.py:105-107` 现 2 行注释只引 spec §11 #6 + §6 #10，没说**为什么 1024 而非其它值**；插 1 行实测数据（"micuapi.ai ~800 token / 2× 余量"）减少 git blame 跳转

**核心约束：零行为变化**——helper 抽取纯结构 refactor、注释扩展纯文档。

**北极星 5 gate**：零配置 ✓ / 稳定可靠 ✓（修脆性 mock 内部耦合）/ 结果准确 ✓ / 傻瓜式 ✓ / SW 装即用 ✓；Windows-only ✓。

---

## 2. 范围

### 2.1 In-scope

| 文件 | 改动 | 行数 |
|---|---|---|
| `tests/jury/test_llm_client.py` | 加 `_get_urlopen_request(m: MagicMock)` helper（放 `_make_cm` 邻近 line 61-66 之后；返 `m.call_args[0][0]` 即被 patch 时存的 Request 实例；**不加 `-> Request` annotation 避免新增 import**）；line 312 + line 336-337 两处调用替换 | helper +5-7 / call site 2 处共 -1 (336-337 二行合一) |
| `tools/jury/llm_client.py:105-107` | 原 2 行注释中间插 1 行：`# 实测 micuapi.ai 长输出 ~800 token；1024 = 2× 余量留未来 12+ features_status 序列化扩展空间。` | +1 |
| `docs/superpowers/JURY_MATCHES_SPEC_STATUS.md` §9.3 §11 follow-up 表 | line 72 (#1) + line 77 (#6) 已 v2.37.2 closed；本 PR 不动这两行。**§12 预登记 2 项原在 v2.37.2 spec doc §12 + retro 文档**——本 PR 在 retro 文档（待新写）登记 closed v2.37.3 | ~3-5（仅 retro 追加，不动 STATUS doc） |
| `docs/superpowers/reports/2026-05-14-v2-37-3-mock-helper-line-rationale-retro.md`（新写） | 完工 retro，复用 v2.37.2 retro 风格 | ~60-80 |

**总 diff ≈ 20-25 行代码 + ~70 行 retro 文档**

### 2.2 Out-of-scope（明确划界）

- §12 其它 6 项（spec f1-f6 / layer 5 五角色登记的）—— 留独立后续 PR
- `tests/jury/test_llm_client.py:296` `kwargs = m.call_args` timeout 测试形态不同（kwargs 而非 [0][0]），**不抽 helper**
- 改 `request_jury_verdict` production 逻辑 / `max_tokens` 数值 / `_REQUIRED_BOOL_KEYS` 任何契约 —— 全不动
- 加 env / config —— 永远不（北极星）

---

## 3. 设计决策

### 3.1 D1 — 单 `_get_urlopen_request` helper（不二分）

**抉择**：1 个 helper 返 `m.call_args[0][0]`，调用方按需访问 `.get_header()` / `.data` / `.full_url` 等。

**理由**：
- 当前 2 处 call site 形态不同（line 312 取 header、line 336 取 body）—— 二分 helper 会 API 膨胀
- 单 helper 最瘦、未来加新断言点（如 method / url）零开销

**对 DRY Rule of Three 的判定**：严格 Rule of Three 要求 3+ 处才抽 helper；当前 2 处。但抽 helper 仍合理——它是**预防性 + 语义清晰**收益（mock 内部 `call_args[0][0]` 不是自解释代码；helper name `_get_urlopen_request` 让意图自描述）。**不假装是 DRY-3+ 触发，而是预防性 refactor 决策**。

### 3.2 D2 — Helper 返回类型不加 annotation

**抉择**：函数签名 `def _get_urlopen_request(m: MagicMock):` 不加 `-> Request` 返回类型 annotation。

**理由**：
- 实测中 mock 替换 `urlopen` 后 `m.call_args[0][0]` 严格说是 **MagicMock 对象**（被 patch 时存的 Request 实例，但类型在 mock 框架下是 Any）
- 加 `-> Request` annotation 需要 `from urllib.request import Request` import（当前文件没有）；为 1 个 helper 加 import 增加耦合
- `tests/jury/` 不在 mypy-strict gate（v2.37.2 spec §2.1 末尾约定）——不加 annotation 不报错
- 函数 docstring 说明返回的是「`m.call_args` 中第 1 个位置参数，被 patch 时是 urllib `Request` 实例」即可

### 3.3 D3 — Line 105 注释中间插 1 行

**抉择**：原 2 行注释保留，**中间**插 1 行实测数据。

**理由**：
- 现 2 行结构「§11 #6 + §6 #10」逻辑清晰，不重写
- 实测数据「~800 token / 2× 余量」最直接回答「为什么 1024」，应紧邻数值
- 总 3 行注释仍可读 < 100 col 内

### 3.4 D4 — 无 TDD RED phase

**抉择**：本 PR 全是 REFACTOR 性质（既有测试就 GREEN）。

**理由**：
- F1 helper 抽取是 pure refactor，重构前后所有测试断言不变 → 既有测试就是 GREEN
- F2 注释扩展不改任何运行时行为
- TDD R 步定义 = 「不改行为下提升可读性」—— 本 PR 就是 R 步本质

**no-RED 不是跳 TDD**：现有 504 测试本身就是该 refactor 的安全网；spec §13 R4 Q5 baseline 验证 + 重构后 PASS 数不变即证零行为变化。

---

## 4. 验收

- **AC-1** `pytest tests/jury/test_llm_client.py -v` 全套 PASS 不变（v2.37.2 后 baseline = 14 case）；新 helper 不增测试数
- **AC-2** `_get_urlopen_request(m)` 返值上调用 `.get_header("User-agent")` 与 `.data` 都仍可用（既有测试断言成功 = 隐式证明）
- **AC-3** `ruff check tests/jury/test_llm_client.py tools/jury/llm_client.py` clean
- **AC-4** `tools/jury/llm_client.py:105-108` 改后 3 行注释，含 `~800 token` 实测数据
- **AC-5** jury 子集 PASS 数 ≥ v2.37.2 baseline 503（refactor 零变化，不增不减）
- **AC-6** CI 8/8 SUCCESS
- **AC-7** 发 v2.37.3 patch tag + GitHub Release（升级路径复制 v2.37.2 Release notes 模板）

---

## 5. 风险与边界

| 风险 | 评估 | 缓解 |
|---|---|---|
| Helper 抽取无意改测试行为 | 低（pure refactor）| AC-1 既有测试 PASS 不变 = 行为不变证 |
| Mock 内部 `call_args[0][0]` 语义未来 urllib 改 | 极低（Python urllib `Request` 25+ 年稳定）| 抽 helper 后未来若改只动 1 处 |
| Helper 命名 `_get_urlopen_request` 与既有 helper（`_make_cm` / `_mock_response`）风格不一致 | 低（既有用动词短语；`_get_X` 也是动词）| 不强求；plan task 0 grep 既有 helper naming 风格再定 |

---

## 6. 不变量

1. `tools/jury/llm_client.py` `request_jury_verdict` body 序列化逻辑不动（含 `max_tokens=1024` / `temperature=0.0` / 任何字段）
2. `tools/jury/verdict.py` 完全不动
3. 测试断言行为零变化（helper 抽取重构）
4. 不加 env / config / fixture / marker / conftest
5. v2.37.2 既有 §6 不变量 #1-#11 全保留
6. `src/cad_spec_gen/data/tools/jury/` 镜像与 canonical 不漂移（每改 canonical 后跑 `python scripts/dev_sync.py`）
7. CI 8 job 矩阵不变；CI 既存 dev_sync `--check` gate 自动覆盖镜像同步

---

## 7. 流程与提交建议

```
brainstorming（本 spec）→ writing-plans → 2-3 task plan → execute
  ↓
Pure refactor（无 RED phase）：改 → 跑既有测试 PASS 不变 → 改下个 → commit
  ↓
self-review → CI → squash merge main → 等 main CI 全绿 → tag v2.37.3 → Release
```

提交建议 2-3 commit：
1. `refactor(test): 抽 _get_urlopen_request helper 消除 mock 内部解构耦合（§12 F1）` — test_llm_client.py
2. `docs(jury): max_tokens 1024 line 注释加实测 rationale（§12 F2）` — llm_client.py
3. `docs(jury): STATUS / retro 标 §12 F1+F2 closed v2.37.3` — docs

---

## 8. Plan 调查步（plan 第 0 task 跑）

1. `git status --short && git log --oneline -3` —— 验证 baseline 是 main@`82ecd7a` clean
2. `python scripts/dev_sync.py --check` —— rc=0 baseline 干净
3. `pytest -q tests/jury/test_llm_client.py 2>&1 | tail -3` —— baseline 实测（v2.37.2 后 = 14 case PASS）
4. `grep -n "call_args\[0\]\[0\]" tests/jury/test_llm_client.py` —— 验证 2 处位置（line 312 + line 337）
5. `grep -n "_make_cm\|_mock_response" tests/jury/test_llm_client.py` —— 找 helper 邻近位置插入点
6. `grep -n "max_tokens" tools/jury/llm_client.py` —— 验证 line 107 当前 1024

---

## 9. Plan 必 cover 项（writing-plans inline 拾起）

- 每 commit 含 canonical + dev_sync 镜像同步（zerodrift；v2.37.2 spec §13 D3）
- PR push 前 `git fetch origin main && git log --oneline HEAD..origin/main` 验证无并行改动（M1）
- dev_sync 跑完后 `git status` verify mirror modified（M2）

---

## 10. 不写代码 / 不进 plan 的事

- 不二分 helper（`_extract_request_body` + `_extract_request_headers`）
- 不为 helper 加 type annotation
- 不改 `tests/jury/test_llm_client.py:296` timeout 测试（kwargs 形态不同）
- 不动 production 代码逻辑（只动 line 107 注释，不改 1024 数值）
- 不开 §12 其它 6 项（spec f1-f6）

---

## 11. v2.37.2 §12 follow-up 表（本 PR 闭合 2 项）

| # | 严重度 | 内容 | 状态 |
|---|---|---|---|
| F1 | LOW | mock helper 抽取消除 `m.call_args[0][0]` 耦合 | **closed v2.37.3**（本 PR）|
| F2 | LOW | line 105 注释扩 1024 定量 rationale | **closed v2.37.3**（本 PR）|
| f1-f6 | LOW | spec §12 预登记 layer 5 五角色 6 项 | 未闭合，留独立 PR |

---

## 12. 本 PR 自身 follow-up

| # | 严重度 | 内容 | 来源 |
|---|---|---|---|
| g1 | LOW | helper 命名 `_get_urlopen_request` 与既有 `_make_cm` / `_mock_response` 风格统一度（plan task 0 实测后决）| spec §5 风险表 |
