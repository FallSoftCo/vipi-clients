#!/usr/bin/env python3
"""Freeze an unseen reference-translation evaluation; never feed it to authoring.

Each direction samples separate translation-graph components. The denominator
includes short and grammatical messages, regardless of available vocabulary.
These are attributed sentence references, not a representative chat population.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import heapq
import json
from pathlib import Path
import sqlite3
import sys
from conversation_corpus import key, lines, sha_file, tag_row
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'language-packs'))
from build_wiktextract import canonical

RECIPE = 'vipi-reserved-reference-components-1'


def readonly(path):
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    db.execute('PRAGMA temp_store=FILE')
    db.execute('PRAGMA cache_size=-32768')
    return db


def build(a):
    a.output.mkdir(parents=True, exist_ok=False)
    parent = json.loads((a.corpus.parent / 'receipt.json').read_text())
    assert sha_file(a.corpus) == parent['sha256']
    catalog = json.loads((a.shards / 'catalog.json').read_text())
    contexts_receipt = json.loads((a.contexts.parent / 'receipt.json').read_text())
    assert contexts_receipt['complete'] and contexts_receipt['corpus_partition'] == 'development'
    assert contexts_receipt['corpus_sha256'] == parent['sha256']
    assert contexts_receipt['source_release_id'] == catalog['release_id']
    assert sha_file(a.contexts) == contexts_receipt['sha256']
    corpus, training = readonly(a.corpus), readonly(a.contexts)
    flagged = {r[0] for r in corpus.execute('''SELECT t.sentence FROM tags t NOT INDEXED
        JOIN tag_metadata m ON m.id=t.tag WHERE m.name LIKE '@%'
        OR lower(m.name) LIKE '%unnatural%' OR lower(m.name) LIKE '%incorrect%'
        OR lower(m.name) IN ('not natural','non natural','less than natural')''')}
    candidates = defaultdict(dict)

    def offer(source, target, left, right, component):
        if source == target or left in flagged or right in flagged:
            return
        pair = source + '-' + target
        rank = hashlib.sha256(canonical([RECIPE, pair, component]).encode()).hexdigest()
        link_rank = hashlib.sha256(canonical([RECIPE, pair, left, right]).encode()).hexdigest()
        item = rank, link_rank, left, right, component
        previous = candidates[pair].get(component)
        if previous is None or item < previous:
            candidates[pair][component] = item

    for left, source, right, target, component, other_component in corpus.execute('''
        SELECT l.a,a.language,l.b,b.language,a.component,b.component FROM links l
        JOIN sentences a ON a.id=l.a JOIN sentences b ON b.id=l.b
        WHERE a.partition='reserved' AND b.partition='reserved' AND a.language<>b.language'''):
        assert component == other_component
        offer(source, target, left, right, component)
        offer(target, source, right, left, component)
    print(canonical(dict(stage='base_component_candidates',pairs=len(candidates))), flush=True)

    # Recover Swahili reserved references from the same frozen graph. A whole
    # duplicate group is excluded if any selected-language neighbor is in
    # development, or if any member has no direct selected-language neighbor.
    sw_receipt = json.loads((a.swahili / 'receipt.json').read_text())
    sw_source = a.swahili / 'swh_sentences_detailed.tsv.bz2'
    assert sha_file(sw_source) == sw_receipt['sha256']
    exports_receipt = json.loads((a.exports / 'receipt.json').read_text())
    assert sha_file(a.exports / 'receipt.json') == parent['source_receipt_sha256']
    for name in ['links.tar.bz2', 'tags_detailed.tar.bz2']:
        asset = next(r for r in exports_receipt['assets'] if r['file'] == name)
        assert sha_file(a.exports / name) == asset['sha256']
        if name == 'links.tar.bz2':
            assert asset['last_modified'][:16] == sw_receipt['last_modified'][:16]
    sw, duplicates = {}, defaultdict(set)
    for line in lines(sw_source):
        fields = line.split('\t')
        assert len(fields) == 6 and fields[1] == 'swh'
        identifier = int(fields[0])
        sw[identifier] = fields
        duplicates[key(fields[2])].add(identifier)
    links = set()
    for line in lines(a.exports / 'links.tar.bz2', 'links.csv'):
        left, right = map(int, line.split('\t'))
        if left in sw and right not in sw:
            links.add((left, right))
        elif right in sw and left not in sw:
            links.add((right, left))
    foreign = sorted({right for _, right in links})
    endpoints = {}
    for start in range(0, len(foreign), 500):
        batch = foreign[start:start + 500]
        for row in corpus.execute('SELECT id,language,component,partition FROM sentences WHERE id IN (' + ','.join('?' * len(batch)) + ')', batch):
            endpoints[row[0]] = row
    related = defaultdict(set)
    for left, right in links:
        if right in endpoints:
            related[left].add(right)
    retained = {}
    for ids in duplicates.values():
        neighbors = set().union(*(related[i] for i in ids))
        if not neighbors or any(not related[i] for i in ids) or any(endpoints[n][3] != 'reserved' for n in neighbors):
            continue
        component = min(endpoints[n][2] for n in neighbors)
        retained.update((i, component) for i in ids)
    bad_tags = {r[0] for r in corpus.execute('''SELECT id FROM tag_metadata WHERE name LIKE '@%'
        OR lower(name) LIKE '%unnatural%' OR lower(name) LIKE '%incorrect%'
        OR lower(name) IN ('not natural','non natural','less than natural')''')}
    for line in lines(a.exports / 'tags_detailed.tar.bz2', 'tags_detailed.csv'):
        sentence, tag, _, _ = tag_row(line)
        if sentence in sw and tag in bad_tags:
            flagged.add(sentence)
    for left, right in sorted(links):
        if left not in retained or right not in endpoints:
            continue
        _, language, _, partition = endpoints[right]
        assert partition == 'reserved'
        offer('sw', language, left, right, retained[left])
        offer(language, 'sw', right, left, retained[left])

    cases, counts = [], Counter()
    for pair, by_component in sorted(candidates.items()):
        source, target = pair.split('-')
        for _, rank, left, right, component in heapq.nsmallest(a.per_pair, by_component.values()):
            values = []
            for identifier, language in [(left, source), (right, target)]:
                assert training.execute('SELECT 1 FROM sentences WHERE id=?', (identifier,)).fetchone() is None
                if language == 'sw':
                    assert identifier in retained
                    text, owner = sw[identifier][2:4]
                else:
                    text, owner, partition = corpus.execute('SELECT text,owner,partition FROM sentences WHERE id=?', (identifier,)).fetchone()
                    assert partition == 'reserved'
                values.append((text, owner))
            cases.append(dict(id='reserved-' + rank[:24], dataset='reserved-tatoeba-references',
                source=source, target=target, original=values[0][0], translation=values[1][0],
                source_id=left, target_id=right, source_owner=values[0][1], target_owner=values[1][1], component=component))
            counts[pair] += 1
    path = a.output / 'cases.json'
    path.write_text(canonical(cases) + '\n')
    for shard in catalog['shards']:
        source = a.shards / (shard['language'] + '.sqlite')
        assert sha_file(source) == shard['sha256']
        (a.output / source.name).hardlink_to(source)
    manifest = dict(schema='vipi-lexical-qualification-1', shards=catalog['shards'],
        cases=len(cases), cases_sha256=sha_file(path), datasets={'reserved-tatoeba-references':len(cases)},
        source_catalog_sha256=sha_file(a.shards / 'catalog.json'), compiler_sha256=sha_file(Path(__file__)),
        corpus_sha256=parent['sha256'], context_sha256=contexts_receipt['sha256'],
        swahili_source_sha256=sw_receipt['sha256'], recipe=RECIPE, pairs=dict(counts),
        up_to_per_pair=a.per_pair, direct_references_only=True, all_endpoints_absent_from_context_build=True,
        translation_reused=True, translation_kind='publisher reference, not a fresh native translation',
        selection_independent_of_native_output=True, classification_exercised=False,
        independent_semantic_acceptance=False, license='CC BY 2.0 FR',
        limitation='Connected-component sample of sentence references; not representative chat coverage or semantic precision.')
    snapshot = json.loads((a.native_snapshot / 'receipt.json').read_text())
    for source in snapshot['files']:
        assert sha_file(a.native_snapshot / source['path']) == source['sha256']
    manifest['native_source_snapshot_sha256'] = sha_file(a.native_snapshot / 'receipt.json')
    (a.output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    (a.output / 'ATTRIBUTION.txt').write_text('Tatoeba contributors, CC BY 2.0 FR. Individual owners and IDs in cases.json.\nSentence URLs: https://tatoeba.org/en/sentences/show/{id}.\nChanges: deterministic evaluation sampling; no translation pivots.\n')
    corpus.close()
    training.close()
    print(canonical(dict(cases=len(cases),pairs=dict(counts),manifest_sha256=sha_file(a.output / 'manifest.json'))), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['corpus', 'contexts', 'shards', 'swahili', 'exports', 'native-snapshot', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--per-pair', type=int, default=100)
    args = parser.parse_args()
    assert 1 <= args.per_pair <= 500
    build(args)
