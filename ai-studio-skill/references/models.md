# Supported models

Use this catalog whenever selecting a Yandex AI Studio base-instance model. It covers the current base-instance generative models documented on October 3, 2026. Recheck the official catalog before long-lived production deployments because model lifecycle dates and availability can change.

## URI variables

Assume `folder_id` comes from the shared setup in `responses.md`. Keep the chosen variable name in assembled code so the model family remains obvious.

```python
alice_model = f"gpt://{folder_id}/aliceai-llm"
alice_flash_model = f"gpt://{folder_id}/aliceai-llm-flash"
yandexgpt51_model = f"gpt://{folder_id}/yandexgpt-5.1"
yandexgpt5_model = f"gpt://{folder_id}/yandexgpt-5-pro"
yandexgpt_lite_model = f"gpt://{folder_id}/yandexgpt-5-lite"
deepseek_model = f"gpt://{folder_id}/deepseek-v4-flash"
deepseek41_model = f"gpt://{folder_id}/deepseek-v4.1-flash"
qwen36_model = f"gpt://{folder_id}/qwen3.6-35b-a3b"
alice_art_model = f"art://{folder_id}/aliceai-image-art-3.0"
speech_realtime_deepseek_model = f"gpt://{folder_id}/speech-realtime-deepseek-v4-flash"
speech_realtime_max_tts_model = f"gpt://{folder_id}/speech-realtime-max-tts-live/latest"
speech_tts_live_model = f"gpt://{folder_id}/speech-realtime-tts-live/latest"
```

Do not add `/latest` to the fixed common-instance URIs, except for the two Realtime TTS entries that are documented with it. A major model update receives a different URI rather than silently switching versions.

## Base-instance catalog

| Model | Variable and exact URI suffix | Context or prompt limit | Supported API | Image input | Lifecycle |
| --- | --- | ---: | --- | --- | --- |
| Alice AI LLM | `alice_model` — `aliceai-llm` | 128k (131,072 tokens) | Text Generation; OpenAI-compatible | No | Current |
| Alice AI LLM Flash | `alice_flash_model` — `aliceai-llm-flash` | 64k (65,536 tokens) | OpenAI-compatible | No | Current |
| YandexGPT Pro 5.1 | `yandexgpt51_model` — `yandexgpt-5.1` | 32k (32,768 tokens) | Text Generation; OpenAI-compatible | No | Current; prefer this explicit URI over the legacy `yandexgpt/rc` alias |
| YandexGPT Pro 5 | `yandexgpt5_model` — `yandexgpt-5-pro` | 32k (32,768 tokens) | Text Generation; OpenAI-compatible | No | Current; superseded by 5.1 |
| YandexGPT Lite 5 | `yandexgpt_lite_model` — `yandexgpt-5-lite` | 32k (32,768 tokens) | Text Generation; OpenAI-compatible | No | Current |
| DeepSeek V4 Flash | `deepseek_model` — `deepseek-v4-flash` | 1M (1,048,576 tokens) | OpenAI-compatible | No | Current |
| DeepSeek-V4.1-Flash | `deepseek41_model` — `deepseek-v4.1-flash` | 1M (1,048,576 tokens) | OpenAI-compatible | **Yes** — Base64 images | Current; preferred general model |
| Qwen3.6 35B | `qwen36_model` — `qwen3.6-35b-a3b` | 256k (262,144 tokens) | OpenAI-compatible | **Yes** — Base64 images | Current |
| Alice AI ART | `alice_art_model` — `aliceai-image-art-3.0` | 500-character prompt | Images API | No — text-to-image generation only | Current; preferred for new direct Images API code |
| Speech Realtime DeepSeek V4 Flash | `speech_realtime_deepseek_model` — `speech-realtime-deepseek-v4-flash` | 1M (1,048,576 tokens) | Realtime API | No documented image input | Current; experimental, may answer slower than other Realtime models |
| Speech Realtime Max TTS Live | `speech_realtime_max_tts_model` — `speech-realtime-max-tts-live/latest` | 1M (1,048,576 tokens), output up to 393,216 tokens | Realtime API | No documented image input | Current; uses LiveTTS voices |
| Speech TTS Live | `speech_tts_live_model` — `speech-realtime-tts-live/latest` | Not applicable | Realtime API | No | Current; text-to-speech only, no LLM or audio input |

Fine-tuned YandexGPT Lite is a separate non-fixed entry: `gpt://{folder_id}/yandexgpt-lite/latest@<suffix>`, with a 32k (32,768-token) context through Text Generation and OpenAI-compatible APIs. Use the exact suffix returned by the tuning operation; do not invent one.

## Retired and retiring models

Do not select these for new code. Use a current model from the catalog above instead.

| Model | URI suffix | Lifecycle |
| --- | --- | --- |
| Qwen3 235B | `qwen3-235b-a22b-fp8` | Available until September 30, 2026 |
| gpt-oss-120b | `gpt-oss-120b` | Available until October 30, 2026 |
| gpt-oss-20b | `gpt-oss-20b` | Available until October 30, 2026 |
| Speech Realtime 260528 | `speech-realtime-260528` | Disabled October 12, 2026 |
| Speech Realtime 250923 | `speech-realtime-250923` | Disabled October 12, 2026 |
| YandexART 2.0 | `yandex-art-2.0` | Retired August 18, 2026 |

## Selection rules

- Use `deepseek41_model` for general Responses API examples, tools, RAG, and Code Interpreter unless the user selects another family.
- Use `qwen36_model` or `deepseek41_model` whenever the request contains image input, including semantic OCR and image evaluation. Both are vision models that accept Base64 images.
- Use `deepseek_model` when a non-reasoning 1M-context option is preferred over `deepseek41_model`.
- Use `alice_art_model` for new direct Images API generation.
- Use `alice_model`, `alice_flash_model`, or a YandexGPT variable when the user names that family. Alice AI LLM is suited to complex dialog and RAG; Alice AI LLM Flash is the lightweight choice.
- Use the Speech Realtime variables only with the Realtime API, not the Responses API.
- The hosted `image_generation` Responses tool is selected as a tool; its underlying generator is not passed as the parent response model.

For example, a general request should retain the explicit choice:

```python
response = client.responses.create(
    model=deepseek41_model,
    input="Summarize the key points of this document.",
)
print(response.output_text)
```

## Sources

- Official Yandex AI Studio base-instance model list: https://aistudio.yandex.ru/ru/docs/ai-studio/concepts/generation/models
- Official multimodal Responses API guide: https://aistudio.yandex.ru/ru/docs/ai-studio/operations/generation/multimodels-request-responses
- Official release notes for replacements and recent additions: https://aistudio.yandex.ru/ru/docs/ai-studio/release-notes/
