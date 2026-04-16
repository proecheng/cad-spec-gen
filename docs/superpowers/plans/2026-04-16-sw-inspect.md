# sw-inspect 子命令 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 `cad_pipeline.py sw-inspect [--deep] [--json]` 子命令，聚合 SW 环境/索引/材质/warmup 产物诊断到单一 CLI 入口；抽出共享内核 `adapters/solidworks/sw_probe.py`，让 `scripts/sw_spike_diagnose.py` 也调它。

**Architecture:** 分三层——`sw_probe.py` 纯函数内核（9 个 probe 返回 ProbeResult dataclass，不抛异常/不 print/不 sys.exit）；`tools/sw_inspect.py` CLI 格式化层（文本/JSON 双渲染）；`cad_pipeline.py` subparser + dispatch 注册。零破坏：env-check / sw-warmup / sw_detect 接口全保留。

**Tech Stack:** Python 3.11+、pywin32（仅 `--deep` 模式）、pytest、dataclasses、argparse、concurrent.futures（超时保护）、msvcrt/fcntl（平台分支锁测试）。

**Spec 参考：** `docs/superpowers/specs/2026-04-16-sw-inspect-design.md`（commit e3fefe4）

---

## 文件结构

**新增**：

| 路径 | 职责 |
|---|---|
| `adapters/solidworks/sw_probe.py` | 9 个 probe 函数 + `ProbeResult` dataclass（内核） |
| `tools/sw_inspect.py` | CLI 入口 `run_sw_inspect(args) -> int` + text/JSON 双渲染 |
| `tests/test_sw_probe.py` | 9 个 probe 的 ok/warn/fail 三态单元测试 + 双平台 lock |
| `tests/test_sw_inspect_cli.py` | argparse 解析 / JSON schema / exit code 矩阵 / text 分段 |
| `tests/test_sw_spike_diagnose.py` | spike 脚本薄壳调 sw_probe 的顺序与早退语义契约 |
| `tests/test_sw_inspect_real.py` | `@requires_solidworks` fast/deep smoke |

**修改**：

| 路径 | 改动 |
|---|---|
| `cad_pipeline.py` | 新增 `sw-inspect` subparser + `cmd_sw_inspect` dispatch（靠近 `sw-warmup` 注册处）|
| `scripts/sw_spike_diagnose.py` | 从 147 行收缩到 ~60 行，6 层探测委托 `sw_probe.*` |
| `tests/test_pyproject_contract.py` | 追加断言：sw-inspect 不引入新 extras |
| `docs/superpowers/decisions.md` | 追加决策 #38 |
| `tools/cad_pipeline_agent_guide.md` | 新增 sw-inspect 用法段 |
| `README.md`（存在则补）| 在 CLI 命令列表追加 `sw-inspect` |

---

## Task 1：sw_probe 骨架 + ProbeResult dataclass

**Files:**
- Create: `adapters/solidworks/sw_probe.py`
- Test: `tests/test_sw_probe.py`

- [ ] **Step 1: 写失败测试 — ProbeResult 基础字段**

创建 `tests/test_sw_probe.py`：

```python
"""sw_probe 内核单元测试（不依赖真 SW）。"""
from __future__ import annotations

import pytest

from adapters.solidworks.sw_probe import ProbeResult


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
            layer="y", ok=False, severity="fail", summary="bad",
            data={"k": 1}, error="boom", hint="run pip install ..."
        )
        assert r.error == "boom"
        assert r.hint == "run pip install ..."

    def test_frozen_dataclass(self):
        r = ProbeResult(layer="x", ok=True, severity="ok", summary="", data={})
        with pytest.raises(Exception):
            r.layer = "changed"  # frozen=True 应当禁止修改

    def test_severity_accepts_three_values(self):
        for sev in ("ok", "warn", "fail"):
            r = ProbeResult(layer="x", ok=True, severity=sev, summary="", data={})
            assert r.severity == sev
```

- [ ] **Step 2: 运行测试确认失败**

```
pytest tests/test_sw_probe.py::TestProbeResult -v
```

预期：`ModuleNotFoundError: No module named 'adapters.solidworks.sw_probe'`

- [ ] **Step 3: 写最小实现**

创建 `adapters/solidworks/sw_probe.py`：

```python
"""SolidWorks 诊断内核 — 纯函数 probe + ProbeResult dataclass。

所有 probe_* 函数：
- 不抛异常（除 KeyboardInterrupt/SystemExit）
- 不 print / 不 sys.exit
- 返回结构化 ProbeResult

被 tools/sw_inspect.py（CLI 格式化）和 scripts/sw_spike_diagnose.py（薄壳）共同调用。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


@dataclass(frozen=True)
class ProbeResult:
    """单层探测结果。

    字段：
        layer: 层名（"environment" / "pywin32" / "detect" / ...）
        ok: 本层是否健康（ok 或 warn 视为可用）
        severity: "ok" | "warn" | "fail"
        summary: 一行人读摘要
        data: 结构化字段（JSON schema 定义见 spec §4.4）
        error: 失败时的错误文案（str(exc)[:200]）
        hint: 用户可采取的下一步行动（中文，文本模式缩进打印）
    """

    layer: str
    ok: bool
    severity: Literal["ok", "warn", "fail"]
    summary: str
    data: dict
    error: Optional[str] = None
    hint: Optional[str] = None
```

- [ ] **Step 4: 运行测试确认通过**

```
pytest tests/test_sw_probe.py::TestProbeResult -v
```

预期：4 passed。

- [ ] **Step 5: 提交**

```bash
git add adapters/solidworks/sw_probe.py tests/test_sw_probe.py
git commit -m "feat(sw-inspect): ProbeResult dataclass 骨架 (Task 1)"
```

---

## Task 2：probe_environment

**Files:**
- Modify: `adapters/solidworks/sw_probe.py`
- Test: `tests/test_sw_probe.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_sw_probe.py` 末尾追加：

```python
import sys

from adapters.solidworks.sw_probe import probe_environment


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
```

- [ ] **Step 2: 运行确认失败**

```
pytest tests/test_sw_probe.py::TestProbeEnvironment -v
```

预期：`ImportError: cannot import name 'probe_environment'`

- [ ] **Step 3: 写实现**

在 `adapters/solidworks/sw_probe.py` 末尾追加：

```python
import os
import sys


def probe_environment() -> ProbeResult:
    """层 0：OS / Python 版本 / 位数 / PID。无 I/O，无可能失败点。"""
    pyver = sys.version.split()[0]
    bits = 64 if sys.maxsize > 2**32 else 32
    return ProbeResult(
        layer="environment",
        ok=True,
        severity="ok",
        summary=f"python={pyver} platform={sys.platform} arch={bits}-bit",
        data={
            "os": sys.platform,
            "python_version": pyver,
            "python_bits": bits,
            "pid": os.getpid(),
        },
    )
```

- [ ] **Step 4: 运行测试通过**

```
pytest tests/test_sw_probe.py::TestProbeEnvironment -v
```

预期：2 passed。

- [ ] **Step 5: 提交**

```bash
git add adapters/solidworks/sw_probe.py tests/test_sw_probe.py
git commit -m "feat(sw-inspect): probe_environment (Task 2)"
```

---

## Task 3：probe_pywin32

**Files:**
- Modify: `adapters/solidworks/sw_probe.py`
- Test: `tests/test_sw_probe.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_sw_probe.py` 末尾追加：

```python
from adapters.solidworks.sw_probe import probe_pywin32


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
```

- [ ] **Step 2: 运行确认失败**

```
pytest tests/test_sw_probe.py::TestProbePywin32 -v
```

预期：`ImportError: cannot import name 'probe_pywin32'`

- [ ] **Step 3: 写实现**

在 `adapters/solidworks/sw_probe.py` 末尾追加：

```python
def probe_pywin32() -> ProbeResult:
    """层 1：import win32com.client。失败提示装 [solidworks] extra。"""
    try:
        import win32com.client

        return ProbeResult(
            layer="pywin32",
            ok=True,
            severity="ok",
            summary="pywin32 已安装",
            data={
                "available": True,
                "module_path": getattr(win32com.client, "__file__", None),
            },
        )
    except Exception as e:  # ImportError 或其他
        return ProbeResult(
            layer="pywin32",
            ok=False,
            severity="fail",
            summary="pywin32 未安装或不兼容",
            data={"available": False, "module_path": None},
            error=str(e)[:200],
            hint="运行 `pip install 'cad-spec-gen[solidworks]'`（Windows only）",
        )
```

- [ ] **Step 4: 运行测试通过**

```
pytest tests/test_sw_probe.py::TestProbePywin32 -v
```

预期：2 passed（在装了 pywin32 的 Windows 开发机）或 2 passed（Linux CI，第一条走 fail 分支）。

- [ ] **Step 5: 提交**

```bash
git add adapters/solidworks/sw_probe.py tests/test_sw_probe.py
git commit -m "feat(sw-inspect): probe_pywin32 (Task 3)"
```

---

## Task 4：probe_detect（含 _reset_cache）

**Files:**
- Modify: `adapters/solidworks/sw_probe.py`
- Test: `tests/test_sw_probe.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_sw_probe.py` 末尾追加：

