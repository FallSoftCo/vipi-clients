#!/usr/bin/env python3
"""Review dictionary-bounded lexical units against retained statistical alignments.

This is an offline development experiment, never a runtime mapping release.
Bidirectional alignment is a proposal mechanism, not semantic certification.
"""
import argparse
from collections import Counter, defaultdict
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "language-packs"))
from context_hints import lookup_key
from prepare_statistical_alignment_pilot import tokenize
from conversation_corpus import sha_file, write_json

def identity(row):
    return tuple(row[k] for k in ["dataset", "id", "source", "target"])

def utf16(text, index):
    return len(text[:index].encode("utf-16-le")) // 2

def units(db, text, language):
    tokens = tokenize(text)
    output = []
    for start in range(len(tokens)):
        for end in range(start + 1, min(start + 5, len(tokens)) + 1):
            a, b = tokens[start][1], tokens[end - 1][2]
            written = text[a:b]
            key = lookup_key(written, language)
            guard = db.execute("SELECT blocked,target_blocked,protect_inner,reason FROM guards WHERE normalized=?", (key,)).fetchone()
            rows = db.execute("""SELECT s.lexeme,s.surface,s.number,s.mode,l.pos,l.target_safe
                FROM surfaces s JOIN lexemes l ON l.id=s.lexeme WHERE s.normalized=?""", (key,)).fetchall()
            if not rows:
                continue
            terms = set()
            readings = set()
            allowed = not guard or not guard[0] and not guard[1]
            eligible = []
            for lexeme, surface, number, mode, pos, safe in rows:
                if not allowed or not safe or mode not in [1, 2] or pos not in ["noun", "adj", "adv"]:
                    continue
                # Native names and grammatical homographs remain protected.
                if surface != written and (surface[:1].isupper() or written[:1].isupper() and text[:a].strip() and text[:a].rstrip()[-1] not in ".!?"):
                    continue
                eligible.append((lexeme, number, pos))
                for sense, explicit, reading in db.execute("""SELECT t.sense,s.explicit,t.reading
                    FROM terms t JOIN senses s ON s.id=t.sense WHERE t.lexeme=? AND t.eligible=1""", (lexeme,)):
                    terms.add((sense, explicit, number, pos))
                    if reading:
                        readings.add(reading)
            output.append(dict(start=start, end=end, a=a, b=b, written=written,
                terms=terms, readings=readings, eligible=eligible,
                protect=bool(guard and guard[2]) or bool(eligible)))
    # Never extract correo from the independently recognized correo electrónico.
    # Keep a complete larger lexical unit even when it has no approved pair link.
    return tokens, [u for u in output if u["terms"] and not any(
        v["protect"] and v["start"] <= u["start"] and v["end"] >= u["end"] and
        (v["start"], v["end"]) != (u["start"], u["end"]) for v in output)]

def closed_alignment(left, right, union, mutual):
    inside = {(a, b) for a, b in union if left["start"] <= a < left["end"] and right["start"] <= b < right["end"]}
    if not inside or not inside & mutual:
        return False
    return not any((left["start"] <= a < left["end"]) != (right["start"] <= b < right["end"]) for a, b in union)

