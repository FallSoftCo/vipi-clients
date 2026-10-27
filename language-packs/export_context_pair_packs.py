#!/usr/bin/env python3
"""Export exact bidirectional runtime subsets; keep authoring evidence at source."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import shutil
import sqlite3


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def export(args):
    receipt_path = args.source.parent / 'receipt.json'
    receipt = json.loads(receipt_path.read_text())
    source_sha = sha(args.source)
    assert receipt['complete'] and source_sha == receipt['sha256']
    assert not Path(str(args.source) + '-wal').exists()
    uri = args.source.resolve().as_uri() + '?mode=ro&immutable=1'
    source = sqlite3.connect(uri, uri=True)
    metadata = {k: json.loads(v) for k, v in source.execute('SELECT key,value FROM metadata')}
    assert metadata['schema'] == 'vipi-context-witnesses-1'
    assert not metadata['release_ready'] and not metadata['independent_semantic_acceptance']
    counts = {a + '-' + b: n for a, b, n in source.execute('SELECT source,target,count(*) FROM witnesses GROUP BY source,target')}
    assert counts == metadata['pairs'] and sum(counts.values()) == metadata['counts']['witnesses']
    catalog = json.loads(args.catalog.read_text())
    assert catalog['release_id'] == metadata['source_release_id']
    shards = {r['language']: r for r in catalog['shards']}
    languages = sorted(shards)
    assert set(counts) <= {a + '-' + b for a, b in itertools.permutations(languages, 2)}
    schemas = dict(source.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name IN ('metadata','witnesses')"))
    assert len(schemas) == 2
    args.output.mkdir(parents=True, exist_ok=False)
    shutil.copy2(args.source.parent / 'ATTRIBUTION.txt', args.output / 'ATTRIBUTION.txt')
    shutil.copy2(receipt_path, args.output / 'source-authoring-receipt.json')
    source.close()
    results = []
    compiler_sha = sha(Path(__file__))
    for a, b in itertools.combinations(languages, 2):
        pair = a + '-' + b
        path = args.output / (pair + '.sqlite')
        db = sqlite3.connect(path)
        db.execute('PRAGMA temp_store=FILE')
        db.execute('PRAGMA cache_size=-8192')
        for statement in schemas.values():
            db.execute(statement)
        db.execute('ATTACH DATABASE ? AS authoring', (uri,))
        condition = '(source=? AND target=?) OR (source=? AND target=?)'
        parameters = (a, b, b, a)
        db.execute('INSERT INTO witnesses SELECT * FROM authoring.witnesses WHERE ' + condition, parameters)
        pair_counts = {k: counts[k] for k in (a + '-' + b, b + '-' + a) if k in counts}
        selected = dict(metadata)
        selected.update(pairs=pair_counts, counts=dict(witnesses=sum(pair_counts.values())),
            pair_input_revisions={k: metadata['pair_input_revisions'][k] for k in pair_counts},
            runtime_subset_policy='exact-bidirectional-witness-subset-1',
            authoring_witness_sha256=source_sha, authoring_receipt_sha256=sha(receipt_path),
            audit_evidence_external=True, pack_compiler_sha256=compiler_sha)
        db.executemany('INSERT INTO metadata VALUES (?,?)', [(k, canonical(v)) for k, v in sorted(selected.items())])
        db.commit()
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert db.execute('SELECT count(*) FROM witnesses').fetchone()[0] == sum(pair_counts.values())
        # Verify every value in both directions, not just row counts or digests.
        assert db.execute('SELECT * FROM witnesses EXCEPT SELECT * FROM authoring.witnesses WHERE ' + condition + ' LIMIT 1', parameters).fetchone() is None
        assert db.execute('SELECT * FROM authoring.witnesses WHERE ' + condition + ' EXCEPT SELECT * FROM witnesses LIMIT 1', parameters).fetchone() is None
        assert not db.execute('SELECT 1 FROM witnesses WHERE support<? OR total<support OR CAST(support AS REAL)/total<? LIMIT 1',
                              (metadata['minimum_support'], metadata['minimum_agreement'])).fetchone()
        db.close()
        results.append(dict(pair=pair, file=path.name, directions=pair_counts, rules=sum(pair_counts.values()),
                            bytes=path.stat().st_size, sha256=sha(path),
                            dictionary_bytes=sum(shards[lang]['bytes'] for lang in (a, b)),
                            dictionary_files=[dict(language=lang, bytes=shards[lang]['bytes'], sha256=shards[lang]['sha256']) for lang in (a, b)],
                            installed_sqlite_bytes=path.stat().st_size + sum(shards[lang]['bytes'] for lang in (a, b))))
    assert sum(r['rules'] for r in results) == sum(counts.values())
    output = dict(schema='vipi-context-pair-packs-1', complete=True, exact_row_equality_verified=True,
                  source_authoring_sha256=source_sha, dictionary_release=catalog['release_id'],
                  compiler_sha256=compiler_sha, language_count=len(languages), directed_pairs=len(counts),
                  rules=sum(counts.values()), pair_packs=results, runtime_context_bytes=sum(r['bytes'] for r in results),
                  all_dictionary_bytes=sum(r['bytes'] for r in shards.values()),
                  native_qualified=False, signed=False, release_ready=False, independent_semantic_acceptance=False,
                  limitation='Installed SQLite sizes only. App, baseline catalog, translation and voice models are additional. Evidence/provenance remains in the immutable authoring source. This catalog does not activate production downloads.')
    output['release_id'] = hashlib.sha256(canonical(output).encode()).hexdigest()
    (args.output / 'catalog.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(canonical({k: v for k, v in output.items() if k not in {'pair_packs', 'limitation'}}))
    for row in results:
        if 'en' in row['pair'].split('-'):
            print(canonical({k: row[k] for k in ['pair', 'rules', 'bytes', 'dictionary_bytes', 'installed_sqlite_bytes']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'catalog', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    export(parser.parse_args())
