#!/usr/bin/env python3
"""Single-shot research stages over immutable retained evidence; no inference."""
import argparse,ast,collections,contextlib,gzip,hashlib,importlib.util,json,os,resource,shutil,signal,socket,sqlite3,time,types,zlib
from pathlib import Path
from mechanism import rescued_link,occurrence_reasons,competition
HERE=Path(__file__).resolve().parent
ROOT=Path('/srv/fallsoft/staging/vipi-source-name-scope-20261109-r01')
OLD=Path('/srv/fallsoft/staging/vipi-context-key-expansion-20261109-r01')
MiB=1024**2
KNOWN=['all_function','all_function_global300']
def enc(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(MiB),b''):h.update(b)
 return h.hexdigest()
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def ro(p):
 db=sqlite3.connect(Path(p).as_uri()+'?mode=ro&immutable=1',uri=True);db.row_factory=sqlite3.Row;db.execute('PRAGMA cache_size=-8192');return db
class Run:
 def __init__(self,stage):
  assert socket.gethostname()=='fallsoft-production-20261106' and HERE==ROOT/'code' and ROOT.resolve()==ROOT
  self.stage=stage;self.started=time.monotonic();self.plan=json.loads((HERE/'protocol.json').read_text());self.stack=contextlib.ExitStack()
  os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2)
  def timeout(*args):raise TimeoutError('frozen stage deadline')
  signal.signal(signal.SIGALRM,timeout);signal.alarm(self.plan['seconds'][stage])
  assert shutil.disk_usage(ROOT).free>=8*1024**3+128*MiB
  self.out=ROOT/'outputs'/stage;self.out.mkdir(parents=True,exist_ok=False)
  self.receipt={'complete':False,'production':False,'stage':stage,'protocol_sha256':sha(HERE/'protocol.json')}
  self.paths={k:Path(v['path']) for k,v in self.plan['inputs'].items()}
 def verify(self):
  for name,digest in self.plan['code_hashes'].items():assert sha(HERE/name)==digest,name
  for name,p in self.paths.items():assert p.resolve()==p and sha(p)==self.plan['inputs'][name]['sha256'],name
  self.adapter=load('original_adapter',self.paths['adapter'])
  self.write('freeze.json',{'before_outputs':True,'protocol_sha256':self.receipt['protocol_sha256'],'code_hashes':self.plan['code_hashes'],'inputs':self.plan['inputs']})
 def guard(self,extra=0):
  assert sum(p.stat().st_size for p in self.out.rglob('*') if p.is_file())+extra<self.plan['stage_output_bytes'][self.stage],'stage quota; no proof dropping'
  assert sum(p.stat().st_size for p in (ROOT/'outputs').rglob('*') if p.is_file())+extra<128*MiB-MiB,'aggregate quota; never drop alternatives'
 def write(self,name,x):
  b=(enc(x)+'\n').encode();self.guard(len(b))
  with (self.out/name).open('xb') as f:f.write(b)
 def prior(self,stage):
  p=ROOT/'outputs'/stage;r=json.loads((p/'receipt.json').read_text());assert r['complete'] and r['protocol_sha256']==self.receipt['protocol_sha256']
  for name,b in r['outputs'].items():assert sha(p/name)==b['sha256']
  return p
 def gz(self,name):return self.stack.enter_context(gzip.open(self.out/name,'xb',compresslevel=6))
 def emit(self,f,x):
  b=(enc(x)+'\n').encode();self.guard(len(b)+MiB);f.write(b);f.flush()
 def finish(self,error=None):
  self.stack.close();self.receipt.update(complete=error is None,error=error,seconds=time.monotonic()-self.started,memory={k:int(v.split()[0])*1024 for k,v in (s.split(':',1) for s in Path('/proc/self/status').read_text().splitlines() if s.startswith(('VmHWM:','VmPeak:')))},outputs={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in self.out.iterdir() if p.is_file()})
  self.write('receipt.json',self.receipt);print(enc(self.receipt),flush=True)

