#!/usr/bin/env python3
"""QA-only source lookup ceiling: retained patterns, greetings, unique words.

No target translation is supplied or consulted. Grammar/conversation accuracy
must be reviewed after matching. This is not native code or a shipping pack.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from noun_boundary_experiment import Dictionary, digest, mixed, tokens, u16
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "source_lookup_experiment"))
from matcher import Matcher

SOCIAL = {"hello", "hi", "thanks", "thank you", "thanks a lot", "thank you very much", "see you tomorrow", "what's up"}
PROTECTED = re.compile(r"https?://\S+|\b[^\s@]+@[^\s@]+\.[^\s@]+|```[\s\S]*?```|`[^`]*`")


def free_of_protected(text, start, end):
    return not any(m.start() < end and start < m.end() for m in PROTECTED.finditer(text))


def social_entries(catalog, source, target):
    found = collections.defaultdict(set)
    for row in catalog["references"]:
        key = row["original"].lower().rstrip(".!?")
        if row["pair"] == source + "-" + target and key in SOCIAL:
            # Punctuation stays in the original message; the target face is the
            # complete already-retained formula, not new inferred wording.
            value = row["translation"].strip().strip(".?!¿¡")
            found[key].add(value)
    return {key: next(iter(values)) for key, values in found.items() if len(values) == 1}


def social_spans(text, formulas):
    spans = []
    for source, target in sorted(formulas.items(), key=lambda row: -len(row[0])):
        pattern = re.compile(r"(?<![\w'’])" + re.escape(source).replace(r"\ ", r"[ \t]+") + r"(?![\w'’])", re.I)
        for match in pattern.finditer(text):
            before, after = text[:match.start()], text[match.end():]
            # A social opening is clause-initial, never a naked word anywhere.
            if before.strip() and not re.search(r"[.!?;\n]\s*$", before):
                continue
            if not free_of_protected(text, match.start(), match.end()):
                continue
            allowed = not after.strip() or bool(re.match(r"\s*[,.!?;\n]", after))
            # Bounded external greeting/vocative context. No names are changed.
            if source in {"hello", "hi"}:
                allowed |= bool(re.match(r"[ \t]+(?:my[ \t]+(?:love|dear)|sir|madam|dear|[A-Z][a-z]{1,24})(?:[ \t]*[,.!?;]|[ \t]+(?:how|are|what|i|we|you)\b|[ \t]*$)", after, re.I if after[:8].lower().startswith((" my ", " sir", " madam", " dear")) else 0))
            if source.startswith("thank"):
                allowed |= bool(re.match(r"[ \t]+for\b", after, re.I))
            if not allowed:
                continue
            spans.append({"sourceStartUTF16": u16(before), "sourceEndUTF16": u16(text[:match.end()]),
                          "original": match.group(), "translated": target, "origin": "source_only_reviewed_social_scope_trial",
                          "matched_source_context": text[match.start():min(len(text), match.end() + 64)]})
    return spans


def target_index(dictionary):
    output = collections.defaultdict(dict)
    rows = dictionary.db.execute("""SELECT t.sense,s.surface,s.normalized,s.start,s.end,s.number,s.mode,s.lexeme,l.pos
        FROM surfaces s JOIN lexemes l ON l.id=s.lexeme JOIN terms t ON t.lexeme=s.lexeme
        WHERE t.eligible=1 AND l.target_safe=1 AND l.pos IN ('noun','adj','adv','verb') AND s.mode IN (1,2)
        ORDER BY t.sense,s.surface,s.lexeme"""
    )
    for sense, surface, key, start, end, number, mode, lexeme, pos in rows:
        if start != 0 or end != u16(surface) or len(surface) > 96:
            continue
        guard = dictionary.guard(key)
        if guard and guard["target_blocked"]:
            continue
        output[(sense, pos, number)][surface] = lexeme
    return output


def unique_words(text, source_dictionary, targets):
    spans = []
    for token in tokens(text):
        forms = source_dictionary.analyses(token["key"])
        guard = source_dictionary.guard(token["key"])
        if not forms or (guard and guard["blocked"]) or len({f["lexeme"] for f in forms}) != 1:
            continue
        if not free_of_protected(text, token["start"], token["end"]):
            continue
        claims = collections.defaultdict(list)
        for form in forms:
            if not form["source_safe"] or form["pos"] not in {"noun", "adj", "adv", "verb"}:
                continue
            if form["mode"] not in (1, 2) or form["start"] != 0 or form["end"] != u16(form["surface"]):
                continue
            written = form["surface"]
            if token["text"] != written:
                initial = not text[:token["start"]].strip() or bool(re.search(r"[.!?]\s*$", text[:token["start"]]))
                if not (initial and token["text"][:1].isupper() and token["text"][1:] == written[1:] and written[:1].islower()):
                    continue
            for term in form["terms"]:
                if not term["eligible"]:
                    continue
                for target, lexeme in targets.get((term["sense"], form["pos"], form["number"]), {}).items():
                    claims[target].append({"source_lexeme": form["lexeme"], "target_lexeme": lexeme,
                                           "sense": term["sense"], "source_url": term["source_url"]})
        if len(claims) != 1:
            continue
        target, evidence = next(iter(claims.items()))
        if target.lower() == token["key"]:
            continue
        spans.append({"sourceStartUTF16": token["rangeUTF16"][0], "sourceEndUTF16": token["rangeUTF16"][1],
                      "original": token["text"], "translated": target,
                      "origin": "source_only_single_analysis_unique_counterpart_trial", "evidence": evidence})
    return spans


def select(spans):
    selected = []
    for span in sorted(spans, key=lambda s: (-(s["sourceEndUTF16"] - s["sourceStartUTF16"]), s["sourceStartUTF16"])):
        if any(span["sourceStartUTF16"] < s["sourceEndUTF16"] and s["sourceStartUTF16"] < span["sourceEndUTF16"] for s in selected):
            continue
        selected.append(span)
    return sorted(selected, key=lambda s: s["sourceStartUTF16"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--dictionary-dir", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite retained result")
    protocol = json.loads(args.protocol.read_text())
    catalog = json.loads(args.catalog.read_text())
    pack = json.loads((args.candidate / "pack.json").read_text())
    frozen = json.loads((args.candidate / "freeze.json").read_text())
    assert digest(args.candidate / "pack.json") == frozen["pack_sha256"]
    matcher = Matcher(pack)
    dictionaries = {lang: Dictionary(args.dictionary_dir / f"d-{lang}.sqlite") for lang in {"en", "es", "sw"}}
    indexes = {lang: target_index(dictionaries[lang]) for lang in ("es", "sw")}
    rows = []
    for case in protocol["cases"]:
        if case["source"] != "en" or case["target"] not in indexes:
            continue
        original, target = case["text"], case["target"]
        _, raw = matcher.present(original, "en", target)
        previous = [{"sourceStartUTF16": s["sourceStartUTF16"], "sourceEndUTF16": s["sourceEndUTF16"],
                     "original": s["original"], "translated": s["targetText"], "origin": "retained_source_phrase_candidate3",
                     "mappingId": s["mappingId"]} for s in raw]
        social = social_spans(original, social_entries(catalog, "en", target))
        words = unique_words(original, dictionaries["en"], indexes[target])
        combined = select(previous + social + words)
        count = len(tokens(original))
        covered = sum(sum(s["sourceStartUTF16"] <= t["rangeUTF16"][0] and s["sourceEndUTF16"] >= t["rangeUTF16"][1] for t in tokens(original)) for s in combined)
        rows.append({**case, "spans": combined, "visible": mixed(original, combined),
                     "source_only_parts": {"prior_phrase": len(previous), "social": len(social), "unique_word": len(words)},
                     "python_word_depth": covered / max(1, count)})
    summary = {}
    for target in ("es", "sw"):
        group = [r for r in rows if r["target"] == target]
        if group:
            summary["en-" + target] = {"messages": len(group), "with_span": sum(bool(r["spans"]) for r in group),
                                        "spans": sum(len(r["spans"]) for r in group), "mean_python_word_depth": statistics.mean(r["python_word_depth"] for r in group),
                                        "semantic_review": "pending"}
    report = {"schema": "vipi-source-only-ceiling-1", "production": False, "translation_calls": 0,
              "input_sha256": digest(args.protocol), "catalog_sha256": digest(args.catalog), "runner_sha256": digest(Path(__file__)),
              "dictionary_hashes": {lang: digest(args.dictionary_dir / f"d-{lang}.sqlite") for lang in dictionaries},
              "prior_candidate_sha256": frozen["pack_sha256"], "summary": summary, "results": rows}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
