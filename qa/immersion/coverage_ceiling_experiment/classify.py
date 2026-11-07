#!/usr/bin/env python3
"""Post-review diagnostic strata; these are not held-out policy validation."""
import argparse
import collections
import json
from pathlib import Path
import statistics

from compare import Dictionary, depth, digest, u16


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--dictionary-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite retained diagnostic")
    data = json.loads(args.comparison.read_text())
    dictionary = Dictionary(args.dictionary_dir / "d-en.sqlite")
    summaries, details = {}, []
    for language, name in [("es", "spanish"), ("sw", "swahili")]:
        review_path = Path(__file__).parent / (name + "-200-author-review.json")
        review = json.loads(review_path.read_text())
        assert review["comparison_sha256"] == digest(args.comparison)
        labels = {row["id"]: row for row in review["rows"]}
        strata = collections.defaultdict(collections.Counter)
        policies = collections.defaultdict(list)
        for row in data["results"]:
            if row["target"] != language:
                continue
            row_labels = labels[row["id"]]
            accepted_baseline = [span for span, label in zip(row["A"]["spans"], row_labels["A_spans"]) if label["label"] == "meaning_appears_correct"]
            bad_baseline = any(label["label"] in {"material_error", "lexical_category_error"} for label in row_labels["A_spans"])
            label_by_range = {tuple(label["source_range"]): label for label in row_labels["B_added_spans"]}
            selected = collections.defaultdict(list)
            for span in row["B"]["spans"]:
                if span["origin"] == "production_A":
                    continue
                label = label_by_range[(span["sourceStartUTF16"], span["sourceEndUTF16"])]
                forms = [form for form in dictionary.analyses(span["original"].lower())
                         if form["mode"] in (1, 2, 4, 5) and form["start"] == 0 and form["end"] == u16(form["surface"])]
                source_lexemes = {item["source_lexeme"] for item in span["evidence"]}
                used = [form for form in forms if form["lexeme"] in source_lexemes]
                possible_pos = {form["pos"] for form in forms}
                matched_pos = {item["pos"] for item in span["evidence"]}
                features = {
                    "all_B_additions": True,
                    "source_safe_some": any(form["source_safe"] for form in used),
                    "no_competing_source_POS": possible_pos <= matched_pos,
                    "selected_adjective_or_verb_only": bool(matched_pos) and matched_pos <= {"adj", "verb"},
                    "supplied_inflection": any(form["mode"] in (2, 4, 5) for form in used),
                }
                for key, value in features.items():
                    if value:
                        strata[key][label["label"]] += 1
                        selected[key].append((span, label))
                strata["POS:" + "+".join(sorted(matched_pos))][label["label"]] += 1
                if label["label"] == "lexical_category_error":
                    family = "contextual_grammatical_role_not_resolved_by_dictionary_POS"
                elif label["label"] == "material_error":
                    family = "chat_shorthand_or_typo_interpreted_as_other_lexeme" if span["original"].lower() in {"lap", "hear", "rite"} else "contextual_sense_or_idiom"
                elif label["label"] == "uncertain":
                    family = "needs_context_scope_or_native_idiom_review"
                else:
                    family = "author_accepted"
                strata["finding:" + family][label["label"]] += 1
                details.append({"id": row["id"], "pair": "en-" + language, "original": row["original"],
                                "span": span, "label": label, "failure_family": family,
                                "matched_POS": sorted(matched_pos), "all_complete_source_POS": sorted(possible_pos), "features": features})
            for key in ("all_B_additions", "source_safe_some", "no_competing_source_POS", "selected_adjective_or_verb_only", "supplied_inflection"):
                accepted = accepted_baseline + [span for span, label in selected[key] if label["label"] == "meaning_appears_correct"]
                bad = bad_baseline or any(label["label"] in {"material_error", "lexical_category_error"} for _, label in selected[key])
                policies[key].append({"useful": bool(accepted), "clean_useful": bool(accepted) and not bad,
                                      "depth": depth(accepted, row["native_word_ranges"])})
        summaries["en-" + language] = {
            "strata_added_spans": dict(strata), "review_sha256": digest(review_path),
            "posthoc_policy_A_plus_selected": {key: {"messages_with_author_accepted_span": sum(row["useful"] for row in rows),
                "clean_useful_messages": sum(row["clean_useful"] for row in rows),
                "mean_native_word_depth_of_accepted_spans": statistics.mean(row["depth"] for row in rows)} for key, rows in policies.items()}}
    value = {"schema": "vipi-relaxed-strata-diagnostic-1", "comparison_sha256": digest(args.comparison),
             "runner_sha256": digest(__file__), "dictionary_sha256": digest(args.dictionary_dir / "d-en.sqlite"),
             "posthoc": True, "release_ready": False, "meaning_labels": "Author judgement, not independent bilingual acceptance",
             "summary": summaries, "details": details}
    args.output.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
