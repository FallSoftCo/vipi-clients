#!/usr/bin/env python3
"""Freeze a bounded TRAIN-derived role/morphology mechanism before output."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

Q = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    assert not path.exists()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--primary', type=Path, required=True)
    p.add_argument('--mechanisms', type=Path, required=True)
    p.add_argument('--consensus', type=Path, required=True)
    a = p.parse_args()
    raw = json.loads(gzip.decompress(a.primary.read_bytes()))
    assert sha(a.primary) == '29795d515f0e64fa21746e39cbf5d78f6f31a692915364ef6d193fa942b7350a'
    records = {r[0]: r for r in raw['entries']}
    mechanisms = json.loads(a.mechanisms.read_text())
    ranks = {r['source']: r['TRAIN_rank'] for r in mechanisms['cases']}
    # Explicit ordinary-definition choices, not shortest-string ranking.
    # Source role/meaning remains a testable hypothesis, not golden truth.
    choices = [
        ('like', 'sw', 'kupenda', None, 705329, 'preference_verb'),
        ('like', 'ja', '好む', 'konomu', 1173167, 'preference_verb'),
        ('like', 'es', 'gustar', None, 293318, 'preference_verb'),
        ('live', 'sw', 'kuishi', None, 399500, 'residence_verb'),
        ('live', 'ja', '住む', 'sumu', 823703, 'residence_verb'),
        ('live', 'es', 'vivir', None, 295895, 'residence_verb'),
        ('parents', 'ja', '親', 'oya', 117536, 'ordinary_noun'),
        ('shopping', 'ja', '買い物', 'kaimono', 4009410, 'shopping_activity'),
        ('currently', 'es', 'actualmente', None, 407601, 'temporal_adverb'),
        ('either', 'es', 'tampoco', None, 441483, 'negative_additive'),
        ('interesting', 'ja', '面白い', 'omoshiroi', 483799, 'adjective'),
        ('interesting', 'es', 'interesante', None, 985479, 'adjective'),
        ('birthday', 'sw', 'siku ya kuzaliwa', None, 10260470, 'ordinary_noun'),
        ('birthday', 'ja', '誕生日', 'tanjōbi', 416445, 'ordinary_noun'),
        ('birthday', 'es', 'cumpleaños', None, 226286, 'ordinary_noun'),
        ('hospital', 'sw', 'hospitali', None, 2156320, 'ordinary_noun'),
        ('hospital', 'ja', '病院', 'byōin', 263818, 'ordinary_noun'),
    ]
    entries = []
    for source, lang, target, reading, identifier, guard in choices:
        record = records[identifier]
        assert record[1] == lang
        forms = [r for r in raw['forms'] if r[0] == identifier]
        assert target == record[2] or any(r[1] == target for r in forms)
        if reading:
            assert any(r[1] == reading and 'romanization' in json.loads(r[3]) for r in forms)
        finite = {}
        if lang == 'sw' and source in ('like', 'live'):
            expected = {'like': {'i': 'ninapenda', 'we': 'tunapenda'},
                        'live': {'i': 'ninaishi', 'we': 'tunaishi'}}[source]
            for person, written in expected.items():
                matching = [r for r in forms if r[1] == written]
                assert len(matching) == 1
                tags = set(json.loads(matching[0][3]))
                assert {'first-person', 'present', 'singular' if person == 'i' else 'plural'} <= tags
                finite[person] = {'target': written, 'primary_form': matching[0]}
        entries.append({'id': f'role-r01-en-{lang}-{source}', 'source': source, 'language': lang,
                        'target': target, 'reading': reading, 'native_entry_id': identifier,
                        'guard': guard, 'category': 'function' if source == 'either' else 'content',
                        'train_rank': ranks[source], 'concept': source,
                        'finite_first_person': finite,
                        'primary_entry': record,
                        'primary_senses': [r for r in raw['senses'] if r[0] == identifier],
                        'selected_form_evidence': [r for r in forms if r[1] in {target, reading}],
                        'primary_license': 'CC-BY-SA-4.0'})
    policy = {
        'production': False, 'research_only': True, 'policy_version': 'ordinary-role-content-r01',
        'purpose': 'Qualify reusable source-role/context + exact attested morphology against the unchanged expanded content catalog; ten previously selected TRAIN families are a bounded mechanism pilot, not the final large inventory.',
        'source_scope': 'Exact English complete tokens; no stems, translation provider or whole-target prerequisite.',
        'lookup_precedence': 'Recognize complete blocking/context frames before considering contained lexical tokens. A dictionary multiword head alone never selects a sense: literal live-with-household is separate from tolerating/partnership; comparative/discourse/would-like is separate from preference.',
        'subject_pronouns': ['i', 'you', 'we', 'they', 'he', 'she', 'it'],
        'verb_adverbs': ['really', 'actually', 'always', 'usually', 'still', 'also', 'just', 'never'],
        'negative_auxiliaries': ["don't", "doesn't", "didn't", 'not'],
        'preference_verb': 'Bare like preceded within the contiguous clause by subject pronoun and optionally one listed adverb/negative auxiliary, or do/does/did + subject question. Reject would/could/might + like (desire), be/look/feel/seem + like (comparison), discourse markers and quoted messages. Require a following token; do not use a neighbor from another punctuation-delimited clause.',
        'residence_verb': 'Bare live with the same subject/negative/infinitival source-role evidence plus a contiguous locative complement: here/there/alone/together/nearby; in/at + optional determiner + listed dwelling/location noun; or with + possessive + listed household/person noun. Other live-with idioms, live-off/on/up/down and unknown complements abstain.',
        'locative_heads': ['home', 'house', 'apartment', 'flat', 'city', 'town', 'village', 'country', 'neighborhood', 'neighbourhood', 'dorm', 'dormitory'],
        'household_heads': ['parent', 'parents', 'mom', 'mum', 'mother', 'dad', 'father', 'brother', 'sister', 'brothers', 'sisters', 'family', 'roommate', 'roommates', 'husband', 'wife', 'partner', 'boyfriend', 'girlfriend', 'friend', 'friends'],
        'ordinary_noun': 'Existing local determiner/preposition/object-verb noun guard or sentence-initial noun followed by copula. This is a declared source-role heuristic, not a universal syntax parse. Parent plural is Japanese unmarked-number noun, not both-parents 両親.',
        'shopping_activity': 'shopping after go/goes/went/going or after like/love/enjoy/hate. Do not infer an attested go-shopping whole translation or admit shopping-cart/product sense.',
        'temporal_adverb': 'Exact currently. Selected actualmente is at-present; no shortest hoy/today or uncorroborated Japanese 実際に.',
        'adjective': 'interesting after a copula/degree word, or a/the/an + interesting + following noun-like token; preserve pragmatic/euphemistic uncertainty in review.',
        'negative_additive': 'either only at a clause end with an earlier explicit negative in that same clause. Function category; never contributes content-anchor count. Positive-choice/determiner uses abstain.',
        'finite_unit': 'Only contiguous affirmative I/we + like/live may use the exact supplied Swahili first-person present form. Source unit covers pronoun+verb; content count is one. No inferred conjugations, third-person noun classes, Spanish gustar agreement or Japanese clause generation. Prefer this complete unit when it fits the remaining requested budget; otherwise retain the lexical infinitive candidate as a separately scored mixed-grammar hypothesis.',
        'selection': 'Content before function, then fixed TRAIN family rank, then longest same-concept source unit, then source offset. Complete disjoint ranges, one occurrence per concept, no over-budget fallback. Compare unchanged control, role-word addition, and role+finite addition.',
        'densities': [0.10, 0.25, 0.50],
        'knowledge': ['none', 'all_function', 'all_function_global50', 'all_function_global100', 'all_function_global300'],
        'known_order': 'Same retained global TRAIN canonical family order as the scalable audit; never count repeated inflections as new concepts. Correct prior job/jobs etc aliases; disclose any unresolvable source family.',
        'review': 'All authored contrast outputs, plus hash-fixed 24 added TRAIN messages per target/guard strata, source context included. Raw reach is separate from assistant meaning labels and errors. No fresh holdout is consumed.',
        'risk': ['Lexical infinitives retain native source grammar but can sound unnatural; Spanish gustar valency is explicitly reviewed, not silently declared syntax-correct.', 'Primary dictionary gloss is not blanket common-use or contextual correctness.', 'Target frequency is unavailable in this bounded pilot; no shortest synonym or unsupported frequency claim.', 'No production promotion/native build from this policy alone.'],
        'unavailable': {'sw': ['shopping: retained ununuzi only corroborates purchasing', 'currently: no selected exact ordinary target', 'interesting: missing primary candidate'], 'ja': ['currently: 実際に primary broad gloss insufficient for ordinary current-time use'], 'es': ['hospital: ordinary hospital is an unchanged face, no useful flip', 'shopping: compra purchasing sense and unchanged borrowing do not settle activity unit']},
        'input_hashes': {str(path): sha(path) for path in [a.primary, a.mechanisms, a.consensus, Q/'content-expansion-candidate-r01.json', Q/'content-expansion-concept-group-audit-r02.json', Path(__file__)]},
    }
    contrasts = [
        ('I like coffee.', 'like', True), ('We really like music.', 'like', True),
        ("I don't like coffee.", 'like', True), ('Do you like music?', 'like', True),
        ('Does she like music?', 'like', True), ('I would like coffee.', 'like', False),
        ('I feel like coffee.', 'like', False), ('It looks like coffee.', 'like', False),
        ('Nothing like a warm drink.', 'like', False), ('I am like my father.', 'like', False),
        ('I, like my father, enjoy tea.', 'like', False), ('I said "I like coffee".', 'like', False),
        ('I like.', 'like', False), ('I like! Coffee is good.', 'like', False),
        ('I live with my parents.', 'live', True), ('We live in a house.', 'live', True),
        ('Do you live here?', 'live', True), ('I want to live with my sister.', 'live', True),
        ('I live with pain.', 'live', False), ('I live in fear.', 'live', False),
        ('I live off my savings.', 'live', False), ('I live it up.', 'live', False),
        ('I enjoy live music.', 'live', False), ('We broadcast live.', 'live', False),
        ('I live in December.', 'live', False), ('I live. With my parents watching, I left.', 'live', False),
        ('My parents are home.', 'parents', True), ('The company parents a subsidiary.', 'parents', False),
        ('I go shopping.', 'shopping', True), ('I enjoy shopping.', 'shopping', True),
        ('The shopping cart is empty.', 'shopping', False), ('The shopping arrived.', 'shopping', False),
        ('I am currently studying.', 'currently', True), ('Interesting.', 'interesting', False),
        ('That is interesting.', 'interesting', True), ('It was an interesting idea.', 'interesting', True),
        ('My birthday is tomorrow.', 'birthday', True), ('I work in a hospital.', 'hospital', True),
        ("I don't eat fish either.", 'either', True), ('Either book is fine.', 'either', False),
        ('I like either book.', 'either', False), ('Me either.', 'either', False),
        ('I do not know. Either book is fine.', 'either', False),
    ]
    source_audit = json.loads(a.consensus.read_text())
    candidate = {'production': False, 'entries': entries,
                 'learned_family_order': source_audit['learned_family_order'],
                 'source_families': {r['source']: r['family'] for r in source_audit['source_rows']},
                 'evidence_scope': 'Exact selected primary definitions/forms/readings. No evaluated text imported as a phrase mapping.'}
    write(Q/'role-content-policy-r01.json', policy)
    write(Q/'role-content-candidate-r01.json', candidate)
    write(Q/'role-content-contrasts-r01.json', {'authored_before_output': True, 'semantic_gold': False,
          'cases': [{'id': f'role-contrast-{i:03}', 'text': text, 'source': source, 'expected_role_admission': allowed}
                    for i, (text, source, allowed) in enumerate(contrasts, 1)]})
    freeze = {'production': False, 'frozen_before_candidate_outputs': True,
              'scope': 'TRAIN-only mechanism comparison; source/target author already knows the ten illustrative training cases.',
              'files': {name: sha(Q/name) for name in ['role-content-policy-r01.json', 'role-content-candidate-r01.json', 'role-content-contrasts-r01.json']}}
    write(Q/'role-content-data-freeze-r01.json', freeze)
    print('entries', len(entries), 'contrasts', len(contrasts), 'freeze', sha(Q/'role-content-data-freeze-r01.json'))


if __name__ == '__main__':
    main()
