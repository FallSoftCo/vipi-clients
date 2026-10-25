import sqlite3
import unittest
from collections import Counter
from build_wiktextract import SCHEMA, add_entry, coverage, readable_roman


class CandidateCatalogTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:'); self.db.executescript(SCHEMA); self.counts = Counter()
    def tearDown(self): self.db.close()
    def add(self, word, translations, line=1, **kwargs):
        add_entry(self.db, dict(word=word, lang_code='en', pos='noun', translations=translations, **kwargs), line, self.counts)
    def pair(self, source, target): return next(x for x in coverage(self.db) if x['source']==source and x['target']==target)
    def test_homographs_never_join_across_senses_or_etymologies(self):
        self.add('bank', [{'code':'es','word':'banco','sense':'financial institution'}, {'code':'fr','word':'rive','sense':'river edge'}])
        self.assertEqual(self.pair('es','fr')['candidate_pairs'],0)
        self.add('bank', [{'code':'fr','word':'banque','sense':'financial institution'}],line=2)
        self.assertEqual(self.pair('es','fr')['candidate_pairs'],0)
        self.assertEqual(self.pair('en','fr')['candidate_pairs'],2)
    def test_shared_explicit_sense_is_classified_as_derived(self):
        self.add('coffee',[{'code':'es','word':'café','sense':'drink'}, {'code':'fr','word':'café','sense':'drink'}])
        self.assertEqual(self.pair('es','fr')['candidate_pairs'],1)
        self.assertEqual(self.pair('es','fr')['evidence'],'shared_explicit_english_sense')
        self.assertEqual(self.pair('es','en')['evidence'],'reversed_direct')
        self.assertEqual(self.pair('en','es')['evidence'],'direct')
    def test_unlabeled_translations_are_not_pivoted(self):
        self.add('bank',[{'code':'es','word':'banco'}, {'code':'fr','word':'rive'}])
        self.assertEqual(self.pair('en','es')['candidate_pairs'],1)
        self.assertEqual(self.pair('es','fr')['candidate_pairs'],0)
    def test_sense_level_translations_keep_own_scope(self):
        self.add('bank',[],senses=[{'glosses':['institution'],'translations':[{'code':'es','word':'banco'},{'code':'fr','word':'banque'}]}, {'glosses':['edge'],'translations':[{'code':'fr','word':'rive'}]}])
        self.assertEqual(self.pair('es','fr')['candidate_pairs'],1)
    def test_chinese_dialects_and_arabic_variants_are_not_mandarin_or_msa(self):
        self.add('dictionary',[{'code':'zh','word':'字典','roman':'lī-tián','tags':['Hokkien'],'sense':'book'}, {'code':'ar','word':'قاموس','roman':'gāmūs','tags':['Hijazi-Arabic'],'sense':'book'}, {'code':'cmn','word':'詞典 /词典','roman':'cídiǎn','sense':'book'}])
        self.assertEqual(self.counts['excluded_dialect'],2)
        self.assertEqual(self.pair('en','zh')['candidate_pairs'],2)
        self.assertEqual(self.pair('en','ar')['candidate_pairs'],0)
    def test_reading_evidence_and_conflicts_are_preserved(self):
        self.add('life',[{'code':'ja','word':'生','roman':'sei','sense':'life'}, {'code':'ja','word':'生','roman':'shō','sense':'life'}])
        self.assertEqual(self.db.execute("SELECT count(DISTINCT roman) FROM terms WHERE language='ja'").fetchone()[0],2)
        self.assertEqual(self.pair('en','ja')['candidate_pairs'],1)
        self.add('bank',[{'code':'ja','word':'銀行','sense':'finance'}],line=2)
        self.assertEqual(self.pair('en','ja')['source_headwords'],2)
        self.assertEqual(self.pair('en','ja')['headwords_with_readable_target'],1)
    def test_no_ipa_audio_examples_or_gloss_link_guessing(self):
        self.add('river',[],senses=[{'glosses':['river'],'links':[['rive','rive']],'examples':[{'text':'copyrighted example'}]}])
        self.assertEqual(self.db.execute('SELECT count(*) FROM terms').fetchone()[0],0)
        self.assertEqual(readable_roman('muʕjam'),"mu'jam")
        self.assertEqual(readable_roman('/ɡʁa.tis/'),'')
        self.assertEqual(readable_roman('ʕ'),'')
        self.assertEqual(readable_roman('ᴀ'),'')
        self.assertEqual(readable_roman('...'),'')
        self.assertEqual(readable_roman('x / y'),'')
        self.assertEqual(readable_roman('じしょ'),'')
        self.assertEqual(readable_roman('jisho'),'jisho')
    def test_function_words_obsolete_entries_and_bad_forms_are_excluded(self):
        add_entry(self.db,{'lang_code':'en','word':'the','pos':'det','translations':[{'code':'es','word':'el'}]},1,self.counts)
        self.add('yesterday',[{'code':'fr','word':'hier','tags':['obsolete']}])
        self.add('unsafe',[{'code':'es','word':'<script>'}])
        self.assertEqual(self.db.execute('SELECT count(*) FROM terms').fetchone()[0],0)
    def test_native_v1_installers_must_reject_candidate_schema(self):
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],2)


if __name__ == '__main__': unittest.main()
