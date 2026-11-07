#!/usr/bin/env python3
"""Bounded experimental token pattern matcher; no neural model or target inference.
Latin-source feasibility only. Native clients own production token/grapheme geometry.
"""
import hashlib,json,re,unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
@dataclass(frozen=True)
class Token:
    text:str; start:int; end:int
    @property
    def key(self): return unicodedata.normalize('NFC',self.text).casefold().replace('’',"'")
def tokens(text):
    result=[];i=0
    while i<len(text):
        if text[i].isspace():i+=1;continue
        start=i
        if unicodedata.category(text[i])[0] in 'LNM':
            i+=1
            while i<len(text):
                if unicodedata.category(text[i])[0] in 'LNM':i+=1
                elif text[i] in "'’" and i+1<len(text) and unicodedata.category(text[i+1])[0] in 'LM':i+=1
                else:break
        else:i+=1
        result.append(Token(text[start:i],start,i))
    return result

def keys(text):return tuple(t.key for t in tokens(text))
def u16(text):return len(text.encode('utf-16-le'))//2
PROTECTED=re.compile(r'https?://\S+|\b[^\s@]+@[^\s@]+\.[^\s@]+|```[\s\S]*?```|`[^`]*`')
PUNCT=set('.!?;,:。！？；،')
RIGHT={
 'en':{'today','tomorrow','tonight','now','please','before','after','because','but','and','for','to','on','next','this'},
 'es':{'hoy','mañana','ahora','por','antes','después','porque','pero','y','para','el','esta'},
 'sw':{'leo','kesho','jana','sasa','tafadhali','kabla','baada','kwa','lakini','na','ili'},
}
SOCIAL={'en':{'for'},'es':{'por'},'sw':{'kwa'}}

class Matcher:
    def __init__(self,pack):
        self.pack=pack;self.index=defaultdict(list)
        for row in pack['rules']:
            if row['source'] not in RIGHT:raise ValueError('Unsupported experimental source')
            compiled=[]
            for part in row['parts']:
                if 'choice' in part:compiled.append(('choice',[keys(s) for s in part['choice']]))
                elif 'literal' in part:compiled.append(('literal',[keys(part['literal'])]))
                elif 'focus' in part:compiled.append(('focus',[keys(part['focus'])]))
                elif part.get('capture')=='possessive_name' and part.get('max_tokens')==3:compiled.append(('name',3))
                else:raise ValueError('Unsupported part')
            if sum(p[0]=='focus' for p in compiled)!=1:raise ValueError('One focus required')
            for first in {v[0] for v in compiled[0][1]}:self.index[row['source'],row['target'],first].append((row,compiled))
    def matches(self,text,source,target):
        if source==target or len(text)>16384:return []
        ts=tokens(text);ks=tuple(t.key for t in ts);protected=[m.span() for m in PROTECTED.finditer(text)];found=[]
        for i,t in enumerate(ts):
            for row,parts in self.index[source,target,t.key]:
                if row['left']=='lowercase' and t.text != t.text.lower():continue
                noun_prefix={'en':{'a','an','the','this','that','my','your','his','her','our','their'},'es':{'el','la','un','una','este','esta','mi','tu','su','nuestro','nuestra'},'sw':{'kwenye','katika'}}
                if row['left']=='noun_prefix' and (not i or ts[i-1].key not in noun_prefix[source]):continue
                if row['left']=='clause' and i and ts[i-1].text not in PUNCT and '\n' not in text[ts[i-1].end:t.start] and ts[i-1].key not in {'ok','okay','well','hey','oh'}:continue
                states=[(i,None,{})]
                for kind,choices in parts:
                    new=[]
                    for j,focus,captures in states:
                        if kind=='name':
                            for n in range(1,choices+1):
                                chunk=ts[j:j+n]
                                if len(chunk)!=n or not chunk[-1].key.endswith("'s"):continue
                                forms=[x.key for x in chunk[:-1]]+[chunk[-1].key[:-2]]
                                if not all(x and all(unicodedata.category(c)[0] in 'LM' for c in x) for x in forms):continue
                                # Capture is preserved; no person-identity or gender inference.
                                new.append((j+n,focus,{**captures,'possessive_name':text[chunk[0].start:chunk[-1].end]}))
                        else:
                            for value in choices:
                                end=j+len(value)
                                if ks[j:end]==value:new.append((end,(j,end) if kind=='focus' else focus,captures))
                    states=new
                    if len(states)>64:raise ValueError('Candidate ambiguity bound')
                for end,focus,captures in states:
                    if any(ks[end:end+len(keys(v))]==keys(v) for v in row.get('blocked_following',[])):continue
                    if row.get('right')=='possessive' and (end>=len(ts) or ts[end].key not in {'wangu','wako','wake','wetu','wenu','wao','yangu','yako','yake','yetu','yenu','yao','langu','lako','lake','letu','lenu','lao','changu','chako','chake','chetu','chenu','chao'}):continue
                    if end<len(ts) and row['right'] not in {'any','possessive'}:
                        allow=SOCIAL[source] if row['right']=='social' else RIGHT[source]
                        if ts[end].text not in PUNCT and ts[end].key not in allow:continue
                    if focus is None:continue
                    a,b=ts[focus[0]].start,ts[focus[1]-1].end
                    if any(a<q and b>p for p,q in protected):continue
                    found.append(dict(mappingId=row['id'],sourceStartUTF16=u16(text[:a]),sourceEndUTF16=u16(text[:b]),original=text[a:b],targetText=row['replacement'],reading=None,matchedContextStartUTF16=u16(text[:ts[i].start]),matchedContextEndUTF16=u16(text[:ts[end-1].end]),kind='phrase',captures=captures,experimentalSourceTokenCount=focus[1]-focus[0],_start=a,_end=b))
        # All competing target strings for one exact source span abstain.
        choices=defaultdict(set)
        for r in found:choices[r['_start'],r['_end']].add(r['targetText'])
        valid=[r for r in found if len(choices[r['_start'],r['_end']])==1]
        selected=[]
        for r in sorted(valid,key=lambda r:(-(r['_end']-r['_start']),r['_start'],r['mappingId'])):
            if not any(r['_start']<v['_end'] and r['_end']>v['_start'] for v in selected):selected.append(r)
        return sorted(selected,key=lambda r:r['_start'])
    def present(self,text,source,target):
        matches=self.matches(text,source,target);cursor=0;pieces=[]
        for r in matches:pieces.extend([text[cursor:r['_start']],r['targetText']]);cursor=r['_end']
        pieces.append(text[cursor:]);return ''.join(pieces),[{k:v for k,v in r.items() if not k.startswith('_')} for r in matches]

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('target');p.add_argument('text');a=p.parse_args()
    print(json.dumps(Matcher(json.loads((Path(__file__).parent/'pack.json').read_text())).present(a.text,a.source,a.target),ensure_ascii=False,indent=2))
