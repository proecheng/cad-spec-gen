# 设计：Phase 6 交付报告可视化 — `delivery/README.md` 验收页（队列 D）

- **日期**：2026-05-12
- **基线**：main@f20e5fa（队列 C merge 后）
- **分支**：`feat/delivery-readme-acceptance-page`
- **规模**：小-中型 单 PR（重写 `tools/photo3d_delivery_pack.py::_write_readme` + 往 `report` dict 加一个 `view_evidence` 字段 + 测试；不动交付逻辑、不动 `cad_pipeline.py`、不加 CI mypy gate、不 bump `DELIVERY_PACKAGE.json` schema）
- **状态**：brainstorming 完成（含 3 轮自审 + grep 核实 8 个调查项，见 §7）；待用户复审 → writing-plans

---

## 1. 背景与目标

roadmap（`docs/PROGRESS.md` L192）："最终交付报告可视化 | Phase 6 | 交付包已有证据 JSON，普通用户还需要更直观的摘要和缩略图 | `delivery/README.md` 更像验收页：缩略图、质量摘要、复核状态、下一步动作"；L169 "让交付摘要更适合普通用户直接阅读，并补可视化验收截图/缩略图"。

**现状**：`photo3d-deliver` 已把 enhanced 图复制进 `delivery/enhanced/`、labeled 图进 `delivery/labeled/`、源渲染进 `delivery/source/`、证据报告进 `delivery/`，并生成 `delivery/DELIVERY_PACKAGE.json` + `delivery/README.md`。但 `README.md`（`tools/photo3d_delivery_pack.py::_write_readme`）只是个「JSON-ish 的 markdown 项目符号 dump」：`- subsystem: ... - run_id: ... - status: ...` + `## Reports`（一串报告路径）+ `## Deliverables`（只列**数量** `- enhanced_images: 5`，不展示图）+ `## Blocking Reasons`（如有）+ `## Model Quality`（只列 enum：`readiness_status`/`photoreal_risk`/`review_recommended_count`/`blocking_count`）。**关键浪费**：`model_quality_summary` 有一个 `ordinary_user_message`（中文人话句子）README 没用；`semantic_material_review`（`status`：accepted/not_run/blocked）/ `jury`（verdict + 成本，或 None）/ `quality_summary`（`status` / `view_count`）都有可读状态没 surface；`render_manifest.files[].visible_instance_ids`（队列 C 刚加的「每视角看到哪些件」）也没接进来。

**本 PR**：把 `_write_readme` 重写成**外行用户的验收页**——头条状态 + 内嵌 enhanced 图 + 人话质量摘要 + 复核状态表 + 下一步动作 + 每视角实例计数；底部保留「证据清单（供审计）」（报告路径 / 交付物计数 / 证据文件）。再往 `run_photo3d_delivery_pack` 的 `report` dict 加一个 `view_evidence` 字段（从已 load 的 `manifest` 提取 per-view `visible_instance_ids` + `evidence_method`），让队列 C 的数据既进 README 也进 `DELIVERY_PACKAGE.json`。

**核心约束**：零行为变更（除「README 内容更丰富」+ `DELIVERY_PACKAGE.json` 多一个可选 additive `view_evidence` 字段）；不动交付逻辑（`_copy_view_images` / 证据链 / hash 绑定 / `_reset_managed_delivery_dirs` / blocking 判定 / `model_quality_summary` 的内容）；不动 `cad_pipeline.py::cmd_photo3d_deliver`（薄包装）。北极星：傻瓜式 ✓（外行打开 `delivery/README.md` 就能看懂结果 + 下一步）/ 稳定可靠 ✓（不动交付/证据逻辑）/ 结果准确 ✓（README 只反映已有证据）/ 零配置 ✓ / SW 装即用 ✓；Windows-only ✓（纯字符串拼接 + markdown）。

## 2. 提议的 `delivery/README.md` 结构

