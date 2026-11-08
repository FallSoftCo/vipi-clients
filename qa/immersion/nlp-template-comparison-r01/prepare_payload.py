#!/usr/bin/env python3
"""Freeze the bounded NLP comparison. No runtime data activation or MT calls."""
import hashlib
import itertools
import json
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EVIDENCE = Path('/home/ai/Development/investigations/vipi-immersion-reconciliation-20261107-r01')
Q = ROOT / 'qa/immersion/coverage_ceiling_experiment'


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    path = HERE / name
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    return sha(path)


proofs = {}
faces = []
sets = {}
patterns = []
inputs = {}


def proof(value):
    digest = hashlib.sha256(canonical(value)).hexdigest()
    proofs[digest] = value
    return digest


def face(source, target, language, concept, reading, evidence, qualification):
    identifier = f'en:{source}:{language}:{concept}'
    record = dict(id=identifier, concept_id=concept, source_language='en', source_form=source,
                  target_language=language, target=target, reading=reading or None,
                  primary_ref=evidence, qualification=qualification)
    old = next((f for f in faces if f['id'] == identifier), None)
    if old:
        assert (old['target'], old['reading']) == (record['target'], record['reading'])
    else:
        faces.append(record)
    return identifier


def formset(surface, ids, concept, evidence, pos='noun', lexeme='authored frame focus', features=None):
    key = 'focus:' + surface
    form = dict(id=key + ':0', surface=surface, lexeme_id=lexeme, pos=pos,
                features=features or [], face_ids=ids, primary_ref=evidence)
    if key in sets:
        assert sets[key][0]['face_ids'] == ids
    else:
        sets[key] = [form]
    return key


def literal(name, value):
    return dict(kind='literal', name=name, value=value)


def focus(name, key):
    return dict(kind='focus', name=name, form_set=key)


def morph(name, key):
    return dict(kind='morph', name=name, form_set=key)


def typed(name, kind, words=3):
    return dict(kind='typed', name=name, type=kind, max_words=words,
                max_utf16=64 if kind == 'number' else 128)


def part(name):
    return dict(kind='part', part=name)


def parts(first, last):
    return dict(kind='parts', **{'from': first}, through=last)


def output(concept, scope, from_part=None, ids=None, identifier=None):
    return dict(id=identifier or 'focus:' + concept, concept_id=concept, scope=scope,
                face_from_part=from_part, face_ids=ids or {}, native_cost='computed at runtime')


def pattern(identifier, family, arm, sourceparts, outputs, evidence, mode='none', scope=None,
            meaning=None, priority=0, reason='Only the approved focus is replaced; source grammar is retained.'):
    row = dict(id=identifier, family=family, source_language='en', arms=[arm], parts=sourceparts,
               atomicity=dict(mode=mode, scope=scope, reason=reason), approved_outputs=outputs,
               meaning_id=meaning or family, priority=priority, evidence_ref=evidence)
    row['record_sha256'] = hashlib.sha256(canonical(row)).hexdigest()
    patterns.append(row)


def read_db(path):
    inputs[str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)] = sha(path)
    db = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    return db


