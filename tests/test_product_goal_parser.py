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
