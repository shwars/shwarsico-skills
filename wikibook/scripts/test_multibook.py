import json
from pathlib import Path
import unittest
from unittest.mock import patch
import yaml

import authoring
import card_migration
import fb2_sources
import test_wiki
import wiki


class MultiBookTests(unittest.TestCase):
    setUp = test_wiki.WikiTests.setUp
    tearDown = test_wiki.WikiTests.tearDown

    def test_migration_rewrites_softwrapped_yaml_scalars_and_fact_links(self):
        directory = self.root/'wiki/protagonists'
        directory.mkdir(parents=True)
        old = directory/'Очень длинное читаемое имя исторического персонажа.hist.md'
        new = old.with_name(old.name.replace('.hist.md', '.book2.md'))
        old.write_text('old', encoding='utf-8')
        page = self.root/'wiki/example.md'
        value = ('[[wiki/protagonists/' + old.stem + '#^anchor|Подпись ссылки]]')
        metadata = yaml.safe_dump({'reference': value}, allow_unicode=True, width=35, default_style='"')
        facts = yaml.safe_dump({'facts': [{'sources': [value]}]}, allow_unicode=True, width=35, default_style='"')
        self.assertIn('\\\n', metadata)
        text = '---\n'+metadata+'---\nРучной текст сохраняется.\n~~~yaml\n'+facts+'~~~\n'
        updated = card_migration.rewrite(text, page, old, new, self.root)
        self.assertNotEqual(text, updated)
        front = card_migration.YAML_FRONTMATTER.match(updated)
        fence = card_migration.YAML_FENCE.search(updated)
        expected = value.replace('.hist#', '.book2#')
        self.assertEqual(yaml.safe_load(front.group(1))['reference'], expected)
        self.assertEqual(yaml.safe_load(fence.group('body'))['facts'][0]['sources'], [expected])
        self.assertIn('Ручной текст сохраняется.', updated)
        self.assertEqual(card_migration.rewrite(updated, page, old, new, self.root), updated)

    def test_multipart_notes_titles_progress_and_changed_edition(self):
        source = test_wiki.SOURCE.replace('<body><section>', '<body><title><p>Общий титул</p></title><section>', 1)
        # Distinct physical parts both restart at chapter/note one.
        source = source.replace('<section><title><p>Часть II</p></title>\n   <section><title><p>I. Снова первая</p></title><p>Продолжение.</p></section>\n  </section>', '')
        second = self.source.with_name('second.fb2')
        self.source.write_text(source, encoding='utf-8')
        second.write_text(source, encoding='utf-8')
        # Physical input scopes take precedence over nested part labels.
        second.write_text(source.replace('Часть I', 'Часть II'), encoding='utf-8')
        wiki.prepare('book2', [self.source, second])
        manifest = wiki.load_manifest('book2')
        self.assertEqual([u['id'] for u in manifest['units']],
                         ['p01-frontmatter', 'p01-ch01', 'p02-frontmatter', 'p02-ch01'])
        self.assertEqual([n['id'] for n in manifest['notes']], ['p01-n-1', 'p02-n-1'])
        self.assertIn('#^p02-n-1', manifest['units'][3]['blocks'][0]['markdown'])
        self.assertEqual(len(manifest['source_files']), 2)
        self.assertEqual(manifest['fingerprint_kind'], 'ordered-source-set')
        wiki.set_progress('book2', 'p01-ch01', read=True)
        before = (self.root/'source/book2/manifest.json').read_bytes()
        wiki.prepare('book2', [self.source, second])
        self.assertEqual(before, (self.root/'source/book2/manifest.json').read_bytes())
        self.assertTrue(json.loads((self.root/'source/book2/progress.json').read_text(encoding='utf-8'))['units']['p01-ch01']['read'])
        second.write_text(second.read_text(encoding='utf-8').replace('Начало', 'Изменённое начало'), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Source changed'):
            wiki.prepare('book2', [self.source, second])

    def test_volume_hierarchy_and_alternative_note_ids(self):
        source = test_wiki.SOURCE.replace('n_1', 'note1')
        source = source.replace('<title><p>Книга</p></title>', '<title><p>ТОМ I</p></title>')
        source = source.replace('Часть I', 'ЧАСТЬ I').replace('Часть II', 'ЧАСТЬ II')
        self.source.write_text(source, encoding='utf-8')
        manifest = wiki.parse_fb2(self.source, 'nested')
        self.assertEqual([u['id'] for u in manifest['units']], ['v01-p01-ch01', 'v01-p02-ch01'])
        self.assertIn('notes#^note1', manifest['units'][0]['blocks'][0]['markdown'])

    def test_prepared_anchor_and_source_hash_damage_is_rejected_without_cards(self):
        wiki.prepare('test')
        self.assertEqual(wiki.validate_sources(), [])
        note=self.root/'source/test/notes.md'
        note.write_text(note.read_text(encoding='utf-8').replace('^n-1','^missing'),encoding='utf-8')
        unit=self.root/'source/test/bychapter/p01-ch01.md'
        unit.write_text(unit.read_text(encoding='utf-8').replace('^b0001','^b0999'),encoding='utf-8')
        self.source.write_text(test_wiki.SOURCE.replace('Начало','Изменение'),encoding='utf-8')
        errors=wiki.validate_sources()
        self.assertTrue(any('hash mismatch' in error for error in errors))
        self.assertTrue(any('note anchors' in error for error in errors))
        self.assertTrue(any('block anchors differ' in error for error in errors))

    def history_person(self):
        wiki.prepare('test')
        return wiki.create_card(
            {'entity_id': 'Историк Пример', 'type': 'character', 'first_source': 'hist', 'book_ids': []},
            {'Исторический контекст — не из романа': 'Историческое описание сохраняется.'},
            [{'fact_id': 'Историк Пример/факт-001', 'subject': 'Историк Пример',
              'predicate': 'description', 'scope': 'canon', 'evidence_type': 'narrator',
              'truth_status': 'confirmed', 'value': 'Прямое упоминание',
              'sources': [wiki.ref('test', 'p01-ch01', 'b0001')]}])

    def test_promotion_rewrites_vault_links_preserves_ids_and_rebuilds(self):
        old = self.history_person()
        authoring.revise('Историк Пример', metadata={
            'self_link': '[[wiki/protagonists/Историк Пример.hist|Собственная карточка]]'})
        page = self.root/'wiki/other/page.md';page.parent.mkdir(parents=True)
        text = '''---
related: "[[wiki/protagonists/Историк Пример.hist#^anchor|Подпись]]"
---
![[Историк Пример.hist]]
[Читать](<../protagonists/Историк Пример.hist.md#Раздел>)
[Код](../protagonists/%D0%98%D1%81%D1%82%D0%BE%D1%80%D0%B8%D0%BA%20%D0%9F%D1%80%D0%B8%D0%BC%D0%B5%D1%80.hist.md#x)
[ref]: <../protagonists/Историк Пример.hist.md#x> "Заголовок"
Проза: Историк Пример.hist.md
[Внешняя](https://example.org/Историк.hist.md)
'''
        page.write_text(text, encoding='utf-8')
        preview = card_migration.promote(wiki, 'Историк Пример', 'test')
        self.assertEqual(preview['status'], 'dry-run')
        self.assertTrue(old.exists());self.assertEqual(page.read_text(encoding='utf-8'), text)
        result = card_migration.promote(wiki, 'Историк Пример', 'test', apply=True)
        new = Path(result['new_path']);self.assertTrue(new.exists());self.assertFalse(old.exists())
        content = page.read_text(encoding='utf-8')
        self.assertIn('Пример.test#^anchor|Подпись', content)
        self.assertIn('![[Историк Пример.test]]', content)
        self.assertIn('Пример.test.md#Раздел>', content)
        self.assertIn('%D1%80.test.md#x', content)
        self.assertIn('Проза: Историк Пример.hist.md', content)
        card = wiki.parse_card(new)
        self.assertEqual(card['facts'][0]['fact_id'], 'Историк Пример/факт-001')
        self.assertIn('Историческое описание сохраняется.', card['body'])
        self.assertEqual(card['metadata']['first_source'], 'test')
        self.assertEqual(card['metadata']['book_ids'], ['test'])
        self.assertEqual(card['metadata']['self_link'],
                         '[[wiki/protagonists/Историк Пример.test|Собственная карточка]]')
        self.assertEqual(card_migration.promote(wiki, 'Историк Пример', 'test', apply=True)['status'], 'already-promoted')
        before = new.read_bytes();wiki.build();self.assertEqual(before, new.read_bytes())

    def test_promotion_refuses_collision_and_missing_main_text_evidence(self):
        old = self.history_person()
        collision = old.with_name('Историк Пример.test.md')
        wiki.create_card({'entity_id': 'Другой человек', 'type': 'character', 'first_source': 'test'},
                         {'Описание': 'Другой'}, [], filename=collision.name)
        with self.assertRaisesRegex(ValueError, 'collision'):
            card_migration.promote(wiki, 'Историк Пример', 'test', apply=True)
        self.assertTrue(old.exists())
        collision.unlink()
        text = old.read_text(encoding='utf-8').replace('scope: canon', 'scope: editorial')
        old.write_text(text, encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'main-text evidence'):
            card_migration.promote(wiki, 'Историк Пример', 'test', apply=True)

    def test_later_books_extend_one_card_and_keep_separate_visible_sections(self):
        wiki.prepare('test');person = test_wiki.WikiTests.create_person(self)
        wiki.prepare('later', self.source)
        with patch.object(authoring, 'BOOK_ID', 'later'):
            authoring.add_facts('Персонаж', [dict(predicate='appearance', unit='p01-ch01', blocks=[1], value='Поздний облик')])
        wiki.build()
        self.assertEqual(len(wiki.cards()), 1)
        c = wiki.parse_card(person)
        self.assertEqual(c['metadata']['first_source'], 'test')
        self.assertEqual(set(c['metadata']['book_ids']), {'test', 'later'})
        self.assertIn('Далее из другой книги: Тест', c['body'])
        self.assertIn('Поздний облик', c['body'])
        first_ids = [f['fact_id'] for f in c['facts']]
        with patch.object(authoring, 'BOOK_ID', 'later'):
            authoring.add_facts('Персонаж', [dict(predicate='appearance', unit='p01-ch01', blocks=[1], value='Поздний облик')])
        self.assertEqual([f['fact_id'] for f in wiki.parse_card(person)['facts']], first_ids)

    def test_validation_requires_promoting_a_history_person_with_novel_evidence(self):
        person = self.history_person()
        self.assertTrue(any('promote-person required' in error for error in wiki.validate()[0]))
        before = person.read_bytes()
        with self.assertRaisesRegex(ValueError, 'validation errors'):
            wiki.build()
        self.assertEqual(person.read_bytes(), before)

    def test_text_proven_anonymous_person_merge_keeps_one_card_and_old_fact_ids(self):
        wiki.prepare('test');person = test_wiki.WikiTests.create_person(self)
        duplicate = wiki.create_card(
            {'entity_id': 'Седой лакей', 'type': 'character', 'first_source': 'test'},
            {'До узнавания': 'Ручное наблюдение за лакеем.'},
            [dict(fact_id='Седой лакей/факт-001', subject='Седой лакей', predicate='appearance',
                  value='Седой', scope='canon', evidence_type='narrator', truth_status='confirmed',
                  sources=[wiki.ref('test','p01-ch01','b0001')])])
        page=self.root/'index.md';page.write_text('[[wiki/protagonists/Седой лакей.test|Слуга]]',encoding='utf-8')
        card_migration.merge_people(wiki,'Персонаж','Седой лакей',
            identity_sources=[wiki.ref('test','p02-ch01','b0001')],explanation='Рассказчик прямо называет того же слугу.')
        self.assertFalse(duplicate.exists());self.assertEqual(len(wiki.cards()),1)
        card=wiki.parse_card(person)
        self.assertIn('Седой лакей/факт-001',[f['fact_id'] for f in card['facts']])
        self.assertTrue(all(f['subject']=='Персонаж' for f in card['facts']))
        self.assertIn('Ручное наблюдение',card['body'])
        self.assertIn('[[wiki/protagonists/Персонаж.test|Слуга]]',page.read_text(encoding='utf-8'))
        self.assertEqual(wiki.validate()[0],[])

    def test_arbitrary_book_ids_and_order_without_special_title_rules(self):
        result = fb2_sources.combine([self.source], 'newbook', title='Новая книга', series_order=0)
        self.assertEqual(result['title'], 'Новая книга')
        self.assertEqual(result['series_order'], 0)
        self.assertEqual([u['id'] for u in result['units']], ['p01-ch01', 'p02-ch01'])


if __name__ == '__main__':
    unittest.main()
