"""自制件审计工具 (tools/custom_parts_audit.py) 的单元 + 集成测试。

对应：docs/superpowers/plans/2026-05-13-quality-overhaul-plan.md §CP-2 Task 7

五个 case 覆盖：
  A. chain_of_custody —— BOM 件未在 build_all 登记
  B. envelope_vs_bbox —— 自制件 bbox 显著小于 scaffold envelope (bug A 模式)
  C. scaffold_marker_scan —— .py 仍含 Auto-generated scaffold / # ENRICHED_PLACEHOLDER
  D. placement_collapse_detect —— 件 bbox 中心几乎全堆原点 (bug B 模式)
  E. 反向回归 —— pre-CP-1 (bbox 90×90×30) → FAIL；post-CP-1 (bbox 170×170×32) → PASS

设计取舍：测试层不调 trimesh / cadquery（重 deps + 慢），用 in-memory glb_instances dict
来模拟 GLB 内容；E 不真做 `git stash ee_001_01.py`，用直接的 bbox 注入复现 regression。
"""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

import pytest

# 把 tools/ 加进 sys.path 让 import 工作（仓库 layout 不是 src/ pkg 结构）
_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "tools"))

import custom_parts_audit as cpa  # noqa: E402


# ── Fixture：迷你子系统骨架 ────────────────────────────────────────────────────
def _write_fake_subsystem(
    sub_dir: pathlib.Path,
    *,
    bom_rows: list[tuple[str, str, str, int]],  # (part_no, name, category, qty)
    env_rows: list[tuple[str, str, str]],       # (part_no, shape, dim_str)
    parts: dict[str, str],                      # filename → file body
    build_all_modules: list[str],               # 在 _DXF_BUILDS 里登记的模块名
) -> None:
    """在 sub_dir 下生成最简 CAD_SPEC.md + build_all.py + parts .py 树。"""
    sub_dir.mkdir(parents=True, exist_ok=True)
    bom_md = "| 件号 | 名称 | 备注 | 数量 | 范畴 | 替代 |\n| --- | --- | --- | --- | --- | --- |\n"
    for part_no, name, cat, qty in bom_rows:
        bom_md += f"| {part_no} | {name} |  | {qty} | {cat} | — |\n"
    env_md = "| 件号 | 名称 | 形状 | 尺寸(mm) | 来源 | 朝向 | 置信度 | 范畴 | 类型 | 备注 |\n"
    env_md += "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
    for part_no, shape, dim in env_rows:
        env_md += f"| {part_no} | name | {shape} | {dim} | P3 | — | — | — | — |  |\n"
    spec = (
        "# CAD_SPEC\n\n"
        "## 5 · BOM\n\n"
        + bom_md
        + "\n## 6.4 · Envelope\n\n"
        + env_md
        + "\n## 7 · End\n"
    )
    (sub_dir / "CAD_SPEC.md").write_text(spec, encoding="utf-8")
    build_all = (
        "# Synthetic build_all\n"
        "_DXF_BUILDS = [\n"
        + "".join(f'    ("名", "{m}", "draw_{m}_sheet"),\n' for m in build_all_modules)
        + "]\n"
        "_STEP_BUILDS = []\n"
    )
    (sub_dir / "build_all.py").write_text(build_all, encoding="utf-8")
    for fn, body in parts.items():
        (sub_dir / fn).write_text(body, encoding="utf-8")


# ───────────────────────── case A · chain_of_custody ──────────────────────────
def test_chain_of_custody_warns_when_self_made_py_missing(tmp_path: pathlib.Path) -> None:
    """case A：BOM 有 SLP-100 但 build_all 没登记 → 必产 WARN。"""
    sub_dir = tmp_path / "fake_sub"
    _write_fake_subsystem(
        sub_dir,
        bom_rows=[("SLP-100", "测试件", "自制", 1)],
        env_rows=[],
        parts={},  # 故意不写 p100.py / 100.py
        build_all_modules=[],  # 没登记
    )
    bom = cpa._parse_bom_table(cpa._read_text(sub_dir / "CAD_SPEC.md"))
    result = cpa.chain_of_custody(sub_dir, bom, {}, tmp_path / "out")
    severities = {f["severity"] for f in result["findings"]}
    wheres = {f["where"] for f in result["findings"]}
    assert "FAIL" in severities, "缺 .py 应该是 FAIL，不是 WARN"
    assert any("chain.py_missing" in w for w in wheres)


