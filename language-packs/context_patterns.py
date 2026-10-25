"""Finite source-context generalization, never target-text interpolation."""


def match_pattern(text, parts):
    if not isinstance(parts,list) or not 1 <= len(parts) <= 12:
        raise ValueError('Bounded context pattern required')
    if sum('focus' in x for x in parts if isinstance(x,dict)) != 1:
        raise ValueError('Exactly one lexical focus required')
    if not any(isinstance(x,dict) and isinstance(x.get('literal'),str) and x['literal'].strip() for x in parts):
        raise ValueError('Context literal required')
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
