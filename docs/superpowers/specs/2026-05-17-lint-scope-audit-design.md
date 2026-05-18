# `tools/dev/lint_scope_audit.py` — pyproject lint scope drift 检测 设计

> **PR 类型**：feat（new dev tool；零行为改动 to existing code）
> **关联 §11 follow-up**：§11-N12（v2.37.13b retro §3.3 登记 — Task 0 scout per-file-ignores enumeration 系统化）
> **关联 retro**：`docs/superpowers/reports/2026-05-17-v2-37-13b-ruff-cleanup-p3-retro.md` §3.3
> **关联 brainstorming**：本 session — 3 节 §1/§2/§3 用户逐节 ok 确认
> **Spec rev**：rev 1.3（rev 1.0 首版 + rev 1.1 L1+L2 13 fix + rev 1.2 L3 edge-case 12 fix + **rev 1.3 L4 5 角色 + L5 闭环 dry-run 6 fix**：实测 B7/M10 候选 BLOCKER RESOLVED；2 MAJOR (M10 跨平台 smoke flake + M11 实施期 smoke fail 路径) + 4 MINOR (N8-N11 流程层 caveat/placeholder/graceful degrade)；rev 1.3 cumulative cascade = **31 fix**，超 P3 30 fix — N12 引入新算法+新工具+新 stripped config 机制比纯规则 cleanup 更复杂合理）

---

## 1. 摘要

新增 `tools/dev/lint_scope_audit.py` — 单一 helper script with `ruff` / `mypy` / `all` subcommands，检测 pyproject.toml 声明的 lint scope vs 真实代码 lint 状态间的 drift。

针对 v2.37.13b P3 实施期发现的"spec §3.1.D per-file-ignores glob 漏 2 个 path（`adapters/parts/*.py` + `cad/end_effector/*.py` 共 8 个 E402）→ Task 0 scout 手工 grep 抓出"工艺缺口，将该 enumeration 系统化为可复用工具。同时扩展到 mypy `[[tool.mypy.overrides]] ignore_errors=true` 模块 drift 检测（"该出列的没出"）。

| 改动 | 严重度 | 内容 | 估时 |
| --- | --- | --- | --- |
| **改动 1** | LOW | 新文件 `tools/dev/lint_scope_audit.py`（**~160 LOC**，单脚本 + argparse subcommands；rev 1.2 增量：`_make_mypy_stripped_config` tempfile 逻辑 ~20 行 + `_normalize_ruff_filename` abs→rel ~5 行 + cwd assertion ~5 行）+ `pyproject.toml [project.optional-dependencies] test` 加 `'tomli; python_version < "3.11"'` 一并 commit（rev 1.1 M2：tomli dep 是 script prerequisite，不单独 commit）| 55min |
| **改动 2** | LOW | 新文件 `tests/test_lint_scope_audit.py`（**~180 LOC**，15 unit + 2 real_subprocess + 1 mypy = **18 tests**；rev 1.2 +2 for B4/B6 helpers）| 35min |
| **改动 3** | LOW | retro §3.3 N12 标记 closed + 加 spec/PR/release 引用 | 5min |
| **改动 4** | — | 全套件 PASS + CI ruff-strict + mypy-strict 9/9 守门 | AC |

**N12 闭合预期**：retro §3.3 N12 行 → ✅ closed；下次 cleanup spec rev 1 的 plan Task 0 引用本工具入口。

---

## 2. 背景

### 2.1 N12 起源（来自 v2.37.13b retro §3.3）

> **§11-N10/N11/N12** v2.37.13b retro 新登记。
> **N12**：Task 0 scout 应枚举 per-file-ignores glob 候选文件数（P3 实施期发现 spec §3.1.D 漏 `adapters/parts` + `cad/end_effector` 共 8 个 E402 / 11 文件）。**推迟优先级**：下次 cleanup spec rev 1 起 Task 0。

P3 实施期 Task 0 scout 已有 `S-0.4` 步骤要求 "glob 覆盖率 = 100%（74/74）"，inline 抓到 2 个漏掉的 glob 并 inline 修复 spec。N12 = 把这种检查升级为可复用件，不只本 PR 用。

