# v2.37.8 — §11-N1 rebrand 工具 + §12 f1 doc fix + helper cleanup 设计

> **PR 类型**：feat + docs cleanup（中体量）  
> **关联 STATUS doc**：`docs/superpowers/JURY_MATCHES_SPEC_STATUS.md`（§11 follow-up）  
> **关联 retro**：`docs/superpowers/reports/2026-05-15-gisbot-jury-e2e-retro.md`（§11-N1 原始定义出处）  
> **Spec rev**：rev 3（layer 6 scout fix 7 处 drift / self-review fix 4 处 ambiguity / layer 2 cynical + layer 4 edge-case fix ~25 项核心 fix）

---

## 1. 摘要

闭合 v2.37.x §11 + §12 follow-up 三项：

| 项 | 严重度 | 内容 | 工作量 |
| --- | --- | --- | --- |
| **§11-N1** | LOW | 新建 `tools/dev/rebrand_test_archive.py` dev 工具：递归扫描 archive_dir 自动 rewrite 含 `subsystem` 字段的 JSON（**scan-all + dual-schema-aware + cross-platform-safe**）| ~75min |
| **§12 f1** | LOW | reconcile v2.37.7 spec §11 表 stale 标记（max_tokens 实际 closed v2.37.2）| ~3min |
| **helper cleanup** | LOW | `tools/photo3d_jury.py` main() line 499 改用 `_resolve_effective_subsystem(args)` | ~5min |

---

## 2. 背景

### 2.1 §11-N1 — 测试归档 metadata 不 rebrand 陷阱

GISBOT/ 是 `end_effector` v2.36 测试归档物理复制（`D:\Work\cad-tests\GISBOT\`），但内部 metadata 全 `subsystem: "end_effector"`。下游工具按 metadata 字段路由时与 directory name 不匹配（v2.37.7 用 `--override-subsystem` 是 workaround；治本要在归档时 rewrite）。

### 2.2 Layer 6 scout 实证（spec rev 2 fix）

scout grep `D:/Work/cad-tests/GISBOT/` 实证：

- **8 类 JSON** 含 `subsystem` 顶层 key：
  - `02_codegen/CUSTOM_PARTS_AUDIT.json`
  - `02_codegen/MODEL_CONTRACT.json`
  - `02_codegen/PRODUCT_GRAPH.json`
  - `02_codegen/render_config.json`（**dict-nested**：`{name, name_cn, part_prefix, glb_file, bounding_radius_mm}`）
  - `04_render/render_manifest.json`
  - `05_enhance/ENHANCEMENT_REPORT.json`
  - `cad/end_effector/.cad-spec-gen/ARTIFACT_INDEX.json`
  - `cad/end_effector/.cad-spec-gen/runs/<run_id>/PHOTO3D_JURY_REPORT.json`
- 7 string `'end_effector'` + 1 dict (`subsystem.name == 'end_effector'`)
- 4 个 metadata 文件还在 `cad/output/renders/end_effector/<run_id>/` + `cad/output/renders/` mirror 路径
- `_archive_<ts>/` 时间戳归档复制（rebrand 时**跳过 `_archive_*/`** 路径以保历史快照）

**Schema 二态**：

```json
// pattern A — string 字面
{"subsystem": "end_effector", "...": "..."}

