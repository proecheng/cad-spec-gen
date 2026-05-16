# v2.37.8 — rebrand 工具 + §12 f1 doc + helper cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新建 `tools/dev/rebrand_test_archive.py` 自动 rewrite 测试归档 metadata + 同 PR 顺手 reconcile v2.37.7 spec §12 f1 stale 标记 + 清 photo3d_jury main() 与 helper 的 inline 重复。

**Architecture:** 三项合一 PR / 单 branch `feat/v2-37-8-rebrand-tool-cleanup` / subagent-driven TDD per task / 14 task 收尾 push PR。

**Tech Stack:** Python 3.11+ / pytest / argparse / tempfile / os.walk / json / fnmatch / hashlib (SHA-256 测试断言)

**Spec ref:** `docs/superpowers/specs/2026-05-16-v2-37-8-rebrand-tool-cleanup-design.md` (rev 5, 577 行, commit `4661a1b`)

---

## Task 0: Scout 假设验证（防 plan-drift）

**Files:** 无（grep only）

**预计:** 3 分钟

- [ ] **Step 1: 验证 `tools/dev/` 不存在 + hatch_build COPY_DIRS 含 tools**

Run:
```bash
cd D:/Work/cad-spec-gen
ls tools/dev/ 2>&1 | head -2
grep -nE "COPY_DIRS|tools/dev" hatch_build.py | head -5
```

Expected: `tools/dev/` "No such file" + `COPY_DIRS = {... "tools": "tools" ...}` at line 58-63

- [ ] **Step 2: 验证 pyproject.toml markers 现状**

Run:
```bash
grep -n "markers\|requires_test_archive\|requires_solidworks\|requires_jury_loop_e2e" pyproject.toml | head -10
```

Expected: `markers = [...]` 数组含 `requires_solidworks` + `requires_jury_loop_e2e`，**无** `requires_test_archive`（待加）

- [ ] **Step 3: 验证 photo3d_jury.py 当前 helper / inline 状态**

Run:
```bash
grep -n "_resolve_effective_subsystem\|effective_subsystem = args" tools/photo3d_jury.py
```

Expected:
- line 218: `def _resolve_effective_subsystem(args: argparse.Namespace) -> str:`
- line 304: `effective_subsystem = _resolve_effective_subsystem(args)`
- line 409: `effective_subsystem = _resolve_effective_subsystem(args)`
- line 498: 注释
- line 499: `effective_subsystem = args.subsystem`（inline 待改 helper 调用）

- [ ] **Step 4: 验证 v2.37.7 spec line 281 stale 标记仍在**

Run:
```bash
sed -n '281,283p' docs/superpowers/specs/2026-05-15-v2-37-7-jury-cli-improvements-design.md
```

Expected:
```
| §12 f1 | LOW | max_tokens sunset 条件 | 未闭合（batch 3）|
| §12 f4 | LOW | N≥50 批量场景成本评估 | 未闭合（batch 3）|
```

记录：§12 f4 行也是 "未闭合（batch 3）" 但**本 PR 不动 §12 f4 行**（spec §3.2 B4 fix 明示）。

- [ ] **Step 5: 验证 GISBOT/.test-archive-marker 当前不存在 + 8 类 JSON 真值**

Run:
```bash
ls -la D:/Work/cad-tests/GISBOT/.test-archive-marker 2>&1 | head -2
find D:/Work/cad-tests/GISBOT -maxdepth 5 -name "ENHANCEMENT_REPORT.json" -o -name "render_manifest.json" -o -name "render_config.json" -o -name "MODEL_CONTRACT.json" -o -name "PRODUCT_GRAPH.json" -o -name "CUSTOM_PARTS_AUDIT.json" -o -name "ARTIFACT_INDEX.json" -o -name "PHOTO3D_JURY_REPORT.json" 2>&1 | head -20
```

Expected: marker "No such file"；至少 8 类 metadata JSON 在 GISBOT 子目录中

**记录到 plan 执行 log**：所有 Step 1-5 实证全过 / 任何 mismatch BLOCK 实施重审 spec rev 5

---

## Task 1: 基础设施 — pyproject marker + tools/dev/ + tests/dev/

**Files:**
- Modify: `pyproject.toml` (line 89 markers 区域)
- Create: `tools/dev/__init__.py` (空)
- Create: `tests/dev/__init__.py` (空)

**预计:** 5 分钟

- [ ] **Step 1: 加 `requires_test_archive` marker 到 pyproject.toml**

修改 `pyproject.toml` markers 数组，在 `requires_jury_loop_e2e` 行之后加：

```toml
    "requires_test_archive: 需 D:/Work/cad-tests/<archive>/.test-archive-marker 标识合法测试归档；缺标识自动 skip",
```

完整 markers 段（参照现有格式）：

```toml
markers = [
    "blender: 需要 Blender 真实可执行；缺失自动 skip",
    "requires_solidworks: 需真实 SolidWorks + pywin32；缺任一自动 skip（不报 fail）",
    "requires_jury_loop_e2e: jury-loop L4 端到端 smoke；需 GEMINI_API_KEY ...",
    "requires_test_archive: 需 D:/Work/cad-tests/<archive>/.test-archive-marker 标识合法测试归档；缺标识自动 skip",
]
```

- [ ] **Step 2: 创建 `tools/dev/__init__.py` 空文件**

Run:
```bash
mkdir -p tools/dev
touch tools/dev/__init__.py
```

- [ ] **Step 3: 创建 `tests/dev/__init__.py` 空文件**

Run:
```bash
mkdir -p tests/dev
touch tests/dev/__init__.py
```

- [ ] **Step 4: pytest 跑 collection 不爆**

Run:
```bash
pytest --collect-only tests/ 2>&1 | tail -10
```

Expected: 全 collection 不报 collection error（tests/dev/ 空目录无测试也 OK）

- [ ] **Step 5: Commit 基础设施**

```bash
git add pyproject.toml tools/dev/__init__.py tests/dev/__init__.py
git -c commit.gpgsign=false commit -m "feat(dev-tool): 加 tools/dev/ + tests/dev/ + requires_test_archive marker（§11-N1 task 1）"
```

---

## Task 2: T1-T3 核心 TDD — dry-run / pattern A / pattern B

**Files:**
- Create: `tests/dev/conftest.py`
- Create: `tests/dev/test_rebrand_test_archive.py`
- Create: `tools/dev/rebrand_test_archive.py`

