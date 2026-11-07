#!/usr/bin/env python3
"""QA only: compare two-sided noun grammar cues against retained translations.

This is deliberately not a production parser or a replacement for native guards.
It keeps competing dictionary analyses and tests whether grammar resolves form
ambiguity. A matching full translation is evidence, not semantic ground truth.
No translation service is called and no dictionary is modified.
"""
import argparse
import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path

TOKEN = re.compile(r"[^\W_]+(?:['’][^\W_]+)?", re.UNICODE)
QUANTITIES = {
    "en": dict(zip("two three four five six seven eight nine ten".split(), range(2, 11))),
    "es": dict(zip("dos tres cuatro cinco seis siete ocho nueve diez".split(), range(2, 11))),
}
DETERMINERS = {
    "en": {"a": ("indefinite", 0), "an": ("indefinite", 0), "the": ("definite", None),
           "my": ("possessive-1sg", None), "our": ("possessive-1pl", None)},
    "es": {"un": ("indefinite", 0), "una": ("indefinite", 0),
           "el": ("definite", 0), "la": ("definite", 0),
           "los": ("definite", 2), "las": ("definite", 2),
           "mi": ("possessive-1sg", 0), "mis": ("possessive-1sg", 2),
           "nuestro": ("possessive-1pl", 0), "nuestra": ("possessive-1pl", 0),
           "nuestros": ("possessive-1pl", 2), "nuestras": ("possessive-1pl", 2)},
}
RIGHT_BOUNDARIES = {
    "en": set("is are was were has have had will can could should must may might would do does did in on at by with without from to for of near under over inside outside between beside after before until and or but".split()),
    "es": set("es son era eran está están estaba estaban tiene tienen tuvo hay puede pueden debe deben en con sin de del al a por para cerca debajo encima dentro fuera entre junto desde hasta y o pero".split()),
}
GRAMMATICAL = {"pron", "det", "prep", "postp", "conj", "particle", "article", "aux"}
NUMBER_PARTS = set("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand million cero uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince dieciséis diecisiete dieciocho diecinueve veinte treinta cuarenta cincuenta sesenta setenta ochenta noventa cien ciento mil millón menos minus negative".split())


def digest(path):
    with Path(path).open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def u16(text):
    return len(text.encode("utf-16-le")) // 2


def tokens(text):
    return [{"text": m.group(), "key": m.group().lower(), "start": m.start(), "end": m.end(),
             "rangeUTF16": [u16(text[:m.start()]), u16(text[:m.end()])]} for m in TOKEN.finditer(text)]


class Dictionary:
    def __init__(self, path):
        self.db = sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro&immutable=1", uri=True)
        self.db.row_factory = sqlite3.Row
        self.cache = {}
        self.guards = {}

    def guard(self, word):
        if word not in self.guards:
            row = self.db.execute("SELECT * FROM guards WHERE normalized=?", (word,)).fetchone()
            self.guards[word] = dict(row) if row else None
        return self.guards[word]

    def analyses(self, word):
        if word not in self.cache:
            rows = self.db.execute("""SELECT s.*,l.pos,l.source_safe,l.target_safe,l.headword,
                COALESCE(g.reason,'') AS guard_reason,COALESCE(g.target_blocked,0) AS grammar_guard
                FROM surfaces s JOIN lexemes l ON l.id=s.lexeme
                LEFT JOIN guards g ON g.normalized=l.normalized WHERE s.normalized=?
                ORDER BY s.lexeme,s.mode,s.features""", (word,))
            forms = []
            for row in rows:
                form = dict(row)
                form["features"] = json.loads(form["features"])
                form["terms"] = [dict(term) for term in self.db.execute("""SELECT t.sense,t.eligible,
                    t.reading,s.explicit,s.label,s.source_url FROM terms t JOIN senses s ON s.id=t.sense
                    WHERE t.lexeme=? ORDER BY t.sense,t.reading""", (form["lexeme"],))]
                forms.append(form)
            self.cache[word] = forms
        return self.cache[word]

    def protected(self, text, words, index):
        # Existing dictionary protection only, not invented idiom patches.
        protections = []
        for start in range(max(0, index - 5), index + 1):
            for end in range(index + 1, min(len(words), start + 6) + 1):
                if end - start < 2:
                    continue
                raw = text[words[start]["start"]:words[end - 1]["end"]]
                if not re.fullmatch(r"[^\W_]+(?:['’][^\W_]+)?(?:\s+[^\W_]+(?:['’][^\W_]+)?)+", raw):
                    continue
                key = " ".join(raw.lower().split())
                guard = self.guard(key)
                if guard and guard["protect_inner"]:
                    protections.append({"text": raw, "guard": guard})
        return protections


