---
name: ai-studio
description: Build clean Python applications with Yandex AI Studio through the OpenAI-compatible Responses API and related Yandex services. Use for Yandex AI Studio client setup, text or multimodal responses, conversations, streaming, Pydantic structured output, function/web/file search tools, RAG and vector stores, external MCP servers, Code Interpreter containers and files, image generation, Vision OCR, SpeechKit, or explicit OpenAI Agents SDK integration.
---

# Yandex AI Studio application development

Build the smallest complete program that satisfies the request. Read only the references needed for the requested features.

## Assemble code

1. Read [responses.md](references/responses.md) for authentication and client setup. Reuse one client throughout the program.
2. Read the feature references selected from the catalog below.
3. Combine imports, configuration, helpers, and the requested operation into one clean script. Remove duplicated setup.
4. Accept `folder_id` and `api_key` as optional function arguments; otherwise load lowercase `folder_id` and `api_key` from `.env` in the current directory.
5. Keep model URIs as named, easily overridden variables. Default to:
   - Text and tools: `gpt://{folder_id}/qwen3-235b-a22b-fp8/latest`
   - Vision: `gpt://{folder_id}/qwen3.6-35b-a3b/latest`
   - Images: `art://{folder_id}/aliceai-image-art-3.0/latest`
6. Use `base_url="https://ai.api.cloud.yandex.net/v1"` and pass `project=folder_id` to OpenAI clients.
7. Return or save artifacts using normal Python APIs. Do not emit notebook magics, notebook display helpers, placeholder download URLs, embedded credentials, or imports from the course repository.
8. Include cleanup for uploaded files and vector stores when the generated program owns their lifecycle. Explain that Code Interpreter containers expire after inactivity.

## Reference catalog

- Basic request, conversation, Pydantic output, streaming, or multimodal input: [responses.md](references/responses.md)
- Local function calling, web search, hosted MCP, approvals, or tool inspection: [tools.md](references/tools.md)
- File upload, vector stores, semantic search, RAG, citations, or cleanup: [files-rag.md](references/files-rag.md)
- Code Interpreter, sandbox file upload, logs, or artifact download: [code-interpreter.md](references/code-interpreter.md)
- Direct Images API, PIL conversion, JPG output, hosted image tool, or iterative drawing: [images.md](references/images.md)
- Speech synthesis, short/long recognition, speaker labeling, or long synthesis: [speechkit.md](references/speechkit.md)
- Vision OCR or using a multimodal model as an OCR alternative: [ocr.md](references/ocr.md)
- OpenAI Agents SDK: [agents-sdk.md](references/agents-sdk.md), but load it only when the user explicitly says `OpenAI Agents SDK`, `Agents SDK`, `Runner`, `handoff`, or `multi-agent`. An ordinary request for an “agent” should use Responses API tools instead.

## Quality rules

- Prefer direct Responses API calls over introducing a reusable agent abstraction.
- Use `client.images.generate`; do not invent a create-style Images API method.
- Decode image `b64_json` into `PIL.Image.Image`; convert to RGB before saving JPEG.
- Use `client.responses.parse(..., text_format=Model)` for Pydantic structured output.
- Preserve `response.id` and pass it as `previous_response_id` for continuation.
- Treat MCP servers configured with `require_approval="never"` as trusted. Otherwise surface or explicitly process approval requests.
- Use `create_and_poll` when code must wait for vector indexing before querying.
- Never run model-generated code locally with `exec`; use the hosted Code Interpreter for untrusted or generated code.

The examples are distilled from all notebooks in `D:\GIT\ai-studio-course`, preferring completed solution notebooks and removing incomplete lab cells, duplicated teaching scaffolds, and notebook-only UI code.
