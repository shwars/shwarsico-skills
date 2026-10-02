---
name: ipynb
description: Use this skill when an agent needs to inspect, search, extract, create, or safely edit Jupyter .ipynb notebook files without manually reading or modifying raw notebook JSON.
---

# IPYNB Notebook Toolkit

Use `ipynb-tool` instead of opening or editing raw `.ipynb` JSON. It provides compact notebook views, targeted cell edits, and a Python percent-format workflow for larger changes.

Run commands from this skill directory with `uv`:

```bash
uv run ipynb-tool --summary --toc notebook.ipynb
```

## Inspect a Notebook

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

5. Show stable cell IDs before edits that may shift indexes:

```bash
uv run ipynb-tool --cell-ids notebook.ipynb
```

6. Extract images only when visual outputs matter:

```bash
uv run ipynb-tool --images files --image-dir extracted notebook.ipynb
```

## Make a Small Edit

Editing commands preview changes unless `--write` is present. Inspect the preview, then rerun the same command with `--write`.

```bash
uv run ipynb-tool replace-cell notebook.ipynb id:setup --source-file setup.py
uv run ipynb-tool replace-cell notebook.ipynb id:setup --source-file setup.py --write

uv run ipynb-tool insert-cell notebook.ipynb --type markdown --after 3 --source-file note.md
uv run ipynb-tool delete-cells notebook.ipynb --cells 5,8-9
uv run ipynb-tool move-cells notebook.ipynb --cells 4-6 --before id:results
```

`replace-cell` and `insert-cell` accept either `--source-file PATH` or `--stdin`. Cell selectors are 1-based indexes or `id:<cell-id>`. Changed code always loses its stale outputs and execution count; unchanged and moved cells preserve them.

## Make a Large Edit or Create a Notebook

Export a transient Jupytext-compatible Python percent file, edit it as normal text, then import it. The exported file is not a persistent notebook pairing.

```bash
uv run ipynb-tool export-percent notebook.ipynb --output notebook.edit.py
uv run ipynb-tool import-percent notebook.edit.py notebook.ipynb
uv run ipynb-tool import-percent notebook.edit.py notebook.ipynb --write
```

Import verifies that the target has not changed since export. Removing existing cell markers is treated as deletion and requires `--allow-delete`. New percent files can create Python 3 notebooks:

```bash
uv run ipynb-tool import-percent lesson.py lesson.ipynb
uv run ipynb-tool import-percent lesson.py lesson.ipynb --write
```

## Inspection Switches

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
- `--cell-ids`: list each selected cell's index, type, and stable ID.
- `--images skip|base64|files`: skip image outputs, preserve data URIs, or save images as files. Default is `skip`.
- `--image-dir DIR`: directory for files written by `--images files`.

If no content selector is provided, the tool prints nothing unless an exploration switch such as `--summary`, `--toc`, `--search`, or `--errors` is used. `--images files` by itself extracts images and prints nothing.

Do not use the editing commands to execute notebooks or directly manipulate output MIME bundles or metadata. Use notebook execution tooling separately after source edits when fresh outputs are required.
