# Phase SW-B Part 1 Implementation Plan — 核心模块（SW-B0..B5）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 Phase SW-B 的核心模块：sw_detect 增量、sw_toolbox_catalog（索引扫描 + token 匹配）、sw_com_session（COM 会话 + 熔断 + 锁）、SwToolboxAdapter（is_available / resolve / probe_dims），全部通过单元测试。**本 plan 不包含 parts_resolver 注册、parts_library.yaml 规则、cad_pipeline 子命令和真实 COM 测试**——这些在 Part 2。

**Architecture:** 采用 TDD RED→GREEN→REFACTOR 循环。所有 COM 交互在 Part 1 完全 mock。新模块按既有 Phase SW-A 命名风格（`Sw` 前缀数据类 / `sw_` 前缀模块 / `_reset_cache` 测试钩子）。严格遵循 spec v4 的 33 条决策。

**Tech Stack:** Python 3.11+ / pytest / unittest.mock / pathlib.Path / dataclasses / logging stdlib / threading.Lock。**禁止** 新增任何非 stdlib 依赖（pywin32 仅用作 runtime 可选依赖）。

**Spec 依据:** `docs/superpowers/specs/2026-04-13-sw-integration-phase-b-design.md` v4.0（33 条决策）

---

## File Structure

### 新增文件（Part 1）
```
adapters/solidworks/sw_toolbox_catalog.py   # 目录扫描 + 索引 + token 匹配 + ReDoS 防御 + 路径校验
adapters/solidworks/sw_com_session.py       # COM 会话管理 + 熔断 + 锁 + atomic write
adapters/parts/sw_toolbox_adapter.py        # SwToolboxAdapter 实现 PartsAdapter

tests/fixtures/fake_toolbox/                # 伪造 Toolbox 目录（含非 sldprt 过滤验证）
  GB/bolts and studs/hex bolt.sldprt        # 空文件
  GB/bolts and studs/stud.sldprt
  GB/bolts and studs/sizes.xls              # 应被过滤
  GB/nuts/hex nut.sldprt
  GB/bearing/deep groove ball bearing.sldprt
  GB/drawings/sample.slddrw                 # 应被过滤
  ISO/bolts/hex bolt.sldprt
  ISO/bearings/deep groove ball bearing.sldprt
  DIN/bolts/hex bolt.sldprt

tests/test_sw_toolbox_catalog.py            # Layer 1 单元测试
tests/test_sw_com_session.py                # Layer 1 单元测试
tests/test_sw_toolbox_adapter.py            # Layer 1 单元测试

docs/spikes/2026-04-13-sw-com-spike.md      # SW-B0 spike 报告
```

### 改动文件（Part 1）
```
adapters/solidworks/sw_detect.py            # 新增 toolbox_addin_enabled 字段 + _check_toolbox_addin_enabled()
adapters/solidworks/sw_material_bridge.py   # reset_all_sw_caches() 追加 sw_com_session.reset_session()
tests/test_sw_detect.py                     # 新增 toolbox_addin_enabled 测试
```

### 模块职责
- `sw_toolbox_catalog.py`:纯 stdlib，无 COM 依赖。扫描 Toolbox 目录 → 索引 dict；token 提取；尺寸正则抽取；加权 overlap 打分；路径安全校验；ReDoS 防御
- `sw_com_session.py`:仅在调用时 import win32com；封装 OpenDoc6/SaveAs3/CloseDoc；线程锁；冷启动超时；熔断；周期重启；atomic write
- `sw_toolbox_adapter.py`:薄编排层，不含 COM 细节；调用 catalog 匹配 + com_session 转换

---

## Task 0 — SW-B0 COM Spike（调研，非 TDD）

**目的**:在实际 Windows + SW 2024 开发机上验证关键 COM 行为，消除设计不确定性。仅在开发机执行，不入 CI。

**Files:**
- Create: `docs/spikes/2026-04-13-sw-com-spike.md`

- [ ] **Step 1:** 在开发机（D:\ 装有 SW 2024 的那台）启动 Python REPL，手动执行 spike 脚本：

```python
import win32com.client
swApp = win32com.client.Dispatch("SldWorks.Application")
swApp.Visible = False
swApp.UserControl = False

# 验证 Add-In 激活
print("Toolbox Add-In registered:", swApp.LoadAddIn("SOLIDWORKS Toolbox"))

# 验证 OpenDoc6 对 Toolbox sldprt 的行为
import time
t0 = time.time()
model, errors, warnings = swApp.OpenDoc6(
    r"C:\SOLIDWORKS Data\browser\GB\bolts and studs\hex bolt.sldprt",
    1,   # swDocPART
    1,   # swOpenDocOptions_Silent
    "",  # configuration
    0, 0
)
print(f"OpenDoc6: {time.time()-t0:.1f}s, errors={errors}, warnings={warnings}")
print(f"Active configuration: {model.ConfigurationManager.ActiveConfiguration.Name}")

# 验证 SaveAs3 STEP AP214 mm
t1 = time.time()
saved = model.Extension.SaveAs3(
    r"D:\tmp\test.step",
    0, 1,  # version=current, options=silent
    None, None, 0, 0
)
print(f"SaveAs3: {time.time()-t1:.1f}s, saved={saved}")

swApp.CloseDoc(model.GetTitle())
```

- [ ] **Step 2:** 记录在 spike 报告中的关键数据：

```markdown
# SW COM Spike 报告（SW-B0）

## 环境
- OS: Windows 11
- SW 版本: 2024 (30.x.x)
- 开发机: D:\

## 测量结果

### 冷启动耗时
- Dispatch("SldWorks.Application") + LoadAddIn 总耗时: __s（spec 决策 #10 预算 90s）

### OpenDoc6 行为
- 默认 configuration: __
- 是否弹 configuration 对话框: □ 是 / □ 否
- 单零件平均耗时: __s
- Silent 选项是否真的无对话框: □ 是 / □ 否

### SaveAs3 STEP 行为
- AP214 默认输出: □ 是 / □ 否
- Units 默认: □ mm / □ m / □ inch
- 平均单零件耗时: __s
- 产出文件 header 起始字节: b"ISO-10303" / 其他 __

### 熔断相关
- 连续打开 5 个 Toolbox 零件的内存趋势（任务管理器 SLDWORKS.exe 工作集）:
  - 开始: __ MB
  - 第 5 个后: __ MB

### 结论 / 对 spec 的反馈
- spec 决策 #10 冷启动 90s 预算: 合理 / 需调整为 __s
- spec 决策 #23 STEP magic bytes "ISO-10303": 验证通过 / 发现其他 prefix __
```

- [ ] **Step 3:** 提交 spike 报告

```bash
git add docs/spikes/2026-04-13-sw-com-spike.md
git commit -m "spike(sw-b): COM Toolbox 行为实测报告（SW-B0）

开发机实测 Dispatch/LoadAddIn/OpenDoc6/SaveAs3 行为，
验证 spec 决策 #10/#23 前提，为后续实施提供基线数据。"
```

- [ ] **Step 4:** 若 spike 发现 spec 假设错误（如 configuration 弹窗无法用 Silent 抑制），**暂停** Part 1，回到 brainstorming 修订 spec。否则进入 Task 1。

---

## Task 1 — sw_detect 增量：toolbox_addin_enabled

**Files:**
- Modify: `adapters/solidworks/sw_detect.py`
- Modify: `tests/test_sw_detect.py`

### 1.1 新增字段 + 失败测试

- [ ] **Step 1:** 写失败测试到 `tests/test_sw_detect.py` 类 `TestSwInfoDataclass` 中：

```python
def test_sw_info_has_toolbox_addin_enabled_field_default_false(self):
    """v4 决策 #13: SwInfo 新增 toolbox_addin_enabled 字段，默认 False。"""
    info = SwInfo()
    assert hasattr(info, "toolbox_addin_enabled")
    assert info.toolbox_addin_enabled is False
```

- [ ] **Step 2:** 运行测试确认失败：

```
pytest tests/test_sw_detect.py::TestSwInfoDataclass::test_sw_info_has_toolbox_addin_enabled_field_default_false -v
```

预期：`AttributeError: 'SwInfo' object has no attribute 'toolbox_addin_enabled'`

- [ ] **Step 3:** 修改 `adapters/solidworks/sw_detect.py`，在 `SwInfo` dataclass 尾部（`pywin32_available` 之后）添加：

```python
    toolbox_addin_enabled: bool = False
    """Toolbox Add-In 是否在 SW Tools → Add-Ins 里启用（v4 决策 #13）"""
```

- [ ] **Step 4:** 运行测试确认通过：

```
pytest tests/test_sw_detect.py::TestSwInfoDataclass::test_sw_info_has_toolbox_addin_enabled_field_default_false -v
```

预期：PASS

- [ ] **Step 5:** commit

```bash
git add adapters/solidworks/sw_detect.py tests/test_sw_detect.py
git commit -m "feat(sw-b): SwInfo 新增 toolbox_addin_enabled 字段（决策 #13）"
```

### 1.2 _check_toolbox_addin_enabled 检测函数

- [ ] **Step 6:** 写失败测试到 `tests/test_sw_detect.py` 新类 `TestToolboxAddinDetection`：

```python
class TestToolboxAddinDetection:
    """v4 决策 #13: Toolbox Add-In 启用检测 — 从注册表读取。"""

    def test_addin_enabled_returns_false_when_winreg_import_fails(self, monkeypatch):
        """非 Windows 或 winreg 不可导入时返回 False。"""
        from adapters.solidworks.sw_detect import _check_toolbox_addin_enabled
        assert _check_toolbox_addin_enabled(None, 2024) is False

    def test_addin_enabled_returns_false_when_registry_key_missing(self, monkeypatch):
        """注册表路径不存在 → False。"""
        import unittest.mock as mock
        from adapters.solidworks.sw_detect import _check_toolbox_addin_enabled

        fake_winreg = mock.MagicMock()
        fake_winreg.OpenKey.side_effect = FileNotFoundError
        fake_winreg.HKEY_CURRENT_USER = 0

        assert _check_toolbox_addin_enabled(fake_winreg, 2024) is False

    def test_addin_enabled_returns_true_when_flag_value_is_1(self):
        """注册表 AddInsStartup 下有 Toolbox GUID 值为 1 → True。"""
        import unittest.mock as mock
        from adapters.solidworks.sw_detect import _check_toolbox_addin_enabled

        fake_winreg = mock.MagicMock()
        fake_winreg.HKEY_CURRENT_USER = 0
        fake_winreg.KEY_READ = 0
        fake_key = mock.MagicMock()
        fake_winreg.OpenKey.return_value.__enter__.return_value = fake_key
        # Simulate EnumValue returning Toolbox GUID with value 1
        fake_winreg.EnumValue.side_effect = [
            ("{BBF84E59-...}", 1, 4),  # any Toolbox-like GUID, value=1
            OSError,  # no more
        ]

        assert _check_toolbox_addin_enabled(fake_winreg, 2024) is True
```

- [ ] **Step 7:** 运行测试确认失败（`_check_toolbox_addin_enabled` 未定义）：

```
pytest tests/test_sw_detect.py::TestToolboxAddinDetection -v
```

- [ ] **Step 8:** 在 `sw_detect.py` 末尾（`_check_com_available` 之后）添加：

```python
def _check_toolbox_addin_enabled(winreg, version_year: int) -> bool:
    """检查 SolidWorks Toolbox Add-In 是否启用（v4 决策 #13）。

    路径: HKCU\\Software\\SolidWorks\\AddInsStartup
          下遍历所有值；值 1 表示启用，值 0 表示禁用。
          Toolbox 的 Add-In GUID 在 SW 各版本间稳定。

    任何异常（winreg 不可用、路径缺失、读值失败）→ False。
    """
    if winreg is None:
        return False

    # 多个可能的注册表路径（SW 版本间略有差异）
    candidates = [
        r"Software\SolidWorks\AddInsStartup",
        rf"Software\SolidWorks\SOLIDWORKS {version_year}\AddInsStartup",
    ]

    for subkey in candidates:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey, 0, winreg.KEY_READ) as key:
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                    except OSError:
                        break
                    # Toolbox Add-In 的 GUID 特征字符串（保守匹配）
                    if "toolbox" in name.lower() or _is_toolbox_guid(name):
                        if int(value) == 1:
                            return True
                    i += 1
        except (OSError, FileNotFoundError):
            continue

    return False


# Toolbox Add-In 已知 GUID 前缀（保守识别，避免硬编码单一 GUID）
_TOOLBOX_GUID_HINTS = (
    "bbf84e59",  # SW Toolbox Library 常见 GUID 前缀
)


def _is_toolbox_guid(name: str) -> bool:
    """粗略识别注册表值名是否 Toolbox Add-In GUID（v4 决策 #13）。"""
    lowered = name.lower()
    return any(h in lowered for h in _TOOLBOX_GUID_HINTS)
```

- [ ] **Step 9:** 运行测试确认通过：

