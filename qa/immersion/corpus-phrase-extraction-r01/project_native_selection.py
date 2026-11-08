#!/usr/bin/env python3
"""Pure research projection/selection over retained native UTF16 geometry.

No dictionaries, corpus files, models or semantic labels are read. The caller
binds text through project_scope before select (whose API intentionally has no
text parameter), and computes identical_face from its frozen top-overall target.
This module never searches another target when that face is identical.
"""
import math

KNOWN_LIMITS = {'none': None, 'all_function': 0, 'all_function_global50': 50,
                'all_function_global100': 100, 'all_function_global300': 300}
CATEGORIES = {'content': 0, 'unresolved': 1, 'function': 2}


def _range(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError('range must contain two UTF16 offsets')
    a, b = value
    if not all(isinstance(n, int) and not isinstance(n, bool) for n in value) or not 0 <= a < b:
        raise ValueError('range must be a nonempty nonnegative integer interval')
    return a, b


def _words(supplied):
    if not isinstance(supplied, (list, tuple)):
        raise ValueError('native word ranges must be a sequence')
    result, end = [], 0
    for value in supplied:
        a, b = _range(value)
        if a < end:
            raise ValueError('native word ranges must be ordered and nonoverlapping')
        result.append((a, b)); end = b
    return result


def _overlap(a, b):
    return max(a[0], b[0]) < min(a[1], b[1])


def _cost(focus, words):
    inside = [word for word in words if _overlap(focus, word)]
    if not inside:
        return None, 'no_native_words'
    if any(word[0] < focus[0] or word[1] > focus[1] for word in inside):
        return None, 'partial_native_word'
    if inside[0][0] != focus[0] or inside[-1][1] != focus[1]:
        return None, 'not_exact_native_boundaries'
    return len(inside), None


def project_scope(text, native_words_utf16, focus_utf16):
    """Return exact original codepoint scope/native cost, or explicit rejection.

    Native word ranges are authoritative; no Latin retokenization or source
    normalization occurs. UTF16 boundaries splitting a surrogate pair fail.
    """
    if not isinstance(text, str):
        return {'rejection': 'invalid_original_text'}
    try:
        raw = text.encode('utf-16-le')
        words, focus = _words(native_words_utf16), _range(focus_utf16)
    except (ValueError, UnicodeError):
        return {'rejection': 'invalid_text_or_geometry'}
    positions, offset = {0: 0}, 0
    for cp, char in enumerate(text, 1):
        offset += len(char.encode('utf-16-le')) // 2
        positions[offset] = cp
    if any(a not in positions or b not in positions for a, b in words + [focus]):
        return {'rejection': 'outside_text_or_split_surrogate'}
    cost, rejection = _cost(focus, words)
    if rejection:
        return {'rejection': rejection}
    a, b = positions[focus[0]], positions[focus[1]]
    if raw[focus[0] * 2:focus[1] * 2].decode('utf-16-le') != text[a:b]:
        return {'rejection': 'original_reconstruction_failed'}
    return {'cost': cost, 'codepoints': [a, b]}


def select(candidates, native_words_utf16, protected_ranges_utf16, source_masks,
           density, known, learned_family_order):
    """Select indices, preserving independent masks through all arm filters.

    Candidates must already use the frozen top-overall target choice. Records
    are not mutated. pre_budget_indices are sorted eligible candidates before
    disjoint/concept packing; budget_only_indices are that subset whose focus
    cost exceeds the TOTAL budget, not merely its remaining portion. Selected
    indices retain ranking order, not source order. There is no correctness or
    useful-learning credit here; category is an explicit caller classification.

    Contract masks veto strictly contained focus scopes on every arm; equal
    scopes are allowed. Crossing/noncontaining overlaps are NOT an additional
    atomic policy silently introduced by this historical comparison helper.
    """
    if not isinstance(candidates, (list, tuple)):
        raise ValueError('candidates must be an indexed sequence')
    words = _words(native_words_utf16)
    protected = [_range(value) for value in protected_ranges_utf16]
    masks = []
    for mask in source_masks:
        if not isinstance(mask, dict) or not isinstance(mask.get('unit_id'), str) or not mask['unit_id']:
            raise ValueError('source masks require immutable unit identity')
        masks.append(_range(mask['utf16']))
    if isinstance(density, bool) or not isinstance(density, (int, float)) or not math.isfinite(density) or not 0 < density <= 1:
        raise ValueError('density must be finite and in (0,1]')
    if known not in KNOWN_LIMITS:
        raise ValueError('unknown frozen knowledge snapshot')
    if not isinstance(learned_family_order, (list, tuple)) or any(not isinstance(x, str) or not x for x in learned_family_order):
        raise ValueError('learned family order must contain nonempty IDs')
    if len(set(learned_family_order)) != len(learned_family_order):
        raise ValueError('learned family order must not repeat IDs')
    limit = KNOWN_LIMITS[known]
    learned = set(learned_family_order[:limit]) if limit else set()
    budget = max(1, math.floor(len(words) * density))
    admitted, rejected, costs, contexts, ranges = [], {}, {}, {}, {}
    for index, candidate in enumerate(candidates):
        reasons = []
        try:
            focus, context = _range(candidate['focus_utf16']), _range(candidate['context_utf16'])
            if not context[0] <= focus[0] < focus[1] <= context[1]:
                reasons.append('focus_outside_context')
            cost, focus_error = _cost(focus, words)
            context_cost, context_error = _cost(context, words)
            if focus_error: reasons.append('focus_' + focus_error)
            if context_error: reasons.append('context_' + context_error)
            if not isinstance(candidate['id'], str) or not candidate['id']:
                reasons.append('invalid_candidate_id')
            if not isinstance(candidate['concept_id'], str) or not candidate['concept_id']:
                reasons.append('invalid_concept_id')
            if candidate['category'] not in CATEGORIES:
                reasons.append('invalid_category')
            if not isinstance(candidate['train_rank'], int) or isinstance(candidate['train_rank'], bool) or candidate['train_rank'] < 0:
                reasons.append('invalid_train_rank')
            if not isinstance(candidate['target'], str) or not candidate['target'].strip():
                reasons.append('empty_or_invalid_target')
            if not isinstance(candidate['identical_face'], bool):
                reasons.append('invalid_identity_flag')
            elif candidate['identical_face']:
                reasons.append('identical_face')
            knowledge = candidate['knowledge_ids']
            if not isinstance(knowledge, (list, tuple)) or any(not isinstance(x, str) or not x for x in knowledge):
                reasons.append('invalid_knowledge_ids')
            else:
                if limit is not None and candidate['category'] == 'function': reasons.append('known_function')
                if limit and knowledge and all(value in learned for value in knowledge): reasons.append('known_vocabulary')
            if any(_overlap(focus, scope) for scope in protected): reasons.append('protected_focus')
            if any(scope != focus and scope[0] <= focus[0] and focus[1] <= scope[1] for scope in masks):
                reasons.append('inside_recognized_source_unit')
        except (KeyError, TypeError, ValueError):
            reasons.append('malformed_candidate')
        if reasons:
            rejected[index] = sorted(set(reasons))
        else:
            admitted.append(index); costs[index] = cost; contexts[index] = context_cost; ranges[index] = focus
    admitted.sort(key=lambda i: (-contexts[i], CATEGORIES[candidates[i]['category']], candidates[i]['train_rank'],
                                  -costs[i], ranges[i][0], candidates[i]['id']))
    over_total = [i for i in admitted if costs[i] > budget]
    selected, occupied, concepts, remaining = [], [], set(), budget
    for i in admitted:
        reasons = []
        if candidates[i]['concept_id'] in concepts: reasons.append('repeated_concept')
        if any(_overlap(ranges[i], scope) for scope in occupied): reasons.append('overlapping_selected_focus')
        if costs[i] > budget: reasons.append('over_total_budget')
        elif costs[i] > remaining: reasons.append('exceeds_remaining_budget')
        if reasons:
            rejected[i] = reasons
            continue
        selected.append(i); occupied.append(ranges[i]); concepts.add(candidates[i]['concept_id']); remaining -= costs[i]
    return dict(selected_indices=selected, rejected=[dict(index=i, reasons=rejected[i]) for i in sorted(rejected)],
                budget=budget, pre_budget_indices=admitted, budget_only_indices=over_total)


def _self_test():
    import copy
    import unittest

    class Controls(unittest.TestCase):
        def candidate(self, ident, focus, context=None, category='content', concept=None, knowledge=None, identical=False, rank=0):
            return dict(id=ident, focus_utf16=focus, context_utf16=context or focus, target='target-' + ident,
                        identical_face=identical, category=category, concept_id=concept or ident,
                        knowledge_ids=knowledge if knowledge is not None else [concept or ident], train_rank=rank)

        def choose(self, candidates, words, masks=(), protected=(), density=.5, known='none', order=()):
            return select(candidates, words, protected, masks, density, known, order)

        def test_original_astral_and_native_boundaries(self):
            text = 'a😀b red car'; words = [[0, 4], [5, 8], [9, 12]]
            self.assertEqual(project_scope(text, words, [0, 8]), {'cost': 2, 'codepoints': [0, 7]})
            self.assertEqual(project_scope(text, words, [5, 12]), {'cost': 2, 'codepoints': [4, 11]})
            self.assertEqual(project_scope(text, words, [2, 4])['rejection'], 'outside_text_or_split_surrogate')
            self.assertEqual(project_scope(text, words, [1, 4])['rejection'], 'partial_native_word')
            self.assertIn('rejection', project_scope(text, [[0, 5], [4, 8]], [0, 8]))

        def test_no_new_128_unit_cap_or_normalization(self):
            text = 'a' * 150
            self.assertEqual(project_scope(text, [[0, 150]], [0, 150]), {'cost': 1, 'codepoints': [0, 150]})
            self.assertEqual(project_scope('café', [[0, 5]], [0, 4])['rejection'], 'partial_native_word')

        def test_compound_mask_survives_known_and_overbudget_across_arms(self):
            words = [[0, 7], [8, 13], [14, 19]]
            candidates = [self.candidate('compound', [0, 13], knowledge=['known']),
                          self.candidate('head', [8, 13]), self.candidate('editorial', [0, 7]), self.candidate('safe', [14, 19])]
            mask = [dict(unit_id='country-music', utf16=[0, 13])]
            before = copy.deepcopy((candidates, mask))
            for known, order in [('none', []), ('all_function_global50', ['known'])]:
                result = self.choose(candidates, words, mask, density=.25, known=known, order=order)
                self.assertEqual(result['selected_indices'], [3])
                reasons = {r['index']: r['reasons'] for r in result['rejected']}
                self.assertIn('inside_recognized_source_unit', reasons[1]); self.assertIn('inside_recognized_source_unit', reasons[2])
            self.assertEqual((candidates, mask), before)

        def test_identical_top_target_has_no_credit_or_alternate_search(self):
            c = self.candidate('same', [0, 5], identical=True)
            result = self.choose([c], [[0, 5]])
            self.assertEqual(result['selected_indices'], [])
            self.assertEqual(result['pre_budget_indices'], [])
            self.assertEqual(result['rejected'][0]['reasons'], ['identical_face'])
            self.assertEqual(c['target'], 'target-same')

        def test_protected_context_allowed_but_protected_focus_rejected(self):
            words = [[0, 3], [4, 8], [9, 12]]
            candidates = [self.candidate('safe', [9, 12], [0, 12]), self.candidate('unsafe', [4, 8], [0, 12])]
            result = self.choose(candidates, words, protected=[[0, 8]], density=1)
            self.assertEqual(result['selected_indices'], [0])
            self.assertIn('protected_focus', result['rejected'][0]['reasons'])

        def test_known_all_nonempty_ids_and_category(self):
            words = [[0, 1], [2, 3], [4, 5], [6, 7]]
            cs = [self.candidate('function', words[0], category='function'),
                  self.candidate('all-known', words[1], knowledge=['a', 'b']),
                  self.candidate('part-known', words[2], knowledge=['a', 'new']),
                  self.candidate('empty', words[3], knowledge=[])]
            result = self.choose(cs, words, density=1, known='all_function_global50', order=['a', 'b'])
            self.assertEqual(result['selected_indices'], [2, 3])
            self.assertEqual(self.choose(cs, words, density=1, known='all_function')['selected_indices'], [1, 2, 3])

        def test_total_and_remaining_budget_misses_distinguished(self):
            words = [[0, 1], [2, 3], [4, 5], [6, 7], [8, 9], [10, 11]]
            cs = [self.candidate('three', [0, 5], [0, 11]), self.candidate('one', [0, 1], [0, 9]),
                  self.candidate('two', [6, 9], [2, 11], rank=1)]
            result = self.choose(cs, words, density=.34)
            self.assertEqual(result['budget'], 2); self.assertEqual(result['budget_only_indices'], [0])
            self.assertEqual(result['selected_indices'], [1])
            reasons = {r['index']: r['reasons'] for r in result['rejected']}
            self.assertIn('over_total_budget', reasons[0]); self.assertEqual(reasons[2], ['exceeds_remaining_budget'])

        def test_ranking_disjoint_repeat_and_native_count(self):
            words = [[0, 1], [2, 3], [4, 5], [6, 7], [8, 9]]
            cs = [self.candidate('function-long', [0, 1], [0, 9], category='function'),
                  self.candidate('content', [2, 3], [0, 7], concept='same'),
                  self.candidate('repeated', [4, 5], [0, 7], concept='same', rank=1),
                  self.candidate('overlap', [2, 5], [2, 7], rank=2)]
            result = self.choose(cs, words, density=1)
            self.assertEqual(result['selected_indices'], [0, 1])
            reasons = {r['index']: r['reasons'] for r in result['rejected']}
            self.assertIn('repeated_concept', reasons[2]); self.assertIn('overlapping_selected_focus', reasons[3])
            self.assertEqual(self.choose([], words, density=.25)['budget'], 1)

        def test_equal_scope_allowed_crossing_not_silently_atomic(self):
            words = [[0, 1], [2, 3], [4, 5]]; mask = [dict(unit_id='m', utf16=[0, 3])]
            equal = self.choose([self.candidate('equal', [0, 3])], words, mask, density=1)
            crossing = self.choose([self.candidate('crossing', [2, 5])], words, mask, density=1)
            self.assertEqual(equal['selected_indices'], [0]); self.assertEqual(crossing['selected_indices'], [0])

        def test_input_failures_explicit_and_partial_candidate_rejected(self):
            with self.assertRaises(ValueError): self.choose([], [[0, 2], [1, 3]])
            with self.assertRaises(ValueError): self.choose([], [[0, 2]], density=float('nan'))
            with self.assertRaises(ValueError): self.choose([], [[0, 2]], order=['same', 'same'])
            result = self.choose([self.candidate('partial', [1, 3])], [[0, 3]])
            self.assertEqual(result['selected_indices'], [])
            self.assertIn('focus_partial_native_word', result['rejected'][0]['reasons'])

    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    import sys
    if sys.argv[1:] != ['--self-test']:
        raise SystemExit('Import project_scope/select, or use --self-test; no corpus runner is provided.')
    raise SystemExit(_self_test())
