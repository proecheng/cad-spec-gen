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
    """Track C 激活版路由必须通过 print() 输出决策（不得用 log.info()）。

    gen_parts.py 不调用 logging.basicConfig()，log.info() 会被静默丢弃。
    此测试防止回归到仅 log 的方式，保证路由结果在独立运行时可见。
    """
    gen_parts_src = (_REPO_ROOT / "codegen" / "gen_parts.py").read_text(encoding="utf-8")
    # Track C: 激活版使用 [routing] 而非旧版 [routing preview]
    assert "[routing]" in gen_parts_src, \
        "gen_parts.py must print '[routing]' for routing decisions"
    # 确认通过 print() 输出，不是 log.info()
    assert "print(" in gen_parts_src and "[routing]" in gen_parts_src, \
        "Routing decisions must use print() so they're visible without logging config"


def test_gen_parts_src_path_inserted():
    """gen_parts.py must insert src/ path before importing cad_spec_gen.parts_routing."""
    gen_parts_src = (_REPO_ROOT / "codegen" / "gen_parts.py").read_text(encoding="utf-8")
    assert "src" in gen_parts_src and "sys.path" in gen_parts_src, \
        "gen_parts.py must add src/ to sys.path for package resolution"


def test_gen_parts_routing_preview_is_observable_on_real_run(tmp_path):
    """端对端检查：gen_parts 对 CAD_SPEC 运行后必须输出可见的路由决策行。

    创建最小 CAD_SPEC.md，用 subprocess 以 force 模式运行 gen_parts，
    验证 '[routing]' 字符串出现在 stdout 中。
    此测试防止 log.info vs print 回归（Track C 激活版使用 [routing] 标签）。
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
    # Track C 激活版：应输出至少一行 [routing] 决策行
    assert "[routing]" in combined, (
        f"Expected '[routing]' in output, got:\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
