"""SW 参数化适配器单测。requires_solidworks 标记在非 Windows CI 上 skip。"""
import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from adapters.parts.sw_parametric_adapter import SwParametricAdapter


class TestSwParametricAdapterAvailability:
    def test_is_available_returns_false_on_linux(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        adapter = SwParametricAdapter()
        ok, reason = adapter.is_available()
        assert ok is False

    def test_is_available_false_when_sw_not_installed(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")
        with patch("adapters.parts.sw_parametric_adapter.detect_solidworks") as mock_detect, \
             patch("adapters.solidworks.sw_com_session.get_session") as mock_session:
            mock_detect.return_value = MagicMock(installed=False)
            adapter = SwParametricAdapter()
            ok, reason = adapter.is_available()
        assert ok is False
        mock_session.assert_not_called()

    def test_build_part_returns_none_when_unavailable(self, monkeypatch, tmp_path):
        monkeypatch.setattr("sys.platform", "linux")
        adapter = SwParametricAdapter()
        result = adapter.build_part("flange", {"od": 90, "id": 22, "thickness": 30, "bolt_pcd": 70, "bolt_count": 6, "boss_h": 0}, tmp_path, "TEST-001")
        assert result is None


@pytest.mark.requires_solidworks
class TestSwParametricAdapterBuildFlange:
    def test_build_flange_creates_step_file(self, tmp_path):
        adapter = SwParametricAdapter()
        ok, _ = adapter.is_available()
        assert ok, "SW 不可用，跳过（应由 marker 保护）"
        step = adapter.build_part(
            "flange",
            {"od": 90.0, "id": 22.0, "thickness": 30.0,
             "bolt_pcd": 70.0, "bolt_count": 6, "boss_h": 5.0},
            tmp_path,
            "TEST-001",
        )
        assert step is not None
        assert Path(step).exists()
        assert Path(step).suffix.lower() == ".step"
        assert Path(step).stat().st_size > 1024


class TestCloseDocUsesGetTitle:
    def test_uses_get_title_property(self):
        adapter = SwParametricAdapter()
        mock_swapp = MagicMock()
        mock_model = MagicMock()
        mock_model.GetTitle = "Part1"   # COM BSTR 属性，直接赋字符串
        adapter._close_doc(mock_swapp, mock_model)
        mock_swapp.CloseDoc.assert_called_once_with("Part1")

    def test_skips_when_model_is_none(self):
        adapter = SwParametricAdapter()
        mock_swapp = MagicMock()
        adapter._close_doc(mock_swapp, None)  # 不能抛异常
        mock_swapp.CloseDoc.assert_not_called()


@pytest.mark.requires_solidworks
class TestBuildHousing:
    def test_creates_step(self, tmp_path):
        adapter = SwParametricAdapter()
        ok, _ = adapter.is_available()
        assert ok
        step = adapter.build_part(
            "housing",
            {"width": 60.0, "depth": 40.0, "height": 30.0, "wall_t": 5.0},
            tmp_path, "HOUSING-001",
        )
        assert step is not None and Path(step).exists()
        assert Path(step).stat().st_size > 1024


@pytest.mark.requires_solidworks
class TestBuildBracket:
    def test_creates_step(self, tmp_path):
        adapter = SwParametricAdapter()
        ok, _ = adapter.is_available()
        assert ok
        step = adapter.build_part(
            "bracket",
            {"width": 50.0, "height": 40.0, "thickness": 4.0},
            tmp_path, "BRACKET-001",
        )
        assert step is not None and Path(step).exists()
        assert Path(step).stat().st_size > 1024


@pytest.mark.requires_solidworks
class TestBuildSleeve:
    def test_creates_step(self, tmp_path):
        adapter = SwParametricAdapter()
        ok, _ = adapter.is_available()
        assert ok
        step = adapter.build_part(
            "sleeve",
            {"od": 30.0, "id": 15.0, "length": 50.0},
            tmp_path, "SLEEVE-001",
        )
        assert step is not None and Path(step).exists()
        assert Path(step).stat().st_size > 1024


class TestExtractParamsCover:
    """验证 _extract_params("cover") 正确返回 n_hole 键。"""

    def test_extract_params_cover_includes_n_hole(self):
        from codegen.gen_parts import _extract_params
        result = _extract_params("cover", {"dim_tolerances": []}, (60.0, 60.0, 8.0))
        assert "n_hole" in result
        assert result["n_hole"] == 4  # 默认值

    def test_extract_params_cover_respects_cover_bolt_n(self):
        from codegen.gen_parts import _extract_params
        meta = {"dim_tolerances": [{"name": "COVER_BOLT_N", "nominal": "6"}]}
        result = _extract_params("cover", meta, (60.0, 60.0, 8.0))
        assert result["n_hole"] == 6


@pytest.mark.requires_solidworks
class TestBuildSpringMechanism:
    def test_creates_step(self, tmp_path):
        adapter = SwParametricAdapter()
        ok, _ = adapter.is_available()
        assert ok
        step = adapter.build_part(
            "spring_mechanism",
            {"od": 20.0, "id": 10.0, "free_length": 40.0,
             "wire_d": 2.0, "coil_n": 6},
            tmp_path, "SPRING-001",
        )
        assert step is not None
        assert Path(step).exists()
        assert Path(step).suffix.lower() == ".step"
        assert Path(step).stat().st_size > 1024


@pytest.mark.requires_solidworks
class TestBuildPlate:
    def test_creates_step(self, tmp_path):
        adapter = SwParametricAdapter()
        ok, _ = adapter.is_available()
        assert ok
        step = adapter.build_part(
            "plate",
            {"width": 80.0, "depth": 60.0, "thickness": 5.0, "n_hole": 4},
            tmp_path, "PLATE-001",
        )
        assert step is not None
        assert Path(step).exists()
        assert Path(step).suffix.lower() == ".step"
        assert Path(step).stat().st_size > 1024


@pytest.mark.requires_solidworks
class TestBuildArm:
    def test_creates_step(self, tmp_path):
        adapter = SwParametricAdapter()
        ok, _ = adapter.is_available()
        assert ok
        step = adapter.build_part(
            "arm",
            {"length": 120.0, "width": 20.0, "thickness": 10.0,
             "end_hole_d": 8.0},
            tmp_path, "ARM-001",
        )
        assert step is not None
        assert Path(step).exists()
        assert Path(step).suffix.lower() == ".step"
        assert Path(step).stat().st_size > 1024


@pytest.mark.requires_solidworks
class TestBuildCover:
    def test_creates_step(self, tmp_path):
        adapter = SwParametricAdapter()
        ok, _ = adapter.is_available()
        assert ok
        step = adapter.build_part(
            "cover",
            {"od": 60.0, "thickness": 8.0, "id": 0.0, "n_hole": 4},
            tmp_path, "COVER-001",
        )
        assert step is not None
        assert Path(step).exists()
        assert Path(step).suffix.lower() == ".step"
        assert Path(step).stat().st_size > 1024
