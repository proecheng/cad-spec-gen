"""Tests for assembly_validator.py."""
import os
import sys
import math
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def test_aabb_distance_overlapping():
    """Overlapping AABBs should have distance 0."""
    from assembly_validator import aabb_distance
    a = (0, 0, 0, 10, 10, 10)
    b = (5, 5, 5, 15, 15, 15)
    assert aabb_distance(a, b) == 0.0


def test_aabb_distance_separated():
    """Separated AABBs: d = sqrt(dx^2 + dy^2 + dz^2)."""
    from assembly_validator import aabb_distance
    a = (0, 0, 0, 10, 10, 10)
    b = (20, 0, 0, 30, 10, 10)
    assert aabb_distance(a, b) == 10.0


def test_aabb_distance_diagonal():
    """Diagonal separation: d = sqrt(10^2 + 10^2 + 10^2)."""
    from assembly_validator import aabb_distance
    a = (0, 0, 0, 10, 10, 10)
    b = (20, 20, 20, 30, 30, 30)
    expected = math.sqrt(10**2 + 10**2 + 10**2)
    assert abs(aabb_distance(a, b) - expected) < 0.01


def test_derive_disconnect_threshold_from_tolerances():
    """Threshold = 3 * RSS(tolerances) + 0.3mm ISO 2768-m margin."""
    from assembly_validator import derive_disconnect_threshold
    tolerances = [0.1, 0.1, 0.1, 0.1]
    threshold = derive_disconnect_threshold(tolerances, min_part_size=50.0)
    expected = 3.0 * math.sqrt(sum(t**2 for t in tolerances)) + 0.3
    assert abs(threshold - expected) < 0.01


def test_derive_disconnect_threshold_no_tolerances():
    """Without tolerance data: fallback to 5% of smallest part size."""
    from assembly_validator import derive_disconnect_threshold
    threshold = derive_disconnect_threshold([], min_part_size=40.0)
    assert abs(threshold - 2.0) < 0.01


def test_derive_compactness_threshold():
    """Compactness = sum(heights) * packing_factor."""
    from assembly_validator import derive_compactness_threshold
    heights = [25.0, 5.0, 68.0, 8.0]
    threshold = derive_compactness_threshold(heights)
    assert abs(threshold - 106.0 * 2.0) < 0.01


def test_f1_floating_ignores_declared_excluded_names():
    """Excluded visual leaves should not surface as floating warnings."""
    from assembly_validator import check_f1_floating

    bboxes = {
        "EE-002-01": (0, 0, 0, 10, 10, 10),
        "EE-002-02": (10, 0, 0, 20, 10, 10),
        "STD-EE-002-05": (100, 0, 0, 110, 10, 10),
    }

    issues = check_f1_floating(
        bboxes,
        threshold=0.1,
        ignored_names={"STD-EE-002-05"},
    )
    assert issues == []


def test_f3_compactness_uses_actual_height_when_envelope_missing():
    """F3 should not become over-strict when §6.4 lacks purchased-part envelopes."""
    from assembly_validator import check_f3_compactness

    bboxes = {
        "EE-001-01": (-45, -45, 0, 45, 45, 25),
        "STD-EE-001-05": (-11, -11, 73, 11, 11, 155),
    }
    envelopes = {
        "GIS-EE-001-01": {"dims": (90.0, 90.0, 25.0)},
    }

    issues = check_f3_compactness(bboxes, envelopes, ["GIS-EE-001"])
    assert issues == []


def test_match_name_to_part_no_accepts_unique_single_segment_suffix():
    """Generated SLP assemblies name custom parts as 100/P01, not SLP-100."""
    from assembly_validator import _match_name_to_part_no

    part_nos = ["SLP-100", "SLP-P01", "SLP-C02"]

    assert _match_name_to_part_no("100", part_nos) == "SLP-100"
    assert _match_name_to_part_no("P01", part_nos) == "SLP-P01"


