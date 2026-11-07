#!/usr/bin/env python3
"""Filter fixed, already-reviewed direct-MT scopes using exact local round trips.

Development experiment only. Correlated models can repeat the same wrong sense
in both directions; equality is not independent semantic acceptance.
"""
import argparse
import collections
import hashlib
import json
import unicodedata
from pathlib import Path

from compare_direct_extension import mixed
from score_direct_review import scope, summaries


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normalize(text):
    text = unicodedata.normalize("NFC", text).casefold().strip()
    while text and (text[0].isspace() or unicodedata.category(text[0]).startswith("P")):
        text = text[1:]
    while text and (text[-1].isspace() or unicodedata.category(text[-1]).startswith("P")):
        text = text[:-1]
    return " ".join(text.split())


def main():
    p = argparse.ArgumentParser()
    for name in ("comparison", "review", "protocol", "capture", "output"):
        p.add_argument("--"+name, type=Path, required=True)
    args = p.parse_args()
    comparison = json.loads(args.comparison.read_text())
    review = json.loads(args.review.read_text())
    protocol = json.loads(args.protocol.read_text())
    capture = json.loads(args.capture.read_text())
    assert capture["complete"] and capture["input_sha256"] == sha(args.protocol)
    assert protocol["comparison_sha256"] == review["comparison_sha256"] == sha(args.comparison)
    requests = {r["id"]: r for r in capture["requests"]}
    assert len(requests) == len(protocol["requests"])
    for r in protocol["requests"]:
        assert all(requests[r["id"]][k] == r[k] for k in ("id", "source", "target", "text"))
    bindings = {(r["message_id"], r["forward_target"], tuple(r["source_scope"]+r["target_scope"])): r for r in protocol["bindings"]}
    rows, queries = [], collections.defaultdict(set)
    for row in comparison["rows"]:
        arms = {}
        for arm, value in row["arms"].items():
            projections = []
            for original in value["projections"]:
                accepted, rejected, ids = [], [], set()
                for span in original["spans"]:
                    binding = bindings[row["id"], row["target"], scope(span)]
                    reverse = requests[binding["reverse_query_id"]]
                    ids.add(reverse["id"])
                    okay = reverse["status"] == "translated" and reverse["identifiers_preserved"] and normalize(span["original"]) == normalize(reverse["translation"])
                    item = dict(span, reverse_query_id=reverse["id"], round_trip=reverse.get("translation"),
                                round_trip_agreement=okay)
                    (accepted if okay else rejected).append(item)
                queries[row["target"], arm, original["requested_density"]].update(ids)
                projections.append(dict(original, spans=accepted, rejected_by_round_trip=rejected,
                                        visible=mixed(row["original"], accepted),
                                        covered_source_words=sum(s["source_words"] for s in accepted),
                                        actual_depth=sum(s["source_words"] for s in accepted)/row["source_words"],
                                        changed_source_words=sum(s["changed_source_words"] for s in accepted),
                                        changed_depth=sum(s["changed_source_words"] for s in accepted)/row["source_words"],
                                        reverse_distinct_queries=len(ids),
                                        reverse_sum_measured_call_ms=sum(requests[i]["elapsed_ms"] for i in ids)))
            arms[arm] = dict(value, projections=projections)
        rows.append(dict(row, arms=arms))
    result = {"schema": "vipi-exact-round-trip-comparison-1", "production": False,
              "forward_comparison_sha256": sha(args.comparison), "review_sha256": sha(args.review),
              "reverse_protocol_sha256": sha(args.protocol), "reverse_capture_sha256": sha(args.capture),
              "runner_sha256": sha(__file__), "sample_status": "Inspected development sample; no holdout claim.",
              "filter": "NFC/casefold/collapsed whitespace and outer-punctuation trim; exact equality only. No replacement candidate after rejection.",
              "rows": rows, "models": capture["models"],
              "first_pair_calls": [r for r in capture["requests"] if r["first_call_for_prepared_pair"]],
              "reverse_unique_calls": [{"target": t, "arm": a, "density": d, "count": len(ids),
                                        "sum_measured_call_ms": sum(requests[i]["elapsed_ms"] for i in ids)} for (t, a, d), ids in queries.items()]}
    result["summary"] = summaries(result, review)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")


if __name__ == "__main__":
    main()
