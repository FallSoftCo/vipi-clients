import unittest
import argparse
import json
from pathlib import Path
import sqlite3
import tempfile
import ahocorasick
from build_lexical_contexts import sentence_hits,unique_hits,build,sha_file


class ContextOffsets(unittest.TestCase):
    def hits(self,text,language,word):
        automaton=ahocorasick.Automaton(ahocorasick.STORE_INTS)
        automaton.add_word(word,0);automaton.make_automaton()
        return sentence_hits(text,language,automaton,[(word,[],1)])

    def test_original_utf16_survives_normalization_and_emoji(self):
        for text,language,word,expected in [
            ('👩🏽‍💻 Mi cepillo de dientes.','es','cepillo de dientes',(1,11,29)),
            ('نَبِيّ.','ar','نبي',(1,0,6)),
            ('Un cafe\u0301.','fr','café',(1,3,8)),
            ('İyi.','en','i\u0307yi',(1,0,3))]:
            with self.subTest(text=text):self.assertEqual(self.hits(text,language,word),[expected])

    def test_no_subword_or_partial_unicode_cluster_match(self):
        self.assertEqual(self.hits('A carpet.','en','car'),[])
        self.assertEqual(self.hits('İyi.','en','i'),[])

    def test_repeated_or_competing_occurrence_is_not_unique_alignment(self):
        analyses=lambda _: [[7,1,[[1,'',1]]]]
        self.assertEqual(unique_hits('[[1,0,3],[1,5,8]]',analyses),{})
        competing=lambda _: [[7,1,[[1,'',1]]],[8,1,[[1,'',1]]]]
        self.assertEqual(unique_hits('[[1,0,3]]',competing),{})
        self.assertEqual(unique_hits('[[1,0,3]]',analyses),{1:(0,3,7,1,'',1)})

    def test_supplement_receipt_binds_output_and_reserved_text_stays_out(self):
        # A complete tiny build catches output-path/input-path aliasing and
        # tests partition handling across both primary and supplemental data.
        with tempfile.TemporaryDirectory(dir='artifacts') as temporary:
            root=Path(temporary);shards=root/'shards';shards.mkdir();catalog=[]
            for language,word in [('en','coffee'),('es','café'),('sw','kahawa')]:
                path=shards/(language+'.sqlite');db=sqlite3.connect(path)
                db.executescript('''CREATE TABLE senses(id TEXT,label TEXT,pos TEXT,explicit INTEGER,source_url TEXT);
                    CREATE TABLE lexemes(id INTEGER,source_safe INTEGER,target_safe INTEGER);
                    CREATE TABLE surfaces(normalized TEXT,lexeme INTEGER,mode INTEGER);
                    CREATE TABLE terms(lexeme INTEGER,sense TEXT,reading TEXT,eligible INTEGER);''')
                db.execute('INSERT INTO senses VALUES (?,?,?,?,?)',('coffee','coffee beverage','noun',1,'https://example.test/dictionary'))
                db.execute('INSERT INTO lexemes VALUES (1,1,1)');db.execute('INSERT INTO surfaces VALUES (?,1,1)',(word,))
                db.execute("INSERT INTO terms VALUES (1,'coffee','',1)");db.commit();db.close()
                catalog.append(dict(language=language,sha256=sha_file(path),bytes=path.stat().st_size))
            (shards/'catalog.json').write_text(json.dumps(dict(schema='vipi-lexical-shards-1',shards=catalog,release_id='test')))
            def corpus(name,rows,links,receipt):
                folder=root/name;folder.mkdir();path=folder/'corpus.sqlite';db=sqlite3.connect(path)
                db.executescript('''CREATE TABLE sentences(id INTEGER PRIMARY KEY,language TEXT,text TEXT,owner TEXT,component INTEGER,partition TEXT);
                    CREATE TABLE links(a INTEGER,b INTEGER);CREATE TABLE tags(sentence INTEGER,tag INTEGER);
                    CREATE TABLE tag_metadata(id INTEGER,name TEXT);CREATE TABLE metadata(key TEXT,value TEXT);''')
                db.executemany('INSERT INTO sentences VALUES (?,?,?,?,?,?)',rows)
                db.executemany('INSERT INTO links VALUES (?,?)',links)
                db.execute('INSERT INTO metadata VALUES (?,?)',('receipt',json.dumps(dict(tags_schema='tag_id,sentence_id,username,added_time'))))
                db.commit();db.close();receipt['sha256']=sha_file(path)
                (folder/'receipt.json').write_text(json.dumps(receipt))
                return path
            primary=corpus('primary',[(1,'en','Coffee.','one',1,'development'),(2,'es','Café.','two',1,'development'),
                (99,'en','Coffee must never leak from reserved.','three',99,'reserved')],[(1,2),(1,99)],{})
            supplement=corpus('supplement',[(1,'en','Coffee.','one',1,'development'),(3,'sw','Kahawa.','four',1,'development')],[(1,3)],
                dict(schema='vipi-swahili-development-supplement-1',parent_receipt_sha256=sha_file(primary.parent/'receipt.json')))
            (supplement.parent/'duplicate-audit.json').write_text(json.dumps(dict(complete_duplicate_neighbor_evidence=True)))
            output=root/'output';build(argparse.Namespace(shards=shards,corpus=primary,supplement=[supplement],language=None,
                max_sentences_per_language=0,output=output))
            receipt=json.loads((output/'receipt.json').read_text())
            self.assertEqual(receipt['sha256'],sha_file(output/'contexts.sqlite'))
            self.assertEqual(receipt['bytes'],(output/'contexts.sqlite').stat().st_size)
            with sqlite3.connect(output/'contexts.sqlite') as db:
                self.assertEqual(db.execute('SELECT count(*) FROM sentences WHERE id=99').fetchone()[0],0)
                self.assertEqual(db.execute('SELECT count(*) FROM alignments').fetchone()[0],2)
                self.assertEqual(db.execute("SELECT rowid FROM sentence_search WHERE sentence_search MATCH 'coffee'").fetchall(),[(1,)])


if __name__=='__main__':unittest.main()
