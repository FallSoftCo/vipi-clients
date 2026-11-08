#!/usr/bin/env python3
"""Bounded complete person/predicate lookup. Research only, no inferred target spans."""
import argparse
import json
from pathlib import Path
import re
import statistics
import time
from evaluate_source_concepts import candidates, select, sha, PROTECTED, u16

LEFT_AUXILIARIES=set("can could may might shall should will would do does did don't doesn't didn't must".split())
DETERMINERS=set("a an the my your his her our their this that these those some any each every no two three four five many several".split())
NP_FOLLOW=set("and or but that which who at in from with without for of to".split())


def clause_candidates(text,tokens,lexicon,policy):
    keys=[t.group().casefold().replace('’',"'") for t in tokens]
    protected=list(PROTECTED.finditer(text));found=[];rejected=[]
    nouns={r['source'] for r in lexicon['entries'] if r['pos']=='noun'}
    for entry in policy['entries']:
        parts=entry['source'].split()
        for i in range(len(tokens)-len(parts)+1):
            j=i+len(parts)
            if keys[i:j]!=parts:continue
            start,end=tokens[i].start(),tokens[j-1].end()
            before=text[:start].rstrip().rstrip('"\'“”‘’')
            initial=not before or before[-1] in '.!?'
            left=keys[i-1] if i and not text[tokens[i-1].end():start].strip() else None
            right=keys[j] if j<len(tokens) else None
            reason=None
            if any(m.start()<end and start<m.end() for m in protected):reason='protected_identifier_or_code'
            elif any(text[tokens[k].end():tokens[k+1].start()].strip() for k in range(i,j-1)):reason='noncontiguous_source_unit'
            elif any(t.group().isupper() and len(t.group())>1 for t in tokens[i:j]):reason='uppercase_identifier'
            elif left in LEFT_AUXILIARIES:reason='external_auxiliary_changes_finite_scope'
            elif entry.get('question') and not initial:reason='yes_no_unit_not_sentence_initial'
            elif right in entry.get('reject_right',[]):reason='unsupported_particle_or_reflexive'
            elif entry.get('allow_right') and right not in entry['allow_right']:reason='required_predicate_context_absent'
            elif entry.get('possession'):
                # Explicit small nominal context, not a general parse of every use of have.
                n=j+1 if right in DETERMINERS else j
                if n>=len(tokens) or keys[n] not in nouns:reason='possession_complete_noun_absent'
                elif n+1<len(tokens) and not any(ch in text[tokens[n].end():tokens[n+1].start()] for ch in ',.!?;') and keys[n+1] not in NP_FOLLOW:
                    reason='possession_following_scope_unqualified'
            span=dict(start=start,end=end,sourceStartUTF16=u16(text[:start]),sourceEndUTF16=u16(text[:end]),
                original=text[start:end],translated=entry['target'],category='content',pos='finite_clause',
                lexicon_id=entry['id'],train_rank=0,changed_source_words=len(parts),guard=entry.get('guard','complete_present_person_predicate'),
                source_person=entry['person'],source_tense='simple_present',target_form_evidence=entry['evidence_id'])
            (rejected if reason else found).append(dict(span,reason=reason) if reason else span)
    return found,rejected


def evaluate(case,lexicon,rules,policy):
    text=case['text'];tokens,words,rejections=candidates(text,lexicon,rules)
    clauses,blocked=clause_candidates(text,tokens,lexicon,policy)
    all_candidates=words+clauses
    control_mixed=select(text,tokens,words);control_whole=select(text,tokens,words,whole=True)
    mixed=select(text,tokens,all_candidates);whole=select(text,tokens,all_candidates,whole=True)
    arms=dict(control_mixed=control_mixed,control_union=control_mixed if control_mixed['spans'] else control_whole,
        clause_only_mixed=select(text,tokens,clauses),content_mixed=select(text,tokens,[s for s in all_candidates if s['category']=='content']),
        function_mixed=select(text,tokens,[s for s in all_candidates if s['category']=='function']),primary_mixed=mixed,
        combined25_mixed=select(text,tokens,all_candidates,one=False),whole_lexical=whole,
        primary_union=mixed if mixed['spans'] else whole)
    # Exact complete-clause credit takes precedence over a fragment when it covers the whole message.
    if whole['spans'] and whole['spans'][0]['pos']=='finite_clause':arms['primary_union']=whole
    return dict(case,source_words=len(tokens),candidates=all_candidates,rejections=rejections+blocked,arms=arms)


def main():
    p=argparse.ArgumentParser()
    for k in ('protocol','lexicon','rules','clauses','freeze','output'):p.add_argument('--'+k,type=Path,required=True)
    args=p.parse_args();start=time.perf_counter_ns()
    protocol,lexicon,rules,clauses,freeze=[json.loads(getattr(args,k).read_text()) for k in ('protocol','lexicon','rules','clauses','freeze')]
    assert sha(args.lexicon)==protocol['lexicon_sha256']==freeze['lexicon_sha256']
    assert sha(args.clauses)==freeze['clauses_sha256'] and sha(Path(__file__))==freeze['evaluator_sha256']
    assert sha(args.rules)==freeze['rules_sha256']
    init=(time.perf_counter_ns()-start)/1e6;rows=[];times=[]
    for case in protocol['cases']:
        start=time.perf_counter_ns();rows.append(evaluate(case,lexicon,rules,clauses));times.append((time.perf_counter_ns()-start)/1e6)
    result=dict(schema='vipi-source-clause-research-3',production=False,provider_calls=0,semantic_review='pending',
        boundary_source='QA Unicode English words, not native proof',input_hashes={str(getattr(args,k)):sha(getattr(args,k)) for k in ('protocol','lexicon','rules','clauses','freeze')},
        timing=dict(environment='system76 existing Python CPU, not mobile',initialization_ms=init,median_all_arms_ms=statistics.median(times),p95_all_arms_ms=sorted(times)[int(.95*len(times))-1]),
        summary={a:dict(messages_with_span=sum(bool(r['arms'][a]['spans']) for r in rows),mean_changed_depth=statistics.mean(r['arms'][a]['changed_depth'] for r in rows)) for a in rows[0]['arms']},rows=rows)
    assert not args.output.exists();args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result['summary'],indent=2))


if __name__=='__main__':main()
