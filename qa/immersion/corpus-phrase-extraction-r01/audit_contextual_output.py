#!/usr/bin/env python3
"""Independent actual-output geometry/count audit; no meaning verdicts."""
import collections
import gzip
import json
import math
import time
from pathlib import Path
from extract_pgv import OUT,sha,encoded

def overlap(a,b):return a[0]<b[1] and b[0]<a[1]

def main():
    start=time.monotonic();directory=OUT/'projection-r02/contextual'
    receipt=json.loads((directory/'receipt.json').read_text());assert receipt['complete']
    assert sha(directory/'rows.jsonl.gz')==receipt['outputs']['rows.jsonl.gz']['sha256']
    expected=json.loads((directory/'metrics.json').read_text());counts=collections.defaultdict(collections.Counter)
    budget_detail=collections.defaultdict(collections.Counter)
    distinct=collections.defaultdict(lambda:collections.defaultdict(set));rows=decisions=0
    with gzip.open(directory/'rows.jsonl.gz','rt') as stream:
        for line in stream:
            row=json.loads(line);raw=row['text'].encode('utf-16-le');words=row['native_words_utf16'];n=len(words)
            for pair,data in row['pairs'].items():
                for arm,density,known,index in data['decisions']:
                    d=data['decision_table'][index];selected=[data['candidates'][i] for i in d['selected_indices']]
                    assert d['budget']==max(1,math.floor(n*density));scopes=[];cost=0;concepts=set()
                    for c in selected:
                        a,b=c['focus_utf16'];inside=[w for w in words if a<=w[0]<w[1]<=b]
                        assert inside and inside[0][0]==a and inside[-1][1]==b
                        assert raw[2*a:2*b].decode('utf-16-le')==c['source']
                        assert len(inside)==c['cost'] and not c['identical_face']
                        assert not any(overlap([a,b],x) for x in scopes+row['protected_ranges_utf16'])
                        assert not any(m['utf16']!=[a,b] and m['utf16'][0]<=a and b<=m['utf16'][1] for m in row['source_masks'])
                        assert c['concept_id'] not in concepts
                        if known!='none':assert c['category']!='function'
                        concepts.add(c['concept_id']);scopes.append([a,b]);cost+=len(inside)
                    assert cost<=d['budget'];decisions+=1
                    for bin_name in ['all','short' if n<=5 else 'mid' if n<=12 else 'long']:
                        key='|'.join([pair,arm,str(density),known,bin_name]);c=counts[key]
                        c['messages']+=1;c['source_words']+=n;c['available_messages']+=bool(selected);c['changed_words']+=cost
                        c['content_anchor_messages']+=any(x['category']=='content' for x in selected)
                        c['function_only_messages']+=bool(selected) and all(x['category']=='function' for x in selected)
                        c['content_anchor_changed_words']+=sum(x['content_anchor_native_words'] for x in selected)
                        pre=[data['candidates'][i] for i in d['pre_budget_indices']]
                        multi=[x for x in pre if x['cost']>1]
                        bd=budget_detail[key]
                        bd['messages']+=1
                        bd['prebudget_multiword_available_messages']+=bool(multi)
                        bd['all_multiword_candidates_exceed_total_budget_messages']+=bool(multi) and all(x['cost']>d['budget'] for x in multi)
                        bd['multiword_available_but_only_single_words_selected_messages']+=bool(multi) and bool(selected) and all(x['cost']==1 for x in selected)
                        bd['prebudget_whole_message_lexical_scope_messages']+=any(x['cost']==n for x in pre)
                        bd['whole_message_lexical_scope_overbudget_messages']+=any(x['cost']==n and x['cost']>d['budget'] for x in pre)
                        for item in selected:
                            kind='lexical' if item['kind'] in ['heads_grow','r03_shared_guards'] else 'phrase'
                            distinct[key][kind].add(item['concept_id'])
                            distinct[key][kind+'_'+item['category']].add(item['concept_id'])
                            for word in item['content_anchor_words']:distinct[key]['source_content_surfaces'].add(word)
            rows+=1
    assert rows==9535
    for key,values in counts.items():
        for name,value in values.items():assert expected[key][name]==value,(key,name,value,expected[key][name])
    result=dict(complete=True,production=False,source_sha256=sha(directory/'rows.jsonl.gz'),compiler_sha256=sha(Path(__file__)),rows=rows,decision_count=decisions,
                seconds=time.monotonic()-start,claim='Actual selected source reconstruction, native cost, disjointness, literal/strict-containing mask protection, concept dedup, density and selected numeric totals verified. No semantic correctness claim.',
                knowledge_limit='Lexical family/source-vocabulary exhaustion; phrase IDs and source anchors are not proof of learned contextual senses.',
                budget_diagnostic={k:dict(v) for k,v in budget_detail.items()},
                distinct={k:{name:len(ids) for name,ids in groups.items()} for k,groups in distinct.items()})
    (directory/'independent-count-geometry-audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(encoded({k:v for k,v in result.items() if k not in ['distinct','budget_diagnostic']}))

if __name__=='__main__':main()
