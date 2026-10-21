# /// script
# requires-python = ">=3.10"
# dependencies = ["pypdfium2>=5,<6", "Pillow>=12,<14", "reportlab>=4,<5"]
# ///
"""Behavior tests. Run: uv run scripts/test_publish.py (uses isolated temp output)."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfdoc import PDFArray
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.lib.colors import HexColor

spec = importlib.util.spec_from_file_location("publisher", Path(__file__).with_name("publish.py"))
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


def make_pdf(path, title="A talk", pages=((640, 360, 0), (300, 600, 0), (640, 360, 90)), encrypted=False):
    pdf = canvas.Canvas(str(path), encrypt=StandardEncryption("secret") if encrypted else None)
    pdf.setTitle(title)
    for index, (width, height, rotation) in enumerate(pages):
        pdf.setPageSize((width, height))
        pdf.setPageRotation(rotation)
        colors = ((.08, .25, .6), (.06, .45, .28), (.65, .12, .2))
        pdf.setFillColorRGB(*colors[index % len(colors)])
        pdf.rect(0, 0, width, height, stroke=0, fill=1)
        pdf.setFillColorRGB(1, 1, 1)
        pdf.setFont("Helvetica", 24)
        pdf.drawString(30, height - 60, f"SLIDE CONTENT PRIVATE {index + 1}")
        pdf.setFillColorRGB(.9, .75, .2)
        pdf.rect(width - 60, 20, 40, 40, stroke=0, fill=1)
        pdf.showPage()
        # ReportLab otherwise swaps the MediaBox for quarter-turn rotation,
        # hiding the dimension change this fixture is intended to exercise.
        pdf._doc.Pages.pages[-1].MediaBox = PDFArray([0, 0, width, height])
    pdf.save()


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def make_preview(base):
    """Generate labeled sample decks for the optional browser/visual checks."""
    base = base.expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    talks = [
        ("working-system", "From prompt to working system", "#163FA4", ["From prompt to", "working system"], ["AI", "engineering"]),
        ("useful-models", "What makes a model useful?", "#C8D994", ["What makes a", "model useful?"], ["models", "evaluation"]),
        ("small-experiments", "Teaching with small experiments", "#B74424", ["Teaching with", "small experiments"], ["education", "experiments"]),
    ]
    for slug, title, color, lines, tags in talks:
        source = base / f"{slug}.pdf"
        pdf = canvas.Canvas(str(source), pagesize=(960, 540))
        pdf.setTitle(title)
        for slide_index in range(3):
            width, height = (480, 720) if slide_index == 2 else (960, 540)
            pdf.setPageSize((width, height))
            pdf.setFillColor(HexColor(color))
            pdf.rect(0, 0, width, height, stroke=0, fill=1)
            pdf.setFillColor(HexColor("#17392B" if slug == "useful-models" else "#FFFFFF"))
            pdf.setFont("Helvetica", 15)
            pdf.drawString(40, height - 48, "SAMPLE TALK / 2026")
            pdf.setFont("Helvetica-Bold", 48 if slide_index < 2 else 30)
            for line_index, line in enumerate(lines if slide_index == 0 else ["An experiment", "and a result"]):
                pdf.drawString(40, height - 180 - 60 * line_index, line)
            pdf.setFont("Helvetica", 12)
            pdf.drawString(40, 60, "Illustrative content for the publisher preview")
            pdf.showPage()
        pdf.save()
        for theme in publisher.THEMES:
            output = base / theme / "nested" / "site"
            arguments = ["publish", str(source), "--output", str(output), "--slug", slug,
                         "--theme", theme, "--site-title", "Talks / sample archive", "--speaker", "Demo speaker",
                         "--event", "Sample conference", "--date", "2026-10-20"]
            for tag in tags:
                arguments += ["--tag", tag]
            if (output / "presentations" / slug).exists():
                arguments += ["--replace", "--refresh-player"]
            publisher.publish(publisher.parser().parse_args(arguments))
    print(base)


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="publisher-test-")
        self.base = Path(self.temp.name)
        self.source = self.base / "Исходный доклад.pdf"
        make_pdf(self.source, title="Доклад <AI> & ideas")
        self.output = self.base / "Сайт with spaces"
        self.root = self.output / "presentations"

    def tearDown(self):
        self.temp.cleanup()

    def args(self, command, *extras, output=True):
        return publisher.parser().parse_args([command, *([str(self.source)] if command == "publish" else []),
                                             *(["--output", str(self.output)] if output else []), *map(str, extras)])

    def publish(self, *extras):
        return publisher.publish(self.args("publish", "--slug", "one", *extras))

    def catalog(self):
        return publisher.read_data(self.root / "catalog.js", publisher.CATALOG_VARIABLE)

    def deck(self, slug="one"):
        return publisher.read_data(self.root / slug / "deck.js", publisher.DECK_VARIABLE)

    def save_catalog(self, value):
        publisher.write_data(self.root / "catalog.js", publisher.CATALOG_VARIABLE, value)

    def make_legacy_archive(self):
        self.publish("--speaker", "Alice", "--tag", "AI")
        catalog = self.catalog()
        catalog["version"] = 1
        for entry in catalog["presentations"]:
            slug = publisher.entry_slug(entry)
            deck = self.deck(slug)
            deck.update(version=1, slug=slug)
            publisher.write_json(self.root / slug / "deck.json", deck)
            source = publisher.js_data(publisher.DECK_VARIABLE, deck).replace(publisher.MARKER, publisher.LEGACY_MARKER)
            (self.root / slug / "deck.js").write_text(source, encoding="utf-8")
            entry.pop("href")
            entry.update(slug=slug, cover=f"{slug}/cover.webp")
        publisher.write_json(self.root / "presentations.json", catalog)
        source = publisher.js_data(publisher.CATALOG_VARIABLE, catalog).replace(publisher.MARKER, publisher.LEGACY_MARKER)
        (self.root / "catalog.js").write_text(source, encoding="utf-8")
        manifest = publisher.read_json(self.root / "player/manifest.json")
        manifest.update(version="1.0.0", data_version=1)
        publisher.write_json(self.root / "player/manifest.json", manifest)
        for page in self.root.rglob("*.html"):
            page.write_text(page.read_text(encoding="utf-8").replace(publisher.MARKER, publisher.LEGACY_MARKER), encoding="utf-8")
        return catalog

    def test_portable_publish_and_defaults(self):
        result = self.publish()
        self.assertEqual(result["slides"], 3)
        self.assertEqual(result["theme"], "programme")
        self.assertEqual(self.catalog()["presentations"][0]["title"], "Доклад <AI> & ideas")
        self.assertTrue(publisher.validate(self.args("validate"))["valid"])
        deck = self.deck()
        self.assertNotIn("slug", deck)
        self.assertEqual(self.catalog()["presentations"][0]["href"], "one/index.html")
        self.assertEqual([p.relative_to(self.root).as_posix() for p in self.root.rglob("*.json")], ["player/manifest.json"])
        self.assertEqual((deck["max_edge"], deck["quality"]), (1440, 55))
        self.assertEqual([(s["width"], s["height"]) for s in deck["slides"]], [(1440, 810), (720, 1440), (810, 1440)])
        for index, slide in enumerate(deck["slides"]):
            with Image.open(self.root / "one" / slide["src"]) as image:
                self.assertEqual(image.format, "WEBP")
                pixel = image.getpixel((image.width // 2, image.height // 2))
                expected_channel = [2, 1, 0][index]
                self.assertEqual(pixel.index(max(pixel)), expected_channel)
        all_text = " ".join(p.read_text(encoding="utf-8") for p in self.root.rglob("*") if p.suffix in (".json", ".html", ".js"))
        self.assertNotIn("SLIDE CONTENT PRIVATE", all_text)
        self.assertNotIn(str(self.source), all_text)
        self.assertFalse(any(p.suffix == ".pdf" for p in self.root.rglob("*")))
        self.assertIn("&lt;AI&gt; &amp; ideas", (self.root / "one/index.html").read_text(encoding="utf-8"))

    def test_current_directory_default_and_slug_fallback(self):
        previous = Path.cwd()
        try:
            os.chdir(self.output.parent)
            result = publisher.publish(self.args("publish", output=False))
            self.assertEqual(Path(result["archive"]), self.base / "presentations")
            self.assertRegex(Path(result["presentation"]).parent.name, r"^deck-[0-9a-f]{8}$")
        finally:
            os.chdir(previous)

    def test_add_replace_preserves_order_metadata_and_player(self):
        self.publish("--speaker", "Alice", "--tag", "AI", "--theme", "field-notes")
        css = self.root / "player/styles.css"
        css.write_text(css.read_text(encoding="utf-8") + "\n/* local customization */\n", encoding="utf-8")
        original_player = snapshot(self.root / "player")
        publisher.publish(self.args("publish", "--slug", "two", "--title", "Second talk"))
        (self.root / "one/extra.txt").write_text("preserve me")
        (self.root / "one/slides/author.txt").write_text("preserve nested file")
        before = snapshot(self.root)
        with self.assertRaisesRegex(publisher.PublishError, "--replace"):
            self.publish()
        self.assertEqual(snapshot(self.root), before)
        self.publish("--replace", "--quality", "40")
        entries = self.catalog()["presentations"]
        self.assertEqual([e["href"] for e in entries], ["two/index.html", "one/index.html"])
        self.assertEqual(entries[1]["speaker"], "Alice")
        self.assertEqual(entries[1]["tags"], ["AI"])
        self.assertEqual(self.catalog()["site"]["theme"], "field-notes")
        self.assertEqual(snapshot(self.root / "player"), original_player)
        self.assertEqual((self.root / "one/extra.txt").read_text(), "preserve me")
        self.assertEqual((self.root / "one/slides/author.txt").read_text(), "preserve nested file")
        self.assertEqual(len(list((self.root / "one/slides").glob("*.webp"))), 3)

    def test_rebuild_metadata_order_and_stale_detection(self):
        self.publish()
        publisher.publish(self.args("publish", "--slug", "two"))
        catalog = self.catalog()
        catalog["presentations"].reverse()
        catalog["presentations"][0]["title"] = "</script><img src=x onerror=alert(1)>"
        catalog["site"].update(title="Archive & talks", theme="screening-room")
        self.save_catalog(catalog)
        with self.assertRaisesRegex(publisher.PublishError, "Stale"):
            publisher.validate(self.args("validate"))
        publisher.rebuild(self.args("rebuild"))
        self.assertTrue(publisher.validate(self.args("validate"))["valid"])
        html = (self.root / "one/index.html").read_text(encoding="utf-8")
        self.assertIn("&lt;/script&gt;&lt;img", html)
        self.assertEqual(self.catalog()["presentations"][0]["href"], "one/index.html")

    def test_player_missing_incompatible_and_refresh(self):
        self.publish()
        manifest = self.root / "player/manifest.json"
        value = publisher.read_json(manifest)
        value["version"] = "0.0.1"
        publisher.write_json(manifest, value)
        before = snapshot(self.root)
        with self.assertRaisesRegex(publisher.PublishError, "--refresh-player"):
            publisher.rebuild(self.args("rebuild"))
        self.assertEqual(snapshot(self.root), before)
        (self.root / "player/custom.txt").write_text("keep")
        publisher.rebuild(self.args("rebuild", "--refresh-player"))
        self.assertEqual((self.root / "player/custom.txt").read_text(), "keep")
        self.assertTrue(publisher.validate(self.args("validate"))["valid"])
        import shutil
        shutil.rmtree(self.root / "player")
        publisher.rebuild(self.args("rebuild"))
        self.assertTrue(publisher.validate(self.args("validate"))["valid"])

    def test_image_settings_cover_and_metadata_fallback(self):
        make_pdf(self.source, title="")
        self.publish("--max-edge", "800", "--quality", "35", "--cover-page", "2")
        self.assertEqual(self.catalog()["presentations"][0]["title"], self.source.stem)
        deck = self.deck()
        self.assertEqual(max(deck["slides"][0]["width"], deck["slides"][0]["height"]), 800)
        with Image.open(self.root / "one/cover.webp") as cover:
            self.assertGreater(cover.height, cover.width)
            self.assertLessEqual(max(cover.size), 640)

    def test_bad_pdfs_and_options_preserve_archive(self):
        self.publish()
        for kind in ("corrupt", "encrypted", "empty"):
            with self.subTest(kind=kind):
                if kind == "corrupt":
                    self.source.write_bytes(b"not a PDF")
                else:
                    make_pdf(self.source, encrypted=kind == "encrypted", pages=() if kind == "empty" else ((640, 360, 0),))
                before = snapshot(self.root)
                with self.assertRaises(publisher.PublishError):
                    self.publish("--replace")
                self.assertEqual(snapshot(self.root), before)
        make_pdf(self.source)
        for extras in (("--cover-page", "20"), ("--date", "2026-02-30"), ("--title", ""), ("--max-edge", "0"), ("--slug", "../escape")):
            with self.subTest(extras=extras):
                before = snapshot(self.root)
                with self.assertRaises(publisher.PublishError):
                    self.publish("--replace", *extras)
                self.assertEqual(snapshot(self.root), before)

    def test_conflicts_are_not_overwritten(self):
        self.root.mkdir(parents=True)
        index = self.root / "index.html"
        index.write_text("unrelated page")
        with self.assertRaisesRegex(publisher.PublishError, "unmanaged"):
            self.publish()
        self.assertEqual(index.read_text(), "unrelated page")
        index.unlink()
        (self.root / "player").mkdir()
        (self.root / "player/custom.txt").write_text("unmanaged")
        with self.assertRaisesRegex(publisher.PublishError, "unmanaged"):
            self.publish("--refresh-player")

    def test_validation_missing_images_paths_and_sources(self):
        self.publish()
        manifest = self.root / "one/deck.js"
        original = manifest.read_bytes()
        deck = self.deck()
        deck["slides"][0]["src"] = "slides/../../outside.webp"
        publisher.write_data(manifest, publisher.DECK_VARIABLE, deck)
        with self.assertRaises(publisher.PublishError):
            publisher.validate(self.args("validate"))
        manifest.write_bytes(original)
        (self.root / "source.pdf").write_bytes(self.source.read_bytes())
        with self.assertRaisesRegex(publisher.PublishError, "source documents"):
            publisher.validate(self.args("validate"))
        (self.root / "source.pdf").unlink()
        deck = self.deck()
        (self.root / "one" / deck["slides"][0]["src"]).unlink()
        with self.assertRaisesRegex(publisher.PublishError, "Missing local asset"):
            publisher.validate(self.args("validate"))

    def test_commit_failure_rolls_back(self):
        self.publish()
        before = snapshot(self.root)
        real_replace = publisher.os.replace
        calls = 0

        def broken_replace(source, target):
            nonlocal calls
            calls += 1
            if calls == 4:
                raise OSError("Simulated disk failure")
            return real_replace(source, target)

        with patch.object(publisher.os, "replace", side_effect=broken_replace):
            with self.assertRaisesRegex(OSError, "Simulated"):
                self.publish("--replace", "--title", "New title")
        self.assertEqual(snapshot(self.root), before)

    def test_cli_failures_return_actionable_exit_code(self):
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            result = publisher.main(["publish", str(self.base / "slides.pptx")])
        self.assertEqual(result, 1)
        self.assertIn("Export PPTX to PDF", errors.getvalue())

    def test_readable_data_and_equivalent_hand_formatting(self):
        self.publish()
        path = self.root / "catalog.js"
        source = path.read_text(encoding="utf-8")
        self.assertIn('\n  "generator":', source)
        self.assertIn("Доклад", source)
        catalog = self.catalog()
        # Header and semicolon are optional; whitespace and object key order do
        # not change the authoritative data or require rebuilding companions.
        path.write_text("\ufeff\nwindow.PDFWebPublisherCatalog = " + json.dumps(catalog, ensure_ascii=False, indent=4), encoding="utf-8")
        before = snapshot(self.root)
        self.assertTrue(publisher.validate(self.args("validate"))["valid"])
        self.assertEqual(snapshot(self.root), before)
        (self.root / "one/deck.js").write_text("window.PDFWebPublisherDeck = " + json.dumps(self.deck(), indent=4) + ";", encoding="utf-8")
        self.assertTrue(publisher.validate(self.args("validate"))["valid"])

    def test_rename_requires_only_folder_and_catalog_link(self):
        self.publish("--speaker", "Alice")
        original = snapshot(self.root / "one")
        (self.root / "one").rename(self.root / "renamed")
        catalog = self.catalog()
        catalog["presentations"][0]["href"] = "renamed/index.html"
        self.save_catalog(catalog)
        self.assertTrue(publisher.validate(self.args("validate"))["valid"])
        self.assertEqual(snapshot(self.root / "renamed"), original)
        publisher.publish(self.args("publish", "--slug", "renamed", "--replace"))
        self.assertEqual(len(self.catalog()["presentations"]), 1)
        self.assertEqual(self.catalog()["presentations"][0]["speaker"], "Alice")
        self.assertNotIn("slug", self.deck("renamed"))

    def test_rebuild_recalculates_summary_from_authoritative_slides(self):
        self.publish()
        deck = self.deck()
        deck["slides"].pop()
        publisher.write_data(self.root / "one/deck.js", publisher.DECK_VARIABLE, deck)
        with self.assertRaisesRegex(publisher.PublishError, "recalculate"):
            publisher.validate(self.args("validate"))
        publisher.rebuild(self.args("rebuild"))
        self.assertEqual(self.catalog()["presentations"][0]["slide_count"], 2)
        self.assertTrue(publisher.validate(self.args("validate"))["valid"])

    def test_malformed_or_executable_data_is_rejected_without_changes(self):
        self.publish()
        path = self.root / "catalog.js"
        original = path.read_text(encoding="utf-8")
        invalid = [original.replace('"site": {', '"site": { // comment'),
                   original.replace('"version": 2', '"version": 2,'),
                   original.replace('"version": 2', '"version": NaN'),
                   original.replace('"version": 2', '"version": 2, "version": 2'),
                   original.replace('"version": 2', "'version': 2"),
                   original + "\nwindow.unexpected = true;", original.replace("window.PDFWebPublisherCatalog", "window.other")]
        for source in invalid:
            with self.subTest(source=source[:40]):
                path.write_text(source, encoding="utf-8")
                before = snapshot(self.root)
                with self.assertRaises(publisher.PublishError):
                    publisher.rebuild(self.args("rebuild"))
                self.assertEqual(snapshot(self.root), before)

    def test_explicit_legacy_migration_and_repeat(self):
        self.make_legacy_archive()
        (self.root / "one/extra.txt").write_text("keep")
        (self.root / "player/custom.txt").write_text("keep")
        before_images = {k: v for k, v in snapshot(self.root).items() if k.endswith(".webp")}
        before = snapshot(self.root)
        for action in (lambda: publisher.validate(self.args("validate")), lambda: self.publish("--replace"),
                       lambda: publisher.rebuild(self.args("rebuild"))):
            with self.assertRaisesRegex(publisher.PublishError, "rebuild --refresh-player"):
                action()
            self.assertEqual(snapshot(self.root), before)
        with patch.object(publisher, "render_pdf", side_effect=AssertionError("Migration must not rasterize PDFs")):
            publisher.rebuild(self.args("rebuild", "--refresh-player"))
        self.assertEqual(self.catalog()["version"], 2)
        self.assertEqual(self.catalog()["presentations"][0]["href"], "one/index.html")
        self.assertEqual(self.catalog()["presentations"][0]["cover"], "cover.webp")
        self.assertEqual(self.catalog()["presentations"][0]["speaker"], "Alice")
        self.assertNotIn("slug", self.deck())
        self.assertFalse((self.root / "presentations.json").exists())
        self.assertFalse((self.root / "one/deck.json").exists())
        self.assertEqual({k: v for k, v in snapshot(self.root).items() if k.endswith(".webp")}, before_images)
        self.assertEqual((self.root / "one/extra.txt").read_text(), "keep")
        self.assertEqual((self.root / "player/custom.txt").read_text(), "keep")
        self.assertTrue(publisher.validate(self.args("validate"))["valid"])
        after = snapshot(self.root)
        publisher.rebuild(self.args("rebuild", "--refresh-player"))
        self.assertEqual(snapshot(self.root), after)

    def test_legacy_removal_failure_rolls_back_entire_migration(self):
        self.make_legacy_archive()
        before = snapshot(self.root)
        real_rename = Path.rename

        def failing_remove(source, target):
            if source.name == "deck.json" and Path(target).name.startswith("removed-"):
                raise OSError("Simulated removal failure")
            return real_rename(source, target)

        with patch.object(Path, "rename", failing_remove):
            with self.assertRaisesRegex(OSError, "removal failure"):
                publisher.rebuild(self.args("rebuild", "--refresh-player"))
        self.assertEqual(snapshot(self.root), before)

    def test_migration_converts_unlisted_managed_decks_and_preserves_other_json(self):
        import shutil
        self.make_legacy_archive()
        shutil.copytree(self.root / "one", self.root / "unlisted")
        path = self.root / "unlisted/deck.json"
        value = publisher.read_json(path)
        value["slug"] = "unlisted"
        publisher.write_json(path, value)
        (path.with_suffix(".js")).write_text(publisher.js_data(publisher.DECK_VARIABLE, value).replace(publisher.MARKER, publisher.LEGACY_MARKER), encoding="utf-8")
        unrelated = self.root / "notes/deck.json"
        publisher.write_json(unrelated, {"note": "unrelated data"})
        before = unrelated.read_bytes()
        publisher.rebuild(self.args("rebuild", "--refresh-player"))
        self.assertEqual(len(self.catalog()["presentations"]), 1)
        self.assertFalse(path.exists())
        self.assertNotIn("slug", self.deck("unlisted"))
        self.assertEqual(unrelated.read_bytes(), before)
        self.assertTrue(publisher.validate(self.args("validate"))["valid"])

    def test_migration_refuses_to_overwrite_new_format_catalog_edits(self):
        self.make_legacy_archive()
        catalog = self.catalog()
        catalog["version"] = 2
        catalog["site"]["title"] = "A version-2 edit that must survive"
        entry = catalog["presentations"][0]
        entry["href"] = entry.pop("slug") + "/index.html"
        entry["cover"] = "cover.webp"
        self.save_catalog(catalog)
        before = snapshot(self.root)
        with self.assertRaises(publisher.PublishError):
            publisher.rebuild(self.args("rebuild", "--refresh-player"))
        self.assertEqual(snapshot(self.root), before)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--preview":
        make_preview(Path(sys.argv[2]))
    else:
        unittest.main()
