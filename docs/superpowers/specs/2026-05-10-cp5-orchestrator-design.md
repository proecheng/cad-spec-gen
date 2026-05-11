# CP-5 Orchestrator 实施设计（jury→prompt 闭环单视角主入口）

**日期**：2026-05-10（rev 3 / 二审 4 reviewer 30+ findings 修订；YAGNI 简化）
**关联**：父 spec `2026-05-10-jury-prompt-loop-design.md` §3（数据流与时序）+ §4.4（sidecar schema）+ §4.5（score_select 策略）+ §4.6（loop_status enum）+ §6（jury single-view CLI 契约）
**依赖完成度**：CP-1（reason_parser / rule_table）+ CP-2.5（BackendAdapter Protocol + 3 内置 adapter）+ CP-3（llm_fallback / score_select）+ CP-4（enhance_budget / metadata sidecar）+ batch review fixup（commit `7fa7c93`）全部 GREEN
**前置 plan task**（CP-5 实施前必落）：
- **plan Task 7.2 物理移到 CP-5 之前作 "Task 5.0"**：建 `tools/jury_loop/config.py::JuryLoopConfig` + 嵌套 `BackendConfig` + `load_jury_loop_config(...)`（plan 文件 line 1323-1333 已有详细描述）
- 否则 CP-5 第一行 `from tools.jury_loop.config import JuryLoopConfig` 即 ImportError

---

## §1 范围与非目标

### 范围
- 单视角闭环入口：`tools/jury_loop/orchestrator.py::run_loop_if_eligible`
- 实现父 spec §3 全 10 步 + 8 Gate（loop_disabled / above_threshold / cost_capped / no_tags_parsed / no_rules_hit_no_llm / jury_unavailable / empty_reason / retry_*）
- 4 类 BackendError 异常分类映射到 retry_auth_failed / retry_rate_limited / retry_quota_exceeded / retry_failed
- 调用 score_select 策略；写 sidecar 经 metadata 模块；返回 `LoopResult`
- **fail-safe 不变量**：(a) sidecar 写一次（已知失败：orchestrator 自己写；未知异常：cmd_enhance write_degraded_sidecar 兜底）；(b) `final_path == V<view>_enhanced.jpg` 在 orchestrator 正常返回路径永远存在

### 非目标（CP-5 不做，留给后续 CP）
- **多视角调度**：v1_anchor / parallel 模式由 CP-7 cmd_enhance 管，CP-5 是单视角原子单元
- **photo3d-jury `--single-view` flag 真路径**：CP-6 Task 6.1 落地；CP-5 实施期间 `_call_jury_subprocess` 内部含 subprocess.run 骨架但生产 path 跑不通（mock 兜测试）
- **stdout 1MiB cap (SEC-MINOR-4)**：CP-6 实施
- **reference_mode=none 真并发**：父 spec line 244 提到"可并行"——CP-5 仅设计单视角原子；并发安全由 CP-7 cmd_enhance brainstorm 决定（rev 3 §8 follow-up）
- **NaN/Inf 估算防御**：SP1 三内置 adapter 不可能返 NaN（常量定价表）；SP3 user plugin 接入时再补 enhance_budget isfinite 校验（rev 3 §8 follow-up）
- **`_finalize` OSError 内捕分类**：rev 3 退回 rev 1 路径（向上抛，cmd_enhance write_degraded_sidecar 兜）；errors[].code 精细分类等真发生时再加（rev 3 §8 follow-up）

---

## §2 brainstorm 决议（rev 3 共 12 条）

rev 1: 5 决议；rev 2: 11 决议；rev 3: **12 决议**（YAGNI 删 3 + 新增 5 + 保留 7）

| # | 决议 | 来源 / 理由 |
|---|---|---|
| 1 | **mock 边界 = 深集成**：仅 mock 外部 boundary（subprocess + adapter.call），CP-1/2/3/4 实现全用真实调用 | rev 1 / 决议 |
| 2 | **架构粒度 = 单一函数 + 6 内部 helper**：顶层 + `_check_pre_jury_gates` / `_rename_baseline_as_final` / `_call_jury_subprocess` / `_classify_backend_error` / `_apply_overrides` / `_finalize` | rev 2 / 决议 |
| 3 | **LoopResult = 最小契约**：仅 `final_path: Path + loop_status: str` 两字段 | rev 1 / 决议 |
| 4 | **jury subprocess mock 形态 = 抽内部 helper + monkeypatch.setattr 整体替换** | rev 1 / 决议 |
| 5 | **brainstorm 输出 = 独立 CP-5 子 spec**（本文件） | rev 1 / 决议 |
| 6 | **fail-safe 兜底 = 简化版**：orchestrator try/except Exception → 调 `metadata.write_degraded_sidecar(view, error)` → re-raise；不要 state dict 抽象（rev 2 简化）。已知失败（BackendError 4 子类）正常路径写富 sidecar；未知异常仅写降级 sidecar | rev 3 简化 / YAGNI reviewer："state 容器抽象 30 行 sketch + helper 间 state 接口耦合 vs cmd_enhance 已 fail-safe 链外层" |
| 7 | **_apply_overrides 不动 rc**：返回 `(new_prompt, retry_params)` tuple；调用方拿 retry_params 构造 `BackendRequest.params`；**新增 base_params: dict 第 4 入参**（来自 `pipeline_config.json::enhance.<backend_kind>.params` 段，由 cmd_enhance 加载传入）| rev 1 P3 + dry-run D-10 |
| 8 | **顶层签名加 `jury_profile: JuryProfile + jury_profile_path: Path` 2 kwarg**：profile 实例（含 LLM endpoint+key）由 cmd_enhance 加载传入；profile_path 是同一文件路径，给 subprocess `--config` 用（JuryProfile dataclass 不含 source path，须额外传） | 父子 spec reviewer P-5 |
| 9 | **`_call_jury_subprocess` 返 `tuple[ViewVerdict \| None, str \| None]`**：第二个元素是失败 code（"timeout" / "exit_nonzero" / "json_parse_failed" / "needs_review"）；orchestrator 用之填 `errors[].code` 不丢信息 | 测试可执行性 reviewer T-6 |
| 10 | **`_classify_backend_error` 返 `tuple[str, dict]`**：`(loop_status, error_entry_dict)`；error_entry_dict 形如 `{"code": "backend_auth_error", "message_summary": str(exc), "user_action_hint": "检查 API key"}`；orchestrator 直接 append 到 errors[]，不另搞构造 | 测试可执行性 reviewer T-3 |
| 11 | **empty_reason 触发位置锁定 = jury 返回非 None 后**（在 Gate-4 score 比较之前）：`if verdict.reason.strip() == "": loop_status="empty_reason"; goto finalize_baseline`；这是 Gate-3.5 | 测试可执行性 reviewer T-1 |
| 12 | **score_select.SelectionResult 加 `retry_verdict: ViewVerdict \| None` 字段**（rev 3 改 score_select.py）：保留 retry candidate verdict 让 orchestrator 写 sidecar.retry 字段；force_retry 路径返 None（不二轮 jury）；pick_max_jury 路径返 retry verdict（即使 baseline 高分被选） | 测试可执行性 reviewer T-4 |

