"""验证 cad_pipeline 注册了 jury subcommand。

Task 2 of photo3d-jury plan：仅验证 subcommand 已注册到 argparse 入口；
photo3d_jury 主体（tools/photo3d_jury.py）由 Task 17 提供。当前阶段
入口需在 photo3d_jury 模块缺失时优雅退出（exit=99 + stderr 提示），
不能因 ImportError 把 cad_pipeline.py --help 整个炸掉。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_jury_subcommand_in_help() -> None:
    """python cad_pipeline.py --help 含 jury 子命令名称。"""
    result = subprocess.run(
        [sys.executable, "cad_pipeline.py", "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(PROJECT_ROOT),
        check=False,
    )
    assert result.returncode == 0, (
        f"cad_pipeline.py --help 应该返回 0；stderr={result.stderr!r}"
    )
    assert "jury" in (result.stdout or ""), (
        f"--help 输出应包含 jury 子命令；stdout={result.stdout!r}"
    )


def test_jury_subcommand_help_does_not_crash_on_missing_module() -> None:
    """jury 子命令在 tools.photo3d_jury 不存在时应优雅退出（exit=99），
    而不是因 ImportError 把进程炸掉。

    Task 17 之前 tools/photo3d_jury.py 不存在，但 jury 子命令必须已可调用。
    """
    result = subprocess.run(
        [sys.executable, "cad_pipeline.py", "jury"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(PROJECT_ROOT),
        check=False,
    )
    # tools.photo3d_jury 缺失时退出码为 99 + stderr 提示 TODO
    # 若 Task 17 已完成且模块存在，则进入 photo3d_jury.main()，可能返回其它码；
    # 这里只断言不是 Python 未捕获异常炸出来的退出码（通常 1/2 + traceback）。
    if result.returncode == 99:
        assert "Task 17" in result.stderr or "未实现" in result.stderr, (
            f"exit=99 时 stderr 应包含 Task 17 占位提示；stderr={result.stderr!r}"
        )
    # 任何返回码都不应有 Python traceback
    assert "Traceback" not in result.stderr, (
        f"jury 子命令不应抛未捕获异常；stderr={result.stderr!r}"
    )
