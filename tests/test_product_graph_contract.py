import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write_spec(root: Path, subsystem: str, bom_header: list[str], bom_rows: list[list[str]]) -> Path:
    subsystem_dir = root / "cad" / subsystem
    subsystem_dir.mkdir(parents=True, exist_ok=True)
    rows = "\n".join("| " + " | ".join(row) + " |" for row in bom_rows)
    spec = f"""# CAD Spec

## 5. BOM

| {" | ".join(bom_header)} |
| {" | ".join(["---"] * len(bom_header))} |
{rows}

### 6.2 装配层叠

| 层级 | 零件 | 固定/运动 | 连接 | 偏移 | 轴向 |
| --- | --- | --- | --- | --- | --- |
| 1 | P-100 | 固定 | 基准 | 0 | Z |

### 6.4 包络尺寸

| 料号 | 名称 | 位置 | 包络尺寸 | 粒度 |
| --- | --- | --- | --- | --- |
| P-100-01 | 基座 | 原点 | 100 x 80 x 20 | part_envelope |
| P-100-02 | 导柱 | 两侧 | 10 x 10 x 120 | part_envelope |

### 9.2 约束

| 约束ID | 类型 | 零件A | 零件B | 参数 | 来源 | 置信度 |
| --- | --- | --- | --- | --- | --- | --- |
| C01 | contact | P-100-01 | P-100-02 | gap=0 | test | high |
| C02 | exclude_stack | P-100-03 |  | render=false | test | high |
"""
    path = subsystem_dir / "CAD_SPEC.md"
    path.write_text(spec, encoding="utf-8", newline="\n")
    return path


def _base_bom_rows() -> list[list[str]]:
    return [
        ["P-100", "升降平台总成", "组合件", "1", "总成"],
        ["P-100-01", "基座", "Q235", "1", "自制"],
        ["P-100-02", "导柱", "45钢", "3", "自制"],
        ["P-100-03", "线缆束", "PVC", "2", "外购"],
    ]


def _build_graph(tmp_path: Path, bom_header=None, bom_rows=None) -> dict:
    from tools.product_graph import build_product_graph

    header = bom_header or ["料号", "名称", "材质", "数量", "自制/外购"]
    rows = bom_rows or _base_bom_rows()
    _write_spec(tmp_path, "demo", header, rows)
    return build_product_graph(tmp_path, "demo", run_id="RUN001")


def test_quantity_one_keeps_01_instance_id(tmp_path):
    graph = _build_graph(tmp_path)

    base_instances = [i for i in graph["instances"] if i["part_no"] == "P-100-01"]

    assert [i["instance_id"] for i in base_instances] == ["P-100-01#01"]
    assert base_instances[0]["occurrence_index"] == 1


def test_quantity_n_expands_instances_in_stable_order(tmp_path):
    graph = _build_graph(tmp_path)

    guide_instances = [i for i in graph["instances"] if i["part_no"] == "P-100-02"]

    assert [i["instance_id"] for i in guide_instances] == [
        "P-100-02#01",
        "P-100-02#02",
        "P-100-02#03",
    ]
    assert graph["counts_by_part_no"]["P-100-02"] == 3


def test_render_excluded_part_is_not_required_photo_instance(tmp_path):
    graph = _build_graph(tmp_path)

    cable_part = next(p for p in graph["parts"] if p["part_no"] == "P-100-03")
    cable_instances = [i for i in graph["instances"] if i["part_no"] == "P-100-03"]

    assert cable_part["render_policy"] == "excluded"
    assert cable_part["required"] is False
    assert cable_instances
    assert all(i["render_policy"] == "excluded" and i["required"] is False for i in cable_instances)


def test_contract_policy_fields_use_allowed_enums(tmp_path):
    graph = _build_graph(tmp_path)
    render_policies = {"required", "optional", "excluded"}
    visual_priorities = {"hero", "high", "normal", "low"}
    change_policies = {"preserve", "may_refine_geometry", "may_move", "optional"}

    for item in [*graph["parts"], *graph["instances"]]:
        assert item["render_policy"] in render_policies
        assert item["visual_priority"] in visual_priorities
        assert item["change_policy"] in change_policies


def test_constraints_use_contract_instance_fields(tmp_path):
    graph = _build_graph(tmp_path)

    contact = next(c for c in graph["constraints"] if c["type"] == "contact")

    assert contact["instance_a"] == "P-100-01#01"
    assert contact["instance_b"] == "P-100-02#01"


def test_source_hashes_are_stable_for_unchanged_spec(tmp_path):
    graph1 = _build_graph(tmp_path)
    graph2 = _build_graph(tmp_path)

    assert graph1["source_hashes"] == graph2["source_hashes"]
    assert graph1["source_hashes"]["CAD_SPEC.md"].startswith("sha256:")