---

## §3 顶层 API 与 LoopResult 契约（rev 3 加第 9-10 kwarg）

```python
# tools/jury_loop/orchestrator.py
from dataclasses import dataclass
from pathlib import Path

from enhance_budget import LoopBudget
from tools.jury.config import JuryProfile
from tools.jury.verdict import ViewVerdict
from tools.jury_loop.config import JuryLoopConfig          # 前置依赖：plan Task 5.0
from tools.jury_loop.metadata import write_degraded_sidecar


@dataclass(frozen=True)
class LoopResult:
    """单视角闭环结果。最小契约：仅返"哪张图最终交付 + 闭环状态"。"""
    final_path: Path
    loop_status: str   # spec §4.6 enum 14 项之一


def run_loop_if_eligible(
    *,
    view: str,
    backend_kind: str,
    rc: dict,
    baseline_path: Path,
    base_params: dict,            # rev 3 新增：cmd_enhance 加载 pipeline_config 后传入；
                                  # 来自 enhance.<backend_kind>.params 段（不是 rc 子键）
    budget: LoopBudget,
    project_root: Path,
    config: JuryLoopConfig,
    jury_profile: JuryProfile,    # rev 2 新增：jury LLM endpoint + key
    jury_profile_path: Path,      # rev 3 新增：subprocess "--config" 需要 path 字面
) -> LoopResult:
    """单视角 jury→prompt 闭环。

    异常处理（rev 3 简化）：
    - 已知失败（BackendError 4 子类 + _call_jury_subprocess 返 None）：内部捕获 +
      正常路径调 metadata.write_sidecar 写富 sidecar + 返 LoopResult。
    - 未知异常（rule_table 抛 ValueError / OSError 等）：try/except Exception →
      调 metadata.write_degraded_sidecar(view, error=e) → re-raise；cmd_enhance 接
      Exception 时仅 log 不重复 write_degraded（避免无限循环）。
    - FileNotFoundError（baseline_path 不存在）+ ValueError（view 名注入）：fail-fast
      不写 sidecar；cmd_enhance 仅 log + 跳过该视角。

    前置条件：
    - `baseline_path.is_file() == True`（不满足直接 raise FileNotFoundError）
    - `view` 必须通过 `metadata._validate_view_basename`（不通过 ValueError）

    返回：LoopResult.final_path 在所有正常路径（含 8 Gate 退出）= V<view>_enhanced.jpg
    绝对路径；OSError 抛出时 raise 给 cmd_enhance（cmd_enhance write_degraded_sidecar
    兜底，final_path 不构造 LoopResult）。
    """
    ...
```

### 主流程时序（spec §3 [1]-[10]）

orchestrator 内部按以下顺序执行（rev 3 锁定 ≥ 运算符 / empty_reason 位置 / record_actual 时机）：

