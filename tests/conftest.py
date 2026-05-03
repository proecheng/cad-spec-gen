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
_SRC_STR = str(_SRC)
_ROOT_STR = str(_ROOT)
for _path in (_SRC_STR, _ROOT_STR):
    while _path in sys.path:
        sys.path.remove(_path)
sys.path.insert(0, _SRC_STR)
sys.path.append(_ROOT_STR)


PHOTO3D_CONTRACT_TEST_FILES = frozenset(
    {
        "test_contract_io.py",
        "test_path_context_contract.py",
        "test_artifact_index_contract.py",
        "test_run_manifest_isolation.py",
        "test_product_graph_contract.py",
        "test_model_contract.py",
        "test_assembly_signature_contract.py",
        "test_assembly_import_isolation.py",
        "test_change_scope_gate.py",
        "test_render_manifest_signature.py",
        "test_render_qa.py",
        "test_render_manifest_no_fallback.py",
        "test_photo3d_stale_artifacts.py",
        "test_photo3d_gate_contract.py",
        "test_photo3d_gate_matrix.py",
        "test_photo3d_path_drift.py",
        "test_photo3d_baseline_binding.py",
        "test_photo3d_accept_baseline.py",
        "test_enhance_consistency.py",
        "test_photo3d_llm_action_plan.py",
        "test_layout_contract.py",
        "test_photo3d_packaging_sync.py",
    }
)


def _mark_photo3d_contract_tests(items):
    """Auto-tag default-run Photo3D contract tests by file membership."""
    marker = pytest.mark.photo3d_contract
    for item in items:
        item_path = Path(str(getattr(item, "path", "")))
        if item_path.name in PHOTO3D_CONTRACT_TEST_FILES:
            item.add_marker(marker)


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


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    """为 @pytest.mark.requires_solidworks 的 item 按需加 skip 标记。

    同时把照片级 3D 契约测试按文件清单自动标记为 photo3d_contract；
    该 marker 只做集合识别，不添加 skip，保证普通 pytest 默认执行。

    触发 skip 条件（任一满足，优先级从高到低）：
      1. sys.platform != "win32"（COM 是 Windows 独占）
      2. pywin32 (import win32com) 不可用
      3. adapters.solidworks.sw_detect.detect_solidworks().installed == False

    2 和 3 由运行时唯一事实源 sw_detect 统一回答（非 Windows 平台上
    detect_solidworks() 也返回 installed=False, pywin32_available=False，
    但显式检查 sys.platform 让 skip reason 更精确）。
    异常不吞：sw_detect 导入失败 → collection 失败，不 silent skip。
    """
    _mark_photo3d_contract_tests(items)

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


# ─── Task 14.5 (P0)：默认禁用 sw_config_broker 真路径 ───


@pytest.fixture(autouse=True, scope="function")
def disable_sw_config_broker_by_default(monkeypatch):
    """所有 pytest 默认设 CAD_SW_BROKER_DISABLE=1，broker 走 policy_fallback 短路。

    防护目的（spec rev 2 + Task 14.5 + session 33 真观察）：
    - SW Premium silent automation 在 license / Toolbox add-in 等场景仍可能弹
      modal 对话框，卡死 worker subprocess（已实测）
    - 任何漏 mock 的测试若走到 _list_configs_via_com 会真 spawn worker → 启 SW
    - 此 autouse 把 broker 默认锁死在 policy_fallback；只有需要真跑 broker 路径的
      测试（TestResolveConfigForPart / TestValidateCachedDecisionRobustness /
      TestFileLock / TestBrokerSafetyValve 等）显式 monkeypatch.delenv opt-out

    与 isolate_cad_spec_gen_home 正交：一个守 home dir，一个守 SW 触发。
    """
    monkeypatch.setenv("CAD_SW_BROKER_DISABLE", "1")
    yield


# ─── /Task 14.5 ───


# ─── Phase 3 task 14：跨文件 module-level state isolation ───
# rev 4 D8/I1：现有 conftest 已 redirect ~/.cad-spec-gen/ → tmp_path，
# 但 module-level flag 跨 process 测试也要 reset，否则 cross-test pollution。


@pytest.fixture(autouse=True)
def _reset_save_failure_warned():
    """rev 4 D8/I1：cache.py 的 _save_failure_warned flag 跨 process 测试隔离。

    放 conftest.py 而不是单文件 fixture，因 broker 测试也间接触发
    cache_mod._save_config_lists_cache → 触发 flag set → 后续 cache 测试
    "first_call" 假设破坏。
    """
    import adapters.solidworks.sw_config_lists_cache as mod
    mod._save_failure_warned = False
    yield
    mod._save_failure_warned = False


@pytest.fixture(autouse=True)
def _reset_config_list_caches():
    """rev 4 补：broker 端 _CONFIG_LIST_CACHE (L2) 跨测试清理 + autouse 防 cross-test pollution。"""
    from adapters.solidworks import sw_config_broker
    sw_config_broker._CONFIG_LIST_CACHE.clear()
    yield
    sw_config_broker._CONFIG_LIST_CACHE.clear()


# ─── /Phase 3 task 14 ───
