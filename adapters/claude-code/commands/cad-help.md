# /cad-help — CAD Hybrid Rendering Pipeline Interactive Help

User input: $ARGUMENTS

## Instructions

Read the skill knowledge file `skill_cad_help.md` (located in the same repo's root directory), then execute based on user input:

### Routing Rules

1. **No arguments** (`$ARGUMENTS` is empty) → Show help panel:
   - Output the "Help Panel" template at the end of skill_cad_help.md
   - List common question examples in 4 groups: Environment & Install / Config & Validation / Workflows / Status & Troubleshooting

2. **With arguments** → Intent matching + execution:
   - Extract keywords from `$ARGUMENTS` text
   - Match against the "Intent Matching Table" in skill_cad_help.md, select best match
   - Execute the matched intent's "Action Details" (run commands if possible, guide step-by-step if needed)
   - If no intent matches, reply "Could not understand your question" and show help panel

### Execution Constraints

- Environment check (env_check): run each detection command, report status with checkmarks
- Validate config (validate): read and check render_config.json completeness
- Render (render): confirm GLB exists before executing render commands
- Troubleshoot (troubleshoot): ask user for specific error message, then match against troubleshooting guide
- Status (status): scan cad/ and output/ directories, count artifacts
- All output should be concise, using status markers
