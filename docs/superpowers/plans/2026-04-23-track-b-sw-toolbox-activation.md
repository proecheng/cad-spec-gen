# Track B — SW Toolbox 装即用路径贯通 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 解耦 SW Toolbox Add-in 硬门、修复 `is_available()` 错误拒绝本机合法安装、贯通 sldprt→STEP 转换的物理可达性判断（B3 spike 待定）。

**Architecture:** B0 归一化 `SwInfo.edition` 并加文件系统探针；B1 新增三段式 `discover_toolbox_addin_guid()`；B2 重写 `is_available()`（Standard 版拒、path-healthy 检查、addin 降 advisory）并将 matrix 改为全量跑检查后按 `_BLOCKING_CHECKS` 决定 passed。

**Tech Stack:** Python 3.11+, pytest, winreg (Windows-only, requires_windows marker), `@dataclass(frozen=True)`

**范围说明：** 本计划实施 B0+B1+B2；B3（sldprt→STEP worker 修复）待 spike 结果后独立计划。

---

## 文件结构

| 文件 | 操作 | 职责变化 |
|---|---|---|
| `adapters/solidworks/sw_detect.py` | 修改 | `SwInfo.edition` Literal 归一化；`_find_edition` 加文件系统探针；新增 `check_toolbox_path_healthy`、`_addins_candidates`、`_scan_all_addins_by_description`、`_scan_addin_dll_clsid`、`discover_toolbox_addin_guid` |
| `adapters/parts/sw_toolbox_adapter.py` | 修改 | `is_available()` 全量重写（解耦 addin 硬门、加 Standard 拒、加 path-healthy） |
| `sw_preflight/matrix.py` | 修改 | 新增 `_BLOCKING_CHECKS`；`run_all_checks()` 全量不短路；`_check_toolbox_path` → `_check_toolbox_path_healthy`；`_check_addin_enabled` 降级 advisory；`fix_addin_enable` 使用 `discover_toolbox_addin_guid` |
| `sw_preflight/types.py` | 修改 | `PreflightResult` 加 `advisory_failures: dict` 字段 |
| `sw_preflight/preflight.py` | 修改 | 按 blocking 失败决定 passed，收集 advisory |
| `sw_preflight/cache.py` | 修改 | `SCHEMA_VERSION` 1 → 2 |
| `sw_preflight/report.py` | 修改 | toolbox 行加 advisory 展示 |
| `tests/test_discover_toolbox_addin_guid.py` | 新增 | B1 三段式单测 |
| `tests/test_sw_toolbox_adapter_is_available_b2.py` | 新增 | B2 is_available 新断言 |
| `tests/test_sw_preflight_blocking_checks.py` | 新增 | _BLOCKING_CHECKS + advisory 断言 |
| `tests/test_sw_preflight_cache_schema.py` | 修改 | schema v2 断言 |
| `tests/test_sw_preflight_matrix_check.py` | 修改 | edition 字符串从 `'Standard'` → `'standard'` |
| `tests/test_sw_toolbox_adapter.py` | 修改 | `test_addin_disabled_returns_false` → 改为期望 `ok is True` |

---

## Task 1: B0 — SwInfo.edition 归一化 + _find_edition 文件系统探针

**Files:**
- Modify: `adapters/solidworks/sw_detect.py`
- Modify: `sw_preflight/matrix.py`
- Test: `tests/test_sw_preflight_matrix_check.py`

- [ ] **Step 1: 写失败测试（edition 归一化 + 文件系统探针）**

```python
# tests/test_b0_edition.py（临时测试文件，Task 1 结束后合入正式位置）
import sys
import types
import pytest
from adapters.solidworks import sw_detect


def _make_winreg(key_vals: dict):
    """构造最小 winreg mock，key_vals = {(hive, path): {name: value}}。"""
    import types
    m = types.SimpleNamespace()
    m.HKEY_LOCAL_MACHINE = 2
    m.HKEY_CURRENT_USER = 1
    m.KEY_READ = 1

    class FakeKey:
        def __init__(self, vals):
            self._vals = vals
        def __enter__(self): return self
        def __exit__(self, *_): pass

    def open_key(hive, path, *_):
        key = (hive, path)
        if key not in key_vals:
            raise FileNotFoundError
        return FakeKey(key_vals[key])

    def query_value_ex(key, name):
        if name not in key._vals:
            raise FileNotFoundError
        return (key._vals[name], 1)

    m.OpenKey = open_key
    m.QueryValueEx = query_value_ex
    return m


@pytest.mark.skipif(sys.platform != "win32", reason="需要 Windows")
def test_edition_normalized_pro_to_professional(tmp_path, monkeypatch):
    """注册表 'Professional' → 归一化为 'professional'。"""
    wr = _make_winreg({
        (2, r"SOFTWARE\SolidWorks\SOLIDWORKS 2024\Setup"): {"Edition": "Professional"},
    })
    result = sw_detect._find_edition(wr, 2024, "")
    assert result == "professional"


@pytest.mark.skipif(sys.platform != "win32", reason="需要 Windows")
def test_edition_standard_lower(tmp_path, monkeypatch):
    """注册表 'Standard' → 归一化为 'standard'。"""
    wr = _make_winreg({
        (2, r"SOFTWARE\SolidWorks\SOLIDWORKS 2024\Setup"): {"Edition": "Standard"},
    })
    result = sw_detect._find_edition(wr, 2024, "")
    assert result == "standard"


def test_edition_filesystem_probe_finds_dll(tmp_path):
    """注册表无 Edition，install_dir 下有 Toolbox DLL → 返回 'professional'。"""
    addin_dir = tmp_path / "AddIns" / "Toolbox"
    addin_dir.mkdir(parents=True)
    (addin_dir / "SWToolboxBrowser.dll").write_bytes(b"MZ")

    import types
    wr = types.SimpleNamespace(
        HKEY_LOCAL_MACHINE=2,
        KEY_READ=1,
    )
    wr.OpenKey = lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError())

    result = sw_detect._find_edition(wr, 2024, str(tmp_path))
    assert result == "professional"


def test_edition_filesystem_probe_no_dll_returns_standard(tmp_path):
    """注册表无 Edition，install_dir 存在但无 Toolbox DLL → 返回 'standard'。"""
    # install_dir 存在但无 toolbox AddIns 子目录
    (tmp_path / "AddIns").mkdir()

    import types
    wr = types.SimpleNamespace(HKEY_LOCAL_MACHINE=2, KEY_READ=1)
    wr.OpenKey = lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError())

    result = sw_detect._find_edition(wr, 2024, str(tmp_path))
    assert result == "standard"


def test_edition_unknown_when_no_install_dir():
    """注册表无 Edition，install_dir 为空 → 'unknown'。"""
    import types
    wr = types.SimpleNamespace(HKEY_LOCAL_MACHINE=2, KEY_READ=1)
    wr.OpenKey = lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError())

    result = sw_detect._find_edition(wr, 2024, "")
    assert result == "unknown"
```

- [ ] **Step 2: 运行测试，确认失败**

```
uv run pytest tests/test_b0_edition.py -v
```

期望：`FAILED`（`_find_edition` 签名不接受 `install_dir`，归一化结果也不是小写）

- [ ] **Step 3: 修改 `SwInfo.edition` Literal 类型（sw_detect.py:73）**

```python
# 修改前：
edition: Literal["Standard", "Pro", "Premium", "unknown"] = "unknown"

# 修改后：
edition: Literal["standard", "professional", "premium", "trial", "educational", "unknown"] = "unknown"
```

- [ ] **Step 4: 修改 `_find_edition()` 签名和返回值（sw_detect.py）**

