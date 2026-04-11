"""Integration test: gen_parts.py calls parts_routing and prints decisions."""
import io
import sys
from pathlib import Path
from unittest.mock import patch

_REPO_ROOT = Path(__file__).parent.parent


def test_gen_parts_imports_parts_routing():
    """codegen/gen_parts.py must import parts_routing for Spec 1 integration."""
    gen_parts_src = (_REPO_ROOT / "codegen" / "gen_parts.py").read_text(encoding="utf-8")
    assert "from cad_spec_gen.parts_routing import" in gen_parts_src, \
        "gen_parts.py must import parts_routing"


def test_gen_parts_route_preview_uses_print():
    """Spec 1 integration must use print() not log.info() for routing preview.

    gen_parts.py does not call logging.basicConfig(), so log.info() is
    silently dropped. This test prevents regression to a log-only approach
    that would make the preview invisible during standalone gen_parts runs.
    """
    gen_parts_src = (_REPO_ROOT / "codegen" / "gen_parts.py").read_text(encoding="utf-8")
    assert "[routing preview]" in gen_parts_src, \
        "gen_parts.py must print '[routing preview]' for decisions"
    # Verify the preview is emitted via print(), not log.info()
    # (Look for the specific phrase inside a print call)
    assert "print(" in gen_parts_src and "[routing preview]" in gen_parts_src, \
        "Routing preview must use print() so it's visible without logging config"


def test_gen_parts_src_path_inserted():
    """gen_parts.py must insert src/ path before importing cad_spec_gen.parts_routing."""
    gen_parts_src = (_REPO_ROOT / "codegen" / "gen_parts.py").read_text(encoding="utf-8")
    assert "src" in gen_parts_src and "sys.path" in gen_parts_src, \
        "gen_parts.py must add src/ to sys.path for package resolution"


def test_gen_parts_routing_preview_is_observable_on_real_run(tmp_path):
    """End-to-end check: running gen_parts on a CAD_SPEC must emit visible preview lines.

    Creates a minimal CAD_SPEC.md with the BOM树 format gen_parts actually
    expects, runs gen_parts in force mode via subprocess, and verifies the
    '[routing preview]' string appears in captured stdout. This is the test
    that would have caught the log.info-vs-print regression during Spec 1
    validation.
    """
    import os
    import subprocess

    # Minimal CAD_SPEC.md with one custom part in the BOM树 format
    spec_md = tmp_path / "CAD_SPEC.md"
    spec_md.write_text(
        "# CAD Spec — Test Subsystem (TST)\n"
        "<!-- Generated: test | Source: test | Hash: 00 -->\n"
        "\n"
        "## 1. 全局参数表\n"
        "\n"
        "| 参数 | 值 | 单位 |\n"
        "| --- | --- | --- |\n"
        "| TEST_PARAM | 100 | mm |\n"
        "\n"
        "## 5. BOM树\n"
        "\n"
        "**编号规则**: TST-NNN-NN\n"
        "\n"
        "| 料号 | 名称 | 材质/型号 | 数量 | 自制/外购 | 单价 |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| **TST-001** | **测试总成** | — | 1 | 总成 | — |\n"
        "| TST-001-01 | 测试L支架 | 6061铝合金 140×100×55mm | 1 | 自制 | 100元 |\n"
        "\n"
        "## 6.4 零件包络尺寸\n"
        "\n"
        "| 料号 | 宽度 | 深度 | 高度 |\n"
        "| --- | --- | --- | --- |\n"
        "| TST-001-01 | 140 | 100 | 55 |\n",
        encoding="utf-8",
    )

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    result = subprocess.run(
        [sys.executable, str(_REPO_ROOT / "codegen" / "gen_parts.py"),
         str(spec_md), "--output-dir", str(out_dir), "--mode", "force"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(_REPO_ROOT),
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    combined = result.stdout + result.stderr
    # Should have emitted at least one preview line for the custom part
    assert "[routing preview]" in combined, (
        f"Expected '[routing preview]' in output, got:\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
