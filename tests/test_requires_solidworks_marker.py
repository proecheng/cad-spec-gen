"""@requires_solidworks marker 自动 skip 钩子行为测试（Part 2c P1 T2）。

用 pytester fixture 内联跑 5 类情形：
  1. 无 marker 的用例照常跑（baseline）
  2. 有 marker 且当前环境满足（Windows + pywin32 + SW installed）→ 照常跑
  3. 非 Windows 平台 → skip，reason = "非 Windows 平台"
  4. Windows 但缺 pywin32 → skip，reason = "pywin32 缺"
  5. Windows + pywin32 但 SW 未装 → skip，reason = "SolidWorks 未安装"

通过 monkeypatch 切换 sys.platform 与 detect_solidworks 返回值模拟 5 种环境，
不依赖真 SolidWorks。
"""

from __future__ import annotations

import pytest

pytest_plugins = ["pytester"]


@pytest.fixture
def mock_sw_detect(monkeypatch):
    """返回一个工厂，让测试自选 SwInfo(installed, pywin32_available)。"""
    from adapters.solidworks import sw_detect

    def _set(installed: bool, pywin32_available: bool):
        sw_detect._reset_cache()
        fake = sw_detect.SwInfo(
            installed=installed, pywin32_available=pywin32_available
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake)

    return _set


@pytest.fixture
def pytester_with_hook(pytester):
    """给 pytester 内联会话注入与本仓库 tests/conftest.py 一致的钩子。

    pytester 创建独立 rootdir，不会继承父项目 conftest.py，因此必须显式
    makeconftest 把钩子源码写进内联 conftest.py。同时注册 marker，避免
    PytestUnknownMarkWarning。inprocess 模式下，本进程 monkeypatch 的
    sys.platform 与 sw_detect.detect_solidworks 仍对内联钩子可见。
    """
    pytester.makeconftest(
        """
        import sys
        import pytest

        def pytest_configure(config):
            config.addinivalue_line(
                "markers",
                "requires_solidworks: 需真实 SolidWorks + pywin32",
            )

        def pytest_collection_modifyitems(config, items):
            needs_sw = [
                it for it in items
                if it.get_closest_marker("requires_solidworks")
            ]
            if not needs_sw:
                return
            if sys.platform != "win32":
                reason = "requires_solidworks：非 Windows 平台"
            else:
                from adapters.solidworks.sw_detect import detect_solidworks
                info = detect_solidworks()
                if info.pywin32_available and info.installed:
                    return
                reason = "requires_solidworks：" + (
                    "pywin32 缺" if not info.pywin32_available
                    else "SolidWorks 未安装"
                )
            skip = pytest.mark.skip(reason=reason)
            for it in needs_sw:
                it.add_marker(skip)
        """
    )
    return pytester


class TestRequiresSolidworksMarker:
    """conftest.py 的 pytest_collection_modifyitems 钩子 5 类情形。"""

    def test_no_marker_runs_normally(
        self, pytester_with_hook, mock_sw_detect, monkeypatch
    ):
        """无 marker 的用例不受钩子影响。"""
        pytester = pytester_with_hook
        monkeypatch.setattr("sys.platform", "linux")
        mock_sw_detect(installed=False, pywin32_available=False)

        pytester.makepyfile(
            """
            def test_plain():
                assert 1 == 1
            """
        )
        result = pytester.runpytest("-v", "-rs")
        result.assert_outcomes(passed=1, skipped=0)

    def test_marker_satisfied_runs_normally(
        self, pytester_with_hook, mock_sw_detect, monkeypatch
    ):
        """有 marker + 环境满足（假装装了 SW）→ 照常跑。"""
        pytester = pytester_with_hook
        monkeypatch.setattr("sys.platform", "win32")
        mock_sw_detect(installed=True, pywin32_available=True)

        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.requires_solidworks
            def test_needs_sw():
                assert True
            """
        )
        result = pytester.runpytest("-v", "-rs")
        result.assert_outcomes(passed=1, skipped=0)

    def test_marker_non_windows_skipped(
        self, pytester_with_hook, mock_sw_detect, monkeypatch
    ):
        """非 Windows 平台 → skip，reason 精确匹配。"""
        pytester = pytester_with_hook
        monkeypatch.setattr("sys.platform", "linux")
        mock_sw_detect(installed=False, pywin32_available=False)

        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.requires_solidworks
            def test_needs_sw():
                assert True
            """
        )
        result = pytester.runpytest("-v", "-rs")
        result.assert_outcomes(passed=0, skipped=1)
        result.stdout.fnmatch_lines(["*非 Windows 平台*"])

    def test_marker_missing_pywin32_skipped(
        self, pytester_with_hook, mock_sw_detect, monkeypatch
    ):
        """Windows 但缺 pywin32 → skip，reason = pywin32 缺。"""
        pytester = pytester_with_hook
        monkeypatch.setattr("sys.platform", "win32")
        mock_sw_detect(installed=True, pywin32_available=False)

        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.requires_solidworks
            def test_needs_sw():
                assert True
            """
        )
        result = pytester.runpytest("-v", "-rs")
        result.assert_outcomes(passed=0, skipped=1)
        result.stdout.fnmatch_lines(["*pywin32 缺*"])

    def test_marker_sw_not_installed_skipped(
        self, pytester_with_hook, mock_sw_detect, monkeypatch
    ):
        """Windows + pywin32 但 SW 未装 → skip，reason = SolidWorks 未安装。"""
        pytester = pytester_with_hook
        monkeypatch.setattr("sys.platform", "win32")
        mock_sw_detect(installed=False, pywin32_available=True)

        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.requires_solidworks
            def test_needs_sw():
                assert True
            """
        )
        result = pytester.runpytest("-v", "-rs")
        result.assert_outcomes(passed=0, skipped=1)
        result.stdout.fnmatch_lines(["*SolidWorks 未安装*"])
