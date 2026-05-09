# dev_sync 漂移修复 + CI gate fail-fast 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 提交工作树里 18 个 dev_sync 漂移文件 + 把 CI 的 dev_sync gate 从"runner 上偷偷修好"改成"drift fail-fast"，防止 v2.27→v2.31 的 5 PR 漏同步重演。

**Architecture:** 单 PR 三件套（chore: 同步 + ci: gate 改 --check + test: gate 回归测试）。无业务逻辑改动，无新依赖。

**Tech Stack:** scripts/dev_sync.py（已有 `--check` mode 完备）、`.github/workflows/tests.yml` + `sw-smoke.yml`、pytest + pyyaml（已是依赖）。

**根因分析（必读）：**

`tests.yml` 现有 gate 写的是：

```yaml
- name: Sync data/ mirrors
  shell: bash
  run: |
    rc=0
    python scripts/dev_sync.py || rc=$?           # ← 写入模式：drift 时它直接修好 src/.../data
    if [ "$rc" -gt 1 ]; then exit "$rc"; fi       # ← rc=1 不算 fail（吞掉 drift）
    git diff --exit-code -- AGENTS.md             # ← 只 check AGENTS.md
    python scripts/dev_sync.py --check            # ← 第二次：第一次已写完，必 PASS
```

修法：把第一次直接换成 `--check` → drift 当场 fail。

---

## File Structure

- **Modify**: `.github/workflows/tests.yml` — 两处 `Sync data/ mirrors` step（test job + regression job）
- **Modify**: `.github/workflows/sw-smoke.yml` — 若有同样模式则一起改
- **Create**: `tests/test_ci_dev_sync_gate.py` — 解析 yaml 防漂移回归测试

工作树里**已有的** 18 个 sync 改动是 dev_sync 的产物，本身不需要新增/修改文件，直接 commit。

---

## Task 1: 提交 18 个 sync 漂移文件

**Files:**
- Modify (already in working tree): 13 个 `cad/lifting_platform/std_*.py` + 5 个 `src/cad_spec_gen/data/tools/*`

- [ ] **Step 1: 切新分支**

```bash
git checkout -b fix/dev-sync-drift-and-ci-gate
git status --short  # 验证 18 个 M 文件
```

Expected: 18 个 modified 文件全在 working tree。

- [ ] **Step 2: 验证 dev_sync.py --check 在 commit 前是 fail（confirms drift exists）**

```bash
git stash                                                  # 临时移开 working tree 改动
python scripts/dev_sync.py --check; echo "exit=$?"         # 应 exit=1（drift 检测到）
git stash pop                                              # 恢复改动
python scripts/dev_sync.py --check; echo "exit=$?"         # 应 exit=0（与 canonical 一致）
```

Expected: stash 后 exit=1（13/18 drift），stash pop 后 exit=0。

- [ ] **Step 3: 暂存 + commit**

```bash
git add cad/lifting_platform/ src/cad_spec_gen/data/
git status --short  # 确认无遗漏
git commit -m "$(cat <<'EOF'
chore(packaging): 同步 v2.27→v2.31 累积的 dev_sync 漂移

PR #60 起 5 个 PR 都改了 canonical tools/ 但漏同步到 src/cad_spec_gen/data/
副本，导致 pip install 用户拿不到 jury / handoff jury hook / autopilot 自动检
测 / §11 cleanup / 渐进 KPI 等功能。

CI 的 'Sync data/ mirrors' 步骤在 runner 上写入模式吞掉了 drift（rc=$? + rc>1
判断让 exit=1 不算 fail），所以 PR 全绿但 main 历史一直漂。

本 commit 把 src/cad_spec_gen/data/tools/* 同步到与 canonical tools/* 一致；
下一 commit 修 CI gate 防止再次漂移。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: 1 commit，18 文件 changed。

---

## Task 2: 改 CI workflow gate 为 fail-fast

**Files:**
- Modify: `.github/workflows/tests.yml`（两处 `Sync data/ mirrors` step）
- Modify: `.github/workflows/sw-smoke.yml`（如有同模式）

- [ ] **Step 1: 检查 sw-smoke.yml 是否有同模式**

```bash
grep -n "dev_sync" .github/workflows/sw-smoke.yml
```

Expected: 若 grep 出 `python scripts/dev_sync.py`，按同方式改；若无，跳过 sw-smoke 修改。

- [ ] **Step 2: 改 tests.yml 的 test job gate（around line 51）**

把：

```yaml
      - name: Sync data/ mirrors
        shell: bash
        run: |
          rc=0
          python scripts/dev_sync.py || rc=$?
          if [ "$rc" -gt 1 ]; then exit "$rc"; fi
          git diff --exit-code -- AGENTS.md
          python scripts/dev_sync.py --check
