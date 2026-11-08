"""Indexed source-only candidate producer; research, not app activation.

Literal eligibility applies to every candidate path. Source POS metadata is
independent of target faces. This does not claim contextual sense certainty.
"""
import collections
from diagnose_editorial_guards_r02 import new_context, quoted_ranges
from editorial_common_roles_r01 import eligible
from evaluate_content_expansion_r01 import candidates as old_candidates
from evaluate_reviewed_words import WORD, PROTECTED, u16
from evaluate_role_content_r02 import choose


class SourceLookup:
    def __init__(self, baseline, candidate):
        self.baseline = baseline
        self.candidate = candidate
        self.roles = {w: set(p) for w, p in candidate['source_roles'].items()}
        self.noun_only = set(candidate['noun_only_sources'])
        self.entries = collections.defaultdict(list)
        for e in candidate['entries']:
            self.entries[e['language'], e['source']].append(e)

    def candidates(self, text, language, competing_attributive=False):
        tokens, old, _ = old_candidates(text, self.baseline, language)
        assert [(t.start(), t.end()) for t in tokens] == [(t.start(), t.end()) for t in WORD.finditer(text)]
        literals = quoted_ranges(text) + [(m.start(), m.end()) for m in PROTECTED.finditer(text)]
        contexts = [new_context(text, tokens, i, self.candidate['capitalized_homographs']) for i in range(len(tokens))]
        indices = {(t.start(), t.end()): i for i, t in enumerate(tokens)}
        rejected = []

        def admission(start, end, pos, category, source, form='canonical'):
            if any(a < end and start < b for a, b in literals):
                return False, 'protected_literal_scope_all_paths'
            if category != 'content':
                return True, 'inherited_function_guard'
            i = indices.get((start, end))
            if i is None:
                return False, 'content_unit_role_not_qualified'
            ctx = contexts[i]
            if ctx['common_rejection']:
                return False, ctx['common_rejection']
            after = ctx['after']
            if competing_attributive and pos == 'noun' and 'adj' in self.roles.get(source, set()) and after and 'noun' in self.roles.get(after[0], set()):
                return False, 'competing_attributive_role_experiment'
            if pos == 'noun' and source in self.noun_only:
                return True, 'inventory_noun_only_role'
            return eligible(ctx, pos, self.roles, form)

        accepted_old = []
        for span in old:
            source = span['original'].casefold().replace('’', "'")
            if span['category'] == 'content':
                span['concept_id'] = self.candidate['source_families'].get(source) or span['concept_id']
            allowed, reason = admission(span['start'], span['end'], span.get('pos', 'noun'), span['category'], source)
            if allowed:
                accepted_old.append(dict(span, shared_admission=reason))
            else:
                rejected.append(dict(span, rejected_reason=reason))
        added = []
        for i, token in enumerate(tokens):
            source = token.group().casefold().replace('’', "'")
            for e in self.entries.get((language, source), []):
                allowed, reason = admission(token.start(), token.end(), e['pos'], 'content', source, e['source_form_kind'])
                span = {'start': token.start(), 'end': token.end(), 'sourceStartUTF16': u16(text[:token.start()]),
                        'sourceEndUTF16': u16(text[:token.end()]), 'original': token.group(), 'translated': e['target'],
                        'reading': e['reading'], 'reading_kana': e['reading_kana'], 'category': 'content',
                        'pos': e['pos'], 'concept_id': e['concept_id'], 'lexicon_id': e['id'],
                        'train_rank': e['train_rank'], 'changed_source_words': 1, 'content_source_words': 1,
                        'source_kind': 'editorial_primary', 'guard': 'shared_' + e['pos'],
                        'shared_admission': reason, 'contextual_alternative_risk': e['contextual_alternative_risk']}
                if allowed:
                    added.append(span)
                else:
                    rejected.append(dict(span, rejected_reason=reason))
        existing = {(s['start'], s['end'], s['concept_id']) for s in accepted_old}
        added = [s for s in added if (s['start'], s['end'], s['concept_id']) not in existing]
        return tokens, accepted_old + added, rejected, literals

    def select(self, text, language, density, known='none', competing_attributive=False):
        tokens, spans, rejected, literals = self.candidates(text, language, competing_attributive)
        selected = choose(text, tokens, spans, density, known, self.candidate['learned_family_order'])
        assert all(not any(a < s['end'] and s['start'] < b for a, b in literals) for s in selected['spans'])
        return dict(selected, rejected_candidates=rejected, protected_ranges=literals, source_words=len(tokens))
