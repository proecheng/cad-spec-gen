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

    # schema v2: 顶层有 schema_version + 子系统 dict
    assert data.get("schema_version") == 2, f"schema_version 应为 2：{data.get('schema_version')!r}"
    subsystems = {k: v for k, v in data.items() if k != "schema_version"}
    assert set(subsystems.keys()) == {"lifting_platform", "end_effector"}

    assert set(subsystems["lifting_platform"].keys()) == {"load_kg", "stroke_mm", "platform_size_mm"}
    assert set(subsystems["end_effector"].keys()) == {"rot_range_deg", "switch_time_s", "flange_dia_mm"}

    # schema v2: regex 是 [{pattern, factor}] 对象数组
    for subsystem, kpis in subsystems.items():
        for kpi_name, kpi in kpis.items():
            regex = kpi.get("regex")
            assert isinstance(regex, list) and regex, f"{subsystem}.{kpi_name} regex 缺"
            for entry in regex:
                assert isinstance(entry, dict) and "pattern" in entry and "factor" in entry, \
                    f"{subsystem}.{kpi_name} regex entry 缺 pattern/factor"
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
    # schema v2: 必须含 schema_version=2 才能通过 load_dictionary 入口，
    # 否则 schema_version 校验先 raise，原 implemented-subsystem-missing-kpi 断言失败
    (tmp_path / "kpi_patterns.json").write_text(
        json.dumps({"schema_version": 2}),
        encoding="utf-8",
    )
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


def test_numbers_can_be_shared_across_kpis_no_conflict():
    """50kg + 50mm 各归各位，不算冲突。"""
    from tools.product_goal_parser import parse_product_goal

    result = parse_product_goal(text="升降平台 升 50kg 行程 50mm")
    assert result.kpis["load_kg"].value == 50
    assert result.kpis["load_kg"].status == "extracted"
    assert result.kpis["stroke_mm"].value == 50
    assert result.kpis["stroke_mm"].status == "extracted"


def test_confirmed_kpis_override_parser():
    from tools.product_goal_parser import parse_product_goal

    # 自然语言抽到 50，confirmed 传 100
    result = parse_product_goal(
        text="升降平台 升 50kg",
        confirmed_kpis={"load_kg": 100.0},
    )
    assert result.kpis["load_kg"].value == 100
    assert result.kpis["load_kg"].rule == "confirmed_kpi"


def test_confirmed_subsystem_overrides_parser():
    from tools.product_goal_parser import parse_product_goal

    # 自然语言识别为 EE，confirmed 强制 lifting
    result = parse_product_goal(
        text="末端执行机构",
        confirmed_subsystem="lifting_platform",
    )
    assert result.subsystem_class == "lifting_platform"


def test_kpi_extraction_does_not_leak_cad_param_names():
    """入口层和 CAD 层严格分离：kpis 字段绝不含 PARAM_L25 / SENSOR_STROKE 等。"""
    from tools.product_goal_parser import parse_product_goal

    result = parse_product_goal(text="升降平台 升 50kg 行程 200mm 350x230 平台")
    for kpi in result.kpis.values():
        forbidden = {"PARAM_L25", "PARAM_L27", "SENSOR_STROKE", "PITCH"}
        assert kpi.kpi_name not in forbidden
        if kpi.evidence_token:
            assert kpi.evidence_token not in forbidden


@pytest.mark.parametrize("text,expected_class", [
    ("做导航 SLAM", "navigation"),
    ("运动控制系统", "motion_ctrl"),
    ("电气系统设计", "electrical"),
    ("通信总线", "communication"),
    ("充电桩", "charging"),
    ("耦合剂", "couplant"),
    ("检测传感", "detection"),
    ("集成总成", "integration"),
    ("输出端", "output"),
    ("专利布局", "patent"),
    ("项目规划", "plan"),
    ("电源系统", "power"),
    ("机器人平台", "robot_platform"),
    ("安全系统", "safety"),
    ("软件代码", "software"),
    ("系统架构", "sys_arch"),
    ("预算成本", "budget"),
])
def test_not_yet_implemented_subsystem_recognized(text, expected_class):
    """17 个 not_yet_implemented 子系统 primary_terms 直接命中。"""
    from tools.product_goal_parser import parse_product_goal

    result = parse_product_goal(text=text)
    assert result.subsystem_class == expected_class, f"识别错：{result.subsystem_class}"
    assert result.subsystem_status == "not_yet_implemented"
    assert result.kpis == {}  # not_yet_implemented 不抽 KPI