```python
from adapters.solidworks.sw_detect import SwInfo
from adapters.solidworks.sw_probe import probe_detect


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

        monkeypatch.setattr("adapters.solidworks.sw_probe.sw_detect._reset_cache", fake_reset)
        monkeypatch.setattr("adapters.solidworks.sw_probe.sw_detect.detect_solidworks", lambda: fake)

        r, info = probe_detect()
        assert r.layer == "detect"
        assert r.severity == "ok"
        assert r.ok is True
        assert r.data["installed"] is True
        assert r.data["version_year"] == 2024
        assert r.data["toolbox_dir"] == r"C:\SOLIDWORKS Data\browser"
        assert r.data["toolbox_addin_enabled"] is False
        assert len(reset_called) == 1, "必须调 _reset_cache 保证读最新状态"
        # info 对象透传：下游 probe 复用
        assert info is fake
        assert info.sldmat_paths == ["a.sldmat", "b.sldmat"]

    def test_not_installed(self, monkeypatch):
        fake = SwInfo(installed=False)
        monkeypatch.setattr("adapters.solidworks.sw_probe.sw_detect._reset_cache", lambda: None)
        monkeypatch.setattr("adapters.solidworks.sw_probe.sw_detect.detect_solidworks", lambda: fake)

        r, info = probe_detect()
        assert r.severity == "fail"
        assert r.ok is False
        assert r.data["installed"] is False
        assert r.hint is not None  # 指向注册表检查
        assert info is fake  # 即使未装也返回 SwInfo（installed=False 的空对象）

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
```

- [ ] **Step 2: 运行确认失败**

```
pytest tests/test_sw_probe.py::TestProbeDetect -v
```

预期：`ImportError: cannot import name 'probe_detect'`

- [ ] **Step 3: 写实现**

在 `adapters/solidworks/sw_probe.py` 顶部 import 处追加：

```python
from adapters.solidworks import sw_detect
```

然后在末尾追加：

```python
def probe_detect() -> tuple[ProbeResult, SwInfo]:
    """层 2：sw_detect 静态注册表检测。

    返回 (ProbeResult, SwInfo)：info 对象透传给 probe_material_files /
    probe_toolbox_index_cache，避免重复 detect。

    每次先 `_reset_cache()` 强制重测（SAR-2：保证长驻进程场景下读到最新状态）。
    """
    try:
        sw_detect._reset_cache()
        info = sw_detect.detect_solidworks()
    except Exception as e:
        empty = SwInfo(installed=False)
        return (
            ProbeResult(
                layer="detect",
                ok=False,
                severity="fail",
                summary="detect_solidworks 调用异常",
                data={"installed": False},
                error=str(e)[:200],
            ),
            empty,
        )

    data = {
        "installed": info.installed,
        "version": info.version,
        "version_year": info.version_year,
        "install_dir": info.install_dir,
        "textures_dir": info.textures_dir,
        "p2m_dir": info.p2m_dir,
        "toolbox_dir": info.toolbox_dir,
        "com_available": info.com_available,
        "pywin32_available": info.pywin32_available,
        "toolbox_addin_enabled": info.toolbox_addin_enabled,
    }
    if info.installed:
        return (
            ProbeResult(
                layer="detect",
                ok=True,
                severity="ok",
                summary=f"SolidWorks {info.version_year} 已安装于 {info.install_dir}",
                data=data,
            ),
            info,
        )
    return (
        ProbeResult(
            layer="detect",
            ok=False,
            severity="fail",
            summary="未在注册表检测到 SolidWorks 安装",
            data=data,
            hint="检查 HKLM\\SOFTWARE\\SolidWorks\\SOLIDWORKS 202X 注册表项；或重装 SolidWorks",
        ),
        info,
    )
```

- [ ] **Step 4: 运行测试通过**

```
pytest tests/test_sw_probe.py::TestProbeDetect -v
```

预期：2 passed。

- [ ] **Step 5: 提交**

```bash
git add adapters/solidworks/sw_probe.py tests/test_sw_probe.py
git commit -m "feat(sw-inspect): probe_detect + _reset_cache (Task 4)"
```

---

## Task 5：probe_clsid（Windows + 非 Windows 分支）

**Files:**
- Modify: `adapters/solidworks/sw_probe.py`
- Test: `tests/test_sw_probe.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_sw_probe.py` 末尾追加：

```python
import sys

from adapters.solidworks.sw_probe import probe_clsid


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
```

- [ ] **Step 2: 运行确认失败**

```
pytest tests/test_sw_probe.py::TestProbeClsid -v
```

预期：`ImportError: cannot import name 'probe_clsid'`

- [ ] **Step 3: 写实现**

在 `adapters/solidworks/sw_probe.py` 末尾追加：

```python
def probe_clsid() -> ProbeResult:
    """层 3：winreg 读 SldWorks.Application 的 CLSID（不启动进程）。"""
    if sys.platform != "win32":
        return ProbeResult(
            layer="clsid",
            ok=True,
            severity="warn",
            summary="not applicable（非 Windows 平台；CLSID 仅在 Windows 注册表）",
            data={"progid": "SldWorks.Application", "clsid": "", "registered": False},
        )
    try:
        import winreg

        progid = "SldWorks.Application"
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"{progid}\CLSID") as k:
            clsid, _ = winreg.QueryValueEx(k, "")
        return ProbeResult(
            layer="clsid",
            ok=True,
            severity="ok",
            summary=f"{progid} 已注册 CLSID={clsid}",
            data={"progid": progid, "clsid": clsid, "registered": True},
        )
    except FileNotFoundError as e:
        return ProbeResult(
            layer="clsid",
            ok=False,
            severity="fail",
            summary="SldWorks.Application progid 未注册",
            data={"progid": "SldWorks.Application", "clsid": "", "registered": False},
            error=str(e)[:200],
            hint="管理员权限运行 `sldworks.exe /regserver` 或重装 SW",
        )
    except Exception as e:
        return ProbeResult(
            layer="clsid",
            ok=False,
            severity="fail",
            summary="CLSID 查询异常",
            data={"progid": "SldWorks.Application", "clsid": "", "registered": False},
            error=str(e)[:200],
        )
```

- [ ] **Step 4: 运行测试通过**

```
pytest tests/test_sw_probe.py::TestProbeClsid -v
```

预期：3 passed（Windows 开发机全 3 条）或 1 passed + 2 skipped（Linux CI 仅非 Windows 条）。

- [ ] **Step 5: 提交**

```bash
git add adapters/solidworks/sw_probe.py tests/test_sw_probe.py
git commit -m "feat(sw-inspect): probe_clsid (Task 5)"
```

---

## Task 6：probe_toolbox_index_cache（含 by_standard + stale）

**Files:**
- Modify: `adapters/solidworks/sw_probe.py`
- Test: `tests/test_sw_probe.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_sw_probe.py` 末尾追加：

```python
import json
from pathlib import Path

from adapters.solidworks.sw_detect import SwInfo
from adapters.solidworks.sw_probe import probe_toolbox_index_cache


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
                    standard=std, subcategory=sub,
                    sldprt_path=f"C:\\{std}\\{sub}\\p{i}.sldprt",
                    filename=f"p{i}.sldprt", tokens=[],
                )
                for i in range(n)
            ]
        standards[std] = std_dict
    return {"toolbox_fingerprint": fingerprint, "standards": standards}


class TestProbeToolboxIndexCache:
    def test_happy_path_not_stale(self, tmp_path, monkeypatch):
        idx = _make_fake_index("fp-abc", {"GB": {"bolts": 3}, "ISO": {"nuts": 2}})
        index_path = tmp_path / "sw_toolbox_index.json"
        # 写假 index（load_toolbox_index 会被 mock 成直接返回，所以内容无所谓）
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
            lambda td: "fp-new",  # 与 cached 不一致 → stale
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
```

- [ ] **Step 2: 运行确认失败**

```
pytest tests/test_sw_probe.py::TestProbeToolboxIndexCache -v
```

预期：`ImportError: cannot import name 'probe_toolbox_index_cache'`

- [ ] **Step 3: 写实现**

在 `adapters/solidworks/sw_probe.py` import 区追加：

```python
from pathlib import Path

from adapters.solidworks import sw_toolbox_catalog
from adapters.solidworks.sw_detect import SwInfo
```

末尾追加：

```python
def probe_toolbox_index_cache(sw_cfg: dict, info: SwInfo) -> ProbeResult:
    """层：Toolbox index 缓存健康度（对齐 spec §3.4 真实结构）。

    - entry_count：probe 自行聚合 standards dict
    - by_standard：从 idx["standards"] 的 key 直接聚合，无硬编码白名单
    - stale：cached_fp 与 current_fp 不一致时（两端均非 "unavailable"）为 True
    """
    try:
        index_path = sw_toolbox_catalog.get_toolbox_index_path(sw_cfg)
    except Exception as e:
        return ProbeResult(
            layer="toolbox_index", ok=False, severity="fail",
            summary="解析 index 路径异常", data={"exists": False},
            error=str(e)[:200],
        )

    exists = index_path.is_file()
    size_bytes = index_path.stat().st_size if exists else 0

    if not exists:
        return ProbeResult(
            layer="toolbox_index",
            ok=True,
            severity="warn",
            summary=f"index 缓存不存在：{index_path}",
            data={
                "index_path": str(index_path),
                "exists": False,
                "entry_count": 0,
                "toolbox_fingerprint_cached": "",
                "toolbox_fingerprint_current": "",
                "stale": False,
                "size_bytes": 0,
                "by_standard": {},
            },
            hint=f"运行 `cad_pipeline.py sw-warmup --standard GB --dry-run` 首次生成索引",
        )

    if not info.installed or not info.toolbox_dir:
        return ProbeResult(
            layer="toolbox_index",
            ok=True,
            severity="warn",
            summary="SW 未安装或 toolbox_dir 不明，跳过 fingerprint 校验",
            data={
                "index_path": str(index_path),
                "exists": True,
                "entry_count": 0,
                "toolbox_fingerprint_cached": "",
                "toolbox_fingerprint_current": "",
                "stale": False,
                "size_bytes": size_bytes,
                "by_standard": {},
            },
        )

    try:
        toolbox_dir = Path(info.toolbox_dir)
        idx = sw_toolbox_catalog.load_toolbox_index(index_path, toolbox_dir)
        cached_fp = idx.get("toolbox_fingerprint", "")
        current_fp = sw_toolbox_catalog._compute_toolbox_fingerprint(toolbox_dir)
        standards = idx.get("standards", {})
        entry_count = sum(
            len(sub) for std_dict in standards.values() for sub in std_dict.values()
        )
        by_standard = {
            std: sum(len(sub) for sub in std_dict.values())
            for std, std_dict in standards.items()
        }
        stale = (
            cached_fp != current_fp
            and cached_fp != "unavailable"
            and current_fp != "unavailable"
        )

        data = {
            "index_path": str(index_path),
            "exists": True,
            "entry_count": entry_count,
            "toolbox_fingerprint_cached": cached_fp,
            "toolbox_fingerprint_current": current_fp,
            "stale": stale,
            "size_bytes": size_bytes,
            "by_standard": by_standard,
        }
        if stale:
            return ProbeResult(
                layer="toolbox_index",
                ok=True,
                severity="warn",
                summary=f"index 已 stale（cached {cached_fp[:8]} vs current {current_fp[:8]}），{entry_count} 条",
                data=data,
                hint="删除 index JSON 后重跑 sw-warmup 刷新；或 sw-warmup 自身会 fingerprint mismatch 触发重建",
            )
        return ProbeResult(
            layer="toolbox_index",
            ok=True,
            severity="ok",
            summary=f"index 健康，{entry_count} 条；{', '.join(f'{k}={v}' for k, v in by_standard.items())}",
            data=data,
        )
    except Exception as e:
        return ProbeResult(
            layer="toolbox_index",
            ok=False,
            severity="fail",
            summary="index 加载异常",
            data={"index_path": str(index_path), "exists": True, "size_bytes": size_bytes},
            error=str(e)[:200],
        )
```

