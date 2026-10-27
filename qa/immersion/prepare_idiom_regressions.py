#!/usr/bin/env python3
"""Retain observed idiom errors and a literal route positive in native replay."""
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
    observed = [r for r in cases if (r['dataset'], r['id'], r['source'], r['target']) ==
                ('sms', 'nus-02593b5a543a5b4c48e871e7', 'en', 'ar')]
    assert len(observed) == 1 and 'expected_source' not in observed[0]
    observed[0].update(forbidden_source='way', forbidden_target='طريق')
    literal = [r for r in cases if (r['dataset'], r['id'], r['source'], r['target']) ==
               ('sms', 'nus-076049974ceaaf1e7c46f622', 'en', 'es')]
    assert len(literal) == 1 and 'forbidden_source' not in literal[0]
    literal[0].update(expected_source='way', expected_target='camino', expected_path='combined')
    # These deliberately mismatching translations are negative selector tests,
    # never source evidence or claims about native translation correctness.
    for suffix, original in [('canonical', 'I am free all the way until two.'),
                             ('sms-d', 'I am free all d way until two.'),
                             ('emoji-spaces', '😀 I am free all  e\tway until two.')]:
        cases.append(dict(id='idiom-' + suffix, dataset='authored-idiom-behavior',
                          source='en', target='ar', original=original,
                          translation='أنا حر طوال الطريق حتى الثانية.',
                          forbidden_source='way', forbidden_target='طريق'))
    cases.append(dict(id='idiom-target-fragment', dataset='authored-idiom-behavior',
                      source='ar', target='en', original='طريق إلى المنزل.',
                      translation='I am free all e way until two.',
                      forbidden_source='طريق', forbidden_target='way'))
    assert len({(r['dataset'], r['id'], r['source'], r['target']) for r in cases}) == len(cases)
    manifest['known_regressions'].append(dict(id=observed[0]['id'], source='en', target='ar', category='sms_idiom_fragment'))
    manifest.update(cases=len(cases), datasets=dict(Counter(r['dataset'] for r in cases)),
                    compiler_sha256=sha(Path(__file__)), prior_manifest_sha256=sha(args.base / 'manifest.json'))
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
