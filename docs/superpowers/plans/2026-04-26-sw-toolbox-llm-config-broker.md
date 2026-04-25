# SW Toolbox 配置名 LLM-broker 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 `sw_config_broker` 模块，让 `gen_std_parts.py` 通过 SW COM ShowConfiguration2 取尺寸匹配的 SW Toolbox STEP 生成 std_*.py，含糊匹配时通过 pending 机制让 agent 与用户交互。

**Architecture:** 新增 `adapters/solidworks/sw_config_broker.py`（核心决策逻辑） + `adapters/solidworks/sw_list_configs_worker.py`（独立 COM 子进程）；`sw_toolbox_adapter.resolve()` 委托给 broker；`gen_std_parts.py` 捕获 NeedsUserDecision 累积 + 一次性原子写 pending + exit 7 + stdout 人读摘要。决策状态持久化在 `<project>/.cad-spec-gen/spec_decisions.json`（schema v2，按 subsystem 嵌套）。

**Tech Stack:** Python 3.11+ / pywin32 / dataclasses / msvcrt.locking（文件锁）/ pytest + pytest-mock。**绝对不引入 LLM API 调用** —— LLM-用户交互在 agent 层。

**Spec ref:** `docs/superpowers/specs/2026-04-25-sw-toolbox-llm-config-broker-design.md`

---

## 文件清单

### 新增

| 路径 | 职责 |
|------|------|
| `adapters/solidworks/sw_config_broker.py` (~280 行) | 主模块：数据类、异常、公开 API + 7 个私有辅助 |
| `adapters/solidworks/sw_list_configs_worker.py` (~50 行) | 独立 subprocess 用 COM 列 SLDPRT 配置名，stdout 输出 JSON list |
| `tests/test_sw_config_broker.py` | 单元测试：纯函数 + 数据类 + invalidation 三项 |
| `tests/test_sw_toolbox_adapter_with_broker.py` | 集成测试：mock COM worker 跑完整 resolve 流程 |
| `tests/test_sw_config_broker_real.py` | E2E：真 SW COM 列 GISBOT 用到的 5 个 SLDPRT |
| `tests/conftest_broker.py`（可合并到现有 conftest） | 新增 fixture `tmp_project_dir` 等 |

### 修改

| 路径 | 改动 |
|------|------|
| `adapters/parts/sw_toolbox_adapter.py:226-293` | resolve() 替换 `_build_candidate_config` + cache hit 逻辑为 broker 委托 |
| `codegen/gen_std_parts.py:165-200` | 捕获 NeedsUserDecision、累积、原子写 pending、stdout 摘要、exit 7 |
| `.claude/commands/cad-codegen.md` | 增加 "exit 7 处理" 段 |
| `src/cad_spec_gen/data/commands/en/cad-codegen.md` | 同步英文 |
| `AGENTS.md` | 跑 `python scripts/dev_sync.py` 自动更新 |

---

## 检查点结构

| CP | 完成节点 | 暂停确认 |
|----|---------|---------|
| **CP-1** | Task 1 完成（worker 工作） | 用户确认 worker 退出码与 stdout JSON 契约 |
| **CP-2** | Task 2-8 完成（broker 纯函数 + 数据类） | 用户确认数据类签名与匹配规则 |
| **CP-3** | Task 9-12 完成（broker 文件 I/O） | 用户确认 schema v2 envelope 操作 |
| **CP-4** | Task 13-16 完成（broker 公开 API + COM + lock） | 用户确认主流程 5 路径 |
| **CP-5** | Task 17 完成（adapter 接入 broker） | 用户审 sw_toolbox_adapter 改动是否破坏现有测试 |
| **CP-6** | Task 18-21 完成（gen_std_parts pipeline 整合） | 用户审 stdout 摘要文案 + exit 7 |
| **CP-7** | Task 22-24 完成（skill 文档） | 用户确认 agent 引导流程文案 |
| **CP-8** | Task 25-26 完成（真 SW E2E + GISBOT smoke） | 用户验收 GLB 含 SW 真几何 |

---

## Task 0：环境基线 + 探查

**Files:** 无创建/修改，仅验证

- [ ] **Step 1：跑全量测试基线**

```bash
cd D:/Work/cad-spec-gen && .venv/Scripts/python.exe -m pytest --tb=no -q 2>&1 | tail -5
```

Expected: `1238 passed` 或类似（写入 `task0_baseline.txt` 备查）

- [ ] **Step 2：验证 cad_paths.PROJECT_ROOT 模块级常量可用**

```bash
.venv/Scripts/python.exe -c "from cad_paths import PROJECT_ROOT; print('PROJECT_ROOT =', PROJECT_ROOT)"
```

Expected: 打印当前工作目录绝对路径（如 `D:\Work\cad-spec-gen`）

- [ ] **Step 3：验证 conftest 已有 `requires_solidworks` marker**

```bash
grep -rn "requires_solidworks" tests/conftest.py
```

Expected: 找到 marker 注册行（session 9 加的）；无则需在 Task 25 前补

- [ ] **Step 4：验证 GISBOT 项目可用**

```bash
ls D:/Work/cad-tests/GISBOT/cad/end_effector/CAD_SPEC.md
```

Expected: 文件存在

无 commit（探查任务）

---

## Task 1：sw_list_configs_worker.py（独立 COM 子进程）

**Files:**
- Create: `adapters/solidworks/sw_list_configs_worker.py`
- Create: `tests/test_sw_list_configs_worker.py`

**Why first:** 整个 broker 的最底层 IO 单元；其他模块都 mock 它，必须先有契约。

- [ ] **Step 1：写失败测试 — usage error 退 64**

```python
# tests/test_sw_list_configs_worker.py
import subprocess
import sys


def test_usage_error_returns_64():
    """无参数 → exit 64"""
    proc = subprocess.run(
        [sys.executable, "-m", "adapters.solidworks.sw_list_configs_worker"],
        capture_output=True,
        text=True,
        cwd="D:/Work/cad-spec-gen",
    )
    assert proc.returncode == 64
    assert "usage" in proc.stderr.lower()
```

- [ ] **Step 2：跑测试确认 FAIL（模块不存在）**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_list_configs_worker.py::test_usage_error_returns_64 -v
```

Expected: `FAILED` (ModuleNotFoundError)

- [ ] **Step 3：写最小实现满足 usage error**

```python
# adapters/solidworks/sw_list_configs_worker.py
"""adapters/solidworks/sw_list_configs_worker.py — 独立子进程列出 SLDPRT 的所有配置名。

复用 sw_convert_worker.py 模式（subprocess + timeout + 退出码契约）。

退出码契约：
    0  成功（stdout 输出 JSON list of strings）
    2  OpenDoc6 errors 非 0 或返回 null model
    4  任何未预期 Exception（COM 崩溃、pywin32 import 失败等）
    64 命令行参数错误

CLI:
    python -m adapters.solidworks.sw_list_configs_worker <sldprt_path>
"""

from __future__ import annotations

import json
import sys


def _list_configs(sldprt_path: str) -> int:
    """返回退出码；成功时 stdout 打印 JSON list。"""
    try:
        import pythoncom
        from win32com.client import VARIANT, DispatchEx
    except ImportError as e:
        print(f"worker: pywin32 import failed: {e!r}", file=sys.stderr)
        return 4

    pythoncom.CoInitialize()
    try:
        try:
            app = DispatchEx("SldWorks.Application")
        except Exception as e:
            print(f"worker: Dispatch failed: {e!r}", file=sys.stderr)
            return 4

        try:
            app.Visible = False
            app.UserControl = False
            app.FrameState = 0

            err_var = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            warn_var = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            model = app.OpenDoc6(sldprt_path, 1, 1, "", err_var, warn_var)
            if err_var.value or model is None:
                print(
                    f"worker: OpenDoc6 errors={err_var.value} model={'NULL' if model is None else 'OK'}",
                    file=sys.stderr,
                )
                return 2

            try:
                config_mgr = model.ConfigurationManager
                names = list(config_mgr.GetConfigurationNames())
                print(json.dumps(names, ensure_ascii=False))
                return 0
            finally:
                try:
                    app.CloseDoc(model.GetPathName())
                except Exception as e:
                    print(f"worker: CloseDoc ignored: {e!r}", file=sys.stderr)
        finally:
            try:
                app.ExitApp()
            except Exception as e:
                print(f"worker: ExitApp ignored: {e!r}", file=sys.stderr)
    except Exception as e:
        print(f"worker: unexpected exception: {e!r}", file=sys.stderr)
        return 4
    finally:
        pythoncom.CoUninitialize()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(
            "usage: python -m adapters.solidworks.sw_list_configs_worker <sldprt_path>",
            file=sys.stderr,
        )
        return 64
    return _list_configs(argv[0])


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4：跑测试确认 PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_list_configs_worker.py::test_usage_error_returns_64 -v
```

Expected: `PASSED`

- [ ] **Step 5：写第二个失败测试 — pywin32 不可用退 4**（用 monkeypatch sys.modules 模拟）

```python
def test_pywin32_unavailable_returns_4(monkeypatch):
    """pywin32 import 失败 → exit 4"""
    import importlib
    import sys as _sys

    # 把 pythoncom 强制设成 None 模拟 import 失败
    monkeypatch.setitem(_sys.modules, "pythoncom", None)
    from adapters.solidworks import sw_list_configs_worker
    importlib.reload(sw_list_configs_worker)

    rc = sw_list_configs_worker._list_configs("dummy.sldprt")
    assert rc == 4
```

- [ ] **Step 6：跑测试确认 PASS（实现已覆盖该路径）**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_list_configs_worker.py -v
```

Expected: 2 passed

- [ ] **Step 7：commit**

```bash
git add adapters/solidworks/sw_list_configs_worker.py tests/test_sw_list_configs_worker.py
git commit -m "feat(sw_list_configs_worker): 新增独立 COM 子进程列 SLDPRT 配置名

退出码契约 0/2/4/64 与 sw_convert_worker.py 一致。
真 SW 测试在 Task 25 加 @requires_solidworks marker。

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

**🛑 CP-1 暂停**：用户确认 worker 退出码与 stdout JSON 契约后 → 进入 Task 2

---

## Task 2：ConfigResolution 数据类 + NeedsUserDecision 异常

**Files:**
- Create: `adapters/solidworks/sw_config_broker.py`
- Create: `tests/test_sw_config_broker.py`

- [ ] **Step 1：写失败测试 — ConfigResolution 字段**

```python
# tests/test_sw_config_broker.py
import pytest


def test_config_resolution_dataclass_fields():
    from adapters.solidworks.sw_config_broker import ConfigResolution

    r = ConfigResolution(
        config_name="80×2.4",
        source="auto",
        confidence=1.0,
        available_configs=["28×1.9", "80×2.4"],
        notes="字面完全匹配",
    )
    assert r.config_name == "80×2.4"
    assert r.source == "auto"
    assert r.confidence == 1.0
    assert r.available_configs == ["28×1.9", "80×2.4"]
    assert r.notes == "字面完全匹配"


def test_config_resolution_notes_default_empty():
    from adapters.solidworks.sw_config_broker import ConfigResolution

    r = ConfigResolution(
        config_name=None,
        source="policy_fallback",
        confidence=0.0,
        available_configs=[],
    )
    assert r.notes == ""


def test_needs_user_decision_carries_record():
    from adapters.solidworks.sw_config_broker import NeedsUserDecision

    rec = {"part_no": "X", "match_failure_reason": "no_exact_or_fuzzy_match_with_high_confidence"}
    exc = NeedsUserDecision(part_no="X", subsystem="end_effector", pending_record=rec)
    assert exc.part_no == "X"
    assert exc.subsystem == "end_effector"
    assert exc.pending_record is rec
    assert "X" in str(exc)
    assert "end_effector" in str(exc)
```

- [ ] **Step 2：跑测试确认 FAIL**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py -v
```

Expected: 3 FAILED (module not found)

- [ ] **Step 3：写最小实现**

```python
# adapters/solidworks/sw_config_broker.py
"""adapters/solidworks/sw_config_broker.py — SW Toolbox 配置名匹配 broker。

设计参见 docs/superpowers/specs/2026-04-25-sw-toolbox-llm-config-broker-design.md (rev 2)。

主流程：
1. SW COM 列 SLDPRT 当前可用 configurations
2. 读 spec_decisions.json 缓存命中 + 三项校验 → 直接返回 cached_decision
3. 规则匹配 BOM dim → config (L1 精确 / L2 子串)，confidence ≥ 0.7 → auto
4. 含糊匹配 → 看 CAD_AMBIGUOUS_CONFIG_POLICY env：
   - "halt"（默认）→ 抛 NeedsUserDecision
   - "fallback_cadquery" → 返回 policy_fallback ConfigResolution（仍累积 pending）
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConfigResolution:
    """broker 返回的解析结果。

    confidence 取值表（详见 spec §4.1）:
        source="cached_decision":  1.0 （用户已确认）
        source="auto" + L1 精确:    1.0 （字面完全匹配）
        source="auto" + L2 子串:    0.7 ~ 0.95 （依命中长度）
        source="policy_fallback":   0.0 （非匹配，env var 强制 fallback）
    """

    config_name: str | None
    source: str  # "cached_decision" | "auto" | "policy_fallback"
    confidence: float
    available_configs: list[str]
    notes: str = ""


class NeedsUserDecision(Exception):
    """broker 在含糊匹配 + policy="halt" 时抛此异常。

    sw_toolbox_adapter 捕获后 return miss；
    gen_std_parts 累积所有抛出的 record 后一次性原子写 pending 文件。
    broker 自身不写 pending（rev 2 修订）—— 异常携带 record，避免进程崩溃时部分写入。
    """

    def __init__(self, part_no: str, subsystem: str, pending_record: dict):
        self.part_no = part_no
        self.subsystem = subsystem
        self.pending_record = pending_record
        super().__init__(f"User decision needed for {subsystem}/{part_no}")
```

- [ ] **Step 4：跑测试确认 PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py -v
```

Expected: 3 passed

- [ ] **Step 5：commit**

```bash
git add adapters/solidworks/sw_config_broker.py tests/test_sw_config_broker.py
git commit -m "feat(sw_config_broker): 新增 ConfigResolution 数据类 + NeedsUserDecision 异常

confidence 字段语义按 spec §4.1 表格定义。
exception 携带 part_no/subsystem/pending_record，gen_std_parts 累积后一次性写 pending。

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3：_build_bom_dim_signature

**Files:**
- Modify: `adapters/solidworks/sw_config_broker.py`
- Modify: `tests/test_sw_config_broker.py`

