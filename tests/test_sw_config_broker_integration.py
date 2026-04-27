"""adapters/solidworks/sw_config_broker.py 集成测试（rev 5 C 新增）.

模式：mock 仅 subprocess.run（控制 worker stdout / rc / stderr / TimeoutExpired），
其余 broker / cache_mod / sw_config_lists_cache 代码全走真实路径。
用 tmp_path fixture 隔离 cache file。

spec 引用: docs/superpowers/specs/2026-04-27-sw-config-broker-m2-m4-cleanup-design.md §7.4
"""

from __future__ import annotations

import json
import sys
import unittest.mock as mock
from pathlib import Path

import pytest


@pytest.fixture
def isolated_cache(monkeypatch, tmp_path):
    """隔离 cache file 到 tmp_path（防污染 ~/.cad-spec-gen/）."""
    from adapters.solidworks import sw_config_lists_cache as cache_mod

    cache_path = tmp_path / "sw_config_lists.json"
    monkeypatch.setattr(cache_mod, "get_config_lists_cache_path", lambda: cache_path)
    yield cache_path


@pytest.fixture
def mock_sw_detect(monkeypatch):
    """mock detect_solidworks 返合法 SwInfo（防 envelope_invalidated 触发）."""
    from adapters.solidworks import sw_detect
    from adapters.solidworks import sw_config_broker as broker

    fake_info = mock.MagicMock()
    fake_info.version_year = 24
    fake_info.toolbox_dir = "C:\\SOLIDWORKS Data\\Toolbox"
    _fake_detect = lambda: fake_info
    monkeypatch.setattr(sw_detect, "detect_solidworks", _fake_detect)
    # M-6: broker 持有模块级绑定，必须同时 patch broker namespace
    monkeypatch.setattr(broker, "detect_solidworks", _fake_detect)
    yield fake_info


