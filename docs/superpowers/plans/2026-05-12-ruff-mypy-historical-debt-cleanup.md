# ruff/mypy 历史债 cleanup — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 清理一个已选定的 ruff/mypy 历史债窄子集（memory 队列 A + `src/` 8 处）、给清理过的 3 个 tools 文件加 CI mypy-strict gate、并顺手修两处潜在 bug（`has_spec`/`count` 死赋值），除 Group D 两处外零行为变更。

**Architecture:** 单 PR，分支 `cleanup/ruff-mypy-historical-debt`（已建，spec commit `a190c16`）。Task 0 先 grep + 实跑核实所有 spec 假设；Task 1-5 按 spec 的 4 个 Group（A ruff / B mypy / C CI gate / D 顺手修，D 拆 D1+D2）各一个 commit；Task 6 收尾验证 + 推送 + 开 PR。

**Tech Stack:** Python 3.10+ / `ruff` / `mypy --strict` / `pytest` / GitHub Actions YAML / `scripts/dev_sync.py` 镜像同步。

设计文档：`docs/superpowers/specs/2026-05-12-ruff-mypy-historical-debt-cleanup-design.md`

---

## 前置约定（所有 task 通用）

- 分支必须是 `cleanup/ruff-mypy-historical-debt`，**不是 main**。subagent 用 `git -C "D:\Work\cad-spec-gen"` 绝对路径 + 提交前 `git -C "D:\Work\cad-spec-gen" branch --show-current` 守卫（`feedback_subagent_cwd_drift.md`）。
- 提交用 `git -c commit.gpgsign=false commit`；commit message 描述部分用中文（CLAUDE.md 语言规范）。
- 工作目录 `D:\Work\cad-spec-gen`；shell 是 PowerShell（`$null` 不是 `/dev/null`）；命令行示例里凡跑 `pytest`/`mypy`/`ruff` 都从 repo root 跑。
- 「全套件」= `pytest tests/ -q`；基线 **≥ 3084 PASS / 11 skipped / 0 regression**（v2.34.1 后；Task 4 会 +1 测试文件 6 个用例）。
- 改 `cad_pipeline.py` 或 `tools/*.py` 后，commit 前跑 `python scripts/dev_sync.py` 同步 `src/cad_spec_gen/data/` 下的生成镜像（gitignored，不进 commit），再 `python scripts/dev_sync.py --check` + `git diff --exit-code -- AGENTS.md` 确认。
- `LF will be replaced by CRLF` 的 git warning 是 noise，忽略。

---

## Task 0：核实 spec 假设（无代码改动，无 commit）

**目的**：spec 里标了 6 处「Plan 调查步」+ 几个 feasibility 问题——一次性跑掉，把结果写进本 task 的执行报告（subagent-driven 模式下作为后续 task 的输入）。这是 `feedback_subagent_driven_main_agent_scouts.md` / `feedback_plan_drift_taxonomy.md` 的预防层。

- [ ] **Step 1：确认 ruff 基线**

Run:
```
python -m ruff check cad_pipeline.py src/cad_spec_gen/cad_lib.py src/cad_spec_gen/render_3d.py src/cad_spec_gen/wizard/wizard.py tools/render_qa.py tools/jury_loop/backends/gemini_chat_image.py tools/jury_loop/backends/openai_images_edit.py tests/jury_loop/test_reason_parser.py tests/jury_loop/test_secrets_scrubber.py tests/jury_loop/test_rule_table.py
```
Expected：约 12 个错，分布与 spec §4 表一致（`cad_pipeline.py` F401 PIL.Image；`cad_lib.py` 3×F841 + 1×F541；`render_3d.py` F401 Euler + E402 L108；`wizard.py` F401 sys；`render_qa.py` F401 json；2 个 backends 各 F401 Path；`test_reason_parser.py`/`test_secrets_scrubber.py` 各 F401 pytest；`test_rule_table.py` F401 RuleTableLookupResult）。**若数量/分布不符 → 停下，报告偏差，不继续。**

- [ ] **Step 2：确认 mypy 基线 + 第三方依赖闭包**

Run（带依赖的正常 env）：`python -m mypy --strict tools/enhance_consistency.py tools/render_qa.py tools/path_policy.py`
Expected：恰好 16 个错，全在这 3 文件（`render_qa.py` 7 + `enhance_consistency.py` 8 + `path_policy.py` 1）。

Run（枚举第三方 import）：`python -m mypy --strict --no-site-packages tools/enhance_consistency.py tools/render_qa.py tools/path_policy.py`
Expected：报「Cannot find implementation or library stub for module named 'PIL'」（且**只有 PIL**这一个第三方 miss），外加 `path_policy.py:60` 的 dict 错和 `enhance_consistency.py:85` 的 arg-type 错（PixelAccess 那批因 PIL 成 Any 不会出现）。**若还有别的第三方模块 not-found（非 PIL）→ 记下来，Task 3 的 `pip install` 步要补上。**

- [ ] **Step 3：`_discover_enhanced_images` 调用方**

