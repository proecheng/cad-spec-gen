# §11-N12 `tools/dev/lint_scope_audit.py` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 §11-N12 — `tools/dev/lint_scope_audit.py` dev tool 检测 pyproject 声明的 lint scope vs 真实代码状态 drift (ruff per-file-ignores + mypy ignore_errors)；伴随 `tomli` test dep + 18 tests + retro §3.3 N12 closed。

**Architecture:** 单 script with argparse subcommands (`ruff` / `mypy` / `all`)；两侧算法绕过 pyproject self-suppress（ruff 用 `--config 'lint.per-file-ignores={}'` inline / mypy 用 tempfile stripped pyproject + `--config-file <tmp>`）；纯函数 + 两处 subprocess 边界；零新 pip dep（tomli 仅 py3.10 fallback）。

**Tech Stack:** Python 3.10/3.11/3.12 + tomllib (py3.11+) / tomli (py3.10) + subprocess + argparse + tempfile + pathlib + re + fnmatch (不用) + pytest 7+ for tests。**禁止**引入 pathspec / ruff Python API / mypy plugin API 等额外 dep。

**Spec 引用：** `docs/superpowers/specs/2026-05-17-lint-scope-audit-design.md` rev 1.3 @ commit `0e3b181`（4 轮审查 31 fix 全闭环）。

**Feature branch：** `feat/n12-lint-scope-audit`（已建，head `0e3b181`）。

---

## Task 0: Scout — 实测 spec 假设 + 输出 implementation 真值

**Files:**
- Create: `tmp/n12_scout_report.md`（不入仓，gitignored 路径）

**为何需要 Task 0**：spec rev 1.3 多个假设已实测验证（B7/M10 候选 RESOLVED），但 implementer 用 fresh subagent 时不在 spec session context；必须用 scout 重跑实测固化真值给 Task 2-4 用。

- [ ] **Step 0.1: 检查 cwd 与 branch**

Run:
```bash
pwd  # 应为 D:/Work/cad-spec-gen
git branch --show-current  # 应为 feat/n12-lint-scope-audit
git log -1 --oneline  # 应为 0e3b181 (rev 1.3 spec commit)
```
Expected: cwd=`D:/Work/cad-spec-gen`，branch=`feat/n12-lint-scope-audit`，HEAD=`0e3b181 docs(spec): §11-N12 spec rev 1.3 ...`

- [ ] **Step 0.2: 实测 pyproject.toml per-file-ignores 12 globs**

Run:
```bash
grep -c '^"' pyproject.toml
```
Expected: `12`（spec §2.2 B1 校准值）

- [ ] **Step 0.3: 实测 4 ignore_errors=true modules**

Run:
```bash
grep -E 'adapters\.solidworks\.sw_detect|adapters\.solidworks\.sw_config_lists_cache|cad_paths|tools\.contract_io' pyproject.toml
```
Expected: 4 module names 出现在 `[[tool.mypy.overrides]]` `module = [...]` 列表内

- [ ] **Step 0.4: 实测 ruff version + --config flag**

Run:
```bash
.venv/Scripts/ruff.exe --version
.venv/Scripts/ruff.exe check --config 'lint.per-file-ignores={}' --select=E402 --output-format=json . 2>&1 | python -c "import sys, json; d=json.loads(sys.stdin.read()); print(f'count={len(d)}'); print('filename[0]=', d[0]['filename'][:50] if d else 'EMPTY')"
```
Expected: ruff version `0.15.10`；count ≥ 70（strip 后真违规）；filename[0] 是 absolute Windows path (`D:\Work\...`)。

- [ ] **Step 0.5: 实测 stripped mypy config + 4 modules**

Run:
```bash
cat > tmp/stripped_pyproject.toml << 'EOF'
[tool.mypy]
python_version = "3.10"
strict_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
ignore_missing_imports = true
explicit_package_bases = true
EOF
for m in adapters.solidworks.sw_detect adapters.solidworks.sw_config_lists_cache cad_paths tools.contract_io; do
  echo "=== $m ==="
  .venv/Scripts/python.exe -m mypy --strict --config-file tmp/stripped_pyproject.toml --disable-error-code=import-untyped -p "$m" 2>&1 | tail -1
done
```
Expected: 4 modules 全部 `Found N errors in 1 file` (N ≥ 1 each)；dischargeable=0 baseline 校准。

- [ ] **Step 0.6: 检查 tools/dev/ 目录与 rebrand_test_archive.py 风格**

Run:
```bash
ls tools/dev/
head -50 tools/dev/rebrand_test_archive.py
```
Expected: `__init__.py` + `__pycache__` + `rebrand_test_archive.py`；rebrand 用 argparse + 函数式风格，可参考。

- [ ] **Step 0.7: 检查 pytest baseline**

Run:
```bash
.venv/Scripts/python.exe -m pytest --collect-only -q 2>&1 | tail -3
```
Expected: `3241 tests collected`（spec §2.2 校准基线）。

- [ ] **Step 0.8: 写 tmp/n12_scout_report.md**

```markdown
# N12 scout report — 2026-05-17

## 实测真值

- cwd: D:/Work/cad-spec-gen ✅
- branch: feat/n12-lint-scope-audit @ 0e3b181 ✅
- pyproject per-file-ignores globs: 12（与 spec §2.2 一致）
- ignore_errors=true modules: 4（adapters.solidworks.sw_detect / sw_config_lists_cache / cad_paths / tools.contract_io）
- ruff version: 0.15.10 ✅
- ruff strip per-file-ignores 后 E402 count: <填实测>
- ruff JSON filename: absolute Windows path ✅（B4 假设确认）
- stripped mypy 4 modules 各 error 数: <填实测>
- pytest baseline: <填实测，应 ≈ 3241>
- tools/dev/ 存在 + rebrand_test_archive.py 可参考 ✅

## Task 2-4 直接复用真值

- per-file-ignores glob 12 条原文（pyproject 直接抄）
- ignore_errors=true 4 module 列表（unit test 11 用）
- stripped pyproject 模板（unit test 11 + Task 4 实现 _make_mypy_stripped_config 用）
```

- [ ] **Step 0.9: Scout 与 spec 假设差异 check**

如果 Step 0.2-0.7 任一与 spec rev 1.3 假设不符 → **派单回主 agent 决策**：
  (a) inline 修 spec rev 1.4
  (b) 终止 Task 0
  (c) 调整 plan Task 1-5 假设
不主动修 spec / pyproject 任何文件。

**Task 0 验收：**
- [ ] tmp/n12_scout_report.md 含 7 项实测产物
- [ ] 无 spec 假设差异（如有差异已派单决策）

---

## Task 1: Setup — pyproject tomli dep + 测试文件骨架

**Files:**
- Modify: `pyproject.toml`（test extras +1 行）

