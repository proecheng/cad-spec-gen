# v2.37.10 — rebrand path-prefix 扩 + 真 retry 闭环实测（§11-N9）设计

> **PR 类型**：feat + integration test（中体量，~1.5h + ~$0.50 budget）  
> **关联 STATUS doc**：`docs/superpowers/JURY_MATCHES_SPEC_STATUS.md`（§11 follow-up）  
> **关联 v2.37.9 retro**：`docs/superpowers/reports/2026-05-16-v2-37-9-jury-retry-real-vendor-retro.md`（§11-N9 新登出处）  
> **Spec rev**：rev 1

---

## 1. 摘要

闭合 v2.37.9 retro §11-N9 — v2.37.8 rebrand 工具 scope 不足（仅改 subsystem 字段，未改 path 字段）导致真 retry 闭环实测撞 `render_dir mismatch` block。

| 项 | 严重度 | 内容 | 工作量 |
| --- | --- | --- | --- |
| **§11-N9 改动 1** | LOW | v2.37.8 `tools/dev/rebrand_test_archive.py` 扩 `--from-path-prefix` + `--to-path-prefix` 互锁 flag；字符串 startswith 替换 path prefix；递归扫嵌套 list[dict] | ~40min |
| **§11-N9 改动 2** | LOW | 真 retry 闭环实测 — `cad_pipeline enhance-check` 端到端跑 + jury 重评 + photoreal 验收 | ~30min + ~$0.50 |
| **§11-N9 实测** | — | retry 后 photoreal ≥60 / status=accepted | AC-5 |

---

## 2. 背景

### 2.1 v2.37.9 实测 expose v2.37.8 工具 scope 不足

2026-05-16 GISBOT 真 vendor 实测 expose 真闭环 block：

```
[ERROR] Render directory mismatch:
  CLI --dir=D:\Work\cad-tests\GISBOT\cad\output\renders\end_effector\20260513T115709Z
  manifest render_dir=D:\Work\cad-spec-gen\cad\output\renders  ← v2.37.7 生成时源路径未 rebrand
```

scout grep 实证 4 文件含 `D:\Work\cad-spec-gen` 源路径：

- `02_codegen/CUSTOM_PARTS_AUDIT.json`
- `04_render/render_manifest.json`
- `cad/output/renders/end_effector/<run_id>/render_manifest.json`
- `cad/output/renders/render_manifest.json`

render_manifest 内 path 字段类型分两类：

**A. abs 路径字段（hardcode 源 — 需 rebrand）**：

- `render_dir`
- `render_dir_abs_resolved`
- `files[].path_abs_resolved` × 7 视角

**B. rel 路径字段（不需改 — 副本相同）**：

- `render_dir_rel_project` (= `cad/output/renders`)
- `product_graph_path` / `model_contract_path` / `glb_path` 等
- `files[].path_rel_project`

**~140 path values 需 rewrite，但本质是单一 prefix 替换**（`D:\Work\cad-spec-gen` → `D:\Work\cad-tests\GISBOT`）。

### 2.2 v2.37.9 PR 仅跑 photo3d_jury 单独评分

v2.37.9 PR 因 path 字段 block 无法跑 cad_pipeline enhance-check 全 pipeline。临时绕过路径走 `python -m tools.photo3d_jury` 单独入口验改动 1+1e+1f 决策路径（verdict 升 needs_review），但**真 retry round 未启动**。

PR 主目的（让 photoreal<60 触发 retry）决策路径闭环 ✅ 但**最终质量提升未实测**（vendor 能否把 photoreal=35-45 升到 ≥60 未知）。

v2.37.10 闭环此 gap。

---

## 3. 设计

### 3.1 改动 1 — `tools/dev/rebrand_test_archive.py` 扩 path-prefix

#### 3.1.1 CLI 接口

```bash
python tools/dev/rebrand_test_archive.py <archive_dir> \
  --from <old_subsystem> --to <new_subsystem> \
  [--from-path-prefix <old_prefix>] [--to-path-prefix <new_prefix>] \
  [--apply]
```

