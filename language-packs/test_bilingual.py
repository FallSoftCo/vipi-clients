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
            ('coffee', 'drink', [('zh', '咖啡', 'kāfēi'), ('ja', 'コーヒー', 'kōhī'), ('ko', '커피', 'keopi'), ('ar', 'قهوة', 'qahwa')]),
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
        self.assertEqual(manifest['schema_version'], 3)
        with self.assertRaises(InvalidSignature):
            self.key.public_key().verify(signature, raw.replace(b'candidate', b'approved'), ec.ECDSA(hashes.SHA256()))
        with self.assertRaises(FileExistsError):
            self.export('en', 'zh')


if __name__ == '__main__':
    unittest.main()