- [ ] **Step 1.1: 修改 pyproject.toml 加 tomli py3.10 fallback**

Modify `pyproject.toml`，找到：

```toml
test = [
    "pytest>=7.0",
    "hypothesis>=6.0",
]
```

改为：

```toml
test = [
    "pytest>=7.0",
    "hypothesis>=6.0",
    "tomli; python_version < '3.11'",  # rev 1.1 M2 fix: lint_scope_audit.py py3.10 fallback
]
```

- [ ] **Step 1.2: 验证 pyproject.toml 语法**

Run:
```bash
.venv/Scripts/python.exe -c "import tomllib; tomllib.load(open('pyproject.toml','rb')); print('OK')"
```
Expected: `OK`

- [ ] **Step 1.3: 验证 ruff/mypy gate 仍 pass**

Run:
```bash
.venv/Scripts/ruff.exe check . 2>&1 | tail -3
```
Expected: `All checks passed!` 或 exit 0（pyproject 修改不应触发 ruff codes）

**Task 1 验收：**
- [ ] pyproject.toml `[project.optional-dependencies] test` 含 tomli; python_version<"3.11"
- [ ] tomllib.load 成功

---

## Task 2: TDD 纯函数 part 1 — parse + glob + filename normalize (8 unit tests RED→GREEN)

**Files:**
- Create: `tests/test_lint_scope_audit.py`（test 文件首版骨架 + 前 8 个 unit test）
- Create: `tools/dev/lint_scope_audit.py`（纯函数 part 1 实现）

- [ ] **Step 2.1: 创建 tests/test_lint_scope_audit.py 骨架**

Create `tests/test_lint_scope_audit.py`：

```python
"""§11-N12 lint scope audit tool tests.

Spec: docs/superpowers/specs/2026-05-17-lint-scope-audit-design.md rev 1.3
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# 项目根目录（spec rev 1.2 B5: smoke test 用 REPO_ROOT，避免 cad_paths.py 多副本歧义）
REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "tools" / "dev" / "lint_scope_audit.py"

# Import target (Task 2-4 实现后 import 才有效)
sys.path.insert(0, str(REPO_ROOT))
from tools.dev import lint_scope_audit as lsa  # noqa: E402
```

- [ ] **Step 2.2: 写 test 1 — load_ruff_config 解析**

追加到 `tests/test_lint_scope_audit.py`：

```python
def test_load_ruff_config_parses_globs_and_select():
    """spec §3.2: _load_ruff_config → (globs_to_codes, select_codes)"""
    pyproject = {
        "tool": {
            "ruff": {
                "lint": {
                    "select": ["E402", "F401"],
                    "per-file-ignores": {
                        "tests/*.py": ["E402"],
                        "cad/**/*.py": ["F403", "F405"],
                    },
                }
            }
        }
    }
    globs_to_codes, select_codes = lsa._load_ruff_config(pyproject)
    assert select_codes == ["E402", "F401"]
    assert globs_to_codes == {
        "tests/*.py": ["E402"],
        "cad/**/*.py": ["F403", "F405"],
    }
```

- [ ] **Step 2.3: 写 test 2 — missing section 契约**

追加：

```python
def test_load_ruff_config_missing_section_returns_none():
    """spec §3.2: 缺 [tool.ruff] → None（按设计契约）"""
    pyproject = {"tool": {"mypy": {}}}
    result = lsa._load_ruff_config(pyproject)
    assert result is None
```

- [ ] **Step 2.4: 写 test 3-4 — _match_glob 双星 + Windows path**

追加：

```python
def test_match_globs_handles_double_star():
    """spec §3.4 B4: ** = 任意 dir level (含 0 段)；* = 单段无 /"""
    assert lsa._match_glob("cad/**/*.py", "cad/end_effector/foo.py") is True
    assert lsa._match_glob("cad/**/*.py", "cad/foo.py") is True  # 0 dir level
    assert lsa._match_glob("cad/**/*.py", "adapters/parts/foo.py") is False
    assert lsa._match_glob("tests/*.py", "tests/foo.py") is True
    assert lsa._match_glob("tests/*.py", "tests/sub/foo.py") is False  # * 不跨 /


def test_match_globs_normalizes_windows_paths():
    """spec §3.4 B5: Windows \\ → /"""
    assert lsa._match_glob("cad/**/*.py", "cad\\end_effector\\foo.py") is True
    assert lsa._match_glob("tests/*.py", "tests\\foo.py") is True
```

- [ ] **Step 2.5: 写 test 5 — _normalize_ruff_filename**

追加：

```python
def test_normalize_ruff_filename_strips_absolute_prefix():
    """spec rev 1.2 B4: ruff JSON filename 是 absolute Windows path"""
    cwd = Path("D:/Work/cad-spec-gen")
    abs_path = "D:\\Work\\cad-spec-gen\\adapters\\parts\\bd_warehouse_adapter.py"
    result = lsa._normalize_ruff_filename(abs_path, cwd=cwd)
    assert result == "adapters/parts/bd_warehouse_adapter.py"
```

- [ ] **Step 2.6: 写 test 6-8 — _compute_ruff_drift 三 case**

追加：

```python
def test_compute_ruff_drift_over_permissive():
    """spec §3.3: glob 覆盖 file 但 (file, code) ∉ violations → over_permissive"""
    globs_to_codes = {"tests/*.py": ["E402"]}
    select_codes = ["E402"]
    violations: list[tuple[str, str]] = []  # 0 真违规
    over_permissive, missing_glob = lsa._compute_ruff_drift(globs_to_codes, select_codes, violations)
    assert ("tests/*.py", "E402") in over_permissive
    assert missing_glob == []


def test_compute_ruff_drift_missing_glob():
    """spec §3.3: violation 不被任何 glob cover → missing_glob"""
    globs_to_codes = {"tests/*.py": ["E402"]}
    select_codes = ["E402"]
    violations = [("adapters/parts/foo.py", "E402")]  # 不被 tests/*.py cover
    over_permissive, missing_glob = lsa._compute_ruff_drift(globs_to_codes, select_codes, violations)
    assert over_permissive == [("tests/*.py", "E402")]  # over_permissive 因为 violations 无 tests/*.py
    assert ("adapters/parts/foo.py", "E402") in missing_glob


def test_compute_ruff_drift_perfect_match():
    """spec §3.3: glob 与 violation 完全对齐 → 两类皆空"""
    globs_to_codes = {"tests/*.py": ["E402"]}
    select_codes = ["E402"]
    violations = [("tests/foo.py", "E402")]
    over_permissive, missing_glob = lsa._compute_ruff_drift(globs_to_codes, select_codes, violations)
    assert over_permissive == []
    assert missing_glob == []
```

