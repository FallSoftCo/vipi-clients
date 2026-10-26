#!/usr/bin/env python3
"""Reserve a bounded spontaneous-speech probe, without consulting app mappings.

Only public text samples are used. Speaker labels and timestamps are metadata;
the utterance itself is retained verbatim. This is not a private-chat corpus or
a translation gold set, and turns can contain English/Sheng code switching.
"""
import argparse
from collections import Counter
import csv
import hashlib
import re
from pathlib import Path
from conversation_corpus import key, sha_file, write_json

METADATA_SHA = '30ccb61a8e23fbbb493db6b31205975553138bbe0c460db9b246484526b7be7b'
README_SHA = '544e9247682650028250f7639580a275c556b7f30f68e639b2635a4e37f0e10c'
REVISION = 'effd8511e0db4b12ee753536aa513d62cb01d8bd'
TARGETS = ['en', 'es', 'fr', 'de', 'it', 'pt', 'ar', 'zh', 'ja', 'ko']
TURN = re.compile(r'(?P<speaker>[^\[\]:\n]+) \[(?P<start>\d{2}:\d{2}:\d{2}\.\d{3}) - (?P<end>\d{2}:\d{2}:\d{2}\.\d{3})\]: ?(?P<text>.*)')


def milliseconds(value):
    hours, minutes, seconds = value.split(':')
    if not 0 <= int(minutes) < 60 or not 0 <= float(seconds) < 60:
        raise ValueError('Invalid timestamp')
    return int(hours)*3_600_000 + int(minutes)*60_000 + round(float(seconds)*1000)


def parse_transcript(text):
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip(): continue
        match = TURN.fullmatch(line)
        if not match: raise ValueError('Unrecognized transcript structure at line '+str(number))
        row = match.groupdict()
        if milliseconds(row['end']) < milliseconds(row['start']): raise ValueError('Reversed interval')
        yield dict(row, line=number)


def select(rows, per_conversation=20):
    counts = Counter(); seen = set(); files = set(); selected = []
    for row in sorted(rows, key=lambda r: r['file_name']):
        name = row['file_name']
        if not name or name in files: raise ValueError('Missing or repeated conversation')
        files.add(name); eligible = []
        for turn in parse_transcript(row['transcript']):
            counts['parsed_turns'] += 1
            text = turn['text']
            if not any(c.isalpha() for c in re.sub(r'\[[^\]]*\]', '', text)):
                counts['nonlexical_turns'] += 1; continue
            if len(text.encode('utf-16-le'))//2 > 16_384:
                counts['oversize_turns'] += 1; continue
            normalized = key(text)
            if normalized in seen: counts['exact_normalized_duplicates'] += 1; continue
            seen.add(normalized)
            identity = hashlib.sha256(('liva-sw-public-v1:'+name+':'+str(turn['line'])+':'+text).encode()).hexdigest()
            eligible.append({'id':'liva-sw-'+identity[:24], 'conversation':name,
                'speaker':turn['speaker'], 'start':turn['start'], 'end':turn['end'], 'line':turn['line'],
                'text':{'sw':text}, 'language_label':'publisher-level Swahili; code-switching not adjudicated',
                'selection_hash':identity})
        ranked = sorted(eligible, key=lambda r:r['selection_hash'])
        counts['eligible_unique_turns'] += len(ranked)
        selected.extend(ranked[:per_conversation])
    return selected, dict(counts, conversations=len(files), selected=len(selected))


def main(args):
    metadata = args.source/'data/metadata.csv'; readme = args.source/'README.md'
    if sha_file(metadata) != METADATA_SHA or sha_file(readme) != README_SHA: raise ValueError('Unpinned source')
    with metadata.open(newline='') as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ['file_name','transcript']: raise ValueError('Changed metadata columns')
        rows = list(reader)
    if len(rows) != 10: raise ValueError('Changed public sample count')
    cases, counts = select(rows)
    args.output.mkdir(parents=True, exist_ok=False)
    limits = ['Ten publisher-selected public speech samples, not a representative private-chat corpus.',
        'Utterances can contain English/Sheng and depend on adjacent spoken context; no per-turn language gold label.',
        'Speaker turns from the same conversation are dependent. Public samples may overlap model training.',
        'Automatic app behavior and explicit Swahili override are reported separately; forced translation is diagnostic.',
        'Availability is not semantic accuracy, transliteration acceptance or learning effectiveness.']
    corpus = {'schema':'vipi-liva-swahili-probe-1', 'source':'sw', 'targets':TARGETS, 'cases':cases,
        'partition':'reserved-public-samples-no-app-or-authoring-consultation', 'source_only':True,
        'translation_gold':False, 'limits':limits,
        'attribution':{'dataset':'Liva Swahili ASR public samples', 'authors':'Liva AI and contributors',
            'url':'https://huggingface.co/datasets/liva-ai/swahili-asr', 'license':'CC-BY-4.0', 'revision':REVISION}}
    write_json(args.output/'corpus.json', corpus)
    receipt = {'schema':'vipi-liva-probe-selection-1', 'metadata_sha256':METADATA_SHA, 'readme_sha256':README_SHA,
        'selector_sha256':sha_file(Path(__file__)), 'corpus_sha256':sha_file(args.output/'corpus.json'),
        'selection':'First 20 eligible unique turns per public file in SHA-256 order; no catalog/model consultation',
        'counts':counts, 'directed_cases':len(cases)*len(TARGETS), 'limits':limits,
        'independent_linguistic_acceptance':False, 'runtime_promotion':False}
    write_json(args.output/'receipt.json', receipt)
    (args.output/'ATTRIBUTION.txt').write_text('Liva AI and contributors, Swahili ASR public samples.\n'
        'https://huggingface.co/datasets/liva-ai/swahili-asr/tree/'+REVISION+'\n'
        'Publisher license: CC-BY-4.0. https://creativecommons.org/licenses/by/4.0/\n'
        'Changes: transcript metadata separated; deterministic bounded turn selection and exact normalized deduplication.\n')
    print(receipt)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    main(parser.parse_args())
