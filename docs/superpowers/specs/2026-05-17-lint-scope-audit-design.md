# `tools/dev/lint_scope_audit.py` — pyproject lint scope drift 检测 设计

> **PR 类型**：feat（new dev tool；零行为改动 to existing code）
> **关联 §11 follow-up**：§11-N12（v2.37.13b retro §3.3 登记 — Task 0 scout per-file-ignores enumeration 系统化）
> **关联 retro**：`docs/superpowers/reports/2026-05-17-v2-37-13b-ruff-cleanup-p3-retro.md` §3.3
> **关联 brainstorming**：本 session — 3 节 §1/§2/§3 用户逐节 ok 确认
> **Spec rev**：rev 1.0（首版）

---

## 1. 摘要

新增 `tools/dev/lint_scope_audit.py` — 单一 helper script with `ruff` / `mypy` / `all` subcommands，检测 pyproject.toml 声明的 lint scope vs 真实代码 lint 状态间的 drift。

针对 v2.37.13b P3 实施期发现的"spec §3.1.D per-file-ignores glob 漏 2 个 path（`adapters/parts/*.py` + `cad/end_effector/*.py` 共 8 个 E402）→ Task 0 scout 手工 grep 抓出"工艺缺口，将该 enumeration 系统化为可复用工具。同时扩展到 mypy `[[tool.mypy.overrides]] ignore_errors=true` 模块 drift 检测（"该出列的没出"）。

| 改动 | 严重度 | 内容 | 估时 |
| --- | --- | --- | --- |
| **改动 1** | LOW | 新文件 `tools/dev/lint_scope_audit.py`（~120 LOC，单脚本 + argparse subcommands） | 40min |
| **改动 2** | LOW | 新文件 `tests/test_lint_scope_audit.py`（~150 LOC，11 unit + 5 smoke） | 30min |
| **改动 3** | LOW | retro §3.3 N12 标记 closed + 加 spec/PR 引用 | 5min |
| **改动 4** | — | 全套件 PASS + CI ruff-strict + mypy-strict 9/9 守门 | AC |

**N12 闭合预期**：retro §3.3 N12 行 → ✅ closed；下次 cleanup spec rev 1 的 plan Task 0 引用本工具入口。

---

## 2. 背景

### 2.1 N12 起源（来自 v2.37.13b retro §3.3）

> **§11-N10/N11/N12** v2.37.13b retro 新登记。
> **N12**：Task 0 scout 应枚举 per-file-ignores glob 候选文件数（P3 实施期发现 spec §3.1.D 漏 `adapters/parts` + `cad/end_effector` 共 8 个 E402 / 11 文件）。**推迟优先级**：下次 cleanup spec rev 1 起 Task 0。

P3 实施期 Task 0 scout 已有 `S-0.4` 步骤要求 "glob 覆盖率 = 100%（74/74）"，inline 抓到 2 个漏掉的 glob 并 inline 修复 spec。N12 = 把这种检查升级为可复用件，不只本 PR 用。

### 2.2 当前 baseline

- pyproject.toml `[tool.ruff.lint]`：12 select codes（F401/F541/F811/E401/F841/F405/F403/E731/E702/E402/E741/F821）+ 11 per-file-ignores globs（P3 锁定）
- pyproject.toml `[[tool.mypy.overrides]]`：4 个 `ignore_errors=true` 模块（`adapters.solidworks.sw_detect` / `adapters.solidworks.sw_config_lists_cache` / `cad_paths` / `tools.contract_io`）+ 1 个 `strict=true` 模块（`adapters.solidworks.sw_config_broker`）
- ruff CI ruff-strict gate enforce 新违规
- mypy CI mypy-strict gate enforce 触动 strict scope 模块
- **未有** "声明面 vs 实际需要" 的 set diff 检测

### 2.3 drift 形态定义

