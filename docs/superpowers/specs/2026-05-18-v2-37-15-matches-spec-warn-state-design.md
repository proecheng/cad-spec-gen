# v2.37.15 design — `_derive_matches_spec_status` 扩 'warn' 中间态 + §11 #3 archeology 闭合

**日期**：2026-05-18
**作者**：proecheng + Claude（brainstorming session）
**对应 followup**：[JURY_MATCHES_SPEC_STATUS.md §9.3](../JURY_MATCHES_SPEC_STATUS.md) #2 (LOW) + #3 (LOW)
**版本承诺**：v2.37.15（tag-only release，见 memory `project_v2_31_1_packaging_cleanup.md`（摘要：v2.25+ tag-only release 模式））

---

## §1 背景

### 1.1 现状

`src/cad_spec_gen/data/tools/photo3d_jury.py:195-211` 当前实现：

```python
def _derive_matches_spec_status(run: RunVerdict) -> str:
    """v2.37 Task 7：决策 matches_spec_status（'pass' | 'warn' | 'fail' | 'blocked'）。

    本 task 简化决策（Task 9 retry 接入后再扩 'warn'/'blocked'）：
    - overall_matches_spec=True → 'pass'
    - overall_matches_spec=False → 'fail'（Task 9 retry 中间态再改 'warn'，
      达 N retry 上限再升 'blocked'）
    """
    if run.overall_matches_spec:
        return "pass"
    return "fail"
```

docstring 占位 `'warn'` / `'blocked'` 是 v2.37 Task 7 预留，原意"Task 9 retry 接入后扩"。**v2.37.9 Task 9 retry 已实施**（PR #88），但 deriver 没回头扩 → 典型「intent 早写 + 实现晚到」漂移（与 ruff cleanup 漂移同质）。

### 1.2 问题

binary `pass/fail` 信息粒度不足：

- 用户看到 `status='fail'` 时**无法区分**「1 个视角不达标」与「5 个视角全废」
- 重做决策依据不足：partial fail 可能只需挑选好的视角交付 / 单视角重渲，full fail 才需要整体重做

### 1.3 archeology — §11 #3 已隐式闭合

§11 #3 (LOW) 原描述："`tools/render_qa.py` mirror drift cleanup（pre-existing main 历史债）"。

archeology 结果：

- `git ls-files tools/render_qa.py` → tracked（canonical，5+ commits）
- `git check-ignore src/cad_spec_gen/data/tools/render_qa.py` → 命中 gitignore
- `diff` 两文件 → byte-equal（无 drift）
- `git log --all -- src/cad_spec_gen/data/tools/render_qa.py` 末次记录：`35629fa chore(packaging): 清理 v2.10 遗留 tracked mirror（55 文件 git rm --cached）`（v2.31.1, 2026-05-09）

结论：v2.31.1 packaging cleanup 把 mirror 从 git tracked 移除 + `scripts/dev_sync.py` 接管同步 → drift 不再可能发生。§11 #3 **已被 v2.31.1 隐式闭合**，本 spec 仅追注 archeology 注脚，不动代码（archeology before diagnosis，见 memory `feedback_archeology_before_diagnosis.md`（摘要：异常状态先 archeology 再下结论））。

---

## §2 决策（已锁）

| 维度 | 决策 |
|---|---|
| warn 语义 | **部分视角失败**（`0 < failed_views < total_views`） |
| blocked 归属 | jury 层**不出** blocked / delivery 层保留 `fail → blocked` |
| warn 在 delivery | **不 blocked** / 正常交付 + 透传 `quality_summary` |
| schema_version | 仍 `1`（enum 值扩展向后兼容） |
| docstring 占位 | drop `'blocked'` 字样，docstring 与实现对齐 |
| 职责分离 | jury 层表「判定」（pass/warn/fail），delivery 层表「决策」（fail → blocked） |

### 2.1 为什么不接 retry 计数（拒绝方案 C）

`_derive_matches_spec_status` 跑在 retry loop **结束之后**，拿 final `RunVerdict`。RunVerdict 数据 surface 不含 retry 计数（retry_used / retry_max 在 jury_loop orchestrator 层）。若接 retry 计数，需改 deriver 签名 → 影响 `aggregate_run_verdict` 等多处调用方 → 范围过大。