### 2.2 当前 baseline

- pyproject.toml `[tool.ruff.lint]`：12 select codes（F401/F541/F811/E401/F841/F405/F403/E731/E702/E402/E741/F821）+ **12** per-file-ignores globs（P3 锁定 — rev 1.1 校准：rev 1.0 误算 11，含 10 E402-only + 1 F403/F405-only (`cad/**/*.py`) + 1 F403/F405/E402 (`cad/lifting_platform/*.py`)）
- pyproject.toml `[[tool.mypy.overrides]]`：4 个 `ignore_errors=true` 模块（`adapters.solidworks.sw_detect` / `adapters.solidworks.sw_config_lists_cache` / `cad_paths` / `tools.contract_io`）+ 1 个 `strict=true` 模块（`adapters.solidworks.sw_config_broker`）
- ruff CI ruff-strict gate enforce 新违规
- mypy CI mypy-strict gate enforce 触动 strict scope 模块
- **未有** "声明面 vs 实际需要" 的 set diff 检测

### 2.3 drift 形态定义

**ruff 子命令** 抓两类：
- `over_permissive`：glob 覆盖了文件但**没有任何**该 code violation（声明面 > 真实需要 → 可窄化）
- `missing_glob`：文件有 violation 但**不在任何** per-file-ignores glob（spec 漏掉的 — P3 retro 那种）

**mypy 子命令** 抓一类：
- `dischargeable`：`ignore_errors=true` 模块今天跑 `mypy --strict -p <module>` exit 0 → 建议出列

---

## 3. 设计

### 3.1 入口

```
python tools/dev/lint_scope_audit.py ruff    # ruff drift
python tools/dev/lint_scope_audit.py mypy    # mypy drift
python tools/dev/lint_scope_audit.py all     # 顺序跑两者
```

**默认行为**：所有 subcommand `exit 0` informational mode（无 `--fail-on-drift` flag — 推迟到将来真触发 CI 化再加）。

**外部依赖**：仅 stdlib（py3.11+ 的 `tomllib`；py3.10 fallback 用 `tomli`，try/except import）。**rev 1.1 M2 fix**：本 PR 同步把 `tomli; python_version < "3.11"` 加入 `pyproject.toml [project.optional-dependencies] test`，确保 CI py3.10 matrix 能装到（CI tests.yml 已用 `pip install -e .[test]` 装 test extras，自动 cover）。本仓 `requires-python = ">=3.10"` 不变。

### 3.2 内部模块化（pure 函数 + 两处 subprocess 边界）

