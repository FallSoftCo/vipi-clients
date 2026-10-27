#!/usr/bin/env python3
"""Rank missed conversational word opportunities using native boundaries and shard inventory.

This diagnoses source inventory coverage only; it does not infer a translation,
relax a guard, or count an indexed form as a correct immersion mapping.
"""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import sqlite3
import unicodedata
from analyze_lexical_qualification import read,sha,identity
from coverage_scorecard import CONVERSATION_DATASETS,depth,require_coverage_population

def key(word):
    return "".join(c for c in unicodedata.normalize("NFC",word).lower()
                   if ord(c)!=0x640 and not 0x64b<=ord(c)<=0x652 and ord(c)!=0x670)

def inventory(path, words):
    result={}
    with sqlite3.connect(f"file:{path}?mode=ro",uri=True) as db:
        for start in range(0,len(words),200):
            batch=words[start:start+200];marks=",".join("?" for _ in batch)
            for word in batch:
                result[word]=dict(surface_records=0,usable_form_records=0,parts_of_speech=set(),
                                  source_blocked=False,target_blocked=False,guard_reason=None)
            for word,count,usable,pos in db.execute(
                f"SELECT s.normalized,COUNT(*),SUM(l.target_safe=1 AND s.mode BETWEEN 1 AND 3),l.pos "
                f"FROM surfaces s JOIN lexemes l ON l.id=s.lexeme WHERE s.normalized IN ({marks}) GROUP BY s.normalized,l.pos",batch):
                item=result[word];item["surface_records"]+=count;item["usable_form_records"]+=usable
                item["parts_of_speech"].add(pos)
            for word,blocked,target_blocked,reason in db.execute(
                f"SELECT normalized,blocked,target_blocked,reason FROM guards WHERE normalized IN ({marks})",batch):
                result[word].update(source_blocked=bool(blocked),target_blocked=bool(target_blocked),guard_reason=reason)
    for item in result.values():
        item["parts_of_speech"]=sorted(item["parts_of_speech"])
        if item["guard_reason"]=="grammar" or set(item["parts_of_speech"]) & {"pron","det","prep","postp","conj","particle","article","aux"}:
            category="kept_native_grammar"
        elif item["target_blocked"]:category="explicitly_guarded"
        elif not item["surface_records"]:category="no_indexed_surface"
        elif not item["usable_form_records"]:category="no_usable_form"
        elif item["source_blocked"]:category="source_guard_requires_resolution"
        else:category="indexed_analyses_need_context_or_target"
        item["inventory_category"]=category
    return result

def main(a):
    require_coverage_population(json.loads((a.fixture/"manifest.json").read_text()))
    validation,actual=read(a.fixture,a.report)
    cases={identity(r):r for r in json.loads((a.fixture/"cases.json").read_text())}
    per_pair=defaultdict(lambda:defaultdict(Counter));words=defaultdict(set)
    for ident,value in actual.items():
        if value["dataset"] not in CONVERSATION_DATASETS:
            continue
        case=cases[ident];assert depth(case,value) is not None
        encoded=case["original"].encode("utf-16-le")
        pair=value["source"]+"-"+value["target"]
        for start,end in value["source_token_ranges"]:
            word=key(encoded[2*start:2*end].decode("utf-16-le"))
            touched=any(s["start"]<end and s["end"]>start for s in value["combined_spans"])
            words[value["source"]].add(word)
            counts=per_pair[pair][word];counts["occurrences"]+=1
            counts["selected" if touched else "unselected"]+=1
    inventories={language:inventory(a.fixture/(language+".sqlite"),sorted(values)) for language,values in words.items()}
    pairs={}
    for pair,counts in sorted(per_pair.items()):
        source=pair.split("-")[0];categories=defaultdict(Counter)
        for word,value in counts.items():
            categories[inventories[source][word]["inventory_category"]].update(value)
        ranked=sorted(counts,key=lambda w:(-counts[w]["unselected"],w))
        pairs[pair]=dict(categories={k:dict(v) for k,v in sorted(categories.items())},
            top_unselected=[dict(word=w,**dict(counts[w]),**inventories[source][w])
                            for w in ranked if counts[w]["unselected"]][:a.limit],
            lexical_candidates=[dict(word=w,**dict(counts[w]),**inventories[source][w])
                                for w in ranked if counts[w]["unselected"] and inventories[source][w]["inventory_category"] not in {"kept_native_grammar","explicitly_guarded"}][:a.limit])
    result=dict(schema="vipi-missed-source-inventory-1",platform=validation["platform"],
                compiler_sha256=sha(Path(__file__)),native_report_sha256=sha(a.report),fixture_manifest_sha256=sha(a.fixture/"manifest.json"),
                directions=len(pairs),per_direction_limit=a.limit,
                interpretation="Unselected native word occurrences, separated by source-inventory state. Grammar is expected to remain native. An indexed form is not proof that this sentence has a correct local mapping. Counts repeat source messages across targets; do not pool as unique conversations.",
                pairs=pairs)
    with a.output.open("x") as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2);stream.write("\n")
    print(json.dumps(dict(directions=len(pairs),inventory_words={k:len(v) for k,v in words.items()})))

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("fixture","report","output"):
        p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--limit",type=int,default=100)
    a=p.parse_args();assert 1<=a.limit<=1000;main(a)

