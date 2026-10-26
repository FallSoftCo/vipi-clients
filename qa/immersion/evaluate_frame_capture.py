#!/usr/bin/env python3
"""Validate native replay provenance and report availability, never accuracy."""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def key(row):return row['case'],row['source'],row['target']


def unique(rows):
    result={key(row):row for row in rows}
    if len(result)!=len(rows):raise ValueError('Duplicate directed case')
    return result


def surface(text,start,end):
    if type(start) is not int or type(end) is not int or not 0<=start<end<=len(text.encode('utf-16-le'))//2:
        raise ValueError('Invalid UTF-16 scope')
    try:return text.encode('utf-16-le')[2*start:2*end].decode('utf-16-le')
    except UnicodeError as error:raise ValueError('Scope splits a Unicode scalar') from error


def evaluate(report_path,capture_path,build_path,baseline_path=None,conversation_probe=False,dictionary_path=None):
    report=json.loads(report_path.read_text());capture=json.loads(capture_path.read_text());build=json.loads(build_path.read_text())
    schema='vipi-frame-conversation-1' if conversation_probe else 'vipi-frame-capture-1'
    if report.get('schema')!=schema or report.get('translation_capture_sha256')!=sha(capture_path) or report.get('build_sha256')!=sha(build_path):
        raise ValueError('Native report provenance mismatch')
    if not capture.get('complete') or capture.get('cases_expected')!=capture.get('cases_completed'):
        raise ValueError('Incomplete model capture')
    native=unique(report['results']);actual=unique(capture['results'])
    if native.keys()!=actual.keys() or len(native)!=report['cases'] or len(native)!=capture['cases_expected']:
        raise ValueError('Missing directed cases')
    directions={s+'-'+t for _,s,t in native};installed={p['pack_id'] for p in build['pairs']}
    if (not directions<=installed if conversation_probe else directions!=installed):
        raise ValueError('Pack directions differ from evaluation')
    groups=defaultdict(list)
    for identity,row in native.items():
        source=actual[identity]
        if source['status']!='executed' or any(row[field]!=source[field] for field in ('original','translation')):
            raise ValueError('Replay changed model input or output')
        if type(row['mapping_count']) is not int or not 0<=row['mapping_count']<=256:raise ValueError('Invalid mapping count')
        if not math.isfinite(row['lookup_alignment_ms']) or row['lookup_alignment_ms']<0:raise ValueError('Invalid timing')
        previous_end=0
        for span in row['spans']:
            if not conversation_probe and (span['start'],span['end'])!=(source['start'],source['end']):raise ValueError('Changed lexical focus')
            if span['start']<previous_end:raise ValueError('Overlapping or unsorted source spans')
            if surface(row['original'],span['start'],span['end'])!=span['original'] or surface(row['translation'],span['targetStart'],span['targetEnd'])!=span['translated']:
                raise ValueError('Span does not preserve actual text')
            if row['target'] in ('ar','zh','ja','ko') and not span.get('reading'):raise ValueError('Required reading absent')
            previous_end=span['end']
        groups[row['source']+'-'+row['target']].append(row)
    def counts(rows):
        times=sorted(row['lookup_alignment_ms'] for row in rows)
        return {'cases':len(rows),'cases_with_mappings':sum(r['mapping_count']>0 for r in rows),
            'cases_with_immersion':sum(bool(r['spans']) for r in rows),'spans':sum(len(r['spans']) for r in rows),
            'lookup_alignment_median_ms':statistics.median(times),'lookup_alignment_p95_ms':times[math.ceil(len(times)*.95)-1]}
    result={'schema':'vipi-frame-availability-1','platform':report['platform'],'report_sha256':sha(report_path),
        'translation_capture_sha256':sha(capture_path),'build_sha256':sha(build_path),**counts(list(native.values())),
        'pairs':{pair:counts(rows) for pair,rows in sorted(groups.items())},'linguistic_acceptance':False,
        'scope':('Conversation development probe with actual local translations; no accuracy or population inference' if conversation_probe else
                 'Authored development constructions with actual local translations; no majority-conversation inference')}
    if dictionary_path:
        if not conversation_probe:raise ValueError('Dictionary comparison requires conversation probe')
        dictionary=json.loads(dictionary_path.read_text())
        platform={'Android':'Android','iOS':'Physical iOS device'}[report['platform']]
        if dictionary.get('platform')!=platform:raise ValueError('Different baseline platform')
        old={}
        for pair in dictionary['results']:
            for row in pair['samples']:
                identity=(row['id'],pair['source'],pair['target'])
                if identity in old:raise ValueError('Duplicate baseline case')
                old[identity]=row
        if old.keys()!=native.keys():raise ValueError('Different dictionary cases')
        for identity,row in old.items():
            if row['status']!='executed' or any(row[f]!=native[identity][f] for f in ('original','translation')):
                raise ValueError('Different or failed dictionary translation')
        def opportunity(ids):
            return {'dictionary_cases':sum(bool(old[k]['spans']) for k in ids),
                'additional_frame_cases':sum(bool(native[k]['spans']) and not old[k]['spans'] for k in ids),
                'either_path_cases':sum(bool(old[k]['spans']) or bool(native[k]['spans']) for k in ids)}
        result['dictionary_comparison']={'report_sha256':sha(dictionary_path),**opportunity(native),
            'pairs':{pair:opportunity([k for k in native if k[1]+'-'+k[2]==pair]) for pair in sorted(groups)},
            'limit':'Union of separate availability results, not a combined selection policy, correctness or app integration.'}
    if baseline_path:
        baseline=json.loads(baseline_path.read_text());old=unique(baseline['results'])
        if baseline.get('translation_capture_sha256')!=sha(capture_path) or baseline.get('platform')!=report['platform'] or old.keys()!=native.keys():
            raise ValueError('Comparison requires identical platform and actual capture')
        for identity,row in old.items():
            if any(row[field]!=native[identity][field] for field in ('original','translation')):raise ValueError('Changed baseline text')
        result['comparison']={'baseline_sha256':sha(baseline_path),
            'new_mapping_cases':sum(not old[k]['mapping_count'] and native[k]['mapping_count']>0 for k in native),
            'lost_mapping_cases':sum(old[k]['mapping_count']>0 and not native[k]['mapping_count'] for k in native),
            'new_immersion_cases':sum(not old[k]['spans'] and bool(native[k]['spans']) for k in native),
            'lost_immersion_cases':sum(bool(old[k]['spans']) and not native[k]['spans'] for k in native)}
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('report','capture','build','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--baseline',type=Path)
    p.add_argument('--conversation-probe',action='store_true')
    p.add_argument('--dictionary-baseline',type=Path);a=p.parse_args()
    result=evaluate(a.report,a.capture,a.build,a.baseline,a.conversation_probe,a.dictionary_baseline)
    with a.output.open('x') as stream:json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='pairs'},ensure_ascii=False))
