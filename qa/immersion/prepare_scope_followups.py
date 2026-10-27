#!/usr/bin/env python3
"""Retain two meaning/occurrence failures found after sentence-scope expansion."""
import argparse
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
    found = []
    for identifier, target, source_text, target_text, offset, reason in [
        ('nus-03754c412c794aebc8ca207c', 'es', 'lect', 'lecto', None, 'Lecture abbreviation was treated as a linguistic variety.'),
        ('nus-0418003d9a3aa212fc71b032', 'ja', 'buy', '買う', 71, 'First buy in a repeated-word clause was linked to the later target occurrence.')
    ]:
        matches = [r for r in cases if (r['dataset'], r['id'], r['source'], r['target']) == ('sms', identifier, 'en', target)]
        assert len(matches) == 1 and 'expected_source' not in matches[0] and 'forbidden_source' not in matches[0]
        row = matches[0]
        row.update(forbidden_source=source_text, forbidden_target=target_text)
        if offset is not None:
            assert row['original'][offset:offset + len(source_text)] == source_text
            row['forbidden_source_start'] = offset
        found.append(dict(id=identifier, source='en', target=target, reason=reason, observed_run='026'))
    manifest.update(compiler_sha256=sha(Path(__file__)), prior_manifest_sha256=sha(args.base / 'manifest.json'),
                    author_scope_followups=found)
    args.output.mkdir(parents=True, exist_ok=False)
    for shard in manifest['shards']:
        path = args.base / (shard['language'] + '.sqlite')
        assert sha(path) == shard['sha256']
        (args.output / path.name).symlink_to(path.resolve())
    path = args.output / 'cases.json'
    path.write_text(json.dumps(cases, ensure_ascii=False, separators=(',', ':')) + '\n')
    manifest['cases_sha256'] = sha(path)
    # Preserve evaluation provenance and exclusions alongside a derived fixture.
    for name in ('diagnostic-receipt.json', 'evaluation-exclusions.sqlite', 'EVALUATION-NOTICE.txt'):
        if (args.base / name).exists():
            (args.output / name).symlink_to((args.base / name).resolve())
    (args.output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(cases=len(cases), manifest_sha256=sha(args.output / 'manifest.json'))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args())