```python
# Step 0: Precondition fail-fast（不写 sidecar）
if not baseline_path.is_file(): raise FileNotFoundError(...)
safe_view = metadata._validate_view_basename(view)

# Step 1: Gate-1/2 检查
gate_status = _check_pre_jury_gates(backend_kind, config)
if gate_status:  # "loop_disabled"
    final_path = _rename_baseline_as_final(baseline_path, safe_view, render_dir)
    metadata.write_sidecar(view=safe_view, render_dir=render_dir, backend=backend_kind,
                           loop_status=gate_status, baseline=None, retry=None,
                           extra_cost_usd=0)
    return LoopResult(final_path, gate_status)

# Step 2: jury 第一次评（baseline）
verdict, jury_err_code = _call_jury_subprocess(safe_view, baseline_path, project_root,
                                                jury_profile_path,
                                                config.backend.timeout_s)
if verdict is None:
    # jury_unavailable
    return _finalize_baseline(safe_view, baseline_path, render_dir, "jury_unavailable",
                              backend_kind, errors=[{"code": jury_err_code, ...}],
                              local_extra_cost=0)

# Step 3: empty_reason 检查（rev 3 决议 #11）
if verdict.reason.strip() == "":
    return _finalize_baseline(safe_view, baseline_path, render_dir, "empty_reason",
                              backend_kind, baseline=verdict, local_extra_cost=0)

# Step 4: above_threshold 检查（≥ 运算符）
if verdict.photoreal_score >= config.advanced["threshold"]:
    return _finalize_baseline(safe_view, baseline_path, render_dir, "above_threshold",
                              backend_kind, baseline=verdict, local_extra_cost=0)

# Step 5: 估算 cost + try_spend（cost_capped 检查）
adapter = BACKEND_REGISTRY[backend_kind]
request = BackendRequest(...)
estimate = enhance_budget.estimate_retry_cost(adapter, request,
    with_jury=(config.advanced["score_select_strategy"] == "pick_max_jury"))
local_extra_cost = 0.0   # rev 3 决议 #18：本视角 extra_cost_usd 用 local 不用 budget.spent
if not budget.try_spend(estimate):
    return _finalize_baseline(safe_view, baseline_path, render_dir, "cost_capped",
                              backend_kind, baseline=verdict, local_extra_cost=0)
local_extra_cost += estimate  # 占用估算

# Step 6-7: tags + rules + apply_overrides + retry call
sanitized_reason = reason_sanitized(verdict.reason)
tags = reason_parser.parse_reason(sanitized_reason)
if not tags:
    return _finalize_baseline(safe_view, baseline_path, render_dir, "no_tags_parsed",
                              backend_kind, baseline=verdict, local_extra_cost=local_extra_cost,
                              tags_parsed=[])
hits = rule_table.lookup(tags, backend_kind)  # 模块级调用，不需 RuleTable 实例入参
misses = tags - hits.matched_tags
if misses and config.advanced["llm_fallback"]:
    extra_addons = llm_fallback.translate(unmapped_reason=sanitized_reason,
                                          sanitized_reason=sanitized_reason,
                                          profile=jury_profile)
else:
    extra_addons = []
if not hits.prompt_addons and not extra_addons:
    return _finalize_baseline(..., "no_rules_hit_no_llm", ...)

new_prompt, retry_params = _apply_overrides(rc.get("prompt", ""),
                                             hits.prompt_addons + extra_addons,
                                             hits.param_overrides, base_params, backend_kind)

# Step 8: adapter.call → 4 类 BackendError 分类
try:
    response = adapter.call(BackendRequest(prompt=new_prompt, params=retry_params, ...),
                            timeout=config.backend.timeout_s)
except BackendError as e:
    loop_status, error_entry = _classify_backend_error(e)
    return _finalize_baseline(..., loop_status, errors=[error_entry],
                              local_extra_cost=local_extra_cost)

if response.actual_cost_usd is not None:
    budget.record_actual(response.actual_cost_usd)
    local_extra_cost = local_extra_cost - estimate + response.actual_cost_usd
    warnings = []
else:
    warnings = ["cost_estimated_only"]

# Step 9-10: score_select + finalize
candidates = [CandidateImage(baseline_path, verdict),
              CandidateImage(response.output_image_path, None)]
strategy = STRATEGY_REGISTRY[config.advanced["score_select_strategy"]]()
selection = strategy.select(candidates, jury_callable, budget)
# selection.retry_verdict （rev 3 决议 #12）含 retry verdict 用于 sidecar.retry

final_path = _finalize(selection.pick, baseline_path, response.output_image_path,
                        safe_view, render_dir)
# _finalize OSError 抛出 → 顶层 try/except 捕获 → write_degraded_sidecar + re-raise

# 计算 retry_score_delta / delivered_score_delta
retry_score_delta = (selection.retry_verdict.photoreal_score - verdict.photoreal_score
                     if selection.retry_verdict else None)
delivered_score_delta = (max(retry_score_delta, 0) if selection.pick is candidates[1]
                          else 0) if retry_score_delta is not None else None

# 写 sidecar（含 retry 字段构造）+ 返
metadata.write_sidecar(view=safe_view, render_dir=render_dir, backend=backend_kind,
                       loop_status=("delivered_retry" if selection.pick is candidates[1] else "delivered_baseline"),
                       delivered_kind=("retry" if selection.pick is candidates[1] else "baseline"),
                       baseline={...}, retry=_build_retry_dict(...),
                       retry_score_delta=retry_score_delta,
                       delivered_score_delta=delivered_score_delta,
                       extra_cost_usd=local_extra_cost,
                       warnings=warnings, ...)
return LoopResult(final_path, ...)
```

---

## §4 6 个 helper

### `_check_pre_jury_gates(backend_kind, config) -> str | None`
- 实现 Gate-1/2；返 loop_status 字符串或 None；纯函数

### `_rename_baseline_as_final(baseline_path, view, render_dir) -> Path`
- 父 spec line 165+527 N-1 决议：Gate-1/2 退出路径 baseline → V<view>_enhanced.jpg
- 跨平台安全：`dst.unlink(missing_ok=True) + Path(baseline).replace(dst)`
- OSError 向上抛（顶层 try/except 兜）

### `_call_jury_subprocess(view, image_path, project_root, jury_profile_path, timeout_s) -> tuple[ViewVerdict | None, str | None]`（rev 3 决议 #9 改返 tuple）
- 命令：`subprocess.run([sys.executable, "-m", "tools.photo3d_jury", "--single-view", view, "--image", str(image_path), "--config", str(jury_profile_path)], cwd=project_root, timeout=timeout_s, capture_output=True, text=True)`（DRIFT-MAJOR-5 sys.executable）
- 解析 stdout JSON → 调 `parse_view_verdict(content_text)` 构造 ViewVerdict 实例
- 失败返 `(None, error_code)` 不再丢信息：
  - `subprocess.TimeoutExpired` → `(None, "timeout")`
  - `CalledProcessError` 或 exit≠0 → `(None, "exit_nonzero")`
  - `json.JSONDecodeError` → `(None, "json_parse_failed")`
  - list 形状不符 / `verdict.verdict == "needs_review"` → `(None, "needs_review")`
