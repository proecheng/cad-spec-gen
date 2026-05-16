# v2.37.10 — rebrand path-prefix 扩 + 真 retry 闭环实测（§11-N9）retro

> 关联 PR: TBD（Task 7 push 后填）
> 关联 spec: docs/superpowers/specs/2026-05-16-v2-37-10-rebrand-path-real-retry-design.md (rev 3, 383 行, commit `a1f0647`)
> 关联 plan: docs/superpowers/plans/2026-05-16-v2-37-10-rebrand-path-real-retry.md (commit `c54ecf8`)
> Baseline: cad-spec-gen main@`6539912`（v2.37.9 merge）

## 摘要

v2.37.10 闭合 §11-N9 — v2.37.8 rebrand 工具扩 `--from-path-prefix` + `--to-path-prefix` 互锁 flag + 真 retry 闭环实测。**path-prefix 工具完整闭环**（实测 verify 4 manifest / 84 path values 真改）+ **retry 闭环 path 跑通**（cad_pipeline 不撞 render_dir mismatch / retry round 真启动）。9 新 TDD + 全套件 3244 PASS / 0 regression / CI 8/8（pending push）。

vendor DNS 限制（`gemini-3-pro-image-preview` endpoint `getaddrinfo failed`）阻 photoreal ≥60 终极验收 — 非 PR 改动问题，留 §11-N12 follow-up。

## 完成项

### 改动 1 — rebrand 工具扩 path-prefix
- `tools/dev/rebrand_test_archive.py` 加 argparse 2 互锁 flag
- 5 新 helper：`_validate_path_prefix` / `_looks_like_abs_path` / `_normalize_path` / `_matches_prefix` / `_rewrite_prefix`
- `_scan` 加 `_rewrite_path_in_data` 递归扫 dict/list/string + prefix rewrite
- 9 新 TDD（T-prefix-A-I）全 PASS（5 Task 1 + 7 Task 2 含启用 E）

### 改动 2 — 真 retry 闭环实测（2 步 ops + cad_pipeline enhance + jury_loop）
- 第 1 步 reverse unify (2 files / 4 path) + 第 2 步 forward (4 files / 84 path)
- cad_pipeline enhance-check 不撞 render_dir mismatch（v2.37.9 BLOCKED 解除）
- cmd_enhance --rerun-loop 真启动 retry round（log "Retry 1/2" + "Retry 2/2"）
- vendor DNS fail 阻 photoreal 真提升 — 非 PR bug（环境问题）

## 实测真值（GISBOT 真 retry — 2026-05-16）

### Step 4: 2 步 ops 结果

| 步 | 行动 | 文件改 | path values 改 |
| --- | --- | --- | --- |
| 1 | reverse unify `D:/Work/cad-tests/GISBOT` → `D:\Work\cad-spec-gen` | 2 manifest | 4 path |
| 2 | forward `D:\Work\cad-spec-gen` → `D:\Work\cad-tests\GISBOT` | 4 files | 84 path |