Run：`python -m ruff check --select=ALL --no-cache . 2>&1 | head -0; grep -rn "_discover_enhanced_images" src/ tools/ tests/`
检查每个调用方：拿到返回值后有没有对元素调 `.parent` / `.name` / `.suffix` 等 `Path`-only 方法。
- 没有 → Task 2 用「改 `_discover_enhanced_images` 返回标注为 `-> list[str | Path]`」。
- 有 → Task 2 改用 call-site `cast`（见 Task 2 备注）。
记录结论。

- [ ] **Step 4：`render_3d.py` late import**

Read `src/cad_spec_gen/render_3d.py` L100-115，确认 `import argparse`（L108）是该处唯一 module-level late import（L148/L776 都缩进、在函数内，不算）；ruff Step 1 也只报了 L108。记录确认。

- [ ] **Step 5：`import cad_pipeline` 是否 test-safe**

Run：`python -c "import cad_pipeline; print(cad_pipeline.__file__)"`
Expected：打印 `D:\Work\cad-spec-gen\cad_pipeline.py`（repo root 那个），无异常、无明显副作用（不应启动 argparse / 不应做文件 IO）。
也看一眼 `tests/test_cad_pipeline_jury_subcommand.py` 和 `tests/test_cad_pipeline_preflight_chain.py` 是 `import cad_pipeline` 还是 subprocess 调——若已有测试直接 import 它 = 已证 test-safe。
- test-safe → Task 4 的新测试 `from cad_pipeline import _derive_subsystem_status`。
- 不 safe（有重型 module-level 副作用）→ 记下来，Task 4 把 `_derive_subsystem_status` 放到能轻量 import 的位置（如已有的小工具模块），或改测试策略。记录结论。

- [ ] **Step 6：D2 测试 feasibility**

Read `src/cad_spec_gen/wizard/wizard.py` 的 `run_wizard`（L18 起）完整签名和函数体。判断：能否在一个测试里以「合理量级的 mock」（比如 ≤4 个 mock）驱动到 Step 6 并断言 `ui.success(t("register_done", ...))` 被调用？看 `wizard.py` 里 `ui` / `skill_register` / `env_detect` / `dep_installer` / `blender_setup` / `config_gen` 是怎么引用的（module-level import 便于 monkeypatch 还是别的）。
- **可行（有干净 seam）** → Task 5 Step 1 写测试（用 Task 5 给的 sketch 适配）。
- **不可行（Step 1-5 深度耦合，要 6+ mock）** → Task 5 走 fallback：只加那一行 + Task 6 PR 描述里写手动验证步骤。
记录结论 + 理由。

- [ ] **Step 7：汇总报告**

把 Step 1-6 的结论写成一段，作为本 task 的输出。**任何 Step 发现与 spec 实质不符的，标红、停下、回报，不要直接继续后续 task。**

---

## Task 1：Group A — ruff 清理（10 文件，1 commit，零行为变更）

**Files:**
- Modify: `cad_pipeline.py`（A1）
- Modify: `src/cad_spec_gen/cad_lib.py`（A2 + A3）
- Modify: `src/cad_spec_gen/render_3d.py`（A4 + A5）
- Modify: `src/cad_spec_gen/wizard/wizard.py`（A6）
- Modify: `tools/render_qa.py`（A7）
- Modify: `tools/jury_loop/backends/gemini_chat_image.py`（A8）
- Modify: `tools/jury_loop/backends/openai_images_edit.py`（A9）
- Modify: `tests/jury_loop/test_reason_parser.py`（A10）
- Modify: `tests/jury_loop/test_secrets_scrubber.py`（A11）
- Modify: `tests/jury_loop/test_rule_table.py`（A12）

- [ ] **Step 1：确认改前全套件绿（基线快照）**

Run：`pytest tests/ -q`
Expected：≥ 3084 PASS / 0 fail。

- [ ] **Step 2：A1 — `cad_pipeline.py` 删未用 `from PIL import Image`**

在 `cmd_env_check` 的 Pillow 检查 `try:` 块里：

旧：
```python
    try:
        from PIL import Image
        import PIL

        log.info("  Pillow: %s", PIL.__version__)
    except ImportError:
        log.error("  Pillow: NOT INSTALLED (pip install Pillow)")
```
新：
```python
    try:
        import PIL

        log.info("  Pillow: %s", PIL.__version__)
    except ImportError:
        log.error("  Pillow: NOT INSTALLED (pip install Pillow)")
```

- [ ] **Step 3：A2 — `cad_lib.py` 去掉 3 个未用的 subparser 赋值**

`build_parser()` 里 3 处（doctor / report / migrate），把 `p_xxx = subparsers.add_parser(...)` 改成 `subparsers.add_parser(...)`：
```python
    # doctor
    subparsers.add_parser("doctor", help="Diagnose issues")
```
```python
    # report
    subparsers.add_parser("report", help="Show suggestion log")
```
```python
    # migrate
    subparsers.add_parser("migrate", help="Schema version migration (stub)")
```
（`p_init` / `p_list` / `p_which` / `p_val` / `p_migs` 这些有 `.add_argument` 的**不动**。）