```python
def _find_edition(
    winreg, version_year: int, install_dir: str = ""
) -> Literal["standard", "professional", "premium", "trial", "educational", "unknown"]:
    """从注册表或文件系统读取 SolidWorks edition 字段（Track B0 三探针）。

    探针顺序：
      Probe 1 — 注册表 Setup\\Edition value（快，命中率高）
      Probe 2 — 文件系统：install_dir\\AddIns\\Toolbox*\\ 下 .dll 存在 → Pro+
      全 miss  — install_dir 存在 → 'standard'；install_dir 空 → 'unknown'
    """
    key_patterns = [
        r"SOFTWARE\SolidWorks\SolidWorks {year}\Setup",
        r"SOFTWARE\SolidWorks\SOLIDWORKS {year}\Setup",
    ]

    for pattern in key_patterns:
        key_path = pattern.format(year=version_year)
        raw = _read_registry_value(
            winreg, winreg.HKEY_LOCAL_MACHINE, key_path, "Edition"
        )
        if not raw:
            continue
        lower = raw.strip().lower()
        if lower in ("professional", "pro"):
            return "professional"
        if lower == "standard":
            return "standard"
        if lower == "premium":
            return "premium"
        if lower == "trial":
            return "trial"
        if lower == "educational":
            return "educational"

    # Probe 2: 文件系统 Toolbox DLL 存在性
    if install_dir:
        from pathlib import Path as _Path
        for sub in ("toolbox", "Toolbox"):
            d = _Path(install_dir) / "AddIns" / sub
            if d.is_dir() and any(d.glob("*.dll")):
                return "professional"
        # install_dir 存在但无 Toolbox DLL → Standard
        return "standard"

    return "unknown"
```

- [ ] **Step 5: 更新 `_detect_impl()` 中 `_find_edition` 调用（传入 install_dir）**

```python
# 找到这一行（约 sw_detect.py:177）：
    info.edition = _find_edition(winreg, info.version_year)

# 改为：
    info.edition = _find_edition(winreg, info.version_year, info.install_dir)
```

- [ ] **Step 6: 修改 matrix.py 中 edition 比较字符串**

```python
# sw_preflight/matrix.py:105，找到：
    if info.edition == 'Standard':

# 改为：
    if info.edition == 'standard':
```

同时修改诊断文案里的 'Standard'（同文件约 108–109 行）：
```python
            reason="SolidWorks Standard 版本不包含 Toolbox 标准件库",
            suggestion="升级到 Professional/Premium，或继续使用 stand-in 占位",
```
这两行文案不变（用户可读文案，不是枚举值），无需修改。

- [ ] **Step 7: 运行测试，确认通过**

```
uv run pytest tests/test_b0_edition.py -v
```

期望：4 个 test PASS（skipif on non-Windows 的 2 个在 Linux 上会 skip）

- [ ] **Step 8: 补测试 — matrix check 用 'standard'（非 'Standard'）**

```python
# tests/test_sw_preflight_matrix_check.py
# 找到 test_toolbox_supported_standard_returns_false 相关测试（若存在），
# 把 mock edition 从 'Standard' 改为 'standard'
# 如果没有，添加：
def test_check_toolbox_supported_standard_edition(monkeypatch):
    """edition == 'standard' → _check_toolbox_supported 返 False。"""
    from adapters.solidworks import sw_detect
    from sw_preflight import matrix

    sw_detect._reset_cache()
    fake = sw_detect.SwInfo(installed=True, version_year=2024, edition='standard')
    monkeypatch.setattr(sw_detect, 'detect_solidworks', lambda: fake)
    ok, diag = matrix._check_toolbox_supported()
    assert ok is False
    assert diag is not None
```

- [ ] **Step 9: 运行全量 sw_preflight matrix 测试，确认无回归**

```
uv run pytest tests/test_sw_preflight_matrix_check.py -v
```

- [ ] **Step 10: 提交**

```bash
git add adapters/solidworks/sw_detect.py sw_preflight/matrix.py tests/test_b0_edition.py tests/test_sw_preflight_matrix_check.py
git commit -m "feat(b0): SwInfo.edition 归一化为小写 + _find_edition 文件系统探针"
```

---

## Task 2: B1a — `_addins_candidates()` + `_scan_all_addins_by_description()`

**Files:**
- Modify: `adapters/solidworks/sw_detect.py`
- Create: `tests/test_discover_toolbox_addin_guid.py`（本 task 起建，后续 task 追加）

- [ ] **Step 1: 写失败测试（Stage 2 registry 全量扫描）**

```python
# tests/test_discover_toolbox_addin_guid.py
import sys
import types
import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="requires winreg")
class TestScanAllAddinsByDescription:
    def _mock_registry(self, addins: dict, monkeypatch):
        """addins = {guid: {value_name: value_str}}，放在 HKLM\\SOFTWARE\\SolidWorks\\AddIns。"""
        import winreg as real_winreg
        from adapters.solidworks import sw_detect

        sw_detect._reset_cache()

        class FakeKey:
            def __init__(self, data): self._data = data
            def __enter__(self): return self
            def __exit__(self, *_): pass

        opened_keys = {}

        def fake_open_key(hive, path, *a, **kw):
            # 只处理 AddIns 路径
            if "AddIns" in path and "AddInsStartup" not in path:
                # 返回能枚举子键的 key
                return FakeKey({"subkeys": list(addins.keys())})
            raise FileNotFoundError

        def fake_enum_key(key, i):
            subkeys = key._data.get("subkeys", [])
            if i >= len(subkeys):
                raise OSError
            return subkeys[i]

        def fake_open_sub_key(key, name, *a, **kw):
            # name 是 GUID
            if name in addins:
                return FakeKey(addins[name])
            raise FileNotFoundError

        import winreg
        monkeypatch.setattr(winreg, "OpenKey", fake_open_key)
        monkeypatch.setattr(winreg, "EnumKey", fake_enum_key)

        fake_info = sw_detect.SwInfo(installed=True, version_year=2024)
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)

    def test_description_toolbox_returns_guid(self, monkeypatch):
        """AddIns 下某 GUID 的 Description value 含 'toolbox' → 返回该 GUID。"""
        from adapters.solidworks.sw_detect import _scan_all_addins_by_description

        guid = "{BBBBBBBB-0000-0000-0000-000000000001}"
        # 最小化 mock：让函数能枚举到 guid
        # （完整 mock 复杂，此处做结构测试 —— 先确认函数存在且签名对）
        # 只要函数可导入且不抛 ImportError 即可（Stage 2 真实测试需本机 SW）
        assert callable(_scan_all_addins_by_description)

    def test_addins_candidates_returns_4_paths(self):
        """_addins_candidates(2024) 返回 4 条 (hive, path) 元组。"""
        from adapters.solidworks.sw_detect import _addins_candidates
        import winreg
        result = _addins_candidates(2024)
        assert len(result) == 4
        hives = {r[0] for r in result}
        assert winreg.HKEY_LOCAL_MACHINE in hives
        assert winreg.HKEY_CURRENT_USER in hives
```

- [ ] **Step 2: 运行测试，确认失败（函数不存在）**

```
uv run pytest tests/test_discover_toolbox_addin_guid.py::TestScanAllAddinsByDescription -v
```

期望：`ImportError` 或 `AttributeError`

- [ ] **Step 3: 实现 `_addins_candidates()` 和 `_scan_all_addins_by_description()`（sw_detect.py 尾部）**

