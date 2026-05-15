# 设计：Tier 2 GISBOT 端到端 photo3d-jury e2e 测试

- **日期**：2026-05-15
- **基线**：main@`27b2c5c`（v2.37.5 merge 后；working tree clean）
- **分支**：`feat/gisbot-jury-e2e`（待建）
- **目标版本**：**不发 patch tag**（0 production code 改；仅沉淀 spec/plan/retro 进 git）
- **规模**：小-中；setup 脚本 ~50 行 本地不进 git + e2e 跑测试 + 3 份 git tracked docs（spec/plan/retro 共 ~400 行）
- **状态**：brainstorming 完成（含审查 F1+F2 数据精度 fix）；待用户复审 → writing-plans

---

## 1. 背景与目标

GISBOT 是 v2.36 自制件质量大修测试归档（`D:/Work/cad-tests/GISBOT/`），结构 = 6 阶段顶层 `01_spec/02_codegen/03_build/04_render/05_enhance/`，已跑完 enhance（7 视角 enhanced.jpg + ENHANCEMENT_REPORT.json + labeled cn/en）但**未跑过 photo3d-jury full pipeline**。

photo3d-jury 期望目录 = `<project_root>/cad/<subsystem>/.cad-spec-gen/runs/<active_run_id>/`（jury.py line 516-524 + 653）；与 GISBOT 6 阶段结构**不兼容**。

**layer 6 E7/E8 fact-check 关键发现**（实测 ENHANCEMENT_REPORT.json + render_manifest.json）：
- `subsystem` = **"end_effector"**（不是 "GISBOT"——GISBOT/ 是 end_effector v2.36 测试的物理复制目录归档，内部 metadata 未 rebrand）
- `run_id` = "20260513T115709Z"（v2.36 时代既有）
- `render_dir` = `D:\\Work\\cad-spec-gen\\cad\\output\\renders`（**绝对路径指 cad-spec-gen 仓**不是 cad-tests）
- `views[].source_image` / `enhanced_image` 用 `cad/output/renders/V*.png|jpg` 相对 cad-spec-gen 项目根的老路径

**结论**：纯 copy 方案不可行（subsystem 字段不匹配 + 绝对路径错指 + view paths 不可解析）；必须 **path mirror + subsystem 用既有内部值（end_effector）**。

**目标**：跑通 GISBOT 端到端 photo3d-jury 全流程（feature_extractor + 7 视角 vision verdict + 可能 retry 闭环），验证：
- 跨项目结构兼容性（B 方案 setup 模式 work）
- photo3d-jury full pipeline 完整跑通
- 真金 micuapi.ai gemini-2.5-flash LLM 端到端 vendor 验证（上次只测 1 视角；本次跑 7）

**北极星 5 gate**：零配置 ✓（已配 jury profile）/ 稳定可靠 ✓（验证跨结构）/ 结果准确 ✓（真 LLM 验真 vendor）/ SW 装即用 ✓（不碰 SW）/ 傻瓜式 ✓（用户视角 = 跑 photo3d-jury 一条命令）。

---

## 2. 范围

### 2.1 In-scope

| 文件 | 用途 | 落地 |
|---|---|---|
| `D:/Work/cad-tests/GISBOT/_setup_jury.py` | 一次性 setup 脚本（mkdir + copy + ARTIFACT_INDEX 生成）| **本地不进 git** |
| `D:/Work/cad-tests/GISBOT/cad/GISBOT/.cad-spec-gen/runs/<RUN_ID>/...` | jury 期望目录骨架（运行时生成）| 本地 |
| `D:/Work/cad-tests/GISBOT/cad/GISBOT/.cad-spec-gen/runs/<RUN_ID>/PHOTO3D_JURY_REPORT.json` | jury 跑完产出 evidence | 本地（retro 引路径）|
| `docs/superpowers/specs/2026-05-15-gisbot-jury-e2e-design.md` | 本 spec | **进 cad-spec-gen git** |
| `docs/superpowers/plans/2026-05-15-gisbot-jury-e2e.md` | plan doc | 进 git |
| `docs/superpowers/reports/2026-05-15-gisbot-jury-e2e-retro.md` | retro doc + e2e evidence 总结 | 进 git |

