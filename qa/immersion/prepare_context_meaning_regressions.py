#!/usr/bin/env python3
"""Append inspected wrong meanings and retain an explicit withdrawn-rule record."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main(args):
    manifest = json.loads((args.base / 'manifest.json').read_text())
    assert sha(args.base / 'cases.json') == manifest['cases_sha256']
    cases = json.loads((args.base / 'cases.json').read_text())
    findings = json.loads(Path(__file__).with_name('expanded_context_semantic_findings.json').read_text())
    by_id = {(r['dataset'], r['id'], r['source'], r['target']): r for r in cases}
    for finding in findings['confirmed_regressions']:
        row = by_id[tuple(finding['identity'])]
        assert 'expected_source' not in row
        row.update(forbidden_source=finding['source_text'], forbidden_target=finding['target_text'])
    # The full cumulative corpus withdrew the former Spanish cue, including
    # R:home. Requiring it despite contrary source observations was an invalid
    # fixture contract. Keep the loss visible; don't reinstate that weak cue.
    lost = by_id[('sms', 'nus-076049974ceaaf1e7c46f622', 'en', 'es')]
    assert lost['expected_source'] == 'way' and lost['expected_target'] == 'camino'
    lost['availability_watch'] = dict(source=lost.pop('expected_source'), target=lost.pop('expected_target'),
                                    reason='Cumulative input withdrew old context evidence; not repaired coverage.')
    lost.pop('expected_path')
    literal = by_id[('sms', 'nus-076049974ceaaf1e7c46f622', 'en', 'pt')]
    literal.update(expected_source='way', expected_target='caminho', expected_path='combined')
    manifest.update(cases=len(cases), datasets=dict(Counter(r['dataset'] for r in cases)),
                    compiler_sha256=sha(Path(__file__)), findings_sha256=sha(Path(__file__).with_name('expanded_context_semantic_findings.json')),
                    prior_manifest_sha256=sha(args.base / 'manifest.json'),
                    withdrawn_experimental_positive=dict(id=lost['id'], source='en', target='es', span=lost['availability_watch']))
    args.output.mkdir(parents=True, exist_ok=False)
    for shard in manifest['shards']:
        path = args.base / (shard['language'] + '.sqlite')
        assert sha(path) == shard['sha256']
        (args.output / path.name).symlink_to(path.resolve())
    path = args.output / 'cases.json'
    path.write_text(json.dumps(cases, ensure_ascii=False, separators=(',', ':')) + '\n')
    manifest['cases_sha256'] = sha(path)
    (args.output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(cases=len(cases), manifest_sha256=sha(args.output / 'manifest.json'))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args())
