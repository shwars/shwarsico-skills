# /// script
# requires-python = ">=3.10"
# dependencies = ["pypdfium2>=5,<6", "Pillow>=12,<14"]
# ///
"""Build portable image-only presentation archives. No server or Office required."""
from __future__ import annotations

import argparse
import copy
from datetime import date
import hashlib
import html
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tempfile
import unicodedata

GENERATOR = "pdf-web-publisher"
VERSION = 2
PLAYER_VERSION = "2.0.0"
MARKER = "pdf-web-publisher:generated v2"
LEGACY_MARKER = "pdf-web-publisher:generated v1"
CATALOG_VARIABLE = "PDFWebPublisherCatalog"
DECK_VARIABLE = "PDFWebPublisherDeck"
MIGRATION_HINT = "Version-1 archive found. Run rebuild --refresh-player to migrate its JSON sources to editable JavaScript."
THEMES = ("programme", "screening-room", "field-notes")
SKILL = Path(__file__).resolve().parents[1]
ASSETS = SKILL / "assets" / "player"
PLAYER_FILES = ("common.js", "gallery.js", "viewer.js", "styles.css", "manifest.json")
SLUG_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{0,79}\Z")


class PublishError(ValueError):
    """An actionable input or archive error."""


def fail(message):
    raise PublishError(message)


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_text(value), encoding="utf-8")


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail(f"Cannot read {path}: {exc}")


def check_header(value, label, version=VERSION):
    if not isinstance(value, dict) or value.get("generator") != GENERATOR or value.get("version") != version:
        if isinstance(value, dict) and value.get("generator") == GENERATOR and value.get("version") == 1 and version == VERSION:
            fail(MIGRATION_HINT)
        fail(f"{label} is not a supported {GENERATOR} manifest (version {version}).")


def js_data(variable, value):
    payload = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    payload = payload.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return f"/* {MARKER} */\nwindow.{variable} = {payload};\n"


