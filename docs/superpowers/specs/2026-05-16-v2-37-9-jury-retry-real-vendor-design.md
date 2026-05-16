# v2.37.9 — jury verdict + retry 决策 + 真 vendor 端到端实测 设计

> **PR 类型**：feat + integration test（中体量）  
> **关联 STATUS doc**：`docs/superpowers/JURY_MATCHES_SPEC_STATUS.md`（§11 follow-up 新登 §11-N6）  
> **关联 retro**：`docs/superpowers/reports/2026-05-15-gisbot-jury-e2e-retro.md`（GISBOT photoreal=35-40 / status=preview 不 retry 实证出处）  
> **Spec rev**：rev 3（rev 1 layer 6 scout + rev 2 user review 5 处漂移 + rev 3 第二轮边界审查抓 1 BLOCKER + 1 MAJOR + 2 MINOR cascade fix）

---

## 1. 摘要

闭合 v2.37 GISBOT e2e retro 暴露的 **photoreal<60 不触发 retry** gap：

| 项 | 严重度 | 内容 | 工作量 |
| --- | --- | --- | --- |
| **§11-N6 改动 1** | LOW | `tools/jury/verdict.py:159` photoreal<60 升 `needs_review` + anomaly | ~5min |
| **§11-N6 改动 1b**（rev 3 BLOCKER fix）| **CRITICAL** | `tools/jury_loop/orchestrator.py:199` 扩 retry 白名单含 `photoreal_below_threshold` — 否则 verdict 改完 retry 仍不启动 | ~10min |
| **§11-N6 改动 1c**（rev 3 MAJOR fix）| **MAJOR** | `tools/photo3d_delivery_pack.py:144` status=needs_review 也走 copy_preview ship 兜底 — 防"改完比之前糟"路径 | ~5min |
| **§11-N6 改动 1d** | LOW | 适配 2-3 既有 preview-assert 测试 | ~10min |
| **§11-N6 改动 2** | LOW | `tools/jury_loop/config.py:48` `max_retries` 默认 1→2（支持 2 轮 retry 提升）| ~5min |
| **§11-N6 实测** | — | GISBOT 真 vendor 端到端跑完整 retry 闭环，验证 photoreal ≥60 | ~15min + ~$0.50 |

预计 PR 总规模：~2 文件 modify + 2-3 测试改 + 1 集成测 + 1 retro。

---

## 2. 背景

### 2.1 GISBOT e2e v2.37.7 实测出 photoreal 35-40 + retry 未启动

`D:/Work/cad-tests/GISBOT/cad/end_effector/.cad-spec-gen/runs/20260513T115709Z/PHOTO3D_JURY_REPORT.json` 实证：

- 7 views photoreal **真值 `[40,40,35,40,35,45,45]` avg=40 范围 35-45**（rev 2 D3 修正 — rev 1 写"35-40"低估上界）
- 全 `verdict=preview`
- `status=preview`（顶层）
- retry round 数 = 0（jury_loop retry 未启动）

按当前 `tools/jury/verdict.py:158-162` 决策：

```python
elif score < min_photoreal_score:  # min_photoreal_score=60 默认
    verdict = "preview"
```

photoreal<60 全归 `preview`，**`preview` 不触发 retry**（orchestrator.py:193 仅 `needs_review` 进 retry 分支）。

**用户视角矛盾**：preview="可发布的低质量" + accepted="高质量" + needs_review="差到必须 retry"，但 photoreal=35-40 实测"35 分的可发布"违反产品直觉。

### 2.2 Layer 6 Scout 揭示双阈值合理设计

| 阈值 | 来源 | 语义 | 当前值 |
| --- | --- | --- | --- |
| `verdict.min_photoreal_score` | `tools/jury/verdict.py:52` | 输出 verdict 三态门槛（accepted vs preview/needs_review）| 60 |
| `jury_loop.advanced.threshold` | `tools/jury_loop/config.py:47` + `orchestrator.py:519` | retry 短路（score≥75 不浪费 retry budget）| 75 |

**两阈值非 drift，是双层 gate**：

