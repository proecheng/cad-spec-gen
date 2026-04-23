# tests/test_check_toolbox_path_healthy.py
import sys
import pytest
from pathlib import Path


class TestCheckToolboxPathHealthy:
    def _make_info(self, toolbox_dir: str):
        from adapters.solidworks import sw_detect
        return sw_detect.SwInfo(installed=True, toolbox_dir=toolbox_dir)

    def test_empty_toolbox_dir_returns_false(self):
        from adapters.solidworks.sw_detect import check_toolbox_path_healthy
        ok, reason = check_toolbox_path_healthy(self._make_info(""))
        assert ok is False
        assert reason is not None

    def test_healthy_dir_returns_true(self, tmp_path):
        from adapters.solidworks.sw_detect import check_toolbox_path_healthy
        # 创建 swbrowser.sldedb + 一个 .sldprt
        (tmp_path / "swbrowser.sldedb").write_bytes(b"SQLite")
        sldprt_dir = tmp_path / "GB" / "bolts"
        sldprt_dir.mkdir(parents=True)
        (sldprt_dir / "hex_bolt_m6.sldprt").write_bytes(b"\x00")
        ok, reason = check_toolbox_path_healthy(self._make_info(str(tmp_path)))
        assert ok is True
        assert reason is None

    def test_missing_sldedb_returns_false(self, tmp_path):
        from adapters.solidworks.sw_detect import check_toolbox_path_healthy
        # 有 sldprt 但没有 sldedb
        sldprt_dir = tmp_path / "GB"
        sldprt_dir.mkdir()
        (sldprt_dir / "part.sldprt").write_bytes(b"\x00")
        ok, reason = check_toolbox_path_healthy(self._make_info(str(tmp_path)))
        assert ok is False
        assert "sldedb" in reason.lower()

    def test_no_sldprt_returns_false(self, tmp_path):
        from adapters.solidworks.sw_detect import check_toolbox_path_healthy
        # 有 sldedb 但没有 sldprt
        (tmp_path / "swbrowser.sldedb").write_bytes(b"SQLite")
        ok, reason = check_toolbox_path_healthy(self._make_info(str(tmp_path)))
        assert ok is False
        assert "sldprt" in reason.lower()

    def test_nonexistent_dir_returns_false(self):
        from adapters.solidworks.sw_detect import check_toolbox_path_healthy
        ok, reason = check_toolbox_path_healthy(self._make_info(r"C:\does\not\exist"))
        assert ok is False
        assert reason is not None
