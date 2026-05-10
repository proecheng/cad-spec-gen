# CP-5 Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 jury→prompt 闭环单视角主入口 `tools/jury_loop/orchestrator.py::run_loop_if_eligible`，覆盖 spec §3 全 10 步 + 8 Gate + 4 BackendError 异常分类，返 `LoopResult(final_path, loop_status)` 给 cmd_enhance。

**Architecture:** 单一函数 + 6 内部 `_helper`（_check_pre_jury_gates / _rename_baseline_as_final / _call_jury_subprocess / _classify_backend_error / _apply_overrides / _finalize）；mock 边界仅 subprocess + adapter.call，CP-1/2/3/4 实现全用真实调用（深集成）；fail-safe 简化版 try/except Exception → write_degraded_sidecar + re-raise。

**Tech Stack:** Python 3.12 + pytest + monkeypatch + 既有 BackendAdapter Protocol / LoopBudget / ViewVerdict / metadata.write_sidecar / score_select Strategy。

---

## §1 范围与前置依赖

### CP-5 spec
- 设计文档：`docs/superpowers/specs/2026-05-10-cp5-orchestrator-design.md` rev 3 (commit `c202ae0`)
- 父 spec：`docs/superpowers/specs/2026-05-10-jury-prompt-loop-design.md` §3 / §4.4 / §4.5 / §4.6 / §6

### 前置依赖（必须先于本 plan Task 5.1 实施）
- ✅ CP-1（reason_parser / rule_table）
- ✅ CP-2.5（BackendAdapter Protocol + 3 内置 adapter）
- ✅ CP-3（llm_fallback / score_select）
- ✅ CP-4（enhance_budget / metadata sidecar）
- ✅ batch review fixup commit `7fa7c93`
- 🔲 **Task 5.0 (本 plan 第 1 task)**：落地 `tools/jury_loop/config.py::JuryLoopConfig + BackendConfig + load_jury_loop_config`（原父 plan Task 7.2 物理移到 CP-5 之前）

### 父 plan / 父 spec 同步项（本 plan 内顺手做）
- 父 plan `2026-05-10-jury-prompt-loop-plan.md` Task 7.2 (line 1323-1333) 内容已在本 plan Task 5.0 复制；父 plan 留 cross-reference
- 父 plan Task 5.1 (line 1206-1217) 签名升 10 kwarg：加 `jury_profile / jury_profile_path / base_params`
- 父 plan Task 7.1 (line 1289-1304) cmd_enhance 视角级 try/except 处理 FileNotFoundError 防死循环
- 父 spec line 183 / 191 / §4.4 line 472 三处 doc fix（独立 commit 同步）

---

## §2 文件结构

| 文件 | 责任 | 任务 |
|---|---|---|
| `tools/jury_loop/config.py` | `BackendConfig` + `JuryLoopConfig` dataclass + `load_jury_loop_config(pipeline_config_dict) -> JuryLoopConfig` | Task 5.0 |
| `tools/jury_loop/score_select.py` | `SelectionResult` 加 `retry_verdict: ViewVerdict \| None` 字段；`PickMaxJuryStrategy.select` 填该字段；`ForceRetryStrategy.select` 填 None | Task 5.1.1 |
| `tools/jury_loop/orchestrator.py` | `LoopResult` dataclass + `run_loop_if_eligible(...)` + 6 私有 helper + 2 拼装 helper | Task 5.1.2-5.1.10 |
| `tests/jury_loop/conftest.py` | 加 fixture：`fake_view_verdict / fake_jury_sequence / isolated_backend_registry / fake_backend_adapter / fake_render_dir / tiny_jury_profile / tiny_loop_config / user_yaml_with_tag_no_rule` | Task 5.1.11 |
| `tests/jury_loop/test_config.py` | JuryLoopConfig + load 测试 (3-5 case) | Task 5.0 |
| `tests/jury_loop/test_score_select.py` | 既有 14 测试 + 加 retry_verdict 字段验收（3 case） | Task 5.1.1 |
| `tests/jury_loop/test_orchestrator.py` | spec §5 矩阵 19 测试 | Task 5.1.12-5.1.19 |
| `tools/photo3d_jury.py` | （非 CP-5 范围）`--single-view --image --config` flag 由 CP-6 Task 6.1 落地 | N/A |

---

## §3 任务

### Task 5.0：JuryLoopConfig + BackendConfig + 加载器（前置依赖）

**Files:**
- Create: `tools/jury_loop/config.py`
- Test: `tests/jury_loop/test_config.py`

**说明**：父 plan Task 7.2 (line 1323-1333) 内容物理移到 CP-5 之前。原文要求：嵌套 `BackendConfig`（kind / base_url / api_key_env / model_name / timeout_s）+ 顶层 `enabled` / `cost_cap_usd` + `advanced` dict 5 项；schema 校验函数检测顶层与 advanced 同名 key 共存 → ValueError（DRIFT-MAJOR-4）；`api_key_env` 字段触发时通过 `os.environ.get(name)` 读 raw key，缺失时启动期 warn 但不阻塞（首次 retry 时再 hard fail）。

- [ ] **Step 1：写测试 test_config.py（RED）**

```python
"""tools/jury_loop/config.py 测试。"""
from __future__ import annotations

import pytest

from tools.jury_loop.config import BackendConfig, JuryLoopConfig, load_jury_loop_config


def test_load_jury_loop_config_minimal_dict() -> None:
    """最小 dict 加载得到合法 JuryLoopConfig（用顶层默认 enabled=True / cost_cap_usd=1.5）。"""
    config = load_jury_loop_config({
        "backend": {
            "kind": "fal_comfy", "base_url": "https://example.test",
            "api_key_env": "FAL_KEY", "model_name": "test-model", "timeout_s": 60,
        },
        "advanced": {
            "threshold": 75, "max_retries": 1, "llm_fallback": False,
            "rule_table_path": None, "score_select_strategy": "pick_max_jury",
        },
    })
    assert config.enabled is True
    assert config.cost_cap_usd == 1.5
    assert config.backend.kind == "fal_comfy"
    assert config.advanced["threshold"] == 75


def test_load_rejects_top_level_advanced_key_collision() -> None:
    """顶层与 advanced 同名 key (e.g. 顶层 'threshold') → ValueError (DRIFT-MAJOR-4)。"""
    with pytest.raises(ValueError, match="顶层.*advanced.*共存"):
        load_jury_loop_config({
            "threshold": 80,  # 顶层不应有
            "backend": {"kind": "x", "base_url": "x", "api_key_env": "x",
                         "model_name": "x", "timeout_s": 60},
            "advanced": {"threshold": 75, "max_retries": 1, "llm_fallback": False,
                          "rule_table_path": None, "score_select_strategy": "pick_max_jury"},
        })


def test_load_missing_api_key_env_warns_not_raise(caplog) -> None:
    """api_key_env 指向不存在的环境变量 → warn 不抛（启动期柔性）。"""
    import os
    os.environ.pop("NON_EXIST_KEY", None)
    config = load_jury_loop_config({
        "backend": {"kind": "x", "base_url": "x", "api_key_env": "NON_EXIST_KEY",
                     "model_name": "x", "timeout_s": 60},
        "advanced": {"threshold": 75, "max_retries": 1, "llm_fallback": False,
                      "rule_table_path": None, "score_select_strategy": "pick_max_jury"},
    })
    assert config is not None  # 不抛
    assert any("NON_EXIST_KEY" in m for m in caplog.messages)


def test_jury_loop_config_disabled_form() -> None:
    """enabled=False 时其他字段仍合法 dataclass。"""
    config = load_jury_loop_config({
        "enabled": False,
        "backend": {"kind": "x", "base_url": "x", "api_key_env": "x",
                     "model_name": "x", "timeout_s": 60},
        "advanced": {"threshold": 75, "max_retries": 1, "llm_fallback": False,
                      "rule_table_path": None, "score_select_strategy": "pick_max_jury"},
    })
    assert config.enabled is False
```

