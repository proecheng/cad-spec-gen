# B-16 Toolbox 多规格件 ShowConfiguration2 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 SW Toolbox 多规格 sldprt 导出 STEP 前切换到 BOM 指定的 configuration，使 M6×20 不再导出成 M3×10。

**Architecture:** yaml `config_name_resolver` 规则把 BOM material 字段标准化为 candidate config 名；worker 用 `IConfigurationManager.GetConfigurationNames()` 做两步匹配（精确 + 模糊）；匹配失败 exit 5，通过 `last_convert_diagnostics["stage"]` side channel 传递给调用方，不改公共 API，不计熔断器。Config-specific 缓存路径 `{stem}_{safe_config}.step` 防止不同规格互相覆盖。

**Tech Stack:** Python 3.10+、pywin32 COM（仅 worker 进程内）、pytest、PyYAML、Jinja2

---

## 文件清单

| 文件 | 改动类型 |
|---|---|
| `adapters/solidworks/sw_toolbox_catalog.py` | 修改：`SwToolboxPart` 加 `target_config` 字段 |
| `adapters/parts/sw_toolbox_adapter.py` | 修改：加解析函数 + `resolve()` 扩展 |
| `adapters/solidworks/sw_convert_worker.py` | 修改：`_resolve_config` + `ShowConfiguration2` + exit 5 |
| `adapters/solidworks/sw_com_session.py` | 修改：`_do_convert` 返 int + exit 5 side channel |
| `parts_library.default.yaml` | 修改：加 `config_name_resolver` 段 |
| `parts_library.yaml` | 修改：dev_sync.py 镜像（不手动编辑） |
| `parts_resolver.py` | 修改：`ResolveReportRow.config_match` 字段 |
| `sw_preflight/templates/sw_report.html.j2` | 修改：加 Config 匹配明细区块 |
| `tests/test_sw_toolbox_adapter.py` | 修改：加解析函数测试 + adapter exit 5 测试 |
| `tests/test_sw_convert_worker.py` | 修改：加 ConfigurationManager mock + 3 个 config 切换测试 |
| `tests/test_sw_com_session_subprocess.py` | 修改：加 exit 5 不计熔断 + target_config argv 测试 |

---

## Task 0: 建分支

**Files:**
- （无文件改动，仅 git 操作）

- [ ] **Step 1: 确认当前在 main**

```bash
git status
git log --oneline -3
```

Expected: 看到 `docs(b16): spec v0.3` 等最近提交，branch 为 main。

- [ ] **Step 2: 新建并切换到功能分支**

```bash
git checkout -b feat/b16-toolbox-multi-config
```

Expected: `Switched to a new branch 'feat/b16-toolbox-multi-config'`

---

## Task 1: `SwToolboxPart.target_config` 字段

背景：`SwToolboxPart` 是从 JSON 缓存反序列化的（`SwToolboxPart(**p)`），新增字段必须有默认值，否则旧缓存文件加载会 TypeError。

**Files:**
- Modify: `adapters/solidworks/sw_toolbox_catalog.py:73-91`

- [ ] **Step 1: 在 `SwToolboxPart` dataclass 末尾加字段**

打开 `adapters/solidworks/sw_toolbox_catalog.py`，找到第 73 行的 `@dataclass class SwToolboxPart`，在 `tokens` 字段后追加：

```python
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

    target_config: str | None = None
    """B-16: BOM 指定的 configuration 名（yaml 标准化后）；None = 使用默认 config"""
```

- [ ] **Step 2: 验证现有测试不受影响**

```bash
pytest tests/test_sw_toolbox_catalog.py -v --tb=short
```

Expected: 所有测试 PASS（新字段有默认值，不破坏现有 `SwToolboxPart(**p)` 反序列化）。

- [ ] **Step 3: Commit**

```bash
git add adapters/solidworks/sw_toolbox_catalog.py
git commit -m "feat(b16): SwToolboxPart 加 target_config 字段"
```

---

## Task 2: 纯解析函数 `extract_full_spec` + `_build_candidate_config`

这两个函数不依赖 COM，完全可测。TDD 先写测试。

**Files:**
- Modify: `tests/test_sw_toolbox_adapter.py` (加新测试类)
- Modify: `adapters/parts/sw_toolbox_adapter.py` (加模块级导入 + 两个函数)

- [ ] **Step 1: 在 `tests/test_sw_toolbox_adapter.py` 末尾追加测试类**

```python
class TestExtractFullSpec:
    def test_gb_t_fastener_with_length(self):
        from adapters.parts.sw_toolbox_adapter import extract_full_spec
        assert extract_full_spec("GB/T 70.1 M6×20") == ("GB/T 70.1", "M6×20")

    def test_gb_t_fastener_no_length(self):
        from adapters.parts.sw_toolbox_adapter import extract_full_spec
        assert extract_full_spec("GB/T 6170 M6") == ("GB/T 6170", "M6")

    def test_full_angle_slash(self):
        from adapters.parts.sw_toolbox_adapter import extract_full_spec
        assert extract_full_spec("GB／T 70.1 M6×20") == ("GB／T 70.1", "M6×20")

    def test_no_standard_prefix_returns_none(self):
        from adapters.parts.sw_toolbox_adapter import extract_full_spec
        assert extract_full_spec("6206") is None

    def test_empty_string_returns_none(self):
        from adapters.parts.sw_toolbox_adapter import extract_full_spec
        assert extract_full_spec("") is None

    def test_iso_standard(self):
        from adapters.parts.sw_toolbox_adapter import extract_full_spec
        assert extract_full_spec("ISO 4762 M6×20") == ("ISO 4762", "M6×20")


class TestBuildCandidateConfig:
    _CFG = {
        "standard_transforms": [
            {"from": "GB/T ", "to": "GB_T"},
            {"from": "GB／T ", "to": "GB_T"},
            {"from": "ISO ", "to": "ISO_"},
            {"from": " ", "to": ""},
        ],
        "size_transforms": [
            {"from": "×", "to": "x"},
            {"from": "×", "to": "x"},
            {"from": " ", "to": ""},
        ],
        "separator": "-",
    }

    def test_basic_fastener(self):
        from adapters.parts.sw_toolbox_adapter import _build_candidate_config
        assert _build_candidate_config("GB/T 70.1 M6×20", self._CFG) == "GB_T70.1-M6x20"

    def test_nut_no_length(self):
        from adapters.parts.sw_toolbox_adapter import _build_candidate_config
        assert _build_candidate_config("GB/T 6170 M6", self._CFG) == "GB_T6170-M6"

    def test_full_angle_slash(self):
        from adapters.parts.sw_toolbox_adapter import _build_candidate_config
        assert _build_candidate_config("GB／T 70.1 M6×20", self._CFG) == "GB_T70.1-M6x20"

    def test_no_standard_returns_none(self):
        from adapters.parts.sw_toolbox_adapter import _build_candidate_config
        assert _build_candidate_config("6206", self._CFG) is None

    def test_empty_resolver_cfg_returns_none(self):
        from adapters.parts.sw_toolbox_adapter import _build_candidate_config
        # resolver_cfg 为空时调用方不会调本函数；但若意外调用则返回 None（材料解析失败）
        assert _build_candidate_config("GB/T 70.1 M6×20", {}) is None
```