def catalog(r):
 old=ro(r.paths['heads']);en=ro(r.paths['dictionary_en']);r.stack.callback(old.close);r.stack.callback(en.close)
 helper=load('original_head_helper',r.paths['head_helper']);h=r.adapter.helpers(r)
 db=sqlite3.connect(r.out/'catalog.sqlite');r.stack.callback(db.close);db.execute('PRAGMA cache_size=-8192');db.execute('PRAGMA max_page_count=4096')
 db.executescript('CREATE TABLE heads(id TEXT PRIMARY KEY,source_key TEXT,baseline INTEGER,experimental INTEGER,record TEXT,audit TEXT) WITHOUT ROWID; CREATE INDEX lookup ON heads(source_key);')
 counts=collections.Counter();baseline_ids=set()
 for cid,key,fixed,blob in old.execute('SELECT id,source_key,fixed,proof FROM contexts ORDER BY id'):
  p=json.loads(zlib.decompress(blob));v=p['variant'];st=p['full_parallel_record']['source']['tokens'];a,b=v['source_start'],v['source_end'];prepared=[]
  for head in p['result']['heads']:
   sf={f['form_id']:f for f in head['source_forms']};tf={f['form_id']:f for f in head['target_forms']}
   source_key=helper.lookup_key(head['source_text'],'en');g=en.execute('SELECT blocked,target_blocked,protect_inner,reason FROM guards WHERE normalized=?',(source_key,)).fetchone();guard=dict(g) if g else None
   # Exact source unit identity: guard lookup is bound to the retained source scope/key.
   scope={'tokens':head['source_tokens'],'codepoints':head['source_codepoints'],'utf16':head['source_utf16'],'text':head['source_text']}
   assert helper._identity(['en',scope,source_key])==head['source_unit_id']
   overrides=[m for m in head['shared_senses'] if rescued_link(m,sf[m['source_form_id']],tf[m['target_form_id']],guard)]
   eligible=[m for m in head['shared_senses'] if m['structural_eligible']]+overrides
   pre_reasons=[x for x in head['reasons'] if x not in ['no_eligible_shared_sense_pos_number','competing_target_geometry']]
   pre=bool(eligible) and not pre_reasons
   ident=cid+':'+head['head_id'];original=old.execute('SELECT record FROM heads WHERE id=?',(ident,)).fetchone()
   assert bool(original)==head['structural_eligible']
   if original:
    baseline_ids.add(ident);record=json.loads(original[0])
    oldeligible=[m for m in head['shared_senses'] if m['structural_eligible']];sa,sb=head['source_tokens']
    reconstructed={'id':ident,'context_id':cid,'source_key':key,'fixed':bool(fixed),'source_context_token_text':[h.norm(t['text']) for t in st[a:b]],'source_focus_relative_tokens':[sa-a,sb-a],'target_face':head['target_text'],'source_pos':sorted({m['source_pos'] for m in oldeligible}),'head_shared_senses':oldeligible,'head_readings':head['readings'],'head_id':head['head_id']}
    assert reconstructed==record and enc(reconstructed)==original[0],'baseline catalog reconstruction differs'
   else:
    sa,sb=head['source_tokens'];record={'id':ident,'context_id':cid,'source_key':key,'fixed':bool(fixed),'source_context_token_text':[h.norm(t['text']) for t in st[a:b]],'source_focus_relative_tokens':[sa-a,sb-a],'target_face':head['target_text'],'source_pos':sorted({m['source_pos'] for m in eligible}),'head_id':head['head_id'],'head_readings':[{'text':m['target_reading'],'target_term_id':m['target_term_id'],'target_form_id':m['target_form_id'],'sense_id':m['sense_id'],'structural_eligible':True} for m in eligible if m['target_reading']]}
   audit={'context_id':cid,'original_proof_blob_sha256':hashlib.sha256(blob).hexdigest(),'head_id':head['head_id'],'source_unit_id':head['source_unit_id'],'source_guard_key':source_key,'source_guard':guard,'original_head_reasons':head['reasons'],'override_links':[{k:m[k] for k in ['sense_id','source_form_id','target_form_id','source_term_id','target_term_id','reasons']} for m in overrides],'precompetition_eligible':pre,'remaining_head_reasons':pre_reasons,'baseline':bool(original)}
   prepared.append((head,record,audit,pre));counts['all_heads']+=1;counts['override_link_records']+=len(overrides)
  conflicts=competition([(record['id'],head['source_tokens'],head['target_tokens']) for head,record,audit,pre in prepared if pre])
  for head,record,audit,pre in prepared:
   experimental=pre and record['id'] not in conflicts;audit['experimental_competing_geometry']=record['id'] in conflicts
   if audit['baseline'] or audit['override_links']:
    db.execute('INSERT INTO heads VALUES(?,?,?,?,?,?)',(record['id'],key,int(audit['baseline']),int(experimental),enc(record),enc(audit)))
   counts['baseline']+=audit['baseline'];counts['experimental']+=experimental;counts['new_structural']+=experimental and not audit['baseline'];counts['baseline_competition_loss']+=audit['baseline'] and not experimental
  counts['contexts']+=1
  if counts['contexts']%500==0:db.commit();r.guard(2*MiB)
 assert counts['contexts']==19960 and baseline_ids=={row[0] for row in old.execute('SELECT id FROM heads')}
 db.commit();r.receipt['counts']=dict(counts);r.write('baseline-parity.json',{'complete':True,'contexts':19960,'baseline_heads':len(baseline_ids),'all_original_record_fields_equal':True})

