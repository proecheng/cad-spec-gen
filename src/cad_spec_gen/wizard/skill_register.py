"""Register (copy) skill files to the target project directory.

Extracted from install.py with language-awareness and PyPI data source support.
"""

import hashlib
import json
import os
import shutil
from datetime import datetime
from importlib.resources import files
from pathlib import Path

from .i18n import t
from . import ui

# Files that users may customize — never overwrite silently
USER_CONFIG_FILES = ["config/gisbot.json"]

# Python tools to copy from data/python_tools/ → target root
# Pipeline-specific tools (not shared across subsystems)
_PIPELINE_TOOLS = [
    "cad_pipeline.py", "cad_spec_gen.py", "cad_spec_extractors.py",
    "cad_spec_reviewer.py", "cad_paths.py",
    "bom_parser.py", "annotate_render.py",
    "enhance_prompt.py", "prompt_data_builder.py",
    "gemini_gen.py",
    "comfyui_enhancer.py", "comfyui_env_check.py",
    "fal_enhancer.py", "fal_comfy_enhancer.py", "fal_comfy_env_check.py",
    "engineering_enhancer.py",
    "pipeline_config.json",
]

# Import shared tool list from cad_paths (single source of truth)
try:
    import sys as _sys
    from pathlib import Path as _P
    # cad_paths.py lives in the packaged data/python_tools/ directory
    _tools_dir = _P(__file__).parent.parent / "data" / "python_tools"
    if str(_tools_dir) not in _sys.path:
        _sys.path.insert(0, str(_tools_dir))
    from cad_paths import SHARED_TOOL_FILES as _SHARED
except ImportError:
    # Fallback: hardcoded list (keep in sync manually if import fails)
    _SHARED = ["drawing.py", "draw_three_view.py", "cq_to_dxf.py",
               "render_dxf.py", "render_config.py", "cad_spec_defaults.py"]

PYTHON_TOOLS = _PIPELINE_TOOLS + list(_SHARED)

# Directories to copy from data/{name}/ → target/{name}/
COPY_DIRS = ["codegen", "config", "templates", "tools"]

# Slash commands (from data/commands/{lang}/)
COMMAND_FILES = [
    "cad-help.md", "cad-spec.md", "cad-codegen.md",
    "cad-enhance.md", "mechdesign.md",
]

AGENT_CHOICES = ("claude", "codex", "both")

_CODEX_DESCRIPTIONS = {
    "cad-help": (
        "Use when helping with cad-spec-gen CAD pipeline questions, environment "
        "checks, status, troubleshooting, or next-step recommendations."
    ),
    "cad-spec": (
        "Use when converting mechanical design documents into CAD_SPEC.md, "
        "DESIGN_REVIEW.md, or structured cad-spec-gen Phase 1 outputs."
    ),
    "cad-codegen": (
        "Use when generating CadQuery scaffold code, std parts, assemblies, or "
        "geometry reports from CAD_SPEC.md in cad-spec-gen."
    ),
    "cad-enhance": (
        "Use when enhancing Blender CAD renders with gemini, fal, comfyui, or "
        "engineering backends in cad-spec-gen."
    ),
    "mechdesign": (
        "Use when doing manual parametric mechanical design with CadQuery, GB/T "
        "drawings, rendering, enhancement, or purchased-part reuse."
    ),
}


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


