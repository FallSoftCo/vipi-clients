#!/usr/bin/env python3
"""Bounded research heads inside a corpus phrase; never semantic approval.

derive_heads accepts the export's exact text/codepoints/utf16 token dictionaries.
Both alignment sets use original source→target coordinates, including the
reverse-trained set. Masks survive missing counterparts and selection filters.
No literal parsing, native geometry substitution, target generation or learning
state is implemented here. Callers must apply their frozen policies separately.

This reuses evaluate_statistical_units.py's complete noun/adj/adv forms, matching
sense/POS/number, mutual anchor, closed union and strict-containing-unit masks.
It additionally requires complete UTF16 form geometry and explicit=true senses,
retains rejected alternatives, and binds readings to exact target term records.
Complete supported units retain masks even when output/case eligibility fails.
Run --self-test for synthetic structural controls; no corpus is opened.
"""
import copy
import functools
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'language-packs'))
from context_hints import lookup_key

SCHEMA = 'vipi.corpus-context-heads.r01'
MAX_TEXT_UTF16 = 16384
MAX_SENTENCE_TOKENS = 60
MAX_UNIT_TOKENS = 5
MAX_FORM_RECORDS = 16384
MAX_TERM_RECORDS = 32768
MAX_HEADS = 4096
MAX_SHARED_MATCHES = 32768
POSITIONS = {'noun', 'adj', 'adv'}