```markdown
# 交付包验收 — <subsystem> / <run_id>

**状态**：<_status_badge(report["status"])：delivered → ✓ 已交付 / preview_package → ⚠ 预览包 / not_deliverable → ✗ 未交付>  ·  增强：<_status_badge(report["enhancement_status"])：accepted → ✓ 已验收 / preview → ⚠ 预览 / 其它 → 见 _status_badge 映射>  ·  最终交付物：<report["final_deliverable"] ? "是" : "否">
> <report["ordinary_user_message"]>          ← 通用状态句（= _ordinary_user_message(status)，delivered/preview_package/not_deliverable 各一句中文）

## 渲染图（增强后）                            ← 整段仅当 deliverables["enhanced_images"] 非空（blocked/无图 run 省略）
### V1
![V1 增强图](<rel>)                            ← <rel> = _pkg_path_relative_to_delivery(item["package_path"], report["delivery_dir"]) = `Path(package_path).relative_to(Path(delivery_dir)).as_posix()`（两者都 project-relative），final 模式 → "enhanced/V1_..._enhanced.jpg"，preview 模式 → "preview/V1_..._enhanced.jpg"（path 由 package_path 派生、**不硬编码** "enhanced/"；headline 已说明是 final 还是 preview；relative_to 抛 ValueError 时退化为 package_path 的 basename）
- 本图标着含 <N> 个零件                        ← N = len(view_evidence["per_view"]["V1"])；无 view_evidence 则省略此行
- [带标注版](<labeled rel>)                     ← 若 deliverables["labeled_images"] 里有同 view（rel = relative_to(delivery_dir) → "labeled/..."）
### V2
...
（按 deliverables["enhanced_images"] 顺序，每个 item 一段；视角名 item["view"]）

## 完整性证据                                  ← 整段仅当 view_evidence 不为 None
- 证据方式：<view_evidence["evidence_method"]>（如 instance_bbox_presence）
- 各视角实例计数：V1=12, V2=12, V3=12, ...   ← len(view_evidence["per_view"][view])
- 详细逐视角实例清单见 `DELIVERY_PACKAGE.json` 的 `view_evidence` 字段 / `render_manifest.json`；完整性 PASS/BLOCKED 判定见 `RENDER_VISUAL_REGRESSION.json`（若已跑过 `photo3d-render-check`）
（**不读** `RENDER_VISUAL_REGRESSION.json` 本身——它不在 `source_reports`（`ACTIVE_RUN_ARTIFACTS` 只有 product_graph/model_contract/assembly_signature，已确认），`_write_readme` 只拿到 `report` 没拿到 `run_dir`；要读它得再加 report 字段、超 scope。契约层 block 已由 `render_visual_regression.py` 完成，README 不必复述。"必需零件覆盖 N/M（需 product_graph）" 同理留作未来增强——见 §6 范围外）

## 模型质量
> <model_quality_summary["ordinary_user_message"]>     ← 人话句子，重点
- 就绪状态：<readiness_status>  ·  照片级风险：<photoreal_risk>
- 建议复核 <review_recommended_count> 个零件  ·  阻断 <blocking_count> 个
（来源：`MODEL_CONTRACT.json`，与本 run 绑定）
（整段仅当 model_quality_summary 不为 None）

## 复核状态
| 项 | 状态 |
|---|---|
| 增强图质量（quality_summary）| <quality_summary["status"]：✓ accepted / ⚠ <status>（如 unknown）> |
| AI 增强（enhancement）| <enhancement_status：✓ accepted / ⚠ preview / ✗ <其它>> |
| 语义/材质复核（semantic_material_review）| <按 `["status"]` + `["required"]`（report 里 `required = bool(require_semantic_review)` CLI flag，可 True）：✓ accepted / not_run 时：required=True → ⚠ 必需但未做（处理后重交付）/ required=False → ⚠ 未做（非强制）/ 其它 status → ✗ <status>（含 review_report 路径 `<review_report>` 若有）> |
| AI 视觉评分（jury）| <jury 为 None → ⚠ 未运行；否则按 jury["status"]（= PHOTO3D_JURY_REPORT.json 的 status，即 verdict accepted/needs_review/blocked，已确认 `_build_jury_section` 返 `"status": rep.get("status")`）：✓ accepted（成本 $<jury["actual_cost_usd"]>）/ ⚠ needs_review / ✗ blocked> |

## 下一步
<决策树：
 - report["blocking_reasons"] 非空：✗ 当前有阻断项（见下方「阻断项」），处理后重新 `photo3d-deliver`。
 - 否则若 model_quality_summary 不为 None 且 model_quality_summary["recommended_next_action"]["kind"] ∈ {import_missing_models, review_models}：⚠ 建议先 <中文动作>（import_missing_models→「先导入缺失的 3D 模型」/ review_models→「先复核标黄的零件」）再交付。
 - 否则若 report["status"] == "delivered"：✓ 交付完成，无需进一步动作。
 - 否则（preview_package / not_deliverable 且无 blocking_reasons——少见）：⚠ 见上方各项状态。>
（`recommended_next_action` 结构 = `{"kind": ...}`，kind ∈ {`import_missing_models`（readiness=blocked/not_available）, `review_models`（needs_review）, `continue_photo3d`（ready）, `none`（unknown/兜底）}，已确认；后两个算「无需先做动作」。`report` 没有 `next_action` 字段——不用它。）

## 阻断项                                       ← 仅当 report["blocking_reasons"] 非空
- <code>: <message>
- ...

---
## 证据清单（供审计）
**报告**
- artifact_index: `<path>`
- render_manifest: `<path>`
- enhancement_report: `<path>`
- ...（source_reports 每项）

**交付物**
- 源渲染：<len(source_images)> 张
- 增强图：<len(enhanced_images)> 张
- 标注图：<len(labeled_images)> 张

**证据文件**
- `<package_path>`
- ...（evidence_files 每项）

*本文件由 `photo3d-deliver` 自动生成于交付包目录（`<delivery_dir>`）。`DELIVERY_PACKAGE.json` 是机器可读的完整证据清单。*
```