- [ ] **Step 4：A3 — `cad_lib.py` 去掉无占位符的 f-string**

旧：`        print(f"[X] Canonical render_3d.py not found.", file=sys.stderr)`
新：`        print("[X] Canonical render_3d.py not found.", file=sys.stderr)`

- [ ] **Step 5：A4 — `render_3d.py` 删未用 `Euler`**

旧：`from mathutils import Vector, Euler`
新：`from mathutils import Vector`

- [ ] **Step 6：A5 — `render_3d.py` L108 E402 noqa（不上移）**

`import argparse`（在 `argv = sys.argv` 解析块之后那行）改成：
```python
# ↓ 故意 late import：上方 A1-1 纯 Python helpers 段须在 bpy/argparse/mathutils 使用之前（tests AST 抽取约束）
import argparse  # noqa: E402
```
（把解释放在上一行作普通注释、`# noqa: E402` 单独跟在 import 行尾，避免 ruff 解析 noqa 码后跟中文的歧义。）

- [ ] **Step 7：A6 — `wizard.py` 删 `import sys`**

删掉 L3 的 `import sys` 整行（`"""6-step interactive setup wizard for cad-spec-gen."""` 之后、`from pathlib import Path` 之前那行）。

- [ ] **Step 8：A7 — `tools/render_qa.py` 删 `import json`**

删掉 L3 的 `import json` 整行（`from __future__ import annotations` 之后、`import re` 之前）。

- [ ] **Step 9：A8 / A9 — 两个 backend 删未用 `from pathlib import Path`**

`tools/jury_loop/backends/gemini_chat_image.py`：删掉 `from pathlib import Path` 整行（在 `import json` 和 `from typing import Any` 之间）。
`tools/jury_loop/backends/openai_images_edit.py`：同样删掉 `from pathlib import Path` 整行（在 `import secrets` 和 `from typing import Any` 之间）。

- [ ] **Step 10：A10 / A11 — 两个 jury test 删未用 `import pytest`**

`tests/jury_loop/test_reason_parser.py`：删掉 L6 的 `import pytest` 整行。
`tests/jury_loop/test_secrets_scrubber.py`：删掉 L4 的 `import pytest` 整行。

- [ ] **Step 11：A12 — `test_rule_table.py` 从多名 import 块删 `RuleTableLookupResult`**

旧：
```python
from tools.jury_loop.rule_table import (
    RuleTableLoadError,
    RuleTableLookupResult,
    RuleTableUnsupportedSchemaWarning,
    _clamp_param,
    load_rule_table,
    lookup,
)
```
新：
```python
from tools.jury_loop.rule_table import (
    RuleTableLoadError,
    RuleTableUnsupportedSchemaWarning,
    _clamp_param,
    load_rule_table,
    lookup,
)
```
（`import pytest` 在这个文件里**有用**——别删。）

- [ ] **Step 12：ruff（仅剩 Group D 的 2 个 F841）**

Run：
```
python -m ruff check cad_pipeline.py src/cad_spec_gen/cad_lib.py src/cad_spec_gen/render_3d.py src/cad_spec_gen/wizard/wizard.py tools/render_qa.py tools/jury_loop/backends/gemini_chat_image.py tools/jury_loop/backends/openai_images_edit.py tests/jury_loop/test_reason_parser.py tests/jury_loop/test_secrets_scrubber.py tests/jury_loop/test_rule_table.py
```
Expected：**恰好 2 个错** —— `cad_pipeline.py:3557 F841 has_spec` 和 `src/cad_spec_gen/wizard/wizard.py:163 F841 count`。这 2 个**故意留着**：Group A 不动它们，Task 4（D1）会把 `has_spec` 用上、Task 5（D2）会把 `count` 用上（用变量而非删变量）。其余 14 个 baseline 错（PIL.Image / p_doctor / p_report / p_mig / f-string / Euler / E402 / sys / pytest×2 / RuleTableLookupResult / Path×2 / json）必须全 0。**若除这 2 个 F841 外还有别的错 → 停下报告。**

- [ ] **Step 13：全套件 + dev_sync**

Run：`pytest tests/ -q`
Expected：≥ 3084 PASS / 0 regression（数字与 Step 1 一致）。
Run：`python scripts/dev_sync.py` 然后 `python scripts/dev_sync.py --check` 然后 `git diff --exit-code -- AGENTS.md`
Expected：dev_sync 成功，`--check` 通过，AGENTS.md 无变化。

- [ ] **Step 14：commit**

