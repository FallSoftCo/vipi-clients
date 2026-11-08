#!/usr/bin/env python3
"""Read frozen compiled-cohort entry IDs by primary key, not a remote join.

This qualifies only represented compiled entries, not absent raw homographs.
Each 32-entry batch is retained before the next bounded read.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import time


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--inventory', type=Path, required=True)
    p.add_argument('--cohort', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seconds', type=int, default=900)
    a = p.parse_args()
    a.output.mkdir(exist_ok=True)
    cohort = json.loads(a.cohort.read_text())['languages']['ar']['cross_head_aliases']
    selected = {r['lexeme']: r['headword'] for rows in cohort.values() for r in rows}
    identifiers = sorted(selected)
    binding = {'cohort_sha256': sha(a.cohort), 'script_sha256': sha(Path(__file__)),
               'expected_archive_sha256': '8c97e9de2ce8e94ce9754475a85eb27cd956ee0ba69491fe270376e3177ceb17'}
    started = time.monotonic()
    assert a.inventory.stat().st_size == 4428693504
    db = sqlite3.connect(a.inventory.as_uri() + '?mode=ro&immutable=1', uri=True)
    db.execute('PRAGMA query_only=ON')
    db.execute('PRAGMA cache_size=-8192')
    db.set_progress_handler(lambda: int(time.monotonic() - started > a.seconds), 10000)
    receipts = []
    for offset in range(0, len(identifiers), 32):
        ids = identifiers[offset:offset + 32]
        path = a.output / f'batch-{offset:04d}.json.gz'
        if path.exists():
            batch = json.loads(gzip.decompress(path.read_bytes()))
            assert batch['binding'] == binding and batch['ids'] == ids
        else:
            if time.monotonic() - started > a.seconds:
                break
            marks = ','.join('?' for _ in ids)
            try:
                entries = db.execute('SELECT * FROM native_entries WHERE source_line IN (' + marks + ') ORDER BY source_line', ids).fetchall()
                senses = db.execute('SELECT * FROM native_senses WHERE source_line IN (' + marks + ') ORDER BY source_line,sense_index', ids).fetchall()
                forms = db.execute('SELECT * FROM native_forms WHERE source_line IN (' + marks + ') ORDER BY source_line,form,tags', ids).fetchall()
            except sqlite3.OperationalError as error:
                print('bounded_stop', str(error), flush=True)
                break
            assert len(entries) == len(ids)
            assert all(r[1] == 'ar' and r[2] == selected[r[0]] for r in entries)
            batch = {'binding': binding, 'ids': ids, 'entries': entries, 'senses': senses, 'forms': forms}
            path.write_bytes(gzip.compress(json.dumps(batch, ensure_ascii=False, separators=(',', ':')).encode(), mtime=0))
        receipts.append({'file': path.name, 'sha256': sha(path), 'bytes': path.stat().st_size})
        print('entries', min(offset + 32, len(identifiers)), '/', len(identifiers), 'elapsed', round(time.monotonic() - started, 2), flush=True)
    db.close()
    result = {'binding': binding, 'complete': len(receipts) == (len(identifiers) + 31) // 32,
              'selected_entry_count': len(identifiers), 'alias_key_count': len(cohort),
              'whole_archive_fresh_hash_verified': False, 'batches': receipts,
              'elapsed_seconds': time.monotonic() - started,
              'scope': 'Raw primary records of IDs represented in the compiled cross-head alias cohort; absent raw entries not included.'}
    (a.output / 'receipt.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
