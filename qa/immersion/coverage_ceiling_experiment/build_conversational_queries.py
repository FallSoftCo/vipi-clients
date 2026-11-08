#!/usr/bin/env python3
"""Build a frozen exact-query union from the frozen holdout and native words.

The input boundary receipt must come from a tokenize-only native pass. No
translation, semantic labels or lookup outcomes influence this query selection.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re
import time

SOURCE_SHA = "76545660657732d09a98ac749cec9365292479c9d0a463563dfbe46e4e986586"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "boundaries", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists(), "Preserve frozen protocols"
    source = json.loads(args.source.read_bytes())
    assert sha(args.source.read_bytes()) == SOURCE_SHA
    boundaries = json.loads(args.boundaries.read_bytes())
    assert boundaries["input_sha256"] == SOURCE_SHA and boundaries["complete"]
    assert boundaries["translation_calls"] == 0 and boundaries["tokenize_only"] is True
    rows = boundaries["cases"]
    assert len(rows) == len({row["id"] for row in rows}) == 80
    by_id = {row["id"]: row for row in rows}
    requests = {}
    messages = []
    def query(text):
        request_id = sha(("en\0sw\0" + text).encode())
        requests.setdefault(request_id, {"id": request_id, "source": "en", "target": "sw", "text": text})
        return request_id
    for case in source["cases"]:
        observed = by_id[case["id"]]
        assert observed.get("text", observed.get("original")) == case["text"]
        ranges = observed["native_source_word_ranges"]
        raw = case["text"].encode("utf-16-le")
        previous = 0
        for start, end in ranges:
            assert isinstance(start, int) and isinstance(end, int)
            assert previous <= start < end <= len(raw) // 2
            assert raw[start * 2:end * 2].decode("utf-16-le").strip()
            previous = end
        assert ranges
        size = len(ranges)
        label = "1-5" if size <= 5 else "6-15" if size <= 15 else "16-30" if size <= 30 else "31+"
        candidates = []
        for width in (1, 2, 3):
            for first in range(size - width + 1):
                last = first + width
                if first == 0 and last == size:
                    continue
                start, end = ranges[first][0], ranges[last - 1][1]
                piece = raw[start * 2:end * 2].decode("utf-16-le")
                if len(piece) > 512 or (width > 1 and re.search(r"[.!?。！？;\n]", piece)):
                    continue
                candidates.append({"source_range": [start, end], "source_word_indices": [first, last],
                    "text": piece, "query_id": query(piece),
                    "arms": ["isolated_word" if width == 1 else "bounded_window"]})
        messages.append({"id": case["id"], "text": case["text"], "source": "en", "target": "sw",
            "corpus": case["corpus"], "length_bin": label, "sampling_length_bin": case["sampling_length_bin"],
            "native_source_word_ranges": ranges, "full_query_id": query(case["text"]), "candidates": candidates})
    full_ids = [message["full_query_id"] for message in messages]
    ordered = [requests[request_id] for request_id in full_ids]
    ordered += [requests[request_id] for request_id in sorted(set(requests) - set(full_ids))]
    assert len(ordered) == len(requests)
    uses = sum(1 + len(message["candidates"]) for message in messages)
    output = {"schema": "vipi-direct-extension-native-protocol-1", "name": "vipi-bst-direct-r01",
        "production": False, "training_use": False, "pack_building_use": False, "frozen_unix": time.time(),
        "source_protocol_sha256": SOURCE_SHA, "native_boundary_receipt_sha256": sha(args.boundaries.read_bytes()),
        "runner_sha256": sha(Path(__file__).read_bytes()), "messages": messages, "requests": ordered,
        "requested_depths": [0.1, 0.25, 0.5], "arms": ["isolated_word", "bounded_window"],
        "candidate_policy": "Unchanged native 1/2/3-word windows; no sentence punctuation crossing; whole-source word coverage excluded. No recursive arm in this focused follow-up. Exact UTF16 boundaries from native tokenize-only pass.",
        "query_policy": "Translate each exact source/target/text once. Whole references first in frozen source order, then stable chunk-ID order. No context, aliases, dictionaries, labels or provider outputs enter request selection.",
        "budget": {"max_unique_queries": len(ordered), "max_wall_seconds": 1800, "max_per_query_seconds": 30,
            "max_runtime_parallel_queries": 1, "new_models": 0},
        "query_summary": {"sw": {"unique": len(ordered), "uses_before_dedup": uses, "cache_reuses_possible": uses - len(ordered)}},
        "native_length_bins": dict(collections.Counter(row["length_bin"] for row in messages)),
        "selection_caveat": "Original80 source selections remain fixed if native length bins differ from whitespace sampling bins. All original protocol review context remains external to requests."}
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"sha256": sha(args.output.read_bytes()), "messages": len(messages),
        "requests": len(ordered), "native_bins": output["native_length_bins"]}, indent=2))


if __name__ == "__main__":
    main()
