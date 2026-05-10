# CP-5 Orchestrator 实施设计（jury→prompt 闭环单视角主入口）

**日期**：2026-05-10
**关联**：父 spec `2026-05-10-jury-prompt-loop-design.md` §3（数据流与时序）+ §4.4（sidecar schema）+ §4.5（score_select 策略）+ §4.6（loop_status enum）
**依赖完成度**：CP-1（reason_parser / rule_table）+ CP-2.5（BackendAdapter Protocol + 3 内置 adapter）+ CP-3（llm_fallback / score_select）+ CP-4（enhance_budget / metadata sidecar）+ batch review fixup（commit `7fa7c93`）全部 GREEN
**Brainstorm 决议日期**：2026-05-10 session 4 收尾后 session 5 开局

---

## §1 范围与非目标

### 范围
- 单视角闭环入口：`tools/jury_loop/orchestrator.py::run_loop_if_eligible`
- 实现父 spec §3 全 10 步 + 8 Gate（loop_disabled / above_threshold / cost_capped / no_tags_parsed / no_rules_hit_no_llm / jury_unavailable / empty_reason / retry_*）
- 4 类 BackendError 异常分类映射到 retry_auth_failed / retry_rate_limited / retry_quota_exceeded / retry_failed
- 调用 score_select 策略；写 sidecar 经 metadata 模块；返回 `LoopResult`

### 非目标（CP-5 不做，留给后续 CP）
- **多视角调度**：v1_anchor / parallel 模式由 CP-7 cmd_enhance 管，CP-5 是单视角原子单元
- **photo3d-jury `--single-view` flag 真路径**：CP-6 Task 6.1 落地；CP-5 实施期间 `_call_jury_subprocess` 内部含 subprocess.run + JSON 解析骨架但生产 path 跑不通（mock 兜测试）
- **loop_summary 顶层聚合**：CP-7 cmd_enhance 在视角循环结束读 sidecar 文件聚合 ENHANCEMENT_REPORT.json `loop_summary` 段
- **stdout 1MiB cap (SEC-MINOR-4)**：CP-6 实施

---

## §2 5 条 brainstorm 决议（2026-05-10 session 5）

| # | 决议 | 理由 |
|---|---|---|
| 1 | **mock 边界 = 深集成**：仅 mock 外部 boundary（subprocess + adapter.call），CP-1/2/3/4 实现（reason_parser / rule_table / llm_fallback / score_select / metadata.write_sidecar / LoopBudget）全用真实调用 | 已 197 测试覆盖核心 unit；orchestrator 测试覆盖真集成点 + 防 plan-drift |
| 2 | **架构粒度 = 单一函数 + 5 内部 helper**：顶层 `run_loop_if_eligible` ~150 行 + 5 私有 `_helper`；orchestrator.py 单文件 ~350 行 | 与 spec §3 10 步线性结构同构；状态机反向重构无收益（SP3 扩展见 §4.5.2 Strategy Protocol 已开放） |
| 3 | **LoopResult = 最小契约**：`@dataclass(frozen=True) LoopResult(final_path, loop_status)` 仅两字段 | sidecar = single source of truth；cmd_enhance 在视角循环结束读文件聚合 loop_summary，防内存/文件双写不一致 |
| 4 | **jury subprocess mock 形态 = 抽内部 helper + monkeypatch.setattr 整体替换** | 不依 subprocess.run mock chain / 不需手造 JSON fixture；CP-6 落地 `--single-view` flag 后该 helper 自然 work |
| 5 | **brainstorm 输出 = 独立 CP-5 子 spec**：本文件 `2026-05-10-cp5-orchestrator-design.md` | CP-5 复杂度跳一档（mock 边界 + 16 测试 + 4 异常分类），独立 spec 让 writing-plans 拆 task 更精确 |

---

## §3 顶层 API 与 LoopResult 契约

