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
            self.assertEqual(result.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertGreater(result.execute('SELECT count(*) FROM references_used').fetchone()[0], 0)
            result.close()


if __name__ == '__main__':
    unittest.main()