structural 派生（partial vs full fail）只用 RunVerdict 现有字段，**零 schema 变动**。

### 2.2 为什么 blocked 留 delivery 层（拒绝 jury 层 blocked）

`photo3d_delivery_pack.py::_check_matches_spec_failed_blocked` 已在 delivery 层用 `status == 'fail'` 决定 blocked（D4 半闭环，写 TODO + append blocking）。若 jury 也吐 blocked → 职责重叠 → 下游消费方需区分两 blocked 来源 → 复杂度无端增长。

职责分离：jury 表"判定结果"，delivery 表"是否交付"。

---

## §3 接口契约

### 3.1 deriver 实现

```python
def _derive_matches_spec_status(run: RunVerdict) -> str:
    """v2.37.15：派生 matches_spec_status ∈ {'pass', 'warn', 'fail'}。

    决策表（用 RunVerdict 现有字段直接派生，零 schema 变动）：

    - 'pass'：所有视角 matches_spec=True（含 total_views=0 空集 all=True）
    - 'warn'：部分视角失败（至少 1 失败 + 至少 1 通过；0 < failed_views < total_views）
    - 'fail'：所有视角都失败（failed_views == total_views > 0）

    不变量：overall_matches_spec=False → per_view_failed_features 非空（由
    aggregate_run_verdict 构造保证：matches_spec=False 仅来源于"valid
    features_status 中至少 1 invisible"，必进 per_view_failed_features；见 §5 I-6）。

    Args:
        run: aggregate_run_verdict 返回的 RunVerdict

    Returns:
        'pass' | 'warn' | 'fail'
    """
    if run.overall_matches_spec:
        return "pass"
    total_views = len(run.view_verdicts)
    failed_views = len(run.per_view_failed_features)
    # 不变量保证 failed_views >= 1（见 docstring + §5 I-6）
    if failed_views < total_views:
        return "warn"
    return "fail"
```

### 3.2 决策表（含边界）

| 输入 | total_views | failed_views | overall_matches_spec | 输出 |
|---|---:|---:|---:|---|
| 全视角通过 | 3 | 0 | True | `pass` |
| 空 RunVerdict | 0 | 0 | True | `pass`（空集 all=True） |
| 部分视角失败 | 3 | 1 | False | `warn` |
| 部分视角失败 | 5 | 2 | False | `warn` |
| 全视角失败 | 3 | 3 | False | `fail` |
| 单视角失败 | 1 | 1 | False | `fail`（单视角无 partial） |

---

## §4 修改面

### 4.1 主代码

| 文件 | 改动 | 行数估 |
|---|---|---:|
| `src/cad_spec_gen/data/tools/photo3d_jury.py:195-211` | `_derive_matches_spec_status` 重写 + docstring 改 v2.37.15 语义 | ~10 |

### 4.2 测试

| 文件 | 改动 | 行数估 |
|---|---|---:|
| `tests/jury/test_photo3d_jury_matches_spec.py` | 补 AC-1/2/3/4/5 各 case | ~50 |
| `tests/jury/test_cmd_enhance_check_matches_spec.py` | 透传 'warn' 用例（AC-6） | ~30 |

### 4.3 文档

| 文件 | 改动 |
|---|---|
| `docs/superpowers/JURY_MATCHES_SPEC_STATUS.md` §9.3 | #2 标 closed v2.37.15 + #3 标 closed-by-v2.31.1（archeology 注脚指 `35629fa`） |

### 4.4 不动文件（明示）

| 文件 | 原因 |
|---|---|
| `photo3d_delivery_pack.py::_check_matches_spec_failed_blocked` | delivery 层 fail→blocked 行为零变化 |
| `enhance_consistency.py::_read_jury_matches_spec_status` | 透传层 fail-safe（None）已覆盖新 enum 值 |
| PHOTO3D_JURY_REPORT schema | schema_version 仍 1，enum 扩展向后兼容 |

### 4.5 canonical / mirror 同步

按项目术语 §3（见 memory `feedback_subagent_cwd_drift.md`（摘要：subagent 跨命令 cwd 漂移防御））archeology 已锁定：