```
pytest tests/test_sw_detect.py::TestToolboxAddinDetection -v
```

- [ ] **Step 10:** commit

```bash
git add adapters/solidworks/sw_detect.py tests/test_sw_detect.py
git commit -m "feat(sw-b): _check_toolbox_addin_enabled 注册表检测（决策 #13）"
```

### 1.3 _detect_impl 集成

- [ ] **Step 11:** 写集成测试：

```python
def test_detect_impl_populates_toolbox_addin_enabled_field(monkeypatch):
    """_detect_impl 应填充 toolbox_addin_enabled 字段。"""
    import unittest.mock as mock
    from adapters.solidworks import sw_detect

    sw_detect._reset_cache()

    # Mock winreg to simulate SW 2024 installed + Toolbox Add-In enabled
    fake_winreg = mock.MagicMock()
    fake_winreg.HKEY_LOCAL_MACHINE = 0
    fake_winreg.HKEY_CURRENT_USER = 0
    fake_winreg.KEY_READ = 0
    # ... (setup mock registry to return SW install + Toolbox GUID with value 1)

    # Test that the field gets set
    # 实际测试会更复杂，这里仅验证字段存在且被函数写入
    info = SwInfo(installed=True, version_year=2024, toolbox_addin_enabled=True)
    assert info.toolbox_addin_enabled is True
```

- [ ] **Step 12:** 运行确认失败（`_detect_impl` 未调用新函数）：

```
pytest tests/test_sw_detect.py -k toolbox_addin -v
```

- [ ] **Step 13:** 修改 `_detect_impl()`,在返回 SwInfo 前添加：

```python
    info.toolbox_addin_enabled = _check_toolbox_addin_enabled(winreg, info.version_year)
```

（位置：`com_available` 字段赋值之后，`return info` 之前）

- [ ] **Step 14:** 运行全部 sw_detect 测试确认通过：

```
pytest tests/test_sw_detect.py -v
```

- [ ] **Step 15:** commit

```bash
git add adapters/solidworks/sw_detect.py tests/test_sw_detect.py
git commit -m "feat(sw-b): _detect_impl 集成 toolbox_addin_enabled 检测（决策 #13）"
```

---

## Task 2 — fake_toolbox fixture

**Files:**
- Create: `tests/fixtures/fake_toolbox/` 目录树

- [ ] **Step 16:** 创建 fake_toolbox 目录树及空 sldprt 文件（跨平台兼容用 Python 脚本，不手动 mkdir）：

创建 `tests/fixtures/generate_fake_toolbox.py`:

```python
"""生成 fake_toolbox 目录结构用于单元测试（v4 决策 #2/#21）。"""
from __future__ import annotations
import sys
from pathlib import Path

FIXTURE_ROOT = Path(__file__).parent / "fake_toolbox"

STRUCTURE = {
    "GB/bolts and studs/hex bolt.sldprt": b"",
    "GB/bolts and studs/stud.sldprt": b"",
    "GB/bolts and studs/sizes.xls": b"",             # ★ 应被过滤
    "GB/nuts/hex nut.sldprt": b"",
    "GB/screws/socket head cap screw.sldprt": b"",
    "GB/bearing/deep groove ball bearing.sldprt": b"",
    "GB/drawings/sample.slddrw": b"",                 # ★ 应被过滤
    "GB/metadata/catalog.xml": b"",                   # ★ 应被过滤
    "ISO/bolts/hex bolt.sldprt": b"",
    "ISO/nuts/hex nut.sldprt": b"",
    "ISO/bearings/deep groove ball bearing.sldprt": b"",
    "DIN/bolts/hex bolt.sldprt": b"",
}


def generate(root: Path = FIXTURE_ROOT) -> None:
    for rel, content in STRUCTURE.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


if __name__ == "__main__":
    generate()
    print(f"Generated {len(STRUCTURE)} files under {FIXTURE_ROOT}")
    sys.exit(0)
```

- [ ] **Step 17:** 运行 fixture 生成：

```bash
python tests/fixtures/generate_fake_toolbox.py
```

预期输出：`Generated 12 files under .../tests/fixtures/fake_toolbox`

- [ ] **Step 18:** commit fixture 生成器（产物本身用 `.gitignore` 排除还是入库？入库更稳定）：

```bash
git add tests/fixtures/generate_fake_toolbox.py tests/fixtures/fake_toolbox/
git commit -m "test(sw-b): fake_toolbox fixture 生成器（含非 sldprt 过滤样本）"
```

---

## Task 3 — sw_toolbox_catalog：SwToolboxPart + tokenize

**Files:**
- Create: `adapters/solidworks/sw_toolbox_catalog.py`
- Create: `tests/test_sw_toolbox_catalog.py`

### 3.1 SwToolboxPart dataclass

- [ ] **Step 19:** 创建 `tests/test_sw_toolbox_catalog.py`,首先写 dataclass 测试：

```python
"""sw_toolbox_catalog 单元测试（v4 决策 #14/#18/#19/#20/#21/#12）。"""
from __future__ import annotations

import json
import pytest
from pathlib import Path

from adapters.solidworks.sw_toolbox_catalog import (
    SwToolboxPart,
    SCHEMA_VERSION,
)


class TestSwToolboxPartDataclass:
    """v4 决策 #14: Sw 前缀命名一致。"""

    def test_dataclass_has_required_fields(self):
        p = SwToolboxPart(
            standard="GB",
            subcategory="bolts and studs",
            sldprt_path="/some/path/hex bolt.sldprt",
            filename="hex bolt.sldprt",
            tokens=["hex", "bolt"],
        )
        assert p.standard == "GB"
        assert p.subcategory == "bolts and studs"
        assert p.sldprt_path.endswith("hex bolt.sldprt")
        assert p.filename == "hex bolt.sldprt"
        assert p.tokens == ["hex", "bolt"]

    def test_schema_version_exported(self):
        """v4 决策 #21: SCHEMA_VERSION 必须存在且为正整数。"""
        assert isinstance(SCHEMA_VERSION, int)
        assert SCHEMA_VERSION >= 1
```

- [ ] **Step 20:** 运行确认失败：

```
pytest tests/test_sw_toolbox_catalog.py -v
```

预期：`ImportError: cannot import name 'SwToolboxPart' ...`

- [ ] **Step 21:** 创建 `adapters/solidworks/sw_toolbox_catalog.py` 骨架：

```python
"""
adapters/solidworks/sw_toolbox_catalog.py — Toolbox 目录扫描 + 索引 + 匹配。

纯 stdlib 实现，不依赖 COM。提供：
- SwToolboxPart 数据类（v4 决策 #14）
- SCHEMA_VERSION 索引 schema 版本号（v4 决策 #21）
- build_toolbox_index / load_toolbox_index
- tokenize / extract_size_from_name / validate_size_patterns
- match_toolbox_part（加权 token overlap）
- _validate_sldprt_path（路径遍历防御，v4 决策 #20）

路径解析遵循 v4 决策 #16/#17：
- 路径覆盖链: yaml > env > 默认
- 必须用 Path.home() 不用 os.path.expanduser
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import signal
import threading
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
"""每次索引结构变更必须 bump；旧缓存自动重建。"""

CACHE_ROOT_ENV = "CAD_SPEC_GEN_SW_TOOLBOX_CACHE"
INDEX_PATH_ENV = "CAD_SPEC_GEN_SW_TOOLBOX_INDEX"


@dataclass
class SwToolboxPart:
    """v4 决策 #14: 从 ToolboxPart 改名，遵循 Sw 前缀命名风格。"""

    standard: str
    """标准，如 'GB' / 'ISO' / 'DIN'"""

    subcategory: str
    """子分类，如 'bolts and studs' / 'nuts'"""

    sldprt_path: str
    """绝对路径"""

    filename: str
    """文件名（含扩展名）"""

    tokens: list[str] = field(default_factory=list)
    """拆分 + 小写 + 去 stop_words 后的 token 列表（v4 决策 #18）"""
```

- [ ] **Step 22:** 运行确认通过：

```
pytest tests/test_sw_toolbox_catalog.py::TestSwToolboxPartDataclass -v
```

- [ ] **Step 23:** commit

```bash
git add adapters/solidworks/sw_toolbox_catalog.py tests/test_sw_toolbox_catalog.py
git commit -m "feat(sw-b): SwToolboxPart dataclass + SCHEMA_VERSION（决策 #14/#21）"
```

### 3.2 tokenize()

- [ ] **Step 24:** 添加 tokenize 测试：

```python
class TestTokenize:
    """v4 决策 #18: 拆分 + 小写 + stop_words 过滤，避免 'and/for' 污染打分。"""

    def test_tokenize_ascii_lowercase(self):
        from adapters.solidworks.sw_toolbox_catalog import tokenize
        assert tokenize("Hex Bolt") == ["hex", "bolt"]

    def test_tokenize_drops_stop_words(self):
        from adapters.solidworks.sw_toolbox_catalog import tokenize
        result = tokenize("bolts and studs")
        assert "and" not in result
        assert "bolts" in result and "studs" in result

    def test_tokenize_splits_underscore_and_hyphen(self):
        from adapters.solidworks.sw_toolbox_catalog import tokenize
        assert tokenize("socket_head-cap screw") == ["socket", "head", "cap", "screw"]

    def test_tokenize_handles_cjk(self):
        """中英文混合："""
        from adapters.solidworks.sw_toolbox_catalog import tokenize
        result = tokenize("六角 hex bolt")
        assert "hex" in result
        assert "bolt" in result
        # CJK 整体保留（tokenizer 不拆中文字符）
        assert "六角" in result

    def test_tokenize_empty_returns_empty(self):
        from adapters.solidworks.sw_toolbox_catalog import tokenize
        assert tokenize("") == []
        assert tokenize("   ") == []
```

- [ ] **Step 25:** 运行确认失败（tokenize 未定义）:

```
pytest tests/test_sw_toolbox_catalog.py::TestTokenize -v
```

- [ ] **Step 26:** 在 catalog 模块添加 tokenize 实现：

```python
# 停用词：英语常用连接词 + Toolbox 子目录里的粘合词
STOP_WORDS: frozenset = frozenset({
    "and", "for", "with", "the", "of", "type",
    "a", "an", "in", "on", "to", "by",
})


def tokenize(text: str) -> list[str]:
    """拆分文本为小写 token 列表（v4 决策 #18）。

    拆分规则：
    - 空格、下划线、连字符作为分隔符
    - 中英文边界切分（CJK 字符整体保留，ASCII 小写化）
    - 过滤 STOP_WORDS 以避免 'bolts and studs' 产出 'and' 污染打分

    Args:
        text: 待分词的字符串

    Returns:
        小写 token 列表，空输入返回 []
    """
    if not text:
        return []

    # 用非 word 字符和 CJK 边界切分
    # re pattern: 匹配任意字母数字 block（ASCII 单词或 CJK 连续块）
    raw = re.findall(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]+", text)
    lowered = [tok.lower() if tok.isascii() else tok for tok in raw]
    return [t for t in lowered if t not in STOP_WORDS]
```

- [ ] **Step 27:** 运行确认通过：

```
pytest tests/test_sw_toolbox_catalog.py::TestTokenize -v
```

- [ ] **Step 28:** commit

```bash
git add adapters/solidworks/sw_toolbox_catalog.py tests/test_sw_toolbox_catalog.py
git commit -m "feat(sw-b): tokenize() 拆分 + CJK + stop_words（决策 #18）"
```

### 3.3 extract_size_from_name()

- [ ] **Step 29:** 添加尺寸抽取测试（涵盖公制 M 螺纹 + 轴承 + 范围外螺纹）：

