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
@pytest.mark.xfail(reason="Task 16 尚未实现：_build_flange 当前为 stub，返回 None", strict=False)
class TestSwParametricAdapterBuildFlange:
    def test_build_flange_creates_step_file(self, tmp_path):
        adapter = SwParametricAdapter()
        ok, _ = adapter.is_available()
        assert ok, "SW 不可用，跳过（应由 marker 保护）"
        step = adapter.build_part(
            "flange",
            {"od": 90.0, "id": 22.0, "thickness": 30.0, "bolt_pcd": 70.0, "bolt_count": 6, "boss_h": 5.0},
            tmp_path,
            "TEST-001",
        )
        assert step is not None
        assert Path(step).exists()
        assert Path(step).suffix.lower() == ".step"