# ───────────────────────── case B · envelope_vs_bbox ──────────────────────────
def test_envelope_vs_bbox_fails_for_self_made_when_bbox_dwarfed(tmp_path: pathlib.Path) -> None:
    """case B + reverse-regression：自制件 scaffold envelope 160×160×20，
    GLB bbox 90×90×30（pre-CP-1 法兰 disc-only）→ axis_min_ratio = 90/160 = 0.56 < 0.60 → FAIL。
    """
    sub_dir = tmp_path / "fake_sub"
    _write_fake_subsystem(
        sub_dir,
        bom_rows=[("GIS-EE-001-01", "法兰本体", "自制", 1)],
        env_rows=[],
        parts={
            "ee_001_01.py": (
                '"""法兰\n\nEnvelope: 160.0 x 160.0 x 20.0 mm\n"""\n'
                "def make_ee_001_01(): pass\n"
            ),
        },
        build_all_modules=["ee_001_01"],
    )
    spec_md = cpa._read_text(sub_dir / "CAD_SPEC.md")
    bom = cpa._parse_bom_table(spec_md)
    # 注入 "pre-CP-1" 的 disc-only bbox: 90×90×30
    fake_glb = {
        "EE-001-01#01": ((0.0, 0.0, 15.0), (90.0, 90.0, 30.0)),
    }
    result = cpa.envelope_vs_bbox(sub_dir, spec_md, bom, fake_glb)
    fails = [f for f in result["findings"] if f["severity"] == "FAIL"]
    assert len(fails) == 1, f"应正好产 1 个 FAIL，实际 {len(fails)}: {result['findings']}"
    assert fails[0]["where"] == "envelope.axis"
    assert fails[0]["part"] == "GIS-EE-001-01"


def test_envelope_vs_bbox_passes_for_self_made_when_bbox_matches(tmp_path: pathlib.Path) -> None:
    """post-CP-1：bbox 170×170×32（含 4 臂） vs envelope 160×160×20 → bbox > truth → 至多 WARN, 不 FAIL。"""
    sub_dir = tmp_path / "fake_sub"
    _write_fake_subsystem(
        sub_dir,
        bom_rows=[("GIS-EE-001-01", "法兰本体", "自制", 1)],
        env_rows=[],
        parts={
            "ee_001_01.py": (
                '"""法兰\n\nEnvelope: 160.0 x 160.0 x 20.0 mm\n"""\n'
                "def make_ee_001_01(): pass\n"
            ),
        },
        build_all_modules=["ee_001_01"],
    )
    spec_md = cpa._read_text(sub_dir / "CAD_SPEC.md")
    bom = cpa._parse_bom_table(spec_md)
    fake_glb = {
        "EE-001-01#01": ((0.0, 0.0, 16.0), (170.0, 170.0, 32.0)),
    }
    result = cpa.envelope_vs_bbox(sub_dir, spec_md, bom, fake_glb)
    fails = [f for f in result["findings"] if f["severity"] == "FAIL"]
    assert not fails, f"bbox 大于 envelope 不应 FAIL，实际：{fails}"