**预计:** 25 分钟

- [ ] **Step 1: 写 `tests/dev/conftest.py` 含 `_make_archive_tempdir` fixture**

完整内容（rev 5 B1 fix）：

```python
"""tests/dev/conftest.py — rebrand_test_archive 测试共用 fixture。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _make_archive_tempdir(
    tmp_path: Path,
    json_files: dict[str, dict[str, Any]] | None = None,
    *,
    include_marker: bool = True,
) -> Path:
    """tempdir 内 touch .test-archive-marker + 写 JSON 文件。

    rev 5 B1 fix：所有 T1-T14 测试 fixture 必含空 .test-archive-marker；
    T15 例外不 touch marker（专测 sentinel 缺失 exit=2）。

    Args:
        tmp_path: pytest 标准 tmp_path fixture
        json_files: {relpath: dict_content} 映射；None 表示不写 JSON
        include_marker: True touch .test-archive-marker / False 不 touch（T15 用）

    Returns:
        tmp_path（同传入）
    """
    if include_marker:
        (tmp_path / ".test-archive-marker").touch()
    for relpath, content in (json_files or {}).items():
        p = tmp_path / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(content, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    return tmp_path


__all__ = ["_make_archive_tempdir"]
```

- [ ] **Step 2: 写失败测试 T1（dry-run 默认不写）+ T2（pattern A apply）+ T3（pattern B apply）**

创建 `tests/dev/test_rebrand_test_archive.py`：

```python
"""tests/dev/test_rebrand_test_archive.py — §11-N1 rebrand 工具 TDD 套件。"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.dev.conftest import _make_archive_tempdir

_TOOL = "tools/dev/rebrand_test_archive.py"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """执行工具，cwd 默认 repo root。"""
    return subprocess.run(
        [sys.executable, _TOOL, *args],
        capture_output=True,
        text=True,
        cwd=cwd or Path(__file__).resolve().parents[2],
    )


def test_t1_dry_run_does_not_write(tmp_path: Path) -> None:
    """T1 (rev 5 layer 2 角色 3.1 — SHA-256 跨平台精度防御)"""
    arch = _make_archive_tempdir(
        tmp_path,
        {"a.json": {"subsystem": "old"}},
    )
    sha_before = _sha256(arch / "a.json")

    cp = _run(str(arch), "--from", "old", "--to", "new")

    assert cp.returncode == 0, cp.stderr
    assert _sha256(arch / "a.json") == sha_before
    assert "[DRY]" in cp.stderr


def test_t2_apply_pattern_a_string(tmp_path: Path) -> None:
    """T2 — pattern A: 顶层 subsystem string 改写。"""
    arch = _make_archive_tempdir(
        tmp_path,
        {"a.json": {"subsystem": "old", "other": "keep"}},
    )

    cp = _run(str(arch), "--from", "old", "--to", "new", "--apply")

    assert cp.returncode == 0, cp.stderr
    data = json.loads((arch / "a.json").read_text(encoding="utf-8"))
    assert data["subsystem"] == "new"
    assert data["other"] == "keep"
    assert "[APPLY]" in cp.stderr


def test_t3_apply_pattern_b_dict_nested(tmp_path: Path) -> None:
    """T3 — pattern B: subsystem.name dict-nested 改写（name_cn 保留）。"""
    arch = _make_archive_tempdir(
        tmp_path,
        {
            "b.json": {
                "subsystem": {
                    "name": "old",
                    "name_cn": "保留中文",
                    "part_prefix": "GIS-EE",
                }
            }
        },
    )

    cp = _run(str(arch), "--from", "old", "--to", "new", "--apply")

    assert cp.returncode == 0, cp.stderr
    data = json.loads((arch / "b.json").read_text(encoding="utf-8"))
    assert data["subsystem"]["name"] == "new"
    assert data["subsystem"]["name_cn"] == "保留中文"  # name_cn 不改
    assert data["subsystem"]["part_prefix"] == "GIS-EE"  # 其他字段不改
    assert "[APPLY]" in cp.stderr
```

- [ ] **Step 3: 跑测试验证全 FAIL（RED）**

Run:
```bash
pytest tests/dev/test_rebrand_test_archive.py -v 2>&1 | tail -15
```

Expected: 3 FAIL with `FileNotFoundError: tools/dev/rebrand_test_archive.py` or similar

- [ ] **Step 4: 写 minimal `tools/dev/rebrand_test_archive.py` 让 T1+T2+T3 PASS**

创建工具最小骨架（先实现 sentinel 校验 + scan + pattern A/B + dry-run/apply）：

