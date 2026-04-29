"""sw-smoke workflow 的 Windows runner 合同测试。"""

from __future__ import annotations

from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]
_SW_SMOKE = _ROOT / ".github" / "workflows" / "sw-smoke.yml"
_SETUP_CAD_ENV = _ROOT / ".github" / "actions" / "setup-cad-env" / "action.yml"


def test_sw_smoke_uses_powershell_not_bash_on_solidworks_runner():
    text = _SW_SMOKE.read_text(encoding="utf-8")

    assert "runs-on: [self-hosted, windows, solidworks]" in text
    assert "shell: bash" not in text
    assert text.count("shell: powershell") >= 7


def test_setup_cad_env_composite_uses_powershell_not_bash():
    text = _SETUP_CAD_ENV.read_text(encoding="utf-8")

    assert "using: composite" in text
    assert "shell: bash" not in text
    assert text.count("shell: powershell") == 3


def test_sw_smoke_artifacts_do_not_mask_primary_failure():
    text = _SW_SMOKE.read_text(encoding="utf-8")

    assert "if: always()" in text
    assert "if-no-files-found: warn" in text