```
git -C "D:\Work\cad-spec-gen" branch --show-current   # 必须是 cleanup/ruff-mypy-historical-debt
git -C "D:\Work\cad-spec-gen" add cad_pipeline.py src/cad_spec_gen/cad_lib.py src/cad_spec_gen/render_3d.py src/cad_spec_gen/wizard/wizard.py tools/render_qa.py tools/jury_loop/backends/gemini_chat_image.py tools/jury_loop/backends/openai_images_edit.py tests/jury_loop/test_reason_parser.py tests/jury_loop/test_secrets_scrubber.py tests/jury_loop/test_rule_table.py
git -C "D:\Work\cad-spec-gen" -c commit.gpgsign=false commit -m "chore(cleanup): ruff F401/F841/F541/E402 清理（Group A，10 文件）

删未用 import/变量、去无占位符 f-string、render_3d.py L108 加 # noqa: E402（故意 late import）。零行为变更。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2：Group B — tools mypy strict 修复（3 文件，1 commit，零行为变更）

**Files:**
- Modify: `tools/path_policy.py`（B1）
- Modify: `tools/render_qa.py`（B2：加 `cast` import + 重写 `_corner_background_color`）
- Modify: `tools/enhance_consistency.py`（B3：加 `cast` import + 重写 `_corner_background_color` + `_discover_enhanced_images` 标注）

这是 refactor（行为不变），TDD 形态 = 改前现有相关测试绿 → 改 → 改后仍绿 + `mypy --strict` 0 错。

- [ ] **Step 1：改前快照**

Run：`pytest tests/test_render_qa.py tests/test_enhance_consistency.py -q`（若文件名不同，先 `git ls-files tests/ | grep -iE "render_qa|enhance_consist|path_policy"` 找到相关测试再跑）
Expected：全 PASS。记下用例数。

- [ ] **Step 2：B1 — `path_policy.py` `-> dict` → `-> dict[str, Any]`**

在 L60 那个函数签名（参数列表以 `skill_root: str | Path | None = None,` 结尾、紧接 `root = Path(project_root).resolve()`）：
旧：`) -> dict:`
新：`) -> dict[str, Any]:`
（`Any` 已 import，无需改 import。）

- [ ] **Step 3：B2 — `render_qa.py` 加 `cast` import**

旧：`from typing import Any`
新：`from typing import Any, cast`

- [ ] **Step 4：B2 — 重写 `render_qa.py::_corner_background_color`**

旧：
```python
def _corner_background_color(image: Image.Image) -> tuple[int, int, int, int]:
    width, height = image.size
    pixels = image.load()
    corners = [
        pixels[0, 0],
        pixels[width - 1, 0],
        pixels[0, height - 1],
        pixels[width - 1, height - 1],
    ]
    return tuple(int(sum(pixel[i] for pixel in corners) / len(corners)) for i in range(4))
```
新：
```python
def _corner_background_color(image: Image.Image) -> tuple[int, int, int, int]:
    width, height = image.size
    pixels = image.load()
    if pixels is None:  # pragma: no cover — load() 仅对已关闭图返回 None
        raise RuntimeError("图像像素缓冲不可用")
    corners = [
        cast(tuple[int, int, int, int], pixels[0, 0]),
        cast(tuple[int, int, int, int], pixels[width - 1, 0]),
        cast(tuple[int, int, int, int], pixels[0, height - 1]),
        cast(tuple[int, int, int, int], pixels[width - 1, height - 1]),
    ]
    n = len(corners)
    return (
        int(sum(c[0] for c in corners) / n),
        int(sum(c[1] for c in corners) / n),
        int(sum(c[2] for c in corners) / n),
        int(sum(c[3] for c in corners) / n),
    )
```

- [ ] **Step 5：B3 — `enhance_consistency.py` 加 `cast` import**

旧：`from typing import Any`
新：`from typing import Any, cast`

- [ ] **Step 6：B3 — 重写 `enhance_consistency.py::_corner_background_color`**

把该函数（def 在 ~L270，函数体与 render_qa.py 那份逐字相同）替换成 Step 4 的「新」版本（**不** dedup——两份各留各的）。

- [ ] **Step 7：B3 — `enhance_consistency.py::_discover_enhanced_images` 返回标注**

（Task 0 Step 3 已确认：唯一调用方是同文件 L85 处，传给 `_enhanced_candidates_by_view(...)`（签名 `list[str | Path]`），元素无 `.parent`/`.name` 等 Path-only 调用 → 改返回标注即可，零行为变更。）
旧：`def _discover_enhanced_images(render_dir: Path) -> list[Path]:`
新：`def _discover_enhanced_images(render_dir: Path) -> list[str | Path]:`

- [ ] **Step 8：mypy 归零**

Run：`python -m mypy --strict tools/enhance_consistency.py tools/render_qa.py tools/path_policy.py`
Expected：`Success: no issues found in 3 source files`（或等价的 0-error 输出）。
（若 Task 0 Step 2 发现了非-PIL 第三方依赖，本地 env 里它已装，所以这里能跑；CI 的事 Task 3 管。）

- [ ] **Step 9：ruff（确认没引入新问题）+ 全套件 + dev_sync**

Run：`python -m ruff check tools/path_policy.py tools/render_qa.py tools/enhance_consistency.py`
Expected：0 错（`render_qa.py` 的 `import json` 已在 Task 1 删了；本 task 没引入新的）。
Run：`pytest tests/ -q`
Expected：≥ 3084 PASS / 0 regression。
Run：`python scripts/dev_sync.py && python scripts/dev_sync.py --check && git diff --exit-code -- AGENTS.md`
Expected：通过。

- [ ] **Step 10：commit**

```
git -C "D:\Work\cad-spec-gen" branch --show-current   # 必须是 cleanup/ruff-mypy-historical-debt
git -C "D:\Work\cad-spec-gen" add tools/path_policy.py tools/render_qa.py tools/enhance_consistency.py
git -C "D:\Work\cad-spec-gen" -c commit.gpgsign=false commit -m "chore(cleanup): tools mypy strict 修复 — PixelAccess 守卫 + cast + dict 类型参数 + list 标注（Group B，3 文件）