**总 cad-spec-gen 仓 diff**：3 份 docs ≈ 400 行（spec/plan/retro）；**0 production code / 0 测试 / 0 schema / 0 env-config 改**。

**本地 cad-tests 改**：setup 脚本 + e2e 跑后 evidence 文件（jury report + 中间产物）。

### 2.2 Out-of-scope

- 改 cad-spec-gen `tools/photo3d_jury.py` production 代码（不写 GISBOT 专属分支）
- 发 v2.37.6 patch tag（0 production 改无必要）
- 跑 photo3d-deliver 后续阶段
- 跑 `cad-spec-gen enhance --rerun-loop` jury_loop 闭环（本 PR 只测 standalone `photo3d-jury` 主入口）
- setup 脚本进 cad-spec-gen git tracked tools/（一次性脚本，YAGNI）

---

## 3. 设计决策

### 3.1 D1 — copy 不用 symlink

**抉择**：setup 用 `shutil.copy2` 复制 GISBOT 文件到 `cad/GISBOT/.cad-spec-gen/runs/<RUN_ID>/`。

**理由**：
- Windows symlink 需 Admin / Dev Mode；copy 普适跨 OS
- 实测 7 enhanced.jpg 总 **~1 MB**（每文件 ~130 KB；layer 6 F1 修——spec 写时估 50MB 错 50×；实测数据替换）；copy 成本忽略

### 3.2 D2 — RUN_ID 命名 `gisbot_e2e_20260515_T<HHMM>`

**抉择**：明确测试前缀 `gisbot_e2e_` + 日期 + 时分。

**理由**：
- 不模仿生产 active_run 时间戳 naming（防与未来真 GISBOT 项目 run 混淆）
- 同日多次跑用 HHMM 后缀防冲突
- RUN_ID 进 ARTIFACT_INDEX.json active_run_id + run_dir 名

### 3.3 D3 — ARTIFACT_INDEX 最小写

**抉择**：写 `{schema_version: 1, subsystem: "GISBOT", active_run_id: <RUN_ID>, accepted_baseline_run_id: null, runs: {<RUN_ID>: {run_id: <RUN_ID>, active: true, artifacts: {"enhancement_report": "<rel_path>", "render_manifest": "<rel_path>"}}}}`。

**理由**：
- jury 只读 active_run_id 解析 run_dir（line 516-524）+ artifacts dict 取相对路径
- 其它字段非必需；setup 脚本无需 freeze sha256（jury 内部 Layer 0 自己 freeze）
- artifact keys 名 `enhancement_report` / `render_manifest` 与 jury 代码 line 656-705 + `enhancement_semantic_review.py:67-72` 一致

### 3.4 D4 — `--budget 0.20` cost_cap

**抉择**：`photo3d-jury --budget 0.20`（用户拍板）。

**理由**：
- 实测预算上限 micuapi.ai gemini-2.5-flash $0.005/call × (1 feature_extractor + 7 jury verdict + 0-7 retry) ≈ $0.04-0.08
- $0.20 留 2.5× 余量防 retry 失控
- 超预算 jury exit=3 cost_capped；不阻断 spec 验收 AC

### 3.5 D5 — CAD_SPEC.md 直接复制 GISBOT/01_spec/CAD_SPEC.md

**抉择**：setup 脚本精确路径复制 `GISBOT/01_spec/CAD_SPEC.md → GISBOT/cad/end_effector/CAD_SPEC.md`。

**理由**：
- GISBOT/01_spec/ 已含同名 `CAD_SPEC.md`（实测 + DESIGN_REVIEW.json/.md 共 3 文件）（layer 6 F2 修——spec 写时含糊"第一个 .md"，实测精确路径替换）
- photo3d_jury feature_extractor (Task 9 v2.37) 默认读 `cad/<subsystem>/CAD_SPEC.md`（line 385）；本 PR subsystem=end_effector（D6）
- 若复制失败 → fail-safe matches_spec=True 兜底（spec §6 不变量 #11，v2.37.4 §12 doc）

### 3.6 D6 — subsystem 用既有报告内部值 `end_effector`（不是 "GISBOT"）

