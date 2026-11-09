#!/usr/bin/env python3
"""Narrow immutable crossing of r01 first-loss classes with native role scope.
Read existing proofs and decisions only. No selector, model, or guard changes.
"""
import collections,gzip,hashlib,importlib.util,json,os,resource,shutil,signal,socket,sqlite3,time,zlib
from pathlib import Path
HERE=Path(__file__).resolve().parent
HELPER=HERE/'loss-accounting-r01.py'
HELPER_SHA='5165d80b0475177f9e5567e4974479612fb48ae8995539fc88b3d22df2345a8f'
assert hashlib.sha256(HELPER.read_bytes()).hexdigest()==HELPER_SHA
spec=importlib.util.spec_from_file_location('frozen_loss_helpers',HELPER);h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
ROOT=h.ROOT

def first_loss(row,window_state,arm,known):
    for stage in h.STAGES[:5]:
        if stage not in window_state:return 'no_'+stage
    cs=row['candidates'];indices=[i for i,c in enumerate(cs) if arm=='expanded' or c['fixed']]
    if not indices:return 'no_projected_candidate'
    for stage,reason in [('single_token','not_single_token_head'),('role_assessed','role_unassessed'),('role_compatible','role_conflict'),('content_classified','not_content_classified')]:
        indices=[i for i in indices if reason not in cs[i]['filter_reasons']]
        if not indices:return 'no_'+stage
    d=row['decisions'][known][arm];rejected={x['index']:set(x['reasons']) for x in d['rejected']}
    for stage,predicate in [('nonidentical',lambda i:not cs[i]['identical_face']),('literal_allowed',lambda i:'protected_focus' not in rejected.get(i,set())),('compound_allowed',lambda i:'inside_recognized_source_unit' not in rejected.get(i,set())),('known_allowed',lambda i:not rejected.get(i,set())&{'known_function','known_vocabulary'})]:
        indices=[i for i in indices if predicate(i)]
        if not indices:return 'no_'+stage
    if not d['pre_budget_indices']:return 'no_pre_budget'
    if not d['selected_indices']:return 'no_selected'
    return 'selected'