_corner_background_color 加 image.load() None 守卫 + 逐角 cast + 显式 4-tuple 返回（行为等价：range(4) 推导式逐项一致、/len(corners) 保留）；path_policy.py -> dict 补 dict[str, Any]；enhance_consistency.py _discover_enhanced_images 返回标注补 str|Path。零行为变更。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3：Group C — CI mypy-strict gate（`tests.yml`，1 commit）

**Files:**
- Modify: `.github/workflows/tests.yml`（`mypy-strict` job）

- [ ] **Step 1：复核（Task 0 已查清——这里只确认 Group B 修完后命令是绿的）**

背景（Task 0 发现）：`pyproject.toml [tool.mypy]` 有 `ignore_missing_imports = true`，所以 bare-mypy 环境下找不到 PIL 不会报错、只会让 PIL 退化成 `Any`。即 **CI 不装 pillow 这个 gate 也不会红**——但那样 PIL=Any，gate 看不见 `PixelAccess | None` 那类错，等于只锁住「2 个非 PIL 错」。**装 pillow 的意义是让 gate 用真 PIL 类型、能锁住 PIL 相关回归**（本 PR 改 `_corner_background_color` 就是为这个）——所以仍然装。

Run：`python -m mypy --strict tools/enhance_consistency.py tools/render_qa.py tools/path_policy.py`（Group B 已修完）
Expected：`Success: no issues found in 3 source files`。
Run（无第三方依赖时也能跑、确认没有别的模块解析炸）：`python -m mypy --strict --no-site-packages tools/enhance_consistency.py tools/render_qa.py tools/path_policy.py`
Expected：也 0 错（`ignore_missing_imports` 吞掉所有第三方 not-found；Group B 已修掉那 4 个非 PIL 错）。若这里冒出别的错 → 排查。

- [ ] **Step 2：编辑 `tests.yml`**

在 `mypy-strict` job 里，`Run mypy strict on tools/jury (...)` 那步**之后**、`Verify mypy fixture catches type errors (...)` 那步**之前**，插入两步（注意缩进：`- name:` 6 空格，`run:` 8 空格，与同 job 其它 step 对齐）：

旧：
```yaml
      - name: Run mypy strict on tools/jury (Tasks 25+27 — photo3d jury 模块必 pass)
        run: mypy --strict tools/jury tools/photo3d_jury.py tools/_file_lock.py
      - name: Verify mypy fixture catches type errors (T17 等价 — gate 漂移防御)
```
新：
```yaml
      - name: Run mypy strict on tools/jury (Tasks 25+27 — photo3d jury 模块必 pass)
        run: mypy --strict tools/jury tools/photo3d_jury.py tools/_file_lock.py
      - name: Install Pillow for render-QA mypy check
        run: pip install pillow
      - name: Run mypy strict on render QA / path_policy (cleanup PR — 防回归)
        run: mypy --strict tools/enhance_consistency.py tools/render_qa.py tools/path_policy.py
      - name: Verify mypy fixture catches type errors (T17 等价 — gate 漂移防御)
```
（若 Step 1 发现别的第三方依赖，`pip install pillow` 改成 `pip install pillow <其它>`。）

- [ ] **Step 3：YAML 合法性 + 不破坏既有步**

Run：`python -c "import yaml; d = yaml.safe_load(open('.github/workflows/tests.yml', encoding='utf-8')); steps = d['jobs']['mypy-strict']['steps']; names = [s.get('name','') for s in steps]; print(names)"`
Expected：能解析，`names` 里依次出现 `'Install mypy'` → `'Run mypy strict on sw_config_broker.py ...'` → `'Run mypy strict on tools/jury ...'` → `'Install Pillow for render-QA mypy check'` → `'Run mypy strict on render QA / path_policy ...'` → `'Verify mypy fixture catches type errors ...'`。

- [ ] **Step 4：模拟 CI 的 mypy 步（干净 venv，`feedback_preflight_mirror_ci.md`）**

