#!/usr/bin/env python3
"""Summarize complete native dictionary replays without exposing corpus text."""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def identity(row):return row['dataset'],row['id'],row['source'],row['target']
def quantile(values,p):
    values=sorted(values)
    return round(values[min(len(values)-1,int((len(values)-1)*p))],3) if values else None

def read(root,path):
    manifest=json.loads((root/'manifest.json').read_text())
    assert manifest['cases_sha256']==sha(root/'cases.json')
    cases=json.loads((root/'cases.json').read_text());expected={identity(r):r for r in cases}
    assert len(expected)==len(cases)==manifest['cases']
    report=json.loads(path.read_text())
    assert report['schema']=='vipi-lexical-coverage-1' and report['complete']
    assert report['manifest_sha256']==sha(root/'manifest.json')
    actual={identity(r):r for r in report['outcomes']}
    assert set(actual)==set(expected) and len(actual)==len(report['outcomes'])==report['cases']
    failures=[]
    for key,row in actual.items():
        case=expected[key];spans=row['spans'];combined=row.get('combined_spans')
        for span in spans+(combined if combined is not None else []):
            for text_key,start,end,focus in [('original','start','end','source'),('translation','target_start','target_end','target')]:
                text=case[text_key].encode('utf-16-le')
                assert 0<=span[start]<span[end]<=len(text)//2
                assert text[2*span[start]:2*span[end]].decode('utf-16-le')==span[focus]
            if case['target'] in {'ar','zh','ja','ko'}:assert span['reading'] and span['reading'].strip()
        def forbidden(span):
            return ('forbidden_source' in case and span['source']==case['forbidden_source'] and span['target']==case['forbidden_target']
                    and ('forbidden_source_start' not in case or span['start']==case['forbidden_source_start']))
        if any(map(forbidden,spans)):failures.append(list(key))
        if 'expected_source' in case:
            expected_path=case.get('expected_path','dictionary');assert expected_path in {'dictionary','combined'}
            chosen=combined if expected_path=='combined' else spans
            assert chosen is not None
            matches=lambda s:s['source']==case['expected_source'] and s['target']==case['expected_target']
            if not any(map(matches,chosen)):failures.append(list(key))
            if combined is not None and not any(map(matches,combined)):failures.append(list(key)+['combined missing'])
            if 'expected_count' in case and (sum(map(matches,chosen))!=case['expected_count'] or (combined is not None and sum(map(matches,combined))!=case['expected_count'])):failures.append(list(key)+['repeated lexical occurrence count'])
            if case.get('expected_dictionary_abstention') and any(map(matches,spans)):failures.append(list(key)+['dictionary phrase protection bypassed'])
        if combined is not None:
            if not row['baseline_retained']:failures.append(list(key)+['baseline lost'])
            if any(map(forbidden,combined)):failures.append(list(key)+['combined forbidden'])
            assert row['identifier_guard'] or not combined
    assert report['passed']==(not failures)
    groups=defaultdict(list)
    for row in actual.values():
        groups[row['dataset']].append(row)
        groups[row['dataset']+':'+row['source']+'-'+row['target']].append(row)
    summary={}
    for group,rows in sorted(groups.items()):
        baseline=sum(r['baseline_spans']>0 for r in rows);dictionary=sum(bool(r['spans']) for r in rows)
        extra=sum(bool(r['spans']) and not r['baseline_spans'] for r in rows)
        diagnostics=Counter()
        for row in rows:diagnostics.update(row.get('diagnostics',{}))
        summary[group]=dict(cases=len(rows),baseline_messages=baseline,dictionary_messages=dictionary,
            additional_messages=extra,union_messages=baseline+extra,union_percent=round(100*(baseline+extra)/len(rows),2),
            selected_spans=sum(len(r['spans']) for r in rows),lookup_median_ms=quantile([r['elapsed_ms'] for r in rows],.5),
            lookup_p95_ms=quantile([r['elapsed_ms'] for r in rows],.95),diagnostics=dict(diagnostics))
        if any('combined_spans' in r for r in rows):
            assert all('combined_spans' in r for r in rows)
            combined=sum(bool(r['combined_spans']) for r in rows)
            summary[group].update(combined_messages=combined,combined_percent=round(100*combined/len(rows),2),
                combined_selected_spans=sum(len(r['combined_spans']) for r in rows),
                baseline_loss_cases=sum(not r['baseline_retained'] for r in rows),
                combined_lookup_median_ms=quantile([r['combined_elapsed_ms'] for r in rows],.5),
                combined_lookup_p95_ms=quantile([r['combined_elapsed_ms'] for r in rows],.95))
    return dict(platform=report['platform'],report_sha256=sha(path),manifest_sha256=report['manifest_sha256'],
        complete=True,passed=not failures,failures=failures,groups=summary),actual

def main(a):
    result,rows=read(a.fixture,a.report)
    if a.compare:
        other,against=read(a.fixture,a.compare);assert set(rows)==set(against)
        differences=[]
        for key,row in rows.items():
            left=sorted(row['spans'],key=lambda s:(s['start'],s['end'],s['target']))
            right=sorted(against[key]['spans'],key=lambda s:(s['start'],s['end'],s['target']))
            if left!=right:differences.append(list(key))
        result['parity']=dict(other_platform=other['platform'],other_sha256=other['report_sha256'],
            cases=len(rows),differing_cases=len(differences),differences=differences)
        if all('combined_spans' in r for r in rows.values()) and all('combined_spans' in r for r in against.values()):
            different=[]
            for key,row in rows.items():
                order=lambda s:(s['start'],s['end'],s['target'])
                if sorted(row['combined_spans'],key=order)!=sorted(against[key]['combined_spans'],key=order):different.append(list(key))
            result['combined_parity']=dict(cases=len(rows),differing_cases=len(different),differences=different)
    result.update(schema='vipi-lexical-coverage-summary-1',independent_semantic_acceptance=False,
        limitation='Reused native translations, dictionary-unit mechanics and separately labeled human-reference diagnostics; message availability is not semantic accuracy or general-population coverage.')
    with a.output.open('x') as stream:json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='groups'}))
    print(json.dumps({k:v for k,v in result['groups'].items() if ':' not in k}))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['fixture','report','output']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--compare',type=Path);main(p.parse_args())
