"""
LangChain / AutoGen adapter for cad-spec-gen.

Usage:
    from adapters.langchain.tools import cad_tools
    agent = initialize_agent(tools=cad_tools, llm=your_llm, ...)
"""

from langchain.tools import ShellTool, Tool
from pathlib import Path

# Load system prompt as agent knowledge
_repo_root = Path(__file__).resolve().parent.parent.parent
_system_prompt = (_repo_root / "system_prompt.md").read_text(encoding="utf-8")

shell = ShellTool()

cad_spec_tool = Tool(
    name="cad_spec_gen",
    description="Generate structured CAD_SPEC.md from a Markdown design document. "
                "Input: shell command starting with 'python cad_spec_gen.py ...'",
    func=lambda cmd: shell.run(cmd),
)

bom_parser_tool = Tool(
    name="bom_parser",
    description="Parse BOM tables from a design document. "
                "Input: shell command starting with 'python bom_parser.py ...'",
    func=lambda cmd: shell.run(cmd),
)

cad_tools = [cad_spec_tool, bom_parser_tool, shell]

# For agents that accept a system message, inject the pipeline knowledge:
SYSTEM_MESSAGE = _system_prompt