- score ≥75 → above_threshold，retry 短路（不 retry）
- 60 ≤ score < 75 → accepted（可发布）— rev 1 改动后此区间归 accepted
- 0 ≤ score < 60 → needs_review → 触发 retry（rev 1 改动）

Scout 实证 6+ tests 引用 `threshold=75`（`test_orchestrator.py:247` "spec §5 #5：score=80 ≥ threshold=75 → above_threshold"）。

**重要**：本 PR **不动 threshold:75** —— 是有效双层设计。spec 内显式记录其合理性防未来 drift 误删。

### 2.3 既有 preview-assert 测试

Scout 揭示：

- `tests/jury/test_verdict.py:97` `assert v.verdict == "preview"  # 0 < min 60`
- `tests/jury/test_verdict_matches_spec.py:64` `assert v.verdict in ("accepted", "preview")` 老 fixture 兼容

本 PR 改 photoreal<60 → needs_review 后这两 assert 必更新（破坏既有 fixture 兼容契约）。

---

## 3. 设计

### 3.1 改动 1 — `tools/jury/verdict.py:158-162` photoreal<60 升 needs_review

#### 3.1.1 代码 diff

```diff
@@ -156,11 +156,11 @@ def parse_view_verdict(...) -> ViewVerdict:
         verdict = "needs_review"
     elif "above_threshold_blocked" in anomalies:
         verdict = "preview"
-    elif score < min_photoreal_score:
-        verdict = "preview"
+    elif score < min_photoreal_score:
+        # v2.37.9 §11-N6 — photoreal<60 升 needs_review 触发 retry 闭环
+        anomalies = anomalies + ["photoreal_below_threshold"]
+        verdict = "needs_review"
     else:
         verdict = "accepted"
```

`anomalies` 加 `"photoreal_below_threshold"` 标识符方便 downstream 区分 needs_review 触发原因（与 `matches_spec_failed` 等其他触发因子区分）。

#### 3.1.2 行为对比

| photoreal score | rev 1 前 verdict | rev 1 后 verdict | retry 触发 |
| --- | --- | --- | --- |
| 60-100（无异常）| accepted | accepted | 不触发 |
| 35-59 | **preview** | **needs_review + anomaly=photoreal_below_threshold** | **触发** |
| layer 1 fail / parse 失败 | needs_review | needs_review | 触发 |
| 任何分但 matches_spec_failed | needs_review | needs_review | 触发 |
| 任何分但 above_threshold_blocked | preview | preview | 不触发 |

#### 3.1.3 既有测试适配

**`tests/jury/test_verdict.py:97`**：

```diff
-    assert v.verdict == "preview"  # 0 < min 60
+    # v2.37.9 §11-N6 — photoreal<60 升 needs_review
+    assert v.verdict == "needs_review"
+    assert "photoreal_below_threshold" in v.parse_anomalies
```

**`tests/jury/test_verdict_matches_spec.py:64`**：

```diff
-    assert v.verdict in ("accepted", "preview"), (
-        f"老 fixture verdict 必须 accepted/preview, 实际 = {v.verdict}; "
+    # v2.37.9 §11-N6 — photoreal<60 升 needs_review；老 fixture 若 score>=60 仍 accepted
+    assert v.verdict in ("accepted", "needs_review"), (
+        f"老 fixture verdict 必须 accepted/needs_review, 实际 = {v.verdict}; "
```

需要 grep 找其他 `verdict == "preview"` / `verdict in (... "preview" ...)` assert，逐个评估：

- **保留 preview 路径**：`above_threshold_blocked` (line 157) + layer 1 fail (orchestrator.py 兜底) 仍有 preview 真值。这些路径的 assert 不动。
- **改 preview→needs_review 路径**：仅当 fixture score<60 且无 anomaly 时

### 3.1b 改动 1b — `tools/jury_loop/orchestrator.py:199` 扩 retry 白名单（rev 3 BLOCKER fix）

#### 3.1b.1 真值证据链

第二轮审查发现 spec rev 2 改 verdict.py 不够 — orchestrator 早有 needs_review 路径决策：