Run（PowerShell）：
```
python -m venv .mypy-ci-check
.\.mypy-ci-check\Scripts\python -m pip install --quiet "mypy>=1.10" pillow
.\.mypy-ci-check\Scripts\python -m mypy --strict tools/enhance_consistency.py tools/render_qa.py tools/path_policy.py
```
Expected：`Success: no issues found in 3 source files`（Group B 已修完，所以绿）。
然后清理：`Remove-Item -Recurse -Force .mypy-ci-check`。
（`.mypy-ci-check` 不要 commit；它在 repo root，commit 时只 `git add .github/workflows/tests.yml`，别 `git add -A`。若担心，临时把它加进 `.git/info/exclude`。）

- [ ] **Step 5：commit**

```
git -C "D:\Work\cad-spec-gen" branch --show-current   # 必须是 cleanup/ruff-mypy-historical-debt
git -C "D:\Work\cad-spec-gen" add .github/workflows/tests.yml
git -C "D:\Work\cad-spec-gen" -c commit.gpgsign=false commit -m "chore(ci): mypy-strict gate 加 enhance_consistency/render_qa/path_policy + 装 pillow（Group C）

mypy-strict job 加一步 mypy --strict 这 3 个 tools 文件防回归；因这俩 from PIL import ...，bare-mypy 环境会报找不到 PIL 故先 pip install pillow。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4：Group D1 — `cmd_status` 用 `has_spec` 区分 empty/spec-only（`cad_pipeline.py`，1 commit，TDD）

**Files:**
- Create: `tests/test_cad_pipeline_status.py`
- Modify: `cad_pipeline.py`（加 `_derive_subsystem_status` + 改 `cmd_status` + `icon` dict 加 `"empty"`）

- [ ] **Step 1：写失败测试**

按 Task 0 Step 5 的结论决定 import 方式（默认 `from cad_pipeline import _derive_subsystem_status`；若 Task 0 说 `cad_pipeline` 不 test-safe，按其建议调整）。新建 `tests/test_cad_pipeline_status.py`：
```python
"""单测 cad_pipeline._derive_subsystem_status —— 子系统状态标签推导（D1 顺手修：has_spec 接上线）。"""
from cad_pipeline import _derive_subsystem_status


def test_empty_when_no_spec_no_build():
    assert _derive_subsystem_status(has_spec=False, has_build=False, has_steps=False, has_pngs=False) == "empty"


def test_spec_only_when_spec_present_but_no_build():
    assert _derive_subsystem_status(has_spec=True, has_build=False, has_steps=False, has_pngs=False) == "spec-only"


def test_buildable_when_has_build():
    assert _derive_subsystem_status(has_spec=False, has_build=True, has_steps=False, has_pngs=False) == "buildable"
    # has_build 命中时不看 has_spec
    assert _derive_subsystem_status(has_spec=True, has_build=True, has_steps=False, has_pngs=False) == "buildable"


def test_built_when_has_steps():
    assert _derive_subsystem_status(has_spec=False, has_build=False, has_steps=True, has_pngs=False) == "built"


def test_rendered_when_has_pngs():
    assert _derive_subsystem_status(has_spec=False, has_build=False, has_steps=False, has_pngs=True) == "rendered"


def test_pngs_take_top_priority():
    assert _derive_subsystem_status(has_spec=True, has_build=True, has_steps=True, has_pngs=True) == "rendered"
```

- [ ] **Step 2：跑测试，确认失败**

Run：`pytest tests/test_cad_pipeline_status.py -q`
Expected：FAIL —— `ImportError: cannot import name '_derive_subsystem_status' from 'cad_pipeline'`（函数还不存在）。

- [ ] **Step 3：在 `cad_pipeline.py` 加 `_derive_subsystem_status`**

在 `cmd_status` 函数定义**之前**（module 级），加：
```python
def _derive_subsystem_status(*, has_spec: bool, has_build: bool, has_steps: bool, has_pngs: bool) -> str:
    """根据子系统目录里有哪些产物推导状态标签（纯函数，便于单测）。"""
    if has_pngs:
        return "rendered"
    if has_steps:
        return "built"
    if has_build:
        return "buildable"
    if has_spec:
        return "spec-only"
    return "empty"
```

- [ ] **Step 4：`cmd_status` 改用它 + `icon` dict 加 `"empty"`**

`cmd_status` 里，把：
```python
        status = "spec-only"
        if has_build:
            status = "buildable"
        if steps:
            status = "built"
        if pngs:
            status = "rendered"
```
换成：
```python
        status = _derive_subsystem_status(
            has_spec=has_spec,
            has_build=has_build,
            has_steps=bool(steps),
            has_pngs=bool(pngs),
        )
```
同函数里 `icon` dict 加一项：
```python
        icon = {
            "empty": "[-]",
            "spec-only": "[ ]",
            "buildable": "[B]",
            "built": "[*]",
            "rendered": "[R]",
        }