// pattern B — dict-nested（仅 render_config.json）
{"subsystem": {"name": "end_effector", "name_cn": "...", "part_prefix": "GIS-EE", ...}}
```

### 2.3 §12 f1 — stale follow-up 标记 reconcile

v2.37.7 spec line 281："§12 f1 max_tokens sunset 条件 未闭合（batch 3）"，但 JURY_STATUS line 77 实证 `max_tokens=512→1024` **已 closed v2.37.2**。本 PR 把表 reconcile。

### 2.4 helper cleanup

v2.37.7 PR review 标的 "未使用 helper" 是误诊（grep 显示 helper 在 line 304/409 真用），但 main() line 499 inline 计算与 helper 重复。改 main() 调 helper 后 DRY 改善。

---

## 3. 设计

### 3.1 §11-N1 — `tools/dev/rebrand_test_archive.py`

#### 3.1.1 文件路径与目录创建

**Layer 6 scout 实证 F1**：`tools/dev/` **不存在**。Plan Task 0 需：

```bash
mkdir tools/dev
touch tools/dev/__init__.py    # 空 init 保 namespace package
```

`hatch_build.py` `COPY_DIRS = {"tools": "tools"}`（line 62）实证覆盖整个 `tools/`，新建 `tools/dev/rebrand_test_archive.py` 自动进 mirror 路径 `src/cad_spec_gen/data/tools/dev/`，无需改 `hatch_build.py`。

#### 3.1.2 CLI 接口

```bash
python tools/dev/rebrand_test_archive.py <archive_dir> --from <old_subsystem> --to <new_subsystem> [--apply]
```

| flag | required | 说明 |
| --- | --- | --- |
| `<archive_dir>` | ✓ positional | 测试归档目录（如 `D:/Work/cad-tests/GISBOT`）|
| `--from <old>` | ✓ | 当前 metadata 里的 subsystem 字面值（如 `end_effector`）|
| `--to <new>` | ✓ | 目标 subsystem 字面值（如 `GISBOT`）|
| `--apply` | optional | 真改写；缺省 dry-run 只 preview |

`--help` 输出末尾加 **stderr legend block + examples**（layer 2 角色 4 fix）：

```
Examples:
  python tools/dev/rebrand_test_archive.py D:/Work/cad-tests/GISBOT \
    --from end_effector --to GISBOT          # dry-run preview
  python tools/dev/rebrand_test_archive.py D:/Work/cad-tests/GISBOT \
    --from end_effector --to GISBOT --apply  # actually write

stderr legend:
  [DRY]   candidate (would change if --apply)
  [APPLY] successfully updated
  [SKIP]  skipped (already target / no subsystem key / not matched)
  [WARN]  warning (invalid JSON / IO error / type mismatch)
  [ERROR] fatal error (input validation / dir not exist)