```python
# orchestrator.py:193-201（当前实际行为）
if verdict.verdict == "needs_review":
    if "matches_spec_failed" in verdict.parse_anomalies:
        return (verdict, "matches_spec_failed")  # ← 仅这条走 retry
    return (None, "needs_review")                  # ← 其他全走 jury_unavailable 不 retry
```

photoreal<60 改 needs_review + anomaly `photoreal_below_threshold` 后**不在 matches_spec_failed 分支** → 走 line 199 → **不 retry**。

#### 3.1b.2 代码 diff

```diff
@@ -193,11 +193,15 @@ def _parse_verdict_with_anomaly_path(_json_str: str) -> tuple[Optional[ViewVerdi
     if verdict.verdict == "needs_review":
         # Task 9 v2.37 (C)：matches_spec_failed 路径保留 verdict 让上层走 retry 而非 jury_unavailable。
+        # v2.37.9 §11-N6：photoreal_below_threshold 同 retry path 但不 hint() — 仅重渲
         if "matches_spec_failed" in verdict.parse_anomalies:
             return (verdict, "matches_spec_failed")
+        if "photoreal_below_threshold" in verdict.parse_anomalies:
+            # verdict 完整可信（仅 photoreal 不达标，semantic_checks 仍 valid）
+            return (verdict, "photoreal_below_threshold")
         return (None, "needs_review")
     return (verdict, None)
```

#### 3.1b.3 retry path 处理差异

| anomaly | retry 提示策略 | spec ref |
| --- | --- | --- |
| `matches_spec_failed` | `prompt_rewriter.hint(features_status)` 拼到 enhance prompt 末尾 | orchestrator.py:566 |
| `photoreal_below_threshold`（新增）| **无 hint，仅重渲** — vendor 自然提升（更高质量）；不动 prompt template | rev 3 §3.1b |

`photoreal_below_threshold` 无须 hint 因为 photoreal 是 vision LLM 对"整体真实感"打分，没具体可 hint 的 feature 修复点。retry 仅靠 vendor 重渲随机性 + 不同 seed 提升。

#### 3.1b.4 测试 TDD

- T-orch-photoreal-retry：mock verdict.photoreal=40 / anomaly=photoreal_below_threshold → `_parse_verdict_with_anomaly_path` 返 `(verdict, "photoreal_below_threshold")` 不是 `(None, "needs_review")`
- T-orch-photoreal-rerun：完整 retry 闭环 mock，verify enhance 真被调一次 + retry verdict 真被评

### 3.1c 改动 1c — `tools/photo3d_delivery_pack.py:144` needs_review 兜底 ship（rev 3 MAJOR fix）

#### 3.1c.1 真值证据链

第二轮审查发现 cascade："改完比之前糟"路径：

```python
# photo3d_delivery_pack.py:143-144（当前实际行为）
final_deliverable = enhancement_status == "accepted"
copy_preview = enhancement_status == "preview" and include_preview
# ↑ status=needs_review 既不 final 也不 preview → 用户拿不到输出！
```

- v2.37.7: status=preview → `copy_preview` → 用户拿到 preview 输出（建议复核标签）
- v2.37.9 改 verdict 后: status=needs_review → 不 final 也不 preview → **用户拿不到输出**（退步）

#### 3.1c.2 代码 diff

```diff
@@ -143,7 +143,8 @@ def build_delivery_package(...):
     final_deliverable = enhancement_status == "accepted"
-    copy_preview = enhancement_status == "preview" and include_preview
+    # v2.37.9 §11-N6 — needs_review 兜底走 copy_preview 路径防"retry 用尽未达 60 用户拿不到输出"
+    copy_preview = enhancement_status in {"preview", "needs_review"} and include_preview
```

#### 3.1c.3 行为对比

| status | v2.37.7 行为 | v2.37.9 rev 2 行为 | v2.37.9 rev 3 行为（fix）|
| --- | --- | --- | --- |
| accepted | final ship | final ship | final ship（不变）|
| preview | copy_preview ship | copy_preview ship | copy_preview ship（不变）|
| **needs_review** | （v2.37.7 photoreal<60 走 preview 不会到 needs_review）| **不 final 不 preview**（退步！）| **copy_preview ship 兜底**（rev 3 fix）|
| accepted_pickup | final ship | final ship | final ship（不变）|

