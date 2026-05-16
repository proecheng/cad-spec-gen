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


def _looks_like_abs_path(p: str) -> bool:
    """rev 2 D4 — abs path 须以 drive letter (e.g. C: D:) 开头。"""
    return len(p) >= 2 and p[1] == ":" and p[0].isalpha()


def _normalize_path(p: str) -> str:
    """统一 separator 到 \\\\ 用于匹配比较（仅内部用，不写回）。"""
    return p.replace("/", "\\")


def _matches_prefix(value: str, from_prefix: str) -> bool:
    """prefix 匹配 — 跨 separator 兼容 + 边界紧跟 / 或 \\\\。"""
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
        # 都缺 — 复用 v2.37.8 既有 subsystem 5 条校验（base 已跑过 idempotent）
        return _validate_inputs(archive_dir, args_from, args_to)

    # 都给 path-prefix：
    if not from_prefix or not to_prefix:
        print("[ERROR] --from-path-prefix / --to-path-prefix must be non-empty", file=sys.stderr)
        return 2
    if from_prefix == to_prefix:
        print("[ERROR] --from-path-prefix and --to-path-prefix must differ", file=sys.stderr)
        return 2

    # 不变量 #15：prefix 须含 drive letter + colon
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

    # subsystem 校验（除 from==to 时 skip — T-prefix-E）
    if args_from != args_to:
        sub_rc = _validate_inputs(archive_dir, args_from, args_to)
        if sub_rc != 0:
            return sub_rc
    # else: from==to + path-prefix 给 → skip subsystem 校验；base 已跑完 (B1 fix)

    return 0


def _process_file(path: Path, args_from: str, args_to: str) -> tuple[str, dict[str, Any] | None]:
    """处理单 JSON 文件，返 (action, data_to_write or None).

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
                # skip_other 不 emit
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
    parser.add_argument(
        "--from-path-prefix",
        dest="from_path_prefix",
        default=None,
        help="当前 abs path 前缀（如 D:\\\\Work\\\\cad-spec-gen）；须含 drive letter；与 --to-path-prefix 互锁",
    )
    parser.add_argument(
        "--to-path-prefix",
        dest="to_path_prefix",
        default=None,
        help="目标 abs path 前缀（如 D:\\\\Work\\\\cad-tests\\\\GISBOT）；与 --from-path-prefix 互锁",
    )
    parser.add_argument("--apply", action="store_true", help="真改写（缺省 dry-run preview）")
    args = parser.parse_args()

    rc = _validate_path_prefix(
        args.archive_dir, args.from_, args.to,
        args.from_path_prefix, args.to_path_prefix,
    )
    if rc:
        return rc

    return _scan(args.archive_dir, args.from_, args.to, args.apply)


if __name__ == "__main__":
    sys.exit(main())
