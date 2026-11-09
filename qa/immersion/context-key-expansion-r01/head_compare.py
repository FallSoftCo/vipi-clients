#!/usr/bin/env python3
"""Frozen production-only context/head experiment. Never fits or calls a model.
Stages are individually single-shot; failed directories must remain for review.
Dependencies are immutable, hash-bound source modules or unchanged AST functions.
"""
import argparse, ast, collections, contextlib, gzip, hashlib, importlib.util
import itertools, json, math, os, re, resource, shutil, signal, socket, sqlite3
import sys, time, types, unicodedata, zlib
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = Path('/srv/fallsoft/staging/vipi-context-key-expansion-20261109-r01')
OLD = Path('/srv/fallsoft/staging/vipi-tatoeba-domain-comparison-20261108-r01')
ARM = 'grow-diag-final-and'
KNOWN = ['all_function', 'all_function_global300']
STRATA = ['empty_gain', 'depth_loss', 'new_long_context', 'other_change']
MiB = 1024**2

def enc(x): return json.dumps(x, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
def digest(x): return hashlib.sha256(x).hexdigest()
def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(MiB), b''): h.update(b)
    return h.hexdigest()
def write(p, x):
    data = (enc(x)+'\n').encode()
    with Path(p).open('xb') as f: f.write(data)
def vm():
    return {k: int(v.split()[0])*1024 for k,v in (s.split(':',1) for s in Path('/proc/self/status').read_text().splitlines() if s.startswith(('VmHWM:', 'VmPeak:', 'VmRSS:')))}
def ro(p):
    db=sqlite3.connect(Path(p).as_uri()+'?mode=ro&immutable=1', uri=True)
    db.row_factory=sqlite3.Row; db.execute('PRAGMA cache_size=-8192'); return db
def load(name,p):
    spec=importlib.util.spec_from_file_location(name,p); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def ast_functions(path, names, env, assignments=(), method=None):
    tree=ast.parse(Path(path).read_text()); nodes=[]
    for name in assignments:
        nodes.append(next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets)))
    body=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==method).body if method else tree.body
    nodes.extend(next(n for n in body if isinstance(n,ast.FunctionDef) and n.name==name) for name in names)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),env)
    return env

