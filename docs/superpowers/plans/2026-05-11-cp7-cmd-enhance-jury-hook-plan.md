# CP-7 cmd_enhance 视角级 jury hook + --rerun-loop 实施 plan

**parent**：`docs/superpowers/plans/2026-05-10-jury-prompt-loop-plan.md` §CP-7（line 1284）
**parent spec**：`docs/superpowers/specs/2026-05-10-jury-prompt-loop-design.md` §6 / §7
**branch**：`feat/sp1-cp7-cmd-enhance-jury-hook` / base main@`bc2db41`（v2.33.0）
**前置**：CP-6 v2.33.0 已发；orchestrator.`run_loop_if_eligible()` 签名（`tools/jury_loop/orchestrator.py:390`）已稳

## 范围（3 task，inline TDD）

cmd_enhance 改动跨 argparse + 视角循环内 + 循环出口聚合 3 处，按 RED→GREEN 拆 3 step；配置段 1 step；不派 subagent（跨同函数高耦合）。

| Task | Files | 说明 |
|---|---|---|
| 7.1.1 | `cad_pipeline.py` argparse 入口（line ~4400-4475 enhance subparser）+ helper + 测试 | 加 `--rerun-loop` flag + `_should_skip_jury_loop_for_view(view, render_dir) -> bool` helper（OPS-MAJOR-3 fast-path） |
| 7.1.2 | `cad_pipeline.py:cmd_enhance` 视角循环 + 测试 | baseline 完成后插 `run_loop_if_eligible` 调用 + try/except 三分支（FileNotFoundError / ValueError / 通用 Exception）+ v1_anchor 状态传 `hero_image` |
| 7.1.3 | `cad_pipeline.py:cmd_enhance` 循环出口 + 测试 | 视角循环结束聚合 `loop_summary`（仅 `enabled=true` 时写入 ENHANCEMENT_REPORT，OPS-MAJOR-2） |
| 7.2.1 | `pipeline_config.json` + 测试 | 顶层加 `jury_loop` 段实例（5 backend + 5 advanced 字段）；1 集成测试锁 schema 加载路径 |

测试文件复用 `tests/jury_loop/test_cmd_enhance_integration.py`（不存在则新建）。

---

## Task 7.1.1：`--rerun-loop` flag + sidecar skip helper

**RED 测试**（`tests/jury_loop/test_cmd_enhance_integration.py` 新建）：

1. `test_rerun_loop_flag_argparse_present`：`build_parser` 给 enhance subcommand argparse `--rerun-loop` flag 存在，默认 `False`
2. `test_should_skip_jury_loop_for_view_existing_sidecar_default`：临时 render_dir 写一份模拟 sidecar `V1.jury_loop.json`（含 `delivered_retry=true`）+ `args.rerun_loop=False` → helper 返 `True`（fast-path 跳过）
3. `test_should_skip_jury_loop_for_view_rerun_force`：同上但 `args.rerun_loop=True` → helper 返 `False`（强制重跑）
4. `test_should_skip_jury_loop_for_view_no_sidecar`：render_dir 无 sidecar → helper 返 `False`（首次跑）

**GREEN 实现**：

- argparse：找 enhance subparser（line ~4400-4475），加 `enh_p.add_argument("--rerun-loop", action="store_true", help="强制重跑 jury loop 即使 sidecar 已存在 delivered_retry")`
- helper 放在 `cad_pipeline.py` 顶层（或 `tools/jury_loop/sidecar_helpers.py` 新模块）：

```python
def _should_skip_jury_loop_for_view(view: str, render_dir: Path, rerun_loop: bool) -> bool:
    """OPS-MAJOR-3：sidecar 已存在 delivered_retry 时 fast-path 跳过；--rerun-loop 强制重跑。"""
    if rerun_loop:
        return False
    sidecar = render_dir / f"{view}.jury_loop.json"
    if not sidecar.is_file():
        return False
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        return data.get("delivered_retry") is True
    except (json.JSONDecodeError, OSError):
        return False  # 损坏 sidecar 重跑
```

**验收**：4 PASS / ruff / mypy strict / 全套件 0 regression

**Commit**：`feat(cmd-enhance): --rerun-loop flag + sidecar skip helper（OPS-MAJOR-3，CP-7 Task 7.1.1）`

