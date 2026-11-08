#!/usr/bin/env python3
"""Independent bounded comparator using retained native token/window geometry.

No provider calls. This is an experiment, not a production eligibility policy.
"""
import argparse
import collections
import hashlib
import json
import math
import re
import time
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def u16(text):
    return len(text.encode('utf-16-le')) // 2


def cp_map(text):
    values = [0]
    for ch in text:
        values.append(values[-1] + u16(ch))
    return values, {n: i for i, n in enumerate(values)}


def overlap(a, b):
    return a[0] < b[1] and b[0] < a[1]


def quoted_ranges(text):
    # Exact frozen source function, copied to avoid importing the research pipeline.
    out = []
    i = 0
    while i < len(text):
        marker = next((m for m in ('```', '`', '“', '"') if text.startswith(m, i)), None)
        if not marker or (i and text[i - 1] == '\\'):
            i += 1
            continue
        closing = '”' if marker == '“' else marker
        j = text.find(closing, i + len(marker))
        while j >= 0 and j and text[j - 1] == '\\':
            j = text.find(closing, j + len(closing))
        end = len(text) if j < 0 else j + len(closing)
        out.append((i, end))
        i = end
    return out


def possessor(value, spec):
    if value in spec['pronouns']:
        return True
    words = value.split(' ')
    if not 1 <= len(words) <= spec['max_space_separated_tokens'] or any(not w for w in words):
        return False
    if any(w.endswith(("'s", '’s', "s'", 's’')) for w in words[:-1]):
        return False
    last = words[-1]
    if last.endswith(("'s", '’s')):
        words[-1] = last[:-2]
    elif last.endswith(("s'", 's’')):
        words[-1] = last[:-1]
    else:
        return False
    for word in words:
        if not word or not any(ch.isalpha() for ch in word):
            return False
        if not word[0].isalpha() or not (word[-1].isalpha() or unicodedata.category(word[-1]).startswith('M')):
            return False
        if any(not (ch.isalpha() or unicodedata.category(ch).startswith('M') or ch in "'’-" ) for ch in word):
            return False
    return True