def cue_for(text, words, index, language, arm):
    if index == 0:
        return None
    prev, word = words[index - 1], words[index]
    if not re.fullmatch(r"[ \t]+", text[prev["end"]:word["start"]]):
        return None
    key = prev["key"]
    if arm == "quantity":
        if prev["start"] and text[prev["start"] - 1] in "0123456789./:,+-−":
            return None
        if index >= 2 and words[index - 2]["key"] in NUMBER_PARTS:
            return None
        value = QUANTITIES[language].get(key)
        if key.isascii() and key.isdigit() and 2 <= int(key) <= 10:
            value = int(key)
        if value is not None:
            return {"kind": "quantity", "value": value, "number": 2, "token": prev}
    elif key in DETERMINERS[language]:
        kind, number = DETERMINERS[language][key]
        return {"kind": kind, "value": None, "number": number, "token": prev}
    return None


def right_boundary(text, words, index, language):
    word = words[index]
    if index + 1 == len(words):
        return "end"
    following = words[index + 1]
    between = text[word["end"]:following["start"]]
    if re.search(r"[.!?,;:。！？\r\n]", between):
        return "punctuation"
    if re.fullmatch(r"[ \t]+", between) and following["key"] in RIGHT_BOUNDARIES[language]:
        return "bounded-function-or-finite-context"
    return None


def noun_candidates(dictionary, text, language, arm):
    words = tokens(text)
    output = []
    for index, token in enumerate(words):
        cue = cue_for(text, words, index, language, arm)
        if cue is None:
            continue
        all_forms = dictionary.analyses(token["key"])
        trace = {"token": token, "cue": cue, "analyses": [], "reasons": []}
        protection = dictionary.protected(text, words, index)
        if protection:
            trace["reasons"].append("retained_phrase_protection")
            trace["protections"] = protection
        if not right_boundary(text, words, index, language):
            trace["reasons"].append("right_boundary_unproved")
        # Targets need actual complete lower-case forms. A leading sentence
        # capital is on the cue, never on its following common noun.
        if not token["text"].islower():
            trace["reasons"].append("proper_or_nonlowercase_written_form")
        guard = dictionary.guard(token["key"])
        if guard and guard["target_blocked"]:
            trace["reasons"].append("target_blocked_guard")
        if sum(other["key"] == token["key"] for other in words) != 1:
            trace["reasons"].append("repeated_source_or_target_surface")
        usable = []
        for form in all_forms:
            reasons = []
            if form["pos"] != "noun":
                reasons.append("not_noun")
            if form["mode"] not in (1, 2) or form["start"] != 0 or form["end"] != u16(form["surface"]):
                reasons.append("not_supplied_complete_form")
            if not form["target_safe"] or form["grammar_guard"] or form["guard_reason"] == "grammar":
                reasons.append("unsafe_or_grammatical_analysis")
            if form["surface"] != token["text"]:
                reasons.append("written_case_differs")
            if cue["number"] is not None and cue["number"] != form["number"]:
                reasons.append("cue_number_incompatible")
            if not any(term["eligible"] for term in form["terms"]):
                reasons.append("no_eligible_dictionary_sense")
            trace["analyses"].append({**form, "reasons": reasons})
            if not reasons:
                usable.append(form)
        if not usable:
            trace["reasons"].append("no_complete_noun_analysis")
        trace["usable_lexemes"] = sorted({form["lexeme"] for form in usable})
        trace["_usable"] = usable if not trace["reasons"] else []
        output.append(trace)
    return output


def witnesses(db, source, target, original, noun, counterpart):
    words = tokens(original)
    focus = noun["token"]
    found = []
    for token in words:
        if token["end"] <= focus["start"]:
            side, lo, hi = "L:", token["end"], focus["start"]
        elif token["start"] >= focus["end"]:
            side, lo, hi = "R:", focus["end"], token["start"]
        else:
            continue
        if re.search(r"[.!?。！？;；\r\n]", original[lo:hi]) or len(tokens(original[lo:hi])) >= 6:
            continue
        row = db.execute("""SELECT cue,support,total FROM witnesses
            WHERE source=? AND target=? AND word=? AND counterpart=? AND cue=?""",
            (source, target, focus["key"], counterpart, side + token["key"])).fetchone()
        if row and row[1] >= 3 and row[1] / row[2] >= 0.98:
            found.append({"cue": row[0], "support": row[1], "total": row[2]})
    return found


