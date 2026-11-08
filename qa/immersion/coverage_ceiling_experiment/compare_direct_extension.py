#!/usr/bin/env python3
"""QA only: direct local word/window/split MT, independent of dictionaries.

Exact token agreement with whole MT is an alignment cue, never semantic gold.
The supplied native capture is an eagerly cached query union; arm costs below
are replay projections, not measured end-to-end production latency.
"""
import argparse
import collections
import hashlib
import json
import math
import re
import statistics
import unicodedata
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cut(text, a, b):
    return text.encode("utf-16-le")[2*a:2*b].decode("utf-16-le")


def key(text):
    return unicodedata.normalize("NFC", text).casefold()


def tokens(call):
    text = call["translation"]
    result = []
    last = 0
    ranges = [tuple(r) for r in call["native_target_word_ranges"]]
    # Native linguistic word ranges omit stand-alone numerals. They must remain
    # alignment tokens: 'Machi 3' cannot corroborate just 'Machi' in '3 ya Machi'.
    for match in re.finditer(r"\d+(?:[.,:/]\d+)*", text):
        a = len(text[:match.start()].encode("utf-16-le")) // 2
        b = len(text[:match.end()].encode("utf-16-le")) // 2
        if not any(x < b and a < y for x, y in ranges):
            ranges.append((a, b))
    for a, b in sorted(ranges):
        assert last <= a < b <= len(text.encode("utf-16-le")) // 2
        result.append((key(cut(text, a, b)), a, b))
        last = b
    return result


def overlap(a, b, side="source"):
    return a[side + "StartUTF16"] < b[side + "EndUTF16"] and b[side + "StartUTF16"] < a[side + "EndUTF16"]


def mixed(text, spans):
    result = text.encode("utf-16-le")
    for span in sorted(spans, key=lambda s: s["sourceStartUTF16"], reverse=True):
        a, b = span["sourceStartUTF16"], span["sourceEndUTF16"]
        result = result[:a*2] + span["translated"].encode("utf-16-le") + result[b*2:]
    return result.decode("utf-16-le")


ARMS = {
    "word": {"isolated_word"},
    "window": {"isolated_word", "bounded_window"},
    "split": {"isolated_word", "top_down_split"},
    "union": {"isolated_word", "bounded_window", "top_down_split"},
}


def aligned(message, capture):
    full = capture[message["full_query_id"]]
    target = tokens(full)
    result, rejects = [], collections.Counter()
    for candidate in message["candidates"]:
        call = capture[candidate["query_id"]]
        source_a, source_b = candidate["source_range"]
        assert cut(message["text"], source_a, source_b) == candidate["text"] == call["text"]
        if call["status"] != "translated":
            rejects["provider_failure"] += 1
            continue
        if not call["identifiers_preserved"]:
            rejects["native_literal_integrity_failed"] += 1
            continue
        units = tokens(call)
        if not units:
            rejects["no_target_words"] += 1
            continue
        wanted = [u[0] for u in units]
        positions = [i for i in range(len(target)-len(wanted)+1)
                     if [u[0] for u in target[i:i+len(wanted)]] == wanted]
        if len(positions) != 1:
            rejects["no_full_translation_agreement" if not positions else "multiple_target_occurrences"] += 1
            continue
        i = positions[0]
        a, b = target[i][1], target[i+len(wanted)-1][2]
        translated = cut(full["translation"], a, b)
        assert collections.Counter(re.findall(r"\d+(?:[.,:/]\d+)*", translated)) == collections.Counter(re.findall(r"\d+(?:[.,:/]\d+)*", call["translation"])), "Projection lost numeric content"
        if key(candidate["text"]) == key(translated):
            rejects["unchanged"] += 1
            continue
        first, end = candidate["source_word_indices"]
        assert end-first < len(message["native_source_word_ranges"]), "Whole flips are not mixed immersion"
        source_keys = [key(cut(message["text"], *scope)) for scope in message["native_source_word_ranges"][first:end]]
        copied = sum((collections.Counter(source_keys) & collections.Counter(wanted)).values())
        new_tokens = collections.Counter(wanted) - collections.Counter(source_keys)
        if not any(any(letter.isalpha() for letter in token) for token in new_tokens):
            # Deleting an article from 'a comedy' -> 'comedy' or merely changing
            # punctuation/case supplies no target-language word to learn.
            rejects["no_new_target_tokens"] += 1
            continue
        result.append({"sourceStartUTF16": source_a, "sourceEndUTF16": source_b,
                       "targetStartUTF16": a, "targetEndUTF16": b,
                       "original": candidate["text"], "translated": translated,
                       "source_words": end-first, "changed_source_words": end-first-copied,
                       "unchanged_source_tokens": list((collections.Counter(source_keys) & collections.Counter(wanted)).elements()),
                       "query_id": candidate["query_id"],
                       "isolated_translation": call["translation"], "arms": candidate["arms"]})
    return result, dict(rejects)


def select(candidates, budget):
    # Larger chunks preserve more local meaning. Reject competing independent
    # source claims for the same full-target scope rather than picking one.
    eligible = [c for c in candidates if c["source_words"] <= budget]
    selected, used = [], 0
    competition = 0
    for candidate in sorted(eligible, key=lambda c: (-c["source_words"], c["sourceStartUTF16"], c["targetStartUTF16"])):
        if used + candidate["source_words"] > budget:
            continue
        if any(overlap(candidate, other) or overlap(candidate, other, "target") for other in selected):
            continue
        if any(not overlap(candidate, other) and overlap(candidate, other, "target") for other in eligible):
            competition += 1
            continue
        selected.append(candidate)
        used += candidate["source_words"]
    selected.sort(key=lambda s: s["sourceStartUTF16"])
    return selected, used, competition