- [ ] **Step 2.7: Run all 8 tests RED**

Run:
```bash
.venv/Scripts/python.exe -m pytest tests/test_lint_scope_audit.py -v 2>&1 | tail -20
```
Expected: All 8 fail with `ModuleNotFoundError: No module named 'tools.dev.lint_scope_audit'` (script not yet created)。

- [ ] **Step 2.8: 创建 tools/dev/lint_scope_audit.py 骨架 + part 1 实现**

Create `tools/dev/lint_scope_audit.py`：

```python
"""§11-N12 lint scope audit — pyproject lint scope drift 检测。

Spec: docs/superpowers/specs/2026-05-17-lint-scope-audit-design.md rev 1.3

检测 pyproject 声明的 lint scope vs 真实代码 lint 状态间的 drift：
- ruff: per-file-ignores 的 over_permissive / missing_glob
- mypy: [[tool.mypy.overrides]] ignore_errors=true 的 dischargeable
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    import tomllib  # py3.11+ stdlib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]  # py3.10 fallback


def _load_pyproject(path: Path | None = None) -> dict[str, Any]:
    """读 pyproject.toml 返回 dict（spec §3.2）"""
    if path is None:
        path = Path.cwd() / "pyproject.toml"
    with path.open("rb") as f:
        return tomllib.load(f)


def _load_ruff_config(pyproject: dict[str, Any]) -> tuple[dict[str, list[str]], list[str]] | None:
    """解 [tool.ruff.lint] → (globs_to_codes, select_codes)；缺段返 None"""
    ruff_lint = pyproject.get("tool", {}).get("ruff", {}).get("lint")
    if ruff_lint is None:
        return None
    select_codes = list(ruff_lint.get("select", []))
    globs_to_codes = dict(ruff_lint.get("per-file-ignores", {}))
    return globs_to_codes, select_codes


def _match_glob(glob: str, path: str) -> bool:
    """spec §3.4 rev 1.1 M1 + rev 1.2 B5: glob → regex (** → .* / * → [^/]* / ? → [^/]).

    Normalize Windows \\ → /；锚 ^ + $；不支持 char class [!abc] (N6)。
    """
    path_normalized = path.replace("\\", "/")
    # 逐字符构 regex：先 re.escape 整 glob，然后还原 *、**、? 的特殊语义
    parts: list[str] = []
    i = 0
    while i < len(glob):
        if glob[i] == "*":
            if i + 1 < len(glob) and glob[i + 1] == "*":
                parts.append(".*")  # ** = 任意（含 /）
                i += 2
            else:
                parts.append("[^/]*")  # * = 单段无 /
                i += 1
        elif glob[i] == "?":
            parts.append("[^/]")
            i += 1
        else:
            parts.append(re.escape(glob[i]))
            i += 1
    pattern = "^" + "".join(parts) + "$"
    return re.match(pattern, path_normalized) is not None


def _normalize_ruff_filename(filename: str, cwd: Path) -> str:
    """spec rev 1.2 B4: ruff JSON filename 是 absolute path；normalize 成 / 分隔 relative."""
    try:
        rel = Path(filename).resolve().relative_to(cwd.resolve())
    except ValueError:
        # 路径在 cwd 之外 → 用原值（带 /-分隔标准化）
        return filename.replace("\\", "/")
    return rel.as_posix()


def _compute_ruff_drift(
    globs_to_codes: dict[str, list[str]],
    select_codes: list[str],
    violations: list[tuple[str, str]],
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """spec §3.3: 返 (over_permissive, missing_glob)。

    - over_permissive: 遍 (glob, code)，若无任何 (file, code) ∈ violations 中 file 匹配 glob → over_permissive
    - missing_glob: 遍 (file, code) ∈ violations，若无任何 glob 满足 (path matches glob && code ∈ globs_to_codes[glob]) → missing_glob
    """
    over_permissive: list[tuple[str, str]] = []
    for glob, codes in globs_to_codes.items():
        for code in codes:
            if code not in select_codes:
                continue  # glob 覆盖的 code 不在 select 列表 → 不关心
            has_match = any(
                file_code == code and _match_glob(glob, file)
                for file, file_code in violations
            )
            if not has_match:
                over_permissive.append((glob, code))

    missing_glob: list[tuple[str, str]] = []
    for file, code in violations:
        covered = any(
            code in codes_for_glob and _match_glob(glob, file)
            for glob, codes_for_glob in globs_to_codes.items()
        )
        if not covered:
            missing_glob.append((file, code))

    return over_permissive, missing_glob
```

- [ ] **Step 2.9: Run all 8 tests GREEN**

Run:
```bash
.venv/Scripts/python.exe -m pytest tests/test_lint_scope_audit.py -v 2>&1 | tail -15
```
Expected: 8 passed。

- [ ] **Step 2.10: 验 ruff strict 对 script 自身**

Run:
```bash
.venv/Scripts/ruff.exe check tools/dev/lint_scope_audit.py
```
Expected: `All checks passed!`（spec AC-11）

**Task 2 验收：**
- [ ] tests/test_lint_scope_audit.py 含 8 unit test 全 PASS
- [ ] tools/dev/lint_scope_audit.py 6 函数已实现 (load_pyproject / load_ruff_config / match_glob / normalize_ruff_filename / compute_ruff_drift)
- [ ] ruff check script 自身 exit 0

---

## Task 3: TDD 纯函数 part 2 — mypy overrides + stripped config + render reports (5 unit tests)

**Files:**
- Modify: `tests/test_lint_scope_audit.py`（+5 unit tests）
- Modify: `tools/dev/lint_scope_audit.py`（+4 函数）

- [ ] **Step 3.1: 写 test 9-10 — _load_mypy_overrides 两形态**

追加到 `tests/test_lint_scope_audit.py`：

```python
def test_load_mypy_overrides_filters_ignore_errors_true():
    """spec §3.2 M8: 混合 strict=true + ignore_errors=true → 只返 ignore_errors=true"""
    pyproject = {
        "tool": {
            "mypy": {
                "overrides": [
                    {"module": "a.b.c", "strict": True},
                    {"module": "x.y.z", "ignore_errors": True},
                    {"module": "no_special.flag"},
                ]
            }
        }
    }
    assert lsa._load_mypy_overrides(pyproject) == ["x.y.z"]


def test_load_mypy_overrides_handles_module_list_or_string():
    """spec rev 1.2 M8: module = 'x' 与 module = ['x','y'] 两形态都展开"""
    pyproject = {
        "tool": {
            "mypy": {
                "overrides": [
                    {"module": ["m1", "m2"], "ignore_errors": True},
                    {"module": "m3", "ignore_errors": True},
                ]
            }
        }
    }
    assert lsa._load_mypy_overrides(pyproject) == ["m1", "m2", "m3"]
```