- [ ] **Step 2：跑测试确认 RED**

```bash
python -m pytest tests/jury_loop/test_config.py -v
```
Expected: ERROR collection — `ModuleNotFoundError: No module named 'tools.jury_loop.config'`。

- [ ] **Step 3：写实现 tools/jury_loop/config.py**

```python
"""enhance.jury_loop 段配置 dataclass + 加载器（DRIFT-MAJOR-4 同名 key 校验）。"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_ADVANCED_KEYS = frozenset({
    "threshold", "max_retries", "llm_fallback", "rule_table_path",
    "score_select_strategy",
})


@dataclass(frozen=True)
class BackendConfig:
    """retry backend 配置（spec §4.1 backend 子段 5 字段）。"""
    kind: str
    base_url: str
    api_key_env: str
    model_name: str
    timeout_s: int


@dataclass(frozen=True)
class JuryLoopConfig:
    """enhance.jury_loop 解析后 dataclass（spec §4.1）。"""
    enabled: bool
    cost_cap_usd: float
    backend: BackendConfig
    advanced: dict[str, Any] = field(default_factory=dict)


def load_jury_loop_config(d: dict[str, Any]) -> JuryLoopConfig:
    """从 pipeline_config['enhance']['jury_loop'] dict 解析；未填顶层用默认。

    - 顶层与 advanced 同名 key 共存 → ValueError (DRIFT-MAJOR-4)。
    - api_key_env 指向不存在的环境变量 → warn 但不抛（启动柔性，首次 retry 时再 hard fail）。
    """
    advanced = dict(d.get("advanced", {}))
    # DRIFT-MAJOR-4：顶层 与 advanced 同名 key 共存 → ValueError
    collision = (set(d.keys()) & _ADVANCED_KEYS)
    if collision:
        raise ValueError(
            f"jury_loop 顶层与 advanced 同名 key 共存：{sorted(collision)}"
            f"（请只在 advanced 段配置）"
        )

    backend_dict = d["backend"]
    backend = BackendConfig(
        kind=backend_dict["kind"],
        base_url=backend_dict["base_url"],
        api_key_env=backend_dict["api_key_env"],
        model_name=backend_dict["model_name"],
        timeout_s=int(backend_dict["timeout_s"]),
    )
    if not os.environ.get(backend.api_key_env):
        log.warning(
            "api_key_env=%s 在当前环境未设置；首次 retry 调用时将 hard fail",
            backend.api_key_env,
        )
    return JuryLoopConfig(
        enabled=bool(d.get("enabled", True)),
        cost_cap_usd=float(d.get("cost_cap_usd", 1.5)),
        backend=backend,
        advanced=advanced,
    )
```

- [ ] **Step 4：跑测试确认 GREEN**

```bash
python -m pytest tests/jury_loop/test_config.py -v
```
Expected: 4 passed。

- [ ] **Step 5：mypy + ruff**

```bash
python -m mypy --strict tools/jury_loop/config.py
python -m ruff check tools/jury_loop/config.py tests/jury_loop/test_config.py
```
Expected: 全过。

- [ ] **Step 6：Commit**

```bash
git add tools/jury_loop/config.py tests/jury_loop/test_config.py
git commit -m "feat(jury-loop): JuryLoopConfig + BackendConfig + load 验证 (Task 5.0 / 父 plan Task 7.2 提前)"
```

---

### Task 5.1.1：score_select.SelectionResult 加 retry_verdict 字段

**Files:**
- Modify: `tools/jury_loop/score_select.py:35-45`（SelectionResult NamedTuple 加字段）+ PickMaxJuryStrategy.select / ForceRetryStrategy.select 填该字段
- Test: `tests/jury_loop/test_score_select.py`（加 3 测试）

**说明**：spec rev 3 决议 #12——orchestrator 写 sidecar.retry 字段需要 retry candidate 的 verdict（pick_max_jury 路径选 baseline 时也要保留 retry verdict）。score_select.SelectionResult 当前无 retry_verdict 出口。

- [ ] **Step 1：写测试（RED）**

```python
# tests/jury_loop/test_score_select.py 末尾追加
def test_pick_max_jury_keeps_retry_verdict_in_result() -> None:
    """rev 3 决议 #12：SelectionResult.retry_verdict 保留 retry candidate 的 verdict。"""
    baseline_v = ViewVerdict(semantic_checks={...}, photoreal_score=58, reason="x",
                              parse_status="ok", parse_anomalies=[], verdict="accepted")
    retry_v = ViewVerdict(semantic_checks={...}, photoreal_score=80, reason="y",
                           parse_status="ok", parse_anomalies=[], verdict="accepted")
    candidates = [CandidateImage("a.jpg", baseline_v), CandidateImage("b.jpg", None)]
    result = PickMaxJuryStrategy().select(candidates, lambda p: retry_v, _stub_budget())
    assert result.retry_verdict is retry_v  # 即使选 retry，retry_verdict 仍可读


def test_pick_max_jury_keeps_retry_verdict_when_baseline_picked() -> None:
    """retry 降分被选 baseline 时，retry_verdict 仍含完整 verdict（写 sidecar.retry 用）。"""
    baseline_v = ViewVerdict(semantic_checks={...}, photoreal_score=58, ...)
    retry_v = ViewVerdict(semantic_checks={...}, photoreal_score=50, ...)  # 降分
    candidates = [CandidateImage("a.jpg", baseline_v), CandidateImage("b.jpg", None)]
    result = PickMaxJuryStrategy().select(candidates, lambda p: retry_v, _stub_budget())
    assert result.pick.image_path == "a.jpg"  # 选 baseline
    assert result.retry_verdict is retry_v   # retry verdict 仍出口


def test_force_retry_returns_none_retry_verdict() -> None:
    """force_retry 不二轮 jury，retry_verdict 必为 None（spec §4.4 line 530）。"""
    baseline_v = ViewVerdict(semantic_checks={...}, photoreal_score=58, ...)
    candidates = [CandidateImage("a.jpg", baseline_v), CandidateImage("b.jpg", None)]
    result = ForceRetryStrategy().select(candidates, lambda p: 1/0, _stub_budget())
    assert result.retry_verdict is None
```

- [ ] **Step 2：RED**

```bash
python -m pytest tests/jury_loop/test_score_select.py::test_pick_max_jury_keeps_retry_verdict_in_result -v
```
Expected: AttributeError 或 TypeError（SelectionResult 无 retry_verdict 字段）。

- [ ] **Step 3：改实现 score_select.py**

修改 `SelectionResult` NamedTuple 加 `retry_verdict: ViewVerdict | None`；`PickMaxJuryStrategy.select` line 50-90 段：

```python
class SelectionResult(NamedTuple):
    pick: CandidateImage
    extra_jury_calls: int
    rationale: str
    retry_verdict: ViewVerdict | None  # rev 3 决议 #12：retry candidate verdict 出口


class PickMaxJuryStrategy:
    def select(self, candidates, jury_callable, budget):
        baseline, retry = candidates[0], candidates[1]
        try:
            retry_verdict = jury_callable(retry.image_path)
        except Exception:
            return SelectionResult(pick=baseline, extra_jury_calls=0,
                                    rationale="jury 二轮失败 → 选 baseline",
                                    retry_verdict=None)
        if retry_verdict.photoreal_score > baseline.verdict.photoreal_score:
            return SelectionResult(pick=retry, extra_jury_calls=1,
                                    rationale=f"retry score 高 → 选 retry",
                                    retry_verdict=retry_verdict)
        return SelectionResult(pick=baseline, extra_jury_calls=1,
                                rationale="retry 平/降分 → 选 baseline（保守）",
                                retry_verdict=retry_verdict)


class ForceRetryStrategy:
    def select(self, candidates, jury_callable, budget):
        if len(candidates) != 2:
            raise ValueError("ForceRetryStrategy 仅支持 SP1 双 candidate")
        return SelectionResult(pick=candidates[1], extra_jury_calls=0,
                                rationale="force_retry 强选 retry",
                                retry_verdict=None)
```

