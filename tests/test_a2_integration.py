"""A2 集成验收：gen_parts 生成正确 L2 几何，dim_tolerances 净化（A2-0）。"""
import io
import sys
import ast
from contextlib import redirect_stdout
from pathlib import Path

import pytest

pytest.importorskip("cadquery")
import cadquery as cq

_REPO = Path(__file__).parent.parent
_EE_001_01 = _REPO / "cad" / "end_effector" / "ee_001_01.py"
_EE_001_02 = _REPO / "cad" / "end_effector" / "ee_001_02.py"


def _run_make_fn(py_file: Path, fn_name: str) -> cq.Workplane:
    """动态加载并执行指定零件文件的 make 函数。"""
    sys.path.insert(0, str(_REPO / "cad" / "end_effector"))
    ns: dict = {}
    exec(compile(py_file.read_text(encoding="utf-8"), str(py_file), "exec"), ns)
    return ns[fn_name]()


def _parse_dim_tolerances(py_file: Path) -> list[dict]:
    """从生成的 ee_*.py 中 AST 提取 dim_tolerances 列表（不执行代码）。"""
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and k.value == "dim_tolerances":
                    return ast.literal_eval(v)
    return []


class TestFlangeA20Filter:
    def test_ee_001_01_dim_tolerances_no_spring_pin_bore(self):
        """A2-0 验收：法兰件的 dim_tolerances 不含 SPRING_PIN_BORE（弹簧销孔尺寸）。"""
        tols = _parse_dim_tolerances(_EE_001_01)
        names = [t["name"] for t in tols]
        assert "SPRING_PIN_BORE" not in names, (
            f"A2-0 过滤失败：法兰件不应含弹簧销孔公差，实际: {names}"
        )

    def test_ee_001_01_dim_tolerances_count_reduced(self):
        """A2-0 验收：净化后的公差数量少于原始 12 条（SPRING_PIN_BORE 被移除）。"""
        tols = _parse_dim_tolerances(_EE_001_01)
        assert len(tols) < 12, f"期望 <12 条，实际 {len(tols)} 条"

    def test_ee_001_01_dim_tolerances_retains_flange_entries(self):
        """A2-0 正确性：法兰件保留所有 FLANGE_* 条目。"""
        tols = _parse_dim_tolerances(_EE_001_01)
        names = [t["name"] for t in tols]
        for expected in ["FLANGE_BODY_OD", "FLANGE_BODY_ID", "FLANGE_TOTAL_THICK"]:
            assert expected in names, f"法兰件缺少关键公差 {expected}，实际: {names}"


class TestFlangeGeometry:
    def test_flange_face_count_ge_30(self):
        """A2 验收：法兰件 face ≥ 30（CadQuery 模板生成）。"""
        body = _run_make_fn(_EE_001_01, "make_ee_001_01")
        assert body.faces().size() >= 30, f"face 数={body.faces().size()}，期望 ≥30"


class TestSleeveGeometry:
    @pytest.mark.skip(
        reason=(
            "PEEK绝缘段 (ee_001_02) 命名不含'套筒'，不触发 sleeve 路由。"
            "如需验证 sleeve 模板，可在 template_mapping.json 添加 '绝缘段': 'sleeve' "
            "并在 CAD_SPEC.md 中补充 SLEEVE_OD/SLEEVE_ID/SLEEVE_L 公差后重新生成。"
        )
    )
    def test_sleeve_face_count_ge_20(self):
        body = _run_make_fn(_EE_001_02, "make_ee_001_02")
        assert body.faces().size() >= 20, f"face 数={body.faces().size()}，期望 ≥20"


class TestMappingJsonRouting:
    def test_template_mapping_json_loads_without_warning(self):
        """template_mapping.json 示例文件可被正确加载（无 WARNING 输出）。"""
        sys.path.insert(0, str(_REPO / "codegen"))
        from template_mapping_loader import load_template_mapping

        buf = io.StringIO()
        mapping_path = str(_REPO / "template_mapping.json")
        with redirect_stdout(buf):
            result = load_template_mapping(mapping_path)
        output = buf.getvalue()
        assert "WARNING" not in output, f"加载示例 mapping.json 不应有 WARNING: {output}"
        assert "连接盘" in result
        assert result["连接盘"] == "flange"

    def test_match_template_uses_user_mapping(self):
        """AC5：自定义命名通过 template_mapping.json 正确路由到 flange。"""
        sys.path.insert(0, str(_REPO / "codegen"))
        from template_mapping_loader import load_template_mapping, match_template

        mapping_path = str(_REPO / "template_mapping.json")
        user_mapping = load_template_mapping(mapping_path)
        # "连接盘" is in template_mapping.json → flange
        result = match_template("连接盘", user_mapping)
        assert result == "flange"
        # "法兰本体（含十字悬臂）" matches builtin keyword "法兰" → flange
        result2 = match_template("法兰本体（含十字悬臂）", user_mapping)
        assert result2 == "flange"
