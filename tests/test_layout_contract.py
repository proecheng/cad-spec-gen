from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _product_graph(instances: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "run_id": "RUN001",
        "subsystem": "demo",
        "instances": instances,
    }


def test_layout_contract_reports_unlaid_out_and_orphan_overrides_by_instance_id():
    from tools.layout_contract import build_layout_contract

    contract = build_layout_contract(
        _product_graph([
            {"instance_id": "P-100-01#01", "part_no": "P-100-01", "render_policy": "required"},
            {"instance_id": "P-100-02#01", "part_no": "P-100-02", "render_policy": "required"},
            {"instance_id": "P-100-03#01", "part_no": "P-100-03", "render_policy": "excluded"},
        ]),
        generated_files=["assembly.generated.py", "assembly.py"],
        manual_overrides=[
            {"assembly_name": "human_alias_a", "instance_id": "P-100-01#01"},
            {"assembly_name": "legacy_alias", "instance_id": "P-999-01#01"},
        ],
        force_layout=False,
    )

    assert contract["product_instances"] == ["P-100-01#01", "P-100-02#01"]
    assert contract["unlaid_out_instances"] == ["P-100-02#01"]
    assert contract["orphan_overrides"] == ["P-999-01#01"]
    assert contract["status"] == "blocked"
    assert contract["warnings"][0]["code"] == "unlaid_out_instances"
    assert contract["instance_mapping"] == [
        {"assembly_name": "human_alias_a", "instance_id": "P-100-01#01", "owner": "manual"},
        {"assembly_name": "legacy_alias", "instance_id": "P-999-01#01", "owner": "manual"},
    ]


def test_layout_contract_rejects_non_one_to_one_manual_mapping():
    from tools.layout_contract import build_layout_contract

    with pytest.raises(ValueError, match="duplicate manual layout instance_id"):
        build_layout_contract(
            _product_graph([
                {"instance_id": "P-100-01#01", "part_no": "P-100-01", "render_policy": "required"},
            ]),
            generated_files=[],
            manual_overrides=[
                {"assembly_name": "alias_a", "instance_id": "P-100-01#01"},
                {"assembly_name": "alias_b", "instance_id": "P-100-01#01"},
            ],
        )

    with pytest.raises(ValueError, match="duplicate manual layout assembly_name"):
        build_layout_contract(
            _product_graph([
                {"instance_id": "P-100-01#01", "part_no": "P-100-01", "render_policy": "required"},
            ]),
            generated_files=[],
            manual_overrides=[
                {"assembly_name": "alias_a", "instance_id": "P-100-01#01"},
                {"assembly_name": "alias_a", "instance_id": "P-100-02#01"},
            ],
        )


def test_should_preserve_manual_layout_unless_force_layout(tmp_path):
    from tools.layout_contract import should_preserve_manual_layout

    layout_path = tmp_path / "assembly_layout.py"
    layout_path.write_text("# user layout\n", encoding="utf-8")

    assert should_preserve_manual_layout(layout_path, force_layout=False) is True
    assert should_preserve_manual_layout(layout_path, force_layout=True) is False
    assert should_preserve_manual_layout(tmp_path / "missing.py", force_layout=False) is False


def test_write_assembly_files_preserves_manual_layout_on_plain_force(tmp_path):
    from codegen.gen_assembly import write_assembly_files

    spec = _write_minimal_spec(tmp_path)
    _write_product_graph(spec.parent)
    layout_path = spec.parent / "assembly_layout.py"
    layout_path.write_text(
        "# USER_LAYOUT_MARKER\n"
        "MANUAL_LAYOUT_OVERRIDES = {'demo_alias': 'P-100-01#01'}\n"
        "def apply_layout(assy):\n"
        "    return assy\n",
        encoding="utf-8",
    )

    result = write_assembly_files(str(spec), mode="force", force_layout=False)

    assert "USER_LAYOUT_MARKER" in layout_path.read_text(encoding="utf-8")
    assert result["layout_preserved"] is True
    assert (spec.parent / "assembly.generated.py").is_file()
    assert (spec.parent / "assembly.py").is_file()
    contract = json.loads((spec.parent / "LAYOUT_CONTRACT.json").read_text(encoding="utf-8"))
    assert contract["manual_layout"]["preserved"] is True
    assert contract["manual_layout"]["layout_rebuilt"] is False
    assert contract["generated_files"] == ["assembly.generated.py", "assembly.py"]
    assert contract["status"] == "ok"
    assert contract["warnings"] == []


def test_write_assembly_files_rebuilds_manual_layout_only_with_force_layout(tmp_path):
    from codegen.gen_assembly import write_assembly_files

    spec = _write_minimal_spec(tmp_path)
    _write_product_graph(spec.parent)
    layout_path = spec.parent / "assembly_layout.py"
    layout_path.write_text("# USER_LAYOUT_MARKER\n", encoding="utf-8")

    result = write_assembly_files(str(spec), mode="force", force_layout=True)

    assert "USER_LAYOUT_MARKER" not in layout_path.read_text(encoding="utf-8")
    assert result["layout_preserved"] is False
    contract = json.loads((spec.parent / "LAYOUT_CONTRACT.json").read_text(encoding="utf-8"))
    assert contract["manual_layout"]["preserved"] is False
    assert contract["manual_layout"]["layout_rebuilt"] is True
    assert contract["manual_layout"]["force_layout"] is True


