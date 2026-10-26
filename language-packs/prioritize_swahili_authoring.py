#!/usr/bin/env python3
"""Build an evidence queue from public TRAINING turns, never approved mappings.

The only conversation member read is swa_translate_mwoz_training.xlsx.
Frequency prioritizes author work; it cannot establish a word's intended sense,
translation quality, runtime coverage or a learner's proficiency.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import sqlite3
import sys
import unicodedata
import zipfile

from build_wiktextract import canonical, digest_file
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'qa/immersion'))
from prepare_afriwoz_probe import ARCHIVE_SHA, rows

EVIDENCE_SHA = '46395c3ed74c76ec55e2006c9ea665b4e2a11384877dd3fb264d8a32297cdbae'
TOKEN = re.compile(r"[^\W\d_]+(?:[’'-][^\W\d_]+)*", re.UNICODE)


def normalized(text):
    return unicodedata.normalize('NFC', text).casefold()


def occurrences(text):
    tokens = list(TOKEN.finditer(text))
    for start, token in enumerate(tokens):
        for end in range(start, min(start + 4, len(tokens))):
            if end > start and not text[tokens[end-1].end():tokens[end].start()].isspace():
                break
            yield ' '.join(normalized(t.group()) for t in tokens[start:end+1])


def build(archive, evidence, output, limit):
    if digest_file(archive) != ARCHIVE_SHA:
        raise ValueError('Pinned AfriWOZ archive required')
    if digest_file(evidence) != EVIDENCE_SHA:
        raise ValueError('Pinned complete Swahili dictionary evidence required')
    if output.exists():
        raise ValueError('Use a new output revision; do not overwrite evidence')
    with zipfile.ZipFile(archive) as source:
        license_text = source.read('AfriWOZ_data_statement.txt').decode()
        if 'CC-BY 4.0' not in license_text:
            raise ValueError('Missing corpus attribution')
        training = list(rows(source, 'training'))
    if len(training) != 999:
        raise ValueError('Unexpected training split')
    counts, turns = Counter(), defaultdict(list)
    by_row = {row: text for row, _, text in training}
    for row, _, text in training:
        values = list(occurrences(text))
        counts.update(values)
        for value in set(values):
            turns[value].append(row)

    candidates = []
    with sqlite3.connect(evidence.resolve().as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        for surface in sorted(counts):
            # Upstream Swahili entries/forms, not an inferred stemmer or pivot.
            forms = [dict(r) for r in db.execute(
                'SELECT headword,form,tags,source_line FROM native_forms WHERE form=?', (surface,))]
            heads = {surface, *(r['headword'] for r in forms)}
            senses = []
            for head in sorted(heads):
                senses.extend(dict(r) for r in db.execute(
                    'SELECT * FROM native_senses WHERE headword=?', (head,)))
            if not senses:
                continue
            for row in senses:
                row['glosses'] = json.loads(row['glosses'])
                row['tags'] = json.loads(row['tags'])
            for row in forms:
                row['tags'] = json.loads(row['tags'])
            candidates.append({
                'surface': surface, 'occurrences': counts[surface],
                'training_turns': len(turns[surface]),
                'training_presence_fraction': len(turns[surface]) / len(training),
                'training_examples': [{'row': row, 'text': by_row[row]} for row in turns[surface][:2]],
                'native_senses': senses, 'recorded_forms': forms,
                'status': 'needs_context_and_pair_review', 'runtime_approved': False})
    candidates.sort(key=lambda row: (-row['training_turns'], -row['occurrences'], row['surface']))
    selected = candidates[:limit]
    output.mkdir(parents=True)
    path = output / 'authoring-queue.jsonl'
    path.write_text(''.join(canonical(row) + '\n' for row in selected))
    receipt = {
        'schema': 'vipi-swahili-authoring-priority-1',
        'compiler_sha256': digest_file(Path(__file__)),
        'archive_sha256': ARCHIVE_SHA, 'dictionary_sha256': EVIDENCE_SHA,
        'conversation_member_read': 'swa_translate_mwoz_training.xlsx',
        'training_turns': len(training), 'observed_word_windows': len(counts),
        'windows_with_dictionary_evidence': len(candidates), 'queue_items': len(selected),
        'queue_sha256': digest_file(path), 'release_ready': False, 'runtime_promotion': False,
        'licenses': {'conversation': 'CC-BY-4.0', 'dictionary': 'CC-BY-SA-4.0'},
        'limits': [
            'Frequency is not meaning, mapping approval or runtime coverage.',
            'This booking-domain corpus is not representative of all personal chats.',
            'Forms retain every linked native analysis; no sense is selected automatically.',
            'Author pairs, contextual scope, readings and counterexamples before ledger review.',
            'Neither held-out nor validation conversation text is read by this command.']}
    (output / 'receipt.json').write_text(canonical(receipt) + '\n')
    (output / 'ATTRIBUTION.txt').write_text(
        'AfriWOZ authors / Masakhane: https://github.com/masakhane-io/chatbots-african-languages\n'
        'Pinned commit 3961ae0c514bb019598a9b042da21b3a586bc090; corpus CC BY 4.0.\n'
        'Training split only; changes: normalized frequency windows and sample selection.\n'
        'Wiktionary contributors; extraction by Tatu Ylonen/wiktextract via Kaikki.org.\n'
        'Dictionary CC BY-SA 4.0; exact entry URLs, glosses, tags and source lines retained.\n'
        'Changes: join observed training vocabulary to native dictionary evidence.\n'
        'This research/authoring queue is not a distributed language pack.\n')
    print(canonical(receipt))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--evidence', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--limit', type=int, default=400)
    args = p.parse_args()
    if not 1 <= args.limit <= 5000:
        p.error('Queue limit must be between 1 and 5000')
    build(args.archive, args.evidence, args.output, args.limit)
