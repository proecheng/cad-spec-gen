"""CI dev_sync gate 防漂移回归。

历史教训：v2.27→v2.31 共 5 PR 漏同步 src/cad_spec_gen/data/ 副本，旧 gate
用 'python scripts/dev_sync.py || rc=$?; if [ rc -gt 1 ]; then exit rc' 把
drift exit=1 吞掉，相当于在 runner 上偷偷修好。

本测试断言 .github/workflows/tests.yml 的 'Verify data/ mirrors' 步骤：
  1. 至少存在一个 dev_sync gate
  2. 每次调用 dev_sync.py 必须带 --check（不写入）
  3. 不得用 'rc=$?' 之类的 swallow 模式
"""

from __future__ import annotations

from pathlib import Path

import yaml


WORKFLOW_PATH = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "tests.yml"


def _collect_dev_sync_steps() -> list[dict]:
    """返回 tests.yml 所有 run 里调用了 dev_sync.py 的 step。"""
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    out: list[dict] = []
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            run = step.get("run") or ""
            if "dev_sync.py" in run:
                out.append(step)
    return out


def test_at_least_one_dev_sync_gate_exists() -> None:
    """tests.yml 必须至少有一个 dev_sync gate — 移除会让 src/.../data 漂移无人监管。"""
    steps = _collect_dev_sync_steps()
    assert steps, "tests.yml 缺 dev_sync gate"


def test_every_dev_sync_call_uses_check_flag() -> None:
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


def test_no_swallow_pattern() -> None:
    """禁止 'rc=$?' 风格吞掉 dev_sync exit=1 的旧 gate 模式。"""
    steps = _collect_dev_sync_steps()
    for step in steps:
        run = step["run"]
        assert "rc=$?" not in run, (
            f"step {step.get('name', '<unnamed>')!r} 用 'rc=$?' 吞掉 drift exit=1，"
            "改用直接 'python scripts/dev_sync.py --check'"
        )
