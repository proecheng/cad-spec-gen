# Jury `matches_spec` 维度 — Design Spec

**Date:** 2026-05-13
**Status:** v1 / approved by user (user delegated all technical decisions via brainstorming session)
**Plan doc:** _TBD — writing-plans skill 下一步生成_
**Status doc:** _本 spec 闭合后由 plan 阶段建立 v2_

---

## 1 · Goal

让 photo3d-jury 不只评"AI 修图前后忠实度"，而是**评图与设计文档的语义一致性**。具体：给 jury 加一个新维度 `matches_spec`（第 6 个 boolean），让 vision LLM 看完渲染图后能回答"设计文档里说该有的关键特征（如法兰 4 条悬臂、PEEK 绝缘环）**实际在图里看见了没**"。

## 2 · Context — 这次为啥要做

### 2.1 现状

photo3d-jury (`tools/photo3d_jury.py` + `tools/jury/verdict.py`) 现 5 个 boolean 维度：

```python
_REQUIRED_BOOL_KEYS = (
    "geometry_preserved",     # ① 几何与设计一致 ← 但实际只比 AI 前后 PNG
    "material_consistent",    # ② 材质一致
    "photorealistic",         # ③ 照片真实感
    "no_extra_parts",         # ④ 无凭空多出的件
    "no_missing_parts",       # ⑤ 无丢失的件
)
```

第 ① 个 `geometry_preserved` **名字像是 matches_spec，但实际语义是"AI 没破坏源 PNG"** —— 源 PNG 本身是否符合设计文档，jury 不看（vision LLM 根本拿不到设计文档原文）。

### 2.2 这次质量大修 v1 暴露的两个 bug 都不会被现 jury 抓住

来自 `docs/superpowers/specs/2026-05-13-quality-overhaul-design.md` §2.2：

- bug A：法兰只有圆盘没 4 臂 → 渲染图忠实反映 GLB → `geometry_preserved=true` ✅（"AI 没改"）但实际图不符设计文档 ❌
- bug B：装配全堆原点 → 同样 ✅ ❌

CP-2 的 `custom_parts_audit.py` 已经在**几何层**抓住这两个 bug（envelope vs bbox / placement collapse）。`matches_spec` 维度是**视觉语义层**的兜底（部分场景几何对但视觉特征不对，如相机角度遮挡 / 材质染色让悬臂消失）。

### 2.3 北极星对齐（memory `project_north_star`）

- **零配置** ✓ — 全自动 LLM 抽特征，用户不需手写 features.yaml
- **结果准确** ✓ — 给 vision LLM 喂设计文档让它能判语义
- **傻瓜式** ✓ — FAIL 时输出中文 TODO 文件指引下一步动作，不要求用户读 JSON

## 3 · Decisions（用户授权 LLM 替他做的技术决策）

| # | 决策 | 理由 |
| --- | --- | --- |
| D1 | **特征列表来源：每个 photo3d-jury 进程 LLM 抽 1 次 + 落盘 cache + 同进程 retry 复用；下个 jury 进程重抽（F3）** | 用户选项 B "全自动 0 维护"；落盘是给同进程 retry 路径用，不跨进程复用避免特征 vs 几何 drift |
| D2 | **加 jury 第 6 维度 `matches_spec`，不替换现有 5 维度** | spec §2.2 字面匹配 + 最小 surprise；backward compat |
| D3 | **走现有 SP1 jury→prompt retry 闭环** | v2.32-v2.34 已铺好的路；matches_spec FAIL → 视角 verdict=needs_review → retry；不引入新基建 |
| D4 | **重试 N=3 次仍 FAIL → `MATCHES_SPEC_TODO.md` 写人话清单 + deliver 标 blocked** | 半闭环（spec D5 风格 v1 半闭环对齐）；用户能看见且知道下一步 |
| D5 | **特征抽取 LLM 失败 → `matches_spec=true` 静默跳过，pipeline 不阻断** | 不让外部依赖故障拖垮交付（spec D3 同款思路） |
| D6 | **temperature=0 + 固定 prompt 模板 + features ≤12 条** | 控 cost + 减 LLM variance |
| D7 | **复用现有 LLM client（与 photo3d_jury 同 backend）；feature_extractor 优先 text-only endpoint，无则 vision endpoint fallback（F8）** | 不增加用户配置面 + 控 token cost（文本任务用 text endpoint 便宜很多） |

