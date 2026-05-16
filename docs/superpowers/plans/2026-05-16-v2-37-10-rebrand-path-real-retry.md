# v2.37.10 — rebrand path-prefix 扩 + 真 retry 闭环实测 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** v2.37.8 rebrand 工具扩 `--from-path-prefix` + `--to-path-prefix` 互锁 flag + 真 retry 闭环实测验证 photoreal ≥60。

**Architecture:** 既有 `tools/dev/rebrand_test_archive.py` 扩 4 helper（path-prefix 独立 validation / 跨 separator 兼容 / drive letter 校验）+ scan loop 加 prefix rewrite path；TDD 9 单元 + 1 集成实测。

**Tech Stack:** Python 3.11+ / pytest / fnmatch / json / pathlib / dev_sync mirror

**Spec ref:** `docs/superpowers/specs/2026-05-16-v2-37-10-rebrand-path-real-retry-design.md` (rev 3, 383 行, commit `a1f0647`)

---

## Task 0: Scout 假设验证（防 plan-drift）

**Files:** 无（grep only）

**预计:** 3 分钟

- [ ] **Step 1: 验证 v2.37.8 工具当前 argparse + `_validate_inputs` 真值**

Run:
```bash
cd D:/Work/cad-spec-gen
sed -n '215,225p' tools/dev/rebrand_test_archive.py
sed -n '53,75p' tools/dev/rebrand_test_archive.py
```

Expected:
- argparse 现 4 flag: `archive_dir`, `--from`, `--to`, `--apply`
- `_validate_inputs` 含 path-separator block (`if "/" in val or "\\" in val: exit=2`)

- [ ] **Step 2: 验证 GISBOT mixed state 真值**

Run:
```bash
cd D:/Work/cad-tests/GISBOT
python -c "
import json
manifests = ['04_render/render_manifest.json', 'cad/output/renders/render_manifest.json', 'cad/output/renders/end_effector/20260513T115709Z/render_manifest.json']
for m in manifests:
    d = json.load(open(m, encoding='utf-8'))
    print(f'{m}:')
    print(f'  render_dir: {d.get(\"render_dir\")[:60]}')
    print(f'  files[0].path_abs_resolved: {d.get(\"files\", [{}])[0].get(\"path_abs_resolved\", \"NA\")[:60]}')
"
```

Expected: 04_render 全 `D:\Work\cad-spec-gen`；cad/output 顶层 `D:/Work/cad-tests/GISBOT`（`/` separator）但 files[] 仍 `D:\Work\cad-spec-gen`（mixed state）。

- [ ] **Step 3: 验证 GISBOT .test-archive-marker 仍存**

Run:
```bash
ls -la D:/Work/cad-tests/GISBOT/.test-archive-marker
```

Expected: 存在（v2.37.9 已 touched）

- [ ] **Step 4: 验证 cad_pipeline enhance-check entry**

Run:
```bash
grep -nE "cmd_enhance_check|add_parser.*enhance-check" src/cad_spec_gen/data/python_tools/cad_pipeline.py | head -5
```

Expected:
- `cmd_enhance_check` def at line ~3325
- argparse subparser `enhance-check` at line ~4542

记录 5/5 实证全过即推进 Task 1+。任何 mismatch BLOCK 重审 spec rev 3。

---

## Task 1: 加 argparse flag + 5 helper（dry-run 实现）

**Files:**
- Modify: `tools/dev/rebrand_test_archive.py` (argparse + helper)
- Modify: `tests/dev/test_rebrand_test_archive.py` (TDD T-prefix-D + E + F + H + I + drive letter)

**预计:** 30 分钟

### Step 1: 加 TDD 互锁 + drive letter + 边界 测试

打开 `tests/dev/test_rebrand_test_archive.py`，末尾追加：

```python
def test_t_prefix_d_one_prefix_only_exit_2(tmp_path: Path) -> None:
    """T-prefix-D — 缺 from-path-prefix 仅给 to-path-prefix → exit=2 (互锁校验)。"""
    arch = _make_archive_tempdir(tmp_path)
    
    cp = _run(str(arch), "--from", "old", "--to", "new", "--to-path-prefix", "D:\\Work\\new", "--apply")
    
    assert cp.returncode == 2
    assert "must be" in cp.stderr.lower() or "互锁" in cp.stderr or "specified together" in cp.stderr.lower() or "with --from-path-prefix" in cp.stderr.lower()


def test_t_prefix_e_from_eq_to_with_path_prefix_allowed(tmp_path: Path) -> None:
    """T-prefix-E — from==to (subsystem) + 给 path-prefix → 允许 (skip subsystem rewrite)。"""
    arch = _make_archive_tempdir(
        tmp_path,
        {"a.json": {"subsystem": "x", "render_dir": "D:\\Work\\OLD\\f"}},
    )
    
    cp = _run(
        str(arch), "--from", "x", "--to", "x",
        "--from-path-prefix", "D:\\Work\\OLD",
        "--to-path-prefix", "D:\\Work\\NEW",
        "--apply",
    )
    
    assert cp.returncode == 0, cp.stderr
    data = json.loads((arch / "a.json").read_text(encoding="utf-8"))
    assert data["subsystem"] == "x"  # subsystem 未改 (skip)
    assert data["render_dir"] == "D:\\Work\\NEW\\f"  # path rewrite


def test_t_prefix_f_from_eq_to_without_path_prefix_exit_2(tmp_path: Path) -> None:
    """T-prefix-F — from==to (subsystem) + 不给 path-prefix → exit=2 (v2.37.8 既有)。"""
    arch = _make_archive_tempdir(tmp_path)
    
    cp = _run(str(arch), "--from", "x", "--to", "x", "--apply")
    
    assert cp.returncode == 2
    assert "must differ" in cp.stderr


def test_t_prefix_drive_letter_required(tmp_path: Path) -> None:
    """T-drive-letter — prefix 须以 drive letter + colon 开头 (rev 2 D4 不变量 #15)。"""
    arch = _make_archive_tempdir(tmp_path)
    
    cp = _run(
        str(arch), "--from", "x", "--to", "x",
        "--from-path-prefix", "cad-spec-gen",  # 无 drive letter
        "--to-path-prefix", "GISBOT",
        "--apply",
    )
    
    assert cp.returncode == 2
    assert "drive letter" in cp.stderr.lower()


def test_t_prefix_base_validation_runs_when_skip_subsystem(tmp_path: Path) -> None:
    """T-base-validation — rev 3 B1 fix：from==to + path-prefix 路径仍跑 archive_dir/marker 校验。"""
    # tempdir 不放 marker（_make_archive_tempdir include_marker=False）
    arch = _make_archive_tempdir(tmp_path, include_marker=False)
    
    cp = _run(
        str(arch), "--from", "x", "--to", "x",
        "--from-path-prefix", "D:\\Work\\OLD",
        "--to-path-prefix", "D:\\Work\\NEW",
        "--apply",
    )
    
    # base validation B1 fix：marker 缺失仍 exit=2，不被 subsystem skip 绕过
    assert cp.returncode == 2
    assert ".test-archive-marker" in cp.stderr
```

