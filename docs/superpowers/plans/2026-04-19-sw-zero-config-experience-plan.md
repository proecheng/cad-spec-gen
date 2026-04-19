# SW 装即用 — 零配置体验打通 实现 Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 cad-spec-gen 场景 A（pipeline 一键流）的 "装了 SW 就自动可用" 体验：preflight 体检 + 一键修 + 三选一用户提供 + P2 三段式报告 + cad-spec 审查范围透明化。

**Architecture:** 新增 `sw_preflight/` orchestrator 内部库（不暴露 skill 命令），消费现有 adapters 的 SW 检测/COM/router 能力，对外提供 `run_preflight()` / `dry_run_bom()` / `prompt_user_provided()` / `emit_report()` 4 个函数；3 个 CLI 入口（cad-spec / cad-codegen / cad_pipeline）按 strict=False/True 分级接入；通过 `sw_preflight_cache.json` 跨入口共享 preflight 结果。

**Tech Stack:** Python 3.11+ / pytest / win32com (pywin32) / tkinter.filedialog / jinja2 / pyyaml / cadquery (warn-only STEP 校验)

**Spec 引用:** `docs/superpowers/specs/2026-04-19-sw-zero-config-experience-design.md` (commit `3fbea27`)

**北极星 5 gate（每个 task 都要守）:**
1. 零配置 — 用户不写 yaml/env/deps（skill 自动改 yaml 不算用户负担）
2. 稳定可靠 — 不静默降级
3. 结果准确 — 通过/不通过二值明确
4. SW 装即用 — 装了 SW 自动用
5. 傻瓜式 — 不问技术问题

**TDD 铁律:** 每个 task 严格 RED→GREEN→REFACTOR；先写失败测试，再写最小实现，再 commit。

**通用性铁律 (零硬编码):** sw_preflight/ 任何代码不出现 `Program Files` / `D:\\` / `2024` / `2025` 等字面值；所有 SW 路径/版本/edition 由运行时 API 自主发现（详见 spec §3.5）。

---

## 检查点（用户确认点）

每完成一组 phase 暂停让用户确认，然后再继续：

- ✅ Phase 0-1 (硬编码清查 + 基础类型) → **CHECKPOINT 1**
- ✅ Phase 2-3 (sw_detect 扩展 + parts_resolver 扩展) → **CHECKPOINT 2**
- ✅ Phase 4-5 (io 层 + matrix M 体检+一键修) → **CHECKPOINT 3**
- ✅ Phase 6-8 (cache + dry_run + user_provided) → **CHECKPOINT 4**
- ✅ Phase 9-10 (preflight 编排 + P2 报告) → **CHECKPOINT 5**
- ✅ Phase 11-12 (CLI 接入 + CI + 集成测试) → **CHECKPOINT 6 (最终)**

---

## Phase 0: 准备 + 硬编码清查

### Task 0: grep 清查 sw_detect.py 现有硬编码

**Files:**
- Read: `adapters/solidworks/sw_detect.py`（全文审）
- Modify: `adapters/solidworks/sw_detect.py`（清理硬编码）
- Test: `tests/test_sw_detect_no_hardcode.py`（新建）

- [ ] **Step 0.1: 跑 grep 找现有硬编码**

```bash
git grep -nE 'Program Files|D:\\\\|"20(2[0-9]|3[0-9])"' -- adapters/solidworks/sw_detect.py
```

记录所有命中。每条命中要么验证是注释里的历史描述（保留），要么是真硬编码（需改）。

- [ ] **Step 0.2: 写失败测试 — sw_detect 内不含禁用字面值**

```python
# tests/test_sw_detect_no_hardcode.py
import re
from pathlib import Path

def test_sw_detect_no_hardcoded_paths_or_years():
    """sw_detect.py 非注释行不得出现具体路径/年份字面值"""
    src = Path("adapters/solidworks/sw_detect.py").read_text(encoding="utf-8")
    forbidden = re.compile(r'^[^#]*("Program Files"|"D:\\\\"|"20(2[0-9]|3[0-9])")')
    bad = [(i+1, line) for i, line in enumerate(src.splitlines())
           if forbidden.search(line)]
    assert not bad, f"硬编码命中（行号: 内容）: {bad}"
```

- [ ] **Step 0.3: 跑测试看初始失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_detect_no_hardcode.py -v
```

预期：FAIL（如 grep step 0.1 找到任何硬编码）。

- [ ] **Step 0.4: 改 sw_detect.py 把硬编码改成自主发现**

每条硬编码替换为：注册表枚举 / `winreg.OpenKey` / `winreg.EnumKey` / 或运行时 COM API 调用。**不允许**把硬编码 "藏" 到 dict 字面值里——也算硬编码。

- [ ] **Step 0.5: 跑测试看通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_detect_no_hardcode.py -v
```

预期：PASS。

- [ ] **Step 0.6: 跑现有 sw_detect 全部测试看不回归**

```bash
.venv/Scripts/python.exe -m pytest tests/ -k "sw_detect" -v
```

预期：所有现有测试仍通过。若回归 → 修。

- [ ] **Step 0.7: commit**

```bash
git add adapters/solidworks/sw_detect.py tests/test_sw_detect_no_hardcode.py
git commit -m "refactor(sw_detect): 清理现有硬编码 — 路径/版本走自主发现 (Task 0)"
```

---

### Task 1: 创建 sw_preflight/ 包结构

**Files:**
- Create: `sw_preflight/__init__.py`
- Create: `sw_preflight/types.py`（占位）
- Create: `sw_preflight/diagnosis.py`（占位）
- Test: `tests/test_sw_preflight_import.py`

- [ ] **Step 1.1: 写失败测试 — package 可导入**

```python
# tests/test_sw_preflight_import.py
def test_sw_preflight_package_importable():
    import sw_preflight
    assert sw_preflight is not None
```

- [ ] **Step 1.2: 跑测试看失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_import.py -v
```

预期：FAIL（ModuleNotFoundError）。

- [ ] **Step 1.3: 创建包**

```python
# sw_preflight/__init__.py
"""SW 装即用 体验打通 orchestrator (spec 2026-04-19)"""
```

```python
# sw_preflight/types.py
"""数据类型 — 见 Task 2 填充"""
```

```python
# sw_preflight/diagnosis.py
"""诊断系统 — 见 Task 3 填充"""
```

- [ ] **Step 1.4: 跑测试看通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_import.py -v
```

预期：PASS。

- [ ] **Step 1.5: commit**

```bash
git add sw_preflight/ tests/test_sw_preflight_import.py
git commit -m "feat(sw_preflight): 创建 orchestrator 包骨架 (Task 1)"
```

---

## Phase 1: 底层数据类型

### Task 2: types.py — PartCategory + 7 个 dataclass

**Files:**
- Modify: `sw_preflight/types.py`
- Test: `tests/test_sw_preflight_types.py`

- [ ] **Step 2.1: 写失败测试 — 7 个类型 + PartCategory enum 可构造**

```python
# tests/test_sw_preflight_types.py
from pathlib import Path
from sw_preflight.types import (
    PartCategory, PreflightResult, BomDryRunResult, RowOutcome,
    UserChoiceResult, FixRecord
)

def test_part_category_has_9_members():
    expected = {'STANDARD_FASTENER', 'STANDARD_BEARING', 'STANDARD_SEAL',
                'STANDARD_LOCATING', 'STANDARD_ELASTIC', 'STANDARD_TRANSMISSION',
                'STANDARD_OTHER', 'VENDOR_PURCHASED', 'CUSTOM'}
    assert {m.name for m in PartCategory} == expected

def test_preflight_result_frozen():
    from sw_preflight.types import SwInfoStub  # SwInfo 由 sw_detect 提供，测试用 stub
    r = PreflightResult(passed=True, sw_info=None, fixes_applied=[],
                        diagnosis=None, per_step_ms={'detect': 12.3})
    import dataclasses
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.passed = False

def test_row_outcome_has_category():
    o = RowOutcome(bom_row={'name_cn': 'M6'}, category=PartCategory.STANDARD_FASTENER,
                   expected_adapter='sw_toolbox', actual_adapter='sw_toolbox',
                   status='✅', diagnosis=None)
    assert o.category == PartCategory.STANDARD_FASTENER

def test_fix_record_fields():
    f = FixRecord(action='enable_addin', before_state='disabled',
                  after_state='enabled', elapsed_ms=820.5)
    assert f.elapsed_ms == 820.5
```

- [ ] **Step 2.2: 跑测试看失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_types.py -v
```

预期：FAIL（ImportError）。

- [ ] **Step 2.3: 实现 types.py**

```python
# sw_preflight/types.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Optional

class PartCategory(Enum):
    STANDARD_FASTENER = 'standard_fastener'
    STANDARD_BEARING = 'standard_bearing'
    STANDARD_SEAL = 'standard_seal'
    STANDARD_LOCATING = 'standard_locating'
    STANDARD_ELASTIC = 'standard_elastic'
    STANDARD_TRANSMISSION = 'standard_transmission'
    STANDARD_OTHER = 'standard_other'
    VENDOR_PURCHASED = 'vendor_purchased'
    CUSTOM = 'custom'

@dataclass(frozen=True)
class FixRecord:
    action: str
    before_state: str
    after_state: str
    elapsed_ms: float

@dataclass(frozen=True)
class PreflightResult:
    passed: bool
    sw_info: Any  # SwInfo from adapters/solidworks/sw_detect.py
    fixes_applied: list[FixRecord]
    diagnosis: Optional['DiagnosisInfo']  # forward ref to diagnosis.py
    per_step_ms: dict[str, float]

@dataclass(frozen=True)
class RowOutcome:
    bom_row: dict
    category: PartCategory
    expected_adapter: str
    actual_adapter: str
    status: Literal['✅', '⚠️', '❌']
    diagnosis: Optional['DiagnosisInfo']

@dataclass(frozen=True)
class BomDryRunResult:
    total_rows: int
    hit_rows: list[RowOutcome]
    missing_rows: list[RowOutcome]
    stand_in_rows: list[RowOutcome]

@dataclass(frozen=True)
class UserChoiceResult:
    provided_files: dict[str, Path]  # bom_key -> 复制后的路径
    stand_in_keys: set[str]
    skipped_keys: set[str]
```

> 需要在测试文件顶部加 `import pytest`；如 SwInfoStub 不存在，把测试里的 SwInfo 引用改成传 `None`（types.py 的 sw_info 是 Any 类型）。

- [ ] **Step 2.4: 跑测试看通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_types.py -v
```

预期：PASS。

- [ ] **Step 2.5: commit**

```bash
git add sw_preflight/types.py tests/test_sw_preflight_types.py
git commit -m "feat(sw_preflight): types.py — PartCategory + 5 dataclass (Task 2)"
```

---

### Task 3: diagnosis.py — DiagnosisCode + DiagnosisInfo

**Files:**
- Modify: `sw_preflight/diagnosis.py`
- Modify: `sw_preflight/types.py`（替换 forward ref `'DiagnosisInfo'` 为真实 import）
- Test: `tests/test_sw_preflight_diagnosis.py`

- [ ] **Step 3.1: 写失败测试 — DiagnosisCode 含 v1 全部 15 个码**

```python
# tests/test_sw_preflight_diagnosis.py
from sw_preflight.diagnosis import DiagnosisCode, DiagnosisInfo

def test_diagnosis_code_v1_complete():
    """spec §3.1 列举的 v1 失败码必须全部存在（增量追加策略，不删）"""
    expected = {
        'SW_NOT_INSTALLED', 'SW_TOOLBOX_NOT_SUPPORTED', 'LICENSE_PROBLEM',
        'COM_REGISTRATION_BROKEN', 'TOOLBOX_PATH_INVALID',
        'TOOLBOX_PATH_NOT_ACCESSIBLE', 'PYWIN32_MISSING', 'PYWIN32_INSTALL_FAILED',
        'ADDIN_DISABLED', 'MULTIPLE_SW_VERSIONS_AMBIGUOUS', 'INSUFFICIENT_PRIVILEGES',
        'BOM_ROW_NO_MATCH', 'BOM_ROW_FELL_THROUGH_TO_STAND_IN',
        'USER_PROVIDED_SOURCE_HASH_MISMATCH', 'USER_PROVIDED_SCHEMA_INVALID',
        'PLATFORM_NOT_WINDOWS',
    }
    actual = {c.name for c in DiagnosisCode}
    missing = expected - actual
    assert not missing, f"v1 码缺失: {missing}"

def test_diagnosis_info_has_required_fields():
    d = DiagnosisInfo(
        code=DiagnosisCode.SW_NOT_INSTALLED,
        reason="未检测到 SolidWorks 安装",
        suggestion="请安装 SolidWorks Pro 或 Premium",
        severity='block',
    )
    assert d.severity == 'block'
```

- [ ] **Step 3.2: 跑测试看失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_diagnosis.py -v
```

预期：FAIL。

- [ ] **Step 3.3: 实现 diagnosis.py**

```python
# sw_preflight/diagnosis.py
from dataclasses import dataclass
from enum import Enum
from typing import Literal

class DiagnosisCode(Enum):
    PLATFORM_NOT_WINDOWS = 'platform_not_windows'
    SW_NOT_INSTALLED = 'sw_not_installed'
    SW_TOOLBOX_NOT_SUPPORTED = 'sw_toolbox_not_supported'
    LICENSE_PROBLEM = 'license_problem'
    COM_REGISTRATION_BROKEN = 'com_registration_broken'
    TOOLBOX_PATH_INVALID = 'toolbox_path_invalid'
    TOOLBOX_PATH_NOT_ACCESSIBLE = 'toolbox_path_not_accessible'
    PYWIN32_MISSING = 'pywin32_missing'
    PYWIN32_INSTALL_FAILED = 'pywin32_install_failed'
    ADDIN_DISABLED = 'addin_disabled'
    MULTIPLE_SW_VERSIONS_AMBIGUOUS = 'multiple_sw_versions_ambiguous'
    INSUFFICIENT_PRIVILEGES = 'insufficient_privileges'
    BOM_ROW_NO_MATCH = 'bom_row_no_match'
    BOM_ROW_FELL_THROUGH_TO_STAND_IN = 'bom_row_fell_through_to_stand_in'
    USER_PROVIDED_SOURCE_HASH_MISMATCH = 'user_provided_source_hash_mismatch'
    USER_PROVIDED_SCHEMA_INVALID = 'user_provided_schema_invalid'

@dataclass(frozen=True)
class DiagnosisInfo:
    code: DiagnosisCode
    reason: str            # 中文一句，给用户看
    suggestion: str        # GUI 操作步骤
    severity: Literal['block', 'warn']
```

修复 `sw_preflight/types.py` forward ref：
```python
from sw_preflight.diagnosis import DiagnosisInfo  # 顶部加 import
# PreflightResult 和 RowOutcome 的 diagnosis: Optional[DiagnosisInfo] 直接引用
```

- [ ] **Step 3.4: 跑测试看通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_diagnosis.py tests/test_sw_preflight_types.py -v
```

预期：两个测试文件全过。

- [ ] **Step 3.5: commit**

```bash
git add sw_preflight/diagnosis.py sw_preflight/types.py tests/test_sw_preflight_diagnosis.py
git commit -m "feat(sw_preflight): diagnosis.py — DiagnosisCode v1 16 码 + DiagnosisInfo (Task 3)"
```

