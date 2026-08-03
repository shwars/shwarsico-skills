# OpenAI Agents SDK

Load this reference only when the user explicitly asks for OpenAI Agents SDK, `Runner`, handoffs, or multi-agent behavior. For an ordinary tool-using agent, use direct Responses API patterns from `tools.md`.

Install `openai-agents python-dotenv`.

## Basic connection and run

```python
import asyncio
import os

from agents import Agent, Runner, function_tool, set_tracing_disabled
from agents.models.openai_responses import OpenAIResponsesModel
from dotenv import load_dotenv
from openai import AsyncOpenAI


def create_agents_model(
    folder_id: str | None = None,
    api_key: str | None = None,
) -> OpenAIResponsesModel:
    load_dotenv()
    folder_id = folder_id or os.getenv("folder_id")
    api_key = api_key or os.getenv("api_key")
    if not folder_id or not api_key:
        raise RuntimeError("Set folder_id and api_key in .env or pass them explicitly")

    client = AsyncOpenAI(
        base_url="https://ai.api.cloud.yandex.net/v1",
        api_key=api_key,
        project=folder_id,
    )
    qwen3_model = f"gpt://{folder_id}/qwen3-235b-a22b-fp8"
    agents_model = OpenAIResponsesModel(
        model=qwen3_model,
        openai_client=client,
    )
    return agents_model


@function_tool
def word_count(text: str) -> str:
    """Count words in text."""
    return str(len(text.split()))


async def main() -> None:
    set_tracing_disabled(True)
    agents_model = create_agents_model()
    agent = Agent(
        name="Editor",
        model=agents_model,
        instructions="Answer concisely and use the word-count tool when needed.",
        tools=[word_count],
    )
    result = await Runner.run(agent, "Count the words in: Yandex AI Studio works")
    print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())
```

Disable built-in tracing because it expects OpenAI-hosted tracing credentials. Add `WebSearchTool`, hosted MCP tools, streaming, handoffs, or agents-as-tools only when the user explicitly requests them; do not turn a basic connection example into a multi-agent framework.

## Sources

- `7-multiagent/DeepResearch.ipynb`
- `7-multiagent/Labs/DeepResearchLab-Solution.ipynb`
