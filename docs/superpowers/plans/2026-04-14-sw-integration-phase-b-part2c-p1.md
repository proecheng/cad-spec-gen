# SolidWorks Phase SW-B Part 2c P1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 清理 Part 2b 最终 review 遗留的 Important-1 / Important-3，并落地 Minor-4 / Minor-6 两条基建重构（加 `@requires_solidworks` pytest marker + BOM material 规范化）；所有交付走 TDD，每 task 一个独立原子 commit，合 PR 前 7 个 CI job 全绿。

**Architecture:** 5 个原子 task 按 T1→T5 顺序执行。T1 是跨文件硬重命名（8 处），T2 新增测试基建 marker，T3/T4 在 `tools/sw_warmup.py` 同文件前后修（锁对齐常量化 + exit code 3 子类化），T5 收尾在 `bom_parser.py` 加 material 缺省字符串规范化。commit 之间无代码依赖，但按此顺序 rebase 摩擦最小。

**Tech Stack:** Python 3.11+ / pytest / pytest.raises / unittest.mock / `@pytest.mark.skipif` / pyproject.toml markers / msvcrt + fcntl

**Spec 锚点：** `docs/superpowers/specs/2026-04-14-sw-integration-phase-b-part2c-p1-design.md`（经 4 轮审查定稿：管道融合 / 硬编码与变量一致性 / 五角色 / 文字表述与衔接）

**分支：** `feat/sw-b-part2c-p1`（已基于 `main@0706e44` 创建）

---

## Task 0：环境确认 + 基线跑通

**Files:** 无（只读）

- [ ] **Step 1：确认当前分支 + 工作目录干净**

Run：
```bash
git status
git branch --show-current
pwd
```
Expected：
- `git status` 显示 `On branch feat/sw-b-part2c-p1` + `nothing to commit` 或只有 untracked `.claude/scheduled_tasks.lock`
- 当前分支名：`feat/sw-b-part2c-p1`
- 工作目录：`D:\Work\cad-spec-gen` 或 worktree 根路径

- [ ] **Step 2：确认 spec 文档已提交**

Run：
```bash
git log --oneline -3
```
Expected：首行应含 `docs(sw-b): Part 2c P1 设计文档（brainstorming 产出）` 或含 amend 后的 commit hash（如 `3af8c8a` 等）

- [ ] **Step 3：跑基线 SW 测试套件，确认起点全绿**

Run：
```bash
uv run pytest tests/test_sw_com_session.py tests/test_sw_toolbox_adapter.py tests/test_sw_toolbox_catalog.py tests/test_sw_toolbox_integration.py tests/test_sw_toolbox_adapter_registration.py tests/test_sw_warmup_orchestration.py tests/test_sw_warmup_lock.py tests/test_sw_warmup_bom_reader.py tests/test_sw_convert_worker.py tests/test_sw_com_session_subprocess.py tests/test_sw_detect.py tests/test_bom_parser.py -v --tb=short
```
Expected：所有测试 PASS，不会因 `real_subprocess` marker 或 missing SW 而 skip 过多（目标 >150 passed）。若出现 fail 先停下排查——本 plan 假设 Part 2c P0 squash 合并后基线稳定。

- [ ] **Step 4：记录基线通过测试数**

Run：
```bash
uv run pytest tests/ -v --tb=no -q 2>&1 | tail -5
```
Expected：记录类似 `XXX passed, YY skipped in ZZs` 的数字，作为 T1-T5 结束时回归对照基线。

---

## Task 1：T1 `_find_sldprt` → `find_sldprt` 硬重命名（8 处）

**Files:**
- Modify: `adapters/parts/sw_toolbox_adapter.py:204` — 方法定义
- Modify: `tools/sw_warmup.py:288, 298` — docstring + 调用
- Modify: `tests/test_sw_toolbox_adapter.py:341, 367, 380, 383, 395` — class docstring / 方法 docstring / 内部注释 / 2 处调用

### Step 1：先把既有 2 条测试改成新名字（预期红灯）

- [ ] **读原文件定位精确行**

Run：
```bash
uv run python -c "
from pathlib import Path
p = Path('tests/test_sw_toolbox_adapter.py')
for i, line in enumerate(p.read_text(encoding='utf-8').splitlines()[339:400], start=340):
    print(f'{i}: {line}')
" | head -70
```
Expected：看到 line 341 的 class docstring、line 367 的 `a._find_sldprt(...)`、line 395 的 `a._find_sldprt(...)`

- [ ] **Step 1a：改 `tests/test_sw_toolbox_adapter.py` 5 处**

改动清单（用 Edit 工具逐个替换，保持上下文唯一）：

1. Line 341 class docstring
   ```
   OLD: """v4 §5.3: _find_sldprt() 不触发 COM；供 sw-warmup --bom 复用。"""
   NEW: """v4 §5.3: find_sldprt() 不触发 COM；供 sw-warmup --bom 复用。"""
   ```
2. Line 367 第一条测试调用
   ```
   OLD:         result = a._find_sldprt(
   NEW:         result = a.find_sldprt(
   ```
3. Line 380 第二条测试 docstring
   ```
   OLD:         """_find_sldprt 不应导入/调用 win32com。"""
   NEW:         """find_sldprt 不应导入/调用 win32com。"""
   ```
4. Line 383 内部注释
   ```
   OLD:         # 破坏 win32com.client，证明 _find_sldprt 不依赖它
   NEW:         # 破坏 win32com.client，证明 find_sldprt 不依赖它
   ```
5. Line 395 第二条测试调用
   ```
   OLD:         result = a._find_sldprt(
   NEW:         result = a.find_sldprt(
   ```

- [ ] **Step 2：跑测试验证 RED**

Run：
```bash
uv run pytest tests/test_sw_toolbox_adapter.py::TestFindSldprt -v
```
Expected：2 条测试 **FAIL**，错误类型 `AttributeError: 'SwToolboxAdapter' object has no attribute 'find_sldprt'`（这是 TDD 的 RED 状态——测试调用还不存在的 public 方法）

### Step 3-4：实现 GREEN（重命名 + 更新 docstring）

- [ ] **Step 3：改 `adapters/parts/sw_toolbox_adapter.py:204` 方法定义 + docstring**

Edit 目标：
```python
OLD:
    def _find_sldprt(self, query, spec: dict):
        """匹配逻辑独立方法，供 sw-warmup --bom 复用。不触发 COM。

        从 resolve() 中抽出 step 1-6（索引加载 + 尺寸提取 + token 打分 + 路径校验），
        返回匹配结果元组，供外部调用方决定后续动作（COM 转换或其他）。

NEW:
    def find_sldprt(self, query, spec: dict):
        """公开的 sldprt 匹配 API（不触发 COM）。

        从 resolve() 中抽出 step 1-6（索引加载 + 尺寸提取 + token 打分 + 路径校验），
        返回匹配结果元组，供 sw-warmup --bom / 外部脚本 / 未来 sw-inspect 子命令
        等调用方决定后续动作（COM 转换或其他）。Part 2c P1 M-4：由私有 _find_sldprt
        升为 public API；调用 resolve() 的其他调用方若直接依赖此方法可直接使用。
```

