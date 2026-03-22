#!/usr/bin/env python3
"""
cad-spec-gen Universal Installer

Install the CAD pipeline skill into any LLM/Agent platform.

Usage:
    python install.py --platform claude-code --target /path/to/project
    python install.py --platform openai
    python install.py --platform system-prompt
    python install.py --platform langchain
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent


def install_claude_code(target: Path):
    """Copy slash commands and skill files to a Claude Code project."""
    commands_dir = target / ".claude" / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)

    src_commands = REPO_ROOT / "adapters" / "claude-code" / "commands"
    for f in src_commands.glob("*.md"):
        shutil.copy2(f, commands_dir / f.name)
        print(f"  ✅ {f.name} → .claude/commands/")

    # Copy skill knowledge
    shutil.copy2(REPO_ROOT / "skill_cad_help.md", target / "skill_cad_help.md")
    print("  ✅ skill_cad_help.md → project root")

    # Copy Python tools
    for name in ["cad_spec_gen.py", "cad_spec_extractors.py",
                  "cad_spec_defaults.py", "bom_parser.py"]:
        src = REPO_ROOT / name
        if src.exists():
            shutil.copy2(src, target / name)
    print("  ✅ Python tools copied")

    # Copy config and templates
    for dirname in ["config", "templates"]:
        src_dir = REPO_ROOT / dirname
        dst_dir = target / dirname
        if src_dir.exists():
            if dst_dir.exists():
                shutil.rmtree(dst_dir)
            shutil.copytree(src_dir, dst_dir)
    print("  ✅ config/ and templates/ copied")

    print(f"\nDone! In Claude Code, type:")
    print(f"  /cad-help              — interactive pipeline assistant")
    print(f"  /cad-spec <file.md>    — generate CAD spec")


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
        description="Install cad-spec-gen skill into any LLM/Agent platform"
    )
    parser.add_argument(
        "--platform", "-p",
        required=True,
        choices=["claude-code", "openai", "system-prompt", "langchain", "dify"],
        help="Target platform"
    )
    parser.add_argument(
        "--target", "-t",
        default=".",
        help="Target project directory (for claude-code platform)"
    )
    args = parser.parse_args()

    if args.platform == "claude-code":
        target = Path(args.target).resolve()
        if not target.exists():
            print(f"Error: target directory does not exist: {target}")
            sys.exit(1)
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