- [ ] **Step 3.2: 写 test 11 — _make_mypy_stripped_config**

追加：

```python
def test_make_mypy_stripped_config_removes_ignore_errors_blocks(tmp_path):
    """spec §3.2 B6: 保留 [tool.mypy] 主段 + strict=true；剥离 ignore_errors=true"""
    pyproject = {
        "tool": {
            "mypy": {
                "python_version": "3.10",
                "strict_optional": True,
                "warn_redundant_casts": True,
                "warn_unused_ignores": True,
                "ignore_missing_imports": True,
                "explicit_package_bases": True,
                "overrides": [
                    {"module": "keep.this", "strict": True},
                    {"module": "drop.this", "ignore_errors": True},
                ],
            }
        }
    }
    stripped_path = lsa._make_mypy_stripped_config(pyproject, tmp_dir=tmp_path)
    try:
        content = stripped_path.read_text(encoding="utf-8")
        assert "ignore_errors" not in content  # B6 关键：剥离
        assert "explicit_package_bases" in content  # 保留主段
        assert "python_version" in content
        assert "keep.this" in content  # strict=true override 保留
        assert "drop.this" not in content  # ignore_errors=true override 剥离
    finally:
        stripped_path.unlink(missing_ok=True)
```

- [ ] **Step 3.3: 写 test 12-13 — _render_ruff_report**

追加：

```python
def test_render_ruff_report_includes_both_sections():
    """spec §3.5: findings 非空 → markdown 含 over_permissive + missing_glob 两段"""
    over_permissive = [("tests/*.py", "E402")]
    missing_glob = [("adapters/parts/foo.py", "E402")]
    report = lsa._render_ruff_report(
        select_codes=["E402"],
        globs_to_codes={"tests/*.py": ["E402"]},
        over_permissive=over_permissive,
        missing_glob=missing_glob,
    )
    assert "# Lint scope audit — ruff" in report
    assert "over_permissive" in report
    assert "missing_glob" in report
    assert "tests/*.py" in report
    assert "adapters/parts/foo.py" in report


def test_render_ruff_report_empty_findings_shows_ok():
    """spec §3.5: findings 全空 → 显示 ✅ 无 drift"""
    report = lsa._render_ruff_report(
        select_codes=["E402"],
        globs_to_codes={},
        over_permissive=[],
        missing_glob=[],
    )
    assert "✅ 无 drift" in report
```

- [ ] **Step 3.4: Run all 13 tests RED for new + GREEN for old**

Run:
```bash
.venv/Scripts/python.exe -m pytest tests/test_lint_scope_audit.py -v 2>&1 | tail -20
```
Expected: 8 passed (Task 2) + 5 failed (new) with `AttributeError: module 'tools.dev.lint_scope_audit' has no attribute '_load_mypy_overrides'` etc.

- [ ] **Step 3.5: 实现 _load_mypy_overrides + _make_mypy_stripped_config + _render_ruff_report + _render_mypy_report**

追加到 `tools/dev/lint_scope_audit.py`（在文件末尾，main() 之前）：

```python
import tempfile
from datetime import date


def _load_mypy_overrides(pyproject: dict[str, Any]) -> list[str]:
    """spec §3.2 M8: 解 [[tool.mypy.overrides]] → ignore_errors=true 模块列表。
    
    每 override block 的 module 字段可为 str 或 list[str]，统一展开。
    """
    overrides = pyproject.get("tool", {}).get("mypy", {}).get("overrides", [])
    modules: list[str] = []
    for block in overrides:
        if not block.get("ignore_errors"):
            continue
        module = block.get("module")
        if isinstance(module, str):
            modules.append(module)
        elif isinstance(module, list):
            modules.extend(module)
    return modules


def _make_mypy_stripped_config(
    pyproject: dict[str, Any],
    tmp_dir: Path | None = None,
) -> Path:
    """spec §3.2 B6: 写 tempfile 保留 [tool.mypy] 主段 + strict=true overrides；
    剥离 ignore_errors=true overrides。返 tmp 文件路径，调用方负责清理。
    """
    mypy_section = pyproject.get("tool", {}).get("mypy", {}).copy()
    # 过滤 overrides — 保留 strict=true，剥离 ignore_errors=true
    overrides = mypy_section.get("overrides", [])
    kept_overrides = [b for b in overrides if not b.get("ignore_errors")]
    if "overrides" in mypy_section:
        mypy_section["overrides"] = kept_overrides

    # 渲染 TOML
    lines: list[str] = ["[tool.mypy]"]
    for key, val in mypy_section.items():
        if key == "overrides":
            continue
        if isinstance(val, bool):
            lines.append(f"{key} = {str(val).lower()}")
        elif isinstance(val, str):
            lines.append(f'{key} = "{val}"')
        elif isinstance(val, (int, float)):
            lines.append(f"{key} = {val}")
    for block in kept_overrides:
        lines.append("")
        lines.append("[[tool.mypy.overrides]]")
        for key, val in block.items():
            if isinstance(val, bool):
                lines.append(f"{key} = {str(val).lower()}")
            elif isinstance(val, str):
                lines.append(f'{key} = "{val}"')
            elif isinstance(val, list):
                items = ", ".join(f'"{x}"' for x in val)
                lines.append(f"{key} = [{items}]")
    content = "\n".join(lines) + "\n"

    fd, path = tempfile.mkstemp(suffix=".toml", dir=tmp_dir, text=True)
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        Path(path).unlink(missing_ok=True)
        raise
    return Path(path)


def _render_ruff_report(
    select_codes: list[str],
    globs_to_codes: dict[str, list[str]],
    over_permissive: list[tuple[str, str]],
    missing_glob: list[tuple[str, str]],
) -> str:
    """spec §3.5 + rev 1.3 N8: ruff drift markdown 报告（含 caveat）"""
    today = date.today().isoformat()
    parts: list[str] = []
    parts.append(f"# Lint scope audit — ruff ({today})")
    parts.append("")
    parts.append("## 配置摘要")
    parts.append(f"- select: {len(select_codes)} codes")
    parts.append(f"- per-file-ignores: {len(globs_to_codes)} globs")
    parts.append("")
    parts.append(f"## ⚠ over_permissive ({len(over_permissive)})")
    if over_permissive:
        for glob, code in over_permissive:
            parts.append(f"- `{glob}` covers `{code}` but no actual violations match")
        parts.append(
            "  - **caveat**：本工具 strip per-file-ignores 后计算真违规集合；"
            "安全删除 glob 前请人工 verify (1) future cleanup 不再需要该 path"
            " (2) 删后 `ruff check .` 仍 exit 0"
        )
    else:
        parts.append("- 无")
    parts.append("")
    parts.append(f"## ❌ missing_glob ({len(missing_glob)})")
    if missing_glob:
        for file, code in missing_glob:
            parts.append(f"- `{file}` violates `{code}` but no per-file-ignores glob covers it")
    else:
        parts.append("- 无")
    parts.append("")
    parts.append("## 结论")
    if not over_permissive and not missing_glob:
        parts.append("- ✅ 无 drift")
    else:
        msg_parts: list[str] = []
        if over_permissive:
            msg_parts.append(f"⚠ {len(over_permissive)} 项 over_permissive")
        if missing_glob:
            msg_parts.append(f"❌ {len(missing_glob)} 项 missing_glob")
        parts.append("- " + " / ".join(msg_parts))
    parts.append("")
    return "\n".join(parts)


def _render_mypy_report(
    all_modules: list[str],
    dischargeable: list[str],
    still_has_errors: list[tuple[str, int]],
) -> str:
    """spec §3.5 + rev 1.2 N7 + rev 1.3 M7: mypy drift markdown 报告"""
    today = date.today().isoformat()
    parts: list[str] = []
    parts.append(f"# Lint scope audit — mypy ({today})")
    parts.append("")
    parts.append("## 配置摘要")
    parts.append(f"- ignore_errors=true 模块：{len(all_modules)} 个")
    parts.append("")
    parts.append(f"## ✅ dischargeable ({len(dischargeable)})")
    if dischargeable:
        for module in dischargeable:
            parts.append(
                f"- `{module}` — stripped config + `mypy --strict -p {module}` exit 0；"
                "建议从 [[tool.mypy.overrides]] 出列"
            )
        parts.append(
            "  - **caveat**：本工具用 stripped config + `--disable-error-code=import-untyped`"
            " 判定。出列前请人工手测原 pyproject 下 `mypy --strict -p <module>` 实质 clean"
            "（确认不依赖外部 type stub），再 commit"
        )
    else:
        parts.append("- 无")
    parts.append("")
    parts.append(f"## ⚠ still has errors ({len(still_has_errors)})")
    if still_has_errors:
        for module, error_count in still_has_errors:
            parts.append(f"- `{module}` — stripped config 下 {error_count} errors；保留 ignore_errors=true 合理")
    else:
        parts.append("- 无")
    parts.append("")
    parts.append("## 结论")
    parts.append(
        f"- dischargeable: {len(dischargeable)} 项 / "
        f"still has errors: {len(still_has_errors)} 项 / "
        f"总计 {len(all_modules)} 模块"
    )
    parts.append("")
    return "\n".join(parts)
```