def test_unknown_input_examples():
    """三类典型 unknown 输入：无意义字符串 / 含『未知』关键词 / 完全无关文字。"""
    from tools.product_goal_parser import parse_product_goal

    for text in ["xyz123 abc", "做一个未知设备", "完全不相关的文字"]:
        result = parse_product_goal(text=text)
        assert result.subsystem_status == "unknown", f"{text}: {result.subsystem_status}"


# ===== §11.I-1: kpi_patterns.json schema v2 =====
def test_kpi_patterns_schema_version_2(tmp_path):
    """RED → GREEN: schema_version 校验在 load_dictionary 入口（不绕过 dataclass）。"""
    import json
    from tools.project_guide_dict import load_dictionary

    # 缺 schema_version → RuntimeError 含 "schema_version"
    (tmp_path / "subsystem_keywords.json").write_text(
        json.dumps({"lifting_platform": {"status": "implemented", "primary_terms": ["升降"], "supporting_terms": []}}),
        encoding="utf-8",
    )
    (tmp_path / "kpi_patterns.json").write_text(
        json.dumps({"lifting_platform": {}}),  # 无 schema_version
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="schema_version"):
        load_dictionary(dict_root=tmp_path)


def test_stroke_200_厘米_to_2000mm():
    """guard: 行程 200 厘米 → 2000mm（实证现状已正确，commit 3 schema 重构后保持）。"""
    from tools.product_goal_parser import parse_product_goal

    result = parse_product_goal(text="升降平台 升程 200 厘米")
    kpi = result.kpis["stroke_mm"]
    assert kpi.value == 2000.0, f"实际：{kpi.value}"
    assert kpi.unit == "mm"
    assert kpi.status == "extracted"


def test_stroke_0_2_米_to_200mm():
    """guard: 行程 0.2 米 → 200mm（中文"米"独立 regex 路径，commit 3 新 schema 添加）。"""
    from tools.product_goal_parser import parse_product_goal

    result = parse_product_goal(text="升降平台 升程 0.2 米")
    kpi = result.kpis["stroke_mm"]
    assert kpi.value == 200.0, f"实际：{kpi.value}"
    assert kpi.unit == "mm"
    assert kpi.status == "extracted"


def test_stroke_200mm_basic():
    """guard: 行程 200mm → 200mm（ASCII 路径不回归）。"""
    from tools.product_goal_parser import parse_product_goal

    result = parse_product_goal(text="升降平台 升程 200mm")
    kpi = result.kpis["stroke_mm"]
    assert kpi.value == 200.0
    assert kpi.unit == "mm"
    assert kpi.status == "extracted"


def test_evidence_token_preserves_fullwidth():
    """RED → GREEN: I-3 — evidence_token 取原文切片，保留全角 ５０ｋｇ。"""
    from tools.product_goal_parser import parse_product_goal

    result = parse_product_goal(text="升降平台 载荷 ５０ｋｇ")
    kpi = result.kpis["load_kg"]
    assert kpi.value == 50.0, f"value 应正常归一为 50：{kpi.value}"
    # 强断言：原文切片必须等于全角字符串
    assert kpi.evidence_token == "５０ｋｇ", f"evidence_token 应保留全角原文：{kpi.evidence_token!r}"


def test_evidence_list_token_preserves_fullwidth():
    """RED → GREEN: I-3 双改 — parser_evidence list 的 "token" 字段也取原文切片。"""
    from tools.product_goal_parser import parse_product_goal

    result = parse_product_goal(text="升降平台 载荷 ５０ｋｇ")
    # parser_evidence 是 list of dict，至少含一项 matched=load_kg
    assert result.parser_evidence, "parser_evidence 不应为空"
    matched_entries = [e for e in result.parser_evidence if e.get("matched") == "load_kg"]
    assert matched_entries, "应有 load_kg 的 evidence 条目"
    assert matched_entries[0]["token"] == "５０ｋｇ", f"evidence list token 应保留全角原文：{matched_entries[0]['token']!r}"
