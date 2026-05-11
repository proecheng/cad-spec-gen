# CP-6 photo3d-jury CLI --single-view + --image 实施 plan

**parent**: `docs/superpowers/plans/2026-05-10-jury-prompt-loop-plan.md` Task 6.1（line 1256）
**parent spec**: `docs/superpowers/specs/2026-05-10-jury-prompt-loop-design.md` §6（line 638）
**branch**: `feat/sp1-cp6-jury-cli-single-view` / base main@`3e71086` (v2.32.2)

## 范围

3 task，inline TDD（task 之间高耦合不派 subagent）。

| Task | Files | 说明 |
|---|---|---|
| 6.1.1 | `tools/photo3d_jury.py:_build_parser` + `tests/jury_loop/test_jury_cli_single_view.py` | 加 `--single-view` + `--image` 两 flag（argparse.SUPPRESS） |
| 6.1.2 | `tools/photo3d_jury.py:main` + 测试 | `--single-view` 分支：剥 Layer 0 / cost gate / batch iter，调 LLM → stdout JSON list |
| 6.1.3 | `tools/jury_loop/orchestrator.py:_call_jury_subprocess` + `tests/jury_loop/test_orchestrator.py` | `subprocess.run(capture_output)` → `Popen` + 1 MiB MAX_STDOUT_BYTES（SEC-MINOR-4），超出 kill 子进程返新 error_code `stdout_overflow` |

## Task 6.1.1：CLI flag 注册

**RED 测试**（`tests/jury_loop/test_jury_cli_single_view.py`）：
1. `--single-view V1 --image baseline.jpg --subsystem dummy --config <path>` argparse parse 成功，`args.single_view == "V1"`、`args.image == ["baseline.jpg"]`
2. `--single-view V1 --subsystem dummy --config <path>` 缺 `--image` → argparse error（SystemExit 2）
3. 帮助文本不含 "single-view" 和 "image"（argparse.SUPPRESS 验证）

**GREEN 实现**（`_build_parser`）：
- `p.add_argument("--single-view", help=argparse.SUPPRESS)`
- `p.add_argument("--image", nargs="+", help=argparse.SUPPRESS)`
- `--image` 在 `--single-view` 时必填靠 main() 自定义校验（argparse `required=` 与 `--list-profiles` 等其他 mode 不兼容）

**验收**：3 测试 GREEN / ruff / mypy strict

**Commit**：`feat(jury-cli): _build_parser 加 --single-view + --image flag（SUPPRESS）（CP-6 Task 6.1.1）`

---

## Task 6.1.2：main() --single-view 分支

**位置**：在 `load_jury_config` 之后、`Layer 0` 之前插入 `if args.single_view:` 分支。

**契约**：
- `--single-view <V> --image <p1> [<p2> ...]` 跳过 Layer 0 / cost gate / batch / 写盘
- 遍历 `--image` 列表，每张图调 LLM（复用 `tools.jury.llm_client`）→ 解析 `parse_view_verdict` → 收集 dict
- stdout 输出 `json.dumps(list[verdict_dict])`；stderr 仅 log（不混 stdout）
- `--image` 缺失 / 空列表 → stderr error，exit code 2
- LLM 调用异常（network / parse failure）→ verdict.verdict = "needs_review" 写入 list，exit code 0（调用方按 needs_review 走 jury_unavailable）
- view 名注入防护：`metadata._validate_view_basename(args.single_view)` 失败 → stderr error，exit code 2

**RED 测试**（同文件 4 case）：
1. **single 图正常**：`--single-view V1 --image base.jpg` mock LLM 返 JSON verdict → stdout list 1 元素 / exit 0
2. **batch 2 图**：`--single-view V1 --image a.jpg b.jpg` mock LLM 返 2 次 → stdout list 2 元素 / exit 0
3. **缺 --image**：`--single-view V1` 无 `--image` → stderr error / exit 2
4. **LLM needs_review**：mock LLM 抛 LlmParseError → verdict.verdict = "needs_review"，exit 0 + list 含 needs_review verdict

**GREEN 实现**：~30-50 行 main() 内分支 + 1 helper（避免 main 复杂度爆炸）

**验收**：4 测试 GREEN / 全套件 0 regression / ruff / mypy strict

**Commit**：`feat(jury-cli): main() --single-view 分支调 LLM 输出 stdout JSON list（CP-6 Task 6.1.2）`

---

## Task 6.1.3：orchestrator subprocess 升级 Popen + 1 MiB read limit（SEC-MINOR-4）

**位置**：`tools/jury_loop/orchestrator.py:_call_jury_subprocess`

**契约升级**：
- `subprocess.run(capture_output=True)` → `subprocess.Popen(stdout=PIPE, stderr=PIPE)` + 循环 `read(64*1024)` 累计 ≤ 1 MiB
- 超 1 MiB → `proc.kill()` + 返 `(None, "stdout_overflow")` 走 jury_unavailable
- 新增 error_code 常量 `_ERROR_CODES = {"timeout", "exit_nonzero", "json_parse_failed", "needs_review", "stdout_overflow"}` （或直接列在 docstring）

**RED 测试**：现 test_orchestrator.py 加 1 case
- mock subprocess.Popen 返 stdout > 1 MiB → assert orchestrator 返 `loop_status = jury_unavailable` + `errors[].code` 含 `stdout_overflow`

**GREEN 实现**：~15-25 行替换 subprocess.run

**验收**：测试 GREEN / jury_loop 234 ≥ passing / 全套件 0 regression / mypy strict

**Commit**：`feat(jury-loop): orchestrator subprocess Popen + 1 MiB read limit（SEC-MINOR-4，CP-6 Task 6.1.3）`

---

## 收尾

- 跑 jury_loop 套件 + 全套件
- ruff + mypy strict
- 开 PR base=main
- 等 CI 8/8 → squash merge → tag v2.33.0 + Release

## §11 跟进（不阻断本 PR）

- photo3d_jury.py 现有 `noqa: C901,PLR0911,PLR0912,PLR0915` 复杂度告警进一步降低（CP-7 / CP-8 收）
- spec §6 line 690 "subprocess.Popen + manual read(MAX_STDOUT_BYTES) 循环" 文字可以再加 error_code `stdout_overflow` 字段（本 PR Task 6.1.3 commit message 备注即可）