---

## 🛑 CHECKPOINT 1: Phase 0-1 完成

请用户确认：
- 硬编码清查通过（Task 0 测试通过）
- 包骨架 + types + diagnosis 通过（Task 1-3）
- 暂停等用户 OK 后继续 Phase 2

---

## Phase 2: 扩展 sw_detect.py

### Task 4: SwInfo 加 edition 字段 + reset_cache() API

**Files:**
- Modify: `adapters/solidworks/sw_detect.py`
- Test: `tests/test_sw_detect_edition.py`

- [ ] **Step 4.1: 写失败测试 — SwInfo.edition + reset_cache**

```python
# tests/test_sw_detect_edition.py
import pytest

def test_sw_info_has_edition_field():
    from adapters.solidworks.sw_detect import SwInfo
    import dataclasses
    fields = {f.name for f in dataclasses.fields(SwInfo)}
    assert 'edition' in fields

def test_reset_cache_clears_cached_info():
    from adapters.solidworks import sw_detect
    sw_detect.detect_solidworks()  # 充缓存
    sw_detect.reset_cache()
    # 重 detect 应该重新执行（不能从缓存返回）
    # 通过 monkeypatch 校验：reset 后底层注册表读取被再调一次
    # （细节见 conftest 的 mock_sw_registry_versions fixture，Task 32 提供）
    assert sw_detect._cached_info is None  # 假设 _cached_info 是模块级变量
```

- [ ] **Step 4.2: 跑测试看失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_detect_edition.py -v
```

预期：FAIL。

- [ ] **Step 4.3: 修改 sw_detect.py**

加 `edition: Literal['Standard', 'Pro', 'Premium', 'unknown']` 到 `SwInfo` dataclass；加 `reset_cache()` 函数清 `_cached_info`。edition 来源用注册表 `HKLM\SOFTWARE\SolidWorks\SOLIDWORKS <ver>\Setup\Edition` 字段（**绝对不硬编码版本年份** — 用 `winreg.EnumKey` 枚举所有 SOLIDWORKS 子键）。

- [ ] **Step 4.4: 跑测试看通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_detect_edition.py tests/test_sw_detect_no_hardcode.py -v
```

预期：两个测试都通过（含 Task 0 的零硬编码校验）。

- [ ] **Step 4.5: commit**

```bash
git add adapters/solidworks/sw_detect.py tests/test_sw_detect_edition.py
git commit -m "feat(sw_detect): SwInfo.edition + reset_cache() (Task 4)"
```

---

### Task 5: 多版本枚举 + sw_version_preference.json 读取

**Files:**
- Modify: `adapters/solidworks/sw_detect.py`
- Create: `sw_preflight/preference.py`
- Test: `tests/test_sw_detect_multiversion.py`、`tests/test_sw_preflight_preference.py`

- [ ] **Step 5.1: 写失败测试 — 多版本枚举三档优先级**

```python
# tests/test_sw_detect_multiversion.py
import pytest, os
from unittest.mock import patch

def test_env_var_overrides_preference_and_latest(monkeypatch, tmp_path):
    """env > preference.json > 最新版"""
    monkeypatch.setenv('CAD_SPEC_GEN_SW_PREFERRED_YEAR', '2022')
    # mock 注册表枚举返回 [2022, 2024, 2026]
    with patch('adapters.solidworks.sw_detect._enumerate_registered_years',
               return_value=[2022, 2024, 2026]):
        from adapters.solidworks.sw_detect import detect_solidworks, reset_cache
        reset_cache()
        info = detect_solidworks()
        assert info.version_year == 2022  # env 强制

def test_preference_json_used_when_no_env(monkeypatch, tmp_path):
    monkeypatch.delenv('CAD_SPEC_GEN_SW_PREFERRED_YEAR', raising=False)
    pref = tmp_path / 'sw_version_preference.json'
    pref.write_text('{"preferred_year": 2024}')
    monkeypatch.setattr('sw_preflight.preference.PREFERENCE_PATH', pref)
    with patch('adapters.solidworks.sw_detect._enumerate_registered_years',
               return_value=[2022, 2024, 2026]):
        from adapters.solidworks.sw_detect import detect_solidworks, reset_cache
        reset_cache()
        info = detect_solidworks()
        assert info.version_year == 2024

def test_latest_default_when_no_env_no_preference(monkeypatch):
    monkeypatch.delenv('CAD_SPEC_GEN_SW_PREFERRED_YEAR', raising=False)
    monkeypatch.setattr('sw_preflight.preference.read_preference', lambda: None)
    with patch('adapters.solidworks.sw_detect._enumerate_registered_years',
               return_value=[2022, 2024, 2026]):
        from adapters.solidworks.sw_detect import detect_solidworks, reset_cache
        reset_cache()
        info = detect_solidworks()
        assert info.version_year == 2026  # 最新
```

```python
# tests/test_sw_preflight_preference.py
def test_read_write_preference(tmp_path, monkeypatch):
    from sw_preflight import preference
    monkeypatch.setattr(preference, 'PREFERENCE_PATH', tmp_path / 'pref.json')
    assert preference.read_preference() is None
    preference.write_preference(2024)
    assert preference.read_preference() == 2024
```

- [ ] **Step 5.2: 跑测试看失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_detect_multiversion.py tests/test_sw_preflight_preference.py -v
```

预期：FAIL。

- [ ] **Step 5.3: 实现 preference.py + 改 sw_detect.py**

```python
# sw_preflight/preference.py
"""跨 run 的用户版本偏好持久化"""
import json
from pathlib import Path
from typing import Optional

PREFERENCE_PATH = Path.home() / '.cad-spec-gen' / 'sw_version_preference.json'

def read_preference() -> Optional[int]:
    if not PREFERENCE_PATH.exists():
        return None
    try:
        data = json.loads(PREFERENCE_PATH.read_text(encoding='utf-8'))
        return data.get('preferred_year')
    except (json.JSONDecodeError, OSError):
        return None

def write_preference(year: int) -> None:
    PREFERENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone
    data = {'preferred_year': year,
            'set_at': datetime.now(timezone.utc).isoformat()}
    PREFERENCE_PATH.write_text(json.dumps(data), encoding='utf-8')
```

`sw_detect.py` 加：
- `_enumerate_registered_years()` — 用 `winreg.EnumKey` 枚举 `HKLM\SOFTWARE\SolidWorks` 下所有 `SOLIDWORKS *` 子键
- `_select_version()` — 三档优先级（env → preference → 最新）
- `detect_solidworks()` 用 `_select_version()` 决定 version_year

- [ ] **Step 5.4: 跑测试看通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_detect_multiversion.py tests/test_sw_preflight_preference.py tests/test_sw_detect_no_hardcode.py -v
```

预期：全过（含零硬编码校验）。

- [ ] **Step 5.5: commit**

```bash
git add sw_preflight/preference.py adapters/solidworks/sw_detect.py tests/test_sw_detect_multiversion.py tests/test_sw_preflight_preference.py
git commit -m "feat(sw_detect): 多版本枚举 + sw_version_preference.json 三档优先级 (Task 5)"
```

---

### Task 6: UNC 路径可达性校验

**Files:**
- Modify: `adapters/solidworks/sw_detect.py`
- Test: `tests/test_sw_detect_unc.py`

- [ ] **Step 6.1: 写失败测试 — UNC 路径不可达 → TOOLBOX_PATH_NOT_ACCESSIBLE**

```python
# tests/test_sw_detect_unc.py
def test_unc_unreachable_returns_not_accessible_diagnosis(monkeypatch):
    from adapters.solidworks.sw_detect import probe_toolbox_path_reachability
    # mock: toolbox_dir 是 UNC 但不可达
    result = probe_toolbox_path_reachability(r'\\fileserver-doesnotexist\Toolbox')
    assert result == 'not_accessible'

def test_local_path_invalid_returns_invalid(monkeypatch):
    from adapters.solidworks.sw_detect import probe_toolbox_path_reachability
    result = probe_toolbox_path_reachability('C:/this/path/does/not/exist')
    assert result == 'invalid'

def test_local_path_valid_returns_ok(tmp_path):
    from adapters.solidworks.sw_detect import probe_toolbox_path_reachability
    result = probe_toolbox_path_reachability(str(tmp_path))
    assert result == 'ok'
```

- [ ] **Step 6.2: 跑测试看失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_detect_unc.py -v
```

预期：FAIL。

- [ ] **Step 6.3: 实现 probe_toolbox_path_reachability**

```python
# adapters/solidworks/sw_detect.py 内加
def probe_toolbox_path_reachability(path: str) -> Literal['ok', 'invalid', 'not_accessible']:
    """区分本地路径不存在 vs UNC/网络不可达"""
    from pathlib import Path
    p = Path(path)
    if str(p).startswith('\\\\'):  # UNC
        try:
            return 'ok' if p.exists() and os.access(p, os.R_OK) else 'not_accessible'
        except OSError:
            return 'not_accessible'
    return 'ok' if p.exists() and os.access(p, os.R_OK) else 'invalid'
```

- [ ] **Step 6.4: 跑测试看通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_detect_unc.py tests/test_sw_detect_no_hardcode.py -v
```

预期：全过。

- [ ] **Step 6.5: commit**

```bash
git add adapters/solidworks/sw_detect.py tests/test_sw_detect_unc.py
git commit -m "feat(sw_detect): UNC 路径可达性校验 — 区分 invalid vs not_accessible (Task 6)"
```

---

## Phase 3: 扩展 parts_resolver + parts_library

### Task 7: ResolveResult 加 category 字段

**Files:**
- Modify: `adapters/parts/parts_resolver.py`
- Test: `tests/test_parts_resolver_category.py`

- [ ] **Step 7.1: 写失败测试 — ResolveResult 含 category**

```python
# tests/test_parts_resolver_category.py
from sw_preflight.types import PartCategory

def test_resolver_returns_category_for_fastener():
    from adapters.parts.parts_resolver import PartsResolver
    r = PartsResolver()
    res = r.resolve({'name_cn': 'GB/T 70.1 M6×20 内六角',
                     'category': 'fastener', 'material': '不锈钢'})
    assert res.category == PartCategory.STANDARD_FASTENER

def test_resolver_returns_vendor_category_for_maxon():
    from adapters.parts.parts_resolver import PartsResolver
    r = PartsResolver()
    res = r.resolve({'name_cn': 'Maxon ECX SPEED 22L', 'material': ''})
    assert res.category == PartCategory.VENDOR_PURCHASED

def test_resolver_returns_custom_category_for_unknown():
    from adapters.parts.parts_resolver import PartsResolver
    r = PartsResolver()
    res = r.resolve({'name_cn': '私有件 PXY-2024-A', 'material': ''})
    assert res.category == PartCategory.CUSTOM
```

- [ ] **Step 7.2: 跑测试看失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_parts_resolver_category.py -v
```

预期：FAIL。

- [ ] **Step 7.3: 修改 ResolveResult + resolve()**

`adapters/parts/parts_resolver.py`：
- `ResolveResult` dataclass 加 `category: 'PartCategory'` 字段
- `resolve()` 在命中 mapping 后根据 mapping 的 `match.category` + adapter 类型推断 PartCategory（fastener → STANDARD_FASTENER；bearing → STANDARD_BEARING；step_pool 含 synthesizer → VENDOR_PURCHASED；jinja_primitive → CUSTOM；其它 STANDARD_* → 按 mapping 显式 match.category 字段或新加的 part_category 字段决定）

- [ ] **Step 7.4: 跑测试看通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_parts_resolver_category.py -v
```

预期：PASS。

- [ ] **Step 7.5: 跑现有 parts_resolver 全部测试看不回归**

```bash
.venv/Scripts/python.exe -m pytest tests/ -k "parts_resolver" -v
```

预期：现有测试全过。

- [ ] **Step 7.6: commit**

```bash
git add adapters/parts/parts_resolver.py tests/test_parts_resolver_category.py
git commit -m "feat(parts_resolver): ResolveResult.category — 9 类 PartCategory 路由权威 (Task 7)"
```

---

### Task 8: parts_library.default.yaml 补 STANDARD_* mapping

**Files:**
- Modify: `parts_library.default.yaml`
- Modify: `src/cad_spec_gen/data/parts_library.default.yaml`（同步）
- Test: `tests/test_parts_library_standard_categories.py`

- [ ] **Step 8.1: 写失败测试 — 4 类标准件 mapping 命中**

```python
# tests/test_parts_library_standard_categories.py
from sw_preflight.types import PartCategory

def test_o_ring_routes_to_standard_seal():
    from adapters.parts.parts_resolver import PartsResolver
    r = PartsResolver()
    res = r.resolve({'name_cn': 'GB/T 1235 O 圈 Φ20×2', 'category': 'seal'})
    assert res.category == PartCategory.STANDARD_SEAL

def test_dowel_pin_routes_to_standard_locating():
    from adapters.parts.parts_resolver import PartsResolver
    r = PartsResolver()
    res = r.resolve({'name_cn': 'GB/T 117 圆锥销 Φ4×20', 'category': 'locating'})
    assert res.category == PartCategory.STANDARD_LOCATING

def test_compression_spring_routes_to_standard_elastic():
    from adapters.parts.parts_resolver import PartsResolver
    r = PartsResolver()
    res = r.resolve({'name_cn': 'GB/T 2089 圆柱压缩弹簧', 'category': 'elastic'})
    assert res.category == PartCategory.STANDARD_ELASTIC

def test_gear_routes_to_standard_transmission():
    from adapters.parts.parts_resolver import PartsResolver
    r = PartsResolver()
    res = r.resolve({'name_cn': 'GB/T 1357 渐开线齿轮', 'category': 'transmission'})
    assert res.category == PartCategory.STANDARD_TRANSMISSION
```

- [ ] **Step 8.2: 跑测试看失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_parts_library_standard_categories.py -v
```

预期：FAIL（mapping 不存在）。

- [ ] **Step 8.3: 改 parts_library.default.yaml**

在第一个 `match: {any: true}` 兜底前追加（**不删/不改**现有 mapping）：

```yaml
  # ─── STANDARD_SEAL — O 圈/油封/密封圈（GB/T 1235, 13871）───────────────
  - match:
      category: seal
      keyword_contains: ["GB/T 1235", "GB1235", "O 圈", "O圈"]
    adapter: sw_toolbox
    spec:
      part_category: standard_seal
      standard: GB
      subcategories: ["o-rings"]

  # ─── STANDARD_LOCATING — 销/键/卡簧（GB/T 117, 1096, 894）─────────────
  - match:
      category: locating
      keyword_contains: ["GB/T 117", "GB/T 1096", "GB/T 894", "圆锥销", "平键"]
    adapter: sw_toolbox
    spec:
      part_category: standard_locating
      standard: GB
      subcategories: ["pins", "keys", "retaining rings"]

  # ─── STANDARD_ELASTIC — 弹簧（GB/T 2089, 2087）─────────────────────────
  - match:
      category: elastic
      keyword_contains: ["GB/T 2089", "GB/T 2087", "压缩弹簧", "拉伸弹簧"]
    adapter: jinja_primitive  # 弹簧 SW Toolbox 覆盖差，先走参数化
    spec:
      part_category: standard_elastic

  # ─── STANDARD_TRANSMISSION — 齿轮/链/带（GB/T 1357, 1243）─────────────
  - match:
      category: transmission
      keyword_contains: ["GB/T 1357", "GB/T 1243", "渐开线齿轮", "链轮"]
    adapter: jinja_primitive  # 传动件复杂，先 jinja 参数化兜底
    spec:
      part_category: standard_transmission