| 函数 | 职责 | 副作用 |
|---|---|---|
| `_load_pyproject() → dict` | tomllib 读 pyproject.toml | 文件读取 |
| `_load_ruff_config(pyproject) → tuple[dict[str, list[str]], list[str]]` | 解 `[tool.ruff.lint]` → `(globs_to_codes, select_codes)` | 纯 |
| `_load_mypy_overrides(pyproject) → list[str]` | 解 `[[tool.mypy.overrides]]` → ignore_errors=true 模块列表。**rev 1.2 M8 fix**：每个 override block 的 `module` 字段可为 str 或 list[str]，统一展开成 list[str] 后过滤 ignore_errors=true 块 | 纯 |
| `_run_ruff_json() → list[tuple[str, str]]` | `ruff check --config 'lint.per-file-ignores={}' --output-format=json .` — **关键**：inline 覆盖 per-file-ignores 为空 dict，强制 ruff 报告**所有真违规**；否则 P3 收官状态返 `[]` 导致 over_permissive 100% false positive（rev 1.1 B2 fix；实测 ruff 0.15.10 工作）。**rev 1.2 B4 fix**：JSON 输出 `filename` 字段是 absolute Windows path（实测 `D:\Work\...\file.py`），算法前先 `Path(fn).relative_to(Path.cwd()).as_posix()` normalize 成 `/`-分隔 relative path | subprocess + cwd 必须 = repo root |
| `_make_mypy_stripped_config(pyproject) → Path` | **rev 1.2 B6 fix（核心新增）**：写 tempfile pyproject 保留 `[tool.mypy]` 主段（`python_version` / `strict_optional` / `warn_redundant_casts` / `warn_unused_ignores` / `ignore_missing_imports` / `explicit_package_bases`）+ `strict=true` override（如有），**剥离所有 `ignore_errors=true` overrides**。返 tmp 文件路径，调用方负责清理 | tempfile I/O |
| `_run_mypy_strict_per_module(module, stripped_config_path) → bool` | `python -m mypy --strict --config-file <stripped_config> --disable-error-code=import-untyped -p <module>` exit 0?（**B6 关键**：用 stripped pyproject 跳过 `ignore_errors=true` 自抑制；`-p` flag 必需（rev 1.1 B3）；`--disable-error-code=import-untyped` 忽略外部库缺 type stub 的噪音（如本仓 pywin32 / win32com 无 stub，rev 1.2 M6 fix），让判定聚焦在模块**自身的**类型完整性；`cad_paths` 顶层模块靠 explicit_package_bases=true 解析；smoke test cwd 必须 = repo root（B5）防多副本歧义） | subprocess + cwd 必须 = repo root |
| `_compute_ruff_drift(globs_to_codes, select_codes, violations) → tuple[list, list]` | set diff 算 over_permissive + missing_glob | 纯 |
| `_compute_mypy_dischargeable(modules, per_module_results) → list[str]` | 过滤 OK 模块 | 纯 |
| `_render_ruff_report(over_permissive, missing_glob) → str` | 拼 markdown | 纯 |
| `_render_mypy_report(dischargeable, all_modules) → str` | 拼 markdown | 纯 |
| `main() → int` | argparse + dispatch；**rev 1.2 M9 fix**：`subparsers = parser.add_subparsers(required=True)` 显式 required，防 py3.7+ 默认非 required 引起无 subcommand silent exit 0 | I/O + sys.exit |

### 3.3 数据流

```
pyproject.toml
     ↓ tomllib.load
config dict
     ↓ _load_ruff_config / _load_mypy_overrides
{globs: codes} / [ignore modules]
     │
     │   mypy 子命令 only:
     │   ↓ _make_mypy_stripped_config  (rev 1.2 B6)
     │   tempfile.NamedTemporaryFile(suffix='.toml')
     │   <stripped pyproject 无 ignore_errors override>
     ↓
     ↓ _run_ruff_json (subprocess, ruff --config 'lint.per-file-ignores={}')
     ↓ _run_mypy_strict_per_module (subprocess, mypy --config-file <stripped>
                                              --disable-error-code=import-untyped
                                              -p <module>)
violations / per-module exit codes
     │   ruff 子命令: filename normalize abs → rel (rev 1.2 B4)
     ↓ _compute_*_drift (pure, set diff)
findings (over_permissive / missing_glob / dischargeable)
     ↓ _render_*_report
markdown
     ↓ print
stdout
     └ tempfile cleanup (try/finally)
```

### 3.4 关键设计决策

- **不修复**：脚本只读 + report，绝不动 pyproject.toml；user-curated config 由人决策；rev 1.2 mypy 子命令写 **tempfile** 是工作副本，**永不写回** pyproject.toml
- **glob 匹配**：手撸 `_match_glob(glob, path)` ~20 行 — normalize `\\` → `/` 后用 regex 转换：`/` 段间分隔字面量；`**` → `.*`（任意 dir level，含 0 段）；`*` → `[^/]*`（单段无 `/`）；`?` → `[^/]`。其余字符 `re.escape`。锚 `^` + `$`。`fnmatch.fnmatch` 不可用（不支持 `**`）。**零新外部 dep**；避免引入 `pathspec` 等库。R-1 由 §6 AC-13 smoke 断言"P3 收官状态 0 missing_glob"实测兜底（rev 1.1 M1 fix）。**rev 1.2 N6**：不支持 char class `[!abc]`（pyproject 实际未用，spec 显示限制）
- **mypy 子命令必慢路径**：N=4 模块 × ~5s ≈ 20s + tempfile 写一次 +<10ms；不并行（subprocess 资源 race + 输出顺序不可控）；不缓存（N 小且 mypy 自带 incremental cache）
- **mypy 子命令必绕过 pyproject self-suppress（rev 1.2 B6 fix 核心）**：直接调 `mypy --strict -p <m>` 会被 pyproject `[[tool.mypy.overrides]] ignore_errors=true` 自抑制返 0 → 100% false positive；必须 `_make_mypy_stripped_config` 写 tempfile 剥离 ignore_errors override 后 `mypy --config-file <stripped>` 才能拿到模块**自身**真错。`--disable-error-code=import-untyped` 同时抑制外部依赖（pywin32 / win32com）缺 stub 的噪音，让判定聚焦"模块自身的类型完整性"
- **Windows 路径 + cwd**（rev 1.2 B4/B5 fix）：ruff JSON 实测 `filename` = abs Windows path（如 `D:\Work\...\file.py`），必须 normalize 到 `/`-分隔 relative path 再 glob 匹配；同时 subprocess 调 ruff/mypy **必须设 `cwd=<repo root>`**（脚本可用 `Path(__file__).parent.parent.parent` 推断），防多个 cad_paths.py 副本（root + `.pytest_tmp_*/.../site-packages/cad_spec_gen/data/python_tools/cad_paths.py`）的 sys.path 解析歧义

