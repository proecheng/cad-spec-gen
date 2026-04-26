# tests/conftest.py
"""Pytest configuration for cad-spec-gen tests.

This conftest installs an autouse fixture that redirects ~/.cad-spec-gen/
to a per-test tmp_path, with a hash-based tripwire that fails loudly if
any test bypasses the redirect and modifies the real user home.

Why a hash instead of mtime: NTFS/FAT have ~1-second mtime resolution,
so two tests finishing in the same second can race an mtime check.
A hash over (rel_path, size, mtime) tuples for every file catches any
content mutation regardless of timestamp resolution.
"""

import hashlib
import importlib
import sys
from pathlib import Path

import pytest

# Ensure src/ is on sys.path BEFORE pytest collects tests, to avoid
# shadowing from top-level cad_spec_gen.py script.
# Root is appended (low priority) so root-level modules like bom_parser are
# importable at module scope while src/ stays at position 0 (highest priority).
_ROOT = Path(__file__).parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(_ROOT) not in sys.path:
    sys.path.append(str(_ROOT))


def _dir_state_hash(path: Path) -> str | None:
    """Return a stable hash of a directory's contents, or None if missing."""
    if not path.exists():
        return None
    parts = []
    for p in sorted(path.rglob("*")):
        if p.is_file():
            try:
                st = p.stat()
            except OSError:
                continue
            rel = p.relative_to(path).as_posix()
            parts.append(f"{rel}|{st.st_size}|{st.st_mtime_ns}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


# Captured ONCE at conftest import time (before any test runs).
_REAL_HOME_CAD_DIR = Path.home() / ".cad-spec-gen"
_REAL_HOME_HASH_AT_START = _dir_state_hash(_REAL_HOME_CAD_DIR)


@pytest.fixture(autouse=True, scope="function")
def isolate_cad_spec_gen_home(monkeypatch, tmp_path):
    """Redirect ~/.cad-spec-gen to tmp_path for every test.

    Tripwire (teardown): fail loudly if real user home's .cad-spec-gen
    directory state changed during the test.
    """
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir(parents=True)
    (fake_home / ".cad-spec-gen").mkdir()
    monkeypatch.setenv("CAD_SPEC_GEN_HOME", str(fake_home / ".cad-spec-gen"))
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))  # Windows
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    yield

    current_hash = _dir_state_hash(_REAL_HOME_CAD_DIR)
    assert current_hash == _REAL_HOME_HASH_AT_START, (
        f"Real {_REAL_HOME_CAD_DIR} was modified during test.\n"
        f"  Before: {_REAL_HOME_HASH_AT_START}\n"
        f"  After:  {current_hash}\n"
        f"A code path bypassed the HOME monkeypatch — fixture breach!"
    )


# ─── @requires_solidworks marker 自动 skip 钩子（Part 2c P1 T2） ───


def pytest_collection_modifyitems(config, items):
    """为 @pytest.mark.requires_solidworks 的 item 按需加 skip 标记。

    触发 skip 条件（任一满足，优先级从高到低）：
      1. sys.platform != "win32"（COM 是 Windows 独占）
      2. pywin32 (import win32com) 不可用
      3. adapters.solidworks.sw_detect.detect_solidworks().installed == False

    2 和 3 由运行时唯一事实源 sw_detect 统一回答（非 Windows 平台上
    detect_solidworks() 也返回 installed=False, pywin32_available=False，
    但显式检查 sys.platform 让 skip reason 更精确）。
    异常不吞：sw_detect 导入失败 → collection 失败，不 silent skip。
    """
    needs_sw = [it for it in items if it.get_closest_marker("requires_solidworks")]
    if not needs_sw:
        return

    if sys.platform != "win32":
        reason = "requires_solidworks：非 Windows 平台"
    else:
        try:
            from adapters.solidworks.sw_detect import detect_solidworks

            info = detect_solidworks()
        except ImportError as exc:
            raise pytest.UsageError(f"sw_detect 导入失败：{exc}") from exc

        if info.pywin32_available and info.installed:
            return  # 真装了 SW，保留原样跑
        reason = "requires_solidworks：" + (
            "pywin32 缺" if not info.pywin32_available else "SolidWorks 未安装"
        )

    skip = pytest.mark.skip(reason=reason)
    for it in needs_sw:
        it.add_marker(skip)


# ─── Task 32: sw_preflight mock fixtures ───


@pytest.fixture
def mock_sw_registry_versions():
    """注入虚假注册表多版本数据（测试三档版本优先级时用）"""
    from unittest.mock import patch

    def _inject(years: list[int]):
        return patch(
            "adapters.solidworks.sw_detect._enumerate_registered_years",
            return_value=years,
        )

    return _inject


@pytest.fixture
def mock_filedialog():
    """mock tkinter.filedialog.askopenfilename（避免真弹窗卡测试）"""
    from unittest.mock import patch

    with patch("sw_preflight.io.filedialog") as m:
        yield m


@pytest.fixture
def mock_admin():
    """mock is_user_admin 返回值（测 admin 退化路径时用）"""
    from unittest.mock import patch

    def _set(is_admin: bool):
        return patch("sw_preflight.matrix.is_user_admin", return_value=is_admin)

    return _set


@pytest.fixture
def mock_provenance(tmp_path):
    """快速构造 provenance 测试源文件 fixture"""

    def _make(content: bytes = b"ISO-10303\n" + b"\n" * 20000):
        src = tmp_path / "src.step"
        src.write_bytes(content)
        return src

    return _make


# ─── /Task 32 ───


# ─── Task 8 (sw_config_broker plan)：tmp_project_dir fixture ───


@pytest.fixture
def tmp_project_dir(tmp_path, monkeypatch):
    """为 broker 测试提供独立项目目录。

    - 在 tmp_path 下建 .cad-spec-gen/ 子目录（broker decisions/pending 文件存放处）
    - 设 CAD_PROJECT_ROOT env 指向 tmp_path
    - reload cad_paths 让模块级常量 PROJECT_ROOT 重新读取 env

    yields: tmp_path (Path) — 项目根

    与 isolate_cad_spec_gen_home autouse fixture 正交：
      - isolate_cad_spec_gen_home 隔离的是 **用户 home** (~/.cad-spec-gen/)
      - tmp_project_dir 隔离的是 **项目根** (<project>/.cad-spec-gen/)
      - broker 的 decisions/pending 文件写后者；前者管的是用户级 cache/config
    """
    cad_dir = tmp_path / ".cad-spec-gen"
    cad_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("CAD_PROJECT_ROOT", str(tmp_path))

    if "cad_paths" in sys.modules:
        importlib.reload(sys.modules["cad_paths"])

    yield tmp_path

    # teardown：再 reload 一次让 PROJECT_ROOT 回到默认 cwd，避免污染下一个测试
    if "cad_paths" in sys.modules:
        importlib.reload(sys.modules["cad_paths"])


# ─── /Task 8 ───
