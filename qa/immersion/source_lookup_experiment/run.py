#!/usr/bin/env python3
"""Run a frozen, nonproduction source-only candidate on a public QA protocol."""
import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path
from matcher import Matcher, tokens

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--candidate', type=Path, required=True)
p.add_argument('--protocol', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
freeze = json.loads((a.candidate / 'freeze.json').read_text())
pack_bytes = (a.candidate / 'pack.json').read_bytes()
sha = lambda raw: hashlib.sha256(raw).hexdigest()
if sha(pack_bytes) != freeze['pack_sha256'] or sha(Path(__file__).with_name('matcher.py').read_bytes()) != freeze['matcher_sha256']:
    raise SystemExit('Candidate identity changed since freeze.')
pack = json.loads(pack_bytes)
matcher = Matcher(pack)
rules = {r['id']: r for r in pack['rules']}
pairs = {(r['source'], r['target']) for r in pack['rules']}
protocol_bytes = a.protocol.read_bytes()
protocol = json.loads(protocol_bytes)
rows = []
for case in protocol['cases']:
    source, target, original = case['source'], case['target'], case['text']
    if (source, target) not in pairs:
        rows.append({'id': case['id'], 'source': source, 'target': target, 'status': 'pair_not_in_candidate'})
        continue
    start = time.perf_counter_ns()
    mixed, spans = matcher.present(original, source, target)
    milliseconds = (time.perf_counter_ns() - start) / 1e6
    for span in spans:
        span['mappingSHA256'] = rules[span['mappingId']]['record_sha256']
        span['candidatePackSHA256'] = freeze['pack_sha256']
        span['targetStartUTF16'] = 0
        span['targetEndUTF16'] = len(span['targetText'].encode('utf-16-le')) // 2
    words = sum(any(c.isalpha() for c in t.text) for t in tokens(original))
    rows.append({'id': case['id'], 'source': source, 'target': target,
                 'status': 'executed', 'original': original, 'mixed': mixed, 'spans': spans,
                 'source_words': words, 'milliseconds': milliseconds,
                 'local_translation_calls': 0})
summary = {}
for source, target in sorted(pairs):
    selected = [r for r in rows if r['source'] == source and r['target'] == target and r['status'] == 'executed']
    if not selected:
        continue
    summary[source + '-' + target] = {
        'messages': len(selected), 'messages_with_span': sum(bool(r['spans']) for r in selected),
        'spans': sum(len(r['spans']) for r in selected),
        'median_ms': statistics.median(r['milliseconds'] for r in selected),
        'mean_message_depth': statistics.mean(sum(s['experimentalSourceTokenCount'] for s in r['spans']) / max(1, r['source_words']) for r in selected)}
report = {'schema': 'vipi-source-only-candidate-run-1', 'release_ready': False,
          'independent_semantic_acceptance': False, 'complete_native_pipeline': False,
          'input_sha256': sha(protocol_bytes), 'pack_sha256': freeze['pack_sha256'],
          'matcher_sha256': freeze['matcher_sha256'], 'summary': summary, 'results': rows}
with a.output.open('x') as output:
    json.dump(report, output, ensure_ascii=False, indent=2)
    output.write('\n')
print(json.dumps(summary, ensure_ascii=False, indent=2))
