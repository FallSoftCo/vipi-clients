#!/usr/bin/env python3
"""Freeze deterministic contextual review scopes without semantic judgments."""
import collections
import gzip
import hashlib
import itertools
import json
import sqlite3
from pathlib import Path
from extract_pgv import OUT,HERE,sha,encoded
from project_contextual import mixed

def main():
    directory=OUT/'projection-r02';source=directory/'contextual'
    policy=json.loads((HERE/'contextual-review-selection-r01.json').read_text())
    receipt=json.loads((source/'receipt.json').read_text());assert receipt['complete'] and receipt['rows']==9535
    assert sha(source/'rows.jsonl.gz')==receipt['outputs']['rows.jsonl.gz']['sha256']
    pools=collections.defaultdict(lambda:collections.defaultdict(list));all_count=0
    with gzip.open(source/'rows.jsonl.gz','rt') as stream:
        for line in stream:
            row=json.loads(line)
            for pair,data in row['pairs'].items():
                for arm,density,known,decision in data['decisions']:
                    if arm not in policy['arms'] or density!=.25 or known!='none':continue
                    choice=data['decision_table'][decision]
                    selected=[data['candidates'][i] for i in choice['selected_indices']]
                    for candidate_index,candidate in zip(choice['selected_indices'],selected,strict=True):
                        scope_key=encoded([row['id'],pair,candidate['focus_utf16'],candidate['target']])
                        rank=hashlib.sha256((policy['seed']+'|'+scope_key).encode()).hexdigest()
                        c=candidate['cost'];length='1' if c==1 else '2-3' if c<=3 else '4-8'
                        boundary='head' if candidate['kind']=='heads_grow' else 'expanded' if candidate.get('expanded_observations',0) else 'minimal'
                        stratum=(min(3,candidate['train_rank']//2000),length,boundary,'multiple' if candidate.get('alternatives',1)>1 else 'one')
                        item=dict(case_id=row['id'],pair=pair,arm=arm,candidate_index=candidate_index,candidate_id=candidate['id'],
                                  stratum=list(stratum),sampling_hash=rank,scope_identity=scope_key)
                        pools[pair,arm][stratum].append(item);all_count+=1
    for strata in pools.values():
        for rows in strata.values():rows.sort(key=lambda r:r['sampling_hash'])
    possible_strata=list(itertools.product(range(4),['1','2-3','4-8'],['head','expanded','minimal'],['one','multiple']))
    empty_strata={pair+'|'+arm:[list(v) for v in possible_strata if not pools[pair,arm].get(v)] for pair in policy['targets'] for arm in policy['arms']}
    chosen=[];seen=set();selection_counts=collections.Counter();shortages=[]
    ordered=[(pair,arm) for pair in policy['targets'] for arm in policy['arms']]
    def take(key,need,unique_case):
        picked=[];cases=set();strata=pools[key]
        while len(picked)<need:
            progress=False
            for stratum in sorted(strata):
                queue=strata[stratum]
                eligible=next((i for i,r in enumerate(queue) if r['scope_identity'] not in seen and (not unique_case or r['case_id'] not in cases)),None)
                if eligible is None:continue
                row=queue.pop(eligible);seen.add(row['scope_identity']);cases.add(row['case_id']);picked.append(row);progress=True
                if len(picked)==need:break
            if not progress:break
        chosen.extend(picked);selection_counts['|'.join(key)]+=len(picked)
        return len(picked)
    for key in ordered:
        n=take(key,policy['quota'],True)
        if n<policy['quota']:shortages.append(dict(pair=key[0],arm=key[1],selected=n,quota=policy['quota']))
    while len(chosen)<policy['count']:
        progress=False
        for key in ordered:
            progress=bool(take(key,1,False)) or progress
            if len(chosen)==policy['count']:break
        if not progress:break
    assert len(chosen)==96
    evidence_dir=source/'review';evidence_dir.mkdir(exist_ok=False)
    selection=dict(production=False,semantic_labels_present=False,policy_sha256=sha(HERE/'contextual-review-selection-r01.json'),
                   source_rows_sha256=sha(source/'rows.jsonl.gz'),selected=[dict(case_id=r['case_id'],pair=r['pair'],arm=r['arm'],candidate_id=r['candidate_id'],sampling_hash=r['sampling_hash']) for r in chosen],
                   counts=selection_counts,shortages=shortages,candidate_occurrences_across_arms=all_count,empty_strata=empty_strata,
                   expansion_label_clarification='Frozen stratum label expanded means the aggregate variant has expansion evidence; it does not establish that the retained first example was expanded. Selection keys/order unchanged.')
    (evidence_dir/'selection-freeze.json').write_text(json.dumps(selection,indent=2)+'\n')
    # Selection is already frozen. Rehydrate only96 scopes in a second stream,
    # rather than retaining every full candidate/mask/selected-list in RAM.
    wanted=collections.defaultdict(list)
    for index,r in enumerate(chosen):wanted[r['case_id']].append(index)
    with gzip.open(source/'rows.jsonl.gz','rt') as stream:
        for line in stream:
            row=json.loads(line)
            if row['id'] not in wanted:continue
            for index in wanted[row['id']]:
                r=chosen[index];data=row['pairs'][r['pair']];candidate=data['candidates'][r['candidate_index']]
                assert candidate['id']==r['candidate_id']
                decision=next(i for arm,density,known,i in data['decisions'] if arm==r['arm'] and density==.25 and known=='none')
                selected=[data['candidates'][i] for i in data['decision_table'][decision]['selected_indices']]
                r.update(source=row['text'],candidate=candidate,selected_in_arm=selected,mixed_output=mixed(row['text'],selected),native_words_utf16=row['native_words_utf16'],source_masks=row['source_masks'],protected_ranges_utf16=row['protected_ranges_utf16'])
    needed={(r['pair'],r['candidate'].get('catalog_id')) for r in chosen if r['candidate'].get('catalog_id')}
    catalogs={}
    for name in ['catalog.jsonl.gz','heads-r02/heads-catalog.jsonl.gz']:
        with gzip.open(directory/name,'rt') as stream:
            for line in stream:
                r=json.loads(line)
                if (r['pair'],r['catalog_id']) in needed:
                    catalogs[r['pair'],r.get('proof_id',r['catalog_id'])]=r
    pair_ids={r['pair_id'] for r in catalogs.values()};pairs={}
    with gzip.open(directory/'selected-pair-evidence.jsonl.gz','rt') as stream:
        for line in stream:
            r=json.loads(line)
            if r['pair_id'] in pair_ids:pairs[r['pair_id']]=r
    corpus=OUT.parent/'bst-evaluation-source-r01/train.json'
    conversations=json.loads(corpus.read_text());contexts={}
    for ci,c in enumerate(conversations):
        if c['context_dataset']!='convai2':continue
        for ti,(speaker,text) in enumerate(c['dialog']):
            if speaker==0 and text.strip():contexts[f'bst-train-{ci:04d}-{ti:02d}']=c['dialog'][:ti]
    db=sqlite3.connect((OUT/'phrases/candidates.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True);db.row_factory=sqlite3.Row
    full=[];compact=[]
    for number,row in enumerate(chosen,1):
        candidate=row['candidate'];key=(row['pair'],candidate.get('id','').split('@')[0])
        cat=catalogs.get(key);proof=None;alternatives=[]
        if cat:
            proof=pairs[cat['pair_id']]
            alternatives=[dict(r) for r in db.execute('SELECT id,target_key,distinct_components,mean_lexical_score,expanded_observations,example_pair_index,source_start,source_end,target_start,target_end FROM ranked WHERE pair=? AND arm=? AND source_key=? ORDER BY distinct_components DESC,mean_lexical_score DESC,id LIMIT 12',(cat['pair'],cat['arm'],cat['source_key']))]
        ident=f'corpus-context-{number:03d}'
        prior=contexts[row['case_id']]
        record=dict(review_id=ident,**row,review_only_preceding_context=prior,
                    catalog_record=cat,original_parallel_pair=proof,top_ranked_context_alternatives=alternatives,
                    review_limits='Prior dialogue is unavailable to matcher. Target alternatives are proposals. Dictionary corroboration is not meaning approval. R03 is a research control. No verdict in this packet.')
        full.append(record)
        compact.append(dict(review_id=ident,case_id=row['case_id'],pair=row['pair'],arm=row['arm'],
                            review_only_preceding_context=prior,source=row['source'],recognized_context=candidate['source_context'],
                            emitted_source=candidate['source'],target=candidate['target'],reading=candidate['reading'],
                            focus_utf16=candidate['focus_utf16'],context_utf16=candidate['context_utf16'],
                            mixed_output=row['mixed_output'],all_selected_in_arm=row['selected_in_arm'],
                            alternative_count=candidate.get('alternatives',1),top_context_target_variants=[r['target_key'] for r in alternatives],
                            crossing_mask_ids=candidate['crossing_mask_ids'],contained_mask_ids=candidate['contained_mask_ids'],
                            expansion_evidence_scope='Aggregate variant observations; retained first-example expansion state not inferred.',
                            diagnostic_category=candidate['category'],knowledge_basis=candidate['knowledge_basis'],
                            parallel_source=proof['source']['text'] if proof else None,parallel_target=proof['target']['text'] if proof else None,
                            provenance=proof['provenance'] if proof else {'source':'prior R03 reviewed research candidate; exact control hash in projection freeze'},
                            evidence_id=ident))
    db.close()
    (evidence_dir/'packet.json').write_text(json.dumps(dict(schema='vipi.corpus-context-review-packet.r01',production=False,selection_sha256=sha(evidence_dir/'selection-freeze.json'),context_source_sha256=sha(corpus),cases=compact),ensure_ascii=False,indent=2)+'\n')
    with gzip.open(evidence_dir/'full-evidence.json.gz','xt',encoding='utf-8') as f:json.dump(full,f,ensure_ascii=False,separators=(',',':'))
    result=dict(complete=True,production=False,scopes=len(chosen),cases=len({r['case_id'] for r in chosen}),compiler_sha256=sha(Path(__file__)),outputs={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in evidence_dir.iterdir() if p.is_file()})
    (evidence_dir/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(encoded(result))

if __name__=='__main__':main()