- [ ] **Step 3.6: Run all 13 tests GREEN**

Run:
```bash
.venv/Scripts/python.exe -m pytest tests/test_lint_scope_audit.py -v 2>&1 | tail -25
```
Expected: 13 passed。

- [ ] **Step 3.7: 验 ruff strict 对 script**

Run:
```bash
.venv/Scripts/ruff.exe check tools/dev/lint_scope_audit.py
```
Expected: exit 0。

**Task 3 验收：**
- [ ] tests/test_lint_scope_audit.py 含 13 unit test 全 PASS
- [ ] tools/dev/lint_scope_audit.py 10 函数已实现（part 1 + load_mypy_overrides + make_mypy_stripped_config + render_ruff_report + render_mypy_report）
- [ ] ruff strict 对 script 仍 exit 0

---

## Task 4: TDD subprocess + main() — 5 remaining tests（3 smoke + 2 error path）

**Files:**
- Modify: `tests/test_lint_scope_audit.py`（+5 tests）
- Modify: `tools/dev/lint_scope_audit.py`（+5 函数 + main）

- [ ] **Step 4.1: 写 test 14-16 — smoke tests (real_subprocess + mypy)**

追加到 `tests/test_lint_scope_audit.py`：

```python
@pytest.mark.real_subprocess
def test_ruff_subcommand_against_current_pyproject():
    """spec AC-2 + rev 1.2 M5/B5: smoke ruff 子命令 cwd=REPO_ROOT"""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "ruff"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, f"stderr={result.stderr}"
    assert "# Lint scope audit — ruff" in result.stdout
    assert "## 配置摘要" in result.stdout


@pytest.mark.real_subprocess
@pytest.mark.mypy
def test_mypy_subcommand_against_current_pyproject():
    """spec AC-3 + rev 1.2 N7 + rev 1.3 M10: 只断 4 模块名在报告中出现"""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "mypy"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, f"stderr={result.stderr}"
    assert "# Lint scope audit — mypy" in result.stdout
    # 不断言具体 error 数（跨平台 flake）；只断 4 模块名都列出
    for module in (
        "adapters.solidworks.sw_detect",
        "adapters.solidworks.sw_config_lists_cache",
        "cad_paths",
        "tools.contract_io",
    ):
        assert module in result.stdout, f"{module} 应在报告 dischargeable 或 still_has_errors 段"


@pytest.mark.real_subprocess
def test_all_subcommand_runs_both():
    """spec AC-4: all 子命令两段都跑"""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "all"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0
    assert "# Lint scope audit — ruff" in result.stdout
    assert "# Lint scope audit — mypy" in result.stdout
```

- [ ] **Step 4.2: 写 test 17-18 — error path (mock + tmp_path)**

追加：

```python
def test_ruff_missing_executable_exits_3(monkeypatch):
    """spec §4: ruff 不在 PATH → exit 3"""
    monkeypatch.setattr(shutil, "which", lambda name: None if name == "ruff" else "/usr/bin/" + name)
    with pytest.raises(SystemExit) as exc_info:
        lsa.main(["ruff"])
    assert exc_info.value.code == 3


def test_pyproject_missing_section_exits_2(tmp_path, monkeypatch):
    """spec §4: ruff 子命令缺 [tool.ruff] 段 → exit 2"""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc_info:
        lsa.main(["ruff"])
    assert exc_info.value.code == 2
```

- [ ] **Step 4.3: Run all 18 tests — RED for new 5**

Run:
```bash
.venv/Scripts/python.exe -m pytest tests/test_lint_scope_audit.py -v -m "not real_subprocess and not mypy" 2>&1 | tail -10
.venv/Scripts/python.exe -m pytest tests/test_lint_scope_audit.py -v -m "real_subprocess" 2>&1 | tail -10
```
Expected: 13 + 2 unit pass (Task 2-3) + 3 smoke fail（script no main / no _run_*）+ 2 error path fail（no main）。

- [ ] **Step 4.4: 实现 subprocess runners + dischargeable + main()**

追加到 `tools/dev/lint_scope_audit.py`（末尾）：

