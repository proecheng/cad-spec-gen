"""pyproject.toml 字段契约测试（Part 2c P2 决策 #37）。

保护 `[project.optional-dependencies]` 等字段契约不被意外破坏。
未来若新增其他 extras，同文件扩展 TestXxxExtra 类。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# tomllib 仅 Python 3.11+；3.10 的 CI job 跳过
# 3.11/3.12 × Windows/Ubuntu = 4 个 job 覆盖 pyproject 解析级 regression 足够
pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="tomllib 仅 Python 3.11+ 可用；3.10 job 由 3.11/3.12 的 4 个 job 兜底",
)

# 强制 importorskip 而非假设"packaging 通常已在"——本项目 uv 环境已知有
# partcad vs bd-warehouse 依赖冲突风险，健壮性优先
pytest.importorskip("packaging")

# importorskip 必须在 import 之前执行；E402 是预期的
from packaging.requirements import Requirement  # noqa: E402

PYPROJECT_PATH = Path(__file__).resolve().parents[1] / "pyproject.toml"


def _load_pyproject_optional_deps() -> dict[str, list[str]]:
    """解析 pyproject.toml 返回 optional-dependencies 段。"""
    import tomllib

    with PYPROJECT_PATH.open("rb") as f:
        data = tomllib.load(f)
    return data.get("project", {}).get("optional-dependencies", {})


class TestSolidworksExtra:
    """决策 #37：pyproject.toml 新增 solidworks optional extra。"""

    def test_solidworks_extra_has_pywin32_with_windows_marker(self):
        deps = _load_pyproject_optional_deps()
        assert "solidworks" in deps, "必须有 solidworks extra（决策 #37）"

        reqs = [Requirement(s) for s in deps["solidworks"]]
        pywin32 = next((r for r in reqs if r.name == "pywin32"), None)
        assert pywin32 is not None, "solidworks extra 必须含 pywin32"

        # specifier 语义断言：显式检查 operator + version
        # 不用 .contains("306")——它对 ==306（锁死版本）和 >=306（下限）
        # 都返回 True，但两者语义完全不同，必须区分
        specs = list(pywin32.specifier)
        # SpecifierSet 底层是 frozenset，多个 specifier 时迭代顺序不保证；
        # 强制 len==1 确保 specs[0] 可安全访问，如需支持上界需重写断言逻辑
        assert len(specs) == 1, "pywin32 应只有一个 specifier"
        assert specs[0].operator == ">=", (
            f"operator 必须是 >=（下限），实际: {specs[0].operator}"
        )
        assert specs[0].version == "306"

        # marker 语义断言：PEP 508 marker 解析后语义 == win32-only
        assert pywin32.marker is not None, "pywin32 必须有 sys_platform marker"
        # 规范 marker variable 必须用 sys_platform（而非语义等价的 os_name == "nt"）。
        # Marker.evaluate() 的 environment 仅覆盖对应 key，其他 key 走系统真实值，
        # 如果改成 os_name 语义等价形式，evaluate 断言在 Windows CI 上会误判
        assert str(pywin32.marker) == 'sys_platform == "win32"', (
            f"marker 必须使用 sys_platform 变量（决策 #37），实际: {pywin32.marker}"
        )
        assert pywin32.marker.evaluate({"sys_platform": "win32"}) is True
        assert pywin32.marker.evaluate({"sys_platform": "linux"}) is False
        assert pywin32.marker.evaluate({"sys_platform": "darwin"}) is False

    def test_all_extra_does_not_contain_pywin32(self):
        """D1 决策：`all` extra 不含 pywin32（保持 all 全平台可装）。"""
        deps = _load_pyproject_optional_deps()
        reqs = [Requirement(s) for s in deps.get("all", [])]
        assert all(r.name != "pywin32" for r in reqs), (
            "all extra 不应含 pywin32（D1 决策：避免 marker 污染扩散)"
        )


class TestSwInspectNoNewExtras:
    """F-1 sw-inspect 引入时，确保不新增任何 extras（决策 #37 范围保持）。"""

    def test_no_new_optional_dependencies_group(self):
        import tomllib
        from pathlib import Path

        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        extras = set(data["project"].get("optional-dependencies", {}).keys())
        # allowed 来自 Step 1 实际探查结果（2026-04-16，Task 16）
        allowed = {
            "cad",
            "render",
            "parts_library",
            "parts_library_bd",
            "parts_library_pc",
            "solidworks",
            "all",
        }
        # 断言语义：extras 集合没有扩大（超出预期范围的新 extras 须明确更新此测试）
        unexpected = extras - allowed
        assert unexpected == set(), f"意外新增 extras: {unexpected}"

    def test_sw_inspect_imports_without_solidworks_extra(self):
        """sw-inspect 模块应在不装 [solidworks] 时仍可 import（--deep 会 fail 而非崩溃）。"""
        import importlib
        import tools.sw_inspect as m

        importlib.reload(m)
        assert hasattr(m, "run_sw_inspect")
