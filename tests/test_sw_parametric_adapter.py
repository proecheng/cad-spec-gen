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

    def test_build_part_rejects_step_files_without_importable_geometry(
        self, monkeypatch, tmp_path
    ):
        adapter = SwParametricAdapter()
        monkeypatch.setattr(adapter, "is_available", lambda: (True, None))

        step_path = tmp_path / "TEST-001.step"
        step_path.write_text("ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n", encoding="utf-8")

        build_calls = []

        def fake_build(params, out_step):
            build_calls.append(out_step)
            out_step.write_text(step_path.read_text(encoding="utf-8"), encoding="utf-8")
            return out_step

        monkeypatch.setattr(adapter, "_build_flange", fake_build)
        monkeypatch.setattr(
            adapter,
            "_validate_step_geometry",
            lambda path: False,
            raising=False,
        )
        monkeypatch.setattr(
            adapter,
            "_build_cadquery_fallback",
            lambda tpl_type, params, out_step: None,
            raising=False,
        )

        result = adapter.build_part(
            "flange",
            {
                "od": 90,
                "id": 22,
                "thickness": 30,
                "bolt_pcd": 70,
                "bolt_count": 6,
                "boss_h": 0,
            },
            tmp_path,
            "TEST-001",
        )

        assert result is None
        assert build_calls == [step_path]
        assert not step_path.exists()


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


class TestBuildPlateContract:
    def test_plate_step_contract_rejects_top_plane_axis_permutation(
        self, tmp_path
    ):
        pytest.importorskip("cadquery")
        import cadquery as cq

        adapter = SwParametricAdapter()
        wrong_step = tmp_path / "wrong_plate.step"
        cq.exporters.export(
            cq.Workplane("XY").box(
                80.0, 5.0, 60.0, centered=(True, True, False)),
            str(wrong_step),
        )

        assert adapter._validate_step_contract(
            "plate",
            {"width": 80.0, "depth": 60.0, "thickness": 5.0},
            wrong_step,
        ) is False

    def test_build_plate_uses_front_plane_for_xy_sketch_and_z_thickness(
        self, monkeypatch, tmp_path
    ):
        adapter = SwParametricAdapter()
        mock_swapp = MagicMock()
        mock_model = MagicMock()
        mock_model.Extension.SelectByID2.return_value = True

        monkeypatch.setattr(adapter, "_get_swapp", lambda: mock_swapp)
        monkeypatch.setattr(adapter, "_new_part_doc", lambda _swapp: mock_model)
        monkeypatch.setattr(adapter, "_export_step", lambda _model, _path: True)
        monkeypatch.setattr(adapter, "_close_doc", lambda _swapp, _model: None)

        step = adapter._build_plate(
            {"width": 80.0, "depth": 60.0, "thickness": 5.0, "n_hole": 4},
            tmp_path / "plate.step",
        )

        assert step == tmp_path / "plate.step"
        plane_names = [
            call.args[0]
            for call in mock_model.Extension.SelectByID2.call_args_list
            if len(call.args) > 1 and call.args[1] == "PLANE"
        ]
        assert plane_names
        assert set(plane_names) == {"前视基准面"}


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