```python
"""tools/dev/rebrand_test_archive.py — §11-N1 测试归档 metadata rebrand 工具 (v2.37.8)。

scan-all + dual-schema-aware + cross-platform-safe + archive sentinel marker。

CLI:
  python tools/dev/rebrand_test_archive.py <archive_dir> --from <old> --to <new> [--apply]

archive_dir 必须含 .test-archive-marker 文件（防误传 production repo）。
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

_ARCHIVE_MARKER = ".test-archive-marker"
_SIZE_LIMIT = 50_000_000  # 50MB
_SKIP_DIRS = {
    ".git", ".venv", "__pycache__", "node_modules",
    ".tox", ".pytest_cache", ".mypy_cache", "build", "dist",
}


def _should_skip_dir(name: str) -> bool:
    return fnmatch.fnmatchcase(name, "_archive_*") or name in _SKIP_DIRS


def _atomic_write(target: Path, data: dict[str, Any]) -> None:
    """跨平台原子写盘 — failed cleanup tmp 残留。"""
    parent = target.parent
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=".rebrand_", suffix=".tmp", dir=parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=False)
            f.write("\n")
        os.replace(tmp_path, target)
    except OSError:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def _validate_inputs(archive_dir: Path, args_from: str, args_to: str) -> int:
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
    if not args_from or not args_to:
        print("[ERROR] --from/--to must be non-empty", file=sys.stderr)
        return 2
    if args_from == args_to:
        print("[ERROR] --from and --to must differ", file=sys.stderr)
        return 2
    for label, val in [("--from", args_from), ("--to", args_to)]:
        if any(c <= "\x1f" for c in val):
            print(f"[ERROR] {label} must not contain control chars", file=sys.stderr)
            return 2
        if "/" in val or "\\" in val:
            print(f"[ERROR] {label} must not contain path separators", file=sys.stderr)
            return 2
    return 0


def _process_file(path: Path, args_from: str, args_to: str) -> tuple[str, dict[str, Any] | None]:
    """处理单 JSON 文件，返 (action, data_to_write or None)。

    action ∈ {"candidate_a", "candidate_b", "skip_idempotent",
              "skip_not_matched", "skip_other", "warn_invalid", "warn_encoding",
              "warn_too_large", "warn_type"}
    """
    try:
        if path.stat().st_size > _SIZE_LIMIT:
            return "warn_too_large", None
    except OSError:
        return "skip_other", None

    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig")
        data = json.loads(text)
    except UnicodeDecodeError:
        return "warn_encoding", None
    except json.JSONDecodeError:
        return "warn_invalid", None
    except OSError:
        return "skip_other", None

    if not isinstance(data, dict):
        return "skip_other", None

    val = data.get("subsystem")
    if val is None:
        return "skip_other", None
    if isinstance(val, bool):
        return "warn_type", None
    if isinstance(val, str):
        if val == args_to:
            return "skip_idempotent", None
        if val != args_from:
            return "skip_not_matched", None
        data["subsystem"] = args_to
        return "candidate_a", data
    if isinstance(val, dict):
        if "name" not in val:
            return "warn_type", None
        nested = val.get("name")
        if not isinstance(nested, str):
            return "warn_type", None
        if nested == args_to:
            return "skip_idempotent", None
        if nested != args_from:
            return "skip_not_matched", None
        data["subsystem"]["name"] = args_to
        return "candidate_b", data

    return "warn_type", None


def _scan(archive_dir: Path, args_from: str, args_to: str, apply: bool) -> int:
    candidates: list[tuple[Path, str, dict[str, Any]]] = []
    for root, dirs, files in os.walk(archive_dir, followlinks=False):
        dirs[:] = [d for d in dirs if not _should_skip_dir(d)]
        for name in files:
            if not name.endswith(".json"):
                continue
            path = Path(root) / name
            action, data = _process_file(path, args_from, args_to)
            if action == "candidate_a":
                location = "subsystem"
            elif action == "candidate_b":
                location = "subsystem.name"
            else:
                # 非 candidate 路径直接 log + continue
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
                # skip_other 不 emit（无 subsystem key / not dict）
                continue
            assert data is not None
            candidates.append((path, location, data))

    if not candidates:
        print(f"[SKIP] no candidates found in {archive_dir}", file=sys.stderr)
        return 0

    if not apply:
        for path, location, _ in candidates:
            print(f"[DRY] {path}: {location} {args_from!r} → {args_to!r}", file=sys.stderr)
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


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="rebrand_test_archive",
        description=(
            "§11-N1 测试归档 metadata rebrand 工具 (v2.37.8)。\n"
            "scan-all + dual-schema-aware + cross-platform-safe + archive sentinel marker。"
        ),
        epilog=(
            "Examples:\n"
            "  python tools/dev/rebrand_test_archive.py D:/Work/cad-tests/GISBOT \\\n"
            "    --from end_effector --to GISBOT          # dry-run preview\n"
            "  python tools/dev/rebrand_test_archive.py D:/Work/cad-tests/GISBOT \\\n"
            "    --from end_effector --to GISBOT --apply  # actually write\n\n"
            "stderr legend:\n"
            "  [DRY]   candidate (would change if --apply)\n"
            "  [APPLY] successfully updated\n"
            "  [SKIP]  skipped (already target / no subsystem key / not matched)\n"
            "  [WARN]  warning (invalid JSON / IO error / type mismatch)\n"
            "  [ERROR] fatal error (input validation / dir not exist / missing marker)\n\n"
            "Safety:\n"
            "  archive_dir 必须含 `.test-archive-marker` 文件才接受\n"
            "  （防误传 production repo；marker 文件内容不约束）"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("archive_dir", type=Path, help="测试归档目录")
    parser.add_argument("--from", dest="from_", required=True, help="当前 subsystem 字面值")
    parser.add_argument("--to", required=True, help="目标 subsystem 字面值")
    parser.add_argument("--apply", action="store_true", help="真改写（缺省 dry-run preview）")
    args = parser.parse_args()

    rc = _validate_inputs(args.archive_dir, args.from_, args.to)
    if rc:
        return rc

    return _scan(args.archive_dir, args.from_, args.to, args.apply)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: 跑测试验证 T1+T2+T3 GREEN**

Run:
```bash
pytest tests/dev/test_rebrand_test_archive.py -v -k "t1 or t2 or t3" 2>&1 | tail -15
```

Expected: 3 PASS

- [ ] **Step 6: Commit Task 2**

```bash
git add tests/dev/conftest.py tests/dev/test_rebrand_test_archive.py tools/dev/rebrand_test_archive.py
git -c commit.gpgsign=false commit -m "feat(rebrand): T1+T2+T3 dry-run/pattern A/pattern B 核心 TDD（§11-N1 task 2）"
```

---

## Task 3: T4-T8 边界 TDD — mixed / idempotent / malformed / _archive_* / deny list

**Files:**
- Modify: `tests/dev/test_rebrand_test_archive.py`

**预计:** 15 分钟

- [ ] **Step 1: 加 T4-T8 失败测试到测试文件**

在测试文件末尾追加：

```python
def test_t4_mixed_archive(tmp_path: Path) -> None:
    """T4 — 混合 archive (A + B + 无 subsystem + bool + dict 无 name)。"""
    arch = _make_archive_tempdir(
        tmp_path,
        {
            "a.json": {"subsystem": "old"},  # pattern A → 改
            "b.json": {"subsystem": {"name": "old"}},  # pattern B → 改
            "c.json": {"other": "x"},  # 无 subsystem → skip
            "d.json": {"subsystem": True},  # bool → WARN skip
            "e.json": {"subsystem": {"part_prefix": "x"}},  # dict 无 name → WARN
        },
    )

    cp = _run(str(arch), "--from", "old", "--to", "new", "--apply")

    assert cp.returncode == 0, cp.stderr
    assert json.loads((arch / "a.json").read_text(encoding="utf-8"))["subsystem"] == "new"
    assert json.loads((arch / "b.json").read_text(encoding="utf-8"))["subsystem"]["name"] == "new"
    assert json.loads((arch / "c.json").read_text(encoding="utf-8")) == {"other": "x"}
    assert json.loads((arch / "d.json").read_text(encoding="utf-8")) == {"subsystem": True}
    assert "[APPLY]" in cp.stderr  # a + b
    assert "[WARN]" in cp.stderr  # d + e


