"""sw_probe 内核单元测试（不依赖真 SW）。"""

from __future__ import annotations

import dataclasses
import sys

import pytest

from adapters.solidworks.sw_probe import ProbeResult
from adapters.solidworks.sw_detect import SwInfo
from adapters.solidworks.sw_probe import probe_detect


class TestProbeResult:
    def test_minimal_fields(self):
        r = ProbeResult(layer="x", ok=True, severity="ok", summary="hello", data={})
        assert r.layer == "x"
        assert r.ok is True
        assert r.severity == "ok"
        assert r.summary == "hello"
        assert r.data == {}
        assert r.error is None
        assert r.hint is None

    def test_with_error_and_hint(self):
        r = ProbeResult(
            layer="y",
            ok=False,
            severity="fail",
            summary="bad",
            data={"k": 1},
            error="boom",
            hint="run pip install ...",
        )
        assert r.error == "boom"
        assert r.hint == "run pip install ..."

    def test_frozen_dataclass(self):
        r = ProbeResult(layer="x", ok=True, severity="ok", summary="", data={})
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.layer = "changed"  # frozen=True 应当禁止修改

    def test_severity_accepts_three_values(self):
        for sev in ("ok", "warn", "fail"):
            r = ProbeResult(layer="x", ok=True, severity=sev, summary="", data={})
            assert r.severity == sev


from adapters.solidworks.sw_probe import probe_environment  # noqa: E402


class TestProbeEnvironment:
    def test_ok_shape(self):
        r = probe_environment()
        assert r.layer == "environment"
        assert r.severity == "ok"
        assert r.ok is True
        assert r.data["os"] == sys.platform
        assert r.data["python_version"].count(".") >= 2  # X.Y.Z
        assert r.data["python_bits"] in (32, 64)
        assert isinstance(r.data["pid"], int)
        assert r.data["pid"] > 0

    def test_summary_contains_python_version(self):
        r = probe_environment()
        # summary 至少提到 python 版本号前两位
        short_ver = ".".join(sys.version.split()[0].split(".")[:2])
        assert short_ver in r.summary


from adapters.solidworks.sw_probe import probe_pywin32  # noqa: E402


class TestProbePywin32:
    def test_available_path(self):
        """真装了 pywin32 时（Windows 开发机）走此路径；Linux CI 走下一条。"""
        try:
            import win32com.client  # noqa: F401

            has_pywin32 = True
        except ImportError:
            has_pywin32 = False

        r = probe_pywin32()
        assert r.layer == "pywin32"
        if has_pywin32:
            assert r.severity == "ok"
            assert r.ok is True
            assert r.data["available"] is True
            assert r.data["module_path"] is not None
            assert r.hint is None
        else:
            assert r.severity == "fail"
            assert r.ok is False
            assert r.data["available"] is False
            assert r.hint is not None
            assert "solidworks" in r.hint.lower()

    def test_fail_when_import_error(self, monkeypatch):
        """模拟 pywin32 未装：monkeypatch 让 import win32com.client 抛 ImportError。"""
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "win32com.client" or name.startswith("win32com"):
                raise ImportError("mocked: pywin32 not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        r = probe_pywin32()
        assert r.severity == "fail"
        assert r.ok is False
        assert r.data["available"] is False
        assert "mocked" in r.error or "pywin32" in r.error
        assert r.hint is not None


class TestProbeDetect:
    def test_installed_happy_path(self, monkeypatch):
        """mock detect_solidworks 返回已装 SW 的 SwInfo。
        probe_detect 返回 tuple (ProbeResult, SwInfo)：让下游 probe_material_files /
        probe_toolbox_index_cache 复用 info 对象，避免重复 detect。"""
        fake = SwInfo(
            installed=True,
            version="30.1.0.0080",
            version_year=2024,
            install_dir=r"D:\SOLIDWORKS Corp\SOLIDWORKS",
            sldmat_paths=["a.sldmat", "b.sldmat"],
            textures_dir=r"D:\tex",
            p2m_dir=r"D:\p2m",
            toolbox_dir=r"C:\SOLIDWORKS Data\browser",
            com_available=True,
            pywin32_available=True,
            toolbox_addin_enabled=False,
        )
        reset_called = []

        def fake_reset():
            reset_called.append(1)

        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.sw_detect._reset_cache", fake_reset
        )
        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.sw_detect.detect_solidworks", lambda: fake
        )

        r, info = probe_detect()
        assert r.layer == "detect"
        assert r.severity == "ok"
        assert r.ok is True
        assert r.data["installed"] is True
        assert r.data["version_year"] == 2024
        assert r.data["toolbox_dir"] == r"C:\SOLIDWORKS Data\browser"
        assert r.data["toolbox_addin_enabled"] is False
        assert len(reset_called) == 1, "必须调 _reset_cache 保证读最新状态"
        assert info is fake
        assert info.sldmat_paths == ["a.sldmat", "b.sldmat"]

    def test_not_installed(self, monkeypatch):
        fake = SwInfo(installed=False)
        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.sw_detect._reset_cache", lambda: None
        )
        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.sw_detect.detect_solidworks", lambda: fake
        )

        r, info = probe_detect()
        assert r.severity == "fail"
        assert r.ok is False
        assert r.data["installed"] is False
        assert r.hint is not None
        assert info is fake

    def test_detect_raises_returns_empty_info(self, monkeypatch):
        """detect_solidworks 抛异常时 probe_detect 捕获；info 返回空 SwInfo 占位。"""
        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.sw_detect._reset_cache", lambda: None
        )

        def boom():
            raise RuntimeError("simulated registry boom")

        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.sw_detect.detect_solidworks", boom
        )

        r, info = probe_detect()
        assert r.severity == "fail"
        assert r.error is not None
        assert isinstance(info, SwInfo)
        assert info.installed is False


