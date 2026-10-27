#!/usr/bin/env python3
"""Add frozen human-reference diagnostics without using them as mining input."""
import argparse
from collections import Counter
import hashlib
import itertools
import json
from pathlib import Path
import sqlite3

from build_corpus_exclusions import fingerprint
from fetch_flores_evaluation import LANGUAGES


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def readonly(path):
    return sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)


def main(args):
    assert 1 <= args.sentences <= 997
    args.output.mkdir(parents=True, exist_ok=False)
    acquired = json.loads((args.source / 'receipt.json').read_text())
    assert acquired['complete'] and acquired['evaluation_only']
    inputs = {}
    for row in acquired['selected_members']:
        path = args.source / row['file']
        assert sha(path) == row['sha256']
        if 'language' in row:
            values = path.read_text().splitlines()
            assert len(values) == row['lines']
            inputs[(row['language'], row['partition'])] = values
    for row in acquired['files']:
        assert sha(args.source / row['file']) == row['sha256']
    exclusions_receipt = json.loads((args.exclusions.parent / 'receipt.json').read_text())
    pgv_receipt = json.loads((args.pgv.parent / 'receipt.json').read_text())
    assert exclusions_receipt['complete'] and pgv_receipt['complete']
    assert sha(args.exclusions) == exclusions_receipt['sha256']
    assert sha(args.pgv) == pgv_receipt['sha256']

    # Group all language versions by underlying sentence ID. Repeated text
    # connects IDs too; exclude an entire component if any endpoint overlaps
    # previous authoring/evaluation data or the retained devtest partition.
    parents, owners = {}, {}
    def root(value):
        parents.setdefault(value, value)
        while parents[value] != value:
            parents[value] = parents[parents[value]]
            value = parents[value]
        return value
    def join(a, b):
        a, b = root(a), root(b)
        if a != b:
            parents[max(a, b)] = min(a, b)
    hashes = {}
    for (language, partition), lines in inputs.items():
        for index, text in enumerate(lines):
            group = (partition, index + 1)
            root(group)
            digest = fingerprint(language, text)
            hashes[(language, partition, index + 1)] = digest
            if digest in owners:
                join(group, owners[digest])
            else:
                owners[digest] = group
    old = readonly(args.exclusions)
    pgv = readonly(args.pgv)
    blocked, counts = set(), Counter()
    for digest, group in owners.items():
        if old.execute('SELECT 1 FROM hashes WHERE digest=?', (digest,)).fetchone():
            blocked.add(root(group)); counts['previous_corpus_overlaps'] += 1
        if pgv.execute('SELECT 1 FROM sentences WHERE normalized_sha256=?', (digest,)).fetchone():
            blocked.add(root(group)); counts['pgv_overlaps'] += 1
    old.close(); pgv.close()
    reserved = {root(group) for group in parents if group[0] == 'devtest'}
    eligible, used = [], set()
    for index in range(1, 998):
        group = root(('dev', index))
        if group in blocked or group in reserved or group in used:
            continue
        used.add(group)
        eligible.append(index)
    ranked = sorted(eligible, key=lambda i: hashlib.sha256(('vipi-flores-diagnostic-001\0' + str(i)).encode()).digest())
    assert len(ranked) >= args.sentences
    chosen = ranked[:args.sentences]

    # Retain hashes for every acquired benchmark sentence, including untouched
    # devtest. Future corpus ingestion must include this exclusion artifact.
    exclusion_path = args.output / 'evaluation-exclusions.sqlite'
    with sqlite3.connect(exclusion_path) as db:
        db.execute('CREATE TABLE hashes(digest BLOB PRIMARY KEY CHECK(length(digest)=32)) WITHOUT ROWID')
        db.executemany('INSERT INTO hashes VALUES (?)', [(d,) for d in sorted(owners)])
        db.commit()
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    manifest = json.loads((args.base / 'manifest.json').read_text())
    assert sha(args.base / 'cases.json') == manifest['cases_sha256']
    cases = json.loads((args.base / 'cases.json').read_text())
    prior_count = len(cases)
    for index in chosen:
        for source, target in itertools.permutations(LANGUAGES, 2):
            cases.append(dict(id=f'flores200-dev-{index:04d}', dataset='flores200-human-reference-diagnostic',
                              source=source, target=target, original=inputs[(source, 'dev')][index - 1],
                              translation=inputs[(target, 'dev')][index - 1]))
    assert len({(r['dataset'], r['id'], r['source'], r['target']) for r in cases}) == len(cases)
    receipt = dict(schema='vipi-flores-diagnostic-1', complete=True, evaluation_only=True,
                   source_receipt_sha256=sha(args.source / 'receipt.json'),
                   prior_exclusions_sha256=exclusions_receipt['sha256'], pgv_corpus_sha256=pgv_receipt['sha256'],
                   source_overlap_counts=dict(counts), eligible_dev_components=len(eligible),
                   selected_sentence_ids=chosen, underlying_sentences=len(chosen), directions=110,
                   added_cases=len(cases) - prior_count, native_qualified=False,
                   policy='Hash-ranked dev components only; exclude all prior-corpus overlaps and components touching devtest. Preserve all eleven versions together.',
                   limitation='English-centered professional parallel references, not native-authored chats or word-alignment gold. No semantic or document-independent acceptance claimed.',
                   future_training_exclusions=dict(file=exclusion_path.name, sha256=sha(exclusion_path),
                                                   hashes=len(owners), all_partitions=True),
                   compiler_sha256=sha(Path(__file__)))
    (args.output / 'diagnostic-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    for shard in manifest['shards']:
        path = args.base / (shard['language'] + '.sqlite')
        assert sha(path) == shard['sha256']
        (args.output / path.name).symlink_to(path.resolve())
    path = args.output / 'cases.json'
    path.write_text(json.dumps(cases, ensure_ascii=False, separators=(',', ':')) + '\n')
    manifest.update(cases=len(cases), datasets=dict(Counter(r['dataset'] for r in cases)), cases_sha256=sha(path),
                    compiler_sha256=sha(Path(__file__)), prior_manifest_sha256=sha(args.base / 'manifest.json'),
                    evaluation_receipt_sha256=sha(args.output / 'diagnostic-receipt.json'))
    (args.output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    (args.output / 'EVALUATION-NOTICE.txt').write_text(
        'FLORES-200, NLLB Team / Meta, 2022; CC-BY-SA-4.0.\n'
        'https://github.com/facebookresearch/flores/tree/main/flores200\n'
        'Changes: hash-ranked duplicate-excluded subset and directed reference pair enumeration.\n'
        'Evaluation only. Do not mine vocabulary or context witnesses from this benchmark.\n'
        'Retained source license: ' + str(args.source / 'dataset-LICENSE_CC-BY-SA') + '\n')
    print(json.dumps(dict(cases=len(cases), added_cases=receipt['added_cases'], underlying_sentences=len(chosen),
                         eligible_dev_components=len(eligible), overlaps=dict(counts), manifest_sha256=sha(args.output / 'manifest.json'))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'source', 'exclusions', 'pgv', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--sentences', type=int, default=100)
    main(parser.parse_args())