### 3.5 报告格式（markdown stdout）

**报告日期**：所有 markdown 头部 `(YYYY-MM-DD)` 用 `datetime.now().date().isoformat()` 运行时渲染，不 hardcode（rev 1.1 N1 fix）。

**ruff 子命令**：
```markdown
# Lint scope audit — ruff ({date})

## 配置摘要
- select: 12 codes
- per-file-ignores: 12 globs

## ✅ over_permissive (N)
- `<glob>` covers `<code>` but no actual violations match this glob — consider narrowing
  - **rev 1.3 N8 caveat**：本工具用 `--config 'lint.per-file-ignores={}'` strip per-file-ignores 后跑 ruff 计算真违规集合再做 set diff。安全删除 glob 前请人工 verify：
    (1) 该 glob path pattern 下 future cleanup PR 不会再引入此 code 的 by-design 违规
    (2) 删 glob 后跑 `ruff check .` 仍 exit 0（无其他 path 误触发）
...

## ❌ missing_glob (N)
- `<file>:<line>` violates `<code>` but no per-file-ignores glob covers it — add to spec
...

## 结论
- ✅ 无 drift / ⚠ N 项 over_permissive / ❌ N 项 missing_glob
```

**mypy 子命令**：
```markdown
# Lint scope audit — mypy ({date})

## 配置摘要
- ignore_errors=true 模块：4 个

## ✅ dischargeable (N)
- `<module>` — stripped config + `mypy --strict -p <module>` exit 0；建议从 [[tool.mypy.overrides]] 出列
  - **rev 1.2 M7 caveat**：本工具用 stripped config（剥离 ignore_errors override）+ `--disable-error-code=import-untyped` 判定。出列前请人工手测原 pyproject 下 `mypy --strict -p <module>` 实质 clean（确认不依赖外部类型 stub 才能 pass），再 commit
...

## ⚠ still has errors (M)
- `<module>` — stripped config 下 N errors（如 `15 errors in sw_detect.py`），保留 ignore_errors=true 合理；首行 mypy stderr 显示具体规则

## 结论
- dischargeable: N 项 / still has errors: M 项 / 总计 N+M = 配置中 ignore_errors=true 模块数
```

**rev 1.2 N7 校准**：当前 4/4 模块在 stripped config 下都有真错（N=0, M=4），报告 still has errors 段会列出全部 4 模块名 + 各自 error 数。AC-3 "列出 4 模块"由本段满足，不依赖 dischargeable 非空。

**`all` subcommand 部分失败 fallback wording**（rev 1.1 M4 fix）：

- 若 `[tool.ruff]` 段缺失 → all 报告头部输出：
  ```markdown
  # Lint scope audit — all ({date})

  ## ⚠ ruff 段跳过
  pyproject.toml `[tool.ruff]` 段缺失 — ruff drift 检测不可用。
  
  ---
  
  # Lint scope audit — mypy ({date})
  ...（正常 mypy 段）
  ```