def write_data(path, variable, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(js_data(variable, value), encoding="utf-8")


def read_data(path, variable):
    """Read a JSON object in a known assignment; never execute JavaScript."""
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate key: {key}")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError(f"Not a JSON value: {value}")

    try:
        source = path.read_text(encoding="utf-8-sig")
        wrapper = re.match(r"\s*(?:/\*\s*pdf-web-publisher:generated v[12]\s*\*/\s*)?window\."
                           + re.escape(variable) + r"\s*=\s*", source)
        if not wrapper:
            raise ValueError(f"Expected window.{variable} = {{ ... }};")
        decoder = json.JSONDecoder(object_pairs_hook=unique_object, parse_constant=invalid_constant)
        value, end = decoder.raw_decode(source[wrapper.end():])
        if source[wrapper.end() + end:].strip() not in ("", ";") or not isinstance(value, dict):
            raise ValueError("Only a JSON object and an optional final semicolon are allowed")
        return value
    except (OSError, UnicodeError, ValueError) as exc:
        fail(f"Cannot read {path}: {exc}. Use double-quoted JSON keys/strings, without comments or trailing commas inside the object.")


def slugify(stem):
    ascii_name = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")[:72].rstrip("-")
    if not slug or slug == "player":
        slug = "deck-" + hashlib.sha256(stem.encode()).hexdigest()[:8]
    return slug


def check_slug(slug):
    if not isinstance(slug, str) or not SLUG_PATTERN.fullmatch(slug) or slug == "player":
        fail("Slug must be 1–80 lowercase ASCII letters, digits, or hyphens, start with a letter/digit, and cannot be 'player'.")


def entry_slug(entry):
    href = entry.get("href")
    if not isinstance(href, str) or not href.endswith("/index.html"):
        fail("Each presentation href must be 'deck-directory/index.html'.")
    slug = href[:-len("/index.html")]
    check_slug(slug)
    return slug


def local_file(root, relative):
    """Accept only contained, ordinary relative asset paths; never traverse symlinks."""
    if not isinstance(relative, str) or not relative or any(c in relative for c in "\\:?#\x00"):
        fail(f"Invalid local asset path: {relative!r}")
    parts = PurePosixPath(relative).parts
    if PurePosixPath(relative).is_absolute() or any(p in (".", "..") for p in parts):
        fail(f"Asset must stay inside its archive directory: {relative!r}")
    candidate = root.joinpath(*parts)
    current = root
    for part in parts:
        current /= part
        if current.is_symlink():
            fail(f"Symlink assets are not supported: {current}")
    if not candidate.resolve().is_relative_to(root.resolve()) or not candidate.is_file():
        fail(f"Missing local asset: {candidate}")
    return candidate


def string_field(value, key, required=False):
    item = value.get(key, "")
    if not isinstance(item, str) or (required and not item.strip()):
        fail(f"{key} must be {'a nonempty' if required else 'a'} string.")
    return item


def check_catalog(catalog):
    check_header(catalog, "catalog.js")
    site = catalog.get("site")
    if not isinstance(site, dict) or site.get("theme") not in THEMES:
        fail(f"site.theme must be one of: {', '.join(THEMES)}.")
    string_field(site, "title", required=True)
    entries = catalog.get("presentations")
    if not isinstance(entries, list):
        fail("presentations must be an ordered array.")
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            fail("Every presentation must be an object.")
        slug = entry_slug(entry)
        if "slug" in entry:
            fail(f"Remove the obsolete slug for {slug}; href is the only deck location.")
        # Windows and case-insensitive static hosts must agree about identities.
        if slug in seen:
            fail(f"Duplicate presentation slug: {slug}")
        seen.add(slug)
        string_field(entry, "title", required=True)
        for key in ("speaker", "event", "date", "description"):
            string_field(entry, key)
        if entry.get("date"):
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", entry["date"]):
                    raise ValueError()
                date.fromisoformat(entry["date"])
            except ValueError:
                fail(f"Invalid date for {slug}; use YYYY-MM-DD.")
        if type(entry.get("slide_count")) is not int or entry["slide_count"] < 1:
            fail(f"Invalid slide_count for {slug}.")
        cover = string_field(entry, "cover", required=True)
        if not cover.endswith(".webp") or cover.startswith(f"{slug}/"):
            fail(f"Cover for {slug} must be a deck-relative WebP path, such as 'cover.webp'.")
        tags = entry.get("tags", [])
        if not isinstance(tags, list) or any(not isinstance(t, str) or not t.strip() for t in tags):
            fail(f"tags for {slug} must be an array of nonempty strings.")
    return catalog


def load_catalog(root):
    if root.is_symlink():
        fail(f"Archive directory cannot be a symlink: {root}")
    if (root / "presentations.json").exists():
        fail(MIGRATION_HINT)
    path = root / "catalog.js"
    if path.is_symlink():
        fail(f"Catalog cannot be a symlink: {path}")
    if path.exists():
        return check_catalog(read_data(path, CATALOG_VARIABLE))
    return {"generator": GENERATOR, "version": VERSION,
            "site": {"title": "Presentations", "theme": "programme"}, "presentations": []}


def check_player(root, refresh=False):
    player = root / "player"
    if not player.exists() and not player.is_symlink():
        return True
    if player.is_symlink() or not player.is_dir():
        fail("player must be an ordinary directory.")
    manifest = player / "manifest.json"
    if not manifest.is_file() or manifest.is_symlink():
        fail("Existing player is unmanaged. Choose another output directory or move it aside.")
    value = read_json(manifest)
    if not isinstance(value, dict) or value.get("generator") != GENERATOR:
        fail("Existing player is unmanaged; it will not be overwritten.")
    for name in PLAYER_FILES:
        if (player / name).is_symlink() or ((player / name).exists() and not (player / name).is_file()):
            fail(f"Conflicting player asset: {player / name}")
    if refresh:
        return True
    if value.get("version") != PLAYER_VERSION or value.get("data_version") != VERSION:
        fail("Incompatible player. Run rebuild --refresh-player to install the bundled player.")
    missing = [name for name in PLAYER_FILES if not (player / name).is_file()]
    if missing:
        fail(f"Player assets missing: {', '.join(missing)}. Run rebuild --refresh-player.")
    return False


def generated_target(path):
    if path.is_symlink() or (path.exists() and not path.is_file()):
        fail(f"Conflicting output path: {path}")
    if path.exists():
        try:
            source = path.read_text(encoding="utf-8")[:600]
            managed = MARKER in source or LEGACY_MARKER in source
        except (OSError, UnicodeError):
            managed = False
        if not managed:
            fail(f"Will not replace unmanaged file: {path}. Move it aside or choose another --output.")


def image_info(root, relative, expected=None):
    from PIL import Image
    path = local_file(root, relative)
    try:
        with Image.open(path) as image:
            if image.format != "WEBP":
                fail(f"Expected WebP image: {path}")
            size = image.size
            image.verify()
    except (OSError, SyntaxError) as exc:
        fail(f"Invalid image {path}: {exc}")
    if expected is not None and list(size) != expected:
        fail(f"Image dimensions do not match manifest: {path}")
    return size


def check_deck(folder, entry, deck=None, check_count=True):
    if folder.is_symlink() or not folder.is_dir():
        fail(f"Missing or symlink presentation directory: {folder}")
    if deck is None:
        deck = read_data(local_file(folder, "deck.js"), DECK_VARIABLE)
    check_header(deck, str(folder / "deck.js"))
    if "slug" in deck:
        fail(f"Remove the obsolete slug in {folder / 'deck.js'}; the catalog link locates this deck.")
    slides = deck.get("slides")
    if not isinstance(slides, list) or not slides:
        fail(f"Presentation must contain slides: {folder}")
    if check_count and len(slides) != entry["slide_count"]:
        fail(f"Slide count mismatch: {folder}. Run rebuild to recalculate catalog counts.")
    max_edge = deck.get("max_edge")
    quality = deck.get("quality")
    if type(max_edge) is not int or not 320 <= max_edge <= 4096 or type(quality) is not int or not 1 <= quality <= 95:
        fail(f"Invalid image settings: {folder}")
    seen = set()
    for slide in slides:
        if not isinstance(slide, dict):
            fail(f"Invalid slide in {folder}")
        size = [slide.get("width"), slide.get("height")]
        if any(type(n) is not int or n < 1 for n in size) or max(size) > max_edge:
            fail(f"Invalid slide dimensions: {folder}")
        for key, prefix in (("src", "slides/"), ("thumbnail", "thumbnails/")):
            path = slide.get(key)
            if not isinstance(path, str) or not path.startswith(prefix) or not path.endswith(".webp") or path in seen:
                fail(f"Invalid or duplicate slide asset: {path!r}")
            seen.add(path)
            image_info(folder, path, size if key == "src" else None)
    image_info(folder, entry["cover"])
    # Never let unrelated source documents silently enter the upload directory.
    for item in folder.rglob("*"):
        if item.is_symlink():
            fail(f"Symlinks are not supported in decks: {item}")
        if item.suffix.lower() in (".pdf", ".pptx", ".ppt"):
            fail(f"Source document found in archive; move it outside presentations: {item}")
    return deck


def render_html(title, theme, deck=False):
    prefix = "../" if deck else ""
    title = html.escape(title, quote=True)
    mode = "viewer" if deck else "gallery"
    data = '<script src="deck.js" defer></script>' if deck else ""
    # The contract is emitted into each page, including generated production HTML.
    contract = """THESIS: Covers and titles orient a public talk archive; slides own the viewing stage.
OWN-WORLD: Programme uses gray/cobalt rows; Screening Room charcoal/large covers;
Field Notes mint/numbered entries. Local system type and precise SVG controls.
STORY: Find a talk, open its cover, move through image-only slides, return to the archive.
FIRST VIEWPORT: Archive title and search precede cover/title rows; a deck opens on
its fitted slide with navigation directly below. FORM: user-pinned themes; seed db88faca.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, and DESIGN.md"""
    return f'''<!doctype html>
<!-- {MARKER} -->
<html lang="en" data-theme="{theme}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="referrer" content="no-referrer">
  <title>{title}</title>
  <link rel="stylesheet" href="{prefix}player/styles.css">
  <script src="{prefix}catalog.js" defer></script>
  {data}
  <script src="{prefix}player/common.js" defer></script>
  <script src="{prefix}player/{mode}.js" defer></script>
</head>
<body class="{mode}-page">
<!-- {contract} -->
  <a class="skip-link" href="#main">Skip to content</a>
  <main id="main" tabindex="-1"><p class="boot-message" role="status">Opening {"presentation" if deck else "archive"}…</p></main>
  <noscript><p class="boot-message">Enable JavaScript to browse this image-only presentation archive.</p></noscript>
</body>
</html>
'''


def build_files(root, catalog, decks, copy_player):
    files = {
        Path("catalog.js"): js_data(CATALOG_VARIABLE, catalog),
        Path("index.html"): render_html(catalog["site"]["title"], catalog["site"]["theme"]),
    }
    for entry in catalog["presentations"]:
        slug = entry_slug(entry)
        files[Path(slug) / "index.html"] = render_html(entry["title"], catalog["site"]["theme"], deck=True)
        files[Path(slug) / "deck.js"] = js_data(DECK_VARIABLE, decks[slug])
    for relative in files:
        if relative.suffix == ".html":
            generated_target(root / relative)
    if copy_player:
        for name in PLAYER_FILES:
            files[Path("player") / name] = (ASSETS / name).read_bytes()
    return files


def commit(root, files, staged_deck=None, slug=None, removals=()):
    """Replace managed files as a unit; roll back ordinary write/rename failures."""
    existed = root.exists()
    root.mkdir(parents=True, exist_ok=True)
    transaction = Path(tempfile.mkdtemp(prefix=".publisher-", dir=root))
    installed, backups, made_dirs = [], [], []
    try:
        if staged_deck is not None:
            target = root / slug
            if target.exists():
                backup = transaction / "old-deck"
                target.rename(backup)
                backups.append((backup, target))
            shutil.copytree(staged_deck, transaction / "new-deck")
            (transaction / "new-deck").rename(target)
            installed.append(target)
        for number, (relative, content) in enumerate(files.items()):
            target = root / relative
            if not target.parent.exists():
                target.parent.mkdir(parents=True)
                made_dirs.append(target.parent)
            fresh = transaction / f"new-{number}"
            if isinstance(content, bytes):
                fresh.write_bytes(content)
            else:
                fresh.write_text(content, encoding="utf-8", newline="\n")
            # Newly staged deck wrappers have no previous files to preserve.
            if target.exists() and not (staged_deck is not None and relative.parts[0] == slug):
                backup = transaction / f"old-{number}"
                target.rename(backup)
                backups.append((backup, target))
            os.replace(fresh, target)
            installed.append(target)
        for number, relative in enumerate(removals):
            target = local_file(root, Path(relative).as_posix())
            backup = transaction / f"removed-{number}"
            target.rename(backup)
            backups.append((backup, target))
    except BaseException:
        for target in reversed(installed):
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
        for backup, target in reversed(backups):
            target.parent.mkdir(parents=True, exist_ok=True)
            backup.rename(target)
        for folder in reversed(made_dirs):
            if folder.exists() and not any(folder.iterdir()):
                folder.rmdir()
        raise
    finally:
        shutil.rmtree(transaction)
        if not existed and not any(root.iterdir()):
            root.rmdir()


def render_pdf(source, destination, max_edge, quality, cover_page):
    import pypdfium2 as pdfium
    from PIL import Image
    stream = source.open("rb")
    try:
        document = pdfium.PdfDocument(stream)
    except Exception as exc:
        stream.close()
        fail(f"Cannot open PDF (it may be corrupt or encrypted). Supply a readable, unlocked PDF: {exc}")
    try:
        count = len(document)
        if count < 1:
            fail("PDF has no pages.")
        if not 1 <= cover_page <= count:
            fail(f"--cover-page must be between 1 and {count}.")
        title = (document.get_metadata_value("Title") or "").strip()
        slides = []
        (destination / "slides").mkdir(parents=True)
        (destination / "thumbnails").mkdir()
        for number in range(count):
            page = document[number]
            try:
                width, height = page.get_size()
                if not all(math.isfinite(n) and n > 0 for n in (width, height)):
                    fail(f"Invalid page dimensions on page {number + 1}.")
                scale = max_edge / max(width, height)
                bitmap = page.render(scale=scale, fill_color=(255, 255, 255, 255))
                try:
                    image = bitmap.to_pil().convert("RGB")
                finally:
                    bitmap.close()
            finally:
                page.close()
            image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
            # Content-derived names avoid stale slides after replacing a deck on static hosting.
            digest = hashlib.sha256(image.tobytes() + str(quality).encode()).hexdigest()[:12]
            name = f"{number + 1:04d}-{digest}.webp"
            image.save(destination / "slides" / name, "WEBP", quality=quality, method=6)
            thumbnail = image.copy()
            thumbnail.thumbnail((320, 320), Image.Resampling.LANCZOS)
            thumbnail.save(destination / "thumbnails" / name, "WEBP", quality=45, method=6)
            if number + 1 == cover_page:
                cover = image.copy()
                cover.thumbnail((640, 640), Image.Resampling.LANCZOS)
                cover.save(destination / "cover.webp", "WEBP", quality=50, method=6)
            slides.append({"src": f"slides/{name}", "thumbnail": f"thumbnails/{name}",
                           "width": image.width, "height": image.height})
        manifest = {"generator": GENERATOR, "version": VERSION,
                    "max_edge": max_edge, "quality": quality, "cover_page": cover_page, "slides": slides}
        write_data(destination / "deck.js", DECK_VARIABLE, manifest)
        return title, manifest
    finally:
        document.close()
        stream.close()


def inspect_archive(root, catalog, replacing=None, check_counts=True):
    decks = {}
    for entry in catalog["presentations"]:
        slug = entry_slug(entry)
        if slug != replacing:
            decks[slug] = check_deck(root / slug, entry, check_count=check_counts)
    check_archive_files(root)
    return decks


def check_archive_files(root):
    if root.exists():
        for item in root.rglob("*"):
            if item.is_symlink():
                fail(f"Symlinks are not supported in archives: {item}")
            if item.suffix.lower() in (".pdf", ".pptx", ".ppt"):
                fail(f"Move source documents outside presentations before publishing: {item}")


def publish(args):
    root = archive_root(args.output)
    source = args.pdf.expanduser().resolve()
    if source.suffix.lower() != ".pdf" or not source.is_file():
        fail("Input must be an existing PDF file. Export PPTX to PDF before publishing.")
    if source.is_relative_to(root):
        fail("Keep the source PDF outside the presentations directory.")
    slug = args.slug or slugify(source.stem)
    check_slug(slug)
    if not 320 <= args.max_edge <= 4096 or not 1 <= args.quality <= 95:
        fail("--max-edge must be 320–4096 and --quality must be 1–95.")
    catalog = copy.deepcopy(load_catalog(root))
    old = next((e for e in catalog["presentations"] if entry_slug(e) == slug), None)
    if old and not args.replace:
        fail(f"Presentation '{slug}' already exists. Use --replace to replace it.")
    if not old and (root / slug).exists():
        fail(f"Unmanaged presentation directory exists: {root / slug}. Choose another slug.")
    previous_deck = None
    if old:
        # Validate the previous deck too: replacing must not hide unmanaged/source content.
        previous_deck = check_deck(root / slug, old)
    copy_player = check_player(root, args.refresh_player)
    decks = inspect_archive(root, catalog, replacing=slug)
    with tempfile.TemporaryDirectory(prefix="pdf-web-publisher-") as temporary:
        staged = Path(temporary) / slug
        pdf_title, manifest = render_pdf(source, staged, args.max_edge, args.quality, args.cover_page)
        entry = copy.deepcopy(old) if old else {"href": f"{slug}/index.html", "tags": []}
        entry["title"] = args.title if args.title is not None else (entry.get("title") or pdf_title or source.stem)
        for key in ("speaker", "event", "date", "description"):
            value = getattr(args, key)
            if value is not None:
                entry[key] = value
        if args.tag is not None:
            entry["tags"] = list(dict.fromkeys(args.tag))
        entry.update(cover="cover.webp", slide_count=len(manifest["slides"]))
        if old:
            catalog["presentations"][catalog["presentations"].index(old)] = entry
        else:
            catalog["presentations"].insert(0, entry)
        apply_site_options(catalog, args)
        check_catalog(catalog)
        check_deck(staged, entry)
        decks[slug] = manifest
        files = build_files(root, catalog, decks, copy_player)
        if old:
            # Keep unrelated files in a managed deck on replacement. Old generated
            # slide files are removed, but an author's extra material is preserved.
            managed = {"deck.js", "index.html", "cover.webp"}
            managed.update(s[key] for s in previous_deck["slides"] for key in ("src", "thumbnail"))
            for item in (root / slug).rglob("*"):
                relative = item.relative_to(root / slug)
                if relative.as_posix() in managed:
                    continue
                if item.is_file():
                    (staged / relative).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, staged / relative)
        commit(root, files, staged, slug)
    return {"archive": str(root), "index": str(root / "index.html"), "presentation": str(root / slug / "index.html"),
            "slides": entry["slide_count"], "theme": catalog["site"]["theme"]}


