#!/usr/bin/env python3
"""Retain corrected source-only candidate and rejected competing-role arm."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--evidence-dir', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    a = p.parse_args()
    M = a.evidence_dir/'scaled-mechanism-cases-r01'
    names = ['editorial-source-role-proof-r03.json', 'editorial-runtime-candidate-r03.json',
             'editorial-runtime-freeze-r03.json', 'editorial-runtime-TRAIN-output-r03.json',
             'editorial-runtime-independent48-review-r03.json', 'editorial-runtime-author-review-r03.json',
             'editorial-runtime-independent-root-review-r03.json', 'editorial-runtime-literal-controls-r03.json',
             'editorial-runtime-joined-decision-r03.json']
    assert not a.output_dir.exists()
    a.output_dir.mkdir(parents=True)
    files = []
    sha = lambda b: hashlib.sha256(b).hexdigest()
    for name in names:
        raw = (M/name).read_bytes()
        payload = gzip.compress(raw, compresslevel=9, mtime=0)
        assert gzip.decompress(payload) == raw
        (a.output_dir/(name+'.gz')).write_bytes(payload)
        files.append({'file': name+'.gz', 'bytes': len(payload), 'sha256': sha(payload),
                      'source_bytes': len(raw), 'source_sha256': sha(raw)})
    manifest = {'schema': 'vipi.editorial-runtime-evidence.r03', 'production': False,
                'files': files, 'dependencies': ['../editorial-content500-evidence-r01/manifest.json',
                    '../editorial-guard-evidence-r02/manifest.json', '../scaled-content-evidence-r01/manifest.json'],
                'reproduction': ['Prepare candidate from the retainedr01 target faces, explicit464 source bindings and existing bundled d-en source shard. Exact source-role rows are retained, so no remote archive read is required to inspect them.',
                    'evaluate_editorial_runtime_r03.py replays exact9535 licensed TRAIN turns and verifies the frozen input/source hashes. Elapsed time is observational.',
                    'editorial_runtime_lookup_r03.py is the indexed research producer. No app activation is performed.'],
                'licenses': ['Wiktionary/Kaikki exact source-role and target records CC BY-SA4.0 with retained entry IDs/URLs.',
                             'JMdict/EDRDG selected Japanese readings/senses CC BY-SA4.0.',
                             'BST/ParlAI source conversations CC BY4.0; notices in ../evaluation-data-licenses.'],
                'decision': ['Core selected24 jointly meaning-compatible; no blanket1139-entry semantic approval.',
                             'Broad competing-attributive guard is rejected for excessive false abstention.',
                             'Known compound/idiom and source-reading context errors remain; no production data enablement.',
                             'Native selection seam can be qualified independently using SOURCE_UNIT_RUNTIME_R03.md.']}
    raw = (json.dumps(manifest, ensure_ascii=False, indent=2)+'\n').encode()
    (a.output_dir/'manifest.json').write_bytes(raw)
    print(json.dumps({'files': len(files), 'bytes': sum(x['bytes'] for x in files), 'manifest_sha256': sha(raw)}))


if __name__ == '__main__':
    main()
