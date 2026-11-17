#!/usr/bin/env python3
"""Diagnostic approximation, not either native matcher or production output."""
import hashlib,json,pathlib,re
D=pathlib.Path(__file__).parent
m=json.loads((D/'manifest.json').read_text());packs={}
for row in m['packs']:
 data=(D/'packs'/row['file']).read_bytes();assert hashlib.sha256(data).hexdigest()==row['sha256'];packs[(row['source'],row['target'])]=json.loads(data)
fixture=json.loads((D/'holdout.json').read_text());rows=[]
for case in fixture['cases']:
 text=case['text'];protected=[m.span() for m in re.finditer(r'https?://\S+|[\w.+-]+@[\w.-]+',text)];found=[]
 for p in packs[(case['source'],case['target'])]['patterns']:
  for v in p['variants']:
   for match in re.finditer(r'(?<!\w)'+re.escape(v['context'])+r'(?!\w)',text):
    pos=match.start()+v['context'].index(p['source']);end=pos+len(p['source'])
    if any(pos<b and a<end for a,b in protected):continue
    found.append({'source':p['source'],'target':p['target'],'reading':p['reading'] or None,'start':pos,'end':end})
 assert len(found)<=1,(case,found)
 actual=found[0] if found else None
 passed=(actual is None if case['expected'] is None else actual is not None and actual['target']==case['expected'] and actual['source']==case['focus'] and actual['reading']==case.get('reading'))
 rows.append({'source':case['source'],'target':case['target'],'message':text,'actual':actual,'expected':case['expected'],'passed':passed,'reason':case.get('reason')})
r={'status':'diagnostic_only_not_native_or_production','fixture_sha256':hashlib.sha256((D/'holdout.json').read_bytes()).hexdigest(),'seed_sha256':m['seed_sha256'],'cases':rows,'all_passed':all(x['passed'] for x in rows)}
(D/'holdout-result.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print('cases',len(rows),'passed',sum(x['passed'] for x in rows),'emissions',sum(x['actual'] is not None for x in rows));assert r['all_passed']
