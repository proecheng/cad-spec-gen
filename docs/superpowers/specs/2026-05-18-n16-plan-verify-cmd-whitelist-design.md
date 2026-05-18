# §11-N16 闭环 — Plan 中 verify 命令必抄 CI 白名单

| 项 | 值 |
|---|---|
| 日期 | 2026-05-18 |
| 目标 release | v2.37.16（v2.25+ tag-only） |
| 起源 | v2.37.15 retro §3.3 N-16（plan Task 8 写 `ruff check tools/ src/ tests/` 触发 24 historical errors false-alarm） |
| spec rev | 3（rev 1 → rev 2 修 C1/C2 数据漂移 + 7 处 → rev 3 修 EC-DRIFT-1 STATUS doc 不存在 + 7 处边界）|
| scope | 2 文件（`CLAUDE.md` + `docs/superpowers/reports/2026-05-18-v2-37-15-retro.md` 交叉引用） |
| 工艺 | pure docs append，无 RED/GREEN 阶段 |
| 预计工作量 | ~20-25 min |

---

## §1 目的

闭合 v2.37.15 retro §3.3 **§11-N16**：plan 文件中历史上存在凭直觉自定 `ruff` / `mypy` / `pytest` 命令 path scope，与 `.github/workflows/tests.yml` 真命令偏离，触发 pyproject 配置外的 false-alarm（v2.37.15 plan Task 8 step 2 实证：`ruff check tools/ src/ tests/` → 24 historical errors）。

本 spec 让该类错误未来不再发生，方法：

1. `CLAUDE.md ## Superpowers 插件工作流` 新增 `### Plan 中 verify 命令必抄 CI` 子节
2. 白名单表 7 行覆盖 `tests.yml` 全部 ruff/mypy/pytest step（每行 literal 命令，可 grep）
3. 显式 sync 责任 + narrowing-vs-override 边界 + 例外段
4. `v2.37.15 retro §3.3 N-16 row` 附 closure 引用（同 v2.37.13b → v2.37.14 模式）

零代码、零测试、零 lint scope 改动。

---

## §2 范围

| 项 | 内容 |
|---|---|
| 改 | `CLAUDE.md`（新 ### 子节）+ `docs/superpowers/reports/2026-05-18-v2-37-15-retro.md`（§3.3 N-16 row 附 closure 引用）= **2 文件** |
| 不改 | `JURY_MATCHES_SPEC_STATUS.md`（N-16 本就不在 §9.3 — 该 STATUS doc 只装 jury matches_spec 实现 follow-up，N-13~N-17 是 plan-writing 工艺规则不同性质）/ `.github/workflows/*.yml` / `tools/` / `tests/` / 其他 spec / 其他 plan |
| 测试 | 无（pure docs append；CLAUDE.md 不在 lint scope） |
| release | tag-only v2.37.16（v2.25+ 模式，不 bump `pyproject.toml`） |
| retro | merge 后单独 retro PR `docs/superpowers/reports/2026-05-18-v2-37-16-retro.md` |
| follow-up §11 | 本 PR retro §4 候选登记 EC-MIGRATE-GAP（retro §3.3 → STATUS doc migration 工艺缺失，作未来 N-18）；N-13/N-14/N-15 仍 ⬜ open，本 PR 不涉 |

---

## §3 改动详情

### §3.1 `CLAUDE.md` 新增子节

**位置**：`## Superpowers 插件工作流` 区块底部，在现有 `### 并行任务` 子节之后、`---` 分隔线之前。

**完整新增文本**：