- 若 `[[tool.mypy.overrides]]` 无 ignore_errors=true 模块 → mypy 段头部输出 `## 结论 - 无 ignore_errors 模块`（保持 §4 表的 exit 0 行为）。两 段都 OK 时 `---` 分隔顺序拼接。

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
| `mypy --strict -p <module>` 跑挂（import error / 模块不存在 / 真有 type error）| subprocess 非 0 | 视为"still has errors" → 不出列；warn 到 stderr 含 stderr 头几行帮 debug | 0（继续）|
| `[tool.ruff.lint.per-file-ignores]` 段缺失但 `[tool.ruff]` 在 | `globs_to_codes = {}` | 跑正常，所有 violation 进 missing_glob | 0 |
| 真实 ruff 0 violation 且无 over_permissive | findings 全空 | markdown 显示"✅ 无 drift" | 0 |
| **tempfile 创建失败**（rev 1.2 B6）| `OSError`（disk full / permission）| stderr 报错 + 终止；不退路本调用 | 5 |
| **tempfile cleanup 失败**（rev 1.2 B6）| `try/finally` 内捕获 unlink 失败 | warn 到 stderr 但不阻塞主流程 | 0 |
| **mypy `--disable-error-code=import-untyped` 旧版不支持**（mypy < 0.991）| subprocess stderr "unknown option" | warn + 不带此 flag retry 一次；若仍 fail → 视 module 为 "still has errors" | 0（continue）|
| **cwd 不在 repo root**（rev 1.2 B5）| 启动检测 `(cwd / "pyproject.toml").exists()` | 自动 cd 到 `Path(__file__).parent.parent.parent`；若仍找不到 → stderr 报错 + 终止 | 2 |
| **多个 `cad_paths.py` 副本**（rev 1.2 B5）| mypy `-p` 解析靠 sys.path + explicit_package_bases=true | cwd=repo root + 显式 PYTHONPATH 排除 `.pytest_tmp_*` 路径；smoke test 同样保障 | — |
| **ruff/mypy 输出非预期 schema**（rev 1.3 N11 graceful degrade）| `json.JSONDecodeError` 或 mypy stderr 不可解析 | stderr 提示 "ruff/mypy version 不匹配 / 输出 schema 漂移；本工具 pin ruff 0.15.x + mypy 1.x 验证" + 终止 | 4 |

---

## 5. 测试

**新文件**：`tests/test_lint_scope_audit.py`（~150 LOC）

### 5.1 Unit tests（核心算法，13 个 — 全离线、毫秒级；rev 1.2 +2 for B6/B4）

| Test | 验证 |
|---|---|
| `test_load_ruff_config_parses_globs_and_select` | 给 inline TOML 字符串 → 返 `(globs_to_codes, select_codes)` 正确 |
| `test_load_ruff_config_missing_section_returns_none` | 缺 `[tool.ruff]` → None（按设计契约）|
| `test_match_globs_handles_double_star` | `cad/**/*.py` 匹配 `cad/end_effector/foo.py` ✅、`cad/foo.py` ✅（0 dir level）、`adapters/parts/foo.py` ❌ |
| `test_match_globs_normalizes_windows_paths` | 输入 `cad\end_effector\foo.py` → 正确匹配 `cad/**/*.py` |
| `test_normalize_ruff_filename_strips_absolute_prefix` | **rev 1.2 B4**：输入 `D:\Work\cad-spec-gen\adapters\parts\foo.py` + cwd=`D:\Work\cad-spec-gen` → 返 `adapters/parts/foo.py` |
| `test_compute_ruff_drift_over_permissive` | glob 覆盖 file 但无 violation → 进 over_permissive |
| `test_compute_ruff_drift_missing_glob` | file 有 violation 但无 glob → 进 missing_glob |
| `test_compute_ruff_drift_perfect_match` | glob 与 violation 完全对齐 → 两类皆空 |
| `test_load_mypy_overrides_filters_ignore_errors_true` | 混合 strict=true + ignore_errors=true → 只返 ignore_errors=true |
| `test_load_mypy_overrides_handles_module_list_or_string` | `module = "x"` 和 `module = ["x","y"]` 两种 TOML 形式都解 |
| `test_make_mypy_stripped_config_removes_ignore_errors_blocks` | **rev 1.2 B6**：输入完整 pyproject dict → tmp 文件 contents 不含 `ignore_errors = true` 行，保留 `[tool.mypy]` 主段 + strict=true overrides |
| `test_render_ruff_report_includes_both_sections` | findings 含两类 → markdown 含两标题 |
| `test_render_ruff_report_empty_findings_shows_ok` | findings 全空 → 显示"✅ 无 drift" |