---

## Task 7.1.2：视角循环插 jury hook + try/except 异常隔离

**RED 测试**（同文件 4 case）：

1. `test_jury_hook_normal_path_invoked`：mock `orchestrator.run_loop_if_eligible` 返 `LoopResult(final_path=...)`，跑单视角 → hook 被调用 1 次 + 视角输出有 `_enhanced` 文件
2. `test_jury_hook_unknown_exception_isolated`：mock orchestrator raise `RuntimeError("X")` → 当前视角 log.error 后 `continue`，下视角不受影响（DRIFT-MAJOR-7）
3. `test_jury_hook_filenotfounderror_fail_fast`：mock orchestrator raise `FileNotFoundError("baseline missing")` → log.warning + continue + **不重写 sidecar**（防误覆盖）
4. `test_jury_hook_v1_anchor_state_passes_to_v2`：`reference_mode=v1_anchor` + V1 retry 成功 → `hero_image` 在 V2 处理时等于 V1 enhanced 路径（BL-4）

**GREEN 实现位置**：

baseline `enhance_image()` 调用块（line 2811 起 `for png in pngs:` 内，gemini path line ~3100 / fal_comfy path line ~2947 设 `hero_image = new_path` 之后）插入：

```python
# CP-7 视角级 jury loop hook
if not _should_skip_jury_loop_for_view(view_key, Path(render_dir), getattr(args, "rerun_loop", False)):
    try:
        loop_result = orchestrator.run_loop_if_eligible(
            view=view_key,
            backend_kind=jury_loop_config.backend.kind,
            rc=rc,
            baseline_path=Path(new_path) if new_path else Path(png),
            base_params=baseline_backend_params,
            budget=loop_budget,
            project_root=PROJECT_ROOT,
            config=jury_loop_config,
            jury_profile=jury_profile,
            jury_profile_path=jury_profile_path,
        )
        if _ref_mode == "v1_anchor" and view_key == "V1" and loop_result.final_path:
            hero_image = str(loop_result.final_path)
    except FileNotFoundError as e:
        log.warning("Loop hook precondition failed for %s (baseline missing): %s", view_key, e)
    except ValueError as e:
        log.error("Loop hook precondition failed for %s (invalid view): %s", view_key, e)
    except Exception as e:
        # 未知 Exception：orchestrator 内层已 write_degraded_sidecar；仅 log 不重写 sidecar 防无限循环
        log.error("Loop hook crashed for %s: %s", view_key, e)
```

**前置常量** 在 cmd_enhance 顶部（视角循环之前）：
- `jury_loop_config = load_jury_loop_config(_pcfg)`（Task 7.2.1 落地 pipeline_config.json `jury_loop` 段后此调用才可用）
- `jury_profile, jury_profile_path = load_jury_profile_from_config(...)`
- `loop_budget = LoopBudget(cap_usd=jury_loop_config.cost_cap_usd)`
- `baseline_backend_params = ...`（baseline enhance_image 实际生效的 backend params）

**降级守卫**：`jury_loop_config.enabled` 为 False 或 config 加载失败 → hook 整体跳过；当前 Task 7.1.2 此守卫返"None loop_result"分支 OK（不调 hook 即可），不需 raise。

**验收**：4 PASS / 全套件 0 regression / ruff / mypy strict

**Commit**：`feat(cmd-enhance): 视角级 jury hook + try/except 异常隔离 + v1_anchor 状态传递（BL-4 + DRIFT-MAJOR-7，CP-7 Task 7.1.2）`

---

## Task 7.1.3：循环出口聚合 loop_summary + 条件写 ENHANCEMENT_REPORT

**RED 测试**（同文件 2 case）：

1. `test_loop_summary_aggregated_when_enabled`：跑 3 视角（1 delivered_retry / 1 baseline_kept / 1 jury_unavailable）+ `jury_loop.enabled=true` → ENHANCEMENT_REPORT.json 顶层有 `loop_summary` key，含计数 + per-view loop_status_zh
2. `test_loop_summary_absent_when_disabled`：同 fixture 但 `jury_loop.enabled=false` → ENHANCEMENT_REPORT.json **不**含 `loop_summary` key（OPS-MAJOR-2）

**GREEN 实现**：