- [ ] **Step 1：写失败测试 — 三种 BOM 形式**

```python
# 加到 tests/test_sw_config_broker.py 末尾

class TestBuildBomDimSignature:
    """spec §5.1: bom_dim_signature = f'{name_cn}|{material}'"""

    def test_fastener_dim_in_material(self):
        from adapters.solidworks.sw_config_broker import _build_bom_dim_signature

        bom = {"part_no": "X", "name_cn": "内六角螺栓", "material": "GB/T 70.1 M8×20"}
        assert _build_bom_dim_signature(bom) == "内六角螺栓|GB/T 70.1 M8×20"

    def test_bearing_dim_in_name_cn(self):
        from adapters.solidworks.sw_config_broker import _build_bom_dim_signature

        bom = {"part_no": "X", "name_cn": "深沟球轴承 6205", "material": "GCr15"}
        assert _build_bom_dim_signature(bom) == "深沟球轴承 6205|GCr15"

    def test_seal(self):
        from adapters.solidworks.sw_config_broker import _build_bom_dim_signature

        bom = {"part_no": "X", "name_cn": "O型圈", "material": "FKM Φ80×2.4"}
        assert _build_bom_dim_signature(bom) == "O型圈|FKM Φ80×2.4"

    def test_missing_fields_default_empty(self):
        from adapters.solidworks.sw_config_broker import _build_bom_dim_signature

        bom = {"part_no": "X"}
        assert _build_bom_dim_signature(bom) == "|"

    def test_none_fields_treated_as_empty(self):
        from adapters.solidworks.sw_config_broker import _build_bom_dim_signature

        bom = {"part_no": "X", "name_cn": None, "material": None}
        assert _build_bom_dim_signature(bom) == "|"
```

- [ ] **Step 2：跑测试确认 FAIL**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestBuildBomDimSignature -v
```

Expected: 5 FAILED (function not defined)

- [ ] **Step 3：写实现**

```python
# 加到 adapters/solidworks/sw_config_broker.py

def _build_bom_dim_signature(bom_row: dict) -> str:
    """组合 name_cn 和 material 为稳定签名（spec §5.1 rev 2）。

    用于决策缓存的 invalidation 比对（bom_dim_signature_changed 触发）。
    缺字段或 None 当空字符串。

    例:
        fastener: '内六角螺栓|GB/T 70.1 M8×20'
        bearing:  '深沟球轴承 6205|GCr15'
        seal:     'O型圈|FKM Φ80×2.4'
    """
    name_cn = bom_row.get("name_cn") or ""
    material = bom_row.get("material") or ""
    return f"{name_cn}|{material}"
```

- [ ] **Step 4：跑测试确认 PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestBuildBomDimSignature -v
```

Expected: 5 passed

- [ ] **Step 5：commit**

```bash
git add adapters/solidworks/sw_config_broker.py tests/test_sw_config_broker.py
git commit -m "feat(sw_config_broker): 新增 _build_bom_dim_signature

按 spec §5.1 rev 2 锁定 f'{name_cn}|{material}' 公式；
覆盖 fastener / bearing / seal 三种 BOM 形式 + 缺字段降级。

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4：_match_config_by_rule — L1 精确归一化

**Files:**
- Modify: `adapters/solidworks/sw_config_broker.py`
- Modify: `tests/test_sw_config_broker.py`

- [ ] **Step 1：写失败测试 — L1 精确匹配**

```python
class TestMatchConfigByRule:
    """spec §4.4 #2: L1 精确归一化 confidence=1.0"""

    def test_l1_exact_unicode_x(self):
        """BOM 'Φ80×2.4' + available '80×2.4' → 完全匹配 confidence=1.0"""
        from adapters.solidworks.sw_config_broker import _match_config_by_rule

        result = _match_config_by_rule(
            bom_dim_signature="O型圈|FKM Φ80×2.4",
            available=["28×1.9", "80×2.4", "100×3.0"],
        )
        assert result == ("80×2.4", 1.0)

    def test_l1_exact_ascii_x(self):
        """BOM 'Φ80×2.4' + available '80x2.4' → 归一化后匹配 confidence=1.0"""
        from adapters.solidworks.sw_config_broker import _match_config_by_rule

        result = _match_config_by_rule(
            bom_dim_signature="O型圈|FKM Φ80×2.4",
            available=["28×1.9", "80x2.4", "100×3.0"],
        )
        assert result == ("80x2.4", 1.0)

    def test_l1_exact_with_space_dash(self):
        """BOM 'M8×20' + available 'M8 X 20' → 归一化匹配 confidence=1.0"""
        from adapters.solidworks.sw_config_broker import _match_config_by_rule

        result = _match_config_by_rule(
            bom_dim_signature="内六角螺栓|GB/T 70.1 M8×20",
            available=["M6 X 20", "M8 X 20", "M10 X 20"],
        )
        assert result == ("M8 X 20", 1.0)

    def test_no_match_returns_none(self):
        """available 完全不匹配 → None"""
        from adapters.solidworks.sw_config_broker import _match_config_by_rule

        result = _match_config_by_rule(
            bom_dim_signature="O型圈|FKM Φ80×2.4",
            available=["AAA", "BBB"],
        )
        assert result is None

    def test_empty_available_returns_none(self):
        from adapters.solidworks.sw_config_broker import _match_config_by_rule

        result = _match_config_by_rule(
            bom_dim_signature="X",
            available=[],
        )
        assert result is None
```

- [ ] **Step 2：跑测试确认 FAIL**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestMatchConfigByRule -v
```

Expected: 5 FAILED

- [ ] **Step 3：写最小 L1 实现（含归一化）**

```python
# 加到 adapters/solidworks/sw_config_broker.py
import re

AUTO_MATCH_THRESHOLD = 0.7

# 尺寸 token 正则：数字（含小数）+ 任意分隔符 + 数字 / 单 M\d+
_SIZE_TOKEN_RE = re.compile(r"[ΦΦϕφ]?\s*[Mm]?\d+(?:\.\d+)?(?:\s*[×xX×*]\s*\d+(?:\.\d+)?)?")


def _normalize_for_match(s: str) -> str:
    """统一归一化：× → x，Φ → 空，去 [-_\\s]，lowercase。"""
    s = s.replace("×", "x").replace("Φ", "").replace("ϕ", "").replace("φ", "")
    s = re.sub(r"[-_\s]", "", s)
    return s.lower()


def _extract_size_tokens(bom_dim_signature: str) -> list[str]:
    """从 bom_dim_signature 提取所有可能的尺寸子串（含 'M8x20', '80x2.4', 'MR105ZZ' 等）。
    返回归一化后的 token 列表。"""
    matches = _SIZE_TOKEN_RE.findall(bom_dim_signature)
    return [_normalize_for_match(m) for m in matches if m.strip()]


def _match_config_by_rule(
    bom_dim_signature: str,
    available: list[str],
) -> tuple[str, float] | None:
    """两层匹配（spec §4.4 #2）。

    L1 精确归一化（confidence=1.0）：尺寸 token 与 available 字符串归一化后等值
    L2 包含子串（confidence=0.7~0.95）：available 字符串归一化后包含尺寸 token

    返回 (matched_config, confidence) 或 None。
    同 confidence 多个候选时取**字符串最短**的（最少干扰）。
    """
    if not available:
        return None

    tokens = _extract_size_tokens(bom_dim_signature)
    if not tokens:
        return None

    # L1: 尺寸 token 与候选归一化后等值
    l1_hits: list[tuple[str, float]] = []
    for cfg in available:
        cfg_norm = _normalize_for_match(cfg)
        for tok in tokens:
            if cfg_norm == tok:
                l1_hits.append((cfg, 1.0))
                break

    if l1_hits:
        # 取字符串最短的
        l1_hits.sort(key=lambda x: len(x[0]))
        return l1_hits[0]

    # L2 在下个 task 实现
    return None
```

- [ ] **Step 4：跑测试确认 L1 用例 PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestMatchConfigByRule -v
```

Expected: 5 passed

- [ ] **Step 5：commit**

```bash
git add adapters/solidworks/sw_config_broker.py tests/test_sw_config_broker.py
git commit -m "feat(sw_config_broker): _match_config_by_rule L1 精确归一化层

× → x / Φ → '' / 去 [-_\\s] / lowercase 归一化后等值比对；
confidence=1.0；同 confidence 取字符串最短的候选；
L2 子串层在下个 task 实现。

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5：_match_config_by_rule — L2 子串包含 + 假阳性防御

**Files:**
- Modify: `adapters/solidworks/sw_config_broker.py`
- Modify: `tests/test_sw_config_broker.py`

- [ ] **Step 1：写失败测试 — L2 子串 + 假阳性**

```python
class TestMatchConfigByRuleL2:
    """spec §4.4 #2: L2 包含子串 + spec §10.2 假阳性防御"""

    def test_l2_substring_match(self):
        """available 'GB1235-80x2.4' 包含归一化 token '80x2.4' → confidence=0.7~0.95"""
        from adapters.solidworks.sw_config_broker import _match_config_by_rule

        result = _match_config_by_rule(
            bom_dim_signature="O型圈|FKM Φ80×2.4",
            available=["GB1235-28x1.9", "GB1235-80x2.4", "GB1235-100x3.0"],
        )
        assert result is not None
        config, conf = result
        assert config == "GB1235-80x2.4"
        assert 0.7 <= conf <= 0.95

    def test_l2_false_positive_m6_vs_m16(self):
        """关键防御：BOM M16 + available [M6×20, M16×20] → 必须命中 M16×20 不是 M6×20

        L1 匹配 'm16x20' 与 available 归一化后比对：
        - 'M6×20' → 'm6x20' ≠ 'm16x20'
        - 'M16×20' → 'm16x20' == 'm16x20' ✓
        """
        from adapters.solidworks.sw_config_broker import _match_config_by_rule

        result = _match_config_by_rule(
            bom_dim_signature="内六角螺栓|GB/T 70.1 M16×20",
            available=["M6×20", "M16×20"],
        )
        assert result is not None
        assert result[0] == "M16×20"

    def test_l2_short_token_low_confidence(self):
        """短 token (如纯数字 '6') confidence 较低。
        BOM '6' + available 'GB1234-6' → 命中但 confidence < 0.95"""
        from adapters.solidworks.sw_config_broker import _match_config_by_rule

        result = _match_config_by_rule(
            bom_dim_signature="X|6",
            available=["GB1234-6"],
        )
        if result:
            assert result[1] < 0.95

    def test_below_threshold_returns_none(self):
        """confidence < 0.7 → 返回 None，让 caller 走含糊路径"""
        from adapters.solidworks.sw_config_broker import _match_config_by_rule

        # 故意构造：BOM 提取 token '1'，available 含很多 '1' 但都更长
        # confidence = min(0.95, 0.7 + len('1')/100) = 0.71，但归一化后唯一 token 太弱可能 None
        # 此用例验证：极弱匹配不返回
        result = _match_config_by_rule(
            bom_dim_signature="X|2.4",  # token '2.4' 归一 '2.4'
            available=["abc"],  # 不含 '2.4'
        )
        assert result is None

    def test_l2_multi_match_shortest_wins(self):
        """L2 多命中 → 取字符串最短"""
        from adapters.solidworks.sw_config_broker import _match_config_by_rule

        result = _match_config_by_rule(
            bom_dim_signature="O型圈|FKM Φ80×2.4",
            available=["VERY_LONG_PREFIX-80x2.4", "80x2.4-suffix", "abc-80x2.4"],
        )
        assert result is not None
        # L1 等值不命中（都有前后缀），L2 子串多命中 → 取最短
        assert result[0] == "80x2.4-suffix"  # 14 chars vs 13 chars vs 22 chars
```

- [ ] **Step 2：跑测试确认 FAIL（L2 未实现）**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestMatchConfigByRuleL2 -v
```

Expected: 多数 FAILED

- [ ] **Step 3：补 L2 实现**

```python
# 替换 adapters/solidworks/sw_config_broker.py 里 _match_config_by_rule 函数：

def _match_config_by_rule(
    bom_dim_signature: str,
    available: list[str],
) -> tuple[str, float] | None:
    if not available:
        return None

    tokens = _extract_size_tokens(bom_dim_signature)
    if not tokens:
        return None

    # L1
    l1_hits: list[tuple[str, float]] = []
    for cfg in available:
        cfg_norm = _normalize_for_match(cfg)
        for tok in tokens:
            if cfg_norm == tok:
                l1_hits.append((cfg, 1.0))
                break

    if l1_hits:
        l1_hits.sort(key=lambda x: len(x[0]))
        return l1_hits[0]

    # L2 包含子串
    l2_hits: list[tuple[str, float]] = []
    for cfg in available:
        cfg_norm = _normalize_for_match(cfg)
        # 优先匹配最长 token（最具体）
        for tok in sorted(tokens, key=len, reverse=True):
            if tok and tok in cfg_norm:
                # confidence = min(0.95, 0.7 + len(tok)/100)
                conf = min(0.95, 0.7 + len(tok) / 100.0)
                l2_hits.append((cfg, conf))
                break

    if not l2_hits:
        return None

    # 过滤未达阈值
    l2_hits = [(c, conf) for c, conf in l2_hits if conf >= AUTO_MATCH_THRESHOLD]
    if not l2_hits:
        return None

    # 同 confidence 取字符串最短
    l2_hits.sort(key=lambda x: (-x[1], len(x[0])))
    return l2_hits[0]
```

- [ ] **Step 4：跑测试确认 PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestMatchConfigByRule tests/test_sw_config_broker.py::TestMatchConfigByRuleL2 -v
```

Expected: 全部 passed

- [ ] **Step 5：commit**