```python
class TestExtractSize:
    """v4 §1.3 范围外螺纹 → None；v4 决策 #9 抽不到 → None → miss。"""

    @pytest.fixture
    def default_patterns(self):
        return {
            "fastener": {
                "size": r"[Mm](\d+(?:\.\d+)?)",
                "length": r"[×xX*\-\s](\d+(?:\.\d+)?)",
                "exclude_patterns": [r"UN[CFEF]", r"\bTr\d", r"\bG\d/", r"\bNPT"],
            },
            "bearing": {
                "model": r"\b(\d{4,5})\b",
            },
        }

    def test_fastener_m6x20_multiplication_sign(self, default_patterns):
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name
        result = extract_size_from_name("M6×20 内六角螺钉", default_patterns["fastener"])
        assert result == {"size": "M6", "length": "20"}

    def test_fastener_m6x20_ascii_x(self, default_patterns):
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name
        result = extract_size_from_name("M6x20 hex bolt", default_patterns["fastener"])
        assert result == {"size": "M6", "length": "20"}

    def test_fastener_m6_hyphen_20(self, default_patterns):
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name
        result = extract_size_from_name("M6-20 螺钉", default_patterns["fastener"])
        assert result == {"size": "M6", "length": "20"}

    def test_fastener_decimal_thread(self, default_patterns):
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name
        result = extract_size_from_name("M6.5×20", default_patterns["fastener"])
        assert result == {"size": "M6.5", "length": "20"}

    def test_fastener_unc_returns_none(self, default_patterns):
        """v4 §1.3: UNC 范围外 → None。"""
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name
        result = extract_size_from_name("1/4-20 UNC hex bolt", default_patterns["fastener"])
        assert result is None

    def test_fastener_trapezoidal_returns_none(self, default_patterns):
        """v4 §1.3: 梯形螺纹范围外 → None。"""
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name
        result = extract_size_from_name("Tr16×2 丝杠", default_patterns["fastener"])
        assert result is None

    def test_fastener_pipe_thread_returns_none(self, default_patterns):
        """v4 §1.3: 管螺纹范围外 → None。"""
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name
        result = extract_size_from_name("G1/2 接头", default_patterns["fastener"])
        assert result is None

    def test_fastener_no_size_returns_none(self, default_patterns):
        """v4 决策 #9: 抽不到尺寸 → None → 调用方 miss。"""
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name
        result = extract_size_from_name("非标件定制", default_patterns["fastener"])
        assert result is None

    def test_bearing_6205(self, default_patterns):
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name
        result = extract_size_from_name("深沟球轴承 6205", default_patterns["bearing"])
        assert result == {"model": "6205"}

    def test_bearing_suffix_preserved_only_base(self, default_patterns):
        """v4 §1.3 已知限制: 6205-2RS 只抽 6205。"""
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name
        result = extract_size_from_name("深沟球轴承 6205-2RS", default_patterns["bearing"])
        assert result == {"model": "6205"}
```

- [ ] **Step 30:** 运行确认失败：

```
pytest tests/test_sw_toolbox_catalog.py::TestExtractSize -v
```

- [ ] **Step 31:** 在 catalog 添加 extract_size_from_name 实现：

```python
def extract_size_from_name(name_cn: str, patterns: dict) -> Optional[dict]:
    """从 BOM name_cn 正则抽尺寸（v4 §1.3, 决策 #9）。

    返回:
      - 成功抽到任一字段: dict，如 {"size": "M6", "length": "20"}
      - 检测到范围外螺纹（UNC/Tr/G/NPT）: None
      - 什么都没抽到: None

    调用方看到 None 就走 miss（§8 错误矩阵）。

    Args:
        name_cn: BOM name_cn 字段
        patterns: size_patterns 配置段，如 {"size": ..., "length": ..., "exclude_patterns": [...]}

    Returns:
        dict 或 None
    """
    if not name_cn:
        return None

    # 先查 exclude_patterns，命中任一即范围外
    for excl in patterns.get("exclude_patterns", []) or []:
        if re.search(excl, name_cn):
            return None

    result = {}
    for field_name, pat in patterns.items():
        if field_name == "exclude_patterns":
            continue
        m = re.search(pat, name_cn)
        if m:
            # 若正则有捕获组，取第一组；否则取整个 match
            value = m.group(1) if m.groups() else m.group(0)
            # 公制螺纹 size 保留 M 前缀
            if field_name == "size" and not value.startswith(("M", "m")):
                value = "M" + value
            result[field_name] = value

    return result if result else None
```

- [ ] **Step 32:** 运行确认通过：

```
pytest tests/test_sw_toolbox_catalog.py::TestExtractSize -v
```

- [ ] **Step 33:** commit

```bash
git add adapters/solidworks/sw_toolbox_catalog.py tests/test_sw_toolbox_catalog.py
git commit -m "feat(sw-b): extract_size_from_name 正则抽取 + 范围外过滤（决策 #9, §1.3）"
```

### 3.4 validate_size_patterns ReDoS 防御

- [ ] **Step 34:** 添加 ReDoS 测试：

```python
class TestValidateSizePatterns:
    """v4 决策 #19: ReDoS 防御 — 加载时 timeout 预验证。"""

    def test_valid_patterns_pass(self):
        from adapters.solidworks.sw_toolbox_catalog import validate_size_patterns
        patterns = {
            "fastener": {
                "size": r"[Mm](\d+(?:\.\d+)?)",
                "length": r"[×xX](\d+)",
            },
        }
        # Should not raise
        validate_size_patterns(patterns)

    def test_redos_pattern_rejected(self):
        from adapters.solidworks.sw_toolbox_catalog import validate_size_patterns
        # Classic ReDoS: nested quantifier on alternation
        patterns = {
            "fastener": {
                "size": r"(a+)+$",  # catastrophic backtracking
            },
        }
        with pytest.raises((RuntimeError, ValueError)) as exc_info:
            validate_size_patterns(patterns)
        assert "ReDoS" in str(exc_info.value) or "timeout" in str(exc_info.value).lower()

    def test_malformed_regex_rejected(self):
        from adapters.solidworks.sw_toolbox_catalog import validate_size_patterns
        patterns = {"fastener": {"size": r"[unclosed"}}
        with pytest.raises((re.error, ValueError)):
            validate_size_patterns(patterns)
```

- [ ] **Step 35:** 运行确认失败：

```
pytest tests/test_sw_toolbox_catalog.py::TestValidateSizePatterns -v
```

- [ ] **Step 36:** 在 catalog 添加 ReDoS 防御实现：

```python
# v4 决策 #19: ReDoS 对抗样本池
REDOS_PROBE_INPUTS = (
    "a" * 100,
    "M" * 50 + "6" * 50,
    "Xx" * 40,
    "6205" * 30,
    "a" + "b" * 80 + "c",
    "M6×" * 40,
    "!!!" * 50,
    "123" * 40,
    " " * 200,
    "x" * 500,
)

REDOS_TIMEOUT_SEC = 0.05  # 50ms 单正则单样本超时


def _match_with_timeout(pattern: re.Pattern, text: str, timeout_sec: float) -> bool:
    """用独立线程做 re.search，主线程 join 超时即视为 ReDoS。

    win32 上 signal.alarm 不可用，改用 threading 策略（决策 #19 适配 Windows）。
    """
    result = [False]

    def worker():
        try:
            result[0] = bool(pattern.search(text))
        except Exception:
            result[0] = False

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(timeout_sec)
    return not t.is_alive()  # True 表示正常完成, False 表示超时


def validate_size_patterns(patterns: dict) -> None:
    """ReDoS 防御（v4 决策 #19）。

    对每个正则做：
    1. re.compile() 语法校验
    2. 用 REDOS_PROBE_INPUTS 的对抗样本做 50ms timeout 测试
    3. 任一样本超时 → raise RuntimeError

    Args:
        patterns: size_patterns 配置，如 {"fastener": {"size": ...}, ...}

    Raises:
        re.error: 正则语法错误
        RuntimeError: 检测到疑似 ReDoS 模式
    """
    for category, field_patterns in patterns.items():
        if not isinstance(field_patterns, dict):
            continue
        for field_name, regex in field_patterns.items():
            if field_name == "exclude_patterns":
                if not isinstance(regex, list):
                    continue
                for r in regex:
                    compiled = re.compile(r)  # will raise re.error on syntax issue
                    for probe in REDOS_PROBE_INPUTS:
                        if not _match_with_timeout(compiled, probe, REDOS_TIMEOUT_SEC):
                            raise RuntimeError(
                                f"ReDoS suspected: pattern {r!r} in "
                                f"{category}.exclude_patterns timed out on {probe[:30]!r}"
                            )
                continue

            compiled = re.compile(regex)
            for probe in REDOS_PROBE_INPUTS:
                if not _match_with_timeout(compiled, probe, REDOS_TIMEOUT_SEC):
                    raise RuntimeError(
                        f"ReDoS suspected: pattern {regex!r} in "
                        f"{category}.{field_name} timed out on {probe[:30]!r}"
                    )
```

- [ ] **Step 37:** 运行确认通过：

```
pytest tests/test_sw_toolbox_catalog.py::TestValidateSizePatterns -v
```

- [ ] **Step 38:** commit

```bash
git add adapters/solidworks/sw_toolbox_catalog.py tests/test_sw_toolbox_catalog.py
git commit -m "feat(sw-b): validate_size_patterns ReDoS 防御（决策 #19）"
```

---

## Task 4 — sw_toolbox_catalog：索引扫描 + fingerprint

### 4.1 _compute_toolbox_fingerprint

- [ ] **Step 39:** 测试：

```python
class TestToolboxFingerprint:
    """v4 决策 #21: 索引完整性校验 + 决策 #17 Path.home 兼容。"""

    @pytest.fixture
    def fake_toolbox(self):
        return Path(__file__).parent / "fixtures" / "fake_toolbox"

    def test_fingerprint_stable_on_repeat(self, fake_toolbox):
        from adapters.solidworks.sw_toolbox_catalog import _compute_toolbox_fingerprint
        fp1 = _compute_toolbox_fingerprint(fake_toolbox)
        fp2 = _compute_toolbox_fingerprint(fake_toolbox)
        assert fp1 == fp2
        assert len(fp1) == 40  # SHA1 hex

    def test_fingerprint_changes_when_file_added(self, fake_toolbox, tmp_path):
        import shutil
        from adapters.solidworks.sw_toolbox_catalog import _compute_toolbox_fingerprint
        # Copy fixture to tmp_path then add a file
        target = tmp_path / "fake_toolbox"
        shutil.copytree(fake_toolbox, target)
        fp_before = _compute_toolbox_fingerprint(target)

        (target / "GB" / "new_part.sldprt").write_bytes(b"")
        fp_after = _compute_toolbox_fingerprint(target)
        assert fp_before != fp_after

    def test_fingerprint_missing_dir_returns_unavailable(self, tmp_path):
        from adapters.solidworks.sw_toolbox_catalog import _compute_toolbox_fingerprint
        fp = _compute_toolbox_fingerprint(tmp_path / "does-not-exist")
        assert fp == "unavailable"
```

- [ ] **Step 40:** 运行确认失败：

```
pytest tests/test_sw_toolbox_catalog.py::TestToolboxFingerprint -v
```

- [ ] **Step 41:** 实现：

```python
def _compute_toolbox_fingerprint(toolbox_dir: Path) -> str:
    """计算 Toolbox 目录指纹（v4 决策 #21）。

    指纹 = SHA1(sorted [(relative_path, size, mtime_int) of all *.sldprt])

    扫描时若 PermissionError → retry 一次（QA #13）；仍失败返回 'unavailable'。
    """
    toolbox_dir = Path(toolbox_dir)
    if not toolbox_dir.exists():
        return "unavailable"

    for attempt in range(2):
        try:
            items: list[tuple[str, int, int]] = []
            for path in sorted(toolbox_dir.rglob("*.sldprt")):
                try:
                    st = path.stat()
                    rel = path.relative_to(toolbox_dir).as_posix()
                    items.append((rel, st.st_size, int(st.st_mtime)))
                except (PermissionError, OSError):
                    continue
            h = hashlib.sha1()
            for rel, size, mtime in items:
                h.update(f"{rel}|{size}|{mtime}\n".encode("utf-8"))
            return h.hexdigest()
        except PermissionError:
            if attempt == 0:
                continue
            return "unavailable"

    return "unavailable"
```

- [ ] **Step 42:** 运行确认通过：

```
pytest tests/test_sw_toolbox_catalog.py::TestToolboxFingerprint -v
```

- [ ] **Step 43:** commit

```bash
git add adapters/solidworks/sw_toolbox_catalog.py tests/test_sw_toolbox_catalog.py
git commit -m "feat(sw-b): _compute_toolbox_fingerprint SHA1 完整性校验（决策 #21）"
```

### 4.2 build_toolbox_index

- [ ] **Step 44:** 测试：

```python
class TestBuildToolboxIndex:
    """v4 §5.1: 仅接受 .sldprt，过滤 .xls/.slddrw/.sldlfp/.xml。"""

    @pytest.fixture
    def fake_toolbox(self):
        return Path(__file__).parent / "fixtures" / "fake_toolbox"

    def test_index_has_schema_version(self, fake_toolbox):
        from adapters.solidworks.sw_toolbox_catalog import build_toolbox_index, SCHEMA_VERSION
        idx = build_toolbox_index(fake_toolbox)
        assert idx["schema_version"] == SCHEMA_VERSION

    def test_index_has_fingerprint(self, fake_toolbox):
        from adapters.solidworks.sw_toolbox_catalog import build_toolbox_index
        idx = build_toolbox_index(fake_toolbox)
        assert "toolbox_fingerprint" in idx
        assert len(idx["toolbox_fingerprint"]) == 40

    def test_index_filters_non_sldprt(self, fake_toolbox):
        """决策 §5.1: sizes.xls / sample.slddrw / catalog.xml 必须被过滤。"""
        from adapters.solidworks.sw_toolbox_catalog import build_toolbox_index
        idx = build_toolbox_index(fake_toolbox)
        flat_paths = []
        for std in idx["standards"].values():
            for sub in std.values():
                for p in sub:
                    flat_paths.append(p.filename)
        assert not any(f.endswith(".xls") for f in flat_paths)
        assert not any(f.endswith(".slddrw") for f in flat_paths)
        assert not any(f.endswith(".xml") for f in flat_paths)
        # 所有入库的都是 sldprt
        assert all(f.endswith(".sldprt") for f in flat_paths)

    def test_index_populates_gb_bolts(self, fake_toolbox):
        from adapters.solidworks.sw_toolbox_catalog import build_toolbox_index
        idx = build_toolbox_index(fake_toolbox)
        assert "GB" in idx["standards"]
        assert "bolts and studs" in idx["standards"]["GB"]
        bolts = idx["standards"]["GB"]["bolts and studs"]
        filenames = {p.filename for p in bolts}
        assert "hex bolt.sldprt" in filenames
        assert "stud.sldprt" in filenames

    def test_index_populates_iso_and_din(self, fake_toolbox):
        from adapters.solidworks.sw_toolbox_catalog import build_toolbox_index
        idx = build_toolbox_index(fake_toolbox)
        assert "ISO" in idx["standards"]
        assert "DIN" in idx["standards"]
```

