"""工厂函数测试：exec 生成代码并检查 face 数。"""
import sys
import textwrap
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "codegen"))

import cadquery as cq
import pytest
from part_templates.flange import make_flange
from part_templates.housing import make_housing
from part_templates.bracket import make_bracket
from part_templates.spring_mechanism import make_spring_mechanism
from part_templates.sleeve import make_sleeve
from part_templates.plate import make_plate
from part_templates.arm import make_arm
from part_templates.cover import make_cover


def _exec_template(code: str) -> cq.Workplane:
    """执行模板代码字符串（自动 dedent，兼容 4 空格嵌入格式）。"""
    ns = {"cq": cq}
    exec(textwrap.dedent(code), ns)
    return ns["body"]


class TestMakeFlange:
    def test_returns_none_when_od_missing(self):
        assert make_flange(od=None, id=22, thickness=30, bolt_pcd=70) is None

    def test_returns_none_when_id_missing(self):
        assert make_flange(od=90, id=None, thickness=30, bolt_pcd=70) is None

    def test_returns_none_when_thickness_missing(self):
        assert make_flange(od=90, id=22, thickness=None, bolt_pcd=70) is None

    def test_returns_none_when_bolt_pcd_missing(self):
        assert make_flange(od=90, id=22, thickness=30, bolt_pcd=None) is None

    def test_returns_none_when_id_ge_od(self):
        assert make_flange(od=20, id=25, thickness=10, bolt_pcd=15) is None

    def test_returns_code_string(self):
        code = make_flange(od=90, id=22, thickness=30, bolt_pcd=70)
        assert isinstance(code, str)
        assert "body" in code
        assert "cq.Workplane" in code

    def test_face_count_ge_30(self):
        code = make_flange(od=90, id=22, thickness=30, bolt_pcd=70, bolt_count=6)
        body = _exec_template(code)
        assert body.faces().size() >= 30

    def test_custom_bolt_count(self):
        code = make_flange(od=90, id=22, thickness=30, bolt_pcd=70, bolt_count=8)
        body = _exec_template(code)
        assert body.faces().size() >= 30

    def test_with_boss(self):
        code = make_flange(od=90, id=22, thickness=30, bolt_pcd=70, boss_h=10)
        body = _exec_template(code)
        assert body.faces().size() >= 30


class TestMakeHousing:
    def test_returns_none_when_width_missing(self):
        assert make_housing(width=None, depth=50, height=60, wall_t=4) is None

    def test_returns_none_when_wall_t_missing(self):
        assert make_housing(width=50, depth=50, height=60, wall_t=None) is None

    def test_returns_code_string(self):
        code = make_housing(width=50, depth=50, height=60, wall_t=4)
        assert isinstance(code, str) and "body" in code

    def test_face_count_ge_20(self):
        code = make_housing(width=50, depth=50, height=60, wall_t=4)
        body = _exec_template(code)
        assert body.faces().size() >= 20


class TestMakeBracket:
    def test_returns_none_when_param_missing(self):
        assert make_bracket(width=None, height=50, thickness=5) is None

    def test_returns_code_string(self):
        code = make_bracket(width=60, height=80, thickness=6)
        assert isinstance(code, str) and "body" in code

    def test_face_count_ge_30(self):
        code = make_bracket(width=60, height=80, thickness=6)
        body = _exec_template(code)
        assert body.faces().size() >= 30


class TestMakeSpringMechanism:
    def test_returns_none_when_od_missing(self):
        assert make_spring_mechanism(od=None, id=8, free_length=40) is None

    def test_returns_none_when_free_length_missing(self):
        assert make_spring_mechanism(od=20, id=8, free_length=None) is None

    def test_returns_code_string(self):
        code = make_spring_mechanism(od=20, id=8, free_length=40)
        assert isinstance(code, str) and "body" in code

    def test_face_count_ge_30(self):
        code = make_spring_mechanism(od=20, id=8, free_length=40, coil_n=8)
        body = _exec_template(code)
        assert body.faces().size() >= 30


class TestMakeSleeve:
    def test_returns_none_when_od_missing(self):
        assert make_sleeve(od=None, id=10, length=30) is None

    def test_returns_none_when_id_ge_od(self):
        assert make_sleeve(od=10, id=15, length=30) is None

    def test_returns_code_string(self):
        code = make_sleeve(od=20, id=10, length=30)
        assert isinstance(code, str) and "body" in code

    def test_face_count_ge_20(self):
        code = make_sleeve(od=20, id=10, length=30)
        body = _exec_template(code)
        assert body.faces().size() >= 20


class TestMakePlate:
    def test_returns_none_when_param_missing(self):
        assert make_plate(width=None, depth=80, thickness=5) is None

    def test_returns_code_string(self):
        code = make_plate(width=100, depth=80, thickness=5)
        assert isinstance(code, str) and "body" in code

    def test_face_count_ge_20(self):
        code = make_plate(width=100, depth=80, thickness=5, n_hole=4)
        body = _exec_template(code)
        assert body.faces().size() >= 20


class TestMakeArm:
    def test_returns_none_when_param_missing(self):
        assert make_arm(length=None, width=12, thickness=8) is None

    def test_returns_code_string(self):
        code = make_arm(length=80, width=12, thickness=8)
        assert isinstance(code, str) and "body" in code

    def test_face_count_ge_20(self):
        code = make_arm(length=80, width=12, thickness=8)
        body = _exec_template(code)
        assert body.faces().size() >= 20


class TestMakeCover:
    def test_returns_none_when_od_missing(self):
        assert make_cover(od=None, thickness=5) is None

    def test_returns_code_string(self):
        code = make_cover(od=60, thickness=5)
        assert isinstance(code, str) and "body" in code

    def test_face_count_ge_20(self):
        code = make_cover(od=60, thickness=5, n_hole=4)
        body = _exec_template(code)
        assert body.faces().size() >= 20

    def test_with_center_hole(self):
        code = make_cover(od=60, thickness=5, id=20)
        body = _exec_template(code)
        assert body.faces().size() >= 20
