# Responses API tools

## Contents

- Local Pydantic function calling
- Web search
- Hosted MCP servers
- MCP approvals
- Inspecting tool activity

Assume `client` comes from `responses.md` and `qwen3_model` from `models.md`.

## Local Pydantic function calling

Define local tools as Pydantic models, derive their JSON schemas, execute validated arguments locally, and return `function_call_output` items.

```python
import json
import math

from pydantic import BaseModel, Field


class SquareRoot(BaseModel):
    """Calculate a square root."""

    value: float = Field(ge=0)

    def process(self) -> str:
        return str(math.sqrt(self.value))


tool_classes = [SquareRoot]
tool_map = {tool.__name__: tool for tool in tool_classes}
tools = [
    {
        "type": "function",
        "name": tool.__name__,
        "description": tool.__doc__ or "",
        "parameters": tool.model_json_schema(),
    }
    for tool in tool_classes
]

response = client.responses.create(
    model=qwen3_model,
    instructions="Use the tool for calculations.",
    input="What is the square root of 2026?",
    tools=tools,
)

while True:
    calls = [item for item in response.output if item.type == "function_call"]
    if not calls:
        break

    outputs = []
    for call in calls:
        tool_type = tool_map[call.name]
        arguments = json.loads(call.arguments or "{}")
        result = tool_type.model_validate(arguments).process()
        outputs.append(
            {
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": result,
            }
        )

    response = client.responses.create(
        model=qwen3_model,
        previous_response_id=response.id,
        input=outputs,
        tools=tools,
    )

print(response.output_text)
```

Catch validation and execution exceptions in public-facing applications and return a short error string as the tool output.

## Web search

```python
web_search = {
    "type": "web_search",
    "search_context_size": "high",
    "filters": {"allowed_domains": ["arxiv.org"]},
}

response = client.responses.create(
    model=qwen3_model,
    instructions="Search when current information is required and cite sources.",
    input="Find recent papers about multi-agent systems.",
    tools=[web_search],
)
print(response.output_text)
```

Supported notebook patterns include `search_context_size`, `filters.allowed_domains`, and `filters.user_location.region`.

## Hosted MCP servers

Responses API connects to the remote MCP server and executes its tools. No local `mcp` package is required for this hosted pattern.

```python
mcp_tool = {
    "type": "mcp",
    "server_label": "Research",
    "server_description": "Search a trusted research catalog",
    "server_url": "https://mcp.example.com/sse",
    "require_approval": "never",
}

response = client.responses.create(
    model=qwen3_model,
    instructions="Use the research server to answer the question.",
    input="Find papers about visual transformers.",
    tools=[mcp_tool],
)
print(response.output_text)
```

Use multiple MCP servers by passing multiple dictionaries:

```python
mcp_tools = [
    {
        "type": "mcp",
        "server_label": "Research",
        "server_description": "Search papers",
        "server_url": "https://research.example.com/sse",
        "require_approval": "never",
    },
    {
        "type": "mcp",
        "server_label": "Notes",
        "server_description": "Store research notes",
        "server_url": "https://notes.example.com/sse",
        "require_approval": "never",
    },
]

response = client.responses.create(
    model=qwen3_model,
    input="Research visual transformers and save a note.",
    tools=mcp_tools,
)
```

Replace example URLs with user-supplied reachable servers. Use `require_approval="never"` only when the user trusts the server and authorizes automatic calls.

## MCP approvals

When a server requests approval, present it to the user unless the application has an explicit approval policy. After approval:

```python
approval_requests = [
    item for item in response.output if item.type == "mcp_approval_request"
]

if approval_requests:
    response = client.responses.create(
        model=qwen3_model,
        previous_response_id=response.id,
        tools=[mcp_tool],
        input=[
            {
                "type": "mcp_approval_response",
                "approval_request_id": item.id,
                "approve": True,
            }
            for item in approval_requests
        ],
    )
```

## Inspecting tool activity

```python
for item in response.output:
    if item.type == "web_search_call":
        print("Web query:", item.action.query)
    elif item.type == "mcp_call":
        print("MCP call:", item.server_label, item.name, item.arguments)
    elif item.type == "function_call":
        print("Function call:", item.name, item.arguments)
```

## Sources

- `3-tool-calling/ToolCalling.ipynb`
- `3-tool-calling/ArxivResearch.ipynb`
- `4-rag-search/WebSearch.ipynb`
- `6-mcp/ArxivResearchMCP.ipynb`
- `6-mcp/Labs/MCPTravelLab-Solution.ipynb`
- `4-rag-search/Agent.py` for the approval-response pattern