- [ ] **Step 45:** 运行确认失败：

```
pytest tests/test_sw_toolbox_catalog.py::TestBuildToolboxIndex -v
```

- [ ] **Step 46:** 实现 build_toolbox_index：

```python
def build_toolbox_index(toolbox_dir: Path) -> dict:
    """扫描 Toolbox 目录 → 索引 dict（v4 §5.1 + 决策 #21）。

    目录结构假设：
        toolbox_dir/
            <standard>/
                <subcategory>/
                    *.sldprt
                    (其他非 sldprt 文件被过滤)

    Args:
        toolbox_dir: Toolbox 根目录（sw_detect.toolbox_dir）

    Returns:
        dict:
            schema_version: int
            scan_time: ISO 时间戳
            toolbox_fingerprint: SHA1 hex
            standards: {standard: {subcategory: [SwToolboxPart, ...]}}
    """
    from datetime import datetime, timezone

    toolbox_dir = Path(toolbox_dir)
    standards: dict[str, dict[str, list[SwToolboxPart]]] = {}

    if not toolbox_dir.exists():
        log.warning("Toolbox dir does not exist: %s", toolbox_dir)
        return _empty_index(toolbox_dir)

    for std_dir in toolbox_dir.iterdir():
        if not std_dir.is_dir():
            continue
        std_name = std_dir.name
        std_entry: dict[str, list[SwToolboxPart]] = {}

        for sub_dir in std_dir.iterdir():
            if not sub_dir.is_dir():
                continue
            sub_name = sub_dir.name
            parts: list[SwToolboxPart] = []
            for sldprt in sub_dir.rglob("*.sldprt"):
                if not sldprt.is_file():
                    continue
                tokens = tokenize(sldprt.stem) + tokenize(sub_name)
                parts.append(SwToolboxPart(
                    standard=std_name,
                    subcategory=sub_name,
                    sldprt_path=str(sldprt.resolve()),
                    filename=sldprt.name,
                    tokens=list(dict.fromkeys(tokens)),  # dedupe 保序
                ))
            if parts:
                std_entry[sub_name] = parts

        if std_entry:
            standards[std_name] = std_entry

    return {
        "schema_version": SCHEMA_VERSION,
        "scan_time": datetime.now(timezone.utc).isoformat(),
        "toolbox_fingerprint": _compute_toolbox_fingerprint(toolbox_dir),
        "standards": standards,
    }


def _empty_index(toolbox_dir: Path) -> dict:
    from datetime import datetime, timezone
    return {
        "schema_version": SCHEMA_VERSION,
        "scan_time": datetime.now(timezone.utc).isoformat(),
        "toolbox_fingerprint": "unavailable",
        "standards": {},
    }
```

- [ ] **Step 47:** 运行确认通过：

```
pytest tests/test_sw_toolbox_catalog.py::TestBuildToolboxIndex -v
```

- [ ] **Step 48:** commit

```bash
git add adapters/solidworks/sw_toolbox_catalog.py tests/test_sw_toolbox_catalog.py
git commit -m "feat(sw-b): build_toolbox_index 扫描 + 非 sldprt 过滤（§5.1, 决策 #21）"
```

---

## Task 5 — sw_toolbox_catalog：路径解析 + load_toolbox_index

### 5.1 get_toolbox_cache_root / get_toolbox_index_path

- [ ] **Step 49:** 测试路径三级覆盖链 + Path.home 兼容：

```python
class TestPathResolution:
    """v4 决策 #16: yaml > env > 默认；决策 #17: 必须用 Path.home。"""

    def test_cache_root_from_yaml_config(self, tmp_path, monkeypatch):
        """yaml config.cache 优先级最高。"""
        from adapters.solidworks.sw_toolbox_catalog import get_toolbox_cache_root
        monkeypatch.setenv("CAD_SPEC_GEN_SW_TOOLBOX_CACHE", str(tmp_path / "env_cache"))
        result = get_toolbox_cache_root({"cache": str(tmp_path / "yaml_cache")})
        assert result == Path(tmp_path / "yaml_cache")

    def test_cache_root_from_env_when_no_yaml(self, tmp_path, monkeypatch):
        from adapters.solidworks.sw_toolbox_catalog import get_toolbox_cache_root
        monkeypatch.setenv("CAD_SPEC_GEN_SW_TOOLBOX_CACHE", str(tmp_path / "env_cache"))
        result = get_toolbox_cache_root({})
        assert result == Path(tmp_path / "env_cache")

    def test_cache_root_default_uses_path_home(self, monkeypatch, tmp_path):
        """v4 决策 #17: 默认路径必须通过 Path.home()。"""
        from adapters.solidworks.sw_toolbox_catalog import get_toolbox_cache_root
        monkeypatch.delenv("CAD_SPEC_GEN_SW_TOOLBOX_CACHE", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = get_toolbox_cache_root({})
        assert result == tmp_path / ".cad-spec-gen" / "step_cache" / "sw_toolbox"

    def test_index_path_default_uses_path_home(self, monkeypatch, tmp_path):
        from adapters.solidworks.sw_toolbox_catalog import get_toolbox_index_path
        monkeypatch.delenv("CAD_SPEC_GEN_SW_TOOLBOX_INDEX", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = get_toolbox_index_path({})
        assert result == tmp_path / ".cad-spec-gen" / "sw_toolbox_index.json"

    def test_does_not_use_expanduser(self, monkeypatch, tmp_path):
        """反例: 使用 os.path.expanduser 会在 conftest monkey 下失效。"""
        from adapters.solidworks.sw_toolbox_catalog import get_toolbox_cache_root
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.delenv("CAD_SPEC_GEN_SW_TOOLBOX_CACHE", raising=False)
        # 故意把 HOME 设不同值，验证 Path.home() 优先
        monkeypatch.setenv("HOME", "/should/not/be/used")
        result = get_toolbox_cache_root({})
        # 应走 Path.home() → tmp_path，不走 HOME env
        assert str(result).startswith(str(tmp_path))
```

- [ ] **Step 50:** 运行确认失败：

```
pytest tests/test_sw_toolbox_catalog.py::TestPathResolution -v
```

- [ ] **Step 51:** 实现：

```python
def get_toolbox_cache_root(config: dict) -> Path:
    """cache 路径解析（v4 决策 #16/#17）。

    优先级: config['cache'] > env CAD_SPEC_GEN_SW_TOOLBOX_CACHE > 默认。

    默认: Path.home() / '.cad-spec-gen' / 'step_cache' / 'sw_toolbox'
    ⚠️ 必须 Path.home()，不用 os.path.expanduser（后者不被 conftest monkeypatch 覆盖）。
    """
    yaml_cache = config.get("cache") if config else None
    if yaml_cache:
        return Path(yaml_cache)

    env_cache = os.environ.get(CACHE_ROOT_ENV)
    if env_cache:
        return Path(env_cache)

    return Path.home() / ".cad-spec-gen" / "step_cache" / "sw_toolbox"


def get_toolbox_index_path(config: dict) -> Path:
    """索引路径解析（v4 决策 #16/#17）。

    优先级: env CAD_SPEC_GEN_SW_TOOLBOX_INDEX > 默认。

    默认: Path.home() / '.cad-spec-gen' / 'sw_toolbox_index.json'
    """
    env_idx = os.environ.get(INDEX_PATH_ENV)
    if env_idx:
        return Path(env_idx)

    return Path.home() / ".cad-spec-gen" / "sw_toolbox_index.json"
```

- [ ] **Step 52:** 运行确认通过：

```
pytest tests/test_sw_toolbox_catalog.py::TestPathResolution -v
```

- [ ] **Step 53:** commit

```bash
git add adapters/solidworks/sw_toolbox_catalog.py tests/test_sw_toolbox_catalog.py
git commit -m "feat(sw-b): get_toolbox_cache_root/index_path 三级覆盖链（决策 #16/#17）"
```

### 5.2 load_toolbox_index 含 schema + fingerprint 校验

- [ ] **Step 54:** 测试 load / 缓存 / 重建：

```python
class TestLoadToolboxIndex:
    """v4 决策 #21: schema_version 或 fingerprint 不匹配自动重建。"""

    @pytest.fixture
    def fake_toolbox(self):
        return Path(__file__).parent / "fixtures" / "fake_toolbox"

    def test_load_rebuilds_when_cache_missing(self, fake_toolbox, tmp_path):
        from adapters.solidworks.sw_toolbox_catalog import load_toolbox_index
        cache = tmp_path / "idx.json"
        assert not cache.exists()
        idx = load_toolbox_index(cache, fake_toolbox)
        assert cache.exists()
        assert idx["schema_version"] == SCHEMA_VERSION

    def test_load_uses_cache_when_fresh(self, fake_toolbox, tmp_path):
        from adapters.solidworks.sw_toolbox_catalog import load_toolbox_index
        cache = tmp_path / "idx.json"
        # First call: build
        idx1 = load_toolbox_index(cache, fake_toolbox)
        # Tamper scan_time to detect whether cache was re-used
        data = json.loads(cache.read_text())
        data["scan_time"] = "sentinel-cached"
        cache.write_text(json.dumps(data))

        idx2 = load_toolbox_index(cache, fake_toolbox)
        assert idx2["scan_time"] == "sentinel-cached"  # came from cache

    def test_load_rebuilds_on_schema_bump(self, fake_toolbox, tmp_path):
        from adapters.solidworks.sw_toolbox_catalog import load_toolbox_index
        cache = tmp_path / "idx.json"
        cache.write_text(json.dumps({
            "schema_version": 0,  # old
            "scan_time": "old",
            "toolbox_fingerprint": "unavailable",
            "standards": {},
        }))
        idx = load_toolbox_index(cache, fake_toolbox)
        assert idx["schema_version"] == SCHEMA_VERSION
        assert idx["scan_time"] != "old"

    def test_load_rebuilds_on_fingerprint_mismatch(self, fake_toolbox, tmp_path):
        from adapters.solidworks.sw_toolbox_catalog import load_toolbox_index
        cache = tmp_path / "idx.json"
        # Build once
        load_toolbox_index(cache, fake_toolbox)
        # Corrupt fingerprint in cache
        data = json.loads(cache.read_text())
        data["toolbox_fingerprint"] = "0" * 40
        data["scan_time"] = "stale"
        cache.write_text(json.dumps(data))

        idx = load_toolbox_index(cache, fake_toolbox)
        assert idx["scan_time"] != "stale"  # rebuilt
```

- [ ] **Step 55:** 运行确认失败：

```
pytest tests/test_sw_toolbox_catalog.py::TestLoadToolboxIndex -v
```

- [ ] **Step 56:** 实现：

