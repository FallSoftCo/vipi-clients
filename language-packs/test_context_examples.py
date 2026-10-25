from collections import Counter
import sqlite3
import unittest
from build_context_examples import SCHEMA, records, focus, search_text


class ContextExamplesTests(unittest.TestCase):
    def test_only_explicit_paired_spans_create_bilingual_records(self):
        example = {'type': 'example', 'text': 'Mis pies.', 'english': 'My feet.',
                   'bold_text_offsets': [[4, 8]], 'bold_translation_offsets': [[3, 7]]}
        entry = {'lang_code': 'es', 'lang': 'Spanish', 'word': 'pie', 'senses': [{'glosses': ['foot'], 'examples': [example]}]}
        rows = list(records(entry, 12, Counter()))
        self.assertEqual([(r['source'], r['target']) for r in rows], [('pies', 'feet'), ('feet', 'pies')])
        self.assertTrue(all(r['source_line'] == 12 for r in rows))
        for field, value in [('bold_translation_offsets', []), ('bold_text_offsets', [[4, 8], [0, 3]]), ('ref', 'Quoted work'), ('type', 'quotation')]:
            changed = dict(example, **{field: value})
            entry['senses'][0]['examples'] = [changed]
            self.assertEqual(list(records(entry, 12, Counter())), [])

    def test_unicode_character_offsets_are_validated_without_guessing(self):
        self.assertEqual(focus('😀 pies', [[2, 6]]), 'pies')
        for offsets in [[[2, 999]], [[-1, 2]], [[3, 2]], [['2', 6]], [[True, 3]]]:
            self.assertIsNone(focus('😀 pies', offsets))

    def test_fts_retrieves_phrases_and_unspaced_contexts(self):
        self.assertEqual(search_text('Apple東京駅。', 'ja'), 'apple 東京 京駅')
        with sqlite3.connect(':memory:') as db:
            db.executescript(SCHEMA)
            # Search-only synthetic rows test actual SQLite indexing, not sense acceptance.
            for index, (value, language) in enumerate([('Read the bill in parliament.', 'en'), ('明日は図書館で本を読む。', 'ja')], 1):
                db.execute('INSERT INTO context_search(docid,search_text) VALUES (?,?)', (index, search_text(value, language)))
            self.assertEqual(db.execute("SELECT docid FROM context_search WHERE context_search MATCH ?", ('"bill in parliament"',)).fetchall(), [(1,)])
            self.assertEqual(db.execute("SELECT docid FROM context_search WHERE context_search MATCH ?", ('図書',)).fetchall(), [(2,)])
            self.assertEqual(db.execute("SELECT docid FROM context_search WHERE context_search MATCH ?", ('bank',)).fetchall(), [])


if __name__ == '__main__': unittest.main()