要点：
- 「图标+中文」用一个小映射 helper（`_status_badge(status: str) -> str`）：正向集 `{delivered, accepted, ready, continue_photo3d}` → `"✓ <中文>"`；告警集 `{preview, preview_package, needs_review, unknown, not_run}` → `"⚠ <中文>"`；阻断集 `{not_deliverable, blocked, not_available}` → `"✗ <中文>"`；其它未知值 → `"· <原值>"`（中性，不误判成 ✗）。状态值都用现有的，不新造。
- 内嵌图用相对路径（细节见 §7.6，已确认）：enhanced 图被 `_copy_view_images` 复制进 `delivery/enhanced/`（`final` 时）或 `delivery/preview/`（preview 时），`image_item["package_path"]` 是 project-relative；README 在 `delivery/README.md`，路径转「相对 delivery_dir」= `_pkg_path_relative_to_delivery(package_path, report["delivery_dir"])`（如 `cad/.../runs/RUN001/delivery/enhanced/V1_enhanced.jpg` → `enhanced/V1_enhanced.jpg`）。labeled 同理（`delivery/labeled/`），source 不内嵌（只计数）。
- 所有「整段仅当 X 不为 None/非空」的条件分支：X 缺时整段省略（不写空标题）——graceful degradation，老 run / 缺数据时 README 仍是合法 markdown。

## 3. 文件结构

- **改** `tools/photo3d_delivery_pack.py`：
  - `_write_readme(path: Path, report: dict[str, Any]) -> None` 重写成 §2 的结构。拆几个内部 helper（纯函数、返回 `list[str]` 行：`_readme_headline(report)` / `_readme_images_section(report)` / `_readme_view_evidence(report)` / `_readme_model_quality(report)` / `_readme_review_status(report)` / `_readme_next_step(report)` / `_readme_blocking(report)` / `_readme_evidence_appendix(report)`；+ `_status_badge(status)` 小映射 + `_pkg_path_relative_to_delivery(package_path, delivery_dir)`）。代码合理标注类型（`tools/photo3d_delivery_pack.py` **不在** CI mypy-strict gate，本 PR **不加它进去**——800 行非 strict-clean，超 scope；但新 helper 写干净）。
  - `run_photo3d_delivery_pack`：在 `report = { ... }` 里加一个 `"view_evidence": view_evidence` 字段（紧跟 `model_quality_summary` 之后或在 `deliverables` 附近，位置不重要）。`view_evidence` 由一个 helper 从已 load 的 `manifest`（render_manifest.json，函数里已有局部变量）算：
    ```python
    def _view_evidence_summary(manifest: dict[str, Any]) -> dict[str, Any] | None:
        method = manifest.get("evidence_method")
        per_view = {
            str(f.get("view")): list(f.get("visible_instance_ids"))
            for f in (manifest.get("files") or [])
            if isinstance(f, dict) and f.get("view") and isinstance(f.get("visible_instance_ids"), list)
        }
        if not method and not per_view:
            return None
        return {"evidence_method": method, "per_view": per_view}
    ```