- 测试 monkeypatch.setattr 整体替换；orchestrator 模块属性引用风格便于 patch

### `_classify_backend_error(exc) -> tuple[str, dict]`（rev 3 决议 #10 改返 tuple）
```python
def _classify_backend_error(exc: BackendError) -> tuple[str, dict]:
    """4 路异常分类 → (loop_status, error_entry)。"""
    if isinstance(exc, BackendAuthError):
        return ("retry_auth_failed", {"code": "backend_auth_error",
                                       "message_summary": str(exc)[:200],
                                       "user_action_hint": "检查 API key 是否有效"})
    if isinstance(exc, BackendRateLimitError):
        return ("retry_rate_limited", {"code": "backend_rate_limited", ...})
    if isinstance(exc, BackendQuotaExceededError):
        return ("retry_quota_exceeded", {"code": "backend_quota_exceeded", ...})
    if isinstance(exc, BackendCallError):
        return ("retry_failed", {"code": "backend_call_error", ...})
    return ("retry_failed", {"code": "backend_unknown_error", ...})  # fallback
```

### `_apply_overrides(prompt, prompt_addons, param_overrides, base_params, backend_kind) -> tuple[str, dict]`（rev 3 决议 #7 加 base_params 第 4 入参）
- 返 `(new_prompt, retry_params)` tuple；不动 rc
- new_prompt = `prompt + " | " + ", ".join(prompt_addons)`
- retry_params = `{**base_params, **param_overrides.get(backend_kind, {})}`（rule 赢，A-1）

### `_finalize(pick, baseline_path, retry_path, view, render_dir) -> Path`
- 父 spec §3 [10]：pick 重命名为 V<view>_enhanced.jpg；另一张保留为 V<view>_enhanced_<otherkind>.jpg
- 顺序两次 rename；任一步 OSError 向上抛（顶层 try/except → write_degraded_sidecar）

---

## §5 测试矩阵（rev 3：24 → 19，YAGNI 删 6 加 1 简化 1）

| # | 测试名 | mock 输入 | 期望 loop_status | 验收附加项 |
|---|---|---|---|---|
| 1 | `test_gate1_backend_unregistered` | backend_kind="engineering"（不在 REGISTRY） | `loop_disabled` | sidecar.loop_eligible=false; final_path 是 V1_enhanced.jpg |
| 2 | `test_gate2_enabled_false` | config.enabled=False | `loop_disabled` | 同 #1 |
| 3 | `test_gate3_jury_returns_none` | `_call_jury_subprocess` → (None, "exit_nonzero") | `jury_unavailable` | sidecar.delivered_kind="baseline"; sidecar.errors[0].code=="exit_nonzero" |
| 4 | `test_gate3_5_empty_reason` | verdict(score=50, reason="") | `empty_reason` | sidecar.delivered_kind="baseline"; baseline 字段含 reason="" |
| 5 | `test_gate4_score_above_threshold` | verdict(photoreal_score=80) + threshold=75 | `above_threshold` | sidecar.user_friendly_summary 含 "80" |
| 5b | `test_gate4_score_equals_threshold` | verdict(photoreal_score=75) + threshold=75 | `above_threshold` | 锁 ≥ 而非 > 边界 |
| 6 | `test_gate5_budget_capped` | budget.try_spend → False | `cost_capped` | sidecar.extra_cost_usd == 0（local_extra_cost；try_spend 返 False 未扣） |
| 7 | `test_gate6_no_tags_parsed` | reason="abc xyz blah"（ASCII 无 tag） | `no_tags_parsed` | sidecar.tags_parsed=[] |
| 8 | `test_gate7_all_miss_llm_fallback_off` | tags 经用户 yaml 扩展含未配 tag + config.advanced["llm_fallback"]=False | `no_rules_hit_no_llm` | 需 fixture user_yaml_with_tag_no_rule |
| 9 | `test_gate8_backend_auth_error` | adapter.call → BackendAuthError | `retry_auth_failed` | sidecar.errors[0].code == "backend_auth_error" |
| 10 | `test_gate8_backend_rate_limit_error` | adapter.call → BackendRateLimitError | `retry_rate_limited` | sidecar.errors[0].code == "backend_rate_limited" |
| 11 | `test_gate8_backend_quota_exceeded` | adapter.call → BackendQuotaExceededError | `retry_quota_exceeded` | sidecar.errors[0].code == "backend_quota_exceeded" |
| 12 | `test_gate8_backend_call_error` | adapter.call → BackendCallError | `retry_failed` | sidecar.errors[0].code == "backend_call_error" |
| 13 | `test_normal_retry_improves_score` | retry_score=80 > baseline=58 (pick_max_jury) | `delivered_retry` | retry_score_delta=+22; delivered_kind="retry"; delivered_score_delta=+22 |
| 14 | `test_normal_retry_degrades_score` | retry_score=50 < baseline=58 | `delivered_baseline` | retry_score_delta=-8; delivered_score_delta=0; retry 字段含完整 verdict（依 selection.retry_verdict） |
| 15 | `test_actual_cost_none_warns` | BackendResponse.actual_cost_usd=None | `delivered_retry`（或 retry 跑通形态） | sidecar.warnings 含 `"cost_estimated_only"`; sidecar.extra_cost_usd == estimate |
| 16 | `test_force_retry_strategy_skips_second_jury` | config.advanced["score_select_strategy"]="force_retry" | `delivered_retry` | retry.photoreal_score=null + semantic_checks=null + reason=null + final_prompt 非空 + backend_payload 非空 + retry_score_delta=null + delivered_score_delta=null（spec §4.4 line 530 全约束） |
| 20 | `test_baseline_path_missing_raises` | baseline_path 文件不存在 | raise FileNotFoundError | 不写 sidecar; cmd_enhance 兜 |
| 22 | `test_unknown_exception_invokes_degraded_sidecar` | monkeypatch rule_table.lookup 抛 ValueError | raise ValueError | metadata.write_degraded_sidecar 被调一次（断 mock 调用次数）；不验 sidecar 内部字段（属 cmd_enhance / metadata 范围） |