（保留原函数体不变，只改 def 行 + docstring 前 4 行；后续 body 一字不动）

- [ ] **Step 4：改 `tools/sw_warmup.py` 两处**

Edit 1：line 288 docstring
```
OLD:     """读 BOM → 复用 SwToolboxAdapter._find_sldprt 找匹配 sldprt。
NEW:     """读 BOM → 复用 SwToolboxAdapter.find_sldprt 找匹配 sldprt。
```

Edit 2：line 298 调用
```
OLD:         match = adapter._find_sldprt(q, spec)
NEW:         match = adapter.find_sldprt(q, spec)
```

- [ ] **Step 5：跑测试验证 GREEN**

Run：
```bash
uv run pytest tests/test_sw_toolbox_adapter.py::TestFindSldprt -v
```
Expected：2 条测试 **PASS**

- [ ] **Step 6：全量 SW 套件回归**

Run：
```bash
uv run pytest tests/test_sw_toolbox_adapter.py tests/test_sw_toolbox_catalog.py tests/test_sw_toolbox_integration.py tests/test_sw_warmup_orchestration.py tests/test_sw_warmup_bom_reader.py -v --tb=short
```
Expected：全部 PASS，无新 fail

- [ ] **Step 7：grep 验收确认无残留**

Run：
```bash
uv run python -c "
import subprocess, sys
r = subprocess.run(
    ['rg', '_find_sldprt', 'adapters', 'tools', 'tests'],
    capture_output=True, text=True
)
print('STDOUT:', r.stdout or '<empty>')
print('RC:', r.returncode)
sys.exit(0 if not r.stdout.strip() else 1)
"
```
Expected：STDOUT `<empty>`、exit 0。若有残留，去掉该 callsite 再跑。

- [ ] **Step 8：Ruff 检查**

Run：
```bash
uv run ruff check adapters/parts/sw_toolbox_adapter.py tools/sw_warmup.py tests/test_sw_toolbox_adapter.py
uv run ruff format --check adapters/parts/sw_toolbox_adapter.py tools/sw_warmup.py tests/test_sw_toolbox_adapter.py
```
Expected：`All checks passed!` + format 无 diff

- [ ] **Step 9：Commit**

Run：
```bash
git add adapters/parts/sw_toolbox_adapter.py tools/sw_warmup.py tests/test_sw_toolbox_adapter.py
git commit -m "$(cat <<'EOF'
refactor(sw-b): SwToolboxAdapter._find_sldprt 升 public find_sldprt（Part 2b M-4）

8 处同步改动：
- adapters/parts/sw_toolbox_adapter.py:204 方法定义 + docstring
- tools/sw_warmup.py:288 docstring + :298 调用点
- tests/test_sw_toolbox_adapter.py 5 处（class docstring / 方法 docstring / 内部注释 / 2 处调用）

sw_toolbox_catalog.py:448 的历史注释保留，不属 API 契约；docs/ 下 2026-04-13-* 历史快照文档保持不动。
TDD 循环：先改测试（RED）→ 改实现（GREEN）→ 回归 + grep 验收。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2：T2 `@requires_solidworks` marker + conftest 自动 skip

**Files:**
- Modify: `pyproject.toml:70-76` — markers 列表追加
- Modify: `tests/conftest.py` 末尾追加 `pytest_collection_modifyitems` 钩子
- Create: `tests/test_requires_solidworks_marker.py` — pytester 参数化 3 类情形

### Step 1：先追加 marker 注册（基础设施）

- [ ] **Step 1：改 `pyproject.toml:70-76` markers 列表**

Edit 目标（加一行到 `markers` 列表末尾）：
```
OLD:
markers = [
    "fast: unit tests, <100ms each",
    "integration: full-chain tests",
    "slow: packaging/wheel-build tests, run on main/nightly only",
    "blender: real Blender headless smoke tests (v2.9.2+); auto-skip if Blender missing",
    "real_subprocess: 真 subprocess / 真 IO 集成测试，无需真实 SolidWorks，默认 pytest 不跑；需 -m real_subprocess",
]

NEW:
markers = [
    "fast: unit tests, <100ms each",
    "integration: full-chain tests",
    "slow: packaging/wheel-build tests, run on main/nightly only",
    "blender: real Blender headless smoke tests (v2.9.2+); auto-skip if Blender missing",
    "real_subprocess: 真 subprocess / 真 IO 集成测试，无需真实 SolidWorks，默认 pytest 不跑；需 -m real_subprocess",
    "requires_solidworks: 需真实 SolidWorks + pywin32；缺任一自动 skip（不报 fail）",
]
```

- [ ] **Step 2：验证 marker 注册生效**

Run：
```bash
uv run pytest --collect-only tests/test_sw_toolbox_adapter.py 2>&1 | grep -i "warning\|requires_solidworks" | head -5
```
Expected：无 `PytestUnknownMarkWarning.*requires_solidworks` 告警（证明 pyproject.toml 注册被 pytest 识别）

### Step 2：写失败测试（RED）

- [ ] **Step 3：创建 `tests/test_requires_solidworks_marker.py`**

Write 文件（新建）：
```python
"""@requires_solidworks marker 自动 skip 钩子行为测试（Part 2c P1 T2）。

用 pytester fixture 内联跑 3 类情形：
  1. 无 marker 的用例照常跑（baseline）
  2. 有 marker 且当前环境满足（Windows + pywin32 + SW installed）→ 照常跑
  3. 有 marker 且当前环境不满足 → skip，reason 精确枚举

通过 monkeypatch 切换 sys.platform 与 detect_solidworks 返回值模拟 3 种环境，
不依赖真 SolidWorks。
"""

from __future__ import annotations

import pytest

pytest_plugins = ["pytester"]


@pytest.fixture
def mock_sw_detect(monkeypatch):
    """返回一个工厂，让测试自选 SwInfo(installed, pywin32_available)。"""
    from adapters.solidworks import sw_detect

    def _set(installed: bool, pywin32_available: bool):
        sw_detect._reset_cache()
        fake = sw_detect.SwInfo(
            installed=installed, pywin32_available=pywin32_available
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake)

    return _set


