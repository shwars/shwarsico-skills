# CLI and archive format

Use `uv run <absolute-skill-path>/scripts/publish.py <command> ...`.
Python 3.10+ is required for authoring; uv resolves the declared pypdfium2 and
Pillow dependencies. Internet may be needed on the first dependency install.
The exported archive has no Python, Node, server, or internet requirement.

## Commands

`publish input.pdf` creates or extends an archive. PDF pages become slides in
document order, with their rotation and proportions preserved. Rasterize rendered
pages, never extract embedded images as a substitute for rendering the page.

| Option | Meaning |
| --- | --- |
| `--output BASE` | Always generate `BASE/presentations`; default BASE is the current working directory. |
| `--slug NAME` | Directory ID: lowercase ASCII letters/digits/hyphens, at most 80 characters; `player` is reserved. Derived from the filename by default, with a stable hash fallback for non-ASCII-only names. |
| `--title TEXT` | Display title; new decks default to PDF title metadata, then filename. |
| `--speaker`, `--event`, `--description` | Optional archive metadata; use an empty string to clear on replacement. |
| `--date YYYY-MM-DD` | Optional talk date, validated as a calendar date. |
| `--tag TEXT` | Repeatable tag. Supplied tags replace the previous tag list. Clear tags by editing JSON and rebuilding. |
| `--cover-page N` | One-based PDF page used for the cover; default 1. |
| `--max-edge N` | Slide long-edge cap, 320–4096; default 1440 pixels. |
| `--quality N` | Lossy WebP quality, 1–95; default 55. Not a target file size. |
| `--replace` | Replace an existing managed slug, preserving unspecified catalog metadata and its position. Image settings return to defaults unless explicitly supplied. |
| `--theme NAME` | `programme`, `screening-room`, or `field-notes`; site-wide, preserved when omitted. |
| `--site-title TEXT` | Archive heading; default `Presentations`, preserved when omitted. |
| `--refresh-player` | Explicitly replace the managed shared player with the bundled version. |

`rebuild` accepts `--output`, `--theme`, `--site-title`, and `--refresh-player`.
It validates the catalog and deck imagery, then regenerates all HTML and classic
script companions. It does not rasterize PDFs. Remove a catalog entry to unlist a
deck; its directory is preserved, but the viewer requires a catalog entry.

`validate` accepts `--output`. It reads without modifying output and checks data
versions, player files, image existence/format/dimensions, path containment, and
whether browser companions are current. All commands return a JSON result on
stdout; failures print an actionable message to stderr and return exit code 1.

## Editable catalog

`presentations/presentations.json` is authoritative for metadata, theme, and order:

```json
{
  "generator": "pdf-web-publisher",
  "version": 1,
  "site": {"title": "Talks", "theme": "programme"},
  "presentations": [
    {
      "slug": "deck-one",
      "title": "Ideas in motion",
      "cover": "deck-one/cover.webp",
      "slide_count": 12,
      "speaker": "Speaker name",
      "event": "Conference",
      "date": "2026-10-20",
      "description": "A short description of the talk.",
      "tags": ["AI", "education"]
    }
  ]
}
```

Only slug, title, cover, and slide_count are required on each entry. Optional text
fields may be omitted. Tags default to an empty list. Reorder the array to reorder
the gallery. Keep slugs stable; renaming one also requires matching its directory
and deck manifest. Gallery search matches all query words across metadata.

`deck-one/deck.json` is authoritative for image order and dimensions:

```json
{
  "generator": "pdf-web-publisher",
  "version": 1,
  "slug": "deck-one",
  "max_edge": 1440,
  "quality": 55,
  "cover_page": 1,
  "slides": [
    {"src": "slides/0001-CONTENTHASH.webp", "thumbnail": "thumbnails/0001-CONTENTHASH.webp", "width": 1440, "height": 810}
  ]
}
```

Here the example slide list is abbreviated; its real length must match the
catalog's slide_count. Filenames include a content hash to avoid stale slide
images after updates. Covers are at most 640 px and thumbnails at most 320 px.
No full slide text, source-document paths, or source PDFs are emitted.

`catalog.js` and `deck.js` contain derived `window.PDFWebPublisherCatalog` and
`window.PDFWebPublisherDeck` values. They are external classic scripts on purpose.
Do not switch to `fetch`, modules, canvas pixel reads, a service worker, or CDN
assets: double-click browsing must remain functional.

## Shared player and recovery

If `player/` is absent, publish/rebuild copies it from this skill. A present,
compatible player is reused byte-for-byte, including CSS customizations. Its
manifest identifies the bundled player version and data format version.

An incompatible or incomplete managed player requires `rebuild --refresh-player`.
Refresh replaces the known bundled files and preserves unrelated files. An
unmanaged directory named `player` is never overwritten, even with this option.
Generated HTML/script files carry an ownership marker. Conflicting unmanaged
entrypoints cause an error; move them aside or choose another base directory.

Publishing stages rendering and checks before touching the archive. Managed file
updates roll back on ordinary write/rename failures. This is a local single-writer
tool: do not run two publishers on the same archive concurrently. As with any
multi-file update, process termination or power loss during the commit can require
restoring a backup; it is not a database transaction.

Keep input PDFs outside `presentations/`. The validator rejects source documents
and symlinks within the archive to prevent accidental source publication or
references outside the portable directory. Preserve the whole folder on upload,
including catalog companions and the shared player. Cache HTML/data scripts with
revalidation on the hosting service when configuring cache policy; image filenames
are content-addressed, but entrypoints are updated in place.

## Viewing

Open `presentations/index.html` or a deck's `index.html`. The entire folder must
travel together. Direct slide links use `deck-one/index.html#slide=12`.

Controls: Left/Right arrows or Page Up/Page Down, Home/End, T for thumbnails,
F for fullscreen, Escape to close thumbnails or expanded view. Native fullscreen
has an in-page fallback. Mobile visitors can swipe horizontally; vertical scroll
and browser pinch zoom remain available. A failed image shows a retry action.

PDF pages are images: embedded links, animations, text selection, and slide-text
search are not exported. Gallery metadata remains selectable/searchable. The
viewer does not intercept browser Save As or developer-tool shortcuts. Its casual
copying deterrents do not prevent screenshots, OCR, or a determined download.

## Development checks

From the skill directory, run `uv run scripts/test_publish.py` for the Python
behavior tests. ReportLab is a test-only dependency, declared by that script.
To generate labeled, synthetic decks for all three themes:

```text
uv run scripts/test_publish.py --preview /temporary/preview
node scripts/test_browser.cjs /temporary/preview /temporary/screenshots
```

The optional browser check requires the `playwright` Node package and its
Chromium browser, available through ordinary Node resolution or `NODE_PATH`.
Set `PLAYWRIGHT_CHROMIUM_EXECUTABLE` to use an existing Chromium executable.
It serves fixtures only on loopback, checks both file and HTTP viewing, and saves
desktop/mobile screenshots. Browser tests and ReportLab are not viewing or
publishing dependencies. Use temporary directories outside the skill package.