**rev 3 删除的 6 项**（YAGNI + 测试可执行性矛盾共识）：
- ~~#14b retry == baseline~~：score_select 单测（test_score_select.py:79-87）已覆盖；CP-5 集成层冗余
- ~~#17 jury subprocess timeout~~：rev 3 决议 #9 _call_jury_subprocess 返 tuple 已经能保留 "timeout" code，但具体 TimeoutExpired 路径属 helper unit test（CP-6 实施 helper 真路径时覆盖）
- ~~#18 score 越界~~：spec rev 2 §7 决议白名单含 "clamped"，与测试期望 jury_unavailable 内部矛盾；parse_view_verdict 已 clamp，删除该测试
- ~~#19 NaN estimate~~：决议 #10 删除（YAGNI）；3 内置 adapter estimate_cost_usd 不可能返 NaN；SP3 user plugin 接入时再加
- ~~#21 finalize OSError 钱-账保留~~：决议 #7 删除（YAGNI），_finalize OSError 退回 rev 1 向上抛
- ~~#23 partial rename~~：事务式删除，rev 3 _finalize 简单顺序 rename，任一步失败抛即可

**总测试数**：rev 1 16 → rev 2 24 → rev 3 **19**（保留 #1-16 + 5b + 20 + 22 简化版）

---

## §6 mock fixture（rev 3：对齐既有 isolated_registry / 加 stateful 工厂）

```python
# tests/jury_loop/conftest.py 新增

@pytest.fixture
def fake_view_verdict():
    """ViewVerdict factory；字段集对齐 tools/jury/verdict.py 真签名 6 字段。"""
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
    """stateful jury 工厂：把 (score, reason) tuple list 变 lambda 让连续调用按序返不同 verdict。

    用法（测试 #13/#14）：
        jury_seq = fake_jury_sequence([(58, "plastic"), (80, "metallic")])
        monkeypatch.setattr(orchestrator, "_call_jury_subprocess",
                             lambda *a, **kw: (jury_seq(), None))
    """
    def _make(items: list[tuple[int, str]]):
        verdicts = iter([fake_view_verdict(score=s, reason=r) for s, r in items])
        return lambda: next(verdicts)
    return _make


@pytest.fixture
def isolated_backend_registry():
    """对齐既有 test_backend_protocol.py:isolated_registry — snapshot/restore 模式
    防 pytest-xdist 并发同时 register_backend("test_stub") 的 ValueError。"""
    snapshot = dict(BACKEND_REGISTRY)
    yield BACKEND_REGISTRY
    BACKEND_REGISTRY.clear()
    BACKEND_REGISTRY.update(snapshot)


@pytest.fixture
def fake_backend_adapter(isolated_backend_registry):
    """注册 _FakeAdapter 到 BACKEND_REGISTRY 的 context manager。

    @contextmanager 进入时确保 kind 不在 REGISTRY（pop 兜）；register_backend 通过
    isinstance(adapter, BackendAdapter) Protocol 校验；isolated_backend_registry
    fixture 在 yield 后整体 restore。
    """
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
        BACKEND_REGISTRY.pop(kind, None)  # 清残留（防上次 raise 没 cleanup）
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
    """JuryProfile factory（fake LLM endpoint，测试用）。"""
    return JuryProfile(
        id="test", kind="openai_compat",
        api_base_url="https://example.test/v1",
        api_key="sk-fake-test-key",
        model="gemini-2.5-flash", cost_per_call_usd=0.005,
    )


@pytest.fixture
def tiny_loop_config():
    """JuryLoopConfig factory，字段对齐 plan Task 5.0 (前 7.2)。"""
    def _make(*, enabled=True, cost_cap_usd=1.5, backend_kind="test_stub",
              threshold=75, llm_fallback=False,
              score_select_strategy="pick_max_jury",
              max_retries=1, rule_table_path=None):
        from tools.jury_loop.config import BackendConfig
        return JuryLoopConfig(
            enabled=enabled, cost_cap_usd=cost_cap_usd,
            backend=BackendConfig(kind=backend_kind, base_url="https://example.test",
                                   api_key_env="TEST_API_KEY", model_name="test-model",
                                   timeout_s=60),
            advanced={"threshold": threshold, "max_retries": max_retries,
                       "llm_fallback": llm_fallback,
                       "rule_table_path": rule_table_path,
                       "score_select_strategy": score_select_strategy},
        )
    return _make


@pytest.fixture
def user_yaml_with_tag_no_rule(tmp_path):
    """测试 #8 专用：用户 yaml 扩展 tag_dictionary 但不加 rule，触发 rule_table 全 miss。"""
    p = tmp_path / "user_rules.yaml"
    p.write_text("""
schema_version: 1
tag_dictionary:
  unknown_aesthetic_tag:
    patterns: ["weird vibe", "off feeling"]
rules: []  # 故意不加 rule
""", encoding="utf-8")
    return p
```

---

