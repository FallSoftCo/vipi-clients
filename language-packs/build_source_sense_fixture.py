#!/usr/bin/env python3
"""Reproducible synthetic compiler-to-native regression fixture; never release data."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from build_wiktextract import SCHEMA, add_entry
from export_bilingual import export_pair


def build(output):
    output.mkdir(parents=True, exist_ok=False)
    catalog = output / 'catalog.sqlite'
    with sqlite3.connect(catalog) as db:
        db.executescript(SCHEMA)
        entries = [
            ('bank', 'noun', 'financial institution', 'es', 'banco'),
            ('bank', 'noun', 'edge of a river', 'fr', 'rive'),
            # Equal glosses must not collapse different POS identities.
            ('bank', 'verb', 'edge of a river', 'fr', 'border'),
            ('coffee', 'noun', 'drink', 'es', 'café'),
            ("don't", 'verb', 'negative auxiliary', 'es', 'no'),
            ('don’t', 'verb', 'negative auxiliary', 'es', 'no'),
        ]
        for line, (word, pos, label, lang, target) in enumerate(entries, 1):
            add_entry(db, {'lang_code': 'en', 'word': word, 'pos': pos,
                          'translations': [{'code': lang, 'word': target, 'sense': label}]}, line, Counter())
        db.executemany('INSERT INTO metadata VALUES (?,?)', [
            ('upstream_sha256', json.dumps('synthetic-source-senses')),
            ('source_version', json.dumps('synthetic-regression-only'))])
    key = ec.generate_private_key(ec.SECP256R1())
    manifest = export_pair(catalog, 'en', 'es', output / 'pack', 1, key, 'source-senses-test')
    (output / 'pack/signing-public-key.der').write_bytes(key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo))
    print(json.dumps({'schema': manifest['schema_version'], 'unmapped_source_senses': manifest['unmapped_source_senses'],
                      'database_sha256': manifest['sha256'], 'qualification_only': True}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output)