## 4 · Scope

### In Scope (v2.37.0)

- 改 `tools/photo3d_jury.py`：启动时调 1 次特征抽取 LLM → cache → 每视角 vision call prompt 附加 features 列表
- 改 `tools/jury/verdict.py`：`_REQUIRED_BOOL_KEYS` 加 `matches_spec` + 新增 `features_status: list` 字段透传 + parse 兼容老 fixture（无 `features_status` 时 `matches_spec=true` 跳过）
- 改 jury_loop hook：matches_spec FAIL → verdict=needs_review 触发 retry；prompt rewriter 接 hint 接口接受 missing feature 名列表
- 失败兜底：N=3 次 fail → 写 `cad/<sub>/.cad-spec-gen/MATCHES_SPEC_TODO.md`（中文人话）+ `DELIVERY_PACKAGE.json` status=blocked
- 整合到现有 `enhance-check.quality_summary`：加 sub-field `matches_spec_status: pass|warn|fail|blocked`
- 整合到 `cad-tests/<sub>/_README.md` (CP-3 生成的)：加「特征对账」section 引用 TODO 文件或显示 PASS
- 测试 L1-L4 mock layer（CI 跑）+ L5 e2e smoke `requires_jury_loop_e2e` marker（CI skip）
- spec / plan / STATUS / retro 跨会话文档全套

### Out of Scope (v2.38+ 或 v3)

- prompt rewriter 智能化（先用最朴素"拼接 missing features 名"）
- features 手编辑接口（features.yaml + UI / CLI 编辑器）— 完全自动
- 第 2 个 reviewer 整合（`enhancement_semantic_review.py` 不动 matches_spec）
- retry 次数动态自适应（用 SP1 hardcoded N=3）
- features 抽取的 LLM model 选择面（用 jury 已配 backend）
- features 多语言支持（仅中文 description）

## 5 · Architecture

### 5.1 数据流

```
photo3d-jury 进程启动
    │
    ├─ NEW · feature_extractor.extract(spec_md_path, design_doc_md_path) → features.json
    │       cache 路径: cad/<sub>/.cad-spec-gen/matches_spec_features.json
    │       per-process 抽 1 次（F3）；同进程 retry 复用；下进程重抽
    │       LLM 失败 → return {features: []}（pipeline 继续，matches_spec 跳过）
    │
    ├─ vision LLM call per-view（已有，扩 prompt + 输出 schema）
    │       prompt 添加：相关 features 列表（按 expected_in_views 过滤）
    │       输出 JSON 加 features_status: [{feature_id, visible, reason ≤80字}]
    │
    ├─ jury/verdict.parse_view_verdict（扩字段，view-scope）
    │       semantic_checks["matches_spec"] = all(f.visible for f in features_status)
    │       透传 features_status 给下游 reporter
    │
    ├─ NEW · jury/verdict.aggregate_run_verdict(view_verdicts) (F1)
    │       overall_matches_spec = all(v.semantic_checks["matches_spec"] for v in view_verdicts)
    │       per_view_failed_features: dict[view_id, list[feature_id]] (供 prompt rewriter 反馈)
    │
    └─ jury_loop hook（已有，扩 hint 接口）
           per-view retry granularity（F5：实施前 grep tools/jury_loop/ 验证假设）
           view.matches_spec=false → 该 view verdict=needs_review → retry 该 view
           prompt_rewriter.hint(view_id, missing_features=[id1, id2]) → 注入到该 view 的 enhance prompt
```

### 5.2 数据契约

#### 5.2.1 `matches_spec_features.json`

```json
{
  "schema_version": 1,
  "subsystem": "end_effector",
  "run_id": "20260513T200000Z",
  "source_files": [
    "cad/end_effector/CAD_SPEC.md",
    "examples/04-末端执行机构设计.md"
  ],
  "features": [
    {
      "feature_id": "flange_arms_4",
      "description_cn": "法兰应含 4 条径向悬臂，沿 0°/90°/180°/270° 分布",
      "expected_in_views": ["V4", "V5"],
      "doc_ref": "examples/04-末端执行机构设计.md §3 ARM_L_2"
    },
    {
      "feature_id": "peek_insulation_ring",
      "description_cn": "法兰底面应有 PEEK 绝缘环（金色）",
      "expected_in_views": null,
      "doc_ref": "CAD_SPEC.md §6.2 L4 Z=-27mm"
    }
  ]
}
```