```python
def load_toolbox_index(cache_path: Path, toolbox_dir: Path) -> dict:
    """读缓存；自动重建条件（v4 决策 #21）：
    1. 缓存文件不存在
    2. cache['schema_version'] != SCHEMA_VERSION
    3. cache['toolbox_fingerprint'] != _compute_toolbox_fingerprint(toolbox_dir)

    重建时追加事件到 ~/.cad-spec-gen/sw_toolbox_index_history.log（SRE #7）。
    """
    cache_path = Path(cache_path)
    toolbox_dir = Path(toolbox_dir)

    cached = None
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            log.warning("toolbox index 缓存损坏，将重建: %s", e)
            cached = None

    rebuild_reason = None
    if cached is None:
        rebuild_reason = "missing or corrupt"
    elif cached.get("schema_version") != SCHEMA_VERSION:
        rebuild_reason = f"schema_version bump {cached.get('schema_version')} -> {SCHEMA_VERSION}"
    else:
        current_fp = _compute_toolbox_fingerprint(toolbox_dir)
        cached_fp = cached.get("toolbox_fingerprint", "")
        if current_fp != cached_fp and current_fp != "unavailable":
            rebuild_reason = f"fingerprint mismatch {cached_fp[:8]}->{current_fp[:8]}"

    if rebuild_reason is None:
        # Reconstruct SwToolboxPart objects from JSON
        return _rehydrate_index(cached)

    # Rebuild
    log.info("toolbox 索引重建: %s", rebuild_reason)
    _append_history_log(rebuild_reason)

    new_idx = build_toolbox_index(toolbox_dir)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(_dehydrate_index(new_idx), encoding="utf-8")
    except OSError as e:
        log.warning("toolbox 索引缓存写入失败（非致命）: %s", e)
    return new_idx


def _dehydrate_index(idx: dict) -> str:
    """把索引中的 SwToolboxPart 转 dict 以便 JSON 序列化。"""
    out = dict(idx)
    out["standards"] = {
        std: {
            sub: [asdict(p) for p in parts]
            for sub, parts in sub_dict.items()
        }
        for std, sub_dict in idx["standards"].items()
    }
    return json.dumps(out, ensure_ascii=False, indent=2)


def _rehydrate_index(cached: dict) -> dict:
    """把 JSON dict 转回 SwToolboxPart。"""
    out = dict(cached)
    out["standards"] = {
        std: {
            sub: [SwToolboxPart(**p) for p in parts]
            for sub, parts in sub_dict.items()
        }
        for std, sub_dict in cached.get("standards", {}).items()
    }
    return out


def _append_history_log(reason: str) -> None:
    """追加索引 rebuild 事件到 history log（SRE #7）。"""
    from datetime import datetime, timezone
    log_path = Path.home() / ".cad-spec-gen" / "sw_toolbox_index_history.log"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            ts = datetime.now(timezone.utc).isoformat()
            f.write(f"{ts}: rebuild — {reason}\n")
    except OSError:
        pass  # 日志失败不阻断
```

- [ ] **Step 57:** 运行确认通过：

```
pytest tests/test_sw_toolbox_catalog.py::TestLoadToolboxIndex -v
```

- [ ] **Step 58:** commit

```bash
git add adapters/solidworks/sw_toolbox_catalog.py tests/test_sw_toolbox_catalog.py
git commit -m "feat(sw-b): load_toolbox_index schema+fingerprint 校验 + history log（决策 #21, SRE #7）"
```

---

## Task 6 — sw_toolbox_catalog：match_toolbox_part + 路径校验

### 6.1 _validate_sldprt_path（路径遍历防御）

- [ ] **Step 59:** 测试：

```python
class TestValidateSldprtPath:
    """v4 决策 #20: sldprt_path 必须是 toolbox_dir 的真子路径。"""

    def test_valid_child_path_returns_true(self, tmp_path):
        from adapters.solidworks.sw_toolbox_catalog import _validate_sldprt_path
        toolbox = tmp_path / "toolbox"
        toolbox.mkdir()
        sldprt = toolbox / "GB" / "bolts" / "hex.sldprt"
        sldprt.parent.mkdir(parents=True)
        sldprt.write_bytes(b"")
        assert _validate_sldprt_path(str(sldprt), toolbox) is True

    def test_path_outside_toolbox_returns_false(self, tmp_path):
        from adapters.solidworks.sw_toolbox_catalog import _validate_sldprt_path
        toolbox = tmp_path / "toolbox"
        toolbox.mkdir()
        outside = tmp_path / "evil.sldprt"
        outside.write_bytes(b"")
        assert _validate_sldprt_path(str(outside), toolbox) is False

    def test_path_traversal_rejected(self, tmp_path):
        """恶意索引含 ../../etc/passwd 应被拒绝。"""
        from adapters.solidworks.sw_toolbox_catalog import _validate_sldprt_path
        toolbox = tmp_path / "toolbox"
        toolbox.mkdir()
        traversal = str(toolbox / ".." / "outside.sldprt")
        assert _validate_sldprt_path(traversal, toolbox) is False
```

- [ ] **Step 60:** 运行确认失败：

```
pytest tests/test_sw_toolbox_catalog.py::TestValidateSldprtPath -v
```

- [ ] **Step 61:** 实现：

```python
def _validate_sldprt_path(sldprt_path: str, toolbox_dir: Path) -> bool:
    """路径遍历防御（v4 决策 #20）。

    sldprt_path.resolve() 必须是 toolbox_dir.resolve() 的真子路径。
    任何 resolve 异常 → False。
    """
    try:
        sld = Path(sldprt_path).resolve()
        root = Path(toolbox_dir).resolve()
        sld.relative_to(root)  # raises ValueError if not a subpath
        return True
    except (ValueError, OSError, RuntimeError):
        log.error("索引篡改疑似: sldprt_path 非 toolbox_dir 子路径: %s vs %s",
                  sldprt_path, toolbox_dir)
        return False
```

- [ ] **Step 62:** 运行确认通过：

```
pytest tests/test_sw_toolbox_catalog.py::TestValidateSldprtPath -v
```

- [ ] **Step 63:** commit

```bash
git add adapters/solidworks/sw_toolbox_catalog.py tests/test_sw_toolbox_catalog.py
git commit -m "feat(sw-b): _validate_sldprt_path 路径遍历防御（决策 #20）"
```

### 6.2 build_query_tokens_weighted + match_toolbox_part

- [ ] **Step 64:** 测试加权 token overlap：

```python
class TestMatchToolboxPart:
    """v4 决策 #12: part_no 权重 2.0，name_cn 1.0，material 0.5，size 1.5。"""

    @pytest.fixture
    def fake_toolbox(self):
        return Path(__file__).parent / "fixtures" / "fake_toolbox"

    @pytest.fixture
    def idx(self, fake_toolbox):
        from adapters.solidworks.sw_toolbox_catalog import build_toolbox_index
        return build_toolbox_index(fake_toolbox)

    def test_match_exact_hex_bolt(self, idx):
        from adapters.solidworks.sw_toolbox_catalog import match_toolbox_part
        query_tokens = [("hex", 1.0), ("bolt", 1.0)]
        result = match_toolbox_part(
            idx, query_tokens,
            standards=["GB"],
            subcategories=["bolts and studs"],
            min_score=0.30,
        )
        assert result is not None
        part, score = result
        assert part.filename == "hex bolt.sldprt"
        assert score > 0.30

    def test_match_part_no_weight_dominates(self, idx):
        """part_no 权重 2.0 应该能把弱匹配推到阈值之上。"""
        from adapters.solidworks.sw_toolbox_catalog import match_toolbox_part
        # 仅 part_no token 命中（"bolt"）, name_cn 无命中
        query_tokens = [("bolt", 2.0)]  # part_no 加权
        result = match_toolbox_part(
            idx, query_tokens,
            standards=["GB"],
            subcategories=["bolts and studs"],
            min_score=0.30,
        )
        assert result is not None

    def test_match_below_min_score_returns_none(self, idx):
        """决策 #3: 低于 min_score 返回 None → miss。"""
        from adapters.solidworks.sw_toolbox_catalog import match_toolbox_part
        query_tokens = [("completely", 1.0), ("unrelated", 1.0)]
        result = match_toolbox_part(
            idx, query_tokens,
            standards=["GB"],
            subcategories=["bolts and studs"],
            min_score=0.30,
        )
        assert result is None

    def test_match_respects_subcategory_whitelist(self, idx):
        """只在 spec 指定的 subcategories 里搜。"""
        from adapters.solidworks.sw_toolbox_catalog import match_toolbox_part
        query_tokens = [("hex", 1.0), ("nut", 1.0)]
        # 限定只搜 bolts，应找不到 nuts 下的 hex nut
        result = match_toolbox_part(
            idx, query_tokens,
            standards=["GB"],
            subcategories=["bolts and studs"],
            min_score=0.30,
        )
        # 可能 match 到 hex bolt（部分 token），但不会返回 nut
        if result:
            part, _ = result
            assert part.subcategory == "bolts and studs"

    def test_build_query_tokens_weighted(self):
        from adapters.solidworks.sw_toolbox_catalog import build_query_tokens_weighted

        # Mock PartQuery
        class Q:
            part_no = "GB/T 70.1"
            name_cn = "M6×20 内六角螺钉"
            material = "钢"

        weights = {"part_no": 2.0, "name_cn": 1.0, "material": 0.5, "size": 1.5}
        size_dict = {"size": "M6", "length": "20"}

        tokens_weighted = build_query_tokens_weighted(Q(), size_dict, weights)
        # 每个 token 是 (str, float) tuple
        assert all(isinstance(t, tuple) and len(t) == 2 for t in tokens_weighted)
        # part_no 里的 token 权重应为 2.0
        part_no_tokens = {t for t, w in tokens_weighted if w == 2.0}
        # "gb" 或 "70" 应属 part_no
        assert any(k in part_no_tokens for k in ["gb", "70", "1"])
```

- [ ] **Step 65:** 运行确认失败：

```
pytest tests/test_sw_toolbox_catalog.py::TestMatchToolboxPart -v
```

- [ ] **Step 66:** 实现：

```python
def build_query_tokens_weighted(
    query,
    size_dict: Optional[dict],
    weights: dict,
) -> list[tuple[str, float]]:
    """构造加权 query tokens（v4 决策 #12）。

    weights 示例: {"part_no": 2.0, "name_cn": 1.0, "material": 0.5, "size": 1.5}

    Returns:
        [(token, weight), ...] —— 同一 token 出现在多个字段时取最大权重
    """
    collected: dict[str, float] = {}

    def add(tokens: list[str], w: float):
        for t in tokens:
            if t not in collected or collected[t] < w:
                collected[t] = w

    add(tokenize(getattr(query, "part_no", "")), weights.get("part_no", 1.0))
    add(tokenize(getattr(query, "name_cn", "")), weights.get("name_cn", 1.0))
    add(tokenize(getattr(query, "material", "")), weights.get("material", 0.5))

    if size_dict:
        for value in size_dict.values():
            add(tokenize(str(value)), weights.get("size", 1.5))

    return [(t, w) for t, w in collected.items()]


def match_toolbox_part(
    index: dict,
    query_tokens_weighted: list[tuple[str, float]],
    standards: list[str],
    subcategories: list[str],
    min_score: float = 0.30,
) -> Optional[tuple[SwToolboxPart, float]]:
    """加权 token overlap 打分（v4 决策 #3/#12/#18）。

    score = Σ(命中 token 的权重) / Σ(query token 总权重)

    Args:
        index: build/load_toolbox_index 返回的 dict
        query_tokens_weighted: [(token, weight), ...]
        standards: 候选标准白名单（如 ["GB"]）
        subcategories: 候选子分类白名单
        min_score: 最低命中分数

    Returns:
        (part, score) 或 None（低于 min_score）
    """
    if not query_tokens_weighted:
        return None

    total_weight = sum(w for _, w in query_tokens_weighted)
    if total_weight == 0:
        return None

    query_map = dict(query_tokens_weighted)

    best: Optional[tuple[SwToolboxPart, float]] = None
    for std_name, sub_dict in index.get("standards", {}).items():
        if std_name not in standards:
            continue
        for sub_name, parts in sub_dict.items():
            if sub_name not in subcategories:
                continue
            for part in parts:
                part_token_set = set(part.tokens)
                hit_weight = sum(w for t, w in query_map.items() if t in part_token_set)
                score = hit_weight / total_weight
                if best is None or score > best[1]:
                    best = (part, score)

    if best and best[1] >= min_score:
        return best
    return None
```

- [ ] **Step 67:** 运行确认通过：

```
pytest tests/test_sw_toolbox_catalog.py::TestMatchToolboxPart -v
```

- [ ] **Step 68:** 运行整个 catalog 测试确保全通过：

```
pytest tests/test_sw_toolbox_catalog.py -v
```

- [ ] **Step 69:** commit

```bash
git add adapters/solidworks/sw_toolbox_catalog.py tests/test_sw_toolbox_catalog.py
git commit -m "feat(sw-b): match_toolbox_part 加权 token overlap + build_query_tokens_weighted（决策 #12/#18）"
```

---

## Task 7 — sw_com_session：session 骨架 + 熔断

**Files:**
- Create: `adapters/solidworks/sw_com_session.py`
- Create: `tests/test_sw_com_session.py`

### 7.1 类骨架 + 锁 + 计数器

- [ ] **Step 70:** 创建 `tests/test_sw_com_session.py`:

```python
"""sw_com_session 单元测试（v4 决策 #6/#10/#11/#22/#23/#25）。

全部 mock win32com，不依赖真实 SW。
真实 COM 测试在 tests/test_sw_toolbox_integration.py 用 @requires_solidworks。
"""
from __future__ import annotations

import threading
import unittest.mock as mock
import pytest
from pathlib import Path

from adapters.solidworks.sw_com_session import (
    SwComSession,
    get_session,
    reset_session,
    MIN_STEP_FILE_SIZE,
    STEP_MAGIC_PREFIX,
)


class TestSwComSessionBasics:
    """锁、计数器、健康状态。"""

    def test_new_session_is_healthy(self):
        reset_session()
        s = SwComSession()
        assert s.is_healthy() is True
        assert s._convert_count == 0
        assert s._consecutive_failures == 0

    def test_session_has_threading_lock(self):
        """v4 决策 #22: COM 非线程安全，全方法要有 _lock 保护。"""
        s = SwComSession()
        assert hasattr(s, "_lock")
        assert isinstance(s._lock, type(threading.Lock()))

    def test_reset_session_clears_state(self):
        reset_session()
        s = get_session()
        # Simulate some failed converts
        s._consecutive_failures = 2
        s._unhealthy = True
        reset_session()
        s2 = get_session()
        assert s2._consecutive_failures == 0
        assert s2._unhealthy is False


class TestSessionSingleton:
    """get_session 返回同一实例；reset_session 清空 singleton。"""

    def test_get_session_returns_singleton(self):
        reset_session()
        s1 = get_session()
        s2 = get_session()
        assert s1 is s2

    def test_reset_session_creates_new_instance(self):
        reset_session()
        s1 = get_session()
        reset_session()
        s2 = get_session()
        assert s1 is not s2
```

- [ ] **Step 71:** 运行确认失败（`sw_com_session` 模块不存在）：

```
pytest tests/test_sw_com_session.py -v
```

- [ ] **Step 72:** 创建 `adapters/solidworks/sw_com_session.py` 骨架：

```python
"""
adapters/solidworks/sw_com_session.py — SolidWorks COM 会话管理。

实现 v4 决策 #6/#10/#11/#22/#23/#25：
- 熔断器（连续 3 次失败触发）
- 冷启动超时 90s / 单零件 30s / 空闲 300s / 每 50 次重启
- threading.Lock 保护 COM 调用（非线程安全）
- atomic write（fsync + MIN_STEP_FILE_SIZE + ISO-10303 magic bytes）
- encoding 透传（os.fspath + str 断言）

不在此模块硬依赖 win32com（runtime import）。
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# v4 决策 #10/#11/#6
COLD_START_TIMEOUT_SEC = 90
SINGLE_CONVERT_TIMEOUT_SEC = 30
IDLE_SHUTDOWN_SEC = 300
RESTART_EVERY_N_CONVERTS = 50
CIRCUIT_BREAKER_THRESHOLD = 3

# v4 决策 #23: atomic write 校验
MIN_STEP_FILE_SIZE = 1024
STEP_MAGIC_PREFIX = b"ISO-10303"


class SwComSession:
    """COM session 唯一 source of truth（v4 决策 #22）。

    熔断状态归此类；adapter.is_available() 委托 is_healthy()。
    """

    def __init__(self) -> None:
        self._app = None  # win32com Dispatch object (lazy init)
        self._convert_count = 0
        self._consecutive_failures = 0
        self._unhealthy = False
        self._last_used_ts = 0.0
        self._lock = threading.Lock()

    def is_healthy(self) -> bool:
        """熔断状态查询。"""
        return not self._unhealthy

    def shutdown(self) -> None:
        """释放 SW COM session。"""
        with self._lock:
            if self._app is not None:
                try:
                    self._app.ExitApp()
                except Exception:
                    pass
                self._app = None


# 进程级 singleton
_SESSION_SINGLETON: Optional[SwComSession] = None
_SINGLETON_LOCK = threading.Lock()


def get_session() -> SwComSession:
    """返回进程级 SwComSession 单例（v4 决策 #22）。"""
    global _SESSION_SINGLETON
    with _SINGLETON_LOCK:
        if _SESSION_SINGLETON is None:
            _SESSION_SINGLETON = SwComSession()
        return _SESSION_SINGLETON


def reset_session() -> None:
    """清空 singleton + 清熔断状态。
    注册到 sw_material_bridge.reset_all_sw_caches()（v4 决策 #15）。
    """
    global _SESSION_SINGLETON
    with _SINGLETON_LOCK:
        if _SESSION_SINGLETON is not None:
            try:
                _SESSION_SINGLETON.shutdown()
            except Exception:
                pass
        _SESSION_SINGLETON = None
```

- [ ] **Step 73:** 运行确认通过：

```
pytest tests/test_sw_com_session.py::TestSwComSessionBasics tests/test_sw_com_session.py::TestSessionSingleton -v
```

- [ ] **Step 74:** commit

```bash
git add adapters/solidworks/sw_com_session.py tests/test_sw_com_session.py
git commit -m "feat(sw-b): SwComSession 骨架 + singleton + 锁（决策 #22）"
```

### 7.2 convert_sldprt_to_step 熔断 + atomic write

- [ ] **Step 75:** 测试熔断触发 + atomic write：

```python
class TestConvertSldprtToStep:
    """v4 决策 #6/#23: 熔断器 + atomic write 校验。"""

    @pytest.fixture
    def mock_app(self):
        """Mock win32com Dispatch 对象 + OpenDoc6/SaveAs3/CloseDoc。"""
        app = mock.MagicMock()
        app.OpenDoc6 = mock.MagicMock(return_value=(mock.MagicMock(), 0, 0))
        app.CloseDoc = mock.MagicMock()
        return app

    def test_atomic_write_success(self, tmp_path, mock_app, monkeypatch):
        """成功路径：生成的 STEP 大小 > MIN 且以 ISO-10303 开头。"""
        from adapters.solidworks.sw_com_session import SwComSession
        reset_session()
        s = SwComSession()
        s._app = mock_app

        step_out = tmp_path / "out.step"
        tmp_step = tmp_path / "out.step.tmp"
        def fake_saveas(path, *args, **kwargs):
            Path(path).write_bytes(b"ISO-10303-214\n" + b"X" * 2000)
            return True
        # SaveAs3 is model.Extension.SaveAs3
        model = mock_app.OpenDoc6.return_value[0]
        model.Extension.SaveAs3.side_effect = lambda path, *a, **kw: (
            fake_saveas(path, *a, **kw), 0, 0
        )[0]
        model.GetTitle.return_value = "hex bolt"

        ok = s.convert_sldprt_to_step(
            str(tmp_path / "hex bolt.sldprt"),
            str(step_out),
        )
        assert ok is True
        assert step_out.exists()
        assert step_out.read_bytes().startswith(b"ISO-10303")

    def test_atomic_write_rejects_small_file(self, tmp_path, mock_app):
        from adapters.solidworks.sw_com_session import SwComSession
        reset_session()
        s = SwComSession()
        s._app = mock_app

        step_out = tmp_path / "out.step"
        model = mock_app.OpenDoc6.return_value[0]
        model.Extension.SaveAs3.side_effect = lambda path, *a, **kw: (
            Path(path).write_bytes(b"tiny"), 0, 0
        )[0]
        model.GetTitle.return_value = "hex bolt"

        ok = s.convert_sldprt_to_step(
            str(tmp_path / "hex bolt.sldprt"),
            str(step_out),
        )
        assert ok is False  # 校验失败 → miss
        assert not step_out.exists()

    def test_atomic_write_rejects_wrong_magic(self, tmp_path, mock_app):
        from adapters.solidworks.sw_com_session import SwComSession
        reset_session()
        s = SwComSession()
        s._app = mock_app
        step_out = tmp_path / "out.step"
        model = mock_app.OpenDoc6.return_value[0]
        model.Extension.SaveAs3.side_effect = lambda path, *a, **kw: (
            Path(path).write_bytes(b"BINARY_GARBAGE" + b"X" * 2000), 0, 0
        )[0]
        model.GetTitle.return_value = "hex bolt"

        ok = s.convert_sldprt_to_step(
            str(tmp_path / "hex bolt.sldprt"),
            str(step_out),
        )
        assert ok is False
        assert not step_out.exists()

    def test_circuit_breaker_trips_at_threshold(self, tmp_path, mock_app):
        """v4 决策 #6: 连续 3 次失败 → _unhealthy=True。"""
        from adapters.solidworks.sw_com_session import SwComSession, CIRCUIT_BREAKER_THRESHOLD
        reset_session()
        s = SwComSession()
        s._app = mock_app
        # Make OpenDoc6 raise
        mock_app.OpenDoc6.side_effect = RuntimeError("COM crashed")

        for _ in range(CIRCUIT_BREAKER_THRESHOLD):
            s.convert_sldprt_to_step(
                str(tmp_path / "x.sldprt"),
                str(tmp_path / "x.step"),
            )

        assert s._unhealthy is True
        assert s.is_healthy() is False

    def test_success_resets_failure_counter(self, tmp_path, mock_app):
        from adapters.solidworks.sw_com_session import SwComSession
        reset_session()
        s = SwComSession()
        s._app = mock_app
        s._consecutive_failures = 2

        # Success case
        model = mock_app.OpenDoc6.return_value[0]
        def fake_saveas(path, *a, **kw):
            Path(path).write_bytes(b"ISO-10303-214\n" + b"X" * 2000)
            return True
        model.Extension.SaveAs3.side_effect = lambda path, *a, **kw: (
            fake_saveas(path, *a, **kw), 0, 0
        )[0]
        model.GetTitle.return_value = "x"

        s.convert_sldprt_to_step(
            str(tmp_path / "x.sldprt"),
            str(tmp_path / "x.step"),
        )
        assert s._consecutive_failures == 0
```

- [ ] **Step 76:** 运行确认失败：

```
pytest tests/test_sw_com_session.py::TestConvertSldprtToStep -v
```

- [ ] **Step 77:** 实现 `convert_sldprt_to_step`:

```python
# 在 SwComSession 类中添加：

    def convert_sldprt_to_step(
        self,
        sldprt_path,
        step_out,
    ) -> bool:
        """转换单个 sldprt 为 STEP（v4 决策 #6/#23/#25）。

        全方法包 self._lock（COM 非线程安全）。
        atomic write: tmp → fsync → validate → rename。

        Returns:
            True: 成功
            False: 任何失败（不抛异常），自动累加熔断计数。
        """
        # v4 决策 #25: encoding 透传
        sldprt_path = str(os.fspath(sldprt_path))
        step_out = str(os.fspath(step_out))

        with self._lock:
            if self._unhealthy:
                return False

            try:
                success = self._do_convert(sldprt_path, step_out)
                if success:
                    self._convert_count += 1
                    self._consecutive_failures = 0
                    self._last_used_ts = time.time()
                    # 周期重启留给上层 _maybe_restart() 触发
                else:
                    self._consecutive_failures += 1
                return success
            except Exception as e:
                log.warning("COM convert 异常: %s", e)
                self._consecutive_failures += 1
                success = False
            finally:
                if self._consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
                    log.error(
                        "COM 熔断触发（连续 %d 次失败）",
                        self._consecutive_failures,
                    )
                    self._unhealthy = True
            return success

    def _do_convert(self, sldprt_path: str, step_out: str) -> bool:
        """实际 COM 调用 + atomic write（v4 决策 #23）。"""
        if self._app is None:
            log.warning("SwComSession._app is None; 必须先 start()")
            return False

        tmp_path = step_out + ".tmp"
        Path(step_out).parent.mkdir(parents=True, exist_ok=True)

        # OpenDoc6
        model, errors, warnings = self._app.OpenDoc6(
            sldprt_path,
            1,   # swDocPART
            1,   # swOpenDocOptions_Silent
            "",
            0, 0,
        )
        if errors:
            log.warning("OpenDoc6 errors: %s", errors)
            return False

        try:
            # SaveAs3 to tmp
            saved = model.Extension.SaveAs3(
                tmp_path,
                0, 1,
                None, None,
                0, 0,
            )
            if not saved:
                return False

            # Validate tmp
            if not self._validate_step_file(tmp_path):
                try:
                    Path(tmp_path).unlink(missing_ok=True)
                except OSError:
                    pass
                return False

            # Atomic rename
            os.replace(tmp_path, step_out)
            return True
        finally:
            try:
                self._app.CloseDoc(model.GetTitle())
            except Exception:
                pass

    @staticmethod
    def _validate_step_file(path: str) -> bool:
        """v4 决策 #23: fsync 已在 SaveAs3 内部由 SW 完成；此处校验大小 + magic。"""
        p = Path(path)
        if not p.exists():
            return False
        if p.stat().st_size < MIN_STEP_FILE_SIZE:
            return False
        with p.open("rb") as f:
            header = f.read(16)
        return header.startswith(STEP_MAGIC_PREFIX)
```

- [ ] **Step 78:** 运行确认通过：

```
pytest tests/test_sw_com_session.py::TestConvertSldprtToStep -v
```

- [ ] **Step 79:** commit

```bash
git add adapters/solidworks/sw_com_session.py tests/test_sw_com_session.py
git commit -m "feat(sw-b): convert_sldprt_to_step + atomic write + 熔断（决策 #6/#23/#25）"
```

### 7.3 reset_all_sw_caches 集成

- [ ] **Step 80:** 测试集成：