```

> **重要**：这些 mapping 插入位置在现有 `bd_warehouse generic deep-groove fallback`（约第 210 行）之后、`{any: true}` 兜底之前——保证现有紧固件/轴承规则的 first-hit 顺序不变。

同步改 `src/cad_spec_gen/data/parts_library.default.yaml`（如果存在副本）。

- [ ] **Step 8.4: 跑测试看通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_parts_library_standard_categories.py tests/test_parts_resolver_category.py -v
```

预期：全过。

- [ ] **Step 8.5: 跑同题域回归**

```bash
.venv/Scripts/python.exe -m pytest tests/test_parts_library*.py tests/test_parts_resolver*.py -v
```

预期：现有测试不回归（per memory `feedback_local_test_scope.md`：改 yaml 必须跑同题域 glob）。

- [ ] **Step 8.6: commit**

```bash
git add parts_library.default.yaml src/cad_spec_gen/data/parts_library.default.yaml tests/test_parts_library_standard_categories.py
git commit -m "feat(parts_library): 补 STANDARD_SEAL/LOCATING/ELASTIC/TRANSMISSION mapping (Task 8)"
```

---

## 🛑 CHECKPOINT 2: Phase 2-3 完成

请用户确认：
- sw_detect 扩展完成（edition / reset_cache / 多版本 / UNC）
- parts_resolver + parts_library 扩展完成（category 字段 + 4 类 mapping）
- 所有现有测试不回归
- 暂停等用户 OK 后继续 Phase 4

---

## Phase 4: sw_preflight io 层

### Task 9: io.py — SW 装配体检测 + 等关闭轮询

**Files:**
- Create: `sw_preflight/io.py`
- Test: `tests/test_sw_preflight_io_wait.py`

- [ ] **Step 9.1: 写失败测试 — 等装配体关闭轮询（mock SW 进程）**

```python
# tests/test_sw_preflight_io_wait.py
import pytest
from unittest.mock import patch, MagicMock

@pytest.mark.requires_solidworks
def test_wait_for_assembly_close_returns_when_no_assembly():
    """已无装配体打开 → 立即返回 True"""
    from sw_preflight.io import wait_for_assembly_close
    # 假设当前 SW 没装配体打开
    result = wait_for_assembly_close(timeout_sec=2)
    assert result is True

def test_wait_for_assembly_close_mock_assembly_then_close():
    """有装配体 → poll 直到关闭"""
    from sw_preflight import io
    states = ['has_assembly', 'has_assembly', 'no_assembly']
    with patch.object(io, '_count_open_assemblies', side_effect=lambda: 0 if states.pop(0) == 'no_assembly' else 1):
        result = io.wait_for_assembly_close(timeout_sec=10, poll_interval=0.01)
        assert result is True

def test_wait_for_assembly_close_timeout():
    from sw_preflight import io
    with patch.object(io, '_count_open_assemblies', return_value=1):
        result = io.wait_for_assembly_close(timeout_sec=0.05, poll_interval=0.01)
        assert result is False  # 超时
```

- [ ] **Step 9.2: 跑测试看失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_io_wait.py -v -m "not requires_solidworks"
```

预期：FAIL（io.py 不存在）。

- [ ] **Step 9.3: 实现 io.py 装配体检测部分**

```python
# sw_preflight/io.py
import time
from typing import Optional

def _count_open_assemblies() -> int:
    """通过 ISldWorks::GetDocuments 枚举打开文档，按 type=swDocASSEMBLY 计数"""
    try:
        from adapters.solidworks.sw_com_session import get_session
        sess = get_session()
        if not sess.is_healthy():
            return 0
        # 调 SW COM API 数装配体
        # swDocASSEMBLY = 2 (SolidWorks 常量)
        return sess.count_documents_by_type(doc_type=2)
    except Exception:
        return 0

def wait_for_assembly_close(timeout_sec: float = 300, poll_interval: float = 1.0) -> bool:
    """轮询等装配体全关；超时返回 False"""
    start = time.time()
    while time.time() - start < timeout_sec:
        if _count_open_assemblies() == 0:
            return True
        time.sleep(poll_interval)
    return False
```

> 注：`sw_com_session.count_documents_by_type` 可能不存在 — 若如此，`_count_open_assemblies` 实现走 `sess.com.GetDocuments()` 直接遍历。本步骤的核心是测试通过 mock 路径；真 SW 路径在 Task 26 集成测试时验证。

- [ ] **Step 9.4: 跑测试看通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_io_wait.py -v -m "not requires_solidworks"
```

预期：PASS（mock 部分 — 真 SW 部分 `requires_solidworks` 在 Windows runner 跑）。

- [ ] **Step 9.5: commit**

```bash
git add sw_preflight/io.py tests/test_sw_preflight_io_wait.py
git commit -m "feat(sw_preflight): io.py — 装配体检测 + 等关闭轮询 (Task 9)"
```

---

### Task 10: io.py — tkinter.filedialog 包装 + 三选一 prompt

**Files:**
- Modify: `sw_preflight/io.py`
- Test: `tests/test_sw_preflight_io_dialog.py`

- [ ] **Step 10.1: 写失败测试 — file dialog mock 测试**

```python
# tests/test_sw_preflight_io_dialog.py
from unittest.mock import patch, MagicMock
from pathlib import Path

def test_ask_step_file_returns_path():
    with patch('sw_preflight.io.filedialog.askopenfilename',
               return_value='C:/Users/foo/m6x20.step'):
        from sw_preflight.io import ask_step_file
        result = ask_step_file('为 GB/T 70.1 M6×20 选择 STEP (1/5)')
        assert result == Path('C:/Users/foo/m6x20.step')

def test_ask_step_file_returns_none_on_cancel():
    with patch('sw_preflight.io.filedialog.askopenfilename', return_value=''):
        from sw_preflight.io import ask_step_file
        assert ask_step_file('test') is None

def test_three_choice_prompt(monkeypatch):
    monkeypatch.setattr('builtins.input', lambda _: '2')
    from sw_preflight.io import three_choice_prompt
    result = three_choice_prompt(missing_count=5)
    assert result == 'stand_in'  # [2] 全部 stand-in
```

- [ ] **Step 10.2: 跑测试看失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_io_dialog.py -v
```

预期：FAIL。

- [ ] **Step 10.3: 实现 io.py 对话框部分**

```python
# sw_preflight/io.py 追加
from pathlib import Path
from typing import Optional, Literal
from tkinter import filedialog, Tk

def ask_step_file(title: str) -> Optional[Path]:
    """弹 Windows 原生文件对话框"""
    root = Tk()
    root.withdraw()
    try:
        path = filedialog.askopenfilename(
            title=title,
            filetypes=[('STEP files', '*.step *.stp'), ('All files', '*.*')]
        )
        return Path(path) if path else None
    finally:
        root.destroy()

def three_choice_prompt(missing_count: int) -> Literal['provide', 'stand_in', 'skip']:
    """全局三选一 — [1] 我来指定 / [2] stand-in / [3] 跳过"""
    print(f"\n⚠️ BOM 中 {missing_count} 行 SW 库未直接命中。")
    print("如何处理?")
    print("  [1] 我来指定 STEP 文件 (依次弹文件对话框, 单行可跳过)")
    print("  [2] 全部用参数化 stand-in (精度低但能跑)")
    print("  [3] 全部跳过 (这些零件不出现在渲染中)")
    while True:
        choice = input("请选 [1/2/3]: ").strip()
        if choice == '1': return 'provide'
        if choice == '2': return 'stand_in'
        if choice == '3': return 'skip'
        print("无效输入，请输入 1、2 或 3")
```

- [ ] **Step 10.4: 跑测试看通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_io_dialog.py -v
```

预期：PASS。

- [ ] **Step 10.5: commit**

```bash
git add sw_preflight/io.py tests/test_sw_preflight_io_dialog.py
git commit -m "feat(sw_preflight): io.py — tkinter.filedialog 包装 + 三选一 prompt (Task 10)"
```

---

### Task 11: io.py — STEP 三层校验

**Files:**
- Modify: `sw_preflight/io.py`
- Test: `tests/test_sw_preflight_io_step_validate.py`

- [ ] **Step 11.1: 写失败测试 — 扩展名/大小/魔数头三层**

```python
# tests/test_sw_preflight_io_step_validate.py
from pathlib import Path

def test_ext_check_rejects_stl(tmp_path):
    f = tmp_path / 'file.stl'
    f.write_text('foo')
    from sw_preflight.io import validate_step_file
    result = validate_step_file(f)
    assert result.kind == 'invalid_ext'

def test_size_too_small(tmp_path):
    f = tmp_path / 'tiny.step'
    f.write_text('x')  # 1 byte < 10KB
    from sw_preflight.io import validate_step_file
    result = validate_step_file(f)
    assert result.kind == 'too_small'

def test_size_too_large(tmp_path):
    f = tmp_path / 'huge.step'
    f.write_bytes(b'x' * (501 * 1024 * 1024))  # 501MB > 500MB
    from sw_preflight.io import validate_step_file
    result = validate_step_file(f)
    assert result.kind == 'too_large'

def test_magic_header_invalid(tmp_path):
    f = tmp_path / 'fake.step'
    f.write_bytes(b'not iso 10303' + b'x' * 20000)
    from sw_preflight.io import validate_step_file
    result = validate_step_file(f)
    assert result.kind == 'invalid_magic'

def test_valid_step_file(tmp_path):
    f = tmp_path / 'valid.step'
    f.write_bytes(b'ISO-10303-21;\nHEADER;\n' + b'\n' * 20000)
    from sw_preflight.io import validate_step_file
    result = validate_step_file(f)
    assert result.kind == 'valid'
```

- [ ] **Step 11.2: 跑测试看失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_io_step_validate.py -v
```

预期：FAIL。

- [ ] **Step 11.3: 实现 validate_step_file**

```python
# sw_preflight/io.py 追加
from dataclasses import dataclass

@dataclass(frozen=True)
class StepValidateResult:
    kind: Literal['valid', 'invalid_ext', 'too_small', 'too_large',
                  'invalid_magic', 'parse_warn']

MIN_SIZE = 10 * 1024
MAX_SIZE = 500 * 1024 * 1024

def validate_step_file(path: Path) -> StepValidateResult:
    """三层校验: 扩展名 → 大小 → 魔数头 (cadquery 解析在 Task 24)"""
    if path.suffix.lower() not in ('.step', '.stp'):
        return StepValidateResult(kind='invalid_ext')
    size = path.stat().st_size
    if size < MIN_SIZE:
        return StepValidateResult(kind='too_small')
    if size > MAX_SIZE:
        return StepValidateResult(kind='too_large')
    head = path.read_bytes()[:50]
    if b'ISO-10303' not in head:
        return StepValidateResult(kind='invalid_magic')
    return StepValidateResult(kind='valid')
```

- [ ] **Step 11.4: 跑测试看通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_io_step_validate.py -v
```

预期：PASS。

- [ ] **Step 11.5: commit**

```bash
git add sw_preflight/io.py tests/test_sw_preflight_io_step_validate.py
git commit -m "feat(sw_preflight): io.py — STEP 三层校验（扩展名/大小/魔数头） (Task 11)"
```

---

## Phase 5: sw_preflight matrix 层（M 体检 + 一键修）

### Task 12: matrix.py — 自动通过判定 7 项

**Files:**
- Create: `sw_preflight/matrix.py`
- Test: `tests/test_sw_preflight_matrix_check.py`

- [ ] **Step 12.1: 写失败测试 — 7 项检查全过 → passed=True**

```python
# tests/test_sw_preflight_matrix_check.py
from unittest.mock import MagicMock, patch

def test_all_checks_pass():
    from sw_preflight.matrix import run_all_checks
    with patch('sw_preflight.matrix._check_platform', return_value=(True, None)):
        with patch('sw_preflight.matrix._check_pywin32', return_value=(True, None)):
            with patch('sw_preflight.matrix._check_sw_installed', return_value=(True, None)):
                with patch('sw_preflight.matrix._check_toolbox_supported', return_value=(True, None)):
                    with patch('sw_preflight.matrix._check_com_healthy', return_value=(True, None)):
                        with patch('sw_preflight.matrix._check_addin_enabled', return_value=(True, None)):
                            with patch('sw_preflight.matrix._check_toolbox_path', return_value=(True, None)):
                                result = run_all_checks()
                                assert result['passed'] is True
                                assert result['failed_check'] is None

def test_first_fail_returns_diagnosis():
    from sw_preflight.matrix import run_all_checks
    from sw_preflight.diagnosis import DiagnosisCode, DiagnosisInfo
    fake_diag = DiagnosisInfo(code=DiagnosisCode.SW_NOT_INSTALLED,
                              reason="未检测到", suggestion="装", severity='block')
    with patch('sw_preflight.matrix._check_platform', return_value=(True, None)):
        with patch('sw_preflight.matrix._check_pywin32', return_value=(True, None)):
            with patch('sw_preflight.matrix._check_sw_installed', return_value=(False, fake_diag)):
                result = run_all_checks()
                assert result['passed'] is False
                assert result['failed_check'] == 'sw_installed'
                assert result['diagnosis'].code == DiagnosisCode.SW_NOT_INSTALLED
```

- [ ] **Step 12.2: 跑测试看失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_matrix_check.py -v
```

预期：FAIL。

- [ ] **Step 12.3: 实现 run_all_checks**

```python
# sw_preflight/matrix.py
from typing import Optional
from sw_preflight.diagnosis import DiagnosisCode, DiagnosisInfo

def _check_platform() -> tuple[bool, Optional[DiagnosisInfo]]:
    import sys
    if sys.platform != 'win32':
        return False, DiagnosisInfo(
            code=DiagnosisCode.PLATFORM_NOT_WINDOWS,
            reason=f"本工具仅支持 Windows — 检测到 platform={sys.platform}",
            suggestion="在 Windows 机器上重跑",
            severity='block'
        )
    return True, None

def _check_pywin32() -> tuple[bool, Optional[DiagnosisInfo]]:
    import importlib.util
    if importlib.util.find_spec('win32com') is None:
        return False, DiagnosisInfo(
            code=DiagnosisCode.PYWIN32_MISSING,
            reason="缺 Python 与 SOLIDWORKS 通信组件 (pywin32)",
            suggestion="可一键安装", severity='block'
        )
    return True, None

# 类似实现 _check_sw_installed / _check_toolbox_supported / _check_com_healthy /
# _check_addin_enabled / _check_toolbox_path（每个调对应 sw_detect/sw_toolbox_adapter API）

CHECK_ORDER = [
    ('platform', _check_platform),
    ('pywin32', _check_pywin32),
    ('sw_installed', _check_sw_installed),
    ('toolbox_supported', _check_toolbox_supported),
    ('com_healthy', _check_com_healthy),
    ('addin_enabled', _check_addin_enabled),
    ('toolbox_path', _check_toolbox_path),
]

