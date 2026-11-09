"""Compare retained native results; no inference, Android calls or network."""
from pathlib import Path
import argparse, json, hashlib, collections

ROOT = Path(__file__).resolve().parent
APPLE = Path('/home/ai/Development/investigations/vipi-apple-delivery-20261107-r01/native-context-pack-20261109-r01/independent-review-r01')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
encoded = lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(',', ':'))

def normalize_units(units, android=False):
    out = []
    for unit in units:
        copy = dict(unit)
        forms = []
        for form in unit['forms']:
            f = dict(form)
            if android:
                f['range'] = f.pop('intrinsic')
            f['features'] = sorted(f['features'])
            forms.append(f)
        copy['forms'] = sorted(forms, key=encoded)
        out.append(copy)
    return sorted(out, key=encoded)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('variant', choices=['debug', 'release'])
    args = parser.parse_args()
    output = ROOT / (args.variant + '-apple-comparison.json')
    assert not output.exists()
    pins = {'ios-pack.json': '08fbec7753d0cd0b6d50230105729bda9bfd07f2af76b41b24b594b135518125',
            'recognition-r02.json': 'b31f087180b3280c80fc47e5c3b0dcc270b0cceafcbd6aa2129a64df9a93637f'}
    for name, digest in pins.items():
        assert sha(APPLE / name) == digest
    groups = collections.defaultdict(list)
    source = ROOT / ('probe-' + args.variant + '-run.stdout')
    for line in source.read_text().splitlines():
        if 'CONTEXT_ROW:' in line:
            row = json.loads(line.split('CONTEXT_ROW:', 1)[1])
            groups[row['kind']].append(row['value'])
    ios = json.loads((APPLE / 'ios-pack.json').read_text())
    recognition = json.loads((APPLE / 'recognition-r02.json').read_text())['cases']
    differences = []
    assert len(groups['rule']) == len(ios['observations']) == 1157
    for a, b in zip(ios['observations'], groups['rule']):
        for key in ['rule_id', 'winner', 'heads', 'whole_native_geometry_equal']:
            if a.get(key) != b.get(key):
                differences.append({'scope': 'rule', 'id': a['rule_id'], 'field': key})
    assert len(groups['full_source']) == len(ios['full_sources']) == len(recognition) == 52
    for a, b, r in zip(ios['full_sources'], groups['full_source'], recognition):
        assert a['case_id'] == b['case_id'] == r['case_id']
        snap = b['snapshot']
        checks = {
            'native_words': a['current_native_ranges'] == b['native'],
            'original': a['source'] == snap['original'],
            'source_id': a['source_id'] == b['source_id'],
            'dictionary_release': r['release'] == snap['release'],
            'dictionary_inventory': r['inventory'] == snap['inventory'],
            'named_places': r['named_places'] == snap['named_places'],
            'phrases': r['phrase_ranges'] == snap['phrases'],
            'all_unit_form_guard_fields': normalize_units(r['units']) == normalize_units(snap['units'], True),
            'focuses': [{'focus': f['focus'], 'source': f['source'], 'winner': f['current_winner'],
                         'geometry_rejections': f['current_geometry_rejections']} for f in a['focuses']] == b['focuses'],
        }
        differences.extend({'scope': 'full_source', 'id': a['case_id'], 'field': k}
                           for k, equal in checks.items() if not equal)
    result = {'variant': args.variant, 'rule_count': len(groups['rule']), 'full_source_count': 52,
              'comparison': 'Actual retained iOS outputs versus Android; unit/form order canonicalized, duplicates retained',
              'differences': differences, 'android_stdout_sha256': sha(source), 'apple_pins': pins,
              'scope': 'Matcher and dictionary recognition parity only; no semantic, coverage, UI or display permission claim'}
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