```

替换为：

```yaml
      - name: Verify data/ mirrors are in sync
        shell: bash
        run: |
          # fail-fast：drift 直接 exit=1，不在 runner 上偷偷修复掩盖问题
          # （历史教训：v2.27→v2.31 共 5 PR 漏同步均被旧 gate 吞掉）
          python scripts/dev_sync.py --check
```

- [ ] **Step 3: 改 tests.yml 的 regression job gate（around line 100）**

同样替换 regression job 里的 `Sync data/ mirrors` 步骤为上面的 `Verify data/ mirrors are in sync` step。

- [ ] **Step 4: （若 Step 1 找到）改 sw-smoke.yml**

按 Step 2 同模式替换。

- [ ] **Step 5: 本地 lint workflow（可选）**

```bash
# 若装了 actionlint 跑一下；否则 git diff 肉眼检查
git diff .github/workflows/
```

Expected: yaml 缩进与上下文一致，无语法错。

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/
git commit -m "$(cat <<'EOF'
ci(dev-sync): 把 mirror gate 改成 --check fail-fast

旧 gate 用 'rc=\$? + rc>1' 让 dev_sync.py 默认写入模式 exit=1 被吞掉，相当于
runner 上偷偷修好 drift 让测试通过。结果：v2.27→v2.31 共 5 PR 都漏同步到
src/cad_spec_gen/data/* 副本但 CI 全绿，pip install 用户拿不到新功能。

新 gate 直接调 'python scripts/dev_sync.py --check'：drift 当场 exit=1，
PR 必须本地跑 dev_sync.py 后再推。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 加 CI gate 防漂移回归测试

**Files:**
- Create: `tests/test_ci_dev_sync_gate.py`

- [ ] **Step 1: 写失败测试（TDD red）**

```python
"""CI dev_sync gate 防漂移回归。

历史教训：v2.27→v2.31 共 5 PR 漏同步 src/cad_spec_gen/data/ 副本，旧 gate
用 'python scripts/dev_sync.py || rc=$?; if [ rc -gt 1 ]; then exit rc' 把
drift exit=1 吞掉，相当于在 runner 上偷偷修好。

本测试断言 .github/workflows/tests.yml 的 'Verify data/ mirrors' 步骤：
  1. 调用 dev_sync.py 时必须带 --check（不写入）
  2. 不得用 'rc=\$?' 之类的 swallow 模式
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


WORKFLOW_PATH = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "tests.yml"


def _collect_dev_sync_steps() -> list[dict]:
    """返回所有 run 里调用了 dev_sync.py 的 step。"""
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    out = []
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            run = step.get("run") or ""
            if "dev_sync.py" in run:
                out.append(step)
    return out


def test_at_least_one_dev_sync_gate_exists():
    """tests.yml 必须至少有一个 dev_sync gate（test 或 regression job）。"""
    steps = _collect_dev_sync_steps()
    assert steps, "tests.yml 缺 dev_sync gate — 移除会让 src/.../data 漂移无人监管"


def test_every_dev_sync_call_uses_check_flag():
    """每次调用 dev_sync.py 必须带 --check（防 runner 写入吞 drift）。"""
    steps = _collect_dev_sync_steps()
    for step in steps:
        run = step["run"]
        for line in run.splitlines():
            stripped = line.strip()
            if "python scripts/dev_sync.py" in stripped and not stripped.startswith("#"):
                assert "--check" in stripped, (
                    f"step {step.get('name', '<unnamed>')!r} 调用 dev_sync.py 缺 --check：\n"
                    f"  {stripped}\n"
                    "禁止默认（写入）模式：runner 会偷偷修 drift 让 PR 假绿。"
                )


def test_no_swallow_pattern():
    """禁止 'rc=$?' 风格吞掉 dev_sync exit=1 的旧 gate 模式。"""
    steps = _collect_dev_sync_steps()
    for step in steps:
        run = step["run"]
        # 历史 anti-pattern：rc=0 / rc=$? + if [ rc -gt 1 ]
        assert "rc=$?" not in run, (
            f"step {step.get('name', '<unnamed>')!r} 用 'rc=$?' 吞掉 drift exit=1，"
            "改用直接 'python scripts/dev_sync.py --check'"
        )
```

- [ ] **Step 2: 跑测试验证 GREEN（Task 2 已修 gate，这步应 pass）**

```bash
python -m pytest tests/test_ci_dev_sync_gate.py -v
```

Expected: 3 PASS。

- [ ] **Step 3: 故意倒退验证测试真的会 RED**

```bash
# 临时把 --check 删掉
sed -i.bak 's/python scripts\/dev_sync.py --check/python scripts\/dev_sync.py/' .github/workflows/tests.yml
python -m pytest tests/test_ci_dev_sync_gate.py -v  # 应 FAIL
mv .github/workflows/tests.yml.bak .github/workflows/tests.yml
python -m pytest tests/test_ci_dev_sync_gate.py -v  # 应 PASS 复原
```

Expected: 倒退后 `test_every_dev_sync_call_uses_check_flag` FAIL，复原后 PASS。

- [ ] **Step 4: 全量回归（确保未引入其他 fail）**

```bash
python -m pytest tests/ -x -q --tb=short -m "not mypy" 2>&1 | tail -20
```

Expected: 无新增 fail（基线 2725 PASS）。

- [ ] **Step 5: Commit**

```bash
git add tests/test_ci_dev_sync_gate.py
git commit -m "$(cat <<'EOF'
test(ci): 加 dev_sync gate 防漂移回归测试

解析 .github/workflows/tests.yml，断言每次 dev_sync.py 调用都带 --check 且不
含 'rc=\$?' 吞 drift 模式。下次有人改回旧 gate 时本测试立即 fail。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: 推 PR + 验证 CI 真的会 fail-on-drift

**Files:** （无文件改动）

- [ ] **Step 1: 本地完整 mirror CI 跑一次**

```bash
python scripts/dev_sync.py --check                          # exit=0
python -m pytest tests/test_ci_dev_sync_gate.py tests/test_dev_sync_check.py -v  # all PASS
```

Expected: 全 PASS。

- [ ] **Step 2: push 分支**

```bash
git push -u origin fix/dev-sync-drift-and-ci-gate
```

- [ ] **Step 3: 开 PR**

```bash
gh pr create --title "fix(packaging): 修复 dev_sync 漂移 + CI gate 改 fail-fast" --body "$(cat <<'EOF'
## Summary

- v2.27→v2.31 共 5 PR 漏同步 canonical `tools/` → `src/cad_spec_gen/data/tools/` 副本，pip install 用户拿不到 jury / handoff hook / autopilot / 渐进 KPI 等
- CI 旧 gate 用 `rc=$?` + 写入模式偷偷修好 drift，让 PR 假绿
- 本 PR：①commit 18 个累积 sync 改动 ②CI gate 换成 `--check` fail-fast ③加防回归测试

## Test plan

- [ ] CI tests job (Linux × 3.10/3.11/3.12) 全绿
- [ ] CI tests job (Windows × 3.10/3.11/3.12) 全绿
- [ ] CI regression job 全绿
- [ ] CI mypy-strict job 全绿
- [ ] 验证 fail-fast：本地临时 revert 1 个 sync 文件 → `python scripts/dev_sync.py --check` exit=1
- [ ] 测试 `tests/test_ci_dev_sync_gate.py` 3/3 PASS

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 4: 等 CI + 验证 fail-fast 真起作用**

回到 PR url 看 8 个 CI job 全绿。如想真测 fail-fast，可以本地起个 second branch 故意 revert 1 个 sync 文件 push 上去看 CI 立即 fail（可选验证，merge 前回滚）。

- [ ] **Step 5: merge + 发版（用户决策）**

合并后建议 tag v2.31.1（packaging hotfix）+ GitHub Release notes 注明"修复 v2.27→v2.31 累积的 pip install 副本漂移"。

---

## 北极星 5 gate 自检

- **零配置** ✓ 无新 user-facing config
- **稳定可靠** ✓ CI gate fail-fast 防回归 + 121 行已有 dev_sync test 不动
- **结果准确** ✓ pip install 用户拿到与 canonical 一致的代码
- **SW 装即用** ✓ 不涉及 SW
- **傻瓜式操作** ✓ 用户感知不到（packaging-only）

---

## 风险 + 缓解

1. **本地 dev 用户跑 dev_sync 已习惯写入模式** — 仍可直接 `python scripts/dev_sync.py`（无 `--check`）做本地 sync；只是 CI 不再代劳。
2. **若 sw-smoke.yml 也有 gate 但本 PR 漏改** — Task 2 Step 1 grep 会发现；如发现就一起改。
3. **新增 yaml 解析依赖 pyyaml** — 已是 tests.yml 现有 deps（`pip install jinja2 pyyaml psutil`），零新增。

---

## Self-Review Checklist

**1. Spec coverage：** 用户选项是"修同步漂移 + 加 CI gate"。Task 1 = 漂移修复，Task 2-3 = gate 改造 + 防回归。Task 4 = 验证。✓

**2. Placeholder scan：** 无 TBD/TODO/"add appropriate"。每个 commit 信息、yaml 改动、测试代码都是完整可执行的。✓

**3. Type consistency：** 测试函数签名一致；workflow yaml step 名 `Verify data/ mirrors are in sync` 在 Task 2 Step 2 + Step 3 + Task 3 测试断言里都用同一字符串。✓
