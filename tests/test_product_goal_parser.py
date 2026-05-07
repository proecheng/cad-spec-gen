"""产品目标解析器单元测试。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
DICT_DIR = REPO_ROOT / "tools" / "project_guide_dict"


def test_subsystem_keywords_json_exists_and_covers_all_19_subsystems():
    path = DICT_DIR / "subsystem_keywords.json"
    assert path.is_file(), f"missing: {path}"
    data = json.loads(path.read_text(encoding="utf-8"))

    expected_implemented = {"lifting_platform", "end_effector"}
    expected_not_yet = {
        "navigation", "motion_ctrl", "electrical", "communication",
        "charging", "couplant", "detection", "integration", "output",
        "patent", "plan", "power", "robot_platform", "safety",
        "software", "sys_arch", "budget",
    }
    expected = expected_implemented | expected_not_yet

    assert set(data.keys()) == expected, f"差异：{set(data.keys()) ^ expected}"
    for name in expected_implemented:
        assert data[name]["status"] == "implemented", f"{name} 应为 implemented"
    for name in expected_not_yet:
        assert data[name]["status"] == "not_yet_implemented", f"{name} 应为 not_yet_implemented"


def test_kpi_patterns_json_has_3_kpis_per_implemented_subsystem():
    path = DICT_DIR / "kpi_patterns.json"
    assert path.is_file(), f"missing: {path}"
    data = json.loads(path.read_text(encoding="utf-8"))

    assert set(data.keys()) == {"lifting_platform", "end_effector"}

    assert set(data["lifting_platform"].keys()) == {"load_kg", "stroke_mm", "platform_size_mm"}
    assert set(data["end_effector"].keys()) == {"rot_range_deg", "switch_time_s", "flange_dia_mm"}

    # 每个 KPI 必有 regex (list) + context_terms (list) + unit (str)
    for subsystem, kpis in data.items():
        for kpi_name, kpi in kpis.items():
            assert isinstance(kpi.get("regex"), list) and kpi["regex"], f"{subsystem}.{kpi_name} regex 缺"
            assert isinstance(kpi.get("context_terms"), list) and kpi["context_terms"], f"{subsystem}.{kpi_name} context_terms 缺"
            assert isinstance(kpi.get("unit"), str), f"{subsystem}.{kpi_name} unit 缺"


def test_load_dictionary_returns_validated_object():
    from tools.project_guide_dict import load_dictionary, ProductGoalDictionary

    d = load_dictionary()
    assert isinstance(d, ProductGoalDictionary)
    assert "lifting_platform" in d.subsystem_keywords
    assert "load_kg" in d.kpi_patterns["lifting_platform"]


def test_load_dictionary_raises_on_missing_file(tmp_path):
    from tools.project_guide_dict import load_dictionary

    (tmp_path / "subsystem_keywords.json").write_text("{}", encoding="utf-8")
    # 缺 kpi_patterns.json
    with pytest.raises(RuntimeError, match="kpi_patterns.json"):
        load_dictionary(dict_root=tmp_path)


def test_load_dictionary_raises_on_implemented_subsystem_missing_kpis(tmp_path):
    from tools.project_guide_dict import load_dictionary

    (tmp_path / "subsystem_keywords.json").write_text(
        json.dumps({"lifting_platform": {"status": "implemented", "primary_terms": ["升降"], "supporting_terms": []}}),
        encoding="utf-8",
    )
    (tmp_path / "kpi_patterns.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="lifting_platform.*kpi_patterns"):
        load_dictionary(dict_root=tmp_path)


def test_parse_empty_text_returns_no_subsystem():
    from tools.product_goal_parser import parse_product_goal

    result = parse_product_goal(text="")
    assert result.subsystem_class is None
    assert result.subsystem_status == "unknown"
    assert result.kpis == {}
    assert result.raw_text == ""


@pytest.mark.parametrize("text,expected_class,expected_status", [
    ("做一个升降平台", "lifting_platform", "implemented"),
    ("我要个 lifting platform", "lifting_platform", "implemented"),
    ("末端执行机构", "end_effector", "implemented"),
    ("end effector 设计", "end_effector", "implemented"),
    ("做导航 SLAM", "navigation", "not_yet_implemented"),
    ("一个充电桩", "charging", "not_yet_implemented"),
])
def test_subsystem_primary_terms_match_directly(text, expected_class, expected_status):
    from tools.product_goal_parser import parse_product_goal

    result = parse_product_goal(text=text)
    assert result.subsystem_class == expected_class, f"识别错：{result.subsystem_class}"
    assert result.subsystem_status == expected_status


def test_subsystem_supporting_only_marks_ambiguous():
    """仅 supporting_terms 命中（无 primary）→ ambiguous。"""
    from tools.product_goal_parser import parse_product_goal

    result = parse_product_goal(text="升降 50kg")  # "升降" 是 lifting 的 supporting，无 primary
    assert result.subsystem_class is None
    assert result.subsystem_status == "ambiguous"


def test_unknown_subsystem_returns_unknown():
    from tools.product_goal_parser import parse_product_goal

    result = parse_product_goal(text="做一个不存在的产品类型 xyzzy")
    assert result.subsystem_class is None
    assert result.subsystem_status == "unknown"


def test_kpi_extracted_when_regex_and_context_both_hit():
    from tools.product_goal_parser import parse_product_goal

    result = parse_product_goal(text="做一个能升 50kg 的升降平台")
    assert result.subsystem_class == "lifting_platform"
    assert result.kpis["load_kg"].value == 50
    assert result.kpis["load_kg"].status == "extracted"
    assert result.kpis["load_kg"].unit == "kg"


def test_kpi_missing_when_only_regex_hits_no_context():
    """50kg 但无任何 lifting context_term → load_kg 应 missing。"""
    from tools.product_goal_parser import parse_product_goal

    # 此 case 中 "升降平台" 含"升"作 context，应抽到
    result = parse_product_goal(text="做一个升降平台 50kg")
    assert result.kpis["load_kg"].status == "extracted"

    # 此 case 中 "lifting platform" 不含 context_terms 内任一中文词
    # （context_terms = ["载荷", "承载", "负载", "升起", "举起", "提升", "升"]）
    # → load_kg 应 missing
    result2 = parse_product_goal(text="做一个 lifting platform，重量 50kg")
    assert result2.kpis["load_kg"].status == "missing"


def test_stroke_unit_normalize_mm_cm_m_all_normalize_to_mm():
    from tools.product_goal_parser import parse_product_goal

    for text, expected in [
        ("升降平台 行程 200mm", 200.0),
        ("升降平台 行程 20cm", 200.0),
        ("升降平台 行程 0.2m", 200.0),
    ]:
        result = parse_product_goal(text=text)
        assert result.kpis["stroke_mm"].value == expected, f"{text}: {result.kpis['stroke_mm'].value}"


def test_platform_size_extracts_pair():
    from tools.product_goal_parser import parse_product_goal

    result = parse_product_goal(text="升降平台 350x230 平台")
    assert result.kpis["platform_size_mm"].value == (350.0, 230.0)
    assert result.kpis["platform_size_mm"].status == "extracted"


def test_nfkc_normalize_fullwidth_digits():
    from tools.product_goal_parser import parse_product_goal

    # 全角数字 １００ 应等价 100
    result = parse_product_goal(text="升降平台 升起 １００kg")
    assert result.kpis["load_kg"].value == 100
