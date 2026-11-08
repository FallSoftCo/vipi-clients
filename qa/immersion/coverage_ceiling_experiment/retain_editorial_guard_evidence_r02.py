#!/usr/bin/env python3
"""Retain immutable guard ablations and explicit source-sense editorial choices."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    source = args.evidence_dir / 'scaled-mechanism-cases-r01'
    names = [
        'editorial-guards-diagnostic-freeze-r02.json',
        'editorial-guards-diagnostic-output-r02.json',
        'editorial-guards-independent48-review-r02.json',
        'editorial-guards-author-review-r02.json',
        'editorial-guards-independent-root-review-r02.json',
        'editorial-guards-joined-decision-r02.json',
        'editorial-source-sense-binding-complete-r02.json',
    ]
    assert not args.output_dir.exists()
    args.output_dir.mkdir(parents=True)
    files = []
    for name in names:
        raw = (source / name).read_bytes()
        payload = gzip.compress(raw, compresslevel=9, mtime=0)
        assert gzip.decompress(payload) == raw
        (args.output_dir / (name + '.gz')).write_bytes(payload)
        files.append({'file': name + '.gz', 'bytes': len(payload),
                      'sha256': sha(payload), 'source_bytes': len(raw),
                      'source_sha256': sha(raw)})
    manifest = {
        'schema': 'vipi.editorial-guard-evidence.r02', 'production': False,
        'files': files,
        'dependencies': [
            '../editorial-content500-evidence-r01/manifest.json',
            '../scaled-content-evidence-r01/manifest.json',
            '../diagnose_editorial_guards_r02.py',
        ],
        'reproduction': 'Restore exact evidence files to an isolated evidence-dir layout; run diagnose_editorial_guards_r02.py with the retained frozen candidate, source inventory and licensed BST TRAIN. Frozen input hashes are checked. Elapsed time is observational, not byte-reproducible.',
        'scope': 'Four guard ablations on all 9535 previously used TRAIN turns, three targets and 10/25/50 percent requested density. Source-sense choices are separately authored and do not change the frozen output.',
        'limits': [
            'No native runtime or production pack changed. No fresh holdout or population accuracy claim.',
            'Quote protection in the diagnostic reaches content candidates only; function candidates can bypass it. Unclosed quote behavior is explicitly retained.',
            'Noun-only membership is a complete retained source-role proxy, not proof of universally unique role or sense.',
            'The selected48 review does not qualify all outputs. Employee benefits, pretty gross, baby spinach and contextual Japanese counter reading issues remain visible.',
            'All464 source/POS bindings were inspected;163 changed,6 changed lexeme identity,1 ended adjective withheld. This is source evidence repair, not target or runtime semantic approval.',
        ],
        'licenses': 'Existing pinned Wiktionary/Kaikki and JMdict sources CC BY-SA4.0; BST/ParlAI CC BY4.0. Full entry IDs, URLs and exact primary records remain in the dependency capsules.',
    }
    raw = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
    (args.output_dir / 'manifest.json').write_bytes(raw)
    print(json.dumps({'files': len(files), 'bytes': sum(f['bytes'] for f in files),
                      'manifest_sha256': sha(raw)}))


if __name__ == '__main__':
    main()
