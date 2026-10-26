#!/usr/bin/env python3
"""Audit a staged catalog without promoting it or inferring linguistic approval."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def audit(baseline, current):
    before = json.loads((baseline / 'catalog.json').read_text())
    after = json.loads((current / 'catalog.json').read_text())
    old = {(r['pair'], r['original']): r['translation'] for r in before['references']}
    new = {(r['pair'], r['original']): r['translation'] for r in after['references']}
    if len(old) != len(before['references']) or len(new) != len(after['references']):
        raise ValueError('Duplicate whole-reference key')
    changed = [{'pair': pair, 'original': original} for (pair, original), text in old.items()
               if new.get((pair, original)) != text]
    units = unchanged = byte_count = 0
    conflicts = []
    for group, suffix in [('packs', ''), ('contexts', '-contexts')]:
        for entry in after[group]:
            path = current / (entry['id'] + suffix + '.sqlite')
            if path.stat().st_size != entry['bytes'] or sha(path) != entry['sha256']:
                raise ValueError('Changed staged database: ' + str(path))
            byte_count += entry['bytes']
            if group != 'packs':
                continue
            senses, readings = {}, {}
            with sqlite3.connect('file:' + str(path.resolve()) + '?mode=ro', uri=True) as db:
                for (payload,) in db.execute('SELECT payload FROM mappings'):
                    row = json.loads(payload)
                    if not row.get('lexical_unit'):
                        continue
                    units += 1
                    if row['source'].casefold() == row['target'].casefold() and row['target_language'] not in ('ar', 'zh', 'ja', 'ko'):
                        unchanged += 1
                    senses.setdefault(row['source'], set()).add(row['meaning'])
                    readings.setdefault((row['source'], row['target']), set()).add(row['reading'])
            for source, values in senses.items():
                if len(values) > 1:
                    conflicts.append({'pair': entry['id'], 'source': source, 'meanings': sorted(values)})
            for (source, target), values in readings.items():
                if len(values) > 1:
                    conflicts.append({'pair': entry['id'], 'source': source, 'target': target,
                                      'readings': sorted(values)})
    return {'schema': 'vipi-bundled-unit-audit-1', 'baseline_catalog_sha256': sha(baseline / 'catalog.json'),
            'catalog_sha256': sha(current / 'catalog.json'), 'database_bytes': byte_count,
            'lexical_units': units, 'unchanged_latin_forms': unchanged, 'references': len(new),
            'added_references': len(new.keys() - old.keys()), 'changed_or_missing_references': changed,
            'conflicts': conflicts, 'passed': not changed and not conflicts,
            'independent_linguistic_acceptance': False, 'release_ready': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--current', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.baseline, args.current)
    with args.output.open('x') as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
        output.write('\n')
    print(json.dumps(result, ensure_ascii=False))
    if not result['passed']:
        raise SystemExit('Staged catalog withheld: audit failed')
