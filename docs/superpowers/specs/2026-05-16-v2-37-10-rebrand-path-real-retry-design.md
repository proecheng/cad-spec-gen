# v2.37.10 — rebrand path-prefix 扩 + 真 retry 闭环实测（§11-N9）设计

> **PR 类型**：feat + integration test（中体量，~1.5h + ~$0.50 budget）  
> **关联 STATUS doc**：`docs/superpowers/JURY_MATCHES_SPEC_STATUS.md`（§11 follow-up）  
> **关联 v2.37.9 retro**：`docs/superpowers/reports/2026-05-16-v2-37-9-jury-retry-real-vendor-retro.md`（§11-N9 新登出处）  
> **Spec rev**：rev 3（rev 1 user review + rev 2 fix + rev 3 第二轮边界审查抓 1 BLOCKER + 1 MAJOR + 1 MINOR cascade fix）

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

scout grep 实证 4 文件含 `D:\Work\cad-spec-gen` 源路径（**rev 2 D2 修正**：v2.37.9 实测后 GISBOT 处于 **mixed state** — ad-hoc patched 不完整 + 跨 separator）：

- `02_codegen/CUSTOM_PARTS_AUDIT.json` — 全 hardcode `D:\Work\cad-spec-gen`
- `04_render/render_manifest.json` — 全 hardcode `D:\Work\cad-spec-gen`（未 ad-hoc patch）
- `cad/output/renders/render_manifest.json` — 顶层 `render_dir/render_dir_abs_resolved` ad-hoc patched 用 `/` separator → `D:/Work/cad-tests/GISBOT`；`files[].path_abs_resolved` 仍 hardcode `D:\Work\cad-spec-gen` 用 `\`
- `cad/output/renders/end_effector/<run_id>/render_manifest.json` — 同上 mixed
- 4 文件涉 ~140 path values；**至少 2 个不同 source prefix**（`D:\Work\cad-spec-gen` + `D:/Work/cad-tests/GISBOT`）+ 跨 separator

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

**关键 BLOCKER fix（rev 2 D1）**：v2.37.8 `_validate_inputs(args_from, args_to)` 含 path-separator block (`if "/" in val or "\\" in val: exit=2`)；若**复用**既有函数，path prefix value 必含 `\` 必 exit=2。**rev 2 加独立 `_validate_path_prefix` helper**，不复用既有函数。

```
独立 _validate_path_prefix(archive_dir, from_prefix, to_prefix, from_subsystem, to_subsystem) -> int:
  # rev 3 B1 fix：base validations 必先跑（不绕过 v2.37.8 sentinel 安全闸门）
  if not archive_dir.is_dir(): → exit=2 "not a directory"
  if not (archive_dir / _ARCHIVE_MARKER).is_file(): → exit=2 "archive_dir missing .test-archive-marker"
  
  # 互锁校验（不变量 #12）:
  if (from_prefix is None) != (to_prefix is None) → exit=2  # 必须同时给或同时缺
  
  if from_prefix is None:  # 都缺 — 复用 v2.37.8 既有 _validate_inputs subsystem 校验
    # _validate_inputs 含 from!=to / 空 / 控制字符 / 路径分隔符 5 条 subsystem 专用校验
    return _validate_inputs(...)  # 既有逻辑（含 archive_dir/marker 跑了 2 次但 idempotent）
  
  # 都给 path-prefix：
  if not from_prefix or not to_prefix: → exit=2 "must be non-empty"
  if from_prefix == to_prefix: → exit=2 "must differ"
  
  # 不变量 #15 (rev 2 D4)：prefix 须含 drive letter + colon 防误匹配 rel path
  if not _looks_like_abs_path(from_prefix): → exit=2 "from-path-prefix must start with drive letter (e.g. D:/, C:\\)"
  if not _looks_like_abs_path(to_prefix): → exit=2 "to-path-prefix must start with drive letter"
  
  # subsystem 校验（除 from==to）— rev 3 B1 fix：不 early return，按需校验
  if from_subsystem != to_subsystem:
    # subsystem 真 rewrite，仍跑 v2.37.8 subsystem 5 条校验（控制字符 / 路径分隔符 / 等）
    # 注意：archive_dir / marker 已在上面跑过，跑 _validate_inputs 时再跑 2 次但 idempotent OK
    sub_rc = _validate_inputs(...)
    if sub_rc != 0: return sub_rc
  # else from==to: T-prefix-E 语义 — skip subsystem rewrite 但 base validations 已在 #B1 fix 跑完
  
  return 0  # 全过


