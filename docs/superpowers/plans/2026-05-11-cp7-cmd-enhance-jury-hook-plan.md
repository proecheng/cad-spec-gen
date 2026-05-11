# CP-7 cmd_enhance 视角级 jury hook + --rerun-loop 实施 plan（rev 2 — 漂移修正版）

**parent**：`docs/superpowers/plans/2026-05-10-jury-prompt-loop-plan.md` §CP-7（line 1284）
**parent spec**：`docs/superpowers/specs/2026-05-10-jury-prompt-loop-design.md` §6 / §7
**branch**：`feat/sp1-cp7-cmd-enhance-jury-hook` / base main@`bc2db41`（v2.33.0）
**前置**：CP-6 v2.33.0 已发；`orchestrator.run_loop_if_eligible()` 签名（`tools/jury_loop/orchestrator.py:390`）已稳

---

## rev 2 漂移修正（2026-05-12 主 agent 实测 grep + 读源码）

| # | rev 1 假设 | 实际 | 本 rev 处理 |
|---|---|---|---|
| 1 | Task 7.1.1 sidecar `<V>.jury_loop.json` + `delivered_retry` bool | orchestrator 写 `<V>_enhance_meta.json`（spec §4.4 / `metadata.py:309`）+ `loop_status` enum；fast-path 条件见 spec §6.2 | 拆 **Task 7.1.0 fix**：重写 `sidecar_skip.py` + `test_sidecar_skip.py`（已 push 的实现是死代码 bug） |
| 2 | Task 7.1.3 在 cmd_enhance 视角循环出口写 `ENHANCEMENT_REPORT.loop_summary` | `cmd_enhance` **不写**该文件；`cmd_enhance_check` → `tools/enhance_consistency.py:build_enhancement_report` 写 | loop_summary 聚合移到 `enhance_consistency.py`；`cmd_enhance` 只在末尾打一行中文 log（spec §6 D-5） |
| 3 | 默认 dict `backend.kind: "fal_comfy"` | `BACKEND_REGISTRY` 仅 `{gemini_chat_image, openai_images_edit, comfyui_workflow_cloud}`；`fal_comfy` 是 baseline enhance backend 名字面值不同概念 | 默认 `gemini_chat_image` |
| 4 | `LoopBudget(cap_usd=...)` | 真实签名 `LoopBudget(cap_usd: float|None=None, *, n_views: int)`（`enhance_budget.py:65`），`n_views` 必填关键字 | hook 实例化传 `n_views=len(pngs)` |
| 5 | `loop_result.final_path` 可能 None | `LoopResult.final_path` 恒 `Path`（含全 8 Gate 退出路径，`orchestrator.py:209`/`416`）| 守卫去掉 |
| 6 | （rev 1 未提）orchestrator `_rename_baseline_as_final` 把 `baseline_path` **rename** 为 `<view>_enhanced.jpg` | cmd_enhance 现产物名是 `V<i>_<ts>_enhanced.jpg`（带时间戳）| **决策见下"命名约定"段** |

### scoping 决策（写明，免下游再纠结）

- **fast-path 跳过的是"jury loop hook"，不是"整个视角的 baseline enhance"**。spec §6.2 字面是"跳过该视角的 enhance + 闭环"——但那要重构 baseline enhance 流程；SP1 仅跳 hook（昂贵部分 = jury subprocess + retry backend 调用 = 真花钱处），baseline enhance 仍跑（产物刷新）。"跳整个 enhance"登记 §11 follow-up（N-15）。
- **`DEFAULT_JURY_LOOP_DICT` 放 `tools/jury_loop/config.py`**（config 模块顶层），`cad_pipeline.py` + `tools/enhance_consistency.py` 都 import，避免循环依赖（pipeline_config.json 带 skip-worktree，不能加新字段——approach A）。
- **jury_profile 加载**：`tools/jury/config.py:load_jury_config(path) -> (JuryProfile, JuryCaps)`；path = `~/.claude/cad_jury_config.json`（`tools/photo3d_jury.py:109 _resolve_config_path` 已有 resolver——cmd_enhance 复制等价小逻辑或直接 import）。文件缺失 / schema 错 → **hook 整体跳过**（log warn，不报错，等价 `loop_disabled`）。
- **`base_params` 传 `{}`**：orchestrator 把 `base_params` 浅合并 rule `param_overrides`；retry backend (`gemini_chat_image`) 的基线参数留空，rule 命中时按需注入。pipeline_config.json 里没有 retry-backend 专用参数段（那些 `enhance.gemini`/`enhance.fal_comfy` 是 baseline backend 的），故 `{}`。

