#!/usr/bin/env python3
"""Research-only test of shared target surfaces across ALL catalog meanings.

Reuses a native candidate export and signed candidate dictionaries. No model,
runtime policy or customer-facing output is changed. These reused examples are
regression data, never independent acceptance data.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'language-packs'))
from context_hints import lookup_key


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(args):
    args.output.mkdir(exist_ok=False)
    captured = json.loads(args.candidates.read_text())
    protocol = {'policy': 'all-source-catalog-senses-share-the-observed-target-3',
                'compiler_sha256': digest(Path(__file__)),
                'runtime_integration': False, 'linguistic_acceptance': False,
                'acceptance_corpus': False, 'candidate_capture_sha256': digest(args.candidates),
                'pack_receipt_sha256': digest(args.packs / 'receipt.json'),
                'preserves': ['native lexical ambiguity checks', 'mandatory reading checks', 'native protected spans', 'native contrary sentence cues'],
                'limits': ['dictionary senses may be incomplete', 'shared surfaces do not prove sentence alignment',
                           'inflection and omitted readings still limit coverage', 'newer-pack source exclusions only reduce old candidate set'],
                'review_requirements': ['known financial-bank and morgen errors must remain excluded',
                                        'inspect all selected spans before any integration', 'run untouched acceptance data before release']}
    if 'attribution' in captured: protocol['attribution'] = captured['attribution']
    (args.output / 'protocol.json').write_text(json.dumps(protocol, indent=2) + '\n')
    counts = collections.Counter(); rows = []; empty = []
    for pair in captured['results']:
        pair_id = pair['source'] + '-' + pair['target']; selected_pair = 0
        path = args.packs / pair_id / 'vocabulary.sqlite'
        manifest = json.loads((path.parent / 'manifest.json').read_text())
        assert digest(path) == manifest['sha256']
        assert manifest['schema_version'] == 4 and manifest['context_policy'] == 'all-source-senses-veto-3', 'Old pair catalogs omit competing source senses'
        with sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True) as db:
            for sample in pair['samples']:
                selected = []
                for candidate in sample['context_candidates']:
                    meanings = collections.defaultdict(set)
                    # Identical labels can belong to different parts of speech.
                    # Never merge their target sets to manufacture agreement.
                    for sense_id, target in db.execute('''SELECT s.sense_id,v.target FROM source_senses s
                        LEFT JOIN vocabulary v ON v.source=s.source AND v.sense_id=s.sense_id WHERE s.source=?''',
                        (lookup_key(candidate['original'], pair['source']),)):
                        surfaces = meanings[sense_id]
                        if target is not None: surfaces.add(lookup_key(target, pair['target']))
                    target = lookup_key(candidate['translated'], pair['target'])
                    if meanings and all(target in surfaces for surfaces in meanings.values()):
                        selected.append(dict(candidate, attested_senses=len(meanings)))
                # Native candidate export has already enforced non-overlap. Use
                # its actual token boundaries for a 30% display budget.
                budget = max(1, int(len(sample['source_words']) * .3)); used = 0; spans = []
                for candidate in sorted(selected, key=lambda c: (-(c['end']-c['start']), c['start'])):
                    words = max(1, sum(w['start'] >= candidate['start'] and w['end'] <= candidate['end'] for w in sample['source_words']))
                    if used + words <= budget: spans.append(candidate); used += words
                spans.sort(key=lambda c: c['start'])
                rows.append({'pair': pair_id, 'case': sample['id'], 'original': sample['original'],
                             'translation': sample['translation'], 'reference': sample.get('reference'), 'spans': spans})
                counts['samples'] += 1; counts['with_spans'] += bool(spans); counts['spans'] += len(spans)
                selected_pair += len(spans)
        if not selected_pair: empty.append(pair_id)
    report = {**protocol, **counts, 'pairs': len(captured['results']), 'zero_span_pairs': empty, 'results': rows}
    (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({**counts, 'pairs': len(captured['results']), 'zero_span_pairs': empty, 'linguistic_acceptance': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidates', type=Path, required=True)
    parser.add_argument('--packs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args())