# ────────────────────────── case C · scaffold_marker_scan ─────────────────────
def test_scaffold_marker_scan_catches_both_marker_kinds(tmp_path: pathlib.Path) -> None:
    """auto-generated scaffold + # ENRICHED_PLACEHOLDER 都必须被抓到。"""
    sub_dir = tmp_path / "fake_sub"
    sub_dir.mkdir()
    (sub_dir / "p100.py").write_text(
        '"""Auto-generated scaffold by codegen/gen_parts.py"""\ndef make_p100(): pass\n',
        encoding="utf-8",
    )
    (sub_dir / "p500.py").write_text(
        "# ENRICHED_PLACEHOLDER\nimport cq\ndef make_p500(): pass\n",
        encoding="utf-8",
    )
    (sub_dir / "p999.py").write_text(  # 干净的 — 不应该被抓
        '"""Clean part."""\ndef make_p999(): pass\n',
        encoding="utf-8",
    )
    result = cpa.scaffold_marker_scan(sub_dir)
    files_with_findings = {r["file"] for r in result["rows"]}
    assert files_with_findings == {"p100.py", "p500.py"}, (
        f"应抓两个 marker 文件，实际 {files_with_findings}"
    )
    # 都是 WARN，不是 FAIL（markers 是"未完工提示"，不是几何错）
    assert all(f["severity"] == "WARN" for f in result["findings"])


def test_scaffold_marker_scan_skips_aux_files(tmp_path: pathlib.Path) -> None:
    """build_all / params / assembly* / draw_* / std_* / __init__ 不被扫。"""
    sub_dir = tmp_path / "fake_sub"
    sub_dir.mkdir()
    for fn in ("build_all.py", "params.py", "__init__.py", "assembly.py",
               "assembly_layout.py", "draw_top_plate.py", "std_p01.py"):
        (sub_dir / fn).write_text("# Auto-generated scaffold should be ignored here\n", encoding="utf-8")
    result = cpa.scaffold_marker_scan(sub_dir)
    assert not result["rows"], f"辅助文件不应被扫，实际：{result['rows']}"


# ─────────────────── case D · placement_collapse_detect ───────────────────────
def test_placement_collapse_detect_fails_when_all_at_origin() -> None:
    """case D：所有 mesh node 中心在世界原点附近（<0.1 mm）→ FAIL（bug B 模式）。"""
    glb = {f"SLP-{i}#01": ((0.001 * i, 0.0, 0.0), (10.0, 10.0, 10.0)) for i in range(10)}
    result = cpa.placement_collapse_detect(glb)
    fails = [f for f in result["findings"] if f["severity"] == "FAIL"]
    assert fails, f"全堆原点应该 FAIL，实际 findings：{result['findings']}"
    assert "placement.collapse" in fails[0]["where"]


def test_placement_collapse_warns_in_intermediate_range() -> None:
    """件距 0.5~10 mm 区间（如 O-ring 叠在垫片上）→ WARN，不是 FAIL。"""
    glb = {
        "SLP-A#01": ((0.0, 0.0, 0.0), (10.0, 10.0, 10.0)),
        "SLP-B#01": ((0.0, 0.0, 0.5), (10.0, 10.0, 10.0)),
        # 远离的第三件让"closest pair"非零，但仍 < 10mm 阈值
    }
    result = cpa.placement_collapse_detect(glb)
    fails = [f for f in result["findings"] if f["severity"] == "FAIL"]
    warns = [f for f in result["findings"] if f["severity"] == "WARN"]
    assert not fails, f"叠片不应 FAIL，实际：{fails}"
    assert warns, f"叠片应给 WARN，实际：{result['findings']}"


def test_placement_collapse_passes_for_healthy_assembly() -> None:
    """件距均 >10 mm → PASS, 0 findings。"""
    glb = {
        "SLP-A#01": ((0.0, 0.0, 0.0), (10.0, 10.0, 10.0)),
        "SLP-B#01": ((0.0, 0.0, 50.0), (10.0, 10.0, 10.0)),
        "SLP-C#01": ((100.0, 0.0, 0.0), (10.0, 10.0, 10.0)),
    }
    result = cpa.placement_collapse_detect(glb)
    assert not result["findings"], f"健康装配应无 findings，实际：{result['findings']}"


