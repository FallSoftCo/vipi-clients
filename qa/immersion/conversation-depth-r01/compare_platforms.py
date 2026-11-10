#!/usr/bin/env python3
from pathlib import Path
import json,hashlib
W=Path('/home/ai/Development/investigations/vipi-conversation-depth-20261109-r01');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=W/'platform-comparison-r01.json';assert not out.exists();a=W/'apple-capture-r01/inputs-r01/apple-output.jsonl';b=W/'android-capture-r01/output.stdout'
 assert sha(a)=='f3503b19697590848bfdb4c66d065102e2540d6bc99d4e4088b569c0968eef21'
 key=lambda x:(x['id'],x['pair'],x['density'])
 aa={key(x):x for x in map(json.loads,a.read_text().splitlines())};bb={key(x):x for x in map(json.loads,b.read_text().splitlines())};assert len(aa)==len(bb)==320 and aa.keys()==bb.keys()
 fields=['source','stratum','spans','mixed_script','mixed_reading','origin','status','reference_hit'];diff=[];geometry=[];new=[]
 def option(x):return json.dumps({k:x[k]for k in ['source','pair','spans','mixed_script','mixed_reading']},ensure_ascii=False,sort_keys=True,separators=(',',':'))
 apple_options={option(x)for x in aa.values()}
 for k,x in aa.items():
  y=bb[k];changed=[n for n in fields if x[n]!=y[n]]
  if changed:diff.append({'id':k[0],'pair':k[1],'density':k[2],'changed_fields':changed})
  if x['native_words']!=y['native_words']:geometry.append({'id':k[0],'pair':k[1],'density':k[2],'apple_words':len(x['native_words']),'android_words':len(y['native_words'])})
  if option(y)not in apple_options:new.append({'id':k[0],'pair':k[1],'density':k[2],'option_sha256':hashlib.sha256(option(y).encode()).hexdigest()})
 result={'rows':320,'presentation_metadata_differences':diff,'native_geometry_differences':geometry,'android_options_absent_from_apple':new,'semantic_labels_read':False,'bindings':{str(p):sha(p)for p in [a,b,Path(__file__)]}}
 out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'comparison_sha256':sha(out),'presentation_metadata_differences':len(diff),'native_geometry_differences':len(geometry),'android_new_option_rows':len(new)}))
if __name__=='__main__':main()