#### 3.1c.4 测试 TDD

- T-delivery-needs-review-ship：mock enhancement_status="needs_review" + include_preview=True → `copy_preview = True`
- T-delivery-accepted-final：保 final ship 不变（回归 anchor）

### 3.2 改动 2 — `tools/jury_loop/config.py:48` max_retries 1→2

```diff
-        "threshold": 75,
-        "max_retries": 1,
+        "threshold": 75,  # spec §2.2 双层 gate：retry 短路（score≥75 不 retry）— 不动
+        "max_retries": 2,  # v2.37.9 §11-N6 — 1→2 支持 2 轮 retry 提升 photoreal
```

#### 3.2.1 cost 分析

GISBOT 实测 v2.37.7 baseline：

- jury 7 views × ~$0.01/view = ~$0.07/round
- enhance retry: 1 image edit × 7 views × ~$0.04/view = ~$0.28/round
- 总 ~$0.35/retry round

`cost_cap_usd=1.5` 默认支持 ~4 round retry。`max_retries=2` 实际跑最多 2 轮 = ~$0.70 远低于 cap。

#### 3.2.2 既有测试影响（rev 2 D2 RISK-MAJOR 精确化）

rev 1 漏估 — scout 完整清单 ~6-7 test 真改：

| 文件 : 行 | 改动 | 说明 |
| --- | --- | --- |
| `tools/jury_loop/config.py:48` | `max_retries: 1` → `2` | production default |
| `tests/jury_loop/test_config.py:32+49+70+97+122` | 5 处 `"max_retries": 1` → `2` | default snapshot 测试 |
| `tests/jury_loop/conftest.py:186` | fixture default `max_retries: int = 1` → `2` | mirror production default |
| `tests/jury_loop/test_orchestrator.py:39` | **不动** `"max_retries": 1` — 是测 max_retries=1 场景的显式 fixture，与 default 无关 | scope 隔离 |

**无关命名空间**（误命中 grep — 不改）：

- `tests/jury/test_llm_client.py:120/166/187/204/222/250/272/289` — 是 LLM HTTP 客户端 retry 参数（HTTP 调用层）
- `tests/jury/test_photo3d_jury_matches_spec.py:726/799/868` — 是 mock 接口 signature 参数命名

plan Task 0 完整 grep verify scope（防 fixture caller 未传 max_retries 导致行为变化的潜在 cascade — caller 大多显式传 max_retries 或不依赖默认）。

### 3.3 实测 — GISBOT 真 vendor 端到端 retry 闭环

#### 3.3.1 前置

- 用户 touch `D:/Work/cad-tests/GISBOT/.test-archive-marker`（v2.37.8 已设此契约）
- 用户跑 `python tools/dev/rebrand_test_archive.py D:/Work/cad-tests/GISBOT --from end_effector --to GISBOT --apply` 一次（让 metadata 一致；v2.37.8 工具）
- 用户提供 GEMINI_API_KEY env var（retry backend gemini_chat_image）
- 用户提供 jury vendor key（如 micuapi.ai gpt-image-2-pro v2.37.7 实测过）

#### 3.3.2 跑命令

```bash
cd D:/Work/cad-tests/GISBOT
# rev 2 D5 — `cmd_enhance_check` 是 cad_pipeline.py:3325 内 def 非独立 module；
# plan Task 0 grep 验证 user-facing entry：
#   1) python -m cad_spec_gen.cad_pipeline enhance-check ...（subcommand 派发）
#   2) 或直接 `python -c "from src.cad_spec_gen.data.python_tools.cad_pipeline import cmd_enhance_check; ..."`
# 实际 invocation 由 plan Task 0 探查 cad_pipeline.py 顶部 argparse subparsers 确定
python -m cad_spec_gen.cad_pipeline enhance-check --skill end_effector --confirm \
  --max-cost-usd 0.50
```

#### 3.3.3 验收 AC

