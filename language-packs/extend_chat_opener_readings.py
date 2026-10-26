#!/usr/bin/env python3
"""Merge the explicitly assessed opener readings into the prior exact asset."""
import argparse
import json
from pathlib import Path
import unicodedata
from build_wiktextract import canonical, digest_file

BASE_SHA = '244c5c12e99572c7303808408e29062c7e2dd02e269b917b3cf1dacf29ad4854'
READINGS_SHA = '6bb24f7cfacdfe0237a8b4a582954ffeaaaf85de53206f000a77d57a7d3a1b0b'
ASSESSMENT_SHA = 'f9896e1b1360402aea8eb3135f7d8007bbe2004f991a9ff24981cc28efe255da'
CATALOG_SHA = '0b04233cc386d74bca4828f8e336b799341ab23f9ac4a0ede4a40853ea2b1e80'


def build(base, readings, assessment, catalog, output):
    for path, expected in [(base, BASE_SHA), (readings, READINGS_SHA),
                           (assessment, ASSESSMENT_SHA), (catalog, CATALOG_SHA)]:
        if digest_file(path) != expected:
            raise ValueError('Changed assessed input: ' + str(path))
    previous = json.loads(base.read_text())['entries']
    entries = {(r['language'], r['text']): r['latin'] for r in previous}
    if len(previous) != 390 or len(entries) != 390:
        raise ValueError('Expected 390 unique prior readings')
    references = {(r['pair'].split('-')[1], r['translation'])
                  for r in json.loads(catalog.read_text())['references']}
    additions = json.loads(readings.read_text())
    if len(additions) != 20:
        raise ValueError('Expected twenty explicit new readings')
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
    print(canonical({'readings': len(entries), 'added': 20, 'sha256': digest_file(output),
                     'bytes': output.stat().st_size, 'independent_linguistic_acceptance': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'readings', 'assessment', 'catalog', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    build(args.base, args.readings, args.assessment, args.catalog, args.output)
