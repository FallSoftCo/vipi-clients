from pathlib import Path
import hashlib
import json

R = Path(__file__).resolve().parents[3]
W = R.parent / 'investigations/vipi-contextual-sense-hold-20261109-r01'
source = R / 'data/immersion/starter-en-sw-004.json'
assert hashlib.sha256(source.read_bytes()).hexdigest() == 'e474bfebae95e6f8a6f58c1eeaaf6be65582fad243ae33a6a83e9e1e1f785373'
pack = json.loads(source.read_text())
old_entries = json.loads(source.read_text())['entries']
matches = [entry for entry in pack['entries'] if entry['id'] == 'word-en-sw-hair']
assert len(matches) == 1 and matches[0]['source'] == 'hair' and matches[0]['target'] == 'nywele'
assert 'guard' not in matches[0]
matches[0]['guard'] = 'withheld_contextual_sense'
pack.update(version='starter-en-sw-005', activation=False,
    qualification_status='contextual_sense_hold_awaiting_default_route_qualification',
    sense_hold_parent_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    sense_hold_reason='Unqualified human-head-hair mapping cannot establish animal-coat sense. Retain source recognition and withhold display, including valid human-head uses, pending a separately reviewed contextual rule.')
for before, after in zip(old_entries, pack['entries']):
    assert before == {key: value for key, value in after.items() if not (after['id'] == 'word-en-sw-hair' and key == 'guard')}
out = W / 'candidate-r01'
assert not out.exists()
out.mkdir(parents=True)
data = (json.dumps(pack, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode()
manifest = {'schema': 'vipi-source-starter-manifest-1', 'file': 'starter-en-sw-005.json',
            'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
            'version': 'starter-en-sw-005', 'entries': 213}
(out / manifest['file']).write_bytes(data)
(out / 'starter-sw-catalog.json').write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n')
receipt = {'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
           'source_entry_retained': True, 'target_and_record_provenance_unchanged': True,
           'other_entries_unchanged': 212, 'source_permissions_added': False,
           'candidate_only': True, 'outputs': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}}
(W / 'candidate-build-r01.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt))