> 最后一个测试：`_build_candidate_config("GB/T 70.1 M6×20", {})` 会执行 `extract_full_spec` 成功，然后 `for rule in resolver_cfg["standard_transforms"]` 会 KeyError。为了让测试通过，实现里需要对空 cfg 做防御（`if not resolver_cfg.get("standard_transforms"): return None`），或者在调用方已有 `if resolver_cfg` 守卫后不传空 cfg。选择方案：在 `_build_candidate_config` 内部加守卫（更健壮）：
>
> ```python
> if not resolver_cfg.get("standard_transforms"):
>     return None
> ```

- [ ] **Step 2: 运行测试确认 FAIL**

```bash
pytest tests/test_sw_toolbox_adapter.py::TestExtractFullSpec tests/test_sw_toolbox_adapter.py::TestBuildCandidateConfig -v
```

Expected: FAIL，`ImportError: cannot import name 'extract_full_spec'`

- [ ] **Step 3: 在 `adapters/parts/sw_toolbox_adapter.py` 头部加 `import re`，然后加两个函数**

在文件顶部 `from __future__ import annotations` 之后、现有 import 块内追加：
```python
import re
```

然后在 `get_toolbox_addin_guid()` 函数定义**之前**（即在类定义之前的模块级区域）追加：

```python
_SPEC_RE = re.compile(
    r'^(?P<standard>(?:GB[/／]T|ISO|DIN|JIS)\s*[\d.]+(?:\s+Part\s+\d+)?)'
    r'\s+(?P<size>.+)$'
)
# 已知不覆盖：GB 93（弹垫，无 /T）、ANSI 等 → target_config=None → 使用默认 config


def extract_full_spec(material: str) -> tuple[str, str] | None:
    """从 BOM material 字段解析 (standard, size) 二元组，失败返回 None。"""
    m = _SPEC_RE.match(material.strip())
    return (m.group("standard"), m.group("size")) if m else None


def _build_candidate_config(material: str, resolver_cfg: dict) -> str | None:
    """用 yaml resolver_cfg 将 material 字段转为 SW config 候选名。

    示例: "GB/T 70.1 M6×20" → "GB_T70.1-M6x20"
    resolver_cfg 为空或缺 standard_transforms 时返回 None。
    """
    if not resolver_cfg.get("standard_transforms"):
        return None
    result = extract_full_spec(material)
    if result is None:
        return None
    standard, size = result
    for rule in resolver_cfg["standard_transforms"]:
        standard = standard.replace(rule["from"], rule["to"])
    for rule in resolver_cfg.get("size_transforms", []):
        size = size.replace(rule["from"], rule["to"])
    return f"{standard}{resolver_cfg['separator']}{size}"
```

- [ ] **Step 4: 运行测试确认 PASS**

```bash
pytest tests/test_sw_toolbox_adapter.py::TestExtractFullSpec tests/test_sw_toolbox_adapter.py::TestBuildCandidateConfig -v
```

Expected: 11 PASS

- [ ] **Step 5: 确认原有测试不受影响**

```bash
pytest tests/test_sw_toolbox_adapter.py -v --tb=short
```

Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add adapters/parts/sw_toolbox_adapter.py tests/test_sw_toolbox_adapter.py
git commit -m "feat(b16): extract_full_spec + _build_candidate_config 解析函数"
```

---

## Task 3: Worker `_resolve_config` + `ShowConfiguration2` + exit 5

**Files:**
- Modify: `tests/test_sw_convert_worker.py` (加新测试类)
- Modify: `adapters/solidworks/sw_convert_worker.py`

- [ ] **Step 1: 在 `tests/test_sw_convert_worker.py` 末尾追加测试类**

```python
class TestResolveConfig:
    """_resolve_config 两步匹配：精确 → 模糊。"""

    def test_exact_match_case_insensitive(self):
        from adapters.solidworks.sw_convert_worker import _resolve_config
        available = ["GB_T70.1-M6x10", "GB_T70.1-M6x20"]
        assert _resolve_config("GB_T70.1-M6x20", available) == "GB_T70.1-M6x20"

    def test_exact_match_case_insensitive_lower(self):
        from adapters.solidworks.sw_convert_worker import _resolve_config
        available = ["GB_T70.1-M6x20"]
        assert _resolve_config("gb_t70.1-m6x20", available) == "GB_T70.1-M6x20"

    def test_fuzzy_match_strips_dashes(self):
        from adapters.solidworks.sw_convert_worker import _resolve_config
        available = ["GB_T70.1-M6x20"]
        assert _resolve_config("GB-T70.1-M6x20", available) == "GB_T70.1-M6x20"

    def test_no_match_returns_none(self):
        from adapters.solidworks.sw_convert_worker import _resolve_config
        available = ["GB_T70.1-M6x10", "GB_T70.1-M6x20"]
        assert _resolve_config("GB_T70.1-M99x99", available) is None

    def test_empty_available_returns_none(self):
        from adapters.solidworks.sw_convert_worker import _resolve_config
        assert _resolve_config("GB_T70.1-M6x20", []) is None


