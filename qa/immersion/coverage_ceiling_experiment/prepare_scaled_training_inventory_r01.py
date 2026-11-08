#!/usr/bin/env python3
"""Freeze TRAIN frequency before primary-dictionary candidate discovery; no held-out input."""
import argparse,collections,datetime,hashlib,json,unicodedata
from pathlib import Path
from evaluate_reviewed_words import WORD
Q=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--train',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert sha(a.train)=='a5a9672c3e2e8a2f3d740cb0b61810ad46f3e3cd7bbe86b8d79962c6b34ad33c';counts=collections.Counter();messages=collections.Counter();turns=0
 for c in json.loads(a.train.read_text()):
  if c['context_dataset']!='convai2':continue
  for speaker,text in c['dialog']:
   if speaker!=0 or not text.strip():continue
   turns+=1;words=[unicodedata.normalize('NFC',m.group()).casefold().replace('’',"'") for m in WORD.finditer(text)];counts.update(words);messages.update(set(words))
 ordered=sorted(counts,key=lambda w:(-counts[w],w));rows=[{'rank':i+1,'source':w,'occurrences':counts[w],'messages':messages[w]} for i,w in enumerate(ordered[:3000])];out={'production':False,'training_only':True,'new_target_selection_seen':False,'frozen_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'train_sha256':sha(a.train),'source_license':'BSTCCBY4.0; existing evaluation-data-licenses attribution retained.','free_human_convai2_turns':turns,'distinct_source_forms':len(ordered),'selected_source_forms':len(rows),'rank_policy':'Top3000 exact normalized TRAIN forms by descending frequency, lexical tie-break; no held-out input or target availability filter. This is a candidate-discovery inventory, not semantic admission.','compiler_sha256':sha(Path(__file__)),'rows':rows};assert not a.output.exists();a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(sha(a.output),turns,len(ordered),rows[-1])
if __name__=='__main__':main()
