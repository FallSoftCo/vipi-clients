#!/usr/bin/env python3
"""Pin MASSIVE 1.1 and inventory partitions/annotation types without printing text.

This is source acquisition, not translation acceptance or runtime promotion.
Localized entities are not interchangeable translations. Future mining must
respect official partitions and exclude all earlier development/evaluation text.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import tarfile
import urllib.request

COMMIT = 'f966f21846043aabef9b0f974fa7970027f43738'
URL = 'https://amazon-massive-nlu-dataset.s3.amazonaws.com/amazon-massive-dataset-1.1.tar.gz'
EXPECTED_BYTES = 40251390


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def fetch(url, path, maximum, expected=None):
    request = urllib.request.Request(url, headers={'User-Agent': 'Vipi-language-source-qualification/1'})
    with urllib.request.urlopen(request, timeout=90) as response, path.open('xb') as output:
        headers = {k: response.headers.get(k) for k in ('Content-Length', 'ETag', 'Last-Modified')}
        count = 0
        while block := response.read(1048576):
            count += len(block)
            assert count <= maximum
            output.write(block)
    assert expected is None or count == expected
    return dict(url=url, file=path.name, bytes=count, sha256=sha(path), headers=headers)


def main(args):
    args.output.mkdir(parents=True, exist_ok=False)
    sources = []
    for name in ('README.md', 'NOTICE.md', 'LICENSE.txt', 'THIRD-PARTY.md'):
        sources.append(fetch('https://raw.githubusercontent.com/alexa/massive/' + COMMIT + '/' + name,
                             args.output / name, 2097152))
    assert URL in (args.output / 'README.md').read_text()
    path = args.output / 'amazon-massive-dataset-1.1.tar.gz'
    sources.append(fetch(URL, path, EXPECTED_BYTES, EXPECTED_BYTES))
    locales, members, notices = {}, [], []
    with tarfile.open(path, 'r:gz') as archive:
        for member in archive:
            members.append(dict(name=member.name, bytes=member.size, regular=member.isfile()))
            if not member.isfile():
                continue
            if Path(member.name).name.upper() in {'LICENSE', 'LICENSE.TXT', 'NOTICE', 'NOTICE.MD'}:
                assert member.size < 2097152
                data = archive.extractfile(member).read()
                target = args.output / ('distribution-' + Path(member.name).name)
                target.write_bytes(data)
                notices.append(dict(member=member.name, file=target.name, sha256=sha(target)))
            if not member.name.endswith('.jsonl'):
                continue
            locale = Path(member.name).stem
            partitions, intents, methods, judgments = Counter(), Counter(), Counter(), Counter()
            identities = set()
            for line in archive.extractfile(member):
                row = json.loads(line)
                assert row['locale'] == locale and row['partition'] in {'train', 'dev', 'test'}
                assert row['id'] not in identities
                identities.add(row['id'])
                partitions[row['partition']] += 1
                # Only aggregate training annotations. Reserved text is never
                # printed, copied into authoring records or used for selection.
                if row['partition'] == 'train':
                    intents[row['intent']] += 1
                    methods.update(slot['method'] for slot in row.get('slot_method', []))
                    judgments.update(str(j.get('language_identification')) for j in row.get('judgments', []))
            locales[locale] = dict(rows=len(identities), partitions=dict(partitions), training_intents=dict(intents),
                                   training_slot_methods=dict(methods), training_judgment_languages=dict(judgments))
    assert notices and len(locales) == 52 and 'sw-KE' in locales
    result = dict(schema='vipi-massive-source-inventory-1', complete=True, version='1.1',
                  repository_commit=COMMIT, sources=sources, archive_members=members, locales=locales,
                  archive_sha256=sha(path), distribution_notices=notices,
                  source_page='https://github.com/alexa/massive',
                  data_license='CC-BY-4.0; retain distribution license and upstream notices',
                  record_model='English SLURP utterances localized into other languages; not independent peer-to-peer translations',
                  authoring_imported=False, runtime_promoted=False, independent_semantic_acceptance=False,
                  inspected_public_example=dict(original_id='0', locale='de-DE', source='official README',
                      future_exclusion='all locales with original ID 0 must be excluded from untouched acceptance'),
                  compiler_sha256=sha(Path(__file__)))
    (args.output / 'receipt.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(complete=True, locales=len(locales), rows=sum(v['rows'] for v in locales.values()),
                          swahili=locales['sw-KE']['partitions'], archive_bytes=path.stat().st_size,
                          authoring_imported=False)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args())
