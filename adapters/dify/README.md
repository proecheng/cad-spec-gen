# Dify / Coze Adapter

Use the CAD pipeline skill with Dify, Coze, or other low-code AI platforms.

## Dify Setup

### Method 1: Knowledge Base (Recommended)

1. Create a new Knowledge Base in Dify
2. Upload these files:
   - `system_prompt.md` — universal system prompt
   - `skill_cad_help.md` — full knowledge base (15 intents)
3. Create a new Agent app, attach the Knowledge Base
4. In the Agent's system prompt, add:
   ```
   You are a CAD rendering pipeline assistant.
   Use the knowledge base to answer questions about the CAD pipeline.
   When execution is needed, generate shell commands for the user to run.
   ```

### Method 2: Tool Node (with Code Execution)

If your Dify setup supports Code Execution nodes:

1. Add a Code node with the CLI commands from `system_prompt.md`
2. Map user intents to tool calls using the intent routing table
3. Return results to the LLM node for formatting

## Coze Setup

1. Create a new Bot
2. Add a Knowledge plugin, upload `system_prompt.md` and `skill_cad_help.md`
3. Enable Code Interpreter if available
4. Set the bot's persona to the content of `system_prompt.md`

## FastGPT / Other Platforms

The same pattern applies:
1. **Knowledge**: Upload `system_prompt.md` + `skill_cad_help.md`
2. **System prompt**: Use `system_prompt.md` content
3. **Execution**: Enable shell/code execution if available; otherwise generate commands for users to copy-paste

## Key Files

| File | Purpose |
|------|---------|
| `../../system_prompt.md` | Universal system prompt — paste into any platform |
| `../../skill_cad_help.md` | Full knowledge base with 15 intents and actions |
| `../../skill.json` | Machine-readable skill manifest |
