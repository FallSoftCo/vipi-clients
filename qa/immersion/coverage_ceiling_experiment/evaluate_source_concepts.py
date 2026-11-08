#!/usr/bin/env python3
"""Research-only source concepts: reviewed words, local guards, and separate whole credit."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import time

from evaluate_reviewed_words import WORD, PROTECTED, u16

DETERMINERS = set("a an the my your his her our their this that these those some any each every much little more enough no two three four five many several".split())
PREPOSITIONS = set("in at from near around beside outside inside with without of for into behind under over".split())
OBJECT_VERBS = set("need needs needed want wants wanted drink drinks drank eat eats ate buy buys bought have has had like likes liked love loves loved".split())
COPULAS = set("is are was were seems seem looks look".split())
ARMS = ("control_mixed", "content_mixed", "function_mixed", "primary_mixed", "combined25_mixed", "whole_lexical", "primary_union")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidates(text, lexicon, rules=None):
    tokens = list(WORD.finditer(text))
    protected = list(PROTECTED.finditer(text))
    entries = {row["source"]: row for row in lexicon["entries"]}
    found, rejected = [], []
    keys = [t.group().casefold().replace("’", "'") for t in tokens]
    for i, token in enumerate(tokens):
        matches = []
        if keys[i] in entries:
            matches.append((entries[keys[i]], i + 1))
        if rules:
            for key, rule in {**rules["single_words"], **rules["units"]}.items():
                parts = key.split()
                j = i + len(parts)
                if keys[i:j] == parts:
                    matches.append((dict(id="question-en-sw-" + key.replace(" ", "-"), source=key,
                        target=rule["target"], category="function", pos="interrogative", train_rank=16,
                        guard="interrogative", following=rule["following"]), j))
        for entry, j in matches:
            end = tokens[j-1].end()
            before = text[:token.start()].rstrip().rstrip('"\'“”‘’')
            initial = not before or before[-1] in ".!?"
            reason = None
            if any(m.start() < end and token.start() < m.end() for m in protected):
                reason = "protected_identifier_or_code"
            elif keys[i] != "i" and token.group().isupper() and len(token.group()) > 1:
                reason = "uppercase_identifier"
            elif keys[i] != "i" and token.group()[0].isupper() and not initial:
                reason = "mid_sentence_capital"
            elif entry.get("guard") == "interrogative":
                if not initial:
                    reason = "question_not_sentence_initial"
                elif j >= len(keys) or keys[j] not in entry["following"]:
                    reason = "question_right_context_absent"
                elif any(text[tokens[k].end():tokens[k+1].start()].strip() for k in range(i,j)):
                    reason = "noncontiguous_question_context"
            elif entry.get("guard") == "ordinary_noun_context":
                left = keys[i-1] if i and not text[tokens[i-1].end():token.start()].strip() else None
                right = keys[j] if j < len(keys) else None
                # Guards are local hypotheses, not a complete syntactic parse.
                if not (left in DETERMINERS | PREPOSITIONS | OBJECT_VERBS or (initial and right in COPULAS)):
                    reason = "noun_context_absent"
            span = dict(start=token.start(), end=end, sourceStartUTF16=u16(text[:token.start()]),
                sourceEndUTF16=u16(text[:end]), original=text[token.start():end], translated=entry["target"],
                category=entry["category"], pos=entry["pos"], lexicon_id=entry["id"],
                train_rank=entry["train_rank"], changed_source_words=j-i, guard=entry.get("guard"))
            (rejected if reason else found).append(dict(span, reason=reason) if reason else span)
    return tokens, found, rejected


def select(text, tokens, eligible, one=True, whole=False):
    # Whole credit is separate and only for a candidate covering all source words.
    eligible = [s for s in eligible if (s["changed_source_words"] == len(tokens)) == whole]
    eligible.sort(key=lambda s: (s["category"] != "content", s["train_rank"], -s["changed_source_words"], s["start"]))
    selected = []
    budget = len(tokens) if whole else max(0, len(tokens)-1) if one else min(len(tokens)-1, math.ceil(len(tokens)*0.25))
    for span in eligible:
        if span["changed_source_words"] > budget:
            continue
        if any(s["start"] < span["end"] and span["start"] < s["end"] for s in selected):
            continue
        selected.append(span)
        budget -= span["changed_source_words"]
        if one:
            break
    selected.sort(key=lambda s:s["start"])
    output, cursor = "", 0
    for span in selected:
        output += text[cursor:span["start"]] + span["translated"]
        cursor = span["end"]
    output += text[cursor:]
    return dict(spans=selected,mixed_text=output,changed_depth=sum(s["changed_source_words"] for s in selected)/len(tokens) if tokens else 0)


def evaluate(case, lexicon, control, rules):
    text=case["text"]
    tokens, found, rejected = candidates(text,lexicon,rules)
    _, old, _ = candidates(text,control)
    arms={
        "control_mixed":select(text,tokens,old),
        "content_mixed":select(text,tokens,[s for s in found if s["category"]=="content"]),
        "function_mixed":select(text,tokens,[s for s in found if s["category"]=="function"]),
        "primary_mixed":select(text,tokens,found),
        "combined25_mixed":select(text,tokens,found,one=False),
        "whole_lexical":select(text,tokens,found,whole=True)}
    arms["primary_union"]=arms["primary_mixed"] if arms["primary_mixed"]["spans"] else arms["whole_lexical"]
    return dict(case,source_words=len(tokens),candidates=found,rejections=rejected,arms=arms)


def main():
    p=argparse.ArgumentParser()
    for key in ("protocol","lexicon","control","rules","freeze","output"):
        p.add_argument("--"+key,type=Path,required=True)
    args=p.parse_args(); start=time.perf_counter_ns()
    protocol,lexicon,control,rules,freeze=[json.loads(getattr(args,k).read_text()) for k in ("protocol","lexicon","control","rules","freeze")]
    assert sha(args.lexicon)==protocol["lexicon_sha256"]==freeze["lexicon_sha256"]
    assert sha(args.rules)==freeze["rules_sha256"] and sha(Path(__file__))==freeze["evaluator_sha256"]
    init=(time.perf_counter_ns()-start)/1e6
    rows,times=[],[]
    for case in protocol["cases"]:
        start=time.perf_counter_ns(); rows.append(evaluate(case,lexicon,control,rules));times.append((time.perf_counter_ns()-start)/1e6)
    output=dict(schema="vipi-source-concept-research-2",production=False,provider_calls=0,
        input_hashes={str(getattr(args,k)):sha(getattr(args,k)) for k in ("protocol","lexicon","control","rules","freeze")},
        semantic_review="pending",boundary_source="QA English Unicode approximation, not native qualification",
        timing=dict(environment="system76 existing Python CPU; not mobile",initialization_ms=init,median_all_arms_ms=statistics.median(times),p95_all_arms_ms=sorted(times)[int(.95*len(times))-1]),
        summary={arm:dict(messages_with_span=sum(bool(r["arms"][arm]["spans"]) for r in rows),mean_changed_depth=statistics.mean(r["arms"][arm]["changed_depth"] for r in rows)) for arm in ARMS},rows=rows)
    assert not args.output.exists();args.output.write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:output[k] for k in ["summary","timing"]},indent=2))


if __name__=="__main__":main()
