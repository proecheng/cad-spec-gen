# Retro — Tier 2 GISBOT 端到端 photo3d-jury e2e

**完工日期：** 2026-05-15
**Spec：** `docs/superpowers/specs/2026-05-15-gisbot-jury-e2e-design.md`（247 行 / brainstorming F1+F2 + layer 6 E7+E8+E10 fix）
**Plan：** `docs/superpowers/plans/2026-05-15-gisbot-jury-e2e.md`（669 行 / 4 task）
**Baseline：** cad-spec-gen main@`27b2c5c`（v2.37.5 merge）

> **spec 标题 vs 实际 subsystem mapping**：本 PR spec/plan/retro 标题"GISBOT jury e2e"实际跑 subsystem **"end_effector"**（GISBOT 是 end_effector v2.36 测试归档物理复制目录，内部 metadata 未 rebrand；spec §3.6 D6 决策接受此 mapping）。

## 一句话

跑通 `D:/Work/cad-tests/GISBOT/` 端到端 photo3d-jury 真金 7 视角 e2e；status=preview（7 视角 photoreal_score 35-45 全 < 60，但 semantic_checks + matches_spec 全 pass）；cost $0.07 / 7 LLM calls 全 HTTP 200。

## 完工范围

- `_setup_jury.py` 本地脚本（不进 git）镜像 GISBOT/ 文件 + 写 ARTIFACT_INDEX.json
- Task 2 跑 photo3d-jury 真金 e2e，产 PHOTO3D_JURY_REPORT.json
- spec/plan/retro 3 docs 进 cad-spec-gen git
- **0 production code 改 / 0 测试改 / 不发 patch tag**

## 数字（实测）

| 指标 | 值 |
|---|---|
| jury 子集 PASS（baseline 不变）| 503 → 503 |
| 全套件 PASS | 3193 → 3193 / 0 regression |
| PHOTO3D_JURY_REPORT status | **preview** |
| n_views / n_calls / n_retries | 7 / 7 / 0 |
| actual_cost_usd | **$0.07** (budget $0.20) |
| overall_matches_spec | **True** ✓ |
| matches_spec_status | pass |
| deterministic_gate | passed |
| 7 视角 photoreal_score | V1=40 V2=40 V3=35 V4=40 V5=35 V6=45 V7=45（均 35-45 < 60 阈值） |
| LLM call HTTP 200 | 7/7 first attempt |
| LLM latency 均值 | ~15s/view |
| parse_status | ok（全 7 视角）|

## 跑通的 evidence（本地路径）

- setup 脚本：`D:/Work/cad-tests/GISBOT/_setup_jury.py`
- 镜像布局：`D:/Work/cad-tests/GISBOT/cad/output/renders/` + `cad/end_effector/.cad-spec-gen/`
- jury 报告：`D:/Work/cad-tests/GISBOT/cad/end_effector/.cad-spec-gen/runs/20260513T115709Z/PHOTO3D_JURY_REPORT.json`（6209 bytes）
- 跑命令：`cd D:/Work/cad-tests/GISBOT && python -m tools.photo3d_jury --project-root . --subsystem end_effector --budget 0.20`

> evidence 在本仓主 maintainer 本机 `D:/Work/cad-tests/`；其他开发者本机路径相对应（layer 6 F1 教训）。

## 关键发现 — 实施期 3 项 plan-drift

### 1. spec D7 path mirror 布局与 jury 内部 hardcode 不匹配（中）

**spec 假设**：`cad/output/renders/` 平铺所有文件（V*.png + V*_enhanced.jpg + ENHANCEMENT_REPORT.json + render_manifest.json）。

**实测发现**：`tools/jury/input_evidence_binding.py:87` hardcode 期望 `cad/output/renders/<subsystem>/<active_run_id>/ENHANCEMENT_REPORT.json` 嵌套布局；Layer 0 不查 ARTIFACT_INDEX 的 `artifacts.enhancement_report` 路径字段。

**implementer hotfix workaround**：把 ENHANCEMENT_REPORT.json + render_manifest.json **额外** copy 到 `cad/output/renders/end_effector/20260513T115709Z/`（嵌套子目录）；图片文件保持平铺（report 内 enhanced_image 字段相对 project_root 解析）。

**lesson**：spec 写跨项目兼容性 setup 时不能只看 ENHANCEMENT_REPORT 内字段；必须 grep 实际 jury 代码看 hardcode path expectation。Task 0 scout 应加一步：`grep -n "cad/output/renders" tools/jury/`。

### 2. jury 真跑时 stderr 不发 per-view 进度（低）

**现象**：Task 2 Step 3 真金跑时 stderr 0 bytes；报告写完。

**评估**：cosmetic / logging 问题；不阻断验收。

**lesson**：jury CLI UX 改进点（spec §11 follow-up §11-N3 候选）；用户看不到进度容易以为挂了。

### 3. `ordinary_user_message` Windows GBK mojibake（低）

**现象**：jury report `ordinary_user_message` 字段含 `(��� stderr ������ʾ)` 乱码。

**root cause**：jury 内部某处把 stderr 内容（含中文）作为字符串写进 report；Windows 控制台默认 GBK 编码捕获中文时 → mojibake。

