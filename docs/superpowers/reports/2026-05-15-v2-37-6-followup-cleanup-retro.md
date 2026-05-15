# Retro — v2.37.6 §11-N5 + §12 f2 cleanup（含 §11-N4 重新评估）

**完工日期：** 2026-05-15
**Spec：** `docs/superpowers/specs/2026-05-15-v2-37-6-followup-cleanup-design.md`（213 行 / brainstorming F1+F2 + layer 6 E1+E2+E10+E3+E5+E4 fix）
**Plan：** `docs/superpowers/plans/2026-05-15-v2-37-6-followup-cleanup.md`（655 行 / 8 task）
**Baseline：** cad-spec-gen main@`2ab0003`（GISBOT e2e merge）

## 一句话

闭合 §11-N5（jury 估价表加 gpt-image entry $0.010/call，production list + doc mirror 同步）+ §12 f2（CLAUDE.md 加 memory 引用约定）；§11-N4 重新评估为非 bug（mojibake 是 client cp936 vs utf-8 显示问题，jury report 本身 UTF-8 正确）。

## 完工范围

- **§11-N5 closed**：`tools/jury/config.py:48` 插 `("gpt-image", 0.010)` tuple + `tests/jury/test_config.py::test_cost_lookup_gpt_image` 3 assertion TDD 测试 + `docs/cad-jury-config.md §4` 表同步 entry
- **§12 f2 closed**：`CLAUDE.md` 加 `## memory 引用约定` 节（≤20 字符 inline 摘要 / 仅未来生效 / 新旧格式兼容）
- **§11-N4 drop**：retro 沉淀"非 production bug，client 环境问题"+ 字节级 verify lesson

## 数字（实测）

- test_config.py PASS：26 → **27**（+1 `test_cost_lookup_gpt_image`）
- jury 子集 PASS：503 → **504** / 6 skipped / 0 regression
- 全套件 PASS：3193 → 3194
- 元测试 5 PASS 不变（CLAUDE.md 加节不影响 AGENTS.md regen，v2.37.5 实证再现）
- diff stat：`tools/jury/config.py` +1 / `tests/jury/test_config.py` +9 / `docs/cad-jury-config.md` +1 / `CLAUDE.md` +24 / retro ~120 = **~155 行**
- 3 commits（feat / docs / retro）
- CI 8/8 SUCCESS（待 PR 后实测）

## 关键发现 — Layer 6 E1 揭示 production scope 漂移

**原 spec 假设**：纯 docs PR（仅改 `cad-jury-config.md §4` markdown 表）。

**Layer 6 grep `tools/jury/config.py:45-186` 揭示**：
- `BUILTIN_MODEL_COST_USD: list[tuple[str, float]]`（line 45-54，实有 **8 entries**，spec 假设 5 项也错）是 production 真实查表源
- `lookup_builtin_cost`（line 184-189）按 list 行序 first-match
- `cad-jury-config.md §4 表`是**人类可读 mirror**，单改 doc 不影响 jury 查表行为

**修复**：spec scope 翻倍：
- 加 production change：`tools/jury/config.py:48` 插 1 tuple
- 加测试覆盖：`tests/jury/test_config.py::test_cost_lookup_gpt_image` 3 assertion
- doc mirror 同步：`cad-jury-config.md §4` 加同步 entry
- 总 diff ~155 行（原假设 ~20 行 docs only）

**Lesson 沉淀**：spec 写"加 entry/字段"前必 grep 实际 production code 看是 doc-only 还是 doc-as-mirror。下次 cleanup PR brainstorming 阶段问"这是 docs 改还是 doc-as-mirror 双改？"

## §11-N4 重新评估说明

**GISBOT retro 当时报告**：jury report `ordinary_user_message` 字段含 mojibake `"(��� stderr ������ʾ)"`，假定 jury production 跨平台 stderr 捕获 bug。

**本 PR 重新 cat 实测**：jury report `ordinary_user_message` 字段实际 UTF-8 真值 `"(详见 stderr 中文提示)"`（`tools/photo3d_jury.py:693` 写死兜底 message，纯中文 UTF-8）。