def _looks_like_abs_path(p: str) -> bool:
    \"\"\"rev 2 D4 — abs path 须以 drive letter (e.g. C: D:) 开头。\"\"\"
    return len(p) >= 2 and p[1] == ":" and p[0].isalpha()

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

#### 3.1.3 prefix 匹配规则（R1 防越界 + rev 2 D3 跨 separator）

**仅前缀紧跟路径分隔符 (`\`, `/`) 或字符串 end 才匹配**；**跨 separator 兼容**（value 含 `/` 但 prefix 用 `\` 仍能匹配）：

- `"D:\Work\cad-spec-gen\cad\..."` 匹配 prefix `"D:\Work\cad-spec-gen"`（紧跟 `\`）→ rewrite，输出保持 `\` separator
- `"D:/Work/cad-spec-gen/cad/..."` 匹配 prefix `"D:\Work\cad-spec-gen"`（normalize 后等价；紧跟 `/`）→ rewrite
- `"D:\Work\cad-spec-gen-backup\..."` **不**匹配（紧跟 `-` 非分隔符）→ skip
- `"D:\Work\cad-spec-gen"`（exact match end）→ rewrite

Python 实现（rev 2 D3 跨 separator）：

```python
def _normalize_path(p: str) -> str:
    \"\"\"统一 separator 到 `\\` 用于匹配比较（仅内部用，不写回）。\"\"\"
    return p.replace("/", "\\")


def _matches_prefix(value: str, from_prefix: str) -> bool:
    \"\"\"prefix 匹配 — 跨 separator 兼容 + 边界紧跟 / 或 \\。\"\"\"
    v_norm = _normalize_path(value)
    p_norm = _normalize_path(from_prefix)
    if v_norm == p_norm:
        return True
    if v_norm.startswith(p_norm):
        rest_first_char = v_norm[len(p_norm):][:1]
        return rest_first_char == "\\"  # normalized 后只判 \
    return False


def _rewrite_prefix(value: str, from_prefix: str, to_prefix: str) -> str:
    \"\"\"prefix replace — 保留 value 原 separator 风格。\"\"\"
    # 判 value 主用 separator
    sep = "/" if value.count("/") > value.count("\\") else "\\"
    p_norm = _normalize_path(from_prefix)
    v_norm = _normalize_path(value)
    new_v = _normalize_path(to_prefix) + v_norm[len(p_norm):]
    return new_v.replace("\\", sep) if sep == "/" else new_v
```

#### 3.1.4 不变量

v2.37.8 既有 11 条不变量保留，新加：

12. `--from-path-prefix` 与 `--to-path-prefix` 互锁（必同时给或同时缺）；缺 = v2.37.8 既有行为
13. path-prefix replace **仅 string value**；不动 path 字段名 / key 名
14. prefix 边界匹配（仅紧跟路径分隔符或 end-of-string）防越界匹配 `cad-spec-gen-backup` 等近似命名；跨 separator 兼容（`/` vs `\\`）
15. **path-prefix 必须以 drive letter + colon 开头**（如 `D:\\`, `C:/`）；防误匹配 rel path 含 `cad-spec-gen` 字面（如 `model_contract_path: cad/end_effector/.cad-spec-gen/...`）
16. **`_validate_path_prefix` 独立 helper**，不复用 v2.37.8 既有 `_validate_inputs`（含 path-separator block 与 prefix value 冲突）
17. **rev 3 B1 fix**：`_validate_path_prefix` 必先跑 base validations（archive_dir.is_dir / sentinel marker），不绕过 v2.37.8 安全闸门；subsystem skip 仅跳 subsystem 校验不跳基础
18. **rev 3 B9 cascade**：path rewrite 后 `path_context_hash` / 类似 sha 字段失效；本 PR 不重算 sha；下游 cad_pipeline 若严格校验 sha → fail 时进 §8 follow-up `§11-N11 sha 重算`（条件触发：实测 fail）

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

#### 3.2.1 前置 ops（rev 2 D6 mixed state 2 步流程）

GISBOT 当前 mixed state（v2.37.9 ad-hoc patched 不完整 + 跨 separator）。2 步 unify + rebrand：

```bash
# 1. touch sentinel marker（v2.37.8 §3.1.0 契约 — v2.37.9 已 touched）
ls -la D:/Work/cad-tests/GISBOT/.test-archive-marker

# 2a. 先 reverse 把 ad-hoc patched 已是 D:/Work/cad-tests/GISBOT 的 path 改回 D:\\Work\\cad-spec-gen
#     unify GISBOT 到 v2.37.7 baseline state（所有 path 同源 prefix）
python tools/dev/rebrand_test_archive.py D:/Work/cad-tests/GISBOT \
  --from end_effector --to end_effector \
  --from-path-prefix "D:/Work/cad-tests/GISBOT" \
  --to-path-prefix "D:\\Work\\cad-spec-gen" \
  --apply

# 2b. 再 forward 把所有 D:\\Work\\cad-spec-gen 改为 D:\\Work\\cad-tests\\GISBOT
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

**为什么 2 步**：当前 v2.37.10 工具仅支持 1 prefix per run；mixed state 含 2 个不同 source prefix（`D:\\Work\\cad-spec-gen` + `D:/Work/cad-tests/GISBOT`），单次跑只覆盖其一。**若 GISBOT 处 clean state（仅源 prefix）跑 1 步即够**。

**⚠️ rev 3 B5 WARNING — 严禁两步间跑实测**：

第 1 步跑完到第 2 步跑完中间，archive 内 path 字段全指 `D:\\Work\\cad-spec-gen`（v2.37.7 源仓路径），但实际 file 在 `D:\\Work\\cad-tests\\GISBOT\\` 副本里 — **deceptive state**。**严禁此期间触发 `enhance-check` 或任何 path 校验工具** —— 会撞更深层 path mismatch fail，难以诊断。

**安全约定**：

- 2 步必须连续执行无中断
- 若第 1 步失败 → 立即跑第 2 步前置（先 cat 1 个 manifest verify state）
- CI / cron 不得在两步之间触发

§11-N10 留 follow-up：工具支持多 prefix （`--from-path-prefix p1,p2,p3`）或 atomic 2 步 sub-command — 触发条件实测后看是否常态需要。

#### 3.2.2 跑 enhance-check 端到端（rev 2 D7 enhance backend 细化）

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
- enhance vendor 重渲 — backend kind 视 jury_loop config 默认 `gemini_chat_image`
- 重评 jury / `_pick_best` 选高分

**Enhance backend kind 真值（rev 2 D7 细化）**：

| backend kind | endpoint | micuapi.ai 兼容性 |
| --- | --- | --- |
| `gemini_chat_image` (default) | chat-completions + native generateContent | ✓ micuapi.ai 用 chat-completions 路径（v2.37.9 jury 实证）|
| `openai_images_edit` | multipart POST /v1/images/edits | ❓ 未实证 micuapi.ai 是否支持此 endpoint |
| `comfyui_workflow_cloud` | fal.ai | ✗ 不是 micuapi.ai |

**实测策略**：跑默认 `gemini_chat_image` 用 micuapi.ai key + base_url；若 image gen 路径 fail，fallback 走 `openai_images_edit` kind 试 micuapi.ai `/v1/images/edits` endpoint；都 fail → 用真 Gemini API key（用户提供）。

**fallback option 决策点**：若 enhance retry vendor 全 fail（micuapi.ai 不支持 image gen + 用户无真 Gemini key）→ 进 spec §7 R7 不退步路径 + retro 标实测结果。**v2.37.10 PR 不阻** —— path-prefix 工具 + 决策路径已闭环，最终质量验收 留 §11-N7 + §11-N9 联合 follow-up。

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
| R5 | enhance retry backend 路径与 jury vendor 不同（image-gen vs vision LLM）| 用 micuapi.ai 同 key 同 endpoint（v2.37.9 实测验证可达）；rev 2 D7 细化：default `gemini_chat_image` kind 先试 → fallback `openai_images_edit` → fallback 真 Gemini key（若 micuapi.ai image gen 不兼容）|
| **R6**（rev 2 D2）| GISBOT 当前 mixed state（v2.37.9 实测残留），spec assume clean state | spec §3.2.1 加 2 步前置 ops（先 reverse unify 再 forward rebrand）|
| **R7**（rev 2 D1）| v2.37.8 既有 `_validate_inputs` 含 path-separator block，复用会撞 | spec §3.1.2 + 不变量 #16 明示 `_validate_path_prefix` 独立 helper |
| **R8**（rev 3 B1）| from==to subsystem + path-prefix 路径 early-return 绕过 archive_dir/marker 基础校验 | spec §3.1.2 重构 pseudocode — base validations 必先跑；subsystem skip 仅跳 subsystem 不跳基础；不变量 #17 |
| **R9**（rev 3 B5）| 2 步 ops 中间 deceptive state；两步间跑实测撞更深层 fail | spec §3.2.1 加 WARNING + 安全约定（必连续 / 不许 CI 触发）|
| **R10**（rev 3 B9）| path rewrite 后 sha256 / path_context_hash 字段失效 | 不变量 #18 明示；条件触发 §11-N11 sha 重算 follow-up |

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
