# 设计：ruff/mypy 历史债 cleanup PR

- **日期**：2026-05-12
- **基线**：main@c9ddab0（v2.34.1 发布后）
- **分支**：`cleanup/ruff-mypy-historical-debt`
- **规模**：颗粒小的单 PR，与 v2.30.0 cleanup 同量级
- **状态**：brainstorming 完成；待用户复审 → writing-plans

---

## 1. 背景与目标

v2.34.1 发布后，全仓 `ruff check .` 有 **393 个 pre-existing 错误**（adapters 45 / tests 128 / codegen 23 / src 8 / tools 18 / templates 7 等）。这些不阻断 CI——**CI 根本不跑 ruff**。CI 的 `mypy-strict` job 也只覆盖 `adapters/solidworks/sw_config_broker.py` + `tools/jury` + `tools/photo3d_jury.py` + `tools/_file_lock.py`，**不覆盖** `tools/enhance_consistency.py` / `tools/render_qa.py` / `tools/path_policy.py`（这 3 文件有 16 个 pre-existing mypy strict 错）。

本 PR 做三件事：

1. **清理一个已选定的窄子集**——memory「后续工作队列 A」列的文件 + `src/` 包里的 8 处 ruff 错；
2. **修两处 BOUNDARY-3 的潜在 bug**（`cad_pipeline.py` 的 `has_spec` 死赋值、`wizard.py` 的 `count` 死赋值——它们看起来都是「值算了/i18n 加了，就差一行接上线」的遗漏）；
3. **给清理过的 3 个 tools 文件加 CI mypy-strict gate** 防回归。

**核心约束**：除 §5 Group D 两处显式 bug 修复外，**零行为变更**。

---

## 2. 范围

### 2.1 In-scope（4 个 Group）

| Group | 内容 | 文件数 |
|---|---|---|
| A — ruff 修复 | 删未用 import/变量、去多余 f 前缀、一处 E402 noqa | 10 |
| B — mypy strict 修复 | `PixelAccess \| None` 守卫 + `cast`、`dict` 类型参数、`list[str\|Path]` 标注 | 3 |
| C — CI mypy gate | `tests.yml` `mypy-strict` job 加一步 | 1 |
| D — BOUNDARY-3 顺手修 | `has_spec` 接上 status 判定、`count` 接上 `register_done` 输出 | 2：`cad_pipeline.py`（D1，与 A1 同文件）+ `wizard.py`（D2，与 A6 同文件）；另 D1 新建 1 个测试文件，D2 可能 +1 测试 |

### 2.2 Out-of-scope（明确划界）

- **其余 ~360 个 ruff 错**（`adapters/` 45 / `codegen/` 23 / `tests/` 128 / `templates/` 7 等）——不在本 PR；若要清需另开按目录分批的多 PR（与「颗粒最小」初衷不符，本 PR 不做）。
- **`cad/end_effector/render_3d.py` + `cad/lifting_platform/render_3d.py`** 的同款 ruff 错（各 `Euler` F401 + L108 E402，共 4 个）。理由：这俩是 tracked 的**部署副本**，由 `cad-lib migrate-subsystem` 从 `src/cad_spec_gen/render_3d.py` 重生，且各带一个 divergent `_CONFIG_MATERIALS` patch（本身是登记过的技术债，见 `project_session28_handoff.md`）。修 `src/` canonical 后，下次 `migrate-subsystem` 会把修复传播过去。本 PR 只动 canonical，不碰副本，避免牵出 divergence 问题。**用户已确认（BOUNDARY-1：只修 src/）。**
- **把 `tools/jury_loop` 整体加入 mypy-strict gate**——SP1 的 `tools/jury_loop` 从未进过 CI mypy gate（gate 里的 `tools/jury` 是 photo3d-jury 旧模块，不是 `tools/jury_loop`）。本 PR 只删 `tools/jury_loop/backends/*.py` 里 2 处未用 `Path` import（纯 ruff 修，无 mypy 影响）；「`tools/jury_loop` 加 mypy gate」是独立 §11 项，不在本 PR。**用户已确认（BOUNDARY-2：划界本 PR 外）。**
- **`_corner_background_color` dedup**——这个函数在 `render_qa.py` 和 `enhance_consistency.py` 里逐字重复，但本 PR 两份各自修，不抽公共模块（dedup 是另一个 scope）。**用户已确认（不 dedup）。**
- SP1 §11 其余项（N-15 / N-16 / `skill.json` 描述 / Task 8.2 L4 smoke）、真实 AI adapter、多视角实例证据增强、交付报告可视化——都不在本 PR。

