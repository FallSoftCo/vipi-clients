#!/usr/bin/env python3
"""Freeze exclusions and existing control bindings only; no corpus source access."""
import hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from build_corpus_exclusions import fingerprint
W=Path('/home/ai/Development/investigations/vipi-tatoeba-domain-comparison-20261108-r01')
P=Path('/home/ai/Development/investigations/vipi-immersion-reconciliation-20261107-r01/corpus-phrase-extraction-r01')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def main():
 base=P/'evaluation-exclusion-hashes.json';assert sha(base)=='f0aab9c30e5764504241aa0ed0ce7ee593c8f78eb0c1b78ad007ce0776915a9d'
 hashes=set(json.loads(base.read_text())['hashes']);assert len(hashes)==1113
 inputs=[{'path':str(base),'sha256':sha(base),'kind':'original1113'}];counts={}
 packets=[(P/'projection-r02/contextual/review/packet.json','490a7ec8bb45cb21b9cd5c14f7c78c19f85f935ee35266feccaff56972cc0b1d','context96'),(P.parent.parent/'vipi-source-role-veto-20261108-r01/projection-r01/review-packet.json','daef98710599c6465a2b82938191d20c069ab6a1183c55582b320f17bf56032f','role32'),(HERE.parent/'native-source-annotations-r01/inputs.json','cb37306db9723bf39ea41204674515c890fa12186d7e6ac052db06e6d1f27b14','native116')]
 # Paths are explicit; never discover or query the retained bulk corpus.
 packets[1]=(Path('/home/ai/Development/investigations/vipi-source-role-veto-20261108-r01/projection-r01/review-packet.json'),packets[1][1],packets[1][2])
 for path,expected,kind in packets:
  assert sha(path)==expected;before=len(hashes);n=0
  for c in json.loads(path.read_text())['cases']:
   texts=[('en',c['text'] if kind=='native116' else c['source'])]
   texts.extend(('en',turn[1]) for turn in c.get('review_only_preceding_context',[]))
   if kind=='context96':texts.extend([('en',c['parallel_source']),(c['pair'].split('-')[1],c['parallel_target'])])
   for lang,text in texts:
    if text is None:continue  # Some dictionary-only review cases have no parallel sentence.
    assert isinstance(text,str)
    if text.strip():hashes.add(fingerprint(lang,text).hex());n+=1
  inputs.append({'path':str(path),'sha256':expected,'kind':kind});counts[kind]={'full_text_records':n,'new_hashes':len(hashes)-before}
 # Function-withheld16 is an exact subset of role32; no new raw source/parallel text.
 excluded={'schema':1,'production':False,'base_count':1113,'count':len(hashes),'normalization':'language+NUL+NFC/casefold/collapsed whitespace; punctuation preserved','scope':'Full reviewed sources, prior dialogue turns, parallel source/target sentences, native116. No synthetic mixed outputs treated as natural parallel data. Function-withheld16 is a subset of role32. Not guaranteed all historical exposure.','inputs':inputs,'counts':counts,'hashes':sorted(hashes)}
 with (W/'exclusions.json').open('x') as f:json.dump(excluded,f,ensure_ascii=False,indent=2);f.write('\n')
 keys=P/'source-frequency-keys.json';assert sha(keys)=='e5a252dcadf14db1fea1385f16aa9cc0f617b82e363472b5152511b379302762'
 tr=json.loads((P/'training-receipt.json').read_text());control=next(x for x in tr['pairs'] if x['pair']=='en-es');assert control['rows']==40000
 bind=[]
 for name in ['en-es-pairs.jsonl.gz','en-es.txt','alignments/en-es-forward.align','alignments/en-es-reverse.align','alignments/en-es-grow-diag-final-and.align','alignments/en-es-forward.params','alignments/en-es-reverse.params','alignments/execution-freeze.json','toolchain/build-receipt.json']:
  p=P/name;bind.append({'name':name,'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)})
 for artifact in control['artifacts'][:2]:assert sha(P/Path(artifact['path']).name)==artifact['sha256']
 frozen={'schema':1,'production':False,'before_new_corpus_access':True,'preparer_sha256':sha(Path(__file__)),'exclusions':{'path':str(W/'exclusions.json'),'sha256':sha(W/'exclusions.json'),'count':len(hashes)},'source_keys':{'path':str(keys),'sha256':sha(keys),'unigram_count':3000,'multiword_count':5000},'pgv_control':bind,'tokenizer':{'path':str(HERE.parent/'prepare_statistical_alignment_pilot.py'),'sha256':sha(HERE.parent/'prepare_statistical_alignment_pilot.py')},'fingerprint':{'path':str(HERE.parent/'build_corpus_exclusions.py'),'sha256':sha(HERE.parent/'build_corpus_exclusions.py')},'normalization':{'path':str(HERE.parent/'conversation_corpus.py'),'sha256':sha(HERE.parent/'conversation_corpus.py')},'review_history_confounds':'PGV remains exact prior40k, with subsequent exposed full parallel texts. Audit overlap later; do not filter or retrain control. Tatoeba uses expanded exclusions.'}
 with (W/'input-freeze.json').open('x') as f:json.dump(frozen,f,indent=2);f.write('\n')
 print(json.dumps({'exclusion_count':len(hashes),'added':counts,'freeze_sha256':sha(W/'input-freeze.json')}))
if __name__=='__main__':main()