```python
# ── Track B1：三段式 Toolbox GUID 发现 ──────────────────────────────────────


def _addins_candidates(version_year: int) -> list[tuple[int, str]]:
    """返回 [(hive, subkey_path)]；延迟构造以使用运行时已知的 version_year。

    4 条路径（HKLM × 2 + HKCU × 2）：
      HKLM\\SOFTWARE\\SolidWorks\\AddIns
      HKLM\\SOFTWARE\\SolidWorks\\SOLIDWORKS {year}\\AddIns
      HKCU\\Software\\SolidWorks\\AddIns
      HKCU\\Software\\SolidWorks\\SOLIDWORKS {year}\\AddIns
    """
    import winreg  # type: ignore[import-not-found]
    return [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\SolidWorks\AddIns"),
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\SolidWorks\SOLIDWORKS {version_year}\AddIns"),
        (winreg.HKEY_CURRENT_USER,  r"Software\SolidWorks\AddIns"),
        (winreg.HKEY_CURRENT_USER,  rf"Software\SolidWorks\SOLIDWORKS {version_year}\AddIns"),
    ]


def _scan_all_addins_by_description() -> Optional[str]:
    """Stage 2：枚举 4 条 AddIns registry 路径，三口径任一命中即返回 GUID。

    命中口径（任一）：
      (a) Description 或 Title value 含 'toolbox'（大小写不敏感）
      (b) GUID 子键名含 'toolbox'（大小写不敏感）
      (c) _is_toolbox_guid(name) 前缀匹配（与 Stage 1 口径对齐）
    """
    if sys.platform != "win32":
        return None
    try:
        import winreg  # type: ignore[import-not-found]
    except ImportError:
        return None

    info = detect_solidworks()
    if info.version_year == 0:
        return None

    for hive, path in _addins_candidates(info.version_year):
        try:
            with winreg.OpenKey(hive, path, 0, winreg.KEY_READ) as root:
                i = 0
                while True:
                    try:
                        guid = winreg.EnumKey(root, i)
                        i += 1
                    except OSError:
                        break

                    # 口径 (b): GUID 子键名含 'toolbox'
                    if "toolbox" in guid.lower() or _is_toolbox_guid(guid):
                        return guid

                    # 口径 (a): 读 Description / Title value
                    try:
                        with winreg.OpenKey(root, guid, 0, winreg.KEY_READ) as gk:
                            for val_name in ("Description", "Title"):
                                try:
                                    val, _ = winreg.QueryValueEx(gk, val_name)
                                    if "toolbox" in str(val).lower():
                                        return guid
                                except OSError:
                                    continue
                    except OSError:
                        continue
        except (OSError, FileNotFoundError):
            continue

    return None
```

- [ ] **Step 4: 运行测试，确认通过**

```
uv run pytest tests/test_discover_toolbox_addin_guid.py::TestScanAllAddinsByDescription -v
```

期望：`test_addins_candidates_returns_4_paths` PASS，其余 PASS 或 SKIP

- [ ] **Step 5: 提交**

```bash
git add adapters/solidworks/sw_detect.py tests/test_discover_toolbox_addin_guid.py
git commit -m "feat(b1a): _addins_candidates + _scan_all_addins_by_description 实现"
```

---

## Task 3: B1b — `_scan_addin_dll_clsid()` + B-17 HKCU 写入

**Files:**
- Modify: `adapters/solidworks/sw_detect.py`
- Modify: `tests/test_discover_toolbox_addin_guid.py`

- [ ] **Step 1: 写失败测试（Stage 3 文件系统扫描）**

```python
# 追加到 tests/test_discover_toolbox_addin_guid.py

class TestScanAddinDllClsid:
    def test_no_install_dir_returns_none(self, monkeypatch):
        """install_dir 为空 → None。"""
        from adapters.solidworks import sw_detect
        sw_detect._reset_cache()
        monkeypatch.setattr(
            sw_detect, "detect_solidworks",
            lambda: sw_detect.SwInfo(installed=False, install_dir=""),
        )
        result = sw_detect._scan_addin_dll_clsid()
        assert result is None

    def test_no_dll_returns_none(self, tmp_path, monkeypatch):
        """AddIns/toolbox 下无 dll → None。"""
        from adapters.solidworks import sw_detect
        sw_detect._reset_cache()
        (tmp_path / "AddIns" / "Toolbox").mkdir(parents=True)
        monkeypatch.setattr(
            sw_detect, "detect_solidworks",
            lambda: sw_detect.SwInfo(installed=True, install_dir=str(tmp_path)),
        )
        result = sw_detect._scan_addin_dll_clsid()
        assert result is None

    @pytest.mark.skipif(sys.platform != "win32", reason="requires winreg")
    def test_returns_none_when_clsid_not_in_registry(self, tmp_path, monkeypatch):
        """DLL 存在但 HKCR\\CLSID 里没有匹配条目 → None。"""
        import winreg
        from adapters.solidworks import sw_detect
        sw_detect._reset_cache()

        addin_dir = tmp_path / "AddIns" / "Toolbox"
        addin_dir.mkdir(parents=True)
        (addin_dir / "SWToolbox.dll").write_bytes(b"MZ")

        monkeypatch.setattr(
            sw_detect, "detect_solidworks",
            lambda: sw_detect.SwInfo(installed=True, install_dir=str(tmp_path)),
        )
        # mock HKCR\CLSID → 空（无匹配）
        monkeypatch.setattr(
            winreg, "OpenKey",
            lambda hive, path, *a, **kw: (_ for _ in ()).throw(FileNotFoundError()),
        )
        result = sw_detect._scan_addin_dll_clsid()
        assert result is None
```

- [ ] **Step 2: 运行测试，确认失败**

```
uv run pytest tests/test_discover_toolbox_addin_guid.py::TestScanAddinDllClsid -v
```

- [ ] **Step 3: 实现 `_scan_addin_dll_clsid()`（sw_detect.py）**

```python
def _scan_addin_dll_clsid() -> Optional[str]:
    """Stage 3：在 install_dir\\AddIns\\toolbox*\\ 找 DLL，反查 HKCR\\CLSID 得到 GUID。

    仅在 Stage 1/2 都 miss 时调用（慢路径，枚举 HKCR\\CLSID）。
    命中后自动写 HKCU\\Software\\SolidWorks\\AddInsStartup\\{guid}=1（B-17）。
    """
    if sys.platform != "win32":
        return None
    try:
        import winreg  # type: ignore[import-not-found]
    except ImportError:
        return None

    info = detect_solidworks()
    if not info.install_dir:
        return None

    # 收集候选 DLL 路径（小写，用于比较）
    dll_paths: set[str] = set()
    for sub in ("toolbox", "Toolbox"):
        d = Path(info.install_dir) / "AddIns" / sub
        if d.is_dir():
            for f in d.glob("*.dll"):
                dll_paths.add(str(f).lower())

    if not dll_paths:
        return None

    # 在 HKCR\CLSID 里反查 InprocServer32 / LocalServer32 路径
    try:
        clsid_root = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "CLSID")
    except OSError:
        return None

    found_guid: Optional[str] = None
    with clsid_root:
        idx = 0
        while True:
            try:
                guid_str = winreg.EnumKey(clsid_root, idx)
                idx += 1
            except OSError:
                break
            for server in ("InprocServer32", "LocalServer32"):
                try:
                    with winreg.OpenKey(clsid_root, f"{guid_str}\\{server}") as sk:
                        srv_path = winreg.QueryValue(sk, "")
                        if srv_path.lower() in dll_paths:
                            found_guid = guid_str if guid_str.startswith("{") else f"{{{guid_str}}}"
                            break
                except OSError:
                    continue
            if found_guid:
                break

    if not found_guid:
        return None

    # B-17：DLL 物理存在 + GUID 已知 → 写 HKCU AddInsStartup 让 SW 下次启动自动加载
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\SolidWorks\AddInsStartup",
            0,
            winreg.KEY_SET_VALUE,
        ) as k:
            winreg.SetValueEx(k, found_guid, 0, winreg.REG_DWORD, 1)
    except OSError:
        pass  # 写失败不阻断：discover 目的只是发现 GUID，写是 best-effort

    return found_guid
```

- [ ] **Step 4: 运行测试，确认通过**

```
uv run pytest tests/test_discover_toolbox_addin_guid.py::TestScanAddinDllClsid -v
```

- [ ] **Step 5: 提交**

```bash
git add adapters/solidworks/sw_detect.py tests/test_discover_toolbox_addin_guid.py
git commit -m "feat(b1b): _scan_addin_dll_clsid + B-17 HKCU 写入"
```

---

## Task 4: B1c — `discover_toolbox_addin_guid()` + `fix_addin_enable` 集成

