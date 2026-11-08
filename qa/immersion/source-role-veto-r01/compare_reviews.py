#!/usr/bin/env python3
"""Join frozen reviews without changing judgments or treating consensus as gold.
Writes corpus-bearing raw labels only to the private output directory.
"""
import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = Path('/home/ai/Development/investigations/vipi-source-role-veto-20261108-r01/projection-r01')
INPUTS = {
    'author': (OUT / 'author-review-r01.json', '57985d67e63a52fa38c9d15aa8b8e7d362480a4505e0d49f3fc8f9c472ea80e2'),
    'root': (Path('/home/ai/Development/investigations/vipi-production-delivery-20261107/source-role-veto-root-independent-review-r01.json'), '961204fe1b75c6d01eb1c7b662fe68fc41b12b092804ba3ec92a34b2fb339859'),
    'apple': (Path('/home/ai/Development/investigations/vipi-apple-delivery-20261107-r01/source-role-veto-r01/apple-independent-review-r01.json'), 'a0115f13a634342a4ec5e5ad7f701852cbf2b6d93fd1e16d60ac338e6aa67765'),
}
PACKET_SHA = 'daef98710599c6465a2b82938191d20c069ab6a1183c55582b320f17bf56032f'
ARMS = ['original', 'eligible_links', 'apple_disagreement_veto', 'apple_role_required', 'opennlp_disagreement_veto', 'opennlp_role_required']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(u, reviewer):
    meaning = {'material': 'material_error'}.get(u['meaning'], u['meaning'])
    if reviewer == 'author':
        form = {'compatible_mixed_vocabulary': 'compatible', 'minor_form_or_register': 'minor', 'material_form_or_role': 'wrong', 'uncertain': 'uncertain'}[u['form']]
        complete = {'complete_for_intended_sense': 'complete', 'incomplete_or_added_meaning': 'incomplete', 'uncertain': 'uncertain'}[u['complete_unit']]
        entity = 'changed_unverified' if u['entity_idiom_identifier_error'] else 'not_flagged'
        role = None  # Original author form combines role and form, not separately recoverable.
    else:
        form = {'compatible_for_mixed_vocabulary': 'compatible', 'minor': 'minor', 'wrong': 'wrong', 'uncertain': 'uncertain'}[u['target_form']]
        complete = 'complete' if u['unit_completeness'] == 'complete' else 'incomplete'
        entity = 'not_flagged' if u['entity_identifier'] == 'not_applicable' else u['entity_identifier']
        role = u['lexical_role']
    defect = meaning == 'material_error' or form == 'wrong' or role == 'wrong' or complete == 'incomplete' or entity != 'not_flagged'
    uncertain = 'uncertain' in (meaning, form, role, complete)
    return {'meaning': meaning, 'form_or_role': form, 'separate_role': role, 'completeness': complete, 'entity_or_idiom_flag': entity,
            'utility': u['utility'], 'defect': defect, 'uncertain': uncertain,
            'strict_pass': not defect and not uncertain and meaning == 'correct' and form == 'compatible',
            'minor_tolerant_pass': not defect and not uncertain}


def whole(units):
    if not units:
        return {'status': 'empty', 'selected': 0, 'strict_pass': False, 'minor_tolerant_pass': False, 'accepted_content_units': 0}
    defect = any(u['defect'] for u in units)
    uncertain = any(u['uncertain'] for u in units)
    return {'status': 'defect' if defect else 'unresolved' if uncertain else 'minor_or_correct', 'selected': len(units),
            'strict_pass': all(u['strict_pass'] for u in units), 'minor_tolerant_pass': all(u['minor_tolerant_pass'] for u in units),
            'accepted_content_units': sum(u['minor_tolerant_pass'] and u['utility'] == 'content' for u in units)}