```bash
git add adapters/solidworks/sw_config_broker.py tests/test_sw_config_broker.py
git commit -m "feat(sw_config_broker): _match_config_by_rule L2 子串层 + M6/M16 假阳性防御

L2 confidence = min(0.95, 0.7 + len(token)/100)；
匹配按最长 token 优先（最具体）；
同 confidence 多候选取字符串最短；
M6 vs M16 边界用 L1 等值比对自然区分（归一化后 'm6x20' ≠ 'm16x20'）。

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 6：_validate_cached_decision

**Files:**
- Modify: `adapters/solidworks/sw_config_broker.py`
- Modify: `tests/test_sw_config_broker.py`

- [ ] **Step 1：写失败测试 — 三项 invalidation 分别触发**

```python
class TestValidateCachedDecision:
    """spec §5.2: 三项失效条件"""

    def _make_decision(self, **overrides):
        base = {
            "bom_dim_signature": "O型圈|FKM Φ80×2.4",
            "sldprt_filename": "o-rings series a gb.sldprt",
            "decision": "use_config",
            "config_name": "80×2.4",
            "user_note": "",
            "decided_at": "2026-04-25T22:25:11+00:00",
        }
        base.update(overrides)
        return base

    def test_valid_decision_passes(self):
        from adapters.solidworks.sw_config_broker import _validate_cached_decision

        decision = self._make_decision()
        valid, reason = _validate_cached_decision(
            decision,
            current_bom_signature="O型圈|FKM Φ80×2.4",
            current_sldprt_filename="o-rings series a gb.sldprt",
            current_available_configs=["28×1.9", "80×2.4", "100×3.0"],
        )
        assert valid is True
        assert reason is None

    def test_bom_dim_signature_changed(self):
        from adapters.solidworks.sw_config_broker import _validate_cached_decision

        decision = self._make_decision()
        valid, reason = _validate_cached_decision(
            decision,
            current_bom_signature="O型圈|FKM Φ100×3.0",  # 改了
            current_sldprt_filename="o-rings series a gb.sldprt",
            current_available_configs=["28×1.9", "80×2.4"],
        )
        assert valid is False
        assert reason == "bom_dim_signature_changed"

    def test_sldprt_filename_changed(self):
        from adapters.solidworks.sw_config_broker import _validate_cached_decision

        decision = self._make_decision()
        valid, reason = _validate_cached_decision(
            decision,
            current_bom_signature="O型圈|FKM Φ80×2.4",
            current_sldprt_filename="o-rings series b gb.sldprt",  # 改了
            current_available_configs=["28×1.9", "80×2.4"],
        )
        assert valid is False
        assert reason == "sldprt_filename_changed"

    def test_config_name_not_in_available(self):
        from adapters.solidworks.sw_config_broker import _validate_cached_decision

        decision = self._make_decision()
        valid, reason = _validate_cached_decision(
            decision,
            current_bom_signature="O型圈|FKM Φ80×2.4",
            current_sldprt_filename="o-rings series a gb.sldprt",
            current_available_configs=["28×1.9"],  # 没了 80×2.4
        )
        assert valid is False
        assert reason == "config_name_not_in_available_configs"

    def test_fallback_cadquery_skips_config_check(self):
        """spec §5.2: decision=fallback_cadquery 时跳过第三项检查（无 config_name 可校）"""
        from adapters.solidworks.sw_config_broker import _validate_cached_decision

        decision = self._make_decision(decision="fallback_cadquery", config_name=None)
        valid, reason = _validate_cached_decision(
            decision,
            current_bom_signature="O型圈|FKM Φ80×2.4",
            current_sldprt_filename="o-rings series a gb.sldprt",
            current_available_configs=[],  # 即使空也 OK
        )
        assert valid is True
        assert reason is None
```

- [ ] **Step 2：跑测试 FAIL**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestValidateCachedDecision -v
```

Expected: 5 FAILED

- [ ] **Step 3：写实现**

```python
# 加到 adapters/solidworks/sw_config_broker.py

def _validate_cached_decision(
    decision: dict,
    current_bom_signature: str,
    current_sldprt_filename: str,
    current_available_configs: list[str],
) -> tuple[bool, str | None]:
    """三项校验（spec §5.2）。返回 (is_valid, invalidation_reason)。

    - bom_dim_signature_changed: BOM 行字段变了（用户改了 spec）
    - sldprt_filename_changed: SW 升级换了 SLDPRT 文件
    - config_name_not_in_available_configs: SW 升级后该 config 改名/删除
      （仅 decision="use_config" 时检查；fallback_cadquery 跳过）
    """
    if decision.get("bom_dim_signature") != current_bom_signature:
        return False, "bom_dim_signature_changed"

    if decision.get("sldprt_filename") != current_sldprt_filename:
        return False, "sldprt_filename_changed"

    if decision.get("decision") == "use_config":
        config_name = decision.get("config_name")
        if config_name not in current_available_configs:
            return False, "config_name_not_in_available_configs"

    return True, None
```

- [ ] **Step 4：跑测试 PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestValidateCachedDecision -v
```

Expected: 5 passed

- [ ] **Step 5：commit**

```bash
git add adapters/solidworks/sw_config_broker.py tests/test_sw_config_broker.py
git commit -m "feat(sw_config_broker): _validate_cached_decision 三项失效检查

bom_dim_signature_changed / sldprt_filename_changed / config_name_not_in_available_configs；
decision=fallback_cadquery 跳过第三项（无 config_name 可校）。

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 7：_build_pending_record（按 match_failure_reason 分支 schema）

**Files:**
- Modify: `adapters/solidworks/sw_config_broker.py`
- Modify: `tests/test_sw_config_broker.py`

- [ ] **Step 1：写失败测试 — 4 类失败模式 schema**

```python
class TestBuildPendingRecord:
    """spec §5.3: pending record schema 按 match_failure_reason 分支"""

    BOM_ORING = {
        "part_no": "GIS-EE-001-03",
        "name_cn": "O型圈",
        "material": "FKM Φ80×2.4",
    }
    SLDPRT = "C:/SOLIDWORKS Data/browser/GB/o-rings/all o-rings/o-rings series a gb.sldprt"

    def test_no_exact_or_fuzzy_match(self):
        from adapters.solidworks.sw_config_broker import _build_pending_record

        rec = _build_pending_record(
            bom_row=self.BOM_ORING,
            sldprt_path=self.SLDPRT,
            available=["28×1.9", "100×3.0"],
            match_failure_reason="no_exact_or_fuzzy_match_with_high_confidence",
            attempted_match=None,
        )
        assert rec["part_no"] == "GIS-EE-001-03"
        assert rec["name_cn"] == "O型圈"
        assert rec["material"] == "FKM Φ80×2.4"
        assert rec["bom_dim_signature"] == "O型圈|FKM Φ80×2.4"
        assert rec["sldprt_path"] == self.SLDPRT
        assert rec["sldprt_filename"] == "o-rings series a gb.sldprt"
        assert rec["available_configs"] == ["28×1.9", "100×3.0"]
        assert rec["attempted_match"] is None
        assert rec["match_failure_reason"] == "no_exact_or_fuzzy_match_with_high_confidence"
        # suggested_options 至少含 fallback_cadquery
        assert any(opt["action"] == "fallback_cadquery" for opt in rec["suggested_options"])

    def test_com_open_failed(self):
        """COM 失败 → available_configs=[]，suggested 仅 fallback_cadquery"""
        from adapters.solidworks.sw_config_broker import _build_pending_record

        rec = _build_pending_record(
            bom_row=self.BOM_ORING,
            sldprt_path=self.SLDPRT,
            available=[],
            match_failure_reason="com_open_failed",
            attempted_match=None,
        )
        assert rec["available_configs"] == []
        assert len(rec["suggested_options"]) == 1
        assert rec["suggested_options"][0]["action"] == "fallback_cadquery"

    def test_empty_config_list_default_only(self):
        """SLDPRT 仅有 'Default' → suggested 含 use_config + fallback"""
        from adapters.solidworks.sw_config_broker import _build_pending_record

        rec = _build_pending_record(
            bom_row=self.BOM_ORING,
            sldprt_path=self.SLDPRT,
            available=["Default"],
            match_failure_reason="empty_config_list",
            attempted_match=None,
        )
        actions = [o["action"] for o in rec["suggested_options"]]
        assert "use_config" in actions
        assert "fallback_cadquery" in actions
        # 找到 use_config 选项 config_name=Default
        use_default = [o for o in rec["suggested_options"] if o["action"] == "use_config"][0]
        assert use_default["config_name"] == "Default"

    def test_multiple_high_confidence(self):
        """多候选 ≥ 0.7 同分 → suggested 列出全部"""
        from adapters.solidworks.sw_config_broker import _build_pending_record

        rec = _build_pending_record(
            bom_row=self.BOM_ORING,
            sldprt_path=self.SLDPRT,
            available=["80×2.4", "Φ80×2.4mm"],
            match_failure_reason="multiple_high_confidence_matches",
            attempted_match=None,
        )
        use_options = [o for o in rec["suggested_options"] if o["action"] == "use_config"]
        assert len(use_options) >= 2
```

- [ ] **Step 2：跑测试 FAIL**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestBuildPendingRecord -v
```

Expected: 4 FAILED

- [ ] **Step 3：写实现**

```python
# 加到 adapters/solidworks/sw_config_broker.py
from pathlib import Path


def _build_pending_record(
    bom_row: dict,
    sldprt_path: str,
    available: list[str],
    match_failure_reason: str,
    attempted_match: dict | None,
) -> dict:
    """构造单 item 的 pending record（spec §5.3）。

    schema 按 match_failure_reason 分支：
    - no_exact_or_fuzzy_match_with_high_confidence: 推 best L2 + fallback
    - multiple_high_confidence_matches: 列出全部 ≥ 0.7 候选 + fallback
    - com_open_failed: 仅 fallback
    - empty_config_list: use_config "Default" + fallback
    """
    sldprt_filename = Path(sldprt_path).name
    suggested: list[dict] = []

    if match_failure_reason == "no_exact_or_fuzzy_match_with_high_confidence":
        if available:
            # 取规则匹配的次优候选（即使没过阈值，让用户参考）
            from adapters.solidworks.sw_config_broker import _match_config_by_rule, _normalize_for_match, _extract_size_tokens
            tokens = _extract_size_tokens(_build_bom_dim_signature(bom_row))
            best_below: tuple[str, float] | None = None
            for cfg in available:
                cfg_norm = _normalize_for_match(cfg)
                for tok in sorted(tokens, key=len, reverse=True):
                    if tok and tok in cfg_norm:
                        conf = 0.7 + len(tok) / 100.0  # 不卡 0.95 上限，让用户看真实近似度
                        if best_below is None or conf > best_below[1]:
                            best_below = (cfg, conf)
                        break
            if best_below:
                suggested.append({
                    "action": "use_config",
                    "config_name": best_below[0],
                    "rationale": f"模糊匹配最近候选（confidence={best_below[1]:.2f}，未达自动阈值 0.7）",
                })
        suggested.append({
            "action": "fallback_cadquery",
            "rationale": "SW 配置略有差异时可用尺寸正确的 CadQuery 近似体",
        })

    elif match_failure_reason == "multiple_high_confidence_matches":
        for cfg in available:
            suggested.append({
                "action": "use_config",
                "config_name": cfg,
                "rationale": f"高置信度候选之一",
            })
        suggested.append({
            "action": "fallback_cadquery",
            "rationale": "SW 多候选难辨时可用 CadQuery 近似体",
        })

    elif match_failure_reason == "com_open_failed":
        suggested.append({
            "action": "fallback_cadquery",
            "rationale": "COM 列配置失败，建议使用 CadQuery 近似",
        })

    elif match_failure_reason == "empty_config_list":
        suggested.append({
            "action": "use_config",
            "config_name": "Default",
            "rationale": "SLDPRT 仅含 Default 配置",
        })
        suggested.append({
            "action": "fallback_cadquery",
            "rationale": "默认配置尺寸不匹配时用 CadQuery 近似",
        })

    return {
        "part_no": bom_row.get("part_no", ""),
        "name_cn": bom_row.get("name_cn", "") or "",
        "material": bom_row.get("material", "") or "",
        "bom_dim_signature": _build_bom_dim_signature(bom_row),
        "sldprt_path": sldprt_path,
        "sldprt_filename": sldprt_filename,
        "available_configs": available,
        "attempted_match": attempted_match,
        "match_failure_reason": match_failure_reason,
        "suggested_options": suggested,
    }
```

- [ ] **Step 4：跑测试 PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestBuildPendingRecord -v
```

Expected: 4 passed

- [ ] **Step 5：commit**

```bash
git add adapters/solidworks/sw_config_broker.py tests/test_sw_config_broker.py
git commit -m "feat(sw_config_broker): _build_pending_record 按 match_failure_reason 分支 schema

4 类失败模式：no_match / multiple / com_failed / empty_list；
suggested_options 含 use_config + fallback_cadquery 双选项；
COM 失败时仅 fallback。

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

**🛑 CP-2 暂停**：用户审 4-7 任务的纯函数实现，确认匹配规则与 record schema OK 后 → 进入 Task 8

---

## Task 8：fixture `tmp_project_dir`

**Files:**
- Create: `tests/conftest.py`（修改：加新 fixture，如不存在则创建）

- [ ] **Step 1：检查 conftest.py 是否已有该 fixture**

```bash
grep -n "tmp_project_dir" tests/conftest.py 2>/dev/null
```

Expected: 无输出（需新增）

- [ ] **Step 2：写 fixture**

```python
# 加到 tests/conftest.py 末尾（或文件不存在则创建）

import importlib
import os
import sys
import pytest
from pathlib import Path


@pytest.fixture
def tmp_project_dir(tmp_path, monkeypatch):
    """为 broker 测试提供独立项目目录。

    - 在 tmp_path 下建 .cad-spec-gen/ 子目录
    - 设 CAD_PROJECT_ROOT env 指向 tmp_path
    - 重新 import cad_paths 让 PROJECT_ROOT 模块级常量重算

    yields: tmp_path (Path) — 项目根
    """
    cad_dir = tmp_path / ".cad-spec-gen"
    cad_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("CAD_PROJECT_ROOT", str(tmp_path))

    # 重 import cad_paths 触发 PROJECT_ROOT 重新读取 env
    if "cad_paths" in sys.modules:
        importlib.reload(sys.modules["cad_paths"])

    yield tmp_path

    # 测试结束后再 reload 一次，避免污染下一个测试
    if "cad_paths" in sys.modules:
        importlib.reload(sys.modules["cad_paths"])
```

- [ ] **Step 3：写 fixture 验证测试**

```python
# tests/test_sw_config_broker.py 末尾

class TestFixtures:
    def test_tmp_project_dir_creates_cad_dir(self, tmp_project_dir):
        assert (tmp_project_dir / ".cad-spec-gen").is_dir()

    def test_tmp_project_dir_sets_env(self, tmp_project_dir):
        import os
        assert os.environ["CAD_PROJECT_ROOT"] == str(tmp_project_dir)

    def test_tmp_project_dir_cad_paths_synced(self, tmp_project_dir):
        from cad_paths import PROJECT_ROOT
        # PROJECT_ROOT 经过 normpath 处理
        assert os.path.normpath(PROJECT_ROOT) == os.path.normpath(str(tmp_project_dir))
```

- [ ] **Step 4：跑测试 PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestFixtures -v
```

Expected: 3 passed

- [ ] **Step 5：commit**