### Step 2: 跑测试 5 FAIL（RED — 新 flag 未加 / helper 未存在）

Run:
```bash
pytest tests/dev/test_rebrand_test_archive.py -v -k "prefix_d or prefix_e or prefix_f or drive_letter or base_validation" 2>&1 | tail -15
```

Expected: 5 FAIL（`unrecognized arguments: --from-path-prefix`）

### Step 3: 加 argparse 2 新 flag + 5 helper

打开 `tools/dev/rebrand_test_archive.py`。

**3a. 加 import**（顶部 import 区已有 fnmatch、json、os、sys、tempfile、Path 等，无需新增）

**3b. 加 helper 函数**（在 `_validate_inputs` 之后）：

```python
def _looks_like_abs_path(p: str) -> bool:
    """rev 2 D4 — abs path 须以 drive letter (e.g. C: D:) 开头。"""
    return len(p) >= 2 and p[1] == ":" and p[0].isalpha()


def _normalize_path(p: str) -> str:
    """统一 separator 到 \\ 用于匹配比较（仅内部用，不写回）。"""
    return p.replace("/", "\\")


def _matches_prefix(value: str, from_prefix: str) -> bool:
    """prefix 匹配 — 跨 separator 兼容 + 边界紧跟 / 或 \\。"""
    v_norm = _normalize_path(value)
    p_norm = _normalize_path(from_prefix)
    if v_norm == p_norm:
        return True
    if v_norm.startswith(p_norm):
        rest_first_char = v_norm[len(p_norm):][:1]
        return rest_first_char == "\\"
    return False


def _rewrite_prefix(value: str, from_prefix: str, to_prefix: str) -> str:
    """prefix replace — 保留 value 原 separator 风格。"""
    # 判 value 主用 separator
    sep = "/" if value.count("/") > value.count("\\") else "\\"
    p_norm = _normalize_path(from_prefix)
    v_norm = _normalize_path(value)
    new_v = _normalize_path(to_prefix) + v_norm[len(p_norm):]
    return new_v.replace("\\", sep) if sep == "/" else new_v


def _validate_path_prefix(
    archive_dir: Path,
    args_from: str,
    args_to: str,
    from_prefix: str | None,
    to_prefix: str | None,
) -> int:
    """rev 2 + rev 3 — 独立 path-prefix 校验 helper（不复用 _validate_inputs path-separator block）。
    
    rev 3 B1 fix: base validations (archive_dir/marker) 必先跑，subsystem skip 仅跳 subsystem 不跳基础。
    """
    # base validations 必先跑（B1 fix）
    if not archive_dir.is_dir():
        print(f"[ERROR] not a directory: {archive_dir}", file=sys.stderr)
        return 2
    if not (archive_dir / _ARCHIVE_MARKER).is_file():
        print(
            f"[ERROR] archive_dir missing {_ARCHIVE_MARKER} file "
            f"(refuse to operate on non-archive directory)",
            file=sys.stderr,
        )
        return 2
    
    # 互锁校验（不变量 #12）
    if (from_prefix is None) != (to_prefix is None):
        print(
            "[ERROR] --from-path-prefix and --to-path-prefix must be specified together",
            file=sys.stderr,
        )
        return 2
    
    if from_prefix is None:
        # 都缺 — 复用 v2.37.8 既有 subsystem 5 条校验（base 已跑过）
        return _validate_inputs(archive_dir, args_from, args_to)
    
    # 都给 path-prefix：
    if not from_prefix or not to_prefix:
        print("[ERROR] --from-path-prefix / --to-path-prefix must be non-empty", file=sys.stderr)
        return 2
    if from_prefix == to_prefix:
        print("[ERROR] --from-path-prefix and --to-path-prefix must differ", file=sys.stderr)
        return 2
    
    # 不变量 #15 (rev 2 D4)：prefix 须含 drive letter + colon
    if not _looks_like_abs_path(from_prefix):
        print(
            "[ERROR] --from-path-prefix must start with drive letter (e.g. D:/, C:\\)",
            file=sys.stderr,
        )
        return 2
    if not _looks_like_abs_path(to_prefix):
        print(
            "[ERROR] --to-path-prefix must start with drive letter",
            file=sys.stderr,
        )
        return 2
    
    # subsystem 校验（除 from==to 时 skip subsystem 5 条 — T-prefix-E 语义）
    if args_from != args_to:
        # subsystem 真 rewrite，跑 v2.37.8 subsystem 5 条校验（base 跑 2 次 idempotent OK）
        sub_rc = _validate_inputs(archive_dir, args_from, args_to)
        if sub_rc != 0:
            return sub_rc
    # else: from==to + path-prefix 给 → skip subsystem 5 条；base 已跑完 (B1 fix)
    
    return 0
```

**3c. 加 argparse flag**（找 `parser.add_argument("--apply"...)` 之前插入）：

```python
    parser.add_argument(
        "--from-path-prefix",
        dest="from_path_prefix",
        default=None,
        help="当前 abs path 前缀（如 D:\\Work\\cad-spec-gen）；须含 drive letter；与 --to-path-prefix 互锁",
    )
    parser.add_argument(
        "--to-path-prefix",
        dest="to_path_prefix",
        default=None,
        help="目标 abs path 前缀（如 D:\\Work\\cad-tests\\GISBOT）；与 --from-path-prefix 互锁",
    )
```

