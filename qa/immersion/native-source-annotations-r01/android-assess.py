from pathlib import Path
import json,hashlib
q=Path(__file__).resolve().parent;p=Path('/home/ai/Development/investigations/vipi-android-source-annotations-20261108-r01')
rows=[json.loads(s) for s in (p/'annotations.jsonl').read_text().splitlines()];byid={r['id']:r for r in rows if r['pass']==0}
epath=Path('/home/ai/Development/investigations/vipi-production-delivery-20261107/source-context-independent-expectations-r01.json');ex=json.loads(epath.read_text())
mapping={'ADJ':'adjective','ADP':'preposition','ADV':'adverb','AUX':'verb','CCONJ':'conjunction','SCONJ':'conjunction','DET':'determiner','INTJ':'interjection','NOUN':'noun','PROPN':'noun','NUM':'numeral','PART':'particle','PRON':'pronoun','PUNCT':'punctuation','VERB':'verb'}
results=[]
for e in ex['cases']:
 tokens=[t for s in byid[e['case_id']]['sentences'] for t in s['tokens']];a,b=e['focus_utf16'];over=[t for t in tokens if t['start']<b and a<t['end']];exact=[t for t in over if (t['start'],t['end'])==(a,b)]
 r=dict(e,observed_tokens=over,exact_single_token=len(exact)==1)
 if e['axis']=='coarse_role':r['coarse_observed']=mapping.get(exact[0]['pos']) if len(exact)==1 else None;r['matched']=r['coarse_observed'] in e['expected']
 else:r['resolved_by_POS']=False
 results.append(r)
roles=[r for r in results if r['axis']=='coarse_role'];assessment={'schema':'vipi.android-source-annotation-assessment.r01','output_sha256':hashlib.sha256((p/'annotations.jsonl').read_bytes()).hexdigest(),'expectations_sha256':hashlib.sha256(epath.read_bytes()).hexdigest(),'role_mapping':mapping,'role_mapping_policy':'Only exact single-token UTF16 match. PROPN maps to coarse noun, not entity approval. AUX maps to verb. Composite tags preserved, not silently collapsed.','matched':sum(r['matched'] for r in roles),'role_total':len(roles),'failures':[r for r in roles if not r['matched']],'cases':results,'scope':'Frozen nominated roles on116 reused diagnostic sources, not population accuracy. No Android runtime qualification.'}
(p/'expectation-comparison.json').write_text(json.dumps(assessment,indent=2,ensure_ascii=False)+'\n')
summary={k:v for k,v in assessment.items() if k!='cases'};summary['private_comparison_path']=str(p/'expectation-comparison.json');summary['process_metrics']={'model_load_ms':887.140090,'passes_ms':[721.538037,317.707996,217.540765],'VmHWM_kib':90140,'measurement':'JVM /proc/self/status; whole process high-water resident memory, not heap or launcher historical rusage','three_passes_identical':True};summary['scope_limits']=['JVM21 on Linux; no Android/Dalvik/R8/minSdk check','POS scores not calibrated sense confidence','No NER model or idiom recognizer','Raw POS output includes composite UD tags such as PRON+AUX; preserve them','No release/runtime approval; no automatic9535 expansion']
(q/'android-assessment.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n');print(json.dumps({'matched':summary['matched'],'total':summary['role_total'],'failures':summary['failures']},indent=2,ensure_ascii=False))
