from collections import Counter
import json
import sqlite3
import unittest
from build_context_examples import SCHEMA, records, focus, search_text


class ContextExamplesTests(unittest.TestCase):
    def test_multiword_negation_is_not_a_vocabulary_candidate(self):
        entry = {'lang_code':'zh','lang':'Chinese','word':'不要','senses':[{
            'glosses':['do not'], 'examples':[{'type':'example','text':'请不要鼓掌。',
                'english':'Please do not clap.','bold_text_offsets':[[1,3]],
                'bold_translation_offsets':[[7,13]]}]}]}
        rows = list(records(entry, 1, Counter(), {'en':{'do','not'},'zh':{'不要'}}))
        self.assertEqual(rows, [])
        # A lexical phrase with a preposition still supplies evidence. Its
        # person/meaning must be resolved separately before display.
        entry = {'lang_code':'es','lang':'Spanish','word':'camino','senses':[{
            'glosses':['way'], 'examples':[{'type':'example','text':'De camino a casa.',
                'english':'On my way home.','bold_text_offsets':[[0,9]],
                'bold_translation_offsets':[[0,9]]}]}]}
        rows = list(records(entry, 2, Counter(), {'en':{'on','my'},'es':{'de'}}))
        self.assertEqual(len(rows), 2)

    def test_only_explicit_paired_spans_create_bilingual_records(self):
        example = {'type': 'example', 'text': 'Mis pies.', 'english': 'My feet.',
                   'bold_text_offsets': [[4, 8]], 'bold_translation_offsets': [[3, 7]]}
        entry = {'lang_code': 'es', 'lang': 'Spanish', 'word': 'pie', 'senses': [{'glosses': ['foot'], 'examples': [example]}]}
        rows = list(records(entry, 12, Counter()))
        self.assertEqual([(r['source'], r['target']) for r in rows], [('pies', 'feet'), ('feet', 'pies')])
        self.assertTrue(all(r['source_line'] == 12 for r in rows))
        for row in rows:
            self.assertEqual(row['source_context'][row['source_start']:row['source_end']], row['source'])
            self.assertEqual(row['target_context'][row['target_start']:row['target_end']], row['target'])
            self.assertEqual(json.loads(row['usage_evidence'])['context_conditions'], 'not_inferred')
        for field, value in [('bold_translation_offsets', []), ('bold_text_offsets', [[4, 8], [0, 3]]), ('ref', 'Quoted work'), ('type', 'quotation')]:
            changed = dict(example, **{field: value})
            entry['senses'][0]['examples'] = [changed]
            self.assertEqual(list(records(entry, 12, Counter())), [])

    def test_unicode_character_offsets_are_validated_without_guessing(self):
        self.assertEqual(focus('😀 pies', [[2, 6]]), 'pies')
        for offsets in [[[2, 999]], [[-1, 2]], [[3, 2]], [['2', 6]], [[True, 3]]]:
            self.assertIsNone(focus('😀 pies', offsets))

    def test_only_the_explicit_romanization_span_is_a_word_reading(self):
        example = {'type': 'example', 'text': '本を読む。', 'english': 'Read a book.',
                   'bold_text_offsets': [[2,4]], 'bold_translation_offsets': [[0,4]],
                   'roman': 'Hon o yomu.', 'bold_roman_offsets': [[6,10]]}
        entry = {'lang_code':'ja','lang':'Japanese','word':'読む','senses':[{'glosses':['to read'],'examples':[example]}]}
        rows = list(records(entry, 1, Counter()))
        self.assertEqual([(r['target_language'], r['reading']) for r in rows], [('en',''),('ja','yomu')])
        example['bold_roman_offsets'] = []
        self.assertTrue(all(not r['reading'] for r in records(entry, 1, Counter())))
        example.update(roman='jɔmɯ', bold_roman_offsets=[[0,4]])
        self.assertTrue(all(not r['reading'] for r in records(entry, 1, Counter())))

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