```python
# tools/jury_loop/orchestrator.py
from dataclasses import dataclass
from pathlib import Path

from enhance_budget import LoopBudget
from tools.jury.verdict import ViewVerdict
from tools.jury_loop.config import JuryLoopConfig  # 现有 / Task 0 已建


@dataclass(frozen=True)
class LoopResult:
    """单视角闭环结果。

    最小契约：仅返"哪张图最终交付 + 闭环状态"，不暴露 sidecar 内容。
    cmd_enhance (CP-7) 在视角循环结束统一读 sidecar 文件聚合 loop_summary，
    避免内存与文件源双写一致性问题。
    """
    final_path: Path
    loop_status: str   # spec §4.6 enum 14 项之一


def run_loop_if_eligible(
    *,
    view: str,
    backend_kind: str,           # 来自 jury_loop.backend.kind 配置
    rc: dict,                    # pipeline_config 视角级 render config
    baseline_path: Path,         # V<i>_enhanced_baseline.jpg 实际路径
    budget: LoopBudget,          # 跨视角共享预算簿
    project_root: Path,          # 项目根（jury subprocess cwd）
    config: JuryLoopConfig,      # 解析后的 enhance.jury_loop.* 配置
) -> LoopResult:
    """单视角 jury→prompt 闭环。永不抛已知异常（BackendError 4 子类 +
    OSError 重命名失败均内部捕获写 sidecar）；未知异常向上抛给 cmd_enhance
    视角级 try/except 兜底（CP-7 写 degraded sidecar）。"""
    ...
```

---

## §4 内部 helper 切分（5 个 private function）

按 spec §3 10 步线性流程同构切分：

### `_check_pre_jury_gates(backend_kind, config) -> str | None`
- 实现 spec §3 Gate-1（`backend_kind ∉ BACKEND_REGISTRY`）+ Gate-2（`config.enabled == False`）
- 返 `loop_status` 字符串或 None（None 表示通过，继续主流程）
- 不读文件不调外部依赖；纯函数，可 unit test 独立

### `_call_jury_subprocess(view, image_path, project_root, jury_profile) -> ViewVerdict | None`
- 含 `subprocess.run(["python", "-m", "tools.photo3d_jury", "--single-view", view, "--image", str(image_path), ...], cwd=project_root, timeout=...)`
- 解析 stdout JSON → 构造 ViewVerdict（详见 spec §4.4 嵌套 baseline 字段）
- 失败返 None（subprocess.CalledProcessError / json.JSONDecodeError / list 形状不符 / verdict.kind == "needs_review"）
- **测试 monkeypatch.setattr 整体替换**；生产 CP-6 后真 work

### `_classify_backend_error(exc: BackendError) -> str`
- 纯函数：`isinstance(exc, BackendAuthError) → "retry_auth_failed"` 等 4 路 mapping
- 不读 HTTP 码（adapter 已映射好，spec §4.6 OPS-MAJOR-5）
- 测试覆盖 4 子类 + 1 fallback（未知 BackendError 子类 → `retry_failed`）

### `_apply_overrides(rc, prompt_addons, param_overrides) -> dict`
- 实现 spec §3 [6]：`rc_for_retry = copy.deepcopy(rc)`
- prompt 拼接：`rc_for_retry["prompt"] = base_prompt + " | " + ", ".join(addons)`
- params 浅合并：`rc_for_retry[backend].update(rule_overrides[backend])`（rule 赢，A-1）
- 不污染传入 `rc`；测试断言原 rc 不变 + 返回新 dict 含合并结果

### `_finalize(pick: CandidateImage, baseline_path, retry_path, view, render_dir) -> Path`
- 实现 spec §3 [10]：将 `pick.image_path` 重命名为 `V<view>_enhanced.jpg`
- 另一张保留为 `V<view>_enhanced_<otherkind>.jpg`（baseline 或 retry）
- 返 `V<view>_enhanced.jpg` 绝对路径（即 `LoopResult.final_path`）
- OSError（磁盘满 / 权限）向上抛给顶层；顶层不再捕获（cmd_enhance write_degraded_sidecar）

---

## §5 测试矩阵（16 用例 + fixture）

