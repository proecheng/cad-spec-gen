# CP-5 Orchestrator 实施设计（jury→prompt 闭环单视角主入口）

**日期**：2026-05-10（rev 2 / 4 reviewer batch 30 findings 修订）
**关联**：父 spec `2026-05-10-jury-prompt-loop-design.md` §3（数据流与时序）+ §4.4（sidecar schema）+ §4.5（score_select 策略）+ §4.6（loop_status enum）+ §6（jury single-view CLI 契约）
**依赖完成度**：CP-1（reason_parser / rule_table）+ CP-2.5（BackendAdapter Protocol + 3 内置 adapter）+ CP-3（llm_fallback / score_select）+ CP-4（enhance_budget / metadata sidecar）+ batch review fixup（commit `7fa7c93`）全部 GREEN
**前置 plan task（CP-5 实施前必落）**：
- **plan Task 7.2 提前到 CP-5 之前作 "Task 0"**：建 `tools/jury_loop/config.py::JuryLoopConfig` + 嵌套 `BackendConfig` + `load_jury_loop_config(...)`（plan 文件 line 1323-1333 已有详细描述）
- 否则 CP-5 第一行 `from tools.jury_loop.config import JuryLoopConfig` 即 ImportError

---

## §1 范围与非目标

### 范围
- 单视角闭环入口：`tools/jury_loop/orchestrator.py::run_loop_if_eligible`
- 实现父 spec §3 全 10 步 + 8 Gate（loop_disabled / above_threshold / cost_capped / no_tags_parsed / no_rules_hit_no_llm / jury_unavailable / empty_reason / retry_*）
- 4 类 BackendError 异常分类映射到 retry_auth_failed / retry_rate_limited / retry_quota_exceeded / retry_failed
- 调用 score_select 策略；写 sidecar 经 metadata 模块；返回 `LoopResult`
- **fail-safe 不变量**：(a) sidecar 永远写至少一份；(b) `final_path == V<view>_enhanced.jpg` 永远存在；(c) `budget._spent` 与 sidecar.extra_cost_usd 永远一致

### 非目标（CP-5 不做，留给后续 CP）
- **多视角调度**：v1_anchor / parallel 模式由 CP-7 cmd_enhance 管，CP-5 是单视角原子单元
- **photo3d-jury `--single-view` flag 真路径**：CP-6 Task 6.1 落地；CP-5 实施期间 `_call_jury_subprocess` 内部含 subprocess.run 调用骨架但生产 path 跑不通（mock 兜测试）；flag 字面（如 `--single-view` / `--image`）以 CP-6 plan 决议为准，CP-5 只规范"调用 photo3d-jury 子进程取 ViewVerdict"
- **stdout 1MiB cap (SEC-MINOR-4)**：CP-6 实施
- **reference_mode=none 真并发**：父 spec line 244 提到"可并行"——CP-5 仅设计单视角原子；并发安全由 cmd_enhance（CP-7）的"每视角独立 LoopBudget" 或 "禁用 record_actual 仅用 estimate" 兜（决议见 §2 #11）

---

## §2 brainstorm 决议（11 条）