**ruff 子命令** 抓两类：
- `over_permissive`：glob 覆盖了文件但**没有任何**该 code violation（声明面 > 真实需要 → 可窄化）
- `missing_glob`：文件有 violation 但**不在任何** per-file-ignores glob（spec 漏掉的 — P3 retro 那种）

**mypy 子命令** 抓一类：
- `dischargeable`：`ignore_errors=true` 模块今天跑 `mypy --strict <module>` exit 0 → 建议出列

---

## 3. 设计

### 3.1 入口

```
python tools/dev/lint_scope_audit.py ruff    # ruff drift
python tools/dev/lint_scope_audit.py mypy    # mypy drift
python tools/dev/lint_scope_audit.py all     # 顺序跑两者
```

**默认行为**：所有 subcommand `exit 0` informational mode（无 `--fail-on-drift` flag — 推迟到将来真触发 CI 化再加）。

**外部依赖**：仅 stdlib（py3.11+ 的 `tomllib`；py3.10 fallback 用 `tomli`，try/except import）。**零新 pip dep**。

### 3.2 内部模块化（pure 函数 + 两处 subprocess 边界）

| 函数 | 职责 | 副作用 |
|---|---|---|
| `_load_pyproject() → dict` | tomllib 读 pyproject.toml | 文件读取 |
| `_load_ruff_config(pyproject) → tuple[dict[str, list[str]], list[str]]` | 解 `[tool.ruff.lint]` → `(globs_to_codes, select_codes)` | 纯 |
| `_load_mypy_overrides(pyproject) → list[str]` | 解 `[[tool.mypy.overrides]]` → ignore_errors=true 模块列表 | 纯 |
| `_run_ruff_json() → list[tuple[str, str]]` | `ruff check --output-format=json .` | subprocess |
| `_run_mypy_strict_per_module(module) → bool` | `python -m mypy --strict <module>` exit 0? | subprocess |
| `_compute_ruff_drift(globs_to_codes, select_codes, violations) → tuple[list, list]` | set diff 算 over_permissive + missing_glob | 纯 |
| `_compute_mypy_dischargeable(modules, per_module_results) → list[str]` | 过滤 OK 模块 | 纯 |
| `_render_ruff_report(over_permissive, missing_glob) → str` | 拼 markdown | 纯 |
| `_render_mypy_report(dischargeable, all_modules) → str` | 拼 markdown | 纯 |
| `main() → int` | argparse + dispatch | I/O + sys.exit |

### 3.3 数据流

```
pyproject.toml
     ↓ tomllib.load
config dict
     ↓ _load_ruff_config / _load_mypy_overrides
{globs: codes} / [ignore modules]
     ↓ _run_ruff_json / _run_mypy_strict_per_module (subprocess)
violations / per-module exit codes
     ↓ _compute_*_drift (pure)
findings (over_permissive / missing_glob / dischargeable)
     ↓ _render_*_report
markdown
     ↓ print
stdout
```

### 3.4 关键设计决策

- **不修复**：脚本只读 + report，绝不动 pyproject.toml；user-curated config 由人决策
- **glob 匹配**：手撸 `_match_glob(glob, path)` ~20 行 — normalize `\\` → `/` + 把 `**` 视为"零或多段 path segment"（regex 模式 `[\w\-./]*` 经 `re.escape` 处理）。**零新外部 dep**；避免引入 `pathspec` 等库。R-1 由 §6 AC-13 smoke 断言"P3 收官状态 0 missing_glob"实测兜底
- **mypy 子命令必慢路径**：N=4 模块 × ~5s ≈ 20s；不并行（subprocess 资源 race + 输出顺序不可控）；不缓存（N 小且 mypy 自带 incremental cache）
- **Windows 路径**：subprocess 调用的 `ruff check` 输出 JSON 内 `filename` 字段使用 Windows `\` 或 POSIX `/` 取决于 ruff version；统一 `path.replace("\\", "/")` 后匹配

### 3.5 报告格式（markdown stdout）

**ruff 子命令**：
```markdown
# Lint scope audit — ruff (2026-05-17)

