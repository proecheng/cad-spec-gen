import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "codegen"))

from template_mapping_loader import load_template_mapping, match_template, _BUILTIN_KEYWORDS


class TestBuiltinKeywords:
    def test_flange_keyword(self):
        assert match_template("法兰本体", {}) == "flange"

    def test_housing_keyword(self):
        assert match_template("涂抹模块壳体", {}) == "housing"

    def test_bracket_keyword(self):
        assert match_template("安装支架", {}) == "bracket"

    def test_spring_keyword(self):
        assert match_template("弹簧限力机构总成", {}) == "spring_mechanism"

    def test_sleeve_keyword(self):
        assert match_template("PEEK绝缘套筒", {}) == "sleeve"

    def test_plate_keyword(self):
        assert match_template("底板", {}) == "plate"

    def test_arm_keyword(self):
        assert match_template("十字悬臂", {}) == "arm"

    def test_cover_keyword(self):
        assert match_template("端盖密封件", {}) == "cover"

    def test_no_match_returns_none(self):
        assert match_template("万向节柔性关节", {}) is None


class TestUserMapping:
    def test_exact_match_overrides_builtin(self):
        user = {"连接盘": "flange"}
        assert match_template("连接盘", user) == "flange"

    def test_exact_match_takes_priority_over_builtin_contains(self):
        # "弹簧壳体" 含"壳体"(builtin→housing)，但 user 覆盖→spring_mechanism
        user = {"弹簧壳体": "spring_mechanism"}
        assert match_template("弹簧壳体", user) == "spring_mechanism"

    def test_no_exact_match_falls_through_to_builtin(self):
        user = {"连接盘": "flange"}
        assert match_template("法兰本体", user) == "flange"  # builtin match


class TestLoadMapping:
    def test_load_nonexistent_returns_empty(self):
        result = load_template_mapping("/nonexistent/template_mapping.json")
        assert result == {}

    def test_load_none_returns_empty(self):
        assert load_template_mapping(None) == {}

    def test_load_valid_file(self, tmp_path):
        f = tmp_path / "template_mapping.json"
        f.write_text(
            json.dumps({"连接盘": "flange", "外壳": "housing"}),
            encoding="utf-8",
        )
        result = load_template_mapping(str(f))
        assert result == {"连接盘": "flange", "外壳": "housing"}

    def test_invalid_template_name_warned_and_skipped(self, tmp_path, capsys):
        f = tmp_path / "template_mapping.json"
        f.write_text(
            json.dumps({"怪件": "nonexistent_template"}),
            encoding="utf-8",
        )
        result = load_template_mapping(str(f))
        assert "怪件" not in result
        assert "WARNING" in capsys.readouterr().out