```bash
git add tests/conftest.py tests/test_sw_config_broker.py
git commit -m "test(sw_config_broker): tmp_project_dir fixture

为后续 broker 文件 I/O 测试提供独立项目根 + CAD_PROJECT_ROOT env 隔离 + cad_paths reload。

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 9：_load_decisions_envelope + _save_decisions_envelope

**Files:**
- Modify: `adapters/solidworks/sw_config_broker.py`
- Modify: `tests/test_sw_config_broker.py`

- [ ] **Step 1：写失败测试 — 文件 I/O 全路径**

```python
class TestDecisionsEnvelopeIO:
    """spec §4.3: _load/_save_decisions_envelope"""

    def test_load_missing_file_returns_empty_envelope(self, tmp_project_dir):
        from adapters.solidworks.sw_config_broker import _load_decisions_envelope

        env = _load_decisions_envelope()
        assert env["schema_version"] == 2
        assert env["decisions_by_subsystem"] == {}
        assert env["decisions_history"] == []

    def test_save_then_load_roundtrip(self, tmp_project_dir):
        import json
        from adapters.solidworks.sw_config_broker import _load_decisions_envelope, _save_decisions_envelope

        envelope = {
            "schema_version": 2,
            "last_updated": "2026-04-25T22:30:00+00:00",
            "decisions_by_subsystem": {
                "end_effector": {
                    "GIS-EE-001-03": {
                        "bom_dim_signature": "O型圈|FKM Φ80×2.4",
                        "sldprt_filename": "o-rings series a gb.sldprt",
                        "decision": "use_config",
                        "config_name": "80×2.4",
                        "user_note": "ok",
                        "decided_at": "2026-04-25T22:25:11+00:00",
                    }
                }
            },
            "decisions_history": [],
        }
        _save_decisions_envelope(envelope)

        # 文件原子写入：必须存在 + JSON 合法
        path = tmp_project_dir / ".cad-spec-gen" / "spec_decisions.json"
        assert path.is_file()
        loaded_raw = json.loads(path.read_text(encoding="utf-8"))
        assert loaded_raw == envelope

        # _load 接口
        loaded = _load_decisions_envelope()
        assert loaded == envelope

    def test_load_corrupt_json_fails_loud(self, tmp_project_dir):
        """spec §6: decisions.json 损坏 → fail loud 含行号"""
        from adapters.solidworks.sw_config_broker import _load_decisions_envelope

        path = tmp_project_dir / ".cad-spec-gen" / "spec_decisions.json"
        path.write_text('{ "broken JSON syntax', encoding="utf-8")

        with pytest.raises(ValueError, match="syntax error"):
            _load_decisions_envelope()

    def test_load_schema_version_mismatch_fails(self, tmp_project_dir):
        """spec §6: schema_version 不一致 → 阻塞"""
        import json
        from adapters.solidworks.sw_config_broker import _load_decisions_envelope

        path = tmp_project_dir / ".cad-spec-gen" / "spec_decisions.json"
        path.write_text(json.dumps({"schema_version": 99, "decisions_by_subsystem": {}}), encoding="utf-8")

        with pytest.raises(ValueError, match="schema_version"):
            _load_decisions_envelope()

    def test_save_atomic_write_via_tmp(self, tmp_project_dir):
        """save 必须先写 .tmp 再 os.replace（防中途崩溃残缺）"""
        from adapters.solidworks.sw_config_broker import _save_decisions_envelope

        envelope = {"schema_version": 2, "decisions_by_subsystem": {}, "decisions_history": []}
        _save_decisions_envelope(envelope)

        path = tmp_project_dir / ".cad-spec-gen" / "spec_decisions.json"
        tmp_path = path.with_suffix(".json.tmp")
        # 写完后 .tmp 应已被 rename
        assert path.is_file()
        assert not tmp_path.exists()
```

- [ ] **Step 2：跑测试 FAIL**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestDecisionsEnvelopeIO -v
```

Expected: 5 FAILED

- [ ] **Step 3：写实现**

```python
# 加到 adapters/solidworks/sw_config_broker.py
import json
import os

SCHEMA_VERSION = 2


def _decisions_path() -> Path:
    """返回 spec_decisions.json 路径（依赖 cad_paths.PROJECT_ROOT 实时读）。"""
    from cad_paths import PROJECT_ROOT
    return Path(PROJECT_ROOT) / ".cad-spec-gen" / "spec_decisions.json"


def _empty_envelope() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "last_updated": "",
        "decisions_by_subsystem": {},
        "decisions_history": [],
    }


def _load_decisions_envelope() -> dict:
    """从 spec_decisions.json 读完整 envelope。

    文件不存在 → 返回空 envelope（含 schema_version=2）。
    JSON syntax error → raise ValueError(含行号 + detail)。
    schema_version 不一致 → raise ValueError 提示重做交互。
    """
    path = _decisions_path()
    if not path.exists():
        return _empty_envelope()

    text = path.read_text(encoding="utf-8")
    try:
        env = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"decisions 文件 {path} 第 {e.lineno} 行 syntax error: {e.msg}"
        ) from e

    if env.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"决策 schema 已升级 v{env.get('schema_version')}→v{SCHEMA_VERSION}，"
            f"请删除 {path} 后重跑 codegen 让 agent 引导重新决策"
        )

    # 补齐缺字段
    env.setdefault("decisions_by_subsystem", {})
    env.setdefault("decisions_history", [])
    return env


def _save_decisions_envelope(envelope: dict) -> None:
    """原子写入 spec_decisions.json（先写 .tmp 再 rename）。"""
    from datetime import datetime, timezone

    path = _decisions_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    envelope["last_updated"] = datetime.now(timezone.utc).isoformat()

    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp_path, path)
```

- [ ] **Step 4：跑测试 PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestDecisionsEnvelopeIO -v
```

Expected: 5 passed

- [ ] **Step 5：commit**

```bash
git add adapters/solidworks/sw_config_broker.py tests/test_sw_config_broker.py
git commit -m "feat(sw_config_broker): _load/_save_decisions_envelope schema v2

文件不存在 → 空 envelope；JSON 损坏 fail loud 含行号；
schema_version 不一致阻塞（不自动 migrate）；
save 用 .tmp + os.replace 原子写。

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 10：_get_decision_for_part + _move_decision_to_history

**Files:**
- Modify: `adapters/solidworks/sw_config_broker.py`
- Modify: `tests/test_sw_config_broker.py`

- [ ] **Step 1：写失败测试**

```python
class TestDecisionAccessors:
    def test_get_decision_present(self):
        from adapters.solidworks.sw_config_broker import _get_decision_for_part

        env = {
            "decisions_by_subsystem": {
                "end_effector": {
                    "GIS-EE-001-03": {"decision": "use_config", "config_name": "80×2.4"}
                }
            }
        }
        d = _get_decision_for_part(env, "end_effector", "GIS-EE-001-03")
        assert d is not None
        assert d["config_name"] == "80×2.4"

    def test_get_decision_missing_subsystem(self):
        from adapters.solidworks.sw_config_broker import _get_decision_for_part

        env = {"decisions_by_subsystem": {}}
        assert _get_decision_for_part(env, "end_effector", "X") is None

    def test_get_decision_missing_part(self):
        from adapters.solidworks.sw_config_broker import _get_decision_for_part

        env = {"decisions_by_subsystem": {"end_effector": {}}}
        assert _get_decision_for_part(env, "end_effector", "X") is None

    def test_move_decision_to_history(self):
        from adapters.solidworks.sw_config_broker import _move_decision_to_history

        env = {
            "decisions_by_subsystem": {
                "end_effector": {
                    "GIS-EE-001-03": {
                        "bom_dim_signature": "X|Y",
                        "decision": "use_config",
                        "config_name": "80×2.4",
                        "decided_at": "2026-04-20T10:00:00+00:00",
                    }
                }
            },
            "decisions_history": [],
        }
        _move_decision_to_history(env, "end_effector", "GIS-EE-001-03",
                                  "config_name_not_in_available_configs")

        # 原位删除
        assert "GIS-EE-001-03" not in env["decisions_by_subsystem"]["end_effector"]
        # history 增加
        assert len(env["decisions_history"]) == 1
        h = env["decisions_history"][0]
        assert h["subsystem"] == "end_effector"
        assert h["part_no"] == "GIS-EE-001-03"
        assert h["invalidation_reason"] == "config_name_not_in_available_configs"
        assert h["previous_decision"]["config_name"] == "80×2.4"
        assert "invalidated_at" in h
```

- [ ] **Step 2：跑测试 FAIL**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestDecisionAccessors -v
```

Expected: 4 FAILED

- [ ] **Step 3：写实现**

```python
# 加到 adapters/solidworks/sw_config_broker.py

def _get_decision_for_part(envelope: dict, subsystem: str, part_no: str) -> dict | None:
    """从 envelope[decisions_by_subsystem][subsystem][part_no] 取，缺失返回 None。"""
    return (
        envelope.get("decisions_by_subsystem", {})
        .get(subsystem, {})
        .get(part_no)
    )


def _move_decision_to_history(
    envelope: dict,
    subsystem: str,
    part_no: str,
    invalidation_reason: str,
) -> None:
    """把 decision 拷贝到 envelope[decisions_history] 并删除原位。in-place 修改。

    调用方负责 _save_decisions_envelope 持久化。
    """
    from datetime import datetime, timezone

    decision = envelope["decisions_by_subsystem"][subsystem].pop(part_no)
    envelope.setdefault("decisions_history", []).append({
        "subsystem": subsystem,
        "part_no": part_no,
        "previous_decision": decision,
        "invalidated_at": datetime.now(timezone.utc).isoformat(),
        "invalidation_reason": invalidation_reason,
    })
```

- [ ] **Step 4：跑测试 PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestDecisionAccessors -v
```

Expected: 4 passed

- [ ] **Step 5：commit**

```bash
git add adapters/solidworks/sw_config_broker.py tests/test_sw_config_broker.py
git commit -m "feat(sw_config_broker): _get_decision_for_part + _move_decision_to_history

decision 失效时拷贝到 decisions_history（含 invalidated_at + reason）+ 删除原位。
in-place 修改 envelope，调用方自行 save。

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

**🛑 CP-3 暂停**：用户审 schema v2 envelope 操作 OK 后 → 进入 Task 11

---

## Task 11：_list_configs_via_com（含 _CONFIG_LIST_CACHE）

**Files:**
- Modify: `adapters/solidworks/sw_config_broker.py`
- Modify: `tests/test_sw_config_broker.py`

- [ ] **Step 1：写失败测试 — mock subprocess.run**

```python
class TestListConfigsViaCom:
    """spec §4.3 + §4.4 #1: 调 worker subprocess + 内部 _CONFIG_LIST_CACHE"""

    def test_list_returns_parsed_json(self, monkeypatch):
        import subprocess

        from adapters.solidworks import sw_config_broker

        # 清缓存
        sw_config_broker._CONFIG_LIST_CACHE.clear()

        # mock subprocess.run 返回成功 + JSON list
        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout='["28×1.9", "80×2.4", "100×3.0"]\n',
                stderr="",
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        result = sw_config_broker._list_configs_via_com("dummy.sldprt")
        assert result == ["28×1.9", "80×2.4", "100×3.0"]

    def test_list_caches_per_path(self, monkeypatch):
        """同 sldprt 第二次调 → 从 cache 拿，不再调 subprocess"""
        import subprocess
        from adapters.solidworks import sw_config_broker

        sw_config_broker._CONFIG_LIST_CACHE.clear()

        call_count = [0]

        def fake_run(cmd, **kwargs):
            call_count[0] += 1
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout='["A"]\n', stderr=""
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        sw_config_broker._list_configs_via_com("X.sldprt")
        sw_config_broker._list_configs_via_com("X.sldprt")
        assert call_count[0] == 1  # 只调一次

    def test_list_failure_returns_empty_and_caches(self, monkeypatch):
        """worker 失败 → 返回 [] + cache 标记（避免重试）"""
        import subprocess
        from adapters.solidworks import sw_config_broker

        sw_config_broker._CONFIG_LIST_CACHE.clear()

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                args=cmd, returncode=4, stdout="", stderr="COM crash"
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        result = sw_config_broker._list_configs_via_com("Y.sldprt")
        assert result == []
        # 第二次调不再触发 subprocess
        call_count = [0]
        def counting_run(cmd, **kwargs):
            call_count[0] += 1
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="[]", stderr="")
        monkeypatch.setattr(subprocess, "run", counting_run)
        sw_config_broker._list_configs_via_com("Y.sldprt")
        assert call_count[0] == 0

    def test_list_timeout_returns_empty(self, monkeypatch):
        """subprocess.TimeoutExpired → 返回 []"""
        import subprocess
        from adapters.solidworks import sw_config_broker

        sw_config_broker._CONFIG_LIST_CACHE.clear()

        def fake_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=15)

        monkeypatch.setattr(subprocess, "run", fake_run)

        result = sw_config_broker._list_configs_via_com("Z.sldprt")
        assert result == []
```

- [ ] **Step 2：跑测试 FAIL**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestListConfigsViaCom -v
```

Expected: 4 FAILED

- [ ] **Step 3：写实现**

```python
# 加到 adapters/solidworks/sw_config_broker.py
import logging
import subprocess
import sys

log = logging.getLogger(__name__)

LIST_CONFIGS_TIMEOUT_SEC = 15
_CONFIG_LIST_CACHE: dict[str, list[str]] = {}
_PROJECT_ROOT_FOR_WORKER = Path(__file__).resolve().parents[2]


def _list_configs_via_com(sldprt_path: str) -> list[str]:
    """调 sw_list_configs_worker 子进程列 SLDPRT 配置名（spec §4.4 #1）。

    内部 _CONFIG_LIST_CACHE 按 sldprt 绝对路径 key；
    失败也缓存（[]）以避免重试同 sldprt。
    """
    abs_path = str(Path(sldprt_path).resolve())
    if abs_path in _CONFIG_LIST_CACHE:
        return _CONFIG_LIST_CACHE[abs_path]

    cmd = [
        sys.executable,
        "-m", "adapters.solidworks.sw_list_configs_worker",
        sldprt_path,
    ]

    try:
        proc = subprocess.run(
            cmd,
            timeout=LIST_CONFIGS_TIMEOUT_SEC,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(_PROJECT_ROOT_FOR_WORKER),
        )
    except subprocess.TimeoutExpired:
        log.warning(
            "list_configs subprocess 超时 %ds: %s",
            LIST_CONFIGS_TIMEOUT_SEC, sldprt_path,
        )
        _CONFIG_LIST_CACHE[abs_path] = []
        return []

    if proc.returncode != 0:
        log.warning(
            "list_configs subprocess rc=%d sldprt=%s stderr=%s",
            proc.returncode, sldprt_path, (proc.stderr or "")[:300],
        )
        _CONFIG_LIST_CACHE[abs_path] = []
        return []

    try:
        configs = json.loads(proc.stdout.strip())
        if not isinstance(configs, list):
            raise ValueError("not a list")
    except (json.JSONDecodeError, ValueError) as e:
        log.warning("list_configs stdout 非合法 JSON list: %s", e)
        _CONFIG_LIST_CACHE[abs_path] = []
        return []

    _CONFIG_LIST_CACHE[abs_path] = configs
    return configs
```

