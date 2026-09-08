---
name: mindmap-js-skill
description: Convert text into mindmaps, edit existing Markmap Markdown, and render interactive HTML previews using Markmap.js. Use for mindmap or Markmap requests, including optional PNG/SVG export through the agent's browser tools; not for general flowcharts or document extraction.
---

# Markmap mindmaps

Produce an editable Markdown hierarchy and an interactive HTML preview. Keep document extraction with the coding agent: obtain the text using available tools, then apply this skill. Do not require a particular document reader, browser integration, or external AI service.

## Choose the map

Before each new map, ask together for any choices the request has not specified:

- **Detail:** concise summary or detailed coverage.
- **HTML assets:** offline (larger HTML with embedded rendering libraries) or CDN (smaller HTML requiring internet to view).
- **Appearance:** readable Markmap defaults or custom styling. If custom, collect the desired palette, font, background, or other relevant preferences.

Wait for those choices before converting or rendering. Honor explicit choices without asking again. Reuse answers during revisions of the same map; for a new map, ask for unspecified choices unless the user established standing preferences. When the user explicitly delegates the choices, use concise coverage, offline assets, and readable defaults.

For existing Markmap Markdown, preserve the hierarchy, wording, and style unless changes are requested. A faithful render does not require choosing a new summary level; existing styling counts as a specified appearance.

## Organize and render

1. Read the [mapping and rendering reference](references/mindmaps.md) for content organization, the readable style preset, or export guidance as applicable.
2. Convert prose into a hierarchy of short labels. Preserve the source language, meaning, key qualifications, and supplied links. Do not add unsupported facts or turn tentative statements into certainties. Use headings and nested lists, without fixed depth or branch-count requirements.
3. Save UTF-8 Markdown beside its HTML in the user's requested output location, otherwise the current task workspace. Choose a descriptive shared basename. Resolve paths before changing working directory; keep the input document intact.
4. Use Node.js 20+ and npm. If dependencies are absent, run `npm ci --ignore-scripts --no-audit --no-fund` from this skill's directory. No global installation is needed. Offline output can still require network access during dependency installation and asset embedding.
5. Run the bundled helper, using absolute input/output paths when invoking it from another directory:

   ```text
   node scripts/render.mjs input.md --output output.html --assets offline
   node scripts/render.mjs input.md --output output.html --assets cdn
   ```

   Paths in these examples are relative to the command's working directory. The helper generates HTML without opening a browser. For custom fonts/backgrounds, supply a local stylesheet with `--style style.css`; it is embedded in the HTML. Markmap layout/colors belong in the Markdown frontmatter.
6. Open the generated HTML with the agent's available browser or preview tool. If that tool requires HTTP, use a local loopback server. Inspect label wrapping, clipping, and the map's fit; correct visible problems before delivering. If preview tools are unavailable, provide the file and explain that it can be opened in a browser; do not claim visual verification.
7. Deliver links to both Markdown and HTML. For PNG/SVG requests, follow the reference using the agent's available browser tools. No browser or static-export implementation is bundled.

## Revisions and boundaries

Edit the saved Markdown as the source of truth and regenerate HTML in the same asset mode. Preserve unrelated branches and the agreed appearance. Styling supplied separately remains in its CSS source file for repeatable regeneration.

Offline mode embeds rendering libraries, not every resource referenced by the content. External images, fonts, and stylesheet URLs need separate handling before claiming complete offline portability. Do not upload the user's text to the Markmap website or publish/host output as part of this local workflow.
