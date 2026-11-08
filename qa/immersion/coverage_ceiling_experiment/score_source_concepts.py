#!/usr/bin/env python3
"""Score frozen selected scopes; hits alone are not semantic coverage."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import statistics


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scope_id(case,span):
    return hashlib.sha256((case+':'+str(span['sourceStartUTF16'])+':'+str(span['sourceEndUTF16'])+':'+span['translated']).encode()).hexdigest()[:16]


def main():
    p=argparse.ArgumentParser()
    for key in ('capture','review','freeze','output'):
        p.add_argument('--'+key,type=Path,required=True)
    args=p.parse_args()
    capture,review,freeze=[json.loads(getattr(args,k).read_text()) for k in ('capture','review','freeze')]
    labels={(r['id'],s['scope_id']):s['label'] for r in review['rows'] for s in r['labels']}
    arms=list(capture['rows'][0]['arms'])
    results={}
    for arm in arms:
        groups=collections.defaultdict(list)
        for row in capture['rows']:
            spans=row['arms'][arm]['spans']
            ls=[labels[(row['id'],scope_id(row['id'],s))] for s in spans]
            item=dict(id=row['id'],useful=bool(spans),clean=bool(spans) and all(x in ('correct','minor') for x in ls),
                material=any(x in ('material_error','wrong_scope') for x in ls),uncertain='uncertain' in ls,
                correct_depth=sum(s['changed_source_words'] for s,l in zip(spans,ls) if l in ('correct','minor'))/row['source_words'] if row['source_words'] else 0,
                content=any(s['category']=='content' for s in spans),function=any(s['category']=='function' for s in spans),
                lexical_ids=[s['lexicon_id'] for s in spans])
            groups['all'].append(item);groups[row['sampling_length_bin']].append(item)
        results[arm]={group:dict(messages=len(rows),clean_useful=sum(x['clean'] for x in rows),with_candidate=sum(x['useful'] for x in rows),material_error_messages=sum(x['material'] for x in rows),uncertain_messages=sum(x['uncertain'] for x in rows),mean_correct_depth=statistics.mean(x['correct_depth'] for x in rows),content_messages=sum(x['content'] for x in rows),function_messages=sum(x['function'] for x in rows),selected_lexicon_ids=dict(collections.Counter(y for x in rows for y in x['lexical_ids']))) for group,rows in groups.items()}
    gate=freeze['research_advance_only']
    passed=(results['primary_union']['all']['clean_useful']>=gate['primary_clean_useful_at_least'] and results['primary_union']['all']['material_error_messages']<=gate['primary_material_or_scope_errors_at_most'] and results['content_mixed']['all']['clean_useful']>=gate['content_clean_useful_at_least'])
    control={r['id'] for r in capture['rows'] if r['arms']['control_mixed']['spans']}
    primary={r['id'] for r in capture['rows'] if r['arms']['primary_union']['spans']}
    output=dict(schema='vipi-source-concept-decision-2',production=False,gate_passed=passed,semantic_review_type='Author review; independent subset is retained separately; not native bilingual certification.',input_hashes={str(getattr(args,k)):sha(getattr(args,k)) for k in ('capture','review','freeze')},results=results,paired_newly_available=sorted(primary-control),paired_lost=sorted(control-primary),whole_credit='Whole lexical scopes are scored separately and union is deduplicated. No unreviewed whole MT is credited.',limitations=['80 sampled crowdsourced persona-conversation messages, not a population or real-user outcome estimate.','Mean depth is macro-averaged per message including zeros. Length strata reported explicitly.','No inference and no native integration. Python timing is not mobile timing.'])
    assert not args.output.exists();args.output.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(gate_passed=passed,summary={a:{g:{k:v for k,v in r.items() if k!='selected_lexicon_ids'} for g,r in rr.items()} for a,rr in results.items()}),indent=2))


if __name__=='__main__':main()