- 视角循环结束（line ~3100 末尾，写 ENHANCEMENT_REPORT 前）聚合：
  ```python
  loop_summary = None
  if jury_loop_config.enabled:
      loop_summary = _aggregate_loop_summary(render_dir, [extract_view_key(p, rc) for p in pngs])
  ```
- helper 函数 `_aggregate_loop_summary(render_dir, views) -> dict` 读每视角 `<V>.jury_loop.json` sidecar 聚合 → 返 `{"total": N, "delivered_retry": ..., "baseline_kept": ..., "jury_unavailable": ..., "per_view": [{"view": ..., "loop_status_zh": ...}]}`；缺失 sidecar 归 `not_attempted`
- ENHANCEMENT_REPORT.json 写盘代码处加 `if loop_summary is not None: report["loop_summary"] = loop_summary`

**验收**：2 PASS / 全套件 0 regression / autopilot 旧解析器读 v1 报告不爆（v0/v1 additive-only）/ ruff / mypy strict

**Commit**：`feat(cmd-enhance): 视角循环出口聚合 loop_summary 条件写 ENHANCEMENT_REPORT（OPS-MAJOR-2，CP-7 Task 7.1.3）`

---

## Task 7.2.1：pipeline_config.json `jury_loop` 段 + 集成测试

**RED 测试**（`tests/jury_loop/test_config_load_integration.py` 新建或扩 existing test_config）：

1. `test_pipeline_config_jury_loop_section_loadable`：读真实 `pipeline_config.json` → `load_jury_loop_config(json.load(...))` 返 `JuryLoopConfig` 实例（不 raise），`enabled=True` / `cost_cap_usd=1.5` / `backend.kind` 在 BACKEND_REGISTRY

**GREEN 实现**（`pipeline_config.json` 顶层加段，参考 spec §4.1）：

```json
{
  ...,
  "jury_loop": {
    "enabled": true,
    "cost_cap_usd": 1.5,
    "backend": {
      "kind": "fal_comfy",
      "base_url": "https://queue.fal.run",
      "api_key_env": "FAL_KEY",
      "model_name": "fal-ai/flux-realism",
      "timeout_s": 180
    },
    "advanced": {
      "max_retries_per_view": 2,
      "score_select_strategy": "highest",
      "fallback_to_baseline": true,
      "min_score_threshold": 75,
      "needs_review_window_sec": 600
    }
  }
}
```

具体字段值以 spec §4.1 为准；实施时 grep 现有 `pipeline_config.json` 顶层 key 不冲突。

**验收**：1 PASS / 全套件 0 regression / config schema 加载验证 / ruff / mypy strict

**Commit**：`feat(jury-loop): pipeline_config.json jury_loop 段实例（M-5 + M-6 + M-8，CP-7 Task 7.2.1）`

---

## 收尾

- 跑 jury_loop 套件 + 全套件
- ruff + mypy strict
- 开 PR base=main → 等 CI 8/8 SUCCESS → squash merge → tag **v2.34.0** + GitHub Release

## §11 跟进（不阻断本 PR）

- `cmd_enhance` 复杂度告警可在 Task 7.1.2 落地后再降（noqa 已有 / 拆 helper 是大重构推迟）
- L3 契约 + L4 smoke + 文档 → CP-8 单独 PR
- 父 plan line 1306 `jury_profile` 实例加载的 helper 函数（`load_jury_profile_from_config`）若 CP-6 未落地 → 本 PR Task 7.1.2 内一并加 thin wrapper

## 假设漂移自检（grep 前置）

实施前 Task 0 自检：
- `grep "def run_loop_if_eligible" tools/jury_loop/orchestrator.py` → 签名匹配 plan §Task 7.1.2 代码块
- `grep "def load_jury_loop_config" tools/jury_loop/config.py` → 函数存在（CP-5 已落地）
- `grep "BACKEND_REGISTRY" tools/jury_loop/backends/__init__.py` → registry dict 存在
- `grep "JuryProfile\|load_jury_profile" tools/jury_loop/` → 若 helper 名不符 → Task 7.1.2 用现有名

漂移点 ≥1 时 reviewer 调整 plan 后再 implementer 实施（参考 feedback_subagent_driven_main_agent_scouts.md 经验）。