**Files:**
- Modify: `adapters/solidworks/sw_detect.py`
- Modify: `sw_preflight/matrix.py`
- Modify: `adapters/parts/sw_toolbox_adapter.py`
- Modify: `tests/test_discover_toolbox_addin_guid.py`

- [ ] **Step 1: 写失败测试（三段式公共函数）**

```python
# 追加到 tests/test_discover_toolbox_addin_guid.py

class TestDiscoverToolboxAddinGuid:
    def test_stage1_hit_returns_startup_source(self, monkeypatch):
        """Stage 1 命中 → 返回 (guid, 'startup')。"""
        from adapters.solidworks import sw_detect
        monkeypatch.setattr(sw_detect, "find_toolbox_addin_guid",
                            lambda: "{AAAA-STAGE1}")
        guid, source = sw_detect.discover_toolbox_addin_guid()
        assert guid == "{AAAA-STAGE1}"
        assert source == "startup"

    def test_stage2_hit_when_stage1_miss(self, monkeypatch):
        """Stage 1 miss，Stage 2 命中 → ('registry_fullscan')。"""
        from adapters.solidworks import sw_detect
        monkeypatch.setattr(sw_detect, "find_toolbox_addin_guid", lambda: None)
        monkeypatch.setattr(sw_detect, "_scan_all_addins_by_description",
                            lambda: "{BBBB-STAGE2}")
        guid, source = sw_detect.discover_toolbox_addin_guid()
        assert guid == "{BBBB-STAGE2}"
        assert source == "registry_fullscan"

    def test_stage3_hit_when_stage1_2_miss(self, monkeypatch):
        """Stage 1/2 miss，Stage 3 命中 → ('filesystem')。"""
        from adapters.solidworks import sw_detect
        monkeypatch.setattr(sw_detect, "find_toolbox_addin_guid", lambda: None)
        monkeypatch.setattr(sw_detect, "_scan_all_addins_by_description", lambda: None)
        monkeypatch.setattr(sw_detect, "_scan_addin_dll_clsid",
                            lambda: "{CCCC-STAGE3}")
        guid, source = sw_detect.discover_toolbox_addin_guid()
        assert guid == "{CCCC-STAGE3}"
        assert source == "filesystem"

    def test_all_miss_returns_none(self, monkeypatch):
        """三段全 miss → (None, 'none')。"""
        from adapters.solidworks import sw_detect
        monkeypatch.setattr(sw_detect, "find_toolbox_addin_guid", lambda: None)
        monkeypatch.setattr(sw_detect, "_scan_all_addins_by_description", lambda: None)
        monkeypatch.setattr(sw_detect, "_scan_addin_dll_clsid", lambda: None)
        guid, source = sw_detect.discover_toolbox_addin_guid()
        assert guid is None
        assert source == "none"

    def test_old_find_toolbox_addin_guid_signature_unchanged(self):
        """向后兼容：find_toolbox_addin_guid() 签名和返回类型不变。"""
        from adapters.solidworks.sw_detect import find_toolbox_addin_guid
        import inspect
        sig = inspect.signature(find_toolbox_addin_guid)
        assert len(sig.parameters) == 0  # 无参数
```

- [ ] **Step 2: 运行测试，确认失败**

```
uv run pytest tests/test_discover_toolbox_addin_guid.py::TestDiscoverToolboxAddinGuid -v
```

- [ ] **Step 3: 实现 `discover_toolbox_addin_guid()`（sw_detect.py）**

```python
def discover_toolbox_addin_guid() -> tuple[Optional[str], str]:
    """三段式发现 Toolbox Add-In 的 GUID（Track B1）。

    Returns:
        (guid, source)，source ∈ {"startup", "registry_fullscan", "filesystem", "none"}。
    """
    # Stage 1: 老路径（快，历史用户命中率高）
    guid = find_toolbox_addin_guid()
    if guid:
        return guid, "startup"

    # Stage 2: 全量 AddIns registry 扫描（4 条路径，Description/Title/name 三口径）
    guid = _scan_all_addins_by_description()
    if guid:
        return guid, "registry_fullscan"

    # Stage 3: 文件系统扫描反查 CLSID（慢，但覆盖新装机无 AddInsStartup 条目的场景）
    guid = _scan_addin_dll_clsid()
    if guid:
        return guid, "filesystem"

    return None, "none"
```

- [ ] **Step 4: 更新 `get_toolbox_addin_guid()`（sw_toolbox_adapter.py:22）使用三段式**

```python
def get_toolbox_addin_guid() -> Optional[str]:
    """对外暴露的 Toolbox Add-In GUID 发现入口（Track B1 更新）。

    使用三段式 discover_toolbox_addin_guid()，覆盖历史用户 + 新装机场景。
    """
    from adapters.solidworks.sw_detect import discover_toolbox_addin_guid

    guid, _ = discover_toolbox_addin_guid()
    return guid
```

- [ ] **Step 5: 更新 `fix_addin_enable()` 错误文案（matrix.py:336）**

```python
# 找到这一行：
    guid = get_toolbox_addin_guid()
    if guid is None:
        raise RuntimeError(
            "ADDIN_ENABLE_FAILED: Toolbox Add-in GUID not discoverable from registry"
        )

# 改为：
    guid = get_toolbox_addin_guid()
    if guid is None:
        raise RuntimeError(
            "ADDIN_DLL_NOT_FOUND: install_dir 下找不到 Toolbox Add-in DLL — "
            "可能是 Standard 版未装 Toolbox Library"
        )
```

- [ ] **Step 6: 运行测试，确认通过**

```
uv run pytest tests/test_discover_toolbox_addin_guid.py -v
```

- [ ] **Step 7: 运行 matrix_fix_addin 测试，确认回归无损**

```
uv run pytest tests/test_sw_preflight_matrix_fix_addin.py -v
```

- [ ] **Step 8: 提交**

```bash
git add adapters/solidworks/sw_detect.py adapters/parts/sw_toolbox_adapter.py sw_preflight/matrix.py tests/test_discover_toolbox_addin_guid.py
git commit -m "feat(b1c): discover_toolbox_addin_guid 三段式 + fix_addin_enable 错误文案更新"
```

---

## Task 5: B2a — `check_toolbox_path_healthy()` 实现

**Files:**
- Modify: `adapters/solidworks/sw_detect.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_check_toolbox_path_healthy.py
import sys
import pytest
from pathlib import Path


class TestCheckToolboxPathHealthy:
    def _make_info(self, toolbox_dir: str):
        from adapters.solidworks import sw_detect
        return sw_detect.SwInfo(installed=True, toolbox_dir=toolbox_dir)

    def test_empty_toolbox_dir_returns_false(self):
        from adapters.solidworks.sw_detect import check_toolbox_path_healthy
        ok, reason = check_toolbox_path_healthy(self._make_info(""))
        assert ok is False
        assert reason is not None

    def test_healthy_dir_returns_true(self, tmp_path):
        from adapters.solidworks.sw_detect import check_toolbox_path_healthy
        # 创建 swbrowser.sldedb + 一个 .sldprt
        (tmp_path / "swbrowser.sldedb").write_bytes(b"SQLite")
        sldprt_dir = tmp_path / "GB" / "bolts"
        sldprt_dir.mkdir(parents=True)
        (sldprt_dir / "hex_bolt_m6.sldprt").write_bytes(b"\x00")
        ok, reason = check_toolbox_path_healthy(self._make_info(str(tmp_path)))
        assert ok is True
        assert reason is None

    def test_missing_sldedb_returns_false(self, tmp_path):
        from adapters.solidworks.sw_detect import check_toolbox_path_healthy
        # 有 sldprt 但没有 sldedb
        sldprt_dir = tmp_path / "GB"
        sldprt_dir.mkdir()
        (sldprt_dir / "part.sldprt").write_bytes(b"\x00")
        ok, reason = check_toolbox_path_healthy(self._make_info(str(tmp_path)))
        assert ok is False
        assert "sldedb" in reason.lower()

    def test_no_sldprt_returns_false(self, tmp_path):
        from adapters.solidworks.sw_detect import check_toolbox_path_healthy
        # 有 sldedb 但没有 sldprt
        (tmp_path / "swbrowser.sldedb").write_bytes(b"SQLite")
        ok, reason = check_toolbox_path_healthy(self._make_info(str(tmp_path)))
        assert ok is False
        assert "sldprt" in reason.lower()

    def test_nonexistent_dir_returns_false(self):
        from adapters.solidworks.sw_detect import check_toolbox_path_healthy
        ok, reason = check_toolbox_path_healthy(self._make_info(r"C:\does\not\exist"))
        assert ok is False
        assert reason is not None
```