| 路径 | 角色 | 状态（spec 起草时 verify） |
|---|---|---|
| `tools/photo3d_jury.py` | **canonical**（git tracked） | byte-equal 37639 字节 |
| `src/cad_spec_gen/data/tools/photo3d_jury.py` | **mirror**（gitignored，dev_sync 同步） | byte-equal 37639 字节 |

**实施流程**：改 canonical → 跑 `python scripts/dev_sync.py` → mirror 自动同步。

同样适用于测试（`tests/jury/` 直接 git tracked，无 mirror）— 改测试文件无需 dev_sync。

---

## §5 不变量

- **I-1**：`PHOTO3D_JURY_REPORT.schema_version` 仍 `1`（enum 值扩展向后兼容）
- **I-2**：`'pass'` 触发条件零变化（`overall_matches_spec=True`）
- **I-3**：`'fail'` 触发条件等价收窄到「全视角失败」；原 `'fail'` 涵盖的「部分视角失败」case 现归 `'warn'`
- **I-4**：delivery 层 `'fail' → blocked` 行为零变化
- **I-5**：`'warn'` 不触发 delivery blocked（`delivery_status=accepted`）
- **I-6**：构造不变量 — `overall_matches_spec=False → len(per_view_failed_features) >= 1`（由 `aggregate_run_verdict` 构造保证：`matches_spec=False` 仅来源于「valid features_status 中至少 1 invisible」，必进 per_view_failed_features）
- **I-7**：下游 fail-safe（status 缺/烂/不是 dict → `None`）保留

### 5.1 I-3 行为变更影响 — 半闭环 fail-safe

`'fail'` 触发条件收窄是**唯一**用户可观测的行为变更：

- v2.37.14 之前：partial fail → status='fail' → delivery blocked
- v2.37.15 之后：partial fail → status='warn' → delivery accepted

潜在风险：若用户依赖「partial fail 也阻断 delivery」，本改动会让 partial fail 不再阻断。但：

- jury 现有消费方（`_check_matches_spec_failed_blocked`）显式判 `status == 'fail'` 才 blocked — 不判 `'warn'` → 行为符合 §2 决策
- 用户判 `quality_summary.matches_spec_status == 'fail'` 决策的代码不受影响（'fail' 还是 'fail'）
- 新 'warn' 值在 quality_summary 中显式透传，用户能看到「partial fail」信号决策

---

## §6 验收（AC）

| AC | 触发条件 | 期望 |
|---|---|---|
| **AC-1** | 2 views，1 view matches_spec=False（features_status 含 invisible） | `_derive_matches_spec_status` returns `'warn'` |
| **AC-2** | 3 views，3 views matches_spec=False | returns `'fail'` |
| **AC-3** | 2 views，0 views fail | returns `'pass'` |
| **AC-4** | total_views=0（空 RunVerdict） | returns `'pass'`（空集 all=True，保留现行为） |
| **AC-5** | 单视角失败 (total=1, failed=1) | returns `'fail'`（单视角无 partial） |
| **AC-6** | jury 出 `matches_spec_status='warn'` → enhance-check 透传 | `ENHANCEMENT_REPORT.quality_summary.matches_spec_status == 'warn'` 且 `delivery_status == 'accepted'`（不 blocked） |
| **AC-7** | docs — `JURY_MATCHES_SPEC_STATUS.md` §9.3 表 | #2 行加 `closed v2.37.15` 标记 + #3 行加 `closed-by-v2.31.1` 标记 + archeology 注脚指 `35629fa` |

### 6.1 TDD 节奏

- AC-1～5：5 个 RED → 5 个 GREEN（每个 AC 独立 fixture，标注 `matches_spec_status_partial_fail_returns_warn` 等）
- AC-6：单 RED → GREEN（透传链路 fixture，复用 `test_enhance_check_transits_matches_spec_status_pass` pattern）
- AC-7：docs-only，纯文档 PR-task（不要求 RED phase）

**禁 pure refactor / no-RED phase**：本 PR 引入新 enum 值 `'warn'` 是行为变更，不适用 pure refactor 路径（项目术语 §5）。

---

## §7 §11 follow-up

### 7.1 本 PR 闭合

| ID | 项目 | 闭合方式 |
|---|---|---|
| **§9.3 #2** | `_derive_matches_spec_status` 加 'warn'/'blocked' 中间态 | ✅ 本 spec 实现 'warn'，drop 'blocked' 占位 |
| **§9.3 #3** | `tools/render_qa.py` mirror drift cleanup | ✅ archeology 注脚追闭合到 v2.31.1（`35629fa`） |

