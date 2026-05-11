"""CP-7 Task 7.1.1：cad_pipeline enhance subcommand `--rerun-loop` flag argparse 集成测试。

用 subprocess 调 `python cad_pipeline.py enhance --help` 校验 flag 存在；
避免直接 import cad_pipeline 触发巨型脚本副作用（5000+ 行 god module）。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_enhance_help_includes_rerun_loop_flag() -> None:
    """`enhance --help` 输出含 `--rerun-loop` flag（OPS-MAJOR-3）。"""
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "cad_pipeline.py"), "enhance", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=PROJECT_ROOT,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, f"--help 应 exit 0；stderr={result.stderr}"
    assert "--rerun-loop" in result.stdout, (
        f"`enhance --help` 必须含 --rerun-loop flag；stdout 摘要：\n{result.stdout[:500]}"
    )