### 命名约定（漂移 #6 决策）

cmd_enhance **保持现有命名**（`V<i>_<ts>_enhanced.jpg`）不动（改它会破 archive/autopilot/现有测试）。hook 调用时把 baseline 的 `new_path` 传给 orchestrator 作 `baseline_path` → orchestrator `_rename_baseline_as_final` 把它 rename 成 `V<i>_enhanced.jpg`（含 Gate 退出路径也是这个名）。后果：

- hook **跑**的视角 → 最终产物 `V<i>_enhanced.jpg`（干净名）
- hook **没跑**的视角（jury 未配 / `enabled=false` / `new_path is None` / fast-path skip）→ 产物保持 `V<i>_<ts>_enhanced.jpg`

`build_enhancement_report._discover_enhanced_images` 用宽 glob 匹配 `*enhanced*`（实施前 grep 确认）——两种命名都能被发现。命名不一致登记 §11 follow-up（N-16：SP1.x 统一）。`new_path is None`（baseline enhance 跑了但产物未定位）→ **跳过 hook**（orchestrator 要求 `baseline_path.is_file()`，传 `png` 原始 render 无意义）。

---

## Task 7.1.0：修正 `sidecar_skip.py`（漂移 #1，bug fix，无 subagent）

**RED**（**重写** `tests/jury_loop/test_sidecar_skip.py`，14 case；helper `_write_meta(render_dir, view, loop_status)` 写 `<view>_enhance_meta.json`）：

| # | 场景 | 期望 |
|---|---|---|
| 1 | `loop_status=delivered_retry` + rerun=False | skip True |
| 2 | `loop_status=delivered_baseline` + rerun=False | skip True |
| 3 | `loop_status=above_threshold` + rerun=False | skip True |
| 4 | `loop_status=retry_auth_failed`（持久失败）+ rerun=False | skip True |
| 5 | `loop_status=retry_quota_exceeded` + rerun=False | skip True |
| 6 | `loop_status=jury_unavailable`（临时失败）+ rerun=False | skip False（仍重试） |
| 7 | `loop_status=retry_rate_limited` + rerun=False | skip False |
| 8 | `loop_status=cost_capped` + rerun=False | skip False（新跑 = 新 LoopBudget，给它再一次机会） |
| 9 | `loop_status=loop_disabled` + rerun=False | skip False（gate 检查很便宜） |
| 10 | `loop_status=delivered_retry` + rerun=True | skip False（强制重跑） |
| 11 | 无 sidecar 文件 | skip False |
| 12 | sidecar 非 JSON（损坏）| skip False |
| 13 | sidecar read 抛 OSError（monkeypatch）| skip False |
| 14 | sidecar 缺 `loop_status` key | skip False |

**GREEN**（`tools/jury_loop/sidecar_skip.py`）：

```python
#: spec §6.2 OPS-MAJOR-3：默认幂等模式下 fast-path 跳过的 loop_status 集合。
#: "已成功交付" {delivered_baseline, delivered_retry, above_threshold} +
#: "持久失败重跑无意义" {retry_auth_failed, retry_quota_exceeded}（修 key/充值后用 --rerun-loop）。
#: 临时失败（jury_unavailable / retry_failed / retry_rate_limited / cost_capped / ...）默认仍重试，不在此集合。
_FAST_PATH_SKIP_STATUSES = frozenset({
    "delivered_retry", "delivered_baseline", "above_threshold",
    "retry_auth_failed", "retry_quota_exceeded",
})

def should_skip_jury_loop_for_view(view: str, render_dir: Path, rerun_loop: bool) -> bool:
    if rerun_loop:
        return False
    sidecar = render_dir / f"{view}_enhance_meta.json"
    if not sidecar.is_file():
        return False
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("sidecar %s 损坏/读失败，重跑视角：%s", sidecar, e)
        return False
    return data.get("loop_status") in _FAST_PATH_SKIP_STATUSES
```

