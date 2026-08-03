# Vision OCR and multimodal reading

## Contents

- Vision OCR REST request
- Extract full text and line geometry
- Multimodal Responses API alternative

Install `requests pillow python-dotenv openai`.

## Vision OCR REST request

Use Vision OCR when coordinates, blocks, lines, handwriting, tables, or mathematical layout matter.

```python
import base64
import io
import os

import requests
from dotenv import load_dotenv
from PIL import Image


load_dotenv()
api_key = os.getenv("api_key")
if not api_key:
    raise RuntimeError("Set api_key in .env or pass it explicitly")


def image_to_base64(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def recognize_text(
    image: Image.Image,
    api_key: str,
    model: str = "page",
    language_codes: list[str] | None = None,
) -> dict:
    response = requests.post(
        "https://ocr.api.cloud.yandex.net/ocr/v1/recognizeText",
        headers={"Authorization": f"Api-Key {api_key}"},
        json={
            "mimeType": "image/png",
            "languageCodes": language_codes or ["*"],
            "model": model,
            "content": image_to_base64(image),
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


image = Image.open("document.png")
result = recognize_text(image, api_key)
print(result["result"]["textAnnotation"]["fullText"])
```

Course model examples include `page`, `handwritten`, `table`, and `math-markdown`. Preserve the full JSON when downstream code needs bounding boxes.

## Extract lines and bounding boxes

```python
def extract_lines(ocr_result: dict) -> list[dict]:
    annotation = ocr_result["result"]["textAnnotation"]
    lines = []
    for block in annotation.get("blocks", []):
        for line in block.get("lines", []):
            text = " ".join(
                word.get("text", "") for word in line.get("words", [])
            ).strip()
            vertices = line.get("boundingBox", {}).get("vertices", [])
            lines.append({"text": text, "vertices": vertices})
    return lines
```

## Multimodal Responses API alternative

Use `qwen36_model` when the user needs semantic explanation rather than precise OCR geometry. Use the shared client setup from `responses.md` and the URI from `models.md`.

```python
import base64


with open("document.png", "rb") as file_handle:
    encoded = base64.b64encode(file_handle.read()).decode("ascii")

response = client.responses.create(
    model=qwen36_model,
    input=[
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": "Extract the text and explain the visual structure.",
                },
                {
                    "type": "input_image",
                    "image_url": f"data:image/png;base64,{encoded}",
                    "detail": "auto",
                },
            ],
        }
    ],
)
print(response.output_text)
```

## Sources

- `8-other-services/OCR.ipynb`
- `8-other-services/Labs/LectureRAG-Solution.ipynb`