def main():
    assert socket.gethostname()=='fallsoft-production-20261106' and ROOT.resolve()==ROOT
    started=time.monotonic();os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2)
    def timeout(*unused):raise TimeoutError('120s scope-accounting ceiling')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(120)
    assert shutil.disk_usage(ROOT).free>=8*1024**3+5*1024**2
    out=ROOT/'outputs/loss-accounting-r02';out.mkdir(exist_ok=False);receipt={'complete':False,'production':False,'script_sha256':h.sha(Path(__file__))};db=None
    try:
        files=dict(h.FILES);files['r01_result']=('outputs/loss-accounting-r01/result.json','18277ff8935910d464af586d456e60130f580fe53a237e2de9c8063d7052af8a')
        for name,(rel,digest) in files.items():assert h.sha(ROOT/rel)==digest,name
        receipt['inputs']={k:{'path':str(ROOT/v[0]),'sha256':v[1]} for k,v in files.items()};receipt['helper']={'path':str(HELPER),'sha256':HELPER_SHA}
        old=json.loads((ROOT/files['r01_result'][0]).read_text());keys={x['source_key']:x for x in json.load(gzip.open(ROOT/files['keys'][0],'rt'))};phase={k:{'source_context'} for k in keys}
        db=sqlite3.connect((ROOT/files['heads'][0]).as_uri()+'?mode=ro&immutable=1',uri=True);db.execute('PRAGMA query_only=ON');db.execute('PRAGMA cache_size=-8192');contexts=0
        for key,blob in db.execute('SELECT source_key,proof FROM contexts ORDER BY id'):
            hs=json.loads(zlib.decompress(blob))['result']['heads'];state=phase[key];state.add('aligned_context');contexts+=1
            if hs:state.add('shared_head_context')
            if any(any(m['structural_eligible'] for m in x['shared_senses']) for x in hs):state.add('eligible_link_context')
            if any(x['structural_eligible'] for x in hs):state.add('structural_head_context')
        assert contexts==19960
        assert {s:sum(s in x for x in phase.values()) for s in h.STAGES[:5]}==old['source_keys']['stage_presence']
        groups=collections.defaultdict(lambda:collections.defaultdict(collections.Counter));cross=collections.defaultdict(lambda:collections.defaultdict(collections.Counter));exclusive=collections.defaultdict(collections.Counter);population=collections.Counter();rows=0;first20=[]
        with gzip.open(ROOT/files['decisions'][0],'rt') as ds,(ROOT/files['geometry'][0]).open() as gs,(ROOT/files['annotations'][0]).open() as anns:
            for dline,gline in zip(ds,gs,strict=True):
                row,g,a=json.loads(dline),json.loads(gline),json.loads(next(anns));assert row['id']==g['id']==a['id'] and row['text']==g['text'] and a['pass']==0
                assert a['source_sha256']==hashlib.sha256(row['text'].encode()).hexdigest()
                if rows<20:first20.append((a['id'],a['source_sha256'],a['tokens']))
                rows+=1;native={tuple(x) for x in row['native_words_utf16']};tags={(a,b):tag for a,b,tag,_ in a['tokens']};scope={x for x in native if tags.get(x) in ['NOUN','ADJ','ADV']};verbs={x for x in native if tags.get(x)=='VERB'};aux={x for x in native if tags.get(x)=='AUX'}
                bucket='zero' if not scope else 'one' if len(scope)==1 else 'two_plus';population['messages']+=1;population['in_scope_'+bucket]+=1
                states={arm:set() for arm in ['fixed','expanded']};raw=row['text'].encode('utf-16-le')
                for left,right in g['native_window_ranges_utf16']:
                    key=h.norm(raw[2*left:2*right].decode('utf-16-le'))
                    if key not in phase:continue
                    states['expanded']|=phase[key]
                    if keys[key]['fixed']:states['fixed']|=phase[key]
                for arm in ['fixed','expanded']:
                    focuses={tuple(c['focus_utf16']) for c in row['candidates'] if arm=='expanded' or c['fixed']};in_scope_focus=scope & focuses
                    for known in ['all_function','all_function_global300']:
                        label=arm+'|'+known;loss=first_loss(row,states[arm],arm,known);exclusive[label][loss]+=1;v=groups[label][loss];v['messages']+=1;v['in_scope_'+bucket]+=1;v['in_scope_word_occurrences']+=len(scope)
                        v['any_projected_focus']+=bool(focuses);v['in_scope_projected_focus']+=bool(in_scope_focus);v['in_scope_words_without_projected_focus']+=len(scope-focuses);v['in_scope_present_but_no_projected_in_scope_focus']+=bool(scope) and not in_scope_focus
                        if not scope:
                            v['zero_scope_VERB_present' if verbs else 'zero_scope_AUX_only_of_verb_tags' if aux else 'zero_scope_no_VERB_or_AUX']+=1
                        cross[label][loss][bucket+'|projected='+str(bool(focuses)).lower()+'|in_scope_projected='+str(bool(in_scope_focus)).lower()]+=1
                if rows%3000==0:print(json.dumps({'rows':rows,'seconds':time.monotonic()-started}),flush=True)
            repeats=[json.loads(x) for x in anns];assert len(repeats)==20 and all(x['pass']==1 for x in repeats)
            assert [(x['id'],x['source_sha256'],x['tokens']) for x in repeats]==first20
        assert rows==9535 and {k:dict(v) for k,v in exclusive.items()}==old['messages_exclusive_first_loss']
        for values in groups.values():
            for v in values.values():assert v['messages']==sum(v['in_scope_'+b] for b in ['zero','one','two_plus'])
        result={'production':False,'population':dict(population),'first_loss_parity_with_r01':True,'by_first_loss':{k:{a:dict(b) for a,b in v.items()} for k,v in groups.items()},'scope_and_focus_cross':{k:{a:dict(b) for a,b in v.items()} for k,v in cross.items()},'definitions':{'in_scope':'An existing frozen OpenNLP NOUN/ADJ/ADV token whose full UTF16 range equals one retained native word. No new annotation or confidence threshold.','projected_focus':'Any recorded structurally eligible projected candidate in this arm before actual-role/content/same-face/mask/known/selection filters.','in_scope_projected_focus':'Such a projected focus exactly matches an in-scope native word.','verb_only_proxy':'zero_scope_VERB_present plus zero_scope_AUX_only_of_verb_tags: at least one VERB/AUX and no in-scope NOUN/ADJ/ADV; other function/proper-name/unmapped words can still exist. This is not literally all words are verbs.','zero_scope_no_VERB_or_AUX':'No exact native token in either role group; may include proper names, interjections, closed classes or tokenization/unassessed cases.','first_loss':'Same ordered availability attribution as immutable r01, checked exactly for all four arm/state combinations; not recoverable correctness.'},'limits':['NOUN/ADJ/ADV tags indicate diagnostic scope, not verified vocabulary meanings or correct tags.','An in-scope word without a projected focus may lack a source context, a retained relation, a complete supported form or a fitting witness; this crossing does not isolate those causes.','VERB/AUX absence from current emission policy is intentional, but AUX is often grammar rather than vocabulary.','No raw samples, proof copies, selector changes, guard relaxation or semantic claims.']}
        h.write(out/'result.json',result);receipt['complete']=True
    except BaseException as e:receipt['error']=repr(e);raise
    finally:
        if db:db.close()
        receipt.update(seconds=time.monotonic()-started,memory={k:int(v.split()[0])*1024 for k,v in (x.split(':',1) for x in Path('/proc/self/status').read_text().splitlines() if x.startswith(('VmHWM:','VmPeak:')))},outputs={p.name:{'bytes':p.stat().st_size,'sha256':h.sha(p)} for p in out.iterdir() if p.is_file()});h.write(out/'receipt.json',receipt);print(json.dumps(receipt),flush=True)
if __name__=='__main__':main()
