#!/usr/bin/env python3
"""Before/after candidate identity on retained primary cohorts, not meaning QA."""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'language-packs'))
from build_wiktextract import EXCLUDED
from context_hints import lookup_key
from native_lemma_links import NativeLinks


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(text):
    return unicodedata.normalize('NFC', text).lower().replace('\u0640', '')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--primary-dir', type=Path, required=True)
    p.add_argument('--cohort', type=Path, required=True)
    p.add_argument('--before', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    assert not a.output.exists()
    receipt = json.loads((a.primary_dir/'receipt.json').read_text())
    assert receipt['complete']
    db = sqlite3.connect(':memory:')
    db.executescript('''
      CREATE TABLE native_entries(source_line INTEGER PRIMARY KEY,language TEXT,headword TEXT,
        normalized TEXT,part_of_speech TEXT,tags TEXT,source_url TEXT);
      CREATE TABLE native_senses(source_line INTEGER,sense_index INTEGER,glosses TEXT,tags TEXT,form_of TEXT,alt_of TEXT);
      CREATE TABLE native_forms(source_line INTEGER,form TEXT,normalized TEXT,tags TEXT);
      CREATE INDEX forms_key ON native_forms(normalized);
      CREATE INDEX entry_key ON native_entries(language,normalized);
    ''')
    entries, forms, senses = [], [], []
    for file in receipt['batches']:
        path = a.primary_dir/file['file']
        assert sha(path) == file['sha256']
        batch = json.loads(gzip.decompress(path.read_bytes()))
        entries += batch['entries']; forms += batch['forms']; senses += batch['senses']
    db.executemany('INSERT INTO native_entries VALUES (?,?,?,?,?,?,?)', entries)
    db.executemany('INSERT INTO native_senses VALUES (?,?,?,?,?,?)', senses)
    db.executemany('INSERT INTO native_forms VALUES (?,?,?,?)', forms)
    spec = importlib.util.spec_from_file_location('native_links_before', a.before)
    previous = importlib.util.module_from_spec(spec); spec.loader.exec_module(previous)
    old, new = previous.NativeLinks(db, 'ar', {}), NativeLinks(db, 'ar', {})
    keys = set(json.loads(a.cohort.read_text())['languages']['ar']['cross_head_aliases'])
    queries = set(keys)
    expected = defaultdict(set)
    for identifier, _, head, key, *_ in entries:
        if key in keys:
            queries.add(head)
            expected[head].add(identifier)
    for identifier, written, key, tags in forms:
        tags = set(json.loads(tags))
        if key in keys and tags & {'canonical', 'alternative'} and not tags & EXCLUDED:
            queries.add(written)
            expected[written].add(identifier)
    rows, counts = [], Counter()
    for query in sorted(queries):
        before, after = set(old.candidates(query)), set(new.candidates(query))
        marked = lookup_key(query, 'ar') != identity(query)
        missing = expected[query] - after
        assert not missing, (query, missing)
        assert after <= before
        if not marked:
            assert after == before
        counts['queries'] += 1
        counts['marked_queries' if marked else 'unmarked_queries'] += 1
        counts['before_entry_links'] += len(before)
        counts['after_entry_links'] += len(after)
        counts['removed_entry_links'] += len(before - after)
        counts['changed_queries'] += before != after
        counts['query_without_candidate_after'] += not after
        counts['exact_attested_identities_preserved'] += len(expected[query])
        if before != after:
            rows.append({'query': query, 'key': lookup_key(query, 'ar'), 'marked': marked,
                         'before': sorted(before), 'after': sorted(after),
                         'removed': sorted(before - after), 'attested_exact_ids': sorted(expected[query])})
    old.close(); new.close(); db.close()
    reading_groups = defaultdict(set)
    for identifier, form, key, tags in forms:
        if 'romanization' in json.loads(tags):
            reading_groups[identifier].add(form)
    cross_head_reading_risks = []
    heads = {r[0]: r[2] for r in entries}
    for identifier, written, key, tags in forms:
        if set(json.loads(tags)) & {'canonical', 'alternative'} and key in keys and key != lookup_key(heads[identifier], 'ar'):
            cross_head_reading_risks.append({'lexeme': identifier, 'headword': heads[identifier], 'alias': written,
                'entry_romanizations': sorted(reading_groups[identifier]),
                'state': 'Alias reading is not automatically the head reading; exact form-specific evidence required.'})
    out = {'production': False, 'semantic_error_estimate': False,
           'input_hashes': {'primary_receipt': sha(a.primary_dir/'receipt.json'), 'cohort': sha(a.cohort),
                            'before': sha(a.before), 'after': sha(ROOT/'language-packs/native_lemma_links.py'),
                            'qualifier': sha(Path(__file__))},
           'primary_entries': len(entries), 'primary_senses': len(senses), 'primary_forms': len(forms),
           'alias_keys': len(keys), 'counts': dict(counts), 'changed_query_rows': rows,
           'cross_head_reading_risks': cross_head_reading_risks,
           'limitations': ['Primary records of compiled cohort IDs; not every unexported raw homograph.',
                          'Queries are supplied head/canonical/alternative forms and bare cohort keys; not conversational frequency or all raw bilingual translation terms.',
                          'Removal means unsupported exact identity for the supplied marked form, not a manually labeled wrong translation count.',
                          'Unvocalized ambiguity and alias-specific reading provenance remain unresolved separately.',
                          'No packaged DB, cache or native runtime changed.']}
    a.output.write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'sha256': sha(a.output), 'counts': out['counts'], 'entries': len(entries), 'cross_head_reading_rows': len(cross_head_reading_risks)}))


if __name__ == '__main__':
    main()
