#!/usr/bin/env python3
"""Experimental source-only English progressive clauses → attested Swahili forms.

Uses complete conjugated forms supplied by Wiktionary, never generated affixes.
English present participles come from the retained dictionary. A source match
requires no full translation. Grammar applicability does not prove word sense.
"""
import argparse
import collections
import json
from pathlib import Path
import re
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from noun_boundary_experiment import digest, mixed, u16

PERSONS = {"i": {"first-person", "singular"}, "we": {"first-person", "plural"},
           "he": {"third-person", "singular", "class-1", "class-2"},
           "she": {"third-person", "singular", "class-1", "class-2"}}
CLAUSE = re.compile(r"(?<![\w'’])(?P<person>I|we|he|she|they|you|it)(?P<aux>[ \t]+(?:am|are|is)|['’](?:m|re|s))[ \t]+(?P<verb>[a-z]+ing)\b", re.I)
PROTECTED = re.compile(r'https?://\S+|\b[^\s@]+@[^\s@]+\.[^\s@]+|`[^`]*`|"[^"]*"|“[^”]*”')
FUTURE = re.compile(r"\b(?:tomorrow|tonight|next|later|soon|eventually)\b", re.I)
PARTICLE = re.compile(r"[ \t]+(?:up|down|off|out|over|away|through|back|around|about|into)\b", re.I)


def build(source, english):
    db = sqlite3.connect(f"file:{english.resolve()}?mode=ro&immutable=1", uri=True)
    gerunds = collections.defaultdict(set)
    for head, surface, features in db.execute("SELECT l.headword,s.surface,s.features FROM lexemes l JOIN surfaces s ON s.lexeme=l.id WHERE l.pos='verb'"):
        tags = set(json.loads(features))
        if {"present", "participle"} <= tags and re.fullmatch("[a-z]+ing", surface):
            gerunds[head].add(surface)
    entries = []
    for line_number, line in enumerate(source.open(), 1):
        row = json.loads(line)
        if row.get("pos") != "verb":
            continue
        forms = collections.defaultdict(set)
        for form in row.get("forms", []):
            tags = set(form.get("tags", []))
            for person, features in PERSONS.items():
                if tags == features | {"present"} and re.fullmatch("[a-z]+", form["form"]):
                    forms[person].add(form["form"])
        if set(forms) != set(PERSONS):
            continue
        for sense in row.get("senses", []):
            for gloss in sense.get("glosses", []):
                match = re.fullmatch(r"to ([a-z]+)", gloss)
                if not match:
                    continue
                lemma = match[1]
                for gerund in gerunds[lemma]:
                    entries.append({"english_lemma": lemma, "english_participle": gerund,
                                    "swahili_headword": row["word"], "gloss": gloss,
                                    "source_line": line_number,
                                    "source_url": "https://en.wiktionary.org/wiki/" + row["word"],
                                    "attested_forms": {p: sorted(v) for p, v in forms.items()},
                                    "selected_forms": {p: sorted(v, key=lambda x: (-len(x), x))[0] for p, v in forms.items()}})
    return entries


def match(text, entries):
    index = collections.defaultdict(list)
    for entry in entries:
        index[entry["english_participle"]].append(entry)
    spans, rejected = [], []
    for m in CLAUSE.finditer(text):
        person, verb = m["person"].lower(), m["verb"].lower()
        before, after = text[:m.start()], text[m.end():]
        scoped_after = re.split(r"[.!?;\n]", after, 1)[0]
        reason = None
        if any(p.start() < m.end() and m.start() < p.end() for p in PROTECTED.finditer(text)):
            reason = "quoted_or_protected"
        elif before.strip() and not re.search(r"(?:[.!?;\n]|\b(?:and|but))\s*$", before, re.I):
            reason = "source_clause_boundary_unproved"
        elif person not in PERSONS:
            reason = "person_number_or_noun_class_ambiguous"
        elif m["aux"].strip().replace("’", "'").lower() not in ({"am", "'m"} if person == "i" else {"are", "'re"} if person == "we" else {"is", "'s"}):
            reason = "subject_auxiliary_disagreement"
        elif FUTURE.search(scoped_after):
            reason = "future_reading_not_qualified"
        elif PARTICLE.match(after) or (verb == "going" and re.match(r"\s+to\b", after, re.I)):
            reason = "particle_or_auxiliary_sense_unqualified"
        elif verb not in index:
            reason = "no_attested_bilingual_participle"
        claims = index.get(verb, [])
        choices = {r["selected_forms"].get(person) for r in claims} - {None}
        if reason is None and len(choices) != 1:
            reason = "competing_target_lexemes"
        evidence = {"source": m.group(), "source_range": [u16(before), u16(text[:m.end()])],
                    "english_participle": verb, "claims": claims}
        if reason:
            rejected.append({**evidence, "reason": reason})
            continue
        spans.append({"sourceStartUTF16": u16(before), "sourceEndUTF16": u16(text[:m.end()]),
                      "original": m.group(), "translated": next(iter(choices)),
                      "origin": "eval_only_attested_finite_source_clause", "evidence": evidence})
    return {"status": "matched" if spans else "ambiguous" if rejected else "inapplicable",
            "spans": spans, "rejections": rejected, "visible": mixed(text, spans)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--english", type=Path, required=True)
    p.add_argument("--protocol", type=Path, action="append", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        p.error("refusing to overwrite evidence")
    entries = build(args.source, args.english)
    rows = []
    for path in args.protocol:
        for case in json.loads(path.read_text())["cases"]:
            if case["source"] == "en" and case["target"] == "sw":
                rows.append({**case, "protocol_sha256": digest(path), **match(case["text"], entries)})
    value = {"schema": "vipi-attested-finite-source-clause-experiment-1", "production": False,
             "translation_calls": 0, "source_sha256": digest(args.source), "english_sha256": digest(args.english),
             "runner_sha256": digest(__file__), "license": "Wiktionary/Kaikki CC BY-SA 4.0; per-entry source URLs retained",
             "limitations": "Exact English gloss and attested inflections prove form provenance, not source word sense. Person/number, scope, and some particle/future traps abstain. Author review required.",
             "entries": entries, "summary": {"entries": len(entries), "distinct_participles": len({e['english_participle'] for e in entries}),
             "statuses": dict(collections.Counter(r["status"] for r in rows)),
             "rejection_reasons": dict(collections.Counter(x["reason"] for r in rows for x in r["rejections"]))}, "results": rows}
    args.output.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(value["summary"], indent=2))


if __name__ == "__main__":
    main()
