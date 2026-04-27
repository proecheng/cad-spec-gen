"""Task 14.6：sw_config_lists_cache module 单元测试（spec §6.1 A+B 矩阵）。"""

from __future__ import annotations

import json
from pathlib import Path


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

    # ─── rev 4 + rev 5 新增（spec rev 6 §3.4 + §3.5 + §5 I7/I8）───

    def test_save_permission_error_first_call_writes_banner_to_stderr(
        self, monkeypatch, tmp_path, capsys,
    ):
        """spec §3.4：mock write_text 抛 PermissionError → stderr banner 出现。"""
        from adapters.solidworks import sw_config_lists_cache as m

        monkeypatch.setattr(
            m, "get_config_lists_cache_path",
            lambda: tmp_path / "sw_config_lists.json",
        )
        from pathlib import Path
        def fake_write_text(self, *args, **kwargs):
            raise PermissionError("OneDrive 锁定")
        monkeypatch.setattr(Path, "write_text", fake_write_text)

        m._save_config_lists_cache({
            "schema_version": 1, "generated_at": "x",
            "sw_version": 24, "toolbox_path": "X", "entries": {},
        })

        err = capsys.readouterr().err
        assert "⚠ cache 文件" in err
        assert "PermissionError" in err
        assert "本次 codegen 不受影响" in err  # rev 3 I3 安抚文案

    def test_save_failure_second_call_no_banner_only_log_warning(
        self, monkeypatch, tmp_path, capsys, caplog,
    ):
        """spec §3.5 / I6：同 process 第 2 次 save 失败 → 不再 banner，只 log.warning。"""
        from adapters.solidworks import sw_config_lists_cache as m

        monkeypatch.setattr(
            m, "get_config_lists_cache_path",
            lambda: tmp_path / "sw_config_lists.json",
        )
        from pathlib import Path
        def fake_write_text(self, *args, **kwargs):
            raise PermissionError("锁定中")
        monkeypatch.setattr(Path, "write_text", fake_write_text)

        cache = {
            "schema_version": 1, "generated_at": "x",
            "sw_version": 24, "toolbox_path": "X", "entries": {},
        }

        # 第 1 次：banner
        m._save_config_lists_cache(cache)
        capsys.readouterr()  # 清空

        # 第 2 次：仅 log.warning，不 banner
        with caplog.at_level("WARNING"):
            m._save_config_lists_cache(cache)
        err = capsys.readouterr().err
        assert "⚠ cache 文件" not in err
        assert any("重复失败" in r.message for r in caplog.records)

    def test_save_oserror_does_not_propagate_to_caller(
        self, monkeypatch, tmp_path,
    ):
        """spec §3.4 / I1：函数返 None 不 raise。"""
        from adapters.solidworks import sw_config_lists_cache as m

        monkeypatch.setattr(
            m, "get_config_lists_cache_path",
            lambda: tmp_path / "sw_config_lists.json",
        )
        from pathlib import Path
        def fake_write_text(self, *args, **kwargs):
            raise OSError("disk full")
        monkeypatch.setattr(Path, "write_text", fake_write_text)

        result = m._save_config_lists_cache({
            "schema_version": 1, "generated_at": "x",
            "sw_version": 24, "toolbox_path": "X", "entries": {},
        })
        assert result is None  # 不 raise

    def test_save_oserror_subclass_disk_full_does_not_propagate(
        self, monkeypatch, tmp_path,
    ):
        """spec §3.4 边角：OSError 子类（ENOSPC 等）也静默自愈。"""
        from adapters.solidworks import sw_config_lists_cache as m

        monkeypatch.setattr(
            m, "get_config_lists_cache_path",
            lambda: tmp_path / "sw_config_lists.json",
        )
        from pathlib import Path
        import errno

        def fake_write_text(self, *args, **kwargs):
            raise OSError(errno.ENOSPC, "No space left on device")
        monkeypatch.setattr(Path, "write_text", fake_write_text)

        # 不 raise
        m._save_config_lists_cache({
            "schema_version": 1, "generated_at": "x",
            "sw_version": 24, "toolbox_path": "X", "entries": {},
        })

    def test_invariant_save_failure_emits_user_visible_banner(
        self, monkeypatch, tmp_path, capsys,
    ):
        """spec §5 I7 直测：banner 含 ⚠ + 用户行动指引 + 安抚文案三 marker."""
        from adapters.solidworks import sw_config_lists_cache as m

        monkeypatch.setattr(
            m, "get_config_lists_cache_path",
            lambda: tmp_path / "sw_config_lists.json",
        )
        from pathlib import Path
        def fake_write_text(self, *args, **kwargs):
            raise PermissionError("test")
        monkeypatch.setattr(Path, "write_text", fake_write_text)

        m._save_config_lists_cache({
            "schema_version": 1, "generated_at": "x",
            "sw_version": 24, "toolbox_path": "X", "entries": {},
        })

        err = capsys.readouterr().err
        assert "⚠" in err  # 视觉 emoji marker
        assert "请检查" in err  # 用户行动指引
        assert "本次 codegen 不受影响" in err  # rev 3 I3 安抚
        assert "不再 banner" in err  # 防 spam 提示（reviewer 加固，spec §3.4 第 4 marker）

    def test_invariant_v220_cache_schema_v1_loads_without_break(
        self, monkeypatch, tmp_path,
    ):
        """spec §5 I8 直测：v2.20.0 cache schema v1 fixture 加载 OK."""
        import shutil
        from pathlib import Path
        from adapters.solidworks import sw_config_lists_cache as m

        # 拷贝 fixture 到 tmp
        fixture_src = Path(__file__).parent / "fixtures" / "sw_config_lists_v220.json"
        fixture_dst = tmp_path / "sw_config_lists.json"
        shutil.copy(fixture_src, fixture_dst)

        monkeypatch.setattr(m, "get_config_lists_cache_path", lambda: fixture_dst)

        cache = m._load_config_lists_cache()
        assert cache["schema_version"] == 1
        assert cache["sw_version"] == 24
        assert "C:\\test\\p1.sldprt" in cache["entries"]
        assert cache["entries"]["C:\\test\\p1.sldprt"]["configs"] == ["A", "B"]
        # reviewer 加固：spec I5 terminal mark [] 双 entry 结构第二半（防 fixture 改删未感知）
        assert "C:\\test\\p2.sldprt" in cache["entries"]
        assert cache["entries"]["C:\\test\\p2.sldprt"]["configs"] == []


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