- [ ] **Step 4: 运行测试通过**

```
pytest tests/test_sw_probe.py::TestProbeToolboxIndexCache -v
```

预期：3 passed。

- [ ] **Step 5: 提交**

```bash
git add adapters/solidworks/sw_probe.py tests/test_sw_probe.py
git commit -m "feat(sw-inspect): probe_toolbox_index_cache + by_standard + stale (Task 6)"
```

---

## Task 7：probe_material_files

**Files:**
- Modify: `adapters/solidworks/sw_probe.py`
- Test: `tests/test_sw_probe.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_sw_probe.py` 末尾追加：

```python
from adapters.solidworks.sw_probe import probe_material_files


class TestProbeMaterialFiles:
    def test_counts(self, tmp_path):
        # 构造：3 个 sldmat、2 个 category 目录（共 4 张 png）、5 个 p2m
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
```

- [ ] **Step 2: 运行确认失败**

```
pytest tests/test_sw_probe.py::TestProbeMaterialFiles -v
```

预期：`ImportError: cannot import name 'probe_material_files'`

- [ ] **Step 3: 写实现**

在 `adapters/solidworks/sw_probe.py` 末尾追加：

```python
def probe_material_files(info: SwInfo) -> ProbeResult:
    """层：材质/贴图/P2M 文件数（仅 count；不解析 XML，见 spec ME-2 升级路径）。"""
    sldmat_count = len(info.sldmat_paths or [])
    tex_cats = 0
    tex_total = 0
    p2m_count = 0

    try:
        tex_root = Path(info.textures_dir) if info.textures_dir else None
        if tex_root and tex_root.is_dir():
            cats = [p for p in tex_root.iterdir() if p.is_dir()]
            tex_cats = len(cats)
            for cat in cats:
                tex_total += sum(1 for _ in cat.iterdir() if _.is_file())

        p2m_root = Path(info.p2m_dir) if info.p2m_dir else None
        if p2m_root and p2m_root.is_dir():
            p2m_count = sum(1 for p in p2m_root.iterdir() if p.suffix.lower() == ".p2m")
    except Exception as e:
        return ProbeResult(
            layer="materials", ok=False, severity="fail",
            summary="材质目录扫描异常",
            data={
                "sldmat_files": sldmat_count,
                "textures_categories": tex_cats,
                "textures_total": tex_total,
                "p2m_files": p2m_count,
            },
            error=str(e)[:200],
        )

    data = {
        "sldmat_files": sldmat_count,
        "textures_categories": tex_cats,
        "textures_total": tex_total,
        "p2m_files": p2m_count,
    }
    all_zero = sldmat_count == 0 and tex_cats == 0 and p2m_count == 0
    if all_zero:
        return ProbeResult(
            layer="materials", ok=True, severity="warn",
            summary="未找到任何材质/贴图/P2M 文件",
            data=data,
            hint="检查 SW 安装是否完整；或确认 SwInfo 的 textures_dir / p2m_dir 已正确解析",
        )
    return ProbeResult(
        layer="materials", ok=True, severity="ok",
        summary=f"sldmat={sldmat_count} textures_cats={tex_cats} textures={tex_total} p2m={p2m_count}",
        data=data,
    )
```

- [ ] **Step 4: 运行测试通过**

```
pytest tests/test_sw_probe.py::TestProbeMaterialFiles -v
```

预期：2 passed。

- [ ] **Step 5: 提交**

```bash
git add adapters/solidworks/sw_probe.py tests/test_sw_probe.py
git commit -m "feat(sw-inspect): probe_material_files (Task 7)"
```

---

## Task 8：probe_warmup_artifacts（双平台锁 + 降级）

**Files:**
- Modify: `adapters/solidworks/sw_probe.py`
- Test: `tests/test_sw_probe.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_sw_probe.py` 末尾追加：

```python
import sys

from adapters.solidworks.sw_probe import probe_warmup_artifacts


class TestProbeWarmupArtifacts:
    def test_all_absent_defaults_warn_or_ok(self, tmp_path, monkeypatch):
        """当 home 为空 tmp、step_cache_root 为空 tmp 时：无 lock、无 error log、0 step → warn（全空）。"""
        monkeypatch.setattr(
            "adapters.solidworks.sw_probe.Path.home", lambda: tmp_path
        )
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
        assert r.severity == "warn"  # 有 error log 即 warn

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

    @pytest.mark.skipif(sys.platform == "win32", reason="fcntl 仅 Unix；Windows 走 msvcrt 分支单独测试")
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
        proc = multiprocessing.Process(target=hold_lock, args=(lock_path, ready, release))
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
```

- [ ] **Step 2: 运行确认失败**

```
pytest tests/test_sw_probe.py::TestProbeWarmupArtifacts -v
```

预期：`ImportError: cannot import name 'probe_warmup_artifacts'`

- [ ] **Step 3: 写实现**

在 `adapters/solidworks/sw_probe.py` import 区追加：

```python
from datetime import datetime, timezone
```

末尾追加：

```python
_STEP_COUNT_DOWNGRADE_THRESHOLD = 5000


def _read_last_line(path: Path) -> Optional[str]:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            lines = [ln.rstrip("\r\n") for ln in fh if ln.strip()]
        return lines[-1] if lines else None
    except Exception:
        return None


def _try_acquire_lock(lock_path: Path) -> tuple[bool, Optional[int]]:
    """non-blocking try-acquire：拿到 → 立即 release → 返回 (held_by_other=False, None)；
    EAGAIN → (True, pid_or_None)。"""
    if not lock_path.exists():
        return False, None
    try:
        if sys.platform == "win32":
            import msvcrt
            with lock_path.open("a+") as fh:
                fh.seek(0)
                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                    return False, None
                except OSError:
                    return True, None  # Windows 下难解析对方 PID
        else:
            import fcntl
            with lock_path.open("a+") as fh:
                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                    return False, None
                except (OSError, BlockingIOError):
                    return True, None
    except Exception:
        return False, None


def probe_warmup_artifacts(sw_cfg: dict) -> ProbeResult:
    """层：warmup 产物快照。

    路径（对齐 spec §3.3 常量表）：
      home = Path.home() / ".cad-spec-gen"
      lock_path = home / "sw_warmup.lock"
      error_log_path = home / "sw_warmup_errors.log"
      step_cache_root = get_toolbox_cache_root(sw_cfg)  # 默认 home/step_cache/sw_toolbox

    SA-2：lock 用 non-blocking try + immediate release，不与 sw-warmup 争锁。
    SAR-3：step_files > _STEP_COUNT_DOWNGRADE_THRESHOLD 时跳过 size 计算。
    """
    try:
        home = Path.home() / ".cad-spec-gen"
        lock_path = home / "sw_warmup.lock"
        error_log_path = home / "sw_warmup_errors.log"
        step_cache_root = sw_toolbox_catalog.get_toolbox_cache_root(sw_cfg)
    except Exception as e:
        return ProbeResult(
            layer="warmup", ok=False, severity="fail",
            summary="warmup 路径解析异常", data={},
            error=str(e)[:200],
        )

    lock_held, lock_pid = _try_acquire_lock(lock_path)
    error_log_last = _read_last_line(error_log_path) if error_log_path.exists() else None
    error_log_mtime = None
    if error_log_path.exists():
        ts = datetime.fromtimestamp(error_log_path.stat().st_mtime, tz=timezone.utc)
        error_log_mtime = ts.isoformat().replace("+00:00", "Z")

    step_files = 0
    step_size_bytes = 0
    if step_cache_root.is_dir():
        step_paths = list(step_cache_root.rglob("*.step"))
        step_files = len(step_paths)
        if step_files <= _STEP_COUNT_DOWNGRADE_THRESHOLD:
            step_size_bytes = sum(p.stat().st_size for p in step_paths if p.is_file())

    data = {
        "home": str(home),
        "step_cache_root": str(step_cache_root),
        "step_files": step_files,
        "step_size_bytes": step_size_bytes,
        "lock_path": str(lock_path),
        "lock_held": lock_held,
        "lock_pid": lock_pid,
        "error_log_path": str(error_log_path),
        "error_log_last_line": error_log_last,
        "error_log_mtime": error_log_mtime,
    }

    if error_log_last or lock_held:
        parts = []
        if error_log_last:
            parts.append("error_log 有内容")
        if lock_held:
            parts.append("另一进程持有 warmup 锁")
        return ProbeResult(
            layer="warmup", ok=True, severity="warn",
            summary=f"warmup: {'; '.join(parts)}；STEP {step_files} 件",
            data=data,
            hint="查看 sw_warmup_errors.log 末行；或等待占锁进程释放",
        )
    if step_files == 0:
        return ProbeResult(
            layer="warmup", ok=True, severity="warn",
            summary="warmup 缓存为空；尚未跑过 sw-warmup",
            data=data,
            hint="运行 `cad_pipeline.py sw-warmup --standard GB` 预热常用 Toolbox",
        )
    return ProbeResult(
        layer="warmup", ok=True, severity="ok",
        summary=f"STEP {step_files} 件 / {step_size_bytes // 1024} KiB",
        data=data,
    )
```

