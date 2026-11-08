#!/usr/bin/env python3
"""Freeze disjoint dialogue contexts; preserve natural formula-surface repetition."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import time

from sample_conversational_holdout import canonical, strings


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ['train','test','freeze','amendment','output']:
        p.add_argument('--'+arg,type=Path,required=True)
    p.add_argument('--exclude',type=Path,action='append',default=[])
    a=p.parse_args();plan=json.loads(a.freeze.read_text());amend=json.loads(a.amendment.read_text())
    assert amend['policy_freeze_sha256']==sha(a.freeze)
    assert amend['allow_training_surface_overlap'] and amend['allow_repeated_surface_across_distinct_conversations']
    assert sha(a.train)=='a5a9672c3e2e8a2f3d740cb0b61810ad46f3e3cd7bbe86b8d79962c6b34ad33c'
    assert sha(a.test)=='14ee0431113d28ca5e9424212170196c7e45706e96e7b46d34d52b96cbd0b380'
    bindings={str(p):sha(p) for p in [a.train,a.test,a.freeze,a.amendment]+a.exclude}
    train_texts=set()
    for c in json.loads(a.train.read_text()):
        train_texts.update(canonical(t) for _,t in c['dialog'])
        train_texts.update(canonical(c[k]) for k in ['free_turker_utterance','guided_turker_utterance'])
    excluded_texts=set();excluded_dialogues=set()
    for path in a.exclude:
        prior=json.loads(path.read_text());excluded_texts.update(canonical(t) for t in strings(prior))
        for r in prior.get('cases',[]):
            if isinstance(r,dict) and str(r.get('id','')).startswith('bst-test-') and 'conversation_index' in r:
                excluded_dialogues.add(r['conversation_index'])
    pools=collections.defaultdict(list)
    for ci,c in enumerate(json.loads(a.test.read_text())):
        if ci in excluded_dialogues or c['context_dataset']!='convai2':continue
        for ti,(speaker,text) in enumerate(c['dialog']):
            if speaker!=0 or not text.strip():continue
            n=len(text.split());group='1-5' if n<=5 else '6-15' if n<=15 else '16-30' if n<=30 else None
            if not group:continue
            context=[dict(role='free_seed',text=c['free_turker_utterance']),dict(role='guided_seed',text=c['guided_turker_utterance'])]
            context += [dict(role='free_human' if s==0 else 'guided_human_may_use_suggestions',text=t) for s,t in c['dialog'][:ti]]
            pools[group].append(dict(id=f'bst-test-content-r01-{ci:04d}-{ti:02d}',text=text,source='en',
                conversation_index=ci,turn_index=ti,sampling_length_bin=group,
                train_surface_overlap=canonical(text) in train_texts,
                previously_evaluated_or_seen_surface_overlap=canonical(text) in excluded_texts,
                review_only_preceding_context=context))
    selected=[];used=set()
    for group,quota in [('1-5',26),('6-15',27),('16-30',27)]:
        choices=sorted(pools[group],key=lambda r:hashlib.sha256(('content-expansion-context-r01:'+r['id']).encode()).digest())
        count=0
        for r in choices:
            if r['conversation_index'] in used:continue
            selected.append(r);used.add(r['conversation_index']);count+=1
            if count==quota:break
        assert count==quota,(group,count)
    selected.sort(key=lambda r:hashlib.sha256(('content-expansion-order-r01:'+r['id']).encode()).digest())
    for group in pools:
        rows=sorted([r for r in selected if r['sampling_length_bin']==group],key=lambda r:hashlib.sha256(('content-expansion-review-r01:'+r['id']).encode()).digest())
        for r in rows[:8]:r['independent24']=True
    output=dict(schema='vipi-content-expansion-context-holdout-1',production=False,training_use=False,pack_building_use=False,
        frozen_unix=time.time(),policy_freeze_sha256=sha(a.freeze),sampling_amendment_sha256=sha(a.amendment),
        input_hashes=bindings,sampler_sha256=sha(Path(__file__)),excluded_test_conversations=sorted(excluded_dialogues),
        source_license='BlendedSkillTalk CC-BY-4.0, existing evaluation-data-licenses attribution',
        context_policy='Only selected message enters matcher. Prior turns are review-only; selected inputs are human free-worker, guided context may contain suggestions.',
        sampling_limit='Length-balanced persona-chat diagnostic, not a frequency-weighted worldwide-chat estimate. TRAIN surface overlaps and duplicate utterance surfaces retained and reported separately.',
        summary=dict(cases=len(selected),distinct_conversations=len(used),unique_source_texts=len({canonical(r['text']) for r in selected}),train_surface_overlaps=sum(r['train_surface_overlap'] for r in selected),previously_evaluated_or_seen_surface_overlaps=sum(r['previously_evaluated_or_seen_surface_overlap'] for r in selected),novel_surface_rows=sum(not r['train_surface_overlap'] and not r['previously_evaluated_or_seen_surface_overlap'] for r in selected)),cases=selected)
    assert not a.output.exists();a.output.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(summary=output['summary'],sha256=sha(a.output)),indent=2))


if __name__=='__main__':main()