def test_match_name_to_part_no_accepts_instance_suffixes():
    """Assembly instance names should map back to their BOM base part."""
    from assembly_validator import _match_name_to_part_no

    part_nos = ["SLP-P01", "SLP-P02", "SLP-C04"]

    assert _match_name_to_part_no("SLP-P01#01", part_nos) == "SLP-P01"
    assert _match_name_to_part_no("P01-LS1", part_nos) == "SLP-P01"
    assert _match_name_to_part_no("P02-GS2", part_nos) == "SLP-P02"
    assert _match_name_to_part_no("STD-SLP-C04-LS2", part_nos) == "SLP-C04"
    assert _match_name_to_part_no("STD-SLP-C01-LS1-NUT", part_nos + ["SLP-C01"]) == "SLP-C01"
    assert _match_name_to_part_no("200-LEFT-SUPPORT", part_nos + ["SLP-200"]) == "SLP-200"


def test_match_name_to_part_no_rejects_ambiguous_single_segment_suffix():
    """One-token suffix matching is only safe when it is unique."""
    from assembly_validator import _match_name_to_part_no

    part_nos = ["GIS-EE-001-04", "GIS-EE-003-04"]

    assert _match_name_to_part_no("04", part_nos) == ""


def test_f5_completeness_excludes_connectors_cables_and_excluded_assemblies():
    """Expected and actual counts should use the same render exclusion contract."""
    from assembly_validator import check_f5_completeness

    bom_parts = [
        {"part_no": "GIS-EE-001", "name_cn": "法兰总成",
         "is_assembly": True, "material": "", "make_buy": "总成"},
        {"part_no": "GIS-EE-001-01", "name_cn": "法兰本体",
         "is_assembly": False, "material": "铝合金", "make_buy": "自制"},
        {"part_no": "GIS-EE-001-02", "name_cn": "LEMO插头",
         "is_assembly": False, "material": "FGG.0B.307", "make_buy": "外购"},
        {"part_no": "GIS-EE-001-03", "name_cn": "Gore柔性同轴",
         "is_assembly": False, "material": "MicroTCA", "make_buy": "外购"},
        {"part_no": "GIS-EE-001-04", "name_cn": "定位销",
         "is_assembly": False, "material": "Φ3×6mm H7/g6", "make_buy": "外购"},
        {"part_no": "GIS-EE-006", "name_cn": "信号调理模块",
         "is_assembly": True, "material": "", "make_buy": "总成"},
        {"part_no": "GIS-EE-006-01", "name_cn": "壳体",
         "is_assembly": False, "material": "6063铝合金", "make_buy": "自制"},
    ]
    bboxes = {
        "EE-001-01": (0, 0, 0, 90, 90, 25),
        "STD-EE-001-02": (100, 0, 0, 110, 10, 10),
    }

    report = check_f5_completeness(
        bboxes,
        bom_parts,
        excluded_part_nos={"GIS-EE-001-02"},
        excluded_assembly_nos={"GIS-EE-006"},
    )
    assert report["expected"] == 1
    assert report["actual"] == 1
    assert report["missing"] == []
    assert report["ok"] is True


def test_f5_completeness_counts_mechanical_drivetrain_parts():
    """Mechanical drivetrain leaves must be counted, so missing belts,
    pulleys, couplings, screw nuts, and guards are visible in F5."""
    from assembly_validator import check_f5_completeness

    bom_parts = [
        {"part_no": "SLP-100", "name_cn": "上固定板",
         "is_assembly": False, "material": "6061", "make_buy": "自制"},
        {"part_no": "SLP-500", "name_cn": "同步带护罩",
         "is_assembly": False, "material": "PLA", "make_buy": "自制"},
        {"part_no": "SLP-C01", "name_cn": "T16 螺母 C7",
         "is_assembly": False, "material": "", "make_buy": "外购"},
        {"part_no": "SLP-C04", "name_cn": "GT2 20T 开式带轮 φ12",
         "is_assembly": False, "material": "", "make_buy": "外购"},
        {"part_no": "SLP-C05", "name_cn": "GT2-310-6mm 带",
         "is_assembly": False, "material": "", "make_buy": "外购"},
        {"part_no": "SLP-C06", "name_cn": "L070 联轴器",
         "is_assembly": False, "material": "", "make_buy": "外购"},
    ]
    bboxes = {
        "100": (0, 0, 0, 100, 80, 10),
    }

    report = check_f5_completeness(bboxes, bom_parts)

    assert report["expected"] == 6
    assert report["actual"] == 1
    assert set(report["missing"]) == {
        "SLP-500", "SLP-C01", "SLP-C04", "SLP-C05", "SLP-C06",
    }
    assert report["ok"] is False


