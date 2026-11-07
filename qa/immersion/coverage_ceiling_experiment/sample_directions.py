#!/usr/bin/env python3
"""Freeze human Spanish prompts plus the already-frozen English Taskmaster sample.

Evaluation only. No provider outcomes are consulted and no inputs become packs.
"""
import argparse
import collections
import gzip
import hashlib
import json
from pathlib import Path


def sha(value):
    return hashlib.sha256(value).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-dir", type=Path, required=True)
    p.add_argument("--taskmaster", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        p.error("refusing to overwrite frozen protocol")
    source = args.source_dir / "2023-04-12_oasst_ready.messages.jsonl.gz"
    assert sha(source.read_bytes()) == "286a6e9a5a413b3272ae9c0b5a20d327983dea1c24342ae28cb244a6da65185c"
    trees = collections.defaultdict(list)
    with gzip.open(source, "rt") as f:
        for line in f:
            row = json.loads(line)
            if (row["lang"] == "es" and row["role"] == "prompter"
                    and row.get("synthetic") is False and row.get("review_result") is True
                    and row.get("deleted") is False and row["text"].strip()
                    and len(row["text"]) <= 2000 and len(row["text"].split()) <= 120):
                trees[row["message_tree_id"]].append(row)
    choices = [min(rows, key=lambda r: sha(("vipi-oasst-turn-r01:" + r["message_id"]).encode()))
               for rows in trees.values()]
    choices.sort(key=lambda r: sha(("vipi-oasst-tree-r01:" + r["message_tree_id"]).encode()))
    selected = choices[:200]
    assert len(selected) == 200
    reverse = [{"id": "oasst-" + r["message_id"], "source": "es", "target": "en",
                "text": r["text"], "conversation_id": r["message_tree_id"],
                "provenance": "OASST1 human Spanish prompter; not synthetic; reviewed; not deleted"}
               for r in selected]
    tm = json.loads(args.taskmaster.read_text())
    forward = [{**r, "target": "ja"} for r in tm["cases"] if r["target"] == "es"]
    assert len(forward) == 200
    lengths = collections.Counter("1-5" if len(r["text"].split()) <= 5 else "6-15"
                                  if len(r["text"].split()) <= 15 else "16-30"
                                  if len(r["text"].split()) <= 30 else "31+" for r in reverse)
    value = {"schema": "vipi-directional-conversation-evaluation-1", "cases": forward + reverse,
             "runner_sha256": sha(Path(__file__).read_bytes()),
             "source_receipt": json.loads((args.source_dir / "download-receipt.json").read_text()),
             "taskmaster_protocol_sha256": sha(args.taskmaster.read_bytes()),
             "licenses": {"OASST1": "Apache-2.0", "Taskmaster-2": "CC BY 4.0"},
             "attribution": {"OASST1": "OpenAssistant contributors, LAION, 2023",
                             "Taskmaster-2": tm["attribution"]},
             "method": "Spanish human prompter, reviewed and not deleted/synthetic; at most 2000 characters and 120 whitespace words. One hash-selected turn per eligible tree, then first 200 hash-ordered trees. Japanese reuses all 200 frozen English Taskmaster inputs, new direction. No outcome selection.",
             "eligible_spanish_trees": len(trees), "spanish_whitespace_length_bins": dict(lengths),
             "limitations": "Human assistant conversations and task-oriented dialogue, not a peer-chat population estimate. No bilingual gold reference. Historical model training overlap unmeasured. Reviewer context is never translation input.",
             "training_use": False, "pack_building_use": False}
    args.output.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"sha256": sha(args.output.read_bytes()), "cases": len(value["cases"]),
                      "spanish_length_bins": lengths, "eligible_trees": len(trees)}))


if __name__ == "__main__":
    main()
