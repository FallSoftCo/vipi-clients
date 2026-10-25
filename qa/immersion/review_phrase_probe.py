#!/usr/bin/env python3
"""Summarize observed phrase correspondence separately from meaning acceptance.

An exact reference match is a narrow regression check, not a fluency score.
Reference words are never used to choose or construct a correspondence.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics


def summarize(report):
    if report['schema'] != 'vipi-local-phrase-observations-1' or not report['complete']:
        raise ValueError('Complete native observation report required')
    rows = report['results']
    if len(rows) != report['cases_expected'] or len(rows) != report['cases_completed']:
        raise ValueError('Incomplete observations')
    counts = Counter(); pairs = {}; nonexact = []; regressions = []
    for row in rows:
        pair = row['source']+'-'+row['target']; per_pair = pairs.setdefault(pair, Counter())
        focus = [x for x in row['phrases'] if x['focus_only']]
        if len(focus) != 1: raise ValueError('Exactly one source focus required')
        matches = focus[0]['whole_translation_matches']
        # Selection uses only provider output and native boundaries.
        candidate = matches[0] if len(matches) == 1 else None
        for counter in (counts, per_pair):
            counter['cases'] += 1
            counter['unique_focus_correspondences'] += candidate is not None
        overlapping = []
        if candidate:
            for phrase in row['phrases']:
                if phrase['focus_only']: continue
                if any(x['start'] <= candidate['start'] and x['end'] >= candidate['end']
                       for x in phrase['whole_translation_matches']):
                    overlapping.append(phrase['input'])
            counts['with_overlapping_phrase_agreement'] += bool(overlapping)
        entry = {'pair': pair, 'case': row['case'], 'concept': row['concept'],
                 'original': row['original'], 'source_focus': row['source_word'],
                 'focus_translation': focus[0]['translation'], 'full_translation': row['translation'],
                 'correspondence': candidate, 'supporting_source_phrases': overlapping}
        if 'expected_target' in row:
            for counter in (counts, per_pair):
                counter['reference_cases'] += 1
                counter['reference_cases_with_correspondence'] += candidate is not None
            exact = candidate is not None and candidate['text'].casefold() == row['expected_target'].casefold()
            for counter in (counts, per_pair): counter['exact_reference_surface_matches'] += exact
            if candidate and not exact:
                nonexact.append({**entry, 'reference_surface': row['expected_target'],
                                 'classification': 'requires review: may be valid form, excess grammar, or wrong sense'})
        else: regressions.append(entry)
    latencies = sorted(x['latency_ms'] for x in rows)
    return {'schema': 'vipi-phrase-correspondence-review-1', 'linguistic_acceptance': False,
            'runtime_integration': False, 'scope': 'reused development/regression cases',
            'counts': dict(counts), 'pairs': {k: dict(v) for k,v in pairs.items()},
            'case_latency_median_ms': statistics.median(latencies),
            'case_latency_p95_ms': latencies[min(len(latencies)-1, int(len(latencies)*.95))],
            'latency_scope': 'observed case processing, including warm/cold translation and cache reuse; not chat UI latency',
            'nonexact_reference_surfaces': nonexact, 'additional_regressions': regressions,
            'limits': ['Same-provider agreement does not independently establish meaning.',
                       'Exact surface references do not cover all valid synonyms or inflections.',
                       'Focus positions come from a development protocol, not general-chat discovery.',
                       'Grammar scope and mandatory target readings remain separate checks.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = args.input.read_bytes(); result = summarize(json.loads(raw))
    result['capture_sha256'] = hashlib.sha256(raw).hexdigest()
    with args.output.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2); stream.write('\n')
    print(json.dumps(result['counts']))