- jury 7 views photoreal ≥ 60（rev 1 前 35-40）
- 至少 1 视角触发 retry round（jury_review_input.json 内 retry log entry ≥1）
- delivery status 升 `accepted`（v2.37.7 是 preview）
- cost ≤ $0.50（用户授权预算）
- 实测耗时 ≤ 15min
- 实测数据进 retro（不进 git，外部归档）

#### 3.3.4 失败应对（rev 2 D1 RISK-MAJOR — "实测 fail 不退步" 说明）

| 场景 | 行为 |
| --- | --- |
| photoreal 提升但仍 <60 | retro 记录"vendor 能力不足 2 轮"，新登 §11 follow-up 调 max_retries=3 / 改 backend；**不算改完比之前糟** — 见下 |
| matches_spec_failed 触发 | 不阻 PR；jury_loop retry 已含此路径 |
| cost 超 $0.50 | hard stop / log warning / PR retro 记 |
| vendor 限流 502/429 | retry_rate_limited path 已有兜底 |
| retry **降分**（retry_score_delta<0）| `_pick_best` 机制保留 baseline / 不退步（rev 2 D4 — orchestrator.py:412 `retry_score_delta = retry.score - baseline.score 可正/0/负` + jury_loop v2.37.8 spec rev 5 `_pick_best` 选高分）|

**关键：实测 fail 不算改完比之前糟（rev 2 D1 防"改完糟" 风险定调）**：

- v2.37.7 baseline：photoreal 35-40 / verdict=preview / status=preview ship 不 retry → 用户拿到的是低质量但 "preview 可发布" 输出
- v2.37.9 改后即便 retry 2 轮 photoreal 仍<60：
  - jury_loop `_pick_best` 自动选高分 baseline / retry 中较优者作 final（不会无脑用 retry 降分版）
  - 即使 retry 全降分，final = baseline（与 v2.37.7 完全等价）
  - 多消耗 ~$0.70 retry 成本但**输出质量不退步**
- 所以本 PR 最差结果 = v2.37.7 baseline +$0.70 cost；最好结果 = photoreal ≥60 status=accepted
- **不存在 "改完比之前糟" 路径**（除非 vendor 能力问题 + 用户认为多花的 $0.70 算"糟"，但 cost_cap_usd=1.5 默认 + `--max-cost-usd 0.50` hard limit 防失控）

---

## 4. 不变量（项目级）

1. 北极星 5 gate 不破坏（零配置 / 稳定可靠 / 结果准确 / SW 装即用 / 傻瓜式操作）
2. **双阈值 gate 设计保留**：`verdict.min_photoreal_score=60`（输出三态）+ `jury_loop.threshold=75`（retry 短路）— 各自独立合理，本 PR 不动 threshold:75
3. `preview` verdict 不消失，仍保留给 `above_threshold_blocked` + layer 1 fail 等 fallback 路径
4. `needs_review` 触发 retry 路径不变（orchestrator.py:193），仅扩 trigger condition（photoreal<60 入此路径）
5. canonical/mirror 同步：dev_sync `--check` PASS

---

## 5. 验收（AC）

| AC | 期望 | 验证 |
| --- | --- | --- |
| AC-1 | `tools/jury/verdict.py` photoreal<60 → needs_review + anomaly=photoreal_below_threshold | grep + 单元测 |
| AC-2 | 既有 preview-assert 测试适配（test_verdict.py:97 + test_verdict_matches_spec.py:64）| pytest tests/jury/ -v |
| AC-3 | `jury_loop/config.py` max_retries=2 + test_config.py snapshot 同步 | grep + pytest tests/jury_loop/test_config.py |
| AC-4 | jury 子集回归 509+ PASS / 0 regression | pytest -q tests/jury/ tests/jury_loop/ |
| AC-5 | 全套件 3217+ PASS / 0 regression | pytest -q tests/ |
| AC-6 | 实测 GISBOT photoreal ≥ 60 / status=accepted | 实跑 + cat report |
| AC-7 | 实测 cost ≤ $0.50 | 实跑 stderr cost log |
| AC-8 | CI 8/8 SUCCESS | gh pr checks |
| AC-9 | dev_sync `--check` PASS | shell |