## §7 异常隔离与 fail-safe（rev 3 简化）

### orchestrator 自捕获范围
- **`BackendError` 4 子类**：内捕 + `_classify_backend_error` 返 (loop_status, error_dict) + 写 sidecar.errors[]
- **`subprocess.{Called,TimeoutExpired}` / `json.JSONDecodeError`**：在 `_call_jury_subprocess` 内捕返 `(None, error_code)`；上层填 sidecar.errors[].code
- **顶层 `try/except Exception`（rev 3 简化）**：调 `metadata.write_degraded_sidecar(view=safe_view, render_dir, error=e)` → re-raise；防止 cmd_enhance 重复 write_degraded（cmd_enhance 视角级 try/except 接 ValueError 后仅 log + skip view，不重写 sidecar，避免无限循环）

### orchestrator **不**自捕获范围（向上抛给 cmd_enhance）
- **`FileNotFoundError`（baseline_path 不存在）**：顶层第 1 行 fail-fast；不写 sidecar（cmd_enhance plan line 1301-1303 也不重写——见 §8 follow-up #2 plan 同步）
- **`ValueError`（_validate_view_basename 拒绝注入 view）**：顶层第 2 行 fail-fast；不写 sidecar（view 名无法构造文件名）
- **`OSError`（_finalize / _rename_baseline_as_final 失败）**：rev 3 退回 rev 1 路径——经顶层 try/except Exception 兜（已 write_degraded_sidecar）后 re-raise；errors[].code 暂不细分 finalize_rename_failed（§8 follow-up #6）

### sidecar 写盘 OSError
- orchestrator 顶层 try/except 仅写一次 write_degraded_sidecar；该调用如果自身 OSError 由 cmd_enhance 视角级 except OSError 静默 log（rev 2 决议同款）

### 字段构造规则（rev 3 决议 #11/#12 落地）

```python
# 选张完成后的 retry / score_delta 计算
def _compute_score_deltas(selection, baseline_verdict):
    """根据 selection（含 retry_verdict）算 retry_score_delta / delivered_score_delta。"""
    if selection.retry_verdict is None:  # force_retry 路径
        return None, None
    retry_score_delta = selection.retry_verdict.photoreal_score - baseline_verdict.photoreal_score
    if selection.pick.image_path == retry_path:  # retry 被选
        delivered_score_delta = retry_score_delta  # 必正
    else:  # baseline 被选
        delivered_score_delta = 0
    return retry_score_delta, delivered_score_delta


# sidecar.retry 字典构造
def _build_retry_dict(retry_path, selection, request, response):
    """根据 selection 构造 sidecar.retry（force_retry vs pick_max_jury 双形态）。"""
    if selection.retry_verdict is None:  # force_retry：父 spec line 530
        return {
            "image_path": str(retry_path), "photoreal_score": None,
            "semantic_checks": None, "reason": None,
            "final_prompt": request.prompt,           # OPS-MAJOR-1 复盘需要
            "backend_payload": response.raw_request_summary,
        }
    # pick_max_jury：retry 含完整 verdict
    return {
        "image_path": str(retry_path),
        "photoreal_score": selection.retry_verdict.photoreal_score,
        "semantic_checks": dict(selection.retry_verdict.semantic_checks),
        "reason": selection.retry_verdict.reason,
        "final_prompt": request.prompt,
        "backend_payload": response.raw_request_summary,
    }
```

---

## §8 §11 follow-up（rev 3 闭合 + 新登记）

### rev 3 闭合
- ✅ rev 1 ViewVerdict.kind/view 字段错（rev 2 修；rev 3 fixture 仍对齐 6 字段）
- ✅ rev 1 JuryLoopConfig 不存在（rev 2 加前置；rev 3 plan Task 5.0 物理移到 CP-5 之前）
- ✅ rev 1 rc[backend] 字典结构错（决议 #7：_apply_overrides 不动 rc + base_params 第 4 入参）
- ✅ rev 2 jury_profile 缺来源（决议 #8 加 jury_profile + jury_profile_path 2 kwarg）
- ✅ rev 2 _classify_backend_error 缺 errors[] 构造（决议 #10 改返 tuple）
- ✅ rev 2 _call_jury_subprocess 信息丢失（决议 #9 改返 tuple）
- ✅ rev 2 empty_reason 触发位置缺（决议 #11 锁 Gate-3.5）
- ✅ rev 2 score_select retry_verdict 出口缺（决议 #12 改 score_select.SelectionResult）
- ✅ rev 2 ≥ vs > 运算符缺（§3 主流程时序写明 `>=`）
- ✅ rev 2 base_params 来源缺（决议 #7 加第 4 入参）
- ✅ rev 2 fake_backend_adapter snapshot/restore 模式（§6 加 isolated_backend_registry fixture）
- ✅ rev 2 rule_table 模块级调用（§3 [5] 不再注入 RuleTable instance；rev 3 删除该 kwarg）

### rev 3 新登记 §11 follow-up（非 CP-5 范围）

1. **plan Task 7.2 物理移到 CP-5 之前作 "Task 5.0"**（plan 文件改）：进 writing-plans 时立即修
2. **plan Task 5.1 line 1206-1217 签名加 jury_profile / jury_profile_path / base_params 3 kwarg**（plan 文件改）：进 writing-plans 时立即修
3. **plan Task 7.1 line 1289-1304 cmd_enhance 视角级 try/except 处理**：FileNotFoundError 仅 log + skip（不调 write_degraded_sidecar 避免死循环）；其他 Exception 仅 log（不重复调 write_degraded_sidecar，orchestrator 已写）
4. **父 spec doc fix 3 处**（建议 1 commit 同步）：
   - line 183 `tags = reason_parser(sanitized_reason)` → `reason_parser.parse_reason(sanitized_reason)`
   - line 191 `llm_fallback.translate(misses, sanitized_reason)` → `translate(unmapped_reason=sanitized_reason, sanitized_reason=sanitized_reason, profile=jury_profile) if misses and config.llm_fallback`
   - §4.4 line 472 `backend ∈ {gemini, comfyui, fal, fal_comfy, engineering}` 加 "unknown"（cmd_enhance pre-classification 异常专用）