class TestRequiresSolidworksMarker:
    """conftest.py 的 pytest_collection_modifyitems 钩子 3 类情形。"""

    def test_no_marker_runs_normally(self, pytester, mock_sw_detect, monkeypatch):
        """无 marker 的用例不受钩子影响。"""
        monkeypatch.setattr("sys.platform", "linux")
        mock_sw_detect(installed=False, pywin32_available=False)

        pytester.makepyfile(
            """
            def test_plain():
                assert 1 == 1
            """
        )
        result = pytester.runpytest("-v", "-rs")
        result.assert_outcomes(passed=1, skipped=0)

    def test_marker_satisfied_runs_normally(
        self, pytester, mock_sw_detect, monkeypatch
    ):
        """有 marker + 环境满足（假装装了 SW）→ 照常跑。"""
        monkeypatch.setattr("sys.platform", "win32")
        mock_sw_detect(installed=True, pywin32_available=True)

        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.requires_solidworks
            def test_needs_sw():
                assert True
            """
        )
        result = pytester.runpytest("-v", "-rs")
        result.assert_outcomes(passed=1, skipped=0)

    def test_marker_non_windows_skipped(
        self, pytester, mock_sw_detect, monkeypatch
    ):
        """非 Windows 平台 → skip，reason 精确匹配。"""
        monkeypatch.setattr("sys.platform", "linux")
        mock_sw_detect(installed=False, pywin32_available=False)

        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.requires_solidworks
            def test_needs_sw():
                assert True
            """
        )
        result = pytester.runpytest("-v", "-rs")
        result.assert_outcomes(passed=0, skipped=1)
        result.stdout.fnmatch_lines(["*非 Windows 平台*"])

    def test_marker_missing_pywin32_skipped(
        self, pytester, mock_sw_detect, monkeypatch
    ):
        """Windows 但缺 pywin32 → skip，reason = pywin32 缺。"""
        monkeypatch.setattr("sys.platform", "win32")
        mock_sw_detect(installed=True, pywin32_available=False)

        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.requires_solidworks
            def test_needs_sw():
                assert True
            """
        )
        result = pytester.runpytest("-v", "-rs")
        result.assert_outcomes(passed=0, skipped=1)
        result.stdout.fnmatch_lines(["*pywin32 缺*"])

    def test_marker_sw_not_installed_skipped(
        self, pytester, mock_sw_detect, monkeypatch
    ):
        """Windows + pywin32 但 SW 未装 → skip，reason = SolidWorks 未安装。"""
        monkeypatch.setattr("sys.platform", "win32")
        mock_sw_detect(installed=False, pywin32_available=True)

        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.requires_solidworks
            def test_needs_sw():
                assert True
            """
        )
        result = pytester.runpytest("-v", "-rs")
        result.assert_outcomes(passed=0, skipped=1)
        result.stdout.fnmatch_lines(["*SolidWorks 未安装*"])
```

**重要**：pytester 跑的内联测试会继承本仓库的 `tests/conftest.py`——钩子还没加，这些测试会因为"没有 skip 钩子"而跑过不被 skip。后面 Step 5 加钩子后才会按预期。

- [ ] **Step 4：跑测试验证 RED**

Run：
```bash
uv run pytest tests/test_requires_solidworks_marker.py -v
```
Expected：至少 3 条 skip-情形测试 **FAIL**（因为 conftest 还没加钩子，marker 不 skip），`test_no_marker_runs_normally` 和 `test_marker_satisfied_runs_normally` 可能 PASS。

### Step 3：实现 GREEN（追加 conftest 钩子）

- [ ] **Step 5：追加钩子到 `tests/conftest.py` 末尾**

Edit 目标：在文件末尾（现第 72 行后）追加——**不触碰** line 1-72 的现有 `isolate_cad_spec_gen_home` fixture 和 sys.path insert：

```
OLD (file ends with):
    current_hash = _dir_state_hash(_REAL_HOME_CAD_DIR)
    assert current_hash == _REAL_HOME_HASH_AT_START, (
        f"Real {_REAL_HOME_CAD_DIR} was modified during test.\n"
        f"  Before: {_REAL_HOME_HASH_AT_START}\n"
        f"  After:  {current_hash}\n"
        f"A code path bypassed the HOME monkeypatch — fixture breach!"
    )

NEW (追加在 assert 闭合的 `)` 后空一行加入):
    current_hash = _dir_state_hash(_REAL_HOME_CAD_DIR)
    assert current_hash == _REAL_HOME_HASH_AT_START, (
        f"Real {_REAL_HOME_CAD_DIR} was modified during test.\n"
        f"  Before: {_REAL_HOME_HASH_AT_START}\n"
        f"  After:  {current_hash}\n"
        f"A code path bypassed the HOME monkeypatch — fixture breach!"
    )


# ─── @requires_solidworks marker 自动 skip 钩子（Part 2c P1 T2） ───

def pytest_collection_modifyitems(config, items):
    """为 @pytest.mark.requires_solidworks 的 item 按需加 skip 标记。

    触发 skip 条件（任一满足，优先级从高到低）：
      1. sys.platform != "win32"（COM 是 Windows 独占）
      2. pywin32 (import win32com) 不可用
      3. adapters.solidworks.sw_detect.detect_solidworks().installed == False

    2 和 3 由运行时唯一事实源 sw_detect 统一回答（非 Windows 平台上
    detect_solidworks() 也返回 installed=False, pywin32_available=False，
    但显式检查 sys.platform 让 skip reason 更精确）。
    异常不吞：sw_detect 导入失败 → collection 失败，不 silent skip。
    """
    needs_sw = [
        it for it in items if it.get_closest_marker("requires_solidworks")
    ]
    if not needs_sw:
        return

    if sys.platform != "win32":
        reason = "requires_solidworks：非 Windows 平台"
    else:
        try:
            from adapters.solidworks.sw_detect import detect_solidworks
            info = detect_solidworks()
        except ImportError as exc:
            raise pytest.UsageError(
                f"sw_detect 导入失败：{exc}"
            ) from exc

        if info.pywin32_available and info.installed:
            return  # 真装了 SW，保留原样跑
        reason = "requires_solidworks：" + (
            "pywin32 缺" if not info.pywin32_available else "SolidWorks 未安装"
        )

    skip = pytest.mark.skip(reason=reason)
    for it in needs_sw:
        it.add_marker(skip)
```

**注意**：本文件 import 区已有 `import sys` 和 `import pytest`（line 14-18），直接复用，不再重复 import。

- [ ] **Step 6：跑测试验证 GREEN**

Run：
```bash
uv run pytest tests/test_requires_solidworks_marker.py -v
```
Expected：5 条全部 **PASS**（`test_no_marker_runs_normally` + `test_marker_satisfied_runs_normally` + 3 条 skip 情形）

- [ ] **Step 7：全量测试回归（确认新钩子不破坏现有测试）**

Run：
```bash
uv run pytest tests/ -v --tb=short 2>&1 | tail -15
```
Expected：passed 数 ≥ Task 0 基线（+5 条新测试）；无新 fail；skip 数可能略增（如有标过 marker 的既有测试，Linux 上会新 skip，但本 PR 不 backfill 故 0 增）

- [ ] **Step 8：--collect-only 验证无 UnknownMark 告警（QA Q5 验收）**

Run：
```bash
uv run pytest tests/ --collect-only 2>&1 | grep -c "PytestUnknownMarkWarning.*requires_solidworks"
```
Expected：输出 `0`

- [ ] **Step 9：Ruff**

Run：
```bash
uv run ruff check pyproject.toml tests/conftest.py tests/test_requires_solidworks_marker.py
uv run ruff format --check tests/conftest.py tests/test_requires_solidworks_marker.py
```
Expected：All checks passed + format 无 diff

- [ ] **Step 10：Commit**

Run：
```bash
git add pyproject.toml tests/conftest.py tests/test_requires_solidworks_marker.py
git commit -m "$(cat <<'EOF'
test(sw-b): @requires_solidworks pytest marker + conftest 自动 skip 钩子