- [ ] **Step 4: 运行测试通过**

```
pytest tests/test_sw_probe.py::TestProbeWarmupArtifacts -v
```

预期：4 passed（Linux）或 3 passed + 1 skipped（Windows 开发机；Linux 独有的 fcntl 测试 skipped）。

- [ ] **Step 5: 提交**

```bash
git add adapters/solidworks/sw_probe.py tests/test_sw_probe.py
git commit -m "feat(sw-inspect): probe_warmup_artifacts 双平台锁 + 降级 (Task 8)"
```

---

## Task 9：probe_dispatch（含 GetObject 附着 + ThreadPoolExecutor 超时 + 真阻塞超时测试）

**Files:**
- Modify: `adapters/solidworks/sw_probe.py`
- Test: `tests/test_sw_probe.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_sw_probe.py` 末尾追加：

```python
import time

from adapters.solidworks.sw_probe import probe_dispatch


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
            def ExitApp(self): self.exited = True

        def fake_getobj(progid): raise OSError("no current instance")
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
            def ExitApp(self): raise AssertionError("不应 ExitApp")

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
            monkeypatch, dispatch=fake_dispatch, get_object=fake_getobj,
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
            monkeypatch, dispatch=slow_dispatch, get_object=fake_getobj,
        )

        t0 = time.perf_counter()
        r = probe_dispatch(timeout_sec=1)
        elapsed = time.perf_counter() - t0

        assert r.severity == "fail"
        assert r.data["dispatched"] is False
        assert "timeout" in r.error.lower()
        assert 0.8 <= elapsed <= 2.0, f"elapsed={elapsed}s 应在 ~1s 上下（容差 ±0.8）"
```

- [ ] **Step 2: 运行确认失败**

```
pytest tests/test_sw_probe.py::TestProbeDispatch -v
```

预期：`ImportError: cannot import name 'probe_dispatch'`

- [ ] **Step 3: 写实现**

在 `adapters/solidworks/sw_probe.py` import 区追加：

```python
import concurrent.futures
import time as _time
```

末尾追加：

```python
def probe_dispatch(timeout_sec: int = 60) -> ProbeResult:
    """层 4：Dispatch COM + Revision + Visible + ExitApp。

    3D-2：先 GetObject 检查现有 SW 会话；已运行则附着（severity=warn，不 ExitApp）。
    超时用 ThreadPoolExecutor 软超时（后台线程无法真 kill，已知妥协）。
    """
    try:
        import win32com.client  # noqa: F401
    except Exception as e:
        return ProbeResult(
            layer="dispatch", ok=False, severity="fail",
            summary="pywin32 未安装，无法 Dispatch COM",
            data={
                "dispatched": False, "elapsed_ms": 0, "revision_number": "",
                "visible_set_ok": False, "exit_app_ok": False,
                "attached_existing_session": False,
            },
            error=str(e)[:200],
            hint="运行 `pip install 'cad-spec-gen[solidworks]'`",
        )

    from win32com import client as _wc

    # 3D-2：先试附着
    attached = False
    app = None
    try:
        app = _wc.GetObject("SldWorks.Application")
        attached = True
    except Exception:
        attached = False

    if attached and app is not None:
        try:
            rev = str(getattr(app, "RevisionNumber", ""))
        except Exception as e:
            return ProbeResult(
                layer="dispatch", ok=False, severity="fail",
                summary="附着到现有 SW 但 RevisionNumber 读取失败",
                data={
                    "dispatched": True, "elapsed_ms": 0, "revision_number": "",
                    "visible_set_ok": False, "exit_app_ok": False,
                    "attached_existing_session": True,
                },
                error=str(e)[:200],
            )
        return ProbeResult(
            layer="dispatch", ok=True, severity="warn",
            summary="SW 已在另一会话运行；本次 probe 附着未接管 visibility / 未退出以保护用户工作",
            data={
                "dispatched": True, "elapsed_ms": 0, "revision_number": rev,
                "visible_set_ok": False, "exit_app_ok": None,
                "attached_existing_session": True,
            },
        )

    # 冷启路径
    t0 = _time.perf_counter()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_wc.Dispatch, "SldWorks.Application")
            app = fut.result(timeout=timeout_sec)
    except concurrent.futures.TimeoutError:
        return ProbeResult(
            layer="dispatch", ok=False, severity="fail",
            summary=f"Dispatch 超时 ({timeout_sec}s)",
            data={
                "dispatched": False, "elapsed_ms": int((_time.perf_counter() - t0) * 1000),
                "revision_number": "", "visible_set_ok": False, "exit_app_ok": False,
                "attached_existing_session": False,
            },
            error=f"dispatch timeout after {timeout_sec}s",
            hint="检查 SW 许可证、位数匹配（64-bit Python 对 64-bit SW）、是否被其他进程独占",
        )
    except Exception as e:
        return ProbeResult(
            layer="dispatch", ok=False, severity="fail",
            summary="Dispatch 抛异常",
            data={
                "dispatched": False, "elapsed_ms": int((_time.perf_counter() - t0) * 1000),
                "revision_number": "", "visible_set_ok": False, "exit_app_ok": False,
                "attached_existing_session": False,
            },
            error=str(e)[:200],
            hint="典型原因：许可证过期、SW 位数与 Python 不匹配、progid 路径错误",
        )

    elapsed_ms = int((_time.perf_counter() - t0) * 1000)
    rev = ""
    visible_ok = False
    exit_ok = False
    try:
        rev = str(getattr(app, "RevisionNumber", ""))
    except Exception:
        pass
    try:
        app.Visible = False
        visible_ok = True
    except Exception:
        pass
    try:
        app.ExitApp()
        exit_ok = True
    except Exception:
        pass

    return ProbeResult(
        layer="dispatch", ok=True, severity="ok",
        summary=f"Dispatch 冷启 {elapsed_ms}ms RevisionNumber={rev}",
        data={
            "dispatched": True, "elapsed_ms": elapsed_ms, "revision_number": rev,
            "visible_set_ok": visible_ok, "exit_app_ok": exit_ok,
            "attached_existing_session": False,
        },
    )
```

- [ ] **Step 4: 运行测试通过**

```
pytest tests/test_sw_probe.py::TestProbeDispatch -v
```

预期：4 passed。第 4 条（真 ThreadPoolExecutor 超时）约 1s 耗时。

- [ ] **Step 5: 提交**

```bash
git add adapters/solidworks/sw_probe.py tests/test_sw_probe.py
git commit -m "feat(sw-inspect): probe_dispatch 附着+超时保护 (Task 9)"
```

---

## Task 10：probe_loadaddin

**Files:**
- Modify: `adapters/solidworks/sw_probe.py`
- Test: `tests/test_sw_probe.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_sw_probe.py` 末尾追加：

```python
from adapters.solidworks.sw_probe import probe_loadaddin


class TestProbeLoadAddin:
    @staticmethod
    def _install_fake_win32com_with_app(monkeypatch, fake_app):
        """两层 mock（同 TestProbeDispatch）。"""
        import types
        def getobj(progid): raise OSError("no instance")
        fake_client = types.ModuleType("win32com.client")
        fake_client.Dispatch = lambda progid: fake_app
        fake_client.GetObject = getobj
        fake_root = types.ModuleType("win32com")
        fake_root.client = fake_client
        monkeypatch.setitem(sys.modules, "win32com", fake_root)
        monkeypatch.setitem(sys.modules, "win32com.client", fake_client)

    def test_first_progid_loads_ok(self, monkeypatch):
        loaded_calls = []

        class FakeApp:
            def LoadAddIn(self, progid):
                loaded_calls.append(progid)
                return 1  # SUCCESS

        self._install_fake_win32com_with_app(monkeypatch, FakeApp())

        r = probe_loadaddin()
        assert r.layer == "loadaddin"
        assert r.severity == "ok"
        assert r.data["loaded"] is True
        assert r.data["attempts"][0]["progid"] == "SwToolbox.1"
        assert r.data["attempts"][0]["return_code"] == 1

    def test_second_progid_fallback(self, monkeypatch):
        class FakeApp:
            def LoadAddIn(self, progid):
                return 1 if progid == "SwToolbox" else 3

        self._install_fake_win32com_with_app(monkeypatch, FakeApp())

        r = probe_loadaddin()
        assert r.severity == "ok"
        assert r.data["loaded"] is True
        assert len(r.data["attempts"]) == 2

    def test_all_fail_becomes_warn_not_fail(self, monkeypatch):
        """loadaddin 失败按 spec §5.1 降级为 warn（SW-B0 实证非必要）。"""
        class FakeApp:
            def LoadAddIn(self, progid): return 3  # 非 1 都算失败

        self._install_fake_win32com_with_app(monkeypatch, FakeApp())

        r = probe_loadaddin()
        assert r.severity == "warn"
        assert r.data["loaded"] is False
        assert all(a["return_code"] == 3 for a in r.data["attempts"])
        assert r.hint is not None
```