def main():
    contract = sha(HERE / 'contract.json')
    base_path = Q / 'content-expansion-candidate-r01.json'
    inputs[str(base_path.relative_to(ROOT))] = sha(base_path)
    base = json.loads(base_path.read_text())
    dbs = {lang: read_db(ROOT / f'data/immersion/en-{lang}.sqlite') for lang in ('sw', 'ja', 'es')}
    lex = {lang: read_db(EVIDENCE / f'noun-boundary-arms/d-{lang}.sqlite') for lang in ('en', 'sw', 'ja', 'es')}
    family_defs = [('reading_book', 'book_object', 'book', 'book'),
                   ('drinking_water', 'drinking_water', 'water', 'water'),
                   ('birthday_party', 'birthday_party', 'party', 'party'),
                   ('phone_charger', 'phone_charger', 'charger', 'charger'),
                   ('bank_account', 'bank_account', 'account', 'account'),
                   ('phone_number', 'phone_number', 'phone number', 'phone_number')]
    focus_keys = {}
    for stem, family, source, concept in family_defs:
        ids, records = {}, {}
        for lang, db in dbs.items():
            identifier = f'vipi-authored-r1:phrase_frame_{stem}:en-{lang}'
            row = db.execute('select payload,evidence from mappings where id=?', (identifier,)).fetchone()
            payload, evidence = json.loads(row['payload']), json.loads(row['evidence'])
            records[lang] = dict(payload=payload, evidence=evidence,
                                 source_inputs=[r[0] for r in db.execute('select input from source_inputs where mapping_id=? order by input', (identifier,))])
            ids[lang] = face(source, payload['target'], lang, concept, payload['reading'],
                             proof(records[lang]), 'existing_assessed_frame_face')
        evidence = proof(dict(kind='retained source frame and exact indexed expansions', records=records,
                              permission='Existing frame faces are assessed; source-only approval without target corroboration remains an experimental arm.'))
        key = formset(source, ids, concept, evidence)
        focus_keys[source] = key
        old_parts = records['es']['payload']['source_parts']
        new_parts = []
        for index, p in enumerate(old_parts):
            name = 'focus' if 'focus' in p else f'p{index}'
            if 'focus' in p:
                new_parts.append(focus(name, key))
            elif 'literal' in p:
                new_parts.append(literal(name, p['literal']))
            else:
                new_parts.append(dict(kind='enum', name=name, values=p['slot']))
        # Finite baseline retains the exact native matcher inputs. Exact arm includes ALL
        # already-indexed expansions, so enumeration is not disadvantaged artificially.
        out = output(concept, part('focus'), 'focus')
        pattern('finite:' + stem, family, 'existing_finite_slots', new_parts, [out], evidence,
                mode='head_backoff', scope=dict(kind='context'))
        assert all(records[lang]['source_inputs'] == records['es']['source_inputs'] for lang in records)
        for index, text in enumerate(records['es']['source_inputs']):
            start = text.rfind(source)
            assert start >= 0 and text.count(source) == 1
            p = ([literal('prefix', text[:start])] if start else []) + [focus('focus', key)]
            if text[start + len(source):]:
                p.append(literal('suffix', text[start + len(source):]))
            pattern(f'exact:{stem}:{index}', family, 'exact_top_down', p, [out], evidence,
                    mode='head_backoff', scope=dict(kind='context'))

    # Retained ordinary faces. Only diagnostic fallback entries are offered out of context;
    # their errors are observable controls, not new claims of source-only safety.
    fallback_ids = []
    for source, concept in [('books', 'book'), ('school', 'schools'), ('music', 'music'), ('dog', 'dog'), ('water', 'water')]:
        ids, rows = {}, {}
        for lang in ('sw', 'ja', 'es'):
            row = next(r for r in base['pairs']['en-' + lang]['entries'] if r['source'] == source)
            rows[lang] = row
            ids[lang] = face(source, row['target'], lang, concept, row.get('reading'), proof(row), 'existing_reviewed_word_face')
            if source != 'books':
                fallback_ids.append(ids[lang])
        evidence = proof(dict(kind='retained reviewed word faces', records=rows,
                              concept_note='book/books share the noun concept here; number-specific target faces remain distinct.'))
        key = formset(source, ids, concept, evidence, features=['plural'] if source == 'books' else [])
        focus_keys[source] = key

    # Complete English form identity is used for CONTEXT, not as permission to emit its
    # legacy stem-focus substring. Multiple retained analyses remain separate.
    for head, surfaces in {'read': ['read', 'reads', 'reading'], 'bring': ['bring', 'brings', 'bringing', 'brought'],
                           'drink': ['drink', 'drinks', 'drinking', 'drank', 'drunk'],
                           'go': ['go', 'goes', 'going', 'went'],
                           'raise': ['raise', 'raises', 'raised', 'raising']}.items():
        forms = []
        for surface in surfaces:
            rows = [dict(r) for r in lex['en'].execute('select s.*,l.headword,l.pos,l.source_url from surfaces s join lexemes l on l.id=s.lexeme where s.normalized=? and l.headword=? and l.pos=?', (surface, head, 'verb'))]
            if not rows:
                continue
            evidence = proof(dict(kind='exact retained source written-form identity', rows=rows,
                                  limitation='Context-only binding; no output authorization for a partial legacy focus or unique tense/person analysis.'))
            analyses = [dict(lexeme_id=r['lexeme'], features=json.loads(r['features'])) for r in rows]
            forms.append(dict(id=f'verb:{head}:{surface}', surface=surface, lexeme_id=rows[0]['lexeme'],
                              pos='verb', features=[], analyses=analyses, face_ids={}, primary_ref=evidence))
        sets['verb:' + head] = forms

    # Existing exact compound evidence supplies reusable shorter matches too. Longer
    # typed context is credited only for genuinely new contexts/number-sensitive forms.
    typed_proof = proof(dict(kind='new authored source grammar experiment', author='Vipi immersion team',
                             license='FallSoft.Co project authored', source_basis='Exact possessive/determiner object construction, retained written-form morphology, unchanged lexical noun focus.',
                             exclusions='No target agreement generation, no named-entity claim, no verb output, no sense guarantee from a matching string alone.'))
    for source in ('book', 'books'):
        key = focus_keys[source]
        for verb in ('read', 'bring'):
            pattern(f'typed:{verb}:possessor:{source}', 'book_object', 'typed_slots_attested_morphology',
                    [morph('action', 'verb:' + verb), literal('space1', ' '), typed('owner', 'possessor'),
                     literal('space2', ' '), focus('focus', key)],
                    [output('book', part('focus'), 'focus')], typed_proof,
                    mode='head_backoff', scope=part('focus'))
        if source == 'books':
            pattern('typed:bring:number:books', 'book_object', 'typed_slots_attested_morphology',
                    [morph('action', 'verb:bring'), literal('space1', ' '), typed('count', 'number', 8),
                     literal('space2', ' '), focus('focus', key)],
                    [output('book', part('focus'), 'focus')], typed_proof, mode='head_backoff', scope=part('focus'),
                    reason='Plural face is attested; numeral value is preserved, not used to generate agreement.')
    pattern('typed:drink:possessor:water', 'drinking_water', 'typed_slots_attested_morphology',
            [morph('action', 'verb:drink'), literal('space1', ' '), typed('owner', 'possessor'),
             literal('space2', ' '), focus('focus', focus_keys['water'])],
            [output('water', part('focus'), 'focus')], typed_proof, mode='head_backoff', scope=part('focus'))
    for family, prefix, source, concept in [('birthday_party', 'birthday ', 'party', 'party'),
                                           ('phone_charger', 'phone ', 'charger', 'charger'),
                                           ('bank_account', 'bank ', 'account', 'account')]:
        pattern('typed:possessor:' + family, family, 'typed_slots_attested_morphology',
                [typed('owner', 'possessor'), literal('space', ' '), literal('prefix', prefix), focus('focus', focus_keys[source])],
                [output(concept, part('focus'), 'focus')], typed_proof,
                mode='head_backoff', scope=parts('prefix', 'focus'))
    pattern('typed:phone:number', 'phone_number', 'typed_slots_attested_morphology',
            [typed('owner', 'possessor'), literal('space', ' '), focus('focus', focus_keys['phone number']),
             literal('copula', ' is '), typed('number', 'number', 8)],
            [output('phone_number', part('focus'), 'focus')], typed_proof, mode='head_backoff', scope=part('focus'))
    pattern('typed:phone:identifier', 'phone_number', 'typed_slots_attested_morphology',
            [focus('focus', focus_keys['phone number']), literal('location', ' at '), typed('identifier', 'identifier', 8)],
            [output('phone_number', part('focus'), 'focus')], typed_proof, mode='head_backoff', scope=part('focus'))

    for family, prefix, source, concept in [('high_school', 'high ', 'school', 'schools'), ('country_music', 'country ', 'music', 'music')]:
        evidence = proof(dict(kind='authored head-backoff compound contrast', source=prefix + source,
                              permitted_head=source, primary_face_proof=sets[focus_keys[source]][0]['primary_ref'],
                              scope='Experimental head meaning only; modifier is protected from generic independent substitution.'))
        pattern('exact:' + family, family, 'exact_top_down', [literal('modifier', prefix), focus('focus', focus_keys[source])],
                [output(concept, part('focus'), 'focus')], evidence, mode='head_backoff', scope=dict(kind='context'))

    # Food compound faces are primary sense-linked, but bare compound-shaped text does
    # NOT establish food sense. A mask-only permitted scope lets a longer food context
    # authorize the same complete output without authorizing generic dog underneath it.
    compound_ids = {}
    for lang, head in [('ja', 'ホットドッグ'), ('es', 'perrito caliente')]:
        r = lex[lang].execute('select * from lexemes where normalized=? and pos=?', (head, 'noun')).fetchone()
        terms = [dict(t) for t in lex[lang].execute('select t.*,s.label,s.source_url from terms t join senses s on s.id=t.sense where lexeme=?', (r['id'],))]
        term = next(t for t in terms if t['label'] == 'frankfurter in a bun')
        e = proof(dict(kind='primary sense-bound target entry', lexeme=dict(r), terms=terms,
                       source_lexemes=[dict(z) for z in lex['en'].execute('select * from lexemes where normalized=?', ('hot dog',))]))
        compound_ids[lang] = face('hot dog', head, lang, 'compound:hot_dog', term['reading'], e, 'new_experimental_compound_face')
    bareproof = proof(dict(kind='compound-shaped text with unresolved sense', source='hot dog',
                           alternatives=['frankfurter in a bun', 'literal hot animal', 'show-off verb/interjection'],
                           target_unavailable=['sw'], qualification='No food output from the bare match.'))
    maskout = output('compound:hot_dog', dict(kind='context'), ids={}, identifier='compound:hot_dog')
    pattern('mask:hot_dog', 'hot_dog', 'exact_top_down', [literal('compound', 'hot dog')], [maskout], bareproof,
            mode='atomic', scope=dict(kind='context'), meaning='hot_dog',
            reason='Compound shape alone is not food sense. Empty face map is recognition-only; longer food context can permit same ID and exact geometry.')
    for index, prefix in enumerate(('eat a ', 'ate a ', 'eating a ')):
        pattern(f'exact:hot_dog:food:{index}', 'hot_dog', 'exact_top_down',
                [literal('food_context', prefix), literal('compound', 'hot dog')],
                [output('compound:hot_dog', part('compound'), ids=compound_ids, identifier='compound:hot_dog')], bareproof,
                mode='atomic', scope=part('compound'), meaning='hot_dog', priority=10,
                reason='Authored food-predicate context. Literal animal counterreadings remain semantic review cases, not guaranteed by string matching.')
    idiomproof = proof(dict(kind='authored idiom/literal ambiguity control', source='raise the bar',
                            unavailable_reason='No approved sense-disambiguated target focus. Recognition must suppress generic bar even when known or over budget.'))
    for form in sets['verb:raise']:
        text = form['surface'] + ' the bar'
        pattern('exact:raise_bar:' + form['surface'], 'raise_the_bar', 'exact_top_down', [literal('idiom', text)], [], idiomproof,
                mode='ambiguous', scope=dict(kind='context'), reason='Idiom and physical bar are unresolved; no smaller generic bar output.')
    pattern('morph:raise_bar', 'raise_the_bar', 'typed_slots_attested_morphology',
            [morph('action', 'verb:raise'), literal('rest', ' the bar')], [], idiomproof,
            mode='ambiguous', scope=dict(kind='context'), reason='Same attested surface set as exact expansions; morphology is a representation comparison, not invented extra reach.')

    # Generic diagnostic controls deliberately include unsafe components to demonstrate
    # whether all recognition masks actually prevent smaller backoff across paths.
    runtime_path = EVIDENCE / 'scaled-mechanism-cases-r01/editorial-runtime-candidate-r03.json'
    runtime = json.loads(runtime_path.read_text())
    inputs[str(runtime_path)] = sha(runtime_path)
    for source in ('high', 'country', 'bar'):
        for lang in ('sw', 'ja', 'es'):
            rows = [r for r in runtime['entries'] if r.get('source') == source and r.get('language') == lang]
            if rows:
                row = rows[0]
                fallback_ids.append(face(source, row['target'], lang, source, row.get('reading'), proof(row), 'existing_reviewed_word_face'))

    payload = dict(schema='vipi.nlp-template-payload.r01', production=False, contract_sha256=contract,
                   schema_sha256=sha(HERE / 'schema.json'), semantics_sha256=sha(HERE / 'semantics.json'),
                   faces=faces, form_sets=sets, patterns=patterns, fallback_entries=sorted(set(fallback_ids)),
                   provenance=dict(inputs=inputs, proof_file='proofs.json', proof_sha256=save('proofs.json', proofs),
                                   license='Retained dictionary excerpts CC-BY-SA-4.0; project-authored frame/context records retain their original provenance.',
                                   record_hash='SHA256 of sorted compact UTF-8 JSON of pattern excluding record_sha256.',
                                   limitations=['Research only; exact source-only frame use is not current bidirectional frame acceptance.',
                                                'No source or target model calls. No target interpolation or arbitrary inflection generation.',
                                                'Fallback entries are deliberately unguarded diagnostic comparators, not a production word policy.',
                                                'Hot-dog Swahili face unavailable; no invented translation.',
                                                'HFST branch retained independently; this payload does not silently accept all analyzer features.']))
    payload_hash = save('payload.json', payload)
    build_cases(contract, payload_hash)
    save('freeze.json', dict(production=False, status='Frozen before comparator outputs', payload_sha256=payload_hash,
                             cases_sha256=sha(HERE / 'authored-cases.json'), proofs_sha256=sha(HERE / 'proofs.json'),
                             compiler_sha256=sha(Path(__file__)), patterns=len(patterns), faces=len(faces),
                             form_sets=len(sets), forms=sum(map(len, sets.values())), families=sorted({p['family'] for p in patterns}),
                             inputs=inputs, policy='Do not change targets/matcher after reviewing comparison output; retain any correction as explicit new revision.'))