| # | 决议 | 理由 |
|---|---|---|
| 1 | **mock 边界 = 深集成**：仅 mock 外部 boundary（subprocess + adapter.call），CP-1/2/3/4 实现（reason_parser / rule_table / llm_fallback / score_select / metadata.write_sidecar / LoopBudget）全用真实调用 | 已 197 测试覆盖核心 unit；orchestrator 测试覆盖真集成点 + 防 plan-drift |
| 2 | **架构粒度 = 单一函数 + 6 内部 helper**（rev 1 是 5 helper，rev 2 加 `_rename_baseline_as_final`） | 与 spec §3 10 步线性结构同构；Gate-1/2 提前退出与 _finalize 共享 rename 语义 |
| 3 | **LoopResult = 最小契约**：`@dataclass(frozen=True) LoopResult(final_path, loop_status)` 仅两字段 | sidecar = single source of truth；cmd_enhance 在视角循环结束读文件聚合 loop_summary |
| 4 | **jury subprocess mock 形态 = 抽内部 helper + monkeypatch.setattr 整体替换** | 不依 subprocess.run mock chain；CP-6 落地 `--single-view` flag 后该 helper 自然 work |
| 5 | **brainstorm 输出 = 独立 CP-5 子 spec**（本文件） | CP-5 复杂度跳一档；独立 spec 让 writing-plans 拆 task 更精确 |
| 6 | **fail-safe 写盘策略 = try/finally 状态容器**：`run_loop_if_eligible` 顶层维护 `state_dict`；finally 块统一 `metadata.write_sidecar(**state_dict)` | 修 rev 1 缺口：未知 Exception / OSError / NaN 等异常路径下 sidecar 仍含已知字段（baseline verdict / tags / cost），非"全填默认 None"的 degraded 形态 |
| 7 | **`_finalize` OSError 内捕**（rev 1 错让向上抛）：catch 后改 sidecar.loop_status="retry_failed"；`errors[].code="finalize_rename_failed"`；user_action_hint 提示磁盘/权限 | 修 rev 1 缺口：rename 失败误报 retry_failed 文案 → 用户排查方向错；现 errors[].code 区分根因 |
| 8 | **顶层签名加 `jury_profile: JuryProfile` + `rule_table: RuleTable` 入参** | 修 rev 1 缺口：rev 1 helper 用 jury_profile 但顶层未声明来源；rule_table 须 `load_rule_table` 缓存复用避免每视角重 load yaml；cmd_enhance 在视角循环外 1 次 load |
| 9 | **`_apply_overrides` 不动 rc**：返回新 `params: dict` 给 `BackendRequest.params`，不改入参 rc | 修 rev 1 缺口：rev 1 暗示 `rc[backend].update(...)` 字典结构假设错——rc 是视角级渲染配置（subsystem/camera/materials），无 backend kind 子键 |
| 10 | **NaN/Inf budget 防御**：`adapter.estimate_cost_usd → NaN/Inf` 时 orchestrator 视同 retry_failed（cost 不可估算）；`budget.try_spend` 入口添加 `math.isfinite` 校验（enhance_budget 模块负责） | 修 rev 1 缺口：rev 1 没考虑 estimate 病态返值；NaN 比较恒 False 让 try_spend 永真 → 财务破口 |
| 11 | **reference_mode=none 并发模式 record_actual 决议**：SP1 实施期 cmd_enhance 在 reference_mode=none 时**不调 record_actual**，全用 estimate；budget._spent 不修正，sidecar.warnings 加 `cost_estimated_only`；reference_mode=v1_anchor（串行）正常调 record_actual | 修 rev 1 缺口：rev 1 LoopBudget 跨视角共享 + record_actual 配对约束在并发下数据竞争。本决议保留并发能力 + 牺牲 record_actual 精度（已超花一点点不破 cap） |

---

## §3 顶层 API 与 LoopResult 契约

```python
# tools/jury_loop/orchestrator.py
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from enhance_budget import LoopBudget
from tools.jury.config import JuryProfile
from tools.jury.verdict import ViewVerdict
from tools.jury_loop.config import JuryLoopConfig          # 前置依赖：plan Task 7.2 提前
from tools.jury_loop.rule_table import RuleTable           # 由 cmd_enhance load 一次跨视角共享


@dataclass(frozen=True)
class LoopResult:
    """单视角闭环结果。

    最小契约：仅返"哪张图最终交付 + 闭环状态"，不暴露 sidecar 内容。
    cmd_enhance (CP-7) 在视角循环结束统一读 sidecar 文件聚合 loop_summary。
    final_path 永远是 V<view>_enhanced.jpg 绝对路径（即便 Gate-1/2 提前退出）。
    """
    final_path: Path
    loop_status: str   # spec §4.6 enum 14 项之一


def run_loop_if_eligible(
    *,
    view: str,
    backend_kind: str,           # 来自 jury_loop.backend.kind 配置
    rc: dict,                    # pipeline_config 视角级 render config（不被本函数修改）
    baseline_path: Path,         # V<i>_enhanced_baseline.jpg；前置：必须 .is_file()
    budget: LoopBudget,          # 跨视角共享预算簿
    project_root: Path,          # 项目根（jury subprocess cwd）
    config: JuryLoopConfig,      # 解析后的 enhance.jury_loop.* 配置
    jury_profile: JuryProfile,   # rev 2 新增：jury LLM endpoint + key（cmd_enhance 加载后传入）
    rule_table: RuleTable,       # rev 2 新增：cmd_enhance load_rule_table 1 次跨视角共享
) -> LoopResult:
    """单视角 jury→prompt 闭环。

    异常处理（rev 2 fail-safe 重写）：
    - 已知异常（BackendError 4 子类 / subprocess.{Called,TimeoutExpired} / json.JSONDecodeError /
      _finalize OSError / NaN-cost / score 越界）：内部捕获写 sidecar 后正常返。
    - 未知异常（rule_table 抛 ValueError / write_sidecar 自身 OSError 等）：try/finally 写
      尽量富的 sidecar 后向上抛；cmd_enhance 视角级 try/except 仅 log 不重复 write_degraded
      （避免无限循环）。

    前置条件：
    - `baseline_path.is_file() == True`（不满足直接 raise FileNotFoundError 给 cmd_enhance）
    - `view` 必须通过 `metadata._validate_view_basename`（不通过则 ValueError 给 cmd_enhance）

    返回：LoopResult.final_path **永远存在**为 V<view>_enhanced.jpg 形态绝对路径。
    """
    ...
```