- **改** `tests/test_photo3d_delivery_pack.py`：① 更新 `test_photo3d_delivery_pack_includes_active_run_model_quality_summary` 的 README 断言（现在断 `"model_quality_summary" in readme` + `"needs_review" in readme`——新结构里这些字面字符串位置变/可能没了；改成断「模型质量」段存在 + `model_quality_summary["ordinary_user_message"]` 的文案在 readme 里 + `"needs_review"` 仍在（`readiness_status` 是 needs_review 时会出现在 readme 里））；② 加新断言：README 含每个 enhanced 视角的 `![...](enhanced/<filename>)`、含「复核状态」段（断 `"semantic_material_review"` 或「语义/材质复核」+ 对应状态）、含「下一步」段、含 view_evidence 段（`render_manifest` 带 `visible_instance_ids` 时——fixture 的 `_contracts` 产的 manifest 现在带这个，因为它的 assembly_signature 有 instances，是队列 C 改的）；③ 加 `DELIVERY_PACKAGE.json` 的 `view_evidence` 字段断言（带证据时 `package["view_evidence"]["evidence_method"]` + `per_view`；不带时为 None——构造一个不带 `visible_instance_ids` 的 manifest 测向后兼容）。
- **不改** `tools/photo3d_delivery_pack.py` 的交付逻辑（`run_photo3d_delivery_pack` 主流程 / `_copy_view_images` / `_model_quality_summary_from_source_reports` / `_build_jury_section` / `_semantic_material_review_summary` / 证据链 / hash 绑定 / `_reset_managed_delivery_dirs` / blocking 判定）—— 只动 `_write_readme` + 加 `view_evidence` 字段。
- **不改** `cad_pipeline.py::cmd_photo3d_deliver`、`tools/render_visual_regression.py`、`tools/model_audit.py`、`render_manifest` schema、`DELIVERY_PACKAGE.json` schema_version（仍 1，`view_evidence` 是可选 additive）。
- canonical/mirror：`tools/photo3d_delivery_pack.py` 在 tools/，`src/cad_spec_gen/data/tools/photo3d_delivery_pack.py` 是 **gitignored** 镜像——改完跑 `python scripts/dev_sync.py` + `--check` + `git diff --exit-code -- AGENTS.md`。

## 4. 测试（TDD）

- 现有 `tests/test_photo3d_delivery_pack.py` 有 fixture `_contracts`（from `test_photo3d_gate_contract.py`）+ `_write_photo3d_run` + `_write_enhancement_report(with_views=True)`（造带视角的 ENHANCEMENT_REPORT）—— 复用。`_contracts` 产的 `render_manifest` 现在带 `visible_instance_ids`（队列 C 改的，因为它的 `assembly_signature` 有 instances）。
- 先改 `test_photo3d_delivery_pack_includes_active_run_model_quality_summary` 的 README 断言（断新结构的字符串）→ 跑 → fail（旧 `_write_readme` 不产新结构）→ 重写 `_write_readme` → 跑 → pass。
- 加：① README 每 enhanced 视角含 `![](enhanced/...)`（或 `preview/...` 若 preview 模式——测 final 模式即可）；② README 含「复核状态」段 + `semantic_material_review` 的状态字符串；③ README 含「下一步」段；④ `render_manifest` 带 `visible_instance_ids` → README 含「本图标着含 N 个零件」+ `DELIVERY_PACKAGE.json` 有 `view_evidence`（`evidence_method` + `per_view` 字典）；⑤ 构造不带 `visible_instance_ids` 的 manifest → README 完整性证据段省略 + `view_evidence` 为 None（向后兼容）；⑥ 现有 `test_photo3d_delivery_pack_packages_accepted_run_evidence`（断 README 文件存在）+ blocked-path 测试（断 `final_deliverable is False` + blocking_reasons）仍过。
- 全套件不回归（`test_photo3d_delivery_pack.py` + `test_photo3d_gate_contract.py` 在 `tests/conftest.py` 的 `PHOTO3D_CONTRACT_TEST_FILES`；`DELIVERY_PACKAGE.json` 加 `view_evidence` 是 additive——plan 确认没别处硬断言它的字段集；`render_visual_regression.py` / `photo3d_gate.py` 不读 `DELIVERY_PACKAGE.json` 的字段集）。

