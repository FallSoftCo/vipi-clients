#!/usr/bin/env python3
"""Frozen source-support probe. Two bounded read-only passes; no selector replay."""
import argparse,ast,collections,gzip,hashlib,importlib.util,json,os,resource,shutil,signal,socket,sqlite3,time,types,unicodedata,zlib
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=Path('/srv/fallsoft/staging/vipi-context-key-expansion-20261109-r01')
BASE=ROOT/'outputs/missing-support-probe-r01'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def enc(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def norm(s):return ' '.join(unicodedata.normalize('NFC',s).casefold().split())
def fingerprint(s):return hashlib.sha256(('en\0'+norm(s)).encode()).hexdigest()
def write(p,x):
 data=(enc(x)+'\n').encode();assert sum(f.stat().st_size for f in BASE.rglob('*') if f.is_file())+len(data)<=10*1024**2
 with p.open('xb') as f:f.write(data)
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def main():
 ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['select','evidence']);args=ap.parse_args()
 assert socket.gethostname()=='fallsoft-production-20261106' and ROOT.resolve()==ROOT
 started=time.monotonic();os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2)
 def timeout(*unused):raise TimeoutError('120s probe pass ceiling')
 signal.signal(signal.SIGALRM,timeout);signal.alarm(120)
 assert shutil.disk_usage(ROOT).free>=8*1024**3+10*1024**2
 out=BASE/args.stage;out.mkdir(parents=True,exist_ok=False);r={'complete':False,'production':False,'stage':args.stage,'script_sha256':sha(Path(__file__))};db=None;en=None
 try:
  plan=json.loads((HERE/'missing-support-probe-r01-protocol.json').read_text());assert r['script_sha256']==plan['script_sha256'];r['protocol_sha256']=sha(HERE/'missing-support-probe-r01-protocol.json')
  for name,b in plan['inputs'].items():assert sha(Path(b['path']))==b['sha256'],name
  r['input_bindings']=plan['inputs'];paths={k:Path(v['path']) for k,v in plan['inputs'].items()}
  db=sqlite3.connect(paths['heads'].as_uri()+'?mode=ro&immutable=1',uri=True);db.execute('PRAGMA query_only=ON');db.execute('PRAGMA cache_size=-8192')
  keys={x['source_key']:x for x in json.load(gzip.open(paths['keys'],'rt'))}
  if args.stage=='select':
   excluded=set(json.loads(paths['prior_exclusions'].read_text())['hashes']);review=json.loads(paths['review_packet'].read_text());review_ids=set()
   for c in review['cases']:
    review_ids.add(c['source_id']);excluded.add(fingerprint(c['source']))
    for _,text in c['review_only_preceding_context']:excluded.add(fingerprint(text))
   for proof in review['context_proofs'].values():excluded.add(fingerprint(proof['full_parallel_record']['source']['text']))
   write(out/'exposure-freeze.json',{'hashes':sorted(excluded),'source_ids':sorted(review_ids),'scope':plan['exposure_scope']})
   shared=set();eligible=set();aligned=set()
   for key,blob in db.execute('SELECT source_key,proof FROM contexts ORDER BY id'):
    hs=json.loads(zlib.decompress(blob))['result']['heads'];aligned.add(key)
    if hs:shared.add(key)
    if any(any(m['structural_eligible'] for m in h['shared_senses']) for h in hs):eligible.add(key)
   assert (len(aligned),len(shared),len(eligible))==(19960,15967,3524)
   pool=[];counts=collections.Counter();first20=[]
   with gzip.open(paths['decisions'],'rt') as ds,paths['geometry'].open() as gs,paths['annotations'].open() as anns:
    for i,(dl,gl) in enumerate(zip(ds,gs,strict=True)):
     row,g,a=json.loads(dl),json.loads(gl),json.loads(next(anns));assert row['id']==g['id']==a['id'] and row['text']==g['text'] and a['pass']==0
     assert a['source_sha256']==hashlib.sha256(row['text'].encode()).hexdigest()
     if i<20:first20.append((a['id'],a['source_sha256'],a['tokens']))
     raw=row['text'].encode('utf-16-le');ks={norm(raw[2*l:2*u].decode('utf-16-le')) for l,u in g['native_window_ranges_utf16']}
     if not ks&shared or ks&eligible:continue
     counts['no_eligible_link_messages']+=1;assert not row['candidates'] and not row['decisions']['all_function']['expanded']['selected_indices']
     native={tuple(x) for x in row['native_words_utf16']};scope=[t for t in a['tokens'] if tuple(t[:2]) in native and t[2] in ['NOUN','ADJ','ADV']]
     if not scope:continue
     counts['with_in_scope_words']+=1
     if row['id'] in review_ids or fingerprint(row['text']) in excluded:counts['review_exposed_excluded']+=1;continue
     pool.append({'source_id':row['id'],'source_sha256':a['source_sha256'],'sampling_hash':hashlib.sha256(row['id'].encode()).hexdigest(),'in_scope_word_count':len(scope)})
    repeats=[json.loads(x) for x in anns];assert len(repeats)==20 and [(x['id'],x['source_sha256'],x['tokens']) for x in repeats]==first20 and all(x['pass']==1 for x in repeats)
   assert counts['no_eligible_link_messages']==3190 and counts['with_in_scope_words']==2971
   pool.sort(key=lambda x:(x['sampling_hash'],x['source_id']));selected=pool[:12];assert len(selected)==12
   write(out/'selection.json',{'production':False,'before_selected_examples_collected':True,'method':'SHA256(source ID UTF8), ascending; no target/classifier-quality based reselection','selected':selected,'eligible_unexposed_pool':len(pool),'cohort_counts':dict(counts),'exposure_sha256':sha(out/'exposure-freeze.json'),'protocol_sha256':r['protocol_sha256']});r['selected_count']=12
  else:
   previous=BASE/'select';pr=json.loads((previous/'receipt.json').read_text());assert pr['complete'] and pr['protocol_sha256']==r['protocol_sha256']
   for name,b in pr['outputs'].items():assert sha(previous/name)==b['sha256']
   selection=json.loads((previous/'selection.json').read_text());wanted={x['source_id']:x for x in selection['selected']};r['selection_sha256']=sha(previous/'selection.json')
   adapter=load('frozen_head_adapter',paths['adapter']);oldplan=json.loads(paths['head_protocol'].read_text());helperpaths={k:Path(v['remote']) for k,v in oldplan['inputs'].items()}
   for name in ['old_projector','family_control','content_baseline','tokenizer','normalizer','head_helper','lookup_key_dependency']:
    assert sha(helperpaths[name])==oldplan['inputs'][name]['sha256']
   pure=adapter.helpers(types.SimpleNamespace(paths=helperpaths));headhelper=load('frozen_head_helper',helperpaths['head_helper'])
   control=json.loads(helperpaths['family_control'].read_text());baseline=json.loads(helperpaths['content_baseline'].read_text());env={'norm':pure.norm,'tokenize':pure.tokenize};adapter.ast_functions(helperpaths['old_projector'],['classify'],env,method='Producer')
   tree=ast.parse(helperpaths['old_projector'].read_text());init=next(n for n in next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Producer').body if isinstance(n,ast.FunctionDef) and n.name=='__init__');update=next(n for n in ast.walk(init) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='update' and isinstance(n.func.value,ast.Attribute) and n.func.value.attr=='function')
   classifier=types.SimpleNamespace(function={e['source'] for p in baseline['pairs'].values() for e in p['entries'] if e['category']=='function'}|ast.literal_eval(update.args[0]),roles={k:set(v) for k,v in control['source_roles'].items()},families=control['source_families'])
   en=sqlite3.connect(paths['dictionary_en'].as_uri()+'?mode=ro&immutable=1',uri=True);en.execute('PRAGMA cache_size=-8192');ann={}
   with paths['annotations'].open() as f:
    for line in f:
     a=json.loads(line)
     if a['id'] in wanted and a['pass']==0:ann[a['id']]=a
   context_ids=dict(db.execute('SELECT source_key,id FROM contexts'));cases=[];proofs={};classifier_counts=collections.Counter();diagnostics=collections.Counter()
   with paths['geometry'].open() as f:
    for line in f:
     g=json.loads(line)
     if g['id'] not in wanted:continue
     text=g['text'];assert hashlib.sha256(text.encode()).hexdigest()==wanted[g['id']]['source_sha256'];off=adapter.offsets(text);inverse={x:i for i,x in enumerate(off)};tokens=[{'text':t,'codepoints':[a,b],'utf16':[off[a],off[b]]} for t,a,b in pure.tokenize(text)]
     units=headhelper._dictionary_units(en,text,headhelper._tokens(text,tokens),headhelper._database_identity(en));native={tuple(x) for x in g['native_source_word_ranges_utf16']};starts={t['utf16'][0]:i for i,t in enumerate(tokens)};ends={t['utf16'][1]:i+1 for i,t in enumerate(tokens)};focuses=[]
     for left,right,tag,score in ann[g['id']]['tokens']:
      if (left,right) not in native or tag not in ['NOUN','ADJ','ADV']:continue
      word=text[inverse[left]:inverse[right]];category,anchors,knowledge=env['classify'](classifier,word);classifier_counts[category]+=1
      actual_units=[u for u in units if u['scope']['utf16']==[left,right]];containing=[{'unit_id':u['unit_id'],'text':u['scope']['text'],'tokens':u['scope']['tokens']} for u in units if u['scope']['utf16']!=[left,right] and u['scope']['utf16'][0]<=left<right<=u['scope']['utf16'][1]]
      form_records=[form for u in actual_units for form in u['forms']];source_summary={'forms':len(form_records),'complete_supported_forms':sum(x['complete'] and x['mode'] in [1,2] and x['pos'] in ['noun','adj','adv'] for x in form_records),'eligible_explicit_forms':sum(not x['reasons'] and any(not t['reasons'] for t in x['terms']) for x in form_records),'form_reason_overlap':dict(collections.Counter(reason for x in form_records for reason in x['reasons'])),'term_reason_overlap':dict(collections.Counter(reason for x in form_records for t in x['terms'] for reason in t['reasons']))}
      contexts=[]
      for a,b in g['native_window_ranges_utf16']:
       if not a<=left<right<=b:continue
       key=norm(text[inverse[a]:inverse[b]])
       if key not in keys:continue
       record=db.execute('SELECT id,proof FROM contexts WHERE id=?',(context_ids.get(key),)).fetchone()
       if record is None:contexts.append({'source_key':key,'message_context_utf16':[a,b],'status':'no_aligned_context'});continue
       cid,blob=record;proof=json.loads(zlib.decompress(blob));v=proof['variant'];st=proof['full_parallel_record']['source']['tokens'];ss,se=v['source_start'],v['source_end'];first,last=starts.get(a),ends.get(b);fa,fb=starts.get(left),ends.get(right);binding=None
       if None not in [first,last,fa,fb] and [norm(t['text']) for t in tokens[first:last]]==[norm(t['text']) for t in st[ss:se]]:binding=[ss+fa-first,ss+fb-first]
       if cid not in proofs:
        pair=proof['full_parallel_record'];proofs[cid]={'source_key':key,'variant':v,'pair_id':pair['pair_id'],'full_source_witness':pair['source']['text'],'full_target_witness':pair['target']['text'],'source_context':proof['result']['source_context'],'target_context':proof['result']['target_context'],'all_target_variant_ids':[x['id'] for x in proof['all_ranked_variants']],'other_variants_not_reselected':True,'focus_evidence':{}}
       evidence_key=enc(binding);matches=[x for x in proof['result']['heads'] if x['source_tokens']==binding] if binding else []
       source_rejected=[x for x in proof['result']['rejected'] if x['kind']=='unit' and x['side']=='source' and x['unit']['scope']['tokens']==binding] if binding else []
       # Preserve every focus-linked match/reason, referenced forms and terms. No arbitrary cap or slicing.
       compact_heads=[{k:x[k] for k in ['head_id','source_unit_id','target_unit_id','source_tokens','target_tokens','target_text','reasons','structural_eligible','shared_senses','source_forms','target_forms']} for x in matches]
       evidence={'source_focus_tokens':binding,'all_focus_heads':compact_heads,'all_rejected_source_focus_units':source_rejected,'head_reason_overlap':dict(collections.Counter(r for x in matches for r in x['reasons'])),'shared_link_reason_overlap':dict(collections.Counter(r for x in matches for m in x['shared_senses'] for r in m['reasons']))}
       proofs[cid]['focus_evidence'][evidence_key]=evidence
       contexts.append({'source_key':key,'message_context_utf16':[a,b],'context_id':cid,'focus_evidence_key':evidence_key,'status':'exact_focus_bound' if binding else 'focus_or_context_geometry_unbound','focus_shared_heads':len(matches),'focus_link_records':sum(len(x['shared_senses']) for x in matches)})
      aligned=[c for c in contexts if 'context_id' in c];hasheads=any(c.get('focus_shared_heads') for c in aligned)
      diagnosis='classifier_'+category if category!='content' else 'no_complete_supported_source_form' if not source_summary['complete_supported_forms'] else 'no_retained_covering_source_context' if not contexts else 'no_aligned_covering_context' if not aligned else 'focus_geometry_unbound' if all(c['status']!='exact_focus_bound' for c in aligned) else 'no_shared_focus_link_in_top_witnesses' if not hasheads else 'shared_focus_links_rejected_by_frozen_rules'
      diagnostics[diagnosis]+=1;focuses.append({'word':word,'native_utf16':[left,right],'raw_tag':tag,'raw_score':score,'classifier':{'category':category,'anchors':anchors,'knowledge_ids':knowledge},'source_dictionary_summary':source_summary,'all_actual_source_units':actual_units,'containing_units':containing,'all_covering_contexts':contexts,'diagnosis':diagnosis,'cause_limit':'Within retained top witnesses and explicit historical form/link rules; dictionary-wide target alternatives and intended meaning are not established.'})
     assert len(focuses)==wanted[g['id']]['in_scope_word_count'];cases.append({'source_id':g['id'],'source_sha256':wanted[g['id']]['source_sha256'],'source':text,'native_words_utf16':g['native_source_word_ranges_utf16'],'in_scope_focuses':focuses})
   assert len(cases)==12;order={x['source_id']:i for i,x in enumerate(selection['selected'])};cases.sort(key=lambda x:order[x['source_id']])
   write(out/'probe.json',{'production':False,'selection_sha256':r['selection_sha256'],'cases':cases,'witness_proofs':proofs,'classifier_counts':dict(classifier_counts),'diagnosis_counts':dict(diagnostics),'limits':plan['limits_of_interpretation']});r.update(cases=len(cases),focuses=sum(len(x['in_scope_focuses']) for x in cases),witnesses=len(proofs),classifier_counts=dict(classifier_counts),diagnosis_counts=dict(diagnostics))
   headhelper.clear_unit_cache()
  r['complete']=True
 except BaseException as e:r['error']=repr(e);raise
 finally:
  if db:db.close()
  if en:en.close()
  r.update(seconds=time.monotonic()-started,memory={k:int(v.split()[0])*1024 for k,v in (l.split(':',1) for l in Path('/proc/self/status').read_text().splitlines() if l.startswith(('VmHWM:','VmPeak:')))},outputs={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in out.iterdir() if p.is_file()});write(out/'receipt.json',r);print(enc(r),flush=True)
if __name__=='__main__':main()