---

## §4 6 个 helper（rev 2 加 `_rename_baseline_as_final`）

按 spec §3 10 步线性流程同构切分：

### `_check_pre_jury_gates(backend_kind, config) -> str | None`
- 实现 Gate-1（`backend_kind ∉ BACKEND_REGISTRY`）+ Gate-2（`config.enabled == False`）
- 纯函数：返 loop_status 字符串或 None；不读文件不调外部
- Gate-1/2 退出后由顶层调 `_rename_baseline_as_final` 完成 rename

### `_rename_baseline_as_final(baseline_path, view, render_dir) -> Path`（rev 2 新）
- 父 spec line 165+527 N-1 决议：Gate-1/2 路径直接重命名 `_baseline.jpg → _enhanced.jpg`
- 跨平台安全：`dst.unlink(missing_ok=True) + Path(baseline).replace(dst)`（父 spec line 270 同款）
- 返 V<view>_enhanced.jpg 绝对路径
- OSError 抛出由顶层 try/finally 写 sidecar 后再 raise

### `_call_jury_subprocess(view, image_path, project_root, jury_profile, timeout_s) -> ViewVerdict | None`
- 含 `subprocess.run([sys.executable, "-m", "tools.photo3d_jury", "--single-view", view, "--image", str(image_path), "--config", str(jury_profile_path)], cwd=project_root, timeout=timeout_s, capture_output=True, text=True)`（**rev 2 修：sys.executable 替 "python"** 遵守父 spec DRIFT-MAJOR-5）
- 解析 stdout JSON → 调 `parse_view_verdict(content_text)` 构造 ViewVerdict 实例（**rev 2 修：用 `tools.jury.verdict.parse_view_verdict`** 而非手拼字段）
- 失败返 None：`subprocess.CalledProcessError` / `subprocess.TimeoutExpired` / `json.JSONDecodeError` / list 形状不符 / `verdict.verdict == "needs_review"`（**rev 2 修：字段名 `verdict` 不是 `kind`**）
- timeout_s 来源：`config.backend.timeout_s`（plan Task 7.2 schema 字段）
- **测试 monkeypatch.setattr 整体替换**

### `_classify_backend_error(exc: BackendError) -> str`
- 纯函数：4 路 mapping `BackendAuthError → retry_auth_failed` 等
- 不读 HTTP 码（adapter 已映射好）
- 测试覆盖 4 子类 + 1 fallback（未知 BackendError 子类 → `retry_failed`）

### `_apply_overrides(prompt: str, prompt_addons: list[str], param_overrides: dict[str, dict]) -> tuple[str, dict]`（rev 2 修）
- 实现父 spec §3 [6]：返 `(new_prompt, retry_params)` tuple，**不动 rc**
- prompt 拼接：`new_prompt = prompt + " | " + ", ".join(prompt_addons)`
- params 浅合并：`retry_params = {**base_params_for_kind, **param_overrides.get(backend_kind, {})}`（rule 赢，A-1）
- 调用方拿 retry_params 构造 `BackendRequest(..., params=retry_params, ...)`

### `_finalize(pick: CandidateImage, baseline_path, retry_path, view, render_dir) -> Path`（rev 2 修：事务式 + OSError 内捕）
- 实现父 spec §3 [10]：将 `pick.image_path` 重命名为 `V<view>_enhanced.jpg`
- 另一张保留为 `V<view>_enhanced_<otherkind>.jpg`（baseline 或 retry）
- 事务式：先尝试 dst.unlink + src.replace；**第一步失败保留原状抛 OSError**（不继续第二步避免半完成态）
- **rev 2 修：OSError 由顶层 try/except 捕获**（rev 1 错让向上抛）→ sidecar.loop_status="retry_failed" + errors[].code="finalize_rename_failed"
- 返 V<view>_enhanced.jpg 绝对路径