```python
import argparse
import json
import shutil
import subprocess
import sys


def _run_ruff_json(cwd: Path) -> list[tuple[str, str]]:
    """spec §3.2 B2+B4: 用 --config strip per-file-ignores 拿真违规；normalize filename"""
    if shutil.which("ruff") is None:
        print("Error: ruff not in PATH", file=sys.stderr)
        raise SystemExit(3)
    result = subprocess.run(
        [
            "ruff",
            "check",
            "--config",
            "lint.per-file-ignores={}",
            "--output-format=json",
            ".",
        ],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    # ruff 有 violation 时 returncode=1，无 violation 时=0；都是正常输出
    try:
        violations_raw = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"Error: ruff JSON parse failed (version mismatch?): {e}", file=sys.stderr)
        print(f"stdout sample: {result.stdout[:200]}", file=sys.stderr)
        raise SystemExit(4) from e
    violations: list[tuple[str, str]] = []
    for v in violations_raw:
        filename = _normalize_ruff_filename(v["filename"], cwd=cwd)
        code = v["code"]
        violations.append((filename, code))
    return violations


def _run_mypy_strict_per_module(module: str, stripped_config_path: Path, cwd: Path) -> tuple[bool, int]:
    """spec §3.2 B6+M6: stripped config + --disable-error-code=import-untyped。

    返 (is_clean, error_count)：is_clean = exit 0；error_count 取"Found N errors"或 0。
    """
    if shutil.which("mypy") is None:
        print("Error: mypy not in PATH", file=sys.stderr)
        raise SystemExit(3)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--strict",
            "--config-file",
            str(stripped_config_path),
            "--disable-error-code=import-untyped",
            "-p",
            module,
        ],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if result.returncode == 0:
        return True, 0
    # 解析 "Found N errors" 行
    match = re.search(r"Found (\d+) error", result.stdout)
    count = int(match.group(1)) if match else 0
    return False, count


def _compute_mypy_dischargeable(
    modules: list[str],
    results: list[tuple[bool, int]],
) -> tuple[list[str], list[tuple[str, int]]]:
    """spec §3.2: 返 (dischargeable, still_has_errors)"""
    dischargeable: list[str] = []
    still_has_errors: list[tuple[str, int]] = []
    for module, (is_clean, count) in zip(modules, results):
        if is_clean:
            dischargeable.append(module)
        else:
            still_has_errors.append((module, count))
    return dischargeable, still_has_errors


def _ensure_repo_root_cwd() -> Path:
    """spec rev 1.2 B5: cwd 不在 repo root → 尝试自动 cd；失败终止 exit 2"""
    cwd = Path.cwd()
    if (cwd / "pyproject.toml").exists():
        return cwd
    # 尝试从 __file__ 推
    script_root = Path(__file__).resolve().parent.parent.parent
    if (script_root / "pyproject.toml").exists():
        return script_root
    print("Error: cannot locate pyproject.toml; cwd must be repo root", file=sys.stderr)
    raise SystemExit(2)


def _cmd_ruff(cwd: Path) -> str:
    """ruff 子命令主逻辑：返 markdown 报告"""
    pyproject = _load_pyproject(cwd / "pyproject.toml")
    ruff_config = _load_ruff_config(pyproject)
    if ruff_config is None:
        print("Error: [tool.ruff] section missing in pyproject.toml", file=sys.stderr)
        raise SystemExit(2)
    globs_to_codes, select_codes = ruff_config
    violations = _run_ruff_json(cwd)
    over_permissive, missing_glob = _compute_ruff_drift(globs_to_codes, select_codes, violations)
    return _render_ruff_report(select_codes, globs_to_codes, over_permissive, missing_glob)


def _cmd_mypy(cwd: Path) -> str:
    """mypy 子命令主逻辑：返 markdown 报告"""
    pyproject = _load_pyproject(cwd / "pyproject.toml")
    modules = _load_mypy_overrides(pyproject)
    if not modules:
        return "# Lint scope audit — mypy\n\n无 ignore_errors=true 模块。\n"
    stripped_path = _make_mypy_stripped_config(pyproject)
    try:
        results = [_run_mypy_strict_per_module(m, stripped_path, cwd) for m in modules]
    finally:
        stripped_path.unlink(missing_ok=True)
    dischargeable, still_has_errors = _compute_mypy_dischargeable(modules, results)
    return _render_mypy_report(modules, dischargeable, still_has_errors)


def main(argv: list[str] | None = None) -> int:
    """argparse + dispatch；rev 1.2 M9: subparsers required=True"""
    parser = argparse.ArgumentParser(
        prog="lint_scope_audit",
        description="§11-N12 pyproject lint scope drift 检测（ruff per-file-ignores + mypy ignore_errors）",
    )
    subparsers = parser.add_subparsers(dest="cmd", required=True)
    subparsers.add_parser("ruff", help="检测 ruff per-file-ignores drift")
    subparsers.add_parser("mypy", help="检测 mypy ignore_errors drift")
    subparsers.add_parser("all", help="顺序跑 ruff + mypy")
    args = parser.parse_args(argv)

    cwd = _ensure_repo_root_cwd()

    if args.cmd == "ruff":
        print(_cmd_ruff(cwd))
    elif args.cmd == "mypy":
        print(_cmd_mypy(cwd))
    elif args.cmd == "all":
        # rev 1.2 M4: all 子命令 fallback wording — 若 ruff 段缺 → 跳过继续 mypy
        try:
            print(_cmd_ruff(cwd))
        except SystemExit as e:
            if e.code == 2:
                print("# Lint scope audit — all\n\n## ⚠ ruff 段跳过\n"
                      "pyproject.toml [tool.ruff] 段缺失 — ruff drift 检测不可用。\n")
            else:
                raise
        print("\n---\n")
        print(_cmd_mypy(cwd))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4.5: Run 全 18 tests GREEN**

Run:
```bash
.venv/Scripts/python.exe -m pytest tests/test_lint_scope_audit.py -v 2>&1 | tail -25
```
Expected: 18 passed。

- [ ] **Step 4.6: 验 ruff strict 对 script**

Run:
```bash
.venv/Scripts/ruff.exe check tools/dev/lint_scope_audit.py
```
Expected: exit 0（spec AC-11）

- [ ] **Step 4.7: 验本地 mypy --strict 对 script (AC-11 本地手测)**

Run:
```bash
.venv/Scripts/python.exe -m mypy --strict tools/dev/lint_scope_audit.py
```
Expected: `Success: no issues found in 1 source file`（spec AC-11 rev 1.1 M3）

**Task 4 验收：**
- [ ] tests/test_lint_scope_audit.py 18 tests 全 PASS
- [ ] tools/dev/lint_scope_audit.py main 函数完成；smoke tests pass
- [ ] ruff strict 对 script exit 0
- [ ] 本地 mypy --strict 对 script exit 0

---

## Task 5: AC-1 to AC-13 verification + commit 1 + commit 2

**Files:**
- 无新文件；本 task 跑 AC 验证 + git commit

- [ ] **Step 5.1: AC-1 — `--help` 列 3 subcommands**

Run:
```bash
.venv/Scripts/python.exe tools/dev/lint_scope_audit.py --help
```
Expected: exit 0；stdout 含 "ruff" / "mypy" / "all" subcommand 描述。

- [ ] **Step 5.2: AC-2 — ruff 子命令实跑**

Run:
```bash
.venv/Scripts/python.exe tools/dev/lint_scope_audit.py ruff
```
Expected: exit 0；stdout 起始 `# Lint scope audit — ruff`；含"## 配置摘要"。