- `expected_in_views: null` = 所有视角应可见
- `expected_in_views: ["V4"]` = 仅特定视角应可见
- features 数组上限 12 条；超出截断 + parse_anomalies 加 `feature_extraction_truncated`

#### 5.2.2 jury verdict 扩字段（含 F1 jury-level aggregate + F7 default）

**View-scope（扩老 ViewVerdict）**：

```python
@dataclass(frozen=True)
class ViewVerdict:
    semantic_checks: dict[str, bool]                                  # 6 keys (含新 matches_spec)
    photoreal_score: int
    reason: str
    parse_status: Literal["ok"]
    parse_anomalies: list[str] = field(default_factory=list)
    verdict: Literal["accepted", "preview", "needs_review"] = "accepted"
    features_status: list[dict] = field(default_factory=list)         # NEW (F7: explicit default)
                                                                       #   [{feature_id, visible, reason}]
```

**Run-scope（F1 NEW）**：

```python
@dataclass(frozen=True)
class RunVerdict:
    """整 photo3d-jury 进程的 jury-level summary。"""
    view_verdicts: dict[str, ViewVerdict]                              # view_id → ViewVerdict
    overall_matches_spec: bool                                          # all(view matches_spec)
    per_view_failed_features: dict[str, list[str]] = field(default_factory=dict)
                                                                       # {view_id: [feature_id, ...]}
                                                                       # 给 prompt_rewriter 用
```

**向后兼容**：`features_status` 默认空列表；老 jury 输出（无 features_status）→ ViewVerdict 中 `semantic_checks["matches_spec"] = True` 跳过；RunVerdict 中 `overall_matches_spec = True`（无特征数据视为通过）。

#### 5.2.3 `MATCHES_SPEC_TODO.md` 模板