class TestWorkerConfigSwitch:
    """_convert 带 target_config 参数时的 ShowConfiguration2 行为。"""

    def _patch_com(self, monkeypatch, *, dispatch_return=None, dispatch_raises=None):
        """复用 TestWorkerConvert._patch_com 的完全相同实现。"""
        fake_pythoncom = mock.MagicMock()
        fake_pythoncom.VT_BYREF = 0x4000
        fake_pythoncom.VT_I4 = 3
        fake_pythoncom.VT_DISPATCH = 9

        fake_win32com_client = mock.MagicMock()

        if dispatch_raises is not None:
            fake_win32com_client.DispatchEx.side_effect = dispatch_raises
        else:
            fake_app = dispatch_return or mock.MagicMock()
            fake_win32com_client.DispatchEx.return_value = fake_app

        def fake_variant(vartype, initial):
            v = mock.MagicMock()
            v.value = initial
            return v

        fake_win32com_client.VARIANT.side_effect = fake_variant

        monkeypatch.setitem(sys.modules, "pythoncom", fake_pythoncom)
        monkeypatch.setitem(sys.modules, "win32com.client", fake_win32com_client)
        return (
            fake_win32com_client.DispatchEx.return_value
            if dispatch_raises is None
            else None
        )

    def _make_model(self, fake_app, config_names):
        """构造带 ConfigurationManager 的 fake model。"""
        model = mock.MagicMock()
        fake_app.OpenDoc6.return_value = model
        model.Extension.SaveAs3.return_value = True

        fake_cfg_mgr = mock.MagicMock()
        fake_cfg_mgr.GetConfigurationNames.return_value = config_names
        model.ConfigurationManager = fake_cfg_mgr
        return model

    def test_exact_config_match_calls_showconfiguration(self, monkeypatch):
        from adapters.solidworks import sw_convert_worker

        fake_app = mock.MagicMock()
        self._patch_com(monkeypatch, dispatch_return=fake_app)
        model = self._make_model(fake_app, ["GB_T70.1-M6x10", "GB_T70.1-M6x20"])

        rc = sw_convert_worker._convert("in.sldprt", "out.tmp.step", "GB_T70.1-M6x20")
        assert rc == 0
        model.ShowConfiguration2.assert_called_once_with("GB_T70.1-M6x20")

    def test_fuzzy_config_match_calls_showconfiguration(self, monkeypatch):
        from adapters.solidworks import sw_convert_worker

        fake_app = mock.MagicMock()
        self._patch_com(monkeypatch, dispatch_return=fake_app)
        model = self._make_model(fake_app, ["GB_T70.1-M6x20"])

        rc = sw_convert_worker._convert("in.sldprt", "out.tmp.step", "GB-T70.1-M6x20")
        assert rc == 0
        model.ShowConfiguration2.assert_called_once()

    def test_no_config_match_returns_5(self, monkeypatch, capsys):
        from adapters.solidworks import sw_convert_worker

        fake_app = mock.MagicMock()
        self._patch_com(monkeypatch, dispatch_return=fake_app)
        self._make_model(fake_app, ["GB_T70.1-M6x10", "GB_T70.1-M6x20"])

        rc = sw_convert_worker._convert("in.sldprt", "out.tmp.step", "GB_T70.1-M99x99")
        assert rc == 5
        err = capsys.readouterr().err
        assert "config 未匹配" in err
        assert "GB_T70.1-M99x99" in err

    def test_no_target_config_skips_config_switch(self, monkeypatch):
        """target_config=None 时不调用 GetConfigurationNames 也不调用 ShowConfiguration2。"""
        from adapters.solidworks import sw_convert_worker

        fake_app = mock.MagicMock()
        self._patch_com(monkeypatch, dispatch_return=fake_app)
        model = mock.MagicMock()
        fake_app.OpenDoc6.return_value = model
        model.Extension.SaveAs3.return_value = True

        rc = sw_convert_worker._convert("in.sldprt", "out.tmp.step")
        assert rc == 0
        model.ShowConfiguration2.assert_not_called()

    def test_main_with_three_args(self, monkeypatch, capsys):
        """main([sldprt, tmp, config_name]) 正确解析 argv[2] 并传给 _convert。"""
        from adapters.solidworks import sw_convert_worker

        calls = []

        def fake_convert(sldprt, tmp, cfg=None):
            calls.append(cfg)
            return 0

        monkeypatch.setattr(sw_convert_worker, "_convert", fake_convert)
        rc = sw_convert_worker.main(["a.sldprt", "b.tmp.step", "GB_T70.1-M6x20"])
        assert rc == 0
        assert calls == ["GB_T70.1-M6x20"]

    def test_main_with_four_args_returns_64(self, capsys):
        from adapters.solidworks import sw_convert_worker

        rc = sw_convert_worker.main(["a", "b", "c", "d"])
        assert rc == 64
```

- [ ] **Step 2: 运行测试确认 FAIL**

```bash
pytest tests/test_sw_convert_worker.py::TestResolveConfig tests/test_sw_convert_worker.py::TestWorkerConfigSwitch -v
```

Expected: FAIL，`ImportError: cannot import name '_resolve_config'`

- [ ] **Step 3: 修改 `adapters/solidworks/sw_convert_worker.py`**

**3a) 在文件顶部 `import sys` 行之后加 `import re`：**

```python
import re
import sys
```

**3b) 在 `_convert` 函数定义**之前**追加 `_resolve_config` 函数：**

```python
def _resolve_config(candidate: str, available: list[str]) -> str | None:
    """两步匹配：精确（大小写不敏感）→ 模糊（去 -_/ 空格后比较）。"""
    lower_map = {n.lower(): n for n in available}
    if candidate.lower() in lower_map:
        return lower_map[candidate.lower()]

    def _norm(s: str) -> str:
        return re.sub(r'[-_\s]', '', s).lower()

    norm_map = {_norm(n): n for n in available}
    return norm_map.get(_norm(candidate))
