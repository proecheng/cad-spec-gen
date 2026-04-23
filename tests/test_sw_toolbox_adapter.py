"""SwToolboxAdapter 单元测试（v4 决策 #13/#22）。"""

from __future__ import annotations

import os
import sys
import unittest.mock as mock
import pytest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestIsAvailable:
    """v4 §5.3: 6 项检查全通过才 True。"""

    def test_non_windows_returns_false(self, monkeypatch):
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter

        monkeypatch.setattr(sys, "platform", "linux")
        a = SwToolboxAdapter()
        ok, _ = a.is_available()
        assert ok is False

    def test_sw_not_installed_returns_false(self, monkeypatch):
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_detect

        sw_detect._reset_cache()
        fake_info = sw_detect.SwInfo(installed=False)
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
        a = SwToolboxAdapter()
        ok, _ = a.is_available()
        assert ok is False

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
        ok, _ = a.is_available()
        assert ok is False

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
        ok, _ = a.is_available()
        assert ok is False

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
        ok, _ = a.is_available()
        assert ok is False

    def test_addin_disabled_no_longer_blocks(self, monkeypatch, tmp_path):
        """Track B 决策 B-2: Toolbox Add-In 未启用 → is_available 仍可返 True（advisory）。"""
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_detect, sw_com_session

        # 创建健康 toolbox_dir
        (tmp_path / "swbrowser.sldedb").write_bytes(b"SQLite")
        (tmp_path / "GB").mkdir()
        (tmp_path / "GB" / "p.sldprt").write_bytes(b"\x00")

        sw_detect._reset_cache()
        fake_info = sw_detect.SwInfo(
            installed=True,
            version_year=2024,
            pywin32_available=True,
            toolbox_dir=str(tmp_path),
            toolbox_addin_enabled=False,
            edition="professional",
        )
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)

        class FakeSession:
            def is_healthy(self): return True
        monkeypatch.setattr(sw_com_session, "get_session", lambda: FakeSession())

        ok, reason = SwToolboxAdapter().is_available()
        assert ok is True   # Add-in 硬门已解耦，未启用不再返 False

    def test_unhealthy_session_returns_false(self, monkeypatch, tmp_path):
        """v4 决策 #22: SwComSession 熔断 → False。"""
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_detect, sw_com_session

        # 创建健康 toolbox_dir，避免在路径健康检查处提前返回
        (tmp_path / "swbrowser.sldedb").write_bytes(b"SQLite")
        (tmp_path / "GB").mkdir()
        (tmp_path / "GB" / "p.sldprt").write_bytes(b"\x00")

        sw_detect._reset_cache()
        fake_info = sw_detect.SwInfo(
            installed=True,
            version_year=2024,
            pywin32_available=True,
            toolbox_dir=str(tmp_path),
            toolbox_addin_enabled=True,
            edition="professional",
        )
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
        sw_com_session.reset_session()
        sess = sw_com_session.get_session()
        sess._unhealthy = True
        a = SwToolboxAdapter()
        ok, _ = a.is_available()
        assert ok is False

    def test_all_checks_pass_returns_true(self, monkeypatch, tmp_path):
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_detect, sw_com_session

        # 创建健康 toolbox_dir，B-8 路径健康检查需要
        (tmp_path / "swbrowser.sldedb").write_bytes(b"SQLite")
        (tmp_path / "GB").mkdir()
        (tmp_path / "GB" / "p.sldprt").write_bytes(b"\x00")

        # is_available() 第一项检查是 sys.platform == "win32"；Linux CI runner 上
        # 必须先把平台改成 win32，后续 mock 才有意义（其余 TestIsAvailable 用例
        # 都期望 False，平台短路"碰巧 OK"，唯独这条期望 True 的必须 mock 平台）。
        monkeypatch.setattr(sys, "platform", "win32")
        sw_detect._reset_cache()
        sw_com_session.reset_session()
        fake_info = sw_detect.SwInfo(
            installed=True,
            version_year=2024,
            pywin32_available=True,
            toolbox_dir=str(tmp_path),
            toolbox_addin_enabled=True,
            edition="professional",
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
        a = SwToolboxAdapter()
        ok, _ = a.is_available()
        assert ok is True


class TestCanResolve:
    def test_can_resolve_always_true(self):
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter

        a = SwToolboxAdapter()

        class Q:
            pass

        assert a.can_resolve(Q()) is True


class TestInitValidatesSizePatterns:
    """I-2 回归: __init__ 必须调用 validate_size_patterns 挡下恶意 config（决策 #19）。"""

    def test_init_rejects_redos_pattern_in_config(self):
        """含 catastrophic backtracking 正则的 config 应在构造阶段被拒。"""
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter

        bad_config = {
            "size_patterns": {
                "fastener": {
                    "diameter": r"(a+)+$",  # 典型 ReDoS 模式
                }
            }
        }
        with pytest.raises(RuntimeError, match="ReDoS suspected"):
            SwToolboxAdapter(config=bad_config)

    def test_init_accepts_safe_patterns(self):
        """合法正则不应触发异常。"""
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter

        safe_config = {
            "size_patterns": {
                "fastener": {
                    "diameter": r"M(\d+(?:\.\d+)?)",
                    "length": r"x(\d+)",
                }
            }
        }
        a = SwToolboxAdapter(config=safe_config)
        assert a.config is safe_config

    def test_init_tolerates_empty_config(self):
        """空/缺失 size_patterns 不应触发校验异常。"""
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter

        SwToolboxAdapter()
        SwToolboxAdapter(config={})
        SwToolboxAdapter(config={"size_patterns": {}})


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
                "exclude_patterns": [r"UN[CFEF]", r"\bTr\d", r"\bG\d/", r"\bNPT"],
            },
            "bearing": {"model": r"\b(\d{4,5})\b"},
        },
    }


class TestFindSldprt:
    """v4 §5.3: find_sldprt() 不触发 COM；供 sw-warmup --bom 复用。"""

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
        result = a.find_sldprt(
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
        """find_sldprt 不应导入/调用 win32com。"""
        import sys

        # 破坏 win32com.client，证明 find_sldprt 不依赖它
        monkeypatch.setitem(sys.modules, "win32com.client", None)  # sabotage

        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter

        class Q:
            part_no = "GB/T 5782"
            name_cn = "M6×20 hex bolt 六角头"
            material = "钢"

        a = SwToolboxAdapter(config=_default_config())
        # 应该不 raise（证明没有 import win32com）
        result = a.find_sldprt(
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
