#!/usr/bin/env python3
"""Bounded selected archive reads, checkpointing every 32 normalized aliases."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import time


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def emit(path, value):
    path.write_bytes(gzip.compress(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode(), mtime=0))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--inventory', type=Path, required=True)
    p.add_argument('--cohort', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seconds', type=int, default=300)
    a = p.parse_args()
    a.output.mkdir(exist_ok=True)
    started = time.monotonic()
    assert a.inventory.stat().st_size == 4428693504
    cohort = json.loads(a.cohort.read_text())
    keys = sorted(cohort['languages']['ar']['cross_head_aliases'])
    binding = {'cohort_sha256': sha(a.cohort), 'script_sha256': sha(Path(__file__)),
               'expected_archive_sha256': '8c97e9de2ce8e94ce9754475a85eb27cd956ee0ba69491fe270376e3177ceb17'}
    db = sqlite3.connect(a.inventory.as_uri() + '?mode=ro&immutable=1', uri=True)
    db.execute('PRAGMA cache_size=-8192')
    db.execute('PRAGMA query_only=ON')
    db.set_progress_handler(lambda: int(time.monotonic() - started > a.seconds), 10000)
    receipts = []
    for start in range(0, len(keys), 32):
        group = keys[start:start + 32]
        path = a.output / f'batch-{start:04d}.json.gz'
        if path.exists():
            result = json.loads(gzip.decompress(path.read_bytes()))
            assert result['binding'] == binding and result['keys'] == group
        else:
            if time.monotonic() - started >= a.seconds:
                break
            marks = ','.join('?' for _ in group)
            try:
                direct = db.execute('SELECT source_line FROM native_entries WHERE language=\'ar\' AND normalized IN (' + marks + ')', group).fetchall()
                aliases = db.execute('''SELECT f.source_line FROM native_forms f JOIN native_entries e USING(source_line)
                    WHERE f.normalized IN (''' + marks + ''') AND e.language='ar'
                    AND (f.tags LIKE '%canonical%' OR f.tags LIKE '%alternative%')''', group).fetchall()
                identifiers = sorted({r[0] for r in direct + aliases})
                imarks = ','.join('?' for _ in identifiers)
                entries = db.execute('SELECT * FROM native_entries WHERE source_line IN (' + imarks + ') ORDER BY source_line', identifiers).fetchall()
                senses = db.execute('SELECT * FROM native_senses WHERE source_line IN (' + imarks + ') ORDER BY source_line,sense_index', identifiers).fetchall()
                forms = db.execute('SELECT * FROM native_forms WHERE source_line IN (' + imarks + ''')
                    AND (tags LIKE '%canonical%' OR tags LIKE '%alternative%' OR tags LIKE '%romanization%')
                    ORDER BY source_line,form,tags''', identifiers).fetchall()
            except sqlite3.OperationalError as error:
                print('bounded_stop', str(error), flush=True)
                break
            result = {'binding': binding, 'keys': group, 'entries': entries, 'senses': senses, 'forms': forms}
            emit(path, result)
        receipts.append({'file': path.name, 'sha256': sha(path), 'bytes': path.stat().st_size})
        print('keys_retained', min(start + 32, len(keys)), '/', len(keys), 'elapsed', round(time.monotonic() - started, 2), flush=True)
    receipt = {'binding': binding, 'complete': len(receipts) == (len(keys) + 31) // 32,
               'whole_archive_fresh_hash_verified': False, 'batches': receipts,
               'elapsed_seconds': time.monotonic() - started}
    (a.output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    main()
