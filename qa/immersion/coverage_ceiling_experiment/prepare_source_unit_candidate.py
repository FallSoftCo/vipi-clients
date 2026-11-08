#!/usr/bin/env python3
"""Assemble a bounded native-qualification candidate, never install production data.

Source entries were selected from TRAIN before their held-out reviews. This
post-review subset retains only observed units with no unresolved meaning label.
Its filtered/replayed metrics must not be described as a new blind validation.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import unicodedata

from evaluate_source_concepts import DETERMINERS, PREPOSITIONS, OBJECT_VERBS, COPULAS


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    return unicodedata.normalize("NFKC", value).casefold()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--spanish-root", type=Path, required=True)
    parser.add_argument("--android-reading-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    q = Path(__file__).resolve().parent
    evidence = args.evidence_root
    spanish = args.spanish_root
    inputs = {}

    def read(path):
        inputs[str(path)] = sha(path)
        return json.loads(path.read_text())

    observations = {pair: collections.defaultdict(list) for pair in ("sw", "ja", "es")}
    packets = {
        "sw": [(evidence / "source-concept-all80-review-r02.json", evidence / "source-concept-author-review-r02.json"),
               (evidence / "source-clause-all80-review-r03.json", evidence / "source-clause-author-review-r03.json")],
        "ja": [(evidence / "japanese-transfer-all80-review-r01.json", evidence / "japanese-transfer-author-review-r01.json")],
        "es": [(spanish / "all80-review-r02.json", spanish / "author-review-r01.json")],
    }
    for pair, files in packets.items():
        for packet_path, review_path in files:
            packet, review = read(packet_path), read(review_path)
            labels = {(row["id"], s["scope_id"]): s for row in review["rows"]
                      for s in row.get("labels", row.get("scopes", []))}
            for row in packet["rows"]:
                for span in row["scopes"]:
                    if not span["lexicon_id"].startswith(("word-", "question-")):
                        continue
                    label = labels[(row["id"], span["scope_id"])]
                    observations[pair][span["lexicon_id"]].append(dict(
                        case_id=row["id"], scope_id=span["scope_id"],
                        translated=span["translated"],
                        label=label.get("label", label.get("judgment")),
                        reading_status=label.get("reading_status")))

    for row in read(evidence / "source-word-valid-author-review-r01.json")["rows"]:
        for span in row["scopes"]:
            observations["sw"][span["lexicon_id"]].append(dict(
                case_id=row["id"], source_start_utf16=span["sourceStartUTF16"],
                source_end_utf16=span["sourceEndUTF16"], translated=span["translated"],
                label=span["semantic_label"]))

    for name in ("source-word-valid-root-review-r01.json", "source-concept-root-review-r02.json",
                 "source-clause-root-review-r03.json", "japanese-transfer-independent-root-review-r01.json",
                 "spanish-transfer-independent-review-r01.json", "spanish-transfer-independent-context-amendment-r01.json"):
        read(evidence / name)  # Exact independent-review bindings; original disagreements stay retained.

    native = read(args.android_reading_receipt)
    assert inputs[str(args.android_reading_receipt)] == "3b148240f292584aa18061bed7b0bbbbeb16a3d70914146fe4949bc11bb255fa"
    matawa = next(r for r in native["japanese_reading_diagnostic_only"] if r["original"] == "または")
    assert matawa["speech_kana"] == "マタワ"
    assert matawa["tokens"][0]["reading"] == "マタハ"
    assert matawa["tokens"][0]["pronunciation"] == "マタワ"

    pairs = {}
    for target in ("sw", "ja", "es"):
        lexicon_name = "reviewed-word-lexicon-en-sw-r02.json" if target == "sw" else f"reviewed-word-lexicon-en-{target}-transfer-r01.json"
        rules_name = "source-question-rules-r02.json" if target == "sw" else f"source-question-rules-en-{target}-transfer-r01.json"
        lexicon, rules = read(q / lexicon_name), read(q / rules_name)
        source_entries = {row["id"]: row for row in lexicon["entries"]}
        for phrase, rule in {**rules["single_words"], **rules["units"]}.items():
            entry_id = f"question-en-{target}-" + phrase.replace(" ", "-")
            source_entries[entry_id] = dict(rule, id=entry_id, source=phrase,
                category="function", pos="interrogative", train_rank=16, guard="interrogative")
        eligible, unresolved, unexercised, unchanged = [], [], [], []
        for entry_id, source in sorted(source_entries.items()):
            observed = observations[target].get(entry_id, [])
            if canonical(source["source"]) == canonical(source["target"]):
                unchanged.append(entry_id)
                continue
            if not observed:
                unexercised.append(entry_id)
                continue
            assert all(x["translated"] == source["target"] for x in observed), entry_id
            if any(x["label"] not in ("correct", "minor") for x in observed):
                unresolved.append(dict(id=entry_id, observations=observed))
                continue
            entry = {key: source[key] for key in (
                "id", "source", "target", "category", "pos", "train_rank", "guard", "following",
                "reading", "reading_kana") if key in source}
            entry["source_tokens"] = source["source"].split()
            entry["observed_reviews"] = observed
            entry["primary_evidence_sha256"] = hashlib.sha256(json.dumps(
                source.get("evidence", {}), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if target == "ja":
                assert source["reading"] and source["reading_kana"]
                if source["target"] == "または":
                    assert source["reading"] == "mataha"
                    entry.update(reading="matawa", pronunciation_kana="またわ",
                        reading_correction=dict(kind="exact_lexical_pronunciation_override",
                            original_frozen_reading="mataha", native_receipt_sha256=inputs[str(args.android_reading_receipt)],
                            primary_url="https://bibdb.ninjal.ac.jp/bunken/ja/article/100000126715",
                            scope="Only this lexical conjunction. Orthographic reading remains または. No blanket は replacement."))
                else:
                    assert all(x.get("reading_status") in (None, "supported") for x in observed)
            eligible.append(entry)
        pairs[f"en-{target}"] = dict(entries=eligible, excluded_unresolved=unresolved,
            withheld_unexercised=unexercised, excluded_unchanged_faces=unchanged,
            target_unavailable=lexicon.get("unavailable", []),
            summary=dict(eligible_units=len(eligible),
                content_units=sum(x["category"] == "content" for x in eligible),
                function_units=sum(x["category"] == "function" for x in eligible),
                question_units=sum(x.get("guard") == "interrogative" for x in eligible),
                unresolved_units=len(unresolved), unexercised_units=len(unexercised)))

    output = dict(schema="vipi-reviewed-source-unit-native-candidate-1", production=False,
        status="Proposed native qualification input; root promotion and both routing qualifications required.",
        selection_basis="Post-review observed-unit subset of TRAIN-derived frozen mappings. No held-out phrase is added as a source mapping. Not a fresh blind result.",
        input_sha256=inputs, compiler_sha256=sha(Path(__file__)),
        source_policy_sha256=sha(q / "evaluate_source_concepts.py"),
        routing_contract_sha256=sha(q / "source-unit-routing-contract-r01.json"),
        source_context_sets=dict(determiners=sorted(DETERMINERS), prepositions=sorted(PREPOSITIONS),
            object_verbs=sorted(OBJECT_VERBS), copulas=sorted(COPULAS)),
        runtime_contract=dict(source_language="en", target_languages=["sw", "ja", "es"],
            source_language_confirmation="Keep existing explicit-input/identifier language confirmation; no model-readiness dependency for an approved hit.",
            precedence="Existing exact whole/sentence-reference lookup first; this candidate only supplies source units when those paths yield no useful approved face.",
            selection="Beginner qualification selects at most one unit, preferring content then TRAIN rank then longer unit then source offset, as the frozen primary arm. Unchanged normalized faces never count.",
            boundaries="Native word boundaries and exact UTF16 source ranges required. Never slice an inflected word or use target-dependent dictionary alignment as source proof.",
            protections="Reuse frozen protected identifiers/code, source case rules, explicit noun and interrogative guards. Native parity must be demonstrated; Python ranges are not native proof.",
            presentation="Existing SourceReferenceUnit and PartialImmersionResult; no fabricated whole-message translation. Mandatory exact Japanese reading travels with the target.",
            full_translation="Use accepted routing intent: explicit full action or lookup miss. Preserve current source slots on complete-reference attachment.",
            density="This is a beginner single-unit increment. Greater depth and learned-word exhaustion are not solved by its availability count.",
            deployment="Do not install as runtime assets or enable until parent review and native acceptance. No new model/runtime/provider dependency."),
        japanese_particle_audit=[
            dict(target="はい", kana="はい", latin="hai", decision="Lexical syllable ha; retain."),
            dict(target="または", kana="または", latin="matawa", decision="Lexical conjunction uses wa pronunciation; exact override plus native pronunciation proof."),
            dict(target="浜辺", kana="はまべ", latin="hamabe", decision="Lexical syllable ha; retain."),
            dict(target="母", kana="はは", latin="haha", decision="Both are lexical ha syllables; retain."),
            dict(target="部屋", kana="へや", latin="heya", decision="Lexical syllable he; retain."),
            dict(target="犯罪", kana="はんざい", latin="hanzai", decision="Lexical syllable ha; retain.")],
        licenses=dict(sw="Kaikki/Wiktionary CC-BY-SA-4.0; exact proof remains in source lexicon.",
            ja="JMdict/EDRDG CC-BY-SA-4.0; attribution/license and exact proof retained. 知っている separately authored/primary-verified.",
            es="Kaikki/Wiktionary CC-BY-SA-4.0; exact proof remains in retained per-word primary records."),
        limitations=["Assistant meaning review is not native bilingual certification or a language-learning outcome study.",
            "Unexercised mappings are retained for future evaluation, not marked linguistically rejected.",
            "No current-production call/latency comparison on these selected conversational samples has yet been captured.",
            "Only English-source three-target candidate; no reverse direction or eleven-language coverage claim.",
            "All15 finite-clause rules remain outside this initial native increment."], pairs=pairs)
    assert [pairs[f"en-{x}"]["summary"]["eligible_units"] for x in ("sw", "ja", "es")] == [109, 47, 43]
    assert not args.output.exists()
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({p: v["summary"] for p, v in pairs.items()}, indent=2))
    print(sha(args.output))


if __name__ == "__main__":
    main()
