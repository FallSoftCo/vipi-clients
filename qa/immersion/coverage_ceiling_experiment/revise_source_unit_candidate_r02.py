#!/usr/bin/env python3
"""Retain r01 and create the explicitly reviewed native-candidate revision2."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    q = Path(__file__).resolve().parent
    prior = q / "reviewed-source-unit-native-candidate-r01.json"
    assert sha(prior) == "98f4d1844c4fd2ef5741c80161842cf36d22f2f68d866cde187f40f4936e7135"
    data = json.loads(prior.read_text())
    rules_path = q / "source-question-rules-r02.json"
    rules = json.loads(rules_path.read_text())
    changed = []
    for entry in data["pairs"]["en-sw"]["entries"]:
        if not entry["id"].startswith("question-"):
            continue
        authored = {**rules["single_words"], **rules["units"]}[entry["source"]]
        assert authored["target"] == entry["target"]
        assert entry.pop("primary_evidence_sha256") == "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"
        entry["provenance"] = dict(kind="authored_reviewed_interrogative_unit",
            source_rule_file=rules_path.name, source_rule_file_sha256=sha(rules_path),
            exact_source_rule=dict(source=entry["source"], **authored),
            exact_rule_sha256=hashlib.sha256(json.dumps(dict(source=entry["source"], **authored),
                ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            primary_verification_references=rules["primary_sources"],
            review_input_sha256={p: digest for p, digest in data["input_sha256"].items()
                if "source-concept-" in p or "source-clause-" in p},
            explanation="Authored short linguistic unit verified with primary sources and reviewed in the bound observations; no dictionary record or empty-object hash is claimed as primary evidence.")
        changed.append(entry["id"])
    assert len(changed) == 7
    ja = data["pairs"]["en-ja"]
    withheld = next(e for e in ja["entries"] if e["id"] == "word-en-ja-months")
    ja["entries"].remove(withheld)
    audit = q / "japanese-month-scope-audit-r02.json"
    assert sha(audit) == "c41f51b99e44a30b374536c7520a9ca34c55813f52f8d05d910ea7223c143864"
    ja["withheld_target_scope"] = [dict(entry=withheld, audit_file=audit.name,
        audit_sha256=sha(audit), reason="Only observed context is a duration. Standalone 月/つき is attested, but that alone does not qualify a general duration-counter substitution. Frozen minor label/scores remain unchanged.")]
    ja["summary"]["eligible_units"] -= 1
    ja["summary"]["content_units"] -= 1
    ja["summary"]["withheld_target_scope_units"] = 1
    data["schema"] = "vipi-reviewed-source-unit-native-candidate-2"
    data["revision"] = 2
    data["pack_version"] = "reviewed-source-starter-en-v002"
    data["prior_candidate_sha256"] = sha(prior)
    data["revision_compiler_sha256"] = sha(Path(__file__))
    data["changes_from_revision1"] = dict(authored_provenance_corrected=changed,
        withheld_month_duration_unit="word-en-ja-months", matching_data_otherwise_unchanged=True,
        frozen_research_scores_changed=False)
    data["runtime_contract"]["selection"] = "Requested density0.10 only. At most one unit, among units fitting the existing native token budget; prefer content, then TRAIN rank, then longer unit, then source offset. Native token-budget abstentions remain visible rather than overriding them to match Python availability."
    data["runtime_contract"]["density"] = "The frozen Python primary selected at most one unit and was not a hard10% cap. Native qualification explicitly requests0.10, preserves existing native density budget/quantization, and reports actual changed depth. No25%/50% or intermediate-progression claim."
    data["runtime_contract"]["progression"] = "Known/already-learned word exclusion is not implemented or qualified. Repeated I/and/etc availability cannot establish continuing learning or depth after those words are learned."
    data["input_sha256"][str(audit)] = sha(audit)
    data["input_sha256"][str(rules_path)] = sha(rules_path)
    assert [data["pairs"][p]["summary"]["eligible_units"] for p in ("en-sw", "en-ja", "en-es")] == [109, 46, 43]
    assert all(e.get("primary_evidence_sha256") != "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"
        for pair in data["pairs"].values() for e in pair["entries"])
    assert not args.output.exists()
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(sha(args.output))


if __name__ == "__main__":
    main()