---

## §5 测试矩阵（24 用例 + fixture）

rev 1 16 → rev 2 24（加 8 测试覆盖 reviewer 找出的边界缺口）

| # | 测试名 | mock 输入 | 期望 loop_status | 验收附加项 |
|---|---|---|---|---|
| 1 | `test_gate1_backend_unregistered` | backend_kind="engineering"（不在 REGISTRY） | `loop_disabled` | sidecar.loop_eligible=false; final_path 是 V1_enhanced.jpg |
| 2 | `test_gate2_enabled_false` | config.enabled=False | `loop_disabled` | 同 #1 |
| 3 | `test_gate3_jury_returns_none` | `_call_jury_subprocess` → None | `jury_unavailable` | sidecar.delivered_kind="baseline" |
| 4 | `test_gate3_jury_empty_reason` | verdict(score=50, reason="") | `empty_reason` | 同 #3 |
| 5 | `test_gate4_score_above_threshold` | verdict(photoreal_score=80) + threshold=75 | `above_threshold` | sidecar.user_friendly_summary 含 "80" |
| **5b** | **`test_gate4_score_equals_threshold`**（rev 2 新） | verdict(photoreal_score=75) + threshold=75 | `above_threshold` | 锁 ≥ 而非 > 边界 |
| 6 | `test_gate5_budget_capped` | budget.try_spend → False | `cost_capped` | sidecar.extra_cost_usd == budget.spent |
| 7 | `test_gate6_no_tags_parsed` | reason="完全未知文本不含已知 tag" | `no_tags_parsed` | sidecar.tags_parsed=[] |
| 8 | `test_gate7_all_miss_llm_fallback_off` | tags 全 unknown + config.llm_fallback=False | `no_rules_hit_no_llm` | - |
| 9 | `test_gate8_backend_auth_error` | adapter.call → BackendAuthError | `retry_auth_failed` | sidecar.errors[0].code 含 "auth" |
| 10 | `test_gate8_backend_rate_limit_error` | adapter.call → BackendRateLimitError | `retry_rate_limited` | - |
| 11 | `test_gate8_backend_quota_exceeded` | adapter.call → BackendQuotaExceededError | `retry_quota_exceeded` | - |
| 12 | `test_gate8_backend_call_error` | adapter.call → BackendCallError | `retry_failed` | - |
| 13 | `test_normal_retry_improves_score` | retry_score=80 > baseline=58 (pick_max_jury) | `delivered_retry` | retry_score_delta=+22; delivered_kind="retry" |
| 14 | `test_normal_retry_degrades_score` | retry_score=50 < baseline=58 | `delivered_baseline` | retry_score_delta=-8; **delivered_score_delta=0**（rev 2 补）; delivered_kind="baseline"; retry 字段含完整 verdict |
| **14b** | **`test_normal_retry_equals_baseline`**（rev 2 新） | retry_score=58 == baseline=58 | `delivered_baseline` | retry_score_delta=0; delivered_score_delta=0; retry 字段含完整 verdict |
| 15 | `test_actual_cost_none_warns` | BackendResponse.actual_cost_usd=None | `delivered_retry`（或 retry 跑通形态） | sidecar.warnings 含 `"cost_estimated_only"` |
| 16 | `test_force_retry_strategy_skips_second_jury`（rev 2 扩） | config.score_select_strategy="force_retry" | `delivered_retry` (force_retry) | **5 字段全断**：retry.photoreal_score=null + retry.semantic_checks=null + retry.reason=null + retry.final_prompt 非空 + retry.backend_payload 非空 + retry_score_delta=null + delivered_score_delta=null（spec §4.4 line 530 全部约束） |
| **17** | **`test_jury_subprocess_timeout`**（rev 2 新） | subprocess.TimeoutExpired | `jury_unavailable` | sidecar.errors[0].code 含 "timeout" |
| **18** | **`test_jury_score_out_of_range`**（rev 2 新） | verdict(photoreal_score=200) | `jury_unavailable` | parse_view_verdict 在该路径 clamp + needs_review；orchestrator 视同 jury 失败 |
| **19** | **`test_adapter_estimate_returns_nan`**（rev 2 新） | adapter.estimate_cost_usd=NaN | `retry_failed` | sidecar.errors[0].code="estimate_invalid"; budget.spent 不变 |
| **20** | **`test_baseline_path_missing_raises`**（rev 2 新） | baseline_path 文件不存在 | raise FileNotFoundError | 不写 sidecar; 由 cmd_enhance 兜 |
| **21** | **`test_finalize_oserror_keeps_budget_accounting`**（rev 2 新） | `_finalize` 第一步 Path.replace 抛 OSError | `retry_failed` | sidecar.errors[0].code="finalize_rename_failed"; sidecar.extra_cost_usd == budget.spent（不丢账）; final_path 是 V1_enhanced.jpg（实际不存在的占位 — rename 失败后调用方知情靠 errors[]） |
| **22** | **`test_unknown_exception_writes_sidecar_then_raises`**（rev 2 新） | 故意 patch rule_table.lookup 抛 ValueError | raise ValueError | finally 块写 sidecar.loop_status="retry_failed"; sidecar.extra_cost_usd == budget.spent; cmd_enhance 兜 ValueError 仅 log |
| **23** | **`test_finalize_partial_rename_failure_preserves_baseline`**（rev 2 新） | `_finalize` 第一步成功（retry → enhanced）但第二步失败（baseline → enhanced_baseline） | `delivered_retry` 但 sidecar.warnings 含 "finalize_partial" | retry 已成为最终交付；baseline 文件名 stale 但内容完整 |