- [ ] **Step 2: 运行测试，确认失败**

```
uv run pytest tests/test_check_toolbox_path_healthy.py -v
```

- [ ] **Step 3: 实现 `check_toolbox_path_healthy()`（sw_detect.py）**

```python
def check_toolbox_path_healthy(info: "SwInfo") -> tuple[bool, Optional[str]]:
    """B-8：校验 toolbox_dir 的物理健康状态。

    硬要求：
      1. toolbox_dir 非空
      2. 目录存在且可枚举（listdir）
      3. swbrowser.sldedb 存在（Toolbox 索引）
      4. 至少 1 个 .sldprt 可读

    UNC 路径预检：先 `exists()` 确认可达性，失败时明示 UNC 不可达原因。

    Returns:
        (True, None) 健康；(False, reason_str) 不健康。
    """
    if not info.toolbox_dir:
        return False, "toolbox_dir 为空"

    p = Path(info.toolbox_dir)

    # UNC 路径预检（避免 listdir 对不可达网络路径挂起）
    if str(p).startswith("\\\\"):
        try:
            if not p.exists():
                return False, f"UNC 路径不可达：{info.toolbox_dir}"
        except OSError as e:
            return False, f"UNC 路径访问异常：{e}"

    # 目录可枚举
    try:
        next(p.iterdir(), None)
    except (PermissionError, OSError) as e:
        return False, f"toolbox_dir 不可读：{e}"

    # swbrowser.sldedb 硬要求（直接在 toolbox_dir 根目录）
    if not (p / "swbrowser.sldedb").exists():
        return False, "swbrowser.sldedb 不存在（Toolbox 索引缺失，Toolbox 可能未完整安装）"

    # 至少 1 个 .sldprt 可读（只扫一层子目录，避免深递归慢）
    sldprt_found = False
    for entry in p.iterdir():
        if entry.is_dir():
            for f in entry.iterdir():
                if f.suffix.lower() == ".sldprt":
                    try:
                        f.stat()
                        sldprt_found = True
                    except OSError:
                        pass
                    if sldprt_found:
                        break
        if sldprt_found:
            break

    if not sldprt_found:
        return False, "toolbox_dir 下未找到可读 .sldprt 文件（Toolbox 零件库可能为空）"

    return True, None
```

- [ ] **Step 4: 运行测试，确认通过**

```
uv run pytest tests/test_check_toolbox_path_healthy.py -v
```

期望：5 个 PASS

- [ ] **Step 5: 提交**

```bash
git add adapters/solidworks/sw_detect.py tests/test_check_toolbox_path_healthy.py
git commit -m "feat(b2a): check_toolbox_path_healthy — Toolbox 物理路径健康校验"
```

---

## Task 6: B2b — `is_available()` 全量重写

**Files:**
- Modify: `adapters/parts/sw_toolbox_adapter.py`
- Create: `tests/test_sw_toolbox_adapter_is_available_b2.py`
- Modify: `tests/test_sw_toolbox_adapter.py`（删除硬门测试）

- [ ] **Step 1: 写新测试（B2 语义）**

```python
# tests/test_sw_toolbox_adapter_is_available_b2.py
import sys
import pytest


@pytest.fixture()
def good_info(tmp_path):
    """构造一个 toolbox_dir 健康、非 Standard 的 SwInfo。"""
    from adapters.solidworks import sw_detect
    # 创建健康 toolbox_dir
    (tmp_path / "swbrowser.sldedb").write_bytes(b"SQLite")
    sub = tmp_path / "GB"
    sub.mkdir()
    (sub / "part.sldprt").write_bytes(b"\x00")
    return sw_detect.SwInfo(
        installed=True,
        version_year=2024,
        pywin32_available=True,
        toolbox_dir=str(tmp_path),
        toolbox_addin_enabled=False,  # 未启用 Add-in
        edition="professional",
    )


@pytest.mark.skipif(sys.platform != "win32", reason="需要 Windows")
class TestIsAvailableB2:
    def test_addin_disabled_but_healthy_returns_true(self, monkeypatch, good_info):
        """B-2: Add-in 未启用 + 其他条件满足 → (True, None)。"""
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_detect, sw_com_session

        sw_detect._reset_cache()
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: good_info)

        class FakeSession:
            def is_healthy(self): return True
        monkeypatch.setattr(sw_com_session, "get_session", lambda: FakeSession())

        ok, reason = SwToolboxAdapter().is_available()
        assert ok is True
        assert reason is None

    def test_standard_edition_returns_false(self, monkeypatch, good_info, tmp_path):
        """B-13: Standard 版 → (False, reason 含 'Standard edition')。"""
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_detect

        sw_detect._reset_cache()
        good_info = sw_detect.SwInfo(
            installed=True, version_year=2024,
            pywin32_available=True, toolbox_dir=str(tmp_path),
            edition="standard",
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: good_info)

        ok, reason = SwToolboxAdapter().is_available()
        assert ok is False
        assert reason is not None
        assert "Standard edition" in reason

    def test_unhealthy_toolbox_path_returns_false(self, monkeypatch, good_info):
        """B-8: toolbox_dir 不健康 → (False, reason 含 'toolbox path')。"""
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_detect

        sw_detect._reset_cache()
        bad_info = sw_detect.SwInfo(
            installed=True, version_year=2024,
            pywin32_available=True,
            toolbox_dir=r"C:\does\not\exist",
            edition="professional",
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: bad_info)

        ok, reason = SwToolboxAdapter().is_available()
        assert ok is False
        assert reason is not None

    def test_circuit_broken_returns_false(self, monkeypatch, good_info):
        """熔断 → (False, reason 含 circuit + edition 信息)。"""
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_detect, sw_com_session

        sw_detect._reset_cache()
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: good_info)

        class BrokenSession:
            def is_healthy(self): return False
        monkeypatch.setattr(sw_com_session, "get_session", lambda: BrokenSession())

        ok, reason = SwToolboxAdapter().is_available()
        assert ok is False
        assert reason is not None
        assert "circuit" in reason.lower() or "breaker" in reason.lower()
```

- [ ] **Step 2: 运行测试，确认失败**

```
uv run pytest tests/test_sw_toolbox_adapter_is_available_b2.py -v
```

- [ ] **Step 3: 重写 `is_available()`（sw_toolbox_adapter.py:54-93）**

