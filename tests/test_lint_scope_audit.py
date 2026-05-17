"""§11-N12 lint scope audit tool tests.

Spec: docs/superpowers/specs/2026-05-17-lint-scope-audit-design.md rev 1.3
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# 项目根目录（spec rev 1.2 B5: smoke test 用 REPO_ROOT，避免 cad_paths.py 多副本歧义）
REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "tools" / "dev" / "lint_scope_audit.py"

# Import target (Task 2-4 实现后 import 才有效)
sys.path.insert(0, str(REPO_ROOT))
from tools.dev import lint_scope_audit as lsa  # noqa: E402


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


def test_load_ruff_config_missing_section_returns_none():
    """spec §3.2: 缺 [tool.ruff] → None（按设计契约）"""
    pyproject = {"tool": {"mypy": {}}}
    result = lsa._load_ruff_config(pyproject)
    assert result is None


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


def test_normalize_ruff_filename_strips_absolute_prefix():
    """spec rev 1.2 B4: ruff JSON filename 是 absolute Windows path"""
    cwd = Path("D:/Work/cad-spec-gen")
    abs_path = "D:\\Work\\cad-spec-gen\\adapters\\parts\\bd_warehouse_adapter.py"
    result = lsa._normalize_ruff_filename(abs_path, cwd=cwd)
    assert result == "adapters/parts/bd_warehouse_adapter.py"


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


@pytest.mark.real_subprocess
def test_ruff_subcommand_against_current_pyproject():
    """spec AC-2 + rev 1.2 M5/B5: smoke ruff 子命令 cwd=REPO_ROOT"""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "ruff"],
        capture_output=True,
        text=True,
        encoding="utf-8",
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
        encoding="utf-8",
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
        encoding="utf-8",
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0
    assert "# Lint scope audit — ruff" in result.stdout
    assert "# Lint scope audit — mypy" in result.stdout


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