- [ ] **Step 5.3: AC-3 — mypy 子命令实跑（实测 dischargeable=0）**

Run:
```bash
.venv/Scripts/python.exe tools/dev/lint_scope_audit.py mypy
```
Expected: exit 0；含 4 模块名（adapters.solidworks.sw_detect / sw_config_lists_cache / cad_paths / tools.contract_io）；dischargeable=0；still_has_errors=4。

- [ ] **Step 5.4: AC-4 — all 子命令两段**

Run:
```bash
.venv/Scripts/python.exe tools/dev/lint_scope_audit.py all
```
Expected: exit 0；含两段 (`# Lint scope audit — ruff` + `# Lint scope audit — mypy`)。

- [ ] **Step 5.5: AC-5 — unit tests 全 PASS**

Run:
```bash
.venv/Scripts/python.exe -m pytest tests/test_lint_scope_audit.py -m "not real_subprocess and not mypy" -v 2>&1 | tail -5
```
Expected: 15 passed（§5.1 13 + §5.2 后 2）

- [ ] **Step 5.6: AC-6 — real_subprocess smoke**

Run:
```bash
.venv/Scripts/python.exe -m pytest tests/test_lint_scope_audit.py -m "real_subprocess and not mypy" -v 2>&1 | tail -5
```
Expected: 2 passed。

- [ ] **Step 5.7: AC-7 — mypy smoke**

Run:
```bash
.venv/Scripts/python.exe -m pytest tests/test_lint_scope_audit.py -m "mypy" -v 2>&1 | tail -5
```
Expected: 1 passed。

- [ ] **Step 5.8: AC-8 — 全套件 baseline +18**

Run:
```bash
.venv/Scripts/python.exe -m pytest 2>&1 | tail -3
```
Expected: `3259 passed` 或 ≥ `3241 + 18 PASS`（baseline 3241 + 18 new tests = 3259）。

- [ ] **Step 5.9: AC-11 — ruff + mypy 对 script 本身**

Run:
```bash
.venv/Scripts/ruff.exe check tools/dev/lint_scope_audit.py
.venv/Scripts/python.exe -m mypy --strict tools/dev/lint_scope_audit.py
```
Expected: 两条都 exit 0。

- [ ] **Step 5.10: AC-13 — 当前 pyproject 实测无 missing_glob**

Run:
```bash
.venv/Scripts/python.exe tools/dev/lint_scope_audit.py ruff | grep -A 1 "missing_glob"
```
Expected: `## ❌ missing_glob (0)` + `- 无`（P3 收官状态）。

- [ ] **Step 5.11: Commit 1 — script + pyproject**

```bash
git add tools/dev/lint_scope_audit.py pyproject.toml
git commit -m "feat(dev-tools): tools/dev/lint_scope_audit.py — §11-N12 lint scope drift 检测

实现 spec rev 1.3 设计：
- 单 script + argparse subcommands (ruff / mypy / all)
- ruff: --config 'lint.per-file-ignores={}' inline strip per-file-ignores
        + filename abs→rel normalize (B4) + glob ** → .* regex 模式 (M1)
        + over_permissive / missing_glob 两类 drift
- mypy: _make_mypy_stripped_config tempfile 剥离 ignore_errors override (B6)
        + --disable-error-code=import-untyped 忽略外部库 stub 噪音 (M6)
        + mypy --config-file <stripped> --strict -p <dotted> (B3)
        + ignore_errors=true dischargeable / still_has_errors 二分
- cwd 显式 = repo root 防 cad_paths.py 多副本歧义 (B5)
- argparse subparsers required=True (M9)
- _load_mypy_overrides 处理 module 字段 str/list 两形态 (M8)
- 默认 informational mode (exit 0)；非 0 仅 missing-section/missing-exec/JSON-error
- pyproject.toml [project.optional-dependencies] test 加 tomli; python_version<'3.11' (M2)

闭合 §11-N12（v2.37.13b retro §3.3）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 5.12: Commit 2 — tests**

```bash
git add tests/test_lint_scope_audit.py
git commit -m "test(dev-tools): tests/test_lint_scope_audit.py — 18 tests cover §11-N12

15 unit（纯函数 + error path mock）+ 2 real_subprocess smoke + 1 mypy smoke = 18 tests：

unit (15):
- _load_pyproject / _load_ruff_config / _load_mypy_overrides 解析
- _match_glob 双星 + Windows path normalize
- _normalize_ruff_filename abs → rel
- _compute_ruff_drift over_permissive / missing_glob / perfect match
- _make_mypy_stripped_config 剥离 ignore_errors block
- _render_ruff_report 两段含 caveat / 空 findings ✅
- error path: ruff missing executable exit 3 / pyproject missing section exit 2

smoke (3):
- ruff 子命令对当前 pyproject 跑通 (exit 0 + markdown 头)
- mypy 子命令对当前 pyproject 跑通 (含 4 模块名；rev 1.3 M10：不断言 error 数)
- all 子命令两段都跑

baseline 3241 → 3259 PASS。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

**Task 5 验收：**
- [ ] AC-1 to AC-8 + AC-11 + AC-13 全 PASS
- [ ] git log 显示 2 个新 commit（feat + test）
- [ ] 工作树 clean（除 retro doc 未改）

---

## Task 6: Retro §3.3 N12 → closed + commit 3

**Files:**
- Modify: `docs/superpowers/reports/2026-05-17-v2-37-13b-ruff-cleanup-p3-retro.md`

- [ ] **Step 6.1: 修改 retro §3.3 N12 行**

Modify `docs/superpowers/reports/2026-05-17-v2-37-13b-ruff-cleanup-p3-retro.md`，找到（§3.3 "本 retro 新登记" 表）：

```markdown
| **§11-N12** | Task 0 scout 应枚举 per-file-ignores glob 候选文件数（P3 实施期发现 spec §3.1.D 漏 `adapters/parts` + `cad/end_effector` 共 8 个 E402 / 11 文件） | P4 cleanup spec 起 Task 0 |
```

改为：