**测试矩阵补强说明**：5b/14b/17/18/19/20/21/22/23 共 9 个新测试覆盖 reviewer 边界审 6 项严重 + 3 项中优；总用例 16 → 24。

---

## §6 mock fixture（tests/jury_loop/conftest.py 新增；rev 2 字段对齐真签名）

```python
# 保留现有 fixture_dir / sample_reason_plastic_flat / builtin_yaml_path

@pytest.fixture
def fake_view_verdict():
    """ViewVerdict factory；字段集对齐 tools/jury/verdict.py 真签名 6 字段。"""
    def _make(
        score: int = 58,
        reason: str = "plastic look, flat lighting",
        verdict: str = "accepted",
        parse_anomalies: list[str] | None = None,
        semantic_checks: dict[str, bool] | None = None,
    ) -> ViewVerdict:
        return ViewVerdict(
            semantic_checks=semantic_checks or {
                "geometry_preserved": True,
                "material_consistent": True,
                "photorealistic": False,   # 默认低分场景
                "no_extra_parts": True,
                "no_missing_parts": True,
            },
            photoreal_score=score,
            reason=reason,
            parse_status="ok",
            parse_anomalies=parse_anomalies or [],
            verdict=verdict,
        )
    return _make


@pytest.fixture
def fake_backend_adapter():
    """注册 stub adapter 到 BACKEND_REGISTRY 的 context manager。

    rev 2 修：完整 _FakeAdapter stub 实现 5 个 BackendAdapter Protocol 成员；
    用 register_backend 公共 API（不绕过 isinstance 校验）；
    cleanup 用 BACKEND_REGISTRY.pop（dict 原生 API，cleanup 不需类型校验合法）。
    默认 kind="test_stub" 防与内置 fal_comfy / openai_images_edit / gemini_chat_image / comfyui_workflow_cloud 撞名（register_backend 重名抛 ValueError）。
    """
    @contextmanager
    def _register(
        kind: str = "test_stub",
        call_returns: BackendResponse | None = None,
        raises: BaseException | None = None,
        estimate_cost_usd: float = 0.05,
    ):
        class _FakeAdapter:
            @property
            def kind(self) -> str: return kind
            @property
            def known_params(self) -> dict[str, tuple[float | None, float | None]]: return {}
            def supports_controlnet(self) -> bool: return False
            def estimate_cost_usd(self, request) -> float: return estimate_cost_usd
            def call(self, request, timeout):
                if raises is not None: raise raises
                return call_returns
        adapter = _FakeAdapter()
        register_backend(adapter)  # type-check 通过 @runtime_checkable
        try:
            yield kind
        finally:
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
    """JuryLoopConfig factory。

    字段集对齐 plan Task 7.2 (line 1323-1333)：
    - 顶层：enabled / cost_cap_usd
    - backend 嵌套（BackendConfig）：kind / base_url / api_key_env / model_name / timeout_s
    - advanced 嵌套：threshold / max_retries / llm_fallback / rule_table_path / score_select_strategy
    """
    def _make(
        *,
        enabled: bool = True,
        cost_cap_usd: float = 1.5,
        backend_kind: str = "test_stub",
        threshold: int = 75,
        llm_fallback: bool = False,
        score_select_strategy: str = "pick_max_jury",
        max_retries: int = 1,
        rule_table_path: Path | None = None,
    ) -> JuryLoopConfig:
        from tools.jury_loop.config import BackendConfig  # plan Task 7.2 嵌套
        return JuryLoopConfig(
            enabled=enabled,
            cost_cap_usd=cost_cap_usd,
            backend=BackendConfig(
                kind=backend_kind,
                base_url="https://example.test",
                api_key_env="TEST_API_KEY",
                model_name="test-model",
                timeout_s=60,
            ),
            advanced={
                "threshold": threshold,
                "max_retries": max_retries,
                "llm_fallback": llm_fallback,
                "rule_table_path": rule_table_path,
                "score_select_strategy": score_select_strategy,
            },
        )
    return _make
```