**评估**：cosmetic；不阻断；retro 引用真实数据时直接展示乱码字段说明问题。

**lesson**：cad-spec-gen 跨平台 stderr 捕获应显式 `errors="replace"` 或 `encoding="utf-8"`，Windows GBK 默认易产生 mojibake（spec §11 follow-up §11-N4 候选）。

## 审查矩阵

| Layer | findings | inline 修 | 接受 |
|---|---|---|---|
| brainstorming 数据/漂移 | 2 (F1+F2) | 2 | 0 |
| layer 6 边界 + 闭环 | 10 | 3（E7+E8+E10）| 7 |
| per-task implementer report | 3（spec D7 实际 layout + stderr 空 + mojibake）| 1 workaround | 2 sw-接受 retro 沉淀 |
| **总** | **15** | **6** | **9** |

## 沉淀 lessons

1. **spec cat 验证抓 metadata 漂移**（layer 6 E7+E8）：spec 写时凭印象假设；cat JSON 30 行救本 PR 免 BLOCKED。
2. **测试归档 metadata 不 rebrand 陷阱**：GISBOT/ 是 end_effector 物理复制目录但 metadata 未 rebrand；下游工具用 metadata 字段 fail；**新登 §11 follow-up §11-N1**：tools/dev/rebrand_test_archive.py
3. **path mirror 优于 path rewrite**（spec D7）：保 sha256/schema 不漂；但**实施期发现还需嵌套子目录** —— spec D7 应明示 jury hardcode `<subsystem>/<active_run_id>/` 子目录要求。
4. **cwd 显式声明**（layer 6 E10）：跨项目跑 photo3d-jury 时 `--project-root .` + `cd <target>` 双保险。
5. **Spec 写跨项目 setup 必 grep 实际代码 hardcode**（实施期发现 #1）：不能只读 ENHANCEMENT_REPORT/render_manifest schema；必须 grep 实际 jury 内部 path 解析逻辑（如 `tools/jury/input_evidence_binding.py`）确认 hardcode 期望。
6. **真金 e2e 实测 vendor cost 准度**：spec §3.4 D4 估 micuapi.ai $0.005/call × 7 = $0.035；实测 $0.07（2× 估算偏差，仍 budget 内）。**新登 §11 follow-up §11-N5**：cad-jury-config.md §4 估价表 micuapi.ai entry 校准至 ~$0.010/call。

## §11 follow-up（项目级，本 PR 新登）

| # | 严重度 | 内容 | 触发条件 |
|---|---|---|---|
| §11-N1 | LOW | 测试归档 rebrand 工具 `tools/dev/rebrand_test_archive.py` 自动 rewrite ENHANCEMENT_REPORT/render_manifest metadata | ≥ 2 个测试归档 e2e 跑过都遇 metadata 错位 |
| §11-N2 | LOW | photo3d-jury 接受 `--override-subsystem` flag | 用户多次需跨 subsystem 测试 |
| §11-N3 | LOW | photo3d-jury 真跑时 stderr 加 per-view 进度提示 | 多用户报"看不到进度以为挂了" |
| §11-N4 | LOW | 跨平台 stderr 捕获 utf-8/errors=replace（Windows GBK mojibake 防御）| 中文字符串污染报告 ≥ 1 次 |
| §11-N5 | LOW | cad-jury-config.md §4 估价表 micuapi.ai entry 校准至 ~$0.010/call（实测 7 view = $0.07 vs spec 估 $0.035 偏 2×）| 已实证 — 直接做 |

## 验收对照（spec §4）

| AC | 期望 | 实测 | 状态 |
|---|---|---|---|
| AC-1 setup 脚本 exit 0 | ✓ | ✓ | ✅ |
| AC-2 photo3d-jury exit ∈ {0,3,10,11,12} | ✓ | exit=0 | ✅ |
| AC-3 PHOTO3D_JURY_REPORT 7 视角 verdict + status | ✓ | ✓ status=preview / 7 views | ✅ |
| AC-4 feature_extractor / matches_spec OK | ✓ | ✓ overall_matches_spec=True | ✅ |
| AC-5 cost ≤ $0.20 | ✓ | $0.07 | ✅ |
| AC-6 retro doc 沉淀 lesson | ✓ | 本文 | ✅ |
| AC-7 3 docs 进 git，0 production | ✓ | spec/plan/retro 全 docs | ✅ |

**7/7 AC 全过 ✓**

## 下次类似 PR 优化

- spec 涉及 JSON schema 假设时 brainstorming 阶段 cat 实测必跑
- spec 写跨项目 setup 必 grep 实际代码 hardcode 路径解析逻辑（不只读 JSON schema）
- 真金 LLM cost 估算用项目惯例估价表的 2× upper bound 防偏差
- 测试归档 rebrand metadata 防 anti-pattern（§11-N1 待做）
- cwd + project-root 跨项目场景必显式声明

[[project-v2-37-5-done]] 上游 §12 f3 cleanup 追溯。
[[project-v2-37-4-done]] 上游 §12 f5+f6 + layer 6 E10 行号 snapshot lesson 追溯。