### 7.2 仍 open

| ID | 项目 | 触发条件 |
|---|---|---|
| **§9.3 #4** | plan-drift 模板纠正（spec review checklist 补） | v2.37 系列后续 PR |
| **§9.3 #5** | Task 13 cad-tests README 真 e2e 时补 | 下次真 e2e run 触发 |

### 7.3 本 spec 新登记

无（小 PR，无新 followup 预期）。

---

## §8 §12 PR-self follow-up

无（小 PR，无 spec 本身 PR-self followup 预期）。

---

## §9 v2.37.15 release 承诺

### 9.1 user-facing 变更

- `quality_summary.matches_spec_status` 新增 `'warn'` 值
- 含义：「**部分视角与设计不符**，可交付但建议复核」
- 旧值 `'pass'` / `'fail'` 触发条件不变（但 `'fail'` 收窄到「全视角失败」）

### 9.2 backward compat

#### 9.2.1 内部消费方（zero-impact）

- `photo3d_delivery_pack._check_matches_spec_failed_blocked` 显式判 `== 'fail'` 才 blocked，新 `'warn'` 不触发 blocked → 行为零变化
- `enhance_consistency._read_jury_matches_spec_status` 透传 status 字符串，对值不假设 → 兼容新 'warn'
- PHOTO3D_JURY_REPORT.schema_version 仍 `1`

#### 9.2.2 外部消费方（**有行为变更，需告知**）

`'fail'` 触发条件**等价收窄**到「全视角失败」。原 `'fail'` 涵盖的「partial fail」case 现归 `'warn'`：

- ✅ 若外部代码判 `status == 'fail'` 表"完蛋了"：行为变更 — partial fail 现归 'warn'，不再命中此分支
- ✅ 若外部代码判 `status == 'pass'` 表"完美"：零变化（'pass' 触发条件不变）
- ⚠️ 若外部代码想覆盖「任何失败」：需改为 `status in ('fail', 'warn')`

release notes 必显式提示外部消费方的迁移路径。

### 9.3 风险评估

- **低风险**：deriver 改动隔离，仅 3 状态 + 1 边界 + 1 透传 = 5 测试覆盖
- **回归覆盖**：项目连续 25 PR CI 一次过 + characterization 测试保现行 `'pass'` / `'fail'` 不变
- **影响范围**：仅 jury 输出 enum 扩展，下游消费方零代码改动

### 9.4 release notes 草稿

```markdown
## v2.37.15 — matches_spec_status 加 'warn' 中间态

**user-facing**：
- `quality_summary.matches_spec_status` 新增 `'warn'` 值，表「部分视角与设计不符」
- 单视角失败仍归 `'fail'`，全视角失败仍归 `'fail'`，partial fail（部分通过部分失败）归 `'warn'`
- `'warn'` 不阻断 delivery，仅作信号

**§11 follow-up 闭合**：
- #2 `_derive_matches_spec_status` warn 中间态 ✅
- #3 `tools/render_qa.py` mirror drift（追闭合到 v2.31.1）✅

**backward compat 须知**：
- 内部消费方（delivery / enhance_consistency）零变化
- 外部消费方若判 `status == 'fail'` 想覆盖「任何失败」需改为 `status in ('fail', 'warn')`；只想覆盖「全视角失败」无需改动
- PHOTO3D_JURY_REPORT.schema_version 仍 1
```

---

## §10 关联 memory 与项目术语

- **memory** `feedback_archeology_before_diagnosis.md`（摘要：异常状态先 archeology 再下结论）— §1.3 archeology 闭合 #3 的方法论
- **memory** `feedback_subagent_cwd_drift.md`（摘要：subagent 跨命令 cwd 漂移防御）— §4.5 canonical/mirror 同步
- **memory** `project_v2_31_1_packaging_cleanup.md`（摘要：v2.25+ tag-only release 模式）— release 形式
- **项目术语 §5** pure refactor / no-RED phase — 本 PR 是行为变更，不适用，TDD RED 必走
- **项目术语 §10** plan-drift 5 分类 — Task 0 scout 必验证 canonical 路径（dev_sync 双写区）

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