def run_case(case, dictionaries, witness_db, arm):
    original, translated = case["original"], case["translation"]
    left = noun_candidates(dictionaries[case["source"]], original, case["source"], arm)
    right = noun_candidates(dictionaries[case["target"]], translated, case["target"], arm)
    spans = []
    for noun in left:
        claims = {}
        noun["comparisons"] = []
        for counterpart in right:
            cue_a, cue_b = noun["cue"], counterpart["cue"]
            reason = None
            if (cue_a["kind"], cue_a["value"]) != (cue_b["kind"], cue_b["value"]):
                reason = "cue_identity_differs"
            if noun["token"]["key"] == counterpart["token"]["key"]:
                reason = "no_meaningful_written_change"
            def sentence_index(text, token):
                return len(re.findall(r"[.!?。！？;；\r\n]+", text[:token["start"]]))
            if sentence_index(original, noun["token"]) != sentence_index(translated, counterpart["token"]):
                reason = "sentence_scope_differs"
            pairs = []
            if reason is None:
                for a in noun["_usable"]:
                    for b in counterpart["_usable"]:
                        if a["number"] != b["number"]:
                            continue
                        meanings_a = {term["sense"] for term in a["terms"] if term["eligible"]}
                        meanings_b = {term["sense"] for term in b["terms"] if term["eligible"]}
                        shared = meanings_a & meanings_b
                        if shared:
                            pairs.append({"source_lexeme": a["lexeme"], "target_lexeme": b["lexeme"],
                                          "number": a["number"], "shared_senses": sorted(shared),
                                          "source_unshared_senses": sorted(meanings_a - meanings_b)})
            if not pairs and reason is None:
                reason = "no_complete_compatible_shared_sense_pair"
            comparison = {"target_rangeUTF16": counterpart["token"]["rangeUTF16"],
                          "target": counterpart["token"]["text"], "pairs": pairs, "reason": reason}
            noun["comparisons"].append(comparison)
            if pairs:
                start, end = counterpart["token"]["rangeUTF16"]
                claims[(start, end)] = comparison
        if len(claims) != 1:
            noun["decision"] = "reject_ambiguous_target" if claims else "reject_no_target"
            continue
        (start, end), claim = next(iter(claims.items()))
        noun["decision"] = "accept_grammar_only_candidate"
        support = witnesses(witness_db, case["source"], case["target"], original, noun, claim["target"].lower())
        spans.append({"sourceStartUTF16": noun["token"]["rangeUTF16"][0],
                      "sourceEndUTF16": noun["token"]["rangeUTF16"][1],
                      "original": noun["token"]["text"], "translated": claim["target"],
                      "targetStartUTF16": start, "targetEndUTF16": end,
                      "reading": None, "arm": arm, "retained_witnesses": support,
                      "unshared_source_senses": any(p["source_unshared_senses"] for p in claim["pairs"]),
                      "reason": "two_sided_matching_nominal_cue_complete_forms_unique_shared_sense_target"})
    # Distinct source words cannot independently claim the same translated span.
    target_counts = {}
    for span in spans:
        key = (span["targetStartUTF16"], span["targetEndUTF16"])
        target_counts[key] = target_counts.get(key, 0) + 1
    for noun in left:
        for key in list(noun):
            if key.startswith("_"):
                noun.pop(key)
    for noun in right:
        noun.pop("_usable")
    accepted = [span for span in spans if target_counts[(span["targetStartUTF16"], span["targetEndUTF16"]) ] == 1]
    return {"arm": arm, "source_candidates": left, "target_candidates": right, "spans": accepted}


def mixed(original, spans):
    value = original.encode("utf-16-le")
    for span in sorted(spans, key=lambda x: x["sourceStartUTF16"], reverse=True):
        a, b = span["sourceStartUTF16"] * 2, span["sourceEndUTF16"] * 2
        value = value[:a] + span["translated"].encode("utf-16-le") + value[b:]
    return value.decode("utf-16-le")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dictionary-dir", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite retained result")
    dictionaries = {lang: Dictionary(args.dictionary_dir / f"d-{lang}.sqlite") for lang in ("en", "es")}
    witness_path = args.dictionary_dir / "w-en-es.sqlite"
    witness_db = sqlite3.connect(f"file:{witness_path.resolve()}?mode=ro&immutable=1", uri=True)
    protocol = json.loads(args.input.read_text())
    report = {"schema": "vipi-noun-boundary-qa-1", "production": False, "fresh_translation_calls": 0,
              "input_sha256": digest(args.input), "runner_sha256": digest(__file__),
              "dictionary_hashes": {lang: digest(args.dictionary_dir / f"d-{lang}.sqlite") for lang in ("en", "es")},
              "witness_sha256": digest(witness_path), "results": []}
    for case in protocol["cases"]:
        start = time.perf_counter()
        result = {"id": case["id"], "original": case["original"], "translation": case["translation"],
                  "source": case["source"], "target": case["target"], "translation_provenance": case["translation_provenance"]}
        arms = [run_case(case, dictionaries, witness_db, arm) for arm in ("quantity", "determiner")]
        for arm in arms:
            arm["mixed"] = mixed(case["original"], arm["spans"])
            arm["witness_supported_spans"] = [span for span in arm["spans"] if span["retained_witnesses"]]
        result.update(arms=arms, elapsed_ms=(time.perf_counter() - start) * 1000)
        report["results"].append(result)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "cases": len(report["results"]),
                      "spans": {arm: sum(len(r["arms"][i]["spans"]) for r in report["results"])
                                for i, arm in enumerate(("quantity", "determiner"))}}))


if __name__ == "__main__":
    main()