def test_gen_assembly_cli_force_layout_flag_controls_manual_layout(tmp_path):
    spec = _write_minimal_spec(tmp_path)
    _write_product_graph(spec.parent)
    layout_path = spec.parent / "assembly_layout.py"
    layout_path.write_text("# USER_LAYOUT_MARKER\n", encoding="utf-8")

    plain_force = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "codegen" / "gen_assembly.py"),
            str(spec),
            "--mode",
            "force",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
    )
    assert plain_force.returncode == 0, plain_force.stderr
    assert "USER_LAYOUT_MARKER" in layout_path.read_text(encoding="utf-8")

    force_layout = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "codegen" / "gen_assembly.py"),
            str(spec),
            "--mode",
            "force",
            "--force-layout",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
    )
    assert force_layout.returncode == 0, force_layout.stderr
    assert "USER_LAYOUT_MARKER" not in layout_path.read_text(encoding="utf-8")


def test_write_assembly_files_requires_product_graph_for_layout_contract(tmp_path):
    from codegen.gen_assembly import write_assembly_files

    spec = _write_minimal_spec(tmp_path)

    with pytest.raises(FileNotFoundError, match="PRODUCT_GRAPH.json"):
        write_assembly_files(str(spec), mode="force")

    assert not (spec.parent / "assembly.generated.py").exists()
    assert not (spec.parent / "assembly.py").exists()
    assert not (spec.parent / "assembly_layout.py").exists()
    assert not (spec.parent / "LAYOUT_CONTRACT.json").exists()


def test_manual_layout_parse_error_does_not_half_write_generated_files(tmp_path):
    from codegen.gen_assembly import write_assembly_files

    spec = _write_minimal_spec(tmp_path)
    _write_product_graph(spec.parent)
    layout_path = spec.parent / "assembly_layout.py"
    layout_path.write_text("MANUAL_LAYOUT_OVERRIDES = dict(alias='P-100-01#01')\n", encoding="utf-8")

    with pytest.raises(ValueError, match="MANUAL_LAYOUT_OVERRIDES"):
        write_assembly_files(str(spec), mode="force")

    assert "dict(alias" in layout_path.read_text(encoding="utf-8")
    assert not (spec.parent / "assembly.generated.py").exists()
    assert not (spec.parent / "assembly.py").exists()
    assert not (spec.parent / "LAYOUT_CONTRACT.json").exists()


def test_force_migrates_legacy_assembly_py_without_destroying_it(tmp_path):
    from codegen.gen_assembly import write_assembly_files

    spec = _write_minimal_spec(tmp_path)
    _write_product_graph(spec.parent)
    legacy_entry = spec.parent / "assembly.py"
    legacy_entry.write_text("# LEGACY_ASSEMBLY_MARKER\n", encoding="utf-8")

    result = write_assembly_files(str(spec), mode="force")

    backup = spec.parent / "assembly_legacy.py"
    assert backup.read_text(encoding="utf-8") == "# LEGACY_ASSEMBLY_MARKER\n"
    assert "Stable assembly entrypoint" in legacy_entry.read_text(encoding="utf-8")
    contract = json.loads((spec.parent / "LAYOUT_CONTRACT.json").read_text(encoding="utf-8"))
    assert result["legacy_entry_backup"] == str(backup)
    assert contract["migration_events"] == [{
        "code": "legacy_assembly_entry_preserved",
        "source": "assembly.py",
        "backup": "assembly_legacy.py",
        "message": "Existing assembly.py was preserved before writing the stable entrypoint.",
    }]
    assert any(warning["code"] == "legacy_assembly_entry_preserved" for warning in contract["warnings"])


def test_layout_contract_marks_orphans_as_blocked():
    from tools.layout_contract import build_layout_contract

    contract = build_layout_contract(
        _product_graph([
            {"instance_id": "P-100-01#01", "part_no": "P-100-01", "render_policy": "required"},
        ]),
        generated_files=["assembly.generated.py", "assembly.py"],
        manual_overrides=[{"assembly_name": "legacy_alias", "instance_id": "P-999-01#01"}],
    )

    assert contract["status"] == "blocked"
    assert contract["blocking_reasons"] == [{
        "code": "orphan_layout_overrides",
        "instance_ids": ["P-999-01#01"],
        "message": "Manual layout references instances that are not present in PRODUCT_GRAPH.json.",
    }]
    assert contract["warnings"][0]["code"] == "unlaid_out_instances"


def _write_minimal_spec(tmp_path: Path) -> Path:
    spec_dir = tmp_path / "cad" / "demo"
    spec_dir.mkdir(parents=True)
    spec = spec_dir / "CAD_SPEC.md"
    spec.write_text(
        "# CAD Spec - Demo (P)\n"
        "\n"
        "## 5. BOM\n"
        "| 料号 | 名称 | 材质 | 数量 | 自制/外购 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| P-100 | 总成 | 组合件 | 1 | 总成 |\n"
        "| P-100-01 | 基座 | Q235 | 1 | 自制 |\n"
        "\n"
        "### 6.4 零件包络尺寸\n"
        "| 料号 | 零件名 | 类型 | 尺寸(mm) | 来源 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| P-100-01 | 基座 | box | 20x20x10 | test |\n",
        encoding="utf-8",
    )
    return spec


def _write_product_graph(spec_dir: Path) -> None:
    graph = _product_graph([
        {"instance_id": "P-100-01#01", "part_no": "P-100-01", "render_policy": "required"},
    ])
    (spec_dir / "PRODUCT_GRAPH.json").write_text(
        json.dumps(graph, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
