from pathlib import Path
import json,hashlib,subprocess,collections
q=Path(__file__).resolve().parent; repo=q.parents[2];w=Path('/home/ai/Development/investigations/vipi-taskmaster-source-first-20261109-r01')
load=lambda p:json.loads(p.read_text());sha=lambda b:hashlib.sha256(b).hexdigest()
raw=load(w/'run-r01/output.json');mechanics=load(w/'mechanics.json');joined=load(w/'joined-review.json');rows={x['id']:x for x in raw['cases']}
paths=['data/immersion/catalog.json','ios/Vipi/ConversationImmersion.swift','ios/Vipi/BundledImmersionCatalog.swift','ios/VipiCore/Sources/VipiCore/LookupFirst.swift']
blobs={p:subprocess.check_output(['git','show','HEAD:'+p],cwd=repo) for p in paths}
refs={x['original']:x['translation'] for x in json.loads(blobs[paths[0]])['references'] if x['pair']=='en-es'}
empty=[]
for m in mechanics['cases']:
 if m['selected_spans'] != 0:continue
 r=rows[m['id']];sent=[]
 for a,b in r['sentences']:
  text=r['original'].encode('utf-16-le')[2*a:2*b].decode('utf-16-le')
  if text in refs:sent.append({'utf16':[a,b],'source':text,'reference':refs[text]})
 empty.append({'mechanics':m,'original':r['original'],'whole_authored_reference':refs.get(r['original']),'sentence_exact_references':sent,'candidates':r['candidates'],'gates':r['gates'],'assessments':r['assessments'],'selection':r['selection'],'geometry_rejections':r['geometry_rejections'],'conditional_geometry_rejections':r['conditional_geometry_rejections']})
material=[]
for p in joined['source_first_noncorrect_candidate_provenance']:
 if p['unit']['label']=='material_error':
  r=rows[p['id']];material.append(dict(p,original=r['original'],mixed_output=r['selection']['mixed_output'],source_protections=r['source_protections'],supplied_protection=r['supplied_protection']))
key={(x['id'],x['label']):x['method'] for x in load(w/'packet/method-key.json')};aa=load(w/'author-review-r01.json');per=collections.defaultdict(dict)
for x in aa['options']:per[x['id']][key[x['id'],x['option']]]=bool(x['units'])
summary={'empty_whole_authored_reference_count':sum(x['whole_authored_reference'] is not None for x in empty),'empty_with_exact_sentence_reference_count':sum(bool(x['sentence_exact_references']) for x in empty),'nonempty_gains':sum(v['source_first'] and not v['target_informed'] for v in per.values()),'nonempty_losses':sum(v['target_informed'] and not v['source_first'] for v in per.values()),'material_source_keys':[x['candidate']['source_key'] for x in material]}
out={'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),'committed_source_hashes':{p:sha(b) for p,b in blobs.items()},'raw_sha256':sha((w/'run-r01/output.json').read_bytes()),'summary':summary,'material_provenance':material,'all_empty_cases':empty,'routing_interpretation':'Exact authored references and source paths exist; this read-only audit does not execute full app routing, density admission or promise every punctuation variant matches.'}
(w/'closure-audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary));print([(x['original'],x['whole_authored_reference']) for x in empty if x['whole_authored_reference'] is not None])