- [ ] **Step 4：跑全套件 GREEN**

```bash
python -m pytest tests/jury_loop/test_score_select.py -v
```
Expected: 既有 14 测试 + 3 新测试全 GREEN（17 total）。

- [ ] **Step 5：Commit**

```bash
git add tools/jury_loop/score_select.py tests/jury_loop/test_score_select.py
git commit -m "feat(jury-loop): SelectionResult 加 retry_verdict 出口（CP-5 rev 3 决议 #12）"
```

---

### Task 5.1.2：LoopResult dataclass + Precondition fail-fast

**Files:**
- Create: `tools/jury_loop/orchestrator.py`（先建骨架 + LoopResult + Precondition）
- Test: `tests/jury_loop/test_orchestrator.py`（先加 #20 baseline_missing）

- [ ] **Step 1：写测试 #20 RED**

```python
"""CP-5 orchestrator 集成测试（spec §5 矩阵）。"""
from __future__ import annotations
from pathlib import Path
import pytest

from tools.jury_loop.orchestrator import LoopResult, run_loop_if_eligible


def test_baseline_path_missing_raises_filenotfound(tmp_path, tiny_loop_config,
                                                      tiny_jury_profile):
    """rev 3 §5 测试 #20：baseline_path 不存在 → fail-fast raise FileNotFoundError；不写 sidecar。"""
    config = tiny_loop_config()
    with pytest.raises(FileNotFoundError):
        run_loop_if_eligible(
            view="V1", backend_kind="test_stub", rc={},
            baseline_path=tmp_path/"nope.jpg",  # 不存在
            base_params={}, budget=_stub_budget(), project_root=tmp_path,
            config=config, jury_profile=tiny_jury_profile,
            jury_profile_path=tmp_path/"profile.yaml",
        )
    # 不写 sidecar
    assert not list(tmp_path.glob("V1_enhance_meta.json"))
```

- [ ] **Step 2：RED**

```bash
python -m pytest tests/jury_loop/test_orchestrator.py::test_baseline_path_missing_raises_filenotfound -v
```
Expected: ImportError（orchestrator 模块不存在）。

- [ ] **Step 3：写 orchestrator.py 骨架**

```python
"""CP-5 orchestrator：jury→prompt 闭环单视角主入口。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from enhance_budget import LoopBudget
from tools.jury.config import JuryProfile
from tools.jury_loop.config import JuryLoopConfig
from tools.jury_loop.metadata import _validate_view_basename


@dataclass(frozen=True)
class LoopResult:
    """单视角闭环结果（最小契约）。"""
    final_path: Path
    loop_status: str


def run_loop_if_eligible(
    *,
    view: str,
    backend_kind: str,
    rc: dict,
    baseline_path: Path,
    base_params: dict,
    budget: LoopBudget,
    project_root: Path,
    config: JuryLoopConfig,
    jury_profile: JuryProfile,
    jury_profile_path: Path,
) -> LoopResult:
    """单视角 jury→prompt 闭环。详见 spec §3。"""
    # Precondition fail-fast（不写 sidecar）
    if not baseline_path.is_file():
        raise FileNotFoundError(f"baseline_path 不存在：{baseline_path}")
    safe_view = _validate_view_basename(view)
    raise NotImplementedError("Task 5.1.10 完整实现")
```

- [ ] **Step 4：测试 #20 GREEN（其他测试还会 NotImplementedError）**

```bash
python -m pytest tests/jury_loop/test_orchestrator.py::test_baseline_path_missing_raises_filenotfound -v
```
Expected: PASS。

- [ ] **Step 5：Commit**

```bash
git add tools/jury_loop/orchestrator.py tests/jury_loop/test_orchestrator.py
git commit -m "feat(jury-loop): orchestrator 骨架 + LoopResult + Precondition fail-fast（CP-5 Task 5.1.2）"
```

---

### Task 5.1.3：fixture 升级（conftest.py）

**Files:**
- Modify: `tests/jury_loop/conftest.py`（加 6 新 fixture）

- [ ] **Step 1：写实现（无 RED 阶段——fixture 是测试支撑，不直接测）**

```python
# tests/jury_loop/conftest.py 追加（保留既有 fixture_dir / sample_reason_plastic_flat / builtin_yaml_path）

from contextlib import contextmanager
from pathlib import Path
from typing import Iterable

import pytest

from tools.jury.config import JuryProfile
from tools.jury.verdict import ViewVerdict
from tools.jury_loop.backends import BACKEND_REGISTRY, register_backend


@pytest.fixture
def fake_view_verdict():
    """ViewVerdict factory（对齐 tools/jury/verdict.py 真签名 6 字段）。"""
    def _make(score=58, reason="plastic look, flat lighting", verdict="accepted",
              parse_anomalies=None, semantic_checks=None):
        return ViewVerdict(
            semantic_checks=semantic_checks or {
                "geometry_preserved": True, "material_consistent": True,
                "photorealistic": False, "no_extra_parts": True,
                "no_missing_parts": True,
            },
            photoreal_score=score, reason=reason,
            parse_status="ok", parse_anomalies=parse_anomalies or [],
            verdict=verdict,
        )
    return _make


@pytest.fixture
def fake_jury_sequence(fake_view_verdict):
    """Stateful jury 工厂：把 (score, reason) tuple list 变 lambda 让连续调用按序返。"""
    def _make(items: Iterable[tuple[int, str]]):
        verdicts = iter([fake_view_verdict(score=s, reason=r) for s, r in items])
        return lambda: next(verdicts)
    return _make


@pytest.fixture
def isolated_backend_registry():
    """对齐既有 test_backend_protocol.py:79 模式 — snapshot/restore。"""
    snapshot = dict(BACKEND_REGISTRY)
    yield BACKEND_REGISTRY
    BACKEND_REGISTRY.clear()
    BACKEND_REGISTRY.update(snapshot)


@pytest.fixture
def fake_backend_adapter(isolated_backend_registry):
    """注册 _FakeAdapter 到 BACKEND_REGISTRY 的 context manager。"""
    @contextmanager
    def _register(kind="test_stub", call_returns=None, raises=None,
                  estimate_cost_usd=0.05):
        class _FakeAdapter:
            @property
            def kind(self): return kind
            @property
            def known_params(self): return {}
            def supports_controlnet(self): return False
            def estimate_cost_usd(self, request): return estimate_cost_usd
            def call(self, request, timeout):
                if raises is not None: raise raises
                return call_returns
        BACKEND_REGISTRY.pop(kind, None)  # 清残留
        register_backend(_FakeAdapter())
        yield kind
    return _register


@pytest.fixture
def fake_render_dir(tmp_path):
    rd = tmp_path / "render"
    rd.mkdir()
    (rd / "V1_enhanced_baseline.jpg").write_bytes(b"\x89PNG\r\n...假 PNG 头")
    return rd


@pytest.fixture
def tiny_jury_profile():
    """JuryProfile factory（fake LLM endpoint）。"""
    return JuryProfile(
        id="test", kind="openai_compat",
        api_base_url="https://example.test/v1",
        api_key="sk-fake-test-key",
        model="gemini-2.5-flash", cost_per_call_usd=0.005,
    )


@pytest.fixture
def tiny_loop_config():
    """JuryLoopConfig factory（字段对齐 plan Task 5.0 真 schema）。"""
    def _make(*, enabled=True, cost_cap_usd=1.5, backend_kind="test_stub",
              threshold=75, llm_fallback=False,
              score_select_strategy="pick_max_jury",
              max_retries=1, rule_table_path=None):
        from tools.jury_loop.config import BackendConfig, JuryLoopConfig
        return JuryLoopConfig(
            enabled=enabled, cost_cap_usd=cost_cap_usd,
            backend=BackendConfig(
                kind=backend_kind, base_url="https://example.test",
                api_key_env="TEST_API_KEY", model_name="test-model", timeout_s=60),
            advanced={"threshold": threshold, "max_retries": max_retries,
                       "llm_fallback": llm_fallback,
                       "rule_table_path": rule_table_path,
                       "score_select_strategy": score_select_strategy},
        )
    return _make


@pytest.fixture
def user_yaml_with_tag_no_rule(tmp_path):
    """测试 #8 专用：用户 yaml 扩 tag_dictionary 不加 rule。"""
    p = tmp_path / "user_rules.yaml"
    p.write_text("""schema_version: 1
tag_dictionary:
  unknown_aesthetic_tag:
    patterns:
      - "weird vibe"
      - "off feeling"
rules: []
""", encoding="utf-8")
    return p
```

