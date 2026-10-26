import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from collections import Counter
from cryptography.hazmat.primitives.asymmetric import ec
from build_wiktextract import SCHEMA,add_entry
from expand_attested_nouns import noun_forms,augment
from export_bilingual import export_pair


def forms_fixture(rows):
    db=sqlite3.connect(':memory:')
    db.execute('CREATE TABLE analyses(language,source_key,surface,lemma,lemma_key,pos,features,occurrences,atomic_lemma_candidate,evidence)')
    for language,surface,lemma,pos,number in rows:
        db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,?,?,?,?)',(language,surface.lower(),surface,lemma,lemma.lower(),pos,
            json.dumps({'Number':number} if number else {}),4,1,json.dumps([{'sentence_id':'synthetic','token_id':'1'}])))
    return db


class AttestedNounTests(unittest.TestCase):
    def test_competing_pos_lemmas_or_numbers_block_a_proposal(self):
        db=forms_fixture([
            ('en','houses','house','NOUN','Plur'),('en','can','can','NOUN','Plur'),('en','can','can','AUX',None),
            ('en','axes','axe','NOUN','Plur'),('en','axes','axis','NOUN','Plur'),
            ('en','means','means','NOUN','Plur'),('en','means','means','NOUN','Sing'),
            ('en','things','thing','NOUN',None),('en','Smiths','Smith','PROPN','Plur')])
        try:
            plural,_,_=noun_forms(db,'en')
            self.assertEqual(set(plural),{'houses'})
        finally:db.close()

    def test_supplement_preserves_untranslated_and_lexicalized_senses(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);catalog=root/'catalog.sqlite'
            with sqlite3.connect(catalog) as db:
                db.executescript(SCHEMA)
                for i,(word,pos,label,language,target) in enumerate([
                    ('house','noun','building for dwelling','es','casa'),
                    ('house','verb','provide accommodation','es','alojar'),
                    ('houses','noun','legislative chambers','ja','議院')],1):
                    add_entry(db,{'lang_code':'en','word':word,'pos':pos,'translations':[
                        {'code':language,'word':target,'sense':label}]},i,Counter())
                db.executemany('INSERT INTO metadata VALUES (?,?)',[
                    ('upstream_sha256',json.dumps('synthetic')),('source_version',json.dumps('synthetic'))])
            folder=root/'pack';export_pair(catalog,'en','es',folder,1,ec.generate_private_key(ec.SECP256R1()),'synthetic')
            forms=forms_fixture([('en','houses','house','NOUN','Plur'),('es','casa','casa','NOUN','Sing'),
                ('es','casas','casa','NOUN','Plur'),('es','casos','caso','NOUN','Plur')])
            try:
                report=augment(folder/'vocabulary.sqlite',catalog,'en','es',noun_forms(forms,'en'),noun_forms(forms,'es'),{'en':set(),'es':set()},10)
            finally:forms.close()
            self.assertEqual(report['proposed_sources'],1)
            with sqlite3.connect(folder/'vocabulary.sqlite') as db:
                self.assertEqual(db.execute('SELECT source,target FROM vocabulary WHERE source=?',('houses',)).fetchall(),[('houses','casas')])
                self.assertEqual(db.execute('SELECT count(*) FROM source_senses WHERE source=?',('houses',)).fetchone()[0],3)
                self.assertEqual(db.execute('SELECT count(*) FROM attested_noun_forms').fetchone()[0],2)
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
                self.assertEqual(db.execute("SELECT count(*) FROM senses WHERE source_word='houses'").fetchone()[0],1)


if __name__=='__main__':unittest.main()
