# LangChain / AutoGen Adapter

Use the CAD pipeline skill with LangChain, AutoGen, CrewAI, or similar agent frameworks.

## Quick Start

```python
from langchain.agents import initialize_agent
from adapters.langchain.tools import cad_tools, SYSTEM_MESSAGE

agent = initialize_agent(
    tools=cad_tools,
    llm=your_llm,
    agent_type="zero-shot-react-description",
    system_message=SYSTEM_MESSAGE
)

agent.run("Generate CAD spec for docs/design/04-末端执行机构设计.md")
```

## Manual Setup

If you prefer not to import from this adapter:

```python
from langchain.tools import ShellTool

# Load the universal system prompt as agent knowledge
system_prompt = open("system_prompt.md").read()

agent = initialize_agent(
    tools=[ShellTool()],
    llm=your_llm,
    agent_type="zero-shot-react-description",
    system_message=system_prompt
)

agent.run("Help me render the end effector assembly")
```

## AutoGen

```python
from autogen import AssistantAgent, UserProxyAgent

system_prompt = open("system_prompt.md").read()

assistant = AssistantAgent("cad_assistant", system_message=system_prompt)
user_proxy = UserProxyAgent("user", code_execution_config={"work_dir": "."})

user_proxy.initiate_chat(assistant, message="Generate CAD spec for the end effector")
```

## Key Files

| File | Purpose |
|------|---------|
| `tools.py` | Pre-configured LangChain tools + system message |
| `../../system_prompt.md` | Universal system prompt (injected automatically) |
| `../../skill_cad_help.md` | Full knowledge base (16 intents + actions) |