def main():
    assert sha(OUT / 'review-packet.json') == PACKET_SHA
    packet = json.loads((OUT / 'review-packet.json').read_text())
    reviews = {}
    for who, (path, expected) in INPUTS.items():
        assert sha(path) == expected, who
        d = json.loads(path.read_text())
        assert d['packet_sha256'] == PACKET_SHA
        reviews[who] = {c['review_id']: c for c in d['cases']}
        assert len(reviews[who]) == 32
    joined, disagreements = [], []
    for c in packet['cases']:
        rid = c['review_id']
        record = {'review_id': rid, 'pair': c['pair'], 'known': c['known'], 'units': [], 'whole': {}}
        for who in INPUTS:
            assert reviews[who][rid]['source_id'] == c['source_id']
            assert len(reviews[who][rid]['units']) == len(c['review_union'])
        for i, scope in enumerate(c['review_union']):
            raw, norm = {}, {}
            for who in INPUTS:
                u = reviews[who][rid]['units'][i]
                assert u['focus_utf16'] == scope['focus_utf16'] and u['target'] == scope['target']
                assert set(u['arms']) == set(scope['arms'])
                raw[who], norm[who] = u, normalized(u, who)
            axes = [axis for axis in ['meaning', 'form_or_role', 'completeness', 'entity_or_idiom_flag', 'utility', 'defect', 'uncertain', 'strict_pass', 'minor_tolerant_pass'] if len({n[axis] for n in norm.values()}) > 1]
            if axes:
                disagreements.append({'review_id': rid, 'union_index': i, 'axes': axes,
                                      'normalized': norm})
            record['units'].append({'union_index': i, 'scope': scope, 'raw_labels': raw, 'normalized': norm})
        for who in INPUTS:
            record['whole'][who] = {a: whole([u['normalized'][who] for u in record['units'] if a in u['scope']['arms']]) for a in ARMS}
        joined.append(record)
    assert len(joined) == 32 and sum(len(c['units']) for c in joined) == 77
    summary, transitions = {}, {}
    for who in INPUTS:
        summary[who], transitions[who] = {}, {}
        for pair in ['all', 'en-es', 'en-sw']:
            cases = [c for c in joined if pair == 'all' or c['pair'] == pair]
            summary[who][pair], transitions[who][pair] = {}, {}
            for arm in ARMS:
                w = [c['whole'][who][arm] for c in cases]
                counts = Counter(x['status'] for x in w)
                summary[who][pair][arm] = {'denominator': len(cases), 'status_counts': dict(counts), 'strict_whole_pass': sum(x['strict_pass'] for x in w), 'minor_tolerant_whole_pass': sum(x['minor_tolerant_pass'] for x in w), 'selected_units': sum(x['selected'] for x in w), 'accepted_content_units': sum(x['accepted_content_units'] for x in w)}
            for base, arm in [('original', 'eligible_links')] + [('eligible_links', a) for a in ARMS[2:]]:
                counts, ids = Counter(), {'gained_nonempty_pass': [], 'lost_nonempty_pass': [], 'introduced_defect': [], 'removed_defect': [], 'emptied': []}
                for c in cases:
                    bw, aw = c['whole'][who][base], c['whole'][who][arm]
                    for key, flag in [('gained_nonempty_pass', not bw['minor_tolerant_pass'] and aw['minor_tolerant_pass']), ('lost_nonempty_pass', bw['minor_tolerant_pass'] and not aw['minor_tolerant_pass']), ('introduced_defect', bw['status'] != 'defect' and aw['status'] == 'defect'), ('removed_defect', bw['status'] == 'defect' and aw['status'] != 'defect'), ('emptied', bw['selected'] > 0 and aw['selected'] == 0)]:
                        if flag:
                            counts[key] += 1
                            ids[key].append(c['review_id'])
                    for direction, a, b in [('removed', base, arm), ('introduced', arm, base)]:
                        for u in c['units']:
                            if a in u['scope']['arms'] and b not in u['scope']['arms']:
                                n = u['normalized'][who]
                                counts[direction + '_units'] += 1
                                counts[direction + '_defect_units'] += int(n['defect'])
                                counts[direction + '_uncertain_units'] += int(n['uncertain'])
                                counts[direction + '_minor_tolerant_units'] += int(n['minor_tolerant_pass'])
                transitions[who][pair][base + '->' + arm] = {'counts': dict(counts), 'case_ids': ids}
    private = OUT / 'joined-reviews-r01.json'
    assert not private.exists(), 'Do not overwrite a retained join.'
    private.write_text(json.dumps({'packet_sha256': PACKET_SHA, 'cases': joined}, ensure_ascii=False, indent=2) + '\n')
    receipt = {'schema': 1, 'production': False, 'script_sha256': sha(Path(__file__)), 'packet_sha256': PACKET_SHA,
               'reviews': {who: {'path': str(path), 'sha256': expected} for who, (path, expected) in INPUTS.items()},
               'joined_private': {'path': str(private), 'sha256': sha(private)}, 'denominators': {'cases': 32, 'union_units': 77, 'arms_per_case': 6},
               'normalization': 'Raw labels preserved privately. Material/material_error unified. Author combined form/role cannot be separated; separate_role=null. Wrong role, wrong form, incomplete unit, entity/idiom flag or material meaning is a defect. Any uncertain axis blocks pass. Strict excludes minor; minor-tolerant permits minor. Empty outputs never pass. These are rubric-normalized judgments, not gold. Author completeness often bundles wrong role; see raw notes.',
               'summary': summary, 'transitions': transitions, 'disagreements': disagreements,
               'raw_corpus_metrics': json.loads((OUT / 'metrics.json').read_text()),
               'limits': ['Changed-case/reused TRAIN diagnostic sample, not representative accuracy.', 'No majority gold. Original review files and earlier 96 judgments unchanged.', 'Corpus metrics are catalog classifications, not reviewed semantic coverage.', 'Noun/verb/adjective/adverb mapping only; closed classes, PROPN and composites unassessed.', 'No projection rerun or activation.']}
    dest = HERE / 'comparison-receipt.json'
    assert not dest.exists()
    dest.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'receipt': str(dest), 'sha256': sha(dest), 'disagreement_units': len(disagreements)}))


if __name__ == '__main__':
    main()
