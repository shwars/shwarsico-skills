# PDF Web Publisher

Publish PDFs as a browsable presentation archive for a static website or local
viewing. Each PDF page becomes a compressed image, and every presentation uses
one shared player. Open the resulting `presentations/index.html` in a browser,
or upload the complete `presentations/` folder to your website.

The skill accepts **PDF only**. Export PowerPoint files to PDF first. Authoring
requires Python 3.10+ and [uv](https://docs.astral.sh/uv/); the script declares its
PDFium and Pillow dependencies, which uv installs when needed. First-time setup
can require internet access. Visitors need only a browser.

## Keep all presentations in one archive

The output argument is always the **parent of `presentations/`**:

| How you publish | Where the archive is built |
| --- | --- |
| No `--output` | `presentations/` under the current working directory |
| `--output D:\my-site` | `D:\my-site\presentations\` |

Every publish to the same parent updates the existing catalog and adds the new
deck to that collection. Publishing to different parents creates independent
archives; it does not merge those archives later.

### Start the coding assistant in your website directory

For a site with this structure, start your assistant in `D:\my-site`:

```text
D:\my-site\                    ← start the coding assistant here
  presentations\
    index.html
    catalog.js
    player\
    first-talk\
```

Then ask:

```text
Use $pdf-web-publisher to publish D:\talks\agents.pdf into the existing
presentation archive. Use the title "Building useful agents" and slug agents.
```

Starting inside `D:\my-site\presentations` and using the default would create a
nested `presentations\presentations` directory. Start in the parent instead.
Keep the input PDF outside the generated `presentations/` folder.

### Specify the same publishing home from anywhere

If you often work in different directories, always give the same output parent:

```text
Use $pdf-web-publisher to publish D:\talks\evaluation.pdf. Always use
D:\my-site as the output parent, so the deck joins D:\my-site\presentations.
Use the title "Evaluating AI applications" and slug evaluation.
```

The equivalent CLI command uses `--output D:\my-site`, **not**
`--output D:\my-site\presentations`.

### Make your chosen directory a personal default

You can modify your installed copy of this skill's [SKILL.md](SKILL.md) to tell
your assistant to always use your own publishing directory. For example:

```text
For my presentation archive, always use D:\my-site as the output parent.
Pass --output "D:\my-site" to publish, rebuild, and validate, regardless of
the current working directory. All decks belong in D:\my-site\presentations.
Use a different destination only when I explicitly request it.
```

Replace that example path with the directory you actually use for posting
presentations. This is an instruction for the coding assistant: the CLI itself
still defaults to the current working directory unless `--output` is supplied.

## CLI examples

Use the absolute path to the publisher script in your installed skill. These
PowerShell examples assume it is installed under `C:\skills`:

```powershell
$publisher = 'C:\skills\pdf-web-publisher\scripts\publish.py'

# Publish into the archive under the current directory.
Set-Location 'D:\my-site'
uv run $publisher publish 'D:\talks\agents.pdf' --slug agents --title 'Building useful agents'

# Add another talk to the same archive, from any working directory.
uv run $publisher publish 'D:\talks\evaluation.pdf' --output 'D:\my-site' --slug evaluation --title 'Evaluating AI applications' --tag AI

# Replace one existing deck, preserving its catalog position and unspecified metadata.
uv run $publisher publish 'D:\talks\agents-v2.pdf' --output 'D:\my-site' --slug agents --replace

# Refresh generated HTML and slide counts after editing data, or change the theme.
uv run $publisher rebuild --output 'D:\my-site' --theme screening-room

# Check the archive without modifying it.
uv run $publisher validate --output 'D:\my-site'
```

New decks appear first. Slugs are directory names: use a unique slug for a new
talk and `--replace` for an intentional update. The publisher will not silently
overwrite a deck with the same slug or an unmanaged conflicting entrypoint.

Optional metadata includes speaker, event, date, description, and repeatable
`--tag` values. By default, the title comes from PDF metadata or the filename,
and page 1 supplies the cover. See the [CLI and format reference](references/cli-and-format.md)
for all options.

## Choose a design

All three themes include the same navigation, search, keyboard shortcuts, swipe,
thumbnails, and fullscreen behavior. The theme is **site-wide** and persists
until you explicitly change it.

| Theme | Option value | Appearance and use |
| --- | --- | --- |
| Programme — default | `programme` | Light gray and cobalt, with cover thumbnails beside titles and event details. A general-purpose public talk archive. |
| Screening Room | `screening-room` | Charcoal surfaces and larger covers. More space for the presentation imagery and a darker viewing environment. |
| Field Notes | `field-notes` | Pale mint, numbered entries, and compact rows. Useful for scanning longer collections. |

Ask your assistant to use a named theme, pass `--theme` to `publish` or `rebuild`,
or edit `site.theme` in `catalog.js` and reload. A rebuild updates the HTML's
initial theme and title as well. For bespoke styling, see the [design system](DESIGN.md).
Changes to the published player are reused by subsequent publishes; an explicit
`--refresh-player` replaces the bundled player files, including customized CSS.

## How it works

1. **Render complete PDF pages.** PDFium preserves each page's proportions and
   rotation. Pillow saves lossy WebP slides, smaller covers, and thumbnail images.
   Defaults are a 1440 px slide long edge and quality 55; dense slides may need a
   higher `--max-edge` or `--quality`.
2. **Maintain one catalog and one slide list per deck.** `catalog.js` holds site
   settings, talk metadata, ordering, and links. Each `deck.js` holds that deck's
   relative image paths and dimensions. There are no duplicate JSON catalogs.
   The catalog's slide count is a summary recalculated by publish/rebuild.
3. **Reuse the shared player.** The first publish copies player assets from the
   skill. Compatible player files are subsequently reused without modification.
4. **Load data through classic scripts.** The browser reads the same JavaScript
   data files that the publisher edits. No JSON fetching, module loader, CDN,
   backend, or local web server is required for double-click viewing.
5. **Stage updates before committing.** Rendering and validation happen before
   replacing published files. Ordinary write/rename failures roll back managed
   changes. Use one publisher at a time for each archive; keep normal backups.

Content hashes in slide filenames help avoid stale images when replacing a deck
on a static website. If configuring hosting caches, allow HTML and data scripts
to revalidate because those filenames stay the same.

## Directory layout

The installed skill contains the tools and reusable assets:

```text
pdf-web-publisher/
  SKILL.md                       instructions for the coding assistant
  README.md                      this user guide
  scripts/
    publish.py                   publish, rebuild, validate, and v1 migration
    test_publish.py              behavior tests and sample archive generator
    test_browser.cjs             optional browser checks
  assets/player/                 player files copied into a new archive
  references/cli-and-format.md   detailed CLI and data format
  PRODUCT.md                     product constraints
  DESIGN.md                      theme and interface guidance
```

The uploadable result is separate from the skill:

```text
my-site/
  presentations/
    index.html                   gallery entrypoint
    catalog.js                   editable site settings and main catalog
    player/
      manifest.json              one player compatibility record, not a catalog
      common.js
      gallery.js
      viewer.js
      styles.css
    agents/
      index.html                 deck entrypoint; all references are relative
      deck.js                    editable slide list and rendering settings
      cover.webp
      slides/                    compressed slide images
      thumbnails/                smaller preview images
    evaluation/
      ...
```

Upload the complete `presentations/` folder together. A deck directory depends on
the shared catalog and player in its parent. Publishing also works beneath a
website subdirectory. Creating local files does not automatically upload them.

## Edit the data by hand

The data files are JavaScript assignments around **JSON-compatible objects**:

```javascript
window.PDFWebPublisherCatalog = {
  "generator": "pdf-web-publisher",
  "version": 2,
  "site": {
    "title": "My talks",
    "theme": "programme"
  },
  "presentations": [
    {
      "href": "agents/index.html",
      "title": "Building useful agents",
      "cover": "cover.webp",
      "slide_count": 12,
      "speaker": "Speaker name",
      "tags": ["AI"]
    }
  ]
};
```

Change metadata, theme, or array order directly and reload the browser. Use
double-quoted keys and strings, with no comments or trailing commas inside the
object. Keep the `window.PDFWebPublisherCatalog =` assignment (or
`window.PDFWebPublisherDeck =` in `deck.js`). The publisher parses this limited
format as data; it does not execute JavaScript. Generated files include an
ownership comment above the assignment, which you can leave in place.

Slide paths in `deck.js` are relative to that deck's directory. If you edit its
slide array, run `rebuild` to recalculate the gallery's slide count. Rebuild also
updates generated HTML titles and initial themes after metadata changes; normal
browser viewing reads the edited data immediately. Validation accepts equivalent
data formatting, but reports stale generated HTML or slide counts until rebuilt.

### Rename a presentation directory

To rename `agents` to `useful-agents`:

1. Rename the folder `presentations/agents` to `presentations/useful-agents`.
2. Change only its catalog link to `"href": "useful-agents/index.html"`.

Nothing inside the deck needs editing: `deck.js` has no slug, the cover path is
deck-relative, and the HTML's player references stay relative. No rebuild is
needed just for the rename. Existing external URLs to the old directory will
need updating or a redirect on your hosting service. For future replacements,
use `--slug useful-agents --replace`.

## Migrate an older archive

Archives generated with format version 1 contain both JSON sources and JavaScript
copies. Convert them explicitly:

```powershell
uv run $publisher rebuild --output 'D:\my-site' --refresh-player
```

Migration reads the legacy JSON sources, writes the version-2 JavaScript data,
updates the player, and removes the obsolete `presentations.json` and managed
`deck.json` files. It preserves image files and unrelated content without needing
the input PDFs or rendering them again. Managed decks that were previously
unlisted are converted too. The operation stages changes and rolls back ordinary
write/rename failures. **Player refresh replaces customized managed player code
and CSS**, so preserve those customizations before migrating.

`player/manifest.json` remains: it is a single compatibility record, not a
duplicate catalog. Subsequent publishing uses only the JavaScript data files.

## Viewing and copying limits

Navigate with arrows, Page Up/Page Down, Home/End, swipe, or the player buttons.
Use **T** for thumbnails, **F** for fullscreen, and **Escape** to exit expanded
view or close thumbnails. Share a slide with a URL such as
`presentations/agents/index.html#slide=5`.

Only rendered imagery is published. Source PDFs, extracted text layers, notes,
and higher-resolution originals are not copied into the archive. Download/print
controls are omitted, slide context menus and dragging are suppressed, and slide
imagery is hidden when printing. This deters casual copying; browser Save As,
developer tools, screenshots, and OCR remain possible. Image-only slides also
provide no screen-reader transcription, embedded PDF links, or text search.
