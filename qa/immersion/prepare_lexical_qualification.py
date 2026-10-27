#!/usr/bin/env python3
"""Freeze broad dictionary mechanics and existing conversation replays.

No corpus text feeds dictionary authoring. Reused diagnostics are not untouched
acceptance data; single-word dictionary probes do not establish chat accuracy.
"""
import argparse
from collections import defaultdict, Counter
import hashlib
import heapq
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'language-packs'))
from build_wiktextract import canonical,digest_file

def main(a):
    catalog=json.loads((a.shards/'catalog.json').read_text())
    assert catalog['schema']=='vipi-lexical-shards-1'
    cases=[];provenance=[]
    manifest=json.loads((a.replay/'manifest.json').read_text())
    assert manifest['schema']=='vipi-captured-conversation-input-1'
    for file in manifest['files']:
        path=a.replay/file['file'];assert digest_file(path)==file['sha256']
        data=json.loads(path.read_text());count=0
        for pair in data['pairs']:
            for sample in pair['samples']:
                assert sample['status']=='executed'
                cases.append(dict(id=sample['id'],dataset=data['name'],source=pair['source'],target=pair['target'],
                    original=sample['original'],translation=sample['translation']))
                count+=1
        assert count==file['cases'];provenance.append(dict(file=str(path),sha256=file['sha256'],cases=count,kind='reused-native-captures'))
    if a.swahili:
        assert digest_file(a.swahili)=='bdb9a77770f6b8f0c43e15e0c7baa43e983421e924ea3ec0c610280cb2ea52a5'
        data=json.loads(a.swahili.read_text());assert data['schema']=='vipi-spontaneous-swahili-coverage-1'
        for row in data['rows']:
            explicit=row['explicit_sw'];assert explicit and row['source']=='sw' and explicit['baseline']==row['original']
            cases.append(dict(id=row['id'],dataset='liva-sw-explicit-replay',source='sw',target=row['target'],
                original=row['original'],translation=explicit['translation']))
        provenance.append(dict(file=str(a.swahili),sha256=digest_file(a.swahili),cases=len(data['rows']),kind='reused-explicit-source-native-captures'))
    findings=[]
    for filename in ['sms_semantic_findings.json','multi3woz_semantic_findings.json']:
        data=json.loads(Path(__file__).with_name(filename).read_text())
        for finding in data['findings']:
            left,right=finding['pair'].split('-')
            matches=[r for r in cases if r['id']==finding['case'] and r['source']==left and r['target']==right]
            assert len(matches)==1
            row=matches[0];row['forbidden_source']=finding['source'];row['forbidden_target']=finding['target']
            findings.append(dict(id=row['id'],source=left,target=right,category=finding['category']))
    # Deterministic dictionary-unit sample. Selection is independent of native
    # output; failures/abstentions remain in its denominator.
    heads=defaultdict(lambda:defaultdict(list));languages=[]
    for shard in catalog['shards']:
        lang=shard['language'];languages.append(lang);path=a.shards/(lang+'.sqlite')
        assert digest_file(path)==shard['sha256']
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as db:
            for sid,word,reading,source_safe,explicit in db.execute('''SELECT t.sense,l.headword,t.reading,l.source_safe,s.explicit
                FROM terms t JOIN lexemes l ON l.id=t.lexeme JOIN senses s ON s.id=t.sense
                WHERE t.eligible=1 AND l.target_safe=1 ORDER BY t.sense,l.id,t.reading'''):
                if not word.isalpha() or len(word)>64:continue
                heads[sid][lang].append((word,reading,bool(source_safe),bool(explicit)))
    probes=defaultdict(list)
    for sid,values in heads.items():
        for source,left in values.items():
            for target,right in values.items():
                if source==target:continue
                aform=next((r for r in left if r[2] and (source=='en' or target=='en' or r[3])),None)
                bform=right[0]
                if not aform or aform[0].lower()==bform[0].lower():continue
                fingerprint=hashlib.sha256(canonical([source,target,sid,aform[0],bform[0]]).encode()).hexdigest()
                item=(-int(fingerprint,16),fingerprint,aform[0],bform[0]);heap=probes[source,target]
                if len(heap)<a.per_pair:heapq.heappush(heap,item)
                elif item>heap[0]:heapq.heapreplace(heap,item)
    for pair in sorted(probes):
        for _,identifier,left,right in sorted(probes[pair],key=lambda row:row[1]):
            cases.append(dict(id='lexical-'+identifier[:24],dataset='dictionary-unit-mechanics',source=pair[0],target=pair[1],original=left+'.',translation=right+'.'))
    assert set(probes)=={(s,t) for s in languages for t in languages if s!=t}
    for identifier,left,right,focus,target in [
        ('sw-say-carrier','Ninasema.','I speak.','sema','speak'),
        ('sw-know-carrier','Ninajua.','I know.','jua','know'),
        ('sw-love-carrier','Ninapenda.','I love.','penda','love')]:
        cases.append(dict(id=identifier,dataset='authored-carrier-behavior',source='sw',target='en',original=left,translation=right,
            expected_source=focus,expected_target=target))
    cases.append(dict(id='sw-invented-carrier',dataset='authored-carrier-behavior',source='sw',target='en',
        original='Xyzpenda.',translation='I love.',forbidden_source='penda',forbidden_target='love'))
    cases.append(dict(id='sw-know-conflicting-person',dataset='authored-carrier-behavior',source='sw',target='en',
        original='Ninajua.',translation='You know.',forbidden_source='jua',forbidden_target='know'))
    a.output.mkdir(parents=True,exist_ok=False)
    path=a.output/'cases.json';path.write_text(canonical(cases)+'\n')
    result=dict(schema='vipi-lexical-qualification-1',shards=catalog['shards'],cases_sha256=digest_file(path),
        source_catalog_sha256=digest_file(a.shards/'catalog.json'),compiler_sha256=digest_file(Path(__file__)),
        cases=len(cases),datasets=dict(Counter(r['dataset'] for r in cases)),provenance=provenance,known_regressions=findings,
        dictionary_probe_pairs=len(probes),classification_exercised=False,independent_semantic_acceptance=False)
    (a.output/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    # Hard links consume no duplicate payload; staging failures leave originals.
    for shard in catalog['shards']:(a.output/(shard['language']+'.sqlite')).hardlink_to(a.shards/(shard['language']+'.sqlite'))
    print(canonical({k:result[k] for k in ['cases','datasets','dictionary_probe_pairs']}))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['shards','replay','output']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--swahili',type=Path);p.add_argument('--per-pair',type=int,default=32)
    a=p.parse_args();assert 1<=a.per_pair<=128;main(a)
