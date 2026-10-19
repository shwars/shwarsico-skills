import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import wiki
import authoring


SOURCE = """<?xml version="1.0" encoding="utf-8"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"
 xmlns:xlink="http://www.w3.org/1999/xlink">
 <description><title-info><book-title>Тест</book-title></title-info></description>
 <body><section><title><p>Книга</p></title>
  <section><title><p>Часть I</p></title>
   <section><title><p>I. Первая</p></title>
    <p>Начало <a type="note" xlink:href="#n_1">[1]</a>.</p>
    <cite><p>Письмо.</p><text-author>Автор</text-author></cite>
    <poem><stanza><v>Стих один</v><v>Стих два</v></stanza></poem>
   </section>
  </section>
  <section><title><p>Часть II</p></title>
   <section><title><p>I. Снова первая</p></title><p>Продолжение.</p></section>
  </section>
 </section></body>
 <body name="notes"><section id="n_1"><title><p>1</p></title><p>Пояснение.</p></section></body>
</FictionBook>"""


class WikiTests(unittest.TestCase):
    def setUp(self):
        self.authoring_patches = [patch.object(authoring, field, None)
                                  for field in ('BOOK_ID', 'BOOK_TITLE', 'BOOK_ROOT')]
        for item in self.authoring_patches:
            item.start()
        self.temp_base = Path(__file__).resolve().parent / ".test-tmp"
        self.temp_base.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=self.temp_base)
        self.root = Path(self.temp.name)
        self.assertTrue(self.root.resolve().is_relative_to(self.temp_base.resolve()))
        self.patch_root = patch.object(wiki, "ROOT", self.root)
        self.patch_wiki = patch.object(wiki, "WIKI", self.root / "wiki")
        self.patch_root.start()
        self.patch_wiki.start()
        self.source = self.root / "source" / "test.fb2"
        self.source.parent.mkdir()
        self.source.write_text(SOURCE, encoding="utf-8")

    def tearDown(self):
        for item in reversed(self.authoring_patches):
            item.stop()
        self.patch_wiki.stop()
        self.patch_root.stop()
        self.assertTrue(self.root.resolve().is_relative_to(self.temp_base.resolve()))
        self.temp.cleanup()

    def test_preparation_preserves_all_atoms_and_distinguishes_parts(self):
        manifest = wiki.parse_fb2(self.source, "test")
        self.assertEqual([u["id"] for u in manifest["units"]], ["p01-ch01", "p02-ch01"])
        self.assertEqual([b["kind"] for b in manifest["units"][0]["blocks"]],
                         ["p", "p", "text-author", "v", "v"])
        self.assertEqual(manifest["notes"][0]["blocks"], ["Пояснение."])
        self.assertIn("[[source/test/notes#^n-1|[1]]]",
                      manifest["units"][0]["blocks"][0]["markdown"])
        before = self.source.read_bytes()
        wiki.prepare("test")
        wiki.set_progress("test", "p01-ch01", read=True, summary="Прочитано")
        files_before = {p.name: p.read_bytes() for p in (self.root / "source/test/bychapter").glob("*.md")}
        wiki.prepare("test")
        files_after = {p.name: p.read_bytes() for p in (self.root / "source/test/bychapter").glob("*.md")}
        self.assertEqual(before, self.source.read_bytes())
        self.assertEqual(files_before, files_after)
        progress = json.loads((self.root / "source/test/progress.json").read_text(encoding="utf-8"))
        self.assertTrue(progress["units"]["p01-ch01"]["read"])
        self.source.write_text(SOURCE.replace("Продолжение.", "Другой текст."), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Source changed"):
            wiki.prepare("test")

    def create_person(self):
        return wiki.create_card(
            {"entity_id": "Персонаж", "type": "character", "first_source": "test",
             "book_ids": ["test"]},
            {"Кто это": "Ручной текст, который нельзя затирать."},
            [{"fact_id": "Персонаж/факт-001", "subject": "Персонаж",
              "predicate": "description", "value": "Описание", "scope": "canon",
              "evidence_type": "narrator", "truth_status": "confirmed",
              "sources": [wiki.ref("test", "p01-ch01", "b0001")]}])

    def test_event_projection_accepts_literal_obstacle(self):
        card = {"metadata": {"entity_id": "Преграда", "type": "event"},
                "facts": [{"fact_id": "Преграда/факт-001", "subject": "Преграда",
                           "predicate": "prevents", "value": "Неадресованный план отхода",
                           "scope": "analysis", "evidence_type": "inference",
                           "truth_status": "confirmed", "sources": ["Подтверждение"]}]}
        rendered = wiki.generated_body(card, {"Преграда": card}, {"Преграда": []})
        self.assertIn("Неадресованный план отхода", rendered)
        self.assertIn("вывод анализа", rendered)
        self.assertIn("Подтверждение", rendered)

    def test_repeated_build_preserves_authoring_and_reverse_links(self):
        wiki.prepare("test")
        wiki.build()
        person = self.create_person()
        wiki.create_card(
            {"entity_id": "Событие", "type": "event", "first_source": "test",
             "book_ids": ["test"], "date_text": "Не установлена", "event_status": "occurred"},
            {"Что произошло": "Авторское описание события."},
            [{"fact_id": "Событие/факт-001", "subject": "Событие",
              "predicate": "participates", "object": "Персонаж", "scope": "canon",
              "evidence_type": "action", "truth_status": "confirmed",
              "sources": [wiki.ref("test", "p01-ch01", "b0001")]}],
            [{"book_id": "test", "unit_id": "p01-ch01", "block_id": "b0001", "kind": "действие"}],
            filename="undated--Событие.test.md")
        wiki.build()
        initial = person.read_bytes()
        self.assertIn("Ручной текст, который нельзя затирать.", initial.decode("utf-8"))
        self.assertIn("undated--Событие.test", initial.decode("utf-8"))
        wiki.build()
        self.assertEqual(initial, person.read_bytes())
        self.assertEqual(wiki.validate()[0], [])
        with self.assertRaisesRegex(ValueError, "Entity already"):
            self.create_person()

    def test_invalid_evidence_and_canonical_reference_are_rejected(self):
        wiki.prepare("test")
        wiki.build()
        person = self.create_person()
        text = person.read_text(encoding="utf-8").replace("#^b0001", "#^b0999")
        person.write_text(text, encoding="utf-8")
        self.assertTrue(any("Missing block" in e for e in wiki.validate()[0]))
        with self.assertRaisesRegex(ValueError, "validation errors"):
            wiki.build()

    def test_reported_event_and_later_profile_evidence_remain_visible(self):
        wiki.prepare("test")
        person = self.create_person()
        with patch.object(authoring, "BOOK_ID", "test"), patch.object(authoring, "BOOK_TITLE", "Тест"):
            authoring.add_facts("Персонаж", [
                {"unit": "p02-ch01", "blocks": [1], "predicate": "appearance", "value": "Новая внешность"},
                {"unit": "p02-ch01", "blocks": [1], "predicate": "believes", "value": "Ошибочная версия",
                 "truth_status": "refuted"},
            ])
            authoring.event("Сообщённое событие", "p01-ch01", [1], "По словам свидетеля произошло событие.",
                            participants=["Персонаж"], status="reported", occurrence_kind="ретроспекция",
                            dates={"prefix": "undated", "date_min": None, "date_max": None,
                                   "date_precision": "unknown", "date_text": "Не установлена"})
        wiki.build()
        text = person.read_text(encoding="utf-8")
        self.assertIn("### Внешность", text)
        self.assertIn("Новая внешность", text)
        self.assertIn("Убеждение: Ошибочная версия (опровергнуто)", text)
        self.assertIn("[[source/test/bychapter/p02-ch01#^b0001]]", text)
        event = next(c for c in wiki.cards() if c["metadata"]["entity_id"] == "Сообщённое событие")
        self.assertEqual(event["metadata"]["event_status"], "reported")
        self.assertTrue(all(f["truth_status"] == "claimed" and f["evidence_type"] == "testimony"
                            for f in event["facts"]))
        self.assertEqual(event["occurrences"][0]["kind"], "ретроспекция")
        first = person.read_bytes()
        wiki.build()
        self.assertEqual(first, person.read_bytes())

    def test_source_shape_and_hash_without_external_books(self):
        result = wiki.parse_fb2(self.source, "sample")
        self.assertEqual(len(result["units"]), 2)
        self.assertEqual(len(result["notes"]), 1)
        self.assertEqual(result["source_sha256"], hashlib.sha256(self.source.read_bytes()).hexdigest())

    def test_authoring_batch_updates_index_and_rechecks_external_edits_after_exit(self):
        wiki.prepare('test')
        with wiki.authoring_batch():
            person = self.create_person()
            self.assertEqual(len(wiki.cards()), 1)
            with self.assertRaisesRegex(ValueError, 'Entity already'):
                self.create_person()
            with patch.object(authoring, 'BOOK_ID', 'test'):
                authoring.add_facts('Персонаж', [dict(unit='p01-ch01', blocks=[1],
                                                    predicate='trait', value='Смелость')])
            self.assertEqual(len(wiki.cards()[0]['facts']), 2)
        person.write_text(person.read_text(encoding='utf-8').replace('Смелость', 'Осторожность'),
                          encoding='utf-8')
        self.assertEqual(wiki.cards()[0]['facts'][-1]['value'], 'Осторожность')


if __name__ == "__main__":
    unittest.main()