def test_validate_assembly_writes_run_scoped_report_and_signature(tmp_path):
    """Runtime validation artifacts should be bound to the current run_id."""
    import json

    sub_dir = tmp_path / "project" / "cad" / "demo"
    output_dir = tmp_path / "project" / "cad" / "output"
    sub_dir.mkdir(parents=True)
    (sub_dir / "CAD_SPEC.md").write_text(
        "# CAD Spec — Demo (P)\n"
        "\n"
        "## 5. BOM\n"
        "| 料号 | 名称 | 材质 | 数量 | 自制/外购 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| P-100 | Demo总成 | 组合件 | 1 | 总成 |\n"
        "| P-100-01 | 基座 | Q235 | 1 | 自制 |\n"
        "\n"
        "### 6.4 包络尺寸\n"
        "| 料号 | 名称 | 位置 | 包络尺寸 | 粒度 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| P-100-01 | 基座 | 原点 | 10 x 10 x 10 | part_envelope |\n",
        encoding="utf-8",
        newline="\n",
    )
    (sub_dir / "PRODUCT_GRAPH.json").write_text(
        json.dumps({
            "schema_version": 1,
            "run_id": "RUN001",
            "subsystem": "demo",
            "path_context_hash": "sha256:pathctx",
            "instances": [{
                "instance_id": "P-100-01#01",
                "part_no": "P-100-01",
                "required": True,
                "render_policy": "required",
                "visual_priority": "hero",
            }],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    (sub_dir / "assembly.py").write_text(
        "class BBox:\n"
        "    xmin = ymin = zmin = 0.0\n"
        "    xmax = ymax = zmax = 10.0\n"
        "class Shape:\n"
        "    def moved(self, loc):\n"
        "        return self\n"
        "    def BoundingBox(self):\n"
        "        return BBox()\n"
        "class Sub:\n"
        "    obj = Shape()\n"
        "    loc = None\n"
        "class Assy:\n"
        "    objects = {'P-100-01#01': Sub()}\n"
        "def make_assembly():\n"
        "    return Assy()\n",
        encoding="utf-8",
        newline="\n",
    )

    from assembly_validator import validate_assembly

    report = validate_assembly(
        str(sub_dir),
        str(sub_dir / "CAD_SPEC.md"),
        str(output_dir),
    )

    run_dir = output_dir / "runs" / "RUN001"
    report_path = run_dir / "ASSEMBLY_REPORT.json"
    signature_path = run_dir / "ASSEMBLY_SIGNATURE.json"
    assert report["report_path"] == str(report_path.resolve())
    assert report["assembly_signature_path"] == str(signature_path.resolve())
    assert report_path.is_file()
    assert not (output_dir / "ASSEMBLY_REPORT.json").exists()
    signature = json.loads(signature_path.read_text(encoding="utf-8"))
    assert signature["source_mode"] == "runtime"
    assert signature["coverage"]["matched_total"] == 1


def test_validate_assembly_rejects_bad_product_graph_instead_of_silent_skip(tmp_path):
    sub_dir = tmp_path / "project" / "cad" / "demo"
    sub_dir.mkdir(parents=True)
    (sub_dir / "CAD_SPEC.md").write_text("# CAD Spec\n", encoding="utf-8")
    (sub_dir / "PRODUCT_GRAPH.json").write_text("{bad json", encoding="utf-8")
    (sub_dir / "assembly.py").write_text(
        "class BBox:\n"
        "    xmin = ymin = zmin = 0.0\n"
        "    xmax = ymax = zmax = 1.0\n"
        "class Shape:\n"
        "    def moved(self, loc):\n"
        "        return self\n"
        "    def BoundingBox(self):\n"
        "        return BBox()\n"
        "class Sub:\n"
        "    obj = Shape()\n"
        "    loc = None\n"
        "class Assy:\n"
        "    objects = {'P-001#01': Sub()}\n"
        "def make_assembly():\n"
        "    return Assy()\n",
        encoding="utf-8",
        newline="\n",
    )

    from assembly_validator import validate_assembly

    report = validate_assembly(str(sub_dir), str(sub_dir / "CAD_SPEC.md"))

    assert "error" in report
    assert "PRODUCT_GRAPH.json" in report["error"]
    assert not (tmp_path / "project" / "cad" / "output").exists()


def test_validate_assembly_rejects_output_dir_outside_project(tmp_path):
    import json

    sub_dir = tmp_path / "project" / "cad" / "demo"
    outside = tmp_path / "outside"
    sub_dir.mkdir(parents=True)
    (sub_dir / "CAD_SPEC.md").write_text("# CAD Spec\n", encoding="utf-8")
    (sub_dir / "PRODUCT_GRAPH.json").write_text(
        json.dumps({
            "schema_version": 1,
            "run_id": "RUN001",
            "subsystem": "demo",
            "instances": [{
                "instance_id": "P-001#01",
                "part_no": "P-001",
                "required": True,
                "render_policy": "required",
            }],
        }),
        encoding="utf-8",
    )
    (sub_dir / "assembly.py").write_text(
        "class BBox:\n"
        "    xmin = ymin = zmin = 0.0\n"
        "    xmax = ymax = zmax = 1.0\n"
        "class Shape:\n"
        "    def moved(self, loc):\n"
        "        return self\n"
        "    def BoundingBox(self):\n"
        "        return BBox()\n"
        "class Sub:\n"
        "    obj = Shape()\n"
        "    loc = None\n"
        "class Assy:\n"
        "    objects = {'P-001#01': Sub()}\n"
        "def make_assembly():\n"
        "    return Assy()\n",
        encoding="utf-8",
        newline="\n",
    )

    from assembly_validator import validate_assembly

    report = validate_assembly(
        str(sub_dir),
        str(sub_dir / "CAD_SPEC.md"),
        str(outside),
    )

    assert "error" in report
    assert "output_dir" in report["error"]
    assert not outside.exists()


def test_validate_assembly_rejects_run_id_path_traversal(tmp_path):
    import json

    sub_dir = tmp_path / "project" / "cad" / "demo"
    output_dir = tmp_path / "project" / "cad" / "output"
    sub_dir.mkdir(parents=True)
    (sub_dir / "CAD_SPEC.md").write_text("# CAD Spec\n", encoding="utf-8")
    (sub_dir / "PRODUCT_GRAPH.json").write_text(
        json.dumps({
            "schema_version": 1,
            "run_id": "..\\..\\outside",
            "subsystem": "demo",
            "instances": [{
                "instance_id": "P-001#01",
                "part_no": "P-001",
                "required": True,
                "render_policy": "required",
            }],
        }),
        encoding="utf-8",
    )
    (sub_dir / "assembly.py").write_text(
        "class BBox:\n"
        "    xmin = ymin = zmin = 0.0\n"
        "    xmax = ymax = zmax = 1.0\n"
        "class Shape:\n"
        "    def moved(self, loc):\n"
        "        return self\n"
        "    def BoundingBox(self):\n"
        "        return BBox()\n"
        "class Sub:\n"
        "    obj = Shape()\n"
        "    loc = None\n"
        "class Assy:\n"
        "    objects = {'P-001#01': Sub()}\n"
        "def make_assembly():\n"
        "    return Assy()\n",
        encoding="utf-8",
        newline="\n",
    )

    from assembly_validator import validate_assembly

    report = validate_assembly(
        str(sub_dir),
        str(sub_dir / "CAD_SPEC.md"),
        str(output_dir),
    )

    assert "error" in report
    assert "run_id" in report["error"]
    assert not output_dir.exists()