- [ ] **Step 2：跑全套件确保 fixture 不破现有测试**

```bash
python -m pytest tests/jury_loop/ -v
```
Expected: 既有 jury_loop 套件 ≥201 测试全 GREEN（fixture 仅 additive；test_orchestrator.py::test_baseline_path_missing PASS，其他不变）。

- [ ] **Step 3：Commit**

```bash
git add tests/jury_loop/conftest.py
git commit -m "test(jury-loop): orchestrator fixture 升级 — isolated_registry / stateful jury / tiny config（CP-5 Task 5.1.3）"
```

---

### Task 5.1.4：_check_pre_jury_gates + 测试 #1/#2

**Files:**
- Modify: `tools/jury_loop/orchestrator.py`（加 `_check_pre_jury_gates` helper）
- Test: `tests/jury_loop/test_orchestrator.py`（加 #1/#2）

- [ ] **Step 1：写测试 #1/#2 RED**

```python
def test_gate1_backend_unregistered(tmp_path, fake_render_dir, tiny_loop_config,
                                       tiny_jury_profile, isolated_backend_registry):
    """spec §5 #1：backend_kind='engineering' 不在 BACKEND_REGISTRY → loop_disabled。"""
    config = tiny_loop_config(backend_kind="engineering")
    result = run_loop_if_eligible(
        view="V1", backend_kind="engineering", rc={},
        baseline_path=fake_render_dir/"V1_enhanced_baseline.jpg",
        base_params={}, budget=_stub_budget(), project_root=tmp_path,
        config=config, jury_profile=tiny_jury_profile,
        jury_profile_path=tmp_path/"profile.yaml",
    )
    assert result.loop_status == "loop_disabled"
    assert (fake_render_dir/"V1_enhanced.jpg").is_file()


def test_gate2_enabled_false(tmp_path, fake_render_dir, fake_backend_adapter,
                                tiny_loop_config, tiny_jury_profile):
    """spec §5 #2：config.enabled=False → loop_disabled。"""
    with fake_backend_adapter() as kind:
        config = tiny_loop_config(enabled=False, backend_kind=kind)
        result = run_loop_if_eligible(
            view="V1", backend_kind=kind, rc={},
            baseline_path=fake_render_dir/"V1_enhanced_baseline.jpg",
            base_params={}, budget=_stub_budget(), project_root=tmp_path,
            config=config, jury_profile=tiny_jury_profile,
            jury_profile_path=tmp_path/"profile.yaml",
        )
    assert result.loop_status == "loop_disabled"
```

`_stub_budget()` 是 module-level helper：

```python
def _stub_budget():
    return LoopBudget(cap_usd=1.5, n_views=1)
```

- [ ] **Step 2：RED**

```bash
python -m pytest tests/jury_loop/test_orchestrator.py -v
```
Expected: NotImplementedError（顶层骨架仍 raise）。

- [ ] **Step 3：实现 _check_pre_jury_gates + Gate-1/2 路径**

替换 orchestrator.py `raise NotImplementedError` 为：

```python
from tools.jury_loop.backends import BACKEND_REGISTRY
from tools.jury_loop import metadata


def _check_pre_jury_gates(backend_kind: str, config: JuryLoopConfig) -> str | None:
    """Gate-1：backend_kind 不在 BACKEND_REGISTRY → loop_disabled。
    Gate-2：config.enabled=False → loop_disabled。否则返 None。"""
    if backend_kind not in BACKEND_REGISTRY:
        return "loop_disabled"
    if not config.enabled:
        return "loop_disabled"
    return None


def _rename_baseline_as_final(baseline_path: Path, view: str, render_dir: Path) -> Path:
    """父 spec §3 Gate-1/2 line 165：baseline → V<view>_enhanced.jpg。"""
    final_path = render_dir / f"{view}_enhanced.jpg"
    final_path.unlink(missing_ok=True)
    Path(baseline_path).replace(final_path)
    return final_path


# 顶层 run_loop_if_eligible 在 Precondition 之后接：
def run_loop_if_eligible(...):
    if not baseline_path.is_file(): raise FileNotFoundError(...)
    safe_view = _validate_view_basename(view)
    render_dir = baseline_path.parent

    # Step 1: Gate-1/2
    gate_status = _check_pre_jury_gates(backend_kind, config)
    if gate_status:
        final_path = _rename_baseline_as_final(baseline_path, safe_view, render_dir)
        metadata.write_sidecar(
            view=safe_view, render_dir=render_dir, backend=backend_kind,
            loop_status=gate_status, baseline=None, retry=None,
            extra_cost_usd=0,
        )
        return LoopResult(final_path, gate_status)

    raise NotImplementedError("Task 5.1.5+ 完整 jury 流程")
```

- [ ] **Step 4：测试 #1/#2 GREEN**

```bash
python -m pytest tests/jury_loop/test_orchestrator.py -k "gate1 or gate2 or baseline_path_missing" -v
```
Expected: 3 PASS（含 #20）。

- [ ] **Step 5：Commit**

```bash
git add tools/jury_loop/orchestrator.py tests/jury_loop/test_orchestrator.py
git commit -m "feat(jury-loop): _check_pre_jury_gates + _rename_baseline_as_final + Gate-1/2 路径（CP-5 Task 5.1.4）"
```

---

### Task 5.1.5：_classify_backend_error + 测试 #9-#12

**Files:**
- Modify: `tools/jury_loop/orchestrator.py`（加 `_classify_backend_error` helper）
- Test: 加 #9-#12 测试

**说明**：spec rev 3 决议 #10——返 `tuple[str, dict]`，第二个是 errors[].* 字典。

- [ ] **Step 1：写测试 #9-#12 RED**

```python
import pytest
from tools.jury_loop.backends import (BackendAuthError, BackendCallError,
                                        BackendQuotaExceededError, BackendRateLimitError)


@pytest.mark.parametrize("exc_class, expected_status, expected_code", [
    (BackendAuthError, "retry_auth_failed", "backend_auth_error"),
    (BackendRateLimitError, "retry_rate_limited", "backend_rate_limited"),
    (BackendQuotaExceededError, "retry_quota_exceeded", "backend_quota_exceeded"),
    (BackendCallError, "retry_failed", "backend_call_error"),
])
def test_gate8_backend_error_classification(
    tmp_path, fake_render_dir, fake_backend_adapter, tiny_loop_config,
    tiny_jury_profile, fake_jury_sequence, monkeypatch,
    exc_class, expected_status, expected_code,
):
    """spec §5 #9-#12：4 类 BackendError → 对应 retry_* loop_status + errors[0].code。"""
    jury_seq = fake_jury_sequence([(58, "plastic look")])
    monkeypatch.setattr(
        "tools.jury_loop.orchestrator._call_jury_subprocess",
        lambda *a, **kw: (jury_seq(), None),
    )
    with fake_backend_adapter(raises=exc_class("vendor 错")) as kind:
        config = tiny_loop_config(backend_kind=kind)
        result = run_loop_if_eligible(
            view="V1", backend_kind=kind, rc={"prompt": "test"},
            baseline_path=fake_render_dir/"V1_enhanced_baseline.jpg",
            base_params={}, budget=LoopBudget(cap_usd=1.5, n_views=1),
            project_root=tmp_path, config=config,
            jury_profile=tiny_jury_profile,
            jury_profile_path=tmp_path/"profile.yaml",
        )
    assert result.loop_status == expected_status
    sidecar = json.loads((fake_render_dir / "V1_enhance_meta.json").read_text("utf-8"))
    assert sidecar["errors"][0]["code"] == expected_code
```