### 5.2 Smoke tests（real subprocess，3 个）+ error path tests（mock，2 个）

| Test | 类型 | 验证 | marker |
|---|---|---|---|
| `test_ruff_subcommand_against_current_pyproject` | smoke | `subprocess.run([sys.executable, script, "ruff"], cwd=REPO_ROOT)` → exit 0 + stdout 含 markdown 头 | `real_subprocess` |
| `test_mypy_subcommand_against_current_pyproject` | smoke | 同上 mypy → **只断言** 4 模块名都出现在报告中（**rev 1.3 M10 fix**：不断言具体 error 数 — Linux CI 上 pywin32 不装时 `ignore_missing_imports=true` + `--strict` 组合会让 `import` 变 Any 然后产生 `no-untyped-call` 错（非 import-untyped/not-found 类），error 数跨平台差异大；只断"4 模块在报告 still has errors 段或 dischargeable 段任一"避免 flake；rev 1.2 N7 校准：当前 stripped config 4/4 仍有真错，dischargeable 列表 = 空）| `mypy` + `real_subprocess` |
| `test_all_subcommand_runs_both` | smoke | 两段都出现 | `real_subprocess` |
| `test_ruff_missing_executable_exits_3` | unit | mock `shutil.which("ruff") → None` → exit 3 | （无 marker）|
| `test_pyproject_missing_section_exits_2` | unit | tmp_path 写残缺 pyproject → exit 2 | （无 marker）|

**总计 18 个**（rev 1.2 +2 from 16）：unit 15（§5.1 13 + §5.2 后 2）+ smoke real_subprocess 2（§5.2 前 2 不含 mypy）+ smoke mypy 1（§5.2 第 2 含 mypy marker）

**rev 1.2 M5 fix**：smoke test 用 `sys.executable` 不 hardcode `"python"`（PATH 不一定有；CI matrix 各 Python 版本隔离 `.venv`）。
**rev 1.2 B5 fix**：smoke test 显式 `cwd=REPO_ROOT`（`REPO_ROOT = Path(__file__).parent.parent`，pytest test dir 是 `tests/`），防多 `cad_paths.py` 副本歧义。

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
| **AC-3** | mypy 子命令对当前 pyproject 跑通 | `python tools/dev/lint_scope_audit.py mypy` | exit 0 + 列出 4 模块（dischargeable=0 是 rev 1.2 实测预期：stripped config + `--disable-error-code=import-untyped` 下 4 模块都仍有自身 type error，N7 校准）| commit 1 后 |
| **AC-4** | all 子命令两段都跑 | `python tools/dev/lint_scope_audit.py all` | exit 0 + 两段 markdown | commit 1 后 |
| **AC-5** | unit tests 全 PASS | `pytest tests/test_lint_scope_audit.py -m "not real_subprocess and not mypy"` | **15 passed**（§5.1 13 + §5.2 后 2；rev 1.2 +2 for B4/B6 helpers）| commit 2 后 |
| **AC-6** | real_subprocess smoke 全 PASS | `pytest tests/test_lint_scope_audit.py -m "real_subprocess and not mypy"` | **2 passed** | commit 2 后 |
| **AC-7** | mypy smoke 跑通 | `pytest tests/test_lint_scope_audit.py -m "mypy"` | **1 passed** | commit 2 后 |
| **AC-8** | 全套件 baseline +18 | `pytest` | ≥3241 + 18 PASS（15 unit + 2 real_subprocess + 1 mypy = 18）| commit 2 后 |
| **AC-9** | ruff-strict CI gate pass | `.github/workflows/tests.yml` ruff-strict job | exit 0 | PR 后 |
| **AC-10** | mypy-strict CI gate pass | `.github/workflows/tests.yml` mypy-strict job | exit 0（无新 strict 模块加入）| PR 后 |
| **AC-11** | 新脚本本身无 ruff 违规（CI ruff-strict 自动 cover）+ 本地手测 mypy --strict clean（**非 CI gate**，rev 1.1 M3 fix：现 CI mypy-strict job 由 `[[tool.mypy.overrides]] strict=true` 块决定 file 列表，仅 `sw_config_broker`；`tools/dev/lint_scope_audit.py` 不进 mypy-strict CI scope 是 by-design — 渐进式 typing 政策不应因新 dev tool 扩张 strict scope；commit 1 实施时本地 `mypy --strict tools/dev/lint_scope_audit.py` 应 exit 0，AC 用本地手测验，不进 CI gate）| `ruff check tools/dev/lint_scope_audit.py`（CI）+ 本地 `mypy --strict tools/dev/lint_scope_audit.py` | ruff CI exit 0 + 本地 mypy exit 0 | commit 1 后 |
| **AC-12** | retro §3.3 N12 标记改 closed | git diff retro doc | N12 行 → ✅ + 加 spec/PR/release 引用 | commit 3 后 |
| **AC-13** | 当前 pyproject 实测无 ruff drift | `python tools/dev/lint_scope_audit.py ruff` | stdout 含 "✅ 无 drift" 或仅 over_permissive（不应 missing_glob，因 P3 已收官）| smoke test 锚定 |

