#!/usr/bin/env python3
"""Bind complete native qualification to immutable bulk data/source identities."""
import argparse
import hashlib
import json
from pathlib import Path
from analyze_lexical_qualification import read


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main(args):
    results = []
    inputs = [args.fixture / 'manifest.json', args.fixture / 'cases.json', args.catalog,
              args.witness / 'receipt.json', args.delivery_budget]
    manifest = json.loads((args.fixture / 'manifest.json').read_text())
    catalog = json.loads(args.catalog.read_text())
    assert {r['language']: (r['sha256'], r['bytes']) for r in manifest['shards']} == {
        r['language']: (r['sha256'], r['bytes']) for r in catalog['shards']}
    witness = json.loads((args.witness / 'receipt.json').read_text())
    assert witness['complete'] and witness['sha256'] == sha(args.witness / 'witnesses.sqlite')
    assert witness['source_release_id'] == catalog['release_id']
    for platform, path, snapshot in [('android', args.android, args.android_source), ('ios', args.ios, args.ios_source)]:
        summary, _ = read(args.fixture, path)
        raw = json.loads(path.read_text())
        assert summary['passed'] and raw['context_guard_checks']
        assert raw['witness_sha256'] == witness['sha256']
        source = json.loads(snapshot.read_text())
        assert source['run'] == raw['run'] and source['dictionary_release'] == catalog['release_id']
        assert source['witness_sha256'] == witness['sha256']
        for row in source['files']:
            if row['path'].startswith('android/' if platform == 'android' else 'ios/'):
                assert sha(Path(row['path'])) == row['sha256'], 'Working source differs from tested snapshot'
        groups = {k: v for k, v in summary['groups'].items() if ':' not in k}
        result = dict(platform=platform, run=raw['run'], cases=raw['cases'], report_sha256=sha(path),
                      source_snapshot_sha256=sha(snapshot), passed=True, groups=groups)
        if platform == 'ios':
            samples = raw['memory_samples']
            assert samples and all(s['physical_footprint_bytes'] > 0 for s in samples)
            result['physical_footprint'] = dict(first_bytes=samples[0]['physical_footprint_bytes'],
                maximum_sampled_bytes=max(s['physical_footprint_bytes'] for s in samples),
                final_bytes=samples[-1]['physical_footprint_bytes'], samples=len(samples),
                limitation='Periodic process physical footprint samples, not an allocation profiler or production memory limit.')
        results.append(result)
        inputs.extend([path, snapshot])
    budget = json.loads(args.delivery_budget.read_text())
    assert budget['complete'] and not budget['production_ready']
    result = dict(schema='vipi-bulk-native-qualification-1', complete=True, native_regressions_passed=True,
                  dictionary_release=catalog['release_id'], witness_sha256=witness['sha256'],
                  manifest_sha256=sha(args.fixture / 'manifest.json'), platforms=results,
                  inputs=[dict(file=str(p), sha256=sha(p)) for p in inputs],
                  installed_language_data_bytes=budget['installed_bytes'], language_data_zip_bytes=budget['download_bytes'],
                  independent_semantic_acceptance=False, majority_chat_coverage_demonstrated=False,
                  production_installer_qualified=False, production_default_changed=False, store_ready=False,
                  limitation='Component tests check retained positives, known negatives, offsets, transliteration presence and baseline retention. Dataset message availability is not semantic accuracy or population coverage. Exported subsets are SQL-equal to the tested authoring witness rows; no native production download has been exercised.')
    with args.output.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(dict(complete=True, cases=[r['cases'] for r in results], runs=[r['run'] for r in results],
                          ios_footprint=results[1]['physical_footprint'], sha256=sha(args.output))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('fixture', 'catalog', 'witness', 'delivery-budget', 'android', 'ios', 'android-source', 'ios-source', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    main(parser.parse_args())