| # | 测试名 | mock 输入 | 期望 loop_status | 验收附加项 |
|---|---|---|---|---|
| 1 | `test_gate1_backend_unregistered` | backend_kind="engineering"（不在 REGISTRY） | `loop_disabled` | sidecar.loop_eligible=false; final_path 是 V1_enhanced.jpg |
| 2 | `test_gate2_enabled_false` | config.enabled=False | `loop_disabled` | 同 #1 |
| 3 | `test_gate3_jury_returns_none` | `_call_jury_subprocess` → None | `jury_unavailable` | sidecar.delivered_kind="baseline" |
| 4 | `test_gate3_jury_empty_reason` | verdict(score=50, reason="") | `empty_reason` | 同 #3 |
| 5 | `test_gate4_score_above_threshold` | verdict(photoreal_score=80) + threshold=75 | `above_threshold` | sidecar.user_friendly_summary 含 "80" |
| 6 | `test_gate5_budget_capped` | budget.try_spend → False | `cost_capped` | sidecar.extra_cost_usd == budget.spent |
| 7 | `test_gate6_no_tags_parsed` | reason="完全未知文本不含已知 tag" | `no_tags_parsed` | sidecar.tags_parsed=[] |
| 8 | `test_gate7_all_miss_llm_fallback_off` | tags 全 unknown + config.llm_fallback=False | `no_rules_hit_no_llm` | - |
| 9 | `test_gate8_backend_auth_error` | adapter.call → BackendAuthError | `retry_auth_failed` | sidecar.errors[0].code 含 "auth" |
| 10 | `test_gate8_backend_rate_limit_error` | adapter.call → BackendRateLimitError | `retry_rate_limited` | - |
| 11 | `test_gate8_backend_quota_exceeded` | adapter.call → BackendQuotaExceededError | `retry_quota_exceeded` | - |
| 12 | `test_gate8_backend_call_error` | adapter.call → BackendCallError | `retry_failed` | - |
| 13 | `test_normal_retry_improves_score` | retry_score=80 > baseline=58 (pick_max_jury) | `delivered_retry` | retry_score_delta=+22; delivered_kind="retry" |
| 14 | `test_normal_retry_degrades_score` | retry_score=50 < baseline=58 (pick_max_jury) | `delivered_baseline` | retry_score_delta=-8; delivered_kind="baseline"; retry 字段含完整 verdict（spec §4.4 line 531） |
| 15 | `test_actual_cost_none_warns` | BackendResponse.actual_cost_usd=None | `delivered_retry`（或任何 retry 跑通形态） | sidecar.warnings 含 "cost_estimated_only" |
| 16 | `test_force_retry_strategy_skips_second_jury` | config.score_select_strategy="force_retry" | `delivered_retry` (force_retry) | sidecar.retry.photoreal_score=null（spec §4.4 line 530） |

---

## §6 mock fixture 提取（tests/jury_loop/conftest.py 新增）

```python
# 新增 fixture（保留现有 fixture_dir / sample_reason_plastic_flat / builtin_yaml_path）

@pytest.fixture
def fake_view_verdict():
    """ViewVerdict factory，默认低分含已知 tag。"""
    def _make(score: int = 58, reason: str = "plastic look, flat lighting", **kwargs):
        return ViewVerdict(
            kind="ok",
            view="V1",
            photoreal_score=score,
            semantic_checks={...默认 5 字段...},
            reason=reason,
            **kwargs,
        )
    return _make


@pytest.fixture
def fake_backend_adapter():
    """注册 stub adapter 到 BACKEND_REGISTRY 的 context manager。

    用法：
        with fake_backend_adapter(kind="fal_comfy",
                                  call_returns=BackendResponse(...),
                                  raises=None) as adapter_kind:
            ...
    """
    @contextmanager
    def _register(kind: str, call_returns=None, raises=None):
        ...
        yield kind
        BACKEND_REGISTRY.pop(kind, None)
    return _register


@pytest.fixture
def fake_render_dir(tmp_path):
    """造一个含 V1_enhanced_baseline.jpg 的临时 render_dir。"""
    rd = tmp_path / "render"
    rd.mkdir()
    (rd / "V1_enhanced_baseline.jpg").write_bytes(b"\x89PNG\r\n...假 PNG 头")
    return rd


@pytest.fixture
def tiny_loop_config():
    """JuryLoopConfig 最小配置 factory。"""
    def _make(*, threshold: int = 75, enabled: bool = True,
              llm_fallback: bool = False,
              score_select_strategy: str = "pick_max_jury", **kwargs):
        return JuryLoopConfig(
            enabled=enabled, threshold=threshold,
            llm_fallback=llm_fallback,
            score_select_strategy=score_select_strategy,
            **kwargs,
        )
    return _make
```