5. **父 spec line 600-606** 文字暗示"orchestrator 看 HTTP 码"易误读；加一句"实施层 HTTP 码由 BackendAdapter 归一化为 BackendError 4 子类"
6. **`_finalize` OSError errors[].code 精细分类**：rev 3 暂复用 retry_failed；真发生时再加 finalize_rename_failed
7. **NaN/Inf 防御**：SP3 user plugin 接入时在 enhance_budget.try_spend 加 isfinite 校验
8. **reference_mode=none 真并发**：CP-7 brainstorm 决定（每视角独立 LoopBudget vs 全用 estimate）
9. **stdout 1MiB cap (SEC-MINOR-4)**：CP-6 实施
10. **photo3d-jury `--single-view` flag 字面**：CP-6 plan 决议；CP-5 用 `--single-view --image --config` 是预设

---

## §9 提交策略

- spec rev 3 写出 + 自审 → commit `docs(spec): CP-5 子 spec rev 3 — 二审 30+ findings YAGNI 简化`
- 用户审 rev 3 通过 → 进 writing-plans skill 输出 plan 文件
- writing-plans 阶段**立即同步 plan**：移 Task 7.2 / 加 3 kwarg / 加 reference_mode 分支注释
- subagent-driven 实施由 plan 阶段决议

---

## §10 自审记录（rev 3）

按二审 4 reviewer × 30+ findings 闭合 + YAGNI 决断：

### Dry-run reviewer（12 项）
| # | finding | 闭合策略 | 状态 |
|---|---|---|---|
| D-1 | jury_unavailable extra_cost_usd 写 None | §3 主流程 `local_extra_cost=0` 显式传给 _finalize_baseline | ✅ |
| D-2 | sidecar_written flag 时序 | rev 3 决议 #6 简化为 try/except → write_degraded_sidecar，无 state 容器抽象 | ✅ |
| D-3 | _finalize OSError state 重置 | rev 3 决议 #7 删除（退回 rev 1 向上抛）；OSError 不再内捕 | ✅（YAGNI 删） |
| D-4 | NaN 检测位置歧义 | rev 3 决议 #10 删除 NaN 防御 | ✅（YAGNI 删） |
| D-5 | unknown ValueError 路径 state | rev 3 决议 #6 简化版用 write_degraded_sidecar 兜，不需手动改 state | ✅ |
| D-6 | FileNotFoundError 跨 spec 不一致 | §8 follow-up #3 plan Task 7.1 同步：FileNotFoundError 仅 log skip 不写 degraded | ✅ |
| D-7 | force_retry retry dict 构造 | §7 字段构造规则 + 决议 #12 score_select 加 retry_verdict 出口 | ✅ |
| D-8 | retry_score_delta 时机 | §7 _compute_score_deltas 函数 + selection.retry_verdict | ✅ |
| D-9 | extra_cost_usd 跨视角语义 | rev 3 决议 #18：本视角 local_extra_cost 不用 budget.spent | ✅ |
| D-10 | base_params 来源 | rev 3 决议 #7 加第 4 入参；§3 顶层签名加 base_params kwarg | ✅ |
| D-11 | FileNotFoundError fail-fast 文档 | §3 docstring + §7 显式分块 | ✅ |
| D-12 | subprocess capture_output 1MiB | §1 非目标 + §8 follow-up #9 CP-6 实施 | ✅ |

### 测试可执行性 reviewer（9 写不出 + 11 能写但坑）
| # | finding | 闭合策略 | 状态 |
|---|---|---|---|
| T-1 | empty_reason 位置 | rev 3 决议 #11 锁 Gate-3.5；§3 主流程 Step 3 | ✅ |
| T-2 | all_miss 结构性不可造 | §6 加 user_yaml_with_tag_no_rule fixture；§5 #8 用之 | ✅ |
| T-3 | BackendError errors[] 构造 | rev 3 决议 #10 改 _classify_backend_error 返 tuple | ✅ |
| T-4 | score_select retry_verdict 出口 | rev 3 决议 #12 改 score_select.SelectionResult | ✅ |
| T-5 | actual_cost_none warning | §3 主流程 Step 8 显式 warnings=["cost_estimated_only"] | ✅ |
| T-6 | jury subprocess timeout 信息丢失 | rev 3 决议 #9 _call_jury_subprocess 返 tuple；测试 #17 删除 | ✅ |
| T-7 | spec 决议白名单 vs #18 矛盾 | 测试 #18 删除 | ✅（YAGNI 删） |
| T-8 | enhance_budget isfinite prerequisite | NaN 防御 YAGNI 删除；不需 prerequisite | ✅ |
| T-9 | 事务式 vs partial 矛盾 | _finalize 退回 rev 1 顺序 rename；测试 #21/#23 删除 | ✅ |
| T-10 | BACKEND_REGISTRY 隔离 | §6 加 isolated_backend_registry snapshot/restore | ✅ |
| T-11 | _call_jury_subprocess module 属性引用 | §4 + 决议 #4 注释 | ✅ |
| T-12 | ≥ vs > 运算符 | §3 主流程 Step 4 显式 `>=` | ✅ |
| T-13 | reason ASCII 字面量 | §5 #7 改用 "abc xyz blah" | ✅ |
| T-14 | stateful jury fixture | §6 加 fake_jury_sequence factory | ✅ |
| T-15 | retry sidecar 字典样板 | §7 _build_retry_dict 函数 | ✅ |
| T-16 | _finalize OSError 测试 | rev 3 删除（决议 #7 YAGNI） | ✅ |
| T-17 | rule_table.lookup patch 路径 | §4 注释模块属性引用 | ✅ |
| T-18 | tiny_jury_profile fixture 缺 | §6 加 | ✅ |
| T-19 | RuleTable fixture 缺 | rev 3 删除该 kwarg；不再需要 fixture | ✅ |
| T-20 | fake_backend_adapter 冲突 | §6 改 isolated_backend_registry 模式 | ✅ |