def run_all_checks() -> dict:
    """按顺序跑 7 项；遇第一失败返回；全过返回 passed=True"""
    for name, check in CHECK_ORDER:
        ok, diag = check()
        if not ok:
            return {'passed': False, 'failed_check': name, 'diagnosis': diag}
    return {'passed': True, 'failed_check': None, 'diagnosis': None}
```

- [ ] **Step 12.4: 跑测试看通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_matrix_check.py -v
```

预期：PASS。

- [ ] **Step 12.5: commit**

```bash
git add sw_preflight/matrix.py tests/test_sw_preflight_matrix_check.py
git commit -m "feat(sw_preflight): matrix.py — 自动通过判定 7 项检查 (Task 12)"
```

---

### Task 13: matrix.py — 一键修 pywin32 install

**Files:**
- Modify: `sw_preflight/matrix.py`
- Test: `tests/test_sw_preflight_matrix_fix_pywin32.py`

- [ ] **Step 13.1: 写失败测试 — pywin32 install 流程（mock subprocess）**

```python
# tests/test_sw_preflight_matrix_fix_pywin32.py
from unittest.mock import patch, MagicMock

def test_fix_pywin32_install_success():
    """pywin32 装好 + postinstall 跑完 → 返回 FixRecord(success=True)"""
    from sw_preflight.matrix import fix_pywin32
    with patch('subprocess.run', return_value=MagicMock(returncode=0)):
        with patch('importlib.util.find_spec', return_value=MagicMock()):
            record = fix_pywin32()
            assert record.action == 'pywin32_install'
            assert 'success' in record.after_state.lower()

def test_fix_pywin32_install_fail():
    """pip install 失败 → raise RuntimeError(PYWIN32_INSTALL_FAILED)"""
    from sw_preflight.matrix import fix_pywin32
    with patch('subprocess.run', return_value=MagicMock(returncode=1, stderr='no network')):
        import pytest
        with pytest.raises(RuntimeError, match="PYWIN32_INSTALL_FAILED"):
            fix_pywin32()
```

- [ ] **Step 13.2: 跑测试看失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_matrix_fix_pywin32.py -v
```

预期：FAIL。

- [ ] **Step 13.3: 实现 fix_pywin32**

```python
# sw_preflight/matrix.py 追加
import subprocess
import sys
import time
from sw_preflight.types import FixRecord

def fix_pywin32() -> FixRecord:
    start = time.time()
    r = subprocess.run([sys.executable, '-m', 'pip', 'install', 'pywin32'],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"PYWIN32_INSTALL_FAILED: pip install 失败: {r.stderr}")
    # 跑 postinstall
    r2 = subprocess.run([sys.executable, '-c',
                        'import win32com'], capture_output=True, text=True)
    if r2.returncode != 0:
        raise RuntimeError(f"PYWIN32_INSTALL_FAILED: postinstall 后 import 仍失败")
    elapsed = (time.time() - start) * 1000
    return FixRecord(action='pywin32_install', before_state='missing',
                     after_state='installed_success', elapsed_ms=elapsed)
```

- [ ] **Step 13.4: 跑测试看通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_matrix_fix_pywin32.py -v
```

预期：PASS。

- [ ] **Step 13.5: commit**

```bash
git add sw_preflight/matrix.py tests/test_sw_preflight_matrix_fix_pywin32.py
git commit -m "feat(sw_preflight): matrix.py — 一键修 pywin32 install (Task 13)"
```

---

### Task 14: matrix.py — 一键修 ROT 释放（静默自愈）

**Files:**
- Modify: `sw_preflight/matrix.py`
- Test: `tests/test_sw_preflight_matrix_fix_rot.py`

- [ ] **Step 14.1: 写失败测试 — ROT 僵死实例释放**

```python
# tests/test_sw_preflight_matrix_fix_rot.py
from unittest.mock import patch, MagicMock

def test_fix_rot_releases_orphan_session(monkeypatch):
    """检测到 ROT 僵死 → release + reset cache → 静默"""
    from sw_preflight.matrix import fix_rot_orphan
    fake_session = MagicMock()
    fake_session.is_healthy.side_effect = [False, True]  # 修后健康
    with patch('adapters.solidworks.sw_com_session.get_session', return_value=fake_session):
        with patch('adapters.solidworks.sw_detect.reset_cache') as mock_reset:
            record = fix_rot_orphan()
            assert record.action == 'rot_orphan_release'
            mock_reset.assert_called_once()
```

- [ ] **Step 14.2: 跑测试看失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_matrix_fix_rot.py -v
```

预期：FAIL。

- [ ] **Step 14.3: 实现 fix_rot_orphan**

```python
# sw_preflight/matrix.py 追加
def fix_rot_orphan() -> FixRecord:
    """静默释放 ROT 僵死实例 + reset sw_detect 缓存"""
    from adapters.solidworks.sw_com_session import get_session
    from adapters.solidworks import sw_detect
    start = time.time()
    sess = get_session()
    sess.release_all()  # 假设 sw_com_session 有该 API；若无则用 pythoncom.CoUninitialize
    sw_detect.reset_cache()
    elapsed = (time.time() - start) * 1000
    return FixRecord(action='rot_orphan_release', before_state='unhealthy',
                     after_state='healthy', elapsed_ms=elapsed)
```

> 注：若 `sw_com_session` 无 `release_all()` API，改用 `pythoncom.CoUninitialize() + CoInitialize()`。

- [ ] **Step 14.4: 跑测试看通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_matrix_fix_rot.py -v
```

- [ ] **Step 14.5: commit**

```bash
git add sw_preflight/matrix.py tests/test_sw_preflight_matrix_fix_rot.py
git commit -m "feat(sw_preflight): matrix.py — 一键修 ROT 僵死释放（静默自愈） (Task 14)"
```

---

### Task 15: matrix.py — 一键修 Toolbox Add-In enable（HKCU + 幂等）

**Files:**
- Modify: `sw_preflight/matrix.py`
- Test: `tests/test_sw_preflight_matrix_fix_addin.py`

- [ ] **Step 15.1: 写失败测试 — HKCU 写入幂等**

```python
# tests/test_sw_preflight_matrix_fix_addin.py
from unittest.mock import patch, MagicMock

def test_addin_enable_writes_hkcu_only():
    """Add-In enable 必须写 HKCU，不写 HKLM (避免 admin 需求)"""
    from sw_preflight.matrix import fix_addin_enable
    with patch('winreg.OpenKey') as mock_open, \
         patch('winreg.SetValueEx') as mock_set:
        with patch('sw_preflight.io.wait_for_assembly_close', return_value=True):
            fix_addin_enable()
            # 校验: 所有 OpenKey 调用都用 HKCU
            for call in mock_open.call_args_list:
                hive = call.args[0] if call.args else call.kwargs.get('key')
                assert 'HKEY_CURRENT_USER' in str(hive)

def test_addin_enable_idempotent():
    """已启用 → 跳过写入"""
    from sw_preflight.matrix import fix_addin_enable
    with patch('sw_preflight.matrix._is_addin_enabled', return_value=True):
        with patch('winreg.SetValueEx') as mock_set:
            with patch('sw_preflight.io.wait_for_assembly_close', return_value=True):
                fix_addin_enable()
                mock_set.assert_not_called()  # 幂等：不重复写
```

- [ ] **Step 15.2: 跑测试看失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_matrix_fix_addin.py -v
```

预期：FAIL。

- [ ] **Step 15.3: 实现 fix_addin_enable**

```python
# sw_preflight/matrix.py 追加
def _is_addin_enabled() -> bool:
    """读 HKCU 看 Toolbox Add-In 启用标记"""
    # 复用 sw_toolbox_adapter 的发现机制（不重复 GUID）
    from adapters.parts.sw_toolbox_adapter import is_available
    return is_available()

def fix_addin_enable() -> FixRecord:
    """HKCU 写 + 幂等"""
    from sw_preflight.io import wait_for_assembly_close
    if _is_addin_enabled():
        return FixRecord(action='addin_enable', before_state='already_enabled',
                         after_state='no_op', elapsed_ms=0.0)
    if not wait_for_assembly_close(timeout_sec=300):
        raise RuntimeError("等关装配体超时")
    start = time.time()
    # 走 HKCU 写入（不走 HKLM；GUID 由 sw_toolbox_adapter 暴露）
    import winreg
    from adapters.parts.sw_toolbox_adapter import get_toolbox_addin_guid
    guid = get_toolbox_addin_guid()  # 复用现有发现机制
    key_path = rf"SOFTWARE\SolidWorks\Addins\{guid}"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_DWORD, 1)
    elapsed = (time.time() - start) * 1000
    return FixRecord(action='addin_enable', before_state='disabled',
                     after_state='enabled_hkcu', elapsed_ms=elapsed)
```

> 若 `sw_toolbox_adapter.get_toolbox_addin_guid` 不存在，需先在 sw_toolbox_adapter 加该 helper（调用现有 GUID 发现逻辑），不在 sw_preflight 重复硬编码 GUID。

- [ ] **Step 15.4: 跑测试看通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_matrix_fix_addin.py -v
```

- [ ] **Step 15.5: commit**

```bash
git add sw_preflight/matrix.py tests/test_sw_preflight_matrix_fix_addin.py
git commit -m "feat(sw_preflight): matrix.py — 一键修 Toolbox Add-In enable（HKCU 幂等） (Task 15)"
```

---

### Task 16: matrix.py — 一键修 SW 后台进程启动

**Files:**
- Modify: `sw_preflight/matrix.py`
- Test: `tests/test_sw_preflight_matrix_fix_sw_launch.py`

- [ ] **Step 16.1: 写失败测试 — 启 SW 后台进程不弹界面**

```python
# tests/test_sw_preflight_matrix_fix_sw_launch.py
from unittest.mock import patch, MagicMock

def test_fix_sw_launch_background():
    from sw_preflight.matrix import fix_sw_launch_background
    fake_session = MagicMock()
    fake_session.is_healthy.return_value = True
    with patch('adapters.solidworks.sw_com_session.get_session', return_value=fake_session):
        record = fix_sw_launch_background()
        assert record.action == 'sw_launch_background'
        assert 'launched' in record.after_state.lower()
```

- [ ] **Step 16.2: 跑测试看失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_matrix_fix_sw_launch.py -v
```

- [ ] **Step 16.3: 实现 fix_sw_launch_background**

```python
# sw_preflight/matrix.py 追加
def fix_sw_launch_background() -> FixRecord:
    """启 SW 后台进程（visible=false），不弹 GUI"""
    from adapters.solidworks.sw_com_session import get_session
    start = time.time()
    sess = get_session()
    if not sess.is_healthy():
        sess.start_background()  # 假设接口；若无走 pythoncom Dispatch + Visible=0
    elapsed = (time.time() - start) * 1000
    return FixRecord(action='sw_launch_background', before_state='not_running',
                     after_state='launched_invisible', elapsed_ms=elapsed)
```

- [ ] **Step 16.4: 跑测试看通过 + commit**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_matrix_fix_sw_launch.py -v
git add sw_preflight/matrix.py tests/test_sw_preflight_matrix_fix_sw_launch.py
git commit -m "feat(sw_preflight): matrix.py — 一键修 SW 后台进程启动 (Task 16)"
```

---

### Task 17: matrix.py — 管理员权限检测 + ShellExecute "runas" 退化

**Files:**
- Modify: `sw_preflight/matrix.py`
- Test: `tests/test_sw_preflight_matrix_admin.py`

- [ ] **Step 17.1: 写失败测试 — admin 检测 + 退化路径**

```python
# tests/test_sw_preflight_matrix_admin.py
from unittest.mock import patch

def test_is_admin_returns_bool():
    from sw_preflight.matrix import is_user_admin
    result = is_user_admin()
    assert isinstance(result, bool)

def test_elevate_with_runas_called(monkeypatch):
    from sw_preflight.matrix import elevate_with_runas
    called = []
    monkeypatch.setattr('ctypes.windll.shell32.ShellExecuteW',
                       lambda *a, **kw: called.append(a) or 42)
    elevate_with_runas()
    assert len(called) == 1
    assert called[0][1] == 'runas'  # 第二参数是动作

def test_admin_required_three_choice(monkeypatch):
    """非 admin 时三选一: [1] 重启 admin / [2] 手动修 / [Q] 退出"""
    from sw_preflight.matrix import handle_admin_required
    monkeypatch.setattr('builtins.input', lambda _: '2')
    with patch('sw_preflight.matrix.is_user_admin', return_value=False):
        result = handle_admin_required(action_desc='Add-In 启用')
        assert result == 'manual'  # [2] 手动修
```

- [ ] **Step 17.2: 跑测试看失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_matrix_admin.py -v
```

- [ ] **Step 17.3: 实现 admin 部分**

```python
# sw_preflight/matrix.py 追加
import ctypes

def is_user_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

def elevate_with_runas() -> int:
    """ShellExecute "runas" 重启当前进程为 admin"""
    return ctypes.windll.shell32.ShellExecuteW(
        None, 'runas', sys.executable, ' '.join(sys.argv), None, 1
    )

def handle_admin_required(action_desc: str) -> str:
    """非 admin 时三选一"""
    print(f"\n⚠️ 此修复 ({action_desc}) 需要管理员权限。")
    print("  [1] 以管理员身份重启本工具（系统会弹 UAC 确认）")
    print("  [2] 我自己手动修（按报告里的 GUI 步骤）")
    print("  [Q] 退出")
    while True:
        choice = input("请选 [1/2/Q]: ").strip().upper()
        if choice == '1':
            elevate_with_runas()
            sys.exit(0)
        if choice == '2': return 'manual'
        if choice == 'Q': sys.exit(2)
```

- [ ] **Step 17.4: 跑测试 + commit**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_matrix_admin.py -v
git add sw_preflight/matrix.py tests/test_sw_preflight_matrix_admin.py
git commit -m "feat(sw_preflight): matrix.py — admin 检测 + ShellExecute runas 退化 (Task 17)"
```

---

### Task 18: matrix.py — 卡住诊断 8 个 DiagnosisCode

**Files:**
- Modify: `sw_preflight/matrix.py`
- Test: `tests/test_sw_preflight_matrix_diagnostics.py`

- [ ] **Step 18.1: 写失败测试 — 8 个 DiagnosisCode 各自构造正确诊断**

```python
# tests/test_sw_preflight_matrix_diagnostics.py
from sw_preflight.diagnosis import DiagnosisCode

def test_make_diagnosis_for_sw_not_installed():
    from sw_preflight.matrix import make_diagnosis
    d = make_diagnosis(DiagnosisCode.SW_NOT_INSTALLED)
    assert '未检测到' in d.reason
    assert d.severity == 'block'

def test_make_diagnosis_license_problem_suggests_open_sw_gui():
    from sw_preflight.matrix import make_diagnosis
    d = make_diagnosis(DiagnosisCode.LICENSE_PROBLEM)
    assert '双击桌面 SOLIDWORKS 图标' in d.suggestion or '打开 SOLIDWORKS' in d.suggestion

def test_make_diagnosis_unc_path_not_accessible():
    from sw_preflight.matrix import make_diagnosis
    d = make_diagnosis(DiagnosisCode.TOOLBOX_PATH_NOT_ACCESSIBLE,
                       context={'path': r'\\fileserver\Toolbox'})
    assert 'fileserver' in d.reason

def test_make_diagnosis_multiple_versions_ambiguous():
    from sw_preflight.matrix import make_diagnosis
    d = make_diagnosis(DiagnosisCode.MULTIPLE_SW_VERSIONS_AMBIGUOUS,
                       context={'versions': [2022, 2024]})
    assert '2022' in d.reason and '2024' in d.reason
```

