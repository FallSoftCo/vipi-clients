#!/usr/bin/env python3
"""Index pinned Swahili dictionary evidence for incremental context authoring.

Native Swahili senses and explicit English translation groups are separate
evidence. Neither a shared spelling nor a pivot makes a runtime substitution
approved. The research schema cannot be installed by either native client.
"""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import sqlite3
import time
from urllib.parse import quote

from build_wiktextract import (LANGUAGES, MAX_LINE, SCHEMA, add_entry, canonical,
    clean, coverage, digest_file, form_ok, translations)

LANGUAGES_WITH_SWAHILI = (*LANGUAGES, 'sw')
NATIVE_SCHEMA = '''
CREATE TABLE native_senses(headword TEXT NOT NULL, part_of_speech TEXT NOT NULL,
 source_line INTEGER NOT NULL, sense_index INTEGER NOT NULL, glosses TEXT NOT NULL,
 tags TEXT NOT NULL, source_url TEXT NOT NULL,
 PRIMARY KEY(source_line,sense_index)) WITHOUT ROWID;
CREATE INDEX native_sense_lookup ON native_senses(headword);
CREATE TABLE native_forms(headword TEXT NOT NULL, form TEXT NOT NULL,
 tags TEXT NOT NULL, source_line INTEGER NOT NULL,
 PRIMARY KEY(source_line,form,tags)) WITHOUT ROWID;
CREATE INDEX native_form_lookup ON native_forms(form);
'''


def collect_native(db, entry, line, counts):
    if entry.get('lang_code') != 'sw': return
    head = clean(entry.get('word', ''))
    if not form_ok(head): return
    counts['native_entries'] += 1
    url = 'https://en.wiktionary.org/wiki/' + quote(head, safe='') + '#Swahili'
    for index, sense in enumerate(entry.get('senses', [])):
        if not isinstance(sense, dict): continue
        glosses = sense.get('glosses', [])
        if not glosses or not all(isinstance(value, str) for value in glosses): continue
        db.execute('INSERT INTO native_senses VALUES (?,?,?,?,?,?,?)',
            (head, entry.get('pos', ''), line, index, canonical(glosses),
             canonical(sorted(sense.get('tags', []))), url))
        counts['native_senses'] += 1
    for form in entry.get('forms', []):
        if not isinstance(form, dict): continue
        value = clean(form.get('form', ''))
        if not form_ok(value): continue
        # Preserve upstream morphology; do not assert that every form inherits
        # every headword sense or infer arbitrary Swahili prefix/suffix rules.
        db.execute('INSERT OR IGNORE INTO native_forms VALUES (?,?,?,?)',
            (head, value, canonical(sorted(form.get('tags', []))), line))


def build(source, output, max_bytes):
    pin = json.loads(Path(__file__).with_name('sources').joinpath('wiktextract-20261021.json').read_text())
    if source.stat().st_size != pin['source_bytes'] or digest_file(source) != pin['source_sha256']:
        raise ValueError('Exact pinned full upstream dictionary required')
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic(); counts = Counter(); lines = 0
    path = output / 'swahili-evidence.sqlite'
    with sqlite3.connect(path) as db:
        db.executescript(SCHEMA + NATIVE_SCHEMA)
        with gzip.open(source, 'rb') as stream:
            while raw := stream.readline(MAX_LINE + 1):
                if len(raw) > MAX_LINE: raise ValueError('Oversized upstream record')
                lines += 1
                entry = json.loads(raw)
                if entry.get('lang_code') == 'en' and any(
                    item.get('code', item.get('lang_code')) == 'sw'
                    for _, _, _, item in translations(entry)):
                    counts['english_entries_with_swahili'] += 1
                    add_entry(db, entry, lines, counts, LANGUAGES_WITH_SWAHILI)
                collect_native(db, entry, lines, counts)
                if lines % 250_000 == 0:
                    db.commit()
                    if path.stat().st_size > max_bytes: raise ValueError('Declared index bound exceeded')
                    print(canonical({'lines':lines, 'bytes':path.stat().st_size,
                        'native_entries':counts['native_entries'], 'seconds':round(time.monotonic()-started, 2)}), flush=True)
        metadata = {'schema':'vipi-swahili-dictionary-evidence-1', 'quality':'unqualified',
            'upstream_sha256':pin['source_sha256'], 'license':'CC-BY-SA-4.0',
            'compiler_sha256':digest_file(Path(__file__)),
            'shared_compiler_sha256':digest_file(Path(__file__).with_name('build_wiktextract.py')),
            'languages':LANGUAGES_WITH_SWAHILI}
        db.executemany('INSERT INTO metadata VALUES (?,?)', [(key, canonical(value)) for key,value in metadata.items()])
        db.commit()
        if path.stat().st_size > max_bytes: raise ValueError('Declared index bound exceeded')
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise ValueError('Invalid database')
        if db.execute('PRAGMA foreign_key_check').fetchone() is not None: raise ValueError('Broken reference')
        pairs = [row for row in coverage(db, LANGUAGES_WITH_SWAHILI) if 'sw' in (row['source'], row['target'])]
        counts['native_headwords'] = db.execute('SELECT count(DISTINCT headword) FROM native_senses').fetchone()[0]
        counts['native_forms'] = db.execute('SELECT count(*) FROM native_forms').fetchone()[0]
    receipt = {**metadata, 'source_entries_read':lines, 'complete_source_scan':True,
        'counts':dict(counts), 'pairs':pairs, 'bytes':path.stat().st_size,
        'sha256':digest_file(path), 'seconds':round(time.monotonic()-started, 2),
        'release_ready':False, 'runtime_promotion':False,
        'limits':['Native analyses can be incomplete, redundant or ambiguous.',
            'Shared explicit English senses are pivot evidence, not independent translations.',
            'Native forms are retained as evidence without inferred morphology.',
            'No reserved conversation corpus supplies this index or approves these candidates.']}
    (output/'receipt.json').write_text(canonical(receipt)+'\n')
    (output/'ATTRIBUTION.txt').write_text(
        'Wiktionary contributors; extracted by Tatu Ylonen/wiktextract via Kaikki.org.\n'
        'CC BY-SA 4.0: https://creativecommons.org/licenses/by-sa/4.0/\n'
        'Pinned upstream: '+pin['source_url']+'\n'
        'Original entry URLs and source lines remain in the database. Contributor history is available at each entry.\n'
        'Changes: Swahili native gloss/form selection; English explicit translation-group selection; filtering and SQLite indexing.\n'
        'Research evidence only. No examples, quotations, recordings or IPA fields are included.\n')
    print(canonical(receipt), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-bytes', type=int, default=134_217_728)
    args = parser.parse_args()
    if args.max_bytes < 1: parser.error('Positive storage bound required')
    build(args.source, args.output, args.max_bytes)