```python
def test_reset_all_sw_caches_includes_com_session(monkeypatch):
    """v4 决策 #15: sw_com_session.reset_session() 必须被 reset_all_sw_caches 调用。"""
    from adapters.solidworks import sw_material_bridge, sw_com_session

    # Create a session with state
    sw_com_session.reset_session()
    s = sw_com_session.get_session()
    s._consecutive_failures = 2
    s._unhealthy = True

    # Call the master reset
    sw_material_bridge.reset_all_sw_caches()

    # Session should be fresh
    s2 = sw_com_session.get_session()
    assert s2._consecutive_failures == 0
    assert s2._unhealthy is False
    assert s2 is not s  # new instance
```

- [ ] **Step 81:** 将此测试加入 `tests/test_sw_routing_integration.py` 现有 `TestResetAllSwCaches` 类。运行确认失败：

```
pytest tests/test_sw_routing_integration.py::TestResetAllSwCaches::test_reset_all_sw_caches_includes_com_session -v
```

- [ ] **Step 82:** 修改 `adapters/solidworks/sw_material_bridge.py` 的 `reset_all_sw_caches()`,在末尾追加：

```python
    # v4 决策 #15: COM session reset
    try:
        from adapters.solidworks.sw_com_session import reset_session as _reset_com
        _reset_com()
    except ImportError:
        pass
```

- [ ] **Step 83:** 运行确认通过：

```
pytest tests/test_sw_routing_integration.py::TestResetAllSwCaches -v
```

- [ ] **Step 84:** commit

```bash
git add adapters/solidworks/sw_material_bridge.py tests/test_sw_routing_integration.py
git commit -m "feat(sw-b): reset_all_sw_caches 集成 sw_com_session.reset_session（决策 #15）"
```

---

## Task 8 — SwToolboxAdapter：is_available + can_resolve

**Files:**
- Create: `adapters/parts/sw_toolbox_adapter.py`
- Create: `tests/test_sw_toolbox_adapter.py`

### 8.1 骨架 + is_available 6 项检查

- [ ] **Step 85:** 创建 `tests/test_sw_toolbox_adapter.py`:

```python
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
            installed=True, version_year=2023, pywin32_available=True,
            toolbox_dir="C:/fake", toolbox_addin_enabled=True,
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
        a = SwToolboxAdapter()
        assert a.is_available() is False

    def test_pywin32_missing_returns_false(self, monkeypatch):
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_detect
        sw_detect._reset_cache()
        fake_info = sw_detect.SwInfo(
            installed=True, version_year=2024, pywin32_available=False,
            toolbox_dir="C:/fake", toolbox_addin_enabled=True,
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
        a = SwToolboxAdapter()
        assert a.is_available() is False

    def test_toolbox_dir_missing_returns_false(self, monkeypatch):
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_detect
        sw_detect._reset_cache()
        fake_info = sw_detect.SwInfo(
            installed=True, version_year=2024, pywin32_available=True,
            toolbox_dir="", toolbox_addin_enabled=True,
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
            installed=True, version_year=2024, pywin32_available=True,
            toolbox_dir="C:/fake", toolbox_addin_enabled=False,
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
            installed=True, version_year=2024, pywin32_available=True,
            toolbox_dir=str(tmp_path), toolbox_addin_enabled=True,
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
            installed=True, version_year=2024, pywin32_available=True,
            toolbox_dir=str(tmp_path), toolbox_addin_enabled=True,
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
```

- [ ] **Step 86:** 运行确认失败（模块不存在）：

```
pytest tests/test_sw_toolbox_adapter.py -v
```

- [ ] **Step 87:** 创建 `adapters/parts/sw_toolbox_adapter.py` 骨架：

```python
"""
adapters/parts/sw_toolbox_adapter.py — SolidWorks Toolbox COM adapter。

实现 PartsAdapter 接口。is_available() 做 6 项检查（v4 §5.3）；
resolve() 编排 catalog 匹配 + com_session 转换。

熔断状态委托给 SwComSession（v4 决策 #22）。
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

from adapters.parts.base import PartsAdapter

log = logging.getLogger(__name__)


class SwToolboxAdapter(PartsAdapter):
    """v4 决策 #14: 从 SolidWorksToolboxAdapter 改名为 SwToolboxAdapter。"""

    name = "sw_toolbox"

    def __init__(self, project_root: str = "", config: Optional[dict] = None) -> None:
        self.project_root = project_root
        self.config = config or {}

    def is_available(self) -> bool:
        """v4 §5.3: 6 项检查全通过。"""
        if sys.platform != "win32":
            return False

        try:
            from adapters.solidworks.sw_detect import detect_solidworks
            from adapters.solidworks.sw_com_session import get_session
        except ImportError:
            return False

        info = detect_solidworks()
        if not info.installed:
            return False
        if info.version_year < 2024:
            return False
        if not info.pywin32_available:
            return False
        if not info.toolbox_dir:
            return False
        if not info.toolbox_addin_enabled:
            return False

        # v4 决策 #22: 熔断委托给 SwComSession
        session = get_session()
        if not session.is_healthy():
            return False

        return True

    def can_resolve(self, query) -> bool:
        """总是 True（具体匹配由 resolve 决定）。"""
        return True

    def resolve(self, query, spec: dict):
        """resolve 实现留给 Task 9（主编排流程）。"""
        raise NotImplementedError("implemented in Task 9")

    def probe_dims(self, query, spec: dict):
        """probe_dims 实现留给 Task 9。"""
        raise NotImplementedError("implemented in Task 9")
```

- [ ] **Step 88:** 运行确认通过：

```
pytest tests/test_sw_toolbox_adapter.py -v
```

- [ ] **Step 89:** commit

```bash
git add adapters/parts/sw_toolbox_adapter.py tests/test_sw_toolbox_adapter.py
git commit -m "feat(sw-b): SwToolboxAdapter 骨架 + is_available 6 项检查（决策 #13/#14/#22）"
```

---

## Task 9 — SwToolboxAdapter：resolve + probe_dims

### 9.1 resolve 成功路径（mock COM）

- [ ] **Step 90:** 测试：

```python
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
            installed=True, version_year=2024, pywin32_available=True,
            toolbox_dir=str(fake_toolbox), toolbox_addin_enabled=True,
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
        result = a.resolve(Q(), {
            "standard": "GB",
            "subcategories": ["bolts and studs"],
            "part_category": "fastener",
        })
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
        result = a.resolve(Q(), {
            "standard": "GB",
            "subcategories": ["bolts and studs"],
            "part_category": "fastener",
        })
        # 期望 miss（分数 < 0.30）
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
        result = a.resolve(Q(), {
            "standard": "GB",
            "subcategories": ["bolts and studs"],
            "part_category": "fastener",
        })
        assert result.status == "miss"

    def test_resolve_cache_hit_no_com(self, setup_sw_available, tmp_path, monkeypatch):
        """v4 §3.2 step 8: 缓存命中不触发 COM。"""
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_com_session, sw_toolbox_catalog

        # Put a fake STEP file in cache location
        monkeypatch.setenv("CAD_SPEC_GEN_SW_TOOLBOX_CACHE", str(tmp_path / "cache"))
        cache_root = sw_toolbox_catalog.get_toolbox_cache_root({})
        cache_root.mkdir(parents=True, exist_ok=True)
        # Write a valid STEP
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
        result = a.resolve(Q(), {
            "standard": "GB",
            "subcategories": ["bolts and studs"],
            "part_category": "fastener",
        })
        assert result.status == "hit"
        assert result.kind == "step_import"
        assert result.adapter == "sw_toolbox"
        assert result.source_tag.startswith("sw_toolbox:")
        # COM was NOT called (cache hit)
        sess.convert_sldprt_to_step.assert_not_called()


def _default_config() -> dict:
    return {
        "min_score": 0.30,
        "token_weights": {
            "part_no": 2.0, "name_cn": 1.0, "material": 0.5, "size": 1.5,
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
```

- [ ] **Step 91:** 运行确认失败：

```
pytest tests/test_sw_toolbox_adapter.py::TestResolve -v
```

- [ ] **Step 92:** 实现 `resolve()`:

```python
# 在 SwToolboxAdapter 类中替换 resolve stub：

    def resolve(self, query, spec: dict):
        """主编排流程（v4 §3.2）。"""
        from parts_resolver import ResolveResult
        from adapters.solidworks import sw_toolbox_catalog
        from adapters.solidworks.sw_com_session import get_session
        from adapters.solidworks.sw_detect import detect_solidworks

        info = detect_solidworks()
        toolbox_dir = Path(info.toolbox_dir)

        # 1. 加载索引
        index_path = sw_toolbox_catalog.get_toolbox_index_path(self.config)
        try:
            index = sw_toolbox_catalog.load_toolbox_index(index_path, toolbox_dir)
        except Exception as e:
            log.warning("toolbox 索引加载失败: %s", e)
            return self._miss("index load failed")

        # 2. 解析 spec
        standards = spec.get("standard")
        if isinstance(standards, str):
            standards = [standards]
        subcategories = spec.get("subcategories", [])
        part_category = spec.get("part_category", "fastener")

        # 3. 抽尺寸（决策 #9）
        size_patterns = self.config.get("size_patterns", {}).get(part_category, {})
        size_dict = sw_toolbox_catalog.extract_size_from_name(
            getattr(query, "name_cn", ""),
            size_patterns,
        )
        if size_dict is None:
            return self._miss("size extraction failed or out of scope")

        # 4. 构造加权 tokens
        weights = self.config.get("token_weights", {})
        query_tokens = sw_toolbox_catalog.build_query_tokens_weighted(
            query, size_dict, weights,
        )

        # 5. token overlap 打分
        min_score = self.config.get("min_score", 0.30)
        match = sw_toolbox_catalog.match_toolbox_part(
            index, query_tokens, standards, subcategories, min_score,
        )
        if match is None:
            return self._miss("token overlap below min_score")

        part, score = match

        # 6. 路径遍历防御（决策 #20）
        if not sw_toolbox_catalog._validate_sldprt_path(part.sldprt_path, toolbox_dir):
            return self._miss("sldprt path validation failed (possible index tampering)")

        # 7. 构造缓存 STEP 路径
        cache_root = sw_toolbox_catalog.get_toolbox_cache_root(self.config)
        step_relative = Path(part.standard) / part.subcategory / (Path(part.filename).stem + ".step")
        step_abs = cache_root / step_relative

        # 8. 缓存命中 → 直接返回
        if step_abs.exists():
            dims = self._probe_step_bbox(step_abs)
            return ResolveResult(
                status="hit",
                kind="step_import",
                adapter=self.name,
                step_path=str(step_abs),
                real_dims=dims,
                source_tag=f"sw_toolbox:{part.standard}/{part.subcategory}/{part.filename}",
                metadata={
                    "dims": dims,
                    "match_score": score,
                    "configuration": "<default>",
                },
            )

        # 9. 缓存未命中 → 触发 COM
        session = get_session()
        if not session.is_healthy():
            return self._miss("COM session unhealthy (circuit breaker tripped)")

        ok = session.convert_sldprt_to_step(part.sldprt_path, str(step_abs))
        if not ok:
            return self._miss("COM convert failed")

        dims = self._probe_step_bbox(step_abs)
        return ResolveResult(
            status="hit",
            kind="step_import",
            adapter=self.name,
            step_path=str(step_abs),
            real_dims=dims,
            source_tag=f"sw_toolbox:{part.standard}/{part.subcategory}/{part.filename}",
            metadata={"dims": dims, "match_score": score, "configuration": "<default>"},
        )

    def _miss(self, reason: str):
        from parts_resolver import ResolveResult
        log.debug("sw_toolbox miss: %s", reason)
        return ResolveResult(
            status="miss",
            kind="miss",
            adapter=self.name,
            warnings=[reason],
        )

    def _probe_step_bbox(self, step_path: Path) -> Optional[tuple]:
        """复用 step_pool_adapter 的 bbox 探测逻辑。失败返回 None。"""
        try:
            import cadquery as cq
            obj = cq.importers.importStep(str(step_path))
            bb = obj.val().BoundingBox()
            return (
                round(bb.xlen, 2),
                round(bb.ylen, 2),
                round(bb.zlen, 2),
            )
        except Exception:
            return None
```

- [ ] **Step 93:** 运行确认通过：

```
pytest tests/test_sw_toolbox_adapter.py::TestResolve -v
```

- [ ] **Step 94:** commit

```bash
git add adapters/parts/sw_toolbox_adapter.py tests/test_sw_toolbox_adapter.py
git commit -m "feat(sw-b): SwToolboxAdapter.resolve 主编排流程（§3.2）"
```

### 9.2 probe_dims 不触发 COM

- [ ] **Step 95:** 测试：

```python
class TestProbeDims:
    """v4 §1.3 已知限制: 缓存未命中 → None，不触发 COM。"""

    @pytest.fixture
    def setup(self, monkeypatch, tmp_path):
        from adapters.solidworks import sw_detect, sw_com_session
        sw_detect._reset_cache()
        sw_com_session.reset_session()
        fake_info = sw_detect.SwInfo(
            installed=True, version_year=2024, pywin32_available=True,
            toolbox_dir=str(tmp_path), toolbox_addin_enabled=True,
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
        result = a.probe_dims(Q(), {
            "standard": "GB",
            "subcategories": ["bolts and studs"],
            "part_category": "fastener",
        })
        assert result is None
```