---

## 3. Canonical / mirror 注意

- `cad_pipeline.py`（顶层）和 `tools/*.py` 在 `src/cad_spec_gen/data/python_tools/`、`src/cad_spec_gen/data/tools/` 下有**生成镜像**（`.gitignore` line 25/29 排除，**不 tracked**）。改 canonical 后跑 `python scripts/dev_sync.py` 同步本地镜像；CI 的 `python scripts/dev_sync.py --check` 会从 canonical 重生并验证。因为镜像 gitignored，本地 `git status` 不会显示它们，也无需提交——但实施时仍要跑一次 `dev_sync.py` + `--check` 确认 canonical 内部一致。
- `src/cad_spec_gen/cad_lib.py` / `src/cad_spec_gen/render_3d.py` / `src/cad_spec_gen/wizard/wizard.py` / `src/cad_spec_gen/wizard/i18n.py` 是包内 canonical 文件，无镜像，直接改。
- 不动 `src/cad_spec_gen/data/skill.json` → `AGENTS.md`（`scripts/dev_sync.py` 自动生成）不受影响。

---

## 4. 详细改动 — Group A（ruff，零行为变更）

| # | 文件 | 行 | 改动 | 已核实 |
|---|---|---|---|---|
| A1 | `cad_pipeline.py` | L3649（`cmd_env_check` 函数内） | 删 `from PIL import Image`（**保留** `import PIL`） | 该 `try:` 块只 `log.info("Pillow: %s", PIL.__version__)`，`Image` 全程未用；删后 `import PIL` 仍能触发 `except ImportError`、`PIL.__version__` 仍可读。唯一差异：不再额外验证 `PIL.Image` 子模块可导入（可忽略） |
| A2 | `src/cad_spec_gen/cad_lib.py` | L81 / L105 / L108（`build_parser` 函数内） | `p_doctor = subparsers.add_parser(...)` → `subparsers.add_parser(...)`（去赋值，3 处：doctor / report / migrate） | 这 3 个 subparser 后无 `.add_argument`，变量未用；`add_parser` 的副作用（注册子命令）保留，dispatch 不受影响 |
| A3 | `src/cad_spec_gen/cad_lib.py` | L519（`migrate_subsystem` cmd 内） | `print(f"[X] Canonical render_3d.py not found.", ...)` → 去 `f` 前缀 | 无占位符 |
| A4 | `src/cad_spec_gen/render_3d.py` | L23 | `from mathutils import Vector, Euler` → `from mathutils import Vector` | `Euler` 用 0 次；`Vector` 用 18 次 |
| A5 | `src/cad_spec_gen/render_3d.py` | L108 | `import argparse` 行尾加 `# noqa: E402  # 故意 late import：A1-1 纯 Python helpers 段须在 bpy/argparse/mathutils 使用之前（tests AST 抽取约束，见上方注释）` | ruff 仅报 L108 一处 module-level late import（L148/L776 都是函数内 import，不算）。**采用 noqa 而非上移**：文件有显式注释说明放置是故意的；该文件本就无法在 Blender 外正常 import（L17 `import bpy`），保守不动结构（`feedback_archeology_before_diagnosis.md`） |
| A6 | `src/cad_spec_gen/wizard/wizard.py` | L3 | 删 `import sys` | `sys` 用 0 次 |
| A7 | `tools/render_qa.py` | L3 | 删 `import json` | `json` 用 0 次（注：`enhance_consistency.py` 的 `json` 有用，不删） |
| A8 | `tools/jury_loop/backends/gemini_chat_image.py` | L14 | 删 `from pathlib import Path` | `Path` 仅在 import 行出现 |
| A9 | `tools/jury_loop/backends/openai_images_edit.py` | L16 | 删 `from pathlib import Path` | `Path` 仅在 import 行出现 |
| A10 | `tests/jury_loop/test_reason_parser.py` | L6 | 删 `import pytest` | `pytest` 仅在 import 行出现；pytest 收集测试不依赖文件 import pytest |
| A11 | `tests/jury_loop/test_secrets_scrubber.py` | L4 | 删 `import pytest` | 同上 |
| A12 | `tests/jury_loop/test_rule_table.py` | L15（多名 import 块内） | 从 `from ... import (...)` 块里删 `RuleTableLookupResult,` 一行 | `RuleTableLookupResult` 仅在 import 块出现；删时注意多行 import 语法（保留其它名 + 尾逗号合法性，ruff 会处理） |