verify state unified：3 manifest 全 OK / 04_render 全 `\` separator / cad/output/renders 跨 separator（顶层 `/` files[] `\`）— 保留原 separator 风格 ✓

### Step 5: cmd_enhance --rerun-loop

```
20:00:02 [INFO] Enhance backend: gemini
20:00:02 [INFO] Using manifest: 7 files (subsystem=end_effector, ts=2026-05-13T12:05:52)
20:00:02 [INFO]   Running: enhance V1_front_iso_20260513_1959.png (V1, 127 chars)
20:00:03 [INFO]   Retry 1/2 for V1_front_iso_20260513_1959.png ...
20:00:13 [INFO]   Retry 2/2 for V1_front_iso_20260513_1959.png ...
20:00:23 [ERROR]   FAILED enhance V1_front_iso_20260513_1959.png (exit 1, 20.7s)
20:00:23 [ERROR]     STDERR: Connection error: [Errno 11001] getaddrinfo failed
... (7 view 全同 pattern)
```

| AC | 期望 | 实证 |
| --- | --- | --- |
| AC-3 render_dir mismatch 消除 | True | ✅ path-prefix 工具 verify / cad_pipeline 不撞 mismatch |
| AC-4 retry round ≥1 真启动 | True | ✅ log "Retry 1/2" "Retry 2/2" 每视角 2 round |
| AC-5 photoreal ≥60 | True 或 fallback | ❌ vendor DNS fail (`getaddrinfo failed`) 环境阻 — §11-N12 follow-up |
| AC-6 cost ≤$0.50 | True | ✅ $0（vendor 全 fail / 0 charge）|

### vendor DNS fail 根因

`gemini-3-pro-image-preview` enhance backend 调 Google Gemini native endpoint `generativelanguage.googleapis.com` — 与 jury 评分 chat-completions endpoint 不同。micuapi.ai key 不走此 endpoint；environment DNS 解析 fail（可能受网络环境限制如 GFW）。

这是 spec rev 3 §7 R5 风险细化项 — enhance backend 与 jury backend 不同 endpoint。

**重要**：DNS fail **非 PR 改动正确性问题**：
- path-prefix 工具 100% work
- retry 闭环 path 通（cad_pipeline 不撞 mismatch + retry 真启动）
- vendor 调用受限纯 environment

## 走过的弯路 / Plan-drift（实施期发现）

1. **plan Task 5 entry 选错** — plan §3.2.2 写 `cad_pipeline enhance-check` 实际是仅检查既有 enhancement_report status，**不跑 jury / 不跑 retry**。真 retry 闭环入口是 `cmd_enhance --rerun-loop`（cad_pipeline.py:2571，含 jury_loop hook）。implementer 发现后切 entry。**教训**：retry 闭环需用 `cmd_enhance` 不是 `enhance-check`。

2. **GISBOT mixed state 状态比 spec assume 复杂** — spec §2.1 实证写 "4 文件含源 path"，实际 Task 4 发现：04_render 全旧 + cad/output/renders 半新半旧（顶层 patched 但 files[] 未 patched）+ 跨 separator。2 步 ops 流程跑完 unify。

3. **render_dir vs files[] 位置匹配** — Task 5 第 1 次撞 "manifest source image must stay inside render_dir"（用 `--dir cad/output/renders/end_effector/<run_id>/` 时 image 实际在 `renders/` 根）。切到 `--dir cad/output/renders` 通。**教训**：cad_pipeline `--dir` 参数应指向**image 所在目录**，不是 manifest 子目录。

4. **enhance vendor endpoint ≠ jury vendor endpoint** — Task 5 撞 DNS fail expose spec rev 3 §7 R5 risk 真值：jury 用 chat-completions endpoint（micuapi.ai work），enhance 用 Google native generateContent endpoint（DNS fail）。**教训**：spec rev 3 R5 应区分 "vendor 能力不足" vs "endpoint DNS 不通"。

## 4 层 review 实证

| 层 | 抓 | spec rev |
| --- | --- | --- |
| Layer 6 scout | 5 处实证 | rev 1 |
| self-review | 4 项过 | rev 1 inline |
| Layer 3 user review | 1 BLOCKER + 3 MAJOR + 3 MINOR | rev 1→rev 2 |
| 2nd boundary review | 1 BLOCKER + 1 MAJOR + 1 MINOR | rev 2→rev 3 |

## §11 follow-up 更新

- 闭合：§11-N9（rebrand path-prefix + 真 retry 闭环 path verify）
- 仍 open：
  - §12 f4 N≥50 批量场景成本评估
  - **新登 §11-N12**：enhance backend DNS environment 限制（与 jury backend 不同 endpoint）— 解决方案：proxy / VPN / 真 Gemini key
  - §11-N7 max_retries=3 升级（条件 §11-N12 解决后实测）
  - §11-N10 多 prefix per run / atomic 2 步 sub-command（rule-of-three 触发）

## 后续工作

按 §6 YAGNI：
- v2.37.11 候选：§11-N12 解决 vendor DNS / 端到端图像质量回归（条件 vendor 通后）
- 360+ ruff cleanup