```

**3c) 修改 `_convert` 函数签名（加 `target_config` 参数）：**

```python
def _convert(sldprt_path: str, tmp_out_path: str,
             target_config: str | None = None) -> int:
```

**3d) 在 `_convert` 内部，`model = app.OpenDoc6(...)` 赋值之后、`try:` 块（含 `SaveAs3`）内的 `disp_none_a = ...` 之前，插入 config 切换逻辑：**

找到 `try:` 块（约第 63 行），在 `disp_none_a = VARIANT(...)` 之前插入：

```python
            if target_config:
                config_mgr = model.ConfigurationManager
                available = list(config_mgr.GetConfigurationNames())
                matched = _resolve_config(target_config, available)
                if matched is None:
                    print(
                        f"[B-16] config 未匹配: {target_config!r}",
                        file=sys.stderr,
                    )
                    print(f"[B-16] 可用列表: {available}", file=sys.stderr)
                    return 5
                model.ShowConfiguration2(matched)
```

**3e) 修改 `main` 函数：**

```python
def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) not in (2, 3):
        print(
            "usage: python -m adapters.solidworks.sw_convert_worker "
            "<sldprt_path> <tmp_out_path> [config_name]",
            file=sys.stderr,
        )
        return 64
    target_config = argv[2] if len(argv) == 3 else None
    return _convert(argv[0], argv[1], target_config)
```

**3f) 更新文件头 docstring 中的退出码契约，在 `64 命令行参数错误` 之前加：**

```
    5  config 未找到（调用方 stage="config_not_found"，不计熔断器）
```

- [ ] **Step 4: 运行测试确认 PASS**

```bash
pytest tests/test_sw_convert_worker.py -v --tb=short
```

Expected: 所有测试 PASS（含原有测试 + 新增测试）

- [ ] **Step 5: Commit**

```bash
git add adapters/solidworks/sw_convert_worker.py tests/test_sw_convert_worker.py
git commit -m "feat(b16): worker _resolve_config + ShowConfiguration2 + exit 5"
```

---

## Task 4: `sw_com_session.py` exit 5 side channel

背景：`convert_sldprt_to_step` 保持 `-> bool`（不改公共 API，`sw_warmup.py` 两处调用无需修改）。`_do_convert` 改为 `-> int`。exit 5 通过 `_set_diag("config_not_found", 5, ...)` 传递，不计入熔断器。

**Files:**
- Modify: `tests/test_sw_com_session_subprocess.py` (加新测试类)
- Modify: `adapters/solidworks/sw_com_session.py`

- [ ] **Step 1: 在 `tests/test_sw_com_session_subprocess.py` 末尾追加测试类**

```python
class TestDoConvertExit5:
    """exit 5 (config_not_found) 不计熔断器，通过 diagnostics stage 传递。"""

    def test_exit5_returns_false_and_no_breaker_increment(self, tmp_path, monkeypatch):
        import subprocess
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()

        def fake_run_exit5(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 5, stdout="", stderr="config not found")

        monkeypatch.setattr(subprocess, "run", fake_run_exit5)

        ok = s.convert_sldprt_to_step(
            str(tmp_path / "part.sldprt"),
            str(tmp_path / "out.step"),
            "GB_T70.1-M6x20",
        )
        assert ok is False
        assert s._consecutive_failures == 0  # 不计熔断
        assert s.is_healthy() is True

    def test_exit5_sets_config_not_found_stage(self, tmp_path, monkeypatch):
        import subprocess
        from adapters.solidworks.sw_com_session import (
            SwComSession, reset_session, _STAGE_CONFIG_NOT_FOUND,
        )

        reset_session()
        s = SwComSession()

        def fake_run_exit5(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 5, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run_exit5)

        s.convert_sldprt_to_step(
            str(tmp_path / "part.sldprt"),
            str(tmp_path / "out.step"),
            "GB_T70.1-M6x20",
        )
        diag = s.last_convert_diagnostics
        assert diag is not None
        assert diag["stage"] == _STAGE_CONFIG_NOT_FOUND
        assert diag["exit_code"] == 5

    def test_exit5_three_times_does_not_trip_breaker(self, tmp_path, monkeypatch):
        import subprocess
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()

        def fake_run_exit5(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 5, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run_exit5)

        for _ in range(3):
            s.convert_sldprt_to_step(
                str(tmp_path / "part.sldprt"),
                str(tmp_path / "out.step"),
                "GB_T70.1-M6x20",
            )
        assert s.is_healthy() is True

    def test_target_config_appended_to_cmd(self, tmp_path, monkeypatch):
        import subprocess
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()
        captured_cmds = []

        def fake_run_success(cmd, **kwargs):
            captured_cmds.append(cmd)
            out_path = cmd[-2]  # tmp_path = argv[-2] when target_config present
            from pathlib import Path
            Path(out_path).parent.mkdir(parents=True, exist_ok=True)
            Path(out_path).write_bytes(b"ISO-10303-214\n" + b"X" * 2000)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run_success)

        s.convert_sldprt_to_step(
            str(tmp_path / "part.sldprt"),
            str(tmp_path / "out.step"),
            "GB_T70.1-M6x20",
        )
        cmd = captured_cmds[0]
        assert cmd[-1] == "GB_T70.1-M6x20"

    def test_nonzero_non5_rc_increments_breaker(self, tmp_path, monkeypatch):
        import subprocess
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()

        def fake_run_exit2(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 2, stdout="", stderr="OpenDoc6 fail")

        monkeypatch.setattr(subprocess, "run", fake_run_exit2)

        s.convert_sldprt_to_step(str(tmp_path / "part.sldprt"), str(tmp_path / "out.step"))
        assert s._consecutive_failures == 1