def test_t5_idempotent_rerun(tmp_path: Path) -> None:
    """T5 — 二次 apply 零写盘。"""
    arch = _make_archive_tempdir(
        tmp_path,
        {"a.json": {"subsystem": "old"}},
    )
    _run(str(arch), "--from", "old", "--to", "new", "--apply")  # 第一次

    sha_before = _sha256(arch / "a.json")
    cp = _run(str(arch), "--from", "old", "--to", "new", "--apply")  # 第二次

    assert cp.returncode == 0
    assert _sha256(arch / "a.json") == sha_before  # 零写盘
    assert "no candidates found" in cp.stderr


def test_t6_malformed_json_skip(tmp_path: Path) -> None:
    """T6 — malformed JSON skip + WARN。"""
    arch = _make_archive_tempdir(tmp_path)
    (arch / "bad.json").write_text("{ not json", encoding="utf-8")
    (arch / "good.json").write_text(
        json.dumps({"subsystem": "old"}), encoding="utf-8"
    )

    cp = _run(str(arch), "--from", "old", "--to", "new", "--apply")

    assert cp.returncode == 0, cp.stderr
    assert "[WARN]" in cp.stderr
    assert "invalid JSON" in cp.stderr
    assert json.loads((arch / "good.json").read_text(encoding="utf-8"))["subsystem"] == "new"


def test_t7_archive_dir_pattern_skipped(tmp_path: Path) -> None:
    """T7 — _archive_* 子目录跳过（含 case-sensitive：_archive_ skip / _Archive_ 不 skip — Linux/macOS）。"""
    arch = _make_archive_tempdir(tmp_path)
    # _archive_xxx 子目录
    (arch / "_archive_20260513").mkdir()
    (arch / "_archive_20260513" / "old.json").write_text(
        json.dumps({"subsystem": "old"}), encoding="utf-8"
    )
    # 正常子目录
    (arch / "normal").mkdir()
    (arch / "normal" / "ok.json").write_text(
        json.dumps({"subsystem": "old"}), encoding="utf-8"
    )

    cp = _run(str(arch), "--from", "old", "--to", "new", "--apply")

    assert cp.returncode == 0, cp.stderr
    # _archive_ 子目录未扫
    assert (
        json.loads((arch / "_archive_20260513" / "old.json").read_text(encoding="utf-8"))[
            "subsystem"
        ]
        == "old"
    )
    # 正常子目录改写
    assert (
        json.loads((arch / "normal" / "ok.json").read_text(encoding="utf-8"))["subsystem"]
        == "new"
    )


def test_t8_deny_list_skipped(tmp_path: Path) -> None:
    """T8 — .git/ __pycache__/ 等普适目录跳过。"""
    arch = _make_archive_tempdir(tmp_path)
    for skip_dir in [".git", "__pycache__", "node_modules", ".pytest_cache"]:
        d = arch / skip_dir
        d.mkdir()
        (d / "old.json").write_text(json.dumps({"subsystem": "old"}), encoding="utf-8")

    cp = _run(str(arch), "--from", "old", "--to", "new", "--apply")

    assert cp.returncode == 0
    for skip_dir in [".git", "__pycache__", "node_modules", ".pytest_cache"]:
        data = json.loads((arch / skip_dir / "old.json").read_text(encoding="utf-8"))
        assert data["subsystem"] == "old", f"{skip_dir} 子目录被扫了"
```

- [ ] **Step 2: 跑测试验证 T4-T8 GREEN（实现已支持）**

Run:
```bash
pytest tests/dev/test_rebrand_test_archive.py -v -k "t4 or t5 or t6 or t7 or t8" 2>&1 | tail -20
```

Expected: 5 PASS（Task 2 实现已含 deny list + _archive_* + dual-schema）

- [ ] **Step 3: Commit Task 3**

```bash
git add tests/dev/test_rebrand_test_archive.py
git -c commit.gpgsign=false commit -m "feat(rebrand): T4-T8 边界 TDD — 混合/幂等/损坏/_archive_*/deny list（§11-N1 task 3）"
```

---

## Task 4: T9-T11 input validation TDD

**Files:**
- Modify: `tests/dev/test_rebrand_test_archive.py`

**预计:** 10 分钟

- [ ] **Step 1: 加 T9+T10+T11 input validation 测试**

测试文件末尾追加：

```python
def test_t9_from_equals_to_exit_2(tmp_path: Path) -> None:
    """T9 — --from == --to exit=2。"""
    arch = _make_archive_tempdir(tmp_path)

    cp = _run(str(arch), "--from", "x", "--to", "x", "--apply")

    assert cp.returncode == 2
    assert "must differ" in cp.stderr


def test_t10_archive_dir_not_exist_exit_2(tmp_path: Path) -> None:
    """T10 — archive_dir 不存在 exit=2。"""
    fake = tmp_path / "does_not_exist"

    cp = _run(str(fake), "--from", "a", "--to", "b", "--apply")

    assert cp.returncode == 2
    assert "not a directory" in cp.stderr


def test_t11_control_char_exit_2(tmp_path: Path) -> None:
    """T11 — --from 含控制字符 exit=2。"""
    arch = _make_archive_tempdir(tmp_path)

    cp = _run(str(arch), "--from", "a\x00b", "--to", "new", "--apply")

    assert cp.returncode == 2
    assert "control chars" in cp.stderr