```markdown
### Plan 中 verify 命令必抄 CI（防 N-16 类 false-alarm）

**适用范围**：本节规则仅约束 **plan 文件**（`docs/superpowers/plans/*.md`）中的 verify step（步骤含"运行 ruff" / "运行 mypy" / "运行 pytest" 等之类的 CI 镜像验证）。**不**约束本地开发 pre-commit 提示（见 `## 技术规范 → Python` 的 `uv run ruff check .` 是本地工作流），**不**约束单文件 / single-test pytest 调用。

plan verify step 中所有 ruff / mypy / pytest 命令必须 **verbatim 抄** `.github/workflows/tests.yml` 中对应 step 的整行命令（含 quote 风格 / 空格 / 续行符），**不许** 自加 path scope / select override。否则会触发 pyproject 配置外的 false-alarm（v2.37.15 plan Task 8 实证：写 `ruff check tools/ src/ tests/` 触发 24 historical errors，应改 `ruff check .`）。

**verify 命令白名单**（截至 2026-05-18 / v2.37.15）：

| 用途 | tests.yml step 名 | plan 中允许写法 |
|---|---|---|
| ruff lint 全仓 | `ruff-strict` → "Run ruff check (P1+P2+P3 全规则集 守门)" | `ruff check .` |
| mypy broker | `mypy-strict` → "Run mypy strict on sw_config_broker.py" | `mypy --platform=win32 adapters/solidworks/sw_config_broker.py` |
| mypy jury | `mypy-strict` → "Run mypy strict on tools/jury" | `mypy --strict tools/jury tools/photo3d_jury.py tools/_file_lock.py` |
| mypy render-QA | `mypy-strict` → "Run mypy strict on render QA / path_policy" | `mypy --strict tools/enhance_consistency.py tools/render_qa.py tools/path_policy.py tools/view_instance_evidence.py` |
| pytest 全套 (Linux) | `test` → "Run tests with coverage gate (Linux / macOS)" | `pytest tests/ -v --tb=short -m "not mypy" --cov=adapters.solidworks.sw_config_broker --cov=adapters.solidworks.sw_config_lists_cache --cov-report=term-missing --cov-fail-under=95` |
| pytest 全套 (Windows) | `test` → "Run tests with coverage gate (Windows, PYTHONUTF8=1)" | `pytest tests/ -v --tb=short -m "not mypy" --cov=adapters.solidworks.sw_config_broker --cov=adapters.solidworks.sw_config_lists_cache --cov=adapters.solidworks.sw_list_configs_worker --cov-report=term-missing --cov-fail-under=95` |
| pytest regression | `regression` → "Run parts_resolver unit tests with kill switch" | `pytest tests/test_parts_resolver.py tests/test_parts_adapters.py -v` |

**narrowing 允许 vs scope override 禁止**：

- ✓ 允许 `-k filter` / `-x` / `--lf` 等 selector narrowing（在 CI scope 内做子集筛选）
- ✗ 禁止 `ruff check tools/ src/`（path override）/ `ruff check --select=X`（rule override）/ `mypy --strict <与 tests.yml 不同的 files>` / `pytest tests/ --cov=other`（cov target override）

**sync 责任**：`tests.yml` 中 ruff / mypy / pytest step 增删改时，PR **建议同步改本表**（INFO，非阻断）；reviewer 抓 `tests.yml` diff 含 lint/test 命令变动但 CLAUDE.md 未动 → 提示同步即可。

**例外**：

- 单测 / single-test pytest（如 `pytest tests/test_foo.py::test_bar -v`）不算 verify step，可自由写
- 本地 pre-commit 检查（见 `## 技术规范 → Python` 的 `uv run` 形式）独立轨道，不在本节范围
```

### §3.2 `v2.37.15 retro §3.3 N-16 row` 附 closure 引用

**改动**：retro doc §3.3 表 N-16 行末追加 closure cross-link（与 v2.37.13b retro §3.3 N12 → v2.37.14 同模式）。

**before**（当前）：

```markdown
| **§11-N16** | plan ruff command scope 校准 — v2.37.15 Task 8 step 2 ruff check 命令带显式 path `tools/ src/ tests/`，逾出 pyproject.toml 配的 ruff scope，触发 24 pre-existing 历史债 errors；项目 CI 真用 `ruff check .`（pyproject scope）。**未来 plan ruff/mypy command 必须 verbatim 抄项目 CI 命令** | 下次写 ruff verify step plan 触发 |
```

**after**：

```markdown
| **§11-N16** | plan ruff command scope 校准 — v2.37.15 Task 8 step 2 ruff check 命令带显式 path `tools/ src/ tests/`，逾出 pyproject.toml 配的 ruff scope，触发 24 pre-existing 历史债 errors；项目 CI 真用 `ruff check .`（pyproject scope）。**未来 plan ruff/mypy command 必须 verbatim 抄项目 CI 命令** | ✅ **closed v2.37.16**（CLAUDE.md `## Superpowers 插件工作流` 新增 `### Plan 中 verify 命令必抄 CI` 子节 + 7 行白名单 + narrowing-vs-override + sync 责任，见 [spec](../specs/2026-05-18-n16-plan-verify-cmd-whitelist-design.md)） |
```

---

## §4 验收标准

| AC | 内容 | 验证方式 | 期望 |
|---|---|---|---|
| AC-1 | CLAUDE.md 含新 ### 子节标题 | `grep -n "Plan 中 verify 命令必抄 CI" CLAUDE.md` | ≥ 1 line |
| AC-2 | 白名单 7 行全 literal grep 可命中 | `grep -cE "ruff check \.\|mypy --platform=win32 adapters/solidworks\|mypy --strict tools/jury\|mypy --strict tools/enhance_consistency\|--cov-fail-under=95\|pytest tests/test_parts_resolver" CLAUDE.md` | ≥ 7（6 pattern × 多次匹配） |
| AC-3 | 适用范围 + 主规则 + sync 责任 3 处提及 tests.yml | `grep -c "tests.yml" CLAUDE.md` | ≥ 3 |
| AC-4 | narrowing-vs-override + example 段存在 | `grep -nE "narrowing 允许 vs scope override 禁止\|single-test pytest" CLAUDE.md` | ≥ 2 lines |
| AC-5 | v2.37.15 retro §3.3 N-16 row 含 closure 引用 | `grep -n "v2.37.16" docs/superpowers/reports/2026-05-18-v2-37-15-retro.md` | ≥ 1 line |
| AC-6 | CI 9/9 SUCCESS | `gh pr checks <PR>` | all pass |

注：AC-2 grep pattern 用 `-cE` ERE（CLAUDE.md §8 跨平台约定）；`\.` 防 `.` regex 匹配；OR 用 `|`（CLAUDE.md §8 不用 `\|`）。

---

## §5 北极星 5 gate 自审

| Gate | 影响 | 判定 |
|---|---|---|
| 零配置 | 无 | ✓ |
| 稳定可靠 | 增加 plan-time 防御层，防 false-alarm 干扰开发节奏 | ✓ |
| 结果准确 | 减少 plan reviewer / subagent 因 plan-drift 误判 | ✓ |
| SW 装即用 | 无 | ✓ |
| 傻瓜式操作 | 开发者面，不触用户 | ✓ |

5 gate 全过。

---

## §6 plan-drift 5 分类自审（scout 防御）

| 分类 | 风险 | 防御 / 真值锚 |
|---|---|---|
| (a) API 不存在 | ✗ 无 API 调用 | — |
| (b) 路径假设错 | ⚠ rev 1 假设 STATUS §9.3 有 N-16 — **已发现并修正为 retro §3.3** | rev 3 §3.2 改 retro 真位 |
| (c) 测试 helper 误用 | ✗ 无测试 | — |
| (d) 实现细节 bug | ⚠ AC-2 grep `\.` 防匹配 `tools/ src/`；`-E` 防 BSD grep 不识别 `\|` | OK（CLAUDE.md §8） |
| (e) 参数签名 | ✗ 无参数 | — |

scout 已跑（grep tests.yml 真值 → 7 行白名单全可字面 grep；grep STATUS doc → N-13~N-17 不在 §9.3）。

---

## §7 PR-self §12 follow-up 候选

无预登候选。retro 阶段如发现：

- reviewer 误判（subagent 看到 RED-only commit 类）→ 登 §12
- 白名单 row 遗漏（grep 反例 / 真 CI step）→ 登 §12
- migration gap (EC-MIGRATE-GAP) → 登 §11 N-18 候选（retro §3.3 → STATUS doc 工艺）

---

## §8 commit 序列

**单 commit**（pure docs append，无 RED/GREEN 阶段分）：

```
feat(workflow): §11-N16 — plan verify 命令必抄 CI 白名单 + retro 闭环 (v2.37.16)

- CLAUDE.md ## Superpowers 插件工作流 新增 ### Plan 中 verify 命令必抄 CI 子节
  · 适用范围 + 主规则 + 7 行白名单（ruff/mypy×3/pytest×3） + narrowing-vs-override + sync 责任 + 例外
- docs/superpowers/reports/2026-05-18-v2-37-15-retro.md §3.3 N-16 row 附 closure 引用 v2.37.16
- docs/superpowers/specs/2026-05-18-n16-plan-verify-cmd-whitelist-design.md
- docs/superpowers/plans/2026-05-18-n16-plan-verify-cmd-whitelist.md
```

retro PR（merge 后单独）：

```
docs(retro): v2.37.16 retro — §11-N16 闭环 + 7 edge case 修
- docs/superpowers/reports/2026-05-18-v2-37-16-retro.md
```

---

## §9 估时

| 阶段 | 时间 |
|---|---|
| spec + plan 文件落盘 | 5 min |
| 实施（CLAUDE.md edit + retro cross-link） | 3 min |
| AC-1 ~ AC-5 grep 验证 | 2 min |
| PR + push + CI 等待 | 7-10 min |
| merge + tag v2.37.16 + GitHub Release | 3 min |
| **本 PR 合计** | **~20-25 min** |
| retro PR（merge 后）| ~5 min |

---

## §10 spec 演进与审查 audit log

| rev | 触发 | 关键修复 |
|---|---|---|
| rev 1 | brainstorming Q1-Q4 锁定 + 初设计 | 单 5 行白名单 + sync MAJOR + 单 commit + 单文件 scope（CLAUDE.md only） |
| rev 2 | 用户提"审查防止改完不如改前" → L4 cynical re-read | 修 7 处：C1 mypy 表数据漂移（无 broker 覆盖）/ C2 pytest 自相矛盾（白名单 vs AC-6）/ C17 §2 scope 与 §8 commit 序列冲突 / C5 MAJOR→INFO / C10 单/双 commit 摇摆 / C11 删 AC-6 全套件无关 / C20 retro 落点明示 |
| rev 3 | 用户提"再次审查，边界问题，是否闭环" → L5 edge-case hunter + Round 2 closure + L6 scout grep tests.yml + STATUS doc 真值 | **CRITICAL** EC-DRIFT-1：STATUS doc §9.3 不存在 N-16 → 改 update v2.37.15 retro §3.3（真位）+ EC-2 适用范围段（隔 §技术规范 line 49）+ EC-3 narrowing-vs-override 子条 + EC-9 table cell 去 `\` 转义 + EC-17 mypy 拆 broker/jury/render-QA literal 三行 + EC-18 去 line 65-70 改 step name + EC-15 含 quote 风格 + 新发现 EC-MIGRATE-GAP 登 retro §4 候选 N-18 |

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
