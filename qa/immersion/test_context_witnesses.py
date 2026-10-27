"""Adversarial input checks for experimental context evidence compilation."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ContextEvidenceTests(unittest.TestCase):
    def test_duplicate_sense_rows_do_not_inflate_support_or_resolve_conflicts(self):
        with tempfile.TemporaryDirectory(prefix='vipi-context-test-') as directory:
            root = Path(directory)
            source = root / 'contexts.sqlite'
            db = sqlite3.connect(source)
            db.executescript('''
                CREATE TABLE sentences(id INTEGER PRIMARY KEY,language TEXT,text TEXT,owner TEXT);
                CREATE TABLE alignments(a INTEGER,b INTEGER,a_start INTEGER,a_end INTEGER,b_start INTEGER,b_end INTEGER);
            ''')
            next_id = 1

            def reference(original, translation, word, target, repeats=1):
                nonlocal next_id
                a, b = next_id, next_id + 1
                next_id += 2
                db.executemany('INSERT INTO sentences VALUES (?,?,?,?)',
                    [(a, 'en', original, 'source-contributor'), (b, 'es', translation, 'target-contributor')])
                offset = lambda text, term: len(text[:text.index(term)].encode('utf-16-le')) // 2
                start, end = offset(original, word), offset(translation, target)
                row = a, b, start, start + len(word), end, end + len(target)
                db.executemany('INSERT INTO alignments VALUES (?,?,?,?,?,?)', [row] * repeats)

            # Duplicate dictionary-sense alignments and repeated references to
            # one sentence must not supply the three required observations.
            reference('a bicycle works', 'una bicicleta funciona', 'bicycle', 'bicicleta', 10)
            # Three direct, distinct source contexts corroborate the same pair.
            for tail in ['works', 'stops', 'moves']:
                reference('😀 my train ' + tail, 'mi tren ' + tail, 'train', 'tren', 2)
            # Four observations split across competing translations remain
            # disputed even if one counterpart occurs three times.
            for tail in ['opens', 'closes', 'waits']:
                reference('the bank ' + tail, 'el banco ' + tail, 'bank', 'banco')
            reference('the bank floods', 'la orilla inunda', 'bank', 'orilla')
            # A frequent word in the previous sentence supplies no local cue.
            for tail in ['one', 'two', 'three']:
                reference('sunny. table ' + tail, 'mesa ' + tail, 'table', 'mesa')
            db.commit()
            db.close()
            sha = hashlib.sha256(source.read_bytes()).hexdigest()
            (root / 'receipt.json').write_text(json.dumps(dict(
                schema='vipi-broad-lexical-contexts-2', complete=True, pilot=False,
                sha256=sha, languages=['en', 'es'], source_release_id='a' * 64)))
            (root / 'ATTRIBUTION.txt').write_text('Synthetic source provenance for the compiler test.\n')
            output = root / 'compiled'
            subprocess.run([sys.executable, str(ROOT / 'language-packs/build_context_witnesses.py'),
                '--contexts', str(source), '--pair', 'en-es', '--pair', 'es-en',
                '--output', str(output)], check=True, stdout=subprocess.DEVNULL)
            result = sqlite3.connect(output / 'witnesses.sqlite')
            rows = result.execute('SELECT source,target,word,counterpart,cue,support,total FROM witnesses').fetchall()
            self.assertIn(('en', 'es', 'train', 'tren', 'L:my', 3, 3), rows)
            self.assertFalse(any(row[2] in {'bicycle', 'bank'} for row in rows))
            self.assertFalse(any(row[4] == 'L:sunny' for row in rows))
            receipt = json.loads((output / 'receipt.json').read_text())
            self.assertEqual(receipt['sha256'], hashlib.sha256((output / 'witnesses.sqlite').read_bytes()).hexdigest())
            self.assertFalse(receipt['release_ready'])
            self.assertIn('Synthetic source provenance', (output / 'ATTRIBUTION.txt').read_text())
            self.assertEqual(result.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertGreater(result.execute('SELECT count(*) FROM references_used').fetchone()[0], 0)
            result.close()
            # Adding a corpus must change the denominator, not simply union
            # its successful witnesses with the older successful witnesses.
            parent=json.loads((root/'receipt.json').read_text())
            parent.update(corpus_sha256='b'*64,corpus_receipt_sha256='c'*64,supplemental_receipts=[])
            (root/'receipt.json').write_text(json.dumps(parent))
            extra=root/'delta';extra.mkdir();extra_db=extra/'contexts.sqlite'
            with sqlite3.connect(extra_db) as db:
                db.executescript('''CREATE TABLE sentences(id INTEGER PRIMARY KEY,language TEXT,text TEXT,owner TEXT);
                    CREATE TABLE alignments(a INTEGER,b INTEGER,a_start INTEGER,a_end INTEGER,b_start INTEGER,b_end INTEGER);''')
                for i,(left,right,word,target) in enumerate([
                    ('my bicycle works','mi bicicleta funciona','bicycle','bicicleta'),
                    ('your bicycle works','tu bicicleta funciona','bicycle','bicicleta'),
                    ('my train fails','mi autobús falla','train','autobús')],1):
                    a,b=-2*i,-2*i-1
                    db.executemany('INSERT INTO sentences VALUES (?,?,?,?)',[(a,'en',left,'new-source'),(b,'es',right,'new-target')])
                    x,y=left.index(word),right.index(target)
                    db.execute('INSERT INTO alignments VALUES (?,?,?,?,?,?)',(a,b,x,x+len(word),y,y+len(target)))
            exclusions=root/'exclusions';exclusions.mkdir();hashes=exclusions/'hashes.sqlite'
            with sqlite3.connect(hashes) as db:db.execute('CREATE TABLE hashes(digest BLOB PRIMARY KEY)')
            digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
            (exclusions/'receipt.json').write_text(json.dumps(dict(complete=True,sha256=digest(hashes),
                source_corpus_sha256='b'*64,source_corpus_receipt_sha256='c'*64)))
            corpus_receipt=extra/'source-corpus-receipt.json'
            corpus_receipt.write_text(json.dumps(dict(sha256='d'*64,direct_links_only=True,exclusions_sha256=digest(hashes))))
            (extra/'receipt.json').write_text(json.dumps(dict(schema='vipi-broad-lexical-contexts-3',complete=True,pilot=False,
                sha256=digest(extra_db),languages=['en','es'],source_release_id='e'*64,corpus_schema='vipi-pgv-corpus-1',
                corpus_receipt_sha256=digest(corpus_receipt),corpus_sha256='d'*64,automatic_sentence_alignment=True,
                licenses=['Synthetic delta license'])))
            (extra/'ATTRIBUTION.txt').write_text('Synthetic delta source provenance.\n')
            adapter=root/'adapter';adapter.mkdir();adapter_db=adapter/'witnesses.sqlite';adapter_db.write_bytes(b'synthetic adapter')
            (adapter/'receipt.json').write_text(json.dumps(dict(sha256=digest(adapter_db),
                adaptation_policy='unchanged-dictionary-links-added-carriers-1',source_contexts_sha256=sha,
                context_compilation_release_id='a'*64,source_release_id='e'*64,
                adaptation_proof={'en':dict(senses_added=0,terms_added=0)})))
            combined=root/'combined'
            command=[sys.executable,str(ROOT/'language-packs/build_context_witnesses.py'),
                '--contexts',str(source),'--additional-context',str(extra_db),
                '--additional-corpus-receipt',str(corpus_receipt),'--source-exclusions',str(hashes),
                '--release-adapter',str(adapter_db),'--pair','en-es','--pair','es-en','--output',str(combined)]
            subprocess.run(command,check=True,stdout=subprocess.DEVNULL)
            with sqlite3.connect(combined/'witnesses.sqlite') as db:
                self.assertEqual(db.execute("SELECT support,total FROM witnesses WHERE source='en' AND word='bicycle' AND cue='R:works'").fetchall(),[(3,3)])
                self.assertEqual(db.execute("SELECT count(*) FROM witnesses WHERE source='en' AND word='train' AND cue='L:my'").fetchone()[0],0)
            merged=json.loads((combined/'receipt.json').read_text())
            self.assertEqual(merged['source_release_id'],'e'*64)
            self.assertEqual(merged['observations_sha256'],digest(combined/'observations.sqlite'))
            self.assertTrue(merged['automatic_sentence_alignment'])
            self.assertIn('Synthetic delta source provenance',(combined/'ATTRIBUTION.txt').read_text())
            # A different exclusion identity cannot justify combining sources.
            wrong=json.loads(corpus_receipt.read_text());wrong['exclusions_sha256']='f'*64;corpus_receipt.write_text(json.dumps(wrong))
            failed=subprocess.run(command[:-1]+[str(root/'rejected')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            self.assertNotEqual(failed.returncode,0)


if __name__ == '__main__':
    unittest.main()