- [ ] **Step 2: 运行确认失败**

```
pytest tests/test_sw_probe.py::TestProbeLoadAddin -v
```

预期：`ImportError: cannot import name 'probe_loadaddin'`

- [ ] **Step 3: 写实现**

在 `adapters/solidworks/sw_probe.py` 末尾追加：

```python
def probe_loadaddin() -> ProbeResult:
    """层 5：LoadAddIn。SAR-1：无参数，内部自行 Dispatch 附着（秒级）。
    SW-B0 实证 Toolbox Add-In 非必要，失败降级为 warn，不是 fail。"""
    try:
        import win32com.client  # noqa: F401
    except Exception as e:
        return ProbeResult(
            layer="loadaddin", ok=False, severity="fail",
            summary="pywin32 未安装", data={"attempts": [], "loaded": False},
            error=str(e)[:200],
        )

    from win32com import client as _wc

    try:
        app = _wc.Dispatch("SldWorks.Application")
    except Exception as e:
        return ProbeResult(
            layer="loadaddin", ok=False, severity="fail",
            summary="Dispatch 失败，无法测试 LoadAddIn",
            data={"attempts": [], "loaded": False},
            error=str(e)[:200],
        )

    attempts = []
    loaded = False
    for progid in ("SwToolbox.1", "SwToolbox"):
        try:
            rc = int(app.LoadAddIn(progid))
        except Exception as e:
            attempts.append({"progid": progid, "return_code": None, "error": str(e)[:100]})
            continue
        attempts.append({"progid": progid, "return_code": rc})
        if rc == 1:
            loaded = True
            break

    if loaded:
        return ProbeResult(
            layer="loadaddin", ok=True, severity="ok",
            summary="Toolbox Add-In 加载成功",
            data={"attempts": attempts, "loaded": True},
        )
    return ProbeResult(
        layer="loadaddin", ok=True, severity="warn",
        summary="Toolbox Add-In 未加载（对 sldprt→STEP 转换非必要，仅插入标准件时需要）",
        data={"attempts": attempts, "loaded": False},
        hint="若要手工插入标准件，在 SW Tools → Add-Ins 中勾选 'SOLIDWORKS Toolbox Library'",
    )
```

- [ ] **Step 4: 运行测试通过**

```
pytest tests/test_sw_probe.py::TestProbeLoadAddin -v
```

预期：3 passed。

- [ ] **Step 5: 提交**

```bash
git add adapters/solidworks/sw_probe.py tests/test_sw_probe.py
git commit -m "feat(sw-inspect): probe_loadaddin (Task 10)"
```

---

## Task 11：run_sw_inspect 主编排（含文本渲染）

**Files:**
- Create: `tools/sw_inspect.py`
- Test: `tests/test_sw_inspect_cli.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_sw_inspect_cli.py`：

```python
"""tools/sw_inspect.py CLI 契约测试。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from adapters.solidworks.sw_probe import ProbeResult
from tools import sw_inspect


def _fake_args(deep: bool = False, as_json: bool = False) -> argparse.Namespace:
    return argparse.Namespace(deep=deep, json=as_json)


def _ok_probe(layer: str) -> ProbeResult:
    return ProbeResult(layer=layer, ok=True, severity="ok", summary=f"{layer} ok", data={})


def _warn_probe(layer: str) -> ProbeResult:
    return ProbeResult(layer=layer, ok=True, severity="warn", summary=f"{layer} warn", data={})


def _fail_probe(layer: str) -> ProbeResult:
    return ProbeResult(layer=layer, ok=False, severity="fail", summary=f"{layer} fail", data={}, error="boom")


def _patch_all_ok(monkeypatch):
    """所有 probe 都返回 ok。"""
    monkeypatch.setattr("tools.sw_inspect.probe_environment", lambda: _ok_probe("environment"))
    monkeypatch.setattr("tools.sw_inspect.probe_pywin32", lambda: _ok_probe("pywin32"))
    fake_info = MagicMock()
    fake_info.installed = True
    monkeypatch.setattr("tools.sw_inspect.probe_detect", lambda: (_ok_probe("detect"), fake_info))
    monkeypatch.setattr("tools.sw_inspect.probe_clsid", lambda: _ok_probe("clsid"))
    monkeypatch.setattr("tools.sw_inspect.probe_toolbox_index_cache", lambda cfg, info: _ok_probe("toolbox_index"))
    monkeypatch.setattr("tools.sw_inspect.probe_material_files", lambda info: _ok_probe("materials"))
    monkeypatch.setattr("tools.sw_inspect.probe_warmup_artifacts", lambda cfg: _ok_probe("warmup"))
    monkeypatch.setattr("tools.sw_inspect.probe_dispatch", lambda timeout_sec=60: _ok_probe("dispatch"))
    monkeypatch.setattr("tools.sw_inspect.probe_loadaddin", lambda: _ok_probe("loadaddin"))
    monkeypatch.setattr("tools.sw_inspect.load_registry", lambda: {"solidworks_toolbox": {}})


class TestRunSwInspect:
    def test_fast_all_ok_exit_0(self, monkeypatch, capsys):
        _patch_all_ok(monkeypatch)
        rc = sw_inspect.run_sw_inspect(_fake_args())
        assert rc == 0
        out = capsys.readouterr().out
        assert "Overall" in out
        assert "environment" in out

    def test_fast_warn_exit_1(self, monkeypatch, capsys):
        _patch_all_ok(monkeypatch)
        monkeypatch.setattr("tools.sw_inspect.probe_warmup_artifacts",
                            lambda cfg: _warn_probe("warmup"))
        rc = sw_inspect.run_sw_inspect(_fake_args())
        assert rc == 1

    def test_fast_fail_exit_2(self, monkeypatch):
        _patch_all_ok(monkeypatch)
        monkeypatch.setattr("tools.sw_inspect.probe_pywin32",
                            lambda: _fail_probe("pywin32"))
        rc = sw_inspect.run_sw_inspect(_fake_args())
        assert rc == 2

    def test_deep_dispatch_fail_exit_3(self, monkeypatch):
        _patch_all_ok(monkeypatch)
        monkeypatch.setattr("tools.sw_inspect.probe_dispatch",
                            lambda timeout_sec=60: _fail_probe("dispatch"))
        rc = sw_inspect.run_sw_inspect(_fake_args(deep=True))
        assert rc == 3

    def test_deep_loadaddin_fail_exit_4(self, monkeypatch):
        _patch_all_ok(monkeypatch)
        monkeypatch.setattr("tools.sw_inspect.probe_loadaddin",
                            lambda: _fail_probe("loadaddin"))
        rc = sw_inspect.run_sw_inspect(_fake_args(deep=True))
        assert rc == 4

    def test_deep_dispatch_fail_skips_loadaddin(self, monkeypatch):
        """spec §5.3：dispatch fail 时 loadaddin 不执行、不出现在 layers。"""
        _patch_all_ok(monkeypatch)
        called = []
        monkeypatch.setattr("tools.sw_inspect.probe_dispatch",
                            lambda timeout_sec=60: _fail_probe("dispatch"))
        monkeypatch.setattr("tools.sw_inspect.probe_loadaddin",
                            lambda: (called.append(1), _ok_probe("loadaddin"))[1])
        sw_inspect.run_sw_inspect(_fake_args(deep=True))
        assert called == [], "probe_loadaddin 不应被调用"
```

- [ ] **Step 2: 运行确认失败**

```
pytest tests/test_sw_inspect_cli.py::TestRunSwInspect -v
```

预期：`ModuleNotFoundError: No module named 'tools.sw_inspect'`

- [ ] **Step 3: 写实现**

创建 `tools/sw_inspect.py`：

