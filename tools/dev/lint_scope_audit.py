"""§11-N12 lint scope audit — pyproject lint scope drift 检测。

Spec: docs/superpowers/specs/2026-05-17-lint-scope-audit-design.md rev 1.3

检测 pyproject 声明的 lint scope vs 真实代码 lint 状态间的 drift：
- ruff: per-file-ignores 的 over_permissive / missing_glob
- mypy: [[tool.mypy.overrides]] ignore_errors=true 的 dischargeable
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, cast

try:
    import tomllib  # py3.11+ stdlib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef,import-not-found,unused-ignore]  # py3.10 fallback


def _find_executable(name: str) -> str | None:
    """spec hotfix: find executable in PATH or venv bin/Scripts dir.

    CI runners often don't have venv on PATH; subprocess.run() inheriting PATH
    won't see ruff/mypy installed via pip even though they're available.
    """
    found = shutil.which(name)
    if found:
        return found
    # 检查 sys.executable 的同级目录（venv Scripts/bin）
    venv_bin = Path(sys.executable).parent
    for ext in ("", ".exe"):
        candidate = venv_bin / f"{name}{ext}"
        if candidate.exists():
            return str(candidate)
    return None


def _load_pyproject(path: Path | None = None) -> dict[str, Any]:
    """读 pyproject.toml 返回 dict（spec §3.2）"""
    if path is None:
        path = Path.cwd() / "pyproject.toml"
    with path.open("rb") as f:
        return cast(dict[str, Any], tomllib.load(f))


def _load_ruff_config(pyproject: dict[str, Any]) -> tuple[dict[str, list[str]], list[str]] | None:
    """解 [tool.ruff.lint] → (globs_to_codes, select_codes)；缺段返 None"""
    ruff_lint = pyproject.get("tool", {}).get("ruff", {}).get("lint")
    if ruff_lint is None:
        return None
    select_codes = list(ruff_lint.get("select", []))
    globs_to_codes = dict(ruff_lint.get("per-file-ignores", {}))
    return globs_to_codes, select_codes


def _match_glob(glob: str, path: str) -> bool:
    """spec §3.4 rev 1.1 M1 + rev 1.2 B5: glob → regex (** → .* / * → [^/]* / ? → [^/]).

    Normalize Windows \\ → /；锚 ^ + $；不支持 char class [!abc] (N6)。
    """
    path_normalized = path.replace("\\", "/")
    # 逐字符构 regex：先 re.escape 整 glob，然后还原 *、**、? 的特殊语义
    parts: list[str] = []
    i = 0
    while i < len(glob):
        if glob[i] == "*":
            if i + 1 < len(glob) and glob[i + 1] == "*":
                if i + 2 < len(glob) and glob[i + 2] == "/":
                    parts.append("(.*/)?")  # **/ → 含 0 段的任意子树（含 /）
                    i += 3  # 同时消费 **/
                else:
                    parts.append(".*")  # ** 在末尾 = 任意（含 /）
                    i += 2
            else:
                parts.append("[^/]*")  # * = 单段无 /
                i += 1
        elif glob[i] == "?":
            parts.append("[^/]")
            i += 1
        else:
            parts.append(re.escape(glob[i]))
            i += 1
    pattern = "^" + "".join(parts) + "$"
    return re.match(pattern, path_normalized) is not None


def _normalize_ruff_filename(filename: str, cwd: Path) -> str:
    """spec rev 1.2 B4: ruff JSON filename 是 absolute path；normalize 成 / 分隔 relative."""
    try:
        rel = Path(filename).resolve().relative_to(cwd.resolve())
    except ValueError:
        # 路径在 cwd 之外 → 用原值（带 /-分隔标准化）
        return filename.replace("\\", "/")
    return rel.as_posix()


def _compute_ruff_drift(
    globs_to_codes: dict[str, list[str]],
    select_codes: list[str],
    violations: list[tuple[str, str]],
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """spec §3.3: 返 (over_permissive, missing_glob)。

    - over_permissive: 遍 (glob, code)，若无任何 (file, code) ∈ violations 中 file 匹配 glob → over_permissive
    - missing_glob: 遍 (file, code) ∈ violations，若无任何 glob 满足 (path matches glob && code ∈ globs_to_codes[glob]) → missing_glob
    """
    over_permissive: list[tuple[str, str]] = []
    for glob, codes in globs_to_codes.items():
        for code in codes:
            if code not in select_codes:
                continue  # glob 覆盖的 code 不在 select 列表 → 不关心
            has_match = any(
                file_code == code and _match_glob(glob, file)
                for file, file_code in violations
            )
            if not has_match:
                over_permissive.append((glob, code))

    missing_glob: list[tuple[str, str]] = []
    for file, code in violations:
        covered = any(
            code in codes_for_glob and _match_glob(glob, file)
            for glob, codes_for_glob in globs_to_codes.items()
        )
        if not covered:
            missing_glob.append((file, code))

    return over_permissive, missing_glob


def _load_mypy_overrides(pyproject: dict[str, Any]) -> list[str]:
    """spec §3.2 M8: 解 [[tool.mypy.overrides]] → ignore_errors=true 模块列表。

    每 override block 的 module 字段可为 str 或 list[str]，统一展开。
    """
    raw_overrides = pyproject.get("tool", {}).get("mypy", {}).get("overrides", [])
    if not isinstance(raw_overrides, list):
        raw_overrides = []
    overrides: list[dict[str, Any]] = [b for b in raw_overrides if isinstance(b, dict)]
    modules: list[str] = []
    for block in overrides:
        if not block.get("ignore_errors"):
            continue
        module = block.get("module")
        if isinstance(module, str):
            modules.append(module)
        elif isinstance(module, list):
            modules.extend(str(m) for m in module)
    return modules


def _make_mypy_stripped_config(
    pyproject: dict[str, Any],
    tmp_dir: Path | None = None,
) -> Path:
    """spec §3.2 B6: 写 tempfile 保留 [tool.mypy] 主段 + strict=true overrides；
    剥离 ignore_errors=true overrides。返 tmp 文件路径，调用方负责清理。
    """
    raw_section = pyproject.get("tool", {}).get("mypy", {})
    if not isinstance(raw_section, dict):
        raw_section = {}
    mypy_section: dict[str, Any] = dict(raw_section)

    # 过滤 overrides — 保留 strict=true，剥离 ignore_errors=true
    raw_overrides = mypy_section.get("overrides", [])
    if not isinstance(raw_overrides, list):
        raw_overrides = []
    overrides: list[dict[str, Any]] = [b for b in raw_overrides if isinstance(b, dict)]
    kept_overrides: list[dict[str, Any]] = [b for b in overrides if not b.get("ignore_errors")]

    # 渲染 TOML
    lines: list[str] = ["[tool.mypy]"]
    for key, val in mypy_section.items():
        if key == "overrides":
            continue
        if isinstance(val, bool):
            lines.append(f"{key} = {str(val).lower()}")
        elif isinstance(val, str):
            lines.append(f'{key} = "{val}"')
        elif isinstance(val, (int, float)):
            lines.append(f"{key} = {val}")
    for block in kept_overrides:
        lines.append("")
        lines.append("[[tool.mypy.overrides]]")
        for key, val in block.items():
            if isinstance(val, bool):
                lines.append(f"{key} = {str(val).lower()}")
            elif isinstance(val, str):
                lines.append(f'{key} = "{val}"')
            elif isinstance(val, list):
                items = ", ".join(f'"{x}"' for x in val)
                lines.append(f"{key} = [{items}]")
    content = "\n".join(lines) + "\n"

    tmp_dir_arg = str(tmp_dir) if tmp_dir is not None else None
    fd, path_str = tempfile.mkstemp(suffix=".toml", dir=tmp_dir_arg, text=True)
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        Path(path_str).unlink(missing_ok=True)
        raise
    return Path(path_str)


def _render_ruff_report(
    select_codes: list[str],
    globs_to_codes: dict[str, list[str]],
    over_permissive: list[tuple[str, str]],
    missing_glob: list[tuple[str, str]],
) -> str:
    """spec §3.5 + rev 1.3 N8: ruff drift markdown 报告（含 caveat）"""
    today = date.today().isoformat()
    parts: list[str] = []
    parts.append(f"# Lint scope audit — ruff ({today})")
    parts.append("")
    parts.append("## 配置摘要")
    parts.append(f"- select: {len(select_codes)} codes")
    parts.append(f"- per-file-ignores: {len(globs_to_codes)} globs")
    parts.append("")
    parts.append(f"## ⚠ over_permissive ({len(over_permissive)})")
    if over_permissive:
        for glob, code in over_permissive:
            parts.append(f"- `{glob}` covers `{code}` but no actual violations match")
        parts.append(
            "  - **caveat**：本工具 strip per-file-ignores 后计算真违规集合；"
            "安全删除 glob 前请人工 verify (1) future cleanup 不再需要该 path"
            " (2) 删后 `ruff check .` 仍 exit 0"
        )
    else:
        parts.append("- 无")
    parts.append("")
    parts.append(f"## ❌ missing_glob ({len(missing_glob)})")
    if missing_glob:
        for file, code in missing_glob:
            parts.append(f"- `{file}` violates `{code}` but no per-file-ignores glob covers it")
    else:
        parts.append("- 无")
    parts.append("")
    parts.append("## 结论")
    if not over_permissive and not missing_glob:
        parts.append("- ✅ 无 drift")
    else:
        msg_parts: list[str] = []
        if over_permissive:
            msg_parts.append(f"⚠ {len(over_permissive)} 项 over_permissive")
        if missing_glob:
            msg_parts.append(f"❌ {len(missing_glob)} 项 missing_glob")
        parts.append("- " + " / ".join(msg_parts))
    parts.append("")
    return "\n".join(parts)


def _render_mypy_report(
    all_modules: list[str],
    dischargeable: list[str],
    still_has_errors: list[tuple[str, int]],
) -> str:
    """spec §3.5 + rev 1.2 N7 + rev 1.3 M7: mypy drift markdown 报告"""
    today = date.today().isoformat()
    parts: list[str] = []
    parts.append(f"# Lint scope audit — mypy ({today})")
    parts.append("")
    parts.append("## 配置摘要")
    parts.append(f"- ignore_errors=true 模块：{len(all_modules)} 个")
    parts.append("")
    parts.append(f"## ✅ dischargeable ({len(dischargeable)})")
    if dischargeable:
        for module in dischargeable:
            parts.append(
                f"- `{module}` — stripped config + `mypy --strict -p {module}` exit 0；"
                "建议从 [[tool.mypy.overrides]] 出列"
            )
        parts.append(
            "  - **caveat**：本工具用 stripped config + `--disable-error-code=import-untyped`"
            " 判定。出列前请人工手测原 pyproject 下 `mypy --strict -p <module>` 实质 clean"
            "（确认不依赖外部 type stub），再 commit"
        )
    else:
        parts.append("- 无")
    parts.append("")
    parts.append(f"## ⚠ still has errors ({len(still_has_errors)})")
    if still_has_errors:
        for module, error_count in still_has_errors:
            parts.append(
                f"- `{module}` — stripped config 下 {error_count} errors；保留 ignore_errors=true 合理"
            )
    else:
        parts.append("- 无")
    parts.append("")
    parts.append("## 结论")
    parts.append(
        f"- dischargeable: {len(dischargeable)} 项 / "
        f"still has errors: {len(still_has_errors)} 项 / "
        f"总计 {len(all_modules)} 模块"
    )
    parts.append("")
    return "\n".join(parts)


def _run_ruff_json(cwd: Path) -> list[tuple[str, str]]:
    """spec §3.2 B2+B4: 用 --config strip per-file-ignores 拿真违规；normalize filename"""
    ruff_exe = _find_executable("ruff")
    if ruff_exe is None:
        print("Error: ruff not in PATH or venv", file=sys.stderr)
        raise SystemExit(3)
    result = subprocess.run(
        [
            ruff_exe,
            "check",
            "--config",
            "lint.per-file-ignores={}",
            "--output-format=json",
            ".",
        ],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    # ruff 有 violation 时 returncode=1，无 violation 时=0；都是正常输出
    try:
        violations_raw: list[dict[str, Any]] = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"Error: ruff JSON parse failed (version mismatch?): {e}", file=sys.stderr)
        print(f"stdout sample: {result.stdout[:200]}", file=sys.stderr)
        raise SystemExit(4) from e
    violations: list[tuple[str, str]] = []
    for v in violations_raw:
        filename = _normalize_ruff_filename(cast(str, v["filename"]), cwd=cwd)
        code = cast(str, v["code"])
        violations.append((filename, code))
    return violations


def _run_mypy_strict_per_module(
    module: str, stripped_config_path: Path, cwd: Path
) -> tuple[bool, int]:
    """spec §3.2 B6+M6: stripped config + --disable-error-code=import-untyped。

    返 (is_clean, error_count)：is_clean = exit 0；error_count 取"Found N errors"或 0。
    """
    mypy_exe = _find_executable("mypy")
    if mypy_exe is None:
        print("Error: mypy not in PATH or venv", file=sys.stderr)
        raise SystemExit(3)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--strict",
            "--config-file",
            str(stripped_config_path),
            "--disable-error-code=import-untyped",
            "-p",
            module,
        ],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if result.returncode == 0:
        return True, 0
    # 解析 "Found N errors" 行
    match = re.search(r"Found (\d+) error", result.stdout)
    count = int(match.group(1)) if match else 0
    return False, count


def _compute_mypy_dischargeable(
    modules: list[str],
    results: list[tuple[bool, int]],
) -> tuple[list[str], list[tuple[str, int]]]:
    """spec §3.2: 返 (dischargeable, still_has_errors)"""
    dischargeable: list[str] = []
    still_has_errors: list[tuple[str, int]] = []
    for module, (is_clean, count) in zip(modules, results):
        if is_clean:
            dischargeable.append(module)
        else:
            still_has_errors.append((module, count))
    return dischargeable, still_has_errors


def _ensure_repo_root_cwd() -> Path:
    """spec rev 1.2 B5: cwd 不在 repo root → 尝试自动 cd；失败终止 exit 2"""
    cwd = Path.cwd()
    if (cwd / "pyproject.toml").exists():
        return cwd
    # 尝试从 __file__ 推
    script_root = Path(__file__).resolve().parent.parent.parent
    if (script_root / "pyproject.toml").exists():
        return script_root
    print("Error: cannot locate pyproject.toml; cwd must be repo root", file=sys.stderr)
    raise SystemExit(2)


def _cmd_ruff(cwd: Path) -> str:
    """ruff 子命令主逻辑：返 markdown 报告"""
    pyproject = _load_pyproject(cwd / "pyproject.toml")
    ruff_config = _load_ruff_config(pyproject)
    if ruff_config is None:
        print("Error: [tool.ruff] section missing in pyproject.toml", file=sys.stderr)
        raise SystemExit(2)
    globs_to_codes, select_codes = ruff_config
    violations = _run_ruff_json(cwd)
    over_permissive, missing_glob = _compute_ruff_drift(globs_to_codes, select_codes, violations)
    return _render_ruff_report(select_codes, globs_to_codes, over_permissive, missing_glob)


def _cmd_mypy(cwd: Path) -> str:
    """mypy 子命令主逻辑：返 markdown 报告"""
    pyproject = _load_pyproject(cwd / "pyproject.toml")
    modules = _load_mypy_overrides(pyproject)
    if not modules:
        return "# Lint scope audit — mypy\n\n无 ignore_errors=true 模块。\n"
    stripped_path = _make_mypy_stripped_config(pyproject)
    try:
        results = [_run_mypy_strict_per_module(m, stripped_path, cwd) for m in modules]
    finally:
        stripped_path.unlink(missing_ok=True)
    dischargeable, still_has_errors = _compute_mypy_dischargeable(modules, results)
    return _render_mypy_report(modules, dischargeable, still_has_errors)


def main(argv: list[str] | None = None) -> int:
    """argparse + dispatch；rev 1.2 M9: subparsers required=True"""
    # rev 1.2 M5/M10 + Windows GBK fix: force UTF-8 stdout/stderr
    # avoid UnicodeEncodeError on '⚠', '✅', '—', 中文 etc.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(
        prog="lint_scope_audit",
        description="§11-N12 pyproject lint scope drift 检测（ruff per-file-ignores + mypy ignore_errors）",
    )
    subparsers = parser.add_subparsers(dest="cmd", required=True)
    subparsers.add_parser("ruff", help="检测 ruff per-file-ignores drift")
    subparsers.add_parser("mypy", help="检测 mypy ignore_errors drift")
    subparsers.add_parser("all", help="顺序跑 ruff + mypy")
    args = parser.parse_args(argv)

    cwd = _ensure_repo_root_cwd()

    if args.cmd == "ruff":
        print(_cmd_ruff(cwd))
    elif args.cmd == "mypy":
        print(_cmd_mypy(cwd))
    elif args.cmd == "all":
        # rev 1.2 M4: all 子命令 fallback wording — 若 ruff 段缺 → 跳过继续 mypy
        try:
            print(_cmd_ruff(cwd))
        except SystemExit as e:
            if e.code in (2, 3):  # 2=missing section, 3=missing executable
                print(
                    f"# Lint scope audit — all\n\n## ⚠ ruff 段跳过\n"
                    f"ruff 不可用 or pyproject [tool.ruff] 段缺失 — exit code {e.code}\n"
                )
            else:
                raise
        print("\n---\n")
        print(_cmd_mypy(cwd))
    return 0


if __name__ == "__main__":
    sys.exit(main())
