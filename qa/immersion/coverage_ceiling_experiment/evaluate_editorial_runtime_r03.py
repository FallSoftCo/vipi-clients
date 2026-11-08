#!/usr/bin/env python3
"""TRAIN diagnostic of corrected evidence and all-path scoped guards.

The competing attributive-role arm remains separate. Neither branch activates
data in the native apps; frozen selected scopes still require meaning review.
"""
import argparse
import collections
import hashlib
import json
import time
from pathlib import Path
import evaluate_editorial_content500_r01 as base
import editorial_common_roles_r01 as guard
from diagnose_editorial_guards_r02 import new_context
from editorial_runtime_lookup_r03 import SourceLookup
from evaluate_role_content_r02 import choose

Q = Path(__file__).resolve().parent
ARMS = ('r02_guard_control', 'r03_core', 'r03_competing_attributive')
DENSITIES = (.10, .25, .50)
KNOWLEDGE = ('none', 'all_function', 'all_function_global50', 'all_function_global100', 'all_function_global300')


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def emit(p, data):
    assert not p.exists(), p
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--evidence-dir', type=Path, required=True)
    p.add_argument('--prepare-freeze', action='store_true')
    a = p.parse_args()
    E = a.evidence_dir
    M = E / 'scaled-mechanism-cases-r01'
    paths = {'candidate': M/'editorial-runtime-candidate-r03.json',
             'control': M/'editorial-content500-candidate-r01.json',
             'baseline': Q/'content-expansion-candidate-r01.json',
             'train': E/'bst-evaluation-source-r01/train.json',
             'runner': Path(__file__), 'engine': Q/'editorial_runtime_lookup_r03.py',
             'guard': Q/'editorial_common_roles_r01.py',
             'scope_guard': Q/'diagnose_editorial_guards_r02.py',
             'selection': Q/'evaluate_role_content_r02.py',
             'control_evaluator': Q/'evaluate_editorial_content500_r01.py'}
    freeze = M/'editorial-runtime-freeze-r03.json'
    if a.prepare_freeze:
        emit(freeze, {'production': False, 'frozen_before_outputs': True,
                      'inputs': {k: {'path': str(v), 'sha256': sha(v)} for k, v in paths.items()},
                      'arms': ARMS, 'densities': DENSITIES, 'knowledge': KNOWLEDGE,
                      'core': ['Exact ordinary source-sense bindings; source ended-adjective withheld.',
                               'Same target faces, readings and concept grouping as frozenr01.',
                               'Source role metadata independent of target availability;6384 complete source forms.',
                               'Same independently inspected508 noun-only proxy; no new noun-only admission.',
                               'Quoted/URL/code literal overlap rejects every path, including functions; unclosed opener protects through end.',
                               'Existing reviewed face still wins same occurrence/concept. Full native parity unmeasured.'],
                      'separate_experimental_arm': 'Withhold noun-face use when its source has an adjective role and the following complete source has a noun role. Tests a competing modifier-role ambiguity, not a general compound ban; false abstentions must be reviewed.',
                      'contrast_policy': 'Existing known failure texts and authored quote/noun-role probes are diagnostics, never fresh-corpus semantic proof.',
                      'review_selection': '8 salted core-changed and8 salted competing-role-withheld contexts per target, one exact scope each. Review includes whole output and preceding context; source already used in TRAIN.',
                      'semantic_gate': 'No runtime promotion by raw reach. Require joined selected-scope/context review, explicit unresolved classes, native identity/known/budget/reading parity. Source and target proof separately bound.',
                      'coverage_limits': 'All9535 TRAIN role-play turns; no new holdout or population estimate. Reused previous observations stay diagnostic.'})
        print('freeze', sha(freeze))
        return
    f = json.loads(freeze.read_text())
    for k, path in paths.items():
        assert sha(path) == f['inputs'][k]['sha256'], k
    candidate = json.loads(paths['candidate'].read_text())
    control = json.loads(paths['control'].read_text())
    baseline = json.loads(paths['baseline'].read_text())
    engine = SourceLookup(baseline, candidate)
    train = json.loads(paths['train'].read_text())
    cases = [{'id': f'bst-train-{ci:04d}-{ti:02d}', 'text': text,
              'preceding_context_for_review_only': c['dialog'][:ti]}
             for ci, c in enumerate(train) if c['context_dataset'] == 'convai2'
             for ti, (speaker, text) in enumerate(c['dialog']) if speaker == 0 and text.strip()]
    assert len(cases) == 9535
    original_context, original_eligible = base.context, base.eligible

    def noun_eligible(ctx, pos, roles, form_kind='canonical'):
        if pos == 'noun' and not ctx['common_rejection'] and ctx['word'] in engine.noun_only:
            return True, 'inventory_noun_only_role'
        return guard.eligible(ctx, pos, roles, form_kind)

    base.context, base.eligible = new_context, noun_eligible
    metrics, pools = {}, collections.defaultdict(list)
    rejects = collections.Counter()
    started = time.monotonic()
    try:
        for case in cases:
            text = case['text']
            for language in ('sw', 'ja', 'es'):
                old = base.run(text, baseline, control, language)
                tokens, core_spans, core_rejections, literals = engine.candidates(text, language)
                ntokens, competing_spans, competing_rejections, _ = engine.candidates(text, language, True)
                assert len(tokens) == len(ntokens) == old['source_words']
                n = len(tokens)
                rejects.update((language, 'r03_core', r['rejected_reason']) for r in core_rejections)
                rejects.update((language, 'r03_competing_attributive', r['rejected_reason']) for r in competing_rejections)
                defaults = {}
                for density in DENSITIES:
                    for known in KNOWLEDGE:
                        selected = {
                            'r02_guard_control': old['arms'][f'editorial500|{density:.2f}|{known}'],
                            'r03_core': choose(text, tokens, core_spans, density, known, candidate['learned_family_order']),
                            'r03_competing_attributive': choose(text, tokens, competing_spans, density, known, candidate['learned_family_order']),
                        }
                        for arm, s in selected.items():
                            if arm != 'r02_guard_control':
                                assert all(not any(a < z['end'] and z['start'] < b for a, b in literals) for z in s['spans'])
                            for view in ('all', 'length_' + ('1-5' if n <= 5 else '6-15' if n <= 15 else '16+')):
                                key = language, arm, density, known, view
                                m = metrics.setdefault(key, {'messages': 0, 'available': 0, 'content_available': 0,
                                    'source_words': 0, 'changed_source_words': 0, 'content_source_words': 0,
                                    'depth_sum': 0., 'content_depth_sum': 0., 'concepts': set()})
                                m['messages'] += 1
                                m['available'] += bool(s['spans'])
                                m['content_available'] += bool(s['content_source_words'])
                                m['source_words'] += n
                                m['changed_source_words'] += s['changed_source_words']
                                m['content_source_words'] += s['content_source_words']
                                m['depth_sum'] += s['changed_source_words']/n if n else 0
                                m['content_depth_sum'] += s['content_source_words']/n if n else 0
                                m['concepts'].update(z['concept_id'] for z in s['spans'] if z['category'] == 'content')
                        if density == .25 and known in ('none', 'all_function_global300'):
                            defaults[known] = selected
                old25, core25, attr25 = (defaults['none'][arm] for arm in ARMS)
                identity = lambda s: (s['start'], s['end'], s['lexicon_id'])
                prior = {identity(s) for s in old25['spans']}
                added = [s for s in core25['spans'] if identity(s) not in prior]
                removed = [s for s in core25['spans'] if identity(s) not in {identity(t) for t in attr25['spans']}]
                attr_rejected_ids = {identity(s) for s in competing_rejections if s['rejected_reason'] == 'competing_attributive_role_experiment'}
                withheld = [s for s in removed if identity(s) in attr_rejected_ids]
                common = dict(case, language=language, source_words=n, defaults=defaults,
                              protected_ranges=literals, core_rejections=core_rejections,
                              competing_rejections=[s for s in competing_rejections if s['rejected_reason'] == 'competing_attributive_role_experiment'])
                if added:
                    pools[language+'|core_changed'].append(dict(common, reviewable_scopes=added))
                if withheld:
                    pools[language+'|attributive_withheld'].append(dict(common, reviewable_scopes=withheld))
    finally:
        base.context, base.eligible = original_context, original_eligible
    summary = []
    for (language, arm, density, known, view), m in metrics.items():
        summary.append(dict(language=language, arm=arm, density=density, known=known, view=view,
            **{k: v for k, v in m.items() if k not in ('concepts', 'depth_sum', 'content_depth_sum')},
            mean_depth=m['depth_sum']/m['messages'], mean_content_depth=m['content_depth_sum']/m['messages'],
            distinct_content_concepts=len(m['concepts']), concepts=sorted(m['concepts'])))
    packet = []
    for language in ('sw', 'ja', 'es'):
        for stratum in ('core_changed', 'attributive_withheld'):
            rows = sorted(pools[language+'|'+stratum], key=lambda r: hashlib.sha256(('vipi-runtime-r03|'+language+'|'+stratum+'|'+r['id']).encode()).hexdigest())
            for row in rows[:8]:
                scopes = sorted(row['reviewable_scopes'], key=lambda s: hashlib.sha256((row['id']+'|'+s['lexicon_id']+'|'+str(s['start'])).encode()).hexdigest())
                packet.append(dict(row, stratum=stratum, selected_review_scope=scopes[0]))
    diagnostic_texts = [
        'I said "hello" and enjoy music.', 'I said "I love music and coffee.',
        'I said “I love music” and enjoy coffee.', 'I wrote `I love music` and enjoy coffee.',
        'I enjoy https://example.com/music and coffee.', 'The company parents a subsidiary.',
        'My parents are kind.', 'I go to school.', 'I want to work.', 'That is pretty gross.',
        'I buy baby spinach for my salad.', 'I enjoy chicken soup.', 'I like orange juice.',
        'I work at a high school.', 'My great-great-grandfather lived here.',
        'The original trilogy is good.', 'The employee benefits are useful.',
        'My old man works too hard.', 'I am a short person.',
    ]
    contrasts = [{'text': text, 'language': lang,
                  'core': engine.select(text, lang, .50),
                  'competing': engine.select(text, lang, .50, competing_attributive=True)}
                 for text in diagnostic_texts for lang in ('sw', 'ja', 'es')]
    out = {'production': False, 'semantic_approval': False, 'provider_calls': 0,
           'freeze_sha256': sha(freeze), 'source_messages': len(cases), 'summary': summary,
           'rejections': [{'language': k[0], 'arm': k[1], 'reason': k[2], 'count': v} for k, v in sorted(rejects.items())],
           'gain_pools': dict(pools), 'review_packet': packet, 'diagnostic_contrasts': contrasts,
           'elapsed_seconds': time.monotonic()-started,
           'limits': ['TRAIN diagnostic and reused known errors, not unseen accuracy.',
                      'Current native production path is not this old research control.',
                      'All-path literal guards are checked; general sentence sense and compounds remain unresolved.',
                      'Python runtime measurement is not native mobile latency.']}
    output = M/'editorial-runtime-TRAIN-output-r03.json'
    emit(output, out)
    packet_path = M/'editorial-runtime-independent48-review-r03.json'
    emit(packet_path, {'production': False, 'capture_sha256': sha(output), 'candidate_sha256': sha(paths['candidate']),
                       'review_note': 'Review core additions and separately whether withheld noun faces were appropriate. Familiar TRAIN contexts, not blind corpus. Whole output errors remain separate from selected-scope denominator.',
                       'rows': packet})
    print(json.dumps({'path': str(output), 'sha256': sha(output), 'packet': str(packet_path),
                      'packet_sha256': sha(packet_path), 'packet_rows': len(packet),
                      'seconds': out['elapsed_seconds']}))


if __name__ == '__main__':
    main()