def test_bom_header_order_uses_mapping_not_fixed_columns(tmp_path):
    rows = [
        ["1", "自制", "升降平台总成", "组合件", "P-100"],
        ["1", "自制", "基座", "Q235", "P-100-01"],
        ["3", "自制", "导柱", "45钢", "P-100-02"],
    ]
    graph = _build_graph(
        tmp_path,
        bom_header=["数量", "自制/外购", "名称", "材质", "料号"],
        bom_rows=rows,
    )

    assert graph["parser"]["bom_header_mapping"]["part_no"] == "料号"
    assert graph["parts"][1]["part_no"] == "P-100-01"
    assert graph["parts"][1]["name_cn"] == "基座"
    assert graph["counts_by_part_no"]["P-100-02"] == 3


def test_low_confidence_bom_row_enters_warnings(tmp_path):
    graph = _build_graph(
        tmp_path,
        bom_rows=[
            ["P-100", "升降平台总成", "组合件", "1", "总成"],
            ["P-100-01", "基座", "Q235", "约两件", "自制"],
        ],
    )

    low_part = next(p for p in graph["parts"] if p["part_no"] == "P-100-01")
    assert low_part["parse_confidence"] < 1.0
    assert any("P-100-01" in warning["message"] for warning in graph["warnings"])


def test_chinese_compound_quantity_expands_instances(tmp_path):
    graph = _build_graph(
        tmp_path,
        bom_rows=[
            ["P-100", "升降平台总成", "组合件", "1", "总成"],
            ["P-100-04", "垫片", "Q235", "十二件", "自制"],
        ],
    )

    washer_instances = [i for i in graph["instances"] if i["part_no"] == "P-100-04"]
    assert graph["counts_by_part_no"]["P-100-04"] == 12
    assert len(washer_instances) == 12
    assert washer_instances[-1]["instance_id"] == "P-100-04#12"


def test_cli_product_graph_writes_json_to_output(tmp_path):
    _write_spec(
        tmp_path,
        "demo",
        ["料号", "名称", "材质", "数量", "自制/外购"],
        _base_bom_rows(),
    )
    output = tmp_path / "out" / "PRODUCT_GRAPH.json"
    env = {**os.environ, "CAD_PROJECT_ROOT": str(tmp_path)}

    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "cad_pipeline.py"),
            "product-graph",
            "--subsystem",
            "demo",
            "--output",
            str(output),
        ],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["source_spec"] == "cad/demo/CAD_SPEC.md"
    assert data["instances"][0]["instance_id"].endswith("#01")


def test_cli_product_graph_default_is_standalone_subsystem_file(tmp_path):
    from tools.product_graph import write_product_graph

    _write_spec(
        tmp_path,
        "demo",
        ["料号", "名称", "材质", "数量", "自制/外购"],
        _base_bom_rows(),
    )

    output = write_product_graph(tmp_path, "demo", run_id="RUN001")

    assert output == tmp_path / "cad" / "demo" / "PRODUCT_GRAPH.json"
    assert output.is_file()


def test_write_product_graph_rejects_output_outside_project(tmp_path):
    from tools.product_graph import write_product_graph

    _write_spec(
        tmp_path,
        "demo",
        ["料号", "名称", "材质", "数量", "自制/外购"],
        _base_bom_rows(),
    )
    absolute_outside = tmp_path.parent / "outside_product_graph.json"
    relative_outside = Path("..") / "outside_product_graph_relative.json"

    for output in (absolute_outside, relative_outside):
        target = output if output.is_absolute() else tmp_path / output
        if target.exists():
            target.unlink()
        with pytest.raises(ValueError):
            write_product_graph(tmp_path, "demo", output=output, run_id="RUN001")
        assert not target.exists()


def test_build_product_graph_rejects_symlinked_subsystem_outside_project(tmp_path):
    from tools.product_graph import build_product_graph

    outside_root = tmp_path.parent / f"{tmp_path.name}_outside_subsystem"
    outside_root.mkdir()
    _write_spec(outside_root, "demo", ["料号", "名称", "材质", "数量", "自制/外购"], _base_bom_rows())
    external_subsystem = outside_root / "cad" / "demo"
    project_cad_dir = tmp_path / "cad"
    project_cad_dir.mkdir()
    linked_subsystem = project_cad_dir / "demo"
    try:
        linked_subsystem.symlink_to(external_subsystem, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink unavailable on this platform: {exc}")

    with pytest.raises(ValueError):
        build_product_graph(tmp_path, "demo", run_id="RUN001")