- pyproject.toml: markers 追加 requires_solidworks（pytest 5 个 marker → 6 个）
- tests/conftest.py: 末尾追加 pytest_collection_modifyitems，不触碰既有 isolate_cad_spec_gen_home fixture 与 sys.path insert
- tests/test_requires_solidworks_marker.py: 用 pytester 参数化 5 类情形（无 marker / 满足 / 非 Windows / 缺 pywin32 / SW 未装）

skip reason 优先级：sys.platform != "win32" > pywin32_available > installed；异常不吞，sw_detect 导入失败 → UsageError。本 PR 不 backfill 既有测试，marker 留给 SW-B9 真实 COM 验收用例。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3：T3 msvcrt.locking seek + 字节数常量化（Part 2b I-3）

**Files:**
- Modify: `tools/sw_warmup.py` 顶部加 `_LOCK_OFFSET` / `_LOCK_NBYTES` 常量
- Modify: `tools/sw_warmup.py:137-143` 加 seek + 常量化 acquire
- Modify: `tools/sw_warmup.py:178-180` 常量化 release（配对修改）
- Create/Modify: `tests/test_sw_warmup_lock.py` 加 `test_acquire_seeks_to_zero_before_locking`

### Step 1：写失败测试（RED）

- [ ] **Step 1：追加测试到 `tests/test_sw_warmup_lock.py`**

先看现有测试文件结构：
```bash
uv run python -c "
from pathlib import Path
p = Path('tests/test_sw_warmup_lock.py')
print(p.read_text(encoding='utf-8'))"
```

然后在 `TestAcquireWarmupLock` class 内追加方法（建议末尾），使用 Edit 工具在 class 末尾追加：
```python
    def test_acquire_seeks_to_zero_before_locking(
        self, tmp_path, monkeypatch
    ):
        """Part 2b I-3: msvcrt.locking 前必须 fh.seek(0)；字节数 == _LOCK_NBYTES。

        验证 acquire 路径调用 msvcrt.locking 时：
          - 文件位置在 0（由 _LOCK_OFFSET 常量驱动）
          - 第 3 位置参数（nbytes）等于 _LOCK_NBYTES 模块常量
        """
        import os

        if os.name != "nt":
            pytest.skip("msvcrt 仅 Windows")

        import msvcrt
        from tools import sw_warmup as mod

        observed = {}

        def _fake_locking(fd, op, nbytes):
            # 通过 fd 反查当前 fh.tell() 不可靠；改用：测试拿到 fh 后先 seek 到 EOF，
            # 若实现正确（先 seek(0) 再 locking），fake 被调用时 fd 对应的文件位置
            # 仍在 0（acquire 内 seek 生效）。用 os.lseek 不改变 position 查询。
            observed["nbytes"] = nbytes
            observed["pos_at_call"] = os.lseek(fd, 0, 1)  # SEEK_CUR

        monkeypatch.setattr(msvcrt, "locking", _fake_locking)

        lock_path = tmp_path / "sw_warmup.lock"
        with mod.acquire_warmup_lock(lock_path):
            pass

        assert observed["pos_at_call"] == mod._LOCK_OFFSET, (
            f"acquire 未在 locking 前 seek 到 _LOCK_OFFSET={mod._LOCK_OFFSET}"
        )
        assert observed["nbytes"] == mod._LOCK_NBYTES, (
            f"acquire 的 locking 字节数 != _LOCK_NBYTES={mod._LOCK_NBYTES}"
        )
```

- [ ] **Step 2：跑测试验证 RED**

Run（Windows 本地）：
```bash
uv run pytest tests/test_sw_warmup_lock.py::TestAcquireWarmupLock::test_acquire_seeks_to_zero_before_locking -v
```
Expected：**FAIL**——`AttributeError: module 'tools.sw_warmup' has no attribute '_LOCK_OFFSET'`（或 `_LOCK_NBYTES`），因为常量还没加

Linux CI 上会 skip，不暴露问题——这是符合预期的（msvcrt Windows-only）。

### Step 3-5：实现 GREEN（常量 + acquire + release 三处配对改）

- [ ] **Step 3：加模块常量到 `tools/sw_warmup.py`**

Edit 目标（在 `_held_locks: set[str] = set()` 定义后加）：
```
OLD:
# 全局状态：追踪当前进程已持有的锁（同进程内防止重复 acquire）
_held_locks: set[str] = set()


# 列名别名表（值为标准化后的字段名，键为 BOM CSV 中可能出现的列名小写）

NEW:
# 全局状态：追踪当前进程已持有的锁（同进程内防止重复 acquire）
_held_locks: set[str] = set()


# 锁定的字节范围常量 — acquire 与 release 必须对齐同一 range，
# 否则 msvcrt release 成 no-op 导致句柄泄漏（Part 2b review I-3）。
_LOCK_OFFSET = 0
_LOCK_NBYTES = 1


# 列名别名表（值为标准化后的字段名，键为 BOM CSV 中可能出现的列名小写）
```

- [ ] **Step 4：改 acquire 路径（line 137-143 附近）**

Edit 目标（在 `if os.name == "nt":` 和 `import msvcrt` 之后，`msvcrt.locking` 之前加 seek，并把字面量 `1` 换成常量）：
```
OLD:
    fh = open(lock_path, "a+")
    try:
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)

NEW:
    fh = open(lock_path, "a+")
    try:
        if os.name == "nt":
            import msvcrt

            try:
                # msvcrt.locking 锁的是"从当前位置起 N 字节"。"a+" 模式 open 后
                # file position 默认在 EOF，锁会落在未知 offset；而释放路径已
                # seek 到 _LOCK_OFFSET 锁定 _LOCK_NBYTES 字节。acquire 与 release
                # 必须对齐同一 byte range，否则 release 成 no-op 导致锁句柄泄漏。
                # 修 Part 2b final review I-3。
                fh.seek(_LOCK_OFFSET)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, _LOCK_NBYTES)
```

- [ ] **Step 5：改 release 路径（line 178-180 附近）配对**

Edit 目标：
```
OLD:
            if os.name == "nt":
                import msvcrt

                try:
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)

NEW:
            if os.name == "nt":
                import msvcrt

                try:
                    fh.seek(_LOCK_OFFSET)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, _LOCK_NBYTES)
```

- [ ] **Step 6：跑测试验证 GREEN**