**抉择**：跑命令 `photo3d-jury --subsystem end_effector`（不是 `--subsystem GISBOT`）；RUN_ID 用既有 `20260513T115709Z`（不是 `gisbot_e2e_<HHMM>` — 取消 D2）。

**理由**（layer 6 E7+E8 fix）：
- ENHANCEMENT_REPORT.json + render_manifest.json 内嵌 `subsystem = "end_effector"` + `run_id = "20260513T115709Z"`；jury Layer 0 cross-validate 这些字段
- 若 cli `--subsystem GISBOT` → 与 report 内嵌字段 mismatch → jury 报 error_kind 或 blocked
- 用既有值匹配最小化 rewrite 工作量；语义 = "在 cad-tests/GISBOT/ 工作目录下重跑 end_effector subsystem 的 jury"

**spec 名误导风险**：spec/plan/retro 标题"GISBOT jury e2e"实际跑 end_effector subsystem；retro 文档显式声明此 mapping 避免读者困惑。

### 3.7 D7 — path mirror 而不是 path rewrite

**抉择**：setup 脚本镜像 GISBOT 内文件到 `cad/output/renders/` + `cad/end_effector/.cad-spec-gen/runs/20260513T115709Z/` 完全模拟 cad-spec-gen 项目根布局；**不改 ENHANCEMENT_REPORT/render_manifest 文件内容**（避免 sha256/schema 漂移）。

**理由**（layer 6 E7+E8 fix）：
- ENHANCEMENT_REPORT.json 内嵌 view paths `cad/output/renders/V*.png|jpg` 相对 project_root 工作 → 在 `--project-root D:/Work/cad-tests/GISBOT` 下解析为 `D:/Work/cad-tests/GISBOT/cad/output/renders/V*` → setup 镜像后**真实存在**
- render_manifest.json 内嵌 `render_dir = D:\\Work\\cad-spec-gen\\cad\\output\\renders` 绝对路径**仍指 cad-spec-gen** — 这是 v2.36 测试归档 metadata；本 PR 接受此 "stale absolute path" 作为 known issue
  - jury Layer 0 用 `render_dir_rel_project` 相对路径校验为主，绝对路径仅 informational（实测 enhancement_semantic_review.py:67-79 检 `render_dir_rel_project` 不检 `render_dir` 绝对）
  - 若实测 jury 报 absolute path mismatch → plan task 0 fallback 加一行 sed 改 render_dir 绝对路径

**setup 镜像清单**（Task 1 实施）：
```
D:/Work/cad-tests/GISBOT/
├── 01_spec/CAD_SPEC.md → cad/end_effector/CAD_SPEC.md
├── 04_render/render_manifest.json → cad/output/renders/render_manifest.json
├── 04_render/V*.png → cad/output/renders/V*.png
├── 05_enhance/V*_enhanced.jpg → cad/output/renders/V*_enhanced.jpg
└── 05_enhance/ENHANCEMENT_REPORT.json → cad/output/renders/ENHANCEMENT_REPORT.json
└── cad/end_effector/.cad-spec-gen/
    ├── ARTIFACT_INDEX.json （setup 生成，active_run_id=20260513T115709Z）
    └── runs/20260513T115709Z/.jury.lock（jury 自动创建/清理）
```

---

## 4. 验收

- **AC-1** `_setup_jury.py` 无异常 exit 0；镜像骨架建好（`cad/output/renders/V*` + `cad/end_effector/.cad-spec-gen/{ARTIFACT_INDEX.json, runs/20260513T115709Z/}` + `cad/end_effector/CAD_SPEC.md`）
- **AC-2** `cd D:/Work/cad-tests/GISBOT && photo3d-jury --project-root . --subsystem end_effector --budget 0.20` exit ∈ {0, 3, 10, 11, 12}（产 PHOTO3D_JURY_REPORT.json 即算成功；具体 verdict 看真 LLM）（D6+E10 修：subsystem=end_effector 匹配既有 metadata；cwd 显式 cd GISBOT）
- **AC-3** PHOTO3D_JURY_REPORT.json 含 7 视角 verdict + 顶层 `status` + `ordinary_user_message` + `first_blocking_reason`（若有）
- **AC-4** feature_extractor 抽特征成功（或 fail-safe 静默跳过 matches_spec=True）；report 含 features count 或 anomaly 标
- **AC-5** total cost ≤ $0.20（若超 → exit=3 cost_capped，AC-2 仍通过）
- **AC-6** retro doc 沉淀 lesson + evidence 链接（jury report 路径 + 实际 verdict 数字 + cost 实测）
- **AC-7** cad-spec-gen 仓 3 docs（spec/plan/retro）进 git，无 production 改；commit 序列 push 后开 PR 或直接 merge main（plan 决定）

