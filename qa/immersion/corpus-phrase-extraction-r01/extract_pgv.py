#!/usr/bin/env python3
"""Bounded, restartable indexed PGV subset; metadata selection precedes text."""
import argparse
import collections
import gzip
import hashlib
import heapq
import json
import resource
import shutil
import sqlite3
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from build_corpus_exclusions import fingerprint
from prepare_statistical_alignment_pilot import tokenize

OUT = Path('/home/ai/Development/investigations/vipi-immersion-reconciliation-20261107-r01/corpus-phrase-extraction-r01')


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def write(name, value):
    p = OUT / name
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(p)


def guards(start, seconds):
    if time.monotonic() - start > seconds:
        raise TimeoutError('bounded source extraction deadline')
    if shutil.disk_usage(OUT).free < 8 * 1024 ** 3:
        raise RuntimeError('8GiB free reserve')
    if process_hwm() > 2 * 1024 ** 3:
        raise RuntimeError('2GiB RSS cap')


def process_hwm():
    # This exec transport inherits a larger pre-exec ru_maxrss. Linux VmHWM
    # describes this Python process image and does not misattribute the launcher.
    return int(next(line.split()[1] for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('VmHWM:'))) * 1024


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['metadata', 'fetch', 'export'])
    parser.add_argument('--seconds', type=int, default=1800)
    args = parser.parse_args()
    start = time.monotonic()
    protocol = json.loads((HERE / 'protocol.json').read_text())
    frozen = json.loads((OUT / 'input-freeze.json').read_text())
    assert sha(HERE / 'protocol.json') == frozen['protocol_sha256']
    assert sha(OUT / 'evaluation-exclusion-hashes.json') == frozen['exclusions_sha256']
    assert sha(OUT / 'source-frequency-keys.json') == frozen['source_frequency_sha256']
    guards(start, args.seconds)
    db = sqlite3.connect(OUT / 'subset.sqlite')
    db.executescript('''PRAGMA temp_store=FILE; PRAGMA cache_size=-32768;
      CREATE TABLE IF NOT EXISTS evidence(pair TEXT,rank TEXT,a INTEGER,b INTEGER,
      archive TEXT,unit TEXT,score REAL,PRIMARY KEY(pair,rank)) WITHOUT ROWID;
      CREATE TABLE IF NOT EXISTS sentences(id INTEGER PRIMARY KEY,language TEXT,text TEXT,
      owner TEXT,fingerprint TEXT,component INTEGER,partition TEXT,record_sha256 TEXT);
      CREATE TABLE IF NOT EXISTS status(key TEXT PRIMARY KEY,value TEXT) WITHOUT ROWID;''')
    source = None
    if args.stage != 'export':
        p = Path(protocol['sources']['pgv']['path'])
        assert p.stat().st_size == protocol['sources']['pgv']['bytes']
        source = sqlite3.connect(p.as_uri() + '?mode=ro&immutable=1', uri=True)
        source.execute('PRAGMA cache_size=-65536')
        source.execute('PRAGMA temp_store=FILE')
        source.set_progress_handler(lambda: int(time.monotonic() - start > args.seconds), 10000)
    receipt = dict(stage=args.stage, complete=False, production=False,
                   protocol_sha256=frozen['protocol_sha256'], builder_sha256=sha(Path(__file__)))
    try:
        if args.stage == 'metadata':
            assert not db.execute("SELECT 1 FROM status WHERE key='metadata_complete'").fetchone()
            # Run both scans before recording completion or reading any sentence text.
            results = []
            for archive in protocol['sources']['pgv']['archives']:
                pair = {'eng-spa': 'en-es', 'eng-swa': 'en-sw'}[archive['pair']]
                cap = protocol['training_selection']['metadata_candidates'][pair]
                heap, scanned = [], 0
                for a, b, unit, score in source.execute(
                        'SELECT a,b,unit,score FROM link_evidence WHERE archive=?', (archive['url'],)):
                    digest = hashlib.sha256((protocol['training_selection']['seed'] + '|' + archive['url'] + '|' + str(unit)).encode()).hexdigest()
                    item = (-int(digest, 16), digest, a, b, str(unit), score)
                    if len(heap) < cap:
                        heapq.heappush(heap, item)
                    elif item[0] > heap[0][0]:
                        heapq.heapreplace(heap, item)
                    scanned += 1
                    if scanned % 10000 == 0:
                        guards(start, args.seconds)
                ordered = sorted(heap, key=lambda r: r[1])
                db.executemany('INSERT INTO evidence VALUES(?,?,?,?,?,?,?)',
                               [(pair, rank, a, b, archive['url'], unit, score)
                                for _, rank, a, b, unit, score in ordered])
                db.commit()
                results.append(dict(pair=pair, archive=archive, rows_scanned=scanned, selected=len(ordered)))
                print(encoded(results[-1]), flush=True)
            db.execute("INSERT INTO status VALUES('metadata_complete','true')")
            db.commit()
            receipt['pairs'] = results
            receipt['selected_identity_sha256'] = hashlib.sha256(encoded(list(db.execute('SELECT * FROM evidence ORDER BY pair,rank'))).encode()).hexdigest()
            write('metadata-freeze.json', receipt | dict(complete=True, before_pair_text=True))
        elif args.stage == 'fetch':
            assert db.execute("SELECT 1 FROM status WHERE key='metadata_complete'").fetchone()
            # Source PK order minimizes remote page churn; final acceptance still uses frozen hash order.
            ids = sorted(set(r[0] for r in db.execute('SELECT a FROM evidence UNION SELECT b FROM evidence')))
            existing = set(r[0] for r in db.execute('SELECT id FROM sentences'))
            todo = [i for i in ids if i not in existing]
            receipt.update(required_unique_endpoints=len(ids), already_retained=len(existing))
            for offset in range(0, len(todo), 128):
                guards(start, args.seconds)
                batch = todo[offset:offset+128]
                fetched = list(source.execute('SELECT id,language,text,owner,normalized_sha256,component,partition FROM sentences WHERE id IN (' + ','.join('?' for _ in batch) + ') ORDER BY id', batch))
                assert len(fetched) == len(batch)
                rows = []
                for row in fetched:
                    values = list(row)
                    values[4] = values[4].hex()
                    assert fingerprint(values[1], values[2]).hex() == values[4]
                    rows.append(values + [hashlib.sha256(encoded(values).encode()).hexdigest()])
                db.executemany('INSERT INTO sentences VALUES(?,?,?,?,?,?,?,?)', rows)
                db.commit()
                if offset % 1280 == 0:
                    receipt.update(fetched_this_invocation=offset+len(batch), elapsed_seconds=time.monotonic()-start)
                    write('fetch-progress.json', receipt)
                    print(encoded({k: receipt[k] for k in ['fetched_this_invocation', 'elapsed_seconds']}), flush=True)
            db.execute("INSERT OR REPLACE INTO status VALUES('fetch_complete','true')")
            db.commit()
        else:
            assert db.execute("SELECT 1 FROM status WHERE key='fetch_complete'").fetchone()
            assert not (OUT / 'training-receipt.json').exists()
            excluded = set(json.loads((OUT / 'evaluation-exclusion-hashes.json').read_text())['hashes'])
            archive_map = {r['url']: r for r in protocol['sources']['pgv']['archives']}
            pair_results = []
            for pair, cap in protocol['training_selection']['accepted_pair_caps'].items():
                counts, seen, rows_out = collections.Counter(), {}, 0
                manifest = OUT / (pair + '-pairs.jsonl.gz')
                lines = OUT / (pair + '.txt')
                decisions = OUT / (pair + '-selection.jsonl.gz')
                with gzip.open(manifest, 'xt', encoding='utf-8') as out, lines.open('x') as text, gzip.open(decisions, 'xt', encoding='utf-8') as dec:
                    for _, rank, a, b, archive, unit, score in db.execute('SELECT * FROM evidence WHERE pair=? ORDER BY rank', (pair,)):
                        left, right = [db.execute('SELECT * FROM sentences WHERE id=?', (i,)).fetchone() for i in [a, b]]
                        if right[1] == 'en':
                            left, right = right, left
                        reason = None
                        if (left[1], right[1]) != tuple(pair.split('-')):
                            reason = 'wrong_language_pair'
                        elif left[6] != 'development' or right[6] != 'development':
                            reason = 'non_development_partition'
                        elif left[4] in excluded or right[4] in excluded:
                            reason = 'evaluated_complete_message'
                        lt, rt = tokenize(left[2]), tokenize(right[2])
                        if reason is None and (not 2 <= len(lt) <= 60 or not 2 <= len(rt) <= 60 or '|||' in left[2] or '|||' in right[2]):
                            reason = 'token_length_or_delimiter'
                        pair_id = hashlib.sha256((left[4] + right[4]).encode()).hexdigest()
                        if reason is None and pair_id in seen:
                            reason = 'duplicate_direct_pair'
                        if reason is None and rows_out >= cap:
                            reason = 'accepted_cap'
                        decision = dict(rank=rank, archive=archive, unit=unit, source_id=left[0], target_id=right[0], pair_id=pair_id, reason=reason or 'accepted')
                        dec.write(encoded(decision)+'\n')
                        counts[decision['reason']] += 1
                        if reason:
                            continue
                        seen[pair_id] = rows_out
                        def endpoint(row, tokens):
                            return dict(id=row[0], language=row[1], text=row[2], owner=row[3], fingerprint=row[4], component=row[5], partition=row[6], record_sha256=row[7], tokens=[dict(text=t, codepoints=[s,e], utf16=[len(row[2][:s].encode('utf-16-le'))//2, len(row[2][:e].encode('utf-16-le'))//2]) for t,s,e in tokens])
                        record = dict(index=rows_out, pair_id=pair_id, pair=pair, source=endpoint(left,lt), target=endpoint(right,rt), provenance=dict(source_namespace='PGV', source_license=protocol['sources']['pgv']['license'], distribution_status='research_only_not_approved_pack', archive_url=archive, archive_sha256=archive_map[archive]['sha256'], unit_id=unit, score=score, hash_selection_rank=rank))
                        out.write(encoded(record)+'\n')
                        text.write(' '.join(t[0].casefold() for t in lt)+' ||| '+' '.join(t[0].casefold() for t in rt)+'\n')
                        rows_out += 1
                        if rows_out % 500 == 0:
                            guards(start, args.seconds)
                pair_results.append(dict(pair=pair, rows=rows_out, counts=dict(counts), artifacts=[dict(path=str(p), bytes=p.stat().st_size, sha256=sha(p)) for p in [manifest, lines, decisions]]))
                print(encoded(pair_results[-1]), flush=True)
            receipt['pairs'] = pair_results
        receipt['complete'] = True
    except BaseException as exc:
        receipt['error'] = repr(exc)
        raise
    finally:
        receipt.update(elapsed_seconds=time.monotonic()-start, process_vm_hwm_bytes=process_hwm(), inherited_pre_exec_ru_maxrss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024, free_bytes=shutil.disk_usage(OUT).free)
        db.close()
        if source:
            source.close()
        write({'metadata':'metadata-receipt.json','fetch':'fetch-receipt.json','export':'training-receipt.json'}[args.stage], receipt)
        print(encoded(receipt), flush=True)


if __name__ == '__main__':
    main()