| flag | required | 说明 |
| --- | --- | --- |
| `<archive_dir>` | ✓ | 测试归档目录（v2.37.8 既有）|
| `--from <old>` | ✓ | subsystem 字面值（v2.37.8 既有）|
| `--to <new>` | ✓ | subsystem 目标值（v2.37.8 既有）|
| `--from-path-prefix <old>` | optional | 当前 abs path 前缀（如 `D:\Work\cad-spec-gen`）|
| `--to-path-prefix <new>` | optional | 目标 abs path 前缀（如 `D:\Work\cad-tests\GISBOT`）|
| `--apply` | optional | 真改写（v2.37.8 既有）|

#### 3.1.2 行为

```
input validation 扩（不变量 #12）:
  if --from-path-prefix 给但 --to-path-prefix 缺 → exit=2
  if --to-path-prefix 给但 --from-path-prefix 缺 → exit=2
  if --from-path-prefix == --to-path-prefix → exit=2 (same as v2.37.8 from==to 校验风格)
  
  # 特殊：T-prefix-E 语义
  if args.from_ == args.to AND --from-path-prefix 给 → 允许（仅 path rewrite，skip subsystem rewrite）
  if args.from_ == args.to AND --from-path-prefix 缺 → exit=2 (v2.37.8 既有错误 'from/to must differ')

扫描行为（v2.37.8 既有 scan-all 上扩 path-prefix replace）:
  对每 *.json 文件:
    解析 dict
    递归扫所有 string value（含 nested dict / list[dict]）:
      if value.startswith(args.from_path_prefix + path_sep) OR value == args.from_path_prefix:
        new_value = args.to_path_prefix + value[len(args.from_path_prefix):]
        替换 + log [DRY] / [APPLY]
    subsystem rewrite（v2.37.8 既有，跳过若 from==to）
  
  atomic write + ASCII label stderr（v2.37.8 既有）
```

#### 3.1.3 prefix 匹配规则（R1 防越界）