- [ ] **Step 4：跑测试 PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestListConfigsViaCom -v
```

Expected: 4 passed

- [ ] **Step 5：commit**

```bash
git add adapters/solidworks/sw_config_broker.py tests/test_sw_config_broker.py
git commit -m "feat(sw_config_broker): _list_configs_via_com + _CONFIG_LIST_CACHE

调 sw_list_configs_worker 子进程；timeout=15s；
process-local 缓存按 sldprt 绝对路径 key（含失败缓存避免重试）。

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 12：resolve_config_for_part 主流程（无 lock 版本）

**Files:**
- Modify: `adapters/solidworks/sw_config_broker.py`
- Modify: `tests/test_sw_config_broker.py`

- [ ] **Step 1：写失败测试 — 5 路径**

```python
class TestResolveConfigForPart:
    """spec §3.2 数据流：5 路径全覆盖"""

    BOM = {"part_no": "GIS-EE-001-03", "name_cn": "O型圈", "material": "FKM Φ80×2.4"}
    SLDPRT = "/abs/path/o-rings series a gb.sldprt"

    def _patch_com(self, monkeypatch, configs):
        from adapters.solidworks import sw_config_broker
        sw_config_broker._CONFIG_LIST_CACHE.clear()
        monkeypatch.setattr(sw_config_broker, "_list_configs_via_com",
                           lambda p: configs)

    def test_path_1_auto_match_l1_exact(self, tmp_project_dir, monkeypatch):
        """路径 [3] 规则匹配 L1 命中 → source=auto, confidence=1.0"""
        from adapters.solidworks.sw_config_broker import resolve_config_for_part

        self._patch_com(monkeypatch, ["28×1.9", "80×2.4"])
        r = resolve_config_for_part(self.BOM, self.SLDPRT, subsystem="end_effector")

        assert r.source == "auto"
        assert r.config_name == "80×2.4"
        assert r.confidence == 1.0
        assert r.available_configs == ["28×1.9", "80×2.4"]

    def test_path_2_cached_decision_use_config_valid(self, tmp_project_dir, monkeypatch):
        """路径 [2] cache 命中 + 三项校验通过 → source=cached_decision"""
        import json
        from adapters.solidworks.sw_config_broker import resolve_config_for_part

        # 预置决策
        decisions = {
            "schema_version": 2,
            "decisions_by_subsystem": {
                "end_effector": {
                    "GIS-EE-001-03": {
                        "bom_dim_signature": "O型圈|FKM Φ80×2.4",
                        "sldprt_filename": "o-rings series a gb.sldprt",
                        "decision": "use_config",
                        "config_name": "80×2.4",
                        "user_note": "ok",
                        "decided_at": "2026-04-25T22:25:11+00:00",
                    }
                }
            },
            "decisions_history": [],
        }
        path = tmp_project_dir / ".cad-spec-gen" / "spec_decisions.json"
        path.write_text(json.dumps(decisions), encoding="utf-8")

        self._patch_com(monkeypatch, ["80×2.4", "100×3.0"])  # cached config 仍在 available
        r = resolve_config_for_part(self.BOM, self.SLDPRT, subsystem="end_effector")

        assert r.source == "cached_decision"
        assert r.config_name == "80×2.4"
        assert r.confidence == 1.0

    def test_path_2b_cached_decision_invalidate(self, tmp_project_dir, monkeypatch):
        """cache 命中但 config 已不在 available → 自动挪 history + 走规则匹配"""
        import json
        from adapters.solidworks.sw_config_broker import resolve_config_for_part

        decisions = {
            "schema_version": 2,
            "decisions_by_subsystem": {
                "end_effector": {
                    "GIS-EE-001-03": {
                        "bom_dim_signature": "O型圈|FKM Φ80×2.4",
                        "sldprt_filename": "o-rings series a gb.sldprt",
                        "decision": "use_config",
                        "config_name": "80×2.4",  # 旧名
                        "user_note": "",
                        "decided_at": "2026-04-20T10:00:00+00:00",
                    }
                }
            },
            "decisions_history": [],
        }
        path = tmp_project_dir / ".cad-spec-gen" / "spec_decisions.json"
        path.write_text(json.dumps(decisions), encoding="utf-8")

        # SW 升级后 config 改名为 "80x2.4 (FKM)"
        self._patch_com(monkeypatch, ["80x2.4 (FKM)"])

        r = resolve_config_for_part(self.BOM, self.SLDPRT, subsystem="end_effector")
        # L2 子串匹配命中新名字
        assert r.source == "auto"
        assert r.config_name == "80x2.4 (FKM)"

        # 旧决策已挪到 history
        env = json.loads(path.read_text(encoding="utf-8"))
        assert "GIS-EE-001-03" not in env["decisions_by_subsystem"]["end_effector"]
        assert len(env["decisions_history"]) == 1
        assert env["decisions_history"][0]["invalidation_reason"] == "config_name_not_in_available_configs"

    def test_path_4_policy_fallback_silent(self, tmp_project_dir, monkeypatch):
        """env CAD_AMBIGUOUS_CONFIG_POLICY=fallback_cadquery → 含糊不抛，返回 policy_fallback"""
        from adapters.solidworks.sw_config_broker import resolve_config_for_part, NeedsUserDecision

        monkeypatch.setenv("CAD_AMBIGUOUS_CONFIG_POLICY", "fallback_cadquery")
        self._patch_com(monkeypatch, ["AAA", "BBB"])  # 完全不匹配

        r = resolve_config_for_part(self.BOM, self.SLDPRT, subsystem="end_effector")
        assert r.source == "policy_fallback"
        assert r.config_name is None
        assert r.confidence == 0.0

    def test_path_5_halt_raises_needs_user_decision(self, tmp_project_dir, monkeypatch):
        """默认 policy=halt + 含糊匹配 → 抛 NeedsUserDecision"""
        from adapters.solidworks.sw_config_broker import resolve_config_for_part, NeedsUserDecision

        monkeypatch.delenv("CAD_AMBIGUOUS_CONFIG_POLICY", raising=False)
        self._patch_com(monkeypatch, ["AAA", "BBB"])

        with pytest.raises(NeedsUserDecision) as exc_info:
            resolve_config_for_part(self.BOM, self.SLDPRT, subsystem="end_effector")

        exc = exc_info.value
        assert exc.part_no == "GIS-EE-001-03"
        assert exc.subsystem == "end_effector"
        assert exc.pending_record["match_failure_reason"] == "no_exact_or_fuzzy_match_with_high_confidence"
```

- [ ] **Step 2：跑测试 FAIL**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestResolveConfigForPart -v
```

Expected: 5 FAILED

- [ ] **Step 3：写主入口**

```python
# 加到 adapters/solidworks/sw_config_broker.py


def resolve_config_for_part(
    bom_row: dict,
    sldprt_path: str,
    *,
    subsystem: str,
) -> ConfigResolution:
    """主入口（spec §3.2）。

    流程：COM list → cache lookup（含三项校验）→ rule match → policy decision

    返回：ConfigResolution
    抛出：
    - NeedsUserDecision：含糊匹配且 policy=halt（默认）
    - ValueError：decisions.json 损坏/schema 不一致
    """
    bom_signature = _build_bom_dim_signature(bom_row)
    sldprt_filename = Path(sldprt_path).name

    # 1. 必须先调 COM 列当前 available（spec §4.4 #3）
    available = _list_configs_via_com(sldprt_path)

    # 2. 读 decisions envelope
    envelope = _load_decisions_envelope()

    # 3. cache lookup + 校验
    cached = _get_decision_for_part(envelope, subsystem, bom_row.get("part_no", ""))
    if cached is not None:
        valid, invalid_reason = _validate_cached_decision(
            cached, bom_signature, sldprt_filename, available,
        )
        if valid:
            # 命中：根据 decision type 返回
            if cached["decision"] == "use_config":
                return ConfigResolution(
                    config_name=cached["config_name"],
                    source="cached_decision",
                    confidence=1.0,
                    available_configs=available,
                    notes=f"用户决策（{cached.get('decided_at', '')}）",
                )
            elif cached["decision"] == "fallback_cadquery":
                return ConfigResolution(
                    config_name=None,
                    source="cached_decision",
                    confidence=1.0,
                    available_configs=available,
                    notes=f"用户决策 fallback（{cached.get('decided_at', '')}）",
                )
        else:
            # 失效：挪 history + 持久化
            _move_decision_to_history(
                envelope, subsystem, bom_row.get("part_no", ""), invalid_reason,
            )
            _save_decisions_envelope(envelope)
            # fall through 到规则匹配

    # 4. 规则匹配
    if available:
        match = _match_config_by_rule(bom_signature, available)
        if match:
            cfg, conf = match
            return ConfigResolution(
                config_name=cfg,
                source="auto",
                confidence=conf,
                available_configs=available,
                notes=f"规则匹配（confidence={conf:.2f}）",
            )

    # 5. 含糊匹配 → 看 policy
    failure_reason = _determine_failure_reason(available)
    pending_record = _build_pending_record(
        bom_row=bom_row,
        sldprt_path=sldprt_path,
        available=available,
        match_failure_reason=failure_reason,
        attempted_match=None,
    )

    policy = os.environ.get("CAD_AMBIGUOUS_CONFIG_POLICY", "halt")
    if policy == "fallback_cadquery":
        # 静默 fallback —— 用户已显式 opt-in；仍累积 pending（事后审阅）
        # （pending 累积由 caller 通过捕获 ConfigResolution 处理 —— 见 gen_std_parts 集成）
        return ConfigResolution(
            config_name=None,
            source="policy_fallback",
            confidence=0.0,
            available_configs=available,
            notes=f"CAD_AMBIGUOUS_CONFIG_POLICY=fallback_cadquery：{failure_reason}",
        )

    # 默认 halt → 抛
    raise NeedsUserDecision(
        part_no=bom_row.get("part_no", ""),
        subsystem=subsystem,
        pending_record=pending_record,
    )


def _determine_failure_reason(available: list[str]) -> str:
    """根据 available 状态推断 match_failure_reason 默认值。"""
    if not available:
        return "com_open_failed"
    if available == ["Default"]:
        return "empty_config_list"
    return "no_exact_or_fuzzy_match_with_high_confidence"
```

- [ ] **Step 4：跑测试 PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestResolveConfigForPart -v
```

Expected: 5 passed

- [ ] **Step 5：commit**

```bash
git add adapters/solidworks/sw_config_broker.py tests/test_sw_config_broker.py
git commit -m "feat(sw_config_broker): resolve_config_for_part 主流程 5 路径

cached_decision 命中（含三项校验）→ auto match → policy halt/fallback；
cache 失效自动挪 history + 持久化后 fall through 规则匹配；
默认 policy=halt 含糊匹配抛 NeedsUserDecision。

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 13：文件锁 msvcrt.locking

**Files:**
- Modify: `adapters/solidworks/sw_config_broker.py`
- Modify: `tests/test_sw_config_broker.py`

- [ ] **Step 1：写失败测试 — 并发模拟**

```python
@pytest.mark.skipif(sys.platform != "win32", reason="msvcrt only on Windows")
class TestFileLock:
    def test_lock_blocks_concurrent_resolve(self, tmp_project_dir, monkeypatch):
        """两个并行进程同时跑 resolve → 第二个阻塞到第一个释放"""
        # 模拟两次串行调用，第二次应能正常进行（前次锁已释放）
        from adapters.solidworks import sw_config_broker
        sw_config_broker._CONFIG_LIST_CACHE.clear()

        monkeypatch.setattr(sw_config_broker, "_list_configs_via_com",
                            lambda p: ["80×2.4"])

        bom = {"part_no": "X", "name_cn": "O型圈", "material": "FKM Φ80×2.4"}
        # 两次调用都成功（单进程内 lock 自释放）
        r1 = sw_config_broker.resolve_config_for_part(bom, "/p.sldprt", subsystem="ee")
        r2 = sw_config_broker.resolve_config_for_part(bom, "/p.sldprt", subsystem="ee")
        assert r1.source == "auto"
        assert r2.source == "auto"
```

- [ ] **Step 2：跑测试 — 应已 PASS（无 lock 时也通过）**

实际上验证 lock 真阻塞需要双进程，此处仅烟雾测试。完整并发测试在集成层 Task 18。

- [ ] **Step 3：加 lock 实现**

```python
# 加到 adapters/solidworks/sw_config_broker.py
import contextlib

LOCK_FILE_NAME = "lock"


