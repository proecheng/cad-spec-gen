"""SW Toolbox 端到端 mocked 集成测试（spec §9.3）。

验证 BOM CSV → PartsResolver → SwToolboxAdapter → mocked SwComSession
全链路在不调真实 COM 的情况下能产生预期 STEP 缓存命中。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DEMO_BOM = Path(__file__).parent / "fixtures" / "sw_warmup_demo_bom.csv"
FAKE_TOOLBOX = Path(__file__).parent / "fixtures" / "fake_toolbox"


@pytest.fixture
def sw_available(monkeypatch, tmp_path):
    """Mock 让 SwToolboxAdapter.is_available() = True 且 cache 在 tmp_path。"""
    from adapters.solidworks import sw_com_session, sw_detect, sw_toolbox_catalog

    # 非 Windows CI 下 is_available 首关 sys.platform != 'win32' 会直接 False
    monkeypatch.setattr(sys, "platform", "win32")

    sw_detect._reset_cache()
    reset_fn = getattr(sw_com_session, "reset_session", None)
    if callable(reset_fn):
        reset_fn()

    fake_info = sw_detect.SwInfo(
        installed=True,
        version_year=2024,
        pywin32_available=True,
        toolbox_dir=str(FAKE_TOOLBOX),
        toolbox_addin_enabled=True,
    )
    monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
    monkeypatch.setattr(
        sw_toolbox_catalog,
        "get_toolbox_cache_root",
        lambda config: tmp_path / "cache",
    )
    monkeypatch.setattr(
        sw_toolbox_catalog,
        "get_toolbox_index_path",
        lambda config: tmp_path / "idx.json",
    )

    def fake_convert(self, sldprt_path, step_out, target_config=None):
        Path(step_out).parent.mkdir(parents=True, exist_ok=True)
        Path(step_out).write_bytes(b"ISO-10303-21 fake" + b"\x00" * 2000)
        return True

    monkeypatch.setattr(
        sw_com_session.SwComSession, "convert_sldprt_to_step", fake_convert
    )
    return tmp_path


def test_bom_resolves_with_mocked_com(sw_available):
    """加载 demo_bom.csv → 经 PartsResolver → 至少 1 行命中 sw_toolbox。

    fake_toolbox 只含少数 GB sldprt 且命名语言受限，这里测试环境放宽 min_score
    到 0.05（生产默认 0.30）以让中文 BOM 和英/中 fake 部件能产生至少 1 次命中，
    证端到端链路（BOM → resolver → SW adapter → mocked COM → cache 写入）打通。
    """
    from parts_resolver import default_resolver
    from tools.sw_warmup import read_bom_csv

    queries = read_bom_csv(DEMO_BOM)
    assert len(queries) == 15

    resolver = default_resolver(project_root=str(sw_available))
    # 放宽阈值：fake fixture token 稀疏，仅为验证链路
    sw_adapter = next((a for a in resolver.adapters if a.name == "sw_toolbox"), None)
    assert sw_adapter is not None, "SwToolboxAdapter 未注册"
    sw_adapter.config["min_score"] = 0.05

    sw_hits = 0
    for q in queries:
        result = resolver.resolve(q)
        if result.adapter == "sw_toolbox" and result.status == "hit":
            sw_hits += 1

    assert sw_hits >= 1, "至少 1 行应命中 sw_toolbox（fake_toolbox 几何有限）"


def test_coverage_regression_baseline(monkeypatch, tmp_path):
    """同一 BOM 跑两次：有 SW 时 sw_toolbox ≥ 1 命中，jinja 不增加。

    会计关系：有 SW 的 sw_hits 来源是 jinja/其他 adapter 迁移量，因此
    jinja_no_sw - jinja_with_sw ≤ sw_with_sw（允许部分 sw_hits 来自 miss
    行变 hit，而非纯 jinja 迁移）。
    """
    from adapters.solidworks import sw_com_session, sw_detect, sw_toolbox_catalog
    from parts_resolver import default_resolver
    from tools.sw_warmup import read_bom_csv

    queries = read_bom_csv(DEMO_BOM)

    # ─── pass 1: 无 SW ───
    sw_detect._reset_cache()
    monkeypatch.setattr(
        sw_detect,
        "detect_solidworks",
        lambda: sw_detect.SwInfo(installed=False),
    )
    resolver1 = default_resolver(project_root=str(tmp_path))
    counts_no_sw: dict[str, int] = {}
    for q in queries:
        r = resolver1.resolve(q)
        counts_no_sw[r.adapter] = counts_no_sw.get(r.adapter, 0) + 1

    sw_no_sw = counts_no_sw.get("sw_toolbox", 0)
    jinja_no_sw = counts_no_sw.get("jinja_primitive", 0)
    assert sw_no_sw == 0, "无 SW 时 sw_toolbox 不应命中"

    # ─── pass 2: 有 SW（mock）───
    monkeypatch.setattr(sys, "platform", "win32")
    sw_detect._reset_cache()
    reset_fn = getattr(sw_com_session, "reset_session", None)
    if callable(reset_fn):
        reset_fn()

    fake_info = sw_detect.SwInfo(
        installed=True,
        version_year=2024,
        pywin32_available=True,
        toolbox_dir=str(FAKE_TOOLBOX),
        toolbox_addin_enabled=True,
    )
    monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
    monkeypatch.setattr(
        sw_toolbox_catalog,
        "get_toolbox_cache_root",
        lambda config: tmp_path / "cache",
    )
    monkeypatch.setattr(
        sw_toolbox_catalog,
        "get_toolbox_index_path",
        lambda config: tmp_path / "idx.json",
    )

    def fake_convert(self, sldprt_path, step_out, target_config=None):
        Path(step_out).parent.mkdir(parents=True, exist_ok=True)
        Path(step_out).write_bytes(b"ISO-10303-21 fake" + b"\x00" * 2000)
        return True

    monkeypatch.setattr(
        sw_com_session.SwComSession, "convert_sldprt_to_step", fake_convert
    )

    resolver2 = default_resolver(project_root=str(tmp_path))
    sw_adapter = next((a for a in resolver2.adapters if a.name == "sw_toolbox"), None)
    assert sw_adapter is not None
    sw_adapter.config["min_score"] = 0.05  # 与 test_bom_resolves_with_mocked_com 一致

    counts_with_sw: dict[str, int] = {}
    for q in queries:
        r = resolver2.resolve(q)
        counts_with_sw[r.adapter] = counts_with_sw.get(r.adapter, 0) + 1

    sw_with_sw = counts_with_sw.get("sw_toolbox", 0)
    jinja_with_sw = counts_with_sw.get("jinja_primitive", 0)

    assert sw_with_sw >= 1, f"有 SW 时 sw_toolbox 应至少命中 1 行（实际 {sw_with_sw}）"
    assert jinja_with_sw <= jinja_no_sw, (
        f"jinja 命中数不应增加（{jinja_no_sw} → {jinja_with_sw}）"
    )
    assert (jinja_no_sw - jinja_with_sw) <= sw_with_sw, (
        f"迁移会计不平衡: jinja 减少 {jinja_no_sw - jinja_with_sw} vs "
        f"sw 命中 {sw_with_sw}"
    )