```

- [ ] **Step 2: 运行测试确认 FAIL**

```bash
pytest tests/test_sw_com_session_subprocess.py::TestDoConvertExit5 -v
```

Expected: FAIL，`ImportError: cannot import name '_STAGE_CONFIG_NOT_FOUND'`

- [ ] **Step 3: 修改 `adapters/solidworks/sw_com_session.py`**

**3a) 在 `STEP_MAGIC_PREFIX = b"ISO-10303"` 行之后加模块常量：**

```python
_STAGE_CONFIG_NOT_FOUND = "config_not_found"
```

**3b) 修改 `convert_sldprt_to_step` 方法**（替换整个方法体）：

```python
def convert_sldprt_to_step(
    self, sldprt_path, step_out, target_config: str | None = None
) -> bool:
    """转换单个 sldprt 为 STEP（Part 2c P0 subprocess 守护版）。

    保持 -> bool 兼容现有调用（sw_warmup.py:326/385 无需修改）。
    exit 5 (config_not_found) 通过 last_convert_diagnostics["stage"] 传递，不计熔断器。

    Returns:
        True: 成功
        False: 任何失败（不抛异常）。exit 5 时熔断计数不增加。
    """
    sldprt_path = str(os.fspath(sldprt_path))
    step_out = str(os.fspath(step_out))

    with self._lock:
        self._last_convert_diagnostics = None
        if self._unhealthy:
            log.info(
                "熔断器已开：跳过 convert（系统性故障，call reset_session() 清除）"
            )
            self._set_diag("circuit_breaker_open", None, "")
            return False

        try:
            rc = self._do_convert(sldprt_path, step_out, target_config)
        except Exception as e:
            log.warning("convert 未预期异常: %s", e)
            self._set_diag(
                "unexpected_exception", None, f"{type(e).__name__}: {e}"[:500]
            )
            rc = 4

        if rc == 0:
            self._consecutive_failures = 0
            return True
        if rc == 5:
            # config_not_found 不是 COM 错误，不计入熔断器
            # _do_convert 已调用 _set_diag(_STAGE_CONFIG_NOT_FOUND, 5, ...)
            return False
        # 真错误：计入熔断器
        self._consecutive_failures += 1
        if self._consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
            log.error(
                "COM 熔断触发（连续 %d 次失败）",
                self._consecutive_failures,
            )
            self._unhealthy = True
        return False
```

**3c) 修改 `_do_convert` 方法签名和实现**（替换整个 `_do_convert` 方法）：

```python
def _do_convert(self, sldprt_path: str, step_out: str,
                target_config: str | None = None) -> int:
    """启动 worker subprocess，成功则 validate + atomic rename。

    返回 int exit code：0=成功, 5=config未找到, 其他=真错误。
    （私有方法；公共 API convert_sldprt_to_step 保持 -> bool）
    """
    tmp_path = str(Path(step_out).with_suffix(".tmp.step"))
    Path(step_out).parent.mkdir(parents=True, exist_ok=True)

    cmd = [sys.executable, "-m", _WORKER_MODULE, sldprt_path, tmp_path]
    if target_config:
        cmd.append(target_config)

    try:
        proc = subprocess.run(
            cmd,
            timeout=SINGLE_CONVERT_TIMEOUT_SEC,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(_PROJECT_ROOT),
        )
    except subprocess.TimeoutExpired:
        log.warning(
            "convert subprocess 超时 %ds，已被 subprocess.run kill；sldprt=%s",
            SINGLE_CONVERT_TIMEOUT_SEC,
            sldprt_path,
        )
        self._set_diag("timeout", None, "")
        self._cleanup_tmp(tmp_path)
        return 1

    stderr = (proc.stderr or "")[:500]

    if proc.returncode == 5:
        self._set_diag(_STAGE_CONFIG_NOT_FOUND, 5, stderr)
        self._cleanup_tmp(tmp_path)
        return 5

    if proc.returncode != 0:
        log.warning(
            "convert subprocess rc=%d sldprt=%s stderr=%s",
            proc.returncode,
            sldprt_path,
            stderr[:300],
        )
        self._set_diag("subprocess_error", proc.returncode, stderr)
        self._cleanup_tmp(tmp_path)
        return proc.returncode

    if not self._validate_step_file(tmp_path):
        log.warning("convert tmp STEP 校验失败: %s", tmp_path)
        self._set_diag("validation_failure", proc.returncode, stderr)
        self._cleanup_tmp(tmp_path)
        return 3

    self._set_diag("success", proc.returncode, stderr)
    os.replace(tmp_path, step_out)
    return 0
```

- [ ] **Step 4: 运行测试确认 PASS**

```bash
pytest tests/test_sw_com_session_subprocess.py -v --tb=short
```

Expected: 所有测试 PASS（含原有测试）

- [ ] **Step 5: 跑全部 session 测试确认无回归**

```bash
pytest tests/test_sw_com_session.py tests/test_sw_com_session_subprocess.py tests/test_sw_com_session_real_subprocess.py -v --tb=short
```

Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add adapters/solidworks/sw_com_session.py tests/test_sw_com_session_subprocess.py
git commit -m "feat(b16): sw_com_session exit 5 side channel，不计熔断器"
```

---

## Task 5: `sw_toolbox_adapter.resolve()` config-aware 缓存路径 + stage 检查

**Files:**
- Modify: `tests/test_sw_toolbox_adapter.py` (加新测试类)
- Modify: `adapters/parts/sw_toolbox_adapter.py` (修改 `resolve()`)

- [ ] **Step 1: 在 `tests/test_sw_toolbox_adapter.py` 末尾追加测试类**