**仅前缀紧跟路径分隔符 (`\`, `/`) 或字符串 end 才匹配**：

- `"D:\Work\cad-spec-gen\cad\output\..."` 匹配 prefix `"D:\Work\cad-spec-gen"`（紧跟 `\`）→ rewrite
- `"D:\Work\cad-spec-gen-backup\..."` **不**匹配 prefix `"D:\Work\cad-spec-gen"`（紧跟 `-`，非分隔符）→ skip
- `"D:\Work\cad-spec-gen"`（exact match end）→ rewrite

Python 实现：

```python
def _matches_prefix(s: str, prefix: str) -> bool:
    if s == prefix:
        return True
    if s.startswith(prefix):
        rest_first_char = s[len(prefix):][:1]
        return rest_first_char in ("\\", "/")
    return False
```

#### 3.1.4 不变量

v2.37.8 既有 11 条不变量保留，新加：

12. `--from-path-prefix` 与 `--to-path-prefix` 互锁（必同时给或同时缺）；缺 = v2.37.8 既有行为
13. path-prefix replace **仅 string value**；不动 path 字段名 / key 名
14. prefix 边界匹配（仅紧跟路径分隔符或 end-of-string）防越界匹配 `cad-spec-gen-backup` 等近似命名

#### 3.1.5 测试设计（TDD — 7 unit）

| # | 测试 | 断言 |
| --- | --- | --- |
| T-prefix-A | string 字段含 prefix 真替换 | `{"render_dir": "D:\\Work\\cad-spec-gen\\..."}` + prefix flag → 改为 `D:\\Work\\GISBOT\\...` |
| T-prefix-B | dict-nested subsystem.name **不**触发 path-prefix | `{"subsystem": {"name": "end_effector"}}` + path flag → subsystem 改但 name 不被当 path 解释 |
| T-prefix-C | 嵌套 list[dict] 递归改 | `{"files": [{"path_abs_resolved": "D:\\Work\\cad-spec-gen\\f.png"}]}` → 数组内 path 改 |
| T-prefix-D | 缺 from-path-prefix 仅给 to-path-prefix → exit=2 | 互锁校验 |
| T-prefix-E | from==to (subsystem) + 给 path-prefix → 允许（skip subsystem rewrite）| 仅 path rewrite |
| T-prefix-F | from==to (subsystem) + 不给 path-prefix → exit=2 | v2.37.8 既有校验保留 |
| T-prefix-G | idempotent rerun | path 改完 二次跑零写盘 |
| T-prefix-H | prefix 边界匹配 `cad-spec-gen-backup` **不**改 | R1 fix |
| T-prefix-I | exact match end-of-string `"D:\\Work\\cad-spec-gen"` 改 | 边界 R1 fix |

预计 9 新 unit test（T-prefix-A through T-prefix-I）。

### 3.2 改动 2 — 真 retry 闭环实测

#### 3.2.1 前置 ops

```bash
# 1. touch sentinel marker（v2.37.8 §3.1.0 契约 — v2.37.9 已 touched）
ls -la D:/Work/cad-tests/GISBOT/.test-archive-marker

# 2. v2.37.10 改动 1 path-prefix rebrand
python tools/dev/rebrand_test_archive.py D:/Work/cad-tests/GISBOT \
  --from end_effector --to end_effector \
  --from-path-prefix "D:\\Work\\cad-spec-gen" \
  --to-path-prefix "D:\\Work\\cad-tests\\GISBOT" \
  --apply
# 注：subsystem from/to 同（T-prefix-E）= skip subsystem，仅 path rewrite

# 3. env vars
export GEMINI_API_KEY=<micuapi key>  # 同 v2.37.9 实测 vendor
export PYTHONPATH=D:/Work/cad-spec-gen
```

#### 3.2.2 跑 enhance-check 端到端

```bash
cd D:/Work/cad-tests/GISBOT
python D:/Work/cad-spec-gen/src/cad_spec_gen/data/python_tools/cad_pipeline.py \
  enhance-check --subsystem end_effector \
  --dir cad/output/renders/end_effector/20260513T115709Z \
  2>&1 | tee /tmp/v2-37-10-real-retry.log
```

**预期行为**：

- 不再撞 `render_dir mismatch` block（path-prefix 已 rebrand）
- jury 初评 verdict=needs_review（v2.37.9 已 verify）
- orchestrator 触发 retry round（v2.37.9 改动 1b/1f 已 wire）
- enhance vendor 重渲（用 micuapi.ai 同 backend / kind=openai_compat 或 image-gen path）
- 重评 jury / `_pick_best` 选高分

#### 3.2.3 验收 AC（α option）

- **AC-4** retry round ≥1 真启动（jury_review_input.json 含 retry round 记录）
- **AC-5** retry 后 photoreal ≥60 / view verdict=accepted
- **AC-5 fallback**（v2.37.9 §7 R7 不退步）：vendor 能力不足 photoreal 未达 60 → 不阻 PR / retro 记 / §11-N7 follow-up 调 max_retries=3
- **AC-6** cost ≤ $0.50

---

## 4. 不变量

1. 北极星 5 gate 不破坏
2. v2.37.8 既有 11 条不变量保留
3. 新加不变量 #12 #13 #14（§3.1.4）
4. canonical/mirror 同步：dev_sync `--check` PASS
5. v2.37.9 既有 retry 决策路径不变（仅扩 rebrand 工具 + 实测）

---

## 5. 验收（AC）

| AC | 期望 | 验证 |
| --- | --- | --- |
| AC-1 | rebrand 工具加 `--from-path-prefix` + `--to-path-prefix` 互锁 flag | grep argparse |
| AC-2 | 9/9 unit test PASS（T-prefix-A 到 I）| `pytest tests/dev/test_rebrand_test_archive.py -v` |
| AC-3 | path-prefix rewrite 后 cad_pipeline enhance-check 不再撞 mismatch | 实测 |
| AC-4 | 真 retry round ≥1 启动 | jury_review_input.json |
| AC-5 | retry 后 photoreal ≥60 / status=accepted（或 fallback 不退步）| 实测 + cat report |
| AC-6 | cost ≤ $0.50 | 实测 |
| AC-7 | jury+jury_loop 子集 0 regression | pytest |
| AC-8 | 全套件 3228+ PASS / 0 regression | pytest |
| AC-9 | CI 8/8 SUCCESS | gh pr checks |
| AC-10 | dev_sync `--check` PASS | shell |

---

## 6. 范围（YAGNI）

**做**：
- rebrand 工具扩 2 互锁 flag + 9 新 unit test
- 真 retry 闭环实测（α 验收 photoreal ≥60）
- retro 文档（含实测真值）

**不做**（留下批）：
- 跨副本批处理（仅 1 prefix per run）
- path 字段 audit log（dry-run 已 enough）
- subsystem rename 自动同 path-prefix（user 显式给 prefix 更可控）
- `tools/dev/_common.py` rule-of-three（仍未触发）
- §11-N7 max_retries=3（条件 AC-5 fail 后才调）

---

## 7. 风险

| # | 风险 | 缓解 |
| --- | --- | --- |
| R1 | string.startswith() 越界匹配 `cad-spec-gen-backup` | 不变量 #14 边界匹配 + T-prefix-H/I 测试硬保 |
| R2 | sha256 字段被误改 | hash value 不含 path prefix 自然 skip；不变量 #13 仅替换 prefix 命中 string |
| R3 | Windows `\\` vs `/` path separator 不一致 | 不变量 #14 接受任一分隔符；保留原字段 separator 风格 |
| R4 | retry 闭环 vendor 能力不足（photoreal 未达 60）| v2.37.9 §7 R7 不退步 + AC-5 fallback / retro 记录 + §11-N7 follow-up |
| R5 | enhance retry backend 路径与 jury vendor 不同（image-gen vs vision LLM）| 用 micuapi.ai 同 key 同 endpoint（v2.37.9 实测验证可达）|

---

## 8. follow-up

| 项 | 状态 |
| --- | --- |
| §11-N9 改动 1+2 | closed v2.37.10 ✓（本 PR）|
| §12 f4 | LOW 留 v2.37.11 |
| §11-N7 max_retries=3 | 条件 AC-5 fail 后做 |
| 新登 §11-N10（条件触发）| dev 工具批量多 prefix（YAGNI 直到第 2 用例）|

---

## 9. Layer 6 scout 实证

| Scout | 假设 | 实证 |
| --- | --- | --- |
| A | 4 文件含 `D:\Work\cad-spec-gen` 源 path | ✓ scout 实证（grep -rln cad-spec-gen --include=*.json）|
| B | render_manifest abs 字段 = render_dir / render_dir_abs_resolved / files[].path_abs_resolved | ✓ scout 实证 |
| C | rel 字段 = path_rel_project / product_graph_path 等不需改 | ✓ scout 实证 |
| D | v2.37.8 工具 `--from == --to` 校验 exit=2 | ✓ 既有 spec §3.1.4 |
| E | v2.37.9 已 touched `.test-archive-marker` | ✓ shell 实证 |

无 plan-drift（rev 1 scout 同时跑过 — 关键 path 字段已实证 4 文件含 prefix）。

---

## 10. 关联文档

- v2.37.8 spec: `docs/superpowers/specs/2026-05-16-v2-37-8-rebrand-tool-cleanup-design.md`（rev 5, 577 行）
- v2.37.9 spec: `docs/superpowers/specs/2026-05-16-v2-37-9-jury-retry-real-vendor-design.md`（rev 4, 509 行）
- v2.37.9 retro: `docs/superpowers/reports/2026-05-16-v2-37-9-jury-retry-real-vendor-retro.md`（§11-N9 新登出处）
- rebrand 工具：`tools/dev/rebrand_test_archive.py`（v2.37.8 引入，245 行）