class Run:
    def __init__(self,stage):
        assert socket.gethostname()=='fallsoft-production-20261106'
        assert ROOT.resolve()==ROOT and OLD.resolve()==OLD
        assert HERE==ROOT/'code/qa/immersion/context-key-expansion-r01'
        self.plan=json.loads((HERE/'head-protocol-r01.json').read_text())
        assert sha(__file__)==self.plan['code_hashes']['head_compare.py']
        self.stage=stage; self.started=time.monotonic()
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))}); os.nice(10)
        resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2)
        def timeout(*unused): raise TimeoutError('1200s stage ceiling')
        signal.signal(signal.SIGALRM,timeout); signal.alarm(1200)
        assert shutil.disk_usage(ROOT).free>=8*1024**3+512*MiB
        self.out=ROOT/'outputs'/stage; self.out.mkdir(parents=True,exist_ok=False)
        self.paths={}; self.receipt={'complete':False,'stage':stage,'production':False,'protocol_sha256':sha(HERE/'head-protocol-r01.json'),'code_sha256':sha(__file__)}
        self.stack=contextlib.ExitStack()
    def verify(self):
        for name,b in self.plan['inputs'].items():
            p=Path(b['remote']); assert p.resolve()==p
            assert p.is_relative_to(ROOT/'inputs') or p.is_relative_to(ROOT/'code') or p.is_relative_to(OLD)
            assert p.stat().st_size==b['bytes'] and sha(p)==b['sha256'],name
            self.paths[name]=p
        for name,h in self.plan['code_hashes'].items(): assert sha(HERE/name)==h
        write(self.out/'freeze.json',self.receipt|{'before_outputs':True,'inputs':self.plan['inputs'],'policy':self.plan['policy']})
    def prior(self,stage):
        p=ROOT/'outputs'/stage; r=json.loads((p/'receipt.json').read_text())
        assert r['complete'] and r['protocol_sha256']==self.receipt['protocol_sha256']
        for name,b in r['outputs'].items(): assert sha(p/name)==b['sha256']
        return p
    def size(self,p): return sum(q.stat().st_size for q in p.rglob('*') if q.is_file())
    def guard(self,reserve=0):
        assert time.monotonic()-self.started<1200
        assert shutil.disk_usage(ROOT).free>=8*1024**3+reserve
        assert self.size(ROOT/'outputs')+reserve<512*MiB-2*MiB,'aggregate output reservation exhausted; retain failure'
        assert self.size(self.out)+reserve<self.plan['stage_quotas_bytes'][self.stage]-MiB,'stage quota exhausted; no proof dropping'
    def db(self,name):
        db=sqlite3.connect(self.out/name); db.row_factory=sqlite3.Row
        db.execute('PRAGMA journal_mode=DELETE'); db.execute('PRAGMA temp_store=FILE'); db.execute('PRAGMA cache_size=-8192')
        # Reserve half the stage quota for journals, non-DB evidence and receipts.
        db.execute('PRAGMA max_page_count='+str(self.plan['stage_quotas_bytes'][self.stage]//8192))
        self.stack.callback(db.close); return db
    def gz(self,name): return self.stack.enter_context(gzip.open(self.out/name,'xb',compresslevel=6))
    def emit(self,f,obj):
        data=(enc(obj)+'\n').encode(); assert len(data)<=16*MiB,'oversized proof; fail instead of truncate'
        self.guard(len(data)+MiB); f.write(data); f.flush()
    def finish(self,error=None):
        self.stack.close()
        self.receipt.update(complete=error is None,error=error,seconds=time.monotonic()-self.started,process_memory_bytes=vm(),outputs={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in self.out.iterdir() if p.is_file()})
        write(self.out/'receipt.json',self.receipt); print(enc(self.receipt),flush=True)

def helpers(r):
    env={'math':math,'unicodedata':unicodedata,'re':re,'json':json,'hashlib':hashlib}
    ast_functions(r.paths['phrase_helper'],['crosses_stop','consistent_targets','parse_links','lexical_score'],env,['STOPS'])
    ast_functions(r.paths['normalizer'],['norm'],env)
    ast_functions(r.paths['tokenizer'],['tokenize'],env,['TOKEN'])
    return types.SimpleNamespace(**env)

def keys(r):
    data=json.load(gzip.open(r.paths['matched_keys'],'rt')); result={x['source_key']:x for x in data}
    assert len(data)==len(result)==25931 and sum(x['fixed'] for x in data)==6461
    fixed=json.loads(r.paths['fixed_keys'].read_text()); original={x['source_key'] for x in fixed['unigram_keys']+fixed['multiword_keys']}
    assert len(original)==8000 and len(fixed['unigram_keys'])==3000
    assert all(x['fixed']==(k in original) and (x['fixed'] or min(x['native_word_costs'])>=2) for k,x in result.items())
    return result

def preflight(r):
    inventory=keys(r)
    r.receipt['resource_estimate']={'source_matched_keys':len(inventory),'corpus_occurrences':sum(x['corpus_occurrences'] for x in inventory.values()),'maximum_interval_expansions_per_occurrence':78,'proof_volume_not_yet_measured':True,'output_policy':'Per-stage disk reservations and SQLite max_page_count; complete alternatives or explicit failed stage, never success with truncation. No fit/corpus model jobs.'}
    r.receipt['free_bytes']=shutil.disk_usage(ROOT).free
    r.receipt['staged_input_bytes']=sum(b['bytes'] for b in r.plan['inputs'].values() if b['remote'].startswith(str(ROOT)))
    assert r.receipt['staged_input_bytes']+512*MiB<=int(1.25*1024**3)

def extract(r):
    r.prior('preflight'); h=helpers(r); inventory=keys(r)
    def params(p):
        data={}
        with p.open() as f:
            for line in f:
                a,b,v=line.rstrip('\n').split('\t'); data[a,b]=float(v)
        return data
    forward=params(r.paths['forward_params']); reverse=params(r.paths['reverse_params'])
    db=r.db('variants.sqlite')
    db.executescript('''CREATE TABLE variants(id TEXT PRIMARY KEY,pair TEXT,arm TEXT,source_key TEXT,target_key TEXT,source_tokens INTEGER,target_tokens INTEGER,observations INTEGER,lexical_score_sum REAL,missing_lexical_parameters INTEGER,expanded_observations INTEGER,example_pair_index INTEGER,source_start INTEGER,source_end INTEGER,target_start INTEGER,target_end INTEGER) WITHOUT ROWID;
CREATE TABLE components(variant TEXT,component INTEGER,PRIMARY KEY(variant,component)) WITHOUT ROWID;
CREATE INDEX source_lookup ON variants(source_key);''')
    obs=r.gz('observations.jsonl.gz'); counts=collections.Counter(); hits=collections.Counter()
    with gzip.open(r.paths['pairs'],'rt') as pairs,r.paths['grow_align'].open() as align:
        for raw,al in zip(pairs,align,strict=True):
            row=json.loads(raw); assert row['index']==counts['pairs'] and row['pair']=='en-es'
            assert row['source']['component']==row['target']['component']
            st,tt=row['source']['tokens'],row['target']['tokens']; sw,tw=[t['text'].casefold() for t in st],[t['text'].casefold() for t in tt]
            links=h.parse_links(al,len(st),len(tt))
            for ss in range(len(st)):
                for se in range(ss+1,min(len(st),ss+8)+1):
                    if h.crosses_stop(sw[ss:se]): break
                    key=h.norm(row['source']['text'][st[ss]['codepoints'][0]:st[se-1]['codepoints'][1]])
                    if key not in inventory: continue
                    hits[key]+=1
                    for ts,te,lo,hi in h.consistent_targets(ss,se,tw,links):
                        target=h.norm(row['target']['text'][tt[ts]['codepoints'][0]:tt[te-1]['codepoints'][1]])
                        vid=digest(json.dumps(['en-es',ARM,key,target],ensure_ascii=False,separators=(',',':')).encode())
                        local={(s-ss,t-ts) for s,t in links if ss<=s<se and ts<=t<te}
                        value,missing=h.lexical_score(sw[ss:se],tw[ts:te],local,forward,reverse); expanded=int((ts,te)!=(lo,hi))
                        # Small per-transaction prospective reserve, before SQLite writes.
                        if counts['observations']%128==0:
                            db.commit(); obs.flush(); r.guard(8*MiB)
                        db.execute('INSERT INTO variants VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET observations=observations+1,lexical_score_sum=lexical_score_sum+excluded.lexical_score_sum,missing_lexical_parameters=missing_lexical_parameters+excluded.missing_lexical_parameters,expanded_observations=expanded_observations+excluded.expanded_observations',(vid,'en-es',ARM,key,target,se-ss,te-ts,1,value,missing,expanded,row['index'],ss,se,ts,te))
                        db.execute('INSERT OR IGNORE INTO components VALUES(?,?)',(vid,row['source']['component']))
                        o={'variant_id':vid,'pair_index':row['index'],'pair_id':row['pair_id'],'component':row['source']['component'],'direct_edge':row['provenance']['direct_edge'],'arm':ARM,'source_tokens':[ss,se],'target_tokens':[ts,te],'minimal_target_tokens':[lo,hi],'source_codepoints':[st[ss]['codepoints'][0],st[se-1]['codepoints'][1]],'source_utf16':[st[ss]['utf16'][0],st[se-1]['utf16'][1]],'target_codepoints':[tt[ts]['codepoints'][0],tt[te-1]['codepoints'][1]],'target_utf16':[tt[ts]['utf16'][0],tt[te-1]['utf16'][1]],'links':sorted(local),'lexical_score':value,'missing_lexical_parameters':missing}
                        # Flush in bounded batches, not per observation.
                        obs.write((enc(o)+'\n').encode()); counts['observations']+=1
                        counts['expanded_observations']+=expanded; counts['missing_lexical_parameters']+=missing
                    if counts['observations']%1000==0: db.commit(); obs.flush(); r.guard(2*MiB)
            counts['pairs']+=1
            if counts['pairs']%100==0: db.commit(); obs.flush(); r.guard(2*MiB)
            if counts['pairs']%2500==0: print(enc({'stage':'extract','counts':counts}),flush=True)
    assert counts['pairs']==40000
    assert dict(hits)=={k:x['corpus_occurrences'] for k,x in inventory.items()},'source occurrence parity'
    db.execute('CREATE TABLE ranked AS SELECT v.*,count(c.component) AS distinct_components,v.lexical_score_sum/v.observations AS mean_lexical_score FROM variants v JOIN components c ON c.variant=v.id GROUP BY v.id')
    db.execute('CREATE INDEX ranked_lookup ON ranked(source_key,distinct_components DESC,mean_lexical_score DESC,id)'); db.commit()
    old=ro(r.paths['fixed_variants']); checked=0; missing=0
    for key,entry in inventory.items():
        if not entry['fixed']: continue
        before=[dict(x) for x in old.execute('SELECT * FROM ranked WHERE source_key=? AND pair=? AND arm=? ORDER BY id',(key,'en-es',ARM))]
        after=[dict(x) for x in db.execute('SELECT * FROM ranked WHERE source_key=? ORDER BY id',(key,))]
        assert before==after,(key,'fixed subtable parity failed')
        if not before: missing+=1
        for v in before:
            assert list(map(tuple,old.execute('SELECT component FROM components WHERE variant=? ORDER BY component',(v['id'],))))==list(map(tuple,db.execute('SELECT component FROM components WHERE variant=? ORDER BY component',(v['id'],))))
        checked+=len(before)
    old.close(); write(r.out/'fixed-parity.json',{'complete':True,'fixed_source_present_keys':6461,'aligned_rows_checked':checked,'fixed_keys_without_aligned_row':missing,'absent_rows_compared_as_empty':True,'all_variant_fields_and_component_memberships':True})
    r.receipt['counts']=dict(counts)

def heads(r):
    extracted=r.prior('extract'); parity=json.loads((extracted/'fixed-parity.json').read_text()); assert parity['complete']
    h=helpers(r); inventory=keys(r)
    helper=load('frozen_context_heads',r.paths['head_helper'])
    en=ro(r.paths['dictionary_en']); es=ro(r.paths['dictionary_es']); r.stack.callback(en.close); r.stack.callback(es.close); r.stack.callback(helper.clear_unit_cache)
    variants=ro(extracted/'variants.sqlite'); r.stack.callback(variants.close)
    bypair=collections.defaultdict(list)
    for key in sorted(inventory):
        top=variants.execute('SELECT * FROM ranked WHERE source_key=? ORDER BY distinct_components DESC,mean_lexical_score DESC,id LIMIT 1',(key,)).fetchone()
        if top: bypair[top['example_pair_index']].append(dict(top))
    db=r.db('heads.sqlite'); db.executescript('CREATE TABLE contexts(id TEXT PRIMARY KEY,source_key TEXT, fixed INTEGER,proof BLOB) WITHOUT ROWID; CREATE TABLE heads(id TEXT PRIMARY KEY,context TEXT,source_key TEXT,fixed INTEGER,record TEXT) WITHOUT ROWID; CREATE INDEX head_lookup ON heads(source_key);')
    counts=collections.Counter()
    with gzip.open(r.paths['pairs'],'rt') as pairs,r.paths['forward_align'].open() as fa,r.paths['reverse_align'].open() as ra:
        for raw,fline,rline in zip(pairs,fa,ra,strict=True):
            row=json.loads(raw); wanted=bypair.get(row['index'],[])
            if not wanted: continue
            s,t=row['source'],row['target']; f=h.parse_links(fline,len(s['tokens']),len(t['tokens'])); rev=h.parse_links(rline,len(s['tokens']),len(t['tokens']))
            for v in wanted:
                a,b=v['source_start'],v['source_end']; c,d=v['target_start'],v['target_end']; st,tt=s['tokens'],t['tokens']
                assert h.norm(s['text'][st[a]['codepoints'][0]:st[b-1]['codepoints'][1]])==v['source_key']
                assert h.norm(t['text'][tt[c]['codepoints'][0]:tt[d-1]['codepoints'][1]])==v['target_key']
                result=helper.derive_heads(s['text'],t['text'],st,tt,[a,b],[c,d],f,rev,en,es)
                alternatives=[dict(x) for x in variants.execute('SELECT * FROM ranked WHERE source_key=? ORDER BY distinct_components DESC,mean_lexical_score DESC,id',(v['source_key'],))]
                proof={'variant':v,'full_parallel_record':row,'forward_links':sorted(f),'reverse_links':sorted(rev),'all_ranked_variants':alternatives,'result':result}
                payload=zlib.compress(enc(proof).encode()); assert len(payload)<=16*MiB
                r.guard(len(payload)*2+2*MiB)
                fixed=int(inventory[v['source_key']]['fixed']); db.execute('INSERT INTO contexts VALUES(?,?,?,?)',(v['id'],v['source_key'],fixed,payload))
                for head in result['heads']:
                    counts['all_heads']+=1; counts.update('rejected:'+x for x in head['reasons'])
                    if not head['structural_eligible']: continue
                    eligible=[m for m in head['shared_senses'] if m['structural_eligible']]
                    sa,sb=head['source_tokens']; hid=v['id']+':'+head['head_id']
                    record={'id':hid,'context_id':v['id'],'source_key':v['source_key'],'fixed':bool(fixed),'source_context_token_text':[h.norm(x['text']) for x in st[a:b]],'source_focus_relative_tokens':[sa-a,sb-a],'target_face':head['target_text'],'source_pos':sorted({x['source_pos'] for x in eligible}),'head_shared_senses':eligible,'head_readings':head['readings'],'head_id':head['head_id']}
                    # Head readings remain an exact set bound to target terms, not an invented single pronunciation.
                    db.execute('INSERT INTO heads VALUES(?,?,?,?,?)',(hid,v['id'],v['source_key'],fixed,enc(record))); counts['eligible_heads']+=1
                counts['contexts']+=1
                db.commit(); r.guard(2*MiB)
            if counts['contexts']%100==0: print(enc({'stage':'heads','counts':counts}),flush=True)
    assert counts['contexts']==sum(map(len,bypair.values())); r.receipt['counts']=dict(counts)

def offsets(text):
    out=[0]
    for c in text: out.append(out[-1]+len(c.encode('utf-16-le'))//2)
    return out

def mixed(text,selected):
    raw=text.encode('utf-16-le')
    for c in sorted(selected,key=lambda x:x['focus_utf16'][0],reverse=True):
        a,b=c['focus_utf16'];raw=raw[:2*a]+c['target'].encode('utf-16-le')+raw[2*b:]
    return raw.decode('utf-16-le')

def project(r):
    hp=r.prior('heads'); h=helpers(r)
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
    db=ro(hp/'heads.sqlite'); en=ro(r.paths['dictionary_en']); r.stack.callback(db.close); r.stack.callback(en.close); r.stack.callback(headhelper.clear_unit_cache)
    output=r.gz('decisions.jsonl.gz'); counts=collections.defaultdict(collections.Counter); seen=[]
    inventory=keys(r); review=load('head_review',HERE/'head_review.py').Selection(r.plan, json.loads(r.paths['exclusions'].read_text())['hashes'])
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
            review.consider(trace); r.emit(output,trace)
            if len(seen)%250==0: print(enc({'stage':'project','rows':len(seen)}),flush=True)
    assert seen==list(sources)
    write(r.out/'review-selection-freeze.json',review.freeze()); write(r.out/'metrics.json',dict(counts)); r.receipt['rows']=len(seen)

def packet(r):
    project_dir=r.prior('project'); heads_dir=r.prior('heads')
    module=load('head_review',HERE/'head_review.py'); module.packet(r,project_dir,heads_dir)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('stage',choices=['preflight','extract','heads','project','packet']); args=ap.parse_args()
    run=Run(args.stage)
    try:
        run.verify(); globals()[args.stage](run); run.guard(); run.finish()
    except BaseException as e:
        run.finish(repr(e)); raise
if __name__=='__main__': main()