- [ ] **Step 2：RED**

测试预期 NotImplementedError（jury → tag → retry 流程未实现）。

```bash
python -m pytest tests/jury_loop/test_orchestrator.py -k "backend_error" -v
```

- [ ] **Step 3：实现 _classify_backend_error + 完整 retry 路径骨架**

往 orchestrator.py 加：

```python
from tools.jury_loop.backends import (BackendAuthError, BackendCallError,
                                       BackendError, BackendQuotaExceededError,
                                       BackendRateLimitError)


def _classify_backend_error(exc: BackendError) -> tuple[str, dict]:
    """4 路异常分类 → (loop_status, error_entry)。spec rev 3 决议 #10。"""
    if isinstance(exc, BackendAuthError):
        return ("retry_auth_failed", {
            "code": "backend_auth_error",
            "message_summary": str(exc)[:200],
            "user_action_hint": "API key 无效，请检查配置",
        })
    if isinstance(exc, BackendRateLimitError):
        return ("retry_rate_limited", {
            "code": "backend_rate_limited",
            "message_summary": str(exc)[:200],
            "user_action_hint": "服务限流，请稍后重试",
        })
    if isinstance(exc, BackendQuotaExceededError):
        return ("retry_quota_exceeded", {
            "code": "backend_quota_exceeded",
            "message_summary": str(exc)[:200],
            "user_action_hint": "服务账户余额不足，请充值后重试",
        })
    if isinstance(exc, BackendCallError):
        return ("retry_failed", {
            "code": "backend_call_error",
            "message_summary": str(exc)[:200],
            "user_action_hint": "重试失败，请查看 sidecar.errors[]",
        })
    # fallback：未知 BackendError 子类
    return ("retry_failed", {
        "code": "backend_unknown_error",
        "message_summary": str(exc)[:200],
        "user_action_hint": "未知 backend 错误；请提交 issue",
    })
```

至此 Task 5.1.5 暂留 _classify_backend_error 实现；retry 路径会触发 Gate-3 _call_jury_subprocess 仍 NotImplementedError。下一 task 完成。

- [ ] **Step 4：跑测试看 RED 情况（这次因为 monkeypatch _call_jury_subprocess）**

测试 #9-#12 的 monkeypatch 直接替换 _call_jury_subprocess，但 orchestrator 顶层还在 Gate-1/2 后 raise NotImplementedError——会过 Gate-1/2，进 NotImplementedError → 测试失败但原因是 "尚未实现"。这是预期 RED。

- [ ] **Step 5：Commit**

```bash
git add tools/jury_loop/orchestrator.py tests/jury_loop/test_orchestrator.py
git commit -m "feat(jury-loop): _classify_backend_error 4 路分类 + 测试 #9-#12 写入（CP-5 Task 5.1.5）"
```

---

### Task 5.1.6：_call_jury_subprocess + 测试 #3/#4 (Gate-3 / Gate-3.5)

**Files:**
- Modify: `tools/jury_loop/orchestrator.py`（加 `_call_jury_subprocess` helper + Gate-3/3.5 路径）
- Test: 加 #3/#4

**说明**：spec rev 3 决议 #9 返 tuple[ViewVerdict|None, str|None]；#11 empty_reason 锁 Gate-3.5（jury 返非 None 后立即检 `reason.strip() == ""`）。

- [ ] **Step 1：写测试 RED**

```python
def test_gate3_jury_returns_none_maps_to_jury_unavailable(
    tmp_path, fake_render_dir, fake_backend_adapter, tiny_loop_config,
    tiny_jury_profile, monkeypatch,
):
    """spec §5 #3：_call_jury_subprocess 返 (None, "exit_nonzero") → jury_unavailable。"""
    monkeypatch.setattr(
        "tools.jury_loop.orchestrator._call_jury_subprocess",
        lambda *a, **kw: (None, "exit_nonzero"),
    )
    with fake_backend_adapter() as kind:
        config = tiny_loop_config(backend_kind=kind)
        result = run_loop_if_eligible(view="V1", backend_kind=kind, ...)  # 略
    assert result.loop_status == "jury_unavailable"
    sidecar = json.loads((fake_render_dir / "V1_enhance_meta.json").read_text("utf-8"))
    assert sidecar["errors"][0]["code"] == "exit_nonzero"


def test_gate3_5_empty_reason(...):
    """spec §5 #4：jury 返 reason="" → empty_reason。"""
    monkeypatch.setattr(..., lambda *a, **kw: (fake_view_verdict(score=50, reason=""), None))
    ...
    assert result.loop_status == "empty_reason"
```

- [ ] **Step 2：RED + Step 3 实现**

实现 _call_jury_subprocess（subprocess 部分骨架）+ 顶层 Step 2/3 流程：

```python
import subprocess
import sys
import json as _json

from tools.jury.verdict import ViewVerdict, parse_view_verdict


def _call_jury_subprocess(
    view: str, image_path: Path, project_root: Path,
    jury_profile_path: Path, timeout_s: int,
) -> tuple[ViewVerdict | None, str | None]:
    """调 photo3d-jury --single-view 子进程。
    返 tuple：(verdict, error_code)；失败时 verdict=None error_code 是失败类型。"""
    cmd = [
        sys.executable, "-m", "tools.photo3d_jury",
        "--single-view", view,
        "--image", str(image_path),
        "--config", str(jury_profile_path),
    ]
    try:
        proc = subprocess.run(
            cmd, cwd=project_root, timeout=timeout_s,
            capture_output=True, text=True,
        )
    except subprocess.TimeoutExpired:
        return (None, "timeout")
    if proc.returncode != 0:
        return (None, "exit_nonzero")
    try:
        items = _json.loads(proc.stdout)
    except _json.JSONDecodeError:
        return (None, "json_parse_failed")
    if not isinstance(items, list) or len(items) != 1:
        return (None, "json_parse_failed")
    verdict = parse_view_verdict(_json.dumps(items[0]))
    if verdict.verdict == "needs_review":
        return (None, "needs_review")
    return (verdict, None)


# 顶层在 Gate-1/2 之后接：
def run_loop_if_eligible(...):
    ...
    gate_status = _check_pre_jury_gates(...)
    if gate_status: return _emit_loop_disabled(...)

    # Step 2: jury 第一次评
    verdict, jury_err = _call_jury_subprocess(
        safe_view, baseline_path, project_root,
        jury_profile_path, config.backend.timeout_s,
    )
    if verdict is None:
        return _finalize_baseline_only(
            view=safe_view, render_dir=render_dir, backend=backend_kind,
            loop_status="jury_unavailable", baseline_path=baseline_path,
            errors=[{"code": jury_err, "message_summary": f"jury 调用失败：{jury_err}",
                     "user_action_hint": "查看 sidecar.errors[].code"}],
            local_extra_cost=0,
        )

    # Step 3: empty_reason 检（rev 3 决议 #11）
    if verdict.reason.strip() == "":
        return _finalize_baseline_only(
            view=safe_view, render_dir=render_dir, backend=backend_kind,
            loop_status="empty_reason", baseline_path=baseline_path,
            baseline=verdict, local_extra_cost=0,
        )

    raise NotImplementedError("Task 5.1.7+ 完整流程")


def _finalize_baseline_only(*, view, render_dir, backend, loop_status, baseline_path,
                              baseline=None, errors=None, local_extra_cost=0,
                              tags_parsed=None, warnings=None):
    """所有 baseline-only 退出路径（Gate-1~7）共用：rename baseline + write sidecar。"""
    final_path = _rename_baseline_as_final(baseline_path, view, render_dir)
    metadata.write_sidecar(
        view=view, render_dir=render_dir, backend=backend,
        loop_status=loop_status,
        baseline=_view_verdict_to_baseline_dict(baseline, final_path) if baseline else None,
        retry=None, errors=errors or [],
        tags_parsed=tags_parsed or [],
        extra_cost_usd=local_extra_cost,
        warnings=warnings or [],
    )
    return LoopResult(final_path, loop_status)


def _view_verdict_to_baseline_dict(verdict: ViewVerdict, image_path: Path) -> dict:
    """ViewVerdict → sidecar.baseline 投影 4 字段（spec §4.4 line 478-482）。"""
    return {
        "image_path": str(image_path),
        "photoreal_score": verdict.photoreal_score,
        "semantic_checks": dict(verdict.semantic_checks),
        "reason": verdict.reason,
    }
```