## 配置摘要
- select: 12 codes
- per-file-ignores: 11 globs

## ✅ over_permissive (N)
- `<glob>` covers `<code>` but no actual violations match this glob — consider narrowing
...

## ❌ missing_glob (N)
- `<file>:<line>` violates `<code>` but no per-file-ignores glob covers it — add to spec
...

## 结论
- ✅ 无 drift / ⚠ N 项 over_permissive / ❌ N 项 missing_glob
```

**mypy 子命令**：
```markdown
# Lint scope audit — mypy (2026-05-17)

## 配置摘要
- ignore_errors=true 模块：4 个

## ✅ dischargeable (N)
- `<module>` — `mypy --strict` exit 0；建议从 [[tool.mypy.overrides]] 出列
...

## 结论
- 无可出列 / N 项可出列
```

---

## 4. 错误处理与边界条件

| 场景 | 检测 | 处理 | exit code |
|---|---|---|---|
| `pyproject.toml` 不存在 | `Path.exists()` | stderr 报错 + 终止 | 2 |
| `pyproject.toml` 解析失败 | `tomllib.TOMLDecodeError` | stderr 含 lineno + 终止 | 2 |
| `[tool.ruff]` 段缺失（ruff subcommand）| `pyproject.get("tool",{}).get("ruff")` 为 None | 报"本项目未启用 ruff 配置" + 终止 | 2 |
| `[tool.ruff]` 段缺失（all subcommand）| 同 | 跳过 ruff 段继续 mypy | 0 |
| `[[tool.mypy.overrides]]` 无 ignore_errors=true | 过滤后空列表 | 报"无 ignore_errors 模块" + exit 0 | 0 |
| `ruff` 不在 PATH | `shutil.which("ruff") is None` | stderr 报错 + 终止 | 3 |
| `mypy` 不在 PATH | 同 | 同 | 3 |
| `ruff check` 输出非 JSON（version 漂移）| `json.JSONDecodeError` | stderr + 终止 | 4 |
| `mypy --strict <module>` 跑挂（import error / 模块不存在）| subprocess 非 0 且 stderr 显示 import error | 视为"still has errors" → 不出列；warn 到 stderr | 0（继续）|
| `[tool.ruff.lint.per-file-ignores]` 段缺失但 `[tool.ruff]` 在 | `globs_to_codes = {}` | 跑正常，所有 violation 进 missing_glob | 0 |
| 真实 ruff 0 violation 且无 over_permissive | findings 全空 | markdown 显示"✅ 无 drift" | 0 |

---

## 5. 测试

**新文件**：`tests/test_lint_scope_audit.py`（~150 LOC）

### 5.1 Unit tests（核心算法，11 个 — 全离线、毫秒级）

| Test | 验证 |
|---|---|
| `test_load_ruff_config_parses_globs_and_select` | 给 inline TOML 字符串 → 返 `(globs_to_codes, select_codes)` 正确 |
| `test_load_ruff_config_missing_section_returns_none` | 缺 `[tool.ruff]` → None（按设计契约）|
| `test_match_globs_handles_double_star` | `cad/**/*.py` 匹配 `cad/end_effector/foo.py` ✅、`adapters/parts/foo.py` ❌ |
| `test_match_globs_normalizes_windows_paths` | 输入 `cad\end_effector\foo.py` → 正确匹配 `cad/**/*.py` |
| `test_compute_ruff_drift_over_permissive` | glob 覆盖 file 但无 violation → 进 over_permissive |
| `test_compute_ruff_drift_missing_glob` | file 有 violation 但无 glob → 进 missing_glob |
| `test_compute_ruff_drift_perfect_match` | glob 与 violation 完全对齐 → 两类皆空 |
| `test_load_mypy_overrides_filters_ignore_errors_true` | 混合 strict=true + ignore_errors=true → 只返 ignore_errors=true |
| `test_load_mypy_overrides_handles_module_list_or_string` | `module = "x"` 和 `module = ["x","y"]` 两种 TOML 形式都解 |
| `test_render_ruff_report_includes_both_sections` | findings 含两类 → markdown 含两标题 |
| `test_render_ruff_report_empty_findings_shows_ok` | findings 全空 → 显示"✅ 无 drift" |

### 5.2 Smoke tests（real subprocess，3 个）+ error path tests（mock，2 个）

| Test | 类型 | 验证 | marker |
|---|---|---|---|
| `test_ruff_subcommand_against_current_pyproject` | smoke | `subprocess.run([python, script, "ruff"])` → exit 0 + stdout 含 markdown 头 | `real_subprocess` |
| `test_mypy_subcommand_against_current_pyproject` | smoke | 同上 mypy → 含 4 模块名 | `mypy` + `real_subprocess` |
| `test_all_subcommand_runs_both` | smoke | 两段都出现 | `real_subprocess` |
| `test_ruff_missing_executable_exits_3` | unit | mock `shutil.which("ruff") → None` → exit 3 | （无 marker）|
| `test_pyproject_missing_section_exits_2` | unit | tmp_path 写残缺 pyproject → exit 2 | （无 marker）|

**总计 16 个**：unit 13（§5.1 11 + §5.2 后 2）+ smoke real_subprocess 2（§5.2 前 2 不含 mypy）+ smoke mypy 1（§5.2 第 2 含 mypy marker）

### 5.3 TDD 顺序

RED → GREEN → REFACTOR：
1. 11 unit 先全 RED（脚本未实现）
2. 实现纯函数 → unit GREEN
3. 5 smoke RED
4. 实现 `main()` + argparse → smoke GREEN
5. REFACTOR：抽 `_render_findings_section()` 通用 helper（DRY）

### 5.4 CI 影响

**零变更**：
- 不加新 CI job
- unit + smoke 跑在 `tests.yml` 默认 test matrix
- baseline 增量：**+16 tests**（3241 → 3257）
- ruff-strict / mypy-strict CI gate 自动 cover 新脚本本身（脚本需 ruff/mypy strict clean）

---

## 6. AC（acceptance criteria）

| ID | 验证 | 工具 | 阈值 | 时机 |
|---|---|---|---|---|
| **AC-1** | 新脚本可执行 | `python tools/dev/lint_scope_audit.py --help` | exit 0 + 列 3 subcommands | commit 1 后 |
| **AC-2** | ruff 子命令对当前 pyproject 跑通 | `python tools/dev/lint_scope_audit.py ruff` | exit 0 + markdown 头 | commit 1 后 |
| **AC-3** | mypy 子命令对当前 pyproject 跑通 | `python tools/dev/lint_scope_audit.py mypy` | exit 0 + 列出 4 模块 | commit 1 后 |
| **AC-4** | all 子命令两段都跑 | `python tools/dev/lint_scope_audit.py all` | exit 0 + 两段 markdown | commit 1 后 |
| **AC-5** | unit tests 全 PASS | `pytest tests/test_lint_scope_audit.py -m "not real_subprocess and not mypy"` | **13 passed**（§5.1 11 + §5.2 后 2）| commit 2 后 |
| **AC-6** | real_subprocess smoke 全 PASS | `pytest tests/test_lint_scope_audit.py -m "real_subprocess and not mypy"` | **2 passed** | commit 2 后 |
| **AC-7** | mypy smoke 跑通 | `pytest tests/test_lint_scope_audit.py -m "mypy"` | **1 passed** | commit 2 后 |
| **AC-8** | 全套件 baseline +16 | `pytest` | ≥3241 + 16 PASS（13 unit + 2 real_subprocess + 1 mypy = 16）| commit 2 后 |
| **AC-9** | ruff-strict CI gate pass | `.github/workflows/tests.yml` ruff-strict job | exit 0 | PR 后 |
| **AC-10** | mypy-strict CI gate pass | `.github/workflows/tests.yml` mypy-strict job | exit 0（无新 strict 模块加入）| PR 后 |
| **AC-11** | 新脚本本身无 ruff/mypy 违规 | `ruff check tools/dev/lint_scope_audit.py && mypy --strict tools/dev/lint_scope_audit.py` | 都 exit 0 | commit 1 后 |
| **AC-12** | retro §3.3 N12 标记改 closed | git diff retro doc | N12 行 → ✅ + 加 spec/PR/release 引用 | commit 3 后 |
| **AC-13** | 当前 pyproject 实测无 ruff drift | `python tools/dev/lint_scope_audit.py ruff` | stdout 含 "✅ 无 drift" 或仅 over_permissive（不应 missing_glob，因 P3 已收官）| smoke test 锚定 |

---

## 7. 风险与缓解

| ID | 风险 | 级别 | 缓解 |
|---|---|---|---|
| **R-1** | 手撸 glob 匹配语义与 ruff 不一致（双星 / 多 segment）→ 误报 | MED | smoke test 跑真 pyproject 断言"P3 收官状态 0 missing_glob"实测兜底；若误报 → unit test 增量 case + 修 `_match_glob` regex 模式；不引入 `pathspec` dep |
| **R-2** | mypy ignore_errors 模块今天可能确实仍有 type error → dischargeable 列表空 | LOW | 是预期结果（"渐进式 typing 政策"，由业务节奏决定何时出列）；空列表也是有效报告 |
| **R-3** | tomllib 在 py3.10 缺失 | LOW | try/except import + tomli fallback；CI 已 test py3.10/3.11/3.12 |
| **R-4** | ruff JSON 输出格式版本漂移 | LOW | pin ruff version 与本仓既有约定一致；本仓 `feedback_preflight_mirror_ci.md` 教训已 cover |
| **R-5** | 脚本本身 ruff/mypy 违规导致 PR CI fail | LOW | AC-11 commit 1 后立验；TDD 顺序 unit 先 RED 自然驱动接口设计干净 |
| **R-6** | smoke test 在 CI 跑慢（mypy --strict × 4 模块 ~20s）| LOW | 仅加 +20s 到现有 windows-latest job；总 wall < 8min 可接受 |

---

## 8. 提交序

```
Commit 1 — feat(dev-tools): tools/dev/lint_scope_audit.py
  + new script 单 file ~120 LOC + argparse subcommands (ruff/mypy/all)
  + ruff: per-file-ignores over_permissive + missing_glob 两类 drift
  + mypy: [[tool.mypy.overrides]] ignore_errors=true dischargeable
  + 默认 informational mode (exit 0)
  + 闭合 §11-N12

