#!/usr/bin/env python3
"""Freeze the published Swahili test split before native catalog evaluation.

Research inputs only. No translations, mappings or runtime data are generated.
Exact normalized duplicates of development turns and repeated test turns are
excluded. This cannot establish participant separation or linguistic accuracy.
"""
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile
from conversation_corpus import key, sha_file, write_json

ARCHIVE_SHA = '887182c8cd7e5f743b52d43534f744da638d3cf99675e739a65520bfbdbd3d48'
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
TARGETS = ['en', 'es', 'fr', 'de', 'it', 'pt', 'ar', 'zh', 'ja', 'ko']


def rows(archive, split):
    name = 'swa_translate_mwoz_' + split + '.xlsx'
    with zipfile.ZipFile(io.BytesIO(archive.read(name))) as workbook:
        shared = [''.join(t.text or '' for t in item.findall('.//s:t', NS))
                  for item in ET.fromstring(workbook.read('xl/sharedStrings.xml'))]
        sheet = ET.fromstring(workbook.read('xl/worksheets/sheet1.xml'))
        for row in sheet.findall('.//s:sheetData/s:row', NS):
            cells = {}
            for cell in row.findall('s:c', NS):
                column = ''.join(c for c in cell.attrib['r'] if c.isalpha())
                value = cell.find('s:v', NS)
                if value is not None:
                    cells[column] = shared[int(value.text)] if cell.get('t') == 's' else value.text
                elif cell.get('t') == 'inlineStr':
                    cells[column] = ''.join(t.text or '' for t in cell.findall('.//s:t', NS))
            if row.attrib['r'] == '1':
                if cells.get('B') != 'Conversation': raise ValueError('Changed workbook header')
                continue
            if cells.get('B', '').strip():
                yield int(row.attrib['r']), cells.get('A', ''), cells['B']


def main(args):
    if sha_file(args.archive) != ARCHIVE_SHA: raise ValueError('Unpinned archive')
    args.output.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(args.archive) as archive:
        license_text = archive.read('AfriWOZ_data_statement.txt').decode()
        if 'CC-BY 4.0' not in license_text: raise ValueError('Missing dataset licence')
        training = list(rows(archive, 'training')); validation = list(rows(archive, 'validation'))
        testing = list(rows(archive, 'testset'))
    development = {key(text) for _, _, text in training + validation}
    seen = set(); cases = []; counts = Counter()
    for row, episode, text in testing:
        normalized = key(text)
        if normalized in development: counts['development_duplicate'] += 1; continue
        if normalized in seen: counts['test_duplicate'] += 1; continue
        seen.add(normalized)
        if len(text.encode('utf-16-le')) // 2 > 16_384: counts['too_long'] += 1; continue
        identifier = hashlib.sha256(('afriwoz-sw-test-v1:' + str(row) + ':' + text).encode()).hexdigest()
        cases.append({'id': 'afriwoz-' + identifier[:24], 'row': row, 'episode_marker': episode,
                      'text': {'sw': text}})
    corpus = {'schema': 'vipi-afriwoz-probe-1', 'source': 'sw', 'targets': TARGETS,
        'cases': cases, 'partition': 'published-test-exact-development-duplicates-purged',
        'source_only': True, 'translation_gold': False,
        'attribution': {'dataset': 'AfriWOZ', 'authors': 'AfriWOZ authors and contributors',
            'url': 'https://github.com/masakhane-io/chatbots-african-languages',
            'paper': 'https://arxiv.org/abs/2204.08083', 'license': 'CC-BY 4.0',
            'commit': '3961ae0c514bb019598a9b042da21b3a586bc090'}}
    write_json(args.output/'corpus.json', corpus)
    (args.output/'DATASET_LICENSE.txt').write_text(license_text)
    receipt = {'archive_sha256': ARCHIVE_SHA, 'selector_sha256': sha_file(Path(__file__)),
        'corpus_sha256': sha_file(args.output/'corpus.json'),
        'observed_nonempty_turns': {'training': len(training), 'validation': len(validation), 'test': len(testing)},
        'excluded': dict(counts), 'selected': len(cases), 'directed_cases': len(cases)*len(TARGETS),
        'selection': 'All eligible published Swahili test turns, in workbook order; no model or catalog consultation',
        'independent_linguistic_acceptance': False, 'runtime_promotion': False,
        'limits': ['Translated task-oriented dialogue; not representative of private friend conversations.',
                   'Workbook contains no aligned English reference column; translation quality needs separate review.',
                   'Exact turn deduplication does not establish participant or conversation independence.']}
    write_json(args.output/'receipt.json', receipt)
    print(json.dumps(receipt))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args())