**真相**：implementer 之前看到的 mojibake 是 Windows 控制台默认 cp936 读 utf-8 JSON 显示乱码（client 端编码问题），jury 写盘 JSON 本身 UTF-8 正确。

**Lesson**：报 production bug 前先 `cat -A` 或 `python -c "import json; print(repr(json.load(open(...))['field']))"` 实测字节，不只看控制台显示（控制台编码可能与文件编码不一致）。

## 审查矩阵

| Layer | findings | inline 修 | 接受 |
|---|---|---|---|
| brainstorming F1+F2 fact-check | 2 | 2 | 0 |
| layer 6 边界 + 闭环 | 10 | 4 合（E1+E2+E10+E3+E5+E4）| 6 |
| per-task spec+quality review × 3 task | 0 阻断（Task 1+2 / Task 3+4 都 ✅）| 0 | 0 |
| **总** | **12** | **6** | **6** |

## 沉淀 lessons

1. **layer 6 grep 揭示 doc-as-mirror 漂移**（layer 6 E1 实证）：spec 假定纯 docs PR；grep production 揭示 doc 是 mirror，必须同步改 production list。Lesson：spec 写"加 entry/字段"前必 grep 实际查表/解析逻辑代码。
2. **TDD RED→GREEN 仍是小 production change 的纪律**（Task 1+2）：1 行 list insert 也走完整 RED→GREEN→REFACTOR；防"小改不测试"陷阱。
3. **报 production bug 前 cat -A 实测字节**（§11-N4 重新评估）：控制台显示乱码 ≠ 文件含乱码；Windows cp936 vs utf-8 默认不一致是常见误判源。
4. **profile 显式值 vs default 表项分层**（spec §3.1 D1 + E2+E10）：jury cost 公式 = profile 显式 > §4 表 default > exit reject。本 PR 加 entry 仅影响"未显式填 cost 的新用户"；既有显式 profile 零影响。
5. **≤20 字符（明示非字节）+ 新旧格式兼容**（spec §3.3 D3 + E4+E3+E5）：约定写跨语言（含中文）UI 文本时必明示 char vs byte；新约定与既有写法兼容声明防"格式迁移焦虑"。
6. **BUILTIN_MODEL_COST_USD 8 entries vs doc §4 5 行 glob 折叠**（Task 0 scout 实证）：spec 写假设数字时必 sed -n 实测，特别是带 glob 折叠的 doc mirror 场景；layer 6 R5 D2 教训"行号 snapshot；plan 实测"扩展到"列表长度也是 snapshot"。

## §11 + §12 follow-up 表（本 PR 闭合后）

| 项 | 状态 |
|---|---|
| §12 F1/F2/f3/f5/f6 | closed v2.37.3-v2.37.5 ✓ |
| **§12 f2** memory inline 摘要 | **closed v2.37.6 ✓** |
| §12 f1 / f4 | 未闭合（下次 batch）|
| **§11-N5** 估价表 gpt-image | **closed v2.37.6 ✓** |
| §11-N4 stderr mojibake | **drop（非 production bug，client cp936 显示问题）✓** |
| §11-N1 rebrand 工具 | 未闭合（batch 3）|
| §11-N2 jury --override-subsystem | 未闭合（batch 2 / v2.37.7）|
| §11-N3 jury per-view 进度 | 未闭合（batch 2 / v2.37.7）|

## 下次类似 PR 优化

- spec 写"加 entry/字段"前必 grep production 代码看是 doc-only 还是 doc-as-mirror
- TDD 小 production change 也走完整 RED→GREEN→REFACTOR
- 报 production bug 前 cat -A / python repr() 字节级验证
- 跨语言文本字段约定明示 char vs byte 单位
- profile 显式值 vs default 分层逻辑 spec 必明示
- 带 glob 折叠的 doc mirror 列表长度也是 snapshot；Task 0 实测重计数

[[project-gisbot-jury-e2e-done]] 上游 §11-N5 / N4 来源追溯。
[[project-v2-37-5-done]] §12 f3 glossary 追溯。