模块 docstring 更新（sidecar 文件名 = `<view>_enhance_meta.json`；skip-set 来源 spec §6.2）。

**验收**：14 PASS / `ruff check` / `mypy --strict` 0 issue / 全套件 0 regression
**Commit**：`fix(jury-loop): sidecar_skip 改读 _enhance_meta.json + spec §6.2 fast-path skip-set（CP-7 Task 7.1.0）`

---

## Task 7.2.1：`DEFAULT_JURY_LOOP_DICT` 内嵌默认（approach A，漂移 #3，无 subagent）

**RED**（新建 `tests/jury_loop/test_default_jury_loop_dict.py`）：

1. `DEFAULT_JURY_LOOP_DICT` 是 module-level dict（`from tools.jury_loop.config import DEFAULT_JURY_LOOP_DICT`）
2. `load_jury_loop_config(DEFAULT_JURY_LOOP_DICT)` 不抛，返 `JuryLoopConfig`；`.enabled is True`；`.cost_cap_usd == 1.5`
3. `DEFAULT_JURY_LOOP_DICT["backend"]["kind"] == "gemini_chat_image"`（且 ∈ 已知 BACKEND_REGISTRY key 集——可硬编码 3 元素集合断言，不 import backends 触发 lazy register）
4. `set(DEFAULT_JURY_LOOP_DICT["advanced"]) == {"threshold","max_retries","llm_fallback","rule_table_path","score_select_strategy"}`（与 `_ADVANCED_KEYS` 一致）
5. `set(DEFAULT_JURY_LOOP_DICT["backend"]) == {"kind","base_url","api_key_env","model_name","timeout_s"}`
6. 顶层 key 与 advanced 无同名碰撞（DRIFT-MAJOR-4 不触发）

**GREEN**（`tools/jury_loop/config.py` 顶部，`_ADVANCED_KEYS` 定义之后加）：

```python
#: approach A（pipeline_config.json 带 skip-worktree 不能加字段）：用户未在
#: pipeline_config["enhance"]["jury_loop"] 配置时，cmd_enhance / enhance_consistency 用此默认。
#: 用户可在 pipeline_config.json 自行写 enhance.jury_loop 段覆盖（per-machine）。
#: 字段对齐 spec §4.1。
DEFAULT_JURY_LOOP_DICT: dict[str, Any] = {
    "enabled": True,
    "cost_cap_usd": 1.5,
    "backend": {
        "kind": "gemini_chat_image",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "api_key_env": "GEMINI_API_KEY",
        "model_name": "gemini-2.5-flash-image",
        "timeout_s": 180,
    },
    "advanced": {
        "threshold": 75,
        "max_retries": 1,
        "llm_fallback": False,
        "rule_table_path": None,
        "score_select_strategy": "pick_max_jury",
    },
}
```

（`rule_table_path: None` = 用内置 `photoreal_v1.yaml`；`max_retries: 1` = spec §3 SP1 单轮；`score_select_strategy: "pick_max_jury"` = spec §4.5 默认。实施前 grep 确认 `load_jury_loop_config` 接受 `rule_table_path=None` 不抛——若抛则改成内置 yaml 资源相对路径或省略该 key（advanced 全 optional）。）

**验收**：6 PASS / `ruff` / `mypy --strict` / 全套件 0 regression
**Commit**：`feat(jury-loop): DEFAULT_JURY_LOOP_DICT 内嵌默认（approach A，pipeline_config 不动，CP-7 Task 7.2.1）`

---

## Task 7.1.2：cmd_enhance 视角级 hook + try/except + v1_anchor 状态传递（无 subagent — god function 高耦合）