---

## §7 异常隔离与 fail-safe（rev 2 重写）

### orchestrator 自捕获范围（rev 2 扩）
- `BackendError` 4 子类：内部 catch + `_classify_backend_error` 分类 + 写 sidecar `errors[]`
- `subprocess.CalledProcessError` / `subprocess.TimeoutExpired` / `json.JSONDecodeError`：在 `_call_jury_subprocess` 内捕获返 None；上层映射 `jury_unavailable`
- **`_finalize` OSError**（rev 2 改）：内部 catch → `loop_status="retry_failed"` + `errors[].code="finalize_rename_failed"`；不向上抛
- **NaN/Inf 估算**（rev 2 新）：`adapter.estimate_cost_usd` 返 NaN/Inf 时视同 retry_failed + `errors[].code="estimate_invalid"`
- **score 越界**（rev 2 新）：`parse_view_verdict` 已 clamp 到 [0,100] + parse_anomalies "clamped"；orchestrator 检查 `parse_anomalies` 含非白名单（非 reason_sanitized / clamped）→ 视同 jury_unavailable

### orchestrator **不**自捕获范围（向上抛给 cmd_enhance）
- `FileNotFoundError`（baseline_path 不存在）：顶层第 1 行 fail-fast；不写 sidecar（cmd_enhance 已知 baseline 阶段失败）
- `ValueError`（_validate_view_basename 拒绝注入 view 名）：顶层第 2 行 fail-fast；不写 sidecar（view 名无法构造文件名）；cmd_enhance 仅 log + 跳过该视角
- `ValueError`（rule_table.lookup 等内部不该发生的异常）：顶层 try/finally 写尽量富的 sidecar 后向上抛
- 任何未知 `Exception`（user plugin 抛 plain Exception 等）：同上 try/finally 写 sidecar 后向上抛

### fail-safe 写盘策略（rev 2 新 — 修 B1+B2+B6）

```python
def run_loop_if_eligible(...) -> LoopResult:
    # Precondition fail-fast（不写 sidecar）
    if not baseline_path.is_file():
        raise FileNotFoundError(...)
    safe_view = metadata._validate_view_basename(view)  # 抛 ValueError 不写 sidecar

    state: dict[str, Any] = {
        "view": safe_view,
        "backend": backend_kind,
        "loop_status": "delivered_baseline",  # 默认兜底
        "loop_eligible": True,
        # ... 累计 baseline / retry / tags / rules / extra_cost_usd 等
    }
    sidecar_written = False
    try:
        # 主流程：8 Gate → retry → score_select → _finalize
        # 每完成一步往 state 追加字段
        # 已知异常（BackendError / OSError / NaN）内捕后修改 state["loop_status"] 字段
        ...
    finally:
        if not sidecar_written:
            try:
                metadata.write_sidecar(**state, render_dir=baseline_path.parent)
                sidecar_written = True
            except OSError:
                # write_sidecar 自身写盘失败 = 磁盘满/权限；fail-safe 链断
                # cmd_enhance 视角级 try/except 仅 log，不重复 write_degraded
                pass
    return LoopResult(...)
```

### sidecar 写盘 OSError（rev 2 新决议 — 修 B5）
- orchestrator 内 finally 块捕获 + 静默（已 log on failure）
- cmd_enhance 视角级兜底**不重复** `write_degraded_sidecar`（避免无限循环）；仅 stderr log
- 父 spec §5 line 612 "metadata.json 是事实来源" 加附注："写盘失败时 fail-safe 链断；视为不可恢复"