**3d. main() 改用新 validation**（找 `rc = _validate_inputs(...)` 替换）：

```python
    rc = _validate_path_prefix(
        args.archive_dir, args.from_, args.to,
        args.from_path_prefix, args.to_path_prefix,
    )
    if rc:
        return rc
```

### Step 4: 跑 5 测试 GREEN

Run:
```bash
pytest tests/dev/test_rebrand_test_archive.py -v -k "prefix_d or prefix_e or prefix_f or drive_letter or base_validation" 2>&1 | tail -15
```

Expected: T-prefix-D + T-prefix-F + T-drive-letter + T-base-validation 4 PASS（partial — T-prefix-E 需要 scan loop 改）；T-prefix-E **可能仍 FAIL** 因为 scan loop 还没集成 path-prefix rewrite（仅校验通过，path 字段未真改写）。Step 5 会修。

如果 T-prefix-E FAIL with "render_dir 未改"则正确，Step 5 集成；如果 ParseError 则 Step 3 实施漏。

### Step 5: 临时 stub `_rewrite_path_in_data`（让 T-prefix-E 暂 GREEN，下 task 真集成）

实际让 Task 1 仅完成 validation；T-prefix-E 留 Task 2 完整测试。

修改 Task 1 测试 — 把 T-prefix-E 临时 skip：

```python
@pytest.mark.skip(reason="Task 2 集成 scan loop 后启用")
def test_t_prefix_e_from_eq_to_with_path_prefix_allowed(tmp_path: Path) -> None:
    ...
```

跑 4 测试 GREEN：
```bash
pytest tests/dev/test_rebrand_test_archive.py -v -k "prefix_d or prefix_f or drive_letter or base_validation" 2>&1 | tail -10
```

Expected: 4 PASS

### Step 6: 全 jury/dev 子集回归

```bash
pytest -q tests/dev/ 2>&1 | tail -5
```

Expected: 既有 v2.37.8 16 unit + 1 integration 不回归 + 4 新 PASS / 1 skip / 0 regression

### Step 7: dev_sync + Commit

```bash
python scripts/dev_sync.py 2>&1 | tail -3
git add tools/dev/rebrand_test_archive.py tests/dev/test_rebrand_test_archive.py
git -c commit.gpgsign=false commit -m "feat(rebrand): argparse 加 --from/--to-path-prefix + _validate_path_prefix helper（§11-N9 改动 1 task 1）

argparse 加 2 互锁 flag --from-path-prefix / --to-path-prefix。
新加 5 helper:
- _looks_like_abs_path: drive letter 校验（不变量 #15）
- _normalize_path: \\ vs / 跨 separator 兼容（rev 2 D3）
- _matches_prefix: prefix 边界匹配（紧跟 \\）防越界
- _rewrite_prefix: 保 value 原 separator 风格
- _validate_path_prefix: 独立校验 (rev 2 B1 不绕过 base validations)

TDD 4 测试 PASS（T-prefix-D 互锁 / T-prefix-F from==to+无 prefix exit=2 /
T-drive-letter / T-base-validation rev 3 B1 fix）；T-prefix-E skip 留 Task 2。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
"
```

---

## Task 2: scan loop 集成 path-prefix rewrite + TDD T-prefix-A/B/C/G/H/I + T-prefix-E

**Files:**
- Modify: `tools/dev/rebrand_test_archive.py` (scan loop 加 path-prefix rewrite path)
- Modify: `tests/dev/test_rebrand_test_archive.py` (加 6 TDD + 启用 T-prefix-E)

**预计:** 30 分钟

### Step 1: 写 TDD T-prefix-A/B/C/G/H/I（不动 v2.37.8 既有 _process_file）

打开 `tests/dev/test_rebrand_test_archive.py`，末尾追加：