def apply_site_options(catalog, args):
    if args.theme:
        catalog["site"]["theme"] = args.theme
    if args.site_title is not None:
        catalog["site"]["title"] = args.site_title


def legacy_deck(folder, entry):
    value = read_json(local_file(folder, "deck.json"))
    check_header(value, str(folder / "deck.json"), version=1)
    if value.get("slug") != folder.name:
        fail(f"Legacy deck slug does not match its directory: {folder}")
    existing = folder / "deck.js"
    if existing.exists():
        check_header(read_data(local_file(folder, "deck.js"), DECK_VARIABLE), str(existing), version=1)
    value.pop("slug")
    value["version"] = VERSION
    return check_deck(folder, entry, deck=value, check_count=False)


def load_legacy_archive(root):
    """Convert old authoritative JSON in memory; deletions happen only at commit."""
    catalog = read_json(local_file(root, "presentations.json"))
    check_header(catalog, "presentations.json", version=1)
    if (root / "catalog.js").exists():
        check_header(read_data(local_file(root, "catalog.js"), CATALOG_VARIABLE), "catalog.js", version=1)
    entries = catalog.get("presentations")
    if not isinstance(entries, list):
        fail("Legacy presentations must be an array.")
    for entry in entries:
        if not isinstance(entry, dict):
            fail("Every legacy presentation must be an object.")
        slug = entry.get("slug")
        check_slug(slug)
        if entry.get("cover") != f"{slug}/cover.webp":
            fail(f"Invalid legacy cover for {slug}.")
        entry.pop("slug")
        entry.update(href=f"{slug}/index.html", cover="cover.webp")
    catalog["version"] = VERSION
    check_catalog(catalog)
    decks = {entry_slug(e): legacy_deck(root / entry_slug(e), e) for e in entries}
    removals = [Path("presentations.json"), *(Path(slug) / "deck.json" for slug in decks)]
    unlisted = {}
    # Previously unlisted managed decks also lose their redundant JSON copy;
    # unrelated files with a similar name are left alone.
    for path in root.glob("*/deck.json"):
        if path.parent.name in decks:
            continue
        try:
            value = read_json(local_file(root, path.relative_to(root).as_posix()))
        except PublishError:
            continue
        if not isinstance(value, dict) or value.get("generator") != GENERATOR or value.get("version") != 1:
            continue
        check_slug(path.parent.name)
        entry = {"cover": "cover.webp"}
        unlisted[Path(path.parent.name) / "deck.js"] = legacy_deck(path.parent, entry)
        removals.append(path.relative_to(root))
    return catalog, decks, removals, unlisted