```

stderr 使用 `[DRY] / [APPLY] / [SKIP] / [WARN] / [ERROR]` **纯 ASCII label**（不用 emoji 避外行 ops 困扰）。

#### 3.1.3 行为（scan-all + dual-schema-aware + cross-platform-safe）

```
扫描 <archive_dir>:
  校验 (input validation, exit=2 early):
    archive_dir.is_dir() == False → exit=2 "[ERROR] not a directory"   (edge-case #7)
    --from / --to 空字符串              → exit=2 "[ERROR] must be non-empty"
    --from == --to                       → exit=2 "[ERROR] must differ"
    --from / --to 含 control char (\\x00-\\x1f) → exit=2 "[ERROR] control chars" (edge-case #8)
    --from / --to 含路径分隔符 (/ \\)    → exit=2 "[ERROR] path separators"
  
  os.walk(archive_dir, followlinks=False) 递归（不变量 #4 防 symlink loop / 跨卷漫扫）:
    # 原地修剪 dirnames，不递归进黑名单子目录 (layer 4 edge #18):
    dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]
    
    其中 _should_skip_dir(name):
      return (
        fnmatch.fnmatchcase(name, "_archive_*")       # 时间戳归档 (case-sensitive)
        or name in {".git", ".venv", "__pycache__",
                    "node_modules", ".tox", ".pytest_cache",
                    ".mypy_cache", "build", "dist"}    # edge-case #19
      )
    
    对每个 *.json 文件:
      size guard (edge-case #17):
        if path.stat().st_size > 50_000_000: 
          stderr "[WARN] {path}: file >50MB, skipped"
          continue
      
      try: 
        raw = path.read_bytes()
        # 显式 utf-8-sig 兼容 BOM (edge-case #1):
        text = raw.decode("utf-8-sig")
        data = json.loads(text)
      except UnicodeDecodeError:                      # edge-case #2
        stderr "[WARN] {path}: encoding not utf-8/utf-8-sig, skipped"
        continue
      except json.JSONDecodeError:
        stderr "[WARN] {path}: invalid JSON, skipped"
        continue
      
      if not isinstance(data, dict):                  # edge-case #3
        stderr f"[SKIP] {path}: not a JSON object (type={type(data).__name__})"
        continue
      
      val = data.get("subsystem")
      # 严格 type 分发 (bool 在 int 之前判，edge-case #4):
      if val is None:
        stderr f"[SKIP] {path}: no subsystem key"
        continue
      elif isinstance(val, bool):
        stderr f"[WARN] {path}: subsystem is bool, expected str/dict"
        continue
      elif isinstance(val, str):
        # pattern A
        if val == args.to:
          stderr f"[SKIP] {path}: subsystem already {args.to!r}, idempotent"
          continue
        if val != args.from_:
          stderr f"[SKIP] {path}: subsystem={val!r}, not matched"
          continue
        candidate (pattern=A, location="subsystem")
      elif isinstance(val, dict):
        # pattern B
        nested = val.get("name")
        if not isinstance(nested, str):               # edge-case #5
          stderr f"[WARN] {path}: subsystem.name not a string"
          continue
        if "name" not in val:                          # edge-case #6
          stderr f"[WARN] {path}: subsystem dict missing 'name' key"
          continue
        if nested == args.to:
          stderr f"[SKIP] {path}: subsystem.name already {args.to!r}, idempotent"
          continue
        if nested != args.from_:
          stderr f"[SKIP] {path}: subsystem.name={nested!r}, not matched"
          continue
        candidate (pattern=B, location="subsystem.name")
      else:
        stderr f"[WARN] {path}: subsystem is {type(val).__name__}, expected str/dict"
        continue
  
  dry-run（默认）:
    stderr "[DRY] {path}: {location} {from!r} → {to!r}"  per candidate
    stderr "△ {N} files would change (run with --apply)"
    exit 0
  
  --apply:
    对每个 candidate:
      pattern A: data["subsystem"] = args.to
      pattern B: data["subsystem"]["name"] = args.to
      _atomic_write(path, data)
      stderr "[APPLY] {path}: {location} updated"
    stderr "✓ {N} files updated"
    exit 0
```

#### 3.1.4 `_atomic_write` 实现（layer 2 角色 1 + edge-case #10-14, #25 联合 fix）

```python
def _atomic_write(target: Path, data: dict) -> None:
    """跨平台原子写盘 — Windows file lock / read-only / disk full / mid-write 全 cleanup。"""
    parent = target.parent
    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix=".rebrand_", suffix=".tmp", dir=parent
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="\n") as f:
            # newline="\n" 保跨平台一致 LF (edge-case #22)
            json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=False)
            f.write("\n")  # POSIX trailing newline (edge-case #21)
        # os.replace 原子（POSIX rename / Windows MoveFileEx），edge-case #10/13:
        # - 跨 drive: 同 parent dir，永远同盘 ✓
        # - target 被打开 (Windows file lock): raise PermissionError → caller WARN
        # - target read-only: raise PermissionError → caller WARN
        os.replace(tmp_path, target)
    except OSError as exc:
        # disk full / file lock / read-only / 其他 IO 错全 catch
        # edge-case #11, #12, #14
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass  # cleanup best-effort
        raise  # caller (循环体) catch + skip + WARN
```

调用方在循环里 catch OSError 跳过该文件 + 继续：

```python
try:
    _atomic_write(path, data)
    stderr f"[APPLY] {path}: {location} updated"
    success_count += 1
except (OSError, PermissionError) as exc:
    stderr f"[WARN] {path}: write failed ({exc.__class__.__name__}: {exc}), skipped"
    skip_count += 1