```python
def test_t_prefix_a_string_field_prefix_replace(tmp_path: Path) -> None:
    """T-prefix-A — string 字段含 prefix 真替换。"""
    arch = _make_archive_tempdir(
        tmp_path,
        {"a.json": {"subsystem": "old", "render_dir": "D:\\Work\\OLD\\cad\\output"}},
    )
    
    cp = _run(
        str(arch),
        "--from", "old", "--to", "new",
        "--from-path-prefix", "D:\\Work\\OLD",
        "--to-path-prefix", "D:\\Work\\NEW",
        "--apply",
    )
    
    assert cp.returncode == 0, cp.stderr
    data = json.loads((arch / "a.json").read_text(encoding="utf-8"))
    assert data["subsystem"] == "new"
    assert data["render_dir"] == "D:\\Work\\NEW\\cad\\output"


def test_t_prefix_b_dict_nested_subsystem_not_path(tmp_path: Path) -> None:
    """T-prefix-B — dict-nested subsystem.name 不被当 path-prefix 解释。"""
    arch = _make_archive_tempdir(
        tmp_path,
        {"a.json": {"subsystem": {"name": "old"}, "render_dir": "D:\\Work\\OLD"}},
    )
    
    cp = _run(
        str(arch),
        "--from", "old", "--to", "new",
        "--from-path-prefix", "D:\\Work\\OLD",
        "--to-path-prefix", "D:\\Work\\NEW",
        "--apply",
    )
    
    assert cp.returncode == 0, cp.stderr
    data = json.loads((arch / "a.json").read_text(encoding="utf-8"))
    assert data["subsystem"]["name"] == "new"  # dict-nested subsystem 仍 rewrite
    assert data["render_dir"] == "D:\\Work\\NEW"  # path rewrite


def test_t_prefix_c_nested_list_recursive(tmp_path: Path) -> None:
    """T-prefix-C — 嵌套 list[dict] 递归改 (files[].path_abs_resolved)。"""
    arch = _make_archive_tempdir(
        tmp_path,
        {
            "manifest.json": {
                "subsystem": "x",
                "render_dir": "D:\\Work\\OLD",
                "files": [
                    {"path_abs_resolved": "D:\\Work\\OLD\\f1.png"},
                    {"path_abs_resolved": "D:\\Work\\OLD\\f2.png"},
                ],
            }
        },
    )
    
    cp = _run(
        str(arch),
        "--from", "x", "--to", "x",
        "--from-path-prefix", "D:\\Work\\OLD",
        "--to-path-prefix", "D:\\Work\\NEW",
        "--apply",
    )
    
    assert cp.returncode == 0, cp.stderr
    data = json.loads((arch / "manifest.json").read_text(encoding="utf-8"))
    assert data["files"][0]["path_abs_resolved"] == "D:\\Work\\NEW\\f1.png"
    assert data["files"][1]["path_abs_resolved"] == "D:\\Work\\NEW\\f2.png"


def test_t_prefix_g_idempotent_rerun(tmp_path: Path) -> None:
    """T-prefix-G — idempotent rerun 零写盘。"""
    arch = _make_archive_tempdir(
        tmp_path,
        {"a.json": {"subsystem": "x", "render_dir": "D:\\Work\\OLD"}},
    )
    _run(  # 第 1 次
        str(arch),
        "--from", "x", "--to", "x",
        "--from-path-prefix", "D:\\Work\\OLD",
        "--to-path-prefix", "D:\\Work\\NEW",
        "--apply",
    )
    sha_before = _sha256(arch / "a.json")
    
    cp = _run(  # 第 2 次同参数
        str(arch),
        "--from", "x", "--to", "x",
        "--from-path-prefix", "D:\\Work\\OLD",
        "--to-path-prefix", "D:\\Work\\NEW",
        "--apply",
    )
    
    assert cp.returncode == 0
    assert _sha256(arch / "a.json") == sha_before  # 零写盘


def test_t_prefix_h_boundary_match_no_overreach(tmp_path: Path) -> None:
    """T-prefix-H — prefix 边界匹配防越界 (rev 2 D1 R1 fix)。
    
    prefix = "D:\\Work\\OLD" 不应匹配 "D:\\Work\\OLD-backup\\..."
    """
    arch = _make_archive_tempdir(
        tmp_path,
        {
            "a.json": {
                "subsystem": "x",
                "render_dir": "D:\\Work\\OLD-backup\\cad",  # 不应匹配
                "render_dir2": "D:\\Work\\OLD\\cad",  # 应匹配
            }
        },
    )
    
    cp = _run(
        str(arch),
        "--from", "x", "--to", "x",
        "--from-path-prefix", "D:\\Work\\OLD",
        "--to-path-prefix", "D:\\Work\\NEW",
        "--apply",
    )
    
    assert cp.returncode == 0, cp.stderr
    data = json.loads((arch / "a.json").read_text(encoding="utf-8"))
    assert data["render_dir"] == "D:\\Work\\OLD-backup\\cad"  # 边界未匹配，未改
    assert data["render_dir2"] == "D:\\Work\\NEW\\cad"  # 边界匹配，改


def test_t_prefix_i_exact_match_end_of_string(tmp_path: Path) -> None:
    """T-prefix-I — exact match end-of-string 改 (边界 case)。"""
    arch = _make_archive_tempdir(
        tmp_path,
        {"a.json": {"subsystem": "x", "render_dir": "D:\\Work\\OLD"}},  # exact match
    )
    
    cp = _run(
        str(arch),
        "--from", "x", "--to", "x",
        "--from-path-prefix", "D:\\Work\\OLD",
        "--to-path-prefix", "D:\\Work\\NEW",
        "--apply",
    )
    
    assert cp.returncode == 0, cp.stderr
    data = json.loads((arch / "a.json").read_text(encoding="utf-8"))
    assert data["render_dir"] == "D:\\Work\\NEW"  # exact match end → 改
```

### Step 2: 启用 T-prefix-E（删 skip 装饰器）

找 `@pytest.mark.skip(reason="Task 2 集成 scan loop 后启用")` 删除，让 T-prefix-E active。

### Step 3: 跑测试验证 7 FAIL（RED — scan loop 未集成 path-prefix rewrite）

```bash
pytest tests/dev/test_rebrand_test_archive.py -v -k "prefix_a or prefix_b or prefix_c or prefix_e or prefix_g or prefix_h or prefix_i" 2>&1 | tail -20
```

Expected: 7 FAIL（path 字段未改写）

### Step 4: scan loop 集成 path-prefix rewrite

打开 `tools/dev/rebrand_test_archive.py`，找 `_scan` 函数（line ~140）。需要：

1. 加 `from_path_prefix` + `to_path_prefix` 参数
2. 每个 JSON 文件 load 后扫所有 string value 递归 + path-prefix replace
3. 既有 _process_file subsystem rewrite path 保留不动

实际加 helper `_rewrite_path_in_data`（递归扫 dict/list/string）：

```python
def _rewrite_path_in_data(
    data: Any, from_prefix: str, to_prefix: str,
) -> tuple[Any, int]:
    """递归扫 dict/list 的 string value，含 prefix 即 rewrite。
    
    返 (new_data, num_changed) — num_changed > 0 表示有改写。
    """
    if isinstance(data, str):
        if _matches_prefix(data, from_prefix):
            return _rewrite_prefix(data, from_prefix, to_prefix), 1
        return data, 0
    if isinstance(data, dict):
        new_dict = {}
        total = 0
        for k, v in data.items():
            new_v, n = _rewrite_path_in_data(v, from_prefix, to_prefix)
            new_dict[k] = new_v
            total += n
        return new_dict, total
    if isinstance(data, list):
        new_list = []
        total = 0
        for item in data:
            new_item, n = _rewrite_path_in_data(item, from_prefix, to_prefix)
            new_list.append(new_item)
            total += n
        return new_list, total
    return data, 0
```

改 `_scan` 函数（找 `def _scan(archive_dir: Path, args_from: str, args_to: str, apply: bool) -> int:` 改签名 + 行为）：

