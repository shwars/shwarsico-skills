# Responses API basics

## Contents

- Client setup
- Basic response and conversation
- Pydantic structured output
- Streaming
- Multimodal image input

## Client setup

Install the common dependencies with `pip install openai python-dotenv pydantic pillow`.

Use this setup once per program. Explicit arguments take precedence over `.env` values.

```python
import os

from dotenv import load_dotenv
from openai import OpenAI


def create_client(
    folder_id: str | None = None,
    api_key: str | None = None,
) -> tuple[OpenAI, str]:
    load_dotenv()
    folder_id = folder_id or os.getenv("folder_id")
    api_key = api_key or os.getenv("api_key")
    if not folder_id or not api_key:
        raise RuntimeError("Set folder_id and api_key in .env or pass them explicitly")

    client = OpenAI(
        base_url="https://ai.api.cloud.yandex.net/v1",
        api_key=api_key,
        project=folder_id,
    )
    return client, folder_id


client, folder_id = create_client()
```

Append only the concrete URI variables needed from `models.md`. The examples below use `qwen3_model` for text and `qwen36_model` for image input.

## Basic response and conversation

```python
response = client.responses.create(
    model=qwen3_model,
    instructions="Answer clearly and briefly.",
    input="Explain the Responses API in two sentences.",
)
print(response.output_text)

follow_up = client.responses.create(
    model=qwen3_model,
    previous_response_id=response.id,
    input="Give me one minimal use case.",
)
print(follow_up.output_text)
```

Responses are stored by default. Set `store=True` explicitly when the behavior should be obvious in teaching code. Save only the latest `response.id` for the next turn.

## Pydantic structured output

```python
from pydantic import BaseModel, Field


class ArticleSummary(BaseModel):
    title: str
    key_points: list[str] = Field(min_length=1)
    sentiment: str


response = client.responses.parse(
    model=qwen3_model,
    input="Summarize: AI agents can call tools and maintain conversation context.",
    text_format=ArticleSummary,
)

summary: ArticleSummary = response.output_parsed
print(summary.model_dump_json(indent=2))
```

Use `responses.parse`, not manual JSON extraction, whenever the caller wants typed output.

## Streaming

```python
with client.responses.stream(
    model=qwen3_model,
    input="Write a short birthday toast.",
) as stream:
    for event in stream:
        if event.type == "response.output_text.delta":
            print(event.delta, end="", flush=True)

    final_response = stream.get_final_response()

print("\nResponse ID:", final_response.id)
```

This direct Responses API streaming pattern comes from the current Yandex AI Studio migration documentation because the course notebooks demonstrate token streaming only through the Agents SDK.

## Multimodal image input

```python
import base64
import io

from PIL import Image


def image_data_url(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


image = Image.open("photo.jpg")
response = client.responses.create(
    model=qwen36_model,
    input=[
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Describe this image briefly."},
                {
                    "type": "input_image",
                    "image_url": image_data_url(image),
                    "detail": "auto",
                },
            ],
        }
    ],
)
print(response.output_text)
```

## Sources

- `1-intro-ai-studio/CloudConnect.ipynb`
- `2-responses-api/ResponsesAPI.ipynb`
- `2-responses-api/Labs/PaperSummarize-Solution.ipynb`
- `2-responses-api/Labs/AgenticImageGeneraton-Solution.ipynb`
- Streaming: official Yandex AI Studio Responses API migration guide