```

- [ ] **Step 2: 跑测试验证 T9-T11 GREEN**

Run:
```bash
pytest tests/dev/test_rebrand_test_archive.py -v -k "t9 or t10 or t11" 2>&1 | tail -10
```

Expected: 3 PASS

- [ ] **Step 3: Commit Task 4**

```bash
git add tests/dev/test_rebrand_test_archive.py
git -c commit.gpgsign=false commit -m "feat(rebrand): T9-T11 input validation TDD（§11-N1 task 4）"
```

---

## Task 5: T12-T14 atomic / 大文件 / BOM

**Files:**
- Modify: `tests/dev/test_rebrand_test_archive.py`

**预计:** 15 分钟

- [ ] **Step 1: 加 T12+T13+T14 测试**

测试文件末尾追加：

```python
def test_t12_atomic_write_interrupt_no_residue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """T12 — mock os.replace raise / 原文件未改 / tempdir 无 .tmp 残留 (rev 5 B5 + layer 2 3.2)."""
    arch = _make_archive_tempdir(
        tmp_path,
        {"a.json": {"subsystem": "old"}},
    )
    original_content = (arch / "a.json").read_bytes()

    real_replace = os.replace

    def fail_replace(*args, **kwargs):
        raise OSError("simulated disk full")

    monkeypatch.setattr(os, "replace", fail_replace)

    cp = _run(str(arch), "--from", "old", "--to", "new", "--apply")

    # 工具内部 catch OSError → WARN + 继续 + exit=0
    assert cp.returncode == 0
    assert "[WARN]" in cp.stderr
    # 原文件未改
    assert (arch / "a.json").read_bytes() == original_content
    # 无 .tmp 残留
    tmps = list(arch.glob(".rebrand_*.tmp"))
    assert tmps == [], f"残留 tmp 文件: {tmps}"


def test_t13_large_file_skipped(tmp_path: Path) -> None:
    """T13 — 文件 >50MB skip + WARN。"""
    arch = _make_archive_tempdir(tmp_path)
    huge = arch / "huge.json"
    # 写 ~51MB JSON
    payload = '{"subsystem": "old", "padding": "' + ("x" * 51_000_000) + '"}'
    huge.write_text(payload, encoding="utf-8")

    cp = _run(str(arch), "--from", "old", "--to", "new", "--apply")

    assert cp.returncode == 0
    assert "[WARN]" in cp.stderr
    assert ">50MB" in cp.stderr


def test_t14_utf8_sig_bom_compat(tmp_path: Path) -> None:
    """T14 — utf-8-sig BOM 兼容。"""
    arch = _make_archive_tempdir(tmp_path)
    bom = arch / "bom.json"
    bom.write_bytes(b"\xef\xbb\xbf" + b'{"subsystem": "old"}')

    cp = _run(str(arch), "--from", "old", "--to", "new", "--apply")

    assert cp.returncode == 0, cp.stderr
    data = json.loads(bom.read_text(encoding="utf-8-sig"))
    assert data["subsystem"] == "new"
```

注意：T12 需 import os，文件顶部 import 区加 `import os`。

- [ ] **Step 2: 跑测试验证 T12-T14 GREEN**

Run:
```bash
pytest tests/dev/test_rebrand_test_archive.py -v -k "t12 or t13 or t14" 2>&1 | tail -15
```

Expected: 3 PASS（实现已含 atomic write + size guard + utf-8-sig decode）

- [ ] **Step 3: Commit Task 5**

```bash
git add tests/dev/test_rebrand_test_archive.py
git -c commit.gpgsign=false commit -m "feat(rebrand): T12-T14 atomic/大文件/BOM TDD（§11-N1 task 5）"
```

---

## Task 6: T15-T16 sentinel marker TDD

**Files:**
- Modify: `tests/dev/test_rebrand_test_archive.py`

**预计:** 8 分钟

- [ ] **Step 1: 加 T15+T16 sentinel 测试**

测试文件末尾追加：

```python
def test_t15_missing_marker_exit_2(tmp_path: Path) -> None:
    """T15 (rev 4 RISK-CRITICAL) — archive_dir 缺 .test-archive-marker exit=2。"""
    # 不调 _make_archive_tempdir / 不 touch marker
    arch = tmp_path
    (arch / "a.json").write_text(json.dumps({"subsystem": "old"}), encoding="utf-8")

    cp = _run(str(arch), "--from", "old", "--to", "new", "--apply")

    assert cp.returncode == 2
    assert ".test-archive-marker" in cp.stderr


def test_t16_with_marker_continues(tmp_path: Path) -> None:
    """T16 — marker 存在则继续（白盒）。"""
    arch = _make_archive_tempdir(
        tmp_path,
        {"a.json": {"subsystem": "old"}},
    )

    cp = _run(str(arch), "--from", "old", "--to", "new", "--apply")

    assert cp.returncode == 0, cp.stderr
    assert json.loads((arch / "a.json").read_text(encoding="utf-8"))["subsystem"] == "new"
```

- [ ] **Step 2: 跑全 16 测试验证全 GREEN**

Run:
```bash
pytest tests/dev/test_rebrand_test_archive.py -v 2>&1 | tail -25
```

Expected: 16/16 PASS

- [ ] **Step 3: Commit Task 6**

```bash
git add tests/dev/test_rebrand_test_archive.py
git -c commit.gpgsign=false commit -m "feat(rebrand): T15+T16 sentinel marker TDD — 16/16 PASS（§11-N1 task 6）"
```

---

## Task 7: 集成测试 + conftest skip 钩子

**Files:**
- Modify: `tests/dev/conftest.py` (加 pytest_collection_modifyitems skip 钩子)
- Create: `tests/dev/test_rebrand_test_archive_integration.py`

**预计:** 15 分钟

- [ ] **Step 1: 加 conftest pytest_collection_modifyitems 自动 skip requires_test_archive**

修改 `tests/dev/conftest.py`，追加：

```python
import pytest
from pathlib import Path as _Path  # 避免覆盖上面的 Path import


_GISBOT_MARKER = _Path("D:/Work/cad-tests/GISBOT/.test-archive-marker")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """rev 5 B2+B3 fix — 集成测 conftest skip 检 .test-archive-marker 真值契约。"""
    if _GISBOT_MARKER.is_file():
        return
    skip_reason = pytest.mark.skip(
        reason=(
            f"archive marker missing: run `touch {_GISBOT_MARKER}` to enable"
        )
    )
    for item in items:
        if "requires_test_archive" in item.keywords:
            item.add_marker(skip_reason)