## 5. 验证清单
1. `python -m pytest tests/test_photo3d_delivery_pack.py tests/test_photo3d_gate_contract.py -q` → 全 PASS（+新测试）。
2. `python -m pytest tests/ -q` → ≥ 3096 PASS / 0 regression。
3. `python -m ruff check tools/photo3d_delivery_pack.py tests/test_photo3d_delivery_pack.py` → `All checks passed!`（不跑 mypy on photo3d_delivery_pack——不在 gate；但若顺手发现新 helper 有明显类型错可修）。
4. `python scripts/dev_sync.py && python scripts/dev_sync.py --check && git diff --exit-code -- AGENTS.md` → 通过。
5. 北极星 5 gate + Windows-only：全过（见 §1）。
6. （手动可选）造一个真 active-run 的 delivery 包、打开 `delivery/README.md` 在 markdown viewer 里看一眼图是否内嵌、各段是否可读——PR 描述里附一张截图或贴 README 文本片段。

## 6. 范围外
- 生成单独的缩略图文件（PIL resize）—— 用户选了「内嵌 enhanced 图（markdown ![](path)）」，不做。
- HTML 报告 —— 只做 markdown README。
- 「必需零件覆盖 N/M + 缺哪些必需零件」/「完整性 PASS/BLOCKED」—— 需 load `product_graph`（`photo3d_delivery_pack` 当前没 load，只有 `render_manifest`）或读 `RENDER_VISUAL_REGRESSION.json`（已确认**不在** `source_reports`/`ACTIVE_RUN_ARTIFACTS`，且 `_write_readme` 只拿到 `report` 没 `run_dir`，要读得再加 report 字段——超 scope）；MVP 只显示 per-view 计数 + `evidence_method` + 指向 `RENDER_VISUAL_REGRESSION.json` 的一行说明，N/M 与完整性 verdict 留未来增强（契约层 block 已由 `render_visual_regression.py` 完成，README 复述非必需）。
- `model_quality_summary` / `semantic_material_review` / `jury` 本身的内容/逻辑改动 —— 只 surface 已有数据。
- 把 `tools/photo3d_delivery_pack.py` 加进 CI mypy-strict gate —— 800 行非 strict-clean，超本 PR scope。
- bump `DELIVERY_PACKAGE.json` schema_version —— 不做（`view_evidence` 可选 additive）。
- 改 `cad_pipeline.py::cmd_photo3d_deliver` —— 薄包装，不动。
- B3/B4（§11 命名统一 / fast-path 扩展）/ E（真实 AI adapter）—— 不在本 PR。

## 7. Plan 第 0 task 调查项（✓ = 本 brainstorm 已 grep+实跑核实；剩下的 plan Task 0 复核）