- [ ] **Step 4：测试 #3/#4 GREEN**

```bash
python -m pytest tests/jury_loop/test_orchestrator.py -k "gate3" -v
```
Expected: 2 PASS。

- [ ] **Step 5：Commit**

```bash
git commit -m "feat(jury-loop): _call_jury_subprocess + Gate-3/3.5 + _finalize_baseline_only（CP-5 Task 5.1.6）"
```

---

### Task 5.1.7：Gate-4/5/6/7（above_threshold / cost_capped / no_tags / no_rules）

**Files:**
- Modify: `tools/jury_loop/orchestrator.py`（继续 Step 4-7）
- Test: 加 #5/#5b/#6/#7/#8

- [ ] **Step 1：写测试 #5/#5b/#6/#7/#8 RED**

5 测试合并 1 commit；每测试形如 `monkeypatch _call_jury_subprocess + 设置 config 参数 + assert loop_status`。略代码块（结构同 #3）。

- [ ] **Step 2：RED**

```bash
python -m pytest tests/jury_loop/test_orchestrator.py -k "gate4 or gate5 or gate6 or gate7" -v
```

- [ ] **Step 3：实现 Gate-4/5/6/7 顶层流程**

往 orchestrator.py 顶层 Step 3 之后加：

```python
import enhance_budget
from tools.jury_loop import reason_parser, rule_table, llm_fallback


# Step 4: above_threshold (≥ 运算符锁)
if verdict.photoreal_score >= config.advanced["threshold"]:
    return _finalize_baseline_only(
        view=safe_view, render_dir=render_dir, backend=backend_kind,
        loop_status="above_threshold", baseline_path=baseline_path,
        baseline=verdict, local_extra_cost=0,
    )

# Step 5: 估算 cost + try_spend (cost_capped 检)
adapter = BACKEND_REGISTRY[backend_kind]
estimate = enhance_budget.estimate_retry_cost(
    adapter, _build_request(...),  # base_params 入参；具体 BackendRequest 构造
    with_jury=(config.advanced["score_select_strategy"] == "pick_max_jury"),
)
local_extra_cost = 0.0
if not budget.try_spend(estimate):
    return _finalize_baseline_only(..., loop_status="cost_capped",
                                    baseline=verdict, local_extra_cost=0)
local_extra_cost += estimate

# Step 6: tags + rules + apply_overrides
sanitized = reason_parser.reason_sanitized(verdict.reason)
tags = reason_parser.parse_reason(sanitized)
if not tags:
    return _finalize_baseline_only(..., loop_status="no_tags_parsed",
                                    baseline=verdict, local_extra_cost=local_extra_cost,
                                    tags_parsed=[])

# Step 7: rule_table.lookup + llm_fallback
rule_tbl = rule_table.load_rule_table(
    user_yaml_path=config.advanced.get("rule_table_path"),
    project_root=project_root,
)
hits = rule_table.lookup(rule_tbl, tags, backend_kind)
misses = tags - hits.matched_tags
if misses and config.advanced["llm_fallback"]:
    extra_addons = llm_fallback.translate(
        unmapped_reason=sanitized,
        sanitized_reason=sanitized,
        profile=jury_profile,
    )
else:
    extra_addons = []
if not hits.prompt_addons and not extra_addons:
    return _finalize_baseline_only(..., loop_status="no_rules_hit_no_llm",
                                    baseline=verdict, local_extra_cost=local_extra_cost,
                                    tags_parsed=list(tags))

raise NotImplementedError("Task 5.1.8 retry 调用")


def _build_request(*, baseline_path, prompt, params, base_url, api_key, model_name):
    return BackendRequest(
        input_image_path=baseline_path, prompt=prompt, params=params,
        base_url=base_url, api_key=api_key, model_name=model_name,
    )
```

注意：retry 调用阶段 BackendRequest.input_image_path 是 baseline；retry 阶段 prompt 替换 + params 替换；BackendResponse.output_image_path 是 retry 输出文件。`_apply_overrides` Task 5.1.8 用之。

- [ ] **Step 4：测试 GREEN**

```bash
python -m pytest tests/jury_loop/test_orchestrator.py -k "gate4 or gate5 or gate6 or gate7" -v
```
Expected: 5 PASS。

- [ ] **Step 5：Commit**

```bash
git commit -m "feat(jury-loop): Gate-4/5/6/7（above_threshold / cost_capped / no_tags / no_rules）（CP-5 Task 5.1.7）"
```

---

### Task 5.1.8：retry 调用 + Gate-8 + score_select + _finalize（含 #13/#14/#15/#16）

**Files:**
- Modify: `tools/jury_loop/orchestrator.py`（加 _apply_overrides / _finalize / _build_retry_dict / _compute_score_deltas + 主流程 Step 7-10）
- Test: 加 #13/#14/#15/#16

- [ ] **Step 1：写测试 #13/#14/#15/#16 RED**

测试结构（用 fake_jury_sequence + fake_backend_adapter call_returns）。略代码（参 spec §5）。

- [ ] **Step 2：RED**

```bash
python -m pytest tests/jury_loop/test_orchestrator.py -k "improves or degrades or actual_cost or force_retry" -v
```

- [ ] **Step 3：实现 _apply_overrides + _finalize + _build_retry_dict + _compute_score_deltas + Step 7-10 主流程**