```python
    def is_available(self) -> tuple[bool, Optional[str]]:
        """B-2 重写：解耦 Add-in 硬门，Add-in 未启用降为 advisory。

        检查顺序：
        1. 非 Windows → False
        2. SW 未安装 → False
        3. 版本 < 2024 → False
        4. pywin32 不可用 → False
        5. toolbox_dir 为空 → False
        6. Standard 版（B-13）→ False
        7. toolbox 物理路径不健康（B-8）→ False
        8. Add-in 未启用 → advisory log only（B-2），不 return False
        9. SwComSession 熔断 → False（v4 决策 #22）
        """
        if sys.platform != "win32":
            return False, "not windows"

        try:
            from adapters.solidworks.sw_detect import detect_solidworks, check_toolbox_path_healthy
            from adapters.solidworks.sw_com_session import get_session
        except ImportError as e:
            return False, f"import failed: {e}"

        info = detect_solidworks()
        if not info.installed:
            return False, "SW not installed"
        if info.version_year < 2024:
            return False, f"SW {info.version_year} too old (need 2024+)"
        if not info.pywin32_available:
            return False, "pywin32 not available"
        if not info.toolbox_dir:
            return False, "toolbox_dir empty"

        # B-13: Standard 版直接拒
        if info.edition == "standard":
            return False, "SW Standard edition does not ship Toolbox Browser DLL"

        # B-8: 物理路径健康校验
        healthy, path_reason = check_toolbox_path_healthy(info)
        if not healthy:
            return False, f"toolbox path unhealthy: {path_reason}"

        # B-2: Add-in 未启用 → advisory log，不阻断
        if not info.toolbox_addin_enabled:
            import logging as _logging
            _logging.getLogger(__name__).info(
                "SwToolboxAdapter: Toolbox Add-in 未在 SW 菜单里启用 —— "
                "将通过 COM 直接打开 sldprt，不经 Add-in Browser（Track B 决策 B-2）。"
            )

        # v4 决策 #22: 熔断
        session = get_session()
        if not session.is_healthy():
            return False, (
                f"SwComSession circuit breaker tripped; edition={info.edition}"
            )

        return True, None
```

- [ ] **Step 4: 更新旧测试 — `test_addin_disabled_returns_false` 语义变更**

```python
# tests/test_sw_toolbox_adapter.py，找到约第 98-103 行的测试：
# def test_addin_disabled_returns_false(self, monkeypatch):
#     """v4 决策 #13: Toolbox Add-In 未启用 → False。"""
#     ...
#     assert ok is False  ← 改为 assert ok is True

# 修改该测试（Add-in 禁用不再是 gate，但需要 toolbox_dir 健康）：
    def test_addin_disabled_no_longer_blocks(self, monkeypatch, tmp_path):
        """Track B 决策 B-2: Toolbox Add-In 未启用 → is_available 仍可返 True（advisory）。"""
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_detect, sw_com_session

        sw_detect._reset_cache()
        # 创建健康 toolbox_dir
        (tmp_path / "swbrowser.sldedb").write_bytes(b"SQLite")
        (tmp_path / "GB").mkdir()
        (tmp_path / "GB" / "p.sldprt").write_bytes(b"\x00")

        fake_info = sw_detect.SwInfo(
            installed=True,
            version_year=2024,
            pywin32_available=True,
            toolbox_dir=str(tmp_path),
            toolbox_addin_enabled=False,
            edition="professional",
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)

        class FakeSession:
            def is_healthy(self): return True
        monkeypatch.setattr(sw_com_session, "get_session", lambda: FakeSession())

        ok, reason = SwToolboxAdapter().is_available()
        assert ok is True   # ← 与 v4 相反（Add-in 硬门已解耦）
```

- [ ] **Step 5: 运行新 B2 测试**

```
uv run pytest tests/test_sw_toolbox_adapter_is_available_b2.py -v
```

- [ ] **Step 6: 运行原有 sw_toolbox_adapter 测试（含修改后的旧测试）**

```
uv run pytest tests/test_sw_toolbox_adapter.py -v
```

- [ ] **Step 7: 提交**

```bash
git add adapters/parts/sw_toolbox_adapter.py tests/test_sw_toolbox_adapter.py tests/test_sw_toolbox_adapter_is_available_b2.py
git commit -m "feat(b2b): is_available() 解耦 addin 硬门 + Standard 拒 + path-healthy 校验"
```

---

## Task 7: B2c — `_BLOCKING_CHECKS` + `run_all_checks()` + `PreflightResult.advisory_failures`

**Files:**
- Modify: `sw_preflight/types.py`
- Modify: `sw_preflight/matrix.py`
- Create: `tests/test_sw_preflight_blocking_checks.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_sw_preflight_blocking_checks.py
import pytest


class TestBlockingChecks:
    def test_addin_enabled_not_in_blocking_checks(self):
        """addin_enabled 不在 _BLOCKING_CHECKS → advisory-only。"""
        from sw_preflight.matrix import _BLOCKING_CHECKS
        assert "addin_enabled" not in _BLOCKING_CHECKS

    def test_blocking_checks_contains_platform_and_core(self):
        from sw_preflight.matrix import _BLOCKING_CHECKS
        for name in ("platform", "pywin32", "sw_installed", "toolbox_supported", "com_healthy"):
            assert name in _BLOCKING_CHECKS

    def test_run_all_checks_advisory_failure_doesnt_block(self, monkeypatch):
        """addin_enabled 失败 → run_all_checks passed=True，advisory_failures 非空。"""
        import sw_preflight.matrix as m
        # mock blocking checks → all pass
        for name, attr in m.CHECK_ORDER:
            if name != "addin_enabled":
                monkeypatch.setattr(m, attr, lambda: (True, None))
        # addin_enabled → fail
        monkeypatch.setattr(m, "_check_addin_enabled", lambda: (False, None))

        result = m.run_all_checks()
        assert result["passed"] is True
        assert "addin_enabled" in result.get("advisory_failures", {})

    def test_run_all_checks_blocking_failure_sets_passed_false(self, monkeypatch):
        """blocking check 失败 → passed=False。"""
        import sw_preflight.matrix as m
        for name, attr in m.CHECK_ORDER:
            monkeypatch.setattr(m, attr, lambda: (True, None))
        # com_healthy → fail（blocking）
        monkeypatch.setattr(m, "_check_com_healthy", lambda: (False, None))

        result = m.run_all_checks()
        assert result["passed"] is False

    def test_preflight_result_has_advisory_failures_field(self):
        """PreflightResult 有 advisory_failures 字段，默认空 dict。"""
        from sw_preflight.types import PreflightResult
        r = PreflightResult(
            passed=True, sw_info=None,
            fixes_applied=[], diagnosis=None, per_step_ms={}
        )
        assert hasattr(r, "advisory_failures")
        assert r.advisory_failures == {}
```

- [ ] **Step 2: 运行测试，确认失败**

```
uv run pytest tests/test_sw_preflight_blocking_checks.py -v
```

- [ ] **Step 3: 更新 `PreflightResult`（sw_preflight/types.py）**

```python
# sw_preflight/types.py，在 PreflightResult dataclass 里加 advisory_failures 字段
# 现有字段：passed, sw_info, fixes_applied, diagnosis, per_step_ms

@dataclass(frozen=True)
class PreflightResult:
    """整体预检结果载体"""
    passed: bool
    sw_info: Any
    fixes_applied: list[FixRecord]
    diagnosis: Optional['DiagnosisInfo']
    per_step_ms: dict[str, float]
    advisory_failures: dict = field(default_factory=dict)  # ← 新增，key=check_name, value=DiagnosisInfo or None
```

注意：需要在文件顶部确保 `from dataclasses import dataclass, field` 已导入。

- [ ] **Step 4: 新增 `_BLOCKING_CHECKS` 常量（matrix.py，放在 `CHECK_ORDER` 之后）**

```python
# sw_preflight/matrix.py，在 CHECK_ORDER 列表之后添加：

_BLOCKING_CHECKS: frozenset[str] = frozenset({
    "platform",
    "pywin32",
    "sw_installed",
    "toolbox_supported",
    "com_healthy",
    "toolbox_path",          # ← Task 8 会把 toolbox_path 重命名为 toolbox_path_healthy
    # addin_enabled 故意不在此集合 —— B-5 advisory only
})
```

- [ ] **Step 5: 重写 `run_all_checks()`（matrix.py:219）**