def build(args):
    report = json.loads((args.review / "report.json").read_text())
    assert report["complete"] and not report["runtime_integrated"]
    catalog = json.loads((args.shards / "catalog.json").read_text())
    args.output.mkdir(exist_ok=False)
    grouped = defaultdict(list)
    for row in report["results"]:
        case = row["case"]
        pair = "-".join(sorted([case["source"], case["target"]]))
        grouped[pair].append(case)
    connections = {}
    try:
        for language in {l for pair in grouped for l in pair.split("-")}:
            path = args.shards / (language + ".sqlite")
            expected = next(r for r in catalog["shards"] if r["language"] == language)
            assert path.stat().st_size == expected["bytes"] and sha_file(path) == expected["sha256"]
            db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
            db.execute("PRAGMA cache_size=-8192")
            connections[language] = db
        results = []
        counts = Counter()
        files = []
        for pair, cases in sorted(grouped.items()):
            cases.sort(key=lambda r: hashlib.sha256(json.dumps(identity(r)).encode()).hexdigest())
            lines = []
            for direction in ["forward", "reverse"]:
                path = args.review / (pair + "-" + direction + ".output")
                files.append(dict(file=str(path), sha256=sha_file(path)))
                values = [line.split("|||") for line in path.read_text().splitlines()]
                assert len(values) == len(cases)
                lines.append(values)
            for index, case in enumerate(cases):
                left_language, right_language = pair.split("-")
                original, translation = case["original"], case["translation"]
                left_text, right_text = (original, translation) if case["source"] == left_language else (translation, original)
                left_tokens, left_units = units(connections[left_language], left_text, left_language)
                right_tokens, right_units = units(connections[right_language], right_text, right_language)
                alignments = []
                for direction in range(2):
                    row = lines[direction][index]
                    assert row[0].strip() == " ".join(t[0].casefold() for t in left_tokens)
                    assert row[1].strip() == " ".join(t[0].casefold() for t in right_tokens)
                    links = {tuple(map(int, point.split("-"))) for point in row[2].split()}
                    assert all(0 <= a < len(left_tokens) and 0 <= b < len(right_tokens) for a, b in links)
                    alignments.append(links)
                union, mutual = alignments[0] | alignments[1], alignments[0] & alignments[1]
                proposals = []
                for left in left_units:
                    for right in right_units:
                        senses = left["terms"] & right["terms"]
                        if not senses or not closed_alignment(left, right, union, mutual):
                            continue
                        source, target = (left, right) if case["source"] == left_language else (right, left)
                        proposals.append(dict(source=source["written"], target=target["written"],
                            start=utf16(original, source["a"]), end=utf16(original, source["b"]),
                            target_start=utf16(translation, target["a"]), target_end=utf16(translation, target["b"]),
                            dictionary_senses=sorted({s[0] for s in senses}),
                            multiword=len(tokenize(source["written"])) > 1 or len(tokenize(target["written"])) > 1))
                # Conflicting counterpart geometry remains unresolved.
                counts[pair + ":raw_candidates"] += len(proposals)
                proposals = [p for p in proposals if not any(
                    q != p and (p["start"], p["end"]) == (q["start"], q["end"]) and
                    (p["target_start"], p["target_end"]) != (q["target_start"], q["target_end"])
                    for q in proposals)]
                results.append(dict(case=case, proposals=proposals))
                counts[pair + ":cases"] += 1
                counts[pair + ":nonempty"] += bool(proposals)
                counts[pair + ":proposals"] += len(proposals)
                counts[pair + ":multiword"] += sum(p["multiword"] for p in proposals)
        write_json(args.output / "report.json", dict(complete=True, compiler_sha256=sha_file(Path(__file__)),
            input_report_sha256=sha_file(args.review / "report.json"),
            catalog_sha256=sha_file(args.shards / "catalog.json"), alignment_files=files,
            offsets="UTF-16", counts=dict(counts), results=results,
            method="Complete supplied noun/adjective/adverb units; shared dictionary meaning and POS/number; closed union alignment with a mutual anchor. Competing larger dictionary units protect their interior.",
            reference="https://www2.statmt.org/moses/manual/html/training3.html",
            limitations=["Whole-message translation can still be wrong.", "Statistical alignment and dictionary agreement do not resolve every sense.", "No native integration or independent semantic acceptance."],
            independent_semantic_acceptance=False, runtime_integrated=False))
        print(json.dumps(dict(counts=counts)), flush=True)
    finally:
        for db in connections.values():
            db.close()

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ["review", "shards", "output"]:
        p.add_argument("--" + name, type=Path, required=True)
    build(p.parse_args())
