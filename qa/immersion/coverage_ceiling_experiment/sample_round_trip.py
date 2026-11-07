#!/usr/bin/env python3
"""Freeze distinct reverse requests for already-selected development chunks."""
import argparse
import collections
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    comparison = json.loads(args.comparison.read_text())
    requests, bindings = {}, []
    for row in comparison["rows"]:
        seen = set()
        for arm, value in row["arms"].items():
            for projection in value["projections"]:
                for span in projection["spans"]:
                    scope = tuple(span[k] for k in ("sourceStartUTF16", "sourceEndUTF16", "targetStartUTF16", "targetEndUTF16"))
                    if scope in seen:
                        continue
                    seen.add(scope)
                    source, target, text = row["target"], row["source"], span["translated"]
                    identifier = hashlib.sha256((source+"\0"+target+"\0"+text).encode()).hexdigest()
                    requests[identifier] = {"id": identifier, "source": source, "target": target, "text": text}
                    bindings.append({"message_id": row["id"], "forward_target": row["target"], "source_scope": list(scope[:2]),
                                     "target_scope": list(scope[2:]), "original_chunk": span["original"],
                                     "visible_target_chunk": text, "reverse_query_id": identifier})
    result = {"schema": "vipi-round-trip-native-protocol-1", "production": False, "training_use": False,
              "sample_status": "Previously inspected development set; no holdout claim.",
              "comparison_sha256": hashlib.sha256(args.comparison.read_bytes()).hexdigest(),
              "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "selection": "Distinct exact target strings selected by any word/window/split/union arm at10/25/50%, after numeric and copied-token projection fixes. No semantic-label-based query selection.",
              "filter_precommitment": "Exact NFC/casefold/collapsed-whitespace source-to-round-trip equality after trimming outer punctuation only. No synonym acceptance, no learned adaptation. Preserve numerals and identifiers.",
              "budget": {"max_wall_seconds": 600, "max_call_seconds": 30, "new_models": False, "parallel_calls": 1},
              "requests": sorted(requests.values(), key=lambda r: (r["source"], r["id"])), "bindings": bindings}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({"requests": len(requests), "binding_uses": len(bindings), "pairs": dict(collections.Counter(r["source"]+"-"+r["target"] for r in requests.values())),
                      "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
