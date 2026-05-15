# v2.37.7 jury CLI 收尾 retro — 2026-05-15

> 关联 PR: TBD
> 关联 spec: `docs/superpowers/specs/2026-05-15-v2-37-7-jury-cli-improvements-design.md`
> 关联 plan: `docs/superpowers/plans/2026-05-15-v2-37-7-jury-cli-improvements.md`

## 摘要（1 段）

v2.37.7 闭合 §11-N3 + §11-N2 两 followup（per-view progress + override-subsystem alias）。
TDD 5 测试 GREEN（3 §11-N3 + 2 §11-N2） / jury 子集 504 → 509 PASS / 0 regression / CI 8/8 SUCCESS（pending push）。
2 个 production commit：Task 1 `2023896`（进度行 3 路径全覆盖）+ Task 2 `fa102dd`（override flag + effective_subsystem 字段）。

## 完成项

### Task 1: 每视角进度三路径输出（§11-N3）

`tools/photo3d_jury.py` +21 行 production，`tests/jury/test_photo3d_jury_progress.py` +224 行测试：

- **try-success 路径**：`△ [V<n>/<total>] <model> photoreal=<score> verdict=<verdict> <latency>s`
- **except JuryLlmError 路径**：`△ [V<n>/<total>] <model> ERROR <error_kind> 0.0s`
- **except Exception 路径**（NEW BLOCK，E2 fix 不吞异常）：
  `△ [V<n>/<total>] <model> CRASH <exc_type>\n` + **`raise` 重新抛出**保证未知异常不被吃掉
- **total_views 兜底**：`len(layer0.frozen_report.get("views", []) or [1])` 避免 0 视角时 ZeroDivisionError
- **字符风格**：沿用既有 `△` (U+25B3) stderr 风格（line 763 既有用法）

### Task 2: --override-subsystem alias flag（§11-N2）

`tools/photo3d_jury.py` +67/-7 行，`tests/jury/test_photo3d_jury_progress.py` +106 行测试：

- argparse 新增 `--override-subsystem ACTUAL_SUBSYSTEM` flag
- **输入校验**：`strip() → 空 / 含 `/` / 含 `\` / 含 `..` → exit=2 + stderr `✗ 错误信息``
- **effective_subsystem 集中计算**：`args.override_subsystem or args.subsystem`（默认零行为）
- **8 path 改用 effective_subsystem**（line 279/385/391/402/510/519/651 区域 jury Layer 0 / run_dir / 路径拼接）
- **3 处保留 args.subsystem**（line 464 guard / 687 report `subsystem` 字段 / 745 review_input）保 forward-compat
- **report + jury_review_input 加 `effective_subsystem` 字段仅 override 时存在**（默认调用零变化）

## 测试与回归

- 5/5 新增 jury progress 测试 GREEN（3 §11-N3 success/failure/crash + 2 §11-N2 used/validation）
- jury 子集 504 → 509 passed / 6 skipped / 0 regression
- CI 8/8 SUCCESS（pending push & PR）

## 走过的弯路 / Plan-drift

### 1. Task 2 implementer Step 6 漏加 report 字段写入（中等坑）

production code 把 `args.subsystem` → `effective_subsystem` 字段读取改了 8 处 path，但 PHOTO3D_JURY_REPORT.json 内嵌 `effective_subsystem` **字段未写入**。`test_override_subsystem_flag_used` 断言失败暴露：测试读 report 拿不到 `effective_subsystem`。fix subagent 加条件分支 `if args.override_subsystem: report["effective_subsystem"] = effective_subsystem` 才闭环。

**教训**：production 改 "字段读取" ≠ 改 "字段写入"；TDD red 测试断言 report **写入** assertion 比断言 logic-only 单元 assertion 更能抓 wiring bug。spec §3.2 D2 第 4 条本身已写"report 加 effective_subsystem 字段"，是 implementer drift；spec/plan 文字本无歧义。

### 2. Task 1 implementer Windows GBK 编码问题（低坑）

`_setup_jury.py` 脚本 `print("✓ ...")` 在 Windows cp936 默认 codec 下 `UnicodeEncodeError`；implementer 需加 `sys.stdout.reconfigure(encoding="utf-8")` 在入口处。生产代码 `tools/photo3d_jury.py` 走 stderr 不受影响（已有 utf-8 buffer 配置）。

**教训**：Windows Python 默认 cp936；脚本/工具 stdout/stderr 输出 emoji/中文/特殊字符必须显式 `reconfigure(encoding="utf-8")` 或文件层 PYTHONIOENCODING；这条已在 §11-N3 spec §4 风格约束确立，本次只是 setup 辅助脚本踩坑（非 production）。

### 3. implementer 多写 unused `_resolve_effective_subsystem(args)` helper（minor）

implementer 在 `main()` 外加了 `_resolve_effective_subsystem(args)` helper 想抽离 `args.override_subsystem or args.subsystem` 逻辑，但 `main()` 内仍 inline 计算两遍，helper 从未被调用。reviewer 标为 minor（不影响行为也不阻塞 merge）。

**教训**：YAGNI — 抽 helper 前先确认调用点会用；inline 一行计算无需 helper。下批 §11 cleanup 可顺手删（或挂 `# pragma: no cover` 等用得着时再启用）。

## Layer 6 fact-check 复盘

spec rev 1 → rev 2 通过 layer 6（代码-spec grep 对照）抓到的 7 处 fix（F1/E2/E3/E4-E6/E8/E9）全部进 spec rev 2 真值，并在实施中**零新增 plan-drift**：

| Fix | 内容 | 实施印证 |
|-----|------|---------|
| F1 | try-success 路径补 emit（不只 except 才输出） | Task 1 commit `2023896` line ~623 |
| E2 | except Exception bare 不吞异常 + `raise` re-raise | Task 1 commit `2023896` line ~658 |
| E3 | --override-subsystem 输入校验 exit=2（空 / 路径遍历） | Task 2 commit `fa102dd` validation block |
| E4+E5+E6 | report 字段表清单（effective_subsystem 仅 override 时存在） | Task 2 commit `fa102dd` line ~687 条件写入 |
| E8 | Unicode `△` U+25B3 不是 ASCII triangle 字符 | 3 路径进度行字面量 |
| E9 | grep `△ \[V` 精确 prefix 不抓到诊断/debug 输出 | 测试 fixture stderr assert |

**结论**：layer 6 grep 对照在 spec 阶段直接预防 7 处实施踩坑，无新 plan-drift 漂移。本批 3 处弯路（report 字段漏写 / GBK 编码 / unused helper）均在 implementer 层冒出、reviewer 层抓到、当 PR commit 内闭环，spec/plan 本身零修订。

## §11 follow-up 更新

**闭合**：
- §11-N3 (jury per-view progress)
- §11-N2 (jury --override-subsystem alias flag)

**仍 open（推迟下批）**：
- §11-N1 (rebrand "photo3d-jury" → 工具批改名)
- §12 f1 (max_tokens 1024 sunset → 2048 评估)
- §12 f4 (N≥50 批量成本评估)
- minor: `_resolve_effective_subsystem` unused helper 清理

## 后续工作（下个 PR）

按用户 Tier1+Tier2 队列：

- **v2.37.8 候选**：§11-N1 rebrand 工具批改名（中工作量；spec 需多轮 search-replace 设计） 或 §12 f1 max_tokens sunset 1024→2048（小工作量；先验证 jury 7 视角真实 token usage 上限）
- **真 LLM adapter / GISBOT 真 vendor rerun**：Tier 2 候选；需 wire path adapter + 真 vendor key 验证