def rebuild(args):
    root = archive_root(args.output)
    legacy = (root / "presentations.json").exists()
    removals, unlisted = [], {}
    if legacy:
        if not args.refresh_player:
            fail(MIGRATION_HINT)
        catalog, decks, removals, unlisted = load_legacy_archive(root)
    else:
        catalog = load_catalog(root)
        if not (root / "catalog.js").exists():
            fail("No catalog.js found. Publish a PDF first.")
        decks = inspect_archive(root, catalog, check_counts=False)
    for entry in catalog["presentations"]:
        entry["slide_count"] = len(decks[entry_slug(entry)]["slides"])
    apply_site_options(catalog, args)
    check_catalog(catalog)
    copy_player = check_player(root, args.refresh_player)
    if legacy:
        # Apply the same archive-wide checks after validating converted deck data.
        check_archive_files(root)
    files = build_files(root, catalog, decks, copy_player)
    files.update((path, js_data(DECK_VARIABLE, value)) for path, value in unlisted.items())
    commit(root, files, removals=removals)
    return {"archive": str(root), "presentations": len(decks), "theme": catalog["site"]["theme"]}


def validate(args):
    root = archive_root(args.output)
    catalog = load_catalog(root)
    if not (root / "catalog.js").is_file():
        fail("No catalog.js found. Publish a PDF first.")
    if check_player(root):
        fail("Shared player is absent. Run rebuild to restore it.")
    decks = inspect_archive(root, catalog)
    expected = build_files(root, catalog, decks, False)
    for relative, text in expected.items():
        if relative.suffix == ".js":
            continue  # Authoritative data was parsed and checked, not compared as text.
        actual = local_file(root, relative.as_posix()).read_text(encoding="utf-8")
        if actual != text:
            fail(f"Stale generated file: {relative}. Run rebuild.")
    return {"valid": True, "archive": str(root), "presentations": len(decks),
            "slides": sum(e["slide_count"] for e in catalog["presentations"])}