```python
from tools.jury_loop.score_select import (CandidateImage, STRATEGY_REGISTRY)


def _apply_overrides(
    prompt: str, prompt_addons: list[str],
    param_overrides: dict[str, dict], base_params: dict, backend_kind: str,
) -> tuple[str, dict]:
    """spec §3 [6]：返 (new_prompt, retry_params)；不动 rc。"""
    new_prompt = prompt + " | " + ", ".join(prompt_addons) if prompt_addons else prompt
    retry_params = {**base_params, **param_overrides.get(backend_kind, {})}
    return new_prompt, retry_params


def _finalize(pick: CandidateImage, baseline_path: Path, retry_path: Path,
               view: str, render_dir: Path) -> Path:
    """spec §3 [10]：pick → V<view>_enhanced.jpg；另一张保留为 V<view>_enhanced_<otherkind>.jpg。"""
    final_path = render_dir / f"{view}_enhanced.jpg"
    final_path.unlink(missing_ok=True)
    if Path(pick.image_path) == retry_path:
        Path(retry_path).replace(final_path)
        # baseline 保留为 V<view>_enhanced_baseline.jpg（已是该名，无需改）
    else:
        Path(baseline_path).replace(final_path)
        # retry 保留为 V<view>_enhanced_retry.jpg
        new_retry = render_dir / f"{view}_enhanced_retry.jpg"
        new_retry.unlink(missing_ok=True)
        Path(retry_path).replace(new_retry)
    return final_path


def _build_retry_dict(retry_path, selection, request, response):
    """spec §4.4 line 530/531：force_retry vs pick_max_jury 双形态 retry 字典构造。"""
    if selection.retry_verdict is None:  # force_retry
        return {
            "image_path": str(retry_path), "photoreal_score": None,
            "semantic_checks": None, "reason": None,
            "final_prompt": request.prompt,
            "backend_payload": response.raw_request_summary,
        }
    return {
        "image_path": str(retry_path),
        "photoreal_score": selection.retry_verdict.photoreal_score,
        "semantic_checks": dict(selection.retry_verdict.semantic_checks),
        "reason": selection.retry_verdict.reason,
        "final_prompt": request.prompt,
        "backend_payload": response.raw_request_summary,
    }


def _compute_score_deltas(selection, baseline_verdict, retry_path):
    """retry / delivered score delta（spec §4.4 line 503-504）。"""
    if selection.retry_verdict is None:
        return None, None
    retry_score_delta = (selection.retry_verdict.photoreal_score
                          - baseline_verdict.photoreal_score)
    if Path(selection.pick.image_path) == retry_path:
        delivered_score_delta = retry_score_delta
    else:
        delivered_score_delta = 0
    return retry_score_delta, delivered_score_delta


# 顶层接 Step 7：
def run_loop_if_eligible(...):
    ...  # Step 1-7（之前 task 已实现）

    # Step 7: apply overrides
    new_prompt, retry_params = _apply_overrides(
        prompt=rc.get("prompt", ""),
        prompt_addons=hits.prompt_addons + extra_addons,
        param_overrides=hits.param_overrides,
        base_params=base_params, backend_kind=backend_kind,
    )

    # Step 8: adapter.call + 4 类异常 + record_actual
    request = _build_request(
        baseline_path=baseline_path, prompt=new_prompt, params=retry_params,
        base_url=config.backend.base_url,
        api_key=os.environ.get(config.backend.api_key_env, ""),
        model_name=config.backend.model_name,
    )
    try:
        response = adapter.call(request, timeout=config.backend.timeout_s)
    except BackendError as e:
        loop_status, error_entry = _classify_backend_error(e)
        return _finalize_baseline_only(
            ..., loop_status=loop_status, baseline=verdict,
            errors=[error_entry], local_extra_cost=local_extra_cost,
            tags_parsed=list(tags),
        )

    if response.actual_cost_usd is not None:
        budget.record_actual(response.actual_cost_usd)
        local_extra_cost = local_extra_cost - estimate + response.actual_cost_usd
        warnings = []
    else:
        warnings = ["cost_estimated_only"]

    # Step 9: score_select
    candidates = [
        CandidateImage(str(baseline_path), verdict),
        CandidateImage(str(response.output_image_path), None),
    ]
    strategy = STRATEGY_REGISTRY[config.advanced["score_select_strategy"]]()
    jury_callable = lambda p: _call_jury_subprocess(
        safe_view, Path(p), project_root, jury_profile_path,
        config.backend.timeout_s,
    )[0] or _raise_jury_unavailable()
    selection = strategy.select(candidates, jury_callable, budget)

    # Step 10: finalize + sidecar
    try:
        final_path = _finalize(selection.pick, baseline_path,
                                response.output_image_path, safe_view, render_dir)
    except OSError as e:
        # rev 3 简化：OSError 向上抛；顶层 try/except 兜
        raise

    delivered_kind = ("retry" if Path(selection.pick.image_path) == response.output_image_path
                       else "baseline")
    loop_status = "delivered_retry" if delivered_kind == "retry" else "delivered_baseline"
    retry_score_delta, delivered_score_delta = _compute_score_deltas(
        selection, verdict, response.output_image_path,
    )
    metadata.write_sidecar(
        view=safe_view, render_dir=render_dir, backend=backend_kind,
        loop_status=loop_status, delivered_kind=delivered_kind,
        baseline=_view_verdict_to_baseline_dict(verdict, baseline_path),
        retry=_build_retry_dict(response.output_image_path, selection, request, response),
        tags_parsed=list(tags), rules_hit=list(hits.matched_tags),
        prompt_addons_applied=hits.prompt_addons + extra_addons,
        param_overrides_applied={backend_kind: hits.param_overrides.get(backend_kind, {})},
        retry_score_delta=retry_score_delta,
        delivered_score_delta=delivered_score_delta,
        extra_cost_usd=local_extra_cost,
        warnings=warnings,
        llm_fallback_used=bool(extra_addons),
    )
    return LoopResult(final_path, loop_status)


def _raise_jury_unavailable():
    raise RuntimeError("二轮 jury 调用失败")
```

- [ ] **Step 4：测试 GREEN**

```bash
python -m pytest tests/jury_loop/test_orchestrator.py -k "improves or degrades or actual_cost or force_retry" -v
```
Expected: 4 PASS。

- [ ] **Step 5：Commit**

```bash
git commit -m "feat(jury-loop): retry 调用 + Gate-8 + score_select + _finalize 主流程（CP-5 Task 5.1.8）"
```

---

### Task 5.1.9：顶层 try/except + 测试 #22 (unknown exception)

**Files:**
- Modify: `tools/jury_loop/orchestrator.py`（顶层包 try/except）
- Test: 加 #22

- [ ] **Step 1：写测试 #22 RED**

```python
def test_unknown_exception_invokes_degraded_sidecar(
    tmp_path, fake_render_dir, fake_backend_adapter,
    tiny_loop_config, tiny_jury_profile, monkeypatch,
):
    """spec §5 #22：未知 Exception → write_degraded_sidecar 被调一次后 re-raise。"""
    write_degraded_calls = []
    original = metadata.write_degraded_sidecar
    def mock_write(*a, **kw):
        write_degraded_calls.append(kw)
        return original(*a, **kw)
    monkeypatch.setattr("tools.jury_loop.metadata.write_degraded_sidecar", mock_write)
    monkeypatch.setattr(
        "tools.jury_loop.rule_table.lookup",
        lambda *a, **kw: (_ for _ in ()).throw(ValueError("oops")),
    )
    monkeypatch.setattr(
        "tools.jury_loop.orchestrator._call_jury_subprocess",
        lambda *a, **kw: (..., None),  # 任意 verdict
    )
    with fake_backend_adapter() as kind:
        with pytest.raises(ValueError):
            run_loop_if_eligible(...)
    assert len(write_degraded_calls) == 1
```

- [ ] **Step 2：RED + Step 3：把顶层全包 try/except**

```python
def run_loop_if_eligible(...):
    if not baseline_path.is_file(): raise FileNotFoundError(...)
    safe_view = _validate_view_basename(view)
    render_dir = baseline_path.parent
    try:
        # 主流程（之前 task 实现的全部 Step 1-10）
        ...
    except (FileNotFoundError, ValueError):
        raise  # fail-fast 不写 degraded sidecar
    except (BackendError, OSError):
        raise  # 已在内层处理 / 让 cmd_enhance 兜
    except Exception as e:
        # 未知 Exception：写 degraded sidecar 后 re-raise
        try:
            metadata.write_degraded_sidecar(view=safe_view, render_dir=render_dir, error=e)
        except OSError:
            pass  # write_degraded 自身失败：仅静默
        raise
```

- [ ] **Step 4：GREEN**

```bash
python -m pytest tests/jury_loop/test_orchestrator.py -k "unknown_exception" -v
```

- [ ] **Step 5：Commit**

```bash
git commit -m "feat(jury-loop): 顶层 try/except + write_degraded_sidecar 兜未知异常（CP-5 Task 5.1.9）"
```

---

### Task 5.1.10：父 plan / 父 spec 同步（非 CP-5 但本 plan 范围内）

**Files:**
- Modify: `docs/superpowers/plans/2026-05-10-jury-prompt-loop-plan.md`（plan 同步项 1-3）
- Modify: `docs/superpowers/specs/2026-05-10-jury-prompt-loop-design.md`（父 spec 同步项 4-5）

- [ ] **Step 1：plan Task 7.2 物理移到 CP-5 之前**

把 plan line 1323-1333 整段从 `## CP-7：cmd_enhance 集成` 内移到 `## CP-5：orchestrator 主入口` 之前；新位置改标号为 "Task 5.0"，原标号 "Task 7.2" cross-reference 提示。

- [ ] **Step 2：plan Task 5.1 (line 1206-1217) 签名升 10 kwarg**

