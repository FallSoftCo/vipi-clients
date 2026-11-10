"""Inspect risk/retention on exposed diagnostics; never fit or publish a gate."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics
import unicodedata

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def normalized(s):
    s = unicodedata.normalize('NFC', s).casefold().strip()
    while s and unicodedata.category(s[0]).startswith('P'): s = s[1:].strip()
    while s and unicodedata.category(s[-1]).startswith('P'): s = s[:-1].strip()
    return ' '.join(s.split())

def metrics(rows, labels, selected):
    accepted = [r for r in rows if selected(r)]
    counts = Counter(labels[r['id']] for r in accepted)
    return {'selected': len(accepted), 'available': len(rows), 'labels': dict(counts),
            'retained_fraction': len(accepted)/len(rows) if rows else None,
            'material_fraction_of_selected': counts['material']/len(accepted) if accepted else None,
            'uncertain_fraction_of_selected': counts['uncertain']/len(accepted) if accepted else None,
            'note': 'Exploratory diagnostic, not population accuracy or calibrated probability.'}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--review', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    p = Path(__file__).resolve().parent
    assert not args.output.exists(), 'Preserve previous analysis.'
    capture = p/'native/capture.jsonl'; packet = p/'meaning-review-packet.json'
    raw = [json.loads(line) for line in capture.read_text().splitlines()]
    assert raw[-1]['kind'] == 'complete'
    review = json.loads(args.review.read_text())
    assert review['packet_sha256'] == sha(packet)
    rows = [r for r in raw if r['kind']=='case' and r['status']=='complete']
    # Both reviewers retain their own frozen schemas; never rewrite their labels.
    labels = {r.get('id', r.get('rowid')): r['label'] for r in review['rows']}
    assert len(labels) == len(review['rows'])
    assert set(labels) == {r['id'] for r in rows} and len(labels) == len(rows)
    assert set(labels.values()) <= {'compatible', 'minor', 'material', 'uncertain'}
    output = {'schema': 'vipi-confidence-diagnostic-analysis-1',
              'capture_sha256': sha(capture), 'review_sha256': sha(args.review), 'analyzer_sha256': sha(Path(__file__)),
              'reviewer': review.get('reviewer'), 'production_gate': False,
              'thresholds_calibrated': False, 'scores_are_probabilities': False,
              'independent_native_speaker_gold': False, 'groups': {}, 'latency_ms': {}}
    for origin in ['native_translation', 'authored_diagnostic']:
        group = [r for r in rows if r['candidate_origin']==origin]
        report = {'unfiltered': metrics(group, labels, lambda _: True),
                  'exact_round_trip': metrics(group, labels, lambda r: normalized(r['original']) == normalized(r['round_trip'])),
                  'similarity_thresholds': {}, 'per_target': {}}
        for threshold in [.5, .6, .65, .7, .75, .8, .85, .9, .95]:
            report['similarity_thresholds'][str(threshold)] = metrics(group, labels,
                lambda r: r.get('english_sentence_cosine_similarity', -2) >= threshold)
        for target in sorted({r['target'] for r in group}):
            subset = [r for r in group if r['target']==target]
            report['per_target'][target] = metrics(subset, labels, lambda _: True)
        output['groups'][origin] = report
    native = [r for r in rows if r['candidate_origin']=='native_translation']
    for key in ['forward_ms', 'reverse_ms', 'embedding_ms']:
        vals = sorted(r[key] for r in native if key in r)
        output['latency_ms'][key] = {'n': len(vals), 'median': statistics.median(vals),
            'p95_nearest_rank': vals[math.ceil(.95*len(vals))-1], 'max': max(vals)}
    output['errors'] = [{'id': r['id'], 'origin': r['candidate_origin'],
        'similarity': r.get('english_sentence_cosine_similarity'),
        'normalized_exact': normalized(r['original']) == normalized(r['round_trip'])}
        for r in rows if labels[r['id']] in ('material', 'uncertain')]
    output['limitations'] = [
        'Only18 distinct English sources (8 already-exposed BST messages and10 authored); translations across9 targets share sources and are not independent samples.',
        '12 deliberately authored Spanish candidates are a separate adversarial diagnostic, not natural error prevalence.',
        'No source-language reversal or all-pair qualification; native Mac timings do not establish phone performance.',
        'System model versions and translation quality confidence are not exposed; networking remained enabled.',
        'Similarity thresholds are explored on this packet, not chosen on a separate calibration set; never activate from this result.',
        'Round-trip quality can be damaged by the backward translator or conceal forward errors; target meaning needs independent review.',
        'Whole-sentence quality does not approve individual source-to-target substitutions.'
    ]
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'output': str(args.output), 'sha256': sha(args.output),
        'native': output['groups']['native_translation']['unfiltered'],
        'at_0_7': output['groups']['native_translation']['similarity_thresholds']['0.7']}))

if __name__ == '__main__': main()
