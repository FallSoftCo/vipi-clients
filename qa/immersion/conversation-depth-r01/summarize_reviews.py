from pathlib import Path
import collections
import hashlib
import json
import statistics

R = Path(__file__).resolve().parents[3]
W = R.parent / 'investigations/vipi-conversation-depth-20261109-r01'
rows = [json.loads(line) for line in (W / 'apple-capture-r01/inputs-r01/apple-output.jsonl').read_text().splitlines()]
bindings = json.loads((W / 'review-r01/bindings.json').read_text())
packet = json.loads((W / 'review-r01/packet.json').read_text())
expected = {(case['id'], option['id']) for case in packet['cases'] for option in case['options']}
scores, labels = [], {}
for reviewer in ('root', 'author'):
    review = json.loads((W / (reviewer + '-review-r01.json')).read_text())
    assert review['complete']
    lookup = {(row['case'], row['option']): row for row in review['rows']}
    assert set(lookup) == expected and len(lookup) == len(review['rows']) == 189
    labels[reviewer] = lookup
    for pair in ('en-ja', 'en-sw'):
        for density in (0.25, 0.75):
            for stratum in ('all', 'persona', 'empathetic'):
                selected = [row for row in rows if row['pair'] == pair and row['density'] == density
                            and (stratum == 'all' or row['stratum'] == stratum)]
                values, strict_depth, minor_depth, useful_depth = [], [], [], []
                useful = minor_useful = covered = words = 0
                for row in selected:
                    binding = bindings[f"{row['id']}:{pair}:{density}"]
                    verdict = lookup[(binding['case'], binding['option'])]
                    values.append(verdict['label'])
                    content = verdict['useful_span_indices']
                    assert all(0 <= index < len(row['spans']) for index in content)
                    denominator = len(row['native_words'])
                    def word_cost(spans):
                        return sum(any(span['source_utf16'][0] <= start and end <= span['source_utf16'][1]
                                       for span in spans) for start, end in row['native_words'])
                    cost = word_cost(row['spans'])
                    depth = cost / denominator if denominator else 0
                    compatible = verdict['label'] == 'compatible'
                    tolerant = verdict['label'] in ('compatible', 'minor')
                    strict_depth.append(depth if compatible else 0)
                    minor_depth.append(depth if tolerant else 0)
                    useful_depth.append(word_cost([row['spans'][index] for index in content]) / denominator
                                        if denominator and compatible else 0)
                    useful += bool(content) and compatible
                    minor_useful += bool(content) and tolerant
                    covered += cost
                    words += denominator
                scores.append({'reviewer': reviewer, 'pair': pair, 'density': density, 'stratum': stratum,
                    'messages': len(selected), 'labels': dict(collections.Counter(values)),
                    'strict_useful_messages': useful, 'minor_inclusive_useful_messages': minor_useful,
                    'macro_strict_correct_depth': statistics.mean(strict_depth),
                    'macro_minor_inclusive_correct_depth': statistics.mean(minor_depth),
                    'macro_strict_useful_content_depth': statistics.mean(useful_depth),
                    'selected_native_words': covered, 'native_words': words})
disagreements = [{'case': key[0], 'option': key[1], 'root': labels['root'][key], 'author': labels['author'][key]}
                 for key in sorted(expected)
                 if any(labels['root'][key][field] != labels['author'][key][field]
                        for field in ('label', 'useful_span_indices'))]
report = {'schema': 'vipi-conversation-depth-reviewed-scorecard-1', 'baseline_revision': '1d42f9c',
    'source_messages': 80, 'native_rows_per_platform': 320, 'distinct_reviewed_options': 189,
    'model_availability_forced_unavailable': True,
    'scope': 'Local lookup coverage only; does not measure installed translation-model fallback or learning outcomes.',
    'source_frame_units_selected': 0, 'exact_reference_hits': 0,
    'native_human_gold': False, 'reviewers_kept_separate': True,
    'scores': scores, 'disagreements': disagreements,
    'bindings': {name: hashlib.sha256((W / name).read_bytes()).hexdigest() for name in
                 ['root-review-r01.json', 'author-review-r01.json', 'review-r01/packet.json',
                  'root-platform-verification-r01.json', 'selection-freeze.json']}}
destination = W / 'reviewed-scorecard-r01.json'
assert not destination.exists()
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'disagreements': len(disagreements), 'scores': [score for score in scores
    if score['density'] == 0.75 and score['stratum'] == 'all']}, indent=2))
