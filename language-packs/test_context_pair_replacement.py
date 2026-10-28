import argparse
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from build_wiktextract import digest_file
from replace_context_witness_pairs import replace


class PairReplacement(unittest.TestCase):
    def test_complete_pair_replacement_removes_old_successes_and_keeps_other_pairs(self):
        with tempfile.TemporaryDirectory(dir='artifacts') as directory:
            root=Path(directory)
            def fixture(name,rows,requested=None):
                folder=root/name;folder.mkdir();path=folder/'witnesses.sqlite'
                db=sqlite3.connect(path)
                db.executescript('''CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                    CREATE TABLE witnesses(source TEXT,target TEXT,word TEXT,counterpart TEXT,cue TEXT,support INTEGER,total INTEGER,
                        PRIMARY KEY(source,target,word,counterpart,cue));
                    CREATE TABLE evidence(source TEXT,target TEXT,word TEXT,counterpart TEXT,cue TEXT,sentence INTEGER,translation INTEGER,
                        PRIMARY KEY(source,target,word,counterpart,cue,sentence));
                    CREATE TABLE references_used(sentence INTEGER PRIMARY KEY,owner TEXT NOT NULL);''')
                db.executemany('INSERT INTO witnesses VALUES (?,?,?,?,?,?,?)',rows)
                pairs={a+'-'+b:n for a,b,n in db.execute('SELECT source,target,count(*) FROM witnesses GROUP BY source,target')}
                meta=dict(schema='vipi-context-witnesses-1',policy='experimental-direct-reference-agreement-1',
                    source_release_id='a'*64,source_contexts_sha256='b'*64,minimum_support=3,minimum_agreement=.98,
                    counts=dict(witnesses=len(rows)),pairs=pairs,compiler_sha256='c'*64,license='Synthetic test data',release_ready=False)
                if requested:meta.update(requested_pairs=requested,additional_contexts_sha256=['d'*64],disjoint_source_proof={'policy':'synthetic proof'})
                db.executemany('INSERT INTO metadata VALUES (?,?)',[(k,json.dumps(v)) for k,v in meta.items()]);db.commit();db.close()
                (folder/'receipt.json').write_text(json.dumps(dict(meta,complete=True,sha256=digest_file(path))))
                (folder/'ATTRIBUTION.txt').write_text('Synthetic '+name+' fixture.\n')
                return path
            base=fixture('base',[('sw','en','kitu','thing','@whole',3,3),('en','sw','cat','paka','@whole',3,3),
                ('es','en','casa','house','@whole',3,3)],['sw-en','en-sw','es-en','ja-sw'])
            delta=fixture('delta',[('en','sw','dog','mbwa','@whole',4,4)],['sw-en','en-sw'])
            output=root/'output';replace(argparse.Namespace(base=base,replacement=delta,output=output))
            with sqlite3.connect(output/'witnesses.sqlite') as db:
                self.assertEqual(db.execute('SELECT word,counterpart FROM witnesses ORDER BY word').fetchall(),[('casa','house'),('dog','mbwa')])
                meta={k:json.loads(v) for k,v in db.execute('SELECT key,value FROM metadata')}
            self.assertNotIn('sw-en',meta['pairs'])
            self.assertEqual(meta['pair_input_revisions']['sw-en'],digest_file(delta))
            self.assertEqual(meta['pair_input_revisions']['es-en'],digest_file(base))
            self.assertEqual(meta['pair_input_revisions']['ja-sw'],digest_file(base))
            self.assertEqual(set(meta['requested_pairs']),{'sw-en','en-sw','es-en','ja-sw'})
            self.assertNotIn('ja-sw',meta['pairs'])
            self.assertFalse(meta['release_ready'])
            self.assertEqual(json.loads((output/'receipt.json').read_text())['sha256'],digest_file(output/'witnesses.sqlite'))
            # Declaring fewer processed pairs cannot silently keep/delete data.
            with sqlite3.connect(delta) as db:
                db.execute("UPDATE metadata SET value=? WHERE key='requested_pairs'",(json.dumps(['sw-en']),));db.commit()
            receipt=json.loads((delta.parent/'receipt.json').read_text());receipt['sha256']=digest_file(delta)
            (delta.parent/'receipt.json').write_text(json.dumps(receipt))
            with self.assertRaises(AssertionError):replace(argparse.Namespace(base=base,replacement=delta,output=root/'rejected'))


if __name__=='__main__':unittest.main()
