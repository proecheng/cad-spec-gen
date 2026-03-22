# /cad-spec — Generate CAD Spec from Design Document

User input: $ARGUMENTS

## Instructions

Run the CAD Spec Generator on the specified design document.

### Routing Rules

1. **No arguments** (`$ARGUMENTS` is empty) → Show usage:
   ```
   Usage: /cad-spec <design_doc.md> [--force]

   Examples:
     /cad-spec examples/04-末端执行机构设计.md
     /cad-spec docs/design/05-电气系统设计.md --force
     /cad-spec --all
   ```

2. **`--all`** → Process all subsystems:
   ```bash
   python cad_spec_gen.py --all --config config/gisbot.json
   ```

3. **File path** → Process single document:
   ```bash
   python cad_spec_gen.py "$ARGUMENTS" --config config/gisbot.json --output-dir ./output
   ```

4. After generation, read the output CAD_SPEC.md and summarize:
   - Number of parameters, fasteners, BOM parts extracted
   - Any CRITICAL or WARNING missing data items
   - Location of output file
