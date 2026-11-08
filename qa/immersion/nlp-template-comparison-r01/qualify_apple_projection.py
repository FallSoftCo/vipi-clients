#!/usr/bin/env python3
"""Compare actual Apple capture shards to the independent reference projection.

Reads both verbose authored and compact TRAIN serialization without changing inputs.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def signature(candidate):
    return candidate['face_id'], tuple(candidate['source_range_utf16'])


def recognition_signature(recognition):
    return (recognition['rule_id'], tuple(recognition['context_range_utf16']),
            tuple(sorted((k, tuple(v)) for k, v in recognition['part_ranges_utf16'].items())))


def decisions(row, target, arm):
    candidates = arm['output_candidates']
    if 'decisions' in arm:
        by_id = {c['candidate_id']: c for c in candidates}
        for d in arm['decisions']:
            yield d['density'], d['known_snapshot_id'], d, [by_id[i] for i in d['selected_candidate_ids']]
    else:
        for density, known_index, decision_index, elapsed in arm['decision_matrix']:
            d = arm['decision_table'][decision_index]
            yield density, row['known_snapshot_order'][known_index], d, [candidates[i] for i in d['selected_candidate_indices']]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native', action='append', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists(), 'Retain prior qualification; use a new receipt.'
    reference = {r['id']: r for r in map(json.loads, args.reference.open())}
    protocol = json.loads(args.protocol.read_text())
    expected = {r['id']: r for r in protocol['cases']}
    seen, mismatch, recognition_mismatch = set(), [], []
    totals = collections.defaultdict(lambda: dict(available=0, contextual_available=0, changed_words=0, contextual_changed_words=0))
    decision_count, empty_rows = 0, 0
    for path in args.native:
        for line in path.open():
            row = json.loads(line)
            identifier = row['id']
            assert identifier not in seen, identifier
            assert identifier in expected and expected[identifier]['text'] == row['text']
            seen.add(identifier)
            ref = reference.get(identifier, dict(recognitions=[], candidate_tables={}, decisions={}))
            actual_rec = set(map(recognition_signature, row['recognitions']))
            reference_rec = set(map(recognition_signature, ref['recognitions']))
            if actual_rec != reference_rec:
                recognition_mismatch.append(dict(id=identifier, native_only=sorted(actual_rec - reference_rec),
                                                 reference_only=sorted(reference_rec - actual_rec)))
            if not isinstance(row['target_results'], list):
                empty_rows += 1
                if ref['decisions']:
                    mismatch.append(dict(id=identifier, reason='native_wholly_empty_reference_nonempty'))
                continue
            for target in row['target_results']:
                for arm in target['arms']:
                    table = ref['candidate_tables'].get(target['target'] + '|' + arm['arm'], {}).get('admitted', [])
                    for density, known, decision, selected in decisions(row, target, arm):
                        key = '|'.join((target['target'], arm['arm'], str(density), known))
                        projected = [table[i] for i in ref['decisions'].get(key, [])]
                        decision_count += 1
                        if set(map(signature, selected)) != set(map(signature, projected)):
                            mismatch.append(dict(id=identifier, key=key, native=selected, reference=projected))
                        metric = totals[key]
                        metric['available'] += bool(selected)
                        metric['changed_words'] += sum(c['native_cost'] for c in selected)
                        contextual = [c for c in selected if c['recognition_index'] is not None]
                        metric['contextual_available'] += bool(contextual)
                        metric['contextual_changed_words'] += sum(c['native_cost'] for c in contextual)
    output = dict(production=False, semantic_approval=False, provider_calls=0,
                  native=[dict(path=str(p), sha256=sha(p)) for p in args.native],
                  reference_sha256=sha(args.reference), protocol_sha256=sha(args.protocol),
                  comparator_sha256=sha(Path(__file__)), expected_cases=len(expected), actual_cases=len(seen),
                  complete=set(expected) == seen, missing_ids=sorted(set(expected) - seen),
                  decision_count=decision_count, wholly_empty_rows=empty_rows,
                  recognition_mismatches=recognition_mismatch, selection_mismatches=mismatch,
                  all_compared_scopes_equal=not mismatch and not recognition_mismatch,
                  summary=dict(totals),
                  limitations=['Structural projection equality is not semantic correctness.',
                               'Reference must use this same platform native geometry, not another platform tokenizer.',
                               'Elapsed native timing remains in original immutable captures; this join does not pool cold/warm timing.'])
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: output[k] for k in ('expected_cases', 'actual_cases', 'complete', 'decision_count', 'all_compared_scopes_equal')}))


if __name__ == '__main__':
    main()
