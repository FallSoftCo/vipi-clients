#!/usr/bin/env python3
"""Validate exact native evidence and count availability, never meaning accuracy."""
import argparse
from collections import Counter
import json
from pathlib import Path
import statistics
from conversation_corpus import sha_file, write_json
from review_pipeline import utf16_slice


def summarize_modes(report, corpus):
    originals = {turn['id']: turn['text']['sw'] for turn in corpus['cases']}
    expected = {(turn, target, mode) for turn in originals for target in corpus['targets']
                for mode in ('incremental', 'fullMessages')}
    seen = set()
    counts = Counter()
    for row in report['rows']:
        identity = row['id'], row['target'], row['mode']
        if identity not in expected or identity in seen:
            raise ValueError('Duplicate or unexpected turn, direction or mode')
        seen.add(identity)
        turn, target, mode = identity
        value = row['value']
        original = originals[turn]
        if (value['original'] != original or value['meaningText'] != original or
                value['inputLanguage'] != 'sw' or value['practiceLanguage'] != target or
                not value['practiceText'] or row['provider'] not in ('apple', 'mlKit')):
            raise ValueError('Changed turn or missing local provider result')
        words = value.get('words')
        if mode == 'incremental':
            if not isinstance(words, list):
                raise ValueError('Missing incremental word plan')
            end = 0
            pieces = []
            for word in words:
                start = word['start']
                stop = start + word['length']
                if start < end or stop <= start or utf16_slice(original, start, stop) != word['source']:
                    raise ValueError('Changed or overlapping source word')
                pieces.extend((utf16_slice(original, end, start), word['target']))
                end = stop
            pieces.append(utf16_slice(original, end, len(original.encode('utf-16-le')) // 2))
            if ''.join(pieces) != value['practiceText']:
                raise ValueError('Practice text differs from the recorded word replacements')
            if words and not row['identifierIntegrity']:
                raise ValueError('Incremental word replacements changed a protected identifier')
            counts['with_word_replacements'] += bool(words)
        elif words is not None:
            raise ValueError('Unexpected word plan in full-message mode')
        counts[mode] += 1
        counts['identifier_mismatches'] += not row['identifierIntegrity']
    if seen != expected or not expected:
        raise ValueError('Incomplete native report')
    return {'source_turns': len(originals), 'directions': len(corpus['targets']), 'totals': dict(counts)}


def summarize(report, corpus):
    if report['schema'] == 'vipi-swahili-conversation-modes-1':
        return summarize_modes(report, corpus)
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
    p.add_argument('--catalog', type=Path, help='Bundled catalog used by the historical catalog report')
    for name in ('report', 'corpus', 'output'): p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    report = json.loads(a.report.read_text()); corpus = json.loads(a.corpus.read_text())
    current = report['schema'] == 'vipi-swahili-conversation-modes-1'
    if report['corpusSHA256' if current else 'corpus_sha256'] != sha_file(a.corpus): raise ValueError('Wrong frozen corpus')
    if not current and (not a.catalog or report['catalog_sha256'] != sha_file(a.catalog)): raise ValueError('Wrong app catalog')
    if a.output.exists(): raise ValueError('Preserve existing receipt')
    result = {'schema': 'vipi-swahili-modes-summary-1' if current else 'vipi-swahili-coverage-summary-1', 'platform': report['platform'],
        'report_sha256': sha_file(a.report), 'corpus_sha256': sha_file(a.corpus),
        'evaluator_sha256': sha_file(Path(__file__)), 'semantic_accuracy': None, 'independent_linguistic_acceptance': False,
        'limits': ['One translated task-oriented source domain, not general friend conversation coverage.',
                   'Full translation returning text does not prove its meaning is correct.',
                   'Availability counts substitutions, not independently reviewed correct substitutions.',
                   'Ten directions reuse the same 241 Swahili turns; these are not 2,410 independent conversations.'],
        **summarize(report, corpus)}
    if not current: result['catalog_sha256'] = sha_file(a.catalog)
    write_json(a.output, result); print(json.dumps(result))