---

## §8 §11 follow-up（rev 2 闭合 + 新登记）

### rev 2 闭合
- ✅ `cost_capped` 形态 `extra_cost_usd` 由 caller 传 `budget.spent`：§5 测试 #6 锁
- ✅ `delivered_retry → delivered_kind="retry"` 严格性：父 spec metadata.write_sidecar batch review 已加 ValueError guard
- ✅ ViewVerdict 字段对齐：§6 fixture 用真 6 字段
- ✅ JuryLoopConfig 不存在前置：§1 头部声明 plan Task 7.2 提前作 Task 0
- ✅ `_apply_overrides` 不动 rc 改返 params dict：§4
- ✅ jury_profile 来源：§3 顶层加 kwarg
- ✅ rule_table 跨视角缓存：§3 顶层加 kwarg + cmd_enhance load 一次

### rev 2 新登记 §11 follow-up（仍开放）
1. **父 spec line 244 "可并行" 与 LoopBudget record_actual 配对约束冲突**：CP-5 决议 #11 (reference_mode=none → 不调 record_actual) 暂解；理想方案需父 spec 明示并发模式语义 / 或 enhance_budget 加 `_last_spent` 历史栈支持多 in-flight try_spend
2. **父 spec line 183 文案 `tags = reason_parser(sanitized_reason)`** 模块名当函数调用错；正确 `reason_parser.parse_reason(sanitized_reason)`；父 spec 同步小修
3. **父 spec line 191 `llm_fallback.translate(misses, sanitized_reason)`** misses (set) 当 str 传错；正确 `translate(unmapped_reason=sanitized_reason, sanitized_reason=sanitized_reason, profile=jury_profile) if misses and config.llm_fallback`；父 spec 同步小修
4. **父 spec §6 jury single-view CLI 输出 schema** 列出每张图字段，但与 ViewVerdict dataclass 结构不直接对应；CP-6 实施时确保 stdout JSON 经 parse_view_verdict 后构造 ViewVerdict 正常
5. **`write_degraded_sidecar backend="unknown"`** 不在 spec §4.4 enum 内：建议父 spec 加为合法值或文档化为 cmd_enhance pre-classification 异常专用
6. **CP-6 `--single-view` flag 实际命名**：CP-5 spec _call_jury_subprocess 暂用 `--single-view --image`；CP-6 plan 决议时如改名同步父 spec § 6 + 本 spec §4

---

## §9 提交策略

- spec rev 2 写出 + 自审 → commit `docs(spec): CP-5 子 spec rev 2 — 4 reviewer 30 findings 修订`
- 用户审 rev 2 通过 → 进 writing-plans skill 输出 plan 文件
- plan 阶段先拆 Task 0（落地 JuryLoopConfig，复用 plan Task 7.2 内容）；再拆 Task 5.1 子步骤
- subagent-driven 实施由 plan 阶段决议（per session 36 教训"CP-末 batch reviewer"高效）

---

## §10 自审记录（rev 2）

按 4 reviewer × 30 findings 闭合表：

### 数据 reviewer（6 项）
| # | finding | 闭合点 | 状态 |
|---|---|---|---|
| D1 | ViewVerdict.kind/view 字段不存在 | §6 fixture 改 6 字段 | ✅ |
| D2 | 测试 #16 force_retry 仅 1/5 字段 | §5 #16 扩到 7 项验收 | ✅ |
| D3 | JuryLoopConfig 不存在 | §1 头部前置 + §6 fixture 用真 schema | ✅ |
| D4 | 测试 #14 漏 delivered_score_delta=0 | §5 #14 加该项 | ✅ |
| D5 | fixture 显式 5 字段 semantic_checks | §6 改全列名 | ✅ |
| D6 | _call_jury_subprocess 注释歧义 | §4 改用 parse_view_verdict | ✅ |

