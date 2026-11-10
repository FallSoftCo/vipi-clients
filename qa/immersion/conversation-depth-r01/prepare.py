#!/usr/bin/env python3
"""Frozen source-only exposure accounting and selection. Never calls native/provider code."""
from pathlib import Path
import json,hashlib,unicodedata,collections,resource,signal,os,time
R=Path('/home/ai/Development/vipi-production-20261107');Q=Path(__file__).resolve().parent;W=Path('/home/ai/Development/investigations/vipi-conversation-depth-20261109-r01');E=Path('/home/ai/Development/investigations/vipi-immersion-reconciliation-20261107-r01/bst-evaluation-source-r01')
sha=lambda b:hashlib.sha256(b).hexdigest()
norm=lambda s:' '.join(unicodedata.normalize('NFC',s).casefold().split())
def write(p,x):
 assert not p.exists();p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def main():
 resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));signal.alarm(60);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});started=time.monotonic()
 protocol=json.loads((W/'protocol.json').read_text());assert protocol['prepare_sha256']==sha(Path(__file__).read_bytes())
 raw_exact=set();raw_normal=set();sequence_exact=set();sequence_normal=set();valid_used=set();bindings=[];counts=collections.Counter()
 def add(s):
  if not isinstance(s,str) or not s.strip():return
  raw_exact.add(sha(s.encode()));raw_normal.add(sha(norm(s).encode()))
 def sequence(v):
  if not isinstance(v,list):return
  texts=[]
  for x in v:
   if isinstance(x,(list,tuple)) and len(x)==2 and isinstance(x[1],str):texts.append(x[1])
   elif isinstance(x,dict):
    t=x.get('text') or x.get('source') or x.get('original')
    if isinstance(t,str):texts.append(t)
  if texts:
   for t in texts:add(t)
   sequence_exact.add(sha(json.dumps(texts,ensure_ascii=False,separators=(',',':')).encode()));sequence_normal.add(sha(json.dumps([norm(t)for t in texts],ensure_ascii=False,separators=(',',':')).encode()))
 def visit(x):
  if isinstance(x,dict):
   for k,v in x.items():
    if k in ['text','source','original','original_text','source_text'] and isinstance(v,str):add(v)
    if 'context' in k or 'dialogue' in k or 'dialog'==k:sequence(v)
    visit(v)
  elif isinstance(x,list):
   for v in x:visit(v)
 for row in protocol['exposure_inputs']:
  p=Path(row['path']);raw=p.read_bytes();assert sha(raw)==row['sha256'];x=json.loads(raw);bindings.append(row);visit(x)
  if isinstance(x,dict) and protocol['valid_sha256'] in x.get('input_hashes',{}).values():
   valid_used.update(c['conversation_index'] for c in x.get('cases',[]) if isinstance(c,dict) and 'conversation_index'in c)
 # All retained TRAIN/TEST free-worker text is a separate development/cross-split exclusion.
 cross_exact=set();cross_normal=set()
 for n,digest in protocol['cross_split_inputs'].items():
  raw=(E/n).read_bytes();assert sha(raw)==digest;data=json.loads(raw)
  for c in data:
   for who,text in c['dialog']:
    if who==0 and text.strip():cross_exact.add(sha(text.encode()));cross_normal.add(sha(norm(text).encode()))
  del data,raw
 indexed=json.loads(Path(protocol['legacy_exclusion_index']['path']).read_text());assert sha(Path(protocol['legacy_exclusion_index']['path']).read_bytes())==protocol['legacy_exclusion_index']['sha256'];legacy=set(indexed['hashes'])
 raw=(E/'valid.json').read_bytes();assert sha(raw)==protocol['valid_sha256'];data=json.loads(raw);del raw
 options=collections.defaultdict(lambda:collections.defaultdict(list));prior_overlaps={}
 for ci,c in enumerate(data):
  dataset=c['context_dataset'];stratum={'convai2':'persona','empathetic_dialogues':'empathetic'}.get(dataset)
  if stratum is None:continue
  counts[stratum+'_conversations']+=1
  if ci in valid_used:counts[stratum+'_exposed_conversations']+=1;continue
  for ti,(who,text) in enumerate(c['dialog']):
   if who!=0 or not text.strip():continue
   counts[stratum+'_turns_considered']+=1;encoded=text.encode();exact=sha(encoded);normal=sha(norm(text).encode())
   if len(text.encode('utf-16-le'))//2>16384:counts[stratum+'_oversize']+=1;continue
   if exact in raw_exact or normal in raw_normal:counts[stratum+'_exposed_source']+=1;continue
   if exact in cross_exact or normal in cross_normal:counts[stratum+'_cross_split_source']+=1;continue
   if sha(('en\0'+norm(text)).encode()) in legacy:counts[stratum+'_legacy_index_source']+=1;continue
   prior=c['dialog'][:ti];prior_texts=[t for _,t in prior]
   pe=sha(json.dumps(prior_texts,ensure_ascii=False,separators=(',',':')).encode());pn=sha(json.dumps([norm(t)for t in prior_texts],ensure_ascii=False,separators=(',',':')).encode())
   if prior_texts and (pe in sequence_exact or pn in sequence_normal):counts[stratum+'_exposed_complete_prior_sequence']+=1;continue
   n=len(text.split());length='short' if n<=5 else 'medium' if n<=15 else 'long'
   id=f'bst-valid-depth-r01-{ci:04d}-{ti:02d}';rank=sha((protocol['seed']+'\0'+id).encode())
   options[stratum][length].append({'id':id,'stratum':stratum,'source':text,'source_ids':{'dataset':'BlendedSkillTalk','split':'valid','conversation_index':ci,'dialog_index':ti,'valid_sha256':protocol['valid_sha256']},'length_bin':length,'source_sha256':exact,'normalized_sha256':normal,'rank':rank,'prior':prior,'prior_exact_sha256':pe,'prior_normalized_sha256':pn,'prior_individual_exact_overlap':sum(sha(t.encode())in raw_exact for t in prior_texts),'prior_individual_normalized_overlap':sum(sha(norm(t).encode())in raw_normal for t in prior_texts)})
 selected=[];limits={}
 for stratum in ['persona','empathetic']:
  # Deterministic bipartite matching: fixed 10 short/20 medium/10 long slots; conversations exclusive.
  slots=[kind for kind,num in protocol['length_quotas'].items()for _ in range(num)];edges=[]
  for kind in slots:
   by_conv={}
   for row in sorted(options[stratum][kind],key=lambda x:x['rank']):by_conv.setdefault(row['source_ids']['conversation_index'],row)
   edges.append(list(by_conv.values()))
  assigned={};slot_rows={}
  def match(slot,seen):
   for row in edges[slot]:
    ci=row['source_ids']['conversation_index']
    if ci in seen:continue
    seen.add(ci)
    if ci not in assigned or match(assigned[ci],seen):assigned[ci]=slot;slot_rows[slot]=row;return True
   return False
  success=sum(match(i,set()) for i in range(len(slots)));limits[stratum]={'filled':success,'eligible_by_bin':{k:len(v)for k,v in options[stratum].items()},'eligible_conversations_by_bin':{k:len({x['source_ids']['conversation_index']for x in v})for k,v in options[stratum].items()}}
  selected.extend(slot_rows[i]for i in sorted(slot_rows))
 audit={'protocol_sha256':sha((W/'protocol.json').read_bytes()),'counts':dict(counts),'valid_exposed_conversation_ids':sorted(valid_used),'exposure_exact_text_hashes':len(raw_exact),'exposure_normalized_text_hashes':len(raw_normal),'complete_prior_sequence_hashes':len(sequence_normal),'limits':limits,'inputs':bindings,'uncertainty':protocol['exposure_limits'],'seconds':time.monotonic()-started,'VmHWM':next(l for l in Path('/proc/self/status').read_text().splitlines()if l.startswith('VmHWM'))}
 write(W/'exposure-audit.json',audit)
 assert all(v['filled']==40 for v in limits.values()),'Insufficient pool; retained audit, no substitution or native input'
 assert len(selected)==80 and len({x['source_ids']['conversation_index']for x in selected})==80
 assert len({x['normalized_sha256']for x in selected})==80,'Selected source duplicate; no automatic reselection'
 selected.sort(key=lambda x:(x['stratum'],x['rank']))
 native=[{k:x[k]for k in ['id','stratum','source','source_ids']}for x in selected]
 prior=[{k:x[k]for k in ['id','stratum','source_ids','prior','prior_exact_sha256','prior_normalized_sha256','prior_individual_exact_overlap','prior_individual_normalized_overlap']}for x in selected]
 write(W/'inputs/messages.json',{'schema':'vipi-conversation-depth-input-1','cases':native})
 write(W/'reviewer-only/prior-dialogue.json',{'schema':'vipi-conversation-depth-prior-1','policy':'Review context only; never native input; free/guided worker roles retained as 0/1.','cases':prior})
 write(W/'selection-freeze.json',{'protocol_sha256':sha((W/'protocol.json').read_bytes()),'audit_sha256':sha((W/'exposure-audit.json').read_bytes()),'cases':[{k:v for k,v in x.items()if k not in ['source','prior']}for x in selected],'remaining_pool_not_selected':True,'no_match_or_output_access':True,'source_texts_printed':False,'native_messages_sha256':sha((W/'inputs/messages.json').read_bytes()),'prior_dialogue_sha256':sha((W/'reviewer-only/prior-dialogue.json').read_bytes())})
 write(W/'inputs/manifest.json',{'messages.json':sha((W/'inputs/messages.json').read_bytes())})
 print(json.dumps({'cases':len(native),'strata':dict(collections.Counter(x['stratum']for x in native)),'lengths':dict(collections.Counter(x['stratum']+'/'+x['length_bin']for x in selected)),'manifest_sha256':sha((W/'inputs/manifest.json').read_bytes()),'messages_sha256':sha((W/'inputs/messages.json').read_bytes()),'selection_sha256':sha((W/'selection-freeze.json').read_bytes()),'prior_individual_overlap_cases':sum(x['prior_individual_normalized_overlap']>0 for x in selected)}))
if __name__=='__main__':main()