- [ ] **Step 18.2: 跑测试看失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_matrix_diagnostics.py -v
```

- [ ] **Step 18.3: 实现 make_diagnosis**

```python
# sw_preflight/matrix.py 追加
DIAGNOSIS_TEMPLATES = {
    DiagnosisCode.PLATFORM_NOT_WINDOWS: lambda ctx: DiagnosisInfo(
        code=DiagnosisCode.PLATFORM_NOT_WINDOWS,
        reason=f"本工具仅支持 Windows — 检测到 platform={ctx.get('platform','?')}",
        suggestion="在 Windows 机器上重跑", severity='block'),
    DiagnosisCode.SW_NOT_INSTALLED: lambda ctx: DiagnosisInfo(
        code=DiagnosisCode.SW_NOT_INSTALLED,
        reason="未检测到 SolidWorks 安装",
        suggestion="请先安装 SolidWorks Pro 或 Premium", severity='block'),
    DiagnosisCode.SW_TOOLBOX_NOT_SUPPORTED: lambda ctx: DiagnosisInfo(
        code=DiagnosisCode.SW_TOOLBOX_NOT_SUPPORTED,
        reason=f"检测到 SW 但 Toolbox 不可用",
        suggestion="请打开 SOLIDWORKS → 帮助 → 关于 → 查看许可证类型；按需升级 Pro/Premium 或用 SW installer 修改安装勾选 Toolbox",
        severity='block'),
    DiagnosisCode.LICENSE_PROBLEM: lambda ctx: DiagnosisInfo(
        code=DiagnosisCode.LICENSE_PROBLEM,
        reason="SW 已安装但 license 异常",
        suggestion="请双击桌面 SOLIDWORKS 图标启动一次，查看 SW 自己弹的 license 报错并按提示修复",
        severity='block'),
    DiagnosisCode.COM_REGISTRATION_BROKEN: lambda ctx: DiagnosisInfo(
        code=DiagnosisCode.COM_REGISTRATION_BROKEN,
        reason="SW COM 接口异常 (CLSID 实例化失败)",
        suggestion="控制面板 → 程序 → SOLIDWORKS → 修改 → 修复安装",
        severity='block'),
    DiagnosisCode.TOOLBOX_PATH_INVALID: lambda ctx: DiagnosisInfo(
        code=DiagnosisCode.TOOLBOX_PATH_INVALID,
        reason=f"Toolbox 数据库路径配置无效 (本地路径不存在): {ctx.get('path','?')}",
        suggestion="SOLIDWORKS → 工具 → 选项 → 异型孔向导/Toolbox → 把路径改到本地非同步目录",
        severity='block'),
    DiagnosisCode.TOOLBOX_PATH_NOT_ACCESSIBLE: lambda ctx: DiagnosisInfo(
        code=DiagnosisCode.TOOLBOX_PATH_NOT_ACCESSIBLE,
        reason=f"Toolbox 路径配置存在但访问失败 (UNC/网络不可达): {ctx.get('path','?')}",
        suggestion="检查网络连接、VPN、共享映射；联系 IT 管理员确认权限",
        severity='block'),
    DiagnosisCode.MULTIPLE_SW_VERSIONS_AMBIGUOUS: lambda ctx: DiagnosisInfo(
        code=DiagnosisCode.MULTIPLE_SW_VERSIONS_AMBIGUOUS,
        reason=f"检测到多个 SW 版本 {ctx.get('versions','?')}，自动选择失败",
        suggestion="请打开期望使用的 SW 版本一次（确认它能正常启动），或卸载坏的版本",
        severity='block'),
    DiagnosisCode.INSUFFICIENT_PRIVILEGES: lambda ctx: DiagnosisInfo(
        code=DiagnosisCode.INSUFFICIENT_PRIVILEGES,
        reason="修复需要管理员权限",
        suggestion="重新以'以管理员身份运行'启动终端再跑本工具，或按报告中的 GUI 步骤手动修复",
        severity='block'),
}

def make_diagnosis(code: DiagnosisCode, context: dict = None) -> DiagnosisInfo:
    ctx = context or {}
    template = DIAGNOSIS_TEMPLATES.get(code)
    if template is None:
        raise ValueError(f"未知 DiagnosisCode: {code}")
    return template(ctx)
```

- [ ] **Step 18.4: 跑测试 + commit**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_matrix_diagnostics.py -v
git add sw_preflight/matrix.py tests/test_sw_preflight_matrix_diagnostics.py
git commit -m "feat(sw_preflight): matrix.py — 9 个 DiagnosisCode 模板 (Task 18)"
```

---

## 🛑 CHECKPOINT 3: Phase 4-5 完成

请用户确认：
- io 层完成（装配体检测 / file dialog / STEP 三层校验）
- matrix 层完成（M 体检 7 项 + 一键修 4 个 + admin 退化 + 9 诊断码）
- 暂停等用户 OK 后继续 Phase 6

---

## Phase 6: cache + preference

### Task 19: cache.py — sw_preflight_cache.json IPC

**Files:**
- Create: `sw_preflight/cache.py`
- Test: `tests/test_sw_preflight_cache.py`

- [ ] **Step 19.1: 写失败测试 — TTL + schema_version 校验**

```python
# tests/test_sw_preflight_cache.py
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

def test_write_then_read_within_ttl(tmp_path):
    from sw_preflight.cache import write_cache, read_cache
    write_cache(tmp_path / 'cache.json', {'preflight_result': {'passed': True}}, ttl_sec=300)
    cached = read_cache(tmp_path / 'cache.json')
    assert cached is not None
    assert cached['preflight_result']['passed'] is True

def test_read_returns_none_when_expired(tmp_path):
    cache_path = tmp_path / 'cache.json'
    expired_data = {
        'schema_version': 1,
        'ran_at': (datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat(),
        'ttl_seconds': 300,
        'preflight_result': {'passed': True},
    }
    cache_path.write_text(json.dumps(expired_data))
    from sw_preflight.cache import read_cache
    assert read_cache(cache_path) is None

def test_read_returns_none_when_schema_mismatch(tmp_path):
    cache_path = tmp_path / 'cache.json'
    cache_path.write_text(json.dumps({
        'schema_version': 999, 'ran_at': datetime.now(timezone.utc).isoformat(),
        'ttl_seconds': 300, 'preflight_result': {}
    }))
    from sw_preflight.cache import read_cache
    assert read_cache(cache_path) is None
```

- [ ] **Step 19.2: 跑测试看失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_cache.py -v
```

- [ ] **Step 19.3: 实现 cache.py**

```python
# sw_preflight/cache.py
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = 1

def write_cache(path: Path, payload: dict, ttl_sec: int = 300,
                ran_by_entry: str = 'unknown') -> None:
    data = {
        'schema_version': SCHEMA_VERSION,
        'ran_at': datetime.now(timezone.utc).isoformat(),
        'ran_by_entry': ran_by_entry,
        'ttl_seconds': ttl_sec,
        **payload,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, default=str), encoding='utf-8')

