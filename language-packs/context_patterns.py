"""Finite source-context generalization, never target-text interpolation."""


def match_pattern(text, parts):
    if not isinstance(parts,list) or not 1 <= len(parts) <= 12:
        raise ValueError('Bounded context pattern required')
    if sum('focus' in x for x in parts if isinstance(x,dict)) != 1:
        raise ValueError('Exactly one lexical focus required')
    if not any(isinstance(x,dict) and (
        isinstance(x.get('literal'),str) and x['literal'].strip() or
        isinstance(x.get('slot'),list) and x['slot'] and all(isinstance(v,str) and v.strip() for v in x['slot'])) for x in parts):
        raise ValueError('Explicit nonempty context required')
    states={(0,None)}
    for part in parts:
        if not isinstance(part,dict) or len(part)!=1 or next(iter(part)) not in ('literal','slot','focus'):
            raise ValueError('Explicit literal, slot or focus required')
        kind,value=next(iter(part.items()))
        alternatives=value if kind=='slot' else [value]
        if (not isinstance(alternatives,list) or not 1 <= len(alternatives) <= 32 or
            any(not isinstance(x,str) or not 0 < len(x.encode('utf-16-le'))//2 <= (128 if kind=='focus' else 256) for x in alternatives)):
            raise ValueError('Bounded finite alternatives required')
        next_states=set()
        for offset,focus in states:
            for value in alternatives:
                if text.startswith(value,offset):
                    end=offset+len(value)
                    next_states.add((end,(offset,end) if kind=='focus' else focus))
                    if len(next_states)>128: raise ValueError('Ambiguous pattern exceeds bound')
        states=next_states
    focuses={focus for offset,focus in states if offset==len(text)}
    return next(iter(focuses)) if len(focuses)==1 else None


def validate_pattern(record):
    pattern=record['usage'].get('context_pattern')
    if pattern is None: return
    focus=match_pattern(record['source_context'],pattern)
    if focus!=tuple(record['source_span']):
        raise ValueError('Pattern must recover the exact authored source focus')
    if next(x['focus'] for x in pattern if 'focus' in x)!=record['source']:
        raise ValueError('Pattern cannot alter lexical focus')


def frame_parts(record,side):
    """An explicitly bounded local frame inside the retained full reference."""
    usage=record['usage'];text=record[side+'_context'];focus=record[side+'_span']
    span=usage.get(side+'_frame_span')
    if (not isinstance(span,list) or len(span)!=2 or any(type(i) is not int for i in span)
        or not 0<=span[0]<=focus[0]<focus[1]<=span[1]<=len(text)):
        raise ValueError('Explicit frame must contain the lexical focus')
    fragment=text[span[0]:span[1]];a,b=focus[0]-span[0],focus[1]-span[0]
    if len(fragment.encode('utf-16-le'))//2>256:raise ValueError('Frame exceeds native window bound')
    parts=usage.get(side+'_frame_pattern')
    if usage.get('lexical_unit') is True:
        expected=[{'focus':record[side]}]
        if span!=focus or parts!=expected or fragment!=record[side] or not fragment.strip():
            raise ValueError('A lexical unit must be the entire exact assessed focus')
        return expected
    if parts is None:
        parts=([{'literal':fragment[:a]}] if a else [])+[{'focus':record[side]}]
        if b<len(fragment):parts.append({'literal':fragment[b:]})
    if match_pattern(fragment,parts)!=(a,b) or next(x['focus'] for x in parts if 'focus' in x)!=record[side]:
        raise ValueError('Frame cannot alter lexical focus')
    return parts


def validate_frames(record):
    usage=record['usage'];extent=usage.get('context_extent','exact_context')
    if 'lexical_unit' in usage and type(usage['lexical_unit']) is not bool:
        raise ValueError('Lexical unit scope must be explicit')
    if extent not in ('exact_context','local_phrase'):raise ValueError('Unknown context extent')
    if extent=='exact_context':
        if usage.get('lexical_unit'):raise ValueError('Lexical units require assessed local scope')
        if any(k in usage for k in ('source_frame_span','target_frame_span','source_frame_pattern','target_frame_pattern')):
            raise ValueError('Phrase scopes require explicit local extent')
        return
    if not isinstance(usage.get('permitted_context'),str) or not usage['permitted_context'].strip():
        raise ValueError('Permitted surrounding context must be stated')
    exclusions=usage.get('abstain_when')
    if not isinstance(exclusions,list) or not 1<=len(exclusions)<=16 or any(not isinstance(x,str) or not x.strip() for x in exclusions):
        raise ValueError('Frame abstention limits must be stated')
    for side in ('source','target'):frame_parts(record,side)
