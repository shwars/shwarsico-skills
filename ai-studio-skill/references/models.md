# Supported models

Use this catalog whenever selecting a Yandex AI Studio model. It covers the current common-instance generative models documented on August 3, 2026. Recheck the official catalog before long-lived production deployments because model lifecycle dates and availability can change.

## URI variables

Assume `folder_id` comes from the shared setup in `responses.md`. Keep the chosen variable name in assembled code so the model family remains obvious.

```python
alice_model = f"gpt://{folder_id}/aliceai-llm"
alice_flash_model = f"gpt://{folder_id}/aliceai-llm-flash"
yandexgpt51_model = f"gpt://{folder_id}/yandexgpt-5.1"
yandexgpt5_model = f"gpt://{folder_id}/yandexgpt-5-pro"
yandexgpt_lite_model = f"gpt://{folder_id}/yandexgpt-5-lite"
deepseek_model = f"gpt://{folder_id}/deepseek-v4-flash"
qwen3_model = f"gpt://{folder_id}/qwen3-235b-a22b-fp8"
qwen36_model = f"gpt://{folder_id}/qwen3.6-35b-a3b"
gpt_oss_120b_model = f"gpt://{folder_id}/gpt-oss-120b"
gpt_oss_20b_model = f"gpt://{folder_id}/gpt-oss-20b"
alice_art_model = f"art://{folder_id}/aliceai-image-art-3.0"
yandex_art_model = f"art://{folder_id}/yandex-art-2.0"
speech_realtime_model = f"gpt://{folder_id}/speech-realtime-260528"
speech_realtime_legacy_model = f"gpt://{folder_id}/speech-realtime-250923"
```

Do not add `/latest` to these fixed common-instance URIs. A major model update receives a different URI rather than silently switching versions.

## Common-instance catalog

| Model | Variable and exact URI suffix | Context or prompt limit | Supported API | Image input | Lifecycle |
| --- | --- | ---: | --- | --- | --- |
| Alice AI LLM | `alice_model` — `aliceai-llm` | 128k (131,072 tokens) | Text Generation; OpenAI-compatible | No | Current |
| Alice AI LLM Flash | `alice_flash_model` — `aliceai-llm-flash` | 64k (65,536 tokens) | OpenAI-compatible | No | Current |
| YandexGPT Pro 5.1 | `yandexgpt51_model` — `yandexgpt-5.1` | 32k (32,768 tokens) | Text Generation; OpenAI-compatible | No | Current; prefer this explicit URI over the legacy `yandexgpt/rc` alias |
| YandexGPT Pro 5 | `yandexgpt5_model` — `yandexgpt-5-pro` | 32k (32,768 tokens) | Text Generation; OpenAI-compatible | No | Current; prefer this explicit URI over the legacy `yandexgpt/latest` alias |
| YandexGPT Lite 5 | `yandexgpt_lite_model` — `yandexgpt-5-lite` | 32k (32,768 tokens) | Text Generation; OpenAI-compatible | No | Current |
| DeepSeek V4 Flash | `deepseek_model` — `deepseek-v4-flash` | 1M (1,048,576 tokens) | OpenAI-compatible | No | Current; replaced DeepSeek V3.2 |
| Qwen3 235B | `qwen3_model` — `qwen3-235b-a22b-fp8` | 256k (262,144 tokens) | OpenAI-compatible | No | Current |
| gpt-oss-120b | `gpt_oss_120b_model` — `gpt-oss-120b` | 128k (131,072 tokens) | OpenAI-compatible | No | Current |
| gpt-oss-20b | `gpt_oss_20b_model` — `gpt-oss-20b` | 128k (131,072 tokens) | OpenAI-compatible | No | Current |
| Qwen3.6 35B | `qwen36_model` — `qwen3.6-35b-a3b` | 256k (262,144 tokens) | OpenAI-compatible | **Yes** — Base64 images | Current; only model in this catalog documented for image input |
| Alice AI ART | `alice_art_model` — `aliceai-image-art-3.0` | 500-character prompt | Images API | No — text-to-image generation only | Current; preferred for new direct Images API code |
| YandexART 2.0 | `yandex_art_model` — `yandex-art-2.0` | 500-character prompt | Image generation APIs | No — text-to-image generation only | Scheduled for retirement on August 18, 2026 |
| Speech Realtime 260528 | `speech_realtime_model` — `speech-realtime-260528` | 64k (65,536 tokens) | Realtime API | No documented image input | Current; preferred realtime speech model |
| Speech Realtime 250923 | `speech_realtime_legacy_model` — `speech-realtime-250923` | 32k (32,768 tokens) | Realtime API | No documented image input | Older realtime speech version |

Fine-tuned YandexGPT Lite is a separate non-fixed entry: `gpt://{folder_id}/yandexgpt-lite/latest@<suffix>`, with a 32k (32,768-token) context through Text Generation and OpenAI-compatible APIs. Use the exact suffix returned by the tuning operation; do not invent one.

## Selection rules

- Use `qwen3_model` for general Responses API examples, tools, RAG, and Code Interpreter unless the user selects another family.
- Use `deepseek_model` when the input can exceed 256k tokens; it is the catalog option for a request around 500k tokens.
- Use `qwen36_model` whenever the request contains image input, including semantic OCR and image evaluation.
- Use `alice_art_model` for new direct Images API generation. Use `yandex_art_model` only when explicitly requested or maintaining existing code, and mention its retirement date.
- Use `alice_model`, `alice_flash_model`, or a YandexGPT variable when the user names that family. Alice AI LLM is suited to complex dialog and RAG; Alice AI LLM Flash is the lightweight choice.
- Use the Speech Realtime variables only with the Realtime API, not the Responses API.
- The hosted `image_generation` Responses tool is selected as a tool; its underlying generator is not passed as the parent response model.

For example, a large-context request should retain the explicit choice:

```python
response = client.responses.create(
    model=deepseek_model,
    input=large_document,
)
print(response.output_text)
```

## Sources

- Official Yandex AI Studio common-instance model list: https://aistudio.yandex.ru/docs/en/ai-studio/concepts/generation/models.html
- Official multimodal Responses API guide: https://aistudio.yandex.ru/docs/en/ai-studio/operations/generation/multimodels-request-responses.html
- Official release notes for replacements and recent additions: https://aistudio.yandex.ru/docs/en/ai-studio/release-notes/