> ⚠️ 这是本 plan 最重 task；先读 `cad_pipeline.py:2516-3218`（`cmd_enhance` 全身）+ 上面"命名约定"段，再动手。

### 结构

**(a) 视角循环之前**（line ~2735 `hero_image = None` 附近，紧跟 `_pcfg` / `_enhance_cfg` 解析后）加 hook 前置块：

```python
# ── CP-7 jury loop hook 前置：加载 config + jury_profile + budget ──
from tools.jury_loop import orchestrator
from tools.jury_loop.config import DEFAULT_JURY_LOOP_DICT, JuryLoopConfig, load_jury_loop_config
from enhance_budget import LoopBudget

jury_loop_config: JuryLoopConfig | None = None
loop_budget: LoopBudget | None = None
jury_profile = None
jury_profile_path: Path | None = None
try:
    _jl_dict = _pcfg.get("enhance", {}).get("jury_loop") or DEFAULT_JURY_LOOP_DICT
    jury_loop_config = load_jury_loop_config(_jl_dict)
except (ValueError, TypeError) as _jl_err:
    log.warning("jury_loop 配置无效，本次跑跳过闭环：%s", _jl_err)
    jury_loop_config = None
if jury_loop_config is not None and jury_loop_config.enabled:
    try:
        from tools.jury.config import load_jury_config
        jury_profile_path = _resolve_jury_config_path(args)  # 复用 photo3d_jury 等价逻辑（--config / ~/.claude/cad_jury_config.json）
        jury_profile, _ = load_jury_config(jury_profile_path)
        loop_budget = LoopBudget(cap_usd=jury_loop_config.cost_cap_usd, n_views=len(pngs))
    except (FileNotFoundError, OSError, ValueError) as _jp_err:
        log.warning("jury 未配置或配置错误（%s），本次跑跳过闭环；如需启用闭环请配置 ~/.claude/cad_jury_config.json", _jp_err)
        jury_loop_config = None  # 整体禁用 hook 的标记
```

（`_resolve_jury_config_path`：若 cad_pipeline 已有等价 helper 复用之；否则在 `cmd_enhance` 内 inline：`Path(getattr(args, "jury_config", None)) if getattr(args, "jury_config", None) else Path.home() / ".claude" / "cad_jury_config.json"`。`enhance` subparser **不必**新增 `--jury-config` arg（用户极少需要），缺则只走 home 路径——实施时确认 enhance subparser 现有 args，没 `--config` 就直接用 home 路径。）

**(b) 循环内 hook 闭包**（定义在 `for png in pngs:` 之前，与 `_pixel_seed` / `_is_render_acceptable` 等其他闭包并列）：

```python
def _run_loop_hook(view_key: str, new_path: str | None) -> None:
    """CP-7 视角级 jury→prompt 闭环 hook。异常隔离：任何失败只 log，不影响下一视角。"""
    if jury_loop_config is None or not jury_loop_config.enabled or loop_budget is None:
        return
    if not new_path or not os.path.isfile(new_path):
        return  # baseline enhanced 产物未定位，无 baseline_path 可传
    if should_skip_jury_loop_for_view(view_key, Path(render_dir), getattr(args, "rerun_loop", False)):
        log.info("  Loop hook skip %s（既有 sidecar fast-path；--rerun-loop 可强制重跑）", view_key)
        return
    nonlocal hero_image
    try:
        loop_result = orchestrator.run_loop_if_eligible(
            view=view_key,
            backend_kind=jury_loop_config.backend.kind,
            rc=rc,
            baseline_path=Path(new_path),
            base_params={},
            budget=loop_budget,
            project_root=Path(PROJECT_ROOT),
            config=jury_loop_config,
            jury_profile=jury_profile,
            jury_profile_path=jury_profile_path,
        )
        if _ref_mode == "v1_anchor" and view_key == "V1":
            hero_image = str(loop_result.final_path)  # BL-4：闭环最终交付张作 V2+ anchor
        log.info("  Loop hook %s → %s", view_key, loop_result.loop_status)
    except FileNotFoundError as e:
        log.warning("  Loop hook precondition failed for %s (baseline missing): %s", view_key, e)
    except ValueError as e:
        log.error("  Loop hook precondition failed for %s (invalid view): %s", view_key, e)
    except Exception as e:  # noqa: BLE001 — DRIFT-MAJOR-7 视角级隔离：未知 Exception 内层已 write_degraded_sidecar
        log.error("  Loop hook crashed for %s: %s", view_key, e)
```

