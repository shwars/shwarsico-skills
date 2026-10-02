# Shell tool and skills

## Contents

- Overview
- Upload a skill
- Attach a skill to a response
- SKILL.md format
- Versions and management
- Limits
- Security
- Cleanup

## Overview

The Shell tool (`tools[].type = "shell"`) is a built-in Responses API tool that gives the agent a container with a command-line environment. Use it when the agent must run operating-system commands, not only Python. For Python-only analysis, use the Code Interpreter from `code-interpreter.md` instead.

Skills are versioned, reusable file sets with an `SKILL.md` manifest that describe how to perform a repeatable process. Upload a skill through the Skills API, then attach it to the Shell tool environment. The model receives the skill name, description, and path in its context and decides whether to use it. There is no separate charge for skills: the content the model uses counts as model context and is billed by the selected model's rules.

Prerequisites: a service account with the `ai.assistants.editor` and `ai.languageModels.user` roles, and an API key with the `yc.ai.foundationModels.execute` scope. Use the shared `client` from `responses.md` and a skill-capable model such as `deepseek41_model` from `models.md`.

## Upload a skill

The skill directory must contain exactly one `SKILL.md` (the name is case-insensitive). Preserve the directory structure when uploading by passing paths relative to the skill directory's parent, so the top-level folder name is kept.

```python
from pathlib import Path


def skill_files(skill_dir: str | Path, root: str | Path | None = None):
    skill_dir = Path(skill_dir).resolve()
    root = Path(root).resolve() if root else skill_dir.parent
    files = []
    for path in skill_dir.rglob("*"):
        if path.is_file():
            files.append((path.relative_to(root).as_posix(), path.open("rb")))
    return files


skill = client.skills.create(files=skill_files("skills/libru-search"))
print(skill.id)
```

The returned skill object exposes `id` (for example `skill_abc123`), `name`, `description`, `default_version`, and `latest_version`.

Equivalent raw request with `curl`:

```bash
curl https://ai.api.cloud.yandex.net/v1/skills \
  --header "Authorization: Api-Key <API-key>" \
  --form "files=@./libru-search/SKILL.md;filename=libru-search/SKILL.md;type=text/markdown" \
  --form "files=@./libru-search/scripts/search_libru.py;filename=libru-search/scripts/search_libru.py;type=text/plain"
```

You can also upload a ZIP archive with a single top-level folder instead of individual files.

## Attach a skill to a response

Combine `shell` with `environment.type = "container_auto"` and a `skill_reference`:

```python
response = client.responses.create(
    model=deepseek41_model,
    instructions="You are a librarian with access to the Lib.ru catalog.",
    input="Build a character-mention frequency table for Anna Karenina.",
    tools=[
        {
            "type": "shell",
            "environment": {
                "type": "container_auto",
                "skills": [
                    {
                        "type": "skill_reference",
                        "skill_id": skill.id,
                    }
                ],
            },
        }
    ],
)
print(response.output_text)
```

`skill_reference` fields:

| Field | Required | Meaning |
| --- | --- | --- |
| `type` | Yes | Always `skill_reference`. |
| `skill_id` | Yes | Identifier returned by the Skills API. |
| `version` | No | Positive integer or `latest`. Defaults to the skill's `default_version`. |

To pin a version, add `"version": "2"` to the reference. If the model must use a skill deterministically, name it in the request or in the agent instructions: by default the model decides on its own from the skill name, description, and path.

## SKILL.md format

The manifest starts with YAML frontmatter containing `name` and `description`, followed by the instructions. Give the model the when-to-use rules, the files in the skill, and the exact command sequence.

````markdown
---
name: libru-search
description: Find books and authors in Maxim Moshkov's Lib.ru library and download texts for local analysis.
---

Work in a Unix environment. Resolve this skill's directory as `SKILL_DIR`.
The reusable commands live in `scripts/` below it.

## Find Russian classics

```sh
python3 "$SKILL_DIR/scripts/search_azlib.py" "title fragment" --limit 10
```
````

`SKILL.md` instructions are treated as user instructions, not as a system prompt, so do not rely on them to override safety policy.

## Versions and management

```python
client.skills.list()
client.skills.retrieve(skill.id)
client.skills.update(skill.id, default_version="2")
client.skills.versions.create(skill.id, files=skill_files("skills/libru-search"))
client.skills.versions.list(skill.id)
client.skills.versions.delete("1", skill_id=skill.id)
client.skills.content.retrieve(skill.id)
```

Each upload creates an immutable new version. `default_version` is used when `skill_reference` omits `version`; `latest_version` is the most recent upload. You cannot delete the default version until you point `default_version` at another one. Deleting the last remaining version deletes the skill, and deleting a skill removes all of its versions.

## Limits

- Exactly one `SKILL.md` per skill.
- ZIP archive up to 50 MB.
- Up to 500 files per skill version.
- Up to 25 MB per unpacked file.

## Security

- Review skill contents before attaching them. A skill can influence the model's planning, tool use, and command execution in the Shell tool container.
- Do not let end users freely select and attach arbitrary skills from an open list.
- For high-impact or mutating actions, require explicit confirmation and additional policy checks.
- Never run model-generated shell commands locally with `subprocess` or `os.system`; execute them in the hosted Shell tool container.

## Cleanup

Delete skills the program owns after the final request when they are no longer needed:

```python
client.skills.delete(skill.id)
```

## Sources

- Official Shell tool documentation: https://aistudio.yandex.ru/ru/docs/ai-studio/concepts/agents/tools/shell-tool
- Official skills documentation: https://aistudio.yandex.ru/ru/docs/ai-studio/concepts/agents/skills
- Step-by-step example: https://aistudio.yandex.ru/ru/docs/ai-studio/operations/agents/use-skill
- Notebook: `building-data-agent/notebooks/AIStudio_Demo.ipynb`, section "Shell Tool и Навыки (Skills)"
