#!/usr/bin/env python3
"""Join immutable scope labels; no model calls, inference or production changes."""
import argparse
import collections
import hashlib
import json
from pathlib import Path


def scope(span):
    return tuple(span[k] for k in ("sourceStartUTF16", "sourceEndUTF16",
                                  "targetStartUTF16", "targetEndUTF16"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    review = args.evidence / "blind-review"
    inputs = {}

    def read(name):
        path = review / name
        inputs[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        return json.loads(path.read_text())

    primary = read("all-80-masked.json")["rows"]
    primary_labels = read("author-primary-80-masked-review-r01.json")["rows"]
    secondary = read("secondary-80-masked.json")["rows"]
    secondary_labels = read("author-secondary-80-review-r01.json")["rows"]
    keys = {r["id"]: r for r in read("provider-key.json")["rows"]}
    codes = dict(C="correct", M="material", W="wrong_scope", m="minor",
                 U="uncertain", P="proper_name")
    rows = []
    for p, pl, s, sl in zip(primary, primary_labels, secondary, secondary_labels, strict=True):
        assert p["id"] == pl["id"] == s["id"] == sl["id"]
        for slot in ("A", "B"):
            labels = {scope(span): label for span, label in
                      zip(p[slot]["selected_spans"], pl[slot]["spans"], strict=True)}
            for span in sl[slot]:
                assert scope(span) not in labels
                labels[scope(span)] = codes[span["label"]]
            count = p[slot]["source_word_count"]
            length = "1-5" if count <= 5 else "6-15" if count <= 15 else "16-30"
            for projection in s[slot]["projections"]:
                spans = [dict(span, semantic_label=labels[scope(span)])
                         for span in projection["selected_spans"]]
                correct = sum(span["changed_source_words"] for span in spans
                              if span["semantic_label"] == "correct")
                material = any(span["semantic_label"] in ("material", "wrong_scope") for span in spans)
                uncertain = any(span["semantic_label"] == "uncertain" for span in spans)
                rows.append(dict(id=p["id"], provider=keys[p["id"]][slot], source=p["source"],
                                 full_reference=s[slot]["full_reference"], length_bin=length,
                                 density=projection["requested_density"], source_words=count,
                                 mixed_text=projection["mixed_text"], spans=spans,
                                 correct_depth=correct / count if count else 0,
                                 clean_useful=bool(correct) and not material and not uncertain,
                                 material_or_scope_error=material, uncertain=uncertain))
    summaries = []
    for provider in ("mlkit", "afrislm"):
        for density in (0.25, 0.5):
            for length in ("all", "1-5", "6-15", "16-30"):
                selected = [r for r in rows if r["provider"] == provider and r["density"] == density
                            and (length == "all" or r["length_bin"] == length)]
                summaries.append(dict(provider=provider, density=density, length_bin=length,
                    messages=len(selected), mean_correct_changed_depth=sum(r["correct_depth"] for r in selected)/len(selected),
                    clean_useful_messages=sum(r["clean_useful"] for r in selected),
                    material_or_scope_error_messages=sum(r["material_or_scope_error"] for r in selected),
                    uncertain_messages=sum(r["uncertain"] for r in selected),
                    span_labels=dict(collections.Counter(s["semantic_label"] for r in selected for s in r["spans"]))))
    output = dict(schema="vipi-conversational-secondary-decision-1", production=False,
                  review_order="Primary labels were blinded and immutable first; new secondary scopes were reviewed after unmasking. Not independent native bilingual gold.",
                  decision="Primary gate remains FAILED; secondary descriptive comparison cannot override it.",
                  input_hashes=inputs, script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  summaries=summaries, rows=rows)
    assert not args.output.exists()
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps([s for s in summaries if s["length_bin"] == "all"], indent=2))


if __name__ == "__main__":
    main()
