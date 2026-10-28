import unittest
import argparse
import json
from pathlib import Path
import sqlite3
import tempfile
import ahocorasick
from build_lexical_contexts import sentence_hits,unique_hits,build,sha_file,select_changed_pair_endpoints


class ContextOffsets(unittest.TestCase):
    def hits(self,text,language,word):
        automaton=ahocorasick.Automaton(ahocorasick.STORE_INTS)
        automaton.add_word(word,0);automaton.make_automaton()
        return sentence_hits(text,language,automaton,[(word,[],1)])

    def test_changed_language_selection_excludes_reserved_and_indirect_neighbors(self):
        with tempfile.TemporaryDirectory(dir='artifacts') as temporary:
            db=sqlite3.connect(str(Path(temporary)/'corpus.sqlite'))
            try:
                db.executescript("CREATE TABLE sentences(id INTEGER PRIMARY KEY,language TEXT,partition TEXT); CREATE TABLE links(a INTEGER,b INTEGER);")
                db.executemany("INSERT INTO sentences VALUES (?,?,?)",[
                    (1,'zh','development'),(2,'en','development'),(3,'fr','development'),
                    (4,'zh','reserved'),(5,'en','reserved'),(6,'de','development'),
                    (7,'it','development'),(8,'en','development'),(9,'zh','development')])
                db.executemany("INSERT INTO links VALUES (?,?)",[(1,2),(1,3),(2,4),(1,5),(1,6),(2,7),(7,8),(1,9)])
                count=select_changed_pair_endpoints(db,['zh','en','fr','it'],['zh'])
                self.assertEqual(count,3)
                self.assertEqual({r[0] for r in db.execute("SELECT id FROM changed_pair_endpoints")},{1,2,3})
            finally:db.close()

    def test_original_utf16_survives_normalization_and_emoji(self):
        for text,language,word,expected in [
            ('👩🏽‍💻 Mi cepillo de dientes.','es','cepillo de dientes',(1,11,29)),
            ('نَبِيّ.','ar','نبي',(1,0,6)),
            ('Un cafe\u0301.','fr','café',(1,3,8)),
            ('İyi.','en','i\u0307yi',(1,0,3))]:
            with self.subTest(text=text):
                hit=self.hits(text,language,word)
                self.assertEqual([v[:3] for v in hit],[expected])
                self.assertEqual(hit[0][3],text.encode('utf-16-le')[2*expected[1]:2*expected[2]].decode('utf-16-le'))

    def test_no_subword_or_partial_unicode_cluster_match(self):
        self.assertEqual(self.hits('A carpet.','en','car'),[])
        self.assertEqual(self.hits('İyi.','en','i'),[])

    def test_repeated_or_competing_occurrence_is_not_unique_alignment(self):
        analyses=lambda _: [[7,1,[[1,'',1]]]]
        self.assertEqual(unique_hits('[[1,0,3],[1,5,8]]',analyses),{})
        competing=lambda _: [[7,1,[[1,'',1]]],[8,1,[[1,'',1]]]]
        self.assertEqual(unique_hits('[[1,0,3]]',competing),{})
        self.assertEqual(unique_hits('[[1,0,3]]',analyses),{1:(0,3,7,1,'',1)})

    def test_carrier_focus_keeps_grammar_and_unicode_geometry(self):
        def align(actual,written,a,b,base=0):
            end=base+len(actual.encode('utf-16-le'))//2
            analyses=lambda _:[[7,1,[[1,'reading',1]],[[3,written,a,b]]]]
            return unique_hits(json.dumps([[1,base,end,actual]]),analyses)
        self.assertEqual(align('학교에서','학교에서',0,2,3),{1:(3,5,7,1,'reading',1)})
        self.assertEqual(align('الفنجان','الفنجان',2,7),{1:(2,7,7,1,'reading',1)})
        self.assertEqual(align('Ninasema','ninasema',4,8),{1:(4,8,7,1,'reading',1)})
        self.assertEqual(align('الْفنجان','الفنجان',2,7),{})
        self.assertEqual(align('학교를','학교을',0,2),{})
        self.assertEqual(align('😀x','😀x',1,2),{})
        competing=lambda _:[[7,1,[[1,'reading',1]],[[3,'학교에서',0,2],[1,'학교에서',0,4]]]]
        self.assertEqual(unique_hits('[[1,0,4,"학교에서"]]',competing),{})

    def test_new_complete_past_does_not_remove_the_existing_stem_focus(self):
        analyses=lambda _:[[7,1,[[1,'',1]],[[3,'walked',0,4],[4,'walked',0,6]]]]
        payload='[[1,2,8,"walked"]]'
        self.assertEqual(unique_hits(payload,analyses),{1:(2,6,7,1,'',1)})
        self.assertEqual(unique_hits(payload,analyses,(4,)),{1:(2,8,7,1,'',1)})
        self.assertEqual(unique_hits(payload,analyses,(1,2,3,4)),{})

    def test_whole_past_focus_preserves_the_entire_inflection(self):
        analyses=lambda _:[[7,1,[[1,'ikimashita',1]],[[4,'行きました',0,5]]]]
        self.assertEqual(unique_hits('[[1,3,8,"行きました"]]',analyses,(4,)),
            {1:(3,8,7,1,'ikimashita',1)})
        self.assertEqual(unique_hits('[[1,3,8,"行きません"]]',analyses,(4,)),{})

    def test_supplement_receipt_binds_output_and_reserved_text_stays_out(self):
        # A complete tiny build catches output-path/input-path aliasing and
        # tests partition handling across both primary and supplemental data.
        with tempfile.TemporaryDirectory(dir='artifacts') as temporary:
            root=Path(temporary);shards=root/'shards';shards.mkdir();catalog=[]
            for language,word in [('en','coffee'),('es','café'),('sw','kahawa')]:
                path=shards/(language+'.sqlite');db=sqlite3.connect(path)
                db.executescript('''CREATE TABLE metadata(key TEXT,value TEXT);
                    INSERT INTO metadata VALUES ('policy','"native-linked-adjective-agreement-10"');
                    CREATE TABLE senses(id TEXT,label TEXT,pos TEXT,explicit INTEGER,source_url TEXT);
                    CREATE TABLE lexemes(id INTEGER,source_safe INTEGER,target_safe INTEGER);
                    CREATE TABLE surfaces(normalized TEXT,lexeme INTEGER,mode INTEGER,surface TEXT,start INTEGER,end INTEGER,features TEXT);
                    CREATE TABLE terms(lexeme INTEGER,sense TEXT,reading TEXT,eligible INTEGER);''')
                db.execute('INSERT INTO senses VALUES (?,?,?,?,?)',('coffee','coffee beverage','noun',1,'https://example.test/dictionary'))
                db.execute('INSERT INTO lexemes VALUES (1,1,1)');db.execute("INSERT INTO surfaces VALUES (?,1,1,?,0,?,'[]')",(word,word,len(word)))
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
                metadata=receipt if receipt.get('schema') in {'vipi-pgv-corpus-1','vipi-massive-corpus-1'} else dict(tags_schema='tag_id,sentence_id,username,added_time')
                db.execute('INSERT INTO metadata VALUES (?,?)',('receipt',json.dumps(metadata)))
                if receipt.get('schema')=='vipi-pgv-corpus-1':
                    db.executescript('''CREATE TABLE attribution(sentence INTEGER,archive TEXT,unit TEXT);
                        CREATE TABLE link_evidence(a INTEGER,b INTEGER,archive TEXT,unit TEXT,score REAL);''')
                    db.executemany('INSERT INTO attribution VALUES (?,?,?)',[(r[0],'https://example.test/archive',str(r[0])) for r in rows])
                    db.executemany('INSERT INTO link_evidence VALUES (?,?,?,?,?)',[(a,b,'https://example.test/archive',str(a),3.0) for a,b in links])
                if receipt.get('schema')=='vipi-massive-corpus-1':
                    db.executescript('''CREATE TABLE source_rows(unit TEXT,locale TEXT,sentence INTEGER,partition TEXT,payload TEXT);
                        CREATE TABLE link_evidence(a INTEGER,b INTEGER,unit TEXT,locale TEXT,source_partition TEXT);''')
                    db.executemany('INSERT INTO source_rows VALUES (?,?,?,?,?)',
                        [(str(row[0]),row[1],row[0],'train' if row[-1]=='development' else 'test','retained fixture judgment') for row in rows])
                    db.executemany('INSERT INTO link_evidence VALUES (?,?,?,?,?)',
                        [(a,b,str(a),'sw-KE','train') for a,b in links])
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
            pgv=corpus('pgv',[
                (-4,'en','Coffee.','PGV example source',-4,'development'),
                (-3,'sw','Kahawa.','PGV example target',-4,'development'),
                (-2,'sw','Kahawa reserved.','PGV reserved',-2,'reserved'),
                (-1,'sw','Kahawa excluded.','PGV excluded',-1,'excluded-existing-source')],
                [(-4,-3),(-4,-2),(-4,-1)],dict(schema='vipi-pgv-corpus-1',complete=True,
                direct_links_only=True,automatic_alignment=True,license='CC-BY-4.0: PGV fixture',citation='Synthetic PGV fixture.'))
            pgv_output=root/'pgv-output';build(argparse.Namespace(shards=shards,corpus=pgv,supplement=None,
                language=None,max_sentences_per_language=0,output=pgv_output))
            pgv_receipt=json.loads((pgv_output/'receipt.json').read_text())
            self.assertTrue(pgv_receipt['automatic_sentence_alignment'])
            self.assertEqual(pgv_receipt['corpus_schema'],'vipi-pgv-corpus-1')
            self.assertIn('CC-BY-4.0: PGV fixture',pgv_receipt['licenses'])
            self.assertNotIn('Tatoeba',(pgv_output/'ATTRIBUTION.txt').read_text())
            with sqlite3.connect(pgv_output/'contexts.sqlite') as db:
                self.assertEqual(db.execute('SELECT id FROM sentences ORDER BY id').fetchall(),[(-4,),(-3,)])
                self.assertEqual(db.execute('SELECT count(*) FROM alignments').fetchone()[0],1)
                self.assertEqual(db.execute('SELECT sentence FROM source_attribution ORDER BY sentence').fetchall(),[(-4,),(-3,)])
                self.assertEqual(db.execute('SELECT a,b FROM source_link_evidence').fetchall(),[(-4,-3)])
                self.assertEqual(db.execute("SELECT rowid FROM sentence_search WHERE sentence_search MATCH 'coffee'").fetchall(),[(-4,)])

            massive=corpus('massive',[
                (-103,'en','Coffee.','MASSIVE fixture',-103,'development'),
                (-102,'sw','Kahawa.','MASSIVE fixture',-103,'development'),
                (-101,'sw','Kahawa held out.','MASSIVE fixture',-101,'reserved')],
                [(-103,-102),(-103,-101)],dict(schema='vipi-massive-corpus-1',complete=True,
                    policy='massive-original-train-direct-unlocalized-1',license='CC-BY-4.0: MASSIVE fixture'))
            massive_output=root/'massive-output';build(argparse.Namespace(shards=shards,corpus=massive,supplement=None,
                language=None,max_sentences_per_language=0,output=massive_output))
            mr=json.loads((massive_output/'receipt.json').read_text())
            self.assertFalse(mr['automatic_sentence_alignment'])
            self.assertEqual(mr['corpus_schema'],'vipi-massive-corpus-1')
            self.assertIn('CC-BY-4.0: MASSIVE fixture',mr['licenses'])
            self.assertNotIn('Tatoeba',(massive_output/'ATTRIBUTION.txt').read_text())
            with sqlite3.connect(massive_output/'contexts.sqlite') as db:
                self.assertEqual(db.execute('SELECT id FROM sentences ORDER BY id').fetchall(),[(-103,),(-102,)])
                self.assertEqual(db.execute('SELECT count(*) FROM alignments').fetchone()[0],1)
                self.assertEqual(db.execute('SELECT DISTINCT partition FROM source_rows').fetchall(),[('train',)])
                self.assertEqual(db.execute('SELECT a,b FROM source_link_evidence').fetchall(),[(-103,-102)])


if __name__=='__main__':unittest.main()