from adapters.solidworks.sw_probe import probe_clsid  # noqa: E402


class TestProbeClsid:
    @pytest.mark.skipif(sys.platform != "win32", reason="仅 Windows 注册表")
    def test_registered_when_sw_installed(self):
        """装了 SW 的 Windows 开发机应读到 CLSID；CI Linux 跳过。"""
        r = probe_clsid()
        assert r.layer == "clsid"
        # 装 SW 则 severity=ok，未装则 fail——两种都可接受
        assert r.severity in ("ok", "fail")
        if r.severity == "ok":
            assert r.data["registered"] is True
            assert r.data["clsid"].startswith("{")

    def test_non_windows_returns_warn(self, monkeypatch):
        """非 Windows 应返回 warn（not applicable）。"""
        monkeypatch.setattr("adapters.solidworks.sw_probe.sys.platform", "linux")
        r = probe_clsid()
        assert r.layer == "clsid"
        assert r.severity == "warn"
        assert "not applicable" in r.summary or "不适用" in r.summary
        assert r.data["registered"] is False

    @pytest.mark.skipif(sys.platform != "win32", reason="winreg 仅 Windows")
    def test_fail_when_progid_missing(self, monkeypatch):
        """mock winreg.OpenKey 抛 FileNotFoundError 模拟 progid 未注册。"""
        import winreg

        def fake_open(*args, **kwargs):
            raise FileNotFoundError("not registered")

        monkeypatch.setattr(winreg, "OpenKey", fake_open)
        r = probe_clsid()
        assert r.severity == "fail"
        assert r.data["registered"] is False
        assert r.hint is not None


from adapters.solidworks.sw_probe import probe_dispatch  # noqa: E402
from adapters.solidworks.sw_probe import probe_material_files  # noqa: E402