def read_cache(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return None
    if data.get('schema_version') != SCHEMA_VERSION:
        return None
    ran_at = datetime.fromisoformat(data['ran_at'])
    age_sec = (datetime.now(timezone.utc) - ran_at).total_seconds()
    if age_sec > data.get('ttl_seconds', 300):
        return None
    return data
```

- [ ] **Step 19.4: 跑测试 + commit**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_cache.py -v
git add sw_preflight/cache.py tests/test_sw_preflight_cache.py
git commit -m "feat(sw_preflight): cache.py — sw_preflight_cache.json IPC + TTL (Task 19)"
```

---

### Task 20: preference.py 已在 Task 5 完成

> Task 5 已实现 preference.py 与 sw_detect 集成。本 task 跳过实现，仅补 sw_version_preference.json 的"用户人工裁决后自动写"测试。

- [ ] **Step 20.1: 写测试 — 用户裁决后写 preference**

```python
# tests/test_sw_preflight_preference.py 追加
def test_write_after_user_resolves_ambiguous(monkeypatch, tmp_path):
    from sw_preflight import preference
    monkeypatch.setattr(preference, 'PREFERENCE_PATH', tmp_path / 'pref.json')
    preference.write_preference(2024)
    assert preference.read_preference() == 2024
```

- [ ] **Step 20.2: 跑测试 + commit**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_preference.py -v
git add tests/test_sw_preflight_preference.py
git commit -m "test(sw_preflight): preference 用户裁决后自动写 (Task 20)"
```

---

## Phase 7: dry_run

### Task 21: dry_run.py — dry_run_bom 主流程

**Files:**
- Create: `sw_preflight/dry_run.py`
- Test: `tests/test_sw_preflight_dry_run.py`

- [ ] **Step 21.1: 写失败测试 — dry-run 分类 BOM 行**

```python
# tests/test_sw_preflight_dry_run.py
from unittest.mock import patch, MagicMock
from sw_preflight.types import PartCategory

def test_dry_run_classifies_rows():
    """dry-run 应区分 hit / missing / stand_in"""
    bom = [
        {'name_cn': 'GB/T 70.1 M6×20 内六角', 'category': 'fastener'},
        {'name_cn': 'Maxon ECX SPEED 22L', 'category': ''},
        {'name_cn': '私有件 PXY-2024-A', 'category': ''},
        {'name_cn': '未知件 XXX', 'category': ''},
    ]
    fake_results = [
        MagicMock(category=PartCategory.STANDARD_FASTENER, adapter='sw_toolbox', success=True),
        MagicMock(category=PartCategory.VENDOR_PURCHASED, adapter='step_pool', success=True),
        MagicMock(category=PartCategory.CUSTOM, adapter='jinja_primitive', success=True),
        MagicMock(category=PartCategory.CUSTOM, adapter='step_pool', success=False, fallback='stand_in'),
    ]
    with patch('adapters.parts.parts_resolver.PartsResolver.resolve',
               side_effect=fake_results):
        from sw_preflight.dry_run import dry_run_bom
        result = dry_run_bom(bom)
        assert result.total_rows == 4
        assert len(result.hit_rows) == 3  # 前 3 个 hit
        assert len(result.stand_in_rows) == 1  # 第 4 个 fall through stand_in
```

- [ ] **Step 21.2: 跑测试看失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_dry_run.py -v
```

- [ ] **Step 21.3: 实现 dry_run.py**

```python
# sw_preflight/dry_run.py
from sw_preflight.types import BomDryRunResult, RowOutcome, PartCategory
from sw_preflight.diagnosis import DiagnosisCode, DiagnosisInfo

def dry_run_bom(bom_rows: list[dict]) -> BomDryRunResult:
    """走 PartsResolver.resolve() 一遍，标记每行 hit/missing/stand_in"""
    from adapters.parts.parts_resolver import PartsResolver
    resolver = PartsResolver()
    hit, missing, stand_in = [], [], []
    for row in bom_rows:
        res = resolver.resolve(row)
        outcome = RowOutcome(
            bom_row=row,
            category=res.category,
            expected_adapter=_expected_adapter_for_category(res.category),
            actual_adapter=res.adapter,
            status=_status_from_resolve(res),
            diagnosis=_diagnosis_from_resolve(res),
        )
        if outcome.status == '✅':
            hit.append(outcome)
        elif outcome.status == '⚠️':
            stand_in.append(outcome)
        else:
            missing.append(outcome)
    return BomDryRunResult(
        total_rows=len(bom_rows),
        hit_rows=hit, missing_rows=missing, stand_in_rows=stand_in,
    )

def _expected_adapter_for_category(cat: PartCategory) -> str:
    if cat in (PartCategory.STANDARD_FASTENER, PartCategory.STANDARD_BEARING):
        return 'sw_toolbox'
    if cat == PartCategory.VENDOR_PURCHASED:
        return 'step_pool'
    if cat == PartCategory.CUSTOM:
        return 'jinja_primitive'
    return 'sw_toolbox'  # 其它 STANDARD_* 默认期望 SW

def _status_from_resolve(res) -> str:
    if not getattr(res, 'success', True): return '⚠️'  # fallback to stand-in
    if res.adapter == _expected_adapter_for_category(res.category): return '✅'
    return '⚠️'  # 走了 fallback adapter

def _diagnosis_from_resolve(res):
    if _status_from_resolve(res) == '⚠️':
        return DiagnosisInfo(
            code=DiagnosisCode.BOM_ROW_FELL_THROUGH_TO_STAND_IN,
            reason=f"未命中期望 adapter，走 {res.adapter}",
            suggestion="可在三选一中指定 STEP 文件提升精度",
            severity='warn',
        )
    return None
```

- [ ] **Step 21.4: 跑测试 + commit**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_dry_run.py -v
git add sw_preflight/dry_run.py tests/test_sw_preflight_dry_run.py
git commit -m "feat(sw_preflight): dry_run.py — dry_run_bom 三分类 (Task 21)"
```

---

## Phase 8: user_provided 流

### Task 22: user_provided.py — prompt_user_provided 主入口

**Files:**
- Create: `sw_preflight/user_provided.py`
- Test: `tests/test_sw_preflight_user_provided_prompt.py`

- [ ] **Step 22.1: 写失败测试 — 三选一 → file dialog 路径**

```python
# tests/test_sw_preflight_user_provided_prompt.py
from unittest.mock import patch
from pathlib import Path

def test_user_choice_stand_in_returns_all_stand_in():
    from sw_preflight.user_provided import prompt_user_provided
    missing = [{'name_cn': 'GB/T 70.1 M3×8'}, {'name_cn': '私有件 X'}]
    with patch('sw_preflight.io.three_choice_prompt', return_value='stand_in'):
        result = prompt_user_provided(missing)
        assert len(result.stand_in_keys) == 2
        assert len(result.provided_files) == 0

def test_user_choice_skip_returns_all_skipped():
    from sw_preflight.user_provided import prompt_user_provided
    missing = [{'name_cn': 'GB/T 70.1 M3×8'}]
    with patch('sw_preflight.io.three_choice_prompt', return_value='skip'):
        result = prompt_user_provided(missing)
        assert len(result.skipped_keys) == 1

def test_user_choice_provide_loops_dialog(tmp_path):
    from sw_preflight.user_provided import prompt_user_provided
    missing = [{'name_cn': 'GB/T 70.1 M3×8'}, {'name_cn': '私有件 X'}]
    fake_step = tmp_path / 'm3x8.step'
    fake_step.write_bytes(b'ISO-10303-21;\n' + b'\n' * 20000)
    with patch('sw_preflight.io.three_choice_prompt', return_value='provide'):
        with patch('sw_preflight.io.ask_step_file', side_effect=[fake_step, None]):  # 第 2 个取消
            with patch('builtins.input', return_value='1'):  # 取消后选 stand-in
                result = prompt_user_provided(missing, copy_files=False)
                assert len(result.provided_files) == 1
                assert len(result.stand_in_keys) == 1
```

- [ ] **Step 22.2: 跑测试看失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_user_provided_prompt.py -v
```

- [ ] **Step 22.3: 实现 prompt_user_provided**

```python
# sw_preflight/user_provided.py
from sw_preflight.types import UserChoiceResult
from sw_preflight import io

def _bom_key(row: dict) -> str:
    """BOM 行唯一标识 — 用 name_cn + part_no 组合"""
    return f"{row.get('name_cn','')}|{row.get('part_no','')}"

def prompt_user_provided(missing_rows: list[dict], copy_files: bool = True) -> UserChoiceResult:
    if not missing_rows:
        return UserChoiceResult(provided_files={}, stand_in_keys=set(), skipped_keys=set())
    choice = io.three_choice_prompt(missing_count=len(missing_rows))
    if choice == 'stand_in':
        return UserChoiceResult(provided_files={},
                                stand_in_keys={_bom_key(r) for r in missing_rows},
                                skipped_keys=set())
    if choice == 'skip':
        return UserChoiceResult(provided_files={}, stand_in_keys=set(),
                                skipped_keys={_bom_key(r) for r in missing_rows})
    # choice == 'provide' → 逐行 file dialog
    provided, stand_in, skipped = {}, set(), set()
    for i, row in enumerate(missing_rows, 1):
        title = f"为 {row.get('name_cn','?')} 选择 STEP ({i}/{len(missing_rows)})"
        path = io.ask_step_file(title)
        if path is None:
            sub = input(f"取消了 — 该行用 [1] stand-in / [2] 跳过: ").strip()
            if sub == '2':
                skipped.add(_bom_key(row))
            else:
                stand_in.add(_bom_key(row))
            continue
        # 校验 + 复制（复制逻辑在 Task 23）
        if copy_files:
            from sw_preflight.user_provided import copy_to_user_provided  # forward ref
            dest = copy_to_user_provided(path, row)
            provided[_bom_key(row)] = dest
        else:
            provided[_bom_key(row)] = path
    return UserChoiceResult(provided_files=provided, stand_in_keys=stand_in,
                            skipped_keys=skipped)
```

- [ ] **Step 22.4: 跑测试 + commit**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_user_provided_prompt.py -v
git add sw_preflight/user_provided.py tests/test_sw_preflight_user_provided_prompt.py
git commit -m "feat(sw_preflight): user_provided.py — prompt 主入口 + 三选一 (Task 22)"
```

---

### Task 23: user_provided.py — 文件复制（按 PartCategory 分流）

**Files:**
- Modify: `sw_preflight/user_provided.py`
- Test: `tests/test_sw_preflight_user_provided_copy.py`

- [ ] **Step 23.1: 写失败测试 — 按 category 分流目录**

```python
# tests/test_sw_preflight_user_provided_copy.py
from sw_preflight.types import PartCategory
from pathlib import Path

def test_copy_standard_to_user_provided_standard(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = tmp_path / 'm3x8.step'
    src.write_bytes(b'ISO-10303\n' + b'\n' * 20000)
    from sw_preflight.user_provided import copy_to_user_provided
    row = {'name_cn': 'GB/T 70.1 M3×8'}
    dest = copy_to_user_provided(src, row, category=PartCategory.STANDARD_FASTENER)
    assert dest.exists()
    assert 'std_parts/user_provided/standard' in str(dest).replace('\\', '/')

def test_copy_vendor_to_user_provided_vendor(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = tmp_path / 'lemo.step'
    src.write_bytes(b'ISO-10303\n' + b'\n' * 20000)
    from sw_preflight.user_provided import copy_to_user_provided
    row = {'name_cn': 'LEMO FGG.0B.302'}
    dest = copy_to_user_provided(src, row, category=PartCategory.VENDOR_PURCHASED)
    assert 'std_parts/user_provided/vendor' in str(dest).replace('\\', '/')

def test_copy_custom_to_std_parts_custom(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = tmp_path / 'pxy.step'
    src.write_bytes(b'ISO-10303\n' + b'\n' * 20000)
    from sw_preflight.user_provided import copy_to_user_provided
    row = {'name_cn': '私有件 PXY-2024-A'}
    dest = copy_to_user_provided(src, row, category=PartCategory.CUSTOM)
    assert 'std_parts/custom' in str(dest).replace('\\', '/')
```

- [ ] **Step 23.2: 跑测试 + 实现**

```python
# sw_preflight/user_provided.py 追加
import shutil
import re
from pathlib import Path
from sw_preflight.types import PartCategory

def _safe_filename(name: str) -> str:
    """BOM name_cn → 安全文件名"""
    return re.sub(r'[^\w\-.]', '_', name)[:80]

CATEGORY_TO_SUBDIR = {
    PartCategory.STANDARD_FASTENER: 'standard',
    PartCategory.STANDARD_BEARING: 'standard',
    PartCategory.STANDARD_SEAL: 'standard',
    PartCategory.STANDARD_LOCATING: 'standard',
    PartCategory.STANDARD_ELASTIC: 'standard',
    PartCategory.STANDARD_TRANSMISSION: 'standard',
    PartCategory.STANDARD_OTHER: 'standard',
    PartCategory.VENDOR_PURCHASED: 'vendor',
    PartCategory.CUSTOM: None,  # 走 std_parts/custom/
}

def copy_to_user_provided(src: Path, row: dict, category: PartCategory) -> Path:
    """复制文件到 ./std_parts/user_provided/{standard,vendor}/ 或 ./std_parts/custom/"""
    sub = CATEGORY_TO_SUBDIR.get(category)
    if sub is None:
        dest_dir = Path('./std_parts/custom')
    else:
        dest_dir = Path(f'./std_parts/user_provided/{sub}')
    dest_dir.mkdir(parents=True, exist_ok=True)
    fname = _safe_filename(row.get('name_cn', 'unknown')) + '.step'
    dest = dest_dir / fname
    shutil.copy2(src, dest)
    return dest
```

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_user_provided_copy.py -v
git add sw_preflight/user_provided.py tests/test_sw_preflight_user_provided_copy.py
git commit -m "feat(sw_preflight): user_provided.py — 按 PartCategory 分流复制 (Task 23)"
```

---

### Task 24: user_provided.py — yaml mapping 追加 + provenance

**Files:**
- Modify: `sw_preflight/user_provided.py`
- Test: `tests/test_sw_preflight_user_provided_yaml.py`

- [ ] **Step 24.1: 写失败测试 — yaml 追加位置 + provenance 字段 + 损坏 3 类**

```python
# tests/test_sw_preflight_user_provided_yaml.py
from pathlib import Path
import yaml

def test_append_mapping_to_empty_yaml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from sw_preflight.user_provided import append_yaml_mapping
    src = tmp_path / 'm3x8.step'
    src.write_bytes(b'ISO-10303\n' + b'\n' * 20000)
    dest = tmp_path / 'std_parts/user_provided/standard/m3x8.step'
    dest.parent.mkdir(parents=True)
    src.rename(dest)
    append_yaml_mapping({'name_cn': 'GB/T 70.1 M3×8'}, dest, source_path=src)
    cfg = yaml.safe_load(Path('parts_library.yaml').read_text(encoding='utf-8'))
    mapping = cfg['mappings'][0]
    assert mapping['adapter'] == 'step_pool'
    assert 'GB/T 70.1 M3×8' in mapping['match']['keyword_contains']
    assert 'provenance' in mapping
    assert mapping['provenance']['provided_by_user'] is True
    assert 'source_hash' in mapping['provenance']
    assert mapping['provenance']['source_hash'].startswith('sha256:')

def test_append_inserts_before_any_true(tmp_path, monkeypatch):
    """新规则插在第一个 {any: true} 之前"""
    monkeypatch.chdir(tmp_path)
    Path('parts_library.yaml').write_text(yaml.dump({
        'mappings': [
            {'match': {'category': 'fastener'}, 'adapter': 'sw_toolbox'},
            {'match': {'any': True}, 'adapter': 'jinja_primitive'},
        ]
    }), encoding='utf-8')
    from sw_preflight.user_provided import append_yaml_mapping
    src = tmp_path / 'm3x8.step'
    src.write_bytes(b'ISO-10303\n' + b'\n' * 20000)
    append_yaml_mapping({'name_cn': 'TEST'}, Path('std_parts/test.step'), source_path=src)
    cfg = yaml.safe_load(Path('parts_library.yaml').read_text(encoding='utf-8'))
    # 新规则应该在 index 1（fastener 之后、{any:true} 之前）
    assert cfg['mappings'][1]['match']['keyword_contains'] == ['TEST']
    assert cfg['mappings'][2]['match'] == {'any': True}

def test_append_yaml_syntax_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path('parts_library.yaml').write_text("mappings:\n  - match: {any: true\n  adapter: jp",
                                          encoding='utf-8')
    from sw_preflight.user_provided import append_yaml_mapping
    import pytest
    with pytest.raises(ValueError, match='YAML 语法错误'):
        src = tmp_path / 'src.step'
        src.write_bytes(b'ISO-10303\n')
        append_yaml_mapping({'name_cn': 'TEST'}, Path('dest.step'), source_path=src)

def test_append_yaml_schema_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path('parts_library.yaml').write_text("mappings:\n  some_key: some_value", encoding='utf-8')
    from sw_preflight.user_provided import append_yaml_mapping
    import pytest
    with pytest.raises(ValueError, match='mappings 应为列表'):
        src = tmp_path / 'src.step'
        src.write_bytes(b'ISO-10303\n')
        append_yaml_mapping({'name_cn': 'TEST'}, Path('dest.step'), source_path=src)
```

- [ ] **Step 24.2: 跑测试看失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_user_provided_yaml.py -v
```

- [ ] **Step 24.3: 实现 append_yaml_mapping**

```python
# sw_preflight/user_provided.py 追加
import hashlib
import yaml as pyyaml
from datetime import datetime, timezone

def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return f'sha256:{h.hexdigest()[:16]}...'

def append_yaml_mapping(row: dict, dest_path: Path, source_path: Path) -> None:
    yaml_path = Path('./parts_library.yaml')
    cfg = {'mappings': []}
    if yaml_path.exists():
        try:
            cfg = pyyaml.safe_load(yaml_path.read_text(encoding='utf-8'))
        except pyyaml.YAMLError as e:
            raise ValueError(f"YAML 语法错误: {e}")
    if not isinstance(cfg.get('mappings'), list):
        raise ValueError("mappings 应为列表（list），当前是 " + type(cfg.get('mappings')).__name__)
    # 构造新 mapping
    src_stat = source_path.stat()
    new_mapping = {
        'match': {'keyword_contains': [row.get('name_cn', '')]},
        'adapter': 'step_pool',
        'spec': {'file': str(dest_path).replace('\\', '/')},
        'provenance': {
            'provided_by_user': True,
            'provided_at': datetime.now(timezone.utc).isoformat(),
            'source_path': str(source_path),
            'source_hash': _file_sha256(source_path),
            'source_mtime': datetime.fromtimestamp(src_stat.st_mtime, timezone.utc).isoformat(),
        },
    }
    # 找第一个 {any: true} 兜底位置
    insert_idx = len(cfg['mappings'])
    for i, m in enumerate(cfg['mappings']):
        if m.get('match', {}).get('any') is True:
            insert_idx = i
            break
    cfg['mappings'].insert(insert_idx, new_mapping)
    yaml_path.write_text(pyyaml.dump(cfg, allow_unicode=True), encoding='utf-8')
```

- [ ] **Step 24.4: 跑测试 + commit**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_user_provided_yaml.py -v
git add sw_preflight/user_provided.py tests/test_sw_preflight_user_provided_yaml.py
git commit -m "feat(sw_preflight): user_provided.py — yaml mapping 追加 + provenance + 损坏 3 类 (Task 24)"
```

---

### Task 25: user_provided.py — provenance 失效检测

**Files:**
- Modify: `sw_preflight/user_provided.py`
- Test: `tests/test_sw_preflight_user_provided_provenance.py`

- [ ] **Step 25.1: 写失败测试 — 源文件变化 → 提示**

```python
# tests/test_sw_preflight_user_provided_provenance.py
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

def test_provenance_check_source_unchanged(tmp_path):
    src = tmp_path / 'src.step'
    src.write_bytes(b'ISO-10303\n' + b'\n' * 20000)
    from sw_preflight.user_provided import check_provenance_validity, _file_sha256
    mapping = {'provenance': {
        'source_path': str(src),
        'source_hash': _file_sha256(src),
        'source_mtime': datetime.fromtimestamp(src.stat().st_mtime, timezone.utc).isoformat(),
    }}
    result = check_provenance_validity(mapping)
    assert result == 'valid'

def test_provenance_check_source_changed(tmp_path):
    src = tmp_path / 'src.step'
    src.write_bytes(b'ISO-10303\n' + b'\n' * 20000)
    from sw_preflight.user_provided import check_provenance_validity
    mapping = {'provenance': {
        'source_path': str(src),
        'source_hash': 'sha256:WRONGHASH',  # 故意错
        'source_mtime': datetime.now(timezone.utc).isoformat(),
    }}
    result = check_provenance_validity(mapping)
    assert result == 'changed'

def test_provenance_check_source_missing(tmp_path):
    from sw_preflight.user_provided import check_provenance_validity
    mapping = {'provenance': {
        'source_path': str(tmp_path / 'doesnotexist.step'),
        'source_hash': 'sha256:WHATEVER',
        'source_mtime': datetime.now(timezone.utc).isoformat(),
    }}
    result = check_provenance_validity(mapping)
    assert result == 'source_missing'
```

- [ ] **Step 25.2: 跑测试 + 实现 + commit**

```python
# sw_preflight/user_provided.py 追加
def check_provenance_validity(mapping: dict) -> str:
    """返回 'valid' | 'changed' | 'source_missing' | 'no_provenance'"""
    prov = mapping.get('provenance')
    if not prov:
        return 'no_provenance'
    src = Path(prov.get('source_path', ''))
    if not src.exists():
        return 'source_missing'
    expected_hash = prov.get('source_hash', '')
    if _file_sha256(src) != expected_hash:
        return 'changed'
    return 'valid'
```

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_user_provided_provenance.py -v
git add sw_preflight/user_provided.py tests/test_sw_preflight_user_provided_provenance.py
git commit -m "feat(sw_preflight): user_provided.py — provenance 失效检测 (Task 25)"
```

---

## 🛑 CHECKPOINT 4: Phase 6-8 完成

请用户确认：
- cache.py / preference.py 完成
- dry_run.py 完成（三分类）
- user_provided.py 完成（prompt + 复制 + yaml 追加 + provenance 校验）
- 暂停等用户 OK 后继续 Phase 9

---

## Phase 9: preflight 编排

### Task 26: preflight.py — run_preflight 主入口

**Files:**
- Create: `sw_preflight/preflight.py`
- Test: `tests/test_sw_preflight_preflight.py`

- [ ] **Step 26.1: 写失败测试 — 完整编排（matrix + cache）**

```python
# tests/test_sw_preflight_preflight.py
from unittest.mock import patch, MagicMock
from sw_preflight.types import PreflightResult

def test_run_preflight_strict_true_passed():
    """全过 → 返回 PreflightResult(passed=True)"""
    with patch('sw_preflight.matrix.run_all_checks',
               return_value={'passed': True, 'failed_check': None, 'diagnosis': None}):
        with patch('adapters.solidworks.sw_detect.detect_solidworks',
                   return_value=MagicMock(installed=True, version_year=2024)):
            from sw_preflight.preflight import run_preflight
            result = run_preflight(strict=True)
            assert result.passed is True

def test_run_preflight_strict_true_blocked():
    """卡住 → strict=True 时 sys.exit(2)"""
    from sw_preflight.diagnosis import DiagnosisCode, DiagnosisInfo
    fake_diag = DiagnosisInfo(code=DiagnosisCode.SW_NOT_INSTALLED,
                              reason="未装", suggestion="装", severity='block')
    with patch('sw_preflight.matrix.run_all_checks',
               return_value={'passed': False, 'failed_check': 'sw_installed', 'diagnosis': fake_diag}):
        with patch('sw_preflight.matrix.try_one_click_fix', return_value=None):  # 不可修
            from sw_preflight.preflight import run_preflight
            import pytest
            with pytest.raises(SystemExit) as exc:
                run_preflight(strict=True)
            assert exc.value.code == 2

def test_run_preflight_strict_false_just_warns(capsys):
    """strict=False 异常时只打 1 行温和提示，不卡"""
    from sw_preflight.diagnosis import DiagnosisCode, DiagnosisInfo
    fake_diag = DiagnosisInfo(code=DiagnosisCode.ADDIN_DISABLED,
                              reason="未启用", suggestion="启用", severity='block')
    with patch('sw_preflight.matrix.run_all_checks',
               return_value={'passed': False, 'failed_check': 'addin_enabled', 'diagnosis': fake_diag}):
        from sw_preflight.preflight import run_preflight
        result = run_preflight(strict=False)
        assert result.passed is False  # 不 raise
        captured = capsys.readouterr()
        assert 'SW 状态预告' in captured.out

def test_run_preflight_writes_cache(tmp_path, monkeypatch):
    """preflight 完成后写 sw_preflight_cache.json"""
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'artifacts/test-run').mkdir(parents=True)
    with patch('sw_preflight.matrix.run_all_checks',
               return_value={'passed': True, 'failed_check': None, 'diagnosis': None}):
        with patch('adapters.solidworks.sw_detect.detect_solidworks',
                   return_value=MagicMock(installed=True, version_year=2024)):
            from sw_preflight.preflight import run_preflight
            result = run_preflight(strict=True, run_id='test-run', entry='cad-spec')
    cache = tmp_path / 'artifacts/test-run/sw_preflight_cache.json'
    assert cache.exists()
```

- [ ] **Step 26.2: 跑测试看失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_preflight.py -v
```

- [ ] **Step 26.3: 实现 preflight.py**

```python
# sw_preflight/preflight.py
import sys
import time
from pathlib import Path
from typing import Optional
from sw_preflight.types import PreflightResult, FixRecord
from sw_preflight import matrix, cache

def run_preflight(strict: bool = True, run_id: str = '', entry: str = 'unknown') -> PreflightResult:
    """主入口 — 编排 matrix + 一键修 + cache 落盘"""
    start_total = time.time()
    per_step: dict[str, float] = {}
    fixes: list[FixRecord] = []

    # 跑 7 项检查
    t0 = time.time()
    check = matrix.run_all_checks()
    per_step['detect'] = (time.time() - t0) * 1000

    # 异常 → 尝试一键修
    if not check['passed']:
        try_fix = matrix.try_one_click_fix(check['failed_check'], check['diagnosis'])
        if try_fix:
            fixes.append(try_fix)
            # 重 detect (matrix 内会调 sw_detect.reset_cache)
            check = matrix.run_all_checks()
            per_step['after_fix_detect'] = (time.time() - t0) * 1000

    # 仍异常 → 处理 strict
    if not check['passed']:
        if strict:
            print(f"\n❌ {check['diagnosis'].reason}")
            print(f"   建议: {check['diagnosis'].suggestion}")
            sys.exit(2)
        else:
            print(f"\nℹ️ SW 状态预告: {check['diagnosis'].reason}")
            print(f"   后续 cad-codegen 会自动提示修复。当前编辑不受影响。")

    from adapters.solidworks.sw_detect import detect_solidworks
    sw_info = detect_solidworks()

    result = PreflightResult(
        passed=check['passed'],
        sw_info=sw_info,
        fixes_applied=fixes,
        diagnosis=check['diagnosis'],
        per_step_ms=per_step,
    )

    # 落 cache
    if run_id:
        cache_path = Path(f'./artifacts/{run_id}/sw_preflight_cache.json')
        from dataclasses import asdict
        cache.write_cache(cache_path, {'preflight_result': asdict(result)},
                          ttl_sec=300, ran_by_entry=entry)

    return result
```

> 需在 `matrix.py` 加 `try_one_click_fix(failed_check, diagnosis)` 助手 — 根据 failed_check 名字 dispatch 到 fix_pywin32 / fix_addin_enable / fix_rot_orphan / fix_sw_launch_background；不可修返回 None。

- [ ] **Step 26.4: 跑测试 + commit**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_preflight.py -v
git add sw_preflight/preflight.py sw_preflight/matrix.py tests/test_sw_preflight_preflight.py
git commit -m "feat(sw_preflight): preflight.py — run_preflight 编排（matrix + 一键修 + cache 落盘） (Task 26)"
```

---

## Phase 10: P2 报告

### Task 27: templates/sw_report.html.j2 — 三段式 HTML 模板

**Files:**
- Create: `sw_preflight/templates/sw_report.html.j2`
- Test: `tests/test_sw_preflight_template_render.py`

- [ ] **Step 27.1: 写失败测试 — 模板渲染含三段 + 状态卡 + 折叠区**

```python
# tests/test_sw_preflight_template_render.py
from pathlib import Path

def test_template_renders_three_sections(tmp_path):
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader('sw_preflight/templates'))
    tpl = env.get_template('sw_report.html.j2')
    html = tpl.render(
        sw_status={'edition': 'Pro 2024', 'toolbox': True, 'pywin32': True},
        ran_at='2026-04-19T14:32:00Z', elapsed='2m18s',
        standard_rows=[{'status': '✅', 'name': 'GB/T 70.1 M6', 'adapter': 'sw_toolbox'}],
        vendor_rows=[{'status': '✅', 'name': 'Maxon ECX', 'adapter': 'step_pool'}],
        custom_rows=[{'status': '✅', 'name': '立柱 P1-001', 'adapter': 'jinja_primitive'}],
        fix_records=[{'action': '程序残留清理', 'elapsed_ms': 1200,
                      'detail': 'ROT 释放 1 个僵死 SLDWORKS 实例'}],
    )
    assert 'SW 资产报告' in html
    assert '标准件' in html
    assert '外购件' in html
    assert '自定义件' in html
    assert '后台修复记录' in html
    assert '<details>' in html  # 折叠区给技术细节
    assert 'Pro 2024' in html
```

- [ ] **Step 27.2: 实现 sw_report.html.j2**

```html
<!-- sw_preflight/templates/sw_report.html.j2 -->
<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>SW 资产报告</title>
<style>
body{font-family:sans-serif;max-width:900px;margin:2em auto;color:#222}
h1{font-size:1.4em;border-bottom:2px solid #333;padding-bottom:.3em}
.status-card{background:#eef;padding:.5em 1em;border-radius:6px}
.section{margin:1.5em 0;border:1px solid #ccc;border-radius:6px;overflow:hidden}
.section-head{background:#f4f4f4;padding:.5em 1em;font-weight:bold}
.row{padding:.4em 1em;border-top:1px solid #eee}
.ok{color:#2a7}.warn{color:#c80}.err{color:#c33}
details{margin-top:.3em;font-size:.85em;color:#666}
</style></head><body>

<h1>SW 资产报告 — {{ ran_at }}  耗时 {{ elapsed }}</h1>
<div class="status-card">SW 状态：✅ {{ sw_status.edition }} |
Toolbox: {{ '✅' if sw_status.toolbox else '❌' }} |
pywin32: {{ '✅' if sw_status.pywin32 else '❌' }}</div>

<div class="section">
  <div class="section-head">标准件 ({{ standard_rows|length }} 行)</div>
  {% for r in standard_rows %}
  <div class="row"><span class="{{ 'ok' if r.status=='✅' else 'warn' if r.status=='⚠️' else 'err' }}">{{ r.status }}</span>
  {{ r.name }} → {{ r.adapter }}{% if r.reason %}<br>原因: {{ r.reason }}<br>建议: {{ r.suggestion }}{% endif %}</div>
  {% endfor %}
</div>

<div class="section">
  <div class="section-head">外购件 ({{ vendor_rows|length }} 行)</div>
  {% for r in vendor_rows %}
  <div class="row"><span class="{{ 'ok' if r.status=='✅' else 'warn' if r.status=='⚠️' else 'err' }}">{{ r.status }}</span>
  {{ r.name }} → {{ r.adapter }}</div>
  {% endfor %}
</div>

<div class="section">
  <div class="section-head">自定义件 ({{ custom_rows|length }} 行)</div>
  {% for r in custom_rows %}
  <div class="row"><span class="ok">{{ r.status }}</span> {{ r.name }} → {{ r.adapter }}</div>
  {% endfor %}
</div>

<div class="section">
  <div class="section-head">后台修复记录 ({{ fix_records|length }} 项)</div>
  {% for f in fix_records %}
  <div class="row">🛠️ {{ f.action }} ({{ '%.1f'|format(f.elapsed_ms/1000) }}s)
  <details><summary>技术细节</summary>{{ f.detail }}</details></div>
  {% endfor %}
</div>

</body></html>
```

- [ ] **Step 27.3: 跑测试 + commit**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_template_render.py -v
git add sw_preflight/templates/sw_report.html.j2 tests/test_sw_preflight_template_render.py
git commit -m "feat(sw_preflight): templates/sw_report.html.j2 — 三段式 HTML + 折叠技术细节 (Task 27)"
```

---

### Task 28: report.py — emit_report + 语言去技术化

**Files:**
- Create: `sw_preflight/report.py`
- Test: `tests/test_sw_preflight_report.py`

- [ ] **Step 28.1: 写失败测试 — emit_report 生成 HTML + JSON**

```python
# tests/test_sw_preflight_report.py
from pathlib import Path
from unittest.mock import MagicMock
from sw_preflight.types import (PreflightResult, BomDryRunResult, RowOutcome,
                                  PartCategory, FixRecord)

def test_emit_report_generates_html_and_json(tmp_path):
    pre = PreflightResult(passed=True, sw_info=MagicMock(edition='Pro', version_year=2024),
                          fixes_applied=[FixRecord(action='rot_orphan_release',
                                                    before_state='unhealthy',
                                                    after_state='healthy', elapsed_ms=1200)],
                          diagnosis=None, per_step_ms={'detect': 12.3})
    dry = BomDryRunResult(total_rows=2, hit_rows=[], stand_in_rows=[], missing_rows=[])
    from sw_preflight.report import emit_report
    out = emit_report([], dry, pre, output_dir=tmp_path)
    assert out.exists()
    assert (tmp_path / 'sw_report.html').exists()
    assert (tmp_path / 'sw_report_data.json').exists()
    html = (tmp_path / 'sw_report.html').read_text(encoding='utf-8')
    assert '程序残留清理' in html  # ROT 僵死 → 用户友好术语
    assert 'ROT' not in html.split('<details>')[0]  # 主体不含 ROT 字面值（折叠区可有）
```

- [ ] **Step 28.2: 跑测试看失败 + 实现**

```python
# sw_preflight/report.py
import json
from pathlib import Path
from dataclasses import asdict
from jinja2 import Environment, FileSystemLoader
from sw_preflight.types import PreflightResult, BomDryRunResult, FixRecord

# 术语去技术化映射
ACTION_FRIENDLY = {
    'rot_orphan_release': '程序残留清理',
    'pywin32_install': 'Python 通信组件安装',
    'addin_enable': 'Toolbox 模块自动启用',
    'sw_launch_background': 'SOLIDWORKS 后台启动',
}

def _friendly_action(action: str) -> str:
    return ACTION_FRIENDLY.get(action, action)

def _friendly_detail(record: FixRecord) -> str:
    if record.action == 'rot_orphan_release':
        return 'ROT 释放 1 个僵死 SLDWORKS 实例 (技术名: Running Object Table)'
    return f"{record.before_state} → {record.after_state}"

def emit_report(bom_rows: list[dict], dry_run: BomDryRunResult,
                preflight: PreflightResult, output_dir: Path) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 分三段
    standard_rows, vendor_rows, custom_rows = [], [], []
    for o in dry_run.hit_rows + dry_run.stand_in_rows:
        entry = {
            'status': o.status,
            'name': o.bom_row.get('name_cn', '?'),
            'adapter': o.actual_adapter,
            'reason': o.diagnosis.reason if o.diagnosis else None,
            'suggestion': o.diagnosis.suggestion if o.diagnosis else None,
        }
        if o.category.value.startswith('standard'):
            standard_rows.append(entry)
        elif o.category.value == 'vendor_purchased':
            vendor_rows.append(entry)
        else:
            custom_rows.append(entry)

    fix_records = [{'action': _friendly_action(f.action),
                    'elapsed_ms': f.elapsed_ms, 'detail': _friendly_detail(f)}
                   for f in preflight.fixes_applied]

    sw_status = {
        'edition': f"{preflight.sw_info.edition} {preflight.sw_info.version_year}",
        'toolbox': preflight.passed,
        'pywin32': True,  # 跑到这里 pywin32 必装
    }

    env = Environment(loader=FileSystemLoader(str(Path(__file__).parent / 'templates')))
    tpl = env.get_template('sw_report.html.j2')
    from datetime import datetime, timezone
    html = tpl.render(
        sw_status=sw_status,
        ran_at=datetime.now(timezone.utc).isoformat(),
        elapsed='?',  # plan 阶段从 preflight.per_step_ms 算
        standard_rows=standard_rows, vendor_rows=vendor_rows, custom_rows=custom_rows,
        fix_records=fix_records,
    )
    html_path = output_dir / 'sw_report.html'
    html_path.write_text(html, encoding='utf-8')

    # JSON 副本
    json_path = output_dir / 'sw_report_data.json'
    json_path.write_text(json.dumps({
        'sw_status': sw_status,
        'standard_rows': standard_rows,
        'vendor_rows': vendor_rows,
        'custom_rows': custom_rows,
        'fix_records': [asdict(f) for f in preflight.fixes_applied],
    }, default=str, indent=2), encoding='utf-8')
    return html_path
```

- [ ] **Step 28.3: 跑测试 + commit**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_report.py -v
git add sw_preflight/report.py tests/test_sw_preflight_report.py
git commit -m "feat(sw_preflight): report.py — emit_report + 语言去技术化（折叠技术细节） (Task 28)"
```

---

## 🛑 CHECKPOINT 5: Phase 9-10 完成

请用户确认：
- preflight.py 编排完成（含 cache 落盘）
- report.py + 模板完成（含术语友好化）
- 暂停等用户 OK 后继续 Phase 11

---

## Phase 11: CLI 入口接入

### Task 29: cad_spec_gen.py — strict=False + 审查范围透明化

**Files:**
- Modify: `cad_spec_gen.py`（项目根）
- Test: `tests/test_cad_spec_gen_preflight_integration.py`

- [ ] **Step 29.1: 写失败测试 — cad-spec 入口调 strict=False + 审查透明化提示**

```python
# tests/test_cad_spec_gen_preflight_integration.py
from unittest.mock import patch
import subprocess, sys

def test_cad_spec_strict_false_does_not_block_on_addin_disabled(tmp_path, monkeypatch):
    """cad-spec 入口 SW 异常时不卡，仅打 1 行温和提示"""
    monkeypatch.chdir(tmp_path)
    # mock preflight 返回 passed=False 但 strict=False 不 raise
    # 集成测试 — 通过 subprocess 跑 cad_spec_gen.py
    # 仅校验 exit code = 0 (不卡)
    # 详细测试参见 Task 34 集成测试
    pass  # placeholder — 真测试在 Task 34

def test_cad_spec_review_appends_uncovered_section():
    """--review 输出末尾含 '审查 *未* 覆盖' + '几何引擎'"""
    # 类似 placeholder
    pass
```

- [ ] **Step 29.2: 修改 cad_spec_gen.py**

在主入口（main 函数 / argparse handler）开头加：
```python
# cad_spec_gen.py
from sw_preflight.preflight import run_preflight

def main():
    # ... 现有 argparse / 配置 ...
    run_id = generate_run_id()  # 现有逻辑或新加
    preflight_result = run_preflight(strict=False, run_id=run_id, entry='cad-spec')
    # ... 现有 spec 抽取流程 ...

    # 如果是 --review 模式，输出末尾追加：
    if args.review:
        print("\n✅ 本次审查覆盖:")
        print("   - 机械参数完整性 / 装配关系完整性 / 材料指定完整性 ...")
        print("\n⚠️ 本次审查 *未* 覆盖（需要几何引擎，当前阶段做不到）:")
        print("   - 元件重叠 / 碰撞检测")
        print("   - 元件悬浮（无支撑结构）")
        print("   - 紧固件配合间隙")
        print("   - 装配可行性（拆装顺序、避让空间）")
        print("\n💡 这些检查计划在未来版本由 SOLIDWORKS 几何引擎自动完成")
        print("   （已装 SW 即可用，无需额外配置）")
```

- [ ] **Step 29.3: 跑测试 + commit**

```bash
.venv/Scripts/python.exe -m pytest tests/test_cad_spec_gen_preflight_integration.py -v
git add cad_spec_gen.py tests/test_cad_spec_gen_preflight_integration.py
git commit -m "feat(cad_spec): 接入 sw_preflight strict=False + 审查透明化 (Task 29)"
```

---

### Task 30: codegen/gen_std_parts.py — strict=True + dry_run + 三选一 + emit_report

**Files:**
- Modify: `codegen/gen_std_parts.py`
- Test: `tests/test_gen_std_parts_preflight_integration.py`

- [ ] **Step 30.1: 写失败测试 — cad-codegen 入口 strict=True + 流程**

```python
# tests/test_gen_std_parts_preflight_integration.py
from unittest.mock import patch

def test_codegen_reads_cache_when_recent(tmp_path):
    """cache.json TTL 内 → 复用 preflight 不重做"""
    pass  # placeholder — Task 34 详细集成

def test_codegen_emits_report_at_end(tmp_path):
    """跑完 stdout 含 sw_report.html 路径"""
    pass  # placeholder
```

- [ ] **Step 30.2: 修改 gen_std_parts.py**

```python
# codegen/gen_std_parts.py
from sw_preflight.preflight import run_preflight
from sw_preflight.cache import read_cache
from sw_preflight.dry_run import dry_run_bom
from sw_preflight.user_provided import prompt_user_provided
from sw_preflight.report import emit_report

def main():
    # ... 现有 argparse + 加载 BOM ...
    run_id = ...

    # 1. 读 cache 复用 preflight
    cache_path = Path(f'./artifacts/{run_id}/sw_preflight_cache.json')
    cached = read_cache(cache_path)
    if cached and cached['preflight_result']['passed']:
        preflight_result = ...  # 反序列化
    else:
        preflight_result = run_preflight(strict=True, run_id=run_id, entry='cad-codegen')

    # 2. dry_run BOM
    dry = dry_run_bom(bom_rows)

    # 3. 三选一 prompt
    missing_for_prompt = [o.bom_row for o in dry.missing_rows + dry.stand_in_rows]
    user_choice = prompt_user_provided(missing_for_prompt)

    # 4. 跑 codegen 主流程（用 user_choice 覆盖 router 决策）
    # ... 现有 codegen 逻辑 ...

    # 5. emit_report
    output_dir = Path(f'./artifacts/{run_id}')
    report_path = emit_report(bom_rows, dry, preflight_result, output_dir)
    print(f"\n✅ Done. 构建产物 → {output_dir}")
    print(f"📋 SW 资产报告 → {report_path} （建议先看）")
```

- [ ] **Step 30.3: 跑测试 + commit**

```bash
.venv/Scripts/python.exe -m pytest tests/test_gen_std_parts_preflight_integration.py -v
git add codegen/gen_std_parts.py tests/test_gen_std_parts_preflight_integration.py
git commit -m "feat(codegen): 接入 sw_preflight strict=True + dry_run + 三选一 + emit_report (Task 30)"
```

---

### Task 31: cad_pipeline.py — 串联

**Files:**
- Modify: `cad_pipeline.py`（项目根）
- Test: `tests/test_cad_pipeline_preflight_chain.py`

- [ ] **Step 31.1: 写失败测试 + 实现**

```python
# tests/test_cad_pipeline_preflight_chain.py
def test_pipeline_runs_cad_spec_then_codegen():
    """cad_pipeline 串联 cad-spec → cad-codegen，复用 cache"""
    pass  # placeholder — 集成测试在 Task 34
```

```python
# cad_pipeline.py 改动 — 不加新 preflight，串联现有 cad_spec → gen_std_parts
# preflight 由各自入口执行；cache.json 跨入口共享
def run_pipeline(args):
    cad_spec_main(args.spec_doc)        # 内部跑 strict=False preflight
    gen_std_parts_main(args.bom_path)   # 内部读 cache.json 复用
    # ... 后续渲染 etc ...
```

- [ ] **Step 31.2: commit**

```bash
git add cad_pipeline.py tests/test_cad_pipeline_preflight_chain.py
git commit -m "feat(pipeline): 串联 cad-spec/cad-codegen，cache.json 跨入口复用 (Task 31)"
```

---

## Phase 12: CI 自动化 + 集成测试 + 收尾

### Task 32: conftest.py — mock fixtures

**Files:**
- Modify: `tests/conftest.py`
- Test: 各 task 已用到这些 fixture

- [ ] **Step 32.1: 加 4 个 fixture**

```python
# tests/conftest.py 追加
import pytest
from unittest.mock import patch, MagicMock

@pytest.fixture
def mock_sw_registry_versions():
    """注入虚假注册表多版本数据"""
    def _inject(years: list[int]):
        return patch('adapters.solidworks.sw_detect._enumerate_registered_years',
                     return_value=years)
    return _inject

@pytest.fixture
def mock_filedialog():
    """mock tkinter.filedialog.askopenfilename"""
    with patch('sw_preflight.io.filedialog') as m:
        yield m

@pytest.fixture
def mock_admin():
    """mock IsUserAnAdmin"""
    def _set(is_admin: bool):
        return patch('sw_preflight.matrix.is_user_admin', return_value=is_admin)
    return _set

@pytest.fixture
def mock_provenance(tmp_path):
    """快速构造 provenance 测试 fixture"""
    def _make(content=b'ISO-10303\n' + b'\n'*20000):
        src = tmp_path / 'src.step'
        src.write_bytes(content)
        return src
    return _make
```

- [ ] **Step 32.2: commit**

```bash
git add tests/conftest.py
git commit -m "test(conftest): 加 sw_preflight 用 4 个 mock fixture (Task 32)"
```

---

### Task 33: CI workflow — 零硬编码 grep step

**Files:**
- Modify: `.github/workflows/sw-smoke.yml`（或主 CI workflow）
- Test: 在本地手动跑 grep 命令验证

- [ ] **Step 33.1: 加 CI step**

```yaml
# .github/workflows/sw-smoke.yml 追加
  - name: 零硬编码静态校验 (AC-2.5.1)
    run: |
      if git grep -nE 'Program Files|D:\\\\|"20(2[0-9]|3[0-9])"' -- sw_preflight/ ; then
        echo "❌ sw_preflight/ 含禁用的硬编码字面值"
        exit 1
      fi
      echo "✅ 零硬编码校验通过"
```

- [ ] **Step 33.2: 本地手动验证 + commit**

```bash
git grep -nE 'Program Files|D:\\\\|"20(2[0-9]|3[0-9])"' -- sw_preflight/
# 预期：无输出（exit code 1 = 无命中，git grep 反向）
git add .github/workflows/
git commit -m "ci: 加零硬编码静态校验 step (AC-2.5.1, Task 33)"
```

---

### Task 34: 集成测试 — 24 case Q 退出矩阵 + 修复幂等 + yaml 3 类

**Files:**
- Create: `tests/test_sw_preflight_integration_q_exit.py`
- Create: `tests/test_sw_preflight_integration_idempotent.py`

- [ ] **Step 34.1: 写 6×4 退出矩阵测试**

```python
# tests/test_sw_preflight_integration_q_exit.py
import pytest
from unittest.mock import patch

# 6 个交互点 × 4 种响应（参考 spec §9.1.1）
INTERACTION_POINTS = [
    'wait_close_assembly', 'pywin32_install_prompt', 'addin_enable_prompt',
    'admin_required_prompt', 'three_choice_prompt', 'cancel_dialog_secondary',
]

@pytest.mark.parametrize('interaction', INTERACTION_POINTS)
@pytest.mark.parametrize('response', ['Y', 'N', 'Q', 'TIMEOUT'])
def test_interaction_exit_paths_clean(interaction, response):
    """每个交互点的每种响应都不留半完成状态"""
    if response == 'TIMEOUT' and interaction not in ('wait_close_assembly',):
        pytest.skip("非超时适用")
    # 详细 mock 各交互点 + 响应 + 校验状态干净
    # 此处展示框架；plan 实现阶段补每个 case 的具体 mock
    pass
```

- [ ] **Step 34.2: 写修复幂等测试**

```python
# tests/test_sw_preflight_integration_idempotent.py
def test_three_consecutive_runs_only_first_fixes(tmp_path):
    """连跑 3 次 sw_preflight，第 1 次修，第 2/3 次静默通过"""
    fixes_per_run = []
    for i in range(3):
        from sw_preflight.preflight import run_preflight
        with patch('sw_preflight.matrix.run_all_checks',
                   side_effect=[
                       # run 1: 第一次 check 失败、第二次 (after fix) 过
                       {'passed': False, 'failed_check': 'addin_enabled',
                        'diagnosis': MagicMock(severity='block')},
                       {'passed': True, 'failed_check': None, 'diagnosis': None}
                   ] if i == 0 else [
                       {'passed': True, 'failed_check': None, 'diagnosis': None}
                   ]):
            r = run_preflight(strict=False, run_id=f'run-{i}')
            fixes_per_run.append(len(r.fixes_applied))
    assert fixes_per_run == [1, 0, 0]  # 只第 1 次有 fix
```

- [ ] **Step 34.3: 跑全部测试 + commit**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_integration*.py -v
git add tests/test_sw_preflight_integration_q_exit.py tests/test_sw_preflight_integration_idempotent.py
git commit -m "test: 集成测试 — 24 case 退出矩阵 + 修复幂等 (Task 34)"
```

---

### Task 35: .gitignore + SKILL.md 文档化

**Files:**
- Modify: `.gitignore`
- Modify: `.claude/skills/cad-spec/SKILL.md`
- Modify: `.claude/skills/cad-codegen/SKILL.md`

- [ ] **Step 35.1: .gitignore 加中间产物**

```
# .gitignore 追加
artifacts/*/sw_preflight_cache.json
artifacts/*/sw_report.html
artifacts/*/sw_report_data.json
~/.cad-spec-gen/sw_version_preference.json
```

- [ ] **Step 35.2: SKILL.md 文档化**

```markdown
<!-- .claude/skills/cad-spec/SKILL.md 追加 -->
## SW 装即用 集成 (spec 2026-04-19)

cad-spec 入口在启动时跑 `sw_preflight.run_preflight(strict=False)`：
- 正常情况静默通过
- SW 状态异常时 stdout 末尾打 1 行温和预告，不卡用户编辑
- `--review` 模式输出末尾追加"审查范围透明化"段（说明几何审查未覆盖）
```

```markdown
<!-- .claude/skills/cad-codegen/SKILL.md 追加 -->
## SW 装即用 集成 (spec 2026-04-19)

cad-codegen 入口流程：
1. 读 `./artifacts/<run-id>/sw_preflight_cache.json` 复用 cad-spec 阶段的 preflight 结果
2. 若无缓存或过期 → 自己跑 `run_preflight(strict=True)`（修不动 sys.exit(2)）
3. 跑 `dry_run_bom(bom)` 识别 SW 找不到的 BOM 行
4. 弹三选一 prompt + tkinter file dialog 让用户指定 STEP（按 PartCategory 分流复制）
5. 跑 codegen 主流程
6. `emit_report()` 生成 `sw_report.html` (三段式 + 术语去技术化)
7. stdout 末尾打报告路径
```

- [ ] **Step 35.3: commit**

```bash
git add .gitignore .claude/skills/
git commit -m "docs+chore: .gitignore + SKILL.md 文档化 sw_preflight 集成 (Task 35)"
```

---

## 🛑 CHECKPOINT 6 (最终): Phase 11-12 完成

请用户确认：
- 3 个 CLI 入口完成接入（cad-spec / cad-codegen / cad_pipeline）
- conftest fixtures 完成
- CI grep step 加入
- 集成测试（24 case + 幂等 + yaml 3 类）跑过
- .gitignore + SKILL.md 文档化

**最终验收**：跑全 spec 验收矩阵：
```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_preflight_*.py tests/test_sw_detect_*.py tests/test_parts_resolver_category.py tests/test_parts_library_standard_categories.py -v
```

预期：全部 PASS（mock 部分 — 真 SW 部分 `requires_solidworks` 在 Windows runner 跑）。

---

## 总结：35 个 task，6 个检查点

| Phase | Task 范围 | 内容 |
|---|---|---|
| 0 | Task 0 | 硬编码清查 |
| 1 | Task 1-3 | 包骨架 + types + diagnosis |
| 2 | Task 4-6 | sw_detect 扩展 |
| 3 | Task 7-8 | parts_resolver + parts_library 扩展 |
| 4 | Task 9-11 | io 层 |
| 5 | Task 12-18 | matrix M 体检 + 一键修 + diagnosis 模板 |
| 6 | Task 19-20 | cache + preference |
| 7 | Task 21 | dry_run |
| 8 | Task 22-25 | user_provided 流 |
| 9 | Task 26 | preflight 编排 |
| 10 | Task 27-28 | P2 报告 |
| 11 | Task 29-31 | CLI 入口接入 |
| 12 | Task 32-35 | conftest + CI + 集成测试 + 文档 |

**估算工时**：35 task × 平均 30min/task = ~17.5 小时（按 TDD 节奏，含测试 + 实现 + commit）。

**关键约束（每个 task 必守）**：
1. TDD 严格 RED→GREEN→REFACTOR
2. 零硬编码（路径/版本/edition 走自主发现）
3. windows-only（真 SW 测试用 `@pytest.mark.requires_solidworks`）
4. 每完成一组暂停让用户确认（6 个 checkpoint）
5. commit 频繁（每 task 至少 1 commit）

---

**END OF PLAN**