class Comparator:
    def __init__(self, payload, semantics):
        self.payload = payload
        self.semantics = semantics
        self.faces = {r['id']: r for r in payload['faces']}
        self.patterns = payload['patterns']
        self.forms = payload['form_sets']
        self.form_by_id = {r['id']: r for rows in self.forms.values() for r in rows}
        protection = semantics['literal_protection']
        self.protect_regexes = [re.compile(protection[k]) for k in ('existing_regex', 'extra_handles_regex', 'extra_number_regex')]
        self.number = re.compile(semantics['typed_number']['regex'])

    def protections(self, text, offsets):
        scopes, identifiers = [], []
        for index, regex in enumerate(self.protect_regexes):
            for match in regex.finditer(text):
                scope = [offsets[match.start()], offsets[match.end()]]
                scopes.append(scope)
                if index < 2:
                    identifiers.append(scope)
        scopes.extend([offsets[a], offsets[b]] for a, b in quoted_ranges(text))
        return sorted({tuple(r) for r in scopes}), {tuple(r) for r in identifiers}

    def parse(self, pattern, text, start, end, offsets, identifiers, words):
        # States retain complete named bindings. Never infer target text from a slot.
        states = [(start, {}, {}, {})]
        for item in pattern['parts']:
            nxt = []
            for position, ranges, bindings, form_ids in states:
                options = []
                kind = item['kind']
                if kind == 'literal':
                    options = [(item['value'], None)]
                elif kind == 'enum':
                    options = [(v, None) for v in item['values']]
                elif kind in ('morph', 'focus'):
                    options = [(r['surface'], r['id']) for r in self.forms[item['form_set']]]
                elif kind == 'typed':
                    for stop in range(position + 1, end + 1):
                        value = text[position:stop]
                        scope = (offsets[position], offsets[stop])
                        if scope[1] - scope[0] > item['max_utf16']:
                            break
                        if value.strip() != value or '\n' in value or '\r' in value:
                            continue
                        if sum(a >= scope[0] and b <= scope[1] for a, b in words) > item['max_words']:
                            continue
                        if item['type'] == 'possessor':
                            valid = possessor(value, self.semantics['typed_possessor'])
                        elif item['type'] == 'number':
                            valid = bool(self.number.fullmatch(value))
                        else:
                            valid = scope in identifiers
                        if valid:
                            options.append((value, None))
                for value, form_id in options:
                    stop = position + len(value)
                    if stop > end or not text.startswith(value, position):
                        continue
                    r = {**ranges, item['name']: [offsets[position], offsets[stop]]}
                    b = {**bindings, item['name']: value}
                    f = {**form_ids, **({item['name']: form_id} if form_id else {})}
                    nxt.append((stop, r, b, f))
                    if len(nxt) > 128:
                        return [], 'state_cap'
            states = nxt
            if not states:
                return [], None
        return [(r, b, f) for stop, r, b, f in states if stop == end], None

    @staticmethod
    def range_for(spec, context, ranges):
        if spec is None:
            return None
        if spec['kind'] == 'context':
            return list(context)
        if spec['kind'] == 'part':
            return ranges[spec['part']]
        return [ranges[spec['from']][0], ranges[spec['through']][1]]

    def recognize(self, row):
        text = row['text']
        offsets, inverse = cp_map(text)
        words = row['native_source_word_ranges_utf16']
        windows = row['native_window_ranges_utf16']
        protected, identifiers = self.protections(text, offsets)
        recognized, errors = [], []
        for pattern in self.patterns:
            if pattern['source_language'] != row['source_language']:
                continue
            # Necessary exact surface presence only; full parsing still decides matches.
            if any(p['kind'] == 'literal' and p['value'] not in text for p in pattern['parts']):
                continue
            if any(p['kind'] in ('focus', 'morph') and not any(f['surface'] in text for f in self.forms[p['form_set']]) for p in pattern['parts']):
                continue
            for a, b in windows:
                if a not in inverse or b not in inverse:
                    errors.append('invalid_native_utf16_geometry')
                    continue
                matches, error = self.parse(pattern, text, inverse[a], inverse[b], offsets, identifiers, words)
                if error:
                    errors.append(error)
                for ranges, bindings, forms in matches:
                    outputs = []
                    for out in pattern['approved_outputs']:
                        ids = self.form_by_id[forms[out['face_from_part']]]['face_ids'] if out['face_from_part'] else out['face_ids']
                        outputs.append({**out, 'source_range_utf16': self.range_for(out['scope'], [a, b], ranges), 'resolved_face_ids': ids})
                    recognized.append(dict(rule_id=pattern['id'], family=pattern['family'], arms=pattern['arms'],
                                           meaning_id=pattern['meaning_id'], context_range_utf16=[a, b], part_ranges_utf16=ranges,
                                           bindings_original=bindings, form_ids=forms, atomic_mode=pattern['atomicity']['mode'],
                                           atomic_range_utf16=self.range_for(pattern['atomicity']['scope'], [a, b], ranges),
                                           allowed_inner_output_ids=[o['id'] for o in outputs], outputs=outputs,
                                           record_sha256=pattern['record_sha256'], reason=pattern['atomicity']['reason'],
                                           priority=pattern['priority'], context_native_words=sum(x >= a and y <= b for x, y in words)))
        return recognized, protected, errors

    def candidates(self, row, recs, protected, language, arm):
        inherited = set(self.semantics['arm_inheritance'][arm])
        active = [r for r in recs if inherited.intersection(r['arms'])]
        masks = [r for r in active if r['atomic_range_utf16'] is not None]
        words = row['native_source_word_ranges_utf16']
        offsets, inverse = cp_map(row['text'])
        candidates = []
        for r in active:
            for out in r['outputs']:
                fid = out['resolved_face_ids'].get(language)
                if not fid:
                    continue
                candidates.append(dict(output_id=out['id'], face_id=fid, source_range_utf16=out['source_range_utf16'],
                                       concept_id=out['concept_id'], context_range_utf16=r['context_range_utf16'],
                                       context_native_words=r['context_native_words'], pattern_priority=r['priority'],
                                       rule_id=r['rule_id'], meaning_id=r['meaning_id'], kind='context_approved'))
        for fid in self.payload['fallback_entries']:
            face = self.faces[fid]
            if face['target_language'] != language:
                continue
            for scope in words:
                if row['text'][inverse[scope[0]]:inverse[scope[1]]] != face['source_form']:
                    continue
                candidates.append(dict(output_id='diagnostic:' + face['concept_id'], face_id=fid, source_range_utf16=scope,
                                       concept_id=face['concept_id'], context_range_utf16=scope, context_native_words=1,
                                       pattern_priority=-100, rule_id='diagnostic_generic_word', meaning_id='diagnostic:' + face['concept_id'],
                                       kind='diagnostic_generic_fallback'))
        admitted, rejected = [], []
        for c in candidates:
            scope, reason = c['source_range_utf16'], None
            face = self.faces[c['face_id']]
            contained = [(a, b) for a, b in words if a >= scope[0] and b <= scope[1]]
            c.update(target=face['target'], reading=face['reading'], native_cost=len(contained))
            if not contained or contained[0][0] != scope[0] or contained[-1][1] != scope[1] or any(overlap(scope, w) and not (w[0] >= scope[0] and w[1] <= scope[1]) for w in words):
                reason = 'native_whole_word_scope'
            elif scope[1] - scope[0] > 128:
                reason = 'unit_utf16_cap'
            elif any(overlap(scope, p) for p in protected):
                reason = 'protected_output'
            elif language == 'ja' and not c['reading']:
                reason = 'missing_required_reading'
            elif unicodedata.normalize('NFKC', row['text'][inverse[scope[0]]:inverse[scope[1]]]).casefold() == unicodedata.normalize('NFKC', face['target']).casefold():
                reason = 'unchanged_face'
            if reason is None:
                for m in masks:
                    if not overlap(scope, m['atomic_range_utf16']):
                        continue
                    permitted = m['atomic_mode'] != 'ambiguous' and any(o['id'] == c['output_id'] and o['source_range_utf16'] == scope for o in m['outputs'])
                    if not permitted:
                        reason = 'atomic_or_ambiguity_mask:' + m['rule_id']
                        break
            if reason is None and c['kind'] == 'context_approved':
                for other in active:
                    if other['meaning_id'] == c['meaning_id'] or not overlap(c['context_range_utf16'], other['context_range_utf16']):
                        continue
                    scopes = [o['source_range_utf16'] for o in other['outputs']]
                    if other['atomic_range_utf16']:
                        scopes.append(other['atomic_range_utf16'])
                    if any(overlap(scope, s) for s in scopes):
                        reason = 'competing_meaning:' + other['rule_id']
                        break
            if reason:
                rejected.append({**c, 'reason': reason})
            else:
                admitted.append(c)
        # Equivalent inherited exact/finite recognitions are distinct proofs, one output.
        admitted.sort(key=lambda c: (-c['context_native_words'], -(c['context_range_utf16'][1] - c['context_range_utf16'][0]),
                                     -c['pattern_priority'], -c['native_cost'], c['source_range_utf16'][0], c['output_id']))
        unique, seen = [], set()
        for c in admitted:
            key = (c['output_id'], c['face_id'], tuple(c['source_range_utf16']))
            if key not in seen:
                unique.append(c)
                seen.add(key)
        return unique, rejected

    @staticmethod
    def select(candidates, words, density, known):
        budget = max(1, math.floor(len(words) * density)) if words else 0
        selected, used, concepts = [], 0, set()
        for c in candidates:
            if c['concept_id'] in known or c['concept_id'] in concepts or used + c['native_cost'] > budget:
                continue
            if any(overlap(c['source_range_utf16'], old['source_range_utf16']) for old in selected):
                continue
            selected.append(c)
            used += c['native_cost']
            concepts.add(c['concept_id'])
        return selected, budget, used


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--geometry', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = args.output_dir / 'matches.jsonl'
    assert not out.exists(), 'Keep original output immutable; use a new output directory.'
    payload = json.loads((HERE / 'payload.json').read_text())
    semantics = json.loads((HERE / 'semantics.json').read_text())
    engine = Comparator(payload, semantics)
    summary = collections.defaultdict(lambda: dict(messages=0, raw_available=0, context_available=0,
                                                  changed_words=0, context_changed_words=0, source_words=0,
                                                  mean_depth_sum=0.0, concepts=set()))
    started = time.perf_counter()
    matched_ids, all_ids, families, errors = [], [], collections.Counter(), collections.Counter()
    raw_rows = 0
    with args.geometry.open() as src, out.open('w') as dest:
        for line in src:
            row = json.loads(line)
            all_ids.append(row['id'])
            recs, protected, row_errors = engine.recognize(row)
            errors.update(row_errors)
            for family in {r['family'] for r in recs}:
                families[family] += 1
            if recs:
                matched_ids.append(row['id'])
            tables, decisions = {}, {}
            n = len(row['native_source_word_ranges_utf16'])
            any_raw = False
            for language in ('sw', 'ja', 'es'):
                for arm in ('exact_top_down', 'existing_finite_slots', 'typed_slots_attested_morphology'):
                    candidates, rejected = engine.candidates(row, recs, protected, language, arm)
                    any_raw |= bool(candidates or rejected)
                    if candidates or rejected:
                        tables[language + '|' + arm] = dict(admitted=candidates, rejected=rejected)
                    for density in (0.1, 0.25, 0.5):
                        for snapshot, known in semantics['known_snapshots'].items():
                            selected, budget, changed = engine.select(candidates, row['native_source_word_ranges_utf16'], density, known)
                            contextual = [c for c in selected if c['kind'] == 'context_approved']
                            key = '|'.join((language, arm, str(density), snapshot))
                            metric = summary[key]
                            metric['messages'] += 1
                            metric['raw_available'] += bool(selected)
                            metric['context_available'] += bool(contextual)
                            metric['changed_words'] += changed
                            metric['context_changed_words'] += sum(c['native_cost'] for c in contextual)
                            metric['source_words'] += n
                            metric['mean_depth_sum'] += changed / n if n else 0
                            metric['concepts'].update(c['concept_id'] for c in selected)
                            if selected:
                                decisions[key] = [candidates.index(c) for c in selected]
            if recs or any_raw:
                raw_rows += 1
                dest.write(json.dumps(dict(id=row['id'], text=row['text'], source_language=row['source_language'],
                                           native_source_word_ranges_utf16=row['native_source_word_ranges_utf16'],
                                           protected_ranges_utf16=protected, recognitions=recs,
                                           candidate_tables=tables, decisions=decisions, errors=row_errors), ensure_ascii=False, separators=(',', ':')) + '\n')
    final = []
    for key, metric in sorted(summary.items()):
        language, arm, density, known = key.split('|')
        metric['distinct_concepts'] = len(metric['concepts'])
        metric['concepts'] = sorted(metric['concepts'])
        metric['mean_changed_depth'] = metric.pop('mean_depth_sum') / metric['messages']
        final.append(dict(language=language, arm=arm, density=float(density), known=known, **metric))
    result = dict(production=False, semantic_approval=False, provider_calls=0, source_messages=len(all_ids),
                  geometry_path=str(args.geometry), geometry_sha256=sha(args.geometry),
                  payload_sha256=sha(HERE / 'payload.json'), semantics_sha256=sha(HERE / 'semantics.json'),
                  comparator_sha256=sha(Path(__file__)), matched_context_messages=len(matched_ids),
                  matched_ids=matched_ids, raw_trace_rows=raw_rows, family_messages=dict(families),
                  parse_errors=dict(errors), elapsed_seconds=time.perf_counter() - started,
                  matches_sha256=sha(out), matches_bytes=out.stat().st_size, summary=final,
                  limitations=['Reused TRAIN and authored diagnostics, not fresh accuracy or population coverage.',
                               'Raw availability includes deliberately generic word controls and is NOT safe immersion coverage.',
                               'Context availability means recognized and structurally admitted, not independently reviewed meaning.',
                               'This independent Python implementation uses real native geometry but is not native runtime timing.',
                               'No full translation, existing reference-route capture or HFST is simulated by this reference script.'])
    (args.output_dir / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('source_messages', 'matched_context_messages', 'family_messages', 'parse_errors', 'elapsed_seconds', 'matches_bytes')}))


if __name__ == '__main__':
    main()
