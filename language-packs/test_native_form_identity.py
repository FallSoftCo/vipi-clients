"""Translation form identity must survive lossy search-key normalization."""
import json
import sqlite3
import unittest

from context_hints import lookup_key
from native_lemma_links import NativeLinks


class NativeFormIdentity(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.executescript('''
            CREATE TABLE native_entries(source_line INTEGER PRIMARY KEY,
                language TEXT,headword TEXT,normalized TEXT,part_of_speech TEXT,tags TEXT,source_url TEXT);
            CREATE TABLE native_forms(source_line INTEGER,form TEXT,normalized TEXT,tags TEXT);
        ''')
        # Exact supplied spellings/entry identities from retained Wiktextract
        # archive 8c97e9de...; obsolete senses are intentionally still separate.
        for identifier, head, forms in [
            (954313, 'بن', [('بْن', ['canonical', 'masculine'])]),
            (954314, 'بن', [('بُنّ', ['canonical', 'masculine'])]),
            (954315, 'بن', [('بُنّ', ['canonical', 'masculine'])]),
            (954317, 'بن', [('بِنّ', ['canonical', 'masculine'])]),
            (1451005, 'ابن', [('اِبْن', ['canonical', 'masculine']), ('بْن', ['alternative'])]),
        ]:
            self.entry(identifier, 'ar', head, forms)
        self.links = NativeLinks(self.db, 'ar', {})

    def tearDown(self):
        self.links.close()
        self.db.close()

    def entry(self, identifier, language, head, forms):
        self.db.execute('INSERT INTO native_entries VALUES (?,?,?,?,?,?,?)',
                        (identifier, language, head, lookup_key(head, language), 'noun', '[]', 'primary-fixture'))
        self.db.executemany('INSERT INTO native_forms VALUES (?,?,?,?)',
            [(identifier, form, lookup_key(form, language), json.dumps(tags)) for form, tags in forms])

    def test_vocalized_coffee_does_not_join_son_or_differently_vocalized_homograph(self):
        self.assertEqual(self.links.candidates('بُنّ'), (954314, 954315))
        # This identity test does not certify either remaining sense as modern
        # or correct: the existing downstream sense/obsolete checks still apply.
        self.assertEqual(self.links.candidates('بِنّ'), (954317,))

    def test_attested_son_alternative_is_preserved_without_merging_identities(self):
        self.assertEqual(self.links.candidates('بْن'), (954313, 1451005))
        self.assertEqual(self.links.candidates('اِبْن'), (1451005,))

    def test_unvocalized_input_retains_ambiguity(self):
        self.assertEqual(self.links.candidates('بن'), (954313, 954314, 954315, 954317, 1451005))

    def test_combining_order_and_elongation_are_not_different_lexemes(self):
        self.assertEqual(self.links.candidates('بـُنّ'), (954314, 954315))
        self.entry(2, 'ar', 'سن', [('سُنّ', ['canonical'])])
        self.assertEqual(self.links.candidates('سُنّ'), (2,))
        self.entry(3, 'ar', 'شد', [('شَدّ', ['canonical'])])
        self.assertEqual(self.links.candidates('شَدّ'), (3,))
        self.entry(4, 'ar', 'مد', [('مَدَّ', ['canonical'])])
        self.assertEqual(self.links.candidates('مَدَّ'), (4,))

    def test_unattested_marked_form_is_not_guessed_from_bare_head(self):
        self.assertEqual(self.links.candidates('بَنّ'), ())
        self.assertEqual(self.links.candidates('بُن'), ())

    def test_exact_alternate_script_remains_available(self):
        self.entry(10, 'zh', '學校', [('学校', ['alternative'])])
        links = NativeLinks(self.db, 'zh', {})
        try:
            self.assertEqual(links.candidates('学校'), (10,))
        finally:
            links.close()

    def test_non_arabic_diacritics_and_unicode_script_variants_are_unchanged(self):
        cases = [
            (20, 'de', 'Mädchen', [], 'Ma\u0308dchen'),
            (21, 'es', 'camión', [], 'camio\u0301n'),
            (22, 'fr', 'café', [], 'cafe\u0301'),
            (23, 'ja', '珈琲', [('コーヒー', ['alternative'])], 'コーヒー'),
            (24, 'ko', '한글', [], '\u1112\u1161\u11ab\u1100\u1173\u11af'),
        ]
        for identifier, language, head, forms, query in cases:
            self.entry(identifier, language, head, forms)
            links = NativeLinks(self.db, language, {})
            try:
                self.assertEqual(links.candidates(query), (identifier,))
            finally:
                links.close()


if __name__ == '__main__':
    unittest.main()
