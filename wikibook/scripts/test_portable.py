"""Portable end-to-end checks; all books and vaults are synthetic and temporary."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

import authoring as a
import card_migration
import fb2_sources
import test_wiki
import wiki


UNKNOWN = dict(prefix="undated", date_min=None, date_max=None,
               date_precision="unknown", date_text="Год не установлен")


def novel(title, paragraphs):
    from xml.sax.saxutils import escape
    body = ''.join('<p>' + escape(p) + '</p>' for p in paragraphs)
    return ('<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
            '<description><title-info><book-title>' + escape(title) + '</book-title>'
            '</title-info></description><body><section><title><p>Часть I</p></title>'
            '<section><title><p>Глава 1</p></title>' + body +
            '</section></section></body></FictionBook>')


class PortableTests(unittest.TestCase):
    setUp = test_wiki.WikiTests.setUp
    tearDown = test_wiki.WikiTests.tearDown

    def test_cli_copied_package_runs_outside_repository_with_explicit_root(self):
        package = self.root / 'отдельный скилл' / 'scripts'
        package.mkdir(parents=True)
        for name in ('wiki.py', 'authoring.py', 'fb2_sources.py', 'card_migration.py'):
            shutil.copy2(Path(__file__).parent / name, package / name)
        elsewhere = self.root / 'другой рабочий каталог'
        elsewhere.mkdir()
        def cli(*args):
            result = subprocess.run([sys.executable, str(package / 'wiki.py'), '--root',
                                     str(self.root), *args], cwd=elsewhere,
                                    env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
                                    capture_output=True, text=True, encoding='utf-8', timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result.stdout
        cli('prepare', '--book-id', 'arbitrary', '--input', str(self.source),
            '--title', 'Произвольный роман', '--series-order', '7')
        cli('prepare', '--book-id', 'arbitrary', '--input', str(self.source))
        manifest = wiki.load_manifest('arbitrary')
        self.assertEqual((manifest['title'], manifest['series_order']), ('Произвольный роман', 7))
        self.assertIn('[b0001]', cli('read', 'p01-ch01', '--book-id', 'arbitrary', '--first', '1', '--last', '1'))
        self.assertIn('Письмо', cli('search', 'Письмо', '--book-id', 'arbitrary'))
        self.assertIn('next unit: p01-ch01', cli('status', '--book-id', 'arbitrary'))
        cli('build')
        cli('validate')
        self.assertFalse((elsewhere / 'wiki').exists())
        self.assertFalse((package / 'wiki').exists())

    def test_multipart_colliding_structures_get_physical_file_scope(self):
        second = self.source.with_name('second.fb2')
        second.write_bytes(self.source.read_bytes())
        wiki.prepare('multipart', [self.source, second])
        result = wiki.load_manifest('multipart')
        self.assertEqual([u['id'] for u in result['units']],
                         ['s01-p01-ch01', 's01-p02-ch01', 's02-p01-ch01', 's02-p02-ch01'])
        self.assertEqual([n['id'] for n in result['notes']], ['p01-n-1', 'p02-n-1'])
        before = (self.root/'source/multipart/manifest.json').read_bytes()
        wiki.prepare('multipart', [self.source, second])
        self.assertEqual(before, (self.root/'source/multipart/manifest.json').read_bytes())

    def test_english_hierarchy_and_multiple_main_bodies_preserve_text(self):
        text = test_wiki.SOURCE.replace('Книга', 'Volume I').replace('Часть I', 'PART I').replace('Часть II', 'PART II')
        text = text.replace('</FictionBook>', '<body><section><title><p>Afterword</p></title>'
                            '<p>Additional main body.</p></section></body></FictionBook>')
        self.source.write_text(text, encoding='utf-8')
        result = fb2_sources.parse(self.source, 'english')
        self.assertEqual([u['id'] for u in result['units'][:2]], ['v01-p01-ch01', 'v01-p02-ch01'])
        self.assertEqual(result['units'][-1]['blocks'][0]['text'], 'Additional main body.')

    def test_atomic_write_failure_preserves_previous_file(self):
        target = self.root / 'state.json'
        wiki.write_json(target, {'version': 1})
        before = target.read_bytes()
        with patch.object(wiki.os, 'replace', side_effect=OSError('simulated interruption')):
            with self.assertRaises(OSError):
                wiki.write_json(target, {'version': 2})
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual(list(self.root.glob('.wikibook-*')), [])

    def test_prepared_text_damage_detected_even_with_valid_anchor(self):
        wiki.prepare('sample', self.source)
        page = self.root / 'source/sample/bychapter/p01-ch01.md'
        page.write_text(page.read_text(encoding='utf-8').replace('Письмо.', 'Подмена.'), encoding='utf-8')
        self.assertTrue(any('Prepared block text differs' in e for e in wiki.validate_sources()))

    def test_coverage_requires_actual_stages_and_audit_record(self):
        wiki.prepare('sample', self.source)
        progress = self.root / 'source/sample/progress.json'
        before = progress.read_bytes()
        with self.assertRaises(ValueError):
            wiki.set_progress('sample', 'p01-ch01', extracted=True)
        with self.assertRaises(ValueError):
            wiki.set_progress('sample', 'p01-ch01', read=True, extracted=True, audited=True)
        self.assertEqual(progress.read_bytes(), before)
        wiki.set_progress('sample', 'p01-ch01', read=True, extracted=True)
        wiki.set_progress('sample', 'p01-ch01', audited=True, audit_date='2026-10-19',
                          audit_summary='Сверена тестовая глава.', audit_method='Повторное чтение')
        self.assertTrue(json.loads(progress.read_text(encoding='utf-8'))['units']['p01-ch01']['audited'])

    def test_configuration_switch_clears_identity_index(self):
        wiki.prepare('sample', self.source)
        a.set_book('sample')
        a.concept('Первый', 'character', 'p01-ch01', [1], 'Первый человек')
        original_root = wiki.ROOT
        second_root = self.root / 'another'
        try:
            wiki.configure(second_root)
            self.assertEqual(wiki.cards(), [])
            with wiki.authoring_batch():
                with self.assertRaises(ValueError):
                    wiki.configure(original_root)
        finally:
            wiki.configure(original_root)
        self.assertEqual(wiki.cards()[0]['metadata']['entity_id'], 'Первый')

    def test_complete_cycle_shared_person_false_claim_plan_and_history_promotion(self):
        first = self.source
        first.write_text(novel('Начало', [
            'Софья — посланница. Пришёл гость.',
            'Гость сказал, что Софья погибла вчера.',
            'Софья вошла живой; гость солгал о её смерти.',
            'Софья задумала бегство, но ещё не бежала.',
            'Софья передала письмо гостю. Год не назван.',
        ]), encoding='utf-8')
        later = self.source.with_name('later.fb2')
        later.write_text(novel('Продолжение', [
            'Софья, теперь в синем плаще, встретила историка Льва.',
            'Она вспомнила, как передала письмо гостю.',
        ]), encoding='utf-8')
        originals = (first.read_bytes(), later.read_bytes())
        wiki.prepare('first', first, series_order=1)
        a.set_book('first')
        with wiki.authoring_batch():
            a.concept('Софья', 'character', 'p01-ch01', [1], 'Посланница; внешность пока не описана.')
            a.concept('Гость', 'character', 'p01-ch01', [1], 'Пришедший гость.')
            a.event('Предполагаемая гибель Софьи', 'p01-ch01', [2], 'По словам гостя Софья погибла.',
                    participants=['Софья'], dates=UNKNOWN, status='reported', occurrence_kind='свидетельство')
            a.event('План бегства Софьи', 'p01-ch01', [4], 'Бегство задумано, исполнения нет.',
                    participants=['Софья'], dates=UNKNOWN, status='planned', occurrence_kind='план')
            a.event('Передача письма', 'p01-ch01', [5], 'Софья передала письмо гостю.',
                    participants=['Софья', 'Гость'], dates=UNKNOWN)
        claim = next(c for c in wiki.cards() if c['metadata']['entity_id'] == 'Предполагаемая гибель Софьи')
        facts = [dict(f, truth_status='refuted', asserted_by='Гость',
                      sources=f['sources']+[wiki.ref('first', 'p01-ch01', 'b0003')]) for f in claim['facts']]
        a.revise('Предполагаемая гибель Софьи', metadata={'event_status': 'refuted'}, facts=facts)
        history = wiki.create_card(dict(entity_id='Историк Лев', type='character', first_source='hist'),
            {'Исторический контекст — не из романа': 'Синтетическая справка для теста.'},
            [dict(fact_id='Историк Лев/факт-001', subject='Историк Лев', predicate='historical_context',
                  value='Синтетическая справка.', scope='history', evidence_type='web',
                  truth_status='confirmed', sources=['https://example.org/test-context'])])
        wiki.set_progress('first', 'p01-ch01', read=True, extracted=True)
        wiki.set_progress('first', 'p01-ch01', audited=True, audit_date='2026-10-19',
                          audit_summary='Ложное свидетельство опровергнуто, исполнение плана не приписано.',
                          audit_method='Сверка с полным синтетическим источником')
        wiki.build()
        person_path = next(c['path'] for c in wiki.cards() if c['metadata']['entity_id'] == 'Софья')
        initial_ids = {f['fact_id'] for c in wiki.cards() for f in c['facts']}
        wiki.prepare('later', later, series_order=2)
        a.set_book('later')
        a.add_facts('Софья', [dict(unit='p01-ch01', blocks=[1], predicate='appearance', value='Синий плащ')])
        a.add_facts('Историк Лев', [dict(unit='p01-ch01', blocks=[1], predicate='role', value='Историк')])
        a.appearance('Передача письма', 'p01-ch01', 2, 'воспоминание')
        preview = card_migration.promote(wiki, 'Историк Лев', 'later')
        self.assertTrue(history.exists())
        self.assertEqual(preview['status'], 'dry-run')
        card_migration.promote(wiki, 'Историк Лев', 'later', apply=True)
        self.assertFalse(history.exists())
        self.assertEqual(person_path, next(c['path'] for c in wiki.cards() if c['metadata']['entity_id'] == 'Софья'))
        self.assertIn('Далее из другой книги: Продолжение', person_path.read_text(encoding='utf-8'))
        self.assertTrue(initial_ids <= {f['fact_id'] for c in wiki.cards() for f in c['facts']})
        self.assertEqual(wiki.validate()[0], [])
        calendar = (wiki.WIKI / 'cal-timeline.md').read_text(encoding='utf-8')
        undated, unconfirmed = calendar.split('## Сообщения, планы и спорные версии')
        self.assertNotIn('План бегства Софьи', undated)
        self.assertNotIn('Предполагаемая гибель Софьи', undated)
        self.assertIn('План бегства Софьи', unconfirmed)
        self.assertIn('Предполагаемая гибель Софьи', unconfirmed)
        plan = next(c for c in wiki.cards() if c['metadata']['entity_id'] == 'План бегства Софьи')
        self.assertTrue(all(f['truth_status'] == 'unknown' for f in plan['facts']))
        graph = json.loads((wiki.WIKI / 'graph.json').read_text(encoding='utf-8'))
        self.assertEqual([b['book_id'] for b in graph['books']], ['first', 'later'])
        self.assertEqual(len([o for o in graph['occurrences'] if o['event_id']=='Передача письма']), 2)
        before = {p.relative_to(wiki.WIKI): p.read_bytes() for p in wiki.WIKI.rglob('*') if p.is_file()}
        wiki.build()
        after = {p.relative_to(wiki.WIKI): p.read_bytes() for p in wiki.WIKI.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual((first.read_bytes(), later.read_bytes()), originals)

    def test_card_examples_are_valid_in_an_isolated_demo_vault(self):
        wiki.prepare('demo', self.source)
        assets = Path(__file__).resolve().parents[1] / 'assets'
        for source, folder, name in [('character.example.md', 'protagonists', 'Софья.demo.md'),
                                     ('event.example.md', 'events', 'undated--Софья получает письмо.demo.md')]:
            destination = wiki.WIKI / folder / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(assets / source, destination)
        self.assertEqual(wiki.validate()[0], [])
        wiki.build()

    def test_identity_merge_preview_repeat_and_write_failure_rollback(self):
        wiki.prepare('sample', self.source)
        a.set_book('sample')
        keep = a.concept('Софья', 'character', 'p01-ch01', [1], 'Известная посланница.')
        a.concept('Незнакомка у ворот', 'character', 'p01-ch01', [2], 'Та же женщина до узнавания.')
        index = self.root / 'index.md'
        index.write_text('[[wiki/protagonists/Незнакомка у ворот.sample|Посланница]]', encoding='utf-8')
        kwargs = dict(identity_sources=[wiki.ref('sample', 'p01-ch01', 'b0003')],
                      explanation='Синтетический пример прямого узнавания.')
        before = {p: p.read_bytes() for p in self.root.rglob('*.md')}
        preview = card_migration.merge_people(wiki, 'Софья', 'Незнакомка у ворот', apply=False, **kwargs)
        self.assertEqual(preview['status'], 'dry-run')
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*.md')})
        original_write = wiki.write_text
        attempts = 0
        def fail_once(path, text):
            nonlocal attempts
            attempts += 1
            if attempts == 2:
                raise OSError('simulated interruption')
            return original_write(path, text)
        with patch.object(wiki, 'write_text', side_effect=fail_once):
            with self.assertRaises(OSError):
                card_migration.merge_people(wiki, 'Софья', 'Незнакомка у ворот', **kwargs)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*.md')})
        card_migration.merge_people(wiki, 'Софья', 'Незнакомка у ворот', **kwargs)
        self.assertEqual(card_migration.merge_people(wiki, 'Софья', 'Незнакомка у ворот', **kwargs)['status'],
                         'already-merged')
        self.assertEqual(len(wiki.cards()), 1)
        self.assertIn('Незнакомка у ворот/факт-001', [f['fact_id'] for f in wiki.cards()[0]['facts']])
        self.assertIn('Софья.sample', index.read_text(encoding='utf-8'))
        wiki.build()
        self.assertEqual(wiki.validate()[0], [])


if __name__ == '__main__':
    unittest.main()