> 注：A1（`cad_pipeline.py::cmd_env_check` 的 PIL import）和 D1（`cad_pipeline.py::cmd_status` 的 `has_spec`）同文件不同函数；A2/A3 在 `src/cad_spec_gen/cad_lib.py::build_parser`，是另一个文件。被多个 Group 触到的文件有 3 个：`cad_pipeline.py`（A1+D1）、`tools/render_qa.py`（A7+B2）、`src/cad_spec_gen/wizard/wizard.py`（A6+D2）——同一文件的多处改动在 plan 里归到同一个 task（或按 commit 分组），避免互相覆盖。

**Plan 调查步**：A5——确认 `render_3d.py` L108 之后到 `argparse` 使用（L110）之间没有别的 module-level `import`；ruff 当前只报 L108，按理一处 noqa 足够，但实施时 `ruff check src/cad_spec_gen/render_3d.py` 确认归零。

---

## 5. 详细改动 — Group B（mypy strict，零行为变更）

`mypy --strict tools/enhance_consistency.py tools/render_qa.py tools/path_policy.py`（repo root）当前 **16 错全在这 3 文件**（`render_qa.py` 7 + `enhance_consistency.py` 8 + `path_policy.py` 1）；transitive 依赖（`enhance_budget` / `tools/jury_loop/config` / `tools/contract_io`）已 strict-clean（`mypy --strict` 跟随 import 检查它们，当前无报错）。修完这 16 个 → 该命令绿（已本地核实 16 错的清单与归属）。

### B1. `tools/path_policy.py` L60
```python
) -> dict:          # → ) -> dict[str, Any]:
```
`Any` 已 import（L4 `from typing import Any`），无需新 import。修 `Missing type arguments for generic type "dict"`。

### B2. `tools/render_qa.py` `_corner_background_color`（def 在 L282；被 L41 `Image.new("RGBA", rgba.size, _corner_background_color(rgba))` 用作 RGBA 填充色——印证「返回 4-tuple int」是既有契约）
顶部 import：`from typing import Any` → `from typing import Any, cast`。
函数重写为（注意：`from __future__ import annotations` 在文件顶，`cast(tuple[...], ...)` 第一参数是运行期表达式，PEP 585 在 3.9+ OK，本项目 3.10+ 且已用 `|` 语法）：
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
修 4 处 `PixelAccess | None is not indexable` + return-value 类型不匹配 + `pixel[i]` 不可索引 + generator misc。

### B3. `tools/enhance_consistency.py`
- 同 B2：`from typing import Any` → `from typing import Any, cast`；`_corner_background_color`（def 在 L270；被 L250 同样用作 `Image.new` 填充色）同样重写（独立改，**不** dedup）。修 8 个错里的 7 个（L274-277 + L279×3）。
- L85 arg-type（`list[str | Path] | list[Path]` 与期望 `list[str | Path]` 不匹配，list 不变型）：把 `_discover_enhanced_images`（def 在 L428）的返回标注 `-> list[Path]` 改成 `-> list[str | Path]`（值层面 `list[Path]` 就是合法 `list[str | Path]`，运行时对象不变）。修剩下 1 个错。
  - **Plan 调查步**：`grep -rn "_discover_enhanced_images(" src/ tools/ tests/` 确认没有调用方依赖返回元素是 `Path` 具体类型（如对元素调 `.parent` / `.name`）；若有，改用 call-site `cast("list[str | Path]", _discover_enhanced_images(render_dir))` 而不改函数签名。

