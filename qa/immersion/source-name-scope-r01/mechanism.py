"""Narrow research exception; original records are never mutated."""
def rescued_link(match, source, target, guard):
    if not guard or guard['reason'] != 'name' or not guard['blocked'] or guard['target_blocked']:
        return False
    if source['pos'] != 'noun' or target['pos'] != 'noun': return False
    if not all(f['complete'] and f['mode'] in (1,2) for f in (source,target)): return False
    if source['number'] != target['number']: return False
    if set(source['reasons']) != {'dictionary_guard'} or target['reasons']: return False
    st=next(t for t in source['terms'] if t['term_id']==match['source_term_id'])
    tt=next(t for t in target['terms'] if t['term_id']==match['target_term_id'])
    if not all(t['eligible'] and t['explicit'] and not t['reasons'] for t in (st,tt)): return False
    assert st['sense_id']==tt['sense_id']==match['sense_id']
    assert match['source_pos']==source['pos'] and match['target_pos']==target['pos']
    assert match['source_number']==source['number'] and match['target_number']==target['number']
    assert set(match['reasons'])=={'dictionary_guard'} and not match['structural_eligible']
    return True

def occurrence_reasons(candidate):
    reasons=[]
    raw=candidate['role']['raw']
    if not raw or raw[0]!='NOUN': reasons.append('rescue_requires_actual_NOUN')
    if candidate['category']!='content': reasons.append('rescue_requires_content')
    if candidate['cost']!=1 or 'not_single_token_head' in candidate['filter_reasons']: reasons.append('rescue_requires_exact_single_token')
    if not candidate['source'].islower(): reasons.append('rescue_requires_lowercase_source')
    return reasons

def competition(heads):
    """Input is precompetition eligibility after all other frozen head guards."""
    geometries={}
    for ident,source,target in heads: geometries.setdefault(tuple(source),set()).add(tuple(target))
    return {ident for ident,source,target in heads if len(geometries[tuple(source)])>1}
