#!/usr/bin/env python3
"""Data-only corpus catalog projection onto retained actual native geometry.

No runtime provider, target rewriting or new meaning labels. All selected indices
refer to uncensored candidates; source masks apply across every comparison arm.
"""
import collections
import gzip
import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path
from extract_pgv import OUT,HERE,sha,guards,process_hwm,encoded,tokenize
from prepare_inputs import norm
from context_heads import recognize_source_masks,clear_unit_cache
from compile_context_heads import DICTIONARIES,HASHES
from project_native_selection import project_scope,select

QA=HERE.parent
sys.path.insert(0,str(QA/'coverage_ceiling_experiment'))
sys.path.insert(0,str(QA/'nlp-template-comparison-r01'))
from editorial_runtime_lookup_r03 import SourceLookup
from reference_compare import Comparator
GEOMETRY=Path('/home/ai/Development/investigations/vipi-android-readiness-20261107-r01/top-down-source-lookup-r01/tokenizer-r87b/rows.jsonl')
CONTROL=OUT.parent/'scaled-mechanism-cases-r01/editorial-runtime-candidate-r03.json'
BASELINE=QA/'coverage_ceiling_experiment/content-expansion-candidate-r01.json'
DENSITIES=[.1,.25,.5]
KNOWN=['none','all_function','all_function_global50','all_function_global100','all_function_global300']
ARMS=['mutual_word','raw_intersect','raw_grow','complete_grow','heads_grow','r03_shared_guards','heads_r03_union']