```python
"""cad_pipeline.py sw-inspect 子命令实现。

职责：
1. 加载 parts_library registry 得 sw_cfg
2. 顺序调 sw_probe 的 9 条 probe（deep 时额外 2 条）
3. 聚合 ProbeResult → 顶层 payload
4. 按 args.json 分流 JSON/彩色文本输出
5. 按 spec §5.1 计算 exit code
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone

from adapters.solidworks.sw_probe import (
    ProbeResult,
    probe_clsid,
    probe_detect,
    probe_dispatch,
    probe_environment,
    probe_loadaddin,
    probe_material_files,
    probe_pywin32,
    probe_toolbox_index_cache,
    probe_warmup_artifacts,
)

# Part 2c P1：parts_resolver.load_registry 加载 parts_library.default.yaml
# 延迟 import 以便测试 monkeypatch
try:
    from parts_resolver import load_registry
except ImportError:  # pragma: no cover
    def load_registry():
        return {}


_SCHEMA_VERSION = "1"


def _layer_dict(r: ProbeResult) -> dict:
    """把 ProbeResult 转成 JSON schema 定义的 layer dict。"""
    d = {
        "ok": r.ok,
        "severity": r.severity,
        "summary": r.summary,
        "data": r.data,
    }
    if r.error is not None:
        d["error"] = r.error
    if r.hint is not None:
        d["hint"] = r.hint
    return d


def _severity_rank(sev: str) -> int:
    return {"ok": 0, "warn": 1, "fail": 2}[sev]


def _overall_severity(layers: dict) -> str:
    max_rank = 0
    sev = "ok"
    for layer in layers.values():
        r = _severity_rank(layer["severity"])
        if r > max_rank:
            max_rank, sev = r, layer["severity"]
    return sev


def _exit_code(mode: str, layers: dict) -> int:
    """spec §5.1 退出码表。"""
    static_layers = ("environment", "pywin32", "detect", "clsid")
    for name in static_layers:
        if name in layers and layers[name]["severity"] == "fail":
            return 2
    if mode == "deep":
        if layers.get("dispatch", {}).get("severity") == "fail":
            return 3
        if layers.get("loadaddin", {}).get("severity") == "fail":
            return 4
    # 无 fail：按 warn/ok 分
    sev = _overall_severity(layers)
    if sev == "warn":
        return 1
    return 0


def _print_text(payload: dict) -> None:
    """彩色文本渲染（复用 check_env 风格）。"""
    icon = {"ok": "[OK]  ", "warn": "[WARN]", "fail": "[FAIL]"}
    print(f"=== sw-inspect ({payload['mode']}) ===")
    for name, layer in payload["layers"].items():
        tag = icon[layer["severity"]]
        print(f"{tag} {name:16s} {layer['summary']}")
        if layer.get("hint"):
            print(f"       ↪ {layer['hint']}")
        if layer.get("error"):
            print(f"       ! {layer['error']}")
    print()
    ov = payload["overall"]
    print(
        f"Overall: {ov['severity']} "
        f"(exit {ov['exit_code']}, elapsed {ov['elapsed_ms']}ms, "
        f"warn={ov['warning_count']} fail={ov['fail_count']})"
    )
    if ov.get("summary"):
        print(f"  {ov['summary']}")


def run_sw_inspect(args: argparse.Namespace) -> int:
    """sw-inspect 主入口。返回退出码。"""
    t_start = time.perf_counter()

    sw_cfg = load_registry().get("solidworks_toolbox", {})

    layers: dict[str, dict] = {}

    r_env = probe_environment()
    layers[r_env.layer] = _layer_dict(r_env)

    r_py = probe_pywin32()
    layers[r_py.layer] = _layer_dict(r_py)

    r_det, info = probe_detect()
    layers[r_det.layer] = _layer_dict(r_det)

    r_cl = probe_clsid()
    layers[r_cl.layer] = _layer_dict(r_cl)

    r_ti = probe_toolbox_index_cache(sw_cfg, info)
    layers[r_ti.layer] = _layer_dict(r_ti)

    r_mat = probe_material_files(info)
    layers[r_mat.layer] = _layer_dict(r_mat)

    r_wm = probe_warmup_artifacts(sw_cfg)
    layers[r_wm.layer] = _layer_dict(r_wm)

    mode = "deep" if getattr(args, "deep", False) else "fast"
    if mode == "deep":
        r_dp = probe_dispatch()
        layers[r_dp.layer] = _layer_dict(r_dp)
        # spec §5.3：dispatch fail 则跳过 loadaddin
        if r_dp.severity != "fail":
            r_la = probe_loadaddin()
            layers[r_la.layer] = _layer_dict(r_la)

    warn_count = sum(1 for L in layers.values() if L["severity"] == "warn")
    fail_count = sum(1 for L in layers.values() if L["severity"] == "fail")
    overall_sev = _overall_severity(layers)
    exit_code = _exit_code(mode, layers)
    elapsed_ms = int((time.perf_counter() - t_start) * 1000)

    payload = {
        "version": _SCHEMA_VERSION,
        "generated_at": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "mode": mode,
        "overall": {
            "ok": overall_sev != "fail",
            "severity": overall_sev,
            "exit_code": exit_code,
            "warning_count": warn_count,
            "fail_count": fail_count,
            "elapsed_ms": elapsed_ms,
            "summary": layers.get("detect", {}).get("summary", ""),
        },
        "layers": layers,
    }

    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_text(payload)

    return exit_code
```

- [ ] **Step 4: 运行测试通过**

```
pytest tests/test_sw_inspect_cli.py::TestRunSwInspect -v
```

预期：6 passed。

- [ ] **Step 5: 提交**

```bash
git add tools/sw_inspect.py tests/test_sw_inspect_cli.py
git commit -m "feat(sw-inspect): run_sw_inspect 编排 + 文本渲染 + exit 码矩阵 (Task 11)"
```

---

## Task 12：JSON 渲染 + schema shape 断言

**Files:**
- Modify: `tests/test_sw_inspect_cli.py`

- [ ] **Step 1: 写失败测试（已在 Task 11 中 skeleton；这里补 schema 契约）**

在 `tests/test_sw_inspect_cli.py` 末尾追加：

```python
class TestJsonSchemaShape:
    def _assert_inspect_json_shape(self, doc: dict):
        """唯一的 JSON schema 源头断言（spec §6.3）。"""
        assert doc["version"] == "1"
        assert doc["mode"] in {"fast", "deep"}
        assert isinstance(doc["overall"]["exit_code"], int)
        assert isinstance(doc["overall"]["elapsed_ms"], int)
        assert doc["overall"]["severity"] in {"ok", "warn", "fail"}
        assert "warning_count" in doc["overall"]
        assert "fail_count" in doc["overall"]
        assert set(doc["layers"].keys()) >= {
            "environment", "pywin32", "detect", "clsid",
            "toolbox_index", "materials", "warmup",
        }
        if doc["mode"] == "deep":
            assert "dispatch" in doc["layers"]
            # loadaddin 可选（dispatch fail 时不存在）——不强制
        # generated_at 必须以 Z 结尾（UTC）
        assert doc["generated_at"].endswith("Z")
        for name, layer in doc["layers"].items():
            assert {"ok", "severity", "summary", "data"} <= layer.keys(), \
                f"layer {name} 缺字段：{layer.keys()}"
            assert layer["severity"] in {"ok", "warn", "fail"}

    def test_fast_json_shape(self, monkeypatch, capsys):
        _patch_all_ok(monkeypatch)
        sw_inspect.run_sw_inspect(_fake_args(as_json=True))
        captured = capsys.readouterr().out
        doc = json.loads(captured)
        self._assert_inspect_json_shape(doc)
        assert doc["mode"] == "fast"
        assert "dispatch" not in doc["layers"]

    def test_deep_json_shape(self, monkeypatch, capsys):
        _patch_all_ok(monkeypatch)
        sw_inspect.run_sw_inspect(_fake_args(deep=True, as_json=True))
        doc = json.loads(capsys.readouterr().out)
        self._assert_inspect_json_shape(doc)
        assert doc["mode"] == "deep"
        assert "dispatch" in doc["layers"]
        assert "loadaddin" in doc["layers"]

    def test_deep_dispatch_fail_loadaddin_absent(self, monkeypatch, capsys):
        _patch_all_ok(monkeypatch)
        monkeypatch.setattr("tools.sw_inspect.probe_dispatch",
                            lambda timeout_sec=60: _fail_probe("dispatch"))
        sw_inspect.run_sw_inspect(_fake_args(deep=True, as_json=True))
        doc = json.loads(capsys.readouterr().out)
        self._assert_inspect_json_shape(doc)
        assert "dispatch" in doc["layers"]
        assert "loadaddin" not in doc["layers"]

    def test_generated_at_is_utc(self, monkeypatch, capsys):
        _patch_all_ok(monkeypatch)
        sw_inspect.run_sw_inspect(_fake_args(as_json=True))
        doc = json.loads(capsys.readouterr().out)
        ts = doc["generated_at"]
        assert ts.endswith("Z")
        assert "T" in ts
        # 反解能成功
        from datetime import datetime
        datetime.fromisoformat(ts.replace("Z", "+00:00"))
```

- [ ] **Step 2: 运行测试（应该直接通过，Task 11 实现已含 JSON 分支）**

```
pytest tests/test_sw_inspect_cli.py::TestJsonSchemaShape -v
```

预期：4 passed。

- [ ] **Step 3: 如有失败，修 tools/sw_inspect.py**

检查 elapsed_ms 非负、generated_at 带 Z 后缀、dispatch 缺席时 loadaddin 也缺席。若 Task 11 实现正确，此步无改动。

- [ ] **Step 4: 再跑一遍总套件确认无回归**

```
pytest tests/test_sw_probe.py tests/test_sw_inspect_cli.py -v
```

预期：全绿。

- [ ] **Step 5: 提交**

```bash
git add tests/test_sw_inspect_cli.py
git commit -m "test(sw-inspect): JSON schema shape 契约测试 (Task 12)"
```

---

## Task 13：cad_pipeline.py subparser + dispatch 集成

**Files:**
- Modify: `cad_pipeline.py`（靠近 sw-warmup 注册处，约行 2849-2862 + 行 2896）
- Test: `tests/test_sw_inspect_cli.py`

- [ ] **Step 1: 写失败测试（子命令注册 + dispatch）**

在 `tests/test_sw_inspect_cli.py` 末尾追加：

```python
class TestCadPipelineIntegration:
    def test_subparser_registered(self):
        """cad_pipeline.py 构建 parser 后，sw-inspect 应为已注册的子命令。"""
        import importlib
        import cad_pipeline as cp
        importlib.reload(cp)
        parser = cp._build_parser() if hasattr(cp, "_build_parser") else None
        # 若 _build_parser 不暴露，至少在 argparse 层面试跑 help
        if parser is None:
            import subprocess
            result = subprocess.run(
                [sys.executable, "cad_pipeline.py", "sw-inspect", "--help"],
                capture_output=True, text=True, cwd=Path(__file__).parent.parent
            )
            assert result.returncode == 0
            assert "--deep" in result.stdout
            assert "--json" in result.stdout
        else:
            args = parser.parse_args(["sw-inspect", "--deep", "--json"])
            assert args.command == "sw-inspect"
            assert args.deep is True
            assert args.json is True
```

- [ ] **Step 2: 运行确认失败**

```
pytest tests/test_sw_inspect_cli.py::TestCadPipelineIntegration -v
```

预期：subprocess 退出码非 0，或断言失败（子命令未注册）。

- [ ] **Step 3: 修改 cad_pipeline.py — 新增 subparser**