def archive_root(output):
    base = Path(output).expanduser().resolve()
    root = base / "presentations"
    if root.is_symlink() or (root.exists() and not root.is_dir()):
        fail(f"Archive destination must be an ordinary directory: {root}")
    return root


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    for name, help_text in (("publish", "Convert a PDF and update the gallery."),
                            ("rebuild", "Refresh HTML and counts from editable JavaScript data; migrate v1 with --refresh-player."),
                            ("validate", "Check the archive without changing it.")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--output", default=".", help="Parent directory; output is always <parent>/presentations.")
        if name != "validate":
            command.add_argument("--theme", choices=THEMES)
            command.add_argument("--site-title", help="Archive heading, preserved when omitted.")
            command.add_argument("--refresh-player", action="store_true", help="Replace the managed shared player with bundled assets.")
        if name == "publish":
            command.add_argument("pdf", type=Path)
            for key in ("slug", "title", "speaker", "event", "date", "description"):
                command.add_argument(f"--{key}")
            command.add_argument("--tag", action="append", help="Repeat for multiple tags; replaces tags when supplied.")
            command.add_argument("--cover-page", type=int, default=1, help="One-based cover page (default: 1).")
            command.add_argument("--max-edge", type=int, default=1440, help="Maximum slide long edge in pixels (default: 1440).")
            command.add_argument("--quality", type=int, default=55, help="Lossy WebP quality 1–95 (default: 55).")
            command.add_argument("--replace", action="store_true", help="Replace an existing managed deck.")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = {"publish": publish, "rebuild": rebuild, "validate": validate}[args.command](args)
    except (PublishError, OSError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json_text(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
