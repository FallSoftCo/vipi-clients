#!/usr/bin/env python3
"""Lookup-only beginner vocabulary experiment; no model or grammar rewriting."""
import argparse
import collections
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import time

WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")
PROTECTED = re.compile(r"https?://\S+|\b[^\s@]+@[^\s@]+\.[^\s@]+|```[\s\S]*?```|`[^`]*`")
ARMS = ("one_content", "one_function", "one_prefer_content", "content_up_to25", "combined_up_to25")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def u16(text):
    return len(text.encode("utf-16-le")) // 2


def main():
    parser = argparse.ArgumentParser()
    for key in ("protocol", "lexicon", "freeze", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter_ns()
    lexicon = json.loads(args.lexicon.read_text())
    words = {row["source"]: row for row in lexicon["entries"]}
    initialization_ms = (time.perf_counter_ns() - started) / 1e6
    protocol, freeze = json.loads(args.protocol.read_text()), json.loads(args.freeze.read_text())
    assert sha(args.lexicon) == protocol["lexicon_sha256"] == freeze["lexicon_sha256"]
    assert len(protocol["cases"]) == 80
    rows, times = [], []
    for case in protocol["cases"]:
        started = time.perf_counter_ns()
        text = case["text"]
        tokens = list(WORD.finditer(text))
        protected = list(PROTECTED.finditer(text))
        candidates, rejections = [], []
        for token in tokens:
            key = token.group().casefold()
            if key not in words:
                continue
            before = text[:token.start()].rstrip().rstrip('"\'“”‘’')
            reason = None
            if any(m.start() < token.end() and token.start() < m.end() for m in protected):
                reason = "protected_identifier_or_code"
            elif key != "i" and token.group().isupper() and len(key) > 1:
                reason = "uppercase_identifier"
            elif key != "i" and token.group()[0].isupper() and before and before[-1] not in ".!?":
                reason = "mid_sentence_capital"
            elif len(tokens) <= 1:
                reason = "whole_message_excluded_from_mixed_credit"
            lexical = words[key]
            span = dict(sourceStartUTF16=u16(text[:token.start()]), sourceEndUTF16=u16(text[:token.end()]),
                start=token.start(), end=token.end(), original=token.group(), translated=lexical["target"],
                category=lexical["category"], pos=lexical["pos"], lexicon_id=lexical["id"],
                train_rank=lexical["train_rank"], changed_source_words=1)
            if reason:
                rejections.append(dict(span, reason=reason))
            else:
                candidates.append(span)
        arms = {}
        for arm in ARMS:
            eligible = [s for s in candidates if (s["category"] == "content" if arm in ("one_content", "content_up_to25")
                        else s["category"] == "function" if arm == "one_function" else True)]
            eligible.sort(key=lambda s: (s["category"] != "content", s["train_rank"], s["sourceStartUTF16"]))
            budget = min(len(tokens)-1, 1 if arm.startswith("one_") else math.ceil(len(tokens)*0.25))
            selected = sorted(eligible[:max(0, budget)], key=lambda s: s["sourceStartUTF16"])
            output, cursor = "", 0
            for span in selected:
                output += text[cursor:span["start"]] + span["translated"]
                cursor = span["end"]
            output += text[cursor:]
            arms[arm] = dict(spans=selected, mixed_text=output, changed_depth=len(selected)/len(tokens) if tokens else 0)
        elapsed = (time.perf_counter_ns() - started) / 1e6
        times.append(elapsed)
        rows.append(dict(case, source_words=len(tokens), qa_source_word_ranges=[[u16(text[:m.start()]), u16(text[:m.end()])] for m in tokens],
                         candidates=candidates, rejections=rejections, arms=arms, lookup_all_arms_elapsed_ms=elapsed))
    summary = {arm: dict(messages=80, messages_with_span=sum(bool(r["arms"][arm]["spans"]) for r in rows),
        mean_changed_depth=statistics.mean(r["arms"][arm]["changed_depth"] for r in rows),
        semantic_review="pending") for arm in ARMS}
    output = dict(schema="vipi-reviewed-word-lookup-evaluation-1", production=False, provider_calls=0,
        input_hashes={str(p): sha(p) for p in (args.protocol, args.lexicon, args.freeze)}, script_sha256=sha(Path(__file__)),
        boundary_source="QA Unicode English-word approximation, not native tokenizer qualification",
        timing=dict(environment="system76 Python existing CPU runtime; not mobile latency", lexicon_initialization_ms=initialization_ms,
                    median_all_five_arms_ms=statistics.median(times), p95_all_five_arms_ms=sorted(times)[75]),
        summaries=summary, rows=rows)
    assert not args.output.exists()
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(dict(summaries=summary, timing=output["timing"]), indent=2))


if __name__ == "__main__":
    main()