Run（Windows 本地）：
```bash
uv run pytest tests/test_sw_warmup_lock.py -v
```
Expected：**全部 PASS**（包括新 `test_acquire_seeks_to_zero_before_locking` + 既有 `test_concurrent_acquire_raises`）

- [ ] **Step 7：grep 验收——msvcrt.locking 第 3 参数不再出现字面量 1**

Run：
```bash
uv run python -c "
import re
from pathlib import Path
p = Path('tools/sw_warmup.py')
for i, line in enumerate(p.read_text(encoding='utf-8').splitlines(), start=1):
    if 'msvcrt.locking(' in line and re.search(r', 1\)', line):
        print(f'{i}: {line}  ← 残留字面量 1，FAIL')
else:
    print('OK：msvcrt.locking 调用均使用 _LOCK_NBYTES 常量')
"
```
Expected：`OK：msvcrt.locking 调用均使用 _LOCK_NBYTES 常量`

- [ ] **Step 8：Ruff**

Run：
```bash
uv run ruff check tools/sw_warmup.py tests/test_sw_warmup_lock.py
uv run ruff format --check tools/sw_warmup.py tests/test_sw_warmup_lock.py
```
Expected：All checks passed + format 无 diff

- [ ] **Step 9：Commit**

Run：
```bash
git add tools/sw_warmup.py tests/test_sw_warmup_lock.py
git commit -m "$(cat <<'EOF'
fix(sw-b): sw_warmup 首次 msvcrt.locking 前 fh.seek(0) + 字节数常量化（Part 2b I-3）

- 加模块常量 _LOCK_OFFSET=0 / _LOCK_NBYTES=1
- acquire 路径（msvcrt 分支）在 locking 前 fh.seek(_LOCK_OFFSET)
- release 路径配对改为 _LOCK_NBYTES（消除 acquire/release 字节数双份硬编码）
- POSIX fcntl 分支不改（fcntl.flock 锁整个文件，不看 file position）
- 新测试 test_acquire_seeks_to_zero_before_locking 用 os.lseek 查询 mock 被调时的 fd 位置

修前：acquire 在 "a+" 模式 EOF 位置锁 1 byte，release 在 offset 0 解 1 byte，解锁成 no-op 导致句柄泄漏到第 3 轮才暴露。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4：T4 exit code 3 + `WarmupLockContentionError` 子类（Part 2b I-1）

**Files:**
- Modify: `tools/sw_warmup.py` 顶部加 `WarmupLockContentionError` 类
- Modify: `tools/sw_warmup.py:147, 156` 两处 raise 换子类 + 结构化 PID
- Modify: `tools/sw_warmup.py:233-244` `run_sw_warmup` 加 exit 3 分支 + docstring 更新
- Modify: `tests/test_sw_warmup_lock.py` 升级既有 `test_concurrent_acquire_raises` + 加 POSIX 分支测试
- Modify: `tests/test_sw_warmup_orchestration.py` 加 3 条新单测

### Step 1：写失败测试（RED）

- [ ] **Step 1：在 `tests/test_sw_warmup_orchestration.py` 追加 3 条新单测**

在文件末尾追加（先看现有 import block 再复用）：
```python
# ─── Part 2c P1 T4: exit code 3 + WarmupLockContentionError ──────────────

class TestLockContentionExitCode:
    """run_sw_warmup 对 lock contention 专用 exit code 3（Part 2b I-1）。"""

    def test_WarmupLockContentionError_exposes_pid_attribute(self):
        """架构审查 A1：PID 作为结构化属性暴露，不用字符串反解。"""
        from tools.sw_warmup import WarmupLockContentionError

        exc = WarmupLockContentionError(pid="9999")
        assert exc.pid == "9999"
        assert "9999" in str(exc)
        assert isinstance(exc, RuntimeError)  # 子类关系保证反向兼容

    def test_run_sw_warmup_returns_3_on_lock_contention(
        self, tmp_path, monkeypatch, capsys
    ):
        """mock acquire_warmup_lock 抛 WarmupLockContentionError → rc == 3。"""
        from contextlib import contextmanager
        from tools import sw_warmup as mod

        @contextmanager
        def _raise_contention(_path):
            raise mod.WarmupLockContentionError(pid="1234")
            yield  # unreachable

        monkeypatch.setattr(mod, "acquire_warmup_lock", _raise_contention)
        monkeypatch.setattr(
            mod, "_default_lock_path", lambda: tmp_path / "sw_warmup.lock"
        )

        rc = mod.run_sw_warmup(_make_args(standard="GB"))
        assert rc == 3
        captured = capsys.readouterr()
        assert "1234" in captured.out  # PID 在输出

    def test_run_sw_warmup_returns_1_on_generic_runtimeerror(
        self, tmp_path, monkeypatch, capsys
    ):
        """_run_warmup_locked 抛裸 RuntimeError → rc == 1（回归保护）。"""
        from contextlib import contextmanager
        from tools import sw_warmup as mod

        @contextmanager
        def _noop_lock(_path):
            yield  # 正常获锁

        monkeypatch.setattr(mod, "acquire_warmup_lock", _noop_lock)
        monkeypatch.setattr(
            mod, "_default_lock_path", lambda: tmp_path / "sw_warmup.lock"
        )
        monkeypatch.setattr(
            mod,
            "_run_warmup_locked",
            lambda args: (_ for _ in ()).throw(RuntimeError("通用错误")),
        )

        rc = mod.run_sw_warmup(_make_args(standard="GB"))
        assert rc == 1
```

- [ ] **Step 2：升级既有 `tests/test_sw_warmup_lock.py::test_concurrent_acquire_raises`**

Edit 目标（找到现有测试的 `pytest.raises(RuntimeError, ...)` 位置）：
```
OLD:
            with pytest.raises(RuntimeError, match="另一个 sw-warmup 进程"):

NEW:
            # Part 2c P1 T4: 升级为精确子类断言 + 结构化 pid 属性
            import os
            from tools.sw_warmup import WarmupLockContentionError

            with pytest.raises(WarmupLockContentionError) as ei:
```

然后在 with 块后（缩进恢复到 class 级或 method 末尾）加断言：
```python
            assert ei.value.pid == str(os.getpid())
            assert "另一个 sw-warmup 进程" in str(ei.value)
```

（具体插入位置需对照测试现有结构——若 `pytest.raises` 块是最后一行且 class 在后有其他方法，把 assert 放在 `with pytest.raises(...)` context 的缩进外、method 的 `self` 作用域内。）

- [ ] **Step 3：加 POSIX fcntl 分支专用测试到 `tests/test_sw_warmup_lock.py`**

在 `TestAcquireWarmupLock` class 追加：
```python
    @pytest.mark.skipif(os.name == "nt", reason="POSIX fcntl 分支测试")
    def test_concurrent_acquire_raises_on_posix(self, tmp_path):
        """POSIX fcntl 分支：同进程两次 acquire → WarmupLockContentionError。"""
        import os
        from tools.sw_warmup import (
            acquire_warmup_lock,
            WarmupLockContentionError,
        )

        lock_path = tmp_path / "sw_warmup.lock"
        with acquire_warmup_lock(lock_path):
            with pytest.raises(WarmupLockContentionError) as ei:
                with acquire_warmup_lock(lock_path):
                    pass  # unreachable
            assert ei.value.pid == str(os.getpid())