注：`should_skip_jury_loop_for_view` 已在 cad_pipeline.py 顶部 import（Task 7.1.1 留下）。

**(c) 调用点**——baseline enhance 产出 `new_path` 之后、视角循环各成功分支末尾：
- table-driven 路径（comfyui/fal/fal_comfy/engineering）：在 line ~2951 的 `continue  # skip Gemini block` **之前**插 `_run_loop_hook(view_key, new_path)`。
- gemini 路径：在 line ~3116 `finally:` 块**之后**、line ~3118 labeled section **之前**插 `_run_loop_hook(view_key, new_path)`（此处 gemini enhance 已成功；失败的话上面早 `continue` 了）。

### v1_anchor 串行约束

spec §6 要求 `reference_mode=v1_anchor` 时视角循环串行（V1 hook 完才进 V2）。cmd_enhance 现 `for png in pngs:` 本就是串行（pngs 按 `view_sort_key` 排序，V1 在前），且无并行实现——**无需改动**，只需在 plan 注明"现状已满足，不要重构成并行"。

### RED 测试（`tests/jury_loop/test_cmd_enhance_integration.py` 新建，用 import cad_pipeline + monkeypatch 而非 subprocess——需直接调 `cmd_enhance` 并 mock orchestrator）

> ⚠️ import cad_pipeline 触发巨型脚本副作用；conftest 已有处理？实施前 grep `tests/conftest.py` + `tests/jury_loop/conftest.py`。若 import 太重，改用 monkeypatch 注入 + 直接调 `cad_pipeline.cmd_enhance(args)` 的轻量 fixture（构造 fake render_dir + render_manifest + 1 张 V1.png）。

1. `test_hook_invoked_after_baseline`：fake render_dir 1 张 V1.png + 假 manifest，backend=engineering（零外部依赖），monkeypatch `orchestrator.run_loop_if_eligible` 返 `LoopResult(final_path=render_dir/"V1_enhanced.jpg", loop_status="delivered_retry")` → cmd_enhance 跑完，hook 被调 1 次（用 mock.call_count）
2. `test_hook_disabled_when_jury_config_missing`：同上但 `~/.claude/cad_jury_config.json` 不存在（monkeypatch `Path.home` 指向 tmp）→ hook **不**被调，cmd_enhance 仍 exit 0
3. `test_hook_disabled_when_enabled_false`：pipeline_config 写 `enhance.jury_loop.enabled=false`（monkeypatch `_load_pipeline_config`）→ hook 不被调
4. `test_hook_unknown_exception_isolated`：2 张视角 V1/V2，mock `run_loop_if_eligible` 对 V1 raise `RuntimeError("boom")` → V1 log.error 后继续，V2 hook 仍被调（call_count==2），cmd_enhance exit 0（hook 异常不计 failures）
5. `test_hook_filenotfounderror_logged`：mock raise `FileNotFoundError("baseline gone")` → log.warning，不 raise，继续
6. `test_hook_v1_anchor_sets_hero`：`reference_mode=v1_anchor`，2 视角，mock V1 返 `LoopResult(final_path=.../"V1_enhanced.jpg", "delivered_retry")` → V2 处理时 `hero_image == str(.../"V1_enhanced.jpg")`（断言方式：再 mock `build_enhance_prompt` 或检查传给 gemini cmd 的 `--reference` arg；engineering backend 无 reference 概念 → 这条用 gemini backend + mock subprocess）
7. `test_hook_skipped_when_sidecar_fast_path`：预写 `V1_enhance_meta.json` `loop_status=delivered_retry`，无 `--rerun-loop` → hook 不被调
8. `test_hook_rerun_loop_forces`：同 7 但 `args.rerun_loop=True` → hook 被调

