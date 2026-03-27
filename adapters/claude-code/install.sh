#!/bin/bash
# Install cad-skill as a Claude Code skill into a target project.
# Usage: bash install.sh /path/to/your-project

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

TARGET="${1:-.}"
TARGET="$(cd "$TARGET" && pwd)"

echo "Installing cad-skill into: $TARGET"

# 1. Copy slash commands (all 5)
mkdir -p "$TARGET/.claude/commands"
for cmd in cad-help.md cad-spec.md cad-codegen.md cad-enhance.md mechdesign.md; do
  cp "$SCRIPT_DIR/commands/$cmd" "$TARGET/.claude/commands/"
done
echo "  OK Slash commands → .claude/commands/ (5 commands)"

# 2. Copy skill knowledge files
cp "$REPO_ROOT/skill_cad_help.md" "$TARGET/"
cp "$REPO_ROOT/skill_mech_design.md" "$TARGET/"
echo "  OK Skill knowledge → skill_cad_help.md, skill_mech_design.md"

# 3. Copy core Python tools
for f in cad_pipeline.py cad_spec_gen.py cad_spec_extractors.py cad_spec_defaults.py \
         cad_spec_reviewer.py bom_parser.py orientation_check.py \
         enhance_prompt.py prompt_data_builder.py annotate_render.py cad_paths.py; do
  cp "$REPO_ROOT/$f" "$TARGET/" 2>/dev/null || true
done
echo "  OK Python tools → cad_pipeline.py, cad_spec_gen.py, enhance_prompt.py, prompt_data_builder.py, ..."

# 4. Copy config, templates, codegen, docs
mkdir -p "$TARGET/config" "$TARGET/templates" "$TARGET/codegen" "$TARGET/docs"
cp -r "$REPO_ROOT/config/"* "$TARGET/config/" 2>/dev/null || true
cp -r "$REPO_ROOT/templates/"* "$TARGET/templates/" 2>/dev/null || true
cp -r "$REPO_ROOT/codegen/"* "$TARGET/codegen/" 2>/dev/null || true
cp -r "$REPO_ROOT/docs/"* "$TARGET/docs/" 2>/dev/null || true
echo "  OK Config, templates, codegen, docs"

# 5. Copy pipeline config
cp "$REPO_ROOT/pipeline_config.json" "$TARGET/" 2>/dev/null || true
echo "  OK pipeline_config.json"

echo ""
echo "Done! Now in Claude Code, type:"
echo "  /cad-help                    — interactive pipeline assistant"
echo "  /cad-spec <file.md>          — generate CAD spec (Phase 1)"
echo "  /cad-codegen <subsystem>     — generate CadQuery scaffolds (Phase 2)"
echo "  /cad-enhance <subsystem>     — AI image enhancement (Phase 5)"
echo "  /mechdesign <subsystem>      — mechanical design assistant"