def percentile(values, q):
    return sorted(values)[min(len(values)-1, math.ceil(q*len(values))-1)] if values else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    native = json.loads(args.capture.read_text())
    assert native["complete"] and native["input_sha256"] == sha(args.protocol)
    capture = {r["id"]: r for r in native["requests"]}
    assert len(capture) == len(protocol["requests"]) == native["completed_count"]
    for request in protocol["requests"]:
        actual = capture[request["id"]]
        assert all(request[k] == actual[k] for k in ("id", "source", "target", "text"))
    rows = []
    for message in protocol["messages"]:
        candidates, rejection_counts = aligned(message, capture)
        full = capture[message["full_query_id"]]
        count = len(message["native_source_word_ranges"])
        arms = {}
        for arm, kinds in ARMS.items():
            values = [c for c in candidates if set(c["arms"]) & kinds]
            queries = {c["query_id"] for c in message["candidates"] if set(c["arms"]) & kinds}
            queries.add(message["full_query_id"])
            projections = []
            for density in protocol["requested_depths"]:
                # A one-word message is deliberately ineligible: its replacement
                # is a whole-sentence flip, not evidence of mixed immersion.
                budget = min(count-1, max(1, math.ceil(count*density))) if count else 0
                spans, used, competition = select(values, budget)
                projections.append({"requested_density": density, "word_budget": budget,
                                    "spans": spans, "visible": mixed(message["text"], spans),
                                    "actual_depth": used/count if count else 0,
                                    "changed_depth": sum(s["changed_source_words"] for s in spans)/count if count else 0,
                                    "changed_source_words": sum(s["changed_source_words"] for s in spans),
                                    "covered_source_words": used, "competing_claims_rejected": competition})
            arms[arm] = {"projections": projections, "eager_distinct_queries": len(queries),
                         "eager_sum_measured_call_ms": sum(capture[q]["elapsed_ms"] for q in queries),
                         "query_ids": sorted(queries)}
        rows.append({"id": message["id"], "corpus": message["corpus"], "source": message["source"],
                     "target": message["target"], "length_bin": message["length_bin"], "source_words": count,
                     "original": message["text"], "full_translation": full["translation"],
                     "full_identifiers_preserved": full["identifiers_preserved"],
                     "native_source_word_ranges": message["native_source_word_ranges"],
                     "candidate_rejections": rejection_counts, "aligned_candidates": candidates, "arms": arms})
    summary = []
    for target in sorted({r["target"] for r in rows}):
        for corpus in ["all", *sorted({r["corpus"] for r in rows})]:
            for length in ("all", "1-5", "6-15", "16-30", "31+"):
                group = [r for r in rows if r["target"] == target and (corpus == "all" or r["corpus"] == corpus)
                         and (length == "all" or r["length_bin"] == length)]
                if not group:
                    continue
                for arm in ARMS:
                    queries = set().union(*(set(r["arms"][arm]["query_ids"]) for r in group))
                    for density in protocol["requested_depths"]:
                        outputs = [next(p for p in r["arms"][arm]["projections"] if p["requested_density"] == density) for r in group]
                        costs = [r["arms"][arm]["eager_sum_measured_call_ms"] for r in group]
                        summary.append({"target": target, "corpus": corpus, "length_bin": length, "arm": arm,
                                        "requested_density": density, "messages": len(group),
                                        "messages_with_flips": sum(bool(p["spans"]) for p in outputs),
                                        "spans": sum(len(p["spans"]) for p in outputs),
                                        "mean_raw_depth": statistics.mean(p["actual_depth"] for p in outputs),
                                        "mean_changed_depth": statistics.mean(p["changed_depth"] for p in outputs),
                                        "pooled_raw_depth": sum(p["covered_source_words"] for p in outputs)/sum(r["source_words"] for r in group),
                                        "eager_calls_before_cross_message_cache": sum(r["arms"][arm]["eager_distinct_queries"] for r in group),
                                        "eager_calls_after_cross_message_cache": len(queries),
                                        "projected_eager_query_ms_median": statistics.median(costs),
                                        "projected_eager_query_ms_p95": percentile(costs, .95)})
    output = {"schema": "vipi-direct-extension-comparison-1", "production": False, "semantic_review": False,
              "protocol_sha256": sha(args.protocol), "capture_sha256": sha(args.capture), "runner_sha256": sha(__file__),
              "method": "Dictionary-independent native word-token agreement, unique target occurrence, no independent competing source claims; source and target scopes disjoint; whole-source replacement excluded.",
              "changed_depth_policy": "Subtract unchanged source/target token multiset intersections inside each selected chunk. Proper names, copied slang, numbers and identical cognates do not earn changed-word depth. This conservative count is not itself semantic approval.",
              "cost_limitation": "Actual capture ran the eager cached union. Per-arm query sums omit unmeasured orchestration and may reuse warmed calls; they are projections, not first-message latency benchmarks.",
              "first_pair_calls": [r for r in native["requests"] if r["first_call_for_prepared_pair"]],
              "models": native["models"], "native_elapsed_ms": sum(r["elapsed_ms"] for r in native["requests"]),
              "summary": summary, "rows": rows}
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps([s for s in summary if s["corpus"] == s["length_bin"] == "all"], indent=2))


if __name__ == "__main__":
    main()
