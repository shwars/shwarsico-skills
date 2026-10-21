---
name: pdf-web-publisher
description: Publish PDF files as compressed, image-only slide archives for offline browsing and static web hosting. Create or extend a shared presentation gallery with selectable themes, without distributing source PDFs. Use for PDF-to-web publishing; not for PPTX conversion, hosting uploads, or document editing.
---

# PDF Web Publisher

Turn each PDF page into a compressed slide image and build a portable archive.
Use the bundled publisher and player rather than rebuilding the viewer for each
deck. The finished archive needs only a browser, including through `file://`.

## Publish

Resolve this skill's absolute directory and the input PDF before running commands.
Use `uv run` with the bundled script; it declares its own Python dependencies.

```text
uv run /skill/scripts/publish.py publish /input/talk.pdf --title "Talk title"
uv run /skill/scripts/publish.py publish /input/talk.pdf --output /website --slug deck-one --title "Talk title" --speaker "Speaker" --event "Conference" --date 2026-10-20 --tag AI
uv run /skill/scripts/publish.py validate --output /website
```

`--output` names the **parent** directory: `/website` produces
`/website/presentations/`. Without it, use `./presentations/` under the current
working directory. All generated code and assets stay inside that folder.
The source PDF must be outside the destination archive.

- Accept PDF only. Ask for an exported PDF when given PPTX. Do not silently
  introduce an Office converter or upload a document to an external service.
- Title defaults to PDF title metadata, then the filename. Use an explicit title
  if the metadata is unsuitable. Page 1 supplies the cover unless overridden.
- Default images: lossy WebP, 1440 px maximum long edge, quality 55. Override with
  `--max-edge` and `--quality` when the user needs a different tradeoff. Inspect
  a dense slide before claiming that fine text is readable.
- Optional archive metadata: speaker, event, date, description, and repeated
  `--tag` values. Publish successfully with title and cover alone.
- Existing slugs require `--replace`. Compatible player files are reused without
  modification. Use `--refresh-player` only when replacing the shared bundled
  player is intended; it replaces its managed files, including customized CSS.
- Unmanaged conflicting entrypoints cause an error. Preserve unrelated files.

## Gallery and appearance

The archive has one shared `player/` directory and one directory per deck.
`catalog.js` is the editable catalog and controls presentation order.
New decks are prepended; replacement preserves position and unspecified metadata.
Each deck's `deck.js` is its authoritative slide list. Do not create duplicate
JSON catalogs. Both files use indented JSON-compatible objects in their existing
`window.PDFWebPublisherCatalog` / `window.PDFWebPublisherDeck` assignments.
Use double-quoted keys/strings without comments or trailing commas inside data.

Catalog entries have an `href`, such as `deck-one/index.html`, and a deck-relative
cover path, such as `cover.webp`. Deck data has no slug. To rename a presentation,
rename its directory and change only that catalog link; no internal edits or
rebuild are needed. Use the new directory name with `--slug` for later replacement.

Offer the bundled themes when appearance is unspecified, without blocking an
ordinary publish: **Programme** (default: light gray and cobalt, cover-and-title
rows), **Screening Room** (charcoal, larger covers), and **Field Notes** (pale mint,
compact numbered entries). `--theme programme|screening-room|field-notes` sets the
site-wide theme. Preserve an existing choice unless the user changes it.

For bespoke interface changes use available design guidance, such as impeccable;
preserve the shipped [design system](DESIGN.md). The stock themes do not require
a separate design skill at publishing time.

Hand-edited data takes effect on reload. Refresh generated HTML titles/themes,
or recalculate gallery counts after changing a deck's slide array, with:

```text
uv run /skill/scripts/publish.py rebuild --output /website
```

Read [the CLI and data reference](references/cli-and-format.md) for all options,
schemas, player updates, and recovery, and [the user guide](README.md) for the two
ways to keep all talks in one publishing home. Classic scripts are deliberate:
JSON fetching and ES modules would break double-click viewing in common browsers.

Version-1 archives require explicit `rebuild --refresh-player` migration. It
converts their legacy JSON sources, removes the obsolete JSON copies, and updates
the player without rendering PDFs again. Do not migrate automatically on publish.
The explicit refresh replaces customized managed player files, including CSS.

## Verify and deliver

Run `validate`, open `presentations/index.html` and a deck locally, and inspect a
representative slide at desktop and phone widths. When browser tooling requires
HTTP, also check a static-server preview; report separately if `file://` could
not be tested. Check gallery links, metadata search, slide navigation, thumbnails,
and the selected theme. Deliver the archive's absolute path and index link.

Upload the **whole** `presentations/` folder when the user chooses to publish it.
Creating local output does not itself authorize a hosting upload.

Only compressed imagery is exported: no source PDF, slide text layer, notes, or
high-resolution original. The player omits download and print controls, suppresses
slide context menus and dragging, and hides imagery when printing. Browser Save
As, developer tools, OCR, and screenshots remain possible. Describe this as a
casual-copying deterrent, never access control or DRM. Image-only slides do not
provide a screen-reader transcription of their contents.