```

**注意**：若文件顶部已有 `import os`，复用；否则加。

- [ ] **Step 4：跑测试验证 RED**

Run：
```bash
uv run pytest tests/test_sw_warmup_orchestration.py::TestLockContentionExitCode tests/test_sw_warmup_lock.py -v
```
Expected：新 3 条 `TestLockContentionExitCode.*` + `test_concurrent_acquire_raises_on_posix`（Linux 才跑）**全 FAIL**——`WarmupLockContentionError` 类还不存在；既有 `test_concurrent_acquire_raises` 也会 FAIL 因断言升级。

### Step 5-7：实现 GREEN

- [ ] **Step 5：加 `WarmupLockContentionError` 到 `tools/sw_warmup.py`**

Edit 目标（在 Task 3 加的 `_LOCK_NBYTES = 1` 之后、`BOM_COLUMN_ALIASES` 之前）：
```
OLD:
_LOCK_OFFSET = 0
_LOCK_NBYTES = 1


# 列名别名表（值为标准化后的字段名，键为 BOM CSV 中可能出现的列名小写）

NEW:
_LOCK_OFFSET = 0
_LOCK_NBYTES = 1


class WarmupLockContentionError(RuntimeError):
    """另一 sw-warmup 进程持有锁；调用方应返回 exit 3 而非 1。

    PID 作为结构化属性暴露，未来 sw-inspect 子命令（P2）可以直接
    `exc.pid` 读取，无需 `re.match(r"PID (\\d+)", str(exc))` 反解字符串。
    """

    _MSG_FMT = "另一个 sw-warmup 进程运行中 (PID {pid})"

    def __init__(self, pid: str):
        super().__init__(self._MSG_FMT.format(pid=pid))
        self.pid: str = pid


# 列名别名表（值为标准化后的字段名，键为 BOM CSV 中可能出现的列名小写）
```

- [ ] **Step 6：改 `acquire_warmup_lock` 两处 raise**

Edit 1（msvcrt 分支，line 147 附近）：
```
OLD:
            except OSError as e:
                fh.close()
                pid = lock_path.read_text(encoding="utf-8").strip() or "未知"
                raise RuntimeError(f"另一个 sw-warmup 进程运行中 (PID {pid})") from e

NEW:
            except OSError as e:
                fh.close()
                pid = lock_path.read_text(encoding="utf-8").strip() or "未知"
                raise WarmupLockContentionError(pid=pid) from e
```

Edit 2（fcntl 分支，line 156 附近）：
```
OLD:
            except (OSError, BlockingIOError) as e:
                fh.close()
                pid = lock_path.read_text(encoding="utf-8").strip() or "未知"
                raise RuntimeError(f"另一个 sw-warmup 进程运行中 (PID {pid})") from e

NEW:
            except (OSError, BlockingIOError) as e:
                fh.close()
                pid = lock_path.read_text(encoding="utf-8").strip() or "未知"
                raise WarmupLockContentionError(pid=pid) from e
```

- [ ] **Step 7：改 `run_sw_warmup` 加 exit 3 分支 + 更新 docstring**

Edit 目标（line 233-244 附近）：
```
OLD:
def run_sw_warmup(args) -> int:
    """sw-warmup 主入口（v4 §7）。

    Returns:
        0 成功 / 1 部分失败 / 2 前置失败
    """
    try:
        with acquire_warmup_lock(_default_lock_path()):
            return _run_warmup_locked(args)
    except RuntimeError as e:
        print(f"[sw-warmup] {e}")
        return 1

NEW:
def run_sw_warmup(args) -> int:
    """sw-warmup 主入口（v4 §7）。

    Returns:
        0 成功 / 1 部分失败 / 2 前置失败 / 3 锁争用（另一实例在运行）
    """
    try:
        with acquire_warmup_lock(_default_lock_path()):
            return _run_warmup_locked(args)
    except WarmupLockContentionError as e:
        print(f"[sw-warmup] {e}")
        return 3
    except RuntimeError as e:
        # 其它 RuntimeError 仍按"部分失败"处理，保持既有行为
        print(f"[sw-warmup] {e}")
        return 1
```

- [ ] **Step 8：跑测试验证 GREEN**

Run：
```bash
uv run pytest tests/test_sw_warmup_orchestration.py::TestLockContentionExitCode tests/test_sw_warmup_lock.py -v
```
Expected：**全部 PASS**（含 Windows 的 `test_concurrent_acquire_raises` 升级版 + Linux 才跑的 `test_concurrent_acquire_raises_on_posix`）

- [ ] **Step 9：全量回归（确保既有 0/1/2 return code 路径不破坏）**

Run：
```bash
uv run pytest tests/test_sw_warmup_orchestration.py tests/test_sw_warmup_lock.py tests/test_sw_warmup_bom_reader.py -v --tb=short
```
Expected：全部 PASS；特别确认 `test_failure_appends_error_log` / `test_mixed_success_fail_returns_1`（line 177/200）仍返回 1

- [ ] **Step 10：Ruff**

Run：
```bash
uv run ruff check tools/sw_warmup.py tests/test_sw_warmup_orchestration.py tests/test_sw_warmup_lock.py
uv run ruff format --check tools/sw_warmup.py tests/test_sw_warmup_orchestration.py tests/test_sw_warmup_lock.py
```
Expected：All checks passed + format 无 diff

- [ ] **Step 11：Commit**

Run：
```bash
git add tools/sw_warmup.py tests/test_sw_warmup_orchestration.py tests/test_sw_warmup_lock.py
git commit -m "$(cat <<'EOF'
feat(sw-b): sw_warmup exit code 3 区分 lock contention + WarmupLockContentionError 子类（Part 2b I-1）

- 新增 WarmupLockContentionError(RuntimeError) 子类，PID 作为结构化属性暴露
- acquire_warmup_lock 两处 raise（msvcrt + fcntl 分支）改抛子类
- run_sw_warmup 新加 except WarmupLockContentionError → return 3；裸 RuntimeError 仍 return 1（反向兼容）
- docstring 从 "0/1/2" 更新为 "0/1/2/3"
- 既有 test_concurrent_acquire_raises 升级为 pytest.raises(WarmupLockContentionError) + exc.pid 结构化断言
- 新加 test_concurrent_acquire_raises_on_posix（@skipif Windows）补 POSIX fcntl 分支覆盖
- 新加 test_WarmupLockContentionError_exposes_pid_attribute + test_run_sw_warmup_returns_3/1