```python
def _scan(
    archive_dir: Path,
    args_from: str,
    args_to: str,
    apply: bool,
    from_path_prefix: str | None = None,
    to_path_prefix: str | None = None,
) -> int:
    candidates: list[tuple[Path, str, dict[str, Any]]] = []
    for root, dirs, files in os.walk(archive_dir, followlinks=False):
        dirs[:] = [d for d in dirs if not _should_skip_dir(d)]
        for name in files:
            if not name.endswith(".json"):
                continue
            path = Path(root) / name
            # 既有 _process_file subsystem rewrite path（保留不动）
            action, data = _process_file(path, args_from, args_to)
            
            # 新加 path-prefix rewrite（rev 2/3）
            if from_path_prefix is not None and to_path_prefix is not None:
                # 必须先 read data（如果 subsystem 路径未 read），否则 _process_file 走 skip 路径不 read
                if data is None:
                    # subsystem rewrite skip — 但 path-prefix rewrite 仍需 read
                    try:
                        raw = path.read_bytes()
                        text = raw.decode("utf-8-sig")
                        data_for_path = json.loads(text)
                    except (UnicodeDecodeError, json.JSONDecodeError, OSError):
                        # 既有 _process_file 已 emit WARN，跳过 path rewrite
                        continue
                else:
                    data_for_path = data  # subsystem 改后的 data 继续 path rewrite
                
                new_data, num_path_changed = _rewrite_path_in_data(
                    data_for_path, from_path_prefix, to_path_prefix,
                )
                
                if num_path_changed > 0:
                    if action in ("candidate_a", "candidate_b"):
                        # subsystem + path 同改
                        location = "subsystem" if action == "candidate_a" else "subsystem.name"
                        candidates.append((path, location + f" + {num_path_changed} path", new_data))
                    else:
                        # 仅 path rewrite
                        candidates.append((path, f"{num_path_changed} path", new_data))
                    continue  # 跳过下面 action log emit
            
            # 既有 action log emit（保留 v2.37.8 既有行为）
            if action == "candidate_a":
                location = "subsystem"
            elif action == "candidate_b":
                location = "subsystem.name"
            else:
                # 非 candidate 路径直接 log + continue（既有逻辑）
                if action == "warn_invalid":
                    print(f"[WARN] {path}: invalid JSON, skipped", file=sys.stderr)
                elif action == "warn_encoding":
                    print(f"[WARN] {path}: encoding not utf-8/utf-8-sig, skipped", file=sys.stderr)
                elif action == "warn_too_large":
                    print(f"[WARN] {path}: file >50MB, skipped", file=sys.stderr)
                elif action == "warn_type":
                    print(f"[WARN] {path}: subsystem type mismatch, skipped", file=sys.stderr)
                elif action == "skip_idempotent":
                    print(f"[SKIP] {path}: subsystem already {args_to!r}, idempotent", file=sys.stderr)
                elif action == "skip_not_matched":
                    print(f"[SKIP] {path}: subsystem not matched, skipped", file=sys.stderr)
                continue
            assert data is not None
            candidates.append((path, location, data))
    
    # 既有 dry-run + apply 逻辑保留
    if not candidates:
        print(f"[SKIP] no candidates found in {archive_dir}", file=sys.stderr)
        return 0
    
    if not apply:
        for path, location, _ in candidates:
            print(f"[DRY] {path}: {location} rewrite", file=sys.stderr)
        print(f"△ {len(candidates)} files would change (run with --apply)", file=sys.stderr)
        return 0
    
    success = 0
    for path, location, data in candidates:
        try:
            _atomic_write(path, data)
            print(f"[APPLY] {path}: {location} updated", file=sys.stderr)
            success += 1
        except (OSError, PermissionError) as exc:
            print(
                f"[WARN] {path}: write failed ({exc.__class__.__name__}: {exc}), skipped",
                file=sys.stderr,
            )
    print(f"✓ {success} files updated", file=sys.stderr)
    return 0
```

改 `main()` 调用方传新参数（找 `return _scan(...)` 替换）：

```python
    return _scan(
        args.archive_dir, args.from_, args.to, args.apply,
        from_path_prefix=args.from_path_prefix,
        to_path_prefix=args.to_path_prefix,
    )
```

### Step 5: 跑 7 测试 GREEN

```bash
pytest tests/dev/test_rebrand_test_archive.py -v -k "prefix_a or prefix_b or prefix_c or prefix_e or prefix_g or prefix_h or prefix_i" 2>&1 | tail -15
```

Expected: 7 PASS

### Step 6: 跑全 dev 子集回归（含 v2.37.8 既有 16 unit + 1 integration）

```bash
pytest -q tests/dev/ 2>&1 | tail -5
```

Expected: 16 v2.37.8 既有 + 9 新 (Task 1 4 + Task 2 5)(T-prefix-E 启用算 Task 2 计 6, 但 Task 1 Step 5 临时 skip 跑 4) — 总 25 PASS + 1 integration skip / 0 regression

### Step 7: dev_sync + Commit

```bash
python scripts/dev_sync.py 2>&1 | tail -3
git add tools/dev/rebrand_test_archive.py tests/dev/test_rebrand_test_archive.py
git -c commit.gpgsign=false commit -m "feat(rebrand): scan loop 集成 path-prefix rewrite + 7 新 TDD（§11-N9 task 2）

加 _rewrite_path_in_data 递归扫 dict/list/string 含 prefix 即 rewrite。
_scan 改签名加 from_path_prefix/to_path_prefix 可选参数；与既有
subsystem rewrite 并行扫；可同改 subsystem + path 同一文件。

7 新 TDD（启用 Task 1 skip 的 T-prefix-E）:
- T-prefix-A string field prefix replace
- T-prefix-B dict-nested subsystem.name 不被当 path
- T-prefix-C nested list[dict] 递归 (files[].path_abs_resolved)
- T-prefix-E from==to subsystem + path-prefix → 仅 path rewrite
- T-prefix-G idempotent rerun 零写盘
- T-prefix-H boundary 防越界 (cad-spec-gen-backup 不匹配)
- T-prefix-I exact match end-of-string

dev 子集 25 PASS + 1 skip / 0 regression（含 v2.37.8 既有 16 unit
+ Task 1 4 + Task 2 7（含 启用 E））。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
"
```

---

## Task 3: 全套件 + dev_sync 终验

**Files:** 无（验证 only）

**预计:** 5 分钟

### Step 1: dev_sync --check

