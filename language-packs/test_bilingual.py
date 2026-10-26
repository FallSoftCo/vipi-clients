import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from collections import Counter

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from build_wiktextract import SCHEMA, add_entry
from export_bilingual import export_pair


def fixture_catalog(path):
    with sqlite3.connect(path) as db:
        db.executescript(SCHEMA)
        for line, (source, label, translations) in enumerate([
            ('bank', 'financial institution', [('es', 'banco', ''), ('fr', 'banque', '')]),
            ('bank', 'edge of a river', [('es', 'orilla', ''), ('fr', 'rive', '')]),
            ('coffee', 'drink', [('zh', '咖啡', 'kāfēi'), ('ja', 'コーヒー', 'kōhī'), ('ko', '커피', 'keopi'), ('ar', 'قَهْوَة', 'qahwa')]),
            ('lead', 'metal', [('zh', '铅', 'qiān')]),
            ('lead', 'to guide', [('zh', '引导', 'yǐndǎo')]),
            ('read', 'interpret writing', [('ja', '読む', 'yomu'), ('ja', '読む', 'doku')]),
            ('missing', 'not found', [('zh', '丢失', '')]),
            ('unlabeled', '', [('es', 'sin etiqueta', ''), ('fr', 'sans étiquette', '')]),
        ], 1):
            add_entry(db, {'lang_code': 'en', 'word': source, 'pos': 'noun',
                          'translations': [{'code': language, 'word': word, 'roman': roman, 'sense': label}
                                           for language, word, roman in translations]}, line, Counter())
        db.executemany('INSERT INTO metadata VALUES (?,?)', [
            ('upstream_sha256', json.dumps('synthetic-source')),
            ('source_version', json.dumps('synthetic-qualification')),
        ])


class BilingualExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.catalog = self.root / 'catalog.sqlite'
        fixture_catalog(self.catalog)
        self.before = hashlib.sha256(self.catalog.read_bytes()).hexdigest()
        self.key = ec.generate_private_key(ec.SECP256R1())

    def tearDown(self):
        self.assertEqual(hashlib.sha256(self.catalog.read_bytes()).hexdigest(), self.before)
        self.tmp.cleanup()

    def export(self, source, target):
        output = self.root / (source + '-' + target)
        manifest = export_pair(self.catalog, source, target, output, 1, self.key, 'qa-only')
        return output, manifest

    def test_native_guards_retain_unmapped_source_evidence_and_bind_provenance(self):
        from build_source_guards import SCHEMA as GUARD_SCHEMA, POLICY
        guards=self.root/'guards.sqlite'
        with sqlite3.connect(guards) as db:
            db.executescript(GUARD_SCHEMA)
            db.executemany('INSERT INTO metadata VALUES (?,?)',[
                ('schema','vipi-native-source-guards-1'),('language','zh'),
                ('policy',POLICY),('upstream_sha256','synthetic-source')])
            db.execute('INSERT INTO source_guards VALUES (?,?,?,?)',('板蓝根',1,0,'[]'))
        folder=self.root/'guarded-zh-en'
        manifest=export_pair(self.catalog,'zh','en',folder,9,self.key,'qa-only',source_guards=guards)
        self.assertEqual(manifest['native_source_guard_policy'],POLICY)
        self.assertEqual(manifest['context_policy'],'all-source-senses-native-guards-veto-4')
        self.assertEqual(manifest['native_source_guard_sha256'],hashlib.sha256(guards.read_bytes()).hexdigest())
        with sqlite3.connect(folder/'vocabulary.sqlite') as db:
            self.assertEqual(db.execute('SELECT * FROM source_guards').fetchall(),[('板蓝根',1,0)])
            self.assertEqual(db.execute("SELECT count(*) FROM vocabulary WHERE source='板蓝根'").fetchone()[0],0)
        with sqlite3.connect(guards) as db:db.execute("UPDATE metadata SET value='wrong-source' WHERE key='upstream_sha256'")
        with self.assertRaisesRegex(ValueError,'provenance'):
            export_pair(self.catalog,'zh','en',self.root/'invalid-guard',10,self.key,'qa-only',source_guards=guards)

    def test_pivot_keeps_senses_and_rejects_unlabeled_cross_language(self):
        output, manifest = self.export('es', 'fr')
        with sqlite3.connect(output / 'vocabulary.sqlite') as db:
            self.assertEqual(db.execute('SELECT source,target FROM vocabulary ORDER BY source').fetchall(), [('banco', 'banque'), ('orilla', 'rive')])
            self.assertEqual(db.execute('SELECT count(DISTINCT sense_id) FROM vocabulary').fetchone()[0], 2)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(db.execute('SELECT DISTINCT evidence FROM senses').fetchall(), [('shared_explicit_english_sense',)])
            self.assertTrue(all(url.startswith('https://en.wiktionary.org/wiki/bank') for url, in db.execute('SELECT source_url FROM senses')))
        self.assertEqual(manifest['quality'], 'candidate')

    def test_readings_and_conflicts_survive_without_guessing(self):
        output, _ = self.export('en', 'ja')
        with sqlite3.connect(output / 'vocabulary.sqlite') as db:
            self.assertEqual(db.execute("SELECT target,reading FROM vocabulary WHERE source='coffee'").fetchall(), [('コーヒー', 'kōhī')])
            self.assertEqual(set(db.execute("SELECT target,reading FROM vocabulary WHERE source='read'")), {('読む', 'yomu'), ('読む', 'doku')})

    def test_direct_unlabeled_translation_is_retained_but_never_pivoted(self):
        output, _ = self.export('en', 'es')
        with sqlite3.connect(output / 'vocabulary.sqlite') as db:
            self.assertEqual(db.execute("SELECT target FROM vocabulary WHERE source='unlabeled'").fetchall(), [('sin etiqueta',)])
            self.assertEqual(db.execute('SELECT DISTINCT evidence FROM senses').fetchall(), [('direct',)])

    def test_reverse_does_not_mix_homograph_senses(self):
        output, _ = self.export('zh', 'en')
        with sqlite3.connect(output / 'vocabulary.sqlite') as db:
            rows = db.execute("SELECT v.source,s.label FROM vocabulary v JOIN senses s ON v.sense_id=s.id WHERE v.target='lead'").fetchall()
            self.assertEqual(set(rows), {('铅', 'metal'), ('引导', 'to guide')})

    def test_signature_binds_manifest_and_complete_database(self):
        output, manifest = self.export('en', 'zh')
        raw, signature = (output / 'manifest.json').read_bytes(), (output / 'manifest.sig').read_bytes()
        self.key.public_key().verify(signature, raw, ec.ECDSA(hashes.SHA256()))
        self.assertEqual(hashlib.sha256((output / 'vocabulary.sqlite').read_bytes()).hexdigest(), manifest['sha256'])
        self.assertEqual(manifest['schema_version'], 4)
        with self.assertRaises(InvalidSignature):
            self.key.public_key().verify(signature, raw.replace(b'candidate', b'approved'), ec.ECDSA(hashes.SHA256()))
        with self.assertRaises(FileExistsError):
            self.export('en', 'zh')

    def test_sense_hints_keep_the_competing_context(self):
        output, manifest = self.export('en', 'es')
        with sqlite3.connect(output / 'vocabulary.sqlite') as db:
            rows = [(label, term) for label, terms in db.execute('SELECT s.label,c.hints FROM senses s JOIN sense_context c ON c.sense_id=s.id') for term in terms.split('\x1f')]
        self.assertIn(('edge of a river', 'river'), rows)
        self.assertNotIn(('edge of a river', 'of'), rows)
        self.assertEqual(manifest['context_policy'], 'all-source-senses-veto-3')

    def test_missing_target_does_not_erase_a_source_meaning(self):
        with sqlite3.connect(self.catalog) as db:
            add_entry(db, {'lang_code': 'en', 'word': 'bank', 'pos': 'noun',
                          'translations': [{'code': 'de', 'word': 'Bank', 'sense': 'row of objects'}]}, 100, Counter())
            # Same label, different part of speech: identity must survive.
            add_entry(db, {'lang_code': 'en', 'word': 'bank', 'pos': 'verb',
                          'translations': [{'code': 'de', 'word': 'anordnen', 'sense': 'row of objects'}]}, 101, Counter())
        self.before = hashlib.sha256(self.catalog.read_bytes()).hexdigest()
        output, manifest = self.export('en', 'es')
        with sqlite3.connect(output / 'vocabulary.sqlite') as db:
            self.assertEqual(db.execute("SELECT count(*) FROM source_senses WHERE source='bank'").fetchone()[0], 4)
            self.assertEqual(db.execute("SELECT count(*) FROM vocabulary WHERE source='bank'").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT count(*) FROM senses WHERE label='row of objects'").fetchone()[0], 2)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
        # The existing unlabeled fixture also has an unmapped source sense.
        self.assertEqual(manifest['unmapped_source_senses'], 3)

    def test_negative_contractions_remain_native_with_both_apostrophes(self):
        words = ["don't", 'don’t', "can't", 'can’t', 'cannot', "won't", 'won’t']
        with sqlite3.connect(self.catalog) as db:
            for line, word in enumerate(words, 100):
                add_entry(db, {'lang_code': 'en', 'word': word, 'pos': 'verb',
                              'translations': [{'code': 'es', 'word': 'no', 'sense': 'negative auxiliary'}]}, line, Counter())
        self.before = hashlib.sha256(self.catalog.read_bytes()).hexdigest()
        output, _ = self.export('en', 'es')
        with sqlite3.connect(output / 'vocabulary.sqlite') as db:
            for word in words:
                self.assertEqual(db.execute('SELECT count(*) FROM vocabulary WHERE source=?', (word,)).fetchone()[0], 0)
            self.assertGreater(db.execute("SELECT count(*) FROM vocabulary WHERE source='bank'").fetchone()[0], 0)

    def test_arabic_vowel_variants_share_lookup_without_losing_readings(self):
        from context_hints import lookup_key
        self.assertEqual(lookup_key('قَـهْوَة', 'ar'), 'قهوة')
        self.assertNotEqual(lookup_key('أمل', 'ar'), lookup_key('امل', 'ar'))
        with sqlite3.connect(self.catalog) as db:
            add_entry(db, {'lang_code': 'en', 'word': 'water', 'pos': 'noun', 'translations': [
                {'code': 'ar', 'word': 'مَاء', 'roman': "mā'", 'sense': 'liquid'}]}, 100, Counter())
        self.before = hashlib.sha256(self.catalog.read_bytes()).hexdigest()
        output, _ = self.export('ar', 'en')
        with sqlite3.connect(output / 'vocabulary.sqlite') as db:
            self.assertEqual(db.execute("SELECT source,target FROM vocabulary WHERE source='ماء'").fetchall(), [('ماء', 'water')])

    def test_negation_remains_in_source_grammar(self):
        with sqlite3.connect(self.catalog) as db:
            add_entry(db, {'lang_code': 'en', 'word': 'not', 'pos': 'adv', 'translations': [
                {'code': 'es', 'word': 'no', 'sense': 'negates another word'}]}, 100, Counter())
        self.before = hashlib.sha256(self.catalog.read_bytes()).hexdigest()
        output, _ = self.export('en', 'es')
        with sqlite3.connect(output / 'vocabulary.sqlite') as db:
            self.assertEqual(db.execute("SELECT count(*) FROM vocabulary WHERE source='not'").fetchone()[0], 0)

    def test_native_grammatical_homograph_remains_untranslated(self):
        with sqlite3.connect(self.catalog) as db:
            for word, target in [('up', 'arriba'), ('be', 'ser')]:
                add_entry(db, {'lang_code': 'en', 'word': word, 'pos': 'verb', 'translations': [
                    {'code': 'es', 'word': target, 'sense': 'synthetic lexical sense'}]}, 101, Counter())
        self.before = hashlib.sha256(self.catalog.read_bytes()).hexdigest()
        output = self.root / 'guarded'
        manifest = export_pair(self.catalog, 'en', 'es', output, 1, self.key, 'qa-only',
                               {'terms': {'en': {'up': {}, 'be': {}}}, 'file_sha256': 'synthetic-guard'})
        with sqlite3.connect(output / 'vocabulary.sqlite') as db:
            self.assertEqual(db.execute("SELECT count(*) FROM vocabulary WHERE source IN ('up','be')").fetchone()[0], 0)
            self.assertGreater(db.execute("SELECT count(*) FROM vocabulary WHERE source='bank'").fetchone()[0], 0)
        self.assertEqual(manifest['grammar_mappings_omitted'], 2)
        self.assertEqual(manifest['grammar_guard_sha256'], 'synthetic-guard')

    def test_arabic_reading_collision_in_another_sense_abstains(self):
        with sqlite3.connect(self.catalog) as db:
            for index, (word, pos, form, reading) in enumerate([
                ('open', 'verb', 'فَتَحَ', 'fataḥa'),
                ('opening', 'noun', 'فَتْح', 'fatḥ'),
            ], 100):
                add_entry(db, {'lang_code':'en','word':word,'pos':pos,'translations':[
                    {'code':'ar','word':form,'roman':reading,'sense':word}]}, index, Counter())
        self.before = hashlib.sha256(self.catalog.read_bytes()).hexdigest()
        output, manifest = self.export('en', 'ar')
        with sqlite3.connect(output / 'vocabulary.sqlite') as db:
            self.assertEqual(db.execute("SELECT count(*) FROM vocabulary WHERE source IN ('open','opening')").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT target,reading FROM vocabulary WHERE source='coffee'").fetchall(), [('قَهْوَة','qahwa')])
        self.assertEqual(manifest['reading_collision_mappings_omitted'], 2)

    def test_all_grammar_phrase_is_excluded_without_excluding_lexical_phrases(self):
        with sqlite3.connect(self.catalog) as db:
            for line, (source, target) in enumerate([('do not','不要'), ('have to','必须'),
                                                    ('on the way','途中')], 100):
                add_entry(db, {'lang_code':'en','word':source,'pos':'verb','translations':[
                    {'code':'zh','word':target,'sense':'synthetic phrase'}]}, line, Counter())
        self.before = hashlib.sha256(self.catalog.read_bytes()).hexdigest()
        output = self.root / 'guarded-phrases'
        manifest = export_pair(self.catalog, 'en', 'zh', output, 1, self.key, 'qa-only',
                               {'terms': {'en': {'do':{}, 'have':{}, 'to':{}, 'on':{}, 'the':{}}},
                                'file_sha256':'synthetic-guard'})
        with sqlite3.connect(output / 'vocabulary.sqlite') as db:
            self.assertEqual(db.execute("SELECT source FROM vocabulary WHERE source IN ('do not','have to')").fetchall(), [])
            self.assertEqual(db.execute("SELECT target FROM vocabulary WHERE source='on the way'").fetchall(), [('途中',)])
        self.assertEqual(manifest['grammar_mappings_omitted'], 2)
        self.assertEqual(manifest['grammar_policy'], 'native-closed-class-phrases-2')

    def test_qualifiers_cannot_add_or_contradict_age_or_speaker_gender(self):
        from context_hints import qualifiers_compatible
        elder = json.dumps({'english':'elder','translation':'elder'})
        older = json.dumps({'english':'older'})
        younger = json.dumps({'english':'younger'})
        self.assertTrue(qualifiers_compatible(elder,older,'sister','zh','ja'))
        self.assertFalse(qualifiers_compatible(elder,younger,'sister','zh','ja'))
        self.assertFalse(qualifiers_compatible('{}',younger,'sister','en','ja'))
        self.assertTrue(qualifiers_compatible('{}',younger,'younger sister','en','ja'))
        self.assertFalse(qualifiers_compatible(elder,json.dumps({'english':'elder, of a male'}),'sister','zh','ko'))
        self.assertFalse(qualifiers_compatible('{}',json.dumps({'note':'ancient form'}),'sister','en','zh'))

    def test_export_rejects_missing_qualifiers_inside_a_scoped_family(self):
        with sqlite3.connect(self.catalog) as db:
            add_entry(db, {'lang_code':'en','word':'sister','pos':'noun','translations':[
                {'code':'zh','word':'姐姐','roman':'jiějie','sense':'female sibling','english':'elder'},
                {'code':'ja','word':'お姉さん','roman':'onēsan','sense':'female sibling','english':'elder'},
                {'code':'ja','word':'妹','roman':'imōto','sense':'female sibling','english':'younger'},
                {'code':'ja','word':'姉','roman':'ane','sense':'female sibling'}]},100,Counter())
        self.before = hashlib.sha256(self.catalog.read_bytes()).hexdigest()
        output, _ = self.export('zh','ja')
        with sqlite3.connect(output / 'vocabulary.sqlite') as db:
            self.assertEqual(db.execute("SELECT target FROM vocabulary WHERE source='姐姐'").fetchall(), [('お姉さん',)])
            details = json.loads(db.execute("SELECT mapping_details FROM vocabulary WHERE source='姐姐'").fetchone()[0])
            self.assertEqual(details['source']['english'], 'elder')
        output, _ = self.export('en','ja')
        with sqlite3.connect(output / 'vocabulary.sqlite') as db:
            self.assertEqual(db.execute("SELECT count(*) FROM vocabulary WHERE source='sister'").fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
