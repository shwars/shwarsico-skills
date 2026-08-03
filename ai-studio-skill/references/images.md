# Image generation

## Contents

- Direct Images API to PIL
- Generate an artistic prompt and save JPG
- Hosted Image Generation tool
- Iterative prompt, generate, and evaluate loop

Assume `client` and `folder_id` come from `responses.md`, and `qwen3_model`, `qwen36_model`, and `alice_art_model` come from `models.md`. Install Pillow with `pip install pillow`.

## Direct Images API to PIL

```python
import base64
import io

from PIL import Image


def generate_image(
    prompt: str,
    model: str = alice_art_model,
    size: str = "1536x1024",
) -> Image.Image:
    if len(prompt) > 500:
        raise ValueError("Alice AI ART prompts must not exceed 500 characters")
    response = client.images.generate(
        model=model,
        prompt=prompt,
        n=1,
        size=size,
    )
    image_bytes = base64.b64decode(response.data[0].b64_json)
    return Image.open(io.BytesIO(image_bytes))
```

Always use `client.images.generate`, which is the Python SDK method used by the course.

## Generate an artistic prompt and save JPG

This is the preferred composition for “generate a prompt, draw it, and save it as JPG.”

```python
from pathlib import Path


concept = "a beautiful woman in an elegant cinematic portrait"
prompt_response = client.responses.create(
    model=qwen3_model,
    instructions=(
        "You are an art director. Return only one polished image-generation "
        "prompt of at most 500 characters describing subject, composition, "
        "lighting, color, and style."
    ),
    input=f"Create an image prompt for: {concept}",
)

prompt = prompt_response.output_text.strip()
image = generate_image(prompt)
output_path = Path("portrait.jpg")
image.convert("RGB").save(output_path, format="JPEG", quality=95)
print(output_path.resolve())
```

## Hosted Image Generation tool

Use this when the text model should decide when and how to generate the image within a Responses API call.

```python
import base64
import io

from PIL import Image


response = client.responses.create(
    model=qwen36_model,
    instructions="Act as an art director and use image generation.",
    input="Create an image representing happiness.",
    tools=[{"type": "image_generation", "size": "1024x1024"}],
)

generated_images: list[Image.Image] = []
for item in response.output:
    if item.type == "image_generation_call" and getattr(item, "result", None):
        image_bytes = base64.b64decode(item.result)
        generated_images.append(Image.open(io.BytesIO(image_bytes)))

for index, image in enumerate(generated_images, start=1):
    image.convert("RGB").save(f"generated_{index}.jpg", quality=95)
```

## Iterative prompt, generate, and evaluate loop

Use a multimodal Pydantic response to refine an image deterministically.

```python
import base64
import io

from PIL import Image
from pydantic import BaseModel, Field


class ImageEvaluation(BaseModel):
    fit: float = Field(ge=0, le=1)
    recommendations: str


def image_data_url(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def draw_concept(concept: str, max_iterations: int = 3) -> Image.Image:
    feedback = ""
    image: Image.Image | None = None

    for _ in range(max_iterations):
        prompt_response = client.responses.create(
            model=qwen3_model,
            instructions=(
                "Return only a polished image-generation prompt of at most "
                "500 characters."
            ),
            input=f"Concept: {concept}\nPrevious feedback: {feedback}",
        )
        prompt = prompt_response.output_text.strip()
        image = generate_image(prompt)

        evaluation = client.responses.parse(
            model=qwen36_model,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": f"Evaluate how well this depicts {concept}.",
                        },
                        {
                            "type": "input_image",
                            "image_url": image_data_url(image),
                            "detail": "auto",
                        },
                    ],
                }
            ],
            text_format=ImageEvaluation,
        ).output_parsed

        if evaluation.fit >= 0.9:
            return image
        feedback = evaluation.recommendations

    if image is None:
        raise RuntimeError("No image was generated")
    return image
```

## Sources

- `1-intro-ai-studio/CloudConnect.ipynb`
- `2-responses-api/Labs/AgenticImageGeneraton-Solution.ipynb`
- `5-other-int-tools/ImageGeneration.ipynb`