---

## 6. 范围（YAGNI）

**做**：
- verdict.py photoreal<60 → needs_review + anomaly + 既有测试适配
- jury_loop/config.py max_retries 1→2 + snapshot 测试更新
- 实测 GISBOT 真 vendor 端到端（retro 文档归档）
- 新加 TDD 测试覆盖 photoreal<60 新路径（含 anomaly assert）

**不做**（留下批）：
- **threshold:75 不动** — 双阈值合理设计（Scout 实证 6+ caller）
- max_retries 3+（实测后才决定是否再加）
- 调 photo3d_delivery 状态决策（仍由 jury verdict 派生）
- 改 cost_cap_usd 默认（保 1.5 不动）
- 实测多组 archive（仅 GISBOT；jiehuo 留下次）

---

## 7. 风险与权衡

| # | 风险 | 缓解 |
| --- | --- | --- |
| R1 | photoreal<60 全 retry 后仍<60 → 死循环 | max_retries=2 严格上限 + cost_cap_usd=1.5 hard stop |
| R2 | retry 提升 photoreal 但破坏 matches_spec_failed 语义 | 实测前后 features_status 不变（jury_review_input.json 比对）|
| R3 | 实测 cost 超 $0.50 用户授权 | `--max-cost-usd 0.50` 显式传 hard limit |
| R4 | preview verdict 改 needs_review 破坏既有 fixture | grep 完整覆盖 / per-test 评估保留 vs 改写 |
| R5 | vendor 限流 502/429 | jury_loop 已有 retry_rate_limited 路径 |
| R6 | enhance retry 真改图后 jury 再评 LLM 出 token 限流 | gemini_chat_image 有限流退避 |
| **R7**（rev 2 D1）| vendor 能力不足 2 轮 retry 提升不到 60 | `_pick_best` 保 baseline 不退步；实测 fail 进 retro 记录但 PR 不阻 / max_retries=3 留 §11-N7 follow-up |
| **R8**（rev 2 D4）| retry 降分（retry_score_delta<0）| `_pick_best` 机制保留 baseline；与 v2.37.7 baseline 等价 |
| **R9**（rev 3 B1）| orchestrator retry 路径白名单遗漏新 anomaly | 改动 1b orchestrator.py:199 +3 行 + T-orch-photoreal-retry TDD 硬保 |
| **R10**（rev 3 B4）| status=needs_review 用户拿不到输出（cascade 退步）| 改动 1c photo3d_delivery_pack.py:144 needs_review 兜底 copy_preview + T-delivery-needs-review-ship TDD 硬保 |

---

## 8. follow-up（本 PR 闭合后）

| 项 | 严重度 | 内容 |
| --- | --- | --- |
| §11-N6 | closed v2.37.9 ✓ | 本 PR |
| §12 f4 | LOW | N≥50 批量场景成本评估（v2.37.10 留）|
| 新登 §11-N7 | LOW | jury_loop max_retries 加 cli flag 用户可调（先做 spec rev 1 默认 2 不加 flag）|
| 新登 §11-N8 | LOW | photoreal 阈值 60/75 配置化（避未来 hardcode drift）|

---

## 9. Layer 6 fact-check + rev 1→rev 2 user review

### 9.1 Layer 6 scout（spec rev 1 时实证）

| Scout | 假设（brainstorm Q1 propose）| 实证 | spec rev 1 真值 |
| --- | --- | --- | --- |
| A | threshold:75 stale 无 caller | **6+ caller**（orchestrator.py:519 / 4+ tests）| §6 YAGNI **不动**，spec §2.2 标合理设计 |
| B | preview-assert 测试无影响 | 2 处 fixture assert 必改 | §3.1.3 详列 diff |
| C | retry trigger 是 verdict=needs_review | ✓ 实证 orchestrator.py:193 | §3.1.2 行为表 |
| D | jury_loop max_retries 默认 1 | ✓ 实证 config.py:48 | §3.2 改 2 |
| E | cost_cap_usd 默认 1.5 | ✓ 实证 config.py:38 | §3.2.1 不动 |