### 父子 spec 一致性 reviewer（5 严重 + 3 中）
| # | finding | 闭合策略 | 状态 |
|---|---|---|---|
| P-1 | plan Task 5.1 签名漏 kwarg | §8 follow-up #2 writing-plans 立即修 | ✅（待 plan 同步） |
| P-2 | plan Task 7.2 须移到 CP-5 前 | §8 follow-up #1 writing-plans 立即移 | ✅（待 plan 同步） |
| P-3 | plan 缺 enhance_budget isfinite Task | NaN 防御 YAGNI 删除；不需新 Task | ✅ |
| P-4 | plan Task 7.1 record_actual reference_mode 分支 | §8 follow-up #8 推到 CP-7 brainstorm | ✅（推迟） |
| P-5 | jury_profile_path 第 10 kwarg | §3 顶层签名加 `jury_profile_path: Path` | ✅ |
| P-6 | 父 spec doc fix 3 处 | §8 follow-up #4 1 commit 同步 | ✅（待父 spec 同步） |
| P-7 | 父 spec §5 line 612 fail-safe 链断附注 | §8 follow-up #5 父 spec 同步 | ✅（待父 spec 同步） |
| P-8 | fake_backend_adapter snapshot/restore | §6 加 isolated_backend_registry | ✅ |

### YAGNI reviewer（10 删 + 3 简化 + 7 保留）
| # | 项 | 决断 | 状态 |
|---|---|---|---|
| Y-1 | 决议 #7 _finalize OSError 内捕 | 删除（趋零概率） | ✅ |
| Y-2 | 决议 #10 NaN 防御 | 删除（3 内置 adapter 不可能） | ✅ |
| Y-3 | 决议 #11 reference_mode 决议 | 删除（推到 CP-7 brainstorm） | ✅ |
| Y-4 | rule_table kwarg | 删除（模块级调用即可） | ✅ |
| Y-5 | 测试 #14b retry==baseline | 删除（score_select 单测覆盖） | ✅ |
| Y-6 | 测试 #17 jury timeout | 删除（信息已通过 tuple 保留） | ✅ |
| Y-7 | 测试 #18 score 越界 | 删除（spec 矛盾） | ✅ |
| Y-8 | 测试 #19 NaN | 删除（决议 #10 配套） | ✅ |
| Y-9 | 测试 #21 finalize OSError | 删除（决议 #7 配套） | ✅ |
| Y-10 | 测试 #23 partial rename | 删除（决议 #7 配套） | ✅ |
| Y-11 | 决议 #6 try/finally state 容器 | 简化（write_degraded_sidecar + re-raise） | ✅ |
| Y-12 | _finalize 事务式 | 简化（顺序 rename） | ✅ |
| Y-13 | 测试 #22 unknown exception | 简化（仅断 mock 调用次数） | ✅ |

### 综合
- **闭合 30+/30+**：dry-run 12 + 测试可执行性 20 + 父子 spec 8 + YAGNI 13 = 53 项 finding 全部回应
- **rev 1 → rev 2 → rev 3 决议演进**：5 → 11 → 12（YAGNI 删 4 + 新增 5）
- **rev 1 → rev 2 → rev 3 测试矩阵**：16 → 24 → 19（YAGNI 删 6 + 简化 1）
- **rev 1 → rev 2 → rev 3 helper**：5 → 6 → 6
- **rev 2 → rev 3 顶层 kwarg**：9 → 10（加 base_params + jury_profile_path；删 rule_table）
- **rev 2 → rev 3 文件大小**：461 → 当前估计 ~520 行（YAGNI 删省 50 行 + 决议 #6-#12 详化加 110 行 = 净 +60 行）

---

## §11 修订日志

| Rev | 日期 | 改动 |
|---|---|---|
| 1 | 2026-05-10 session 5 | 初版 brainstorm 5 决议 + 16 测试矩阵；commit `76ef3a8` |
| 2 | 2026-05-10 session 5（第一轮 4 reviewer） | 30 findings 修订；决议 5 → 11；测试 16 → 24；helper 5 → 6；顶层加 jury_profile/rule_table；fail-safe try/finally state 容器；ViewVerdict/JuryLoopConfig 字段对齐；commit `a863484` |
| 3 | 2026-05-10 session 5（第二轮 4 reviewer，常犯错方向） | 53 findings 修订；YAGNI 删 4 决议 + 6 测试 + 简化 3；新增 5 决议（#7 base_params / #8 jury_profile_path / #9 _call_jury_subprocess 返 tuple / #10 _classify_backend_error 返 tuple / #11 empty_reason 位置 / #12 score_select retry_verdict 出口 / #18 local_extra_cost 跨视角）；fixture 加 isolated_backend_registry / fake_jury_sequence / tiny_jury_profile / user_yaml_with_tag_no_rule；plan 同步项进 §8 follow-up |
