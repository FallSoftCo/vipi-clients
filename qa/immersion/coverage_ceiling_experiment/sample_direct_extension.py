#!/usr/bin/env python3
"""Freeze direct word/window/top-down local-MT requests without dictionary links.

Uses exact earlier native source boundaries. Request union is cached by pair and
exact text; whole translation is a reference only, never mixed-coverage credit.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def bin_for(count):
    return "1-5" if count <= 5 else "6-15" if count <= 15 else "16-30" if count <= 30 else "31+"


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sms-capture",type=Path,required=True)
    p.add_argument("--taskmaster-capture",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():p.error("refusing to overwrite frozen protocol")
    samples=[];sources=[]
    for corpus,path,counts in [("SMS",args.sms_capture,[12,12,12,4]),("Taskmaster2",args.taskmaster_capture,[14,14,10,2])]:
        capture=json.loads(path.read_text());assert capture["complete"]
        groups=collections.defaultdict(list)
        for row in capture["cases"]:
            if row["source"]=="en" and row["target"]=="sw":
                groups[bin_for(len(row["native_source_word_ranges"]))].append(row)
        for label,count in zip(["1-5","6-15","16-30","31+"],counts):
            ordered=sorted(groups[label],key=lambda r:sha(("vipi-direct-extension-r01:"+corpus+":"+r["id"]).encode()))
            assert len(ordered)>=count,(corpus,label,len(ordered),count)
            samples.extend({"id":r["id"],"text":r["original"],"corpus":corpus,"length_bin":label,"native_source_word_ranges":r["native_source_word_ranges"]} for r in ordered[:count])
        sources.append({"path":str(path),"sha256":sha(path.read_bytes()),"protocol_sha256":capture["input_sha256"]})
    assert len(samples)==80 and len({x['id'] for x in samples})==80
    requests={};messages=[];total_uses=collections.Counter()
    def query(text,target):
        key=("en",target,text)
        if key not in requests:
            requests[key]={"id":sha(("en\0"+target+"\0"+text).encode()),"source":"en","target":target,"text":text}
        return requests[key]["id"]
    for target in ["sw","es"]:
        for sample in samples:
            text=sample["text"];ranges=sample["native_source_word_ranges"];raw=text.encode('utf-16-le');n=len(ranges)
            candidates={}
            def add(first,last,arm):
                if first==0 and last==n:return  # Whole-message exposure gets no mixed credit.
                start,end=ranges[first][0],ranges[last-1][1]
                piece=raw[start*2:end*2].decode('utf-16-le')
                if not piece.strip() or len(piece)>512:return
                key=(start,end)
                if key not in candidates:candidates[key]={"source_range":[start,end],"source_word_indices":[first,last],"text":piece,"query_id":query(piece,target),"arms":[]}
                if arm not in candidates[key]['arms']:candidates[key]['arms'].append(arm)
            for width in [1,2,3]:
                for i in range(n-width+1):
                    piece=raw[ranges[i][0]*2:ranges[i+width-1][1]*2].decode('utf-16-le')
                    if width>1 and re.search(r'[.!?。！？;\n]',piece):continue
                    add(i,i+width,'isolated_word' if width==1 else 'bounded_window')
            def split(first,last,depth):
                if last-first<=1 or depth>=5:return
                middle=(first+last)//2
                for a,b in [(first,middle),(middle,last)]:
                    add(a,b,'top_down_split');split(a,b,depth+1)
            split(0,n,0)
            full=query(text,target)
            total_uses[target]+=len(candidates)+1
            messages.append({**sample,"source":"en","target":target,"full_query_id":full,"candidates":list(candidates.values())})
    ordered=sorted(requests.values(),key=lambda r:(r['target'],r['id']))
    # Schedule each pair's first whole message first to measure true cold startup.
    for target in ['es','sw']:
        first=next(m['full_query_id'] for m in messages if m['target']==target)
        ordered.sort(key=lambda r:(r['target'],r['id']!=first,r['id']))
    value={"schema":"vipi-direct-extension-native-protocol-1","messages":messages,"requests":ordered,
           "source_captures":sources,"runner_sha256":sha(Path(__file__).read_bytes()),
           "requested_depths":[0.1,0.25,0.5],"selection":"Hash order within native-word-length bins. SMS12/12/12/4 and Taskmaster14/14/10/2. Exact original80 messages;160 pair directions. Fixed before new subphrase provider outputs.",
           "arms":["isolated_word","bounded_window","top_down_split","union"],
           "query_policy":"One actual local native translation per pair/exact input, reuse union across arms and messages. Whole original recaptured for each selected message; reference only. No dictionary links, external translator or semantic labels enter provider input.",
           "candidate_policy":"All native single words; contiguous two/three-word windows within punctuation boundary; recursive binary native-word halves to depth5. Whole-source word coverage excluded from every mixed candidate, including one-word messages. Native target-word boundaries required for later exact-occurrence alignment.",
           "budget":{"max_unique_queries":len(ordered),"max_wall_seconds":1800,"max_per_query_seconds":30,"max_runtime_parallel_queries":1,"new_models":0},
           "query_summary":{t:{"unique":sum(r['target']==t for r in ordered),"uses_before_dedup":total_uses[t],"cache_reuses_possible":total_uses[t]-sum(r['target']==t for r in ordered)} for t in ['es','sw']},
           "limitations":"Prior whole translations were already reviewed; new subphrase outputs unobserved at freeze. Diagnostic comparison, not a new blind population sample. Native model content version inaccessible; capture app/provider/OS and timestamps. Keep all raw outputs, failures and elapsed time.","production":False,"training_use":False,"pack_building_use":False}
    args.output.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({"sha256":sha(args.output.read_bytes()),"messages":len(messages),"requests":len(ordered),"summary":value['query_summary']},indent=2))


if __name__=='__main__':main()