```bash
cd D:/Work/cad-spec-gen
python scripts/dev_sync.py --check 2>&1 | tail -3
```

Expected: clean

### Step 2: jury + jury_loop + dev 子集

```bash
pytest -q tests/jury/ tests/jury_loop/ tests/dev/ 2>&1 | tail -5
```

Expected: 0 regression（v2.37.9 main baseline 3228 + 本 PR 新 9 = 3237 子集）

### Step 3: 全套件冒烟（60s timeout）

```bash
pytest -q --timeout 60 tests/ 2>&1 | tail -5
```

Expected: 全套件 3237+ PASS / ~18 skip / 0 regression

### Step 4: branch state

```bash
git log --oneline main..feat/v2-37-10-rebrand-path-real-retry
```

Expected: 3 spec commit + 1 plan commit (after writing-plans 实施) + 2 implementation commit = 6 commit

---

## Task 4: 真 retry 闭环实测前置 — 2 步 ops 流程

**Files:** 无 git（外部 cad-tests 跑）

**预计:** 5 分钟（不含 retry round 实测时间）

### Step 1: 确认 GISBOT marker + mixed state

```bash
ls -la D:/Work/cad-tests/GISBOT/.test-archive-marker
cd D:/Work/cad-tests/GISBOT
python -c "
import json
d = json.load(open('cad/output/renders/render_manifest.json', encoding='utf-8'))
print('顶层 render_dir:', d.get('render_dir'))
print('files[0].path_abs_resolved:', d.get('files', [{}])[0].get('path_abs_resolved'))
"
```

Expected: marker 存在 / mixed state 已 verify Task 0

### Step 2: 第 1 步 reverse unify (D:/Work/cad-tests/GISBOT → D:\Work\cad-spec-gen)

```bash
cd D:/Work/cad-spec-gen
python tools/dev/rebrand_test_archive.py D:/Work/cad-tests/GISBOT \
  --from end_effector --to end_effector \
  --from-path-prefix "D:/Work/cad-tests/GISBOT" \
  --to-path-prefix "D:\\Work\\cad-spec-gen" \
  --apply 2>&1 | tail -10
```

Expected: `[APPLY] xx files updated` — 2-3 manifest 内顶层 path 反 patched 回源

### Step 3: 第 2 步 forward rebrand (D:\Work\cad-spec-gen → D:\Work\cad-tests\GISBOT)

⚠️ **rev 3 B5 WARNING — 与 Step 2 必须连续无中断**

```bash
python tools/dev/rebrand_test_archive.py D:/Work/cad-tests/GISBOT \
  --from end_effector --to end_effector \
  --from-path-prefix "D:\\Work\\cad-spec-gen" \
  --to-path-prefix "D:\\Work\\cad-tests\\GISBOT" \
  --apply 2>&1 | tail -10
```

Expected: `[APPLY] xx files updated` — 全部 path 字段（4 manifest 含 ~140 path values）改为 GISBOT 副本路径

### Step 4: verify path 字段全 unified

```bash
cd D:/Work/cad-tests/GISBOT
grep -rl "cad-spec-gen" --include="*.json" -- . 2>&1 | grep -v _archive | head -5
```

Expected: 仅 rel path (如 `model_contract_path: cad/end_effector/.cad-spec-gen/...`) 含 `cad-spec-gen` 字面；**0 abs path 含源 prefix**

```bash
python -c "
import json
d = json.load(open('cad/output/renders/render_manifest.json', encoding='utf-8'))
assert 'cad-spec-gen' not in d['render_dir'], 'render_dir 仍含源 prefix'
assert 'cad-tests' in d['render_dir'], 'render_dir 应含 GISBOT 副本 prefix'
print('✓ render_dir:', d['render_dir'])
print('✓ files[0].path_abs_resolved:', d['files'][0]['path_abs_resolved'])
"
```

Expected: 全 unified 到 GISBOT 副本 path

无 git 改动（实测在外部 archive 跑）。

---

## Task 5: 真 retry 闭环实测 — cad_pipeline enhance-check

**Files:** 无 git

**预计:** 15 分钟 + ~$0.30-0.50 cost

### Step 1: 设 env vars

```bash
export GEMINI_API_KEY="sk-G40y5dea43zMIecEk13OPG9BslkBu75fUUIbj7vjGySDknG7"  # v2.37.9 实测 vendor 同 key
export PYTHONPATH="D:/Work/cad-spec-gen"
export PYTHONIOENCODING=utf-8  # Windows GBK fix
```

### Step 2: 跑 cad_pipeline enhance-check

```bash
cd D:/Work/cad-tests/GISBOT
python D:/Work/cad-spec-gen/src/cad_spec_gen/data/python_tools/cad_pipeline.py \
  enhance-check --subsystem end_effector \
  --dir cad/output/renders/end_effector/20260513T115709Z \
  2>&1 | tee /tmp/v2-37-10-real-retry.log
```

**预期行为**：

- 不撞 `render_dir mismatch` block（path-prefix 已 rebrand）
- jury 初评 verdict=needs_review (v2.37.9 已 verify)
- orchestrator 触发 retry round (v2.37.9 改动 1b/1f 已 wire)
- enhance vendor 重渲（用 micuapi.ai 同 backend / kind default gemini_chat_image）
- 重评 jury / `_pick_best` 选高分

### Step 3: 读 PHOTO3D_JURY_REPORT.json 真值 + AC 验证

```bash
cd D:/Work/cad-tests/GISBOT
python -c "
import json, glob, os
candidates = glob.glob('cad/end_effector/.cad-spec-gen/runs/20260513T115709Z/PHOTO3D_JURY_REPORT*.json')
candidates.sort(key=os.path.getmtime, reverse=True)
latest = candidates[0] if candidates else 'NONE'
print('newest report:', latest)
d = json.load(open(latest, encoding='utf-8'))
print('top status:', d.get('status'))
print('overall_photoreal:', d.get('overall_photoreal'))
print()
for v in d.get('views', []):
    name = v.get('view') or '?'
    score = v.get('photoreal_score')
    verdict = v.get('verdict')
    print(f'{name}: photoreal={score} verdict={verdict}')
print()
# AC 验证
scores = [v.get('photoreal_score') for v in d.get('views', [])]
ge60_count = sum(1 for s in scores if s and s >= 60)
print(f'AC-5: photoreal >=60 views: {ge60_count}/{len(scores)}')
print(f'AC-5 fallback: vendor 能力不足 photoreal 未达 60 → 不阻 PR')
"
```

