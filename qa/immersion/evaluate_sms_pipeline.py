#!/usr/bin/env python3
"""Measure native immersion availability on frozen real-message probes.

Coverage is execution availability, never semantic approval. Every observed
span remains available for a separate assessment bound to its report hash.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import statistics
from conversation_corpus import sha_file,write_json
from review_pipeline import utf16_slice


def summarize(report,corpus):
    expected={(source,target):{c['id']:c['text'][source] for c in corpus['cases'] if source in c['text']}
        for source in corpus['languages'] for target in corpus['languages'] if source!=target}
    expected={pair:rows for pair,rows in expected.items() if rows}
    seen=set();pairs=[];latency=[]
    for pair in report['results']:
        identity=(pair['source'],pair['target'])
        if identity in seen or identity not in expected:raise ValueError('Unexpected pair')
        seen.add(identity)
        if pair.get('status','executed')!='executed':raise ValueError('Failed native pair')
        rows={};counts=Counter()
        for sample in pair['samples']:
            identifier=sample['id']
            if identifier in rows or identifier not in expected[identity]:raise ValueError('Unexpected case')
            if sample['original']!=expected[identity][identifier] or sample['status']!='executed':raise ValueError('Wrong/failed source case')
            rows[identifier]=sample;counts['messages']+=1
            counts['with_dictionary_candidates']+=sample['candidate_senses']>0
            latency.append(sample['lookup_alignment_ms'])
            for field in ('spans','context_candidates'):
                if field not in sample:continue
                spans=sample[field];counts[field]+=len(spans);counts['messages_with_'+field]+=bool(spans)
                end=0
                for span in spans:
                    if span['start']<end:raise ValueError('Overlapping spans')
                    if utf16_slice(sample['original'],span['start'],span['end'])!=span['original']:raise ValueError('Source offset mismatch')
                    if utf16_slice(sample['translation'],span['targetStart'],span['targetEnd'])!=span['translated']:raise ValueError('Target offset mismatch')
                    if pair['target'] in ('ar','zh','ja','ko') and not span.get('reading'):raise ValueError('Missing reading')
                    end=span['end']
        if rows.keys()!=expected[identity].keys():raise ValueError('Missing cases')
        pairs.append({'pair':'-'.join(identity),**dict(counts),
            'strict_message_availability':counts['messages_with_spans']/counts['messages'],
            'research_candidate_availability':counts['messages_with_context_candidates']/counts['messages']})
    if seen!=set(expected):raise ValueError('Missing pairs')
    totals=Counter()
    for pair in pairs:
        totals.update({k:v for k,v in pair.items() if isinstance(v,int)})
    sources=sorted({source for source,target in expected})
    source_messages=sum(len([c for c in corpus['cases'] if source in c['text']]) for source in sources)
    return {'source_languages':sources,'source_messages':source_messages,
        'pairs':pairs,'totals':dict(totals),
        'lookup_alignment_ms':{'median':statistics.median(latency),'p95':sorted(latency)[int(len(latency)*.95)]}}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('report','corpus','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();report=json.loads(a.report.read_text());corpus=json.loads(a.corpus.read_text())
    if a.output.exists():raise SystemExit('Preserve evaluation receipt')
    write_json(a.output,{'schema':'vipi-real-message-native-availability-1',
        'report_sha256':sha_file(a.report),'corpus_sha256':sha_file(a.corpus),'evaluator_sha256':sha_file(Path(__file__)),
        'platform':report['platform'],'meaning_accuracy':None,'linguistic_acceptance':False,
        'limits':['A replacement being available does not make its meaning or reading correct.',
          'Research candidates relax the positive-cue requirement only; they are never displayed in the app.',
          'Directions reuse source messages; directed cases are not independent conversations.',
          'Coverage applies only to the listed source languages and the retained corpus sampling design.'],
        **summarize(report,corpus)})
    print(json.dumps({'output':str(a.output),'summary':summarize(report,corpus)['totals']}))