下游 cad_pipeline.py 透传 exit code 无硬编码 rc == N，零改动。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5：T5 bom_parser material 9 条缺省规范化（Part 2b M-6）

**Files:**
- Modify: `bom_parser.py` 顶部加 `_MATERIAL_ABSENT_TOKENS` + `_normalize_material`
- Modify: `bom_parser.py:196` 调用点包一层
- Create: `tests/test_bom_parser_material_normalization.py`

### Step 1：写失败测试（RED）

- [ ] **Step 1：创建 `tests/test_bom_parser_material_normalization.py`**

Write 文件（新建）：
```python
"""BOM material 缺省字符串规范化测试（Part 2c P1 T5 / Part 2b M-6）。

_normalize_material 把工程 BOM 里的"无材质"惯用写法（CJK + 英文 + Excel 自动替换
后的全角破折号）统一归一为空字符串，下游视同 unset；真值（如 Q235B）保持原样。
"""

from __future__ import annotations

import pytest


# 9 条缺省 token：与 bom_parser._MATERIAL_ABSENT_TOKENS 对齐
# （"—" 是 U+2014 em dash；"——" 是 U+2014×2 两 em dash 连写）
@pytest.mark.parametrize(
    "raw",
    [
        "",
        "-",
        "—",        # U+2014
        "——",       # U+2014 × 2
        "/",
        "N/A",
        "n/a",
        "NA",
        "na",
        "无",
        "无材质",
    ],
)
def test_normalize_material_absent_tokens_return_empty(raw):
    """9 条（+3 大小写变体）缺省 token 都归一为 ""。"""
    from bom_parser import _normalize_material

    assert _normalize_material(raw) == ""


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, ""),              # 非 str 类型契约
        ("   ", ""),             # 纯空白 → strip 后 ""
        ("\tN/A\n", ""),         # 两端空白 + 缺省值
    ],
)
def test_normalize_material_edge_cases(raw, expected):
    """QA Q3：None / 纯空白 / 两端空白边界。"""
    from bom_parser import _normalize_material

    assert _normalize_material(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "Q235B",
        "45#",
        "7075-T6铝合金",
        "Al 6061-T6  硬质阳极氧化≥25μm",
        "S355JR",
    ],
)
def test_normalize_material_real_values_preserved(raw):
    """真值反例：不被误杀（T5 集合只 == 比较，非 substring）。"""
    from bom_parser import _normalize_material

    assert _normalize_material(raw) == raw.strip()
```

- [ ] **Step 2：跑测试验证 RED**

Run：
```bash
uv run pytest tests/test_bom_parser_material_normalization.py -v
```
Expected：**全 FAIL**——`ImportError: cannot import name '_normalize_material' from 'bom_parser'`

### Step 3：实现 GREEN

- [ ] **Step 3：加 `_MATERIAL_ABSENT_TOKENS` + `_normalize_material` 到 `bom_parser.py`**

先定位现有 `classify_part` 函数位置：
```bash
uv run python -c "
from pathlib import Path
p = Path('bom_parser.py')
for i, line in enumerate(p.read_text(encoding='utf-8').splitlines()[40:60], start=41):
    print(f'{i}: {line}')"
```

Edit 目标：在 `classify_part` 定义（line 47）之前插入常量和辅助函数：
```
OLD:
def classify_part(name: str, material: str = "") -> str:

NEW:
# Part 2c P1 T5：BOM material 缺省字符串规范化（M-6）
# 注意字符选择：所有 em dash 都是 U+2014。"——" 是两 em dash 连写（Excel 里输入 `--`
# 再被自动替换后的常见形态），不是 U+2500 BOX DRAWINGS。
# 机械设计师审查 D1：加 "na"（英制 BOM 无斜杠变体，与 "n/a" 并列为常见写法）。
_MATERIAL_ABSENT_TOKENS = frozenset(
    {"", "-", "—", "——", "/", "n/a", "na", "无", "无材质"}
)


def _normalize_material(raw: str | None) -> str:
    """把 BOM 里的"无材质"惯用写法统一为空字符串。

    Why：Excel 导出的 BOM 常见 "—"（U+2014 全角破折号，`--` 自动替换）/
    "N/A"/"无"等表示"无指定材质"。字面值传到下游：
      - classify_part 的 substring keyword match 会走 "other"（行为等效，
        但消耗一次字符串 upper）
      - cad_pipeline.py 的 material keyword preset match 会全 miss，走默认
        preset（行为等效）
      - 未来 sw_material_bridge 若加 by-name lookup 会 100% miss
    统一归一为 ""，让"缺省"在数据流里是显式状态，日志与观察一致。

    架构一致性：本模块 parse_price 已有 ("—", "-", "N/A") 的缺省集合先例；T5 把
    material 域的同类逻辑抽成显式辅助函数并扩展 CJK 写法。两者域不同
    （price / material）暂不合并——若未来第三个消费者出现，届时再抽通用
    _normalize_empty_strings(raw, tokens)。

    不区分大小写（"N/A" / "n/a" 等价）；strip 两端空白再比较。
    非缺省值（如 "Q235B"）只做 strip，返回原字符串。
    """
    if raw is None:
        return ""
    stripped = raw.strip()
    return "" if stripped.lower() in _MATERIAL_ABSENT_TOKENS else stripped


def classify_part(name: str, material: str = "") -> str:
```

**不改** `classify_part` 实现——`material=""` / `material="—"` 在 substring keyword match 下行为等效，单点规范化由 bom_parser.py:196 调用点保证。

- [ ] **Step 4：改 `bom_parser.py:196` 读 material 单元格后包一层**

先定位 line 196：
```bash
uv run python -c "
from pathlib import Path
p = Path('bom_parser.py')
for i, line in enumerate(p.read_text(encoding='utf-8').splitlines()[193:200], start=194):
    print(f'{i}: {line}')"
```

Edit 目标：
```
OLD:
                material = _strip_bold(cells[col_map.get("material", -1)]) if "material" in col_map and col_map["material"] < len(cells) else ""

NEW:
                material = _normalize_material(
                    _strip_bold(cells[col_map.get("material", -1)])
                    if "material" in col_map and col_map["material"] < len(cells)
                    else ""
                )
```

- [ ] **Step 5：跑 T5 新测试验证 GREEN**

Run：
```bash
uv run pytest tests/test_bom_parser_material_normalization.py -v
```
Expected：**全 PASS**（11 + 3 + 5 = 19 条参数化单测）

- [ ] **Step 6：跑既有 bom_parser 测试确认无回归**

Run：
```bash
uv run pytest tests/test_bom_parser.py -v --tb=short
```
Expected：全 PASS，无 classify 逻辑回归

- [ ] **Step 7：Ruff**

Run：
```bash
uv run ruff check bom_parser.py tests/test_bom_parser_material_normalization.py
uv run ruff format --check bom_parser.py tests/test_bom_parser_material_normalization.py
```
Expected：All checks passed + format 无 diff