```markdown
| **§11-N12** | Task 0 scout 应枚举 per-file-ignores glob 候选文件数（P3 实施期发现 spec §3.1.D 漏 `adapters/parts` + `cad/end_effector` 共 8 个 E402 / 11 文件） | ✅ **closed** — `tools/dev/lint_scope_audit.py` 落地（spec rev 1.3 / 4 轮审查 31 fix / 18 tests）；PR #<填> / merge SHA `<填>` / release tag `<填>`（命名 user 决策） |
```

(实施期填 PR# / merge SHA / release tag 三个占位 — rev 1.3 N9 fix)。

- [ ] **Step 6.2: 校验文件改动只 1 行**

Run:
```bash
git diff --stat docs/superpowers/reports/2026-05-17-v2-37-13b-ruff-cleanup-p3-retro.md
```
Expected: `1 file changed, 1 insertion(+), 1 deletion(-)` 或类似。

- [ ] **Step 6.3: Commit 3 — retro closure**

```bash
git add docs/superpowers/reports/2026-05-17-v2-37-13b-ruff-cleanup-p3-retro.md
git commit -m "docs(retro): v2.37.13b retro §3.3 N12 → closed

§11-N12 (Task 0 scout per-file-ignores enumeration 系统化) 闭合：
- tools/dev/lint_scope_audit.py 落地
- spec docs/superpowers/specs/2026-05-17-lint-scope-audit-design.md rev 1.3
- 4 轮 review 累计 31 fix（L1+L2+L3+L4+L5 全闭环）
- 18 tests（15 unit + 2 real_subprocess + 1 mypy smoke）

PR # / merge SHA / release tag 三处占位待 merge 后回填（rev 1.3 N9）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

**Task 6 验收：**
- [ ] retro doc §3.3 N12 行已改为 closed
- [ ] git log 显示 3 个新 commit (feat + test + docs)

---

## Task 7: Pre-PR final check — 全套件 + lint + branch push

**Files:**
- 无新文件；本 task 跑 final 验证 + push

- [ ] **Step 7.1: 全套件 PASS**

Run:
```bash
.venv/Scripts/python.exe -m pytest 2>&1 | tail -5
```
Expected: `3259 passed` (baseline 3241 + 18) + 0 failed + 同 baseline skipped 数。

- [ ] **Step 7.2: ruff-strict 全仓**

Run:
```bash
.venv/Scripts/ruff.exe check .
```
Expected: `All checks passed!`

- [ ] **Step 7.3: mypy-strict 仅 strict scope（不应触动 script）**

Run:
```bash
.venv/Scripts/python.exe -m mypy --strict -p adapters.solidworks.sw_config_broker
```
Expected: `Success: no issues found ...`（不应受 N12 PR 影响；spec AC-10）

- [ ] **Step 7.4: 检查 commit 数 + branch**

Run:
```bash
git log --oneline origin/main..HEAD
git branch --show-current
```
Expected: 8 commits ahead of main = 4 spec commits (rev 1.0/1.1/1.2/1.3: b4452cc / 6efc6ce / 1caf081 / 0e3b181) + 1 plan commit (本 plan 文档) + 3 implementation commits (feat / test / docs)；branch=`feat/n12-lint-scope-audit`。

- [ ] **Step 7.5: Push branch（如果用户授权）**

**注意**：CLAUDE.md 规定 "提交或推送只在用户要求时"。本 step 跑前需主 agent 确认用户授权 push。

Run（用户确认后）：
```bash
git push -u origin feat/n12-lint-scope-audit
```
Expected: push 成功，可 `gh pr create` 开 PR。

- [ ] **Step 7.6: gh pr create（如果用户授权）**

Run（用户确认后）：
```bash
gh pr create \
  --title "feat(dev-tools): §11-N12 lint_scope_audit.py — pyproject lint scope drift 检测" \
  --body "$(cat <<'EOF'
## 摘要

闭合 §11-N12（v2.37.13b retro §3.3 登记）— 实现 `tools/dev/lint_scope_audit.py` dev tool 检测 pyproject 声明的 lint scope vs 真实代码状态的 drift。

## 关键产出

- **新文件** `tools/dev/lint_scope_audit.py`（160 LOC，单 script + argparse subcommands `ruff` / `mypy` / `all`）
- **新文件** `tests/test_lint_scope_audit.py`（180 LOC，18 tests = 15 unit + 2 real_subprocess + 1 mypy smoke）
- **修改** `pyproject.toml`（test extras 加 `tomli; python_version<'3.11'`）
- **修改** `docs/superpowers/reports/2026-05-17-v2-37-13b-ruff-cleanup-p3-retro.md` §3.3 N12 → ✅ closed

## 算法亮点

- **ruff**：用 `--config 'lint.per-file-ignores={}'` inline strip per-file-ignores 拿真违规集合 → 两类 drift (over_permissive + missing_glob)
- **mypy**：用 tempfile stripped pyproject 剥离 `[[tool.mypy.overrides]] ignore_errors=true` blocks + `--disable-error-code=import-untyped` 忽略外部库 stub 噪音 → dischargeable / still_has_errors 二分
- **避坑**：两侧子命令绕过 pyproject self-suppress 陷阱（spec 4 轮审查 31 fix 实测验证）

## 项目北极星 5 gate

- ✅ 零配置（无新外部 dep / 内部 dev tool）
- ✅ 稳定可靠（CI 9/9 + pytest 0 regression）
- ✅ 结果准确（4 轮 spec 审查 31 fix；算法实测验证）
- N/A SW 装即用（dev tool 不动 SW backend）
- ✅ 傻瓜式操作（dev 调用 `python tools/dev/lint_scope_audit.py [ruff|mypy|all]`）

## 关联

- **spec**: `docs/superpowers/specs/2026-05-17-lint-scope-audit-design.md` rev 1.3
- **plan**: `docs/superpowers/plans/2026-05-17-lint-scope-audit.md`
- **关联 retro**: v2.37.13b retro §3.3 → N12 closed

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR 创建成功，gh 输出 PR URL。

**Task 7 验收：**
- [ ] 全套件 3259 passed
- [ ] ruff strict 全仓 exit 0
- [ ] mypy-strict gate 模块 exit 0（不退化）
- [ ] branch pushed（如授权）
- [ ] PR opened（如授权）

---

## §11-N12 闭合判定（实施后 user 确认）

- [ ] helper script `tools/dev/lint_scope_audit.py` 落地 ✅
- [ ] 测试覆盖 15 unit + 3 smoke = 18 ✅
- [ ] CI ruff-strict gate 守门脚本本身（mypy-strict 非 gate，本地手测，rev 1.1 M3）✅
- [ ] retro §3.3 N12 标记改 closed + 加 spec/PR/release 引用 ✅
- [ ] 文档复用入口（spec §9） ✅

实施期填 PR / merge SHA / release tag（rev 1.3 N9 占位）后正式收官。

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
