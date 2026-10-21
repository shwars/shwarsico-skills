# CLI and archive format

Use `uv run <absolute-skill-path>/scripts/publish.py <command> ...`.
Python 3.10+ is required for authoring; uv resolves the declared PDFium and
Pillow dependencies. First-time dependency installation may need internet.
The exported archive requires only a browser. See [the user guide](../README.md)
for assistant prompts, directory workflows, and the three theme choices.

## Commands

`publish input.pdf` creates or extends an archive, with one rendered image per
PDF page, preserving document order, rotation, and proportions.

| Option | Meaning |
| --- | --- |
| `--output BASE` | Generate `BASE/presentations`; default BASE is the current working directory. Reuse the same parent to keep all talks in one archive. |
| `--slug NAME` | Directory name: lowercase ASCII letters/digits/hyphens, at most 80 characters; `player` is reserved. Derived from the filename, with a stable hash fallback for non-ASCII-only names. Stored only as part of the main catalog link, never inside deck data. |
| `--title TEXT` | Display title; new decks default to PDF title metadata, then filename. |
| `--speaker`, `--event`, `--description` | Optional metadata; an empty string clears the field on replacement. |
| `--date YYYY-MM-DD` | Optional talk date, validated as a calendar date. |
| `--tag TEXT` | Repeat for multiple tags. Supplied tags replace the previous list; clear it by editing the catalog. |
| `--cover-page N` | One-based PDF page used for the cover; default 1. |
| `--max-edge N` | Slide long-edge cap, 320–4096; default 1440 pixels. |
| `--quality N` | Lossy WebP quality, 1–95; default 55. Not a target file size. |
| `--replace` | Replace an existing managed deck, preserving unspecified metadata and catalog position. Rendering settings return to defaults unless supplied. |
| `--theme NAME` | `programme`, `screening-room`, or `field-notes`; site-wide, preserved when omitted. |
| `--site-title TEXT` | Archive heading; default `Presentations`, preserved when omitted. |
| `--refresh-player` | Explicitly replace managed player files with bundled assets, including custom CSS. |

`rebuild` accepts `--output`, `--theme`, `--site-title`, and `--refresh-player`.
It validates the authoritative data, recalculates catalog slide counts from deck
slide lists, formats the JavaScript data files, and refreshes generated HTML.
It does not rasterize PDFs or generate JSON catalog copies. Reordering or editing
metadata in JavaScript takes effect on browser reload; rebuild updates HTML title
and initial-theme fallbacks as well. Removing a catalog entry unlists the deck
without deleting its directory; the viewer requires a catalog entry to open it.

`validate` accepts `--output`. It checks without changing output: data/player
versions, image existence/format/dimensions, safe local paths, summary counts, and
generated HTML freshness. Equivalent JavaScript data formatting is accepted.
All commands return JSON results on stdout. Failures print an actionable message
to stderr and return exit code 1.

## Authoritative data files

The main catalog is `presentations/catalog.js`:

```javascript
window.PDFWebPublisherCatalog = {
  "generator": "pdf-web-publisher",
  "version": 2,
  "site": {
    "title": "Talks",
    "theme": "programme"
  },
  "presentations": [
    {
      "href": "deck-one/index.html",
      "title": "Ideas in motion",
      "cover": "cover.webp",
      "slide_count": 12,
      "speaker": "Speaker name",
      "event": "Conference",
      "date": "2026-10-22",
      "description": "A short description of the talk.",
      "tags": ["AI", "education"]
    }
  ]
};
```

Each entry requires href, title, cover, and slide_count. Optional text fields may
be omitted; tags default to an empty array. The ordered array controls gallery
order, and search matches all query words across metadata. `href` has the exact
form `valid-slug/index.html`. Cover paths are relative to that deck directory,
not the archive root; they must refer to local WebP images within the deck.

Each deck's only slide-data file is `deck-one/deck.js`:

```javascript
window.PDFWebPublisherDeck = {
  "generator": "pdf-web-publisher",
  "version": 2,
  "max_edge": 1440,
  "quality": 55,
  "cover_page": 1,
  "slides": [
    {
      "src": "slides/0001-CONTENTHASH.webp",
      "thumbnail": "thumbnails/0001-CONTENTHASH.webp",
      "width": 1440,
      "height": 810
    }
  ]
};
```

The example slide list is abbreviated: the real array length supplies the catalog
summary count. All image paths are relative to the deck. There is no internal
slug, title, or copied gallery metadata. Images contain no exported text layer.
Slide names include content hashes; cover and thumbnail long edges are capped at
640 and 320 px respectively.

