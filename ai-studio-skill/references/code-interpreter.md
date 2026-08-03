# Code Interpreter

## Contents

- Automatic container
- Upload files and create an explicit container
- Run analysis and include outputs
- Inspect code and download artifacts
- Lifecycle and cleanup

Assume `client` comes from `responses.md` and `qwen3_model` from `models.md`.

Never execute model-generated Python locally with `exec`. Use the hosted Code Interpreter sandbox.

## Automatic container

```python
response = client.responses.create(
    model=qwen3_model,
    instructions="Use Python for every calculation.",
    input="Calculate the first 20 Fibonacci numbers and summarize the pattern.",
    tools=[
        {
            "type": "code_interpreter",
            "container": {"type": "auto"},
        }
    ],
)
print(response.output_text)
```

An automatic container is suitable when no state must be prepared before the request.

## Upload files and create an explicit container

```python
from pathlib import Path


source_path = Path("cities.xlsx")
with source_path.open("rb") as file_handle:
    uploaded_file = client.files.create(
        file=file_handle,
        purpose="assistants",
    )

container = client.containers.create(
    name="cities-analysis",
    expires_after={"anchor": "last_active_at", "minutes": 20},
    file_ids=[uploaded_file.id],
)

print("File:", uploaded_file.id)
print("Container:", container.id)
```

The model sees the uploaded file by its filename inside the container.

## Run analysis and include outputs

```python
response = client.responses.create(
    model=qwen3_model,
    instructions=(
        "Read cities.xlsx, calculate Density = Population / Area_km2, "
        "save cities_with_density.xlsx, create density.png, and attach both files."
    ),
    input="Analyze the city data.",
    include=["code_interpreter_call.outputs"],
    tools=[
        {
            "type": "code_interpreter",
            "container": container.id,
        }
    ],
)
print(response.output_text)
```

## Inspect code and download artifacts

Generated files appear as `container_file_citation` annotations. Download them with Files API.

```python
from pathlib import Path


def download_code_interpreter_files(
    response,
    download_dir: str | Path = "downloaded_files",
) -> list[Path]:
    download_dir = Path(download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []

    for item in response.output:
        if item.type == "code_interpreter_call":
            print("Container:", getattr(item, "container_id", None))
            print("Code:\n", item.code)
            for output in getattr(item, "outputs", None) or []:
                logs = getattr(output, "logs", "")
                if logs:
                    print(logs)

        elif item.type == "message":
            for content in item.content:
                for annotation in getattr(content, "annotations", None) or []:
                    if annotation.type != "container_file_citation":
                        continue
                    path = download_dir / Path(annotation.filename).name
                    file_content = client.files.content(annotation.file_id)
                    path.write_bytes(file_content.read())
                    downloaded.append(path)

    return downloaded


downloaded = download_code_interpreter_files(response)
for path in downloaded:
    print(path)
```

## Automatic container with uploaded files

When no explicit container reuse is needed, attach uploaded file IDs directly:

```python
response = client.responses.create(
    model=qwen3_model,
    input="Analyze the uploaded spreadsheet and create summary.xlsx.",
    include=["code_interpreter_call.outputs"],
    tools=[
        {
            "type": "code_interpreter",
            "container": {
                "type": "auto",
                "file_ids": [uploaded_file.id],
            },
        }
    ],
)
```

## Lifecycle and cleanup

- Explicit containers can live for at most 20 minutes after last activity in the course pattern.
- Download artifacts before the container expires.
- Delete source uploads owned by the program after the final request:

```python
client.files.delete(file_id=uploaded_file.id)
```

## Sources

- `5-other-int-tools/CodeInterpreter.ipynb`
- `5-other-int-tools/Labs/DataAnalysis-Solution.ipynb`
- Automatic `file_ids` form: official Yandex AI Studio Code Interpreter guide
