"""SwToolboxAdapter 单元测试（v4 决策 #13/#22）。"""

from __future__ import annotations

import sys
import unittest.mock as mock
import pytest
from pathlib import Path


class TestIsAvailable:
    """v4 §5.3: 6 项检查全通过才 True。"""

    def test_non_windows_returns_false(self, monkeypatch):
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter

        monkeypatch.setattr(sys, "platform", "linux")
        a = SwToolboxAdapter()
        assert a.is_available() is False

    def test_sw_not_installed_returns_false(self, monkeypatch):
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_detect

        sw_detect._reset_cache()
        fake_info = sw_detect.SwInfo(installed=False)
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
        a = SwToolboxAdapter()
        assert a.is_available() is False

    def test_version_below_2024_returns_false(self, monkeypatch):
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_detect

        sw_detect._reset_cache()
        fake_info = sw_detect.SwInfo(
            installed=True,
            version_year=2023,
            pywin32_available=True,
            toolbox_dir="C:/fake",
            toolbox_addin_enabled=True,
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
        a = SwToolboxAdapter()
        assert a.is_available() is False

    def test_pywin32_missing_returns_false(self, monkeypatch):
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_detect

        sw_detect._reset_cache()
        fake_info = sw_detect.SwInfo(
            installed=True,
            version_year=2024,
            pywin32_available=False,
            toolbox_dir="C:/fake",
            toolbox_addin_enabled=True,
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
        a = SwToolboxAdapter()
        assert a.is_available() is False

    def test_toolbox_dir_missing_returns_false(self, monkeypatch):
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_detect

        sw_detect._reset_cache()
        fake_info = sw_detect.SwInfo(
            installed=True,
            version_year=2024,
            pywin32_available=True,
            toolbox_dir="",
            toolbox_addin_enabled=True,
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
        a = SwToolboxAdapter()
        assert a.is_available() is False

    def test_addin_disabled_returns_false(self, monkeypatch):
        """v4 决策 #13: Toolbox Add-In 未启用 → False。"""
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_detect

        sw_detect._reset_cache()
        fake_info = sw_detect.SwInfo(
            installed=True,
            version_year=2024,
            pywin32_available=True,
            toolbox_dir="C:/fake",
            toolbox_addin_enabled=False,
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
        a = SwToolboxAdapter()
        assert a.is_available() is False

    def test_unhealthy_session_returns_false(self, monkeypatch, tmp_path):
        """v4 决策 #22: SwComSession 熔断 → False。"""
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_detect, sw_com_session

        sw_detect._reset_cache()
        fake_info = sw_detect.SwInfo(
            installed=True,
            version_year=2024,
            pywin32_available=True,
            toolbox_dir=str(tmp_path),
            toolbox_addin_enabled=True,
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
        sw_com_session.reset_session()
        sess = sw_com_session.get_session()
        sess._unhealthy = True
        a = SwToolboxAdapter()
        assert a.is_available() is False

    def test_all_checks_pass_returns_true(self, monkeypatch, tmp_path):
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_detect, sw_com_session

        sw_detect._reset_cache()
        sw_com_session.reset_session()
        fake_info = sw_detect.SwInfo(
            installed=True,
            version_year=2024,
            pywin32_available=True,
            toolbox_dir=str(tmp_path),
            toolbox_addin_enabled=True,
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
        a = SwToolboxAdapter()
        assert a.is_available() is True


class TestCanResolve:
    def test_can_resolve_always_true(self):
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter

        a = SwToolboxAdapter()

        class Q:
            pass

        assert a.can_resolve(Q()) is True


class TestResolve:
    """主编排流程（v4 §3.2）。"""

    @pytest.fixture
    def fake_toolbox(self):
        return Path(__file__).parent / "fixtures" / "fake_toolbox"

    @pytest.fixture
    def setup_sw_available(self, monkeypatch, fake_toolbox):
        """Mock sw_detect + SwComSession 以让 is_available 返回 True。"""
        from adapters.solidworks import sw_detect, sw_com_session

        sw_detect._reset_cache()
        sw_com_session.reset_session()
        fake_info = sw_detect.SwInfo(
            installed=True,
            version_year=2024,
            pywin32_available=True,
            toolbox_dir=str(fake_toolbox),
            toolbox_addin_enabled=True,
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)

    def test_resolve_size_extract_fail_returns_miss(self, setup_sw_available):
        """v4 决策 #9: 抽不到尺寸 → miss。"""
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter

        class Q:
            part_no = "XYZ"
            name_cn = "非标件"
            material = "铝"
            category = "fastener"

        a = SwToolboxAdapter(config=_default_config())
        result = a.resolve(
            Q(),
            {
                "standard": "GB",
                "subcategories": ["bolts and studs"],
                "part_category": "fastener",
            },
        )
        assert result.status == "miss"

    def test_resolve_low_score_returns_miss(self, setup_sw_available):
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter

        class Q:
            part_no = "Y"
            name_cn = "M99×999 奇怪螺钉"
            material = ""
            category = "fastener"

        a = SwToolboxAdapter(config=_default_config())
        # name_cn 里的 M99×999 能抽尺寸，但 token 与 hex bolt/stud 重叠极少
        result = a.resolve(
            Q(),
            {
                "standard": "GB",
                "subcategories": ["bolts and studs"],
                "part_category": "fastener",
            },
        )
        assert result.status == "miss"

    def test_resolve_unc_returns_miss(self, setup_sw_available):
        """v4 §1.3: UNC 范围外。"""
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter

        class Q:
            part_no = ""
            name_cn = "1/4-20 UNC hex bolt"
            material = "steel"
            category = "fastener"

        a = SwToolboxAdapter(config=_default_config())
        result = a.resolve(
            Q(),
            {
                "standard": "GB",
                "subcategories": ["bolts and studs"],
                "part_category": "fastener",
            },
        )
        assert result.status == "miss"

    def test_resolve_cache_hit_no_com(self, setup_sw_available, tmp_path, monkeypatch):
        """v4 §3.2 step 8: 缓存命中不触发 COM。"""
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_com_session, sw_toolbox_catalog

        # Put a fake STEP file in cache location
        monkeypatch.setenv("CAD_SPEC_GEN_SW_TOOLBOX_CACHE", str(tmp_path / "cache"))
        cache_root = sw_toolbox_catalog.get_toolbox_cache_root({})
        cache_root.mkdir(parents=True, exist_ok=True)
        step_file = cache_root / "GB" / "bolts and studs" / "hex bolt.step"
        step_file.parent.mkdir(parents=True, exist_ok=True)
        step_file.write_bytes(b"ISO-10303-214\n" + b"X" * 2000)

        # Mock SwComSession convert to ensure it's NOT called
        sess = sw_com_session.get_session()
        sess.convert_sldprt_to_step = mock.MagicMock()

        class Q:
            part_no = "GB/T 5782"
            name_cn = "GB/T 5782 M6×20 hex bolt 六角头螺栓"
            material = "钢"
            category = "fastener"

        a = SwToolboxAdapter(config=_default_config())
        result = a.resolve(
            Q(),
            {
                "standard": "GB",
                "subcategories": ["bolts and studs"],
                "part_category": "fastener",
            },
        )
        assert result.status == "hit"
        assert result.kind == "step_import"
        assert result.adapter == "sw_toolbox"
        assert result.source_tag.startswith("sw_toolbox:")
        # COM was NOT called (cache hit)
        sess.convert_sldprt_to_step.assert_not_called()


def _default_config() -> dict:
    return {
        "min_score": 0.15,  # hex bolt 查询实际得分约 0.16（见 v4 §3.2 注释）
        "token_weights": {
            "part_no": 2.0,
            "name_cn": 1.0,
            "material": 0.5,
            "size": 1.5,
        },
        "size_patterns": {
            "fastener": {
                "size": r"[Mm](\d+(?:\.\d+)?)",
                "length": r"[×xX*\-\s](\d+(?:\.\d+)?)",
                "exclude_patterns": [r"UN[CFEF]", r"\bTr\d", r"\bG\d/", r"\bNPT"],
            },
            "bearing": {"model": r"\b(\d{4,5})\b"},
        },
    }


class TestFindSldprt:
    """v4 §5.3: _find_sldprt() 不触发 COM；供 sw-warmup --bom 复用。"""

    @pytest.fixture
    def setup_sw(self, monkeypatch, tmp_path):
        from adapters.solidworks import sw_detect

        fake_toolbox = Path(__file__).parent / "fixtures" / "fake_toolbox"
        sw_detect._reset_cache()
        fake_info = sw_detect.SwInfo(
            installed=True,
            version_year=2024,
            pywin32_available=True,
            toolbox_dir=str(fake_toolbox),
            toolbox_addin_enabled=True,
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)

    def test_find_sldprt_returns_match(self, setup_sw):
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter

        class Q:
            part_no = "GB/T 5782"
            name_cn = "M6×20 hex bolt 六角头"
            material = "钢"

        a = SwToolboxAdapter(config=_default_config())
        result = a._find_sldprt(
            Q(),
            {
                "standard": "GB",
                "subcategories": ["bolts and studs"],
                "part_category": "fastener",
            },
        )
        assert result is not None
        part, score = result
        assert part.filename == "hex bolt.sldprt"

    def test_find_sldprt_no_com_imports(self, setup_sw, monkeypatch):
        """_find_sldprt 不应导入/调用 win32com。"""
        import sys

        # 破坏 win32com.client，证明 _find_sldprt 不依赖它
        monkeypatch.setitem(sys.modules, "win32com.client", None)  # sabotage

        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter

        class Q:
            part_no = "GB/T 5782"
            name_cn = "M6×20 hex bolt 六角头"
            material = "钢"

        a = SwToolboxAdapter(config=_default_config())
        # 应该不 raise（证明没有 import win32com）
        result = a._find_sldprt(
            Q(),
            {
                "standard": "GB",
                "subcategories": ["bolts and studs"],
                "part_category": "fastener",
            },
        )
        assert result is not None


class TestProbeDims:
    """v4 §1.3 已知限制: 缓存未命中 → None，不触发 COM。"""

    @pytest.fixture
    def setup(self, monkeypatch, tmp_path):
        from adapters.solidworks import sw_detect, sw_com_session

        sw_detect._reset_cache()
        sw_com_session.reset_session()
        fake_info = sw_detect.SwInfo(
            installed=True,
            version_year=2024,
            pywin32_available=True,
            toolbox_dir=str(tmp_path),
            toolbox_addin_enabled=True,
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)

    def test_probe_dims_cache_miss_returns_none(self, setup):
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter

        class Q:
            part_no = "X"
            name_cn = "M6×20 hex bolt"
            material = "钢"
            category = "fastener"

        a = SwToolboxAdapter(config=_default_config())
        result = a.probe_dims(
            Q(),
            {
                "standard": "GB",
                "subcategories": ["bolts and studs"],
                "part_category": "fastener",
            },
        )
        assert result is None