Expected：
- AC-5 best case: ≥4/7 view photoreal ≥60 / top status=accepted
- AC-5 fallback: < 60 → retro 标实测结果，§11-N7 follow-up

### Step 4: 实测 cost 读

```bash
# jury_review_input.json 内含 cost 字段
cd D:/Work/cad-tests/GISBOT
python -c "
import json
try:
    d = json.load(open('cad/end_effector/.cad-spec-gen/runs/20260513T115709Z/jury_review_input.json', encoding='utf-8'))
    print('total_cost_usd:', d.get('total_cost_usd', 'NA'))
    print('retry_rounds:', d.get('retry_rounds', 'NA'))
except FileNotFoundError:
    print('jury_review_input.json not found - status 可能不是 accepted')
"
```

Expected: cost ≤ $0.50 budget

### Step 5: 实测真值写到外部归档（不进 git）

```bash
mkdir -p /tmp
cat > /tmp/v2-37-10-real-retry-result.txt << 'EOF'
v2.37.10 真 retry 闭环实测结果（2026-05-16）:
- photoreal scores: [..., ..., ...]
- top status: ...
- retry rounds: ...
- cost: $X.XX
- AC-3: render_dir mismatch 消除 Y/N
- AC-4: retry round ≥1 真启动 Y/N
- AC-5: photoreal ≥60 Y/N (或 fallback rationale)
- AC-6: cost ≤$0.50 Y/N
EOF
cat /tmp/v2-37-10-real-retry-result.txt
```

后续 Task 6 retro 引用此文件真值。

无 git commit（实测真值进 Task 6 retro）。

---

## Task 6: retro 文档

**Files:**
- Create: `docs/superpowers/reports/2026-05-16-v2-37-10-rebrand-path-real-retry-retro.md`

**预计:** 10 分钟

### Step 1: 写 retro

完整模板：

```markdown
# v2.37.10 — rebrand path-prefix 扩 + 真 retry 闭环实测（§11-N9）retro

> 关联 PR: TBD（Task 8 push 后填）  
> 关联 spec: docs/superpowers/specs/2026-05-16-v2-37-10-rebrand-path-real-retry-design.md (rev 3, 383 行, commit `a1f0647`)  
> 关联 plan: docs/superpowers/plans/2026-05-16-v2-37-10-rebrand-path-real-retry.md  
> Baseline: cad-spec-gen main@`6539912`（v2.37.9 merge）

## 摘要

v2.37.10 闭合 §11-N9 — v2.37.8 rebrand 工具扩 `--from-path-prefix` + `--to-path-prefix` 互锁 flag + 真 retry 闭环实测。**path-prefix 工具扩** + **真 retry 实测**双闭环。9 新 TDD + 0 regression / CI 8/8（pending push）/ GISBOT 实测 cost $X.XX。

## 完成项

### 改动 1 — rebrand 工具扩 path-prefix
- `tools/dev/rebrand_test_archive.py` 加 argparse 2 互锁 flag
- 5 新 helper：`_validate_path_prefix` / `_looks_like_abs_path` / `_normalize_path` / `_matches_prefix` / `_rewrite_prefix`
- `_scan` 加 `_rewrite_path_in_data` 递归扫 dict/list/string + prefix rewrite

### 改动 2 — 真 retry 闭环实测
- 2 步 ops 流程（reverse unify + forward rebrand）
- cad_pipeline enhance-check 端到端 / micuapi.ai 同 vendor
- 实测 cost / photoreal / status / retry round

## 实测真值（GISBOT 真 retry — 2026-05-16）

（实施期填，参 /tmp/v2-37-10-real-retry-result.txt）

| AC | 期望 | 实证 |
| --- | --- | --- |
| AC-3 render_dir mismatch 消除 | True | ... |
| AC-4 retry round ≥1 启动 | True | ... |
| AC-5 photoreal ≥60 | True (或 fallback 不退步) | ... |
| AC-6 cost ≤$0.50 | True | ... |

## 走过的弯路 / Plan-drift（subagent 实施期发现）

（实施期填）

## 4 层 review 实证

| 层 | 抓 | spec rev |
| --- | --- | --- |
| Layer 6 scout | 5 处实证 | rev 1 |
| self-review | 4 项过 | rev 1 inline |
| Layer 3 user review | 1 BLOCKER + 3 MAJOR + 3 MINOR | rev 1→rev 2 |
| 2nd boundary review | 1 BLOCKER + 1 MAJOR + 1 MINOR | rev 2→rev 3 |

## §11 follow-up 更新

- 闭合：§11-N9（rebrand path-prefix + 真 retry 闭环实测）
- 仍 open：
  - §12 f4 N≥50 批量场景成本评估
  - §11-N7 max_retries=3 升级（条件实测 fail）
  - 新登 §11-N10：多 prefix per run / atomic 2 步 sub-command（rule-of-three 触发）
  - 新登 §11-N11：path rewrite 后 sha 重算（条件实测 fail）

## 后续工作

按 §6 YAGNI：
- v2.37.11 候选：§11-N7 max_retries=3 / 端到端图像质量回归
- 360+ ruff cleanup
```

### Step 2: Commit retro

```bash
cd D:/Work/cad-spec-gen
git add docs/superpowers/reports/2026-05-16-v2-37-10-rebrand-path-real-retry-retro.md
git -c commit.gpgsign=false commit -m "docs(retro): v2.37.10 rebrand path-prefix + 真 retry 闭环实测 retro

§11-N9 闭合：rebrand 工具扩 path-prefix + 真 retry 闭环实测。
9 新 TDD + GISBOT 真 retry 实测 \$X.XX。
4 层 review (rev 1→3 含 1 BLOCKER + 1 MAJOR + 1 MINOR rev 3 fix)。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
"
```

---

## Task 7: PR push + CI

**Files:** 无（CI 操作）