def project(r):
    catalog_dir=r.prior('catalog'); h=r.adapter.helpers(r)
    adapter=r.adapter; ast_functions=adapter.ast_functions; offsets=adapter.offsets; mixed=adapter.mixed
    headhelper=load('frozen_context_heads',r.paths['head_helper']); selector=load('frozen_selector',r.paths['selector'])
    comparator=load('frozen_comparator',r.paths['comparator']); literal=comparator.Comparator(json.loads(r.paths['literal_payload'].read_text()),json.loads(r.paths['literal_semantics'].read_text()))
    control=json.loads(r.paths['family_control'].read_text()); baseline=json.loads(r.paths['content_baseline'].read_text())
    env={'json':json,'hashlib':hashlib,'norm':h.norm,'tokenize':h.tokenize}
    ast_functions(r.paths['annotation_loader'],['annotations'],env)
    ast_functions(r.paths['old_projector'],['classify'],env,method='Producer')
    tree=ast.parse(r.paths['old_projector'].read_text())
    init=next(n for n in next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Producer').body if isinstance(n,ast.FunctionDef) and n.name=='__init__')
    update=next(n for n in ast.walk(init) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='update' and isinstance(n.func.value,ast.Attribute) and n.func.value.attr=='function')
    function={e['source'] for p in baseline['pairs'].values() for e in p['entries'] if e['category']=='function'}|ast.literal_eval(update.args[0])
    classifier=types.SimpleNamespace(function=function,roles={k:set(v) for k,v in control['source_roles'].items()},families=control['source_families'])
    classify=lambda text:env['classify'](classifier,text)
    freq=json.loads(r.paths['fixed_keys'].read_text()); ranked=sorted(freq['unigram_keys']+freq['multiword_keys'],key=lambda x:(-x['source_message_frequency'],-x['occurrence_frequency'],x['source_key']))
    ranks={x['source_key']:i for i,x in enumerate(ranked)}
    sources={x['id']:x['text'] for x in json.loads(r.paths['annotation_inputs'].read_text())['cases']}; assert len(sources)==9535
    annotation=env['annotations'](r.paths['annotations'],'opennlp',sources)
    db=ro(r.paths['heads']); en=ro(r.paths['dictionary_en']); r.stack.callback(db.close); r.stack.callback(en.close); r.stack.callback(headhelper.clear_unit_cache)
    output=r.gz('decisions.jsonl.gz'); counts=collections.defaultdict(collections.Counter); seen=[]
    inventory=r.adapter.keys(r); review=load('name_review',HERE/'review.py').Selection(r.plan)
    catalog_db=ro(catalog_dir/'catalog.sqlite'); r.stack.callback(catalog_db.close)
    enabled={x[0]:bool(x[1]) for x in catalog_db.execute('SELECT id,experimental FROM heads WHERE baseline=1')}
    old_trace=r.stack.enter_context(gzip.open(r.paths['decisions'],'rt')); changed_counts=collections.defaultdict(collections.Counter)
    with r.paths['geometry'].open() as stream:
        for line in stream:
            row=json.loads(line); ident,text=row['id'],row['text']; assert sources[ident]==text; seen.append(ident)
            off=offsets(text); inverse={x:i for i,x in enumerate(off)}; words=row['native_source_word_ranges_utf16']
            tok=h.tokenize(text); tokens=[{'text':x,'codepoints':[a,b],'utf16':[off[a],off[b]]} for x,a,b in tok]
            # Match historical helper bounds: inability to construct complete masks is a failed stage, not an empty mask.
            masks=headhelper.recognize_source_masks(text,tokens,en)['source_masks']; protected,_=literal.protections(text,off)
            starts={t['codepoints'][0]:i for i,t in enumerate(tokens)}; ends={t['codepoints'][1]:i+1 for i,t in enumerate(tokens)}
            candidates=[]; rejected=[]
            for left,right in row['native_window_ranges_utf16']:
                a,b=inverse[left],inverse[right]; key=h.norm(text[a:b])
                if key not in inventory: continue
                first,last=starts.get(a),ends.get(b)
                for hr in db.execute('SELECT record FROM heads WHERE source_key=? ORDER BY id',(key,)):
                    record=json.loads(hr[0]); reasons=[]
                    if first is None or last is None: rejected.append({'head':record['id'],'window':[left,right],'reason':'training_token_boundary'}); continue
                    actual=tokens[first:last]
                    if [h.norm(t['text']) for t in actual]!=record['source_context_token_text']: rejected.append({'head':record['id'],'window':[left,right],'reason':'context_token_sequence'}); continue
                    sa,sb=record['source_focus_relative_tokens']; assert 0<=sa<sb<=len(actual)
                    focus=[actual[sa]['utf16'][0],actual[sb-1]['utf16'][1]]; scope=selector.project_scope(text,words,focus)
                    if 'rejection' in scope: rejected.append({'head':record['id'],'window':[left,right],'reason':scope['rejection']}); continue
                    fa,fb=scope['codepoints']; original=text[fa:fb]; category,anchors,knowledge=classify(original)
                    evidence=annotation[ident].get(tuple(focus)); mapped={'NOUN':'noun','ADJ':'adj','ADV':'adv'}.get(evidence[0]) if evidence else None
                    if sb-sa!=1 or scope['cost']!=1: reasons.append('not_single_token_head')
                    if mapped is None: reasons.append('role_unassessed')
                    elif mapped not in record['source_pos']: reasons.append('role_conflict')
                    if category!='content': reasons.append('not_content_classified')
                    c={'id':record['id']+f'@{left}:{right}','head_id':record['id'],'context_id':record['context_id'],'fixed':record['fixed'],'focus_utf16':focus,'context_utf16':[left,right],'source':original,'target':record['target_face'],'reading':sorted({x['text'] for x in record['head_readings']}),'identical_face':h.norm(original)==h.norm(record['target_face']),'category':category,'content_anchor_words':anchors,'knowledge_ids':knowledge,'concept_id':classifier.families.get(h.norm(original),'lexical:'+h.norm(original)),'train_rank':ranks.get(key,10**9),'cost':scope['cost'],'source_key':key,'context_native_cost':sum(left<=x<y<=right for x,y in words),'role':{'raw':evidence,'mapped':mapped},'filter_reasons':reasons,'output_codepoints':scope['codepoints']}
                    candidates.append(c)
            assert len({c['id'] for c in candidates})==len(candidates)
            decisions={}
            for known in KNOWN:
                decisions[known]={}
                for arm in ['fixed','expanded']:
                    indices=[i for i,c in enumerate(candidates) if not c['filter_reasons'] and (arm=='expanded' or c['fixed'])]
                    chosen=selector.select([candidates[i] for i in indices],words,protected,masks,.25,known,control['learned_family_order'])
                    assert chosen==selector.select([candidates[i] for i in indices],words,protected,masks,.25,known,control['learned_family_order'])
                    translated={k:[indices[i] for i in chosen[k]] for k in ['selected_indices','pre_budget_indices','budget_only_indices']}
                    translated.update(budget=chosen['budget'],rejected=[dict(x,index=indices[x['index']]) for x in chosen['rejected']])
                    selected=[candidates[i] for i in translated['selected_indices']]; assert all(not c['identical_face'] for c in selected)
                    translated['mixed_output']=mixed(text,selected); decisions[known][arm]=translated
                    s=counts[arm+'|'+known]; s['messages']+=1; s['nonempty']+=bool(selected); s['changed_words']+=sum(c['cost'] for c in selected); s['selected_context_depth_sum']+=sum(c['context_native_cost'] for c in selected)
            trace={'id':ident,'text':text,'native_words_utf16':words,'source_masks':masks,'protected_ranges_utf16':protected,'candidates':candidates,'geometry_rejections':rejected,'decisions':decisions}
            expected=json.loads(next(old_trace));assert json.loads(enc(trace))==expected,('baseline full trace parity',ident)
            original_count=len(candidates); baseline_decisions=decisions;experimental_geometry_rejections=[]
            for left,right in row['native_window_ranges_utf16']:
                a,b=inverse[left],inverse[right]; key=h.norm(text[a:b])
                if key not in inventory: continue
                first,last=starts.get(a),ends.get(b)
                for hr in catalog_db.execute('SELECT record FROM heads WHERE source_key=? AND baseline=0 AND experimental=1 ORDER BY id',(key,)):
                    record=json.loads(hr[0]); reasons=[]
                    if first is None or last is None: experimental_geometry_rejections.append({'head':record['id'],'window':[left,right],'reason':'training_token_boundary'}); continue
                    actual=tokens[first:last]
                    if [h.norm(t['text']) for t in actual]!=record['source_context_token_text']: experimental_geometry_rejections.append({'head':record['id'],'window':[left,right],'reason':'context_token_sequence'}); continue
                    sa,sb=record['source_focus_relative_tokens']; assert 0<=sa<sb<=len(actual)
                    focus=[actual[sa]['utf16'][0],actual[sb-1]['utf16'][1]]; scope=selector.project_scope(text,words,focus)
                    if 'rejection' in scope: experimental_geometry_rejections.append({'head':record['id'],'window':[left,right],'reason':scope['rejection']}); continue
                    fa,fb=scope['codepoints']; original=text[fa:fb]; category,anchors,knowledge=classify(original)
                    evidence=annotation[ident].get(tuple(focus)); mapped={'NOUN':'noun','ADJ':'adj','ADV':'adv'}.get(evidence[0]) if evidence else None
                    if sb-sa!=1 or scope['cost']!=1: reasons.append('not_single_token_head')
                    if mapped is None: reasons.append('role_unassessed')
                    elif mapped not in record['source_pos']: reasons.append('role_conflict')
                    if category!='content': reasons.append('not_content_classified')
                    c={'id':record['id']+f'@{left}:{right}','head_id':record['id'],'context_id':record['context_id'],'fixed':record['fixed'],'focus_utf16':focus,'context_utf16':[left,right],'source':original,'target':record['target_face'],'reading':sorted({x['text'] for x in record['head_readings']}),'identical_face':h.norm(original)==h.norm(record['target_face']),'category':category,'content_anchor_words':anchors,'knowledge_ids':knowledge,'concept_id':classifier.families.get(h.norm(original),'lexical:'+h.norm(original)),'train_rank':ranks.get(key,10**9),'cost':scope['cost'],'source_key':key,'context_native_cost':sum(left<=x<y<=right for x,y in words),'role':{'raw':evidence,'mapped':mapped},'filter_reasons':reasons,'output_codepoints':scope['codepoints']}
                    c['filter_reasons']+=occurrence_reasons(c)
                    guard=en.execute('SELECT blocked,target_blocked,reason FROM guards WHERE normalized=?',(headhelper.lookup_key(original,'en'),)).fetchone()
                    if guard is None or not guard['blocked'] or guard['target_blocked'] or guard['reason']!='name':c['filter_reasons'].append('rescue_requires_exact_current_source_name_guard')
                    candidates.append(c)
            paired={}
            for known in KNOWN:
                indices=[i for i,c in enumerate(candidates) if not c['filter_reasons'] and (i>=original_count or enabled[c['head_id']])]
                chosen=selector.select([candidates[i] for i in indices],words,protected,masks,.25,known,control['learned_family_order'])
                translated={k:[indices[i] for i in chosen[k]] for k in ['selected_indices','pre_budget_indices','budget_only_indices']}
                translated.update(budget=chosen['budget'],rejected=[dict(x,index=indices[x['index']]) for x in chosen['rejected']])
                selected=[candidates[i] for i in translated['selected_indices']];assert all(not c['identical_face'] for c in selected)
                translated['mixed_output']=mixed(text,selected)
                paired[known]={'baseline':baseline_decisions[known]['expanded'],'experimental':translated}
                for arm,data in paired[known].items():
                    picked=[candidates[i] for i in data['selected_indices']];counter=changed_counts[arm+'|'+known]
                    counter['messages']+=1;counter['nonempty']+=bool(picked);counter['changed_words']+=sum(c['cost'] for c in picked)
            trace.update(decisions=paired,baseline_candidate_count=original_count,experimental_geometry_rejections=experimental_geometry_rejections,competition_removed_baseline_indices=[i for i,c in enumerate(candidates[:original_count]) if not enabled[c['head_id']]])
            review.consider(trace);r.emit(output,trace)
            if len(seen)%250==0: print(enc({'stage':'project','rows':len(seen)}),flush=True)
    assert seen==list(sources)
    assert next(old_trace,None) is None
    r.write('baseline-parity.json',{'complete':True,'messages':len(seen),'known_states':2,'full_original_fixed_and_expanded_trace_equal':True,'credited_only_after_full_parity':True})
    r.write('review-selection-freeze.json',review.freeze());r.write('metrics.json',dict(changed_counts));r.receipt['rows']=len(seen)

def packet(r):load('name_review',HERE/'review.py').packet(r)
def main():
 parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['catalog','project','packet']);args=parser.parse_args();r=Run(args.stage)
 try:r.verify();globals()[args.stage](r);r.guard();r.finish()
 except BaseException as e:r.finish(repr(e));raise
if __name__=='__main__':main()