- [ ] **Step 8：Commit**

Run：
```bash
git add bom_parser.py tests/test_bom_parser_material_normalization.py
git commit -m "$(cat <<'EOF'
fix(sw-b): bom_parser material 9 条缺省字符串规范化（Part 2b M-6 + smoke 2026-04-14 实证）

- _MATERIAL_ABSENT_TOKENS frozenset 覆盖：空串 / "-" / em dash "—"(U+2014) / 双 em dash "——" / "/" / "n/a" / "na" / "无" / "无材质"
- _normalize_material(raw: str|None) → str：strip + lower 后等值匹配 token → 归一为 ""
- bom_parser.py:196 读 material 单元格后包一层
- 不改 classify_part：substring match 下 "" / "—" 行为等效，一处规范化（bom_parser 调用点）符合 single source of truth
- 19 条参数化新单测覆盖 11 正例 + 3 边界（None / 纯空白 / 两端空白）+ 5 真值反例

架构一致性：bom_parser.parse_price 已有 ("—", "-", "N/A") 缺省集合先例；T5 抽成显式辅助函数并扩展 CJK 写法（域不同暂不合并）。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6：收尾 — 全量回归 + Push + PR

- [ ] **Step 1：全量 SW 测试套件 + 新测试**

Run：
```bash
uv run pytest tests/ -v --tb=short -k "sw_ or bom_parser or requires_solidworks" 2>&1 | tail -20
```
Expected：
- T1-T5 新增测试全 PASS
- 既有 SW 套件零回归
- Linux 上 `@requires_solidworks` 测试若有会 skip（本 PR 没 backfill 故 0 增）

- [ ] **Step 2：全量 pytest 跑（含非 SW）**

Run：
```bash
uv run pytest tests/ -v --tb=no -q 2>&1 | tail -5
```
Expected：passed 数 ≥ Task 0 基线 + ~24（T2 的 5 + T3 的 1 + T4 的 3 + T5 的 19 - 少量冗余）

- [ ] **Step 3：Ruff 全库**

Run：
```bash
uv run ruff check .
uv run ruff format --check .
```
Expected：All checks passed + format 无 diff

- [ ] **Step 4：查看 commit 历史**

Run：
```bash
git log --oneline main..HEAD
```
Expected：6 个 commit（spec + T1~T5）：
```
<hash> fix(sw-b): bom_parser material 9 条缺省字符串规范化...
<hash> feat(sw-b): sw_warmup exit code 3 区分 lock contention...
<hash> fix(sw-b): sw_warmup 首次 msvcrt.locking 前 fh.seek(0)...
<hash> test(sw-b): @requires_solidworks pytest marker...
<hash> refactor(sw-b): SwToolboxAdapter._find_sldprt 升 public...
<hash> docs(sw-b): Part 2c P1 设计文档（brainstorming 产出）
```

- [ ] **Step 5：推分支**

Run：
```bash
git push -u origin feat/sw-b-part2c-p1
```
Expected：新远端分支创建成功

- [ ] **Step 6：等 CI 7 个 job 跑完，确认全绿**

Run：
```bash
gh run list --branch feat/sw-b-part2c-p1 --limit 1
```
等几分钟后跑：
```bash
gh run view <run_id> | head
```
Expected：最终 `success`；7/7 job PASS（Part 2c P0 PR #1 修过 CI workflow 后稳定）

- [ ] **Step 7：开 PR**

Run：
```bash
gh pr create --base main --head feat/sw-b-part2c-p1 --title "feat(sw-b): Part 2c P1 — Part 2b review backlog 清理 + 基建重构" --body "$(cat <<'EOF'
## Summary

Part 2b 最终 review 遗留 I-1 / I-3 + Minor-4 / Minor-6 一并落地，无 SolidWorks 依赖的基建重构 + BOM 规范化。5 个原子 commit 各自独立可 review：

- **T1** `_find_sldprt` → `find_sldprt` 硬重命名（8 处文字同步，Part 2b M-4）
- **T2** `@requires_solidworks` pytest marker + conftest 自动 skip 钩子（SW-B9 先决条件）
- **T3** `sw_warmup.py` msvcrt.locking 前 fh.seek(0) + 字节数/offset 常量化（Part 2b I-3，消除 acquire/release 字节数双份硬编码）
- **T4** `sw_warmup.py` exit code 3 + `WarmupLockContentionError` 子类（Part 2b I-1，PID 作为结构化属性）
- **T5** `bom_parser.py` material 9 条缺省字符串规范化（Part 2b M-6 + 2026-04-14 SW smoke 实证）

## Spec

`docs/superpowers/specs/2026-04-14-sw-integration-phase-b-part2c-p1-design.md`（经 4 轮审查定稿）

## 范围外（defer）

- ③ BOM length regex fix — 单测可写，端到端复验需真 SW smoke，推迟到下次
- ⑤ P2：timeout 30→20s / packaging / sw-inspect 子命令 — 按用户明示排除

## Test plan

- [ ] `uv run pytest tests/ -v -k "sw_ or bom_parser or requires_solidworks"` 全绿
- [ ] `uv run ruff check . && uv run ruff format --check .` 通过
- [ ] CI 7 job（regression + ubuntu 3.10/3.11/3.12 + windows 3.10/3.11/3.12）全绿
- [ ] 本地 Windows 跑 `pytest tests/test_sw_warmup_lock.py::TestAcquireWarmupLock -v` 验 msvcrt 分支
- [ ] Linux CI 跑 `test_concurrent_acquire_raises_on_posix` 验 fcntl 分支
- [ ] `pytest tests/ --collect-only 2>&1 | grep -c "PytestUnknownMarkWarning.*requires_solidworks"` == 0

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected：返回 PR URL。

---

## Self-review checklist（在 writing-plans skill 提交前由写计划者填完）

- [x] **Spec coverage**：T1-T5 全部对应 spec 5 个 task；Task 0 基线 + Task 6 收尾额外覆盖"前置验证"和"合 PR 闭环"
- [x] **Placeholder 扫描**：
  - 无 "TBD" / "TODO" / "similar to Task N" / "appropriate error handling"
  - 每个 code block 都是完整可复制代码
  - 每个 Run 命令都有 Expected 输出
- [x] **Type/name 一致性**：
  - `find_sldprt`（T1 后）全文一致
  - `_LOCK_OFFSET` / `_LOCK_NBYTES`（T3 引入）T4 不再单独用字面量
  - `WarmupLockContentionError.pid: str`（T4）在测试里均以 str 断言
  - `_MATERIAL_ABSENT_TOKENS` / `_normalize_material`（T5）跨文件无别名
- [x] **Commit message 规范**：全部符合 `<type>(<scope>): 描述` + 中文 + `Co-Authored-By` trailer（CLAUDE.md 强制）
- [x] **TDD 顺序**：每 task RED→GREEN→（REFACTOR 嵌入）→ 回归 → commit
