#!/usr/bin/env python3
"""Validate exact native evidence and count availability, never meaning accuracy."""
import argparse
from collections import Counter
import json
from pathlib import Path
import statistics
from conversation_corpus import sha_file, write_json
from review_pipeline import utf16_slice


def summarize(report, corpus):
    if report['schema'] != 'vipi-swahili-live-catalog-coverage-1': raise ValueError('Unknown report')
    expected = {(row['id'], target): row['text']['sw'] for row in corpus['cases'] for target in corpus['targets']}
    counts = {target: Counter() for target in corpus['targets']}; seen = set(); latency = []
    for row in report['rows']:
        identity = row['id'], row['target']
        if identity in seen or identity not in expected: raise ValueError('Duplicate or unexpected case')
        if row['source'] != 'sw' or row['original'] != expected[identity]: raise ValueError('Changed original')
        seen.add(identity); count = counts[row['target']]
        count['messages'] += 1; count['with_immersion'] += bool(row['spans'])
        count['spans'] += len(row['spans']); count['exact_references'] += row['exact_reference']
        count['identifier_abstentions'] += not row['identifier_integrity']
        if row['spans'] and not row['identifier_integrity']: raise ValueError('Unprotected output displayed')
        end = 0
        for span in row['spans']:
            if span['start'] < end: raise ValueError('Overlapping source spans')
            if utf16_slice(row['original'], span['start'], span['end']) != span['original']: raise ValueError('Changed source scope')
            if utf16_slice(row['translation'], span['targetStart'], span['targetEnd']) != span['translated']: raise ValueError('Changed target scope')
            if row['target'] in ('ar', 'zh', 'ja', 'ko') and not span['reading']: raise ValueError('Missing required reading')
            end = span['end']
        latency.append(row['elapsed_ms'])
    if seen != set(expected): raise ValueError('Incomplete native report')
    totals = Counter()
    for count in counts.values(): totals.update(count)
    return {'source_turns': len(corpus['cases']), 'directions': len(counts),
        'pairs': {target: dict(count, message_availability=count['with_immersion']/count['messages']) for target, count in counts.items()},
        'totals': dict(totals), 'message_availability': totals['with_immersion']/totals['messages'],
        'translation_and_alignment_ms': {'median': statistics.median(latency), 'p95': sorted(latency)[int(len(latency)*.95)]}}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('report', 'corpus', 'catalog', 'output'): p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    report = json.loads(a.report.read_text()); corpus = json.loads(a.corpus.read_text())
    if report['corpus_sha256'] != sha_file(a.corpus): raise ValueError('Wrong frozen corpus')
    if report['catalog_sha256'] != sha_file(a.catalog): raise ValueError('Wrong app catalog')
    if a.output.exists(): raise ValueError('Preserve existing receipt')
    result = {'schema': 'vipi-swahili-coverage-summary-1', 'platform': report['platform'],
        'report_sha256': sha_file(a.report), 'corpus_sha256': sha_file(a.corpus), 'catalog_sha256': sha_file(a.catalog),
        'evaluator_sha256': sha_file(Path(__file__)), 'semantic_accuracy': None, 'independent_linguistic_acceptance': False,
        'limits': ['One translated task-oriented source domain, not general friend conversation coverage.',
                   'Full translation returning text does not prove its meaning is correct.',
                   'Availability counts substitutions, not independently reviewed correct substitutions.',
                   'Ten directions reuse the same 241 Swahili turns; these are not 2,410 independent conversations.'],
        **summarize(report, corpus)}
    write_json(a.output, result); print(json.dumps(result))