把 plan line 1206-1217 签名从 7 改为 10 kwarg，加 `jury_profile / jury_profile_path / base_params`；docstring 删除 "含 sidecar 数据"（与 CP-5 spec rev 3 决议 #3 LoopResult 最小契约一致）。

- [ ] **Step 3：plan Task 7.1 (line 1289-1304) cmd_enhance try/except**

把 cmd_enhance 视角级 try/except 改为：

```python
try:
    loop_result = orchestrator.run_loop_if_eligible(
        view=view, backend_kind=jury_loop_config.backend.kind, rc=rc,
        baseline_path=baseline_path, base_params=base_params,
        budget=budget, project_root=PROJECT_ROOT,
        config=jury_loop_config,
        jury_profile=jury_profile, jury_profile_path=jury_profile_path,
    )
    if reference_mode == "v1_anchor" and view == "V1":
        hero_image = loop_result.final_path
except FileNotFoundError as e:
    log.error("baseline_path 不存在：%s（baseline 阶段失败，跳过此视角闭环）", e)
    # 不写 degraded sidecar（防死循环）
except Exception as e:
    log.error("Loop hook crashed for %s: %s", view, e)
    # orchestrator 已写 degraded sidecar；cmd_enhance 仅 log 不重写
```

- [ ] **Step 4：父 spec 3 处 doc fix**

- line 183 `tags = reason_parser(sanitized_reason)` → `tags = reason_parser.parse_reason(sanitized_reason)`
- line 191 `extra_addons = llm_fallback.translate(misses, sanitized_reason)` → `extra_addons = llm_fallback.translate(unmapped_reason=sanitized_reason, sanitized_reason=sanitized_reason, profile=jury_profile) if misses and config.llm_fallback else []`
- §4.4 line 472 `backend ∈ {gemini, comfyui, fal, fal_comfy, engineering}` 加 `, "unknown"`（cmd_enhance pre-classification 异常专用）

- [ ] **Step 5：Commit**

```bash
git add docs/superpowers/plans/2026-05-10-jury-prompt-loop-plan.md docs/superpowers/specs/2026-05-10-jury-prompt-loop-design.md
git commit -m "docs: 同步父 plan / 父 spec 至 CP-5 rev 3（Task 7.2 移前 / 签名加 kwarg / 3 处 doc fix）"
```

---

### Task 5.1.11：全套件回归 + mypy + ruff 验收

- [ ] **Step 1：jury_loop 全套件**

```bash
python -m pytest tests/jury_loop/ -v
```
Expected: ≥220 passed（既有 201 + score_select 3 新 + config 4 新 + orchestrator 19 新）。

- [ ] **Step 2：mypy strict**

```bash
python -m mypy --strict tools/jury_loop/config.py tools/jury_loop/orchestrator.py tools/jury_loop/score_select.py
```
Expected: clean。

- [ ] **Step 3：ruff**

```bash
python -m ruff check tools/jury_loop/ tests/jury_loop/
```
Expected: clean。

- [ ] **Step 4：CI matrix**（push 后）

```bash
git push origin feat/sp1-jury-prompt-loop
gh pr checks (PR 编号)
```
Expected: Linux + Windows matrix 全绿。

- [ ] **Step 5：合并 commit（可选，subagent-driven dev 流程通常每 task 1 commit）**

如果 task 间有零碎修改，最末一次 squash 整理；否则跳过。

---

## §4 Self-Review

**Spec 覆盖度检查**（spec rev 3 关键节 vs plan task 映射）：

| spec 节 | 内容 | plan task |
|---|---|---|
| §1 范围 + 前置 | Task 5.0 + 父 plan/spec 同步 | Task 5.0 / Task 5.1.10 |
| §2 决议 #1 mock 边界深集成 | 注入 _call_jury_subprocess + adapter; 真用 reason_parser/rule_table/llm_fallback/score_select/metadata | Task 5.1.6 / 5.1.7 / 5.1.8 |
| §2 决议 #2 单一函数 + 6 helper | _check_pre_jury_gates / _rename_baseline_as_final / _call_jury_subprocess / _classify_backend_error / _apply_overrides / _finalize | Task 5.1.4 / 5.1.5 / 5.1.6 / 5.1.8 |
| §2 决议 #3 LoopResult 最小契约 | dataclass 2 字段 | Task 5.1.2 |
| §2 决议 #4 jury mock 形态 | monkeypatch.setattr orchestrator._call_jury_subprocess | 测试 #3-#16 |
| §2 决议 #6 fail-safe 简化 | try/except Exception → write_degraded_sidecar + re-raise | Task 5.1.9 |
| §2 决议 #7 _apply_overrides 4 入参 | base_params 入参 | Task 5.1.8 |
| §2 决议 #8 jury_profile + path 2 kwarg | 顶层签名 | Task 5.1.2 |
| §2 决议 #9 _call_jury_subprocess tuple | 返 (verdict, error_code) | Task 5.1.6 |
| §2 决议 #10 _classify_backend_error tuple | 返 (loop_status, error_dict) | Task 5.1.5 |
| §2 决议 #11 empty_reason Gate-3.5 | jury 返非 None 后即检 reason.strip() | Task 5.1.6 |
| §2 决议 #12 SelectionResult retry_verdict | score_select.py 改字段 | Task 5.1.1 |
| §3 主流程时序 10 步 | Step 1-10 顶层逐步实现 | Task 5.1.4 → 5.1.8 |
| §4 6 helper | 全部实现 | Task 5.1.4-5.1.8 |
| §5 19 测试矩阵 | #1/2/3/4/5/5b/6/7/8/9/10/11/12/13/14/15/16/20/22 | Task 5.1.4-5.1.9 |
| §6 fixture | conftest.py | Task 5.1.3 |
| §7 异常隔离 | 顶层 try/except + 4 BackendError 内捕 + subprocess 内捕返 tuple | Task 5.1.5/5.1.6/5.1.9 |
| §8 follow-up 1-3 | 父 plan / 父 spec 同步 | Task 5.1.10 |

**Placeholder 扫描**：
- 全 task 含具体代码 / 命令 / 期望输出
- Step 1 测试码 / Step 3 实现码 / Step 5 commit msg 全列
- 无 "TODO / TBD / 同 Task N" 等占位
- ⚠️ Task 5.1.7 / 5.1.8 部分代码片段写 "略代码块 / 同上" 等省略——补正：每测试都要在 Step 1 列出完整代码，subagent-driven 实施时可参考其他测试同结构补全。建议实施期 implementer agent 不偷懒，inline 补全。

**Type 一致性**：
- `LoopResult(final_path: Path, loop_status: str)` 跨 task 一致
- `ViewVerdict` 6 字段（semantic_checks / photoreal_score / reason / parse_status / parse_anomalies / verdict）跨 task 一致
- `_call_jury_subprocess` 返 `tuple[ViewVerdict | None, str | None]` 跨 Task 5.1.6/5.1.8 一致
- `_classify_backend_error` 返 `tuple[str, dict]` 跨 Task 5.1.5/5.1.8 一致
- `SelectionResult.retry_verdict: ViewVerdict | None` 跨 Task 5.1.1/5.1.8 一致

**修订**：
- Task 5.1.7 / 5.1.8 测试代码省略部分由 implementer 参 spec §5 + Task 5.1.4/5.1.6 测试模板补全
- Task 5.0 测试 4 case 是合理覆盖（4 case 已在 spec rev 3 §6 fixture 内对齐）

---

## §5 执行 Handoff

Plan 文件已写完，保存于 `docs/superpowers/plans/2026-05-11-cp5-orchestrator-plan.md`。

**两个执行选项：**

1. **Subagent-Driven (Recommended)** — 每 task 派一个 fresh subagent；task 间审；快速迭代；契合 session 32+38+40 实证套路（subagent → spec reviewer → quality reviewer → final review）。
2. **Inline Execution** — 当 session 内顺序跑；checkpoint 后用户审；适合简单 task。
