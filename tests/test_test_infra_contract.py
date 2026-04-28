"""测试基础设施治理契约。"""

from __future__ import annotations

from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]


def test_optional_marker_is_registered():
    text = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"optional:' in text


def test_packaging_smoke_does_not_skip_build_failures_on_ci():
    text = (_ROOT / "tests" / "test_packaging.py").read_text(encoding="utf-8")
    assert "_skip_or_fail_packaging" in text
    assert "os.environ.get(\"CI\")" in text


def test_ci_sync_materializes_then_checks_tracked_drift():
    text = (_ROOT / ".github" / "workflows" / "tests.yml").read_text(
        encoding="utf-8"
    )
    assert "python scripts/dev_sync.py || rc=$?" in text
    assert "git diff --exit-code -- AGENTS.md" in text
    assert "python scripts/dev_sync.py --check" in text


def test_local_runtime_noise_is_gitignored():
    ignore = (_ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in (".coverage", "htmlcov/", ".serena/"):
        assert pattern in ignore
