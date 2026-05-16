# v2.37.9 — jury verdict + retry + 真 vendor 实测 retro

> 关联 PR: TBD（Task 8 push 后填）
> 关联 spec: docs/superpowers/specs/2026-05-16-v2-37-9-jury-retry-real-vendor-design.md (rev 4, 509 行, commit `a7a4a85`)
> 关联 plan: docs/superpowers/plans/2026-05-16-v2-37-9-jury-retry-real-vendor.md (commit `a45c074`)
> Baseline: cad-spec-gen main@`7434b27`（v2.37.8 merge）

## 摘要

v2.37.9 闭合 §11-N6 — photoreal<60 + semantic_check=False 触发 retry 闭环。**真 vendor 实测两轮 expose 改动 1 NO-OP** → spec rev 4 加改动 1e+1f fix elif 链顺序漏洞。最终 PR 7 改动跨 5 production 文件 + 4 新 TDD 文件 + 4 既有适配 / 0 regression / CI 8/8（pending push） / GISBOT 真 vendor 实测 2 轮 cost $0.14。

## 完成项

### 改动 1 — verdict.py photoreal<60 → needs_review + anomaly
- `tools/jury/verdict.py:159` photoreal<60 升 needs_review + anomaly=photoreal_below_threshold
- 4 新 TDD（59/60/35/45 边界）

### 改动 1b BLOCKER — orchestrator retry 白名单扩
- `tools/jury_loop/orchestrator.py:199` +3 行 photoreal_below_threshold 走 retry
- abstract `_parse_verdict_with_anomaly_path()` helper（plan-drift: 原本 inline）
- 3 新 TDD

### 改动 1c MAJOR — photo3d_delivery_pack needs_review 兜底
- `tools/photo3d_delivery_pack.py:144` copy_preview 含 needs_review
- 4 新 TDD

### 改动 2 — max_retries 1→2
- `tools/jury_loop/config.py:48` production + `conftest.py:186` + `test_config.py` × 5 snapshot

### 改动 1e（rev 4 真 vendor 实测 fix）— verdict.py not all(checks) 升 needs_review
- `tools/jury/verdict.py:158` not all(checks) 加 anomaly=semantic_checks_failed + verdict=needs_review
- 3 新 TDD（含 photoreal<60 + checks=False 优先级 verify）
- 1 cascade adapt (test_jury_cli_single_view.py:139)

### 改动 1f（rev 4 cascade）— orchestrator retry 白名单加 semantic_checks_failed
- `tools/jury_loop/orchestrator.py:199` 同 改动 1b 模式扩 semantic_checks_failed
- 1 新 TDD

## 实测真值（GISBOT 真 vendor 两轮）

### 第 1 轮（pre-rev 4，commit `656fd8d`）— expose 改动 1 NO-OP

```
V1-V7: photoreal=20-45 全 verdict=preview / semantic_checks.photorealistic=False
top status: preview
```

**真值**：vision LLM 一致给 photorealistic=False（5 bool 之一），verdict.py elif `not all(checks)` 先吃 → verdict=preview。**改动 1 line 161 score<min 永远 unreachable** — 单元 TDD 用 fixture 全 True 绕过没发现。

### 第 2 轮（post-rev 4，commit `738b3f8`）— rev 4 fix 真 vendor 闭环

```
V1: photoreal=45 verdict=needs_review llm_meta.parse_anomalies=["semantic_checks_failed"]
V2: photoreal=35 verdict=needs_review llm_meta.parse_anomalies=["semantic_checks_failed"]
V3: photoreal=45 verdict=needs_review llm_meta.parse_anomalies=["semantic_checks_failed"]
V4: photoreal=45 verdict=needs_review llm_meta.parse_anomalies=["semantic_checks_failed"]
V5: photoreal=18 verdict=needs_review llm_meta.parse_anomalies=["semantic_checks_failed"]
V6: photoreal=30 verdict=needs_review llm_meta.parse_anomalies=["semantic_checks_failed"]
V7: photoreal=40 verdict=needs_review llm_meta.parse_anomalies=["semantic_checks_failed"]
top status: needs_review ✅
```

**关键验证**：
- 7/7 view verdict=needs_review ✅ (rev 4 fix work)
- 7/7 view anomaly=semantic_checks_failed ✅
- top status=needs_review（v2.37.7 baseline 是 preview）
- 与 v2.37.7 baseline 显著差 — decision path 已闭环
- AC-6（photoreal ≥60 status=accepted）未达 — 本 PR 仅跑 jury 评分不跑 retry round（path 字段 limit）；留 §11-N9 follow-up

