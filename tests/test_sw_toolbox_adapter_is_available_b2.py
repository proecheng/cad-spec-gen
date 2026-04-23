# tests/test_sw_toolbox_adapter_is_available_b2.py
import sys
import pytest


@pytest.fixture()
def good_info(tmp_path):
    """构造一个 toolbox_dir 健康、非 Standard 的 SwInfo。"""
    from adapters.solidworks import sw_detect
    # 创建健康 toolbox_dir
    (tmp_path / "swbrowser.sldedb").write_bytes(b"SQLite")
    sub = tmp_path / "GB"
    sub.mkdir()
    (sub / "part.sldprt").write_bytes(b"\x00")
    return sw_detect.SwInfo(
        installed=True,
        version_year=2024,
        pywin32_available=True,
        toolbox_dir=str(tmp_path),
        toolbox_addin_enabled=False,  # 未启用 Add-in
        edition="professional",
    )


@pytest.mark.skipif(sys.platform != "win32", reason="需要 Windows")
class TestIsAvailableB2:
    def test_addin_disabled_but_healthy_returns_true(self, monkeypatch, good_info):
        """B-2: Add-in 未启用 + 其他条件满足 → (True, None)。"""
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_detect, sw_com_session

        sw_detect._reset_cache()
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: good_info)

        class FakeSession:
            def is_healthy(self): return True
        monkeypatch.setattr(sw_com_session, "get_session", lambda: FakeSession())

        ok, reason = SwToolboxAdapter().is_available()
        assert ok is True
        assert reason is None

    def test_standard_edition_returns_false(self, monkeypatch, good_info, tmp_path):
        """B-13: Standard 版 → (False, reason 含 'Standard edition')。"""
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_detect

        sw_detect._reset_cache()
        bad_info = sw_detect.SwInfo(
            installed=True, version_year=2024,
            pywin32_available=True, toolbox_dir=str(tmp_path),
            edition="standard",
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: bad_info)

        ok, reason = SwToolboxAdapter().is_available()
        assert ok is False
        assert reason is not None
        assert "Standard edition" in reason

    def test_unhealthy_toolbox_path_returns_false(self, monkeypatch, good_info):
        """B-8: toolbox_dir 不健康 → (False, reason 非空)。"""
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_detect

        sw_detect._reset_cache()
        bad_info = sw_detect.SwInfo(
            installed=True, version_year=2024,
            pywin32_available=True,
            toolbox_dir=r"C:\does\not\exist",
            edition="professional",
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: bad_info)

        ok, reason = SwToolboxAdapter().is_available()
        assert ok is False
        assert reason is not None

    def test_circuit_broken_returns_false(self, monkeypatch, good_info):
        """熔断 → (False, reason 含 'circuit' 或 'breaker')。"""
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_detect, sw_com_session

        sw_detect._reset_cache()
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: good_info)

        class BrokenSession:
            def is_healthy(self): return False
        monkeypatch.setattr(sw_com_session, "get_session", lambda: BrokenSession())

        ok, reason = SwToolboxAdapter().is_available()
        assert ok is False
        assert reason is not None
        assert "circuit" in reason.lower() or "breaker" in reason.lower()