---

## 7. 风险与缓解

| ID | 风险 | 级别 | 缓解 |
|---|---|---|---|
| **R-1** | 手撸 glob 匹配语义与 ruff 不一致（双星 / 多 segment）→ 误报 | MED | smoke test 跑真 pyproject 断言"P3 收官状态 0 missing_glob"实测兜底；**rev 1.1 N2 fix**：同 smoke 加断言 over_permissive 数 ≤ 12 globs（合理上界，防 B2 类 100% false positive 回归）；若误报 → unit test 增量 case + 修 `_match_glob` regex 模式；不引入 `pathspec` dep |
| **R-2** | mypy ignore_errors 模块的 dischargeable 列表为空 / 非空均合理 | LOW | **rev 1.2 校准**（rev 1.1 误判已修）：rev 1.1 实测"sw_detect mypy --strict clean"是被 pyproject `ignore_errors=true` 自抑制的假象（B6 真因）；rev 1.2 stripped config 实测下 4/4 模块全有真错（sw_detect 15 errors / 其余类似）→ 首次运行 dischargeable = 空。这是合理状态 — 当前模块确实仍是历史债。空列表是有效报告 |
| **R-3** | tomllib 在 py3.10 缺失 | LOW | try/except import + tomli fallback；CI 已 test py3.10/3.11/3.12 |
| **R-4** | ruff JSON 输出格式版本漂移 | LOW | pin ruff version 与本仓既有约定一致；本仓 `feedback_preflight_mirror_ci.md` 教训已 cover |
| **R-5** | 脚本本身 ruff/mypy 违规导致 PR CI fail | LOW | AC-11 commit 1 后立验；TDD 顺序 unit 先 RED 自然驱动接口设计干净 |
| **R-6** | smoke test 在 CI 跑慢（mypy --strict × 4 模块 ~20s）| LOW | 仅加 +20s 到现有 windows-latest job；总 wall < 8min 可接受 |

---

## 8. 提交序