定位 `cad_pipeline.py` 第 2862 行附近（`sw-warmup` 的 `p_sw_warmup.add_argument("--overwrite" ...)` 后面），**紧接着追加**：

```python
    # sw-inspect（F-1 子命令）
    p_sw_inspect = sub.add_parser(
        "sw-inspect",
        help="SolidWorks 环境/索引/材质/产物快速诊断（--deep 启动 COM）",
    )
    p_sw_inspect.add_argument(
        "--deep", action="store_true",
        help="启动 win32com Dispatch + LoadAddIn（冷启约 10–20s，纯诊断用）",
    )
    p_sw_inspect.add_argument(
        "--json", action="store_true",
        help="输出机读 JSON 而非彩色文本",
    )
```

- [ ] **Step 4: 修改 cad_pipeline.py — 新增 cmd_sw_inspect 函数**

定位 `cad_pipeline.py` 第 2494 行（`cmd_sw_warmup` 函数末尾 `return run_sw_warmup(args)` 之后），**紧接着追加**：

```python
def cmd_sw_inspect(args):
    """F-1：SW 环境/索引/材质/warmup 产物诊断。"""
    from tools.sw_inspect import run_sw_inspect

    return run_sw_inspect(args)
```

- [ ] **Step 5: 修改 cad_pipeline.py — dispatch 映射表**

定位 `cad_pipeline.py` 第 2896 行附近（`"sw-warmup": cmd_sw_warmup,`），**紧接着追加一行**：

```python
        "sw-inspect": cmd_sw_inspect,
```

- [ ] **Step 6: 运行测试通过**

```
pytest tests/test_sw_inspect_cli.py::TestCadPipelineIntegration -v
```

预期：1 passed。再跑一次冒烟：

```
python cad_pipeline.py sw-inspect --help
```

预期 stdout 含 `--deep` 和 `--json`。

- [ ] **Step 7: 提交**

```bash
git add cad_pipeline.py tests/test_sw_inspect_cli.py
git commit -m "feat(sw-inspect): cad_pipeline.py subparser + dispatch (Task 13)"
```

---

## Task 14：scripts/sw_spike_diagnose.py 改造为薄壳

**Files:**
- Modify: `scripts/sw_spike_diagnose.py`
- Create: `tests/test_sw_spike_diagnose.py`

- [ ] **Step 1: 写失败测试（契约测试）**

创建 `tests/test_sw_spike_diagnose.py`：

```python
"""scripts/sw_spike_diagnose.py 改造后契约：调 sw_probe.*，按顺序早退。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from adapters.solidworks.sw_probe import ProbeResult


def _fail_probe(layer: str) -> ProbeResult:
    return ProbeResult(layer=layer, ok=False, severity="fail", summary=f"{layer} fail",
                       data={}, error="mocked")


def _ok_probe(layer: str) -> ProbeResult:
    return ProbeResult(layer=layer, ok=True, severity="ok", summary=f"{layer} ok", data={})


@pytest.fixture
def reload_spike():
    """保证 scripts.sw_spike_diagnose 按当前实现重新加载。"""
    import importlib

    # 允许 scripts/ 从 sys.path 读
    root = Path(__file__).resolve().parent.parent
    scripts_path = str(root / "scripts")
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    import sw_spike_diagnose
    importlib.reload(sw_spike_diagnose)
    return sw_spike_diagnose


class TestSpikeDelegatesToProbe:
    def test_pywin32_fail_returns_1(self, reload_spike, monkeypatch):
        monkeypatch.setattr("adapters.solidworks.sw_probe.probe_pywin32",
                            lambda: _fail_probe("pywin32"))
        rc = reload_spike.main()
        assert rc == 1

    def test_detect_fail_returns_2(self, reload_spike, monkeypatch):
        from adapters.solidworks.sw_detect import SwInfo
        monkeypatch.setattr("adapters.solidworks.sw_probe.probe_pywin32",
                            lambda: _ok_probe("pywin32"))
        # probe_detect 返回 tuple (ProbeResult, SwInfo)
        monkeypatch.setattr("adapters.solidworks.sw_probe.probe_detect",
                            lambda: (_fail_probe("detect"), SwInfo(installed=False)))
        rc = reload_spike.main()
        assert rc == 2

    def test_all_ok_returns_0(self, reload_spike, monkeypatch):
        from adapters.solidworks.sw_detect import SwInfo
        for fn in ("probe_pywin32", "probe_clsid", "probe_dispatch", "probe_loadaddin"):
            layer = fn.replace("probe_", "")
            monkeypatch.setattr(f"adapters.solidworks.sw_probe.{fn}",
                                lambda layer=layer: _ok_probe(layer))
        monkeypatch.setattr("adapters.solidworks.sw_probe.probe_detect",
                            lambda: (_ok_probe("detect"), SwInfo(installed=True)))
        rc = reload_spike.main()
        assert rc == 0

    def test_loadaddin_fail_does_not_early_exit(self, reload_spike, monkeypatch):
        """spike 脚本对 loadaddin 不早退（spec §4.8 sample code）。"""
        from adapters.solidworks.sw_detect import SwInfo
        for fn in ("probe_pywin32", "probe_clsid", "probe_dispatch"):
            layer = fn.replace("probe_", "")
            monkeypatch.setattr(f"adapters.solidworks.sw_probe.{fn}",
                                lambda layer=layer: _ok_probe(layer))
        monkeypatch.setattr("adapters.solidworks.sw_probe.probe_detect",
                            lambda: (_ok_probe("detect"), SwInfo(installed=True)))
        monkeypatch.setattr("adapters.solidworks.sw_probe.probe_loadaddin",
                            lambda: _fail_probe("loadaddin"))
        rc = reload_spike.main()
        assert rc == 0  # loadaddin fail 不影响退出码
```

- [ ] **Step 2: 运行确认失败**

```
pytest tests/test_sw_spike_diagnose.py -v
```

预期：失败（当前 spike 脚本还没改造，直接跑 COM 而非 probe_*）。

- [ ] **Step 3: 重写 `scripts/sw_spike_diagnose.py`**

完整替换文件内容：

```python
"""SW-B0 spike 诊断脚本（薄壳版）—— 委托 adapters.solidworks.sw_probe。

历史兜底工具：当 `cad_pipeline.py sw-inspect --deep` 出问题时在此直跑最底层。
一般用户优先用 CLI；本脚本保留为 SW-B0 时期 REPL 友好的调试入口。

退出码（与 CLI sw-inspect 独立，保留历史语义）：
  0 = 全绿
  1 = probe_pywin32 fail
  2 = probe_detect fail
  3 = probe_clsid fail
  4 = probe_dispatch fail
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from adapters.solidworks import sw_probe  # noqa: E402


_ICON = {"ok": "[OK]  ", "warn": "[WARN]", "fail": "[FAIL]"}


def _print(r) -> None:
    print(f"{_ICON[r.severity]} {r.layer:12s} {r.summary}")
    if r.hint:
        print(f"       ↪ {r.hint}")
    if r.error:
        print(f"       ! {r.error}")


def main() -> int:
    print("=" * 60)
    print("SW-B0 spike diagnose — 逐层边界探测（薄壳；委托 sw_probe）")
    print("=" * 60)

    # probe_detect 返回 tuple (ProbeResult, SwInfo)，spike 只消费 ProbeResult
    probes = [
        (sw_probe.probe_pywin32, 1),
        (lambda: sw_probe.probe_detect()[0], 2),
        (sw_probe.probe_clsid, 3),
        (sw_probe.probe_dispatch, 4),
        (sw_probe.probe_loadaddin, None),  # 不早退
    ]
    for probe_fn, exit_on_fail in probes:
        r = probe_fn()
        _print(r)
        if r.severity == "fail" and exit_on_fail is not None:
            return exit_on_fail

    print("\n" + "=" * 60)
    print("诊断完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 运行测试通过**

```
pytest tests/test_sw_spike_diagnose.py -v
```

预期：4 passed。

- [ ] **Step 5: 提交**

```bash
git add scripts/sw_spike_diagnose.py tests/test_sw_spike_diagnose.py
git commit -m "refactor(sw-inspect): sw_spike_diagnose 改造为 sw_probe 薄壳 (Task 14)"
```

---

## Task 15：@requires_solidworks 真跑 smoke 测试

**Files:**
- Create: `tests/test_sw_inspect_real.py`

- [ ] **Step 1: 写测试（非失败；CI 自动 skip）**

创建 `tests/test_sw_inspect_real.py`：

```python
"""sw-inspect 真 SW smoke 测试。

带 @pytest.mark.requires_solidworks，tests/conftest.py 的 pytest_collection_modifyitems
钩子会在非 Windows / 无 pywin32 / 无 SW 安装时自动 skip。

本组测试不依赖任何 mock，直接调 run_sw_inspect；结果反映真实开发机环境。
"""
from __future__ import annotations

import argparse
import io
import json
from contextlib import redirect_stdout

import pytest

from tools.sw_inspect import run_sw_inspect


@pytest.mark.requires_solidworks
class TestSwInspectRealSmoke:
    def test_fast_real_smoke(self):
        args = argparse.Namespace(deep=False, json=True)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = run_sw_inspect(args)
        doc = json.loads(buf.getvalue())
        assert rc in (0, 1), f"fast 模式应 0/1；实际 {rc}，doc={doc}"
        assert doc["mode"] == "fast"
        assert doc["layers"]["detect"]["data"]["installed"] is True
        assert doc["layers"]["detect"]["data"]["version_year"] >= 2020

    def test_deep_real_smoke(self):
        args = argparse.Namespace(deep=True, json=True)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = run_sw_inspect(args)
        doc = json.loads(buf.getvalue())
        assert doc["mode"] == "deep"
        # dispatch 可能 ok 或 warn（已附着）；不应 fail
        disp = doc["layers"]["dispatch"]
        assert disp["severity"] in ("ok", "warn"), f"dispatch={disp}"
        assert disp["data"]["elapsed_ms"] < 30_000, \
            f"Dispatch 耗时 {disp['data']['elapsed_ms']}ms 超 30s"