### 9.2 rev 1→rev 2 user review fix（5 处含 2 RISK-MAJOR）

| # | 漂移 | 严重度 | rev 2 fix 落点 |
| --- | --- | --- | --- |
| **D1** | vendor 能 boost photoreal 是未实证 assumption；实测可能 fail | **MAJOR** | §3.3.4 加 "实测 fail 不退步（_pick_best 保 baseline）" + §7 R7 |
| **D2** | max_retries 1→2 破坏 test scope 严重低估 | **MAJOR** | §3.2.2 详列 6-7 test + 排除 8 个 grep 无关命中 + plan Task 0 完整 grep |
| **D3** | photoreal 真值 35-45 avg=40 不是 "35-40" | MINOR | §2.1 数据修正 |
| **D4** | retry 可能降分（retry_score_delta<0）| MINOR | §3.3.4 含 _pick_best 行为 + §7 R8 |
| **D5** | cmd_enhance_check 实际 entry 是 cad_pipeline.py 内 def | MINOR | §3.3.2 entry candidate 列 + plan Task 0 探查 |

### 9.3 rev 2→rev 3 第二轮边界审查 fix（1 BLOCKER + 1 MAJOR + 2 MINOR）

| # | 漂移 | 严重度 | rev 3 fix 落点 |
| --- | --- | --- | --- |
| **B1+B2** | **orchestrator.py:199 photoreal_below_threshold 走 jury_unavailable 不 retry** — rev 2 改 verdict.py 后 retry 仍不启动！PR 主目的失败 | **BLOCKER** | 新增改动 1b（orchestrator +3 行扩 retry 白名单）+ T-orch-photoreal-retry/rerun TDD |
| **B4** | **status="needs_review" 既不 final 也不 copy_preview** — 用户拿不到输出（退步路径）| **MAJOR** | 新增改动 1c（photo3d_delivery_pack +1 行 needs_review 兜底 copy_preview）+ T-delivery-needs-review-ship TDD |
| **B7** | conftest fixture default 改后 caller 行为变 | MINOR | plan Task 0 grep `_make()` caller 是否传 explicit max_retries |
| **B9** | spec 内未明示 `photoreal_below_threshold` anomaly 与 matches_spec_failed 同 retry 语义 | MINOR | §3.1.2 行为表 + §3.1b.3 retry path 差异表 |

### 9.4 PR 主目的闭环（rev 3 实证）

| 阶段 | 路径 | 触发 |
| --- | --- | --- |
| 1. verdict 决策 | `verdict.py:159` photoreal<60 → needs_review + anomaly=photoreal_below_threshold | rev 2 改动 1 |
| 2. orchestrator retry 路径 | `orchestrator.py:199` photoreal_below_threshold → (verdict, "photoreal_below_threshold") | **rev 3 改动 1b** |
| 3. enhance retry 启动 | retry vendor 重渲（无 hint） | jury_loop 既有流程 |
| 4. 再 jury 评分 | retry_verdict.photoreal | jury_loop 既有 |
| 5. pick_best | retry vs baseline 选高分 | v2.37.8 spec rev 5 既有 |
| 6. status 派生 | 看最终 verdict 集合 | photo3d_jury.py:187-192 既有 |
| 7. delivery ship | accepted=final / preview=copy_preview / **needs_review=copy_preview** | **rev 3 改动 1c** |

链路 7 步全闭环 — 无任何 1 步走"用户拿不到输出"路径。

---

## 10. 关联文档

- STATUS doc：`docs/superpowers/JURY_MATCHES_SPEC_STATUS.md`
- v2.37.7 spec：`docs/superpowers/specs/2026-05-15-v2-37-7-jury-cli-improvements-design.md`
- v2.37.7 GISBOT e2e retro：`docs/superpowers/reports/2026-05-15-gisbot-jury-e2e-retro.md`（photoreal 35-40 实测出处）
- jury verdict 模块：`tools/jury/verdict.py:48-165`
- jury_loop orchestrator：`tools/jury_loop/orchestrator.py:193,519`
- jury_loop config：`tools/jury_loop/config.py:34-50`