```
Commit 1 — feat(dev-tools): tools/dev/lint_scope_audit.py + pyproject tomli dep
  + new script 单 file ~160 LOC + argparse subcommands (ruff/mypy/all)
  + ruff: --config 'lint.per-file-ignores={}' inline strip (rev 1.1 B2 fix)
        + filename abs→rel normalize (rev 1.2 B4 fix)
        + over_permissive/missing_glob 两类 drift
  + mypy: _make_mypy_stripped_config tempfile 剥离 ignore_errors override (rev 1.2 B6 fix)
        + --disable-error-code=import-untyped 忽略外部库 stub 噪音 (rev 1.2 M6 fix)
        + mypy --config-file <stripped> --strict -p <dotted> flag (rev 1.1 B3 fix)
        + ignore_errors=true dischargeable
  + cwd 显式 = repo root + 多 cad_paths.py 副本 disambiguation (rev 1.2 B5 fix)
  + _match_glob regex impl: ** → .* / * → [^/]* (rev 1.1 M1 fix)
  + argparse subparsers required=True (rev 1.2 M9 fix)
  + _load_mypy_overrides 处理 module 字段两形态 (rev 1.2 M8 fix)
  + pyproject.toml [project.optional-dependencies] test 加 tomli; python_version<"3.11" (rev 1.1 M2 fix)
  + 默认 informational mode (exit 0)
  + 闭合 §11-N12

Commit 2 — test(dev-tools): tests/test_lint_scope_audit.py
  + 15 unit + 2 real_subprocess + 1 mypy = 18 tests (rev 1.2 +2 for B4/B6)
  + smoke test 用 sys.executable + cwd=REPO_ROOT (rev 1.2 M5+B5)
  + 验证 pyproject 解析 + glob 匹配 + drift 算法 + 报告渲染 + 错误路径

Commit 3 — docs(retro): v2.37.13b retro §3.3 N12 → closed
  + 引用 spec / plan / PR # / merge SHA / release tag

实施期 smoke fail 处理路径（rev 1.3 M11 fix）:
  - commit 1 后 AC-2/3/4 跑 smoke 期间如 ruff missing_glob ≠ 0
    → implementer 派单回主 agent；主 agent 三选一决策：
      (a) inline 补 pyproject [tool.ruff.lint.per-file-ignores] glob
          （新增 path 是 by-design 的 sys.path/import 模式）
      (b) 升级 spec rev 1.4 加新 finding
      (c) 终止 commit 1，让 user 决策
  - mypy 子命令 smoke fail（4 模块名缺）一般不可能；如真发生 → spec rev
    1.4 升级或回查 pyproject [[tool.mypy.overrides]] 解析逻辑
  - 主 agent 决策记录追加到 plan retro，不进 spec
```

---

## 9. 复用入口（下次 cleanup spec 写法模板）

下次任何 cleanup spec（ruff / mypy / future lint）rev 1 的 plan Task 0 必含一行：

```markdown
## Task 0: Scout
- [ ] **S-0.X.Y** 跑 `python tools/dev/lint_scope_audit.py <ruff|mypy>` → 输出贴到 `tmp/{spec}_scout_report.md`
  - **预期 baseline**（rev 1.3 N10 校准）：
    - **ruff**: 0 missing_glob（P3 收官状态全 cover）+ over_permissive 列表可非空（合法 — 需 spec 决策"是否窄化 glob"）
    - **mypy**: dischargeable 列表为空（当前 4/4 历史债模块在 stripped config 下仍有真错）+ still has errors 列表 = 4 模块名（rev 1.2 N7 实测）
  - **非预期**（如 missing_glob 突现 ≠ 0 / dischargeable 出现新模块）：spec inline 修补 per-file-ignores 或 ignore_errors 列表，无升级（5 层审查 inline fix 工艺）
```

---

## 10. §11-N12 闭合判定

- ✅ helper script `tools/dev/lint_scope_audit.py` 落地
- ✅ 测试覆盖 15 unit + 3 smoke = 18（rev 1.2 校准）
- ✅ CI ruff-strict gate 守门脚本本身（mypy-strict 非 gate，本地手测，rev 1.1 M3）
- ✅ retro §3.3 N12 标记改 closed + 加 spec/PR/release 引用
- ✅ 文档复用入口（§9）

**rev 1.3 N9 closure 占位说明**：
- PR # / merge SHA / release tag 三个占位由实施期填入（commit 3 时已知）
- release tag 命名由 user 决策；不属 spec scope；按本仓 v2.25+ tag-only release 模式，候选 `v2.37.14`（patch 级 — N12 是 internal dev tool 不破坏 user-facing 行为）或 `v2.37.13c`（cleanup 子号续接）
- 若该 PR merge 后选择**不发 tag**（视为内部工艺改进），则 release 行写 "internal, no tag"

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