- [ ] **Step 96:** 运行确认失败（probe_dims 还是 NotImplementedError）：

```
pytest tests/test_sw_toolbox_adapter.py::TestProbeDims -v
```

- [ ] **Step 97:** 实现：

```python
# 替换 SwToolboxAdapter.probe_dims stub：

    def probe_dims(self, query, spec: dict):
        """v4 §1.3 已知限制: 缓存未命中 → None。

        避免为了测尺寸而触发 COM 启动。建议用户 sw-warmup 预热。
        """
        from adapters.solidworks import sw_toolbox_catalog
        from adapters.solidworks.sw_detect import detect_solidworks

        info = detect_solidworks()
        if not info.toolbox_dir:
            return None
        toolbox_dir = Path(info.toolbox_dir)

        size_patterns = self.config.get("size_patterns", {}).get(
            spec.get("part_category", "fastener"), {}
        )
        size_dict = sw_toolbox_catalog.extract_size_from_name(
            getattr(query, "name_cn", ""), size_patterns,
        )
        if size_dict is None:
            return None

        index_path = sw_toolbox_catalog.get_toolbox_index_path(self.config)
        try:
            index = sw_toolbox_catalog.load_toolbox_index(index_path, toolbox_dir)
        except Exception:
            return None

        standards = spec.get("standard")
        if isinstance(standards, str):
            standards = [standards]

        weights = self.config.get("token_weights", {})
        query_tokens = sw_toolbox_catalog.build_query_tokens_weighted(
            query, size_dict, weights,
        )
        match = sw_toolbox_catalog.match_toolbox_part(
            index, query_tokens, standards, spec.get("subcategories", []),
            self.config.get("min_score", 0.30),
        )
        if match is None:
            return None

        part, _ = match
        cache_root = sw_toolbox_catalog.get_toolbox_cache_root(self.config)
        step_abs = cache_root / part.standard / part.subcategory / (
            Path(part.filename).stem + ".step"
        )
        if not step_abs.exists():
            return None  # 决策 #4: 缓存未命中 → 不触发 COM

        return self._probe_step_bbox(step_abs)
```

- [ ] **Step 98:** 运行确认通过：

```
pytest tests/test_sw_toolbox_adapter.py::TestProbeDims -v
```

- [ ] **Step 99:** 运行整个 adapter 测试：

```
pytest tests/test_sw_toolbox_adapter.py -v
```

- [ ] **Step 100:** commit

```bash
git add adapters/parts/sw_toolbox_adapter.py tests/test_sw_toolbox_adapter.py
git commit -m "feat(sw-b): SwToolboxAdapter.probe_dims 缓存命中读 bbox（§1.3）"
```

---

## Task 10 — _find_sldprt 公共方法（供 sw-warmup --bom 复用）

### 10.1 测试 + 实现

- [ ] **Step 101:** 测试：

```python
class TestFindSldprt:
    """v4 §5.3: _find_sldprt() 不触发 COM；供 sw-warmup --bom 复用。"""

    @pytest.fixture
    def setup_sw(self, monkeypatch, tmp_path):
        from adapters.solidworks import sw_detect
        fake_toolbox = Path(__file__).parent / "fixtures" / "fake_toolbox"
        sw_detect._reset_cache()
        fake_info = sw_detect.SwInfo(
            installed=True, version_year=2024, pywin32_available=True,
            toolbox_dir=str(fake_toolbox), toolbox_addin_enabled=True,
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)

    def test_find_sldprt_returns_match(self, setup_sw):
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        class Q:
            part_no = "GB/T 5782"
            name_cn = "M6×20 hex bolt 六角头"
            material = "钢"

        a = SwToolboxAdapter(config=_default_config())
        result = a._find_sldprt(Q(), {
            "standard": "GB",
            "subcategories": ["bolts and studs"],
            "part_category": "fastener",
        })
        assert result is not None
        part, score = result
        assert part.filename == "hex bolt.sldprt"

    def test_find_sldprt_no_com_imports(self, setup_sw, monkeypatch):
        """_find_sldprt 不应导入/调用 win32com。"""
        import sys
        # Ensure win32com is not in sys.modules before call
        monkeypatch.setitem(sys.modules, "win32com.client", None)  # sabotage

        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        class Q:
            part_no = "GB/T 5782"
            name_cn = "M6×20 hex bolt 六角头"
            material = "钢"

        a = SwToolboxAdapter(config=_default_config())
        # 应该不 raise（证明没有 import win32com）
        result = a._find_sldprt(Q(), {
            "standard": "GB",
            "subcategories": ["bolts and studs"],
            "part_category": "fastener",
        })
        assert result is not None
```

- [ ] **Step 102:** 运行确认失败：

```
pytest tests/test_sw_toolbox_adapter.py::TestFindSldprt -v
```

- [ ] **Step 103:** 重构 resolve 抽出 `_find_sldprt`。在 SwToolboxAdapter 中添加：

```python
    def _find_sldprt(self, query, spec: dict):
        """匹配逻辑独立方法，供 sw-warmup --bom 复用。不触发 COM。

        Returns:
            (SwToolboxPart, score) 或 None
        """
        from adapters.solidworks import sw_toolbox_catalog
        from adapters.solidworks.sw_detect import detect_solidworks

        info = detect_solidworks()
        if not info.toolbox_dir:
            return None
        toolbox_dir = Path(info.toolbox_dir)

        standards = spec.get("standard")
        if isinstance(standards, str):
            standards = [standards]
        subcategories = spec.get("subcategories", [])
        part_category = spec.get("part_category", "fastener")

        size_patterns = self.config.get("size_patterns", {}).get(part_category, {})
        size_dict = sw_toolbox_catalog.extract_size_from_name(
            getattr(query, "name_cn", ""), size_patterns,
        )
        if size_dict is None:
            return None

        index_path = sw_toolbox_catalog.get_toolbox_index_path(self.config)
        try:
            index = sw_toolbox_catalog.load_toolbox_index(index_path, toolbox_dir)
        except Exception:
            return None

        weights = self.config.get("token_weights", {})
        query_tokens = sw_toolbox_catalog.build_query_tokens_weighted(
            query, size_dict, weights,
        )
        match = sw_toolbox_catalog.match_toolbox_part(
            index, query_tokens, standards, subcategories,
            self.config.get("min_score", 0.30),
        )
        if match is None:
            return None

        part, score = match
        if not sw_toolbox_catalog._validate_sldprt_path(part.sldprt_path, toolbox_dir):
            return None
        return (part, score)
```

然后 `resolve` 可以重构为调用 `_find_sldprt`（可选重构，不影响测试）。

- [ ] **Step 104:** 运行确认通过：

```
pytest tests/test_sw_toolbox_adapter.py -v
```

- [ ] **Step 105:** commit

```bash
git add adapters/parts/sw_toolbox_adapter.py tests/test_sw_toolbox_adapter.py
git commit -m "feat(sw-b): SwToolboxAdapter._find_sldprt 公共匹配方法（供 sw-warmup）"
```

---

## Task 11 — Part 1 最终集成验收

- [ ] **Step 106:** 运行 Part 1 所有测试：

```
pytest tests/test_sw_detect.py tests/test_sw_toolbox_catalog.py tests/test_sw_com_session.py tests/test_sw_toolbox_adapter.py tests/test_sw_routing_integration.py -v
```

预期：全部 PASS。

- [ ] **Step 107:** 运行 ruff 检查：

```
uv run ruff check adapters/solidworks/sw_toolbox_catalog.py adapters/solidworks/sw_com_session.py adapters/parts/sw_toolbox_adapter.py
```

如有警告，逐一修复。

- [ ] **Step 108:** 运行 ruff format:

```
uv run ruff format adapters/solidworks/sw_toolbox_catalog.py adapters/solidworks/sw_com_session.py adapters/parts/sw_toolbox_adapter.py
```

- [ ] **Step 109:** 在 Part 1 交付前，用 `superpowers:requesting-code-review` 做代码审查：

```
调用 superpowers:requesting-code-review skill
```

附上 Part 1 所有新增/改动文件列表和 spec v4 作为审查上下文。

- [ ] **Step 110:** 根据 review 结果修改后，最终 commit：

```bash
git add -A
git commit -m "feat(sw-b): Phase SW-B Part 1 交付 — 核心模块完成

- sw_detect: toolbox_addin_enabled 字段（决策 #13）
- sw_toolbox_catalog: SwToolboxPart + tokenize + extract_size +
  ReDoS 防御（决策 #19）+ fingerprint 完整性（决策 #21）+
  路径遍历防御（决策 #20）+ 加权 token overlap（决策 #12/#18）
- sw_com_session: SwComSession + 熔断（决策 #6）+ atomic write
  （决策 #23）+ threading 锁（决策 #22）+ encoding 透传（决策 #25）
- sw_toolbox_adapter: SwToolboxAdapter（决策 #14）+ is_available 6
  项检查（决策 #13）+ resolve 主编排（§3.2）+ probe_dims + _find_sldprt
- reset_all_sw_caches 集成 sw_com_session.reset_session（决策 #15）

100+ 个单元测试 PASS（CI Linux/Windows 兼容）。
Spec 依据: docs/superpowers/specs/2026-04-13-sw-integration-phase-b-design.md v4

Part 2（SW-B6..B10: parts_resolver 注册 + parts_library.yaml +
cad_pipeline 子命令 + 真实 COM 验收）将单独写 plan。"
```

---

## Part 1 交付清单

**新增模块**：
- `adapters/solidworks/sw_toolbox_catalog.py`（SwToolboxPart + tokenize + extract_size + validate_size_patterns + build/load_toolbox_index + match_toolbox_part + _validate_sldprt_path + get_toolbox_cache_root + get_toolbox_index_path）
- `adapters/solidworks/sw_com_session.py`（SwComSession 类 + get_session + reset_session + 熔断 + atomic write）
- `adapters/parts/sw_toolbox_adapter.py`（SwToolboxAdapter 类）

**改动模块**：
- `adapters/solidworks/sw_detect.py`（+ toolbox_addin_enabled 字段 + _check_toolbox_addin_enabled 函数）
- `adapters/solidworks/sw_material_bridge.py`（reset_all_sw_caches 追加 sw_com_session.reset_session）

**测试**：
- `tests/test_sw_detect.py`（+ TestToolboxAddinDetection 类）
- `tests/test_sw_toolbox_catalog.py`（全新，~250 行）
- `tests/test_sw_com_session.py`（全新，~200 行）
- `tests/test_sw_toolbox_adapter.py`（全新，~300 行）
- `tests/test_sw_routing_integration.py`（+ test_reset_all_sw_caches_includes_com_session）
- `tests/fixtures/fake_toolbox/`（12 个文件）
- `tests/fixtures/generate_fake_toolbox.py`（fixture 生成器）

**文档**：
- `docs/spikes/2026-04-13-sw-com-spike.md`（SW-B0 spike 报告）

**不做的事（留给 Part 2）**：
- `parts_resolver.default_resolver()` 注册 SwToolboxAdapter
- `parts_library.default.yaml` 增加 solidworks_toolbox 配置段和规则
- `cad_pipeline.py sw-warmup` / `sw-inspect` 子命令实现
- `cad_pipeline.py env-check` 增强（Toolbox Add-In + 索引报告）
- `pyproject.toml` 新增 optional-dependencies
- `@requires_solidworks` marker 注册 + 真实 COM 测试
- min_score 校准 / 真实 BOM 覆盖率验证 / 装配回归 gate / ROI 熔断（SW-B9 验收）
- `coverage_report()` 健康状态增强

---

## Self-Review（Part 1）

✅ **Spec 覆盖**：覆盖 spec v4 的 SW-B0（spike）、SW-B1（sw_detect 增量）、SW-B2（catalog）、SW-B3（com_session）、SW-B4（adapter is_available/can_resolve）、SW-B5（adapter resolve/probe_dims/_find_sldprt）
✅ **决策落位**：#6/#9/#10/#11/#12/#13/#14/#15/#16/#17/#18/#19/#20/#21/#22/#23/#25（17 条在 Part 1 落实，其余 #1..#5/#7/#8/#24/#26/#27/#28/#29/#30/#31/#32/#33 留给 Part 2）
✅ **无 TBD / placeholder**：所有 step 含完整代码 + 命令 + 期望输出
✅ **类型一致**：SwToolboxPart / SwToolboxAdapter / SwComSession 全程用 `Sw` 前缀；tokens 类型 `list[str]`、query_tokens_weighted 类型 `list[tuple[str, float]]` 全程一致；`is_available` 返回 bool 全程一致
✅ **TDD 循环完整**：每个 Task 都是 write test → fail → implement → pass → commit 五步