class TestIntegrationBrokerToCacheChain:
    """broker → worker → cache 真实调用链；mock 仅 subprocess.run."""

    def test_integration_prewarm_to_l1_cache_to_save_full_chain_rc0(
        self, monkeypatch, tmp_path, isolated_cache, mock_sw_detect,
    ):
        """spec §7.4：rc=0 整链落盘 → 读 file 验证 entries + envelope."""
        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)
        from adapters.solidworks import sw_config_broker as broker

        p1 = tmp_path / "p1.sldprt"
        p2 = tmp_path / "p2.sldprt"
        p1.write_text("dummy")
        p2.write_text("dummy")

        worker_stdout = json.dumps([
            {"path": str(p1), "configs": ["A", "B"], "exit_code": 0},
            {"path": str(p2), "configs": ["X"], "exit_code": 0},
        ])
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: mock.MagicMock(returncode=0, stdout=worker_stdout.encode(),
                                              stderr=b""),
        )

        broker.prewarm_config_lists([str(p1), str(p2)])

        # 读真实 cache file 验证
        assert isolated_cache.exists()
        data = json.loads(isolated_cache.read_text(encoding="utf-8"))
        assert data["schema_version"] == 1
        assert str(p1.resolve()) in data["entries"]
        assert data["entries"][str(p1.resolve())]["configs"] == ["A", "B"]
        assert data["entries"][str(p2.resolve())]["configs"] == ["X"]

    def test_integration_prewarm_terminal_persists_empty_to_l1_cache_rc2(
        self, monkeypatch, tmp_path, isolated_cache, mock_sw_detect,
    ):
        """spec §7.4 / I5：rc=2 entry 写 entries[key]['configs']=[] 防重试."""
        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)
        from adapters.solidworks import sw_config_broker as broker

        p1 = tmp_path / "p1.sldprt"
        p1.write_text("dummy")

        worker_stdout = json.dumps([
            {"path": str(p1), "configs": [], "exit_code": 2},
        ])
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: mock.MagicMock(returncode=0, stdout=worker_stdout.encode(),
                                              stderr=b""),
        )

        broker.prewarm_config_lists([str(p1)])

        data = json.loads(isolated_cache.read_text(encoding="utf-8"))
        key = str(p1.resolve())
        assert key in data["entries"]
        assert data["entries"][key]["configs"] == []  # terminal mark

    def test_integration_prewarm_transient_does_not_persist_rc3(
        self, monkeypatch, tmp_path, isolated_cache, mock_sw_detect,
    ):
        """spec §7.4 / I4：rc=3 entry 跳过不写 entries（L1 不被 transient 污染）."""
        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)
        from adapters.solidworks import sw_config_broker as broker

        p1 = tmp_path / "p1.sldprt"
        p1.write_text("dummy")

        worker_stdout = json.dumps([
            {"path": str(p1), "configs": [], "exit_code": 3},
        ])
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: mock.MagicMock(returncode=0, stdout=worker_stdout.encode(),
                                              stderr=b""),
        )

        broker.prewarm_config_lists([str(p1)])

        if isolated_cache.exists():
            data = json.loads(isolated_cache.read_text(encoding="utf-8"))
            assert str(p1.resolve()) not in data["entries"]

    def test_integration_prewarm_legacy_no_exit_code_skipped_to_save(
        self, monkeypatch, tmp_path, isolated_cache, mock_sw_detect, caplog,
    ):
        """spec §7.4 + rev 3 C2：旧 worker batch 缺 exit_code → 跳过不写 + log.warning."""
        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)
        from adapters.solidworks import sw_config_broker as broker

        p1 = tmp_path / "p1.sldprt"
        p1.write_text("dummy")

        worker_stdout = json.dumps([
            {"path": str(p1), "configs": []},  # 缺 exit_code（旧 worker schema）
        ])
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: mock.MagicMock(returncode=0, stdout=worker_stdout.encode(),
                                              stderr=b""),
        )

        with caplog.at_level("WARNING"):
            broker.prewarm_config_lists([str(p1)])

        assert any("缺 exit_code 字段" in r.message for r in caplog.records)
        if isolated_cache.exists():
            data = json.loads(isolated_cache.read_text(encoding="utf-8"))
            assert str(p1.resolve()) not in data["entries"]

    def test_integration_save_failure_does_not_break_subsequent_calls(
        self, monkeypatch, tmp_path, mock_sw_detect, capsys,
    ):
        """spec §7.4 / I1：save 失败 banner 出 stderr + 不抛 + 后续调用 OK.

        Task 19 修 plan-drift #1（plan 原代码 setup 顺序错 + mock 不区分 batch/single）：
        1. 先建 sldprt（无 patch 干扰）；2. selective Path.write_text 只拦 cache 路径；
        3. smart subprocess mock 区分 --batch（list of dict）与 single（list of str）。
        """
        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)
        from adapters.solidworks import sw_config_broker as broker
        from adapters.solidworks import sw_config_lists_cache as cache_mod

        # 1. 先创 sldprt（无 patch 干扰）
        p1 = tmp_path / "p1.sldprt"
        p1.write_text("dummy")

        # 2. monkeypatch cache 路径 → tmp_path 隔离
        monkeypatch.setattr(
            cache_mod, "get_config_lists_cache_path",
            lambda: tmp_path / "sw_config_lists.json",
        )

        # 3. selective Path.write_text — 只对 cache 文件抛 PermissionError
        from pathlib import Path
        original_write_text = Path.write_text
        def fake_write_text_selective(self, *args, **kwargs):
            if "sw_config_lists" in str(self):
                raise PermissionError("simulated lock")
            return original_write_text(self, *args, **kwargs)
        monkeypatch.setattr(Path, "write_text", fake_write_text_selective)

        # 4. smart subprocess.run mock：batch 返 list of dict / single 返 list of str
        worker_batch_stdout = json.dumps(
            [{"path": str(p1), "configs": ["A"], "exit_code": 0}],
        ).encode()
        worker_single_stdout = json.dumps(["A"]).encode()
        def smart_run(cmd, *a, **kw):
            stdout = worker_batch_stdout if "--batch" in cmd else worker_single_stdout
            return mock.MagicMock(returncode=0, stdout=stdout, stderr=b"")
        monkeypatch.setattr("subprocess.run", smart_run)

        # 5. 第 1 次 prewarm：cache save 抛 PermissionError → banner 出 + 不抛
        broker.prewarm_config_lists([str(p1)])
        err = capsys.readouterr().err
        assert "⚠ cache 文件" in err

        # 6. 第 2 次：_list_configs_via_com 不抛 + 返合法 list（spec I1 fire-and-forget）
        # 注：save 失败让 L1 没落盘 → fallback 走 single worker → 返 ["A"]
        result = broker._list_configs_via_com(str(p1))
        assert result == ["A"]  # L2 hit

    def test_integration_l1_cache_load_corrupt_self_heals_then_prewarm_rebuilds(
        self, monkeypatch, tmp_path, isolated_cache, mock_sw_detect,
    ):
        """spec §7.4：cache file 写非法 JSON → _load self-heal 返空 envelope → prewarm 重建."""
        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)
        from adapters.solidworks import sw_config_broker as broker

        # 预写非法 JSON
        isolated_cache.write_text("INVALID JSON {{{", encoding="utf-8")

        p1 = tmp_path / "p1.sldprt"
        p1.write_text("dummy")
        worker_stdout = json.dumps([{"path": str(p1), "configs": ["A"], "exit_code": 0}])
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: mock.MagicMock(returncode=0, stdout=worker_stdout.encode(),
                                              stderr=b""),
        )

        broker.prewarm_config_lists([str(p1)])

        # 读后 cache 已重建合法
        data = json.loads(isolated_cache.read_text(encoding="utf-8"))
        assert data["schema_version"] == 1
        assert str(p1.resolve()) in data["entries"]

    def test_integration_envelope_invalidated_clears_entries_and_rewrites_envelope(
        self, monkeypatch, tmp_path, isolated_cache,
    ):
        """spec §7.4：旧 sw_version envelope → mock 返新 sw_version → 整 entries 清重列."""
        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)
        from adapters.solidworks import sw_config_broker as broker
        from adapters.solidworks import sw_detect

        # 预填 cache 旧 envelope + entries
        isolated_cache.write_text(json.dumps({
            "schema_version": 1,
            "generated_at": "x",
            "sw_version": 23,  # 旧版本
            "toolbox_path": "C:/old",
            "entries": {"C:/p_old.sldprt": {"mtime": 100, "size": 200, "configs": ["X"]}},
        }), encoding="utf-8")

        # mock 返新 sw_version
        from adapters.solidworks import sw_config_broker as broker
        fake_info = mock.MagicMock()
        fake_info.version_year = 24  # 新版本
        fake_info.toolbox_dir = "C:/new"
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

        # 读后 envelope 已升 + 旧 entries 清
        data = json.loads(isolated_cache.read_text(encoding="utf-8"))
        assert data["sw_version"] == 24
        assert data["toolbox_path"] == "C:/new"
        assert "C:/p_old.sldprt" not in data["entries"]  # 旧 entries 清
        assert str(p1.resolve()) in data["entries"]

    @pytest.mark.skipif(
        sys.platform != "win32",
        reason="forward/back slash 一致性是 Windows-specific 问题（Linux 上 \\ 在路径中无意义）",
    )
    def test_integration_normalize_sldprt_key_consistency_forward_vs_back_slash(
        self, monkeypatch, tmp_path, isolated_cache, mock_sw_detect,
    ):
        """spec §7.4：forward-slash 写入 + back-slash 读 → 同 key (Path.resolve)."""
        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)
        from adapters.solidworks import sw_config_broker as broker

        p1 = tmp_path / "p1.sldprt"
        p1.write_text("dummy")
        forward = str(p1).replace("\\", "/")
        back = str(p1).replace("/", "\\")

        worker_stdout = json.dumps([{"path": forward, "configs": ["A"], "exit_code": 0}])
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: mock.MagicMock(returncode=0, stdout=worker_stdout.encode(),
                                              stderr=b""),
        )

        broker.prewarm_config_lists([forward])

        # 用 backslash 读，应该 L1 hit
        result = broker._list_configs_via_com(back)
        assert result == ["A"]  # L2 hit