1. ✓ **`_write_readme(path, report)` 现状** = 项目符号 dump（`subsystem`/`run_id`/`status`/`final_deliverable`/`enhancement_status` + `## Reports` source_reports 路径 + `## Deliverables` 计数 + `## Blocking Reasons`（若有）+ `## Model Quality` enum：`readiness_status`/`photoreal_risk`/`review_recommended_count`/`blocking_count`）。✓ **`report` dict 字段**（`tools/photo3d_delivery_pack.py:180-203` 实读）：`schema_version:1` / `generated_at` / `run_id` / `subsystem` / `status` / `final_deliverable` / `ordinary_user_message`（= `_ordinary_user_message(status)` 通用句）/ `enhancement_status` / `quality_summary` / `model_quality_summary` / `semantic_material_review` / `jury` / `delivery_dir`（= `project_relative(delivery_dir, root)`，**project-relative**）/ `source_reports`（dict）/ `deliverables` / `evidence_files` / `warnings` / `blocking_reasons` / `artifacts`（`delivery_package`/`delivery_readme`）。**无 `next_action`、无 `run_dir`**——「下一步」用 `model_quality_summary["recommended_next_action"]` + status/blocking 推；要读 `RENDER_VISUAL_REGRESSION.json` 得加 report 字段（超 scope，§6）。
2. ✓ **`_build_jury_section`**（`:362-369`）返 `{"report":<rel>, "review_input":<rel|None>, "status": rep.get("status"), "actual_cost_usd": jury_meta.get("actual_cost_usd"), "vendor_request_ids":[...], "jury_report_schema_version":...}` 或 `None`（PHOTO3D_JURY_REPORT.json 不存在/解析失败）。**`jury["status"]` 就是 verdict**（PHOTO3D_JURY_REPORT.json 的 `status` ∈ accepted/needs_review/blocked）——README 直接用，不用再读 jury 报告。
3. ✓ **`model_quality_summary`**（`tools/model_audit.py::build_model_quality_summary`）：`schema_version:1` / `source` / `source_report` / `binding_status` / `readiness_status`（∈ {ready, needs_review, blocked, not_available}）/ `photoreal_risk` / `ordinary_user_message`（中文人话句）/ `recommended_next_action`（= `{"kind": ...}`，kind ∈ {`import_missing_models`（blocked/not_available）, `review_models`（needs_review）, `continue_photo3d`（ready）, `none`（兜底）}）/ `review_recommended_count` / `blocking_count`。`model_quality_summary` 可能为 `None`（源报告缺/绑定失败时 `_model_quality_summary_from_source_reports` 返 None）→ 整段省略。
4. ✓ **状态 enum 汇总**（README 各 badge 用）：`report["status"]` ∈ {delivered, preview_package, not_deliverable}（`_package_status`）；`enhancement_status` = `ENHANCEMENT_REPORT.delivery_status or status`（典型 accepted/preview/...）；`quality_summary["status"]` ∈ {accepted, unknown, ...}（来自 ENHANCEMENT_REPORT.quality_summary.status，缺则 accepted/unknown 兜底）；`semantic_material_review["status"]` ∈ {not_run, accepted, blocked, ...}，`["required"]` 在 report 里 = `bool(require_semantic_review)`（`--require-semantic-review` CLI flag，**可为 True**——`_semantic_material_review_summary` helper 初值 False，`run_photo3d_delivery_pack:139` 覆盖）；`jury["status"]` ∈ {accepted, needs_review, blocked}（或 None=未跑）。
5. ✓ **`ACTIVE_RUN_ARTIFACTS`**（`:14-18`）= `{product_graph: PRODUCT_GRAPH.json, model_contract: MODEL_CONTRACT.json, assembly_signature: ASSEMBLY_SIGNATURE.json}`——**`render_visual_regression` 不在里面**，即 `RENDER_VISUAL_REGRESSION.json` 不进 `source_reports`。MVP「完整性证据」段只 per-view 计数 + `evidence_method` + 指向 `RENDER_VISUAL_REGRESSION.json`/`render_manifest.json` 的一行（不读其内容）。
6. ✓ **图路径**：`_copy_view_images`（`:507-516`）把 source→`delivery/source/`、enhanced→`delivery/enhanced/`（`final=True`）或 `delivery/preview/`（preview）、labeled→`delivery/labeled/`；`_image_item`（`:567-572`）的 `package_path` = `project_relative(copied, root)`，**project-relative**（如 `cad/.../runs/RUN001/delivery/enhanced/V1_enhanced.jpg`）。README 在 `delivery/README.md`，相对路径 = `Path(item["package_path"]).relative_to(Path(report["delivery_dir"])).as_posix()` → `enhanced/V1_enhanced.jpg`（两者都 project-relative，`relative_to` 安全）。helper `_pkg_path_relative_to_delivery(package_path: str, delivery_dir: str) -> str` 封装；万一 `relative_to` ValueError（路径异常）→ 退化用 `Path(package_path).name`（不内嵌也不崩）。`source_images` 也复制了（`delivery/source/`）但 README 不内嵌（只计数）。
7. **（待 plan Task 0 复核）** `grep -rn "DELIVERY_PACKAGE\|delivery_package" tests/` —— 确认没别处硬断言 `DELIVERY_PACKAGE.json` 的字段集（加 `view_evidence` additive 不会炸现有断言）。`tests/conftest.py` 的 `PHOTO3D_CONTRACT_TEST_FILES` 含 `test_photo3d_delivery_pack.py` + `test_photo3d_gate_contract.py`——改这两个文件的测试时确认 conftest 钩子不会漏跑。
8. ✓ **CI / 镜像**：`photo3d_delivery_pack.py` **不在** CI `mypy-strict` 那行（`tools/enhance_consistency.py tools/render_qa.py tools/path_policy.py tools/view_instance_evidence.py`）——本 PR 不加（800 行非 strict-clean）。本 PR 不动 `pyproject.toml` / `.github/workflows/`。`src/cad_spec_gen/data/tools/photo3d_delivery_pack.py` 是 gitignored 镜像（`.gitignore:29`）——改 canonical（`tools/`）+ 跑 `python scripts/dev_sync.py` + `--check` + `git diff --exit-code -- AGENTS.md`。