### 行为不变性论证
- **`_corner_background_color`**：原 `tuple(int(sum(pixel[i] for pixel in corners) / len(corners)) for i in range(4))` 对 `i = 0,1,2,3` → 与显式 4-tuple 逐项等价；`/ len(corners)` 保留（`n = len(corners)`，恒为 4）；「4 通道」假设原代码 `pixel[i] for i in range(4)` 本就隐含（非 RGBA 图原代码会 IndexError），`cast` 只把它显式化，不改运行时；新增 `if pixels is None: raise` 是 PIL stub 要求的防御分支，实际从不触发（`# pragma: no cover`），不影响任何现有测试；CI cov gate 不覆盖 `tools/`，覆盖率不受影响。
- **`_discover_enhanced_images` 返回标注 `list[Path] → list[str | Path]`**：纯标注变更，运行时返回的对象与元素类型不变。
- **`-> dict` → `-> dict[str, Any]`**：纯标注变更。

---

## 6. 详细改动 — Group C（CI mypy gate）

`.github/workflows/tests.yml` 的 `mypy-strict` job 当前只 `pip install "mypy>=1.10"`，**不装 Pillow**。而 `enhance_consistency.py` / `render_qa.py` 都 `from PIL import ...`——bare-mypy 环境下 mypy 报「Cannot find implementation or library stub for module named 'PIL'」（`--strict` 不含 `--ignore-missing-imports`），且 `PixelAccess | None` 这类错根本不会出现（PIL 成 `Any`）。**所以本步必须先装 Pillow**，否则 gate 要么红在「找不到 PIL」、要么（若加 `--ignore-missing-imports`）形同虚设。

在现有 `tools/jury` 那步（`run: mypy --strict tools/jury tools/photo3d_jury.py tools/_file_lock.py`）之后加两步：

```yaml
      - name: Install Pillow for render-QA mypy check
        run: pip install pillow
      - name: Run mypy strict on render QA / path_policy（cleanup PR — 防回归）
        run: mypy --strict tools/enhance_consistency.py tools/render_qa.py tools/path_policy.py
```

- 单独的 `- name:` step（失败归因清晰），不与 `tools/jury` 那步合并。
- **不加 pytest mypy 测试**（`feedback_ci_mypy_marker_deselect.md`：tool-job 直接调 CLI 比 pytest 间接调更稳；test matrix 已 `-m "not mypy"`，新 workflow 步与之无关，无需 deselect）。
- 命令从 repo root 跑（与 CI 一致）。该 gate 的 import 闭包里第三方依赖**只有 Pillow**（其余 `enhance_budget` / `tools.contract_io` / `tools.jury_loop.config` 都是 repo-local，已 strict-clean——mypy `--follow-imports=normal` 会深检它们；而 site-packages 里的 Pillow 只取其 `py.typed` 接口、不深检 Pillow 内部，所以不会冒出 Pillow 自身的类型噪声）。
- **Plan 强制核实步**（`feedback_preflight_mirror_ci.md`）：开一个干净 venv，只 `pip install "mypy>=1.10" pillow`，从 repo root 跑上面的 mypy 命令，确认（a）修完 Group B 后绿，（b）不需要再装别的依赖（若闭包里还有别的第三方 import 被漏，补到 install 步）。本地常规 dev env 因装了 cadquery 等会顺带满足依赖，**不能**作为「CI 等价」的证据。

---

## 7. 详细改动 — Group D（BOUNDARY-3 顺手修，2 处行为变更）

### D1. `cad_pipeline.py` `cmd_status` — `has_spec` 接上线

当前（约 L3557-3583）：`has_spec = os.path.isfile(...)` 算了但未用；`status` 无条件从 `"spec-only"` 起步，即使该子系统目录里没有 `CAD_SPEC.md` 也标 `spec-only`（错误）。

