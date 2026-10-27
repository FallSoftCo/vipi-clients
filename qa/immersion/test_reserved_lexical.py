"""Ensure the fresh evaluator cannot admit development or duplicate neighbors."""
import bz2
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent


class ReservedEvaluationTests(unittest.TestCase):
    def test_direct_reserved_endpoints_and_complete_swahili_duplicate_groups(self):
        with tempfile.TemporaryDirectory(prefix='vipi-reserved-test-') as directory:
            root = Path(directory)
            for name in ['corpus', 'contexts', 'shards', 'swahili', 'exports', 'snapshot']:
                (root / name).mkdir()
            sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
            write = lambda path, data: path.write_text(json.dumps(data))
            db = sqlite3.connect(root / 'corpus/corpus.sqlite')
            db.executescript('''CREATE TABLE sentences(id INTEGER PRIMARY KEY,language,text,owner,component,partition);
                CREATE TABLE links(a,b);CREATE TABLE tags(sentence,tag);CREATE TABLE tag_metadata(id,name);''')
            db.executemany('INSERT INTO sentences VALUES (?,?,?,?,?,?)', [
                (1, 'en', 'development', 'owner', 1, 'development'),
                (2, 'en', 'reserved one', 'owner', 2, 'reserved'),
                (3, 'es', 'reserva uno', 'owner', 2, 'reserved'),
                (4, 'en', 'reserved two', 'owner', 4, 'reserved'),
                (5, 'es', 'reserva dos', 'owner', 4, 'reserved')])
            db.executemany('INSERT INTO links VALUES (?,?)', [(2, 3), (4, 5)])
            db.execute("INSERT INTO tag_metadata VALUES (1,'@needs_native_check')")
            db.commit()
            db.close()

            def archive(name, member, text):
                value = text.encode()
                with tarfile.open(root / 'exports' / name, 'w:bz2') as stream:
                    item = tarfile.TarInfo(member)
                    item.size = len(value)
                    stream.addfile(item, io.BytesIO(value))

            archive('links.tar.bz2', 'links.csv', '1000\t2\n1001\t1\n1002\t2\n1003\t2\n1005\t2\n')
            archive('tags_detailed.tar.bz2', 'tags_detailed.csv', '1\t1005\towner\t2026-10-24\n')
            modified = 'Sat, 24 Oct 2026 06:41:06 GMT'
            assets = [dict(file=name, sha256=sha(root / 'exports' / name), last_modified=modified)
                for name in ['links.tar.bz2', 'tags_detailed.tar.bz2']]
            write(root / 'exports/receipt.json', dict(assets=assets))
            corpus_sha = sha(root / 'corpus/corpus.sqlite')
            write(root / 'corpus/receipt.json', dict(sha256=corpus_sha,
                source_receipt_sha256=sha(root / 'exports/receipt.json')))
            sw = [(1000, 'valid'), (1001, 'mixed'), (1002, 'mixed'), (1003, 'orphan'), (1004, 'orphan'), (1005, 'flagged')]
            text = ''.join(f'{i}\tswh\t{value}\towner\tdate\tdate\n' for i, value in sw)
            (root / 'swahili/swh_sentences_detailed.tsv.bz2').write_bytes(bz2.compress(text.encode()))
            write(root / 'swahili/receipt.json', dict(sha256=sha(root / 'swahili/swh_sentences_detailed.tsv.bz2'), last_modified=modified))
            db = sqlite3.connect(root / 'contexts/contexts.sqlite')
            db.execute('CREATE TABLE sentences(id INTEGER PRIMARY KEY)')
            db.execute('INSERT INTO sentences VALUES (1)')
            db.commit()
            db.close()
            write(root / 'contexts/receipt.json', dict(complete=True, corpus_partition='development',
                corpus_sha256=corpus_sha, source_release_id='test-release', sha256=sha(root / 'contexts/contexts.sqlite')))
            (root / 'shards/en.sqlite').write_bytes(b'qualification-only-hash-fixture')
            write(root / 'shards/catalog.json', dict(schema='vipi-lexical-shards-1', release_id='test-release',
                shards=[dict(language='en', sha256=sha(root / 'shards/en.sqlite'))]))
            (root / 'snapshot/source.txt').write_text('frozen selector')
            write(root / 'snapshot/receipt.json', dict(files=[dict(path='source.txt', sha256=sha(root / 'snapshot/source.txt'))]))
            command = [sys.executable, str(ROOT / 'prepare_reserved_lexical.py')]
            for name in ['corpus', 'contexts', 'shards', 'swahili', 'exports']:
                path = root / name
                if name in ['corpus', 'contexts']:
                    path /= name + '.sqlite'
                command += ['--' + name, str(path)]
            command += ['--native-snapshot', str(root / 'snapshot'), '--output', str(root / 'result')]
            subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
            rows = json.loads((root / 'result/cases.json').read_text())
            self.assertEqual({row['source_id'] for row in rows} | {row['target_id'] for row in rows}, {2, 3, 4, 5, 1000})
            self.assertEqual({(row['source'], row['target']) for row in rows}, {('en', 'es'), ('es', 'en'), ('sw', 'en'), ('en', 'sw')})
            manifest = json.loads((root / 'result/manifest.json').read_text())
            self.assertEqual(manifest['cases'], 6)
            self.assertEqual(manifest['cases_sha256'], sha(root / 'result/cases.json'))
            self.assertTrue(manifest['all_endpoints_absent_from_context_build'])
            self.assertFalse(manifest['independent_semantic_acceptance'])


if __name__ == '__main__':
    unittest.main()