```markdown
# 自制件特征对账 — 未达标
日期：YYYY-MM-DD · 子系统：{sub} · 重试 N/N 次仍 FAIL

## 应有但未见的特征

- [ ] **{feature_id}** — {description_cn}（设计文档：{doc_ref}）
  - {view}：{reason}
  ...

## 建议下一步
1. 重 build：检查相关 `cad/{sub}/*.py` 是否真画了该特征
2. 跑 `python cad_pipeline.py custom-parts-audit --subsystem {sub}` 看几何审计
3. 若 audit PASS 但 jury 仍 FAIL → 调相机角度 `render_config.json`
```

### 5.3 接入点 / 文件改动

| 文件 | 改动 |
| --- | --- |
| `tools/photo3d_jury.py` | 进程启动时调 feature_extractor；vision prompt 附 features；输出含 features_status + 顶层 overall_matches_spec；写 `cad/output/renders/jury_report.json` 含完整 RunVerdict（F2 wire） |
| `tools/jury/verdict.py` | `_REQUIRED_BOOL_KEYS` += `matches_spec`；ViewVerdict 加 features_status field（F7 default）；新增 RunVerdict + aggregate_run_verdict()（F1）；parse 兼容老 fixture |
| `tools/jury/feature_extractor.py` (新) | extract(spec_md, design_doc_md) → cache or fresh LLM call；text-only endpoint 优先 vision fallback（F8） |
| `tools/jury/prompt_rewriter.py` (扩) | hint(view_id, missing_features) 接口；per-view scope（F5） |
| `tools/photo3d_delivery_pack.py` | 检 RunVerdict.overall_matches_spec；FAIL 3 次后写 MATCHES_SPEC_TODO.md / 标 `DELIVERY_PACKAGE.json status=blocked` |
| `cad_pipeline.py::cmd_enhance_check` | 读 `cad/output/renders/jury_report.json` 的 `matches_spec_status` 字段，透传到 `quality_summary.matches_spec_status` sub-field（F2 wire） |
| `cad-tests/<sub>/_README.md` (CP-3 交付页) | **手工补写一次** 「特征对账」section + 在本 spec §11 注脚记录 README 格式模板（F4：不依赖 tmp 脚本） |

## 6 · Acceptance Criteria

| # | 验收 | 怎么验 |
| --- | --- | --- |
| 1 | 老 jury 输出（无 `features_status`）能正常 parse | 现有 fixture 仍 PASS（向后兼容） |
| 2 | 新 jury 输出含 `features_status` 时 matches_spec 正确 aggregate | TDD L2 真值表 |
| 3 | 特征抽取 LLM 失败 → matches_spec=true 不阻断 | TDD L3 fail-safe |
| 4 | matches_spec=false 触发 retry | TDD L4 jury_loop 集成测试 |
| 5 | 重试 N=3 次仍 FAIL → 写 TODO + 标 blocked | TDD L4 + 集成测试 |
| 6 | end_effector 在 v2.36.1 main 跑（已知 GISBOT 法兰 4 臂 + PEEK 都画对）→ features 抽取 **≥3 条** 且**必含 anchor 特征 `flange_arms_4`**（最显眼，bug A 核心特征）；matches_spec PASS（F6：不硬要求覆盖所有特征，降低 LLM 不稳定风险） | L5 e2e smoke `requires_jury_loop_e2e` marker（手动跑） |
| 7 | 故意 break ee_001_01.py（删 4 臂 union）→ matches_spec FAIL with missing feature flange_arms_4 | L5 反向回归（手动跑） |

## 6.5 · 测试金字塔（5 层）

| 层 | Case | mock 还是 real | CI |
| --- | --- | --- | --- |
| **L1** parse | jury verdict 含/不含 `features_status` 都正确 parse（向后兼容老 fixture）；features_status 中 visible 缺失字段 → parse_anomalies | mock content_text | ✓ 跑 |
| **L2** aggregate | `matches_spec = all(visible)` 真值表（0/1/2/n features, all visible/部分 invisible/all invisible）| 纯单元 | ✓ 跑 |
| **L3** feature_extractor | mock LLM 返回 `{features:[...]}` 验证 prompt 构造、cache 命中、抽取失败 fallback (matches_spec=true 跳过)、超过 12 条截断 | mock LLM client | ✓ 跑 |
| **L4** retry 集成 | mock jury 第一次 fail 第二次 pass → 验证 jury_loop 走 retry 路径；rewriter 收到 missing features 名列表；3 次 fail 后写 TODO + 标 blocked | mock LLM + jury_loop hook | ✓ 跑 |
| **L5** e2e smoke | 真 LLM + 真 fixture（v2.36.0 main GISBOT/jiehuo 归档）：(a) 现状 PASS / (b) 故意 break ee_001_01.py 删 4 臂 union → FAIL with missing flange_arms_4 / (c) 同特征集合 3 次跑一致 | real LLM + real fixtures | ⏭ skip (marker `requires_jury_loop_e2e`，需 GEMINI_API_KEY + 花钱手跑) |

## 7 · Risks & Mitigations

| 风险 | 缓解 |
| --- | --- |
| LLM 抽特征不稳定（每次输出 feature 集合不同）| temperature=0 + 固定 prompt 模板；features ≤12 条；e2e smoke 3 次比较 feature_id 集合一致 |
| Token cost 涨 | feature_extractor 仅 1 次 per run；vision prompt features 仅本视角相关；用 cheap model |
| Prompt rewriter 反馈不够智能 | v1 朴素拼接 missing features 名；后续 v2 iterate（不在本 PR） |
| Vision LLM 误判 features 可见性 | L5 e2e 跑 known-good fixture 期 PASS；如 drift 出现 调 prompt + 报告 |
| gemini 代理 503 现状 | feature extractor 同 backend；503 时 matches_spec 静默跳过 → 不阻断（D5）|
| 老 jury fixture 大量存在 | 向后兼容 parse 兜底（D2 backward compat 子项） |

## 8 · 不变量（任何 session 改代码都不许碰）

1. **不许动 `_REQUIRED_BOOL_KEYS` 现有 5 个 key 的语义**（仅追加 `matches_spec`）
2. **不许把 features 抽取 LLM 调用变成 per-view**（cost 爆炸；spec D1 已定 per-run）
3. **不许让 matches_spec FAIL 阻断 enhance 阶段**（FAIL 走 retry；N 次后才 block deliver）
4. **不许去掉 fail-safe**（特征抽取 LLM 失败 → matches_spec=true，pipeline 继续；spec D5）
5. **不许跑 `cad_pipeline.py full`**（绕开 STATUS doc checkpoint，仓库纪律）

## 9 · 验证脚本（用户验收时跑）

```bash
# 跑测试套件
python -m pytest tests/jury/ tests/test_photo3d_jury_matches_spec.py -q

# 烟雾测试 (real LLM, 需 GEMINI_API_KEY + 花钱)
python -m pytest tests/jury_loop/ -m requires_jury_loop_e2e

# 端到端 (沿用 v2.36.0 CP-3 流程)
python cad_pipeline.py enhance --subsystem end_effector
# 看 cad/end_effector/.cad-spec-gen/matches_spec_features.json 已生成
# 看 cad/output/renders/jury_report.json 含 features_status
# 看 enhance-check.quality_summary.matches_spec_status
```

## 10 · 跨会话入口

- 本 spec：`docs/superpowers/specs/2026-05-13-jury-matches-spec-design.md`
- Plan（待 writing-plans 生成）：`docs/superpowers/plans/2026-05-13-jury-matches-spec-plan.md`
- STATUS doc（plan 阶段建）：`docs/superpowers/JURY_MATCHES_SPEC_STATUS.md`（F9：命名与 v1 `QUALITY_OVERHAUL_STATUS.md` 一致：全大写 + 下划线）
- 前置 v1：`docs/superpowers/specs/2026-05-13-quality-overhaul-design.md` §2.2 / spec §4 (Out of Scope 第 2 条)
- 北极星：`memory/project_north_star.md`

## 11 · 注脚 — `cad-tests/<sub>/_README.md` 「特征对账」section 模板（F4）

CP-3 期间 v1 用过的 `tmp/_write_cp3_readme.py` 是 throwaway 脚本（tmp/ gitignored），不可作为 v2 实施依赖。v2 plan 阶段需**手工补一段 README section**，按以下模板：

```markdown
## 特征对账（matches_spec / v2.37+）

**状态**：✓ PASS / ⚠ 重试中 / ✗ FAIL — 见 `02_codegen/MATCHES_SPEC_TODO.md`

- 抽取特征数：N
- 各视角覆盖：V4=3/3 / V5=2/2 / V6=1/1（feature_id 数 PASS / 总数）
- 锚点特征 `flange_arms_4`：✓ 在 V4 + V5 可见
- 阻断特征：（如 PASS 此处略；FAIL 时列 missing feature_id 集合）

证据：`cad-spec-gen/matches_spec_features.json` + `jury_report.json::view_verdicts[*].features_status`
```

数据来源：
- `cad/<sub>/.cad-spec-gen/matches_spec_features.json` → 抽取特征数
- `cad/output/renders/jury_report.json::view_verdicts[*].features_status` → per-view 覆盖
- `cad/<sub>/.cad-spec-gen/MATCHES_SPEC_TODO.md`（如 FAIL）→ 阻断特征列表

## 12 · Review Findings 记录（2026-05-13 spec 4 层审查）

写完 spec 后跑 4 层审查（self-review / 5 角色对抗 / 代码-spec 对照 / holistic dry-run），9 项 finding 全部修复并 inline 写入 spec：

| # | 严重度 | 修在哪 |
| --- | --- | --- |
| F1 | BLOCKER（闭环未闭）| §5.1 + §5.2.2 加 RunVerdict + overall_matches_spec aggregate |
| F2 | BLOCKER（漂移）| §5.3 enhance-check 读 `jury_report.json` 透传 wire |
| F3 | MAJOR（漂移）| §3 D1 + §5.1 改 per-process scope（不是 per-run） |
| F4 | MAJOR（漂移）| §5.3 不依赖 tmp 脚本，README 手工补 + 本 spec §11 模板注脚 |
| F5 | MAJOR（闭环未闭）| §5.1 retry per-view scope；plan 实施前 grep 验证 jury_loop 假设 |
| F6 | MINOR（回归）| §6 acc #6 降阈值 ≥3 features 含 anchor `flange_arms_4` |
| F7 | MINOR（回归）| §5.2.2 ViewVerdict default_factory explicit |
| F8 | MINOR（漂移）| §3 D7 + §5.3 text-only endpoint 优先 vision fallback |
| F9 | MINOR（流程）| §10 STATUS 命名 `JURY_MATCHES_SPEC_STATUS.md` 与 v1 一致 |
