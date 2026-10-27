#!/usr/bin/env python3
"""Merge the explicitly assessed short-response readings into the prior exact asset."""
import argparse
import json
from pathlib import Path
import unicodedata
from build_wiktextract import canonical, digest_file

BASE_SHA = '0fbfa760c2089b6d8619f836de7aa409e6d4d27bfc4a4bba3afcac716c998a51'
READINGS_SHA = '00c690f618dca60ba93d50acd2e2834b6acf1085b39c65ff01ecd3d73e59b347'
ASSESSMENT_SHA = '29267f7dea2715c4e30a6a82c1cb2fd85505c8393a3b4f50d01619f53fe31cc8'
CATALOG_SHA = '4f88f3ced64a31bf255f1ce10e8cc029f0380277ea07eda4bec00b00810e0b66'


def build(base, readings, assessment, catalog, output):
    for path, expected in [(base, BASE_SHA), (readings, READINGS_SHA),
                           (assessment, ASSESSMENT_SHA), (catalog, CATALOG_SHA)]:
        if digest_file(path) != expected:
            raise ValueError('Changed assessed input: ' + str(path))
    previous = json.loads(base.read_text())['entries']
    entries = {(r['language'], r['text']): r['latin'] for r in previous}
    if len(previous) != 410 or len(entries) != 410:
        raise ValueError('Expected 410 unique prior readings')
    references = {(r['pair'].split('-')[1], r['translation'])
                  for r in json.loads(catalog.read_text())['references']}
    additions = json.loads(readings.read_text())
    if len(additions) != 13:
        raise ValueError('Expected thirteen explicit new readings')
    for row in additions:
        key = row['language'], row['text']
        latin = row['latin']
        if key in entries or key not in references or row['language'] not in ('ar', 'zh', 'ja', 'ko'):
            raise ValueError('Unapproved or conflicting native sentence')
        if not latin or len(latin) > 512:
            raise ValueError('Invalid reading length')
        for char in latin:
            if char.isalpha() and ('LATIN' not in unicodedata.name(char, '') or 0x0250 <= ord(char) <= 0x02ff):
                raise ValueError('Native script or IPA in a Latin reading')
        entries[key] = latin
    result = {'schema': 'vipi-sentence-readings-1', 'assessment': 'author_assessment',
              'independent_linguistic_acceptance': False, 'base_sha256': BASE_SHA,
              'assessment_sha256': ASSESSMENT_SHA, 'addition_sha256': READINGS_SHA,
              'catalog_sha256': CATALOG_SHA, 'authoring_sha256': digest_file(Path(__file__)),
              'entries': [{'language': lang, 'text': native, 'latin': latin}
                          for (lang, native), latin in sorted(entries.items())]}
    with output.open('x') as stream:
        stream.write(canonical(result) + '\n')
    print(canonical({'readings': len(entries), 'added': 13, 'sha256': digest_file(output),
                     'bytes': output.stat().st_size, 'independent_linguistic_acceptance': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'readings', 'assessment', 'catalog', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    build(args.base, args.readings, args.assessment, args.catalog, args.output)
