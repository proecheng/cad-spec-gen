# CAD Spec Generator

Auto-generate structured CAD specification documents from Markdown design documents.

The tool parses design docs to extract **9 categories** of structured data:

1. **Global Parameters** — dimensions, tolerances, from parameter tables
2. **Tolerances & Surface Finish** — dimensional, GD&T, surface roughness
3. **Fasteners** — bolt specs, torque, auto-filled standard defaults
4. **Connection Matrix** — synthesized from fasteners + assembly layers
5. **BOM Tree** — full bill of materials with cost summary
6. **Assembly Pose & Positioning** — coordinate system, layer stack
7. **Visual IDs** — material, color, labels for each part
8. **Render Plan** — iteration groups, camera views, negative constraints
9. **Completeness Report** — missing data with severity levels

## Features

- **Idempotent**: skips regeneration if source MD5 hasn't changed
- **Auto-defaults**: fills standard bolt torques (8.8 grade), surface Ra by material
- **Derived calculations**: total cost, part count, BOM completeness %
- **Configurable**: subsystem mapping via JSON config files
- **Zero dependencies**: Python 3.9+ stdlib only

## Quick Start

```bash
# Clone
git clone https://github.com/YOUR_USER/cad-spec-gen.git
cd cad-spec-gen

# Run on a design document
python cad_spec_gen.py examples/04-末端执行机构设计.md \
    --config config/gisbot.json \
    --output-dir ./output

# Check output
cat output/end_effector/CAD_SPEC.md
```

## Usage

```
python cad_spec_gen.py [FILES...] --config CONFIG [OPTIONS]

Arguments:
  FILES                 Design document paths (NN-*.md)

Required:
  --config PATH         JSON config with subsystem mapping

Options:
  --output-dir DIR      Output directory (default: ./output)
  --doc-dir DIR         Design docs directory for --all
  --all                 Process all NN-*.md in doc-dir
  --force               Force regeneration (ignore MD5 check)
```

### Process a single document

```bash
python cad_spec_gen.py docs/design/04-末端执行机构设计.md --config config/gisbot.json
```

### Process all subsystems

```bash
python cad_spec_gen.py --all --config config/gisbot.json --doc-dir docs/design
```

### BOM parser standalone

```bash
python bom_parser.py examples/04-末端执行机构设计.md          # tree view
python bom_parser.py examples/04-末端执行机构设计.md --json   # JSON output
python bom_parser.py examples/04-末端执行机构设计.md --summary # one-line summary
```

## Configuration

Create a JSON config file (see `config/gisbot.json` for a complete example):

```json
{
  "doc_dir": "docs/design",
  "output_dir": "./output",
  "subsystems": {
    "04": {
      "name": "End Effector",
      "prefix": "GIS-EE",
      "cad_dir": "end_effector",
      "aliases": ["ee", "end_effector"]
    }
  }
}
```

| Key | Description |
|-----|-------------|
| `doc_dir` | Default directory for `--all` mode |
| `output_dir` | Default output directory |
| `subsystems` | Map of chapter number → subsystem info |
| `subsystems.*.name` | Display name |
| `subsystems.*.prefix` | Part number prefix (e.g. `GIS-EE`) |
| `subsystems.*.cad_dir` | Output subdirectory name |
| `subsystems.*.aliases` | Alternative names for lookup |

## Design Document Format

The tool expects Markdown documents with:

- **Filename**: `NN-<name>.md` (e.g., `04-末端执行机构设计.md`)
- **Parameter tables**: columns containing `参数|设计值` or `尺寸|值`
- **BOM table**: columns containing `料号` and `名称`
- **Assembly tables**: `层级`, `术语|定义`, etc.

See `examples/` and `templates/cad_spec_template.md` for format details.

## Project Structure

```
├── cad_spec_gen.py          # Main generator (CLI entry point)
├── cad_spec_extractors.py   # 8 extraction functions
├── cad_spec_defaults.py     # Standard defaults & completeness rules
├── bom_parser.py            # BOM table parser (also standalone CLI)
├── config/
│   └── gisbot.json          # Example: GISBOT project config
├── templates/
│   └── cad_spec_template.md # Output template reference
└── examples/
    └── 04-末端执行机构设计.md # Example design document
```

## License

MIT
