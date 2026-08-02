# SpeechKit

## Contents

- SDK setup
- Short text-to-speech
- Short speech-to-text
- Long recognition with speaker labels
- Long-text synthesis

Install `yandex-ai-studio-sdk python-dotenv`. SpeechKit uses the native AI Studio SDK, while LLM calls should continue to use the OpenAI-compatible client.

## SDK setup

```python
import os

from dotenv import load_dotenv
from yandex_ai_studio_sdk import AIStudio


def create_sdk(
    folder_id: str | None = None,
    api_key: str | None = None,
) -> AIStudio:
    load_dotenv()
    folder_id = folder_id or os.getenv("folder_id")
    api_key = api_key or os.getenv("api_key")
    if not folder_id or not api_key:
        raise RuntimeError("Set folder_id and api_key in .env or pass them explicitly")
    return AIStudio(folder_id=folder_id, auth=api_key)


sdk = create_sdk()
```

## Short text-to-speech

```python
from pathlib import Path


def synthesize_wav(
    text: str,
    output_path: str | Path,
    voice: str = "jane",
    speed: float = 1.0,
) -> Path:
    output_path = Path(output_path)
    tts = sdk.speechkit.text_to_speech(voice=voice, audio_format="WAV")
    result = tts.configure(speed=speed).run(text)
    output_path.write_bytes(result.data)
    return output_path


path = synthesize_wav("Привет, мир!", "hello.wav")
print(path.resolve())
```

## Short speech-to-text

```python
from pathlib import Path


def recognize_short_wav(path: str | Path, punctuation: bool = True) -> str:
    stt = sdk.speechkit.speech_to_text(
        audio_format="WAV",
        text_normalization=True,
    )
    if punctuation:
        normalization = stt.TextNormalization(literature_text=True)
        stt = stt.configure(text_normalization=normalization)
    result = stt.run(Path(path).read_bytes())
    return result.text


print(recognize_short_wav("hello.wav"))
```

## Long recognition with speaker labels

```python
from pathlib import Path


def recognize_long_mp3(path: str | Path, language: str = "ru-RU"):
    stt = sdk.speechkit.speech_to_text(
        audio_format="MP3",
        language_codes=language,
        speaker_labeling=True,
    )
    operation = stt.run_deferred(Path(path).read_bytes())
    return operation.wait()


def extract_speaker_turns(result) -> list[dict]:
    turns = []
    for channel in result:
        for utterance in channel.utterances:
            turns.append(
                {
                    "speaker": channel.tag,
                    "start_time_ms": utterance.timespan.start_time_ms,
                    "text": utterance.text,
                }
            )
    return sorted(turns, key=lambda item: item["start_time_ms"])


result = recognize_long_mp3("podcast.mp3")
for turn in extract_speaker_turns(result):
    print(turn)
```

## Long-text synthesis

SpeechKit requests have practical text limits. Split long text into sentence-sized chunks, synthesize each chunk, then join WAV audio. This example needs `pydub`.

```python
import io

from pydub import AudioSegment


def split_text(text: str, max_chars: int = 900):
    sentences = [part.strip() for part in text.split(".") if part.strip()]
    chunk = ""
    for sentence in sentences:
        candidate = f"{chunk}. {sentence}".strip(". ")
        if chunk and len(candidate) > max_chars:
            yield chunk + "."
            chunk = sentence
        else:
            chunk = candidate
    if chunk:
        yield chunk + "."


def synthesize_long_text(text: str, output_path: str, voice: str = "jane") -> None:
    tts = sdk.speechkit.text_to_speech(voice=voice, audio_format="WAV")
    combined = AudioSegment.empty()
    for chunk in split_text(text):
        result = tts.run(chunk)
        combined += AudioSegment.from_wav(io.BytesIO(result.data))
    combined.export(output_path, format="wav")
```

## Sources

- `8-other-services/SpeechKit.ipynb`
- `8-other-services/LongSpeech.ipynb`