---

## 5. 风险与边界

| 风险 | 评估 | 缓解 |
|---|---|---|
| LLM 全 7 视角失败 | 低 | jury 退 needs_review；仍算 AC-2 通过；retro 记 |
| vendor 不识别 base64 image | 极低（v2.37.1 实测 micuapi.ai 单视角 vision OK）| 实测验证；fail → retro 沉淀新 lesson |
| cost > $0.20 → exit=3 | 中-低 | budget 兜底，仍算 AC-5 通过；retro 记 |
| GISBOT 缺 CAD_SPEC.md（实测有，但 setup 复制失败）| 低 | D5 fail-safe 兜底 matches_spec=True；feature_extractor anomaly 记 |
| Setup 脚本 path/encoding bug（中文字符）| 低 | `D:/Work/cad-tests/GISBOT/` 全英文路径；setup write_text utf-8 显式 |
| jury_review_input.json freeze sha256 mismatch | 中-低 | jury 内部 Layer 0 sha256 重读校验；mismatch 写 error_kind=blocked，retro 记 |
| 既有 `cad/GISBOT/` 目录冲突 | 极低（实测不存在）| setup `mkdir(exist_ok=True)` 容错；若存在 abort 让用户清理 |
| PYTHONPATH / cad-spec-gen install 状态 | 低 | retro 验证 `photo3d-jury` CLI 入口可达；fail → 用 `python -m tools.photo3d_jury` 兜底 |
| **render_manifest.json `render_dir` 绝对路径 stale**（layer 6 E8）| 中（v2.36 测试归档既有数据，绝对路径指 cad-spec-gen 仓不是 cad-tests）| jury 主用 `render_dir_rel_project` 相对路径校验（实测 line 67-79）；plan task 0 实测若 jury 真 fail 才 fallback sed 改绝对路径 |
| **ENHANCEMENT_REPORT.json `subsystem` 字段错位**（layer 6 E7）| 已修（D6 用 subsystem=end_effector 匹配既有 metadata） | spec D6 决策；retro 显式声明 spec 标题 "GISBOT" vs 实际 subsystem "end_effector" 的 mapping |
| jury cwd 假设（layer 6 E10）| 低 | spec §7 流程加 `cd D:/Work/cad-tests/GISBOT &&` 显式 cwd 设定 |

---

## 6. 不变量

1. 0 cad-spec-gen production code 改 / 0 测试改
2. GISBOT 既有 `01_spec/04_render/05_enhance/` 字面零改（setup 只 copy 到新 `cad/` 子目录）
3. setup 脚本本地 `D:/Work/cad-tests/GISBOT/_setup_jury.py`，不进 cad-spec-gen git
4. 跑完保留 PHOTO3D_JURY_REPORT.json 在 run_dir；`.jury.lock` 自动清理
5. cad-spec-gen v2.37.5 之前所有 spec 不变量保留
6. 不发 patch tag；仅 docs 沉淀

---

## 7. 流程

```
brainstorming（本 spec）→ writing-plans → 3-4 task plan → execute
  ↓
Task 0: scout + dev_sync baseline + 实测 ENHANCEMENT_REPORT/render_manifest 内嵌 schema（layer 6 E7+E8 验证）
Task 1: 写 _setup_jury.py + 镜像 GISBOT/ 文件到 cad/ 子目录布局（D7 path mirror）
Task 2: cd D:/Work/cad-tests/GISBOT && 跑 photo3d-jury --subsystem end_effector --budget 0.20 真金 e2e（D6 subsystem 用既有内部值）
Task 3: 写 retro 沉淀 lesson + 显式声明 spec 标题 "GISBOT" vs 实际 subsystem "end_effector" 的 mapping
  ↓
docs commits 在 cad-spec-gen 仓；plan 决定开 PR 或直接 commit main（无 production 改可直 commit）
```

