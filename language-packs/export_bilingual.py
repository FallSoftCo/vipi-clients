#!/usr/bin/env python3
"""Export auditable native bilingual data from the pinned sense catalog.

Exports remain candidate data. Signing authenticates provenance, not linguistic
accuracy. Qualification keys are never added to a release client's trust list.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import time

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from build_wiktextract import LANGUAGES, canonical, digest_file
from context_hints import GRAMMAR, lookup_key, source_hint_lexicon, hints, has_scope, qualifiers_compatible

CATALOG_SHA256 = '547122b54c3dfb1d90f581d3d6534695a8e934787bf856d1ec828f8eb676daba'
SCHEMA = '''
PRAGMA application_id=1447645257;
PRAGMA user_version=3;
PRAGMA temp_store=FILE;
PRAGMA cache_size=-8192;
CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE senses(id TEXT PRIMARY KEY,label TEXT NOT NULL,part_of_speech TEXT NOT NULL,
 source_word TEXT NOT NULL,source_line INTEGER NOT NULL,source_url TEXT NOT NULL,
 evidence TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE vocabulary(source TEXT NOT NULL,target TEXT NOT NULL,sense_id TEXT NOT NULL
 REFERENCES senses(id),reading TEXT NOT NULL,mapping_details TEXT NOT NULL,
 PRIMARY KEY(source,sense_id,target,reading)) WITHOUT ROWID;
CREATE TABLE sense_context(sense_id TEXT PRIMARY KEY REFERENCES senses(id),hints TEXT NOT NULL) WITHOUT ROWID;
'''


def export_pair(catalog, source, target, output, revision, key, key_id):
    if source not in LANGUAGES or target not in LANGUAGES or source == target or revision < 1:
        raise ValueError('Invalid pair/revision')
    pack_id = source + '-' + target
    output.mkdir(parents=True, exist_ok=False)
    database = output / 'vocabulary.sqlite'
    extra = ' AND s.explicit=1' if source != 'en' and target != 'en' else ''
    evidence = 'direct' if source == 'en' else 'reversed_direct' if target == 'en' else 'shared_explicit_english_sense'
    with sqlite3.connect(database) as db:
        db.executescript(SCHEMA)
        db.create_function('source_key', 1, lambda value: lookup_key(value, source), deterministic=True)
        db.create_function('has_scope', 1, has_scope, deterministic=True)
        db.create_function('compatible', 3, lambda a,b,word: qualifiers_compatible(a,b,word,source,target), deterministic=True)
        db.create_function('details', 2, lambda a,b: canonical({'source':json.loads(a),'target':json.loads(b)}) if a != '{}' or b != '{}' else '{}', deterministic=True)
        # ATTACH accepts a bound filename. The source is opened immutable/read-only.
        db.execute('ATTACH DATABASE ? AS catalog', (catalog.resolve().as_uri() + '?mode=ro&immutable=1',))
        db.execute('CREATE TEMP TABLE scoped(sense_id TEXT,language TEXT,PRIMARY KEY(sense_id,language)) WITHOUT ROWID')
        db.execute('INSERT INTO scoped SELECT DISTINCT sense_id,language FROM catalog.terms WHERE language IN (?,?) AND has_scope(qualifiers)', (source,target))
        db.execute('''INSERT OR IGNORE INTO vocabulary
            SELECT source_key(a.normalized),b.form,a.sense_id,b.display_reading,details(a.qualifiers,b.qualifiers)
            FROM catalog.terms a JOIN catalog.terms b ON a.sense_id=b.sense_id
            JOIN catalog.senses s ON s.id=a.sense_id
            WHERE a.language=? AND b.language=? AND a.normalized<>b.normalized
            AND compatible(a.qualifiers,b.qualifiers,s.source_word)
            AND (has_scope(a.qualifiers) OR NOT EXISTS (SELECT 1 FROM scoped WHERE sense_id=a.sense_id AND language=a.language))
            AND (has_scope(b.qualifiers) OR NOT EXISTS (SELECT 1 FROM scoped WHERE sense_id=b.sense_id AND language=b.language))
            AND a.tags NOT LIKE '%"ironic"%' AND a.tags NOT LIKE '%"humorous"%'
            AND b.tags NOT LIKE '%"ironic"%' AND b.tags NOT LIKE '%"humorous"%' ''' + extra, (source, target))
        db.executemany('DELETE FROM vocabulary WHERE source=?', [(word,) for word in GRAMMAR[source]])
        reading_collisions = 0
        if target == 'ar':
            # Translation output normally omits Arabic short vowels. A reading
            # unique within one English sense is not unique in Arabic: فتح can
            # be fataḥa (opened) or fatḥ (opening). Check the entire catalog,
            # including senses unavailable in this source language, and abstain.
            db.create_function('arabic_key', 1, lambda value: lookup_key(value, 'ar'), deterministic=True)
            db.execute('CREATE TEMP TABLE reading_collision(form TEXT PRIMARY KEY) WITHOUT ROWID')
            db.execute('''INSERT INTO reading_collision SELECT arabic_key(form)
                FROM catalog.terms WHERE language='ar' AND display_reading<>''
                GROUP BY arabic_key(form) HAVING count(DISTINCT display_reading)>1''')
            reading_collisions = db.execute('''DELETE FROM vocabulary WHERE arabic_key(target)
                IN (SELECT form FROM reading_collision)''').rowcount
        db.execute('''INSERT INTO senses SELECT s.id,s.label,s.part_of_speech,s.source_word,s.source_line,s.source_url,?
            FROM catalog.senses s WHERE s.id IN (SELECT sense_id FROM vocabulary)''', (evidence,))
        lexicon = source_hint_lexicon(catalog, source)
        for sense_id, label, source_word in db.execute('SELECT id,label,source_word FROM senses').fetchall():
            values = hints(label, source_word, source, lexicon)
            if values: db.execute('INSERT INTO sense_context VALUES (?,?)', (sense_id, '\x1f'.join(values)))
        source_metadata = {row[0]: json.loads(row[1]) for row in db.execute('SELECT key,value FROM catalog.metadata')}
        metadata = {
            'schema': 'vipi-bilingual-3', 'pack_id': pack_id, 'source_language': source,
            'target_language': target, 'revision': str(revision), 'normalization': 'unicode-nfc-lower-arabic-harakat-v1',
            'context_policy': 'cross-sense-label-veto-2', 'qualifier_policy': 'explicit-compatible-or-abstain-1',
            'arabic_reading_policy': 'catalog-wide-collision-abstention-1',
            'quality': 'candidate', 'license': 'CC-BY-SA-4.0',
            'license_url': 'https://creativecommons.org/licenses/by-sa/4.0/',
            'attribution': 'Wiktionary contributors; extraction by Tatu Ylonen/wiktextract via Kaikki.org.',
            'source_sha256': source_metadata['upstream_sha256'],
            'source_version': source_metadata['source_version'],
            'derivation': evidence,
        }
        db.executemany('INSERT INTO metadata VALUES (?,?)', metadata.items())
        count, headwords = db.execute('SELECT count(*),count(DISTINCT source) FROM vocabulary').fetchone()
        readings, = db.execute("SELECT count(*) FROM vocabulary WHERE reading<>''").fetchone()
        if not count or db.execute('PRAGMA foreign_key_check').fetchone() is not None:
            raise ValueError('Empty or inconsistent bilingual export')
        db.commit()
        db.execute('VACUUM')
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Bilingual integrity failure')
    if database.stat().st_size > 67_108_864:
        raise ValueError('Native pack exceeds the bounded installer size')
    manifest = dict(metadata, revision=revision, schema_version=3, file='vocabulary.sqlite',
                    bytes=database.stat().st_size, sha256=digest_file(database),
                    mappings=count, headwords=headwords, readings=readings,
                    reading_collision_mappings_omitted=reading_collisions,
                    compiler='vipi-bilingual-3', compiler_sha256=digest_file(Path(__file__)),
                    context_compiler_sha256=digest_file(Path(__file__).with_name('context_hints.py')),
                    catalog_sha256=digest_file(catalog), key_id=key_id,
                    signature_algorithm='ECDSA-P256-SHA256')
    encoded = canonical(manifest).encode()
    signature = key.sign(encoded, ec.ECDSA(hashes.SHA256()))
    key.public_key().verify(signature, encoded, ec.ECDSA(hashes.SHA256()))
    (output / 'manifest.json').write_bytes(encoded)
    (output / 'manifest.sig').write_bytes(signature)
    (output / 'ATTRIBUTION.txt').write_text(
        metadata['attribution'] + '\n' + metadata['license_url'] + '\n'
        'Original entries and contributor history: senses.source_url; append ?action=history before #English.\n'
        'Changes: selected modern vocabulary, normalized source forms, split Han variants, preserved sense groups,\n'
        'conservative readable romanization and bilingual SQLite export. Full source and derivation are retained.\n'
        'Candidate mappings require contextual matching; signature does not certify translation accuracy.\n')
    return manifest


def main(args):
    if digest_file(args.catalog) != CATALOG_SHA256:
        raise ValueError('Catalog does not match the qualified provenance pin')
    if args.qualification:
        key = ec.generate_private_key(ec.SECP256R1())
    else:
        key = serialization.load_pem_private_key(args.signing_key.read_bytes(), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
        raise ValueError('Expected P-256 signing key')
    args.output.mkdir(parents=True, exist_ok=False)
    public = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    (args.output / 'signing-public-key.der').write_bytes(public)
    pairs = [tuple(pair.split('-')) for pair in args.pair] if args.pair else [(s, t) for s in LANGUAGES for t in LANGUAGES if s != t]
    started = time.monotonic()
    manifests = []
    for source, target in pairs:
        manifest = export_pair(args.catalog, source, target, args.output / (source + '-' + target), args.revision, key, args.key_id)
        manifests.append(manifest)
        print(canonical({k: manifest[k] for k in ('pack_id', 'bytes', 'headwords', 'mappings', 'readings')}), flush=True)
    (args.output / 'receipt.json').write_text(canonical({
        'quality': 'candidate', 'qualification_only_key': args.qualification,
        'private_key_written': False, 'catalog_sha256': CATALOG_SHA256,
        'compiler_sha256': digest_file(Path(__file__)), 'pairs': manifests,
        'seconds': time.monotonic() - started,
    }) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--pair', action='append', default=[])
    parser.add_argument('--revision', type=int, required=True)
    parser.add_argument('--key-id', required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--qualification', action='store_true')
    group.add_argument('--signing-key', type=Path)
    main(parser.parse_args())