**预计:** 5 分钟 + CI 等待

### Step 1: dev_sync --check + push

```bash
cd D:/Work/cad-spec-gen
python scripts/dev_sync.py --check 2>&1 | tail -3
git push -u origin feat/v2-37-10-rebrand-path-real-retry 2>&1 | tail -5
```

### Step 2: 开 PR

```bash
gh pr create --base main --head feat/v2-37-10-rebrand-path-real-retry \
  --title "feat(rebrand): v2.37.10 — rebrand path-prefix 扩 + 真 retry 闭环实测（§11-N9）" \
  --body "$(cat <<'EOF'
## 摘要

v2.37.10 闭合 §11-N9 — v2.37.8 rebrand 工具扩 `--from-path-prefix` + `--to-path-prefix` 互锁 flag + 真 retry 闭环实测验证。

| 改动 | 内容 |
| --- | --- |
| **1** | `rebrand_test_archive.py` 加 argparse 2 互锁 flag + 5 helper + scan loop 集成 |
| **2** | 真 retry 闭环实测（2 步 ops + cad_pipeline enhance-check + AC 验证）|
| **实测** | GISBOT cost \$X.XX < \$0.50 budget |

## 改动一览

| 文件 | 改动 |
| --- | --- |
| Modify \`tools/dev/rebrand_test_archive.py\` | argparse +2 flag + 5 helper + _scan 集成 path-prefix rewrite |
| Modify \`tests/dev/test_rebrand_test_archive.py\` | +9 unit TDD（T-prefix-A 到 I）|
| Create retro | v2.37.10 复盘含实测真值 |

## TDD + 回归

- ✅ **9 新 unit TDD PASS**（互锁 + drive letter + 边界 + 跨 separator + idempotent）
- ✅ dev 子集 25 PASS + 1 skip / 0 regression
- ✅ 全套件 3237+ PASS / 0 regression
- ⏳ CI 8/8（pending push）
- ✅ **真 retry 闭环实测** (Task 5 — \$X.XX cost / photoreal/status/retry round)

## spec 演进（3 rev + 真 vendor 实测）

- rev 1（290 行 brainstorm + scout 5 处 fix）
- rev 2（user review 1 BLOCKER + 3 MAJOR + 3 MINOR cascade fix）
- rev 3（2nd boundary review 1 BLOCKER + 1 MAJOR + 1 MINOR cascade）

## §11 follow-up 更新

- 闭合：§11-N9
- 新登：§11-N10 (多 prefix per run) + §11-N11 (sha 重算，条件触发)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)" 2>&1 | tail -3
```

### Step 3: 等 CI 8/8

```bash
gh pr checks --watch --interval 30
```

Expected: 8/8 SUCCESS

---

## Task 8: 等用户授权 merge + tag + Release + memory

**Files:** memory 文件

**预计:** 用户授权 + 5 min

### Step 1: 等用户授权 merge

CI 8/8 SUCCESS 后向用户报告 + 等"授权 squash merge + tag v2.37.10 + Release"决策。

### Step 2: Squash merge

```bash
gh pr merge <PR#> --squash --subject "..." --body "..."
```

### Step 3: Tag + Release

```bash
git fetch origin main && git checkout main && git pull --ff-only
git tag -a v2.37.10 -m "v2.37.10 — rebrand path-prefix + 真 retry 闭环实测"
git push origin v2.37.10
gh release create v2.37.10 --title "..." --notes "..."
```

### Step 4: Memory + MEMORY.md

写 `C:\Users\procheng\.claude\projects\D--Work-cad-spec-gen\memory\project_v2_37_10_done.md` + Edit MEMORY.md。

---

## Self-Review

**1. Spec 覆盖：**

| spec § | task | 覆盖 |
| --- | --- | --- |
| §3.1.1 CLI 接口（2 互锁 flag）| Task 1 Step 3c | ✓ |
| §3.1.2 _validate_path_prefix（base validations 先跑 / 互锁 / drive letter / from==to skip subsystem）| Task 1 Step 3b + Task 1 Step 1 TDD | ✓ |
| §3.1.3 跨 separator 处理（normalize / matches / rewrite）| Task 2 Step 4 helper + Task 2 Step 1 T-prefix-A/B | ✓ |
| §3.1.4 不变量 #12-18 | Task 1 Step 3 (16-18) + Task 2 Step 4 (12-15) | ✓ |
| §3.1.5 9 TDD T-prefix-A 到 I | Task 1 (D/E/F/drive/base) + Task 2 (A/B/C/G/H/I) | ✓ |
| §3.2.1 前置 ops 2 步 | Task 4 | ✓ |
| §3.2.2 enhance-check 实测 + backend kind | Task 5 | ✓ |
| §5 AC-1~10 | Task 1-3 (AC-1,2,7,8,10) + Task 4-5 (AC-3,4,5,6) + Task 7 (AC-9) | ✓ |
| §7 R6-R10 风险 | spec inline + Task 4 (R6/R9) + Task 5 (R5/R10) | ✓ |
| retro | Task 6 | ✓ |
| PR + tag + Release | Task 7+8 | ✓ |

无 spec gap。

**2. Placeholder scan：**
- Task 5 Step 4 cost / photoreal / status `[..., ..., ...]` — 占位（实测期填）OK
- Task 6 retro `（实施期填）` × 2 — 占位 OK
- Task 7 PR body / Task 8 PR# / tag notes — 占位 OK

无 plan failure 红旗。

**3. Type consistency：**
- `_validate_path_prefix(archive_dir, args_from, args_to, from_prefix, to_prefix)` 签名 Task 1 def + Task 1 main() 调用一致
- `_rewrite_path_in_data(data, from_prefix, to_prefix) -> tuple[Any, int]` Task 2 def + scan 调用一致
- `_matches_prefix(value, from_prefix)` Task 1 def + Task 2 _rewrite_path_in_data 调用一致
- `args.from_path_prefix` / `args.to_path_prefix` argparse dest 一致

无 type drift。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-16-v2-37-10-rebrand-path-real-retry.md`。

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task + 2 stage review；适合 8 task
2. **Inline Execution** — 主 agent batch 跑 + checkpoint

**Which approach?**
