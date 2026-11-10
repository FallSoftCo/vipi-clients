#!/usr/bin/env python3
"""Add a read-only raw-candidate snapshot to exact committed private loader copies."""
from pathlib import Path
import subprocess,hashlib,json
R=Path(__file__).resolve().parents[3];W=Path('/home/ai/Development/investigations/vipi-source-context-frames-20261109-r01/native-overlay-r01')
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 bindings={}
 for lang in ['Japanese','Swahili']:
  for ext,base in [('kt','android/app/src/main/java/co/fallsoft/vipi/'),('swift','ios/Vipi/')]:
   name=lang+'StarterLookup';path=base+name+'.'+ext;raw=subprocess.check_output(['git','show','HEAD:'+path],cwd=R);text=raw.decode();old=text
   if ext=='kt':
    marker='    var trace';pos=text.find(marker)
    if pos<0:marker='    private var trace';pos=text.find(marker)
    assert pos>=0,path
    text=text[:pos]+'    var rawCandidates: List<FrameStarterCandidate> = emptyList()\n        private set\n'+text[pos:]
    assert '        trace=JSONArray()' in text;text=text.replace('        trace=JSONArray()','        trace=JSONArray();rawCandidates=emptyList()',1)
    marker='        val ordered=hits.filter';assert marker in text
    insert='''        rawCandidates=hits.map { h -> FrameStarterCandidate(h.entry.id,h.entry.concept,h.entry.category,h.entry.rank,h.entry.tokens.size,h.range,h.cost,h.reason,
            SourceReferenceUnit(h.range.start,h.range.end,original.substring(h.range.start,h.range.end),h.entry.target,READING,
                "$version:$packSHA:${h.entry.id}",packSHA,h.cost,h.outputID)) }
'''.replace('READING','h.entry.reading' if lang=='Japanese' else 'null')
    text=text.replace(marker,insert+marker,1)
   else:
    marker='    var trace:';assert marker in text;text=text.replace(marker,'    private(set) var rawCandidates: [FrameStarterCandidate] = []\n'+marker,1)
    text=text.replace('        trace = []','        trace = []; rawCandidates = []',1)
    marker='        let found = hits.filter';assert marker in text
    insert='''        rawCandidates = hits.map { h in FrameStarterCandidate(entryID:h.entry.id,conceptID:h.entry.concept_id,category:h.entry.category,rank:h.entry.train_rank,tokenCount:h.entry.source_tokens.count,range:h.range,cost:h.cost,reason:h.reason,
            unit:SourceReferenceUnit(range:h.range,original:text.substring(with:h.range),translated:h.entry.target,reading:READING,
                referenceID:packIdentity+":"+h.entry.id,catalogSHA256:sha,nativeSourceTokens:h.cost,conceptID:h.entry.concept_id,outputID:h.outputID)) }
'''.replace('READING','h.entry.reading' if lang=='Japanese' else 'nil')
    text=text.replace(marker,insert+marker,1)
   dest=W/ext;dest.mkdir(exist_ok=True);(dest/(name+'.'+ext)).write_text(text);(dest/('Reference'+name+'.'+ext)).write_text(old.replace(name,'Reference'+name))
   # Remove only the instrumentation and require exact canonical reconstruction.
   reversed_text=text.replace(insert,'',1)
   if ext=='kt':reversed_text=reversed_text.replace('    var rawCandidates: List<FrameStarterCandidate> = emptyList()\n        private set\n','',1).replace('        trace=JSONArray();rawCandidates=emptyList()','        trace=JSONArray()',1)
   else:reversed_text=reversed_text.replace('    private(set) var rawCandidates: [FrameStarterCandidate] = []\n','',1).replace('        trace = []; rawCandidates = []','        trace = []',1)
   assert reversed_text==old,path
   bindings[path]={'canonical_sha256':sha(raw),'overlay_sha256':sha(text.encode()),'reconstruction_exact':True,'baseline_copy_sha256':sha((dest/('Reference'+name+'.'+ext)).read_bytes())}
 (W/'loader-extraction-receipt.json').write_text(json.dumps({'source_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip(),'generator_sha256':sha(Path(__file__).read_bytes()),'bindings':bindings,'canonical_mutated':False,'native_compilation':False},indent=2)+'\n');print(json.dumps(bindings))
if __name__=='__main__':main()
