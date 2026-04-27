"""adapters/solidworks/sw_config_broker.py 端到端 user 场景测试（rev 5 F 新增）.

模式：用 user 视角描述场景；mock 必要的外部依赖（subprocess / SW detect /
file system）；跑真实 broker / cache 全 layer。

spec 引用: docs/superpowers/specs/2026-04-27-sw-config-broker-m2-m4-cleanup-design.md §7.6
"""

from __future__ import annotations

import json
import unittest.mock as mock
from pathlib import Path

import pytest

from adapters.solidworks import sw_config_broker as broker


class TestE2EUserScenarios:
    """5 个用户视角端到端场景."""

    def test_e2e_first_install_sw_default_settings_prewarm_to_lookup_path(
        self, monkeypatch, tmp_path,
    ):
        """场景：首次装 SW + 跑 codegen 5 件 BOM。Prewarm 一次后 5 次 lookup 都 L1 hit."""
        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)
        from adapters.solidworks import sw_config_broker as broker
        from adapters.solidworks import sw_config_lists_cache as cache_mod
        from adapters.solidworks import sw_detect

        cache_path = tmp_path / "sw_config_lists.json"
        monkeypatch.setattr(cache_mod, "get_config_lists_cache_path", lambda: cache_path)

        fake_info = mock.MagicMock()
        fake_info.version_year = 24
        fake_info.toolbox_dir = "C:/SW"
        _fake_detect = lambda: fake_info
        monkeypatch.setattr(sw_detect, "detect_solidworks", _fake_detect)
        # M-6: broker 持有模块级绑定，必须同时 patch broker namespace
        monkeypatch.setattr(broker, "detect_solidworks", _fake_detect)

        sldprts = []
        for i in range(5):
            p = tmp_path / f"p{i}.sldprt"
            p.write_text("dummy")
            sldprts.append(str(p))

        worker_stdout = json.dumps([
            {"path": p, "configs": [f"cfg{i}"], "exit_code": 0}
            for i, p in enumerate(sldprts)
        ])
        call_count = {"n": 0}
        def fake_run(*a, **kw):
            call_count["n"] += 1
            return mock.MagicMock(returncode=0, stdout=worker_stdout.encode(), stderr=b"")
        monkeypatch.setattr("subprocess.run", fake_run)

        # 跑 prewarm 一次
        broker.prewarm_config_lists(sldprts)
        assert call_count["n"] == 1

        # 5 次 lookup 都 L1 hit
        for i, p in enumerate(sldprts):
            result = broker._list_configs_via_com(p)
            assert result == [f"cfg{i}"]
        assert call_count["n"] == 1, "L1 hit 不应 spawn worker"

    def test_e2e_upgrade_period_legacy_worker_skip_then_single_fallback(
        self, monkeypatch, tmp_path,
    ):
        """场景：升级期混跑（broker 新 / worker 旧）。batch 缺 exit_code → 跳过 + 单件 fallback."""
        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)
        from adapters.solidworks import sw_config_broker as broker
        from adapters.solidworks import sw_config_lists_cache as cache_mod
        from adapters.solidworks import sw_detect

        cache_path = tmp_path / "sw_config_lists.json"
        monkeypatch.setattr(cache_mod, "get_config_lists_cache_path", lambda: cache_path)

        fake_info = mock.MagicMock()
        fake_info.version_year = 24
        fake_info.toolbox_dir = "C:/SW"
        _fake_detect = lambda: fake_info
        monkeypatch.setattr(sw_detect, "detect_solidworks", _fake_detect)
        # M-6: broker 持有模块级绑定，必须同时 patch broker namespace
        monkeypatch.setattr(broker, "detect_solidworks", _fake_detect)

        p1 = tmp_path / "p1.sldprt"
        p1.write_text("dummy")

        # batch worker：旧格式（缺 exit_code）
        legacy_batch_stdout = json.dumps([{"path": str(p1), "configs": []}])
        single_call_count = {"n": 0}

        def fake_run(*a, **kw):
            cmd = a[0] if a else kw.get("args", [])
            if "--batch" in str(cmd):
                return mock.MagicMock(returncode=0, stdout=legacy_batch_stdout.encode(),
                                        stderr=b"")
            else:
                single_call_count["n"] += 1
                return mock.MagicMock(returncode=4, stdout="", stderr="")  # 旧 worker rc=4

        monkeypatch.setattr("subprocess.run", fake_run)

        broker.prewarm_config_lists([str(p1)])

        # 单件 fallback
        result = broker._list_configs_via_com(str(p1))
        assert result == []  # rc=4 当 transient
        assert single_call_count["n"] == 1

    def test_e2e_corrupt_cache_file_self_heals_and_rebuilds(
        self, monkeypatch, tmp_path,
    ):
        """场景：磁盘工具把 cache 写坏 → load self-heal → prewarm 重建."""
        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)
        from adapters.solidworks import sw_config_broker as broker
        from adapters.solidworks import sw_config_lists_cache as cache_mod
        from adapters.solidworks import sw_detect

        cache_path = tmp_path / "sw_config_lists.json"
        cache_path.write_text("INVALID_JSON_CONTENT", encoding="utf-8")
        monkeypatch.setattr(cache_mod, "get_config_lists_cache_path", lambda: cache_path)

        fake_info = mock.MagicMock()
        fake_info.version_year = 24
        fake_info.toolbox_dir = "C:/SW"
        _fake_detect = lambda: fake_info
        monkeypatch.setattr(sw_detect, "detect_solidworks", _fake_detect)
        # M-6: broker 持有模块级绑定，必须同时 patch broker namespace
        monkeypatch.setattr(broker, "detect_solidworks", _fake_detect)

        p1 = tmp_path / "p1.sldprt"
        p1.write_text("dummy")

        worker_stdout = json.dumps([{"path": str(p1), "configs": ["A"], "exit_code": 0}])
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: mock.MagicMock(returncode=0, stdout=worker_stdout.encode(),
                                              stderr=b""),
        )

        broker.prewarm_config_lists([str(p1)])

        # 重建后合法
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        assert data["schema_version"] == 1
        assert str(p1.resolve()) in data["entries"]

    def test_e2e_double_sw_concurrent_prewarm_last_writer_wins(
        self, monkeypatch, tmp_path,
    ):
        """场景：双进程 prewarm（last-writer-wins，known limitation §11.4）."""
        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)
        from adapters.solidworks import sw_config_broker as broker
        from adapters.solidworks import sw_config_lists_cache as cache_mod
        from adapters.solidworks import sw_detect

        cache_path = tmp_path / "sw_config_lists.json"
        monkeypatch.setattr(cache_mod, "get_config_lists_cache_path", lambda: cache_path)

        fake_info = mock.MagicMock()
        fake_info.version_year = 24
        fake_info.toolbox_dir = "C:/SW"
        _fake_detect = lambda: fake_info
        monkeypatch.setattr(sw_detect, "detect_solidworks", _fake_detect)
        # M-6: broker 持有模块级绑定，必须同时 patch broker namespace
        monkeypatch.setattr(broker, "detect_solidworks", _fake_detect)

        p1 = tmp_path / "p1.sldprt"
        p2 = tmp_path / "p2.sldprt"
        p1.write_text("dummy")
        p2.write_text("dummy")

        # process A: prewarm p1
        worker_stdout_A = json.dumps([{"path": str(p1), "configs": ["A"], "exit_code": 0}])
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: mock.MagicMock(returncode=0, stdout=worker_stdout_A.encode(),
                                              stderr=b""),
        )
        broker.prewarm_config_lists([str(p1)])

        # 清 in-process L2 模拟新 process
        broker._CONFIG_LIST_CACHE.clear()

        # process B: prewarm p2
        worker_stdout_B = json.dumps([{"path": str(p2), "configs": ["B"], "exit_code": 0}])
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: mock.MagicMock(returncode=0, stdout=worker_stdout_B.encode(),
                                              stderr=b""),
        )
        broker.prewarm_config_lists([str(p2)])

        # B 后 cache 应该 union（envelope 不变 → entries 合并）— 但实际 broker 实现是
        # _load → modify → save，所以 A 写的 entries 会被 B 读到合并
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        # 实际：last writer wins or merge — 测试此设计契约
        # 当前实现：B 跑时 _load_config_lists_cache 读到 A 写的 entries (含 p1)，
        # 然后 prewarm 加 p2 → save → 最终含 p1 + p2
        assert str(p2.resolve()) in data["entries"]
        # 注：spec §11.4 说"双进程互覆"是 known limitation；此 e2e 测试当前实际是 merge

    def test_e2e_large_bom_100_components_no_excessive_spawn_after_prewarm(
        self, monkeypatch, tmp_path,
    ):
        """场景：100 件大 BOM。Prewarm 一次后 100 次 lookup 都 L1 hit."""
        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)
        from adapters.solidworks import sw_config_broker as broker
        from adapters.solidworks import sw_config_lists_cache as cache_mod
        from adapters.solidworks import sw_detect

        cache_path = tmp_path / "sw_config_lists.json"
        monkeypatch.setattr(cache_mod, "get_config_lists_cache_path", lambda: cache_path)

        fake_info = mock.MagicMock()
        fake_info.version_year = 24
        fake_info.toolbox_dir = "C:/SW"
        _fake_detect = lambda: fake_info
        monkeypatch.setattr(sw_detect, "detect_solidworks", _fake_detect)
        # M-6: broker 持有模块级绑定，必须同时 patch broker namespace
        monkeypatch.setattr(broker, "detect_solidworks", _fake_detect)

        sldprts = []
        for i in range(100):
            p = tmp_path / f"p{i:03d}.sldprt"
            p.write_text("dummy")
            sldprts.append(str(p))

        worker_stdout = json.dumps([
            {"path": p, "configs": [f"c{i}"], "exit_code": 0}
            for i, p in enumerate(sldprts)
        ])
        call_count = {"n": 0}
        def fake_run(*a, **kw):
            call_count["n"] += 1
            return mock.MagicMock(returncode=0, stdout=worker_stdout.encode(), stderr=b"")
        monkeypatch.setattr("subprocess.run", fake_run)

        broker.prewarm_config_lists(sldprts)
        assert call_count["n"] == 1, "prewarm 一次"

        for i, p in enumerate(sldprts):
            result = broker._list_configs_via_com(p)
            assert result == [f"c{i}"]
        assert call_count["n"] == 1, "100 次 lookup 都 L1 hit 不 spawn"
