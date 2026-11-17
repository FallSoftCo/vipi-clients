"""Isolated CPU candidate probe; no application integration or message upload.

The upstream pipeline/license is retained beside this file. Source-preserving
projection is original qualification code, deliberately distinct from the
upstream destructive-normalization string API.
"""
from pathlib import Path
import hashlib,json,os,re,resource,statistics,sys,time,unicodedata
os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'runtime'))
import numpy as np
import onnxruntime as ort
import pipeline as upstream

MODEL_SHA='9779e1aca89cebc77a9b92037b7d700c422cdf6c3774d4883f4652f641f3f705'
CASES_SHA='ba78d10fcbd4310b74661f982100c47bc05bb80f98c2eb6c6eb6fc27859243f8'
assert hashlib.sha256((ROOT/'model.onnx').read_bytes()).hexdigest()==MODEL_SHA
cases_raw=(ROOT/'frozen-cases.json').read_bytes();assert hashlib.sha256(cases_raw).hexdigest()==CASES_SHA
config=json.loads((ROOT/'config.json').read_text());assert config['sha256']==MODEL_SHA
assert config['num_tags']==16 and config['opset']==17 and config['max_seq_len']==1024
sym2id=config['sym2id'];assert len(sym2id)==175
options=ort.SessionOptions();options.intra_op_num_threads=1;options.inter_op_num_threads=1
options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL;options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_ENABLE_ALL
before=time.perf_counter();session=ort.InferenceSession(str(ROOT/'model.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
load_ms=(time.perf_counter()-before)*1000
assert session.get_inputs()[0].name=='input_ids' and session.get_outputs()[0].name=='logits'
assert session.get_providers()==['CPUExecutionProvider']

def logits_for(base):
 if not 1<=len(base)<=1024:raise ValueError('bounded model input required')
 ids=np.asarray([[sym2id.get(c,1) for c in base]],dtype=np.int64)
 logits=session.run(['logits'],{'input_ids':ids})[0][0]
 assert logits.shape==(len(base),16)
 selected=logits.argmax(axis=-1)
 stable=logits-logits.max(axis=-1,keepdims=True);probs=np.exp(stable);probs/=probs.sum(axis=-1,keepdims=True)
 confidence=probs[np.arange(len(base)),selected]
 return selected.tolist(),confidence.tolist()

# Research protection set mirrors the production intent; native parity of the
# exact production protected-range implementation is a separate integration gate.
OPAQUE=re.compile(r'https?://[^\s<>]+|`[^`]*`|[\w.+-]+@[\w.-]+\.[\w]+|[\w_-]+\.(?:md|txt|pdf|json|csv|kt|swift)')
VOWELS=set(chr(c) for c in range(0x64b,0x653))|{'\u0670'}

def protected_mask(text):
 mask=[False]*len(text)
 for match in OPAQUE.finditer(text):
  end=match.end()
  while end>match.start() and text[end-1] in '.,!?;:。！？،؛؟':end-=1
  for i in range(match.start(),end):mask[i]=True
 return mask

def preserving_projection(text):
 mask=protected_mask(text);clusters=[];i=0;base=[];mapping=[]
 while i<len(text):
  start=i;i+=1
  while i<len(text) and unicodedata.combining(text[i]):i+=1
  source=text[start:i];opaque=any(mask[start:i]);cluster_index=len(clusters)
  clusters.append({'start_scalar':start,'end_scalar':i,'source':source,'protected':opaque,'existing_vowels':any(c in VOWELS for c in source)})
  normalized=' ' if opaque or source.isspace() else upstream.strip_diacritics(source)
  for c in normalized:
   # Collapse only the MODEL view; the original whitespace/ranges stay exact.
   if c.isspace() and base and base[-1]==' ':continue
   base.append(c);mapping.append(cluster_index)
 while base and base[0]==' ':base.pop(0);mapping.pop(0)
 while base and base[-1]==' ':base.pop();mapping.pop()
 model_input=''.join(base)
 masked=''.join(' ' if mask[i] else c for i,c in enumerate(text))
 assert model_input==upstream.strip_diacritics(masked), 'model-view whitespace/normalization alignment'
 labels,confidence=logits_for(model_input)
 added={};scores=[]
 for pos,(c,lab) in enumerate(zip(model_input,labels)):
  idx=mapping[pos];cluster=clusters[idx]
  if upstream.is_arabic_letter(c) and not cluster['protected'] and not cluster['existing_vowels']:
   added[idx]=upstream.label_to_combo(lab);scores.append(confidence[pos])
 for idx,cluster in enumerate(clusters):
  cluster['derived']=cluster['source']+added.get(idx,'')
  assert cluster['derived'].startswith(cluster['source'])
  if cluster['protected'] or cluster['existing_vowels']:assert cluster['derived']==cluster['source']
 assert ''.join(c['source'] for c in clusters)==text
 derived=''.join(c['derived'] for c in clusters)
 return derived,clusters,{'min':min(scores) if scores else None,'mean':statistics.mean(scores) if scores else None,'below_0_8':sum(p<.8 for p in scores)},model_input

def mark_units(text):
 units=[]
 for c in text:
  if upstream.AR_DIACRITIC_RE.fullmatch(c):
   if units:units[-1][1].append(c)
  else:units.append([c,[]])
 return [(c,tuple(sorted(marks))) for c,marks in units if upstream.is_arabic_letter(c)]

rows=[];times=[];total_errors=total_letters=0
for case in json.loads(cases_raw)['cases']:
 text=case['text'];base=upstream.strip_diacritics(text)
 begin=time.perf_counter();labels,_=logits_for(base);raw=upstream.attach(base,labels);first_ms=(time.perf_counter()-begin)*1000
 begin=time.perf_counter();derived,pieces,confidence,model_input=preserving_projection(text);projection_ms=(time.perf_counter()-begin)*1000
 warm=[]
 for _ in range(3):
  begin=time.perf_counter();next_value,_,_,_=preserving_projection(text);warm.append((time.perf_counter()-begin)*1000);assert next_value==derived
 times.extend(warm)
 row=case|{'upstream_normalized_output':raw,'preserving_derived_metadata':derived,'first_inference_ms':first_ms,'preserving_first_ms':projection_ms,'warm_ms':warm,'confidence':confidence,'source_partition':True,'source_changed':False,'protected_and_supplied_vowels_exact':True,'pieces':pieces}
 if case['reference']:
  predicted=mark_units(raw);expected=mark_units(case['reference']);assert [x[0] for x in predicted]==[x[0] for x in expected],case['id']
  errors=[{'letter_index':i,'letter':a[0],'predicted_marks':''.join(a[1]),'reference_marks':''.join(b[1])} for i,(a,b) in enumerate(zip(predicted,expected)) if a!=b]
  row['author_reference_letter_errors']=errors;row['reference_letters']=len(expected)
  total_errors+=len(errors);total_letters+=len(expected)
 rows.append(row)
# Resource-only limit. This repeated authored text is not accuracy evaluation.
long=('رفع العامل العلم. '*80)[:1024]
begin=time.perf_counter();logits_for(upstream.strip_diacritics(long));long_ms=(time.perf_counter()-begin)*1000
try:logits_for('ا'*1025);raise AssertionError('over-limit inference admitted')
except ValueError:pass
report={'schema':'vipi-arabic-local-candidate-qualification-1','model_sha256':MODEL_SHA,'model_revision':'ff8783fff6f6986929d8986983279d2f307d7bed','frozen_cases_sha256':CASES_SHA,'runtime':{'onnxruntime':ort.__version__,'numpy':np.__version__,'providers':session.get_providers(),'threads':1},'load_ms':load_ms,'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'warm_median_ms':statistics.median(times),'warm_max_ms':max(times),'max_input_inference_ms':long_ms,'source_tts_remains_original':True,'app_enabled':False,'independent_native_linguistic_acceptance':False,'accuracy_scope':'16 newly authored MSA references frozen before inference. No assertion of training disjointness; source ambiguity, names, dialect and preservation cases are separately reviewed, not scored against guessed reference vowels. This is not app population quality.','author_reference_letter_errors':total_errors,'author_reference_letters':total_letters,'cases':rows}
out=ROOT/'qualification-results-r02.json';assert not out.exists();out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
readable=['# Native CPU Arabic candidate outputs — derived metadata only','',f'Model load {load_ms:.2f} ms; warm median {statistics.median(times):.2f} ms; warm maximum {max(times):.2f} ms; process peak RSS {report["peak_rss_bytes"]/1024**2:.1f} MiB.','',f'Author-reference marks differ at {total_errors}/{total_letters} Arabic-letter positions across16frozenMSA references. Case endings and orthographic conventions need native review; this is not independent linguistic acceptance.','']
for row in rows:
 readable.extend([f'## {row["id"]}',row['text'],row['preserving_derived_metadata'],f'First {row["first_inference_ms"]:.2f} ms; warm median {statistics.median(row["warm_ms"]):.2f} ms; min predicted confidence {row["confidence"]["min"]}.',''])
(ROOT/'readable-outputs-r02.md').write_text('\n'.join(readable))
print(json.dumps({k:report[k] for k in ['load_ms','peak_rss_bytes','warm_median_ms','warm_max_ms','max_input_inference_ms','author_reference_letter_errors','author_reference_letters']},indent=2))
print('Total owned logical bytes',sum(p.stat().st_size for p in ROOT.rglob('*') if p.is_file()))