def _identity(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _tokens(text, supplied):
    if not isinstance(text, str) or len(text.encode('utf-16-le')) // 2 > MAX_TEXT_UTF16:
        raise ValueError('invalid or oversized original text')
    if not isinstance(supplied, (list, tuple)) or not 1 <= len(supplied) <= MAX_SENTENCE_TOKENS:
        raise ValueError('invalid sentence token count')
    offsets = [0]
    for char in text:
        offsets.append(offsets[-1] + len(char.encode('utf-16-le')) // 2)
    output, prior = [], 0
    for row in supplied:
        if not isinstance(row, dict) or set(row) != {'text', 'codepoints', 'utf16'}:
            raise ValueError('expected exact exported token shape')
        cp, u16 = row['codepoints'], row['utf16']
        if not all(isinstance(v, (list, tuple)) and len(v) == 2 and all(_integer(n) for n in v)
                   for v in [cp, u16]):
            raise ValueError('invalid token coordinates')
        a, b = cp
        if not prior <= a < b <= len(text) or text[a:b] != row['text'] or list(u16) != [offsets[a], offsets[b]]:
            raise ValueError('token does not reconstruct exact original text')
        output.append((row['text'], a, b, offsets[a], offsets[b]))
        prior = b
    return tuple(output)


def _range(value, count, maximum):
    if not isinstance(value, (tuple, list)) or len(value) != 2 or not all(_integer(n) for n in value):
        raise ValueError('invalid context range')
    a, b = value
    if not 0 <= a < b <= count or b - a > maximum:
        raise ValueError('context outside frozen limits')
    return a, b


def _scope(text, tokens, start, end):
    a, b = tokens[start][1], tokens[end - 1][2]
    return dict(tokens=[start, end], codepoints=[a, b],
                utf16=[tokens[start][3], tokens[end - 1][4]], text=text[a:b])


def _links(supplied, source_count, target_count):
    result = set()
    for edge in supplied:
        if not isinstance(edge, (tuple, list)) or len(edge) != 2 or not all(_integer(n) for n in edge):
            raise ValueError('invalid alignment edge')
        s, t = edge
        if not 0 <= s < source_count or not 0 <= t < target_count:
            raise ValueError('alignment edge outside full sentence')
        result.add((s, t))
    return result


def _database_identity(db):
    metadata = dict(db.execute("SELECT key,value FROM metadata WHERE key IN ('language','release_id','policy','normalization')"))
    result = {k: json.loads(v) for k, v in metadata.items()}
    if not isinstance(result.get('language'), str) or not result['language']:
        raise ValueError('dictionary language metadata required')
    return result


def _capitalization_rejected(surface, written, text, start):
    # Historical proper-name/homograph guard, unchanged; no new NER claim.
    return surface != written and (surface[:1].isupper() or
           written[:1].isupper() and bool(text[:start].strip()) and text[:start].rstrip()[-1] not in '.!?')


@functools.lru_cache(maxsize=16)
def _units_cached(db, text, tokens, language, database_revision):
    """The caller owns the immutable dictionary; revision also catches test writes.

    Cache keys retain the connection object, so a reused numeric object ID cannot
    alias another dictionary. Returned records are copied before public exposure.
    clear_unit_cache releases these bounded references at the end of a run.
    """
    del database_revision
    units, form_count, term_count = [], 0, 0
    for start in range(len(tokens)):
        for end in range(start + 1, min(start + MAX_UNIT_TOKENS, len(tokens)) + 1):
            scope = _scope(text, tokens, start, end)
            written, key = scope['text'], lookup_key(scope['text'], language)
            guard_row = db.execute('SELECT blocked,target_blocked,protect_inner,reason FROM guards WHERE normalized=?', (key,)).fetchone()
            guard = None if guard_row is None else dict(zip(['blocked', 'target_blocked', 'protect_inner', 'reason'], guard_row))
            forms = []
            # The shard's surfaces PK begins with normalized; lexemes is an ID PK.
            for row in db.execute('''SELECT f.lexeme,f.surface,f.start,f.end,f.number,f.mode,f.features,
                l.headword,l.pos,l.source_safe,l.target_safe,l.source_url
                FROM surfaces f JOIN lexemes l ON l.id=f.lexeme WHERE f.normalized=?''', (key,)):
                form_count += 1
                if form_count > MAX_FORM_RECORDS:
                    raise ValueError('dictionary form limit; no alternatives silently dropped')
                lexeme, surface, a, b, number, mode, features, headword, pos, source_safe, target_safe, url = row
                reasons = []
                complete = a == 0 and b == len(surface.encode('utf-16-le')) // 2 and lookup_key(surface, language) == key
                if not complete: reasons.append('incomplete_dictionary_form')
                if mode not in (1, 2): reasons.append('unsupported_form_mode')
                if pos not in POSITIONS: reasons.append('unsupported_pos')
                if not target_safe: reasons.append('dictionary_target_unsafe')
                if guard and (guard['blocked'] or guard['target_blocked']): reasons.append('dictionary_guard')
                if _capitalization_rejected(surface, written, text, scope['codepoints'][0]): reasons.append('historical_capitalization_guard')
                terms = []
                for sid, reading, eligible, qualifiers, label, explicit, surl, sense_pos in db.execute('''
                    SELECT t.sense,t.reading,t.eligible,t.qualifiers,s.label,s.explicit,s.source_url,s.pos
                    FROM terms t JOIN senses s ON s.id=t.sense WHERE t.lexeme=?''', (lexeme,)):
                    term_count += 1
                    if term_count > MAX_TERM_RECORDS:
                        raise ValueError('dictionary term limit; no alternatives silently dropped')
                    term_reasons = ([] if eligible else ['dictionary_term_ineligible']) + ([] if explicit else ['sense_not_explicit'])
                    terms.append(dict(term_id=_identity([language, lexeme, sid, reading, qualifiers]), sense_id=sid,
                                      reading=reading, eligible=bool(eligible), explicit=bool(explicit), qualifiers=json.loads(qualifiers),
                                      label=label, sense_pos=sense_pos, source_url=surl, reasons=term_reasons))
                forms.append(dict(form_id=_identity([language, lexeme, surface, a, b, number, mode, features]),
                                  lexeme_id=lexeme, surface=surface, form_utf16=[a, b], number=number, mode=mode,
                                  features=json.loads(features), headword=headword, pos=pos, source_safe=bool(source_safe),
                                  target_safe=bool(target_safe), source_url=url, complete=complete, reasons=reasons, terms=terms))
            if not forms and not (guard and guard['protect_inner']):
                continue
            forms.sort(key=lambda f: f['form_id'])
            for form in forms: form['terms'].sort(key=lambda t: t['term_id'])
            # Recognition survives capitalization/safety/term output rejection.
            # This conservative mask-only tightening is explicit in the handoff.
            complete_supported = any(f['complete'] and f['mode'] in (1, 2) and f['pos'] in POSITIONS for f in forms)
            protect = bool(guard and guard['protect_inner']) or complete_supported
            units.append(dict(unit_id=_identity([language, scope, key]), scope=scope, key=key,
                              guard=guard, forms=forms, protect_inner=protect))
    return units


def clear_unit_cache():
    _units_cached.cache_clear()


def unit_cache_info():
    return _units_cached.cache_info()._asdict()


def _dictionary_units(db, text, tokens, identity):
    revision = (db.total_changes, db.execute('PRAGMA data_version').fetchone()[0], _identity(identity))
    return _units_cached(db, text, tokens, identity['language'], revision)


def _within(unit, context):
    a, b = unit['scope']['tokens']
    return context[0] <= a < b <= context[1]


def _maskers(unit, units):
    a, b = unit['scope']['tokens']
    return [v['unit_id'] for v in units if v['protect_inner'] and
            v['scope']['tokens'] != [a, b] and v['scope']['tokens'][0] <= a and v['scope']['tokens'][1] >= b]


def _mask(unit):
    return dict(unit_id=unit['unit_id'], **unit['scope'],
                form_ids=[f['form_id'] for f in unit['forms'] if f['complete'] and f['mode'] in (1, 2) and f['pos'] in POSITIONS],
                guard=unit['guard'], policy='strict_containing_complete_unit_or_guard',
                protects_without_target=True)


def recognize_source_masks(text, tokens, source_db):
    """Recognize the actual message independently of a corpus example/target.

    Malformed or oversized input raises ValueError; it is never an empty-mask
    success. The caller keeps its original native token/literal eligibility.
    """
    checked = _tokens(text, tokens)
    identity = _database_identity(source_db)
    units = _dictionary_units(source_db, text, checked, identity)
    return copy.deepcopy(dict(schema=SCHEMA, production=False, semantic_approval=False,
                              source_dictionary=identity,
                              source_masks=[_mask(u) for u in units if u['protect_inner']],
                              rejected=[dict(unit=u, reasons=['no_eligible_explicit_unit_term']) for u in units
                                        if not any(not f['reasons'] and any(not t['reasons'] for t in f['terms']) for f in u['forms'])],
                              diagnostics=dict(full_sentence_tokens=len(checked), recognized_units=len(units),
                                               maximum_unit_tokens=MAX_UNIT_TOKENS, literal_policy_applied=False)))


def derive_heads(source_text, target_text, source_tokens, target_tokens, source_context,
                 target_context, forward_links, reverse_links, source_db, target_db):
    """Return all shared-sense head alternatives, independent masks and rejections.

    structural_eligible means only this helper's dictionary/alignment controls.
    It is neither semantic approval nor native/literal/known/density eligibility.
    Rejected alternatives stay in heads; rejected also summarizes unit-level gaps.
    """
    st, tt = _tokens(source_text, source_tokens), _tokens(target_text, target_tokens)
    sc, tc = _range(source_context, len(st), 8), _range(target_context, len(tt), 12)
    forward, reverse = _links(forward_links, len(st), len(tt)), _links(reverse_links, len(st), len(tt))
    union, mutual = forward | reverse, forward & reverse
    sd, td = _database_identity(source_db), _database_identity(target_db)
    su = _dictionary_units(source_db, source_text, st, sd)
    tu = _dictionary_units(target_db, target_text, tt, td)
    heads, rejected, paired_source, paired_target = [], [], set(), set()
    match_count = 0
    for left in (u for u in su if _within(u, sc)):
        for right in (u for u in tu if _within(u, tc)):
            matches = []
            target_terms = {}
            for tf in right['forms']:
                for tterm in tf['terms']:
                    target_terms.setdefault(tterm['sense_id'], []).append((tf, tterm))
            for sf in left['forms']:
                for sterm in sf['terms']:
                    for tf, tterm in target_terms.get(sterm['sense_id'], []):
                        match_count += 1
                        if match_count > MAX_SHARED_MATCHES:
                            raise ValueError('shared match limit; no alternatives silently dropped')
                        reasons = set(sf['reasons'] + tf['reasons'] + sterm['reasons'] + tterm['reasons'])
                        if sf['pos'] != tf['pos']: reasons.add('pos_mismatch')
                        if sf['number'] != tf['number']: reasons.add('number_mismatch')
                        matches.append(dict(sense_id=sterm['sense_id'], source_pos=sf['pos'], target_pos=tf['pos'],
                                                source_number=sf['number'], target_number=tf['number'],
                                                source_form_id=sf['form_id'], target_form_id=tf['form_id'],
                                                source_lexeme_id=sf['lexeme_id'], target_lexeme_id=tf['lexeme_id'],
                                                source_term_id=sterm['term_id'], target_term_id=tterm['term_id'],
                                                source_primary_url=sf['source_url'], target_primary_url=tf['source_url'],
                                                source_sense_url=sterm['source_url'], target_sense_url=tterm['source_url'],
                                            target_reading=tterm['reading'], structural_eligible=not reasons, reasons=sorted(reasons)))
            if not matches: continue
            if len(heads) >= MAX_HEADS: raise ValueError('head alternative limit; no alternatives silently dropped')
            paired_source.add(left['unit_id']); paired_target.add(right['unit_id'])
            sa, sb = left['scope']['tokens']; ta, tb = right['scope']['tokens']
            inside = {(s, t) for s, t in union if sa <= s < sb and ta <= t < tb}
            crossing = sorted((s, t) for s, t in union if (sa <= s < sb) != (ta <= t < tb))
            reasons = []
            if not inside & mutual: reasons.append('no_mutual_anchor')
            if crossing: reasons.append('union_edge_crosses_focus')
            sm, tm = _maskers(left, su), _maskers(right, tu)
            if sm: reasons.append('inside_larger_source_unit')
            if tm: reasons.append('inside_larger_target_unit')
            if not any(m['structural_eligible'] for m in matches): reasons.append('no_eligible_shared_sense_pos_number')
            matches.sort(key=lambda m: (m['sense_id'], m['source_form_id'], m['target_form_id'], m['source_term_id'], m['target_term_id']))
            heads.append(dict(head_id=_identity([left['unit_id'], right['unit_id']]),
                              source_tokens=left['scope']['tokens'], target_tokens=right['scope']['tokens'],
                              source_codepoints=left['scope']['codepoints'], source_utf16=left['scope']['utf16'],
                              target_codepoints=right['scope']['codepoints'], target_utf16=right['scope']['utf16'],
                              source_text=left['scope']['text'], target_text=right['scope']['text'],
                              source_unit_id=left['unit_id'], target_unit_id=right['unit_id'],
                              source_context=_scope(source_text, st, *sc), target_context=_scope(target_text, tt, *tc),
                              source_forms=left['forms'], target_forms=right['forms'], shared_senses=matches,
                              readings=[dict(text=m['target_reading'], target_term_id=m['target_term_id'],
                                             target_form_id=m['target_form_id'], sense_id=m['sense_id'],
                                             structural_eligible=m['structural_eligible']) for m in matches if m['target_reading']],
                              mutual_anchor=sorted(inside & mutual), crossing_union_edges=crossing,
                              source_mask_ids=sm, target_mask_ids=tm, structural_eligible=not reasons, reasons=reasons))
    # Preserve the alternatives instead of historically discarding both records.
    geometries = {}
    for head in heads:
        if head['structural_eligible']:
            geometries.setdefault(tuple(head['source_tokens']), set()).add(tuple(head['target_tokens']))
    for head in heads:
        if head['structural_eligible'] and len(geometries[tuple(head['source_tokens'])]) > 1:
            head['structural_eligible'] = False
            head['reasons'].append('competing_target_geometry')
        if not head['structural_eligible']:
            rejected.append(dict(kind='head', head_id=head['head_id'], reasons=head['reasons']))
    for side, all_units, context, paired in [('source', su, sc, paired_source), ('target', tu, tc, paired_target)]:
        for unit in all_units:
            if not _within(unit, context): continue
            reasons = []
            if unit['unit_id'] not in paired: reasons.append('no_shared_sense_counterpart_in_context')
            if not any(not f['reasons'] and any(not t['reasons'] for t in f['terms']) for f in unit['forms']):
                reasons.append('no_eligible_explicit_unit_term')
            if reasons:
                rejected.append(dict(kind='unit', side=side, unit=unit, reasons=reasons))
    return copy.deepcopy(dict(schema=SCHEMA, production=False, semantic_approval=False,
                              source_dictionary=sd, target_dictionary=td,
                              source_context=_scope(source_text, st, *sc), target_context=_scope(target_text, tt, *tc),
                              heads=heads, source_masks=[_mask(u) for u in su if u['protect_inner']],
                              target_masks=[_mask(u) for u in tu if u['protect_inner']], rejected=rejected,
                              policy=dict(maximum_unit_tokens=MAX_UNIT_TOKENS, explicit_senses_required=True,
                                          masks_survive_absent_target=True, native_literal_known_budget_applied=False,
                                          source_safe_single_sense_required=False,
                                          historical_difference='Complete UTF16 forms and explicit senses required; alternatives retained; complete supported-unit masks survive output/capitalization rejection.')))


def _self_test():
    import unittest

    class Controls(unittest.TestCase):
        def setUp(self):
            clear_unit_cache()
            self.source, self.target = self.database('en'), self.database('es')

        def tearDown(self):
            clear_unit_cache()
            self.source.close(); self.target.close()

        def database(self, language):
            db = sqlite3.connect(':memory:')
            db.executescript('''
                CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT) WITHOUT ROWID;
                CREATE TABLE lexemes(id INTEGER PRIMARY KEY,headword,pos,source_safe,target_safe,source_url);
                CREATE TABLE surfaces(normalized TEXT,lexeme INTEGER,surface TEXT,start INTEGER,end INTEGER,
                    number INTEGER,mode INTEGER,features TEXT,
                    PRIMARY KEY(normalized,lexeme,surface,start,end,number,mode,features)) WITHOUT ROWID;
                CREATE TABLE senses(id TEXT PRIMARY KEY,label,pos,explicit,source_url) WITHOUT ROWID;
                CREATE TABLE terms(lexeme INTEGER,sense TEXT,reading TEXT,eligible INTEGER,qualifiers TEXT,
                    PRIMARY KEY(lexeme,sense,reading,qualifiers)) WITHOUT ROWID;
                CREATE TABLE guards(normalized TEXT PRIMARY KEY,blocked,target_blocked,protect_inner,reason) WITHOUT ROWID;''')
            db.execute('INSERT INTO metadata VALUES (?,?)', ('language', json.dumps(language)))
            db.execute('INSERT INTO metadata VALUES (?,?)', ('release_id', '"synthetic-1"'))
            return db

        def add(self, db, word, sid, pos='noun', number=0, eligible=True, explicit=True, reading='', end=None, mode=1):
            language = _database_identity(db)['language']
            lid = db.execute('SELECT count(*)+1 FROM lexemes').fetchone()[0]
            db.execute('INSERT INTO lexemes VALUES(?,?,?,?,?,?)', (lid, word, pos, 0, 1, 'synthetic:entry:' + str(lid)))
            db.execute('INSERT INTO surfaces VALUES(?,?,?,?,?,?,?,?)',
                       (lookup_key(word, language), lid, word, 0, len(word.encode('utf-16-le')) // 2 if end is None else end, number, mode, '[]'))
            if sid is not None:
                db.execute('INSERT OR IGNORE INTO senses VALUES(?,?,?,?,?)', (sid, sid, pos, int(explicit), 'synthetic:sense:' + sid))
                db.execute('INSERT INTO terms VALUES(?,?,?,?,?)', (lid, sid, reading, int(eligible), '[]'))
            return lid

        def tokens(self, text):
            # Explicit whitespace-delimited synthetic controls, not a new producer tokenizer.
            result, start = [], 0
            for word in text.split():
                start = text.index(word, start); end = start + len(word)
                result.append(dict(text=word, codepoints=[start, end],
                                   utf16=[len(text[:start].encode('utf-16-le')) // 2, len(text[:end].encode('utf-16-le')) // 2]))
                start = end
            return result

        def run_heads(self, source, target, forward, reverse=None, sc=None, tc=None):
            st, tt = self.tokens(source), self.tokens(target)
            return derive_heads(source, target, st, tt, sc or [0, len(st)], tc or [0, len(tt)],
                                forward, forward if reverse is None else reverse, self.source, self.target)

        def test_head_context_offsets_and_term_bound_readings(self):
            self.add(self.source, 'water', 'water')
            lid = self.add(self.target, 'agua', 'water', reading='agua-reading')
            self.target.execute('INSERT INTO senses VALUES(?,?,?,?,?)', ('unrelated', 'other', 'noun', 1, 'synthetic:other'))
            self.target.execute('INSERT INTO terms VALUES(?,?,?,?,?)', (lid, 'unrelated', 'wrong-reading', 1, '[]'))
            result = self.run_heads('I need water', 'Necesito agua', {(2, 1)})
            head = result['heads'][0]
            self.assertTrue(head['structural_eligible'])
            self.assertEqual(head['source_tokens'], [2, 3])
            self.assertEqual(head['source_context']['text'], 'I need water')
            self.assertEqual(head['source_utf16'], [7, 12])
            self.assertEqual([x['text'] for x in head['readings']], ['agua-reading'])
            self.assertEqual(head['readings'][0]['target_term_id'], head['shared_senses'][0]['target_term_id'])

        def test_source_mask_survives_missing_target_and_smaller_context(self):
            self.add(self.source, 'cream', 'cream'); self.add(self.source, 'ice cream', None)
            self.add(self.target, 'nata', 'cream')
            result = self.run_heads('ice cream', 'nata', {(1, 0)}, sc=[1, 2])
            self.assertIn('inside_larger_source_unit', result['heads'][0]['reasons'])
            self.assertTrue(any(m['text'] == 'ice cream' for m in result['source_masks']))

        def test_actual_message_masks_do_not_depend_on_corpus_context(self):
            self.add(self.source, 'country', 'country')
            self.add(self.source, 'country music', None)
            corpus = recognize_source_masks('like country', self.tokens('like country'), self.source)
            actual = recognize_source_masks('I like country music', self.tokens('I like country music'), self.source)
            self.assertFalse(any(m['text'] == 'country music' for m in corpus['source_masks']))
            self.assertTrue(any(m['text'] == 'country music' for m in actual['source_masks']))
            with self.assertRaises(ValueError):
                recognize_source_masks(' '.join(['word'] * 61), self.tokens(' '.join(['word'] * 61)), self.source)

        def test_uppercase_compound_mask_survives_case_rejection(self):
            self.add(self.source, 'country music', 'genre')
            self.add(self.source, 'music', 'music'); self.add(self.target, 'música', 'music')
            result = self.run_heads('I like Country music', 'música', {(3, 0)})
            self.assertTrue(any(m['text'] == 'Country music' and m['form_ids'] for m in result['source_masks']))
            self.assertIn('inside_larger_source_unit', result['heads'][0]['reasons'])

        def test_target_complete_unit_masks_inner_head(self):
            self.add(self.source, 'email', 'email'); self.add(self.target, 'correo', 'email')
            self.add(self.target, 'correo electrónico', None)
            result = self.run_heads('email', 'correo electrónico', {(0, 0)})
            self.assertIn('inside_larger_target_unit', result['heads'][0]['reasons'])
            self.assertTrue(any(m['text'] == 'correo electrónico' for m in result['target_masks']))

        def test_union_crossing_and_missing_mutual_anchor(self):
            self.add(self.source, 'water', 'water'); self.add(self.target, 'agua', 'water')
            result = self.run_heads('water now', 'agua ahora', {(0, 0), (1, 1)}, {(0, 0), (1, 0)})
            self.assertIn('union_edge_crosses_focus', result['heads'][0]['reasons'])
            result = self.run_heads('water', 'agua', {(0, 0)}, set())
            self.assertIn('no_mutual_anchor', result['heads'][0]['reasons'])

        def test_complete_many_to_many_focus_and_unaligned_modifier(self):
            self.add(self.source, 'ice cream', 'ice-cream'); self.add(self.target, 'helado', 'ice-cream')
            result = self.run_heads('ice cream', 'helado', {(0, 0), (1, 0)})
            self.assertTrue(result['heads'][0]['structural_eligible'])
            self.add(self.source, 'laptop', 'laptop'); self.add(self.target, 'computadora portátil', 'laptop')
            result = self.run_heads('laptop', 'computadora portátil', {(0, 0)})
            self.assertTrue(result['heads'][0]['structural_eligible'])

        def test_false_and_ineligible_senses_retained_but_not_approved(self):
            self.add(self.source, 'water', 'water', explicit=False)
            self.add(self.target, 'agua', 'water', explicit=False, eligible=False)
            head = self.run_heads('water', 'agua', {(0, 0)})['heads'][0]
            self.assertFalse(head['structural_eligible'])
            self.assertIn('sense_not_explicit', head['shared_senses'][0]['reasons'])
            self.assertIn('dictionary_term_ineligible', head['shared_senses'][0]['reasons'])

        def test_pos_number_and_partial_form_rejections(self):
            self.add(self.source, 'water', 'water')
            self.add(self.target, 'aguas', 'water', pos='adj', number=2)
            head = self.run_heads('water', 'aguas', {(0, 0)})['heads'][0]
            self.assertEqual(set(head['shared_senses'][0]['reasons']), {'pos_mismatch', 'number_mismatch'})
            self.add(self.source, 'a😀b', 'symbol', end=3)
            self.add(self.target, 'símbolo', 'symbol')
            head = self.run_heads('a😀b', 'símbolo', {(0, 0)})['heads'][0]
            self.assertIn('incomplete_dictionary_form', head['shared_senses'][0]['reasons'])

        def test_astral_exact_offsets_and_invalid_coordinates(self):
            self.add(self.source, 'a😀b', 'symbol'); self.add(self.target, 'símbolo', 'symbol')
            head = self.run_heads('a😀b', 'símbolo', {(0, 0)})['heads'][0]
            self.assertTrue(head['structural_eligible']); self.assertEqual(head['source_utf16'], [0, 4])
            self.assertEqual(head['source_codepoints'], [0, 3])
            malformed = self.tokens('a😀b'); malformed[0]['utf16'] = [0, 3]
            with self.assertRaises(ValueError):
                derive_heads('a😀b', 'símbolo', malformed, self.tokens('símbolo'), [0, 1], [0, 1], {(0, 0)}, {(0, 0)}, self.source, self.target)

        def test_competing_counterpart_geometry_retained(self):
            self.add(self.source, 'house', 'house')
            self.add(self.target, 'la casa', 'house'); self.add(self.target, 'casa grande', 'house')
            result = self.run_heads('house', 'la casa grande', {(0, 1)})
            self.assertEqual(len(result['heads']), 2)
            self.assertTrue(all('competing_target_geometry' in h['reasons'] for h in result['heads']))

        def test_capitalization_and_dictionary_guard(self):
            self.add(self.source, 'water', 'water'); self.add(self.target, 'agua', 'water')
            head = self.run_heads('I like Water', 'agua', {(2, 0)})['heads'][0]
            self.assertIn('historical_capitalization_guard', head['shared_senses'][0]['reasons'])
            self.source.execute('INSERT INTO guards VALUES(?,?,?,?,?)', ('water', 1, 0, 1, 'synthetic'))
            result = self.run_heads('water', 'agua', {(0, 0)})
            self.assertFalse(result['heads'][0]['structural_eligible'])
            self.assertTrue(result['source_masks'])

        def test_cache_reuse_mutation_isolation_and_database_revision(self):
            self.add(self.source, 'water', 'water'); self.add(self.target, 'agua', 'water')
            first = self.run_heads('water', 'agua', {(0, 0)})
            first['heads'][0]['source_forms'][0]['terms'][0]['reading'] = 'mutation'
            second = self.run_heads('water', 'agua', {(0, 0)})
            self.assertEqual(unit_cache_info()['hits'], 2)
            self.assertNotEqual(second['heads'][0]['source_forms'][0]['terms'][0]['reading'], 'mutation')
            self.source.execute('UPDATE terms SET eligible=0')
            self.assertFalse(self.run_heads('water', 'agua', {(0, 0)})['heads'][0]['structural_eligible'])

        def test_surface_lookup_is_indexed_and_lexeme_is_primary_key(self):
            plan = self.source.execute('EXPLAIN QUERY PLAN SELECT f.lexeme FROM surfaces f JOIN lexemes l ON l.id=f.lexeme WHERE f.normalized=?', ('water',)).fetchall()
            detail = ' '.join(row[-1] for row in plan)
            self.assertIn('SEARCH f USING PRIMARY KEY (normalized=?)', detail)
            self.assertIn('SEARCH l USING INTEGER PRIMARY KEY', detail)
            self.assertNotIn('SCAN', detail)

    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    if sys.argv[1:] != ['--self-test']:
        raise SystemExit('Import derive_heads, or use --self-test; no full-corpus runner is provided.')
    raise SystemExit(_self_test())