（测试可能需要 mock 较多 cmd_enhance 内部——若成本过高，砍到 3-4 个核心 case：invoked / disabled-when-no-jury / exception-isolated / v1_anchor。优先保 exception-isolated。）

**验收**：核心 case PASS / 全套件 0 regression / `ruff` / `mypy --strict`
**Commit**：`feat(cmd-enhance): 视角级 jury hook + try/except 隔离 + v1_anchor 状态传递（BL-4 + DRIFT-MAJOR-7，CP-7 Task 7.1.2）`

---

## Task 7.1.3：loop_summary 聚合（移到 `tools/enhance_consistency.py`，无 subagent）

### 实现位置

`build_enhancement_report`（`tools/enhance_consistency.py:64`）返回 dict **之前**，按 `enhance.jury_loop.enabled` 门控追加 `loop_summary` 段。

```python
# 在 build_enhancement_report 末尾、return {...} 之前：
result: dict[str, Any] = {... 现有字段 ...}
loop_summary = _aggregate_loop_summary(root, render_dir)
if loop_summary is not None:
    result["loop_summary"] = loop_summary
return result
```

新 helper `_aggregate_loop_summary(project_root: Path, render_dir: Path) -> dict | None`：
1. 判 enabled：`_jl = _read_pipeline_config_jury_loop(project_root)`（读 `<project_root>/pipeline_config.json` 的 `enhance.jury_loop`，缺则用 `DEFAULT_JURY_LOOP_DICT`）；`if not _jl.get("enabled", True): return None`（OPS-MAJOR-2：enabled=false → 整段不写）
2. 扫 `render_dir.glob("*_enhance_meta.json")` 读每份 sidecar（坏文件跳过 + 计入 `parse_errors` 计数，不抛）
3. 聚合 spec §7 字段（`$schema_version=1` / `loop_type="single_retry"` / `headline{improved_views, score_gain_total, extra_cost_cny}` / `user_friendly_summary`（中文，按计数拼）/ `n_views` / `delivered_baseline_count` / `delivered_retry_count` / `skipped_count` / `skipped_reasons{}` / `total_retries` / `extra_cost_usd` / `score_gain_avg` / `score_gain_total`），字段**保序**（dict 字面量顺序即序列化顺序，Python 3.7+ 保证）
4. `score_gain_*` 统计 `delivered_score_delta`（永非负）不是 `retry_score_delta`
5. `extra_cost_cny = round(extra_cost_usd * USD_TO_CNY_RATE, 2)`（`from enhance_budget import USD_TO_CNY_RATE`）
6. 无任何 sidecar（`*_enhance_meta.json` 一个都没有）→ 仍返回 `loop_summary`（全 0 计数）？还是 `None`？**决策：返 None**——没跑过闭环（sidecar 都没有）说明这个 render_dir 的 enhance 没经过 hook，不该凭空写 loop_summary。L3 测试锁此。

### RED 测试（`tests/jury_loop/test_loop_summary_aggregation.py` 新建）

1. `test_aggregate_returns_none_when_disabled`：fake pipeline_config `enhance.jury_loop.enabled=false` + 1 份 sidecar → `_aggregate_loop_summary` 返 None
2. `test_aggregate_returns_none_when_no_sidecars`：enabled=true 但 render_dir 无 `*_enhance_meta.json` → 返 None
3. `test_aggregate_counts_mixed`：enabled=true + 3 份 sidecar（V1 `delivered_retry` delivered_score_delta=20 extra_cost_usd=0.18 / V2 `above_threshold` delta=0 cost=0 / V3 `jury_unavailable` delta=0 cost=0）→ 返 dict：`n_views==3` / `delivered_retry_count==1` / `delivered_baseline_count==2`（above_threshold + jury_unavailable 都算 baseline 交付）/ `skipped_count==0` / `total_retries==1` / `extra_cost_usd==0.18` / `score_gain_total==20` / `score_gain_avg==pytest.approx(20/1)` 或 `20/3`？**spec §7 注释：score_gain_avg = score_gain_total / delivered_retry_count（只对实际重试的视角平均）** → 实施按此 / `headline["extra_cost_cny"]==round(0.18*7.2,2)` / `headline["improved_views"]==1` / 字段顺序断言（`list(d)[:4]==["$schema_version","loop_type","headline","user_friendly_summary"]`）
4. `test_aggregate_handles_corrupt_sidecar`：2 份好 sidecar + 1 份非 JSON → 不抛，按 2 份聚合
5. `test_build_enhancement_report_includes_loop_summary_when_enabled`：端到端——构造 fake manifest + render_dir 含 1 张 enhanced + 1 份 sidecar + enabled=true → `build_enhancement_report(...)` 返回 dict 含 `"loop_summary"` key
6. `test_build_enhancement_report_omits_loop_summary_when_disabled`：同 5 但 enabled=false → `"loop_summary" not in report`（OPS-MAJOR-2）