class TestProbeMaterialFiles:
    def test_counts(self, tmp_path):
        # 3 个 sldmat、2 个 category 目录（共 4 张 png）、5 个 p2m
        sldmat_paths = []
        for n in ["a.sldmat", "b.sldmat", "c.sldmat"]:
            p = tmp_path / n
            p.write_text("x", encoding="utf-8")
            sldmat_paths.append(str(p))

        tex = tmp_path / "tex"
        (tex / "cat1").mkdir(parents=True)
        (tex / "cat2").mkdir(parents=True)
        (tex / "cat1" / "a.png").write_bytes(b"x")
        (tex / "cat1" / "b.png").write_bytes(b"x")
        (tex / "cat2" / "c.png").write_bytes(b"x")
        (tex / "cat2" / "d.png").write_bytes(b"x")

        p2m = tmp_path / "p2m"
        p2m.mkdir()
        for n in ["a.p2m", "b.p2m", "c.p2m", "d.p2m", "e.p2m"]:
            (p2m / n).write_bytes(b"x")

        info = SwInfo(
            installed=True,
            sldmat_paths=sldmat_paths,
            textures_dir=str(tex),
            p2m_dir=str(p2m),
        )

        r = probe_material_files(info)
        assert r.layer == "materials"
        assert r.severity == "ok"
        assert r.data["sldmat_files"] == 3
        assert r.data["textures_categories"] == 2
        assert r.data["textures_total"] == 4
        assert r.data["p2m_files"] == 5

    def test_missing_dirs_returns_warn(self):
        info = SwInfo(installed=True, sldmat_paths=[], textures_dir="", p2m_dir="")
        r = probe_material_files(info)
        assert r.severity == "warn"
        assert r.data["sldmat_files"] == 0
        assert r.data["textures_categories"] == 0
        assert r.data["textures_total"] == 0
        assert r.data["p2m_files"] == 0


from adapters.solidworks.sw_probe import probe_toolbox_index_cache  # noqa: E402
from adapters.solidworks.sw_probe import probe_warmup_artifacts  # noqa: E402


def _make_fake_index(fingerprint: str, counts: dict[str, dict[str, int]]) -> dict:
    """构造与 _make_index_envelope 同结构的 dict。

    counts: {"GB": {"bolts": 3, "nuts": 2}, "ISO": {"bolts": 1}}
    """
    from adapters.solidworks.sw_toolbox_catalog import SwToolboxPart

    standards = {}
    for std, subs in counts.items():
        std_dict = {}
        for sub, n in subs.items():
            std_dict[sub] = [
                SwToolboxPart(
                    standard=std,
                    subcategory=sub,
                    sldprt_path=f"C:\\{std}\\{sub}\\p{i}.sldprt",
                    filename=f"p{i}.sldprt",
                    tokens=[],
                )
                for i in range(n)
            ]
        standards[std] = std_dict
    return {"toolbox_fingerprint": fingerprint, "standards": standards}


class TestProbeToolboxIndexCache:
    def test_happy_path_not_stale(self, tmp_path, monkeypatch):
        idx = _make_fake_index("fp-abc", {"GB": {"bolts": 3}, "ISO": {"nuts": 2}})
        index_path = tmp_path / "sw_toolbox_index.json"
        index_path.write_text("{}", encoding="utf-8")
        info = SwInfo(installed=True, toolbox_dir=str(tmp_path / "tb"))
        (tmp_path / "tb").mkdir()

        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.sw_toolbox_catalog.get_toolbox_index_path",
            lambda cfg: index_path,
        )
        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.sw_toolbox_catalog.load_toolbox_index",
            lambda ip, td: idx,
        )
        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.sw_toolbox_catalog._compute_toolbox_fingerprint",
            lambda td: "fp-abc",  # 与 cached 一致 → 不 stale
        )

        r = probe_toolbox_index_cache({}, info)
        assert r.layer == "toolbox_index"
        assert r.severity == "ok"
        assert r.data["exists"] is True
        assert r.data["entry_count"] == 5  # 3 + 2
        assert r.data["toolbox_fingerprint_cached"] == "fp-abc"
        assert r.data["toolbox_fingerprint_current"] == "fp-abc"
        assert r.data["stale"] is False
        assert r.data["by_standard"] == {"GB": 3, "ISO": 2}

    def test_stale_warning(self, tmp_path, monkeypatch):
        idx = _make_fake_index("fp-old", {"GB": {"bolts": 1}})
        index_path = tmp_path / "sw_toolbox_index.json"
        index_path.write_text("{}", encoding="utf-8")
        info = SwInfo(installed=True, toolbox_dir=str(tmp_path / "tb"))
        (tmp_path / "tb").mkdir()

        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.sw_toolbox_catalog.get_toolbox_index_path",
            lambda cfg: index_path,
        )
        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.sw_toolbox_catalog.load_toolbox_index",
            lambda ip, td: idx,
        )
        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.sw_toolbox_catalog._compute_toolbox_fingerprint",
            lambda td: "fp-new",
        )

        r = probe_toolbox_index_cache({}, info)
        assert r.severity == "warn"
        assert r.data["stale"] is True
        assert r.hint is not None
        assert "sw-warmup" in r.hint or "刷新" in r.hint

    def test_index_missing(self, tmp_path, monkeypatch):
        info = SwInfo(installed=True, toolbox_dir=str(tmp_path / "tb"))
        (tmp_path / "tb").mkdir()
        missing_path = tmp_path / "nope.json"

        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.sw_toolbox_catalog.get_toolbox_index_path",
            lambda cfg: missing_path,
        )

        r = probe_toolbox_index_cache({}, info)
        assert r.severity == "warn"
        assert r.data["exists"] is False
        assert r.data["entry_count"] == 0


