"""Register (copy) skill files to the target project directory.

Extracted from install.py with language-awareness and PyPI data source support.
"""

import hashlib
import json
import shutil
from datetime import datetime
from importlib.resources import files
from pathlib import Path

from .i18n import t
from . import ui

# Files that users may customize — never overwrite silently
USER_CONFIG_FILES = ["config/gisbot.json"]

# Python tools to copy from data/python_tools/ → target root
PYTHON_TOOLS = [
    "cad_pipeline.py", "cad_spec_gen.py", "cad_spec_extractors.py",
    "cad_spec_defaults.py", "cad_spec_reviewer.py", "cad_paths.py",
    "bom_parser.py", "annotate_render.py", "pipeline_config.json",
]

# Directories to copy from data/{name}/ → target/{name}/
COPY_DIRS = ["codegen", "config", "templates"]

# Slash commands (from data/commands/{lang}/)
COMMAND_FILES = [
    "cad-help.md", "cad-spec.md", "cad-codegen.md",
    "cad-enhance.md", "mechdesign.md",
]


def _data_root():
    """Get the package data root directory."""
    return Path(str(files("cad_spec_gen") / "data"))


def _file_hash(path):
    """MD5 hash of a file."""
    if not path.exists():
        return ""
    return hashlib.md5(path.read_bytes()).hexdigest()


def _dir_hashes(directory):
    """MD5 hashes of all files in a directory (recursive)."""
    hashes = {}
    if directory.exists():
        for f in sorted(directory.rglob("*")):
            if f.is_file():
                rel = f.relative_to(directory.parent).as_posix()
                hashes[rel] = _file_hash(f)
    return hashes


def _safe_copy(src, dst):
    """Copy file, skipping if src and dst are the same."""
    try:
        if src.resolve() == dst.resolve():
            return
    except OSError:
        pass
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _read_installed_version(target):
    """Read .cad_skill_version.json from target."""
    marker = target / ".cad_skill_version.json"
    if not marker.exists():
        return None
    return json.loads(marker.read_text(encoding="utf-8"))


def _check_user_modified(target, installed, filepath):
    """Check if a file was modified by the user since installation."""
    if installed is None:
        return False
    installed_hash = installed.get("files", {}).get(filepath, "")
    if not installed_hash:
        return False
    current_hash = _file_hash(target / filepath)
    return current_hash != installed_hash


def _write_version_marker(target, version):
    """Write version marker with file hashes."""
    hashes = {}
    # Individual files
    for name in PYTHON_TOOLS:
        p = target / name
        if p.exists():
            hashes[name] = _file_hash(p)
    # Knowledge file
    for name in ["skill_cad_help.md"]:
        p = target / name
        if p.exists():
            hashes[name] = _file_hash(p)
    # Directories
    for dirname in COPY_DIRS:
        d = target / dirname
        hashes.update(_dir_hashes(d))
    # Commands
    cmd_dir = target / ".claude" / "commands"
    if cmd_dir.exists():
        for f in cmd_dir.glob("*.md"):
            rel = f".claude/commands/{f.name}"
            hashes[rel] = _file_hash(f)

    marker = {
        "skill": "cad-spec-gen",
        "version": version,
        "installed_at": datetime.now().isoformat(),
        "lang": "zh",  # will be overwritten with actual lang
        "files": hashes,
    }
    (target / ".cad_skill_version.json").write_text(
        json.dumps(marker, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def register_skill(target_dir, lang="zh", version="1.2.0", update=False):
    """Copy all skill files to the target project directory.

    Args:
        target_dir: Path to the target project
        lang: "zh" or "en" — selects command and knowledge file language
        version: Version string for the marker
        update: If True, check for user-modified configs

    Returns:
        int: Number of files copied
    """
    target = Path(target_dir).resolve()
    data = _data_root()
    installed = _read_installed_version(target) if update else None
    count = 0

    # 1. Slash commands (language-specific)
    cmd_src = data / "commands" / lang
    cmd_dst = target / ".claude" / "commands"
    cmd_dst.mkdir(parents=True, exist_ok=True)
    for name in COMMAND_FILES:
        src = cmd_src / name
        if src.exists():
            _safe_copy(src, cmd_dst / name)
            count += 1
    ui.success(f".claude/commands/ ({len(COMMAND_FILES)} commands, {lang})")

    # 2. Knowledge file (language-specific)
    knowledge_name = f"skill_cad_help_{lang}.md"
    knowledge_src = data / "knowledge" / knowledge_name
    if knowledge_src.exists():
        _safe_copy(knowledge_src, target / "skill_cad_help.md")
        count += 1
        ui.success("skill_cad_help.md")

    # 3. System prompt (language-neutral)
    sys_prompt = data / "system_prompt.md"
    if sys_prompt.exists():
        _safe_copy(sys_prompt, target / "system_prompt.md")
        count += 1

    # 4. Python tools
    tools_dir = data / "python_tools"
    for name in PYTHON_TOOLS:
        src = tools_dir / name
        if src.exists():
            _safe_copy(src, target / name)
            count += 1
    ui.success(f"Python tools ({len(PYTHON_TOOLS)} files)")

    # 5. Directories (codegen, config, templates)
    for dirname in COPY_DIRS:
        src_dir = data / dirname
        dst_dir = target / dirname
        if not src_dir.is_dir():
            continue

        if not dst_dir.exists():
            shutil.copytree(src_dir, dst_dir)
            count += sum(1 for _ in src_dir.rglob("*") if _.is_file())
            ui.success(f"{dirname}/")
            continue

        # Update: check each file
        user_modified = []
        dir_count = 0
        for src_file in sorted(src_dir.rglob("*")):
            if not src_file.is_file():
                continue
            rel = src_file.relative_to(src_dir)
            dst_file = dst_dir / rel
            full_rel = f"{dirname}/{rel.as_posix()}"

            if full_rel in USER_CONFIG_FILES and dst_file.exists():
                if _check_user_modified(target, installed, full_rel):
                    new_file = dst_file.with_suffix(dst_file.suffix + ".new")
                    _safe_copy(src_file, new_file)
                    user_modified.append(full_rel)
                    continue

            _safe_copy(src_file, dst_file)
            dir_count += 1

        count += dir_count
        if user_modified:
            ui.warn(f"{dirname}/ ({t('update_modified', lang)})")
            for f in user_modified:
                ui.info(f"  {f} → {f}.new")
        else:
            ui.success(f"{dirname}/")

    # 6. Version marker
    _write_version_marker(target, version)
    # Patch lang into marker
    marker_path = target / ".cad_skill_version.json"
    marker_data = json.loads(marker_path.read_text(encoding="utf-8"))
    marker_data["lang"] = lang
    marker_path.write_text(
        json.dumps(marker_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return count
