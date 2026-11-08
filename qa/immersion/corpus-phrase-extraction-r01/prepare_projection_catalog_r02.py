#!/usr/bin/env python3
"""Freeze diagnostic top targets; preserve competing variants in the parent DB."""
import collections
import gzip
import hashlib
import json
import sqlite3
import time
from pathlib import Path
from extract_pgv import OUT,HERE,sha,guards,process_hwm
from prepare_inputs import norm


def main():
    start=time.monotonic()
    plan=HERE/'contextual-projection-plan-r01.json'
    frozen=json.loads(plan.read_text())
    for name,digest in frozen['inputs'].items():
        assert sha(Path(name))==digest
    directory=OUT/'projection-r02'
    directory.mkdir(exist_ok=False)
    candidate=OUT/'phrases/candidates.sqlite'
    evidence=OUT/'phrases/dictionary-units.sqlite'
    db=sqlite3.connect(candidate.as_uri()+'?mode=ro&immutable=1',uri=True)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA cache_size=-32768')
    db.execute('ATTACH DATABASE ? AS dicts',(evidence.as_uri()+'?mode=ro&immutable=1',))
    query='''SELECT r.*,c.shared_sense_ids,c.status AS dictionary_status FROM ranked r
      LEFT JOIN dicts.corroboration c ON c.variant=r.id
      ORDER BY pair,arm,source_key,distinct_components DESC,mean_lexical_score DESC,id'''
    selected=[]
    group=None; current=[]
    def retain(rows):
        if not rows:return
        # All raw alternatives remain in the exact parent DB and its observations.
        usable=[r for r in rows if r['source_key']!=r['target_key']]
        choices=[('raw',rows[0])]
        full=next((r for r in rows if r['dictionary_status']=='shared_complete_dictionary_sense'),None)
        if full:choices.append(('dictionary_complete',full))
        for kind,row in choices:
            entry=dict(row,choice_kind=kind,identical_face=row['source_key']==row['target_key'],alternatives=len(rows),nonidentical_alternatives=len(usable),
                       top_alternative_ids=[r['id'] for r in rows[:12]],
                       tied_top_support=sum(r['distinct_components']==row['distinct_components'] for r in rows))
            entry['shared_sense_ids']=json.loads(entry['shared_sense_ids'])
            selected.append(entry)
    for row in db.execute(query):
        row=dict(row);key=(row['pair'],row['arm'],row['source_key'])
        if group is not None and key!=group:
            retain(current);current=[]
        current.append(row);group=key
    retain(current)
    db.close()
    index=collections.defaultdict(lambda:collections.defaultdict(list))
    for row in selected:index[row['pair']][row['example_pair_index']].append(row)
    freeze=dict(production=False,source_plan_sha256=sha(plan),compiler_sha256=sha(Path(__file__)),
                selected_identity_sha256=hashlib.sha256(json.dumps([(r['pair'],r['arm'],r['source_key'],r['choice_kind'],r['id']) for r in selected],separators=(',',':')).encode()).hexdigest(),
                choices=len(selected),unique_variants=len({r['id'] for r in selected}),
                policy='Already frozen support/lexical score/stableID ordering; top overall retained including identical faces; identity receives zero immersion credit without replacing it with another target. All competing lengths/senses retained in parent candidates DB. Dictionary-complete view is corroboration, not context approval.')
    (directory/'catalog-selection-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    count=0; examples=0
    with gzip.open(directory/'catalog.jsonl.gz','xt',encoding='utf-8') as catalog,gzip.open(directory/'selected-pair-evidence.jsonl.gz','xt',encoding='utf-8') as proof:
        for pair in ['en-sw','en-es']:
            with gzip.open(OUT/(pair+'-pairs.jsonl.gz'),'rt') as stream:
                for line in stream:
                    raw=json.loads(line)
                    choices=index[pair].get(raw['index'])
                    if not choices:continue
                    proof.write(json.dumps(raw,ensure_ascii=False,separators=(',',':'))+'\n');examples+=1
                    for choice in choices:
                        s,e,t,u=(choice[k] for k in ['source_start','source_end','target_start','target_end'])
                        source,target=raw['source'],raw['target'];st,tt=source['tokens'],target['tokens']
                        source_span=[st[s]['codepoints'][0],st[e-1]['codepoints'][1]]
                        target_span=[tt[t]['codepoints'][0],tt[u-1]['codepoints'][1]]
                        source_text=source['text'][slice(*source_span)];target_text=target['text'][slice(*target_span)]
                        assert norm(source_text)==choice['source_key'] and norm(target_text)==choice['target_key']
                        entry=choice|dict(catalog_id=choice['choice_kind']+':'+choice['id'],
                                          source_context=source_text,target_face=target_text,reading='',
                                          source_context_token_text=[norm(z['text']) for z in st[s:e]],
                                          source_focus_relative_tokens=[0,e-s],
                                          source_context_tokens=[s,e],target_context_tokens=[t,u],
                                          source_context_codepoints=source_span,target_context_codepoints=target_span,
                                          pair_id=raw['pair_id'],source_component=source['component'],target_component=target['component'],
                                          provenance=raw['provenance'],
                                          source_record_sha256=source['record_sha256'],target_record_sha256=target['record_sha256'],
                                          semantic_approval=False)
                        catalog.write(json.dumps(entry,ensure_ascii=False,separators=(',',':'))+'\n');count+=1
                    if examples%250==0:guards(start,1800)
    receipt=dict(complete=True,production=False,selection_freeze_sha256=sha(directory/'catalog-selection-freeze.json'),
                 entries=count,retained_pair_examples=examples,seconds=time.monotonic()-start,
                 process_vm_hwm_bytes=process_hwm(),outputs={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in directory.iterdir() if p.is_file()})
    (directory/'catalog-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))


if __name__=='__main__':main()
