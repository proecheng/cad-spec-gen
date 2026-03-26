#!/usr/bin/env python3
"""
cad-spec-gen Universal Installer

Install or update the CAD pipeline skill into any LLM/Agent platform.

Usage:
    python install.py                          # install to current dir (Claude Code)
    python install.py --update                 # update existing installation
    python install.py --check                  # check if update available
    python install.py --target /path/to/proj   # install to another project
    python install.py --platform openai        # other platforms
"""

import argparse
import hashlib
import io
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Fix Windows GBK encoding for emoji output
if sys.stdout.encoding and sys.stdout.encoding.lower().startswith("gbk"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent

# --- Deprecation notice ---
_DEPRECATION_MSG = """\
⚠️  install.py is deprecated. Please use the PyPI package instead:

    pip install cad-spec-gen
    cad-skill-setup

  The PyPI installer supports language selection (zh/en), environment
  detection, optional dependency installation, and interactive setup.

  This script will continue to work but will not receive new features.
"""
print(_DEPRECATION_MSG, file=sys.stderr)

# Files that users may customize — never overwrite silently
USER_CONFIG_FILES = [
    "config/gisbot.json",
]

# All files to install (relative to repo root → target)
INSTALL_MANIFEST = {
    "python_tools": [
        "cad_spec_gen.py", "cad_spec_extractors.py",
        "cad_spec_defaults.py", "cad_spec_reviewer.py",
        "bom_parser.py",
        "cad_paths.py", "cad_pipeline.py",
        "annotate_render.py",
        "enhance_prompt.py", "prompt_data_builder.py",
        "pipeline_config.json",
    ],
    "knowledge": [
        "skill_cad_help.md",
        "skill_mech_design.md",
    ],
    "directories": [
        "config",
        "templates",
        "codegen",
        "docs",
    ],
    "subsystem_tools": [
        # Per-subsystem tools copied alongside CAD files
        "orientation_check.py",
    ],
}


def _file_hash(path: Path) -> str:
    """MD5 hash of a file's contents."""
    if not path.exists():
        return ""
    return hashlib.md5(path.read_bytes()).hexdigest()


def _dir_hashes(directory: Path) -> dict:
    """MD5 hashes of all files in a directory (recursive)."""
    hashes = {}
    if directory.exists():
        for f in sorted(directory.rglob("*")):
            if f.is_file():
                rel = f.relative_to(directory.parent).as_posix()
                hashes[rel] = _file_hash(f)
    return hashes


def _get_repo_version() -> str:
    """Read version from skill.json."""
    skill_json = REPO_ROOT / "skill.json"
    data = json.loads(skill_json.read_text(encoding="utf-8"))
    return data.get("version", "0.0.0")


def _read_installed_version(target: Path) -> dict | None:
    """Read the version marker from an installed target."""
    marker = target / ".cad_skill_version.json"
    if not marker.exists():
        return None
    return json.loads(marker.read_text(encoding="utf-8"))


def _write_version_marker(target: Path, version: str):
    """Write version marker with file hashes for change detection."""
    hashes = {}
    # Hash individual files
    for name in INSTALL_MANIFEST["python_tools"] + INSTALL_MANIFEST["knowledge"]:
        p = target / name
        if p.exists():
            hashes[name] = _file_hash(p)
    # Hash directory contents
    for dirname in INSTALL_MANIFEST["directories"]:
        d = target / dirname
        hashes.update(_dir_hashes(d))
    # Hash commands
    cmd_dir = target / ".claude" / "commands"
    if cmd_dir.exists():
        for f in cmd_dir.glob("cad-*.md"):
            rel = f".claude/commands/{f.name}"
            hashes[rel] = _file_hash(f)

    marker = {
        "skill": "cad-spec-gen",
        "version": version,
        "installed_at": datetime.now().isoformat(),
        "files": hashes,
    }
    (target / ".cad_skill_version.json").write_text(
        json.dumps(marker, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _check_user_modified(target: Path, installed: dict, filepath: str) -> bool:
    """Check if a file was modified by the user since installation."""
    if installed is None:
        return False
    installed_hash = installed.get("files", {}).get(filepath, "")
    if not installed_hash:
        return False  # file didn't exist at install time
    current_hash = _file_hash(target / filepath)
    return current_hash != installed_hash


def check_update(target: Path):
    """Check if an update is available."""
    installed = _read_installed_version(target)
    repo_version = _get_repo_version()

    if installed is None:
        print(f"未安装 cad-spec-gen。使用 --platform claude-code 安装。")
        print(f"最新版本: {repo_version}")
        return

    inst_ver = installed.get("version", "?")
    inst_date = installed.get("installed_at", "?")[:10]

    if inst_ver == repo_version:
        # Check if repo files changed even with same version (dev mode)
        changed = _get_changed_files(target, installed)
        if changed:
            print(f"版本相同 ({inst_ver})，但有 {len(changed)} 个文件有更新：")
            for f, reason in changed[:10]:
                print(f"  • {f} ({reason})")
            if len(changed) > 10:
                print(f"  ... 及其他 {len(changed) - 10} 个文件")
            print(f"\n运行 --update 更新文件。")
        else:
            print(f"已是最新版本 ({inst_ver}，安装于 {inst_date})")
    else:
        print(f"有新版本可用！")
        print(f"  已安装: {inst_ver} ({inst_date})")
        print(f"  最新:   {repo_version}")
        print(f"\n运行 --update 更新。")


def _get_changed_files(target: Path, installed: dict) -> list:
    """Compare repo files with installed files, return list of (path, reason)."""
    changed = []

    # Check individual files
    for name in INSTALL_MANIFEST["python_tools"] + INSTALL_MANIFEST["knowledge"]:
        src = REPO_ROOT / name
        if not src.exists():
            continue
        repo_hash = _file_hash(src)
        inst_hash = installed.get("files", {}).get(name, "")
        if repo_hash != inst_hash:
            if not inst_hash:
                changed.append((name, "新文件"))
            else:
                changed.append((name, "已更新"))

    # Check directories
    for dirname in INSTALL_MANIFEST["directories"]:
        src_dir = REPO_ROOT / dirname
        if not src_dir.exists():
            continue
        for f in sorted(src_dir.rglob("*")):
            if f.is_file():
                rel = f.relative_to(REPO_ROOT).as_posix()
                repo_hash = _file_hash(f)
                inst_hash = installed.get("files", {}).get(rel, "")
                if repo_hash != inst_hash:
                    if not inst_hash:
                        changed.append((rel, "新文件"))
                    else:
                        changed.append((rel, "已更新"))

    # Check commands
    src_commands = REPO_ROOT / "adapters" / "claude-code" / "commands"
    if src_commands.exists():
        for f in src_commands.glob("*.md"):
            rel = f".claude/commands/{f.name}"
            repo_hash = _file_hash(f)
            inst_hash = installed.get("files", {}).get(rel, "")
            if repo_hash != inst_hash:
                if not inst_hash:
                    changed.append((rel, "新文件"))
                else:
                    changed.append((rel, "已更新"))

    return changed


def _safe_copy(src: Path, dst: Path):
    """Copy file, skipping if src and dst are the same file."""
    try:
        if src.resolve() == dst.resolve():
            return
    except OSError:
        pass
    shutil.copy2(src, dst)


def install_claude_code(target: Path, update: bool = False):
    """Copy slash commands and skill files to a Claude Code project."""
    installed = _read_installed_version(target)
    repo_version = _get_repo_version()

    if update:
        if installed is None:
            print("未检测到已安装版本，将执行全新安装。")
        else:
            changed = _get_changed_files(target, installed)
            if not changed:
                print(f"已是最新版本 ({installed.get('version', '?')})，无需更新。")
                return
            print(f"更新 {installed.get('version', '?')} → {repo_version}")
            print(f"变更文件: {len(changed)}")
            for f, reason in changed:
                print(f"  • {f} ({reason})")
            print()

    # --- Slash commands ---
    commands_dir = target / ".claude" / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    src_commands = REPO_ROOT / "adapters" / "claude-code" / "commands"
    for f in src_commands.glob("*.md"):
        _safe_copy(f, commands_dir / f.name)
        print(f"  ✅ {f.name} → .claude/commands/")

    # --- Knowledge file ---
    _safe_copy(REPO_ROOT / "skill_cad_help.md", target / "skill_cad_help.md")
    print("  ✅ skill_cad_help.md → project root")

    # --- Python tools ---
    for name in INSTALL_MANIFEST["python_tools"]:
        src = REPO_ROOT / name
        if src.exists():
            _safe_copy(src, target / name)
    print("  ✅ Python tools copied")

    # --- Config & Templates (user-config-aware) ---
    for dirname in INSTALL_MANIFEST["directories"]:
        src_dir = REPO_ROOT / dirname
        dst_dir = target / dirname
        if not src_dir.exists():
            continue

        if not dst_dir.exists():
            # Fresh install — just copy
            shutil.copytree(src_dir, dst_dir)
            print(f"  ✅ {dirname}/ copied")
            continue
        elif src_dir.resolve() == dst_dir.resolve():
            # Self-install: target is repo root, dirs already exist
            print(f"  ✅ {dirname}/ (already in place)")
            continue

        # Update mode: check each file
        user_modified_files = []
        for src_file in sorted(src_dir.rglob("*")):
            if not src_file.is_file():
                continue
            rel = src_file.relative_to(src_dir)
            dst_file = dst_dir / rel
            full_rel = f"{dirname}/{rel.as_posix()}"

            if full_rel in USER_CONFIG_FILES and dst_file.exists():
                # Check if user modified this config file
                if _check_user_modified(target, installed, full_rel):
                    # User modified — write .new sidecar, keep user's version
                    new_file = dst_file.with_suffix(dst_file.suffix + ".new")
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    _safe_copy(src_file, new_file)
                    user_modified_files.append(full_rel)
                    continue

            # Not user-modified or not a config file — overwrite
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            _safe_copy(src_file, dst_file)

        if user_modified_files:
            print(f"  ⚠️  {dirname}/ 更新（以下文件已被用户修改，新版本写入 .new）:")
            for f in user_modified_files:
                print(f"     {f} → {f}.new")
        else:
            print(f"  ✅ {dirname}/ copied")

    # --- Write version marker ---
    _write_version_marker(target, repo_version)
    print(f"  ✅ 版本标记: {repo_version}")

    print(f"\nDone! cad-spec-gen {repo_version} {'updated' if update else 'installed'}.")
    print(f"  /cad-help              — interactive pipeline assistant")
    print(f"  /cad-spec <file.md>    — generate CAD spec (with --review)")


def export_openai():
    """Print OpenAI Function Calling JSON schema."""
    functions_path = REPO_ROOT / "adapters" / "openai" / "functions.json"
    print(functions_path.read_text(encoding="utf-8"))


def export_system_prompt():
    """Print universal system prompt (paste into any LLM)."""
    prompt_path = REPO_ROOT / "system_prompt.md"
    print(prompt_path.read_text(encoding="utf-8"))


def export_langchain():
    """Show LangChain integration instructions."""
    readme_path = REPO_ROOT / "adapters" / "langchain" / "README.md"
    print(readme_path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(
        description="Install or update cad-spec-gen skill into any LLM/Agent platform"
    )
    parser.add_argument(
        "--platform", "-p",
        default="claude-code",
        choices=["claude-code", "openai", "system-prompt", "langchain", "dify"],
        help="Target platform (default: claude-code)"
    )
    parser.add_argument(
        "--target", "-t",
        default=".",
        help="Target project directory (default: current directory)"
    )
    parser.add_argument(
        "--update", "-u",
        action="store_true",
        help="Update existing installation (preserves user-modified config files)"
    )
    parser.add_argument(
        "--check", "-c",
        action="store_true",
        help="Check if an update is available (no changes made)"
    )
    args = parser.parse_args()

    if args.platform == "claude-code":
        target = Path(args.target).resolve()
        if not target.exists():
            print(f"Error: target directory does not exist: {target}")
            sys.exit(1)

        if args.check:
            check_update(target)
        elif args.update:
            print(f"Updating cad-spec-gen in: {target}")
            install_claude_code(target, update=True)
        else:
            print(f"Installing cad-spec-gen into: {target}")
            install_claude_code(target)

    elif args.platform == "openai":
        export_openai()

    elif args.platform == "system-prompt":
        export_system_prompt()

    elif args.platform == "langchain":
        export_langchain()

    elif args.platform == "dify":
        readme_path = REPO_ROOT / "adapters" / "dify" / "README.md"
        print(readme_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
