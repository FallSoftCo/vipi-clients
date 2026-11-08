#!/usr/bin/env python3
"""Freeze a disjoint fourth TEST sample after freezing the Japanese target transfer policy."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import time

from sample_conversational_holdout import canonical, strings


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    for key in ("test", "train", "lexicon", "freeze", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    parser.add_argument("--exclude", type=Path, action="append", default=[])
    args = parser.parse_args()
    assert sha(args.train) == "a5a9672c3e2e8a2f3d740cb0b61810ad46f3e3cd7bbe86b8d79962c6b34ad33c"
    assert sha(args.test) == "14ee0431113d28ca5e9424212170196c7e45706e96e7b46d34d52b96cbd0b380"
    plan = json.loads(args.freeze.read_text())
    assert sha(args.lexicon) == plan["lexicon_sha256"]
    amendment = Path(__file__).with_name("japanese-transfer-sampling-amendment-r01.json")
    assert json.loads(amendment.read_text())["original_freeze_sha256"] == sha(args.freeze)
    excluded = set()
    excluded_dialogues = set()
    for conversation in json.loads(args.train.read_text()):
        excluded.update(canonical(text) for _, text in conversation["dialog"])
        excluded.add(canonical(conversation["free_turker_utterance"]))
        excluded.add(canonical(conversation["guided_turker_utterance"]))
    bindings = {str(amendment): sha(amendment), str(args.train): sha(args.train), str(args.test): sha(args.test), str(args.freeze): sha(args.freeze)}
    for path in args.exclude:
        prior = json.loads(path.read_text())
        excluded.update(map(canonical, strings(prior)))
        excluded_dialogues.update(row["conversation_index"] for row in prior.get("cases",[])
            if isinstance(row,dict) and row.get("id", "").startswith("bst-test-") and "conversation_index" in row)
        bindings[str(path)] = sha(path)
    groups = collections.defaultdict(list)
    for ci, conversation in enumerate(json.loads(args.test.read_text())):
        if ci in excluded_dialogues or conversation["context_dataset"] != "convai2":
            continue
        for ti, (speaker, text) in enumerate(conversation["dialog"]):
            if speaker != 0 or not text.strip() or canonical(text) in excluded:
                continue
            count = len(text.split())
            group = "1-5" if count <= 5 else "6-15" if count <= 15 else "16-30" if count <= 30 else None
            if group is None:
                continue
            context = [{"role": "free_seed", "text": conversation["free_turker_utterance"]},
                       {"role": "guided_seed", "text": conversation["guided_turker_utterance"]}]
            context += [{"role": "free_human" if s == 0 else "guided_human_may_use_suggestions", "text": t}
                        for s, t in conversation["dialog"][:ti]]
            groups[group].append(dict(id=f"bst-test-word-r04-{ci:04d}-{ti:02d}", text=text,
                source="en", target="ja", conversation_index=ci, sampling_length_bin=group,
                review_only_preceding_context=context))
    selected, dialogues = [], set()
    for group, quota in (("1-5", 26), ("6-15", 27), ("16-30", 27)):
        candidates = sorted(groups[group], key=lambda r: hashlib.sha256(("word-transfer-test-r04:" + r["id"]).encode()).digest())
        count = 0
        for row in candidates:
            if row["conversation_index"] in dialogues or canonical(row["text"]) in excluded:
                continue
            selected.append(row)
            dialogues.add(row["conversation_index"])
            excluded.add(canonical(row["text"]))
            count += 1
            if count == quota:
                break
        assert count == quota
    selected.sort(key=lambda r: hashlib.sha256(("word-baseline-order-r04:" + r["id"]).encode()).digest())
    for group in groups:
        chosen = [r for r in selected if r["sampling_length_bin"] == group]
        chosen.sort(key=lambda r: hashlib.sha256(("word-baseline-independent-r04:" + r["id"]).encode()).digest())
        for row in chosen[:8]:
            row["independent24"] = True
    output = dict(schema="vipi-source-word-new-holdout-4", production=False, training_use=False,
        pack_building_use=False, frozen_unix=time.time(), excluded_entire_valid_dialogues=sorted(excluded_dialogues), lexicon_sha256=sha(args.lexicon), input_hashes=bindings,
        script_sha256=sha(Path(__file__)), source_license="BlendedSkillTalk dataset CC-BY-4.0; source attribution retained in evaluation-data-licenses/attribution.json",
        context_policy="Only selected exact text enters lookup; preceding context is review-only.", cases=selected)
    assert not args.output.exists()
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print("cases", len(selected), "independent", sum(r.get("independent24", False) for r in selected), sha(args.output))


if __name__ == "__main__":
    main()