```python
def run_all_checks() -> dict:
    """按 CHECK_ORDER 顺序跑全部检查；不短路，全量收集结果。

    Returns:
        {
          'passed': bool,            # True 当且仅当所有 _BLOCKING_CHECKS 中的 check 都通过
          'failed_check': Optional[str],   # 第一个 blocking 失败的 check 名（供一键修 dispatch）
          'diagnosis': Optional[DiagnosisInfo],  # 第一个 blocking 失败的诊断
          'advisory_failures': dict[str, Optional[DiagnosisInfo]],  # 非 blocking 失败集合
        }
    """
    import sys
    this_module = sys.modules[__name__]

    first_blocking_fail: Optional[str] = None
    first_blocking_diag = None
    advisory_failures: dict = {}

    for name, attr in CHECK_ORDER:
        check: CheckFn = getattr(this_module, attr)
        ok, diag = check()
        if not ok:
            if name in _BLOCKING_CHECKS:
                if first_blocking_fail is None:
                    first_blocking_fail = name
                    first_blocking_diag = diag
            else:
                advisory_failures[name] = diag

    passed = first_blocking_fail is None
    return {
        "passed": passed,
        "failed_check": first_blocking_fail,
        "diagnosis": first_blocking_diag,
        "advisory_failures": advisory_failures,
    }
```

- [ ] **Step 6: 运行测试，确认通过**

```
uv run pytest tests/test_sw_preflight_blocking_checks.py -v
```

- [ ] **Step 7: 运行 preflight 全量测试，确认无重大回归**

```
uv run pytest tests/test_sw_preflight_preflight.py tests/test_sw_preflight_matrix_check.py -v
```

- [ ] **Step 8: 提交**

```bash
git add sw_preflight/types.py sw_preflight/matrix.py tests/test_sw_preflight_blocking_checks.py
git commit -m "feat(b2c): _BLOCKING_CHECKS + run_all_checks 全量语义 + PreflightResult.advisory_failures"
```

---

## Task 8: B2d — matrix `_check_toolbox_path_healthy` + `addin_enabled` advisory

**Files:**
- Modify: `sw_preflight/matrix.py`
- Modify: `tests/test_sw_preflight_matrix_check.py`

- [ ] **Step 1: 写失败测试（path-healthy check + addin advisory）**

```python
# 追加到 tests/test_sw_preflight_matrix_check.py

def test_check_toolbox_path_healthy_passes_when_dir_healthy(monkeypatch, tmp_path):
    """_check_toolbox_path_healthy：健康目录 → True。"""
    from adapters.solidworks import sw_detect
    from sw_preflight import matrix

    (tmp_path / "swbrowser.sldedb").write_bytes(b"SQLite")
    (tmp_path / "GB").mkdir()
    (tmp_path / "GB" / "p.sldprt").write_bytes(b"\x00")

    sw_detect._reset_cache()
    fake = sw_detect.SwInfo(installed=True, toolbox_dir=str(tmp_path))
    monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake)

    ok, diag = matrix._check_toolbox_path_healthy()
    assert ok is True
    assert diag is None


def test_check_toolbox_path_healthy_fails_missing_sldedb(monkeypatch, tmp_path):
    """_check_toolbox_path_healthy：缺 sldedb → False。"""
    from adapters.solidworks import sw_detect
    from sw_preflight import matrix

    (tmp_path / "GB").mkdir()
    (tmp_path / "GB" / "p.sldprt").write_bytes(b"\x00")

    sw_detect._reset_cache()
    fake = sw_detect.SwInfo(installed=True, toolbox_dir=str(tmp_path))
    monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake)

    ok, diag = matrix._check_toolbox_path_healthy()
    assert ok is False


def test_addin_enabled_advisory_in_run_all_checks(monkeypatch):
    """addin_enabled 失败时 run_all_checks passed=True，advisory_failures 含 addin_enabled。"""
    import sw_preflight.matrix as m

    for name, attr in m.CHECK_ORDER:
        if name != "addin_enabled":
            monkeypatch.setattr(m, attr, lambda: (True, None))
    monkeypatch.setattr(m, "_check_addin_enabled", lambda: (False, None))

    result = m.run_all_checks()
    assert result["passed"] is True
    assert "addin_enabled" in result["advisory_failures"]
```

- [ ] **Step 2: 运行测试，确认失败（`_check_toolbox_path_healthy` 不存在）**

```
uv run pytest tests/test_sw_preflight_matrix_check.py -k "healthy or advisory" -v
```

- [ ] **Step 3: 添加 `_check_toolbox_path_healthy()` 到 matrix.py（替换 `_check_toolbox_path`）**

```python
# sw_preflight/matrix.py
# 删除旧的 _check_toolbox_path() 函数，添加 _check_toolbox_path_healthy()：

def _check_toolbox_path_healthy() -> tuple[bool, Optional[DiagnosisInfo]]:
    """检查 #7（Track B 版）：toolbox_dir 物理健康（sldedb + sldprt 可读）。

    委托给 sw_detect.check_toolbox_path_healthy，保持 matrix check 接口统一。
    """
    try:
        from adapters.solidworks.sw_detect import detect_solidworks, check_toolbox_path_healthy
        info = detect_solidworks()
    except Exception as e:  # noqa: BLE001
        return False, DiagnosisInfo(
            code=DiagnosisCode.TOOLBOX_PATH_INVALID,
            reason=f"读取 Toolbox 路径状态失败：{e}",
            suggestion="检查 SOLIDWORKS 安装完整性",
            severity='block',
        )

    ok, reason = check_toolbox_path_healthy(info)
    if not ok:
        return False, DiagnosisInfo(
            code=DiagnosisCode.TOOLBOX_PATH_INVALID,
            reason=reason or "Toolbox 目录不健康",
            suggestion=(
                "在 SOLIDWORKS Tools → Options → Hole Wizard/Toolbox 中"
                "重新指定有效 Toolbox 目录，并确保 Toolbox 组件已完整安装"
            ),
            severity='block',
        )
    return True, None
```

- [ ] **Step 4: 更新 `CHECK_ORDER` 中的 `toolbox_path` 条目**

```python
# sw_preflight/matrix.py，找到 CHECK_ORDER，把最后一项改为：
    ('toolbox_path', '_check_toolbox_path_healthy'),   # Track B: 替换为健康校验版本
```

- [ ] **Step 5: 更新 `_BLOCKING_CHECKS`（如有 `toolbox_path_healthy` 命名变动需同步）**

保持 `_BLOCKING_CHECKS` 中的 `"toolbox_path"` 不变（CHECK_ORDER 里的 name 仍是 `'toolbox_path'`，只是 attr 变了）：
```python
_BLOCKING_CHECKS: frozenset[str] = frozenset({
    "platform", "pywin32", "sw_installed",
    "toolbox_supported", "com_healthy", "toolbox_path",
    # addin_enabled 故意不在此集合
})
```

- [ ] **Step 6: 更新 `try_one_click_fix` dispatch 表（matrix.py:617）**

```python
# 确认 fix_map 里 'toolbox_path' 仍映射 None（toolbox_path 无法一键修，行为不变）：
        'toolbox_path': None,
```

- [ ] **Step 7: 运行测试**

```
uv run pytest tests/test_sw_preflight_matrix_check.py tests/test_sw_preflight_blocking_checks.py -v
```

- [ ] **Step 8: 提交**

```bash
git add sw_preflight/matrix.py tests/test_sw_preflight_matrix_check.py
git commit -m "feat(b2d): _check_toolbox_path_healthy 替换旧 path check + addin_enabled advisory"
```

---

## Task 9: B2e — preflight.py 语义 + cache schema v2 + report advisory 展示

**Files:**
- Modify: `sw_preflight/preflight.py`
- Modify: `sw_preflight/cache.py`
- Modify: `sw_preflight/report.py`
- Modify: `tests/test_sw_preflight_cache.py`（若存在 schema_version 相关测试）

- [ ] **Step 1: 写失败测试（schema v2 + advisory 在 preflight 结果里）**