```python
class TestResolveConfigAware:
    """resolve() config-aware 缓存路径 + exit 5 回退路径测试。"""

    def _make_adapter_with_resolver_cfg(self):
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        config = {
            "config_name_resolver": {
                "standard_transforms": [
                    {"from": "GB/T ", "to": "GB_T"},
                    {"from": " ", "to": ""},
                ],
                "size_transforms": [
                    {"from": "×", "to": "x"},
                ],
                "separator": "-",
            },
            "min_score": 0.30,
        }
        return SwToolboxAdapter(config=config)

    def _make_full_mock_resolve_prereqs(self, monkeypatch, tmp_path):
        """mock 掉 resolve() 前 6 步（索引 + 匹配），返回 (fake_part, fake_session)。"""
        import unittest.mock as mock
        from adapters.solidworks import sw_toolbox_catalog

        fake_part = sw_toolbox_catalog.SwToolboxPart(
            standard="GB",
            subcategory="bolts and studs",
            sldprt_path=str(tmp_path / "GB_T70-1.SLDPRT"),
            filename="GB_T70-1.SLDPRT",
            tokens=["gb", "t70", "bolt"],
        )

        monkeypatch.setattr(
            sw_toolbox_catalog, "get_toolbox_index_path", lambda cfg: tmp_path / "idx.json"
        )
        monkeypatch.setattr(
            sw_toolbox_catalog, "load_toolbox_index", lambda *a, **kw: {}
        )
        monkeypatch.setattr(
            sw_toolbox_catalog, "extract_size_from_name", lambda *a, **kw: {"size": "M6"}
        )
        monkeypatch.setattr(
            sw_toolbox_catalog, "build_query_tokens_weighted", lambda *a, **kw: ["m6"]
        )
        monkeypatch.setattr(
            sw_toolbox_catalog, "match_toolbox_part", lambda *a, **kw: (fake_part, 0.8)
        )
        monkeypatch.setattr(
            sw_toolbox_catalog, "_validate_sldprt_path", lambda *a, **kw: True
        )
        monkeypatch.setattr(
            sw_toolbox_catalog, "get_toolbox_cache_root", lambda cfg: tmp_path / "cache"
        )

        from adapters.solidworks import sw_detect
        sw_detect._reset_cache()
        monkeypatch.setattr(
            sw_detect,
            "detect_solidworks",
            lambda: sw_detect.SwInfo(installed=True, toolbox_dir=str(tmp_path)),
        )

        fake_session = mock.MagicMock()
        from adapters.solidworks import sw_com_session
        monkeypatch.setattr(sw_com_session, "get_session", lambda: fake_session)

        return fake_part, fake_session

    def test_config_aware_cache_path_contains_config_suffix(
        self, monkeypatch, tmp_path
    ):
        """当 material 解析成功时，缓存路径应含 config 后缀。"""
        import unittest.mock as mock
        from parts_resolver import PartQuery

        adapter = self._make_adapter_with_resolver_cfg()
        fake_part, fake_session = self._make_full_mock_resolve_prereqs(
            monkeypatch, tmp_path
        )

        # 让 convert_sldprt_to_step 成功并记录调用的 step_out 路径
        captured = []

        def fake_convert(sldprt, step_out, config=None):
            captured.append((step_out, config))
            # 假装写出 STEP 文件以触发后续 _probe_step_bbox 路径
            from pathlib import Path
            Path(step_out).parent.mkdir(parents=True, exist_ok=True)
            Path(step_out).write_bytes(b"ISO-10303-214\n" + b"X" * 2000)
            return True

        fake_session.convert_sldprt_to_step.side_effect = fake_convert
        fake_session.is_healthy.return_value = True

        query = PartQuery(
            part_no="001",
            name_cn="内六角螺栓",
            material="GB/T 70.1 M6×20",
            category="fastener",
            make_buy="标准",
        )
        adapter.resolve(query, {"standard": "GB", "subcategories": [], "part_category": "fastener"})

        assert len(captured) == 1
        step_out_used, config_used = captured[0]
        assert "GB_T70.1-M6x20" in step_out_used
        assert config_used == "GB_T70.1-M6x20"

    def test_exit5_stage_returns_miss_with_config_match_fallback(
        self, monkeypatch, tmp_path
    ):
        """exit 5 → stage=config_not_found → resolve() 返回 miss，config_match=fallback。"""
        import unittest.mock as mock
        from parts_resolver import PartQuery

        adapter = self._make_adapter_with_resolver_cfg()
        fake_part, fake_session = self._make_full_mock_resolve_prereqs(
            monkeypatch, tmp_path
        )

        fake_session.convert_sldprt_to_step.return_value = False
        fake_session.is_healthy.return_value = True
        fake_session.last_convert_diagnostics = {"stage": "config_not_found", "exit_code": 5}

        query = PartQuery(
            part_no="001",
            name_cn="内六角螺栓",
            material="GB/T 70.1 M6×99",
            category="fastener",
            make_buy="标准",
        )
        result = adapter.resolve(
            query,
            {"standard": "GB", "subcategories": [], "part_category": "fastener"},
        )
        assert result.status == "miss"
        assert result.metadata.get("config_match") == "fallback"

    def test_no_resolver_cfg_uses_default_cache_path(self, monkeypatch, tmp_path):
        """config_name_resolver 段不存在时，缓存路径不含 config 后缀（向后兼容）。"""
        import unittest.mock as mock
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from parts_resolver import PartQuery

        adapter = SwToolboxAdapter(config={"min_score": 0.30})  # 无 config_name_resolver
        fake_part, fake_session = self._make_full_mock_resolve_prereqs(
            monkeypatch, tmp_path
        )

        captured = []

        def fake_convert(sldprt, step_out, config=None):
            captured.append((step_out, config))
            from pathlib import Path
            Path(step_out).parent.mkdir(parents=True, exist_ok=True)
            Path(step_out).write_bytes(b"ISO-10303-214\n" + b"X" * 2000)
            return True

        fake_session.convert_sldprt_to_step.side_effect = fake_convert
        fake_session.is_healthy.return_value = True

        query = PartQuery(
            part_no="001",
            name_cn="内六角螺栓",
            material="GB/T 70.1 M6×20",
            category="fastener",
            make_buy="标准",
        )
        adapter.resolve(query, {"standard": "GB", "subcategories": [], "part_category": "fastener"})

        assert len(captured) == 1
        step_out_used, config_used = captured[0]
        # 无 resolver_cfg → target_config=None → 无后缀
        assert "GB_T70.1" not in step_out_used
        assert config_used is None
```

- [ ] **Step 2: 运行测试确认 FAIL**

```bash
pytest tests/test_sw_toolbox_adapter.py::TestResolveConfigAware -v
```