def _write_version_marker(target, version, lang="zh", agent="claude", codex_dir=None):
    """Write version marker with file hashes."""
    hashes = {}
    # Individual files
    for name in PYTHON_TOOLS:
        p = target / name
        if p.exists():
            hashes[name] = _file_hash(p)
    # Knowledge files
    for name in ["skill_cad_help.md", "skill_mech_design.md"]:
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
        "lang": lang,
        "agent": agent,
        "files": hashes,
    }
    if codex_dir is not None:
        marker["codex_skills_dir"] = str(Path(codex_dir))
    (target / ".cad_skill_version.json").write_text(
        json.dumps(marker, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _normalize_agent(agent):
    """Validate and normalize the requested agent adapter."""
    normalized = (agent or "claude").lower()
    if normalized not in AGENT_CHOICES:
        raise ValueError(
            f"Unsupported agent {agent!r}; expected one of {', '.join(AGENT_CHOICES)}"
        )
    return normalized


def default_codex_skills_dir():
    """Default directory where Codex discovers personal skills."""
    agents_home = os.environ.get("AGENTS_HOME")
    if agents_home:
        base = Path(agents_home).expanduser()
        return base if base.name == "skills" else base / "skills"

    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        base = Path(codex_home).expanduser()
        return base if base.name == "skills" else base / "skills"

    return Path.home() / ".agents" / "skills"


def _codex_description(skill):
    """Return concise Codex trigger text for SKILL.md frontmatter."""
    skill_id = skill["id"]
    if skill_id in _CODEX_DESCRIPTIONS:
        return _CODEX_DESCRIPTIONS[skill_id]

    desc = skill.get("description", "").replace("\n", " ").strip()
    if len(desc) > 360:
        desc = desc[:357].rstrip() + "..."
    return f"Use when working with cad-spec-gen {skill_id}. {desc}".replace(":", " -")


def _clean_command_body(text):
    """Remove slash-command argument placeholders that do not apply to Codex."""
    lines = []
    for line in text.splitlines():
        if "$ARGUMENTS" in line:
            continue
        lines.append(line)
    return "\n".join(lines).strip() + "\n"


def _render_codex_skill(skill, command_text):
    """Render one Codex SKILL.md from the canonical command markdown."""
    skill_id = skill["id"]
    trigger = skill.get("trigger", f"/{skill_id}")
    entry_point = skill.get("entry_point", "python cad_pipeline.py")
    description = _codex_description(skill)
    command_body = _clean_command_body(command_text)

    return (
        "---\n"
        f"name: {skill_id}\n"
        f"description: {description}\n"
        "---\n\n"
        "<!-- AUTO-GENERATED by cad-skill-setup; edit skill.json/commands and reinstall. -->\n\n"
        f"# {skill.get('name', skill_id)} ({trigger})\n\n"
        "## Codex usage\n\n"
        f"- Treat this as the Codex form of `{trigger}`; infer parameters from the "
        "user request and current repository files.\n"
        f"- Prefer the local project scripts installed by `cad-skill-setup`, "
        f"especially `{entry_point}`.\n"
        "- If the project lacks the CAD pipeline scripts, ask the user to run "
        "`cad-skill-setup --agent codex --target <project>` first.\n\n"
        "## Canonical command instructions\n\n"
        f"{command_body}"
    )


def _register_codex_skills(data, lang, codex_dir):
    """Write Codex SKILL.md files to the global Codex skills directory."""
    manifest = json.loads((data / "skill.json").read_text(encoding="utf-8"))
    skills_dir = Path(codex_dir).expanduser().resolve()
    command_dir = data / "commands" / lang
    count = 0

    for skill in manifest.get("skills", []):
        skill_id = skill["id"]
        command_path = command_dir / f"{skill_id}.md"
        if not command_path.exists():
            continue
        skill_dst = skills_dir / skill_id / "SKILL.md"
        skill_dst.parent.mkdir(parents=True, exist_ok=True)
        skill_dst.write_text(
            _render_codex_skill(
                skill,
                command_path.read_text(encoding="utf-8"),
            ),
            encoding="utf-8",
        )
        count += 1

    ui.success(f"Codex skills ({count} SKILL.md files) → {skills_dir}")
    return count


def register_skill(
    target_dir,
    lang="zh",
    version=None,
    update=False,
    agent="claude",
    codex_dir=None,
):
    """Copy all skill files to the target project directory.

    Args:
        target_dir: Path to the target project
        lang: "zh" or "en" — selects command and knowledge file language
        version: Version string for the marker
        update: If True, check for user-modified configs
        agent: "claude", "codex", or "both" — selects generated agent adapters
        codex_dir: Codex global skills directory (default: ~/.agents/skills)

    Returns:
        int: Number of files copied
    """
    if version is None:
        from .. import __version__
        version = __version__
    target = Path(target_dir).resolve()
    data = _data_root()
    installed = _read_installed_version(target) if update else None
    agent = _normalize_agent(agent)
    codex_dir = (
        Path(codex_dir).expanduser().resolve()
        if codex_dir is not None
        else default_codex_skills_dir().resolve()
    )
    count = 0

    # 1. Claude slash commands (language-specific)
    if agent in ("claude", "both"):
        cmd_src = data / "commands" / lang
        cmd_dst = target / ".claude" / "commands"
        cmd_dst.mkdir(parents=True, exist_ok=True)
        command_count = 0
        for name in COMMAND_FILES:
            src = cmd_src / name
            if src.exists():
                _safe_copy(src, cmd_dst / name)
                count += 1
                command_count += 1
        ui.success(f".claude/commands/ ({command_count} commands, {lang})")

    # 2. Knowledge files (language-specific)
    for (src_pattern, dst_name) in [
        (f"skill_cad_help_{lang}.md", "skill_cad_help.md"),
        (f"skill_mech_design_{lang}.md", "skill_mech_design.md"),
    ]:
        knowledge_src = data / "knowledge" / src_pattern
        if knowledge_src.exists():
            _safe_copy(knowledge_src, target / dst_name)
            count += 1
            ui.success(dst_name)

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

    # 6. Codex global skills
    if agent in ("codex", "both"):
        count += _register_codex_skills(data, lang, codex_dir)

    # 7. Version marker
    _write_version_marker(
        target,
        version,
        lang=lang,
        agent=agent,
        codex_dir=codex_dir if agent in ("codex", "both") else None,
    )

    return count