# ──────────────── case E · 端到端反向回归（已在 case B 双向覆盖）──────────────
# case B 的两个测试已经构成 pre-CP-1 (FAIL) ↔ post-CP-1 (no FAIL) 的对照对：
#   - test_envelope_vs_bbox_fails_for_self_made_when_bbox_dwarfed (pre-CP-1)
#   - test_envelope_vs_bbox_passes_for_self_made_when_bbox_matches (post-CP-1)
# 此处补一个 audit_subsystem() 顶层入口的烟雾测试，确保它能跑完整流程不崩。


def test_audit_subsystem_smoke_writes_both_reports(tmp_path: pathlib.Path) -> None:
    """audit_subsystem 烟雾测试：跑完整流程，写出 MD + JSON 报告，不抛异常。"""
    sub_dir = tmp_path / "cad" / "fake_sub"
    _write_fake_subsystem(
        sub_dir,
        bom_rows=[("GIS-EE-001-01", "法兰", "自制", 1)],
        env_rows=[],
        parts={
            "ee_001_01.py": (
                '"""法兰\n\nEnvelope: 160.0 x 160.0 x 20.0 mm\n"""\n'
                "def make_ee_001_01(): pass\n"
            ),
        },
        build_all_modules=["ee_001_01"],
    )
    # 模拟空 GLB（trimesh load 会拿到 0 实例）
    (tmp_path / "cad" / "output").mkdir(parents=True, exist_ok=True)

    # 直接调 audit_subsystem，让它读 fake_sub 的 spec + 看 output 里有没有 GLB
    result = cpa.audit_subsystem("fake_sub", project_root=tmp_path)

    md_path = pathlib.Path(result.md_path)
    json_path = pathlib.Path(result.json_path)
    assert md_path.exists() and json_path.exists()

    js = json.loads(json_path.read_text(encoding="utf-8"))
    assert js["subsystem"] == "fake_sub"
    assert js["overall"] in ("PASS", "WARN", "FAIL")
    # MD 报告应该是中文
    md_txt = md_path.read_text(encoding="utf-8")
    assert "自制件审计报告" in md_txt
    assert "A · 五段链对账" in md_txt


# ───────────────────────── 工具函数级别 helpers ───────────────────────────────
def test_part_no_normalization_strips_std_and_adds_gis(_unused: Any = None) -> None:
    """`STD-GIS-EE-005-01` / `EE-001-01#01` 都规范成 BOM 风格 `GIS-EE-xxx`。"""
    assert cpa._part_no_from_instance_name("SLP-100#01") == "SLP-100"
    assert cpa._part_no_from_instance_name("STD-GIS-EE-005-01") == "GIS-EE-005-01"
    assert cpa._part_no_from_instance_name("EE-001-01") == "GIS-EE-001-01"
    assert cpa._part_no_from_instance_name("EE-001-01#02") == "GIS-EE-001-01"
    assert cpa._part_no_from_instance_name("not-a-part") is None


def test_parse_dim_string_cylinder_and_box() -> None:
    assert cpa._parse_dim_string("Φ90.0×25.0", "cylinder") == (90.0, 90.0, 25.0)
    assert cpa._parse_dim_string("12.0×50.0×1.0", "box") == (12.0, 50.0, 1.0)
    assert cpa._parse_dim_string("不定", "box") is None
    assert cpa._parse_dim_string("Φ45.0×", "cylinder") is None  # 缺第二个数 → None


def test_parse_scaffold_envelope(tmp_path: pathlib.Path) -> None:
    f = tmp_path / "p1.py"
    f.write_text('"""\n    Envelope: 200.0 x 100.0 x 8.0 mm\n"""\n', encoding="utf-8")
    assert cpa._parse_scaffold_envelope(f) == (200.0, 100.0, 8.0)
    # 用 × 字符（中文 cross）
    f.write_text('"""\n    Envelope: 30 × 30 × 8 mm\n"""\n', encoding="utf-8")
    assert cpa._parse_scaffold_envelope(f) == (30.0, 30.0, 8.0)
    # 无 Envelope 行 → None
    f.write_text('"""no envelope here"""\n', encoding="utf-8")
    assert cpa._parse_scaffold_envelope(f) is None
