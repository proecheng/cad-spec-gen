"""Task 14.6：sw_config_lists_cache module 单元测试（spec §6.1 A+B 矩阵）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


class TestModuleConstants:
    def test_module_imports_and_has_schema_version(self):
        from adapters.solidworks import sw_config_lists_cache as cache_mod
        assert cache_mod.CONFIG_LISTS_SCHEMA_VERSION == 1

    def test_cache_path_is_user_level(self):
        from adapters.solidworks.sw_config_lists_cache import get_config_lists_cache_path
        p = get_config_lists_cache_path()
        assert p == Path.home() / ".cad-spec-gen" / "sw_config_lists.json"


class TestEmptyCache:
    def test_empty_cache_has_5_fields(self):
        from adapters.solidworks.sw_config_lists_cache import (
            _empty_config_lists_cache,
            CONFIG_LISTS_SCHEMA_VERSION,
        )
        cache = _empty_config_lists_cache()
        assert cache["schema_version"] == CONFIG_LISTS_SCHEMA_VERSION
        assert "generated_at" in cache  # ISO timestamp
        assert cache["sw_version"] is None  # 故意 None → 触发 envelope_invalidated
        assert cache["toolbox_path"] is None
        assert cache["entries"] == {}


class TestSaveCache:
    def test_save_writes_valid_json(self, tmp_path, monkeypatch):
        from adapters.solidworks import sw_config_lists_cache as m
        monkeypatch.setattr(m, "get_config_lists_cache_path",
                            lambda: tmp_path / "deeper" / "sw_config_lists.json")
        cache = {
            "schema_version": 1,
            "generated_at": "2026-04-26T12:34:56+00:00",
            "sw_version": 24,
            "toolbox_path": "C:/SW",
            "entries": {"C:/p1.sldprt": {"mtime": 100, "size": 200, "configs": ["A"]}},
        }
        m._save_config_lists_cache(cache)
        target = tmp_path / "deeper" / "sw_config_lists.json"
        assert target.exists()
        data = json.loads(target.read_text(encoding="utf-8"))
        assert data == cache

    def test_save_creates_parent_dir_if_missing(self, tmp_path, monkeypatch):
        from adapters.solidworks import sw_config_lists_cache as m
        monkeypatch.setattr(m, "get_config_lists_cache_path",
                            lambda: tmp_path / "newdir" / "newer" / "f.json")
        m._save_config_lists_cache({"entries": {}})
        assert (tmp_path / "newdir" / "newer" / "f.json").exists()

    def test_save_atomic_no_tmp_residue(self, tmp_path, monkeypatch):
        from adapters.solidworks import sw_config_lists_cache as m
        target = tmp_path / "sw_config_lists.json"
        monkeypatch.setattr(m, "get_config_lists_cache_path", lambda: target)
        m._save_config_lists_cache({"entries": {}})
        assert not (tmp_path / "sw_config_lists.json.tmp").exists()


class TestLoadCache:
    def test_load_missing_file_returns_empty(self, tmp_path, monkeypatch):
        from adapters.solidworks import sw_config_lists_cache as m
        monkeypatch.setattr(m, "get_config_lists_cache_path",
                            lambda: tmp_path / "no_such.json")
        cache = m._load_config_lists_cache()
        assert cache["entries"] == {}
        assert cache["schema_version"] == m.CONFIG_LISTS_SCHEMA_VERSION

    def test_load_valid_file_round_trips(self, tmp_path, monkeypatch):
        from adapters.solidworks import sw_config_lists_cache as m
        target = tmp_path / "sw_config_lists.json"
        monkeypatch.setattr(m, "get_config_lists_cache_path", lambda: target)
        original = {
            "schema_version": 1,
            "generated_at": "2026-04-26T12:34:56+00:00",
            "sw_version": 24,
            "toolbox_path": "C:/SW",
            "entries": {"C:/p1.sldprt": {"mtime": 100, "size": 200, "configs": ["A"]}},
        }
        target.write_text(json.dumps(original), encoding="utf-8")
        loaded = m._load_config_lists_cache()
        assert loaded == original

    def test_load_corrupt_json_returns_empty(self, tmp_path, monkeypatch):
        from adapters.solidworks import sw_config_lists_cache as m
        target = tmp_path / "sw_config_lists.json"
        monkeypatch.setattr(m, "get_config_lists_cache_path", lambda: target)
        target.write_text("{not valid json", encoding="utf-8")
        cache = m._load_config_lists_cache()
        assert cache["entries"] == {}

    def test_load_schema_version_mismatch_returns_empty(self, tmp_path, monkeypatch):
        from adapters.solidworks import sw_config_lists_cache as m
        target = tmp_path / "sw_config_lists.json"
        monkeypatch.setattr(m, "get_config_lists_cache_path", lambda: target)
        old = {"schema_version": 999, "entries": {"C:/p1.sldprt": {"configs": ["X"]}}}
        target.write_text(json.dumps(old), encoding="utf-8")
        cache = m._load_config_lists_cache()
        assert cache["entries"] == {}  # 旧 v999 entries 不读
        assert cache["schema_version"] == m.CONFIG_LISTS_SCHEMA_VERSION


class TestEnvelopeInvalidated:
    """Envelope-level 失效（spec §4 场景 D）：sw_version / toolbox_path 任一不符。"""

    def test_first_run_empty_cache_invalidated(self, monkeypatch):
        """空 cache (sw_version=None) 必失效。"""
        from adapters.solidworks import sw_config_lists_cache as m
        from adapters.solidworks import sw_detect

        sw_detect._reset_cache()
        monkeypatch.setattr(
            sw_detect, "detect_solidworks",
            lambda: sw_detect.SwInfo(installed=True, version_year=24,
                                     toolbox_dir="C:/SW"),
        )
        cache = m._empty_config_lists_cache()
        assert m._envelope_invalidated(cache) is True

    def test_matching_envelope_not_invalidated(self, monkeypatch):
        from adapters.solidworks import sw_config_lists_cache as m
        from adapters.solidworks import sw_detect

        sw_detect._reset_cache()
        monkeypatch.setattr(
            sw_detect, "detect_solidworks",
            lambda: sw_detect.SwInfo(installed=True, version_year=24,
                                     toolbox_dir="C:/SW"),
        )
        cache = {
            "schema_version": 1, "sw_version": 24, "toolbox_path": "C:/SW",
            "entries": {},
        }
        assert m._envelope_invalidated(cache) is False

    def test_sw_version_mismatch_invalidated(self, monkeypatch):
        from adapters.solidworks import sw_config_lists_cache as m
        from adapters.solidworks import sw_detect

        sw_detect._reset_cache()
        monkeypatch.setattr(
            sw_detect, "detect_solidworks",
            lambda: sw_detect.SwInfo(installed=True, version_year=24,
                                     toolbox_dir="C:/SW"),
        )
        cache = {
            "schema_version": 1, "sw_version": 23, "toolbox_path": "C:/SW",
            "entries": {"C:/p.sldprt": {"mtime": 1, "size": 1, "configs": []}},
        }
        assert m._envelope_invalidated(cache) is True

    def test_toolbox_path_mismatch_invalidated(self, monkeypatch):
        from adapters.solidworks import sw_config_lists_cache as m
        from adapters.solidworks import sw_detect

        sw_detect._reset_cache()
        monkeypatch.setattr(
            sw_detect, "detect_solidworks",
            lambda: sw_detect.SwInfo(installed=True, version_year=24,
                                     toolbox_dir="C:/NewSW"),
        )
        cache = {
            "schema_version": 1, "sw_version": 24, "toolbox_path": "C:/SW",
            "entries": {},
        }
        assert m._envelope_invalidated(cache) is True


class TestEntryValid:
    """Per-entry 失效（spec §4 场景 C）：mtime / size 任一不符。"""

    def test_missing_entry_invalid(self, tmp_path):
        from adapters.solidworks import sw_config_lists_cache as m
        cache = {"entries": {}}
        sldprt = tmp_path / "p.sldprt"
        sldprt.write_bytes(b"x" * 100)
        assert m._config_list_entry_valid(cache, str(sldprt)) is False

    def test_matching_mtime_size_valid(self, tmp_path):
        from adapters.solidworks import sw_config_lists_cache as m
        sldprt = tmp_path / "p.sldprt"
        sldprt.write_bytes(b"x" * 100)
        st = sldprt.stat()
        cache = {"entries": {str(sldprt): {
            "mtime": int(st.st_mtime), "size": st.st_size, "configs": ["A"],
        }}}
        assert m._config_list_entry_valid(cache, str(sldprt)) is True

    def test_mtime_mismatch_invalid(self, tmp_path):
        from adapters.solidworks import sw_config_lists_cache as m
        sldprt = tmp_path / "p.sldprt"
        sldprt.write_bytes(b"x" * 100)
        cache = {"entries": {str(sldprt): {
            "mtime": 0, "size": sldprt.stat().st_size, "configs": ["A"],
        }}}
        assert m._config_list_entry_valid(cache, str(sldprt)) is False

    def test_size_mismatch_invalid(self, tmp_path):
        from adapters.solidworks import sw_config_lists_cache as m
        sldprt = tmp_path / "p.sldprt"
        sldprt.write_bytes(b"x" * 100)
        st = sldprt.stat()
        cache = {"entries": {str(sldprt): {
            "mtime": int(st.st_mtime), "size": 0, "configs": ["A"],
        }}}
        assert m._config_list_entry_valid(cache, str(sldprt)) is False

    def test_missing_sldprt_file_invalid(self):
        """sldprt 文件已删 → entry 视为 invalid（下次 prewarm 不会重列删了的件）。"""
        from adapters.solidworks import sw_config_lists_cache as m
        cache = {"entries": {"C:/no_such.sldprt": {
            "mtime": 100, "size": 100, "configs": ["A"],
        }}}
        assert m._config_list_entry_valid(cache, "C:/no_such.sldprt") is False