### Cost 真值

| 轮次 | 视角数 | 单价 | 小计 |
| --- | --- | --- | --- |
| 1 (pre-rev 4) | 7 | $0.010 | $0.07 |
| 2 (post-rev 4) | 7 | $0.010 | $0.07 |
| **合计** | 14 | — | **$0.14** |
| 用户授权 budget | — | — | $0.50 (28% used) |

## 走过的弯路 / Plan-drift (sub agent 实施期发现)

1. **plan Task 1 plan-drift — semantic_checks keys 真值错** — plan 写 `consistent_lighting/consistent_shadows/...` 实际 _REQUIRED_BOOL_KEYS = `geometry_preserved/material_consistent/photorealistic/no_extra_parts/no_missing_parts`。implementer 修正 fixture。**教训**：plan 写 mock LLM payload 必须 grep 真实 schema constants。

2. **plan Task 2 plan-drift — `_parse_verdict_with_anomaly_path` 函数原不存在** — plan + spec rev 3 §3.1b.2 假设是既有 helper，实际 inline 在 `_call_jury_subprocess` 内。implementer 抽 pure refactor helper 后再加 retry path。**教训**：scout grep 阶段必须 verify 函数定义存在性，不只 grep call site。

3. **真 vendor 实测一击 expose 改动 1 NO-OP** — 4 层 spec review + 11 新 TDD 全 GREEN，但真 vendor 第一轮跑发现 verdict 全 preview，**改动 1 线 161 永远 unreachable**。spec rev 4 加 改动 1e+1f fix elif 顺序 + cascade retry path。**核心教训**：unit test fixture 不真实（用 semantic_checks 全 True 绕过 line 158 elif），真 vendor 实测一次抓到 spec 5 层 review 漏看的 elif 链顺序漏洞。

4. **Layer 6 scout 漏看完整 elif 链** — scout 仅 grep "score < min_photoreal_score" 看到 line 161，没看上游 line 158 `not all(checks)` 先吃。**教训**：grep 单行不够，必须读完整决策链（条件分支顺序）。

5. **`render_dir` path 字段 hardcode 源路径** — v2.37.8 rebrand 工具只改 subsystem 字段不改 path 字段；GISBOT 副本的 render_manifest.json.render_dir 仍指 cad-spec-gen 源目录；cad_pipeline enhance-check 路径校验 fail。本 PR 仅跑 photo3d_jury 单独入口避开 path 校验；**§11-N9 follow-up**：v2.37.8 rebrand 工具扩 path 字段处理。

6. **schema 字段位置 trap** — `parse_anomalies` 在 `view.llm_meta.parse_anomalies`（嵌套），不是 `view.parse_anomalies`（顶层）。spec rev 4 测试断言 ViewVerdict dataclass 对，但 report 序列化时进 llm_meta 子结构。下游消费者需通过 `llm_meta.parse_anomalies` 读。

## 5 层 + 1 真 vendor 实测 review 实证

| 层 | 抓 | spec rev |
| --- | --- | --- |
| Layer 6 scout | 5 处实证（双阈值合理设计 / preview-assert 测试影响）| rev 1 |
| self-review | 4 项过 | rev 1 inline |
| Layer 3 user review | 5 处漂移含 2 RISK-MAJOR | rev 1→rev 2 |
| 2nd boundary review | 1 BLOCKER + 1 MAJOR + 2 MINOR cascade | rev 2→rev 3 |
| **真 vendor 实测** | **1 BLOCKER NO-OP exposed** | **rev 3→rev 4** |

## §11 follow-up 更新

- 闭合：§11-N6（含 改动 1+1b+1c+1d+1e+1f+2）
- 仍 open：
  - §12 f4 N≥50 批量场景成本评估
  - **§11-N9 (rev 4 新登)** — v2.37.8 rebrand 工具扩 path 字段处理（render_dir / render_dir_abs_resolved）支撑跨副本 e2e
  - §11-N7 max_retries=3 升级（待 §11-N9 path 字段修后跑 retry round 实测）

## 后续工作

按 §6 YAGNI：
- v2.37.10 候选：§11-N9 rebrand path 字段 + 真 retry 闭环实测
- 全套件 ruff cleanup
