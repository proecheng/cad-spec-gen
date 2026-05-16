# v2.37.8 — rebrand 工具 + §12 f1 doc + helper cleanup retro

> 关联 PR: TBD（Task 12 push 后填）  
> 关联 spec: docs/superpowers/specs/2026-05-16-v2-37-8-rebrand-tool-cleanup-design.md (rev 5, 577 行, commit `4661a1b`)  
> 关联 plan: docs/superpowers/plans/2026-05-16-v2-37-8-rebrand-tool-cleanup.md (commit `2cc7366`)  
> Baseline: cad-spec-gen main@`05a50a5`（v2.37.7 merge）

## 摘要

v2.37.8 闭合 §11-N1 (rebrand 工具) + §12 f1 (doc stale 标记) + helper cleanup。新建 `tools/dev/rebrand_test_archive.py` (245 行 — minimum impl) + 16 unit + 1 integration test 全 PASS / jury 子集 509 PASS / 0 regression / 全套件 3217 PASS / 18 skip。

## 完成项

### §11-N1 — `tools/dev/rebrand_test_archive.py`

- scan-all + dual-schema-aware（pattern A string / pattern B `subsystem.name` dict-nested）
- archive sentinel marker `.test-archive-marker` 防误传 production（rev 4 RISK-CRITICAL fix）
- ASCII label stderr ([DRY]/[APPLY]/[SKIP]/[WARN]/[ERROR])
- atomic write (tempfile.mkstemp + os.replace) 失败 cleanup tmp
- `_archive_*` glob + 普适开发目录 deny list (`os.walk dirnames[:]=...` 原地修剪)
- utf-8-sig BOM 兼容 / size guard 50MB / symlink 不跟 (followlinks=False)
- 9 action 状态机分发清晰
- 16 单元 + 1 GISBOT sandbox 集成测

### §12 f1 — STATUS 表 reconcile

v2.37.7 spec line 281 单行 doc fix — "未闭合（batch 3）" → "closed v2.37.2 ✓（512→1024 实证）"。§12 f4 行不动（真未闭合留 v2.37.9）。

### helper cleanup

`tools/photo3d_jury.py:498-511` main() 改用 `_resolve_effective_subsystem(args)`。顺序契约：input validation 早于 helper 调用（rev 5 B5）。零行为差异。

## 集成测先决条件

集成测自动 skip 除非：

```bash
touch D:/Work/cad-tests/GISBOT/.test-archive-marker
```

marker 不进 cad-spec-gen git；GISBOT 在仓库外。

## 走过的弯路 / Plan-drift（subagent 实施期发现）

1. **T11 `\x00` Windows subprocess null limit** — plan 写 `--from "a\x00b"`，Windows `subprocess.Popen` 抛 `ValueError: embedded null character`。改用 `\x01`（同属 `\x00-\x1f` 控制字符判定范围）规避；语义等价。**教训**：跨平台子进程 argv 不支持 NUL，但 `\x01-\x1f` OK。
2. **T12 subprocess monkeypatch 不跨进程** — plan 写 `monkeypatch.setattr(os, "replace", ...)` 配合 `_run()` subprocess 跑工具，但 subprocess 是新进程 monkeypatch 不生效。改用 `importlib.util.spec_from_file_location` 动态 import 工具模块 → `monkeypatch.setattr(mod.os, "replace", fail_replace)` → 直调 `mod._scan(arch, "old", "new", True)` 白盒。**教训**：mock IO 中断必须白盒；black-box subprocess 不能 mock 内部依赖。
3. **batch review T7 缺 case-sensitive 负向分支** — spec §3.1.7 line 342 字面要求 `_archive_ skip / _Archive_ 不 skip`，但 implementer 初版 T7 只测正向 skip + normal apply。batch review 抓 minor → Task 10 fixup 补 `_Archive_lowercase/` 大写不 skip 测试。**教训**：spec 字面承诺需逐字翻译到 test assert，不能"代码已支持就行"逻辑省略。

## 5 层 review 实证

| 层 | 抓 | spec rev |
| --- | --- | --- |
| Layer 6 scout | 7 处 drift（tools/dev 不存在 / 8 JSON / dual-schema / marker 缺 等）| rev 1→2 |
| self-review | 4 处 ambiguity（deny list 明示 / exit=0 决策 / `_archive_*` glob / tempdir copy）| rev 2 inline |
| Layer 2 cynical re-read | 8 MAJOR（atomic_write / mtime→SHA256 / ASCII label 等）| rev 2→3 |
| Layer 4 edge-case hunter | 31 cases → 17 进 spec（BOM / Windows lock / bool 子类 等）| rev 2→3 |
| Layer 3 user review | 1 RISK-CRITICAL（archive sentinel marker 防误传）| rev 3→4 |
| 2nd boundary review | 5 闭环漏洞（fixture marker / conftest 真值 / GISBOT 前置 / §12 f4 / 顺序契约）| rev 4→5 |
| Batch review | 1 minor（T7 case-sensitive 负向 assert）| Task 10 fixup |

## 测试覆盖

- 单元 16/16 PASS（T1-T16）
- 集成 1 SKIP（marker 不存在 — 用户 ops `touch` 后可手跑）
- jury 子集 509 PASS / 0 regression
- 全套件 3217 PASS / 18 skip / 0 regression（baseline v2.37.7 = 3084 PASS）

## §11 follow-up 更新

- 闭合：§11-N1 / §12 f1 / helper cleanup
- 仍 open：§12 f4 N≥50 批量场景成本评估（留 v2.37.9）
- 新登（v2.39 候选）：
  - exit code 语义重审（partial-write skip exit=0 vs exit=1）
  - `tools/dev/_common.py` rule-of-three 触发再抽（atomic_write / glob skip / dual-schema-aware）
  - `--help` Windows GBK mojibake（中文 description/epilog 显示乱码）

## 后续工作

按 §6 YAGNI：
- v2.37.9 候选：§12 f4 / 真 AI adapter / 端到端图像回归
