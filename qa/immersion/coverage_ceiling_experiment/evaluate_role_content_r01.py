#!/usr/bin/env python3
"""Frozen ordinary-role pilot; no native/model integration or fresh holdout."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
import time

from evaluate_content_expansion_r01 import candidates as existing_candidates
from evaluate_reviewed_words import PROTECTED, WORD, u16
from evaluate_source_concepts import DETERMINERS, PREPOSITIONS, OBJECT_VERBS, COPULAS

Q = Path(__file__).resolve().parent
LANGUAGES = ('sw', 'ja', 'es')
KNOWLEDGE = ('none', 'all_function', 'all_function_global50', 'all_function_global100', 'all_function_global300')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_roles(text, policy):
    tokens = list(WORD.finditer(text))
    keys = [t.group().casefold().replace('’', "'") for t in tokens]
    roles = {}
    for i, token in enumerate(tokens):
        left = i
        while left and not text[tokens[left-1].end():tokens[left].start()].strip():
            left -= 1
        right = i + 1
        while right < len(tokens) and not text[tokens[right-1].end():tokens[right].start()].strip():
            right += 1
        before, after = keys[left:i], keys[i+1:right]
        previous = before[-1] if before else None
        initial = not text[:token.start()].strip() or text[:token.start()].rstrip()[-1:] in '.!?'
        reason = None
        if any(m.start() < token.end() and token.start() < m.end() for m in PROTECTED.finditer(text)):
            reason = 'protected_literal'
        elif any(c in text for c in ('"', '“', '”', '`')):
            reason = 'quoted_or_code_message'
        elif token.group().isupper() and len(token.group()) > 1:
            reason = 'uppercase_identifier'
        elif token.group()[0].isupper() and not initial:
            reason = 'mid_sentence_capital'
        prefix = before[:]
        removed = []
        while prefix and prefix[-1] in set(policy['verb_adverbs']) | set(policy['negative_auxiliaries']) and len(removed) < 2:
            removed.append(prefix.pop())
        subject = prefix[-1] if prefix and prefix[-1] in policy['subject_pronouns'] else None
        before_subject = prefix[-2] if subject and len(prefix) > 1 else None
        verbal = bool(subject) and before_subject not in {'would', 'could', 'might', 'should', 'will', 'may', 'can', 'must'}
        finite = previous in {'i', 'we'} and before_subject not in {'do', 'does', 'did'} and verbal and not removed
        roles[i] = {'before': before, 'after': after, 'previous': previous,
                    'initial': initial, 'common_rejection': reason,
                    'verbal': verbal, 'finite': finite,
                    'infinitival': previous == 'to'}
    return tokens, keys, roles


def role_allowed(source, role, policy):
    before, after, previous = role['before'], role['after'], role['previous']
    if role['common_rejection']:
        return False, role['common_rejection']
    if source == 'like':
        return (bool(role['verbal'] and after), 'preference_subject_or_complement_absent')
    if source == 'live':
        if not (role['verbal'] or role['infinitival']):
            return False, 'verb_role_absent'
        locative = bool(after and after[0] in {'here', 'there', 'alone', 'together', 'nearby'})
        if len(after) >= 2 and after[0] in {'in', 'at'}:
            complement = after[1:]
            if complement and complement[0] in DETERMINERS:
                complement = complement[1:]
            locative |= bool(complement and complement[0] in policy['locative_heads'])
        if len(after) >= 3 and after[0] == 'with' and after[1] in {'my', 'your', 'his', 'her', 'our', 'their'}:
            locative |= after[2] in policy['household_heads']
        return locative, 'residence_complement_unresolved'
    if source == 'shopping':
        return previous in {'go', 'goes', 'went', 'going', 'like', 'love', 'enjoy', 'hate'}, 'activity_context_absent'
    if source == 'currently':
        return True, ''
    if source == 'interesting':
        allowed = previous in COPULAS | {'am', 'be', 'been', 'very', 'really', 'quite', 'so', 'too', 'more', 'most', 'less'}
        allowed |= bool(previous in {'a', 'an', 'the'} and after)
        return allowed, 'adjective_context_absent'
    if source == 'either':
        negative = {'not', 'never', 'no', "don't", "doesn't", "didn't", "can't", "cannot", "isn't", "aren't", "wasn't", "weren't", "won't", "wouldn't", "couldn't", "haven't", "hasn't", "hadn't"}
        return bool(not after and set(before) & negative), 'negative_additive_context_absent'
    allowed = previous in DETERMINERS | PREPOSITIONS | OBJECT_VERBS or (role['initial'] and after and after[0] in COPULAS)
    return bool(allowed), 'noun_context_absent'


def new_candidates(text, candidate, policy, language):
    tokens, keys, roles = source_roles(text, policy)
    by_source = {e['source']: e for e in candidate['entries'] if e['language'] == language}
    found, rejected = [], []
    for i, token in enumerate(tokens):
        entry = by_source.get(keys[i])
        if not entry:
            continue
        allowed, reason = role_allowed(keys[i], roles[i], policy)
        if not allowed:
            rejected.append({'source': keys[i], 'start': token.start(), 'end': token.end(), 'reason': reason})
            continue
        family = candidate['source_families'].get(keys[i]) or keys[i]
        span = {'start': token.start(), 'end': token.end(), 'sourceStartUTF16': u16(text[:token.start()]),
                'sourceEndUTF16': u16(text[:token.end()]), 'original': token.group(),
                'translated': entry['target'], 'reading': entry['reading'],
                'category': entry['category'], 'concept_id': family,
                'lexicon_id': entry['id'], 'train_rank': entry['train_rank'],
                'changed_source_words': 1, 'content_source_words': int(entry['category'] == 'content'),
                'source_kind': 'role_lexical', 'guard': entry['guard'], 'native_entry_id': entry['native_entry_id']}
        found.append(span)
        if roles[i]['finite'] and roles[i]['previous'] in entry['finite_first_person']:
            form = entry['finite_first_person'][roles[i]['previous']]
            start = tokens[i-1].start()
            found.append(dict(span, start=start, sourceStartUTF16=u16(text[:start]),
                              original=text[start:token.end()], translated=form['target'],
                              changed_source_words=2, source_kind='attested_finite',
                              lexicon_id=entry['id'] + ':' + roles[i]['previous'], primary_form=form['primary_form']))
    return tokens, found, rejected


def choose(text, tokens, spans, density, known, order):
    budget = max(1, math.floor(len(tokens) * density))
    number = int(known.split('global')[-1]) if 'global' in known else 0
    learned = set(order[:number])
    eligible, rejected = [], Counter()
    for span in spans:
        if known != 'none' and span['category'] == 'function':
            rejected['known_function'] += 1
        elif span['category'] == 'content' and span['concept_id'] in learned:
            rejected['known_content_family'] += 1
        elif span['changed_source_words'] > budget:
            rejected['unit_exceeds_budget'] += 1
        else:
            eligible.append(span)
    eligible.sort(key=lambda s: (s['category'] != 'content', s['train_rank'], -s['changed_source_words'], s['start'], s['lexicon_id']))
    chosen, seen, used = [], set(), 0
    for span in eligible:
        if span['concept_id'] in seen:
            rejected['same_concept'] += 1
        elif any(span['start'] < s['end'] and s['start'] < span['end'] for s in chosen):
            rejected['overlap'] += 1
        elif used + span['changed_source_words'] > budget:
            rejected['remaining_budget'] += 1
        else:
            chosen.append(span)
            used += span['changed_source_words']
            seen.add(span['concept_id'])
    chosen.sort(key=lambda s: s['start'])
    output = text
    for span in reversed(chosen):
        assert text[span['start']:span['end']] == span['original']
        output = output[:span['start']] + span['translated'] + output[span['end']:]
    return {'spans': chosen, 'mixed_text': output, 'changed_source_words': used,
            'content_source_words': sum(s['content_source_words'] for s in chosen), 'budget': budget,
            'rejections': dict(rejected)}


def evaluate(text, baseline, candidate, policy, language):
    tokens, old, _ = existing_candidates(text, baseline, language)
    ntokens, added, rejected = new_candidates(text, candidate, policy, language)
    assert [(t.start(), t.end()) for t in tokens] == [(t.start(), t.end()) for t in ntokens]
    for span in old:
        word = span['original'].casefold().replace('’', "'")
        if span['category'] == 'content':
            span['concept_id'] = candidate['source_families'].get(word) or span['concept_id']
    arms = {}
    for density in policy['densities']:
        for known in KNOWLEDGE:
            for arm in ('control', 'role_word', 'role_finite'):
                extras = [] if arm == 'control' else [s for s in added if arm == 'role_finite' or s['source_kind'] != 'attested_finite']
                arms[f'{arm}|{density:.2f}|{known}'] = choose(text, tokens, old + extras, density, known, candidate['learned_family_order'])
    return {'source_words': len(tokens), 'added_candidates': added, 'added_rejections': rejected, 'arms': arms}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--kind', choices=['contrasts', 'train'], required=True)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    freeze = json.loads((Q/'role-content-data-freeze-r01.json').read_text())
    for name, digest in freeze['files'].items():
        assert sha(Q/name) == digest
    policy = json.loads((Q/'role-content-policy-r01.json').read_text())
    candidate = json.loads((Q/'role-content-candidate-r01.json').read_text())
    baseline = json.loads((Q/'content-expansion-candidate-r01.json').read_text())
    if a.kind == 'contrasts':
        cases = json.loads(a.input.read_text())['cases']
    else:
        assert sha(a.input) == 'a5a9672c3e2e8a2f3d740cb0b61810ad46f3e3cd7bbe86b8d79962c6b34ad33c'
        train = json.loads(a.input.read_text())
        cases = [{'id': f'bst-train-{ci:04d}-{ti:02d}', 'text': text, 'preceding_context_for_review': c['dialog'][:ti]}
                 for ci, c in enumerate(train) if c['context_dataset'] == 'convai2'
                 for ti, (speaker, text) in enumerate(c['dialog']) if speaker == 0 and text.strip()]
    started = time.monotonic()
    metrics, rejection_counts, review_pool, rows, contrast_failures = {}, Counter(), [], [], []
    for case in cases:
        targets = {}
        for language in LANGUAGES:
            result = evaluate(case['text'], baseline, candidate, policy, language)
            if a.kind == 'contrasts':
                tokens, keys, roles = source_roles(case['text'], policy)
                actual = any(role_allowed(case['source'], roles[i], policy)[0] for i, key in enumerate(keys) if key == case['source'])
                if actual != case['expected_role_admission']:
                    contrast_failures.append({'id': case['id'], 'language': language, 'expected': case['expected_role_admission'], 'actual': actual})
                targets[language] = result
            else:
                rejection_counts.update((language, r['source'], r['reason']) for r in result['added_rejections'])
                if result['added_candidates']:
                    review_pool.append({'id': case['id'], 'text': case['text'], 'language': language,
                        'preceding_context_for_review': case['preceding_context_for_review'],
                        'added_candidates': result['added_candidates'],
                        'control25': result['arms']['control|0.25|none'],
                        'role25': result['arms']['role_finite|0.25|none'],
                        'role50': result['arms']['role_finite|0.50|none']})
            n = result['source_words']
            for key, selection in result['arms'].items():
                for view in ('all', 'length_' + ('1-5' if n <= 5 else '6-15' if n <= 15 else '16+')):
                    m = metrics.setdefault((language, view, key), {'messages': 0, 'available': 0, 'content_available': 0,
                        'changed_source_words': 0, 'content_source_words': 0, 'depth_sum': 0., 'content_depth_sum': 0.,
                        'concepts': set(), 'content_concepts': set(), 'new_selected': 0})
                    m['messages'] += 1
                    m['available'] += bool(selection['spans'])
                    m['content_available'] += bool(selection['content_source_words'])
                    m['changed_source_words'] += selection['changed_source_words']
                    m['content_source_words'] += selection['content_source_words']
                    m['depth_sum'] += selection['changed_source_words']/n if n else 0
                    m['content_depth_sum'] += selection['content_source_words']/n if n else 0
                    m['concepts'].update(s['concept_id'] for s in selection['spans'])
                    m['content_concepts'].update(s['concept_id'] for s in selection['spans'] if s['category'] == 'content')
                    m['new_selected'] += any(s['lexicon_id'].startswith('role-r01') for s in selection['spans'])
        if a.kind == 'contrasts':
            rows.append(dict(case, targets=targets))
    summaries = {}
    for (language, view, key), m in metrics.items():
        m['mean_raw_depth'] = m.pop('depth_sum') / m['messages']
        m['mean_raw_content_depth'] = m.pop('content_depth_sum') / m['messages']
        m['distinct_concepts'] = len(m['concepts'])
        m['distinct_content_concepts'] = len(m['content_concepts'])
        m['concepts'] = sorted(m['concepts'])
        m['content_concepts'] = sorted(m['content_concepts'])
        summaries.setdefault(language, {}).setdefault(view, {})[key] = m
    review = []
    for language in LANGUAGES:
        pool = [r for r in review_pool if r['language'] == language and any(s['lexicon_id'].startswith('role-r01') for s in r['role25']['spans'])]
        pool.sort(key=lambda r: hashlib.sha256(('role-content-reviewed-r01|' + language + '|' + r['id']).encode()).hexdigest())
        chosen = []
        for guard in sorted({s['guard'] for r in pool for s in r['role25']['spans'] if s['lexicon_id'].startswith('role-r01')}):
            row = next(r for r in pool if any(s['lexicon_id'].startswith('role-r01') and s['guard'] == guard for s in r['role25']['spans']))
            if row not in chosen:
                chosen.append(row)
        chosen += [r for r in pool if r not in chosen][:24-len(chosen)]
        review += chosen
    out = {'production': False, 'kind': a.kind, 'semantic_approval': False, 'provider_calls': 0,
           'input_sha256': sha(a.input), 'policy_freeze_sha256': sha(Q/'role-content-data-freeze-r01.json'),
           'evaluator_sha256': sha(Path(__file__)), 'source_messages': len(cases), 'summary': summaries,
           'contrast_failures': contrast_failures, 'rows': rows, 'review_packet': review,
           'all_added_candidate_rows': review_pool,
           'rejections': [{'language': lang, 'source': source, 'reason': reason, 'count': count} for (lang, source, reason), count in sorted(rejection_counts.items())],
           'elapsed_seconds': time.monotonic() - started,
           'limitations': ['TRAIN role-play, not a fresh/unseen population estimate.', 'Raw selection is not correct meaning.', 'Python boundary approximation, not native latency or app integration.', 'Global learned-family simulation, not measured learner progression.']}
    assert not a.output.exists()
    a.output.write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n')
    print(sha(a.output), 'messages', len(cases), 'contrast_failures', contrast_failures, 'seconds', round(out['elapsed_seconds'], 2))
    for language in LANGUAGES:
        for arm in ('control', 'role_word', 'role_finite'):
            row = summaries[language]['all'][arm + '|0.25|none']
            print(language, arm, row['content_available'], round(row['mean_raw_content_depth']*100, 3), row['new_selected'], row['distinct_content_concepts'])


if __name__ == '__main__':
    main()
