#!/usr/bin/env python3
"""Pin original FLORES-200 for evaluation only; never a pack-mining source."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import urllib.request

COMMIT = 'a6c830c6e1051fb4ac1a44b32358f00463f332bd'
URL = 'https://dl.fbaipublicfiles.com/nllb/flores200_dataset.tar.gz'
LANGUAGES = dict(en='eng_Latn', es='spa_Latn', fr='fra_Latn', de='deu_Latn',
                 it='ita_Latn', pt='por_Latn', ar='arb_Arab', zh='zho_Hans',
                 ja='jpn_Jpan', ko='kor_Hang', sw='swh_Latn')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(url, destination, maximum):
    request = urllib.request.Request(url, headers={'User-Agent': 'Vipi-language-evaluation/1'})
    temporary = destination.with_suffix(destination.suffix + '.partial')
    with urllib.request.urlopen(request, timeout=60) as response, temporary.open('xb') as stream:
        total = 0
        while block := response.read(65536):
            total += len(block)
            assert total <= maximum
            stream.write(block)
        length = response.headers.get('Content-Length')
        assert not length or total == int(length)
        headers = {k: response.headers.get(k) for k in ('Content-Length', 'Last-Modified', 'ETag')}
        resolved = response.url
    temporary.rename(destination)
    return dict(url=url, resolved_url=resolved, file=destination.name, bytes=total, sha256=sha(destination), headers=headers)


def main(args):
    args.output.mkdir(parents=True, exist_ok=False)
    files = []
    for name, source in [('README.md', 'flores200/README.md'), ('dataset-LICENSE_CC-BY-SA', 'LICENSE_CC-BY-SA')]:
        files.append(download('https://raw.githubusercontent.com/facebookresearch/flores/' + COMMIT + '/' + source,
                              args.output / name, 262144))
    archive_path = args.output / 'flores200_dataset.tar.gz'
    files.append(download(URL, archive_path, 40 * 1024**2))
    members, selected = [], []
    with tarfile.open(archive_path, 'r:gz') as archive:
        inventory = archive.getmembers()
        for item in inventory:
            members.append(dict(name=item.name, bytes=item.size, regular=item.isfile()))
        for language, code in LANGUAGES.items():
            for partition, expected in [('dev', 997), ('devtest', 1012)]:
                match = [m for m in inventory if m.isfile() and m.name.endswith('/' + code + '.' + partition)]
                assert len(match) == 1 and match[0].size < 2 * 1024**2
                data = archive.extractfile(match[0]).read()
                lines = data.decode('utf-8').splitlines()
                assert len(lines) == expected and all(line.strip() for line in lines)
                path = args.output / (language + '.' + partition)
                path.write_bytes(data)
                selected.append(dict(language=language, variety=code, partition=partition, lines=len(lines),
                                     file=path.name, member=match[0].name, bytes=len(data), sha256=sha(path)))
        for index, item in enumerate(m for m in inventory if m.isfile() and any(x in Path(m.name).name.lower() for x in ('license', 'readme', 'metadata'))):
            assert item.size < 2 * 1024**2
            path = args.output / ('distribution-' + str(index) + '-' + Path(item.name).name)
            path.write_bytes(archive.extractfile(item).read())
            selected.append(dict(file=path.name, member=item.name, bytes=item.size, sha256=sha(path), metadata=True))
    (args.output / 'archive-members.json').write_text(json.dumps(members, indent=2) + '\n')
    receipt = dict(schema='vipi-flores-evaluation-acquisition-1', complete=True, evaluation_only=True,
                   version='original FLORES-200 (2022), not current FLORES+', repository_commit=COMMIT,
                   license_claim='CC-BY-SA-4.0; retained publisher license and README must accompany derived evaluation artifacts',
                   intended_use='diagnose selector availability with human reference translations; never mine vocabulary packs from this benchmark',
                   inspected_sentence_text=False, files=files, selected_members=selected,
                   compiler_sha256=sha(Path(__file__)), independent_accuracy_acceptance=False)
    (args.output / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(complete=True, evaluation_only=True, archive_bytes=archive_path.stat().st_size,
                         archive_sha256=sha(archive_path), languages=len(LANGUAGES), selected_members=len(selected))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args())