Expected: FAIL（`resolve()` 尚未实现 config-aware 逻辑）

- [ ] **Step 3: 修改 `adapters/parts/sw_toolbox_adapter.py` 的 `resolve()` 方法**

找到 `# 6. 路径遍历防御` 之后，`# 7. 构造缓存 STEP 路径` 之前，**替换**步骤 7-9（约 line 187-231）为：

```python
        # 7. 构造缓存 STEP 路径（B-16：含 config 后缀）
        cache_root = sw_toolbox_catalog.get_toolbox_cache_root(self.config)
        resolver_cfg = self.config.get("config_name_resolver", {})
        material = getattr(query, "material", "") or ""
        target_config = _build_candidate_config(material, resolver_cfg) if resolver_cfg else None
        part.target_config = target_config

        safe_config = re.sub(r'[^\w.\-]', '_', target_config) if target_config else ""
        cache_stem = (
            f"{Path(part.filename).stem}_{safe_config}"
            if safe_config
            else Path(part.filename).stem
        )
        step_abs = cache_root / part.standard / part.subcategory / (cache_stem + ".step")

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
                    "configuration": target_config or "<default>",
                    "config_match": "matched" if target_config else "n/a",
                },
            )

        # 9. 缓存未命中 → 触发 COM
        session = get_session()
        if not session.is_healthy():
            return self._miss("COM session unhealthy (circuit breaker tripped)")

        ok = session.convert_sldprt_to_step(part.sldprt_path, str(step_abs), target_config)
        if not ok:
            stage = (session.last_convert_diagnostics or {}).get("stage", "")
            if stage == "config_not_found":
                log.warning(
                    "Toolbox config 未匹配 %s → 回退 bd_warehouse", target_config
                )
                return ResolveResult(
                    status="miss",
                    kind="miss",
                    adapter=self.name,
                    metadata={"config_match": "fallback"},
                    warnings=[f"config not found: {target_config}"],
                )
            return self._miss("COM convert failed")

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
                "configuration": target_config or "<default>",
                "config_match": "matched" if target_config else "n/a",
            },
        )
```

> 注意：`resolve()` 里已经 `from parts_resolver import ResolveResult`（在方法体开头的 lazy import 块），确认存在即可，无需重复加。

- [ ] **Step 4: 运行测试确认 PASS**

```bash
pytest tests/test_sw_toolbox_adapter.py -v --tb=short
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add adapters/parts/sw_toolbox_adapter.py tests/test_sw_toolbox_adapter.py
git commit -m "feat(b16): resolve() config-aware 缓存路径 + exit 5 stage 检查"
```

---

## Task 6: `parts_library.default.yaml` 加 `config_name_resolver` 段

**Files:**
- Modify: `parts_library.default.yaml:84-86` (在 `com:` 段之后追加)
- Modify: `parts_library.yaml` (通过 dev_sync.py 镜像，不手动编辑)

- [ ] **Step 1: 在 `parts_library.default.yaml` 的 `com:` 段之后追加**

找到约第 84 行的 `com:` 段末（`circuit_breaker_threshold: 3`），在其后追加：

```yaml
  # B-16: BOM material 字段 → SW config 名标准化规则
  # 仅覆盖 GB/T、ISO、DIN、JIS 格式；GB 93（无 /T）等老标准 → 默认 config
  config_name_resolver:
    standard_transforms:
      - {from: "GB/T ", to: "GB_T"}
      - {from: "GB／T ", to: "GB_T"}   # 全角斜杠兼容
      - {from: "ISO ", to: "ISO_"}
      - {from: " ", to: ""}            # 去除残余空格
    size_transforms:
      - {from: "×", to: "x"}
      - {from: "×", to: "x"}          # 全角乘号
      - {from: " ", to: ""}
    separator: "-"
```

- [ ] **Step 2: 运行 dev_sync.py 同步到 parts_library.yaml**

```bash
python scripts/dev_sync.py
```

Expected: exit 0 或 exit 1（有文件被同步，非错误）。

- [ ] **Step 3: 验证 parts_library.yaml 已同步**

```bash
python -c "
import yaml
with open('parts_library.yaml') as f:
    d = yaml.safe_load(f)
cfg = d['solidworks_toolbox']['config_name_resolver']
print('separator:', cfg['separator'])
print('first_std_transform:', cfg['standard_transforms'][0])
"
```

Expected:
```
separator: -
first_std_transform: {'from': 'GB/T ', 'to': 'GB_T'}
```

- [ ] **Step 4: 运行受影响测试确认无回归**

```bash
pytest tests/test_parts_resolver.py tests/test_parts_adapters.py -v --tb=short
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add parts_library.default.yaml parts_library.yaml
git commit -m "feat(b16): parts_library 加 config_name_resolver yaml 段"
```

---

## Task 7: `parts_resolver.py` `ResolveReportRow.config_match`

**Files:**
- Modify: `parts_resolver.py:125-160` (dataclass + to_dict)
- Modify: `parts_resolver.py:450` (resolve_report 构造行)

- [ ] **Step 1: 修改 `ResolveReportRow` dataclass（约 line 125）**

```python
@dataclass
class ResolveReportRow:
    bom_id: str
    name_cn: str
    matched_adapter: str
    attempted_adapters: list[str]
    status: str  # "hit" | "fallback" | "miss"
    config_match: str = "n/a"  # B-16: "matched" | "fallback" | "n/a"
```

- [ ] **Step 2: 修改 `to_dict()` 中 rows 列表的字典构造（约 line 150-158）**

在 `"status": r.status,` 之后加一行：

```python
                    "config_match": r.config_match,
```

完整 rows 列表部分应为：
```python
"rows": [
    {
        "bom_id": r.bom_id,
        "name_cn": r.name_cn,
        "matched_adapter": r.matched_adapter,
        "attempted_adapters": r.attempted_adapters,
        "status": r.status,
        "config_match": r.config_match,
    }
    for r in self.rows
],
```

- [ ] **Step 3: 修改 `resolve_report()` 中构造 `ResolveReportRow` 的位置（约 line 450）**