class TestProbeWarmupArtifacts:
    def test_all_absent_defaults_warn_or_ok(self, tmp_path, monkeypatch):
        """当 home 为空 tmp、step_cache_root 为空 tmp 时：无 lock、无 error log、0 step → warn（全空）。"""
        monkeypatch.setattr("adapters.solidworks.sw_probe.Path.home", lambda: tmp_path)
        fake_cache = tmp_path / ".cad-spec-gen" / "step_cache" / "sw_toolbox"
        fake_cache.mkdir(parents=True)
        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.sw_toolbox_catalog.get_toolbox_cache_root",
            lambda cfg: fake_cache,
        )

        r = probe_warmup_artifacts({})
        assert r.layer == "warmup"
        assert r.severity in ("ok", "warn")
        assert r.data["step_files"] == 0
        assert r.data["lock_held"] is False
        assert r.data["error_log_last_line"] is None

    def test_error_log_last_line(self, tmp_path, monkeypatch):
        monkeypatch.setattr("adapters.solidworks.sw_probe.Path.home", lambda: tmp_path)
        home = tmp_path / ".cad-spec-gen"
        home.mkdir(parents=True)
        log = home / "sw_warmup_errors.log"
        log.write_text("line1\nline2\nLAST LINE\n", encoding="utf-8")
        fake_cache = home / "step_cache" / "sw_toolbox"
        fake_cache.mkdir(parents=True)
        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.sw_toolbox_catalog.get_toolbox_cache_root",
            lambda cfg: fake_cache,
        )

        r = probe_warmup_artifacts({})
        assert r.data["error_log_last_line"] == "LAST LINE"
        assert r.data["error_log_mtime"] is not None
        assert r.severity == "warn"

    def test_step_files_count(self, tmp_path, monkeypatch):
        monkeypatch.setattr("adapters.solidworks.sw_probe.Path.home", lambda: tmp_path)
        home = tmp_path / ".cad-spec-gen"
        home.mkdir(parents=True)
        fake_cache = home / "step_cache" / "sw_toolbox"
        fake_cache.mkdir(parents=True)
        (fake_cache / "GB").mkdir()
        for i in range(3):
            (fake_cache / "GB" / f"p{i}.step").write_bytes(b"x" * 100)
        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.sw_toolbox_catalog.get_toolbox_cache_root",
            lambda cfg: fake_cache,
        )

        r = probe_warmup_artifacts({})
        assert r.data["step_files"] == 3
        assert r.data["step_size_bytes"] == 300

    @pytest.mark.skipif(
        sys.platform == "win32", reason="fcntl 仅 Unix；Windows 走 msvcrt 分支单独测试"
    )
    def test_lock_held_by_other_process_linux(self, tmp_path, monkeypatch):
        """Linux：fork 一个子进程持有 fcntl.flock，主进程 non-blocking try 检测到占用。"""
        import fcntl
        import multiprocessing

        monkeypatch.setattr("adapters.solidworks.sw_probe.Path.home", lambda: tmp_path)
        home = tmp_path / ".cad-spec-gen"
        home.mkdir(parents=True)
        fake_cache = home / "step_cache" / "sw_toolbox"
        fake_cache.mkdir(parents=True)
        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.sw_toolbox_catalog.get_toolbox_cache_root",
            lambda cfg: fake_cache,
        )
        lock_path = home / "sw_warmup.lock"

        def hold_lock(path, ready, release):
            with open(path, "a+") as fh:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                ready.set()
                release.wait(timeout=10)

        ready = multiprocessing.Event()
        release = multiprocessing.Event()
        proc = multiprocessing.Process(
            target=hold_lock, args=(lock_path, ready, release)
        )
        proc.start()
        try:
            assert ready.wait(timeout=5)
            r = probe_warmup_artifacts({})
            assert r.data["lock_held"] is True
        finally:
            release.set()
            proc.join(timeout=5)
            if proc.is_alive():
                proc.terminate()


