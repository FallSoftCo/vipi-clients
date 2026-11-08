#!/usr/bin/env python3
"""Select review candidates from licensed TRAIN frequency and retained dictionaries.

No evaluation messages or full translations are read. Candidate links are lexical
evidence only, not accepted semantic mappings or production pack entries.
"""
import argparse
import collections
import hashlib
import json
import re
import sqlite3
from pathlib import Path

WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def u16(text):
    return len(text.encode("utf-16-le")) // 2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--dictionary-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert sha(args.train) == "a5a9672c3e2e8a2f3d740cb0b61810ad46f3e3cd7bbe86b8d79962c6b34ad33c"
    frequency, messages = collections.Counter(), collections.Counter()
    selected_turns = 0
    for conversation in json.loads(args.train.read_text()):
        # Match the conversational domain, while using only the distinct train split.
        if conversation["context_dataset"] != "convai2":
            continue
        for speaker, text in conversation["dialog"]:
            if speaker != 0:
                continue
            words = [m.group().casefold() for m in WORD.finditer(text)]
            frequency.update(words)
            messages.update(set(words))
            selected_turns += 1
    dictionaries = {lang: sqlite3.connect(f"file:{args.dictionary_dir / ('d-'+lang+'.sqlite')}?mode=ro&immutable=1", uri=True)
                    for lang in ("en", "sw")}
    for db in dictionaries.values():
        db.row_factory = sqlite3.Row
    source, target = dictionaries["en"], dictionaries["sw"]
    target_senses = collections.defaultdict(list)
    for row in target.execute("SELECT t.sense,t.eligible,t.reading,l.* FROM terms t JOIN lexemes l ON l.id=t.lexeme"):
        if row["eligible"]:
            target_senses[row["sense"]].append(dict(row))
    target_forms = {}
    rows = []
    for rank, (word, count) in enumerate(sorted(frequency.items(), key=lambda p: (-p[1], p[0]))[:500], 1):
        analyses = []
        candidates = {}
        for row in source.execute("""SELECT s.*,l.pos,l.headword,l.source_safe,l.source_url
                FROM surfaces s JOIN lexemes l ON l.id=s.lexeme WHERE s.normalized=?""", (word,)):
            form = dict(row)
            if form["mode"] not in (1, 2) or form["start"] != 0 or form["end"] != u16(form["surface"]):
                continue
            terms = [dict(t) for t in source.execute("""SELECT t.sense,t.eligible,s.label,s.explicit,s.source_url
                FROM terms t JOIN senses s ON s.id=t.sense WHERE t.lexeme=?""", (form["lexeme"],))]
            form["terms"] = terms
            analyses.append(form)
            for term in terms:
                if not term["eligible"]:
                    continue
                for lexical in target_senses[term["sense"]]:
                    if lexical["pos"] != form["pos"]:
                        continue
                    lexeme = lexical["id"]
                    if lexeme not in target_forms:
                        target_forms[lexeme] = [dict(f) for f in target.execute("SELECT * FROM surfaces WHERE lexeme=?", (lexeme,))
                            if f["mode"] in (1, 2) and f["start"] == 0 and f["end"] == u16(f["surface"])
                            and not f["surface"].startswith("-")]
                    compatible = [f for f in target_forms[lexeme] if f["number"] == form["number"]]
                    if not compatible:
                        continue
                    record = candidates.setdefault(lexeme, dict(lexeme=lexeme, headword=lexical["headword"],
                        pos=lexical["pos"], source_url=lexical["source_url"], evidence=[], forms=[]))
                    record["evidence"].append(dict(source_lexeme=form["lexeme"], source_number=form["number"], **term))
                    known = {(f["surface"], f["number"], f["features"]) for f in record["forms"]}
                    record["forms"] += [f for f in compatible if (f["surface"], f["number"], f["features"]) not in known]
        for candidate in candidates.values():
            candidate["evidence"] = list({(t["source_lexeme"], t["source_number"], t["sense"]): t for t in candidate["evidence"]}.values())
            candidate["forms"].sort(key=lambda f: (f["surface"] != candidate["headword"], len(f["surface"]), f["surface"]))
        rows.append(dict(rank=rank, word=word, train_occurrences=count, train_messages=messages[word],
                         source_analyses=analyses, candidates=sorted(candidates.values(), key=lambda c: (-len(c["evidence"]), c["headword"]))))
    output = dict(schema="vipi-frequency-lexicon-review-candidates-1", production=False, accepted=False,
        training_only=True, evaluation_text_read=False, selected_free_human_train_turns=selected_turns,
        source_license="BlendedSkillTalk dataset CC-BY-4.0; retained Wiktionary-derived dictionaries retain their own attribution",
        train_sha256=sha(args.train), dictionary_sha256={lang: sha(args.dictionary_dir / ('d-'+lang+'.sqlite')) for lang in dictionaries},
        script_sha256=sha(Path(__file__)), selection="Top500 word frequencies across free-human convai2-context training turns, deterministic count then alphabetic order; no evaluation text selection.", rows=rows)
    assert not args.output.exists()
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print("turns", selected_turns, "candidate words", sum(bool(r["candidates"]) for r in rows))


if __name__ == "__main__":
    main()