---

## §7 边界处理与异常隔离策略

### orchestrator 自捕获范围
- `BackendError` 4 子类：内部 catch + `_classify_backend_error` 分类 + 写 sidecar 含 `errors[]` + 返 LoopResult
- `subprocess.CalledProcessError` / `json.JSONDecodeError` / `subprocess.TimeoutExpired`：在 `_call_jury_subprocess` 内捕获返 None；上层映射 `jury_unavailable`
- `ValueError`（rule_table / metadata path 净化）：内部 raise（spec §3 line 522 SEC-MAJOR-2 要求拒绝；不该发生于内部正确调用）

### orchestrator **不**自捕获范围（向上抛给 cmd_enhance）
- `OSError`（_finalize 重命名失败：磁盘满 / 权限）：cmd_enhance 视角级 try/except 兜底 + write_degraded_sidecar
- 任何未知 `Exception`：同上

### sidecar 写盘时机
- 所有路径（含 8 Gate 提前退出）写一次 sidecar；保证 sidecar 永远存在（spec §4.4 BL-2 additive-only 契约要求）
- 顶层函数最末尾 1 次 `metadata.write_sidecar(...)` 调用；不在 helper 内分散写

---

## §8 §11 follow-up（spec 已登记，不阻断 CP-5）

1. ~~`cost_capped` 形态 `extra_cost_usd` 由 caller (CP-5) 传 `budget.spent`~~ → 本 spec §5 测试 #6 锁死该约定（已闭合）
2. ~~`write_degraded_sidecar backend="unknown"` 不在 spec §4.4 enum~~ → 留 SP1 后续 minor spec doc fix（不阻断 CP-5）
3. CP-6 Task 6.1 (`--single-view + --image` flag) 是 `_call_jury_subprocess` 真 path 跑通的前置；CP-5 实施期间该 helper 含骨架但 mock 兜测试

---

## §9 提交策略

- Brainstorm spec 写出 + 自审 → commit `feat(jury-loop): CP-5 orchestrator 子 spec（mock 边界 / LoopResult / 16 测试矩阵）`
- 用户审 spec 通过 → 进 writing-plans skill 输出 plan 文件
- plan 拆 task → subagent-driven 实施（执行策略待 plan 阶段决）

---

## §10 spec 自审记录

按 brainstorming skill self-review checklist：

| 项 | 检查 | 结果 |
|---|---|---|
| Placeholder | 全文无 TBD/TODO；fixture 段含 `...默认 5 字段...` 与 `...` 是设计示例代码非 placeholder | ✓ |
| Internal consistency | §3 LoopResult 仅 final_path/loop_status；§5 测试 #6 验收 `sidecar.extra_cost_usd == budget.spent` 是读 sidecar 而非 LoopResult，与 §3 决议一致 | ✓ |
| Scope | 单一 task (orchestrator.py + test 文件) + 单 commit；不扩 CP-6 / CP-7 | ✓ |
| Ambiguity | §4 `_finalize` "另一张保留为 `V<view>_enhanced_<otherkind>.jpg`" 明确；§7 异常隔离边界明确（4 BackendError 内捕，OSError 向上抛） | ✓ |
| Spec spec/plan 边界 | 本文件不写 plan-task 拆分；plan 阶段读本 spec 拆 task | ✓ |