def build_cases(contract, payload_hash):
    groups = {
        'book_object': [
            ('I am reading a book now.', 'existing_exact'), ('She reads a book every week.', 'finite_existing'),
            ('I read a book yesterday.', 'tense_preserved'), ('Can you bring my book?', 'typed_pronoun'),
            ("Can you bring Alice's book?", 'typed_name'), ("Please bring Alice Smith's book today.", 'typed_multi_name'),
            ("Please bring alice's book today.", 'typed_lowercase'), ("Can you bring my friend's book?", 'typed_common_possessor'),
            ("Can you bring James' book?", 'typed_s_possessive'), ("Can you bring O'Connor's book?", 'typed_internal_apostrophe'),
            ("Can you bring my friend's sister's book?", 'nested_possessive_negative'),
            ('Please bring 3 books tomorrow.', 'plural_number'), ('She brought their books yesterday.', 'attested_past_context'),
            ('I did not bring her book.', 'negation_retained'), ('We will bring our books.', 'auxiliary_retained'),
            ('Please book my flight.', 'verb_homograph_negative'), ('I read a bookkeeper report.', 'whole_token_negative'),
            ('The book is on the table.', 'unmatched_smaller_fallback'), ('My books are missing.', 'no_typed_context'),
            ('She said "bring my book" yesterday.', 'quoted_focus_negative'),
            ('She said "hello" and will bring my book.', 'unrelated_quote'),
            ('Please bring `book` today.', 'code_focus_negative'), ('Please bring my book and my book.', 'duplicate_context'),
            ('Please bring 1 books.', 'malformed_agreement_source'), ('Can you bring Alice book?', 'missing_possessive_negative')],
        'drinking_water': [
            ('I am drinking water.', 'existing_exact'), ('She drinks water every day.', 'finite_existing'),
            ('We drink water together.', 'existing_exact'), ('He drank my water.', 'past_context'),
            ("She is drinking Alice's water.", 'typed_name'), ('I did not drink your water.', 'negation_retained'),
            ('I will water my plants.', 'verb_homograph_negative'), ('The drinking water is cold.', 'noun_modifier_context'),
            ('I am drinking watercolors.', 'whole_token_negative'), ('Please drink some water.', 'unmatched_smaller_fallback'),
            ('Please drink my water at 10:30.', 'protected_number_outside'), ('"drink my water', 'unclosed_quote_negative')],
        'birthday_party': [
            ('I am going to my birthday party.', 'short_exact_reuse'), ("I am going to Alice's birthday party.", 'typed_name_no_artificial_gain'),
            ("We went to the man's birthday party.", 'typed_common_possessor'), ("We are going to Alice Smith's birthday party.", 'window_limit'),
            ('Her birthday party was fun.', 'sentence_case_boundary'), ('The birthday party starts at 5 pm.', 'protected_time_outside'),
            ('The party won the election.', 'political_party_negative'), ('I am going to my birthday.', 'no_party_focus'),
            ('I am going to @alice birthday party.', 'handle_not_possessor'), ('I love birthday parties.', 'unavailable_plural_face'),
            ('The birthday party is not tomorrow.', 'negation_retained'), ('"birthday party" is the title.', 'quoted_focus_negative')],
        'phone_charger': [
            ('I need a phone charger.', 'short_exact'), ("Where is Alice's phone charger?", 'typed_name_no_artificial_gain'),
            ('I found my phone charger.', 'typed_pronoun'), ('The phone charger costs 20 dollars.', 'protected_number_outside'),
            ('The horse was a charger.', 'other_sense_negative'), ('I need a phone charger cable.', 'longer_compound_context'),
            ('The phone chargers are here.', 'unavailable_plural_face'), ('My phone charged overnight.', 'whole_token_negative'),
            ('The code is `phone charger`.', 'code_focus_negative'), ('My friend mentioned "hello" beside the phone charger.', 'unrelated_quote')],
        'bank_account': [
            ('I opened a bank account.', 'short_exact'), ("This is Alice's bank account.", 'typed_name_no_artificial_gain'),
            ('Please check my bank account.', 'typed_pronoun'), ('I sat on the river bank.', 'other_sense_negative'),
            ('Her account of the event was clear.', 'other_sense_negative'), ('The bank account number is private.', 'longer_compound_context'),
            ('My bank accounts are closed.', 'unavailable_plural_face'), ('The text says "bank account".', 'quote_negative'),
            ('Do not change my bank account.', 'negation_retained'), ('My bank account is 123456.', 'number_preservation')],
        'phone_number': [
            ('What is your phone number?', 'existing_exact'), ('My phone number is 555-0123.', 'typed_number_case_boundary'),
            ('You can see my phone number is 555-0123.', 'typed_number'), ("Alice's phone number is +1 (555) 0123.", 'typed_name_number'),
            ('Check the phone number at https://example.com/contact.', 'typed_url_exact'), ('The phone number at @alice is old.', 'typed_handle'),
            ('The phone number at `contact` is wrong.', 'typed_code'), ('There is a phone number at alice@example.com.', 'typed_email'),
            ('My phone number is not 1234.', 'negative_copula_not_matched'), ('I number my books.', 'verb_number_negative'),
            ('The phone number is 12:30.', 'number_format_limit'), ('The phone number is `555`.', 'code_not_number'),
            ('The phone number at https://example.com/phone-number stays unchanged.', 'url_binding_preserved'),
            ('Please copy "your phone number".', 'quoted_focus_negative')],
        'high_school': [
            ('I teach at a high school.', 'head_backoff'), ('My high school is nearby.', 'head_backoff'),
            ('The school is high on the hill.', 'literal_adjective_context'), ('That price is high.', 'generic_component_valid_elsewhere'),
            ('I went to high school yesterday.', 'budget_quantization'), ('The high school music teacher is here.', 'longer_compound'),
            ('We discuss a high school of thought.', 'crossing_ambiguity_diagnostic'), ('The word is "high school".', 'quoted_focus_negative')],
        'hot_dog': [
            ('I eat a hot dog for lunch.', 'food_context'), ('We ate a hot dog yesterday.', 'food_past_context'),
            ('She is eating a hot dog.', 'food_progressive'), ('I want a hot dog.', 'bare_sense_unresolved'),
            ('That poor hot dog needs water.', 'literal_animal_ambiguity'), ('The hot dog is panting.', 'literal_animal_ambiguity'),
            ('The hot dog barked loudly.', 'literal_animal_ambiguity'), ('He likes to hot dog on stage.', 'verb_sense_negative'),
            ('Hot dog!', 'interjection_negative'), ('I eat a hot dog.', 'overbudget_and_known_mask'),
            ('I eat a hot dog and walk my dog.', 'protected_compound_other_dog'),
            ('I eat a hot dog while my dog sleeps.', 'compound_and_valid_smaller'),
            ('I eat a hot dogfish.', 'whole_token_negative'), ('The menu says "eat a hot dog".', 'quoted_focus_negative')],
        'country_music': [
            ('I like country music.', 'head_backoff'), ('My country music collection is large.', 'head_backoff'),
            ('The country has great music.', 'separate_literal_words'), ('I love the music in this country.', 'separate_literal_words'),
            ('Our country music school is excellent.', 'overlapping_compounds'), ('I am reading a country music book.', 'longer_context_retains_inner_mask'),
            ('The country musician is famous.', 'whole_token_negative'), ('The playlist is "country music".', 'quoted_focus_negative')],
        'raise_the_bar': [
            ('We raise the bar every year.', 'idiom_unavailable'), ('She raised the bar yesterday.', 'attested_past'),
            ('He is raising the bar again.', 'attested_progressive'), ('She raises the bar for everyone.', 'attested_third_person'),
            ('Please raise the bar above your head.', 'literal_physical_ambiguity'), ('The bar is open tonight.', 'generic_component_elsewhere'),
            ('I will not raise the bar.', 'negative_ambiguity'), ('The poster says "raise the bar".', 'quote_negative')],
    }
    cases = []
    for family, rows in groups.items():
        for index, (text, stratum) in enumerate(rows):
            cases.append(dict(id=f'nlp-r01-{family}-{index:03d}', text=text, source_language='en',
                              target_languages=['sw', 'ja', 'es'], stratum=stratum, family_hint=family,
                              expected_scope_category='Diagnostic authored contrast; expected scope is not semantic gold.'))
    assert len(cases) <= 160, len(cases)
    save('authored-cases.json', dict(schema='vipi.nlp-template-cases.r01', production=False,
                                    contract_sha256=contract, payload_sha256=payload_hash,
                                    provenance='Project-authored diagnostic contrasts frozen before comparator output, not held-out conversation coverage.', cases=cases))


if __name__ == '__main__':
    main()
