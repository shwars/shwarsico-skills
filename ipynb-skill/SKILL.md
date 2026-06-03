---
name: ipynb
description: Use this skill when an agent needs to read, inspect, summarize, search, or extract code, markdown, outputs, errors, or images from Jupyter .ipynb notebook files without manually reading raw notebook JSON.
---

# IPYNB Notebook Exploration

Use `ipynb-tool` before opening raw `.ipynb` JSON. It produces compact, agent-readable notebook views and can extract images from outputs.

Run commands from this skill directory with `uv`:

```bash
uv run ipynb-tool --summary --toc notebook.ipynb
```

## Recommended Workflow

1. Start with a cheap map:

```bash
uv run ipynb-tool --summary --toc notebook.ipynb
```

2. Narrow to relevant regions:

```bash
uv run ipynb-tool --search "train|model|error" --around 1 notebook.ipynb
uv run ipynb-tool --cells 4,8-12 --all notebook.ipynb
uv run ipynb-tool --errors notebook.ipynb
```

3. Read executable context:

```bash
uv run ipynb-tool --code notebook.ipynb
uv run ipynb-tool --code --markdown --comments --noxml notebook.ipynb
```

4. Use XML when structure matters:

```bash
uv run ipynb-tool --xml --all --cells 8-12 notebook.ipynb
```

5. Extract images only when visual outputs matter:

```bash
uv run ipynb-tool --images files --image-dir extracted notebook.ipynb
```

## Important Switches

- `--code`, `--markdown`, `--output`, `--all`: choose content to print. `--all` includes code, markdown, and outputs.
- `--xml` / `--noxml`: XML formatting or plain content. `--code` alone defaults to plain code.
- `--comments`: in plain mode, emit markdown and outputs as Python comments so the result remains readable beside code.
- `--summary`: show notebook metadata, cell counts, output counts, image counts, error counts, and execution range.
- `--toc`: show markdown headings with cell numbers.
- `--cells 1,3,8-12`: restrict inspection to 1-based cell indexes.
- `--search PATTERN` and `--around N`: print matching cells and optional neighboring context.
- `--errors`: focus on code cells with error outputs and tracebacks.
- `--max-chars N` / `--no-truncate`: control truncation of long sources and outputs.
- `--metadata`: include notebook and cell metadata.
- `--execution`: include execution counts and warn when code cells appear run out of order.
- `--images skip|base64|files`: skip image outputs, preserve data URIs, or save images as files. Default is `skip`.
- `--image-dir DIR`: directory for files written by `--images files`.

If no content selector is provided, the tool prints nothing unless an exploration switch such as `--summary`, `--toc`, `--search`, or `--errors` is used. `--images files` by itself extracts images and prints nothing.