```

- [ ] **Step 2: 运行测试**

```
pytest tests/test_sw_inspect_real.py -v
```

预期：
- 装 SW 的 Windows 开发机：2 passed（真跑 deep 约 15s）
- 其他机器：2 skipped（reason 包含 "requires_solidworks"）

- [ ] **Step 3: 若 real smoke 失败，调整**

常见失败：`dispatch.severity == "fail"` 但机器确实装 SW —— 检查是否 SW 许可到期 / 独占锁。修 sw_probe / sw_inspect 而非改测试。

- [ ] **Step 4: 提交**

```bash
git add tests/test_sw_inspect_real.py
git commit -m "test(sw-inspect): requires_solidworks real smoke (Task 15)"
```

---

## Task 16：test_pyproject_contract 追加断言

**Files:**
- Modify: `tests/test_pyproject_contract.py`

- [ ] **Step 1: 查看当前 pyproject contract test**

```
head -80 tests/test_pyproject_contract.py
```

定位 `[project.optional-dependencies]` solidworks extra 的解析处。

- [ ] **Step 2: 追加失败测试**

在 `tests/test_pyproject_contract.py` 末尾追加：

```python
class TestSwInspectNoNewExtras:
    """F-1 sw-inspect 引入时，确保不新增任何 extras（决策 #37 范围保持）。"""

    def test_no_new_optional_dependencies_group(self):
        import tomllib
        from pathlib import Path

        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        extras = set(data["project"].get("optional-dependencies", {}).keys())
        # 本次仅允许的 extras：与 Part 2c P2 时相同
        allowed = {"solidworks", "all", "dev"}  # 实际以当前 pyproject 为准
        # 若仓库还有别的 extras（e.g. "render"），把它们加进 allowed
        assert extras <= allowed, f"新增未登记的 extras: {extras - allowed}"

    def test_sw_inspect_imports_without_solidworks_extra(self):
        """sw-inspect 模块应在不装 [solidworks] 时仍可 import（只是 --deep 会 fail）。"""
        import importlib
        import tools.sw_inspect as m
        importlib.reload(m)
        assert hasattr(m, "run_sw_inspect")
```

- [ ] **Step 3: 运行测试**

```
pytest tests/test_pyproject_contract.py::TestSwInspectNoNewExtras -v
```

预期：2 passed。若第一条失败，按实际 pyproject 的 extras 调整 `allowed` 集合。

- [ ] **Step 4: 提交**

```bash
git add tests/test_pyproject_contract.py
git commit -m "test(sw-inspect): pyproject contract — 无新 extras (Task 16)"
```

---

## Task 17：文档更新（decisions #38 + agent_guide + README）

**Files:**
- Modify: `docs/superpowers/decisions.md`
- Modify: `tools/cad_pipeline_agent_guide.md`
- Modify: `README.md`（若存在 CLI 命令列表则补；不存在则跳过）

- [ ] **Step 1: 追加决策 #38**

打开 `docs/superpowers/decisions.md`，在末尾追加：

```markdown

## #38 sw-inspect 作为正式深度诊断入口（2026-04-16）

- **决策**：`cad_pipeline.py sw-inspect [--deep] [--json]` 为 SW 诊断的**正式 CLI 入口**；
  `scripts/sw_spike_diagnose.py` 保留为 SW-B0 时期 REPL 友好的历史档案，内部薄壳调
  `adapters/solidworks/sw_probe.py` 共享内核。
- **退出码独立编号**：
  - sw-inspect：`0` 全绿 / `1` warn / `2` 静态 fail / `3` deep-COM fail / `4` deep-addin fail / `64` 参数错
  - sw_spike_diagnose：`0/1/2/3/4` 继承 SW-B0 时期历史语义不变
  - 两者不互通；CI 和脚本默认消费 sw-inspect 退出码
- **JSON schema v1 稳定字段**（消费方依赖）：
  `overall.exit_code` / `overall.elapsed_ms` / `layers.*.severity` /
  `layers.dispatch.data.elapsed_ms`（F-4a baseline 数据源）
- **F-1 follow-up**：F-1.1 deep 模式材质 XML 解析；F-1.2 subprocess 隔离 Dispatch 悬挂；
  F-1.3 Windows self-hosted runner 真跑 real smoke
- **Spec**：`docs/superpowers/specs/2026-04-16-sw-inspect-design.md`
- **Plan**：`docs/superpowers/plans/2026-04-16-sw-inspect.md`
```

- [ ] **Step 2: 追加 agent_guide 用法段**

打开 `tools/cad_pipeline_agent_guide.md`，在 `sw-warmup` 段之后追加：

```markdown

## sw-inspect — SW 诊断单一入口

**用途**：聚合 SW 环境 / Toolbox 索引 / 材质库 / warmup 产物状态到一个 CLI。

**用法**：
```bash
# 快速扫（< 500ms，不启动 SW 进程）
python cad_pipeline.py sw-inspect

# 深度诊断（真跑 Dispatch + LoadAddIn，冷启约 10–20s）
python cad_pipeline.py sw-inspect --deep

# 机读 JSON 输出给 CI / 脚本消费
python cad_pipeline.py sw-inspect --json
python cad_pipeline.py sw-inspect --deep --json
```

**退出码**：0 全绿 / 1 warn / 2 环境 fail / 3 deep-COM fail / 4 deep-addin fail / 64 参数错

**排障定位**：若 `sw-warmup` 挂了，先跑 `sw-inspect --deep` 看卡在哪一层；输出的 `hint` 字段会指向下一步行动。
```

- [ ] **Step 3: 若 README.md 存在 CLI 列表，追加一行**

```bash
grep -n "sw-warmup" README.md 2>&1 | head -5
```

若命中，在 README.md 的 sw-warmup 条目后追加一行：

```markdown
- `sw-inspect [--deep] [--json]`: SW 环境/索引/材质/warmup 产物诊断
```

- [ ] **Step 4: 快速冒烟：文档格式没破**

```
pytest tests/ -q --co 2>&1 | tail -5
```

`--co` 只收集不执行，确认没 import 错误。

- [ ] **Step 5: 提交**

```bash
git add docs/superpowers/decisions.md tools/cad_pipeline_agent_guide.md README.md
git commit -m "docs(sw-inspect): 决策 #38 + agent_guide + README (Task 17)"
```

---

## 收尾：全量回归

**Files:** 无新增，仅验证

- [ ] **Step 1: 跑全部 SW 相关测试**

```
pytest tests/test_sw_probe.py tests/test_sw_inspect_cli.py tests/test_sw_spike_diagnose.py tests/test_sw_inspect_real.py tests/test_pyproject_contract.py -v
```

预期：~30 passed + 2 skipped（real smoke 在无 SW 机器 skip）。

- [ ] **Step 2: 跑全量套件确认无回归**

```
pytest tests/ -q
```

预期：全绿，不破坏 Part 2c P2 已有 173 passed 基线。

- [ ] **Step 3: lint**

```
ruff check adapters/solidworks/sw_probe.py tools/sw_inspect.py scripts/sw_spike_diagnose.py tests/test_sw_probe.py tests/test_sw_inspect_cli.py tests/test_sw_spike_diagnose.py tests/test_sw_inspect_real.py
ruff format --check adapters/solidworks/sw_probe.py tools/sw_inspect.py scripts/sw_spike_diagnose.py tests/test_sw_probe.py tests/test_sw_inspect_cli.py tests/test_sw_spike_diagnose.py tests/test_sw_inspect_real.py
```

有违规则 `ruff format` 修复后再 `ruff check --fix`。

- [ ] **Step 4: 手动冒烟（可选：有 SW 的机器）**

```
python cad_pipeline.py sw-inspect
python cad_pipeline.py sw-inspect --json | python -m json.tool
python cad_pipeline.py sw-inspect --deep --json | python -m json.tool
```

- [ ] **Step 5: 提交 lint 修复（若有）**

```bash
git add -u && git commit -m "style(sw-inspect): ruff format 收尾"
```

---

## 附录 A：Spec 覆盖对照

| Spec 章节 | Task(s) | 说明 |
|---|---|---|
| §2.1 sw_probe 内核 | 1–10 | 9 probe + ProbeResult dataclass |
| §2.2 sw_inspect CLI | 11, 12 | run_sw_inspect + 文本/JSON 渲染 |
| §2.3 cad_pipeline 改动 | 13 | subparser + dispatch |
| §2.4 spike 脚本改造 | 14 | 薄壳重写 |
| §3.3 数据流融合表 | 11（load_registry / info 复用）、6（sw_cfg）、8（路径常量）| |
| §3.4 Toolbox Index 结构 | 6 | entry_count / by_standard / stale |
| §4.3 JSON 契约 + §4.3.1 消费者表 | 11, 12 | schema v1 shape |
| §5 退出码 | 11, 13 | exit 0/1/2/3/4 矩阵 |
| §6 测试策略 | 各 Task 的 Step 1 测试 | 单元 + CLI + 契约 + real smoke + pyproject |
| §8 向后兼容 | 13（不改 sw-warmup）、14（spike 退出码沿用）| |
| §9 文档更新 | 17 | decisions / agent_guide / README |
| §10 Packaging | 16 | 无新 extras 断言 |

## 附录 B：每步时长估算（自核）

17 Task × 约 5 Step × 2–5 分钟 ≈ 170–420 分钟（3–7 小时）。实际 subagent-driven 并行可显著压缩。