def offsets(text):
    result=[0]
    for c in text:result.append(result[-1]+len(c.encode('utf-16-le'))//2)
    return result

def training_tokens(text):
    off=offsets(text)
    return [dict(text=t,codepoints=[a,b],utf16=[off[a],off[b]]) for t,a,b in tokenize(text)]

def mixed(text,selected):
    raw=text.encode('utf-16-le')
    for c in sorted(selected,key=lambda r:r['focus_utf16'][0],reverse=True):
        a,b=c['focus_utf16'];raw=raw[:2*a]+c['target'].encode('utf-16-le')+raw[2*b:]
    return raw.decode('utf-16-le')

class Producer:
    def __init__(self,directory):
        self.directory=directory
        self.control=json.loads(CONTROL.read_text());self.baseline=json.loads(BASELINE.read_text())
        self.old=SourceLookup(self.baseline,self.control)
        self.roles={k:set(v) for k,v in self.control['source_roles'].items()}
        self.families=self.control['source_families'];self.order=self.control['learned_family_order']
        self.function={e['source'] for p in self.baseline['pairs'].values() for e in p['entries'] if e['category']=='function'}
        self.function.update({'i','a','an','the','to','of','and','or','but','if','in','on','at','for','by','as','is','am','are','was','were','be','been','being','it','its','you','your','we','our','he','his','she','her','they','their','this','that','these','those','my','me','us','them','not','no','yes','do','does','did','have','has','had','will','would','can','could','shall','should','may','might','must'})
        f=json.loads((OUT/'source-frequency-keys.json').read_text())
        ranked=sorted(f['unigram_keys']+f['multiword_keys'],key=lambda r:(-r['source_message_frequency'],-r['occurrence_frequency'],r['source_key']))
        self.ranks={r['source_key']:i for i,r in enumerate(ranked)}
        self.index=collections.defaultdict(list)
        with gzip.open(directory/'catalog.jsonl.gz','rt') as stream:
            for line in stream:
                r=json.loads(line)
                arm={('raw','mutual-word'):'mutual_word',('raw','intersect'):'raw_intersect',('raw','grow-diag-final-and'):'raw_grow',('dictionary_complete','grow-diag-final-and'):'complete_grow'}.get((r['choice_kind'],r['arm']))
                if arm:self.index[r['pair'],r['source_key']].append((arm,r))
        with gzip.open(directory/'heads-r02/heads-catalog.jsonl.gz','rt') as stream:
            for line in stream:
                r=json.loads(line);self.index[r['pair'],r['source_key']].append(('heads_grow',r))
        n=QA/'nlp-template-comparison-r01'
        self.literal=Comparator(json.loads((n/'payload.json').read_text()),json.loads((n/'semantics.json').read_text()))
        self.db=sqlite3.connect((DICTIONARIES/'d-en.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True)
        self.db.execute('PRAGMA cache_size=-16384')

    def classify(self,text):
        words=[norm(t) for t,_,_ in tokenize(text) if any(c.isalpha() for c in t)]
        anchors=[w for w in words if w not in self.function and self.roles.get(w,set())&{'noun','adj','adv','verb'}]
        unknown=[w for w in words if w not in self.function and w not in anchors]
        category='content' if anchors else 'unresolved' if unknown else 'function'
        ids=[self.families.get(w,'unmapped:'+w) for w in words if w not in self.function]
        return category,anchors,sorted(set(ids))

    def produce(self,row):
        text=row['text'];off=offsets(text);inverse={v:k for k,v in enumerate(off)}
        native=row['native_source_word_ranges_utf16'];tokens=training_tokens(text)
        protection,_=self.literal.protections(text,off)
        masks=recognize_source_masks(text,tokens,self.db)['source_masks']
        starts={r['codepoints'][0]:i for i,r in enumerate(tokens)};ends={r['codepoints'][1]:i+1 for i,r in enumerate(tokens)}
        per_pair={};rejections=collections.Counter()
        for pair in ['en-sw','en-es']:
            candidates=[];members=collections.defaultdict(list)
            for left,right in row['native_window_ranges_utf16']:
                a,b=inverse[left],inverse[right];key=norm(text[a:b]);records=self.index.get((pair,key))
                if not records:continue
                first,last=starts.get(a),ends.get(b)
                if first is None or last is None:
                    rejections[pair+':window_training_token_boundary']+=len(records);continue
                actual=tokens[first:last]
                for arm,record in records:
                    if [norm(t['text']) for t in actual]!=record['source_context_token_text']:
                        rejections[pair+':context_token_sequence_mismatch']+=1;continue
                    s,e=record['source_focus_relative_tokens']
                    if not 0<=s<e<=len(actual):raise ValueError('catalog focus outside context')
                    focus=[actual[s]['utf16'][0],actual[e-1]['utf16'][1]]
                    checked=project_scope(text,native,focus)
                    if 'rejection' in checked:
                        rejections[pair+':'+checked['rejection']]+=1;continue
                    fa,fb=checked['codepoints'];original=text[fa:fb]
                    category,anchors,knowledge=self.classify(original)
                    head=arm=='heads_grow'
                    concept=self.families.get(norm(original),'lexical:'+norm(original)) if head else 'phrase:'+key
                    c=dict(id=record.get('proof_id',record['catalog_id'])+f'@{left}:{right}',focus_utf16=focus,context_utf16=[left,right],
                           source=original,target=record['target_face'],reading=record.get('reading',''),
                           identical_face=norm(original)==norm(record['target_face']),category=category,
                           content_anchor_words=anchors,content_anchor_native_words=sum(bool(self.classify(text[inverse[x]:inverse[y]])[1]) for x,y in native if focus[0]<=x<y<=focus[1]),concept_id=concept,knowledge_ids=knowledge,
                           knowledge_basis='source-family-exhaustion-not-sense-learning' if head else 'source-vocabulary-exhaustion-not-phrase-learning',
                           train_rank=self.ranks.get(key,10**9),cost=checked['cost'],kind=arm,
                           catalog_id=record['catalog_id'],head_id=record.get('head_id'),
                           source_key=key,alternatives=record['alternatives'],context_target_key=record['target_key'],
                           emitted_target_key=norm(record['target_face']),head_shared_senses=record.get('head_shared_senses',[]),
                           expanded_observations=record['expanded_observations'],lexical_score=record['mean_lexical_score'],
                           source_context=text[a:b],output_codepoints=[fa,fb],semantic_approval=False)
                    members[arm].append(len(candidates));candidates.append(c)
            _,old,rejected,_=self.old.candidates(text,pair[3:]);rejections[pair+':r03_role_or_literal']+=len(rejected)
            for span in old:
                focus=[span['sourceStartUTF16'],span['sourceEndUTF16']];checked=project_scope(text,native,focus)
                if 'rejection' in checked:
                    rejections[pair+':r03_'+checked['rejection']]+=1;continue
                c=dict(id='r03:'+span['lexicon_id']+f'@{focus[0]}',focus_utf16=focus,context_utf16=focus,
                       source=span['original'],target=span['translated'],reading=span.get('reading',''),
                       identical_face=norm(span['original'])==norm(span['translated']),category=span['category'],
                       content_anchor_words=[norm(span['original'])] if span['category']=='content' else [],
                       content_anchor_native_words=checked['cost'] if span['category']=='content' else 0,
                       concept_id=span['concept_id'],knowledge_ids=[span['concept_id']],knowledge_basis='lexical-family',
                       train_rank=span['train_rank'],cost=checked['cost'],kind='r03_shared_guards',
                       output_codepoints=checked['codepoints'],source_context=span['original'],semantic_approval=False)
                members['r03_shared_guards'].append(len(candidates));candidates.append(c)
            for c in candidates:
                a,b=c['focus_utf16']
                c['crossing_mask_ids']=[m['unit_id'] for m in masks if (m['utf16'][0]<a<m['utf16'][1]<b or a<m['utf16'][0]<b<m['utf16'][1])]
                c['contained_mask_ids']=[m['unit_id'] for m in masks if [a,b]!=m['utf16'] and a<=m['utf16'][0]<m['utf16'][1]<=b]
            members['heads_r03_union']=members['heads_grow']+members['r03_shared_guards']
            per_pair[pair]=dict(candidates=candidates,members=dict(members))
        return per_pair,masks,protection,dict(rejections)

def main():
    start=time.monotonic();directory=OUT/'projection-r02';destination=directory/'contextual';destination.mkdir(exist_ok=False)
    assert sha(GEOMETRY)=='fc41c289c79d3d7d07a72b5f9041c359565f88cdca38deaf5cc0569530425780'
    assert sha(DICTIONARIES/'d-en.sqlite')==HASHES['en']
    hr=json.loads((directory/'heads-r02/heads-receipt.json').read_text());assert hr['complete']
    for name,value in hr['outputs'].items():assert sha(directory/'heads-r02'/name)==value['sha256']
    inputs=[Path(__file__),HERE/'project_native_selection.py',HERE/'context_heads.py',HERE/'projection-selection-addendum-r02.json',HERE/'contextual-projection-plan-r01.json',CONTROL,BASELINE,GEOMETRY,directory/'catalog.jsonl.gz',directory/'heads-r02/heads-catalog.jsonl.gz']
    local_sources=sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py' and str(Path(m.__file__).resolve()).startswith(str(QA.parents[1]))})
    inputs+=local_sources+[OUT/'source-frequency-keys.json',QA/'nlp-template-comparison-r01/payload.json',QA/'nlp-template-comparison-r01/semantics.json',HERE/'contextual-review-selection-r01.json']
    freeze=dict(production=False,before_contextual_output=True,inputs={str(p):sha(p) for p in inputs},arms=ARMS,densities=DENSITIES,known=KNOWN,
                dictionary_hashes=HASHES,source_rank='Combined frozen unigram/multiword keys sorted source-message frequency, occurrence frequency, key; R03 retains its prior TRAIN rank.',
                source_masks='Actual message complete dictionary units; strict containing. Applied to all arms including R03 control/union.',
                category='Diagnostic source-role content anchors, existing function vocabulary and explicit unresolved residue; not semantic useful-content approval.',
                r03_scope='Research control reprojected through same native geometry/masks, not unchanged production runtime.',
                head_context='Only top-overall grow target; no alternate-target rescue.',
                admission_limit='Historical strict-containing masks; crossing and focus-containing-mask flags retained. This is not equivalent to production overlapping-mask explicit-permission admission.',
                budget='Strict native floor unchanged; pre-budget availability and budget-only losses retained separately.')
    (destination/'freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    producer=Producer(directory);summary=collections.defaultdict(collections.Counter);concepts=collections.defaultdict(set)
    complete=False;error=None;count=0
    try:
        with gzip.open(destination/'rows.jsonl.gz','xt',encoding='utf-8',compresslevel=6) as output,GEOMETRY.open() as stream:
            for line in stream:
                row=json.loads(line);perpair,masks,protected,rejections=producer.produce(row);words=row['native_source_word_ranges_utf16'];n=len(words)
                trace=dict(id=row['id'],text=row['text'],native_words_utf16=words,source_masks=masks,protected_ranges_utf16=protected,projection_rejections=rejections,pairs={})
                length='short' if n<=5 else 'mid' if n<=12 else 'long'
                for pair,data in perpair.items():
                    table=[];dedup={};decisions=[];candidates=data['candidates']
                    for arm in ARMS:
                        global_indices=data['members'].get(arm,[]);arm_candidates=[candidates[i] for i in global_indices]
                        for density in DENSITIES:
                            for known in KNOWN:
                                chosen=select(arm_candidates,words,protected,masks,density,known,producer.order)
                                compact={k:[global_indices[i] for i in chosen[k]] for k in ['selected_indices','pre_budget_indices','budget_only_indices']}
                                compact['rejected']=[dict(r,index=global_indices[r['index']]) for r in chosen['rejected']]
                                compact['budget']=chosen['budget'];identity=encoded(compact)
                                if identity not in dedup:dedup[identity]=len(table);table.append(compact)
                                decisions.append([arm,density,known,dedup[identity]])
                                selected=[candidates[i] for i in compact['selected_indices']]
                                for bin_name in ['all',length]:
                                    key='|'.join([pair,arm,str(density),known,bin_name]);s=summary[key]
                                    s['messages']+=1;s['source_words']+=n;s['available_messages']+=bool(selected)
                                    s['changed_words']+=sum(c['cost'] for c in selected)
                                    s['content_anchor_messages']+=any(c['category']=='content' for c in selected)
                                    s['function_only_messages']+=bool(selected) and all(c['category']=='function' for c in selected)
                                    s['unresolved_only_messages']+=bool(selected) and not any(c['category']=='content' for c in selected) and any(c['category']=='unresolved' for c in selected)
                                    s['content_labelled_changed_words']+=sum(c['cost'] for c in selected if c['category']=='content')
                                    s['content_anchor_changed_words']+=sum(c['content_anchor_native_words'] for c in selected)
                                    s['pre_budget_available_messages']+=bool(compact['pre_budget_indices'])
                                    s['budget_only_unavailable_messages']+=bool(compact['pre_budget_indices']) and not selected and set(compact['pre_budget_indices'])==set(compact['budget_only_indices'])
                                    s['selected_crossing_mask_scopes']+=sum(bool(c['crossing_mask_ids']) for c in selected)
                                    s['selected_containing_mask_scopes']+=sum(bool(c['contained_mask_ids']) for c in selected)
                                    s['oversized_units']+=len(compact['budget_only_indices'])
                                    for c in selected:concepts[key].add(c['concept_id'])
                                # Full rejection/selection geometry stays in the compact table.
                    trace['pairs'][pair]=dict(candidates=candidates,decision_table=table,decisions=decisions)
                output.write(encoded(trace)+'\n');count+=1
                if count%100==0:guards(start,1200)
                if count%500==0:print(encoded(dict(rows=count,seconds=time.monotonic()-start)),flush=True)
        assert count==9535;complete=True
    except Exception as exc:error=repr(exc);raise
    finally:
        clear_unit_cache();producer.db.close()
        (destination/'metrics.json').write_text(json.dumps({k:dict(v,distinct_units_or_concepts=len(concepts[k])) for k,v in summary.items()},indent=2)+'\n')
        receipt=dict(complete=complete,error=error,rows=count,production=False,freeze_sha256=sha(destination/'freeze.json'),seconds=time.monotonic()-start,process_vm_hwm_bytes=process_hwm(),outputs={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in destination.iterdir() if p.is_file()})
        (destination/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(encoded(receipt),flush=True)

if __name__=='__main__':main()
