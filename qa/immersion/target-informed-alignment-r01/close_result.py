"""Existing-output closure only; no inference, native test or policy rerun."""
import collections,hashlib,json,pathlib
Q=pathlib.Path(__file__).resolve().parent;W=pathlib.Path('/home/ai/Development/investigations/vipi-target-informed-alignment-20261109-r01');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();read=lambda p:json.loads(p.read_text())
j=read(W/'run-r01/output.json');assert j['baseline_semantic_parity'];r=read(W/'run-r01/receipt.json');assert r['complete'] and r['state_closure']['restored'] and r['state_closure']['labs_alive']
def mixed(text,spans):
 b=text.encode('utf-16-le')
 for s in sorted(spans,key=lambda x:x['source_utf16'][0],reverse=True):
  a,z=s['source_utf16'];assert text.encode('utf-16-le')[2*a:2*z].decode('utf-16-le')==s['source'];b=b[:2*a]+s['target'].encode('utf-16-le')+b[2*z:]
 return b.decode('utf-16-le')
def sig(s):return json.dumps(s,ensure_ascii=False,sort_keys=True)
rows=[];count=collections.Counter();correction=None
for a,b in zip(j['baseline'],j['cases']):
 assert a['id']==b['id'] and a['original']==b['original'] and a['translation']==b['translation'];aa=a['aligned_spans_after_strict_snapshot_veto'];bb=b['aligned_spans_after_strict_snapshot_veto'];added=[s for s in bb if sig(s) not in set(map(sig,aa))];lost=[s for s in aa if sig(s) not in set(map(sig,bb))]
 for s in aa+bb:
  x,y=s['target_utf16'];assert b['translation'].encode('utf-16-le')[2*x:2*y].decode('utf-16-le')==s['target']
 ds=b['lexical_diagnostics_aggregate_not_focus_labels'];events=[(json.loads(k[len('target_graph:'):]),n) for k,n in ds.items() if k.startswith('target_graph:')];owners=[x for x,n in events if x['kind']=='ownership'];count['A_spans']+=len(aa);count['B_spans']+=len(bb);count['added']+=len(added);count['lost']+=len(lost);count['graph_edges']+=len(owners);count['max_graph_edges']=max(count['max_graph_edges'],len(owners));count['form_term_edge_proofs']+=sum(n for x,n in events if x['kind']=='edge');assert ds['target_graph_ownership_controls_passed']==1
 rows.append({'id':a['id'],'source':a['original'],'target_reference':a['translation'],'A':{'spans':aa,'mixed':mixed(a['original'],aa)},'B':{'spans':bb,'mixed':mixed(a['original'],bb)},'added':added,'lost':lost,'B_elapsed_ns':b['alignment_elapsed_ns'],'graph_edges':len(owners)})
 if b['id']=='qualified-noun-015':
  correction={'original_expectation':'Preparation described two target solo occurrences as a repeated-target negative. That omitted existing sentence-scoped compatibility. Preserve this mistaken expectation; do not count this case as a negative-control pass.','source_sentences':b['source_native_sentences'],'target_sentences':b['target_native_sentences'],'source_focus':[0,4],'chosen_target_focus':[0,4],'source_sentence_index':0,'chosen_target_sentence_index':0,'other_solo_targets':[],'actual_ownership_edges':owners}
  raw=b['translation'].encode('utf-16-le')
  for x,y in b['target_native_words']:
   if raw[2*x:2*y].decode('utf-16-le').casefold()=='solo':correction['other_solo_targets'].append({'range':[x,y],'sentence_index':next(i for i,(u,v) in enumerate(b['target_native_sentences']) if u<=x and y<=v)})
  correction['conclusion']='The first Solo belongs to the first sentence. The later solo belongs to the second, so original SentenceAlignment.permits prevents competing for first-sentence Just. Synthetic same-source competing-target geometry is the genuine negative control.'
(W/'mixed-outputs-and-deltas.json').write_text(json.dumps({'status':'exposed diagnostic, no semantic gold','counts':dict(count),'cases':rows},ensure_ascii=False,indent=2)+'\n');(W/'case015-expectation-correction.json').write_text(json.dumps(correction,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(dict(count)));print(json.dumps(correction,ensure_ascii=False))
