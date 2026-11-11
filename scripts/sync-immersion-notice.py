#!/usr/bin/env python3
"""Refresh the existing hash-named Apple notice; Android bundles the source via Gradle Sync."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    source = ROOT / 'data/immersion/NOTICE.txt'
    data = source.read_bytes()
    data.decode('utf-8', errors='strict')
    digest = hashlib.sha256(data).hexdigest()
    directory = ROOT / 'ios/Vipi/ThirdPartyNotices'
    index = directory / 'index.json'
    entries = json.loads(index.read_text())
    matches = [row for row in entries if row['id'] == 'immersion-starter-data']
    assert len(matches) == 1
    row = matches[0]
    previous = row['file']
    filename = 'immersion-starter-notice-' + digest + '.txt'
    (directory / filename).write_bytes(data)
    row.update(title='Immersion language data — JMdict, Wiktionary and project adaptations',
               file=filename, sha256=digest,
               origin='data/immersion/NOTICE.txt; official CC BY-SA 4.0 legalcode.txt; directional provenance in language-packs/directional-dictionary-007/inputs')
    index.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + '\n')
    if previous != filename and previous.startswith('immersion-starter-notice-'):
        if not any(entry['file'] == previous for entry in entries):
            (directory / previous).unlink(missing_ok=True)
    print(json.dumps({'sha256': digest, 'bytes': len(data), 'apple_asset': filename,
                      'android': 'Existing stageImmersionAssets Gradle task copies data/immersion/NOTICE.txt; no separate notice index entry.'}))

if __name__ == '__main__':
    main()
