#!/usr/bin/env python3
"""Rank pinned AfriSenti TRAINING vocabulary for authoring, never promotion.

Only the original project's training TSV is accepted. Social handles, links and
numeric fragments cannot become lexical priorities. Every native dictionary
analysis remains visible; frequency never chooses a sense or approves a mapping.
"""
import argparse
from collections import Counter, defaultdict
import csv
import io
import json
from pathlib import Path
import re
import sqlite3

from build_wiktextract import canonical, digest_file
from prioritize_swahili_authoring import EVIDENCE_SHA, occurrences

TRAINING_SHA = '1f06cb668d1c115a844704b5ffaec3e6168eabf1bd15657e3faf99a42e682152'
REVISION = '5aec3cfcf87b59f885e98641f72e52182776429d'
EXCLUDED = re.compile(r'https?://\S+|www\.\S+|[@#][\w]+|\S*\d\S*', re.IGNORECASE)


def training_rows(text):
    reader = csv.DictReader(io.StringIO(text), delimiter='\t')
    if reader.fieldnames != ['ID', 'tweet', 'label']:
        raise ValueError('Expected original AfriSenti training columns')
    seen = set()
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise ValueError('Malformed training row')
        if not row['ID'] or row['ID'] in seen or not row['tweet'].strip():
            raise ValueError('Empty text or missing/duplicate training identifier')
        seen.add(row['ID'])
        yield row['ID'], row['tweet']


def observed_windows(text):
    # A non-space barrier prevents an n-gram spanning removed material.
    return occurrences(EXCLUDED.sub(' | ', text))


def build(training, evidence, output, limit):
    if digest_file(training) != TRAINING_SHA or digest_file(evidence) != EVIDENCE_SHA:
        raise ValueError('Pinned training text and native dictionary required')
    if output.exists():
        raise ValueError('Use a fresh output revision')
    rows = list(training_rows(training.read_text()))
    if len(rows) != 1810:
        raise ValueError('Unexpected original training split')
    counts, ids = Counter(), defaultdict(list)
    for identifier, text in rows:
        windows = list(observed_windows(text))
        counts.update(windows)
        for surface in set(windows):
            ids[surface].append(identifier)
    candidates = []
    db = sqlite3.connect(evidence.resolve().as_uri()+'?mode=ro', uri=True)
    try:
        db.row_factory = sqlite3.Row
        for surface in sorted(counts):
            forms = [dict(r) for r in db.execute(
                'SELECT headword,form,tags,source_line FROM native_forms WHERE form=?', (surface,))]
            senses = []
            for head in sorted({surface, *(r['headword'] for r in forms)}):
                senses.extend(dict(r) for r in db.execute('SELECT * FROM native_senses WHERE headword=?', (head,)))
            if not senses:
                continue
            for item in senses:
                item['glosses'] = json.loads(item['glosses'])
                item['tags'] = json.loads(item['tags'])
            for item in forms:
                item['tags'] = json.loads(item['tags'])
            candidates.append({'surface': surface, 'occurrences': counts[surface],
                'training_turns': len(ids[surface]), 'training_presence_fraction': len(ids[surface])/len(rows),
                'training_ids': ids[surface][:3], 'native_senses': senses, 'recorded_forms': forms,
                'status': 'needs_context_and_pair_review', 'runtime_approved': False})
    finally:
        db.close()
    candidates.sort(key=lambda row: (-row['training_turns'], -row['occurrences'], row['surface']))
    output.mkdir(parents=True)
    queue = output/'authoring-queue.jsonl'
    queue.write_text(''.join(canonical(row)+'\n' for row in candidates[:limit]))
    receipt = {'schema': 'vipi-social-swahili-authoring-priority-1',
        'compiler_sha256': digest_file(Path(__file__)), 'training_sha256': TRAINING_SHA,
        'dictionary_sha256': EVIDENCE_SHA, 'upstream_revision': REVISION,
        'member_read': 'SubtaskA/train/sw_train.tsv', 'training_rows': len(rows),
        'observed_word_windows': len(counts), 'windows_with_dictionary_evidence': len(candidates),
        'queue_items': min(len(candidates), limit), 'queue_sha256': digest_file(queue),
        'runtime_promotion': False, 'release_ready': False,
        'licenses': {'training': 'CC-BY-4.0 per original repository', 'dictionary': 'CC-BY-SA-4.0'},
        'limits': ['Public sentiment-labelled social posts, not representative private conversations.',
            'No validation/test text is read. Handles, hashtags, links and numeric fragments excluded.',
            'Every linked native analysis is retained; frequency is neither a sense decision nor translation approval.',
            'The mirror has conflicting license metadata; the pinned original README is retained with acquisition.']}
    (output/'receipt.json').write_text(canonical(receipt)+'\n')
    (output/'ATTRIBUTION.txt').write_text(
        'AfriSenti authors: https://github.com/afrisenti-semeval/afrisent-semeval-2023\n'
        'Revision '+REVISION+'; original project README specifies CC BY 4.0.\n'
        'Changes: training-only vocabulary counts, exclusions and native dictionary join.\n'
        'Wiktionary contributors; extraction by Tatu Ylonen/wiktextract via Kaikki.org.\n'
        'CC BY-SA 4.0; exact entry URLs, tags, glosses and source lines retained.\n'
        'Research/authoring queue only; no app pack or automatically accepted mapping.\n')
    print(canonical(receipt))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--training', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=400)
    args = parser.parse_args()
    if not 1 <= args.limit <= 5000:
        parser.error('Queue limit must be between 1 and 5000')
    build(args.training, args.evidence, args.output, args.limit)