```

#### 3.1.5 错误处理 + exit code 语义（layer 2 角色 5.2 + edge-case #30 reconcile）

| 场景 | 行为 | exit |
| --- | --- | --- |
| `<archive_dir>` 不是目录 | stderr `[ERROR] not a directory: {path}` | **2** |
| `--from == --to` | stderr `[ERROR] --from and --to must differ` | **2** |
| `--from`/`--to` 空字符串 / control char / 路径分隔符 | stderr `[ERROR] ...` | **2** |
| JSON 解析失败 / utf-8 解码失败 / 文件 >50MB | per-file `[WARN]` + 继续；不算 fatal | **0** (with WARN) |
| 文件 write 失败（disk full / file lock / read-only / IO 错）| per-file `[WARN]` + 继续；累 skip_count | **0** (with WARN)；若实施层选项可 `exit=1 if skip_count > 0` 但 spec 默认 exit=0 |
| KeyboardInterrupt | 不 catch（让 Ctrl-C 终止）edge-case #29 | (interrupted) |
| 0 candidates | stderr `[SKIP] no candidates found in {archive_dir}` | **0** |
| 成功改写 N 文件 | stderr `✓ {N} files updated` | **0** |

**exit code 决策**（layer 2 角色 5.2 reconcile）：

- `2` = input validation 错（CLI 解析层 — fail-fast 必返）
- `1` = unhandled exception 在 main()（如 import 错 / argparse 内部错 — Python 默认）
- `0` = run completed，含 partial-skip（每 skip 都 stderr WARN，用户可视，CI 不跑此工具）

**rationale**：dev 工具人手跑能看 stderr；CI 不集成；partial-write 用 stderr 详尽 WARN 优于 fail-all。若未来 wrap 进 batch script，本 PR §11 follow-up 登记 "exit code 语义 v2.39 重审"。

#### 3.1.6 不变量

1. 默认 dry-run（永不静默改文件）
2. JSON 写出 `indent=2`, `ensure_ascii=False`, `sort_keys=False`, `newline="\n"`, 末尾 `+ "\n"` trailing newline（保 git diff cleanness）
3. **仅改 pattern A 顶层 `subsystem` 字段 或 pattern B 顶层 `subsystem` 内 1 层深 `.name` 字段**；其他字段全不动（含 `subsystem.name_cn` 中文字段保 mojibake 不动）；**不递归扫嵌套 subsystem 字段** (layer 2 角色 1.2 fix)
4. `os.walk(followlinks=False)` 不跟随 symlink（防 link loop / 跨卷漫扫）
5. `_archive_*` glob + 普适开发目录 deny list（`.git/`, `.venv/`, `__pycache__/`, `node_modules/`, `.tox/`, `.pytest_cache/`, `.mypy_cache/`, `build/`, `dist/`) 在 `os.walk` 时 `dirnames[:] = [...]` 原地修剪不递归
6. idempotent — 相同 `--from --to` 重跑零写盘
7. 文件 size > 50MB skip + WARN（防 MemoryError）
8. atomic write — `tempfile.mkstemp(dir=parent)` 同盘 + `os.replace` 原子 + 失败 cleanup tmp
9. exit code: `0` success（含 partial-skip） / `1` unhandled exception / `2` input validation
10. stderr 用 `[DRY] / [APPLY] / [SKIP] / [WARN] / [ERROR]` ASCII label（不用 emoji 防外行 ops 困扰）

#### 3.1.7 测试设计（TDD — 14 unit + 1 integration）

| # | 测试 | 断言 |
| --- | --- | --- |
| T1 | dry-run 默认不写文件（**SHA-256 hash 比对** — layer 2 角色 3.1 fix）| tempdir / 跑 / 文件 SHA-256 不变 / stderr `[DRY]` |
| T2 | `--apply` 真写 pattern A（string）| 放 `{subsystem: "old"}` / `--apply` / 读回 `{subsystem: "new"}` |
| T3 | `--apply` 真写 pattern B（dict-nested）| 放 `{subsystem: {name: "old", name_cn: "..."}}` / `--apply` / 读回 name 改 name_cn 保 |
| T4 | 混合 archive（A + B + 无 subsystem + bool subsystem + dict 无 name）| 5 JSON / `--apply` / A+B 改 / 3 skip / stderr 详尽 |
| T5 | idempotent rerun | 二次 `--apply` 同参数 / 0 candidates / exit=0 |
| T6 | malformed JSON skip + WARN | 损坏 JSON / 跑 / exit=0 / WARN |
| T7 | `_archive_*` 路径跳过（含 case-sensitive layer 4 #24）| tempdir `_archive_20260513/`+`_Archive_lowercase/` / `--apply` / _archive 跳过, _Archive 不跳过（Linux/macOS） |
| T8 | deny list 跳 `.git/`, `__pycache__/` 等普适目录 | tempdir 含这些子目录 / 跑 / 子目录 JSON 未扫 |
| T9 | `--from == --to` exit=2 | exit=2 |
| T10 | `<archive_dir>` 不存在 exit=2 | exit=2 |
| T11 | `--from` 含 control char `\\x00` exit=2 | exit=2 |
| T12 | atomic write 中断 — mock `os.replace` raise OSError | tempdir / mock raise / 原文件未改 / **tempdir listdir 无 `.tmp` 残留** (layer 2 角色 3.2 fix) / WARN |
| T13 | 大文件 >50MB skip + WARN | tempfile 写 51MB JSON / 跑 / SKIP + WARN |
| T14 | utf-8-sig BOM 兼容 | 写带 BOM 的 JSON / 跑 / 正常 parse |

**集成测试**（手动 + marker skip — sandbox copy 防破坏真归档）：

- pyproject.toml 加 marker `requires_test_archive`（已实证不存在，需 Plan Task 0 加）
- `tests/dev/test_rebrand_test_archive_integration.py::test_gisbot_rebrand` 用 marker
- 跑命令：`pytest tests/dev/test_rebrand_test_archive_integration.py -v -m requires_test_archive`
- conftest.py 检查 `D:/Work/cad-tests/GISBOT/05_enhance/ENHANCEMENT_REPORT.json` 存在；不存在自动 skip
- **测试体**（不动真 GISBOT/，layer 4 edge-case #28 fix）：
  1. `tempfile.mkdtemp()` 建 sandbox（在 tempdir 默认位置，避 OneDrive 同步 flake）
  2. `shutil.copytree(GISBOT, sandbox)` 复制整个 GISBOT 进去（含 `_archive_*` 全套）
  3. 跑 `--apply --from end_effector --to GISBOT_REBRANDED` 改 sandbox 副本
  4. 验 8 类 JSON `subsystem` 全改（含 dict-nested `render_config.json::subsystem.name`，`name_cn` 字段保留不动）
  5. 验 `_archive_*/` 路径 JSON 未改（保历史快照）
  6. tempdir teardown 自动清理（pytest tmp_path fixture）
- **决策**：不在真 GISBOT/ 跑改写测试，避免影响后续 jury e2e 用 GISBOT 时的 path 解析

### 3.2 §12 f1 — STATUS 表 reconcile

文件：`docs/superpowers/specs/2026-05-15-v2-37-7-jury-cli-improvements-design.md:281`

```diff
-| §12 f1 | LOW | max_tokens sunset 条件 | 未闭合（batch 3）|
+| §12 f1 | LOW | max_tokens 1024 sunset 条件（STATUS §9.3 #6）| closed v2.37.2 ✓（512→1024 实证）|
```

无代码改动。

### 3.3 helper cleanup

文件：`tools/photo3d_jury.py:498-511`

改前：

```python
def main() -> int:
    # ...
    effective_subsystem = args.subsystem
    if args.override_subsystem:
        # 输入校验... validate args.override_subsystem
        effective_subsystem = args.override_subsystem