```
（`has_spec` 那行 `has_spec = os.path.isfile(...)` **保留**——现在它被用上了。）

- [ ] **Step 5：跑测试，确认通过**

Run：`pytest tests/test_cad_pipeline_status.py -q`
Expected：6 passed（含 `test_buildable_when_has_build` 里的 2 个断言）。

- [ ] **Step 6：ruff + 全套件 + dev_sync**

Run：`python -m ruff check cad_pipeline.py tests/test_cad_pipeline_status.py`
Expected：0 错。
Run：`pytest tests/ -q`
Expected：≥ 3084 + 6 PASS / 0 regression（也确认 `tests/test_cad_pipeline_*.py` 既有的没被这次改动碰坏——若有断言碰到 status 字符串/输出，更新期望值，记在 commit message）。
Run：`python scripts/dev_sync.py && python scripts/dev_sync.py --check && git diff --exit-code -- AGENTS.md`
Expected：通过。

- [ ] **Step 7：commit**

```
git -C "D:\Work\cad-spec-gen" branch --show-current   # 必须是 cleanup/ruff-mypy-historical-debt
git -C "D:\Work\cad-spec-gen" add cad_pipeline.py tests/test_cad_pipeline_status.py
git -C "D:\Work\cad-spec-gen" -c commit.gpgsign=false commit -m "fix(pipeline): cmd_status 用 has_spec 区分 empty/spec-only（Group D1，TDD）

抽出纯函数 _derive_subsystem_status（pngs>steps>build>spec 优先级），无 CAD_SPEC.md 又无 build_all.py 的子系统目录从错标 spec-only 改为 empty（icon [-]）；status 字符串只本函数内部消费，无外部契约。+6 个单测（cmd_status 原本零测试）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5：Group D2 — wizard 输出已安装文件数（`wizard.py`，1 commit）

**Files:**
- Modify: `src/cad_spec_gen/wizard/wizard.py`（register 段加一行 `ui.success`）

**不加单元测试**（Task 0 Step 6 已判定）：`run_wizard(lang, target, skip_deps, update, agent, codex_dir)` 要驱动到 Step 6 得 monkeypatch `wizard.ui` / `wizard.blender_setup` / `wizard.env_detect` / `wizard.config_gen` / `wizard.skill_register` 共 ~5 处 + 一个有 ~12 个方法的假 `ui` 类——为「加一行镜像同函数早些处 `ui.success(t("deps_done", lang, count=len(succeeded)))` 模式的 UI 调用」建这么大的桩不划算（`feedback_historical_debt_isolation.md`）。改动的覆盖靠：① `ruff` 确认无语法错；② 全套件不回归（这一行不破坏任何东西）；③ Task 6 PR 描述里写明手动验证步骤。

- [ ] **Step 1：加那一行**

`wizard.py` 的 Step 6 register 段，在 `count = skill_register.register_skill(...)` 这个多行调用（以 `)` 结尾）**之后**、`print()` **之前**插一行：
```python
    ui.info(t("register_copying", lang))
    count = skill_register.register_skill(
        target,
        lang=lang,
        version=version,
        update=update,
        agent=agent,
        codex_dir=codex_dir,
    )
    ui.success(t("register_done", lang, count=count))
    print()
```
（`register_done` i18n key 已存在：`i18n.py` zh `"{count} 个文件已安装"` / en `"{count} files installed"`，无需新增。镜像同函数早些处 deps 段的 `ui.success(t("deps_done", lang, count=len(succeeded)))`。）

- [ ] **Step 2：ruff + 全套件 + dev_sync**

Run：`python -m ruff check src/cad_spec_gen/wizard/wizard.py`
Expected：0 错（`import sys` 已在 Task 1 删，`count` F841 现在被这一行用上了 → 全清）。
Run：`pytest tests/ -q`
Expected：≥ 上一 task 的数字 PASS / 0 regression。
Run：`python scripts/dev_sync.py && python scripts/dev_sync.py --check && git diff --exit-code -- AGENTS.md`
Expected：通过（`wizard.py` 在包内、无镜像，但 dev_sync 跑一遍无害）。

- [ ] **Step 3：commit**

