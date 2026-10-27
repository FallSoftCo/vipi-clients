#!/usr/bin/env python3
"""Bind repeated-word failures to their exact source occurrence."""
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
    for target, word in [('fr', 'manger'), ('de', 'essen'), ('it', 'mangiare')]:
        rows = [r for r in cases if (r['dataset'], r['id'], r['source'], r['target']) ==
                ('sms', 'nus-06ee32d204f4aeb3942d1ada', 'en', target)]
        assert len(rows) == 1 and rows[0]['original'][6:9] == 'eat'
        assert 'expected_source' not in rows[0] and 'forbidden_source' not in rows[0]
        rows[0].update(forbidden_source='eat', forbidden_target=word, forbidden_source_start=6)
    cases.append(dict(id='repeated-coffee-separate-sentences', dataset='authored-sentence-scope-behavior',
                      source='en', target='es', original='😀 I drink coffee. I drink coffee.',
                      translation='😀 Yo bebo café. Yo bebo café.',
                      expected_source='coffee', expected_target='café', expected_count=2))
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