import time  # noqa: E402


class TestProbeDispatch:
    @staticmethod
    def _install_fake_win32com(monkeypatch, *, dispatch, get_object):
        """两层 mock：win32com 根包 + win32com.client 子模块。
        Linux CI 没装 win32com，必须两层都塞进 sys.modules。"""
        import types

        fake_client = types.ModuleType("win32com.client")
        fake_client.Dispatch = dispatch
        fake_client.GetObject = get_object

        fake_root = types.ModuleType("win32com")
        fake_root.client = fake_client

        monkeypatch.setitem(sys.modules, "win32com", fake_root)
        monkeypatch.setitem(sys.modules, "win32com.client", fake_client)

    def test_success_not_attached(self, monkeypatch):
        """GetObject 抛（无现有 SW） → 走 Dispatch 冷启路径。"""

        class FakeApp:
            RevisionNumber = "30.1.0.0080"
            Visible = True

            def ExitApp(self):
                self.exited = True

        def fake_getobj(progid):
            raise OSError("no current instance")

        fake_app = FakeApp()

        self._install_fake_win32com(
            monkeypatch,
            dispatch=lambda progid: fake_app,
            get_object=fake_getobj,
        )

        r = probe_dispatch(timeout_sec=5)
        assert r.layer == "dispatch"
        assert r.severity == "ok"
        assert r.data["dispatched"] is True
        assert r.data["attached_existing_session"] is False
        assert r.data["revision_number"] == "30.1.0.0080"
        assert r.data["exit_app_ok"] is True
        assert r.data["elapsed_ms"] >= 0

    def test_attached_existing_session_warn(self, monkeypatch):
        """GetObject 成功 → severity=warn，不 ExitApp。"""

        class FakeApp:
            RevisionNumber = "30.1.0.0080"

            def ExitApp(self):
                raise AssertionError("不应 ExitApp")

        fake_app = FakeApp()

        def boom_dispatch(progid):
            raise AssertionError("附着模式下不该调 Dispatch")

        self._install_fake_win32com(
            monkeypatch,
            dispatch=boom_dispatch,
            get_object=lambda progid: fake_app,
        )

        r = probe_dispatch(timeout_sec=5)
        assert r.severity == "warn"
        assert r.data["attached_existing_session"] is True
        assert r.data["exit_app_ok"] is None or r.data["exit_app_ok"] is False
        assert "另一会话" in r.summary or "attached" in r.summary.lower()

    def test_dispatch_com_error(self, monkeypatch):
        """mock Dispatch 抛 OSError 模拟 com_error。"""

        def fake_dispatch(progid):
            raise OSError("(-2147221164, 'Class not registered', None, None)")

        def fake_getobj(progid):
            raise OSError("no instance")

        self._install_fake_win32com(
            monkeypatch,
            dispatch=fake_dispatch,
            get_object=fake_getobj,
        )

        r = probe_dispatch(timeout_sec=5)
        assert r.severity == "fail"
        assert r.data["dispatched"] is False
        assert "Class not registered" in r.error
        assert r.hint is not None

    def test_real_thread_pool_timeout(self, monkeypatch):
        """真 ThreadPoolExecutor：mock Dispatch 为阻塞 sleep(3)，timeout=1 应在 ~1s 返回 fail。"""

        def slow_dispatch(progid):
            time.sleep(3)
            return object()

        def fake_getobj(progid):
            raise OSError("no instance")

        self._install_fake_win32com(
            monkeypatch,
            dispatch=slow_dispatch,
            get_object=fake_getobj,
        )

        t0 = time.perf_counter()
        r = probe_dispatch(timeout_sec=1)
        elapsed = time.perf_counter() - t0

        assert r.severity == "fail"
        assert r.data["dispatched"] is False
        assert "timeout" in r.error.lower()
        assert 0.8 <= elapsed <= 2.0, f"elapsed={elapsed}s 应在 ~1s 上下（容差 ±0.8）"