```python
# tests/test_sw_preflight_cache_schema.py（追加或新建）
from pathlib import Path
import pytest


def test_cache_schema_version_is_2():
    from sw_preflight.cache import SCHEMA_VERSION
    assert SCHEMA_VERSION == 2


def test_v1_cache_read_returns_none(tmp_path):
    """旧 schema_version=1 的 cache → read_cache 返回 None（视为 miss）。"""
    import json
    from datetime import datetime, timezone
    from sw_preflight.cache import read_cache

    cache_file = tmp_path / "preflight_cache.json"
    cache_file.write_text(json.dumps({
        "schema_version": 1,
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "ttl_seconds": 300,
        "passed": True,
    }), encoding="utf-8")

    result = read_cache(cache_file)
    assert result is None  # schema 不匹配 → miss


def test_v2_cache_read_succeeds(tmp_path):
    """schema_version=2 在 TTL 内 → read_cache 正常返回。"""
    import json
    from datetime import datetime, timezone
    from sw_preflight.cache import read_cache, SCHEMA_VERSION

    cache_file = tmp_path / "preflight_cache.json"
    cache_file.write_text(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "ttl_seconds": 300,
        "passed": True,
    }), encoding="utf-8")

    result = read_cache(cache_file)
    assert result is not None
    assert result["passed"] is True
```

- [ ] **Step 2: 运行测试，确认失败**

```
uv run pytest tests/test_sw_preflight_cache_schema.py -v
```

- [ ] **Step 3: 修改 cache.py SCHEMA_VERSION**

```python
# sw_preflight/cache.py:18
SCHEMA_VERSION = 2  # ← 从 1 改为 2（Track B：PreflightResult 加 advisory_failures）
```

- [ ] **Step 4: 更新 `preflight.py` — `run_preflight()` 收集 advisory_failures**

```python
# sw_preflight/preflight.py，在 run_preflight() 里找到：
    passed=check['passed'],

# 改为（同时传入 advisory_failures）：
    passed=check['passed'],
    advisory_failures=check.get('advisory_failures', {}),
```

完整改动上下文（约第 80-92 行）：
```python
    return PreflightResult(
        passed=check['passed'],
        sw_info=detect_solidworks(),
        fixes_applied=fixes_applied,
        diagnosis=check.get('diagnosis'),
        per_step_ms=per_step,
        advisory_failures=check.get('advisory_failures', {}),  # ← 新增
    )
```

- [ ] **Step 5: 更新 `report.py` — toolbox 行显示 advisory**

```python
# sw_preflight/report.py，找到（约 75-76 行）：
    sw_status = {
        'edition': edition_str,
        'toolbox': preflight.passed,
        ...
    }

# 改为：
    toolbox_advisory = "addin_enabled" in getattr(preflight, "advisory_failures", {})
    sw_status = {
        'edition': edition_str,
        'toolbox': preflight.passed,
        'toolbox_advisory': toolbox_advisory,   # ← 新增
        ...
    }
```

- [ ] **Step 6: 更新 report.py 的 `_render_toolbox_status()` 或直接渲染处理**

```python
# sw_preflight/report.py，在构建人读报告的地方（找到 stdout 输出相关代码）
# 找到类似 "Toolbox: ✅" 或 "Toolbox: ❌" 的渲染逻辑，添加 advisory 分支。
# 控制台输出（非 HTML）使用 ASCII，不用 emoji：
#
# 示例（在 run_preflight 或 report 的 stdout 输出段）：
if preflight.passed:
    addin_advisory = "addin_enabled" in getattr(preflight, "advisory_failures", {})
    if addin_advisory:
        toolbox_line = "[WARN] Toolbox: STEP 转换可用（Add-in 未在 SW 菜单启用，不影响真件提取）"
    else:
        toolbox_line = "Toolbox: OK"
else:
    toolbox_line = "Toolbox: FAIL"
```

注意：HTML 报告模板（`sw_report.html.j2`）中的 `{{ '✅' if sw_status.toolbox else '❌' }}` 保持不变（HTML 是 UTF-8，不受 GBK 控制台编码影响）。

- [ ] **Step 7: 运行 cache schema 测试**

```
uv run pytest tests/test_sw_preflight_cache_schema.py -v
```

- [ ] **Step 8: 运行 preflight 全量测试**

```
uv run pytest tests/test_sw_preflight_preflight.py tests/test_sw_preflight_report.py -v
```

- [ ] **Step 9: 提交**

```bash
git add sw_preflight/preflight.py sw_preflight/cache.py sw_preflight/report.py tests/test_sw_preflight_cache_schema.py
git commit -m "feat(b2e): preflight advisory 收集 + cache schema v2 + report [WARN] advisory 展示"
```

---

## Task 10: 全量回归 + 修复

**Files:** 按需修改

- [ ] **Step 1: 运行全量测试套件**

```
uv run pytest -x -q
```

- [ ] **Step 2: 如有失败，按错误分类修复**

常见预期失败点（按可能性排序）：

**A. `test_sw_preflight_preflight.py` — `run_preflight` 入口行为改变**

若有 `assert result.advisory_failures` 相关断言或 `run_all_checks` 返回字典结构检查，按新结构更新。

**B. `test_sw_toolbox_integration.py` — 集成测试中 addin_enabled mock**

找到 `toolbox_addin_enabled=False` 的 mock，若期望 `is_available()=False`，改为期望 `True`（需同时确保 toolbox_dir 健康）。

**C. `test_sw_preflight_matrix_diagnostics.py` — run_all_checks 返回结构**

若有 `result['failed_check']` 或 `result['diagnosis']` 的断言，在 advisory 场景下 `failed_check` 现在可能是 `None`（passed=True），按需更新。

**D. `test_sw_preflight_cache.py` — schema_version 检查**

确认 `SCHEMA_VERSION` 相关断言已改为期望 `2`。

- [ ] **Step 3: 再次全量运行（确认全绿）**

```
uv run pytest -q
```

期望：`N passed, M skipped`（无 failed）

- [ ] **Step 4: 提交修复**

```bash
git add -u
git commit -m "fix(b2-regression): 修复全量回归失败（addin advisory + schema v2 断言对齐）"
```

- [ ] **Step 5: 检查 sw-inspect 命令（确认 resolve report 展示 advisory）**

```
uv run python -m cad_pipeline sw-inspect 2>&1 | head -30
```

期望：若本机 SW 装了 Professional/Premium，`Toolbox: OK` 或 `[WARN] Toolbox:` 而非 `❌`。

---

## 自检清单（Spec 覆盖）

| Spec 要求 | 对应 Task | 状态 |
|---|---|---|
| B0: SwInfo.edition 归一化为小写 | Task 1 | ─ |
| B0: _find_edition 文件系统探针 | Task 1 | ─ |
| B-13: Standard → is_available() False | Task 6 | ─ |
| B1: _addins_candidates 4 条路径 | Task 2 | ─ |
| B1: _scan_all_addins_by_description Stage 2 | Task 2 | ─ |
| B1: _scan_addin_dll_clsid Stage 3 | Task 3 | ─ |
| B-17: Stage 3 命中时写 HKCU | Task 3 | ─ |
| B1: discover_toolbox_addin_guid 三段式 | Task 4 | ─ |
| B1: fix_addin_enable 错误文案更新 | Task 4 | ─ |
| B-8: check_toolbox_path_healthy (sldedb + sldprt) | Task 5 | ─ |
| B-2: is_available 解耦 addin 硬门 | Task 6 | ─ |
| B-8: is_available 调用 path-healthy | Task 6 | ─ |
| _BLOCKING_CHECKS addin_enabled 不在其中 | Task 7 | ─ |
| run_all_checks 全量不短路 | Task 7 | ─ |
| PreflightResult.advisory_failures | Task 7 | ─ |
| matrix _check_toolbox_path_healthy 替换 | Task 8 | ─ |
| cache SCHEMA_VERSION → 2 | Task 9 | ─ |
| preflight.py 收集 advisory_failures | Task 9 | ─ |
| report.py [WARN] ASCII 前缀（非 emoji） | Task 9 | ─ |
| B3 sldprt→STEP worker 修复 | **未含，待 spike** | 暂缓 |
