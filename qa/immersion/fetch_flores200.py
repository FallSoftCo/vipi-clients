#!/usr/bin/env python3
"""Pin a fixed independent evaluation sample, before inspecting model outputs."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import urllib.request

URL = 'https://dl.fbaipublicfiles.com/nllb/flores200_dataset.tar.gz'
SHA256 = 'b8b0b76783024b85797e5cc75064eb83fc5288b41e9654dabc7be6ae944011f6'
CODES = {'en':'eng_Latn', 'es':'spa_Latn', 'fr':'fra_Latn', 'de':'deu_Latn',
         'it':'ita_Latn', 'pt':'por_Latn', 'ar':'arb_Arab', 'zh':'zho_Hans', 'ja':'jpn_Jpan', 'ko':'kor_Hang'}


def main(output):
    output.mkdir(parents=True, exist_ok=False)
    archive = output / 'flores200_dataset.tar.gz'
    digest = hashlib.sha256()
    size = 0
    with urllib.request.urlopen(URL, timeout=60) as response, archive.open('wb') as dest:
        final_url = response.url
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > 134_217_728:
                raise ValueError('Archive exceeds the explicit download bound')
            digest.update(chunk); dest.write(chunk)
    if digest.hexdigest() != SHA256:
        raise ValueError('Publisher archive no longer matches the reviewed download pin')
    data, files = {}, []
    with tarfile.open(archive, 'r:gz') as source:
        members = {member.name: member for member in source.getmembers()}
        for code, language in CODES.items():
            matches = [member for name,member in members.items() if name.endswith('/devtest/' + language + '.devtest')]
            if len(matches) != 1 or not matches[0].isfile() or matches[0].size > 2_097_152:
                raise ValueError('Missing or oversized language input: ' + language)
            raw = source.extractfile(matches[0]).read()
            lines = raw.decode('utf-8').splitlines()
            if len(lines) != 1012 or any(not line or len(line) > 16384 for line in lines):
                raise ValueError('Unexpected devtest alignment/length')
            data[code] = lines
            (output / (language + '.devtest')).write_bytes(raw)
            files.append({'language':code, 'path':matches[0].name, 'sha256':hashlib.sha256(raw).hexdigest(), 'bytes':len(raw)})
    indices = sorted(range(1012), key=lambda index: hashlib.sha256(f'vipi-independent-20261025:{index + 1}'.encode()).digest())[:32]
    attribution = {'name':'FLORES-200 — NLLB Team et al. (2022)',
                   'url':'https://github.com/facebookresearch/flores/blob/main/flores200/README.md',
                   'license':'CC-BY-SA-4.0', 'license_url':'https://creativecommons.org/licenses/by-sa/4.0/',
                   'archive_sha256':digest.hexdigest()}
    corpus = {'schema':1, 'version':'flores200-devtest-vipi-32-r1', 'languages':list(CODES), 'attribution':attribution,
              'evidence':'Independent reference translation sample; formal prose, not chat or a learning study. Sample selected by fixed ID hash before model output review.',
              'cases':[{'id':f'flores200_devtest_{i+1:04}', 'context':'Independent reference sentence',
                        'text':{code:data[code][i] for code in CODES}} for i in indices]}
    (output / 'corpus.json').write_text(json.dumps(corpus, ensure_ascii=False, indent=2)+'\n')
    receipt = {'requested_url':URL, 'download_url':final_url, 'archive_sha256':digest.hexdigest(), 'archive_bytes':size,
               'languages':files, 'selected_sentence_ids':[i+1 for i in indices], 'attribution':attribution,
               'selection_rule':'32 lowest SHA256(vipi-independent-20261025:<one-based-line>)',
               'current_flores_plus_access':'Gated; original publisher FLORES-200 public release used explicitly.'}
    (output / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'archive_bytes':size, 'sha256':digest.hexdigest(), 'languages':len(data), 'sentences_per_language':len(indices)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    main(parser.parse_args().output)
