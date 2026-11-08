#!/usr/bin/env python3
"""Measure retained compiled alias collisions without approving/rebuilding packs.

Counts are exposure cohorts, not semantic error counts. One verified shard is
expanded at a time; all exact Arabic cross-head alias rows are retained for a
subsequent selected read of the original native records.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import time
import zlib


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists()
    assert shutil.disk_usage(args.output.parent).free > 9 * 1024**3
    started = time.monotonic()
    catalog = json.loads(args.catalog.read_text())
    result = {'production': False, 'catalog_sha256': sha(args.catalog),
              'script_sha256': sha(Path(__file__)), 'languages': {}}
    for file in catalog['files']:
        if not file['id'].startswith('d-'):
            continue
        language = file['id'][2:]
        packed = args.catalog.parent / file['file']
        assert sha(packed) == file['compressed_sha256']
        scratch = args.output.parent / 'alias-identity-scratch.sqlite'
        assert not scratch.exists()
        decoder = zlib.decompressobj()
        digest = hashlib.sha256()
        size = 0
        with packed.open('rb') as source, scratch.open('xb') as output:
            while chunk := source.read(262144):
                data = decoder.decompress(chunk)
                size += len(data)
                assert size <= file['bytes']
                digest.update(data)
                output.write(data)
            data = decoder.flush()
            size += len(data)
            digest.update(data)
            output.write(data)
        assert decoder.eof and size == file['bytes'] and digest.hexdigest() == file['sha256']
        db = sqlite3.connect(scratch.as_uri() + '?mode=ro&immutable=1', uri=True)
        groups = defaultdict(list)
        for key, identifier, written, tags, head, pos, safe, senses in db.execute('''
                SELECT s.normalized,s.lexeme,s.surface,s.features,l.headword,l.pos,l.target_safe,l.senses
                FROM surfaces s JOIN lexemes l ON l.id=s.lexeme
                WHERE s.features LIKE '%canonical%' OR s.features LIKE '%alternative%'
                ORDER BY s.normalized,s.lexeme,s.surface'''):
            groups[key].append({'lexeme': identifier, 'written': written,
                                'tags': json.loads(tags), 'headword': head,
                                'pos': pos, 'target_safe': safe, 'native_senses': senses})
        collisions = {key: rows for key, rows in groups.items()
                      if len({row['lexeme'] for row in rows}) > 1}
        wanted = {row['lexeme'] for rows in collisions.values() for row in rows}
        readings = defaultdict(set)
        meanings = defaultdict(set)
        for identifier, sense, reading in db.execute('SELECT lexeme,sense,reading FROM terms WHERE eligible=1'):
            if identifier in wanted:
                meanings[identifier].add(sense)
                if reading:
                    readings[identifier].add(reading)
        multi_heads = {key: rows for key, rows in collisions.items()
                       if len({row['headword'] for row in rows}) > 1}
        def union(rows, values):
            return set().union(*(values[row['lexeme']] for row in rows))
        stats = {'shard_sha256': file['sha256'], 'alias_keys': len(groups),
                 'multi_lexeme_alias_keys': len(collisions),
                 'multi_headword_alias_keys': len(multi_heads),
                 'multi_reading_alias_keys': sum(len(union(rows, readings)) > 1 for rows in collisions.values()),
                 'multi_sense_alias_keys': sum(len(union(rows, meanings)) > 1 for rows in collisions.values()),
                 'multi_lexeme_entry_count': len(wanted)}
        if language == 'ar':
            stats['cross_head_aliases'] = multi_heads
            stats['coffee_rows'] = groups.get('بن', [])
            for rows in stats['cross_head_aliases'].values():
                for row in rows:
                    row['eligible_readings'] = sorted(readings[row['lexeme']])
                    row['eligible_senses'] = sorted(meanings[row['lexeme']])
        result['languages'][language] = stats
        db.close()
        scratch.unlink()
        print(language, {key: value for key, value in stats.items() if not isinstance(value, (dict, list))}, flush=True)
    result['elapsed_seconds'] = time.monotonic() - started
    result['limitations'] = [
        'Compiled canonical/alternative form cohort only; not all raw native dictionary entries.',
        'Multiple entry identities, senses or readings can be legitimate; these counts are not error estimates.',
        'Eligible reading/sense values come from the existing compiler and may themselves contain contaminated links.',
        'No runtime behavior, pack content or language admission changed.']
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(sha(args.output), args.output.stat().st_size, flush=True)


if __name__ == '__main__':
    main()
