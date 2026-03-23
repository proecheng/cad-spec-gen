# OpenAI / GPT-4 Adapter

Use the CAD pipeline skill with GPT-4, GPT-4o, or OpenAI Assistants API.

## Option A: Assistants API (Recommended)

1. Create an Assistant with **Code Interpreter** enabled
2. Upload these files as knowledge:
   - `system_prompt.md` (from repo root)
   - `skill_cad_help.md` (from repo root)
3. Set the system instructions to:
   ```
   You are a CAD rendering pipeline assistant. Follow the instructions in system_prompt.md.
   When the user asks a question, use the intent routing table to determine the action.
   Execute CLI commands using Code Interpreter.
   ```
4. Upload your project's Python tools (`cad_spec_gen.py`, etc.) for direct execution

## Option B: Function Calling

1. Load `functions.json` from this directory
2. Register the 3 functions: `cad_help`, `cad_spec`, `bom_parse`
3. In your function handler, map to CLI commands:

```python
import subprocess, json

def handle_function(name, args):
    if name == "cad_spec":
        cmd = ["python", "cad_spec_gen.py"]
        if args.get("all"):
            cmd.append("--all")
        elif args.get("file"):
            cmd.append(args["file"])
        cmd.extend(["--config", args["config"]])
        if args.get("output_dir"):
            cmd.extend(["--output-dir", args["output_dir"]])
        if args.get("force"):
            cmd.append("--force")
        if args.get("review"):
            cmd.append("--review")
        if args.get("review_only"):
            cmd.append("--review-only")
        return subprocess.run(cmd, capture_output=True, text=True).stdout

    elif name == "bom_parse":
        cmd = ["python", "bom_parser.py", args["file"]]
        fmt = args.get("format", "tree")
        if fmt == "json":
            cmd.append("--json")
        elif fmt == "summary":
            cmd.append("--summary")
        return subprocess.run(cmd, capture_output=True, text=True).stdout

    elif name == "cad_help":
        # For cad_help, feed query + skill_cad_help.md to the LLM
        # and let it determine the intent and action
        return f"Process this query using skill_cad_help.md: {args['query']}"
```

## Option C: Custom GPT

1. Create a Custom GPT at chat.openai.com
2. Paste `system_prompt.md` content as Instructions
3. Upload `skill_cad_help.md` as a Knowledge file
4. Enable Code Interpreter for CLI execution
