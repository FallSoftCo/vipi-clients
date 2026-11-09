#!/usr/bin/env python3
"""Verify exact bundled source-context models/libraries/licenses, without network."""
from pathlib import Path
import hashlib
import json

root = Path(__file__).resolve().parents[1]
vendor = root / 'android/app/vendor/source-context'
manifest = json.loads((vendor / 'manifest.json').read_text())
assert manifest['schema'] == 'vipi.android-source-context-assets.r01'
assets = vendor / 'assets/source-context'
expected = set()
for group, directory in [('dependencies', vendor / 'libs'), ('models', assets), ('licenses', assets / 'licenses')]:
    for name, pin in manifest[group].items():
        assert Path(name).name == name
        path = directory / name
        assert path.is_file() and not path.is_symlink(), path
        data = path.read_bytes()
        assert len(data) == pin['bytes'] and hashlib.sha256(data).hexdigest() == pin['sha256'], path
        expected.add(path.relative_to(vendor).as_posix())
table = assets / 'unicode15.json'
data = table.read_bytes()
assert len(data) == manifest['unicode15']['bytes'] == 51278
assert hashlib.sha256(data).hexdigest() == manifest['unicode15']['sha256'] == '930b68ddf7c328233125eeb56a68b6863a9b97942a7a5023128e6ad34b489879'
expected.add(table.relative_to(vendor).as_posix())
actual = {p.relative_to(vendor).as_posix() for p in vendor.rglob('*') if p.is_file() and p.name not in {'manifest.json', '.gitignore', 'PROVENANCE.md'}}
assert actual == expected, (actual - expected, expected - actual)
print('Pinned offline source-context assets and licenses verified.')