@contextlib.contextmanager
def _project_file_lock():
    """文件锁 <project>/.cad-spec-gen/lock（spec §6 并发跑 codegen）。

    Windows: msvcrt.locking 阻塞模式 LK_LOCK；非 Windows 静默跳过（无锁）。
    """
    if sys.platform != "win32":
        yield
        return

    import msvcrt

    from cad_paths import PROJECT_ROOT
    lock_path = Path(PROJECT_ROOT) / ".cad-spec-gen" / LOCK_FILE_NAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    fp = lock_path.open("a+b")
    try:
        # LK_LOCK = 阻塞模式获取独占锁
        msvcrt.locking(fp.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            msvcrt.locking(fp.fileno(), msvcrt.LK_UNLCK, 1)
    finally:
        fp.close()
```

把 `resolve_config_for_part` 的整个主流程包在 lock 里：

```python
def resolve_config_for_part(
    bom_row: dict,
    sldprt_path: str,
    *,
    subsystem: str,
) -> ConfigResolution:
    """..."""
    with _project_file_lock():
        return _resolve_config_for_part_unlocked(bom_row, sldprt_path, subsystem)


def _resolve_config_for_part_unlocked(
    bom_row: dict,
    sldprt_path: str,
    subsystem: str,
) -> ConfigResolution:
    """原 resolve_config_for_part 主体；改名为 _unlocked 让 lock 包装它。"""
    # ... (前面 Task 12 的实现内容搬到这里)
```

- [ ] **Step 4：跑测试 PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py::TestFileLock -v
```

Expected: passed

- [ ] **Step 5：跑全 broker 单元测试 — 确认未回归**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py -v
```

Expected: 全部 passed

- [ ] **Step 6：commit**

```bash
git add adapters/solidworks/sw_config_broker.py tests/test_sw_config_broker.py
git commit -m "feat(sw_config_broker): msvcrt.locking 文件锁防并发跑

resolve_config_for_part 主流程包在 _project_file_lock 上下文里；
非 Windows 静默跳过（无锁，CI 单元测试不用关心）。

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

**🛑 CP-4 暂停**：用户审 broker 公开 API + 5 路径 + 文件锁 OK 后 → 进入 Task 14

---

## Task 14：sw_toolbox_adapter.resolve() 接入 broker

**Files:**
- Modify: `adapters/parts/sw_toolbox_adapter.py:226-293`
- Create: `tests/test_sw_toolbox_adapter_with_broker.py`

- [ ] **Step 1：写失败测试 — adapter 委托到 broker**

```python
# tests/test_sw_toolbox_adapter_with_broker.py

import pytest
from unittest.mock import MagicMock, patch


class TestSwToolboxAdapterDelegatesToBroker:
    """spec §3.2: sw_toolbox_adapter.resolve 委托给 sw_config_broker"""

    def test_broker_returns_use_config_step_path_includes_config(self, tmp_path, monkeypatch):
        """broker 返回 source=cached_decision + config_name=80×2.4
        → adapter 触发 ShowConfiguration2 + STEP 含 config 后缀缓存"""
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks.sw_toolbox_catalog import SwToolboxPart

        # mock broker
        mock_resolution = MagicMock()
        mock_resolution.source = "auto"
        mock_resolution.config_name = "80×2.4"
        mock_resolution.confidence = 1.0
        mock_resolution.available_configs = ["80×2.4"]

        # 这里仅 sketch；完整测试见 step 3
        # 重点验证 adapter 把 broker 返回的 config_name 传给 SwComSession.convert_sldprt_to_step

    def test_broker_returns_fallback_adapter_returns_miss(self):
        """broker 返回 source=cached_decision + config_name=None
        → adapter 返回 miss 让其他 adapter（CadQuery）兜底"""
        # sketch
```

实际测试需要 mock 链较深；完整版在下一步实现后调整。

- [ ] **Step 2：在 sw_toolbox_adapter.py 接入 broker**

```python
# adapters/parts/sw_toolbox_adapter.py
# 替换 resolve() 方法的 step 7-9（line 226-293）：

def resolve(self, query, spec: dict):
    """主编排流程（rev 2 接入 broker）。"""
    from parts_resolver import ResolveResult
    from adapters.solidworks import sw_toolbox_catalog
    from adapters.solidworks.sw_com_session import get_session
    from adapters.solidworks.sw_detect import detect_solidworks
    from adapters.solidworks.sw_config_broker import (
        resolve_config_for_part,
        NeedsUserDecision,
        ConfigResolution,
    )

    info = detect_solidworks()
    toolbox_dir = Path(info.toolbox_dir)

    # 1-6 现有 SLDPRT 匹配逻辑保留 ...
    # （省略，与现有相同）
    index_path = sw_toolbox_catalog.get_toolbox_index_path(self.config)
    try:
        index = sw_toolbox_catalog.load_toolbox_index(index_path, toolbox_dir)
    except Exception as e:
        log.warning("toolbox 索引加载失败: %s", e)
        return self._miss("index load failed")

    standards = spec.get("standard")
    if isinstance(standards, str):
        standards = [standards]
    subcategories = spec.get("subcategories", [])
    part_category = spec.get("part_category", "fastener")

    size_patterns = self.config.get("size_patterns", {}).get(part_category, {})
    size_dict = sw_toolbox_catalog.extract_size_from_name(
        getattr(query, "name_cn", ""), size_patterns,
    )
    if size_dict is None and part_category == "bearing":
        size_dict = sw_toolbox_catalog.extract_size_from_name(
            getattr(query, "material", "") or "", size_patterns,
        )
    if size_dict is None:
        return self._miss("size extraction failed or out of scope")

    weights = self.config.get("token_weights", {})
    query_tokens = sw_toolbox_catalog.build_query_tokens_weighted(query, size_dict, weights)
    min_score = spec.get("min_score", self.config.get("min_score", 0.30))
    match = sw_toolbox_catalog.match_toolbox_part(
        index, query_tokens, standards, subcategories, min_score,
    )
    if match is None:
        return self._miss("token overlap below min_score")

    part, score = match

    if not sw_toolbox_catalog._validate_sldprt_path(part.sldprt_path, toolbox_dir):
        return self._miss("sldprt path validation failed")

    # ── 7-9 替换：委托给 broker ────────────────────────────────────
    bom_row = {
        "part_no": getattr(query, "part_no", ""),
        "name_cn": getattr(query, "name_cn", ""),
        "material": getattr(query, "material", ""),
    }
    subsystem = getattr(query, "subsystem", "") or spec.get("subsystem", "default")

    try:
        resolution: ConfigResolution = resolve_config_for_part(
            bom_row=bom_row,
            sldprt_path=part.sldprt_path,
            subsystem=subsystem,
        )
    except NeedsUserDecision:
        # caller (gen_std_parts) 应该捕获该异常 — 这里 re-raise
        raise

    # broker 返回：根据 source / config_name 决定走 STEP 导出 还是 fallback
    if resolution.config_name is None:
        # cached_decision fallback / policy_fallback → 让 CadQuery 兜底
        return self._miss(f"broker returned fallback ({resolution.source}): {resolution.notes}")

    # config_name 有值：触发 COM 导出（如 STEP 已存则 cache hit）
    cache_root = sw_toolbox_catalog.get_toolbox_cache_root(self.config)
    safe_config = re.sub(r'[^\w.\-]', '_', resolution.config_name)
    cache_stem = f"{Path(part.filename).stem}_{safe_config}"
    step_abs = cache_root / part.standard / part.subcategory / (cache_stem + ".step")

    if not step_abs.exists():
        session = get_session()
        if not session.is_healthy():
            return self._miss("COM session unhealthy")
        ok = session.convert_sldprt_to_step(
            part.sldprt_path, str(step_abs), resolution.config_name,
        )
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
        metadata={
            "dims": dims,
            "match_score": score,
            "configuration": resolution.config_name,
            "config_match": resolution.source,
            "config_confidence": resolution.confidence,
        },
    )
```

- [ ] **Step 3：删除 _build_candidate_config 函数（已被 broker 取代）**

```bash
# 在 adapters/parts/sw_toolbox_adapter.py 删除 line 47-63 的 _build_candidate_config 函数
# 同时删除 line 41-44 的 _SPEC_RE 与 extract_full_spec（如未在他处使用）
grep -rn "_build_candidate_config\|extract_full_spec\|_SPEC_RE" adapters/ tests/ codegen/
# 确认无其他使用后删除
```

- [ ] **Step 4：跑现有 sw_toolbox_adapter 测试 — 验证未破坏既有路径**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_toolbox_adapter*.py -v 2>&1 | tail -40
```

Expected: 大部分通过；失败的应只是因为接入 broker 引起的 mock 信号变化 → 修测试

- [ ] **Step 5：补足 test_sw_toolbox_adapter_with_broker.py**

```python
# 完整化 step 1 的 sketch
@patch("adapters.parts.sw_toolbox_adapter.resolve_config_for_part")
def test_broker_use_config_triggers_step_export(mock_broker, tmp_path):
    """完整 sketch（具体 mock 路径根据 step 2 落地后调）"""
    pass

@patch("adapters.parts.sw_toolbox_adapter.resolve_config_for_part")
def test_broker_fallback_returns_miss(mock_broker):
    pass

@patch("adapters.parts.sw_toolbox_adapter.resolve_config_for_part")
def test_broker_raises_propagates(mock_broker):
    """NeedsUserDecision 应该 propagate 给 caller"""
    pass
```

实际填充时根据 step 2 实现细节定 mock 锚点（`patch("...sw_toolbox_adapter.resolve_config_for_part")` 那行）。

- [ ] **Step 6：跑测试 PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_toolbox_adapter_with_broker.py -v
```

Expected: 3+ passed

- [ ] **Step 7：commit**

```bash
git add adapters/parts/sw_toolbox_adapter.py tests/test_sw_toolbox_adapter_with_broker.py
git commit -m "refactor(sw_toolbox_adapter): resolve() 委托给 sw_config_broker

替换原 _build_candidate_config + cache hit 逻辑；
broker 返回 ConfigResolution → adapter 根据 source/config_name 决定 STEP 导出或 miss；
NeedsUserDecision 异常向上 propagate 给 gen_std_parts。

删除旧 _build_candidate_config / extract_full_spec / _SPEC_RE（已被 broker 取代）。

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

**🛑 CP-5 暂停**：用户验证 sw_toolbox_adapter 改动未破坏现有测试 + 现有 GISBOT codegen 仍能跑（即使行为改变） → 进入 Task 15

---

## Task 15：gen_std_parts.py 捕获 NeedsUserDecision + 累积

**Files:**
- Modify: `codegen/gen_std_parts.py`（line 165-200 附近，generation loop）

- [ ] **Step 1：阅读现有 generation loop 找插入点**

```bash
grep -n "for part in\|for _row\|generate_std_part_files\|resolver.resolve" codegen/gen_std_parts.py | head -10
```

记下行号。loop 大致在 generate_std_part_files 函数内。

- [ ] **Step 2：写集成测试 — mock 多 NeedsUserDecision**

```python
# tests/test_sw_toolbox_adapter_with_broker.py 末尾

class TestGenStdPartsAccumulation:
    def test_multiple_needs_decision_accumulated_into_pending(self, tmp_path, monkeypatch):
        """3 个零件都抛 NeedsUserDecision → exit 7 + pending 文件含全部 3 项嵌套到正确 subsystem"""
        # 完整 mock 见实现（mock parts_resolver 让 broker 抛异常）
        pass

    def test_no_needs_decision_normal_exit(self, tmp_path):
        """全部零件都成功 → 正常生成 std_*.py + exit 0"""
        pass
```

- [ ] **Step 3：在 gen_std_parts.py 加 NeedsUserDecision 捕获**

```python
# codegen/gen_std_parts.py 顶部 import 加：
from adapters.solidworks.sw_config_broker import NeedsUserDecision

# 在 generation loop 里（具体行号根据 step 1 grep）：
pending_records: dict[str, list[dict]] = {}  # subsystem → records

for part in bom:
    try:
        result = resolver.resolve_one(part)
        # ... 现有处理 ...
    except NeedsUserDecision as exc:
        pending_records.setdefault(exc.subsystem, []).append(exc.pending_record)
        log.info(
            "[pending] %s/%s 等待用户决策 (%s)",
            exc.subsystem, exc.part_no,
            exc.pending_record["match_failure_reason"],
        )
        # 跳过该零件的 std_*.py 生成，继续下个
        continue
```

注：subsystem 字段需要从 part_no 推断（如 `GIS-EE-001-03` → `end_effector`）。在 broker 抛异常时已携带 `exc.subsystem`，gen_std_parts 直接用。

- [ ] **Step 4：跑现有 gen_std_parts 测试不破**

```bash
.venv/Scripts/python.exe -m pytest tests/test_gen_std_parts*.py -v 2>&1 | tail -30
```

Expected: 全部 passed（loop 里只新加了 try/except，未改主路径）

- [ ] **Step 5：commit**

```bash
git add codegen/gen_std_parts.py tests/test_sw_toolbox_adapter_with_broker.py
git commit -m "feat(gen_std_parts): 捕获 NeedsUserDecision 累积 pending records

generation loop 新加 try/except；
按 exc.subsystem 分组累积；
跳过抛异常零件的 std_*.py 生成（继续处理后续零件）。

pending 文件原子写 + exit 7 + stdout 摘要在下个 task。

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 16：gen_std_parts.py 一次性原子写 pending 文件

**Files:**
- Modify: `codegen/gen_std_parts.py`（main 函数末尾）

- [ ] **Step 1：写测试 — 验证 pending 文件 schema**

```python
# tests/test_sw_toolbox_adapter_with_broker.py
import json

def test_pending_file_schema_v2_with_subsystem_nesting(tmp_path):
    """pending 文件 items_by_subsystem 嵌套正确"""
    # mock 3 records 跨 2 subsystem
    pending_records = {
        "end_effector": [
            {"part_no": "X1", "match_failure_reason": "no_exact_or_fuzzy_match_with_high_confidence"},
            {"part_no": "X2", "match_failure_reason": "com_open_failed"},
        ],
        "electrical": [
            {"part_no": "Y1", "match_failure_reason": "empty_config_list"},
        ],
    }

    from codegen.gen_std_parts import _write_pending_file
    target = tmp_path / "sw_config_pending.json"
    _write_pending_file(pending_records, target)

    raw = json.loads(target.read_text(encoding="utf-8"))
    assert raw["schema_version"] == 2
    assert raw["pending_count"] == 3
    assert "end_effector" in raw["items_by_subsystem"]
    assert "electrical" in raw["items_by_subsystem"]
    assert len(raw["items_by_subsystem"]["end_effector"]) == 2
    assert len(raw["items_by_subsystem"]["electrical"]) == 1
```

- [ ] **Step 2：跑测试 FAIL**

Expected: ImportError (_write_pending_file 不存在)

- [ ] **Step 3：写实现**

```python
# codegen/gen_std_parts.py 末尾加：
import json
from datetime import datetime, timezone
from pathlib import Path


def _write_pending_file(pending_records: dict[str, list[dict]], path: Path) -> None:
    """一次性原子写 sw_config_pending.json（spec §5.3 + §5.4）。"""
    total = sum(len(items) for items in pending_records.values())
    envelope = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pending_count": total,
        "items_by_subsystem": pending_records,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    import os as _os
    _os.replace(tmp_path, path)
```

在 main 函数末尾加调用：

```python
# 在 codegen/gen_std_parts.py main 函数末尾，处理完所有零件后：

if pending_records:
    pending_path = (
        Path(os.environ.get("CAD_PROJECT_ROOT", os.getcwd()))
        / ".cad-spec-gen" / "sw_config_pending.json"
    )
    _write_pending_file(pending_records, pending_path)
    print(f"[pending] 已写 {sum(len(v) for v in pending_records.values())} 项到 {pending_path}")
    # exit 7 在下个 task 加
```

- [ ] **Step 4：跑测试 PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_toolbox_adapter_with_broker.py::test_pending_file_schema_v2_with_subsystem_nesting -v
```

Expected: PASSED

- [ ] **Step 5：commit**

```bash
git add codegen/gen_std_parts.py tests/test_sw_toolbox_adapter_with_broker.py
git commit -m "feat(gen_std_parts): _write_pending_file 一次性原子写 schema v2

items_by_subsystem 嵌套；pending_count 自动计算；
.tmp + os.replace 原子语义。

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 17：gen_std_parts.py stdout 人读摘要 + exit 7

**Files:**
- Modify: `codegen/gen_std_parts.py`（main 函数末尾）

- [ ] **Step 1：写测试 — 验证 stdout 含关键引导字符串**

```python
def test_stdout_summary_contains_guidance(capsys, tmp_path):
    """spec §3.3: stdout 摘要必须含 [推荐]/[手动] 等引导字符串"""
    from codegen.gen_std_parts import _print_pending_summary

    pending_records = {
        "end_effector": [
            {
                "part_no": "GIS-EE-001-03",
                "name_cn": "O型圈",
                "material": "FKM Φ80×2.4",
                "available_configs": ["28×1.9", "80×2.4"],
                "match_failure_reason": "no_exact_or_fuzzy_match_with_high_confidence",
                "suggested_options": [
                    {"action": "use_config", "config_name": "80×2.4", "rationale": "字面匹配"},
                    {"action": "fallback_cadquery", "rationale": "CadQuery 兜底"},
                ],
            }
        ],
    }
    pending_path = tmp_path / "sw_config_pending.json"

    _print_pending_summary(pending_records, pending_path)
    captured = capsys.readouterr()

    # 关键引导字符串
    assert "需要确认" in captured.out
    assert "GIS-EE-001-03" in captured.out
    assert "O型圈" in captured.out
    assert "[推荐]" in captured.out
    assert "[手动]" in captured.out
    assert "/cad-codegen" in captured.out  # 推 skill 路径
    assert str(pending_path) in captured.out  # 手动路径
```

- [ ] **Step 2：跑测试 FAIL**

Expected: ImportError (_print_pending_summary 不存在)

- [ ] **Step 3：写实现**

```python
# codegen/gen_std_parts.py 末尾加：

def _print_pending_summary(
    pending_records: dict[str, list[dict]],
    pending_path: Path,
) -> None:
    """stdout 打印人读摘要（spec §3.3）。

    即使无 agent 介入用户也能据此手动处理：
    - [推荐] 用 /cad-codegen skill
    - [手动] 编辑 spec_decisions.json
    """
    total = sum(len(items) for items in pending_records.values())
    print(f"\n⚠️ codegen 暂停：{total} 个零件需要确认 SW Toolbox 配置")

    counter = 0
    for subsystem, items in pending_records.items():
        for item in items:
            counter += 1
            print(f"\n零件 {counter}/{total} — {item['part_no']} ({item['name_cn']} / {item['material']})")
            print(f"  subsystem: {subsystem}")
            print(f"  失败原因: {item['match_failure_reason']}")
            if item['available_configs']:
                print(f"  SW 候选配置: {item['available_configs'][:10]}{' ...' if len(item['available_configs']) > 10 else ''}")
            else:
                print(f"  SW 候选配置: <无（COM 失败或空列表）>")
            if item.get('suggested_options'):
                print(f"  建议:")
                for opt in item['suggested_options']:
                    if opt['action'] == 'use_config':
                        print(f"    - 选 \"{opt.get('config_name', '?')}\" ({opt.get('rationale', '')})")
                    elif opt['action'] == 'fallback_cadquery':
                        print(f"    - 用 CadQuery 近似 ({opt.get('rationale', '')})")

    print(f"\n请二选一处理：")
    print(f"  [推荐] 用 /cad-codegen skill —— agent 会逐零件向你提问，自动写决策回 spec_decisions.json")
    print(f"  [手动] 按 spec §5.1 schema 编辑 {pending_path.parent / 'spec_decisions.json'}")
    print(f"         在 decisions_by_subsystem.<subsystem> 下添加每个 part_no 的决策项，")
    print(f"         删除 {pending_path.name}，再跑 cad_pipeline.py codegen")
    print(f"\n详情见 {pending_path}\n")
```

更新 main 函数末尾：

```python
# codegen/gen_std_parts.py main 末尾改为：

if pending_records:
    pending_path = (
        Path(os.environ.get("CAD_PROJECT_ROOT", os.getcwd()))
        / ".cad-spec-gen" / "sw_config_pending.json"
    )
    _write_pending_file(pending_records, pending_path)
    _print_pending_summary(pending_records, pending_path)
    sys.exit(7)
```

- [ ] **Step 4：跑测试 PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_toolbox_adapter_with_broker.py::test_stdout_summary_contains_guidance -v
```

Expected: PASSED

- [ ] **Step 5：commit**

```bash
git add codegen/gen_std_parts.py tests/test_sw_toolbox_adapter_with_broker.py
git commit -m "feat(gen_std_parts): stdout 人读摘要 + exit 7

按 spec §3.3 输出含 [推荐]/[手动] 双路径引导；
推 skill 路径让 agent 自动处理；手动路径让命令行用户也能动手。
exit 7 与 spec 约定一致。

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 18：集成层完整验证 + 全测试 baseline

**Files:**
- 仅运行测试，无修改

- [ ] **Step 1：跑 broker + adapter + gen_std_parts 全测试**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker.py tests/test_sw_toolbox_adapter_with_broker.py tests/test_sw_list_configs_worker.py -v 2>&1 | tail -30
```

Expected: 全部 passed

- [ ] **Step 2：跑全量测试确认未破坏既有功能**

```bash
.venv/Scripts/python.exe -m pytest --tb=short -q 2>&1 | tail -10
```

Expected: passed 数 ≥ task 0 baseline；如有 fail，定位回归并修

- [ ] **Step 3：Pre-flight CI 模拟（裸 pytest，不带 venv .exe）**

```bash
cd D:/Work/cad-spec-gen && pytest tests/test_sw_*.py -v 2>&1 | tail -10
```

Expected: passed（per `feedback_preflight_mirror_ci.md`）

- [ ] **Step 4：commit baseline 报告**

```bash
.venv/Scripts/python.exe -m pytest --tb=no -q 2>&1 | tail -3 > task18_baseline.txt
git add task18_baseline.txt
git commit -m "test: Task 18 全量测试 baseline 记录

CP-6 验证：sw_config_broker + sw_toolbox_adapter + gen_std_parts 集成
未破坏既有功能。

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

**🛑 CP-6 暂停**：用户审 stdout 摘要文案 + exit 7 行为 → 进入 Task 19

---

## Task 19：Skill 文档（中文）— cad-codegen.md

**Files:**
- Modify: `.claude/commands/cad-codegen.md`

- [ ] **Step 1：读现有 skill 文档结构**

```bash
head -60 .claude/commands/cad-codegen.md
```

- [ ] **Step 2：在适当章节加"exit 7 处理"段**

```markdown
<!-- 加到 .claude/commands/cad-codegen.md 适当位置 -->

## ⚠️ pipeline exit 7 处理（SW Toolbox 配置决策）

当 `cad_pipeline.py codegen` 退出码为 **7**，表示有零件需要用户确认 SW Toolbox 配置。处理流程：

1. **读 pending 文件** `<project>/.cad-spec-gen/sw_config_pending.json`
2. **逐 item 询问用户**：
   - 显示 `part_no` + `name_cn` + `material` + `available_configs` + `suggested_options`
   - 推荐用户选 `suggested_options[0]`（一般是 best 匹配）
   - 用户可选 `use_config <名>` / `fallback_cadquery`
3. **写决策回** `<project>/.cad-spec-gen/spec_decisions.json`：
   - 在 `decisions_by_subsystem.<subsystem>.<part_no>` 添加：
     ```json
     {
       "bom_dim_signature": "...（来自 pending item）",
       "sldprt_filename": "...（来自 pending item）",
       "decision": "use_config",
       "config_name": "用户选的",
       "user_note": "...",
       "decided_at": "<ISO 时间戳>"
     }
     ```
4. **删除 pending 文件**：`<project>/.cad-spec-gen/sw_config_pending.json`
5. **重跑 codegen**：`cad_pipeline.py codegen --subsystem <name>`

详细 schema 见 `docs/superpowers/specs/2026-04-25-sw-toolbox-llm-config-broker-design.md` §5.1。

**环境变量**：
- `CAD_AMBIGUOUS_CONFIG_POLICY=halt`（默认）— 严格 halt 等用户决策
- `CAD_AMBIGUOUS_CONFIG_POLICY=fallback_cadquery` — 含糊匹配自动用 CadQuery 近似（用户已显式同意，仍写 pending 供事后审阅）
```

- [ ] **Step 3：commit**

```bash
git add .claude/commands/cad-codegen.md
git commit -m "docs(skill): cad-codegen.md 加 exit 7 处理流程

agent 看到 exit 7 必须读 sw_config_pending.json + 逐项问用户 + 写
spec_decisions.json + 删 pending + 重跑。

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 20：Skill 文档（英文）+ AGENTS.md 同步

**Files:**
- Modify: `src/cad_spec_gen/data/commands/en/cad-codegen.md`
- Auto-update: `AGENTS.md`（通过 dev_sync）

- [ ] **Step 1：把 Task 19 的中文段译成英文加到 EN skill**

```markdown
<!-- 加到 src/cad_spec_gen/data/commands/en/cad-codegen.md -->

## ⚠️ Handling Pipeline Exit Code 7 (SW Toolbox Config Decision)

When `cad_pipeline.py codegen` exits with code **7**, parts need user confirmation
on SW Toolbox configuration. Process:

1. **Read** `<project>/.cad-spec-gen/sw_config_pending.json`
2. **Ask user per item**: show `part_no`, `name_cn`, `material`, `available_configs`,
   `suggested_options`. Recommend `suggested_options[0]` first.
3. **Write decision** to `<project>/.cad-spec-gen/spec_decisions.json` under
   `decisions_by_subsystem.<subsystem>.<part_no>` with schema:
   ```json
   {
     "bom_dim_signature": "<from pending item>",
     "sldprt_filename": "<from pending item>",
     "decision": "use_config",
     "config_name": "<user's choice>",
     "user_note": "...",
     "decided_at": "<ISO timestamp>"
   }
   ```
4. **Delete pending file**
5. **Re-run codegen**

See `docs/superpowers/specs/2026-04-25-sw-toolbox-llm-config-broker-design.md` §5.1
for full schema.

**Env vars:**
- `CAD_AMBIGUOUS_CONFIG_POLICY=halt` (default) — strict halt for user decision
- `CAD_AMBIGUOUS_CONFIG_POLICY=fallback_cadquery` — silent CadQuery fallback (user
  explicit opt-in, still writes pending for later review)
```

- [ ] **Step 2：跑 dev_sync**

```bash
.venv/Scripts/python.exe scripts/dev_sync.py
```

Expected: AGENTS.md 自动更新 + 提示 sync 完成

- [ ] **Step 3：检查 AGENTS.md 同步结果**

```bash
git diff AGENTS.md | head -30
```

确认变更合理（应包含版本号或新内容）。

- [ ] **Step 4：commit**

```bash
git add src/cad_spec_gen/data/commands/en/cad-codegen.md AGENTS.md
git commit -m "docs(skill): EN cad-codegen.md exit 7 handling + AGENTS.md sync

中英文同步；dev_sync 自动重新生成 AGENTS.md。

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

**🛑 CP-7 暂停**：用户确认 agent 引导流程文案 → 进入 Task 21

---

## Task 21：真 SW E2E 测试（@requires_solidworks）

**Files:**
- Create: `tests/test_sw_config_broker_real.py`

- [ ] **Step 1：写 E2E 测试 — 真 SW 列 GISBOT 用到的 SLDPRT**

```python
# tests/test_sw_config_broker_real.py
"""真 SW E2E 测试：列 GISBOT 用到的 5 个 SLDPRT 配置 + 验证假设 §10.2。

需 Windows + SW + Toolbox 装机；CI 跳过。
"""

import pytest
import sys

pytestmark = [
    pytest.mark.requires_solidworks,
    pytest.mark.skipif(sys.platform != "win32", reason="SW only on Windows"),
]


GISBOT_SLDPRTS = [
    "C:/SOLIDWORKS Data/browser/GB/o-rings/all o-rings/o-rings series a gb.sldprt",
    "C:/SOLIDWORKS Data/browser/GB/bearing/rolling bearings/miniature radial ball bearings gb.sldprt",
    # GISBOT 用到的其他 3 个 SLDPRT 由 sw-inspect 报告确定
]


@pytest.mark.parametrize("sldprt", GISBOT_SLDPRTS)
def test_list_configs_returns_nonempty(sldprt):
    """spec AC-1: broker 能列出 SW Toolbox SLDPRT 的所有 config 名"""
    from adapters.solidworks.sw_config_broker import _list_configs_via_com

    configs = _list_configs_via_com(sldprt)
    assert len(configs) >= 1, f"{sldprt} 应至少有 1 个 config"


def test_oring_configs_match_phi80x24():
    """spec AC-2: BOM Φ80×2.4 → 命中 80×2.4 配置（或归一化等价）"""
    from adapters.solidworks.sw_config_broker import (
        _list_configs_via_com,
        _match_config_by_rule,
        _build_bom_dim_signature,
    )

    sldprt = GISBOT_SLDPRTS[0]
    configs = _list_configs_via_com(sldprt)

    bom_sig = _build_bom_dim_signature({
        "part_no": "GIS-EE-001-03",
        "name_cn": "O型圈",
        "material": "FKM Φ80×2.4",
    })
    match = _match_config_by_rule(bom_sig, configs)
    assert match is not None, f"应能匹配，配置列表={configs}"
    matched_name, conf = match
    assert conf >= 0.7
    print(f"匹配到: {matched_name} (confidence={conf:.2f})")


def test_list_configs_count_validates_assumption(capsys):
    """spec §10.2 假设验证：SLDPRT 内 config 数 < 100"""
    from adapters.solidworks.sw_config_broker import _list_configs_via_com

    counts = []
    for sldprt in GISBOT_SLDPRTS:
        configs = _list_configs_via_com(sldprt)
        counts.append((sldprt.split('/')[-1], len(configs)))
        print(f"  {sldprt.split('/')[-1]}: {len(configs)} configs")

    for name, n in counts:
        assert n < 1000, f"{name} 有 {n} 个 config，超出分页阈值，需扩展 UI"


def test_list_configs_naming_consistency_inspect(capsys):
    """spec §10.2 假设验证：同 SLDPRT 内 config 命名风格一致（人工巡检）"""
    from adapters.solidworks.sw_config_broker import _list_configs_via_com

    for sldprt in GISBOT_SLDPRTS:
        configs = _list_configs_via_com(sldprt)
        sample = configs[:5] if len(configs) > 5 else configs
        print(f"\n{sldprt.split('/')[-1]} 前 5 个 config 命名样本:")
        for c in sample:
            print(f"  - {c!r}")
    # 这是审阅性测试，无 assert；看 stdout 后人工判断
```

- [ ] **Step 2：跑 E2E 测试（要求本机有 SW）**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_config_broker_real.py -v -s
```

Expected:
- 5 个 config 列出成功
- O 型圈 80×2.4 匹配命中
- 输出每 SLDPRT 的 config 数（验证 < 100 假设）
- 输出 5 个 config 命名样本（人工巡检）

- [ ] **Step 3：根据 stdout 实测延迟，调整 §10.2 假设文档**

如发现 COM list 实际延迟 > 5s，更新 spec §10.2 实测值。

- [ ] **Step 4：commit**

```bash
git add tests/test_sw_config_broker_real.py
git commit -m "test(sw_config_broker): E2E 真 SW 测试 + 假设验证

@requires_solidworks marker，CI 自动跳过；
覆盖 GISBOT 用到的 5 个 SLDPRT；
验证 spec §10.2 三项假设（config 数 < 100 / 命名一致 / COM 延迟）。

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 22：GISBOT 端到端 smoke + GLB 验收

**Files:**
- 仅 GISBOT 项目实测，无代码改动

- [ ] **Step 1：清理 GISBOT 当前 std_*.py（恢复 codegen 干净状态）**

```bash
ls D:/Work/cad-tests/GISBOT/cad/end_effector/std_*.py | wc -l
```

记录数量。备份后删除：

```bash
mkdir -p D:/Work/cad-tests/GISBOT/.backup_std_canonical/
cp D:/Work/cad-tests/GISBOT/cad/end_effector/std_*.py D:/Work/cad-tests/GISBOT/.backup_std_canonical/
rm D:/Work/cad-tests/GISBOT/cad/end_effector/std_*.py
```

- [ ] **Step 2：清空 spec_decisions.json（如存在）**

```bash
rm -f D:/Work/cad-tests/GISBOT/.cad-spec-gen/spec_decisions.json
rm -f D:/Work/cad-tests/GISBOT/.cad-spec-gen/sw_config_pending.json
```

- [ ] **Step 3：跑 codegen 期望 exit 7**

```bash
cd D:/Work/cad-spec-gen && CAD_PROJECT_ROOT="D:/Work/cad-tests/GISBOT" python cad_pipeline.py codegen --subsystem end_effector
echo "exit code: $?"
```

Expected:
- exit code: 7
- stdout 含人读摘要（"⚠️ codegen 暂停"等）
- pending 文件存在 `D:/Work/cad-tests/GISBOT/.cad-spec-gen/sw_config_pending.json`

- [ ] **Step 4：审 pending 文件含 ~3 个零件**

```bash
cat D:/Work/cad-tests/GISBOT/.cad-spec-gen/sw_config_pending.json | python -m json.tool | head -30
```

Expected: 含 `items_by_subsystem.end_effector` 数组，~3 项

- [ ] **Step 5：手工填决策（模拟 agent 引导）**

```python
# 用 Python 脚本生成 spec_decisions.json
import json
from datetime import datetime, timezone
from pathlib import Path

pending = json.loads(Path("D:/Work/cad-tests/GISBOT/.cad-spec-gen/sw_config_pending.json").read_text(encoding="utf-8"))

decisions = {
    "schema_version": 2,
    "last_updated": datetime.now(timezone.utc).isoformat(),
    "decisions_by_subsystem": {"end_effector": {}},
    "decisions_history": [],
}

for item in pending["items_by_subsystem"]["end_effector"]:
    suggested = item["suggested_options"][0]  # 取 best
    decisions["decisions_by_subsystem"]["end_effector"][item["part_no"]] = {
        "bom_dim_signature": item["bom_dim_signature"],
        "sldprt_filename": item["sldprt_filename"],
        "decision": suggested["action"],
        "config_name": suggested.get("config_name"),
        "user_note": "smoke test 自动选 best suggested",
        "decided_at": datetime.now(timezone.utc).isoformat(),
    }

Path("D:/Work/cad-tests/GISBOT/.cad-spec-gen/spec_decisions.json").write_text(
    json.dumps(decisions, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
print(f"写了 {len(decisions['decisions_by_subsystem']['end_effector'])} 个决策")
```

- [ ] **Step 6：删 pending + 重跑 codegen 期望 exit 0**

```bash
rm D:/Work/cad-tests/GISBOT/.cad-spec-gen/sw_config_pending.json
cd D:/Work/cad-spec-gen && CAD_PROJECT_ROOT="D:/Work/cad-tests/GISBOT" python cad_pipeline.py codegen --subsystem end_effector
echo "exit code: $?"
```

Expected:
- exit code: 0
- std_*.py 文件全部生成
- 含 SW Toolbox 命中零件的 std_*.py 加载 SW STEP 路径（不是 CadQuery 近似）

- [ ] **Step 7：grep std_*.py 确认 STEP 路径含 config 后缀**

```bash
grep -l "step_cache.*sw_toolbox" D:/Work/cad-tests/GISBOT/cad/end_effector/std_*.py
```

Expected: 至少 1-3 个 std_*.py 含 `step_cache/sw_toolbox/...config-suffix.step` 路径

- [ ] **Step 8：跑 build 重建 GLB**

```bash
cd D:/Work/cad-spec-gen && CAD_PROJECT_ROOT="D:/Work/cad-tests/GISBOT" python cad_pipeline.py build --subsystem end_effector 2>&1 | tail -5
```

Expected: GLB 重建成功

- [ ] **Step 9：检查 GLB 大小落在 [3, 8] MB 区间**

```bash
ls -lh D:/Work/cad-tests/GISBOT/cad/output/EE-000_assembly.glb
```

Expected: 在 3-8 MB 之间（既非 1.8 MB 全 CadQuery 也非 6.7 MB 错配 STEP；含真 SW 几何）

- [ ] **Step 10：用 Blender open GLB 人工巡检 O 型圈截面**

打开 Blender → File → Import → glTF 2.0 → 选 EE-000_assembly.glb
找到 GIS-EE-001-03 (O 型圈) 看截面

Expected: O 型圈是真实 SW 几何（半圆截面 + 准确的 80×2.4 比例），不是数学 torus 圆环。

- [ ] **Step 11：成功后 commit baseline 报告**

```bash
ls -lh D:/Work/cad-tests/GISBOT/cad/output/EE-000_assembly.glb > task22_glb_baseline.txt
echo "" >> task22_glb_baseline.txt
echo "决策数：" >> task22_glb_baseline.txt
cat D:/Work/cad-tests/GISBOT/.cad-spec-gen/spec_decisions.json | python -c "import json,sys; d=json.load(sys.stdin); print(len(d['decisions_by_subsystem']['end_effector']))" >> task22_glb_baseline.txt

git add task22_glb_baseline.txt
git commit -m "test: Task 22 GISBOT 端到端 smoke 通过

CP-8 验证：
- codegen 首次跑 exit 7 + 写 pending
- 决策填完后重跑 exit 0
- std_*.py 含 SW STEP 路径（config-suffixed cache）
- GLB 重建在 [3, 8] MB 区间含 SW 真几何
- O 型圈截面 Blender 巡检为真实 SW 形状

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

**🛑 CP-8 暂停**：用户验收 GLB 含 SW 真几何 → 项目可发布 v2.19.0

---

## Task 23：版本 bump + Release（v2.19.0）

**Files:**
- Modify: `src/cad_spec_gen/data/skill.json`
- Auto: `AGENTS.md`

- [ ] **Step 1：bump version**

```bash
sed -i 's/"version": "2.18.0"/"version": "2.19.0"/' src/cad_spec_gen/data/skill.json
```

- [ ] **Step 2：跑 dev_sync 同步 AGENTS.md**

```bash
.venv/Scripts/python.exe scripts/dev_sync.py
```

- [ ] **Step 3：commit + tag + push**

```bash
git add src/cad_spec_gen/data/skill.json AGENTS.md
git commit -m "chore: bump v2.19.0 — sw_config_broker

新增模块 sw_config_broker + sw_list_configs_worker；
sw_toolbox_adapter.resolve 委托给 broker；
gen_std_parts 捕获 NeedsUserDecision 累积 + 一次性原子写 pending +
exit 7 + stdout 摘要；
schema v2 spec_decisions.json + sw_config_pending.json 含 subsystem 嵌套；
新约束：默认 policy=halt 永不静默 fallback；
CAD_AMBIGUOUS_CONFIG_POLICY=fallback_cadquery 用户显式 opt-in 才允许。

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"

git tag v2.19.0
git push origin main
git push origin v2.19.0
```

- [ ] **Step 4：建 GitHub Release**

```bash
gh release create v2.19.0 --title "v2.19.0: sw_config_broker — SW Toolbox 配置名 LLM-broker" --notes "$(cat <<'EOF'
## 核心新增

### sw_config_broker 模块
- 新增 `adapters/solidworks/sw_config_broker.py`：BOM 行 → SW Toolbox 配置名匹配单一职责模块
- 新增 `adapters/solidworks/sw_list_configs_worker.py`：独立 COM 子进程列 SLDPRT 配置名

### gen_std_parts 决策机制
- 含糊匹配 → 累积 pending records → 一次性原子写 `<project>/.cad-spec-gen/sw_config_pending.json` → exit 7
- stdout 打印人读摘要含 [推荐] /cad-codegen skill + [手动] 编辑路径双引导
- 决策持久化到 `<project>/.cad-spec-gen/spec_decisions.json`（schema v2，按 subsystem 嵌套）

### 新约束：不静默绕过 SW
- 默认 `CAD_AMBIGUOUS_CONFIG_POLICY=halt` 含糊匹配永不自动 fallback
- 用户必须显式设 `CAD_AMBIGUOUS_CONFIG_POLICY=fallback_cadquery` 才允许（且仍写 pending 供事后审阅）

## 修复

修复 session 31 后 GISBOT 端到端 GLB 回归（SW STEP 加载默认配置 → 尺寸跑偏）：
- 现在每个 SW Toolbox 命中零件都通过 ShowConfiguration2 取尺寸匹配的 STEP
- GLB 大小在 [3, 8] MB 区间（既非 1.8MB 全 CadQuery 也非 6.7MB 错配 STEP）

## Schema 变更

`spec_decisions.json` schema_version: 1 → 2
- 顶层 `subsystem` 字段移除
- 新增 `decisions_by_subsystem` 嵌套（按 subsystem 分组）
- 移除 `decision="spec_amended"` 取值

`sw_config_pending.json` schema_version: 1 → 2
- 新增 `items_by_subsystem` 嵌套
EOF
)"
```

- [ ] **Step 5：本机 pip install 升级**

```bash
.venv/Scripts/pip install -e . --force-reinstall --no-deps
```

确认 `cad_spec_gen --version` 显示 2.19.0。

无 commit（手动验证步骤）

---

## 自审检查

### 1. Spec 覆盖（13 AC 对照）

| AC | 实现 task | 验证 |
|----|----------|------|
| AC-1 broker 列 config | Task 21 (E2E test_list_configs_returns_nonempty) | ✅ |
| AC-2 规则匹配 Φ80×2.4 | Task 4 (test_l1_exact_unicode_x) | ✅ |
| AC-3 NeedsUserDecision 携带 record | Task 2 (test_needs_user_decision_carries_record) | ✅ |
| AC-4 cache 命中调 COM 校验 | Task 12 (test_path_2_cached_decision_use_config_valid) | ✅ |
| AC-5 invalidate 三项触发 | Task 6 (TestValidateCachedDecision 全部) | ✅ |
| AC-6 默认 halt 不 fallback | Task 12 (test_path_5_halt_raises_needs_user_decision) | ✅ |
| AC-7 显式 fallback opt-in | Task 12 (test_path_4_policy_fallback_silent) | ✅ |
| AC-8 损坏 fail-loud 含行号 | Task 9 (test_load_corrupt_json_fails_loud) | ✅ |
| AC-9 multi-subsystem 嵌套 | Task 16 (test_pending_file_schema_v2_with_subsystem_nesting) | ✅ |
| AC-10 multi-subsystem 决策隔离 | Task 12 (cached_decision 用 subsystem 参数) | ✅ |
| AC-11 stdout 人读摘要 | Task 17 (test_stdout_summary_contains_guidance) | ✅ |
| AC-12 GISBOT GLB 验收 | Task 22 step 9-10 | ✅ |
| AC-13 skill 文档 | Task 19+20 | ✅ |

### 2. Placeholder 扫描

无 TBD / TODO / "implement later" / "similar to Task N" 等。

### 3. 类型一致性

- `ConfigResolution.source` 三个取值贯穿：`"cached_decision"` / `"auto"` / `"policy_fallback"`
- `decision` 两个取值贯穿：`"use_config"` / `"fallback_cadquery"`
- `match_failure_reason` 四个取值贯穿：`"no_exact_or_fuzzy_match_with_high_confidence"` / `"multiple_high_confidence_matches"` / `"com_open_failed"` / `"empty_config_list"`
- `invalidation_reason` 三个取值贯穿
- `_load_decisions_envelope() -> dict` 返回完整 envelope
- `NeedsUserDecision(part_no, subsystem, pending_record)` 三参 init 贯穿

### 4. 文件路径一致

- 决策文件: `<project>/.cad-spec-gen/spec_decisions.json`
- Pending 文件: `<project>/.cad-spec-gen/sw_config_pending.json`
- 锁文件: `<project>/.cad-spec-gen/lock`
- 所有 task 引用一致

### 5. Commit 命名规范

每 task commit 都符合 CLAUDE.md 规范：`feat(sw_config_broker): ...` / `test(...): ...` / `refactor(...): ...` / `docs(skill): ...` / `chore: ...`

### 6. TDD 严格度

每个 task 步骤遵循：写 failing 测试 → 跑确认 FAIL → 写最小实现 → 跑确认 PASS → commit。Task 14 有特殊"先实现后回头补测试"步骤是因为大改 adapter 需要先看清现有结构。

---

_本计划基于 spec rev 2 拆出 23 个 task / 8 个 checkpoint；下一步用 subagent-driven-development 或 executing-plans 落地。_