```

改后：

```python
def main() -> int:
    # ...
    if args.override_subsystem:
        # 输入校验... validate args.override_subsystem（保留 — TDD red 防误删 layer 2 R4 fix）
    effective_subsystem = _resolve_effective_subsystem(args)
```

行为零差异。回归 `tests/jury/test_photo3d_jury_progress.py` 5 测试照常 PASS。

---

## 4. 不变量（项目级）

1. 北极星 5 gate 不破坏（dev 工具 / 不进 user 入口 / 不动 user 默认路径）
2. canonical/mirror 同步：`tools/dev/*.py` 是 canonical / `src/cad_spec_gen/data/tools/dev/*.py` 是 mirror（由 hatch_build 自动同步，dev_sync `--check` gate 永过）
3. `_archive_*/` + 普适开发目录全工具不触（保历史快照）
4. helper cleanup 零行为差异（既有 5 测试 + jury 子集 509 PASS）

---

## 5. 验收（AC）

| AC | 期望 | 验证 |
| --- | --- | --- |
| AC-1 | `python tools/dev/rebrand_test_archive.py --help` exit=0 + 输出含 Examples block + legend | shell |
| AC-2 | 14/14 单元测试 PASS（T1-T14）| `pytest tests/dev/test_rebrand_test_archive.py -v` |
| AC-3 | dry-run 默认不写：GISBOT sandbox 副本跑不带 `--apply` / 8 JSON 全 SHA-256 不变 / stderr 含 `[DRY]` × 8 | 集成测 |
| AC-4 | `--apply` 改 GISBOT sandbox 副本 8 类 JSON（7 string + 1 dict-nested）`subsystem` "end_effector" → "GISBOT_REBRANDED" / `subsystem.name_cn` 字段保留 | 集成测 + assert |
| AC-5 | idempotent — `--apply` 二次跑零写盘（8 文件 SHA-256 不变）| 集成测 + assert |
| AC-6 | `_archive_*/` 路径 JSON 未改（保历史快照）| 集成测 + cat sandbox `_archive_20260513_195647/05_enhance/ENHANCEMENT_REPORT.json` 验证 `subsystem == "end_effector"` 未改 |
| AC-7 | v2.37.7 spec §12 f1 行 reconcile | grep doc |
| AC-8 | `tools/photo3d_jury.py` main() 改用 helper / 既有 5 测试 PASS / jury 子集 509 PASS | pytest |
| AC-9 | CI 8/8 SUCCESS（含 mypy-strict pass 新文件）| gh pr checks |
| AC-10 | pyproject.toml 加 `requires_test_archive` marker | grep |
| AC-11 | dev_sync `--check` PASS | shell |

---

## 6. 范围（YAGNI）

**做**：
- §11-N1 dev 工具（scan-all + dual-schema-aware + cross-platform-safe）+ 14 单元测试 + 1 GISBOT 集成测
- pyproject.toml 加 marker `requires_test_archive`
- `tools/dev/` 目录 + `__init__.py`
- §12 f1 doc 表 reconcile（单行 diff）
- helper cleanup（main() 改调用 helper）
- retro 文档

**不做**（留下批）：
- `--reverse` flag（用户可跑 `--from new --to old` 反向）
- 嵌套字段递归改写（仅顶层 `subsystem` / `subsystem.name` 1 层深）
- `tools/dev/` 工具自身的 entry point（pyproject `[project.scripts]` — YAGNI）
- 其他 dev 工具创建（本 PR 只一个工具）
- 跨 archive 批处理（`--archive-glob`）
- **`tools/dev/_common.py` 共享 helper**（layer 2 角色 5.1 fix — rule-of-three：等第 2 个 dev 工具入场时再抽 _common.py，避免 over-engineer）
- 大归档 progress bar（layer 2 角色 2.2 — 当前 per-file stderr 行即提供逐文件进度）
- 自动 schema 三态（list / 其他 type）扩展（layer 2 角色 5.3 — case `_` → WARN 已为 forward compat）

---

## 7. 风险与权衡

| # | 风险 | 缓解 |
| --- | --- | --- |
| R1 | 用户误传 archive_dir 改 production 文件 | 默认 dry-run + schema 过滤（顶层非 `subsystem` 全 skip）+ deny list |
| R2 | dual-schema 设错：误把 pattern A 当 pattern B 改 | type 严格分发 `isinstance(val, bool)` 先于 `int` 检 / `isinstance(val, str)` / `isinstance(val, dict)` + T2+T3+T4 测试硬保 |
| R3 | atomic write 中断破坏文件 | `tempfile.mkstemp` + `os.replace` 跨平台原子 + try/finally cleanup .tmp + T12 测试 |
| R4 | helper cleanup 误删 input validation（v2.37.7 §11-N2 引入的安全阀）| TDD red：`test_override_subsystem_input_validation` 必须仍 PASS + git diff 显式审 |
| R5 | render_config.json 改 `subsystem.name_cn` mojibake 字段 | 不变量 #3 + dual-schema 工具不改 nested 其他字段 + T3 验 name_cn 保留 |
| R6 | scope 4× 工作量超过用户认知 | spec rev 2/3 已实证 8 JSON / dual schema / 25+ edge case；14 测试可控 |
| R7 | Windows file lock / read-only / disk full atomic write 中断 | `_atomic_write` 全 OSError catch + WARN + 继续（不 abort 全程）+ T12 |
| R8 | 大文件 MemoryError | size guard 50MB skip + T13 验证 |
| R9 | symlink loop 漫扫 | `os.walk(followlinks=False)` 默认 + 不变量 #4 |

---

## 8. follow-up（本 PR 闭合后）

| 项 | 严重度 | 内容 |
| --- | --- | --- |
| §11-N1 实施 | closed v2.37.8 ✓ | 本 PR |
| §12 f1 doc | closed v2.37.8 ✓ | 本 PR |
| helper cleanup | closed v2.37.8 ✓ | 本 PR |
| §12 f4 | LOW | N≥50 批量场景成本评估（留 v2.37.9）|
| **新**：exit code 语义 v2.39 重审 | LOW | partial-write skip 时 exit=0 vs exit=1 trade-off（layer 2 角色 5.2 跟进）|
| **新**：`tools/dev/_common.py` 共享 helper | LOW | rule-of-three 触发时 refactor atomic_write / glob skip / dual-schema-aware load |

---

## 9. Layer 6 fact-check + Layer 2 cynical + Layer 4 edge-case 总账

**Layer 6 scout（spec rev 1 → rev 2）— 7 处 drift fix**：

| # | rev 1 假设 | scout 实证 | rev 2/3 真值 |
| --- | --- | --- | --- |
| F1 | `tools/dev/` 已存在 | 不存在 | §3.1.1 plan Task 0 mkdir + `__init__.py` |
| F2 | metadata JSON 在 archive 根 | 4 处嵌套子目录 | §3.1.3 递归扫描 |
| F3 | render_manifest 在根 | 3 处嵌套 | 同 F2 |
| F4 | 仅 2 文件含 subsystem | **8 类 JSON** | §3.1.3 scan-all |
| F4b | 都是 string | 7 string + 1 dict-nested | §3.1.3 dual-schema-aware |
| F5 | marker 既有 | 仅 `requires_solidworks` | §3.1.7 加 `requires_test_archive` |
| F6 | `tools/dev/` 在 COPY_DIRS | ✓ 实证 | §3.1.1 OK 不动 hatch_build |
| F7 | 顶层 `subsystem` 字段名 | ✓ 实证 | OK |
| **NEW** | （无）| `_archive_*/` 应跳 | §3.1.3 + 不变量 #5 + T7 测试 |

**Layer 2 cynical re-read（rev 2 → rev 3）— 0 BLOCKER + 8 MAJOR fix**：

1. ✓ §3.1.4 atomic_write 实现详细化（NamedTemporaryFile→`tempfile.mkstemp(delete=False 等价)` + try/finally cleanup .tmp + os.replace 跨平台保 atomicity）
2. ✓ §3.1.3 `_archive_*` glob 用 `os.walk` `dirnames[:] = [...]` 原地修剪（非 fnmatch full-path 匹配）
3. ✓ §3.1.6 不变量 #3 加"顶层"限定 + §3.1.3 注释明示不递归 nested
4. ✓ §3.1.7 T1 + AC-3/5/6 mtime 断言改 SHA-256 hash 比对（跨平台精度防御）
5. ✓ §3.1.5 错误处理 exit code 与 §3.1.6 不变量 reconcile（exit=0 含 partial-skip，§8 follow-up 加 v2.39 重审）
6. ✓ §3.1.2 stderr 改 ASCII label `[DRY]/[APPLY]/[SKIP]/[WARN]/[ERROR]`（不用 emoji 防外行困扰）+ `--help` legend block
7. ✓ §6 YAGNI 加 "`tools/dev/_common.py` 共享 helper rule-of-three 不抽"
8. ✓ §3.1.7 T12 补 "tempdir listdir 无 .tmp 残留" 断言

**Layer 4 edge-case hunter（rev 2 → rev 3）— 31 个 edge 合并去重得 ~17 个 spec 反映**：

| edge # | 内容 | rev 3 落点 |
| --- | --- | --- |
| 1, 2 | utf-8 BOM / 非 UTF-8 编码 catch | §3.1.3 utf-8-sig 解码 + UnicodeDecodeError catch + T14 |
| 3 | 顶层 list/array root | §3.1.3 `not isinstance(data, dict)` skip |
| 4 | bool 在 int 前判（bool 是 int 子类）| §3.1.3 type 分发顺序 |
| 5, 6 | pattern B `subsystem.name` not str / missing key | §3.1.3 pattern B 严格校验 |
| 7 | archive_dir 是文件而非目录 | §3.1.3 `archive_dir.is_dir()` 校验 |
| 8 | `--from/--to` NUL / control char | §3.1.3 input validation |
| 10-14 | atomic write Windows file lock / read-only / disk full / cleanup tmp | §3.1.4 `_atomic_write` 实现完整 + OSError catch |
| 15 | symlink loop | §3.1.3 `os.walk(followlinks=False)` + 不变量 #4 |
| 17 | 大文件 MemoryError | §3.1.3 size guard 50MB + T13 |
| 18 | `_archive_*` glob 应针对 dirnames | §3.1.3 `dirnames[:] = [...]` |
| 19 | deny list 加 .tox/.pytest_cache/build/dist | 不变量 #5 |
| 21, 22 | trailing newline / CRLF | §3.1.4 `f.write("\n")` + `newline="\n"` |
| 23 | mtime 精度跨平台 | §3.1.7 T1 改 SHA-256 |
| 24 | fnmatch case-sensitive | T7 含 case-sensitive 测试 |
| 25 | T12 tmp 残留 | T12 含 `listdir 无 .tmp` 断言 |
| 28 | conftest skip 条件 GISBOT 改名失效 | conftest 检通用路径（ENHANCEMENT_REPORT.json），不依赖目录名 |
| 29 | 权限错 catch 太宽 swallow KeyboardInterrupt | §3.1.4 `except (OSError, PermissionError)` 显式不捕 KeyboardInterrupt |
| 30 | exit=1 触发条件未定义 | §3.1.5 exit code 表三档明示 |

剩 ~14 个 edge case 是 MINOR 不进 spec（如 sort_keys 顺序、JSON 字符 escape stderr 美观性、Windows MAX_PATH 260 — 这些是 implementation 细节由实施者 grep 验证）。

---

## 10. 关联文档

- STATUS doc：`docs/superpowers/JURY_MATCHES_SPEC_STATUS.md`
- v2.37.7 spec：`docs/superpowers/specs/2026-05-15-v2-37-7-jury-cli-improvements-design.md`
- v2.37.7 retro：`docs/superpowers/reports/2026-05-15-v2-37-7-jury-cli-improvements-retro.md`
- §11-N1 原始 retro：`docs/superpowers/reports/2026-05-15-gisbot-jury-e2e-retro.md:99`
- photo3d_jury：`tools/photo3d_jury.py`（v2.37.7 引入 helper）