**重构**：把 status 推导抽成纯函数，便于测试：
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
`cmd_status` 里 8 行 inline 推导替换为一次调用（传 `has_steps=bool(steps)`, `has_pngs=bool(pngs)`）；`icon` dict 加一项 `"empty": "[-]"`（放在 `"spec-only": "[ ]",` 旁）。

> 等价性核对：原逻辑 `status = "spec-only"; if has_build: ...; if steps: ...; if pngs: ...` 是「后者覆盖前者」，等价于「从最高优先级往下第一个命中」——`_derive_subsystem_status` 的 `if pngs → steps → build → spec` 顺序与之一致。唯一新增：`has_build` 也为假时从 `"spec-only"` 改成（`has_spec` 真→`"spec-only"` / 假→`"empty"`）。`status` 字符串只被本函数的 `icon.get()` + `log.info` 消费，无外部契约，新增 `"empty"` 值安全。

**测试**（TDD RED→GREEN）：`cmd_status` 当前**无测试**（`grep "cmd_status\|spec-only" tests/` 空）——新建 `tests/test_cad_pipeline_status.py`（既有命名约定是 `tests/test_cad_pipeline_<topic>.py`，如 `test_cad_pipeline_resume.py`），`from cad_pipeline import _derive_subsystem_status`（`tests/conftest.py` 已把 repo root append 到 `sys.path`，顶层 `cad_pipeline.py` 可 import；plan 须先确认 `import cad_pipeline` 无重型 module-level 副作用——既有 `test_cad_pipeline_resume.py` 是 subprocess 调，不算 import 证据，查 `test_cad_pipeline_jury_subcommand.py`/`_preflight_chain.py` 是否直接 import）。单测 `_derive_subsystem_status` 真值表：「无 spec 无 build → empty」「有 spec 无 build → spec-only」「有 build → buildable」「有 step → built」「有 png → rendered」「png 优先级最高（同时有 step/build/spec 时仍 rendered）」。先写失败测试（函数还不存在）→ 提取函数 → 绿。

### D2. `wizard.py` register 段 — `count` 接上线

当前（约 L162-176）：`count = skill_register.register_skill(...)` 捕获了返回值（docstring 承诺 `int: Number of files copied`，`tests/test_codex_skill_register.py:46` 已捕获该返回值），但从未输出；而 i18n key `register_done`（`i18n.py:53` zh `"{count} 个文件已安装"` / `:118` en `"{count} files installed"`）已定义、从未被调用——典型「就差一行 `ui.success` 调用」的遗漏。

**改动**：在 `count = skill_register.register_skill(...)` 之后、`print()` 之前加一行（镜像同文件 deps 段 `ui.success(t("deps_done", lang, count=len(succeeded)))` 的既有模式）：
```python
    count = skill_register.register_skill(...)
    ui.success(t("register_done", lang, count=count))
    print()
```
无新 i18n key。

**测试**：当前**无** `tests/test_wizard*.py`（仅 `tests/test_codex_skill_register.py` 测 `register_skill` 这个函数本身，不测 `wizard.py` 的 Step 6 输出）。已核实 `wizard/*.py` 子模块**无 module-level Windows-only import**（无 `winreg`/`tkinter`/`ctypes.windll`），且 `test_codex_skill_register.py` 在 Linux CI 已能 import wizard 子模块——所以 D2 测试在 Linux 安全，**不需要** `requires_windows` marker。Plan 决策（按「测试可行就 TDD、不可行就如实标注」原则）：
- **优先**：在 `tests/test_codex_skill_register.py` 加一个聚焦测试——mock `wizard.ui`（或 `wizard` 模块里的 `ui`）+ mock 掉前 5 步的副作用（`env_detect` / `dep_installer` / `blender_setup` / `config_gen`），驱动 `run_wizard`（或其等价入口）走到 Step 6，断言 `ui.success` 被以含 `count` 的 `register_done` 文案调用过。先写失败测试（当前没这一行调用）→ 加 `ui.success(t("register_done", ...))` → 绿。
- **回退**（若 Step 6 在测试里实在难以独立驱动——前 5 步耦合太重）：接受 D2 为「镜像既有 `deps_done` 模式的一行 UI 补充」，PR 描述里注明手动验证（跑 wizard 走到 Step 6 看是否打印「N 文件已安装」），不强行造测试基建。

