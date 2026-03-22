#!/bin/bash
# Install cad-spec-gen as a Claude Code skill into a target project.
# Usage: bash install.sh /path/to/your-project

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

TARGET="${1:-.}"
TARGET="$(cd "$TARGET" && pwd)"

echo "Installing cad-spec-gen skill into: $TARGET"

# 1. Copy slash commands
mkdir -p "$TARGET/.claude/commands"
cp "$SCRIPT_DIR/commands/cad-help.md" "$TARGET/.claude/commands/"
cp "$SCRIPT_DIR/commands/cad-spec.md" "$TARGET/.claude/commands/"
echo "  ✅ Slash commands → .claude/commands/"

# 2. Copy skill knowledge file
cp "$REPO_ROOT/skill_cad_help.md" "$TARGET/"
echo "  ✅ Skill knowledge → skill_cad_help.md"

# 3. Copy core Python tools
for f in cad_spec_gen.py cad_spec_extractors.py cad_spec_defaults.py bom_parser.py; do
  cp "$REPO_ROOT/$f" "$TARGET/"
done
echo "  ✅ Python tools → cad_spec_gen.py, bom_parser.py, ..."

# 4. Copy config and templates
mkdir -p "$TARGET/config" "$TARGET/templates"
cp -r "$REPO_ROOT/config/"* "$TARGET/config/" 2>/dev/null || true
cp -r "$REPO_ROOT/templates/"* "$TARGET/templates/" 2>/dev/null || true
echo "  ✅ Config & templates"

echo ""
echo "Done! Now in Claude Code, type:"
echo "  /cad-help              — interactive pipeline assistant"
echo "  /cad-spec <file.md>    — generate CAD spec"