```

- [ ] **Step 2: 写 GISBOT sandbox 集成测**

创建 `tests/dev/test_rebrand_test_archive_integration.py`：

```python
"""tests/dev/test_rebrand_test_archive_integration.py — GISBOT sandbox 集成测。

rev 5 B2 fix: conftest 自动检 .test-archive-marker 存在；缺则全 skip。
rev 5 B3 fix: 用户必先 touch D:/Work/cad-tests/GISBOT/.test-archive-marker；
              本 PR retro 记录该命令。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_GISBOT_DIR = Path("D:/Work/cad-tests/GISBOT")
_TOOL = "tools/dev/rebrand_test_archive.py"


@pytest.mark.requires_test_archive
def test_gisbot_sandbox_rebrand_end_to_end(tmp_path: Path) -> None:
    """集成测：sandbox copy GISBOT/ → --apply end_effector → GISBOT_REBRANDED → 验 8 类 JSON 改写 + _archive_*/ 未改。"""
    sandbox = tmp_path / "gisbot_sandbox"
    shutil.copytree(_GISBOT_DIR, sandbox, symlinks=False)

    # 跑 --apply
    cp = subprocess.run(
        [
            sys.executable,
            _TOOL,
            str(sandbox),
            "--from",
            "end_effector",
            "--to",
            "GISBOT_REBRANDED",
            "--apply",
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert cp.returncode == 0, f"工具失败：\n{cp.stderr}"

    # 验 8 类 JSON 已改
    targets = [
        ("02_codegen/CUSTOM_PARTS_AUDIT.json", "subsystem"),
        ("02_codegen/MODEL_CONTRACT.json", "subsystem"),
        ("02_codegen/PRODUCT_GRAPH.json", "subsystem"),
        ("02_codegen/render_config.json", "subsystem.name"),  # pattern B
        ("04_render/render_manifest.json", "subsystem"),
        ("05_enhance/ENHANCEMENT_REPORT.json", "subsystem"),
        # cad/end_effector/.cad-spec-gen/ARTIFACT_INDEX.json — 路径名也含 end_effector
        ("cad/end_effector/.cad-spec-gen/ARTIFACT_INDEX.json", "subsystem"),
    ]
    for relpath, location in targets:
        p = sandbox / relpath
        if not p.exists():
            continue  # 不是所有 GISBOT 副本都有完整 8 类
        data = json.loads(p.read_text(encoding="utf-8"))
        if location == "subsystem":
            assert data.get("subsystem") == "GISBOT_REBRANDED", f"{relpath}: 未改"
        elif location == "subsystem.name":
            assert data.get("subsystem", {}).get("name") == "GISBOT_REBRANDED", f"{relpath}: name 未改"
            # name_cn 字段保留
            assert "name_cn" in data["subsystem"], f"{relpath}: name_cn 字段丢失"

    # 验 _archive_*/ 路径未改（保历史快照）
    archive_dirs = list(sandbox.glob("_archive_*"))
    for arch_dir in archive_dirs:
        for json_file in arch_dir.rglob("*.json"):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8-sig"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if isinstance(data, dict):
                val = data.get("subsystem")
                if isinstance(val, str):
                    assert val != "GISBOT_REBRANDED", f"{json_file}: _archive_/ 被改"
                elif isinstance(val, dict) and isinstance(val.get("name"), str):
                    assert val["name"] != "GISBOT_REBRANDED", f"{json_file}: _archive_/ name 被改"
```

- [ ] **Step 3: 跑集成测验证（无 marker 应 skip）**

Run:
```bash
pytest tests/dev/test_rebrand_test_archive_integration.py -v 2>&1 | tail -10
```

Expected: 1 SKIP (`archive marker missing: run \`touch D:/Work/cad-tests/GISBOT/.test-archive-marker\` to enable`)

- [ ] **Step 4: Commit Task 7**

```bash
git add tests/dev/conftest.py tests/dev/test_rebrand_test_archive_integration.py
git -c commit.gpgsign=false commit -m "feat(rebrand): 集成测 + conftest skip 钩子（§11-N1 task 7）"
```

---

## Task 8: §12 f1 doc reconcile

**Files:**
- Modify: `docs/superpowers/specs/2026-05-15-v2-37-7-jury-cli-improvements-design.md:281`

**预计:** 3 分钟

- [ ] **Step 1: 改 §12 f1 行**

修改 line 281：

```diff
-| §12 f1 | LOW | max_tokens sunset 条件 | 未闭合（batch 3）|
+| §12 f1 | LOW | max_tokens 1024 sunset 条件（STATUS §9.3 #6）| closed v2.37.2 ✓（512→1024 实证）|
```

**注意**：line 282 §12 f4 行**不动**（rev 5 B4 fix — spec §3.2 明示）。

- [ ] **Step 2: grep verify**

Run:
```bash
grep -n "§12 f1\|§12 f4" docs/superpowers/specs/2026-05-15-v2-37-7-jury-cli-improvements-design.md
```

Expected:
```
281:| §12 f1 | LOW | max_tokens 1024 sunset 条件（STATUS §9.3 #6）| closed v2.37.2 ✓（512→1024 实证）|
282:| §12 f4 | LOW | N≥50 批量场景成本评估 | 未闭合（batch 3）|
```

§12 f4 行内容未动 ✓

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-05-15-v2-37-7-jury-cli-improvements-design.md
git -c commit.gpgsign=false commit -m "docs(jury): §12 f1 stale 标记 reconcile — closed v2.37.2 ✓"
```

---

## Task 9: helper cleanup

**Files:**
- Modify: `tools/photo3d_jury.py:497-512`

**预计:** 5 分钟

- [ ] **Step 1: 看当前 line 497-512 真值**

Run:
```bash
sed -n '497,512p' tools/photo3d_jury.py
```

记录当前形态（用于 minimal diff）。

- [ ] **Step 2: 改 main() 用 helper（顺序契约 rev 5 B5）**

打开 `tools/photo3d_jury.py` 找 line ~497-511 这段：

```python
    # v2.37.7 §11-N2: effective_subsystem 默认 = args.subsystem
    # effective_subsystem = args.override_subsystem or args.subsystem（默认零行为变化）
    effective_subsystem = args.subsystem
    ...
    if args.override_subsystem:
        # ... 输入校验... mutate args.override_subsystem.strip()
        effective_subsystem = args.override_subsystem
```

改为：

```python
    # 顺序契约（v2.37.8 §helper cleanup rev 5 B5）：
    # input validation 必须在 helper 调用前 — strip mutate args.override_subsystem，
    # _resolve_effective_subsystem 直接读 args.override_subsystem
    if args.override_subsystem:
        # ... 输入校验（保留 — TDD red 防误删 layer 2 R4） ...
        # 含 args.override_subsystem = args.override_subsystem.strip()

    # validation 完成后调 helper（顺序契约 — 不可调换）
    effective_subsystem = _resolve_effective_subsystem(args)
```

实际改动是删除两行 inline 计算 + 加一行 helper 调用（保留 if 块内 input validation）。

- [ ] **Step 3: 跑回归测试**

Run:
```bash
pytest tests/jury/test_photo3d_jury_progress.py -v 2>&1 | tail -10
```

Expected: 5/5 PASS（含 `test_override_subsystem_flag_used` + `test_override_subsystem_input_validation`）

- [ ] **Step 4: 跑 jury 子集回归**

Run:
```bash
pytest -q tests/jury/ tests/jury_loop/ 2>&1 | tail -5
```

Expected: 509 PASS / 0 regression

- [ ] **Step 5: dev_sync + commit**

```bash
python scripts/dev_sync.py 2>&1 | tail -3
git status -s | head -5  # 应 only tools/photo3d_jury.py + mirror
git add tools/photo3d_jury.py src/cad_spec_gen/data/tools/photo3d_jury.py
git -c commit.gpgsign=false commit -m "refactor(jury): photo3d_jury main() 改用 _resolve_effective_subsystem helper（§helper cleanup）"
```

---

## Task 10: retro 文档

**Files:**
- Create: `docs/superpowers/reports/2026-05-16-v2-37-8-rebrand-tool-cleanup-retro.md`

**预计:** 10 分钟

- [ ] **Step 1: 写 retro 文档**

完整内容模板：

```markdown
# v2.37.8 — rebrand 工具 + §12 f1 doc + helper cleanup retro

> 关联 PR: TBD  
> 关联 spec: docs/superpowers/specs/2026-05-16-v2-37-8-rebrand-tool-cleanup-design.md (rev 5, 577 行)  
> 关联 plan: docs/superpowers/plans/2026-05-16-v2-37-8-rebrand-tool-cleanup.md  
> Baseline: cad-spec-gen main@`05a50a5`（v2.37.7 merge）

## 摘要（1 段）

v2.37.8 闭合 §11-N1 (rebrand 工具) + §12 f1 (doc stale 标记) + helper cleanup。新建 `tools/dev/rebrand_test_archive.py` (~340 行 含详尽 docstring)；scan-all + dual-schema-aware + archive sentinel marker；16 unit + 1 integration test 全 PASS / jury 子集 509 PASS / 0 regression。

## 完成项

### §11-N1 — `tools/dev/rebrand_test_archive.py`
- scan-all + dual-schema-aware（pattern A string / pattern B `subsystem.name` dict-nested）
- archive sentinel marker `.test-archive-marker` 防误传 production
- ASCII label stderr ([DRY]/[APPLY]/[SKIP]/[WARN]/[ERROR])
- atomic write (tempfile.mkstemp + os.replace) 失败 cleanup tmp
- `_archive_*` glob + 普适开发目录 deny list (`os.walk dirnames[:]=...` 原地修剪)
- utf-8-sig BOM 兼容 / size guard 50MB / symlink 不跟 (followlinks=False)
- 16 单元测试 + 1 GISBOT sandbox 集成测

### §12 f1 — STATUS 表 reconcile
v2.37.7 spec line 281 单行 doc fix — "未闭合（batch 3）" → "closed v2.37.2 ✓"。§12 f4 行不动。

### helper cleanup
`tools/photo3d_jury.py:498-511` main() 改用 `_resolve_effective_subsystem(args)`，消除与 helper 重复。顺序契约：input validation 早于 helper 调用。零行为差异。

## 集成测先决条件

集成测自动 skip 除非：

```bash
touch D:/Work/cad-tests/GISBOT/.test-archive-marker
```

marker 不进 cad-spec-gen git；GISBOT 在仓库外。

## 走过的弯路 / Plan-drift

（实施期填）

## 5 层 review 实证

| 层 | 抓 | spec rev |
| --- | --- | --- |
| Layer 6 scout | 7 处 drift（tools/dev 不存在 / 8 JSON / dual-schema / marker 缺 等）| rev 1→2 |
| self-review | 4 处 ambiguity（deny list 明示 / exit=0 决策 / `_archive_*` glob / tempdir copy）| rev 2 inline |
| Layer 2 cynical re-read | 8 MAJOR（atomic_write / mtime→SHA256 / ASCII label 等）| rev 2→3 |
| Layer 4 edge-case hunter | 31 cases → 17 进 spec（BOM / Windows lock / bool 子类 等）| rev 2→3 |
| Layer 3 user review | 1 RISK-CRITICAL（archive sentinel marker 防误传）| rev 3→4 |
| 2nd boundary review | 5 闭环漏洞（fixture marker / conftest 真值 / GISBOT 前置 / §12 f4 / 顺序契约）| rev 4→5 |

## §11 follow-up 更新

- 闭合：§11-N1 / §12 f1 / helper cleanup
- 仍 open：§12 f4 N≥50 批量场景成本评估（留 v2.37.9）
- 新登：exit code 语义 v2.39 重审 / `tools/dev/_common.py` rule-of-three 触发再抽

## 后续工作

按 §6 YAGNI：
- v2.37.9 候选：§12 f4 / 真 AI adapter / 端到端图像回归
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/reports/2026-05-16-v2-37-8-rebrand-tool-cleanup-retro.md
git -c commit.gpgsign=false commit -m "docs(retro): v2.37.8 rebrand 工具 + §12 f1 + helper cleanup retro"
```

---

## Task 11: 全套件 + dev_sync 最终验证

**Files:** 无（验证 only）

**预计:** 5 分钟

- [ ] **Step 1: dev_sync --check 验证**

Run:
```bash
python scripts/dev_sync.py --check 2>&1 | tail -3
```

Expected: exit 0 / no drift

- [ ] **Step 2: 跑 rebrand 测试全量 + jury 子集**

Run:
```bash
pytest tests/dev/ -v 2>&1 | tail -10
pytest -q tests/jury/ tests/jury_loop/ 2>&1 | tail -3
```

Expected: 16+1 PASS in tests/dev/（1 集成自动 skip） + 509 PASS jury

- [ ] **Step 3: 跑全套件冒烟（限 5 min timeout）**

Run:
```bash
pytest -q --timeout 60 2>&1 | tail -5
```

Expected: 全量 PASS / 0 regression（v2.37.7 baseline 3084 PASS + 本 PR 新增 ~17）

- [ ] **Step 4: Commit log review + branch状态**

Run:
```bash
git log --oneline main..feat/v2-37-8-rebrand-tool-cleanup
git status -s
```

Expected: 8-10 commit on branch + working tree 仅残留无关 untracked

---

## Task 12: PR push + CI

**Files:** 无（CI / PR 操作）

**预计:** 5 分钟 + CI 等待

- [ ] **Step 1: Push branch + 开 PR**

Run:
```bash
git push -u origin feat/v2-37-8-rebrand-tool-cleanup
```

- [ ] **Step 2: 开 PR with 详尽 body**

Run:
```bash
gh pr create --base main --head feat/v2-37-8-rebrand-tool-cleanup \
  --title "feat(rebrand): v2.37.8 — tools/dev/rebrand_test_archive.py + §12 f1 doc + helper cleanup" \
  --body "$(cat <<'EOF'
## 摘要

v2.37.8 三项合一 PR：

| 项 | 内容 |
| --- | --- |
| **§11-N1** | 新建 \`tools/dev/rebrand_test_archive.py\` (~340 行) — scan-all + dual-schema-aware + archive sentinel marker；16 unit + 1 integration test |
| **§12 f1** | v2.37.7 spec line 281 stale 标记 reconcile（max_tokens 已 closed v2.37.2）|
| **helper cleanup** | photo3d_jury main() 改用 \`_resolve_effective_subsystem\` helper（零行为差异）|

## 改动一览

| 文件 | 改动 |
| --- | --- |
| Create \`tools/dev/__init__.py\` + \`tools/dev/rebrand_test_archive.py\` | dev 工具 |
| Create \`tests/dev/__init__.py\` + \`conftest.py\` + 2 测试文件 | TDD 16 unit + 1 integration |
| Modify \`pyproject.toml\` | 加 \`requires_test_archive\` marker |
| Modify \`tools/photo3d_jury.py:498-511\` | helper cleanup |
| Modify v2.37.7 spec line 281 | §12 f1 reconcile |
| Create retro 文档 | v2.37.8 复盘 |

## TDD + 回归

- ✅ 16/16 unit tests PASS（T1-T16 dual-schema / sentinel / atomic / BOM / 边界 全覆盖）
- ✅ 1 integration test (sandbox copy) — skip 默认 / ops touch marker 后跑
- ✅ jury 子集 509 PASS / 0 regression
- ⏳ CI 8/8（pending push）

## 5 层 review 历史

spec 演 5 rev：rev 1（180 行 brainstorm）→ rev 2（scout 7 drift fix）→ rev 3（cynical 8 MAJOR + edge-case 17 fix）→ rev 4（user RISK-CRITICAL: sentinel marker）→ rev 5（boundary 5 闭环 fix）。

## 集成测先决条件

集成测 conftest 自动 skip 除非 ops 跑：

\`\`\`bash
touch D:/Work/cad-tests/GISBOT/.test-archive-marker
\`\`\`

marker 不进 cad-spec-gen git。

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: 等 CI 8/8（后台 watch）**

Run（background）:
```bash
gh pr checks --watch --interval 30
```

Expected: 8/8 SUCCESS（ubuntu/windows × py 3.10/3.11/3.12 + regression + mypy-strict）

---

## Task 13: 等用户授权 merge + tag + Release + memory

**Files:** memory 文件

**预计:** 用户授权 wait + 5 min 收尾

- [ ] **Step 1: 等用户授权 merge**

CI 8/8 SUCCESS 后向用户报告，等待 "授权 squash merge + tag v2.37.8 + Release" 决策。

- [ ] **Step 2: Squash merge**

```bash
gh pr merge <PR#> --squash --subject "..." --body "..."
```

- [ ] **Step 3: Tag + Release**

```bash
git fetch origin main && git checkout main && git pull --ff-only
git tag -a v2.37.8 -m "v2.37.8 — rebrand 工具 + §12 f1 doc + helper cleanup"
git push origin v2.37.8
gh release create v2.37.8 --title "..." --notes "..."
```

- [ ] **Step 4: 写 memory + 更新 MEMORY.md**

写 `C:\Users\procheng\.claude\projects\D--Work-cad-spec-gen\memory\project_v2_37_8_done.md` + Edit MEMORY.md 索引追加一行。

---

## Self-Review

**1. Spec 覆盖**：

| spec § | task | 覆盖 |
| --- | --- | --- |
| §3.1.0 sentinel marker | Task 6 (T15+T16) + Task 7 (conftest skip) + Task 2 (fixture default) | ✓ |
| §3.1.1 tools/dev/ mkdir | Task 1 | ✓ |
| §3.1.2 CLI 接口 | Task 2 (argparse) | ✓ |
| §3.1.3 scan-all 行为 | Task 2-6 (T1-T16) | ✓ |
| §3.1.4 _atomic_write | Task 5 (T12) | ✓ |
| §3.1.5 错误处理 + exit code | Task 4 (T9-T11) + Task 6 (T15) | ✓ |
| §3.1.6 不变量 | Task 5 (atomic) + Task 6 (sentinel) + 整体设计 | ✓ |
| §3.1.7 测试 T1-T16 + 集成测 | Task 2-7 | ✓ |
| §3.2 §12 f1 doc | Task 8 | ✓ |
| §3.3 helper cleanup | Task 9 | ✓ |
| AC-1~11 | Task 11+12 | ✓ |
| retro | Task 10 | ✓ |
| PR + tag + Release | Task 12+13 | ✓ |

无 spec gap。

**2. Placeholder scan**：

- Task 10 retro `（实施期填）` 占位 — 接受（plan-drift 实际记录留实施期填）
- Task 12 PR body 含模板 `<PR#>` 等 placeholder — 占位 OK（gh pr create 之后自动产 PR# 进 url）

无 plan failure 红旗。

**3. Type consistency**：

- `_make_archive_tempdir` 签名一致（Task 2 def / Task 2-6 调用）
- `_TOOL` 常量一致 (`tools/dev/rebrand_test_archive.py`)
- `_GISBOT_DIR` / `_GISBOT_MARKER` 命名前后一致
- argparse `dest="from_"` 一致使用（避 from 关键字）

无 type drift。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-16-v2-37-8-rebrand-tool-cleanup.md`。

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task + 2 stage review (spec compliance + code quality)；fast iteration；适合本 PR 14 task 链
2. **Inline Execution** — 主 agent 自己 batch 跑 + checkpoint

**Which approach?**