```
git -C "D:\Work\cad-spec-gen" branch --show-current   # 必须是 cleanup/ruff-mypy-historical-debt
git -C "D:\Work\cad-spec-gen" add src/cad_spec_gen/wizard/wizard.py
git -C "D:\Work\cad-spec-gen" -c commit.gpgsign=false commit -m "fix(wizard): Step 6 输出已安装文件数（Group D2）

register_skill 返回的 count 之前捕获了却没用、register_done i18n key 之前定义了却没调——补上 ui.success(t(\"register_done\", lang, count=count))，镜像同函数 deps 段的 deps_done 模式。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6：收尾验证 + 推送 + 开 PR

**Files:** 无改动。

- [ ] **Step 1：最终全量验证**

Run：`pytest tests/ -q`
Expected：≥ 3090 PASS（3084 + 6 新）/ 11 skipped / 0 regression。
Run：`python -m mypy --strict tools/enhance_consistency.py tools/render_qa.py tools/path_policy.py`
Expected：0 错。
Run（动过的所有文件，逐个）：`python -m ruff check cad_pipeline.py src/cad_spec_gen/cad_lib.py src/cad_spec_gen/render_3d.py src/cad_spec_gen/wizard/wizard.py tools/render_qa.py tools/enhance_consistency.py tools/path_policy.py tools/jury_loop/backends/gemini_chat_image.py tools/jury_loop/backends/openai_images_edit.py tests/jury_loop/test_reason_parser.py tests/jury_loop/test_secrets_scrubber.py tests/jury_loop/test_rule_table.py tests/test_cad_pipeline_status.py tests/test_codex_skill_register.py`
Expected：`All checks passed!`。
Run：`pytest tests/ -v -m "not mypy" -q`（CI 等价命令，系统 Python）
Expected：全 PASS。
Run：`python scripts/dev_sync.py && python scripts/dev_sync.py --check && git diff --exit-code -- AGENTS.md`
Expected：通过。
Run：`git -C "D:\Work\cad-spec-gen" status --porcelain`
Expected：clean（无未跟踪的 `.mypy-ci-check` / 镜像文件残留——若有，清掉）。

- [ ] **Step 2：requesting-code-review**

按 CLAUDE.md，调 `superpowers:requesting-code-review` 对本分支相对 main 的 diff 做一次 review；按 `superpowers:receiving-code-review` 处理意见（cleanup PR 的常见意见：scope creep / 行为变更漏标 / mypy cast 是否掩盖真 bug——逐条核实，不盲改）。有阻断性问题就修完再继续。

- [ ] **Step 3：推送 + 开 PR（需用户确认）**

向用户确认后：
```
git -C "D:\Work\cad-spec-gen" push -u origin cleanup/ruff-mypy-historical-debt
gh pr create --base main --head cleanup/ruff-mypy-historical-debt --title "chore(cleanup): ruff/mypy 历史债 cleanup（窄子集）+ mypy gate + has_spec/count 顺手修" --body "..."
```
PR body 要点：
- 范围：memory 队列 A 子集 + `src/` 8 处 ruff（**不**含其余 ~360 个；**不**含 `cad/*/render_3d.py` 副本；**不**把 `tools/jury_loop` 加进 mypy gate——都是有意划界，见 spec §2.2）
- Group A（ruff 清理 10 文件，零行为变更）/ Group B（tools mypy strict 3 文件，零行为变更，含行为等价论证）/ Group C（CI mypy gate + pip install pillow）/ Group D1（`cmd_status` empty/spec-only，+6 单测）/ Group D2（wizard 输出已安装文件数）
- **若 Task 5 走了 fallback（没加测试）**：PR body 明确写「D2 手动验证步骤：`cad-spec-gen` 跑 wizard → Step 6 → 确认打印『N 个文件已安装』」
- 链接 spec：`docs/superpowers/specs/2026-05-12-ruff-mypy-historical-debt-cleanup-design.md`
- 结尾：`🤖 Generated with [Claude Code](https://claude.com/claude-code)`

- [ ] **Step 4：盯 CI（PowerShell 环境用 `gh pr checks --watch`，别用 bash `comm`/`watch` —— `feedback_monitor_windows_gnu_tools.md`）**

Run：`gh pr checks <PR#> --watch`
Expected：8 checks 全 SUCCESS（mypy-strict + regression + ubuntu 3.10/11/12 + windows 3.10/11/12）。有红的 → 看日志、按 `superpowers:systematic-debugging` 修、push 修复 commit、再 watch。

---

## 自审（writing-plans skill 要求）

**1. Spec 覆盖**：spec §4 Group A 12 项 → Task 1 Step 2-11 逐项；spec §5 Group B B1/B2/B3 → Task 2 Step 2-7；spec §6 Group C → Task 3；spec §7 D1 → Task 4，D2 → Task 5；spec §8 验证清单 → Task 1/2/3/4/5 各自的验证步 + Task 6 汇总；spec §3 canonical/mirror → 「前置约定」+ 各 task 的 dev_sync 步；spec 的 6 处「Plan 调查步」 → Task 0 Step 1-6。无遗漏。

**2. Placeholder 扫描**：Task 5 Step 1 是「按 Task 0 结论二选一」的真分支（两边都给了具体内容/sketch），不是 TBD；Task 2 Step 7、Task 4 Step 1 同理。无 "TODO/待定/类似上文" 之类。

**3. 类型/命名一致**：`_derive_subsystem_status`（Task 0 Step 5 / Task 4 Step 1/3/4 / commit msg）全程同名同签名（`*, has_spec, has_build, has_steps, has_pngs -> str`）；`_corner_background_color` 重写版在 Task 2 Step 4 和 Step 6 引用同一份代码；`register_done` / `deps_done` i18n key 名一致；分支名 `cleanup/ruff-mypy-historical-debt` 全程一致。

**4. 已知留给执行期判断的点**（非 placeholder，是 Task 0 的产出驱动）：`_discover_enhanced_images` 改签名 vs call-site cast（Task 0 Step 3）；`import cad_pipeline` test-safe 与否（Task 0 Step 5）；D2 是否加测试（Task 0 Step 6）；CI mypy 步是否还需装别的第三方（Task 0 Step 2 / Task 3 Step 1）。