---

## 8. 验证清单

1. **ruff**：`ruff check <本 PR 动过的所有文件>` 全部 clean（逐文件验，不跑 `ruff check .` 因为还有 ~360 个 out-of-scope 错）。
2. **mypy gate**：在干净 venv（只 `pip install "mypy>=1.10" pillow`，模拟 CI `mypy-strict` job）从 repo root 跑 `mypy --strict tools/enhance_consistency.py tools/render_qa.py tools/path_policy.py` → clean（`feedback_preflight_mirror_ci.md`：本地 dev env 装了一堆依赖，不算 CI 等价）。
3. **全套件**：`pytest tests/ -q` → **≥ 3084 PASS / 0 regression**，外加 D1（+1 单测）、D2（0 或 +1 单测）的新增；**另外**用 CI 的确切命令 `pytest tests/ -v -m "not mypy"`（系统 Python，不在 venv 里）跑一遍确认 CI 等价。若 D1/D2 触到既有测试的断言（如断言过 status 字符串或 register 输出），更新那些期望值（这是改测试，不是写新测试）——plan 须 `grep` 找。
4. **dev_sync**：`python scripts/dev_sync.py && python scripts/dev_sync.py --check` 通过；`git diff --exit-code -- AGENTS.md`（应无变化）。`cad_pipeline.py` 和 `tools/*.py` 改动后这步会把 `src/cad_spec_gen/data/` 下的生成镜像重生并验证；镜像 gitignored 无需提交。
5. **北极星 5 gate + Windows-only**：
   - 零配置 ✓（不动任何配置文件）
   - 稳定可靠 ✓（D1/D2 是更准确的状态展示，非新增风险面；`pixels is None` 守卫只增不减健壮性）
   - 结果准确 ✓（D1 修了「无 spec 却标 spec-only」的错误标签）
   - SW 装即用 ✓（不动 SW 相关任何东西）
   - 傻瓜式 ✓（D2 让 wizard 多报一行「N 文件已安装」，对外行更友好）
   - Windows-only ✓（不引入跨平台分支；`# pragma: no cover` 在所有平台行为一致）

---

## 9. 不写大量新单元测试的理由

本 PR 主体是卫生（删死 import/变量）+ 标注修复（mypy）+ CI gate + 2 处微 bug 修复，无新功能模块。"测试" = §8 的 ruff/mypy/全套件三道闸 + CI 新 mypy 步。**唯二**新增单测来自 Group D 的行为变更：D1 必加（`_derive_subsystem_status` 真值表，TDD RED→GREEN，因 `cmd_status` 原本零测试）；D2 视既有 wizard 测试基建而定（可行则加断言，不可行则标注手动验证）。这与 v2.30.0 cleanup「窄 scope + 为行为变更补最小测试」的先例一致，不扩 scope（`feedback_historical_debt_isolation.md`）。

---

## 10. 提交建议

按 Group 分 commit 便于 review（`feedback_historical_debt_isolation.md`：cleanup 与功能分离、单 commit 不夹带）：

1. `chore(cleanup): ruff F401/F841/F541/E402 清理（Group A，10 文件）`
2. `chore(cleanup): tools mypy strict 修复 — PixelAccess 守卫 + cast + dict 类型参数 + list 标注（Group B，3 文件）`
3. `chore(ci): mypy-strict gate 加 enhance_consistency/render_qa/path_policy + 装 pillow（Group C）`
4. `fix(cli): cmd_status 用 has_spec 区分 empty/spec-only + wizard 输出已安装文件数（Group D，TDD）`

（也可合成更少 commit；plan 定。commit message 描述部分用中文，提交用 `git -c commit.gpgsign=false commit`；分支必须是 `cleanup/ruff-mypy-historical-debt` 不是 main——subagent 用 `git -C <abs>` + branch 守卫，见 `feedback_subagent_cwd_drift.md`。）