### cmd_enhance 末尾中文 log（spec §6 D-5）

`cmd_enhance` `return 1 if failures else 0` **之前**，若 `jury_loop_config and jury_loop_config.enabled`：扫 `render_dir/*_enhance_meta.json` 聚合一行打印 `log.info("Loop summary: %d views, %d baseline-accept, %d retry-success, %d skip; extra cost $%.2f", ...)`。可复用 `_aggregate_loop_summary` 的内核（抽 `tools/enhance_consistency.py` 的纯计数函数 `_count_loop_sidecars(render_dir) -> dict`，cmd_enhance import 之）。或简化：cmd_enhance 只打 hook 调用次数 + budget.spent。**优先简化**——D-5 是 nice-to-have，核心是 loop_summary 进 ENHANCEMENT_REPORT。

**验收**：6 PASS / 全套件 0 regression / autopilot 旧解析器读 v1 报告不爆（`python -c "import tools.photo3d_autopilot"` 不报错）/ `ruff` / `mypy --strict`
**Commit**：`feat(enhance-consistency): ENHANCEMENT_REPORT 条件追加 loop_summary 聚合段（OPS-MAJOR-2 + spec §7，CP-7 Task 7.1.3）`

---

## 收尾

- 跑 `python -m pytest tests/jury_loop/ -v --tb=short`
- 跑全量 `python -m pytest --tb=short`
- `ruff check .` + `mypy --strict`（按 CI 配置的 source 集）
- autopilot import 自检
- 开 PR base=main → 等 CI 8/8 SUCCESS → squash merge → tag **v2.34.0** + GitHub Release

## §11 跟进（不阻断本 PR）

- **N-15**：fast-path 跳过扩展为"跳整个视角的 baseline enhance"（spec §6.2 字面语义；SP1 仅跳 hook）
- **N-16**：cmd_enhance 命名约定统一（hook 跑 → `V<i>_enhanced.jpg` / 没跑 → `V<i>_<ts>_enhanced.jpg` 不一致）
- L3 契约（`test_l3_contract.py`：sidecar / loop_summary JSON Schema 锁）+ L4 smoke（`@pytest.mark.requires_fal_key`）+ 用户文档 + AGENTS.md SP1 段 → CP-8 单独 PR
- `cmd_enhance` 圈复杂度告警：hook 落地后再评估是否拆 helper（大重构推迟）

## 假设漂移自检（实施前 grep）

- `grep -n "def run_loop_if_eligible" tools/jury_loop/orchestrator.py` → 签名匹配 §Task 7.1.2 代码块
- `grep -n "DEFAULT_JURY_LOOP_DICT\|_ADVANCED_KEYS" tools/jury_loop/config.py` → Task 7.2.1 后应见 DEFAULT_JURY_LOOP_DICT
- `grep -rn "_discover_enhanced_images\|_enhanced_candidates" tools/enhance_consistency.py` → 确认宽 glob 命名兼容（命名约定段）
- `grep -n "rerun_loop\|should_skip_jury_loop_for_view" cad_pipeline.py` → Task 7.1.1 留下的 import + flag
- `grep -rn "import cad_pipeline\|cmd_enhance" tests/conftest.py tests/jury_loop/conftest.py` → 确认 import 副作用处理
