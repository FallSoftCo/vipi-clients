#!/usr/bin/env python3
"""Build a QA-only verb+complement sense-frame arm from explicit bilingual examples.

Only the nonverbal lexical focus flips. The complete verb+complement construction
must match. Attested English inflections may vary the OUTSIDE verb; target focus
text is unchanged. No translation or arbitrary context shortening is used.
"""
import argparse
import collections
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from noun_boundary_experiment import Dictionary, digest, mixed, tokens, u16


def source_examples(spanish, swahili):
    for row in json.loads(spanish.read_text())["rows"]:
        usage = json.loads(row["usage_evidence"])
        if "collocation" in usage.get("example_tags", []):
            yield {**row, "target_language": "es", "pos": usage["native_part_of_speech"], "license": "CC BY-SA 4.0"}
    for row in json.loads(swahili.read_text()):
        e = row["example"]
        if e.get("type") != "example" or len(e.get("bold_text_offsets", [])) != 1 or len(e.get("bold_translation_offsets", [])) != 1:
            continue
        a,b = e["bold_translation_offsets"][0]
        x,y = e["bold_text_offsets"][0]
        yield {"id": f"sw:{row['line']}:{row['sense']}:{row['index']}", "source_context": e["english"], "target_context": e["text"],
               "source": e["english"][a:b], "target": e["text"][x:y], "source_start": a, "source_end": b,
               "target_start": x, "target_end": y, "target_language": "sw", "pos": row["pos"],
               "source_url": "https://en.wiktionary.org/wiki/" + row["word"], "license": "CC BY-SA 4.0"}


def build(examples, dictionary):
    frames, diagnostics = [], collections.Counter()
    for row in examples:
        if row["pos"] not in {"noun", "adj", "adv"}:
            diagnostics["nonverbal_focus_required"] += 1
            continue
        text = row["source_context"].strip().rstrip(".?!")
        words = tokens(text)
        shift = 1 if words and words[0]["key"] == "to" else 0
        if not 2 <= len(words)-shift <= 6:
            diagnostics["frame_length"] += 1
            continue
        first = words[shift]
        if not all(text[a["end"]:b["start"]].isspace() for a,b in zip(words,words[1:])):
            diagnostics["not_plain_complete_frame"] += 1
            continue
        if row["source_start"] <= first["end"] or row["source_end"] > len(text):
            diagnostics["focus_not_inside_complement"] += 1
            continue
        analyses = [x for x in dictionary.analyses(first["key"]) if x["pos"] == "verb" and x["headword"] == first["key"]]
        lemmas = {x["lexeme"] for x in analyses}
        if len(lemmas) != 1:
            diagnostics["verb_lemma_not_unique"] += 1
            continue
        forms = {first["key"]}
        for form, tags in dictionary.db.execute("SELECT surface,features FROM surfaces WHERE lexeme=?", (next(iter(lemmas)),)):
            features = set(json.loads(tags))
            if re.fullmatch("[a-z]+", form) and features & {"present", "past", "participle"} and not features & {"archaic", "dialectal", "obsolete", "nonstandard"}:
                forms.add(form)
        tail = text[first["end"]:]
        if text[row["source_start"]:row["source_end"]] != row["source"] or row["target_context"][row["target_start"]:row["target_end"]] != row["target"]:
            diagnostics["unbound_focus"] += 1
            continue
        frames.append({"id": str(row["id"]), "target_language": row["target_language"], "verb_lemma": first["key"],
                       "verb_forms": sorted(forms), "tail": tail,
                       "focus_start_in_tail": row["source_start"]-first["end"], "focus_end_in_tail": row["source_end"]-first["end"],
                       "translated": row["target"], "source_focus": row["source"], "evidence": row})
    return frames, dict(diagnostics)


def match(text, target, frames):
    candidates = []
    for frame in frames:
        if frame["target_language"] != target:
            continue
        pattern = re.compile(r"(?<![\w'’])(?P<verb>" + "|".join(re.escape(x) for x in frame["verb_forms"]) + r")(?P<tail>" + re.escape(frame["tail"]) + r")(?![\w'’])", re.I)
        for m in pattern.finditer(text):
            start = m.end("verb") + frame["focus_start_in_tail"]
            end = m.end("verb") + frame["focus_end_in_tail"]
            candidates.append({"sourceStartUTF16": u16(text[:start]), "sourceEndUTF16": u16(text[:end]),
                               "original": text[start:end], "translated": frame["translated"],
                               "source_context": m.group(), "context_range_utf16": [u16(text[:m.start()]), u16(text[:m.end()])],
                               "mapping_id": frame["id"], "origin": "eval_only_explicit_complement_frame"})
    accepted, rejected = [], []
    for span in candidates:
        conflict = [s for s in candidates if s is not span and s["sourceStartUTF16"] < span["sourceEndUTF16"] and span["sourceStartUTF16"] < s["sourceEndUTF16"] and (s["sourceStartUTF16"],s["sourceEndUTF16"],s["translated"]) != (span["sourceStartUTF16"],span["sourceEndUTF16"],span["translated"])]
        if conflict:
            rejected.append({"span": span, "reason": "competing_frame_claim"})
        elif not any((s["sourceStartUTF16"],s["sourceEndUTF16"],s["translated"]) == (span["sourceStartUTF16"],span["sourceEndUTF16"],span["translated"]) for s in accepted):
            accepted.append(span)
    accepted.sort(key=lambda x:x["sourceStartUTF16"])
    return {"spans": accepted, "visible": mixed(text, accepted), "rejections": rejected}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--spanish-examples",type=Path,required=True)
    p.add_argument("--swahili-examples",type=Path,required=True)
    p.add_argument("--english",type=Path,required=True)
    p.add_argument("--protocol",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():p.error("refusing overwrite")
    examples=list(source_examples(args.spanish_examples,args.swahili_examples))
    frames,diag=build(examples,Dictionary(args.english))
    rows=[{**c,**match(c["text"],c["target"],frames)} for c in json.loads(args.protocol.read_text())["cases"]]
    summary={target:{"frames":sum(f["target_language"]==target for f in frames),"messages":sum(r["target"]==target for r in rows),"messages_with_spans":sum(r["target"]==target and bool(r["spans"]) for r in rows),"spans":sum(len(r["spans"]) for r in rows if r["target"]==target)} for target in ["es","sw"]}
    result={"schema":"vipi-explicit-complement-frame-experiment-1","production":False,"translation_calls":0,"input_sha256":digest(args.protocol),"runner_sha256":digest(__file__),"source_hashes":{str(p):digest(p) for p in [args.spanish_examples,args.swahili_examples,args.english]},"limitations":"Unreviewed explicit usage examples. Direction/source correctness, phrase scope, inflected outside verbs and focus meanings require review. No arbitrary context-window shortening or target inflection is inferred.","source_examples":len(examples),"filter_counts":diag,"summary":summary,"frames":frames,"results":rows}
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n");print(json.dumps(summary,indent=2))


if __name__=="__main__":main()