Both files are readable JavaScript assignments containing **JSON-compatible
objects**, written with two-space indentation and readable Unicode. Keep the
known `window` assignment and double-quoted keys/strings. Comments and trailing
commas inside the object, arbitrary expressions, extra executable statements,
duplicate keys, and non-JSON constants are not supported. The generated ownership
comment above the assignment is allowed; it and the final semicolon are optional
when hand editing. Python reads the data object without evaluating JavaScript.

Do not add parallel JSON copies or replace classic scripts with `fetch`, modules,
CDNs, a service worker, or canvas pixel reads: double-click viewing must continue
to work. The browser and publisher use the same files as the source of truth.

## Renaming a deck

Rename the directory and change only its `href` in `catalog.js`:

```text
deck-one/                       → renamed-talk/
"href": "deck-one/index.html"   → "href": "renamed-talk/index.html"
```

Leave `deck.js`, deck-relative cover/image paths, and HTML unchanged. The viewer
matches its current URL to the main catalog, ignoring query strings and slide
hashes and treating directory URLs as `index.html`. Rename only at the current
one-directory depth and use the same valid directory-name syntax as `--slug`.
No rebuild is needed for this operation. Future replacements must use the new
name: `publish input.pdf --slug renamed-talk --replace`. Old public URLs need a
hosting redirect if you want them to keep working.

## Shared player and migration

If `player/` is absent, publish/rebuild copies it from this skill. Compatible
players are reused byte-for-byte. Its single `manifest.json` records compatibility
and has no JavaScript duplicate. Version-2 data uses player version 2.0.0.
Incomplete/incompatible managed players require `rebuild --refresh-player`.
Refresh preserves unrelated files but replaces managed code/CSS customizations.
Unmanaged player directories and conflicting HTML entrypoints are not overwritten.

Version-1 archives contain `presentations.json` and per-deck `deck.json` sources
alongside generated JavaScript copies. Publish/validate and ordinary rebuild stop
with a migration instruction. Explicitly run:

```text
uv run /skill/scripts/publish.py rebuild --output /website --refresh-player
```

Migration reads the old JSON sources, converts links and relative covers, removes
deck slugs, writes version-2 data/HTML/player files, and removes the old managed
JSON sources in the same staged commit. It converts previously unlisted managed
decks too, preserving their unlisted status. Unrelated files and existing slide
images are preserved; no PDF input or rendering is needed. It refuses ambiguous
mixed versions rather than overwriting version-2 edits with legacy JSON.
Repeating the command on a migrated archive performs an ordinary player refresh.

Managed updates, including migration removals, roll back on ordinary write/rename
failures. This is a local single-writer tool: do not run concurrent publishers
against one archive. Process termination or power loss during a multi-file commit
can still require restoring a backup.

Keep source PDFs outside `presentations/`. Source documents and symlinks in the
archive are rejected to prevent accidental source uploads and external references.
Upload the entire folder together and allow HTML/data-script revalidation when
configuring host caches; slide image names are content-addressed.

## Viewing and development checks

Open the archive's `index.html` or a deck's `index.html`. Direct links accept
`deck-one/index.html#slide=12`. Keyboard controls: Left/Right, Page Up/Page Down,
Home/End, T for thumbnails, F for fullscreen, Escape to close expanded view or
thumbnails. Native fullscreen has a keyboard-accessible in-page fallback.
Horizontal swipe is supported; vertical scrolling and browser pinch zoom remain.
Missing images produce a visible retry action.

PDF links, animations, text selection, and slide-text search are not exported;
gallery metadata remains selectable/searchable. Save As and developer-tool
shortcuts are not intercepted. Copying deterrents do not prevent screenshots,
OCR, or a determined image download.

From the skill directory, run `uv run scripts/test_publish.py` for behavior tests.
ReportLab is a declared test-only dependency. Generate labeled sample decks for
all themes and run optional browser checks with:

```text
uv run scripts/test_publish.py --preview /temporary/preview
node scripts/test_browser.cjs /temporary/preview /temporary/screenshots
```

Browser checks need the `playwright` Node package and Chromium, through normal
Node resolution or `NODE_PATH`. `PLAYWRIGHT_CHROMIUM_EXECUTABLE` selects an existing
browser executable. Checks use loopback/file URLs and temporary copied archives
for hand-editing/rename cases. ReportLab and browser dependencies are not needed
to publish or view ordinary archives.
