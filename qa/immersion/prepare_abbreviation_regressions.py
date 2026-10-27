#!/usr/bin/env python3
"""Add reviewed name/abbreviation failures without changing existing positives."""
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
    identity = 'liva-sw-0d14f0b15b92cec8ebf453c1'
    matched = [row for row in cases if row['id'] == identity and row['source'] == 'sw' and row['target'] == 'fr']
    assert len(matched) == 1 and 'expected_source' not in matched[0]
    matched[0].update(forbidden_source='Dama', forbidden_target='de')
    # Deliberately mismatching full translations test withholding. They are
    # never source material for dictionary or context-witness construction.
    for identifier, original, translation, source, target in [
        ('abbreviation-is-not-preposition', 'Ninacheza dama.', 'Je viens de jouer aux dames.', 'dama', 'de'),
        ('mid-sentence-capital-name', 'Ninamwona Dama.', 'Je vois la dame.', 'Dama', 'dame'),
    ]:
        cases.append(dict(id=identifier, dataset='authored-name-abbreviation-behavior',
                          source='sw', target='fr', original=original, translation=translation,
                          forbidden_source=source, forbidden_target=target))
    manifest['known_regressions'].append(dict(id=identity, source='sw', target='fr', category='name_and_abbreviation'))
    manifest.update(cases=len(cases), datasets=dict(Counter(row['dataset'] for row in cases)),
                    compiler_sha256=sha(Path(__file__)), prior_manifest_sha256=sha(args.base / 'manifest.json'))
    args.output.mkdir(parents=True, exist_ok=False)
    for shard in manifest['shards']:
        source = args.base / (shard['language'] + '.sqlite')
        assert sha(source) == shard['sha256']
        (args.output / source.name).symlink_to(source.resolve())
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
