# Files, vector stores, and RAG

## Contents

- Upload and index files
- Direct semantic search
- RAG with `file_search`
- Inspect citations
- Add in-memory content
- Cleanup

Assume `client` comes from `responses.md` and `qwen3_model` from `models.md`.

## Upload and index files

```python
from pathlib import Path


paths = [Path("paper.pdf"), Path("notes.txt")]
uploaded_files = []

for path in paths:
    with path.open("rb") as file_handle:
        uploaded = client.files.create(file=file_handle, purpose="assistants")
    uploaded_files.append(uploaded)

vector_store = client.vector_stores.create(name="knowledge_base")

for uploaded in uploaded_files:
    client.vector_stores.files.create_and_poll(
        vector_store_id=vector_store.id,
        file_id=uploaded.id,
        chunking_strategy={
            "type": "static",
            "static": {
                "max_chunk_size_tokens": 800,
                "chunk_overlap_tokens": 100,
            },
        },
    )

print("Vector store:", vector_store.id)
```

Use `create_and_poll` when the next line queries the index. For bulk workflows, submit files first and poll their states separately.

## Direct semantic search

```python
results = client.vector_stores.search(
    vector_store_id=vector_store.id,
    query="What is the attention mechanism?",
    rewrite_query=True,
)

for result in results.data[:3]:
    text = result.content[0].text if result.content else ""
    print(result.filename, result.score, text[:200])
```

## RAG with `file_search`

```python
file_search = {
    "type": "file_search",
    "vector_store_ids": [vector_store.id],
    "max_num_results": 5,
}

response = client.responses.create(
    model=qwen3_model,
    instructions=(
        "Answer from the indexed files, name the sources, and say when the "
        "answer is not present in the knowledge base."
    ),
    input="Explain the attention mechanism.",
    tools=[file_search],
)
print(response.output_text)
```

## Inspect citations

Tool results and answer annotations provide complementary provenance.

```python
for item in response.output:
    if item.type == "file_search_call":
        for result in item.results or []:
            print("Retrieved:", result.filename)
    elif item.type == "message":
        for content in item.content:
            for annotation in getattr(content, "annotations", None) or []:
                if getattr(annotation, "type", None) == "file_citation":
                    print("Cited:", annotation.filename, annotation.file_id)
```

Do not assume fixed positions such as `response.output[0]`; inspect item types.

## Add in-memory content

```python
from io import BytesIO


def add_text(vector_store_id: str, text: str, filename: str = "note.txt") -> str:
    data = BytesIO(text.encode("utf-8"))
    uploaded = client.files.create(
        file=(filename, data),
        purpose="assistants",
    )
    client.vector_stores.files.create_and_poll(
        vector_store_id=vector_store_id,
        file_id=uploaded.id,
    )
    return uploaded.id


note_file_id = add_text(vector_store.id, "Attention assigns weights to tokens.")
```

## Cleanup

Delete only resources created by the current program. Put cleanup in `finally` when failure should not leak resources.

```python
client.vector_stores.delete(vector_store_id=vector_store.id)

for uploaded in uploaded_files:
    client.files.delete(file_id=uploaded.id)

client.files.delete(file_id=note_file_id)
```

## Sources

- `4-rag-search/FileSearch.ipynb`
- `4-rag-search/Labs/OpenAlexLab-Solution.ipynb`
- `8-other-services/Labs/LectureRAG-Solution.ipynb`
