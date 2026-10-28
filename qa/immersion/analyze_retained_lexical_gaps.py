#!/usr/bin/env python3
"""Explain dictionary-linked opportunities, without claiming contextual correctness."""
import argparse,hashlib,json,sqlite3
from collections import Counter
from contextlib import closing
from functools import lru_cache
from pathlib import Path
import icu,unicodedata
ROOT=Path(__file__).resolve().parents[2]
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def words(text,language):
    it=icu.BreakIterator.createWordInstance(icu.Locale(language));value=icu.UnicodeString(text);it.setText(value)
    start=it.first()
    for end in it:
        actual=str(value[start:end])
        if any(c.isalpha() for c in actual):yield start,end,actual,unicodedata.normalize("NFC",actual).lower()
        start=end
def run(args):
    catalog=json.loads(args.dictionary.read_text());fixtures=json.loads(args.cases.read_text())
    report=json.loads(args.report.read_text());assert report["complete"] and report["passed"]
    outcomes={r["id"]:r for r in report["outcomes"]};languages={r[k] for r in fixtures for k in ["source","target"]}
    dbs={};result=[];counts=Counter();pos=Counter();terms=Counter()
    try:
        for row in catalog["shards"]:
            if row["language"] not in languages:continue
            p=args.dictionary.parent/(row["language"]+".sqlite");assert sha(p)==row["sha256"]
            dbs[row["language"]]=sqlite3.connect(p.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
        @lru_cache(maxsize=20000)
        def links(language,word):
            return dbs[language].execute("""SELECT DISTINCT f.surface,f.start,f.end,f.mode,l.normalized,l.pos,t.sense
                FROM surfaces f JOIN lexemes l ON l.id=f.lexeme JOIN terms t ON t.lexeme=l.id JOIN senses s ON s.id=t.sense
                WHERE f.normalized=? AND l.target_safe=1 AND t.eligible=1 AND s.explicit=1""",(word,)).fetchall()
        @lru_cache(maxsize=20000)
        def grammar(language,word):
            rows=dbs[language].execute("""SELECT DISTINCT l.pos,g.reason,COALESCE(g.target_blocked,0)
                FROM surfaces f JOIN lexemes l ON l.id=f.lexeme LEFT JOIN guards g ON g.normalized=l.normalized
                WHERE f.normalized=?""",(word,)).fetchall()
            return any(pos in {"pron","det","prep","postp","conj","particle","article","aux"} or reason=="grammar" or blocked==1
                for pos,reason,blocked in rows)
        for case in fixtures:
            outcome=outcomes[case["id"]];selected=outcome["combined_spans"];candidates=[];counts["messages"]+=1
            counts["messages_with_selected_spans"]+=bool(selected)
            left=list(words(case["original"],case["source"]));right=list(words(case["translation"],case["target"]))
            for a,b,w,key in left:
                if any(s["start"]<b and a<s["end"] for s in selected):continue
                source_links=links(case["source"],key);offered=set()
                for sa,se,t,tk in right:
                    if w.lower()==t.lower():continue
                    target_links=links(case["target"],tk)
                    for written,start,end,mode,head,category,sense in source_links:
                        if start!=0 or end!=len(written.encode("utf-16-le"))//2:continue
                        for tw,ts,te,tm,th,tp,meaning in target_links:
                            if sense!=meaning or ts!=0 or te!=len(tw.encode("utf-16-le"))//2:continue
                            offered.add((w,t,a,b,sa,se,category,tp,mode,tm))
                for value in sorted(offered):
                    item=dict(zip(["source","target","start","end","target_start","target_end","source_pos","target_pos","source_mode","target_mode"],value))
                    item["source_hard_grammar"]=grammar(case["source"],key)
                    candidates.append(item)
            counts["messages_with_unselected_dictionary_links"]+=bool(candidates)
            if not selected:
                counts["empty_messages_with_dictionary_links"]+=bool(candidates)
                content=[c for c in candidates if not c["source_hard_grammar"]]
                counts["empty_messages_with_non_grammar_dictionary_links"]+=bool(content)
                for category in {c["source_pos"] for c in content}:pos[category]+=1
                for word in {c["source"] for c in content}:terms[word]+=1
            result.append(dict(case=case,selected=selected,unqualified_dictionary_links=candidates))
        args.output.mkdir(exist_ok=False,parents=True)
        (args.output/"cases.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
        receipt=dict(complete=True,semantic_accuracy_claim=False,production_promoted=False,
            warning="Dictionary links are unqualified possibilities, not missing correct spans or coverage. No grammar, homograph, sentence, idiom or case acceptance is implied.",
            source_cases_sha256=sha(args.cases),source_report_sha256=sha(args.report),dictionary_catalog_sha256=sha(args.dictionary),
            compiler_sha256=sha(Path(__file__)),counts=dict(counts),empty_message_non_grammar_source_pos=dict(pos),
            empty_message_common_non_grammar_source_words=terms.most_common(40),cases_sha256=sha(args.output/"cases.json"))
        (args.output/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
        print(json.dumps(receipt,ensure_ascii=False),flush=True)
    finally:
        for db in dbs.values():db.close()
if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ["dictionary","cases","report","output"]:p.add_argument("--"+name,type=Path,required=True)
    run(p.parse_args())