Commit 2 — test(dev-tools): tests/test_lint_scope_audit.py
  + 11 unit + 5 smoke
  + 验证 pyproject 解析 + glob 匹配 + drift 算法 + 报告渲染

Commit 3 — docs(retro): v2.37.13b retro §3.3 N12 → closed
  + 引用 spec / plan / PR # / merge SHA / release tag
```

---

## 9. 复用入口（下次 cleanup spec 写法模板）

下次任何 cleanup spec（ruff / mypy / future lint）rev 1 的 plan Task 0 必含一行：

```markdown
## Task 0: Scout
- [ ] **S-0.X.Y** 跑 `python tools/dev/lint_scope_audit.py <ruff|mypy>` → 输出贴到 `tmp/{spec}_scout_report.md`
  - **预期 baseline**：0 missing_glob / 0 dischargeable（按 P3 收官状态）
  - **非 0**：spec inline 修补 per-file-ignores 或 ignore_errors 列表，无升级
```

---

## 10. §11-N12 闭合判定

- ✅ helper script `tools/dev/lint_scope_audit.py` 落地
- ✅ 测试覆盖 11 unit + 5 smoke
- ✅ CI ruff-strict + mypy-strict gate 守门脚本本身
- ✅ retro §3.3 N12 标记改 closed + 加 spec/PR/release 引用
- ✅ 文档复用入口（§9）

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
