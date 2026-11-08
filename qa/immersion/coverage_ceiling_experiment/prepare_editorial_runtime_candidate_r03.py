#!/usr/bin/env python3
"""Bind ordinary senses and source-role metadata without changing target faces.

Research candidate only. The compact source index is independent of whether a
word has an admitted target face. No output-selected target or new translation.
"""
import argparse
import collections
import copy
import hashlib
import json
import sqlite3
import unicodedata
from pathlib import Path
from evaluate_reviewed_words import WORD, u16


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def emit(p, data):
    assert not p.exists(), p
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--evidence-dir', type=Path, required=True)
    p.add_argument('--source-db', type=Path, required=True)
    a = p.parse_args()
    E = a.evidence_dir
    M = E / 'scaled-mechanism-cases-r01'
    Q = Path(__file__).resolve().parent
    inputs = {
        'candidate': M / 'editorial-content500-candidate-r01.json',
        'bindings': M / 'editorial-source-sense-binding-complete-r02.json',
        'inventory': E / 'scaled-content-inventory-r01/source-inventory.json',
        'train': E / 'bst-evaluation-source-r01/train.json',
        'source_db': a.source_db,
        'contrasts': Q / 'editorial-content-contrasts-r01.json',
        'builder': Path(__file__),
    }
    hashes = {k: sha(v) for k, v in inputs.items()}
    assert hashes['train'] == 'a5a9672c3e2e8a2f3d740cb0b61810ad46f3e3cd7bbe86b8d79962c6b34ad33c'
    old = json.loads(inputs['candidate'].read_text())
    binding = json.loads(inputs['bindings'].read_text())
    assert hashes['candidate'] == binding['original_candidate_sha256']
    bypair = {(r['source'], r['pos']): r for r in binding['rows']}
    inventory = json.loads(inputs['inventory'].read_text())
    # Preserve the independently reviewed508 noun-only admission proxy exactly.
    noun_only = sorted(r['source'] for r in inventory['rows']
                       if set(r['parts_of_speech']) == {'noun'}
                       and not r['mixed_content_function_or_name'] and r['content_lexemes'])
    train = json.loads(inputs['train'].read_text())
    texts = [text for c in train if c['context_dataset'] == 'convai2'
             for speaker, text in c['dialog'] if speaker == 0 and text.strip()]
    assert len(texts) == 9535
    words = {t.group().casefold().replace('’', "'") for text in texts
             for t in WORD.finditer(text)}
    words.update(r['source'] for r in inventory['rows'])
    for case in json.loads(inputs['contrasts'].read_text())['cases']:
        words.update(t.group().casefold().replace('’', "'") for t in WORD.finditer(case['text']))
    db = sqlite3.connect(a.source_db.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    db.execute('PRAGMA query_only=ON')
    db.execute('PRAGMA cache_size=-8192')
    metadata = dict(db.execute('SELECT key,value FROM metadata'))
    source_roles = {}
    rows = []
    for word in sorted(words):
        records = db.execute('SELECT s.lexeme,s.surface,s.start,s.end,s.mode,s.features,l.headword,l.pos,l.source_url '
                             'FROM surfaces s JOIN lexemes l ON l.id=s.lexeme WHERE s.normalized=?',
                             (unicodedata.normalize('NFC', word),)).fetchall()
        complete = [r for r in records if r[2] == 0 and r[3] == u16(r[1])
                    and unicodedata.normalize('NFC', r[1]).casefold() == word]
        if complete:
            source_roles[word] = sorted({r[7] for r in complete})
            rows.append({'source': word, 'complete_records': complete})
    db.close()
    role_proof = {
        'production': False, 'schema': 'vipi.editorial-source-roles.r03',
        'inputs': {k: {'path': str(inputs[k]), 'sha256': hashes[k]} for k in ['train', 'source_db', 'inventory', 'contrasts']},
        'source_metadata': metadata, 'requested_unique_sources': len(words),
        'sources_with_complete_native_forms': len(rows),
        'record_columns': ['lexeme', 'surface', 'start_utf16', 'end_utf16', 'mode', 'features', 'headword', 'pos', 'source_url'],
        'rows': rows,
        'limitations': ['Source role membership is not contextual POS or sense gold.',
                       'Compiled complete-form identity is inspected; native raw source ambiguity remains.',
                       'Exact TRAIN vocabulary and existing contrasts select metadata only, not new target faces.'],
    }
    proof_path = M / 'editorial-source-role-proof-r03.json'
    emit(proof_path, role_proof)
    entries = []
    withheld = []
    target_flags = collections.Counter()
    for entry in old['entries']:
        b = bypair[entry['source'], entry['pos']]
        if not b['chosen_ordinary_source_sense_ids']:
            withheld.append({'id': entry['id'], 'reason': 'no_qualified_intended_source_sense',
                             'source': entry['source'], 'language': entry['language']})
            continue
        e = copy.deepcopy(entry)
        e['evidence']['previous_source_selected_sense'] = e['evidence'].pop('source_selected_sense')
        e['evidence']['source_entry'] = b['source_entry_primary']
        e['evidence']['source_ordinary_senses'] = b['chosen_primary_records']
        e['evidence']['source_glosses'] = [json.loads(s[2]) for s in b['chosen_primary_records']]
        e['evidence']['source_complete_form_identity'] = b['source_complete_form_identity']
        e['evidence']['source_binding_sha256'] = hashes['bindings']
        e['evidence']['sense_evidence_ordering'] = 'Explicit ordinary source-sense IDs; no gloss-overlap winner. Target ordinary-fit and context remain separate.'
        target = e['evidence']['target']
        form = target.get('selected_form')
        flags = json.loads(form[-1]) if form else []
        e['target_form_evidence_warnings'] = [t for t in flags if t.startswith('error')]
        target_flags.update(e['target_form_evidence_warnings'])
        e['semantic_review_status'] = 'research_candidate_source_binding_reviewed_target_context_not_universally_approved'
        entries.append(e)
    candidate = copy.deepcopy(old)
    candidate.update(schema='vipi.editorial-runtime-candidate.r03', entries=entries,
                     parent_candidate_sha256=hashes['candidate'], source_binding_sha256=hashes['bindings'],
                     source_role_proof_sha256=sha(proof_path), source_roles=source_roles,
                     noun_only_sources=noun_only, withheld_source_senses=withheld,
                     preparation_inputs=hashes)
    candidate['summary'] = {'entries': len(entries), 'by_language': dict(collections.Counter(e['language'] for e in entries)),
                            'source_pos_pairs': len({(e['source'], e['pos']) for e in entries}),
                            'source_role_forms': len(source_roles), 'noun_only_forms': len(noun_only),
                            'withheld': len(withheld), 'target_form_evidence_warnings': dict(target_flags)}
    candidate['selection'] = 'Same target faces as frozenr01; explicit source bindings, source role metadata independent of target eligibility. No observed-output gate or new translation.'
    path = M / 'editorial-runtime-candidate-r03.json'
    emit(path, candidate)
    print(json.dumps({'path': str(path), 'sha256': sha(path), 'summary': candidate['summary'],
                      'source_proof_sha256': sha(proof_path)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
