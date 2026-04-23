import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "codegen"))

from gen_parts import _tol_belongs_to_part, _dim_filter_enabled


def test_flange_prefix_matches_flange_part():
    assert _tol_belongs_to_part("FLANGE_OD", "法兰本体（含十字悬臂）") is True


def test_flange_prefix_rejected_for_spring_part():
    assert _tol_belongs_to_part("FLANGE_OD", "弹簧限力机构总成") is False


def test_spring_prefix_matches_spring_part():
    assert _tol_belongs_to_part("SPRING_PIN_BORE", "弹簧限力机构总成") is True


def test_spring_prefix_rejected_for_flange_part():
    assert _tol_belongs_to_part("SPRING_PIN_BORE", "法兰本体（含十字悬臂）") is False


def test_unknown_prefix_is_universal():
    # POS_ACC 无前缀命中 → 保留给所有件
    assert _tol_belongs_to_part("POS_ACC", "法兰本体（含十字悬臂）") is True
    assert _tol_belongs_to_part("POS_ACC", "弹簧限力机构总成") is True


def test_case_insensitive():
    assert _tol_belongs_to_part("flange_od", "法兰本体") is True


def test_arm_prefix_matches_arm_part():
    assert (
        _tol_belongs_to_part("ARM_L_2", "法兰本体（含十字悬臂）") is True
    )  # 法兰含悬臂
    assert _tol_belongs_to_part("ARM_L_2", "弹簧限力机构总成") is False


def test_dim_filter_enabled_default_on(monkeypatch):
    monkeypatch.delenv("CAD_SPEC_GEN_DIM_FILTER", raising=False)
    assert _dim_filter_enabled() is True


def test_dim_filter_enabled_off(monkeypatch):
    monkeypatch.setenv("CAD_SPEC_GEN_DIM_FILTER", "off")
    assert _dim_filter_enabled() is False


def test_dim_filter_enabled_case_insensitive(monkeypatch):
    monkeypatch.setenv("CAD_SPEC_GEN_DIM_FILTER", "OFF")
    assert _dim_filter_enabled() is False