### 函数 reviewer（11 项）
| # | finding | 闭合点 | 状态 |
|---|---|---|---|
| F1 | jury_profile 来源 | §3 顶层加 kwarg | ✅ |
| F2 | rule_table.lookup 漏 table | §3 顶层加 RuleTable kwarg | ✅ |
| F3 | translate 漏 profile + 类型错 | §11 #3 父 spec 同步 + CP-5 §3 [5] 写明 | ✅ |
| F4 | fixture stub 5 Protocol 成员 | §6 _FakeAdapter 完整实现 | ✅ |
| F5 | ViewVerdict.kind 字段错 | 同 D1 | ✅ |
| F6 | JuryLoopConfig 前置错 | 同 D3 | ✅ |
| F7 | plan kwarg-only 同步 | §11 plan 阶段同步 | ✅ |
| F8 | jury_callable lambda 包装 | §4 _call_jury_subprocess 由顶层 lambda 包给 strategy.select | 待 plan 阶段细化 |
| F9 | estimate_retry_cost 调用顺序 | §3 docstring 含调用链顺序 | ✅ |
| F10 | reason_parser.parse_reason 写法 | §11 #2 父 spec 同步 | ✅ |
| F11 | subprocess.run sys.executable + --config | §4 改 sys.executable + 加 --config 参数 | ✅ |

### plan-drift reviewer（6 项）
| # | finding | 闭合点 | 状态 |
|---|---|---|---|
| P1 | JuryLoopConfig 不存在 | 同 D3 | ✅ |
| P2 | ViewVerdict 字段错 | 同 D1 | ✅ |
| P3 | rc[backend] 字典结构错 | §2 决议 #9 + §4 _apply_overrides 改返 params | ✅ |
| P4 | --single-view flag 不存在 | §1 非目标 + §11 #6 | ✅ |
| P5 | BACKEND_REGISTRY 重名 | §6 fixture 默认 kind="test_stub" | ✅ |
| P6 | fixture 字段名待 Task 7.2 锁 | §6 字段对齐 plan Task 7.2 | ✅ |

### 边界 reviewer（14 项）
| # | finding | 闭合点 | 状态 |
|---|---|---|---|
| B1 | 未知 Exception → budget-sidecar 不一致 | §7 try/finally state 容器 | ✅ |
| B2 | _finalize OSError → retry_failed 误报 | §2 决议 #7 + §4 _finalize 改内捕 | ✅ |
| B3 | NaN 入 try_spend | §2 决议 #10 + enhance_budget 模块加 isfinite 校验 | ✅ |
| B4 | 并发 record_actual 数据竞争 | §2 决议 #11（reference_mode=none 不调 record_actual） | ✅ |
| B5 | write_sidecar OSError 双重失败 | §7 cmd_enhance 仅 log 不重写 | ✅ |
| B6 | _finalize OSError sidecar 信息退化 | §2 决议 #6+#7 try/finally 写富 sidecar | ✅ |
| B7 | subprocess timeout 来源 + TimeoutExpired 列表 | §4 timeout 来自 config.backend.timeout_s + §7 列入 | ✅ |
| B8 | rule_table/path-净化 ValueError | §7 view 验证 fail-fast 不写 sidecar；rule_table ValueError try/finally 写 | ✅ |
| B9 | score == threshold 边界测试 | §5 #5b 加 | ✅ |
| B10 | score 越界 | §7 + §5 #18 | ✅ |
| B11 | retry == baseline 17th 测试 | §5 #14b 加 | ✅ |
| B12 | baseline_path 不存在 | §3 Precondition + §5 #20 | ✅ |
| B13 | Gate-1/2 rename helper 位置 | §4 加 `_rename_baseline_as_final` helper | ✅ |
| B14 | _finalize 事务式 rename | §4 _finalize 改"第一步失败原状返" | ✅ |

### 综合
- **闭合 30/30**：致命 9 + fail-safe 5 + 中优 11 + 轻 5 全部回应
- **新增 3 项 §11 follow-up**（父 spec 同步小修；不阻断 CP-5 实施）
- **测试矩阵 16 → 24**（+5b/14b/17/18/19/20/21/22/23）
- **顶层签名加 2 kwarg**（jury_profile / rule_table）；helper 数 5 → 6（加 _rename_baseline_as_final）
- **rev 1 vs rev 2 文件大小**：244 行 → 540 行（+121%）

---

## §11 修订日志

| Rev | 日期 | 改动 |
|---|---|---|
| 1 | 2026-05-10 session 5 | 初版 brainstorm 5 决议 + 16 测试矩阵；commit `76ef3a8` |
| 2 | 2026-05-10 session 5（接审） | 4 reviewer batch 30 findings 修订；决议 5 → 11；测试 16 → 24；helper 5 → 6；顶层签名加 jury_profile/rule_table；fail-safe 重写 try/finally state 容器；ViewVerdict/JuryLoopConfig 字段对齐真签名 |