在 `attempted_adapters=row_trace,` 之后，`status=status,` 之后加：

```python
            report.rows.append(ResolveReportRow(
                bom_id=part_no,
                name_cn=name_cn,
                matched_adapter=matched,
                attempted_adapters=row_trace,
                status=status,
                config_match=(result.metadata or {}).get("config_match", "n/a"),
            ))
```

- [ ] **Step 4: 运行 parts_resolver 测试确认无回归**

```bash
pytest tests/test_parts_resolver.py tests/test_parts_adapters.py -v --tb=short
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add parts_resolver.py
git commit -m "feat(b16): ResolveReportRow.config_match 字段 + to_dict + resolve_report"
```

---

## Task 8: HTML 模板加 Config 匹配明细区块

**Files:**
- Modify: `sw_preflight/templates/sw_report.html.j2`

- [ ] **Step 1: 在 `sw_preflight/templates/sw_report.html.j2` 的 `{% if resolve_report %}` 区块内追加**

找到约第 66 行的 `</div>` `{% endif %}`（`resolve_report` 区块结尾），在 `{% endif %}` **之前**插入：

```jinja2
  {% if resolve_report.rows %}
  <div class="section">
    <div class="section-head">Config 匹配明细 ({{ resolve_report.rows|length }} 行)</div>
    <table style="width:100%;border-collapse:collapse;font-size:.9em;">
      <tr style="text-align:left;background:#f4f4f4;">
        <th style="padding:.3em .6em;">零件名</th>
        <th>Adapter</th>
        <th>Config 匹配</th>
        <th>状态</th>
      </tr>
      {% for row in resolve_report.rows %}
      <tr style="border-top:1px solid #eee;">
        <td style="padding:.3em .6em;">{{ row.name_cn }}</td>
        <td>{{ row.matched_adapter }}</td>
        <td class="{{ 'ok' if row.config_match=='matched' else 'warn' if row.config_match=='fallback' else '' }}">
          {{ row.config_match }}</td>
        <td>{{ row.status }}</td>
      </tr>
      {% endfor %}
    </table>
  </div>
  {% endif %}
```

- [ ] **Step 2: 用 Python 快速渲染验证模板语法无错**

```bash
python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('sw_preflight/templates'))
tpl = env.get_template('sw_report.html.j2')
html = tpl.render(
    sw_status={'edition':'test','toolbox':True,'pywin32':True,'toolbox_advisory':False},
    ran_at='2026-04-24T00:00:00Z',
    elapsed='1s',
    standard_rows=[],
    vendor_rows=[],
    custom_rows=[],
    fix_records=[],
    resolve_report={
        'adapter_hits': {'sw_toolbox': {'count': 2, 'unavailable_reason': None}},
        'total_rows': 2,
        'run_id': 'test',
        'rows': [
            {'name_cn': '内六角螺栓', 'matched_adapter': 'sw_toolbox',
             'config_match': 'matched', 'status': 'hit'},
            {'name_cn': '螺母', 'matched_adapter': 'bd_warehouse',
             'config_match': 'fallback', 'status': 'hit'},
        ],
    },
)
assert 'Config 匹配明细' in html
assert 'matched' in html
print('OK')
"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add sw_preflight/templates/sw_report.html.j2
git commit -m "feat(b16): sw_report.html.j2 加 Config 匹配明细区块"
```

---

## CHECKPOINT: 全套测试 + PR

- [ ] **Step 1: 运行全部测试**

```bash
pytest tests/ -v --tb=short
```

Expected: 全部 PASS（原有 1160+ 测试 + 新增测试，无 FAIL）

- [ ] **Step 2: 检查 sw-warmup 相关测试无回归**

```bash
pytest tests/test_sw_warmup_orchestration.py -v --tb=short
```

Expected: 全部 PASS（`sw_warmup.py` 未修改，熔断器 API `-> bool` 不变）

- [ ] **Step 3: Push 分支 + 开 PR**

```bash
git push -u origin feat/b16-toolbox-multi-config
gh pr create \
  --title "feat(b16): Toolbox 多规格件 ShowConfiguration2 — BOM 指定 config 精确导出" \
  --body "$(cat <<'EOF'
## Summary
- `sw_convert_worker`: 新增 `_resolve_config` + `ShowConfiguration2` + exit 5（config 未找到）
- `sw_com_session`: exit 5 不计熔断器，通过 `last_convert_diagnostics["stage"]` 传递信号
- `sw_toolbox_adapter.resolve()`: config-aware 缓存路径 + exit 5 stage 检查 → 回退 bd_warehouse
- `parts_library`: 新增 `config_name_resolver` yaml 段，标准化 BOM material 字段
- `parts_resolver`: `ResolveReportRow.config_match` 字段
- `sw_report.html.j2`: Config 匹配明细区块

## Test plan
- [ ] CI Ubuntu + Windows × Python 3.10/3.11/3.12 全绿
- [ ] `pytest tests/test_sw_convert_worker.py::TestResolveConfig` — `_resolve_config` 5 用例
- [ ] `pytest tests/test_sw_convert_worker.py::TestWorkerConfigSwitch` — 4 个 worker config 切换用例
- [ ] `pytest tests/test_sw_com_session_subprocess.py::TestDoConvertExit5` — 5 个 exit 5 用例
- [ ] `pytest tests/test_sw_toolbox_adapter.py::TestResolveConfigAware` — 3 个 adapter 集成用例
- [ ] 手工验收（SW 2024 开启）: `python cad_pipeline.py full --bom "D:\Work\cad-tests\04-末端执行机构设计.md"` → sw_report.html Config 列有 "matched"

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 4: 等待 CI 全绿后 merge，发布 v2.17.0**

CI 全绿后：
```bash
gh pr merge --squash
git checkout main && git pull
git tag v2.17.0 && git push origin v2.17.0
gh release create v2.17.0 --title "v2.17.0 — B-16 Toolbox 多规格件 ShowConfiguration2" \
  --notes "BOM 指定规格（如 M6×20）现在正确导出对应 configuration 的 STEP，而非默认最小规格。"
```