**关键 cwd 约定（layer 6 E10 fix）**：跑 `photo3d-jury` **必须** 先 `cd D:/Work/cad-tests/GISBOT/` 后跑——jury 内部某些 path 解析可能用 `Path.cwd()` 而非 `--project-root`；显式 cwd 避免 ambiguity。

### 7.1 Rollback 流程

跑 e2e 测试本身不可逆（已发 LLM 请求），但产物全在本地 `cad-tests/`，删目录即可。cad-spec-gen 仓只 3 docs，`git revert` 回退即可。

无 production 改 → 无用户面 release rollback 需求。

---

## 8. Plan 调查步（plan 第 0 task 跑）

1. `cd D:/Work/cad-spec-gen && git status --short && git log --oneline -3` — baseline main@`27b2c5c` clean
2. `python scripts/dev_sync.py --check` rc=0 — 镜像干净（v2.37.3 R5 D2 教训）
3. `pytest -q tests/jury/ tests/jury_loop/ 2>&1 | tail -3` — baseline 503 PASS
4. `ls D:/Work/cad-tests/GISBOT/05_enhance/*.jpg` + `wc -c` — 实测 7 enhanced 文件存在 + 总大小 ~1 MB
5. `cat ~/.claude/cad_jury_config.json | head -20` — 验证 micuapi.ai profile 配置存在 + active_profile_id 正确
6. `which photo3d-jury` 或 `python -m tools.photo3d_jury --help` — CLI 入口可达
7. `ls D:/Work/cad-tests/GISBOT/cad/` — 确认 `cad/` 子目录不预存在（setup mkdir 安全）

---

## 9. Plan 必 cover 项

- Task 0 实测 cad-tests/GISBOT 7 jpg 总大小（实测填入 ~1 MB，不假设 spec 数字；layer 6 E10 教训）
- Task 1 setup 脚本用 utf-8 显式 write（防 Windows 默认 cp936 encoding 坑）
- Task 1 setup 脚本 `mkdir(parents=True, exist_ok=True)` + `shutil.copy2` + ARTIFACT_INDEX `json.dumps(..., ensure_ascii=False, indent=2)`
- Task 2 跑 photo3d-jury 前 `set CAD_JURY_DISABLE_LLM=` 显式空（防 env 残留 disable）
- Task 2 实测 cost 数字填入 AC-5 验证（不假设 $0.04-0.08；layer 6 E10 教训）
- Task 3 retro 引 PHOTO3D_JURY_REPORT.json 绝对路径 + 含 disclaimer "session memory per-instance"（layer 6 F1 教训）

---

## 10. 不写代码 / 不进 plan 的事

- 不改 cad-spec-gen `tools/photo3d_jury.py` / 任何 production
- 不发 v2.37.6 patch tag
- 不跑 jury_loop 闭环（standalone photo3d-jury only）
- 不建 generic CAD project adapter 抽象（YAGNI；本 PR 只验证 B 方案 work）
- setup 脚本不进 cad-spec-gen git tracked（一次性）

---

## 11. 本 PR 自身 follow-up

| # | 严重度 | 内容 | 触发条件 |
|---|---|---|---|
| h1 | LOW | 若本 e2e 成功 + 用户经常跑跨项目 jury → 抽 `tools/dev/external_project_jury_setup.py` generic adapter 进 git | ≥ 3 个不同 cad-tests 项目要跑 jury |
| h2 | LOW | 若 feature_extractor 在 GISBOT 上跑慢 / 失败 → 考虑 spec features cache 预生成机制 | 实测 latency > 30s 或多次失败 |
| h3 | LOW | 若 7 视角 cost 超 $0.05 预期上限 → review jury per-call cost 估算表（cad-jury-config.md §4）准度 | 实测 cost 偏 > 2× 估算 |
