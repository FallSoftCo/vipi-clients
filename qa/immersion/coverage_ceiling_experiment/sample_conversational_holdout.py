#!/usr/bin/env python3
"""Freeze new human conversational sources before obtaining any provider outputs.

Uses only free-worker turns in the licensed official BlendedSkillTalk test set.
Corpus length bins use whitespace tokens only for sampling; the native capture
must supply actual language-aware word boundaries before candidate creation.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import time
import unicodedata


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(text):
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def strings(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ("text", "original", "original_text") and isinstance(child, str):
                yield child
            elif isinstance(child, (dict, list)):
                yield from strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--exclude", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite the frozen source protocol")
    raw = args.source.read_bytes()
    assert digest(raw) == "14ee0431113d28ca5e9424212170196c7e45706e96e7b46d34d52b96cbd0b380"
    exclusions = set()
    bindings = []
    for path in args.exclude:
        blob = path.read_bytes()
        exclusions.update(map(canonical, strings(json.loads(blob))))
        bindings.append({"path": str(path), "sha256": digest(blob)})
    groups = collections.defaultdict(list)
    for conversation_index, conversation in enumerate(json.loads(raw)):
        if conversation["context_dataset"] != "convai2":
            continue
        for turn_index, (speaker, text) in enumerate(conversation["dialog"]):
            if speaker != 0 or not text.strip() or canonical(text) in exclusions:
                continue
            count = len(text.split())
            label = "1-5" if count <= 5 else "6-15" if count <= 15 else "16-30" if count <= 30 else None
            if label is None:
                continue
            source_id = f"bst-test-conv-{conversation_index:04d}-turn-{turn_index:02d}"
            preceding = [{"role": "free_seed", "text": conversation["free_turker_utterance"]},
                         {"role": "guided_seed", "text": conversation["guided_turker_utterance"]}]
            preceding += [{"role": "free_human" if s == 0 else "guided_human_may_use_suggestions", "text": t}
                          for s, t in conversation["dialog"][:turn_index]]
            groups[label].append({"id": source_id, "text": text, "source": "en", "target": "sw",
                "corpus": "BlendedSkillTalk-free-human-convai2", "conversation_index": conversation_index,
                "turn_index": turn_index, "sampling_length_bin": label, "sampling_whitespace_words": count,
                "review_only_preceding_context": preceding,
                "review_only_context_note": "Context helps assess meaning but is never sent to either provider. Guided turns may contain suggested model text; selected inputs are exclusively free-human turns."})
    selected = []
    used_dialogues = set()
    used_texts = set(exclusions)
    for label, quota in [("1-5", 26), ("6-15", 27), ("16-30", 27)]:
        rows = sorted(groups[label], key=lambda row: digest(("vipi-bst-heldout-r01:" + row["id"]).encode()))
        before = len(selected)
        for row in rows:
            if row["conversation_index"] in used_dialogues or canonical(row["text"]) in used_texts:
                continue
            selected.append(row)
            used_dialogues.add(row["conversation_index"])
            used_texts.add(canonical(row["text"]))
            if len(selected) - before == quota:
                break
        assert len(selected) - before == quota, (label, len(selected) - before)
    assert len(selected) == 80 and len(used_dialogues) == 80
    # Fixed interleaving avoids confounding capture startup with length.
    selected.sort(key=lambda row: digest(("vipi-bst-run-order-r01:" + row["id"]).encode()))
    protocol = {
        "schema": "vipi-conversational-holdout-source-1", "name": "vipi-bst-heldout-r01",
        "frozen_unix": time.time(), "production": False, "training_use": False, "pack_building_use": False,
        "source": {"dataset": "BlendedSkillTalk", "authors": "Eric Michael Smith, Mary Williamson, Kurt Shuster, Jason Weston, Y-Lan Boureau",
            "paper": "https://arxiv.org/abs/2004.08449", "license": "CC-BY-4.0",
            "dataset_readme": "https://github.com/facebookresearch/ParlAI/blob/a29567f7ce76992fd1f03c51ba9e3b155a37ea51/parlai/tasks/blended_skill_talk/README.md",
            "archive": "https://parl.ai/downloads/blended_skill_talk/blended_skill_talk.tar.gz",
            "test_sha256": digest(raw), "selection_modification": "Subset and review metadata added by Fallible Software; original selected text unchanged."},
        "selection": "Deterministic hash order within whitespace-word bins, 26/27/27 short/medium/longer messages, one free-human turn per distinct test conversation, convai2 context only, no output-based filtering.",
        "excluded_inputs": bindings, "unique_excluded_normalized_strings": len(exclusions),
        "eligible_counts_after_exclusion": {key: len(value) for key, value in sorted(groups.items())},
        "sampling_caveat": "Crowdsourced persona conversations, not spontaneous private messaging. No >30 whitespace-word messages; do not extrapolate to longer inputs. No Spanish or non-Roman qualification in this Swahili follow-up. Model pretraining overlap unknown.",
        "native_boundary_stage": "Tokenize-only native pass must precede query-union generation; sample identity/order stays fixed even if actual native word bins differ.",
        "cases": selected,
        "arms": ["Current production lookup-first pipeline", "Cached local ML Kit 1-3-word chunks + actual ML Kit full reference", "Identical cached local ML Kit chunks + pinned AfriSLM full reference"],
        "requested_depths": [0.1, 0.25, 0.5], "primary_arm": "Bounded-window candidates at requested10% source-word depth",
        "fixed_rules": "Use unchanged reference-provider-freeze-r01 + compare_reference_provider.py, including strict digit preservation, existing protected-name guard, source/target disjoint unique word-boundary matches. No CAN blacklist or adaptive synonyms. Whole-message replacements receive no mixed-immersion credit.",
        "scoring": "Freeze identity-masked full-reference and selected-span semantic labels before unmasking provider. Retain correct changed-word depth, clean useful messages, material/scope-error messages, uncertain labels, and errors inherited from reference versus introduced by alignment; report each length stratum and exact counts.",
        "routing_and_latency": "Capture actual production outcome/origin/provider-call/cache-hit at each requested density, plus first process request and warm repeat. Tokenization and evaluation-only full-reference probes cannot be reported as production calls. Strong-reference route/cost remains experimental, not integrated production.",
        "advance_for_engineering_only": "Primary arm: at least56/80 clean useful messages, no more than2/80 material-or-scope-error messages, at least8% mean correct changed-word depth; also improve current control correct depth by5percentagepoints or clean useful messages by8/80 without more errors. Report uncertainty and every threshold miss; these are not store-release or all-language acceptance criteria.",
        "bounds": {"new_model_downloads": 0, "native_query_wall_seconds": 1800, "native_query_seconds": 30,
            "slm_cpu_threads": 2, "slm_max_rss_bytes": 2147483648, "slm_wall_seconds": 900}
    }
    args.output.write_text(json.dumps(protocol, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"path": str(args.output), "sha256": digest(args.output.read_bytes()),
        "messages": len(selected), "dialogues": len(used_dialogues),
        "bins": dict(collections.Counter(row["sampling_length_bin"] for row in selected))}, indent=2))


if __name__ == "__main__":
    main()
